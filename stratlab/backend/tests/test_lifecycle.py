"""Lifecycle emails: what triggers each one, that each goes once, the tips opt-out (Account and the link in the email),
receipts that always go, the hourly sweep, Admin's preview and test send; and the first-steps checklist on Home."""
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from html import escape

import pytest

from app import alerts, billing, db, first_steps, lifecycle, mail_tokens, newsletter_prefs, plans
from app.config import settings
from app.newsletter import write
from tests import world as W
from tests.fake_db import headers

IST = plans.IST
NOW = datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc)          # Wed 7 Oct, 10:30 IST


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    monkeypatch.setattr(lifecycle, "BACKGROUND", False)
    lifecycle._seen_today.clear()
    first_steps._marked.clear()
    plans._promo.update(read_at=0.0, until=None)
    yield world
    plans._promo.update(read_at=0.0, until=None)
    world["close"]()


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None:
                        sent.append({"to": to, "subject": subject, "text": text, "html": html, "headers": headers}))
    return sent


def user(uid="u-new", email="new@example.com", created=NOW - timedelta(hours=2), **fields):
    db.get_profile(uid, email)
    return db.update_profile(uid, created_at=created.isoformat(), **fields)


def kinds(rows):
    return [k for k, _, _ in rows]


def trading_days(start: date, n: int) -> list[date]:
    from app.data.calendar import is_trading_day
    out, d = [], start
    while len(out) < n:
        if is_trading_day("IN", d):
            out.append(d)
        d += timedelta(days=1)
    return out


# ---------- what triggers each email ----------
def test_welcome_only_for_a_brand_new_account(w):
    assert kinds(lifecycle.due(user(), NOW, {}, None, None)) == ["welcome"]
    old = user("u-old", "old@example.com", NOW - timedelta(days=3))
    assert "welcome" not in kinds(lifecycle.due(old, NOW, {}, None, None))


def test_day2_only_without_a_backtest(w):
    p = user(created=NOW - timedelta(days=1, hours=2))
    assert kinds(lifecycle.due(p, NOW, {"welcome": (NOW - timedelta(days=1)).isoformat()}, None, None, lambda: False)) == ["day2"]
    assert kinds(lifecycle.due(p, NOW, {"welcome": "2026-10-06T00:00:00+00:00"}, None, None, lambda: True)) == []
    first_day = user("u-d1", "d1@example.com", NOW - timedelta(hours=20))
    assert "day2" not in kinds(lifecycle.due(first_day, NOW, {}, None, None, lambda: False))
    stale = user("u-d9", "d9@example.com", NOW - timedelta(days=9))
    assert lifecycle.due(stale, NOW, {}, None, None, lambda: False) == []


def test_day2_reads_real_backtests(w):
    p = user(created=NOW - timedelta(days=1, hours=2))
    assert not lifecycle.ran_backtest(p["id"])
    db.add_usage(p["id"], "backtest")
    assert lifecycle.ran_backtest(p["id"])
    assert lifecycle.due(p, NOW, {"welcome": "2026-10-05T00:00:00+00:00"}, None, None, lambda: lifecycle.ran_backtest(p["id"])) == []


def test_trial_reminders_the_day_before_and_on_the_last_day(w):
    start = datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)                    # Monday 9:30 IST
    p = user(created=start - timedelta(days=30), live_trial_started_at=start.isoformat())
    last = trading_days(start.astimezone(IST).date(), 5)[-1]
    ends = plans.trial_end(start, 5)
    assert ends.astimezone(IST).date() == last + timedelta(days=1)
    at = lambda d: datetime(d.year, d.month, d.day, 5, 0, tzinfo=timezone.utc)   # 10:30 IST that day
    before = lifecycle.due(p, at(last - timedelta(days=1)), {}, None, None)
    assert before == [("trial_before", "trial_before", {"last_day": last})]
    assert kinds(lifecycle.due(p, at(last), {}, None, None)) == ["trial_end"]
    assert lifecycle.due(p, at(last - timedelta(days=2)), {}, None, None) == []
    assert lifecycle.due(p, at(last + timedelta(days=1)), {}, None, None) == []          # over
    paid = user("u-paid", "paid@example.com", start - timedelta(days=30), live_trial_started_at=start.isoformat(),
                plan="pro", plan_status="active", current_period_end="2099-01-01T00:00:00+00:00")
    assert lifecycle.due(paid, at(last), {}, None, None) == []                              # trial doesn't matter on Pro
    offer = ends + timedelta(days=3)                       # a launch offer outlasting the trial makes it moot
    assert "trial_end" not in kinds(lifecycle.due(p, at(last), {}, None, offer))


def test_launch_offer_reminders_for_free_users_once_per_offer(w):
    until = datetime(2026, 10, 9, 18, 30, tzinfo=timezone.utc)                  # midnight IST: last day is Fri 9 Oct
    p = user(created=NOW - timedelta(days=30))
    day_before = datetime(2026, 10, 8, 5, 0, tzinfo=timezone.utc)
    assert lifecycle.due(p, day_before, {}, None, until) == [("promo_before", "promo_before:2026-10-09", {"last_day": date(2026, 10, 9), "end": until})]
    assert lifecycle.due(p, day_before + timedelta(days=1), {}, None, until)[0][1] == "promo_end:2026-10-09"
    assert lifecycle.due(p, NOW, {}, None, until) == []                                   # two days before: nothing yet
    pro = user("u-pro2", "pro2@example.com", NOW - timedelta(days=30), plan="pro", plan_status="active",
               current_period_end="2099-01-01T00:00:00+00:00")
    assert lifecycle.due(pro, day_before, {}, None, until) == []                          # paying users keep Pro anyway
    assert lifecycle.due(p, day_before, {"promo_before:2026-10-09": "2026-10-08T05:00:00+00:00"}, None, until) == []


def test_inactive_after_14_quiet_days_once(w):
    p = user(created=NOW - timedelta(days=60))
    today = NOW.astimezone(IST).date()
    assert kinds(lifecycle.due(p, NOW, {}, (today - timedelta(days=14)).isoformat(), None)) == ["inactive"]
    assert lifecycle.due(p, NOW, {}, (today - timedelta(days=13)).isoformat(), None) == []
    assert lifecycle.due(p, NOW, {}, None, None) == []                                    # never seen since this shipped
    assert lifecycle.due(p, NOW, {"inactive": "2026-09-01T00:00:00+00:00"}, (today - timedelta(days=30)).isoformat(), None) == []


def test_at_most_one_tip_a_day_but_receipts_dont_count(w):
    p = user(created=NOW - timedelta(days=60))
    seen = (NOW.astimezone(IST).date() - timedelta(days=20)).isoformat()
    assert lifecycle.due(p, NOW, {"welcome": (NOW - timedelta(hours=3)).isoformat()}, seen, None) == []
    assert kinds(lifecycle.due(p, NOW, {"receipt:pay_1": (NOW - timedelta(hours=3)).isoformat()}, seen, None)) == ["inactive"]


# ---------- sending once, opting out ----------
def test_sweep_sends_once_and_one_per_user(w, outbox):
    user("u-a", "a@example.com", NOW - timedelta(hours=3))
    user("u-b", "b@example.com", NOW - timedelta(days=1, hours=3))
    assert lifecycle.sweep(NOW) == 2
    assert sorted((m["to"], m["subject"]) for m in outbox) == [("a@example.com", "Welcome to StratLab"),
                                                                ("b@example.com", "Welcome to StratLab")]
    assert lifecycle.sweep(NOW + timedelta(hours=1)) == 0                    # already welcomed; day 2 waits a day
    assert lifecycle.sweep(NOW + timedelta(hours=20)) == 1                   # b's day-2 nudge (a is still on day 1)
    assert outbox[-1]["to"] == "b@example.com" and "first strategy" in outbox[-1]["subject"]
    assert lifecycle.sweep(NOW + timedelta(hours=20, minutes=30)) == 0
    assert set(lifecycle.sent("u-b")) == {"welcome", "day2"}


def test_welcome_goes_on_the_first_visit_after_signing_up(w, outbox):
    c = w["client"]
    db.update_profile("u-free", created_at=datetime.now(timezone.utc).isoformat())
    assert c.get("/me", headers=headers("free-token")).status_code == 200
    assert [m["subject"] for m in outbox] == ["Welcome to StratLab"] and outbox[0]["to"] == "free@example.com"
    lifecycle._seen_today.clear()                                         # a restart: the record still says it went
    c.get("/me", headers=headers("free-token"))
    assert len(outbox) == 1
    assert db.get_setting(lifecycle.SEEN + "u-free") == datetime.now(IST).date().isoformat()
    c.get("/me", headers=headers("pro-token"))                            # an older account: no welcome
    assert len(outbox) == 1


def test_a_failed_send_is_tried_again(w, monkeypatch):
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    def down(*a, **k):
        raise RuntimeError("Brevo refused the email (500).")
    monkeypatch.setattr(alerts, "send_email", down)
    p = user()
    assert not lifecycle.send(p, "welcome")
    assert "welcome" not in lifecycle.sent(p["id"])
    got = []
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: got.append(a))
    assert lifecycle.send(p, "welcome") and not lifecycle.send(p, "welcome")
    assert len(got) == 1


def test_a_failing_tip_is_given_up_after_three_attempts(w, monkeypatch):
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    tries = []

    def down(*a, **k):
        tries.append(1)
        raise RuntimeError("Brevo refused the email (500).")
    monkeypatch.setattr(alerts, "send_email", down)
    p = user()
    for h in range(6):
        assert not lifecycle.send(p, "welcome", now=NOW + timedelta(hours=h))
    assert len(tries) == lifecycle.TIP_TRIES == 3
    assert "welcome" not in lifecycle.sent(p["id"])                                    # never sent, and no longer tried
    assert lifecycle.due(p, NOW + timedelta(hours=6), lifecycle.sent(p["id"]), None, None) == []
    assert lifecycle.sweep(NOW + timedelta(hours=7)) == 0 and len(tries) == 3
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: tries.append("late"))
    assert not lifecycle.send(p, "welcome", now=NOW + timedelta(hours=8)) and "late" not in tries


def test_a_tip_that_fails_once_still_goes_on_the_next_try_and_counts_no_more(w, monkeypatch):
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    calls = []
    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("timed out")
    monkeypatch.setattr(alerts, "send_email", flaky)
    p = user()
    assert not lifecycle.send(p, "welcome", now=NOW) and lifecycle.send(p, "welcome", now=NOW + timedelta(hours=1))
    assert not lifecycle.send(p, "welcome", now=NOW + timedelta(hours=2)) and len(calls) == 2


def test_the_whats_new_note_has_a_window_after_14_quiet_days(w):
    p = user(created=NOW - timedelta(days=200))
    today = NOW.astimezone(IST).date()
    quiet = lambda n: kinds(lifecycle.due(p, NOW, {}, (today - timedelta(days=n)).isoformat(), None))
    assert quiet(14) == ["inactive"] and quiet(lifecycle.INACTIVE_UNTIL - 1) == ["inactive"]
    assert quiet(lifecycle.INACTIVE_UNTIL) == [] and quiet(200) == []                  # long gone: not sent as news now


def test_a_failed_receipt_or_plan_note_is_retried_by_the_sweep(w, monkeypatch):
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    got = []

    def down(*a, **k):
        raise RuntimeError("timed out")
    monkeypatch.setattr(alerts, "send_email", down)
    p = user(created=NOW - timedelta(days=100))
    inv = {"number": "SL/2026-27/0001", "payment_id": "pay_1", "total": 499.0, "currency": "INR", "date": "2026-10-07"}
    assert not lifecycle.receipt(p, inv, "pro", "month") and not lifecycle.plan_ended(p, "sub_1", "pro")
    assert lifecycle.sent(p["id"]) == {}
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, *a, **k: got.append(subject))
    assert lifecycle.sweep(NOW + timedelta(hours=1)) == 2
    assert sorted(lifecycle.sent(p["id"])) == ["plan_ended:sub_1", "receipt:pay_1"] and len(got) == 2
    assert lifecycle.sweep(NOW + timedelta(hours=2)) == 0 and len(got) == 2             # once


def test_a_failing_account_email_is_given_up_after_a_few_tries(w, monkeypatch):
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    tries = []

    def down(*a, **k):
        tries.append(1)
        raise RuntimeError("timed out")
    monkeypatch.setattr(alerts, "send_email", down)
    p = user(created=NOW - timedelta(days=100))
    lifecycle.plan_ended(p, "sub_1", "pro")
    for h in range(1, 9):
        lifecycle.sweep(NOW + timedelta(hours=h))
    assert len(tries) == lifecycle.RETRIES
    assert db.json_value(db.get_setting(lifecycle.PENDING + p["id"]), {}) == {}


def test_a_failed_invite_reward_keeps_its_end_date_for_the_retry(w, monkeypatch):
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timed out")))
    p = user(created=NOW - timedelta(days=100))
    until = NOW + timedelta(days=30)
    ctx = {"role": "newcomer", "kind": "use", "days": 30, "until": until, "banked": 0}
    assert not lifecycle.send(p, "invite_reward", "invite_reward:x:newcomer", ctx, NOW)
    got = []
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, **k: got.append(text))
    assert lifecycle.sweep(NOW + timedelta(hours=1)) == 1 and "Your free Basic runs until" in got[0]


def test_nothing_without_email_set_up_or_an_address(w, monkeypatch):
    monkeypatch.setattr(alerts, "email_ready", lambda: False)
    assert not lifecycle.send(user(), "welcome") and lifecycle.sweep(NOW) == 0
    assert lifecycle.sent("u-new") == {}
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    assert not lifecycle.send({"id": "u-x", "email": ""}, "welcome")


def test_tips_off_in_account_stops_every_tip(w, outbox):
    c = w["client"]
    assert c.get("/me/emails", headers=headers("free-token")).json() == {"tips": True, "email": "free@example.com"}
    assert c.put("/me/emails", json={"tips": False}, headers=headers("free-token")).json()["tips"] is False
    assert c.get("/me/emails", headers=headers("free-token")).json()["tips"] is False
    assert c.put("/me/emails", json={"tips": "maybe"}, headers=headers("free-token")).status_code == 422
    assert c.get("/me/emails").status_code == 401
    db.update_profile("u-free", created_at=(NOW - timedelta(hours=1)).isoformat())
    assert lifecycle.sweep(NOW) == 0 and outbox == []
    for kind in ("welcome", "day2", "trial_end", "promo_end", "inactive"):
        assert not lifecycle.send(db.get_profile("u-free"), kind, ctx=lifecycle.sample(kind))
    assert outbox == []


def test_every_tip_carries_its_unsubscribe_link_which_works(w, outbox):
    c = w["client"]
    p = user()
    assert lifecycle.send(p, "welcome", now=NOW)
    m = outbox[0]
    link = re.search(r"https?://\S+/unsubscribe\?t=[\w.\-]+", m["text"]).group(0)
    assert link in m["html"] and m["headers"]["List-Unsubscribe"] == f"<{link}>"
    assert m["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    token = link.split("t=")[1]
    assert mail_tokens.read(token, "unsubscribe") == ("u-new", "tips")
    page = c.get("/unsubscribe", params={"t": token})
    assert "tips and reminders" in page.text and lifecycle.tips_on("u-new")             # asking doesn't unsubscribe
    newsletter_prefs.set("u-new", market_in="weekly")
    assert c.post("/unsubscribe", params={"t": token}).status_code == 200
    assert not lifecycle.tips_on("u-new")
    assert newsletter_prefs.get("u-new")["market_in"] == "weekly"                       # newsletters untouched
    everything = mail_tokens.make("u-new", "unsubscribe", "all")
    lifecycle.set_tips("u-new", True)
    c.post("/unsubscribe", params={"t": everything})
    assert not lifecycle.tips_on("u-new") and newsletter_prefs.get("u-new")["market_in"] == "off"


def test_receipts_always_go_once_per_payment(w, outbox):
    p = user(created=NOW - timedelta(days=60))
    lifecycle.set_tips(p["id"], False)
    inv = {"number": "SL/2026-27/0007", "total": 2999.0, "currency": "INR", "date": "2026-10-07", "payment_id": "pay_7"}
    assert lifecycle.receipt(p, inv, "pro", "month")
    assert not lifecycle.receipt(p, inv, "pro", "month")                                 # the webhook again
    assert lifecycle.receipt(p, {**inv, "number": "SL/2026-27/0008", "payment_id": "pay_8"}, "pro", "month")
    assert len(outbox) == 2
    m = outbox[0]
    assert m["subject"] == "Receipt: StratLab Pro plan" and "₹2,999.00" in m["text"] and "SL/2026-27/0007" in m["text"]
    assert m["headers"] is None and "unsubscribe" not in m["text"] and "sent even with tips" in m["text"]
    assert lifecycle.plan_ended(p, "sub_1", "pro") and not lifecycle.plan_ended(p, "sub_1", "pro")
    assert outbox[-1]["subject"] == "Your StratLab plan has changed to Free"


def test_a_payment_sends_its_receipt_and_a_cancellation_its_note(w, outbox, monkeypatch):
    p = user(created=NOW - timedelta(days=60))
    sub = {"id": "sub_9", "notes": {"user_id": p["id"], "plan": "basic", "period": "year"}}
    pay = {"id": "pay_9", "status": "captured", "amount": 999000, "currency": "INR", "created_at": int(NOW.timestamp())}
    inv = billing.invoice_for(p, sub, pay)
    assert inv and inv["payment_id"] == "pay_9"
    billing.invoice_for(p, sub, pay)                                                     # charged webhook after checkout
    assert [m["subject"] for m in outbox] == ["Receipt: StratLab Basic plan"] and "billed yearly" in outbox[0]["text"]
    assert inv["number"] in outbox[0]["text"]
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "whsec")
    monkeypatch.setattr(billing.client().utility, "verify_webhook_signature", lambda *a, **k: True)
    db.update_profile(p["id"], plan="basic", plan_status="active", razorpay_subscription_id="sub_9")
    body = json.dumps({"event": "subscription.cancelled", "payload": {"subscription": {"entity": {**sub, "status": "cancelled"}}}}).encode()
    billing.handle_webhook(body, "abc")
    billing.handle_webhook(body, "abc")
    assert [m["subject"] for m in outbox][1:] == ["Your StratLab plan has changed to Free"]
    assert "Basic subscription has stopped" in outbox[1]["text"]


# ---------- the words ----------
@pytest.mark.parametrize("kind", list(lifecycle.EMAILS))
def test_every_email_is_facts_not_advice_and_names_no_data_source(w, kind):
    subject, html, text = lifecycle.build(kind, {"id": "u", "email": "x@example.com"}, lifecycle.sample(kind, NOW))
    assert subject and escape(subject) in html and "<!doctype html>" in html
    assert not write.banned(text), kind
    for name in ("Kite", "Zerodha", "Yahoo", "Screener", "Finnhub", "Brevo", "Resend"):
        assert name.lower() not in text.lower(), (kind, name)
    assert (write.UNSUBSCRIBE in text) != lifecycle.EMAILS[kind][1]      # tips have the link, receipts don't


def test_dates_in_reminders(w):
    s, _, text = lifecycle.build("trial_before", {}, {"last_day": date(2026, 10, 9)})
    assert s == "Your paper-trading trial ends tomorrow" and "Fri, 9 Oct 2026" in text
    end = datetime(2026, 10, 22, 11, 50, 59, tzinfo=timezone.utc)                  # 17:20 IST: the stored instant is what is said
    s, _, text = lifecycle.build("promo_end", {}, {"last_day": date(2026, 10, 22), "end": end})
    assert s == "The launch offer ends today" and "ends on Thu 22 Oct at 5:20 pm IST." in text and "end of" not in text
    assert "What's new" in lifecycle.build("inactive", {})[0]
    with pytest.raises(ValueError):
        lifecycle.build("nope", {})


def test_a_launch_offer_ending_at_midnight_names_the_day_it_ends(w, monkeypatch):
    # the email's header carries today's date: fixed, so the test reads the same after midnight IST
    monkeypatch.setattr(lifecycle.kit, "today_label", lambda: "Thu 22 Oct")
    midnight = datetime(2026, 10, 22, 18, 30, tzinfo=timezone.utc)                   # 00:00 IST on Fri 23 Oct
    for kind in ("promo_before", "promo_end"):
        _, _, text = lifecycle.build(kind, {}, {"last_day": date(2026, 10, 22), "end": midnight})
        assert "It ends at the end of Thu 22 Oct (India time)." in text and "12:00 am" not in text and "23 Oct" not in text


def test_a_plan_that_ended_says_free_only_when_the_account_is_on_free(w, outbox):
    p = {"id": "u", "email": "x@example.com"}
    _, _, text = lifecycle.build("plan_ended", p, {"plan": "pro"})
    assert "your account is on the Free plan now" in text
    plans._promo.update(read_at=time.monotonic(), until=datetime(2100, 1, 1, tzinfo=timezone.utc))      # the launch offer is on
    subject, _, text = lifecycle.build("plan_ended", p, {"plan": "pro"})
    assert subject == "Your StratLab subscription has stopped"
    assert "Your Pro subscription has stopped." in text and "launch offer" in text and "Free plan" not in text


def test_the_plan_ended_note_reads_the_account_after_the_subscription_ended(w, outbox):
    """The webhook hands over the profile as it was before the plan was set to Free: the note reads it again."""
    p = user(plan="pro", plan_status="active")
    db.update_profile(p["id"], plan="free", plan_status="cancelled")
    assert lifecycle.plan_ended(p, "sub_1", "pro")
    assert outbox[-1]["subject"] == "Your StratLab plan has changed to Free" and "Free plan now" in outbox[-1]["text"]


# ---------- the schedule ----------
def test_job_sweeps_hourly_in_india_daytime_only(w, outbox, monkeypatch):
    calls = []
    monkeypatch.setattr(lifecycle, "sweep", lambda now: calls.append(now) or 0)
    j = lifecycle.Job()
    night = datetime(2026, 10, 6, 20, 0, tzinfo=timezone.utc)                    # 1:30 am IST
    assert j.tick(night) == 0 and calls == []
    j.tick(NOW)
    j.tick(NOW + timedelta(minutes=5))
    assert len(calls) == 1
    assert lifecycle.Job().tick(NOW + timedelta(minutes=10)) == 0 and len(calls) == 1   # restarted: same hour is marked
    j.tick(NOW + timedelta(hours=1))
    assert len(calls) == 2 and j.status["last_run"]


def test_sweep_end_to_end_with_trial_and_offer(w, outbox):
    start = datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)
    last = trading_days(start.astimezone(IST).date(), 5)[-1]
    user("u-t", "t@example.com", start - timedelta(days=40), live_trial_started_at=start.isoformat())
    on = datetime(last.year, last.month, last.day, 5, 0, tzinfo=timezone.utc)
    assert lifecycle.sweep(on) >= 1
    assert any(m["to"] == "t@example.com" and m["subject"] == "Your paper-trading trial ends today" for m in outbox)
    outbox.clear()
    db.set_setting(plans.PROMO_KEY, datetime(2026, 11, 2, 18, 30, tzinfo=timezone.utc).isoformat())   # ends with Mon 2 Nov
    plans._promo.update(read_at=0.0)
    user("u-p", "p@example.com", NOW - timedelta(days=40))
    lifecycle.sweep(datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc))
    assert [m["subject"] for m in outbox if m["to"] in ("p@example.com", "t@example.com")] == ["The launch offer ends tomorrow"] * 2
    assert "ends at the end of Mon 2 Nov (India time)." in outbox[0]["text"]
    lifecycle.sweep(datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc))
    assert len([m for m in outbox if m["to"] == "p@example.com"]) == 1
    lifecycle.sweep(datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc))
    assert [m["subject"] for m in outbox if m["to"] == "p@example.com"][-1] == "The launch offer ends today"
    assert not any(m["to"] == "pro@example.com" for m in outbox)                   # paying users aren't reminded


def test_ends_today_is_never_sent_after_the_end(w, outbox):
    end = datetime(2026, 10, 22, 11, 50, 59, tzinfo=timezone.utc)                  # 17:20 IST
    db.set_setting(plans.PROMO_KEY, end.isoformat())
    plans._promo.update(read_at=0.0)
    user("u-q", "q@example.com", NOW - timedelta(days=40))
    mine = lambda: [m for m in outbox if m["to"] == "q@example.com"]
    lifecycle.sweep(end + timedelta(minutes=10))                                   # 17:30 IST, after the end
    assert not mine()
    lifecycle.sweep(end - timedelta(minutes=20))                                   # 17:00 IST, before it
    assert [m["subject"] for m in mine()] == ["The launch offer ends today"] and "5:20 pm IST" in mine()[0]["text"]


# ---------- admin ----------
def test_admin_preview_and_test_send(w, outbox):
    c = w["client"]
    listed = c.get("/admin/lifecycle", headers=headers("admin-token")).json()
    assert [e["kind"] for e in listed["emails"]] == list(lifecycle.EMAILS) and "job" in listed
    for kind in lifecycle.EMAILS:
        r = c.post(f"/admin/lifecycle/{kind}/preview", headers=headers("admin-token")).json()
        assert r["subject"] and "{unsubscribe_url}" not in r["html"] and r["transactional"] == lifecycle.EMAILS[kind][1]
    r = c.post("/admin/lifecycle/welcome/test", headers=headers("admin-token")).json()
    assert r == {"sent_to": "owner@example.com", "subject": "[Test] Welcome to StratLab"}
    assert outbox[-1]["to"] == "owner@example.com" and "{unsubscribe_url}" not in outbox[-1]["text"]
    assert lifecycle.sent("u-admin") == {}                                      # a test isn't recorded as sent
    assert c.post("/admin/lifecycle/nope/preview", headers=headers("admin-token")).status_code == 404
    assert c.post("/admin/lifecycle/welcome/test", headers=headers("free-token")).status_code == 403
    assert c.get("/admin/lifecycle", headers=headers("pro-token")).status_code == 403


def test_admin_test_send_without_email_set_up(w):
    r = w["client"].post("/admin/lifecycle/receipt/test", headers=headers("admin-token"))
    assert r.status_code == 400 and "isn't set up" in r.json()["detail"]["message"]


# ---------- first steps on Home ----------
def test_first_steps_tick_from_real_data(w):
    c = w["client"]
    db.update_profile("u-free", created_at=datetime.now(timezone.utc).isoformat())
    v = c.get("/me/first-steps", headers=headers("free-token")).json()
    assert v["show"] and [s["id"] for s in v["steps"]] == ["backtest", "watchlist", "deepdive", "paper", "alerts"]
    assert v["done"] == sum(s["done"] for s in v["steps"])
    before = {s["id"]: s["done"] for s in v["steps"]}
    assert not before["backtest"] and not before["deepdive"]
    db.add_usage("u-free", "backtest")
    db.set_setting("watchlist:u-free", json.dumps({"items": [{"region": "IN", "symbol": "TCS"}]}))
    newsletter_prefs.set("u-free", market_in="weekly")
    first_steps.mark("u-free", "deepdive")
    ticks = {s["id"]: s["done"] for s in c.get("/me/first-steps", headers=headers("free-token")).json()["steps"]}
    # a newsletter chosen while the email isn't confirmed sends nothing yet, so the step isn't done (DP2-030)
    assert ticks == {"backtest": True, "watchlist": True, "deepdive": True, "paper": False, "alerts": False}
    db.set_setting(alerts.CONFIRMED + "u-free", "free@example.com")
    ticks = {s["id"]: s["done"] for s in c.get("/me/first-steps", headers=headers("free-token")).json()["steps"]}
    assert ticks == {"backtest": True, "watchlist": True, "deepdive": True, "paper": False, "alerts": True}
    db.sb().table("live_sessions").insert({"user_id": "u-free", "name": "x", "strategy": {}, "instrument": {}}).execute()
    done = c.get("/me/first-steps", headers=headers("free-token")).json()
    assert done["done"] == 5 and not done["show"]                                   # all done: it goes away


def test_opening_a_deep_dive_ticks_its_step(w):
    c = w["client"]
    db.update_profile("u-pro", created_at=datetime.now(timezone.utc).isoformat())
    assert not first_steps.state("u-pro").get("deepdive")
    assert c.get("/research/deep/RELIANCE", headers=headers("pro-token")).status_code == 200
    assert first_steps.state("u-pro")["deepdive"] is True


def test_first_steps_dismiss_and_only_for_new_accounts(w):
    c = w["client"]
    db.update_profile("u-basic", created_at=datetime.now(timezone.utc).isoformat())
    assert c.get("/me/first-steps", headers=headers("basic-token")).json()["show"]
    r = c.put("/me/first-steps", json={"dismissed": True}, headers=headers("basic-token")).json()
    assert r == {"show": False, "dismissed": True, "done": 0, "steps": []}
    assert c.get("/me/first-steps", headers=headers("basic-token")).json()["show"] is False
    assert c.put("/me/first-steps", json={"dismissed": False}, headers=headers("basic-token")).json()["show"]
    db.update_profile("u-basic", created_at=(datetime.now(timezone.utc) - timedelta(days=31)).isoformat())
    assert c.get("/me/first-steps", headers=headers("basic-token")).json()["show"] is False
    assert c.put("/me/first-steps", json={}, headers=headers("basic-token")).status_code == 422
    assert c.get("/me/first-steps").status_code == 401


# ---------- acct4 ----------
def test_the_plan_ended_note_says_free_when_the_account_cannot_be_read_again(w, outbox, monkeypatch):
    """The caller's copy is from before the end (Pro, active): a failed re-read must not word the note from it."""
    p = user("u-gone", "gone@example.com", plan="pro", plan_status="active", razorpay_subscription_id="sub_1",
             current_period_end=(NOW + timedelta(days=20)).isoformat())

    def boom(uid, *a):
        raise RuntimeError("db blip")
    monkeypatch.setattr(lifecycle.db, "get_profile", boom)
    assert lifecycle.plan_ended(p, "sub_1", "pro")
    assert outbox[-1]["subject"] == "Your StratLab plan has changed to Free" and "Pro plan now" not in outbox[-1]["text"]
    plans._promo.update(read_at=time.monotonic(), until=datetime(2100, 1, 1, tzinfo=timezone.utc))      # the launch offer is on
    assert lifecycle.plan_ended(p, "sub_2", "pro")
    assert outbox[-1]["subject"] == "Your StratLab subscription has stopped" and "launch offer" in outbox[-1]["text"]


def test_an_offer_ending_seconds_after_midnight_is_said_as_the_day_before(w, monkeypatch):
    # the email's header carries the day it is sent: fixed here, or the test failed on 22 Oct itself ("22 Oct" not in text)
    monkeypatch.setattr(lifecycle.kit, "today_label", lambda: "Tue 20 Oct")
    end = datetime(2026, 10, 22, 0, 0, 30, tzinfo=IST)                    # 00:00:30 IST on Thu 22 Oct
    assert lifecycle._end_text(end) == "at the end of Wed 21 Oct (India time)"
    assert lifecycle._end_text(datetime(2026, 10, 22, 0, 1, tzinfo=IST)) == "on Thu 22 Oct at 12:01 am IST"
    _, _, text = lifecycle.build("promo_end", {}, {"last_day": date(2026, 10, 21), "end": end})
    assert "It ends at the end of Wed 21 Oct (India time)." in text and "22 Oct" not in text
    p = user(created=NOW - timedelta(days=30))                            # the reminders go on the same days as the words
    on = lambda d: datetime(2026, 10, d, 5, 0, tzinfo=timezone.utc)
    assert lifecycle.due(p, on(20), {}, None, end)[0][1] == "promo_before:2026-10-21"
    assert lifecycle.due(p, on(21), {}, None, end)[0][1] == "promo_end:2026-10-21"


# ---------- R23-005: the welcome says what the Market Brief is on the reader's plan ----------
def test_r23_005_the_welcome_promises_the_brief_the_plan_gives(w):
    daily = "Get the Market Brief: a short email after each market closes."
    free = user("u-free", "free@example.com")
    _, _, text = lifecycle.build("welcome", free)
    assert "a weekly email on Saturday morning on the Free plan" in text and daily not in text
    basic = user("u-basic", "basic@example.com", plan="basic", plan_status="active")
    assert daily in lifecycle.build("welcome", basic)[2]
    plans.set_promo(7)                                                     # the launch offer: daily for now, said with its end
    try:
        text = lifecycle.build("welcome", free)[2]
        assert "a short email after each market closes during the launch offer, which ends on " in text
        assert "then a weekly email on Saturday morning on the Free plan" in text
        assert daily in lifecycle.build("welcome", basic)[2]
    finally:
        plans.set_promo(None)


def test_a_sweep_that_raises_doesnt_use_the_hour_up(w, monkeypatch):
    j = lifecycle.Job()
    monkeypatch.setattr(lifecycle, "sweep", lambda now=None: (_ for _ in ()).throw(RuntimeError("db blip")))
    with pytest.raises(RuntimeError):
        j.tick(NOW)
    assert db.get_setting(lifecycle.MARK) is None
    monkeypatch.setattr(lifecycle, "sweep", lambda now=None: 3)
    assert j.tick(NOW + timedelta(minutes=5)) == 3 and db.get_setting(lifecycle.MARK) is not None
