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


# ---------- R6O-002: red flags follow what the filing is about ----------
import pytest  # noqa: E402


@pytest.mark.parametrize("desc,text,cat,sev", [
    # MOL Meghmani: an amalgamation the NCLT sanctions is a merger, not insolvency
    ("Amalgamation/Merger", "MOL Meghmani Organics Limited has informed the Exchange that the Hon'ble NCLT, Ahmedabad Bench has "
     "sanctioned the Scheme of Amalgamation of the wholly owned subsidiary with the Company", "deal", "info"),
    # POLYCAB: a filing under the insolvency subject that doesn't show the company as the debtor
    ("Corporate Insolvency Resolution Process", "Polycab India Limited has informed the Exchange regarding Corporate Insolvency Resolution Process",
     "insolvency_other", "info"),
    ("Corporate Insolvency Resolution Process", "The Company, as an operational creditor, filed an application against XYZ Limited under Section 9 of the IBC",
     "insolvency_other", "info"),
    # ICICIBANK: the depositories certificate is routine whatever it names
    ("Certificate under SEBI (Depositories and Participants) Regulations, 2018",
     "ICICI Bank Limited has informed the Exchange about Certificate under Regulation 74(5) for the quarter, covering its bonds", "other", "info"),
    # RAYMONDREL: a generic update reporting on money already raised
    ("General Updates", "Raymond Realty Limited has informed the Exchange regarding the monitoring agency report for the preferential issue",
     "other", "info"),
    # TITAN: a generic update that names commercial paper without raising any
    ("Updates", "Titan Company Limited has informed the Exchange regarding listing of commercial papers on the exchange", "other", "info"),
    # still flagged: the company's own insolvency, and a generic update reporting a decision to raise money
    ("Corporate Insolvency Resolution Process", "The NCLT has admitted the application filed by a financial creditor and initiated the corporate "
     "insolvency resolution process against the Company; an interim resolution professional has been appointed", "insolvency", "red"),
    ("Insolvency and Bankruptcy", "The NCLT has admitted the application under Section 7 of the IBC and initiated the corporate insolvency resolution process against the Company",
     "insolvency", "red"),
    ("General Updates", "The Board approved the issue of equity shares on a preferential basis to the promoters", "preferential", "red"),
])
def test_red_flags_on_the_filings_the_owner_saw(desc, text, cat, sev):
    from app.intel import filings as F
    assert F.classify(desc, text) == (cat, sev)


def test_stored_flags_are_read_again_with_the_new_rules():
    from app.intel import filings as F
    assert F.RULES_VERSION >= 3


# ---------- R6O-003: a job's run is kept, and a fresh feed is never "Not run yet" ----------
def test_a_jobs_run_is_stored_when_it_is_written(monkeypatch):
    from app import db, job_status
    saved = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: saved.get(k))
    st = job_status.Status("etf-r6o", {"read": None, "last_error": None})
    st["last_error"] = None
    assert "jobstatus:etf-r6o" not in saved                     # nothing has run yet
    st.update(read="2026-10-08T15:46")
    assert "2026-10-08T15:46" in saved["jobstatus:etf-r6o"]
    # after a restart the job's memory is empty: the stored run shows, marked as from before the restart
    got = job_status.kept("etf-r6o", {"read": None})
    assert got["read"] == "2026-10-08T15:46" and got["before_restart"]


def test_the_feeds_that_said_not_run_yet_keep_their_runs():
    from app import job_status, main
    from app import market_events_routes, fo_changes_routes
    for job, key in ((main.etf_job, "etf"), (main.vix_job, "vix"), (main.positioning_job, "positioning"), (main.surv_job, "surveillance"),
                     (market_events_routes.job, "events"), (fo_changes_routes.job, "fo"), (main.closing_auction_job, "closing-auction"),
                     (main.recorder, "option-chains")):
        assert isinstance(job.status, job_status.Status) and job.status.key == key


def test_a_feed_without_a_run_on_this_server_shows_its_datas_own_time():
    from app.admin_jobs import _ran
    at, why = _ran({"last_run": None}, "last_run", data=lambda: "2026-10-08T18:45")
    assert at == "2026-10-08T18:45" and "stored data" in why[0]
    assert _ran({"last_run": "2026-10-08T19:00"}, "last_run", data=lambda: "x") == ("2026-10-08T19:00", [])
    assert _ran({}, "last_run", data=lambda: (_ for _ in ()).throw(ValueError("down"))) == (None, [])


# ---------- R6O-004: the brief's counts and headlines ----------
def test_a_briefs_headlines_are_the_markets_from_its_day_once_and_whole():
    from app.newsletter.content import pick_headlines
    us = [{"headline": "Former German spy chief arrested on suspicion of spying for Russia", "at": "2026-10-07T14:00:00+00:00"},
          {"headline": "Ohio voters line up before dawn for early voting", "at": "2026-10-07T12:00:00+00:00"},
          {"headline": "Gen Alpha kids are earning money in new ways", "at": "2026-10-07T12:00:00+00:00"},
          {"headline": "Private capital is reshaping Hollywood moviemaking", "at": "2026-10-07T12:00:00+00:00"},
          {"headline": "Stocks slip as Treasury yields climb; Nasdaq falls 0.2%", "at": "2026-10-07T20:10:00+00:00"}]
    assert [h["headline"] for h in pick_headlines("US", us, "2026-10-07", "2026-10-07")] == ["Stocks slip as Treasury yields climb; Nasdaq falls 0.2%"]
    india = [{"headline": "Why is the stock market down today? 3 factors behind Sensex, Nifty 50 fall", "at": "2026-10-08T05:00:00+00:00"},
             {"headline": "Why is the stock market down today? 3 factors behind Sensex, Nifty 50 fall", "at": "2026-10-08T06:00:00+00:00"},
             {"headline": "Sensex drops 571 points, investors lose Rs 5 lakh cr", "at": "2026-10-01T10:00:00+00:00"},
             {"headline": "Five reasons India's stock market is sinking even when its economy is growing", "at": "2026-10-08T04:00:00+00:00"},
             {"headline": "Why is market crashing today? Sensex slumps 1,100 points, Nifty below 22,250. 7 key factors behind Rs 10 l",
              "at": "2026-10-08T09:00:00+00:00"}]
    got = [h["headline"] for h in pick_headlines("IN", india, "2026-10-08", "2026-10-08",
                                                 seen={"five reasons india s stock market is sinking even when its economy is growing"})]
    assert got == ["Why is the stock market down today? 3 factors behind Sensex, Nifty 50 fall",
                   "Why is market crashing today? Sensex slumps 1,100 points, Nifty below 22,250. 7 key factors behind Rs 10…"]


def test_the_summary_counts_the_sectors_the_section_lists():
    from app.newsletter.write import fix_counts
    rot = [{"title": "Sector rotation", "items": [{"text": "Nifty Media moved"}, {"text": "Nifty PSU Bank moved"}]}]
    s = "NIFTY 50 −0.76%; SENSEX −0.59% today. 6 sectors moved to another quadrant on the rotation chart."
    assert fix_counts(s, rot) == "NIFTY 50 −0.76%; SENSEX −0.59% today. 2 sectors moved to another quadrant on the rotation chart."
    us = "S&P 500 −0.22% today. 5 sectors moved to another quadrant on the rotation chart."
    assert fix_counts(us, [{"title": "Indices", "items": []}]) == "S&P 500 −0.22% today."
    assert fix_counts("Two sectors moved to another quadrant.", rot) == "Two sectors moved to another quadrant."


def test_stored_briefs_are_tidied_once(monkeypatch):
    import json as _j
    from app import db
    from app.newsletter import job as J
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(J.write, "render", lambda issue: ("<p>", "text"))
    today = date.today().isoformat()
    from datetime import timedelta
    yday = (date.today() - timedelta(days=1)).isoformat()
    heads = lambda *t: {"title": "Headlines", "items": [{"text": x, "url": None, "lines": []} for x in t]}    # noqa: E731
    a = {"id": f"market.IN.{yday}", "kind": "market", "region": "IN", "day": yday, "weekly": False,
         "summary": "NIFTY 50 +0.98% today. 5 sectors moved to another quadrant on the rotation chart.",
         "sections": [{"title": "Sector rotation", "items": [{"text": "x"}] * 4}, heads("Five reasons India's stock market is sinking")]}
    b = {"id": f"market.IN.{today}", "kind": "market", "region": "IN", "day": today, "weekly": False,
         "summary": "NIFTY 50 −1.64% today. 6 sectors moved to another quadrant on the rotation chart.",
         "sections": [{"title": "Sector rotation", "items": [{"text": "y"}] * 2},
                      heads("Five reasons India's stock market is sinking", "Sensex falls 1,100 points", "Sensex falls 1,100 points",
                            "Gen Alpha kids are earning money")]}
    for i in (a, b):
        J.save(i)
    assert J.repair_headlines("IN") == 2
    got = _j.loads(store[f"news:market:IN:{today}"])
    assert got["summary"].endswith("2 sectors moved to another quadrant on the rotation chart.")
    assert [i["text"] for i in got["sections"][1]["items"]] == ["Sensex falls 1,100 points"]
    assert _j.loads(store[f"news:market:IN:{yday}"])["summary"].endswith("4 sectors moved to another quadrant on the rotation chart.")
    assert J.repair_headlines("IN") == 0                        # once: nothing left to change


# ---------- R6O-005: the assistant page says the plan it is seen on ----------
def test_the_assistant_page_names_the_viewed_plan(monkeypatch):
    from app import mcp_keys, mcp_server
    monkeypatch.setattr(mcp_keys, "keys", lambda uid: [])
    monkeypatch.setattr(mcp_keys, "entries", lambda uid: [])
    got = mcp_server.page({"id": "owner", "_plan": "free", "_view_as": "free"})
    assert got["allowed"] is False and got["plan"] == "Pro" and got["your_plan"] == "Free"
    assert mcp_server.page({"id": "owner", "_plan": "basic"})["your_plan"] == "Basic"
