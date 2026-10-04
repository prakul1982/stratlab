"""Plan rules. Change limits and prices here only."""
from datetime import datetime, timedelta, timezone

PLANS = {
    "free": {
        "name": "Free", "price": 0, "price_year": 0,
        "backtests_per_month": 10,
        "ai_builds_per_month": 10,
        "live_limit": 1,              # only during the trial
        "live_trial_days": 5,         # Indian trading days (no weekends or holidays), counted from the first start
        "group_size": 10,             # instruments in one group test
        "holdings": 30,               # stocks in My Holdings
        "stock_alerts": 5,            # active price and indicator alerts on stocks
        "screens": 2,                 # saved stock screens
        "deepdives_per_month": 2,     # companies opened in the deep dive (each counted once a month)
        "decks_per_month": 1,         # company slide decks (PowerPoint or PDF)
        "features": set(),
    },
    "basic": {
        # rupee prices include GST (invoices.py backs the 18% out)
        "name": "Basic", "price": 699, "price_year": 6999,
        "backtests_per_month": 100,
        "ai_builds_per_month": 100,
        "live_limit": 2,
        "live_trial_days": None,
        "group_size": 25,
        "holdings": 100,
        "stock_alerts": 25,
        "screens": 10,
        "deepdives_per_month": 15,
        "decks_per_month": 5,
        "features": {"indicators", "group_live", "options", "alerts", "daily_report", "newsletter", "scans", "filings",
                     "investor_home"},
    },
    "pro": {
        "name": "Pro", "price": 1999, "price_year": 19999,
        "backtests_per_month": None,  # unlimited
        "ai_builds_per_month": None,  # unlimited (a daily safety cap still applies)
        "live_limit": 10,
        "live_trial_days": None,
        "group_size": 50,
        "holdings": 300,
        "stock_alerts": 100,
        "screens": 25,
        "deepdives_per_month": None,  # unlimited (the daily cap on fresh AI reads still applies)
        "decks_per_month": None,
        "features": {"indicators", "fno", "group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report",
                     "export", "newsletter", "scans", "filings", "investor_home"},
    },
}
# indicators: every indicator beyond price, SMA, EMA and RSI; fno: Indian futures and options;
# newsletter: the daily editions of both newsletters (the weekly ones are for everyone);
# scans: the Stage 2 + Supertrend scan and its alert; filings: red flags for the whole watchlist and the evening alert
# (red flags on a single company page are for everyone)
FEATURES = ("indicators", "fno", "group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report", "export",
            "newsletter", "scans", "filings", "investor_home")
# the smallest plan with each feature, for upgrade messages
FEATURE_PLAN = {f: next(p for p in ("free", "basic", "pro") if f in PLANS[p]["features"] or p == "pro") for f in FEATURES}

BASIC_REFS = {"price", "sma", "ema", "rsi", "num"}      # every other indicator (MACD, Bollinger, VWAP…) is Basic and up

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


def has_indicators(plan: str) -> bool:
    """Every indicator beyond price, SMA, EMA and RSI (Basic and up)."""
    return allows(plan, "indicators")


def has_fno(plan: str) -> bool:
    """Indian futures and options (Pro)."""
    return allows(plan, "fno")


def bigger_plan(plan: str, key: str) -> str | None:
    """The name of the next plan up with a higher count limit `key` (None counts as unlimited), for upgrade messages;
    None when no plan goes higher."""
    have, order = PLANS[plan][key], ("free", "basic", "pro")
    for p in order[order.index(plan) + 1:]:
        cap = PLANS[p][key]
        if have is not None and (cap is None or cap > have):
            return PLANS[p]["name"]
    return None


def group_size(plan: str) -> int:
    return PLANS[plan]["group_size"] if payments_live() else PLANS["pro"]["group_size"]


def holdings_limit(plan: str) -> int:
    """How many stocks My Holdings keeps. Importing is for everyone; paid plans keep more."""
    return PLANS[plan]["holdings"] if payments_live() else PLANS["pro"]["holdings"]


def stock_alerts(plan: str) -> int:
    """How many stock alerts can be on at once."""
    return PLANS[plan]["stock_alerts"] if payments_live() else PLANS["pro"]["stock_alerts"]


def screens(plan: str) -> int:
    """How many stock screens can be saved."""
    return PLANS[plan]["screens"] if payments_live() else PLANS["pro"]["screens"]


def deepdives(plan: str) -> int | None:
    """How many companies a month the deep dive opens (None: unlimited). Each company counts once a month."""
    return PLANS[plan]["deepdives_per_month"] if payments_live() else PLANS["pro"]["deepdives_per_month"]


def decks(plan: str) -> int | None:
    """How many company decks a month (None: unlimited)."""
    return PLANS[plan]["decks_per_month"] if payments_live() else PLANS["pro"]["decks_per_month"]


def plan_info(plan: str) -> dict:
    info = {k: v for k, v in PLANS[plan].items() if k != "features"}
    return {**info, "group_size": group_size(plan), "holdings": holdings_limit(plan), "stock_alerts": stock_alerts(plan),
            "screens": screens(plan), "deepdives_per_month": deepdives(plan), "decks_per_month": decks(plan),
            "indicators": has_indicators(plan), "fno": has_fno(plan),
            "features": {f: allows(plan, f) for f in FEATURES}}


def public_plans() -> dict:
    """What each plan includes, for the Plans page (independent of early access)."""
    return {k: {**{x: v for x, v in p.items() if x != "features"}, "features": sorted(p["features"])} for k, p in PLANS.items()}


def _dt(v) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def effective_plan(profile: dict, now: datetime | None = None) -> str:
    """A paid plan only counts while the subscription is active and not past its period end (at `now`, else now)."""
    plan = profile.get("plan") or "free"
    if plan not in PLANS or plan == "free":
        return "free"
    if profile.get("plan_status") != "active":
        return "free"
    end = profile.get("current_period_end")
    if end and _dt(end) + GRACE < (now or datetime.now(timezone.utc)):
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


# ---------- free Basic time: earned by inviting friends (invite_rewards.py) ----------
FREE_KEY = "freebasic:"          # freebasic:<uid>: {"until": when free Basic ends, "banked": days kept for later}
FREE_TTL = 30.0
_free: dict = {"read_at": -1e9, "rows": {}}


def _free_rows() -> dict:
    """{uid: free Basic record} for everyone who has one. Read from the database every 30 s (only people who earned
    time are stored, so it's a short list)."""
    import json
    import time
    from . import db
    if time.monotonic() - _free["read_at"] > FREE_TTL:
        try:
            rows = {}
            for k, v in db.all_settings_with_prefix(FREE_KEY):
                try:
                    val = json.loads(v)
                except (ValueError, TypeError):
                    continue
                if isinstance(val, dict):
                    rows[k[len(FREE_KEY):]] = val
            _free["rows"] = rows
        except Exception:
            pass   # keep the last known rows if the database blips
        _free["read_at"] = time.monotonic()
    return _free["rows"]


def forget_free_basic():
    """Drop the copy so the next check reads the database (after a change, and between tests)."""
    _free.update(read_at=-1e9, rows={})


def free_basic(uid: str | None) -> dict:
    """{"until": datetime or None, "banked": days} for one user."""
    row = _free_rows().get(uid or "") or {}
    try:
        until = _dt(row["until"]) if row.get("until") else None
        if until and not until.tzinfo:
            until = until.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        until = None
    banked = row.get("banked")
    return {"until": until, "banked": banked if isinstance(banked, int) and 0 < banked < 100000 else 0}


def _save_free(uid: str, until: datetime | None, banked: int):
    import json
    from . import db
    db.set_setting(FREE_KEY + uid, json.dumps({"until": until.isoformat() if until else None, "banked": banked}))
    forget_free_basic()


def add_free_basic(profile: dict, days: int, now: datetime | None = None) -> dict:
    """Give `days` of free Basic. On Free it starts now, stacked after any free time still left; someone paying for
    Basic or Pro banks it instead, and it starts the first time they're seen on Free."""
    now = now or datetime.now(timezone.utc)
    uid = profile["id"]
    have = free_basic(uid)
    until, banked = have["until"], have["banked"]
    if effective_plan(profile, now) == "free":
        until = max(until or now, now) + timedelta(days=days)
    else:
        banked += days
    _save_free(uid, until, banked)
    return {"until": until, "banked": banked}


def free_basic_until(profile: dict, now: datetime | None = None) -> datetime | None:
    """When the user's free Basic ends, or None when they have none running. Banked days start here, the first time
    the user is on Free (their paid plan ended)."""
    now = now or datetime.now(timezone.utc)
    uid = profile.get("id")
    if not uid:
        return None
    have = free_basic(uid)
    until = have["until"]
    if have["banked"] and effective_plan(profile, now) == "free":
        until = max(until or now, now) + timedelta(days=have["banked"])
        try:
            _save_free(uid, until, 0)
        except Exception as e:      # still free Basic now; the bank is spent on the next check instead
            print("free basic: couldn't start banked days:", str(e)[:160])
    return until if until and now < until else None


def access_plan(profile: dict) -> str:
    """What the user can use right now: Pro for everyone during the launch offer, else what they pay for, or Basic
    while they have free Basic time (from inviting friends) and pay for less."""
    if promo_active():
        return "pro"
    plan = effective_plan(profile)
    if plan == "free":
        try:
            if free_basic_until(profile):
                return "basic"
        except Exception as e:      # free time is a bonus: a fault here never takes away anything else
            print("free basic check failed:", str(e)[:160])
    return plan


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
