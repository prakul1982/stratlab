"""Search inside filings and call transcripts (app/doc_store.py, app/doc_index.py, app/doc_search.py): documents read into
passages with their page numbers, the nightly worker's caps and backoff, the search's filters and plan limits, and the
extracts: short, verbatim, escaped, linked to the filed copy, and never the document's text itself.

The store's own SQL (full-text search, phrases, ts_headline, cascades) runs against a local Postgres on port 55432
(MARKET_TEST_SERVER) when one is up, as CI has; everything else runs on tests/fake_doc_store.py."""
import io
import json
import os
import socket
from datetime import date, datetime, timedelta, timezone

import pytest

from app import db, doc_index, doc_search, doc_store, run_marks
from app.intel.net import SourceError
from tests import world as W
from tests.fake_doc_store import MemoryDocStore

IST = timezone(timedelta(hours=5, minutes=30))
SERVER = os.environ.get("MARKET_TEST_SERVER", "postgresql://postgres@127.0.0.1:55432")
PG = SERVER + "/docsearchtest"


# ---------- fixture documents ----------
def pdf(pages: list[list[str]], header: str | None = "ACME LIMITED EARNINGS CALL TRANSCRIPT", footer: bool = True) -> bytes:
    """A real PDF of `pages`, each a list of lines, with a running header and a page footer on every page."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for n, lines in enumerate(pages, start=1):
        y = 800
        if header:
            c.drawString(40, y, header)
            y -= 30
        for ln in lines:
            c.drawString(40, y, ln)
            y -= 16
        if footer:
            c.drawString(40, 30, f"Page {n} of {len(pages)}")
        c.showPage()
    c.save()
    return buf.getvalue()


def blank_pdf(n: int = 2) -> bytes:
    """A scan: pages with no text layer."""
    return pdf([[] for _ in range(n)], header=None, footer=False)


WORDS = ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel")


def fill(page: int, n: int = 30, about: str = "the discussion of operations went on") -> list[str]:
    """Lines of one page, each its own (a line on more than half the pages is a running header and is left out)."""
    return [f"In the {WORDS[page % 8]} {WORDS[k % 8]} part {k}, {about}." for k in range(n)]


THREE = [   # a call transcript's length (deepdive.readable takes a document from 2,500 characters: less is a cover letter)
    ["Moderator: Good morning and welcome to the call.", "Our capacity utilisation was 82 percent this quarter."] + fill(0),
    ["The order book stands at Rs 4,200 crore, up from last year.", "Margins improved on lower input costs."] + fill(1),
    ["We plan capex of Rs 600 crore for a new plant.", "Thank you all for joining."] + fill(2),
]


class FakeDocs:
    """docs.Docs's download and OCR, over a dict of files; a value that is an exception is raised."""

    def __init__(self, files: dict, ocr_text: str = ""):
        self.files, self.ocr_text, self.asked = files, ocr_text, []

    def _download(self, url, extra_hosts, limit):
        self.asked.append(url)
        got = self.files.get(url)
        if isinstance(got, Exception):
            raise got
        if got is None:
            raise SourceError("the exchange", "The document couldn't be downloaded (404).")
        return got

    def _ocr(self, data):
        return self.ocr_text


def reader(docs):
    slept = []
    r = doc_index.PageReader(docs, sleep=slept.append, clock=lambda: 0.0)
    r.slept = slept
    return r


NSE = "https://nsearchives.nseindia.com/corporate/"


# ---------- text into passages ----------
def test_passages_keep_their_page_and_drop_the_running_header_and_footer():
    pages = [f"ACME LIMITED Q2 FY27\n{body}\nPage {n} of 3" for n, body in enumerate(["first page words here and more",
                                                                                       "second page talks of the order book",
                                                                                       "third page plans capex"], start=1)]
    got = doc_index.chunk_pages(pages)
    assert [p for p, _ in got] == [1, 2, 3]
    assert all("ACME LIMITED" not in t and "Page" not in t for _, t in got)
    assert "order book" in got[1][1]


def test_a_long_paragraph_is_cut_into_passages_under_the_limit_and_never_across_pages():
    long = " ".join(f"Sentence number {i} says something about revenue." for i in range(200))
    got = doc_index.chunk_pages([long, "short second page with enough words"])
    assert all(len(t) <= doc_index.CHUNK_CHARS for _, t in got)
    assert {p for p, _ in got} == {1, 2} and got[-1] == (2, "short second page with enough words")
    assert sum(len(t) for p, t in got if p == 1) >= len(long) - 200       # nothing lost but the joins


def test_control_characters_never_reach_a_passage():
    got = doc_index.chunk_text("Revenue \x02grew\x03 by \x01 twenty\x00 percent in the year under review.")
    assert got and not any(ch in got[0][1] for ch in "\x00\x01\x02\x03")


def test_an_sec_filings_section_tags_are_not_text():
    got = doc_index.chunk_text("[BUSINESS]\nWe design chips for data centers and many other things.\n\n[RISKS]\nSupply may be short at times for us.")
    assert all("[BUSINESS]" not in t and "[RISKS]" not in t for _, t in got)


# ---------- reading a document (fixtures, no network) ----------
def test_a_three_page_pdf_becomes_passages_with_their_page_numbers():
    url = NSE + "ACME_transcript.pdf"
    r = reader(FakeDocs({url: pdf(THREE)}))
    meta, chunks = doc_index.read_india(r, {"kind": "transcript", "filed_at": "2026-10-20", "title": "Transcript", "url": url})
    assert meta["pages"] == 3 and meta["ocr"] is False and meta["link"] == url and meta["host"] == "nsearchives.nseindia.com"
    by_page: dict = {}
    for p, t in chunks:
        by_page[p] = by_page.get(p, "") + t
    assert "capacity utilisation" in by_page[1] and "order book" in by_page[2] and "capex" in by_page[3]
    assert not any("ACME LIMITED EARNINGS CALL" in t or "Page 2 of 3" in t for _, t in chunks)     # header and footer left out


def test_a_scanned_pdf_is_read_through_ocr_and_marked_so():
    url = NSE + "SCAN.pdf"
    words = "Management said the order book grew strongly. " * 80
    r = reader(FakeDocs({url: blank_pdf(2)}, ocr_text=words))
    meta, chunks = doc_index.read_india(r, {"kind": "transcript", "filed_at": "2026-10-20", "title": "Transcript", "url": url})
    assert meta["ocr"] is True and meta["pages"] is None and chunks and all(p is None for p, _ in chunks)


def test_a_cover_letter_is_followed_to_the_document_on_the_companys_site():
    letter_url, doc_url = NSE + "LETTER.pdf", "https://www.acme-example.com/investors/q2-transcript.pdf"
    letter = pdf([["Dear Sir, the transcript of the call is available at", doc_url]], header=None, footer=False)
    long = [fill(p, 40, "the order book was discussed at length") for p in range(3)]
    r = reader(FakeDocs({letter_url: letter, doc_url: pdf(long)}))
    meta, chunks = doc_index.read_india(r, {"kind": "transcript", "filed_at": "2026-10-20", "title": "Transcript", "url": letter_url})
    assert meta["link"] == doc_url and meta["host"] == "www.acme-example.com" and chunks


def test_the_exchange_is_asked_at_most_once_every_four_seconds():
    clock = [0.0]
    slept = []

    def sleep(s):
        slept.append(s)
        clock[0] += s
    url = NSE + "A.pdf"
    r = doc_index.PageReader(FakeDocs({url: pdf(THREE)}), sleep=sleep, clock=lambda: clock[0])
    r.text(url)
    clock[0] += 1.0
    r.text(url)
    assert slept and abs(slept[-1] - 3.0) < 1e-6


def test_a_document_off_the_allowed_hosts_is_never_downloaded():
    docs = FakeDocs({"https://evil.example/x.pdf": pdf(THREE)})
    with pytest.raises(SourceError):
        reader(docs).text("https://evil.example/x.pdf")
    assert docs.asked == []


# ---------- the nightly worker ----------
class FakeFilings:
    def __init__(self, items):
        self.items = items

    def announcements(self, symbol, days):
        return self.items.get(symbol, [])


def filing(sym, n, kind="Transcript of earnings call"):
    return {"url": f"{NSE}{sym}_{n}.pdf", "subject": kind, "text": "", "category": "concall", "at": f"2026-{10 - n % 9:02d}-{10 + n % 15}T10:00"}


@pytest.fixture
def mem(monkeypatch):
    s = MemoryDocStore()
    doc_store.use(s)
    monkeypatch.setattr(doc_index, "universe", lambda region: [{"symbol": "ACME", "company": "Acme Ltd", "sector": "Industrials", "cik": None},
                                                               {"symbol": "BETA", "company": "Beta Ltd", "sector": "Banks", "cik": None}] if region == "IN" else [])
    yield s
    doc_store.use(None)


@pytest.fixture
def kv(monkeypatch):
    from tests.fake_db import FakeSupabase
    monkeypatch.setattr(db, "_client", FakeSupabase())
    db.forget_mirror()


def job_with(monkeypatch, files, items, ocr=""):
    j = doc_index.Job()
    j.sleep = lambda s: None
    docs = FakeDocs(files, ocr)
    doc_index.setup(lambda: FakeFilings(items), lambda: None, lambda: docs)
    return j, docs


def test_the_worker_finds_new_documents_and_stops_at_its_cap(monkeypatch, mem, kv):
    items = {"ACME": [filing("ACME", i) for i in range(4)], "BETA": [filing("BETA", i) for i in range(3)]}
    files = {f["url"]: pdf(THREE) for fs in items.values() for f in fs}
    j, _ = job_with(monkeypatch, files, items)
    out = j.run(cap=5, discover=10)
    assert out["found"] == 7 and out["read"] == 5
    assert len(mem.docs) == 5 and mem.queue_stats()["waiting"] == 2
    again = j.run(cap=5, discover=10)                     # nothing found twice; the rest read
    assert again["found"] == 0 and again["read"] == 2 and len(mem.docs) == 7
    assert {d["symbol"] for d in mem.docs.values()} == {"ACME", "BETA"} and all(d["sector"] for d in mem.docs.values())


def test_a_refused_read_is_tried_later_and_five_refusals_in_a_row_pause_the_night(monkeypatch, mem, kv):
    items = {"ACME": [filing("ACME", i) for i in range(8)]}
    files = {f["url"]: SourceError("the exchange", "The document couldn't be downloaded (403).") for f in items["ACME"]}
    j, docs = job_with(monkeypatch, files, items)
    out = j.run(cap=50, discover=10)
    assert out["read"] == 0 and out["failed"] == doc_index.BREAK_AFTER and "Paused" in out["stopped"]
    tried = [q for q in mem.queue.values() if q["tries"]]
    assert len(tried) == doc_index.BREAK_AFTER and all(q["tries"] == 1 and q["next_at"] > datetime.now(timezone.utc) + timedelta(hours=5) for q in tried)
    assert mem.due(100) and len(mem.due(100)) == 8 - doc_index.BREAK_AFTER     # the refused ones wait their backoff


def test_a_filing_with_no_readable_document_is_left_as_failed(monkeypatch, mem, kv):
    items = {"ACME": [filing("ACME", 1)]}
    j, _ = job_with(monkeypatch, {items["ACME"][0]["url"]: b"<html>not a pdf</html>"}, items)
    out = j.run(cap=5, discover=5)
    assert out["failed"] == 1 and mem.queue_stats()["failed"] == 1 and not mem.due(5)


def test_the_run_stops_at_its_time_limit(monkeypatch, mem, kv):
    items = {"ACME": [filing("ACME", i) for i in range(5)]}
    j, _ = job_with(monkeypatch, {f["url"]: pdf(THREE) for f in items["ACME"]}, items)
    t = [0.0]

    def clock():
        t[0] += 30
        return t[0]
    j.clock = clock
    out = j.run(cap=50, discover=5, max_s=100)
    assert out["read"] < 5 and out["stopped"] == "Stopped at the run's time limit."


def test_the_nightly_run_is_off_by_default_runs_once_a_night_when_on_and_never_in_the_day(monkeypatch, mem, kv):
    items = {"ACME": [filing("ACME", 1)]}
    j, _ = job_with(monkeypatch, {items["ACME"][0]["url"]: pdf(THREE)}, items)
    night = datetime(2026, 11, 13, 0, 20, tzinfo=IST)
    assert j.tick(night) is None and not mem.docs                     # off by default
    doc_index.switch(True)
    assert j.tick(datetime(2026, 11, 13, 14, 0, tzinfo=IST)) is None    # in the day: never
    out = j.tick(night)
    assert out["ok"] and len(mem.docs) == 1
    assert run_marks.status(doc_index.RUN_KEY, "2026-11-13") == "done"
    assert j.tick(night + timedelta(minutes=5)) is None                 # once a night
    doc_index.switch(False)
    assert not doc_index.enabled()


def test_a_backfill_raises_the_nights_caps_until_its_date(monkeypatch, mem, kv):
    seen = {}
    j = doc_index.Job()
    monkeypatch.setattr(j, "run", lambda cap, discover, beat=None, max_s=0: seen.update(cap=cap, discover=discover) or {"ok": True})
    doc_index.switch(True)
    j.tick(datetime(2026, 11, 13, 0, 20, tzinfo=IST))
    assert seen == {"cap": doc_index.NIGHT_CAP, "discover": doc_index.DISCOVER}
    doc_index.start_backfill()
    db.delete_setting(doc_index.RUN_KEY)
    j.tick(datetime(2026, 11, 13, 0, 20, tzinfo=IST))
    assert seen == {"cap": doc_index.BACKFILL_CAP, "discover": doc_index.DISCOVER_BACKFILL}


class FakeSEC:
    class Cache(dict):
        def pop(self, k, default=None):
            self.popped = getattr(self, "popped", []) + [k]
            return super().pop(k, default)

    def __init__(self):
        self.cache = self.Cache()

    def submissions(self, cik):
        today = date.today()
        return {"cik": cik, "filings": {"recent": {
            "form": ["8-K", "10-K", "8-K", "4"], "filingDate": [(today - timedelta(days=d)).isoformat() for d in (10, 40, 50, 60)],
            "accessionNumber": ["0001-26-1", "0001-26-2", "0001-26-3", "0001-26-4"], "primaryDocument": ["a.htm", "k.htm", "b.htm", "f.xml"],
            "items": ["2.02,9.01", "", "5.02", ""]}}}

    def annual(self, d):
        self.cache[("doc", d["url"])] = "x"
        return "[BUSINESS]\nWe design accelerators for data centers.\n\n" + "Our supply chain depends on a few foundries. " * 40

    def release_doc(self, d):
        link = d["folder"] + "ex99.htm"
        self.cache[("doc", link)] = "x"
        return link, "Revenue was $10 billion, up 20 percent from a year ago. " * 30


def test_us_filings_annual_reports_and_earnings_releases_are_read_and_dropped_from_the_sec_cache(monkeypatch, mem, kv):
    monkeypatch.setattr(doc_index, "universe", lambda region: [{"symbol": "NVX", "company": "NVX Corp", "sector": "Technology", "cik": 123}] if region == "US" else [])
    sec = FakeSEC()
    j = doc_index.Job()
    j.sleep = lambda s: None
    doc_index.setup(lambda: None, lambda: sec, lambda: None)
    out = j.run(cap=10, discover=5)
    kinds = sorted(d["kind"] for d in mem.docs.values())
    assert kinds == ["annual_report", "earnings_release"] and out["read"] == 2         # the 8-K of item 5.02 and the Form 4 aren't documents to index
    rel = next(d for d in mem.docs.values() if d["kind"] == "earnings_release")
    assert rel["link"].endswith("/ex99.htm") and rel["host"] == "www.sec.gov"
    assert not sec.cache and len(sec.cache.popped) >= 2                                # the text isn't kept in the server


def test_reading_a_hundred_documents_keeps_the_servers_memory_flat(monkeypatch, mem, kv):
    from app import memguard
    items = {"ACME": [filing("ACME", i) | {"url": f"{NSE}M{i}.pdf"} for i in range(100)]}
    body = pdf([fill(p, 40, "capacity utilisation and the order book were discussed") for p in range(5)])
    j, _ = job_with(monkeypatch, {f["url"]: body for f in items["ACME"]}, items)
    mem.chunks_kept = False
    monkeypatch.setattr(mem, "save", lambda doc, chunks: mem.queue.pop(doc["url"], None) and 1)    # nothing kept by the test's own store
    before = memguard.rss_mb() or 0
    out = j.run(cap=100, discover=5)
    after = memguard.rss_mb() or 0
    assert out["read"] == 100
    assert after - before < 50


# ---------- the extracts ----------
def test_an_extract_is_escaped_before_its_marks_are_added():
    got = doc_search.snippet("<script>alert('x')</script> the \x02order\x03 \x02book\x03 grew & so did <b>margins</b>")
    assert got == ["&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; the <mark>order</mark> <mark>book</mark> grew &amp; so did "
                   "&lt;b&gt;margins&lt;/b&gt;"]


def test_an_extract_holds_at_most_two_fragments_of_thirty_five_words():
    frag = " ".join(f"w{i}" for i in range(60)) + " \x02hit\x03"
    got = doc_search.snippet("\x01".join([frag, frag, frag]))
    assert len(got) == 2
    for f in got:
        assert len(f.replace("…", "").split()) <= doc_search.SNIPPET_WORDS and f.endswith("…")


def test_an_extract_never_runs_past_its_character_limit_and_a_cut_mark_is_closed():
    got = doc_search.snippet("\x02" + " ".join(["supercalifragilisticexpialidocious"] * 30) + "\x03")
    import re
    text = re.sub(r"</?mark>", "", got[0]).rstrip("…")
    assert len(text) <= doc_search.SNIPPET_CHARS and got[0].count("<mark>") == got[0].count("</mark>") == 1


def test_a_hit_links_to_the_filed_copy_at_its_page():
    assert doc_search.link_of({"link": NSE + "a.pdf"}, 4) == NSE + "a.pdf#page=4"
    assert doc_search.link_of({"link": "https://www.sec.gov/Archives/x/ex99.htm"}, None) == "https://www.sec.gov/Archives/x/ex99.htm"
    assert doc_search.link_of({"link": "javascript:alert(1)"}, 2) is None
    assert doc_search.source_of("nsearchives.nseindia.com") == "NSE" and doc_search.source_of("www.sec.gov") == "SEC"


# ---------- the routes and the plans ----------
@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    s = MemoryDocStore()
    today = datetime.now(IST).date()
    for i in range(30):                                  # 30 documents that mention the order book, one a fortnight back (27 in the last year)
        filed = (today - timedelta(days=14 * i)).isoformat()
        s.save({"url": f"{NSE}T{i}.pdf", "link": f"{NSE}T{i}.pdf", "host": "nsearchives.nseindia.com", "region": "IN",
                "symbol": "ACME" if i % 2 else "BETA", "company": "Acme Ltd" if i % 2 else "Beta Ltd", "sector": "Industrials" if i % 2 else "Banks",
                "kind": "transcript" if i % 3 else "presentation", "title": f"Transcript {i}", "filed_at": filed, "pages": 3},
               [(1, "Opening remarks by the moderator about the agenda."),
                (2, f"<script>alert({i})</script> Our order book stands at Rs {4000 + i} crore. " + "More detail follows here. " * 70)])
    doc_store.use(s)
    world["store"] = s
    yield world
    doc_store.use(None)
    world["close"]()


def get(w, token, path):
    return w["client"].get(path, headers=W.headers(token) if token else {})


def test_a_visitor_gets_nothing(w):
    r = get(w, None, "/research/docs/search?q=order%20book")
    assert r.status_code == 401
    assert get(w, None, "/research/docs/status").status_code == 401


def test_free_sees_the_first_three_hits_of_the_last_year_and_filters_by_company_only(w):
    r = get(w, "free-token", "/research/docs/search?q=order%20book")
    assert r.status_code == 200, r.text
    d = r.json()
    year_ago = (datetime.now(IST).date() - timedelta(days=365)).isoformat()
    assert len(d["hits"]) == 3 and d["limits"]["hits"] == 3 and d["limits"]["filters"] is False
    assert d["floor"] == year_ago and all(h["filed_at"] >= year_ago for h in d["hits"])
    assert d["total"] == 27
    assert d["locked"] == d["total"] - 3 and d["pages"] == 1
    assert r.headers["x-robots-tag"].startswith("noindex")
    assert get(w, "free-token", "/research/docs/search?q=order%20book&symbols=ACME").json()["symbols"] == ["ACME"]
    for extra in ("sector=Banks", "kind=transcript", "frm=2026-01-01", "theme=defence"):
        bad = get(w, "free-token", f"/research/docs/search?q=order%20book&{extra}")
        assert bad.status_code == 402 and bad.json()["detail"]["plan"] == "basic", extra


def test_basic_sees_every_hit_of_the_last_year_with_every_filter_and_pages(w):
    d = get(w, "basic-token", "/research/docs/search?q=order%20book").json()
    assert d["limits"] == {"hits": None, "days": 365, "filters": True, "export": False}
    assert d["total"] == 27 and d["pages"] == 2 and len(d["hits"]) == 20
    assert sum(d["facets"]["kinds"].values()) == d["total"]
    p2 = get(w, "basic-token", "/research/docs/search?q=order%20book&page=2").json()
    assert p2["page"] == 2 and len(p2["hits"]) == d["total"] - 20
    assert not {h["id"] for h in d["hits"]} & {h["id"] for h in p2["hits"]}
    only = get(w, "basic-token", "/research/docs/search?q=order%20book&sector=Banks&kind=presentation").json()
    assert only["hits"] and all(h["sector"] == "Banks" and h["kind"] == "presentation" for h in only["hits"])
    assert get(w, "basic-token", "/research/docs/export?q=order%20book").status_code == 402


def test_pro_searches_every_year_and_downloads_the_hits(w):
    d = get(w, "pro-token", "/research/docs/search?q=order%20book").json()
    assert d["floor"] is None and d["total"] == 30
    r = get(w, "pro-token", "/research/docs/export?q=order%20book")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("Company,Symbol") and len(lines) == 31
    assert "<mark>" not in r.text and "More detail follows here. " * 12 not in r.text      # extracts only


def test_a_theme_filter_keeps_its_stored_companies(w, monkeypatch):
    from app.intel import theme_library
    monkeypatch.setattr(theme_library, "stored", lambda region, q: {"name": "defence", "payload": {
        "value_chain": [{"layer": "Shipyards", "companies": [{"ticker": "ACME"}]}], "sub_themes": []}} if q == "defence" else None)
    d = get(w, "pro-token", "/research/docs/search?q=order%20book&theme=defence").json()
    assert d["theme"] == "defence" and d["hits"] and {h["symbol"] for h in d["hits"]} == {"ACME"}
    assert get(w, "pro-token", "/research/docs/search?q=order%20book&theme=nothing").status_code == 404


def test_no_route_returns_a_documents_text_and_every_extract_is_short_and_escaped(w):
    d = get(w, "pro-token", "/research/docs/search?q=order%20book").json()
    text = json.dumps(d)
    assert "More detail follows here. " * 8 not in text                    # the passage itself is never sent
    assert "<script>" not in text and "Opening remarks" not in text
    for h in d["hits"]:
        assert 1 <= len(h["snippet"]) <= 2 and "<mark>order</mark>" in h["snippet"][0]
        assert all(len(f.replace("…", "").split()) <= 35 for f in h["snippet"])
        assert h["url"].startswith(NSE) and h["url"].endswith("#page=2") and h["source"] == "NSE"
    s = get(w, "pro-token", "/research/docs/status").json()
    assert s["coverage"]["IN"]["documents"] == 30 and s["sectors"]["IN"] == ["Banks", "Industrials"]


def test_a_query_with_no_words_is_refused_plainly(w):
    r = get(w, "basic-token", "/research/docs/search?q=%20%22%20")
    assert r.status_code == 400 and "Type a word" in r.json()["detail"]["message"]


def test_the_search_says_so_when_the_index_isnt_set_up(w):
    doc_store.use(None)
    d = get(w, "basic-token", "/research/docs/search?q=order").json()
    assert d["ready"] is False and d["hits"] == []


def test_admin_can_switch_the_worker_on_and_off_and_sees_it_in_the_job_list(w):
    h = W.headers("admin-token")
    assert w["client"].post("/admin/doc-index/on", headers=h).json()["ok"]
    assert doc_index.enabled()
    rows = w["client"].get("/admin/jobs", headers=h).json()["jobs"]
    row = next(r for r in rows if r["id"] == "doc-index")
    assert row["name"] == "Filings search index" and "12:15 AM IST" in row["schedule"] and row["next"]
    assert [r["label"] for r in row["run"]][:2] == ["Run now", "Turn off"]
    assert any("India: 30 documents of 2 companies" in x for x in row["log"])
    w["client"].post("/admin/doc-index/off", headers=h)
    assert not doc_index.enabled()
    assert w["client"].post("/admin/doc-index/on", headers=W.headers("pro-token")).status_code in (401, 403)


# ---------- the store itself, on Postgres ----------
def _pg_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 55432), timeout=0.3).close()
        return True
    except OSError:
        return False


needs_pg = pytest.mark.skipif(not _pg_up(), reason="needs a local Postgres on port 55432 (MARKET_TEST_SERVER)")


@pytest.fixture
def pg():
    import psycopg
    from app import market_store
    with psycopg.connect(SERVER + "/postgres", autocommit=True) as c:
        try:
            c.execute("create database docsearchtest")
        except (psycopg.errors.DuplicateDatabase, psycopg.errors.UniqueViolation):
            pass
    lock = psycopg.connect(PG, autocommit=True)
    lock.execute("select pg_advisory_lock(4343)")
    lock.execute("drop table if exists doc_chunks, doc_documents, doc_queue cascade")
    m = market_store.Store(PG)
    s = doc_store.DocStore(m)
    try:
        yield s
    finally:
        if m._pool is not None:
            m._pool.close()
        lock.execute("select pg_advisory_unlock(4343)")
        lock.close()


def put(s, n, symbol="ACME", kind="transcript", filed="2026-10-01", sector="Industrials", region="IN", pages=None):
    pages = pages or [(1, "Opening words.")]
    return s.save({"url": f"{NSE}{symbol}{n}.pdf", "region": region, "symbol": symbol, "company": symbol.title(), "sector": sector, "kind": kind,
                   "title": f"Doc {n}", "filed_at": filed, "host": "nsearchives.nseindia.com", "pages": len(pages)}, pages)


@needs_pg
def test_the_tables_are_made_once_and_making_them_again_changes_nothing(pg):
    pg.ensure()
    put(pg, 1)
    again = doc_store.DocStore(pg.market)
    again.ensure()
    assert again.coverage()["IN"]["documents"] == 1


@needs_pg
def test_postgres_search_phrases_exclusions_and_filters(pg):
    a = put(pg, 1, pages=[(1, "Intro."), (2, "Our order book is Rs 4,000 crore and capacity utilisation was 80 percent.")])
    put(pg, 2, symbol="BETA", kind="presentation", sector="Banks",
        pages=[(1, "The order was placed early. Our long and strong book of loans grew.")])
    put(pg, 3, filed="2024-05-01", pages=[(3, "The order book shrank in that year, with weak capacity utilisation.")])
    put(pg, 4, region="US", symbol="NVX", kind="annual_report", pages=[(None, "Our order book of chips grew.")])
    hit = lambda **kw: {r[0] for r in pg.search(**kw)["rows"]}  # noqa: E731
    assert hit(q='"order book"', region="IN") == {a, a + 2}                          # the far-apart words don't match the phrase
    assert hit(q="order book", region="IN") == {a, a + 1, a + 2}
    assert hit(q='"order book" -shrank', region="IN") == {a}
    assert hit(q="order book", region="IN", symbols=["BETA"]) == {a + 1}
    assert hit(q="order book", region="IN", kinds=["presentation"]) == {a + 1}
    assert hit(q="order book", region="IN", sectors=["Industrials"]) == {a, a + 2}
    assert hit(q="order book", region="IN", frm="2025-01-01") == {a, a + 1}
    assert hit(q="order book", region="IN", to="2025-01-01") == {a + 2}
    assert hit(q="order book", region="US") == {a + 3}
    rows = pg.search(q='"order book"', region="IN")["rows"]
    assert rows[0][2] == 2 or rows[0][2] == 3                                       # the passage's page comes back with it


@needs_pg
def test_postgres_extracts_mark_both_words_and_render_a_documents_markup_inert(pg):
    i = put(pg, 1, pages=[(5, "<script>alert(1)</script> In the quarter our capacity utilisation reached 82 percent, up from 75. " + "Filler words. " * 300)])
    raw = pg.headlines("capacity utilisation", [(i, 0)])[(i, 0)]
    got = doc_search.snippet(raw)
    assert got and "<mark>capacity</mark>" in got[0] and "<mark>utilisation</mark>" in got[0]
    assert "<script>" not in "".join(got) and len(got) <= 2
    import re
    assert all(len(re.sub(r"</?mark>", "", f).rstrip("…")) <= doc_search.SNIPPET_CHARS for f in got)


@needs_pg
def test_postgres_cascades_and_never_queues_or_stores_a_document_twice(pg):
    i = put(pg, 1, pages=[(1, "Order book words."), (2, "More order book words.")])
    row = {"url": f"{NSE}ACME1.pdf", "region": "IN", "symbol": "ACME", "kind": "transcript", "filed_at": "2026-10-01", "title": "x"}
    assert pg.enqueue([row]) == 0                                   # already stored
    new = {**row, "url": f"{NSE}ACME9.pdf"}
    assert pg.enqueue([new, new]) == 1 and pg.enqueue([new]) == 0     # queued once
    put(pg, 1, pages=[(1, "Read again: order book words.")])          # read again: replaces, never a second copy
    assert pg.coverage()["IN"]["documents"] == 1
    j = pg.search(q="order", region="IN")["rows"][0][0]
    pg.delete(j)
    assert pg.search(q="order", region="IN")["rows"] == []
    with pg.market.pool().connection() as c:
        assert c.execute("select count(*) from doc_chunks").fetchone()[0] == 0
    assert i != j
    due = pg.due(10)
    assert [d["url"] for d in due] == [new["url"]]
    pg.retry(new["url"], "refused", 3600)
    assert pg.due(10) == [] and pg.queue_stats()["waiting"] == 1
    pg.retry(new["url"], "no document", 0, give_up=True)
    assert pg.queue_stats()["failed"] == 1


@needs_pg
def test_postgres_a_very_common_word_is_ordered_by_date(pg, monkeypatch):
    put(pg, 1, filed="2026-01-01", pages=[(1, "revenue revenue revenue revenue")])
    put(pg, 2, filed="2026-06-01", pages=[(1, "revenue once")])
    monkeypatch.setattr(doc_store, "COMMON", 0)
    got = pg.search(q="revenue", region="IN")
    assert got["by_date"] and [r[4] for r in got["rows"]] == ["2026-06-01", "2026-01-01"]


@needs_pg
def test_postgres_the_route_returns_extracts_only(pg, monkeypatch):
    world = W.build(monkeypatch)
    try:
        body = "Our capacity utilisation was 82 percent. " + " ".join(f"Sentence {k} adds detail about plants." for k in range(60))
        put(pg, 1, filed=datetime.now(IST).date().isoformat(), pages=[(2, body)])
        doc_store.use(pg)
        d = world["client"].get("/research/docs/search?q=capacity%20utilisation", headers=W.headers("basic-token")).json()
        assert d["total"] == 1 and d["hits"][0]["page"] == 2 and d["hits"][0]["url"].endswith("#page=2")
        assert body[:400] not in json.dumps(d) and "<mark>capacity</mark>" in d["hits"][0]["snippet"][0]
    finally:
        doc_store.use(None)
        world["close"]()
