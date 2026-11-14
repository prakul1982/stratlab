"""Release 53, lane app53: business updates whose stored reads still carry an older reader's year-ago figure (LIVE8B-002 /
LIVE8A-020), and the daily job's order of companies."""
from datetime import date, timedelta

from app import biz_updates as B


def _read(at, period, value, prior, quote, reader=3):
    return {"at": at, "title": "Monthly Business Update", "url": f"https://nsearchives.nseindia.com/corporate/{at}.pdf", "period": period,
            "span": "month", "reader": reader,
            "figures": [{"metric": "Total sales", "segment": None, "value": value, "unit": "units", "basis": "month", "prior": prior,
                         "headline": True, "quote": quote, "page": 1, "own": True}]}


def test_a_stored_year_to_date_figure_is_not_the_year_ago_month():
    # reads made by the reader before the year-to-date fix: Oct 2026's year-ago figure was the year-to-date 33,103
    reads = {"jun": _read("2026-07-01T10:00", "2026-06", 5200, None, "Total 5200"),
             "sep": _read("2026-10-01T10:50", "2026-09", 5954, None, "Total 5954"),
             "oct": _read("2026-11-01T13:24", "2026-10", 3519, 33103, "Total (in Nos) 3519 33103 4664 32069")}
    top = B.headline(B.series(reads))
    assert top["latest"]["value"] == 3519
    assert top["change_year"] is None and top["year_ago"] is None
    assert "89.4" not in (B.words(top) or "") and "down" not in (B.words(top) or "")
    # nor is it drawn on the chart as Oct 2025
    assert "2025-10" not in [p["period"] for p in top["points"]]
    # the real year-ago month, once read, is used
    reads["oct"] = _read("2026-11-01T13:24", "2026-10", 3519, 4664, "Total (in Nos) 3519 33103 4664 32069", reader=B.READER)
    top = B.headline(B.series(reads))
    assert top["change_year"] == -24.5


def test_a_stated_year_ago_figure_in_line_with_the_measure_is_kept():
    reads = {"sep": _read("2026-10-01T10:50", "2026-09", 1004, 1001, "Power weeder 1004 6076 1001 4970", reader=B.READER)}
    row = B.series(reads)[0]
    assert row["year_ago"]["value"] == 1001 and row["change_year"] == 0.3


def test_the_job_starts_at_a_different_company_each_day():
    syms = [f"S{i:03d}" for i in range(250)]
    starts = {B.rotated(syms, date(2026, 11, 1) + timedelta(days=d))[0] for d in range(10)}
    assert len(starts) >= 8
    for d in range(10):
        got = B.rotated(syms, date(2026, 11, 1) + timedelta(days=d))
        assert sorted(got) == syms
    # over a fortnight every part of the list is near the front on some day (a budget for 100 a day reaches all 250)
    reached = set()
    for d in range(14):
        reached |= set(B.rotated(syms, date(2026, 11, 1) + timedelta(days=d))[:100])
    assert reached == set(syms)
    assert B.rotated([], date(2026, 11, 1)) == []
