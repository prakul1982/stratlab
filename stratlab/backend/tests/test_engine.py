import math

import numpy as np
import pandas as pd

from app.engine.core import Ctx, Engine, backtest, eval_cond
from app.engine.indicators import compute, rsi
from app.models import Cond, Ref, Strategy


def bars_from(closes, start="2024-01-01"):
    days = pd.date_range(start, periods=len(closes), freq="D", tz="Asia/Kolkata")
    return [{"t": d.isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000.0}
            for d, c in zip(days, closes)]


def strat(**kw):
    base = {"entry": [{"l": {"t": "price"}, "op": "xa", "r": {"t": "sma", "p": 5}}],
            "exit": [{"l": {"t": "price"}, "op": "xb", "r": {"t": "sma", "p": 5}}],
            "risk": {"capital": 100000, "riskPct": 1, "sl": 5, "tgt": 0, "brokerage": 0, "slippage": 0}}
    base.update(kw)
    return Strategy(**base)


def test_sma_and_ema_match_pandas():
    df = pd.DataFrame(bars_from([float(x) for x in range(1, 41)]))
    df["t"] = pd.to_datetime(df["t"])
    sma = compute(Ref(t="sma", p=10), df, False)
    assert sma.iloc[9] == np.mean(range(1, 11))
    assert math.isnan(sma.iloc[8])
    ema = compute(Ref(t="ema", p=10), df, False)
    assert math.isnan(ema.iloc[8]) and not math.isnan(ema.iloc[9])


def test_rsi_bounds():
    closes = pd.Series([100 + math.sin(i / 3) * 5 for i in range(100)])
    r = rsi(closes, 14).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_cross_above_only_fires_on_crossing_candle():
    ctx = Ctx(bars_from([10, 10, 10, 12, 13, 14]), intraday=False)
    c = Cond(l=Ref(t="price"), op="xa", r=Ref(t="num", v=11))
    assert [eval_cond(ctx, c, i) for i in range(6)] == [False, False, False, True, False, False]


def test_stop_loss_exits_at_stop_price():
    s = strat(exit=[])
    bars = bars_from([100.0] * 10)
    ctx = Ctx(bars, intraday=False)
    eng = Engine(s)
    eng.qty, eng.entry, eng.sl, eng.tg, eng.entry_t = 10, 100.0, 95.0, math.inf, bars[0]["t"]
    bars[1] = {**bars[1], "o": 97.0, "h": 97.0, "l": 90.0, "c": 91.0}
    eng.step(bars, ctx, 1)
    assert eng.qty == 0
    assert eng.trades[-1]["why"] == "Stop loss"
    assert eng.trades[-1]["exit"] == 95.0


def test_position_size_respects_risk_and_capital():
    s = strat(risk={"capital": 100000, "riskPct": 1, "maxAlloc": 100, "sl": 2, "brokerage": 0, "slippage": 0})
    bars = bars_from([100.0] * 10 + [110.0] * 5)
    ctx = Ctx(bars, intraday=False)
    eng = Engine(s)
    for i in range(1, len(bars)):
        eng.step(bars, ctx, i)
        if eng.qty:
            break
    # risk 1,000 / (110 * 2%) = 454 shares, well under the capital cap
    assert eng.qty == math.floor(1000 / (110 * 0.02))
    assert eng.cash >= 0


def test_fno_quantity_rounds_down_to_lots():
    s = strat(risk={"capital": 100000, "riskPct": 1, "sl": 2, "brokerage": 0, "slippage": 0})
    bars = bars_from([100.0] * 10 + [110.0] * 5)
    ctx = Ctx(bars, intraday=False)
    eng = Engine(s, lot=75)
    for i in range(1, len(bars)):
        eng.step(bars, ctx, i)
        if eng.qty:
            break
    assert eng.qty % 75 == 0 and eng.qty > 0


def test_backtest_output_shapes_line_up():
    closes = [100 + 10 * math.sin(i / 8) for i in range(300)]
    bars = bars_from(closes)
    out = backtest(bars, strat(), start=50)
    n = len(bars) - 50
    assert len(out["bars"]) == len(out["equity"]) == len(out["buy_hold"]) == len(out["drawdown"]) == n
    assert out["stats"]["n"] == len(out["trades"]) > 0
    assert out["diagnostics"]["candles"] == n - 1


def test_engine_state_round_trip():
    eng = Engine(strat())
    eng.cash, eng.qty, eng.entry, eng.sl, eng.entry_t = 5000.0, 3, 100.0, 95.0, "t"
    again = Engine(strat(), state=eng.dump())
    assert (again.cash, again.qty, again.entry, again.sl, again.tg) == (5000.0, 3, 100.0, 95.0, math.inf)
