"""Import a watchlist (owner, 12 Nov): symbols pasted (one a line or separated by commas, any case, NSE, BSE or US tickers, ISINs or
company names) or a column of a CSV or Excel file, each looked up with the app's own symbol search (the one behind every company
box, main.suggester), so nothing is guessed:

- "found": the symbol, BSE code or ISIN exactly, one company;
- "confirm": a name, a short name or a near miss, or a symbol two markets share: up to three suggestions, the best first;
- "missing": nothing in the lists matches.

The page then adds what the person kept through PUT /watch/lists/{id}/items, so the plan's limits (plans.py watchlists and
watchlist_symbols) are enforced where they always are, and it says before that call how many fit.

Pasting is for every plan, up to its limits. Reading a file is Basic and up (plans.py "watchlist_import"): the file is read
with the broker holdings-file reader (holdings_file.table: CSV, .xlsx or a broker's HTML .xls, its size, rows and cells capped)
and its columns are sent back for the person to pick the one with the symbols. Nothing is stored: the file is read in memory and
forgotten. Facts only: names and symbols."""
import re
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import holdings_file, name_search
from . import watch_store as WS
from .auth import current_profile
from .responses import err, ok

router = APIRouter(prefix="/watch/import", tags=["watch"])

MAX_QUERIES = WS.HARD_SYMBOLS      # lines checked in one go: a list never holds more
QUERY_MAX = 80                     # characters of one line (a long company name)
SUGGESTIONS = 3
MAX_COLUMNS = 20                   # columns of a file offered to pick from
SAMPLE = 3
FILE_BYTES = 1024 * 1024           # a watchlist file is a few kilobytes
RESOLVES, FILES = 20, 30           # checks a person may run a minute, files read an hour
FEATURE = "watchlist_import"


def _m():
    from . import main
    return main


class ResolveReq(BaseModel):
    queries: list[str] = Field(default_factory=list, max_length=MAX_QUERIES)
    market: Literal["IN", "US", "both"] = "both"


class FileReq(BaseModel):
    data: str = Field(..., max_length=FILE_BYTES * 4 // 3 + 300)        # base64 or a data: URL
    filename: str = Field("", max_length=200)


def clean(q: str) -> str:
    """One line as typed, tidied: spaces collapsed, quotes and stray punctuation at its ends dropped, at most QUERY_MAX long."""
    s = " ".join(str(q or "").split())
    return s.strip("\"'`;,.|\t ")[:QUERY_MAX]


def item_of(row: dict) -> dict | None:
    """A search row as a Market Watch item (the identifier the company pages use: NSE symbol, BSE code or US ticker)."""
    return WS.normalize_item({"market": row.get("market"), "symbol": row.get("id") or row.get("symbol"), "name": row.get("name"), "kind": "stock"})


def resolve_one(q: str, market: str | None, search) -> dict:
    """What one line is: found (one exact match), confirm (suggestions, the best first) or missing. `search(q, market, limit)` is
    the app's ranked symbol search (rows with `match`, name_search's group)."""
    hits = [h for h in (search(q, market, SUGGESTIONS + 2) or []) if item_of(h)]
    if not hits:
        return {"query": q, "status": "missing", "item": None, "suggestions": []}
    best = hits[0]["match"]
    top = [h for h in hits if h["match"] == best]
    if best == name_search.EXACT and len(top) == 1:
        return {"query": q, "status": "found", "item": item_of(hits[0]), "suggestions": []}
    seen, sugg = set(), []
    for h in hits:
        it = item_of(h)
        if it["id"] not in seen:
            seen.add(it["id"])
            sugg.append(it)
    return {"query": q, "status": "confirm", "item": None, "suggestions": sugg[:SUGGESTIONS]}


def resolve(queries: list[str], market: str | None, search) -> list[dict]:
    """Each distinct line once (case aside), in the order given."""
    out, seen = [], set()
    for raw in queries[:MAX_QUERIES]:
        q = clean(raw)
        if not q or q.upper() in seen:
            continue
        seen.add(q.upper())
        out.append(resolve_one(q, market, search))
    return out


def columns_of(rows: list[list[str]]) -> dict:
    """The file's columns to pick from: each one's name, a few of its values and every distinct value (up to MAX_QUERIES), and
    the one that most likely holds the symbols (`guess`). The column names are the first row naming a symbol, ISIN or company
    column (a broker's export has account lines above them); a file without one is all values, its columns numbered."""
    head_at, found = None, {}
    for i, row in enumerate(rows[:holdings_file.HEADER_SCAN]):
        cols = holdings_file._columns(row)
        if cols.keys() & {"symbol", "isin", "name"}:
            head_at, found = i, cols
            break
    body = rows[head_at + 1:] if head_at is not None else rows
    width = min(MAX_COLUMNS, max((len(r) for r in [*body, *(rows[head_at:head_at + 1] if head_at is not None else [])]), default=0))
    head = rows[head_at] if head_at is not None else []
    out = []
    for c in range(width):
        values, seen = [], set()
        for r in body:
            v = clean(r[c]) if c < len(r) else ""
            if v and v.upper() not in seen:
                seen.add(v.upper())
                values.append(v)
            if len(values) >= MAX_QUERIES:
                break
        name = (head[c].strip() if c < len(head) else "") or f"Column {c + 1}"
        if values:
            out.append({"index": c, "name": name[:60], "sample": values[:SAMPLE], "values": values, "count": len(values)})
    guess = next((found[k] for k in ("symbol", "isin", "name") if k in found and any(o["index"] == found[k] for o in out)), None)
    if guess is None:      # no named column: the first that isn't only amounts (a quantity, a price; a six-digit BSE code counts as a symbol)
        amount = lambda v: holdings_file.number(v) is not None and not re.fullmatch(r"\d{6}", v)  # noqa: E731
        guess = next((o["index"] for o in out if not all(amount(v) for v in o["values"][:20])), out[0]["index"] if out else None)
    return {"columns": out, "guess": guess, "named": head_at is not None}


@router.post("/resolve")
def resolve_lines(req: ResolveReq, profile=Depends(current_profile)):
    """Look up pasted lines (or a file's column): every plan."""
    m = _m()
    m.throttle(profile, "watch_import", RESOLVES, 60, "That's a lot of checks in a minute. Wait a moment and try again.")
    market = None if req.market == "both" else req.market
    return ok({"rows": resolve(req.queries, market, m.suggester.search_ranked)})


@router.post("/file")
def read_file(req: FileReq, profile=Depends(current_profile)):
    """A CSV or Excel file's columns, to pick the one with the symbols: Basic and up."""
    m = _m()
    m.need(profile, FEATURE, "Importing a watchlist from a file")
    m.throttle(profile, "watch_import_file", FILES, 3600, "That's a lot of files in an hour. Try again a little later.")
    data = m.upload_bytes(req.data, "A watchlist file is much smaller; check it's the right file.", FILE_BYTES)
    try:
        rows = holdings_file.table(data, FILE_BYTES, holdings_file.MAX_ROWS, "A watchlist file is much smaller; check it's the right file.")
    except holdings_file.FileError as e:
        err(400, "bad_file", str(e))
    got = columns_of(rows)
    if not got["columns"]:
        err(400, "no_columns", "That file has no symbols or names in it. Check it's the right file, or paste the symbols instead.")
    return ok(got)
