"""Admin's status in one reading (the feed counts only the India sessions that need it; the email service is named once),
a job whose run read some sources and not others (Check, in words, never a raw error class), every Run now recorded
like a scheduled run, the Users list by plan, and Account's sign-in method and hand-given plans."""
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import admin_jobs, alerts, main
from app.config import settings
from tests import world as W
from tests.fake_db import headers

ADMIN = headers("admin-token")


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def _jobs(c) -> dict:
    return {j["id"]: j for j in c.get("/admin/jobs", headers=ADMIN).json()["jobs"]}


def test_plain_error_drops_the_error_class_but_keeps_the_words():
    assert admin_jobs.plain_error("Couldn't reach www.rbi.org.in (ConnectError).") == "Couldn't reach www.rbi.org.in."
    assert admin_jobs.plain_error("x: timed out (httpx.ReadTimeout)") == "x: timed out"
    assert admin_jobs.plain_error("The PDF couldn't be read (ValueError).") == "The PDF couldn't be read."
    assert admin_jobs.plain_error("RBI (MPC) answered 503.") == "RBI (MPC) answered 503."       # words in brackets stay
    assert admin_jobs.plain_error(None) is None


def test_a_partial_run_is_check_with_how_many_sources_were_read(w, monkeypatch):
    from app import market_events_routes as r
    monkeypatch.setattr(r.job, "status", dict(r.job.status))
    now = datetime.now(timezone.utc)
    rbi = "Central bank (MPC): Couldn't reach www.rbi.org.in (ConnectError)."
    r.job.record(now, [rbi], 5)
    row = _jobs(w["client"])["events"]
    assert row["state"] == "warn"
    assert row["error"] == "Partial: 4 of 5 sources read. Not read: Central bank (MPC): Couldn't reach www.rbi.org.in."
    assert row["log"] == [rbi]                                  # the log keeps the whole text
    r.job.record(now, [rbi, "US Fed (FOMC): federalreserve.gov answered 503."], 5)
    assert _jobs(w["client"])["events"]["error"].endswith("And 1 more (see the log).")
    r.job.record(now, [f"source {i}: down" for i in range(5)], 5)                # nothing read: a problem
    assert _jobs(w["client"])["events"]["state"] == "bad"
    r.job.record(now, [], 5)                                                         # a good run clears it
    row = _jobs(w["client"])["events"]
    assert row["state"] == "ok" and row["error"] is None and row["last_run"]


def test_run_now_records_its_run_like_the_clock_does(w, monkeypatch):
    """A Run now that went well clears an older run's problem (it used to keep showing until the next scheduled run)."""
    from app import market_events as M, market_events_routes as r, surveillance
    c = w["client"]
    monkeypatch.setattr(r.job, "status", dict(r.job.status))
    monkeypatch.setattr(main.surv_job, "status", dict(main.surv_job.status))
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    r.job.record(old, ["Central bank (MPC): down"], 5)
    main.surv_job.record(old, ["asm: down"], len(surveillance.PARTS))
    monkeypatch.setattr(M, "refresh", lambda web=None, today=None, now=None, only=None: {"problems": [], "read": [n for n, _ in M.READERS]})
    monkeypatch.setattr(surveillance, "refresh", lambda feed, today=None, now=None: {"changes": [], "problems": []})
    assert c.post("/admin/events/refresh", headers=ADMIN).json()["started"] is True
    for _ in range(100):
        if r.job.status.get("last_error") is None:
            break
        time.sleep(0.05)
    assert c.post("/admin/surveillance/refresh", headers=ADMIN).status_code == 200
    jobs = _jobs(c)
    for id in ("events", "surveillance"):
        assert jobs[id]["state"] == "ok" and jobs[id]["error"] is None, jobs[id]
        assert jobs[id]["last_run"] > old.isoformat()


def test_the_feed_counts_only_india_sessions_and_the_email_service_is_named(w, monkeypatch):
    c = w["client"]
    us = SimpleNamespace(polled=True)
    monkeypatch.setattr(main.manager, "sessions", {"a": us})
    sv = c.get("/admin/overview", headers=ADMIN).json()["server"]
    assert sv["live_sessions"] == 1 and sv["india_sessions"] == 0
    monkeypatch.setattr(main.manager, "sessions", {"a": us, "b": SimpleNamespace(polled=False)})
    assert c.get("/admin/overview", headers=ADMIN).json()["server"]["india_sessions"] == 1
    for k in ("BREVO_API_KEY", "RESEND_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.setattr(settings, k, "")
    assert alerts.email_service() is None and alerts.email_ready() is False
    assert c.get("/admin/overview", headers=ADMIN).json()["server"]["admin_alerts"]["via"] is None
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.setattr(settings, k, "x")
    assert alerts.email_service() == "SMTP"
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_x")
    mail = c.get("/admin/overview", headers=ADMIN).json()["server"]["admin_alerts"]
    assert mail["email_ready"] is True and mail["via"] == "Resend"
    monkeypatch.setattr(settings, "BREVO_API_KEY", "b_x")
    assert alerts.email_service() == "Brevo"                  # the order send_email tries them in


def test_overview_tells_paying_users_from_plans_the_owner_gave(w):
    from app import db
    c = w["client"]
    st = c.get("/admin/overview", headers=ADMIN).json()["stats"]
    assert st["paying"] == {"basic": 0, "pro": 0}                        # the fake world's paid plans are all given by hand
    assert st["given"] == {"basic": st["plans"]["basic"], "pro": st["plans"]["pro"]}
    db.update_profile("u-basic", razorpay_subscription_id="sub_1")
    st = c.get("/admin/overview", headers=ADMIN).json()["stats"]
    assert st["paying"]["basic"] == 1 and st["given"]["basic"] == st["plans"]["basic"] - 1


def test_users_by_plan(w):
    c = w["client"]
    pro = c.get("/admin/users?plan=pro", headers=ADMIN).json()
    assert pro and all(u["plan"] == "pro" for u in pro)
    free = c.get("/admin/users?plan=free&q=load1", headers=ADMIN).json()
    assert free and all(u["plan"] == "free" and "load1" in u["email"] for u in free)
    every = c.get("/admin/users", headers=ADMIN).json()
    assert {u["plan"] for u in every} == {"free", "basic", "pro"}
    assert c.get("/admin/users?plan=gold", headers=ADMIN).status_code == 400
    assert c.get("/admin/users?plan=pro", headers=headers("pro-token")).status_code in (401, 403)


def test_me_gives_the_plans_own_limits_and_what_lifts_them(w, monkeypatch):
    """Account lists the same monthly limits as the Plans page, and says when early access or the launch offer lifts them."""
    from app import plans
    c = w["client"]
    for mod in (plans, main):
        monkeypatch.setattr(mod, "payments_live", lambda: False)
    u = c.get("/me", headers=headers("free-token")).json()["usage"]
    assert u["deepdive_plan_limit"] == plans.PLANS["free"]["deepdives_per_month"] == 2
    assert u["deck_plan_limit"] == plans.PLANS["free"]["decks_per_month"] == 1
    # payments off no longer lifts anything (the owner's decision, 7 Oct): Free's own limit, nothing lifting it
    assert u["deepdive_limit"] == 2 and u["lifted_by"] is None
    for mod in (plans, main):
        monkeypatch.setattr(mod, "payments_live", lambda: True)
    u = c.get("/me", headers=headers("free-token")).json()["usage"]
    assert u["deepdive_limit"] == 2 and u["lifted_by"] is None
    assert c.get("/me", headers=headers("pro-token")).json()["usage"]["deepdive_plan_limit"] is None


def test_deleting_your_own_data_needs_your_email_typed_in(w, monkeypatch):
    from app import user_data
    c = w["client"]
    ran: list[str] = []
    monkeypatch.setattr(user_data, "erase", lambda uid: ran.append(uid) or {"done": [{"key": "holdings", "label": "Holdings", "count": 1}], "failed": []})
    assert c.post("/me/delete-data", json={"confirm": "free@example.com"}).status_code == 401
    r = c.post("/me/delete-data", headers=headers("free-token"), json={"confirm": "someone@else.com"})
    assert r.status_code == 400 and "confirm_mismatch" in r.text
    assert c.post("/me/delete-data", headers=headers("free-token"), json={"confirm": ""}).status_code in (400, 422)
    assert ran == []
    r = c.post("/me/delete-data", headers=headers("free-token"), json={"confirm": "  FREE@example.com "})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert ran == ["u-free"]                                   # only your own data, never another account's


def test_download_all_my_data_is_your_own_rows_without_secrets(w):
    from app import user_data
    from app.connect import state
    c = w["client"]
    assert c.get("/me/export").status_code == 401
    # the fake world's owner has imported holdings; give them a sealed broker token too, which must never come out
    state.update("u-admin", "kite", token="sealed-abc", status="ok", kite_user="AB1234")
    r = c.get("/me/export", headers=ADMIN)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert data["profile"]["email"] == "owner@example.com" and data["profile"]["id"] == "u-admin"
    assert {k for k, _, _ in user_data.EXPORT} <= set(data)
    assert data["not_included"] == [], data["not_included"]
    text = r.text
    for secret in ("sealed-abc", "razorpay_", "\"token\"", "\"password\""):
        assert secret not in text
    other = c.get("/me/export", headers=headers("free-token")).json()
    assert data["connected_accounts"]["kite"]["kite_user"] == "AB1234"
    assert other["profile"]["id"] == "u-free" and "kite" not in other["connected_accounts"]     # only your own rows
    assert user_data._clean({"a": 1, "inbox_password": "x", "api_key": "y", "author": "z", "keys": {"p": 1}}) == {"a": 1, "author": "z"}


def test_me_says_how_you_signed_in_and_whether_the_owner_gave_the_plan(w):
    from app import db
    c = w["client"]
    me = c.get("/me", headers=headers("pro-token")).json()
    assert me["signed_in_with"] == "google"
    assert me["billing"]["given_by_owner"] is True                 # Pro by hand: nothing renews, nothing to cancel
    assert c.get("/me", headers=headers("email-signup-admin-token")).json()["signed_in_with"] == "email"
    free = c.get("/me", headers=headers("free-token")).json()
    assert free["billing"]["given_by_owner"] is False
    db.update_profile("u-basic", razorpay_subscription_id="sub_123")
    assert c.get("/me", headers=headers("basic-token")).json()["billing"]["given_by_owner"] is False   # a subscription
