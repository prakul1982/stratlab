"""Release 53, lane app53: the market mood read written on a clock after each close (LIVE8A-006), bounded."""
from datetime import datetime, timedelta, timezone

from app import main  # noqa: F401, I001
from app import mood_job

IST = timezone(timedelta(hours=5, minutes=30))
ET = timezone(timedelta(hours=-5))


def _job(monkeypatch, answers):
    from app.data import calendar
    from app import stock_pages
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    monkeypatch.setattr(stock_pages, "settling", lambda region, now=None: None)
    store = {}
    monkeypatch.setattr(mood_job, "db", type("D", (), {"get_setting": staticmethod(store.get),
                                                       "set_setting": staticmethod(lambda k, v: store.__setitem__(k, v))}))
    calls = []

    def read(region):
        calls.append(region)
        return answers.pop(0) if answers else {"mood": "x"}
    return mood_job.Job(read), calls


def test_the_read_is_written_after_the_close_once_a_day(monkeypatch):
    job, calls = _job(monkeypatch, [])
    fri = datetime(2026, 11, 13, 15, 50, tzinfo=IST)
    assert job.tick(fri.astimezone(timezone.utc)) == {}                 # before 16:10 IST nothing (the US is before its close too)
    got = job.tick(datetime(2026, 11, 13, 16, 15, tzinfo=IST).astimezone(timezone.utc))
    assert got == {"IN": "written"} and calls == ["IN"]
    job.tick(datetime(2026, 11, 13, 16, 20, tzinfo=IST).astimezone(timezone.utc))
    assert calls == ["IN"]                                                # done for the day
    # the US after its own close
    got = job.tick(datetime(2026, 11, 13, 16, 45, tzinfo=ET).astimezone(timezone.utc))
    assert got.get("US") == "written"
    # Saturday: no session, nothing asked
    job.tick(datetime(2026, 11, 14, 17, 0, tzinfo=IST).astimezone(timezone.utc))
    assert calls == ["IN", "US"]


def test_a_read_not_possible_yet_is_tried_again_until_the_day_is_given_up(monkeypatch):
    job, calls = _job(monkeypatch, [{"unavailable": True, "code": "stale"}, {"unavailable": True, "code": "ai_busy"}])
    t = datetime(2026, 11, 13, 16, 15, tzinfo=IST)
    assert job.tick(t.astimezone(timezone.utc))["IN"] == "stale"
    assert job.tick((t + timedelta(minutes=5)).astimezone(timezone.utc))["IN"] == "ai_busy"
    assert job.tick((t + timedelta(minutes=10)).astimezone(timezone.utc))["IN"] == "written"
    # past 21:00 IST a day not written is left to the first visitor
    job2, calls2 = _job(monkeypatch, [{"unavailable": True}] * 5)
    assert job2.tick(datetime(2026, 11, 13, 21, 5, tzinfo=IST).astimezone(timezone.utc)).get("IN") is None and "IN" not in calls2


def test_settling_closes_wait(monkeypatch):
    job, calls = _job(monkeypatch, [])
    from app import stock_pages
    monkeypatch.setattr(stock_pages, "settling", lambda region, now=None: "2026-11-13" if region == "US" else None)
    assert job.tick(datetime(2026, 11, 13, 16, 45, tzinfo=ET).astimezone(timezone.utc)).get("US") == "settling"
    assert "US" not in calls


def test_it_reads_through_the_pulse_route_as_the_clock(monkeypatch):
    from app.intel import routes
    seen = {}

    def fake(region, focus, refresh, profile):
        seen.update(region=region, refresh=refresh, profile=profile)
        from app.responses import ok
        return ok({"mood": "calm", "region": region})
    monkeypatch.setattr(routes, "pulse_ai", fake)
    assert mood_job._pulse_read("IN") == {"mood": "calm", "region": "IN"}
    assert seen["refresh"] is False and seen["profile"]["id"] == "system:mood"
