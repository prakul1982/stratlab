"""Public verdict links: a frozen, anonymous snapshot of one experiment that anyone can open.

Sharing stores the snapshot (no user details, no rules) and the share card image in
app_settings under the link's token, so a later edit or re-run doesn't change what was
shared. Turning the link off, or deleting the experiment, removes both."""
import base64
import binascii
import html
import json
import re
import secrets
import struct

from . import db
from .config import settings

TOKEN = re.compile(r"^[A-Za-z0-9_-]{6,24}$")
MAX_IMAGE = 2_000_000
MAX_SIDE = 2400                      # share cards are drawn at 2400x1260; anything wider or taller isn't one
PNG_START = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
PNG_END = b"\x00\x00\x00\x00IEND\xaeB`\x82"


# the question a notebook is given from its idea's own words: 'Does "buy TCS when the 20-day SMA crosses above…" work?'
_RULES_QUESTION = re.compile(r'^Does ".+" work(?: on [^?]+)?\?$', re.S)


def own_question(q: str | None) -> str:
    """The notebook's question as a shared page may show it: one the person wrote, never the one made from the idea's words,
    which are the rules themselves (R11C-016: "The strategy's rules are private" under the rules, quoted in "The
    question")."""
    q = (q or "").strip()
    return "" if _RULES_QUESTION.match(q) else q


def snapshot(nb: dict, exp: dict) -> dict:
    v = exp.get("verdict") or {}
    inst = exp.get("instrument") or {}
    s = exp.get("series") or {}
    g = exp.get("group")
    return {
        "name": nb.get("name"), "question": own_question(nb.get("question")),
        "instrument": {k: inst.get(k) for k in ("symbol", "name", "market", "currency", "type")},
        "tf": exp.get("tf"), "range": exp.get("range"), "days": exp.get("days"), "v": exp.get("v"),
        "side": (exp.get("strategy") or {}).get("side", "long"), "created_at": exp.get("created_at"),
        "verdict": {k: v.get(k) for k in ("verdict", "headline", "summary", "passed", "total")}
                   | {"checks": [{k: c.get(k) for k in ("id", "title", "status", "detail")} for c in v.get("checks") or []]},
        "stats": exp.get("stats"),
        "series": {"t": s.get("t") or [], "equity": s.get("equity") or [], "buy_hold": s.get("buy_hold") or [], "split": s.get("split")},
        "group": None if not g else {"name": g.get("name"), "max_open": g.get("max_open"),
                                      "members": [{k: m.get(k) for k in ("symbol", "trades", "pnl", "win", "buy_hold")} for m in g.get("members") or []]},
    }


def decode_image(data: str | None) -> str | None:
    """A base64 PNG from the browser, checked; None if there's no usable image."""
    if not data:
        return None
    raw = data.split(",", 1)[1] if data.startswith("data:") else data
    try:
        png = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not is_card_png(png):
        return None
    return base64.b64encode(png).decode()


def is_card_png(png: bytes) -> bool:
    """A whole PNG of a share card's size: the PNG header, a picture no bigger than MAX_SIDE each way (so a small file
    can't unpack into a huge picture for whoever previews it), and nothing after its end."""
    if len(png) > MAX_IMAGE or len(png) < 45 or not png.startswith(PNG_START) or not png.endswith(PNG_END):
        return False
    width, height = struct.unpack(">II", png[16:24])
    return 0 < width <= MAX_SIDE and 0 < height <= MAX_SIDE


def publish(nb: dict, exp: dict, image: str | None) -> str:
    token = exp.get("public") or secrets.token_urlsafe(8)
    db.set_setting(f"share:{token}", json.dumps(snapshot(nb, exp)))
    img = decode_image(image)
    if img:
        db.set_setting(f"shareimg:{token}", img)
    return token


def unpublish(token: str | None):
    if token and TOKEN.match(token):
        db.delete_setting(f"share:{token}")
        db.delete_setting(f"shareimg:{token}")


def load(token: str) -> dict | None:
    if not TOKEN.match(token or ""):
        return None
    raw = db.get_setting(f"share:{token}")
    snap = json.loads(raw) if raw else None
    if isinstance(snap, dict) and snap.get("question"):
        snap["question"] = own_question(snap["question"])        # a link shared before the rules were kept out of it
    if isinstance(snap, dict) and isinstance(snap.get("verdict"), dict):
        from .engine.verdict import restated                     # a link shared with a claim for a headline (R11C-009)
        snap["verdict"] = restated(snap["verdict"], snap.get("stats"))
    return snap


def image(token: str) -> bytes | None:
    if not TOKEN.match(token or ""):
        return None
    raw = db.get_setting(f"shareimg:{token}")
    return base64.b64decode(raw) if raw else None


def url(token: str) -> str:
    return f"{settings.PUBLIC_SITE_URL}/v/{token}"


def preview_html(token: str, snap: dict, has_image: bool) -> str:
    """A tiny page for link previews (WhatsApp, X, LinkedIn read these tags); people are sent on to the app."""
    e = html.escape
    v = snap.get("verdict") or {}
    inst = (snap.get("instrument") or {}).get("symbol") or ""
    title = f"{v.get('headline', 'Verdict')} {snap.get('name') or ''} on {inst}".strip()
    desc = v.get("summary") or "An honest backtest verdict from StratLab."
    site = settings.PUBLIC_SITE_URL
    img = f"{site}/v/{token}.png" if has_image else f"{site}/og-image.png"
    dest = f"{site}/verdict/{token}"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{e(title)} · StratLab</title>
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="StratLab">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url(token))}"><meta property="og:image" content="{e(img)}">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{e(img)}">
<meta http-equiv="refresh" content="0; url={e(dest)}">
</head><body><p><a href="{e(dest)}">Open the verdict on StratLab</a></p></body></html>"""
