"""Admin Quality audit findings: the page's price is the last close, and impossible ratios are left out."""
import pytest

from app import audit
from app.intel.company import at_live_price
from app.intel.screener import _pe, drop_impossible_margins, summary


def test_price_is_the_last_close_across_a_bonus(monkeypatch):
    """SIMPLXREA: the page kept the source's older 142.00 beside a last close of 122.95 whenever a bonus was recorded
    since the source was read."""
    from app import corp_actions
    monkeypatch.setattr(corp_actions, "actions_for", lambda *a, **k: [{"kind": "bonus", "factor": 1.1, "ex_date": "2026-10-10"}])
    s = {"price": 142.0, "pe": 20.0, "book_value": 100.0, "market_cap_cr": 500.0, "div_yield": 1.0}
    out = at_live_price(s, 122.95, "SIMPLXREA", "2026-10-09T05:00+00:00")
    assert out["price"] == 122.95
    assert out["pb"] is None and out["div_yield"] is None
    assert audit.check_prices({"price": out["price"]}, {"price": 122.95, "t": "2026-10-13"}, None) == []


def test_price_is_the_last_close_past_a_move_too_big_for_a_day():
    s = {"price": 65.99, "pe": 20.0, "book_value": 10.0, "market_cap_cr": 500.0, "div_yield": 1.0}
    out = at_live_price(s, 30.0)
    assert out["price"] == 30.0
    assert (out["pe"], out["pb"], out["market_cap_cr"], out["div_yield"]) == (None, None, None, None)
    assert at_live_price({"pe": 5.0}, 30.0) == {"pe": 5.0}           # no price of its own: nothing to compare with


def test_margin_above_100_percent_is_left_out():
    """JIOFIN, Mar 2023: an operating margin above 100% on a revenue row that isn't comparable."""
    p = {"pl": {"cols": ["Mar 2022", "Mar 2023", "Mar 2024"],
                "rows": {"Sales": [1.0, 3.0, 1700.0], "OPM %": [40, 250, 82]}},
         "quarters": {"cols": ["Q1", "Q2", "Q3"], "rows": {"Revenue": [10.0, -4.0, 20.0], "OPM %": [30, 150, 25]}}}
    drop_impossible_margins(p)
    assert p["pl"]["rows"]["OPM %"] == [40, None, 82]
    assert p["quarters"]["rows"]["OPM %"] == [30, None, 25]            # above 100%, and on negative revenue
    q = {"quarters": {"cols": ["Q1"], "rows": {"Sales": [-5.0], "OPM %": [12]}}}
    assert drop_impossible_margins(q)["quarters"]["rows"]["OPM %"] == [None]
    assert drop_impossible_margins({"pl": None}) == {"pl": None}


def _page(eps, own_pe=None):
    return {"pl": {"cols": ["Mar 2025", "TTM"], "rows": {"EPS in Rs": [5.0, eps]}},
            "ratios": {"Current Price": "150", **({"Stock P/E": str(own_pe)} if own_pe else {})}}


def test_pe_from_a_mis_scaled_eps_is_not_shown():
    """Coromandel Agro: P/E 0.1 from an EPS ten times the price."""
    assert _pe(_page(1500.0), 150.0) is None
    assert _pe(_page(1500.0, own_pe=12.0), 150.0) == 12.0               # the source's own figure when it is a P/E
    assert _pe(_page(1500.0, own_pe=0.1), 150.0) is None
    assert _pe(_page(10.0), 150.0) == 15.0                              # an ordinary P/E is as before
    assert summary(_page(1500.0))["pe"] is None
