"""Market breadth while the market is open: the same measures as the daily run, worked out every ~15 minutes from the
live prices the app already reads, for the Indian groups.

Each stock's finished days are kept by the daily run (breadth.base_row: its last close and the sums of its last 19, 49 and
199 closes). A live round is then arithmetic: one batched quote call per 500 stocks (paced), each price compared with the
previous close (advancers, decliners, unchanged) and with its 20-, 50- and 200-day averages, with today's price counted as
the latest close. Nothing else is read, so a round costs a handful of requests whatever the number of stocks.

Today's points are stored per group (breadth:live:<group>) and start afresh each trading day. The daily close numbers are
not touched. When live prices aren't available (the broker login has lapsed, or a round failed) the page says so and
shows the last close. Facts only: counts of stocks, never a view on the market."""
import json
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import breadth, db, leader

LIVE_KEY = "breadth:live:"           # breadth:live:<group> = {"day", "fields", "points": [[HH:MM, ...], ...]}
LIVE_STATUS_KEY = "breadth:livestatus"
EVERY = 15 * 60                      # seconds between rounds: one on each quarter hour of the clock (09:15, 09:30, ...)
STALE_AFTER = 40 * 60                # a newest point older than this is no longer "live"
LATE_AFTER = 20 * 60                 # ...and one older than this is still shown, said to be late (R24-002)
RETRY = 120                          # seconds before a failed round is tried again within its quarter hour
STARTUP = 45                         # seconds after the server starts before the first look (leader chosen, login loaded)
TICK = 20                            # seconds between looks at the clock
ROUND_BUDGET = 8 * 60                # a round still reading prices after this long gives up, so the next one is on time
BATCH = 500                          # stocks per quote call
PAUSE = 0.6                          # seconds between quote calls
KEEP_POINTS = 60                     # a day has 25 quarter hours; the cap only guards a runaway clock
IST = ZoneInfo("Asia/Kolkata")
OPEN_AT, CLOSE_AT = "09:15", "15:30"
COUNTS = ("adv", "dec", "unch", "a20", "n20", "a50", "n50", "a200", "n200")
# a point: [HH:MM, *COUNTS, the index level, the group's size, its stocks with no price today] (R24-003: the last two say
# why rose + fell + unchanged is short of the group: 2,344 of 2,563 on All NSE)
FIELDS = COUNTS + ("idx", "of", "unread")
LIVE_REGIONS = ("IN",)
SPLIT_GAP = 0.3                      # a previous close this far (as a share) from the stored last close is another basis (a split, a bonus)


def is_open(region: str, now: datetime) -> bool:
    """True from the open to the close on a trading day (India time)."""
    if region != "IN":
        return False
    from .data.calendar import is_trading_day
    local = now.astimezone(IST)
    return is_trading_day("IN", local.date()) and OPEN_AT <= local.strftime("%H:%M") <= CLOSE_AT


def slot_of(now: datetime) -> str:
    """The quarter hour of the clock a moment falls in, within the session: "09:15" from 09:15 to 09:29, "09:30" from
    09:30, ... "15:30" at the close."""
    local = now.astimezone(IST)
    m = local.hour * 60 + local.minute
    m -= m % 15
    lo, hi = int(OPEN_AT[:2]) * 60 + int(OPEN_AT[3:]), int(CLOSE_AT[:2]) * 60 + int(CLOSE_AT[3:])
    m = min(max(m, lo), hi)
    return f"{m // 60:02d}:{m % 60:02d}"


def _traded_before(at, day: str) -> bool:
    """A quote whose last trade is from a day before `day` (India time): the stock hasn't traded today."""
    if not at:
        return False
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return False
    return (t if t.tzinfo else t.replace(tzinfo=IST)).astimezone(IST).date().isoformat() < day


def count(base: dict[str, list], quotes: dict[str, dict], symbols: list[str], day: str | None = None) -> dict[str, int]:
    """One group's live counts. A stock needs a price and a previous close; an average counts the stock only when it has
    that many closes. Today's price is the latest close in each average. A stock whose previous close is over 30% from
    the stored last close (it went ex a split or bonus today; the stored averages are of the old prices) is counted for
    its day's move but left out of the averages. `unread`: the group's stocks with no price today: no quote came back
    (suspended, or not quoted under that symbol) or, with `day`, the last trade is from an earlier day (not traded yet
    today, R24-003: such a stock was counted as unchanged)."""
    out = dict.fromkeys(COUNTS, 0)
    out["of"], out["unread"] = len(symbols), 0
    for s in symbols:
        q = quotes.get(s) or {}
        b = base.get(s)
        try:
            px = float(q.get("price"))
        except (TypeError, ValueError):
            out["unread"] += 1
            continue
        prev = q.get("prev_close") or (b[0] if b else None)
        if not px > 0 or not prev or prev <= 0 or (day and _traded_before(q.get("at"), day)):
            out["unread"] += 1
            continue
        out["adv" if px > prev else "dec" if px < prev else "unch"] += 1
        if not b:
            continue
        if b[0] and abs(prev / b[0] - 1) > SPLIT_GAP:
            continue            # a split or bonus went ex today: the stored sums are of the old prices (the stock isn't below them)
        for k, total in ((20, b[2]), (50, b[3]), (200, b[4])):
            if total is None:
                continue
            out[f"n{k}"] += 1
            if px > (total + px) / k:
                out[f"a{k}"] += 1
    return out


def load(group: str, day: str) -> dict:
    try:
        raw = db.json_value(db.get_setting(LIVE_KEY + group), {})
    except Exception:
        return {"day": day, "points": []}
    return raw if raw.get("day") == day and isinstance(raw.get("points"), list) else {"day": day, "points": []}


def save(group: str, day: str, points: list[list]):
    db.set_setting(LIVE_KEY + group, json.dumps({"day": day, "fields": list(FIELDS), "points": points[-KEEP_POINTS:]}))


def status() -> dict:
    try:
        return db.json_value(db.get_setting(LIVE_STATUS_KEY), {})
    except Exception:
        return {}


def _set_status(region: str, **kw):
    s = status()
    s[region] = {**(s.get(region) or {}), **kw}
    db.set_setting(LIVE_STATUS_KEY, json.dumps(s))


class Live:
    """`quote(symbols)` gives {symbol: {price, prev_close}} for up to BATCH stocks (and indices) and may raise;
    `ready()` says whether live prices can be read at all; `rebuild(region, now)` is called when the stored finished days
    are missing or a day old (it should read them, paced, and store them with breadth.save_base)."""

    def __init__(self, quote, ready=lambda: True, rebuild=None, sleep=time.sleep, pause: float = PAUSE, clock=time.monotonic):
        self.quote, self.ready, self.rebuild, self.sleep, self.pause, self.clock = quote, ready, rebuild, sleep, pause, clock
        self.lock = threading.Lock()
        self.last_round: dict[str, float] = {}
        self.failed: dict[str, tuple[str, str, float]] = {}      # region -> (day, quarter hour, when) of the last failed round

    def round(self, region: str, now: datetime) -> dict:
        """One live round for a market: counts for each of its groups stored as a new point."""
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "error": "A live round is already going.", "busy": True}
        started = self.clock()
        try:
            res = self._round(region, now)
        finally:
            self.lock.release()
        local = now.astimezone(IST)
        if res.get("ok"):
            self.failed.pop(region, None)
        else:
            self.failed[region] = (local.date().isoformat(), slot_of(now), time.time())
        try:
            _set_status(region, slot=slot_of(now) if res.get("ok") else (status().get(region) or {}).get("slot"),
                        tried_at=breadth._now(), seconds=round(self.clock() - started, 1))
        except Exception:
            pass
        return res

    def done_slot(self, region: str, day: str) -> str | None:
        """The quarter hour of the day's last stored round (kept in the database, so a restart doesn't run it again and
        doesn't wait a quarter hour from its own start either)."""
        st = status().get(region) or {}
        if st.get("day") != day:
            return None
        return st.get("slot") or (slot_of(datetime.fromisoformat(f"{day}T{st['time']}:00").replace(tzinfo=IST)) if st.get("time") else None)

    def _round(self, region: str, now: datetime) -> dict:
        local = now.astimezone(IST)
        day, hhmm, slot = local.date().isoformat(), local.strftime("%H:%M"), slot_of(now)
        if not self.ready():
            _set_status(region, error="Live prices aren't available (the data login has lapsed).", failed_at=breadth._now())
            return {"ok": False, "error": "not ready"}
        expect = breadth.last_trading(region, breadth.last_complete(region, now))
        base = breadth.load_base(region)
        if (not base or base.get("day") != expect) and self.rebuild:
            try:
                self.rebuild(region, now)
            except Exception as e:
                print("breadth live base:", str(e)[:120])
            base = breadth.load_base(region)
        if not base or base.get("day") != expect:       # still old after a failed rebuild: its sums aren't today's base
            _set_status(region, error="Live prices aren't available (the day's base isn't read yet).", failed_at=breadth._now())
            return {"ok": False, "error": "no base"}
        stocks = (base or {}).get("stocks") or {}
        groups = [g for g, v in breadth.GROUPS.items() if v["region"] == region]
        who = {g: breadth.members(g) for g in groups}
        symbols = sorted({s for g in groups for s in who[g]})
        indexes = sorted({breadth.GROUPS[g]["index"] for g in groups})
        asked = symbols + [i for i in indexes if i not in symbols]
        quotes: dict[str, dict] = {}
        began = self.clock()
        try:
            for i in range(0, len(asked), BATCH):
                if i:
                    self.sleep(self.pause)
                if self.clock() - began > ROUND_BUDGET:
                    raise TimeoutError(f"still reading after {ROUND_BUDGET // 60} minutes")
                quotes.update(self.quote(asked[i:i + BATCH]) or {})
        except Exception as e:
            _set_status(region, error=f"Live prices could not be read ({str(e)[:100] or e.__class__.__name__}).", failed_at=breadth._now())
            return {"ok": False, "error": str(e)[:200]}
        got = sum(1 for s in symbols if (quotes.get(s) or {}).get("price"))
        if not got:
            _set_status(region, error="No live prices came back.", failed_at=breadth._now())
            return {"ok": False, "error": "no prices"}
        for g in groups:
            c = count(stocks, quotes, who[g], day)
            if not c["adv"] + c["dec"] + c["unch"]:
                continue
            idx = (quotes.get(breadth.GROUPS[g]["index"]) or {}).get("price")
            # a point is its quarter hour's ("10:30" for a round run at 10:31 or retried at 10:33): one point a quarter hour
            row = [slot, *(c[f] for f in COUNTS), round(float(idx), 2) if idx else None, c["of"], c["unread"]]
            pts = [p for p in load(g, day)["points"] if p[0] != slot] + [row]
            save(g, day, pts)
        self.last_round[region] = time.time()
        _set_status(region, at=breadth._now(), day=day, time=hhmm, quoted=got, stocks=len(symbols), error=None,
                    base_day=(base or {}).get("day"), calls=-(-len(asked) // BATCH))
        return {"ok": True, "region": region, "time": hhmm, "quoted": got, "stocks": len(symbols)}


class LiveJob:
    """A round on each quarter hour of the clock while a market is open (09:15, 09:30, ... 15:30), looked for every TICK
    seconds. R24-002: the next round was counted from the server's start and from the end of the last round, so a deploy
    at 09:24 IST put the first round at 09:42 and the next at 09:57, and "Live as of 09:15" stood for 27 minutes. Now the
    round of the current quarter hour runs as soon as it is due; after a restart, or a round that ran long, the quarter
    hour that is due runs at once (the missed ones can't be read after the fact); a failed round is tried again after RETRY
    seconds within its quarter hour."""

    def __init__(self, live: Live):
        self.live = live
        self.status: dict = {}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="breadth-live").start()

    def _loop(self):
        time.sleep(STARTUP)
        while True:
            try:
                if leader.leading():      # another container leads: it runs this pass
                    self.tick(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("breadth live:", str(e)[:160])
            time.sleep(TICK)

    def due(self, region: str, now: datetime) -> str | None:
        """The quarter hour a round is due for now, or None: the market is shut, the quarter hour's round is stored, or it
        failed under RETRY seconds ago."""
        if not is_open(region, now):
            return None
        day, slot = now.astimezone(IST).date().isoformat(), slot_of(now)
        done = self.live.done_slot(region, day)
        if done and done >= slot:
            return None
        failed = self.live.failed.get(region)
        if failed and failed[:2] == (day, slot) and time.time() - failed[2] < RETRY:
            return None
        return slot

    def tick(self, now: datetime) -> int:
        ran = 0
        for region in LIVE_REGIONS:
            slot = self.due(region, now)
            if slot is None:
                continue
            res = self.live.round(region, now)
            self.status.update(last_tick=now.isoformat(timespec="seconds"), last_slot=slot, last_ok=bool(res.get("ok")))
            ran += 1 if res.get("ok") else 0
        return ran


def rebuild_base(load_bars, region: str, now: datetime, gap: float = breadth.GAP, sleep=time.sleep) -> int:
    """Read each stock's recent daily candles (paced) and store the finished days the live rounds need. Used only when the
    daily run hasn't stored them for the last finished day. Returns how many stocks were read."""
    through = breadth.last_trading(region, breadth.last_complete(region, now))
    syms = sorted({s for g, v in breadth.GROUPS.items() if v["region"] == region for s in breadth.members(g)})
    stocks, streak = {}, 0
    for i, s in enumerate(syms):
        if i and gap:
            sleep(gap)
        try:
            row = breadth.base_row(load_bars(region, s, 330), through)
            streak = 0
        except Exception:
            streak += 1
            if streak >= breadth.GIVE_UP and not stocks:
                raise RuntimeError("the price source isn't answering")
            continue
        if row:
            stocks[s] = row
    if stocks:
        breadth.save_base(region, through, stocks)
    return len(stocks)


# ---------- what the page shows ----------
def view(group: str, now: datetime | None = None, ready: bool = True) -> dict | None:
    """The live card for a group, or None when there is nothing to say (a market that isn't covered, or closed).
    state "live": points from today, the newest not stale; "pending": the open's first round isn't stored yet (09:15 to
    09:29); "unavailable": the market is open but no fresh points."""
    g = breadth.GROUPS[group]
    now = now or datetime.now(ZoneInfo("UTC"))
    if g["region"] not in LIVE_REGIONS or not is_open(g["region"], now):
        return None
    local = now.astimezone(IST)
    day = local.date().isoformat()
    pts = load(group, day)["points"]
    fresh, age = False, None
    if pts:
        last = datetime.fromisoformat(f"{day}T{pts[-1][0]}:00").replace(tzinfo=IST)
        fresh = (local - last) <= timedelta(seconds=STALE_AFTER)
        age = max(0, int((local - last).total_seconds() // 60))
    # the open's first round not stored yet: it runs at the open and takes a few minutes, so that is said, not an outage
    first = not pts and ready and slot_of(now) == OPEN_AT
    out = {"state": "live" if pts and fresh and ready else "pending" if first else "unavailable", "day": day, "fields": list(FIELDS), "points": pts,
           "as_of": pts[-1][0] if pts else None, "latest": None, "message": None,
           "every_minutes": EVERY // 60, "age_minutes": age,
           # the newest point is over LATE_AFTER old while the market trades: the card says when it was, not "Live" (R24-002)
           "late": bool(pts and age is not None and age * 60 > LATE_AFTER)}
    if pts:
        out["latest"] = dict(zip(FIELDS, pts[-1][1:]))
        out["latest"]["pct20"] = breadth._pct(out["latest"]["a20"], out["latest"]["n20"])
        out["latest"]["pct50"] = breadth._pct(out["latest"]["a50"], out["latest"]["n50"])
        out["latest"]["pct200"] = breadth._pct(out["latest"]["a200"], out["latest"]["n200"])
    if first:
        out["message"] = "The first live count of the day is coming shortly. The numbers below are the last close."
    if out["state"] == "unavailable":
        out["message"] = ("Live prices aren't available right now, so there is no live breadth. The numbers below are the "
                          "last close." if not pts or not ready else
                          f"Live prices stopped updating after {pts[-1][0]}. The numbers below are the last close.")
        out["points"] = pts if ready else []
    return out
