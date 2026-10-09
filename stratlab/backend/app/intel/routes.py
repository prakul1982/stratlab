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
    from .company import market_open as is_open
    return is_open(region, now)


def price_phase(region: str, c: dict, now: datetime | None = None) -> str | None:
    """"pre_open" when an Indian page's price is today's pre-open price, read between 09:00 and 09:15 IST, before the
    session's first trade: an indicative price, never the last close (R7T-004: "Last close ₹1,179.00 +1.00 on the day"
    at 09:13 IST beside an 8 Oct close of ₹1,178.00); None otherwise."""
    from .company import market_today, session_day
    from ..data.calendar import is_trading_day
    if region != "IN":
        return None
    local = (now or datetime.now(timezone.utc)).astimezone(IST)
    if not is_trading_day("IN", local.date()) or not ("09:00" <= local.strftime("%H:%M") < "09:15"):
        return None
    at = (c.get("quote") or {}).get("at")
    return "pre_open" if session_day(at, "IN") == market_today("IN", now) else None


@router.get("/company/{region}/{symbol}")
def company(region: str, symbol: str, profile=Depends(current_profile)):
    """One company's page. `as_of` is when its prices were read, for the page's "as of" line; `market_open` whether
    its market is trading now (else the price is the last close)."""
    r = region_of(region)
    c = page_figures(r, source_call(lambda: hub.company(r, symbol_of(symbol))))
    return ok({**c, "as_of": prices_as_of(c), "market_open": market_open(r), "phase": price_phase(r, c)})


def page_figures(region: str, c: dict) -> dict:
    """The company page's own figures, as the page and its AI read both use them: the dividend yield from the
    dividends listed on the page (R6O-008: Eni's 6.1% beside $1.87 of listed payments, TCS's AI read on another
    yield than the page's); a US company's market value, P/E and EPS on its public page's definitions (R7T-008); the
    52-week range checked against the price and taking in today's high and low (R7T-001, R7T-007)."""
    from .company import with_today_range
    out = with_dividend_yield(c, stored_dividends(region, c["symbol"]), datetime.now(IST).date().isoformat())
    return with_today_range(per_share_checked(with_public_eps(region, out)))


corp_sources = None      # the corporate actions job's sources (set by main), for a US company's dividends
public_facts = None      # (region, symbol) -> the stored public page's facts or None (set by main), never building one


def _metric(c: dict, label: str):
    return next((i for g in c.get("metrics") or [] for i in g["items"] if i["label"] == label), None)


def _drop_metric(c: dict, label: str) -> dict:
    groups = [{**g, "items": [i for i in g["items"] if i["label"] != label]} for g in c.get("metrics") or []]
    return {**c, "metrics": [g for g in groups if g["items"]]}


def _put_metric(c: dict, label: str, value, note: str | None, group: str = "Valuation", unit: str = "x") -> dict:
    """The page with a Key numbers item set (added to its group when the page had none)."""
    from .company import _set_metric
    if _metric(c, label):
        return _set_metric(c, label, value, note)
    groups = [dict(g) for g in c.get("metrics") or []]
    item = {"label": label, "value": value, "unit": unit, **({"note": note} if note else {})}
    for g in groups:
        if g["title"] == group:
            g["items"] = [item, *g["items"]]
            break
    else:
        groups.insert(0, {"title": group, "items": [item]})
    return {**c, "metrics": groups}


def with_public_eps(region: str, c: dict) -> dict:
    """A US company's market value, P/E and EPS on the same definitions and reported figures as its public page, set
    against this page's price (R7O-004, R7V-002): earnings per share over the last four reported quarters from the
    company's filings (or the latest year's, said so, for a company that reports yearly), and the market value of every
    class of its shares in the listed share's terms (R7T-001: BRK-B's P/E was 0.01 on Class A's $59,668 of EPS; R7T-008:
    Eni's $79.6B and P/E 13.42 against $87.5B and 29.9 on its public page). A public page that shows no P/E (a loss, a
    market value that failed its checks, earnings too old) gives none here either. Unchanged without a stored public page."""
    if region != "US" or not callable(public_facts):
        return c
    try:
        f = public_facts("US", c["symbol"]) or {}
    except Exception:
        return c
    from .net import num
    from .. import stock_pages
    p0, live = num(f.get("price")), num((c.get("quote") or {}).get("price"))
    if not f or not p0 or p0 <= 0 or not live:
        return c
    k = live / p0
    out = c
    cap0 = num(f.get("market_cap"))
    if cap0 is not None:
        shown = stock_pages.shown_cap(f)
        out = {**out, "market_cap": shown * 1e6 * k if shown else None}
    pe0 = stock_pages.shown_pe(f)
    if num(f.get("pe")) is None and "pe" not in f:
        return out
    if not pe0:
        # the public page's P/E is n/a: so is the app's, and an EPS from another class of shares goes with it
        out = _drop_metric(out, "P/E")
        eps = _metric(out, "EPS TTM")
        if eps and num(eps.get("value")) and num(eps["value"]) > live:
            out = _drop_metric(out, "EPS TTM")
        return out
    eps = num(f.get("eps")) or p0 / pe0
    year = f.get("pe_basis") == "year" and f.get("pe_end")
    basis = (f"Earnings per share for the {stock_pages.pe_label(f)[5:-1]}, from the company's filings (it reports yearly), as on its public page"
             if year else "Earnings per share over the last four reported quarters, from the company's filings (as on its public page)")
    if _metric(out, "EPS TTM"):
        out = _put_metric(out, "EPS TTM", round(eps, 2), basis, "Per share and returns", "money")
    return _put_metric(out, "P/E", round(live / eps, 2), ("The price over earnings per share for the " + stock_pages.pe_label(f)[5:-1]
                                                          + " (the company reports yearly)") if year else "The price over EPS TTM")


def per_share_checked(c: dict) -> dict:
    """Per-share figures that can't be this share's are left out (R7T-001: BRK-B's page showed Class A's EPS of $59,668
    and a P/E of 0.01 beside a $511 Class B price): an EPS above the price, a P/E under 1, and quarterly earnings per share
    above the price, with the next quarter's estimate."""
    from .net import num
    px = num((c.get("quote") or {}).get("price"))
    if not px:
        return c
    out = c
    eps, pe = _metric(c, "EPS TTM"), _metric(c, "P/E")
    if eps and num(eps.get("value")) is not None and abs(num(eps["value"])) > px:
        out = _drop_metric(_drop_metric(out, "EPS TTM"), "P/E")
    elif pe and num(pe.get("value")) is not None and 0 < num(pe["value"]) < 1:
        out = _drop_metric(out, "P/E")
    rows = out.get("earnings") or []
    if any(abs(num(e.get("actual")) or 0) > px or abs(num(e.get("estimate")) or 0) > px for e in rows):
        out = {**out, "earnings": []}
        if out.get("next_earnings"):
            out = {**out, "next_earnings": {**out["next_earnings"], "eps_estimate": None}}
    return out


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
    """The AI's read of the market's mood, from the index levels and headlines. It is written for the levels as they are:
    kept only while they stay in the same session and about the same moves (a read from before the open is written again
    after it, R7T-003), and never written while an index it would cite is still a previous session's level."""
    r, f = region_of(region), focus.strip()[:60]
    indices = source_call(lambda: hub.indices(r))
    stale = [i["name"] for i in indices if i.get("stale")]
    if stale:
        return ok({"unavailable": True, "code": "stale", "message": stale_words(stale)})
    hour = datetime.now(IST).strftime("%Y-%m-%d %H")

    def build():
        try:
            news = hub.headlines(r, f)
        except SourceError:
            news = []
        return A.pulse(r, f, indices, news, _ai, closed=not market_open(r))
    try:
        return ok(ai_call(profile, "pulse", (r, f.lower(), hour, mood_key(indices, market_open(r))), 3600, refresh, build))
    except HTTPException as e:
        # like a company's AI read: no read right now is an answer ("unavailable", and why), not a failed request on
        # every opening of the page; the levels and headlines don't depend on it
        d = e.detail if isinstance(e.detail, dict) else {}
        if d.get("code") in ("ai_failed", "ai_busy", "research_ai_limit"):
            return ok({"unavailable": True, "code": d["code"], "message": d.get("message") or "No AI read right now."})
        raise


def stale_words(names: list[str]) -> str:
    """Why there is no mood read: an index is still at a previous session's level while the market trades."""
    verb = "hasn't" if len(names) == 1 else "haven't"
    return (f"{', '.join(names)} {verb} updated for today's session yet, so no mood is written on a previous session's "
            "numbers. Ask again in a minute.")


def mood_key(indices: list[dict], is_open: bool) -> tuple:
    """What a mood read is written for: whether the market is open, and each index's session and its move to the nearest
    half percent. A read is kept while these stay the same and written again when they change (the open, a turn)."""
    import math
    return (is_open, tuple((i.get("name"), i.get("day"), math.floor((i.get("change_pct") or 0.0) * 2) / 2) for i in indices))


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
    # each side's figures as its own page shows them (market value, P/E, range)
    ca = page_figures(r, source_call(lambda: hub.company(r, sa)))
    cb = page_figures(r, source_call(lambda: hub.company(r, sb)))
    try:
        verdict = ai_call(profile, "compare", (r, sa, sb, datetime.now(IST).date().isoformat()), 12 * 3600, refresh,
                          lambda: A.compare(ca, cb, _ai))
    except HTTPException as e:
        verdict = {"error": (e.detail or {}).get("message") if isinstance(e.detail, dict) else str(e.detail)}
    is_open = market_open(r)
    return ok({"a": {**ca, "market_open": is_open, "phase": price_phase(r, ca)}, "b": {**cb, "market_open": is_open, "phase": price_phase(r, cb)},
               "ai": verdict})


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
