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

from . import breadth, db

LIVE_KEY = "breadth:live:"           # breadth:live:<group> = {"day", "fields", "points": [[HH:MM, ...], ...]}
LIVE_STATUS_KEY = "breadth:livestatus"
EVERY = 15 * 60                      # seconds between rounds
STALE_AFTER = 40 * 60                # a newest point older than this is no longer "live"
BATCH = 500                          # stocks per quote call
PAUSE = 0.6                          # seconds between quote calls
KEEP_POINTS = 60                     # a day has 25 quarter hours; the cap only guards a runaway clock
IST = ZoneInfo("Asia/Kolkata")
OPEN_AT, CLOSE_AT = "09:15", "15:30"
FIELDS = ("adv", "dec", "unch", "a20", "n20", "a50", "n50", "a200", "n200", "idx")
LIVE_REGIONS = ("IN",)


def is_open(region: str, now: datetime) -> bool:
    """True from the open to the close on a trading day (India time)."""
    if region != "IN":
        return False
    from .data.calendar import is_trading_day
    local = now.astimezone(IST)
    return is_trading_day("IN", local.date()) and OPEN_AT <= local.strftime("%H:%M") <= CLOSE_AT


def count(base: dict[str, list], quotes: dict[str, dict], symbols: list[str]) -> dict[str, int]:
    """One group's live counts. A stock needs a price and a previous close; an average counts the stock only when it has
    that many closes. Today's price is the latest close in each average."""
    out = dict.fromkeys(FIELDS[:-1], 0)
    for s in symbols:
        q = quotes.get(s) or {}
        b = base.get(s)
        try:
            px = float(q.get("price"))
        except (TypeError, ValueError):
            continue
        prev = q.get("prev_close") or (b[0] if b else None)
        if not px > 0 or not prev or prev <= 0:
            continue
        out["adv" if px > prev else "dec" if px < prev else "unch"] += 1
        if not b:
            continue
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

    def __init__(self, quote, ready=lambda: True, rebuild=None, sleep=time.sleep, pause: float = PAUSE):
        self.quote, self.ready, self.rebuild, self.sleep, self.pause = quote, ready, rebuild, sleep, pause
        self.lock = threading.Lock()
        self.last_round: dict[str, float] = {}

    def round(self, region: str, now: datetime) -> dict:
        """One live round for a market: counts for each of its groups stored as a new point."""
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "error": "A live round is already going."}
        try:
            return self._round(region, now)
        finally:
            self.lock.release()

    def _round(self, region: str, now: datetime) -> dict:
        local = now.astimezone(IST)
        day, hhmm = local.date().isoformat(), local.strftime("%H:%M")
        if not self.ready():
            _set_status(region, error="Live prices aren't available (the data login has lapsed).", failed_at=breadth._now())
            return {"ok": False, "error": "not ready"}
        expect = breadth.last_complete(region, now)
        base = breadth.load_base(region)
        if (not base or base.get("day") != expect) and self.rebuild:
            try:
                self.rebuild(region, now)
            except Exception as e:
                print("breadth live base:", str(e)[:120])
            base = breadth.load_base(region)
        stocks = (base or {}).get("stocks") or {}
        groups = [g for g, v in breadth.GROUPS.items() if v["region"] == region]
        who = {g: breadth.members(g) for g in groups}
        symbols = sorted({s for g in groups for s in who[g]})
        indexes = sorted({breadth.GROUPS[g]["index"] for g in groups})
        asked = symbols + [i for i in indexes if i not in symbols]
        quotes: dict[str, dict] = {}
        try:
            for i in range(0, len(asked), BATCH):
                if i:
                    self.sleep(self.pause)
                quotes.update(self.quote(asked[i:i + BATCH]) or {})
        except Exception as e:
            _set_status(region, error=f"Live prices could not be read ({str(e)[:100] or e.__class__.__name__}).", failed_at=breadth._now())
            return {"ok": False, "error": str(e)[:200]}
        got = sum(1 for s in symbols if (quotes.get(s) or {}).get("price"))
        if not got:
            _set_status(region, error="No live prices came back.", failed_at=breadth._now())
            return {"ok": False, "error": "no prices"}
        for g in groups:
            c = count(stocks, quotes, who[g])
            if not c["adv"] + c["dec"] + c["unch"]:
                continue
            idx = (quotes.get(breadth.GROUPS[g]["index"]) or {}).get("price")
            row = [hhmm, *(c[f] for f in FIELDS[:-1]), round(float(idx), 2) if idx else None]
            pts = [p for p in load(g, day)["points"] if p[0] != hhmm] + [row]
            save(g, day, pts)
        self.last_round[region] = time.time()
        _set_status(region, at=breadth._now(), day=day, time=hhmm, quoted=got, stocks=len(symbols), error=None,
                    base_day=(base or {}).get("day"), calls=-(-len(asked) // BATCH))
        return {"ok": True, "region": region, "time": hhmm, "quoted": got, "stocks": len(symbols)}


class LiveJob:
    """Every minute: if a market is open and the last round is a quarter of an hour old, make a new one."""

    def __init__(self, live: Live):
        self.live = live
        self.status: dict = {}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="breadth-live").start()

    def _loop(self):
        time.sleep(900)
        while True:
            try:
                self.tick(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("breadth live:", str(e)[:160])
            time.sleep(60)

    def tick(self, now: datetime) -> int:
        ran = 0
        for region in LIVE_REGIONS:
            if not is_open(region, now) or time.time() - self.live.last_round.get(region, 0) < EVERY:
                continue
            res = self.live.round(region, now)
            if not res.get("ok"):
                self.live.last_round[region] = time.time() - EVERY + 120      # try again in two minutes, not a quarter hour
            ran += 1 if res.get("ok") else 0
        return ran


def rebuild_base(load_bars, region: str, now: datetime, gap: float = breadth.GAP, sleep=time.sleep) -> int:
    """Read each stock's recent daily candles (paced) and store the finished days the live rounds need. Used only when the
    daily run hasn't stored them for the last finished day. Returns how many stocks were read."""
    through = breadth.last_complete(region, now)
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
    state "live": points from today, the newest not stale; "unavailable": the market is open but no fresh points."""
    g = breadth.GROUPS[group]
    now = now or datetime.now(ZoneInfo("UTC"))
    if g["region"] not in LIVE_REGIONS or not is_open(g["region"], now):
        return None
    local = now.astimezone(IST)
    day = local.date().isoformat()
    pts = load(group, day)["points"]
    fresh = False
    if pts:
        last = datetime.fromisoformat(f"{day}T{pts[-1][0]}:00").replace(tzinfo=IST)
        fresh = (local - last) <= timedelta(seconds=STALE_AFTER)
    out = {"state": "live" if pts and fresh and ready else "unavailable", "day": day, "fields": list(FIELDS), "points": pts,
           "as_of": pts[-1][0] if pts else None, "latest": None, "message": None,
           "every_minutes": EVERY // 60}
    if pts:
        out["latest"] = dict(zip(FIELDS, pts[-1][1:]))
        out["latest"]["pct20"] = breadth._pct(out["latest"]["a20"], out["latest"]["n20"])
        out["latest"]["pct50"] = breadth._pct(out["latest"]["a50"], out["latest"]["n50"])
        out["latest"]["pct200"] = breadth._pct(out["latest"]["a200"], out["latest"]["n200"])
    if out["state"] == "unavailable":
        out["message"] = ("Live prices aren't available right now, so there is no live breadth. The numbers below are the "
                          "last close." if not pts or not ready else
                          f"Live prices stopped updating after {pts[-1][0]}. The numbers below are the last close.")
        out["points"] = pts if ready else []
    return out
