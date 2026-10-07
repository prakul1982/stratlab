"""Prices from Yahoo Finance's public chart and search endpoints (no key).

Used for index levels, charts, Indian quotes when Kite is offline, and as the
data source for US, UK, European, Japanese and forex backtests."""
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from .net import BROWSER_UA, Source, SourceError

# Yahoo's intraday history only goes back so far
INTERVAL = {"1d": ("1d", 3650 * 3), "1h": ("60m", 729), "15m": ("15m", 59), "5m": ("5m", 59)}


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


class Yahoo(Source):
    name = "Yahoo Finance"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://query1.finance.yahoo.com", per_minute=90, burst=15,
                         headers={"User-Agent": BROWSER_UA, "Accept": "application/json"}, transport=transport)
        self._recent: dict = {}

    WINDOW = 760                 # days of daily candles fetched when looking an instrument up (scan and rotation need ~700)

    def chart(self, symbol: str, tf: str = "1d", days: int = 365, ttl: float | None = None, exact: bool = False) -> dict:
        """{"meta": {...}, "candles": [{t, o, h, l, c, v}]} with times in the exchange's zone. A shorter window of
        daily candles is cut from a longer one fetched recently, so a lookup followed by a backtest costs one call."""
        interval, max_days = INTERVAL[tf]
        days = max(1, min(days, max_days))
        keep = ttl if ttl is not None else (1800 if tf == "1d" else 60)
        recent = self._recent.get((symbol, tf)) if tf == "1d" and not exact else None
        if recent and recent[1] >= days and time.time() - recent[0] < keep:
            cut = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
            return {"meta": recent[2]["meta"], "candles": [b for b in recent[2]["candles"] if b["t"][:10] >= cut]}
        out = self._chart(symbol, tf, days, interval, ttl)
        if tf == "1d" and not exact and (not recent or days >= recent[1] or time.time() - recent[0] >= keep):
            if len(self._recent) > 500:
                self._recent.clear()
            self._recent[(symbol, tf)] = (time.time(), days, out)
        return out

    def _raw_chart(self, symbol: str, tf: str, days: int) -> dict:
        """The source's answer as sent, uncached: for diagnosing missing candles."""
        interval, _ = INTERVAL[tf]
        now = int(time.time())
        return self.fetch(f"/v8/finance/chart/{symbol}", {"interval": interval, "period1": now - days * 86400,
                                                          "period2": now, "includePrePost": "false"}, ttl=0)

    def _chart(self, symbol: str, tf: str, days: int, interval: str, ttl: float | None) -> dict:
        now = int(time.time())
        # round the window so repeated calls share a cache entry
        step = 3600 if tf == "1d" else 60
        end = now - now % step + step
        params = {"interval": interval, "period1": end - days * 86400, "period2": end,
                  "includePrePost": "false", "events": "div,splits"}
        data = self.fetch(f"/v8/finance/chart/{symbol}", params,
                          ttl=ttl if ttl is not None else (1800 if tf == "1d" else 60))
        res = ((data or {}).get("chart") or {}).get("result") or []
        if not res:
            err = ((data or {}).get("chart") or {}).get("error") or {}
            raise SourceError(self.name, err.get("description") or f"Yahoo has no prices for {symbol}.")
        r = res[0]
        meta = r.get("meta") or {}
        tz = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
        q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
        candles = []
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
                continue
            if tf == "1d":   # daily candles are stamped at the session open; keep the date only
                t = t.replace(hour=0, minute=0, second=0, microsecond=0)
            v = (q.get("volume") or [None] * (i + 1))[i]
            if filled and not v:
                v = meta.get("regularMarketVolume")
            candles.append({"t": t.isoformat(), "o": float(o), "h": float(h), "l": float(l), "c": float(c),
                            "v": float(v or 0)})
        # Yahoo sometimes repeats the live bar; keep the last copy of each time
        dedup = {}
        for b in candles:
            dedup[b["t"]] = b
        return {"meta": meta, "candles": list(dedup.values())}

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
        # exact: the previous close in a chart's meta is the close before its window, so it must be this short window
        m = self.chart(symbol, "1d", 7, ttl=60, exact=True)["meta"]
        price, prev = m.get("regularMarketPrice"), m.get("chartPreviousClose") or m.get("previousClose")
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
            "at": datetime.fromtimestamp(m["regularMarketTime"], timezone.utc).isoformat(timespec="seconds") if isinstance(m.get("regularMarketTime"), (int, float)) else None,
        }

    def search(self, q: str, limit: int = 15) -> list[dict]:
        data = self.fetch("https://query2.finance.yahoo.com/v1/finance/search",
                          {"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0}, ttl=24 * 3600)
        return [x for x in (data or {}).get("quotes") or [] if x.get("symbol")]
