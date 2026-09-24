"""Short selling, trailing stops, time exits and the newer indicators."""
import math

import pandas as pd
import pytest

from app.engine.core import Ctx, Engine, backtest
from app.engine.indicators import compute
from app.models import Ref, Strategy
from tests.test_engine import bars_from

NO_COSTS = {"capital": 100000, "riskPct": 1, "sl": 5, "tgt": 0, "brokerage": 0, "slippage": 0}
ALWAYS = [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}]
NEVER = [{"l": {"t": "price"}, "op": "lt", "r": {"t": "num", "v": 0}}]


def s(**kw):
    base = {"entry": ALWAYS, "exit": [], "risk": dict(NO_COSTS)}
    base.update(kw)
    return Strategy(**base)


def bar(t, o, h, l, c):
    return {"t": f"2024-01-{t:02d}T00:00:00+05:30", "o": o, "h": h, "l": l, "c": c, "v": 1000.0}


def run(strategy, bars):
    ctx = Ctx(bars, intraday=False)
    eng = Engine(strategy)
    for i in range(1, len(bars)):
        eng.step(bars, ctx, i)
    return eng


def test_short_profits_when_price_falls():
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 101, 99, 100), bar(3, 95, 96, 90, 90), bar(4, 90, 91, 89, 90)]
    st = s(side="short", exit=[{"l": {"t": "price"}, "op": "lt", "r": {"t": "num", "v": 91}}])
    eng = run(st, bars)
    t = eng.trades[0]
    assert t["side"] == "short" and t["entry"] == 100 and t["exit"] == 90
    assert t["pnl"] == pytest.approx(t["qty"] * 10) and t["ret"] == pytest.approx(10)
    assert eng.equity(90) == pytest.approx(100000 + t["pnl"])   # the entry rule has already re-opened a short
    assert eng.events[0]["side"] == "sell" and eng.events[0]["why"] == "Short entry" and eng.events[1]["side"] == "buy"


def test_short_stop_is_above_entry_and_equity_marks_to_market():
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 101, 104, 100, 103), bar(4, 103, 108, 103, 107)]
    eng = run(s(side="short", exit=NEVER), bars[:3])
    assert eng.sl == pytest.approx(105) and eng.qty > 0
    assert eng.equity(103) == pytest.approx(100000 - eng.qty * 3)
    eng2 = run(s(side="short", exit=NEVER), bars)
    t = eng2.trades[0]
    assert t["why"] == "Stop loss" and t["exit"] == pytest.approx(105) and t["pnl"] < 0


def test_short_target_below_entry():
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 99, 99, 93, 94)]
    eng = run(s(side="short", risk={**NO_COSTS, "tgt": 5}), bars)
    assert eng.trades[0]["why"] == "Target" and eng.trades[0]["exit"] == pytest.approx(95)


def test_trailing_stop_follows_the_high_and_locks_in_gains():
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 101, 110, 101, 109),
            bar(4, 109, 120, 108, 119), bar(5, 118, 118, 107, 108)]
    eng = run(s(exit=NEVER, risk={**NO_COSTS, "sl": 0, "trail": 5}), bars)
    t = eng.trades[0]
    assert t["why"] == "Trailing stop" and t["exit"] == pytest.approx(120 * 0.95) and t["pnl"] > 0


def test_short_trailing_stop_follows_the_low():
    # falls to 80, bounces: the stop trails 5% above the low and closes the short at a profit
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 99, 99, 90, 91),
            bar(4, 91, 91, 80, 81), bar(5, 82, 88, 82, 87)]
    t = run(s(side="short", exit=NEVER, risk={**NO_COSTS, "sl": 0, "trail": 5}), bars).trades[0]
    assert t["why"] == "Trailing stop" and t["exit"] == pytest.approx(84) and t["pnl"] > 0
    # rises straight away: the untouched first stop is a plain loss, not a "trailing stop"
    up = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 101, 107, 100, 106)]
    t = run(s(side="short", exit=NEVER, risk={**NO_COSTS, "sl": 0, "trail": 5}), up).trades[0]
    assert t["why"] == "Stop loss" and t["exit"] == pytest.approx(105) and t["pnl"] < 0


def test_trailing_stop_never_moves_down():
    bars = [bar(1, 100, 100, 100, 100), bar(2, 100, 100, 100, 100), bar(3, 101, 110, 101, 109), bar(4, 109, 109, 107, 108)]
    eng = run(s(exit=NEVER, risk={**NO_COSTS, "sl": 3, "trail": 3}), bars)
    assert eng.qty > 0 and eng.sl == pytest.approx(110 * 0.97)


def test_time_exit_closes_after_n_candles():
    bars = [bar(i, 100, 101, 99, 100) for i in range(1, 9)]
    eng = run(s(exit=NEVER, risk={**NO_COSTS, "maxBars": 3}), bars)
    assert eng.trades[0]["why"] == "Time exit"
    assert eng.trades[0]["exit_t"] == bars[4]["t"]      # entered on bar 1, held bars 2, 3, 4


def test_old_live_state_still_loads():
    old = {"cash": 90000, "qty": 10, "entry": 100.0, "sl": 95.0, "tg": None, "entry_t": "x", "entry_cost": 0,
           "cost_items": {}, "trades": [], "events": []}
    eng = Engine(s(), state=old)
    assert eng.init_sl == 95.0 and eng.best == 100.0 and eng.held == 0


def test_short_backtest_reports_short_trades():
    closes = [200 - i * 0.5 + 6 * math.sin(i / 4) for i in range(300)]
    st = Strategy(side="short", entry=[{"l": {"t": "price"}, "op": "xb", "r": {"t": "sma", "p": 10}}],
                  exit=[{"l": {"t": "price"}, "op": "xa", "r": {"t": "sma", "p": 10}}], risk=NO_COSTS)
    out = backtest(bars_from(closes), st, 50)
    assert out["trades"] and all(t.get("side") == "short" for t in out["trades"] if t.get("exit_t"))
    assert out["stats"]["ret"] > 0     # a falling market pays a short trend follower


def frame(n=120):
    b = bars_from([100 + 10 * math.sin(i / 7) + i * 0.2 for i in range(n)])
    df = pd.DataFrame(b)
    df["t"] = pd.to_datetime(df["t"])
    return df


def test_new_indicators_are_in_range():
    df = frame()
    adx = compute(Ref(t="adx", p=14), df, False).dropna()
    st = compute(Ref(t="stoch_k", p=14), df, False).dropna()
    atr = compute(Ref(t="atr_pct", p=14), df, False).dropna()
    assert len(adx) > 50 and ((adx >= 0) & (adx <= 100)).all()
    assert ((st >= 0) & (st <= 100)).all()
    assert ((atr > 0) & (atr < 10)).all()


def test_donchian_uses_previous_candles_so_breakouts_can_happen():
    df = frame()
    up = compute(Ref(t="dc_upper", p=20), df, False)
    assert up.iloc[25] == df.h.iloc[5:25].max()
    ctx = Ctx(bars_from([100.0] * 30 + [110.0]), intraday=False)
    from app.engine.core import eval_cond
    from app.models import Cond
    c = Cond(l=Ref(t="price"), op="xa", r=Ref(t="dc_upper", p=20))
    assert eval_cond(ctx, c, 30)


def test_volume_is_blank_for_indices():
    df = frame()
    df["v"] = 0.0
    assert compute(Ref(t="volume"), df, False).isna().all()
    df["v"] = 500.0
    assert compute(Ref(t="vol_sma", p=5), df, False).iloc[-1] == 500
