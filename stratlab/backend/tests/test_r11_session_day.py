"""The market read's headlines are the last session's, not India's calendar day's (owner, 5 Nov 02:30 IST: "What the headlines
say" said "No AI read right now": the day had turned, every headline from the 5 Nov session was dropped, and the read came back
empty). grounding.session_day is the levels' own session day, at most today."""
import json
from datetime import date

from app.intel import ai as A
from app.intel import grounding

NOV5 = [{"name": "NIFTY 50", "price": 24536.6, "change_pct": 2.4, "at": "2026-11-05T15:30:00+05:30"},
        {"name": "SENSEX", "price": 80000.0, "change_pct": 2.1, "at": "2026-11-05T15:30:00+05:30"}]


def test_the_session_day_is_the_levels_day_until_the_next_session():
    assert grounding.session_day(NOV5, date(2026, 11, 6)) == date(2026, 11, 5)          # after India's midnight
    assert grounding.session_day(NOV5, date(2026, 11, 5)) == date(2026, 11, 5)          # the same day
    us = [{"name": "S&P 500", "at": "2026-11-05T15:58:00-05:00"}]                      # the US session running past India's midnight
    assert grounding.session_day(us, date(2026, 11, 6)) == date(2026, 11, 5)
    assert grounding.session_day([], date(2026, 11, 6)) == date(2026, 11, 6)            # no levels: today
    assert grounding.session_day([{"name": "X", "at": "garbage-day"}], date(2026, 11, 6)) == date(2026, 11, 6)
    future = [{"name": "X", "at": "2026-11-07T09:15:00+05:30"}]
    assert grounding.session_day(future, date(2026, 11, 6)) == date(2026, 11, 6)        # never later than today


def test_the_market_read_after_midnight_is_given_the_last_sessions_headlines(monkeypatch):
    seen = {}

    def complete(system, text, **_):
        seen["facts"] = json.loads(text.split("FACTS:\n", 1)[1])
        return json.dumps({"driver": "bank results", "tone": "Banks led after results.", "hot": [], "flows": [], "themes": []})

    monkeypatch.setattr(A, "complete", complete)
    monkeypatch.setattr(A, "ist_date", lambda: date(2026, 11, 6))
    news = [{"headline": "Banks rally after results", "at": "2026-11-05T10:00:00+05:30"},
            {"headline": "An old story", "at": "2026-11-03T10:00:00+05:30"}]
    read = A.pulse("IN", "", NOV5, news, (None, None), closed=True)
    assert seen["facts"]["headlines"] == ["[2026-11-05] Banks rally after results"]
    assert read["tone"] == "Banks led after results."
