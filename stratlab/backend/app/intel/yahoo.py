"""Prices from Yahoo Finance's public chart and search endpoints (no key).

Used for index levels, charts, Indian quotes when Kite is offline, and as the
data source for US, UK, European, Japanese and forex backtests."""
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from .net import BROWSER_UA, Source, SourceError

# Yahoo's intraday history only goes back so far
INTERVAL = {"1d": ("1d", 3650 * 3), "1h": ("60m", 729), "15m": ("15m", 59), "5m": ("5m", 59)}


class Yahoo(Source):
    name = "Yahoo Finance"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://query1.finance.yahoo.com", per_minute=90, burst=15,
                         headers={"User-Agent": BROWSER_UA, "Accept": "application/json"}, transport=transport)

    def chart(self, symbol: str, tf: str = "1d", days: int = 365, ttl: float | None = None) -> dict:
        """{"meta": {...}, "candles": [{t, o, h, l, c, v}]} with times in the exchange's zone."""
        interval, max_days = INTERVAL[tf]
        days = max(1, min(days, max_days))
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
            if None in (o, h, l, c):
                continue
            t = datetime.fromtimestamp(ts, timezone.utc).astimezone(tz)
            if tf == "1d":   # daily candles are stamped at the session open; keep the date only
                t = t.replace(hour=0, minute=0, second=0, microsecond=0)
            v = (q.get("volume") or [None] * (i + 1))[i]
            candles.append({"t": t.isoformat(), "o": float(o), "h": float(h), "l": float(l), "c": float(c),
                            "v": float(v or 0)})
        # Yahoo sometimes repeats the live bar; keep the last copy of each time
        dedup = {}
        for b in candles:
            dedup[b["t"]] = b
        return {"meta": meta, "candles": list(dedup.values())}

    def meta(self, symbol: str) -> dict:
        """Price, previous close, day range and 52-week range for one symbol."""
        m = self.chart(symbol, "1d", 7, ttl=60)["meta"]
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
        }

    def search(self, q: str, limit: int = 15) -> list[dict]:
        data = self.fetch("https://query2.finance.yahoo.com/v1/finance/search",
                          {"q": q, "quotesCount": limit, "newsCount": 0, "listsCount": 0}, ttl=24 * 3600)
        return [x for x in (data or {}).get("quotes") or [] if x.get("symbol")]
