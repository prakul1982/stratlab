"""The exchange's stored closes are the traded (unadjusted) ones; broker candles are adjusted for splits and bonuses, so an
official close is laid over a candle only when it is on the candle's basis (a 1:10 split's 1,010 over an adjusted 101 planted
a jump)."""
from datetime import datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import corp_actions, db, official_close as oc

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 10, 11, 0, tzinfo=IST)          # Saturday: the 9th's closes are final


@pytest.fixture
def mem(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, *a: [(k, v) for k, v in sorted(store.items()) if k.startswith(p)])
    oc.forget()
    yield store
    oc.forget()


def _bars(*closes, first="2026-10-07"):
    from datetime import date
    d0 = date.fromisoformat(first)
    return [{"t": f"{(d0 + timedelta(days=i)).isoformat()}T00:00:00+05:30", "o": c - 1, "h": c + 1, "l": c - 2, "c": c} for i, c in enumerate(closes)]


def _split_closes():
    # a 1:10 split, ex-date Fri 9 Oct: the bhavcopy keeps the traded closes
    oc.save("2026-10-07", {"ABC": 1000.0})
    oc.save("2026-10-08", {"ABC": 1010.0})
    oc.save("2026-10-09", {"ABC": 103.0})


def test_split_keeps_the_adjusted_history(mem):
    _split_closes()
    bars = _bars(100.0, 101.0, 102.5)                   # broker candles adjusted back; the last (ex-date) is on the new basis
    out = oc.history_close(bars, "ABC", "cas", "NSE", now=NOW)
    assert [b["c"] for b in out] == [100.0, 101.0, 103.0]        # the ex-date's own close is on the same basis: laid over
    assert out[0] is bars[0] and out[1] is bars[1]
    assert bars[2]["c"] == 102.5                                  # the broker's list is never changed in place


def test_a_close_far_from_the_candle_is_left_alone_even_without_a_calendar(mem):
    oc.save("2026-10-09", {"ABC": 1030.0})
    bars = _bars(100.0, 101.0, 102.5)
    assert oc.history_close(bars, "ABC", "cas", "NSE", now=NOW) is bars
    assert oc.overlay_bars(bars, "ABC", False, NOW) is bars
    assert oc.with_reference(bars, "ABC", "2026-10-09", NOW) is bars
    assert oc.same_basis(1030.0, 102.5) is False and oc.same_basis(104.0, 102.5) is True and oc.same_basis(None, 1) is True


def test_a_small_close_difference_is_still_laid_over(mem):
    oc.save("2026-10-09", {"ABC": 103.0})
    out = oc.overlay_bars(_bars(100.0, 101.0, 102.5), "ABC", False, NOW)
    assert out[-1]["c"] == 103.0 and out[-1]["official"] and out[-1]["h"] == 103.5


def test_days_before_a_known_ex_date_are_skipped_even_when_the_gap_is_small(mem):
    # a 5:4 bonus (factor 0.8): 1,010 is only 20% from an adjusted 808, inside BASIS_SLACK, but the ex-date says it is unadjusted
    corp_actions.save("IN", [corp_actions.row("IN", "ABC", {"kind": "bonus", "label": "Bonus", "text": "Bonus 1:4", "ratio": [1, 4],
                                                            "factor": 1.25}, datetime(2026, 10, 9).date())])
    assert corp_actions.adjusts(corp_actions.load("IN")["rows"][0])
    oc.save("2026-10-07", {"ABC": 1000.0})
    oc.save("2026-10-08", {"ABC": 900.0})
    oc.save("2026-10-09", {"ABC": 815.0})
    bars = _bars(800.0, 810.0, 812.0)
    out = oc.history_close(bars, "ABC", "cas", "NSE", now=NOW)
    assert [b["c"] for b in out] == [800.0, 810.0, 815.0]        # 7th and 8th are before the ex-date: kept as the broker's
    assert oc.official("ABC", "2026-10-08", use_quote=False) is None and oc.official("ABC", "2026-10-09", use_quote=False) == 815.0
    assert oc.before_ex_date("ABC", "2026-10-08") and not oc.before_ex_date("ABC", "2026-10-09") and not oc.before_ex_date("XYZ", "2026-10-08")
