"""Putting what a statement or a broker says into the stores the rest of the app reads: My Holdings (this file), the mutual
fund store (money_mf), Net worth (money_networth), the trade journal (journal) and the dividends and TDS the tax report
uses. Each goes through the store's own matching, de-duplication and history, the same as an upload by hand.

For holdings a statement or a broker *states* what is held, so a sync sets the quantity (it doesn't add to it, which
would double a share count each time the same file arrived) and keeps the average price already known when the
source has none and the quantity is the same. Whatever came from a source and is no longer in its latest read is taken
out (sold), but only when that read was whole: it had rows and every row matched a listed company. An empty read, or one with a row that didn't
match, keeps what the source gave before (an empty broker reply is a failed read, not "sold everything"). Where two
sources name the same stock, the live broker wins over a statement and a statement over a file or typed entry."""
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


def _parts(i: dict, accounts) -> dict:
    """A statement holding's quantity per demat account, without the accounts in `accounts` (the ones a statement covers)."""
    return {a: q for a, q in (i.get("accts") or {}).items() if a not in accounts}


def merge_sync(before: list[dict], found: list[dict], via: str, replace: bool = True,
               accounts: set[str] | None = None) -> tuple[list[dict], dict]:
    """(holdings, counts). `found` are matched holdings from one source (`via`). `accounts`: the demat accounts a statement
    covers; a holding's parts from other accounts ("accts") stay and add up with this read's. One without "accts" (saved
    before statements kept them, or edited by hand) belongs to whatever account the read covers."""
    mine = PRIORITY.get(via, 1)
    market = {holdings.market_of(f) for f in found}
    accounts = accounts or set()
    kept = {}
    prev = {_key(i): i for i in before if i.get("via") == via}
    for i in before:
        # a read replaces what the same source gave before, within the market it covers (IBKR is US only)
        if replace and i.get("via") == via and (holdings.market_of(i) in market or not found):
            rest = _parts(i, accounts)
            if rest:                      # still held in a demat account this statement doesn't cover
                kept[_key(i)] = {**i, "accts": rest, "qty": round(sum(rest.values()), 4)}
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
        if cur and cur.get("via") == via and f.get("accts"):
            new["accts"] = {**_parts(cur, accounts), **f["accts"]}
            new["qty"] = round(sum(new["accts"].values()), 4)
        old = prev.get(k) or cur
        if old:
            same = abs(float(old["qty"]) - float(new["qty"])) < 1e-9
            if not new.get("avg") and old.get("avg") and same:      # a changed quantity with no cost has no known average
                new["avg"] = old["avg"]
            for extra in ("sector", "since", "applied", "dismissed", "adjusted"):
                if old.get(extra) is not None:
                    new.setdefault(extra, old[extra])
            changed += not same
        else:
            added += 1
        kept[k] = new
    return list(kept.values()), {"added": added, "changed": int(changed), "skipped": skipped}


def _match_by_account(rows: list[dict], matcher) -> tuple[list[dict], list[dict]]:
    """match_all for a statement's rows ({..., "acct"}): one holding per stock, with its quantity in each account."""
    found, missed = [], []
    for a in dict.fromkeys(r["acct"] for r in rows):
        got, miss = holdings.match_all([r for r in rows if r["acct"] == a], matcher)
        found += [{**f, "accts": {a: f["qty"]}} for f in got]
        missed += miss
    out: dict[str, dict] = {}
    for f in found:
        cur = out.get(_key(f))
        if cur:
            accts = {**cur["accts"], **{a: cur["accts"].get(a, 0) + q for a, q in f["accts"].items()}}
            f = {**holdings.merge([cur, f])[0], "accts": accts}
        out[_key(f)] = f
    return list(out.values()), missed


def sync_holdings(profile: dict, rows: list[dict], via: str, source: str, replace: bool = True, since: str | None = None,
                  accounts: set[str] | None = None) -> dict:
    """Match a source's rows ({symbol, isin, name, qty, avg, market}) to listed companies and save them with My Holdings.
    `since` is the day the rows are as of (a statement's last day), else the day they're saved. A statement's rows also
    carry "acct" (its demat account) and `accounts` lists every account it covers.
    {"saved", "count", "unmatched": [...], "over_limit": [...], "added", "changed", "kept", "empty"}."""
    uid = profile["id"]
    in_rows = [r for r in rows if r.get("market") != "US"]
    us_rows = [r for r in rows if r.get("market") == "US"]
    match = _match_by_account if accounts is not None else holdings.match_all
    found, missed = match(in_rows, deps.matcher()) if in_rows else ([], [])
    if us_rows:
        us_found, us_missed = holdings.match_us(us_rows, deps.us_find)
        found, missed = found + us_found, missed + us_missed
    limit = plans.holdings_limit(profile["_plan"])
    out = {}

    def merged(before):                   # runs again on the newer holdings if the user saves one meanwhile
        had = {_key(i) for i in before["items"] if i.get("via") == via}
        # a line that didn't match but names a holding this source gave before (a market list down for a moment) makes the
        # read partial: nothing is taken out. A line that never matched (a gold bond) doesn't stop sold stocks leaving.
        names = {str(v).upper() for m in missed for v in (m.get("symbol"), m.get("isin")) if v}
        unsure = any(i["symbol"].upper() in names or str(i.get("isin") or "").upper() in names
                     for i in before["items"] if i.get("via") == via)
        whole = bool(found) and not unsure        # only a whole read takes out what the source no longer names
        items, counts = merge_sync(before["items"], found, via, replace and whole, accounts)
        out["kept"] = 0 if whole else len(had - {_key(f) for f in found})
        items, out["over"] = holdings.cap(items, before["items"], limit)   # a downgrade deletes nothing
        out["counts"], out["had"] = counts, bool(had)
        out["saved"] = bool(found) or counts["added"] or counts["changed"] or len(items) != len(before["items"])
        if not out["saved"]:
            return None
        known = {i["symbol"]: i.get("sector") for i in holdings.indian(before["items"])}
        return deps.with_sectors(items, known), source, False, since
    holdings.update(uid, merged)
    return {"saved": bool(out["saved"]), "count": len(found), "unmatched": missed[:50], "unmatched_count": len(missed),
            "over_limit": out["over"], "kept": out["kept"], "empty": not rows and out["had"], **out["counts"]}


def note(got: dict, name: str) -> str | None:
    """What a read left as it was, in plain words for the connection's card; None when the read was whole."""
    if got.get("empty"):
        return f"{name} returned no holdings. That's treated as a failed read, so the holdings read from it before are kept."
    if got.get("unmatched_count"):
        lines = ", ".join(m["text"] for m in got.get("unmatched", [])[:5] if m.get("text"))
        n = got["unmatched_count"]
        return (f"{n} {'line' if n == 1 else 'lines'} from {name} didn't match a listed company" + (f" ({lines})" if lines else "")
                + (f", so {got['kept']} holdings read from it before are kept as they were." if got.get("kept") else "."))
    return None
