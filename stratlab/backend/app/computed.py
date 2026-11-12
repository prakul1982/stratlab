"""One shared store for results that are the same for everyone (R19, owner 7 Nov: "make these saved in a single place ... apply this
globally too wherever possible").

A result (an AI read, a theme's read, a theme's dive, a company's figures as a theme used them) is worked out once and kept here for
every user: `get(kind, key)` gives it back, `put(kind, key, value)` keeps it. Nothing expires on its own (owner, 7 Nov: "dont do
automatically ... data doesn't change that often so we can reuse it"): a stored result is served, however old, until someone presses
Refresh (`refresh_gate`: a guard window per kind and a daily cap per person) or the owner refreshes or removes it in Admin → Library.
A rules change is a new key (the caller puts its rules version in the key, and VERSIONS below adds the code versions a kind's caller
doesn't name), so nothing worked out under old rules is served.

Where: app_settings under "cres:" (a market prefix: on Railway's market database once MARKET_DATABASE_URL is set, else the main one),
one row a result and one index row a kind ("cres:idx:<kind>": each entry's label, market, size, when, hits and refreshes, and the kind's
totals). A result over ENTRY_MAX isn't kept; nothing else is removed on its own (owner, 7 Nov: "we'll see how to manage the storage
later"): each entry's size and every kind's total are recorded and shown in Admin → Library, where the owner removes entries. Hit counts
are added up in this process and written into the index at most every FLUSH_EVERY seconds (a few numbers; no job of its own)."""
import hashlib
import json
import threading
import time
from datetime import datetime, timezone

from . import db

PREFIX = "cres:"
INDEX = "cres:idx:"
ENTRY_MAX = 600 * 1024              # bytes: a result bigger than this isn't kept (a theme's read is about 60-150 KB)
LABELS = {"ai:company": "Company AI reads", "ai:compare": "Head-to-head AI reads", "ai:ideas": "Search box: idea answers",
          "ai:ask": "Search box: questions", "ai:sector": "Theme maps (AI)", "ai:sector_claims": "Theme tailwinds and risks (checked)",
          "ai:sector_checked3": "Theme membership (checked)", "ai:pulse": "Market mood: headline reads", "theme": "Theme library",
          "theme:dive": "Theme figures (dives)", "theme:facts": "Company figures used by themes",
          "theme:news": "Theme headlines and filings", "theme:listings": "Theme new listings (checked)",
          "deck:theme": "Theme decks (PDF and PowerPoint files)", "theme:place": "Theme companies placed in the map's layers",
          "sector:metrics": "Sector operating figures from filings (banks, insurers, US companies)"}
# what one hit saves: (seconds of work, AI calls), rough figures from the reads' own timings, for Admin's estimate
SAVES = {"ai:company": (25, 1), "ai:compare": (20, 1), "ai:ideas": (15, 1), "ai:ask": (15, 1), "ai:sector": (45, 1),
         "ai:sector_claims": (30, 1), "ai:sector_checked3": (120, 12), "ai:pulse": (20, 1), "theme": (180, 14), "theme:dive": (8, 0),
         "theme:facts": (0.2, 0), "theme:news": (12, 0), "theme:listings": (20, 1), "deck:theme": (8, 0), "theme:place": (25, 1),
         "sector:metrics": (5, 0)}
HOUR = 3600
GUARD = {"ai:pulse": 300}           # a Refresh within this long of the last one gives the stored result ("already fresh")
DEFAULT_GUARD = 6 * HOUR
FLUSH_EVERY = 300
PLAN_WORDS = ("free", "basic", "pro", "admin")

_lock = threading.Lock()
_pending: dict = {}                 # kind -> {"hits": n, "misses": n, "by": {hkey: n}, "last": {hkey: time}}
_flushed = [time.time()]


def hkey(key) -> str:
    """A key's short name: its JSON, hashed."""
    return hashlib.sha1(json.dumps(key, sort_keys=True, default=str).encode(), usedforsecurity=False).hexdigest()[:24]


def _row(kind: str, hk: str) -> str:
    return f"{PREFIX}{kind}:{hk}"


def _deck_versions() -> list:
    """What a kept theme deck is made from, by version: the membership rules, the deck's own layout and words, the dive's sentences and the
    sector figures' rules."""
    from . import deck
    from .intel import sector_metrics, theme_base, theme_data
    return [theme_base.RULES, deck.THEME_DECK_VERSION, theme_data.DIVE_TEXT, sector_metrics.VERSION]


# A kind whose result depends on code versions its caller's key doesn't all name: those versions are put in the key here, so nothing worked
# out under older code is served after a deploy (lane upd1: a theme deck's key named the rules' and the deck's versions but not the dive's
# sentences or the sector figures' rules, so a deploy that changed only those served the day's deck made before it, from the store, all day).
# Each entry also keeps the versions it was made under (meta "versions"), for Admin -> Library's "not served" note.
VERSIONS = {"deck:theme": _deck_versions}


def versions(kind: str) -> list | None:
    """The code versions a kind's results are kept under now (VERSIONS), or None for a kind whose caller's key says it all."""
    fn = VERSIONS.get(kind)
    return fn() if fn else None


def _keyed(kind: str, key):
    v = versions(kind)
    return key if v is None else {"key": key, "versions": v}


def _now() -> float:
    return time.time()


def _count(kind: str, hk: str | None) -> None:
    with _lock:
        p = _pending.setdefault(kind, {"hits": 0, "misses": 0, "by": {}, "last": {}})
        if hk is None:
            p["misses"] += 1
        else:
            p["hits"] += 1
            p["by"][hk] = p["by"].get(hk, 0) + 1
            p["last"][hk] = _now()


def get(kind: str, key, count: bool = True) -> dict | None:
    """The stored entry ({"value", "at", "label", "region", "meta"}) or None. Never raises: an unreachable store is a miss."""
    hk = hkey(_keyed(kind, key))
    try:
        e = db.json_value(db.get_setting(_row(kind, hk)), {})
    except Exception as ex:
        print("computed: not read:", kind, type(ex).__name__, str(ex)[:100])
        e = {}
    ok = bool(e) and "value" in e
    if count:
        _count(kind, hk if ok else None)
        flush()
    return {**e, "hk": hk} if ok else None


def get_hk(kind: str, hk: str) -> dict | None:
    """An entry by its short name (Admin's "Open"), not counted as a hit."""
    try:
        e = db.json_value(db.get_setting(_row(kind, hk)), {})
    except Exception:
        return None
    return {**e, "hk": hk} if e and "value" in e else None


def _index(raw) -> dict:
    ix = db.json_value(raw, {})
    ix.setdefault("entries", {})
    for k in ("hits", "misses", "refreshes"):
        ix.setdefault(k, 0)
    ix.setdefault("by", {})
    return ix


def _apply_pending(ix: dict, p: dict | None) -> None:
    if not p:
        return
    ix["hits"] += p["hits"]
    ix["misses"] += p["misses"]
    for hk, n in p["by"].items():
        e = ix["entries"].get(hk)
        if e is not None:
            e["hits"] = e.get("hits", 0) + n
            e["last"] = max(e.get("last") or 0, p["last"].get(hk) or 0)


def _take(kind: str) -> dict | None:
    with _lock:
        return _pending.pop(kind, None)


def flush(force: bool = False) -> None:
    """Write the hit counts added up here into each kind's index, at most every FLUSH_EVERY seconds (or now, `force`)."""
    if not force and _now() - _flushed[0] < FLUSH_EVERY:
        return
    _flushed[0] = _now()
    with _lock:
        kinds = list(_pending)
    for kind in kinds:
        p = _take(kind)
        if not p:
            continue
        try:
            db.update_setting(INDEX + kind, lambda cur, p=p: json.dumps(_merged(cur, p), separators=(",", ":")))
        except Exception as ex:
            print("computed: hits not written:", kind, type(ex).__name__, str(ex)[:100])


def _merged(cur, p) -> dict:
    ix = _index(cur)
    _apply_pending(ix, p)
    return ix


def put(kind: str, key, value, label: str = "", region: str = "", meta: dict | None = None, by: str | None = None) -> dict | None:
    """Keep `value` for everyone under (kind, key), replacing what was there. `by`: a Refresh asked by someone on this plan
    ("free", "basic", "pro", "admin"), counted (in aggregate) in the index. Returns the index entry, or None when not kept."""
    hk, at = hkey(_keyed(kind, key)), _now()
    v = versions(kind)
    if v is not None:
        meta = {**(meta or {}), "versions": v}
    try:
        text = json.dumps({"value": value, "at": at, "label": str(label)[:120], "region": region, "meta": meta or {}},
                          ensure_ascii=False, default=str, separators=(",", ":"))
    except (TypeError, ValueError) as ex:
        print("computed: not kept (not JSON):", kind, str(ex)[:100])
        return None
    if len(text) > ENTRY_MAX:
        print("computed: not kept (too big):", kind, len(text))
        return None
    entry: dict = {}

    def change(cur):
        nonlocal entry
        ix = _index(cur)
        _apply_pending(ix, p)
        old = ix["entries"].get(hk) or {}
        entry = {"label": str(label)[:120], "region": region, "size": len(text), "at": at, "first": old.get("first") or at,
                 "hits": old.get("hits", 0), "last": old.get("last") or at, "refreshes": old.get("refreshes", 0) + (1 if by else 0),
                 "meta": {k: v for k, v in (meta or {}).items() if k in ("aliases", "members", "q", "searched", "rules", "gate", "versions")}}
        ix["entries"][hk] = entry
        if by:
            ix["refreshes"] += 1
            ix["by"][by] = ix["by"].get(by, 0) + 1
        return json.dumps(ix, separators=(",", ":"))
    p = _take(kind)
    try:
        db.set_setting(_row(kind, hk), text)
        db.update_setting(INDEX + kind, change)
    except Exception as ex:
        print("computed: not kept:", kind, type(ex).__name__, str(ex)[:100])
        return None
    return {**entry, "hk": hk}


def touch(kind: str, hk: str, **meta) -> None:
    """Change an index entry's meta (a theme's aliases, its times searched)."""
    def change(cur):
        ix = _index(cur)
        e = ix["entries"].get(hk)
        if e is None:
            return None
        e.setdefault("meta", {}).update(meta)
        return json.dumps(ix, separators=(",", ":"))
    try:
        db.update_setting(INDEX + kind, change)
    except Exception as ex:
        print("computed: index not changed:", kind, type(ex).__name__, str(ex)[:100])


def remove(kind: str, hk: str) -> bool:
    """Remove one entry (Admin's "Remove"): the next person to ask works it out again."""
    def change(cur):
        ix = _index(cur)
        if ix["entries"].pop(hk, None) is None:
            return None
        return json.dumps(ix, separators=(",", ":"))
    try:
        db.delete_setting(_row(kind, hk))
        db.update_setting(INDEX + kind, change)
        return True
    except Exception as ex:
        print("computed: not removed:", kind, type(ex).__name__, str(ex)[:100])
        return False


def index(kind: str) -> dict:
    """A kind's index: {"entries": {hk: {...}}, "hits", "misses", "refreshes", "by"}."""
    try:
        return _index(db.get_setting(INDEX + kind))
    except Exception:
        return _index(None)


def _iso(t) -> str | None:
    return datetime.fromtimestamp(float(t), timezone.utc).isoformat(timespec="seconds") if t else None


def stats() -> list[dict]:
    """Every kind's counts for Admin → Library: entries, bytes, hits, misses, hit rate, refreshes (and by which plans), oldest and
    newest, and an estimate of the work the hits saved."""
    flush(force=True)
    out = []
    for kind in LABELS:
        ix = index(kind)
        es = list(ix["entries"].values())
        hits = ix["hits"]
        asked = hits + ix["misses"]
        sec, calls = SAVES.get(kind, (0, 0))
        out.append({"kind": kind, "label": LABELS[kind], "entries": len(es),
                    "bytes": sum(e.get("size") or 0 for e in es), "hits": hits, "misses": ix["misses"],
                    "hit_rate": round(hits / asked * 100, 1) if asked else None, "refreshes": ix["refreshes"],
                    "by": {w: ix["by"].get(w, 0) for w in PLAN_WORDS},
                    "oldest": _iso(min((e.get("at") or 0 for e in es), default=0)), "newest": _iso(max((e.get("at") or 0 for e in es), default=0)),
                    "saved_seconds": round(hits * sec), "saved_ai_calls": hits * calls})
    return out


def entries(kind: str, q: str = "", region: str = "", limit: int = 500) -> list[dict]:
    """A kind's entries, newest first, for Admin (label, market, size, when, hits, refreshes, meta)."""
    q = " ".join(q.lower().split())
    rows = []
    for hk, e in index(kind)["entries"].items():
        if region and e.get("region") != region:
            continue
        hay = " ".join([e.get("label") or ""] + list((e.get("meta") or {}).get("aliases") or [])).lower()
        if q and q not in hay:
            continue
        rows.append({"id": hk, **{k: e.get(k) for k in ("label", "region", "size", "hits", "refreshes", "meta")},
                     "at": _iso(e.get("at")), "first": _iso(e.get("first")), "last": _iso(e.get("last"))})
    rows.sort(key=lambda r: r["at"] or "", reverse=True)
    return rows[:limit]


# ---------- Refresh: a guard window and a daily cap ----------
def plan_word(profile: dict | None) -> str:
    from . import admin
    from .plans import effective_plan
    if not profile:
        return "free"
    if admin.is_admin(profile):
        return "admin"
    try:
        return profile.get("_paid_plan") or effective_plan(profile)
    except Exception:
        return profile.get("plan") or "free"


def day_start() -> str:
    from .kite_service import IST
    return datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def refresh_gate(profile: dict | None, kind: str, at: float | None, guard: float | None = None) -> str:
    """Whether a person's Refresh of a stored result works it out again: "go" (counted against their day), "fresh" (it was worked out
    within the kind's guard window: the stored one is given, "already fresh") or "capped" (their refreshes for today are used: the stored
    one is given, with its date). Nothing stored yet (`at` None) is always "go" and not counted."""
    if not at:
        return "go"
    if _now() - float(at) < (GUARD.get(kind, DEFAULT_GUARD) if guard is None else guard):
        return "fresh"
    word = plan_word(profile)
    if word == "admin" or not profile or not profile.get("id"):
        return "go"
    from .plans import refreshes_per_day
    cap = refreshes_per_day(word)
    try:
        if cap is not None and db.count_usage(profile["id"], "refresh", day_start()) >= cap:
            return "capped"
        db.add_usage(profile["id"], "refresh")
    except Exception as ex:                 # the count couldn't be read: the stored result is given, never an error
        print("computed: refresh not counted:", type(ex).__name__, str(ex)[:100])
        return "capped"
    return "go"


def reset_for_tests() -> None:
    with _lock:
        _pending.clear()
    _flushed[0] = time.time()
