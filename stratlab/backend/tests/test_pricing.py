"""Prices outside India: a price per currency, editable by the admin, charged in that currency once its Razorpay
plans exist and in rupees until then."""
from types import SimpleNamespace

import pytest

from app import billing, pricing
from app.config import settings


@pytest.fixture
def store(monkeypatch):
    saved = {}
    monkeypatch.setattr(pricing.db, "get_setting", lambda k: saved.get(k))
    monkeypatch.setattr(pricing.db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    return saved


def test_every_currency_has_prices_and_is_charged_in_rupees_until_its_plans_exist(store):
    t = pricing.table()
    assert t["INR"]["basic"] == 999 and t["INR"]["charged_in"] == "INR"
    assert t["USD"]["basic"] == 12 and t["USD"]["pro_year"] == 350 and t["USD"]["charged_in"] == "INR"
    assert {"EUR", "GBP", "AUD", "JPY", "AED"} <= set(t)
    pub = pricing.public()
    assert pub["countries"]["DE"] == "EUR" and pub["countries"]["IN"] == "INR"
    assert "plan_basic" not in pub["currencies"]["USD"]                     # plan IDs stay on the server


def test_admin_changes_prices_and_plans(store):
    t = pricing.save({"USD": {"basic": 9, "pro": 29.5, "plan_basic": "plan_ABC123", "plan_pro": "plan_DEF456"},
                      "INR": {"basic": 1}, "XXX": {"basic": 1}})
    assert t["USD"]["basic"] == 9 and t["USD"]["pro"] == 29.5 and t["USD"]["charged_in"] == "USD"
    assert t["INR"]["basic"] == 999                                          # rupee prices come from the plans
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
