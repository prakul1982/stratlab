"""A running options paper-trading session, polled every few seconds by the live manager."""
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..models import OptionStrategy
from .data import OptionsData, freeze
from .engine import VIX_KEY, OptionsEngine, next_entry
from . import strikes as SR
from .signal import SignalFeed

IST = ZoneInfo("Asia/Kolkata")
POLL = 5


class OptionSession:
    polled = True
    kind = "options"

    def __init__(self, mgr, row: dict, data: OptionsData):
        self.mgr, self.data = mgr, data
        self.id, self.user_id, self.name = row["id"], row["user_id"], row["name"]
        self.strategy = OptionStrategy(**row["strategy"])
        self.inst = row["instrument"]
        self.market = self.inst.get("market", "IN")
        self.started_at = row["started_at"]
        state = row.get("state") or {}
        s = self.strategy
        settle = getattr(data, "settlement_price", None)
        self.engine = OptionsEngine(s, state=state or None, margin_fn=data.margin, freeze_default=freeze(s.underlying),
                                    settle_fn=(lambda e: settle(s.exchange, s.underlying, e)) if settle else None)
        self.equity_curve: list[dict] = state.get("equity_curve", [])
        self.lock = threading.Lock()
        self.dirty = False
        self.next_poll = 0.0
        self.poll_ok = True
        self.spot: float | None = None
        self.quotes: dict = {}
        self.last_tick_at: str | None = None
        self.fresh = False
        self.contracts = None
        self._contracts_day = None
        if not data.expiries(s.exchange, s.underlying):
            raise ValueError(f"No {s.underlying} options are listed on {s.exchange}.")
        self.signal = None
        if s.signal:
            sk = data.spot_key(s.exchange, s.underlying, data.pick_expiry(s.exchange, s.underlying, s.expiry))
            self.signal = SignalFeed(data.kite, s.signal.rules, sk, state.get("signal"))

    def _keys(self, spot_key: str | None) -> list[str]:
        keys = [spot_key] if spot_key else []
        e, c = self.engine, self.contracts
        if e.pos:
            keys += [l["key"] for l in e.pos["legs"] if l["open"]]
        if c and self.spot:
            atm = c.atm(self.spot)
            legs = list(self.strategy.legs)
            if self.signal and self.strategy.signal.short == "mirror":
                legs += e.legs_for("short")        # quote both, so either signal can enter at once
            for lg in legs:
                if lg.pick != "offset":
                    continue
                k = c.strike_for(atm, lg.opt, lg.offset, self.strategy.offsetUnit)
                if k is not None:
                    keys.append(c.key(lg.opt, k))
            # a strike rule picks among the strikes near the money: quote them all (and the ATM pair for the model)
            # while the session could enter or re-centre
            if not e.pos or self.strategy.recenter.enabled:
                keys += SR.keys_for(c, atm, legs)
        if self.strategy.vix and not e.pos:
            keys.append(VIX_KEY)
        return [k for k in dict.fromkeys(keys) if k]

    def on_timer(self, now: datetime):
        if time.time() < self.next_poll:
            return
        self.next_poll = time.time() + POLL
        s = self.strategy
        now = now.astimezone(IST)
        try:
            if self._contracts_day != now.date() and not self.engine.pos:
                self.contracts = self.data.contracts(s.exchange, s.underlying, s.expiry)
                self._contracts_day = now.date()
            sk = self.data.spot_key(s.exchange, s.underlying, self.contracts.expiry if self.contracts else None)
            q = self.data.quotes(self._keys(sk))
            sq = q.get(sk) if sk else None
            if sq and sq.get("ltp"):
                self.spot = float(sq["ltp"])
            q2 = self.data.quotes(self._keys(sk))   # strikes near the new spot, mostly from the cache
            q.update(q2)
            self.poll_ok = True
            if self.signal:
                self.signal.poll(now)
        except Exception as e:
            self.poll_ok = False
            print("options poll failed:", self.id, e)
            return
        with self.lock:
            self.quotes = q
            self.fresh = self.data.fresh(sq, now)
            if self.fresh:
                self.last_tick_at = now.isoformat()
            want = self.signal.want() if self.signal else None
            new = self.engine.step(now, self.spot, self.contracts, q, self.fresh, want)
            minute = now.replace(second=0, microsecond=0).isoformat()
            if self.fresh and (not self.equity_curve or self.equity_curve[-1]["t"] != minute):
                self.equity_curve.append({"t": minute, "eq": round(self.engine.equity(q), 2)})
                self.equity_curve = self.equity_curve[-800:]
            self.dirty = True
        for ev in new:
            self.mgr.on_order(self, ev)

    def state(self) -> dict:
        d = self.engine.dump()
        d["equity_curve"] = self.equity_curve
        if self.signal:
            d["signal"] = self.signal.dump()
        return d

    def snapshot(self) -> dict:
        with self.lock:
            e, q = self.engine, self.quotes
            return {
                "id": self.id, "name": self.name, "kind": "options", "status": "running", "instrument": self.inst,
                "strategy": self.strategy.model_dump(), "started_at": self.started_at,
                "spot": self.spot, "last_tick_at": self.last_tick_at, "fresh": self.fresh,
                "feed_connected": self.poll_ok, "expiry": self.contracts.expiry if self.contracts else None,
                "lot": self.contracts.lot if self.contracts else None, "note": e.note,
                "legs": e.legs_view(q), "position": _position(e, q),
                "events": e.events[-200:], "trades": e.trades[-100:], "equity_curve": self.equity_curve,
                "account": account(e, q),
                "signal": None if not self.signal else {**self.signal.view(), "name": self.strategy.signal.name,
                                                        "short": self.strategy.signal.short},
            }


def _position(e: OptionsEngine, q: dict) -> dict | None:
    p = e.pos
    if not p:
        return None
    m = e.mtm(q)
    return {"opened": p["opened"], "center": p["center"], "spot_in": p["spot_in"], "credit": p["credit"],
            "mtm": round(m, 2), "costs": round(p["costs"], 2), "net": round(m - p["costs"], 2),
            "best": p["peak"], "worst": p["low"], "rolls": p["rolls"], "units": p["units"], "orders": p["orders"],
            "expiry": p["expiry"], "dir": p.get("dir")}


def account(e: OptionsEngine, q: dict | None) -> dict:
    return {"capital": e.s.sizing.capital, "equity": e.equity(q), "cash": e.cash,
            "realised": sum(t["pnl"] for t in e.trades), "today": e.day_realised, "halted": e.halted,
            "entries_today": e.entries_today, "trades": len(e.trades), "wins": sum(1 for t in e.trades if t["pnl"] > 0),
            # the earliest time the gap between trades allows the next entry (None when there's no gap, or it runs past the
            # day's last entry), for the page's "Next entry from 13:41" (R7T-013)
            "cool_until": e.cool_until, "next_entry": next_entry(e.cool_until, e.s.timing) if not e.pos else None,
            "unrealised": (e.mtm(q or {}) - e.pos["costs"]) if e.pos else 0.0}


def stopped_snapshot(row: dict) -> dict:
    """What a stopped session looks like, rebuilt from its saved state."""
    st = row.get("state") or {}
    s = OptionStrategy(**row["strategy"])
    e = OptionsEngine(s, state=st or None)
    return {"id": row["id"], "name": row["name"], "kind": "options", "status": row["status"],
            "stop_reason": row.get("stop_reason"), "instrument": row["instrument"], "strategy": row["strategy"],
            "started_at": row["started_at"], "stopped_at": row.get("stopped_at"), "spot": None, "fresh": False,
            "legs": e.legs_view({}), "position": _position(e, {}), "events": e.events[-200:], "trades": e.trades[-100:],
            "equity_curve": st.get("equity_curve", []), "account": account(e, {}), "note": ""}
