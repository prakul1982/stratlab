"""Intraday rules: day values, candle shape, higher timeframes, both directions, sessions, stops, scoring, sizing."""
import numpy as np
import pytest

from app.engine import costs as C
from app.engine.core import Ctx, Engine, bar_clock
from app.models import Ref, Strategy

RISK = {"capital": 100000, "riskPct": 1, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0}


def day(date: str, prices: list[float], start="09:15", step=15):
    """15-minute candles for one session; each price is a close, the open is the previous close."""
    h, m = map(int, start.split(":"))
    out, prev = [], prices[0]
    for k, c in enumerate(prices):
        mins = h * 60 + m + k * step
        o = prev
        out.append({"t": f"{date}T{mins // 60:02d}:{mins % 60:02d}:00+05:30", "o": o, "h": max(o, c) + 0.1, "l": min(o, c) - 0.1, "c": c, "v": 1000.0})
        prev = c
    return out


def run(strategy, bars, kind="flat"):
    ctx = Ctx(bars, intraday=strategy.tf != "1d")
    eng = Engine(strategy, 1, cost_kind=kind)
    for i in range(1, len(bars)):
        eng.step(bars, ctx, i)
    return eng, ctx


def S(**kw):
    base = {"tf": "15m", "entry": [], "exit": [], "risk": dict(RISK)}
    base.update(kw)
    return Strategy(**base)


def cond(l, op, r, **kw):
    return {"l": l, "op": op, "r": r, **kw}


def test_bar_clock_is_candle_close_time():
    assert bar_clock("2026-01-05T09:15:00+05:30", 15) == ("2026-01-05", 9 * 60 + 30)


def test_day_values():
    bars = day("2026-01-05", [100, 101, 102]) + day("2026-01-06", [103, 104, 99])
    ctx = Ctx(bars, intraday=True)
    assert np.isnan(ctx.series(Ref(t="prev_close"))[0])
    assert list(ctx.series(Ref(t="prev_close"))[3:]) == [102, 102, 102]
    assert ctx.series(Ref(t="day_chg"))[4] == pytest.approx((104 / 102 - 1) * 100)
    assert ctx.series(Ref(t="day_open"))[5] == 103                       # the day's first open
    assert ctx.series(Ref(t="day_high"))[5] == pytest.approx(104.1)       # highest so far that day
    assert ctx.series(Ref(t="day_low"))[3] == pytest.approx(102.9)


def test_candle_shape_ago_and_multiplier():
    bars = [{"t": "2026-01-05T09:15:00+05:30", "o": 100, "h": 106, "l": 95, "c": 102, "v": 1},
            {"t": "2026-01-05T09:30:00+05:30", "o": 102, "h": 103, "l": 101, "c": 101, "v": 1}]
    ctx = Ctx(bars, intraday=True)
    assert ctx.series(Ref(t="body"))[0] == 2 and ctx.series(Ref(t="upper_wick"))[0] == 4
    assert ctx.series(Ref(t="lower_wick"))[0] == 5 and ctx.series(Ref(t="range"))[0] == 11
    assert ctx.series(Ref(t="high", ago=1))[1] == 106
    assert ctx.series(Ref(t="body", k=1.5))[0] == 3


def test_higher_timeframe_uses_only_completed_candles():
    # four 15m candles per hour; the 1-hour close is only known once the hour's last candle closes
    prices = list(range(100, 112))                                   # 09:15 .. 12:00 closes, 3 full hours
    bars = day("2026-01-05", prices)
    ctx = Ctx(bars, intraday=True)
    hourly = ctx.series(Ref(t="price", tf="1h"))
    assert np.isnan(hourly[0]) and np.isnan(hourly[2])               # first hour not finished yet
    assert hourly[3] == 103                                           # 10:00-10:15 candle closes the first hour
    assert hourly[4] == 103 and hourly[6] == 103 and hourly[7] == 107


def test_both_directions_and_square_off():
    # day 1 rallies 3% (go long), day 2 falls 3% (go short); square-off at 10:30 closes each
    d0 = day("2026-01-02", [100, 100])                                # no "day change" without a previous day
    d1 = day("2026-01-05", [100, 100.5, 103, 103.5, 104, 104.2, 104.4])
    d2 = day("2026-01-06", [104, 103, 100.5, 100, 99.5, 99, 98.8])
    s = S(side="both", entry=[cond({"t": "day_chg"}, "gt", {"t": "num", "v": 2})],
          shortEntry=[cond({"t": "day_chg"}, "lt", {"t": "num", "v": -2})],
          session={"start": "09:30", "end": "10:15", "squareoff": "10:30", "maxTradesDay": 1})
    eng, _ = run(s, d0 + d1 + d2)
    sides = [(t["side"], t["why"]) for t in eng.trades]
    assert sides == [("long", "Square-off"), ("short", "Square-off")]
    assert eng.trades[0]["exit_t"].endswith("10:15:00+05:30")        # the candle closing at 10:30
    assert eng.trades[1]["pnl"] > 0


def test_entry_window_trades_per_day_and_cooldown():
    prices = [100] + [101] * 20                                      # entry rule true on every candle
    s = S(entry=[cond({"t": "price"}, "gt", {"t": "num", "v": 100.5})], risk={**RISK, "maxBars": 1},
          session={"start": "10:00", "end": "13:00", "maxTradesDay": 3, "cooldown": 2})
    eng, _ = run(s, day("2026-01-05", prices))
    entries = [e["t"][11:16] for e in eng.events if e["why"] == "Entry rule"]
    # the 09:45 candle closes at 10:00; exit on the next candle, skip two, enter again (3 a day at most)
    assert entries == ["09:45", "10:45", "11:45"]


def test_daily_loss_cap_stops_trading_for_the_day():
    prices = [100, 101, 97, 101, 97, 101]
    s = S(entry=[cond({"t": "price"}, "gt", {"t": "num", "v": 100.5})], risk={**RISK, "sizing": "capital", "perTrade": 50000},
          session={"dailyLossPct": 1})
    eng, _ = run(s, day("2026-01-05", prices))
    assert len(eng.trades) == 1 and eng.trades[0]["why"] == "Daily loss cap" and eng.halted


def test_points_swing_stops_and_r_targets():
    bars = day("2026-01-05", [100, 99, 98, 101, 102, 110])
    s = S(entry=[cond({"t": "price"}, "xa", {"t": "num", "v": 100})], risk={**RISK, "sl": 3, "stopType": "swing", "tgt": 2, "tgtType": "r"})
    eng, _ = run(s, bars)
    # swing low of the last 3 candles is 97.9; entry 101 -> 3.1 points risk -> 2R target at 107.2
    assert eng.trades[0]["why"] == "Target" and eng.trades[0]["exit"] == pytest.approx(101 + 2 * (101 - 97.9))
    s2 = S(entry=[cond({"t": "price"}, "xa", {"t": "num", "v": 100})], risk={**RISK, "sl": 5, "stopType": "points"})
    eng2, _ = run(s2, day("2026-01-05", [100, 99, 101, 95.5, 94]))
    assert eng2.trades[0]["why"] == "Stop loss" and eng2.trades[0]["exit"] == pytest.approx(96)


def test_score_mode():
    bars = day("2026-01-05", [100, 101, 102, 103])
    rules = [cond({"t": "price"}, "gt", {"t": "num", "v": 100}, w=3), cond({"t": "price"}, "gt", {"t": "num", "v": 1000}, w=5),
             cond({"t": "rsi", "p": 2}, "gt", {"t": "num", "v": 50}, w=2)]
    assert run(S(entry=rules, entryJoin="score", minScore=5), bars)[0].events               # 3 + 2 is enough
    assert not run(S(entry=rules, entryJoin="score", minScore=6), bars)[0].events           # 3 + 2 isn't


def test_capital_sizing_with_leverage_and_intraday_costs():
    bars = day("2026-01-05", [100, 101, 102])
    s = S(entry=[cond({"t": "price"}, "gt", {"t": "num", "v": 100.5})],
          risk={**RISK, "sizing": "capital", "perTrade": 20000, "leverage": 5, "brokerage": 20}, session={"squareoff": "15:00"})
    eng, _ = run(s, bars, kind="in_eq")
    assert eng.kind == "in_eq_mis"
    assert 980 <= eng.qty <= 990                                      # ~1,00,000 notional at 101, less costs
    buy = C.order_costs("in_eq_mis", "buy", 100, 100, 0)
    assert buy["stt"] == 0 and C.order_costs("in_eq_mis", "sell", 100, 100, 0)["stt"] == pytest.approx(10000 * 0.00025)


def test_old_strategies_behave_as_before():
    s = Strategy(entry=[cond({"t": "price"}, "gt", {"t": "num", "v": 0})], risk={**RISK, "sl": 5})
    daily = [{"t": f"2024-01-{d:02d}T00:00:00+05:30", "o": 100, "h": 101, "l": 99, "c": 100, "v": 1} for d in range(1, 6)]
    eng, _ = run(s, daily)
    assert eng.qty > 0 and not eng.intraday and eng.sl == pytest.approx(95)
