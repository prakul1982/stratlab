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
from datetime import date, datetime, timezone
from html.parser import HTMLParser

import httpx
from fastapi import APIRouter, Depends

from . import db
from . import money_mf as mf
from . import money_mf_nav as navs
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import ok

URL = "https://www.amfiindia.com/modules/LoadTERData"
LATEST_KEY = "mfter:latest"        # {"at", "parts", "s": {scheme name: [date, category, type, regular parts, direct parts]}}
HIST_KEY = "mfter:hist"            # {scheme name: {"t": [[date, regular total, direct total]], "c": [[date, category]]}}
MONTHS_KEY = "mfter:months"        # {"YYYY-MM": unix time read}, so older months are read once
MAX_AGE = 12 * 3600                # re-read the current month after this long
RETRY = 3600                       # after a failed read, wait this long
PAUSE = 2.0                        # seconds between requests in one run
BACKFILL = 24                      # months of history to build up, one older month a run
MAX_POINTS = 200                   # history points kept per scheme
TIMEOUT = 40.0
MAX_BYTES = 30 * 1024 * 1024
MIN_ROWS = 50                      # fewer in the current and previous month together means the read went wrong
BACKGROUND = True                  # refresh in a thread when a copy exists (tests turn it off)
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
_mem: dict = {"latest": None, "hist": None, "months": None, "tried": 0.0, "running": False, "index": None}


# ---------- reading the disclosure ----------
def fetch_month(month: int, year: int) -> str:
    """One month's TER table as published (HTML). Tests replace this."""
    headers = {"User-Agent": "Mozilla/5.0 (StratLab)", "Content-Type": "application/x-www-form-urlencoded"}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as c:
        r = c.post(URL, content=f"MonthTER={month}-{year}&MF_ID=-1&NAV_ID=1&SchemeCat_Desc=-1")
        r.raise_for_status()
        if len(r.content) > MAX_BYTES:
            raise ValueError("file too large")
        return r.text


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
        _mem.update(latest=None, hist=None, months=None, tried=0.0, running=False, index=None)


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


def refresh(today: date | None = None) -> bool:
    """Read the previous and the current month (TERs are published on the day they change, so a scheme unchanged
    this month is in an earlier one), then one older month not yet read, back to BACKFILL months. True when read."""
    today = today or datetime.now(timezone.utc).date()
    _load()
    got, n_rows = [], 0
    try:
        for n in (1, 0):
            m, y = _month_back(today, n)
            if got:
                time.sleep(PAUSE)
            p = parse(fetch_month(m, y))
            got.append((f"{y}-{m:02d}", p))
            n_rows += len(p["rows"])
        if n_rows < MIN_ROWS:
            raise ValueError("too few rows")
    except Exception as e:                      # keep what is stored
        print("TER disclosure unavailable:", type(e).__name__)
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
    return True


def _run():
    try:
        refresh()
    finally:
        with _lock:
            _mem["running"] = False


def ensure() -> dict:
    """The stored TERs, refreshed when older than MAX_AGE: in the background when a copy exists, else here."""
    _load()
    now = time.time()
    with _lock:
        latest = _mem["latest"]
        stale = now - float(latest.get("at") or 0) >= MAX_AGE
        if not stale or _mem["running"] or now - _mem["tried"] < RETRY:
            return latest
        _mem["tried"] = now
        have = bool(latest["s"])
        if have and BACKGROUND:
            _mem["running"] = True
            threading.Thread(target=_run, daemon=True).start()
            return latest
    refresh()
    return _mem["latest"]


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
        return {**base, "schemes": [], "unmatched": [], "total": None, "read_at": None}
    latest = ensure()
    w = mf.worked(data)
    h = mf.holdings(data, w, mf.today_ist())
    with _lock:
        hist = _mem["hist"] or {}
    rows, unmatched = [], []
    for r in h["schemes"]:
        if (r["units"] or 0) <= mf.EPS:
            continue
        rec = w["info"][r["key"]]["rec"] or {}
        ter_name = match(rec.get("name") or "", r["name"]) if latest["s"] else None
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
    return {**base, "schemes": rows, "unmatched": unmatched, "total": total,
            "read_at": datetime.fromtimestamp(read, timezone.utc).isoformat(timespec="minutes") if read else None}


router = APIRouter(prefix="/money/mutual-funds", tags=["money"])


@router.get("/costs")
def mf_costs(profile=Depends(current_profile)):
    """What each fund held costs a year: its TER and the rupees on the current value (everyone), with the parts, the
    other plan beside it, changes since purchase and category changes (Basic and up)."""
    return ok(costs(profile["id"], profile["_plan"]))
