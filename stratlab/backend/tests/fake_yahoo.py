"""A fake Yahoo Finance: wavy daily/intraday prices and a small search catalogue."""
import math
import zlib
import time

import httpx

from tests.fake_prices import level

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
    return {"VOD.L": 7000.0, "7203.T": 2800.0, "EURUSD=X": 1.1}.get(sym) or level(sym, 19000) or 180.0   # Indian names: fake_prices


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
            g = STEP[req.url.params["interval"]]
            p1, p2 = int(req.url.params["period1"]), min(int(req.url.params["period2"]), int(time.time()))
            ts, o, h, l, c, v = [], [], [], [], [], []
            t = p1 - p1 % g
            b = base_price(sym)
            while t <= p2:
                d = t / 86400
                phase = (zlib.crc32(sym.encode()) % 628) / 100 if varied else 0   # varied: each symbol its own rhythm
                px = b * (1 + 0.0003 * (d - 19000)) + b * 0.08 * math.sin(d / 9 + phase) + b * 0.01 * math.sin(t / 7000)
                ts.append(t); o.append(px * 0.998); h.append(px * 1.01); l.append(px * 0.99); c.append(px); v.append(1000)
                t += g
            meta = {"symbol": sym, "currency": cur, "exchangeTimezoneName": tz, "regularMarketPrice": c[-1],
                    "chartPreviousClose": c[-2] if len(c) > 1 else c[-1], "fiftyTwoWeekHigh": max(c) * 1.02,
                    "fiftyTwoWeekLow": min(c) * 0.98, "regularMarketDayHigh": h[-1], "regularMarketDayLow": l[-1],
                    "regularMarketVolume": 123456, "longName": next((x.get("longname") or x["shortname"] for x in CATALOGUE if x["symbol"] == sym), sym),
                    "instrumentType": "ETF" if sym == "SPY" else "EQUITY", "fullExchangeName": "Test"}
            res = {"meta": meta, "timestamp": ts, "indicators": {"quote": [{"open": o, "high": h, "low": l, "close": c, "volume": v}]}}
            if "div" in req.url.params.get("events", "") and sym == "AAPL" and g == 86400:     # a dividend and a split in its history
                div, split = ts[-30] if len(ts) > 30 else ts[0], ts[-300] if len(ts) > 300 else ts[0]
                res["events"] = {"dividends": {str(div): {"amount": 0.26, "date": div}},
                                 "splits": {str(split): {"date": split, "numerator": 4, "denominator": 1, "splitRatio": "4:1"}}}
            if "div" in req.url.params.get("events", "") and sym in OTHER_PAYERS and g == 86400 and len(ts) > 40:
                # a dividend a few days ago (a different day for each company) and, for one, a split: for the US corporate-actions list
                k = 2 + zlib.crc32(sym.encode()) % 24
                res["events"] = {"dividends": {str(ts[-k]): {"amount": round(0.3 + (zlib.crc32(sym.encode()) % 90) / 100, 2), "date": ts[-k]}}}
                if sym == "NVDA":
                    res["events"]["splits"] = {str(ts[-9]): {"date": ts[-9], "numerator": 10, "denominator": 1, "splitRatio": "10:1"}}
            return httpx.Response(200, json={"chart": {"result": [res], "error": None}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)
