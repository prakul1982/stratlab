"""Rule evaluation, trading engine (long only) and backtest statistics.
The same Engine drives backtests and live paper trading."""
import math
import numpy as np
import pandas as pd
from .indicators import compute, ref_name, OSCILLATORS

OP_NAME = {"xa": "crosses above", "xb": "crosses below", "gt": "is above", "lt": "is below"}


class Ctx:
    def __init__(self, bars: list[dict], intraday: bool):
        df = pd.DataFrame(bars)
        df["t"] = pd.to_datetime(df["t"])
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
    def __init__(self, strategy, lot: int = 1, state: dict | None = None):
        self.s, self.r, self.lot = strategy, strategy.risk, max(1, int(lot or 1))
        self.cash = self.r.capital
        self.qty, self.entry, self.sl, self.tg = 0, 0.0, 0.0, math.inf
        self.entry_t = None
        self.trades: list[dict] = []
        self.events: list[dict] = []
        if state:
            self.load(state)

    # --- persistence for live sessions ---
    def dump(self) -> dict:
        return {"cash": self.cash, "qty": self.qty, "entry": self.entry, "sl": self.sl,
                "tg": None if math.isinf(self.tg) else self.tg, "entry_t": self.entry_t,
                "trades": self.trades[-500:], "events": self.events[-1000:]}

    def load(self, st: dict):
        self.cash, self.qty, self.entry, self.sl = st["cash"], st["qty"], st["entry"], st["sl"]
        self.tg = math.inf if st.get("tg") is None else st["tg"]
        self.entry_t = st.get("entry_t")
        self.trades, self.events = st.get("trades", []), st.get("events", [])

    def equity(self, px: float) -> float:
        return self.cash + self.qty * px

    def step(self, bars: list[dict], ctx: Ctx, i: int) -> list[dict]:
        b, r = bars[i], self.r
        slip, brok = r.slippage / 100, r.brokerage
        new = []
        if self.qty > 0:
            px, why = None, ""
            if r.sl > 0 and b["l"] <= self.sl:
                px, why = min(b["o"], self.sl), "Stop loss"
            elif b["h"] >= self.tg:
                px, why = max(b["o"], self.tg), "Target"
            elif self.s.exit and any(eval_cond(ctx, c, i) for c in self.s.exit):
                px, why = b["c"], "Exit rule"
            if px is not None:
                px *= 1 - slip
                pnl = self.qty * (px - self.entry) - 2 * brok
                self.cash += self.qty * px - brok
                self.trades.append({"entry_t": self.entry_t, "exit_t": b["t"], "entry": self.entry, "exit": px,
                                    "qty": self.qty, "pnl": pnl, "ret": (px / self.entry - 1) * 100, "why": why})
                ev = {"t": b["t"], "side": "sell", "px": px, "qty": self.qty, "why": why, "pnl": pnl}
                self.events.append(ev); new.append(ev)
                self.qty = 0
        elif self.s.entry:
            checks = (eval_cond(ctx, c, i) for c in self.s.entry)
            hit = any(checks) if self.s.entryJoin == "any" else all(checks)
            if hit:
                px = b["c"] * (1 + slip)
                slp = r.sl / 100
                q = math.floor(self.cash * r.riskPct / 100 / (px * slp)) if slp > 0 else math.inf
                q = min(q, math.floor((self.cash * r.maxAlloc / 100 - brok) / px))
                q = (q // self.lot) * self.lot
                if q > 0:
                    self.cash -= q * px + brok
                    self.qty, self.entry, self.entry_t = q, px, b["t"]
                    self.sl = px * (1 - slp)
                    self.tg = px * (1 + r.tgt / 100) if r.tgt > 0 else math.inf
                    ev = {"t": b["t"], "side": "buy", "px": px, "qty": q, "why": "Entry rule"}
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


def period_key(t: pd.Timestamp, tf: str) -> str:
    return t.strftime("%b %y") if tf == "1d" else t.strftime("%d %b")


def backtest(bars: list[dict], strategy, start: int, lot: int = 1) -> dict:
    tf = strategy.tf
    ctx = Ctx(bars, intraday=tf != "1d")
    eng = Engine(strategy, lot)
    cap = strategy.risk.capital
    equity = [cap]
    for i in range(start + 1, len(bars)):
        eng.step(bars, ctx, i)
        equity.append(eng.equity(bars[i]["c"]))
    view = bars[start:]
    open_trade = None
    if eng.qty > 0:
        last = bars[-1]["c"]
        open_trade = {"entry_t": eng.entry_t, "exit_t": None, "entry": eng.entry, "exit": last, "qty": eng.qty,
                      "pnl": eng.qty * (last - eng.entry), "ret": (last / eng.entry - 1) * 100, "why": "Still open"}
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
    return {
        "bars": [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} for b in view],
        "equity": clean(equity), "buy_hold": clean(bh), "drawdown": clean(st.pop("dd")),
        "stats": {**st, "buy_hold_ret": (view[-1]["c"] / first - 1) * 100},
        "trades": eng.trades, "open_trade": open_trade, "events": eng.events,
        "overlays": overlays, "oscillators": osc, "periods": periods[-60:],
    }
