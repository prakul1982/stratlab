from datetime import datetime, timedelta, timezone

from app.plans import effective_plan, trial_state

NOW = datetime.now(timezone.utc)


def test_paid_plan_needs_active_status():
    assert effective_plan({"plan": "pro", "plan_status": "active"}) == "pro"
    assert effective_plan({"plan": "pro", "plan_status": "halted"}) == "free"
    assert effective_plan({"plan": "bogus", "plan_status": "active"}) == "free"


def test_paid_plan_lapses_after_period_end_plus_grace():
    ended = (NOW - timedelta(days=3)).isoformat()
    assert effective_plan({"plan": "basic", "plan_status": "active", "current_period_end": ended}) == "free"
    recent = (NOW - timedelta(hours=12)).isoformat()
    assert effective_plan({"plan": "basic", "plan_status": "active", "current_period_end": recent}) == "basic"


def test_trial_window():
    assert trial_state({})["available"] is True
    assert trial_state({"live_trial_started_at": (NOW - timedelta(hours=1)).isoformat()})["active"] is True
    assert trial_state({"live_trial_started_at": (NOW - timedelta(hours=25)).isoformat()})["active"] is False


def test_pro_features_are_open_until_payments_go_live(monkeypatch):
    from app.config import settings
    from app.plans import has_pro_features, plan_info
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    assert has_pro_features("free") and plan_info("free")["pro_features"] and plan_info("free")["backtests_per_month"] == 5
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    assert not has_pro_features("free") and not has_pro_features("basic") and has_pro_features("pro")
