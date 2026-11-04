"""CLOCK: the browser tests' world runs at one named moment (tests/e2e_clock.py), never the machine's unless asked."""
from datetime import datetime, timedelta, timezone

import pytest

from app import money_networth, results
from tests import e2e_clock

IST = timezone(timedelta(hours=5, minutes=30))


def test_the_moments_are_a_wednesday_mid_session_and_a_shut_sunday_on_a_months_first(monkeypatch):
    monkeypatch.delenv("E2E_NOW", raising=False)
    at = e2e_clock.moment()
    assert at == datetime(2026, 10, 28, 11, 0, tzinfo=IST) and at.weekday() == 2
    shut = e2e_clock.moment("closed")
    assert shut == datetime(2026, 11, 1, 15, 0, tzinfo=IST) and shut.weekday() == 6 and shut.day == 1
    assert e2e_clock.moment("CLOSED") == shut and e2e_clock.moment("open") == at
    assert e2e_clock.moment("real") is None
    assert e2e_clock.moment("2026-10-30T10:00:00+05:30") == datetime(2026, 10, 30, 10, 0, tzinfo=IST)
    with pytest.raises(SystemExit):
        e2e_clock.moment("2026-10-30T10:00:00")              # a moment without its zone is no moment


def test_the_app_reads_the_moment_through_whichever_helper_it_uses():
    try:
        assert e2e_clock.start("open") == e2e_clock.moment("open")
        assert money_networth.today().isoformat() == "2026-10-28"
        assert results.local_today("IN").isoformat() == "2026-10-28"
        assert datetime.now(IST).hour == 11                   # and it runs on from there
        e2e_clock.start("closed")
        assert money_networth.today().isoformat() == "2026-11-01"
    finally:
        e2e_clock.start("real")
    assert datetime.now(timezone.utc).year >= 2026 and e2e_clock._travel is None
