"""The sample deck (FREE-TIER, owner Nov: Free is a teaser). Free has no slide decks of its own (plans.PLANS decks_per_month 0), so the
Plans page and the locked deck buttons offer one fixed theme deck that is already kept in the shared store (computed.py, kind
"deck:theme", made by theme_routes.theme_dive_deck) for anyone, signed in or not, to download and see what a deck holds.

Nothing is made here: no AI call, no data source, no deck build, nothing counted. The deck is a kept PDF whose publication gate passed:
SAMPLE_THEME's newest made under today's versions, else the newest such of any theme; when a release has changed the versions and no deck
of today's versions has passed yet, the last one that passed under an earlier release (LIVE15A-003: after Release 77 changed the deck's
versions, no kept PDF was current until someone made a deck again, so /info said available:false for hours while /plans promised a sample);
only then a current deck whose gate failed an item; when none is kept, 404 (the pages then show no link and no promise:
GET /pricing/sample-deck/info).
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


def current(row: dict, versions: list | None = None) -> bool:
    """Whether a kept deck was made under today's versions (its rules, deck, dive text and sector figures: computed.VERSIONS): blog2, the owner,
    16 Nov ("fix ... old deck ... make it all updated"): the index keeps the entries of older versions too, so the newest PDF can be one
    a deploy has since replaced; a deck kept before the versions were recorded is not current either."""
    want = computed.versions(KIND) if versions is None else versions
    return want is None or ((row.get("meta") or {}).get("versions") == want)


def pick(rows: list[dict], versions: list | None = None) -> dict | None:
    """The kept deck to offer, from computed.entries (newest first): of the PDFs made under today's versions (current) whose gate passed,
    SAMPLE_THEME's newest, else the newest; else (LIVE15A-003) the newest PDF whose gate passed under an earlier release, kept until a deck of
    today's versions passes; else a current one whose gate failed an item; None when none of these is kept."""
    from .intel import theme_library
    pdfs = [r for r in rows if _is_pdf(r.get("label") or "")]
    now = [r for r in pdfs if current(r, versions)]
    # fix20 (LIVE14B-005: the IT services deck, the newest kept, handed out as the showcase with engine notes in it): a deck whose publication
    # gate passed every item first, SAMPLE_THEME's before any other; one with a failed item only when no clean one is kept
    region, theme = SAMPLE_THEME
    good = [r for r in now if clean(r)]
    # e84 (LIVE20B-003: the sample deck "Prices as of 19 Nov 2026" handed out after the 20 Nov closes were in): of the clean decks, those at
    # the newest close their prices are at (meta "prices", kept since e84; one kept before says none and counts as older)
    top = max((str((r.get("meta") or {}).get("prices") or "") for r in good), default="")
    if top:
        good = [r for r in good if str((r.get("meta") or {}).get("prices") or "") == top]
    for r in good:
        if r.get("region") == region and theme_library.normalise(_name(r.get("label") or ""), region) == theme:
            return r
    if good:
        return good[0]
    last_good = next((r for r in pdfs if clean(r)), None)       # blog2's older release only while no current deck has passed
    if last_good:
        return last_good
    for r in now:
        if r.get("region") == region and theme_library.normalise(_name(r.get("label") or ""), region) == theme:
            return r
    return now[0] if now else None


def clean(row: dict) -> bool:
    """fix20: whether a kept deck's publication gate (kept with it: theme_routes.theme_dive_deck) passed every item."""
    items = ((row.get("meta") or {}).get("gate") or {}).get("items")
    return bool(items) and all(isinstance(x, dict) and x.get("ok") for x in items)


def chosen(deck_id: str | None = None) -> dict | None:
    """The deck to offer; with `deck_id` (the one /info named, LIVE12B-021), that same deck while it is still a current kept PDF, so the
    file downloaded is the theme the link says even when a newer deck has been kept since the page read /info."""
    try:
        rows = computed.entries(KIND)
        if deck_id:
            same = next((r for r in rows if r.get("id") == deck_id and _is_pdf(r.get("label") or "") and (current(r) or clean(r))), None)
            if same:
                return same
        return pick(rows)
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
    return {"available": bool(r), "theme": _name(r["label"]) if r else None, "region": r.get("region") if r else None, "id": r.get("id") if r else None}


@router.get("/pricing/sample-deck")
def sample_deck(id: str | None = None):
    """The sample deck's PDF, for anyone (no sign-in): an existing kept theme deck, sent as it was made. `id`: the deck /info named (the
    link carries it), so the label and the file are the same theme (LIVE12B-021: "Cement" downloaded the Oil and gas deck)."""
    r = chosen((id or "")[:200] or None)
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
