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
    return {"started": AI.rerank(names), **AI.admin_view()}


@router.post("/pin")
def ai_pin(req: PinReq, _=Depends(admin.admin_profile)):
    """Use only this model for this provider (or, with no model, go back to the measured ones)."""
    AI.pin(_provider(req.provider), (req.model or "").strip() or None)
    return AI.admin_view()


@router.post("/block")
def ai_block(req: BlockReq, _=Depends(admin.admin_profile)):
    """Never use this model (or allow it again)."""
    AI.block(_provider(req.provider), req.model.strip(), req.blocked)
    return AI.admin_view()
