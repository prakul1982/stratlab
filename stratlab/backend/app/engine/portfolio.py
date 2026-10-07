"""Run one strategy across a group of instruments with one pot of capital.

Every instrument has its own engine (its own position, stops and session limits), and they step
through time together. A new trade only opens when a position slot is free (max positions at
once), and the daily loss cap applies to the whole portfolio: when the day's loss across every
position reaches it, everything is closed and nothing new opens until the next day."""
import copy
from datetime import datetime

from . import costs as C
from .core import PER_YEAR, Ctx, Engine, clean, open_position, stats


def _key(t: str) -> datetime:
    return datetime.fromisoformat(str(t))


def run(datasets: list[dict], strategy, max_open: int, t_from: str | None = None, t_to: str | None = None) -> dict:
    """datasets: [{"inst", "bars", "start", "lot", "kind"}]. Trades candles after each dataset's warm-up,
    optionally only between t_from and t_to (ISO times, t_to exclusive)."""
    cap_total = strategy.risk.capital
    loss_cap = cap_total * strategy.session.dailyLossPct / 100 if strategy.session.dailyLossPct else 0.0
    each = copy.deepcopy(strategy)
    each.session.dailyLossPct = 0                  # the cap is the portfolio's, not each stock's
    lo, hi = (_key(t_from) if t_from else None), (_key(t_to) if t_to else None)

    books = []
    for d in datasets:
        bars = d["bars"]
        eng = Engine(each, d["lot"], cost_kind=d["kind"])
        idx = {}
        for i in range(d["start"] + 1, len(bars)):
            k = _key(bars[i]["t"])
            if (lo and k < lo) or (hi and k >= hi):
                continue
            idx[k] = i
        books.append({"inst": d["inst"], "bars": bars, "ctx": Ctx(bars, intraday=strategy.tf != "1d"), "eng": eng,
                      "idx": idx, "last": None, "first": None})
    timeline = sorted({k for b in books for k in b["idx"]})
    state = {"halted": False}

    def free_slot() -> bool:
        return not state["halted"] and sum(1 for b in books if b["eng"].qty > 0) < max_open

    for b in books:
        b["eng"].gate = free_slot

    equity, hold, times = [], [], []
    episodes: list[list] = []        # stretches with any position open: [index before, last index] in [capital, *equity]
    day, realised_at_open, most_open = None, 0.0, 0
    for k in timeline:
        was_open = any(b["eng"].qty > 0 for b in books)
        closed_before = sum(len(b["eng"].trades) for b in books)
        date = k.date()
        if date != day:
            day, state["halted"] = date, False
            realised_at_open = sum(t["pnl"] for b in books for t in b["eng"].trades)
        for b in books:
            i = b["idx"].get(k)
            if i is None:
                continue
            b["eng"].step(b["bars"], b["ctx"], i)
            b["last"] = i
            if b["first"] is None:
                b["first"] = i
        if loss_cap and not state["halted"]:
            realised = sum(t["pnl"] for b in books for t in b["eng"].trades) - realised_at_open
            open_pnl = sum(_open_pnl(b) for b in books)
            if realised + open_pnl <= -loss_cap:
                for b in books:
                    if b["eng"].qty > 0:
                        bar = b["bars"][b["last"]]
                        b["eng"]._close(bar, bar["c"], "Daily loss cap")
                state["halted"] = True
        most_open = max(most_open, sum(1 for b in books if b["eng"].qty > 0))
        equity.append(cap_total + sum(_gain(b) for b in books))
        j = len(equity)
        now_open = any(b["eng"].qty > 0 for b in books)
        traded = now_open or sum(len(b["eng"].trades) for b in books) > closed_before
        if traded and not was_open:
            episodes.append([j - 1, j])
        elif was_open:
            episodes[-1][1] = j
        started = [b for b in books if b["first"] is not None]
        hold.append(cap_total * sum(b["bars"][b["last"]]["c"] / b["bars"][b["first"]]["c"] for b in started) / len(started)
                    if started else cap_total)
        times.append(k.isoformat())

    trades = sorted(({**t, "symbol": b["inst"].get("symbol")} for b in books for t in b["eng"].trades), key=lambda t: t["exit_t"])
    open_trades = []
    for b in books:
        e = b["eng"]
        if e.qty > 0 and b["last"] is not None:
            px = b["bars"][b["last"]]["c"]
            open_trades.append({"symbol": b["inst"].get("symbol"), **open_position(e, px)})
    if not equity:
        equity, hold, times = [cap_total], [cap_total], []
    st = stats(equity, trades, cap_total, PER_YEAR[strategy.tf])
    items: dict[str, float] = {}
    for b in books:
        for name, v in b["eng"].cost_items.items():
            items[name] = items.get(name, 0.0) + v
    paid = sum(items.values())
    kind = datasets[0]["kind"] if datasets else "flat"
    tax = C.tax_estimate(books[0]["eng"].kind if books else kind, trades)
    net = equity[-1] - cap_total
    members = []
    for b in books:
        ts = b["eng"].trades
        members.append({"symbol": b["inst"].get("symbol"), "id": b["inst"].get("id"), "trades": len(ts),
                        "pnl": round(sum(t["pnl"] for t in ts), 2), "win": round(sum(t["pnl"] > 0 for t in ts) / len(ts) * 100, 1) if ts else None,
                        "buy_hold": round((b["bars"][b["last"]]["c"] / b["bars"][b["first"]]["c"] - 1) * 100, 2) if b["first"] is not None else None})
    members.sort(key=lambda m: -m["pnl"])
    return {
        "times": times, "equity": clean(equity), "buy_hold": clean(hold), "drawdown": clean(st.pop("dd")),
        "stats": {**st, "buy_hold_ret": (hold[-1] / cap_total - 1) * 100},
        "trades": trades, "open_trades": open_trades, "members": members,
        "costs": {"gross_pnl": round(net + paid, 2), "total": round(paid, 2), "items": C.breakdown(items),
                  "net_pnl": round(net, 2), "tax": tax, "kept": round(net - (tax["amount"] or 0.0), 2)},
        "most_open": most_open,
        # day-by-day changes in account value over each stretch with a position open, for the bad-luck drawdown check
        "_paths": [[b2 - a2 for a2, b2 in zip(path[a:b], path[a + 1:b + 1])] for path in [[cap_total, *equity]] for a, b in episodes],
    }


def _gain(b: dict) -> float:
    """What this instrument's engine has made or lost so far, open trade included."""
    e = b["eng"]
    if b["last"] is None:
        return 0.0
    return e.equity(b["bars"][b["last"]]["c"]) - e.r.capital


def _open_pnl(b: dict) -> float:
    e = b["eng"]
    if e.qty <= 0 or b["last"] is None:
        return 0.0
    return e.dir * e.qty * (b["bars"][b["last"]]["c"] - e.entry) - e.entry_cost
