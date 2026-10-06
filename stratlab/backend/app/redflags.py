"""Red-flag filings across every company, and US holders above 5%, kept from a daily read so a page never waits on a
source.

India: each evening the exchange's announcements for the whole market are read, one call a day, and the red and
amber ones (the same fixed keyword rules as a company's own page: fund raises, pledges, auditor and director
resignations, defaults, regulator action, rating downgrades) are stored with the company's symbol and name.
US: each evening the SEC filing list of every S&P 500 company is read and its Form 8-K items that match fixed rules
are stored: 1.03 bankruptcy, 3.01 delisting or listing-rule notice, 4.01 change of auditor, 4.02 earlier financial
statements not to be relied on, 5.02 director or officer change. The same read also keeps each company's Schedule
13D and 13G filings (us_holders).

Stored by month (redflags:<region>:<YYYY-MM>) with a state row per region (redflags:state:<region>), so a page reads
only the months it asks for. Facts as filed: the label is the rule that matched, the subject is the filing's own
wording, and the link opens the filing. Nothing here says what a company or its shares will do."""
import json
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import db, deals, universes, us_holders  # noqa: F401  (deals first: it is imported back while the newsletter job loads)
from .intel import filings
from .intel.net import SourceError, TTLCache
from .newsletter import job as news_job

KEY = "redflags:"                     # redflags:<region>:<YYYY-MM> = {"items": [...]}
HOLD_KEY = "redflags:13dg:"           # redflags:13dg:US:<YYYY-MM> = {"items": [...]}
STATE_KEY = "redflags:state:"         # redflags:state:<region> = {"through", "at", "companies", "problems", ...}
REGIONS = ("IN", "US")
RUN_AT = {"IN": ("Asia/Kolkata", "21:00"), "US": ("America/New_York", "19:30")}     # after most filings of the day
FIRST_DAYS = {"IN": 45, "US": 90}     # how far back the first run reads
OVERLAP = 2                           # days read again each run (late filings, corrected rows)
KEEP_DAYS = 400                       # the stored months a query can reach
PAGE = 25
MAX_PAGE = 100
GIVE_UP = 8                           # this many failed calls in a row: the source is down, the run stops and keeps the old
COVER_READS = 40                      # holder covers read per run (newest first)
PAUSE = 0.25                          # seconds between the SEC's documents

# the 8-K items worth a flag: item -> (id, label, severity)
US_ITEMS = {
    "1.03": ("8k_1_03", "Bankruptcy or receivership (Item 1.03)", "red"),
    "3.01": ("8k_3_01", "Delisting or listing-rule notice (Item 3.01)", "red"),
    "4.01": ("8k_4_01", "Change of auditor (Item 4.01)", "red"),
    "4.02": ("8k_4_02", "Earlier financial statements not to be relied on (Item 4.02)", "red"),
    "5.02": ("8k_5_02", "Director or officer change (Item 5.02)", "amber"),
}
US_WORDS = {
    "1.03": "Bankruptcy or Receivership", "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule or Standard",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements or a Related Audit Report",
    "5.02": "Departure of Directors or Certain Officers; Election of Directors; Appointment of Certain Officers",
}
_lock = threading.Lock()
_mem = TTLCache(max_items=60)


class Months:
    """Items kept one document per month under `prefix`+region+":"+month, merged by id."""

    def __init__(self, prefix: str):
        self.prefix = prefix

    def key(self, region: str, month: str) -> str:
        return f"{self.prefix}{region}:{month}"

    def load(self, region: str, month: str) -> list[dict]:
        k = self.key(region, month)
        hit = _mem.get(k)
        if hit is not None:
            return hit
        try:
            raw = db.json_value(db.get_setting(k), {})
        except Exception:
            raw = {}
        items = [i for i in raw.get("items") or [] if isinstance(i, dict) and i.get("id") and i.get("at")]
        _mem.set(k, items, 60)
        return items

    def add(self, region: str, items: list[dict], replace: bool = False) -> int:
        """Merge items into their months; a new id is added, a known id is kept as stored unless `replace`. Returns
        how many ids were new."""
        by_month: dict[str, list[dict]] = {}
        for i in items:
            by_month.setdefault(i["at"][:7], []).append(i)
        new = 0
        with _lock:
            for month, rows in by_month.items():
                have = {i["id"]: i for i in self.load(region, month)}
                for r in rows:
                    if r["id"] not in have:
                        new += 1
                    if replace or r["id"] not in have:
                        have[r["id"]] = r
                k = self.key(region, month)
                db.set_setting(k, json.dumps({"items": sorted(have.values(), key=lambda x: (x["at"], x["id"]), reverse=True)},
                                             separators=(",", ":")))
                _mem.set(k, None, 0)
        return new

    def between(self, region: str, frm: date, to: date) -> list[dict]:
        out, m = [], date(frm.year, frm.month, 1)
        while m <= to:
            out += [i for i in self.load(region, m.strftime("%Y-%m")) if frm.isoformat() <= i["at"][:10] <= to.isoformat()]
            m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
        return out


flags, holds = Months(KEY), Months(HOLD_KEY)


def forget():
    _mem.clear()


# ---------- the state of each region's run ----------
def state(region: str) -> dict:
    try:
        raw = db.json_value(db.get_setting(STATE_KEY + region), {})
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _set_state(region: str, **kw):
    s = state(region)
    s.update(kw)
    db.set_setting(STATE_KEY + region, json.dumps(s))


def _now() -> str:
    return datetime.now(ZoneInfo("UTC")).isoformat(timespec="seconds")


# ---------- reading ----------
def us_items(subs: dict, symbol: str, company: str | None, since: date) -> list[dict]:
    """The 8-K items of one company's filing list that match US_ITEMS, one row per matching item per filing:
    {id, symbol, company, at, category, label, severity, subject, url}."""
    rec = ((subs or {}).get("filings") or {}).get("recent") or {}
    forms, dates, accs, docs = (rec.get(k) or [] for k in ("form", "filingDate", "accessionNumber", "primaryDocument"))
    its = rec.get("items") or [""] * len(forms)
    cik = int((subs or {}).get("cik") or 0)
    out = []
    for form, at, acc, doc, raw in zip(forms, dates, accs, docs, its):
        if form not in ("8-K", "8-K/A") or not at or at < since.isoformat() or not acc:
            continue
        have = [x.strip() for x in str(raw or "").split(",")]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}" if doc else None
        for item in have:
            if item in US_ITEMS:
                cid, label, sev = US_ITEMS[item]
                out.append({"id": f"{symbol}|{acc}|{item}", "symbol": symbol, "company": company, "at": at, "category": cid,
                            "label": label, "severity": sev, "subject": f"Form {form}, Item {item}: {US_WORDS[item]}", "url": url})
    return out


class Runner:
    """Reads one region's sources and stores what they say. `feeds()` gives {"in": the exchange feed, "sec": the SEC client}."""

    def __init__(self, feeds, sleep=time.sleep, pause: float = PAUSE):
        self.feeds, self.sleep, self.pause = feeds, sleep, pause
        self.lock = threading.Lock()
        self.running: str | None = None

    def run(self, region: str, today: date | None = None) -> dict:
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "error": "A red-flag read is already going."}
        try:
            self.running = region
            return self.run_india(today) if region == "IN" else self.run_us(today)
        finally:
            self.running = None
            self.lock.release()

    def run_india(self, today: date | None = None) -> dict:
        feed = self.feeds()["in"]
        today = today or datetime.now(ZoneInfo("Asia/Kolkata")).date()
        st = state("IN")
        try:
            start = date.fromisoformat(st["through"]) - timedelta(days=OVERLAP)
        except (KeyError, ValueError, TypeError):
            start = today - timedelta(days=FIRST_DAYS["IN"])
        start = max(start, today - timedelta(days=KEEP_DAYS))
        day, through, new, got, fails, last_error = start, st.get("through"), 0, 0, 0, None
        while day <= today:
            if day.weekday() < 5 or day == today:       # exchanges file on weekdays; today is read whatever it is
                try:
                    items = feed.market_flags(day)
                except SourceError as e:
                    fails, last_error = fails + 1, str(e)[:160]
                    if fails >= GIVE_UP or getattr(e, "busy", False):
                        break
                    day += timedelta(days=1)
                    continue
                fails = 0
                new += flags.add("IN", items)
                got += 1
                through = day.isoformat()
                if self.pause:
                    self.sleep(self.pause)
            day += timedelta(days=1)
        if not got:
            _set_state("IN", last_error=last_error or "no day could be read", failed_at=_now())
            raise RuntimeError(f"The exchange's announcements couldn't be read ({last_error or 'no data'}).")
        _set_state("IN", through=through, at=_now(), last_error=last_error, days_read=got, new=new)
        return {"ok": True, "region": "IN", "through": through, "days": got, "new": new, "error": last_error}

    def run_us(self, today: date | None = None) -> dict:
        sec = self.feeds()["sec"]
        today = today or datetime.now(ZoneInfo("America/New_York")).date()
        st = state("US")
        first = not st.get("through")
        since = today - timedelta(days=FIRST_DAYS["US"] if first else (today - date.fromisoformat(st["through"])).days + OVERLAP + 1)
        names, ciks = universes.sp500_names(), universes.sp500_ciks()
        found, held, read, fails, last_error = [], [], 0, 0, None
        for sym in sorted(ciks):
            try:
                subs = sec.submissions(ciks[sym], fresh=True)
            except SourceError as e:
                fails, last_error = fails + 1, f"{sym}: {str(e)[:120]}"
                if fails >= GIVE_UP and not read:
                    raise RuntimeError(f"The SEC isn't answering ({last_error}).") from None
                if getattr(e, "busy", False) and fails >= GIVE_UP:
                    break
                continue
            fails = 0
            read += 1
            found += us_items(subs, sym, names.get(sym), since)
            held += us_holders.items_from_subs(subs, sym, names.get(sym), today)
        if not read:
            raise RuntimeError(f"No company's filing list could be read ({last_error or 'no data'}).")
        new = flags.add("US", found)
        # holders: keep what is already read, add the new filings, then read some covers
        stored = {i["id"]: i for i in holds.between("US", today - timedelta(days=us_holders.LOOKBACK_DAYS + 31), today)}
        fresh = [h if h["id"] not in stored else stored[h["id"]] for h in held]
        done, failed = us_holders.read_pending(fresh, lambda url: sec.document(url), COVER_READS)
        holds.add("US", fresh, replace=True)
        _set_state("US", through=today.isoformat(), at=_now(), last_error=last_error, companies=read, new=new,
                   holders=len(fresh), covers_read=len(done), covers_failed=failed)
        return {"ok": True, "region": "US", "through": today.isoformat(), "companies": read, "new": new, "covers_read": len(done),
                "error": last_error}

    def read_covers(self, today: date | None = None, limit: int = COVER_READS) -> int:
        """Read more holder covers (the SEC's documents) without re-reading the filing lists."""
        sec = self.feeds()["sec"]
        today = today or datetime.now(ZoneInfo("America/New_York")).date()
        items = holds.between("US", today - timedelta(days=us_holders.LOOKBACK_DAYS + 31), today)
        done, _ = us_holders.read_pending(items, lambda url: sec.document(url), limit)
        if done:
            holds.add("US", done, replace=True)
        return len(done)


# ---------- the daily job ----------
class Job(news_job.Job):
    """After each region's evening RUN_AT on its trading days, the read of that region, marked done in the database
    (newsjob:redflags-<region>) only once it has stored its rows; a failed run is tried again half an hour later. A
    region with nothing stored yet is read at the first chance, any day."""

    def __init__(self, runner: Runner):
        super().__init__()
        self.runner = runner
        self.retry: dict[str, float] = {}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="redflags").start()

    def _loop(self):
        time.sleep(900)                 # after startup traffic and the other morning jobs
        super()._loop()

    def tick(self, now: datetime) -> int:
        ran = 0
        for region in REGIONS:
            name = f"redflags-{region}"
            if time.time() < self.retry.get(name, 0):
                continue
            tz, at = RUN_AT[region]
            day = self.due(name, now, tz, at, region=region)
            if not day and (self.last.get(f"{name}-filled") or state(region).get("through")):
                continue
            try:
                out = self.runner.run(region)
            except Exception as e:
                self.retry[name] = time.time() + 1800
                self.status["last_error"] = f"{region}: {str(e)[:200]}"
                continue
            if not out.get("ok"):
                continue
            if day:
                self.mark(name, day)
            self.last[f"{name}-filled"] = "1"
            ran += 1
            self.status.update(last_run=now.isoformat(), last_error=None)
        return ran


# ---------- what the pages show ----------
def types(region: str) -> list[dict]:
    """The flag types a region's list can hold: [{id, label, severity}] (the filter's choices)."""
    if region == "US":
        return [{"id": v[0], "label": v[1].split(" (")[0], "severity": v[2]} for v in US_ITEMS.values()]
    return [{"id": cid, "label": label, "severity": sev} for cid, label, sev, _ in filings.RULES if sev != "info"]


def _day(v, default: date) -> date:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return default


def listing(region: str, flag: str = "", frm: str | None = None, to: str | None = None, page: int = 1, size: int = PAGE,
            q: str = "", symbols: set[str] | None = None, today: date | None = None) -> dict:
    """Flagged filings of every company (or of `symbols`), newest first, one page at a time. `flag` is a type id
    (several, comma-separated), `frm` and `to` an inclusive date range (default: the last 90 days), `q` part of a
    symbol or company name. The counts by type are for the same dates, companies and search, whichever flag is picked."""
    today = today or (datetime.now(ZoneInfo("Asia/Kolkata" if region == "IN" else "America/New_York")).date())
    to_d = min(_day(to, today), today)
    frm_d = max(_day(frm, to_d - timedelta(days=90)), today - timedelta(days=KEEP_DAYS))
    if frm_d > to_d:
        frm_d = to_d
    q = "".join(ch for ch in (q or "").upper() if ch.isalnum() or ch in "&-. ").strip()[:30]
    ids = {x for x in (flag or "").split(",") if x}
    rows = [i for i in flags.between(region, frm_d, to_d)
            if (symbols is None or i["symbol"] in symbols) and (not q or q in i["symbol"] or q in str(i.get("company") or "").upper())]
    counts: dict[str, int] = {}
    for i in rows:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    shown = [i for i in rows if not ids or i["category"] in ids]
    shown.sort(key=lambda i: (i["at"], i["symbol"], i["id"]), reverse=True)
    size = max(1, min(int(size or PAGE), MAX_PAGE))
    pages = max(1, -(-len(shown) // size))
    page = max(1, min(int(page or 1), pages))
    st = state(region)
    return {"region": region, "items": shown[(page - 1) * size:page * size], "total": len(shown), "page": page, "pages": pages,
            "size": size, "from": frm_d.isoformat(), "to": to_d.isoformat(), "flag": ",".join(sorted(ids)),
            "companies": len({i["symbol"] for i in shown}),
            "types": [{**t, "count": counts.get(t["id"], 0)} for t in types(region)],
            "as_of": st.get("through"), "updated_at": st.get("at"),
            "covers": universes.sp500_doc()["name"] if region == "US" else "NSE-listed companies"}


def holders_listing(symbol: str = "", form: str = "", page: int = 1, size: int = PAGE, today: date | None = None) -> dict:
    """13D and 13G filings: one company's (by ticker), or every S&P 500 company's, newest first. `form` is 13D or 13G."""
    today = today or datetime.now(ZoneInfo("America/New_York")).date()
    sym = "".join(ch for ch in (symbol or "").upper() if ch.isalnum() or ch in "-.")[:12].replace(".", "-")
    rows = holds.between("US", today - timedelta(days=us_holders.LOOKBACK_DAYS), today)
    rows = [i for i in rows if (not sym or i["symbol"] == sym) and (form not in ("13D", "13G") or i["kind"] == form)]
    rows.sort(key=lambda i: (i["at"], i["symbol"], i["id"]), reverse=True)
    size = max(1, min(int(size or PAGE), MAX_PAGE))
    pages = max(1, -(-len(rows) // size))
    page = max(1, min(int(page or 1), pages))
    st = state("US")
    return {"region": "US", "symbol": sym, "items": rows[(page - 1) * size:page * size], "total": len(rows), "page": page, "pages": pages,
            "size": size, "as_of": st.get("through"), "updated_at": st.get("at"), "form": form if form in ("13D", "13G") else "",
            "unread": sum(1 for i in rows if not i.get("read"))}
