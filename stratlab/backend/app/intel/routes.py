"""/research API: company profiles, charts, quotes, market pulse, sector maps, comparisons,
AI reads and the watchlist. Every third-party call happens here on the server."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db
from ..branding import public_research
from ..responses import err, safe
from ..ai_providers import AIBusy, AIError
from ..auth import current_profile
from ..config import settings
from ..kite_service import IST
from ..plans import has_indicators
from . import ai as A
from . import grounding, key_facts
from .company import Research, with_dividend_yield
from .net import NotFound, SourceError

router = APIRouter(prefix="/research", tags=["research"])
hub: Research | None = None
_ai = (None, None)     # (gemini, anthropic) callables, set by setup()


def setup(research: Research, gemini, anthropic):
    global hub, _ai
    hub, _ai = research, (gemini, anthropic)


def ok(data) -> JSONResponse:
    return JSONResponse(content=safe(public_research(data)))


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
    except NotFound as e:
        err(404, "not_found", str(e))
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


def prices_as_of(c: dict) -> str:
    """When a company page's price is from: the time of the quote's last trade (the exchange's own stamp), never the
    moment of asking. A quote without one is read as of now."""
    now = datetime.now(timezone.utc)
    at = (c.get("quote") or {}).get("at")
    try:
        t = datetime.fromisoformat(at) if isinstance(at, str) else None
    except ValueError:
        t = None
    if t is None:
        return now.isoformat(timespec="minutes")
    return min(t if t.tzinfo else t.replace(tzinfo=IST), now).isoformat(timespec="minutes")


def market_open(region: str, now: datetime | None = None) -> bool:
    """Whether the company's market is trading now (its hours, on one of its trading days): out of hours the price is
    the last close and the page says so, instead of calling a standing price "today's"."""
    from zoneinfo import ZoneInfo
    from ..data.calendar import is_trading_day
    from ..data.markets import BY_ID
    m = BY_ID.get(region)
    if not m or not m.get("hours"):
        return False
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(m["tz"]))
    return is_trading_day(region, local.date()) and m["hours"]["open"] <= local.strftime("%H:%M") < m["hours"]["close"]


@router.get("/company/{region}/{symbol}")
def company(region: str, symbol: str, profile=Depends(current_profile)):
    """One company's page. `as_of` is when its prices were read, for the page's "as of" line; `market_open` whether
    its market is trading now (else the price is the last close)."""
    r = region_of(region)
    c = page_figures(r, source_call(lambda: hub.company(r, symbol_of(symbol))))
    return ok({**c, "as_of": prices_as_of(c), "market_open": market_open(r)})


def page_figures(region: str, c: dict) -> dict:
    """The company page's own figures, as the page and its AI read both use them: the dividend yield from the
    dividends listed on the page (R6O-008: Eni's 6.1% beside $1.87 of listed payments, TCS's AI read on another
    yield than the page's)."""
    out = with_dividend_yield(c, stored_dividends(region, c["symbol"]), datetime.now(IST).date().isoformat())
    return with_public_eps(region, out)


corp_sources = None      # the corporate actions job's sources (set by main), for a US company's dividends
public_facts = None      # (region, symbol) -> the stored public page's facts or None (set by main), never building one


def with_public_eps(region: str, c: dict) -> dict:
    """A US company's P/E and EPS on the same reported earnings as its public page (R7O-004: AAPL 39.02 in the app
    against 38.1 on /stocks): earnings per share over the last four reported quarters from the company's filings, the
    public page's figure, set against this page's price. Unchanged without a stored public page, or one with no P/E
    (a loss, or a market value that failed its checks), or for depositary shares (the app shows no EPS for them)."""
    if region != "US" or not callable(public_facts):
        return c
    try:
        f = public_facts("US", c["symbol"]) or {}
    except Exception:
        return c
    from .company import _set_metric
    from .net import num
    pe0, p0, live = num(f.get("pe")), num(f.get("price")), num((c.get("quote") or {}).get("price"))
    has_eps = any(i["label"] == "EPS TTM" for g in c.get("metrics") or [] for i in g["items"])
    if not pe0 or pe0 <= 0 or not p0 or not live or not has_eps or f.get("pe_basis") == "year":
        return c
    # the public page's own earnings per share (R7V-002: one P/E definition, the close over earnings per share for the
    # last four reported quarters), else what its P/E and price imply
    eps = num(f.get("eps")) or p0 / pe0
    note = "Earnings per share over the last four reported quarters, from the company's filings (as on its public page)"
    out = _set_metric(c, "EPS TTM", round(eps, 2), note)
    return _set_metric(out, "P/E", round(live / eps, 2), "The price over EPS TTM")


def stored_dividends(region: str, symbol: str) -> list[dict]:
    """A company's corporate actions as its page's Corporate actions card lists them (India: stored, no new read; the
    US: the card's own read, kept for a day), or none."""
    try:
        from .. import corp_actions
        if region == "IN":
            return corp_actions.actions_for("IN", symbol, None, fetch=False)
        src = corp_sources() if callable(corp_sources) else None
        got = corp_actions.company("US", symbol, src, fetch=src is not None)
        return (got.get("past") or []) + (got.get("ahead") or [])
    except Exception as e:
        print("dividends for the page:", region, symbol, str(e)[:120])
        return []


@router.get("/chart/{region}/{symbol}")
def chart(region: str, symbol: str, range: str = "1y", tf: str = "1d", before: str | None = None,
          profile=Depends(current_profile)):
    """A company's candles. `tf` is 5m, 15m, 1h or 1d; `before` (an ISO time) asks for the page of older
    candles when the chart is scrolled back, and `more` says whether still older ones exist."""
    if tf not in ("5m", "15m", "1h", "1d"):
        err(400, "bad_tf", "Pick 5m, 15m, 1h or 1d candles.")
    return ok(source_call(lambda: hub.chart(region_of(region), symbol_of(symbol), range[:5], tf, (before or "")[:40])))


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
        # the same figures as the page (its dividend yield) and the results calendar, so the read can tell a
        # filed quarter from one still to come (R6O-001)
        c = page_figures(r, source_call(lambda: hub.company(r, s)))
        try:
            from .. import results as results_calendar
            c = {**c, "results_calendar": results_calendar.lookup(r, c["symbol"])}
        except Exception:
            pass
        return A.company(c, _ai, pro, company_key_facts(r, c))
    try:
        read = ai_call(profile, "company", (r, s, pro, datetime.now(IST).date().isoformat()), 12 * 3600, refresh, build)
    except HTTPException as e:
        # the read is a nice-to-have on a page that has loaded: no AI answer today is an answer ("unavailable", and why),
        # not a failed request on every company page opened
        d = e.detail if isinstance(e.detail, dict) else {}
        if d.get("code") in ("ai_failed", "ai_busy", "research_ai_limit"):
            return ok({"unavailable": True, "code": d["code"], "message": d.get("message") or "No AI read right now."})
        raise
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
        return A.pulse(r, f, indices, news, _ai, closed=not market_open(r))
    try:
        return ok(ai_call(profile, "pulse", (r, f.lower(), hour), 3600, refresh, build))
    except HTTPException as e:
        # like a company's AI read: no read right now is an answer ("unavailable", and why), not a failed request on
        # every opening of the page; the levels and headlines don't depend on it
        d = e.detail if isinstance(e.detail, dict) else {}
        if d.get("code") in ("ai_failed", "ai_busy", "research_ai_limit"):
            return ok({"unavailable": True, "code": d["code"], "message": d.get("message") or "No AI read right now."})
        raise


@router.get("/sector")
def sector(q: str, region: str = "IN", refresh: bool = False, profile=Depends(current_profile)):
    r, theme = region_of(region), " ".join(q.split())[:80]
    if len(theme) < 2:
        err(400, "bad_theme", "Type a sector or theme, like \"India defence\" or \"AI data centers\".")
    # every ticker the AI wrote is checked against the market's list before the map is kept (R5O-008)
    got = ai_call(profile, "sector", (r, theme.lower()), 24 * 3600, refresh,
                  lambda: grounding.drop_unrelated(grounding.ground_sector(A.sector(theme, r, _ai), r, hub.search), industry_lookup(r)))
    # no unsourced market size or growth rate, even on a map kept from before (R7O-012)
    return ok({**got, "market_size": "", "cagr": None, "cagr_note": ""})


def industry_lookup(region: str):
    """{symbol: "sector industry"} from the screener's stored index, for the theme map's relevance check (R6O-017)."""
    try:
        from .. import screens
        rows = screens.load_index(region).get("rows") or []
    except Exception:
        return None
    got = {r["symbol"]: " ".join(x for x in (r.get("sector"), r.get("industry")) if x) for r in rows if r.get("symbol")}
    return got.get if got else None


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
    is_open = market_open(r)
    return ok({"a": {**ca, "market_open": is_open}, "b": {**cb, "market_open": is_open}, "ai": verdict})


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
