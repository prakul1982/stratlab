"""Is the edge real? Four checks on a backtest, and a plain-English verdict.

1. Unseen data: split the test period 70/30 and trade each part with fresh capital.
   A real edge keeps making money on the part it wasn't tuned on.
2. Nearby settings: nudge the indicator lengths up and down. If only the exact
   settings you picked make money, the result is probably a lucky fit.
3. Bad-luck drawdown: reshuffle the order of the trades 1,000 times. The worst
   falls show how deep a drawdown the same trades could have produced.
4. Enough trades: under 15 trades, luck dominates; 30+ is a fair sample.
All returns are after costs."""
import copy

import numpy as np

from ..models import Ref
from .core import Ctx, simulate
from .indicators import params, ref_name

SPLIT = 0.7
SHUFFLES = 1000
PERIOD_TYPES = {"sma", "ema", "rsi", "vwap", "macd", "macd_signal", "macd_hist",
                "bb_upper", "bb_mid", "bb_lower", "supertrend",
                "adx", "stoch_k", "atr_pct", "dc_upper", "dc_lower", "vol_sma"}
NUDGES = (0.6, 0.8, 1.0, 1.2, 1.4)

HEADLINES = {
    "edge": "Likely a real edge.",
    "mixed": "Mixed evidence.",
    "luck": "Probably luck.",
    "not_enough": "Not enough evidence.",
    "no_edge": "No edge here.",
}


def _ret(equity: list[float], capital: float) -> float:
    return (equity[-1] / capital - 1) * 100 if equity else 0.0


def _years(bars: list[dict], a: int, b: int) -> float:
    try:
        from datetime import datetime
        t0, t1 = datetime.fromisoformat(bars[a]["t"]), datetime.fromisoformat(bars[b]["t"])
        return max((t1 - t0).days / 365.25, 1 / 365.25)
    except (IndexError, ValueError):
        return 0.0


def _year_label(bars: list[dict], i: int) -> str:
    return str(bars[i]["t"])[:4]


def check_unseen(bars, strategy, start, lot, kind, ctx) -> dict:
    split = start + int((len(bars) - 1 - start) * SPLIT)
    cap = strategy.risk.capital
    e1, eq1 = simulate(bars, strategy, start, split + 1, lot, kind, ctx)
    e2, eq2 = simulate(bars, strategy, split, None, lot, kind, ctx)
    r1, r2 = _ret(eq1, cap), _ret(eq2, cap)
    data = {"built_ret": r1, "unseen_ret": r2, "built_trades": len(e1.trades), "unseen_trades": len(e2.trades),
            "built_from": _year_label(bars, start), "built_to": _year_label(bars, split),
            "unseen_from": _year_label(bars, split), "unseen_to": _year_label(bars, len(bars) - 1),
            "split_index": split - start}
    if len(e2.trades) == 0 and e2.qty == 0:
        status, detail = "warn", "No trades happened in the unseen part, so it couldn't be tested there."
    elif r2 > 0:
        status, detail = "pass", "It kept making money on data it wasn't tuned on."
    else:
        status, detail = "fail", "It lost money on the part of the period it hadn't seen."
    return {"id": "unseen", "title": "Unseen data", "status": status, "detail": detail, "data": data}


def _param_keys(strategy) -> list[tuple[str, int]]:
    keys = []
    for c in strategy.all_conds():
        for ref in (c.l, c.r):
            if ref.t in PERIOD_TYPES:
                key = (ref.t, params(ref)[0])
                if key not in keys:
                    keys.append(key)
    return keys[:2]


def _nudged(p: int) -> list[int]:
    vals = []
    for f in NUDGES:
        v = max(2, int(round(p * f)))
        if v not in vals:
            vals.append(v)
    return vals


def _with(strategy, subs: dict[tuple[str, int], int]):
    s = copy.deepcopy(strategy)
    for c in s.all_conds():
        for ref in (c.l, c.r):
            key = (ref.t, params(ref)[0]) if ref.t in PERIOD_TYPES else None
            if key in subs:
                ref.p = subs[key]
    return s


def check_nearby(bars, strategy, start, lot, kind, ctx) -> dict:
    keys = _param_keys(strategy)
    if not keys:
        return {"id": "nearby", "title": "Nearby settings", "status": "skip",
                "detail": "Your rules have no indicator lengths to nudge, so this check was skipped.", "data": None}
    cap = strategy.risk.capital
    cols_key = keys[0]
    rows_key = keys[1] if len(keys) > 1 else None
    cols = _nudged(cols_key[1])
    rows = _nudged(rows_key[1]) if rows_key else [None]
    grid, profitable, total, yours = [], 0, 0, [0, 0]
    for ri, rv in enumerate(rows):
        row = []
        for ci, cv in enumerate(cols):
            subs = {cols_key: cv}
            if rows_key:
                subs[rows_key] = rv
            _, eq = simulate(bars, _with(strategy, subs), start, None, lot, kind, ctx)
            r = _ret(eq, cap)
            row.append(round(r, 2))
            profitable += r > 0
            total += 1
            if cv == cols_key[1] and (rv is None or rv == rows_key[1]):
                yours = [ri, ci]
        grid.append(row)
    share = profitable / total
    status = "pass" if share >= 0.6 else "warn" if share >= 0.4 else "fail"
    detail = {"pass": "Most settings near yours make money too, so the idea doesn't hinge on one lucky number.",
              "warn": "About half the settings near yours make money. The result depends a lot on the exact numbers.",
              "fail": "Most settings near yours lose money. Your exact numbers look like a lucky fit."}[status]

    def label(key):
        return ref_name(Ref(t=key[0], p=key[1])).rsplit(" ", 1)[0]

    data = {"grid": grid, "cols": cols, "rows": rows if rows_key else [], "col_label": label(cols_key),
            "row_label": label(rows_key) if rows_key else None, "yours": yours,
            "profitable": profitable, "total": total}
    return {"id": "nearby", "title": "Nearby settings", "status": status, "detail": detail, "data": data}


def _trade_dd(pnls, capital: float) -> float:
    path = capital + np.cumsum(pnls)
    path = np.concatenate([[capital], path])
    peak = np.maximum.accumulate(path)
    return float(np.max((peak - path) / peak) * 100)


def check_shuffle(trades: list[dict], capital: float) -> dict:
    pnls = np.array([t["pnl"] for t in trades], dtype=float)
    if len(pnls) < 5:
        return {"id": "shuffle", "title": "Bad-luck drawdown", "status": "skip",
                "detail": "Too few trades to reshuffle.", "data": None}
    rng = np.random.default_rng(42)  # same answer every time for the same trades
    dds = np.array([_trade_dd(rng.permutation(pnls), capital) for _ in range(SHUFFLES)])
    yours, p95, worst = _trade_dd(pnls, capital), float(np.percentile(dds, 95)), float(dds.max())
    if p95 >= 35:
        status = "fail"
        detail = f"With worse luck the same trades could have fallen {p95:.0f}%. That's hard to sit through."
    elif p95 > max(1.5 * yours, 5):
        status = "warn"
        detail = f"Your backtest fell {yours:.0f}% at worst, but with worse luck expect up to {p95:.0f}%."
    else:
        status = "pass"
        detail = f"Even with worse luck, falls stay around {p95:.0f}%, close to your backtest's {yours:.0f}%."
    return {"id": "shuffle", "title": "Bad-luck drawdown", "status": status, "detail": detail,
            "data": {"yours": yours, "p95": p95, "worst": worst, "runs": SHUFFLES}}


def check_sample(n: int) -> dict:
    if n >= 30:
        status, detail = "pass", "Enough trades to judge."
    elif n >= 15:
        status, detail = "warn", "A small sample: a few lucky trades could decide the result."
    else:
        status, detail = "fail", "Too few trades to tell skill from luck."
    return {"id": "sample", "title": "Enough trades", "status": status, "detail": detail, "data": {"trades": n}}


def suggestions(verdict: str, strategy, days: int, max_days: int) -> list[dict]:
    out = []
    crosses = any(c.op in ("xa", "xb") for c in strategy.entry)
    has_trend = any(r.t in ("sma", "ema") and params(r)[0] >= 150 for c in strategy.entry for r in (c.l, c.r))
    if verdict in ("not_enough", "mixed") and days < max_days:
        out.append({"action": "longer_period", "text": "Test a longer period for more trades"})
    if verdict == "not_enough" and crosses:
        out.append({"action": "loosen_entry", "text": "Buy whenever the condition holds, not only on the cross"})
    if verdict in ("luck", "mixed", "no_edge") and not has_trend:
        out.append({"action": "trend_filter", "text": "Only buy above the 200-period average"})
    if verdict in ("luck", "mixed", "no_edge", "edge"):
        out.append({"action": "other_instrument", "text": "Test the same rules on another instrument"})
    if verdict == "edge":
        out.insert(0, {"action": "paper_trade", "text": "Paper trade it on live prices"})
    out.append({"action": "note", "text": "Write a lab note about what you learned"})
    return out[:4]


def evaluate(bars: list[dict], strategy, start: int, base: dict, lot: float = 1, cost_kind: str = "flat",
             days: int = 365, max_days: int = 3650) -> dict:
    """Run the four checks on a finished backtest (`base`, from core.backtest)."""
    ctx = Ctx(bars, intraday=strategy.tf != "1d")
    trades = base["trades"]
    checks = [
        check_unseen(bars, strategy, start, lot, cost_kind, ctx),
        check_nearby(bars, strategy, start, lot, cost_kind, ctx),
        check_shuffle(trades, strategy.risk.capital),
        check_sample(len(trades)),
    ]
    by = {c["id"]: c["status"] for c in checks}
    n, ret = len(trades), base["stats"]["ret"]
    if n < 15:
        verdict = "not_enough"
        summary = (f"Only {n} trade{'s' if n != 1 else ''} in this period. That's too few to tell a real edge "
                   "from a lucky streak, whatever the return says.")
    elif ret <= 0:
        verdict = "no_edge"
        summary = "After costs, the strategy lost money over the period, so there's no edge to test."
    elif by["unseen"] == "fail" or by["nearby"] == "fail":
        verdict = "luck"
        bits = []
        if by["unseen"] == "fail":
            bits.append("it lost money on the part of the period it wasn't tuned on")
        if by["nearby"] == "fail":
            bits.append("most settings near yours lose money")
        summary = "It made money overall, but " + " and ".join(bits) + ". The profit looks like a lucky fit."
    elif by["unseen"] == "pass" and by["nearby"] in ("pass", "skip") and by["shuffle"] != "fail":
        verdict = "edge"
        summary = ("It made money after costs, kept working on unseen data, and doesn't depend on one exact "
                   "setting. Worth paper trading before real money.")
    else:
        verdict = "mixed"
        summary = "Some checks pass and some don't. Treat it as a maybe: test it longer or on other instruments."
    return {"verdict": verdict, "headline": HEADLINES[verdict], "summary": summary,
            "passed": sum(1 for c in checks if c["status"] == "pass"),
            "total": sum(1 for c in checks if c["status"] != "skip"),
            "checks": checks, "suggestions": suggestions(verdict, strategy, days, max_days)}
