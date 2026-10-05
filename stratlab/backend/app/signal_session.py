"""A paper session moved by outside signals (signals.py) instead of rules: TradingView, Chartink or any alert that can
call a webhook. Each signal is filled at StratLab's own live price when it arrives (never the price the alert names),
with the same per-order charges as every paper session (engine/costs.py), and recorded through the paper manager's
own order log and trade notifications (LiveManager.on_order). Paper only: no order ever leaves StratLab.

One position at a time, long or short: a buy adds to a long or reduces a short, a sell the other way, and one bigger
than the position closes it and opens the rest the other way (a short only when the session allows it). Each part of a
position closed is a trade with its share of the entry charges. Every signal that arrives is logged with its arrival
time and what happened to it: filled, filled late (the alert's own time was over a minute before it arrived), or
refused and why (the market closed, no live price, not enough paper capital, a repeat of an id already seen)."""
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import signals as SG
from .engine import costs as C
from .kite_service import IST

MARK_EVERY = 60          # seconds between price checks for the account's value (polled markets)
CURVE_EVERY = 300        # seconds between equity points while a position is open
TICK_FRESH = 30          # a streamed price older than this is checked again before a fill
KEEP_SIGNALS = 500
KEEP_IDS = 300
KIND = "signal"


def defaults(inst: dict) -> dict:
    """A session's settings when the page leaves them out."""
    derivative = bool(inst.get("fno")) or inst.get("market") in ("MCX", "CDS", "CMDTY", "FX", "CRYPTO")
    return {"capital": 1_000_000.0 if (inst.get("currency") or "INR") == "INR" else 10_000.0, "allow_short": derivative,
            "leverage": 5.0 if derivative and inst.get("market") != "CRYPTO" else 1.0, "slippage": 0.0,
            "brokerage": 20.0 if inst.get("market", "IN") in ("IN", "MCX", "CDS") else 0.0, "product": "intraday"}


def is_index(inst: dict) -> bool:
    return inst.get("type") == "INDEX"


def lot_of(inst: dict) -> float:
    """Units in one lot for F&O and Indian commodity and currency futures (a signal's qty counts lots there)."""
    if inst.get("fno") or inst.get("market") in ("MCX", "CDS"):
        return float(inst.get("lot") or inst.get("step") or 1)
    return 0.0


def market_open(inst: dict, now: datetime) -> bool:
    """Whether the instrument's market is trading now: its hours on a trading day (crypto always)."""
    from .data.calendar import is_trading_day
    from .data.markets import BY_ID
    mid = inst.get("market", "IN")
    m = BY_ID.get(mid)
    if not m or not m.get("hours"):
        return False
    local = now.astimezone(ZoneInfo(m["tz"]))
    if mid == "CRYPTO":
        return True
    if not is_trading_day(mid, local.date()):
        return False
    hours = m["hours"]
    if not hours.get("open"):
        return True
    hhmm = local.strftime("%H:%M")
    return hours["open"] <= hhmm < hours["close"]


class SignalSession:
    kind = KIND

    def __init__(self, mgr, row: dict):
        self.mgr = mgr
        self.id, self.user_id, self.name = row["id"], row["user_id"], row["name"]
        self.inst = row["instrument"]
        self.market = self.inst.get("market", "IN")
        self.settings = {**defaults(self.inst), **{k: v for k, v in (row.get("strategy") or {}).items() if k in defaults(self.inst)}}
        self.strategy = None
        self.polled = self.market != "IN"
        self.prov = mgr.markets.provider(self.market) if mgr.markets else None
        if self.prov is None:
            raise ValueError("That market isn't connected.")
        st = row.get("state") or {}
        self.capital = float(self.settings["capital"])
        self.cash = float(st.get("cash", self.capital))
        self.pos = float(st.get("pos", 0.0))
        self.avg = float(st.get("avg", 0.0))
        self.entry_t = st.get("entry_t")
        self.entry_cost = float(st.get("entry_cost", 0.0))
        self.trades: list[dict] = list(st.get("trades") or [])
        self.events: list[dict] = list(st.get("events") or [])
        self.signals: list[dict] = list(st.get("signals") or [])
        self.seen: list[str] = list(st.get("seen") or [])
        self.equity_curve: list[dict] = list(st.get("equity_curve") or [])
        self.cost_items: dict[str, float] = dict(st.get("cost_items") or {})
        self.last_price: float | None = st.get("last_price")
        self.last_tick_at: str | None = None
        self._tick_ts = 0.0
        self._next_mark = 0.0
        self._last_curve = 0.0
        self.started_at = row["started_at"]
        self.lock = threading.RLock()      # a fill asks for the price while holding it
        self.dirty = False
        self.feed_ok = True

    # ---------- prices ----------
    def attach(self, hub):
        if not self.polled and self.inst.get("token"):
            hub.add(self.id, int(self.inst["token"]), self.on_tick)

    def detach(self, hub):
        if not self.polled:
            hub.remove(self.id)

    def on_tick(self, tick: dict):
        px = tick.get("last_price")
        if px is None:
            return
        with self.lock:
            self.last_price = float(px)
            self._tick_ts = time.time()
            self.last_tick_at = datetime.now(IST).isoformat()

    def _fetch(self) -> float | None:
        try:
            px = self.prov.ltp(self.inst)
            self.feed_ok = True
        except Exception as e:
            self.feed_ok = False
            print("signal session price failed:", self.id, str(e)[:120])
            return None
        if px is None:
            return None
        px = float(px)
        with self.lock:
            self.last_price = px
            self._tick_ts = time.time()
            self.last_tick_at = datetime.now(IST).isoformat()
        return px

    def price_now(self) -> float | None:
        """StratLab's live price: the streamed one if it's fresh, else asked for now."""
        if self.last_price is not None and time.time() - self._tick_ts < TICK_FRESH:
            return self.last_price
        return self._fetch()

    def on_timer(self, now: datetime):
        if not self.polled or time.time() < self._next_mark:
            return
        self._next_mark = time.time() + MARK_EVERY
        if self.pos and market_open(self.inst, now):
            px = self._fetch()
            if px is not None:
                with self.lock:
                    self._curve(px, force=False)

    # ---------- accounting ----------
    def _kind(self) -> str:
        if is_index(self.inst):
            return "flat"
        k = C.kind_of(self.inst)
        return "in_eq_mis" if k == "in_eq" and self.settings["product"] == "intraday" else k

    def _pay(self, side: str, qty: float, px: float) -> float:
        k = self._kind()
        if k == "flat":
            return 0.0
        items = C.order_costs(k, side, qty, px, float(self.settings["brokerage"]))
        for key, v in items.items():
            self.cost_items[key] = self.cost_items.get(key, 0.0) + v
        return C.total(items)

    def equity(self, px: float | None = None) -> float:
        px = self.last_price if px is None else px
        return self.cash + self.pos * (px or self.avg or 0.0)

    def _curve(self, px: float, force: bool = True):
        if not force and time.time() - self._last_curve < CURVE_EVERY:
            return
        self._last_curve = time.time()
        self.equity_curve.append({"t": datetime.now(IST).isoformat(timespec="seconds"), "eq": round(self.equity(px), 2)})
        self.equity_curve = self.equity_curve[-500:]
        self.dirty = True

    def _fill(self, side: str, units: float, px: float, why: str, t: str) -> dict:
        """Move the position by `units` at `px`, closing before opening; returns the order event."""
        sign = 1 if side == "buy" else -1
        cost = self._pay(side, units, px)
        pnl, closed_q = 0.0, 0.0
        if self.pos * sign < 0:
            c = min(units, abs(self.pos))
            d = 1 if self.pos > 0 else -1
            ec = self.entry_cost * c / abs(self.pos)
            xc = cost * c / units
            p = d * c * (px - self.avg) - ec - xc
            self.trades.append({"entry_t": self.entry_t, "exit_t": t, "entry": self.avg, "exit": px, "qty": c, "pnl": p,
                                "costs": ec + xc, "side": "long" if d > 0 else "short",
                                "ret": d * (px / self.avg - 1) * 100 if self.avg else 0.0, "why": why})
            self.trades = self.trades[-1000:]
            self.entry_cost -= ec
            self.pos += sign * c
            pnl += p
            closed_q = c
            if abs(self.pos) < 1e-9:
                self.pos, self.avg, self.entry_t, self.entry_cost = 0.0, 0.0, None, 0.0
        rest = units - closed_q
        if rest > 1e-9:
            if not self.pos:
                self.entry_t = t
            self.avg = (self.avg * abs(self.pos) + px * rest) / (abs(self.pos) + rest)
            self.pos += sign * rest
            self.entry_cost += cost * rest / units
        self.cash -= sign * units * px + cost
        ev = {"t": t, "side": side, "px": px, "qty": int(units) if float(units).is_integer() else units, "why": why,
              "pnl": pnl if closed_q else None, "sym": self.inst.get("symbol")}
        self.events.append(ev)
        self.events = self.events[-1000:]
        self._curve(px)
        return ev

    # ---------- a signal ----------
    def on_signal(self, sig: dict, arrived: datetime | None = None) -> dict:
        """Act on one checked signal. Returns its log entry ({"status": "filled" | "late" | "rejected" | "duplicate" |
        "ignored", ...}); a fill is recorded and announced through the paper manager."""
        arrived = arrived or datetime.now(timezone.utc)
        entry = {"at": arrived.isoformat(timespec="seconds"), "action": sig["action"], "qty": sig.get("qty"),
                 "alert_px": sig.get("price"), "alert_t": sig.get("time"), "id": sig.get("id"), "note": sig.get("note")}
        delay = SG.lateness(sig, arrived)
        if delay is not None:
            entry["delay_s"] = round(delay, 1)
        ev = None
        with self.lock:
            why = self._refuse(sig, delay, arrived)
            if why:
                entry.update(status="duplicate" if why == "duplicate" else "rejected",
                             reason="A signal with this id already arrived." if why == "duplicate" else why)
            else:
                entry, ev = self._act(sig, entry, delay)
            if sig.get("id"):
                self.seen = (self.seen + [sig["id"]])[-KEEP_IDS:]
            self.signals = (self.signals + [entry])[-KEEP_SIGNALS:]
            self.dirty = True
        if ev is not None:
            self.mgr.on_order(self, ev)      # the paper manager's own order log and trade notification
        return entry

    def _refuse(self, sig: dict, delay: float | None, arrived: datetime) -> str | None:
        if sig.get("id") and sig["id"] in self.seen:
            return "duplicate"
        sym = sig.get("symbol")
        mine = {str(self.inst.get(k) or "").upper() for k in ("symbol", "name")} - {""}
        if sym and sym not in mine:
            return f"The signal names {sym}, but this session trades {self.inst.get('symbol')}."
        if delay is not None and delay > SG.STALE_SECONDS:
            return f"The alert was {delay / 60:.0f} minutes old when it arrived (over {SG.STALE_SECONDS // 60} minutes is refused)."
        if delay is not None and delay < -120:
            return "The alert's time is in the future. Check the time it sends."
        if not market_open(self.inst, arrived):
            return "The market was closed."
        return None

    def _act(self, sig: dict, entry: dict, delay: float | None) -> tuple[dict, dict | None]:
        action = sig["action"]
        if action == "exit" and not self.pos:
            entry.update(status="ignored", reason="No open position to exit.")
            return entry, None
        units = abs(self.pos) if action == "exit" else self._units(sig["qty"], entry)
        if units is None:
            return entry, None
        side = ("sell" if self.pos > 0 else "buy") if action == "exit" else action
        sign = 1 if side == "buy" else -1
        new_pos = self.pos + sign * units
        if new_pos < -1e-9 and not self.settings["allow_short"]:
            entry.update(status="rejected", reason="This session doesn't go short: the sell is bigger than the position.")
            return entry, None
        live = self.price_now()
        if live is None:
            entry.update(status="rejected", reason="No live price to fill at just then.")
            return entry, None
        slip = float(self.settings["slippage"]) / 100
        px = live * (1 + slip * sign)
        if abs(new_pos) > abs(self.pos) + 1e-9:
            room = max(self.equity(live), 0.0) * float(self.settings["leverage"])
            if abs(new_pos) * px > room + 1e-6:
                entry.update(status="rejected", reason=f"Not enough paper capital: that position would be worth "
                                                       f"{abs(new_pos) * px:,.0f}, and the account allows {room:,.0f}.")
                return entry, None
        t = datetime.now(IST).isoformat(timespec="seconds")
        ev = self._fill(side, units, px, "Signal" if action != "exit" else "Signal: exit", t)
        late = delay is not None and delay > SG.LATE_SECONDS
        entry.update(status="late" if late else "filled", px=round(px, 4), side=side, units=units,
                     pnl=round(ev["pnl"], 2) if ev["pnl"] is not None else None,
                     reason=f"Filled {delay:.0f} s after the alert's own time." if late else None)
        return entry, ev

    def _units(self, qty: float, entry: dict) -> float | None:
        lot = lot_of(self.inst)
        if lot:
            if not float(qty).is_integer():
                entry.update(status="rejected", reason=f"qty counts lots here ({lot:g} each): send a whole number.")
                return None
            return qty * lot
        step = float(self.inst.get("step") or 1)
        units = C.floor_to(qty, step)
        if units <= 0 or abs(units - qty) > 1e-9:
            entry.update(status="rejected", reason=f"qty must be a multiple of {step:g}.")
            return None
        return float(units)

    # ---------- what's kept and shown ----------
    def state(self) -> dict:
        return {"cash": self.cash, "pos": self.pos, "avg": self.avg, "entry_t": self.entry_t, "entry_cost": self.entry_cost,
                "trades": self.trades[-1000:], "events": self.events[-1000:], "signals": self.signals[-KEEP_SIGNALS:],
                "seen": self.seen[-KEEP_IDS:], "equity_curve": self.equity_curve[-500:], "cost_items": self.cost_items,
                "last_price": self.last_price}

    def signal_counts(self, day: str) -> dict:
        """How many signals arrived on `day` (the market's date of arrival) and what became of them."""
        tz = ZoneInfo(_tz(self.market))
        rows = []
        for s in self.signals:
            try:
                if datetime.fromisoformat(s["at"]).astimezone(tz).date().isoformat() == day:
                    rows.append(s)
            except (KeyError, ValueError, TypeError):
                continue
        return {"received": len(rows), "late": sum(1 for s in rows if s.get("status") == "late"),
                "refused": sum(1 for s in rows if s.get("status") in ("rejected", "duplicate"))}

    def snapshot(self) -> dict:
        with self.lock:
            px = self.last_price
            eq = self.equity(px)
            return {"id": self.id, "name": self.name, "kind": KIND, "status": "running", "instrument": self.inst,
                    "settings": self.settings, "started_at": self.started_at, "last_price": px, "last_tick_at": self.last_tick_at,
                    "feed_connected": self.feed_ok if self.polled else self.mgr.hub.connected,
                    "market_open": market_open(self.inst, datetime.now(timezone.utc)),
                    "events": self.events[-200:], "signals": self.signals[-200:], "equity_curve": self.equity_curve,
                    "trade_list": self.trades[-200:], "costs": C.breakdown(self.cost_items),
                    "account": {"capital": self.capital, "equity": eq, "cash": self.cash, "qty": abs(self.pos),
                                "entry": self.avg if self.pos else None, "side": "short" if self.pos < 0 else "long",
                                "unrealised": self.pos * ((px or self.avg) - self.avg) if self.pos else 0.0,
                                "realised": sum(t["pnl"] for t in self.trades), "trades": len(self.trades),
                                "wins": sum(1 for t in self.trades if t["pnl"] > 0)}}


def _tz(market: str) -> str:
    from .data.markets import BY_ID
    return (BY_ID.get(market) or {}).get("tz") or "UTC"


def stopped_snapshot(row: dict) -> dict:
    """A stopped session as the page shows it, from what was saved."""
    st = row.get("state") or {}
    inst = row.get("instrument") or {}
    settings = {**defaults(inst), **{k: v for k, v in (row.get("strategy") or {}).items() if k in defaults(inst)}}
    trades = st.get("trades") or []
    cap = float(settings["capital"])
    cash = float(st.get("cash", cap))
    pos, avg = float(st.get("pos", 0.0)), float(st.get("avg", 0.0))
    last = st.get("last_price") or avg
    return {"id": row["id"], "name": row["name"], "kind": KIND, "status": row.get("status"), "stop_reason": row.get("stop_reason"),
            "instrument": inst, "settings": settings, "started_at": row.get("started_at"), "stopped_at": row.get("stopped_at"),
            "last_price": st.get("last_price"), "last_tick_at": None, "feed_connected": False, "market_open": False,
            "events": (st.get("events") or [])[-200:], "signals": (st.get("signals") or [])[-200:],
            "equity_curve": st.get("equity_curve") or [], "trade_list": trades[-200:], "costs": C.breakdown(st.get("cost_items") or {}),
            "account": {"capital": cap, "equity": cash + pos * last, "cash": cash, "qty": abs(pos), "entry": avg if pos else None,
                        "side": "short" if pos < 0 else "long", "unrealised": pos * (last - avg) if pos else 0.0,
                        "realised": sum(t.get("pnl", 0) for t in trades), "trades": len(trades),
                        "wins": sum(1 for t in trades if t.get("pnl", 0) > 0)}}
