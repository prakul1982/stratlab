"""Shareable company fact cards: an image of one company's facts (name, sector, price, 1-year range and a few key
numbers) with a public link that previews as that image on WhatsApp, X and LinkedIn, and opens the company's public
/stocks page.

The facts are the public company page's own (never AI), so a card says nothing that page doesn't. The browser
draws the image, the way verdict share cards are made; the server keeps it with the card under a random token. Each
user has one link per company: sharing again refreshes it. The link carries the sharer's invite code, so someone who
signs up from it counts as invited."""
import base64
import binascii
import json
import re
import secrets
from html import escape as e

from . import db, referrals, stock_pages
from .config import settings
from .public import decode_image

TOKEN = re.compile(r"^[A-Za-z0-9_-]{6,24}$")
FACTS = 4


def _region(market: str | None) -> str | None:
    return stock_pages.REGIONS.get((market or "").strip().lower())


def card(f: dict, region: str, symbol: str) -> dict:
    """The card's words and numbers, ready to draw: plain facts from the company page."""
    ind = [x for x in f.get("industry") or [] if x]
    unit = f.get("unit") or ""
    growth = (f.get("growth") or {}).get("sales_cagr_3y")
    rows = [(f"Market cap ({unit})", stock_pages._fmt(f.get("market_cap"), 0)), ("P/E", stock_pages._fmt(f.get("pe"))),
            ("Return on equity", stock_pages._fmt(f.get("roe"), 1, "%")),
            ("Sales growth a year, 3 years", stock_pages._fmt(growth, 1, "%")),
            ("Operating margin", "–" if f.get("bank") else stock_pages._fmt(f.get("opm"), 1, "%")),
            ("Net margin", stock_pages._fmt(f.get("net_margin"), 1, "%")),
            ("Dividend yield", stock_pages._fmt(f.get("div_yield"), 2, "%"))]
    low, high = stock_pages._num(f.get("low52")), stock_pages._num(f.get("high52"))
    return {
        "region": region, "symbol": symbol, "name": f.get("name") or symbol,
        "sector": " · ".join(ind[:2]) if ind else "", "exchange": f.get("exchange") or "",
        "currency": f.get("currency") or ("USD" if region == "US" else "INR"),
        "price": stock_pages._money(f, f.get("price")) if stock_pages._num(f.get("price")) is not None else None,
        "range": f"{stock_pages._money(f, low)} to {stock_pages._money(f, high)}" if low is not None and high is not None else None,
        "as_of": stock_pages._date(f.get("price_at")) or stock_pages._date(f.get("built_at")) or None,
        "facts": [[k, v] for k, v in rows if v != "–"][:FACTS],
        "page": settings.PUBLIC_SITE_URL + stock_pages.path(region, symbol),
    }


def find(market: str, symbol: str) -> tuple[str, str, dict] | None:
    """(region, page symbol, company) for a company with a public page; None otherwise."""
    region = _region(market)
    hit = stock_pages.find(region, symbol) if region else None
    return (region, hit[0], hit[1]) if hit else None


def publish(uid: str, c: dict, image: str | None, ref: str | None) -> str:
    """Store the card (and its image) under this user's link for the company; returns the link's token."""
    mine = f"cardtok:{uid}:{c['region']}:{c['symbol']}"
    token = db.get_setting(mine)
    if not token or not TOKEN.match(token):
        token = secrets.token_urlsafe(8)
        db.set_setting(mine, token)
    db.set_setting(f"card:{token}", json.dumps({**c, "ref": ref}))
    img = decode_image(image)
    if img:
        db.set_setting(f"cardimg:{token}", img)
    return token


def load(token: str) -> dict | None:
    if not TOKEN.match(token or ""):
        return None
    try:
        raw = db.get_setting(f"card:{token}")
        got = json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None
    return got if isinstance(got, dict) and got.get("symbol") and got.get("region") in ("IN", "US") else None


def image(token: str) -> bytes | None:
    if not TOKEN.match(token or ""):
        return None
    raw = db.get_setting(f"cardimg:{token}")
    try:
        return base64.b64decode(raw) if raw else None
    except (binascii.Error, ValueError):
        return None


def url(token: str) -> str:
    return f"{settings.PUBLIC_SITE_URL}/c/{token}"


def destination(c: dict) -> str:
    """The company's public page, with the sharer's invite code so a sign-up from it counts."""
    dest = settings.PUBLIC_SITE_URL + stock_pages.path(c["region"], c["symbol"])
    ref = c.get("ref")
    return dest + (f"?ref={ref}" if referrals.CODE.match(str(ref or "")) else "")


def description(c: dict) -> str:
    bits = []
    if c.get("price"):
        bits.append(f"Last price {c['price']}")
    if c.get("range"):
        bits.append(f"1-year range {c['range']}")
    bits += [f"{k} {v}" for k, v in c.get("facts") or []]
    return (". ".join(bits) + ". Facts, not advice.").lstrip(". ")[:300]


def preview_html(token: str, c: dict, has_image: bool) -> str:
    """A tiny page for link previews (WhatsApp, X and LinkedIn read these tags); people go on to the company page."""
    site = settings.PUBLIC_SITE_URL
    title = f"{c.get('name') or c['symbol']} ({c['symbol']}): the facts on StratLab"
    desc = description(c)
    img = f"{site}/c/{token}.png" if has_image else f"{site}/og-image.png"
    dest = destination(c)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="noindex,follow">
<link rel="canonical" href="{e(site + stock_pages.path(c['region'], c['symbol']))}">
<meta property="og:type" content="website"><meta property="og:site_name" content="StratLab">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url(token))}"><meta property="og:image" content="{e(img)}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{e(title)}">
<meta name="twitter:description" content="{e(desc)}"><meta name="twitter:image" content="{e(img)}">
<meta http-equiv="refresh" content="0; url={e(dest)}">
</head><body><p><a href="{e(dest)}">Open {e(c.get('name') or c['symbol'])} on StratLab</a></p></body></html>"""
