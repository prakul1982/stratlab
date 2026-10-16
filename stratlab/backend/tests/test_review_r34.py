"""Round 34 review (owner pass): an Indian quote's change before the open is the last session's (R34-001)."""
from datetime import datetime, timezone

import time_machine

from app.intel import company as C

UTC = timezone.utc
BARS = [{"t": "2026-10-14T00:00:00+05:30", "c": 1174.60}, {"t": "2026-10-15T00:00:00+05:30", "c": 1215.00}]
# the broker's quote before the open: the last price is the 15 Oct close and so is the "previous close"
QUOTE = {"price": 1215.0, "prev_close": 1215.0, "change": 0.0, "change_pct": 0.0, "at": "2026-10-15T15:29:59+05:30"}


@time_machine.travel(datetime(2026, 10, 16, 3, 0, tzinfo=UTC), tick=False)          # 08:30 IST, before the open
def test_before_the_open_the_change_is_the_last_sessions():
    q = C.last_session_move(QUOTE, BARS)
    assert q["change_day"] == "2026-10-15" and round(q["change"], 2) == 40.40 and q["change_pct"] == 3.44
    assert q["price"] == 1215.0 and QUOTE["change_pct"] == 0.0              # the quote given is never changed


@time_machine.travel(datetime(2026, 10, 16, 5, 0, tzinfo=UTC), tick=False)          # 10:30 IST, during the session
def test_during_the_session_the_quote_stands():
    live = {"price": 1220.0, "prev_close": 1215.0, "change": 5.0, "change_pct": 0.41, "at": "2026-10-16T10:29:00+05:30"}
    assert C.last_session_move(live, BARS) is live


@time_machine.travel(datetime(2026, 10, 15, 11, 0, tzinfo=UTC), tick=False)         # 16:30 IST, after the close
def test_after_the_close_the_quote_of_today_stands():
    done = {"price": 1215.0, "prev_close": 1174.6, "change": 40.4, "change_pct": 3.44, "at": "2026-10-15T15:29:59+05:30"}
    assert C.last_session_move(done, BARS) is done


@time_machine.travel(datetime(2026, 10, 17, 4, 0, tzinfo=UTC), tick=False)          # Saturday: a weekend is no session
def test_a_weekend_shows_the_last_sessions_change():
    q = C.last_session_move(QUOTE, [*BARS, {"t": "2026-10-16T00:00:00+05:30", "c": 1230.0}])
    assert q["change_day"] == "2026-10-16" and round(q["change"], 2) == 15.0


@time_machine.travel(datetime(2026, 10, 16, 3, 0, tzinfo=UTC), tick=False)
def test_without_two_stored_closes_the_quote_stands():
    assert C.last_session_move(QUOTE, BARS[:1]) is QUOTE


@time_machine.travel(datetime(2026, 10, 16, 3, 0, tzinfo=UTC), tick=False)
def test_hub_quotes_use_the_stored_daily_candles():
    class Kite:
        def equity(self, s): return {"token": 1}
        def by_symbol(self, s): return None
        def history(self, token, tf, days): return BARS
    hub = object.__new__(C.Research)
    hub.kite = Kite()
    assert hub._last_session("RELIANCE", QUOTE)["change_pct"] == 3.44


def test_notebook_summary_carries_the_last_runs_return():
    from app import research
    run = {"label": "v1", "verdict": {"verdict": "no_edge"}, "stats": {"ret": -100.0}}
    assert research.summary([run])["last_return"] == -100.0 and research.summary([])["last_return"] is None
