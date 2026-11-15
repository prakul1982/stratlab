"""A theme's change log ("What changed"): each time a theme's figures are stored again (a Refresh, a new map, a re-check under new
placement rules, or the companies' own figures moving), the stored read is set against the one stored before it and what differs is
recorded, dated:

- companies added to the theme, and removed with the reason the read states (another business than the industry files it under, no
  figures stored for it, no longer in the theme's map);
- companies moved from one layer to another (from -> to);
- layers renamed, split or merged, told apart by where their companies went (a layer whose companies went to one new layer that took
  them alone was renamed; to two or more new layers, split; two or more layers whose companies went to one new layer, merged), and
  layers added or removed;
- latest-year figures restated: the same company and the same year, its revenue moved by more than REVENUE_SHARE or its margin (EBITDA,
  else net for a lender) by more than MARGIN_POINTS.

Stored in app_settings under "theme:changes:<market>:<theme>" (the main database, beside the theme's P/E history "theme:hist:"): the
previous read's compact snapshot (each company's name, layer, year, revenue and margin) and the last KEEP entries, each list in an entry
at most ROWS_KEEP rows (its counts are always the full ones). One row a theme, bounded; no job of its own: it is written only when a
read is stored (theme_routes.dive_of).

Who sees what (plans.py "theme_changes"): Basic and Pro the whole log; Free the latest entry's counts and its first FREE_ROWS rows."""
import json
from collections import Counter
from datetime import datetime, timezone

from .. import db

KEEP = 12                    # entries kept a theme
ROWS_KEEP = 150              # rows kept in each list of an entry (the counts stay whole)
FREE_ROWS = 5                # rows of the latest entry a plan without the full log sees
REVENUE_SHARE = 0.02         # a revenue restated: moved by more than 2% for the same year
MARGIN_POINTS = 1.0          # a margin restated: moved by more than one percentage point for the same year
SHARE = 0.25                 # a layer's companies counted as going somewhere: at least a quarter of them (and at least one)
KINDS = ("removed", "added", "moved", "layers", "restated")      # an entry's lists, in the order a short view takes rows from
CAUSES = ("rules", "map", "refresh", "figures")
# cl48 (R47, the outside review's P1 "taxonomy coverage control": Consumer retail fell from 66 of 85 to 58 of 98 companies in informative
# layers when its universe changed, and nothing said so): a theme is flagged on its coverage and to the admins when the share of its placed
# companies in informative layers is under COVER_MIN per cent, or falls by COVER_FALL points or more against its previous live placement
COVER_MIN = 60
# e54 (R54): each company checked outside the figures' window kept with its evidence state (theme_data.EVIDENCE_STATES), one letter each, so
# the membership check moves on from one stored read to the next (theme_routes.membership_check)
EV_CODE = {"description_verified": "d", "industry_code_supported": "i", "list_supported": "l", "not_confirmed": "n", "membership_unverified": "u"}
EV_STATE = {v: k for k, v in EV_CODE.items()}
COVER_FALL = 5               # t56 (R55 review): a fall of 5 points or more is flagged (8 before), and said with why
FLAGS_KEY = "theme:coverage:flags"        # {key_of: {"name", "region", "problem" (None once it passes), "at"}}: the admins' alert (autofix)
FLAGS_KEEP = 200


def key_of(region: str, name: str) -> str:
    from .theme_data import slug
    from .theme_library import normalise
    return f"theme:changes:{region}:{slug(normalise(name, region) or name)}"


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) != float("inf") else None


def snapshot(dive: dict, members=(), stamp: float | int = 0, rules=None, everyone: dict | None = None) -> dict:
    """A stored read, as compared: {"layers": [names in order], "cos": {symbol: [name, layer index, year, revenue, margin, "e"|"n"]},
    "off": {symbol: [name, industry]} (dropped as another business), "map": the map's symbols, "stamp": the map's time, "rules"}.
    Each company in its first layer (a dive lists a company once).
    p57 (R56 review: Jyoti Resins, Picard Medical, Meghna Infracon and Infineon printed as removed, "no longer in the theme's map", and
    Sarepta as removed from Biotech, all still members, only past the largest companies whose figures are worked out): `everyone`,
    {symbol: [name, layer]} of every member of the theme's checked map, keeps each member outside the dive's companies too ("rest":
    {symbol: [name, index into "rest_layers"]}), so a company leaving the figures is never said to leave the theme."""
    layers, cos = [], {}
    for b in dive.get("layers") or []:
        name = str(b.get("layer") or "")
        if name in layers:
            continue
        layers.append(name)
        for c in b.get("companies") or []:
            s_ = c.get("symbol")
            if not s_ or s_ in cos:
                continue
            e, n = _num(c.get("ebitda")), _num(c.get("net"))
            cos[s_] = [str(c.get("name") or s_), len(layers) - 1, c.get("year"), _num(c.get("revenue")),
                       e if e is not None else n, "e" if e is not None else "n" if n is not None else ""]
    off = {o["ticker"]: [str(o.get("name") or o["ticker"]), str(o.get("industry") or "")]
           for o in ((dive.get("placements") or {}).get("off_industry") or []) if isinstance(o, dict) and o.get("ticker")}
    cv = dive.get("coverage") or {}
    cover = [int(cv["informative"]), int(cv["placed"])] if isinstance(cv, dict) and cv.get("placed") and cv.get("informative") is not None else None
    # d53: the companies an earlier version dropped as another business whose own words now keep them in (theme_base.place_rest "back")
    back = sorted(o["ticker"] for o in ((dive.get("placements") or {}).get("back") or []) if isinstance(o, dict) and o.get("ticker"))
    # d53: why each company is in the theme ("by": its official industry, the theme's list, the map from another industry), for the log
    why = {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            t = (c.get("theme") or {}) if isinstance(c.get("theme"), dict) else {}
            if c.get("symbol") and t.get("why"):
                why.setdefault(c["symbol"], str(t["why"])[:200])
    # c54: the named layers of the version before that a re-check would have lost, restored or with why not (theme_base.restore_vanished),
    # and the companies kept once as another symbol of the same company (theme_data.same_company), for the log
    gone = [x for x in ((dive.get("placements") or {}).get("layers_gone") or []) if isinstance(x, dict) and x.get("layer")]
    # c54: why a company is where it is when the placement said it (back by what a layer sells, or new to its layer on that evidence)
    mwhy = {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            r = c.get("refit") if isinstance(c.get("refit"), dict) else {}
            w = r.get("why") or c.get("sold_by")
            if c.get("symbol") and w:
                mwhy.setdefault(c["symbol"], str(w)[:240])
    dups = {str(x["symbol"]): str(x.get("kept_name") or x.get("kept") or "") for x in dive.get("duplicates") or [] if isinstance(x, dict) and x.get("symbol")}
    # t56: each company the map's check (or the theme's own scope) left out, with its reason: a business-membership decision, its listing
    # line said apart (theme_check.check_placements "dropped")
    left = {str(x["ticker"]): dropped_why(x) for x in ((dive.get("placements") or {}).get("dropped") or []) if isinstance(x, dict) and x.get("ticker")}
    mc = dive.get("membership_check") if isinstance(dive.get("membership_check"), dict) else {}
    ev = {s_: EV_CODE[x] for s_, x in (mc.get("outside") or {}).items() if x in EV_CODE}
    # h56 (R56): only the points with the evidence tally's counts ([day, checked, total, description-verified]) are kept
    from .theme_data import tally_points
    hist = tally_points(mc.get("history"))
    rest, rest_layers = {}, []
    for s_, x in (everyone or {}).items():
        if not s_ or s_ in cos or not isinstance(x, (list, tuple)) or len(x) < 2:
            continue
        lay = str(x[1] or "")
        if lay not in rest_layers:
            rest_layers.append(lay)
        rest[s_] = [str(x[0] or s_), rest_layers.index(lay)]
    return {"layers": layers, "cos": cos, "off": off, "map": sorted({s_ for s_ in members if s_}), "stamp": int(_num(stamp) or 0),
            **({"rest": rest, "rest_layers": rest_layers} if everyone is not None else {}),
            "rules": rules, "unit": dive.get("unit"), **({"cover": cover} if cover else {}), **({"back": back} if back else {}),
            **({"why": why} if why else {}), **({"gone": gone} if gone else {}), **({"dups": dups} if dups else {}),
            **({"mwhy": mwhy} if mwhy else {}), **({"ev": ev} if ev else {}), **({"ev_hist": hist} if hist else {}),
            **({"left": left} if left else {})}


BUSINESS, LISTING = "business membership: ", "listing: "


def dropped_why(x: dict) -> str:
    """t56 (R55 review: "Adyen's ADR removed from the universe without saying whether it's a listing-eligibility or business-membership
    decision"): why a company the check left out is no longer in the theme, its business-membership decision first, then its listing line
    said apart ("listing: ...") as what it is: no listing rule of the app removes a company."""
    groups = [str(g) for g in x.get("groups") or [] if g][:2]
    work = " or ".join(f"“{g}”" for g in groups) or "its group"
    whose = f" (read as {x['issuer']}'s)" if x.get("issuer") else ""
    said = x.get("said")
    if said == "scope":
        out = BUSINESS + str(x.get("scope") or "outside the theme's own scope")
    elif said == "unbacked":
        out = BUSINESS + f"the check's answer that it does the work of {work} is not backed by its own words{whose}, and the version before didn't have it as a member"
    elif x.get("words_name"):
        # p57: its own words use that group's terms: the check's answer is said as an answer, never as what its words don't show
        out = BUSINESS + f"the check's answer on its own words{whose} was no for {work}, though its words use that group's terms"
    else:
        out = BUSINESS + f"its own words{whose} were checked and don't show the work of {work}"
    if x.get("listing"):
        out += f"; {LISTING}{x['listing']}, which removes no company"
    return out


def off_memory(got: dict | None) -> dict:
    """d53 (R53, the owner's review of the live R52 Consumer retail deck: "an unrelated energy distributor can't re-enter Consumer Retail"):
    {symbol: [name, industry]} of every company an earlier stored version of the theme dropped as another business: the stored snapshot's
    "off", those kept from every snapshot before it ("off_ever", apply), and each logged removal for that reason (the last KEEP entries)."""
    got = got if isinstance(got, dict) else {}
    snap = got.get("snap") if isinstance(got.get("snap"), dict) else {}
    out: dict = {}
    for e in got.get("log") or []:
        for r in (e.get("removed") or []) if isinstance(e, dict) else []:
            if isinstance(r, dict) and r.get("symbol") and str(r.get("why") or "").startswith("another business"):
                ind = str(r["why"])[len("another business (filed under "):-1] if "(filed under " in str(r["why"]) else ""
                out[r["symbol"]] = [str(r.get("name") or r["symbol"]), ind]
    for k in ("off_ever", "off"):
        for s_, v in (snap.get(k) or {}).items() if isinstance(snap.get(k), dict) else []:
            out[s_] = list(v) if isinstance(v, list) else [s_, ""]
    for s_ in snap.get("back") or []:              # judged again on its own words and kept in: no longer held by the earlier finding
        out.pop(s_, None)
    return out


def move_memory(got: dict | None) -> dict:
    """c54 (R53 review, the live R53 Semiconductors deck: Intel and four more moved by a re-check from "Makers of their own products" into
    "Chip equipment and subsystem suppliers"): {symbol: [from, to]} of every move between layers the stored log keeps (its last KEEP
    entries), the latest of each company's, so the placement judges a company a re-check moved into a layer on what that layer sells
    (theme_base.sold_what) even once the move is in the stored snapshot."""
    got = got if isinstance(got, dict) else {}
    out: dict = {}
    for e in got.get("log") or []:
        for r in (e.get("moved") or []) if isinstance(e, dict) else []:
            if isinstance(r, dict) and r.get("symbol") and r.get("to"):
                out[r["symbol"]] = [str(r.get("from") or ""), str(r["to"])]
    return out


def lost_moves(got: dict | None) -> dict:
    """t56 (R55 review, the live R55 Metals and Consumer retail decks): {symbol: [from, to]} of the moves out of each layer the stored
    snapshot no longer has, made by the one re-check that removed it (the newest logged entry with moves out of it), so the version before
    the snapshot is read back exactly (theme_base.previous_published): the companies a re-check moved out of "Aluminium" when it lost it,
    never those an older re-check had moved out and a later version kept elsewhere."""
    got = got if isinstance(got, dict) else {}
    snap = got.get("snap") if isinstance(got.get("snap"), dict) else {}
    have = {str(x) for x in snap.get("layers") or []}
    out: dict = {}
    done: set = set()
    for e in reversed([e for e in got.get("log") or [] if isinstance(e, dict)]):
        here = set()
        for r in e.get("moved") or []:
            frm = str(r.get("from") or "") if isinstance(r, dict) else ""
            if frm and frm not in have and frm not in done and not frm.startswith("Other ") and r.get("symbol") and r.get("to"):
                out.setdefault(r["symbol"], [frm, str(r["to"])])
                here.add(frm)
        done |= here
    return out


# p57 (R56 review: Capital One, Sarepta (and in R55 Adyen) removed by a re-check under new placement rules whose only reason was the map
# check's answer on the same stored words that had kept them in the version before): a removal on a check's answer alone is no evidence
# against a published member, so such a company is still a published member of the layer it was removed from
WEAK_REMOVALS = ("were checked and don't show the work of", "is not backed by its own words", "no longer in the theme's map",
                 "the check's answer on its own words")


def published_members(got: dict | None) -> dict:
    """p57: {symbol: its layer in the published version} of every member of the stored version (the dive's companies, "cos", and every other
    member, "rest"), and of each company a re-check under new placement rules removed since the theme's map last changed on a check's
    answer alone (WEAK_REMOVALS), at the layer it was removed from: what the placement contract (theme_base.keep_published, hold_published,
    theme_check.check_placements `held`) keeps unless stronger evidence moves it. {} when nothing is stored."""
    got = got if isinstance(got, dict) else {}
    snap = got.get("snap") if isinstance(got.get("snap"), dict) else {}
    out: dict = {}
    entries = [e for e in got.get("log") or [] if isinstance(e, dict)]
    since = max((i for i, e in enumerate(entries) if e.get("cause") == "map"), default=-1)
    for e in entries[since + 1:]:
        if e.get("cause") != "rules":
            continue
        for r in e.get("removed") or []:
            if isinstance(r, dict) and r.get("symbol") and r.get("layer") and any(w in str(r.get("why") or "") for w in WEAK_REMOVALS):
                out[str(r["symbol"])] = str(r["layer"])
    layers = snap.get("layers") or []
    for s_, c in (snap.get("cos") or {}).items() if isinstance(snap.get("cos"), dict) else ():
        if isinstance(c, list) and len(c) > 1 and isinstance(c[1], int) and 0 <= c[1] < len(layers):
            out[s_] = str(layers[c[1]])
    for s_ in (snap.get("rest") or {}) if isinstance(snap.get("rest"), dict) else ():
        lay = rest_layer(snap, s_)
        if lay is not None:
            out[s_] = lay
    return out


def _layer_events(was: dict, now: dict) -> tuple[list[dict], set]:
    """(the layers renamed, split, merged, added or removed, the (from, to) pairs those events explain)."""
    old_names, new_names = was["layers"], now["layers"]
    gone = [x for x in old_names if x not in new_names]
    fresh = [x for x in new_names if x not in old_names]
    if not gone and not fresh:
        return [], set()
    # p57 (R56 audit: "added (0 companies)"): a layer's members past the figures count too
    members = lambda snap, name: ({s_ for s_, c in snap["cos"].items() if snap["layers"][c[1]] == name}      # noqa: E731
                                  | {s_ for s_ in (snap.get("rest") or {}) if rest_layer(snap, s_) == name})
    src = {g: members(was, g) for g in gone}
    dst = {d: members(now, d) for d in fresh}
    m = {(g, d): len(src[g] & dst[d]) for g in gone for d in fresh}
    dests = {g: [d for d in fresh if m[(g, d)] >= max(1, SHARE * len(src[g]))] for g in gone}
    srcs = {d: [g for g in gone if d in dests[g]] for d in fresh}
    out, used_g, used_d, pairs = [], set(), set(), set()
    for g in gone:
        if len(dests[g]) >= 2:
            out.append({"kind": "split", "from": [g], "to": dests[g], "n": len(src[g])})
            used_g.add(g)
            used_d.update(dests[g])
            pairs.update((g, d) for d in dests[g])
    for d in fresh:
        if d in used_d:
            continue
        joined = [g for g in srcs[d] if g not in used_g]
        if len(joined) >= 2:
            out.append({"kind": "merged", "from": joined, "to": [d], "n": len(dst[d])})
            used_g.update(joined)
            used_d.add(d)
            pairs.update((g, d) for g in joined)
    for g in gone:
        if g in used_g or len(dests[g]) != 1:
            continue
        d = dests[g][0]
        if d not in used_d and srcs[d] == [g]:
            out.append({"kind": "renamed", "from": [g], "to": [d], "n": m[(g, d)]})
            used_g.add(g)
            used_d.add(d)
            pairs.add((g, d))
    # c54 (R53 review): a removed layer says where its companies went ({layer: n}) and, when the placement listed it, why it was not kept
    went = lambda g: dict(Counter(now["layers"][now["cos"][s_][1]] if s_ in now["cos"] else "" for s_ in src[g]).most_common())      # noqa: E731
    why = {x.get("layer"): x.get("why") for x in now.get("gone") or [] if isinstance(x, dict)}
    out += [{"kind": "removed", "from": [g], "to": [], "n": len(src[g]), "went": went(g), **({"why": why[g]} if why.get(g) else {})}
            for g in gone if g not in used_g]
    out += [{"kind": "added", "from": [], "to": [d], "n": len(dst[d])} for d in fresh if d not in used_d and dst[d]]
    return out, pairs


def _why_removed(s_: str, now: dict, was: dict | None = None) -> str:
    if s_ in now["off"]:
        ind = now["off"][s_][1]
        return f"another business (filed under {ind})" if ind else "another business"
    if s_ in (now.get("dups") or {}):          # c54 (R53 review: ICICI Prudential Life "removed ... no figures stored for it")
        return f"the same company as {now['dups'][s_]}, listed under two symbols: kept once" if now["dups"][s_] else \
            "the same company as another listed under two symbols: kept once"
    if s_ in (now.get("left") or {}):          # t56: the map's check, or the theme's scope, left it out: its business-membership reason
        return now["left"][s_]
    if s_ in set(now["map"]):
        return "no figures stored for it"
    if was is not None and was.get("stamp") and now.get("stamp") and was["stamp"] != now["stamp"]:
        return BUSINESS + "the theme's new map doesn't name it"
    return "no longer in the theme's map"


def _moved_much(old, new, share: bool) -> bool:
    if old is None or new is None:
        return False
    if share:
        return abs(new - old) > REVENUE_SHARE * abs(old) if old else new != 0
    return abs(new - old) > MARGIN_POINTS


def rest_layer(snap: dict, s_: str):
    """p57: the layer of a member kept outside the dive's companies ("rest"), or None when the snapshot keeps no such member."""
    r = (snap.get("rest") or {}).get(s_) if isinstance(snap.get("rest"), dict) else None
    ls = snap.get("rest_layers") or []
    if isinstance(r, list) and len(r) > 1 and isinstance(r[1], int) and 0 <= r[1] < len(ls):
        return str(ls[r[1]])
    return None


OUTSIDE_FIGURES = "still in the theme, outside the largest companies whose figures are worked out"


def diff(was: dict, now: dict) -> dict:
    """What differs between two snapshots: {"counts": {kind: n}, kind: [rows]} for KINDS. Empty lists when nothing differs.
    p57: a member of either version kept outside the dive's companies ("rest") counts as a member: a company entering or leaving the
    figures is never said to join or leave the theme (only a change of its layer is said)."""
    lay_w, lay_n = was["layers"], now["layers"]
    events, pairs = _layer_events(was, now)
    added, removed, moved, restated = [], [], [], []
    for s_, c in now["cos"].items():
        old = was["cos"].get(s_)
        if old is None and rest_layer(was, s_) is not None:          # p57: a member before, outside the figures then
            a, b = rest_layer(was, s_), lay_n[c[1]]
            if a != b and (a, b) not in pairs:
                moved.append({"symbol": s_, "name": c[0], "from": a, "to": b})
            continue
        if old is None:
            # d53 (R53): every addition with why it is in the theme, and one an earlier version dropped as another business said so
            why = (now.get("why") or {}).get(s_) or ""
            if s_ in (was.get("off") or {}) or s_ in (was.get("off_ever") or {}):
                why = (why + "; " if why else "") + "an earlier version found its own words describe another business; its own words read now show the theme's work"
            added.append({"symbol": s_, "name": c[0], "layer": lay_n[c[1]], **({"why": why} if why else {})})
            continue
        a, b = lay_w[old[1]], lay_n[c[1]]
        if a != b and (a, b) not in pairs:
            mw = (now.get("mwhy") or {}).get(s_)          # c54: the placement's reason for where it is, when it gave one
            moved.append({"symbol": s_, "name": c[0], "from": a, "to": b, **({"why": mw} if mw else {})})
        if old[2] and old[2] == c[2]:
            rev = _moved_much(old[3], c[3], True)
            mar = old[5] == c[5] and _moved_much(old[4], c[4], False)
            if rev or mar:
                restated.append({"symbol": s_, "name": c[0], "year": c[2], "revenue": [old[3], c[3]], "margin": [old[4], c[4]],
                                 "measure": "EBITDA margin" if c[5] == "e" else "Net margin" if c[5] == "n" else "",
                                 "what": [k for k, on in (("revenue", rev), ("margin", mar)) if on]})
    for s_, c in was["cos"].items():
        if s_ not in now["cos"] and rest_layer(now, s_) is not None:      # p57: still a member, outside the figures now
            a, b = lay_w[c[1]], rest_layer(now, s_)
            if a != b and (a, b) not in pairs:
                moved.append({"symbol": s_, "name": c[0], "from": a, "to": b, "why": OUTSIDE_FIGURES})
            continue
        if s_ not in now["cos"]:
            removed.append({"symbol": s_, "name": c[0], "layer": lay_w[c[1]], "why": _why_removed(s_, now, was)})
    if isinstance(was.get("rest"), dict) and isinstance(now.get("rest"), dict):
        # p57: the members outside the figures in both versions: each that left the theme, joined it, or changed layer
        names_now = set(lay_n) | {str(x) for x in now.get("rest_layers") or []}
        for s_, r in was["rest"].items():
            if s_ in now["cos"] or not isinstance(r, list) or not r:
                continue
            a, b = rest_layer(was, s_), rest_layer(now, s_)
            if b is None:
                removed.append({"symbol": s_, "name": str(r[0]), "layer": a or "", "why": _why_removed(s_, now, was)})
            elif a != b and (a, b) not in pairs and a in names_now:
                moved.append({"symbol": s_, "name": str(r[0]), "from": a, "to": b, "why": OUTSIDE_FIGURES})
        for s_, r in now["rest"].items():
            if s_ in was["cos"] or s_ in was["rest"] or not isinstance(r, list) or not r:
                continue
            why = (now.get("why") or {}).get(s_) or ""
            added.append({"symbol": s_, "name": str(r[0]), "layer": rest_layer(now, s_) or "", **({"why": why} if why else {})})
    by_name = lambda r: str(r.get("name") or "").lower()          # noqa: E731
    out = {"removed": sorted(removed, key=by_name), "added": sorted(added, key=by_name), "moved": sorted(moved, key=by_name),
           "layers": events, "restated": sorted(restated, key=by_name)}
    out["counts"] = {k: len(out[k]) for k in KINDS}
    return out


def changed(d: dict) -> bool:
    return any(d["counts"].values())


def cause_of(was: dict, now: dict, refresh: bool) -> str:
    """Why the read was stored again: a re-check under new placement rules, a new map, a Refresh, else the companies' figures moving."""
    if was.get("rules") is not None and now.get("rules") is not None and was["rules"] != now["rules"]:
        return "rules"
    if was.get("stamp") and now.get("stamp") and was["stamp"] != now["stamp"]:
        return "map"
    return "refresh" if refresh else "figures"


def _entry(d: dict, cause: str, at: datetime) -> dict:
    return {"at": at.isoformat(timespec="seconds"), "d": at.date().isoformat(), "cause": cause, "counts": d["counts"],
            **{k: d[k][:ROWS_KEEP] for k in KINDS}}


def apply(cur: dict | None, now: dict, refresh: bool = False, at: datetime | None = None) -> dict:
    """The stored log with this read in: the snapshot replaced, and an entry added (the newest last, at most KEEP) when it differs from
    the snapshot before it. A theme's first read only keeps its snapshot."""
    cur = cur if isinstance(cur, dict) else {}
    log = [e for e in cur.get("log") or [] if isinstance(e, dict)]
    was = cur.get("snap")
    since = cur.get("since")
    at = at or datetime.now(timezone.utc)
    if isinstance(was, dict) and isinstance(was.get("cos"), dict) and isinstance(was.get("layers"), list):
        d = diff(was, now)
        if changed(d):
            log = (log + [_entry(d, cause_of(was, now, refresh), at)])[-KEEP:]
    if isinstance(was, dict):
        # d53: every company an earlier snapshot dropped as another business, kept from one snapshot to the next (off_memory), unless its
        # own words were read again and keep it in ("back")
        ever = {**(was.get("off_ever") if isinstance(was.get("off_ever"), dict) else {}), **(was.get("off") if isinstance(was.get("off"), dict) else {})}
        ever = {s_: v for s_, v in ever.items() if s_ not in set(now.get("back") or []) and s_ not in (now.get("off") or {})}
        if ever:
            now = {**now, "off_ever": ever}
    if isinstance(was, dict) and now.get("cover"):
        # cl48: the coverage before the last change of it, kept until it changes again (a read stored again unchanged keeps the fall said)
        if was.get("cover") and list(was["cover"]) != list(now["cover"]):
            now = {**now, "cover_was": list(was["cover"])}
        elif was.get("cover_was"):
            now = {**now, "cover_was": list(was["cover_was"])}
    return {"snap": now, "log": log, "since": since or at.date().isoformat()}


def record(region: str, name: str, dive: dict, members=(), stamp=0, rules=None, refresh: bool = False, at: datetime | None = None,
           everyone: dict | None = None) -> None:
    """Keep this read in the theme's log (atomically: two requests storing the same theme at once both land). Never raises. p57:
    `everyone`, every member of the theme's checked map ({symbol: [name, layer]}), kept with the snapshot (snapshot "rest")."""
    try:
        now = snapshot(dive, members, stamp, rules, everyone=everyone)
        if not now["cos"]:
            return
        db.update_setting(key_of(region, name), lambda cur: json.dumps(apply(db.json_value(cur, {}), now, refresh, at), ensure_ascii=False,
                                                                       separators=(",", ":"), default=str))
    except Exception as e:
        print("theme changes: not kept:", type(e).__name__, str(e)[:100])


def stored(region: str, name: str) -> dict:
    try:
        got = db.json_value(db.get_setting(key_of(region, name)), {})
    except Exception as e:
        print("theme changes: not read:", type(e).__name__, str(e)[:100])
        got = {}
    return got if isinstance(got, dict) else {}


def _short(e: dict, n: int) -> dict:
    """An entry with its first `n` rows in all, taken in KINDS order; "hidden" counts the rest."""
    out, left = {**e}, n
    for k in KINDS:
        rows = e.get(k) or []
        out[k] = rows[:max(0, left)]
        left -= len(out[k])
    out["hidden"] = sum(len(e.get(k) or []) for k in KINDS) - sum(len(out[k]) for k in KINDS)
    return out


def view(region: str, name: str, full: bool) -> dict:
    """The log as the page shows it, newest first: every entry (`full`), else the latest entry's counts and first FREE_ROWS rows, with
    how many older entries there are. "since": the day the theme's first read was kept."""
    got = stored(region, name)
    log = [e for e in got.get("log") or [] if isinstance(e, dict)][::-1]
    if full:
        return {"full": True, "since": got.get("since"), "entries": log, "older": 0}
    return {"full": False, "since": got.get("since"), "entries": [_short(log[0], FREE_ROWS)] if log else [], "older": max(0, len(log) - 1)}


def full_for(profile: dict | None) -> bool:
    """Whether this account sees the whole log (plans.py "theme_changes": Basic and up)."""
    from ..plans import allows, plan_of
    try:
        return allows(plan_of(profile or {}), "theme_changes")
    except Exception:
        return False


def served(region: str, name: str, dive: dict, profile: dict | None) -> dict:
    """The dive as one account gets it: with its theme's change log as that account's plan shows it ("changes"). The kept dive itself,
    the same for everyone, never holds it."""
    return {**dive, "changes": view(region, name, full_for(profile))}


def _share(n: int, of: int) -> int:
    return int(n * 100 / of + 0.5) if of else 0


LOST_MIN = 3                 # d53: a layer of the previous live read with this many companies or more gone, its companies taken by no new layer
ESTABLISHED = 5              # t56: a layer of the previous live read with this many companies or more is an established category: its removal is
                             # said wherever its companies went (theme_base.LOST_MIN, the taxonomy guard's own count)


def _no_business(name: str) -> bool:
    import re as _re
    return bool(_re.match(r"Other\b", name) or _re.search(r" \((?:larger|smaller)\)$", name))


def lost_layers(snap: dict | None, dive: dict | None) -> list[dict]:
    """d53 (R53, our deck reviewer: a re-check took Utilities' "Electrical cables" and "Heavy electrical equipment" layers away, 12 companies
    to "Other" and the rest to two halves of a split by market value, and only the coverage share was watched): the named layers of the
    previous live read (the stored snapshot) with LOST_MIN companies or more that the new read no longer has, at least half of whose
    companies now sit in its "Other" group or in a half of a layer split by market value (no business layer took them); t56 (R55 review:
    "warn whenever a taxonomy change eliminates an established category"): and every one of ESTABLISHED companies or more that no layer new
    to this read took (a quarter of its companies or more in one: renamed or split), wherever its companies went. [{"layer", "n", "went":
    {layer: count, "not in the theme now": count}}]."""
    if not isinstance(snap, dict) or not isinstance(snap.get("cos"), dict) or not isinstance(snap.get("layers"), list) or not isinstance(dive, dict):
        return []
    try:
        now = snapshot(dive)
    except Exception:
        return []
    old = set(snap["layers"])
    out = []
    for i, g in enumerate(snap["layers"]):
        if g in now["layers"] or _no_business(g):
            continue
        cos = [s_ for s_, c in snap["cos"].items() if isinstance(c, list) and len(c) > 1 and c[1] == i]
        went = [now["layers"][now["cos"][s_][1]] for s_ in cos if s_ in now["cos"]]
        new = Counter(x for x in went if x not in old and not _no_business(x))
        renamed = any(n >= max(1, SHARE * len(cos)) for n in new.values())
        lost = len(cos) >= LOST_MIN and went and sum(1 for x in went if _no_business(x)) * 2 >= len(went)
        if lost or (len(cos) >= ESTABLISHED and not renamed):
            where = dict(Counter(went))
            if len(went) < len(cos):
                where["not in the theme now"] = len(cos) - len(went)
            out.append({"layer": g, "n": len(cos), "went": where})
    return out


def fall_why(snap: dict | None, dive: dict | None) -> dict:
    """t56 (R55 review: "a theme whose informative-layer share falls" said with no reason): why the companies of an informative layer of the
    previous live read (the snapshot) are not in one now: {reason: count}, each company once: its layer gone, a rule moved it to "Other" by
    what its layer is (its "refit"), nothing of its own read yet, else it fit none of this read's layers; one no longer in the theme apart."""
    if not isinstance(snap, dict) or not isinstance(snap.get("cos"), dict) or not isinstance(snap.get("layers"), list) or not isinstance(dive, dict):
        return {}
    rows, layer_of = {}, {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            if c.get("symbol") and c["symbol"] not in rows:
                rows[c["symbol"]], layer_of[c["symbol"]] = c, str(b.get("layer") or "")
    names = set(layer_of.values())
    out: Counter = Counter()
    for s_, c in snap["cos"].items():
        if not (isinstance(c, list) and len(c) > 1 and isinstance(c[1], int) and 0 <= c[1] < len(snap["layers"])):
            continue
        was = snap["layers"][c[1]]
        if _no_business(was):
            continue
        if s_ not in rows:
            out["no longer in the theme"] += 1
            continue
        if not layer_of[s_].startswith("Other"):          # in a layer still (a half of a split one included): informative
            continue
        r = rows[s_]
        if was not in names:
            out[f"its layer “{was}” is gone"] += 1
        elif isinstance(r.get("refit"), dict):
            out["moved to “Other” by what its layer is (its own words and official industry don't say it)"] += 1
        elif r.get("unread"):
            out["nothing of its own read yet"] += 1
        else:
            out["fit none of this version's layers"] += 1
    return dict(out)


def coverage_control(cov: dict | None, snap: dict | None, dive: dict | None = None) -> dict | None:
    """cl48 (R47): the coverage control of a theme's read: {"low": share under COVER_MIN, "fell": {"informative", "placed", "share", "why"}
    of the previous live placement when the share now is COVER_FALL points or more under it (t56: "why", fall_why), "lost" (lost_layers),
    "restored", "guard" (theme_base.share_guard's row)}; None when none. `cov`: the read's coverage (theme_data.layer_coverage); `snap`: the
    theme's stored snapshot (the previous live read), whose coverage is the one compared, or, when the read is the same as it, the coverage
    before the last change (apply's "cover_was")."""
    if not isinstance(cov, dict) or not cov.get("placed"):
        return None
    now = [int(cov.get("informative") or 0), int(cov["placed"])]
    share = _share(*now)
    snap = snap if isinstance(snap, dict) else {}
    prev = snap.get("cover") if isinstance(snap.get("cover"), list) and len(snap["cover"]) == 2 else None
    base = prev if prev and list(prev) != now else snap.get("cover_was")
    out: dict = {}
    if share < COVER_MIN:
        out["low"] = True
    if isinstance(base, list) and len(base) == 2 and base[1] and _share(*base) - share >= COVER_FALL:
        out["fell"] = {"informative": int(base[0]), "placed": int(base[1]), "share": _share(*base)}
        why = fall_why(snap, dive)
        if why:
            out["fell"]["why"] = why
    lost = lost_layers(snap, dive)
    # c54 (R53 review): each lost layer with why the re-check didn't keep it, and each one it restored (theme_base.restore_vanished)
    pl = ((dive or {}).get("placements") or {}) if isinstance(dive, dict) else {}
    gone = [x for x in (pl.get("layers_gone") or []) if isinstance(x, dict) and x.get("layer")]
    why = {x["layer"]: x.get("why") for x in gone}
    if lost:
        out["lost"] = [{**x, **({"why": why[x["layer"]]} if why.get(x["layer"]) else {})} for x in lost]
    back = [{"layer": x["layer"], "before": int(x.get("before") or 0), "now": int(x.get("restored") or 0)} for x in gone if x.get("restored")]
    if back:
        out["restored"] = back
    if isinstance(pl.get("share_guard"), dict) and pl["share_guard"].get("returned"):      # t56: what the taxonomy guard sent back
        out["guard"] = {k: pl["share_guard"][k] for k in ("before", "now", "returned") if k in pl["share_guard"]}
    return out or None


def _went_said(went: dict) -> str:
    return ", ".join(f"{n:,} to “{w}”" if w != "not in the theme now" else f"{n:,} no longer in the theme"
                     for w, n in sorted((went or {}).items(), key=lambda kv: (-kv[1], kv[0])))


def control_line(cov: dict | None) -> str:
    """The coverage control in words, facts with both numbers (cl48): "" when the theme isn't flagged. t56: a fall says why ("Why: ..."),
    and a lost layer where its companies went."""
    ctl = (cov or {}).get("control") if isinstance(cov, dict) else None
    if not ctl:
        return ""
    n, of = int(cov.get("informative") or 0), int(cov.get("placed") or 0)
    share = _share(n, of)
    out = []
    if ctl.get("fell"):
        f = ctl["fell"]
        out.append(f"{n:,} of {of:,} companies placed ({share}%) are in informative layers, against {f['informative']:,} of "
                   f"{f['placed']:,} ({f['share']}%) in the previous live placement: {f['share'] - share} points fewer, a fall of "
                   f"{COVER_FALL} or more.")
        if f.get("why"):
            out.append("Why: " + "; ".join(f"{k_}: {v_:,}" for k_, v_ in sorted(f["why"].items(), key=lambda kv: (-kv[1], kv[0]))) + ".")
    if ctl.get("low"):
        out.append(f"{share}% of the companies placed are in informative layers ({n:,} of {of:,}), under {COVER_MIN}%.")
    if ctl.get("lost"):
        out.append("Layers of the previous live placement gone, their companies taken by no new layer: "
                   + ", ".join(f"“{x['layer']}” ({x['n']:,} companies" + (f": {_went_said(x['went'])}" if x.get("went") else "")
                               + (f"; {x['why']}" if x.get("why") else "") + ")" for x in ctl["lost"]) + ".")
    if ctl.get("restored"):
        out.append("Layers of the previous live placement a re-check would have lost, kept with their companies whose own words or official "
                   "industry still say what they sell: " + ", ".join(f"“{x['layer']}” ({x['now']:,} of its {x['before']:,})" for x in ctl["restored"]) + ".")
    if ctl.get("guard"):
        g = ctl["guard"]
        out.append(f"Companies of “Other” sent back to their layer of the previous version, their own words still saying what it sells: "
                   f"{int(g['returned']):,} (the same companies' share in informative layers {_share(*g['before'])}% before, "
                   f"{_share(*g['now'])}% now).")
    return " ".join(out)


def flag(region: str, name: str, cov: dict | None) -> None:
    """Keep the theme's coverage control for the admins' alert (cl48: theme_routes' autofix source, coverage_checks): its problem, or None once it passes.
    Never raises."""
    line = control_line(cov)
    k = key_of(region, name)

    def put(cur):
        got = db.json_value(cur, {})
        got = got if isinstance(got, dict) else {}
        if not line and k not in got:
            return None                   # nothing flagged, nothing to clear: left as it is
        got[k] = {"name": name, "region": region, "problem": line or None, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if len(got) > FLAGS_KEEP:
            for old in sorted(got, key=lambda x: str(got[x].get("at") or ""))[:len(got) - FLAGS_KEEP]:
                del got[old]
        return json.dumps(got, ensure_ascii=False, separators=(",", ":"))
    try:
        db.update_setting(FLAGS_KEY, put)
    except Exception as e:
        print("theme changes: coverage flag not kept:", type(e).__name__, str(e)[:100])


def flags() -> dict:
    try:
        got = db.json_value(db.get_setting(FLAGS_KEY), {})
    except Exception as e:
        print("theme changes: coverage flags not read:", type(e).__name__, str(e)[:100])
        got = {}
    return got if isinstance(got, dict) else {}
