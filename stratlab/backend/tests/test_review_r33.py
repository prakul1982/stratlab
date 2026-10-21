"""Round 33 review (plans, emails, breadth): every clock is passed in; nothing depends on the time of day."""
from app import admin_jobs, breadth, email_kit as kit, email_previews as P, live


def test_update_failed_only_when_the_run_failed_and_prices_are_older_than_the_due_day():
    pending = {"day": "2026-10-15", "due": "5:55 PM ET"}
    failed = {"US": {"as_of": "2026-10-14", "last_error": "boom", "ran_at": "2026-10-14T21:55:00+00:00", "failed_at": "2026-10-15T21:50:00+00:00"}}
    assert breadth.update_failed("US", pending, failed)
    assert not breadth.update_failed("US", pending, {"US": {"as_of": "2026-10-14", "last_error": None, "ran_at": "2026-10-14T21:55:00+00:00"}})   # no failed run: still due
    assert not breadth.update_failed("US", pending, {"US": {"as_of": "2026-10-15", "last_error": "late"}})     # the day is in
    assert not breadth.update_failed("US", {**pending, "during": True}, failed)                                  # session still trading
    assert not breadth.update_failed("US", None, failed)
    assert not breadth.update_failed("IN", pending, failed)                                                      # another market's run


def test_the_jobs_table_names_the_time_the_page_gives(monkeypatch):
    import inspect
    assert "5:55 PM" in breadth.due_label("US")
    src = inspect.getsource(admin_jobs)
    assert "5:45 PM New York" not in src and "due_label('US')" in src


def test_the_scan_alert_email_links_to_the_scan_page():
    _, html, text = P._scan()
    assert "/research/scan" in html and "/research/scan" in text
    assert kit.BUTTONS["/research/scan"] == "Open the scan"


def test_an_admin_alert_body_does_not_repeat_its_title():
    title = "Kite login failed"
    for body in (title + ".\nThe token was cancelled.", title + "\nThe token was cancelled."):
        html, text = kit.message(title, body, "/admin", "Admin alert", "why")
        assert text.lower().count(title.lower()) == 1, text
        assert "The token was cancelled." in text
    # a body that is only the title still says something
    assert "Kite login failed" in kit.message(title, title + ".", "/admin", "Admin alert", "why")[1]


def test_a_free_trial_that_ended_stops_the_sessions_with_that_reason(monkeypatch):
    class Sess:
        id, user_id, kind, started_at, strategy, inst = "1", "u1", "single", "1", None, None
    monkeypatch.setattr(live, "LiveSession", Sess)
    monkeypatch.setattr(live, "trial_state", lambda profile: {"active": False, "started": True})
    monkeypatch.setattr(live.db, "get_profile", lambda uid: {"id": uid, "plan": "free", "plan_status": "active"})
    stopped = {}
    m = live.LiveManager.__new__(live.LiveManager)
    m.sessions = {"1": Sess()}
    m.stop = lambda sid, why: stopped.__setitem__(sid, why)
    m._enforce_plans([Sess()])
    assert stopped == {"1": "Free live trial ended. Upgrade to keep paper trading."}
