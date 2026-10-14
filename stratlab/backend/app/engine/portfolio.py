"""Run one strategy across a group of instruments with one pot of capital.

Every instrument has its own engine (its own position, stops and session limits), and they step
through time together. A new trade only opens when a position slot is free (max positions at
once), and the daily loss cap applies to the whole portfolio: when the day's loss across every
position reaches it, everything is closed and nothing new opens until the next day. The capital is one account:
each new trade is sized from the whole portfolio's value and can only use the cash the open positions leave free."""
import copy
import math
from datetime import datetime

from . import costs as C
from .core import PER_YEAR, Ctx, Engine, clean, open_position, span_years, stats, write_off


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
    state = {"halted": False, "emptied_on": None, "free0": None, "value0": None, "k": None, "stepped": set()}
    lev = strategy.risk.leverage

    def free_slot(at_open: bool = False) -> bool:
        used = sum(1 for b in books if b["eng"].qty > 0)
        if at_open:
            # a member not yet stepped whose exit fills at this same open has left its slot by then, whatever the order
            used -= len(_leaving_at_open(books, state))
            # a fill at the candle's open: a slot freed later in this candle (a stop hit) was still taken at its open
            used += sum(1 for b in books if b["eng"].qty == 0 and _closed_after_open(b, state["k"]))
        return not state["halted"] and not state["emptied_on"] and used < max_open

    def funds() -> tuple[float, float]:
        """The pot's value (open positions at their last close) and its cash not tied up in an open position.
        Each engine keeps its own books from `capital`; only what it has made or lost counts toward the pot."""
        value = cap_total + sum(_gain(b) for b in books) if state["value0"] is None else state["value0"]
        leaving = _leaving_cash(books, state, lev)
        free = _free(books, cap_total, lev) + leaving
        if state.get("free0") is not None:
            # entries fill at the candle's open: they can use what was free then and what exits at that open freed, never
            # what a position closed later in the same candle gives back (three Rs50,000 slots opened on Rs1,00,000)
            free = min(free, state["free0"] + leaving + _freed_at_open(books, state["k"], lev) - _spent_at(books, state["k"], lev))
        return value, free

    for b in books:
        b["eng"].gate = free_slot
        b["eng"].funds = funds

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
        state["free0"], state["k"], state["stepped"] = _free(books, cap_total, lev), k, set()
        # entries fill at the open: the pot is valued at the last close, not at the close of instruments already stepped
        state["value0"] = cap_total + sum(_gain(b) for b in books)
        for b in books:
            i = b["idx"].get(k)
            if i is None:
                continue
            if not state["emptied_on"]:
                b["eng"].step(b["bars"], b["ctx"], i)
            state["stepped"].add(id(b))
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
        if not state["emptied_on"] and cap_total + sum(_gain(b) for b in books) <= 0:
            _empty(books, state, k, cap_total)
        most_open = max(most_open, sum(1 for b in books if b["eng"].qty > 0))
        equity.append(max(cap_total + sum(_gain(b) for b in books), 0.0))
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
    st = stats(equity, trades, cap_total, PER_YEAR[strategy.tf], span_years(times[0], times[-1]) if times else None)
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
        # a position still open at the end counts in its stock's P&L at its value on the last close, as in the trade list,
        # so the members add up to the total (R11C-014: KOTAKBANK's open +25,549 was left out); `open_pnl` says how much
        still = _open_pnl(b)
        members.append({"symbol": b["inst"].get("symbol"), "id": b["inst"].get("id"), "trades": len(ts),
                        "pnl": round(sum(t["pnl"] for t in ts) + still, 2),
                        "win": round(sum(t["pnl"] > 0 for t in ts) / len(ts) * 100, 1) if ts else None,
                        "open": 1 if b["eng"].qty > 0 and b["last"] is not None else 0, "open_pnl": round(still, 2),
                        "buy_hold": round((b["bars"][b["last"]]["c"] / b["bars"][b["first"]]["c"] - 1) * 100, 2) if b["first"] is not None else None})
    members.sort(key=lambda m: -m["pnl"])
    return {
        "times": times, "equity": clean(equity), "buy_hold": clean(hold), "drawdown": clean(st.pop("dd")),
        "stats": {**st, "buy_hold_ret": (hold[-1] / cap_total - 1) * 100,
                  "emptied_on": state["emptied_on"] or next((b["eng"].emptied_on for b in books if b["eng"].emptied_on), None)},
        "trades": trades, "open_trades": open_trades, "members": members,
        "costs": {"gross_pnl": round(net + paid, 2), "total": round(paid, 2), "items": C.breakdown(items),
                  "net_pnl": round(net, 2), "tax": tax, "kept": round(net - (tax["amount"] or 0.0), 2)},
        "most_open": most_open,
        # day-by-day changes in account value over each stretch with a position open, for the bad-luck drawdown check
        "_paths": [[b2 - a2 for a2, b2 in zip(path[a:b], path[a + 1:b + 1])] for path in [[cap_total, *equity]] for a, b in episodes],
    }


def _empty(books: list[dict], state: dict, k: datetime, cap_total: float) -> None:
    """The whole account is worth nothing (each position is sized on the full capital, so the group can hold more than
    the account has): everything is closed at the last close, the loss is held to what the account had (-100%), and
    nothing opens after this day (R13S-001: a group's run showed -352.6% and a chart down to -Rs10 lakh)."""
    for b in books:
        e = b["eng"]
        if e.qty > 0 and b["last"] is not None:
            bar = b["bars"][b["last"]]
            e._close(bar, bar["c"], "Account emptied")
    state["emptied_on"] = k.date().isoformat()
    pairs = sorted(((t, b["eng"]) for b in books for t in b["eng"].trades), key=lambda p: str(p[0]["exit_t"]))
    total = cap_total + sum(_gain(b) for b in books)
    if total < 0:
        write_off([t for t, _ in pairs], -total, [e for _, e in pairs])


def _gain(b: dict) -> float:
    """What this instrument's engine has made or lost so far, open trade included."""
    e = b["eng"]
    if b["last"] is None:
        return 0.0
    return e.equity(b["bars"][b["last"]]["c"]) - e.r.capital


def _cash(e: Engine) -> float:
    """What this instrument's trades have added to or taken from the pot's cash: closed P&L less the open
    trade's entry charges (its money still counts as the pot's, tied up in the position)."""
    return e.cash + e.dir * e.qty * e.entry - e.r.capital


def _free(books: list[dict], cap_total: float, lev: float) -> float:
    """The pot's cash not tied up in an open position (a position ties up its value over the leverage)."""
    cash = cap_total + sum(_cash(b["eng"]) for b in books)
    return cash - sum(b["eng"].qty * b["eng"].entry for b in books) / lev


def _spent_at(books: list[dict], k: datetime, lev: float) -> float:
    """What the positions opened at candle `k` took from the free cash, those already closed again in it included (their
    charges counted whole: never less than they took)."""
    out = 0.0
    for b in books:
        e = b["eng"]
        if e.qty > 0 and e.entry_t is not None and _key(e.entry_t) == k:
            out += e.qty * e.entry / lev + e.entry_cost
        for t in reversed(e.trades):
            if _key(t["exit_t"]) != k:
                break
            if _key(t["entry_t"]) == k:
                out += t["qty"] * t["entry"] / lev + t["costs"]
    return out


def _leaving_at_open(books: list[dict], state: dict) -> list[dict]:
    """Members not yet stepped in this candle whose open position certainly closes at its open."""
    out = []
    for b in books:
        i = b["idx"].get(state["k"])
        if i is not None and id(b) not in state["stepped"] and b["eng"].open_exit(b["bars"][i]):
            out.append(b)
    return out


def _leaving_cash(books: list[dict], state: dict, lev: float) -> float:
    """What those exits will give back to the free cash at the open: their margin plus their P&L there, after exit charges."""
    out = 0.0
    for b in _leaving_at_open(books, state):
        e, o = b["eng"], b["bars"][b["idx"][state["k"]]]["o"]
        fill = o * (1 - e.r.slippage / 100 * e.dir)
        side = "sell" if e.dir == 1 else "buy"
        cost = C.total(C.order_costs(e.kind, side, e.qty, fill, e.r.brokerage))
        out += e.qty * e.entry / lev + e.dir * e.qty * (fill - e.entry) - e.entry_cost - cost
    return out


def _at_open(b: dict, t: dict, o: float) -> bool:
    if "at_open" in t:
        return t["at_open"]
    d = -1 if t["side"] == "short" else 1
    return math.isclose(t["exit"], o * (1 - b["eng"].r.slippage / 100 * d), rel_tol=1e-9)


def _closed_after_open(b: dict, k: datetime) -> bool:
    """This instrument's latest trade closed in candle `k`, after its open (it held a slot at that open)."""
    i, ts = b["idx"].get(k), b["eng"].trades
    if i is None or not ts or _key(ts[-1]["exit_t"]) != k:
        return False
    return not _at_open(b, ts[-1], b["bars"][i]["o"])


def _freed_at_open(books: list[dict], k: datetime, lev: float) -> float:
    """What the trades closed at candle `k`'s open (an exit rule, a gap through the stop) gave back to the free cash, less
    their entry charges (already spent): never more than they really freed."""
    out = 0.0
    for b in books:
        i = b["idx"].get(k)
        if i is None:
            continue
        o = b["bars"][i]["o"]
        for t in reversed(b["eng"].trades):
            if _key(t["exit_t"]) != k:
                break
            if _at_open(b, t, o):
                out += t["qty"] * t["entry"] / lev + t["pnl"]
    return out


def _open_pnl(b: dict) -> float:
    e = b["eng"]
    if e.qty <= 0 or b["last"] is None:
        return 0.0
    return e.dir * e.qty * (b["bars"][b["last"]]["c"] - e.entry) - e.entry_cost
