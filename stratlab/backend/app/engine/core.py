"""Rule evaluation, the trading engine and backtest statistics.
The same Engine drives backtests and live paper trading."""
import math
import numpy as np
import pandas as pd
from . import costs as C
from .indicators import compute_full, ref_name, OSCILLATORS

OP_NAME = {"xa": "crosses above", "xb": "crosses below", "gt": "is above", "lt": "is below", "eq": "is"}


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
        key = (ref.t, ref.p, ref.m, getattr(ref, "ago", None), getattr(ref, "k", None), getattr(ref, "tf", None))
        if key not in self._cache:
            self._cache[key] = compute_full(ref, self.df, self.intraday).to_numpy(dtype=float)
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
    if c.op == "eq":
        return abs(L - R) < 1e-9
    Lp, Rp = ctx.val(c.l, i - 1), ctx.val(c.r, i - 1)
    if Lp is None or Rp is None:
        return False
    return (Lp <= Rp and L > R) if c.op == "xa" else (Lp >= Rp and L < R)


def cond_text(c) -> str:
    return f"{ref_name(c.l)} {OP_NAME[c.op]} {ref_name(c.r)}"


TF_MIN = {"5m": 5, "15m": 15, "1h": 60, "1d": 1440}


def _minutes(hhmm: str) -> int | None:
    if not hhmm:
        return None
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def bar_clock(t: str, tf_min: int) -> tuple[str, int]:
    """The candle's trading date and the minute of the day it closes at, in the exchange's local time."""
    s = str(t)
    return s[:10], int(s[11:13]) * 60 + int(s[14:16]) + tf_min if len(s) >= 16 else 0


class Engine:
    """Trades one position at a time, long or short (or either, when a strategy trades both ways), with stops,
    targets, trailing stops, time exits and optional intraday session rules."""

    def __init__(self, strategy, lot: float = 1, state: dict | None = None, cost_kind: str = "flat"):
        # `lot` is the quantity step: 1 share, an F&O lot of 65, or 0.0001 of a coin
        self.s, self.r = strategy, strategy.risk
        side = getattr(strategy, "side", "long")
        self.sides = [1, -1] if side == "both" else [-1] if side == "short" else [1]
        self.dir = self.sides[0]
        self.qty_step = float(lot) if lot and lot > 0 else 1.0
        self.sess = getattr(strategy, "session", None)
        self.tf_min = TF_MIN.get(strategy.tf, 1440)
        self.intraday = self.tf_min < 1440 and self.sess is not None
        sess = self.sess
        self.t_start = _minutes(sess.start) if sess else None
        self.t_end = _minutes(sess.end) if sess else None
        self.t_sq = _minutes(sess.squareoff) if sess and self.intraday else None
        product = getattr(strategy, "product", "auto")
        if cost_kind == "in_eq" and (product == "intraday" or (product == "auto" and self.t_sq is not None)):
            cost_kind = "in_eq_mis"
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
        # the trading day, for session limits
        self.day, self.day_trades, self.day_pnl, self.cool, self.halted = None, 0, 0.0, 0, False
        self.gate = None          # a portfolio can veto new trades (no free slot, daily cap hit)
        self.veto = None          # live only: checked once the entry rules hold (a wide spread, too cheap to trade)
        if state:
            self.load(state)

    # --- persistence for live sessions ---
    def dump(self) -> dict:
        return {"cash": self.cash, "qty": self.qty, "entry": self.entry, "sl": self.sl,
                "tg": None if math.isinf(self.tg) else self.tg, "entry_t": self.entry_t,
                "entry_cost": self.entry_cost, "cost_items": self.cost_items,
                "init_sl": self.init_sl, "best": self.best, "held": self.held, "dir": self.dir,
                "day": self.day, "day_trades": self.day_trades, "day_pnl": self.day_pnl, "cool": self.cool,
                "halted": self.halted, "trades": self.trades[-500:], "events": self.events[-1000:]}

    def load(self, st: dict):
        self.cash, self.qty, self.entry, self.sl = st["cash"], st["qty"], st["entry"], st["sl"]
        self.tg = math.inf if st.get("tg") is None else st["tg"]
        self.entry_t = st.get("entry_t")
        self.entry_cost = st.get("entry_cost", 0.0)
        self.cost_items = st.get("cost_items", {})
        self.init_sl = st.get("init_sl", self.sl)
        self.best = st.get("best", self.entry)
        self.held = st.get("held", 0)
        self.dir = st.get("dir", self.dir)
        self.day, self.day_trades = st.get("day"), st.get("day_trades", 0)
        self.day_pnl, self.cool, self.halted = st.get("day_pnl", 0.0), st.get("cool", 0), st.get("halted", False)
        self.trades, self.events = st.get("trades", []), st.get("events", [])

    def _pay(self, side: str, qty: float, px: float) -> float:
        items = C.order_costs(self.kind, side, qty, px, self.r.brokerage)
        for k, v in items.items():
            self.cost_items[k] = self.cost_items.get(k, 0.0) + v
        return C.total(items)

    def _slip(self, q: float, fill: float, px: float):
        """Slippage is in the fill price, not a charge; it's counted here so the cost breakdown can show it."""
        if q and fill != px:
            self.cost_items["slippage"] = self.cost_items.get("slippage", 0.0) + abs(fill - px) * q

    def equity(self, px: float) -> float:
        return self.cash + self.dir * self.qty * px

    def _rules(self, d: int, exit: bool) -> list:
        """Entry or exit rules for a direction. A one-way strategy keeps its rules in entry/exit."""
        s = self.s
        if d == -1 and len(self.sides) == 2:
            return s.shortExit if exit else s.shortEntry
        return s.exit if exit else s.entry

    def _hit(self, conds: list, ctx: Ctx, i: int) -> bool:
        if not conds:
            return False
        join = self.s.entryJoin
        if join == "score":
            got = sum((c.w or 1) for c in conds if eval_cond(ctx, c, i))
            need = self.s.minScore or sum((c.w or 1) for c in conds)
            return got >= need
        checks = (eval_cond(ctx, c, i) for c in conds)
        return any(checks) if join == "any" else all(checks)

    def _stop_distance(self, bars: list[dict], ctx: Ctx, i: int, px: float, d: int) -> float:
        """How far the stop sits from the entry price, in price points (0 = no stop)."""
        r = self.r
        if r.sl <= 0:
            return px * r.trail / 100 if r.trail > 0 else 0.0
        if r.stopType == "points":
            return r.sl
        if r.stopType == "atr":
            from ..models import Ref
            a = ctx.val(Ref(t="atr", p=14), i)
            return r.sl * a if a else px * 0.01
        if r.stopType == "swing":
            n = max(1, int(r.sl))
            window = bars[max(0, i - n + 1): i + 1]
            level = min(b["l"] for b in window) if d == 1 else max(b["h"] for b in window)
            return max(d * (px - level), px * 0.0005)   # at least 0.05%, so a flat candle can't mean no risk
        return px * r.sl / 100

    def _exit_price(self, b: dict) -> tuple[float | None, str]:
        """Where an open trade closes on this candle, checked in order: stop, target, time."""
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

    def _close(self, b: dict, px: float, why: str) -> dict:
        d = self.dir
        close_side = "sell" if d == 1 else "buy"
        fill = px * (1 - self.r.slippage / 100 * d)      # selling a long fills lower, buying back a short fills higher
        self._slip(self.qty, fill, px)
        px = fill
        exit_cost = self._pay(close_side, self.qty, px)
        trade_costs = self.entry_cost + exit_cost
        pnl = d * self.qty * (px - self.entry) - trade_costs
        self.cash += d * self.qty * px - exit_cost
        self.trades.append({"entry_t": self.entry_t, "exit_t": b["t"], "entry": self.entry, "exit": px,
                            "qty": self.qty, "pnl": pnl, "costs": trade_costs, "side": "short" if d == -1 else "long",
                            "ret": pnl / (self.qty * self.entry) * 100 if self.qty and self.entry else 0.0, "why": why})
        ev = {"t": b["t"], "side": close_side, "px": px, "qty": self.qty, "why": why, "pnl": pnl}
        self.events.append(ev)
        self.qty = 0
        self.day_pnl += pnl
        self.cool = self.sess.cooldown if self.sess else 0
        if self._loss_cap() and self.day_pnl <= -self._loss_cap():
            self.halted = True
        return ev

    def _loss_cap(self) -> float:
        return self.r.capital * self.sess.dailyLossPct / 100 if self.sess and self.sess.dailyLossPct else 0.0

    def step(self, bars: list[dict], ctx: Ctx, i: int) -> list[dict]:
        b, r = bars[i], self.r
        date, closes_at = bar_clock(b["t"], self.tf_min)
        if date != self.day:
            self.day, self.day_trades, self.day_pnl, self.halted = date, 0, 0.0, False
        new = []
        if self.qty > 0:
            self.held += 1
            d = self.dir
            px, why = self._exit_price(b)
            if px is None and self.t_sq is not None:
                if str(self.entry_t)[:10] != date:          # a gap in the data: close at this candle's open
                    px, why = b["o"], "Square-off"
                elif closes_at >= self.t_sq:
                    px, why = b["c"], "Square-off"
            if px is None and self._hit_exit(ctx, i):
                px, why = b["c"], "Exit rule"
            cap = self._loss_cap()
            if px is None and cap and self.day_pnl + d * self.qty * (b["c"] - self.entry) - self.entry_cost <= -cap:
                px, why = b["c"], "Daily loss cap"
            if px is not None:
                new.append(self._close(b, px, why))
            elif r.trail > 0:
                # ratchet the trailing stop with the best price so far; it applies from the next candle
                t = r.trail / 100
                if d == 1:
                    self.best = max(self.best, b["h"])
                    self.sl = max(self.sl, self.best * (1 - t))
                else:
                    self.best = min(self.best, b["l"])
                    self.sl = min(self.sl, self.best * (1 + t)) if self.sl > 0 else self.best * (1 + t)
            return new
        if self.cool > 0:
            self.cool -= 1
            return new
        return self._try_enter(bars, ctx, i, closes_at)

    def _try_enter(self, bars: list[dict], ctx: Ctx, i: int, closes_at: int) -> list[dict]:
        if self.intraday and not self._may_enter(closes_at):
            return []
        if self.gate is not None and not self.gate():
            return []
        slip, brok = self.r.slippage / 100, self.r.brokerage
        for d in self.sides:
            if not self._hit(self._rules(d, exit=False), ctx, i):
                continue
            if self.veto is not None and self.veto():
                return []
            ev = self._open(bars, ctx, i, d, slip, brok)
            return [ev] if ev else []
        return []

    def enter_now(self, bars: list[dict], ctx: Ctx, i: int) -> list[dict]:
        """Live only: check the entry rules on the candle that is still forming (its close is the latest
        price) and enter at once if they hold. Exits still wait for the candle to close, as in a backtest."""
        if self.qty > 0 or self.cool > 0:
            return []
        date, closes_at = bar_clock(bars[i]["t"], self.tf_min)
        if date != self.day:
            self.day, self.day_trades, self.day_pnl, self.halted = date, 0, 0.0, False
        return self._try_enter(bars, ctx, i, closes_at)

    # --- paper orders placed by hand (the AI assistant's paper tools), live only ---
    def manual_cost(self, side: str, q: float, px: float) -> float:
        """What opening `q` at `px` takes from cash: the fill after slippage plus the order's charges."""
        d = 1 if side == "buy" else -1
        fill = px * (1 + self.r.slippage / 100 * d)
        return q * fill + C.total(C.order_costs(self.kind, side, q, fill, self.r.brokerage))

    def open_manual(self, t: str, px: float, d: int, q: float, why: str) -> dict:
        """Open a position of `q` at the latest price `px`, with the same slippage and charges as a rule's entry. No
        stop or target is set; the strategy's exit rules, time exit and square-off still apply from the next candle."""
        open_side = "buy" if d == 1 else "sell"
        fill = px * (1 + self.r.slippage / 100 * d)
        self._slip(q, fill, px)
        px = fill
        self.dir = d
        self.entry_cost = self._pay(open_side, q, px)
        self.cash -= d * q * px + self.entry_cost
        self.qty, self.entry, self.entry_t, self.held, self.best = q, px, t, 0, px
        self.sl = self.init_sl = 0.0
        self.tg = math.inf
        self.day_trades += 1
        ev = {"t": t, "side": open_side, "px": px, "qty": q, "why": why}
        self.events.append(ev)
        return ev

    def close_manual(self, t: str, px: float, why: str) -> dict:
        """Close the open position at the latest price `px`, as an exit rule would."""
        return self._close({"t": t}, px, why)

    def _hit_exit(self, ctx: Ctx, i: int) -> bool:
        return any(eval_cond(ctx, c, i) for c in self._rules(self.dir, exit=True))

    def _may_enter(self, closes_at: int) -> bool:
        s = self.sess
        if self.halted or (s.maxTradesDay and self.day_trades >= s.maxTradesDay):
            return False
        if self.t_start is not None and closes_at < self.t_start:
            return False
        if self.t_end is not None and closes_at > self.t_end:
            return False
        return not (self.t_sq is not None and closes_at >= self.t_sq)

    def _open(self, bars: list[dict], ctx: Ctx, i: int, d: int, slip: float, brok: float) -> dict | None:
        b, r = bars[i], self.r
        open_side = "buy" if d == 1 else "sell"
        px = b["c"] * (1 + slip * d)
        dist = self._stop_distance(bars, ctx, i, px, d)
        if r.sizing == "capital":
            per = r.perTrade or r.capital * r.maxAlloc / 100
            cap = min(per, max(self.equity(b["c"]), 0)) * r.leverage       # margin can't exceed what you have
            q = cap / px
        else:
            cap = self.cash * r.maxAlloc / 100
            # the stated risk is a share of the capital ("1% of Rs5,00,000, that is Rs5,000 if the stop loss is hit"): a
            # stop hit never costs more, however much the account has grown (11 units x 2% x Rs24,187 = Rs5,321 did,
            # from 1% of the grown account); after losses the smaller account's share is risked
            q = min(self.cash, r.capital) * r.riskPct / 100 / dist if dist > 0 else math.inf
            q = min(q, (cap - brok) / px)
        q = C.floor_to(q, self.qty_step)
        # percentage costs (STT, exchange fees) must fit in the budget too
        while q > 0 and q * px + C.total(C.order_costs(self.kind, open_side, q, px, brok)) > cap:
            q = C.floor_to(q - max(self.qty_step, q * 0.002), self.qty_step)
        if q <= 0:
            self.skipped_size += 1
            return None
        self.dir = d
        self._slip(q, px, b["c"])
        self.entry_cost = self._pay(open_side, q, px)
        self.cash -= d * q * px + self.entry_cost
        self.qty, self.entry, self.entry_t, self.held, self.best = q, px, b["t"], 0, px
        self.sl = px - d * dist if dist > 0 else 0.0
        self.init_sl = self.sl
        if r.tgt > 0:
            reach = r.tgt if r.tgtType == "points" else r.tgt * dist if r.tgtType == "r" else px * r.tgt / 100
            self.tg = px + d * reach if reach > 0 else math.inf
        else:
            self.tg = math.inf
        self.day_trades += 1
        ev = {"t": b["t"], "side": open_side, "px": px, "qty": q, "why": "Entry rule" if d == 1 else "Short entry"}
        self.events.append(ev)
        return ev


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
    for c in strategy.all_conds():
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
    # where each trade sits in `equity`: [index before its entry, index of its exit (None while open), entry bar]
    eng.spans = []
    for i in range(start + 1, end):
        was, closed = eng.qty > 0, len(eng.trades)
        eng.step(bars, ctx, i)
        equity.append(eng.equity(bars[i]["c"]))
        j = len(equity) - 1
        if was and len(eng.trades) > closed:
            eng.spans[-1][1] = j
        if eng.qty > 0 and (not was or len(eng.trades) > closed):
            eng.spans.append([j - 1, None, i])
    return eng, equity


def backtest(bars: list[dict], strategy, start: int, lot: float = 1, cost_kind: str = "flat") -> dict:
    tf = strategy.tf
    ctx = Ctx(bars, intraday=tf != "1d")
    eng, equity = simulate(bars, strategy, start, lot=lot, cost_kind=cost_kind, ctx=ctx)
    cap = strategy.risk.capital
    view = bars[start:]
    open_trade = None
    if eng.qty > 0:
        open_trade = open_position(eng, bars[-1]["c"])
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
    entries = [*strategy.entry, *(strategy.shortEntry if strategy.side == "both" else [])]
    ent = [[eval_cond(ctx, c, i) for i in rng] for c in entries]
    comb = [eng._hit(entries if strategy.side != "both" else strategy.entry, ctx, i)
            or (strategy.side == "both" and eng._hit(strategy.shortEntry, ctx, i)) for i in rng] if ent else []
    diagnostics = {
        "entry": [{"text": cond_text(c), "true_on": sum(v), "never_computed": _never(ctx, c, start)} for c, v in zip(entries, ent)],
        "entry_join": strategy.entryJoin,
        "all_true_on": sum(comb),
        "exit": [{"text": cond_text(c), "true_on": sum(eval_cond(ctx, c, i) for i in rng)}
                 for c in [*strategy.exit, *(strategy.shortExit if strategy.side == "both" else [])]],
        "skipped_size": eng.skipped_size,
        "candles": len(rng),
    }
    split = split_at(start, len(bars))
    for t, (a, b, i) in zip([*eng.trades, *([open_trade] if open_trade else [])], eng.spans):
        t["part"] = "built" if i <= split else "unseen"
        if i <= split and (b is None or b + start > split):
            t["spans_split"] = True        # opened before the split and closed after it: it counts with the built part
    return {
        "diagnostics": diagnostics,
        "_split": split,
        # each trade's day-by-day changes in account value, for the bad-luck drawdown check
        "_paths": [np.diff(np.asarray(equity[a:(len(equity) - 1 if b is None else b) + 1], dtype=float)) for a, b, _ in eng.spans],
        "bars": [{"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"]} for b in view],
        "equity": clean(equity), "buy_hold": clean(bh), "drawdown": clean(st.pop("dd")),
        "stats": {**st, "buy_hold_ret": (view[-1]["c"] / first - 1) * 100, "skipped_size": eng.skipped_size},
        "trades": eng.trades, "open_trade": open_trade, "events": eng.events,
        "overlays": overlays, "oscillators": osc, "periods": periods[-60:],
        "costs": cost_summary(eng, cost_kind, equity[-1] - cap),
    }


def open_position(eng: Engine, last: float) -> dict:
    """The trade still open at the end, valued at the last close. Its P&L is after the entry's costs, already paid,
    so the trade list adds up to the account's change; closing it would cost the exit's charges too."""
    pnl = eng.dir * eng.qty * (last - eng.entry) - eng.entry_cost
    return {"entry_t": eng.entry_t, "exit_t": None, "entry": eng.entry, "exit": last, "qty": eng.qty, "pnl": pnl,
            "costs": eng.entry_cost, "ret": pnl / (eng.qty * eng.entry) * 100 if eng.entry else 0.0,
            "side": "short" if eng.dir == -1 else "long", "why": "Still open"}


SPLIT = 0.7     # the unseen-data check: the first 70% of the test is "built on", the rest is unseen


def split_at(start: int, n: int) -> int:
    """The bar where the unseen part starts: trades entered after it are unseen."""
    return start + int((n - 1 - start) * SPLIT)


def cost_summary(eng: Engine, cost_kind: str, net_pnl: float) -> dict:
    """Profit before costs, each cost line, a tax estimate, and what is left."""
    paid = sum(eng.cost_items.values())
    tax = C.tax_estimate(cost_kind, eng.trades)
    kept = net_pnl - (tax["amount"] or 0.0)
    return {"gross_pnl": round(net_pnl + paid, 2), "total": round(paid, 2), "items": C.breakdown(eng.cost_items),
            "net_pnl": round(net_pnl, 2), "tax": tax, "kept": round(kept, 2)}
