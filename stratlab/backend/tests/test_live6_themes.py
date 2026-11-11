"""LIVE6 (the live review of Release 34's theme page and deck): the theme's price periods, the latest news, the companies' own words,
one market value per company, and the deck's tables and charts."""
from datetime import date, timedelta

from app.intel import theme_prices as P


def _bars(start: date, end: date, f):
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append({"t": d.isoformat(), "c": f(d)})
        d += timedelta(days=1)
    return out


# ---------- LIVE6-002: calendar periods to the last close, a line that never runs past it ----------
def test_one_month_is_the_close_on_or_before_the_same_day_a_month_back():
    assert P.months_back(date(2026, 11, 10), 1) == date(2026, 10, 10)
    assert P.months_back(date(2026, 5, 31), 1) == date(2026, 4, 30) and P.months_back(date(2026, 3, 31), 3) == date(2025, 12, 31)
    assert P.months_back(date(2026, 11, 10), 36) == date(2023, 11, 10)
    # a close every weekday at its day-of-month: the 1M change is from the 9 Oct close (10 Oct 2026 is a Saturday) to the 10 Nov close
    bars = _bars(date(2026, 1, 1), date(2026, 11, 10), lambda d: 100.0 + d.toordinal() - date(2026, 1, 1).toordinal())
    r = P.reduce_bars(bars)
    last = 100.0 + (date(2026, 11, 10) - date(2026, 1, 1)).days
    base = 100.0 + (date(2026, 10, 9) - date(2026, 1, 1)).days
    assert r["ret"]["1M"] == round((last / base - 1) * 100, 1)
    base3 = 100.0 + (date(2026, 8, 10) - date(2026, 1, 1)).days
    assert r["ret"]["3M"] == round((last / base3 - 1) * 100, 1)


def test_the_theme_and_its_index_over_the_same_calendar_periods_and_the_line_ends_on_the_last_close():
    end = date(2026, 11, 10)                      # a Tuesday: the week isn't over
    start = date(2022, 1, 3)
    a = P.reduce_bars(_bars(start, end, lambda d: 100 + (d - start).days * 0.05))
    b = P.reduce_bars(_bars(start, end, lambda d: 50 + (d - start).days * 0.02))
    idx = P.reduce_bars(_bars(start, end, lambda d: 400 + (d - start).days * 0.1))
    out = P.compute([("A", "A Co"), ("B", "B Co")], {"A": a, "B": b}, idx, "SPY")
    weeks = out["line"]["weeks"]
    assert weeks[-1] == "2026-11-10" and max(weeks) <= "2026-11-10"            # never a Friday after the last close
    assert out["returns_to"] == "2026-11-10"
    # the index's 1M on the weekly line: from the last week ending on or before 10 Oct (Fri 9 Oct) to the last close
    days = [date.fromisoformat(w) for w in weeks]
    bench = out["line"]["bench"]
    i0 = max(i for i, d in enumerate(days) if d <= date(2026, 10, 10))
    assert days[i0] == date(2026, 10, 9)
    assert out["returns"]["1M"]["bench"] == round((bench[-1] / bench[i0] - 1) * 100, 1)
    i3 = max(i for i, d in enumerate(days) if d <= date(2026, 8, 10))
    assert out["returns"]["3M"]["bench"] == round((bench[-1] / bench[i3] - 1) * 100, 1)
