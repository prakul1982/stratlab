"""The owner's Monday email: the week's numbers, sent once a week, and a button to send it now."""
import json
from datetime import datetime, timedelta, timezone

from app import alerts, main, weekly
from app.config import settings
from app.kite_service import IST

MONDAY = datetime(2026, 10, 5, 9, 0, tzinfo=IST)


def _smtp(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_USER", "bot@example.com")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pw")
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, body: sent.append((to, subject, body)))
    return sent


def _week(w, monkeypatch, now):
    """Three users (two new this week, one on Pro), usage, a week of checks, an audited new listing and an error."""
    utc = lambda d: (now - timedelta(days=d)).astimezone(timezone.utc).isoformat()
    until = (now + timedelta(days=20)).astimezone(timezone.utc).isoformat()
    w["db"].tables["profiles"] = [
        {"id": "a", "email": "a@x.com", "plan": "free", "created_at": utc(40)},
        {"id": "b", "email": "b@x.com", "plan": "pro", "plan_status": "active", "current_period_end": until, "created_at": utc(2)},
        {"id": "c", "email": "c@x.com", "plan": "free", "created_at": utc(1)}]
    w["db"].tables["usage_events"] = [{"user_id": "b", "kind": "backtest", "created_at": utc(1)}] * 3 + [
        {"user_id": "b", "kind": "ai", "created_at": utc(1)}, {"user_id": "b", "kind": "backtest", "created_at": utc(20)}]
    hist = [{"at": utc(d), "auto": True, "pass": 20, "warn": 0, "fail": 0, "failed": []} for d in range(1, 7)]
    hist[2].update(fail=1, failed=["Prices: IN"])
    hist.insert(0, {"at": utc(10), "auto": True, "pass": 0, "warn": 0, "fail": 5, "failed": ["Old"]})   # last week's
    main.db.set_setting(main.PLATFORM_HISTORY, json.dumps(hist))
    m = main.market_audit
    m.loaded, m.state["enabled"] = True, True
    m.rows = {"NEWCO": {"symbol": "NEWCO", "at": utc(3), "issues": [{"area": "price", "level": "mismatch"}] * 2 + [{"area": "news", "level": "error"}]},
              "FINE": {"symbol": "FINE", "at": utc(2), "issues": []},
              "OLDCO": {"symbol": "OLDCO", "at": utc(15), "issues": [{"area": "price", "level": "error"}]}}
    main.market_audit_us.loaded = True
    monkeypatch.setattr(main, "RECENT_ERRORS", [{"ref": "A1", "at": (now - timedelta(days=1)).isoformat()},
                                                {"ref": "B2", "at": (now - timedelta(days=9)).isoformat()}])
    monkeypatch.setattr(settings, "FRONTEND_ORIGINS", ["https://stratlab.example", "http://localhost:5500"])


def test_the_summary_has_the_weeks_numbers(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        _week(w, monkeypatch, MONDAY)
        subject, text = main.weekly_summary(MONDAY)
        assert "2 new users" in subject and "3 things to look at" in subject
        assert "- 2 new this week, 3 in all" in text
        assert "- Paid: Pro 1" in text
        assert "- 3 experiments run, 1 AI build" in text
        assert "- 6 runs, 1 with failures: Prices: IN" in text and "Old" not in text
        assert "- India: 2 checked this week, 1 with problems: NEWCO (2 mismatches, 1 error)" in text
        assert "OLDCO" not in text
        assert "- US: audit is off" in text
        assert "- 1 error this week" in text
        assert text.endswith("Admin page: https://stratlab.example/admin")
    finally:
        w["close"]()


def test_a_quiet_week_says_so():
    facts = {"stats": {"users": 1, "new": 0, "paid": {}, "experiments": 0, "ai": 0}, "checks": [],
             "audits": {"India": {"enabled": True, "checked": 0, "issues": []}}, "errors": 0, "admin_url": None}
    subject, text = weekly.summary(MONDAY, facts)
    assert subject == "StratLab weekly: 0 new users, all quiet"
    assert "- Paid: none" in text and "- None ran this week" in text and "no mismatches or errors" in text
    assert "Admin page" not in text


def test_it_goes_out_on_monday_morning_once_a_week(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        sent = _smtp(monkeypatch)
        assert not main.send_weekly_summary(MONDAY - timedelta(minutes=1))          # Monday 8:59
        assert not main.send_weekly_summary(MONDAY - timedelta(days=1, hours=-3))   # Sunday
        assert main.send_weekly_summary(MONDAY)
        assert len(sent) == 1 and sent[0][0] == "owner@example.com" and sent[0][1].startswith("StratLab weekly")
        assert not main.send_weekly_summary(MONDAY + timedelta(hours=3))             # a restart later that morning
        assert not main.send_weekly_summary(MONDAY + timedelta(days=1))
        assert main.send_weekly_summary(MONDAY + timedelta(days=7, minutes=5))       # next Monday
        assert len(sent) == 2
        assert weekly.next_send(MONDAY) == MONDAY + timedelta(days=7)
        assert weekly.next_send(MONDAY - timedelta(hours=1)) == MONDAY
        assert weekly.next_send(datetime(2026, 10, 3, 18, 0, tzinfo=IST)) == MONDAY  # from a Saturday
    finally:
        w["close"]()


def test_admin_can_send_it_now_and_no_one_else_can(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        sent = _smtp(monkeypatch)
        for token in ("pro-token", "email-signup-admin-token"):
            assert w["client"].post("/admin/weekly/test", headers=W.headers(token)).status_code == 403
        assert w["client"].post("/admin/weekly/test").status_code in (401, 403)
        assert sent == []
        r = w["client"].post("/admin/weekly/test", headers=W.headers("admin-token"))
        assert r.status_code == 200
        body = r.json()
        assert body["reached"] == 1 and body["subject"].startswith("StratLab weekly") and "Users" in body["text"]
        assert sent[0][0] == "owner@example.com" and sent[0][2] == body["text"]
        assert main.db.get_setting(weekly.WEEK_KEY) is None                       # Monday's still goes out
    finally:
        w["close"]()
