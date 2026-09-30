"""Sector rotation: quadrants, the path maths, and the endpoint."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app import main, rotation


def bars_from(closes, start=datetime(2023, 1, 2, tzinfo=timezone.utc)):
    return [{"t": (start + timedelta(days=i)).isoformat(), "o": c, "h": c, "l": c, "c": c, "v": 0} for i, c in enumerate(closes)]


def test_quadrants():
    assert [rotation.quadrant(*p) for p in [(101, 101), (101, 99), (99, 99), (99, 101)]] == ["leading", "weakening", "lagging", "improving"]


def test_a_member_pulling_ahead_is_right_of_centre_and_one_falling_behind_left():
    n = 400
    bench = pd.Series(np.linspace(100, 130, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    bench.index = idx
    ahead = pd.Series(np.r_[np.linspace(100, 120, n - 60), np.linspace(120, 175, 60)], index=idx)   # outperforming lately
    behind = pd.Series(np.r_[np.linspace(100, 125, n - 60), np.linspace(125, 105, 60)], index=idx)  # underperforming lately
    a = rotation.path(ahead, bench, 5)
    b = rotation.path(behind, bench, 5)
    assert len(a) == 5 and a[-1]["x"] > 100 and b[-1]["x"] < 100
    assert [p["t"] for p in a] == sorted(p["t"] for p in a)


def test_weekly_takes_each_weeks_last_close():
    s = rotation.closes(bars_from([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), "weekly")   # Mon 2 Jan 2023 onwards
    assert list(s.values) == [5, 10] and s.index[0].weekday() == 4
    assert str(s.index[-1].date()) == "2023-01-11"      # the week so far is dated by its last real day, not the coming Friday


def test_endpoint_rotates_us_sectors(monkeypatch):
    rng = np.random.default_rng(3)
    series = {sym: bars_from(list(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 700)))) for sym in
              rotation.SECTORS["US"]["members"] + ["SPY"]}

    class Prov:
        def ready(self): return True
        def instrument(self, key): return {"symbol": key, "name": key}
    prov = Prov()

    class Reg:
        def provider(self, m): return prov
        def resolve(self, iid): return prov, {"symbol": iid.split(":")[1]}
    monkeypatch.setattr(main, "markets", Reg())
    def load(iid, days):
        if iid == "US:XLU":
            raise RuntimeError("Yahoo Finance said: rate limited")
        return series[iid.split(":")[1]]
    monkeypatch.setattr(rotation, "load_daily", lambda registry: load)
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "plan": "pro", "_plan": "pro"}
    try:
        r = TestClient(main.app).get("/research/rotation?region=US&set=sectors&interval=weekly&tail=6").json()
        assert r["benchmark"] == "SPY" and len(r["rows"]) == 10 and r["name"] == "S&P 500 sectors"
        assert len(r["skipped"]) == 1 and r["skipped"][0].startswith("XLU") and "yahoo" not in r["skipped"][0].lower()
        row = r["rows"][0]
        assert len(row["points"]) == 6 and row["quadrant"] in ("leading", "improving", "weakening", "lagging")
        assert {x["name"] for x in r["rows"]} >= {"Technology", "Energy"}
        assert TestClient(main.app).get("/research/rotation?region=US&set=sectors&tail=99").json()["tail"] == 12
    finally:
        main.app.dependency_overrides.clear()
