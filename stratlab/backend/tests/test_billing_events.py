"""Webhook events that arrive late or out of order must not undo what a later event settled."""
from types import SimpleNamespace

from app import billing


def _patch(monkeypatch):
    saved = {}
    monkeypatch.setattr(billing.db, "update_profile", lambda uid, **kw: saved.update(kw))
    monkeypatch.setattr(billing, "_client", SimpleNamespace(subscription=SimpleNamespace(cancel=lambda *a: None)))
    return saved


def test_a_late_activated_event_does_not_revive_a_cancelled_subscription(monkeypatch):
    profile = {"id": "u", "plan": "free", "plan_status": "cancelled", "razorpay_subscription_id": "sub_1"}
    sub = {"id": "sub_1", "status": "active", "notes": {"plan": "pro"}}       # the payload's own snapshot, taken before the cancel
    assert billing._stale(profile, sub)
    assert billing._stale({**profile, "plan_status": "completed"}, sub)
    assert not billing._stale({**profile, "plan_status": "halted"}, sub)       # a halted one can recover when its retry is paid


def test_a_late_renewal_event_keeps_a_cancellation_to_period_end(monkeypatch):
    saved = _patch(monkeypatch)
    monkeypatch.setattr("app.admin.mark_granted", lambda *a: None)
    profile = {"id": "u", "plan": "pro", "plan_status": "active", "razorpay_subscription_id": "sub_1", "cancel_at_period_end": True}
    billing.activate(profile, {"id": "sub_1", "current_end": 1791000000, "notes": {"plan": "pro"}})
    assert saved["cancel_at_period_end"] is True
    billing.activate(profile, {"id": "sub_2", "current_end": 1791000000, "notes": {"plan": "basic"}})   # a new subscription starts clean
    assert saved["cancel_at_period_end"] is False


# ---------- acct4: an ended subscription never leaves its final state ----------
def _events(monkeypatch, profile: dict):
    """The profile as one stored row, and a function sending one subscription event for `sub_1` (or another id)."""
    monkeypatch.setattr(billing.db, "profile_by_subscription",
                        lambda sid: dict(profile) if profile.get("razorpay_subscription_id") == sid else None)
    monkeypatch.setattr(billing.db, "get_profile", lambda uid, *a: dict(profile))
    monkeypatch.setattr(billing.db, "update_profile", lambda uid, **kw: profile.update(kw) or dict(profile))
    monkeypatch.setattr(billing.lifecycle, "later", lambda *a, **k: None)
    monkeypatch.setattr("app.admin.mark_granted", lambda *a: None)
    monkeypatch.setattr(billing, "_client", SimpleNamespace(subscription=SimpleNamespace(cancel=lambda *a: None)))

    def send(name, status, sid="sub_1"):
        billing._act({"event": name, "payload": {"subscription": {"entity": {
            "id": sid, "status": status, "notes": {"user_id": "u", "plan": "pro"}, "current_end": 1793000000}}}})
    return send


def test_a_late_halted_event_after_the_cancel_cannot_bring_the_plan_back(monkeypatch):
    profile = {"id": "u", "plan": "pro", "plan_status": "active", "razorpay_subscription_id": "sub_1", "cancel_at_period_end": False}
    send = _events(monkeypatch, profile)
    send("subscription.cancelled", "cancelled")
    send("subscription.halted", "halted")              # Razorpay's retry of an earlier delivery
    assert profile["plan_status"] == "cancelled"
    send("subscription.activated", "active")           # later still, its snapshot from before the cancel
    assert (profile["plan"], profile["plan_status"]) == ("free", "cancelled")
    for final in ("completed", "expired", "refunded"):
        profile.update(plan="free", plan_status=final)
        send("subscription.paused", "paused")
        assert profile["plan_status"] == final


def test_a_halted_subscription_still_recovers_and_a_new_one_starts_fresh(monkeypatch):
    profile = {"id": "u", "plan": "pro", "plan_status": "active", "razorpay_subscription_id": "sub_1", "cancel_at_period_end": False}
    send = _events(monkeypatch, profile)
    send("subscription.halted", "halted")
    assert (profile["plan"], profile["plan_status"]) == ("free", "halted")
    send("subscription.charged", "active")             # the retried charge went through
    assert (profile["plan"], profile["plan_status"]) == ("pro", "active")
    send("subscription.cancelled", "cancelled")
    send("subscription.activated", "active", "sub_2")  # a new checkout after the cancel
    assert (profile["plan"], profile["plan_status"], profile["razorpay_subscription_id"]) == ("pro", "active", "sub_2")
