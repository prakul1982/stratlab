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


# ---------- LIVE8A-014: a weekend session found from the exchange's own file of index closes ----------
def test_a_weekend_day_with_an_index_file_is_a_special_session(monkeypatch):
    from app import official_close as oc
    from app.data import calendar as tc
    store, noted = {}, []
    monkeypatch.setattr(oc, "db", type("D", (), {"get_setting": staticmethod(store.get), "set_setting": staticmethod(lambda k, v: store.__setitem__(k, v)),
                                                 "json_value": staticmethod(lambda raw, d: d), "all_settings_with_prefix": staticmethod(lambda p: []),
                                                 "delete_setting": staticmethod(lambda k: None)}))
    monkeypatch.setattr(tc, "is_trading_day", lambda m, d: d.weekday() < 5 and d.isoformat() != "2026-11-10")
    monkeypatch.setattr(tc, "special_days", lambda m: set())
    monkeypatch.setattr(tc, "note_session", lambda m, d: noted.append(str(d)))
    asked = []

    class Files:
        def text(self, url):
            asked.append(url)
            if "ind_close_all_08112026" in url:
                return "Index Name,Index Date,Closing Index Value\nNifty 50,08-11-2026,24986.40\n"
            return ""
    monkeypatch.setitem(oc._src, "files", lambda: Files())
    oc.forget()
    now = datetime(2026, 11, 14, 8, 0, tzinfo=IST)
    assert oc.find_sessions(now) == ["2026-11-08"] and noted == ["2026-11-08"]
    # the shut days only (weekends and the 10 Nov holiday), never a trading day
    assert not any("13112026" in u or "12112026" in u for u in asked)
    assert any("10112026" in u for u in asked)
    # once a day
    n = len(asked)
    assert oc.find_sessions(now) == [] and len(asked) == n


# ---------- LIVE8A-015: "Coming up" after the close starts tomorrow ----------
def test_coming_up_after_the_close_starts_tomorrow(monkeypatch):
    from datetime import date
    from app.data import calendar
    from app.intel import mood
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    fri = date(2026, 11, 13)
    assert mood.coming_from("US", fri, datetime(2026, 11, 13, 21, 45, tzinfo=ET)) == date(2026, 11, 14)
    assert mood.coming_from("US", fri, datetime(2026, 11, 13, 11, 0, tzinfo=ET)) == fri
    assert mood.coming_from("IN", fri, datetime(2026, 11, 13, 16, 0, tzinfo=IST)) == date(2026, 11, 14)
    # a Saturday keeps its own results (Indian companies report on Saturdays)
    sat = date(2026, 11, 14)
    assert mood.coming_from("IN", sat, datetime(2026, 11, 14, 8, 0, tzinfo=IST)) == sat
