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
COVER_FALL = 8
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


def snapshot(dive: dict, members=(), stamp: float | int = 0, rules=None) -> dict:
    """A stored read, as compared: {"layers": [names in order], "cos": {symbol: [name, layer index, year, revenue, margin, "e"|"n"]},
    "off": {symbol: [name, industry]} (dropped as another business), "map": the map's symbols, "stamp": the map's time, "rules"}.
    Each company in its first layer (a dive lists a company once)."""
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
    return {"layers": layers, "cos": cos, "off": off, "map": sorted({s_ for s_ in members if s_}), "stamp": int(_num(stamp) or 0),
            "rules": rules, "unit": dive.get("unit"), **({"cover": cover} if cover else {}), **({"back": back} if back else {}),
            **({"why": why} if why else {})}


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


def _layer_events(was: dict, now: dict) -> tuple[list[dict], set]:
    """(the layers renamed, split, merged, added or removed, the (from, to) pairs those events explain)."""
    old_names, new_names = was["layers"], now["layers"]
    gone = [x for x in old_names if x not in new_names]
    fresh = [x for x in new_names if x not in old_names]
    if not gone and not fresh:
        return [], set()
    members = lambda snap, name: {s_ for s_, c in snap["cos"].items() if snap["layers"][c[1]] == name}      # noqa: E731
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
    out += [{"kind": "removed", "from": [g], "to": [], "n": len(src[g])} for g in gone if g not in used_g]
    out += [{"kind": "added", "from": [], "to": [d], "n": len(dst[d])} for d in fresh if d not in used_d]
    return out, pairs


def _why_removed(s_: str, now: dict) -> str:
    if s_ in now["off"]:
        ind = now["off"][s_][1]
        return f"another business (filed under {ind})" if ind else "another business"
    if s_ in set(now["map"]):
        return "no figures stored for it"
    return "no longer in the theme's map"


def _moved_much(old, new, share: bool) -> bool:
    if old is None or new is None:
        return False
    if share:
        return abs(new - old) > REVENUE_SHARE * abs(old) if old else new != 0
    return abs(new - old) > MARGIN_POINTS


def diff(was: dict, now: dict) -> dict:
    """What differs between two snapshots: {"counts": {kind: n}, kind: [rows]} for KINDS. Empty lists when nothing differs."""
    lay_w, lay_n = was["layers"], now["layers"]
    events, pairs = _layer_events(was, now)
    added, removed, moved, restated = [], [], [], []
    for s_, c in now["cos"].items():
        old = was["cos"].get(s_)
        if old is None:
            # d53 (R53): every addition with why it is in the theme, and one an earlier version dropped as another business said so
            why = (now.get("why") or {}).get(s_) or ""
            if s_ in (was.get("off") or {}) or s_ in (was.get("off_ever") or {}):
                why = (why + "; " if why else "") + "an earlier version found its own words describe another business; its own words read now show the theme's work"
            added.append({"symbol": s_, "name": c[0], "layer": lay_n[c[1]], **({"why": why} if why else {})})
            continue
        a, b = lay_w[old[1]], lay_n[c[1]]
        if a != b and (a, b) not in pairs:
            moved.append({"symbol": s_, "name": c[0], "from": a, "to": b})
        if old[2] and old[2] == c[2]:
            rev = _moved_much(old[3], c[3], True)
            mar = old[5] == c[5] and _moved_much(old[4], c[4], False)
            if rev or mar:
                restated.append({"symbol": s_, "name": c[0], "year": c[2], "revenue": [old[3], c[3]], "margin": [old[4], c[4]],
                                 "measure": "EBITDA margin" if c[5] == "e" else "Net margin" if c[5] == "n" else "",
                                 "what": [k for k, on in (("revenue", rev), ("margin", mar)) if on]})
    for s_, c in was["cos"].items():
        if s_ not in now["cos"]:
            removed.append({"symbol": s_, "name": c[0], "layer": lay_w[c[1]], "why": _why_removed(s_, now)})
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


def record(region: str, name: str, dive: dict, members=(), stamp=0, rules=None, refresh: bool = False, at: datetime | None = None) -> None:
    """Keep this read in the theme's log (atomically: two requests storing the same theme at once both land). Never raises."""
    try:
        now = snapshot(dive, members, stamp, rules)
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


def lost_layers(snap: dict | None, dive: dict | None) -> list[dict]:
    """d53 (R53, our deck reviewer: a re-check took Utilities' "Electrical cables" and "Heavy electrical equipment" layers away, 12 companies
    to "Other" and the rest to two halves of a split by market value, and only the coverage share was watched): the named layers of the
    previous live read (the stored snapshot) with LOST_MIN companies or more that the new read no longer has, at least half of whose
    companies now sit in its "Other" group or in a half of a layer split by market value (no business layer took them): [{"layer", "n"}]."""
    if not isinstance(snap, dict) or not isinstance(snap.get("cos"), dict) or not isinstance(snap.get("layers"), list) or not isinstance(dive, dict):
        return []
    try:
        now = snapshot(dive)
    except Exception:
        return []
    import re as _re
    no_business = lambda name: bool(_re.match(r"Other\b", name) or _re.search(r" \((?:larger|smaller)\)$", name))      # noqa: E731
    out = []
    for i, g in enumerate(snap["layers"]):
        if g in now["layers"] or no_business(g):
            continue
        cos = [s_ for s_, c in snap["cos"].items() if isinstance(c, list) and len(c) > 1 and c[1] == i]
        went = [now["layers"][now["cos"][s_][1]] for s_ in cos if s_ in now["cos"]]
        if len(cos) >= LOST_MIN and went and sum(1 for x in went if no_business(x)) * 2 >= len(went):
            out.append({"layer": g, "n": len(cos)})
    return out


def coverage_control(cov: dict | None, snap: dict | None, dive: dict | None = None) -> dict | None:
    """cl48 (R47): the coverage control of a theme's read: {"low": share under COVER_MIN, "fell": {"informative", "placed", "share"} of the
    previous live placement when the share now is COVER_FALL points or more under it}; None when neither. `cov`: the read's coverage
    (theme_data.layer_coverage); `snap`: the theme's stored snapshot (the previous live read), whose coverage is the one compared, or, when
    the read is the same as it, the coverage before the last change (apply's "cover_was")."""
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
    lost = lost_layers(snap, dive)
    if lost:
        out["lost"] = lost
    return out or None


def control_line(cov: dict | None) -> str:
    """The coverage control in words, facts with both numbers (cl48): "" when the theme isn't flagged."""
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
    if ctl.get("low"):
        out.append(f"{share}% of the companies placed are in informative layers ({n:,} of {of:,}), under {COVER_MIN}%.")
    if ctl.get("lost"):
        out.append("Layers of the previous live placement gone, their companies taken by no new layer: "
                   + ", ".join(f"“{x['layer']}” ({x['n']:,} companies)" for x in ctl["lost"]) + ".")
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
