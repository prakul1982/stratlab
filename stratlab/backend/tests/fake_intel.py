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
COMPANY_NEWS = {"reliance": ("Reliance shares rise after strong Jio numbers", "Economic Times", "https://economictimes.com"),
                "tata consultancy services": ("TCS shares steady ahead of its quarterly results", "Mint", "https://livemint.com"),
                "infosys": ("Infosys sets a date for its board meeting on results", "Business Standard", "https://business-standard.com")}


def _market_line(region: str) -> tuple[str, str, str]:
    """The day's market headline, in step with the price table: up or down as the index is, at its level."""
    from tests import fake_prices as P
    name, short = ("NIFTY 50", "Nifty") if region == "IN" else ("^GSPC", "S&P 500")
    now, prev = P.last(name), P.prev(name)
    market = "IN" if region == "IN" else "US"
    closed = P.session_clock(None, market) == P.last_close(market)
    verb = ("ends" if closed else "trades") + (" higher" if now >= prev else " lower")
    src = ("Economic Times", "https://economictimes.com") if region == "IN" else ("Reuters", "https://reuters.com")
    return f"{short} {verb} at {now:,.0f}", *src


def rss(query: str, region: str = "IN") -> str:
    """The feed for a search, as the news site would answer it: the named company's own headline first (when the demo
    world has one; a company it has none for gets none), then the day's market headline. Every item is a few hours
    old whenever the tests run."""
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    from html import escape
    q = query.lower()
    items = [v for k, v in COMPANY_NEWS.items() if k in q]
    if not items or "market" in q or "reliance" in q:
        items.append(_market_line(region))
    if "share price" in q and not any(k in q for k in COMPANY_NEWS):
        items = []                           # a company the demo world has no news about: none, never another's
    now = datetime.now(timezone.utc)
    out = []
    for i, (title, source, site) in enumerate(items):
        at = format_datetime(now - timedelta(hours=2 + 3 * i))
        out.append(f"<item><title>{escape(title)} - {escape(source)}</title><link>https://example.com/news/{i + 1}</link>"
                   f"<pubDate>{at}</pubDate><source url=\"{site}\">{escape(source)}</source></item>")
    return '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>' + "".join(out) + "</channel></rss>"


# Apple, the US company the browser tests open: its own name, numbers, news and people (made up, in the source's shape).
# Its price and market value come from the demo world's price table (fake_prices), like its chart's.
AAPL = {
    "profile": {"country": "US", "currency": "USD", "exchange": "NASDAQ NMS - GLOBAL MARKET", "finnhubIndustry": "Technology",
                "ipo": "1980-12-12", "logo": "", "name": "Apple Inc", "ticker": "AAPL", "weburl": "https://www.apple.com/"},
    "metric": {"metric": {"peTTM": 28.1, "forwardPE": 26.4, "psTTM": 6.6, "pb": 41.5, "evEbitdaTTM": 20.3,
                          "grossMarginTTM": 46.2, "operatingMarginTTM": 31.5, "netProfitMarginTTM": 24.3, "roeTTM": 151.3,
                          "roaTTM": 29.6, "revenueGrowthTTMYoy": 6.4, "epsGrowthTTMYoy": 9.1, "revenueGrowth3Y": 1.8,
                          "revenueGrowth5Y": 8.7, "epsGrowth5Y": 15.4, "currentRatioQuarterly": 0.9,
                          "longTermDebt/equityQuarterly": 1.2, "epsTTM": 6.51, "beta": 1.2, "dividendYieldIndicatedAnnual": 0.55,
                          "payoutRatioTTM": 15.2}},
    "fin": {"data": [{"year": y, "report": {"ic": [{"label": "Revenue", "concept": "us-gaap_Revenues", "value": rev},
                                                   {"label": "Net income", "concept": "us-gaap_NetIncomeLoss", "value": ni}]}}
                     for y, rev, ni in ((2025, 416161e6, 112010e6), (2024, 391035e6, 93736e6), (2023, 383285e6, 96995e6),
                                        (2022, 394328e6, 99803e6))]},
    "earn": [{"period": p, "actual": a, "estimate": e, "surprisePercent": x} for p, a, e, x in
             (("2026-06-30", 1.62, 1.55, 4.5), ("2026-03-31", 1.71, 1.66, 3.0), ("2025-12-31", 2.52, 2.41, 4.6), ("2025-09-30", 1.85, 1.77, 4.5))],
    "peers": ["AAPL", "MSFT", "GOOGL", "DELL", "HPQ"],
    "rec": [{"period": "2026-09-01", "strongBuy": 14, "buy": 22, "hold": 12, "sell": 2, "strongSell": 0}],
    "insider": {"data": [{"name": "Cook Timothy D", "change": -108136, "filingDate": "2026-09-04"},
                         {"name": "O'Brien Deirdre", "change": -34821, "filingDate": "2026-08-12"}]},
    "news": [("Apple's new iPhones go on sale across its stores", "Reuters", 5), ("Apple shares edge up ahead of its quarterly results", "CNBC", 30)],
}
NVDA_NEWS = [("Nvidia unveils new data centre chips", "Reuters", 4), ("Chip stocks rally on AI demand", "CNBC", 7)]


def _news(rows) -> list[dict]:
    """Headlines a few hours old whenever the tests run."""
    import time
    now = int(time.time())
    return [{"headline": h, "url": f"https://example.com/{i + 1}", "source": src, "datetime": now - hours * 3600}
            for i, (h, src, hours) in enumerate(rows)]


def _quote(sym: str) -> dict:
    """The price table's numbers for a US company, in the source's shape: the last trade (the close, out of hours)."""
    from tests import fake_prices as P
    c, pc = P.last(sym), P.prev(sym)
    clock = P.session_clock(None, "US")
    return {"c": c, "d": round(c - pc, 2), "dp": round((c / pc - 1) * 100, 2), "h": round(max(c, pc) * 1.004, 2),
            "l": round(min(c, pc) * 0.996, 2), "o": pc, "pc": pc, "t": int(clock.timestamp())}


def _range52(sym: str) -> tuple[float, float]:
    """The lowest and highest daily close of the last year, from the price table (as the chart draws them)."""
    from datetime import timedelta
    from tests import fake_prices as P
    end = P.session_clock(None, "US")
    closes = [P.price(sym, end - timedelta(days=d)) for d in range(0, 366)]
    return round(min(closes), 2), round(max(closes), 2)


def _company(sym: str) -> dict | None:
    """One US company's answers: NVIDIA's fixed ones (the unit tests read them), Apple's own, and for the other
    companies the price table knows, their name and price only."""
    from tests import fake_prices as P
    if sym == "NVDA":
        return {"profile": PROFILE, "quote": QUOTE, "metric": METRIC, "news": _news(NVDA_NEWS), "peers": ["NVDA", "AMD", "AVGO", "INTC"],
                "rec": [{"period": "2025-09-01", "strongBuy": 24, "buy": 38, "hold": 7, "sell": 1, "strongSell": 0}],
                "earn": EARN, "fin": FIN,
                "insider": {"data": [{"name": "Huang Jen-Hsun", "change": -120000, "filingDate": "2026-09-10"},
                                     {"name": "Kress Colette", "change": -30000, "filingDate": "2026-09-02"}]},
                "cal": [{"date": "2099-11-19", "epsEstimate": 1.2, "symbol": "NVDA"}]}
    if sym == "AAPL":
        low, high = _range52(sym)
        q = _quote(sym)
        prof = dict(AAPL["profile"], marketCapitalization=round(P.market_cap(sym) / 1e6, 1))
        metric = {"metric": dict(AAPL["metric"]["metric"], **{"52WeekHigh": high, "52WeekLow": low,
                                                               "52WeekPriceReturnDaily": round((q["c"] / P.price(sym, P.session_clock(None, "US").timestamp() - 365 * 86400) - 1) * 100, 1)})}
        cal = [r for r in us_calendar() if r["symbol"] == "AAPL"]
        return {"profile": prof, "quote": q, "metric": metric, "news": _news(AAPL["news"]), "peers": AAPL["peers"], "rec": AAPL["rec"],
                "earn": AAPL["earn"], "fin": AAPL["fin"], "insider": AAPL["insider"], "cal": cal}
    name = P.name_of(sym) if P.market_of(sym) == "US" else None
    if not name:
        return None
    prof = {"country": "US", "currency": "USD", "exchange": "NEW YORK STOCK EXCHANGE, INC.", "finnhubIndustry": P.sector_of(sym) or "",
            "name": name, "ticker": sym, "marketCapitalization": round((P.market_cap(sym) or 0) / 1e6, 1)}
    return {"profile": prof, "quote": _quote(sym), "metric": {"metric": {}}, "news": [], "peers": [], "rec": [], "earn": [],
            "fin": {"data": []}, "insider": {"data": []}, "cal": []}


def fake_finnhub(reject: bool = False) -> httpx.MockTransport:
    def handler(req: httpx.Request):
        if reject:
            return httpx.Response(401, json={"error": "Invalid API key"})
        p, sym = req.url.path, req.url.params.get("symbol", "").upper()
        if p == "/api/v1/calendar/earnings" and not sym:
            return httpx.Response(200, json={"earningsCalendar": us_calendar()})
        if p == "/api/v1/search":
            return httpx.Response(200, json={"result": [{"symbol": "NVDA", "description": "NVIDIA CORP", "type": "Common Stock"},
                                                        {"symbol": "NVDA.SW", "description": "NVIDIA CORP", "type": "Common Stock"}]})
        if p == "/api/v1/news":
            return httpx.Response(200, json=_news(NVDA_NEWS))
        co = _company(sym) if sym != "NOPE" else None
        if co is None:              # a ticker the source doesn't know: an empty profile, like the real one
            return httpx.Response(200, json={} if p.endswith(("/profile2", "/quote", "/metric")) else [])
        routes = {"/api/v1/stock/profile2": co["profile"], "/api/v1/quote": co["quote"], "/api/v1/stock/metric": co["metric"],
                  "/api/v1/company-news": co["news"], "/api/v1/stock/peers": co["peers"], "/api/v1/stock/recommendation": co["rec"],
                  "/api/v1/stock/earnings": co["earn"], "/api/v1/stock/financials-reported": co["fin"],
                  "/api/v1/stock/insider-transactions": co["insider"], "/api/v1/calendar/earnings": {"earningsCalendar": co["cal"]}}
        if p in routes:
            return httpx.Response(200, json=routes[p])
        return httpx.Response(404, json={})
    return httpx.MockTransport(handler)


def us_calendar(today=None) -> list[dict]:
    """The whole US results calendar, relative to today: AAPL tomorrow after the close, NVDA next week, and MSFT,
    which reported two days ago (its row carries the reported numbers and, like the real feed, the estimates)."""
    from datetime import date, timedelta
    from tests.fake_prices import on_trading_day
    t = today or date.today()
    # the demo world (no date given) has companies report on trading days; a test that names its date gets exactly that date
    day = lambda n: (on_trading_day(t + timedelta(days=n), "US", n < 0) if today is None else t + timedelta(days=n)).isoformat()
    return [{"symbol": "AAPL", "date": day(1), "hour": "amc", "quarter": 4, "year": 2026, "epsEstimate": 1.6},
            {"symbol": "NVDA", "date": day(8), "hour": "amc", "quarter": 3, "year": 2026},
            {"symbol": "MSFT", "date": day(-2), "hour": "amc", "quarter": 1, "year": 2027,
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
    return httpx.MockTransport(lambda req: httpx.Response(200, text=rss(req.url.params.get("q", ""), req.url.params.get("gl", "IN"))))


WIKI_PAGES = {
    "reliance industries": ("Reliance Industries", "Indian multinational conglomerate",
                            "Reliance Industries Limited is an Indian multinational conglomerate headquartered in Mumbai."),
    "tata consultancy services": ("Tata Consultancy Services", "Indian information technology company",
                                  "Tata Consultancy Services Limited is an Indian multinational information technology services and consulting company headquartered in Mumbai."),
    "infosys": ("Infosys", "Indian information technology company",
                "Infosys Limited is an Indian multinational information technology company headquartered in Bengaluru."),
    "apple": ("Apple Inc.", "American technology company",
              "Apple Inc. is an American multinational technology company headquartered in Cupertino, California."),
}


def fake_wiki() -> httpx.MockTransport:
    """Wikipedia by name, like the real one: each company gets its own page (a made-up one-liner when it has none here),
    so a company's heading and its description are always about the same company."""
    from urllib.parse import unquote

    def page(name: str):
        key = name.lower().replace("_", " ").replace(" company", "").strip()
        for k, v in WIKI_PAGES.items():
            if key.startswith(k):
                return v
        title = name.replace("_", " ").replace(" company", "").strip()        # the name as given ("HDFC Bank", not "Hdfc Bank")
        return (title, "Listed company", f"{title} is a listed company.")

    def handler(req: httpx.Request):
        if req.url.path == "/w/api.php":
            return httpx.Response(200, json={"query": {"search": [{"title": page(req.url.params.get("srsearch", "Reliance Industries"))[0]}]}})
        if "/page/summary/" in req.url.path:
            title, desc, extract = page(unquote(req.url.path.rsplit("/", 1)[1]))
            return httpx.Response(200, json={"title": title, "description": desc, "extract": extract, "type": "standard",
                                             "content_urls": {"desktop": {"page": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"}}})
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
    from datetime import date, datetime, timedelta
    days = {"d1": date.today() - timedelta(days=5), "d2": date.today() - timedelta(days=12), "d3": date.today() - timedelta(days=20)}

    def handler(req: httpx.Request):
        if req.url.path.endswith("/AnnSubCategoryGetData/w"):
            scrip = req.url.params.get("strScrip")
            frm, to = (datetime.strptime(req.url.params.get(k), "%Y%m%d").date() for k in ("strPrevDate", "strToDate"))
            if (to - frm).days > 365:                          # what BSE answers to a range over a year (seen live)
                return httpx.Response(200, json={"Status": False, "Message": "Date range cannot exceed 12 months."})
            rows = []
            if scrip in ("543210", "500325") and req.url.params.get("pageno") == "1":
                text = json.dumps(BSE_FILINGS)
                for k, v in days.items():
                    text = text.replace("{" + k + "}", v.isoformat())
                rows = [r for r in json.loads(text) if frm.isoformat() <= r["DissemDT"][:10] <= to.isoformat()]
            return httpx.Response(200, json={"Table": rows, "Table1": [{"ROWCNT": len(rows)}]})
        if req.url.path.endswith("/DefaultData/w"):           # corporate actions: an interim dividend for the BSE-only company
            from tests.fake_prices import on_trading_day
            ex = on_trading_day(date.today() + timedelta(days=7)).strftime("%d %b %Y")
            rows = [{"scrip_code": "543210", "short_name": "TINYCO", "long_name": "Tiny Co Ltd", "Ex_date": ex, "RD_Date": ex,
                     "Purpose": "Interim Dividend - Rs. - 0.5000"}] if req.url.params.get("scripcode") == "543210" else []
            return httpx.Response(200, json={"Table": rows})
        return httpx.Response(404)
    return httpx.MockTransport(handler)
