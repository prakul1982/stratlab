"""LIVE9B (16 Nov 2026 live review, reviewer B): the backend side of lane fix9b."""
from datetime import date

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app.intel import ai as A
from app.intel import grounding as G
from tests.test_review_r6o import _aapl, _tcs


def test_live9b_002_a_stored_read_drops_a_ratio_the_page_no_longer_shows_even_with_its_own_rows():
    # the read of 12 Nov carried its own fact rows with the same old ratios: they no longer back its sentences
    read = {"summary": "TCS is an IT services company.", "valuation_note": "P/E is 17.1 and P/B is 7.42.", "position": "",
            "bull": [], "bear": [], "watch": [], "ideas": [],
            "facts": [{"label": "Valuation", "items": [{"label": "P/E", "text": "17.1"}, {"label": "P/B", "text": "7.42"}]}]}
    c = _tcs()                                    # the page: P/E 14.6, P/B 7.01
    got = A.regrounded(read, c, date(2026, 11, 17))
    assert got["valuation_note"] == ""
    assert got["summary"] == read["summary"]
    # the page's own figures stand, to the sentence's rounding
    ok = {**read, "valuation_note": "P/E is 14.6 and P/B is 7.0."}
    assert A.regrounded(ok, c, date(2026, 11, 17))["valuation_note"] == "P/E is 14.6 and P/B is 7.0."
    # a forward P/E is not the page's trailing one, and a percentage near a P/E is not a P/E
    pf = G.PageFacts(A.company_facts(c), "IN", date(2026, 11, 17))
    assert pf._ratios_ok("The P/E has risen 20% this year.")


def test_live9b_002_beats_and_an_eps_pair_are_the_pages():
    c = _aapl()            # four quarters on the page, every one above its estimate
    facts = A.company_facts(c)
    pf = G.PageFacts(facts, "US", date(2026, 11, 17))
    assert not pf.check("Apple beat the estimate in three of the last four quarters.")
    assert pf.check("Apple beat the estimate in four of the last four quarters.")
    assert not pf.check("EPS was $2.05 against an estimate of $2.03.")
    assert pf.check("EPS was $1.91 against $1.85 expected.")


def test_live9b_002_a_lenders_revenue_was_not_were():
    assert G.lender_top_line("Sales in the Sep 2026 quarter were ₹95,132 Cr.") == "Revenue in the Sep 2026 quarter was ₹95,132 Cr."
    assert G.lender_top_line("Sales were ₹10 Cr.") == "Revenue was ₹10 Cr."


def test_live9b_003_whole_number_percentages_give_way_to_worked_decimals():
    from app import company_tables as T
    from tests.test_company_tables import page
    p = page()
    p["pl"]["rows"]["OPM %"] = [20, 20, 21, 20, 20, 20, 20]                     # the source's whole numbers (true 20.0, 20.0, 20.8, 20.0, …)
    p["ratios_table"] = {"cols": ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"],
                         "rows": {"Sales Growth %": [None, 10, 9, 8, 15, 20], "ROCE %": [30, 31, 32, 33, 34, 35]}}
    v = T.statements_view(p, "IN", "OWNCO", {"full": True, "export": False}, ["consolidated"])
    sec = {s["key"]: {r["label"]: r for r in s["rows"]} for s in v["sections"]}
    assert sec["pl"]["OPM %"]["values"][2] == 20.8 and sec["pl"]["OPM %"]["worked"]
    ratios = sec["ratios_table"]
    assert "Sales Growth %" not in ratios                                           # the whole-number row gave way
    assert ratios["Sales growth %"]["values"][2] == 9.1 and ratios["Sales growth %"]["worked"]   # 120/110 = +9.09%
    assert ratios["ROCE %"]["values"] == [30, 31, 32, 33, 34, 35]                   # nothing to work it out from: kept as given


def test_live9b_004_a_to_date_row_gives_its_third_number_as_the_year_ago_month():
    from app import biz_updates as B

    def read(at, period, value, prior, quote):
        return {"at": at, "title": "Monthly Business Update", "url": f"https://nsearchives.nseindia.com/corporate/{at}.pdf", "period": period,
                "span": "month", "reader": 3, "figures": [{"metric": "Power weeder", "segment": None, "value": value, "unit": "units", "basis": "month",
                                                           "prior": prior, "headline": True, "quote": quote, "page": 1, "own": True}]}
    reads = {"jun": read("2026-07-01T10:00", "2026-06", 1001, 3680, "Power Weeder 1001 3680 720 2349"),
             "sep": read("2026-10-01T10:50", "2026-09", 1004, None, "Power weeder 1004 6076 1001 4970")}
    row = B.series(reads)[0]
    assert row["year_ago"]["period"] == "2025-09" and row["year_ago"]["value"] == 1001 and row["change_year"] == 0.3
    assert {p["period"]: p["value"] for p in row["points"]}["2025-06"] == 720
    # a row of another shape keeps what the reader kept
    assert B.to_date_prior({"value": 5954, "prior": 5100, "quote": "Total 5954 5100"}) == 5100
    assert B.to_date_prior({"value": 3519, "prior": 4664, "quote": "Total 3519 4600 4664 4700"}) == 4664


def test_live9b_005_holdings_take_the_screens_sector_list(monkeypatch):
    from app import holdings, main as M, screens
    monkeypatch.setattr(screens, "load_index", lambda region: {"rows": [{"symbol": "APARINDS", "sector": "Industrials"},
                                                                        {"symbol": "APOLLOHOSP", "sector": "Healthcare"}]})
    items = [{"symbol": "APARINDS", "exchange": "NSE", "qty": 1, "sector": "Not classified"},
             {"symbol": "APOLLOHOSP", "exchange": "NSE", "qty": 1, "sector": "Healthcare"},
             {"symbol": "LTINFRA", "exchange": "NSE", "qty": 1, "sector": "Infrastructure"},           # not in the index: kept
             {"symbol": "AAPL", "exchange": "US", "qty": 1, "sector": "Information Technology"}]
    got = {i["symbol"]: i["sector"] for i in M._screen_sectors(items)}
    assert got == {"APARINDS": "Industrials", "APOLLOHOSP": "Healthcare", "LTINFRA": "Infrastructure", "AAPL": "Information Technology"}
    v = holdings.view(M._screen_sectors(items), {})
    assert "Not classified" not in [a["sector"] for a in v["allocation"]]


def test_live9b_006_an_index_notice_takes_effect_on_the_day_its_title_names(monkeypatch):
    from datetime import date as _d
    from app import market_events as ME
    title = "Exclusion of Ennature Bio Pharma Ltd. w.e.f. November 17, 2026"
    text = "Index Maintenance Sub-Committee ... earlier changes effective from September 2, 2026 ... " + title
    assert ME._effective(text, title) == _d(2026, 11, 17)
    # a change stored with the text's earlier day shows its title's
    stored = {"id": "a1", "url": "https://x/a.pdf", "title": title, "announced": "2026-11-13", "effective": "2026-09-02", "sections": []}
    monkeypatch.setattr(ME, "load_state", lambda: {"index": {"changes": [stored]}})
    assert ME.index_changes()[0]["effective"] == "2026-11-17"


def test_live9b_007_a_one_off_investment_is_no_business_figure_and_my_stocks_are_named(monkeypatch):
    from app import biz_updates as B, screens
    read = {"at": "2026-11-05T10:00", "title": "Disclosure", "url": "https://nsearchives.nseindia.com/corporate/a.pdf", "period": "2026-10",
            "span": "month", "reader": B.READER,
            "figures": [{"metric": "Total investment in Clean Max Rudra Private Limited", "segment": None, "value": 11.38, "unit": "₹ crore",
                         "basis": "month", "prior": None, "headline": True, "quote": "₹11.38 crore", "page": 1, "own": True}]}
    assert B.series({"a": read}) == []
    monkeypatch.setattr(B, "my_symbols", lambda uid: [("BHARATCOAL", "holding")])
    monkeypatch.setattr(B, "prime", lambda syms: None)
    monkeypatch.setattr(B, "stored", lambda sym: {})
    monkeypatch.setattr(B, "_headline_row", lambda sym, name, reads: {"symbol": sym, "name": name, "value": None, "status": "unchecked"})
    monkeypatch.setattr(screens, "load_index", lambda region: {"rows": [{"symbol": "BHARATCOAL", "name": "Bharat Coking Coal"}]})
    v = B.my_view("u1")
    assert v["without"][0]["name"] == "Bharat Coking Coal"
