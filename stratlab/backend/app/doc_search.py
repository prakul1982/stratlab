"""Search inside companies' filings and call transcripts: the routes over the index in doc_store.py.

Signed-in only, and never the documents themselves: a hit is the company, the document, its date, and at most two
short verbatim extracts around the match (SNIPPET_FRAGMENTS of up to SNIPPET_WORDS words, HTML-escaped, the matched
words in <mark>), with a link to the exchange's, the company's or the SEC's own copy (at the page, where it is known).
No route returns a passage whole. Facts only: the companies' own words, no ranking of companies.

Plans (plans.py, DOC_SEARCH): Free sees the first DOC_SEARCH["free"]["hits"] hits of a search over the last year, with
no filter but the company; Basic every hit with every filter (market, companies, sector, a stored theme's companies,
kind of document, dates) over the last year; Pro every year stored, and the hits as a CSV.
"""
from __future__ import annotations

import csv
import html
import io
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from . import doc_index, doc_store
from .admin import admin_profile
from .auth import current_profile
from .plans import DOC_SEARCH, allows, plan_of
from .responses import err, ok

router = APIRouter(tags=["research"])
admin_router = APIRouter(tags=["admin"])

IST = timezone(timedelta(hours=5, minutes=30))
PAGE = 20                      # hits a page
EXPORT_HITS = 100              # hits a CSV holds at most
SNIPPET_FRAGMENTS = 2          # extracts a hit shows at most
SNIPPET_WORDS = 35             # words an extract holds at most
SNIPPET_CHARS = 280            # characters an extract holds at most
MAX_SYMBOLS = 20
NONE = "-"                     # a symbol no company has (a theme with no listed companies matches nothing)
PER_MINUTE = 30                # searches one account may run a minute
KINDS = {"IN": ("transcript", "presentation"), "US": ("annual_report", "earnings_release")}
KIND_LABEL = doc_index.KIND_WORDS
NOTE = ("The companies' own words, from the documents they filed with the exchange or the SEC. Each extract is short and links "
        "to the filed copy: read it there for the full context. Text read from a scanned page can hold reading errors. Not advice.")
COVERS = {"IN": "Call transcripts and investor presentations of NIFTY 500 companies, from the last two years.",
          "US": "Annual reports (business, risk factors, management's discussion) and earnings releases of S&P 500 companies, from the "
                "last two years. US call transcripts are not filed with the SEC, so they aren't included."}

_recent: dict[str, list[float]] = {}
_recent_lock = threading.Lock()


def _slow_down(uid: str) -> None:
    now = time.monotonic()
    with _recent_lock:
        hits = [t for t in _recent.get(uid, []) if now - t < 60]
        if len(hits) >= PER_MINUTE:
            err(429, "slow_down", "That's a lot of searches in a minute. Wait a moment, then search again.")
        _recent[uid] = hits + [now]
        if len(_recent) > 5000:                 # bounded: forget everyone else's minute
            for k in list(_recent)[:2500]:
                _recent.pop(k, None)


# ---------- the extracts ----------
_MARK = re.compile(r"[\x02\x03]")


def snippet(raw: str | None) -> list[str]:
    """ts_headline's text as safe HTML extracts: at most SNIPPET_FRAGMENTS of at most SNIPPET_WORDS words and SNIPPET_CHARS
    characters, everything escaped, and only then the match markers (\\x02 … \\x03) turned into <mark> … </mark>, so no text
    from a document can ever become markup."""
    out = []
    for frag in (raw or "").split("\x01")[:SNIPPET_FRAGMENTS]:
        words = frag.split()
        cut = len(words) > SNIPPET_WORDS
        text = " ".join(words[:SNIPPET_WORDS])
        visible = _MARK.sub("", text)
        if len(visible) > SNIPPET_CHARS:              # long words: cut at a space before the limit, counting visible characters only
            kept, n = [], 0
            for w in text.split(" "):
                size = len(_MARK.sub("", w)) + (1 if kept else 0)
                if n + size > SNIPPET_CHARS:
                    cut = True
                    break
                kept.append(w)
                n += size
            text = " ".join(kept)
        if not _MARK.sub("", text).strip():
            continue
        # a mark cut open by the limit is closed; a stray close is dropped
        safe, depth = [], 0
        for part in re.split(r"([\x02\x03])", text):
            if part == "\x02":
                if depth == 0:
                    safe.append("<mark>")
                    depth = 1
            elif part == "\x03":
                if depth == 1:
                    safe.append("</mark>")
                    depth = 0
            else:
                safe.append(html.escape(part, quote=True))
        if depth:
            safe.append("</mark>")
        out.append("".join(safe) + ("…" if cut else ""))
    return out


def plain(fragments: list[str]) -> str:
    """The extracts as plain text (the CSV): marks dropped, entities read back."""
    return " … ".join(html.unescape(re.sub(r"</?mark>", "", f)) for f in fragments)


def source_of(host: str | None) -> str:
    h = (host or "").lower()
    if h.endswith("nseindia.com"):
        return "NSE"
    if h.endswith("bseindia.com"):
        return "BSE"
    if h.endswith("sec.gov"):
        return "SEC"
    return "Company website"


def link_of(doc: dict, page: int | None) -> str | None:
    """The filed copy's address, at the page where the passage is (a PDF's #page=N)."""
    url = str(doc.get("link") or doc.get("url") or "")
    if not url.startswith("https://"):
        return None
    if page and url.lower().split("#")[0].split("?")[0].endswith(".pdf"):
        return f"{url.split('#')[0]}#page={int(page)}"
    return url


# ---------- reading the request ----------
_SYM = re.compile(r"[^A-Z0-9&.\-]")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _list(v: str | None, cap: int = 20) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()][:cap]


def _symbols(v: str | None) -> list[str]:
    out = []
    for s in _list(v, MAX_SYMBOLS):
        s = _SYM.sub("", s.upper())[:20]
        s = re.sub(r"\.(NS|BO)$", "", s)
        if s and s not in out:
            out.append(s)
    return out


def _day(v: str | None, name: str) -> str | None:
    v = (v or "").strip()[:10]
    if not v:
        return None
    if not _DAY.match(v):
        err(400, "bad_date", f"The {name} date should look like 2026-03-31.")
    try:
        date.fromisoformat(v)
    except ValueError:
        err(400, "bad_date", f"The {name} date isn't a real day.")
    return v


def theme_members(region: str, theme: str) -> tuple[str, list[str]]:
    """(the stored theme's name, its companies' symbols) from the theme library; a 404 when no theme by that name is stored."""
    from .intel import theme_library
    got = theme_library.stored(region, theme[:80])
    if not got:
        err(404, "no_theme", "No stored theme by that name for this market. Pick one from the list as you type.")
    payload = got.get("payload") or {}
    syms = []
    for grp in (payload.get("value_chain") or []) + (payload.get("sub_themes") or []):
        for c in grp.get("companies") or []:
            s = re.sub(r"\.(NS|BO)$", "", _SYM.sub("", str(c.get("ticker") or "").upper()))
            if s and s not in syms:
                syms.append(s)
    return str(got.get("name") or theme), syms


def limits(plan: str) -> dict:
    """What the plan gives here, for the page to say."""
    lim = DOC_SEARCH[plan]
    return {"hits": lim["hits"], "days": lim["days"], "filters": allows(plan, "doc_search"), "export": allows(plan, "doc_search_all")}


def _query(q: str) -> str:
    q = re.sub(r"\s+", " ", (q or "").replace("\x00", " ")).strip()[:200]
    if len(re.sub(r"[^\w]", "", q)) < 2:
        err(400, "bad_query", "Type a word or a phrase to search for (at least two letters).")
    return q


def run_search(profile: dict, q: str, region: str, symbols: str = "", sector: str = "", theme: str = "", kind: str = "",
               frm: str = "", to: str = "", page: int = 1, size: int = PAGE) -> dict:
    """The search behind both routes: the plan's limits applied, the best passage per document, one page of hits."""
    plan = plan_of(profile)
    lim = limits(plan)
    q = _query(q)
    region = "US" if str(region).upper() == "US" else "IN"
    syms, sectors, kinds = _symbols(symbols), _list(sector, 12), [k for k in _list(kind, 4) if k in KINDS[region]]
    frm_d, to_d = _day(frm, "from"), _day(to, "to")
    if not lim["filters"] and (sectors or kinds or theme.strip() or frm_d or to_d):
        err(402, "upgrade_required", "Filters beyond the company (sector, theme, kind of document and dates) are on the Basic plan.")
    theme_name = None
    if theme.strip():
        theme_name, members = theme_members(region, theme.strip())
        syms = [s for s in syms if s in members] if syms else members
        if not syms:
            syms = [NONE]                   # a theme with no listed companies matches nothing
    floor = None
    if lim["days"]:
        floor = (datetime.now(IST).date() - timedelta(days=lim["days"])).isoformat()
        frm_d = max(frm_d or floor, floor)
    _slow_down(str(profile.get("id") or ""))
    base = {"q": q, "region": region, "symbols": [s for s in syms if s != NONE], "theme": theme_name, "kinds": kinds, "sectors": sectors,
            "from": frm_d, "to": to_d, "floor": floor, "limits": lim, "note": NOTE, "covers": COVERS[region]}
    store = doc_store.store()
    if store is None:
        return {**base, "ready": False, "hits": [], "total": 0, "page": 1, "pages": 1, "more": False, "by_date": False, "locked": 0,
                "facets": {"kinds": {}, "years": {}}}
    found = store.search(q, region, syms or None, kinds or None, sectors or None, frm_d, to_d)
    best: dict[int, tuple] = {}
    for row in found["rows"]:                       # the rows come best first: the first passage of each document is its best
        best.setdefault(row[0], row)
    ordered = list(best.values())
    total = len(ordered)
    facets: dict = {"kinds": {}, "years": {}}
    if lim["hits"] is not None:
        shown, pages, page = ordered[: lim["hits"]], 1, 1
    else:
        pages = max(1, -(-total // size))
        page = min(max(1, int(page or 1)), pages)
        shown = ordered[(page - 1) * size: page * size]
    meta = store.documents([r[0] for r in (ordered if lim["filters"] else shown)])
    if lim["filters"]:
        for r in ordered:
            d = meta.get(r[0]) or {}
            if d.get("kind"):
                facets["kinds"][d["kind"]] = facets["kinds"].get(d["kind"], 0) + 1
            y = str(r[4] or "")[:4]
            if y:
                facets["years"][y] = facets["years"].get(y, 0) + 1
    heads = store.headlines(q, [(r[0], r[1]) for r in shown])
    hits = []
    for doc_id, n, page_no, rank, filed in shown:
        d = meta.get(doc_id)
        if not d:
            continue
        hits.append({"id": doc_id, "symbol": d["symbol"], "company": d.get("company") or d["symbol"], "region": str(d["region"]).strip(),
                     "sector": d.get("sector"), "kind": d["kind"], "kind_label": KIND_LABEL.get(d["kind"], d["kind"]),
                     "title": str(d.get("title") or KIND_LABEL.get(d["kind"], "Document"))[:200], "filed_at": d["filed_at"],
                     "page": page_no, "pages": d.get("pages"), "url": link_of(d, page_no), "source": source_of(d.get("host")),
                     "ocr": bool(d.get("ocr")), "snippet": snippet(heads.get((doc_id, n)))})
    return {**base, "ready": True, "hits": hits, "total": total, "page": page, "pages": pages, "more": len(found["rows"]) >= doc_store.QUERY_ROWS,
            "by_date": found["by_date"], "locked": max(0, total - len(hits)) if lim["hits"] is not None else 0, "facets": facets}


# ---------- routes ----------
_NOINDEX = {"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "private, no-store"}


@router.get("/research/docs/search")
def search(q: str = "", region: str = "IN", symbols: str = "", sector: str = "", theme: str = "", kind: str = "",
           frm: str = "", to: str = "", page: int = 1, profile=Depends(current_profile)):
    """Search inside the companies' filed documents. Signed-in only; the plan decides how many hits and which filters."""
    res = ok(run_search(profile, q, region, symbols, sector, theme, kind, frm, to, page))
    res.headers.update(_NOINDEX)
    return res


@router.get("/research/docs/status")
def search_status(profile=Depends(current_profile)):
    """What the index holds per market (documents, companies, the newest filing), the sectors to filter by, and the plan's
    limits, for the page's filters and its coverage line."""
    plan = plan_of(profile)
    store = doc_store.store()
    cov, sectors = {}, {}
    if store is not None:
        try:
            cov = store.coverage()
            sectors = store.sectors() if hasattr(store, "sectors") else {}
        except Exception as e:
            print("doc search status:", str(e)[:160])
    res = ok({"ready": store is not None, "coverage": cov, "sectors": sectors, "covers": COVERS, "kinds": {r: [{"id": k, "label": KIND_LABEL[k]} for k in ks]
                                                                                                     for r, ks in KINDS.items()},
              "limits": limits(plan), "note": NOTE})
    res.headers.update(_NOINDEX)
    return res


@router.get("/research/docs/export")
def search_export(q: str = "", region: str = "IN", symbols: str = "", sector: str = "", theme: str = "", kind: str = "",
                  frm: str = "", to: str = "", profile=Depends(current_profile)):
    """The hits as a CSV (company, document, date, page, the short extracts and the link; never the documents' text). Pro."""
    if not allows(plan_of(profile), "doc_search_all"):
        err(402, "upgrade_required", "Downloading the hits as a CSV is on the Pro plan.")
    rows = []
    for p in range(1, EXPORT_HITS // PAGE + 1):
        got = run_search(profile, q, region, symbols, sector, theme, kind, frm, to, p)
        rows += got["hits"]
        if p >= got["pages"]:
            break
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Company", "Symbol", "Market", "Document", "Kind", "Filed", "Page", "Extract", "Link"])
    for h in rows:
        w.writerow([h["company"], h["symbol"], h["region"], h["title"], h["kind_label"], h["filed_at"], h["page"] or "", plain(h["snippet"]), h["url"] or ""])
    name = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")[:40] or "search"
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={**_NOINDEX, "Content-Disposition": f'attachment; filename="stratlab-filings-{name}.csv"'})


# ---------- Admin: the nightly worker's switch and runs ----------
@admin_router.post("/admin/doc-index/on")
def doc_index_on(_=Depends(admin_profile)):
    doc_index.switch(True)
    return {"ok": True, "message": "The filings search index is on: it runs each night at 12:15 AM IST."}


@admin_router.post("/admin/doc-index/off")
def doc_index_off(_=Depends(admin_profile)):
    doc_index.switch(False)
    return {"ok": True, "message": "The filings search index is off: nothing more is read. What is stored stays searchable."}


@admin_router.post("/admin/doc-index/backfill")
def doc_index_backfill(_=Depends(admin_profile)):
    until = doc_index.start_backfill()
    doc_index.switch(True)
    return {"ok": True, "message": f"Backfill on until {until}: each night reads up to {doc_index.BACKFILL_CAP} documents."}


@admin_router.post("/admin/doc-index/backfill/stop")
def doc_index_backfill_stop(_=Depends(admin_profile)):
    doc_index.stop_backfill()
    return {"ok": True, "message": f"Backfill stopped: each night reads up to {doc_index.NIGHT_CAP} documents."}


@admin_router.post("/admin/doc-index/run")
def doc_index_run(_=Depends(admin_profile)):
    """A small run now (RUN_NOW_CAP documents, a few companies looked through), in the background."""
    if doc_store.store() is None:
        err(503, "not_set_up", "The filings search index needs the market database (MARKET_DATABASE_URL).")
    if doc_index.job.running:
        return {"ok": True, "message": "A run is already going."}
    threading.Thread(target=lambda: doc_index.job.run(doc_index.RUN_NOW_CAP, 5, max_s=20 * 60), daemon=True, name="doc-index-now").start()
    return {"ok": True, "message": f"Started: up to {doc_index.RUN_NOW_CAP} documents."}
