"""Fake Finnhub, Screener.in, Google News and Wikipedia for tests and the local harness."""
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
        if p == "/api/v1/calendar/earnings" and not sym:
            return httpx.Response(200, json={"earningsCalendar": us_calendar()})
        if p in routes:
            return httpx.Response(200, json=routes[p])
        return httpx.Response(404, json={})
    return httpx.MockTransport(handler)


def us_calendar(today=None) -> list[dict]:
    """The whole US results calendar, relative to today: AAPL tomorrow after the close, NVDA next week, and MSFT,
    which reported two days ago (its row carries the reported numbers and, like the real feed, the estimates)."""
    from datetime import date, timedelta
    t = today or date.today()
    return [{"symbol": "AAPL", "date": (t + timedelta(days=1)).isoformat(), "hour": "amc", "quarter": 4, "year": 2026, "epsEstimate": 1.6},
            {"symbol": "NVDA", "date": (t + timedelta(days=8)).isoformat(), "hour": "amc", "quarter": 3, "year": 2026},
            {"symbol": "MSFT", "date": (t - timedelta(days=2)).isoformat(), "hour": "amc", "quarter": 1, "year": 2027,
             "epsActual": 3.21, "epsEstimate": 3.1, "revenueActual": 69_400_000_000, "revenueEstimate": 68e9},
            {"symbol": "bad symbol!", "date": t.isoformat()}, {"symbol": "XYZ", "date": "someday"}]


def fake_screener() -> httpx.MockTransport:
    def handler(req: httpx.Request):
        if "/company/RELIANCE/" in req.url.path:
            return httpx.Response(200, text=SCREENER_HTML)
        if "/company/543210/" in req.url.path:          # a company listed only on BSE: Screener files it by BSE code
            return httpx.Response(200, text=SCREENER_HTML.replace("Reliance Industries Ltd", "Tiny Co Ltd"))
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


BSE_FILINGS = [
    {"NEWSID": "n1", "SCRIP_CD": 543210, "NEWSSUB": "Tiny Co Ltd - 543210 - Announcement under Regulation 30 (LODR)-Investor Presentation",
     "DissemDT": "{d1}T18:05:11.53", "SUBCATNAME": "Investor Presentation", "CATEGORYNAME": "Company Update",
     "HEADLINE": "Investor presentation for the quarter.", "ATTACHMENTNAME": "abc-123.pdf", "PDFFLAG": 0},
    {"NEWSID": "n2", "SCRIP_CD": 543210, "NEWSSUB": "Tiny Co Ltd - 543210 - Transcript of Earnings Call",
     "DissemDT": "{d2}T10:00:00", "SUBCATNAME": "Earnings Call Transcript", "CATEGORYNAME": "Company Update",
     "HEADLINE": "Transcript of the earnings conference call.", "ATTACHMENTNAME": "def-456.pdf", "PDFFLAG": 1},
    {"NEWSID": "n3", "SCRIP_CD": 543210, "NEWSSUB": "Tiny Co Ltd - 543210 - Disclosure of creation of pledge by promoter",
     "DissemDT": "{d3}T12:00:00", "SUBCATNAME": "-", "CATEGORYNAME": "Insider Trading / SAST",
     "HEADLINE": "Disclosure under Regulation 31 of creation of pledge.", "ATTACHMENTNAME": "", "PDFFLAG": 0},
]


def fake_bse():
    """BSE's announcements API: three filings for the BSE-only company, nothing for anyone else."""
    import json
    from datetime import date, timedelta
    days = {"d1": date.today() - timedelta(days=5), "d2": date.today() - timedelta(days=12), "d3": date.today() - timedelta(days=20)}

    def handler(req: httpx.Request):
        if req.url.path.endswith("/AnnSubCategoryGetData/w"):
            scrip = req.url.params.get("strScrip")
            rows = []
            if scrip in ("543210", "500325") and req.url.params.get("pageno") == "1":
                text = json.dumps(BSE_FILINGS)
                for k, v in days.items():
                    text = text.replace("{" + k + "}", v.isoformat())
                rows = json.loads(text)
            return httpx.Response(200, json={"Table": rows, "Table1": [{"ROWCNT": len(rows)}]})
        return httpx.Response(404)
    return httpx.MockTransport(handler)
