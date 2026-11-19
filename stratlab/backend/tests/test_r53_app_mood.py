"""Release 53, lane app53: the market mood read written on a clock after each close (LIVE8A-006), bounded."""
from datetime import datetime, timedelta, timezone

from app import main  # noqa: F401, I001
from app import mood_job

IST = timezone(timedelta(hours=5, minutes=30))
ET = timezone(timedelta(hours=-5))


def _job(monkeypatch, answers, mood=None):
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
    # (updated on purpose, LIVE9A-001: the job reads the Mood card's payload too; here it is always of the day asked for)
    return mood_job.Job(read, mood or (lambda region, day: day)), calls


def test_the_read_is_written_after_the_close_once_a_day(monkeypatch):
    job, calls = _job(monkeypatch, [])
    # (updated on purpose, LIVE10A-001: India's read is first tried at 15:45 IST, after the closing auction, no longer 16:10)
    fri = datetime(2026, 11, 13, 15, 40, tzinfo=IST)
    assert job.tick(fri.astimezone(timezone.utc)) == {}                 # before 15:45 IST nothing (the US is before its close too)
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


# ---------- LIVE8A-016: an SME issue's latest close is the exchange's, past a candle series that runs behind ----------
def test_an_issues_closes_past_its_last_candle_come_from_the_exchange(monkeypatch):
    from datetime import date
    from app import ipo, official_close
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    closes = {"2026-11-12": 290.10, "2026-11-13": 274.70}
    monkeypatch.setattr(ipo, "_official", lambda sym, day, now, fetch: closes.get(day) if sym == "MAXENGS" else None)
    monkeypatch.setattr(official_close, "same_basis", lambda a, b: True)
    monkeypatch.setattr(official_close, "out_at", lambda day, kind: datetime.fromisoformat(f"{day}T18:00:00+05:30"))
    row = {"market": "IN", "symbol": "MAXENGS", "segment": "sme", "listing": "2026-11-05", "price": 280.0}
    bars = [{"t": "2026-11-10", "o": 300, "h": 310, "l": 295, "c": 301.0}, {"t": "2026-11-11", "o": 301, "h": 306, "l": 299, "c": 304.35}]
    sat = datetime(2026, 11, 14, 8, 0, tzinfo=IST)
    got, _ = ipo._settle(row, bars, bars[0], sat)
    assert [b["t"] for b in got] == ["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
    assert got[-1]["c"] == 274.70 and got[-1]["official"]
    # during Friday's session, Friday's close isn't there yet
    fri = datetime(2026, 11, 13, 14, 0, tzinfo=IST)
    got, _ = ipo._settle(row, bars, bars[0], fri)
    assert got[-1]["t"] == "2026-11-12"
    # a US issue is untouched
    assert ipo.later_closes({"market": "US", "symbol": "X"}, "2026-11-11", sat) == []
    assert date(2026, 11, 13).weekday() == 4


# ---------- LIVE9A-001: the clock reads the Mood card's own payload, not only the AI's headlines read ----------
def test_the_card_payload_is_read_after_the_close_and_a_day_waits_for_its_session(monkeypatch):
    sessions = {"IN": ["2026-11-13", "2026-11-16"]}          # the first pass after the close still had Friday's tables
    asked = []

    def mood(region, day):
        asked.append((region, day))
        return sessions[region].pop(0) if sessions.get(region) else day
    job, calls = _job(monkeypatch, [], mood=mood)
    t = datetime(2026, 11, 16, 16, 15, tzinfo=IST)
    got = job.tick(t.astimezone(timezone.utc))
    assert got["IN"] == "tables of 2026-11-13" and calls == []                 # no AI read on an earlier session's tables
    assert job.tick((t + timedelta(minutes=5)).astimezone(timezone.utc))["IN"] == "written" and calls == ["IN"]
    assert asked == [("IN", "2026-11-16"), ("IN", "2026-11-16")]


def test_the_default_job_reads_the_mood_hub_payload(monkeypatch):
    from app.intel import routes
    built = []

    class Hub:
        class payloads:
            @staticmethod
            def kept(region):
                return (0.0, {"session": "2026-11-13", "is_open": False})

        def refresh_now(self, region):
            built.append(region)
            # (updated on purpose, fix13 LIVE11A-002: a day is done only with that session's breadth count in the tables)
            return {"session": "2026-11-16", "breadth": {"day": "2026-11-16"}}
    monkeypatch.setattr(routes, "mood_hub", lambda: Hub())
    assert mood_job._mood_payload("IN", "2026-11-16") == "2026-11-16" and built == ["IN"]
    # a payload already of the session that closed is not read again
    Hub.payloads.kept = staticmethod(lambda region: (0.0, {"session": "2026-11-16", "is_open": False, "breadth": {"day": "2026-11-16"}}))
    assert mood_job._mood_payload("IN", "2026-11-16") == "2026-11-16" and built == ["IN"]


def test_refresh_now_keeps_the_payload_in_the_database_at_once(monkeypatch):
    import time
    from app.intel import mood
    m = mood.Mood(hub=None)
    monkeypatch.setattr(m, "build", lambda region: {"session": "2026-11-16", "headline": "x"})
    kept = {}
    from app import db
    monkeypatch.setattr(db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    m._kept_at["IN"] = time.time()                       # written a minute ago: KEEP_EVERY would hold a plain read back
    assert m.refresh_now("IN")["session"] == "2026-11-16"
    assert any(k.endswith("IN") for k in kept)
    assert m.payloads.kept("IN")[1]["session"] == "2026-11-16"


# ---------- LIVE9A-002: one headline never mixes two sessions ----------
def test_the_headline_never_sets_today_against_an_earlier_sessions_breadth():
    from app.intel import mood
    levels = [{"name": "S&P 500", "change_pct": -1.87}, {"name": "NASDAQ", "change_pct": -2.36}, {"name": "DOW JONES", "change_pct": -1.40}]
    friday = {"group": "S&P 500", "live": False, "day": "2026-11-13", "adv": 313, "dec": 183, "stocks": 499}
    assert mood.same_session(friday, "2026-11-16") is None
    assert mood.same_session(friday, "2026-11-13") is friday
    assert mood.same_session({**friday, "live": True}, "2026-11-16")["live"]
    text = mood.headline_of(levels, None, None, mood.same_session(friday, "2026-11-16"))
    assert "313" not in text and text.startswith("Negative: all three indices down")
    # the build passes the breadth through that check
    import inspect
    assert "same_session(b, p[\"session\"])" in inspect.getsource(mood.Mood.build)
