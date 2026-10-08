"""A day's change is measured from the session before, not from the close before the chart's window (the meta's
chartPreviousClose, about a week back for the 7-day window the quote reads). Real NIFTY 50 closes, Oct 2026."""
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.intel.yahoo import Yahoo

IST = ZoneInfo("Asia/Kolkata")
CLOSES = [("2026-10-01", 22421.95), ("2026-10-05", 22555.75), ("2026-10-06", 22776.10), ("2026-10-07", 22603.05)]


def _feed(last_trade: datetime, closes=CLOSES):
    def handler(r):
        ts = [int(datetime.fromisoformat(d).replace(hour=9, minute=15, tzinfo=IST).timestamp()) for d, _ in closes]
        c = [x for _, x in closes]
        return httpx.Response(200, json={"chart": {"result": [{
            "meta": {"symbol": "^NSEI", "currency": "INR", "exchangeTimezoneName": "Asia/Kolkata", "regularMarketPrice": c[-1],
                     "chartPreviousClose": 22620.45, "regularMarketTime": int(last_trade.timestamp())},     # 30 Sep's close
            "timestamp": ts, "indicators": {"quote": [{"open": c, "high": c, "low": c, "close": c, "volume": [0] * len(c)}]}}]}})
    return Yahoo(transport=httpx.MockTransport(handler))


def test_the_days_change_is_from_the_session_before():
    m = _feed(datetime(2026, 10, 7, 15, 30, tzinfo=IST)).meta("^NSEI")
    assert m["prev_close"] == 22776.10
    assert m["change_pct"] == pytest.approx(-0.76, abs=0.005)        # not -0.08% (the change since 30 Sep)


def test_on_a_day_without_a_session_it_is_the_last_sessions_change():
    # read on a holiday or before the open: the last trade was 7 Oct's close
    m = _feed(datetime(2026, 10, 7, 15, 30, tzinfo=IST)).meta("^NSEI")
    assert m["change_pct"] == pytest.approx((22603.05 / 22776.10 - 1) * 100)


def test_after_a_holiday_it_skips_the_closed_day():
    m = _feed(datetime(2026, 10, 5, 15, 30, tzinfo=IST), CLOSES[:2]).meta("^NSEI")
    assert m["prev_close"] == 22421.95                                 # 1 Oct: 2 Oct was a holiday
