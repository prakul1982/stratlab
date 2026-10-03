"""Invite rewards: a free month of Basic for both people once an invited friend is active (3 days with a real action
in their first 14), the caps (12 months for the one inviting, once for the newcomer, never the same mailbox), free
time stacking and kept for later by paying users, more than 5 sign-ups a day held for review, the notes and emails,
the daily job, and what Account and Admin show."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import alerts, db, invite_rewards as R, lifecycle, plans, referrals
from tests import world as W
from tests.fake_db import headers

NOW = datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc)          # Wed 7 Oct, 10:30 India time
DAY = timedelta(days=1)


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    monkeypatch.setattr(lifecycle, "BACKGROUND", False)
    plans._promo.update(read_at=0.0, until=None)
    yield world
    plans.forget_free_basic()
    world["close"]()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None:
                        sent.append({"to": to, "subject": subject, "text": text, "html": html}))
    return sent


def user(uid, email=None, created=NOW - timedelta(hours=1), **fields):
    db.get_profile(uid, email or f"{uid}@example.com")
    return db.update_profile(uid, created_at=created.isoformat(), **fields)


def invite(ref_uid, new_uid, now=NOW, email=None, created=None):
    """`new_uid` signs up through `ref_uid`'s link at `now`."""
    newcomer = user(new_uid, email, created or now - timedelta(minutes=10))
    assert referrals.record(newcomer, referrals.code_for(ref_uid), now) == "recorded"
    return newcomer


def active(uid, start=NOW, days=3, action="backtest"):
    """The newcomer does something real on `days` different days from `start`."""
    p = referrals._profile(uid)
    for i in range(days):
        R._touched.clear()
        R.touch(p, action, start + i * DAY)


def months(uid):
    return R.months_earned(uid)["total"]


def plan_now(uid, now=None):
    p = referrals._profile(uid)
    plans.forget_free_basic()
    return plans.access_plan(p) if now is None else ("basic" if plans.free_basic_until(p, now) else plans.effective_plan(p))


# ---------- active: 3 days with a real action in the first 14 ----------
def test_three_different_days_make_the_friend_active_and_both_get_a_month(w):
    user("u-ref")
    invite("u-ref", "u-a")
    assert R.row("u-a")["status"] == "waiting"
    active("u-a", days=2)
    assert R.row("u-a")["status"] == "waiting" and months("u-a") == 0 and months("u-ref") == 0
    active("u-a", start=NOW + 5 * DAY, days=1)
    r = R.row("u-a")
    assert r["status"] == "given" and r["newcomer_months"] == 1 and r["referrer_months"] == 1
    assert months("u-a") == 1 and months("u-ref") == 1
    for uid in ("u-a", "u-ref"):
        until = plans.free_basic(uid)["until"]
        assert until and timedelta(days=29) < until - NOW < timedelta(days=36)


def test_several_actions_on_one_day_are_one_day(w):
    user("u-ref")
    invite("u-ref", "u-a")
    p = referrals._profile("u-a")
    for action in R.ACTIONS:
        R._touched.clear()
        R.touch(p, action, NOW + timedelta(hours=1))
    for action in R.ACTIONS:
        R._touched.clear()
        R.touch(p, action, NOW + DAY)
    assert R.active_days(p) == ["2026-10-07", "2026-10-08"] and R.row("u-a")["status"] == "waiting"


@pytest.mark.parametrize("action", R.ACTIONS)
def test_each_real_action_counts(w, action):
    user("u-ref")
    invite("u-ref", "u-a")
    active("u-a", action=action)
    assert R.row("u-a")["status"] == "given"


def test_other_things_dont_count(w):
    user("u-ref")
    invite("u-ref", "u-a")
    p = referrals._profile("u-a")
    for i, action in enumerate(("visit", "ai", "", "login")):
        R._touched.clear()
        assert R.touch(p, action, NOW + i * DAY) is False
    assert R.active_days(p) == []


def test_days_after_the_first_14_dont_count_and_the_invite_closes(w):
    user("u-ref")
    invite("u-ref", "u-a")
    active("u-a", days=2)
    active("u-a", start=NOW + 15 * DAY, days=3)                  # too late
    assert R.active_days(referrals._profile("u-a")) == ["2026-10-07", "2026-10-08"]
    assert R.check("u-a", NOW + 10 * DAY) == "waiting"
    assert R.check("u-a", NOW + 15 * DAY) == "expired"
    assert months("u-a") == 0 and months("u-ref") == 0


def test_backtests_and_paper_sessions_already_on_record_count(w):
    user("u-ref")
    invite("u-ref", "u-a")
    usage = db.sb().table("usage_events")
    usage.insert({"user_id": "u-a", "kind": "backtest", "created_at": (NOW + DAY).isoformat()}).execute()
    usage.insert({"user_id": "u-a", "kind": "backtest", "created_at": (NOW + 2 * DAY).isoformat()}).execute()
    usage.insert({"user_id": "u-a", "kind": "ai", "created_at": (NOW + 4 * DAY).isoformat()}).execute()       # not real
    usage.insert({"user_id": "u-a", "kind": "backtest", "created_at": (NOW + 20 * DAY).isoformat()}).execute()  # too late
    assert R.check("u-a", NOW + 3 * DAY) == "waiting"
    db.sb().table("live_sessions").insert({"user_id": "u-a", "name": "x", "strategy": {}, "instrument": {},
                                           "started_at": (NOW + 3 * DAY).isoformat()}).execute()
    assert len(R.active_days(referrals._profile("u-a"))) == 3
    assert R.check("u-a", NOW + 4 * DAY) == "given"


def test_only_invited_newcomers_are_tracked(w):
    p = user("u-solo")
    assert R.touch(p, "backtest", NOW) is False
    assert db.get_setting(R.DAYS + "u-solo") is None


# ---------- caps ----------
def test_the_one_inviting_earns_at_most_12_months(w):
    user("u-ref")
    for i in range(14):
        day = NOW + i * DAY                                       # one a day: never held for review
        invite("u-ref", f"u-f{i}", now=day)
        active(f"u-f{i}", start=day)
    rows = R.all_rows()
    assert sum(r["referrer_months"] for r in rows.values()) == 12
    assert all(r["newcomer_months"] == 1 for r in rows.values())     # every friend still gets theirs
    assert R.months_earned("u-ref")["referrer"] == 12
    assert [r.get("capped", False) for _, r in sorted(rows.items(), key=lambda kv: kv[1]["at"])][-2:] == [True, True]
    until = plans.free_basic("u-ref")["until"]
    assert timedelta(days=12 * 30) <= until - NOW <= timedelta(days=12 * 30 + 14)


def test_the_newcomer_gets_theirs_once(w):
    user("u-ref")
    user("u-ref2")
    invite("u-ref", "u-a")
    assert referrals.record(referrals._profile("u-a"), referrals.code_for("u-ref2"), NOW) == "already"
    active("u-a")
    assert R.check("u-a", NOW + 5 * DAY) == "given"
    R.joined(referrals._profile("u-ref2"), referrals._profile("u-a"), NOW)       # a second call is ignored
    active("u-a", start=NOW + 3 * DAY)
    assert months("u-a") == 1 and months("u-ref2") == 0
    assert timedelta(days=29) < plans.free_basic("u-a")["until"] - NOW < timedelta(days=36)


def test_the_same_mailbox_gets_nothing(w):
    ref = user("u-ref", "jane.doe@gmail.com")
    twin = user("u-twin", "janedoe+trading@googlemail.com")
    assert referrals.record(twin, referrals.code_for("u-ref"), NOW) == "self"
    assert R.joined(ref, twin, NOW) == "same_person"                      # even if it reached the hook
    active("u-twin")
    assert months("u-twin") == 0 and months("u-ref") == 0
    assert plans.free_basic("u-ref")["until"] is None


# ---------- how free time works ----------
def test_free_basic_lifts_a_free_account_and_ends(w):
    p = user("u-a")
    assert plan_now("u-a") == "free"
    plans.add_free_basic(p, 30)
    assert plan_now("u-a") == "basic"
    assert plan_now("u-a", datetime.now(timezone.utc) + timedelta(days=31)) == "free"


def test_rewards_stack_onto_free_time_left(w):
    p = user("u-a")
    plans.add_free_basic(p, 30, NOW)
    plans.add_free_basic(p, 30, NOW + 10 * DAY)
    assert plans.free_basic("u-a")["until"] == NOW + 60 * DAY
    plans.add_free_basic(p, 30, NOW + 100 * DAY)                    # ran out: starts again from then
    assert plans.free_basic("u-a")["until"] == NOW + 130 * DAY


def test_a_paying_user_keeps_the_month_for_later(w):
    end = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    p = user("u-a", plan="pro", plan_status="active", current_period_end=end)
    plans.add_free_basic(p, 30)
    assert plans.free_basic("u-a") == {"until": None, "banked": 30}
    assert plan_now("u-a") == "pro"                                   # pro stays pro; nothing used up
    p = db.update_profile("u-a", plan="free", plan_status=None, current_period_end=None)
    assert plan_now("u-a") == "basic"                                 # dropped to Free: the kept month starts
    have = plans.free_basic("u-a")
    assert have["banked"] == 0 and timedelta(days=29) < have["until"] - datetime.now(timezone.utc) <= timedelta(days=30)
    p = db.update_profile("u-a", plan="pro", plan_status="active", current_period_end=end)
    assert plan_now("u-a") == "pro"                                   # paying again: nothing breaks


def test_paid_basic_is_unchanged_and_the_launch_offer_still_wins(w):
    end = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
    p = user("u-a", plan="basic", plan_status="active", current_period_end=end)
    plans.add_free_basic(p, 30)
    assert plan_now("u-a") == "basic" and plans.free_basic("u-a")["banked"] == 30
    plans.set_promo(3)
    try:
        assert plan_now("u-a") == "pro"
    finally:
        plans.set_promo(None)


def test_damaged_free_time_is_ignored(w):
    user("u-a")
    for bad in ("{oops", "[]", json.dumps({"until": "not a date", "banked": "x"}), json.dumps({"banked": -5})):
        db.set_setting(plans.FREE_KEY + "u-a", bad)
        assert plan_now("u-a") == "free"
    assert plans.access_plan({}) == "free"


def test_signed_in_requests_see_free_basic(w):
    c = w["client"]
    plans.add_free_basic(referrals._profile("u-free"), 30)
    me = c.get("/me", headers=headers("free-token")).json()
    assert me["plan"] == "basic" and me["paid_plan"] == "free" and me["free_basic_until"]
    me = c.get("/me", headers=headers("basic-token")).json()
    assert me["free_basic_until"] is None


# ---------- too many sign-ups in a day ----------
def test_more_than_5_signups_a_day_wait_for_review_and_signups_still_count(w):
    user("u-ref")
    for i in range(7):
        invite("u-ref", f"u-f{i}", now=NOW + timedelta(minutes=i))
    rows = R.all_rows()
    assert [rows[f"u-f{i}"]["status"] for i in range(7)] == ["waiting"] * 5 + ["review"] * 2
    assert len(referrals.joined("u-ref")) == 7                      # the sign-ups themselves are counted
    for i in range(7):
        active(f"u-f{i}")
    rows = R.all_rows()
    assert [rows[f"u-f{i}"]["status"] for i in range(7)] == ["given"] * 5 + ["review"] * 2
    assert months("u-ref") == 5 and months("u-f6") == 0
    # the next day starts a new count
    invite("u-ref", "u-next", now=NOW + DAY)
    assert R.row("u-next")["status"] == "waiting"


def test_admin_reviews_held_rewards(w, outbox):
    c = w["client"]
    user("u-ref")
    now = datetime.now(timezone.utc)
    for i in range(7):
        invite("u-ref", f"u-f{i}", now=now, created=now - timedelta(hours=23))
    for i in range(7):
        active(f"u-f{i}", start=now - timedelta(hours=20))           # all already active
    view = c.get("/admin/invite-rewards", headers=headers("admin-token")).json()
    assert [r["newcomer"] for r in view["review"]] and {r["newcomer"] for r in view["review"]} == {"u-f5", "u-f6"}
    assert view["review"][0]["referrer_email"] == "u-ref@example.com" and view["review"][0]["signups_that_day"] > 5
    assert c.get("/admin/invite-rewards", headers=headers("pro-token")).status_code == 403
    assert c.post("/admin/invite-rewards/u-f5/approve", headers=headers("pro-token")).status_code == 403
    r = c.post("/admin/invite-rewards/u-f5/approve", headers=headers("admin-token")).json()
    assert r["status"] == "given" and months("u-f5") == 1
    r = c.post("/admin/invite-rewards/u-f6/reject", headers=headers("admin-token")).json()
    assert r["status"] == "rejected" and r["review"] == [] and months("u-f6") == 0
    active("u-f6", start=now)
    assert months("u-f6") == 0
    for bad in ("u-f6/approve", "u-f0/approve", "nobody/reject", "u-f5/maybe", "..%2F/approve"):
        assert c.post(f"/admin/invite-rewards/{bad}", headers=headers("admin-token")).status_code == 404
    assert months("u-ref") == 6


# ---------- telling people ----------
def test_both_get_an_email_and_a_note_once_even_with_tips_off(w, outbox, monkeypatch):
    notes = []
    monkeypatch.setattr(alerts, "jobs_for", lambda p, subject, text, url="/paper": [
        ("push", lambda: notes.append((p["id"], subject))), ("email", lambda: notes.append(("email-dup", subject)))])
    user("u-ref", "ref@example.com")
    invite("u-ref", "u-a", email="friend@example.com")
    lifecycle.set_tips("u-ref", False)
    lifecycle.set_tips("u-a", False)
    active("u-a")
    import time
    for _ in range(50):
        if len(notes) >= 2:
            break
        time.sleep(0.02)
    assert sorted(m["to"] for m in outbox) == ["friend@example.com", "ref@example.com"]
    assert all(m["subject"] == "You've got a free month of StratLab Basic" for m in outbox)
    friend = next(m for m in outbox if m["to"] == "friend@example.com")
    assert "through a friend's invite" in friend["text"] and "runs until" in friend["text"]
    assert "unsubscribe" not in friend["text"].lower()
    assert sorted(n[0] for n in notes) == ["u-a", "u-ref"]             # the phone note; no second email
    R.check("u-a", NOW + 5 * DAY)
    assert len(outbox) == 2


def test_a_paying_referrer_is_told_the_month_is_kept(w, outbox):
    end = (NOW + 40 * DAY).isoformat()
    user("u-ref", plan="pro", plan_status="active", current_period_end=end)
    invite("u-ref", "u-a")
    active("u-a")
    mail = next(m for m in outbox if m["to"] == "u-ref@example.com")
    assert "kept for you" in mail["text"]


def test_no_email_to_a_referrer_past_the_cap(w, outbox):
    user("u-ref")
    for i in range(13):
        invite("u-ref", f"u-f{i}", now=NOW + i * DAY)
        active(f"u-f{i}", start=NOW + i * DAY)
    assert sum(1 for m in outbox if m["to"] == "u-ref@example.com") == 12
    assert sum(1 for m in outbox if m["to"] != "u-ref@example.com") == 13


# ---------- the daily job ----------
def test_daily_job_runs_once_a_day_from_6am_and_gives_and_closes(w, outbox):
    user("u-ref")
    invite("u-ref", "u-a")
    invite("u-ref", "u-b")
    usage = db.sb().table("usage_events")
    for i in range(3):
        usage.insert({"user_id": "u-a", "kind": "backtest", "created_at": (NOW + i * DAY).isoformat()}).execute()
    job = R.Job()
    early = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)                # 5:30 am India time
    assert job.tick(early) is None
    later = early + timedelta(hours=1)
    assert job.tick(later) == {"given": 1, "waiting": 1}
    assert job.tick(later + timedelta(hours=3)) is None                   # once a day
    assert db.get_setting(R.MARK) == "2026-10-10"
    assert R.Job().tick(later + timedelta(hours=4)) is None              # nor after a restart
    assert R.row("u-a")["status"] == "given" and R.row("u-b")["status"] == "waiting"
    assert R.Job().tick(later + 15 * DAY) == {"expired": 1}
    assert R.row("u-b")["status"] == "expired"


def test_a_deleted_newcomer_closes_the_invite(w):
    user("u-ref")
    invite("u-ref", "u-a")
    db.sb().table("profiles").delete().eq("id", "u-a").execute()
    assert R.check("u-a", NOW + DAY) == "expired"
    assert months("u-ref") == 0


def test_a_deleted_referrer_still_leaves_the_friend_their_month(w):
    user("u-ref")
    invite("u-ref", "u-a")
    db.sb().table("profiles").delete().eq("id", "u-ref").execute()
    active("u-a")
    assert months("u-a") == 1 and R.row("u-a")["referrer_months"] == 0


# ---------- over HTTP: Account, Admin and real actions ----------
def _new(w, uid):
    for p in w["db"].tables["profiles"]:
        if p["id"] == uid:
            p["created_at"] = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    db.forget_profile(uid)


def test_account_and_admin_show_friends_and_months(w):
    c = w["client"]
    code = c.get("/me/referrals", headers=headers("pro-token")).json()["code"]
    _new(w, "u-free")
    assert c.post("/me/referral", headers=headers("free-token"), json={"code": code}).json() == {"recorded": True}
    mine = c.get("/me/referrals", headers=headers("pro-token")).json()
    assert mine["joined"] == 1 and mine["months"] == 0 and mine["cap"] == 12
    # the friend adds to their watchlist on three days: one today over HTTP, two recorded before
    db.set_setting(R.DAYS + "u-free", json.dumps([(datetime.now(plans.IST) - timedelta(days=d)).date().isoformat()
                                                  for d in (1, 2)]))
    for p in w["db"].tables["profiles"]:
        if p["id"] == "u-free":
            p["created_at"] = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    db.forget_profile("u-free")
    item = {"items": [{"region": "IN", "symbol": "RELIANCE", "name": "Reliance"}]}
    assert c.put("/research/watchlist", headers=headers("free-token"), json=item).status_code == 200
    assert R.row("u-free")["status"] == "given"
    mine = c.get("/me/referrals", headers=headers("pro-token")).json()
    assert mine["months"] == 1 and mine["banked_days"] == 30 and mine["free_basic_until"] is None
    friend = c.get("/me/referrals", headers=headers("free-token")).json()
    assert friend["months"] == 1 and friend["free_basic_until"]
    assert c.get("/me", headers=headers("free-token")).json()["plan"] == "basic"
    rows = {u["id"]: u for q in ("pro@example", "free@example")
            for u in c.get("/admin/users", params={"q": q}, headers=headers("admin-token")).json()}
    assert rows["u-pro"]["free_months"] == 1 and rows["u-free"]["free_months"] == 1 and rows["u-pro"]["referrals"] == 1


def test_removing_from_the_watchlist_isnt_an_add(w):
    c = w["client"]
    user("u-ref")
    _new(w, "u-free")
    assert referrals.record(referrals._profile("u-free"), referrals.code_for("u-ref")) == "recorded"
    db.set_setting("watchlist:u-free", json.dumps({"items": [{"region": "IN", "symbol": "TCS", "name": "TCS"}]}))
    assert c.put("/research/watchlist", headers=headers("free-token"), json={"items": []}).status_code == 200
    assert db.get_setting(R.DAYS + "u-free") is None


def test_a_broken_reward_never_breaks_the_action_or_the_signup(w, monkeypatch):
    c = w["client"]
    code = c.get("/me/referrals", headers=headers("pro-token")).json()["code"]
    _new(w, "u-free")

    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(R, "joined", boom)
    assert c.post("/me/referral", headers=headers("free-token"), json={"code": code}).json() == {"recorded": True}
    monkeypatch.setattr(R, "touch", boom)
    item = {"items": [{"region": "IN", "symbol": "TCS", "name": "TCS"}]}
    assert c.put("/research/watchlist", headers=headers("free-token"), json=item).status_code == 200
    monkeypatch.setattr(R, "mine", boom)
    assert c.get("/me/referrals", headers=headers("pro-token")).json()["joined"] == 1
    monkeypatch.setattr(R, "months_by_user", boom)
    assert c.get("/admin/users", headers=headers("admin-token")).status_code == 200


def test_damaged_records_dont_break_anything(w):
    c = w["client"]
    for k in ("reward:u-free", "actdays:u-free", "reward:u-pro"):
        db.set_setting(k, "{oops")
    db.set_setting("reward:u-x", json.dumps({"by": "u-pro", "status": "waiting", "at": None}))
    assert c.get("/me/referrals", headers=headers("pro-token")).status_code == 200
    assert c.get("/admin/invite-rewards", headers=headers("admin-token")).status_code == 200
    assert R.sweep(NOW) == {"expired": 1}
