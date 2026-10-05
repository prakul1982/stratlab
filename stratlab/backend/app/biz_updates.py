"""Monthly and quarterly business updates, read into numbers.

Many Indian companies file numbers between results: automakers their monthly sales and production, banks and lenders
their quarter's provisional deposits and advances, others store counts, traffic or volumes. They're PDFs in a
different layout each time. This module finds them among a company's exchange filings (intel/filings.py's feed),
has the AI copy the headline figures out of each one, and keeps only the figures whose quote is really in the
document (docs.quote_found) and whose number is in that quote, with the page it's on. The figures become a time
series per measure, with the change on the month (or quarter) and on the year, and a 24-month chart.

Each filing is read once and stored for everyone (bizupd:<SYMBOL>). A daily job reads new updates for the sector
lists and for stocks with a "new business update" alert, and fires those alerts.

Facts and arithmetic only: the company's filed figures with their source, never brokers' estimates, and no "beat" or
"miss" against anything."""
import io
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from . import db, docs
from .ai_providers import AIError, complete, extract_json
from .auth import current_profile
from .intel.net import SourceError, TTLCache
from .plans import FEATURE_PLAN, PLANS, access_plan, allows
from .responses import err, ok

KEY = "bizupd:"                 # bizupd:<SYMBOL> = {"reads": {filing id: {"at", "title", "url", "read_at", "period", "span", "figures", "problem"}}}
AI_DAY_KEY = "bizupd-ai:"       # bizupd-ai:<YYYY-MM-DD> = AI reads made that day (all users together)
IST = ZoneInfo("Asia/Kolkata")
LOOKBACK_DAYS = 400             # filings searched for updates: a year and a bit, so each month has its year-ago month
READ_AT_ONCE = 4                # filings one request reads
AI_PER_DAY = 400                # AI reads a day across everyone (each filing is read once and shared)
KEEP_READS = 40                 # filings kept per company (three years of monthly updates)
MAX_FIGURES = 12
CHART_MONTHS = 24
JOB_DAYS = 45                   # the daily job reads updates filed this recently
RUN_AT = "19:30"                # India time: after the day's monthly updates (the 1st of the month, mostly by noon)
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&\-_.]{0,19}$")
NOTE = ("Figures as the company filed them with the exchange, copied from its own document; each one links to the filing "
        "with the page and the line it's on. Changes are arithmetic on those filed figures. Facts, not advice.")

# the companies the sector view lists, alphabetically: the ones that file monthly or quarterly business updates
SECTORS: dict[str, dict] = {
    "autos": {"label": "Automakers' monthly sales", "span": "month", "symbols": [
        ("ASHOKLEY", "Ashok Leyland"), ("BAJAJ-AUTO", "Bajaj Auto"), ("EICHERMOT", "Eicher Motors"), ("ESCORTS", "Escorts Kubota"),
        ("HEROMOTOCO", "Hero MotoCorp"), ("M&M", "Mahindra & Mahindra"), ("MARUTI", "Maruti Suzuki India"),
        ("TMCV", "Tata Motors (commercial vehicles)"), ("TMPV", "Tata Motors Passenger Vehicles"), ("TVSMOTOR", "TVS Motor Company")]},
    "lenders": {"label": "Banks' and lenders' quarterly updates", "span": "quarter", "symbols": [
        ("AUBANK", "AU Small Finance Bank"), ("BAJFINANCE", "Bajaj Finance"), ("BANDHANBNK", "Bandhan Bank"),
        ("FEDERALBNK", "The Federal Bank"), ("HDFCBANK", "HDFC Bank"), ("IDFCFIRSTB", "IDFC First Bank"),
        ("INDUSINDBK", "IndusInd Bank"), ("RBLBANK", "RBL Bank"), ("YESBANK", "Yes Bank")]},
}

_cache = TTLCache(max_items=500)
_lock = threading.Lock()
_wire = {"feed": None, "docs": None, "ai": None}


def setup(feed_fn, docs_fn, ai_fn):
    """Where filings, documents and the AI come from: main.py's clients, or a test's fakes."""
    _wire.update(feed=feed_fn, docs=docs_fn, ai=ai_fn)


def forget():
    _cache.clear()


# ---------- which filings are business updates ----------
MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
UPDATE = re.compile(
    r"monthly business update|business update|sales (?:update|volumes?|performance|figures|numbers|data)|"
    r"(?:production|sales|despatch|dispatch)(?:es)? (?:and (?:sales|production) )?volumes?|"
    rf"\bsales (?:in|for) (?:the month of )?{MONTHS}\b|\bauto sales\b|"
    r"provisional (?:business|figures|numbers|data|update)|operational (?:update|performance)|traffic (?:figures|update|data)|"
    r"(?:quarterly|q[1-4]) business update|pre-?quarter(?:ly)? update|monthly sales|\bsales (?:in|for) (?:q[1-4]|the quarter)|"
    r"wholesales? and retail sales|\b(?:production|sales|exports?)\b[^.]{0,30}\bfigures\b", re.I)
# the file name says it when the subject is a generic "General Updates"
UPDATE_FILE = re.compile(r"salesupdate|(?:" + MONTHS + r")salesrelease|salesdata|salesvolume|sales(?:" + MONTHS + r")|productionvolume|prod(?:uction)?(?:" + MONTHS +
                         r")|businessupdate|financialupdate|financialdisclosure|initial(?:financial|final)disclosure", re.I)
NOT_UPDATE = re.compile(r"\bsale of\b|slump sale|offer for sale|sales tax|record date|trading window|newspaper|"
                        r"transcript|recording|schedule of (?:analyst|investor|meet)", re.I)
GENERIC = re.compile(r"^(?:general updates?|updates?|press release|other|-)$", re.I)


def is_update(item: dict) -> bool:
    """A filing that carries a monthly or quarterly business update, from its subject, summary or file name."""
    subject, text, url = str(item.get("subject") or ""), str(item.get("text") or ""), str(item.get("url") or "")
    hay = f"{subject} {text}"
    if NOT_UPDATE.search(hay) or not url:
        return False
    if UPDATE.search(hay):
        return True
    name = re.sub(r"[^a-z0-9]", "", url.rsplit("/", 1)[-1].lower())
    return bool(GENERIC.match(subject.strip()) and UPDATE_FILE.search(name))


def maybe_update(item: dict) -> bool:
    """A plain "Press Release" or "General Updates" filed in the first days of a month, the way some automakers file
    their monthly sales: it's opened to check before it counts as an update."""
    subject, at = str(item.get("subject") or "").strip(), str(item.get("at") or "")
    return (bool(GENERIC.match(subject)) and at[8:10] in ("01", "02", "03", "04") and bool(item.get("url"))
            and not NOT_UPDATE.search(f"{subject} {item.get('text') or ''}") and not is_update(item))


# what a sales update says on its first pages, to confirm a "maybe"
SALES_TEXT = re.compile(r"\b(?:sales|sold|despatch\w*|dispatch\w*|production)\b[^\n]{0,200}\bunits\b|"
                        r"\bunits\b[^\n]{0,200}\b(?:sales|sold)\b", re.I)


def _row(i: dict, maybe: bool = False) -> dict:
    return {"id": str(i.get("id")), "at": i["at"], "title": (i.get("text") or i.get("subject") or "")[:200], "url": i["url"],
            "maybe": maybe}


def updates(items: list[dict]) -> list[dict]:
    """The business-update filings among a company's filings, newest first, with a PDF on the exchange's archive."""
    return [_row(i) for i in items if i.get("at") and docs.allowed(i.get("url")) and is_update(i)]


def candidates(items: list[dict]) -> list[dict]:
    """The updates, and the filings that may be one (opened to check before they count), newest first."""
    out = [_row(i, maybe=not is_update(i)) for i in items
           if i.get("at") and docs.allowed(i.get("url")) and (is_update(i) or maybe_update(i))]
    return sorted(out, key=lambda r: r["at"], reverse=True)


# ---------- reading one filing ----------
EXTRACT = """You copy the headline figures out of an Indian listed company's monthly or quarterly business update filed with
the stock exchange: sales or production volumes, deposits, advances or loans, CASA, assets under management, store
counts, passenger traffic, cement or power volumes, and the like.
Return {"period": "YYYY-MM: the month the figures are for (for a quarter, its last month)", "span": "month" or "quarter",
 "figures": [{"metric": "short name, e.g. Total sales, Domestic two-wheelers, Exports, Period-end deposits, CASA ratio",
   "segment": "the part of the business, or null", "value": number exactly as filed (no commas),
   "unit": "units, Rs crore, Rs billion, %, tonnes, MW, stores, passengers...", "basis": "month", "quarter" or "period end",
   "prior": the same figure for the same period a year earlier, as filed, or null,
   "headline": true for the one company-wide total, else false,
   "quote": "the exact line or sentence holding the number, copied word for word", "page": page number}]}
Rules:
- Only figures the document states for that one period. Leave out year-to-date and cumulative totals, targets,
  guidance and anything that isn't the company's own reported figure.
- Use the names under KNOWN MEASURES when the same figure appears, so months line up.
- Every "quote" is copied word for word from the document; a figure whose quote or number isn't there is thrown away.
- At most 12 figures, the company-wide totals first. No opinion, no comparison with estimates.
- Reply with ONLY one JSON object in exactly that shape."""

_NUM = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|crores?|cr\b|million|mn\b|billion|bn\b|thousand|k\b)?", re.I)
_MULT = {"lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7, "million": 1e6, "mn": 1e6, "billion": 1e9,
         "bn": 1e9, "thousand": 1e3, "k": 1e3}


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-9, 0.0005 * abs(b))


def number_in(value: float, quote: str) -> bool:
    """The figure is written in its quote: as is ("236,013"), or with a scale word ("1.9 million" for 1,900,000)."""
    for m in _NUM.finditer(quote or ""):
        try:
            x = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if _close(x, value):
            return True
        mult = _MULT.get((m.group(2) or "").lower().strip())
        if mult and _close(x * mult, value):
            return True
    return False


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        x = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) < 1e15 else None


def _period(v, filed: str) -> str | None:
    """"2026-09" for a month no later than the filing's and no more than 30 months before it."""
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", str(v or "").strip())
    if not m or not 1 <= int(m.group(2)) <= 12:
        return None
    p = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    f = filed[:7]
    lo = shift(f, -30)
    return p if lo <= p <= f else None


def shift(period: str, months: int) -> str:
    y, m = int(period[:4]), int(period[5:7])
    n = y * 12 + (m - 1) + months
    return f"{n // 12:04d}-{n % 12 + 1:02d}"


def pdf_pages(data: bytes, max_pages: int = 12) -> list[str]:
    """Each page's text (the rupee sign put back), for finding the page a quote is on."""
    from pypdf import PdfReader
    out = []
    for page in PdfReader(io.BytesIO(data)).pages[:max_pages]:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        out.append(docs.fix_rupee(re.sub(r"[ \t]+", " ", t).strip()))
    return out


def pages_of(docs_api, url: str) -> list[str]:
    """The filing's pages as text. Scanned pages (no text) are read by the documents' OCR as one page."""
    if not docs.allowed(url):
        raise SourceError("the exchange", "That document isn't on the exchange's site.")
    hit = _cache.get(("pages", url))
    if hit is not None:
        return hit
    data = docs_api._download(url, (), docs.MAX_BYTES)
    if not bytes(data[:5]).startswith(b"%PDF"):
        raise SourceError("the exchange", "The link didn't return a PDF.")
    try:
        pages = pdf_pages(bytes(data))
    except Exception as e:
        raise SourceError("the exchange", f"The PDF couldn't be read ({e.__class__.__name__}).") from None
    if docs.scanned("\n".join(pages), len(pages)):
        text = docs_api.text(url)                 # the OCR path, cached by the documents client
        pages = [text] if text.strip() else pages
    _cache.set(("pages", url), pages, 3600)
    return pages


def clean_figures(d: dict, pages: list[str], filed: str) -> tuple[str | None, str, list[dict]]:
    """(period, span, figures) kept from the AI's reply: each figure's quote must be on one of the pages and its number
    in the quote; the year-ago figure is kept only when it's in the quote too. Year-to-date figures are dropped."""
    period = _period(d.get("period"), filed)
    span = "quarter" if str(d.get("span") or "").lower().startswith("q") else "month"
    out, seen, headline = [], set(), False
    for f in (d.get("figures") or [])[:MAX_FIGURES * 2] if isinstance(d.get("figures"), list) else []:
        if not isinstance(f, dict):
            continue
        name = " ".join(str(f.get("metric") or "").split())[:80]
        value, quote = _num(f.get("value")), " ".join(str(f.get("quote") or "").split())[:300]
        basis = str(f.get("basis") or span).lower().strip()
        basis = "period end" if basis.startswith("period") or "end" in basis else "quarter" if basis.startswith("q") else \
            "month" if basis.startswith("m") else None
        if not name or value is None or not quote or basis is None or re.search(r"year[- ]to[- ]date|\bytd\b|cumulative", name, re.I):
            continue
        page = next((n for n, t in enumerate(pages, 1) if docs.quote_found(quote, t)), None)
        if page is None or not number_in(value, quote):
            continue
        prior = _num(f.get("prior"))
        if prior is not None and not number_in(prior, quote):
            prior = None
        unit = " ".join(str(f.get("unit") or "").split())[:30] or "units"
        unit = re.sub(r"^(?:rs\.?|inr|₹)\s*", "₹ ", unit, flags=re.I)
        segment = " ".join(str(f.get("segment") or "").split())[:60] or None
        k = metric_key(name, segment, unit, basis)
        if k in seen:
            continue
        seen.add(k)
        head = bool(f.get("headline")) and not headline
        headline = headline or head
        out.append({"metric": name, "segment": segment, "value": value, "unit": unit, "basis": basis, "prior": prior,
                    "headline": head, "quote": quote, "page": page})
        if len(out) >= MAX_FIGURES:
            break
    return period, span, out


def known_measures(reads: dict) -> list[str]:
    names = []
    for r in sorted(reads.values(), key=lambda r: r.get("at") or "", reverse=True):
        for f in r.get("figures") or []:
            n = f"{f['metric']} ({f['unit']}, {f['basis']})"
            if n not in names:
                names.append(n)
    return names[:20]


def read_one(symbol: str, item: dict, docs_api, ai, known: list[str]) -> dict:
    """One filing read into figures: {"at", "title", "url", "read_at", "period", "span", "figures", "problem"}."""
    out = {"at": item["at"], "title": item["title"], "url": item["url"],
           "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "period": None, "span": None, "figures": [], "problem": None}
    try:
        pages = pages_of(docs_api, item["url"])
    except SourceError as e:
        out["problem"] = str(e)[:160]
        return out
    if item.get("maybe") and not SALES_TEXT.search("\n".join(pages[:3])):
        out.update(skip=True, problem="Not a business update.")
        return out
    body = "\n\n".join(f"[page {n}]\n{t[:6000]}" for n, t in enumerate(pages, 1) if t.strip())[:24000]
    if len(body.strip()) < 40:
        out["problem"] = "The filing holds no readable text."
        return out
    head = (f"COMPANY: {symbol} (NSE)\nFILED: {item['at'][:10]}\nFILING: {item['title'][:160]}\n"
            f"KNOWN MEASURES: {'; '.join(known) or '(none yet)'}\n\nDOCUMENT:\n")
    raw = complete(EXTRACT, head + body, gemini=ai[0] if ai else None, anthropic=ai[1] if ai else None, max_tokens=2000, kind="long")
    try:
        parsed = extract_json(raw)
    except AIError:
        out["problem"] = "The AI's reply couldn't be read."
        return out
    period, span, figures = clean_figures(parsed if isinstance(parsed, dict) else {}, pages, item["at"])
    out.update(period=period, span=span, figures=figures if period else [])
    if not period or not figures:
        out["problem"] = "No figure could be checked against the document."
    return out


# ---------- what's stored ----------
def stored(symbol: str) -> dict:
    hit = _cache.get(("reads", symbol))
    if hit is not None:
        return hit
    got = db.json_value(db.get_setting(KEY + symbol), {})
    reads = got.get("reads") if isinstance(got.get("reads"), dict) else {}
    _cache.set(("reads", symbol), reads, 600)
    return reads


def save(symbol: str, fid: str, read: dict):
    with _lock:
        got = db.json_value(db.get_setting(KEY + symbol), {})
        reads = got.get("reads") if isinstance(got.get("reads"), dict) else {}
        reads[fid] = read
        keep = sorted(reads, key=lambda k: reads[k].get("at") or "")[-KEEP_READS:]
        db.set_setting(KEY + symbol, json.dumps({"reads": {k: reads[k] for k in keep}}, separators=(",", ":"), ensure_ascii=False))
        _cache.clear()


def _ai_budget() -> bool:
    """One more AI read fits today's cap (shared by everyone); counts it when it does."""
    day = datetime.now(IST).date().isoformat()
    n = int(db.get_setting(AI_DAY_KEY + day) or 0)
    if n >= AI_PER_DAY:
        return False
    db.set_setting(AI_DAY_KEY + day, str(n + 1))
    return True


def read_new(symbol: str, items: list[dict], docs_api, ai, limit: int = READ_AT_ONCE, since: str | None = None) -> dict:
    """Read the newest unread updates (up to `limit`; filed on or after `since` when given). Returns {"read", "problems"}."""
    reads = stored(symbol)
    todo = [i for i in candidates(items) if i["id"] not in reads and (not since or i["at"] >= since)][:limit]
    done, problems = 0, []
    for item in todo:
        if not _ai_budget():
            problems.append("Today's reading limit is reached; the rest are read tomorrow.")
            break
        try:
            r = read_one(symbol, item, docs_api, ai, known_measures(reads))
        except AIError as e:
            problems.append(str(e)[:120])
            break
        save(symbol, item["id"], r)
        reads = stored(symbol)
        if r.get("skip"):
            continue                          # a press release that turned out not to be an update
        done += 1
        if r.get("problem"):
            problems.append(f"{item['at'][:10]}: {r['problem']}")
    return {"read": done, "problems": problems}


# ---------- the series ----------
def _squeeze(s: str | None) -> str:
    return re.sub(r"[^a-z0-9%]+", " ", str(s or "").lower()).strip()


def metric_key(name: str, segment: str | None, unit: str, basis: str) -> str:
    return "|".join((_squeeze(name), _squeeze(segment), _squeeze(unit), basis))


def change(now: float | None, before: float | None, unit: str) -> float | None:
    """Percent change, or the change in percentage points for a figure that is itself a percent."""
    if now is None or before is None:
        return None
    if "%" in unit:
        return round(now - before, 2)
    if before <= 0:
        return None
    return round((now / before - 1) * 100, 1)


def series(reads: dict) -> list[dict]:
    """Every measure across the stored reads: its points by period (a later filing's figure wins; a year-ago figure a
    filing states fills that month when nothing else does), the latest value, the change on the previous point and on
    the same period a year earlier. Measures in the newest filing come first, its headline figure at the top."""
    metrics: dict[str, dict] = {}
    order: list[str] = []
    for fid, r in sorted(reads.items(), key=lambda kv: kv[1].get("at") or ""):
        p = r.get("period")
        if not p:
            continue
        for f in r.get("figures") or []:
            k = metric_key(f["metric"], f.get("segment"), f["unit"], f["basis"])
            m = metrics.setdefault(k, {"key": k, "metric": f["metric"], "segment": f.get("segment"), "unit": f["unit"],
                                       "basis": f["basis"], "span": r.get("span") or "month", "headline": False, "points": {}})
            m["metric"], m["headline"] = f["metric"], m["headline"] or bool(f.get("headline"))
            src = {"at": r["at"], "url": r["url"], "page": f.get("page"), "quote": f.get("quote")}
            m["points"][p] = {"period": p, "value": f["value"], "filed_later": False, "source": src}
            if f.get("prior") is not None:
                py = shift(p, -12)
                if py not in m["points"] or m["points"][py]["filed_later"]:
                    m["points"][py] = {"period": py, "value": f["prior"], "filed_later": True, "source": src}
    newest = max(reads.values(), key=lambda r: r.get("at") or "", default=None)
    if newest:
        order = [metric_key(f["metric"], f.get("segment"), f["unit"], f["basis"]) for f in newest.get("figures") or []]
    out = []
    for k, m in metrics.items():
        pts = sorted(m["points"].values(), key=lambda x: x["period"])
        last = [x for x in pts if not x["filed_later"]] or pts
        latest = last[-1]
        before = [x for x in pts if x["period"] < latest["period"]]
        prev = before[-1] if before else None
        year = m["points"].get(shift(latest["period"], -12))
        step = "quarter" if m["span"] == "quarter" or (prev and shift(prev["period"], 3) == latest["period"]) else "month"
        lo = shift(latest["period"], -(CHART_MONTHS - 1))
        out.append({**{x: m[x] for x in ("key", "metric", "segment", "unit", "basis", "span", "headline")},
                    "latest": latest, "prev": prev, "year_ago": year, "step": step,
                    "change_prev": change(latest["value"], prev["value"], m["unit"]) if prev else None,
                    "change_year": change(latest["value"], year["value"], m["unit"]) if year else None,
                    "points": [x for x in pts if x["period"] >= lo]})
    rank = {k: i for i, k in enumerate(order)}
    out.sort(key=lambda m: (not m["headline"] or m["key"] not in rank, rank.get(m["key"], 999), m["latest"]["period"] < (newest or {}).get("period", ""),
                            m["metric"].lower()))
    return out[:MAX_FIGURES * 2]


def headline(metrics: list[dict]) -> dict | None:
    """The company-wide total: the one the filing marked, else the first measure."""
    return next((m for m in metrics if m["headline"]), metrics[0] if metrics else None)


def words(m: dict | None) -> str | None:
    """"Total sales 2,36,013 units in Sep 2026: up 24.4% on Sep 2025", for the alert and the My Stocks line."""
    if not m:
        return None
    v = m["latest"]
    when = _month(v["period"], m["span"])
    bits = [f"{m['metric']} {fmt_value(v['value'], m['unit'])} in {when}"]
    if m["change_year"] is not None:
        sign = "up" if m["change_year"] > 0 else "down" if m["change_year"] < 0 else "level"
        amt = f"{abs(m['change_year']):.1f}{' points' if '%' in m['unit'] else '%'}"
        bits.append(f"{sign} {amt} on {_month(shift(v['period'], -12), m['span'])}" if sign != "level" else f"level with {_month(shift(v['period'], -12), m['span'])}")
    return ": ".join(bits)


def _month(p: str, span: str = "month") -> str:
    try:
        d = date(int(p[:4]), int(p[5:7]), 1)
    except ValueError:
        return p
    if span == "quarter":
        fy = d.year + (1 if d.month >= 4 else 0)
        q = {6: 1, 9: 2, 12: 3, 3: 4}.get(d.month)
        return f"Q{q} FY{fy % 100:02d}" if q else d.strftime("%b %Y")
    return d.strftime("%b %Y")


def _group_in(whole: str) -> str:
    if len(whole) <= 3:
        return whole
    head, tail = whole[:-3], whole[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + parts) + "," + tail


def fmt_value(v: float, unit: str) -> str:
    """2,36,013 units, ₹31,872 billion, 34.2%: Indian digit grouping, the unit as filed."""
    neg = v < 0
    v = abs(v)
    s = f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    whole, _, frac = s.partition(".")
    s = _group_in(whole) + ("." + frac if frac else "")
    s = ("-" if neg else "") + s
    u = unit.strip()
    if u == "%":
        return s + "%"
    if u.startswith("₹"):
        return f"₹{s} {u[1:].strip()}".strip()
    return f"{s} {u}"


# ---------- what the pages show ----------
def view(symbol: str, items: list[dict] | None, allowed: bool, problems: list[str] | None = None) -> dict:
    """The company page's panel: the business-update filings (for everyone) and, on Basic and up, their figures as
    series with the changes and the chart's points."""
    reads = stored(symbol)
    found = updates(items or [])
    known = {f["id"] for f in found}
    for fid, r in reads.items():                       # read earlier (or a press release found to be one)
        if fid not in known and not r.get("skip"):
            found.append({"id": fid, "at": r["at"], "title": r["title"], "url": r["url"], "maybe": False})
    found.sort(key=lambda f: f["at"], reverse=True)
    filings = [{**f, "read": f["id"] in reads, "period": reads.get(f["id"], {}).get("period"),
                "problem": reads.get(f["id"], {}).get("problem")} for f in found[:30]]
    to_check = sum(1 for c in candidates(items or []) if c["maybe"] and c["id"] not in reads)
    metrics = series(reads) if allowed else []
    return {"symbol": symbol, "filings": filings, "unread": sum(1 for f in filings if not f["read"]) + to_check, "allowed": allowed,
            "metrics": metrics, "headline": words(headline(metrics)) if metrics else None, "problems": problems or [], "note": NOTE}


def sector_view(sector: str) -> dict:
    """Every company in a sector list, alphabetical: its latest headline figure, the change on the previous period and
    on the year, and when it was filed. No ranking."""
    s = SECTORS[sector]
    rows = []
    for sym, name in s["symbols"]:
        ms = series(stored(sym))
        h = headline(ms)
        rows.append({"symbol": sym, "name": name, "metric": h["metric"] if h else None, "unit": h["unit"] if h else None,
                     "span": h["span"] if h else s["span"], "period": h["latest"]["period"] if h else None,
                     "value": h["latest"]["value"] if h else None, "change_prev": h["change_prev"] if h else None,
                     "change_year": h["change_year"] if h else None, "step": h["step"] if h else None,
                     "filed": h["latest"]["source"]["at"] if h else None, "url": h["latest"]["source"]["url"] if h else None,
                     "points": [{"period": p["period"], "value": p["value"]} for p in h["points"]] if h else []})
    rows.sort(key=lambda r: r["name"].upper())
    return {"sector": sector, "label": s["label"], "rows": rows, "sectors": [{"id": k, "label": v["label"]} for k, v in SECTORS.items()],
            "note": NOTE + " Companies are listed alphabetically; each total is the company's own, so their definitions differ."}


def latest_line(symbol: str, since: str | None = None) -> str | None:
    """The newest update's headline in words, when it was filed on or after `since` (for My Stocks and alerts)."""
    reads = stored(symbol)
    if not reads:
        return None
    newest = max(reads.values(), key=lambda r: r.get("at") or "")
    if since and (newest.get("at") or "") < since:
        return None
    return words(headline(series(reads)))


# ---------- the job and the alert ----------
def alert_symbols() -> list[str]:
    """Indian stocks with an active "new business update" alert, from everyone's alerts."""
    from .stock_alerts import KEY as ALERTS
    out = set()
    for _, raw in db.all_settings_with_prefix(ALERTS):
        for a in db.json_value(raw, {}).get("items") or []:
            if isinstance(a, dict) and a.get("kind") == "bizupdate" and a.get("status") == "active" and a.get("region") == "IN":
                out.add(str(a.get("symbol") or "").upper())
    return sorted(s for s in out if SYMBOL.match(s))[:300]


def alert_rows(symbol: str, items: list[dict], since: str) -> list[dict]:
    """Business updates filed since `since`, as events for the stock alerts (kind "bizupdate")."""
    line = latest_line(symbol)
    return [{"kind": "bizupdate", "symbol": symbol, "id": f"bu:{u['id']}", "filed": u["at"][:10], "title": u["title"],
             "text": line} for u in updates(items) if u["at"] >= since]


class Job:
    """Once a day in the evening: for every company on the sector lists and every stock with a business-update alert,
    read the updates filed in the last few weeks that aren't read yet, then fire the alerts on the new ones."""

    def __init__(self, fire, alert_symbols, name="biz-updates"):
        self.fire, self.alert_symbols, self.name = fire, alert_symbols, name
        self.status = {"last_run": None, "read": 0, "fired": 0, "last_error": None}
        self.last_day = None

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name=self.name).start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("business updates:", e)
            time.sleep(300)

    def due(self, now: datetime) -> date | None:
        local = now.astimezone(IST)
        day = local.date()
        if local.strftime("%H:%M") < RUN_AT or self.last_day == day:
            return None
        if db.get_setting("newsjob:bizupd") == day.isoformat():
            self.last_day = day
            return None
        return day

    def run(self, now: datetime) -> dict:
        feed, docs_api, ai = _wire["feed"](), _wire["docs"](), _wire["ai"]() if _wire["ai"] else None
        since = (now.astimezone(IST) - timedelta(days=JOB_DAYS)).date().isoformat()
        symbols = sorted({s for v in SECTORS.values() for s, _ in v["symbols"]} | set(self.alert_symbols()))
        rows, read, problems = [], 0, []
        for sym in symbols:
            try:
                items = feed.announcements(sym)
            except SourceError as e:
                problems.append(f"{sym}: {e}")
                continue
            try:
                got = read_new(sym, items, docs_api, ai, limit=3, since=since)
            except Exception as e:                          # the AI being down mustn't stop the alerts on filings
                got = {"read": 0, "problems": [str(e)[:120]]}
            read += got["read"]
            rows += alert_rows(sym, items, (now.astimezone(IST) - timedelta(days=3)).date().isoformat())
        fired = self.fire(rows, now) if rows else 0
        self.status.update(last_run=now.isoformat(timespec="minutes"), read=read, fired=fired,
                           last_error="; ".join(problems[:3]) or None)
        return {"read": read, "fired": fired, "problems": problems}

    def tick(self, now: datetime):
        day = self.due(now)
        if not day:
            return None
        self.last_day = day
        db.set_setting("newsjob:bizupd", day.isoformat())
        return self.run(now)


# ---------- the routes ----------
router = APIRouter(tags=["invest"])


def _allowed(profile: dict) -> bool:
    return allows(access_plan(profile), "biz_updates")


def _symbol(symbol: str) -> str:
    sym = str(symbol or "").strip().upper()
    if not SYMBOL.match(sym):
        err(400, "bad_symbol", "That doesn't look like a ticker.")
    return sym


def _items(sym: str) -> tuple[list[dict], list[str]]:
    try:
        return _wire["feed"]().announcements(sym, LOOKBACK_DAYS), []
    except SourceError as e:
        return [], [str(e)]


@router.get("/research/business-updates/{symbol}")
def business_updates(symbol: str, profile=Depends(current_profile)):
    """One Indian company's monthly or quarterly business updates: the filings for everyone; the figures read from them,
    with the changes and the chart, on Basic and up."""
    sym = _symbol(symbol)
    items, problems = _items(sym)
    return ok(view(sym, items, _allowed(profile), problems))


@router.post("/research/business-updates/{symbol}/read")
def business_updates_read(symbol: str, profile=Depends(current_profile)):
    """Read the newest business updates not read yet (a few at a time; each is read once for everyone)."""
    sym = _symbol(symbol)
    if not _allowed(profile):
        err(402, "upgrade_required", f"Business updates read into numbers are on the {PLANS[FEATURE_PLAN['biz_updates']]['name']} plan.")
    items, problems = _items(sym)
    if problems and not items:
        err(503, "filings_unavailable", problems[0])
    try:
        got = read_new(sym, items, _wire["docs"](), _wire["ai"]() if _wire["ai"] else None)
    except AIError as e:
        err(503, "ai_unavailable", str(e))
    return ok({**view(sym, items, True, got["problems"]), "just_read": got["read"]})


@router.get("/invest/business-updates")
def business_updates_sector(sector: str = "autos", profile=Depends(current_profile)):
    """A sector's monthly or quarterly figures side by side, alphabetical. Basic and up."""
    if sector not in SECTORS:
        err(404, "no_sector", "That sector isn't on the list.")
    if not _allowed(profile):
        err(402, "upgrade_required", f"The sector view of business updates is on the {PLANS[FEATURE_PLAN['biz_updates']]['name']} plan.")
    return ok(sector_view(sector))
