"""Owner-only admin: who's signed up, what they use, and granting plans by hand.

Access is by Google account: verified emails listed in ADMIN_EMAILS. (The old ?key= admin URLs are gone.)"""
import json
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException

from . import db, leader, referrals
from .auth import current_profile
from .config import settings
from .kite_service import IST
from .plans import PLANS, effective_plan


def admin_emails() -> set[str]:
    return {e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()}


def is_admin(profile: dict) -> bool:
    return bool(profile.get("_email_verified")) and (profile.get("email") or "").strip().lower() in admin_emails()


# Background jobs read profiles from the database, with no sign-in to prove the address. Sign-in records here the ids
# that Google proved an admin address for ({uid: email}); only the server writes app_settings, and a stored profile email
# alone proves nothing (it is whatever address created the account).
OWNERS_KEY = "admin_owner_ids"
OWNERS_TTL = 300.0
_owners: dict = {"until": 0.0, "map": {}}
_owners_lock = threading.Lock()


def forget_owners() -> None:
    with _owners_lock:
        _owners.update(until=0.0, map={})


def _owner_map() -> dict:
    with _owners_lock:
        if _owners["until"] > time.monotonic():
            return _owners["map"]
    try:
        got = db.json_value(db.get_setting(OWNERS_KEY), {})
        got, ttl = (got if isinstance(got, dict) else {}), OWNERS_TTL
    except Exception as e:                  # keep what was read before; try again soon
        print("owner ids read failed:", str(e)[:160])
        got, ttl = _owners["map"], 30.0
    with _owners_lock:
        _owners.update(until=time.monotonic() + ttl, map=got)
    return got


def remember_owner(profile: dict) -> None:
    """Record a signed-in admin's id (auth.current_profile calls this only after is_admin passed)."""
    if not is_admin(profile):
        return
    email = profile["email"].strip().lower()
    known = _owner_map()
    if known.get(profile["id"]) == email:
        return
    def add(raw):                          # compare-and-set: another server's owner id isn't lost
        d = db.json_value(raw, {})
        return None if d.get(profile["id"]) == email else json.dumps({**d, profile["id"]: email})
    known = db.json_value(db.update_setting(OWNERS_KEY, add), {})
    with _owners_lock:
        _owners.update(until=time.monotonic() + OWNERS_TTL, map=known)


def recorded_owner(profile: dict) -> bool:
    """The profile's id signed in with a Google-proved address that is still in ADMIN_EMAILS (for background jobs)."""
    emails = admin_emails()
    if not emails or not profile.get("id"):
        return False
    return _owner_map().get(profile["id"]) in emails


def admin_profile(profile=Depends(current_profile)) -> dict:
    if not is_admin(profile):
        raise HTTPException(403, {"code": "not_admin", "message": "This page is only for the site owner."})
    return profile


def leader_admin(profile=Depends(admin_profile)) -> dict:
    """An admin's Run now, on the container that runs the jobs: anywhere else it would run beside the leader's run."""
    if not leader.leading():
        raise HTTPException(409, {"code": "not_leader", "message": "Another server is running the jobs right now; try again in a minute."})
    return profile


def _paged(query, page: int = 1000) -> list[dict]:
    """Every row of a query, read a page at a time by id (the server caps one read); `query()` gives a fresh one
    selecting at least id."""
    out, after = [], ""
    while True:
        q = query()
        if after:
            q = q.gt("id", after)
        rows = q.order("id").limit(page).execute().data
        out += rows
        if len(rows) < page:
            return out
        after = rows[-1]["id"]


def _count_since(kind: str, since_iso: str) -> int:
    r = (db.sb().table("usage_events").select("id", count="exact").eq("kind", kind).gte("created_at", since_iso)
         .limit(1).execute())
    return r.count or 0


def _usage_since(since_iso: str, ids: list[str]) -> dict[str, Counter]:
    """usage_events since a time for the given users, as {user_id: Counter(kind)} (only their rows are read)."""
    rows = []
    for i in range(0, len(ids), 100):
        part = ids[i:i + 100]
        rows += _paged(lambda: db.sb().table("usage_events").select("id,user_id,kind").in_("user_id", part)
                       .in_("kind", ["backtest", "ai"]).gte("created_at", since_iso))
    out: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        out[r["user_id"]][r["kind"]] += 1
    return out


def _profiles(cols: str, plan: str | None = None, q: str = "") -> list[dict]:
    def build():
        query = db.sb().table("profiles").select(cols)
        if q:
            query = query.ilike("email", f"%{q.strip()}%")
        if plan in ("basic", "pro"):
            query = query.eq("plan", plan)          # narrowed in the database; an ended plan is dropped by the caller
        return query
    return _paged(build)


# who has a paid plan the owner gave by hand (set_plan), as one setting {uid: true}: kept out of profiles so it needs no
# schema change; a subscription that starts later takes the user off it (billing.activate)
GRANTED_KEY = "admin_plan_granted"


def granted() -> set:
    try:
        d = db.json_value(db.get_setting(GRANTED_KEY), {})
        return set(d) if isinstance(d, dict) else set()
    except Exception as e:            # the counts still show; a hand-given plan may read as paying meanwhile
        print("admin granted read failed:", str(e)[:160])
        return set()


def mark_granted(uid: str, on: bool) -> None:
    def change(raw):                       # compare-and-set: a mark set at the same time isn't lost
        d = db.json_value(raw, {})
        if bool(d.get(uid)) == on:
            return None
        if on:
            d[uid] = True
        else:
            d.pop(uid, None)
        return json.dumps(d)
    db.update_setting(GRANTED_KEY, change)


def _paying(r: dict, given: set = frozenset()) -> bool:
    """On a paid plan by a live subscription, not one the owner gave by hand (set_plan) after it ended."""
    return bool(r.get("razorpay_subscription_id")) and r.get("plan_status") == "active" and r.get("id") not in given


def _at(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def users(q: str, month_start: str, limit: int = 200, plan: str | None = None) -> list[dict]:
    """The newest `limit` users: those whose email contains `q`, and on `plan` when given (the plan they have now, so
    a paid plan that ended counts as Free)."""
    cols = "id,email,plan,plan_status,current_period_end,cancel_at_period_end,razorpay_subscription_id,created_at"
    if plan in PLANS:
        rows = sorted(_profiles(cols, plan, q), key=lambda r: r.get("created_at") or "", reverse=True)
        rows = [r for r in rows if effective_plan(r) == plan][:limit]
    else:
        query = db.sb().table("profiles").select(cols)
        if q:
            query = query.ilike("email", f"%{q.strip()}%")
        rows = query.order("created_at", desc=True).limit(limit).execute().data
    usage = _usage_since(month_start, [r["id"] for r in rows])
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
    given = granted()
    return [{
        "id": r["id"], "email": r.get("email"), "created_at": r.get("created_at"),
        "plan": effective_plan(r), "plan_set": r.get("plan"), "plan_status": r.get("plan_status"),
        "plan_until": r.get("current_period_end"), "cancel_at_period_end": bool(r.get("cancel_at_period_end")),
        "paying": _paying(r, given),
        "experiments": usage[r["id"]]["backtest"], "ai_builds": usage[r["id"]]["ai"], "referrals": invited.get(r["id"], 0),
        "free_months": months.get(r["id"], 0),
    } for r in rows]


_COUNT_COLS = "id,plan,plan_status,current_period_end,created_at,razorpay_subscription_id"


def stats(month_start: str) -> dict:
    rows = _profiles(_COUNT_COLS)
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    today = now.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)     # the India day
    plans = Counter(effective_plan(r) for r in rows)
    # on a paid plan by paying (a subscription), or given by the owner by hand: Overview tells them apart
    given = granted()
    paying = Counter(effective_plan(r) for r in rows if _paying(r, given))
    made = [t for t in (_at(r.get("created_at")) for r in rows) if t]
    new = sum(1 for t in made if t >= week_ago)
    return {"users": len(rows), "plans": {p: plans.get(p, 0) for p in PLANS}, "new_7d": new,
            "signups_today": sum(1 for t in made if t >= today),
            "paying": {p: paying.get(p, 0) for p in ("basic", "pro")},
            "given": {p: plans.get(p, 0) - paying.get(p, 0) for p in ("basic", "pro")},
            "experiments_month": _count_since("backtest", month_start), "ai_month": _count_since("ai", month_start),
            "ai_reads_month": _count_since("research_ai", month_start)}


def week_stats(since: datetime) -> dict:
    """Users joined since a time, everyone so far, paid users by plan, and experiments and AI builds since then."""
    rows = _profiles(_COUNT_COLS)
    plans = Counter(effective_plan(r) for r in rows)
    # paying (a subscription) apart from given by the owner, as Overview counts them (R6V-010)
    given = granted()
    paying = Counter(effective_plan(r) for r in rows if _paying(r, given))
    new = sum(1 for r in rows if (t := _at(r.get("created_at"))) and t >= since)
    since_iso = since.astimezone(timezone.utc).isoformat()
    usage = {"backtest": _count_since("backtest", since_iso), "ai": _count_since("ai", since_iso)}
    paid = [p for p in PLANS if p != "free"]
    return {"users": len(rows), "new": new, "paid": {p: plans[p] for p in paid if plans[p]},
            "paying": {p: paying[p] for p in paid if paying[p]}, "given": {p: plans[p] - paying[p] for p in paid if plans[p] - paying[p]},
            "experiments": usage["backtest"], "ai": usage["ai"]}


def set_plan(user_id: str, plan: str, days: int | None) -> dict:
    """Grant a plan by hand. Paid plans run for `days` (or with no end); "free" clears it."""
    if plan not in PLANS:
        raise HTTPException(400, {"code": "bad_plan", "message": "Unknown plan."})
    found = db.sb().table("profiles").select("id,plan_status,razorpay_subscription_id").eq("id", user_id).limit(1).execute().data
    if found and _paying(found[0], granted()):
        raise HTTPException(409, {"code": "pays_razorpay", "message": "This user pays through Razorpay. "
                                  "Cancel their subscription in Razorpay first, then change the plan."})
    if plan == "free":
        fields = {"plan": "free", "plan_status": None, "current_period_end": None, "cancel_at_period_end": False}
    else:
        until = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat() if days else None
        fields = {"plan": plan, "plan_status": "active", "current_period_end": until, "cancel_at_period_end": False}
    # a halted or cancelled subscription is not live (no 409 above), but billing._act still finds the profile by it: a
    # late cancelled/completed event or refund would wipe the plan just given. A hand-given plan has no subscription.
    fields |= {"razorpay_subscription_id": None, "pending_subscription_id": None}
    row = db.update_profile(user_id, **fields)
    if row is None:
        raise HTTPException(404, {"code": "no_user", "message": "No user with that ID."})
    try:
        mark_granted(user_id, plan != "free")     # given by hand, so never counted as paying
    except Exception as e:                    # the plan is given either way; only Overview's paying count reads this
        print("admin granted mark failed:", str(e)[:160])
    return row
