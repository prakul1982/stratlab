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
