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
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, body, html=None, headers=None: sent.append((to, subject, body)))
    return sent


def _week(w, monkeypatch, now):
    """Three users (two new this week, one on Pro), usage, a week of checks, an audited new listing and an error."""
    utc = lambda d: (now - timedelta(days=d)).astimezone(timezone.utc).isoformat()
    until = (max(now, datetime.now(timezone.utc)) + timedelta(days=20)).astimezone(timezone.utc).isoformat()   # paid whenever the test runs
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
    monkeypatch.setattr(settings, "FRONTEND_ORIGINS", ["http://localhost:5500", "https://stratlab.example"])
    monkeypatch.setattr(settings, "PUBLIC_SITE_URL", "https://stratlab.example")       # the admin link is the site's address, not the first origin


def test_the_summary_has_the_weeks_numbers(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        _week(w, monkeypatch, MONDAY)
        subject, text = main.weekly_summary(MONDAY)
        assert "2 new users" in subject and "1 run with failures, 1 listing with problems, 1 server error" in subject
        assert "- 2 new this week, 3 in all" in text
        # b is on Pro with no subscription: given by the owner, not paying (R6V-010: the email said "Paid: Pro 6")
        assert "- Paying: none" in text and "- Given by the owner, not paying: Pro 1" in text and "Paid:" not in text
        assert "- 3 experiments run, 1 AI build" in text
        assert "- 6 runs, 1 with failures: Prices: IN" in text and "Old" not in text
        assert "- India: 2 checked this week, 1 with problems: NEWCO (2 mismatches, 1 error)" in text
        assert "OLDCO" not in text
        assert "- US: audit is off" in text
        assert "- 1 server error this week" in text
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
        assert sent[0][0] == "owner@example.com" and body["text"].splitlines()[0] in sent[0][2]
        assert main.db.get_setting(weekly.WEEK_KEY) is None                       # Monday's still goes out
    finally:
        w["close"]()


def test_the_summary_prints_days_the_way_the_app_does_and_its_email_title_is_the_subject():
    from app import email_kit as kit
    facts = {"stats": {"users": 1, "new": 2, "paid": {}, "experiments": 0, "ai": 0}, "checks": [],
             "audits": {}, "errors": 0, "admin_url": None}
    subject, text = weekly.summary(MONDAY, facts)                                  # Mon 5 Oct: "05 Oct" had a zero in front
    assert text.splitlines()[0] == "StratLab, 28 Sep to 5 Oct 2026"
    html, plain = kit.message(subject, text, "/admin", "Weekly summary", "You get this because you are an admin.")
    assert subject == "StratLab weekly: 2 new users, all quiet"
    assert f"\n{subject}\n" in plain and "\nWeekly: " not in plain and f"{subject}</h1>" in html.replace("\n", "")


# ---------- R23-003: totals that match the list, each error once, and its own label ----------
def test_r23_003_failed_runs_listed_once_each_and_errors_counted_once():
    at = lambda d, h: datetime(2026, 10, d, h, 30, tzinfo=IST).isoformat()      # noqa: E731
    checks = [{"at": at(6, 9), "fail": 1, "failed": ["Prices: IN"]}, {"at": at(7, 9), "fail": 2, "failed": ["Prices: IN", "Prices: US"]},
              {"at": at(8, 9), "fail": 1, "failed": ["Fund"]}, {"at": at(9, 9), "fail": 1, "failed": ["Fund"]},
              {"at": at(10, 9), "fail": 1, "failed": ["Fund"]}] + [{"at": at(11, h), "fail": 0} for h in (9, 10, 11, 12)]
    facts = {"stats": {"users": 9, "new": 4, "paid": {}, "paying": {}, "given": {}, "experiments": 0, "ai": 0}, "checks": checks,
             "audits": {}, "errors": 4, "errors_since_restart": 0, "errors_before_restart": 23,
             "errors_week_since_restart": 0, "errors_week_before_restart": 4, "admin_url": None}
    subject, text = weekly.summary(datetime(2026, 10, 12, 9, 0, tzinfo=IST), facts)
    line = next(x for x in text.splitlines() if x.startswith("- 9 runs, 5 with failures: "))
    assert len(line.split(": ", 1)[1].split("; ")) == 5                                   # five failed runs, five entries
    assert "Prices: IN, Prices: US (Wed 7 Oct, 09:30)" in line
    assert "- Counted: every run of the daily checks in these 7 days, automatic and Run now." in text
    assert "- 4 server errors this week (0 since the last restart, 4 before it)" in text and "23" not in text
    assert subject == "StratLab weekly: 4 new users, 5 runs with failures, 4 server errors"


def test_r23_003_the_weeks_errors_are_split_by_the_restart_not_added_to_it(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        _week(w, monkeypatch, MONDAY)
        started = MONDAY - timedelta(days=2)
        monkeypatch.setattr(main, "SERVER_STARTED_AT", started.isoformat())
        monkeypatch.setattr(main, "RECENT_ERRORS", [{"ref": "A", "at": (MONDAY - timedelta(days=1)).isoformat()},
                                                    {"ref": "B", "at": (MONDAY - timedelta(days=4)).isoformat()},
                                                    {"ref": "C", "at": (MONDAY - timedelta(days=20)).isoformat()}])
        f = main.weekly_facts(MONDAY)
        assert (f["errors"], f["errors_week_since_restart"], f["errors_week_before_restart"]) == (2, 1, 1)
        assert "- 2 server errors this week (1 since the last restart, 1 before it)" in main.weekly_summary(MONDAY)[1]
    finally:
        w["close"]()


def test_r23_003_send_now_is_labelled_weekly_summary(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        labels = []
        monkeypatch.setattr(alerts, "tell_admins", lambda subject, text, label="Admin alert": labels.append(label) or 1)
        assert w["client"].post("/admin/weekly/test", headers=W.headers("admin-token")).status_code == 200
        assert labels == ["Weekly summary"]
    finally:
        w["close"]()


def test_a_failed_build_or_an_unreached_owner_doesnt_use_the_week_up(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        real = main.weekly_facts
        monkeypatch.setattr(main, "weekly_facts", lambda now: (_ for _ in ()).throw(RuntimeError("db blip")))
        try:
            main.send_weekly_summary(MONDAY)
            raise AssertionError("the failure should surface")
        except RuntimeError:
            pass
        assert main.db.get_setting(weekly.WEEK_KEY) is None
        monkeypatch.setattr(main, "weekly_facts", real)
        monkeypatch.setattr(alerts, "tell_admins", lambda *a, **k: 0)                  # the mail service is down
        assert main.send_weekly_summary(MONDAY.replace(hour=10)) is False
        assert main.db.get_setting(weekly.WEEK_KEY) is None
        calls = []
        monkeypatch.setattr(alerts, "tell_admins", lambda *a, **k: calls.append(a) or 1)
        assert main.send_weekly_summary(MONDAY.replace(hour=11)) is True and len(calls) == 1
        assert main.send_weekly_summary(MONDAY.replace(hour=12)) is False and len(calls) == 1
    finally:
        w["close"]()


def test_a_second_container_cant_send_the_week_while_one_is_sending(monkeypatch):
    from app import run_marks
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        run_marks.claim(main.WEEKLY_RUN, weekly.week_of(MONDAY))                        # the other container is mid-send
        calls = []
        monkeypatch.setattr(alerts, "tell_admins", lambda *a, **k: calls.append(a) or 1)
        assert main.send_weekly_summary(MONDAY) is False and calls == []
    finally:
        w["close"]()
