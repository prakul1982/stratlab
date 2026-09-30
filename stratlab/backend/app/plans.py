"""Plan rules. Change limits and prices here only."""
from datetime import datetime, timedelta, timezone

PLANS = {
    "free": {
        "name": "Free", "price": 0, "price_year": 0,
        "backtests_per_month": 5,
        "ai_builds_per_month": 10,
        "live_limit": 1,              # only during the trial
        "live_trial_days": 5,         # Indian trading days (no weekends or holidays), counted from the first start
        "group_size": 10,             # instruments in one group test
        "features": set(),
    },
    "basic": {
        "name": "Basic", "price": 999, "price_year": 9990,
        "backtests_per_month": 50,
        "ai_builds_per_month": 100,
        "live_limit": 2,
        "live_trial_days": None,
        "group_size": 25,
        "features": {"group_live", "options", "daily_report"},
    },
    "pro": {
        "name": "Pro", "price": 2999, "price_year": 29990,
        "backtests_per_month": None,  # unlimited
        "ai_builds_per_month": None,  # unlimited (a daily safety cap still applies)
        "live_limit": 10,
        "live_trial_days": None,
        "group_size": 50,
        # pro_features: advanced indicators and Indian F&O
        "features": {"group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report", "export", "pro_features",
                     "scans", "filings"},
    },
}
FEATURES = ("group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report", "export", "pro_features",
            "scans", "filings")
# the smallest plan with each feature, for upgrade messages
FEATURE_PLAN = {f: next(p for p in ("free", "basic", "pro") if f in PLANS[p]["features"] or p == "pro") for f in FEATURES}

BASIC_REFS = {"price", "sma", "ema", "rsi", "num"}
PRO_REFS = BASIC_REFS | {
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_mid", "bb_lower",
    "vwap", "supertrend", "stage",
}

GRACE = timedelta(days=1)


def payments_live() -> bool:
    """People can actually buy a plan: the Razorpay keys and both monthly plan IDs are set. Until then every
    feature stays open, so setting only the keys never locks people out of features they can't yet buy."""
    from . import billing
    return billing.enabled()


def allows(plan: str, feature: str) -> bool:
    """Paid features are open to everyone until payments go live: nobody can buy a plan yet,
    so gating them would just hide them."""
    return feature in PLANS[plan]["features"] or not payments_live()


def has_pro_features(plan: str) -> bool:
    """Advanced indicators and Indian F&O."""
    return allows(plan, "pro_features")


def group_size(plan: str) -> int:
    return PLANS[plan]["group_size"] if payments_live() else PLANS["pro"]["group_size"]


def plan_info(plan: str) -> dict:
    info = {k: v for k, v in PLANS[plan].items() if k != "features"}
    return {**info, "group_size": group_size(plan), "pro_features": has_pro_features(plan),
            "features": {f: allows(plan, f) for f in FEATURES}}


def public_plans() -> dict:
    """What each plan includes, for the Plans page (independent of early access)."""
    return {k: {**{x: v for x, v in p.items() if x != "features"}, "features": sorted(p["features"])} for k, p in PLANS.items()}


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

# ---------- launch offer: everyone gets Pro until a date the admin sets ----------
PROMO_KEY = "promo:free_until"
PROMO_TTL = 30.0
_promo: dict = {"read_at": 0.0, "until": None}


def promo_until() -> datetime | None:
    """When the free-for-everyone offer ends, or None when there isn't one. Read from the database every 30 s."""
    import time
    from . import db
    if time.monotonic() - _promo["read_at"] > PROMO_TTL:
        try:
            raw = db.get_setting(PROMO_KEY)
            _promo["until"] = _dt(raw) if raw else None
        except Exception:
            pass   # keep the last known value if the database blips
        _promo["read_at"] = time.monotonic()
    return _promo["until"]


def promo_active(now: datetime | None = None) -> bool:
    until = promo_until()
    return bool(until and (now or datetime.now(timezone.utc)) < until)


def set_promo(days: int | None) -> datetime | None:
    """Start the offer now for `days` days, or end it (None)."""
    from . import db
    if days:
        until = datetime.now(timezone.utc) + timedelta(days=days)
        db.set_setting(PROMO_KEY, until.isoformat())
    else:
        until = None
        db.delete_setting(PROMO_KEY)
    _promo.update(read_at=0.0, until=until)
    return until


def access_plan(profile: dict) -> str:
    """What the user can use right now: Pro for everyone during the launch offer, else what they pay for."""
    return "pro" if promo_active() else effective_plan(profile)


def trial_end(started: datetime, days: int) -> datetime:
    """Midnight (India time) after the `days`-th Indian trading day, counting the start day if it is one.
    Weekends and exchange holidays don't count: started on a Saturday, it runs to the end of the fifth
    trading day after."""
    from .data.calendar import is_trading_day
    d = started.astimezone(IST).date()
    left = days
    while True:
        if is_trading_day("IN", d):
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
