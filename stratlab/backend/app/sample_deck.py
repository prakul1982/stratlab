"""The sample deck (FREE-TIER, owner Nov: Free is a teaser). Free has no slide decks of its own (plans.PLANS decks_per_month 0), so the
Plans page and the locked deck buttons offer one fixed theme deck that is already kept in the shared store (computed.py, kind
"deck:theme", made by theme_routes.theme_dive_deck) for anyone, signed in or not, to download and see what a deck holds.

Nothing is made here: no AI call, no data source, no deck build, nothing counted. The deck is SAMPLE_THEME's newest kept PDF; when that
theme has none kept, the newest kept PDF of any theme; when nothing is kept, 404 (the pages then show no link: GET /pricing/sample-deck/info).
"""
import base64

from fastapi import APIRouter
from fastapi.responses import Response

from . import computed
from .responses import err

router = APIRouter()

KIND = "deck:theme"
SAMPLE_THEME = ("IN", "defence")      # the market and the theme's normalised name (theme_library.normalise): "India defence"


def _name(label: str) -> str:
    """The theme's name from a kept deck's label: "India defence (PDF, 2026-11-10)" -> "India defence"."""
    return (label or "").rsplit(" (", 1)[0].strip()


def _is_pdf(label: str) -> bool:
    return "(PDF," in (label or "")


def pick(rows: list[dict]) -> dict | None:
    """The kept deck to offer, from computed.entries (newest first): SAMPLE_THEME's newest PDF, else the newest PDF, else None."""
    from .intel import theme_library
    pdfs = [r for r in rows if _is_pdf(r.get("label") or "")]
    region, theme = SAMPLE_THEME
    for r in pdfs:
        if r.get("region") == region and theme_library.normalise(_name(r.get("label") or ""), region) == theme:
            return r
    return pdfs[0] if pdfs else None


def chosen() -> dict | None:
    try:
        return pick(computed.entries(KIND))
    except Exception:
        return None


def file_name(theme: str) -> str:
    slug = "".join(ch if ch.isalnum() else "-" for ch in theme.lower()).strip("-") or "theme"
    while "--" in slug:
        slug = slug.replace("--", "-")
    return f"stratlab-sample-deck-{slug}.pdf"


@router.get("/pricing/sample-deck/info")
def sample_info():
    """Whether there is a sample deck to download, and which theme it is (the Plans page and the deck lock show the link only then)."""
    r = chosen()
    return {"available": bool(r), "theme": _name(r["label"]) if r else None, "region": r.get("region") if r else None}


@router.get("/pricing/sample-deck")
def sample_deck():
    """The sample deck's PDF, for anyone (no sign-in): an existing kept theme deck, sent as it was made."""
    r = chosen()
    got = computed.get_hk(KIND, r["id"]) if r else None
    body = None
    if got and isinstance(got.get("value"), str):
        try:
            body = base64.b64decode(got["value"])
        except ValueError:
            body = None
    if not body:
        err(404, "no_sample_deck", "There's no sample deck to download right now.")
    return Response(body, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{file_name(_name(r["label"]))}"',
                             "Cache-Control": "public, max-age=3600"})
