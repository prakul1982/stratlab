"""F&O contract changes: one dated list of the exchange's changes to its futures and options contracts. Stocks
entering or leaving F&O (with the last series they trade), lot-size revisions (old and new lot, and the series they
apply from) and changes to expiry days and sessions.

Two sources, both the exchange's own:
- the F&O market lots file (the same file rules_watch.py reads for the admins): one row per underlying, with the lot
  of each month's series. A stock whose later months are blank leaves F&O after its last listed series; a lot that
  differs from one month to the next is a revision from that series on. Each day's copy is also compared with the
  last one kept, so a stock added or dropped, or a lot changed within a series, is caught too.
- the exchange's circulars about F&O exclusions, introductions, lot sizes, expiry days and sessions.

Expiry dates come from the listed contracts when the app has them, else from the exchange's rule (the last Tuesday
of the month from September 2025, the last Thursday before; a holiday moves it to the trading day before).

Facts only: what the exchange changes and when. Nothing here says what to do about it.

Kept in app_settings: the last copy of each source (fochanges:state), the dated list (fochanges:events, about two
years) and each user's alert choice and the changes already sent to them (fochanges:alert:<uid>). The job reads both
sources twice a trading day; a change that touches a stock on someone's watchlist or in one of their running paper
sessions is sent to them once, by phone or email, on Basic and up, when they turned the alert on."""
import calendar
import json
import re
import threading
import time
from datetime import date, datetime, timedelta

from . import db
from .intel.filings import ist_now
from .intel.net import SourceError, TTLCache
from .newsletter import job as news_job

KEY = "fochanges:state"              # {"lots": {...}, "circulars": {...}, "last_run"}
EVENTS_KEY = "fochanges:events"      # [event], newest last
ALERT_KEY = "fochanges:alert:"       # fochanges:alert:<uid> = {"on": bool, "sent": [event ids]}
LOT_URL = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"
CIRCULARS_PAGE = "https://www.nseindia.com/resources/exchange-communication-circulars"
CIRCULAR_DAYS = 30                   # circulars read on each run
KEEP_DAYS = 730                      # changes kept in the list
MAX_EVENTS = 3000
MAX_SENT = 600                       # change ids remembered per user, so none is sent twice
BADGE_DAYS = 30                      # a lot revision or a new entry shows as a badge this long after it applies
RETRIES = (2.0, 6.0)                 # the pauses before each retry when the exchange is busy
SOURCE = "the exchange's F&O contract file and circulars"
NOTE = ("From the exchange's F&O market lots file and its circulars. Expiry dates come from the listed contracts, or "
        "for months not yet listed, from the exchange's expiry rule (the last Tuesday of the month, earlier when that "
        "is a holiday). The exchange's circulars have the full details.")
KINDS = {"exit": "Leaving F&O", "entry": "Entering F&O", "lot": "Lot size", "expiry": "Expiry and sessions",
         "circular": "Other circulars"}
INDEX_NAMES = {"NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "SENSEX", "BANKEX"}
MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}

# circulars about F&O contracts; each is sorted into one kind by the first pattern its subject matches
FO_WORDS = re.compile(r"F\s*&\s*O|\bFO\b|derivative|futures|options|contract|lot size|market lot|expiry|trading hours|"
                      r"market timing|pre-open", re.I)
CIRCULAR_KINDS = (
    ("exit", re.compile(r"exclu(?:sion|ded|de)|removal|cease|discontinu|no (?:fresh|new) contracts", re.I)),
    ("entry", re.compile(r"introduc|inclusion|includ|new (?:stocks|securities|underlyings?)|eligib|launch", re.I)),
    ("lot", re.compile(r"lot size|market lot|\blots?\b", re.I)),
    ("expiry", re.compile(r"expiry|trading hours|market timing|pre-open|session", re.I)),
)
FO_DEPT = re.compile(r"^FAOP$|^futures\s*&\s*options trading$", re.I)
MOCK = re.compile(r"\bmock trading\b", re.I)          # the weekly test session: no change to any contract
DERIVATIVES = re.compile(r"F\s*&\s*O|\bFO\b|derivative|futures|options|contracts?", re.I)

_cache = TTLCache(max_items=20)
_lock = threading.Lock()


# ---------- months and expiry days ----------
def month_of(cell: str) -> str | None:
    """"2026-10" from a column heading as the file writes it: "OCT-26", "Oct-2026", "OCT 26"."""
    m = re.fullmatch(r"([A-Za-z]{3})[\s-]?(\d{2}|\d{4})", (cell or "").strip())
    if not m or m.group(1).upper() not in MONTHS:
        return None
    y = int(m.group(2))
    return f"{2000 + y if y < 100 else y:04d}-{MONTHS[m.group(1).upper()]:02d}"


def series_name(month: str) -> str:
    """"Oct 2026" for "2026-10"."""
    try:
        y, m = month.split("-")
        return f"{calendar.month_abbr[int(m)]} {int(y)}"
    except (ValueError, IndexError, AttributeError):
        return str(month)


def _next_month(month: str, step: int = 1) -> str:
    y, m = map(int, month.split("-"))
    m += step
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def serial_months(months: list[str]) -> list[str]:
    """The monthly series every underlying trades: the run of consecutive months the file starts with ("2026-10",
    "2026-11", "2026-12"). The file also lists the long-dated index options (quarterly and half-yearly months years
    out, which only some indices have), and a blank there says nothing about a stock leaving."""
    out = list(months[:1])
    for m in months[1:]:
        if m != _next_month(out[-1]):
            break
        out.append(m)
    return out


def rule_expiry(month: str) -> date:
    """A month's series expiry by the exchange's rule: the last Tuesday (from September 2025; the last Thursday
    before), moved to the trading day before when it is a holiday."""
    from .data.calendar import is_trading_day
    y, m = map(int, month.split("-"))
    last = date(y, m, calendar.monthrange(y, m)[1])
    weekday = 1 if month >= "2025-09" else 3
    d = last - timedelta(days=(last.weekday() - weekday) % 7)
    for _ in range(10):
        try:
            if is_trading_day("IN", d):
                break
        except Exception:
            break
        d -= timedelta(days=1)
    return d


def _after(d: date) -> date:
    """The trading day after `d`."""
    from .data.calendar import is_trading_day
    n = d + timedelta(days=1)
    for _ in range(10):
        try:
            if is_trading_day("IN", n):
                break
        except Exception:
            break
        n += timedelta(days=1)
    return n


def _day(iso) -> str:
    """"28 Jul 2026" from an ISO date."""
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso or "")
    return f"{d.day} {d:%b %Y}"


def iso_day(text: str) -> str | None:
    """An ISO date from the ways the exchange writes one: "October 01, 2026", "01-Oct-2026", "2026-10-01",
    "01/10/2026", "20261001" (the circulars' own date field)."""
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d-%b-%Y", "%d-%B-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y",
                "%Y%m%d"):
        try:
            return datetime.strptime(s[:30].split(" 00:")[0].strip(), fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    return m.group(0) if m else None


# ---------- reading the contract file ----------
def _cells(line: str) -> list[str]:
    import csv
    row = next(csv.reader([line], delimiter="\t" if "\t" in line else ","), [])
    return [c.strip() for c in row]


def read_lots(text: str) -> dict:
    """{"months": ["2026-10", ...], "rows": {symbol: {"name", "index", "lots": {month: lot}}}} from the exchange's
    F&O market lots file: a heading row (UNDERLYING, SYMBOL, then one column a month), the index rows, and the
    stocks after a line naming the individual securities. A blank cell is a month with no contract. Raises
    ValueError when the file has no month columns or no rows."""
    if not text or "\x00" in text[:2000]:
        raise ValueError("The contract file came as a binary file, which isn't read here.")
    months: list[str | None] = []
    sym_at, rows, stocks = 1, {}, False
    for line in text.splitlines():
        cells = _cells(line)
        if not any(cells):
            continue
        up = [c.upper() for c in cells]
        if not months:
            found = [month_of(c) for c in cells]
            if sum(1 for f in found if f) >= 1 and any(c == "SYMBOL" for c in up):
                months, sym_at = found, up.index("SYMBOL")
            continue
        if "INDIVIDUAL SECURIT" in " ".join(up) or (len(cells) > sym_at and up[sym_at] == "SYMBOL"):
            stocks = True
            continue
        if len(cells) <= sym_at:
            continue
        sym = up[sym_at]
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9&\-_.]{0,24}", sym):
            continue
        lots = {}
        for i, mo in enumerate(months):
            if mo and i < len(cells) and re.fullmatch(r"\d[\d,]*", cells[i]):
                v = int(cells[i].replace(",", ""))
                if 0 < v < 10_000_000:
                    lots[mo] = v
        if not lots:
            continue
        name = cells[0] if sym_at > 0 else sym
        rows[sym] = {"name": name[:80], "index": (not stocks) or sym in INDEX_NAMES, "lots": lots}
    if not months or not any(months):
        raise ValueError("No month columns found in the contract file.")
    if not rows:
        raise ValueError("No contracts found in the contract file.")
    return {"months": [m for m in months if m], "rows": rows}


def _event(kind: str, sym: str | None, **kw) -> dict:
    return {"kind": kind, "symbol": sym, **kw}


MAX_LEAVERS = 12                     # more stocks than this "leaving" at once is a column not yet filled, not an exclusion
MAX_LEAVER_SHARE = 0.05              # ... and so is more than this share of all the stocks


def far_month(months: list[str]) -> str | None:
    """The last month a stock's futures are normally listed for: the third of the monthly series (near, next, far). A
    stock listed up to it, December in the October to December file, is not leaving: that is the far month."""
    serial = serial_months(months)
    return serial[min(2, len(serial) - 1)] if serial else None


def leavers(lots: dict) -> dict[str, str]:
    """{symbol: its last listed series} for the stocks whose listing stops before the far month, as one copy of the
    contract file shows it. A stock is read as leaving only when few of them stop early: when many do, the file's
    newest month is simply not filled in yet (every stock would "leave"), and none is reported from it. The exchange's
    exclusion circular is what confirms a leaver; this is the file's side of it."""
    months = lots["months"]
    far = far_month(months)
    if not far:
        return {}
    serial = serial_months(months)
    out = {}
    stocks = 0
    for sym, r in lots["rows"].items():
        if r["index"]:
            continue
        stocks += 1
        near = [m for m in serial if m in r["lots"]]
        if near and near[-1] < far:
            out[sym] = near[-1]
    if len(out) > max(MAX_LEAVERS, int(stocks * MAX_LEAVER_SHARE)):
        return {}
    return out


def derive(lots: dict, expiry) -> list[dict]:
    """The changes one copy of the contract file shows by itself: stocks whose later months are blank (leaving
    after their last listed series), stocks listed only from a later month (entering), and lots that differ from
    one month to the next (a revision from that series on). `expiry(symbol, month)` gives a series' expiry date."""
    out = []
    months = lots["months"]
    serial = serial_months(months)            # entering and leaving are read on the monthly series only
    going = leavers(lots)
    for sym, r in sorted(lots["rows"].items()):
        have = [m for m in months if m in r["lots"]]
        near = [m for m in serial if m in r["lots"]]
        seg = "index" if r["index"] else "stock"
        if not have:
            continue
        if sym in going:
            out.append(_event("exit", sym, segment=seg, series=going[sym], expiry=expiry(sym, going[sym]).isoformat(),
                              lot=r["lots"][going[sym]], id=f"exit:{sym}:{going[sym]}"))
        if near and near[0] != serial[0]:
            before = expiry(sym, _next_month(near[0], -1))
            out.append(_event("entry", sym, segment=seg, series=near[0], effective=_after(before).isoformat(),
                              lot=r["lots"][near[0]], id=f"entry:{sym}:{near[0]}"))
        for a, b in zip(have, have[1:]):
            was, now = r["lots"][a], r["lots"][b]
            if was != now:
                out.append(_event("lot", sym, segment=seg, series=b, was=was, now=now,
                                  effective=_after(expiry(sym, a)).isoformat(), id=f"lot:{sym}:{b}:{was}>{now}"))
    return out


def diff(old: dict, new: dict, day: str, expiry) -> list[dict]:
    """The changes between two copies of the contract file: an underlying added (entering F&O), one dropped (its last
    series was the last one the old copy listed), and a series whose lot changed after it was listed."""
    out = []
    o, n = old.get("rows") or {}, new.get("rows") or {}
    for sym in sorted(set(n) - set(o)):
        r = n[sym]
        first = next((m for m in new["months"] if m in r["lots"]), None)
        if first:
            out.append(_event("entry", sym, segment="index" if r["index"] else "stock", series=first, effective=day,
                              lot=r["lots"][first], id=f"entry:{sym}:{first}"))
    for sym in sorted(set(o) - set(n)):
        r = o[sym]
        last = max(r["lots"]) if r.get("lots") else None
        if last:
            out.append(_event("exit", sym, segment="index" if r.get("index") else "stock", series=last,
                              expiry=expiry(sym, last).isoformat(), lot=r["lots"][last], id=f"exit:{sym}:{last}"))
    for sym in sorted(set(o) & set(n)):
        for mo, now in sorted(n[sym]["lots"].items()):
            was = (o[sym].get("lots") or {}).get(mo)
            if was and was != now:
                out.append(_event("lot", sym, segment="index" if n[sym]["index"] else "stock", series=mo, was=was, now=now,
                                  effective=day, within=True, id=f"lot:{sym}:{mo}:{was}>{now}"))
    return out


# ---------- reading the circulars ----------
def read_circulars(data, known: set[str] | None = None) -> list[dict]:
    """The exchange's circulars about F&O contracts as changes: each sorted into exit, entry, lot, expiry (expiry days
    and sessions) or another F&O circular, with the F&O symbols its subject names (of those in `known`)."""
    from .rules_watch import read_circulars as read_all
    known = known or set()
    out, seen = [], set()
    rows = read_all(data, re.compile(".", re.S))
    # the exchange says which department wrote each circular: the equity F&O desk's (FAOP) are the ones about these
    # contracts; commodity, currency, SME and listing circulars also say "derivatives", "futures" or "market lot"
    for c in rows:
        subject, by_dept = c["subject"], bool(c.get("dept"))
        if c["id"] in seen or MOCK.search(subject):
            continue
        if by_dept and not FO_DEPT.search(c["dept"]):
            continue
        if not by_dept and not FO_WORDS.search(subject):
            continue
        seen.add(c["id"])
        kind = next((k for k, rx in CIRCULAR_KINDS if rx.search(subject)), "circular")
        if kind in ("exit", "entry") and not DERIVATIVES.search(subject):
            kind = "circular"
        if kind == "circular" and not by_dept and not DERIVATIVES.search(subject):
            continue                          # "exclusion from an index", "trading hours" of another segment...
        words = set(re.findall(r"[A-Z][A-Z0-9&\-]{1,19}", subject.upper()))
        syms = sorted(words & known)
        day = iso_day(c["date"])
        out.append({"id": f"circ:{c['id']}", "kind": kind, "symbol": syms[0] if len(syms) == 1 else None, "symbols": syms[:20],
                    "date": day, "subject": subject, "no": c.get("no") or "", "source": "circular", "url": c.get("url") or ""})
    return out


# ---------- the dated list ----------
def _when(e: dict) -> str:
    """The date a change is listed under: the last expiry for a stock leaving, the day a new lot or entry applies,
    the circular's date."""
    return str(e.get("expiry") or e.get("effective") or e.get("date") or e.get("seen") or "")[:10]


def text_of(e: dict) -> str:
    """One change in plain words."""
    k, sym = e.get("kind"), e.get("symbol") or ""
    series = series_name(e.get("series") or "")
    if e.get("source") == "circular":
        return f"Exchange circular{' ' + e['no'] if e.get('no') else ''}: {e.get('subject')}"
    if k == "exit":
        return (f"{sym} leaves F&O. The {series} series, expiring {_day(e.get('expiry'))}, is the last one the contract "
                f"file lists.")
    if k == "entry":
        return f"{sym} enters F&O from the {series} series, with a lot of {e.get('lot'):,}."
    if k == "lot" and e.get("within"):
        return f"{sym}'s lot for the {series} series changed from {e.get('was'):,} to {e.get('now'):,}."
    if k == "lot":
        return (f"{sym}'s lot size goes from {e.get('was'):,} to {e.get('now'):,} from the {series} series (the near "
                f"month from {_day(e.get('effective'))}).")
    return str(e.get("subject") or "")


def badge_of(e: dict, today: date) -> dict | None:
    """The short badge a change puts on a stock while it matters: until a leaving stock's last expiry, and for
    BADGE_DAYS after a new lot or an entry applies."""
    k, when = e.get("kind"), _when(e)
    if not e.get("symbol") or e.get("source") == "circular":
        return None
    try:
        d = date.fromisoformat(when)
    except ValueError:
        return None
    short_day = f"{d.day} {d:%b}"
    if k == "exit" and d >= today:
        return {"kind": k, "short": f"Leaves F&O after {short_day}", "text": text_of(e), "date": when}
    if d < today - timedelta(days=BADGE_DAYS):
        return None
    if k == "entry":
        return {"kind": k, "short": "New in F&O" if d <= today else f"In F&O from {short_day}", "text": text_of(e), "date": when}
    if k == "lot":
        return {"kind": k, "short": f"Lot {e.get('was'):,}→{e.get('now'):,} from {short_day}", "text": text_of(e), "date": when}
    return None


def load_events() -> list[dict]:
    hit = _cache.get("events")
    if hit is not None:
        return hit
    try:
        got = db.json_value(db.get_setting(EVENTS_KEY), [])
    except Exception:
        got = []
    got = [e for e in got if isinstance(e, dict) and e.get("id")] if isinstance(got, list) else []
    _cache.set("events", got, 300)
    return got


def load_state() -> dict:
    hit = _cache.get("state")
    if hit is not None:
        return hit
    try:
        st = db.json_value(db.get_setting(KEY), {})
    except Exception:
        st = {}
    st = st if isinstance(st, dict) else {}
    _cache.set("state", st, 300)
    return st


def still_leaving(events: list[dict], st: dict) -> list[dict]:
    """The stored changes, without the "leaving" ones the newest copy of the contract file does not bear out: a stock
    listed to the far month (December in the October to December file) was never leaving, and an earlier run, reading a
    month not yet filled in, may have said so. A stock gone from the file altogether did leave, and stays."""
    lots = st.get("lots") if isinstance(st.get("lots"), dict) else {}
    rows, months = lots.get("rows") or {}, lots.get("months") or []
    if not rows or not months:
        return events
    going = leavers({"months": months, "rows": rows})
    out = []
    for e in events:
        if e.get("kind") == "exit" and e.get("source") != "circular" and e.get("symbol") in rows and going.get(e["symbol"]) != e.get("series"):
            continue
        out.append(e)
    return out


SOURCE_DAYS = (150, 10)               # a circular is the source of a change published up to this long before it applies (and a few days after)


def sources_for(e: dict, circs: list[dict]) -> list[dict]:
    """The circulars a change rests on: those of its kind that name its symbol, or name none (the exchange's "two
    securities" circulars list them in an attachment), published shortly before it applies."""
    try:
        when = date.fromisoformat(_when(e))
    except ValueError:
        return []
    out = []
    for c in circs:
        if c["kind"] != e.get("kind"):
            continue
        named = set(c.get("symbols") or [])
        if named and e.get("symbol") not in named:
            continue
        try:
            d = date.fromisoformat(str(c.get("date") or "")[:10])
        except ValueError:
            continue
        if when - timedelta(days=SOURCE_DAYS[0]) <= d <= when + timedelta(days=SOURCE_DAYS[1]):
            out.append(c)
    return sorted(out, key=lambda c: c["date"], reverse=True)[:3]


def source_of(c: dict) -> dict:
    return {"no": c.get("no") or "", "subject": c.get("subject") or "", "url": c.get("url") or "", "date": c.get("date")}


def view(today: date | None = None) -> dict:
    """The page's answer: every change kept (newest date first) as one line in words with the circulars it rests on
    under it, the badges for the stocks they touch, and each source's date. A circular about a change the contract file
    shows is a source of that line, not a second line; one about expiry days, sessions or anything else is its own."""
    today = today or ist_now().date()
    st = load_state()
    events = still_leaving(load_events(), st)
    circs = [e for e in events if e.get("source") == "circular"]
    lots = st.get("lots") if isinstance(st.get("lots"), dict) else {}
    file_source = {"no": "", "subject": "The exchange's F&O contract file", "url": "", "date": lots.get("as_of")}
    used, rows, badges = set(), [], {}
    for e in events:
        row = {k: e.get(k) for k in ("id", "kind", "symbol", "symbols", "segment", "series", "expiry", "effective", "was", "now",
                                     "lot", "seen", "source", "no", "subject", "within")}
        row.update(date=_when(e), text=text_of(e), series_label=series_name(e["series"]) if e.get("series") else None)
        row["upcoming"] = row["date"] >= today.isoformat()
        if e.get("source") == "circular":
            row["sources"] = [source_of(e)]
        else:
            got = sources_for(e, circs)
            used.update(c["id"] for c in got)
            row["sources"] = [source_of(c) for c in got] + [file_source]
        rows.append(row)
        b = badge_of(e, today)
        if b:
            badges.setdefault(e["symbol"], []).append(b)
    # a circular of a kind the contract file reports shows once, as a source, when some line already rests on it
    rows = [r for r in rows if not (r.get("source") == "circular" and r["kind"] in ("exit", "entry", "lot") and r["id"] in used)]
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    for sym, bs in badges.items():
        bs.sort(key=lambda b: ({"exit": 0, "lot": 1, "entry": 2}.get(b["kind"], 3), b["date"]))
    sources = []
    for part, label in (("lots", "Contract file"), ("circulars", "Circulars")):
        p = st.get(part) if isinstance(st.get(part), dict) else {}
        sources.append({"id": part, "label": label, "as_of": p.get("as_of"), "checked": p.get("checked"), "failed": bool(p.get("error"))})
    dated = [s["as_of"] for s in sources if s["as_of"]]
    return {"events": rows, "badges": badges, "sources": sources, "as_of": max(dated) if dated else None, "note": NOTE,
            "kinds": KINDS, "today": today.isoformat()}


# ---------- reading the exchange ----------
def _retrying(fn, sleep=time.sleep):
    """Call `fn`, again after a pause when the exchange is busy (RETRIES), and give up with its error after that."""
    for i in range(len(RETRIES) + 1):
        try:
            return fn()
        except SourceError as e:
            if not e.busy or i == len(RETRIES):
                raise
            sleep(RETRIES[i])


SOURCES_READ = 2          # what refresh() reads: the contract file and the circulars (one problem each at most)


def refresh(feed, today: date | None = None, now: datetime | None = None, expiry=None, sleep=time.sleep) -> dict:
    """Read the contract file and the circulars; keep each one that answered (with its date) and the old copy of one
    that didn't. Adds the changes not seen before to the dated list and returns them ("new"), with "problems". On
    the very first read the list is filled from the file itself, and "new" is empty: nothing is news yet."""
    today = today or ist_now().date()
    now = now or ist_now()
    expiry = expiry or (lambda sym, month: rule_expiry(month))
    stamp = now.isoformat(timespec="minutes")
    found, problems = [], []
    with _lock:
        st = db.json_value(db.get_setting(KEY), {})
        st = st if isinstance(st, dict) else {}
        first = not st.get("lots", {}).get("rows") and not db.json_value(db.get_setting(EVENTS_KEY), [])
        old = st.get("lots") if isinstance(st.get("lots"), dict) else {}
        try:
            lots = read_lots(_retrying(lambda: feed.nse._surv_text(LOT_URL), sleep))
            found += derive(lots, expiry)
            if old.get("rows"):
                found += diff(old, lots, today.isoformat(), expiry)
            st["lots"] = {"as_of": today.isoformat(), "checked": stamp, "months": lots["months"], "rows": lots["rows"], "error": None}
        except (SourceError, ValueError, TypeError, AttributeError) as e:
            problems.append(f"contract file: {str(e)[:160]}")
            st["lots"] = {**old, "error": str(e)[:200], "tried": stamp}
        known = set((st.get("lots") or {}).get("rows") or {}) | INDEX_NAMES
        circ = st.get("circulars") if isinstance(st.get("circulars"), dict) else {}
        try:
            frm = (today - timedelta(days=CIRCULAR_DAYS)).strftime("%d-%m-%Y")
            data = _retrying(lambda: feed.nse._get("/api/circulars", {"fromDate": frm, "toDate": today.strftime("%d-%m-%Y")},
                                                   referer=CIRCULARS_PAGE, circuit="fochanges"), sleep)
            got = read_circulars(data, known)
            found += got
            st["circulars"] = {"as_of": today.isoformat(), "checked": stamp, "count": len(got), "error": None}
        except (SourceError, ValueError, TypeError, AttributeError) as e:
            problems.append(f"circulars: {str(e)[:160]}")
            st["circulars"] = {**circ, "error": str(e)[:200], "tried": stamp}
        st["last_run"] = stamp
        db.set_setting(KEY, json.dumps(st, separators=(",", ":")))
        log = db.json_value(db.get_setting(EVENTS_KEY), [])
        log = [e for e in log if isinstance(e, dict) and e.get("id")] if isinstance(log, list) else []
        have = {e["id"] for e in log}
        links = {e["id"]: e.get("url") for e in found if e.get("source") == "circular" and e.get("url")}
        for e in log:                                   # a circular kept before its link was read gets the link
            if e.get("source") == "circular" and not e.get("url") and links.get(e["id"]):
                e["url"] = links[e["id"]]
        new = []
        for e in found:
            if e["id"] in have:
                continue
            have.add(e["id"])
            e["seen"] = today.isoformat()
            new.append(e)
        cut = (today - timedelta(days=KEEP_DAYS)).isoformat()
        log = [e for e in log if _when(e) >= cut] + new
        db.set_setting(EVENTS_KEY, json.dumps(log[-MAX_EVENTS:], separators=(",", ":")))
    _cache.clear()
    return {"new": [] if first else new, "added": len(new), "problems": problems}


# ---------- who a change touches ----------
def session_symbol(inst: dict | None) -> str | None:
    """The F&O underlying a paper session trades: an options session's underlying, a future's name, a stock's
    symbol."""
    inst = inst or {}
    if inst.get("market", "IN") != "IN":
        return None
    s = inst.get("underlying") or (inst.get("name") if inst.get("fno") else inst.get("symbol"))
    return str(s).upper()[:30] if s else None


def tracked(uid: str, running_only: bool = True) -> set[str]:
    """The Indian symbols on a user's watchlist and in their paper sessions (the running ones, unless asked)."""
    out = set()
    raw = db.json_value(db.get_setting(f"watchlist:{uid}"), {})
    for i in (raw.get("items") or []) if isinstance(raw, dict) else []:
        if isinstance(i, dict) and i.get("region") == "IN" and isinstance(i.get("symbol"), str):
            out.add(i["symbol"].upper()[:30])
    try:
        rows = db.user_sessions(uid, 50)
    except Exception:
        rows = []
    for r in rows:
        if running_only and r.get("status") != "running":
            continue
        s = session_symbol(r.get("instrument"))
        if s:
            out.add(s)
    return out


def alert_row(uid: str) -> dict:
    row = db.json_value(db.get_setting(ALERT_KEY + uid), {})
    row = row if isinstance(row, dict) else {}
    return {"on": bool(row.get("on")), "sent": [x for x in row.get("sent") or [] if isinstance(x, str)][-MAX_SENT:]}


def set_alert(uid: str, on: bool) -> dict:
    row = alert_row(uid)
    row["on"] = bool(on)
    db.set_setting(ALERT_KEY + uid, json.dumps(row))
    return row


def message(events: list[dict]) -> tuple[str, str]:
    """(subject, text) for the changes that touch one user's stocks."""
    syms = sorted({s for e in events for s in ([e["symbol"]] if e.get("symbol") else e.get("symbols") or [])})
    subject = f"StratLab: F&O contract change{'s' if len(events) > 1 else ''} for {', '.join(syms[:4])}" + (" and more" if len(syms) > 4 else "")
    lines = [f"- {text_of(e)}" for e in events[:12]] + ([f"- and {len(events) - 12} more on the F&O changes page"] if len(events) > 12 else [])
    body = ("Changes to the exchange's F&O contracts for stocks on your watchlist or in your paper sessions:\n"
            + "\n".join(lines) + "\n\nFrom the exchange's contract file and circulars. Facts, not advice.")
    return subject[:150], body


def fire(new: list[dict], allowed, send, profile=None) -> int:
    """Send each user who turned the alert on (and whose plan has it, `allowed(profile)`) the new changes touching
    their watchlist or running paper sessions, in one message, once. Returns how many messages went."""
    profile = profile or db.cached_profile
    if not new:
        return 0
    sent = 0
    for key, raw in db.all_settings_with_prefix(ALERT_KEY):
        uid = key[len(ALERT_KEY):]
        row = db.json_value(raw, {})
        if not isinstance(row, dict) or not row.get("on"):
            continue
        try:
            p = profile(uid)
            if not allowed(p):
                continue
            mine = tracked(uid)
        except Exception:
            continue
        done = set(alert_row(uid)["sent"])
        hits = [e for e in new if e["id"] not in done and ({e.get("symbol")} | set(e.get("symbols") or [])) & mine]
        if not hits:
            continue
        subject, body = message(hits)
        try:
            reached = send(p, subject, body)
        except Exception as e:
            print("fo changes alert failed:", str(e)[:120])
            continue
        row = alert_row(uid)
        row["sent"] = (row["sent"] + [e["id"] for e in hits])[-MAX_SENT:]
        db.set_setting(ALERT_KEY + uid, json.dumps({"on": row["on"], "sent": row["sent"]}))
        sent += 1 if reached else 0
    return sent


class Job(news_job.Job):
    """Twice a trading day, before the open and in the evening (the exchange posts revised files and circulars
    through the day): reads both sources, keeps the dated list and sends the alerts. Uses the newsletter job's run
    markers (newsjob:fochanges-am / -pm), so a restart never sends an alert twice. With nothing stored yet (a new
    server), it reads at once."""
    RUNS = (("fochanges-am", "Asia/Kolkata", "08:15"), ("fochanges-pm", "Asia/Kolkata", "19:50"))

    def __init__(self, feed_fn, fire_fn, expiry=None):
        """`expiry()` makes a run's expiry(symbol, month) (the day's listed contracts); the rule when not given."""
        super().__init__()
        self.feed_fn, self.fire_fn, self.expiry = feed_fn, fire_fn, expiry
        self.status.update(added=0, problems=[])
        self._first_try = 0.0

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="fo-changes").start()

    def tick(self, now: datetime) -> int:
        for name, tz, at in self.RUNS:
            day = self.due(name, now, tz, at, region="IN")
            if day:
                self.mark(name, day)
                return self.run(now, day)
        if not load_state().get("lots") and time.time() - self._first_try > 1800:
            self._first_try = time.time()
            self.run(now, ist_now().date())
        return 0

    def run(self, now: datetime, day: date) -> int:
        out = refresh(self.feed_fn(), day, expiry=self.expiry() if self.expiry else None)
        sent = self.fire_fn(out["new"]) if out["new"] else 0
        self.record(now, out["problems"], SOURCES_READ, sent=sent, added=out["added"])
        return sent
