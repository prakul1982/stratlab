"""Fixes from the first fresh-eyes review (round 1): the same fact shows the same number everywhere."""
import pytest

from app.intel.company import at_live_price


def test_ratios_follow_the_live_price():
    s = {"price": 1400.0, "pe": 28.0, "book_value": 700.0, "pb": 2.0, "div_yield": 0.5, "market_cap_cr": 1_900_000.0}
    out = at_live_price(s, 1540.0)                      # the price moved 10% since the fundamentals were read
    assert out["price"] == 1540.0
    assert out["pe"] == pytest.approx(30.8)
    assert out["pb"] == pytest.approx(2.2)
    assert out["div_yield"] == pytest.approx(0.5 / 1.1)
    assert out["market_cap_cr"] == pytest.approx(2_090_000.0)
    assert out["book_value"] == 700.0                   # a reported number: it doesn't move with the price
    assert s["pe"] == 28.0                              # the input is left alone


@pytest.mark.parametrize("live", [None, 0, -5])
def test_ratios_stay_without_a_live_price(live):
    s = {"price": 1400.0, "pe": 28.0}
    assert at_live_price(s, live) is s
    assert at_live_price({"pe": 28.0}, 1500.0) == {"pe": 28.0}       # no price of its own to scale from


@pytest.fixture
def w(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def H(w, token="pro-token"):
    return w["headers"](token)


def test_an_unknown_company_is_not_found_not_a_fault(w):
    r = w["client"].get("/research/company/IN/ZZZZNOTREAL", headers=H(w))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"
    assert "Couldn't find ZZZZNOTREAL" in r.json()["detail"]["message"]
    assert w["client"].get("/research/company/IN/RELIANCE", headers=H(w)).status_code == 200


def test_company_page_ratios_agree_with_its_price(w):
    c = w["client"].get("/research/company/IN/RELIANCE", headers=H(w)).json()
    live = c["quote"]["price"]
    val = {i["label"]: i["value"] for g in c["metrics"] if g["title"] == "Valuation" for i in g["items"]}
    assert val["P/B"] == pytest.approx(live / val["Book value"], rel=1e-6)
    # the demo world's broker prices RELIANCE near where its fundamentals were read (fake_prices), as the real one would
    assert 0.8 < live / 1408 < 1.25
