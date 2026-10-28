"""Market Watch lists (MW-1): several named lists of instruments from every market, kept per user.

The first list is the person's Research watchlist, the stocks they star: it stays in its own row (`watchlist:<uid>`, which
the scans, filings, alerts and business updates read), so nothing is kept twice. What that row can't hold (indices, crypto,
forex, commodities, other countries' stocks) and the order of the whole list sit in one extra row of the `watchlists` table.
Every other list is one row of that table: its name, its items in the order the person put them, and its place among the
lists. Rows are per user and only the server reads them (row-level security on, no client policy).

An item is the instrument as the chart and the quotes name it: {"id": "IN:RELIANCE", "market": "IN", "symbol": "RELIANCE",
"name": "Reliance Industries", "kind": "stock"}. Stocks and ETFs of India and the US are named by their symbol (the company
pages' own), every other market by the markets registry's id (crypto "CRYPTO:BTC-USD", forex "FX:EURUSD=X", gold "CMDTY:GC=F").

Limits come from the plan (plans.py: watchlists, watchlist_symbols) and are stated before they bite; a list already longer
than a lower plan allows is kept, it just can't grow. Bounded: at most HARD_LISTS lists and HARD_SYMBOLS symbols in one.
Facts only: nothing here reads or scores an instrument."""
import json
import re
import uuid

from . import db
from .plans import PLANS, bigger_plan
from .responses import err

HARD_LISTS = 25               # lists a person can have, whatever the plan
HARD_SYMBOLS = 300            # symbols in one list, whatever the plan
NAME_MAX = 40
DEFAULT_ID = "default"
DEFAULT_NAME = "Watchlist"
MARKETS = ("IN", "US", "UK", "EU", "JP", "FX", "CRYPTO", "MCX", "CDS", "CMDTY")
KINDS = ("stock", "etf", "index", "fx", "crypto", "commodity", "future")
SYMBOL = re.compile(r"^[A-Za-z0-9^&._=\-]{1,40}$")
INDICES = {"^NSEI": "NIFTY 50", "^BSESN": "SENSEX", "^NSEBANK": "NIFTY BANK", "^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "DOW JONES"}
# markets whose stocks and ETFs the Research watchlist holds
RESEARCH = ("IN", "US")


def limit(plan: str, key: str) -> int | None:
    return PLANS[plan][key]


def limits(plan: str) -> dict:
    """What the plan allows, for the panel to say before a limit bites: None is no limit."""
    return {"lists": limit(plan, "watchlists"), "symbols": limit(plan, "watchlist_symbols"),
            "charts": limit(plan, "chart_saves"), "indicators": limit(plan, "chart_indicators"),
            "next": {"lists": bigger_plan(plan, "watchlists"), "symbols": bigger_plan(plan, "watchlist_symbols"),
                     "charts": bigger_plan(plan, "chart_saves"), "indicators": bigger_plan(plan, "chart_indicators")}}


def _kind_of(market: str, symbol: str, given: str | None) -> str:
    if given in KINDS:
        return given
    if symbol.startswith("^"):
        return "index"
    return {"CRYPTO": "crypto", "FX": "fx", "CMDTY": "commodity", "MCX": "future", "CDS": "future"}.get(market, "stock")


def normalize_item(raw) -> dict | None:
    """One well-formed item, or None. The id is rebuilt from market and symbol, so it can never disagree with them."""
    if not isinstance(raw, dict):
        return None
    market = str(raw.get("market") or "").upper()
    symbol = str(raw.get("symbol") or "").strip().upper()
    if market not in MARKETS or not SYMBOL.match(symbol):
        return None
    if market in RESEARCH and not (symbol[0].isalnum() or symbol[0] == "^"):
        return None
    name = str(raw.get("name") or "").strip()[:120]
    if not name or name.upper() == symbol:
        name = INDICES.get(symbol) or name or symbol
    return {"id": f"{market}:{symbol}", "market": market, "symbol": symbol, "name": name,
            "kind": _kind_of(market, symbol, raw.get("kind") if isinstance(raw.get("kind"), str) else None)}


def clean_items(raw, cap: int = HARD_SYMBOLS) -> list[dict]:
    """The items of a list as saved: well-formed, each once, in the order given, at most `cap`."""
    out, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        it = normalize_item(r)
        if it and it["id"] not in seen:
            seen.add(it["id"])
            out.append(it)
        if len(out) >= cap:
            break
    return out


def clean_name(raw) -> str:
    name = re.sub(r"\s+", " ", str(raw or "")).strip()[:NAME_MAX]
    if not name:
        err(400, "bad_name", "Give the list a name.")
    return name


# ---------- the first list: the Research watchlist, plus what it can't hold ----------
def _research_key(uid: str) -> str:
    return f"watchlist:{uid}"


def _research_items(uid: str) -> list[dict]:
    raw = db.json_value(db.get_setting(_research_key(uid)), {})
    items = raw.get("items") if isinstance(raw, dict) else None
    out = []
    for i in items if isinstance(items, list) else []:
        if isinstance(i, dict):
            it = normalize_item({"market": i.get("region"), "symbol": i.get("symbol"), "name": i.get("name"), "kind": "stock"})
            if it:
                out.append(it)
    return out


def _extras_row(uid: str) -> dict | None:
    rows = db.sb().table("watchlists").select("*").eq("id", f"d-{uid}").eq("user_id", uid).execute().data
    return rows[0] if rows else None


def _is_research(it: dict) -> bool:
    return it["market"] in RESEARCH and it["kind"] in ("stock", "etf")


def default_items(uid: str) -> list[dict]:
    base, row = _research_items(uid), _extras_row(uid)
    extras = clean_items((row or {}).get("items"))
    order = [str(x) for x in ((row or {}).get("order_ids") or [])] if isinstance((row or {}).get("order_ids"), list) else []
    by = {it["id"]: it for it in [*base, *extras]}
    got = [by.pop(i) for i in order if i in by]
    return got + list(by.values())          # what was added elsewhere (starred on a company page) goes last


def save_default(uid: str, items: list[dict]) -> list[dict]:
    """Keep the first list: stocks and ETFs of India and the US in the Research watchlist's row, the rest, and the order of
    all of them, in the list's extra row."""
    research = [{"region": it["market"], "symbol": it["symbol"], "name": it["name"]} for it in items if _is_research(it)]
    db.set_setting(_research_key(uid), json.dumps({"items": research}))
    extras = [it for it in items if not _is_research(it)]
    row = {"id": f"d-{uid}", "user_id": uid, "name": DEFAULT_NAME, "kind": "default", "position": 0, "items": extras,
           "order_ids": [it["id"] for it in items], "updated_at": db.now_iso()}
    if extras or _extras_row(uid):
        db.sb().table("watchlists").upsert(row).execute()
    return items


# ---------- the others ----------
def _rows(uid: str) -> list[dict]:
    rows = db.sb().table("watchlists").select("*").eq("user_id", uid).order("position").execute().data or []
    return [r for r in rows if r.get("kind") != "default"]


def _public(row: dict) -> dict:
    return {"id": row["id"], "name": row["name"], "default": False, "items": clean_items(row.get("items"))}


def all_lists(uid: str) -> list[dict]:
    """Every list in order, the first being the Research watchlist."""
    return [{"id": DEFAULT_ID, "name": DEFAULT_NAME, "default": True, "items": default_items(uid)}, *[_public(r) for r in _rows(uid)]]


def _row(uid: str, list_id: str) -> dict:
    rows = db.sb().table("watchlists").select("*").eq("id", list_id).eq("user_id", uid).execute().data
    if not rows or rows[0].get("kind") == "default":
        err(404, "no_list", "That list isn't there any more.")
    return rows[0]


def _full(plan: str, key: str, what: str) -> None:
    """Refuse (402) one more of something the plan's limit is already met for, saying plainly what the plan keeps and what the
    next plan up does."""
    cap = limit(plan, key)
    nxt = bigger_plan(plan, key)
    words = f"The {PLANS[plan]['name']} plan keeps {cap} {what}."
    if nxt:
        more = PLANS[nxt.lower()][key]
        words += f" {nxt} {'has no limit' if more is None else f'keeps {more}'}."
    err(402, "plan_limit", words)


def create(uid: str, name: str, plan: str) -> dict:
    name = clean_name(name)
    rows = _rows(uid)
    if len(rows) + 1 >= HARD_LISTS:
        err(400, "too_many_lists", f"That's the most lists a person can have ({HARD_LISTS}).")
    cap = limit(plan, "watchlists")
    if cap is not None and len(rows) + 1 >= cap:
        _full(plan, "watchlists", "watchlist" if cap == 1 else "watchlists")
    if any(r["name"].lower() == name.lower() for r in rows) or name.lower() == DEFAULT_NAME.lower():
        err(400, "name_taken", "You already have a list with that name.")
    row = {"id": str(uuid.uuid4()), "user_id": uid, "name": name, "kind": "list", "position": (rows[-1]["position"] + 1) if rows else 1,
           "items": [], "updated_at": db.now_iso()}
    return _public(db.sb().table("watchlists").insert(row).execute().data[0])


def rename(uid: str, list_id: str, name: str) -> dict:
    if list_id == DEFAULT_ID:
        err(400, "default_list", "The first list is your Research watchlist; it keeps its name.")
    name, row = clean_name(name), _row(uid, list_id)
    if any(r["name"].lower() == name.lower() and r["id"] != list_id for r in _rows(uid)) or name.lower() == DEFAULT_NAME.lower():
        err(400, "name_taken", "You already have a list with that name.")
    got = db.sb().table("watchlists").update({"name": name, "updated_at": db.now_iso()}).eq("id", list_id).eq("user_id", uid).execute().data
    return _public(got[0] if got else {**row, "name": name})


def delete(uid: str, list_id: str) -> None:
    if list_id == DEFAULT_ID:
        err(400, "default_list", "The first list is your Research watchlist. Remove its symbols instead.")
    _row(uid, list_id)
    db.sb().table("watchlists").delete().eq("id", list_id).eq("user_id", uid).execute()


def set_items(uid: str, list_id: str, raw, plan: str, known=None) -> list[dict]:
    """Replace a list's items (membership and order in one call). Past the plan's limit a list may only shrink or stay; an
    instrument added must be one StratLab knows (`known(item)` is False for one it doesn't)."""
    items = clean_items(raw)
    if isinstance(raw, list) and len(raw) > HARD_SYMBOLS:
        err(400, "too_many_symbols", f"A list holds up to {HARD_SYMBOLS} symbols.")
    before = default_items(uid) if list_id == DEFAULT_ID else clean_items(_row(uid, list_id).get("items"))
    had = {i["id"] for i in before}
    new = [i for i in items if i["id"] not in had]
    cap = limit(plan, "watchlist_symbols")
    if new and cap is not None and len(items) > max(cap, len(before)):
        _full(plan, "watchlist_symbols", "symbols in a list")
    for it in new:
        if callable(known) and known(it) is False:
            err(400, "unknown_symbol", f"{it['name']} isn't an instrument StratLab knows, so it wasn't added. Pick one from the suggestions.")
    if list_id == DEFAULT_ID:
        return save_default(uid, items)
    db.sb().table("watchlists").update({"items": items, "updated_at": db.now_iso()}).eq("id", list_id).eq("user_id", uid).execute()
    return items


def reorder(uid: str, ids: list[str]) -> list[str]:
    """The named lists in this order (the first list stays first)."""
    rows = {r["id"]: r for r in _rows(uid)}
    order = [i for i in dict.fromkeys(ids) if i in rows] + [i for i in rows if i not in ids]
    for n, i in enumerate(order, start=1):
        if rows[i]["position"] != n:
            db.sb().table("watchlists").update({"position": n}).eq("id", i).eq("user_id", uid).execute()
    return [DEFAULT_ID, *order]


def forget(uid: str) -> None:
    """Every list of one user but the Research watchlist (the hook for deleting an account)."""
    db.sb().table("watchlists").delete().eq("user_id", uid).execute()
