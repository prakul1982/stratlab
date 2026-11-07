"""Admin's checks (owner, 4 Nov: "a whole check on admin pages — there are a lot of warnings and issues popping up"): each warning
either real (fixed at its source) or false (the check fixed), every member of its class covered."""
from datetime import date, datetime, timedelta, timezone

import pytest

from app import admin_jobs, audit, platform_check
from app.data import calendar
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


# ---------- the exchange holidays: next year's list is due in mid-December, not a Check in November ----------
def test_holidays_known_to_the_end_of_the_year_are_fine_until_next_years_list_is_due(monkeypatch):
    monkeypatch.setattr(calendar, "covered_until", lambda m: date(2026, 12, 31) if m in calendar.LISTED else date(2027, 11, 4))
    for m in calendar.LISTED:                                   # every exchange-listed market, by one rule
        nov = calendar.coverage(m, date(2026, 11, 4))
        assert nov["state"] == "ok" and nov["days_left"] == 57 and nov["hint"] == calendar.AWAITED
        dec = calendar.coverage(m, date(2026, 12, 21))
        assert dec["state"] == "warn" and "paste it below" in dec["hint"]
    # a market on built-in rules isn't touched by the season
    assert calendar.coverage("US", date(2027, 10, 1))["state"] == "warn"
    assert not calendar.awaiting_next_year("IN", date(2026, 11, 30), date(2026, 11, 4))     # a list that stops short of the year end
    # the feature check passes, saying why
    res = platform_check.check_calendar(date(2026, 11, 4))
    assert res["state"] == "pass" and calendar.AWAITED in res["detail"]


def test_calendar_status_gives_one_season_aware_light(w, monkeypatch):
    from app import main
    monkeypatch.setattr(calendar, "covered_until", lambda m: date(2026, 12, 31) if m in calendar.LISTED else date(2027, 11, 4))

    class Day(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 4, 22, 0, tzinfo=main.IST)
    monkeypatch.setattr(main, "datetime", Day)
    cal = main.calendar_status()
    assert cal["state"] == "ok" and cal["note"] == calendar.AWAITED

    class Late(Day):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 12, 22, 9, 0, tzinfo=main.IST)
    monkeypatch.setattr(main, "datetime", Late)
    assert main.calendar_status()["state"] == "warn" and main.calendar_status()["note"] is None


# ---------- insider trades: the whole market's freshness, not one company's ----------
def test_insider_trades_are_judged_across_the_whole_market():
    today = date.today()

    class Feed:
        def __init__(self, items):
            self.items, self.asked = items, None

        def insider_trades(self, symbol=None, days=365, to=None):
            self.asked = (symbol, days)
            return self.items
    f = Feed([{"date": (today - timedelta(days=1)).isoformat()}, {"date": (today - timedelta(days=3)).isoformat()}])
    r = platform_check.check_insider_trades(f)
    assert f.asked == (None, platform_check.INSIDER_WINDOW_DAYS) and r["state"] == "pass" and "across the market" in r["detail"]
    stale = platform_check.check_insider_trades(Feed([{"date": (today - timedelta(days=12)).isoformat()}]))
    assert stale["state"] == "warn" and "unusual for the whole market" in stale["detail"] and "Reliance" not in stale["detail"]
    none = platform_check.check_insider_trades(Feed([]))
    assert none["state"] == "warn" and "stopped updating" in none["detail"] and "may have changed shape" not in none["detail"]


def test_insider_trades_serve_the_last_list_read_when_the_exchange_does_not_answer(monkeypatch):
    """R15 ("Insider trades: Couldn't reach the exchange (ReadTimeout)" in Needs your attention): the last list read stands, with when it
    was read, and the check passes saying so; with no recent list the exchange's error stands."""
    from app import db
    from app.intel import filings as F
    from app.intel.net import SourceError
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    feed = F.NSEFilings()
    today = date.today()
    rows = [{"symbol": "TCS", "date": (today - timedelta(days=1)).isoformat()}]
    answers = [rows]

    def insider(symbol, days, to):
        got = answers.pop(0)
        if isinstance(got, Exception):
            raise got
        return got
    monkeypatch.setattr(feed, "_insider", insider)
    first = feed.insider_trades(None, 14)
    assert first == rows and not hasattr(first, "stale_at")
    answers.append(SourceError("the exchange", "Couldn't reach the exchange (ReadTimeout).", busy=True))
    got = feed.insider_trades(None, 14)
    assert got == rows and got.stale_at
    r = platform_check.check_insider_trades(type("Feed", (), {"insider_trades": lambda self, s=None, d=14, to=None: got})())
    assert r["state"] == "pass" and "the exchange didn't answer just now: the list as read at" in r["detail"]
    # after a restart: the whole market's list from storage
    fresh = F.NSEFilings()
    monkeypatch.setattr(fresh, "_insider", lambda s, d, to: (_ for _ in ()).throw(SourceError("the exchange", "busy", busy=True)))
    assert fresh.insider_trades(None, 14) == rows
    # a company never read, or a shape error (ours to fix): the error stands
    with pytest.raises(SourceError):
        fresh.insider_trades("INFY", 14)
    monkeypatch.setattr(fresh, "_insider", lambda s, d, to: (_ for _ in ()).throw(SourceError("the exchange", "shape")))
    with pytest.raises(SourceError):
        fresh.insider_trades(None, 14)


# ---------- the whole-market audit: every mismatch is checked again after a day, not only prices ----------
def test_a_mismatch_of_any_area_a_day_old_is_checked_again(w):
    a = audit.MarketAudit(lambda: {}, lambda s: {"symbol": s, "issues": []})
    a._load()
    a.listing = {"BSE:512477": {"name": "Betex"}, "TBZ": {"name": "TBZ"}, "OK": {"name": "OK"}, "NEW": {"name": "New"}}
    old = (datetime.now(timezone.utc) - timedelta(hours=audit.STALE_MISMATCH_HOURS + 1)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    a.rows["BSE:512477"] = {"symbol": "BSE:512477", "at": old, "issues": [{"level": "mismatch", "area": "Valuation", "text": "P/E"}]}
    a.rows["TBZ"] = {"symbol": "TBZ", "at": old, "issues": [{"level": "mismatch", "area": "Prices", "text": "price"}]}
    a.rows["OK"] = {"symbol": "OK", "at": old, "issues": [{"level": "gap", "area": "Documents", "text": "x"}]}
    a.rows["NEW"] = {"symbol": "NEW", "at": fresh, "issues": [{"level": "mismatch", "area": "Numbers", "text": "x"}]}
    # every area whose mismatch is a day old, oldest first; a gap or a mismatch found today is left alone
    assert set(a.stale_mismatches()) == {"BSE:512477", "TBZ"}

# ---------- a schedule's clock without AM/PM takes the one before it ----------
def test_a_bare_clock_after_a_pm_one_is_pm():
    now = datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
    assert admin_jobs.next_run_label("Every 30 seconds from 3:14 to 3:40 PM IST; the day is stored after 3:40", now) == "Thu 5 Nov, 3:40 PM IST"
    assert admin_jobs.next_run_label("8:15 AM and 7:50 PM IST on trading days", now) == "Thu 5 Nov, 8:15 AM IST"
    assert admin_jobs.next_run_label("Every quarter hour (09:15 to 15:30 IST) while the Indian market is open", now) is None

