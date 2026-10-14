"""Research fixes: the deck's yield is the public page's; zero net worth isn't negative; a capex target is a band;
a US filer's capex is only what it reported."""
from datetime import date

from app import deepdive, main, report_card, report_card as rc
from app.main import screener_summary
from tests.test_audit import base_for
from tests.test_deepdive import company
from tests.test_report_card import g


def _deck(monkeypatch, divs):
    p = company()
    p["region"] = "US"
    p["ratios"] = {"Market Cap": "520", "Stock P/E": "20", "Current Price": "100", "Dividend Yield": "0.00 %"}
    monkeypatch.setattr(deepdive, "stored", lambda s: None)
    monkeypatch.setattr(report_card, "stored", lambda s: None)
    monkeypatch.setattr(main, "page_dividend_yield", lambda *a, **k: None)      # the app's own list holds none
    def events(sym, n):
        if divs is None:
            raise RuntimeError("no history")
        return {"dividends": divs}
    monkeypatch.setattr(main.research_hub.yahoo, "events", events)
    return main.deep_view("ACME", base_for(p, {"price": 100.0, "t": "2026-10-08T00:00:00"})("ACME"))["snapshot"]["div_yield"]


def test_us_deck_yield_is_na_without_a_list_and_the_pages_fallback_with_one(monkeypatch):
    assert _deck(monkeypatch, None) is None                                 # not the filings' 0.00%
    assert _deck(monkeypatch, []) == 0.0                                   # a history read with none in the year: a real 0%, as on the page
    assert _deck(monkeypatch, [{"date": "2026-06-01", "amount": 2.0}]) == 2.0


def test_zero_net_worth_is_not_negative():
    def s(reserves):
        p = company()
        p["balance"]["rows"]["Reserves"] = [reserves] * 6
        p["balance"]["rows"]["Equity Capital"] = [0] * 6
        return screener_summary(p)
    assert s(0)["debt_equity"] is None and not s(0)["net_worth_negative"]
    assert s(-5)["debt_equity"] is None and s(-5)["net_worth_negative"]


def test_capex_is_a_band_other_targets_are_floors():
    nums = deepdive.numbers(company())      # FY25 capex 23
    def res(metric, low, high=None):
        return rc.check(g(metric, low, "FY25", high=high), nums, today=date(2026, 9, 30))["result"]
    assert res("capex", 25) == "met" and res("capex", 20) == "missed"
    assert res("capex", 10) == "missed"                                     # overspent past 11
    assert res("capex", 10, 21) == "met" and res("capex", 30) == "missed"
    assert res("revenue_growth", 10) == "met"                               # beating a growth target stays met


def test_us_filer_with_partial_capex_row_leaves_unreported_years_blank():
    p = company()
    p["cashflow"]["rows"]["Capex"] = [None, None, None, None, 30, 40]
    n = deepdive.numbers(p)
    y = {r["year"]: r["capex"] for r in n["years"]}
    assert y["Mar 2025"] == 40 and y["Mar 2024"] == 30 and y["Mar 2023"] is None
    assert n["capex_3y_total"] == 70 and n["capex_years"] == 2
