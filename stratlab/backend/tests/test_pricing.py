"""Prices outside India: a price per currency, editable by the admin, charged in that currency once its Razorpay
plans exist and in rupees until then."""
from types import SimpleNamespace

import pytest

from app import billing, pricing
from app.config import settings


@pytest.fixture
def store(monkeypatch):
    saved = {}
    pricing.forget()                    # prices another test saved, kept in memory
    monkeypatch.setattr(pricing.db, "get_setting", lambda k: saved.get(k))
    monkeypatch.setattr(pricing.db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    return saved


def test_every_currency_has_prices_and_is_charged_in_rupees_until_its_plans_exist(store):
    t = pricing.table()
    assert (t["INR"]["basic"], t["INR"]["pro"], t["INR"]["basic_year"], t["INR"]["pro_year"]) == (699, 1999, 6999, 19999)
    assert t["INR"]["charged_in"] == "INR"
    assert (t["USD"]["basic"], t["USD"]["pro"], t["USD"]["basic_year"], t["USD"]["pro_year"]) == (8, 20, 80, 200)
    assert t["USD"]["charged_in"] == "INR"
    assert (t["EUR"]["basic"], t["EUR"]["pro"], t["GBP"]["basic"], t["GBP"]["pro"]) == (8, 19, 7, 16)
    assert (t["AUD"]["basic"], t["AUD"]["pro"], t["JPY"]["pro"], t["MYR"]["basic"]) == (9, 27, 2650, 27)
    assert {"EUR", "GBP", "AUD", "JPY", "AED"} <= set(t)
    pub = pricing.public()
    assert pub["countries"]["DE"] == "EUR" and pub["countries"]["IN"] == "INR"
    assert "plan_basic" not in pub["currencies"]["USD"]                     # plan IDs stay on the server


def test_admin_changes_prices_and_plans(store):
    t = pricing.save({"USD": {"basic": 9, "pro": 29.5, "plan_basic": "plan_ABC123", "plan_pro": "plan_DEF456"},
                      "INR": {"basic": 1}, "XXX": {"basic": 1}})
    assert t["USD"]["basic"] == 9 and t["USD"]["pro"] == 29.5 and t["USD"]["charged_in"] == "USD"
    assert t["INR"]["basic"] == 699                                          # rupee prices come from the plans
    assert pricing.plan_id("USD", "pro", "month") == "plan_DEF456" and pricing.plan_id("USD", "pro", "year") is None
    assert pricing.all_plan_ids()["plan_ABC123"] == ("USD", "basic", "month")
    with pytest.raises(ValueError, match="positive"):
        pricing.save({"EUR": {"basic": -3}})
    with pytest.raises(ValueError, match="plan ID"):
        pricing.save({"EUR": {"plan_basic": "not a plan"}})
    pricing.save({"USD": {"plan_basic": ""}})                               # cleared: back to rupees
    assert pricing.table()["USD"]["charged_in"] == "INR"


def _billing(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_test_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "plan_inrB"),
                 ("RAZORPAY_PLAN_PRO", "plan_inrP")):
        monkeypatch.setattr(settings, k, v)
    made = []
    fake = SimpleNamespace(subscription=SimpleNamespace(create=lambda body: made.append(body) or {"id": "sub_1"}))
    monkeypatch.setattr(billing, "_client", fake)
    monkeypatch.setattr(billing.db, "update_profile", lambda *a, **k: None)
    return made


def test_subscribing_uses_the_currencys_plan_or_falls_back_to_rupees(store, monkeypatch):
    made = _billing(monkeypatch)
    out = billing.create_subscription({"id": "u", "email": "a@b.c"}, "pro", "month", "USD")
    assert made[-1]["plan_id"] == "plan_inrP" and out["currency"] == "INR"
    pricing.save({"USD": {"plan_basic": "plan_usdB", "plan_pro": "plan_usdP"}})
    out = billing.create_subscription({"id": "u", "email": "a@b.c"}, "pro", "month", "USD")
    assert made[-1]["plan_id"] == "plan_usdP" and out["currency"] == "USD" and made[-1]["notes"]["currency"] == "USD"
    assert billing.plan_for({"plan_id": "plan_usdP"}) == "pro"                # a renewal finds its plan
    with pytest.raises(ValueError, match="Yearly"):                          # no yearly plan in either currency
        billing.create_subscription({"id": "u"}, "pro", "year", "USD")


def test_pricing_routes(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        c = w["client"]
        assert c.get("/pricing").json()["currencies"]["GBP"]["symbol"] == "£"
        assert c.put("/admin/prices", headers=W.headers("pro-token"), json={"currencies": {}}).status_code == 403
        r = c.put("/admin/prices", headers=W.headers("admin-token"), json={"currencies": {"GBP": {"basic": 8}}})
        assert r.status_code == 200 and c.get("/pricing").json()["currencies"]["GBP"]["basic"] == 8
        bad = c.put("/admin/prices", headers=W.headers("admin-token"), json={"currencies": {"GBP": {"basic": "free"}}})
        assert bad.status_code == 400
        assert c.post("/billing/subscribe", headers=W.headers("free-token"), json={"plan": "pro", "currency": "us"}).status_code == 422
    finally:
        w["close"]()


def test_prices_follow_the_rupee_price_at_todays_rate(store, monkeypatch):
    pricing._rates_cache[0] = 0.0
    rates = {"USD": 88.0, "GBP": 118.0, "JPY": 0.59, "AUD": 58.0}
    state = pricing.refresh_rates(lambda code: rates.get(code) or 1 / 0)
    assert state["rates"] == rates and any("EUR" in e for e in state["errors"])
    t = pricing.table()
    assert t["AUD"]["basic"] == 12 and t["AUD"]["pro"] == 34 and t["AUD"]["auto"]       # 699/58, 1999/58, tidied
    assert t["JPY"]["basic"] == 1200 and t["AUD"]["basic_year"] == 120
    assert t["CAD"]["basic"] == 8                                                       # no rate yet: the built-in amount
    # dollars, euros and pounds keep their own prices whatever the rate ($8 and $20, whatever 699/88 comes to)
    assert (t["USD"]["basic"], t["USD"]["pro"], t["USD"]["pro_year"], t["GBP"]["basic"]) == (8, 20, 200, 7)
    monkeypatch.setitem(pricing.PLANS["basic"], "price", 999)                           # the rupee price changes...
    assert pricing.table()["AUD"]["basic"] == 17 and pricing.table()["USD"]["basic"] == 8   # ...the others follow
    pricing.save({"USD": {"basic": 9}})                                                 # changed by the admin
    t = pricing.table()
    assert t["USD"]["basic"] == 9 and not t["USD"]["auto"] and t["USD"]["pro"] == 20
    pricing.save({"USD": {"basic": None}})                                              # back to the default
    assert pricing.table()["USD"]["auto"] and pricing.table()["USD"]["basic"] == 8
    pricing._rates_cache[0] = 0.0
    again = pricing.refresh_rates(lambda code: 1 / 0)                                    # the source is down
    assert again["rates"]["USD"] == 88.0                                                 # the last good rates stay


def test_nice_amounts():
    assert [pricing.nice(v) for v in (0.3, 11.35, 99.6, 137, 1694, 12340)] == [1, 11, 100, 135, 1700, 12500]


def test_a_failed_read_keeps_the_old_rate_with_its_old_time(store):
    """Item a: a day whose dollar read fails keeps the last good rate and the time it was read; it isn't stamped as read
    now (the pages would show an old rate as today's)."""
    pricing._rates_cache[0] = 0.0
    first = pricing.refresh_rates(lambda code: 88.0)
    assert not first["errors"] and pricing.rate_at("USD") == first["at"] == first["read_at"]["USD"]
    again = pricing.refresh_rates(lambda code: 1 / 0 if code == "USD" else 90.0)
    assert again["rates"]["USD"] == 88.0 and again["read_at"]["USD"] == first["at"] and pricing.rate_at("USD") == first["at"]
    assert again["at"] == first["at"] and again["read_at"]["GBP"] > first["at"]


def test_admin_rates_time_is_each_rates_own_and_the_oldest_of_them(store):
    """rev6a: "at" moves only when every rate was read, so Admin showed None after a first read with one error, and a stuck
    time while one currency kept failing. Admin now has each rate's own read time and the oldest of them."""
    import time_machine
    from datetime import datetime, timezone
    from app import main
    with time_machine.travel(datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)):
        pricing.refresh_rates(lambda code: 1 / 0 if code == "EUR" else 90.0)           # a first read with an error
    v = main.prices_view()
    assert v["rates_at"] and v["rates_at"].startswith("2026-10-01T06:00") and "EUR" not in v["rates_read_at"]
    assert v["rates_read_at"]["USD"] == v["rates_at"] and any(e.startswith("EUR") for e in v["rate_errors"])
    with time_machine.travel(datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc)):
        pricing.refresh_rates(lambda code: 90.0)
    with time_machine.travel(datetime(2026, 10, 3, 6, 0, tzinfo=timezone.utc)):
        pricing.refresh_rates(lambda code: 1 / 0 if code == "EUR" else 91.0)           # EUR keeps failing from here
    v = main.prices_view()
    assert v["rates_read_at"]["USD"].startswith("2026-10-03") and v["rates_read_at"]["EUR"].startswith("2026-10-02")
    assert v["rates_at"] == v["rates_read_at"]["EUR"]                                    # the oldest rate shown
    assert pricing.rate_at("USD").startswith("2026-10-03")                              # what Holdings shows is unchanged
