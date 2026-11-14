"""The search index of companies' documents (call transcripts, investor presentations, annual reports' main parts and
earnings releases): Postgres full-text search in the market database (market_store, MARKET_DATABASE_URL).

Nothing is held in this process: the text and its index live in Postgres (`tsvector` + GIN), the pages ask for at most
QUERY_ROWS matching passages at a time and only the shown page's short snippets are built (ts_headline). The full text
is kept only to find and quote short passages: no route returns it (doc_search.py), and every hit links to the
exchange's, the company's or the SEC's own copy of the document.

Tables (created on first use, idempotently, like market_store.SCHEMA):
- doc_documents: one row per document read (its filing address is unique, so a document is never stored twice).
- doc_chunks: the document's text in passages of up to about 2,000 characters, page by page, with the filters copied on
  so a search needs no join; `tsv` is a stored tsvector with a GIN index.
- doc_queue: documents found in the filings and waiting to be read by the nightly worker (doc_index.py), with retries.
"""
from __future__ import annotations

import threading
from datetime import date, datetime

SCHEMA = (
    """create table if not exists doc_documents (
      id bigserial primary key,
      region char(2) not null, symbol text not null, company text, sector text,
      kind text not null, title text, filed_at date not null,
      url text not null unique, link text, host text,
      pages int, chars int, chunks int, sha1 text, ocr boolean not null default false,
      indexed_at timestamptz not null default now())""",
    "create index if not exists doc_documents_co on doc_documents (region, symbol, filed_at desc)",
    """create table if not exists doc_chunks (
      doc_id bigint not null references doc_documents (id) on delete cascade,
      n int not null, page int,
      region char(2) not null, symbol text not null, sector text, kind text not null, filed_at date not null,
      body text not null,
      tsv tsvector generated always as (to_tsvector('english', body)) stored,
      primary key (doc_id, n))""",
    "create index if not exists doc_chunks_tsv on doc_chunks using gin (tsv)",
    "create index if not exists doc_chunks_co on doc_chunks (region, symbol, filed_at desc)",
    """create table if not exists doc_queue (
      url text primary key,
      region char(2) not null, symbol text not null, kind text not null, filed_at date not null,
      title text, company text, sector text,
      tries int not null default 0, next_at timestamptz not null default now(), last_error text,
      added_at timestamptz not null default now())""",
    "create index if not exists doc_queue_next on doc_queue (next_at, filed_at desc)",
)
# lz4 squeezes the long passages better and faster than the default (Postgres 14 and up, built with lz4): tried, and left
# as it is where the server can't
OPTIONAL = ("alter table doc_chunks alter column body set compression lz4",)

QUERY_ROWS = 400          # matching passages one search reads at most (the best per document is kept, then a page shown)
COMMON = 50_000           # a query the planner expects to match more passages than this is ordered by date, not rank
TIMEOUT_MS = 3000         # a search never holds the database longer than this
MAX_TRIES = 4             # a document that failed this many times is left as failed (Admin lists them)
HEADLINE = ("MaxFragments=2, MaxWords=35, MinWords=12, ShortWord=3, FragmentDelimiter=\x01, "
            "StartSel=\x02, StopSel=\x03, HighlightAll=false")

DOC_COLS = ("id", "region", "symbol", "company", "sector", "kind", "title", "filed_at", "url", "link", "host", "pages", "chars",
            "chunks", "ocr", "indexed_at")
QUEUE_COLS = ("url", "region", "symbol", "kind", "filed_at", "title", "company", "sector")


def _iso(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if isinstance(v, (date, datetime)) else str(v)


class DocStore:
    """The tables above, through the market database's own small pool (market_store.Store)."""

    def __init__(self, market):
        self.market = market
        self._ready = False
        self._lock = threading.Lock()

    # ---- setup
    def ensure(self) -> None:
        """Create the tables and indexes once per process (each statement is `if not exists`, so a second server, or a
        restart, changes nothing)."""
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            with self.market.pool().connection() as c:
                for sql in SCHEMA:
                    c.execute(sql)
                for sql in OPTIONAL:
                    try:
                        c.execute(sql)
                    except Exception as e:          # an older server or one built without lz4: the default compression
                        print("doc store:", str(e)[:120])
            self._ready = True

    def _conn(self):
        self.ensure()
        return self.market.pool().connection()

    # ---- the queue
    def enqueue(self, rows: list[dict]) -> int:
        """Add documents to read; one already queued or already stored is left alone. Returns how many were added."""
        if not rows:
            return 0
        added = 0
        with self._conn() as c, c.transaction():
            for r in rows:
                cur = c.execute(
                    "insert into doc_queue (url, region, symbol, kind, filed_at, title, company, sector) "
                    "select %s, %s, %s, %s, %s, %s, %s, %s where not exists (select 1 from doc_documents where url = %s) "
                    "on conflict (url) do nothing returning url",
                    (*(r.get(k) for k in QUEUE_COLS), r["url"]))
                added += len(cur.fetchall())
        return added

    def due(self, limit: int) -> list[dict]:
        """Documents to read now, newest filing first."""
        with self._conn() as c:
            rows = c.execute(f"select {', '.join(QUEUE_COLS)}, tries from doc_queue where next_at <= now() and tries < %s "
                             "order by filed_at desc, url limit %s", (MAX_TRIES, limit)).fetchall()
        return [{**dict(zip(QUEUE_COLS + ("tries",), r)), "filed_at": _iso(r[4])} for r in rows]

    def retry(self, url: str, error: str, delay_s: float, give_up: bool = False) -> None:
        """A read that failed: tried again after `delay_s`, or left as failed (`give_up`, or after MAX_TRIES)."""
        with self._conn() as c:
            c.execute("update doc_queue set tries = case when %s then %s else tries + 1 end, last_error = %s, "
                      "next_at = now() + make_interval(secs => %s) where url = %s",
                      (give_up, MAX_TRIES, error[:300], float(delay_s), url))

    def save(self, doc: dict, chunks: list[tuple[int | None, str]]) -> int:
        """Store one document and its passages in one transaction (a document read again replaces its old rows), and take
        it off the queue. `chunks`: [(page or None, text)]. Returns the document's id."""
        with self._conn() as c, c.transaction():
            c.execute("delete from doc_documents where url = %s", (doc["url"],))
            doc_id = c.execute(
                "insert into doc_documents (region, symbol, company, sector, kind, title, filed_at, url, link, host, pages, chars, "
                "chunks, sha1, ocr) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
                (doc["region"], doc["symbol"], doc.get("company"), doc.get("sector"), doc["kind"], doc.get("title"), doc["filed_at"],
                 doc["url"], doc.get("link") or doc["url"], doc.get("host"), doc.get("pages"), sum(len(t) for _, t in chunks),
                 len(chunks), doc.get("sha1"), bool(doc.get("ocr")))).fetchone()[0]
            with c.cursor() as cur:
                cur.executemany(
                    "insert into doc_chunks (doc_id, n, page, region, symbol, sector, kind, filed_at, body) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [(doc_id, n, page, doc["region"], doc["symbol"], doc.get("sector"), doc["kind"], doc["filed_at"], text)
                     for n, (page, text) in enumerate(chunks)])
            c.execute("delete from doc_queue where url = %s", (doc["url"],))
        return int(doc_id)

    def delete(self, doc_id: int) -> None:
        with self._conn() as c:
            c.execute("delete from doc_documents where id = %s", (doc_id,))

    def stored_urls(self, urls: list[str]) -> set[str]:
        if not urls:
            return set()
        with self._conn() as c:
            return {r[0] for r in c.execute("select url from doc_documents where url = any(%s) union "
                                            "select url from doc_queue where url = any(%s)", (urls, urls)).fetchall()}

    # ---- searching
    def search(self, q: str, region: str, symbols: list[str] | None = None, kinds: list[str] | None = None,
               sectors: list[str] | None = None, frm: str | None = None, to: str | None = None, limit: int = QUERY_ROWS) -> dict:
        """The best-matching passages: {"rows": [(doc_id, n, page, rank, filed_at ISO)], "by_date": the query matches so much
        that it was ordered by date (newest first) instead of by rank}. One statement, at most TIMEOUT_MS."""
        where, args = ["c.tsv @@ q.tq", "c.region = %(region)s"], {"q": q, "region": region, "limit": limit}
        if symbols:
            where.append("c.symbol = any(%(symbols)s)")
            args["symbols"] = list(symbols)
        if kinds:
            where.append("c.kind = any(%(kinds)s)")
            args["kinds"] = list(kinds)
        if sectors:
            where.append("c.sector = any(%(sectors)s)")
            args["sectors"] = list(sectors)
        if frm:
            where.append("c.filed_at >= %(frm)s")
            args["frm"] = frm
        if to:
            where.append("c.filed_at <= %(to)s")
            args["to"] = to
        body = f"from doc_chunks c, (select websearch_to_tsquery('english', %(q)s) tq) q where {' and '.join(where)}"
        with self._conn() as c, c.transaction():
            c.execute(f"set local statement_timeout = {int(TIMEOUT_MS)}")
            plan = c.execute(f"explain (format json) select 1 {body}", args).fetchone()[0]
            estimate = _plan_rows(plan)
            by_date = estimate > COMMON
            order = "c.filed_at desc, c.doc_id desc, c.n" if by_date else "r desc, c.filed_at desc, c.doc_id desc, c.n"
            rank = "0.0" if by_date else "ts_rank_cd(c.tsv, q.tq)"
            rows = c.execute(f"select c.doc_id, c.n, c.page, {rank} r, c.filed_at {body} order by {order} limit %(limit)s", args).fetchall()
        return {"rows": [(int(d), int(n), p, float(r), _iso(f)) for d, n, p, r, f in rows], "by_date": by_date}

    def headlines(self, q: str, keys: list[tuple[int, int]]) -> dict[tuple[int, int], str]:
        """Each passage's short extract around the match (ts_headline: at most 2 fragments of up to 35 words, the matched
        words between \\x02 and \\x03, fragments split by \\x01), for the passages of one shown page only."""
        if not keys:
            return {}
        ids, ns = [k[0] for k in keys], [k[1] for k in keys]
        with self._conn() as c, c.transaction():
            c.execute(f"set local statement_timeout = {int(TIMEOUT_MS)}")
            rows = c.execute(
                "select c.doc_id, c.n, ts_headline('english', c.body, websearch_to_tsquery('english', %s), %s) "
                "from doc_chunks c join unnest(%s::bigint[], %s::int[]) k(d, n) on c.doc_id = k.d and c.n = k.n",
                (q, HEADLINE, ids, ns)).fetchall()
        return {(int(d), int(n)): h for d, n, h in rows}

    def covers(self, max_chars: int, limit: int, skip: list[str] | None = None) -> list[dict]:
        """m53: stored US earnings releases whose text is only the 8-K's cover (the filing itself read, under `max_chars` characters, the
        release exhibit not found by its name), newest first, at most `limit`, those in `skip` (already read again) left out."""
        with self._conn() as c:
            rows = c.execute(f"select {', '.join(QUEUE_COLS)} from doc_documents where region = 'US' and kind = 'earnings_release' "
                             "and link = url and chars < %s and not (url = any(%s)) order by filed_at desc, url limit %s",
                             (int(max_chars), list(skip or []), int(limit))).fetchall()
        return [{**dict(zip(QUEUE_COLS, r)), "filed_at": _iso(r[4])} for r in rows]

    def passages(self, q: str, region: str, symbols: list[str], kinds: list[str], since: str, limit: int) -> list[dict]:
        """m53 (sector_ops): the matching passages' own text, for a theme's operating measures read from the companies' documents: the
        companies' passages filed since `since`, newest document first and in page order, at most `limit`, one statement of at most
        TIMEOUT_MS. Never served to a page (sector_ops keeps only each figure with its short quote and link)."""
        if not symbols:
            return []
        with self._conn() as c, c.transaction():
            c.execute(f"set local statement_timeout = {int(TIMEOUT_MS)}")
            rows = c.execute(
                "select c.symbol, c.doc_id, c.n, c.page, c.kind, c.filed_at, c.body, d.link, d.title "
                "from doc_chunks c join doc_documents d on d.id = c.doc_id, (select websearch_to_tsquery('english', %(q)s) tq) q "
                "where c.tsv @@ q.tq and c.region = %(region)s and c.symbol = any(%(symbols)s) and c.kind = any(%(kinds)s) "
                "and c.filed_at >= %(since)s order by c.symbol, c.filed_at desc, c.doc_id desc, c.n limit %(limit)s",
                {"q": q, "region": region, "symbols": list(symbols), "kinds": list(kinds), "since": since, "limit": int(limit)}).fetchall()
        return [{"symbol": s, "doc_id": int(d), "n": int(n), "page": p, "kind": k, "filed_at": _iso(f), "body": b, "link": ln, "title": ti}
                for s, d, n, p, k, f, b, ln, ti in rows]

    def documents(self, ids: list[int]) -> dict[int, dict]:
        """The documents' details (never their text)."""
        if not ids:
            return {}
        with self._conn() as c:
            rows = c.execute(f"select {', '.join(DOC_COLS)} from doc_documents where id = any(%s)", (list(ids),)).fetchall()
        out = {}
        for r in rows:
            d = dict(zip(DOC_COLS, r))
            d["filed_at"], d["indexed_at"] = _iso(d["filed_at"]), _iso(d["indexed_at"])
            out[int(d["id"])] = d
        return out

    # ---- what is held
    def coverage(self) -> dict:
        """Per market: documents, companies, the newest filing and the oldest, and documents by kind."""
        with self._conn() as c:
            rows = c.execute("select region, kind, count(*), count(distinct symbol), max(filed_at), min(filed_at) "
                             "from doc_documents group by region, kind").fetchall()
            cos = dict(c.execute("select region, count(distinct symbol) from doc_documents group by region").fetchall())
        out: dict = {}
        for region, kind, n, _cos, newest, oldest in rows:
            reg = out.setdefault(region.strip(), {"documents": 0, "companies": int(cos.get(region, 0)), "newest": None, "oldest": None, "kinds": {}})
            reg["documents"] += int(n)
            reg["kinds"][kind] = int(n)
            reg["newest"] = max(filter(None, [reg["newest"], _iso(newest)]), default=None)
            reg["oldest"] = min(filter(None, [reg["oldest"], _iso(oldest)]), default=None)
        return out

    def sectors(self) -> dict[str, list[str]]:
        """{market: the sectors of the companies stored, by name}, for the sector filter."""
        with self._conn() as c:
            rows = c.execute("select region, sector from doc_documents where sector is not null group by region, sector order by sector").fetchall()
        out: dict[str, list[str]] = {}
        for region, sector in rows:
            out.setdefault(region.strip(), []).append(sector)
        return out

    def queue_stats(self) -> dict:
        with self._conn() as c:
            waiting, failed, due = c.execute(
                "select count(*) filter (where tries < %s), count(*) filter (where tries >= %s), "
                "count(*) filter (where tries < %s and next_at <= now()) from doc_queue", (MAX_TRIES, MAX_TRIES, MAX_TRIES)).fetchone()
            errors = c.execute("select symbol, title, last_error from doc_queue where tries >= %s order by added_at desc limit 5",
                               (MAX_TRIES,)).fetchall()
            size = c.execute("select coalesce(sum(pg_total_relation_size(c.oid)), 0) from pg_class c join pg_namespace n "
                             "on n.oid = c.relnamespace where n.nspname = current_schema() and c.relkind = 'r' "
                             "and c.relname in ('doc_documents', 'doc_chunks', 'doc_queue')").fetchone()[0]
        return {"waiting": int(waiting), "failed": int(failed), "due": int(due), "bytes": int(size),
                "failures": [{"symbol": s, "title": t, "error": e} for s, t, e in errors]}


def _plan_rows(plan) -> int:
    """The planner's row estimate from EXPLAIN (FORMAT JSON)."""
    try:
        node = plan[0]["Plan"] if isinstance(plan, list) else plan["Plan"]
        return int(node.get("Plan Rows") or 0)
    except (KeyError, IndexError, TypeError, ValueError):
        return 0


_store = None
_store_of = None


def store():
    """The document store on the market database, or None while MARKET_DATABASE_URL isn't set (the search then says the
    index isn't set up, and the nightly worker does nothing)."""
    global _store, _store_of
    if _override is not None:
        return _override
    from . import market_store
    m = market_store.store()
    if m is None:
        return None
    if _store is None or _store_of is not m:
        _store, _store_of = DocStore(m), m
    return _store


_override = None


def use(s) -> None:
    """Swap in a store (tests, the browser tests' fake world); None goes back to the market database's."""
    global _override
    _override = s
