"""/research API: company profiles, charts, quotes, market pulse, sector maps, comparisons,
AI reads and the watchlist. Every third-party call happens here on the server."""
import contextlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db, usage_slots
from ..branding import public_research
from ..responses import err, safe
from ..ai_providers import AIBusy, AIError, ask_again
from ..auth import current_profile
from ..kite_service import IST
from ..plans import has_indicators
from . import ai as A
from . import grounding, key_facts
from .company import INDICES, Research, with_dividend_yield
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


def symbol_of(symbol: str, region: str | None = None) -> str:
    """A ticker checked, and as the app keeps it: with `region` "US", a share class with a dash (BRK.B -> BRK-B), so every
    source is asked for the one listing the canonical page shows (R13-001)."""
    s = symbol.strip().upper()
    if (region or "").upper() == "IN":
        from ..us_ticker import canon_in
        s = canon_in(s)                 # NSE:TCS, TCS.NS and TCS-EQ are TCS (RC5-010); the exchange's prefix has a colon the check below refuses
    # a letter or digit first (or ^ for an index): "..", "-x" and the like never reach a data source's address
    if not s or len(s) > 20 or not (s[0].isalnum() or s[0] == "^") or not all(ch.isalnum() or ch in "&-._^/" for ch in s):
        err(400, "bad_symbol", "That doesn't look like a ticker.")
    from ..us_ticker import canon
    s = canon(region, s) if region else s
    if "/" in s:
        err(400, "bad_symbol", "That doesn't look like a ticker.")
    return s


def source_call(fn):
    try:
        return fn()
    except NotFound as e:
        err(404, "not_found", str(e))
    except SourceError as e:
        err(503 if e.busy else 502, "source_error", str(e))


def ai_cap(profile) -> int | None:
    """A person's daily cap on fresh AI reads (the Plans page and Account say it): none for the site's admins and for
    a Pro plan they pay for; RESEARCH_AI_PER_DAY a day (India's day) for Basic and Free, Free's an abuse guard. The plan
    paid for, never the launch offer's Pro or a "View as" plan (R8O-002: a hidden 60 a day stopped the owner's market
    mood and company reads while Plans said Pro was unlimited)."""
    from .. import admin
    from ..plans import ai_reads_per_day, effective_plan
    if admin.is_admin(profile):
        return None
    return ai_reads_per_day(profile.get("_paid_plan") or effective_plan(profile))


def ai_auto_counts(profile) -> bool:
    """Whether a company read written as a company page opens counts against the person's cap: only for an account
    that pays for no plan (the abuse guard); a read already written for that company today never counts for anyone."""
    from ..plans import effective_plan
    return ai_cap(profile) is not None and (profile.get("_paid_plan") or effective_plan(profile)) == "free"


def ai_day_start() -> str:
    """The start of today in India: the cap is "a day" as the message says, and comes back at midnight IST."""
    return datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def ai_reads_today(profile) -> int:
    return db.count_usage(profile["id"], "research_ai", ai_day_start())


LIMIT_CODE = "research_ai_limit"


SEARCH_AI_PER_DAY = 40         # the search box's AI calls (ideas, ask) a day, every plan; apart from the company reads' cap
SEARCH_KIND = "search_ai"


def read_slot(profile, limit: int | None, kind: str = "research_ai"):
    """Holds one of the person's fresh AI reads while it's written, so parallel requests can't all pass the cap before
    any is counted. Record the usage inside the block; a read that fails leaves the cap untouched. No cap, no hold."""
    if limit is None:
        return contextlib.nullcontext()
    def check(held):
        if db.count_usage(profile["id"], kind, ai_day_start()) + held >= limit:
            if kind == SEARCH_KIND:
                err(429, "search_ai_limit", f"You've used today's {limit} AI answers in the search box. "
                    "The count starts again at midnight India time.")
            err(429, LIMIT_CODE, limit_words(limit))
    return usage_slots.hold(profile["id"], kind, check)


def limit_words(limit: int) -> str:
    return (f"You've used today's {limit} fresh AI reads on your plan. Reads already written for a company or the market "
            "still open, and the count starts again at midnight India time.")


_building: dict[str, threading.Lock] = {}
_building_lock = threading.Lock()


def _drop_finished_builds() -> None:
    """Forget the builds that are over; one still running keeps its lock, so a second request waits for it instead of
    starting its own. Called with `_building_lock` held."""
    for k in [k for k, one in _building.items() if not one.locked()]:
        del _building[k]


def ai_call(profile, kind: str, key: tuple, ttl: float, refresh: bool, build, counted: bool = True, min_age: float = 0,
            kind_used: str = "research_ai", cap: int | None = None):
    """Serve an AI read from the shared cache (every user's, one read per company or market per key), or build it.
    `counted`: a fresh build counts against the person's daily cap and is refused past it; False for reads shared by
    everyone (the market mood) and a company read written as its page opens on a paid plan, which neither count nor are
    refused. `min_age`: a refresh of a shared read younger than this is the read already written (one person's "Ask
    again" can't make everyone's read be written over and over). `kind_used`, `cap`: count under another usage kind with
    its own daily cap (the search box's), instead of the company reads' ones."""
    if not refresh and A.peek(kind, key):
        return A.cached(kind, key, ttl, False, build)[0]
    if refresh and min_age and (hit := A.get(kind, key)) and time.time() - float(hit.get("generated_at") or 0) < min_age:
        return hit
    k = repr((kind, key))
    with _building_lock:
        one = _building.setdefault(k, threading.Lock())
    with read_slot(profile, (cap if kind_used != "research_ai" else ai_cap(profile)) if counted else None, kind_used):
        try:
            with one:                     # two people opening the same company at once: one read, written once
                if not refresh and A.peek(kind, key):
                    return A.cached(kind, key, ttl, False, build)[0]
                with ask_again() if refresh else contextlib.nullcontext():
                    out, fresh = A.cached(kind, key, ttl, refresh, build)
        except AIBusy as e:
            err(503, "ai_busy", str(e))
        except AIError as e:          # there's no idea to rephrase on a research page: the reader can only try again
            err(422, "ai_failed", str(e).replace("Try rephrasing the idea.", "Press Refresh to try again."))
        finally:
            with _building_lock:
                if len(_building) > 2000:
                    _drop_finished_builds()
        if fresh and counted:
            db.add_usage(profile["id"], kind_used)
    return out


# ---------- data ----------
@router.get("/search")
def search(q: str = "", region: str = "IN", profile=Depends(current_profile)):
    r = region_of(region)
    from ..us_ticker import CLASS, canon
    q = q[:40]
    if r == "US" and CLASS.match(q.strip().upper()):       # "BRK.B" finds BRK-B (R13-001)
        q = canon(r, q)
    return ok(source_call(lambda: hub.search(q, r)))


def prices_as_of(c: dict, region: str | None = None, now: datetime | None = None) -> str | None:
    """When a company page's price is from: the time of the quote's last trade (the exchange's own stamp), never the
    moment of asking. A quote without one has no "as of": the page says its time is unknown (review 5c: a price from
    the fundamentals page, hours or days old, was dated "now").

    With the `region`, once the session has closed a last trade in its final half hour (or the close's own stamp a few
    minutes after) is the close, so every page of a closed session says the same time (DD-023: "15:28 IST" on most
    stocks, "15:30" on the day's IPOs)."""
    now = now or datetime.now(timezone.utc)
    at = (c.get("quote") or {}).get("at")
    try:
        t = datetime.fromisoformat(at.replace("Z", "+00:00")) if isinstance(at, str) else None
    except ValueError:
        t = None
    if t is None:
        return None
    t = t if t.tzinfo else t.replace(tzinfo=IST)
    if region:
        from zoneinfo import ZoneInfo
        from ..data.markets import BY_ID
        from ..stock_pages import close_of
        tz = ZoneInfo((BY_ID.get(region) or {}).get("tz") or "UTC")
        day = t.astimezone(tz).date()
        hm = close_of(region, day)
        if hm:
            close = datetime.combine(day, datetime.strptime(hm, "%H:%M").time(), tz)
            if close <= now and not market_open(region, now) and close - timedelta(minutes=30) <= t <= close + timedelta(minutes=5):
                t = close
    return min(t, now).isoformat(timespec="minutes")


def quote_day(region: str, c: dict) -> str | None:
    """The trading day (in the market's zone) of the page's price, from its last trade's time; None when the quote has no
    time. With it the page says "today" only of today's price, never of an earlier session's while the market trades."""
    from .company import session_day
    return session_day((c.get("quote") or {}).get("at"), region)


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
        # a US price read between the 16:00 close and its settle point is the day's last prints, not yet its close: the
        # header says "Latest, closing prints still settling" until then, never "Last close" (R13-005)
        from .. import stock_pages
        day = stock_pages.settling(region, now)
        at = (c.get("quote") or {}).get("at")
        return "settling" if day and (not at or session_day(at, region) == day) else None
    local = (now or datetime.now(timezone.utc)).astimezone(IST)
    if not is_trading_day("IN", local.date()) or not ("09:00" <= local.strftime("%H:%M") < "09:15"):
        return None
    at = (c.get("quote") or {}).get("at")
    return "pre_open" if session_day(at, "IN") == market_today("IN", now) else None


@router.get("/company/{region}/{symbol}")
def company(region: str, symbol: str, lean: bool = False, profile=Depends(current_profile)):
    """One company's page. `as_of` is when its prices were read, for the page's "as of" line; `market_open` whether
    its market is trading now (else the price is the last close). `lean`: without the news, the encyclopedia entry and
    the peers (marked `lazy`; /more brings them), so the price, header and tables don't wait on slow sources (R10O-009)."""
    r = region_of(region)
    s = symbol_of(symbol, r)
    c = page_figures(r, source_call(lambda: hub.company(r, s, lean=True) if lean else hub.company(r, s)))
    return ok({**c, "as_of": prices_as_of(c, r), "market_open": market_open(r), "phase": price_phase(r, c), "quote_day": quote_day(r, c)})


@router.get("/company/{region}/{symbol}/more")
def company_more(region: str, symbol: str, profile=Depends(current_profile)):
    """What a lean company page left out: the company's news, its encyclopedia entry and its peers."""
    r = region_of(region)
    s = symbol_of(symbol, r)
    return ok(source_call(lambda: hub.company_more(r, s)))


def page_figures(region: str, c: dict) -> dict:
    """The company page's own figures, as the page and its AI read both use them: the dividend yield from the
    dividends listed on the page (R6O-008: Eni's 6.1% beside $1.87 of listed payments, TCS's AI read on another
    yield than the page's); a US company's market value, P/E and EPS on its public page's definitions (R7T-008); the
    52-week range checked against the price and taking in today's high and low (R7T-001, R7T-007)."""
    from .company import with_today_range
    # the public EPS first: the payout ratio is the dividends over the EPS TTM the page shows, not the source's (R29B-013: $8.72 vs $8.71)
    out = with_dividend_yield(with_filed_results(region, with_public_eps(region, c)), stored_dividends(region, c["symbol"]), datetime.now(IST).date().isoformat(),
                              listed=_list_read(region, c["symbol"]))
    return with_today_range(per_share_checked(out))


corp_sources = None      # the corporate actions job's sources (set by main), for a US company's dividends
public_facts = None      # (region, symbol) -> the stored public page's facts or None (set by main), never building one
filed_numbers = None     # symbol -> the company's numbers read from its filings (set by main; kept six hours), for a page stored before they were kept


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


QUARTER_OF = {3: 1, 6: 2, 9: 3, 0: 4}       # months after the fiscal year's end -> the quarter it closes


def fiscal_quarter(end: str, fye_month: int) -> str | None:
    """"Q2 FY27" for a quarter ending on `end` (ISO) in a fiscal year ending in month `fye_month`, named by the calendar year
    it ends in (NVIDIA's quarter to 26 Jul 2026 is Q2 FY27; Apple's to 27 Jun 2026, Q3 FY26). A 52/53-week quarter
    ending a few days into a month counts as the month before."""
    from datetime import date, timedelta
    try:
        d = date.fromisoformat(end[:10]) - timedelta(days=15)
    except ValueError:
        return None
    for m in (fye_month, (fye_month - 2) % 12 + 1):            # a fiscal year "ending" a few days into the next month
        k = (d.month - m) % 12
        if k % 3 == 0:
            fy = d.year + (1 if d.month > m else 0)
            return f"Q{QUARTER_OF[k]} FY{fy % 100:02d}"
    return None


def filed_results(rows: list[dict], eps_q: dict[str, float], fye_month: int | None) -> tuple[list[dict], str | None]:
    """The results-versus-estimates rows dated and checked by the company's filings (DD-030, DD-031): each row is matched to
    the filed quarter it is of (the estimates source dates a quarter by the calendar quarter it falls in: NVIDIA's quarter
    to 26 Jul 2026 came as "Sep 2026"), dated by that quarter's end, named by its fiscal quarter, with the filings' GAAP
    diluted EPS beside it. When most rows' EPS is the filed GAAP figure, the source counts GAAP EPS for this company, and a
    row that disagrees with the filing takes the filed figure (AAPL's quarter to 27 Jun 2026: 1.91 against a filed 2.02,
    shown as a miss); otherwise the source's figures are adjusted (non-GAAP, as the estimates are), kept, and said so.
    Returns (rows, "gaap" | "adjusted" | None)."""
    from datetime import date
    ends = sorted(e for e, v in (eps_q or {}).items() if v is not None)
    used, out = set(), []
    for r in rows:
        p = str(r.get("period") or "")[:10]
        try:
            pd_ = date.fromisoformat(p)
        except ValueError:
            out.append(dict(r))
            continue
        cand = [e for e in ends if -7 <= (pd_ - date.fromisoformat(e)).days <= 100 and e not in used]
        e = cand[-1] if cand else None
        if e is None:
            out.append(dict(r))
            continue
        used.add(e)
        out.append({**r, "period": e, "gaap": eps_q[e], **({"fiscal": fq} if fye_month and (fq := fiscal_quarter(e, fye_month)) else {})})
    matched = [r for r in out if r.get("gaap") is not None]
    if not matched:
        return out, None
    same = lambda r: abs(r["actual"] - r["gaap"]) <= max(0.02, 0.01 * abs(r["gaap"]))       # noqa: E731
    if sum(1 for r in matched if same(r)) * 2 > len(matched):
        fixed = []
        for r in out:
            if r.get("gaap") is not None and not same(r):
                a, est = r["gaap"], r.get("estimate")
                r = {**r, "actual": a, "surprise_pct": (a - est) / abs(est) * 100 if est else None, "from_filing": True}
            fixed.append(r)
        return fixed, "gaap"
    return out, "adjusted"


def with_filed_results(region: str, c: dict) -> dict:
    """A US company page with its results-versus-estimates rows checked and dated by its filings (filed_results), and its
    interest coverage said to be not meaningful when its latest annual report gives no interest expense (DD-035: Apple's
    "Interest coverage 623" on an interest cost it stopped disclosing after FY23). Unchanged without a stored public page."""
    if region != "US":
        return c
    try:
        f = (public_facts("US", c["symbol"]) or {}) if callable(public_facts) else {}
    except Exception:
        f = {}
    # a public page stored before the filings' quarterly EPS was kept on it has none (RC1: AAPL's quarter to 27 Jun 2026
    # stayed 1.91 against a filed 2.02 until that page was rebuilt): the company's filings, read once and kept six
    # hours, give the same figures
    from .. import stock_pages
    if (f.get("v") or 1) < stock_pages.FACTS_VERSION and callable(filed_numbers) and (c.get("earnings") or _metric(c, "Interest coverage")):
        try:
            n = filed_numbers(c["symbol"]) or {}
        except Exception:
            n = {}
        f = {**f, **({"eps_q": n["eps_q"]} if n.get("eps_q") and not f.get("eps_q") else {}),
             **({"no_interest": True} if n.get("interest_shown") is False else {}),
             **({"fye": int(str(n["fiscal_year_end"])[:2])} if str(n.get("fiscal_year_end") or "")[:2].isdigit() else {})}
    out = c
    if f.get("no_interest") and _metric(out, "Interest coverage"):
        groups = [{**g, "items": [{**i, "value": None, "text": "n/m", "note": "No interest expense in the latest annual report"}
                                  if i["label"] == "Interest coverage" else i for i in g["items"]]} for g in out.get("metrics") or []]
        out = {**out, "metrics": groups}
    if f.get("eps_q") and out.get("earnings"):
        import re as _re
        last = ((f.get("years") or [{}])[-1] or {}).get("year") or ""
        m = _re.match(r"([A-Za-z]{3})", str(last))
        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        fye = months.index(m.group(1)) + 1 if m and m.group(1) in months else f.get("fye")
        rows, basis = filed_results(out["earnings"], f["eps_q"], fye)
        out = {**out, "earnings": rows, **({"earnings_basis": basis} if basis else {})}
    return out


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


def _list_read(region: str, symbol: str) -> bool:
    """Whether an Indian company's corporate actions list was ever read and stored: then no dividend in it for the year is a real
    0%, not a missing list (RC7-006)."""
    if region != "IN":
        return False
    try:
        from .. import corp_actions
        return bool(corp_actions.hist_load("IN", symbol)["at"])
    except Exception:
        return False


def stored_dividends(region: str, symbol: str) -> list[dict]:
    """A company's corporate actions as its page's Corporate actions card lists them (India: stored, no new read; the
    US: the card's own read, kept for a day), or none."""
    try:
        from .. import corp_actions
        if region == "IN":
            return corp_actions.actions_for("IN", symbol, None, fetch=False)
        src = corp_sources() if callable(corp_sources) else None
        if src is not None and corp_actions.hist_load("US", symbol)["at"]:
            # a stored history, however old, as it is (the corporate actions job keeps them fresh): one older than a day
            # is read again in the background, never on the page's request (R11E: 1 to 3 s on a day's first visit)
            _refresh_history("US", symbol, src)
            got = corp_actions.company("US", symbol, src, fetch=True, fetch_history=False)
        else:                            # never stored: read now, as before
            got = corp_actions.company("US", symbol, src, fetch=src is not None)
        return (got.get("past") or []) + (got.get("ahead") or [])
    except Exception as e:
        print("dividends for the page:", region, symbol, str(e)[:120])
        return []


_hist_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="corp-history")
_hist_reading: set = set()           # (region, symbol) with a background read under way
_hist_lock = threading.Lock()


def _refresh_history(region: str, symbol: str, sources: dict) -> None:
    """Read one company's corporate-actions history again in the background when the stored one is older than a day,
    one read per company at a time."""
    from .. import corp_actions
    k = (region, symbol.upper())
    with _hist_lock:
        if k in _hist_reading or not corp_actions._stale(corp_actions.hist_load(region, symbol)["at"]):
            return
        _hist_reading.add(k)

    def run():
        try:
            corp_actions.history(region, symbol, sources, fetch=True, keep_empty=False)
        except Exception as e:
            print("corporate actions history (background):", region, symbol, str(e)[:120])
        finally:
            with _hist_lock:
                _hist_reading.discard(k)
    _hist_pool.submit(run)


@router.get("/chart/{region}/{symbol}")
def chart(region: str, symbol: str, range: str = "1y", tf: str = "1d", before: str | None = None,
          profile=Depends(current_profile)):
    """A company's candles. `tf` is 5m, 15m, 1h or 1d; `before` (an ISO time) asks for the page of older
    candles when the chart is scrolled back, and `more` says whether still older ones exist."""
    if tf not in ("5m", "15m", "1h", "1d"):
        err(400, "bad_tf", "Pick 5m, 15m, 1h or 1d candles.")
    r = region_of(region)
    s = symbol_of(symbol, r)
    return ok(source_call(lambda: hub.chart(r, s, range[:5], tf, (before or "")[:40])))


@router.get("/quotes")
def quotes(region: str = "IN", symbols: str = "", profile=Depends(current_profile)):
    r = region_of(region)
    asked = [s.strip().upper() for s in symbols.split(",") if s.strip()][:24]
    syms = [symbol_of(s, r) for s in asked]
    got = source_call(lambda: hub.quotes(r, syms))
    # answered under the ticker asked for too, so a page holding "BRK.B" finds its quote (R13-001)
    if isinstance(got, dict):
        for a, s in zip(asked, syms):
            if a != s and s in got:
                got.setdefault(a, got[s])
    return ok(got)


@router.get("/pulse")
def pulse(region: str = "IN", focus: str = "", profile=Depends(current_profile)):
    """The index levels and headlines from memory, read again behind the page (R24-001: the request read them itself and
    took 13 to 40 s at India's open). `pending`: the first read since the server started isn't back yet; ask again."""
    r = region_of(region)
    if not focus.strip() and hasattr(hub, "headlines_now"):
        hub.headlines_now(r, wait=0)             # the headlines' read starts now, beside the levels', not after them
    indices, at = source_call(lambda: _levels_now(r, 6.0))
    news = _news_now(r, 1.0) if not focus.strip() else _focused_news(r, focus[:60])
    if indices is None:
        return ok({"indices": [], "headlines": news, "missing": [], "pending": True})
    got = {i["name"] for i in indices}
    return ok({"indices": indices, "headlines": news, "missing": [n for n, _ in INDICES.get(r, []) if n not in got],
               "read_at": datetime.fromtimestamp(at, timezone.utc).isoformat(timespec="seconds") if at else None})


def _levels_now(r: str, wait: float):
    """The hub's levels from memory (Research.indices_now); a hub without that reads them now."""
    now = getattr(hub, "indices_now", None)
    return now(r, wait=wait) if now else (hub.indices(r), None)


def _news_now(r: str, wait: float) -> list[dict]:
    now = getattr(hub, "headlines_now", None)
    return now(r, wait=wait) if now else _focused_news(r, "")


def _focused_news(r: str, focus: str) -> list[dict]:
    try:
        return hub.headlines(r, focus)
    except SourceError:
        return []


# ---------- AI reads ----------
_writing: dict[tuple, dict] = {}         # company reads being written behind the page: {key: {"at", "done", "error"}}
_writing_lock = threading.Lock()
_writers = None
WRITE_FOR = 120                          # a read still being written after this long is given up on (the page says so)


def _writer_pool():
    global _writers
    if _writers is None:
        from concurrent.futures import ThreadPoolExecutor
        _writers = ThreadPoolExecutor(max_workers=4, thread_name_prefix="company-ai")
    return _writers


def behind_the_page(key: tuple, run) -> dict | None:
    """A company read written behind the page (R8O-007: the page waited 8 to 30 s on its read): started once per company
    whoever asks, and polled. None while it is being written; {"error": detail} once, when it failed."""
    now = time.time()
    with _writing_lock:
        job = _writing.get(key)
        if job and job.get("done"):
            _writing.pop(key, None)
            return {"error": job.get("error")} if job.get("error") else None
        if job and now - job["at"] < WRITE_FOR:
            return None
        job = _writing[key] = {"at": now, "done": False, "error": None}
        if len(_writing) > 500:
            for k in [k for k, v in _writing.items() if now - v["at"] > WRITE_FOR]:
                _writing.pop(k, None)

    def work():
        try:
            run()
        except HTTPException as e:
            job["error"] = e.detail if isinstance(e.detail, dict) else {"code": "ai_failed", "message": str(e.detail)}
        except Exception as e:                       # noqa: BLE001 - said to the page, never raised in a worker
            job["error"] = {"code": "ai_failed", "message": f"The AI read couldn't be written ({str(e)[:80]}). Press Refresh to try again."}
        finally:
            job["done"] = True
    _writer_pool().submit(work)
    return None


@router.get("/company/{region}/{symbol}/ai")
def company_ai(region: str, symbol: str, refresh: bool = False, background: bool = False, profile=Depends(current_profile)):
    """A company's AI read. `background`: the page asks without waiting; a read not written yet is written behind the
    page and the answer is {"pending": true} until it is there (the page asks again every few seconds)."""
    r = region_of(region)
    s = symbol_of(symbol, r)
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
    key = (r, s, pro, datetime.now(IST).date().isoformat())
    counted = refresh or ai_auto_counts(profile)
    if background and not refresh and not A.peek("company", key):
        # within the cap the read is written behind the page; past it, the page hears so now, not after a wait
        limit = ai_cap(profile) if counted else None
        if limit is None or ai_reads_today(profile) < limit:
            failed = behind_the_page(("company",) + key, lambda: ai_call(profile, "company", key, 12 * 3600, False, build, counted=counted))
            if failed is None and not A.peek("company", key):
                return ok({"pending": True})
            if failed:
                d = failed["error"]
                return ok({"unavailable": True, "code": d.get("code") or "ai_failed", "message": d.get("message") or "No AI read right now."})
    try:
        # one read per company a day, shared by everyone: opening a page that already has one costs nobody anything, and
        # on a paid plan a read written as the page opens doesn't count either; "Refresh" (asked for) does (R8O-002)
        read = ai_call(profile, "company", key, 12 * 3600, refresh, build, counted=counted)
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
    r, f = region_of(region), focus.strip()
    if f:                          # the page sends none; free text would make a new uncached read for every wording
        err(400, "bad_focus", "The market read has no focus option.")
    indices, _ = source_call(lambda: _levels_now(r, 12.0))          # the pulse page's own levels, from memory (R24-001)
    if indices is None:
        return ok({"unavailable": True, "code": "ai_busy", "message": "The index levels are still being read. Ask again in a moment."})
    stale = [i["name"] for i in indices if i.get("stale")]
    if stale:
        return ok({"unavailable": True, "code": "stale", "message": stale_words(stale)})
    is_open = market_open(r)
    # while the market trades, a read an hour; once it has closed, one read per close, whoever asks and whenever (R13-011:
    # two views 12 minutes apart after the US close got two different texts, the hour having turned in India)
    hour = datetime.now(IST).strftime("%Y-%m-%d %H") if is_open else "close"
    # between the US close and its settle point the levels are the day's last prints, not yet its close: that read is kept
    # apart and only until they settle, so the evening's read is written on the final closes, never "closed at" a
    # provisional level (R89-007: "The S&P 500 closed at 7,623.68" under "closing prints still settling")
    from .. import stock_pages
    settling = None if is_open else stock_pages.settling(r)
    settle_ttl = None
    if settling:
        hour = "settling"
        until = stock_pages.next_settle(r)
        settle_ttl = max(60.0, (until - datetime.now(timezone.utc)).total_seconds()) if until else 900.0
    cash = flows_today() if r == "IN" else None            # the day's FII and DII figures, as Positioning has them (R10O-004)
    cash_day = cash.get("as_of") if cash and cash.get("status") == "ok" else None

    def build():
        news = _news_now(r, 8.0)
        try:
            sectors = hub.sector_moves(r)
        except Exception:
            sectors = None
        early = before_close_at(r, indices)
        read = A.pulse(r, f, indices, news, _ai, closed=not market_open(r) and not early and not settling, sectors=sectors, cash=cash,
                       before_close=early, settling=bool(settling) and not early)
        # the time of the levels the text quotes, so a read kept while the tiles move on says what its numbers are of (R16B-002)
        return {**read, "levels_at": max((i["at"] for i in indices if i.get("at")), default=None)}
    try:
        # the market's mood is one read per market, shared by everyone: it never counts against anyone's daily cap and is
        # never refused for it (R8O-002: India's mood blocked by the cap in market hours); "Ask again" on a read under five
        # minutes old gives that read
        # "mood": reads kept from before the mood line and main story were added are written again (DD-001)
        return ok(ai_call(profile, "pulse", (r, f.lower(), hour, mood_key(indices, is_open), cash_day, "mood"),
                          3600 if is_open else settle_ttl or CLOSED_MOOD_TTL, refresh, build, counted=False,
                          min_age=300 if is_open else settle_ttl or CLOSED_MOOD_TTL))
    except HTTPException as e:
        # like a company's AI read: no read right now is an answer ("unavailable", and why), not a failed request on
        # every opening of the page; the levels and headlines don't depend on it
        d = e.detail if isinstance(e.detail, dict) else {}
        if d.get("code") in ("ai_failed", "ai_busy", "research_ai_limit"):
            return ok({"unavailable": True, "code": d["code"], "message": d.get("message") or "No AI read right now."})
        raise


def before_close_at(region: str, indices: list[dict]) -> str | None:
    """The time ("15:32 ET") of the earliest level when the market has closed but a level is still from before the close,
    else None: the read then says "at", never "closed at" (R30-002)."""
    early = sorted(i["at"] for i in indices if i.get("pre_close") and i.get("at"))
    if not early:
        return None
    from zoneinfo import ZoneInfo
    from ..data.markets import BY_ID
    t = datetime.fromisoformat(str(early[0]).replace("Z", "+00:00")).astimezone(ZoneInfo((BY_ID.get(region) or {}).get("tz") or "UTC"))
    return t.strftime("%H:%M") + {"US": " ET", "IN": " IST"}.get(region, "")


CLOSED_MOOD_TTL = 20 * 3600      # a closed session's mood read: kept until the next session, never written again on "Ask again"


def flows_today() -> dict | None:
    """Positioning's FII and DII cash-market figures for the newest day, or None when they can't be read."""
    try:
        from .. import positioning
        return positioning.cash_today()
    except Exception:
        return None


def stale_words(names: list[str]) -> str:
    """Why there is no mood read: an index is still at a previous session's level while the market trades."""
    verb = "hasn't" if len(names) == 1 else "haven't"
    return (f"{', '.join(names)} {verb} updated for today's session yet, so no mood is written on a previous session's "
            "numbers. Ask again in a minute.")


def mood_key(indices: list[dict], is_open: bool) -> tuple:
    """What a mood read is written for: whether the market is open, whether the close is still settling, and each index's
    session and its move to the nearest half percent. A read is kept while these stay the same and written again when they
    change (the open, a turn, the settled close: R16B-002 kept 7,719.51 beside tiles of 7,718.94)."""
    import math
    return (is_open, any(i.get("settling") for i in indices), any(i.get("pre_close") for i in indices), tuple((i.get("name"), i.get("day"), math.floor((i.get("change_pct") or 0.0) * 2) / 2) for i in indices))


@router.get("/sector")
def sector(q: str, region: str = "IN", refresh: bool = False, profile=Depends(current_profile)):
    r, theme = region_of(region), " ".join(q.split())[:80]
    if len(theme) < 2:
        err(400, "bad_theme", "Type a sector or theme, like \"India defence\" or \"AI data centers\".")
    rows = index_rows(r)
    # DE-015: letters that spell nothing ("asdkjh qwe zzz") are asked about before an AI read is spent on them
    if not grounding.looks_like_theme(theme, grounding.vocabulary(rows)):
        err(400, "bad_theme", f"\"{theme}\" doesn't read as a sector or theme. Try words like \"India defence\" or \"AI data centers\".")
    # every ticker the AI wrote is checked against the market's list before the map is kept (R5O-008)
    got = ai_call(profile, "sector", (r, theme.lower()), 24 * 3600, refresh,
                  lambda: grounding.drop_unrelated(grounding.ground_sector(A.sector(theme, r, _ai), r, hub.search), industry_lookup(r)))
    # no unsourced market size or growth rate, even on a map kept from before (R7O-012); no figure in the text and no
    # company that isn't listed, and the exchange's own list of the theme's industries beside the map (DE-013)
    got = grounding.listed_only(A.theme_served(got))
    return ok({**got, "market_size": "", "cagr": None, "cagr_note": "", "exchange": grounding.exchange_list(got, rows) or None})


def index_rows(region: str) -> list[dict]:
    """The screener's stored index of listed companies ({symbol, name, sector, industry}), or none when it can't be read."""
    try:
        from .. import screens
        return screens.load_index(region).get("rows") or []
    except Exception:
        return []


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
    r = region_of(region)
    sa, sb = symbol_of(a, r), symbol_of(b, r)
    # the same company twice is a slip, said kindly: by symbol, or once both pages are read (a BSE code and its NSE
    # symbol) (DD-061: "The two couldn't be compared")
    if sa == sb:
        err(400, "same_symbol", f"{sa} is in both boxes. Pick a different company in one of them.")
    # each side's figures as its own page shows them (market value, P/E, range)
    ca = page_figures(r, source_call(lambda: hub.company(r, sa)))
    cb = page_figures(r, source_call(lambda: hub.company(r, sb)))
    if ca.get("symbol") and ca.get("symbol") == cb.get("symbol"):
        err(400, "same_symbol", f"{sa} and {sb} are the same company ({ca['symbol']}). Pick a different company in one of the boxes.")
    try:
        verdict = ai_call(profile, "compare", (r, sa, sb, datetime.now(IST).date().isoformat()), 12 * 3600, refresh,
                          lambda: A.compare(ca, cb, _ai))
    except HTTPException as e:
        verdict = {"error": (e.detail or {}).get("message") if isinstance(e.detail, dict) else str(e.detail)}
    is_open = market_open(r)
    return ok({"a": {**ca, "market_open": is_open, "phase": price_phase(r, ca), "quote_day": quote_day(r, ca)},
               "b": {**cb, "market_open": is_open, "phase": price_phase(r, cb), "quote_day": quote_day(r, cb)},
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


known_symbol = None      # (region, symbol) -> True, False (no such listed instrument) or None (can't tell); set by main


@router.get("/watchlist/facts")
def watchlist_facts(region: str = "IN", symbols: str = "", profile=Depends(current_profile)):
    """P/E and the distance below the 52-week high for the watchlist's list view (DD-072: only the price and the day's
    change), from the screener's daily index as its page shows them: a symbol not in the index has none. Nothing is read
    from a market-data source here."""
    r = region_of(region)
    asked = list(dict.fromkeys(s.strip().upper() for s in symbols.split(",") if s.strip()))[:100]
    try:
        from .. import screens
        idx = screens.load_index(r)
    except Exception:
        idx = {"rows": []}
    rows = {x["symbol"]: x for x in idx.get("rows") or [] if x.get("symbol") in asked}
    out = {s: {"pe": rows[s].get("pe"), "from_high": rows[s].get("from_high"), "price_at": rows[s].get("price_at")} for s in asked if s in rows}
    return ok({"facts": out, "as_of": screens.as_of(idx) if rows else None})


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
        sym = symbol_of(i.symbol, i.region)            # BRK.B is kept as BRK-B, once (R13-001)
        k = (i.region, sym)
        if k not in seen:
            seen.add(k)
            items.append({"region": i.region, "symbol": sym, "name": i.name})
    before = get_watchlist(profile)["items"]
    before = before if isinstance(before, list) else []
    had = {(i.get("region"), str(i.get("symbol") or "").upper()) for i in before if isinstance(i, dict)}
    # a symbol added must be a listed company or fund: one typed and saved as it was ("ZZZZQQ") showed a row of dashes, was
    # counted on At a glance and offered a deep dive (DD-070). One already on the list stays; a list that can't be read to
    # tell (None) doesn't stop the save
    for i in items:
        if (i["region"], i["symbol"].upper()) not in had and callable(known_symbol) and known_symbol(i["region"], i["symbol"]) is False:
            err(400, "unknown_symbol", f"{i['symbol']} isn't a listed company or fund StratLab knows, so it wasn't added. "
                "Pick one from the suggestions, or check the symbol.")
    db.set_setting(_watch_key(profile), json.dumps({"items": items}))
    if any((i["region"], i["symbol"].upper()) not in had for i in items):     # a stock added, not only removed
        from .. import invite_rewards
        invite_rewards.safe_touch(profile, "watchlist")
    return {"items": items}
