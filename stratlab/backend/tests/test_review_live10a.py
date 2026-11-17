"""LIVE10A (17 Nov 2026): the scored live review of Release 60. Each test fails before its fix and passes after."""
from datetime import datetime, timedelta, timezone

from app import main  # noqa: F401, I001
from app import autofix, mood_job

IST = timezone(timedelta(hours=5, minutes=30))
ET = timezone(timedelta(hours=-5))


def _job(monkeypatch, read=None, mood=None):
    from app.data import calendar
    from app import stock_pages
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    monkeypatch.setattr(stock_pages, "settling", lambda region, now=None: None)
    store = {}
    monkeypatch.setattr(mood_job, "db", type("D", (), {"get_setting": staticmethod(store.get),
                                                       "set_setting": staticmethod(lambda k, v: store.__setitem__(k, v))}))
    return mood_job.Job(read or (lambda region: {"mood": "x"}), mood or (lambda region, day: day))


# ---------- LIVE10A-001: the after-close mood read runs on the clock and a late one is seen ----------
def test_india_read_is_tried_once_the_closing_auction_is_done(monkeypatch):
    job = _job(monkeypatch)
    # 16:05 IST on 17 Nov: the reviewer's visit got the 14:47 intraday read; the job now has written the closing read by then
    assert job.tick(datetime(2026, 11, 17, 15, 50, tzinfo=IST).astimezone(timezone.utc)) == {"IN": "written"}
    assert job.tick(datetime(2026, 11, 17, 15, 40, tzinfo=IST).astimezone(timezone.utc)) == {}


def test_a_read_still_not_written_an_hour_after_its_time_is_a_self_healing_check(monkeypatch):
    job = _job(monkeypatch, mood=lambda region, day: "2026-11-13")          # the tables never reach the session that closed
    t = datetime(2026, 11, 16, 16, 45, tzinfo=ET).astimezone(timezone.utc)
    job.tick(t)
    assert job.late("US", t) is None                                        # five minutes in: not late yet
    later = datetime(2026, 11, 16, 17, 45, tzinfo=ET).astimezone(timezone.utc)
    job.tick(later)
    why = job.late("US", later)
    assert why and "2026-11-16" in why and "tables of 2026-11-13" in why
    checks = {c.id: c for c in job.checks(later)}
    assert checks["job:mood-read:US"].problem == why and checks["job:mood-read:US"].fix is not None
    # written: no longer late
    job.mood = lambda region, day: day
    job.tick(later)
    assert job.late("US", later) is None
    # the self-healing sweep lists both markets' checks
    ids = {c.id for src in autofix._sources if src.__module__ == "app.mood_job" for c in src()}
    assert {"job:mood-read:IN", "job:mood-read:US"} <= ids


def test_a_market_hours_copy_served_after_the_close_says_it_was_read_during_the_session(monkeypatch):
    from app.intel import mood
    m = mood.Mood(hub=None)
    m._seeded.add("IN")
    m.payloads.put("IN", {"session": "2026-11-17", "is_open": True, "headline": "x so far today", "lines": []}, 0.0)
    monkeypatch.setattr(m, "_session_now", lambda region: "2026-11-17")
    monkeypatch.setattr(m, "_build_kept", lambda region, force=False: {"session": "2026-11-17", "is_open": False})
    from app.intel import company
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    got, _ = m.get("IN", wait=0)
    assert got["during"] is True and got["is_open"] is False and got["refreshing"] is True
