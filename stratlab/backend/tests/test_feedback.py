"""Help & feedback (owner, 4 Nov): a report from anyone, checked and throttled, kept in the settings store (the last 1,000),
listed and marked in Admin → Feedback only by an admin, with nothing personal attached; and each one emailed to the admins
within a daily cap, after it is saved, never losing a report when the mail fails."""
import json

import pytest

from app import alerts, db, feedback, main
from app.config import settings
from tests import world as W
from tests.fake_db import headers

ADMIN, PRO, FREE = headers("admin-token"), headers("pro-token"), headers("free-token")
GOOD = {"type": "broken", "text": "The chart on TCS shows no candles after I switch to 1h.", "path": "/research/IN/TCS?tab=chart#x",
        "version": "abc1234", "browser": "Chrome 130 on Android", "screen": "390×844"}


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    with main._recent_lock:
        for k in [k for k in main._recent if k[1] == "feedback"]:
            del main._recent[k]
    monkeypatch.setattr(feedback, "SEND_IN_BACKGROUND", False)
    sent = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, body, html=None, headers=None: sent.append((to, subject, body)))
    world["sent"] = sent
    yield world
    world["close"]()


def test_a_signed_in_report_is_kept_with_only_what_helps_and_shows_in_the_inbox(w):
    c = w["client"]
    r = c.post("/feedback", headers=PRO, json={**GOOD, "reply": True, "email": "someone@else.com", "token": "eyJhbGciOi", "password": "x"})
    assert r.status_code == 200 and r.json()["ok"] is True
    rows = c.get("/admin/feedback", headers=ADMIN).json()["rows"]
    got = rows[0]
    assert got["type"] == "broken" and got["text"] == GOOD["text"] and got["status"] == "new"
    assert got["path"] == "/research/IN/TCS"                          # no query or fragment: they can hold a token or a search
    assert got["plan"] == "pro" and got["signed_in"] is True and got["reply"] is True
    assert got["reply_to"] == "pro@example.com"                        # the account's own address, never the typed one
    assert "user_id" not in got and "token" not in got and "password" not in got and "email" not in got
    assert set(got) == {"id", "at", "type", "text", "path", "version", "browser", "screen", "plan", "signed_in", "reply", "reply_to", "status"}
    assert c.get("/admin/overview", headers=ADMIN).json()["server"]["feedback_new"] == 1


def test_a_signed_out_report_keeps_a_reply_address_only_when_asked(w):
    c = w["client"]
    assert c.post("/feedback", json={**GOOD, "type": "idea", "reply": False, "email": "a@b.co"}).status_code == 200
    assert c.post("/feedback", json={**GOOD, "type": "not_working", "reply": True, "email": "Visitor@Example.com"}).status_code == 200
    rows = c.get("/admin/feedback", headers=ADMIN).json()["rows"]
    assert [(r["type"], r["plan"], r["signed_in"], r["reply_to"]) for r in rows] == [
        ("not_working", "signed out", False, "visitor@example.com"), ("idea", "signed out", False, None)]


def test_bad_reports_are_refused_in_words(w):
    c = w["client"]
    assert c.post("/feedback", headers=PRO, json={**GOOD, "type": "spam"}).status_code == 422
    assert c.post("/feedback", headers=PRO, json={**GOOD, "text": ""}).status_code == 422
    assert c.post("/feedback", headers=PRO, json={**GOOD, "text": "x" * (feedback.MAX_TEXT + 1)}).status_code == 422
    r = c.post("/feedback", headers=PRO, json={**GOOD, "text": "  hi \n"})
    assert r.status_code == 400 and "few words" in r.json()["detail"]["message"]
    r = c.post("/feedback", json={**GOOD, "reply": True, "email": "not-an-address"})
    assert r.status_code == 400 and "email" in r.json()["detail"]["message"]
    assert c.post("/feedback", headers={"Authorization": "Bearer nope"}, json=GOOD).status_code == 401
    assert feedback._load() == []


def test_reports_are_throttled_per_person_and_more_strictly_per_address_when_signed_out(w):
    c = w["client"]
    for _ in range(feedback.SIGNED_OUT_HOUR):
        assert c.post("/feedback", json=GOOD).status_code == 200
    assert c.post("/feedback", json=GOOD).status_code == 429
    for _ in range(feedback.SIGNED_IN_HOUR):
        assert c.post("/feedback", headers=PRO, json=GOOD).status_code == 200
    assert c.post("/feedback", headers=PRO, json=GOOD).status_code == 429
    assert c.post("/feedback", headers=FREE, json=GOOD).status_code == 200          # another person has their own allowance


def test_only_an_admin_lists_filters_and_marks_reports(w):
    c = w["client"]
    c.post("/feedback", headers=PRO, json=GOOD)
    c.post("/feedback", headers=PRO, json={**GOOD, "type": "idea"})
    for h in (PRO, FREE, {}):
        assert c.get("/admin/feedback", headers=h).status_code in (401, 403)
    rows = c.get("/admin/feedback", headers=ADMIN).json()["rows"]
    fid = rows[0]["id"]
    for h in (PRO, {}):
        assert c.put(f"/admin/feedback/{fid}", headers=h, json={"status": "fixed"}).status_code in (401, 403)
    assert c.put(f"/admin/feedback/{fid}", headers=ADMIN, json={"status": "fixed"}).json()["status"] == "fixed"
    assert c.put(f"/admin/feedback/{fid}", headers=ADMIN, json={"status": "gone"}).status_code == 422
    assert c.put("/admin/feedback/nope", headers=ADMIN, json={"status": "seen"}).status_code == 404
    body = c.get("/admin/feedback?status=fixed", headers=ADMIN).json()
    assert [r["id"] for r in body["rows"]] == [fid] and body["counts"] == {"new": 1, "seen": 0, "fixed": 1}
    assert [r["type"] for r in c.get("/admin/feedback?type=broken", headers=ADMIN).json()["rows"]] == ["broken"]


def test_the_store_keeps_the_last_reports_only(w, monkeypatch):
    monkeypatch.setattr(feedback, "MAX_KEPT", 3)
    monkeypatch.setattr(feedback, "SIGNED_IN_HOUR", 99)
    for i in range(5):
        w["client"].post("/feedback", headers=PRO, json={**GOOD, "text": f"report number {i}"})
    assert [r["text"] for r in feedback._load()] == ["report number 2", "report number 3", "report number 4"]


def test_each_report_is_emailed_to_the_admins_with_its_facts_and_nothing_personal(w):
    w["client"].post("/feedback", headers=PRO, json={**GOOD, "reply": True})
    (to, subject, body), = w["sent"]
    assert to == "owner@example.com"
    assert subject == "[StratLab feedback] Something's broken: The chart on TCS shows no candles after I switch to 1h."
    for line in ("Type: Something's broken", "Page: /research/IN/TCS", "Plan: pro", "Signed in: yes", "Reply wanted: yes", GOOD["text"]):
        assert line in body, line
    assert "pro@example.com" not in body and "u-pro" not in body and "Chrome" not in body


def test_the_emails_stop_at_the_daily_cap_and_the_next_day_says_how_many_waited(w, monkeypatch):
    monkeypatch.setattr(settings, "FEEDBACK_EMAILS_PER_DAY", 2)
    monkeypatch.setattr(feedback, "SIGNED_IN_HOUR", 99)
    for i in range(5):
        w["client"].post("/feedback", headers=PRO, json={**GOOD, "text": f"report number {i}"})
    assert len(w["sent"]) == 2 and len(feedback._load()) == 5                 # every report kept, two emails
    assert json.loads(db.get_setting(feedback.MAIL_KEY))["held"] == 3
    st = json.loads(db.get_setting(feedback.MAIL_KEY))
    db.set_setting(feedback.MAIL_KEY, json.dumps({**st, "day": "2000-01-01"}))     # a new day
    w["client"].post("/feedback", headers=PRO, json={**GOOD, "text": "the next morning"})
    assert len(w["sent"]) == 3 and "3 more reports came in yesterday" in w["sent"][-1][2]


def test_a_mail_failure_or_no_mail_set_up_never_loses_a_report(w, monkeypatch):
    monkeypatch.setattr(alerts, "send_email", lambda *a, **k: (_ for _ in ()).throw(OSError("brevo down")))
    assert w["client"].post("/feedback", headers=PRO, json=GOOD).status_code == 200
    monkeypatch.setattr(alerts, "email_ready", lambda: False)
    assert w["client"].post("/feedback", headers=PRO, json=GOOD).status_code == 200
    monkeypatch.setattr(settings, "FEEDBACK_EMAILS", False)
    assert w["client"].post("/feedback", headers=PRO, json=GOOD).status_code == 200
    assert len(feedback._load()) == 3
