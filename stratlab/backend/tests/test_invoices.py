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


def test_gst_is_backed_out_of_the_new_inclusive_prices(store):
    """Rupee prices include GST: the invoice shows the taxable value and the 18% inside the amount paid, and they add
    up to it to the paisa (CGST and SGST split it, halves rounding up)."""
    assert invoices.backed_out(499) == (422.88, 76.12) and invoices.backed_out(1499) == (1270.34, 228.66)
    assert invoices.backed_out(4990) == (4228.81, 761.19) and invoices.backed_out(14990) == (12703.39, 2286.61)
    invoices.save_seller(SELLER)
    rows = {}
    for n, rupees in enumerate((499, 1499, 4990, 14990)):
        inv = invoices.make({**PAY, "id": f"pn{n}", "amount": rupees * 100}, {"id": "u1"}, "basic", "month")
        taxes = [t["amount"] for t in inv["taxes"]]
        assert inv["total"] == rupees and round(inv["item"]["taxable"] + sum(taxes), 2) == rupees
        rows[rupees] = (inv["item"]["taxable"], taxes)
    assert rows[499] == (422.88, [38.06, 38.06]) and rows[1499] == (1270.34, [114.33, 114.33])
    assert rows[4990] == (4228.81, [380.6, 380.59])                  # 761.19 split: the odd paisa goes to CGST
    assert rows[14990] == (12703.39, [1143.31, 1143.3])
    invoices.save_billing("u2", {"state": "29", "country": "IN"})        # another state: one IGST line, the same 18%
    other = invoices.make({**PAY, "id": "pn9", "amount": 149900}, {"id": "u2"}, "pro", "month")
    assert other["taxes"] == [{"name": "IGST 18%", "rate": 18, "amount": 228.66}] and other["item"]["taxable"] == 1270.34
    old = invoices.make({**PAY, "id": "pn10"}, {"id": "u1"}, "basic", "month")   # an old ₹999 subscription renewing
    assert old["item"]["taxable"] == 846.61 and sum(t["amount"] for t in old["taxes"]) == 152.39


def test_export_invoices_are_unchanged(store):
    """Abroad: zero-rated under the LUT (no GST in the amount), whatever the currency."""
    invoices.save_seller({**SELLER, "lut_arn": "AD270326012345X"})
    usd = invoices.make({**PAY, "id": "px1", "amount": 800, "currency": "USD", "international": True}, {"id": "u3"}, "basic", "month")
    assert usd["supply"] == "Export (zero-rated)" and usd["total"] == 8 and usd["item"]["taxable"] == 8
    assert usd["taxes"] == [{"name": "IGST 0%", "rate": 0, "amount": 0.0}] and "$8.00" in invoices.html(usd)


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
        assert page.headers["content-security-policy"] == invoices.CSP          # its own, not the guard's script-free one
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


_ids = __import__("itertools").count()


def _webhook(monkeypatch, profile, sub, event="subscription.activated", payment=None):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "w")
    monkeypatch.setattr(billing, "_client", SimpleNamespace(utility=SimpleNamespace(verify_webhook_signature=lambda *a: True)))
    monkeypatch.setattr(billing.db, "profile_by_subscription", lambda sid: profile)
    acted, made = [], []
    monkeypatch.setattr(billing, "activate", lambda p, s: acted.append(s["id"]))
    monkeypatch.setattr(billing, "invoice_for", lambda p, s, pay: made.append(pay))
    monkeypatch.setattr(billing.invite_rewards, "safe_paid", lambda *a: None)
    body = {"event": event, "payload": {"subscription": {"entity": sub}, "payment": {"entity": payment or PAY}}}
    billing.handle_webhook(json.dumps(body).encode(), "sig", f"evt_{next(_ids)}")      # each call its own event
    return acted, made


def test_a_late_webhook_for_an_old_subscription_keeps_the_plan(store, monkeypatch):
    now = {"id": "u", "plan_status": "active", "razorpay_subscription_id": "sub_B"}
    acted, made = _webhook(monkeypatch, now, {"id": "sub_A"}, "subscription.charged")
    assert acted == [] and len(made) == 1                                      # no plan change, the payment is still invoiced
    assert _webhook(monkeypatch, now, {"id": "sub_C"}, "subscription.activated")[0] == []
    assert _webhook(monkeypatch, {**now, "pending_subscription_id": "sub_C"}, {"id": "sub_C"})[0] == ["sub_C"]   # the checkout in progress
    assert _webhook(monkeypatch, now, {"id": "sub_B"})[0] == ["sub_B"]         # the current one
    assert _webhook(monkeypatch, {"id": "u", "plan_status": "free"}, {"id": "sub_A"})[0] == ["sub_A"]       # paid, nothing active
    assert _webhook(monkeypatch, {"id": "u"}, {"id": "sub_A", "status": "cancelled"})[0] == []              # an ended one


def test_a_gstin_fills_or_must_match_the_state(store):
    assert invoices.save_billing("u", {"gstin": "27ABCDE1234F1Z5"})["state"] == "27"
    assert invoices.save_billing("u", {"gstin": "27ABCDE1234F1Z5", "state": "27"})["state"] == "27"
    with pytest.raises(ValueError, match="not the state chosen"):
        invoices.save_billing("u", {"gstin": "27ABCDE1234F1Z5", "state": "29"})


def test_a_payer_abroad_saved_as_india_gets_an_export_invoice(store):
    invoices.save_seller(SELLER)
    invoices.save_billing("u5", {"name": "Zed", "country": "IN"})
    abroad = invoices.make({**PAY, "id": "p5", "international": True}, {"id": "u5"}, "pro", "month")
    assert abroad["buyer"]["country"] == "XX" and abroad["supply"] == "Export (IGST paid)"
    invoices.save_billing("u6", {"name": "Acme", "state": "29", "country": "IN"})
    kept = invoices.make({**PAY, "id": "p6", "international": True}, {"id": "u6"}, "pro", "month")
    assert kept["buyer"]["country"] == "IN"                                     # an Indian business keeps India


def test_a_subscription_is_charged_in_the_currency_plans_showed(monkeypatch):
    from app import pricing
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "k")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "s")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "inr_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "inr_p")
    monkeypatch.setattr(pricing, "table", lambda: {"USD": {"plan_basic": "usd_b", "plan_pro": ""},
                                                   "EUR": {"plan_basic": "eur_b", "plan_pro": "eur_p"}})
    made = []
    monkeypatch.setattr(billing, "_client", SimpleNamespace(subscription=SimpleNamespace(create=lambda d: made.append(d) or {"id": "s"})))
    monkeypatch.setattr(billing.db, "update_profile", lambda *a, **k: None)
    assert billing.create_subscription({"id": "u"}, "basic", "month", "USD")["currency"] == "INR"    # only one of the two exists
    assert made[-1]["plan_id"] == "inr_b"
    assert billing.create_subscription({"id": "u"}, "pro", "month", "EUR")["currency"] == "EUR"
    assert made[-1]["plan_id"] == "eur_p"


# ---------- a full refund or a lost chargeback ends the current plan ----------
def _reversal(store, monkeypatch, event, profile, mapping="default", invoice=None, fetched=None):
    """Runs a refund/dispute event; returns (profile updates, cancelled subscriptions, plan_ended sends)."""
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "w")
    cancelled, updates, ended = [], [], []
    monkeypatch.setattr(billing, "_client", SimpleNamespace(
        utility=SimpleNamespace(verify_webhook_signature=lambda *a: True),
        subscription=SimpleNamespace(cancel=lambda sid, d: cancelled.append((sid, d))),
        invoice=SimpleNamespace(fetch=lambda i: invoice or {}),
        payment=SimpleNamespace(fetch=lambda i: fetched or {})))
    if mapping == "default":
        store["payment-sub:pay_1"] = json.dumps({"sub": "sub_B", "user": "u"})
    monkeypatch.setattr(billing.db, "profile_by_subscription", lambda sid: profile if sid == profile.get("razorpay_subscription_id") else None)
    monkeypatch.setattr(billing.db, "update_profile", lambda uid, **f: updates.append(f))
    monkeypatch.setattr(billing.invite_rewards, "safe_refunded", lambda pid: None)
    monkeypatch.setattr(billing.lifecycle, "later", lambda fn, *a: ended.append(a))
    billing.handle_webhook(json.dumps(event).encode(), "sig", f"evt_{next(_ids)}")
    return updates, cancelled, ended


def _refund(name="refund.processed", amount=99900, **payment):
    return {"event": name, "payload": {"refund": {"entity": {"id": "rfnd_1", "payment_id": "pay_1", "amount": amount}},
                                       "payment": {"entity": {"id": "pay_1", "amount": 99900, **payment}}}}


NOW_PRO = {"id": "u", "plan": "pro", "plan_status": "active", "razorpay_subscription_id": "sub_B"}


def test_a_full_refund_of_the_current_payment_ends_the_plan(store, monkeypatch):
    updates, cancelled, ended = _reversal(store, monkeypatch, _refund(), NOW_PRO)
    assert cancelled == [("sub_B", {"cancel_at_cycle_end": 0})]
    assert updates == [{"plan": "free", "plan_status": "refunded", "cancel_at_period_end": False}]
    assert ended == [(NOW_PRO, "sub_B", "pro")]


def test_a_partial_refund_or_one_just_created_changes_nothing(store, monkeypatch):
    assert _reversal(store, monkeypatch, _refund(amount=50000), NOW_PRO) == ([], [], [])
    assert _reversal(store, monkeypatch, _refund("refund.created"), NOW_PRO) == ([], [], [])
    assert _reversal(store, monkeypatch, _refund("payment.dispute.created"), NOW_PRO) == ([], [], [])


def test_a_refund_of_an_old_subscriptions_payment_keeps_the_current_plan(store, monkeypatch):
    store["payment-sub:pay_1"] = json.dumps({"sub": "sub_A", "user": "u"})
    assert _reversal(store, monkeypatch, _refund(), NOW_PRO, mapping="own") == ([], [], [])


def test_a_lost_dispute_ends_the_plan(store, monkeypatch):
    event = {"event": "payment.dispute.lost", "payload": {"dispute": {"entity": {"id": "disp_1", "payment_id": "pay_1"}}}}
    updates, cancelled, ended = _reversal(store, monkeypatch, event, {**NOW_PRO, "plan": "basic"})
    assert cancelled == [("sub_B", {"cancel_at_cycle_end": 0})] and updates[0]["plan_status"] == "refunded"
    assert ended[0][2] == "basic"


def test_without_a_saved_mapping_the_invoice_finds_the_subscription(store, monkeypatch):
    event = _refund()
    event["payload"]["payment"]["entity"]["invoice_id"] = "inv_1"
    updates, cancelled, _ = _reversal(store, monkeypatch, event, NOW_PRO, mapping="none", invoice={"subscription_id": "sub_B"})
    assert cancelled == [("sub_B", {"cancel_at_cycle_end": 0})] and updates[0]["plan"] == "free"
    # nothing to go on: the webhook still succeeds and the plan stays
    assert _reversal(store, monkeypatch, _refund(), NOW_PRO, mapping="none") == ([], [], [])


def test_the_cancelled_webhook_after_a_refund_changes_nothing_more(store, monkeypatch):
    refunded = {"id": "u", "plan": "free", "plan_status": "refunded", "razorpay_subscription_id": "sub_B"}
    done = []
    monkeypatch.setattr(billing.db, "update_profile", lambda *a, **k: done.append(k))
    _webhook(monkeypatch, refunded, {"id": "sub_B", "status": "cancelled"}, "subscription.cancelled")
    assert done == []


def test_a_real_payment_saves_which_subscription_it_paid_for(store, monkeypatch):
    invoices.save_seller(SELLER)
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_inrB")
    monkeypatch.setattr(billing.lifecycle, "later", lambda *a: None)
    monkeypatch.setattr(billing.product_analytics, "payment_completed", lambda *a: None)
    billing.invoice_for({"id": "u7"}, {"id": "sub_7", "plan_id": "plan_inrB", "notes": {}}, {**PAY, "id": "pay_7"})
    assert json.loads(store["payment-sub:pay_7"]) == {"sub": "sub_7", "user": "u7"}
