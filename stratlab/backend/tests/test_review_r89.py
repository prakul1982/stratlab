"""Round 89, the US close (23 Oct 2026): each test is built on what the reviewer saw."""
from datetime import datetime, timezone

import time_machine

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import breadth, stock_pages
from app.intel import ai as A, company as C, routes as research_routes

UTC = timezone.utc


# ---------- R89-001: US breadth is in about an hour after the close, not two ----------
def test_the_us_breadth_run_starts_after_the_prints_settle_and_after_the_brief():
    from app.newsletter import job
    assert breadth.RUN_AT["US"] == ("America/New_York", "16:55")
    assert breadth.due_label("US") == "5:05 PM ET"
    # after the settle point (16:00 + 45 minutes) and after the US brief's 16:50, so the two don't read every stock at once
    assert "16:45" < breadth.RUN_AT["US"][1] and job.SEND_AT["US"][1] < breadth.RUN_AT["US"][1]


# ---------- R89-007: the market read while the closing prints settle ----------
@time_machine.travel(datetime(2026, 10, 23, 20, 9, tzinfo=UTC), tick=False)
def test_a_read_written_while_the_prints_settle_never_says_closed_ended_or_finished_at(monkeypatch):
    seen = {}

    def fake(system, text, **k):
        seen["facts"] = text
        return ('{"tone": "The S&P 500 closed at 7,623.68, the Nasdaq ended at 25,955.34 and the Dow finished at 52,215.16.",'
                ' "hot": [], "flows": [], "themes": []}')
    monkeypatch.setattr(A, "complete", fake)
    at = "2026-10-23T20:00:00+00:00"
    idx = [C.index_level("S&P 500", {"price": 7623.68, "change_pct": -0.52, "prev_close": 7663.43, "at": at}, "US"),
           C.index_level("Nasdaq", {"price": 25955.34, "change_pct": -0.21, "prev_close": 26009.96, "at": at}, "US"),
           C.index_level("Dow Jones", {"price": 52215.16, "change_pct": -1.23, "prev_close": 52865.4, "at": at}, "US")]
    out = A.pulse("US", "", idx, [], (None, None), closed=False, settling=True)
    assert "closed at" not in out["tone"] and "ended at" not in out["tone"] and "finished at" not in out["tone"]
    assert out["tone"].count("stood at") == 3
    assert "still settling into the official close" in seen["facts"] and "The market has closed for the day" not in seen["facts"]


def _route(monkeypatch, now):
    got = {}
    q = {"price": 7623.68, "change_pct": -0.52, "prev_close": 7663.43, "at": "2026-10-23T20:00:00+00:00"}
    monkeypatch.setattr(research_routes, "_levels_now", lambda r, wait: ([C.index_level("S&P 500", q, "US", now)], None))
    monkeypatch.setattr(research_routes, "market_open", lambda r, now=None: False)

    def call(profile, kind, key, ttl, refresh, build, counted=True, min_age=0, **k):
        got.update(key=key, ttl=ttl, min_age=min_age)
        return {"tone": "x"}
    monkeypatch.setattr(research_routes, "ai_call", call)
    research_routes.pulse_ai("US", "", False, {"id": "u1"})
    return got


def test_the_settling_read_is_kept_apart_and_only_until_the_prints_settle(monkeypatch):
    with time_machine.travel(datetime(2026, 10, 23, 20, 9, tzinfo=UTC), tick=False):      # 16:09 ET, Friday
        assert stock_pages.settling("US") == "2026-10-23"
        got = _route(monkeypatch, datetime(2026, 10, 23, 20, 9, tzinfo=UTC))
    assert got["key"][2] == "settling"
    assert 35 * 60 <= got["ttl"] <= 37 * 60 and got["min_age"] == got["ttl"]               # until 16:45 ET
    with time_machine.travel(datetime(2026, 10, 23, 20, 50, tzinfo=UTC), tick=False):     # 16:50 ET: final
        assert stock_pages.settling("US") is None
        got = _route(monkeypatch, datetime(2026, 10, 23, 20, 50, tzinfo=UTC))
    assert got["key"][2] == "close" and got["ttl"] == research_routes.CLOSED_MOOD_TTL
