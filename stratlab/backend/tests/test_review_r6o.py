"""Round 6, the owner's review on the live site (8 Oct 2026): each test is built on the real example the reviewer saw."""
from datetime import date

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)


# ---------- R6O-001: the company read's numbers are the page's own ----------
def _tcs() -> dict:
    """TCS's page on 8 Oct 2026, as the reviewer saw it: the yearly table to FY26, the Sep 2026 quarter filed."""
    years = ["FY19", "FY20", "FY21", "FY22", "FY23", "FY24", "FY25", "FY26"]
    sales = [146463, 156949, 164177, 191754, 225458, 240893, 255324, 267021]
    profit = [31562, 32447, 32562, 38449, 42303, 46099, 48797, 49454]
    return {
        "region": "IN", "symbol": "TCS", "name": "Tata Consultancy Services Ltd", "currency": "INR",
        "quote": {"price": 2076.0, "change_pct": -0.21}, "range52": {"low": 1976.8, "high": 3350.0}, "market_cap": 7.5e12,
        "metrics": [
            {"title": "Valuation", "items": [{"label": "P/E", "value": 14.6}, {"label": "P/B", "value": 7.01},
                                             {"label": "Div yield", "value": 5.35, "note": "₹111 a share in the last 12 months"}]},
            {"title": "Returns and quality", "items": [{"label": "ROCE", "value": 63.0}, {"label": "ROE", "value": 51.8},
                                                       {"label": "Net margin", "value": 18.5}]},
            {"title": "Sales growth", "items": [{"label": "Latest YoY", "value": 4.6}, {"label": "3Y CAGR", "value": 5.8},
                                                {"label": "5Y CAGR", "value": 10.2}]},
            {"title": "Profit growth", "items": [{"label": "Latest YoY", "value": 1.3}, {"label": "3Y CAGR", "value": 5.3},
                                                 {"label": "5Y CAGR", "value": 8.7}]},
            {"title": "Stock price CAGR", "items": [{"label": "1Y", "value": -31.4}]},
        ],
        "trend": {"unit": "₹ Cr", "revenue": [{"y": y, "v": v} for y, v in zip(years, sales)],
                  "profit": [{"y": y, "v": v} for y, v in zip(years, profit)]},
        "quarters": {"cols": ["Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"], "sales": [67087, 70698, 72275, 73188],
                     "profit": [10720, 13784, 13420, 13934]},
        "results_calendar": {"next": {"symbol": "TCS", "date": "2026-10-08"}, "last": None},
        "news": [{"headline": "TCS Q2 results: net profit at Rs 13,934 crore"}],
    }


def _aapl() -> dict:
    years = ["FY20", "FY21", "FY22", "FY23", "FY24", "FY25"]
    rev = [274.51e9, 365.82e9, 394.33e9, 383.29e9, 391.04e9, 416.16e9]
    ni = [57.41e9, 94.68e9, 99.80e9, 97.0e9, 93.74e9, 112.01e9]
    return {
        "region": "US", "symbol": "AAPL", "name": "Apple Inc", "currency": "USD",
        "quote": {"price": 339.37, "change_pct": 0.8}, "range52": {"low": 243.42, "high": 345.34},
        "margins": {"gross": 48.6, "operating": 33.2, "net": 27.6},
        "metrics": [
            {"title": "Valuation", "items": [{"label": "P/E", "value": 38.92}]},
            {"title": "Profitability", "items": [{"label": "Net margin", "value": 27.6}]},
            {"title": "Growth", "items": [{"label": "Revenue YoY", "value": 14.2}, {"label": "Revenue 5Y", "value": 8.7}]},
            {"title": "Per share and returns", "items": [{"label": "EPS TTM", "value": 8.72}, {"label": "1Y return", "value": 30.0}]},
        ],
        "trend": {"unit": "USD", "revenue": [{"y": y, "v": v} for y, v in zip(years, rev)],
                  "profit": [{"y": y, "v": v} for y, v in zip(years, ni)]},
        "earnings": [{"period": "2025-09-30", "actual": 1.85, "estimate": 1.77}, {"period": "2025-12-31", "actual": 2.84, "estimate": 2.73},
                     {"period": "2026-03-31", "actual": 2.01, "estimate": 1.95}, {"period": "2026-06-30", "actual": 1.91, "estimate": 1.85}],
        "next_earnings": {"date": "2026-10-29"},
    }


def _ground(c: dict, read: dict):
    from app.intel import ai as A
    from app.intel.grounding import ground_company
    facts = A.company_facts(c)
    base = {"summary": "", "valuation_note": "", "position": "", "bull": [], "bear": [], "watch": [], "ideas": []}
    return facts, ground_company({**base, **read}, facts, c["region"], date(2026, 10, 8))


def test_the_ai_is_told_the_latest_year_and_that_the_quarter_is_filed(monkeypatch):
    from app.intel import ai as A
    monkeypatch.setattr(A, "ist_date", lambda: date(2026, 10, 8))
    facts = A.company_facts(_tcs())
    assert facts["latest_fiscal_year"].startswith("FY26 is the latest full year reported")
    assert facts["results"]["status"] == "filed" and facts["results"]["latest_quarter"] == "Sep 2026 (Q2 FY2027)"
    assert "already filed" in facts["fiscal_now"]
    # each Key numbers figure under its group: the sales and profit CAGRs are no longer one "3Y CAGR"
    assert facts["metrics"]["Sales growth: 5Y CAGR"] == 10.2 and facts["metrics"]["Profit growth: 5Y CAGR"] == 8.7
    us = A.company_facts(_aapl())["results"]
    assert us["status"] == "upcoming" and us["next_results_date"] == "2026-10-29"


def test_tcs_read_drops_the_wrong_cagrs_yield_and_results_day(monkeypatch):
    from app.intel import ai as A
    monkeypatch.setattr(A, "ist_date", lambda: date(2026, 10, 8))
    _, out = _ground(_tcs(), {
        "summary": ("TCS is India's largest IT services company. Revenue has grown from ₹146,463 cr in FY19 to an estimated "
                    "₹240,893 cr in FY24, a 5-year CAGR of about 8.7%. Net profit rose from ₹31,562 cr in FY19 to ₹46,099 cr in FY24, "
                    "a CAGR of about 8.7%. Sales grew from ₹1,46,463 cr in FY19 to ₹2,67,021 cr in FY26."),
        "valuation_note": "Dividend yield is 3.08% and the P/E is 14.60.",
        "bull": ["Return on equity is 51.8%.", "Dividend yield is 5.3%.", "Profit has compounded at 8.7% a year over five years."],
        "watch": ["Q2 FY2027 results are due today (2026-10-08).", "The next board meeting date isn't announced yet."],
    })
    assert out["summary"] == "TCS is India's largest IT services company. Sales grew from ₹1,46,463 cr in FY19 to ₹2,67,021 cr in FY26."
    assert out["valuation_note"] == ""                               # 3.08% is not the page's 5.3% yield
    assert out["bull"] == ["Return on equity is 51.8%.", "Dividend yield is 5.3%.", "Profit has compounded at 8.7% a year over five years."]
    assert out["watch"] == ["The next board meeting date isn't announced yet."]


def test_a_cagr_is_worked_out_again_from_the_table():
    from app.intel.grounding import PageFacts
    from app.intel import ai as A
    page = PageFacts(A.company_facts(_tcs()), "IN", date(2026, 10, 8))
    assert round(page.cagr("revenue", 2019, 2024), 1) == 10.5 and round(page.cagr("profit", 2019, 2024), 1) == 7.9
    assert page.check("Revenue grew from ₹146,463 cr in FY19 to ₹240,893 cr in FY24 at a CAGR of 10.5%.") is False   # FY24 isn't the latest
    assert page.check("Sales compounded at 10.2% a year over the last five years.") is True
    assert page.check("Sales compounded at 8.7% a year over the last five years.") is False                          # that is profit's


def test_aapl_read_drops_old_year_margins_and_a_past_quarter_told_as_ahead(monkeypatch):
    from app.intel import ai as A
    monkeypatch.setattr(A, "ist_date", lambda: date(2026, 10, 8))
    _, out = _ground(_aapl(), {
        "summary": ("Apple designs iPhones, Macs and services. Net margin declined to 27.6% in FY24 from prior years. "
                    "Revenue grew 14.2% YoY in the latest year, generating over $390 billion in revenue in FY24. "
                    "Revenue rose 6.4% in FY25 to $416.16 billion."),
        "bull": ["Net margin over the last twelve months is 27.6%.", "Revenue YoY is 14.2%."],
        "watch": ["Fiscal quarter ending 2026-12-31 earnings release (actual EPS 2.84 vs estimate 2.73)",
                  "Results on 2026-10-29."],
    })
    assert out["summary"] == "Apple designs iPhones, Macs and services. Revenue rose 6.4% in FY25 to $416.16 billion."
    assert out["bull"] == ["Net margin over the last twelve months is 27.6%.", "Revenue YoY is 14.2%."]
    assert out["watch"] == ["Results on 2026-10-29."]


def test_the_read_quotes_the_pages_one_year_return():
    from app.intel import ai as A
    from app.intel.grounding import PageFacts
    page = PageFacts(A.company_facts(_aapl()), "US", date(2026, 10, 8))
    assert page.check("The share price is up 30.0% over the past year.") is True
    assert page.check("The share price is up 31.4% over the past year.") is False


def test_judgements_on_the_business_are_dropped():
    from app.intel import ai as A
    from app.intel.grounding import PageFacts
    page = PageFacts(A.company_facts(_aapl()), "US", date(2026, 10, 8))
    assert page.check("The most important factor is its strong earnings momentum.") is False
    assert page.check("A forward P/E of 9.45 indicating low valuation.") is False


# ---------- R6O-008: one figure per thing on a page ----------
def test_us_pe_is_the_pages_price_over_its_eps_ttm():
    from app.intel.company import us_pe
    assert us_pe(339.37, 8.72, 37.98) == 38.92
    assert us_pe(339.37, None, 37.98) == 37.98            # an ADR's EPS is per home share: the source's P/E stays


def test_key_facts_quote_the_pages_one_year_return():
    from app.intel.key_facts import build
    c = {"metrics": [{"title": "Per share and returns", "items": [{"label": "1Y return", "value": 59.7}]}]}
    from datetime import timedelta
    start = date(2025, 9, 1)
    bars = [{"t": (start + timedelta(days=i)).isoformat(), "c": 35.0 if i < 200 else 55.74} for i in range(400)]
    rows = {r["id"]: r for r in build(c, None, bars)}
    one = next(i for i in rows["price"]["items"] if i["label"] == "1-year price change")
    assert one["text"] == "+59.7%"


class _FakeYahoo:
    """Eni on 8 Oct 2026: the ADR's history without Sep and Nov 2025, the Milan listing with them."""
    def meta(self, s):
        return {"E": {"name": "Eni S.p.A.", "currency": "USD"}, "ENI.MI": {"name": "Eni S.p.A.", "currency": "EUR"}}[s]

    def search(self, q):
        return [{"symbol": "E", "quoteType": "EQUITY", "longname": "Eni S.p.A."},
                {"symbol": "ENI.MI", "quoteType": "EQUITY", "longname": "Eni S.p.A."}]

    def events(self, s):
        assert s == "ENI.MI"
        return {"dividends": [{"date": d, "amount": a} for d, a in (("2024-11-18", 0.25), ("2025-03-24", 0.25), ("2025-05-19", 0.25),
                ("2025-09-22", 0.26), ("2025-11-24", 0.26), ("2026-03-23", 0.26), ("2026-05-18", 0.27), ("2026-09-21", 0.27))]}

    def chart(self, s, tf, days, ttl=None):
        assert s == "EURUSD=X"
        rates = {"2024-11-18": 1.06, "2025-03-24": 1.08, "2025-05-19": 1.124, "2025-09-22": 1.175, "2025-11-24": 1.152,
                 "2026-03-23": 1.181, "2026-05-18": 1.168, "2026-09-21": 1.163}
        return {"candles": [{"t": d, "c": r} for d, r in rates.items()]}


def test_an_adrs_missing_dividends_come_from_its_home_listing():
    from app import corp_actions as CA
    adr = [CA.row("US", "E", {"kind": "dividend", "sub": "dividend", "label": "Dividend", "text": "x", "amount": a}, date.fromisoformat(d))
           for d, a in (("2024-11-19", 0.543), ("2025-03-25", 0.52), ("2025-05-20", 0.571), ("2026-03-24", 0.614),
                        ("2026-05-19", 0.631), ("2026-09-22", 0.628))]
    got = CA._home_missing("E", adr, _FakeYahoo(), date(2026, 10, 8))
    assert [g["ex_date"] for g in got] == ["2025-09-22", "2025-11-24"]
    assert all(g["converted"] and 0.58 < g["amount"] < 0.63 for g in got)
    assert "converted" in got[0]["text"]


def test_a_us_pages_yield_is_its_listed_payments_over_the_price():
    from app.intel.company import with_dividend_yield
    c = {"region": "US", "quote": {"price": 55.74},
         "metrics": [{"title": "Per share and returns", "items": [{"label": "Div yield", "value": 6.05, "unit": "%"}]}]}
    divs = [{"kind": "dividend", "amount": a, "ex_date": d} for d, a in
            (("2025-11-24", 0.60), ("2026-03-24", 0.614), ("2026-05-19", 0.631), ("2026-09-22", 0.628))]
    item = with_dividend_yield(c, divs, "2026-10-08")["metrics"][0]["items"][0]
    assert item["value"] == round(2.473 / 55.74 * 100, 2) and item["note"].startswith("$2.473 a share in the last 12 months")


# ---------- R6O-016: results already filed are not "coming up" ----------
def test_a_filed_results_day_is_said_as_filed_on_the_money_calendar(monkeypatch):
    from app import corp_actions, holdings, money_calendar, results
    day = date(2026, 10, 8)
    monkeypatch.setattr(money_calendar, "tracked", lambda uid: ({}, [("IN", "TCS"), ("IN", "INFY")]))
    monkeypatch.setattr(results, "between", lambda region, frm, to, syms=None: [
        {"symbol": "TCS", "date": "2026-10-08", "purpose": "Results", "out": {"at": "2026-10-08T17:02", "title": "Financial results"}},
        {"symbol": "INFY", "date": "2026-10-16", "purpose": "Results"}] if region == "IN" else [])
    monkeypatch.setattr(corp_actions, "prefetch", lambda *a, **k: None)
    monkeypatch.setattr(corp_actions, "load", lambda region: {"rows": []})
    monkeypatch.setattr(corp_actions, "between", lambda *a, **k: [])
    monkeypatch.setattr(holdings, "load", lambda uid: {})
    evs = {e["symbol"]: e for e in money_calendar.holdings_events("u", day, date(2026, 10, 31)) if e.get("symbol")}
    assert evs["TCS"]["title"] == "TCS: results filed" and evs["TCS"]["kind"] == "results_out"
    assert evs["INFY"]["title"] == "INFY: results" and evs["INFY"]["kind"] == "results"
