"""Owner-only admin: who's signed up, what they use, and granting plans by hand.

Access is by Google account: emails listed in ADMIN_EMAILS. The older ?key= admin URLs still work."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException

from . import db
from .auth import current_profile
from .config import settings
from .plans import PLANS, effective_plan


def admin_emails() -> set[str]:
    return {e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()}


def is_admin(profile: dict) -> bool:
    return (profile.get("email") or "").strip().lower() in admin_emails()


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


def users(q: str, month_start: str, limit: int = 200) -> list[dict]:
    query = db.sb().table("profiles").select(
        "id,email,plan,plan_status,current_period_end,razorpay_subscription_id,created_at")
    if q:
        query = query.ilike("email", f"%{q.strip()}%")
    rows = query.order("created_at", desc=True).limit(limit).execute().data
    usage = _usage_since(month_start)
    return [{
        "id": r["id"], "email": r.get("email"), "created_at": r.get("created_at"),
        "plan": effective_plan(r), "plan_set": r.get("plan"), "plan_status": r.get("plan_status"),
        "plan_until": r.get("current_period_end"), "paying": bool(r.get("razorpay_subscription_id")),
        "experiments": usage[r["id"]]["backtest"], "ai_builds": usage[r["id"]]["ai"],
    } for r in rows]


def stats(month_start: str) -> dict:
    rows = db.sb().table("profiles").select("plan,plan_status,current_period_end,created_at").limit(100000).execute().data
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    plans = Counter(effective_plan(r) for r in rows)
    new = sum(1 for r in rows if r.get("created_at") and datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= week_ago)
    usage = Counter()
    for c in _usage_since(month_start).values():
        usage.update(c)
    return {"users": len(rows), "plans": {p: plans.get(p, 0) for p in PLANS}, "new_7d": new,
            "experiments_month": usage["backtest"], "ai_month": usage["ai"]}


def set_plan(user_id: str, plan: str, days: int | None) -> dict:
    """Grant a plan by hand. Paid plans run for `days` (or with no end); "free" clears it."""
    if plan not in PLANS:
        raise HTTPException(400, {"code": "bad_plan", "message": "Unknown plan."})
    if plan == "free":
        fields = {"plan": "free", "plan_status": None, "current_period_end": None, "cancel_at_period_end": False}
    else:
        until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat() if days else None
        fields = {"plan": plan, "plan_status": "active", "current_period_end": until, "cancel_at_period_end": False}
    return db.update_profile(user_id, **fields)
