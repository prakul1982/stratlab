"""LIVE5-003: after the close today's 52-week highs and lows were never filled until the evening run ("At the close" 56 minutes
after the close, and the last close's 24 / 3 read as today's). The live rounds now count them by the daily run's own rule: a day's
high above every high of the last 251 sessions, a day's low below every low."""
from app import breadth, breadth_live


def bars(n, hi=110.0, lo=90.0):
    return [{"t": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}T00:00:00+05:30", "c": 100.0, "h": hi, "l": lo} for i in range(n)]


def test_the_stored_base_carries_the_last_251_sessions_range():
    row = breadth.base_row(bars(300))
    assert row[5] == 110.0 and row[6] == 90.0
    assert breadth.base_row(bars(200))[5:] == [None, None]          # under a year of days: no range, not counted


def test_a_live_round_counts_new_highs_and_lows_from_the_days_range():
    base = {"UP": [100.0, 300, None, None, None, 110.0, 90.0], "DN": [100.0, 300, None, None, None, 110.0, 90.0],
            "MID": [100.0, 300, None, None, None, 110.0, 90.0], "NEW": [100.0, 100, None, None, None, None, None]}
    q = {"UP": {"price": 111.0, "prev_close": 100.0, "high": 112.0, "low": 99.0},
         "DN": {"price": 89.5, "prev_close": 100.0, "high": 100.0, "low": 89.0},
         "MID": {"price": 105.0, "prev_close": 100.0, "high": 110.0, "low": 95.0},       # matching the old high is not a new one
         "NEW": {"price": 200.0, "prev_close": 100.0, "high": 200.0, "low": 100.0}}     # a stock without a year: left out
    c = breadth_live.count(base, q, list(q))
    assert (c["hi"], c["lo"], c["n52"]) == (1, 1, 3)


def test_an_old_base_without_the_range_counts_nothing_for_the_year():
    c = breadth_live.count({"A": [100.0, 300, None, None, None]}, {"A": {"price": 120.0, "prev_close": 100.0, "high": 125.0}}, ["A"])
    assert (c["hi"], c["lo"], c["n52"]) == (0, 0, 0) and c["adv"] == 1


def test_a_stored_point_carries_them_and_the_card_reads_them():
    assert breadth_live.FIELDS[-3:] == ("hi", "lo", "n52")
    pt = ["15:30", 1, 2, 0, 0, 0, 0, 0, 0, 0, 24000.0, 3, 0, 4, 1, 3]
    latest = dict(zip(breadth_live.FIELDS, pt[1:]))
    assert (latest["hi"], latest["lo"], latest["n52"]) == (4, 1, 3)
    old = ["15:30", 1, 2, 0, 0, 0, 0, 0, 0, 0, 24000.0, 3, 0]      # a point stored before: no 52-week fields at all
    assert "hi" not in dict(zip(breadth_live.FIELDS, old[1:]))


def test_after_the_close_the_breadth_line_says_the_day_not_so_far_today():
    """LIVE5-009: "228 of 500 NIFTY 500 stocks rose and 268 fell so far today" at 16:26 IST."""
    from app.intel import mood
    b = {"live": True, "day": "2026-11-06", "adv": 228, "dec": 268, "stocks": 500, "group": "NIFTY 500", "pct50": None}
    shut = " ".join(mood.lines_of({"breadth": b, "is_open": False}))
    assert "so far today" not in shut and "fell on " in shut and "6 Nov" in shut
    assert "so far today" in " ".join(mood.lines_of({"breadth": b, "is_open": True}))
