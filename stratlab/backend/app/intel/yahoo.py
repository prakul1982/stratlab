"""Prices from Yahoo Finance's public chart and search endpoints (no key).

Used for index levels, charts, Indian quotes when Kite is offline, and as the
data source for US, UK, European, Japanese and forex backtests."""
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from .net import BROWSER_UA, NotFound, Source, SourceError

# Yahoo's intraday history only goes back so far
INTERVAL = {"1d": ("1d", 3650 * 3), "1h": ("60m", 729), "15m": ("15m", 59), "5m": ("5m", 59)}


STEP = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}      # an intraday candle's length, seconds


def _fold_live(candles: list[dict], step: int) -> list[dict]:
    """While a session trades, the source ends each intraday answer with one more row stamped at the moment it was read (15:12:53)
    instead of a candle's start: the market's latest price, beside the candle it belongs to. Drawn as it came it is a one-price
    candle next to the real one, and the live candle then grows on a grid shifted by those seconds all session (MWR1-019). The
    row goes into the candle that holds it (its close, high and low), or is that candle when the answer has none yet (a
    1-minute chart has no row for the minute in progress)."""
    out: list[dict] = []
    for b in candles:
        t = datetime.fromisoformat(b["t"])
        if t.second == 0 and t.microsecond == 0:
            out.append(b)
            continue
        if out:
            s = datetime.fromisoformat(out[-1]["t"])
            start = s + timedelta(seconds=((t - s).total_seconds() // step) * step)
        else:
            start = t.replace(second=0, microsecond=0)
        if out and start == datetime.fromisoformat(out[-1]["t"]):
            last = out[-1]
            last["c"], last["h"], last["l"] = b["c"], max(last["h"], b["h"]), min(last["l"], b["l"])
        else:
            out.append({**b, "t": start.isoformat()})
    return out


def _from_quote(meta: dict, tz, day: datetime, ohl: tuple, prev_close: float | None) -> tuple:
    """For London and Frankfurt, Yahoo often sends the latest session's daily candle with a blank close, while the
    same answer's quote has that session's last price and day range. Rebuild that one candle from the quote; any
    other blank day stays blank. The open, if also blank, is the previous close kept inside the day's range."""
    o, h, l = ohl
    at, price = meta.get("regularMarketTime"), meta.get("regularMarketPrice")
    if not at or price is None or datetime.fromtimestamp(at, timezone.utc).astimezone(tz).date() != day.date():
        return o, h, l, None
    h = h if h is not None else meta.get("regularMarketDayHigh")
    l = l if l is not None else meta.get("regularMarketDayLow")
    if h is None or l is None:
        return o, h, l, None
    if o is None:
        o = min(max(prev_close if prev_close is not None else price, l), h)
    c = float(price)
    return o, max(h, o, c), min(l, o, c), c


def _previous_close(meta: dict, candles: list[dict]) -> float | None:
    """The close of the session before the last trade's. The meta's chartPreviousClose is the close before the chart's
    window (about a week back for a 7-day window), so a "day's change" read from it is really the week's."""
    last = meta.get("regularMarketTime")
    try:
        day = datetime.fromtimestamp(last, ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")).date().isoformat() \
            if isinstance(last, (int, float)) else (candles[-1]["t"][:10] if candles else None)
    except (OverflowError, OSError, ValueError):
        day = candles[-1]["t"][:10] if candles else None
    before = [c["c"] for c in candles if day and c["t"][:10] < day]
    if before:
        return before[-1]
    # a stock's first session has no close before it: the reference is its issue price, while "previousClose" is the
    # listing auction's price, the day's open (DD-010: ZETWERK -13.19% against ₹159.25, not -8.4% against ₹151)
    if day and _first_trade_day(meta) == day:
        return _issue_price(meta, candles)
    return meta.get("previousClose") or meta.get("chartPreviousClose")


def _issue_price(meta: dict, candles: list[dict]) -> float | None:
    """A listing's issue price, from the day's own change fields (price less the day's change: ZETWERK 138.25 - -12.75 =
    151, TONBO 700). The chart's chartPreviousClose is the issue price only for a "range" request; for the explicit
    period this reader asks it is the day's open (RC1-001: 159.25 and 1,160 shown as the "issue price"). When neither
    change field is there, chartPreviousClose stands only if it isn't the first candle's open; else None."""
    price = meta.get("regularMarketPrice")
    if isinstance(price, (int, float)) and price > 0:
        change, pct = meta.get("fulldayChange"), meta.get("regularMarketChangePercent")
        if isinstance(change, (int, float)) and price - change > 0:
            return round(price - change, 2)
        if isinstance(pct, (int, float)) and pct > -100:
            return round(price / (1 + pct / 100), 2)
    ref = meta.get("chartPreviousClose")
    opened = candles[0].get("o") if candles else None
    return ref if isinstance(ref, (int, float)) and ref > 0 and (opened is None or abs(ref - opened) > 1e-6) else None


def _first_trade_day(meta: dict) -> str | None:
    """The day (in the exchange's zone) of a listing's first trade, from the answer's firstTradeDate; None without one."""
    t = meta.get("firstTradeDate")
    try:
        return datetime.fromtimestamp(t, ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")).date().isoformat() \
            if isinstance(t, (int, float)) else None
    except (OverflowError, OSError, ValueError):
        return None


# the market whose trading days a Yahoo answer follows, by its instrument type, else by its exchange's zone
MARKET_OF = {"CURRENCY": "FX", "FUTURE": "CMDTY", "Asia/Kolkata": "IN", "America/New_York": "US", "Europe/London": "UK",
             "Europe/Berlin": "EU", "Asia/Tokyo": "JP"}


def _partial(out: dict, now: float | None = None) -> bool:
    """Whether the last daily candle is of a session still trading: today's candle, on a trading day of its market, with
    the answer's own session open now. Crypto trades all day: today's (UTC) candle is still forming."""
    from ..data.calendar import is_trading_day
    now = now or time.time()
    try:
        meta = out["meta"]
        tz = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
        today = datetime.fromtimestamp(now, tz).date()
        if out["candles"][-1]["t"][:10] != today.isoformat():
            return False
        if meta.get("instrumentType") == "CRYPTOCURRENCY":
            return True
        market = MARKET_OF.get(meta.get("instrumentType")) or MARKET_OF.get(meta.get("exchangeTimezoneName"))
        if market and not is_trading_day(market, today):
            return False
        period = meta["currentTradingPeriod"]["regular"]
        return (period.get("start") or 0) <= now < period["end"]
    except (KeyError, IndexError, TypeError, ValueError):
        return False


class Yahoo(Source):
    name = "Yahoo Finance"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://query1.finance.yahoo.com", per_minute=90, burst=15,
                         headers={"User-Agent": BROWSER_UA, "Accept": "application/json"}, transport=transport)
        self._recent: dict = {}

    def check(self, r: httpx.Response):
        # a symbol the source has never heard of is answered 404: a wrong symbol, not a fault (RC1-004: Compare with "ZZZZ" said
        # "Prices couldn't be read just now" because the chart route answered it as a 502)
        if r.status_code == 404:
            raise NotFound(self.name, "No prices found for that symbol. Check it and try again.")
        super().check(r)

    WINDOW = 760                 # days of daily candles fetched when looking an instrument up (scan and rotation need ~700)

    def chart(self, symbol: str, tf: str = "1d", days: int = 365, ttl: float | None = None, exact: bool = False) -> dict:
        """{"meta": {...}, "candles": [{t, o, h, l, c, v}]} with times in the exchange's zone. A shorter window of
        daily candles is cut from a longer one fetched recently, so a lookup followed by a backtest costs one call."""
        interval, max_days = INTERVAL[tf]
        days = max(1, min(days, max_days))
        keep = ttl if ttl is not None else (1800 if tf == "1d" else 60)
        recent = self._recent.get((symbol, tf)) if tf == "1d" and not exact else None
        # a copy kept here is as old as when the source answered it (it may have come from the source's cache), never
        # older than this caller allows (R7V-005: candles read in the minutes after the close, before the close was
        # final, given to the page that asked for a read after it)
        if recent and ttl is None and time.time() - recent[0] >= 60 and _partial(recent[2]):
            recent = None             # a daily candle of a session still trading is reused for a minute at most
        if recent and recent[1] >= days and time.time() - recent[0] < keep:
            cut = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
            return {"meta": recent[2]["meta"], "candles": [b for b in recent[2]["candles"] if b["t"][:10] >= cut]}
        out, at = self._chart(symbol, tf, days, interval, ttl, with_time=True)
        if tf == "1d" and ttl is None and time.time() - at >= 60 and _partial(out):
            out, at = self._chart(symbol, tf, days, interval, 60, with_time=True)
        if tf == "1d" and not exact and (not recent or days >= recent[1] or time.time() - recent[0] >= keep):
            if len(self._recent) > 500:
                self._recent.clear()
            self._recent[(symbol, tf)] = (at, days, out)
        return out

    def _raw_chart(self, symbol: str, tf: str, days: int) -> dict:
        """The source's answer as sent, uncached: for diagnosing missing candles."""
        interval, _ = INTERVAL[tf]
        now = int(time.time())
        return self.fetch(f"/v8/finance/chart/{symbol}", {"interval": interval, "period1": now - days * 86400,
                                                          "period2": now, "includePrePost": "false"}, ttl=0)

    def _chart(self, symbol: str, tf: str, days: int, interval: str, ttl: float | None, with_time: bool = False):
        now = int(time.time())
        # round the window so repeated calls share a cache entry
        step = 3600 if tf == "1d" else 60
        end = now - now % step + step
        params = {"interval": interval, "period1": end - days * 86400, "period2": end,
                  "includePrePost": "false", "events": "div,splits"}
        data, at = self.fetch(f"/v8/finance/chart/{symbol}", params,
                              ttl=ttl if ttl is not None else (1800 if tf == "1d" else 60), with_time=True)
        res = ((data or {}).get("chart") or {}).get("result") or []
        if not res:
            err = ((data or {}).get("chart") or {}).get("error") or {}
            raise SourceError(self.name, err.get("description") or f"Yahoo has no prices for {symbol}.")
        r = res[0]
        meta = r.get("meta") or {}
        tz = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
        q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
        candles, blank = [], []
        for i, ts in enumerate(r.get("timestamp") or []):
            try:
                o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            except (KeyError, IndexError):
                continue
            t = datetime.fromtimestamp(ts, timezone.utc).astimezone(tz)
            filled = c is None and tf == "1d"
            if filled:
                o, h, l, c = _from_quote(meta, tz, t, (o, h, l), candles[-1]["c"] if candles else None)
            if None in (o, h, l, c):
                if tf == "1d":
                    blank.append(t.date().isoformat())
                continue
            if tf == "1d":   # daily candles are stamped at the session open; keep the date only
                t = t.replace(hour=0, minute=0, second=0, microsecond=0)
            v = (q.get("volume") or [None] * (i + 1))[i]
            if filled and not v:
                v = meta.get("regularMarketVolume")
            candles.append({"t": t.isoformat(), "o": float(o), "h": float(h), "l": float(l), "c": float(c),
                            "v": float(v or 0)})
        if tf in STEP:
            candles = _fold_live(candles, STEP[tf])
        # Yahoo sometimes repeats the live bar; keep the last copy of each time
        dedup = {}
        for b in candles:
            dedup[b["t"]] = b
        if blank:
            for b in self._from_hours(symbol, blank, tz).values():
                dedup.setdefault(b["t"], b)
        out = {"meta": meta, "candles": sorted(dedup.values(), key=lambda b: b["t"])}
        return (out, at) if with_time else out

    BLANK_DAYS = 30          # how far back a blank daily candle is rebuilt from hourly ones

    def _from_hours(self, symbol: str, days: list[str], tz) -> dict[str, dict]:
        """Daily candles for recent sessions the daily answer sent blank, built from that day's hourly candles (R81-002:
        Yahoo sent 21 Oct blank for NVDA, AAPL, MSFT and AMZN, so their charts skipped the day and their day's change was
        measured from 20 Oct). {day: candle}; nothing when the hours aren't there either."""
        today = datetime.now(tz).date()
        want = sorted(d for d in set(days) if (today - datetime.fromisoformat(d).date()).days <= self.BLANK_DAYS)
        if not want:
            return {}
        span = (today - datetime.fromisoformat(want[0]).date()).days + 2
        try:
            hours = self._chart(symbol, "1h", span, INTERVAL["1h"][0], 3600)["candles"]
        except Exception:                     # the hours unreadable too: the day stays out, as before
            return {}
        out = {}
        for d in want:
            hs = [b for b in hours if b["t"][:10] == d]
            if not hs:
                continue
            start = datetime.fromisoformat(hs[0]["t"]).replace(hour=0, minute=0, second=0, microsecond=0)
            out[d] = {"t": start.isoformat(), "o": hs[0]["o"], "h": max(b["h"] for b in hs), "l": min(b["l"] for b in hs),
                      "c": hs[-1]["c"], "v": float(sum(b.get("v") or 0 for b in hs))}
        return out

    def events(self, symbol: str, days: int = 1100) -> dict:
        """The dividends and splits in a stock's daily price history, by ex-date in the exchange's zone:
        {"dividends": [{"date", "amount"}], "splits": [{"date", "numerator", "denominator"}]}. Past ex-dates only."""
        now = int(time.time())
        end = now - now % 3600 + 3600
        data = self.fetch(f"/v8/finance/chart/{symbol}", {"interval": "1d", "period1": end - days * 86400, "period2": end,
                                                          "includePrePost": "false", "events": "div,splits"}, ttl=12 * 3600)
        res = ((data or {}).get("chart") or {}).get("result") or []
        if not res:
            raise SourceError(self.name, f"No price history for {symbol}.")
        tz = ZoneInfo((res[0].get("meta") or {}).get("exchangeTimezoneName") or "UTC")
        ev = res[0].get("events") or {}
        day = lambda ts: datetime.fromtimestamp(int(ts), timezone.utc).astimezone(tz).date().isoformat()
        out = {"dividends": [], "splits": []}
        for d in (ev.get("dividends") or {}).values():
            try:
                out["dividends"].append({"date": day(d["date"]), "amount": float(d["amount"])})
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
        for s in (ev.get("splits") or {}).values():
            try:
                out["splits"].append({"date": day(s["date"]), "numerator": float(s["numerator"]), "denominator": float(s["denominator"])})
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
        return out

    def meta(self, symbol: str) -> dict:
        """Price, previous close, day range and 52-week range for one symbol."""
        # exact: a fresh short window, never cut from a long download, so the last sessions are today's
        got = self.chart(symbol, "1d", 7, ttl=60, exact=True)
        m = got["meta"]
        price, prev = m.get("regularMarketPrice"), _previous_close(m, got["candles"])
        return {
            "symbol": m.get("symbol", symbol), "name": m.get("longName") or m.get("shortName"),
            "currency": m.get("currency"), "exchange": m.get("fullExchangeName") or m.get("exchangeName"),
            "price": price, "prev_close": prev,
            "change": (price - prev) if price is not None and prev else None,
            "change_pct": ((price / prev - 1) * 100) if price is not None and prev else None,
            "high": m.get("regularMarketDayHigh"), "low": m.get("regularMarketDayLow"),
            "volume": m.get("regularMarketVolume"),
            "high52": m.get("fiftyTwoWeekHigh"), "low52": m.get("fiftyTwoWeekLow"),
            "tz": m.get("exchangeTimezoneName"), "type": m.get("instrumentType"),
            # the listing's first trading day: a new listing's first session is changed against its issue price (DD-010)
            "first_trade": _first_trade_day(m),
            "at": datetime.fromtimestamp(m["regularMarketTime"], timezone.utc).isoformat(timespec="seconds") if isinstance(m.get("regularMarketTime"), (int, float)) else None,
        }

    def search(self, q: str, limit: int = 15) -> list[dict]:
        data = self.fetch("https://query2.finance.yahoo.com/v1/finance/search",
                          {"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0}, ttl=24 * 3600)
        return [x for x in (data or {}).get("quotes") or [] if x.get("symbol")]
