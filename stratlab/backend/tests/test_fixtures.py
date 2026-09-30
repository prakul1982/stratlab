"""The real-price snapshot: building it, packing it, and (when the admin has saved one into tests/fixtures) running the
analysis tools on real market behaviour."""
import os
from datetime import date, timedelta

import numpy as np
import pytest

from app import fixtures, rotation, scan

REAL = os.path.join(os.path.dirname(__file__), "fixtures", "real_prices.json.gz")


def bars_from(closes, start=date(2024, 1, 1)):
    return [{"t": (start + timedelta(days=i)).isoformat(), "o": c, "h": c, "l": c, "c": c, "v": 1} for i, c in enumerate(closes)]


class Prov:
    def __init__(self, fail=()):
        self.fail = set(fail)

    def ready(self): return True
    def instrument(self, key): return {"symbol": key, "name": key}

    def history(self, inst, tf, days):
        if inst["symbol"] in self.fail:
            raise RuntimeError("no data")
        rng = np.random.default_rng(len(inst["symbol"]))
        return bars_from(list(100 * np.cumprod(1 + rng.normal(0, 0.01, 60))))


class Reg:
    def __init__(self, prov): self.prov = prov
    def provider(self, m): return self.prov if m == "US" else None
    def resolve(self, iid): return self.prov, {"symbol": iid.split(":")[1]}


def test_snapshot_covers_indices_and_groups_and_survives_a_bad_symbol(monkeypatch, tmp_path):
    monkeypatch.setattr(fixtures.universes, "resolve", lambda reg, m, members: ([f"US:{x['symbol']}" for x in members], []))
    snap = fixtures.build(Reg(Prov(fail={"XLK"})), markets=("US", "IN"))
    us = snap["markets"]["US"]
    assert us["SPY"]["kind"] == "benchmark" and us["SMH"]["kind"] == "index" and us["AAPL"]["kind"] == "stock"
    assert "XLK" not in us and any(p.startswith("XLK") for p in snap["problems"])
    assert "IN: market data is offline" in snap["problems"]
    path = tmp_path / "real.json.gz"
    path.write_bytes(fixtures.pack(snap))
    back = fixtures.load(str(path))
    assert fixtures.bars(back, "US", "SPY")[0].keys() == {"t", "o", "h", "l", "c", "v"} and len(fixtures.bars(back, "US", "SPY")) == 60


@pytest.mark.skipif(not os.path.exists(REAL), reason="no real-price snapshot saved in tests/fixtures yet")
def test_tools_behave_on_real_prices():
    snap = fixtures.load(REAL)
    for market, rows in snap["markets"].items():
        bench = next(s for s, r in rows.items() if r["kind"] == "benchmark")
        b = rotation.closes(fixtures.bars(snap, market, bench), "weekly")
        paths = {s: rotation.path(rotation.closes(fixtures.bars(snap, market, s), "weekly"), b, 5)
                 for s, r in rows.items() if r["kind"] == "index"}
        drawn = {s: p for s, p in paths.items() if p}
        assert len(drawn) >= 5, f"{market}: too few indices drawable"
        for pts in drawn.values():
            assert all(80 < p["x"] < 120 and 80 < p["y"] < 120 for p in pts)          # real data stays near 100
        stocks = [s for s, r in rows.items() if r["kind"] == "stock"][:10]
        results = [scan.analyse(fixtures.bars(snap, market, s)) for s in stocks]
        assert all(r is None or r["stage"] in (None, 1, 2, 3, 4) for r in results)
