"""Round 79 (22 Oct 2026): India's open — the backend side."""
from datetime import datetime, timezone

from app import main  # noqa: F401,I001  (first: the app loads the newsletter job before the modules built on it)
from app import vix as V


def test_the_pre_open_points_are_not_drawn_as_todays_line():
    # R79-002: a flat 15.68 (the previous close) from before 09:15 to 09:17, then the day's own line
    def ms(hh, mm):                 # the exchange writes India wall-clock times as milliseconds since 1970
        return int(datetime(2026, 10, 22, hh, mm, tzinfo=timezone.utc).timestamp() * 1000)
    data = {"data": {"grapthData": [[ms(9, 8), 15.68], [ms(9, 14), 15.68], [ms(9, 15), 16.3], [ms(9, 16), 16.1]]}}
    pts = V.parse_graph(data)
    assert [p["t"][11:16] for p in pts] == ["09:15", "09:16"]


def test_a_range_outside_the_drawn_line_is_marked_not_changed():
    line = [{"t": "2026-10-22T09:15+05:30", "v": 16.3}, {"t": "2026-10-22T09:50+05:30", "v": 15.7}]
    q = {"value": 16.18, "low": 14.32, "high": 16.67, "as_of": "2026-10-22T09:50:00+05:30"}
    out = V.within_line(q, line)
    assert out["low"] == 14.32 and out["high"] == 16.67 and out["range_off_line"] is True
    inside = V.within_line({**q, "low": 15.7, "high": 16.3}, line)
    assert inside["range_off_line"] is False
    assert V.within_line(q, []) == q and V.within_line(None, line) is None
