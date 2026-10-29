"""RC-7, the main review, round 3: what broke in the flows, each with the test that proves it."""
from app.intel.company import with_dividend_yield


def _page(region="IN", yield_=1.0):
    return {"region": region, "symbol": "ORIONPOLY", "quote": {"price": 140.0},
            "metrics": [{"title": "Valuation", "items": [{"label": "P/E", "value": 15.4, "unit": "x"},
                                                           {"label": "Div yield", "value": yield_, "unit": "%", "note": "From the last reported year's dividends"}]}],
            "summary": {"div_yield": yield_}}


def _yield(c):
    return next(i for g in c["metrics"] for i in g["items"] if i["label"] == "Div yield")


def test_a_dividends_list_that_was_read_and_has_none_in_the_year_is_a_real_zero_not_the_sources_figure():
    """RC7-006: the company page kept the source's 1.0% "from the last reported year's dividends" where the public page and the
    deep dive said 0.00% for the same company: with the list read and no ex-date in the year, it is 0% on all three."""
    out = with_dividend_yield(_page(), [], "2026-10-28", listed=True)
    assert _yield(out)["value"] == 0.0 and "No dividend with an ex-date in the last 12 months" in _yield(out)["note"]
    assert out["summary"]["div_yield"] == 0.0
    # an old dividend (14 months ago) does not count either: it is outside the year
    old = [{"kind": "dividend", "amount": 5, "ex_date": "2025-08-20"}]
    assert _yield(with_dividend_yield(_page(), old, "2026-10-28", listed=True))["value"] == 0.0


def test_without_a_list_to_go_on_the_sources_figure_stays_labelled_as_its_own():
    out = with_dividend_yield(_page(), [], "2026-10-28", listed=False)
    assert _yield(out)["value"] == 1.0 and _yield(out)["note"] == "From the last reported year's dividends"


def test_a_dividend_in_the_year_still_gives_the_yield_from_the_list():
    rows = [{"kind": "dividend", "amount": 7, "ex_date": "2026-08-20"}]
    out = with_dividend_yield(_page(), rows, "2026-10-28", listed=True)
    assert _yield(out)["value"] == 5.0 and "₹7" in _yield(out)["note"]            # 7 over 140


def test_the_us_page_is_left_as_it_was_by_the_list_flag():
    out = with_dividend_yield(_page("US"), [], "2026-10-28", listed=True)
    assert _yield(out)["value"] == 1.0
