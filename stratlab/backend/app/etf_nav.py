"""Indian ETFs' market price against their NAV: the gap between what a unit trades at and what it holds, as a percent.

Two values to compare with:
- the last NAV the fund house published (the industry body's daily NAV file, which money_mf_nav.py already reads),
  matched to the ETF by its ISIN, else the last NAV the exchange's ETF list gives with its date;
- the indicative NAV (iNAV), the estimate from the holdings' live prices, when a source gives one.

The exchange's ETF list (price and last NAV of every ETF, one call; checked live in October 2026, its "nav" is the
published NAV, not an iNAV) is read every few minutes while the market is open and kept in one app_settings row. It
carries no ISIN: those come from the exchange's ETF securities file (read once a day). After each close the day's closing price is stored with that day's NAV (filled
in when the evening NAV file has it), one row a day, so each ETF has a 30-day history of the gap.

Facts and arithmetic only: "trades 4.2% above its iNAV", with the time of each number. Nothing here calls a price high
or low, or says what to do about it."""
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from . import db, instrument_kinds, money_mf_nav
from .auth import current_profile
from .intel.net import TTLCache
from .newsletter import job as news_job
from .plans import allows
from .responses import err, ok

LIVE_KEY = "etfnav:live"           # {"read", "as_of", "rows": {symbol: [name, isin, price, inav, underlying, nav, nav date]}}
DAY_KEY = "etfnav:day:"            # etfnav:day:<YYYY-MM-DD> = {symbol: [close, that day's NAV or None]}
KEEP_DAYS = 30                     # trading days of history kept
FILL_DAYS = 5                      # days back whose missing NAVs are still looked for
IST = timezone(timedelta(hours=5, minutes=30))
MAX_GAP = 50.0                     # a bigger gap means a mismatched NAV (another plan, a split), not a real one
LIVE_EVERY = 240                   # seconds between reads of the exchange's list while the market is open
RETRY = 1800                       # with nothing stored, wait this long between tries outside market hours
CLOSE_AT = "15:45"                 # India time: the day's closing prices are recorded after this
SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
NOTE = ("Price is the last traded price on the exchange. The NAV is the fund house's own figure for what one unit "
        "holds, published each evening for that day, so through the day the price moves while the NAV stays at the "
        "last close. A gap is the price's distance from the NAV, as a percent. Figures as of the times shown.")
# said only when a source gave a real indicative NAV (the exchange's list gives none)
INAV_NOTE = (" The indicative NAV (iNAV) is the estimate of what one unit holds, worked out through market hours from "
             "the holdings' prices; a gap to it is shown too.")


def note(has_inav: bool) -> str:
    return NOTE + (INAV_NOTE if has_inav else "")

_cache = TTLCache(max_items=50)
_lock = threading.Lock()
_feed = {"fn": None, "tried": 0.0}


def setup(feed_fn):
    """Where the exchange's ETF list is read from (main.py's exchange client, or a test's fake)."""
    _feed["fn"] = feed_fn


def forget():
    """Drop the copies in memory (between tests)."""
    _cache.clear()
    _feed["tried"] = 0.0


# ---------- the arithmetic and the words ----------
def num(v) -> float | None:
    """A positive number from the exchange's text ("1,234.50", "-" or "" for none)."""
    if isinstance(v, bool):
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return x if 0 < x < 1e8 else None


def gap(price, ref) -> float | None:
    """How far the price is from a reference value, as a percent of it (above is positive), to two places. None when
    either is missing, or when the gap is too big to be real (a NAV that belongs to another unit)."""
    p, r = num(price), num(ref)
    if p is None or r is None:
        return None
    g = (p / r - 1) * 100
    return round(g, 2) if abs(g) <= MAX_GAP else None


def pct(g: float) -> str:
    """4.2% or 0.35%: one place from 1% up, two below it, without the sign."""
    a = abs(g)
    return f"{a:.1f}%" if a >= 1 else f"{a:.2f}%"


def words(g: float | None, basis: str = "NAV") -> str:
    """"trades 4.2% above its NAV", "trades 0.35% below its iNAV", "trades at its NAV"."""
    if g is None:
        return ""
    if abs(g) < 0.005:
        return f"trades at its {basis}"
    return f"trades {pct(g)} {'above' if g > 0 else 'below'} its {basis}"


# ---------- the exchange's ETF list ----------
def _when(v) -> str | None:
    """The exchange's timestamp ("03-Oct-2026 15:30:00", India time) as ISO with its offset."""
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(str(v).strip(), fmt).replace(tzinfo=IST).isoformat(timespec="minutes")
        except (TypeError, ValueError):
            continue
    return None


def parse_exchange(data) -> dict:
    """The exchange's ETF list as {"as_of": ISO or None, "rows": {symbol: {name, isin, price, inav, underlying, nav,
    nav_date}}}. Rows without a symbol or a price are left out. The list's "nav" is the fund's last published NAV
    (it matches the evening NAV file to the paisa, and the answer dates it in "navDate"), not an indicative NAV: an
    iNAV is read only from a field that says so, and stays None otherwise."""
    items = data.get("data") if isinstance(data, dict) else data
    nav_day = ((_when(data.get("navDate")) or "")[:10] or None) if isinstance(data, dict) else None
    rows: dict[str, dict] = {}
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        meta = it.get("meta") if isinstance(it.get("meta"), dict) else {}
        sym = str(it.get("symbol") or meta.get("symbol") or "").strip().upper()
        price = num(it.get("ltP") if it.get("ltP") is not None else it.get("lastPrice"))
        if not SYMBOL.match(sym) or price is None:
            continue
        inav = num(it.get("iNavValue") if it.get("iNavValue") is not None else it.get("inav"))
        nav = num(it.get("nav"))
        name = " ".join(str(meta.get("companyName") or it.get("companyName") or it.get("assets") or sym).split())[:120]
        under = " ".join(str(it.get("underlyingAsset") or it.get("assets") or "").split())[:120] or None
        rows[sym] = {"name": name, "isin": money_mf_nav._isin(meta.get("isin") or it.get("isin") or ""),
                     "price": round(price, 4), "inav": round(inav, 4) if inav else None, "underlying": under,
                     "nav": round(nav, 4) if nav else None, "nav_date": nav_day}
    stamp = data.get("timestamp") if isinstance(data, dict) else None
    return {"as_of": _when(stamp) if stamp else None, "rows": rows}


def add_isins(parsed: dict, feed) -> None:
    """Fill in the ISINs the ETF list doesn't carry (the NAV is matched by ISIN): from the exchange's ETF securities
    file, else the ones kept from the last read. A list read without them still stands: its iNAV gaps don't need them."""
    try:
        isins = feed.etf_securities() if hasattr(feed, "etf_securities") else {}
    except Exception:
        isins = {}
    kept = load_live()["rows"]
    for sym, r in parsed["rows"].items():
        if not r["isin"]:
            r["isin"] = money_mf_nav._isin(isins.get(sym) or (kept.get(sym) or {}).get("isin") or "")


def _pack(parsed: dict, read: str) -> str:
    rows = {s: [r["name"], r["isin"], r["price"], r["inav"], r["underlying"], r.get("nav"), r.get("nav_date")]
            for s, r in parsed["rows"].items()}
    return json.dumps({"read": read, "as_of": parsed["as_of"], "rows": rows}, separators=(",", ":"))


def load_live() -> dict:
    """The last list read, as {"read", "as_of", "rows": {symbol: {...}}}; empty rows when none is stored."""
    hit = _cache.get("live")
    if hit is not None:
        return hit
    try:
        got = db.json_value(db.get_setting(LIVE_KEY), {})
    except Exception:
        got = {}
    rows = {}
    for s, r in (got.get("rows") or {}).items() if isinstance(got, dict) else []:
        try:
            name, isin, price, inav, under, nav, nav_day = (list(r) + [None, None])[:7]     # older rows have five
            rows[s] = {"name": name, "isin": isin, "price": float(price), "inav": float(inav) if inav else None, "underlying": under,
                       "nav": float(nav) if nav else None, "nav_date": nav_day}
        except (TypeError, ValueError):
            continue
    out = {"read": got.get("read") if isinstance(got, dict) else None, "as_of": got.get("as_of") if isinstance(got, dict) else None,
           "rows": rows}
    _cache.set("live", out, 60)
    return out


def refresh(feed=None, now: datetime | None = None) -> dict:
    """Read the exchange's ETF list now and keep it. Raises when it can't be read or comes back empty."""
    feed = feed if feed is not None else (_feed["fn"]() if _feed["fn"] else None)
    if feed is None:
        raise ValueError("no exchange client")
    parsed = parse_exchange(feed.etf_list())
    if not parsed["rows"]:
        raise ValueError("the exchange's ETF list came back empty")
    add_isins(parsed, feed)
    now = now or datetime.now(timezone.utc)
    db.set_setting(LIVE_KEY, _pack(parsed, now.isoformat(timespec="seconds")))
    _cache.clear()
    return parsed


# ---------- NAVs ----------
def navs() -> dict:
    """The daily NAV file (every scheme, ETFs included). Tests replace this."""
    return money_mf_nav.daily()


def nav_of(row: dict, data: dict) -> dict | None:
    """The ETF's scheme in the NAV file, by its ISIN only (a name can match another plan of the same fund); else the
    last NAV the exchange's list gave, with its date."""
    sch = money_mf_nav.find(data, isin=row.get("isin") or "") if row.get("isin") else None
    if sch is None and row.get("nav") and row.get("nav_date"):
        sch = {"nav": row["nav"], "date": row["nav_date"]}
    return sch


# ---------- the history ----------
def _days() -> dict[str, dict]:
    """Every stored day: {"2026-10-03": {symbol: [close, nav]}}."""
    hit = _cache.get("days")
    if hit is not None:
        return hit
    out = {}
    try:
        for k, raw in db.all_settings_with_prefix(DAY_KEY):
            day = k[len(DAY_KEY):]
            got = db.json_value(raw, {})
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) and isinstance(got, dict):
                out[day] = got
    except Exception:
        return {}
    _cache.set("days", out, 600)
    return out


def record_close(day: date | str, live: dict, data: dict) -> int:
    """Store the day's closing price of every ETF with that day's NAV when the NAV file already has it (else None, to
    be filled later). Keeps the last KEEP_DAYS days. Returns how many ETFs were stored."""
    day = str(day)[:10]
    rows = {}
    for s, r in live["rows"].items():
        sch = nav_of(r, data)
        rows[s] = [r["price"], sch["nav"] if sch and sch.get("date") == day else None]
    if not rows:
        return 0
    db.set_setting(DAY_KEY + day, json.dumps(rows, separators=(",", ":")))
    _cache.clear()
    prune()
    return len(rows)


def fill_navs(data: dict, today: date) -> int:
    """Fill in the NAVs the evening file has published since a day's close was stored. Returns how many."""
    live = load_live()["rows"]
    cut = (today - timedelta(days=FILL_DAYS)).isoformat()
    filled = 0
    for day, rows in sorted(_days().items()):
        if day < cut:
            continue
        changed = False
        for s, v in rows.items():
            if not isinstance(v, list) or len(v) < 2 or v[1] is not None or s not in live:
                continue
            sch = nav_of(live[s], data)
            if sch and sch.get("date") == day:
                v[1] = sch["nav"]
                changed = True
                filled += 1
        if changed:
            db.set_setting(DAY_KEY + day, json.dumps(rows, separators=(",", ":")))
    if filled:
        _cache.clear()
    return filled


def prune():
    """Only the newest KEEP_DAYS days stay."""
    days = sorted(_days())
    for day in days[:-KEEP_DAYS]:
        db.delete_setting(DAY_KEY + day)
    if len(days) > KEEP_DAYS:
        _cache.clear()


def history(symbol: str) -> list[dict]:
    """One ETF's stored days, oldest first: {"day", "close", "nav", "gap"} (gap and nav None until that day's NAV is
    out)."""
    out = []
    for day, rows in sorted(_days().items())[-KEEP_DAYS:]:
        v = rows.get(symbol)
        if not isinstance(v, list) or len(v) < 2:
            continue
        out.append({"day": day, "close": num(v[0]), "nav": num(v[1]), "gap": gap(v[0], v[1])})
    return out


def summary(hist: list[dict]) -> dict | None:
    """The stored days' gaps in brief: how many, the average, the lowest and the highest."""
    gs = [h["gap"] for h in hist if h["gap"] is not None]
    if not gs:
        return None
    return {"days": len(gs), "avg": round(sum(gs) / len(gs), 2), "low": min(gs), "high": max(gs),
            "from": next(h["day"] for h in hist if h["gap"] is not None), "to": [h["day"] for h in hist if h["gap"] is not None][-1]}


# ---------- what the pages show ----------
def row_view(sym: str, r: dict, data: dict, as_of: str | None) -> dict:
    """One ETF: its price, iNAV and last NAV, the gap to each, and the headline gap in words (to the iNAV when the
    exchange gave one, else to the last NAV)."""
    sch = nav_of(r, data)
    nav, nav_day = (sch["nav"], sch.get("date")) if sch else (None, None)
    inav_gap, nav_gap = gap(r["price"], r.get("inav")), gap(r["price"], nav)
    basis = "iNAV" if inav_gap is not None else "NAV" if nav_gap is not None else None
    g = inav_gap if basis == "iNAV" else nav_gap
    fund = instrument_kinds.fund_of(f"{sym} {r.get('name') or ''} {r.get('underlying') or ''}")
    # the exchange's list names the underlying ("Gold"); the NAV file names the fund ("Nippon India ETF Gold BeES")
    name = (sch or {}).get("name") or r.get("name") or sym
    return {"symbol": sym, "name": name, "underlying": r.get("underlying"), "fund": fund,
            "fund_label": instrument_kinds.FUND_LABELS.get(fund, "ETF"), "price": r["price"], "price_at": as_of,
            "inav": r.get("inav"), "inav_gap": inav_gap, "nav": nav, "nav_date": nav_day, "nav_gap": nav_gap,
            "gap": g, "basis": basis, "text": f"{sym} {words(g, 'indicative NAV' if basis == 'iNAV' else 'last NAV')}" if basis else None}


def table() -> dict:
    """Every ETF on the exchange's list, the widest gap first (either way), with each one's 30-day summary."""
    hit = _cache.get("table")
    if hit is not None:
        return hit
    live = load_live()
    data = navs()
    days = _days()
    rows = []
    for s, r in live["rows"].items():
        v = row_view(s, r, data, live["as_of"])
        v["days"] = summary(history(s)) if days else None
        rows.append(v)
    rows.sort(key=lambda v: (v["gap"] is None, -abs(v["gap"] or 0), v["symbol"]))
    nav_days = sorted({v["nav_date"] for v in rows if v["nav_date"]})
    out = {"rows": rows, "as_of": live["as_of"], "read": live["read"], "nav_as_of": nav_days[-1] if nav_days else None,
           "count": len(rows), "with_gap": sum(1 for v in rows if v["gap"] is not None),
           "note": note(any(v["inav"] is not None for v in rows))}
    _cache.set("table", out, 60)
    return out


def detail(symbol: str) -> dict | None:
    """One ETF's row and its 30-day history; None when it isn't on the exchange's list."""
    live = load_live()
    sym = str(symbol or "").strip().upper()
    r = live["rows"].get(sym)
    if not r:
        return None
    h = history(sym)
    return {"row": row_view(sym, r, navs(), live["as_of"]), "history": h, "days": summary(h), "note": note(r.get("inav") is not None)}


def known(symbol: str) -> bool:
    """On the exchange's ETF list (or no list stored yet, so nothing can be said)."""
    rows = load_live()["rows"]
    return not rows or str(symbol).upper() in rows


def gap_now(symbol: str, price) -> dict | None:
    """For the alerts: an ETF's gap at a live price, against the last iNAV read (else its last NAV). None when it isn't
    an ETF on the list, or neither value is known."""
    r = load_live()["rows"].get(str(symbol).upper())
    if not r or num(price) is None:
        return None
    from .stock_alerts import money
    inav_g = gap(price, r.get("inav"))
    if inav_g is not None:
        return {"gap": inav_g, "basis": "iNAV",
                "text": f"{symbol} {words(inav_g, 'indicative NAV')} (price {money(float(price), 'IN')}, iNAV {money(r['inav'], 'IN')})"}
    sch = nav_of(r, navs())
    g = gap(price, sch["nav"]) if sch else None
    if g is None:
        return None
    return {"gap": g, "basis": "NAV",
            "text": f"{symbol} {words(g, 'last NAV')} (price {money(float(price), 'IN')}, NAV {money(sch['nav'], 'IN')} on {sch.get('date')})"}


# ---------- the job ----------
class Job(news_job.Job):
    """Every five minutes: while India's market is open, read the exchange's ETF list (at most every few minutes);
    after the close, record the day's closing prices once (run marker newsjob:etfnav-close); and fill in NAVs the
    evening file has since published. With nothing stored yet (a new server), it reads the list at once."""

    status_key = "etf"

    def __init__(self, feed_fn):
        super().__init__()
        self.feed_fn = feed_fn
        self.status.update(read=None, recorded=None, filled=0)
        self._read = 0.0
        self._first = 0.0

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="etf-nav").start()

    def _refresh(self, now: datetime) -> bool:
        self._read = time.time()
        try:
            refresh(self.feed_fn(), now)
        except Exception as e:
            self.status["last_error"] = str(e)[:200]
            return False
        self.status.update(read=now.isoformat(timespec="minutes"), last_error=None)
        return True

    def tick(self, now: datetime) -> int:
        from .stock_alerts import market_open
        if market_open("IN", now) and time.time() - self._read >= LIVE_EVERY:
            self._refresh(now)
        day = self.due("etfnav-close", now, "Asia/Kolkata", CLOSE_AT, region="IN")
        if day and (self._refresh(now) or str(load_live().get("as_of") or "")[:10] == day.isoformat()):
            n = record_close(day, load_live(), navs())
            self.mark("etfnav-close", day)
            self.status.update(recorded=day.isoformat(), last_run=now.isoformat())
            return n
        if not load_live()["rows"] and time.time() - self._first > RETRY:
            self._first = time.time()
            self._refresh(now)
        local = now.astimezone(IST).date()
        try:
            self.status["filled"] = fill_navs(navs(), local)
        except Exception as e:
            self.status["last_error"] = str(e)[:200]
        return 0


# ---------- the routes ----------
router = APIRouter(prefix="/invest/etf-gaps", tags=["invest"])


def _first_read():
    """With no list stored (a new server, before the job's first read), read it once now; at most every half hour."""
    if load_live()["rows"] or time.time() - _feed["tried"] < RETRY:
        return
    _feed["tried"] = time.time()
    try:
        refresh()
    except Exception as e:
        print("ETF list unavailable:", str(e)[:120])


@router.get("")
def etf_gaps(profile=Depends(current_profile)):
    """Every Indian ETF's price against its iNAV and last NAV, the widest gap first, with each one's 30-day range."""
    _first_read()
    return ok({**table(), "alerts": allows(profile["_plan"], "etf_gaps")})


@router.get("/{symbol}")
def etf_gap(symbol: str, profile=Depends(current_profile)):
    """One ETF's gap now and its 30-day history (each day's close against that day's NAV)."""
    if not SYMBOL.match(str(symbol).upper()):
        err(404, "not_etf", "That isn't an ETF on the exchange's list.")
    _first_read()
    got = detail(symbol)
    if got is None:
        err(404, "not_etf", f"{symbol.upper()} isn't on the exchange's ETF list.")
    return ok({**got, "alerts": allows(profile["_plan"], "etf_gaps")})
