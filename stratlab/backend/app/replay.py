"""Chart replay practice: a past stretch of candles shown one at a time on StratLab's own price chart, with practice
orders (long, short, flat, a stop and a target) filled against those candles and charged at the published rates
(engine/costs.py). A finished session goes into the trade journal as practice trades.

How orders fill, the same here and in the page's live display (frontend/src/lib/replay.ts, checked against this file
by tests/test_replay.py and unit/replay.test.mjs):
- an order placed on candle i (the last one showing) fills at that candle's close;
- a stop or target placed on candle i works from candle i+1: a long's stop fills when a candle's low reaches it, at
  the stop or the candle's open if it opened beyond it (a gap), and its target when the high reaches it, at the
  target or a better open; a short's the other way round. When one candle reaches both, the stop is taken first;
- one position at a time, long or short: adding to it averages the entry, an order the other way reduces it, and one
  bigger than the position closes it and opens the rest the other way (stops and targets are cleared when it flips);
- each run from flat to flat is one trade; its charges are every fill's at the published rates, intraday rates for
  Indian shares when it opened and closed on the same day;
- what is still open when the session ends is closed at the last candle shown ("End of replay").

A historical simulation, labelled as one: facts about practice trades, never advice. Sessions are kept per user in
app_settings (replay:<uid>) until finished or thrown away."""
import json
import math
import random
import secrets
from datetime import date, datetime, timedelta, timezone

from . import db
from .engine import costs as C

KEY = "replay:"
TFS = ("5m", "15m", "1h", "1d")
CONTEXT = {"5m": 150, "15m": 150, "1h": 150, "1d": 200}      # candles shown before the start, to read the chart
PLAY = {"5m": 375, "15m": 300, "1h": 300, "1d": 250}         # candles to step through after it
MIN_PLAY = 20
PER_DAY = {"5m": 75, "15m": 25, "1h": 7, "1d": 1}
MAX_OPEN = 3                         # unfinished sessions kept per user; the oldest goes when a fourth starts
KEEP_DAYS = 7                        # an unfinished session older than this is dropped
MAX_ORDERS = 500
ACTIONS = ("long", "short", "flat", "stop", "target", "cancel_stop", "cancel_target")
EPS = 1e-9
HIDDEN_BASE = date(2000, 1, 3)       # a Monday: hidden sessions' candles are dated from here, one trading day at a time
NOTE = ("A historical simulation on past candles: practice orders fill at a candle's close, stops and targets on the "
        "candles after, with charges at today's published rates. Not a record of real trades, and not advice.")


class ReplayError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


# ---------- which candles ----------
def cost_kind(inst: dict) -> str:
    """The cost model for practice fills. An index can't be traded itself, so it has no charges."""
    return "flat" if inst.get("type") == "INDEX" else C.kind_of(inst)


def qty_step(inst: dict) -> float:
    """Shares in ones, F&O in lots, coins in their own step (the same as paper trading)."""
    return float(inst.get("step") or (inst.get("lot", 1) if inst.get("fno") else 1) or 1)


def days_back(tf: str, start: date, today: date) -> int:
    """Calendar days of history to read so the window holds the context candles before `start` and the candles to play."""
    ctx_days = math.ceil(CONTEXT[tf] / PER_DAY[tf] * 7 / 5) + 10
    return (today - start).days + ctx_days


def random_start(tf: str, max_days: int, today: date, rng: random.Random) -> date:
    """A day far enough back that the candles to play are all in the past, and near enough that the history the market
    keeps for this candle size still covers the context before it."""
    play_days = math.ceil(PLAY[tf] / PER_DAY[tf] * 7 / 5) + 3
    ctx_days = math.ceil(CONTEXT[tf] / PER_DAY[tf] * 7 / 5) + 10
    latest = play_days
    earliest = max(latest + 1, min(max_days - ctx_days - 5, 3 * 365 if tf == "1d" else max_days))
    return today - timedelta(days=rng.randint(latest, earliest))


def window(bars: list[dict], tf: str, start: date) -> tuple[list[dict], int]:
    """(candles to send, the index of the first one to play): up to CONTEXT[tf] before `start` and PLAY[tf] from it."""
    bars = [b for b in bars if _bar_ok(b)]
    first = next((i for i, b in enumerate(bars) if str(b["t"])[:10] >= start.isoformat()), None)
    if first is None or len(bars) - first < MIN_PLAY:
        raise ReplayError("too_recent", "There aren't enough candles after that date to replay. Pick an earlier one.")
    if first < 30:
        raise ReplayError("too_early", "There isn't enough history before that date to show. Pick a later one, or a bigger candle.")
    lo = max(0, first - CONTEXT[tf])
    out = [{k: b[k] for k in ("t", "o", "h", "l", "c", "v") if k in b} for b in bars[lo:first + PLAY[tf]]]
    return out, first - lo


def _bar_ok(b) -> bool:
    try:
        return (isinstance(b, dict) and isinstance(b.get("t"), str) and all(math.isfinite(float(b[k])) and float(b[k]) > 0 for k in "ohlc"))
    except (KeyError, TypeError, ValueError):
        return False


def mask(bars: list[dict]) -> list[dict]:
    """The candles with their dates hidden: each trading day becomes the next weekday from 3 Jan 2000, times of day
    kept. Prices are the real ones."""
    days: dict[str, str] = {}
    d = HIDDEN_BASE
    out = []
    for b in bars:
        t = str(b["t"])
        day = t[:10]
        if day not in days:
            days[day] = d.isoformat()
            d += timedelta(days=3 if d.weekday() == 4 else 1)
        out.append({**b, "t": days[day] + t[10:]})
    return out


# ---------- the simulation ----------
def _costs(kind: str, fills: list[dict], brokerage: float, intraday: bool) -> float:
    k = "in_eq_mis" if kind == "in_eq" and intraday else kind
    if k == "flat":
        return 0.0
    return sum(C.total(C.order_costs(k, f["side"], f["qty"], f["px"], brokerage)) for f in fills)


def check_orders(orders, first: int, cursor: int) -> list[dict]:
    """The orders as sent, checked: each {i, action, qty?, price?} on a shown candle, in order. Raises ReplayError."""
    if not isinstance(orders, list) or len(orders) > MAX_ORDERS:
        raise ReplayError("bad_orders", f"Up to {MAX_ORDERS} orders a session.")
    out, last = [], first - 1
    for o in orders:
        if not isinstance(o, dict) or o.get("action") not in ACTIONS:
            raise ReplayError("bad_orders", "An order couldn't be read.")
        i = o.get("i")
        if not isinstance(i, int) or isinstance(i, bool) or i < first - 1 or i > cursor or i < last:
            raise ReplayError("bad_orders", "An order is on a candle that wasn't showing.")
        last = i
        row = {"i": i, "action": o["action"]}
        if o["action"] in ("long", "short"):
            q = o.get("qty")
            if not _pos_num(q) or q > 1e9:
                raise ReplayError("bad_orders", "An order's quantity couldn't be read.")
            row["qty"] = float(q)
        if o["action"] in ("stop", "target"):
            p = o.get("price")
            if not _pos_num(p) or p > 1e12:
                raise ReplayError("bad_orders", "A stop or target price couldn't be read.")
            row["price"] = float(p)
        out.append(row)
    return out


def _pos_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def simulate(bars: list[dict], orders: list[dict], first: int, cursor: int, kind: str, step: float = 1.0,
             brokerage: float = 0.0, close_at_end: bool = True) -> dict:
    """Run the orders over candles first-1 .. cursor. Returns {"trades", "fills", "position", "skipped"}: closed trades
    (oldest first), every fill, what's open at the cursor (unless closed at the end), and orders that did nothing (a
    stop with no position, a stop on the wrong side of the price, a quantity under one step)."""
    pos, avg = 0.0, 0.0
    stop = target = None
    ep: dict | None = None
    trades, fills, skipped = [], [], []
    by_bar: dict[int, list[dict]] = {}
    for o in orders:
        by_bar.setdefault(o["i"], []).append(o)

    def fill(j: int, side: str, q: float, px: float, why: str):
        nonlocal pos, avg, ep, stop, target
        sign = 1 if side == "buy" else -1
        f = {"i": j, "t": bars[j]["t"], "side": side, "qty": q, "px": px, "why": why}
        fills.append(f)
        left = q
        if pos * sign < 0:                                  # against the position: closes some or all of it
            c = min(left, abs(pos))
            ep["exits"].append({**f, "qty": c})
            pos += sign * c
            left -= c
            if abs(pos) <= EPS:
                pos = 0.0
                trades.append(_trade(bars, ep, kind, brokerage))
                ep, stop, target = None, None, None
        if left > EPS:                                      # with it, or the rest after a flip
            if ep is None:
                ep = {"sign": sign, "entries": [], "exits": []}
                avg = 0.0
            ep["entries"].append({**f, "qty": left})
            avg = (avg * abs(pos) + px * left) / (abs(pos) + left)
            pos += sign * left

    for j in range(first - 1, cursor + 1):
        b = bars[j]
        if pos and j >= first:                              # resting exits work from the candle after they're placed
            long = pos > 0
            px = why = None
            if stop is not None and stop["from"] <= j and (b["l"] <= stop["price"] if long else b["h"] >= stop["price"]):
                px, why = (min(b["o"], stop["price"]) if long else max(b["o"], stop["price"])), "Stop"
            elif target is not None and target["from"] <= j and (b["h"] >= target["price"] if long else b["l"] <= target["price"]):
                px, why = (max(b["o"], target["price"]) if long else min(b["o"], target["price"])), "Target"
            if px is not None:
                fill(j, "sell" if long else "buy", abs(pos), px, why)
        for o in by_bar.get(j, []):
            a, close = o["action"], b["c"]
            if a in ("long", "short"):
                q = C.floor_to(o["qty"], step)
                if q <= 0:
                    skipped.append({**o, "why": "Under one lot"})
                    continue
                fill(j, "buy" if a == "long" else "sell", float(q), close, "Long" if a == "long" else "Short")
            elif a == "flat":
                if pos:
                    fill(j, "sell" if pos > 0 else "buy", abs(pos), close, "Flat")
            elif a in ("stop", "target"):
                p = o["price"]
                wrong = (not pos or (a == "stop" and (p >= close if pos > 0 else p <= close))
                         or (a == "target" and (p <= close if pos > 0 else p >= close)))
                if wrong:
                    skipped.append({**o, "why": "No position" if not pos else "On the wrong side of the price"})
                    continue
                level = {"price": p, "from": j + 1}
                if a == "stop":
                    stop = level
                else:
                    target = level
            elif a == "cancel_stop":
                stop = None
            elif a == "cancel_target":
                target = None
    open_ = None
    if pos and close_at_end:
        fill(cursor, "sell" if pos > 0 else "buy", abs(pos), bars[cursor]["c"], "End of replay")
    elif pos:
        last = bars[cursor]["c"]
        open_ = {"side": "long" if pos > 0 else "short", "qty": abs(pos), "avg": avg, "mark": last,
                 "unrealised": (last - avg) * pos, "stop": stop["price"] if stop else None, "target": target["price"] if target else None}
    return {"trades": trades, "fills": fills, "position": open_, "skipped": skipped}


def _trade(bars: list[dict], ep: dict, kind: str, brokerage: float) -> dict:
    ins, outs, sign = ep["entries"], ep["exits"], ep["sign"]
    qty = sum(f["qty"] for f in ins)
    entry = sum(f["px"] * f["qty"] for f in ins) / qty
    exit_ = sum(f["px"] * f["qty"] for f in outs) / max(sum(f["qty"] for f in outs), EPS)
    first_t, last_t = str(ins[0]["t"]), str(outs[-1]["t"])
    intraday = first_t[:10] == last_t[:10]
    gross = sign * (exit_ - entry) * qty
    charges = _costs(kind, ins + outs, brokerage, intraday)
    return {"side": "long" if sign > 0 else "short", "qty": qty, "entry": entry, "exit": exit_, "entry_i": ins[0]["i"],
            "exit_i": outs[-1]["i"], "entry_t": first_t, "exit_t": last_t, "gross": gross, "charges": charges,
            "net": gross - charges, "why": outs[-1]["why"], "fills": len(ins) + len(outs)}


def summary(trades: list[dict]) -> dict:
    nets = [t["net"] for t in trades]
    return {"n": len(trades), "wins": sum(1 for v in nets if v > 0), "gross": round(sum(t["gross"] for t in trades), 2),
            "charges": round(sum(t["charges"] for t in trades), 2), "net": round(sum(nets), 2)}


# ---------- stored sessions ----------
def _key(uid: str) -> str:
    return KEY + uid


def load_all(uid: str) -> dict:
    """{rid: session} for the user's unfinished sessions, the stale ones dropped."""
    got = db.json_value(db.get_setting(_key(uid)), {})
    rows = got.get("sessions") if isinstance(got, dict) and isinstance(got.get("sessions"), dict) else {}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)).isoformat()
    return {k: v for k, v in rows.items() if isinstance(v, dict) and str(v.get("created", "")) >= cutoff and isinstance(v.get("bars"), list)}


def _save_all(uid: str, rows: dict):
    if rows:
        db.set_setting(_key(uid), json.dumps({"sessions": rows}, separators=(",", ":")))
    else:
        db.delete_setting(_key(uid))


def create(uid: str, inst: dict, tf: str, bars: list[dict], first: int, start: date, hidden: bool) -> dict:
    rows = load_all(uid)
    while len(rows) >= MAX_OPEN:
        rows.pop(min(rows, key=lambda k: rows[k]["created"]))
    rid = secrets.token_hex(8)
    keep = {k: inst.get(k) for k in ("id", "symbol", "name", "exchange", "type", "lot", "step", "fno", "market", "currency", "tz") if k in inst}
    rows[rid] = {"id": rid, "inst": keep, "tf": tf, "bars": bars, "first": first, "start": start.isoformat(), "hidden": hidden,
                 "created": datetime.now(timezone.utc).isoformat()}
    _save_all(uid, rows)
    return rows[rid]


def get(uid: str, rid: str) -> dict | None:
    return load_all(uid).get(rid) if isinstance(rid, str) and len(rid) <= 32 else None


def drop(uid: str, rid: str) -> bool:
    rows = load_all(uid)
    if rows.pop(rid, None) is None:
        return False
    _save_all(uid, rows)
    return True


def forget(uid: str):
    db.delete_setting(_key(uid))


def label(s: dict) -> str:
    """What the page calls a session: the symbol and start, or "Hidden" until it ends."""
    return "Hidden symbol and date" if s.get("hidden") else f"{s['inst'].get('symbol')} from {s['start']}"


def public(s: dict, brokerage: float) -> dict:
    """A session as the page gets it: hidden sessions without the symbol or real dates."""
    inst, hidden = s["inst"], s.get("hidden")
    kind = cost_kind(inst)
    return {"id": s["id"], "tf": s["tf"], "hidden": bool(hidden), "label": label(s),
            "symbol": None if hidden else inst.get("symbol"), "name": None if hidden else inst.get("name"),
            "currency": inst.get("currency") or "INR", "market": inst.get("market", "IN"),
            "bars": mask(s["bars"]) if hidden else s["bars"], "first": s["first"], "step": qty_step(inst),
            "fno": bool(inst.get("fno")), "kind": kind, "rates": rates(kind, brokerage), "brokerage": brokerage,
            "index": inst.get("type") == "INDEX", "created": s["created"], "note": NOTE}


def rates(kind: str, brokerage: float) -> dict:
    """The cost model as straight lines, for the page's running P&L: {kind: {"buy": share of value, "sell": share of
    value, "flat": per order}} for the instrument's kind (and intraday shares). Exact for India and crypto; the US
    per-share fee is folded in as a share of value, so the page's figure there is close and the saved one exact."""
    out = {}
    for k in ((kind, "in_eq_mis") if kind == "in_eq" else (kind,)):
        if k == "flat":
            out[k] = {"buy": 0.0, "sell": 0.0, "flat": 0.0}
            continue
        row = {}
        for side in ("buy", "sell"):
            flat = C.total(C.order_costs(k, side, 0.0, 0.0, brokerage))
            per = (C.total(C.order_costs(k, side, 1000.0, 1000.0, brokerage)) - flat) / 1e6
            row[side] = per
            row["flat"] = flat
        out[k] = row
    return out


# ---------- into the journal ----------
def journal_rows(s: dict, trades: list[dict]) -> list[dict]:
    """Practice trades in the journal's own shape (as trades added by hand), with the real symbol and dates."""
    from . import journal as J
    inst = s["inst"]
    seg = {"FUT": "fut", "CE": "opt", "PE": "opt"}.get(inst.get("type") or "", "eq")
    if inst.get("market") == "MCX":
        seg = "com"
    elif inst.get("market") == "CDS":
        seg = "cur"
    out = []
    for t in trades:
        ed, et = _split(t["entry_t"])
        xd, xt = _split(t["exit_t"])
        if s["tf"] == "1d":                                  # a daily candle's time is only its date
            et = xt = ""
        out.append({"id": "p" + secrets.token_hex(5), "sym": J.clean_symbol(inst.get("symbol") or "?"), "segment": seg,
                    "side": t["side"], "ed": ed, "et": et, "xd": xd, "xt": xt, "qty": round(t["qty"], 6),
                    "entry": round(t["entry"], 4), "exit": round(t["exit"], 4), "charges": round(t["charges"], 2),
                    "replay": s["id"], "tf": s["tf"]})
    return out


def _split(t: str) -> tuple[str, str]:
    """("2026-03-02", "09:20:00") from a candle time ("" for a daily candle's)."""
    t = str(t)
    if len(t) >= 16 and t[10] in "T ":
        return t[:10], (t[11:19] if len(t) >= 19 else t[11:16] + ":00")
    return t[:10], ""
