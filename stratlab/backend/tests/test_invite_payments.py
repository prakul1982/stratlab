"""Invite rewards paid for by a friend's first payment: after the referrer's 2 use-based months a year, a friend who
subscribes earns them a month (2 a year), then 25% of a month as 8 days (8 a year); one reward per friend; a friend
waiting to subscribe who pays within 90 days; paying without the 3 days; refunds and disputes within 7 days taking it
back; and the Razorpay webhook and checkout paths that bring the payment."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import billing, db, invite_rewards as R, lifecycle, plans, referrals
from app.config import settings
from tests import world as W
from tests.fake_db import headers
from tests.test_invite_rewards import DAY, NOW, active, invite, user

_n = [0]


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    monkeypatch.setattr(lifecycle, "BACKGROUND", False)
    plans._promo.update(read_at=0.0, until=None)
    yield world
    plans.forget_free_basic()
    world["close"]()


def payment(at=NOW, amount=29900, status="captured", **more):
    _n[0] += 1
    return {"id": f"pay_{_n[0]}", "amount": amount, "currency": "INR", "status": status, "amount_refunded": 0,
            "created_at": int(at.timestamp()), **more}


def pays(uid, at=NOW, **more):
    p = payment(at, **more)
    return R.paid(referrals._profile(uid), p, at), p


def friends(n, start=NOW, use=True, prefix="u-f"):
    """`n` friends join a day apart from `start`; with `use`, each becomes active."""
    for i in range(n):
        day = start + i * DAY
        invite("u-ref", f"{prefix}{i}", now=day)
        if use:
            active(f"{prefix}{i}", start=day)


def year(now=NOW + 30 * DAY):
    return R.this_year("u-ref", now)


def days_left(uid, now=NOW):
    have = plans.free_basic(uid)
    return have["banked"] + ((have["until"] - now).days if have["until"] else 0)


# ---------- counting ----------
def test_after_2_use_based_months_a_friend_waits_and_earns_a_month_when_they_pay(w):
    user("u-ref")
    friends(3)
    assert R.row("u-f2")["referrer_pending"] is True and year()["waiting_to_subscribe"] == 1
    assert pays("u-f2", NOW + 20 * DAY)[0] == "given"
    r = R.row("u-f2")
    assert R.kind_of(r) == "payment" and r["referrer_pending"] is False and r["referrer_days"] == 30
    assert year() == {"use": 2, "payment": 1, "extra": 0, "waiting_to_subscribe": 0}
    assert R.months_earned("u-ref")["referrer"] == 3
    assert R.months_earned("u-f2")["newcomer"] == 1                # the friend's own month is unchanged


def test_2_payment_months_then_25_percent_credits_capped_at_8_a_year(w):
    user("u-ref")
    friends(2)                                                     # the 2 use-based months
    friends(12, start=NOW + 2 * DAY, use=False, prefix="u-p")
    before = days_left("u-ref")
    out = [pays(f"u-p{i}", NOW + (3 + i) * DAY)[0] for i in range(12)]
    assert out == ["given"] * 10 + ["recorded"] * 2
    kinds = [R.kind_of(R.row(f"u-p{i}")) for i in range(12)]
    assert kinds == ["payment"] * 2 + ["extra"] * 8 + [None, None]
    assert all(R.row(f"u-p{i}").get("capped") for i in (10, 11))
    assert R.row("u-p2")["referrer_days"] == R.EXTRA_DAYS == 8
    assert days_left("u-ref") - before == 2 * 30 + 8 * 8
    assert year(NOW + 20 * DAY) == {"use": 2, "payment": 2, "extra": 8, "waiting_to_subscribe": 0}
    assert R.months_earned("u-ref")["referrer"] == 4               # an extra credit isn't a month


def test_the_percentage_is_one_constant(w, monkeypatch):
    assert R.INVITE_EXTRA_PCT == 25 and R.EXTRA_DAYS == round(30 * 25 / 100 + 0.01)
    user("u-ref")
    monkeypatch.setattr(R, "EXTRA_DAYS", int(R.MONTH_DAYS * 50 / 100))
    friends(5, use=False)
    for i in range(3):
        pays(f"u-f{i}", NOW + 6 * DAY)
    assert R.row("u-f2")["kind"] == "extra" and R.row("u-f2")["referrer_days"] == 15


def test_a_paying_friend_before_the_3_days_still_counts_and_is_never_rewarded_twice(w):
    user("u-ref")
    invite("u-ref", "u-a")
    assert pays("u-a", NOW + DAY)[0] == "given"
    assert R.kind_of(R.row("u-a")) == "payment" and R.row("u-a")["status"] == "waiting"
    active("u-a", start=NOW + 2 * DAY)                             # then becomes active: the friend's month only
    r = R.row("u-a")
    assert r["status"] == "given" and r["newcomer_months"] == 1 and r["referrer_months"] == 1 and r["kind"] == "payment"
    assert year() == {"use": 0, "payment": 1, "extra": 0, "waiting_to_subscribe": 0}
    assert pays("u-a", NOW + 40 * DAY)[0] == "already"             # a second payment counts for nothing
    assert R.months_earned("u-ref")["referrer"] == 1


def test_a_friend_rewarded_by_use_earns_nothing_more_when_they_pay(w):
    user("u-ref")
    friends(1)
    assert R.kind_of(R.row("u-f0")) == "use"
    assert pays("u-f0", NOW + 5 * DAY)[0] == "recorded"
    assert year() == {"use": 1, "payment": 0, "extra": 0, "waiting_to_subscribe": 0}


def test_a_payment_more_than_90_days_after_joining_earns_nothing(w):
    user("u-ref")
    friends(3)
    assert pays("u-f2", NOW + 95 * DAY)[0] == "recorded"
    assert R.kind_of(R.row("u-f2")) is None and R.row("u-f2")["referrer_pending"] is False
    assert R.this_year("u-ref", NOW + 95 * DAY)["waiting_to_subscribe"] == 0


def test_free_granted_or_failed_charges_dont_count(w):
    user("u-ref")
    invite("u-ref", "u-a")
    for bad in ({"amount": 0}, {"status": "authorized"}, {"status": "failed"}, {"amount_refunded": 100}, {"amount": "29900"}):
        assert R.paid(referrals._profile("u-a"), {**payment(), **bad}, NOW) == "not_paid"
    for bad in (None, {}, {"id": ""}, "pay_x"):
        assert R.paid(referrals._profile("u-a"), bad, NOW) == "not_paid"
    assert R.row("u-a").get("payment_id") is None
    user("u-solo")
    assert R.paid(referrals._profile("u-solo"), payment(), NOW) == "not_invited"


def test_same_person_rejected_and_held_invites_earn_nothing_by_payment(w):
    ref = user("u-ref", "jane@gmail.com")
    twin = user("u-twin", "ja.ne+x@gmail.com")
    assert R.joined(ref, twin, NOW) == "same_person"
    assert pays("u-twin")[0] == "recorded" and R.kind_of(R.row("u-twin")) is None
    for i in range(7):
        invite("u-ref", f"u-h{i}", now=NOW + timedelta(minutes=i))
    assert R.row("u-h6")["status"] == "review"
    assert pays("u-h6", NOW + DAY)[0] == "recorded"
    assert R.review("u-h6", True, NOW + 2 * DAY) == "waiting"      # approved: the payment already made now counts
    assert R.kind_of(R.row("u-h6")) == "payment"
    assert pays("u-h4", NOW + DAY)[0] == "given"                   # the 5th that day was never held
    assert R.review("u-h4", False) is None and R.review("u-h5", False) == "rejected"


# ---------- refunds ----------
def test_a_refund_within_7_days_takes_the_month_back(w):
    user("u-ref")
    invite("u-ref", "u-a")
    _, p = pays("u-a", NOW + DAY)
    assert days_left("u-ref", NOW + DAY) == 30
    assert R.refunded(p["id"], NOW + 5 * DAY) == "reversed"
    r = R.row("u-a")
    assert r["referrer_months"] == 0 and r["reversed_at"] and R.kind_of(r) is None
    assert plans.free_basic_until(referrals._profile("u-ref"), NOW + 5 * DAY) is None
    assert R.refunded(p["id"], NOW + 6 * DAY) == "already"
    active("u-a", start=NOW + 2 * DAY)                             # becoming active later earns the referrer nothing
    assert R.row("u-a")["referrer_months"] == 0 and R.row("u-a")["newcomer_months"] == 1
    assert year()["payment"] == 0


def test_a_refund_after_7_days_keeps_the_month_and_unknown_payments_are_ignored(w):
    user("u-ref")
    invite("u-ref", "u-a")
    _, p = pays("u-a", NOW + DAY)
    assert R.refunded(p["id"], NOW + 9 * DAY) == "kept" and R.kind_of(R.row("u-a")) == "payment"
    for bad in ("pay_unknown", "", None, 42):
        assert R.refunded(bad, NOW) == "none"


def test_a_refunded_extra_credit_takes_back_its_8_days(w):
    user("u-ref")
    friends(4, use=False)
    ps = [pays(f"u-f{i}", NOW + 5 * DAY)[1] for i in range(3)]
    before = days_left("u-ref", NOW + 5 * DAY)
    assert R.refunded(ps[2]["id"], NOW + 6 * DAY) == "reversed"
    assert before - days_left("u-ref", NOW + 5 * DAY) == 8
    assert year(NOW + 7 * DAY)["extra"] == 0
    assert pays("u-f3", NOW + 7 * DAY)[0] == "given" and R.row("u-f3")["kind"] == "extra"   # its slot is free again


def test_taking_back_never_goes_below_none(w):
    p = user("u-a")
    plans.add_free_basic(p, 10, NOW)
    assert plans.take_free_basic("u-a", 30, NOW)["until"] == NOW
    plans.add_free_basic(p, 0, NOW)
    db.update_profile("u-a", plan="pro", plan_status="active", current_period_end=(NOW + 40 * DAY).isoformat())
    plans.add_free_basic(referrals._profile("u-a"), 30, NOW)
    assert plans.take_free_basic("u-a", 30, NOW)["banked"] == 0


# ---------- the emails ----------
def test_the_referrer_is_told_how_they_earned(w, monkeypatch):
    from app import alerts
    sent = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None: sent.append((to, subject, text)))
    user("u-ref")
    friends(2)
    friends(3, start=NOW + 3 * DAY, use=False, prefix="u-p")
    for i in range(3):
        pays(f"u-p{i}", NOW + 6 * DAY)
    mine = [(s, t) for to, s, t in sent if to == "u-ref@example.com"]
    assert [s for s, _ in mine] == ["You've got a free month of StratLab Basic"] * 4 + ["You've got 8 extra days of StratLab Basic"]
    assert "has subscribed" in mine[2][1] and "25% off a month" in mine[4][1]
    assert all("for each of your first 2 friends who subscribe" in t for _, t in mine)


# ---------- the webhook and checkout ----------
def _post(c, event, event_id):
    body = json.dumps(event).encode()
    sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    return c.post("/billing/webhook", content=body, headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": event_id,
                                                              "Content-Type": "application/json"})


def _webhook(monkeypatch):
    for k, v in (("RAZORPAY_WEBHOOK_SECRET", "whsec"), ("RAZORPAY_KEY_ID", "rzp_test_x"), ("RAZORPAY_KEY_SECRET", "s"),
                 ("RAZORPAY_PLAN_BASIC", "plan_b"), ("RAZORPAY_PLAN_PRO", "plan_p")):
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(billing, "_client", None)


def _charged(uid, pay, sub="sub_1"):
    return {"event": "subscription.charged", "payload": {
        "subscription": {"entity": {"id": sub, "plan_id": "plan_b", "status": "active", "current_end": 1893456000,
                                    "notes": {"user_id": uid, "plan": "basic", "period": "month"}}},
        "payment": {"entity": pay}}}


def test_the_charge_webhook_rewards_the_referrer_once_and_a_refund_webhook_takes_it_back(w, monkeypatch):
    _webhook(monkeypatch)
    c = w["client"]
    user("u-ref")
    _new = datetime.now(timezone.utc)
    invite("u-ref", "u-a", now=_new - DAY, created=_new - DAY - timedelta(minutes=5))
    p = payment(_new)
    assert _post(c, _charged("u-a", p), "evt_1").json() == {"ok": True}
    r = R.row("u-a")
    assert R.kind_of(r) == "payment" and r["payment_id"] == p["id"]
    assert referrals._profile("u-a")["plan"] == "basic"             # the plan itself still switched on
    assert _post(c, _charged("u-a", p), "evt_1").status_code == 200   # a replay
    assert _post(c, _charged("u-a", payment(_new)), "evt_2").status_code == 200   # the next month's charge
    assert R.months_earned("u-ref")["referrer"] == 1
    refund = {"event": "refund.processed", "payload": {"refund": {"entity": {"id": "rfnd_1", "payment_id": p["id"]}},
                                                       "payment": {"entity": {**p, "status": "refunded"}}}}
    assert _post(c, refund, "evt_3").status_code == 200
    assert R.row("u-a")["reversed_at"] and R.months_earned("u-ref")["referrer"] == 0


def test_a_dispute_webhook_takes_it_back_and_odd_refund_events_do_nothing(w, monkeypatch):
    _webhook(monkeypatch)
    c = w["client"]
    user("u-ref")
    _new = datetime.now(timezone.utc)
    invite("u-ref", "u-a", now=_new - DAY, created=_new - DAY - timedelta(minutes=5))
    p = payment(_new)
    _post(c, _charged("u-a", p), "evt_1")
    for i, odd in enumerate(({"event": "refund.created"}, {"event": "refund.created", "payload": []},
                             {"event": "refund.created", "payload": {"refund": {"entity": "x"}}},
                             {"event": "payment.dispute.created", "payload": {"dispute": {"entity": {"payment_id": 5}}}})):
        assert _post(c, odd, f"evt_odd{i}").status_code == 200
    assert R.kind_of(R.row("u-a")) == "payment"
    dispute = {"event": "payment.dispute.created", "payload": {"dispute": {"entity": {"id": "disp_1", "payment_id": p["id"]}}}}
    assert _post(c, dispute, "evt_d").status_code == 200
    assert R.row("u-a")["reversed_at"]


def test_checkout_counts_a_captured_payment(w, monkeypatch):
    user("u-ref")
    _new = datetime.now(timezone.utc)
    invite("u-ref", "u-a", now=_new - DAY, created=_new - DAY - timedelta(minutes=5))
    p = payment(_new)
    sub = {"id": "sub_9", "plan_id": "plan_b", "notes": {"user_id": "u-a", "plan": "basic", "period": "month"}}
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(billing, "_client", SimpleNamespace(
        utility=SimpleNamespace(verify_subscription_payment_signature=lambda d: True),
        subscription=SimpleNamespace(fetch=lambda sid: sub), payment=SimpleNamespace(fetch=lambda pid: p)))
    billing.verify_checkout(referrals._profile("u-a"), p["id"], "sub_9", "abc123")
    assert R.kind_of(R.row("u-a")) == "payment"


def test_a_broken_reward_never_breaks_the_payment(w, monkeypatch):
    _webhook(monkeypatch)
    user("u-ref")
    _new = datetime.now(timezone.utc)
    invite("u-ref", "u-a", now=_new - DAY, created=_new - DAY - timedelta(minutes=5))

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(R, "paid", boom)
    monkeypatch.setattr(R, "refunded", boom)
    c = w["client"]
    assert _post(c, _charged("u-a", payment(_new)), "evt_1").status_code == 200
    assert referrals._profile("u-a")["plan"] == "basic"
    assert _post(c, {"event": "refund.created", "payload": {"refund": {"entity": {"payment_id": "pay_x"}}}}, "evt_2").status_code == 200


# ---------- what Account and Admin show ----------
def test_account_shows_this_years_counts_and_admin_shows_the_reward_type(w):
    c = w["client"]
    code = c.get("/me/referrals", headers=headers("pro-token")).json()["code"]
    now = datetime.now(timezone.utc)
    for i in range(4):
        uid = f"u-x{i}"
        user(uid, created=now - timedelta(hours=2))
        assert referrals.record(referrals._profile(uid), code, now - timedelta(hours=1)) == "recorded"
    for i in range(3):
        active(f"u-x{i}", start=now - timedelta(hours=1))
    assert R.paid(referrals._profile("u-x3"), payment(now), now) == "given"
    mine = c.get("/me/referrals", headers=headers("pro-token")).json()
    assert {k: mine[k] for k in ("use_months", "use_cap", "paid_months", "paid_cap", "extras", "extra_cap",
                                  "extra_pct", "extra_days", "waiting_to_subscribe", "joined", "months")} == {
        "use_months": 2, "use_cap": 2, "paid_months": 1, "paid_cap": 2, "extras": 0, "extra_cap": 8, "extra_pct": 25,
        "extra_days": 8, "waiting_to_subscribe": 1, "joined": 4, "months": 3}
    view = c.get("/admin/invite-rewards", headers=headers("admin-token")).json()
    shown = {r["newcomer"]: (r["reward"], r["reward_label"]) for r in view["given"]}
    assert shown["u-x3"] == ("payment", "Payment")
    assert sorted(v for k, v in shown.items() if k != "u-x3") == [
        ("pending_payment", "Waiting to subscribe"), ("use", "Use"), ("use", "Use")]
    assert view["waiting_to_subscribe"] == 1 and view["extras_given"] == 0
