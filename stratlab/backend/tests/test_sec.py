"""US company numbers from the SEC's XBRL filings, in the same shape as the Indian company pages."""
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
        assert not v["ai"] and any(d["kind"] == "annual_report" for d in v["documents"])
        fcf = next(x for x in v["checklist"]["checks"] if x["label"] == "Free cash flow, 3 years")
        assert fcf["value"].startswith("$") and fcf["value"].endswith(" m")
        deck = c.get("/research/deep/AAPL/deck?region=US", headers=h)
        assert deck.status_code == 200 and deck.content[:2] == b"PK"
        assert c.post("/research/deep/AAPL/read?region=US", headers=h).json()["detail"]["code"] == "us_ai_not_yet"
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
