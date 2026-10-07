"""Owner-only admin: who's signed up, what they use, and granting plans by hand.

Access is by Google account: verified emails listed in ADMIN_EMAILS. (The old ?key= admin URLs are gone.)"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException

from . import db, referrals
from .auth import current_profile
from .config import settings
from .plans import PLANS, effective_plan


def admin_emails() -> set[str]:
    return {e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()}


def is_admin(profile: dict) -> bool:
    return bool(profile.get("_email_verified")) and (profile.get("email") or "").strip().lower() in admin_emails()


def admin_profile(profile=Depends(current_profile)) -> dict:
    if not is_admin(profile):
        raise HTTPException(403, {"code": "not_admin", "message": "This page is only for the site owner."})
    return profile


def _usage_since(since_iso: str) -> dict[str, Counter]:
    """usage_events since a time, as {user_id: Counter(kind)}."""
    rows = (db.sb().table("usage_events").select("user_id,kind").gte("created_at", since_iso)
            .limit(50000).execute().data)
    out: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        out[r["user_id"]][r["kind"]] += 1
    return out


def users(q: str, month_start: str, limit: int = 200, plan: str | None = None) -> list[dict]:
    """The newest `limit` users: those whose email contains `q`, and on `plan` when given (the plan they have now, so
    a paid plan that ended counts as Free)."""
    query = db.sb().table("profiles").select(
        "id,email,plan,plan_status,current_period_end,razorpay_subscription_id,created_at")
    if q:
        query = query.ilike("email", f"%{q.strip()}%")
    if plan in ("basic", "pro"):
        query = query.eq("plan", plan)              # narrowed in the database; an ended plan is dropped below
    rows = query.order("created_at", desc=True).limit(100000 if plan in PLANS else limit).execute().data
    if plan in PLANS:
        rows = [r for r in rows if effective_plan(r) == plan][:limit]
    usage = _usage_since(month_start)
    try:
        invited = referrals.counts()
    except Exception as e:           # invite counts are extra: the list still shows without them
        print("admin users: invite counts failed:", str(e)[:160])
        invited = {}
    try:
        from . import invite_rewards
        months = invite_rewards.months_by_user()
    except Exception as e:           # the same: extra
        print("admin users: invite rewards failed:", str(e)[:160])
        months = {}
    return [{
        "id": r["id"], "email": r.get("email"), "created_at": r.get("created_at"),
        "plan": effective_plan(r), "plan_set": r.get("plan"), "plan_status": r.get("plan_status"),
        "plan_until": r.get("current_period_end"), "paying": bool(r.get("razorpay_subscription_id")),
        "experiments": usage[r["id"]]["backtest"], "ai_builds": usage[r["id"]]["ai"], "referrals": invited.get(r["id"], 0),
        "free_months": months.get(r["id"], 0),
    } for r in rows]


def stats(month_start: str) -> dict:
    rows = db.sb().table("profiles").select("plan,plan_status,current_period_end,created_at,razorpay_subscription_id").limit(100000).execute().data
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    plans = Counter(effective_plan(r) for r in rows)
    # on a paid plan by paying (a subscription), or given by the owner by hand: Overview tells them apart
    paying = Counter(effective_plan(r) for r in rows if r.get("razorpay_subscription_id"))
    new = sum(1 for r in rows if r.get("created_at") and datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= week_ago)
    usage = Counter()
    for c in _usage_since(month_start).values():
        usage.update(c)
    return {"users": len(rows), "plans": {p: plans.get(p, 0) for p in PLANS}, "new_7d": new,
            "paying": {p: paying.get(p, 0) for p in ("basic", "pro")},
            "given": {p: plans.get(p, 0) - paying.get(p, 0) for p in ("basic", "pro")},
            "experiments_month": usage["backtest"], "ai_month": usage["ai"]}


def week_stats(since: datetime) -> dict:
    """Users joined since a time, everyone so far, paid users by plan, and experiments and AI builds since then."""
    rows = db.sb().table("profiles").select("plan,plan_status,current_period_end,created_at").limit(100000).execute().data
    plans = Counter(effective_plan(r) for r in rows)
    new = sum(1 for r in rows if r.get("created_at") and datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= since)
    usage = Counter()
    for c in _usage_since(since.astimezone(timezone.utc).isoformat()).values():
        usage.update(c)
    return {"users": len(rows), "new": new, "paid": {p: plans[p] for p in PLANS if p != "free" and plans[p]},
            "experiments": usage["backtest"], "ai": usage["ai"]}


def set_plan(user_id: str, plan: str, days: int | None) -> dict:
    """Grant a plan by hand. Paid plans run for `days` (or with no end); "free" clears it."""
    if plan not in PLANS:
        raise HTTPException(400, {"code": "bad_plan", "message": "Unknown plan."})
    if plan == "free":
        fields = {"plan": "free", "plan_status": None, "current_period_end": None, "cancel_at_period_end": False}
    else:
        until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat() if days else None
        fields = {"plan": plan, "plan_status": "active", "current_period_end": until, "cancel_at_period_end": False}
    row = db.update_profile(user_id, **fields)
    if row is None:
        raise HTTPException(404, {"code": "no_user", "message": "No user with that ID."})
    return row
