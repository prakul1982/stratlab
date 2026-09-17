"""Live paper trading: builds candles from Kite ticks and runs the same Engine as backtests."""
import threading
import time
from datetime import datetime, timedelta

from . import db
from .alerts import notify
from .engine.core import Ctx, Engine, chart_series, clean, cond_text
from .kite_service import IST, KiteService, TickHub, INTERVALS
from .models import Strategy
from .plans import PLANS, effective_plan, trial_state

MINUTES = {"1h": 60, "15m": 15, "5m": 5}


def _session_bounds(ts: datetime):
    open_ = ts.replace(hour=9, minute=15, second=0, microsecond=0)
    close = ts.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_, close


def drop_forming(bars: list[dict], tf: str) -> list[dict]:
    """Kite returns the candle that is still forming; live trading must start from closed candles only."""
    if not bars:
        return bars
    now = datetime.now(IST)
    last = datetime.fromisoformat(bars[-1]["t"]).astimezone(IST)
    if tf == "1d":
        _, close = _session_bounds(now)
        forming = last.date() == now.date() and now < close
    else:
        forming = last + timedelta(minutes=MINUTES[tf]) > now
    return bars[:-1] if forming else bars


class CandleBuilder:
    def __init__(self, tf: str):
        self.tf = tf
        self.minutes = MINUTES.get(tf)
        self.cur: dict | None = None
        self.vol0: float | None = None

    def _bucket(self, ts: datetime):
        open_, close = _session_bounds(ts)
        if ts < open_ or ts >= close:
            return None
        if self.minutes is None:
            return ts.replace(hour=0, minute=0, second=0, microsecond=0), close
        k = int((ts - open_).total_seconds() // 60) // self.minutes
        start = open_ + timedelta(minutes=k * self.minutes)
        return start, min(start + timedelta(minutes=self.minutes), close)

    def on_tick(self, price: float, ts: datetime, cum_vol) -> list[dict]:
        closed = self.flush(ts)
        b = self._bucket(ts)
        if b is None:
            return closed
        start, end = b
        if self.cur and self.cur["start"] != start:
            closed.append(self._close())
        if self.cur is None:
            self.cur = {"start": start, "end": end, "o": price, "h": price, "l": price, "c": price, "v": 0.0}
            self.vol0 = cum_vol
        else:
            self.cur["h"] = max(self.cur["h"], price)
            self.cur["l"] = min(self.cur["l"], price)
            self.cur["c"] = price
        if cum_vol is not None and self.vol0 is not None:
            self.cur["v"] = max(0.0, float(cum_vol) - float(self.vol0))
        return closed

    def flush(self, now: datetime) -> list[dict]:
        if self.cur and now >= self.cur["end"]:
            return [self._close()]
        return []

    def _close(self) -> dict:
        c, self.cur = self.cur, None
        return {"t": c["start"].isoformat(), "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "v": c["v"]}


class LiveSession:
    def __init__(self, mgr: "LiveManager", row: dict):
        self.mgr = mgr
        self.id, self.user_id, self.name = row["id"], row["user_id"], row["name"]
        self.strategy = Strategy(**row["strategy"])
        self.inst = row["instrument"]
        self.tf = self.strategy.tf
        bars = mgr.kite.history(self.inst["token"], self.tf, KiteService.warmup_days(self.tf, 300))
        self.bars = drop_forming(bars, self.tf)[-400:]
        if len(self.bars) < 30:
            raise ValueError("Not enough price history to start this strategy.")
        state = row.get("state") or {}
        lot = self.inst.get("lot", 1) if self.inst.get("fno") else 1
        self.engine = Engine(self.strategy, lot, state=state or None)
        self.equity_curve: list[dict] = state.get("equity_curve", [])
        self.builder = CandleBuilder(self.tf)
        self.last_price = self.bars[-1]["c"]
        self.last_tick_at: str | None = None
        self.started_at = row["started_at"]
        self.lock = threading.Lock()
        self.dirty = False

    def on_tick(self, tick: dict):
        price = tick.get("last_price")
        if price is None:
            return
        ts = tick.get("exchange_timestamp") or tick.get("last_trade_time") or datetime.now(IST)
        ts = ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)
        with self.lock:
            self.last_price = float(price)
            self.last_tick_at = datetime.now(IST).isoformat()
            for c in self.builder.on_tick(float(price), ts, tick.get("volume_traded")):
                self._on_candle(c)

    def on_timer(self, now: datetime):
        with self.lock:
            for c in self.builder.flush(now):
                self._on_candle(c)

    def _on_candle(self, c: dict):
        self.bars.append(c)
        if len(self.bars) > 600:
            self.bars = self.bars[-500:]
        ctx = Ctx(self.bars, intraday=self.tf != "1d")
        new = self.engine.step(self.bars, ctx, len(self.bars) - 1)
        self.equity_curve.append({"t": c["t"], "eq": round(self.engine.equity(c["c"]), 2)})
        self.equity_curve = self.equity_curve[-500:]
        self.dirty = True
        for ev in new:
            self.mgr.on_order(self, ev)

    def state(self) -> dict:
        d = self.engine.dump()
        d["equity_curve"] = self.equity_curve
        return d

    def snapshot(self) -> dict:
        with self.lock:
            e = self.engine
            n = min(150, len(self.bars))
            ctx = Ctx(self.bars, intraday=self.tf != "1d")
            overlays, osc = chart_series(self.strategy, ctx, len(self.bars) - n)
            view = self.bars[-n:]
            forming = self.builder.cur
            px = self.last_price
            return {
                "id": self.id, "name": self.name, "status": "running", "instrument": self.inst,
                "strategy": self.strategy.model_dump(), "started_at": self.started_at,
                "last_price": px, "last_tick_at": self.last_tick_at,
                "feed_connected": self.mgr.hub.connected,
                "bars": [{k: b[k] for k in ("t", "o", "h", "l", "c")} for b in view],
                "forming": None if not forming else {"t": forming["start"].isoformat(), "c": forming["c"]},
                "overlays": overlays, "oscillators": osc,
                "events": e.events[-200:],
                "equity_curve": self.equity_curve,
                "account": {
                    "capital": self.strategy.risk.capital, "equity": e.equity(px), "cash": e.cash,
                    "qty": e.qty, "entry": e.entry if e.qty else None,
                    "stop": e.sl if e.qty and self.strategy.risk.sl > 0 else None,
                    "target": e.tg if e.qty and e.tg != float("inf") else None,
                    "unrealised": e.qty * (px - e.entry) if e.qty else 0.0,
                    "realised": sum(t["pnl"] for t in e.trades),
                    "trades": len(e.trades), "wins": sum(1 for t in e.trades if t["pnl"] > 0),
                },
            }


class LimitError(Exception):
    pass


class LiveManager:
    def __init__(self, kite: KiteService, hub: TickHub):
        self.kite, self.hub = kite, hub
        self.sessions: dict[str, LiveSession] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ---------- lifecycle ----------
    def start_loop(self):
        if not self._thread:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def resume(self):
        for row in db.running_sessions():
            if row["id"] in self.sessions:
                continue
            try:
                self._attach(row)
            except Exception as e:
                db.update_session(row["id"], status="stopped", stopped_at=db.now_iso(),
                                  stop_reason=f"Could not resume after restart: {e}")

    def _attach(self, row: dict) -> LiveSession:
        s = LiveSession(self, row)
        with self._lock:
            self.sessions[s.id] = s
        self.hub.add(s.id, int(s.inst["token"]), s.on_tick)
        return s

    def user_running(self, user_id: str) -> list[LiveSession]:
        with self._lock:
            return [s for s in self.sessions.values() if s.user_id == user_id]

    def start(self, profile: dict, plan: str, strategy: Strategy, inst: dict) -> LiveSession:
        limit = PLANS[plan]["live_limit"]
        if len(self.user_running(profile["id"])) >= limit:
            raise LimitError(f"Your plan runs {limit} live strateg{'y' if limit == 1 else 'ies'} at a time. Stop one first.")
        row = db.create_session({
            "user_id": profile["id"], "name": strategy.name, "strategy": strategy.model_dump(),
            "instrument": inst, "status": "running",
        })
        try:
            return self._attach(row)
        except Exception as e:
            db.update_session(row["id"], status="stopped", stopped_at=db.now_iso(), stop_reason=str(e))
            raise

    def stop(self, sid: str, reason: str):
        with self._lock:
            s = self.sessions.pop(sid, None)
        if not s:
            return
        self.hub.remove(sid)
        db.update_session(sid, status="stopped", stopped_at=db.now_iso(), stop_reason=reason, state=s.state())

    # ---------- orders and alerts ----------
    def on_order(self, s: LiveSession, ev: dict):
        def work():
            try:
                db.add_order({"session_id": s.id, "user_id": s.user_id, "side": ev["side"], "qty": ev["qty"],
                              "price": round(ev["px"], 2), "reason": ev.get("why"), "pnl": ev.get("pnl"),
                              "candle_time": ev["t"]})
                profile = db.get_profile(s.user_id)
                if effective_plan(profile) == "pro" and profile.get("alerts_enabled"):
                    sym = s.inst["symbol"]
                    if ev["side"] == "buy":
                        text = f"StratLab paper trade: BUY {ev['qty']} {sym} at Rs {ev['px']:.2f} ({s.name})"
                    else:
                        text = (f"StratLab paper trade: SELL {ev['qty']} {sym} at Rs {ev['px']:.2f}, "
                                f"{ev['why'].lower()}, P&L Rs {ev['pnl']:,.0f} ({s.name})")
                    notify(profile, f"{s.name}: {ev['side'].upper()} {sym}", text, background=False)
            except Exception as e:
                print("order record failed:", e)
        threading.Thread(target=work, daemon=True).start()

    # ---------- background loop ----------
    def _loop(self):
        last_persist = last_plan = 0.0
        while True:
            time.sleep(5)
            now = datetime.now(IST)
            with self._lock:
                sessions = list(self.sessions.values())
            for s in sessions:
                try:
                    s.on_timer(now)
                except Exception as e:
                    print("timer error:", e)
            t = time.time()
            if t - last_persist > 30:
                last_persist = t
                for s in sessions:
                    if s.dirty:
                        s.dirty = False
                        try:
                            db.update_session(s.id, state=s.state())
                        except Exception as e:
                            print("persist failed:", e)
            if t - last_plan > 60:
                last_plan = t
                self._enforce_plans(sessions)

    def _enforce_plans(self, sessions: list[LiveSession]):
        by_user: dict[str, list[LiveSession]] = {}
        for s in sessions:
            by_user.setdefault(s.user_id, []).append(s)
        for uid, items in by_user.items():
            try:
                profile = db.get_profile(uid)
            except Exception:
                continue
            plan = effective_plan(profile)
            if plan == "free" and not trial_state(profile)["active"]:
                for s in items:
                    self.stop(s.id, "Free live trial ended. Upgrade to keep paper trading.")
                continue
            limit = PLANS[plan]["live_limit"]
            for s in sorted(items, key=lambda x: x.started_at)[limit:]:
                self.stop(s.id, "Plan limit reached after a plan change.")
            if not PLANS[plan]["pro_features"]:
                for s in items:
                    if s.id in self.sessions and needs_pro(s.strategy, s.inst):
                        self.stop(s.id, "This strategy uses Pro features.")


def needs_pro(strategy: Strategy, inst: dict | None) -> bool:
    from .plans import BASIC_REFS
    if inst and inst.get("fno"):
        return True
    return any(r.t not in BASIC_REFS for c in [*strategy.entry, *strategy.exit] for r in (c.l, c.r))


def describe(strategy: Strategy) -> str:
    join = " OR " if strategy.entryJoin == "any" else " AND "
    lines = [f"Entry: {join.join(cond_text(c) for c in strategy.entry) or 'none'}",
             f"Exit: {' OR '.join(cond_text(c) for c in strategy.exit) or 'stop loss / target only'}"]
    r = strategy.risk
    lines.append(f"Risk: {r.riskPct}% per trade, stop {r.sl}%, target {r.tgt}%, capital Rs {r.capital:,.0f}")
    return "\n".join(lines)
