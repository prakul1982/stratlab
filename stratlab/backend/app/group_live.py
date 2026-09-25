"""Paper trading one strategy across a group of instruments at once, with one pot of capital.

Each member has its own engine and candles, fed by live ticks (India) or polled closed candles
(every other market). As in the group backtest, a new trade only opens while a position slot is
free, and the daily loss cap counts the whole group: when the day's loss reaches it, every open
position is closed and nothing new opens until the next day."""
import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from .engine import costs as C
from .engine.core import Ctx, Engine
from .kite_service import IST, KiteService
from .live import CandleBuilder, _closed, drop_forming
from .models import Strategy

POLL_SECONDS = 60          # each polled member is checked this often for a newly closed candle
POLLS_PER_PASS = 3         # members polled per 5-second pass, so a big group doesn't burst the data source
FAST_EVAL_SECONDS = 15     # with fast entries on, each flat member's entry rules are checked this often on the forming candle
QUOTE_MAX_AGE = 60         # an order book older than this can't vouch for the spread
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="group-live")


class Member:
    def __init__(self, sess: "GroupLiveSession", inst: dict, bars: list[dict], state: dict | None):
        self.s, self.inst = sess, inst
        self.sym = inst.get("symbol") or inst["id"]
        self.bars = bars[-400:]
        lot = inst.get("step") or (inst.get("lot", 1) if inst.get("fno") else 1)
        self.engine = Engine(sess.each, lot, state=state or None, cost_kind=C.kind_of(inst))
        self.engine.gate = sess.free_slot
        self.engine.veto = self.filtered
        self.builder = CandleBuilder(sess.tf)
        self.last_price = self.bars[-1]["c"]
        self.next_poll = 0.0
        self.bid = self.ask = None
        self.quote_at = 0.0
        self.next_eval = 0.0
        self.skips = (state or {}).get("skips") or {"spread": 0, "price": 0}

    def filtered(self) -> bool:
        """True (and counted) when the entry rules hold but the trade should be skipped."""
        f = self.s.fast
        if f.get("minPrice") and self.last_price < f["minPrice"]:
            self.skips["price"] += 1
            return True
        if f.get("maxSpreadPct"):
            fresh = self.bid and self.ask and time.time() - self.quote_at <= QUOTE_MAX_AGE
            mid = (self.bid + self.ask) / 2 if fresh else 0
            if not fresh or mid <= 0 or (self.ask - self.bid) / mid * 100 > f["maxSpreadPct"]:
                self.skips["spread"] += 1
                return True
        return False

    def on_tick(self, tick: dict):
        px = tick.get("last_price")
        if px is None:
            return
        ts = tick.get("exchange_timestamp") or tick.get("last_trade_time") or datetime.now(IST)
        ts = ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)
        depth = tick.get("depth") or {}
        bid = next((x["price"] for x in depth.get("buy", []) if x.get("price")), None)
        ask = next((x["price"] for x in depth.get("sell", []) if x.get("price")), None)
        with self.s.lock:
            self.last_price = float(px)
            if bid and ask:
                self.bid, self.ask, self.quote_at = float(bid), float(ask), time.time()
            self.s.last_tick_at = datetime.now(IST).isoformat()
            for c in self.builder.on_tick(float(px), ts, tick.get("volume_traded")):
                self.s._on_candle(self, c)
            if self.s.fast.get("ticks"):
                self.enter_early()

    def enter_early(self):
        """Fast entries: try the entry rules on the forming candle, with its latest price as the close."""
        cur = self.builder.cur
        if cur is None or self.engine.qty > 0 or time.time() < self.next_eval:
            return
        self.next_eval = time.time() + FAST_EVAL_SECONDS
        bar = {"t": cur["start"].isoformat(), "o": cur["o"], "h": cur["h"], "l": cur["l"], "c": cur["c"], "v": cur["v"]}
        bars = self.bars + [bar]
        for ev in self.engine.enter_now(bars, Ctx(bars, intraday=True), len(bars) - 1):
            ev["why"] = ev["why"] + " (live price)"
            self.s.dirty = True
            self.s.mgr.on_order(self.s, {**ev, "sym": self.sym})

    def open_pnl(self) -> float:
        e = self.engine
        return e.dir * e.qty * (self.last_price - e.entry) - e.entry_cost if e.qty > 0 else 0.0


class GroupLiveSession:
    kind = "group"

    def __init__(self, mgr, row: dict):
        self.mgr = mgr
        self.id, self.user_id, self.name = row["id"], row["user_id"], row["name"]
        self.strategy = Strategy(**row["strategy"])
        self.inst = row["instrument"]
        self.tf = self.strategy.tf
        self.market = self.inst.get("market", "IN")
        self.polled = self.market != "IN"
        self.max_open = int(self.inst.get("maxOpen") or 10)
        self.fast = self.inst.get("fast") or {}
        self.started_at = row["started_at"]
        self.lock = threading.RLock()
        self.dirty = False
        self.last_tick_at: str | None = None
        self.poll_ok = True
        self.each = copy.deepcopy(self.strategy)
        self.each.session.dailyLossPct = 0            # the group's cap, not each member's
        cap = self.strategy.risk.capital
        self.loss_cap = cap * self.strategy.session.dailyLossPct / 100 if self.strategy.session.dailyLossPct else 0.0
        state = row.get("state") or {}
        self.day = state.get("day")
        self.halted = state.get("halted", False)
        self.day_start_realised = state.get("day_start_realised", 0.0)
        self.equity_curve: list[dict] = state.get("equity_curve", [])
        self.prov = mgr.markets.provider(self.market) if mgr.markets else None
        if self.polled and self.prov is None:
            raise ValueError("That market isn't connected.")
        saved = state.get("members") or {}
        loaded = list(_pool.map(self._load, self.inst.get("members") or []))
        self.members: list[Member] = [Member(self, inst, bars, saved.get(inst["id"])) for inst, bars in loaded if inst and bars]
        self.skipped = [iid.split(":", 1)[-1] for iid, (inst, bars) in zip(self.inst.get("members") or [], loaded) if not (inst and bars)]
        if len(self.members) < 2:
            raise ValueError("Fewer than two of the group's instruments have enough live price history to start.")
        self.lids: list[str] = []
        self._rr = 0

    def _load(self, iid: str):
        try:
            prov, inst = self.mgr.markets.resolve(iid)
            if not inst:
                return None, None
            if self.polled:
                bars = [b for b in prov.history(inst, self.tf, prov.warmup_days(self.tf, 300)) if _closed(b, self.tf)]
            else:
                bars = drop_forming(self.mgr.kite.history(inst["token"], self.tf, KiteService.warmup_days(self.tf, 300)), self.tf)
            return (inst, bars) if len(bars) >= 30 else (inst, None)
        except Exception as e:
            print("group member failed to load:", iid, e)
            return None, None

    # ---------- the shared book ----------
    def free_slot(self) -> bool:
        return not self.halted and sum(1 for m in self.members if m.engine.qty > 0) < self.max_open

    def realised(self) -> float:
        return sum(t["pnl"] for m in self.members for t in m.engine.trades)

    def equity(self) -> float:
        cap = self.strategy.risk.capital
        return cap + self.realised() + sum(m.open_pnl() for m in self.members)

    def _on_candle(self, m: Member, c: dict):
        day = str(c["t"])[:10]
        if day != self.day:
            self.day, self.halted = day, False
            self.day_start_realised = self.realised()
        m.bars.append(c)
        if len(m.bars) > 600:
            m.bars = m.bars[-500:]
        m.last_price = c["c"]
        ctx = Ctx(m.bars, intraday=self.tf != "1d")
        new = m.engine.step(m.bars, ctx, len(m.bars) - 1)
        if self.loss_cap and not self.halted:
            today = self.realised() - self.day_start_realised + sum(x.open_pnl() for x in self.members)
            if today <= -self.loss_cap:
                for x in self.members:
                    if x.engine.qty > 0:
                        bar = x.bars[-1]
                        ev = x.engine._close(bar, x.last_price, "Daily loss cap")
                        self.mgr.on_order(self, {**ev, "sym": x.sym})
                self.halted = True
        t = str(c["t"])
        if self.equity_curve and self.equity_curve[-1]["t"] == t:
            self.equity_curve[-1]["eq"] = round(self.equity(), 2)
        else:
            self.equity_curve.append({"t": t, "eq": round(self.equity(), 2)})
            self.equity_curve = self.equity_curve[-600:]
        self.dirty = True
        for ev in new:
            self.mgr.on_order(self, {**ev, "sym": m.sym})

    # ---------- feeds ----------
    def attach(self, hub):
        if self.polled:
            return
        for i, m in enumerate(self.members):
            lid = f"{self.id}:{i}"
            hub.add(lid, int(m.inst["token"]), m.on_tick, full=bool(self.fast.get("maxSpreadPct")))
            self.lids.append(lid)

    def detach(self, hub):
        for lid in self.lids:
            hub.remove(lid)
        self.lids = []

    def on_timer(self, now: datetime):
        if not self.polled:
            with self.lock:
                for m in self.members:
                    for c in m.builder.flush(now):
                        self._on_candle(m, c)
            return
        due = [m for m in self.members if time.time() >= m.next_poll]
        for m in due[:POLLS_PER_PASS]:
            m.next_poll = time.time() + POLL_SECONDS
            try:
                new = self.prov.closed_candles(m.inst, self.tf, m.bars[-1]["t"])
                px = self.prov.ltp(m.inst)
                self.poll_ok = True
            except Exception as e:
                self.poll_ok = False
                print("group poll failed:", self.id, m.sym, e)
                continue
            with self.lock:
                for c in new:
                    self._on_candle(m, c)
                if px is not None:
                    m.last_price = float(px)
                self.last_tick_at = datetime.now(IST).isoformat()

    # ---------- saving and showing ----------
    def state(self) -> dict:
        return {"members": {m.inst["id"]: {**m.engine.dump(), "skips": m.skips} for m in self.members}, "day": self.day, "halted": self.halted,
                "day_start_realised": self.day_start_realised, "equity_curve": self.equity_curve}

    def snapshot(self) -> dict:
        with self.lock:
            cap = self.strategy.risk.capital
            events = sorted(({**ev, "sym": m.sym} for m in self.members for ev in m.engine.events[-60:]), key=lambda e: str(e["t"]))[-200:]
            trades = [t for m in self.members for t in m.engine.trades]
            rows = []
            for m in self.members:
                e = m.engine
                rows.append({"symbol": m.sym, "id": m.inst["id"], "price": m.last_price, "trades": len(e.trades),
                         "skipped": m.skips["spread"] + m.skips["price"],
                         "spread": round((m.ask - m.bid) / ((m.ask + m.bid) / 2) * 100, 3) if m.bid and m.ask else None,
                             "pnl": round(sum(t["pnl"] for t in e.trades), 2),
                             "position": None if e.qty <= 0 else {"side": "short" if e.dir == -1 else "long", "qty": e.qty,
                                                                  "entry": e.entry, "unrealised": round(m.open_pnl(), 2),
                                                                  "stop": e.sl if e.sl > 0 else None,
                                                                  "target": e.tg if e.tg != float("inf") else None}})
            rows.sort(key=lambda r: (r["position"] is None, -r["pnl"]))
            open_n = sum(1 for m in self.members if m.engine.qty > 0)
            return {
                "id": self.id, "name": self.name, "kind": "group", "status": "running", "instrument": self.inst,
                "strategy": self.strategy.model_dump(), "started_at": self.started_at,
                "last_tick_at": self.last_tick_at, "feed_connected": self.poll_ok if self.polled else self.mgr.hub.connected,
                "members": rows, "skipped": self.skipped, "events": events, "equity_curve": self.equity_curve,
                "bars": [], "overlays": {}, "oscillators": {},
                "account": {"capital": cap, "equity": self.equity(), "realised": self.realised(),
                            "unrealised": sum(m.open_pnl() for m in self.members), "open": open_n, "max_open": self.max_open,
                            "halted": self.halted, "today": self.realised() - self.day_start_realised + sum(m.open_pnl() for m in self.members),
                            "trades": len(trades), "wins": sum(1 for t in trades if t["pnl"] > 0),
                            "skipped": {k: sum(m.skips[k] for m in self.members) for k in ("spread", "price")}},
                "fast": self.fast,
            }


def stopped_snapshot(row: dict) -> dict:
    st = row.get("state") or {}
    cap = row["strategy"]["risk"]["capital"]
    trades = [t for m in (st.get("members") or {}).values() for t in m.get("trades", [])]
    names = row["instrument"].get("names") or {}
    events = sorted(({**ev, "sym": names.get(iid, iid.split(":", 1)[-1])} for iid, m in (st.get("members") or {}).items() for ev in m.get("events", [])[-60:]),
                    key=lambda e: str(e["t"]))[-200:]
    realised = sum(t["pnl"] for t in trades)
    return {"id": row["id"], "name": row["name"], "kind": "group", "status": row["status"], "stop_reason": row.get("stop_reason"),
            "instrument": row["instrument"], "strategy": row["strategy"], "started_at": row["started_at"],
            "stopped_at": row.get("stopped_at"), "members": [], "skipped": [], "events": events,
            "equity_curve": st.get("equity_curve", []), "bars": [], "overlays": {}, "oscillators": {},
            "account": {"capital": cap, "equity": cap + realised, "realised": realised, "unrealised": 0, "open": 0,
                        "max_open": row["instrument"].get("maxOpen"), "halted": False, "today": 0, "trades": len(trades),
                        "wins": sum(1 for t in trades if t["pnl"] > 0)}}
