"""A fake Yahoo Finance: wavy daily/intraday prices and a small search catalogue."""
import math
import zlib
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from tests import fake_prices

CATALOGUE = [
    {"symbol": "AAPL", "shortname": "Apple Inc.", "longname": "Apple Inc.", "exchange": "NMS", "exchDisp": "NASDAQ", "quoteType": "EQUITY"},
    {"symbol": "AAPL.MX", "shortname": "APPLE INC", "exchange": "MEX", "quoteType": "EQUITY"},
    {"symbol": "SPY", "shortname": "SPDR S&P 500", "exchange": "PCX", "exchDisp": "NYSEArca", "quoteType": "ETF"},
    {"symbol": "VOD.L", "shortname": "VODAFONE GROUP PLC", "exchange": "LSE", "quoteType": "EQUITY"},
    {"symbol": "SAP.DE", "shortname": "SAP SE", "exchange": "GER", "quoteType": "EQUITY"},
    {"symbol": "7203.T", "shortname": "TOYOTA MOTOR CORP", "exchange": "JPX", "quoteType": "EQUITY"},
    {"symbol": "EURUSD=X", "shortname": "EUR/USD", "exchange": "CCY", "quoteType": "CURRENCY"},
    {"symbol": "RELIANCE.NS", "shortname": "RELIANCE INDUSTRIES", "longname": "Reliance Industries Limited", "exchange": "NSI", "quoteType": "EQUITY"},
]
OTHER_PAYERS = {"MSFT", "JPM", "KO", "XOM", "PG", "JNJ", "HD", "CVX", "PEP", "ABBV", "MRK", "WMT", "NVDA", "COST", "V", "MA"}
TZ = {".L": ("Europe/London", "GBp"), ".DE": ("Europe/Berlin", "EUR"), ".T": ("Asia/Tokyo", "JPY"),
      "=X": ("Europe/London", "USD"), ".NS": ("Asia/Kolkata", "INR")}
STEP = {"1d": 86400, "60m": 3600, "15m": 900, "5m": 300}


def base_price(sym: str) -> float:
    return {"VOD.L": 7000.0, "7203.T": 2800.0, "EURUSD=X": 1.1}.get(sym) or 180.0   # the demo world's own names: fake_prices


def _shared(sym: str, t: int, p2: int, g: int):
    """Candles from the demo world's price table (fake_prices), the broker's own numbers: in the market's hours only,
    each closing at the price at its end (or now, for the one still forming), none after the last trade. Daily candles
    run from the session's open to its close and are stamped at the open, as the real feed stamps them."""
    from datetime import timezone
    market = fake_prices.market_of(sym)
    (oh, om), (ch, cm), zone = fake_prices.SESSION[market]
    clock = fake_prices.session_clock(None, market)
    end_at = min(p2, int(clock.timestamp()))
    ts, o, h, l, c, v = [], [], [], [], [], []
    while t <= end_at:
        if g == 86400:
            day = datetime.fromtimestamp(t, timezone.utc).date()
            start = datetime(day.year, day.month, day.day, oh, om, tzinfo=zone)
            end = start.replace(hour=ch, minute=cm)
        else:
            start = datetime.fromtimestamp(t, zone)
            end = datetime.fromtimestamp(t + g, zone)
            day = start.date()
        hours_ok = g == 86400 or ((start.hour, start.minute) >= (oh, om) and (start.hour, start.minute) < (ch, cm))
        if hours_ok and start <= clock and fake_prices.trading_day(market, day):
            a, b = fake_prices.price(sym, start), fake_prices.price(sym, min(end, clock))
            ts.append(int(start.timestamp())); o.append(a); h.append(round(max(a, b) * 1.004, 2)); l.append(round(min(a, b) * 0.996, 2)); c.append(b)
            v.append(0 if sym.endswith("=X") else 1000)
        t += g
    return ts, o, h, l, c, v, clock


def fake_yahoo(fail: set | None = None, varied: bool = False) -> httpx.MockTransport:
    def handler(req: httpx.Request):
        path = req.url.path
        if path.startswith("/v1/finance/search"):
            q = req.url.params["q"].lower()
            return httpx.Response(200, json={"quotes": [x for x in CATALOGUE if q in x["symbol"].lower()
                                                        or q in (x.get("longname") or x["shortname"]).lower()]})
        if path.startswith("/v8/finance/chart/"):
            sym = path.rsplit("/", 1)[1]
            if fail and sym in fail or sym.startswith("NOPE"):
                return httpx.Response(404, json={"chart": {"result": None, "error": {"description": "No data found"}}})
            tz, cur = next((v for k, v in TZ.items() if sym.endswith(k)), ("America/New_York", "USD"))
            if fake_prices.known(sym) and fake_prices.market_of(sym) == "IN":
                tz, cur = "Asia/Kolkata", "INR"
            g = STEP[req.url.params["interval"]]
            p1, p2 = int(req.url.params["period1"]), min(int(req.url.params["period2"]), int(time.time()))
            ts, o, h, l, c, v = [], [], [], [], [], []
            clock = None
            t = p1 - p1 % g
            b = base_price(sym)
            zone = ZoneInfo(tz)
            if fake_prices.known(sym):       # the demo world's own instruments: the one shared price table (fake_prices)
                ts, o, h, l, c, v, clock = _shared(sym, t, p2, g)
                p2 = -1                      # skip the made-up wave below
            while t <= p2:
                if datetime.fromtimestamp(t, zone).weekday() >= 5:     # like the real feed: these markets close at weekends
                    t += g
                    continue
                d = t / 86400
                phase = (zlib.crc32(sym.encode()) % 628) / 100 if varied else 0   # varied: each symbol its own rhythm
                px = b * (1 + 0.0003 * (d - 19000)) + b * 0.08 * math.sin(d / 9 + phase) + b * 0.01 * math.sin(t / 7000)
                ts.append(t); o.append(px * 0.998); h.append(px * 1.01); l.append(px * 0.99); c.append(px)
                v.append(0 if sym.endswith("=X") else 1000)     # spot forex has no exchange volume
                t += g
            meta = {"symbol": sym, "currency": cur, "exchangeTimezoneName": tz, "regularMarketPrice": c[-1],
                    "chartPreviousClose": c[-2] if len(c) > 1 else c[-1], "fiftyTwoWeekHigh": max(c) * 1.02,
                    "fiftyTwoWeekLow": min(c) * 0.98, "regularMarketDayHigh": h[-1], "regularMarketDayLow": l[-1],
                    "regularMarketVolume": 123456, "longName": next((x.get("longname") or x["shortname"] for x in CATALOGUE if x["symbol"] == sym), sym),
                    "instrumentType": "ETF" if sym == "SPY" else "EQUITY", "fullExchangeName": "Test"}
            if clock is not None:            # the time of the last trade: the close, out of hours
                meta["regularMarketTime"] = int(clock.timestamp())
                meta["longName"] = fake_prices.name_of(fake_prices.canonical(sym)) or meta["longName"]
            res = {"meta": meta, "timestamp": ts, "indicators": {"quote": [{"open": o, "high": h, "low": l, "close": c, "volume": v}]}}
            if "div" in req.url.params.get("events", "") and sym == "AAPL" and g == 86400:     # a dividend and a split in its history
                div, split = ts[-30] if len(ts) > 30 else ts[0], ts[-300] if len(ts) > 300 else ts[0]
                res["events"] = {"dividends": {str(div): {"amount": 0.26, "date": div}},
                                 "splits": {str(split): {"date": split, "numerator": 4, "denominator": 1, "splitRatio": "4:1"}}}
            if "div" in req.url.params.get("events", "") and sym in OTHER_PAYERS and g == 86400 and len(ts) > 40:
                # a dividend a few days ago (a different day for each company) and, for one, a split: for the US corporate-actions list
                k = 2 + zlib.crc32(sym.encode()) % 15      # at most 16 trading days back: always inside the four-week window, whatever the weekday or holidays
                res["events"] = {"dividends": {str(ts[-k]): {"amount": round(0.3 + (zlib.crc32(sym.encode()) % 90) / 100, 2), "date": ts[-k]}}}
                if sym == "NVDA":
                    res["events"]["splits"] = {str(ts[-9]): {"date": ts[-9], "numerator": 10, "denominator": 1, "splitRatio": "10:1"}}
            return httpx.Response(200, json={"chart": {"result": [res], "error": None}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)
