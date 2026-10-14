"""A daily candle is re-read every minute only while today's bar is forming: a trading day, after the open, before the
close is out. Weekends, holidays and the hours before the open keep the long reuse (kite_service.history, yahoo._partial)."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import time_machine

from app.intel.yahoo import _partial
from app.kite_service import KiteService

IST = ZoneInfo("Asia/Kolkata")
KEY = (2953217, "1d", 30, False)


def _bar(day: str) -> dict:
    return {"t": f"{day}T00:00:00+05:30", "o": 1.0, "h": 2.0, "l": 1.0, "c": 1.5, "v": 10.0}


def _kite(at: datetime, last_day: str):
    ks = KiteService()
    ks.access_token, ks.token_day = "t", at.date().isoformat()
    ks._by_token = {2953217: {"token": 2953217, "symbol": "TCS", "exchange": "NSE", "type": "EQ"}}
    calls = []

    class Inner:
        def historical_data(self, token, frm, to, interval, continuous=False):
            calls.append(token)
            return [{"date": datetime.fromisoformat(_bar(last_day)["t"]), "open": 1, "high": 2, "low": 1, "close": 1.6,
                     "volume": 10}]
    ks.kite, ks._throttle = Inner(), lambda: None
    ks._cache[KEY] = (at.timestamp(), [_bar(last_day)])
    return ks, calls


def _reads_after(at: datetime, last_day: str, minutes: float) -> int:
    ks, calls = _kite(at, last_day)
    with time_machine.travel(at, tick=False) as t:
        t.shift(minutes * 60)
        ks.history(2953217, "1d", 30)
    return len(calls)


def test_saturday_keeps_the_long_reuse():
    assert _reads_after(datetime(2026, 10, 17, 10, 0, tzinfo=IST), "2026-10-16", 5) == 0


def test_a_holiday_keeps_the_long_reuse():
    assert _reads_after(datetime(2026, 10, 2, 11, 0, tzinfo=IST), "2026-10-01", 5) == 0     # Gandhi Jayanti


def test_before_the_open_keeps_the_long_reuse_until_the_market_opens():
    pre = datetime(2026, 10, 14, 8, 30, tzinfo=IST)
    assert _reads_after(pre, "2026-10-13", 10) == 0
    assert _reads_after(pre, "2026-10-13", 50) == 1        # 09:20: read before the open, so read again


def test_in_session_todays_bar_is_reused_for_a_minute_only():
    at = datetime(2026, 10, 14, 11, 0, tzinfo=IST)
    assert _reads_after(at, "2026-10-14", 0.5) == 0
    assert _reads_after(at, "2026-10-14", 2) == 1


# ---------- Yahoo ----------
def _answer(day: str, tz: str, start: datetime | None = None, end: datetime | None = None, kind: str = "EQUITY") -> dict:
    meta = {"exchangeTimezoneName": tz, "instrumentType": kind}
    if end:
        meta["currentTradingPeriod"] = {"regular": {"start": int(start.timestamp()), "end": int(end.timestamp())}}
    return {"meta": meta, "candles": [{"t": f"{day}T00:00:00-04:00", "c": 1.0}]}


def _us(day: datetime, now_hm: tuple[int, int]) -> tuple[dict, float]:
    ny = ZoneInfo("America/New_York")
    start, end = day.replace(hour=9, minute=30, tzinfo=ny), day.replace(hour=16, tzinfo=ny)
    now = day.replace(hour=now_hm[0], minute=now_hm[1], tzinfo=ny).timestamp()
    return _answer(day.date().isoformat(), "America/New_York", start, end), now


def test_yahoo_a_weekend_or_holiday_candle_is_never_forming():
    assert not _partial(*_us(datetime(2026, 10, 17), (11, 0)))      # Saturday
    assert not _partial(*_us(datetime(2026, 11, 26), (11, 0)))      # Thanksgiving


def test_yahoo_before_the_open_nothing_is_forming_and_in_session_it_is():
    assert not _partial(*_us(datetime(2026, 10, 14), (8, 0)))
    assert _partial(*_us(datetime(2026, 10, 14), (11, 0)))
    assert not _partial(*_us(datetime(2026, 10, 14), (16, 30)))


def test_yahoo_crypto_forms_through_the_utc_day_every_day():
    now = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc).timestamp()                     # a Saturday
    assert _partial({"meta": {"exchangeTimezoneName": "UTC", "instrumentType": "CRYPTOCURRENCY"},
                     "candles": [{"t": "2026-10-17T00:00:00+00:00"}]}, now)
    assert not _partial({"meta": {"exchangeTimezoneName": "UTC", "instrumentType": "CRYPTOCURRENCY"},
                         "candles": [{"t": "2026-10-16T00:00:00+00:00"}]}, now)
