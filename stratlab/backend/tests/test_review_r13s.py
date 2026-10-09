"""Round 13 Safari review (R13S): the account stops at zero."""
import math

from app.engine import portfolio
from app.engine.core import backtest
from app.engine.verdict import _trade_dd, evaluate_portfolio
from app.models import Strategy
from tests.test_engine import bars_from
from tests.test_engine_intraday import day
from tests.test_portfolio import ALWAYS, ds

CAP = 100000


def _group_strategy(**risk):
    r = {"capital": CAP, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": CAP}
    r.update(risk)
    return Strategy(tf="15m", entry=ALWAYS, exit=[], risk=r)


def _crash(start):
    return day("2026-01-05", [start, start, start * 0.8, start * 0.5, start * 0.3, start * 0.2, start * 0.2, start * 0.2])


def test_group_account_stops_at_zero_not_below():
    """Each slot is sized on the whole capital, so three losing slots can lose more than the account has."""
    data = [ds(s, _crash(100.0)) for s in "ABC"]
    out = portfolio.run(data, _group_strategy(), max_open=3)
    assert out["stats"]["ret"] == -100.0
    assert min(out["equity"]) == 0.0 and out["equity"][-1] == 0.0
    assert out["stats"]["emptied_on"] == "2026-01-05"
    assert out["stats"]["mdd"] == -100.0
    # the trades add up to the account's change, so every figure derived from them agrees
    assert math.isclose(sum(t["pnl"] for t in out["trades"]), -CAP, abs_tol=0.01)
    assert out["costs"]["net_pnl"] == -CAP
    assert not out["open_trades"]
    assert any(t.get("capped_loss") for t in out["trades"])


def test_nothing_opens_after_the_account_is_empty():
    data = [ds(s, _crash(100.0) + day("2026-01-06", [100 + i for i in range(8)])) for s in "AB"]
    out = portfolio.run(data, _group_strategy(), max_open=2)
    assert out["stats"]["emptied_on"] == "2026-01-05"
    assert all(t["entry_t"][:10] == "2026-01-05" for t in out["trades"])
    assert out["equity"][-1] == 0.0


def test_a_group_that_does_not_empty_has_no_empty_date():
    up = day("2026-01-05", [100 + i for i in range(10)])
    out = portfolio.run([ds("A", up)], _group_strategy(perTrade=20000), max_open=1)
    assert out["stats"]["emptied_on"] is None


def test_unseen_and_bad_luck_figures_never_pass_100_percent():
    data = [ds(s, _crash(100.0) + day("2026-01-06", [20 + i for i in range(40)])) for s in "ABC"]
    out = portfolio.run(data, _group_strategy(), max_open=3)
    v = evaluate_portfolio(lambda *a: out, out, _group_strategy(), 365, 3650)
    for c in v["checks"]:
        d = c.get("data") or {}
        for k in ("yours", "p95", "worst"):
            assert d.get(k) is None or d[k] <= 100.0
    assert _trade_dd([-90000, -90000], CAP) == 100.0


def test_short_squeeze_closes_the_account_at_zero():
    """A short can lose more than the account has: it is closed when the value reaches zero, and nothing re-opens."""
    closes = [100.0] * 6 + [150, 210, 260, 100, 100, 100, 100]
    s = Strategy(side="short", entry=ALWAYS, exit=[],
                 risk={"capital": CAP, "riskPct": 1, "sl": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": CAP,
                       "leverage": 1})
    # sized on all of the capital, a short that more than doubles loses everything
    out = backtest(bars_from(closes), s, 1)
    assert out["stats"]["ret"] >= -100.0
    assert min(out["equity"]) >= 0.0
    assert out["stats"]["emptied_on"]
    assert any(t["why"] == "Account emptied" for t in out["trades"])
    assert math.isclose(out["equity"][-1], 0.0, abs_tol=0.01)
    assert not out["open_trade"]
