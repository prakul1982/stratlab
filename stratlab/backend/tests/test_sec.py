"""US company numbers from the SEC's XBRL filings, in the same shape as the Indian company pages."""
import json
import pytest

from app import deepdive
from app.intel import sec
from app.intel.net import SourceError
from tests import fake_sec


@pytest.fixture
def p():
    return sec.SEC(transport=fake_sec.transport()).company("AAPL")


def test_years_are_labelled_by_the_month_they_end(p):
    assert p["pl"]["cols"][:7] == ["Sep 2019", "Sep 2020", "Sep 2021", "Sep 2022", "Sep 2023", "Sep 2024", "Sep 2025"]
    assert p["pl"]["cols"][-1] == "TTM" and p["unit"] == "$ million" and p["region"] == "US"


def test_revenue_follows_the_concept_change_and_takes_restatements(p):
    sales = p["pl"]["rows"]["Sales"]
    assert sales[0] == 260174                     # 2019 from the older concept
    assert sales[4] == 383300                     # 2023 as restated in the next year's report
    assert sales[6] == 416161


def test_ttm_is_the_last_four_quarters_with_the_fourth_derived_from_the_year(p):
    q = p["quarters"]
    assert q["cols"][-2:] == ["Dec 2025", "Mar 2026"]
    # the quarter ending with the year is the year less its three quarters (26% of it here)
    fy_q4 = q["rows"]["Sales"][q["cols"].index("Sep 2025")]
    assert fy_q4 == pytest.approx(416161 * 0.26, abs=5)
    ttm = p["pl"]["rows"]["Sales"][-1]
    assert ttm == pytest.approx(416161 * 0.22 + fy_q4 + 124300 + 95400, abs=5)
    assert len(q["cols"]) == 12 and "Mar 2025" in q["cols"]             # year-to-date figures aren't quarters


def test_balance_sheet_debt_adds_its_parts_and_cash_is_reported(p):
    b = p["balance"]["rows"]
    assert b["Borrowings"][-1] == 78328 + 12350 + 8000
    assert b["Cash"][-1] == 35934 and b["Fixed Assets"][-1] == 49834


def test_capex_is_reported_not_estimated(p):
    n = deepdive.numbers(p)
    last = n["years"][-1]
    assert last["capex"] == 12715 and last["fcf"] == round(111482 - 12715, 1)
    assert n["unit"] == "$ million" and n["growth"]["sales_cagr_5y"] is not None


def test_industry_and_documents(p):
    assert p["industry_path"] == ["Manufacturing", "Electronic Computers"] and not p["bank"]
    kinds = [(d["kind"], d["at"]) for d in p["documents"]]
    assert ("earnings_release", "2026-05-01") in kinds and ("annual_report", "2025-10-31") in kinds
    assert all(k != "4" for k, _ in kinds)                              # insider forms aren't documents
    assert [d["at"] for d in p["documents"]] == sorted((d["at"] for d in p["documents"]), reverse=True)
    er = next(d for d in p["documents"] if d["kind"] == "earnings_release")
    assert er["url"].startswith("https://www.sec.gov/Archives/edgar/data/320193/000032019326000011/")
    assert p["shares"] == 14_800_000_000


def test_unknown_ticker_says_why():
    with pytest.raises(SourceError, match="files with the SEC"):
        sec.SEC(transport=fake_sec.transport()).company("ZZZZ")


def test_company_is_built_once_and_cached():
    calls = []
    s = sec.SEC(transport=fake_sec.transport(calls))
    s.company("AAPL")
    s.company("aapl")
    assert sum("companyfacts" in c for c in calls) == 1


def test_quarters_come_from_year_to_date_figures():
    # cash-flow numbers: Q1 alone, then only six and nine months and the year, all from the same start
    rows = [{"start": "2025-01-01", "end": e, "val": v, "form": f, "filed": "2026-02-01"}
            for e, v, f in (("2025-03-31", 10, "10-Q"), ("2025-06-30", 25, "10-Q"), ("2025-09-30", 45, "10-Q"), ("2025-12-31", 70, "10-K"))]
    facts = {"us-gaap": {"DepreciationDepletionAndAmortization": {"units": {"USD": rows}}}}
    assert sec.quarterly(facts, sec.DEPRECIATION) == {"2025-03-31": 10, "2025-06-30": 15, "2025-09-30": 20, "2025-12-31": 25}


def test_operating_profit_is_before_depreciation_like_the_indian_pages(p):
    r = p["pl"]["rows"]
    assert r["Operating Profit"][-2] == 133050 + 11700                  # the last full year: EBIT plus D&A
    assert r["OPM %"][-2] == round((133050 + 11700) / 416161 * 100, 1)


def test_us_deep_dive_through_the_api(monkeypatch):
    from app import deepdive, main, report_card
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(deepdive, "stored", lambda s: None)
        monkeypatch.setattr(report_card, "stored", lambda s: None)
        c, h = w["client"], W.headers("pro-token")
        r = c.get("/research/deep/AAPL?region=US", headers=h)
        assert r.status_code == 200, r.text
        v = r.json()
        assert v["region"] == "US" and v["currency"] == "USD" and v["numbers"]["unit"] == "$ million"
        assert v["numbers"]["capex_reported"] and v["numbers"]["years"][-1]["capex"] == 12715
        assert v["snapshot"]["market_cap_cr"] and v["snapshot"]["pe"]                 # from the price and the share count
        assert v["checklist"]["industry"]["path"] == ["Manufacturing", "Electronic Computers"]
        assert v["ai"] and v["report_card"] and any(d["kind"] == "annual_report" for d in v["documents"])
        fcf = next(x for x in v["checklist"]["checks"] if x["label"] == "Free cash flow, 3 years")
        assert fcf["value"].startswith("$") and fcf["value"].endswith(" bn")             # a large company: billions
        deck = c.get("/research/deep/AAPL/deck?region=US", headers=h)
        assert deck.status_code == 200 and deck.content[:2] == b"PK"
        assert c.get("/research/deep/AAPL?region=JP", headers=h).status_code == 400
        missing = c.get("/research/deep/ZZZZ?region=US", headers=h)
        assert missing.status_code in (404, 502, 503) and "SEC" in missing.text
        w["faults"]["sec"].mode = "500"
        main.sec_feed._built.clear()
        down = c.get("/research/deep/AAPL?region=US", headers=h)
        assert down.status_code in (502, 503) and down.status_code != 500
    finally:
        w["close"]()


def test_quarterly_margin_uses_depreciation_from_year_to_date_cash_flow(p):
    q = p["quarters"]
    i = q["cols"].index("Mar 2026")
    assert q["rows"]["OPM %"][i] == round((29600 + 2950) / 95400 * 100, 1)


def test_a_10k_is_cut_to_its_business_risks_and_discussion_not_its_contents_page():
    s = sec.SEC(transport=fake_sec.transport())
    p = s.company("AAPL")
    annual = next(d for d in p["documents"] if d["kind"] == "annual_report")
    text = s.annual(annual)
    assert "[BUSINESS]" in text and "smartphones" in text and "[RISKS]" in text and "supply chains" in text
    assert "[MDNA]" in text and "$14 billion" in text and "hidden xbrl header" not in text
    assert "Offices in Cupertino" not in text                          # the parts in between are left out
    rel = next(d for d in p["documents"] if d["kind"] == "earnings_release")
    assert "low to mid single digits" in s.release(rel)                # the exhibit 99 press release, not the cover
    with pytest.raises(SourceError):
        s.document("https://evil.example.com/Archives/x.htm")


def test_us_documents_are_read_with_ai_and_stored(monkeypatch):
    from app import deepdive, report_card
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        saved = {}
        monkeypatch.setattr(deepdive, "stored", lambda k: saved.get(k))
        monkeypatch.setattr(deepdive, "store", lambda k, v: saved.__setitem__(k, {**v, "at": "2026-10-03", "ts": 9e18}) or v)
        monkeypatch.setattr(report_card, "stored", lambda s: None)
        c, h = w["client"], W.headers("pro-token")
        r = c.post("/research/deep/AAPL/read?region=US", headers=h)
        assert r.status_code == 200, r.text
        stored = saved["US:AAPL"]
        assert [d["kind"] for d in stored["read"]] == ["annual_report", "earnings_release"]
        assert "AAPL" not in saved                                      # never mixed up with an Indian symbol's read
        assert w["ai"].calls >= 1
    finally:
        w["close"]()


def test_report_card_periods_follow_the_companys_own_fiscal_year():
    from datetime import date
    from app import report_card as rc
    assert rc.fy_of(date(2025, 10, 15), 9) == 2026 and rc.fy_of(date(2025, 9, 15), 9) == 2025
    assert rc.period_end({"kind": "FY", "fy": 2026}, 9) == date(2026, 9, 30)
    assert rc.period_end({"kind": "Q", "fy": 2026, "q": 1}, 9) == date(2025, 12, 31)       # Apple's December quarter
    assert rc.period_end({"kind": "Q", "fy": 2026, "q": 4}, 3) == date(2026, 3, 31)        # India unchanged
    assert rc.period_end({"kind": "Q", "fy": 2026, "q": 1}, 3) == date(2025, 6, 30)
    assert rc._table_label({"kind": "Q", "fy": 2026, "q": 2}, 9) == "Mar 2026"
    assert rc.parse_period("next fiscal year", date(2025, 10, 30), 9) == {"kind": "FY", "fy": 2027}


def test_us_report_card_from_earnings_releases(monkeypatch):
    from app import deepdive, report_card
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        saved = {}
        monkeypatch.setattr(deepdive, "stored", lambda k: None)
        monkeypatch.setattr(report_card, "stored", lambda k: saved.get(k))
        monkeypatch.setattr(report_card, "store", lambda k, v: saved.__setitem__(k, {**v, "at": "2026-10-03", "ts": 9e18}) or v)
        quote = "The Company expects revenue to grow in the low to mid single digits in the June quarter."
        monkeypatch.setattr(report_card, "complete", lambda *a, **k: json.dumps({"guidance": [
            {"metric": "revenue_growth", "low": 1, "high": 5, "unit": "%", "period": "Q3 FY2026",
             "what": "Revenue growth of low to mid single digits", "quote": quote, "source": "S1"},
            {"metric": "margin", "low": 99, "period": "FY2020", "what": "invented", "quote": "not in the release at all here", "source": "S1"}]}))
        c, h = w["client"], W.headers("pro-token")
        r = c.post("/research/deep/AAPL/card?region=US", headers=h)
        assert r.status_code == 200, r.text
        card = r.json()["card"]
        assert len(card["rows"]) == 1 and card["rows"][0]["period"] == "Q3 FY26"          # the made-up quote is dropped
        row = card["rows"][0]
        assert row["metric"] == "revenue_growth" and row["source"]["url"].endswith("a8-kex991q2.htm")   # the exhibit 99 release
        assert "US:AAPL" in saved and r.json()["report_card"] and r.json()["calls"] == 2
    finally:
        w["close"]()


def test_insider_buying_and_selling_in_the_us_checklist():
    from datetime import date
    from app.checklist import insider_flow
    rows = [{"name": "A", "change": 1000, "transactionCode": "P", "transactionDate": "2026-08-01"},
            {"name": "B", "change": -5000, "transactionCode": "S", "transactionDate": "2026-09-01"},
            {"name": "C", "change": 90000, "transactionCode": "M", "transactionDate": "2026-09-02"},     # an option exercise
            {"name": "D", "change": -4000, "transactionCode": "S", "transactionDate": "2025-01-01"}]     # too old
    assert insider_flow(rows, date(2026, 10, 3)) == {"bought": 1000, "sold": 5000, "buyers": 1, "sellers": 1}
    assert insider_flow([], date(2026, 10, 3)) is None


def test_us_checklist_shows_insiders(monkeypatch):
    from app import deepdive, report_card
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(deepdive, "stored", lambda k: None)
        monkeypatch.setattr(report_card, "stored", lambda k: None)
        v = w["client"].get("/research/deep/AAPL?region=US", headers=W.headers("pro-token")).json()
        ins = [c for c in v["checklist"]["checks"] if c["group"] == "Insiders"]
        assert ins and ins[0]["label"] == "Insider buying and selling, 6 months"
        assert not [c for c in v["checklist"]["checks"] if c["group"] == "Promoters"]
    finally:
        w["close"]()


def test_investor_home_for_us_watchlist(monkeypatch):
    import json
    from app import db, deepdive, report_card
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setattr(deepdive, "stored", lambda s: None)
        monkeypatch.setattr(report_card, "stored", lambda s: None)
        c, h = w["client"], W.headers("pro-token")
        uid = c.get("/me", headers=h).json()["id"]
        db.set_setting(f"watchlist:{uid}", json.dumps({"items": [{"region": "IN", "symbol": "RELIANCE"}, {"region": "US", "symbol": "AAPL"}]}))
        us = c.get("/research/investor?region=US", headers=h).json()
        assert us["region"] == "US" and [r["symbol"] for r in us["rows"]] == ["AAPL"]
        row = us["rows"][0]
        assert row["checks"] and row["red"] is None and row["problem"] is None
        assert [r["symbol"] for r in c.get("/research/investor", headers=h).json()["rows"]] == ["RELIANCE"]
    finally:
        w["close"]()
