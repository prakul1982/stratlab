"""R11A: market analytics dates, labels and clock times. Half-day closes in /markets, the PCR's "at the close" claim on an
old recording, the participant volume change's day, the VIX fallback's day, weekly rotation by week, live breadth before
the first round and its quarter-hour points, max pain over the PCR's window, and the expiry-day 409's words."""
from datetime import date, datetime, time as dtime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import breadth_live, db, main, positioning as P, rotation as R, vix as V
from app.data import _hours
from app.data.markets import BY_ID
from tests import fake_positioning as FP
from tests import world as W
from tests.test_breadth import mem  # noqa: F401  (fixture)
from tests.test_breadth_live import live, with_base

IST = P.IST


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    P.clear_cache()


# ---------- 1.2: an early close is the day's close in /markets ----------
def test_markets_send_a_half_days_early_close():
    assert _hours(BY_ID["US"], date(2026, 11, 27))["close"] == "13:00"      # the day after Thanksgiving
    assert _hours(BY_ID["US"], date(2026, 12, 24))["close"] == "13:00"
    assert _hours(BY_ID["UK"], date(2026, 12, 24))["close"] == "12:30"
    assert _hours(BY_ID["US"], date(2026, 11, 26))["close"] == "16:00"      # a holiday keeps the usual hours
    assert _hours(BY_ID["US"], date(2026, 10, 15))["close"] == "16:00"
    assert _hours(BY_ID["JP"], date(2026, 10, 15))["close"] == BY_ID["JP"]["hours"]["close"]


# ---------- 1.3: an old recording is not "the last close" ----------
def test_pcr_table_dates_a_recording_older_than_the_close(w, monkeypatch):
    monkeypatch.setattr(main.options_data, "ready", lambda: False)
    FP.record_days(db.add_option_snapshot, "BANKNIFTY", [date(2026, 10, 9)], spot=55000.0, gap=100)
    now = datetime(2026, 10, 15, 20, 0, tzinfo=IST)                          # the close named is 15 Oct's
    row = next(r for r in P.pcr_table(main.options_data, now) if r["name"] == "BANKNIFTY")
    assert row["source"] == "recorded" and row["at_close"] is False and row["as_of"].startswith("2026-10-09T15:25")
    FP.record_days(db.add_option_snapshot, "BANKNIFTY", [date(2026, 10, 15)], spot=55000.0, gap=100)
    P.clear_cache()
    row = next(r for r in P.pcr_table(main.options_data, now) if r["name"] == "BANKNIFTY")
    assert row["at_close"] is True and row["as_of"].startswith("2026-10-15")


# ---------- 1.4: the volume change is against the labelled day ----------
def test_participant_volume_change_is_from_the_labelled_day_only(w):
    d2, d1, d0 = date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1)
    for d, kinds in ((d2, ("oi", "vol")), (d1, ("oi",)), (d0, ("oi", "vol"))):
        P.store_day("part", d.isoformat(), {k: P.participant_rows(FP.participant_csv(d, k))["rows"] for k in kinds})
    view = P.participants_today(datetime(2026, 10, 1, 20, 0, tzinfo=IST))
    assert view["prev"] == "2026-09-30"
    fii = next(r for r in view["vol"] if r["id"] == "fii")
    assert fii["fut_idx_long"] is not None and "fut_idx_long_chg" not in fii and "fut_idx_net_chg" not in fii
    assert "fut_idx_long_chg" in next(r for r in view["oi"] if r["id"] == "fii")


# ---------- 1.5: the VIX fallback carries its day ----------
class Down:
    def _get(self, *a, **k):
        raise RuntimeError("down")


def test_vix_fallback_close_says_its_day_and_is_not_its_own_past(w):
    V.forget()
    try:
        V.store({"2026-10-08": [14, 15, 13, 14.2], "2026-10-09": [14, 15, 13, 16.73]})
        p = V.panel(None, datetime(2026, 10, 15, 11, 0, tzinfo=IST), feed=Down())
        assert p["quote"] is None and p["value"] == 16.73 and p["value_day"] == "2026-10-09"
        assert p["percentile"]["days"] == 1 and p["percentile"]["high"] == 14.2
    finally:
        V.forget()


# ---------- 1.6: weekly rotation pairs closes by week ----------
def _series():
    days = pd.bdate_range("2025-01-06", "2026-10-09")
    rng = np.random.default_rng(1)
    b = 100 * np.cumprod(1 + rng.normal(0, .01, len(days)))
    m = 100 * np.cumprod(1 + rng.normal(0, .012, len(days)))
    return ([{"t": d.date().isoformat(), "c": v} for d, v in zip(days, b)],
            [{"t": d.date().isoformat(), "c": v} for d, v in zip(days, m)])


def test_weekly_rotation_keeps_a_week_whose_last_bar_is_on_another_day():
    bench, mem_ = _series()
    b = R.closes(bench, "weekly")
    full = [p["t"] for p in R.path(R.closes(mem_, "weekly"), b, 5)]
    assert full == ["2026-09-11", "2026-09-18", "2026-09-25", "2026-10-02", "2026-10-09"]
    lag = R.path(R.closes(mem_[:-1], "weekly"), b, 5)                         # no bar for Fri 9 Oct
    assert [p["t"] for p in lag] == full
    gap = R.path(R.closes([x for x in mem_ if x["t"] != "2026-09-18"], "weekly"), b, 5)   # none for Fri 18 Sep
    assert [p["t"] for p in gap] == full


# ---------- 1.7 and 2: live breadth before the first round, and points by quarter hour ----------
def test_live_breadth_before_the_first_round_is_pending_not_unavailable(mem):  # noqa: F811
    with_base(mem)
    v = breadth_live.view("nifty500", datetime(2026, 10, 1, 3, 45, 30, tzinfo=timezone.utc), ready=True)    # 09:15:30 IST
    assert v["state"] == "pending" and "coming shortly" in v["message"] and "aren't available" not in v["message"]
    later = breadth_live.view("nifty500", datetime(2026, 10, 1, 4, 5, tzinfo=timezone.utc), ready=True)     # 09:35, none yet
    assert later["state"] == "unavailable"
    assert breadth_live.view("nifty500", datetime(2026, 10, 1, 3, 46, tzinfo=timezone.utc), ready=False)["state"] == "unavailable"


def test_live_breadth_points_are_keyed_by_their_quarter_hour(mem):  # noqa: F811
    with_base(mem)
    L = live(mem)
    for mi in (31, 33, 44):          # 11:01 IST, a retry at 11:03 in the same quarter hour, and 11:14
        assert L.round("IN", datetime(2026, 10, 1, 5, mi, tzinfo=timezone.utc))["ok"]
    assert [p[0] for p in breadth_live.load("nifty500", "2026-10-01")["points"]] == ["11:00"]


# ---------- 2: max pain over the PCR's window ----------
def test_max_pain_counts_the_same_window_as_the_pcr():
    spot, rows = 25000, []
    for i in range(-30, 31):
        coi, poi = (50000 if i > 0 else 1000), (50000 if i < 0 else 1000)
        if i <= -16:
            coi = 400000              # heavy call open interest outside the 15-strike window
        rows.append([spot + 50 * i, 1, 1, 1, coi, 1, 1, 1, poi, 0, 0])
    st = P.chain_stats(rows, spot, "2026-10-20", datetime(2026, 10, 15, 11, 0, tzinfo=IST))
    assert st["max_pain"] == P.max_pain(P.near(rows, spot)) == 25000
    assert P.max_pain(rows) != 25000                                         # the whole read would say otherwise


# ---------- 2: the expiry-day 409 says the settlement is fixed ----------
def test_greeks_after_settlement_on_expiry_day_say_the_settlement_is_fixed(monkeypatch):
    from tests.fake_options_kite import _expiries
    from tests.test_options_api import setup
    setup(monkeypatch)
    e = _expiries()[0]
    monkeypatch.setattr(main.positioning, "ist_now", lambda: datetime.combine(e, dtime(15, 35), IST))
    try:
        r = TestClient(main.app).post("/options/greeks", json={"exchange": "NFO", "underlying": "NIFTY", "expiry": e.isoformat(),
                                                               "legs": [{"side": "buy", "opt": "CE", "strike": 25000, "qty": 75, "fill": 150}]})
        assert r.status_code == 409
        text = str(r.json())
        assert "settlement price is already fixed" in text and "has passed" not in text
    finally:
        main.app.dependency_overrides.clear()
