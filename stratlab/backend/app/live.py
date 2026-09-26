"""Live paper trading: builds candles from Kite ticks and runs the same Engine as backtests."""
import threading
import time
from datetime import datetime, timedelta

from . import db
from . import alerts
from .alerts import notify
from .engine import costs as C
from .engine.core import Ctx, Engine, chart_series, cond_text
from .kite_service import IST, KiteService, TickHub
from .models import Strategy
from .daily_report import Reporter
from .data.markets import MARKETS
from .errors import report
from .plans import PLANS, access_plan, allows, has_pro_features, trial_state

MINUTES = {"1h": 60, "15m": 15, "5m": 5}
POLL_SECONDS = 15          # how often polled markets (crypto) are checked for a newly closed candle


def _session_bounds(ts: datetime):
    open_ = ts.replace(hour=9, minute=15, second=0, microsecond=0)
    close = ts.replace(hour=15, minute=30, second=0, microsecond=0)
    return open_, close


def _closed(bar: dict, tf: str) -> bool:
    secs = {"1d": 86400, "1h": 3600, "15m": 900, "5m": 300}[tf]
    return datetime.fromisoformat(bar["t"]).timestamp() + secs <= time.time()


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
        self.market = self.inst.get("market", "IN")
        # India streams ticks from Kite; other markets are polled for closed candles
        self.polled = self.market != "IN"
        self.prov = mgr.markets.provider(self.market) if mgr.markets else None
        if self.polled:
            if self.prov is None:
                raise ValueError("That market isn't connected.")
            bars = self.prov.history(self.inst, self.tf, self.prov.warmup_days(self.tf, 300))
            bars = [b for b in bars if _closed(b, self.tf)]
        else:
            bars = drop_forming(mgr.kite.history(self.inst["token"], self.tf, KiteService.warmup_days(self.tf, 300)), self.tf)
        self.bars = bars[-400:]
        if len(self.bars) < 30:
            raise ValueError("Not enough price history to start this strategy.")
        state = row.get("state") or {}
        lot = self.inst.get("step") or (self.inst.get("lot", 1) if self.inst.get("fno") else 1)
        self.engine = Engine(self.strategy, lot, state=state or None, cost_kind=C.kind_of(self.inst))
        self.next_poll = 0.0
        self.poll_ok = True
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
        if self.polled:
            self._poll()
            return
        with self.lock:
            for c in self.builder.flush(now):
                self._on_candle(c)

    def _poll(self):
        if time.time() < self.next_poll:
            return
        self.next_poll = time.time() + POLL_SECONDS
        try:
            new = self.prov.closed_candles(self.inst, self.tf, self.bars[-1]["t"])
            px = self.prov.ltp(self.inst)
            self.poll_ok = True
        except Exception as e:
            self.poll_ok = False
            print("poll failed:", self.id, e)
            return
        with self.lock:
            for c in new:
                self._on_candle(c)
            if px is not None:
                self.last_price = float(px)
            self.last_tick_at = datetime.now(IST).isoformat()

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
                "feed_connected": self.poll_ok if self.polled else self.mgr.hub.connected,
                "bars": [{k: b[k] for k in ("t", "o", "h", "l", "c")} for b in view],
                "forming": None if not forming else {"t": forming["start"].isoformat(), "c": forming["c"]},
                "overlays": overlays, "oscillators": osc,
                "events": e.events[-200:],
                "equity_curve": self.equity_curve,
                "account": {
                    "capital": self.strategy.risk.capital, "equity": e.equity(px), "cash": e.cash,
                    "qty": e.qty, "entry": e.entry if e.qty else None,
                    "stop": e.sl if e.qty and e.sl > 0 else None,
                    "side": "short" if e.dir == -1 else "long",
                    "target": e.tg if e.qty and e.tg != float("inf") else None,
                    "unrealised": e.dir * e.qty * (px - e.entry) if e.qty else 0.0,
                    "realised": sum(t["pnl"] for t in e.trades),
                    "trades": len(e.trades), "wins": sum(1 for t in e.trades if t["pnl"] > 0),
                },
            }


class LimitError(Exception):
    pass


class LiveManager:
    def __init__(self, kite: KiteService, hub: TickHub, markets=None, options=None):
        self.kite, self.hub, self.markets, self.options = kite, hub, markets, options
        self.reporter = Reporter(db)
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
            if (row.get("instrument") or {}).get("market", "IN") in ("IN", "MCX") and not self.kite.ready():
                continue  # resumes after today's Kite login; shown as paused until then
            try:
                self._attach(row)
            except Exception as e:
                db.update_session(row["id"], status="stopped", stopped_at=db.now_iso(),
                                  stop_reason=f"Could not resume after restart: {e}")

    def _attach(self, row: dict):
        kind = (row.get("instrument") or {}).get("type")
        if kind == "OPTIONS":
            from .options.session import OptionSession
            s = OptionSession(self, row, self.options)
        elif kind == "GROUP":
            from .group_live import GroupLiveSession
            s = GroupLiveSession(self, row)
        else:
            s = LiveSession(self, row)
        with self._lock:
            self.sessions[s.id] = s
        if hasattr(s, "attach"):
            s.attach(self.hub)
        elif not s.polled:
            self.hub.add(s.id, int(s.inst["token"]), s.on_tick)
        return s

    def user_running(self, user_id: str) -> list[LiveSession]:
        with self._lock:
            return [s for s in self.sessions.values() if s.user_id == user_id]

    def start(self, profile: dict, plan: str, strategy, inst: dict):
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
        if hasattr(s, "detach"):
            s.detach(self.hub)
        elif not s.polled:
            self.hub.remove(sid)
        with s.lock:
            st = s.state()
        db.update_session(sid, status="stopped", stopped_at=db.now_iso(), stop_reason=reason, state=st)

    # ---------- orders and alerts ----------
    def on_order(self, s: LiveSession, ev: dict):
        def work():
            try:
                if isinstance(ev["qty"], int):  # the orders table stores whole quantities; the session keeps every order
                    db.add_order({"session_id": s.id, "user_id": s.user_id, "side": ev["side"], "qty": ev["qty"],
                                  "price": round(ev["px"], 2), "reason": ev.get("why"), "pnl": ev.get("pnl"),
                                  "candle_time": ev["t"]})
                profile = db.get_profile(s.user_id)
                if alerts_on(profile):
                    sym, cur = ev.get("sym") or s.inst["symbol"], s.inst.get("currency", "INR")
                    if ev["side"] == "buy":
                        text = f"StratLab paper trade: BUY {ev['qty']:g} {sym} at {ev['px']:,.2f} {cur} ({s.name})"
                    else:
                        text = (f"StratLab paper trade: SELL {ev['qty']:g} {sym} at {ev['px']:,.2f} {cur}, "
                                f"{ev['why'].lower()}, P&L {ev['pnl']:,.0f} {cur} ({s.name})")
                    notify(profile, f"{s.name}: {ev['side'].upper()} {sym}", text, background=False, url=f"/paper/{s.id}")
            except Exception as e:
                print("order record failed:", e)
        threading.Thread(target=work, daemon=True).start()

    # ---------- background loop ----------
    def _loop(self):
        self._last_persist = self._last_plan = 0.0
        while True:
            time.sleep(5)
            try:
                self._tick()
            except Exception as e:  # never let one bad pass kill the loop
                print("live loop error:", e)
                report(e, where="live loop")

    def _tick(self):
        now = datetime.now(IST)
        with self._lock:
            sessions = list(self.sessions.values())
        for s in sessions:
            try:
                s.on_timer(now)
            except Exception as e:
                print("timer error:", e)
                report(e, where="live timer")
        t = time.time()
        if t - self._last_persist > 30:
            self._last_persist = t
            self.persist(sessions)
        if t - self._last_plan > 60:
            self._last_plan = t
            self._enforce_plans(sessions)
            try:
                self.reporter.run(sessions, can_alert=report_on, market_name=market_name,
                                  send=lambda p, subj, body: notify(p, subj, body, background=False))
            except Exception as e:
                print("daily reports failed:", e)
                report(e, where="daily report")

    def persist(self, sessions: list[LiveSession] | None = None, only_dirty: bool = True):
        if sessions is None:
            with self._lock:
                sessions = list(self.sessions.values())
        for s in sessions:
            if only_dirty and not s.dirty:
                continue
            s.dirty = False
            try:
                with s.lock:
                    st = s.state()
                db.update_session(s.id, state=st)
            except Exception as e:
                s.dirty = True  # try again next time
                print("persist failed:", e)

    def _enforce_plans(self, sessions: list[LiveSession]):
        by_user: dict[str, list[LiveSession]] = {}
        for s in sessions:
            by_user.setdefault(s.user_id, []).append(s)
        for uid, items in by_user.items():
            try:
                profile = db.get_profile(uid)
            except Exception:
                continue
            plan = access_plan(profile)
            if plan == "free" and not trial_state(profile)["active"]:
                why = ("Free live trial ended. Upgrade to keep paper trading." if trial_state(profile)["started"] else
                       "The free launch offer has ended. Start the session again to use your free live trial, or upgrade.")
                for s in items:
                    self.stop(s.id, why)
                continue
            limit = PLANS[plan]["live_limit"]
            for s in sorted(items, key=lambda x: x.started_at)[limit:]:
                self.stop(s.id, "Plan limit reached after a plan change.")
            if not has_pro_features(plan):
                for s in items:
                    if s.id in self.sessions and isinstance(s, LiveSession) and needs_pro(s.strategy, s.inst):
                        self.stop(s.id, "This strategy uses Pro features.")
            for s in items:
                missing = session_needs(s, plan)
                if missing and s.id in self.sessions:
                    self.stop(s.id, f"{missing} isn't on your plan any more.")


def session_needs(s, plan: str) -> str | None:
    """The first feature a running session uses that the plan doesn't include, in words, or None."""
    kind = getattr(s, "kind", "single")
    if kind == "group":
        if not allows(plan, "group_live"):
            return "Paper trading a group"
        f = getattr(s, "fast", {}) or {}
        if (f.get("ticks") or f.get("maxSpreadPct")) and not allows(plan, "fast_entries"):
            return "Faster group entries"
    if kind == "options":
        if not allows(plan, "options"):
            return "Options paper trading"
        if getattr(s.strategy, "signal", None) and not allows(plan, "options_signal"):
            return "Options on a signal"
    return None


def alerts_on(profile: dict) -> bool:
    """A message for every paper trade: for anyone who turned alerts on and whose plan has them."""
    return bool(profile.get("alerts_enabled")) and allows(access_plan(profile), "alerts")


def report_on(profile: dict) -> bool:
    """The daily report goes wherever alerts are set up (phone, Telegram or email), on plans that include it."""
    has_channel = bool(alerts.jobs_for(profile, "", ""))      # only channels the server can actually use
    return bool(has_channel) and allows(access_plan(profile), "daily_report")


def market_name(mid: str) -> str:
    return next((m["name"] for m in MARKETS if m["id"] == mid), mid)


def needs_pro(strategy: Strategy, inst: dict | None) -> bool:
    from .plans import BASIC_REFS
    if inst and inst.get("fno"):
        return True
    return any(r.t not in BASIC_REFS for c in strategy.all_conds() for r in (c.l, c.r))


def describe(strategy: Strategy) -> str:
    join = {"any": " OR ", "score": " + "}.get(strategy.entryJoin, " AND ")
    both = strategy.side == "both"
    go = "Short" if strategy.side == "short" else "Long"
    lines = [f"{go} entry: {join.join(cond_text(c) for c in strategy.entry) or 'none'}",
             f"{go} exit: {' OR '.join(cond_text(c) for c in strategy.exit) or 'stop / target only'}"]
    if both:
        lines += [f"Short entry: {join.join(cond_text(c) for c in strategy.shortEntry) or 'none'}",
                  f"Short exit: {' OR '.join(cond_text(c) for c in strategy.shortExit) or 'stop / target only'}"]
    if strategy.entryJoin == "score":
        lines.append(f"Enter when the score reaches {strategy.minScore or 'every rule'}")
    r, ss = strategy.risk, strategy.session
    unit = {"pct": "%", "points": " pts", "atr": "x ATR", "swing": "-candle swing"}[r.stopType]
    tunit = {"pct": "%", "points": " pts", "r": "R"}[r.tgtType]
    size = (f"{r.riskPct}% risk per trade" if r.sizing == "risk"
            else f"{r.perTrade or r.capital * r.maxAlloc / 100:,.0f} per trade x{r.leverage:g}")
    lines.append(f"Risk: {size}, stop {r.sl:g}{unit}, target {r.tgt:g}{tunit}, capital {r.capital:,.0f}")
    if strategy.tf != "1d" and (ss.start or ss.end or ss.squareoff or ss.maxTradesDay or ss.cooldown or ss.dailyLossPct):
        lines.append(f"Session: entries {ss.start or 'open'}-{ss.end or 'close'}, square-off {ss.squareoff or 'none'}, "
                     f"{ss.maxTradesDay or 'unlimited'} trades a day, cooldown {ss.cooldown} candles, "
                     f"daily loss cap {ss.dailyLossPct:g}%")
    return "\n".join(lines)
