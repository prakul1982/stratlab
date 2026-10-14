import math

import numpy as np
import pandas as pd
import pytest

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


def test_bars_across_a_daylight_saving_change():
    from app.engine.core import Ctx
    bars = [{"t": "2026-03-06T00:00:00-05:00", "o": 1, "h": 1, "l": 1, "c": 1},
            {"t": "2026-03-09T00:00:00-04:00", "o": 1, "h": 1, "l": 1, "c": 1}]
    ctx = Ctx(bars, intraday=False)
    assert [d.day for d in ctx.df.t] == [6, 9]


def test_leverage_raises_the_cap_on_risk_sized_trades():
    # risk 1,000 at a 0.5% stop wants 1,818 shares (2,00,000); 50% of 1,00,000 caps it at 454, x5 leverage at 2,272
    risk = {"capital": 100000, "riskPct": 1, "maxAlloc": 50, "sl": 0.5, "brokerage": 0, "slippage": 0}
    bars = bars_from([100.0] * 10 + [110.0] * 5)
    ctx = Ctx(bars, intraday=False)
    qty = {}
    for lev in (1, 5):
        eng = Engine(strat(risk={**risk, "leverage": lev}))
        for i in range(1, len(bars)):
            eng.step(bars, ctx, i)
            if eng.events:
                break
        qty[lev] = eng.events[0]["qty"]         # the 0.5% stop is hit on the fill candle itself
    assert qty[1] == math.floor(50000 / 110)
    assert qty[5] == math.floor(1000 / (110 * 0.005))       # the stop's risk binds once the cap is 2,50,000


def test_cagr_and_sharpe_come_from_the_calendar():
    # a coin growing 0.1% a day for 365 days: one year, so CAGR is the return, not the return over 1.45 "years"
    closes = [100 * 1.001 ** k for k in range(366)]
    bars = bars_from(closes)
    s = strat(entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}], exit=[],
              risk={"capital": 100000, "riskPct": 100, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0})
    out = backtest(bars, s, start=0)
    st = out["stats"]
    # with 252 days in a year (the old table) it was about 28%
    assert st["cagr"] == pytest.approx(st["ret"], rel=0.01) and st["ret"] > 40


def test_no_yearly_return_under_a_year():
    # 30 days at +1.45% compounded to 19% a year; 5 days of 5-minute candles to hundreds of %
    from app.engine.core import span_years, stats
    month = stats([100, 101.45], [], 100, 252, span_years("2024-01-01T00:00:00+00:00", "2024-01-31T00:00:00+00:00"))
    assert month["cagr"] is None and month["ret"] == pytest.approx(1.45)
    assert stats([100.0] * 375 + [103.0], [], 100, 252 * 75, span_years("2024-01-01T09:15", "2024-01-05T15:30"))["cagr"] is None
    assert stats([100, 50], [], 100, 252, 2.0)["cagr"] == pytest.approx(-29.29, abs=0.01)


def test_stats_bars_a_year_follow_the_span():
    from app.engine.core import span_years, stats
    eq = [100 * 1.001 ** k for k in range(366)]
    st = stats(eq, [], 100, 252, span_years("2024-01-01T00:00:00+00:00", "2024-12-31T06:00:00+00:00"))
    assert st["cagr"] == pytest.approx(44.0, abs=0.2)
    old = stats(eq, [], 100, 252)            # no times: the timeframe's table, as before
    assert old["cagr"] < 30
    # Sharpe annualised with 365 returns a year, not 252
    assert st["sharpe"] / old["sharpe"] == pytest.approx(math.sqrt(365 / 252), rel=0.01)
    assert span_years("2024-01-01T09:15", "2024-01-01T15:30") is None and span_years(None, "x") is None


def test_walkforward_with_sub_day_tuning_stretches_does_not_overflow(monkeypatch):
    # a big return over a stretch of a few hours, raised to its yearly rate, is past a float: no yearly figure is made
    import math
    from app.engine import walkforward
    from app.models import Strategy
    from tests.test_notebooks import EMA
    s = Strategy(**{k: EMA[k] for k in ("entry", "exit", "risk")})
    closes = [100 * 1.003 ** i * (1 + 0.1 * math.sin(i / 8)) for i in range(1500)]
    monkeypatch.setattr(walkforward, "_years", lambda bars, a, b: 1 / 36525)
    with pytest.raises(OverflowError):
        walkforward._yearly(900, 1 / 36525)
    out = walkforward.run(bars_from(closes), s, 50)
    assert out["efficiency"] is None and "under half a year" in out["detail"]
