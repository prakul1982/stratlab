"""Who a theme's companies are, and which companies a theme considers (lane e57, Release 57; the audit of the 24 live R56 decks, RC6, RC7).

- `resolve_identity`: a company the AI's map names under a line the index does not list (the exchange's series after the symbol,
  "HFCL-BE"; a name spelled with another legal form, "Ltd" for "Limited") is the index's company, never a second member beside it (the live
  R56 Telecom deck held HFCL and Sterlite twice). Names are compared normalised (norm_name): legal form, punctuation, "&" and "and".
- `with_peers`: a company the map names from an official industry the theme does not hold, and whose own words were checked to show the
  theme's work, makes its industry's other listed companies above a size floor (the theme's median market value) candidates of the theme
  (the live R56 Consumer retail deck lacked Best Buy, AutoZone, Tractor Supply, Gap and Dick's). A candidate joins only on its own stored
  description showing the theme's work; every other one is said, with its reason ("peer_candidates"), and the ones without a description
  are read in the background (theme_routes.describe_missing).
- `data_gaps`: the members above the theme's median market value with no description of their own or no figures.

Nothing here reads a source or asks the AI: the index rows and the stored descriptions only."""
from __future__ import annotations

import re
from statistics import median

LEGAL = re.compile(r"\b(?:limited|ltd|inc|incorporated|corp|corporation|co|company|plc|llc|lp|nv|n v|sa|s a|ag|holdings?|the)\b")
SERIES = re.compile(r"-[A-Z]{2}$")          # the exchange's series after a symbol: -BE, -BZ, -SM, -ST, -RR (a REIT), -IV (an InvIT)
PEER_MAX = 12                               # candidates a pick's industry gives a theme, largest first
PEERS_MAX = 40                              # ...and a theme in all


def norm_name(name) -> str:
    """A company name as compared: lower case, "&" as "and", punctuation and legal forms ("Limited", "Ltd", "Inc.") taken out."""
    t = str(name or "").lower().replace("&", " and ")
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return " ".join(LEGAL.sub(" ", t).split())


def plain_symbol(sym) -> str:
    """A symbol without the exchange's series after it ("HFCL-BE" -> "HFCL"); the symbol itself when it has none."""
    s = str(sym or "")
    return SERIES.sub("", s) or s


def resolve_identity(m: dict, rows: list[dict]) -> dict:
    """The map with each company the index does not list under its own ticker taken as the index's company: by its symbol without the
    exchange's series, else by a normalised name only one listed company has. Within a layer, a company named twice (once under each
    line) is one, keeping the checked one's words. Every other company is as it was."""
    idx = {r["symbol"]: r for r in rows or [] if r.get("symbol")}
    if not idx:
        return m
    by_name: dict[str, list[str]] = {}
    for s_, r in idx.items():
        k = norm_name(r.get("name"))
        if k:
            by_name.setdefault(k, []).append(s_)

    def resolved(c: dict) -> dict:
        t = c.get("ticker")
        if not t or t in idx:
            return c
        p = plain_symbol(t)
        if p != t and p in idx:
            return {**c, "ticker": p, "listed_as": t}
        hits = by_name.get(norm_name(c.get("name")), [])
        return {**c, "ticker": hits[0], "listed_as": t} if len(hits) == 1 else c

    def one(cos):
        out, at = [], {}
        for c in (resolved(x) for x in cos or []):
            t = c.get("ticker")
            if t in at:
                was = out[at[t]]
                if c.get("verified") and not was.get("verified"):
                    out[at[t]] = {**was, **{k: c[k] for k in ("what", "verified") if k in c}}
                continue
            at[t] = len(out)
            out.append(c)
        return out
    return {**m, "value_chain": [{**v, "companies": one(v.get("companies"))} for v in m.get("value_chain") or []],
            "sub_themes": [{**x, "companies": one(x.get("companies"))} for x in m.get("sub_themes") or []]}


def one_listing(out: dict) -> dict:
    """The checked map with one member per company: of members sharing a normalised name and an official industry (or a symbol without its
    series), the one with the largest market value stays and each other is left out as another listing line of it (the index lists some
    US companies twice: an old and a new ticker, an over-the-counter line, a bankruptcy "Q" line). "placements" gets "same_company":
    [{ticker, name, kept}] and its counts lose them."""
    cos = [c for g in (out.get("value_chain") or []) + (out.get("sub_themes") or []) for c in g.get("companies") or [] if c.get("ticker")]
    groups: dict[tuple, list] = {}
    for c in {c["ticker"]: c for c in cos}.values():
        n = norm_name(c.get("name"))
        if n:
            groups.setdefault(("n", n, str(c.get("industry") or "").lower()), []).append(c)
        groups.setdefault(("s", plain_symbol(c["ticker"])), []).append(c)
    gone: dict[str, dict] = {}
    for g in groups.values():
        live = [c for c in g if c["ticker"] not in gone]
        if len(live) < 2:
            continue
        keep = max(live, key=lambda c: (c.get("cap") or 0, bool(c.get("verified")), -len(c["ticker"]), c["ticker"]))
        for c in live:
            if c is not keep and c["ticker"] != keep["ticker"]:
                gone[c["ticker"]] = {"ticker": c["ticker"], "name": c.get("name") or c["ticker"], "kept": keep["ticker"]}
    if not gone:
        return out
    out = {**out, "value_chain": [{**v, "companies": [c for c in v.get("companies") or [] if c.get("ticker") not in gone]} for v in out.get("value_chain") or []],
           "sub_themes": [{**x, "companies": [c for c in x.get("companies") or [] if c.get("ticker") not in gone]} for x in out.get("sub_themes") or []]}
    out["value_chain"] = [v for v in out["value_chain"] if v.get("companies") or not v.get("official")]
    pl = dict(out.get("placements") or {})
    pl["same_company"] = sorted(gone.values(), key=lambda x: x["ticker"])
    for k in ("placed", "total"):
        if isinstance(pl.get(k), int):
            pl[k] = max(0, pl[k] - len(gone))
    out["placements"] = pl
    return out


def _floor(out: dict) -> float:
    caps = [c.get("cap") for v in out.get("value_chain") or [] for c in v.get("companies") or [] if isinstance(c.get("cap"), (int, float)) and c["cap"] > 0]
    return float(median(caps)) if caps else float("inf")


def with_peers(out: dict, rows: list[dict], about, theme: str, key=None) -> dict:
    """The checked map with the candidates its map picks give (see the module). `about(symbol)`: a company's stored description or None.
    A candidate joins the pick's layer when its own words say that layer's work (its name and the map's description of it): basis "peer",
    "peer_of" the pick, "verified" (its own words were read and checked); "placements" gets "peer_candidates": every candidate considered,
    [{ticker, name, industry, cap, peer_of, joined, why}]."""
    from . import theme_base as TB, theme_data as TD
    key = key or TB.key
    idx = {r["symbol"]: r for r in rows or [] if r.get("symbol")}
    held = {key(i) for i in (out.get("placements") or {}).get("industries") or []}
    placed = {c.get("ticker") for g in (out.get("value_chain") or []) + (out.get("sub_themes") or []) for c in g.get("companies") or []}
    picks: dict[str, tuple] = {}            # industry -> (the pick, the index of its layer)
    for i, v in enumerate(out.get("value_chain") or []):
        if v.get("official"):
            continue
        for c in v.get("companies") or []:
            ind = (idx.get(c.get("ticker")) or {}).get("industry")
            if c.get("verified") is True and not c.get("base") and ind and key(ind) not in held:
                picks.setdefault(key(ind), (c["ticker"], i))
    if not picks:
        return out
    floor = _floor(out)
    vc = [dict(v) for v in out.get("value_chain") or []]
    adds: dict[int, list] = {}
    said: list[dict] = []
    for ind, (pick, at) in picks.items():
        # its own words must say the work of the pick's layer (its name and the map's description of it), the layer it would join
        words = TD.theme_words({"value_chain": [vc[at]]}, "")
        peers = sorted((r for s_, r in idx.items() if key(r.get("industry")) == ind and s_ not in placed and (r.get("market_cap") or 0) >= floor),
                       key=lambda r: (-(r.get("market_cap") or 0), r["symbol"]))[:PEER_MAX]
        for r in peers:
            if len(said) >= PEERS_MAX:
                break
            text = None
            try:
                text = about(r["symbol"])
            except Exception:
                pass
            own = TB.own_words(TB.own_line(text, r.get("name") or ""), r.get("name") or "") if text else ""
            joined = bool(own) and TD.does_the_work(own, words)
            why = ("its own description shows its layer's work" if joined else
                   "its own description describes other work" if own else "no description of its own is read yet")
            said.append({"ticker": r["symbol"], "name": r.get("name") or r["symbol"], "industry": r.get("industry") or "", "cap": r.get("market_cap"),
                         "peer_of": pick, "joined": joined, "why": why})
            if joined:
                adds.setdefault(at, []).append(
                    {"ticker": r["symbol"], "name": r.get("name") or r["symbol"], "what": own, "verified": True, "base": False, "basis": "peer",
                     "industry": r.get("industry") or "", "cap": r.get("market_cap"), "peer_of": pick})
    for at, cos in adds.items():
        vc[at]["companies"] = list(vc[at].get("companies") or []) + cos
    out = {**out, "value_chain": vc}
    pl = dict(out.get("placements") or {})
    pl["peer_candidates"] = said
    n = sum(len(cos) for cos in adds.values())
    if n:
        pl["placed"] = int(pl.get("placed") or 0) + n
        pl["total"] = int(pl.get("total") or 0) + n
        pl["added"] = int(pl.get("added") or 0) + n
        pl["confirmed"] = int(pl.get("confirmed") or 0) + n
    out["placements"] = pl
    return out


def peers_unread(m: dict) -> list[str]:
    """The candidates of a checked map with no description of their own read yet, largest first (read in the background)."""
    cs = [x for x in ((m.get("placements") or {}).get("peer_candidates") or []) if isinstance(x, dict) and x.get("why", "").startswith("no description")]
    return [x["ticker"] for x in sorted(cs, key=lambda x: -(x.get("cap") or 0))]


def data_gaps(members: list[dict], has_description, has_figures) -> list[dict]:
    """The members above the theme's median market value with no description of their own or no figures: [{ticker, name, cap, lacks}],
    largest first (lacks: "description", "figures" or both)."""
    caps = [c.get("cap") for c in members if isinstance(c.get("cap"), (int, float)) and c["cap"] > 0]
    if not caps:
        return []
    mid = median(caps)
    out = []
    for c in sorted(members, key=lambda c: -(c.get("cap") or 0)):
        if not isinstance(c.get("cap"), (int, float)) or c["cap"] <= mid:
            continue
        lacks = [w for w, ok in (("description", has_description(c["ticker"])), ("figures", has_figures(c["ticker"]))) if not ok]
        if lacks:
            out.append({"ticker": c["ticker"], "name": c.get("name") or c["ticker"], "cap": c["cap"], "lacks": lacks})
    return out
