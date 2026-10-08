"""The numbers on an experiment page add up: one drawdown measure, unseen-data parts that reconcile with the trade list,
returns after costs, slippage shown as a cost, the open trade counted once, and no weekend candles for weekday markets."""
import math
from datetime import date

import numpy as np
import pytest

from app import research
from app.data.calendar import trading_bars
from app.engine import portfolio
from app.engine import verdict as V
from app.engine.core import backtest
from app.intel.yahoo import Yahoo
from app.data.yahoo_markets import YahooProvider
from app.models import Strategy
from tests.fake_yahoo import fake_yahoo
from tests.test_engine import bars_from
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)
from tests.test_verdict import ema_cross, wavy


def run(bars, s, start=250, kind="in_eq"):
    base = backtest(bars, s, start, cost_kind=kind)
    return base, V.evaluate(bars, s, start, base, cost_kind=kind, days=1825, max_days=3650)


def check(v, cid):
    return next(c for c in v["checks"] if c["id"] == cid)


def every(base):
    return [*base["trades"], *([base["open_trade"]] if base["open_trade"] else [])]


# ---------- one drawdown ----------
def test_bad_luck_drawdown_yours_is_the_worst_fall():
    bars = wavy()
    base, v = run(bars, ema_cross())
    d = check(v, "shuffle")["data"]
    assert d["daily"] is True
    assert d["yours"] == pytest.approx(-base["stats"]["mdd"], abs=1e-6)       # the same day-by-day measure
    assert d["worst"] >= d["p95"] >= 0


def test_bad_luck_drawdown_covers_every_change_in_the_account():
    """Each trade's day-by-day path, in order, sums to its P&L, and all of them to the account's change."""
    bars = wavy(900)
    base = backtest(bars, ema_cross(), 250, cost_kind="in_eq")
    paths = base["_paths"]
    assert len(paths) == len(every(base))
    for p, t in zip(paths, every(base)):
        assert float(np.sum(p)) == pytest.approx(t["pnl"], abs=1e-6)
    assert sum(float(np.sum(p)) for p in paths) == pytest.approx(base["costs"]["net_pnl"], abs=0.01)


def test_fall_text_never_reads_minus_zero():
    assert V.fall_text(0.0) == "0%" and V.fall_text(0.04) == "0%" and V.fall_text(2.46) == "2.5%"


# ---------- unseen data ----------
def test_unseen_parts_add_up_to_the_trades_and_the_return():
    bars = wavy()
    base, v = run(bars, ema_cross())
    d = check(v, "unseen")["data"]
    trades = every(base)
    # counts: every closed trade is in exactly one part, the open one is counted separately
    assert d["built_trades"] + d["unseen_trades"] == base["stats"]["n"] == len(base["trades"])
    assert d["open_built"] + d["open_unseen"] == (1 if base["open_trade"] else 0)
    # returns: each part is the sum of its own trades' P&L, and the two parts make the total return
    cap = 500000
    built = sum(t["pnl"] for t in trades if t["part"] == "built") / cap * 100
    unseen = sum(t["pnl"] for t in trades if t["part"] == "unseen") / cap * 100
    assert d["built_ret"] == pytest.approx(built) and d["unseen_ret"] == pytest.approx(unseen)
    assert d["built_ret"] + d["unseen_ret"] == pytest.approx(base["stats"]["ret"], abs=1e-6)
    assert d["unseen_trades"] > 0 and d["built_trades"] > 0


def test_a_trade_across_the_split_is_labelled_and_counted_with_the_built_part():
    bars = wavy()
    s = ema_cross()
    base = backtest(bars, s, 250, cost_kind="in_eq")
    split_t = bars[base["_split"]]["t"]
    spanning = [t for t in every(base) if t["entry_t"] <= split_t and (t["exit_t"] is None or t["exit_t"] > split_t)]
    flagged = [t for t in every(base) if t.get("spans_split")]
    assert flagged == spanning
    assert all(t["part"] == "built" for t in flagged)
    d = V.check_unseen(bars, base, 250, s.risk.capital)["data"]
    assert d["spanning"] == len(spanning)


def test_spanning_trade_found_on_a_made_up_series():
    """A long, slow wave: one trade is open across the split, and the check says so."""
    closes = [100 + 20 * math.sin(i / 40) for i in range(700)]
    bars = bars_from(closes)
    s = Strategy(entry=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "sma", "p": 10}}],
                 exit=[{"l": {"t": "price"}, "op": "xb", "r": {"t": "sma", "p": 10}}],
                 risk={"capital": 100000, "sl": 0, "brokerage": 0, "slippage": 0})
    for start in range(50, 120, 3):
        base = backtest(bars, s, start)
        if any(t.get("spans_split") for t in every(base)):
            break
    else:
        pytest.fail("no start put a trade across the split")
    d = V.check_unseen(bars, base, start, 100000)["data"]
    assert d["spanning"] >= 1 and d["built_trades"] + d["unseen_trades"] == len(base["trades"])


# ---------- returns after costs, slippage, the open trade ----------
def test_trade_return_is_after_costs_like_its_pnl():
    bars = wavy(900)
    base = backtest(bars, ema_cross(), 250, cost_kind="in_eq")
    for t in every(base):
        assert t["ret"] == pytest.approx(t["pnl"] / (t["qty"] * t["entry"]) * 100)
        assert (t["ret"] > 0) == (t["pnl"] > 0)


def test_trade_list_adds_up_to_the_account_with_an_open_trade():
    for n in range(700, 900, 7):                        # find a run that ends with a trade still open
        base = backtest(wavy(n), ema_cross(), 250, cost_kind="in_eq")
        if base["open_trade"]:
            break
    else:
        pytest.fail("no run ended with a trade open")
    o = base["open_trade"]
    assert o["costs"] > 0 and o["pnl"] == pytest.approx(o["qty"] * (o["exit"] - o["entry"]) - o["costs"])
    assert sum(t["pnl"] for t in every(base)) == pytest.approx(base["costs"]["net_pnl"], abs=0.01)


def test_slippage_is_a_cost_line_and_profit_before_costs_is_before_it():
    bars = wavy(900)
    s = ema_cross(slippage=0.5, brokerage=0)
    base = backtest(bars, s, 250, cost_kind="flat")          # no charges at all: slippage is the only cost
    c = base["costs"]
    slip = next(i for i in c["items"] if i["label"] == "Slippage")
    assert [i["label"] for i in c["items"]] == ["Slippage"]
    # the price move at the candles' own closes, before any slippage
    gross = 0.0
    for t in base["trades"]:
        gross += t["qty"] * (t["exit"] / (1 - 0.005) - t["entry"] / (1 + 0.005))
    if base["open_trade"]:
        o = base["open_trade"]
        gross += o["qty"] * (o["exit"] - o["entry"] / (1 + 0.005))
    assert c["gross_pnl"] == pytest.approx(gross, abs=0.05)
    assert c["gross_pnl"] - slip["amount"] == pytest.approx(c["net_pnl"], abs=0.05)
    assert c["total"] == pytest.approx(slip["amount"], abs=0.01)


def test_no_slippage_line_without_slippage():
    base = backtest(wavy(900), ema_cross(slippage=0, brokerage=0), 250, cost_kind="flat")
    assert base["costs"]["items"] == [] and base["costs"]["gross_pnl"] == base["costs"]["net_pnl"]


# ---------- the verdict states the comparison with buy and hold ----------
def test_verdict_states_buy_and_hold_as_a_fact():
    bars = wavy()
    base, v = run(bars, ema_cross())
    hold = base["stats"]["buy_hold_ret"]
    assert "buying and holding over the same period" in v["summary"]
    assert V._pc(hold) in v["summary"] and V._pc(base["stats"]["ret"]) in v["summary"]
    assert "Worth" not in v["summary"] and "real money" not in v["summary"]


def test_edge_wording_has_no_advice():
    checks = [{"id": i, "status": "pass"} for i in ("unseen", "nearby", "shuffle", "sample")]
    v = V.decide(checks, 40, 24.6, ema_cross(), 365, 3650, 70.5)
    assert v["verdict"] == "edge"
    assert v["summary"].endswith("The strategy returned +24.6% after costs, less than buying and holding over the same period (+70.5%).")
    for word in ("Worth", "should", "real money", "Treat it"):
        assert word not in v["summary"]
    mixed = V.decide([{"id": "unseen", "status": "pass"}, {"id": "nearby", "status": "warn"}, {"id": "shuffle", "status": "pass"},
                      {"id": "sample", "status": "pass"}], 40, 5.0, ema_cross(), 365, 3650, 1.0)
    assert mixed["verdict"] == "mixed" and "Treat it" not in mixed["summary"] and "more than buying and holding" in mixed["summary"]


# ---------- a group: the same reconciliation ----------
def test_group_unseen_parts_add_up():
    a = bars_from([100 + 10 * math.sin(i / 7) for i in range(400)])
    b = bars_from([50 + 6 * math.sin(i / 5 + 1) for i in range(400)])
    s = Strategy(entry=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "sma", "p": 5}}],
                 exit=[{"l": {"t": "price"}, "op": "xb", "r": {"t": "sma", "p": 5}}],
                 risk={"capital": 100000, "sl": 0, "brokerage": 0, "slippage": 0.1, "sizing": "capital", "perTrade": 40000})
    ds = [{"inst": {"symbol": k, "id": f"X:{k}"}, "bars": x, "start": 50, "lot": 1, "kind": "flat"} for k, x in (("A", a), ("B", b))]
    out = research.run_group(ds, s, {"maxOpen": 2}, 365, 3650)
    d = check(out["verdict"], "unseen")["data"]
    assert d["built_trades"] + d["unseen_trades"] == len(out["trades"])
    total = sum(t["pnl"] for t in [*out["trades"], *out["open_trades"]]) / 100000 * 100
    assert d["built_ret"] + d["unseen_ret"] == pytest.approx(total, abs=1e-6)
    assert d["built_ret"] + d["unseen_ret"] == pytest.approx(out["stats"]["ret"], abs=1e-6)
    sh = check(out["verdict"], "shuffle")["data"]
    assert sh["yours"] == pytest.approx(-out["stats"]["mdd"], abs=1e-6)
    assert "_paths" not in out


# ---------- market calendars ----------
def _days(bars):
    return [date.fromisoformat(b["t"][:10]).weekday() for b in bars]


def test_trading_bars_drops_weekends_for_weekday_markets():
    week = [{"t": f"2026-10-{d:02d}T00:00:00-04:00", "o": 1, "h": 1, "l": 1, "c": 1} for d in range(3, 12)]   # Sat 3 .. Sun 11
    us = trading_bars("US", week, "1d")
    assert [b["t"][:10] for b in us] == [f"2026-10-{d:02d}" for d in (5, 6, 7, 8, 9)]
    assert trading_bars("CRYPTO", week, "1d") == week                  # crypto trades every day
    assert trading_bars("IN", week, "1d") == week                      # the exchange's own feed is taken as sent
    sunday_evening = [{"t": "2026-10-04T22:00:00+01:00", "c": 1}, {"t": "2026-10-03T12:00:00+01:00", "c": 1}]
    assert trading_bars("FX", sunday_evening, "1h") == sunday_evening[:1]     # forex's week opens on Sunday evening
    assert trading_bars("FX", sunday_evening, "1d") == []


@pytest.mark.parametrize("market,sym", [("US", "AAPL"), ("FX", "EURUSD=X")])
def test_weekday_markets_have_no_weekend_candles(market, sym):
    prov = YahooProvider(market, Yahoo(transport=fake_yahoo()))
    inst = prov.instrument(sym)
    bars = prov.history(inst, "1d", 730)
    assert len(bars) > 400 and max(_days(bars)) <= 4
    # about 261 weekdays a year, not 365; the demo world's US stocks also keep the exchange's holidays (about 252 sessions)
    from datetime import timedelta
    from app.data.calendar import is_trading_day
    today = date.today()
    sessions = sum(is_trading_day("US", today - timedelta(days=d)) for d in range(730))
    assert len(bars) == pytest.approx(sessions if market == "US" else 730 * 5 / 7, abs=10)


def test_a_weekday_backtest_never_trades_at_the_weekend(api):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "AAPL", "strategy": EMA, "instrument": "US:AAPL"}).json()
    exp = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1825}).json()["experiment"]
    stamps = [t[k] for t in exp["trades"] for k in ("entry_t", "exit_t") if t[k]]
    assert stamps and all(date.fromisoformat(s[:10]).weekday() < 5 for s in stamps)
    assert exp["candles"] < 1825 * 5 / 7 + 10


def test_spot_forex_has_no_volume():
    prov = YahooProvider("FX", Yahoo(transport=fake_yahoo()))
    assert all(b["v"] == 0 for b in prov.history(prov.instrument("EURUSD=X"), "1d", 60))
