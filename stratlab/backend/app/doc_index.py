"""The nightly worker that fills the filings search index (doc_store.py), and how a document becomes searchable passages.

Bounded and polite by design:
- Off until the admin switches it on (Admin → Data and jobs → Filings search index, or POST /admin/doc-index/on).
- Once a night at RUN_AT (India time), between the evening's heavy runs (breadth, red flags, IPOs, all done by about
  10:30 PM) and the US close's (after 2 AM), for at most MAX_RUN_S. Each run first looks through a slice of the
  universe's filings for new documents (DISCOVER companies a market, a rotating slice, so every company is looked at
  every few nights), then reads at most NIGHT_CAP documents (BACKFILL_CAP while the admin's backfill runs), newest first.
- One document at a time, under memguard.heavy, with nothing kept in memory: a PDF of 1 MB and up is read in the
  short-lived child process (pdf_proc), the SEC's text is dropped from its cache once stored, and the text goes straight
  to Postgres.
- The existing readers do the work: the exchange's filings list (filings.IndiaFilings), deepdive.documents() and
  deepdive.readable() (which follows a cover letter to the company's own copy), docs.Docs for downloads and OCR of
  scans, and for the US the SEC's filing list (sec.documents), SEC.annual() and SEC.release_doc().
- At most one request every EXCHANGE_GAP_S to the exchanges' hosts (the SEC client keeps its own limit and declared
  user agent); a read that is refused or times out is tried again later with backoff, and the night's run stops after
  BREAK_AFTER refusals in a row.

Universe: NIFTY 500 call transcripts and investor presentations; S&P 500 annual reports (the business, risk factors and
management's discussion) and earnings releases (8-K exhibit 99), over the last DOC_DAYS. US call transcripts are not
filed with the SEC, so they are not covered.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from . import db, doc_store, job_status, leader, run_marks

IST = timezone(timedelta(hours=5, minutes=30))
SWITCH_KEY = "docidx:on"                 # "1": the nightly worker runs (off by default)
BACKFILL_KEY = "docidx:backfill"         # ISO date: until then the night's caps are the backfill's
CURSOR_KEY = "docidx:cursor:"            # per market: where the next night's look through the filings starts
RUN_KEY = "docidx:night"                 # run_marks: the night's run, once
RUN_AT = "00:15"                         # India time (12:15 AM)
RUN_UNTIL = "03:00"                      # a night's run starts only before this (a restart in the day never starts one)
MAX_RUN_S = 100 * 60                     # a run stops after this, wherever it is
NIGHT_CAP = 300                          # documents read a night
BACKFILL_CAP = 600                       # ...while a backfill runs
RUN_NOW_CAP = 25                         # documents read by Admin's Run now
DISCOVER = 60                            # companies a market whose filings are looked through a night
DISCOVER_BACKFILL = 250                  # ...during a backfill
BACKFILL_NIGHTS = 30
DOC_DAYS = 730                           # documents of the last two years
EXCHANGE_GAP_S = 4.0                     # at most one request this often to the exchanges' and companies' hosts
BREAK_AFTER = 5                          # refusals in a row that end the night's run
CHUNK_CHARS = 2000                       # a passage's size at most
INDIA_KINDS = ("transcript", "presentation")
US_KINDS = ("annual_report", "earnings_release")
COVER_CHARS = 8000                       # m53: a stored earnings release shorter than this whose text is the 8-K itself is its cover page
RECHECK_CAP = 20                         # ...read again at most this many a run (the release exhibit by its name: sec.release_doc), once each
RECHECK_KEY = "docidx:covers"            # JSON list of the filings already read again, never again
KIND_WORDS = {"transcript": "Call transcript", "presentation": "Investor presentation", "annual_report": "Annual report",
              "earnings_release": "Earnings release"}

_feeds: dict = {"filings": None, "sec": None, "docs": None}


def setup(filings_fn, sec_fn, docs_fn) -> None:
    """The sources (main.py's): the exchange's filings, the SEC client and the document reader."""
    _feeds.update(filings=filings_fn, sec=sec_fn, docs=docs_fn)


def _feed(name: str):
    fn = _feeds.get(name)
    return fn() if fn else None


# ---------- the switch ----------
def enabled() -> bool:
    try:
        return db.get_setting(SWITCH_KEY) == "1"
    except Exception:
        return False


def switch(on: bool) -> None:
    if on:
        db.set_setting(SWITCH_KEY, "1")
    else:
        db.delete_setting(SWITCH_KEY)


def backfill_until() -> str | None:
    try:
        v = db.get_setting(BACKFILL_KEY)
    except Exception:
        return None
    return v if v and v >= datetime.now(IST).date().isoformat() else None


def start_backfill(nights: int = BACKFILL_NIGHTS) -> str:
    until = (datetime.now(IST).date() + timedelta(days=nights)).isoformat()
    db.set_setting(BACKFILL_KEY, until)
    return until


def stop_backfill() -> None:
    db.delete_setting(BACKFILL_KEY)


# ---------- text into passages ----------
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_DIGITS = re.compile(r"\d+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def clean(text: str) -> str:
    """Text as it is stored: control characters out (the snippets' own markers can never come from a document), spaces
    tidied."""
    text = _CONTROL.sub(" ", text or "")
    return re.sub(r"[ \t ]+", " ", text)


def repeated_lines(pages: list[str]) -> set[str]:
    """Lines that repeat on more than half the pages (a page header or footer, a running title, "Page 3 of 20" with its
    number set aside): left out of the passages, so they don't match every search."""
    if len([p for p in pages if p]) < 3:
        return set()
    counts: dict[str, int] = {}
    for p in pages:
        for key in {_DIGITS.sub("#", ln.strip().lower()) for ln in (p or "").splitlines() if 0 < len(ln.strip()) <= 120}:
            counts[key] = counts.get(key, 0) + 1
    half = len(pages) / 2
    return {k for k, n in counts.items() if n > half}


def _pieces(paragraph: str, limit: int) -> list[str]:
    """A paragraph longer than `limit` cut at sentence ends (or, failing that, at spaces) into pieces of at most `limit`."""
    if len(paragraph) <= limit:
        return [paragraph]
    out, cur = [], ""
    for s in _SENTENCE.split(paragraph):
        while len(s) > limit:                       # one sentence longer than a passage: at a space before the limit
            cut = s.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            if cur:
                out.append(cur)
                cur = ""
            out.append(s[:cut].strip())
            s = s[cut:].strip()
        if cur and len(cur) + 1 + len(s) > limit:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return [p for p in out if p]


def chunk_pages(pages: list[str | None], limit: int = CHUNK_CHARS, numbered: bool = True) -> list[tuple[int | None, str]]:
    """[(page number from 1, or None when the pages aren't known; passage)]: each page's paragraphs packed into passages
    of up to `limit` characters, never across a page, with repeated headers and footers left out."""
    pages = [clean(p) if p else "" for p in pages]
    drop = repeated_lines(pages) if numbered else set()
    out: list[tuple[int | None, str]] = []
    for no, text in enumerate(pages, start=1):
        lines = [ln.strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if not drop or _DIGITS.sub("#", ln.lower()) not in drop]
        # paragraphs: split at blank lines; a page with none (PDF text often has one line per row) is one paragraph
        paras, cur = [], []
        for ln in lines:
            if ln:
                cur.append(ln)
            elif cur:
                paras.append(" ".join(cur))
                cur = []
        if cur:
            paras.append(" ".join(cur))
        buf = ""
        for para in paras:
            for piece in _pieces(para, limit):
                if buf and len(buf) + 1 + len(piece) > limit:
                    out.append((no if numbered else None, buf))
                    buf = piece
                else:
                    buf = f"{buf}\n{piece}" if buf else piece
        if buf:
            out.append((no if numbered else None, buf))
    return [(p, t) for p, t in out if len(t.strip()) >= 20]


_SECTION_TAG = re.compile(r"^\s*\[(?:BUSINESS|RISKS|MDNA)\]\s*$", re.M)


def chunk_text(text: str, limit: int = CHUNK_CHARS) -> list[tuple[int | None, str]]:
    """A document with no page numbers (an SEC filing's text, an OCR read): passages by paragraph."""
    return chunk_pages([_SECTION_TAG.sub("", text or "")], limit, numbered=False)


# ---------- reading the exchange's documents, page by page ----------
class Refused(Exception):
    """The source turned the request away or didn't answer (try again later, and count it for the breaker)."""


class PageReader:
    """deepdive.readable()'s document reader for the index: the same downloads and checks as docs.Docs.text() (only the
    exchanges' hosts or the company's own site, on public addresses, size and page caps, OCR of scans), but the pages are
    kept apart (joined with a form feed, so each passage keeps its page number), nothing is cached, and the exchanges'
    hosts are asked at most once every EXCHANGE_GAP_S."""

    def __init__(self, docs, gap: float = EXCHANGE_GAP_S, sleep=time.sleep, clock=time.monotonic):
        self.docs, self.gap, self.sleep, self.clock = docs, gap, sleep, clock
        self.last = -1e9
        self.ocr: set[str] = set()
        self.refusals = 0          # refusals or no answer met during the current document

    def _wait(self) -> None:
        left = self.gap - (self.clock() - self.last)
        if left > 0:
            self.sleep(left)
        self.last = self.clock()

    def _get(self, url: str, extra_hosts: tuple[str, ...], limit: int) -> bytes:
        from .intel.net import SourceError
        self._wait()
        try:
            return self.docs._download(url, extra_hosts, limit)
        except SourceError as e:
            if e.busy or re.search(r"\((?:403|429)\)", str(e)):
                self.refusals += 1
            raise

    def text(self, url: str, extra_hosts: tuple[str, ...] = ()) -> str:
        from . import docs as D, pdf_proc
        from .intel.net import SourceError
        if not D.allowed(url, extra_hosts):
            raise SourceError("the exchange", "That document isn't on the exchange's or the company's own site.")
        buf = self._get(url, extra_hosts, D.MAX_BYTES)
        if not buf[:5].startswith(b"%PDF"):
            raise SourceError("the exchange", "The link didn't return a PDF.")
        try:
            pages, count = pdf_proc.page_texts(buf, D.MAX_PAGES)
        except Exception as e:
            raise SourceError("the exchange", f"The PDF couldn't be read ({e.__class__.__name__}).") from None
        tidy = [D._tidy(p) if p else "" for p in pages]
        if D.scanned("\n".join(tidy), count):
            read = self.docs._ocr(buf)
            if read:
                self.ocr.add(url)
                return read
        return "\f".join(tidy)

    def page(self, url: str, extra_hosts: tuple[str, ...] = ()) -> str:
        from . import docs as D
        from .intel.net import SourceError
        u = urlparse(url)
        if u.scheme != "https" or not D._host_ok(u.hostname, extra_hosts):
            raise SourceError("the exchange", "That page isn't on a site the company's filing named.")
        return self._get(url, extra_hosts, 2 * 1024 * 1024).decode("utf-8", "replace")


def read_india(reader: PageReader, item: dict) -> tuple[dict, list[tuple[int | None, str]]] | None:
    """One Indian filing's document as passages, following a cover letter to the document it names; None when the filing
    holds no readable document."""
    from . import deepdive
    d = {"kind": item["kind"], "at": item["filed_at"], "title": item.get("title") or KIND_WORDS.get(item["kind"], "Document"), "url": item["url"]}
    problems: list[str] = []
    got = deepdive.readable(reader, [d], 1, problems)
    if not got:
        return None
    found, text = got[0]
    link = found.get("url") or item["url"]
    if link in reader.ocr:
        chunks, pages, ocr = chunk_text(text), None, True
    else:
        parts = text.split("\f")
        chunks, pages, ocr = chunk_pages(parts), len(parts), False
    meta = {"link": link, "host": (urlparse(link).hostname or "").lower(), "pages": pages, "ocr": ocr,
            "sha1": hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()}
    return meta, chunks


def read_us(sec, item: dict) -> tuple[dict, list[tuple[int | None, str]]] | None:
    """One SEC filing as passages: an annual report's business, risk factors and management's discussion, or an earnings
    release (the 8-K's exhibit 99). The SEC client's copy of the text is dropped once read."""
    url = item["url"]
    if item["kind"] == "annual_report":
        text, link = sec.annual({"url": url}), url
        drop = [url]
    else:
        folder = url.rsplit("/", 1)[0] + "/"
        link, text = sec.release_doc({"url": url, "folder": folder})
        drop = [url, link]
    for u in drop:
        try:
            sec.cache.pop(("doc", u))
        except Exception:
            pass
    if not text or len(text) < 500:
        return None
    meta = {"link": link, "host": (urlparse(link).hostname or "").lower(), "pages": None, "ocr": False,
            "sha1": hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()}
    return meta, chunk_text(text)


# ---------- which companies, and their documents ----------
def universe(region: str) -> list[dict]:
    """[{symbol, company, sector, cik}] of the market's indexed companies: India's NIFTY 500 (the last good list the
    breadth job kept, else the screens' 500 largest), the US's S&P 500."""
    from . import breadth, universes
    try:
        sectors = breadth.sector_map(region)
    except Exception:
        sectors = {}
    if region == "US":
        return [{"symbol": s, "company": n, "sector": sectors.get(s) or sec_ or None, "cik": int(c) if c else None}
                for s, n, sec_, c in universes.sp500_doc()["rows"]]
    from . import screens
    try:
        rows = screens.load_index("IN").get("rows") or []
    except Exception:
        rows = []
    names = {r["symbol"]: r.get("name") for r in rows}
    try:
        syms = breadth.members("nifty500")
    except Exception:
        syms = []
    if not syms:
        syms = [r["symbol"] for r in sorted(rows, key=lambda r: r.get("rank") or 1e9)[:500]]
    return [{"symbol": s, "company": names.get(s) or s, "sector": sectors.get(s), "cik": None} for s in syms]


def found_india(feed, co: dict) -> list[dict]:
    """A company's transcripts and presentations of the last DOC_DAYS, as queue rows."""
    from . import deepdive
    items = feed.announcements(co["symbol"], DOC_DAYS)
    out = []
    for d in deepdive.documents(items):
        if d["kind"] in INDIA_KINDS and str(d.get("at") or "")[:10]:
            out.append({"url": d["url"], "region": "IN", "symbol": co["symbol"], "kind": d["kind"], "filed_at": d["at"][:10],
                        "title": str(d.get("title") or "")[:200], "company": co.get("company"), "sector": co.get("sector")})
    return out


def found_us(sec, co: dict) -> list[dict]:
    """A company's annual reports and earnings releases of the last DOC_DAYS, as queue rows."""
    from .intel import sec as S
    if not co.get("cik"):
        return []
    subs = sec.submissions(int(co["cik"]))
    return [{"url": d["url"], "region": "US", "symbol": co["symbol"], "kind": d["kind"], "filed_at": d["at"][:10],
             "title": d.get("title"), "company": co.get("company"), "sector": co.get("sector")}
            for d in S.documents(subs, DOC_DAYS) if d["kind"] in US_KINDS]


# ---------- the run ----------
class Job:
    """The nightly run: look for new documents, then read the queue up to the night's cap."""

    def __init__(self):
        self.status = job_status.Status("docindex", {"last_run": None, "last_error": None, "read": 0, "found": 0, "failed": 0})
        self.lock = threading.Lock()
        self.running = False
        self.started: float | None = None
        self.sleep = time.sleep
        self.clock = time.monotonic

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="doc-index").start()

    def _loop(self):
        time.sleep(600)                       # after startup traffic
        while True:
            try:
                if leader.leading():
                    self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("doc index:", str(e)[:200])
            time.sleep(300)

    def due_day(self, now: datetime) -> str | None:
        """Tonight's date (India) when the run is due now and hasn't run, else None."""
        local = now.astimezone(IST)
        if not (RUN_AT <= local.strftime("%H:%M") < RUN_UNTIL):
            return None
        return local.date().isoformat()

    def tick(self, now: datetime) -> dict | None:
        if not enabled() or doc_store.store() is None:
            return None
        day = self.due_day(now)
        if not day:
            return None
        run = run_marks.claim(RUN_KEY, day)
        if run is None:
            return None
        back = bool(backfill_until())
        out = self.run(BACKFILL_CAP if back else NIGHT_CAP, DISCOVER_BACKFILL if back else DISCOVER, beat=run.beat)
        if out.get("ok"):
            run.done()
        return out

    def run(self, cap: int, discover: int, beat=None, max_s: float = MAX_RUN_S) -> dict:
        """Look through `discover` companies a market for new documents, then read up to `cap` documents, one at a time,
        for at most `max_s` seconds. Returns what it did."""
        store = doc_store.store()
        if store is None:
            return {"ok": False, "error": "The search index has no database (MARKET_DATABASE_URL isn't set)."}
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "error": "A run is already going."}
        self.running, self.started = True, time.time()
        began = self.clock()
        left = lambda: max_s - (self.clock() - began)  # noqa: E731
        out = {"ok": True, "found": 0, "read": 0, "failed": 0, "passages": 0, "problems": [], "stopped": None}
        try:
            out["found"] = self.discover(store, discover, left, out["problems"], beat)
            self.read_queue(store, cap, left, out, beat)
            self.reread_covers(store, left, out, beat)
            stats = {}
            try:
                stats = store.queue_stats()
            except Exception:
                pass
            self.status.update(last_run=datetime.now(timezone.utc).isoformat(timespec="seconds"), read=out["read"], found=out["found"],
                               failed=out["failed"], passages=out["passages"], stopped=out["stopped"],
                               problems=out["problems"][:5], last_error=out["stopped"] if out["stopped"] and "refused" in out["stopped"] else None,
                               waiting=stats.get("waiting"), failed_total=stats.get("failed"), bytes=stats.get("bytes"))
        except Exception as e:
            out.update(ok=False, error=str(e)[:200])
            self.status.update(last_error=str(e)[:200])
        finally:
            self.running, self.started = False, None
            self.lock.release()
        return out

    def discover(self, store, per_market: int, left, problems: list[str], beat=None) -> int:
        """New documents of the next `per_market` companies in each market (where the last run stopped), queued."""
        from . import memguard
        added = 0
        feeds = {"IN": _feed("filings"), "US": _feed("sec")}
        for region in ("IN", "US"):
            feed = feeds[region]
            if feed is None or per_market <= 0:
                continue
            cos = universe(region)
            if not cos:
                continue
            try:
                start = int(db.get_setting(CURSOR_KEY + region) or 0) % len(cos)
            except (TypeError, ValueError):
                start = 0
            n, failed = 0, 0
            for i in range(min(per_market, len(cos))):
                if left() <= 0 or failed >= BREAK_AFTER:      # the filings list refused several in a row: tomorrow, from here
                    break
                co = cos[(start + i) % len(cos)]
                try:
                    with memguard.heavy("doc-index"):
                        rows = found_india(feed, co) if region == "IN" else found_us(feed, co)
                        rows = [r for r in rows if r["url"]]
                        added += store.enqueue(rows)
                    failed = 0
                except Exception as e:
                    failed += 1
                    problems.append(f"{region} {co['symbol']}: the filings list couldn't be read ({str(e)[:100]})")
                n = i + 1
                if region == "IN":
                    self.sleep(EXCHANGE_GAP_S)          # the exchange's filings list, politely
                if beat:
                    beat()
            db.set_setting(CURSOR_KEY + region, str((start + n) % len(cos)))
        return added

    def reread_covers(self, store, left, out: dict, beat=None) -> None:
        _reread_covers(self, store, left, out, beat)

    def read_queue(self, store, cap: int, left, out: dict, beat=None) -> None:
        from . import memguard
        docs, sec = _feed("docs"), _feed("sec")
        reader = PageReader(docs, sleep=self.sleep, clock=self.clock) if docs is not None else None
        refused_in_a_row = 0
        while out["read"] + out["failed"] < cap:
            if left() <= 0:
                out["stopped"] = "Stopped at the run's time limit."
                return
            batch = store.due(min(25, cap - out["read"] - out["failed"]))
            if not batch:
                return
            for item in batch:
                if left() <= 0 or out["read"] + out["failed"] >= cap:
                    break
                refused = False
                try:
                    with memguard.heavy("doc-index"):
                        if item["region"] == "IN":
                            if reader is None:
                                raise Refused("no document reader")
                            reader.refusals = 0
                            got = read_india(reader, item)
                            refused = reader.refusals > 0 and got is None
                        else:
                            if sec is None:
                                raise Refused("no SEC client")
                            got = read_us(sec, item)
                        if got is not None:
                            meta, chunks = got
                            if not chunks:
                                got = None
                            else:
                                store.save({**item, **meta}, chunks)
                                out["read"] += 1
                                out["passages"] += len(chunks)
                    if got is None:
                        out["failed"] += 1
                        if refused:
                            store.retry(item["url"], "the source didn't answer or refused", _backoff(item.get("tries") or 0))
                        else:
                            store.retry(item["url"], "no readable document in the filing", 0, give_up=True)
                except Exception as e:
                    from .intel.net import SourceError
                    busy = isinstance(e, (Refused,)) or (isinstance(e, SourceError) and (e.busy or bool(re.search(r"\((?:403|429)\)", str(e)))))
                    refused = busy
                    out["failed"] += 1
                    out["problems"].append(f"{item['region']} {item['symbol']}: {str(e)[:120]}")
                    store.retry(item["url"], str(e)[:300], _backoff(item.get("tries") or 0), give_up=not busy)
                refused_in_a_row = refused_in_a_row + 1 if refused else 0
                if refused_in_a_row >= BREAK_AFTER:
                    out["stopped"] = f"Paused for the night: the source refused or didn't answer {BREAK_AFTER} reads in a row."
                    return
                if beat:
                    beat()


def _rechecked() -> list[str]:
    import json
    try:
        got = json.loads(db.get_setting(RECHECK_KEY) or "[]")
        return [str(u) for u in got] if isinstance(got, list) else []
    except Exception:
        return []


def _reread_covers(job, store, left, out: dict, beat=None) -> None:
    """m53: US earnings releases stored before the release exhibit was found by its name ("pypl3q-26earningsrelease.htm", not "ex99"):
    their stored text is the 8-K's cover page (the filing itself, a few thousand characters). Up to RECHECK_CAP a run, within the run's
    time, each is read again once: replaced when the filing's one other document is the release, else left as it is; never again either
    way. A refused read is tried on a later night."""
    import json
    from . import memguard
    sec = _feed("sec")
    if sec is None or not hasattr(store, "covers") or left() <= 0:
        return
    done = _rechecked()
    try:
        rows = store.covers(COVER_CHARS, RECHECK_CAP, done)
    except Exception as e:
        out["problems"].append(f"covers: {str(e)[:120]}")
        return
    out.setdefault("reread", 0)
    for item in rows:
        if left() <= 0:
            break
        try:
            with memguard.heavy("doc-index"):
                got = read_us(sec, item)
                if got is not None and got[0]["link"] != item["url"] and got[1]:
                    store.save({**item, **got[0]}, got[1])
                    out["reread"] += 1
        except Exception as e:
            from .intel.net import SourceError
            if isinstance(e, SourceError) and (e.busy or re.search(r"\((?:403|429)\)", str(e))):
                out["problems"].append(f"US {item['symbol']}: cover not read again ({str(e)[:80]})")
                break
            out["problems"].append(f"US {item['symbol']}: {str(e)[:120]}")
        done.append(item["url"])
        if beat:
            beat()
    try:
        db.set_setting(RECHECK_KEY, json.dumps(done[-5000:]))
    except Exception as e:
        out["problems"].append(f"covers: not kept ({str(e)[:80]})")


def _backoff(tries: int) -> float:
    """Seconds before a refused read is tried again: 6 hours, then 12, 24, up to 3 days."""
    return min(6 * 3600 * (2 ** tries), 3 * 86400)


job = Job()


# ---------- Admin ----------
def admin_row() -> dict:
    """The job's row on Admin → Data and jobs (admin_jobs.rows)."""
    from .admin_jobs import _row
    st = job_status.kept("docindex", dict(job.status))
    on, back = enabled(), backfill_until()
    store = doc_store.store()
    log: list[str] = []
    if store is None:
        log.append("No database: the index lives in the market database (MARKET_DATABASE_URL).")
    else:
        try:
            cov = store.coverage()
            q = store.queue_stats()
            for region, word in (("IN", "India"), ("US", "US")):
                c = cov.get(region) or {}
                log.append(f"{word}: {c.get('documents', 0):,} documents of {c.get('companies', 0):,} companies"
                           + (f", newest filed {c['newest']}" if c.get("newest") else ""))
            total = sum((cov.get(r) or {}).get("documents", 0) for r in ("IN", "US"))
            share = (q["failed"] / (total + q["failed"]) * 100) if (total + q["failed"]) else 0
            log.append(f"Waiting to be read: {q['waiting']:,}. Failed: {q['failed']:,} ({share:.1f}%). On disk: {q['bytes'] / 1048576:,.0f} MB.")
            log += [f"Failed: {f['symbol']} {str(f['title'] or '')[:60]}: {f['error']}" for f in q["failures"][:3]]
        except Exception as e:
            log.append(f"The index couldn't be read: {str(e)[:120]}")
    if st.get("last_run"):
        log.insert(0, f"Last run: {st.get('read', 0)} read, {st.get('found', 0)} new found, {st.get('failed', 0)} not read"
                   + (f". {st['stopped']}" if st.get("stopped") else "."))
    cap = BACKFILL_CAP if back else NIGHT_CAP
    schedule = (f"Each night at 12:15 AM IST: looks through {DISCOVER_BACKFILL if back else DISCOVER} companies a market for new filings, then reads up "
                f"to {cap} documents, for at most {MAX_RUN_S // 60} minutes" + (f" (backfill until {back})" if back else "")) if on else "Off"
    run = [{"label": "Run now", "path": "/admin/doc-index/run"},
           {"label": "Turn off", "path": "/admin/doc-index/off"} if on else {"label": "Turn on", "path": "/admin/doc-index/on"},
           {"label": "Stop backfill", "path": "/admin/doc-index/backfill/stop"} if back else {"label": f"Backfill {BACKFILL_NIGHTS} nights", "path": "/admin/doc-index/backfill"}]
    note = None if on else "Off: switch it on to fill the filings search index each night."
    return _row("doc-index", "Filings search index", schedule, st.get("last_run"), st.get("last_error"), log, run,
                running=job.running, note=note, started=job.started)
