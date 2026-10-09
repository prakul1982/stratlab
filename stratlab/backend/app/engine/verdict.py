"""Is the edge real? Four checks on a backtest, and a plain-English verdict.

1. Unseen data: split the test period 70/30 and trade each part with fresh capital.
   A real edge keeps making money on the part it wasn't tuned on.
2. Nearby settings: nudge the indicator lengths up and down (and an India VIX
   cut-off, when the rules have one). If only the exact settings you picked make
   money, the result is probably a lucky fit.
3. Bad-luck drawdown: reshuffle the order of the trades 1,000 times. The worst
   falls show how deep a drawdown the same trades could have produced.
4. Enough trades: under 15 trades, luck dominates; 30+ is a fair sample.
All returns are after costs."""
import copy

import numpy as np

from ..models import Ref
from .core import SPLIT, Ctx, simulate
from .indicators import MARKET, params, ref_name

SHUFFLES = 1000
SHUFFLE_BLOCK = 2_000_000
PERIOD_TYPES = {"sma", "ema", "rsi", "vwap", "macd", "macd_signal", "macd_hist",
                "bb_upper", "bb_mid", "bb_lower", "supertrend", "stage",
                "adx", "stoch_k", "atr_pct", "dc_upper", "dc_lower", "vol_sma"}
NUDGES = (0.6, 0.8, 1.0, 1.2, 1.4)

# each verdict in a few words, as facts about the checks (R11C-009: no "Likely a real edge." or "Probably luck."); a
# verdict's own headline is fact_headline's, with its numbers
HEADLINES = {
    "edge": "Passed the checks.",
    "mixed": "Mixed check results.",
    "luck": "Failed a robustness check.",
    "not_enough": "Too few trades.",
    "no_edge": "Lost money after costs.",
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


# the fewest trades in the unseen part that can pass the check (R6O-010: "Passed ... 3 trades +1.1%"). Below five, one
# or two trades decide the sign of the result: with three, a single winner can turn the part into a profit however the
# rule does otherwise. Five is the smallest count where no one trade is more than a fifth of what is being judged.
MIN_UNSEEN_TRADES = 5


def unseen_check(trades: list[dict], open_trades: list[dict], capital: float, built: list[bool], spans: list[bool],
                 labels: tuple[str, str, str, str], split_index: int, who: str = "It") -> dict:
    """The unseen-data check from the run's own trades: each trade counts with the part it was opened in (a trade
    opened before the split and closed after it counts with the built part), so the two parts' trades add up to the
    whole test and each part's return is the sum of its trades' P&L after costs, as a % of the starting capital. A
    trade still open at the end counts with its part at its value on the last close. `built` and `spans` hold one flag
    per trade, closed trades first, then the open ones."""
    every = [*trades, *open_trades]
    n_closed = len(trades)
    part = lambda b: [t for t, x in zip(every, built) if x == b]       # noqa: E731
    b_tr, u_tr = part(True), part(False)
    ret = lambda ts: sum(t["pnl"] for t in ts) / capital * 100 if capital else 0.0    # noqa: E731
    closed_in = lambda b: sum(1 for k, x in enumerate(built) if x == b and k < n_closed)   # noqa: E731
    open_in = [("built" if x else "unseen") for k, x in enumerate(built) if k >= n_closed]
    r1, r2 = ret(b_tr), ret(u_tr)
    data = {"built_ret": r1, "unseen_ret": r2, "built_trades": closed_in(True), "unseen_trades": closed_in(False),
            "open_built": open_in.count("built"), "open_unseen": open_in.count("unseen"), "spanning": sum(spans),
            "built_from": labels[0], "built_to": labels[1], "unseen_from": labels[2], "unseen_to": labels[3],
            "split_index": split_index}
    if not u_tr:
        status, detail = "warn", "No trades happened in the unseen part, so it couldn't be tested there."
    elif len(u_tr) < MIN_UNSEEN_TRADES:
        n = len(u_tr)
        status, detail = "warn", (f"Only {n} trade{'s' if n != 1 else ''} happened in the unseen part ({'+' if r2 >= 0 else '−'}{abs(r2):.1f}%): "
                                  f"too few to tell, as one or two trades decide the result. It needs at least {MIN_UNSEEN_TRADES}.")
    elif r2 > 0:
        status, detail = "pass", ("It kept making money on data it wasn't tuned on." if who == "It"
                                  else f"{who} kept making money on the part of the period it wasn't tuned on.")
    else:
        status, detail = "fail", f"{who} lost money on the part of the period it hadn't seen."
    return {"id": "unseen", "title": "Unseen data", "status": status, "detail": detail, "data": data}


def check_unseen(bars, base: dict, start: int, capital: float) -> dict:
    """The unseen-data check of one instrument's backtest (`base`, from core.backtest)."""
    split = base["_split"]
    every = [*base["trades"], *([base["open_trade"]] if base.get("open_trade") else [])]
    built = [t.get("part", "built") == "built" for t in every]
    return unseen_check(base["trades"], [base["open_trade"]] if base.get("open_trade") else [], capital, built,
                        [bool(t.get("spans_split")) for t in every],
                        (_year_label(bars, start), _year_label(bars, split), _year_label(bars, split), _year_label(bars, len(bars) - 1)),
                        split - start)


def _market_cut(c) -> tuple[str, float] | None:
    """A rule comparing India VIX (or its change %) with a number: ("india_vix", the number)."""
    for a, b in ((c.l, c.r), (c.r, c.l)):
        if a.t in MARKET and b.t == "num" and b.v is not None:
            return a.t, float(b.v)
    return None


def _param_keys(strategy) -> list[tuple[str, float]]:
    """What the check nudges, at most two: an India VIX cut-off first (a level picked to fit the past is the easiest
    lucky number to miss), then the indicator lengths."""
    keys = []
    for c in strategy.all_conds():
        cut = _market_cut(c)
        if cut and cut not in keys:
            keys.append(cut)
            break
    for c in strategy.all_conds():
        for ref in (c.l, c.r):
            if ref.t in PERIOD_TYPES:
                key = (ref.t, params(ref)[0])
                if key not in keys:
                    keys.append(key)
    return keys[:2]


def _values(key: tuple[str, float]) -> list:
    """The nudged values of a key: lengths by NUDGES; an India VIX level by the same factors to the nearest 0.5; a
    change % by 1 and 2 points either way."""
    t, v = key
    if t == "india_vix_chg":
        return [round(v + d, 2) for d in (-2, -1, 0, 1, 2)]
    if t in MARKET:
        out = []
        for f in NUDGES:
            x = round(v * f * 2) / 2 if f != 1.0 else v
            if x > 0 and x not in out:
                out.append(x)
        return out
    return _nudged(int(v))


def _nudged(p: int) -> list[int]:
    vals = []
    for f in NUDGES:
        v = max(2, int(round(p * f)))
        if v not in vals:
            vals.append(v)
    return vals


def _with(strategy, subs: dict[tuple, float]):
    s = copy.deepcopy(strategy)
    for c in s.all_conds():
        cut = _market_cut(c)
        if cut in subs:
            num = c.r if c.r.t == "num" else c.l
            num.v = subs[cut]
            continue
        for ref in (c.l, c.r):
            key = (ref.t, params(ref)[0]) if ref.t in PERIOD_TYPES else None
            if key in subs:
                ref.p = subs[key]
    return s


def check_nearby(bars, strategy, start, lot, kind, ctx, traded: bool | None = None) -> dict:
    """`traded`: whether the exact settings made any trade (False: none at all, so there's nothing to compare)."""
    keys = _param_keys(strategy)
    if not keys:
        return {"id": "nearby", "title": "Nearby settings", "status": "skip",
                "detail": "Your rules have no indicator lengths to nudge, so this check was skipped.", "data": None}
    cap = strategy.risk.capital
    cols_key = keys[0]
    rows_key = keys[1] if len(keys) > 1 else None
    cols = _values(cols_key)
    rows = _values(rows_key) if rows_key else [None]
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
    detail = {"pass": f"{profitable} of {total} settings near yours made money too.",
              "warn": f"{profitable} of {total} settings near yours made money: the result changes a lot with the exact numbers.",
              "fail": f"{profitable} of {total} settings near yours made money; most lost money."}[status]
    if traded is False:
        # no trade with the exact settings: nothing to compare the neighbours with (R11C-006: "Failed ... Your exact
        # numbers look like a lucky fit" on a test with no trades)
        status = "skip"
        detail = (f"Your settings made no trades in this period, so there is no result of yours to compare. "
                  f"{profitable} of {total} settings near yours made money.")

    def label(key):
        if key[0] in MARKET:
            return ref_name(Ref(t=key[0])) + " cut-off"
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


def _trade_dds(orders: np.ndarray, capital: float) -> np.ndarray:
    """The worst fall of each row of trade results at once (one array operation instead of a Python loop per
    reshuffle, so a backtest doesn't hold up other people's pages)."""
    path = capital + np.cumsum(orders, axis=1)
    path = np.concatenate([np.full((orders.shape[0], 1), capital), path], axis=1)
    peak = np.maximum.accumulate(path, axis=1)
    return np.max((peak - path) / peak, axis=1) * 100


def _path_dds(inc: np.ndarray, starts: np.ndarray, lens: np.ndarray, perms: np.ndarray, capital: float) -> np.ndarray:
    """The worst day-by-day fall of each reshuffle: every row of `perms` is an order of the trades, and each trade
    brings its own run of daily changes in account value (entry costs, each day's move, exit), so a reshuffle is the
    same days in another order of trades."""
    order_lens = lens[perms]                                         # rows × trades
    seg = np.repeat(perms.ravel(), order_lens.ravel()).reshape(perms.shape[0], -1)
    offs = np.cumsum(order_lens, axis=1) - order_lens                # where each trade starts in its row
    within = np.arange(seg.shape[1])[None, :] - np.repeat(offs.ravel(), order_lens.ravel()).reshape(seg.shape)
    return _trade_dds(inc[starts[seg] + within], capital)


def fall_text(v: float) -> str:
    """A fall from the peak as the pages write it: one decimal, and a fall that rounds to nothing is "0%"."""
    return "0%" if round(v, 1) == 0 else f"{v:.1f}%"


def check_shuffle(trades: list[dict], capital: float, who: str = "Your backtest", whose: str = "your backtest's",
                  paths: list | None = None, steps: list | None = None) -> dict:
    """Reshuffle the trades' order: how deep a fall the same trades could have had. `who` and `whose` name the trades
    in the wording (a backtest's, or the user's real trades in the journal).

    With `paths` (a backtest: each trade's day-by-day changes in account value, the open trade's too), falls are
    measured day by day from the peak, the same measure as the backtest's "Worst fall", which "yours" then equals.
    Without them (real trades, known only by their results) each trade is one step.

    With `steps` (a group of instruments, whose trades overlap), the account's day-by-day changes are reshuffled: the
    same days in another order. A reshuffle that can't reorder anything (fewer than five pieces to move) proves nothing,
    so the check is then not run rather than passed (R11C-010)."""
    pnls = np.array([t["pnl"] for t in trades], dtype=float)
    if len(pnls) < 5:
        return {"id": "shuffle", "title": "Bad-luck drawdown", "status": "skip",
                "detail": "Too few trades to reshuffle.", "data": None}
    rng = np.random.default_rng(42)  # same answer every time for the same trades
    moving = [s for s in (steps or []) if s] if steps is not None else None
    if steps is not None and len(moving) < 5:
        return {"id": "shuffle", "title": "Bad-luck drawdown", "status": "skip",
                "detail": "Too few days with a change in the account to reshuffle.", "data": None}
    if paths is not None and steps is None and len(paths) < 5:
        return {"id": "shuffle", "title": "Bad-luck drawdown", "status": "skip",
                "detail": "Too few separate trades to reshuffle: they overlap, so their order can't change.", "data": None}
    by = "trades"
    if steps is not None:
        by = "days"
        inc = np.asarray(steps, dtype=float)
        yours = _trade_dd(inc, capital)
        rows = max(1, SHUFFLE_BLOCK // max(1, len(inc)))
        dds = np.concatenate([_trade_dds(np.stack([rng.permutation(inc) for _ in range(min(rows, SHUFFLES - i))]), capital)
                              for i in range(0, SHUFFLES, rows)])
    elif paths:
        segs = [np.asarray(p, dtype=float) for p in paths]
        lens = np.array([len(p) for p in segs])
        inc = np.concatenate(segs) if segs else np.zeros(0)
        starts = np.cumsum(lens) - lens
        yours = _trade_dd(inc, capital)
        rows = max(1, SHUFFLE_BLOCK // max(1, len(inc)))
        dds = np.concatenate([_path_dds(inc, starts, lens, np.stack([rng.permutation(len(segs)) for _ in range(min(rows, SHUFFLES - i))]), capital)
                              for i in range(0, SHUFFLES, rows)])
    else:
        # in blocks of about two million numbers, so thousands of trades (a real-trade journal) never build one huge array;
        # the reshuffles come in the same order, so the answer is the same as all at once
        rows = max(1, SHUFFLE_BLOCK // len(pnls))
        dds = np.concatenate([_trade_dds(np.stack([rng.permutation(pnls) for _ in range(min(rows, SHUFFLES - i))]), capital)
                              for i in range(0, SHUFFLES, rows)])
        yours = _trade_dd(pnls, capital)
    p95, worst = float(np.percentile(dds, 95)), float(dds.max())
    what = "days" if by == "days" else "trades"
    if p95 >= 35:
        status = "fail"
        detail = (f"{who} fell {fall_text(yours)} at worst; in 95 of 100 reshuffles of the same {what} the fall was up to "
                  f"{fall_text(p95)}, 35% or more.")
    elif p95 > max(1.5 * yours, 5):
        status = "warn"
        detail = f"{who} fell {fall_text(yours)} at worst; in 95 of 100 reshuffles the fall was up to {fall_text(p95)}."
    else:
        status = "pass"
        detail = f"In 95 of 100 reshuffles the fall was up to {fall_text(p95)}, close to {whose} {fall_text(yours)}."
    return {"id": "shuffle", "title": "Bad-luck drawdown", "status": status, "detail": detail,
            "data": {"yours": yours, "p95": p95, "worst": worst, "runs": SHUFFLES, "daily": bool(paths) or by == "days", "by": by}}


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
        check_unseen(bars, base, start, strategy.risk.capital),
        check_nearby(bars, strategy, start, lot, cost_kind, ctx, bool(trades or base.get("open_trade"))),
        check_shuffle(trades, strategy.risk.capital, paths=base.get("_paths")),
        check_sample(len(trades)),
    ]
    return decide(checks, len(trades), base["stats"]["ret"], strategy, days, max_days, base["stats"].get("buy_hold_ret"))


def _pc(v: float) -> str:
    """A signed percentage with a real minus, as the pages write it: +24.6%, −3.1%, 0.0%."""
    s = f"{abs(v):.1f}"
    return ("" if float(s) == 0 else "+" if v > 0 else "−") + s + "%"


def versus_hold(ret: float, hold: float | None) -> str:
    """The plain comparison with buying and holding, stated as a fact in every verdict."""
    if hold is None:
        return ""
    if abs(ret - hold) < 0.05:
        rel = "about the same as"
    else:
        rel = "more than" if ret > hold else "less than"
    return f" The strategy returned {_pc(ret)} after costs, {rel} buying and holding over the same period ({_pc(hold)})."


def fact_label(verdict: str, checks: list[dict], n: int, none: bool = False) -> str:
    """The verdict as a fact about the checks, in the library card's words (library.label): no claim about the strategy,
    no instruction."""
    run = [c for c in checks if c.get("status") != "skip"]
    passed = sum(1 for c in run if c.get("status") == "pass")
    if verdict == "not_enough":
        return "No trades in this period" if none or n == 0 else f"Only {n} trade{'s' if n != 1 else ''}: too few to judge"
    if verdict == "no_edge":
        return "Lost money after costs"
    if verdict == "luck":
        by = {c["id"]: c.get("status") for c in checks}
        if by.get("unseen") == "fail":
            return "Lost money on the unseen part of the period"
        if by.get("nearby") == "fail":
            return "Failed the nearby-settings check"
    if not run:
        return "No checks could be run"
    if passed == 4:
        return "Passed all four checks"
    return f"Passed all {len(run)} checks run" if passed == len(run) else f"Passed {passed} of the {len(run)} checks run"


def fact_headline(verdict: str, checks: list[dict], n: int, ret: float, hold: float | None, none: bool = False) -> str:
    """The headline of a verdict as facts (R11C-009: "Likely a real edge." over +55.8% against +173.6% for buy and hold):
    how the return after costs compares with buying and holding, then what the checks found, as the library card says it
    ("117.1 points behind buy and hold after costs; passed all 3 checks run.")."""
    lab = fact_label(verdict, checks, n, none)
    if hold is None or none:
        return lab + "."
    gap = ret - hold
    low = lab[:1].lower() + lab[1:]
    if gap <= -1:
        return f"{abs(gap):.1f} points behind buy and hold after costs; {low}."
    if gap >= 1:
        return f"{gap:.1f} points ahead of buy and hold after costs; {low}."
    return f"Within a point of buy and hold after costs; {low}."


def decide(checks: list[dict], n: int, ret: float, strategy, days: int, max_days: int, hold: float | None = None) -> dict:
    """The verdict from the checks, the trade count and the return after costs. `hold` is buy and hold's return over
    the same period: the summary always states how the two compare."""
    by = {c["id"]: c["status"] for c in checks}
    none = n == 0 and abs(ret) < 1e-9          # not one trade, not even one still open: nothing happened to judge
    if none:
        verdict = "not_enough"
        # no claim about a return that no trade made (R11C-006: "returned 0.0% after costs, more than buying and holding")
        summary = "No trades happened in this period: the rules' conditions never held together, so the account stayed at its starting capital."
        if hold is not None:
            summary += f" Buying and holding returned {_pc(hold)} over the same period."
    elif n < 15:
        verdict = "not_enough"
        summary = (f"Only {n} trade{'s' if n != 1 else ''} in this period. That's too few to tell a real edge "
                   "from a lucky streak, whatever the return says.")
    elif ret <= 0:
        verdict = "no_edge"
        summary = "After costs, the strategy lost money over the period."
    elif by["unseen"] == "fail" or by["nearby"] == "fail":
        verdict = "luck"
        bits = []
        if by["unseen"] == "fail":
            bits.append("it lost money on the part of the period it wasn't tuned on")
        if by["nearby"] == "fail":
            bits.append("most settings near yours lost money")
        summary = "It made money overall, but " + " and ".join(bits) + "."
    elif by["unseen"] == "pass" and by["nearby"] in ("pass", "skip") and by["shuffle"] != "fail":
        verdict = "edge"
        # only what the checks showed: a nearby-settings check that wasn't run (a group of stocks) proves nothing about
        # the settings (R6V-005)
        summary = ("It made money after costs, kept making money on unseen data, and settings near yours made money too."
                   if by["nearby"] == "pass" else
                   "It made money after costs and kept making money on unseen data. The nearby-settings check wasn't "
                   "run, so this doesn't show whether the result depends on the exact settings.")
        if by["shuffle"] == "warn":
            summary += " With the trades in a worse order, the worst fall was much deeper."
    else:
        verdict = "mixed"
        summary = "It made money after costs, but some checks pass and some don't."
    if not none:
        summary += versus_hold(ret, hold)
    return {"verdict": verdict, "headline": fact_headline(verdict, checks, n, ret, hold, none), "summary": summary,
            "passed": sum(1 for c in checks if c["status"] == "pass"),
            "total": sum(1 for c in checks if c["status"] != "skip"),
            "checks": checks, "suggestions": suggestions(verdict, strategy, days, max_days)}


def evaluate_portfolio(run, base: dict, strategy, days: int, max_days: int) -> dict:
    """The checks for a group of instruments. `run(t_from, t_to)` re-runs the portfolio on part of the period (kept for
    callers; the unseen check reads the full run's own trades, as for one instrument)."""
    times, cap = base["times"], strategy.risk.capital
    checks = []
    if len(times) > 20:
        k = int(len(times) * SPLIT)
        split = _when(times[k])
        opened = base.get("open_trades") or []
        every = [*base["trades"], *opened]
        built = [_when(t["entry_t"]) < split for t in every]
        spans = [b and (t.get("exit_t") is None or _when(t["exit_t"]) >= split) for t, b in zip(every, built)]
        checks.append(unseen_check(base["trades"], opened, cap, built, spans,
                                   (times[0][:4], times[k][:4], times[k][:4], times[-1][:4]), k, who="The portfolio"))
    else:
        checks.append({"id": "unseen", "title": "Unseen data", "status": "skip", "detail": "Too short a period to split.", "data": None})
    checks.append({"id": "nearby", "title": "Nearby settings", "status": "skip",
                   "detail": "Not run on a group of instruments yet: it would mean hundreds of backtests. Test the idea on one stock to see this check.",
                   "data": None})
    # a group's trades overlap (ten positions open at once), so reordering whole trades isn't possible: the stretches with
    # any position open run into one, and a reshuffle of one stretch is no reshuffle at all (R11C-010: p95 = worst = yours
    # to 15 digits). The group's own account is reshuffled instead, day by day.
    checks.append(check_shuffle(base["trades"], cap, steps=day_steps(times, base.get("equity") or [], cap)))
    checks.append(check_sample(len(base["trades"])))
    return decide(checks, len(base["trades"]), base["stats"]["ret"], strategy, days, max_days, base["stats"].get("buy_hold_ret"))


def day_steps(times: list[str], equity: list, capital: float) -> list[float]:
    """Each trading day's change in the account's value, from its value at the day's last candle: what the group's
    bad-luck check reshuffles."""
    last: dict[str, float] = {}
    for t, v in zip(times, equity):
        if v is not None:
            last[str(t)[:10]] = float(v)
    values = [capital, *(last[d] for d in sorted(last))]
    return [b - a for a, b in zip(values, values[1:])]


def _when(t: str):
    from datetime import datetime
    return datetime.fromisoformat(str(t))
