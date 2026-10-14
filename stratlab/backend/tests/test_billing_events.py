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
