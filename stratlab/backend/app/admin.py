"""Owner-only admin: who's signed up, what they use, and granting plans by hand.

Access is by Google account: verified emails listed in ADMIN_EMAILS. (The old ?key= admin URLs are gone.)"""
import json
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
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


def _usage_since(since_iso: str, ids: list[str], last: dict | None = None) -> dict[str, Counter]:
    """usage_events since a time for the given users, as {user_id: Counter(kind)} (only their rows are read). `last`, when
    given, is filled with each user's newest event time (for Last active, DJ-009)."""
    rows = []
    for i in range(0, len(ids), 100):
        part = ids[i:i + 100]
        rows += _paged(lambda: db.sb().table("usage_events").select("id,user_id,kind,created_at").in_("user_id", part)
                       .in_("kind", ["backtest", "ai"]).gte("created_at", since_iso))
    out: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        out[r["user_id"]][r["kind"]] += 1
        if last is not None and r.get("created_at") and str(r["created_at"]) > str(last.get(r["user_id"]) or ""):
            last[r["user_id"]] = str(r["created_at"])
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


# Test accounts (DJ-001): the "+sl-" aliases of an admin's own address that POST /admin/test-account makes, and every id
# that endpoint recorded. They are left out of every growth and plan count (seven reviewer accounts made one day read as
# "Sign-ups today 7"); Admin's "Show test accounts" puts them back.
TEST_ACCOUNTS = "test-accounts"


def _base(email: str) -> tuple[str, str]:
    local, _, domain = (email or "").strip().lower().partition("@")
    return local.split("+", 1)[0], domain


def is_test_email(email: str | None) -> bool:
    """An address on a "+sl-" alias of an admin's own address ("owner+sl-free@x.com")."""
    e = (email or "").strip().lower()
    local = e.partition("@")[0]
    if "+sl-" not in local:
        return False
    return _base(e) in {_base(a) for a in admin_emails()}


def recorded_tests() -> set:
    """The ids POST /admin/test-account recorded."""
    try:
        d = db.json_value(db.get_setting(TEST_ACCOUNTS), {})
        return set(d) if isinstance(d, dict) else set()
    except Exception as e:             # the counts still show; test accounts may be counted meanwhile
        print("admin test accounts read failed:", str(e)[:160])
        return set()


def _count_since_for(kind: str, since_iso: str, ids: list[str]) -> int:
    """usage_events of one kind since a time for these users only (the test accounts', taken off the month's count)."""
    n = 0
    for i in range(0, len(ids), 100):
        r = (db.sb().table("usage_events").select("id", count="exact").eq("kind", kind).in_("user_id", ids[i:i + 100])
             .gte("created_at", since_iso).limit(1).execute())
        n += r.count or 0
    return n


def _paying(r: dict, given: set = frozenset()) -> bool:
    """On a paid plan by a live subscription, not one the owner gave by hand (set_plan) after it ended."""
    return bool(r.get("razorpay_subscription_id")) and r.get("plan_status") == "active" and r.get("id") not in given


def _at(s) -> datetime | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


# The sign-in service's own record of every account (Supabase's auth.users): when each last signed in, and the accounts
# that signed in but have no profile here (DJ-009, DJ-010). Read a page of 1000 at a time, kept a few minutes.
SIGN_INS_FOR = 300.0
_sign_ins: dict = {"at": 0.0, "map": None, "error": None, "client": None}
_sign_ins_lock = threading.Lock()


def sign_ins(fresh: bool = False) -> tuple[dict, str | None]:
    """({user id: {"email", "created_at", "last_sign_in_at"}}, error): every account the sign-in service has."""
    with _sign_ins_lock:
        if (not fresh and _sign_ins["map"] is not None and _sign_ins["client"] == id(db.sb())
                and time.monotonic() - _sign_ins["at"] < SIGN_INS_FOR):
            return _sign_ins["map"], _sign_ins["error"]
    out, error = {}, None
    try:
        api = db.sb().auth.admin
        page = 1
        while page <= 50:                      # 50,000 accounts: far past StratLab's size, so a loop can't run away
            got = api.list_users(page=page, per_page=1000) or []
            for u in got:
                iso = lambda v: v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)   # noqa: E731
                out[str(u.id)] = {"email": getattr(u, "email", None), "created_at": iso(getattr(u, "created_at", None)),
                                  "last_sign_in_at": iso(getattr(u, "last_sign_in_at", None))}
            if len(got) < 1000:
                break
            page += 1
    except Exception as e:                     # the users still list; Last active then says the sign-in service didn't answer
        error = f"The sign-in service didn't answer: {str(e)[:160]}"
    with _sign_ins_lock:
        _sign_ins.update(at=time.monotonic(), map=out if not error else {}, error=error, client=id(db.sb()))
        return _sign_ins["map"], error


def _later(*times) -> str | None:
    got = [str(t) for t in times if t]
    return max(got, key=lambda t: _at(t) or datetime.min.replace(tzinfo=timezone.utc)) if got else None


def users(q: str, month_start: str, limit: int = 200, plan: str | None = None, include_test: bool = False) -> list[dict]:
    """The newest `limit` users: those whose email contains `q`, and on `plan` when given (the plan they have now, so
    a paid plan that ended counts as Free). Test accounts (DJ-001) are left out unless `include_test`; each row says
    whether it is one. `last_active` is the later of the last sign-in and the last experiment or AI build (DJ-009)."""
    cols = "id,email,plan,plan_status,current_period_end,cancel_at_period_end,razorpay_subscription_id,created_at"
    tests = recorded_tests()
    is_test = lambda r: r["id"] in tests or is_test_email(r.get("email"))    # noqa: E731
    if plan in PLANS:
        rows = sorted(_profiles(cols, plan, q), key=lambda r: r.get("created_at") or "", reverse=True)
        rows = [r for r in rows if effective_plan(r) == plan and (include_test or not is_test(r))][:limit]
    else:
        query = db.sb().table("profiles").select(cols)
        if q:
            query = query.ilike("email", f"%{q.strip()}%")
        # a few more than the page, so leaving the test accounts out still lists `limit` real users
        rows = query.order("created_at", desc=True).limit(limit + (0 if include_test else len(tests) + 10)).execute().data
        rows = [r for r in rows if include_test or not is_test(r)][:limit]
    last: dict = {}
    usage = _usage_since(month_start, [r["id"] for r in rows], last)
    seen, seen_error = sign_ins()
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
        "paying": _paying(r, given), "test": is_test(r),
        "last_sign_in": (seen.get(r["id"]) or {}).get("last_sign_in_at"),
        "last_active": _later((seen.get(r["id"]) or {}).get("last_sign_in_at"), last.get(r["id"])),
        "sign_ins_unread": bool(seen_error),
        "experiments": usage[r["id"]]["backtest"], "ai_builds": usage[r["id"]]["ai"], "referrals": invited.get(r["id"], 0),
        "free_months": months.get(r["id"], 0),
    } for r in rows]


ENDING_DAYS = 7          # a plan given by hand that ends within this many days (or ended this many days ago) is listed


def accounts_view(include_test: bool = False) -> dict:
    """What Users and growth lists beside the users (DJ-010, DJ-011): accounts that signed in but have no profile here,
    and plans given by hand that end within ENDING_DAYS days or have ended in the last ENDING_DAYS."""
    seen, error = sign_ins()
    profiles = {r["id"]: r for r in _profiles("id,email,plan,plan_status,current_period_end,razorpay_subscription_id")}
    orphans = sorted(({"id": uid, "email": u.get("email"), "created_at": u.get("created_at"), "last_sign_in": u.get("last_sign_in_at")}
                      for uid, u in seen.items() if uid not in profiles and (include_test or not is_test_email(u.get("email")))),
                     key=lambda x: x["created_at"] or "")
    now = datetime.now(timezone.utc)
    given, tests = granted(), recorded_tests()
    ending = []
    for r in profiles.values():
        end = _at(r.get("current_period_end")) if r.get("current_period_end") else None
        if (not end or r.get("plan") not in ("basic", "pro") or r.get("plan_status") != "active" or _paying(r, given)
                or not include_test and (r["id"] in tests or is_test_email(r.get("email")))):
            continue
        if now - timedelta(days=ENDING_DAYS) <= end <= now + timedelta(days=ENDING_DAYS):
            ending.append({"id": r["id"], "email": r.get("email"), "plan": r["plan"], "until": r["current_period_end"],
                           "ended": end <= now, "plan_now": effective_plan(r)})
    return {"orphans": orphans, "ending": sorted(ending, key=lambda x: x["until"]), "sign_ins_error": error,
            "accounts": len(seen) if not error else None}


def active_users(days: int = 7, include_test: bool = False) -> int | None:
    """People active in the last `days` days (DJ-004): signed in, or ran an experiment or an AI build, in that time. None
    when neither could be read."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    seen, error = sign_ins()
    ids = {uid for uid, u in seen.items() if (t := _at(u.get("last_sign_in_at") or "")) and t >= since}
    try:
        rows = _paged(lambda: db.sb().table("usage_events").select("id,user_id").in_("kind", ["backtest", "ai", "research_ai"])
                      .gte("created_at", since.isoformat()))
        ids |= {r["user_id"] for r in rows if r.get("user_id")}
    except Exception as e:
        print("admin active users read failed:", str(e)[:160])
        if error:
            return None
    if not include_test:
        tests = recorded_tests()
        emails = {uid: u.get("email") for uid, u in seen.items()}
        ids = {i for i in ids if i not in tests and not is_test_email(emails.get(i))}
    return len(ids)


_COUNT_COLS = "id,plan,plan_status,current_period_end,created_at,razorpay_subscription_id"


_stats_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="admin-stats")


def _count_profiles(since_iso: str | None = None) -> int:
    q = db.sb().table("profiles").select("id", count="exact")
    if since_iso:
        q = q.gte("created_at", since_iso)
    return q.limit(1).execute().count or 0


def _paid_profiles() -> list[dict]:
    """The profiles with a paid plan set (only these can count as Basic or Pro, see effective_plan)."""
    def build():
        return db.sb().table("profiles").select(_COUNT_COLS).in_("plan", ["basic", "pro"])
    return _paged(build)


def _test_rows() -> list[dict]:
    """The test accounts' profiles for the counts, in one small read (there are at most a handful): the recorded ids and
    the "+sl-" aliases. Never fails the counts: on an error none are left out."""
    try:
        cols = _COUNT_COLS + ",email"
        rows = {r["id"]: r for r in (db.sb().table("profiles").select(cols).ilike("email", "%+sl-%").limit(1000).execute().data or [])
                if is_test_email(r.get("email"))}
        ids = sorted(i for i in recorded_tests() if i not in rows)
        if ids:
            for r in db.sb().table("profiles").select(cols).in_("id", ids).limit(1000).execute().data or []:
                rows[r["id"]] = r
        return list(rows.values())
    except Exception as e:
        print("admin test accounts read failed:", str(e)[:160])
        return []


def stats(month_start: str, extra: dict | None = None, include_test: bool = False) -> dict:
    """Overview's counts. Everyone is counted in the database, not read: only the profiles with a paid plan set are read,
    for the plan they have now; Free is everyone else. The reads go at once (one after another was 10 to 13 round
    trips, R11E), with `extra` {name: fn} beside them, added to the result. The test accounts are left out of every
    count (DJ-001) unless `include_test`; `test_accounts` says how many there are."""
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    today = now.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)     # the India day
    jobs = {"users": (_count_profiles, ()), "new_7d": (_count_profiles, (week_ago.isoformat(),)),
            "signups_today": (_count_profiles, (today.isoformat(),)), "paid": (_paid_profiles, ()), "given": (granted, ()),
            "experiments_month": (_count_since, ("backtest", month_start)), "ai_month": (_count_since, ("ai", month_start)),
            "ai_reads_month": (_count_since, ("research_ai", month_start)), "tests": (_test_rows, ()),
            **{k: (fn, ()) for k, fn in (extra or {}).items()}}
    futures = {k: _stats_pool.submit(fn, *args) for k, (fn, args) in jobs.items()}
    got = {k: f.result() for k, f in futures.items()}
    tests = got["tests"]
    out_ids = set() if include_test else {r["id"] for r in tests}
    if out_ids:
        made = [t for t in (_at(r.get("created_at")) for r in tests) if t]
        got["users"] -= len(tests)
        got["new_7d"] -= sum(1 for t in made if t >= week_ago)
        got["signups_today"] -= sum(1 for t in made if t >= today)
        ids = sorted(out_ids)
        for key, kind in (("experiments_month", "backtest"), ("ai_month", "ai"), ("ai_reads_month", "research_ai")):
            got[key] -= _count_since_for(kind, month_start, ids)
    rows, given = [r for r in got["paid"] if r.get("id") not in out_ids], got["given"]
    plans = Counter(effective_plan(r) for r in rows)
    plans["free"] = got["users"] - plans.get("basic", 0) - plans.get("pro", 0)
    # on a paid plan by paying (a subscription), or given by the owner by hand: Overview tells them apart
    paying = Counter(effective_plan(r) for r in rows if _paying(r, given))
    return {"users": got["users"], "plans": {p: plans.get(p, 0) for p in PLANS}, "new_7d": got["new_7d"],
            "signups_today": got["signups_today"],
            "paying": {p: paying.get(p, 0) for p in ("basic", "pro")},
            "given": {p: plans.get(p, 0) - paying.get(p, 0) for p in ("basic", "pro")},
            "experiments_month": got["experiments_month"], "ai_month": got["ai_month"],
            "ai_reads_month": got["ai_reads_month"], "test_accounts": len(tests), **{k: got[k] for k in extra or {}}}


def week_stats(since: datetime) -> dict:
    """Users joined since a time, everyone so far, paid users by plan, and experiments and AI builds since then. The test
    accounts are left out (DJ-001), as on Overview."""
    tests = {r["id"] for r in _test_rows()}
    rows = [r for r in _profiles(_COUNT_COLS) if r.get("id") not in tests]
    plans = Counter(effective_plan(r) for r in rows)
    # paying (a subscription) apart from given by the owner, as Overview counts them (R6V-010)
    given = granted()
    paying = Counter(effective_plan(r) for r in rows if _paying(r, given))
    new = sum(1 for r in rows if (t := _at(r.get("created_at"))) and t >= since)
    since_iso = since.astimezone(timezone.utc).isoformat()
    ids = sorted(tests)
    usage = {k: _count_since(k, since_iso) - (_count_since_for(k, since_iso, ids) if ids else 0) for k in ("backtest", "ai")}
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
