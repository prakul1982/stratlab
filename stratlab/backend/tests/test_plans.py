from datetime import datetime, timedelta, timezone


from app.plans import IST, effective_plan, trial_end, trial_state

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
    assert trial_state({"live_trial_started_at": (NOW - timedelta(hours=25)).isoformat()})["active"] is True
    assert trial_state({"live_trial_started_at": (NOW - timedelta(days=20)).isoformat()})["active"] is False   # 5 market days, whatever weekends and holidays fall between


def test_trial_counts_market_days():
    # Wednesday 24 Sep 2025 10:00 IST: Wed, Thu, Fri, Mon, Tue → ends at midnight after Tuesday 30 Sep
    assert trial_end(datetime(2025, 9, 24, 10, 0, tzinfo=IST), 5) == datetime(2025, 10, 1, tzinfo=IST)
    # Saturday: the weekend doesn't count, and neither does Thursday 2 Oct (Gandhi Jayanti, markets shut):
    # Mon 29, Tue 30, Wed 1, Fri 3, Mon 6 → ends at midnight after Monday 6 Oct
    assert trial_end(datetime(2025, 9, 27, 10, 0, tzinfo=IST), 5) == datetime(2025, 10, 7, tzinfo=IST)
    # Monday late at night still counts Monday as day one
    assert trial_end(datetime(2025, 9, 22, 23, 0, tzinfo=IST), 5) == datetime(2025, 9, 27, tzinfo=IST)


def test_each_plan_gets_what_pricing_lists_payments_or_not(monkeypatch):
    """The owner's decision (7 Oct): plans gate from day one, whether or not a plan can be bought yet. (This test used
    to check that everything was open until payments went live.)"""
    from app.config import settings
    from app.plans import decks, deepdives, has_fno, has_indicators, plan_info
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "")
    info = plan_info("free")
    assert not has_indicators("free") and not has_fno("free") and not info["indicators"] and not any(info["features"].values())
    assert deepdives("free") == 2 and decks("free") == 1 and info["deepdives_per_month"] == 2
    assert info["backtests_per_month"] == 10
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "")
    assert not has_fno("free") and deepdives("free") == 2   # keys alone change nothing either
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")
    assert not has_indicators("free") and has_indicators("basic") and not has_fno("basic") and has_fno("pro")
    assert (deepdives("free"), decks("free"), deepdives("basic"), decks("basic")) == (2, 1, 15, 5)
