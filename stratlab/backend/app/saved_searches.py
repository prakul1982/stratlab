"""Saved searches: a search or filter set a person wants again, kept on their account (R19, owner 7 Nov: "in themes make option to save the
search and give option in them then to update it ... also check where all this is applicable").

One mechanism for every page that has one: each saved search has a `kind` (KINDS: the page it opens on and the parameters it may keep), a
name, the page's own parameters (a theme's words and market, the red-flag filters) and a small snapshot of what the search showed when it was
last read. "Update" reads the search again through the page's normal endpoint (the browser does that, so the read follows the page's own
cache rules: no extra AI call while a fresh read is kept) and sends the new snapshot here; the answer says what changed since the saved read:
rows added and removed, and the key figures' moves. Facts only.

Storage, the app's per-user settings pattern (watchlist:, screens:user:): one small row per person with the list
(saved:user:<uid> = {"items": [...]}) and one row per saved search with its snapshot (saved:snap:<uid>:<id>), so reading the list never
reads the snapshots. Bounded: LIMIT saved searches a person, ROWS_MAX rows a snapshot. Nothing runs in the background."""
import json
import math
import re
import secrets
import threading
from datetime import datetime, timezone

from . import db

KEY = "saved:user:"               # saved:user:<uid> = {"items": [{id, kind, name, params, saved_at, read_at, figures, rows}]}
SNAP = "saved:snap:"              # saved:snap:<uid>:<id> = {"rows": {key: [label, value]}, "figures": {name: number}}
# the same on every plan: a saved search costs a small stored row and nothing else (no background read, no message); saved stock screens
# have plan limits because each can send a weekly note
LIMIT = 25
MAX_NAME = 80
ROWS_MAX = 600                    # rows a snapshot keeps (a theme's companies, a filter's filings); the largest by value when there are more
LABEL_MAX = 80
FIGURES_MAX = 12
LIST_MAX = 50                     # added or removed rows an answer lists (the counts say how many in all)
MOVES_MAX = 10                    # rows whose value moved the most, in an answer
_ID = re.compile(r"^[0-9a-f]{12}\Z")
_FIG = re.compile(r"^[a-z][a-z0-9_]{0,23}\Z")
_ROW = re.compile(r"^[A-Za-z0-9&._:\-]{1,64}\Z")
REGION = ("IN", "US")

# kind -> {param: (max length, allowed values or None)}; "required": params a search of the kind can't be without
KINDS: dict[str, dict] = {
    "theme": {"label": "Theme", "path": "/research/themes", "required": ("q", "region"),
              "params": {"q": (80, None), "region": (2, REGION)}},
    "filings": {"label": "Red-flag filings", "path": "/research/filings", "required": ("region",),
                "params": {"region": (2, REGION), "view": (4, ("all", "mine")), "flag": (200, None), "range": (6, None),
                           "frm": (10, None), "to": (10, None), "q": (60, None)}},
    # AI reads (owner, 7 Nov: "they can also save their ai reads"): the read itself stays in the app's shared store; a saved one keeps where
    # it is and when it was written, and opens the stored read
    "company_ai": {"label": "Company AI read", "path": "/research/{region}/{symbol}", "required": ("region", "symbol"), "ai": True,
                   "params": {"region": (2, REGION), "symbol": (24, None)}},
    "compare": {"label": "Two companies compared", "path": "/research/compare", "required": ("region", "a", "b"), "ai": True,
                "params": {"region": (2, REGION), "a": (24, None), "b": (24, None)}},
    # a deep dive draws on the plan's monthly deep dives: Update opens its page, whose own button reads it again
    "deep_dive": {"label": "Deep dive", "path": "/research/{region}/{symbol}/deep", "required": ("region", "symbol"), "ai": True, "open_only": True,
                  "params": {"region": (2, REGION), "symbol": (24, None)}},
}
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&._\-]{0,23}\Z")
SYMBOLS = ("symbol", "a", "b")


class SavedError(ValueError):
    """A saved search that can't be kept as sent; the message says why in plain words."""


class LimitReached(Exception):
    pass


_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def valid_id(sid: str) -> bool:
    return bool(_ID.match(str(sid or "")))


def _read(uid: str) -> list[dict]:
    try:
        row = db.json_value(db.get_setting(KEY + uid), {})
    except Exception:
        row = {}
    items = row.get("items") if isinstance(row, dict) else None
    return [x for x in items if isinstance(x, dict) and valid_id(x.get("id")) and x.get("kind") in KINDS] if isinstance(items, list) else []


def _write(uid: str, items: list[dict]) -> None:
    db.set_setting(KEY + uid, json.dumps({"items": items}, separators=(",", ":")))


def _snap_key(uid: str, sid: str) -> str:
    return f"{SNAP}{uid}:{sid}"


def snapshot(uid: str, sid: str) -> dict | None:
    got = db.json_value(db.get_setting(_snap_key(uid, sid)), {})
    return got or None


def clean_name(name) -> str:
    n = re.sub(r"\s+", " ", str(name or "")).strip()[:MAX_NAME]
    if not n:
        raise SavedError("Give the search a name.")
    return n


def clean_params(kind: str, params) -> dict:
    """The page parameters a kind keeps, as short strings; anything else is dropped. The words are kept as typed (spaces folded)."""
    if kind not in KINDS:
        raise SavedError("That kind of search can't be saved.")
    spec = KINDS[kind]
    raw = params if isinstance(params, dict) else {}
    out = {}
    for k, (most, allowed) in spec["params"].items():
        v = raw.get(k)
        if v is None:
            continue
        v = re.sub(r"\s+", " ", str(v)).strip()
        if k == "region" or k in SYMBOLS:
            v = v.upper()
        if not v:
            continue
        if len(v) > most or (allowed and v not in allowed) or (k in SYMBOLS and not SYMBOL.match(v)):
            raise SavedError("The search's filters aren't ones the page uses.")
        out[k] = v
    for k in spec["required"]:
        if k not in out:
            raise SavedError("The search is missing what it is for." if k != "q" else "Type a theme to save.")
    if kind == "theme" and len(out["q"]) < 2:
        raise SavedError("Type a theme to save.")
    return out


def _num(v) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) and abs(v) < 1e16 else None


def clean_snap(snap) -> dict | None:
    """{"rows": {key: [label, value or None]}, "figures": {name: number or None}}, bounded; None when nothing was sent."""
    if snap is None:
        return None
    if not isinstance(snap, dict):
        raise SavedError("The search's read couldn't be kept.")
    rows_in = snap.get("rows") if isinstance(snap.get("rows"), dict) else {}
    rows = []
    for k, v in rows_in.items():
        if not _ROW.match(str(k)):
            continue
        label, value = (v[0] if v else "", v[1] if len(v) > 1 else None) if isinstance(v, (list, tuple)) else (v, None)
        rows.append((str(k), str(label or k)[:LABEL_MAX], _num(value)))
    if len(rows) > ROWS_MAX:              # the largest by value stay; a row without one sorts last
        rows.sort(key=lambda r: -(r[2] if r[2] is not None else -1e18))
        rows = rows[:ROWS_MAX]
    figs_in = snap.get("figures") if isinstance(snap.get("figures"), dict) else {}
    figures = {str(k): _num(v) for k, v in list(figs_in.items())[:FIGURES_MAX] if _FIG.match(str(k))}
    return {"rows": {k: [label, value] for k, label, value in rows}, "figures": figures, "cut": len(rows_in) > ROWS_MAX}


def _pct(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return round((b - a) / abs(a) * 100, 1)


def changes(old: dict | None, new: dict) -> dict | None:
    """What changed from the saved read to the new one: rows added and removed (largest by value first, LIST_MAX of each with the counts),
    each key figure before and after, and the rows in both whose value moved the most. None when there was no saved read to compare."""
    if not old:
        return None
    o, n = old.get("rows") or {}, new.get("rows") or {}
    order = lambda rows: sorted(rows, key=lambda r: (-(r["value"] if r["value"] is not None else -1e18), r["key"]))  # noqa: E731
    added = order([{"key": k, "label": v[0], "value": v[1]} for k, v in n.items() if k not in o])
    removed = order([{"key": k, "label": v[0], "value": v[1]} for k, v in o.items() if k not in n])
    moves = []
    for k, v in n.items():
        if k in o and o[k][1] and v[1] is not None and (p := _pct(o[k][1], v[1])) is not None and p != 0:
            moves.append({"key": k, "label": v[0], "before": o[k][1], "after": v[1], "pct": p})
    moves.sort(key=lambda m: (-abs(m["pct"]), m["key"]))
    of, nf = old.get("figures") or {}, new.get("figures") or {}
    figures = [{"name": k, "before": of.get(k), "after": nf.get(k), "change": (nf[k] - of[k]) if of.get(k) is not None and nf.get(k) is not None else None,
                "pct": _pct(of.get(k), nf.get(k))} for k in list(dict.fromkeys([*of, *nf]))]
    return {"added": added[:LIST_MAX], "added_count": len(added), "removed": removed[:LIST_MAX], "removed_count": len(removed),
            "moves": moves[:MOVES_MAX], "figures": figures, "same": not added and not removed and not moves and all(f["change"] in (0, None) for f in figures)}


def view(item: dict) -> dict:
    spec = KINDS[item["kind"]]
    p = item.get("params") or {}
    path = spec["path"].replace("{region}", p.get("region", "")).replace("{symbol}", p.get("symbol", ""))
    query = {k: v for k, v in p.items() if "{" + k + "}" not in spec["path"]}
    return {**item, "kind_label": spec["label"], "path": path, "query": query, "ai": bool(spec.get("ai")), "open_only": bool(spec.get("open_only"))}


def items(uid: str, kind: str | None = None) -> list[dict]:
    return [view(x) for x in _read(uid) if kind is None or x["kind"] == kind]


def _summary(snap: dict | None) -> dict:
    return {"figures": (snap or {}).get("figures") or {}, "rows": len((snap or {}).get("rows") or {})} if snap else {"figures": {}, "rows": None}


def add(uid: str, kind: str, name, params, snap=None, limit: int = LIMIT) -> tuple[dict, bool]:
    """Keep a search (with its read when one is sent); (the item, whether it is new). The same kind with the same parameters is the one
    already kept, so a second click never makes a copy."""
    p = clean_params(kind, params)
    nm = clean_name(name)
    s = clean_snap(snap)
    with _lock:
        mine = _read(uid)
        same = next((x for x in mine if x["kind"] == kind and x.get("params") == p), None)
        if same:
            return view(same), False
        if len(mine) >= limit:
            raise LimitReached(limit)
        now = _now()
        item = {"id": secrets.token_hex(6), "kind": kind, "name": nm, "params": p, "saved_at": now, "read_at": now if s else None, **_summary(s)}
        if s:
            db.set_setting(_snap_key(uid, item["id"]), json.dumps(s, separators=(",", ":")))
        _write(uid, mine + [item])
        return view(item), True


def rename(uid: str, sid: str, name) -> dict | None:
    nm = clean_name(name)
    with _lock:
        mine = _read(uid)
        item = next((x for x in mine if x["id"] == sid), None)
        if item is None:
            return None
        item["name"] = nm
        _write(uid, mine)
        return view(item)


def update(uid: str, sid: str, snap) -> tuple[dict, dict | None] | None:
    """The search read again: its new snapshot kept, and what changed since the one before (None the first time). None when it's gone."""
    s = clean_snap(snap)
    if s is None:
        raise SavedError("The search's read couldn't be kept.")
    with _lock:
        mine = _read(uid)
        item = next((x for x in mine if x["id"] == sid), None)
        if item is None:
            return None
        diff = changes(snapshot(uid, sid), s)
        db.set_setting(_snap_key(uid, sid), json.dumps(s, separators=(",", ":")))
        item.update(read_at=_now(), **_summary(s))
        _write(uid, mine)
        return view(item), diff


def remove(uid: str, sid: str) -> bool:
    with _lock:
        mine = _read(uid)
        keep = [x for x in mine if x["id"] != sid]
        if len(keep) == len(mine):
            return False
        _write(uid, keep)
    db.delete_setting(_snap_key(uid, sid))
    return True


def usage(uid: str) -> dict:
    """How many saved searches and reads the person keeps, and how many they can (Settings -> Your usage)."""
    return {"count": len(_read(uid)), "limit": LIMIT}


def forget(uid: str) -> int:
    """Every saved search of the person's and its snapshot (Account -> Delete all my data); how many there were."""
    n = len(_read(uid))
    for key, _ in db.all_settings_with_prefix(f"{SNAP}{uid}:"):
        db.delete_setting(key)
    db.delete_setting(KEY + uid)
    return n


def export(uid: str) -> list[dict]:
    """The person's saved searches for "Download all my data" (the list; the snapshots are what the pages showed)."""
    return _read(uid)


def counts_by_kind() -> dict:
    """For Admin: how many saved searches there are of each kind and how many people keep any (no names, no words)."""
    kinds = {k: 0 for k in KINDS}
    people = 0
    for key, raw in db.all_settings_with_prefix(KEY):
        row = db.json_value(raw, {})
        got = [x for x in (row.get("items") if isinstance(row, dict) else None) or [] if isinstance(x, dict) and x.get("kind") in KINDS]
        if got:
            people += 1
        for x in got:
            kinds[x["kind"]] += 1
    return {"kinds": kinds, "total": sum(kinds.values()), "people": people}
