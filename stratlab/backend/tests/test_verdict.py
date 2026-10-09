import math

import pytest

from app.engine import verdict as V
from app.engine.core import backtest
from app.models import Strategy
from tests.test_engine import bars_from


def ema_cross(**risk):
    return Strategy(entry=[{"l": {"t": "ema", "p": 20}, "op": "xa", "r": {"t": "ema", "p": 50}}],
                    exit=[{"l": {"t": "ema", "p": 20}, "op": "xb", "r": {"t": "ema", "p": 50}}],
                    risk={"capital": 500000, "riskPct": 1, "sl": 3, "brokerage": 20, "slippage": 0.05, **risk})


def wavy(n=1400, period=9):
    return bars_from([20000 * (1 + 0.0003 * i) + 1500 * math.sin(i / period) for i in range(n)])


def run(bars, s, start=250):
    base = backtest(bars, s, start, cost_kind="in_eq")
    return base, V.evaluate(bars, s, start, base, cost_kind="in_eq", days=1825, max_days=3650)


def test_checks_have_expected_shapes():
    bars = wavy()
    base, v = run(bars, ema_cross())
    ids = [c["id"] for c in v["checks"]]
    assert ids == ["unseen", "nearby", "shuffle", "sample"]
    for c in v["checks"]:
        assert c["status"] in ("pass", "warn", "fail", "skip") and c["detail"]
    nearby = v["checks"][1]["data"]
    assert len(nearby["grid"]) == 5 and all(len(r) == 5 for r in nearby["grid"])
    assert nearby["cols"] == [12, 16, 20, 24, 28] and nearby["rows"] == [30, 40, 50, 60, 70]
    assert nearby["yours"] == [2, 2]
    # the centre cell is the backtest itself
    assert nearby["grid"][2][2] == pytest.approx(base["stats"]["ret"], abs=0.01)
    unseen = v["checks"][0]["data"]
    assert 0 < unseen["split_index"] < len(bars) - 250
    # the headline is the facts, how it did against buy and hold and what the checks found, not "Likely a real edge." (R11C-009)
    assert v["headline"] == V.fact_headline(v["verdict"], v["checks"], len(base["trades"]), base["stats"]["ret"], base["stats"]["buy_hold_ret"])
    assert "buy and hold after costs; " in v["headline"] and v["headline"].endswith(".")
    assert 1 <= len(v["suggestions"]) <= 4


def test_shuffle_is_deterministic():
    trades = [{"pnl": p} for p in [5000, -3000, 2000, -8000, 7000, -1000, 4000, -2500]]
    a, b = V.check_shuffle(trades, 100000), V.check_shuffle(trades, 100000)
    assert a == b
    assert a["data"]["worst"] >= a["data"]["p95"] >= 0


def test_sample_thresholds():
    assert V.check_sample(40)["status"] == "pass"
    assert V.check_sample(20)["status"] == "warn"
    assert V.check_sample(3)["status"] == "fail"


def test_rules_without_lengths_skip_nearby():
    s = Strategy(entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 20000}}])
    bars = wavy(400)
    c = V.check_nearby(bars, s, 50, 1, "flat", None)
    assert c["status"] == "skip"


def _fake(monkeypatch, unseen, nearby, shuffle="pass"):
    mk = lambda i, st: {"id": i, "title": i, "status": st, "detail": "x", "data": None}
    monkeypatch.setattr(V, "check_unseen", lambda *a: mk("unseen", unseen))
    monkeypatch.setattr(V, "check_nearby", lambda *a: mk("nearby", nearby))
    monkeypatch.setattr(V, "check_shuffle", lambda *a, **k: mk("shuffle", shuffle))   # takes the trades' day-by-day paths by keyword


@pytest.mark.parametrize("unseen,nearby,ret,n,expected", [
    ("pass", "pass", 12.0, 40, "edge"),
    ("fail", "pass", 12.0, 40, "luck"),
    ("pass", "fail", 12.0, 40, "luck"),
    ("pass", "warn", 12.0, 40, "mixed"),
    ("pass", "pass", -3.0, 40, "no_edge"),
    ("pass", "pass", 30.0, 6, "not_enough"),
])
def test_verdict_logic(monkeypatch, unseen, nearby, ret, n, expected):
    _fake(monkeypatch, unseen, nearby)
    base = {"trades": [{"pnl": 1.0}] * n, "stats": {"ret": ret}}
    v = V.evaluate(wavy(300), ema_cross(), 50, base)
    assert v["verdict"] == expected


def test_edge_suggests_paper_trading(monkeypatch):
    _fake(monkeypatch, "pass", "pass")
    v = V.evaluate(wavy(300), ema_cross(), 50, {"trades": [{"pnl": 1.0}] * 40, "stats": {"ret": 9}})
    assert v["suggestions"][0]["action"] == "paper_trade"
