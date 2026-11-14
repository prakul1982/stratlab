"""Release 53, lane app53: company AI reads held to the page's figures of now (LIVE8B-009), a bank's top line called revenue and a one-off's
note said once in the whole read (LIVE8B-010)."""
from datetime import date

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app.intel import ai as A
from app.intel import grounding as G
from tests.test_review_r6o import _aapl


def test_a_stored_read_drops_a_figure_the_page_no_longer_shows():
    read = {"summary": "Apple designs iPhones, Macs and services. Revenue rose 6.4% in FY25 to $416.16 billion.",
            "valuation_note": "P/E is 38.92.", "bull": ["Net margin over the last twelve months is 27.6%."], "bear": [], "position": "", "watch": [],
            "facts": [], "ideas": []}
    same = A.regrounded(read, _aapl(), date(2026, 10, 8))
    assert same["valuation_note"] == "P/E is 38.92."
    # the price moved on: the page's P/E is 39.7 now, so the read's 38.92 is left out; the rest stands
    now = _aapl()
    now["metrics"][0]["items"][0]["value"] = 39.7
    got = A.regrounded(read, now, date(2026, 10, 8))
    assert "38.92" not in got["valuation_note"]
    assert got["summary"] == read["summary"] and got["bull"] == read["bull"]
    # with no page figures the read is served as stored
    assert A.regrounded(read, None) is read


def test_a_banks_read_says_revenue_and_a_one_off_note_once():
    read = {"summary": "Sales in the Sep 2026 quarter were ₹95,132 Cr (Mar 2024 had a tax rate of -1% against a median of 24%). It is a large bank.",
            "valuation_note": "", "position": "",
            "bull": ["Net profit rose 12% on Mar 2024 (Mar 2024 had a tax rate of -1% against a median of 24%)."],
            "bear": ["Quarterly sales fell 3%."], "watch": [], "ideas": []}
    out = G.polish_company(read, "IN", lender=True, today=date(2026, 11, 14))
    text = " ".join([out["summary"], *out["bull"], *out["bear"]])
    assert "Sales" not in text and " sales " not in text
    assert out["summary"].startswith("Revenue in the Sep 2026 quarter were")
    assert out["bear"] == ["Quarterly revenue fell 3%."]
    assert text.count("tax rate of") == 1
    # a company that isn't a lender keeps its sales
    assert G.polish_company(read, "IN", lender=False, today=date(2026, 11, 14))["summary"].startswith("Sales")


def test_a_banks_facts_name_its_top_line_revenue():
    c = {"region": "IN", "symbol": "HDFCBANK", "name": "HDFC Bank", "bank": True,
         "quarters": {"cols": ["Jun 2026", "Sep 2026"], "sales": [93000, 95132], "profit": [16000, 17000]}}
    f = A.company_facts(c)
    assert f["quarterly_results"]["revenue"] == [93000, 95132] and "sales" not in f["quarterly_results"]
    assert "never call it sales" in f["lender"]


def test_a_growth_row_is_a_percentage_whatever_its_label():
    from app import company_tables as T
    assert T.kind_of("Sales Growth") == "pct" and T.kind_of("Profit growth") == "pct"
    assert T.kind_of("Sales") == "money" and T.kind_of("OPM %") == "pct"
