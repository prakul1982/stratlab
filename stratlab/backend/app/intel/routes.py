"""/research API: company profiles, charts, quotes, market pulse, sector maps, comparisons,
AI reads and the watchlist. Every third-party call happens here on the server."""
import json
import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db
from ..branding import public_research, public_text
from ..ai_providers import AIBusy, AIError
from ..auth import current_profile
from ..config import settings
from ..kite_service import IST
from ..plans import has_indicators
from . import ai as A
from . import key_facts
from .company import Research
from .net import SourceError

router = APIRouter(prefix="/research", tags=["research"])
hub: Research | None = None
_ai = (None, None)     # (gemini, anthropic) callables, set by setup()


def setup(research: Research, gemini, anthropic):
    global hub, _ai
    hub, _ai = research, (gemini, anthropic)


def err(status: int, code: str, message: str):
    raise HTTPException(status, {"code": code, "message": public_text(message)})


def _safe(o):
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_safe(v) for v in o]
    return o


def ok(data) -> JSONResponse:
    return JSONResponse(content=_safe(public_research(data)))


def region_of(region: str) -> str:
    r = region.upper()
    if r not in ("IN", "US"):
        err(400, "bad_region", "Research covers India (IN) and the US (US).")
    return r


def symbol_of(symbol: str) -> str:
    s = symbol.strip().upper()
    # a letter or digit first (or ^ for an index): "..", "-x" and the like never reach a data source's address
    if not s or len(s) > 20 or not (s[0].isalnum() or s[0] == "^") or not all(ch.isalnum() or ch in "&-._^" for ch in s):
        err(400, "bad_symbol", "That doesn't look like a ticker.")
    return s


def source_call(fn):
    try:
        return fn()
    except SourceError as e:
        err(503 if e.busy else 502, "source_error", str(e))


def ai_call(profile, kind: str, key: tuple, ttl: float, refresh: bool, build):
    """Serve an AI read from the shared cache, or build it within the user's daily allowance."""
    if not refresh and A.peek(kind, key):
        return A.cached(kind, key, ttl, False, build)[0]
    since = (datetime.now(IST) - timedelta(days=1)).isoformat()
    limit = settings.RESEARCH_AI_PER_DAY
    if db.count_usage(profile["id"], "research_ai", since) >= limit:
        err(429, "research_ai_limit", f"You've used {limit} fresh AI reads today. Cached ones still work; try again tomorrow.")
    try:
        out, fresh = A.cached(kind, key, ttl, refresh, build)
    except AIBusy as e:
        err(503, "ai_busy", str(e))
    except AIError as e:          # there's no idea to rephrase on a research page: the reader can only try again
        err(422, "ai_failed", str(e).replace("Try rephrasing the idea.", "Press Refresh to try again."))
    if fresh:
        db.add_usage(profile["id"], "research_ai")
    return out


# ---------- data ----------
@router.get("/search")
def search(q: str = "", region: str = "IN", profile=Depends(current_profile)):
    return ok(source_call(lambda: hub.search(q[:40], region_of(region))))


@router.get("/company/{region}/{symbol}")
def company(region: str, symbol: str, profile=Depends(current_profile)):
    """One company's page. `as_of` is when its prices were read, for the page's "as of" line."""
    c = source_call(lambda: hub.company(region_of(region), symbol_of(symbol)))
    return ok({**c, "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes")})


@router.get("/chart/{region}/{symbol}")
def chart(region: str, symbol: str, range: str = "1y", profile=Depends(current_profile)):
    return ok(source_call(lambda: hub.chart(region_of(region), symbol_of(symbol), range)))


@router.get("/quotes")
def quotes(region: str = "IN", symbols: str = "", profile=Depends(current_profile)):
    syms = [symbol_of(s) for s in symbols.split(",") if s.strip()][:24]
    return ok(source_call(lambda: hub.quotes(region_of(region), syms)))


@router.get("/pulse")
def pulse(region: str = "IN", focus: str = "", profile=Depends(current_profile)):
    r = region_of(region)
    indices = source_call(lambda: hub.indices(r))
    try:
        news = hub.headlines(r, focus[:60])
    except SourceError:
        news = []
    return ok({"indices": indices, "headlines": news})


# ---------- AI reads ----------
@router.get("/company/{region}/{symbol}/ai")
def company_ai(region: str, symbol: str, refresh: bool = False, profile=Depends(current_profile)):
    r, s = region_of(region), symbol_of(symbol)
    pro = has_indicators(profile["_plan"])       # which indicators the read may mention; the facts are the same

    def build():
        c = source_call(lambda: hub.company(r, s))
        return A.company(c, _ai, pro, company_key_facts(r, c))
    read = ai_call(profile, "company", (r, s, pro, datetime.now(IST).date().isoformat()), 12 * 3600, refresh, build)
    return ok(A.clean_company(read))


def company_key_facts(region: str, c: dict) -> list[dict]:
    """The plain-number rows next to the AI read, from the reported results (India) or the page's own numbers (US)
    and a year of daily prices. A source that's down only leaves its lines out."""
    reported = bars = None
    if region == "IN":
        try:
            reported = hub.screener.company(c.get("bse_code") or c["symbol"])
        except Exception:
            reported = None
    try:
        bars = hub.chart(region, c["symbol"], "1y").get("candles")
    except Exception:
        bars = None
    return key_facts.build(c, reported, bars)


@router.get("/pulse/ai")
def pulse_ai(region: str = "IN", focus: str = "", refresh: bool = False, profile=Depends(current_profile)):
    r, f = region_of(region), focus.strip()[:60]
    hour = datetime.now(IST).strftime("%Y-%m-%d %H")

    def build():
        indices = source_call(lambda: hub.indices(r))
        try:
            news = hub.headlines(r, f)
        except SourceError:
            news = []
        return A.pulse(r, f, indices, news, _ai)
    return ok(ai_call(profile, "pulse", (r, f.lower(), hour), 3600, refresh, build))


@router.get("/sector")
def sector(q: str, region: str = "IN", refresh: bool = False, profile=Depends(current_profile)):
    r, theme = region_of(region), " ".join(q.split())[:80]
    if len(theme) < 2:
        err(400, "bad_theme", "Type a sector or theme, like \"India defence\" or \"AI data centers\".")
    return ok(ai_call(profile, "sector", (r, theme.lower()), 24 * 3600, refresh, lambda: A.sector(theme, r, _ai)))


@router.get("/compare")
def compare(a: str, b: str, region: str = "IN", refresh: bool = False, profile=Depends(current_profile)):
    r, sa, sb = region_of(region), symbol_of(a), symbol_of(b)
    if sa == sb:
        err(400, "same_symbol", "Pick two different companies.")
    ca = source_call(lambda: hub.company(r, sa))
    cb = source_call(lambda: hub.company(r, sb))
    try:
        verdict = ai_call(profile, "compare", (r, sa, sb, datetime.now(IST).date().isoformat()), 12 * 3600, refresh,
                          lambda: A.compare(ca, cb, _ai))
    except HTTPException as e:
        verdict = {"error": (e.detail or {}).get("message") if isinstance(e.detail, dict) else str(e.detail)}
    return ok({"a": ca, "b": cb, "ai": verdict})


# ---------- watchlist (one row per user in app_settings) ----------
class WatchItem(BaseModel):
    region: str = Field(pattern="^(IN|US)$")
    symbol: str = Field(min_length=1, max_length=20)
    name: str | None = Field(None, max_length=120)


class WatchReq(BaseModel):
    items: list[WatchItem] = Field(default_factory=list, max_length=100)


def _watch_key(profile) -> str:
    return f"watchlist:{profile['id']}"


@router.get("/watchlist")
def get_watchlist(profile=Depends(current_profile)):
    raw = db.get_setting(_watch_key(profile))
    try:
        return {"items": json.loads(raw)["items"] if raw else []}
    except (ValueError, KeyError, TypeError):
        return {"items": []}


@router.put("/watchlist")
def put_watchlist(req: WatchReq, profile=Depends(current_profile)):
    seen, items = set(), []
    for i in req.items:
        k = (i.region, i.symbol.upper())
        if k not in seen:
            seen.add(k)
            items.append({"region": i.region, "symbol": symbol_of(i.symbol), "name": i.name})
    before = get_watchlist(profile)["items"]
    before = before if isinstance(before, list) else []
    db.set_setting(_watch_key(profile), json.dumps({"items": items}))
    had = {(i.get("region"), str(i.get("symbol") or "").upper()) for i in before if isinstance(i, dict)}
    if any((i["region"], i["symbol"].upper()) not in had for i in items):     # a stock added, not only removed
        from .. import invite_rewards
        invite_rewards.safe_touch(profile, "watchlist")
    return {"items": items}
