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
from .packed import pack, unpack
from .auth import current_profile
from .intel.net import TTLCache
from .newsletter import job as news_job
from .plans import allows
from .responses import err, ok

NAV_DAY_KEY = "etfnav:navday:"     # etfnav:navday:<YYYY-MM-DD> = {isin: that trading day's NAV} (DF-006)
LIVE_KEY = "etfnav:live"           # {"read", "as_of", "rows": {symbol: [name, isin, price, inav, underlying, nav, nav date, volume]}}
DAY_KEY = "etfnav:day:"            # etfnav:day:<YYYY-MM-DD> = {symbol: [close, that day's NAV or None, 1 when the close is the exchange's official one]}
KEEP_DAYS = 30                     # trading days of history the list's 30-day column is worked out over
ROW_DAYS = 45                      # day rows kept as they are; past ROLL_AT rows, the oldest move into each ETF's long series (O1)
ROLL_AT = 70
SERIES_KEY = "etfnav:ser:"         # etfnav:ser:<SYMBOL> = packed {"o": first day ordinal, "d": [days after the one before], "c": [closes], "n": [NAVs], "bf": 1 once back-filled}
BACKFILL_KEY = "etfnav:bf"         # {"fail": {symbol: [tries, last day tried]}}
BACKFILL_DAYS = 1800               # the NAV history service's limit is under five years
BACKFILL_PER_TICK = 3              # ETFs one run of the job back-fills (two reads each, about a minute)
BACKFILL_RETRY_DAYS = 7            # an ETF that failed three times is left alone for this long
FILL_DAYS = 5                      # days back whose missing NAVs are still looked for
IST = timezone(timedelta(hours=5, minutes=30))
WIDE_GAP = 50.0                    # a gap beyond this is shown, said to be that wide (DF-001): an overseas fund at its limit
MISMATCH = 3.0                     # a price 3x its NAV or more (or a third of it): a NAV of another unit, left out and said so
DOUBT_MOVE = 2.0                   # %: a close this far from the latest price, while the latest price sits near the NAV, is doubted
LIVE_EVERY = 240                   # seconds between reads of the exchange's list while the market is open
RETRY = 1800                       # with nothing stored, wait this long between tries outside market hours
CLOSE_AT = "15:45"                 # India time: the day's closing prices are recorded after this
SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
NOTE = ("Price is the last traded price on the exchange. The NAV is the fund house's own figure for what one unit "
        "holds, published each evening for that day. A gap compares a price and a NAV of the same day: the day's official "
        "closing price on the exchange against that day's NAV. A gap is left out when that close and the latest price are "
        "too far apart to both be right. Through the day, before that day's NAV is out, the gap shown is the last close's "
        "against its NAV, so the day's market move is never read as a gap. A gap of more than a few percent usually means "
        "few units trade, or the fund has stopped making new units: an overseas fund at the overseas investment limit "
        "can trade 40% or more above its NAV for months, and one beyond 50% is shown and said to be that wide. A price "
        "three or more times its NAV (or under a third of it) is a NAV of another unit (another plan, a split), so that "
        "gap is left out and said so. An international fund's NAV is worked out from overseas closing prices, which come "
        "hours after the Indian close, so its gap also holds the overseas market's move in between. Figures as of the times shown.")
# DF-007: the exchange's list gives no indicative NAV, and no other source is read for one, so the note says it isn't shown
NO_INAV_NOTE = (" An indicative NAV, the fund house's own estimate through the day, isn't shown: the exchange's ETF list "
                "doesn't carry one.")
# said only when a source gave a real indicative NAV (the exchange's list gives none)
INAV_NOTE = (" The indicative NAV (iNAV) is the estimate of what one unit holds, worked out through market hours from "
             "the holdings' prices; a gap to it is shown too.")


def note(has_inav: bool) -> str:
    return NOTE + (INAV_NOTE if has_inav else NO_INAV_NOTE)

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
    for k in [k for k in _feed if isinstance(k, tuple)]:
        del _feed[k]                   # the history report's last tries (fill_day_navs)


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


def volume_of(v) -> float | None:
    """Units traded, 0 included ("0", "1,200"); None when not given."""
    if isinstance(v, bool) or v is None or v == "":
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return x if 0 <= x < 1e12 else None


def mismatched(price, ref) -> bool:
    """A price MISMATCH times its reference value or more (or under 1/MISMATCH of it): a NAV of another unit (another
    plan, a split), not a premium any fund trades at."""
    p, r = num(price), num(ref)
    return p is not None and r is not None and not (1 / MISMATCH < p / r < MISMATCH)


def gap(price, ref) -> float | None:
    """How far the price is from a reference value, as a percent of it (above is positive), to two places. None when
    either is missing, or when the two are mismatched (a NAV that belongs to another unit). A wide gap is a real one:
    MONQ50 closed at 220.17 against a NAV of 118.37 on 23 Oct 2026, 86% above, and leaving it out made the 45.9% of
    the next ETF read as the widest (DF-001)."""
    p, r = num(price), num(ref)
    if p is None or r is None or mismatched(p, r):
        return None
    return round((p / r - 1) * 100, 2)


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
        # the units traded today: an ETF with none has only an old last price, never a close of today (R6O-018)
        vol = volume_of(it.get("qty") if it.get("qty") is not None else it.get("totalTradedVolume"))
        rows[sym] = {"name": name, "isin": money_mf_nav._isin(meta.get("isin") or it.get("isin") or ""),
                     "price": round(price, 4), "inav": round(inav, 4) if inav else None, "underlying": under,
                     "nav": round(nav, 4) if nav else None, "nav_date": nav_day, **({"volume": vol} if vol is not None else {})}
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
    rows = {s: [r["name"], r["isin"], r["price"], r["inav"], r["underlying"], r.get("nav"), r.get("nav_date"), r.get("volume")]
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
            name, isin, price, inav, under, nav, nav_day, vol = (list(r) + [None, None, None])[:8]     # older rows have five or seven
            rows[s] = {"name": name, "isin": isin, "price": float(price), "inav": float(inav) if inav else None, "underlying": under,
                       "nav": float(nav) if nav else None, "nav_date": nav_day, "volume": volume_of(vol)}
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


def trading(day: str | None) -> bool:
    """An Indian trading day (weekends and the exchange's holidays aren't)."""
    try:
        from .data.calendar import is_trading_day
        return bool(day) and is_trading_day("IN", date.fromisoformat(str(day)[:10]))
    except (ImportError, ValueError):
        return True


def trading_day_before(day: str) -> str:
    """The last trading day on or before `day`."""
    from . import exchange_days
    d = date.fromisoformat(day[:10])
    return d.isoformat() if trading(d.isoformat()) else exchange_days.prev_trading(d).isoformat()


def day_navs(day: str) -> dict:
    """The NAVs of a trading day kept for the ETFs whose daily file is dated a day with no trading ({isin: nav})."""
    hit = _cache.get(("navday", day))
    if hit is not None:
        return hit
    try:
        got = db.json_value(db.get_setting(NAV_DAY_KEY + day), {})
    except Exception:
        got = {}
    got = got if isinstance(got, dict) else {}
    _cache.set(("navday", day), got, 600)
    return got


def nav_of(row: dict, data: dict, sym: str | None = None) -> dict | None:
    """The ETF's scheme in the NAV file, by its ISIN only (a name can match another plan of the same fund); else the
    last NAV the exchange's list gave, with its date.

    A liquid fund publishes a NAV for every calendar day, so on a weekend the file's is dated a Sunday, a day with no
    close to set it against (DF-006: 20 liquid ETFs read "Last NAV 25 Oct 2026" and "no close of 25 Oct"). Then the
    NAV of the last trading day is used: the one kept from the industry body's history report (fill_day_navs), else
    the exchange list's when it is of that day, else the one stored with that day's close. Only with none of them is
    the file's NAV shown, marked `closed_day`."""
    sch = money_mf_nav.find(data, isin=row.get("isin") or "") if row.get("isin") else None
    if sch is None and row.get("nav") and row.get("nav_date"):
        sch = {"nav": row["nav"], "date": row["nav_date"]}
    if sch and sch.get("date") and not trading(sch["date"]):
        day = trading_day_before(sch["date"])
        kept = (_days().get(day) or {}).get(sym) if sym else None
        nav = (day_navs(day).get(row.get("isin") or "") if row.get("isin") else None) \
            or (row.get("nav") if row.get("nav_date") == day else None) \
            or (num(kept[1]) if isinstance(kept, list) and len(kept) > 1 else None)
        sch = {**sch, "nav": nav, "date": day} if nav else {**sch, "closed_day": True}
    return sch


HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt={d}&todt={d}"


def history_text(day: str) -> str:
    """The industry body's NAV history report for one day, every scheme. Tests replace this."""
    return money_mf_nav.fetch_text(HISTORY_URL.format(d=date.fromisoformat(day).strftime("%d-%b-%Y")))


def fill_day_navs(data: dict) -> int:
    """For the ETFs whose daily-file NAV is dated a day with no trading, keep the NAV of the trading day before it from
    the history report, read once per day (and again after RETRY when it isn't out). Returns how many were kept."""
    want: dict[str, set] = {}
    for r in load_live()["rows"].values():
        sch = money_mf_nav.find(data, isin=r.get("isin") or "") if r.get("isin") else None
        if sch and sch.get("date") and not trading(sch["date"]):
            want.setdefault(trading_day_before(sch["date"]), set()).add(r["isin"])
    kept = 0
    for day, isins in want.items():
        have = day_navs(day)
        if isins <= set(have) or time.time() - _feed.get(("hist", day), 0.0) < RETRY:
            continue
        _feed[("hist", day)] = time.time()
        try:
            parsed = money_mf_nav.parse(history_text(day))
        except Exception as e:
            print("NAV history unavailable:", type(e).__name__)
            continue
        got = dict(have)
        for i in isins:
            s = money_mf_nav.find(parsed, isin=i)
            if s and s.get("date") == day:
                got[i] = s["nav"]
        if len(got) > len(have):
            db.set_setting(NAV_DAY_KEY + day, json.dumps(got, separators=(",", ":")))
            kept += len(got) - len(have)
            _cache.clear()
    return kept


# ---------- the one-off back-fill of the long series (O1) ----------
_hist = {"closes": None}


def setup_history(closes_fn):
    """Where an ETF's daily closes come from for the back-fill: `closes_fn(symbol)` -> [{"t": ISO day, "c": close}, ...] (main.py's
    price client, or a test's fake)."""
    _hist["closes"] = closes_fn


def nav_history(code: str, start: str, end: str) -> dict[str, float]:
    """A scheme's NAV on each day of a range, {day: NAV}, from the industry body's NAV history service (public)."""
    got = money_mf_nav.fetch_history(code, start, end, timeout=120.0)
    groups = ((got or {}).get("data") or {}).get("nav_groups") or [{}]
    out = {}
    for r in (groups[0] or {}).get("historical_records") or []:
        n = money_mf_nav._num(str(r.get("nav") if r.get("nav") is not None else ""))
        if n and str(r.get("date") or "")[:10]:
            out[str(r["date"])[:10]] = n
    return out


def backfill_state() -> dict:
    return db.json_value(db.get_setting(BACKFILL_KEY), {})


def backfill_one(sym: str, row: dict, data: dict, today: date) -> bool:
    """Read one ETF's five years once: its scheme's NAV on each day and the exchange-traded price's daily closes, joined by day into the
    long series. False when the NAV scheme or the closes can't be found."""
    sch = money_mf_nav.find(data, isin=row.get("isin") or "") if row.get("isin") else None
    fn = _hist["closes"]
    if not sch or not sch.get("code") or fn is None:
        return False
    start = (today - timedelta(days=BACKFILL_DAYS)).isoformat()
    navs_ = nav_history(sch["code"], start, today.isoformat())
    bars = fn(sym) or []
    closes = {str(b["t"])[:10]: num(b.get("c")) for b in bars if num(b.get("c")) is not None}
    rows = {d: (c, navs_.get(d)) for d, c in closes.items() if d >= start and str(d) < today.isoformat()}
    if not rows:
        return False
    save_series(sym, rows, backfilled=True)
    return True


def backfill_step(data: dict, today: date, limit: int = BACKFILL_PER_TICK) -> int:
    """Back-fill up to `limit` more ETFs, once each. Three failures put an ETF aside for BACKFILL_RETRY_DAYS. Returns how many were done.
    The whole walk is about 360 ETFs; once every one is in the state, a run costs one read of that state."""
    live = load_live()["rows"]
    st = backfill_state()
    done, fail = set(st.get("done") or []), dict(st.get("fail") or {})
    todo = []
    for s in sorted(live):
        if s in done:
            continue
        n, last = (fail.get(s) or [0, ""])
        if n >= 3 and last and (today - date.fromisoformat(last)).days < BACKFILL_RETRY_DAYS:
            continue
        todo.append(s)
    n_done = 0
    for s in todo[:limit]:
        try:
            ok_ = backfill_one(s, live[s], data, today)
        except Exception as e:
            print("ETF back-fill failed:", s, type(e).__name__, str(e)[:100])
            ok_ = False
        if ok_:
            done.add(s)
            fail.pop(s, None)
            n_done += 1
        else:
            n, _ = (fail.get(s) or [0, ""])
            fail[s] = [1 if n >= 3 else n + 1, today.isoformat()]          # after the wait, a first failure again
        db.set_setting(BACKFILL_KEY, json.dumps({"done": sorted(done), "fail": fail}, separators=(",", ":")))
    return n_done


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


# ---------- the long series (O1) ----------
def load_series(symbol: str) -> dict:
    """One ETF's long series as stored: {"o", "d", "c", "n", "bf"}; {} when it has none."""
    key = SERIES_KEY + symbol
    hit = _cache.get(("ser", symbol))
    if hit is not None:
        return hit
    try:
        got = unpack(db.get_setting(key))
    except Exception:
        got = {}
    _cache.set(("ser", symbol), got, 300)
    return got


def series_rows(symbol: str) -> list[tuple[str, float | None, float | None]]:
    """The long series as [(day, close, NAV)], oldest first."""
    s = load_series(symbol)
    if not s.get("d"):
        return []
    out, o = [], int(s["o"])
    for i, step in enumerate(s["d"]):
        o += int(step)
        out.append((date.fromordinal(o).isoformat(), s["c"][i], s["n"][i]))
    return out


def save_series(symbol: str, rows: dict[str, tuple[float | None, float | None]], backfilled: bool | None = None):
    """Merge days {day: (close, NAV)} into an ETF's long series (a value given replaces the one stored; None keeps it)."""
    have = {d: (c, n) for d, c, n in series_rows(symbol)}
    for day, (c, n) in rows.items():
        oc, on = have.get(day, (None, None))
        have[day] = (c if c is not None else oc, n if n is not None else on)
    days = sorted(have)
    if not days:
        return
    first = date.fromisoformat(days[0]).toordinal()
    prev, deltas = first, []
    for d in days:
        o = date.fromisoformat(d).toordinal()
        deltas.append(o - prev)
        prev = o
    old = load_series(symbol)
    doc = {"o": first, "d": deltas, "c": [have[d][0] for d in days], "n": [have[d][1] for d in days],
           **({"bf": 1} if (backfilled if backfilled is not None else old.get("bf")) else {})}
    db.set_setting(SERIES_KEY + symbol, pack(doc))
    _cache.set(("ser", symbol), doc, 300)


def whole_market(official: dict, symbols) -> bool:
    """A day's official closes for the whole market, ETFs included (the bhavcopy lists a few thousand securities, most
    ETFs among them), so an ETF missing from them didn't trade that day; a short list, or one without ETFs, proves
    nothing."""
    symbols = list(symbols)
    return len(official or {}) >= 500 and sum(1 for x in symbols if x in official) >= max(1, len(symbols) // 2)


def official_closes(day: str) -> dict:
    """The exchange's official closes of a day (the cash bhavcopy, via official_close), {} while they aren't out."""
    try:
        from . import official_close
        return official_close.closes(day) or {}
    except Exception:
        return {}


def record_close(day: date | str, live: dict, data: dict) -> int:
    """Store the day's closing price of every ETF with that day's NAV when the NAV file already has it (else None, to
    be filled later). The close is the exchange's official one when it is out, else the list's last trade until it is
    (fill_navs swaps it in: R7O-007, MOGSEC's last trade 62.50 against an official close of 64.87). Keeps the last
    KEEP_DAYS days. Returns how many ETFs were stored."""
    day = str(day)[:10]
    official = official_closes(day)
    covers = whole_market(official, live["rows"])
    rows = {}
    for s, r in live["rows"].items():
        sch = nav_of(r, data, s)
        nav = sch["nav"] if sch and sch.get("date") == day else None
        if official.get(s):
            rows[s] = [official[s], nav, 1]
            continue
        if covers:
            rows[s] = [None, nav, 0]           # not in the day's bhavcopy: it didn't trade that day (DF-005)
            continue
        # no units traded that day: its last price is an older day's, so there's no close of this day to keep (R6O-018)
        rows[s] = [None if r.get("volume") == 0 else r["price"], nav]
    if not rows:
        return 0
    db.set_setting(DAY_KEY + day, json.dumps(rows, separators=(",", ":")))
    _cache.clear()
    prune()
    return len(rows)


def fill_navs(data: dict, today: date) -> int:
    """Fill in the NAVs the evening file has published since a day's close was stored, and the exchange's official
    close in place of a last trade once the day's bhavcopy is out (R7O-007). Returns how many NAVs were filled."""
    live = load_live()["rows"]
    cut = (today - timedelta(days=FILL_DAYS)).isoformat()
    filled = 0
    for day, rows in sorted(_days().items()):
        if day < cut:
            continue
        changed = False
        if any(isinstance(v, list) and len(v) < 3 for v in rows.values()):
            official = official_closes(day)
            covers = whole_market(official, rows)
            for s, v in rows.items():
                if isinstance(v, list) and len(v) >= 2 and len(v) < 3 and official.get(s):
                    v[0] = official[s]
                    v.append(1)
                    changed = True
                elif isinstance(v, list) and len(v) == 2 and covers:
                    v[0] = None                # the bhavcopy is out and the ETF isn't in it: no trade that day (DF-005)
                    v.append(0)
                    changed = True
        for s, v in rows.items():
            if not isinstance(v, list) or len(v) < 2 or v[1] is not None or s not in live:
                continue
            sch = nav_of(live[s], data, s)
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
    """Past ROLL_AT day rows, the oldest move into each ETF's long series (one write per ETF, about once a month) and the
    rows go: the newest ROW_DAYS stay as they are. Nothing is thrown away (O1)."""
    days = sorted(_days())
    if len(days) <= ROLL_AT:
        return
    old = days[:-ROW_DAYS]
    add: dict[str, dict[str, tuple]] = {}
    every = _days()
    for day in old:
        for sym, v in (every.get(day) or {}).items():
            if isinstance(v, list) and len(v) >= 2 and (num(v[0]) is not None or num(v[1]) is not None):
                add.setdefault(sym, {})[day] = (num(v[0]), num(v[1]))
    for sym, pts in add.items():
        save_series(sym, pts)
    for day in old:
        db.delete_setting(DAY_KEY + day)
    _cache.clear()


def history(symbol: str, doubtful_day: str | None = None, keep: int | None = KEEP_DAYS) -> list[dict]:
    """One ETF's stored days, oldest first: {"day", "close", "nav", "gap", "official"} (gap and nav None until that
    day's NAV is out; `official` when the close is the exchange's own). `doubtful_day` is the day whose gap the row
    leaves out (its close and the latest price disagree): it is left out of the history too, marked `doubtful`, so the
    range never holds the gap the row says it left out (DF-004: GROWWN200's "left out" gap was in its range)."""
    out = []
    for day, rows in (sorted(_days().items())[-keep:] if keep else sorted(_days().items())):
        v = rows.get(symbol)
        if not isinstance(v, list) or len(v) < 2:
            continue
        g = None if day == doubtful_day else gap(v[0], v[1])
        out.append({"day": day, "close": num(v[0]), "nav": num(v[1]), "gap": g, **({"official": True} if len(v) > 2 and v[2] else {}),
                    **({"doubtful": True} if day == doubtful_day else {}),
                    **({"mismatch": True} if g is None and day != doubtful_day and mismatched(v[0], v[1]) else {})})
    return out


def long_history(symbol: str, doubtful_day: str | None = None) -> list[dict]:
    """One ETF's whole stored history, oldest first, in history()'s shape: the long series (back-filled and rolled over) up to the
    day rows, which win on a day both have (their closes are the exchange's official ones)."""
    recent = history(symbol, doubtful_day, keep=None)
    first = recent[0]["day"] if recent else None
    out = []
    for day, close, nav in series_rows(symbol):
        if first and day >= first:
            continue
        g = gap(close, nav)
        out.append({"day": day, "close": num(close), "nav": num(nav), "gap": g,
                    **({"mismatch": True} if g is None and mismatched(close, nav) else {})})
    return out + recent


def summary(hist: list[dict]) -> dict | None:
    """The stored days' gaps in brief: how many, the average, the lowest and the highest. Every day with a gap counts,
    the widest included (DF-002: MASPTOP50's 14 days ran 45.9% to 65.6% above, but the days beyond 50% were dropped
    and two days read 45.9% to 48.3%); `stored` is how many days were kept at all, so the page can say the days used."""
    gs = [h["gap"] for h in hist if h["gap"] is not None]
    if not gs:
        return None
    return {"days": len(gs), "stored": len(hist), "avg": round(sum(gs) / len(gs), 2), "low": min(gs), "high": max(gs),
            "from": next(h["day"] for h in hist if h["gap"] is not None), "to": [h["day"] for h in hist if h["gap"] is not None][-1]}


# ---------- what the pages show ----------
def day_of(iso: str | None) -> str | None:
    """The India day of an ISO time (the list's read), or None."""
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return (t if t.tzinfo is None else t.astimezone(IST)).date().isoformat()


def same_day(sym: str, price, price_day: str | None, nav_day: str | None, volume=None) -> tuple[float | None, str | None]:
    """The price to set against a NAV of `nav_day`, and its day: the list's price when it is from that same day (after
    the close, once the evening NAV is out), else that day's stored close. None while neither exists: a price from
    today against yesterday's NAV is the day's market move, not a gap (8 Oct 2026: NIFTYBEES at 254.15 against the
    7 Oct NAV of 257.80 read "1.4% below" with the market down 1.7%)."""
    if not nav_day:
        return None, None
    close = (_days().get(nav_day) or {}).get(sym)
    if isinstance(close, list) and len(close) > 2 and close[2] and num(close[0]) is not None:
        return num(close[0]), nav_day                 # the exchange's official close of that day comes first (R7O-007)
    if isinstance(close, list) and len(close) > 2 and not close[2] and close[0] is None:
        return None, None                             # the bhavcopy says it didn't trade that day (DF-005)
    if price_day == nav_day and volume != 0:
        return num(price), nav_day
    if isinstance(close, list) and close and num(close[0]) is not None:
        return num(close[0]), nav_day
    return None, None


def doubtful(close, latest, nav) -> bool:
    """A close that can't be right beside the latest price: more than DOUBT_MOVE% from it while the latest price sits
    much nearer the NAV (R7O-007: MOGSEC's 62.50 "close", 3.4% below a NAV of 64.68, with the latest price at 64.77).
    Such a gap is left out rather than shown."""
    c, p, n = num(close), num(latest), num(nav)
    if not c or not p or not n or c == p:
        return False
    g_close, g_latest = gap(c, n), gap(p, n)
    if g_close is None or g_latest is None:
        return False
    return abs(c / p - 1) * 100 > DOUBT_MOVE and abs(g_latest) < abs(g_close) / 2


def last_trade_day(sym: str, r: dict, as_of: str | None, official: dict | None = None, covers: bool | None = None) -> str | None:
    """The day of the list's last price: the read's own day, unless no units traded that day (the list says none, or
    the day's bhavcopy is out without it), when it is the newest stored day the ETF did trade, or None when no stored
    day says (DF-005: GSEC10ABSL read "Last trade 23 Oct" for its 19 Oct trade, absent from the 23 Oct bhavcopy)."""
    today = day_of(as_of)
    if not today:
        return None
    official = official_closes(today) if official is None else official
    covers = whole_market(official, load_live()["rows"]) if covers is None else covers
    if r.get("volume") != 0 and not (covers and not official.get(sym)):
        return today
    for day, rows in sorted(_days().items(), reverse=True):
        v = rows.get(sym)
        if day >= today or not isinstance(v, list) or not v or num(v[0]) is None:
            continue
        if len(v) < 3 or v[2]:
            return day
    return None


def row_view(sym: str, r: dict, data: dict, as_of: str | None, official: dict | None = None, covers: bool | None = None) -> dict:
    """One ETF: its price, iNAV and last NAV, the gap to each, and the headline gap in words (to the iNAV when the
    exchange gave one, else to the last NAV). The NAV gap is of one day: that day's close (or the list's price, when it
    is of the NAV's day) against that day's NAV; `nav_price` and `nav_price_day` say which price, and `nav_waiting`
    that there is a NAV but no price of its day to set against it."""
    sch = nav_of(r, data, sym)
    nav, nav_day = (sch["nav"], sch.get("date")) if sch else (None, None)
    price_day = last_trade_day(sym, r, as_of, official, covers)
    vs, vs_day = same_day(sym, r["price"], price_day, nav_day, r.get("volume"))
    doubt = doubtful(vs, r["price"], nav)
    inav_gap, nav_gap = gap(r["price"], r.get("inav")), (None if doubt else gap(vs, nav))
    basis = "iNAV" if inav_gap is not None else "NAV" if nav_gap is not None else None
    g = inav_gap if basis == "iNAV" else nav_gap
    fund = instrument_kinds.fund_of(f"{sym} {r.get('name') or ''} {r.get('underlying') or ''}")
    # the exchange's list names the underlying ("Gold"); the NAV file names the fund ("Nippon India ETF Gold BeES")
    name = (sch or {}).get("name") or r.get("name") or sym
    return {"symbol": sym, "name": name, "underlying": r.get("underlying"), "fund": fund,
            "fund_label": instrument_kinds.FUND_LABELS.get(fund, "ETF"), "price": r["price"], "price_at": as_of, "price_day": price_day,
            "inav": r.get("inav"), "inav_gap": inav_gap, "nav": nav, "nav_date": nav_day, "nav_gap": nav_gap,
            "nav_price": vs if nav_gap is not None else None, "nav_price_day": vs_day if nav_gap is not None else None,
            "nav_waiting": bool(nav_day and vs is None), "nav_doubtful": doubt,
            # beyond WIDE_GAP: shown, and said to be that wide; mismatched: left out, with the reason (DF-001)
            "nav_wide": nav_gap is not None and abs(nav_gap) > WIDE_GAP, "nav_mismatch": bool(not doubt and vs and nav and mismatched(vs, nav)),
            "nav_closed_day": bool((sch or {}).get("closed_day")),
            "gap": g, "basis": basis, "text": _text(sym, g, basis, vs_day, day_of(as_of)) if basis else None}


def _text(sym: str, g: float | None, basis: str | None, vs_day: str | None, price_day: str | None) -> str:
    if basis == "iNAV":
        return f"{sym} {words(g, 'indicative NAV')}"
    if vs_day and vs_day != price_day:              # an earlier day's close: said in the past, with its day
        d = date.fromisoformat(vs_day)
        return f"{sym} {words(g, 'NAV').replace('trades', 'closed', 1)} on {d.day} {d.strftime('%b')}"
    return f"{sym} {words(g, 'last NAV')}"


def table() -> dict:
    """Every ETF on the exchange's list, the widest gap first (either way), with each one's 30-day summary."""
    hit = _cache.get("table")
    if hit is not None:
        return hit
    live = load_live()
    data = navs()
    days = _days()
    official = official_closes(day_of(live["as_of"])) if day_of(live["as_of"]) else {}
    covers = whole_market(official, live["rows"])
    rows = []
    for s, r in live["rows"].items():
        v = row_view(s, r, data, live["as_of"], official, covers)
        v["days"] = summary(history(s, v["nav_date"] if v["nav_doubtful"] else None)) if days else None
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
    row = row_view(sym, r, navs(), live["as_of"])
    h = long_history(sym, row["nav_date"] if row["nav_doubtful"] else None)
    return {"row": row, "history": h, "days": summary(h), "note": note(r.get("inav") is not None)}


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
    sch = nav_of(r, navs(), str(symbol).upper())
    # only a NAV of the price's own day: through the day the last NAV is yesterday's, and a live price against it is the
    # market's move, not a gap (the list's read stands for the day of the price)
    if not sch or sch.get("date") != day_of(load_live().get("as_of")):
        return None
    g = gap(price, sch["nav"])
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
        self.status.update(read=None, recorded=None, filled=0, backfilled=0)
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
            data = navs()
            fill_day_navs(data)
            self.status["filled"] = fill_navs(data, local)
            from .stock_alerts import market_open
            if load_live()["rows"] and not market_open("IN", now):
                # the one-off long history, a few ETFs a run, outside market hours (O1); over once every ETF is in
                self.status["backfilled"] += backfill_step(data, local)
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
