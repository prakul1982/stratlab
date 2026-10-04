"""Invite rewards: when a friend joins through someone's invite link and becomes active, the friend gets a free month
of Basic. The one who invited them earns from their first friends in a year, and a smaller credit after that.

- Active: the newcomer used the app on 3 different days (India dates) within their first 14 days. A day counts when
  they did something real: a backtest, a watchlist add, a deep dive, starting paper trading or importing holdings.
- The newcomer's month: once they're active, once per account (an account is counted as invited once).
- The referrer's reward, one per invited friend at most, counted over a rolling 365 days:
  - use: a free month when the friend becomes active, for the first 2 such friends (USE_CAP);
  - payment: a free month when the friend makes their first real payment (a captured Razorpay subscription charge
    with money in it, never free or granted time) within 90 days of joining, active or not, for the first 2 such
    friends (PAY_CAP);
  - extra: past the payment cap, each further friend's first real payment gives INVITE_EXTRA_PCT of a month (25%:
    8 days) of free time, at most 8 a year (EXTRA_CAP).
  A friend who became active once the use-based months were used up is "waiting to subscribe" (referrer_pending)
  until they pay or their 90 days end. A payment refunded or disputed within 7 days of being made takes back what it
  earned (billing.py hands over Razorpay's refund and dispute events), and that friend earns nothing more.
- Nothing when both addresses reach the same mailbox.
- Free time is free Basic (plans.add_free_basic): straight away on Free, stacked after any free time left; banked for
  later by someone who pays for Basic or Pro (a subscription's own end date is Razorpay's, so it isn't moved).
- Abuse: one person's link bringing more than 5 sign-ups in one day (India time) puts the rewards for the 6th on in
  Admin for review. The sign-ups themselves always go through.
- Given from the day the newcomer's third active day is recorded (or their payment arrives), and by a daily check
  (Job below, modelled on the lifecycle emails' job) that also closes invites whose 14 days ran out.

Kept in app_settings:
  reward:{newcomer uid}  -> {"by", "at", "status", "referrer_months", "newcomer_months", "kind", "referrer_at",
                             "referrer_days", "referrer_pending", "paid_at", "payment_id", ...}, one per counted invite
  actdays:{newcomer uid} -> the India dates they did something real, written only in their first 14 days
  rewardpay:{payment id} -> the newcomer whose first payment it was, so a refund finds the reward
  rewardjob:last         -> the India date the daily check last ran
Statuses (the newcomer's side): waiting (for the newcomer to become active), review (for the admin), given, expired
(14 days passed), same_person, rejected (by the admin)."""
import json
import threading
import time
from datetime import datetime, timedelta, timezone

from . import alerts, db, lifecycle, plans, referrals
from .plans import IST, _dt

ROW = "reward:"
DAYS = "actdays:"
PAY = "rewardpay:"
MARK = "rewardjob:last"
WINDOW = timedelta(days=14)          # the newcomer's first 14 days
ACTIVE_DAYS = 3                      # different days with a real action
MONTH_DAYS = 30                      # one free month of Basic
USE_CAP = 2                          # referrer months a year from friends becoming active
PAY_CAP = 2                          # referrer months a year from friends' first payments
INVITE_EXTRA_PCT = 25                # past PAY_CAP, a paying friend gives this share of a month
EXTRA_DAYS = int(MONTH_DAYS * INVITE_EXTRA_PCT / 100 + 0.5)
EXTRA_CAP = 8                        # those extra credits a year
YEAR = timedelta(days=365)           # the rolling year the caps count over
PAY_WITHIN = timedelta(days=90)      # a friend's first payment counts this long after they joined
REFUND_WITHIN = timedelta(days=7)    # a refund or dispute this soon after the payment takes the reward back
DAILY_SIGNUPS = 5                    # sign-ups through one link in a day before the rest wait for review
RUN_AFTER = 6                        # India hour the daily check runs from
ACTIONS = ("backtest", "watchlist", "deepdive", "paper", "holdings")
CAPS = {"use": USE_CAP, "payment": PAY_CAP, "extra": EXTRA_CAP}

_lock = threading.RLock()
_touched: dict[str, str] = {}        # uid -> the India date already recorded, so a busy day writes once


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _day(t: datetime) -> str:
    return t.astimezone(IST).date().isoformat()


def _when(v) -> datetime | None:
    try:
        t = _dt(v)
    except (TypeError, ValueError, AttributeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _created(profile: dict) -> datetime | None:
    return _when(profile.get("created_at"))


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


def kind_of(r: dict) -> str | None:
    """What the referrer earned for this invite: "use", "payment" or "extra" (older records are "use"), or None."""
    if r.get("referrer_months") != 1:
        return None
    return r["kind"] if r.get("kind") in ("payment", "extra") else "use"


def months_earned(uid: str, rows: dict | None = None) -> dict:
    """Free months a user earned: as the one who invited (ever; an extra credit isn't a month) and as an invited
    newcomer (once)."""
    rows = all_rows() if rows is None else rows
    referrer = sum(1 for r in rows.values() if r.get("by") == uid and kind_of(r) in ("use", "payment"))
    mine = rows.get(uid) or {}
    newcomer = 1 if mine.get("newcomer_months") == 1 else 0
    return {"referrer": referrer, "newcomer": newcomer, "total": referrer + newcomer}


def this_year(by: str, now: datetime, rows: dict | None = None) -> dict:
    """The referrer's rewards in the 365 days to `now`, by kind, and the friends waiting to subscribe."""
    rows = all_rows() if rows is None else rows
    out = {"use": 0, "payment": 0, "extra": 0, "waiting_to_subscribe": 0}
    for r in rows.values():
        if r.get("by") != by:
            continue
        kind = kind_of(r)
        at = _when(r.get("referrer_at") or r.get("given_at") or r.get("at"))
        if kind and at and at > now - YEAR:
            out[kind] += 1
        joined_at = _when(r.get("at"))
        if r.get("referrer_pending") and not kind and joined_at and now < joined_at + PAY_WITHIN:
            out["waiting_to_subscribe"] += 1
    return out


def _paid_in_time(r: dict) -> bool:
    paid, joined_at = _when(r.get("paid_at")), _when(r.get("at"))
    return bool(paid and joined_at and paid < joined_at + PAY_WITHIN)


def _due(r: dict, now: datetime) -> str | None:
    """What the referrer earns for this invite now: "use", "payment", "extra", "cap" (earned, but every cap this year
    is reached) or None (nothing, or not yet)."""
    if r.get("referrer_months") == 1 or r.get("reversed_at") or r.get("status") in ("same_person", "review", "rejected"):
        return None
    year = this_year(r["by"], now)
    if _paid_in_time(r):
        for kind in ("payment", "extra"):
            if year[kind] < CAPS[kind]:
                return kind
        return "cap"
    if r.get("status") == "given":
        return "use" if year["use"] < USE_CAP else None
    return None


def _referrer(uid: str, r: dict, now: datetime) -> list[tuple]:
    """The referrer's reward for one invite when it's due, under the lock; the caller saves `r`. Returns who to tell."""
    due = _due(r, now)
    referrer = referrals._profile(r["by"])
    if due in CAPS and referrer:
        days = EXTRA_DAYS if due == "extra" else MONTH_DAYS
        after = plans.add_free_basic(referrer, days, now)
        r.update(referrer_months=1, kind=due, referrer_days=days, referrer_at=now.isoformat(timespec="seconds"),
                 referrer_pending=False)
        r.pop("capped", None)
        return [(referrer, "referrer", after, f"invite_reward:{uid}:referrer", due)]
    if due == "cap":
        r["capped"] = True
    r["referrer_pending"] = bool(r.get("status") == "given" and r.get("referrer_months") != 1
                                 and not r.get("reversed_at") and not r.get("paid_at"))
    return []


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


def _give(uid: str, r: dict, newcomer: dict, now: datetime) -> list[tuple]:
    """The newcomer's month and the referrer's reward when due, under the lock. Returns who to tell."""
    after = plans.add_free_basic(newcomer, MONTH_DAYS, now)
    r["newcomer_months"] = 1
    r.update(status="given", given_at=now.isoformat(timespec="seconds"))
    out = [(newcomer, "newcomer", after, f"invite_reward:{uid}:newcomer", "use")]
    out += _referrer(uid, r, now)
    _save(uid, r)
    return out


def _tell(given: list[tuple], now: datetime):
    """A phone or Telegram note (where set up) and an account email to each person who got free time."""
    for p, role, after, key, kind in given:
        ctx = {"role": role, "kind": kind, "days": EXTRA_DAYS if kind == "extra" else MONTH_DAYS,
               "until": after.get("until"), "banked": after.get("banked", 0)}
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


# ---------- the friend pays ----------
def real_payment(payment) -> bool:
    """A captured charge with money in it and nothing refunded: what counts as a friend's first payment."""
    if not isinstance(payment, dict) or not isinstance(payment.get("id"), str) or not payment["id"]:
        return False
    amount = payment.get("amount")
    return (payment.get("status") == "captured" and isinstance(amount, (int, float)) and amount > 0
            and not payment.get("amount_refunded"))


def paid(profile: dict, payment: dict, now: datetime | None = None) -> str:
    """A charge went through for `profile` (billing.py: checkout, or Razorpay's subscription.charged). For an invited
    friend's first real payment, remembers it and gives the referrer's reward when due. Returns what happened:
    "given", "recorded" (remembered; nothing due), "already", "not_invited" or "not_paid"."""
    now = _now(now)
    uid = profile.get("id")
    if not uid or not real_payment(payment):
        return "not_paid"
    with _lock:
        r = row(uid)
        if not r:
            return "not_invited"
        if r.get("payment_id"):
            return "already"                     # only the first payment counts
        made = payment.get("created_at")
        at = datetime.fromtimestamp(made, tz=timezone.utc) if isinstance(made, int) and 0 < made < 4e9 else now
        r.update(paid_at=at.isoformat(timespec="seconds"), payment_id=payment["id"][:80])
        db.set_setting(PAY + r["payment_id"], uid)
        given = _referrer(uid, r, now)
        _save(uid, r)
    _tell(given, now)
    return "given" if given else "recorded"


def refunded(payment_id, now: datetime | None = None) -> str:
    """Razorpay refunded a payment or a dispute was opened on it (billing.py). When it was an invited friend's first
    payment and that was 7 days ago or less, what it earned the referrer is taken back and the friend earns nothing
    more. Returns "reversed", "closed" (nothing had been given), "kept" (too late), "already" or "none"."""
    now = _now(now)
    if not isinstance(payment_id, str) or not payment_id:
        return "none"
    uid = db.get_setting(PAY + payment_id[:80])
    if not uid:
        return "none"
    with _lock:
        r = row(uid)
        if not r or r.get("payment_id") != payment_id[:80]:
            return "none"
        if r.get("reversed_at"):
            return "already"
        r["refunded_at"] = now.isoformat(timespec="seconds")
        paid_at = _when(r.get("paid_at"))
        if not paid_at or now - paid_at > REFUND_WITHIN:
            _save(uid, r)
            return "kept"
        r.update(reversed_at=r["refunded_at"], referrer_pending=False)
        out = "closed"
        if kind_of(r) in ("payment", "extra"):
            plans.take_free_basic(r["by"], int(r.get("referrer_days") or MONTH_DAYS), now)
            r["referrer_months"] = 0
            out = "reversed"
        _save(uid, r)
    return out


# ---------- the admin ----------
def review(uid: str, approve: bool, now: datetime | None = None) -> str | None:
    """The admin's call on a reward waiting for review: approved, it waits for the newcomer to become active like
    any other (given at once when they already are, and the referrer's paid reward when the friend already paid);
    rejected, nothing is given. Returns the status after, or None when it wasn't waiting for review."""
    now = _now(now)
    with _lock:
        r = row(uid)
        if not r or r.get("status") != "review":
            return None
        r["status"] = "waiting" if approve else "rejected"
        r["reviewed_at"] = now.isoformat(timespec="seconds")
        _save(uid, r)
    if not approve:
        return "rejected"
    status = check(uid, now)
    if status != "given":
        with _lock:
            r = row(uid)
            given = _referrer(uid, r, now) if r and r.get("paid_at") else []
            if given:
                _save(uid, r)
        _tell(given, now)
    return status


REWARD_LABELS = {"use": "Use", "payment": "Payment", "extra": f"Payment ({INVITE_EXTRA_PCT}% of a month)"}


def admin_view(limit: int = 200) -> dict:
    """Rewards for Admin: those waiting for review first, then the newest given, each with how the referrer earned."""
    rows = all_rows()
    emails = {}
    ids = {u for u in rows} | {r["by"] for r in rows.values()}
    for p in db.all_profiles():
        if p.get("id") in ids:
            emails[p["id"]] = p.get("email")

    def reward(r):
        kind = kind_of(r)
        if kind:
            return kind, REWARD_LABELS[kind]
        if r.get("reversed_at"):
            return "reversed", "Taken back (refund)"
        if r.get("capped"):
            return "capped", "None: every cap this year reached"
        if r.get("referrer_pending"):
            return "pending_payment", "Waiting to subscribe"
        return None, ""

    def show(uid, r):
        kind, label = reward(r)
        return {"newcomer": uid, "newcomer_email": emails.get(uid), "referrer": r["by"], "referrer_email": emails.get(r["by"]),
                "at": r.get("at"), "status": r.get("status"), "given_at": r.get("given_at") or r.get("referrer_at"),
                "signups_that_day": r.get("signups_that_day", 0),
                "months": (1 if kind_of(r) in ("use", "payment") else 0) + (r.get("newcomer_months") or 0),
                "capped": bool(r.get("capped")), "reward": kind, "reward_label": label, "paid_at": r.get("paid_at")}
    items = sorted(rows.items(), key=lambda kv: str(kv[1].get("given_at") or kv[1].get("referrer_at") or kv[1].get("at") or ""),
                   reverse=True)
    pending = [show(u, r) for u, r in items if r.get("status") == "review"]
    given = [show(u, r) for u, r in items
             if r.get("status") == "given" or r.get("referrer_months") == 1 or r.get("reversed_at")][:limit]
    months = sum(months_earned(u, rows)["newcomer"] for u in rows) + sum(
        1 for r in rows.values() if kind_of(r) in ("use", "payment"))
    return {"review": pending[:limit], "given": given, "months_given": months,
            "extras_given": sum(1 for r in rows.values() if kind_of(r) == "extra"),
            "waiting": sum(1 for r in rows.values() if r.get("status") == "waiting"),
            "waiting_to_subscribe": sum(1 for r in rows.values() if r.get("referrer_pending") and not kind_of(r))}


def months_by_user() -> dict[str, int]:
    """{uid: free months earned}, for Admin's Users tab."""
    out: dict[str, int] = {}
    for uid, r in all_rows().items():
        if kind_of(r) in ("use", "payment"):
            out[r["by"]] = out.get(r["by"], 0) + 1
        if r.get("newcomer_months") == 1:
            out[uid] = out.get(uid, 0) + 1
    return out


# ---------- what the user sees ----------
def mine(profile: dict, now: datetime | None = None) -> dict:
    """For Account: friends joined, free months earned, this year's rewards against their caps, and the user's free
    Basic time."""
    now = _now(now)
    uid = profile["id"]
    rows = all_rows()
    year = this_year(uid, now, rows)
    have = plans.free_basic(uid)
    until = plans.free_basic_until(profile)
    return {"joined": len(referrals.joined(uid)), "months": months_earned(uid, rows)["total"],
            "use_months": year["use"], "use_cap": USE_CAP, "paid_months": year["payment"], "paid_cap": PAY_CAP,
            "extras": year["extra"], "extra_cap": EXTRA_CAP, "extra_pct": INVITE_EXTRA_PCT, "extra_days": EXTRA_DAYS,
            "waiting_to_subscribe": year["waiting_to_subscribe"],
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


def safe_paid(profile: dict, payment: dict | None):
    """paid() for billing: a fault here never fails the payment."""
    try:
        if payment:
            paid(profile, payment)
    except Exception as e:
        print("invite payment reward failed:", str(e)[:160])


def safe_refunded(payment_id):
    """refunded() for billing's webhook."""
    try:
        refunded(payment_id)
    except Exception as e:
        print("invite refund check failed:", str(e)[:160])
