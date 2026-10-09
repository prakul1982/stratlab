"""Fund costs (Money: mutual funds): what each fund the user holds charges a year (its total expense ratio, TER, and
the parts it is made of), what that comes to in rupees on the user's current value, the same scheme's other plan
(direct or regular) beside it, how the TER moved since the user's first units still held were bought, and category
changes (the 2026 recategorisation among them).

The TER figures come from the fund industry body's public TER disclosure: a table per month with a row each time a
scheme's TER changes (date, category, and the regular and direct plans' parts and total). It is read at most every
12 hours (the current and the previous month, then one older month a run until two years are stored, a pause between
requests), and kept market-wide in app_settings: the latest row per scheme, and each scheme's history of totals and
categories. Nothing here is per user; the user's own values come from their saved funds and are never stored here."""
import csv
import io
import json
import re
import threading
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from xml.etree import ElementTree
from html.parser import HTMLParser

import httpx
from fastapi import APIRouter, Depends

from . import db
from . import money_mf as mf
from . import money_mf_nav as navs
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows
from .admin import admin_profile
from .responses import err, ok

URL = "https://www.amfiindia.com/api/populate-te-rdata-revised"     # the month's TER table; excel=true: the whole of it
LATEST_KEY = "mfter:latest"        # {"at", "parts", "s": {scheme name: [date, category, type, regular parts, direct parts]}}
HIST_KEY = "mfter:hist"            # {scheme name: {"t": [[date, regular total, direct total]], "c": [[date, category]]}}
MONTHS_KEY = "mfter:months"        # {"YYYY-MM": unix time read}, so older months are read once
STATUS_KEY = "mfter:status"        # how the last read went, for the platform check
MAX_AGE = 12 * 3600                # re-read the current month after this long
RETRY = 3600                       # after a failed read, wait this long
PAUSE = 2.0                        # seconds between requests in one run
TRIES = 3                          # per month: a busy source can answer with something that isn't a workbook
BACKFILL = 24                      # months of history to build up, one older month a run
MAX_POINTS = 200                   # history points kept per scheme
TIMEOUT = 120.0                    # the month's workbook is a few MB, built on request
MAX_BYTES = 30 * 1024 * 1024
MAX_UNZIPPED = 300 * 1024 * 1024
MIN_ROWS = 50                      # fewer in the current and previous month together means the read went wrong
BACKGROUND = True                  # refresh in a thread when a copy exists (tests turn it off)
CHECK_SCHEMES = 500                # the platform check wants at least this many schemes in a read
CHECK_DAYS = 45                    # and the last good read no older than this
RECAT_FROM = "2026-02-26"          # SEBI's circular recategorising schemes

DISCLAIMER = ("Facts and arithmetic: each fund's published expense ratio applied to your current value. Not investment "
              "advice, and not a comparison of funds.")
ASSUMPTIONS = [
    "The expense ratio (TER) is a yearly rate the fund takes out of its assets a little each day, so the NAV, your "
    "value and your gains above are already after it. Nothing extra is charged to you.",
    "The rupee cost is today's value times today's TER, as if both stayed the same for a year.",
    "The other plan's figure is the same arithmetic on your current value at that plan's TER. The two plans have "
    "different NAVs, so it is the TER gap in rupees, not what a holding in the other plan would be worth.",
    "Each fund is matched to the TER disclosure by its scheme name; the matched name is shown under each fund.",
    "TER history starts from the earliest month read; changes before that aren't shown.",
]
PART_LABEL = {"base": "Base expense", "b30": "Extra for inflows from smaller cities, Reg. 52(6A)(b)",
              "c": "Additional expenses, Reg. 52(6A)(c)", "brokerage": "Brokerage and transaction costs",
              "levies": "Statutory levies", "gst": "GST", "total": "Total"}

_lock = threading.Lock()
_mem: dict = {"latest": None, "hist": None, "months": None, "tried": 0.0, "running": False, "index": None, "status": None}


# ---------- reading the disclosure ----------
def _excel_rows(data: bytes):
    """The rows of the disclosure's workbook (its first sheet), as lists of cell texts. The file has no shared
    strings: every cell carries its own text."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    name = "xl/worksheets/sheet1.xml"
    if zf.getinfo(name).file_size > MAX_UNZIPPED:
        raise ValueError("TER workbook too large")
    row: dict[int, str] = {}
    with zf.open(name) as f:
        head = f.read(4096)
        if b"<!DOCTYPE" in head.upper() or b"<!ENTITY" in head.upper():
            # a worksheet never needs a DTD; refusing one rules out entity-expansion tricks (as the other XML readers do)
            raise ValueError("TER workbook has a document type declaration")
        parser = ElementTree.XMLPullParser()
        chunk = head
        while chunk:
            parser.feed(chunk)
            for _, el in parser.read_events():
                tag = el.tag.rsplit("}", 1)[-1]
                if tag == "c":
                    ref = re.match(r"[A-Z]+", el.get("r") or "")
                    v = next((x.text for x in el.iter() if x.tag.rsplit("}", 1)[-1] in ("v", "t") and x.text), "")
                    if ref:
                        col = 0
                        for ch in ref.group():
                            col = col * 26 + ord(ch) - 64
                        row[col - 1] = v
                    el.clear()
                elif tag == "row":
                    yield [row.get(i, "") for i in range(max(row) + 1)] if row else []
                    row = {}
                    el.clear()
            chunk = f.read(65536)
        parser.close()


def _excel_day(v: str) -> str:
    """A TER date as the workbook writes it (days since 30 Dec 1899) as YYYY-MM-DD; text dates are kept."""
    try:
        return (date(1899, 12, 30) + timedelta(days=int(float(v)))).isoformat()
    except (TypeError, ValueError, OverflowError):
        return v


def _to_csv(rows) -> str:
    """The workbook's rows in the columns parse() reads: brokerage and the trades' transaction cost are one part, the
    date is written out. Columns are found by their headings."""
    out = io.StringIO()
    w = csv.writer(out)
    head = None
    for r in rows:
        if head is None:
            if not any("scheme name" in c.lower() for c in r):
                continue
            low = [c.lower() for c in r]
            find = lambda *words: [i for i, c in enumerate(low) if all(x in c for x in words)]     # noqa: E731
            head = {"name": find("scheme name"), "type": find("scheme type"), "cat": find("scheme category"),
                    "date": find("ter date")}
            for plan in ("regular", "direct"):
                head[plan] = {"base": find(plan, "base"), "brokerage": find(plan, "brokerage") + find(plan, "transaction cost"),
                              "levies": find(plan, "levies"), "total": find(plan, "total")}
            if not head["name"] or not head["date"]:
                raise ValueError("the TER workbook's columns weren't recognised")
            w.writerow(["Scheme Name", "Scheme Type", "Scheme Category", "TER Date"] +
                       [f"{p.title()} Plan - {LABEL[k]} (%)" for p in ("regular", "direct") for k in LABEL])
            continue
        cell = lambda i: r[i] if i < len(r) else ""     # noqa: E731
        one = lambda idx: cell(idx[0]) if idx else ""     # noqa: E731

        def part(idx):
            vals = [_pct(cell(i)) for i in idx]
            return "" if all(v is None for v in vals) else str(round(sum(v or 0 for v in vals), 4))
        w.writerow([one(head["name"]), one(head["type"]), one(head["cat"]), _excel_day(one(head["date"]))] +
                   [part(head[p][k]) for p in ("regular", "direct") for k in LABEL])
    if head is None:
        raise ValueError("no TER table in the workbook")
    return out.getvalue()


LABEL = {"base": "Base TER", "brokerage": "Brokerage and transaction costs", "levies": "Statutory levies",
         "total": "Total TER"}


def fetch_month(month: int, year: int) -> str:
    """One month's TER disclosure for every fund house (the page's Excel download), as CSV in the columns parse()
    reads. Asked again with a growing wait when the source answers with something that isn't a workbook. Tests
    replace this."""
    headers = {"User-Agent": "Mozilla/5.0 (StratLab)"}
    params = {"MF_ID": "All", "Month": f"{month:02d}-{year}", "strCat": -1, "strType": -1, "excel": "true"}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as c:
        for i in range(TRIES):
            if i:
                time.sleep(PAUSE * 2 ** (i - 1))
            r = c.get(URL, params=params)
            r.raise_for_status()
            if len(r.content) > MAX_BYTES:
                raise ValueError("file too large")
            try:
                return _to_csv(_excel_rows(r.content))
            except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
                continue
    raise ValueError(f"no readable TER workbook after {TRIES} tries")


class _Tables(HTMLParser):
    """Every table in an HTML page as rows of cell texts."""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row and self.tables:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _grid(text: str) -> list[list[str]]:
    """The rows of the disclosure, whatever it came as: an HTML table, CSV, or JSON records."""
    t = (text or "").strip()
    if not t:
        return []
    if t[0] in "[{":
        try:
            got = json.loads(t)
        except ValueError:
            return []
        if isinstance(got, dict):
            got = next((v for v in got.values() if isinstance(v, list)), [])
        recs = [r for r in got if isinstance(r, dict)] if isinstance(got, list) else []
        if not recs:
            return []
        keys = list(recs[0].keys())
        return [keys] + [[str(r.get(k, "") if r.get(k) is not None else "") for k in keys] for r in recs]
    if "<t" in t.lower():
        p = _Tables()
        try:
            p.feed(t)
        except Exception:
            return []
        for table in p.tables:
            if any(_is_header(r) for r in table[:5]):
                return table
        return []
    return [[c.strip() for c in r] for r in csv.reader(io.StringIO(t))]


def _is_header(row: list[str]) -> bool:
    return any("scheme name" in c.lower() for c in row)


def part_key(label: str) -> str:
    """A short key for one part of the TER, from the column's label."""
    s = label.lower()
    if "total" in s:
        return "total"
    if "52(6a)(b)" in s.replace(" ", ""):
        return "b30"
    if "52(6a)(c)" in s.replace(" ", ""):
        return "c"
    if "gst" in s or "goods and services" in s:
        return "gst"
    if "brokerage" in s or "transaction cost" in s:
        return "brokerage"
    if "levies" in s or "statutory" in s:
        return "levies"
    if "base" in s:
        return "base"
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"\(%\)", "", s)).strip("_")[:40] or "other"


_PLAN_COL = re.compile(r"^\s*(regular|direct)\s*(?:plan)?\s*[-–:]?\s*(.+)$", re.I)


def _pct(s: str) -> float | None:
    try:
        v = float(str(s).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return round(v, 4) if 0 <= v <= 10 else None


def parse(text: str) -> dict:
    """One month's disclosure as {"parts": [part keys, total last], "rows": [{name, type, category, date, reg: {part:
    pct}, dir: {part: pct}}]}. Rows without a scheme name, a date or any TER figure are left out."""
    grid = _grid(text)
    start = next((i for i, r in enumerate(grid) if _is_header(r)), None)
    if start is None:
        return {"parts": [], "rows": []}
    cols: dict = {}
    plan_cols: list[tuple[int, str, str]] = []
    parts: list[str] = []
    for i, c in enumerate(grid[start]):
        low = c.lower().strip()
        m = _PLAN_COL.match(c)
        if m and ("ter" in low or "expense" in low or "gst" in low or "%" in low or "brokerage" in low or "levies" in low):
            key = part_key(m.group(2))
            plan_cols.append((i, "reg" if m.group(1).lower() == "regular" else "dir", key))
            if key not in parts:
                parts.append(key)
        elif "scheme name" in low:
            cols["name"] = i
        elif "scheme type" in low:
            cols["type"] = i
        elif "category" in low:
            cols["category"] = i
        elif "date" in low:
            cols["date"] = i
    if "name" not in cols or not plan_cols:
        return {"parts": [], "rows": []}
    parts = [p for p in parts if p != "total"] + (["total"] if "total" in parts else [])
    rows = []
    for r in grid[start + 1:]:
        get = lambda k: r[cols[k]].strip() if k in cols and cols[k] < len(r) else ""     # noqa: E731
        name = " ".join(get("name").split())[:200]
        day = navs._day(get("date")) if get("date") else None
        if not name or not day or _is_header(r):
            continue
        reg, dir_ = {}, {}
        for i, plan, key in plan_cols:
            v = _pct(r[i]) if i < len(r) else None
            if v is not None:
                (reg if plan == "reg" else dir_)[key] = v
        for side in (reg, dir_):
            if side and "total" not in side:
                side["total"] = round(sum(side.values()), 4)
        if not reg and not dir_:
            continue
        rows.append({"name": name, "type": get("type")[:80], "category": get("category")[:120], "date": day,
                     "reg": reg, "dir": dir_})
    return {"parts": parts, "rows": rows}


# ---------- what is stored ----------
def forget():
    """Drop the copies in memory (between tests)."""
    with _lock:
        _mem.update(latest=None, hist=None, months=None, tried=0.0, running=False, index=None, status=None)


def _load():
    """The stored copies, read once into memory."""
    with _lock:
        if _mem["latest"] is not None:
            return
    latest = db.json_value(db.get_setting(LATEST_KEY), {})
    hist = db.json_value(db.get_setting(HIST_KEY), {})
    months = db.json_value(db.get_setting(MONTHS_KEY), {})
    with _lock:
        if _mem["latest"] is None:
            _mem["latest"] = latest if isinstance(latest, dict) and isinstance(latest.get("s"), dict) else {"at": 0, "parts": [], "s": {}}
            _mem["hist"] = hist if isinstance(hist, dict) else {}
            _mem["months"] = months if isinstance(months, dict) else {}
            _mem["index"] = None


def _squash(points: list) -> list:
    """Points in date order with each repeat of the value before it dropped (the first date it took a value stays)."""
    out = []
    for p in sorted(points, key=lambda p: p[0]):
        if out and out[-1][0] == p[0]:
            out[-1] = p
        elif not out or out[-1][1:] != p[1:]:
            out.append(p)
    return out[-MAX_POINTS:]


def ingest(parsed: dict):
    """Add one month's rows: the latest row per scheme moves forward only, and history keeps every change of total and
    category, whichever order the months arrive in."""
    _load()
    with _lock:
        latest, hist = _mem["latest"], _mem["hist"]
        parts = list(latest.get("parts") or [])
        for p in parsed["parts"]:
            if p not in parts:
                parts.insert(len(parts) - 1 if parts and parts[-1] == "total" and p != "total" else len(parts), p)
        if "total" in parts:
            parts = [p for p in parts if p != "total"] + ["total"]
        old_parts = latest.get("parts") or []
        if parts != old_parts:      # re-lay stored rows on the new list of parts
            for v in latest["s"].values():
                for side in (3, 4):
                    was = dict(zip(old_parts, v[side] or []))
                    v[side] = [was.get(p) for p in parts]
        latest["parts"] = parts
        for r in parsed["rows"]:
            cur = latest["s"].get(r["name"])
            if cur is None or r["date"] >= cur[0]:
                latest["s"][r["name"]] = [r["date"], r["category"], r["type"],
                                          [r["reg"].get(p) for p in parts] if r["reg"] else None,
                                          [r["dir"].get(p) for p in parts] if r["dir"] else None]
            h = hist.setdefault(r["name"], {"t": [], "c": []})
            h["t"] = _squash(h["t"] + [[r["date"], r["reg"].get("total"), r["dir"].get("total")]])
            if r["category"]:
                h["c"] = _squash(h["c"] + [[r["date"], r["category"]]])
        _mem["index"] = None


def _save():
    with _lock:
        latest, hist, months = (json.dumps(_mem[k], separators=(",", ":")) for k in ("latest", "hist", "months"))
    try:
        db.set_setting(LATEST_KEY, latest)
        db.set_setting(HIST_KEY, hist)
        db.set_setting(MONTHS_KEY, months)
    except Exception as e:
        print("TER disclosure not saved:", type(e).__name__)


def _month_back(d: date, n: int) -> tuple[int, int]:
    m = d.year * 12 + d.month - 1 - n
    return m % 12 + 1, m // 12


def _status_note(**kw):
    """Record how the last read went (kept for the platform check and the admin panel)."""
    with _lock:
        st = _mem["status"] = {**(_mem["status"] or {}), **kw}
        raw = json.dumps(st, separators=(",", ":"))
    try:
        db.set_setting(STATUS_KEY, raw)
    except Exception as e:
        print("TER status not saved:", type(e).__name__)


def status() -> dict:
    """How the last reads went: {"last_try", "last_ok" (unix times), "error" (the last failure, or None), "schemes"
    (schemes in the last good read's two months), "month" ("YYYY-MM" read last)}, whether a read is running, and
    what is stored."""
    _load()
    if _mem["status"] is None:
        got = db.json_value(db.get_setting(STATUS_KEY), {})
        with _lock:
            if _mem["status"] is None:
                _mem["status"] = got
    with _lock:
        latest = _mem["latest"] or {}
        return {**_mem["status"], "running": _mem["running"], "stored": len(latest.get("s") or {}),
                "months": len(_mem["months"] or {}),
                "newest": max((v[0] for v in (latest.get("s") or {}).values()), default=None)}


def refresh(today: date | None = None) -> bool:
    """Read the previous and the current month (TERs are published on the day they change, so a scheme unchanged
    this month is in an earlier one), then one older month not yet read, back to BACKFILL months. True when read."""
    today = today or datetime.now(timezone.utc).date()
    _load()
    status()
    got, names = [], set()
    tried = time.time()
    try:
        for n in (1, 0):
            m, y = _month_back(today, n)
            if got:
                time.sleep(PAUSE)
            p = parse(fetch_month(m, y))
            got.append((f"{y}-{m:02d}", p))
            names |= {r["name"] for r in p["rows"]}
        if len(names) < MIN_ROWS:
            raise ValueError(f"only {len(names)} schemes in {got[0][0]} and {got[-1][0]}")
    except Exception as e:                      # keep what is stored
        print("TER disclosure unavailable:", type(e).__name__)
        _status_note(last_try=tried, error=f"{type(e).__name__}: {str(e)[:200]}")
        return False
    now = time.time()
    for ym, p in got:
        ingest(p)
        with _lock:
            _mem["months"][ym] = now
    with _lock:
        _mem["latest"]["at"] = now
        done = set(_mem["months"])
    for n in range(2, BACKFILL + 1):
        m, y = _month_back(today, n)
        ym = f"{y}-{m:02d}"
        if ym in done:
            continue
        time.sleep(PAUSE)
        try:
            ingest(parse(fetch_month(m, y)))
            with _lock:
                _mem["months"][ym] = time.time()
        except Exception as e:
            print("older TER month unavailable:", type(e).__name__)
        break
    _save()
    _status_note(last_try=tried, last_ok=now, error=None, schemes=len(names), month=got[-1][0])
    return True


def _run():
    try:
        refresh()
    finally:
        with _lock:
            _mem["running"] = False


def start(force: bool = False) -> bool:
    """Start a read: in a thread (or here, when BACKGROUND is off). Without `force`, only when the copy is older than
    MAX_AGE and no read was tried in the last RETRY seconds. True when a read started."""
    _load()
    now = time.time()
    with _lock:
        stale = now - float(_mem["latest"].get("at") or 0) >= MAX_AGE
        if _mem["running"] or not force and (not stale or now - _mem["tried"] < RETRY):
            return False
        _mem["tried"] = now
        _mem["running"] = True
    if BACKGROUND:
        threading.Thread(target=_run, daemon=True).start()
    else:
        _run()
    return True


def ensure() -> dict:
    """The stored TERs, with a read started in the background when they are older than MAX_AGE."""
    start()
    return _mem["latest"]


def reading() -> bool:
    """True while the very first read is under way (nothing stored yet)."""
    with _lock:
        return bool(_mem["running"]) and not (_mem["latest"] or {}).get("s")


def age_words(days: float) -> str:
    """How long ago a read was, in whole days: "today", "1 day ago", "3 days ago" (R9R-004: "1 days ago")."""
    n = max(0, round(days))
    return "today" if n == 0 else f"{n} day{'' if n == 1 else 's'} ago"


def check(now: float | None = None, start_read: bool = True) -> dict:
    """Platform check "Fund costs (TER)": pass when the last good read had at least CHECK_SCHEMES schemes and is at
    most CHECK_DAYS old; a warning when it is older or smaller; a failure when nothing has ever been read. Starts a
    read in the background when the copy is due one, so the next check sees it (not when `start_read` is off: the Admin
    page asks again on every look, and shows the job's last result, the same one Data and jobs quotes)."""
    from .platform_check import _result
    try:
        if start_read:
            start()
    except Exception as e:
        print("TER read not started:", type(e).__name__)
    st, now = status(), now or time.time()
    err = f" Last error: {st['error']}" if st.get("error") else ""
    name, area = "Fund costs (TER)", "Money"
    if not st["stored"] or not st.get("last_ok"):
        return _result(name, area, "fail", "Nothing has been read from the TER disclosure yet." + (err or " A first read has started."))
    days = (now - float(st["last_ok"])) / 86400
    what = (f"{st.get('schemes') or 0} schemes read for {st.get('month')}, {age_words(days)}; "
            f"{st['stored']} stored over {st['months']} months.")
    if days > CHECK_DAYS:
        return _result(name, area, "warn", f"Stale: {what}{err}")
    if (st.get("schemes") or 0) < CHECK_SCHEMES:
        return _result(name, area, "warn", f"Fewer than {CHECK_SCHEMES} schemes: {what}{err}")
    return _result(name, area, "pass", what + (f" The last try failed.{err}" if err else ""))


# ---------- finding a fund ----------
_DROP = {"fund", "plan", "option", "options", "direct", "regular", "growth", "idcw", "dividend", "div", "payout", "reinvestment",
         "reinvest", "bonus", "the", "scheme", "mf", "mutual", "of", "and", "a", "an", "gr", "dir", "reg", "cumulative",
         "daily", "weekly", "fortnightly", "monthly", "quarterly", "half", "yearly", "annual", "transfer", "sweep", "income",
         "distribution", "cum", "capital", "withdrawal", "inc", "dist", "erstwhile", "formerly", "known", "as", "series", "po"}


def name_tokens(name: str) -> frozenset:
    """The words that tell schemes apart: no plan, option or 'formerly known as' part."""
    s = re.sub(r"\((?:[^)]*formerly|[^)]*erstwhile)[^)]*\)?", " ", (name or "").lower())
    s = re.sub(r"\bformerly known as\b.*$", " ", s)
    words = re.findall(r"[a-z0-9]+", s.replace("&", " and "))
    return frozenset(w for w in words if w not in _DROP)


def _index() -> list[tuple[frozenset, str]]:
    with _lock:
        if _mem["index"] is None:      # one name per set of words: a renamed scheme's newest row wins
            best: dict[frozenset, str] = {}
            s = (_mem["latest"] or {}).get("s", {})
            for n, rec in s.items():
                t = name_tokens(n)
                if t not in best or rec[0] > s[best[t]][0]:
                    best[t] = n
            _mem["index"] = [(t, n) for t, n in best.items()]
        return _mem["index"]


def match(*names: str) -> str | None:
    """The disclosure's scheme name for a fund, by its names (the NAV file's, the statement's): the most words in
    common, clearly ahead of the next best. None when nothing fits well enough."""
    idx = _index()
    for name in names:
        want = name_tokens(name)
        if len(want) < 2:
            continue
        best, second, hit = 0.0, 0.0, None
        for have, n in idx:
            if not have:
                continue
            score = len(want & have) / len(want | have)
            if score > best:
                best, second, hit = score, best, n
            elif score > second:
                second = score
        if hit and best >= 0.6 and best - second >= 0.05:
            return hit
    return None


def plan_of(name: str) -> str | None:
    words = set(re.findall(r"[a-z]+", (name or "").lower()))
    return "direct" if "direct" in words or "dir" in words else "regular" if "regular" in words or "reg" in words else None


# ---------- the arithmetic ----------
def rupees(value: float | None, ter: float | None) -> float | None:
    """A year's cost in rupees at a TER (in %), on a value."""
    return None if value is None or ter is None else round(value * ter / 100, 2)


def at_or_before(points: list, day: str, col: int) -> tuple[str, float] | None:
    """The value in force on a day (the last point on or before it, with a figure in that column)."""
    hit = None
    for p in points:
        if p[0] > day:
            break
        if col < len(p) and p[col] is not None:
            hit = (p[0], p[col])
    return hit


def scheme_cost(row: dict, first_buy: str | None, ter_name: str, latest: dict, hist: dict, full: bool) -> dict:
    """One fund: its plan's TER and parts, rupees a year, the other plan's, the history since purchase and category
    changes (the parts, rupees per fund, the other plan and the history on the full view only)."""
    parts = latest.get("parts") or []
    rec = latest["s"][ter_name]
    plan = plan_of(row["name"])
    sides = {"regular": rec[3], "direct": rec[4]}
    def side(p):       # noqa: E306
        vals = sides.get(p)
        if not vals:
            return None
        d = dict(zip(parts, vals))
        return {"total": d.get("total"), "parts": [{"key": k, "label": PART_LABEL.get(k, k.replace("_", " ").capitalize()), "pct": d[k]}
                                                   for k in parts if k != "total" and d.get(k) is not None]}
    mine = side(plan) if plan else None
    out = {"key": row["key"], "name": row["name"], "matched": ter_name, "plan": plan, "value": row["value"],
           "ter_date": rec[0], "ter": mine["total"] if mine else None, "full": full}
    if not full:
        return out
    other_plan = {"direct": "regular", "regular": "direct"}.get(plan)
    other = side(other_plan) if other_plan else None
    out.update(parts=mine["parts"] if mine else [], cost_year=rupees(row["value"], out["ter"]),
               regular=side("regular"), direct=side("direct"), other_plan=other_plan)
    reg, dir_ = (out["regular"] or {}).get("total"), (out["direct"] or {}).get("total")
    gap = round(reg - dir_, 4) if reg is not None and dir_ is not None else None
    out["gap_pp"] = gap
    out["gap_year"] = rupees(row["value"], abs(gap)) if gap is not None else None
    out["other_cost_year"] = rupees(row["value"], other["total"]) if other else None
    h = hist.get(ter_name) or {"t": [], "c": []}
    col = 1 if plan == "regular" else 2 if plan == "direct" else None
    since = None
    if col and first_buy:
        pts = [p for p in h["t"] if col < len(p) and p[col] is not None]
        if pts:
            then = at_or_before(pts, first_buy, col)
            start = then or (pts[0][0], pts[0][col])
            later = [{"date": p[0], "ter": p[col]} for p in pts if p[0] > start[0]]
            since = {"first_buy": first_buy, "from": start[0], "history_starts_late": then is None, "then": start[1],
                     "now": out["ter"], "change_pp": round(out["ter"] - start[1], 4) if out["ter"] is not None else None,
                     "changes": later[-24:], "count": len(later)}
    out["since"] = since
    cats = h["c"]
    out["category"] = rec[1] or (cats[-1][1] if cats else "")
    out["category_changes"] = [{"date": b[0], "from": a[1], "to": b[1], "recat_2026": b[0] >= RECAT_FROM}
                               for a, b in zip(cats, cats[1:])]
    return out


def costs(uid: str, plan: str) -> dict:
    """What each fund the user holds costs a year, from their saved funds and the stored TERs."""
    data = mf.load(uid)
    full = allows(plan, "mf_costs")
    base = {"full": full, "plan": PLANS[FEATURE_PLAN["mf_costs"]]["name"], "assumptions": ASSUMPTIONS,
            "disclaimer": DISCLAIMER, "as_of": mf.today_ist()}
    if not data["txns"]:
        return {**base, "state": "ok", "schemes": [], "unmatched": [], "total": None, "read_at": None}
    latest = ensure()
    if not latest["s"]:     # nothing read yet: say so, rather than "not found" for every fund
        return {**base, "state": "reading" if reading() else "unavailable", "schemes": [], "unmatched": [], "total": None,
                "read_at": None}
    w = mf.worked(data)
    h = mf.holdings(data, w, mf.today_ist())
    with _lock:
        hist = _mem["hist"] or {}
    rows, unmatched = [], []
    for r in h["schemes"]:
        if (r["units"] or 0) <= mf.EPS:
            continue
        rec = w["info"][r["key"]]["rec"] or {}
        ter_name = match(rec.get("name") or "", r["name"])
        if not ter_name:
            unmatched.append({"key": r["key"], "name": r["name"]})
            continue
        lots = w["c"]["lots"][r["key"]]
        first = min((l["d"] for l in lots if l["u"] > mf.EPS), default=None)
        rows.append(scheme_cost(r, first, ter_name, latest, hist, full))
    priced = [s for s in rows if s["ter"] is not None and s["value"]]
    value = sum(s["value"] for s in priced)
    year = sum(rupees(s["value"], s["ter"]) for s in priced)
    total = {"cost_year": round(year, 2), "value": round(value, 2), "weighted_ter": round(year / value * 100, 4) if value else None,
             "funds": len(priced), "held": len(rows) + len(unmatched)}
    read = latest.get("at")
    return {**base, "state": "ok", "schemes": rows, "unmatched": unmatched, "total": total,
            "read_at": datetime.fromtimestamp(read, timezone.utc).isoformat(timespec="minutes") if read else None}


router = APIRouter(prefix="/money/mutual-funds", tags=["money"])


@router.get("/costs")
def mf_costs(profile=Depends(current_profile)):
    """What each fund held costs a year: its TER and the rupees on the current value (everyone), with the parts, the
    other plan beside it, changes since purchase and category changes (Basic and up)."""
    return ok(costs(profile["id"], profile["_plan"]))


# ---------- admin ----------
admin_router = APIRouter(prefix="/admin/ter", tags=["admin"])


@admin_router.get("")
def admin_ter(_=Depends(admin_profile)):
    """How the TER disclosure reads have gone, and the platform check's verdict on them."""
    verdict = check()          # first: it may start a read
    return {"status": status(), "check": verdict}


@admin_router.post("/read")
def admin_ter_read(_=Depends(admin_profile)):
    """Read the TER disclosure now, in the background, whatever the age of the stored copy."""
    if not start(force=True):
        err(409, "busy", "A read is already running.")
    return {"started": True, "status": status()}
