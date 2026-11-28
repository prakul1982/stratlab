"""The sample deck (FREE-TIER, owner Nov: Free is a teaser). Free makes one theme deck a month as a marked PDF (price102), and the
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
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import Response

from . import computed
from .config import settings
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


@router.get("/sample-deck.pdf")
def sample_deck_pdf(id: str | None = None):
    """conv101: the same PDF at the site's own stable address (stratlab.studio/sample-deck.pdf; vercel.json forwards it here)."""
    return sample_deck(id)


# ---------- the sample deck's own page (conv101: a link people can share, with a preview, that leads to the PDF) ----------
WHAT_IT_HOLDS = (
    "The theme at a glance: how its companies were found and checked, and the funds that track it",
    "The value chain by layer, as a chart and a table",
    "Each layer's companies with their figures: market value, revenue, margins, the median and range",
    "Tailwinds and risks, each with its source and date",
    "Recent headlines, new listings and the method behind every number",
)


def page_html() -> tuple[str, int]:
    """The sample deck's page: what it is, what a theme deck holds, the download, and how to get decks of any theme. The page's Open Graph
    tags give a shared link its title, description and picture. (html, status): 200 with a deck to give, else a short page kept out of search."""
    import html as _html
    from . import plans, stock_pages
    from .titles import page_title
    e = _html.escape
    site = settings.PUBLIC_SITE_URL
    r = chosen()
    theme = _name(r["label"]) if r else ""
    canonical = site + "/sample-deck"
    if not r:
        head = stock_pages._head(page_title("Sample deck"), "There's no sample deck to download right now.", canonical, robots="noindex,follow")
        body = ('<h1>Sample theme deck</h1><p class="muted">There\'s no sample deck to download right now. Please look again later.</p>'
                f'<div class="ctas"><a class="btn ghost" href="{e(site)}/themes">See the themes</a><a class="btn ghost" href="{e(site)}/pricing">See the plans</a></div>')
        return stock_pages._page(head, None, body, src="sample-deck"), 200
    title = page_title(f"Sample theme deck: {theme}")
    desc = (f"A real StratLab theme deck, free to download as a PDF with no sign-in: {theme}, its listed companies by layer, their figures, "
            "tailwinds and risks with sources. Facts from filings, not advice.")
    pdf = f"{site}/sample-deck.pdf?id={quote(str(r.get('id') or ''), safe='')}"
    ld = stock_pages._ld({"@context": "https://schema.org", "@type": "DigitalDocument", "name": f"StratLab sample theme deck: {theme}",
                          "description": desc, "url": canonical, "encodingFormat": "application/pdf", "isAccessibleForFree": True,
                          "publisher": {"@type": "Organization", "name": "StratLab", "url": site}})
    head = stock_pages._head(title, desc, canonical, extra=ld, og_type="article")
    region = r.get("region") if r.get("region") in ("IN", "US") else None
    theme_link = ""
    if region:
        try:
            from . import public_themes
            from .intel import theme_library
            name = theme_library.normalise(theme, region)
            hit = next((x for x in public_themes.entries(region) if public_themes.slug(x["name"]) == public_themes.slug(name)), None)
            if hit:
                theme_link = f'<p><a class="link" href="{e(public_themes.path(region, hit["slug"]))}">See the {e(public_themes.short_label(hit["label"]))} theme\'s companies on the site</a></p>'
        except Exception as ex:
            print("sample deck theme link failed:", str(ex)[:160])
    free, basic, pro = (plans.PLANS[p]["decks_per_month"] for p in ("free", "basic", "pro"))
    per = lambda n: "unlimited" if n is None else f"{n} a month"      # noqa: E731
    holds = "".join(f"<li>{e(x)}</li>" for x in WHAT_IT_HOLDS)
    body = (f'<h1>Sample theme deck <span class="muted">{e(theme)}</span></h1>'
            '<p class="muted">A real deck StratLab made from its theme map, as it was made: free to download, no sign-in, nothing to fill in.</p>'
            f'<div class="ctas" data-sample-download><a class="btn" href="{e(pdf)}" download>Download the sample deck (PDF)</a>'
            f'<a class="btn ghost" href="{e(site)}/pricing">See the plans</a></div>'
            f'<section class="card"><h2>What a theme deck holds</h2><ul class="plain">{holds}</ul></section>'
            f'<section class="card"><h2>Decks of any theme or company</h2><p>A free account makes {e(str(free))} theme deck a month as a PDF, each page marked '
            f'"Made with StratLab · stratlab.studio". Basic makes {e(per(basic))} and Pro {e(per(pro))}, of a company or a theme, as PowerPoint or PDF. '
            f'<a class="link" href="{e(site)}/pricing">Plans and prices</a>.</p></section>'
            + theme_link +
            '<p class="note">StratLab gives facts, not investment advice, and is not a SEBI-registered investment adviser or research analyst. '
            'Figures come from companies\' reported results and filings (NSE, BSE and the SEC) and market prices.</p>')
    return stock_pages._page(head, None, body, src="sample-deck"), 200


@router.get("/sample-deck")
def sample_deck_page():
    from fastapi.responses import HTMLResponse
    page, status = page_html()
    return HTMLResponse(page, status_code=status, headers={"Cache-Control": "public, max-age=300, s-maxage=3600, stale-while-revalidate=600"})
