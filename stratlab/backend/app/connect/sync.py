"""Putting what a statement or a broker says into the stores the rest of the app reads: My Holdings (this file), the mutual
fund store (money_mf), Net worth (money_networth), the trade journal (journal) and the dividends and TDS the tax report
uses. Each goes through the store's own matching, de-duplication and history, the same as an upload by hand.

For holdings a statement or a broker *states* what is held, so a sync sets the quantity (it doesn't add to it, which
would double a share count each time the same file arrived) and keeps the average price already known when the
source has none. Whatever came from a source and is no longer in its latest read is taken out (sold). Where two sources
name the same stock, the live broker wins over a statement and a statement over a file or typed entry."""
from .. import holdings, plans

PRIORITY = {"kite": 3, "ibkr": 3, "cas": 2}


class Deps:
    """What main.py hands over (the matcher needs the live market lists, which live there)."""
    matcher = None          # () -> holdings.Matcher
    us_find = None          # (ticker) -> {"symbol", "name"} | None
    with_sectors = None     # (items, known) -> items


deps = Deps()


def setup(matcher, us_find, with_sectors) -> None:
    deps.matcher, deps.us_find, deps.with_sectors = matcher, us_find, with_sectors


def profile_for(uid: str) -> dict | None:
    """A signed-out stand-in for current_profile: the stored profile with its plan (the daily jobs and the inbox have no
    request to read it from)."""
    from .. import db
    p = db.get_profile(uid)
    if not p:
        return None
    p = dict(p)
    p["_plan"] = plans.access_plan(p)
    return p


def _key(i: dict) -> str:
    return f"{i.get('exchange')}:{i['symbol']}"


def merge_sync(before: list[dict], found: list[dict], via: str, replace: bool = True) -> tuple[list[dict], dict]:
    """(holdings, counts). `found` are matched holdings from one source (`via`)."""
    mine = PRIORITY.get(via, 1)
    market = {holdings.market_of(f) for f in found}
    kept = {}
    prev = {_key(i): i for i in before if i.get("via") == via}
    for i in before:
        # a read replaces what the same source gave before, within the market it covers (IBKR is US only)
        if replace and i.get("via") == via and (holdings.market_of(i) in market or not found):
            continue
        kept[_key(i)] = i
    added = changed = skipped = 0
    for f in found:
        k = _key(f)
        cur = kept.get(k) or prev.get(k)
        if cur and k in kept and PRIORITY.get(cur.get("via"), 1) > mine:
            skipped += 1
            continue
        new = {**f, "via": via}
        if cur:
            if not new.get("avg") and cur.get("avg"):
                new["avg"] = cur["avg"]
            for extra in ("sector", "since", "applied", "dismissed", "adjusted"):
                if cur.get(extra) is not None:
                    new.setdefault(extra, cur[extra])
            changed += abs(float(cur["qty"]) - float(new["qty"])) > 1e-9
        else:
            added += 1
        kept[k] = new
    return list(kept.values()), {"added": added, "changed": int(changed), "skipped": skipped}


def sync_holdings(profile: dict, rows: list[dict], via: str, source: str, replace: bool = True) -> dict:
    """Match a source's rows ({symbol, isin, name, qty, avg, market}) to listed companies and save them with My Holdings.
    {"saved", "count", "unmatched": [...], "over_limit": [...], "added", "changed"}."""
    uid = profile["id"]
    in_rows = [r for r in rows if r.get("market") != "US"]
    us_rows = [r for r in rows if r.get("market") == "US"]
    found, missed = holdings.match_all(in_rows, deps.matcher()) if in_rows else ([], [])
    if us_rows:
        us_found, us_missed = holdings.match_us(us_rows, deps.us_find)
        found, missed = found + us_found, missed + us_missed
    before = holdings.load(uid)
    merged, counts = merge_sync(before["items"], found, via, replace)
    limit = plans.holdings_limit(profile["_plan"])
    over, merged = [i["symbol"] for i in merged[limit:]], merged[:limit]
    saved = bool(found) or counts["added"] or counts["changed"] or len(merged) != len(before["items"])
    if saved:
        known = {i["symbol"]: i.get("sector") for i in holdings.indian(before["items"])}
        holdings.save(uid, deps.with_sectors(merged, known), source)
    return {"saved": bool(saved), "count": len(found), "unmatched": missed[:50], "unmatched_count": len(missed),
            "over_limit": over, **counts}
