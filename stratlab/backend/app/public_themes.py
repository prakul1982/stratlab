"""Public theme pages (bet 3): /themes, /themes/<in|us> and /themes/<in|us>/<slug>, server-rendered from the theme library's stored
entries (intel/theme_library.py), for search engines and people who aren't signed in.

A page is a teaser that brings people to the app (owner, 12 Nov): the theme's description, its layers with the names of their checked
companies (each linked to its public /stocks page), the date the map was made and a note on the method, then a call to open the full
theme in the app. Only figures that are reported, never one StratLab works out (owner, until the data terms are confirmed): a member's
market value and its latest reported revenue in its own reporting currency. No layer medians, ranks, margins or sums; no decks,
downloads or tables beyond the member list.

A page is offered to search engines only when it has at least MIN_LAYERS layers with checked companies and MIN_MEMBERS checked
companies in all; any other is noindex and left out of the sitemap. One page per theme: the address is the stored name's slug, and
a slug of one of its aliases answers 301 to it. Rendering reads stored entries only (no AI, no source call); the edge keeps a page
for hours (CACHE)."""
import html
import re
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from . import computed, stock_pages
from .config import settings
from .intel import theme_base, theme_library
from .share import FACTS_LINE, checked, day_text, public_words, theme_layers

router = APIRouter(include_in_schema=False)

REGIONS = {"in": "IN", "us": "US"}
MIN_LAYERS = 2
MIN_MEMBERS = 8
CACHE = "public, max-age=600, s-maxage=21600, stale-while-revalidate=86400"
MISSING_CACHE = "public, max-age=60, s-maxage=300"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\Z")
METHOD = ("How companies are chosen: a theme's companies come from its official industries (the exchange's own classification) and "
          "from a map of the theme's layers; a company placed by the map is shown here only once its own filings or description "
          "confirm the work its layer names. Market value is at the last close; revenue is the latest full year as the company "
          "reported it, in its own reporting currency. StratLab works out no figure on this page.")


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")[:80]


def path(region: str, s: str) -> str:
    return f"/themes/{region.lower()}/{s}"


def entries(region: str | None = None) -> list[dict]:
    """The library's stored themes under today's membership rules: {region, name, label, slug, aliases, at, hk}, by name."""
    out = []
    for hk, e in (computed.index(theme_library.KIND).get("entries") or {}).items():
        m = e.get("meta") or {}
        if m.get("rules") != theme_base.RULES or e.get("region") not in ("IN", "US") or (region and e.get("region") != region):
            continue
        name = str(m.get("q") or "")
        if not slug(name):
            continue
        out.append({"region": e["region"], "name": name, "label": public_words(e.get("label") or name, 80) or name, "slug": slug(name),
                    "aliases": [slug(a) for a in m.get("aliases") or [] if slug(a)], "at": e.get("at"), "hk": hk})
    return sorted(out, key=lambda x: (x["region"], x["label"].lower()))


def find(region: str, s: str) -> tuple[dict | None, str | None]:
    """(the entry at this slug, None), or (None, the canonical slug) when the slug is one of a theme's aliases, or (None, None)."""
    rows = entries(region)
    hit = next((x for x in rows if x["slug"] == s), None)
    if hit:
        return hit, None
    alias = [x for x in rows if s in x["aliases"]]
    return (None, alias[0]["slug"]) if len(alias) == 1 else (None, None)


def payload(entry: dict) -> dict | None:
    got = computed.get(theme_library.KIND, theme_library.key_of(entry["region"], entry["name"]), count=False)
    p = ((got or {}).get("value") or {}).get("payload")
    return p if isinstance(p, dict) else None


def _index_caps(region: str) -> dict:
    """{symbol: market value} as the screens' index has it (each page's own checked value: a failed one is None)."""
    try:
        from . import screens
        return {r["symbol"]: r.get("market_cap") for r in screens.load_index(region).get("rows") or [] if r.get("symbol")}
    except Exception:
        return {}


def _revenues(region: str, name: str, p: dict) -> dict:
    """{symbol: (revenue, year, unit)} from the theme's stored dive, only where the figure is the company's own reported revenue in
    the market's reporting unit (a figure turned from another currency is left out: that conversion is StratLab's)."""
    try:
        from .intel import theme_routes
        got = computed.get(theme_library.DIVE, theme_routes.dive_key(region, name, {**p, "_library": name}), count=False)
    except Exception:
        return {}
    dive = ((got or {}).get("value") or {}).get("dive") or {}
    out = {}
    for b in dive.get("layers") or []:
        for c in b.get("companies") or []:
            v = c.get("revenue")
            if isinstance(v, (int, float)) and v > 0 and not c.get("fx") and c.get("unit") in ("₹ crore", "$ million") and c.get("symbol"):
                out.setdefault(c["symbol"], (v, c.get("year"), c["unit"]))
    return out


def money(region: str, v, unit: str | None = None) -> str | None:
    if not isinstance(v, (int, float)) or v <= 0:
        return None
    return stock_pages.usd_text(v) if (unit or ("$ million" if region == "US" else "₹ crore")) == "$ million" else stock_pages.inr_text(v)


def view(entry: dict, p: dict) -> dict:
    """What a theme page shows: checked companies only, reported figures only."""
    region = entry["region"]
    caps, revs = _index_caps(region), _revenues(region, entry["name"], p)
    known = stock_pages.companies(region)
    layers = []
    for v in theme_layers(p):
        rows = []
        for c in v["companies"]:
            sym = c["ticker"]
            rev = revs.get(sym)
            rows.append({"symbol": sym, "name": public_words(c.get("name") or sym, 100) or sym,
                         "page": stock_pages.path(region, sym) if sym in known else None,
                         "cap": money(region, caps.get(sym)), "revenue": money(region, rev[0], rev[2]) if rev else None,
                         "year": str(rev[1] or "")[:20] if rev else None})
        layers.append({"name": v["name"], "companies": rows})
    n = len({c["symbol"] for v in layers for c in v["companies"]})
    return {"region": region, "label": entry["label"], "slug": entry["slug"], "name": entry["name"],
            "summary": public_words(p.get("summary"), 700), "layers": layers, "members": n,
            "day": datetime.fromtimestamp(float(entry["at"]), timezone.utc).date().isoformat() if entry.get("at") else None,
            "indexable": len(layers) >= MIN_LAYERS and n >= MIN_MEMBERS}


def indexable(entry: dict) -> bool:
    p = payload(entry)
    if not p:
        return False
    layers = theme_layers(p)
    return len(layers) >= MIN_LAYERS and len({c["ticker"] for v in layers for c in v["companies"]}) >= MIN_MEMBERS


def sitemap_rows(site: str) -> list[tuple[str, str | None]]:
    """(address, day) for the sitemap: the directory pages, and every theme page that is offered to search engines."""
    rows = entries()
    newest = max((datetime.fromtimestamp(float(x["at"]), timezone.utc).date().isoformat() for x in rows if x.get("at")), default=None)
    out = [(site + "/themes", newest)] + [(site + f"/themes/{r}", newest) for r in REGIONS]
    for x in rows:
        if indexable(x):
            out.append((site + path(x["region"], x["slug"]), datetime.fromtimestamp(float(x["at"]), timezone.utc).date().isoformat() if x.get("at") else None))
    return out


def latest_day() -> str:
    return max((datetime.fromtimestamp(float(x["at"]), timezone.utc).date().isoformat() for x in entries() if x.get("at")), default="")


# ---------- pages ----------
def _market(region: str) -> str:
    return "India" if region == "IN" else "the US"


def _app(region: str, name: str | None = None) -> str:
    return settings.PUBLIC_SITE_URL + "/research/themes" + (f"?q={quote(name)}&region={region}" if name else f"?region={region}")


def _where(v: dict) -> str:
    """ "companies in India", or just "companies" when the theme's own name says the market ("India steel and mining")."""
    word = "India" if v["region"] == "IN" else "US"
    return "companies" if re.search(rf"\b{word}\b", v["label"], re.I) else f"companies in {_market(v['region'])}"


def render(v: dict) -> str:
    e = html.escape
    site = settings.PUBLIC_SITE_URL
    r = v["region"]
    canonical = site + path(r, v["slug"])
    title = f"{v['label']} {_where(v)}: the theme's layers · StratLab"
    desc = (f"{v['label']} in {_market(r)}: {v['members']} checked companies in {len(v['layers'])} layers"
            + (f", from {', '.join(x['name'] for x in v['layers'][:3])}" if v["layers"] else "") + ". Facts from filings, not advice.")
    crumbs_html, crumbs_ld = stock_pages._crumbs([("Themes", "/themes"), ("India" if r == "IN" else "US", f"/themes/{r.lower()}"),
                                                  (v["label"], path(r, v["slug"]))])
    ld = stock_pages._ld({"@context": "https://schema.org", "@type": "Dataset", "name": f"{v['label']} companies in {_market(r)}",
                          "description": stock_pages.clamp_desc(desc, 300), "url": canonical, "dateModified": v["day"],
                          "creator": {"@type": "Organization", "name": "StratLab", "url": site}, "isAccessibleForFree": True}) + crumbs_ld
    head = stock_pages._head(title, desc, canonical, extra=ld, robots="index,follow" if v["indexable"] else "noindex,follow")
    app = _app(r, v["name"])
    body = (crumbs_html + f"<h1>{e(v['label'])} <span class=\"muted\">{e(_where(v))}</span></h1>"
            f'<p class="muted">{v["members"]} checked compan{"y" if v["members"] == 1 else "ies"} in {len(v["layers"])} layer{"" if len(v["layers"]) == 1 else "s"}'
            + (f" · map made {e(day_text(v['day']))}" if v.get("day") else "") + "</p>")
    if v["summary"]:
        body += f"<p>{e(v['summary'])}</p>"
    for x in v["layers"]:
        items = ""
        for c in x["companies"]:
            name = f'<a href="{e(c["page"])}">{e(c["name"])}</a>' if c["page"] else e(c["name"])
            figs = [f"Market value {c['cap']}"] if c["cap"] else []
            if c["revenue"]:
                figs.append(f"revenue {c['revenue']}" + (f" ({e(c['year'])})" if c.get("year") else ""))
            items += f'<li>{name} <span class="muted small">{e(c["symbol"])}' + (" · " + e(", ".join(figs)) if figs else "") + "</span></li>"
        body += f'<section class="card" data-layer><h2>{e(x["name"])}</h2><ul class="plain">{items}</ul></section>'
    if not v["layers"]:
        body += '<p class="note">No company in this theme has been checked yet.</p>'
    body += (f'<section class="card" data-cta><h2>See the full theme on StratLab</h2><p>Sign in for the whole theme: the figures of each layer, '
             f"every company placed by the map and how it was checked, the tailwinds and risks with their sources, the news and the slides.</p>"
             f'<div class="ctas"><a class="btn" href="{e(app)}">Open the {e(v["label"])} theme</a><a class="btn ghost" href="{e(site)}/pricing">See the plans</a></div></section>'
             f'<details class="how"><summary>How this page is made</summary><p>{e(METHOD)}</p></details>'
             f'<p class="note">{e(FACTS_LINE)} <a href="{e(site)}/help#feedback">Report an error</a>.</p>')
    return stock_pages._page(head, app, body)


def directory(region: str | None) -> str:
    e = html.escape
    site = settings.PUBLIC_SITE_URL
    rows = entries(region)
    where = f" in {_market(region)}" if region else ""
    canonical = site + ("/themes" + (f"/{region.lower()}" if region else ""))
    title = f"Investment themes{where}: companies by layer · StratLab"
    desc = f"Themes{where} mapped into layers of listed companies, each checked against its own filings. Facts, not advice."
    trail = [("Themes", "/themes")] + ([("India" if region == "IN" else "US", f"/themes/{region.lower()}")] if region else [])
    crumbs_html, crumbs_ld = stock_pages._crumbs(trail)
    head = stock_pages._head(title, desc, canonical, extra=crumbs_ld)
    tabs = "".join(f'<a href="/themes{p}"' + (' aria-current="page"' if (region or "") == R else "") + f">{t}</a>"
                   for p, R, t in (("", "", "All"), ("/in", "IN", "India"), ("/us", "US", "US")))
    body = (crumbs_html + f"<h1>Themes{e(where)}</h1><p class=\"muted\">{e(desc)}</p><nav class=\"links\" aria-label=\"Markets\">{tabs}</nav>")
    if rows:
        body += ('<ul class="dir">' + "".join(f'<li><a href="{e(path(x["region"], x["slug"]))}">{e(x["label"])}</a>'
                                               f'<span class="muted">{"India" if x["region"] == "IN" else "US"}</span></li>' for x in rows) + "</ul>")
    else:
        body += '<p class="note">No theme has been mapped and checked yet. Open the themes in the app to map one.</p>'
    body += (f'<div class="ctas"><a class="btn" href="{e(_app(region or "IN"))}">Map any theme on StratLab</a></div>'
             f'<p class="note">{e(FACTS_LINE)}</p>')
    return stock_pages._page(head, _app(region or "IN"), body)


def not_found() -> str:
    site = settings.PUBLIC_SITE_URL
    head = stock_pages._head("Theme not found · StratLab", "No theme at this address.", site + "/themes", robots="noindex,follow")
    return stock_pages._page(head, None, '<h1>No theme at this address</h1><p><a href="/themes">See every theme</a></p>')


def _missing():
    return HTMLResponse(not_found(), status_code=404, headers={"Cache-Control": MISSING_CACHE, "X-Robots-Tag": "noindex"})


@router.get("/themes")
def themes_all():
    return HTMLResponse(directory(None), headers={"Cache-Control": CACHE})


@router.get("/themes/{region}")
def themes_region(region: str):
    R = REGIONS.get(region)
    if not R:
        return _missing()
    return HTMLResponse(directory(R), headers={"Cache-Control": CACHE})


@router.get("/themes/{region}/{s}")
def theme_page(region: str, s: str):
    R = REGIONS.get(region)
    if not R or not SLUG.match(s or "") or len(s) > 80:
        return _missing()
    entry, canonical = find(R, s)
    if canonical:
        return RedirectResponse(path(R, canonical), status_code=301, headers={"Cache-Control": CACHE})
    p = payload(entry) if entry else None
    if not p:
        return _missing()
    v = view(entry, p)
    headers = {"Cache-Control": CACHE}
    if not v["indexable"]:
        headers["X-Robots-Tag"] = "noindex, follow"
    return HTMLResponse(render(v), headers=headers)


__all__ = ["router", "slug", "path", "entries", "find", "view", "render", "sitemap_rows", "indexable", "checked"]
