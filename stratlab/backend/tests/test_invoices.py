"""GST invoices: one per payment, numbered per financial year, with the tax the rules call for."""
import json
from types import SimpleNamespace

import pytest

from app import billing, invoices
from app.config import settings


@pytest.fixture
def store(monkeypatch):
    saved = {}
    monkeypatch.setattr(invoices.db, "get_setting", lambda k: saved.get(k))
    monkeypatch.setattr(invoices.db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    return saved


SELLER = {"legal_name": "StratLab Studio", "address": "Pune", "state": "27", "gstin": "27ABCDE1234F1Z5", "pan": "ABCDE1234F",
          "lut_arn": "", "email": "billing@stratlab.studio", "prefix": "SL"}
PAY = {"id": "pay_1", "amount": 99900, "currency": "INR", "created_at": 1791000000, "international": False, "status": "captured"}


def test_domestic_invoice_splits_gst_and_numbers_by_financial_year(store):
    invoices.save_seller(SELLER)
    inv = invoices.make(PAY, {"id": "u1", "email": "a@b.c"}, "basic", "month")
    assert inv["number"] == "SL/2026-27/0001" and inv["supply"] == "Intra-state"
    assert [t["name"] for t in inv["taxes"]] == ["CGST 9%", "SGST 9%"]
    assert inv["item"]["taxable"] == round(999 / 1.18, 2) and round(inv["item"]["taxable"] + sum(t["amount"] for t in inv["taxes"]), 2) == 999
    assert invoices.make(PAY, {"id": "u1"}, "basic", "month")["number"] == inv["number"]           # one per payment
    nxt = invoices.make({**PAY, "id": "pay_2"}, {"id": "u1"}, "basic", "month")
    assert nxt["number"] == "SL/2026-27/0002" and [i["number"] for i in invoices.of_user("u1")] == ["SL/2026-27/0002", "SL/2026-27/0001"]
    assert invoices.fy(__import__("datetime").datetime(2027, 3, 31, 20, tzinfo=__import__("datetime").timezone.utc)) == "2027-28"   # 1 Apr in India


def test_other_states_exports_and_unregistered_sellers(store):
    invoices.save_seller(SELLER)
    invoices.save_billing("u2", {"name": "Acme", "state": "29", "country": "IN"})
    assert invoices.make({**PAY, "id": "p3"}, {"id": "u2"}, "pro", "year")["taxes"][0]["name"] == "IGST 18%"
    abroad = invoices.make({**PAY, "id": "p4", "international": True}, {"id": "u3"}, "pro", "month")
    assert abroad["supply"] == "Export (IGST paid)" and abroad["place_of_supply"] == "Outside India"
    invoices.save_seller({**SELLER, "lut_arn": "AD270326012345X"})
    lut = invoices.make({**PAY, "id": "p5", "international": True}, {"id": "u3"}, "pro", "month")
    assert lut["supply"] == "Export (zero-rated)" and lut["taxes"][0]["amount"] == 0 and "LUT" in lut["note"]
    invoices.save_seller({**SELLER, "gstin": "", "state": "27"})
    plain = invoices.make({**PAY, "id": "p6"}, {"id": "u1"}, "basic", "month")
    assert plain["taxes"] == [] and "not registered" in plain["note"] and "Tax invoice" not in invoices.html(plain)


def test_details_are_checked(store):
    with pytest.raises(ValueError, match="GSTIN"):
        invoices.save_seller({**SELLER, "gstin": "123"})
    with pytest.raises(ValueError, match="not the state"):
        invoices.save_seller({**SELLER, "state": "29"})
    with pytest.raises(ValueError, match="GSTIN"):
        invoices.save_billing("u", {"gstin": "nope"})
    assert invoices.save_billing("u", {"country": "us", "state": "27"}) == {"name": "", "address": "", "state": "", "gstin": "", "country": "US"}


def test_a_charge_webhook_makes_the_invoice(store, monkeypatch):
    invoices.save_seller(SELLER)
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "w")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_inrB")
    monkeypatch.setattr(billing, "_client", SimpleNamespace(utility=SimpleNamespace(verify_webhook_signature=lambda *a: True)))
    monkeypatch.setattr(billing.db, "profile_by_subscription", lambda sid: {"id": "u9", "email": "x@y.z"})
    monkeypatch.setattr(billing.db, "update_profile", lambda *a, **k: None)
    body = {"event": "subscription.charged", "payload": {
        "subscription": {"entity": {"id": "sub_9", "plan_id": "plan_inrB", "notes": {"plan": "basic", "period": "month"}, "current_end": 1793000000}},
        "payment": {"entity": {**PAY, "id": "pay_9"}}}}
    billing.handle_webhook(json.dumps(body).encode(), "sig")
    billing.handle_webhook(json.dumps(body).encode(), "sig")                     # Razorpay retries: still one invoice
    mine = invoices.of_user("u9")
    assert len(mine) == 1 and mine[0]["payment_id"] == "pay_9" and "Basic plan, monthly" in mine[0]["item"]["description"]


def test_invoice_routes(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        c = w["client"]
        r = c.put("/admin/invoices/seller", headers=W.headers("admin-token"), json=SELLER)
        assert r.status_code == 200 and r.json()["seller"]["gstin"] == SELLER["gstin"]
        assert c.put("/admin/invoices/seller", headers=W.headers("pro-token"), json=SELLER).status_code == 403
        invoices.make(PAY, {"id": "u-pro", "email": "pro@example.com"}, "pro", "month")
        mine = c.get("/billing/invoices", headers=W.headers("pro-token")).json()
        assert mine["invoices"][0]["number"] == "SL/2026-27/0001" and "27" in mine["states"]
        page = c.get("/billing/invoices/2026-27/0001", headers=W.headers("pro-token"))
        assert page.status_code == 200 and "Tax invoice" in page.text and "CGST 9%" in page.text
        assert c.get("/billing/invoices/2026-27/0001", headers=W.headers("basic-token")).status_code == 404   # not theirs
        assert c.get("/billing/invoices/2026-27/0001", headers=W.headers("admin-token")).status_code == 200
        assert c.get("/admin/invoices?year=2026-27", headers=W.headers("admin-token")).json()["invoices"][0]["tax"] > 0
        assert c.put("/billing/details", headers=W.headers("pro-token"), json={"gstin": "x"}).status_code == 400
    finally:
        w["close"]()


def test_a_replayed_webhook_event_does_nothing(store, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "w")
    monkeypatch.setattr(billing, "_client", SimpleNamespace(utility=SimpleNamespace(verify_webhook_signature=lambda *a: True)))
    monkeypatch.setattr(billing.db, "profile_by_subscription", lambda sid: {"id": "u9", "razorpay_subscription_id": "sub_new"})
    acted = []
    monkeypatch.setattr(billing, "activate", lambda profile, sub: acted.append(sub["id"]))
    body = json.dumps({"event": "subscription.activated", "payload": {"subscription": {"entity": {"id": "sub_old"}}}}).encode()
    billing.handle_webhook(body, "sig", "evt_1")
    billing.handle_webhook(body, "sig", "evt_1")                                  # the same signed event, sent again
    billing.handle_webhook(body, "sig", "evt_2")
    assert acted == ["sub_old", "sub_old"]
