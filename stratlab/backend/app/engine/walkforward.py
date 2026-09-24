"""Walk-forward test: the most honest way to check an idea whose numbers were tuned.

The period is cut into blocks. For each step we tune the indicator lengths on a stretch of the
past (the "training" window: every nearby setting is tried and the best one kept), then trade
the chosen settings on the block right after it, which the tuning never saw. Then the whole
thing slides forward and repeats. Stitching the unseen blocks together gives the return you
could have had if you'd re-tuned as you went, without ever peeking at the future.

It answers: "if I keep optimising this idea, does the optimised version still make money on
data it hasn't seen?" A strategy whose best settings only ever work in hindsight fails here.
"""
from datetime import datetime

from .core import Ctx, simulate
from .indicators import ref_name
from .verdict import _nudged, _param_keys, _ret, _with
from ..models import Ref

BLOCKS = 8          # the tradeable period is cut into this many equal blocks
TRAIN_BLOCKS = 3    # each step tunes on 3 blocks and tests on the next one: 5 unseen steps in all
MIN_BLOCK = 20      # candles per block; fewer and a step can't show anything


def _date(bars, i: int) -> str:
    return str(bars[min(i, len(bars) - 1)]["t"])[:10]


def _years(bars, a: int, b: int) -> float:
    try:
        t0 = datetime.fromisoformat(str(bars[a]["t"])[:19])
        t1 = datetime.fromisoformat(str(bars[min(b, len(bars) - 1)]["t"])[:19])
        return max((t1 - t0).days / 365.25, 1 / 365.25)
    except (ValueError, IndexError):
        return 1.0


def _yearly(ret_pct: float, years: float) -> float:
    g = 1 + ret_pct / 100
    return (g ** (1 / years) - 1) * 100 if g > 0 else -100.0


def run(bars: list[dict], strategy, start: int, lot: float = 1, kind: str = "flat") -> dict:
    keys = _param_keys(strategy)
    if not keys:
        return {"status": "skip", "headline": "Nothing to tune.",
                "detail": "Walk-forward re-tunes your indicator lengths as it goes. These rules have none (they use only price and fixed numbers), so there's nothing to test.",
                "windows": []}
    span = len(bars) - 1 - start
    blocks = BLOCKS
    while blocks > TRAIN_BLOCKS + 1 and span // blocks < MIN_BLOCK:
        blocks -= 1
    size = span // blocks
    if blocks < TRAIN_BLOCKS + 2 or size < MIN_BLOCK:
        return {"status": "skip", "headline": "Not enough history.",
                "detail": "Walk-forward needs at least about 100 candles in the test period. Pick a longer period and run the experiment again.",
                "windows": []}

    ctx = Ctx(bars, intraday=strategy.tf != "1d")
    cap = strategy.risk.capital
    grid = [{keys[0]: a} for a in _nudged(keys[0][1])]
    if len(keys) > 1:
        grid = [{**g, keys[1]: b} for g in grid for b in _nudged(keys[1][1])]
    label = {k: ref_name(Ref(t=k[0], p=k[1])).rsplit(" ", 1)[0] for k in keys}

    windows, wf_curve, fixed_curve, times = [], [], [], []
    wf_growth = fixed_growth = 1.0
    is_yearly = []
    for w in range(blocks - TRAIN_BLOCKS):
        tr_a = start + w * size
        te_a = tr_a + TRAIN_BLOCKS * size
        te_b = te_a + size if w < blocks - TRAIN_BLOCKS - 1 else len(bars) - 1
        # tune: every nearby setting on the training window, keep the best (ties go to the setting closest to yours)
        best = None
        for subs in grid:
            _, eq = simulate(bars, _with(strategy, subs), tr_a, te_a + 1, lot, kind, ctx)
            r = _ret(eq, cap)
            dist = sum(abs(v - k[1]) for k, v in subs.items())
            if best is None or (r, -dist) > (best[0], -best[2]):
                best = (r, subs, dist)
        train_ret, chosen, _ = best
        # trade the chosen settings, and your own, on the block the tuning never saw
        eng, eq = simulate(bars, _with(strategy, chosen), te_a, te_b + 1, lot, kind, ctx)
        _, eq_fixed = simulate(bars, strategy, te_a, te_b + 1, lot, kind, ctx)
        test_ret, fixed_ret = _ret(eq, cap), _ret(eq_fixed, cap)
        for k, (a, b) in enumerate(zip(eq, eq_fixed)):
            if k == 0 and wf_curve:
                continue          # the first point of a block is the last point of the one before
            wf_curve.append(round((wf_growth * a / cap - 1) * 100, 3))
            fixed_curve.append(round((fixed_growth * b / cap - 1) * 100, 3))
            times.append(bars[te_a + k]["t"])
        wf_growth *= 1 + test_ret / 100
        fixed_growth *= 1 + fixed_ret / 100
        is_yearly.append(_yearly(train_ret, _years(bars, tr_a, te_a)))
        windows.append({
            "train_from": _date(bars, tr_a), "train_to": _date(bars, te_a),
            "test_from": _date(bars, te_a), "test_to": _date(bars, te_b),
            "chosen": [{"label": label[k], "value": v, "yours": k[1]} for k, v in chosen.items()],
            "train_ret": round(train_ret, 2), "test_ret": round(test_ret, 2), "fixed_ret": round(fixed_ret, 2),
            "trades": len(eng.trades) + (1 if eng.qty else 0),
        })

    oos_a = start + TRAIN_BLOCKS * size
    wf_ret, fixed_ret = (wf_growth - 1) * 100, (fixed_growth - 1) * 100
    bh_ret = (bars[-1]["c"] / bars[oos_a]["c"] - 1) * 100
    oos_years = _years(bars, oos_a, len(bars) - 1)
    oos_yearly = _yearly(wf_ret, oos_years)
    avg_is = sum(is_yearly) / len(is_yearly)
    efficiency = round(oos_yearly / avg_is, 2) if avg_is > 0 else None
    profitable = sum(1 for w in windows if w["test_ret"] > 0)
    settings_used = len({tuple(c["value"] for c in w["chosen"]) for w in windows})
    n = len(windows)
    trades = sum(w["trades"] for w in windows)

    if wf_ret <= 0:
        status = "fail"
        headline = "Re-tuning doesn't rescue it."
        detail = (f"Tuned on the past and traded on the next stretch, it lost {abs(wf_ret):.1f}% over the unseen periods. "
                  "The best settings in hindsight didn't carry forward, which is what curve-fitting looks like.")
    elif profitable / n >= 0.6 and (efficiency is None or efficiency >= 0.5):
        status = "pass"
        headline = "It holds up when re-tuned as you go."
        detail = (f"Tuned only on past data each time, it made money in {profitable} of {n} unseen periods "
                  f"({wf_ret:+.1f}% in all). The edge survives without hindsight.")
    else:
        status = "warn"
        headline = "It survives, but only just."
        detail = (f"It made {wf_ret:+.1f}% over the unseen periods, but only {profitable} of {n} of them were profitable"
                  + (f", and it kept about {max(efficiency, 0) * 100:.0f}% of the return it showed when tuned" if efficiency is not None else "")
                  + ". Treat the backtest return as optimistic.")

    if status == "pass" and trades < 10:
        status = "warn"
        headline = "Promising, but thin."
        detail += f" Only {trades} trades happened in the unseen periods, though, so this could still be chance."
    # thin the curve for storage
    step = max(1, len(times) // 240)
    idx = list(range(0, len(times), step))
    if idx[-1] != len(times) - 1:
        idx.append(len(times) - 1)
    return {
        "status": status, "headline": headline, "detail": detail,
        "windows": windows, "wf_ret": round(wf_ret, 2), "fixed_ret": round(fixed_ret, 2), "buy_hold_ret": round(bh_ret, 2),
        "profitable": profitable, "total": n, "trades": trades, "efficiency": efficiency, "settings_used": settings_used,
        "tuned": [f"{label[k]} {k[1]}" for k in keys], "grid_size": len(grid),
        "from": _date(bars, oos_a), "to": _date(bars, len(bars) - 1),
        "series": {"t": [times[i] for i in idx], "wf": [wf_curve[i] for i in idx], "fixed": [fixed_curve[i] for i in idx]},
    }
