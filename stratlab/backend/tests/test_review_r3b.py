"""Round 3, builder B: weekend events say so, plan interest ("Tell me when plans open"), options premiums round alike."""
from datetime import date

import pytest

from app import db, main  # noqa: F401  (main first: it loads the modules in the order they need)
from app import market_events as M


def ev(kind, day, **kw):
    return {"id": "x", "kind": kind, "date": day, "title": "T", "detail": "Detail.", **kw}


def test_an_event_on_a_weekend_says_so_and_a_weekday_one_is_left_alone():
    sun = M.mark_weekend(ev("rbi", "2026-10-11"))
    assert sun["weekend"] == "Sunday"
    assert sun["detail"] == "Detail. This day is a Sunday, so the exchanges are closed."
    sat = M.mark_weekend(ev("india", "2026-10-17"))
    assert sat["weekend"] == "Saturday"
    mon = M.mark_weekend(ev("rbi", "2026-10-12"))
    assert "weekend" not in mon and mon["detail"] == "Detail."
    # holidays and expiries are about the calendar itself
    assert "weekend" not in M.mark_weekend(ev("holiday", "2026-10-11"))
    assert "weekend" not in M.mark_weekend(ev("expiry", "2026-10-17"))


def test_the_dated_list_marks_a_weekend_minutes_due_date():
    st = {"rbi": {"meetings": [{"start": date(2026, 9, 27).isoformat(), "end": date(2026, 9, 27).isoformat()}]}}
    out = M.rbi_events(st["rbi"], date(2026, 9, 20))
    due = next(e for e in out if e["title"].endswith("(due)"))
    assert due["date"] == "2026-10-11"                    # the 14th day after a Sunday decision
    assert M.mark_weekend(dict(due))["weekend"] == "Sunday"


def test_the_scan_alert_spells_out_stage_2_plus_supertrend():
    from app import scan
    text = scan.alert_text("IN", [{"symbol": "TCS"}])
    assert text.startswith("Stage 2 + Supertrend on your India watchlist: TCS is in Stage 2")
    assert "ST S2" not in text
