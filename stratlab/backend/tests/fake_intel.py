"""Fake Finnhub, Screener.in, Google News and Wikipedia for tests and the local harness."""
import json
import os

import httpx

HERE = os.path.dirname(__file__)
SCREENER_HTML = open(os.path.join(HERE, "fixtures", "screener_reliance.html"), encoding="utf-8").read()

PROFILE = {"country": "US", "currency": "USD", "exchange": "NASDAQ NMS - GLOBAL MARKET", "finnhubIndustry": "Semiconductors",
           "ipo": "1999-01-22", "logo": "https://static.finnhub.io/logo/nvda.png", "marketCapitalization": 4312000.5,
           "name": "NVIDIA Corp", "ticker": "NVDA", "weburl": "https://www.nvidia.com/"}
METRIC = {"metric": {"52WeekHigh": 195.6, "52WeekLow": 86.6, "peTTM": 52.3, "forwardPE": 33.1, "psTTM": 26.4, "pb": 45.2,
                     "evEbitdaTTM": 44.1, "grossMarginTTM": 70.1, "operatingMarginTTM": 58.1, "netProfitMarginTTM": 52.4,
                     "roeTTM": 105.2, "roaTTM": 70.3, "revenueGrowthTTMYoy": 71.6, "epsGrowthTTMYoy": 64.3,
                     "revenueGrowth3Y": 91.2, "revenueGrowth5Y": 64.1, "epsGrowth5Y": 90.2, "currentRatioQuarterly": 4.2,
                     "longTermDebt/equityQuarterly": 0.07, "epsTTM": 3.51, "beta": 2.1, "52WeekPriceReturnDaily": 48.2,
                     "dividendYieldIndicatedAnnual": 0.02, "payoutRatioTTM": 1.1}}
QUOTE = {"c": 183.2, "d": 2.4, "dp": 1.33, "h": 184.9, "l": 180.1, "o": 181.0, "pc": 180.8, "t": 1790000000}
FIN = {"data": [{"year": y, "report": {"ic": [{"label": "Revenue", "concept": "us-gaap_Revenues", "value": rev},
                                              {"label": "Net income", "concept": "us-gaap_NetIncomeLoss", "value": ni}]}}
                for y, rev, ni in ((2025, 130497e6, 72880e6), (2024, 60922e6, 29760e6), (2023, 26974e6, 4368e6),
                                   (2022, 26914e6, 9752e6))]}
EARN = [{"period": p, "actual": a, "estimate": e, "surprisePercent": s} for p, a, e, s in
        (("2025-07-31", 1.05, 1.01, 3.9), ("2025-04-30", 0.96, 0.93, 3.2), ("2025-01-31", 0.89, 0.85, 4.7), ("2024-10-31", 0.81, 0.75, 8.0))]
NEWS = [{"headline": "Nvidia unveils new data centre chips", "url": "https://example.com/1", "source": "Reuters", "datetime": 1790000000},
        {"headline": "Chip stocks rally on AI demand", "url": "https://example.com/2", "source": "CNBC", "datetime": 1789990000}]
RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>Reliance shares rise after strong Jio numbers - Economic Times</title><link>https://example.com/et</link><pubDate>Wed, 24 Sep 2026 08:00:00 GMT</pubDate><source url="https://economictimes.com">Economic Times</source></item>
<item><title>Nifty ends higher as banks gain &amp; IT slips - Mint</title><link>https://example.com/mint</link><pubDate>Wed, 24 Sep 2026 10:30:00 GMT</pubDate><source url="https://livemint.com">Mint</source></item>
</channel></rss>"""


def fake_finnhub(reject: bool = False) -> httpx.MockTransport:
    def handler(req: httpx.Request):
        if reject:
            return httpx.Response(401, json={"error": "Invalid API key"})
        p, sym = req.url.path, req.url.params.get("symbol", "")
        if sym == "NOPE" and p.endswith("/profile2"):
            return httpx.Response(200, json={})
        routes = {"/api/v1/stock/profile2": PROFILE, "/api/v1/quote": QUOTE, "/api/v1/stock/metric": METRIC,
                  "/api/v1/company-news": NEWS, "/api/v1/stock/peers": ["NVDA", "AMD", "AVGO", "INTC"],
                  "/api/v1/stock/recommendation": [{"period": "2025-09-01", "strongBuy": 24, "buy": 38, "hold": 7, "sell": 1, "strongSell": 0}],
                  "/api/v1/stock/earnings": EARN, "/api/v1/stock/financials-reported": FIN,
                  "/api/v1/stock/insider-transactions": {"data": [{"name": "Huang Jen-Hsun", "change": -120000, "filingDate": "2026-09-10"},
                                                                  {"name": "Kress Colette", "change": -30000, "filingDate": "2026-09-02"}]},
                  "/api/v1/calendar/earnings": {"earningsCalendar": [{"date": "2099-11-19", "epsEstimate": 1.2, "symbol": "NVDA"}]},
                  "/api/v1/search": {"result": [{"symbol": "NVDA", "description": "NVIDIA CORP", "type": "Common Stock"},
                                                {"symbol": "NVDA.SW", "description": "NVIDIA CORP", "type": "Common Stock"}]},
                  "/api/v1/news": NEWS}
        if p in routes:
            return httpx.Response(200, json=routes[p])
        return httpx.Response(404, json={})
    return httpx.MockTransport(handler)


def fake_screener() -> httpx.MockTransport:
    def handler(req: httpx.Request):
        if "/company/RELIANCE/" in req.url.path:
            return httpx.Response(200, text=SCREENER_HTML)
        return httpx.Response(404, text="<html>Not found</html>")
    return httpx.MockTransport(handler)


def fake_news() -> httpx.MockTransport:
    return httpx.MockTransport(lambda req: httpx.Response(200, text=RSS))


def fake_wiki() -> httpx.MockTransport:
    def handler(req: httpx.Request):
        if req.url.path == "/w/api.php":
            return httpx.Response(200, json={"query": {"search": [{"title": "Reliance Industries"}]}})
        if "/page/summary/" in req.url.path:
            return httpx.Response(200, json={"title": "Reliance Industries", "description": "Indian multinational conglomerate",
                                             "extract": "Reliance Industries Limited is an Indian multinational conglomerate headquartered in Mumbai.",
                                             "type": "standard", "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Reliance_Industries"}}})
        return httpx.Response(404)
    return httpx.MockTransport(handler)
