"""Round 80 (launch check, signed-out visitor, 22 Oct 2026)."""
from app import main  # noqa: F401  (loads the app first, as the other review tests do)
from app import library, stock_pages


def test_mixed_case_brands_keep_their_capitals():
    # R80-016: "CONOCOPHILLIPS" came out as "Conocophillips"
    assert stock_pages.proper_name("CONOCOPHILLIPS") == "ConocoPhillips"
    assert stock_pages.proper_name("PEPSICO INC") == "PepsiCo Inc"
    assert stock_pages.proper_name("ABBVIE INC.") == "AbbVie Inc."
    assert stock_pages.proper_name("CHEVRON CORP") == "Chevron Corp"


def test_a_losing_library_strategy_says_its_checks_ran():
    # R80-005: "the checks weren't run" sat above a list of the checks' results
    e = {"verdict": {"verdict": "no_edge", "checks": [{"id": "oos", "status": "fail"}]}, "stats": {"ret": -4.2, "trades": 40}}
    line = library.reason(e)
    assert "weren't run" not in line and "shown for reference" in line


def test_the_stocks_search_form_keeps_one_row_and_fonts_dont_shift_it():
    # R80-002 / R80-015: the form wrapped to two rows on a phone, then jumped to one; fonts swapped in late
    html = stock_pages.STYLE
    assert "font-display:swap" not in html and "font-display:optional" in html
    assert "form.find{display:flex;gap:8px;flex-wrap:nowrap" in html and "form.find input{flex:1;min-width:0}" in html
    assert 'placeholder="Company or symbol"' in stock_pages._find_form("IN")
