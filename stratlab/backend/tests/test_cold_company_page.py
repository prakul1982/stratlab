"""A company page and its chart read the same year of daily candles (370 days, then 365): the second takes the first's
stored copy, cut to its own start, instead of asking the broker again (cold company page: one broker read, not two)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import time_machine

from app.kite_service import KiteService

IST = ZoneInfo("Asia/Kolkata")
TOKEN = 2953217
NOW = datetime(2026, 10, 17, 10, 0, tzinfo=IST)          # a Saturday: the long reuse applies


def _bar(day: str) -> dict:
    return {"t": f"{day}T00:00:00+05:30", "o": 1.0, "h": 2.0, "l": 1.0, "c": 1.5, "v": 10.0}


def _kite():
    ks = KiteService()
    ks.access_token, ks.token_day = "t", NOW.date().isoformat()
    ks._by_token = {TOKEN: {"token": TOKEN, "symbol": "TCS", "exchange": "NSE", "type": "EQ"}}
    calls = []

    class Inner:
        def historical_data(self, token, frm, to, interval, continuous=False):
            calls.append((frm, to))
            return []
    ks.kite, ks._throttle = Inner(), lambda: None
    days = [(NOW - timedelta(days=i)).date().isoformat() for i in range(400, -1, -1)]
    ks._cache[(TOKEN, "1d", 370, False)] = (NOW.timestamp(), [_bar(d) for d in days if d >= (NOW - timedelta(days=370)).date().isoformat()])
    return ks, calls


def test_a_shorter_window_takes_the_wider_stored_copy_cut_to_its_start():
    ks, calls = _kite()
    with time_machine.travel(NOW, tick=False):
        bars = ks.history(TOKEN, "1d", 365)
    assert calls == []
    assert bars[0]["t"][:10] == (NOW - timedelta(days=364)).date().isoformat()
    assert bars[-1]["t"][:10] == NOW.date().isoformat()


def test_a_longer_window_still_asks_the_broker():
    ks, calls = _kite()
    with time_machine.travel(NOW, tick=False):
        ks.history(TOKEN, "1d", 730)
    assert len(calls) >= 1


def test_another_token_does_not_borrow_the_copy():
    ks, calls = _kite()
    ks._by_token[1] = {"token": 1, "symbol": "X", "exchange": "NSE", "type": "EQ"}
    with time_machine.travel(NOW, tick=False):
        ks.history(1, "1d", 365)
    assert len(calls) >= 1
