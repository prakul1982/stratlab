"""FIX-1A: the findings of the live-site review LIVE-1A that the backend answers."""
from datetime import datetime
from zoneinfo import ZoneInfo

from app import db, main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import ipo as I

NY, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")


def _bars():
    return [{"t": "2026-10-27T00:00:00-04:00", "o": 4.1, "h": 6.0, "l": 4.0, "c": 5.5, "v": 1.0},
            {"t": "2026-10-28T00:00:00-04:00", "o": 4.1, "h": 6.2, "l": 4.0, "c": 6.07, "v": 1.0}]


def test_a_us_session_still_going_on_is_not_a_close():
    """LIVE1A-060: the 12:00 ET read put a midday price under "Close 28 Oct" (AMRO $6.07; the close was $5.86)."""
    row = {"market": "US", "symbol": "AMRO", "priced": "2026-10-27"}
    mid = datetime(2026, 10, 28, 12, 0, tzinfo=NY).astimezone(UTC)
    bars, first = I._settle(row, _bars(), _bars()[0], mid)
    assert [b["t"][:10] for b in bars] == ["2026-10-27"] and first["t"][:10] == "2026-10-27"
    # the listing day itself still going on: no first session yet
    one = _bars()[1:]
    bars, first = I._settle(row, one, one[0], mid)
    assert bars == [] and first is None
    # after the close and the closing print, the day's candle is its close
    late = datetime(2026, 10, 28, 16, 30, tzinfo=NY).astimezone(UTC)
    bars, first = I._settle(row, _bars(), _bars()[0], late)
    assert [b["t"][:10] for b in bars] == ["2026-10-27", "2026-10-28"] and bars[-1]["c"] == 6.07


def test_the_us_list_is_read_again_after_the_new_york_close():
    names = [n for n, _ in I.Job.SLOTS]
    assert "us-close" in names
    at = dict(I.Job.SLOTS)["us-close"]
    assert "02:30" < at < "06:00"           # IST: after 16:00 ET in summer and in winter time


def test_an_issue_size_with_both_parts_in_rupees_gives_the_parts():
    """LIVE1A-030: "Issue size" did not say whether it was all new shares or new shares plus a sale by existing holders."""
    row = {"market": "IN", "fresh_cr": 300.0, "ofs_cr": 368.0, "high": 330.0}
    sz = I.sizes(row)
    assert sz["amount"] == 668.0 and sz["basis"] == "stated" and sz["parts"]["fresh_cr"] == 300.0 and sz["parts"]["ofs_cr"] == 368.0
    only = I.sizes({"market": "IN", "fresh_cr": 179.0, "high": 150.0})
    assert only["amount"] == 179.0 and "parts" not in only


def test_the_after_the_close_read_runs_in_the_small_hours_only(monkeypatch):
    from datetime import timedelta
    monkeypatch.setattr(I, "run_marker", lambda name: None)
    job = I.Job(sleep=lambda s: None)
    base = datetime(2026, 10, 29, 3, 40, tzinfo=ZoneInfo("Asia/Kolkata")).astimezone(UTC)
    assert job.due("us-close", "03:30", base) == "2026-10-29"
    assert job.due("us-close", "03:30", base - timedelta(hours=1)) is None                   # 02:40 IST: not yet
    assert job.due("us-close", "03:30", base + timedelta(hours=3)) is None                   # 06:40 IST: past the window


def test_a_coin_sessions_today_is_the_utc_day_in_the_roll_up_too():
    """LIVE1A-044: the roll-up counted a crypto session's day from 00:00 IST, its page from 00:00 UTC: "Today $5" against "Today $33"."""
    import time_machine
    from app import risk
    snap = {"id": "s1", "name": "Ride the trend", "kind": "group", "instrument": {"market": "CRYPTO", "currency": "USD"},
            "account": {"capital": 10000.0, "equity": 10163.0, "realised": 0.0, "trades": 0}, "members": [],
            "day_equity": {"2026-10-27": 9900.0, "2026-10-28": 10100.0}, "closed": [], "equity_curve": []}
    with time_machine.travel(datetime(2026, 10, 28, 21, 0, tzinfo=UTC), tick=False):      # 02:30 IST on the 29th, still the 28th in UTC
        row = risk.summary([snap])["sessions"][0]
    assert row["today"] == 263.0 and row["session_pnl"] is None
    # a share session keeps India's day
    share = {**snap, "id": "s2", "instrument": {"market": "IN", "currency": "INR", "symbol": "TCS"}, "day_equity": {"2026-10-27": 9900.0, "2026-10-28": 10100.0}}
    with time_machine.travel(datetime(2026, 10, 28, 21, 0, tzinfo=UTC), tick=False):
        assert risk.summary([share])["sessions"][0]["today"] == 63.0


def test_a_sessions_chart_holds_enough_candles_for_its_longest_average():
    """LIVE1A-012: "price above SMA 200" on a chart of 150 daily candles had no line (the legend read "SMA 200 -")."""
    from app import live
    from app.models import Strategy
    s = Strategy(name="t", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 200}}], exit=[{"l": {"t": "price"}, "op": "xb", "r": {"t": "sma", "p": 20}}])
    assert live.chart_window(s, 1000) == 300
    assert live.chart_window(s, 250) == 250                               # never more than it has
    short = Strategy(name="t", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 20}}])
    assert live.chart_window(short, 1000) == 150
    huge = Strategy(name="t", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 500}}])
    assert live.chart_window(huge, 5000) == live.CHART_BARS_MAX
