"""India VIX: today's value and change, the intraday line, the daily history with where today sits in the past year,
and NIFTY's at-the-money IV beside it.

Where the numbers come from:
- Today's value, change, open, high and low: the exchange's index list (one call for every index, read at most once a
  minute), else the live feed's India VIX quote with the previous close from the stored history.
- The intraday line: the exchange's one-day index chart (minute points; the pre-open points are left out).
- The daily history: the exchange's India VIX history (open, high, low and close a day). It answers at most 70 days a
  request, so it is read in 90-calendar-day pieces: the last year at once on a new server, then further back a few
  pieces at a time outside market hours (back to FIRST_DAY), and each trading day's row after the close.
- NIFTY's ATM IV: the same number the Positioning page shows (positioning.atm_iv on the nearest expiry's chain, live
  or recorded), and its recorded daily history.

The history is stored a year to a row (vix:daily:<year> = {"YYYY-MM-DD": [open, high, low, close]}); it is market data
every user shares, so it lives in the market store (market_store.MARKET_PREFIXES).

Uses: the panel on Positioning and the Trade home (everyone); the "india_vix" and "india_vix_chg" rule values in
notebooks (engine/indicators.py reads closes() through a hook); and the entry filter on options sessions (the session
reads the live quote itself, options/engine.py).

A published index and arithmetic on it: nothing here says what a level of India VIX means for a trade, and no
"expected move" is worked out from it."""
import json
import threading
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from . import db
from .auth import current_profile
from .intel.net import TTLCache
from .newsletter import job as news_job
from .responses import err, ok

IST = timezone(timedelta(hours=5, minutes=30))
DAY_KEY = "vix:daily:"                 # vix:daily:<year> = {"YYYY-MM-DD": [open, high, low, close]}
STATE_KEY = "vix:state"                # {"back": the oldest day read so far, "done": True once FIRST_DAY is reached}
FIRST_DAY = date(2009, 3, 2)           # how far back the history is read (the exchange's series runs from 2008)
CHUNK = 90                             # calendar days a history request asks for (the exchange answers 70 rows at most)
STEP = 4                               # pieces of older history read per run, politely paced
PACE = 1.5                             # seconds between two history requests
LIVE_TTL = 60                          # the index list is read at most once a minute for everyone
GRAPH_TTL = 120
CLOSE_AT = "15:50"                     # India time: the day's row is read after this
YEAR_DAYS = 365                        # the percentile's window, in calendar days
MIN_DAYS = 60                          # stored days needed before the percentile means anything
RANGES = {"1y": 366, "3y": 1096, "5y": 1827, "all": 9000}
HIST_PATH, HIST_PAGE = "/api/historicalOR/vixhistory", "https://www.nseindia.com/reports-indices-historical-vix"
LIST_PATH, LIST_PAGE = "/api/allIndices", "https://www.nseindia.com/market-data/live-market-indices"
GRAPH_PATH = "/api/NextApi/apiClient"
NAME = "INDIA VIX"
NOTE = ("India VIX is the exchange's published volatility index, worked out from NIFTY option prices. Values as of the "
        "times shown. NIFTY ATM IV is StratLab's own model estimate from the nearest expiry's option prices. Facts, not "
        "advice.")

_cache = TTLCache(max_items=50)
_lock = threading.Lock()
_feed = {"fn": None, "first": 0.0}


def setup(feed_fn):
    """Where the exchange is read from (main.py's exchange client, or a test's fake)."""
    _feed["fn"] = feed_fn


def forget():
    """Drop the copies in memory (between tests)."""
    _cache.clear()
    _feed["first"] = 0.0


def _nse(feed=None):
    f = feed if feed is not None else (_feed["fn"]() if _feed["fn"] else None)
    if f is None:
        raise ValueError("no exchange client")
    return getattr(f, "nse", f)


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return x if 0 < x < 1000 else None


def _day(v) -> str | None:
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(v).strip(), fmt).date().isoformat()
        except (TypeError, ValueError):
            continue
    return None


# ---------- the exchange's answers ----------
def parse_history(data) -> dict[str, list]:
    """The exchange's India VIX history as {"YYYY-MM-DD": [open, high, low, close]}; rows without a date or a close are
    left out."""
    rows = data.get("data") if isinstance(data, dict) else data
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        d, c = _day(r.get("EOD_TIMESTAMP")), _num(r.get("EOD_CLOSE_INDEX_VAL"))
        if not d or c is None:
            continue
        out[d] = [_num(r.get("EOD_OPEN_INDEX_VAL")), _num(r.get("EOD_HIGH_INDEX_VAL")), _num(r.get("EOD_LOW_INDEX_VAL")), c]
    return out


def parse_quote(data) -> dict | None:
    """India VIX's row in the exchange's index list: the value now, the previous close, the change, the day's open,
    high and low, the 52-week range and the time of the list. None when the row isn't there."""
    rows = data.get("data") if isinstance(data, dict) else None
    row = next((r for r in rows or [] if isinstance(r, dict) and str(r.get("index") or "").upper() == NAME), None)
    v = _num(row.get("last")) if row else None
    if v is None:
        return None
    prev = _num(row.get("previousClose"))
    stamp = data.get("timestamp")
    as_of = None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M"):
        try:
            as_of = datetime.strptime(str(stamp).strip(), fmt).replace(tzinfo=IST).isoformat(timespec="minutes")
            break
        except (TypeError, ValueError):
            continue
    return {"value": v, "prev_close": prev, "change": round(v - prev, 2) if prev else None,
            "change_pct": round((v / prev - 1) * 100, 2) if prev else None, "open": _num(row.get("open")),
            "high": _num(row.get("high")), "low": _num(row.get("low")), "year_high": _num(row.get("yearHigh")),
            "year_low": _num(row.get("yearLow")), "as_of": as_of, "source": "exchange"}


def parse_graph(data) -> list[dict]:
    """The exchange's one-day chart as [{"t": ISO India time, "v"}], oldest first, without the pre-open points. Its
    times are India wall-clock times written as milliseconds since 1970."""
    d = data.get("data") if isinstance(data, dict) else None
    pts = (d or {}).get("grapthData") if isinstance(d, dict) else None
    out, seen = [], set()
    for p in pts if isinstance(pts, list) else []:
        if not isinstance(p, list) or len(p) < 2 or (len(p) > 2 and p[2] == "PO"):
            continue
        v = _num(p[1])
        try:
            t = datetime.fromtimestamp(int(p[0]) / 1000, timezone.utc).replace(tzinfo=IST)
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        key = t.isoformat(timespec="minutes")
        if v is None or key in seen:
            continue
        seen.add(key)
        out.append({"t": key, "v": v})
    out.sort(key=lambda x: x["t"])
    return out


# ---------- storage ----------
def _year_key(year: int) -> str:
    return f"{DAY_KEY}{year}"


def _load_year(year: int) -> dict:
    hit = _cache.get(("y", year))
    if hit is not None:
        return hit
    try:
        got = db.json_value(db.get_setting(_year_key(year)), {})
    except Exception:
        got = {}
    got = got if isinstance(got, dict) else {}
    _cache.set(("y", year), got, 600)
    return got


def store(rows: dict[str, list]) -> int:
    """Merge days into their years' rows. Returns how many days were stored."""
    by_year: dict[int, dict] = {}
    for d, v in rows.items():
        by_year.setdefault(int(d[:4]), {})[d] = v
    with _lock:
        for y, days in by_year.items():
            cur = db.json_value(db.get_setting(_year_key(y)), {})
            cur = cur if isinstance(cur, dict) else {}
            cur.update(days)
            db.set_setting(_year_key(y), json.dumps(dict(sorted(cur.items())), separators=(",", ":")))
            _cache.set(("y", y), cur, 600)
    _cache.set("closes", None, 0)          # read again on the next use
    return len(rows)


def daily(since: str | None = None, today: date | None = None) -> list[tuple[str, list]]:
    """Every stored day from `since` on, oldest first: (day, [open, high, low, close])."""
    today = today or datetime.now(IST).date()
    first = int(since[:4]) if since else FIRST_DAY.year
    out = []
    for y in range(max(first, FIRST_DAY.year), today.year + 1):
        out += [(d, v) for d, v in _load_year(y).items() if (not since or d >= since) and isinstance(v, list) and len(v) == 4]
    return sorted(out)


def closes() -> dict[str, float]:
    """{day: close} for every stored day: what the "india_vix" rule value reads (kept ten minutes)."""
    hit = _cache.get("closes")
    if hit:
        return hit
    out = {d: v[3] for d, v in daily() if v[3]}
    _cache.set("closes", out, 600)
    return out


def state() -> dict:
    got = db.json_value(db.get_setting(STATE_KEY), {})
    return got if isinstance(got, dict) else {}


def _set_state(**parts):
    st = state()
    st.update(parts)
    db.set_setting(STATE_KEY, json.dumps(st, separators=(",", ":")))


# ---------- reading the exchange ----------
def fetch(frm: date, to: date, feed=None, sleep=time.sleep, pace: float = PACE) -> dict[str, list]:
    """The history between two days, read in CHUNK-day pieces (each answer holds 70 days at most), each piece stored
    as soon as it's read, so a refusal half-way loses nothing."""
    nse = _nse(feed)
    got: dict[str, list] = {}
    d = frm
    while d <= to:
        end = min(to, d + timedelta(days=CHUNK - 1))
        rows = parse_history(nse._get(HIST_PATH, {"from": d.strftime("%d-%m-%Y"), "to": end.strftime("%d-%m-%Y")},
                                      referer=HIST_PAGE, circuit="vix"))
        if rows:
            store(rows)
        got.update(rows)
        d = end + timedelta(days=1)
        if d <= to and pace:
            sleep(pace)
    return got


def quote_now(feed=None) -> dict | None:
    """India VIX now from the exchange's index list, kept a minute for everyone."""
    hit = _cache.get("quote")
    if hit is not None:
        return hit or None
    try:
        q = parse_quote(_nse(feed)._get(LIST_PATH, {}, referer=LIST_PAGE, circuit="vix"))
    except Exception as e:
        print("india vix: index list", str(e)[:120])
        q = None
    _cache.set("quote", q or {}, LIVE_TTL if q else 20)
    return q


def intraday(feed=None) -> list[dict]:
    """Today's minute line from the exchange's one-day chart, kept two minutes."""
    hit = _cache.get("graph")
    if hit is not None:
        return hit
    try:
        pts = parse_graph(_nse(feed)._get(GRAPH_PATH, {"functionName": "getGraphChart", "type": NAME, "flag": "1D"},
                                          circuit="vix"))
    except Exception as e:
        print("india vix: intraday", str(e)[:120])
        pts = []
    _cache.set("graph", pts, GRAPH_TTL if pts else 30)
    return pts


def feed_quote(options_data, today: date) -> dict | None:
    """India VIX from the live feed, with the change worked out from the stored previous close: the stand-in when the
    exchange's index list can't be read."""
    from .options.engine import VIX_KEY
    try:
        if not options_data or not options_data.ready():
            return None
        q = options_data.quotes([VIX_KEY]).get(VIX_KEY) or {}
    except Exception:
        return None
    v = _num(q.get("ltp"))
    if v is None:
        return None
    prev = next((c[3] for d, c in reversed(daily((today - timedelta(days=15)).isoformat(), today)) if d < today.isoformat()), None)
    return {"value": v, "prev_close": prev, "change": round(v - prev, 2) if prev else None,
            "change_pct": round((v / prev - 1) * 100, 2) if prev else None, "open": None, "high": None, "low": None,
            "year_high": None, "year_low": None, "as_of": q.get("ts"), "source": "feed"}


# ---------- the arithmetic ----------
def percentile(value: float | None, past: list[float]) -> dict:
    """Where a value sits among past daily closes: the share of days that closed lower (0-100), with the lowest and
    highest. Empty until MIN_DAYS days are stored."""
    past = [v for v in past if isinstance(v, (int, float))]
    out = {"days": len(past), "need": MIN_DAYS, "percentile": None, "low": min(past) if past else None,
           "high": max(past) if past else None}
    if value is None or len(past) < MIN_DAYS:
        return out
    out["percentile"] = round(100 * sum(1 for v in past if v < value) / len(past), 1)
    return out


def nifty_iv(options_data, now: datetime) -> dict:
    """NIFTY's at-the-money IV now (the live chain, else the newest recording) and its recorded days for the last year."""
    from . import positioning
    today = None
    try:
        got = positioning.live_chain(options_data, "NFO", "NIFTY", "current") or \
            positioning.recorded_chain("NIFTY", "current", now.date())
        if got:
            at = datetime.fromisoformat(got["taken_at"]) if got["source"] == "recorded" else now
            iv = positioning.atm_iv(sorted(got["chain"], key=lambda r: r[0]), got.get("spot"), got["expiry"], at)
            today = {"iv": iv["iv"], "as_of": got["taken_at"], "source": got["source"], "at_close": bool(got.get("at_close"))} if iv else None
    except Exception as e:
        print("india vix: nifty iv", str(e)[:120])
    since = (now.date() - timedelta(days=YEAR_DAYS)).isoformat()
    series = [{"day": p["day"], "iv": p["atm_iv"]} for p in positioning.chain_series("NIFTY", since) if p.get("atm_iv") is not None]
    return {"today": today, "series": series}


def panel(options_data=None, now: datetime | None = None, feed=None) -> dict:
    """Everything the India VIX panel shows."""
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    today = now.date()
    q = quote_now(feed) or feed_quote(options_data, today)
    since = (today - timedelta(days=YEAR_DAYS)).isoformat()
    hist = daily(since, today)
    past = [v[3] for d, v in hist if d < today.isoformat()]
    value = q["value"] if q else (hist[-1][1][3] if hist else None)
    every = daily(today=today)
    return {"quote": q, "value": value, "intraday": intraday(feed), "history": [{"day": d, "close": v[3]} for d, v in hist],
            "percentile": percentile(value, past),
            "stored": {"days": len(every), "first": every[0][0] if every else None, "last": every[-1][0] if every else None},
            "nifty_iv": nifty_iv(options_data, now) if options_data is not None else {"today": None, "series": []},
            "note": NOTE, "today": today.isoformat()}


def history_view(rng: str, now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    since = (now.date() - timedelta(days=RANGES[rng])).isoformat()
    return {"range": rng, "points": [{"day": d, "open": v[0], "high": v[1], "low": v[2], "close": v[3]} for d, v in daily(since, now.date())]}


# ---------- the job ----------
class Job(news_job.Job):
    """Every five minutes: with nothing stored, read the last year at once; after each trading day's close, read the
    last fortnight (the day's row, and any day a restart missed); outside market hours, walk the history back a few
    pieces at a time until FIRST_DAY."""

    status_key = "vix"

    def __init__(self, feed_fn, sleep=time.sleep):
        super().__init__()
        self.feed_fn, self.sleep = feed_fn, sleep
        self.status.update(read=None, back=None)
        self._tried = 0.0

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="india-vix").start()

    def tick(self, now: datetime) -> int:
        local = now.astimezone(IST)
        today = local.date()
        feed = self.feed_fn()
        if not daily((today - timedelta(days=30)).isoformat(), today) and time.time() - self._tried > 1800:
            self._tried = time.time()
            n = len(fetch(today - timedelta(days=YEAR_DAYS + 5), today, feed, self.sleep))
            self.status.update(read=local.isoformat(timespec="minutes"), last_error=None)
            _set_state(back=(today - timedelta(days=YEAR_DAYS + 5)).isoformat())
            return n
        day = self.due("vix-close", now, "Asia/Kolkata", CLOSE_AT, region="IN")
        if day:
            got = fetch(day - timedelta(days=14), day, feed, self.sleep)
            if day.isoformat() in got or local.strftime("%H:%M") >= "21:00":
                self.mark("vix-close", day)
            self.status.update(read=local.isoformat(timespec="minutes"), last_run=now.isoformat(), last_error=None)
            return len(got)
        hhmm = local.strftime("%H:%M")
        st = state()
        if not ("09:00" <= hhmm <= "15:45") and not st.get("done"):
            back = date.fromisoformat(st["back"]) if st.get("back") else today - timedelta(days=YEAR_DAYS + 5)
            n = 0
            for _ in range(STEP):
                if back <= FIRST_DAY:
                    break
                frm = max(FIRST_DAY, back - timedelta(days=CHUNK))
                n += len(fetch(frm, back - timedelta(days=1), feed, self.sleep))
                back = frm
                self.sleep(PACE)
            _set_state(back=back.isoformat(), done=back <= FIRST_DAY)
            self.status["back"] = back.isoformat()
            return n
        return 0


def first_read(feed=None):
    """With nothing stored (a new server, before the job's first run), read the last year in the background, at most
    every half hour."""
    today = datetime.now(IST).date()
    if daily((today - timedelta(days=30)).isoformat(), today) or time.time() - _feed["first"] < 1800:
        return
    _feed["first"] = time.time()

    def work():
        try:
            fetch(today - timedelta(days=YEAR_DAYS + 5), today, feed)
        except Exception as e:
            print("india vix: first read", str(e)[:120])
    threading.Thread(target=work, daemon=True, name="india-vix-first").start()


# ---------- the routes ----------
router = APIRouter(prefix="/trade/vix", tags=["trade"])
_options = {"fn": None}


def use_options(fn):
    """Where the live option feed is (main.py's, or a test's): NIFTY's ATM IV beside India VIX, and the feed's quote
    when the exchange's index list can't be read."""
    _options["fn"] = fn


@router.get("")
def vix_panel(profile=Depends(current_profile)):
    """India VIX now, today's line, the last year's closes and where today sits among them, and NIFTY's ATM IV."""
    first_read()
    return ok(panel(_options["fn"]() if _options["fn"] else None))


@router.get("/history")
def vix_history(range: str = "1y", profile=Depends(current_profile)):
    """India VIX's stored daily open, high, low and close for a range."""
    if range not in RANGES:
        err(400, "bad_request", "Pick 1y, 3y, 5y or all.")
    return ok(history_view(range))
