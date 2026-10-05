"""The exchange's daily per-stock files, shared by the per-stock market desks: stock futures (stock_futures.py), stock
lending (slb.py) and margin-funded positions (mtf.py).

Each desk reads one trading day's files (the exchange's archive host, through the positioning feed's client: its
cookies, retry on a bot guard and its breaker), turns them into one small row per stock, and keeps:
- one row per day ({prefix}d:<YYYY-MM-DD> = {"rows": {symbol: row}, "meta": {...}}), for today's whole-market table;
- each stock's history in a few shards ({prefix}s:<n> = {symbol: [[day, ...point], ...]}), so one stock's year is one
  small read instead of a year of whole-market rows;
- the list of stored days ({prefix}days) and the desk's own state ({prefix}state: the last run, tries, the archive walk).

One job runs every desk: each evening after the files are out (retried every twenty minutes until they are), at any
other time it catches up on recent days a run missed, and outside market hours it walks the archive back a few days at
a time, politely paced. The cash market's closing prices (the exchange's cash bhavcopy) are read once per day for
every desk that needs them.

Facts and arithmetic only: nothing here reads a number as a signal."""
import csv
import gzip
import io
import json
import threading
import time
import zipfile
import zlib
from datetime import date, datetime, timedelta

from . import db
from .intel.net import SourceError, TTLCache, num
from .newsletter import job as news_job
from .positioning import IST, Feed, ist_now

ARCHIVE = "https://nsearchives.nseindia.com"
CASH_BHAV = ARCHIVE + "/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
CATCH_UP_DAYS = 10            # recent trading days a missed run looks back over
CATCH_UP_TRIES = 3            # times a recent day is asked for before it's taken as not published
BACKFILL_STEP = 6             # past days one archive walk reads, so a run never hammers the exchange
MISS_RUN = 6                  # trading days in a row the archive hasn't got: it's turning us away, not missing them
RETRY_MINUTES = 20
PACE = 1.5                    # seconds between two archive files
QUIET = ("09:00", "15:45")    # the archive walk rests while the market is open
_cache = TTLCache(max_items=400, max_bytes=48 * 1024 * 1024)
_lock = threading.Lock()


def clear_cache():
    _cache.clear()


# ---------- reading files ----------
def unpack(data: bytes | None, want: str = ".csv") -> str | None:
    """A file's text from what the archive sent: a zip (its first member ending in `want`), a gzip, or plain text."""
    if data is None:
        return None
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = [n for n in z.namelist() if n.lower().endswith(want)] or z.namelist()
                if not names:
                    return None
                data = z.read(names[0])
        except zipfile.BadZipFile:
            return None
    elif data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except OSError:
            return None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return data.decode(enc).replace("\x00", "")
        except UnicodeDecodeError:
            continue
    return None


class Files:
    """The exchange's archive files through the positioning feed (`Feed`): `text(url)` is the file's text, None when
    it isn't published (404, or a page instead of the file); an outage or a refusal raises SourceError."""

    def __init__(self, feed: Feed, sleep=time.sleep, pace: float = PACE):
        self.feed, self.sleep, self.pace = feed, sleep, pace
        self._asked = 0

    def text(self, url: str, want: str = ".csv") -> str | None:
        if self._asked and self.pace:
            self.sleep(self.pace)
        self._asked += 1
        return unpack(self.feed.raw(url), want)


def files_of(feed_fn, sleep=time.sleep, pace: float = PACE) -> Files:
    """Files from whatever main.py hands the desks: the exchange client (filings_feed, or its NSE part)."""
    f = feed_fn()
    if isinstance(f, Files):
        return f
    if not isinstance(f, Feed):
        f = Feed(getattr(f, "nse", f), sleep=sleep)
    return Files(f, sleep=sleep, pace=pace)


def dmy(d: date) -> str:
    return d.strftime("%d%m%Y")


def rows_of(text: str) -> list[dict]:
    """A CSV's rows with stripped header names and values."""
    reader = csv.DictReader(io.StringIO(text))
    return [{str(k or "").strip(): str(v or "").strip() for k, v in r.items() if k is not None} for r in reader]


def cash_rows(text: str) -> dict[str, dict]:
    """The cash market's common bhavcopy: {symbol: {"close", "prev", "series"}} for the equity series (EQ, BE, BZ, SM,
    ST). A file without that shape is an error."""
    out: dict[str, dict] = {}
    rows = rows_of(text)
    if rows and "TckrSymb" not in rows[0]:
        raise ValueError("not the cash bhavcopy")
    for r in rows:
        sym, series = r.get("TckrSymb", "").upper(), r.get("SctySrs", "").upper()
        if not sym or series not in ("EQ", "BE", "BZ", "SM", "ST"):
            continue
        close = num(r.get("ClsPric")) or num(r.get("LastPric"))
        if close is None or close <= 0:
            continue
        if sym in out and out[sym]["series"] == "EQ":
            continue                                    # a stock's main line wins over its other series
        out[sym] = {"close": close, "prev": num(r.get("PrvsClsgPric")), "series": series}
    return out


def cash_closes(files: Files, day: date) -> dict[str, dict] | None:
    """A day's cash-market closes, read once and kept in memory for every desk that needs them; None when the file
    isn't published."""
    key = ("cash", day.isoformat())
    hit = _cache.get(key)
    if hit is not None:
        return hit or None
    text = files.text(CASH_BHAV.format(ymd=day.strftime("%Y%m%d")))
    if text is None:
        _cache.set(key, {}, 600)
        return None
    try:
        got = cash_rows(text)
    except ValueError:
        raise SourceError("the exchange", "The exchange's cash bhavcopy wasn't in the expected shape.") from None
    _cache.set(key, got, 6 * 3600)
    return got


# ---------- storage ----------
def _load(key: str, default, ttl: float = 300):
    hit = _cache.get(("k", key))
    if hit is not None:
        return hit
    try:
        v = db.json_value(db.get_setting(key), default)
    except Exception:
        return default
    _cache.set(("k", key), v, ttl)
    return v


def _save(key: str, value):
    db.set_setting(key, json.dumps(value, separators=(",", ":")))
    _cache.set(("k", key), value, 300)


class DayStore:
    """One desk's days, kept as described above. `point(row)` is what a stock's history keeps for one day (a short
    list); `keep` is how many trading days are kept."""

    def __init__(self, prefix: str, keep: int, point=None, shards: int = 16):
        self.prefix, self.keep, self.shards = prefix, keep, shards
        self.point = point or (lambda row: row)

    def _shard(self, symbol: str) -> str:
        return f"{self.prefix}s:{zlib.crc32(symbol.encode()) % self.shards}"

    def days(self) -> list[str]:
        return [d for d in _load(self.prefix + "days", {}).get("days") or [] if isinstance(d, str)]

    def get(self, day: str) -> dict | None:
        rec = _load(f"{self.prefix}d:{day}", {}, 3600)
        return rec if rec.get("rows") is not None else None

    def latest(self, before: str | None = None) -> tuple[str, dict] | None:
        for d in reversed(self.days()):
            if before is None or d < before:
                rec = self.get(d)
                if rec:
                    return d, rec
        return None

    def has(self, day: str) -> bool:
        return day in set(self.days())

    def put(self, day: str, rows: dict, meta: dict | None = None):
        self.put_many([(day, rows, meta or {})])

    def put_many(self, items: list[tuple[str, dict, dict]]):
        """Store several days at once: each day's row, then every shard touched once."""
        if not items:
            return
        with _lock:
            for day, rows, meta in items:
                _save(f"{self.prefix}d:{day}", {"rows": rows, "meta": meta or {}})
            idx = db.json_value(db.get_setting(self.prefix + "days"), {})
            days = sorted(set(idx.get("days") or []) | {d for d, _, _ in items})
            drop = days[:-self.keep] if len(days) > self.keep else []
            days = days[len(drop):]
            cut = days[0] if days else None
            by_shard: dict[str, dict[str, dict[str, list]]] = {}
            for day, rows, _ in items:
                for sym, row in rows.items():
                    p = self.point(row)
                    if p is not None:
                        by_shard.setdefault(self._shard(sym), {}).setdefault(sym, {})[day] = p
            touched = set(by_shard)
            if drop:
                touched |= {f"{self.prefix}s:{i}" for i in range(self.shards)}
            for key in sorted(touched):
                cur = db.json_value(db.get_setting(key), {})
                for sym, new in by_shard.get(key, {}).items():
                    old = {s[0]: s[1:] for s in cur.get(sym) or [] if isinstance(s, list) and s}
                    old.update({d: list(p) for d, p in new.items()})
                    cur[sym] = [[d, *old[d]] for d in sorted(old)]
                if cut:
                    cur = {s: kept for s, ser in cur.items() if (kept := [x for x in ser if x[0] >= cut])}
                _save(key, cur)
            _save(self.prefix + "days", {"days": days})
            for d in drop:
                try:
                    db.delete_setting(f"{self.prefix}d:{d}")
                except Exception:
                    pass
                _cache.set(("k", f"{self.prefix}d:{d}"), {}, 60)

    def series(self, symbol: str, since: str | None = None) -> list[list]:
        """One stock's stored points, oldest first: [[day, ...point], ...]."""
        ser = _load(self._shard(symbol), {}).get(symbol) or []
        return [s for s in ser if isinstance(s, list) and s and (not since or s[0] >= since)]

    def all_series(self) -> dict[str, list[list]]:
        """Every stock's points (the whole-market table's streaks): every shard, cached."""
        out = {}
        for i in range(self.shards):
            out.update(_load(f"{self.prefix}s:{i}", {}))
        return out

    def state(self) -> dict:
        return _load(self.prefix + "state", {})

    def set_state(self, **parts):
        with _lock:
            st = db.json_value(db.get_setting(self.prefix + "state"), {})
            st.update(parts)
            _save(self.prefix + "state", st)


# ---------- the days ----------
def trading(d: date) -> bool:
    from .data.calendar import is_trading_day
    return is_trading_day("IN", d)


def prev_trading(d: date) -> date:
    d -= timedelta(days=1)
    for _ in range(15):
        if trading(d):
            return d
        d -= timedelta(days=1)
    return d


def expected(now: datetime, ready_at: str, lag: int = 0) -> date | None:
    """The newest trading day whose file should be out by `now`: today after `ready_at` (India time), else the trading
    day before; `lag` trading days further back for a file published a day late (the margin trading disclosure)."""
    local = now.astimezone(IST)
    d = local.date() if local.strftime("%H:%M") >= ready_at else local.date() - timedelta(days=1)
    for _ in range(15):
        if trading(d):
            break
        d -= timedelta(days=1)
    else:
        return None
    for _ in range(lag):
        d = prev_trading(d)
    return d


def day_words(iso: str | None) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day} {d:%b %Y}"


def status(desk, now: datetime | None = None) -> dict:
    """Whether the newest stored day is the one expected, and a line on why not: for the pages' "as of" line."""
    now = now or ist_now()
    exp = expected(now, desk.ready_at, desk.lag)
    got = desk.store.days()
    have = got[-1] if got else None
    st = desk.store.state()
    out = {"as_of": have, "expected": exp.isoformat() if exp else None, "days": len(got), "first": got[0] if got else None,
           "checked": st.get("checked"), "error": st.get("error"),
           "backfill_done": bool((st.get("backfill") or {}).get("done")), "backfill_target": desk.backfill_days}
    if have and exp and have >= exp.isoformat():
        out["status"], out["reason"] = "ok", None
    elif st.get("error"):
        out["status"] = "pending" if have else "none"
        out["reason"] = f"The last try ({day_words(st.get('checked'))}, {str(st.get('checked'))[11:16]} IST) didn't get it: {st['error']}"
    elif not have:
        out["status"] = "none"
        out["reason"] = (f"Not read yet. StratLab reads the exchange's {desk.what} each trading evening once it's published, "
                         f"and catches up within {RETRY_MINUTES} minutes when a run was missed.")
    else:
        out["status"] = "pending"
        out["reason"] = f"The exchange hasn't published {day_words(exp.isoformat() if exp else None)}'s {desk.what} yet."
    return out


def mine(uid: str, limit: int = 120) -> tuple[list[str], list[str]]:
    """(the user's Indian holdings, largest first; their Indian watchlist), as exchange symbols, at most `limit` all told."""
    ok = lambda s: bool(s) and len(s) <= 20 and all(ch.isalnum() or ch in "&-" for ch in s)     # noqa: E731
    try:
        from . import holdings
        held = [s.upper() for s in holdings.symbols(uid)]
    except Exception:
        held = []
    try:
        from .intel.filings import watchlist_symbols
        watch = [s.upper() for s in watchlist_symbols(uid, "IN")]
    except Exception:
        watch = []
    held = [s for s in dict.fromkeys(held) if ok(s)][:limit]
    watch = [s for s in dict.fromkeys(watch) if ok(s) and s not in held][:max(0, limit - len(held))]
    return held, watch


# ---------- the desks and the run ----------
class Desk:
    """One kind of daily file. A desk says where its days are kept (`store`), when the file is out (`ready_at`,
    India time, `lag` trading days late), how far back the archive is walked (`backfill_days`), and reads one day:
    `read(files, day)` -> (rows, meta), or None when the day's file isn't published. `after(day, rows, prev_rows)`
    returns the alert events of a newly stored newest day."""
    name = "desk"
    what = "file"
    ready_at = "19:00"
    lag = 0
    backfill_days = 120
    store: DayStore

    def read(self, files: Files, day: date) -> tuple[dict, dict] | None:
        raise NotImplementedError

    def after(self, day: str, rows: dict, prev: dict | None) -> list[dict]:
        return []


class Runner:
    """Reads the desks' days: the newest ones a run missed (catch_up) and the archive, a few days at a time (backfill).
    Every day is stored as soon as it's read, so a stop half-way loses nothing."""

    def __init__(self, desks: list[Desk], feed_fn, sleep=time.sleep, pace: float = PACE, fire=None):
        self.desks = {d.name: d for d in desks}
        self.feed_fn, self.sleep, self.pace = feed_fn, sleep, pace
        self.fire = fire or (lambda events, now: 0)
        self.running = False

    def _files(self) -> Files:
        return files_of(self.feed_fn, self.sleep, self.pace)

    def _read(self, desk: Desk, files: Files, day: date) -> tuple[str, tuple | None]:
        try:
            got = desk.read(files, day)
        except SourceError as e:
            return str(e)[:200], None
        except (ValueError, KeyError, TypeError) as e:
            return f"The exchange's {desk.what} wasn't in the expected shape ({str(e)[:80]}).", None
        if got is None:
            return "missing", None
        return "ok", (day.isoformat(), got[0], got[1])

    def read_day(self, desk: Desk, files: Files, day: date) -> str:
        """Read and store one day: "ok", "missing" (not published) or the error, in a line."""
        r, got = self._read(desk, files, day)
        if got:
            desk.store.put_many([got])
        return r

    def catch_up(self, desk: Desk, now: datetime | None = None) -> dict:
        """The recent trading days the store hasn't got, newest first; a newly stored newest day fires its alerts."""
        now = now or ist_now()
        exp = expected(now, desk.ready_at, desk.lag)
        if not exp:
            return {}
        st = desk.store.state()
        tries = dict(st.get("tries") or {})
        have = set(desk.store.days())
        res: dict = {}
        files = None
        d = exp
        stop = exp - timedelta(days=CATCH_UP_DAYS)
        self.running = True
        try:
            while d > stop:
                key = d.isoformat()
                if trading(d) and key not in have and tries.get(key, 0) < CATCH_UP_TRIES:
                    files = files or self._files()
                    r = self.read_day(desk, files, d)
                    res[key] = r
                    if r == "missing":
                        tries[key] = tries.get(key, 0) + 1
                    elif r != "ok":
                        break                           # busy or refusing: the next run tries again
                d -= timedelta(days=1)
        finally:
            self.running = False
        stamp = now.astimezone(IST).isoformat(timespec="minutes")
        bad = next((r for r in res.values() if r not in ("ok", "missing")), None)
        cut = stop.isoformat()
        desk.store.set_state(checked=stamp if res else st.get("checked"), error=bad if res else st.get("error"),
                             tries={k: v for k, v in tries.items() if k > cut})
        if res.get(exp.isoformat()) == "ok":
            rec = desk.store.get(exp.isoformat()) or {}
            prev = desk.store.latest(before=exp.isoformat())
            try:
                events = desk.after(exp.isoformat(), rec.get("rows") or {}, (prev[1].get("rows") if prev else None))
                if events:
                    res["alerts"] = self.fire(events, now)
            except Exception as e:
                print(f"{desk.name}: alerts", str(e)[:160])
        return res

    def backfill(self, desk: Desk, today: date, step: int = BACKFILL_STEP, days: int | None = None) -> dict:
        """Read up to `step` more past days, walking back from the oldest one tried; done when it reaches the desk's
        depth. Five days in a row the archive hasn't got is the archive turning us away: the next run tries them again
        (three times), then passes them by."""
        days = desk.backfill_days if days is None else days
        st = desk.store.state()
        bf = dict(st.get("backfill") or {})
        if bf.get("done"):
            return bf
        stop = today - timedelta(days=int(days * 7 / 5) + 10)       # trading days to calendar days, with holidays
        d = date.fromisoformat(bf["next"]) if bf.get("next") else prev_trading(today)
        have = set(desk.store.days())
        read, misses, streak = 0, 0, None
        stuck = dict(bf.get("stuck") or {})
        files = None
        batch: list[tuple] = []
        self.running = True
        try:
            while d >= stop and read < step:
                if trading(d) and d.isoformat() not in have:
                    files = files or self._files()
                    r, got = self._read(desk, files, d)
                    if got:
                        batch.append(got)
                    if r not in ("ok", "missing"):
                        bf["error"] = r
                        break
                    read += 1
                    bf["read"] = bf.get("read", 0) + (r == "ok")
                    misses, streak = (misses + 1, streak or d) if r == "missing" else (0, None)
                    if misses >= MISS_RUN and stuck.get(streak.isoformat(), 0) < 3:
                        stuck = {streak.isoformat(): stuck.get(streak.isoformat(), 0) + 1}
                        bf["stuck"] = stuck
                        bf["error"] = f"The archive had none of {MISS_RUN} trading days in a row from {day_words(streak.isoformat())}; trying again later."
                        d = streak
                        break
                d -= timedelta(days=1)
            else:
                bf.pop("error", None)
        finally:
            desk.store.put_many(batch)                  # the days read so far, every shard written once
            self.running = False
        bf["next"] = d.isoformat()
        if d < stop or len(desk.store.days()) >= desk.store.keep:
            bf["done"] = True
        desk.store.set_state(backfill=bf)
        return bf


class Job(news_job.Job):
    """Every five minutes, for each desk: when the newest expected day isn't stored, read it (at most every twenty
    minutes, so an evening before publication asks a few times, then again after); outside market hours, walk the
    archive back a few days. A restart loses nothing: what's stored says what's left."""

    def __init__(self, runner: Runner):
        super().__init__()
        self.runner = runner
        self._tried: dict[str, float] = {}
        self.status.update(desks={})

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="stock-desks").start()

    def tick(self, now: datetime) -> int:
        if self.runner.running:
            return 0
        local = now.astimezone(IST)
        hhmm = local.strftime("%H:%M")
        for name, desk in self.runner.desks.items():
            try:
                exp = expected(now, desk.ready_at, desk.lag)
                days = desk.store.days()
                behind = exp is not None and (not days or days[-1] < exp.isoformat())
                if behind and time.time() - self._tried.get(name, 0.0) >= RETRY_MINUTES * 60:
                    self._tried[name] = time.time()
                    self.status["desks"][name] = {"catch_up": self.runner.catch_up(desk, now), "at": now.isoformat()}
                elif not (QUIET[0] <= hhmm <= QUIET[1]) and not (desk.store.state().get("backfill") or {}).get("done"):
                    self.status["desks"].setdefault(name, {})["backfill"] = self.runner.backfill(desk, local.date())
            except Exception as e:
                self.status["last_error"] = f"{name}: {str(e)[:180]}"
        self.status["last_run"] = now.isoformat()
        return 0
