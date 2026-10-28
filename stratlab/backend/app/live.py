"""Live paper trading: builds candles from Kite ticks and runs the same Engine as backtests."""
import json
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import db
from . import leader
from . import alerts
from . import email_kit as kit
from . import risk
from .alerts import notify
from .corp_actions import PaperActions
from .engine import costs as C
from .engine.core import TF_MIN, Ctx, Engine, chart_series, cond_text, saved_totals
from .kite_service import IST, KiteService, TickHub
from .models import Strategy
from .daily_report import Reporter
from .data import sessions as S
from .data.markets import MARKETS
from .errors import report
from .plans import PLANS, allows, has_fno, has_indicators, plan_of, trial_state

MINUTES = {"1h": 60, "15m": 15, "5m": 5}
POLL_SECONDS = 15          # how often polled markets (crypto) are checked for a newly closed candle
OFFICIAL_WAIT = timedelta(minutes=30)   # a daily candle waits this long past the close for the official close
FRESH_SECONDS = 180        # a paper order placed by hand fills only at a price this recent
RESUME_TRIES = 10            # a running session whose attach keeps failing for another reason than a permanent one is stopped after this many tries
MANUAL_WHY = "Opened from your AI assistant"
MANUAL_CLOSE_WHY = "Closed from your AI assistant"


def _session_bounds(ts: datetime, kind: str = "cash"):
    """When continuous trading starts and ends that day for this kind of instrument (data/sessions.py): a stock with
    derivatives stops at 15:15 since the closing auction began, futures and options run to 15:40."""
    start, end = S.continuous(kind, ts)
    open_ = ts.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    close = ts.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    return open_, close


def session_kind(kite, inst: dict | None) -> str:
    """The instrument's kind in the session table: "cas", "cash", "index" or "fo"."""
    names = getattr(kite, "derivative_names", None)
    try:
        return S.kind_of(inst, names() if names else ())
    except Exception as e:                     # no instrument list (logged out): the plain cash timetable
        print("session kind unknown:", e)
        return S.kind_of(inst)


def official_close(kite, inst: dict, day: str) -> float | None:
    """The day's official close from its daily candle (the auction price for a stock with derivatives), or None
    before it's out."""
    try:
        bars = kite.history(inst["token"], "1d", 7, ttl=60)
    except Exception as e:
        print("official close unavailable:", inst.get("symbol"), e)
        return None
    for b in reversed(bars or []):
        if str(b["t"])[:10] == day:
            # a stock's candle is the exchange's close once that is known (official_close.history_close); until then, or
            # for OFFICIAL_WAIT after the close is due, its last continuous trade is not the auction price (R8B-001)
            if (getattr(kite, "__dict__", {}).get("day_close") and inst.get("type") == "EQ" and not b.get("official")
                    and datetime.now(IST) < S.at(day, S.close_known(session_kind(kite, inst), day)) + OFFICIAL_WAIT):
                return None
            return float(b["c"])
    return None


def close_at_auction(engine: Engine, kind: str, now: datetime, close_px) -> dict | None:
    """An intraday position (one with a square-off time) still open when the day's official close is out closes at
    that close: no continuous candle came after its square-off time (for a stock with derivatives, a square-off after
    15:15 falls in the closing auction), and orders placed in the auction fill at its price, as orders in the cash
    market's post-close session fill at the close. Cash-market instruments and indices only; `close_px()` fetches the
    close. Returns the order, or None."""
    if kind == "fo" or engine.qty <= 0 or engine.t_sq is None:
        return None
    local = now.astimezone(IST)
    if str(engine.entry_t)[:10] != local.date().isoformat():
        return None
    known = S.close_known(kind, local)
    if local.time() < known:
        return None
    px = close_px()
    if px is None:
        return None
    why = "Square-off at the closing auction price" if S.auction(kind, local) else "Square-off at the closing price"
    return engine._close({"t": S.at(local, known).isoformat()}, px, why)


def _closed(bar: dict, tf: str) -> bool:
    secs = {"1d": 86400, "1h": 3600, "15m": 900, "5m": 300}[tf]
    return datetime.fromisoformat(bar["t"]).timestamp() + secs <= time.time()


def drop_forming(bars: list[dict], tf: str, kind: str = "cash") -> list[dict]:
    """Kite returns the candle that is still forming; live trading must start from closed candles only. Today's daily
    candle counts as closed once the official close is out."""
    if not bars:
        return bars
    now = datetime.now(IST)
    last = datetime.fromisoformat(bars[-1]["t"]).astimezone(IST)
    if tf == "1d":
        forming = last.date() == now.date() and now < S.at(now, S.close_known(kind, now))
    else:
        forming = last + timedelta(minutes=MINUTES[tf]) > now
    return bars[:-1] if forming else bars


class CandleBuilder:
    """Candles from ticks, inside the instrument's continuous session only: a tick after continuous trading ends
    makes no candle, so nothing fills on it. With `official(day)` given, the daily candle waits for the day's official
    close (for a stock with derivatives, the closing auction price) and closes on it; if the close still isn't out
    OFFICIAL_WAIT after it should be, the candle closes on the last price."""
    def __init__(self, tf: str, kind: str = "cash", official=None):
        self.tf, self.kind, self.official = tf, kind, official
        self.minutes = MINUTES.get(tf)
        self.cur: dict | None = None
        self.vol0: float | None = None
        self.last_vol: float | None = None   # the day's traded volume at the last tick
        self.last_end: datetime | None = None   # the end of the last candle emitted: a tick before it is late or stale
        self._retry = 0.0

    def resume(self, last: dict | None, forming: dict | None = None):
        """Pick up after the history: ticks before `last` (the newest closed candle) are dropped, and `forming`, the
        history's candle still in progress, becomes the current candle so its open, high, low and volume aren't lost."""
        try:
            if last:
                t = datetime.fromisoformat(str(last["t"]))
                end = t + timedelta(days=1) if self.minutes is None else datetime.fromisoformat(candle_end(last, self.tf))
                self.last_end = end.replace(tzinfo=IST) if end.tzinfo is None else end
            if forming:
                t = datetime.fromisoformat(str(forming["t"]))
                t = t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST)
                b = self._bucket(_session_bounds(t, self.kind)[0] if self.minutes is None else t)
                if b and (self.minutes is None or b[0] == t) and (self.last_end is None or b[0] >= self.last_end):
                    self.cur = {"start": b[0], "end": b[1], "o": forming["o"], "h": forming["h"], "l": forming["l"],
                                "c": forming["c"], "v": float(forming.get("v") or 0)}
        except (KeyError, TypeError, ValueError) as e:
            print("candle builder resume:", e)

    def _bucket(self, ts: datetime):
        open_, close = _session_bounds(ts, self.kind)
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
        if (self.last_end and start < self.last_end) or (self.cur and start < self.cur["start"]):
            return closed                    # a late or stale tick: its candle has already closed
        if self.cur and self.cur["start"] != start:
            closed.append(self._close())
        vol = float(cum_vol) if cum_vol is not None else None
        if self.cur is None:
            self.cur = {"start": start, "end": end, "o": price, "h": price, "l": price, "c": price, "v": 0.0}
            # counted from the last tick before it, so what traded before its first tick is in it (not across days)
            self.vol0 = self.last_vol if vol is not None and self.last_vol is not None and self.last_vol <= vol else None
        else:
            self.cur["h"] = max(self.cur["h"], price)
            self.cur["l"] = min(self.cur["l"], price)
            self.cur["c"] = price
        if vol is not None:
            if self.vol0 is None:
                self.vol0 = vol - self.cur["v"]   # a resumed candle keeps the volume it had
            self.cur["v"] = max(0.0, vol - self.vol0)
            self.last_vol = vol
        return closed

    def flush(self, now: datetime) -> list[dict]:
        if self.cur and now >= self.cur["end"]:
            if self.minutes is None and self.official is not None and not self._settle(now):
                return []
            return [self._close()]
        return []

    def _settle(self, now: datetime) -> bool:
        """The daily candle takes the official close; False while it should wait for it."""
        local = now.astimezone(IST)
        day = self.cur["start"].astimezone(IST).date()
        known = S.at(day, S.close_known(self.kind, day))
        if local < known:
            return False
        if time.time() < self._retry and local < known + OFFICIAL_WAIT:
            return False
        px = self.official(day.isoformat())
        if px is None:
            self._retry = time.time() + 60
            return local >= known + OFFICIAL_WAIT
        c = self.cur
        c["c"], c["h"], c["l"] = px, max(c["h"], px), min(c["l"], px)
        return True

    def _close(self) -> dict:
        c, self.cur = self.cur, None
        self.last_end, self.vol0 = c["end"], None
        # "t" names the candle by its start, as the engine and the backtest do; "end" is when it closed, the moment its
        # close (the price a rule's order fills at) was the price (R11C-011)
        return {"t": c["start"].isoformat(), "o": c["o"], "h": c["h"], "l": c["l"], "c": c["c"], "v": c["v"],
                "end": c["end"].isoformat()}


def candle_end(c: dict, tf: str) -> str:
    """When a closed candle closed: its own end when it has one (a candle built from ticks: the last one of a session ends
    at the session's close), else its start plus its length. A daily candle keeps its day."""
    if c.get("end"):
        return str(c["end"])
    if tf not in MINUTES:
        return c["t"]
    try:
        return (datetime.fromisoformat(str(c["t"])) + timedelta(minutes=MINUTES[tf])).isoformat()
    except ValueError:
        return c["t"]


def _ts(t) -> float:
    d = datetime.fromisoformat(str(t))
    return (d.replace(tzinfo=IST) if d.tzinfo is None else d).timestamp()


def split_missed(bars: list[dict], last_t: str | None) -> tuple[list[dict], list[dict]]:
    """The history up to the last candle the session processed, and the closed candles after it (the server was down
    when they closed). With no saved last candle (a new session, or state saved before this was kept) nothing is missed."""
    if not last_t:
        return bars, []
    last = _ts(last_t)
    i = len(bars)
    while i and _ts(bars[i - 1]["t"]) > last:
        i -= 1
    if i < 30:                     # down longer than the history reaches: too few candles before the gap to run rules on
        return bars, []
    return bars[:i], bars[i:]


def tick_time(ts: datetime) -> str:
    """When a tick's price was the price: its own time, or now if that is later (a snapshot of yesterday's close
    sent on subscribe is not a fresh price)."""
    now = datetime.now(IST)
    return min(ts, now).isoformat() if ts.tzinfo else now.isoformat()


def day_close_minutes(market: str):
    """For the engine: the minute a day's session closes, from the exchange calendar (an early close), or None."""
    from .data.calendar import day_close

    def close(day: str) -> int | None:
        try:
            hm = day_close(market, datetime.fromisoformat(day).date())
        except ValueError:
            return None
        return int(hm[:2]) * 60 + int(hm[3:]) if hm else None
    return close


TRADE_ALERTS = "tradealerts:"        # tradealerts:<uid>: {"day": India date, "n": paper-trade alerts sent that day}
TRADE_ALERTS_PER_DAY = 40            # on email and Telegram; the phone has no cap
TRADE_ALERTS_CAPPED = "More trade alerts today are on the session page."
CATCH_UP_LINES = 20                  # a catch-up alert lists this many orders (Telegram stops at 4096 characters)


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
        # India: which session timetable the instrument follows (a stock with derivatives closes through the auction)
        self.session_kind = "cash" if self.polled else session_kind(mgr.kite, self.inst)
        if self.polled:
            if self.prov is None:
                raise ValueError("That market isn't connected.")
            bars = self.prov.history(self.inst, self.tf, self.prov.warmup_days(self.tf, 300))
            bars = [b for b in bars if _closed(b, self.tf)]
            forming = None
        else:
            raw = mgr.kite.history(self.inst["token"], self.tf, KiteService.warmup_days(self.tf, 300))
            bars = drop_forming(raw, self.tf, self.session_kind)
            forming = raw[-1] if len(bars) < len(raw or []) else None
        if len(bars) < 30:
            raise ValueError("Not enough price history to start this strategy.")
        state = row.get("state") or {}
        # a stock's bonuses and splits: the candles in today's prices, before the missed ones are split off and run
        self.corp = PaperActions(self.inst, state)
        today = self.corp.today()
        todo = self.corp.resume(bars, today)
        bars, missed = split_missed(bars, state.get("last_bar_t"))
        self.bars = bars[-400:]
        lot = self.inst.get("step") or (self.inst.get("lot", 1) if self.inst.get("fno") else 1)
        self.engine = Engine(self.strategy, lot, state=state or None, cost_kind=C.kind_of(self.inst))
        n = len(self.engine.events)
        # dividends and cash for fractional shares, paid in or out: in the cash, and counted with the realised P&L as a
        # group's are. A state saved before it was kept has it in its cash only
        self.corp_cash = state.get("corp_cash", 0.0)
        cash = self.corp.apply(self.engine, todo, today, todo=True)[0]
        self.engine.cash += cash
        self.corp_cash += cash
        self.engine.next_open = False        # live fills at the latest price, once the candle has closed
        self.engine.day_close = day_close_minutes(self.market)
        self.next_poll = 0.0
        self.poll_ok = True
        self.equity_curve: list[dict] = state.get("equity_curve", [])
        self.day_equity: dict = state.get("day_equity") or {}      # each day's closing equity, beyond the curve (R8B-002)
        self.builder = CandleBuilder(self.tf, self.session_kind, self._official if self.session_kind in ("cas", "index") else None)
        self.last_price = self.bars[-1]["c"]
        self.last_tick_at: str | None = None
        self.started_at = row["started_at"]
        self.lock = threading.Lock()
        self.dirty = len(self.engine.events) > n
        self.replaying: list[dict] | None = None    # the orders of candles being caught up on, alerted as one
        if missed:
            self.mgr.replay(self, lambda: [self._on_candle(c) for c in missed])
            self.last_price = self.bars[-1]["c"]
        self.builder.resume(self.bars[-1], forming)

    def on_tick(self, tick: dict):
        price = tick.get("last_price")
        if price is None:
            return
        ts = tick.get("exchange_timestamp") or tick.get("last_trade_time") or datetime.now(IST)
        ts = ts.replace(tzinfo=IST) if ts.tzinfo is None else ts.astimezone(IST)
        with self.lock:
            self.last_price = float(price)
            self.last_tick_at = tick_time(ts)
            for c in self.builder.on_tick(float(price), ts, tick.get("volume_traded")):
                self._on_candle(c)

    def on_timer(self, now: datetime):
        with self.lock:
            self._corp_day(self.corp.today(now), timer=True)
        if self.polled:
            self._poll()
            return
        with self.lock:
            for c in self.builder.flush(now):
                self._on_candle(c)
            ev = close_at_auction(self.engine, self.session_kind, now,
                                  lambda: self._official(now.astimezone(IST).date().isoformat()))
            if ev:
                self.last_price = ev["px"]
                self.equity_curve.append({"t": ev["t"], "eq": round(self.engine.equity(ev["px"]), 2)})
                self.dirty = True
                self.mgr.on_order(self, ev)

    def _official(self, day: str) -> float | None:
        return official_close(self.mgr.kite, self.inst, day)

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
            if px is not None:                # no price: the last one stays, and ages
                self.last_price = float(px)
                self.last_tick_at = datetime.now(IST).isoformat()

    def _corp_day(self, day: str, timer: bool = False):
        """Once a day, before its first candle: the stock's bonuses, splits and dividends on the open position. From the
        timer the last price is the previous day's, so it's put in the new prices too."""
        acts = self.corp.new_day(day)
        if acts:
            n = len(self.engine.events)
            self.corp.bars(self.bars, acts)
            cash, f = self.corp.apply(self.engine, acts, day)
            self.engine.cash += cash
            self.corp_cash += cash
            if timer:
                self.last_price /= f
            self.dirty = self.dirty or len(self.engine.events) > n

    def _on_candle(self, c: dict):
        self._corp_day(str(c["t"])[:10])
        self.bars.append(c)
        if len(self.bars) > 600:
            self.bars = self.bars[-500:]
        if self.corp.waiting:
            self.corp.on_bar(self.bars)
        ctx = Ctx(self.bars, intraday=self.tf != "1d", base_min=TF_MIN.get(self.tf))
        new = self.engine.step(self.bars, ctx, len(self.bars) - 1)
        # the account's value at the candle's close, stamped when the candle closed: the 14:00-14:05 candle's close is the
        # 14:05 price (R11C-011: the curve said 14:00 and marked the 14:05 price)
        self.equity_curve.append({"t": candle_end(c, self.tf), "eq": round(self.engine.equity(c["c"]), 2)})
        self.equity_curve = self.equity_curve[-500:]
        self.dirty = True
        for ev in new:
            self.mgr.on_order(self, ev)

    # ---------- paper orders by hand (the AI assistant's paper tools) ----------
    def price_problem(self, now: datetime | None = None) -> str | None:
        """Why the latest price can't be used to fill a paper order now (the market is shut, or no price has arrived
        in the last few minutes), or None when it can."""
        from .data.calendar import day_close, is_trading_day
        from .data.markets import BY_ID
        now = now or datetime.now(IST)
        m = BY_ID.get(self.market) or {}
        hours = m.get("hours") or {}
        local = now.astimezone(ZoneInfo(m.get("tz") or "UTC"))
        open_, close = hours.get("open"), day_close(self.market, local.date()) or hours.get("close")      # the calendar knows early closes
        if self.market == "MCX":
            from .options.data import expiry_time
            close = expiry_time("MCX", local.date())       # 23:55 while US daylight saving is off
        elif self.market == "IN":
            # the timetable of this kind of instrument: futures and options trade to 15:40, a stock with derivatives to 15:15 (RC3T-006)
            start, end = S.continuous(getattr(self, "session_kind", "cash"), local.date())
            open_, close = start.strftime("%H:%M"), end.strftime("%H:%M")
        if not is_trading_day(self.market, local.date()) or (
                open_ and not open_ <= local.strftime("%H:%M") < close):
            return f"{m.get('name') or self.market} is closed now, so there's no live price to fill a paper order at."
        if not self.last_tick_at:
            return "No live price has arrived for this session yet. Try again in a minute."
        try:
            age = (now - datetime.fromisoformat(self.last_tick_at)).total_seconds()
        except (TypeError, ValueError):
            age = None
        if age is None or age > FRESH_SECONDS:
            return "The last price for this session is more than a few minutes old. Try again once prices are flowing."
        return None

    def _stamp(self) -> str:
        """Now as the candles are stamped: in the instrument's own zone (India's for a stock, the exchange's for a US one).
        The engine compares this date with a candle's to see whether a position is from an earlier day."""
        from .data.markets import BY_ID
        tz = self.inst.get("tz") or (BY_ID.get(self.market) or {}).get("tz") or "Asia/Kolkata"
        return datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds")

    def manual_open(self, side: str, qty: float, now: datetime | None = None) -> dict:
        """Open a paper position at the latest price. Raises ValueError with a plain reason when it can't."""
        d = 1 if side == "buy" else -1
        if d not in self.engine.sides:
            raise ValueError(f"This session's strategy trades {'short' if self.engine.sides == [-1] else 'long'} only, "
                             f"so a {'buy' if d == 1 else 'short sale'} can't be opened in it.")
        problem = self.price_problem(now)
        if problem:
            raise ValueError(problem)
        with self.lock:
            e = self.engine
            if e.qty > 0:
                raise ValueError("This session already has an open position. Close it first.")
            stamp = self._stamp()
            e.roll_day(stamp)            # yesterday's loss limit doesn't hold today, before today's first candle too
            if e.halted:
                raise ValueError("This session hit its daily loss limit today, so it opens nothing more until tomorrow.")
            q = C.floor_to(float(qty), e.qty_step)
            if q <= 0:
                raise ValueError(f"The quantity must be at least {e.qty_step:g} (this instrument's step).")
            px = float(self.last_price)
            need = e.manual_cost(side, q, px)
            if need > e.cash:
                raise ValueError(f"That needs about {need:,.2f} and the session has {e.cash:,.2f} in cash.")
            ev = e.open_manual(stamp, px, d, q, MANUAL_WHY)
            self.dirty = True
        self.mgr.on_order(self, ev)
        return ev

    def manual_close(self, now: datetime | None = None) -> dict:
        """Close the open paper position at the latest price. Raises ValueError with a plain reason when it can't."""
        if self.engine.qty <= 0:
            raise ValueError("This session has no open position to close.")
        problem = self.price_problem(now)
        if problem:
            raise ValueError(problem)
        with self.lock:
            if self.engine.qty <= 0:
                raise ValueError("This session has no open position to close.")
            mark = self.bars[-1]["c"] if self.bars else None     # the last close: a carried position's day mark
            ev = self.engine.close_manual(self._stamp(), float(self.last_price), MANUAL_CLOSE_WHY, mark)
            self.dirty = True
        self.mgr.on_order(self, ev)
        return ev

    def state(self) -> dict:
        d = self.engine.dump()
        d["equity_curve"] = self.equity_curve
        d["day_equity"] = self.day_equity = risk.note_days(self.day_equity, self.equity_curve)
        d["last_price"], d["last_tick_at"] = self.last_price, self.last_tick_at
        d["last_bar_t"] = self.bars[-1]["t"]       # the last candle run: a restart catches up on the ones after it
        d.update(self.corp.dump())
        d["corp_cash"] = self.corp_cash
        return d

    def final_state(self, now: datetime | None = None) -> dict:
        """The state kept when the session stops. An open position stays open, as the stop dialog says, valued at the last
        price: the account's value at that price is the curve's last point, and the newest candles are kept, so the
        stopped page shows the same account, position and chart as the curve (R11C-002)."""
        e = self.engine
        if e.qty > 0 and self.last_price:
            eq = round(e.equity(float(self.last_price)), 2)
            if not self.equity_curve or self.equity_curve[-1]["eq"] != eq:
                self.equity_curve.append({"t": (now or datetime.now(IST)).isoformat(timespec="seconds"), "eq": eq})
        d = self.state()
        d["bars"] = [chart_bar(b) for b in self.bars[-chart_window(self.strategy, len(self.bars)):]]
        return d

    def snapshot(self) -> dict:
        with self.lock:
            e = self.engine
            n = chart_window(self.strategy, len(self.bars))
            ctx = Ctx(self.bars, intraday=self.tf != "1d", base_min=TF_MIN.get(self.tf))
            overlays, osc = chart_series(self.strategy, ctx, len(self.bars) - n)
            view = self.bars[-n:]
            forming = self.builder.cur
            px = self.last_price
            return {
                "id": self.id, "name": self.name, "status": "running", "instrument": self.inst,
                "strategy": self.strategy.model_dump(), "started_at": self.started_at,
                "last_price": px, "last_tick_at": self.last_tick_at,
                "feed_connected": self.poll_ok if self.polled else self.mgr.hub.connected,
                "bars": [chart_bar(b) for b in view],
                "forming": None if not forming else {"t": forming["start"].isoformat(), "c": forming["c"]},
                "overlays": overlays, "oscillators": osc,
                "events": e.events[-200:],
                "equity_curve": self.equity_curve,
                "day_equity": risk.note_days(self.day_equity, self.equity_curve), "closed": risk.closed_list(e.trades),
                "account": {
                    "capital": self.strategy.risk.capital, "equity": e.equity(px), "cash": e.cash,
                    "qty": e.qty, "entry": e.entry if e.qty else None,
                    "stop": e.sl if e.qty and e.sl > 0 else None,
                    "side": "short" if e.dir == -1 else "long",
                    "target": e.tg if e.qty and e.tg != float("inf") else None,
                    "unrealised": e.dir * e.qty * (px - e.entry) - e.entry_cost if e.qty else 0.0,   # net of entry costs, as equity is
                    # the running totals (the trade list keeps only the newest after a restart), with the cash
                    # corporate actions paid, as a group counts them
                    "realised": e.realised_total + self.corp_cash, "corp_cash": self.corp_cash,
                    "trades": e.trade_count, "wins": e.win_count,
                    "emptied_on": e.emptied_on,
                },
            }


CHART_BARS, CHART_BARS_MAX = 150, 600


def chart_window(strategy, have: int) -> int:
    """How many of the newest candles the session's chart gets: 150, or enough that the longest average or indicator in the rules is drawn
    (an entry rule "price above SMA 200" has no line on a chart of 150 daily candles; the legend read "SMA 200 -", LIVE1A-012). The longest
    period is read from the rules' own references and the window is that plus a screenful, never above CHART_BARS_MAX."""
    longest = 0

    def walk(x):
        nonlocal longest
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("p", "m") and isinstance(v, (int, float)) and not isinstance(v, bool):
                    longest = max(longest, int(v))
                else:
                    walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    try:
        walk(strategy.model_dump() if hasattr(strategy, "model_dump") else strategy)
    except Exception:
        return min(CHART_BARS, have)
    return min(have, max(CHART_BARS, min(longest + 100, CHART_BARS_MAX)))


def chart_bar(b: dict) -> dict:
    """A candle as the session's chart gets it, with its volume when the feed gave one (DB-022: the chart's table had a
    Volume column of dashes)."""
    out = {k: b[k] for k in ("t", "o", "h", "l", "c")}
    if isinstance(b.get("v"), (int, float)) and not isinstance(b.get("v"), bool):
        out["v"] = b["v"]
    return out


def stopped_snapshot(row: dict) -> dict:
    """A stopped session as its page shows it, from the state kept at the stop. A position still open at the stop stays
    open ("Open paper positions are left as they are"), valued at the last price before the stop, so equity, return,
    unrealised P&L and the curve's last point agree (R11C-002: the page showed the cash alone, -97%, and no position). A
    session stopped before the last price was kept values it where the curve ends."""
    st = row.get("state") or {}
    strategy = row.get("strategy") or {}
    cap = (strategy.get("risk") or {}).get("capital") or 0
    realised, n_trades, wins = saved_totals(st)
    corp_cash = st.get("corp_cash", 0.0)
    cash = st.get("cash", cap)
    qty = st.get("qty") or 0
    d = st.get("dir") or 1
    entry = st.get("entry") or 0.0
    curve = st.get("equity_curve", [])
    px = st.get("last_price")
    if qty and not px and curve:
        px = (curve[-1]["eq"] - cash) / (d * qty)          # the price the curve's last point valued the position at
    held = bool(qty and px)
    bars = st.get("bars") or []
    overlays, osc = {}, {}
    if bars:
        try:
            ctx = Ctx(bars, intraday=strategy.get("tf") != "1d", base_min=TF_MIN.get(strategy.get("tf") or "1d"))
            overlays, osc = chart_series(Strategy(**strategy), ctx, 0)
        except Exception as e:                       # the candles without their lines rather than none
            print("stopped session lines:", row.get("id"), str(e)[:120])
    tg = st.get("tg")
    return {"id": row["id"], "name": row["name"], "status": row["status"], "stop_reason": row.get("stop_reason"),
            "instrument": row["instrument"], "strategy": strategy, "started_at": row["started_at"],
            "stopped_at": row.get("stopped_at"), "bars": bars, "overlays": overlays, "oscillators": osc,
            "last_price": px if held else (bars[-1]["c"] if bars else None),
            "events": st.get("events", []), "equity_curve": curve,
            "account": {"capital": cap, "equity": cash + d * qty * px if held else cash, "cash": cash,
                        "qty": qty if held else 0, "entry": entry if held else None,
                        "stop": st.get("sl") if held and (st.get("sl") or 0) > 0 else None,
                        "target": tg if held and tg is not None else None,
                        "side": "short" if d == -1 else "long",
                        "unrealised": d * qty * (px - entry) - (st.get("entry_cost") or 0.0) if held else 0.0,
                        "valued_at": px if held else None,
                        "realised": realised + corp_cash, "corp_cash": corp_cash, "trades": n_trades,
                        "wins": wins, "emptied_on": st.get("emptied_on")}}


class LimitError(Exception):
    pass


class LiveManager:
    def __init__(self, kite: KiteService, hub: TickHub, markets=None, options=None):
        self.kite, self.hub, self.markets, self.options = kite, hub, markets, options
        self.reporter = Reporter(db)
        self.sessions: dict[str, LiveSession] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stopped: set[str] = set()     # stopped here: a reconcile that read the row before the stop mustn't re-attach it
        self._last_sync = time.time()       # resume() has just read the rows: the first reconcile comes 30 s on
        self._attach_fails: dict[str, int] = {}     # consecutive failed attaches of a running row (a transient error is retried)

    # ---------- lifecycle ----------
    def start_loop(self):
        if not self._thread:
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def resume(self, rows: list[dict] | None = None):
        if not leader.leading():       # only the leader runs sessions; it picks these up itself
            return
        for row in db.running_sessions() if rows is None else rows:
            if row["id"] in self.sessions or row["id"] in self._stopped:
                continue
            if (row.get("instrument") or {}).get("market", "IN") in ("IN", "MCX", "CDS") and not self.kite.ready():
                continue  # resumes after today's Kite login; shown as paused until then
            try:
                self._attach(row)
                self._attach_fails.pop(row["id"], None)
            except ValueError as e:        # what the builders raise for good: no history, the market isn't connected
                self._attach_fails.pop(row["id"], None)
                db.update_session(row["id"], status="stopped", stopped_at=db.now_iso(),
                                  stop_reason=f"Could not resume after restart: {e}")
            except Exception as e:         # a timeout or a 503: the row stays running and the next reconcile tries again
                n = self._attach_fails[row["id"]] = self._attach_fails.get(row["id"], 0) + 1
                print(f"live resume of {row['id']} failed ({n}/{RESUME_TRIES}):", e)
                if n >= RESUME_TRIES:
                    self._attach_fails.pop(row["id"], None)
                    db.update_session(row["id"], status="stopped", stopped_at=db.now_iso(),
                                      stop_reason=f"Could not resume after restart ({RESUME_TRIES} tries in a row): the market's prices "
                                                  "couldn't be read.")   # the error itself goes to the log: it can name the data source

    def _attach(self, row: dict):
        s = self._build(row)
        with self._lock:
            if s.id in self.sessions:  # attached meanwhile (a start and a reconcile at once)
                return self.sessions[s.id]
            self.sessions[s.id] = s
        if s.dirty:                    # caught up on candles missed while the server was down
            self.persist([s])
        if hasattr(s, "attach"):
            s.attach(self.hub)
        elif not s.polled:
            self.hub.add(s.id, int(s.inst["token"]), s.on_tick)
        return s

    @staticmethod
    def row_kind(row: dict) -> str:
        """The kind of session a stored row runs as (what _build makes of it): signal, options, group or rules."""
        if (row.get("strategy") or {}).get("kind") == "signal":
            return "signal"
        return {"OPTIONS": "options", "GROUP": "group"}.get((row.get("instrument") or {}).get("type"), "rules")

    def _build(self, row: dict):
        kind = (row.get("instrument") or {}).get("type")
        if (row.get("strategy") or {}).get("kind") == "signal":      # moved by outside signals (signal_session.py)
            from .signal_session import SignalSession
            s = SignalSession(self, row)
        elif kind == "OPTIONS":
            from .options.session import OptionSession
            s = OptionSession(self, row, self.options)
        elif kind == "GROUP":
            from .group_live import GroupLiveSession
            s = GroupLiveSession(self, row)
        else:
            s = LiveSession(self, row)
        return s

    def user_running(self, user_id: str) -> list[LiveSession]:
        with self._lock:
            return [s for s in self.sessions.values() if s.user_id == user_id]

    def start(self, profile: dict, plan: str, strategy, inst: dict):
        limit = PLANS[plan]["live_limit"]
        lead = leader.leading()
        running = (len(self.user_running(profile["id"])) if lead else
                   db.count_running(profile["id"]))
        if running >= limit:
            raise LimitError(f"Your plan runs {limit} live strateg{'y' if limit == 1 else 'ies'} at a time. Stop one first.")
        row = db.create_session({
            "user_id": profile["id"], "name": strategy.name, "strategy": strategy.model_dump(),
            "instrument": inst, "status": "running",
        })
        try:
            if lead:
                return self._attach(row)
            # another container runs the sessions: built here only to check it can start; the leader attaches the
            # running row on its next reconcile, a few seconds from now
            s = self._build(row)
            s.snapshot = lambda snap=s.snapshot: {**snap(), "pending": True}
            return s
        except Exception as e:
            db.update_session(row["id"], status="stopped", stopped_at=db.now_iso(), stop_reason=str(e))
            raise

    def stop(self, sid: str, reason: str):
        s = self._detach(sid)
        if not s:
            return
        with s.lock:
            st = s.final_state() if hasattr(s, "final_state") else s.state()
        db.update_session(sid, status="stopped", stopped_at=db.now_iso(), stop_reason=reason, state=st)

    def _detach(self, sid: str):
        with self._lock:
            s = self.sessions.pop(sid, None)
            if s:
                self._stopped.add(sid)
        if not s:
            return None
        if hasattr(s, "detach"):
            s.detach(self.hub)
        elif not s.polled:
            self.hub.remove(sid)
        return s

    def reconcile(self):
        """Follow the database: attach running sessions started by another container, detach the ones stopped there
        (keeping their final state, as a stop here would)."""
        with self._lock:
            before = set(self.sessions)          # sessions attached after the read below are left alone
        index = db.running_index()           # id, owner and status only; the full rows (state and all) only for the new ones
        running = {r["id"] for r in index}
        for sid in before - running:
            s = self._detach(sid)
            if s:
                with s.lock:
                    st = s.final_state() if hasattr(s, "final_state") else s.state()
                db.update_session(sid, state=st)
        with self._lock:
            new = [i for i in running if i not in self.sessions and i not in self._stopped]
        self.resume(db.sessions_by_ids(new) if new else [])

    def drop_all(self):
        """Leadership lost: stop running every session here without saving (the new leader owns their rows)."""
        with self._lock:
            sids = list(self.sessions)
        for sid in sids:
            self._detach(sid)
        with self._lock:
            self._stopped.difference_update(sids)     # the next leader term may attach them again

    # ---------- orders and alerts ----------
    def replay(self, s, run):
        """Catch a resumed session up on the candles that closed while the server was down (`run` steps them): their
        orders are logged as usual, with one alert for them all."""
        s.replaying = evs = []
        try:
            run()
        finally:
            s.replaying = None
        if not evs:
            return

        def work():
            try:
                profile = db.get_profile(s.user_id)
                if alerts_on(profile):
                    shown = evs[:CATCH_UP_LINES]
                    cur = s.inst.get("currency", "INR")
                    lines = [f"{ev['side'].upper()} {ev['qty']:g} {ev.get('sym') or s.inst['symbol']} at {kit.money(ev['px'], cur, 2)} "
                             f"({ev.get('why') or 'order'}, candle {str(ev['t'])[:16].replace('T', ' ')})" for ev in shown]
                    if len(evs) > len(shown):
                        lines.append(f"and {len(evs) - len(shown)} more on the session page")
                    trade_notify(profile, f"{s.name}: {len(evs)} paper trade{'s' if len(evs) > 1 else ''} while offline",
                           f"StratLab caught up on candles that closed while the server was down ({s.name}):\n" + "\n".join(lines),
                           background=False, url=f"/paper/{s.id}")
            except Exception as e:
                print("catch-up alert failed:", e)
        threading.Thread(target=work, daemon=True).start()

    def on_order(self, s: LiveSession, ev: dict):
        self.on_orders(s, [ev])

    def on_orders(self, s: LiveSession, evs: list[dict], net: float | None = None):
        """Record orders placed together. An options session's legs open or close in one step: one alert for them, with
        the trade's net P&L (`net`) when the step closed it, so a four-leg structure doesn't use up the day's alerts."""
        caught_up = getattr(s, "replaying", None)
        if caught_up is not None:             # a candle missed while the server was down: one alert for them all
            caught_up.extend(evs)

        def work():
            if not leader.leading():
                return
            try:
                # the session's state is saved first, so a restart can't lose an order that was logged (or alerted)
                if s.id in self.sessions:
                    s.dirty = True
                    self.persist([s])
                for ev in evs:
                    if isinstance(ev["qty"], int):  # the orders table stores whole quantities; the session keeps every order
                        db.add_order({"session_id": s.id, "user_id": s.user_id, "side": ev["side"], "qty": ev["qty"],
                                      "price": round(ev["px"], 2), "reason": ev.get("why"), "pnl": ev.get("pnl"),
                                      "candle_time": ev["t"]})
                profile = db.get_profile(s.user_id)
                if caught_up is None and alerts_on(profile):
                    if getattr(s, "kind", "") == "options":
                        subject, text = structure_alert(s, evs, net)
                        trade_notify(profile, subject, text, background=False, url=f"/paper/{s.id}")
                        return
                    for ev in evs:
                        sym, cur = ev.get("sym") or s.inst["symbol"], s.inst.get("currency", "INR")
                        head = f"StratLab paper trade: {ev['side'].upper()} {ev['qty']:g} {sym} at {kit.money(ev['px'], cur, 2)}"
                        if ev.get("pnl") is None:      # opening a trade (a buy, a short sale or a written option)
                            text = f"{head} ({s.name})"
                        else:                          # closing one
                            why = f"{str(ev.get('why') or 'closed').lower()}, " if ev.get("why") else ""
                            text = f"{head}, {why}P&L {kit.money(ev['pnl'], cur, signed=True)} ({s.name})"
                        trade_notify(profile, f"{s.name}: {ev['side'].upper()} {sym}", text, background=False, url=f"/paper/{s.id}")
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
        if not leader.leading():
            return
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
        if t - self._last_sync > 30:
            self._last_sync = t
            try:
                self.reconcile()
            except Exception as e:
                print("live reconcile failed:", e)
        if t - self._last_persist > 30:
            self._last_persist = t
            self.persist(sessions)
        if t - self._last_plan > 60:
            self._last_plan = t
            self._enforce_plans(sessions)
            try:
                self.reporter.run(sessions, can_alert=report_on, market_name=market_name,
                                  send=lambda p, subj, body: notify(p, subj, body, background=False, unsub="daily_report"))
            except Exception as e:
                print("daily reports failed:", e)
                report(e, where="daily report")

    def persist(self, sessions: list[LiveSession] | None = None, only_dirty: bool = True):
        if not leader.leading():       # never write over the leader's state
            return
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
            plan = plan_of(profile)
            if plan == "free" and not trial_state(profile)["active"]:
                why = ("Free live trial ended. Upgrade to keep paper trading." if trial_state(profile)["started"] else
                       "The free launch offer has ended. Start the session again to use your free live trial, or upgrade.")
                for s in items:
                    self.stop(s.id, why)
                continue
            limit = PLANS[plan]["live_limit"]
            for s in sorted(items, key=lambda x: x.started_at)[limit:]:
                self.stop(s.id, "Plan limit reached after a plan change.")
            for s in items:
                if s.id not in self.sessions or not isinstance(s, LiveSession):
                    continue
                if not has_fno(plan) and needs_fno(s.inst):
                    self.stop(s.id, "Indian F&O is on Pro.")
                elif not has_indicators(plan) and needs_indicators(s.strategy):
                    self.stop(s.id, "This strategy uses Basic indicators.")
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
    if kind == "signal":
        if not allows(plan, "signal_webhooks"):
            return "Forward-testing outside signals"
        if needs_fno(s.inst) and not allows(plan, "fno"):
            return "Indian F&O"
    if kind == "options":
        if not allows(plan, "options"):
            return "Options paper trading"
        if getattr(s.strategy, "signal", None) and not allows(plan, "options_signal"):
            return "Options on a signal"
    return None


def alerts_on(profile: dict) -> bool:
    """A message for every paper trade: for anyone who turned alerts on and whose plan has them."""
    return bool(profile.get("alerts_enabled")) and allows(plan_of(profile), "alerts")


def trade_notify(profile: dict, subject: str, text: str, **kw):
    """notify, with at most TRADE_ALERTS_PER_DAY a day per user on email and Telegram (a runaway strategy shouldn't flood
    an inbox). Past it the phone still gets each one, and email and Telegram get one last line saying so."""
    uid, day = profile.get("id"), datetime.now(IST).date().isoformat()
    n = []

    def count(raw):
        have = db.json_value(raw, {})
        n[:] = [(have["n"] if have.get("day") == day else 0) + 1]
        return json.dumps({"day": day, "n": n[0]})
    try:
        db.update_setting(TRADE_ALERTS + uid, count)
    except Exception as e:
        print("trade alert count failed:", e)
        return notify(profile, subject, text, **kw)
    if n[0] <= TRADE_ALERTS_PER_DAY:
        return notify(profile, subject, text, **kw)
    url = kw.get("url", "/paper")
    sends = [j for c, j in alerts.jobs_for(profile, subject, text, url) if c == "push"]
    if n[0] == TRADE_ALERTS_PER_DAY + 1:
        sends += [j for c, j in alerts.jobs_for(profile, "StratLab: trade alert limit for today", TRADE_ALERTS_CAPPED, url)
                  if c != "push"]
    for job in sends:
        try:
            job()
        except Exception as e:
            print("alert failed:", e)
    return [] if not sends else ["push"]


def structure_alert(s, evs: list[dict], net: float | None) -> tuple[str, str]:
    """(subject, text) of the one alert for an options structure's orders in a step: its legs, and the trade's net P&L
    (after charges) when the step closed it, else the closed legs' P&L."""
    cur = s.inst.get("currency", "INR")
    opened, closed = [e for e in evs if e.get("pnl") is None], [e for e in evs if e.get("pnl") is not None]
    # what happened, from the outcome: a trade closed in the step (`net`) leaves no position, whatever opened on the way
    # (an entry abandoned when a leg couldn't open, a re-centre that couldn't open its new legs)
    if net is not None:
        word = "closed"
    elif opened and closed:
        word = "re-centred"               # the old legs closed and new ones opened: the position is still open
    elif opened:
        word = "opened"
    elif all(e.get("why") == "Leg stop" for e in closed):
        word = "leg stopped, position still open"
    else:
        word = "legs closed, position still open"
    legs = "; ".join(f"{e['side'].upper()} {e['qty']:g} {e.get('sym') or s.inst['symbol']} at {kit.money(e['px'], cur, 2)}" for e in evs)
    text = f"StratLab paper trade: {s.name} {word} ({len(evs)} order{'s' if len(evs) != 1 else ''}): {legs}"
    if closed:
        why = str((closed[-1] if net is not None else closed[0]).get("why") or "").lower()
        if net is not None:
            text += f". {why.capitalize() + ': ' if why else ''}net P&L {kit.money(net, cur, signed=True)} after charges"
        else:
            text += f". {why.capitalize() + ': ' if why else ''}P&L of the closed legs {kit.money(sum(e['pnl'] for e in closed), cur, signed=True)}"
    return f"{s.name}: {word}", text


def report_on(profile: dict) -> bool:
    """The daily report goes wherever alerts are set up (phone, Telegram or email), on plans that include it."""
    has_channel = bool(alerts.jobs_for(profile, "", ""))      # only channels the server can actually use
    return bool(has_channel) and allows(plan_of(profile), "daily_report")


def market_name(mid: str) -> str:
    return next((m["name"] for m in MARKETS if m["id"] == mid), mid)


def needs_fno(inst: dict | None) -> bool:
    """The instrument is an Indian future or option (Pro)."""
    return bool(inst and inst.get("fno"))


def needs_indicators(strategy: Strategy) -> bool:
    """The rules use an indicator beyond price, SMA, EMA and RSI (Basic and up)."""
    from .plans import BASIC_REFS
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
