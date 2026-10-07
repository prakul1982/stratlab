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


def test_dividend_on_the_money_calendar_counts_the_bonus_before_it(w):
    """R1-002: TCS's 1:1 bonus goes ex today and its ₹11 dividend in three days. 12 shares held before the bonus are
    24 on the dividend's ex-date: ₹264 on the Money calendar, as on Holdings and Tax tools."""
    from datetime import date, timedelta
    from app import holdings, main, money_calendar
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    holdings.save("u-pro", [{"symbol": "TCS", "qty": 12, "avg": 3000.0, "since": yesterday}], "manual")
    main.corp_job.refresh("IN")
    evs = money_calendar.holdings_events("u-pro", date.today(), date.today() + timedelta(days=10))
    div = [e for e in evs if e.get("symbol") == "TCS" and str(e.get("kind", "")).endswith("dividend")]
    assert div and {round(e["amount"], 2) for e in div} == {264.0}
    assert "On 24 shares (counting the bonus or split before it)" in div[0]["detail"]
    hv = w["client"].get("/holdings", headers=H(w)).json()
    ahead = [x for x in (hv.get("actions") or {}).get("ahead", []) if x["symbol"] == "TCS"]
    assert not ahead or ahead[0]["total"] == 264.0


def test_red_flags_follow_holdings_and_the_watchlist(w):
    """R1-049: the red-flag list covers the stocks the person holds, not only the ones they watch (ETFs left out)."""
    import json
    from app import db, holdings
    from app.intel import filings
    holdings.save("u-pro", [{"symbol": "TCS", "qty": 5, "avg": 3000.0}, {"symbol": "NIFTYBEES", "qty": 10, "avg": 250.0},
                            {"symbol": "INFY", "qty": 2, "avg": 1500.0}], "manual")
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"region": "IN", "symbol": "INFY"}, {"region": "IN", "symbol": "ITC"},
                                                            {"region": "US", "symbol": "AAPL"}]}))
    assert filings.followed_symbols("u-pro") == ["TCS", "INFY", "ITC"]


def test_an_unchanged_rerun_asks_first(w):
    """R1-023: the same rules, market and period run again the same day would repeat the last experiment."""
    c, h = w["client"], H(w)
    from tests.test_notebooks import EMA
    nb = c.post("/notebooks", headers=h, json={"name": "Repeat", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    first = c.post(f"/notebooks/{nb['id']}/experiments", headers=h, json={"days": 365})
    assert first.status_code == 200, first.text
    again = c.post(f"/notebooks/{nb['id']}/experiments", headers=h, json={"days": 365})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "same_as_last"
    assert "Nothing changed since v1" in again.json()["detail"]["message"]
    assert c.post(f"/notebooks/{nb['id']}/experiments", headers=h, json={"days": 730}).status_code == 200      # a new period is a new test
    forced = c.post(f"/notebooks/{nb['id']}/experiments", headers=h, json={"days": 730, "again": True})
    assert forced.status_code == 200 and forced.json()["experiment"]["v"] == 3


def test_company_growth_matches_the_ai_read_facts(w):
    """F4-004: the Key numbers card and the facts beside the AI read work growth out the same way."""
    from app.intel import routes
    c = w["client"].get("/research/company/IN/RELIANCE", headers=H(w)).json()
    val = {(g["title"], i["label"]): i["value"] for g in c["metrics"] for i in g["items"]}
    rows = {r["id"]: {i["label"]: i["text"] for i in r["items"]} for r in routes.company_key_facts("IN", c)}
    assert rows["growth"]["Sales, 3 years"] == f"{val[('Sales growth', '3Y CAGR')]:.1f}% a year"
    assert rows["growth"]["Net profit, 5 years"] == f"{val[('Profit growth', '5Y CAGR')]:.1f}% a year"
