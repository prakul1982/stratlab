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
import re
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


def clip_words(text, n: int) -> str:
    """r64e (the live R63 decks' change logs: "and “Additionally, Ferroglobe currently has (i) quart)", "nothing of “Makers of thei)",
    "Policybazaar and Paisab"): a stored reason kept to `n` characters ends on a whole word, with an ellipsis, and closes a quote it opened."""
    s = str(text or "")
    if len(s) <= n:
        return s
    cut = s[:n - 2]
    sp = cut.rfind(" ")
    if sp > n // 2:
        cut = cut[:sp]
    cut = cut.rstrip(" ,;:(“‘—-")
    # r66e (the live R65 US metals deck, p.11: "“ready-mix concrete and asphalt) and…”"): never ended on a joining word
    while (j := _JOINS.search(cut)):
        cut = cut[:j.start()].rstrip(" ,;:(“‘—-")
    return cut + ("…”" if cut.count("“") > cut.count("”") else "…")


# (r69e, the live R67 US metals deck p.8: "… custom smelters”, and “the…”": a joining word just after an opening quote is one too)
_JOINS = re.compile(r"[\s,;:(–\-“‘\"]+(?:and|or|of|the|a|an|for|in|to|with|by|on|at|from|its|their|as|&)$", re.I)


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
                why.setdefault(c["symbol"], clip_words(t["why"], 200))
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
                mwhy.setdefault(c["symbol"], clip_words(w, 240))
    dups = {str(x["symbol"]): str(x.get("kept_name") or x.get("kept") or "") for x in dive.get("duplicates") or [] if isinstance(x, dict) and x.get("symbol")}
    kept_layers = {str(b["layer"]): clip_words(b["single_kept"], 200) for b in dive.get("layers") or [] if b.get("layer") and b.get("single_kept")}
    # t56: each company the map's check (or the theme's own scope) left out, with its reason: a business-membership decision, its listing
    # line said apart (theme_check.check_placements "dropped")
    left = {str(x["ticker"]): dropped_why(x) for x in ((dive.get("placements") or {}).get("dropped") or []) if isinstance(x, dict) and x.get("ticker")}
    mc = dive.get("membership_check") if isinstance(dive.get("membership_check"), dict) else {}
    ev = {s_: EV_CODE[x] for s_, x in (mc.get("outside") or {}).items() if x in EV_CODE}
    # h56 (R56): only the points with the evidence tally's counts ([day, checked, total, description-verified]) are kept
    from .theme_data import tally_points
    hist = tally_points(mc.get("history"))
    rest, rest_layers, rest_why, rest_mwhy = {}, [], {}, {}
    for s_, x in (everyone or {}).items():
        if not s_ or s_ in cos or not isinstance(x, (list, tuple)) or len(x) < 2:
            continue
        lay = str(x[1] or "")
        if lay not in rest_layers:
            rest_layers.append(lay)
        rest[s_] = [str(x[0] or s_), rest_layers.index(lay)]
        if len(x) > 2 and x[2]:
            rest_why[s_] = clip_words(x[2], 200)
        if len(x) > 3 and x[3]:
            rest_mwhy[s_] = clip_words(x[3], 240)          # r67e: the placement's reason for its layer
    # r68e (R68): the core-and-adjacent split and the rules' version it is of, so a company that joins or leaves the core members is named
    # (population_change); a dive of an older engine keeps none
    adj = {str(x["symbol"]): str(x.get("kind") or "") for x in dive.get("adjacent") or [] if isinstance(x, dict) and x.get("symbol")}
    pop = {"pop": dive["population_rule"], "adj": adj} if isinstance(dive.get("population_rule"), int) else {}
    return {"layers": layers, "cos": cos, "off": off, "map": sorted({s_ for s_ in members if s_}), "stamp": int(_num(stamp) or 0), **pop,
            **({"rest": rest, "rest_layers": rest_layers} if everyone is not None else {}), **({"rest_why": rest_why} if rest_why else {}),
            **({"rest_mwhy": rest_mwhy} if rest_mwhy else {}),
            "rules": rules, "unit": dive.get("unit"), **({"cover": cover} if cover else {}), **({"back": back} if back else {}),
            **({"why": why} if why else {}), **({"gone": gone} if gone else {}), **({"dups": dups} if dups else {}),
            **({"mwhy": mwhy} if mwhy else {}), **({"ev": ev} if ev else {}), **({"ev_hist": hist} if hist else {}),
            **({"left": left} if left else {}), **({"kept_layers": kept_layers} if kept_layers else {})}


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


def moved_why(layer: str, syms, now: dict) -> str:
    """r66e (the live R65 Fertilizers deck, p.7: "“Commodity chemicals” removed (18 companies: 18 to “Other fertilizers and agrochemical
    companies”)" with no reason, while each of its companies' moves said why the layer was not made): a removed layer the placement gave no
    reason for takes the one reason its companies' moves out of it all give ("mwhy"), said of the layer; "" when they give none or several."""
    mw = now.get("mwhy") if isinstance(now.get("mwhy"), dict) else {}
    said = {str(mw[s_]) for s_ in syms if mw.get(s_)}
    if len(said) != 1:
        return ""
    r = said.pop()
    head = f"“{layer}” "
    if not r.startswith(head):
        return ""                  # a reason of the company's own, not of the layer
    return clip_words("it " + r[len(head):].replace(": listed in the theme's", ": its companies listed in the theme's"), 220)


def _layer_events(was: dict, now: dict) -> tuple[list[dict], set]:
    """(the layers renamed, split, merged, added or removed, the (from, to) pairs those events explain)."""
    # r67e (P0-3, "pure renames not reported as moves"): a layer whose members are all past the figures is a layer too, renamed or not
    # ("Other" past the figures: only its rename pairs its members' moves away, below)
    rest_of = lambda snap: [str(x) for x in snap.get("rest_layers") or [] if str(x) not in snap["layers"]]      # noqa: E731
    old_names = list(was["layers"]) + [x for x in rest_of(was) if not _no_business(x)]
    new_names = list(now["layers"]) + [x for x in rest_of(now) if not _no_business(x)]
    o_gone = [x for x in rest_of(was) if _no_business(x) and x not in now["layers"] and x not in rest_of(now)]
    o_new = [x for x in rest_of(now) if _no_business(x) and x not in was["layers"] and x not in rest_of(was)]
    gone = [x for x in old_names if x not in new_names]
    fresh = [x for x in new_names if x not in old_names]
    if len(o_gone) == 1 and len(o_new) == 1 and o_gone[0].startswith("Other") and o_new[0].startswith("Other"):
        o_pair = {(o_gone[0], o_new[0])}                 # r67e: the "Other" group past the figures renamed: its members not moved
    else:
        o_pair = set()
    if not gone and not fresh:
        return [], o_pair
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
    # r571 (the live R57 Software deck: 7 companies of "Ad-funded platforms and online games" printed as 7 moves into "Consumer internet,
    # games and advertising", a layer new to it): a new layer most of whose companies come from one layer that stays was split off it,
    # said once, its companies' moves explained by it
    kept_names = set(old_names) & set(new_names)
    for d in fresh:
        if d in used_d or not dst[d]:
            continue
        came = Counter(was["layers"][was["cos"][s_][1]] if s_ in was["cos"] else rest_layer(was, s_) for s_ in dst[d])
        src_, k_ = (came.most_common(1) or [(None, 0)])[0]
        if src_ in kept_names and not str(src_).startswith("Other ") and k_ >= 2 and k_ * 2 >= len(dst[d]):
            out.append({"kind": "split", "from": [src_], "to": [src_, d], "n": k_})
            used_d.add(d)
            pairs.add((src_, d))
    # c54 (R53 review): a removed layer says where its companies went ({layer: n}) and, when the placement listed it, why it was not kept
    # r58 (the owner's review of the live R57.2 Textiles deck: "185 companies: 163 out of the theme", while all 325 were in it before and
    # after): a company past the figures count is still in the theme, in the layer the snapshot's rest says (rest_layer)
    went = lambda g: dict(Counter(now["layers"][now["cos"][s_][1]] if s_ in now["cos"] else (rest_layer(now, s_) or "")      # noqa: E731
                                  if s_ in (now.get("rest") or {}) else "" for s_ in src[g]).most_common())
    why = {x.get("layer"): x.get("why") for x in now.get("gone") or [] if isinstance(x, dict)}
    out += [{"kind": "removed", "from": [g], "to": [], "n": len(src[g]), "went": went(g),
             **({"why": why[g]} if why.get(g) else {"why": moved_why(g, src[g], now)} if moved_why(g, src[g], now) else {})}
            for g in gone if g not in used_g]
    # r581 (the live R58 Insurance deck: "“Distribution and aggregation” added (1 company)", a layer of an earlier published version kept
    # with its one member): a layer the placement kept from the published version says so ("back")
    kept_l = now.get("kept_layers") if isinstance(now.get("kept_layers"), dict) else {}
    out += [{"kind": "added", "from": [], "to": [d], "n": len(dst[d]), **({"back": str(kept_l[d])} if kept_l.get(d) else {})}
            for d in fresh if d not in used_d and dst[d]]
    return out, pairs | o_pair


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


def _rest_move(now: dict, s_: str, name: str, a: str, b: str) -> dict:
    """r67e (the owner's review of the live R65 decks, P0: "every move between informative layers and Other has an auditable reason"; Biotech's
    106 moves out of "Other" said only OUTSIDE_FIGURES): a move of a member past the figures with the placement's own reason for where it is
    (its map record's, snapshot "rest_mwhy"), else none here (the log's reader says what its own words say, reasoned); "outside" marks it."""
    mw = (now.get("rest_mwhy") or {}).get(s_) or (now.get("mwhy") or {}).get(s_)
    return {"symbol": s_, "name": name, "from": a, "to": b, "outside": True, **({"why": mw} if mw else {})}


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
                mw = (now.get("mwhy") or {}).get(s_)
                moved.append({"symbol": s_, "name": c[0], "from": a, "to": b, **({"why": mw} if mw else {})})
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
                moved.append(_rest_move(now, s_, c[0], a, b))
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
                moved.append(_rest_move(now, s_, str(r[0]), a, b))
        for s_, r in now["rest"].items():
            if s_ in was["cos"] or s_ in was["rest"] or not isinstance(r, list) or not r:
                continue
            # r62 (the live R60 Biotech deck: "added 3: Genenta Science S.p.A., Vicore Pharma Holding AB, Windward Bio Group AG" with no
            # reason, three members outside the figures): a member outside the figures says why it is in the theme too, as its map's
            # record gives it (member_why)
            why = (now.get("why") or {}).get(s_) or (now.get("rest_why") or {}).get(s_) or ""
            added.append({"symbol": s_, "name": str(r[0]), "layer": rest_layer(now, s_) or "", **({"why": why} if why else {})})
    # r63e (the live R62 Biotech deck: "added 1: InMed Pharmaceuticals Inc. ...; removed 1: InMed Pharmaceuticals Inc." in one change, one
    # company kept under one of its two symbols): an addition and a removal of one name in one change are that company under another
    # symbol: no addition or removal, a move only when its layer changed
    key_ = lambda r: re.sub(r"[^a-z0-9]+", " ", str(r.get("name") or "").lower()).strip()      # noqa: E731
    gone_ = {}
    for r in removed:
        gone_.setdefault(key_(r), []).append(r)
    for r in list(added):
        twin = (gone_.get(key_(r)) or [None])[0] if key_(r) else None
        if twin is None or twin["symbol"] == r["symbol"]:
            continue
        gone_[key_(r)].remove(twin)
        added.remove(r)
        removed.remove(twin)
        if twin.get("layer") and r.get("layer") and twin["layer"] != r["layer"] and (twin["layer"], r["layer"]) not in pairs:
            moved.append({"symbol": r["symbol"], "name": r["name"], "from": twin["layer"], "to": r["layer"],
                          "why": f"listed under {r['symbol']} now, {twin['symbol']} before"})
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
    if isinstance(was, dict) and isinstance(was.get("pop"), int) and isinstance(now.get("pop"), int):
        # r68e: the split before the last change of it, kept until it changes again (a read stored again unchanged keeps the change said)
        if dict(was.get("adj") or {}) != dict(now.get("adj") or {}):
            now = {**now, "adj_was": [was["pop"], dict(was.get("adj") or {})]}
        elif was.get("adj_was"):
            now = {**now, "adj_was": was["adj_was"]}
    now = {k: v for k, v in now.items() if k not in ("rest_why", "rest_mwhy")}           # r62, r67e: read for this entry's reasons, never stored
    return {"snap": now, "log": log, "since": since or at.date().isoformat()}


def member_why(c: dict, layer: str) -> str:
    """r62: why a member of the checked map is in the theme, from its map record: brought in by its official industry (basis "industry"), else
    named by the map in its layer; with whether its own words are checked yet."""
    ind = str(c.get("industry") or "").strip()
    why = (f"filed under its official industry, {ind}, one of the theme's" if c.get("basis") == "industry" and ind else
           f"the theme's map places it in “{layer}”" if layer else "")
    if why and c.get("verified") is not True and not c.get("what"):
        why += "; its own words are not checked yet"
    return why


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


# r572 (R57.2, the live R57.1 decks: "ADOBE INC., INTUIT INC., Salesforce, Inc. (no longer in the theme's map)" in Semiconductors, Citi and
# UBS in Payments, SBI Cards in Automotive, 20 companies in Capital goods): a company that left the theme with no reason but the map's not
# naming it any more has that said as a business-membership decision, with what its own stored words say it does (their first sentence) or,
# with none stored, the official industry its filings give; "another business" when those words say nothing of the theme's own business
UNNAMED = ("no longer in the theme's map", BUSINESS + "the theme's new map doesn't name it")
QUOTE_MAX = 200


_VERB_END = re.compile(r"\s(?:and|or|of|the|a|an|in|to|with|for|by|is|are|was|its|their|manufactures|makes|sells|produces|provides|offers|"
                       r"supplies|operates|designs|develops|distributes|markets|engaged)$", re.I)


def first_sentence(words) -> str:
    """The first sentence of a company's own words (its industry line left out), at most QUOTE_MAX characters, cut at a clause."""
    text = re.sub(r"^\s*Industry:[^.]*\.\s*", "", str(words or "")).strip()
    if not text or text.startswith("From its own filings:"):
        return ""
    # r66e (LIVE12A-006: BigBloc's move "its own words say “Incorporated in 2015, BigBloc Construction Ltd manufactures”", cut before what it
    # manufactures): a heading a profile glues on ends the sentence before it, its founding-history opening is left off, and a cut never
    # ends on the verb or joining word before what the company makes
    from .theme_base import _HEADING, _HISTORY
    text = " ".join(_HEADING.sub(". ", text).split()).lstrip(". ")
    text = _HISTORY.sub("", text, count=1).strip() or text
    # r581 (the live R58 Automotive deck: SBI Cards' quote ran past "... registered with the RBI." into "The Company is engaged in issuing
    # credit cards to", and the deck's reader took the full stop inside the quote for the end of the reason): a sentence ends after an
    # acronym of capitals too ("RBI."), never after one letter's ("U.S.")
    one = re.split(r"(?:(?<=[a-z0-9)”\"])|(?<=[A-Z]{2}))\.\s+(?=[A-Z])", text, maxsplit=1)[0].strip().rstrip(".")
    if len(one) > QUOTE_MAX:
        cut = max(one.rfind(", ", 0, QUOTE_MAX), one.rfind("; ", 0, QUOTE_MAX))
        one = one[:cut] if cut > 40 and not _VERB_END.search(one[:cut]) else one[:one.rfind(" ", 0, QUOTE_MAX)]
        while _VERB_END.search(one) and " " in one:
            one = one[:one.rfind(" ")]
    # r58 (the live R57.2 Automotive deck: SBI Cards' removal "(business membership: ...; its own words say “SBI Cards and Payment Services
    # Limited (...) is ...”)", a bracket inside the reason's own bracket, read as the reason): an aside in brackets is left out of the quote
    one = re.sub(r"\s*\([^()]*\)", "", one)
    return one.strip(" ,;:").replace("“", "‘").replace("”", "’").replace("(", "").replace(")", "")


def unnamed_why(why: str, words=None, industry: str = "", theme_words: set | None = None) -> str:
    """r572: a removal's reason with what its own words or filings say, when its reason was only that the map no longer names it."""
    if why not in UNNAMED:
        return why
    base = BUSINESS + ("the theme's new map doesn't name it" if why.startswith(BUSINESS) else "the theme's map no longer names it")
    quote = first_sentence(words)
    if quote:
        from .theme_base import kind_stems
        if theme_words and not (kind_stems(quote) & theme_words):
            return f"another business: its own words say “{quote}”"
        return f"{base}; its own words say “{quote}”"
    if industry:
        return f"{base}; filed under {industry}"
    return base


def reasoned(entries: list, words_of=None, industry_of=None, theme_words: set | None = None) -> list:
    """r572: the log's entries with each removal whose only reason is the map's no longer naming it said with its own words (unnamed_why)."""
    # (r67e: with no reader of its words, each move still gets a reason, below; a removal's stands as kept)
    def why(r):
        if (words_of is None and industry_of is None) or not isinstance(r, dict) or r.get("why") not in UNNAMED or not r.get("symbol"):
            return r
        try:
            w = words_of(r["symbol"]) if words_of is not None else None
            ind = (industry_of(r["symbol"]) if industry_of is not None else "") or ""
        except Exception:
            w, ind = None, ""
        return {**r, "why": unnamed_why(r["why"], w, ind, theme_words)}

    def move_why(r):
        # round 2 (the live R57.1 decks: General Dynamics, Bilibili, Sphere and Creative Eye moved between layers with no reason printed):
        # a move with no reason of the placement's says what its own words or filings say; a move between two halves of one layer is that
        # layer's split by market value
        if not isinstance(r, dict) or not r.get("symbol"):
            return r
        if r.get("why") == OUTSIDE_FIGURES:            # r67e: a log kept before: where it sits is no reason for its move
            r = {**{k: x for k, x in r.items() if k != "why"}, "outside": True}
        if r.get("why"):
            return r
        a, b = _HALF_NAME.sub("", str(r.get("from") or "")), _HALF_NAME.sub("", str(r.get("to") or ""))
        if a == b:
            return {**r, "why": "the same layer, split into halves by market value"}
        try:
            w = words_of(r["symbol"]) if words_of is not None else None
            ind = (industry_of(r["symbol"]) if industry_of is not None else "") or ""
        except Exception:
            w, ind = None, ""
        q = first_sentence(w)
        said = f"its own words say “{q}”" if q else f"filed under {ind}" if ind else ""
        if not said:
            # r67e (P0-3): never a move with no reason: one with no words of its own stored and no industry says so
            said = ("no words of its own are stored, so none says a named layer's work" if str(b).startswith("Other ") else
                    f"no words of its own are stored; the theme's map places it in “{b}”")
        return {**r, "why": said}
    return [{**e, **({"removed": [why(r) for r in e.get("removed") or []]} if e.get("removed") else {}),
             **({"moved": [move_why(r) for r in e.get("moved") or []]} if e.get("moved") else {})} for e in entries]


def view(region: str, name: str, full: bool, words_of=None, industry_of=None) -> dict:
    """The log as the page shows it, newest first: every entry (`full`), else the latest entry's counts and first FREE_ROWS rows, with
    how many older entries there are. "since": the day the theme's first read was kept. r572: `words_of` / `industry_of`, a company's stored
    words and official industry, say why a company the map no longer names left (reasoned)."""
    got = stored(region, name)
    log = [e for e in got.get("log") or [] if isinstance(e, dict)][::-1]
    tw = None
    if words_of is not None or industry_of is not None:
        from .theme_base import kind_stems
        snap = got.get("snap") if isinstance(got.get("snap"), dict) else {}
        tw = kind_stems(" ".join([str(name)] + [str(x) for x in snap.get("layers") or [] if not str(x).startswith("Other ")]))
    log = reasoned(log, words_of, industry_of, tw)          # r67e: every move with its reason, whatever reads its words
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


def served(region: str, name: str, dive: dict, profile: dict | None, words_of=None, industry_of=None) -> dict:
    """The dive as one account gets it: with its theme's change log as that account's plan shows it ("changes"). The kept dive itself,
    the same for everyone, never holds it."""
    return {**dive, "changes": view(region, name, full_for(profile), words_of=words_of, industry_of=industry_of)}


def _share(n: int, of: int) -> int:
    return int(n * 100 / of + 0.5) if of else 0


_HALF_NAME = re.compile(r" \((?:larger|smaller)\)$")
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
        # r572 round 2 (the live R57.1 Media deck: "Content production and music rights" (30 companies: 14 to its "(smaller)" half, 13 to its
        # "(larger)" half) printed as gone, taken by no new layer): a layer most of whose companies went to the two halves of one layer split by
        # market value was split, never lost: said as a split
        halves = Counter(_HALF_NAME.sub("", x) for x in went if _HALF_NAME.search(x))
        base, k = (halves.most_common(1) or [("", 0)])[0]
        if base and k * 2 > len(cos) and (base == _HALF_NAME.sub("", g) or not {base, f"{base} (larger)", f"{base} (smaller)"} & old):
            out.append({"layer": g, "n": len(cos), "halves": [f"{base} (larger)", f"{base} (smaller)"]})
            continue
        lost = len(cos) >= LOST_MIN and went and sum(1 for x in went if _no_business(x)) * 2 >= len(went)
        if lost or (len(cos) >= ESTABLISHED and not renamed):
            where = dict(Counter(went))
            if len(went) < len(cos):
                where["not in the theme now"] = len(cos) - len(went)
            out.append({"layer": g, "n": len(cos), "went": where})
    return out


def fall_why(snap: dict | None, dive: dict | None, everyone: dict | None = None) -> dict:
    """t56 (R55 review: "a theme whose informative-layer share falls" said with no reason): why the companies of an informative layer of the
    previous live read (the snapshot) are not in one now: {reason: count}, each company once: its layer gone, a rule moved it to "Other" by
    what its layer is (its "refit"), nothing of its own read yet, else it fit none of this read's layers; one no longer in the theme apart.
    r65e (the live R64 Biotech deck: "400 of 821 ... against 459 of 821 ...: 7 points fewer ... Why: moved to “Other” by what its layer is
    ...: 4; no longer in the theme: 1", 5 companies said of a fall of 59, the others past the figures' window): with `everyone` ({symbol:
    {"layer", "refit", "unread"}} of every member of this read's map), the members the snapshot keeps outside its figures' window ("rest")
    are counted the same way."""
    if not isinstance(snap, dict) or not isinstance(snap.get("cos"), dict) or not isinstance(snap.get("layers"), list) or not isinstance(dive, dict):
        return {}
    from .theme_data import FOREIGN_KIND
    rows, layer_of = {}, {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            if c.get("symbol") and c["symbol"] not in rows:
                rows[c["symbol"]], layer_of[c["symbol"]] = c, str(b.get("layer") or "")
    # (only against a snapshot that keeps its members past the window: one that doesn't would read each of them as new to the theme)
    everyone = everyone if isinstance(everyone, dict) and isinstance(snap.get("rest"), dict) else None
    for s_, x in (everyone or {}).items():
        if s_ not in rows and isinstance(x, dict):
            rows[s_], layer_of[s_] = x, str(x.get("layer") or "")
    names = set(layer_of.values())
    out: Counter = Counter()
    was_of = {}
    for s_, c in snap["cos"].items():
        if isinstance(c, list) and len(c) > 1 and isinstance(c[1], int) and 0 <= c[1] < len(snap["layers"]):
            was_of[s_] = snap["layers"][c[1]]
    if everyone is not None:
        for s_ in snap["rest"]:
            if s_ not in was_of and rest_layer(snap, s_):
                was_of[s_] = rest_layer(snap, s_)
    for s_, was in was_of.items():
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
    # r58 (R58, the owner's review of the live R57.2 decks: Payments 90% -> 83% and Media US 89% -> 82% with the fall unsaid, two companies
    # kept in "Other" on their own words): a fall can come from companies new to the theme placed in "Other", the count it is a share of
    # growing, not from any company leaving a layer; and a core member now shown apart as an adjacent participant. Each said with its count
    rest = snap.get("rest") if isinstance(snap.get("rest"), dict) else {}
    for s_, c in rows.items():
        if s_ in snap["cos"] or s_ in rest:
            continue
        if layer_of[s_].startswith("Other"):
            out["new to the theme, placed in “Other” (the count of companies placed grew; no company left a layer for it)"] += 1
    for s_, c in snap["cos"].items():
        if s_ in rows and rows[s_].get("adjacent") and isinstance(c, list) and len(c) > 1:
            # fix20: a company based abroad is no other kind of business (theme_data.FOREIGN_KIND)
            far = isinstance(rows[s_]["adjacent"], dict) and rows[s_]["adjacent"].get("kind") == FOREIGN_KIND
            out[f"now an adjacent participant ({'listed in the US but based abroad' if far else 'another kind of business'}), shown apart from "
                "the core members"] += 1
    return dict(out)


def population_change(snap: dict | None, dive: dict | None) -> dict | None:
    """r68e (R68, the owner's review of the live R66 Payments deck: 16 -> 21 core members with figures, the card issuers, consumer lenders
    and digital banks folded into the core, none named): the companies that joined or left the theme's core members against the stored read
    before (its snapshot's split, or the split before its last change when the read is the same as it), each with why: {"rule": [was, now]
    when the core-and-adjacent rules' version changed, "left": [{"symbol", "name", "kind", "why"}] (now adjacent participants), "joined":
    [{"symbol", "name", "was", "why"}] (now core members)}; None when nothing moved or the stored read keeps no split (an older engine's)."""
    from .theme_data import ADJACENT_WHERE, FOREIGN_KIND, HOLDING_KIND, POPULATION_RULE
    if not isinstance(snap, dict) or not isinstance(dive, dict) or not isinstance(snap.get("pop"), int) or not isinstance(dive.get("population_rule"), int):
        return None
    now_adj = {str(x["symbol"]): x for x in dive.get("adjacent") or [] if isinstance(x, dict) and x.get("symbol")}
    was_pop, was_adj = snap["pop"], dict(snap.get("adj") or {})
    if {k: str(v.get("kind") or "") for k, v in now_adj.items()} == was_adj and isinstance(snap.get("adj_was"), list) and len(snap["adj_was"]) == 2:
        was_pop, was_adj = snap["adj_was"][0], dict(snap["adj_was"][1] or {})
    rows = {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            if c.get("symbol"):
                rows.setdefault(str(c["symbol"]), c)
    members_was = set(snap.get("cos") or {}) | set(snap.get("rest") or {}) if isinstance(snap.get("rest"), dict) else set(snap.get("cos") or {})
    rule = [was_pop, dive["population_rule"]] if was_pop != dive["population_rule"] else None
    ruled = (f"; the core-and-adjacent rules changed (version {was_pop} to {dive['population_rule']}: "
             f"{POPULATION_RULE.get(dive['population_rule'], '')})") if rule else ""
    left, joined = [], []
    for s_, x in sorted(now_adj.items(), key=lambda kv: str(kv[1].get("name") or "")):
        if s_ in was_adj or s_ not in members_was:          # (a company new to the theme is an addition, not a move out of the core)
            continue
        # fix20 (the R75 decks: "is of listed in the US, based abroad"): a company based abroad, or a holding company of other members, said
        # as what it is, never as a principal business "of" it
        why_ = ("it is listed in the US but based abroad" + (f": it {x['text']}" if x.get("text") else "")) if x.get("kind") == FOREIGN_KIND else \
            (f"it is a holding company of other members ({ADJACENT_WHERE['holding']}: “{x.get('text') or ''}”)") if x.get("kind") == HOLDING_KIND else \
            (f"its principal business ({ADJACENT_WHERE.get(x.get('where'), 'its official industry')}, “{x.get('text') or ''}”) is of {x.get('kind')}")
        left.append({"symbol": s_, "name": str(x.get("name") or s_), "kind": str(x.get("kind") or ""), "why": why_ + ruled})
    for s_, kind in sorted(was_adj.items()):
        if s_ in now_adj or s_ not in rows:
            continue
        c = rows[s_]
        ind = str(c.get("official_industry") or c.get("map_industry") or "").strip()
        why = c.get("core_kept") or ("its official industry" + (f" ({ind})" if ind else "") + " and its principal business, as read now, "
                                     "name no other kind of business than the theme's")
        joined.append({"symbol": s_, "name": str(c.get("name") or s_), "was": kind, "why": why + ruled})
    joined.sort(key=lambda r: r["name"].lower())
    if not left and not joined:
        return None
    return {**({"rule": rule} if rule else {}), "left": left, "joined": joined}


def moved_out_why(dive: dict | None) -> dict:
    """r60 (R60, the live R59 Defence and Insurance decks: "86% ... against 91%" and "80% ... against 93% in the previous live placement",
    the fall said with no reason: the snapshot compared was already the new placement, so fall_why found no company that left a layer): the
    companies of "Other" a rule moved there from a layer, each with its reason printed, counted by the layer they left: {reason: count}."""
    out: Counter = Counter()
    for b in (dive or {}).get("layers") or [] if isinstance(dive, dict) else []:
        if not str(b.get("layer") or "").startswith("Other"):
            continue
        for c in b.get("companies") or []:
            r = c.get("refit") if isinstance(c.get("refit"), dict) else {}
            frm = str(r.get("from") or "")
            if frm and not frm.startswith("Other") and r.get("why"):
                out[f"moved to “Other” from “{frm}” by a rule of the placement (each one's reason in the change log)"] += 1
    return dict(out)


def coverage_control(cov: dict | None, snap: dict | None, dive: dict | None = None, everyone: dict | None = None) -> dict | None:
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
        why = fall_why(snap, dive, everyone) or moved_out_why(dive)
        if why:
            out["fell"]["why"] = why
    found = lost_layers(snap, dive)
    lost = [x for x in found if not x.get("halves")]
    split = [x for x in found if x.get("halves")]          # r572 round 2: split into halves by market value, said as a split
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
    if out and split:              # (a split alone flags nothing: it is said beside a flag)
        out["split"] = [{"layer": x["layer"], "n": x["n"], "halves": x["halves"]} for x in split]
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
    if ctl.get("split"):
        out.append("Layers of the previous live placement split by market value: " + ", ".join(
            f"“{x['layer']}” ({x['n']:,} companies) split into “{x['halves'][0]}” and “{x['halves'][1]}”" for x in ctl["split"]) + ".")
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
