"""Rule evaluation, trading engine (long only) and backtest statistics.
The same Engine drives backtests and live paper trading."""
import math
import numpy as np
import pandas as pd
from . import costs as C
from .indicators import compute, ref_name, OSCILLATORS

OP_NAME = {"xa": "crosses above", "xb": "crosses below", "gt": "is above", "lt": "is below"}


class Ctx:
    def __init__(self, bars: list[dict], intraday: bool):
        df = pd.DataFrame(bars)
        try:
            df["t"] = pd.to_datetime(df["t"])
        except (ValueError, TypeError):
            # markets with daylight saving mix two UTC offsets; the engine only needs each
            # bar's local date and time (days for VWAP, months for period returns)
            df["t"] = pd.to_datetime(df["t"].astype(str).str.slice(0, 19))
        for col in "ohlcv":
            if col not in df:
                df[col] = 0.0
            df[col] = df[col].astype(float)
        self.df, self.intraday, self._cache = df, intraday, {}

    def series(self, ref) -> np.ndarray:
        key = (ref.t, ref.p, ref.m)
        if key not in self._cache:
            self._cache[key] = compute(ref, self.df, self.intraday).to_numpy(dtype=float)
        return self._cache[key]

    def val(self, ref, i: int):
        if ref.t == "num":
            return ref.v
        if i < 0:
            return None
        x = self.series(ref)[i]
        return None if math.isnan(x) else float(x)


def eval_cond(ctx: Ctx, c, i: int) -> bool:
    L, R = ctx.val(c.l, i), ctx.val(c.r, i)
    if L is None or R is None:
        return False
    if c.op == "gt":
        return L > R
    if c.op == "lt":
        return L < R
    Lp, Rp = ctx.val(c.l, i - 1), ctx.val(c.r, i - 1)
    if Lp is None or Rp is None:
        return False
    return (Lp <= Rp and L > R) if c.op == "xa" else (Lp >= Rp and L < R)


def cond_text(c) -> str:
    return f"{ref_name(c.l)} {OP_NAME[c.op]} {ref_name(c.r)}"


class Engine:
    """Trades one position at a time, long or short, with stop, target, trailing stop and time exit."""

    def __init__(self, strategy, lot: float = 1, state: dict | None = None, cost_kind: str = "flat"):
        # `lot` is the quantity step: 1 share, an F&O lot of 75, or 0.0001 of a coin
        self.s, self.r = strategy, strategy.risk
        self.dir = -1 if getattr(strategy, "side", "long") == "short" else 1
        self.qty_step = float(lot) if lot and lot > 0 else 1.0
        self.kind = cost_kind
        self.cash = self.r.capital
        self.qty, self.entry, self.sl, self.tg = 0, 0.0, 0.0, math.inf
        self.init_sl, self.best, self.held = 0.0, 0.0, 0
        self.entry_t = None
        self.entry_cost = 0.0
        self.trades: list[dict] = []
        self.events: list[dict] = []
        self.cost_items: dict[str, float] = {}
        self.skipped_size = 0
        if state:
            self.load(state)

    # --- persistence for live sessions ---
    def dump(self) -> dict:
        return {"cash": self.cash, "qty": self.qty, "entry": self.entry, "sl": self.sl,
                "tg": None if math.isinf(self.tg) else self.tg, "entry_t": self.entry_t,
                "entry_cost": self.entry_cost, "cost_items": self.cost_items,
                "init_sl": self.init_sl, "best": self.best, "held": self.held,
                "trades": self.trades[-500:], "events": self.events[-1000:]}

    def load(self, st: dict):
        self.cash, self.qty, self.entry, self.sl = st["cash"], st["qty"], st["entry"], st["sl"]
        self.tg = math.inf if st.get("tg") is None else st["tg"]
        self.entry_t = st.get("entry_t")
        self.entry_cost = st.get("entry_cost", 0.0)
        self.cost_items = st.get("cost_items", {})
        self.init_sl = st.get("init_sl", self.sl)
        self.best = st.get("best", self.entry)
        self.held = st.get("held", 0)
        self.trades, self.events = st.get("trades", []), st.get("events", [])

    def _pay(self, side: str, qty: float, px: float) -> float:
        items = C.order_costs(self.kind, side, qty, px, self.r.brokerage)
        for k, v in items.items():
            self.cost_items[k] = self.cost_items.get(k, 0.0) + v
        return C.total(items)

    def equity(self, px: float) -> float:
        return self.cash + self.dir * self.qty * px

    def _exit_price(self, b: dict) -> tuple[float | None, str]:
        """Where an open trade closes on this candle, checked in order: stop, target, time, exit rule."""
        r, long = self.r, self.dir == 1
        stop_on = r.sl > 0 or r.trail > 0
        trailed = r.trail > 0 and self.sl != self.init_sl
        if stop_on and self.sl > 0 and (b["l"] <= self.sl if long else b["h"] >= self.sl):
            px = min(b["o"], self.sl) if long else max(b["o"], self.sl)
            return px, "Trailing stop" if trailed else "Stop loss"
        if not math.isinf(self.tg) and (b["h"] >= self.tg if long else b["l"] <= self.tg):
            return (max(b["o"], self.tg) if long else min(b["o"], self.tg)), "Target"
        if r.maxBars and self.held >= r.maxBars:
            return b["c"], "Time exit"
        return None, ""

    def step(self, bars: list[dict], ctx: Ctx, i: int) -> list[dict]:
        b, r = bars[i], self.r
        slip, brok, d = r.slippage / 100, r.brokerage, self.dir
        open_side, close_side = ("buy", "sell") if d == 1 else ("sell", "buy")
        new = []
        if self.qty > 0:
            self.held += 1
            px, why = self._exit_price(b)
            if px is None and self.s.exit and any(eval_cond(ctx, c, i) for c in self.s.exit):
                px, why = b["c"], "Exit rule"
            if px is not None:
                px *= 1 - slip * d            # selling a long fills lower, buying back a short fills higher
                exit_cost = self._pay(close_side, self.qty, px)
                trade_costs = self.entry_cost + exit_cost
                pnl = d * self.qty * (px - self.entry) - trade_costs
                self.cash += d * self.qty * px - exit_cost
                self.trades.append({"entry_t": self.entry_t, "exit_t": b["t"], "entry": self.entry, "exit": px,
                                    "qty": self.qty, "pnl": pnl, "costs": trade_costs, "side": "short" if d == -1 else "long",
                                    "ret": d * (px / self.entry - 1) * 100, "why": why})
                ev = {"t": b["t"], "side": close_side, "px": px, "qty": self.qty, "why": why, "pnl": pnl}
                self.events.append(ev); new.append(ev)
                self.qty = 0
            else:
                # ratchet the trailing stop with the best price so far; it applies from the next candle
                if r.trail > 0:
                    t = r.trail / 100
                    if d == 1:
                        self.best = max(self.best, b["h"])
                        self.sl = max(self.sl, self.best * (1 - t))
                    else:
                        self.best = min(self.best, b["l"])
                        self.sl = min(self.sl, self.best * (1 + t)) if self.sl > 0 else self.best * (1 + t)
        elif self.s.entry:
            checks = (eval_cond(ctx, c, i) for c in self.s.entry)
            hit = any(checks) if self.s.entryJoin == "any" else all(checks)
            if hit:
                px = b["c"] * (1 + slip * d)
                risk_dist = (r.sl or r.trail) / 100
                cap = self.cash * r.maxAlloc / 100
                q = self.cash * r.riskPct / 100 / (px * risk_dist) if risk_dist > 0 else math.inf
                q = C.floor_to(min(q, (cap - brok) / px), self.qty_step)
                # percentage costs (STT, exchange fees) must fit in the budget too
                while q > 0 and q * px + C.total(C.order_costs(self.kind, open_side, q, px, brok)) > cap:
                    q = C.floor_to(q - max(self.qty_step, q * 0.002), self.qty_step)
                if q <= 0:
                    self.skipped_size += 1
                if q > 0:
                    self.entry_cost = self._pay(open_side, q, px)
                    self.cash -= d * q * px + self.entry_cost
                    self.qty, self.entry, self.entry_t, self.held, self.best = q, px, b["t"], 0, px
                    stop = r.sl or r.trail
                    self.sl = px * (1 - d * stop / 100) if stop > 0 else 0.0
                    self.init_sl = self.sl
                    self.tg = px * (1 + d * r.tgt / 100) if r.tgt > 0 else math.inf
                    ev = {"t": b["t"], "side": open_side, "px": px, "qty": q,
                          "why": "Entry rule" if d == 1 else "Short entry"}
                    self.events.append(ev); new.append(ev)
        return new

def stats(eq: list[float], trades: list[dict], capital: float, per_year: float) -> dict:
    arr = np.asarray(eq, dtype=float)
    end = float(arr[-1])
    peak = np.maximum.accumulate(arr)
    dd = (arr / peak - 1) * 100
    rets = np.diff(arr) / arr[:-1] if len(arr) > 1 else np.array([0.0])
    sd = float(rets.std())
    years = len(arr) / per_year
    wins = [t for t in trades if t["pnl"] > 0]
    gw = sum(t["pnl"] for t in wins)
    gl = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    n = len(trades)
    return {
        "ret": (end / capital - 1) * 100, "pnl": end - capital,
        "cagr": ((end / capital) ** (1 / years) - 1) * 100 if years > 0 and end > 0 else 0.0,
        "mdd": float(dd.min()), "dd": dd.tolist(),
        "sharpe": float(rets.mean() / sd * math.sqrt(per_year)) if sd > 0 else 0.0,
        "n": n, "win": len(wins) / n * 100 if n else 0.0,
        "pf": (gw / gl) if gl > 0 else (None if gw > 0 else 0.0),  # None = infinite
        "avg": sum(t["pnl"] for t in trades) / n if n else 0.0,
    }


PER_YEAR = {"1d": 252, "1h": 252 * 7, "15m": 252 * 25, "5m": 252 * 75}


def chart_series(strategy, ctx: Ctx, start: int) -> tuple[dict, dict]:
    overlays, osc = {}, {}
    for c in [*strategy.entry, *strategy.exit]:
        for ref in (c.l, c.r):
            if ref.t in ("price", "num"):
                continue
            target = osc if ref.t in OSCILLATORS else overlays
            target[ref_name(ref)] = clean(ctx.series(ref)[start:])
    return overlays, osc


def clean(a) -> list:
    return [None if (x is None or (isinstance(x, float) and not math.isfinite(x))) else round(float(x), 4) for x in a]


def _never(ctx: Ctx, c, start: int) -> bool:
    """True if one side of the condition has no value at all in the test window (e.g. a missing number)."""
    for ref in (c.l, c.r):
        if ref.t == "num":
            if ref.v is None:
                return True
            continue
        vals = ctx.series(ref)[start:]
        if not any(math.isfinite(x) for x in vals):
            return True
    return False


def period_key(t: pd.Timestamp, tf: str) -> str:
    return t.strftime("%b %y") if tf == "1d" else t.strftime("%d %b")


def simulate(bars: list[dict], strategy, start: int, end: int | None = None, lot: float = 1,
             cost_kind: str = "flat", ctx: Ctx | None = None) -> tuple[Engine, list[float]]:
    """Trade bars start+1 .. end-1 with fresh capital. Indicators use all earlier bars, so there is no warm-up gap."""
    ctx = ctx or Ctx(bars, intraday=strategy.tf != "1d")
    end = len(bars) if end is None else end
    eng = Engine(strategy, lot, cost_kind=cost_kind)
    equity = [strategy.risk.capital]
    for i in range(start + 1, end):
        eng.step(bars, ctx, i)
        equity.append(eng.equity(bars[i]["c"]))
    return eng, equity


def backtest(bars: list[dict], strategy, start: int, lot: float = 1, cost_kind: str = "flat") -> dict:
    tf = strategy.tf
    ctx = Ctx(bars, intraday=tf != "1d")
    eng, equity = simulate(bars, strategy, start, lot=lot, cost_kind=cost_kind, ctx=ctx)
    cap = strategy.risk.capital
    view = bars[start:]
    open_trade = None
    if eng.qty > 0:
        last = bars[-1]["c"]
        open_trade = {"entry_t": eng.entry_t, "exit_t": None, "entry": eng.entry, "exit": last, "qty": eng.qty,
                      "pnl": eng.dir * eng.qty * (last - eng.entry), "ret": eng.dir * (last / eng.entry - 1) * 100,
                      "side": "short" if eng.dir == -1 else "long", "why": "Still open"}
    st = stats(equity, eng.trades, cap, PER_YEAR[tf])
    first = view[0]["c"]
    bh = [cap * b["c"] / first for b in view]
    # period returns
    ts = ctx.df.t.iloc[start:].reset_index(drop=True)
    periods, cur, s_eq = [], None, equity[0]
    for j, t in enumerate(ts):
        k = period_key(t, tf)
        if k != cur:
            if cur is not None:
                periods.append({"k": cur, "ret": (equity[j - 1] / s_eq - 1) * 100})
                s_eq = equity[j - 1]
            cur = k
    periods.append({"k": cur, "ret": (equity[-1] / s_eq - 1) * 100})
    overlays, osc = chart_series(strategy, ctx, start)
    rng = range(start + 1, len(bars))
    ent = [[eval_cond(ctx, c, i) for i in rng] for c in strategy.entry]
    comb = [(any if strategy.entryJoin == "any" else all)(col) for col in zip(*ent)] if ent else []
    diagnostics = {
        "entry": [{"text": cond_text(c), "true_on": sum(v), "never_computed": _never(ctx, c, start)} for c, v in zip(strategy.entry, ent)],
        "entry_join": strategy.entryJoin,
        "all_true_on": sum(comb),
        "exit": [{"text": cond_text(c), "true_on": sum(eval_cond(ctx, c, i) for i in rng)} for c in strategy.exit],
        "skipped_size": eng.skipped_size,
        "candles": len(rng),
    }
    return {
        "diagnostics": diagnostics,
        "bars": [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} for b in view],
        "equity": clean(equity), "buy_hold": clean(bh), "drawdown": clean(st.pop("dd")),
        "stats": {**st, "buy_hold_ret": (view[-1]["c"] / first - 1) * 100},
        "trades": eng.trades, "open_trade": open_trade, "events": eng.events,
        "overlays": overlays, "oscillators": osc, "periods": periods[-60:],
        "costs": cost_summary(eng, cost_kind, equity[-1] - cap),
    }


def cost_summary(eng: Engine, cost_kind: str, net_pnl: float) -> dict:
    """Profit before costs, each cost line, a tax estimate, and what is left."""
    paid = sum(eng.cost_items.values())
    tax = C.tax_estimate(cost_kind, eng.trades)
    kept = net_pnl - (tax["amount"] or 0.0)
    return {"gross_pnl": round(net_pnl + paid, 2), "total": round(paid, 2), "items": C.breakdown(eng.cost_items),
            "net_pnl": round(net_pnl, 2), "tax": tax, "kept": round(kept, 2)}
