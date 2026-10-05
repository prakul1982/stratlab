"""The closing auction desk (Trade → Closing auction): India's closing auction session (CAS) as the exchange publishes
it, live through the auction and kept for 60 trading days.

Since 3 Aug 2026 stocks with derivatives stop continuous trading at 15:15 and close through an auction that ends at
15:35 (data/sessions.py has the timetable and the circulars). Through the auction the exchange publishes, per stock,
the reference price (VWAP of 15:00-15:15), the +/-3% band, the indicative equilibrium price (IEP) and quantity, the
best bid and ask, and the unmatched quantity; after it, the final price (the official close) and quantity. For indices
it publishes the index value on the constituents' last continuous prices and an indicative close on their IEPs.

The exchange's CAS page data is read every 30 seconds from 15:14 to 15:40 on trading days, kept in one app_settings
row, and after 15:40 the day is stored (each stock's reference and final price and quantity, each index's value as
the auction began and its close) for the 60-day history (Basic).

Facts and arithmetic only: "final price 0.42% above the reference price". The IEP is labelled indicative: it changes
until the auction ends. Nothing here forecasts a close or says what to do."""
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from . import db
from .auth import current_profile
from .data import sessions as S
from .data.calendar import is_trading_day
from .intel.net import TTLCache
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import err, ok

LIVE_KEY = "closeauc:live"         # {"read", "phase", "as_of", "status", "stocks": {sym: [...]}, "indices": {...}, "start": {...}}
DAY_KEY = "closeauc:day:"          # closeauc:day:<YYYY-MM-DD> = {"stocks": {sym: [ref, final, qty]}, "indices": {name: [start, close]}}
KEEP_DAYS = 60
EVERY = 30                         # seconds between reads through the auction
READ_FROM, READ_TO = "15:14", "15:40"     # India time: the reads, around the 15:15-15:35 auction
SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
INDEX = re.compile(r"^[A-Z0-9 &\-]{2,40}$")
MAX_GAP = 25.0                     # a bigger gap is a broken number, not an auction (the band is +/-3%)
NOTE = ("From the exchange's closing auction data. The reference price is the volume-weighted average price of "
        "15:00-15:15; the auction's band is 3% either side of it. The indicative equilibrium price (IEP) is the price at "
        "which most quantity would match on the orders in the book at that moment: indicative, it changes until the "
        "auction ends at 15:35. The final price is the official close. Facts, not advice.")
IST = timezone(timedelta(hours=5, minutes=30))

_cache = TTLCache(max_items=50)
_feed = {"fn": None}
_lock = threading.Lock()


def setup(feed_fn):
    """Where the exchange's CAS data is read from (main.py's exchange client, or a test's fake)."""
    _feed["fn"] = feed_fn


def forget():
    _cache.clear()


# ---------- numbers ----------
def num(v) -> float | None:
    """A number from the exchange's JSON ("1,234.50", "-", "" and None are none)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return x if abs(x) < 1e15 else None


def pos(v) -> float | None:
    x = num(v)
    return x if x is not None and x > 0 else None


def gap(price, ref) -> float | None:
    """How far a price is from a reference, as a percent of it (above is positive), to two places."""
    p, r = pos(price), pos(ref)
    if p is None or r is None:
        return None
    g = (p / r - 1) * 100
    return round(g, 2) if abs(g) <= MAX_GAP else None


def words(g: float | None, what: str = "the reference price") -> str:
    if g is None:
        return ""
    if abs(g) < 0.005:
        return f"at {what}"
    a = abs(g)
    return f"{a:.2f}% {'above' if g > 0 else 'below'} {what}"


# ---------- the exchange's data ----------
def _when(v) -> str | None:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(v).strip()[:20], fmt).replace(tzinfo=IST).isoformat(timespec="seconds")
        except (TypeError, ValueError):
            continue
    return None


# per stock, as stored: reference, lower band, upper band, IEP, IEQ, final price, final qty, unmatched at IEP,
# unmatched market orders, best bid qty, best bid, best ask, best ask qty, total buy qty, total sell qty
FIELDS = ("ref", "lower", "upper", "iep", "ieq", "final", "final_qty", "imb", "imb_mkt", "bid_qty", "bid", "ask", "ask_qty",
          "buy_qty", "sell_qty")
_SRC = ("refrencePrice", "lowerBand", "upperBand", "IEP", "totTradedQty", "finalPrice", "finalQuantity", "iiqAtEP",
        "iiqAtMO", "bestBidQty", "bestBidPrice", "bestAskPrice", "bestAskQty", "totalBuyQuantity", "totalSellQuantity")


def parse_stocks(data) -> dict:
    """The exchange's CAS list as {"as_of", "status", "eligible": [symbols], "rows": {symbol: {field: number}}}."""
    d = data if isinstance(data, dict) else {}
    rows = {}
    for it in d.get("data") if isinstance(d.get("data"), list) else []:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "").strip().upper()
        if not SYMBOL.match(sym):
            continue
        r = {f: num(it.get(k)) for f, k in zip(FIELDS, _SRC)}
        if pos(r["ref"]) is None and pos(r["iep"]) is None and pos(r["final"]) is None:
            continue
        rows[sym] = r
    eligible = sorted({str(s).strip().upper() for s in d.get("symbols") or [] if SYMBOL.match(str(s).strip().upper())})
    return {"as_of": _when(d.get("timestamp")) if d.get("timestamp") else None, "status": d.get("status"),
            "message": d.get("statusMsg"), "eligible": eligible, "rows": rows}


def parse_indices(data) -> dict:
    """The exchange's F&O index list as {name: {"value", "prev_close", "indicative", "status"}}."""
    out = {}
    for it in data if isinstance(data, list) else []:
        if not isinstance(it, dict):
            continue
        name = " ".join(str(it.get("indexName") or "").upper().split())
        if not INDEX.match(name):
            continue
        out[name] = {"value": pos(it.get("currentPrice")), "prev_close": pos(it.get("closePrice")),
                     "indicative": pos(it.get("indicativeClose")), "status": str(it.get("icStatus") or "") or None}
    return out


# ---------- storage ----------
def load_live() -> dict:
    hit = _cache.get("live")
    if hit is not None:
        return hit
    try:
        got = db.json_value(db.get_setting(LIVE_KEY), {})
    except Exception:
        got = {}
    got = got if isinstance(got, dict) else {}
    stocks = {}
    for s, v in (got.get("stocks") or {}).items():
        if isinstance(v, list) and len(v) == len(FIELDS):
            stocks[s] = dict(zip(FIELDS, v))
    out = {"read": got.get("read"), "day": got.get("day"), "as_of": got.get("as_of"), "status": got.get("status"),
           "message": got.get("message"), "eligible": got.get("eligible") or [], "stocks": stocks,
           "indices": got.get("indices") or {}, "start": got.get("start") or {}}
    _cache.set("live", out, 20)
    return out


def save_live(day: str, stocks: dict, indices: dict, now: datetime):
    """Keep one read. The index values at the first read of the day (as the auction began) are kept beside it."""
    prev = load_live()
    start = prev["start"] if prev.get("day") == day else {}
    for name, r in indices.items():
        if name not in start and r.get("value"):
            start[name] = r["value"]
    row = {"read": now.isoformat(timespec="seconds"), "day": day, "as_of": stocks["as_of"], "status": stocks["status"],
           "message": stocks["message"], "eligible": stocks["eligible"] or prev.get("eligible") or [],
           "stocks": {s: [r[f] for f in FIELDS] for s, r in stocks["rows"].items()}, "indices": indices, "start": start}
    db.set_setting(LIVE_KEY, json.dumps(row, separators=(",", ":")))
    _cache.clear()


def refresh(feed=None, now: datetime | None = None) -> dict:
    """Read the exchange's CAS data now and keep it. Raises when it can't be read."""
    feed = feed if feed is not None else (_feed["fn"]() if _feed["fn"] else None)
    if feed is None:
        raise ValueError("no exchange client")
    now = now or datetime.now(timezone.utc)
    stocks = parse_stocks(feed.cas_stocks())
    try:
        indices = parse_indices(feed.cas_indices())
    except Exception as e:                    # the stocks still count
        print("CAS indices unavailable:", str(e)[:120])
        indices = {}
    save_live(now.astimezone(IST).date().isoformat(), stocks, indices, now)
    return stocks


def _days() -> dict[str, dict]:
    hit = _cache.get("days")
    if hit is not None:
        return hit
    out = {}
    try:
        for k, raw in db.all_settings_with_prefix(DAY_KEY):
            day = k[len(DAY_KEY):]
            got = db.json_value(raw, {})
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and isinstance(got, dict):
                out[day] = got
    except Exception:
        return {}
    _cache.set("days", out, 600)
    return out


def record_day(day: str, live: dict) -> int:
    """Store the day's auction: each stock's reference price, final price and final quantity, and each index's value
    as the auction began and its close. Only a read from that day counts. Returns how many stocks were stored."""
    if live.get("day") != day:
        return 0
    stocks = {s: [r["ref"], r["final"], r["final_qty"]] for s, r in live["stocks"].items() if pos(r["final"])}
    indices = {n: [live["start"].get(n), r.get("value")] for n, r in live["indices"].items() if r.get("value")}
    if not stocks:
        return 0
    db.set_setting(DAY_KEY + day, json.dumps({"stocks": stocks, "indices": indices}, separators=(",", ":")))
    _cache.clear()
    for old in sorted(_days())[:-KEEP_DAYS]:
        db.delete_setting(DAY_KEY + old)
    _cache.clear()
    return len(stocks)


# ---------- what the page shows ----------
def stock_view(sym: str, r: dict, phase: str) -> dict:
    """One stock: its reference price and band, the IEP (or final price) and the gap to the reference, and the
    quantities."""
    final = pos(r.get("final"))
    price = final if final else pos(r.get("iep"))
    g = gap(price, r.get("ref"))
    imb = num(r.get("imb"))
    return {"symbol": sym, "ref": pos(r.get("ref")), "lower": pos(r.get("lower")), "upper": pos(r.get("upper")),
            "iep": pos(r.get("iep")), "ieq": num(r.get("ieq")), "final": final, "final_qty": num(r.get("final_qty")),
            "price": price, "final_out": bool(final), "gap": g,
            "imbalance": imb, "imbalance_market": num(r.get("imb_mkt")),
            "bid": pos(r.get("bid")), "bid_qty": num(r.get("bid_qty")), "ask": pos(r.get("ask")), "ask_qty": num(r.get("ask_qty")),
            "buy_qty": num(r.get("buy_qty")), "sell_qty": num(r.get("sell_qty")),
            "text": f"{sym}: {'final price' if final else 'IEP'} {words(g)}" if g is not None else None}


def index_view(name: str, r: dict, start: float | None) -> dict:
    value, ind = pos(r.get("value")), pos(r.get("indicative"))
    return {"name": name, "value": value, "prev_close": pos(r.get("prev_close")), "indicative": ind,
            "status": r.get("status"), "start": pos(start), "gap": gap(ind, value) if ind else None,
            "close_gap": gap(value, start) if start and value else None}


def expiry_today(today: date) -> list[str]:
    """Index option series expiring today on NSE or BSE, from the day's contract list (empty when it can't be read)."""
    from . import main
    out = []
    for ex, name in (("NFO", "NIFTY"), ("NFO", "BANKNIFTY"), ("NFO", "FINNIFTY"), ("NFO", "MIDCPNIFTY"), ("BFO", "SENSEX"), ("BFO", "BANKEX")):
        try:
            if main.options_data.pick_expiry(ex, name, "current") == today.isoformat():
                out.append(name)
        except Exception:
            return out
    return out


SETTLEMENT = ("On expiry, index options settle at the index's close, worked out from its constituents' closing prices "
              "(auction prices for stocks with derivatives); stock options at the volume-weighted average of the NSE and "
              "BSE auction closes (NSE Clearing NCL/CMPT/73370). In force since 3 Aug 2026.")
PROPOSAL = ("SEBI's consultation paper of 12 Sep 2026 proposes settling at a blend of the last 30 minutes of continuous "
            "trading and the auction, or at the last 30 minutes' VWAP alone, and moving the auction to 15:31-15:40 or "
            "15:15-15:25. Proposals only; comments closed on 3 Oct 2026.")


def positions_at_settlement(profile: dict, indices: dict, stocks: dict, today: date) -> list[dict]:
    """The user's running paper option positions that expire today, each open leg at its intrinsic value against the
    indicative settlement (the index's indicative close, or the stock's IEP / final price). Model arithmetic on the
    indicative numbers, labelled so."""
    from . import main
    from .options.data import INDEX_SPOT
    out = []
    try:
        sessions = main.manager.user_running(profile["id"])
    except Exception:
        return out
    for s in sessions:
        e = getattr(s, "engine", None)
        p = getattr(e, "pos", None) if getattr(s, "kind", "") == "options" else None
        if not p or p.get("expiry") != today.isoformat():
            continue
        st = s.strategy
        spot = INDEX_SPOT.get((st.exchange, st.underlying))
        if spot:
            r = indices.get(spot.split(":", 1)[1].upper()) or {}
            under, basis = pos(r.get("indicative")) or pos(r.get("value")), "the index's indicative close"
        else:
            r = stocks.get(st.underlying.upper()) or {}
            under, basis = pos(r.get("final")) or pos(r.get("iep")), "the stock's auction price"
        legs, total = [], 0.0
        for leg in p["legs"]:
            if not leg.get("open"):
                continue
            k = float(leg["strike"])
            iv = None if under is None else max(0.0, under - k) if leg["opt"] == "CE" else max(0.0, k - under)
            pnl = None if iv is None else ((leg["entry"] - iv) if leg["side"] == "sell" else (iv - leg["entry"])) * leg["qty"]
            total += pnl or 0.0
            legs.append({"sym": leg["sym"], "side": leg["side"], "opt": leg["opt"], "strike": k, "qty": leg["qty"],
                         "entry": leg["entry"], "value": None if iv is None else round(iv, 2), "pnl": None if pnl is None else round(pnl, 2)})
        out.append({"session": s.id, "name": s.name, "underlying": st.underlying, "settle_on": under, "basis": basis,
                    "legs": legs, "open_pnl": round(total, 2) if under is not None else None,
                    "closed_pnl": round(p.get("closed_pnl", 0.0), 2)})
    return out


def view(profile: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(IST)
    today = local.date()
    trading = is_trading_day("IN", today)
    phase = S.phase(local) if trading else "holiday"
    live = load_live()
    fresh = live.get("day") == today.isoformat()
    stocks = [stock_view(s, r, phase) for s, r in live["stocks"].items()] if live["stocks"] else []
    stocks.sort(key=lambda v: (v["gap"] is None, -abs(v["gap"] or 0), v["symbol"]))
    indices = [index_view(n, r, live["start"].get(n)) for n, r in live["indices"].items()]
    expiring = expiry_today(today) if trading else []
    return {"phase": phase, "today": today.isoformat(), "trading_day": trading, "timetable": S.describe(today),
            "day": live.get("day"), "fresh": fresh, "read": live.get("read"), "as_of": live.get("as_of"),
            "status": live.get("status"), "message": live.get("message"), "eligible": len(live.get("eligible") or []),
            "stocks": stocks, "indices": indices,
            "expiry": {"series": expiring, "settlement": SETTLEMENT, "proposal": PROPOSAL,
                       "positions": positions_at_settlement(profile, live["indices"], live["stocks"], today)
                       if expiring or fresh else []},
            "history": {"allowed": allows(profile["_plan"], "cas_history"), "plan": PLANS[FEATURE_PLAN["cas_history"]]["name"],
                        "days": len(_days())},
            "sources": S.SOURCES, "note": NOTE}


def history(symbol: str | None = None) -> dict:
    """The stored days, newest first: per day, how many stocks closed in the auction, the average and widest gap of
    the final price to the reference price, and each index's close against its value as the auction began. With a
    symbol, that stock's days."""
    days = []
    for day, got in sorted(_days().items(), reverse=True)[:KEEP_DAYS]:
        st = got.get("stocks") or {}
        gaps = {s: gap(v[1], v[0]) for s, v in st.items() if isinstance(v, list) and len(v) >= 3}
        gs = [g for g in gaps.values() if g is not None]
        idx = [{"name": n, "start": pos(v[0]), "close": pos(v[1]), "gap": gap(v[1], v[0])}
               for n, v in (got.get("indices") or {}).items() if isinstance(v, list) and len(v) >= 2]
        row = {"day": day, "stocks": len(st), "avg_abs_gap": round(sum(abs(g) for g in gs) / len(gs), 2) if gs else None,
               "up": sum(1 for g in gs if g > 0), "down": sum(1 for g in gs if g < 0), "indices": idx}
        if gs:
            wide = max(gaps.items(), key=lambda kv: abs(kv[1]) if kv[1] is not None else -1)
            row["widest"] = {"symbol": wide[0], "gap": wide[1]}
        if symbol:
            v = st.get(symbol)
            row["stock"] = None if not isinstance(v, list) else {"ref": pos(v[0]), "final": pos(v[1]), "qty": num(v[2]),
                                                                 "gap": gaps.get(symbol)}
        days.append(row)
    return {"days": days, "symbol": symbol, "note": NOTE}


# ---------- the job ----------
class Job:
    """Through the auction on trading days (15:14-15:40 India time), read the exchange's CAS data every 30 seconds;
    after 15:40, store the day once (run marker closeauc:recorded)."""

    def __init__(self, feed_fn):
        self.feed_fn = feed_fn
        self.status = {"read": None, "recorded": None, "last_error": None}
        self._next = 0.0

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="closing-auction").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
            time.sleep(10)

    def tick(self, now: datetime) -> str | None:
        """One check: "read", "recorded" or None."""
        local = now.astimezone(IST)
        day = local.date()
        if not is_trading_day("IN", day) or not S.timetable(day).auction:
            return None
        hm = local.strftime("%H:%M")
        if READ_FROM <= hm < READ_TO:
            if time.time() < self._next:
                return None
            self._next = time.time() + EVERY
            try:
                refresh(self.feed_fn(), now)
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                return None
            self.status.update(read=now.isoformat(timespec="seconds"), last_error=None)
            return "read"
        if hm >= READ_TO and db.get_setting("closeauc:recorded") != day.isoformat():
            live = load_live()
            if live.get("day") != day.isoformat() or not any(pos(r["final"]) for r in live["stocks"].values()):
                if hm >= "16:30":          # nothing came: give up for the day
                    db.set_setting("closeauc:recorded", day.isoformat())
                    return None
                if time.time() >= self._next:
                    self._next = time.time() + 120
                    try:
                        refresh(self.feed_fn(), now)
                    except Exception as e:
                        self.status["last_error"] = str(e)[:200]
                return None
            n = record_day(day.isoformat(), live)
            db.set_setting("closeauc:recorded", day.isoformat())
            self.status.update(recorded=day.isoformat())
            return "recorded" if n else None
        return None


# ---------- the routes ----------
router = APIRouter(prefix="/trade/closing-auction", tags=["trade"])


@router.get("")
def closing_auction(profile=Depends(current_profile)):
    """Today's closing auction: the phase, each stock's reference price, IEP or final price and the gap, the
    indices, the expiry-day settlement and your paper option positions that expire today. Free."""
    return ok(view(profile))


@router.get("/history")
def closing_auction_history(symbol: str | None = Query(None, max_length=20), profile=Depends(current_profile)):
    """The last 60 trading days of auctions (Basic and up)."""
    if not allows(profile["_plan"], "cas_history"):
        err(402, "upgrade_required", f"The closing auction history is on the {PLANS[FEATURE_PLAN['cas_history']]['name']} plan.")
    sym = (symbol or "").strip().upper() or None
    if sym and not SYMBOL.match(sym):
        err(422, "bad_symbol", "That isn't a stock symbol.")
    return ok(history(sym))
