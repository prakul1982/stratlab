"""/admin/stored: Admin → Library (R19, owner 7 Nov: "make a tab in admin too where i can see all the data").

Everything kept once for every user in one view: the shared store's kinds (computed.py: counts, sizes, hits, hit rate, refreshes and by
which plans, oldest and newest, the work the hits saved), the theme library row by row (search, market, members, last read, times
searched, size; Refresh now and Remove), the other shared data the app already keeps in the database (company pages, deep dives,
results, ...: counts and sizes by prefix), and how many saved searches people keep, by kind (counts only, nobody's content)."""
import threading

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import admin, computed, db, market_store
from .responses import err

router = APIRouter(prefix="/admin/stored", tags=["admin"])       # (/admin/library is the strategy library's moderation queue)

# the shared data kept before the store, by app_settings prefix: what it is, for the table
STORED = (("stocks:", "Company pages"), ("deep:", "Company deep dives"), ("audit:", "Company checks"), ("results:", "Results calendar and past results"),
          ("bizupd:", "Business updates"), ("deals:", "Bulk and block deals"), ("corpact:", "Corporate actions"), ("shp:", "Shareholding"),
          ("redflags:", "Red flags"), ("screens:index:", "Screener index"), ("ipo:", "IPOs"), ("breadth:", "Market breadth"),
          ("theme:evidence:", "Company descriptions (themes)"), ("theme:hist:", "Theme valuation history"), ("mfnav:", "Mutual fund NAVs"))


class RowReq(BaseModel):
    kind: str = Field(..., max_length=40)
    id: str = Field(..., min_length=6, max_length=40)


def _prefix_stats(prefix: str) -> dict:
    """Count, size, oldest and newest of one prefix: on the market database in one query; on the main one, keys and dates only."""
    ms = market_store.store()
    if ms is not None and market_store.covers_prefix(prefix):
        try:
            return ms.prefix_stats(prefix)
        except Exception as e:
            print("library: prefix not counted:", prefix, type(e).__name__, str(e)[:100])
            return {"entries": None, "bytes": None, "oldest": None, "newest": None}
    rows, after = [], ""
    try:
        while True:                 # by key, a page at a time (the server caps one read); no values read
            qy = db.sb().table("app_settings").select("key,updated_at").like("key", prefix + "%")
            got = (qy.gt("key", after) if after else qy).order("key").limit(1000).execute().data or []
            rows += got
            if len(got) < 1000:
                break
            after = got[-1]["key"]
    except Exception:
        rows = []
    dates = sorted(str(r.get("updated_at") or "") for r in rows if r.get("updated_at"))
    return {"entries": len(rows), "bytes": None, "oldest": dates[0] if dates else None, "newest": dates[-1] if dates else None}


def saved_counts() -> list[dict] | None:
    """People's saved searches by kind (counts only), from the saved-searches feature when it is there; None before."""
    for name in ("saved_searches", "saved"):
        try:
            mod = __import__(f"app.{name}", fromlist=["counts_by_kind"])
        except Exception:
            continue
        fn = getattr(mod, "counts_by_kind", None)
        if callable(fn):
            try:
                got = fn() or {}
                return [{"kind": k, "count": int(v)} for k, v in sorted(got.items())]
            except Exception as e:
                print("library: saved searches not counted:", type(e).__name__, str(e)[:100])
                return None
    return None


def _themes(q: str = "", region: str = "") -> list[dict]:
    from .intel import theme_library
    rows = computed.entries(theme_library.KIND, q, region)
    for r in rows:
        m = r.get("meta") or {}
        r.update(q=m.get("q"), aliases=m.get("aliases") or [], members=m.get("members"), searched=r.get("hits") or 0,
                 refreshing=bool(theme_library.refreshing(r.get("region") or "", m.get("q") or "")))
    return rows


DECKS_SHOWN = 60                 # the newest kept theme decks listed with their publication check


def _decks(q: str = "", region: str = "") -> list[dict]:
    """The kept theme decks, newest first, each with its publication gate's result (R27: pass or fail per item, what was dropped); a deck
    kept before the gate existed says so (no result)."""
    rows = []
    for r in computed.entries("deck:theme", q, region)[:DECKS_SHOWN]:
        g = (r.get("meta") or {}).get("gate") or None
        rows.append({"id": r["id"], "label": r.get("label"), "region": r.get("region"), "at": r.get("at"), "size": r.get("size"), "hits": r.get("hits") or 0,
                     "gate": g if isinstance(g, dict) and g.get("items") else None})
    return rows


@router.get("")
def library_view(q: str = "", region: str = "", _=Depends(admin.admin_profile)):
    stored = [{"prefix": p, "label": label, **_prefix_stats(p)} for p, label in STORED]
    reg = region if region in ("IN", "US") else ""
    return {"stores": computed.stats(), "themes": _themes(q[:80], reg), "decks": _decks(q[:80], reg), "stored": stored,
            "saved": saved_counts()}


@router.get("/entries")
def library_entries(kind: str, q: str = "", region: str = "", _=Depends(admin.admin_profile)):
    if kind not in computed.LABELS:
        err(400, "bad_kind", "That isn't one of the stored kinds.")
    return {"kind": kind, "rows": computed.entries(kind, q[:80], region if region in ("IN", "US") else "")}


def _refresh_theme(profile: dict, region: str, name: str, q: str) -> None:
    """Admin's Refresh now for a stored theme, behind the request: the AI map written again, checked, described and kept for everyone.
    If anything fails, the stored read stays as it was."""
    from .intel import routes as R, theme_library, theme_routes
    theme_library.mark_refreshing(region, name, by="admin")
    try:
        R.sector_map(profile, region, q, refresh=True)
        j = theme_routes.job_of(("map", region, " ".join(q.split())[:80].lower()))
        if j is not None:
            j["done"].wait(180)
        if not theme_library.keep(region, q, R.sector_payload(profile, region, q, False, wait=True), by="admin"):
            theme_library.mark_refreshing(region, name, False)
    except Exception as e:
        print("library: theme not refreshed:", name, type(e).__name__, str(e)[:120])
        theme_library.mark_refreshing(region, name, False)


@router.post("/refresh")
def library_refresh(req: RowReq, profile=Depends(admin.admin_profile)):
    """Refresh now: a theme is written again behind the request (the row says "Refreshing" until it's in); any other stored result is
    removed, so the next person who opens it gets it worked out afresh and kept again."""
    if req.kind not in computed.LABELS:
        err(400, "bad_kind", "That isn't one of the stored kinds.")
    if req.kind != "theme":
        return {"ok": computed.remove(req.kind, req.id), "refreshing": False}
    e = computed.index("theme")["entries"].get(req.id)
    if e is None:
        err(404, "not_found", "That theme isn't in the library any more.")
    stored = computed.get_hk("theme", req.id) or {}
    q = (stored.get("value") or {}).get("q") or (e.get("meta") or {}).get("q") or e.get("label") or ""
    threading.Thread(target=_refresh_theme, args=(profile, e.get("region") or "IN", (e.get("meta") or {}).get("q") or "", q),
                     name="library-refresh", daemon=True).start()
    return {"ok": True, "refreshing": True}


@router.post("/remove")
def library_remove(req: RowReq, _=Depends(admin.admin_profile)):
    if req.kind not in computed.LABELS:
        err(400, "bad_kind", "That isn't one of the stored kinds.")
    return {"ok": computed.remove(req.kind, req.id)}
