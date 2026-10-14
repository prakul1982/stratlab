"""A rule's signal on a candle's close fills at the next candle's open; live fills at the latest price."""
import pytest

from app.engine.core import Ctx, Engine, backtest
from app.models import Strategy
from tests.test_engine_intraday import RISK, S, cond, day, run

FLAT = {"capital": 100000, "riskPct": 1, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0,
        "sizing": "capital", "perTrade": 10000}


def bar(d, o, h, l, c):
    return {"t": f"2024-01-{d:02d}T00:00:00+05:30", "o": o, "h": h, "l": l, "c": c, "v": 1000.0}


def above(v):
    return [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": v}}]


def daily(entry, exit=None, **risk):
    return Strategy(entry=entry, exit=exit or above(1e9), risk={**FLAT, **risk})


def step_all(strategy, bars, live=False):
    eng = Engine(strategy)
    eng.next_open = not live
    ctx = Ctx(bars, intraday=False)
    for i in range(1, len(bars)):
        eng.step(bars, ctx, i)
    return eng


def test_entry_fills_at_the_next_open_and_is_sized_from_it():
    bars = [bar(1, 90, 90, 90, 90), bar(2, 90, 101, 90, 100), bar(3, 125, 126, 124, 125), bar(4, 125, 126, 124, 125)]
    eng = step_all(daily(above(95)), bars)
    ev = eng.events[0]
    assert ev["t"] == bars[2]["t"] and ev["px"] == 125 and ev["qty"] == 10000 // 125
    # live keeps filling at the signal candle's close, the latest price
    live = step_all(daily(above(95)), bars, live=True).events[0]
    assert live["t"] == bars[1]["t"] and live["px"] == 100 and live["qty"] == 10000 // 100


def test_exit_rule_fills_at_the_next_open():
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 100, 100, 100, 100),
            bar(4, 100, 111, 100, 110), bar(5, 104, 106, 103, 105), bar(6, 105, 105, 105, 105)]
    eng = step_all(daily(above(99), exit=above(109)), bars)
    t = eng.trades[0]
    assert t["why"] == "Exit rule" and t["exit"] == 104 and t["exit_t"] == bars[4]["t"]


def test_stop_is_checked_on_the_fill_candle():
    # filled at 100 with a 2% stop: the fill candle's own low of 97 hits it
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 100, 101, 97, 99), bar(4, 99, 99, 99, 99)]
    eng = step_all(daily(above(99.5), sl=2), bars)
    t = eng.trades[0]
    assert t["why"] == "Stop loss" and t["entry"] == 100 and t["exit"] == pytest.approx(98)
    assert t["entry_t"] == t["exit_t"] == bars[2]["t"]
    # the backtest keeps one equity span per trade, the same-candle one included
    res = backtest(bars, daily(above(99.5), sl=2), 0)
    assert len(res["_paths"]) == len(res["trades"]) + (1 if res["open_trade"] else 0)


def test_a_signal_on_the_last_candle_does_not_fill():
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 100, 111, 100, 110)]
    eng = step_all(daily(above(105)), bars)
    assert eng.qty == 0 and not eng.events
    # an exit signal on the last candle leaves the trade open
    res = backtest(bars, daily(above(99), exit=above(105)), 0)
    assert not res["trades"] and res["open_trade"]["entry_t"] == bars[2]["t"]


def test_intraday_no_entry_on_the_next_day_or_at_square_off():
    # day 1 ends early at 14:00: its last candle's signal can't fill at the next morning's open
    d1 = day("2026-01-05", [100, 100, 101], start="13:30")
    d2 = day("2026-01-06", [101, 101, 101], start="09:15")
    s = S(entry=[cond({"t": "price"}, "gt", {"t": "num", "v": 100.5})], risk=RISK, session={"squareoff": "15:15"})
    eng, _ = run(s, d1 + d2)
    assert [e["t"][:16] for e in eng.events if e["why"] == "Entry rule"] == ["2026-01-06T09:30"]
    # the 15:00 candle closes at 15:15 (square-off), so a signal on the 14:45 candle doesn't fill
    late = day("2026-01-05", [100, 100, 101, 101], start="14:15")
    eng, _ = run(S(entry=[cond({"t": "price"}, "gt", {"t": "num", "v": 100.5})], risk=RISK, session={"squareoff": "15:15"}), late)
    assert not eng.events
