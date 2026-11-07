"""/me/saved: the signed-in person's saved searches and AI reads (saved_searches), and /admin/saved-searches, the counts by kind for Admin.

Private to the person: the profile's id is part of every stored key, so nothing in a request can reach someone else's. A search is read
again by the page's own endpoint (in the browser, under that endpoint's cache rules); these routes keep the list and the snapshots and say
what changed."""
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import saved_searches as S
from .admin import admin_profile
from .auth import current_profile
from .responses import err, ok

router = APIRouter(prefix="/me/saved", tags=["saved"])
admin_router = APIRouter(tags=["admin"])
SAVES = 60                 # saves, renames and updates per person per hour


class SaveReq(BaseModel):
    kind: str = Field(..., max_length=24)
    name: str = Field(..., max_length=200)
    params: dict[str, Any] = Field(default_factory=dict)
    snap: dict[str, Any] | None = None


class RenameReq(BaseModel):
    name: str = Field(..., max_length=200)


class UpdateReq(BaseModel):
    snap: dict[str, Any]


def _throttle(profile) -> None:
    from . import main
    main.throttle(profile, "saved_search", SAVES, 3600, "That's a lot of saved-search changes in an hour. Try again later.")


def _page(uid: str, kind: str | None = None) -> dict:
    mine = S.items(uid)
    return {"items": [x for x in mine if kind is None or x["kind"] == kind], "count": len(mine), "limit": S.LIMIT}


def _gone() -> None:
    err(404, "not_found", "That saved search is gone. Reload the page.")


@router.get("")
def saved_list(kind: str | None = None, profile=Depends(current_profile)):
    if kind is not None and kind not in S.KINDS:
        err(400, "bad_kind", "That kind of search can't be saved.")
    return ok(_page(profile["id"], kind))


@router.get("/usage")
def saved_usage(profile=Depends(current_profile)):
    """{"count", "limit"}: the saved list's use of its limit, for Settings' usage table."""
    return ok(S.usage(profile["id"]))


@router.post("")
def saved_add(req: SaveReq, profile=Depends(current_profile)):
    _throttle(profile)
    try:
        item, new = S.add(profile["id"], req.kind, req.name, req.params, req.snap)
    except S.SavedError as e:
        err(400, "bad_saved", str(e))
    except S.LimitReached:
        err(400, "saved_limit", f"You can keep {S.LIMIT} saved searches and reads. Remove one to save another.")
    return ok({"item": item, "new": new, **_page(profile["id"], req.kind)})


@router.patch("/{sid}")
def saved_rename(sid: str, req: RenameReq, profile=Depends(current_profile)):
    if not S.valid_id(sid):
        _gone()
    _throttle(profile)
    try:
        item = S.rename(profile["id"], sid, req.name)
    except S.SavedError as e:
        err(400, "bad_saved", str(e))
    if item is None:
        _gone()
    return ok({"item": item, **_page(profile["id"], item["kind"])})


@router.post("/{sid}/update")
def saved_update(sid: str, req: UpdateReq, profile=Depends(current_profile)):
    """The search read again by its page's endpoint: the new snapshot kept, and what changed since the saved one."""
    if not S.valid_id(sid):
        _gone()
    _throttle(profile)
    try:
        got = S.update(profile["id"], sid, req.snap)
    except S.SavedError as e:
        err(400, "bad_saved", str(e))
    if got is None:
        _gone()
    item, changes = got
    return ok({"item": item, "changes": changes, **_page(profile["id"], item["kind"])})


@router.delete("/{sid}")
def saved_remove(sid: str, kind: str | None = None, profile=Depends(current_profile)):
    if not S.valid_id(sid) or not S.remove(profile["id"], sid):
        _gone()
    return ok(_page(profile["id"], kind if kind in S.KINDS else None))


@admin_router.get("/admin/saved-searches")
def saved_counts(_=Depends(admin_profile)):
    """How many saved searches and reads there are of each kind, and how many people keep any (for Admin's Library tab)."""
    return ok({**S.counts_by_kind(), "labels": {k: v["label"] for k, v in S.KINDS.items()}, "limit": S.LIMIT})
