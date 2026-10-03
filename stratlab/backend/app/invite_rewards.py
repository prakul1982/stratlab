"""Invite rewards: when a friend joins through someone's invite link and becomes active, both get a free month of Basic.

- Active: the newcomer used the app on 3 different days (India dates) within their first 14 days. A day counts when
  they did something real: a backtest, a watchlist add, a deep dive, starting paper trading or importing holdings.
- Caps: the referrer earns at most 12 free months, ever; the newcomer gets theirs once (an account is counted as
  invited once); nothing when both addresses reach the same mailbox.
- A free month is 30 days of free Basic (plans.add_free_basic): straight away on Free, stacked after any free time
  left; banked for later by someone who pays for Basic or Pro.
- Abuse: one person's link bringing more than 5 sign-ups in one day (India time) puts the rewards for the 6th on in
  Admin for review. The sign-ups themselves always go through.
- Given from the day the newcomer's third active day is recorded, and by a daily check (Job below, modelled on the
  lifecycle emails' job) that also closes invites whose 14 days ran out.

Kept in app_settings:
  reward:{newcomer uid}  -> {"by", "at", "status", "referrer_months", "newcomer_months", ...}, one per counted invite
  actdays:{newcomer uid} -> the India dates they did something real, written only in their first 14 days
  rewardjob:last         -> the India date the daily check last ran
Statuses: waiting (for the newcomer to become active), review (for the admin), given, expired (14 days passed),
same_person, rejected (by the admin)."""
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from . import alerts, db, lifecycle, plans, referrals
from .plans import IST, _dt

ROW = "reward:"
DAYS = "actdays:"
MARK = "rewardjob:last"
WINDOW = timedelta(days=14)          # the newcomer's first 14 days
ACTIVE_DAYS = 3                      # different days with a real action
MONTH_DAYS = 30                      # one free month of Basic
REFERRER_CAP = 12                    # free months one person can earn by inviting, ever
DAILY_SIGNUPS = 5                    # sign-ups through one link in a day before the rest wait for review
RUN_AFTER = 6                        # India hour the daily check runs from
ACTIONS = ("backtest", "watchlist", "deepdive", "paper", "holdings")

_lock = threading.RLock()
_touched: dict[str, str] = {}        # uid -> the India date already recorded, so a busy day writes once


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _day(t: datetime) -> str:
    return t.astimezone(IST).date().isoformat()


def _created(profile: dict) -> datetime | None:
    try:
        made = _dt(profile["created_at"])
    except (KeyError, TypeError, ValueError):
        return None
    return made if made.tzinfo else made.replace(tzinfo=timezone.utc)


def row(uid: str) -> dict | None:
    """The reward record for a newcomer, or None when they weren't invited."""
    v = db.json_value(db.get_setting(ROW + uid), {})
    return v if v.get("by") else None


def _save(uid: str, r: dict):
    db.set_setting(ROW + uid, json.dumps(r))


def all_rows() -> dict[str, dict]:
    """{newcomer uid: reward record} for every counted invite."""
    out = {}
    for k, v in db.all_settings_with_prefix(ROW):
        r = db.json_value(v, {})
        if r.get("by"):
            out[k[len(ROW):]] = r
    return out


def months_earned(uid: str, rows: dict | None = None) -> dict:
    """Free months a user earned: as the one who invited (capped at 12) and as an invited newcomer (once)."""
    rows = all_rows() if rows is None else rows
    referrer = sum(1 for r in rows.values() if r.get("by") == uid and r.get("referrer_months") == 1)
    mine = rows.get(uid) or {}
    newcomer = 1 if mine.get("newcomer_months") == 1 else 0
    return {"referrer": referrer, "newcomer": newcomer, "total": referrer + newcomer}


# ---------- a friend joins ----------
def joined(referrer: dict, newcomer: dict, now: datetime | None = None) -> str:
    """The invite was counted (referrals.on_referral_joined). Starts waiting for the newcomer to become active, or
    puts the reward up for review when the link brought too many sign-ups today. Returns the status."""
    uid, by = newcomer.get("id"), referrer.get("id")
    if not uid or not by:
        return "none"
    with _lock:
        have = row(uid)
        if have:
            return have["status"]                # an account is rewarded once
        status = "waiting"
        mine = referrals._mailbox(newcomer.get("email"))
        if uid == by or (mine and mine == referrals._mailbox(referrer.get("email"))):
            status = "same_person"
        stamps = []                              # when each sign-up through this link was counted
        for j in referrals.joined(by):
            try:
                if isinstance(j, dict):
                    stamps.append((j.get("id"), _dt(j["at"])))
            except (KeyError, TypeError, ValueError):
                continue
        now = now or next((t for i, t in stamps if i == uid), None) or _now(None)
        today = _day(now)
        same_day = sum(1 for _, t in stamps if _day(t) == today)
        if status == "waiting" and same_day > DAILY_SIGNUPS:
            status = "review"
        _save(uid, {"by": by, "at": now.isoformat(timespec="seconds"), "status": status, "signups_that_day": same_day,
                    "referrer_months": 0, "newcomer_months": 0})
    if status == "waiting":
        check(uid, now)                          # nothing yet for a brand-new account, but keeps one path
    return status


# ---------- the newcomer uses the app ----------
def touch(profile: dict, action: str, now: datetime | None = None) -> bool:
    """A user did something real (one of ACTIONS). For an invited newcomer in their first 14 days, remembers the day
    and gives the rewards once it's the third. Once a day per user at most touches the database."""
    now = _now(now)
    uid = profile.get("id")
    if not uid or action not in ACTIONS:
        return False
    today = _day(now)
    if _touched.get(uid) == today:
        return False
    if len(_touched) > 50000:
        _touched.clear()
    _touched[uid] = today
    made = _created(profile)
    if not made or not made <= now < made + WINDOW:
        return False
    r = row(uid)
    if not r or r.get("status") not in ("waiting", "review"):
        return False
    with _lock:
        days = db.json_value(db.get_setting(DAYS + uid), [])
        if today not in days:
            db.set_setting(DAYS + uid, json.dumps(sorted(set(days) | {today})[-60:]))
    if r.get("status") == "waiting":
        check(uid, now)
    return True


def active_days(profile: dict) -> list[str]:
    """The India dates in the newcomer's first 14 days with a real action: those recorded as they happened, plus
    backtests and paper sessions from their own records."""
    made = _created(profile)
    if not made:
        return []
    end = made + WINDOW
    first, last = _day(made), _day(end - timedelta(seconds=1))
    days = {d for d in db.json_value(db.get_setting(DAYS + profile["id"]), []) if isinstance(d, str) and first <= d <= last}
    for at in db.usage_times(profile["id"], "backtest", made.astimezone(timezone.utc).isoformat(),
                             end.astimezone(timezone.utc).isoformat()):
        try:
            t = _dt(at)
            if made <= t < end:
                days.add(_day(t))
        except (TypeError, ValueError):
            continue
    for s in db.user_sessions(profile["id"], 50):
        try:
            t = _dt(s.get("started_at") or s.get("created_at"))
            if made <= t < end:
                days.add(_day(t))
        except (TypeError, ValueError):
            continue
    return sorted(days)


def check(uid: str, now: datetime | None = None) -> str:
    """Give the rewards for one invite when the newcomer has become active, or close it when their 14 days are over.
    Returns the status after."""
    now = _now(now)
    with _lock:
        r = row(uid)
        if not r:
            return "none"
        if r.get("status") != "waiting":
            return r.get("status")
        newcomer = referrals._profile(uid)
        if not newcomer:
            r["status"] = "expired"
            _save(uid, r)
            return "expired"
        if len(active_days(newcomer)) >= ACTIVE_DAYS:
            given = _give(uid, r, newcomer, now)
        else:
            made = _created(newcomer)
            if made and now >= made + WINDOW:
                r["status"] = "expired"
                _save(uid, r)
            return r["status"]
    _tell(given, now)
    return "given"


def _give(uid: str, r: dict, newcomer: dict, now: datetime) -> list[tuple[dict, str, dict]]:
    """Both months, under the lock. Returns who to tell: (profile, role, free Basic after)."""
    out = []
    after = plans.add_free_basic(newcomer, MONTH_DAYS, now)
    r["newcomer_months"] = 1
    out.append((newcomer, "newcomer", after))
    referrer = referrals._profile(r["by"])
    if referrer and months_earned(r["by"])["referrer"] < REFERRER_CAP:
        after = plans.add_free_basic(referrer, MONTH_DAYS, now)
        r["referrer_months"] = 1
        out.append((referrer, "referrer", after))
    elif referrer:
        r["capped"] = True
    r.update(status="given", given_at=now.isoformat(timespec="seconds"))
    _save(uid, r)
    return [(p, role, after, f"invite_reward:{uid}:{role}") for p, role, after in out]


def _tell(given: list[tuple[dict, str, dict, str]], now: datetime):
    """A phone or Telegram note (where set up) and an account email to each person who got a month."""
    for p, role, after, key in given:
        ctx = {"role": role, "until": after.get("until"), "banked": after.get("banked", 0)}
        subject, _, text = lifecycle.build("invite_reward", p, ctx)
        try:
            for channel, job in alerts.jobs_for(p, subject, text, "/account#invite"):
                if channel != "email":           # the email goes below, once, as an account email
                    threading.Thread(target=_quiet(job), daemon=True).start()
        except Exception as e:
            print("invite reward note failed:", str(e)[:160])
        lifecycle.later(lifecycle.send, p, "invite_reward", key, ctx, now)


def _quiet(job):
    def run():
        try:
            job()
        except Exception as e:
            print("invite reward note failed:", str(e)[:160])
    return run


# ---------- the admin ----------
def review(uid: str, approve: bool, now: datetime | None = None) -> str | None:
    """The admin's call on a reward waiting for review: approved, it waits for the newcomer to become active like
    any other (given at once when they already are); rejected, nothing is given. Returns the status after, or None
    when it wasn't waiting for review."""
    with _lock:
        r = row(uid)
        if not r or r.get("status") != "review":
            return None
        r["status"] = "waiting" if approve else "rejected"
        r["reviewed_at"] = _now(now).isoformat(timespec="seconds")
        _save(uid, r)
    return check(uid, now) if approve else "rejected"


def admin_view(limit: int = 200) -> dict:
    """Rewards for Admin: those waiting for review first, then the newest given."""
    rows = all_rows()
    emails = {}
    ids = {u for u in rows} | {r["by"] for r in rows.values()}
    for p in db.all_profiles():
        if p.get("id") in ids:
            emails[p["id"]] = p.get("email")

    def show(uid, r):
        return {"newcomer": uid, "newcomer_email": emails.get(uid), "referrer": r["by"], "referrer_email": emails.get(r["by"]),
                "at": r.get("at"), "status": r.get("status"), "given_at": r.get("given_at"),
                "signups_that_day": r.get("signups_that_day", 0), "months": (r.get("referrer_months") or 0) + (r.get("newcomer_months") or 0),
                "capped": bool(r.get("capped"))}
    items = sorted(rows.items(), key=lambda kv: str(kv[1].get("at") or ""), reverse=True)
    pending = [show(u, r) for u, r in items if r.get("status") == "review"]
    given = [show(u, r) for u, r in items if r.get("status") == "given"][:limit]
    months = sum((r.get("referrer_months") or 0) + (r.get("newcomer_months") or 0) for r in rows.values())
    return {"review": pending[:limit], "given": given, "months_given": months,
            "waiting": sum(1 for r in rows.values() if r.get("status") == "waiting")}


def months_by_user() -> dict[str, int]:
    """{uid: free months earned}, for Admin's Users tab."""
    out: dict[str, int] = {}
    for uid, r in all_rows().items():
        if r.get("referrer_months") == 1:
            out[r["by"]] = out.get(r["by"], 0) + 1
        if r.get("newcomer_months") == 1:
            out[uid] = out.get(uid, 0) + 1
    return out


# ---------- what the user sees ----------
def mine(profile: dict) -> dict:
    """For Account: friends joined, free months earned, and the user's free Basic time."""
    uid = profile["id"]
    have = plans.free_basic(uid)
    until = plans.free_basic_until(profile)
    return {"joined": len(referrals.joined(uid)), "months": months_earned(uid)["total"], "cap": REFERRER_CAP,
            "free_basic_until": until.isoformat() if until else None, "banked_days": have["banked"]}


# ---------- the daily check ----------
def sweep(now: datetime | None = None) -> dict:
    """Check every invite still waiting. Returns {status: how many}."""
    now = _now(now)
    out: dict[str, int] = {}
    for uid, r in all_rows().items():
        if r.get("status") != "waiting":
            continue
        try:
            s = check(uid, now)
        except Exception as e:
            print("invite reward check failed:", str(e)[:160])
            s = "error"
        out[s] = out.get(s, 0) + 1
    return out


class Job:
    """Checks every ten minutes; runs once a day from 6 am India time. The day is marked in the database before
    running, and each reward is recorded per invite, so a restart never gives twice."""

    def __init__(self):
        self.last: str | None = None
        self.status = {"last_run": None, "result": {}, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="invite-rewards").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("invite rewards:", e)
            time.sleep(600)

    def due(self, now: datetime) -> str | None:
        local = now.astimezone(IST)
        if local.hour < RUN_AFTER:
            return None
        day = local.date().isoformat()
        if self.last == day:
            return None
        if db.get_setting(MARK) == day:              # ran today before a restart
            self.last = day
            return None
        return day

    def tick(self, now: datetime) -> dict | None:
        day = self.due(now)
        if not day:
            return None
        self.last = day
        db.set_setting(MARK, day)
        result = sweep(now)
        self.status.update(last_run=now.isoformat(), result=result, last_error=None)
        return result


def safe_touch(profile: dict, action: str):
    """touch() for the routes: a fault here never fails what the user was doing."""
    try:
        touch(profile, action)
    except Exception as e:
        print("invite activity:", str(e)[:160])
