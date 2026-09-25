"""Plan rules. Change limits and prices here only."""
from datetime import datetime, timedelta, timezone

PLANS = {
    "free": {
        "name": "Free", "price": 0,
        "backtests_per_month": 5,
        "ai_builds_per_month": 10,
        "live_limit": 1,              # only during the trial
        "live_trial_days": 5,         # market days (Mon–Fri), counted in India time from the first start
        "pro_features": False,
    },
    "basic": {
        "name": "Basic", "price": 1999,
        "backtests_per_month": 50,
        "ai_builds_per_month": 100,
        "live_limit": 1,
        "live_trial_days": None,
        "pro_features": False,
    },
    "pro": {
        "name": "Pro", "price": 4900,
        "backtests_per_month": None,  # unlimited
        "ai_builds_per_month": None,  # unlimited (a daily safety cap still applies)
        "live_limit": 5,
        "live_trial_days": None,
        "pro_features": True,         # advanced indicators, F&O, alerts, export
    },
}

BASIC_REFS = {"price", "sma", "ema", "rsi", "num"}
PRO_REFS = BASIC_REFS | {
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_mid", "bb_lower",
    "vwap", "supertrend",
}

GRACE = timedelta(days=1)


def payments_live() -> bool:
    """Razorpay keys are set, so people can actually buy Pro."""
    from .config import settings
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def has_pro_features(plan: str) -> bool:
    """Pro features (advanced indicators, F&O) are open to everyone until payments go live:
    nobody can buy Pro yet, so gating them would just hide them."""
    return PLANS[plan]["pro_features"] or not payments_live()


def plan_info(plan: str) -> dict:
    return {**PLANS[plan], "pro_features": has_pro_features(plan)}


def _dt(v) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def effective_plan(profile: dict) -> str:
    """A paid plan only counts while the subscription is active and not past its period end."""
    plan = profile.get("plan") or "free"
    if plan not in PLANS or plan == "free":
        return "free"
    if profile.get("plan_status") != "active":
        return "free"
    end = profile.get("current_period_end")
    if end and _dt(end) + GRACE < datetime.now(timezone.utc):
        return "free"
    return plan


IST = timezone(timedelta(hours=5, minutes=30))


def trial_end(started: datetime, days: int) -> datetime:
    """Midnight (India time) after the `days`-th weekday, counting the start day if it's a weekday.
    Started on a Saturday, the trial runs to the end of the following Friday."""
    d = started.astimezone(IST).date()
    left = days
    while True:
        if d.weekday() < 5:
            left -= 1
            if left == 0:
                break
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, tzinfo=IST) + timedelta(days=1)


def trial_state(profile: dict) -> dict:
    days = PLANS["free"]["live_trial_days"]
    started = profile.get("live_trial_started_at")
    if not started:
        return {"started": False, "active": False, "ends_at": None, "available": True, "days": days}
    ends = trial_end(_dt(started), days)
    active = datetime.now(timezone.utc) < ends
    return {"started": True, "active": active, "ends_at": ends.isoformat(), "available": active, "days": days}
