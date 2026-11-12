"""Public research share links (bet 3): a signed-in person makes a link to a deep dive or a theme they opened, and anyone can
open it at /r/<token> without signing in.

A link is a frozen, dated teaser, not the research itself (owner, 12 Nov: "the public stuff is only to attract people"): the title,
the date, a few headline facts (a company's key numbers from its public page; a theme's layers and how many checked companies each
holds) and the first one or two sections, then "See the full research on StratLab". It holds no user data: no name, email,
watchlist, holdings or notes, and no id (the owner's list of links is kept apart, under the owner). Every word goes through
`public_words` (no advice wording, no data vendor named). Pages are server-rendered HTML in the public pages' look, kept out of
search (noindex): a snapshot goes stale.

Storage: the snapshot in app_settings under rshare:<token> (a few KB); the owner's list under rshares:user:<uid> (newest
MAX_PER_USER kept: making one more takes down the oldest). Turning a link off removes its snapshot at once; the link then answers
the "not available" page with 404. Making links counts against the plan's share_links_per_month and is throttled per hour."""
import html
import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from . import db, deepdive, plans, public, stock_pages
from .auth import current_profile
from .branding import public_text
from .config import settings
from .intel import theme_library
from .intel.grounding import ADVICE
from .responses import err, ok

router = APIRouter(tags=["share"])
page_router = APIRouter(include_in_schema=False)

TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,32}\Z")
TOKEN_BYTES = 18                   # 144 random bits: 24 URL-safe characters, never guessed
MAX_PER_USER = 200                 # links kept on one account's list (the oldest beyond go)
PER_HOUR = 30                      # links one account may make in an hour, whatever its plan
USAGE = "share_link"
SECTION_MAX = 600                  # characters of one section's text on a link
SEGMENTS_MAX = 6
CACHE = "public, max-age=60"       # a link turned off stops being served within a minute (as /v/ and /c/ links)
HEADERS = {"Cache-Control": CACHE, "X-Robots-Tag": "noindex, follow"}
IST = timezone(timedelta(hours=5, minutes=30))

# advice and promotion beyond grounding.ADVICE: no "top picks", no "beneficiaries", no rankings by attractiveness (bet 3, 3.4)
PROMO = re.compile(r"\b(top picks?|beneficiar\w*|best (?:stocks?|bets?|buys?|picks?)|recommend\w*|multi-?baggers?|must[- ]own|"
                   r"outperform\w*|underperform\w*|strong buy|rating)\b", re.I)
_SENT = re.compile(r"(?<=[.!?])\s+")

_made: dict[str, list[float]] = {}
_made_lock = threading.Lock()
_list_lock = threading.Lock()

# set by main.py: (market, symbol) -> the company's card facts from its public page (company_cards.card), raising the API's own
# 404/503 errors for a company with no page or facts not ready
_card = None


def setup(card) -> None:
    global _card
    _card = card


def public_words(text, n: int | None = None) -> str:
    """Text fit for a public page: every sentence with advice or promotion wording left out, data vendors never named, cut at
    `n` characters on a word."""
    t = " ".join(str(text or "").split())
    t = " ".join(x for x in _SENT.split(t) if x and not ADVICE.search(x) and not PROMO.search(x))
    t = public_text(t)
    if n and len(t) > n:
        t = t[:n - 1].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
    return t


def today() -> str:
    return datetime.now(IST).date().isoformat()


def day_text(iso) -> str:
    """'12 Nov 2026' from an ISO date or time; '' when there is none."""
    s = str(iso or "")[:10]
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return ""
    return f"{d.day} {d.strftime('%b %Y')}"


# ---------- snapshots: what a link shows, and nothing else ----------
def deep_snapshot(card: dict, reads: dict | None) -> dict:
    """A company's deep dive as a teaser: its name, key numbers from its public page and the first sections of the stored read of
    its own documents (what it does, its segments by name). No quotes beyond those, no plans, no report card, no checklist."""
    region, sym = card["region"], card["symbol"]
    facts = [["Last price", card["price"]]] if card.get("price") else []
    facts += [[k, v] for k, v in card.get("facts") or []]
    if card.get("range"):
        facts.append(["1-year range", card["range"]])
    sections = []
    b = (reads or {}).get("business") if isinstance((reads or {}).get("business"), dict) else None
    if b:
        summary = public_words(b.get("summary"), SECTION_MAX)
        if summary:
            sections.append({"title": "What the company does, from its own documents", "text": summary, "items": []})
        segs = []
        for s in (b.get("segments") or [])[:SEGMENTS_MAX]:
            if not isinstance(s, dict) or not public_words(s.get("name"), 80):
                continue
            share = s.get("share_pct")
            segs.append(public_words(s["name"], 80) + (f" ({share:g}% of revenue)" if isinstance(share, (int, float)) and 0 < share <= 100 else ""))
        if segs:
            sections.append({"title": "Its businesses", "text": "", "items": segs})
    return {"v": 1, "kind": "deep", "region": region, "symbol": sym, "title": public_words(card.get("name") or sym, 120),
            "subtitle": public_words(" · ".join(x for x in (sym, card.get("sector"), card.get("exchange")) if x), 160),
            "made": today(), "as_of": str(card.get("as_of") or "")[:40], "facts": [[public_words(k, 40), public_words(v, 60)] for k, v in facts][:8],
            "sections": sections[:2], "layers": [],
            "app": f"/research/{region}/{sym}/deep", "page": stock_pages.path(region, sym)}


def checked(c: dict) -> bool:
    """A company shown publicly as in a theme: one whose own words were checked against its layer, or one in the theme's official
    industry (the exchange's classification). A company placed by the map and not yet confirmed is never shown."""
    return bool(c.get("ticker")) and (c.get("verified") is True or (c.get("basis") == "industry" and c.get("base") is True))


def theme_layers(payload: dict) -> list[dict]:
    """Each layer of the theme's map with its checked companies, layers with none left out."""
    out = []
    for v in payload.get("value_chain") or []:
        if not isinstance(v, dict):
            continue
        cos, seen = [], set()
        for c in v.get("companies") or []:
            if isinstance(c, dict) and checked(c) and c["ticker"] not in seen:
                seen.add(c["ticker"])
                cos.append(c)
        name = public_words(v.get("layer"), 80)
        if cos and name:
            out.append({"name": name, "companies": cos})
    return out


def theme_snapshot(region: str, got: dict) -> dict:
    """A stored theme as a teaser: its name, when its map was made, a short description, and its layers with how many checked
    companies each holds. No company list, no figures, no tailwinds or risks."""
    payload, entry = got["payload"], got["entry"]
    label = public_words(entry.get("label") or payload.get("sector") or got["name"], 120)
    layers = theme_layers(payload)
    n = len({c["ticker"] for v in layers for c in v["companies"]})
    sections = []
    summary = public_words(payload.get("summary"), SECTION_MAX)
    if summary:
        sections.append({"title": "About the theme", "text": summary, "items": []})
    from . import public_themes
    slug = public_themes.slug(got["name"])
    return {"v": 1, "kind": "theme", "region": region, "slug": slug, "title": label,
            "subtitle": f"{'India' if region == 'IN' else 'US'} · {n} checked compan{'y' if n == 1 else 'ies'} in {len(layers)} layer{'' if len(layers) == 1 else 's'}",
            "made": today(), "as_of": day_text(datetime.fromtimestamp(float(got.get("at") or 0), timezone.utc).isoformat()) if got.get("at") else "",
            "facts": [], "sections": sections, "layers": [{"name": v["name"], "n": len(v["companies"])} for v in layers],
            "app": f"/research/themes?q={quote(got['name'])}&region={region}", "page": public_themes.path(region, slug)}


SNAP_KEYS = {"v", "kind", "region", "symbol", "slug", "title", "subtitle", "made", "as_of", "facts", "sections", "layers", "app", "page"}


# ---------- storing, listing, turning off ----------
def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def _key(token: str) -> str:
    return f"rshare:{token}"


def _list_key(uid: str) -> str:
    return f"rshares:user:{uid}"


def _rows(uid: str) -> list[dict]:
    try:
        rows = json.loads(db.get_setting(_list_key(uid)) or "[]")
    except (ValueError, TypeError):
        return []
    return [r for r in rows if isinstance(r, dict) and TOKEN.match(str(r.get("t") or ""))] if isinstance(rows, list) else []


def publish(uid: str, snap: dict) -> str:
    """Keep the snapshot under a new random token and note it on the owner's list; returns the token."""
    snap = {k: v for k, v in snap.items() if k in SNAP_KEYS}
    token = new_token()
    db.set_setting(_key(token), json.dumps(snap, ensure_ascii=False))
    with _list_lock:
        rows = _rows(uid)
        rows.append({"t": token, "kind": snap["kind"], "title": snap["title"], "region": snap["region"], "made": snap["made"], "on": True})
        for old in rows[:-MAX_PER_USER]:
            db.delete_setting(_key(old["t"]))
        db.set_setting(_list_key(uid), json.dumps(rows[-MAX_PER_USER:], ensure_ascii=False))
    return token


def load(token: str) -> dict | None:
    if not TOKEN.match(token or ""):
        return None
    try:
        got = json.loads(db.get_setting(_key(token)) or "null")
    except (ValueError, TypeError):
        return None
    return got if isinstance(got, dict) and got.get("kind") in ("deep", "theme") and got.get("title") else None


def mine(uid: str) -> list[dict]:
    """The owner's links, newest first, each with whether it is still on."""
    return [{"token": r["t"], "url": url(r["t"]), "kind": r.get("kind"), "title": r.get("title"), "region": r.get("region"),
             "made": r.get("made"), "on": bool(r.get("on"))} for r in reversed(_rows(uid))]


def turn_off(uid: str, token: str) -> bool:
    """Turn one of the owner's links off: its snapshot goes at once; it stays on the list, marked off. False when it isn't theirs."""
    if not TOKEN.match(token or ""):
        return False
    with _list_lock:
        rows = _rows(uid)
        hit = next((r for r in rows if r["t"] == token), None)
        if hit is None:
            return False
        hit["on"] = False
        db.delete_setting(_key(token))
        db.set_setting(_list_key(uid), json.dumps(rows, ensure_ascii=False))
    return True


def url(token: str) -> str:
    return f"{settings.PUBLIC_SITE_URL}/r/{token}"


# ---------- the plan's monthly count and the hourly throttle ----------
def month_start_iso() -> str:
    return datetime.now(IST).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def used(profile: dict) -> int:
    return db.count_usage(profile["id"], USAGE, month_start_iso())


def check_quota(profile: dict) -> None:
    plan = plans.plan_of(profile)
    limit = plans.share_links(plan)
    if limit is not None and used(profile) >= limit:
        err(402, "share_limit", plans.limit_message(plan, "share_links_per_month", f"You've made {limit} share link{'' if limit == 1 else 's'} this month",
                                                    "share links", monthly=True, after="Links you've already made stay open."))


def throttle(uid: str, now: float | None = None) -> None:
    now = time.time() if now is None else now
    with _made_lock:
        hits = [t for t in _made.get(uid, []) if now - t < 3600]
        if len(hits) >= PER_HOUR:
            err(429, "slow_down", "That's a lot of share links in an hour. Try again later.")
        _made[uid] = hits + [now]
        if len(_made) > 20000:
            _made.clear()


def _make(profile: dict, snap: dict) -> dict:
    token = publish(profile["id"], snap)
    db.add_usage(profile["id"], USAGE)
    return ok({"token": token, "url": url(token), "title": snap["title"], "kind": snap["kind"]})


# ---------- routes ----------
@router.post("/research/share/deep/{region}/{symbol}")
def share_deep(region: str, symbol: str, profile=Depends(current_profile)):
    """A share link to a company's deep dive: a dated teaser of its key numbers and the first sections of its stored read."""
    region = (region or "").upper()
    if region not in ("IN", "US") or not re.fullmatch(r"[A-Za-z0-9&._-]{1,20}", symbol or ""):
        err(404, "not_found", "There's no public page for that company to share.")
    throttle(profile["id"])
    check_quota(profile)
    card = _card(region, symbol)
    key = f"US:{card['symbol']}" if card["region"] == "US" else card["symbol"]
    return _make(profile, deep_snapshot(card, deepdive.stored(key)))


@router.post("/research/share/theme")
def share_theme(q: str = "", region: str = "IN", profile=Depends(current_profile)):
    """A share link to a theme in StratLab's library: a dated teaser of its layers and how many checked companies each holds."""
    region = "US" if (region or "").upper() == "US" else "IN"
    q = (q or "")[:120]
    got = theme_library.stored(region, q) if q.strip() else None
    if not got or not theme_layers(got["payload"]):
        err(404, "not_stored", "Only a theme whose map is finished and checked can be shared. Open it, wait for the checks, then share it.")
    throttle(profile["id"])
    check_quota(profile)
    return _make(profile, theme_snapshot(region, got))


@router.get("/research/shares")
def my_shares(profile=Depends(current_profile)):
    """The person's share links, newest first, with this month's count and the plan's limit."""
    plan = plans.plan_of(profile)
    return ok({"links": mine(profile["id"]), "used": used(profile), "limit": plans.share_links(plan)})


@router.delete("/research/shares/{token}")
def turn_off_share(token: str, profile=Depends(current_profile)):
    if not turn_off(profile["id"], token):
        err(404, "not_found", "That link isn't one of yours.")
    return ok({"on": False})


@page_router.get("/r/{token}")
def share_page(token: str):
    snap = load(token)
    if not snap:
        return HTMLResponse(public.gone_html(), status_code=404, headers=public.GONE_HEADERS)
    return HTMLResponse(render(token, snap), headers=HEADERS)


# ---------- the page ----------
FACTS_LINE = "Facts from company filings and reported numbers, for research and education; not a recommendation."


def description(snap: dict) -> str:
    if snap["kind"] == "theme":
        bits = [snap.get("subtitle") or ""] + [f"{x['name']} ({x['n']})" for x in snap.get("layers") or []][:4]
    else:
        bits = [f"{k} {v}" for k, v in snap.get("facts") or []][:4]
    return public_words(f"{snap['title']}: " + "; ".join(b for b in bits if b) + ". A dated snapshot shared from StratLab.", 300)


def render(token: str, snap: dict) -> str:
    e = html.escape
    site = settings.PUBLIC_SITE_URL
    app = site + (snap.get("app") or "/")
    title = f"{snap['title']}: {'theme' if snap['kind'] == 'theme' else 'deep dive'} snapshot · StratLab"
    head = stock_pages._head(title, description(snap), url(token), robots="noindex,follow", og_type="article")
    made = day_text(snap.get("made"))
    as_of = snap.get("as_of") or ""
    what = "theme map" if snap["kind"] == "theme" else "deep dive"
    body = (f'<p class="muted small" data-shared>Shared from StratLab · a snapshot of this {what} taken on {e(made)}'
            + (f" · {'map made' if snap['kind'] == 'theme' else 'prices as of'} {e(as_of)}" if as_of else "") + "</p>"
            f"<h1>{e(snap['title'])}</h1>" + (f'<p class="muted">{e(snap["subtitle"])}</p>' if snap.get("subtitle") else ""))
    facts = snap.get("facts") or []
    if facts:
        cols = " c3" if len(facts) % 3 == 0 and len(facts) % 4 else ""
        body += (f'<section class="card figs" aria-label="Key numbers"><div class="tiles{cols}">'
                 + "".join(f'<div class="stat"><span>{e(k)}</span><b>{e(v)}</b><small></small></div>' for k, v in facts) + "</div></section>")
    layers = snap.get("layers") or []
    if layers:
        body += ('<section class="card"><h2>Layers of the theme</h2><ul class="plain">'
                 + "".join(f'<li><b>{e(x["name"])}</b> <span class="muted">· {x["n"]} checked compan{"y" if x["n"] == 1 else "ies"}</span></li>' for x in layers)
                 + "</ul></section>")
    for s in snap.get("sections") or []:
        body += f'<section class="card"><h2>{e(s["title"])}</h2>' + (f"<p>{e(s['text'])}</p>" if s.get("text") else "")
        body += ('<ul class="plain">' + "".join(f"<li>{e(i)}</li>" for i in s.get("items") or []) + "</ul>") if s.get("items") else ""
        body += "</section>"
    more = ("every company in each layer with its figures, the tailwinds and risks with their sources, the news and slides"
            if snap["kind"] == "theme" else "ten years of reported numbers, growth and margins, plans in the company's own words, the report card and checklist")
    page = snap.get("page")
    body += (f'<section class="card" data-cta><h2>See the full research on StratLab</h2><p>This is a dated snapshot. Sign in for the live version: {e(more)}.</p>'
             f'<div class="ctas"><a class="btn" href="{e(app)}">See the full research on StratLab</a>'
             + (f'<a class="btn ghost" href="{e(site + page)}">{"The theme" if snap["kind"] == "theme" else "The company"}\'s public page</a>' if page else "")
             + f'</div></section><p class="note">{e(FACTS_LINE)} Figures can have changed since the snapshot was taken.</p>')
    return stock_pages._page(head, app, body)
