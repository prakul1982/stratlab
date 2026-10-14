"""/admin/ai/... API for the Admin page's AI panel: every provider's state, the models in use and how they're doing,
the order each kind of job asks them in, and the buttons (test now, re-rank, pin a model, block a model).
Provider names are fine here: only admins can call these."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import admin
from . import ai_providers as AI
from .ai_catalog import PROVIDERS
from .responses import err

router = APIRouter(prefix="/admin/ai", tags=["admin"])


class RerankReq(BaseModel):
    provider: str | None = Field(None, max_length=40)


class PinReq(BaseModel):
    provider: str = Field(..., max_length=40)
    model: str | None = Field(None, max_length=200)


class BlockManyReq(BaseModel):
    items: list[PinReq] = Field(..., min_length=1, max_length=200)
    blocked: bool = True


class UnblockAllReq(BaseModel):
    scope: str = Field("all", pattern="^(all|today)$")


class RestoreReq(BaseModel):
    ranks: dict = Field(..., max_length=40)


class BlockReq(BaseModel):
    provider: str = Field(..., max_length=40)
    model: str = Field(..., min_length=1, max_length=200)
    blocked: bool = True


def _provider(name: str | None) -> str:
    if name not in PROVIDERS:
        err(400, "bad_provider", "That isn't one of the AI providers.")
    return name


@router.get("")
def ai_view(_=Depends(admin.admin_profile)):
    return AI.admin_view()


@router.post("/test")
def ai_test(_=Depends(admin.admin_profile)):
    """A tiny request to every provider with a key, now (spends a little free quota)."""
    from .ai_writer import _anthropic, _gemini
    return {"providers": AI.test_all(gemini=_gemini, anthropic=_anthropic), "view": AI.admin_view()}


@router.post("/rerank")
def ai_rerank(req: RerankReq, _=Depends(admin.admin_profile)):
    """Measure the models again, in the background (a minute or two); the panel shows progress."""
    names = [_provider(req.provider)] if req.provider else None
    if names and not AI.configured(names[0]):
        err(400, "no_key", f"{PROVIDERS[names[0]].label} has no key yet.")
    # what each provider's order was, so the page can offer to put it back (R13S-004)
    before = AI.snapshot_rank(names)
    return {"started": AI.rerank(names), "undo": before, **AI.admin_view()}


@router.post("/rank-restore")
def ai_rank_restore(req: RestoreReq, _=Depends(admin.admin_profile)):
    """Put the orders from before a re-rank back (and keep them if the measuring is still running)."""
    return {"restored": AI.restore_rank(req.ranks), **AI.admin_view()}


@router.post("/pin")
def ai_pin(req: PinReq, _=Depends(admin.admin_profile)):
    """Use only this model for this provider (or, with no model, go back to the measured ones)."""
    AI.pin(_provider(req.provider), (req.model or "").strip() or None)
    return AI.admin_view()


@router.post("/block")
def ai_block(req: BlockReq, profile=Depends(admin.admin_profile)):
    """Never use this model (or allow it again). A block keeps who made it and when."""
    AI.block(_provider(req.provider), req.model.strip(), req.blocked, profile.get("email"))
    return AI.admin_view()


@router.post("/block-many")
def ai_block_many(req: BlockManyReq, profile=Depends(admin.admin_profile)):
    """Block or allow several models at once: the undo of "Unblock all"."""
    items = [(_provider(i.provider), (i.model or "").strip()) for i in req.items if (i.model or "").strip()]
    AI.block_many(items, req.blocked, profile.get("email"))
    return AI.admin_view()


@router.post("/unblock-all")
def ai_unblock_all(req: UnblockAllReq, profile=Depends(admin.admin_profile)):
    """Allow every blocked model again, or only the ones blocked today (India's day). Says which, so it can be undone."""
    items = AI.blocked_since(AI.today_start() if req.scope == "today" else None)
    AI.block_many(items, False, profile.get("email"))
    return {"unblocked": [{"provider": n, "model": m} for n, m in items], **AI.admin_view()}
