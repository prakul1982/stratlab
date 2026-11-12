"""Embeddable charts (bet 3): /embed/price/<in|us>/<symbol> and /embed/theme/<in|us>/<slug>, small server-rendered pages holding one
SVG chart, a caption with the kind of source and the date, and a link back to StratLab, for other sites to put in an iframe.

These are the only addresses any other site may frame: the API's guard (guard.py) and the host's headers (frontend/vercel.json) send
`frame-ancestors *` and no X-Frame-Options here, and DENY everywhere else. No script runs; the chart is drawn here from the same closes
the public company page's chart uses (a price) or from the theme's stored map (how many checked companies each layer holds: a count,
not a figure StratLab works out from the numbers). The edge keeps each for minutes to hours (CACHE)."""
import html
import json
from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from . import public_themes, stock_pages
from .config import settings
from .share import day_text, public_words

router = APIRouter(include_in_schema=False)

PRICE_CACHE = "public, max-age=900, s-maxage=3600, stale-while-revalidate=21600"
THEME_CACHE = "public, max-age=3600, s-maxage=21600, stale-while-revalidate=86400"
MISSING_CACHE = "public, max-age=60, s-maxage=300"
RANGES = {"6m": 183, "1y": 365, "5y": 1830}
W, H, PAD = 600, 220, 44
EPOCH = date(1970, 1, 1)

# set by main.py: (region, symbol, request) -> the response of /stocks/<region>/<symbol>/prices.json (its caches, ration and checks)
_prices = None


def setup(prices) -> None:
    global _prices
    _prices = prices


STYLE = """
:root{--paper:#FFFDF8;--ink:#1D1B17;--muted:#5C574D;--line:#E2DAC8;--blue:#1F4FB5;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--paper:#1F1D1A;--ink:#EFE9DC;--muted:#B3AC9C;--line:#34312A;--blue:#7EA0F0;color-scheme:dark}}
*{box-sizing:border-box}html,body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{padding:12px 14px}h1{font-size:15px;font-weight:600;margin:0 0 2px}p{margin:0}.muted{color:var(--muted)}.small{font-size:12.5px}
svg{display:block;width:100%;height:auto;margin:6px 0}.axis{stroke:var(--line)}.lbl{fill:var(--muted);font-size:12px}.line{stroke:var(--blue);fill:none;stroke-width:2}
.bar{fill:var(--blue)}.val{fill:var(--ink);font-size:12px;font-weight:600}a{color:var(--blue)}
.sr-only{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
"""


def _doc(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="robots" content="noindex,follow"><title>{html.escape(title)}</title><style>{STYLE}</style></head>'
            f"<body><main>{body}</main></body></html>")


def _missing(what: str):
    return HTMLResponse(_doc("Not available · StratLab", f'<p>{html.escape(what)}</p><p class="small"><a href="{settings.PUBLIC_SITE_URL}/" target="_blank" '
                                                          f'rel="noopener">StratLab</a></p>'),
                        status_code=404, headers={"Cache-Control": MISSING_CACHE})


def price_points(series: dict, days: int) -> list[tuple[str, float]]:
    """(day, close) of the series' last `days` days, oldest first."""
    t, c = series.get("t") or [], series.get("c") or []
    rows = [(EPOCH + timedelta(days=int(d)), float(v)) for d, v in zip(t, c) if isinstance(d, (int, float)) and isinstance(v, (int, float)) and v > 0]
    if not rows:
        return []
    cut = rows[-1][0] - timedelta(days=days)
    return [(d.isoformat(), v) for d, v in rows if d >= cut]


def price_svg(points: list[tuple[str, float]], money) -> tuple[str, str]:
    """A line of closes with the low and the high marked on the left, the first and last day under it."""
    lo, hi = min(v for _, v in points), max(v for _, v in points)
    span = (hi - lo) or 1.0
    n = len(points)
    x = lambda i: PAD + (W - PAD - 8) * (i / max(1, n - 1))                    # noqa: E731
    y = lambda v: 10 + (H - 40) * (1 - (v - lo) / span)                         # noqa: E731
    line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
    first, last = points[0], points[-1]
    label = f"Daily close from {day_text(first[0])} ({money(first[1])}) to {day_text(last[0])} ({money(last[1])}); low {money(lo)}, high {money(hi)}."
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(label)}">'
            f'<line class="axis" x1="{PAD}" y1="{H - 30}" x2="{W - 8}" y2="{H - 30}"/>'
            f'<text class="lbl" x="2" y="{y(hi) + 4:.1f}">{html.escape(money(hi))}</text><text class="lbl" x="2" y="{y(lo) + 4:.1f}">{html.escape(money(lo))}</text>'
            f'<polyline class="line" points="{line}"/>'
            f'<text class="lbl" x="{PAD}" y="{H - 10}">{html.escape(day_text(first[0]))}</text>'
            f'<text class="lbl" x="{W - 8}" y="{H - 10}" text-anchor="end">{html.escape(day_text(last[0]))}</text></svg>'), label


def theme_svg(layers: list[tuple[str, int]]) -> tuple[str, str]:
    """One bar per layer: how many checked companies it holds."""
    top = max(n for _, n in layers) or 1
    row, gap = 26, 8
    h = len(layers) * (row + gap) + 4
    label = "Checked companies in each layer: " + "; ".join(f"{name} {n}" for name, n in layers) + "."
    bars = ""
    for i, (name, n) in enumerate(layers):
        yy = i * (row + gap)
        wbar = max(2.0, (W - 250) * n / top)
        short = name if len(name) <= 30 else name[:29].rstrip() + "…"
        bars += (f'<text class="lbl" x="0" y="{yy + 17}">{html.escape(short)}</text><rect class="bar" x="210" y="{yy + 3}" width="{wbar:.1f}" height="{row - 6}" rx="3"/>'
                 f'<text class="val" x="{210 + wbar + 6:.1f}" y="{yy + 18}">{n}</text>')
    return f'<svg viewBox="0 0 {W} {h}" role="img" aria-label="{html.escape(label)}">{bars}</svg>', label


def _caption(source: str, as_of: str, back: str, back_text: str) -> str:
    return (f'<p class="small muted">Source: {html.escape(source)}, compiled by StratLab. As of {html.escape(as_of)}. Facts, not advice.</p>'
            f'<p class="small"><a href="{html.escape(back)}" target="_blank" rel="noopener">{html.escape(back_text)}</a></p>')


@router.get("/embed/price/{region}/{symbol}")
def embed_price(region: str, symbol: str, request: Request, range: str = "1y"):
    R = stock_pages.REGIONS.get((region or "").lower())
    hit = stock_pages.find(R, symbol) if R and 0 < len(symbol or "") <= 20 else None
    if not hit or _prices is None:
        return _missing("No price chart for that company.")
    sym, co = hit
    resp = _prices(region.lower(), sym, request)
    if resp.status_code != 200:
        return HTMLResponse(_doc("Prices busy · StratLab", "<p>Prices can't be read right now. Try again in a minute.</p>"), status_code=503,
                            headers={"Retry-After": "60", "Cache-Control": "no-store"})
    points = price_points(json.loads(resp.body), RANGES.get(range, 365))
    if len(points) < 2:
        return _missing("No price chart for that company.")
    usd = R == "US"
    money = (lambda v: f"${v:,.2f}") if usd else (lambda v: f"₹{v:,.2f}")   # noqa: E731
    name = public_words(stock_pages.label_of(R, sym, co), 100) or sym
    svg, label = price_svg(points, money)
    back = settings.PUBLIC_SITE_URL + stock_pages.path(R, sym)
    body = (f"<h1>{html.escape(name)}" + (f" <span class=\"muted\">({html.escape(sym)})</span>" if name != sym else "") + "</h1>"
            f'<p class="small muted">Daily close, last {"6 months" if range == "6m" else "5 years" if range == "5y" else "year"}</p>'
            + svg + f'<p class="sr-only">{html.escape(label)}</p>'
            + _caption("exchange closing prices", day_text(points[-1][0]), back, f"{name} on StratLab"))
    return HTMLResponse(_doc(f"{name} price · StratLab", body), headers={"Cache-Control": PRICE_CACHE})


@router.get("/embed/price/{symbol}")
def embed_price_any(symbol: str, request: Request, range: str = "1y"):
    """The short form: an Indian listing first, then a US one."""
    for r in ("in", "us"):
        if 0 < len(symbol or "") <= 20 and stock_pages.find(stock_pages.REGIONS[r], symbol):
            return embed_price(r, symbol, request, range)
    return _missing("No price chart for that company.")


@router.get("/embed/theme/{region}/{slug}")
def embed_theme(region: str, slug: str):
    R = public_themes.REGIONS.get((region or "").lower())
    if not R or not public_themes.SLUG.match(slug or "") or len(slug) > 80:
        return _missing("No chart for that theme.")
    entry, canonical = public_themes.find(R, slug)
    entry = entry or (public_themes.find(R, canonical)[0] if canonical else None)
    p = public_themes.payload(entry) if entry else None
    if not p:
        return _missing("No chart for that theme.")
    v = public_themes.view(entry, p)
    if not v["layers"]:
        return _missing("No company in this theme has been checked yet.")
    svg, label = theme_svg([(x["name"], len(x["companies"])) for x in v["layers"]])
    back = settings.PUBLIC_SITE_URL + public_themes.path(R, v["slug"])
    body = (f"<h1>{html.escape(v['label'])} <span class=\"muted\">· {'India' if R == 'IN' else 'US'}</span></h1>"
            '<p class="small muted">Checked companies in each layer of the theme</p>' + svg + f'<p class="sr-only">{html.escape(label)}</p>'
            + _caption("company filings and the exchange's industry classification", day_text(v["day"]) or "the map's date", back,
                       f"The {v['label']} theme on StratLab"))
    return HTMLResponse(_doc(f"{v['label']} theme · StratLab", body), headers={"Cache-Control": THEME_CACHE})
