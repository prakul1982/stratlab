"""Data status: one public page listing each dataset StratLab keeps, when it was last updated, when it is next due, and whether it is
on time or late.

Built from the records the background jobs already keep for Admin (job_status, each job's own stored state and each dataset's own
stamp) and from the jobs' own clocks (the constants they run by), so the page and the jobs never disagree about when something is due.
Only safe facts go out: a dataset's public name, its market, the time of its last update and the day it covers, when it is next due,
and a state. No job's internal name, no data source's name, no error text and nothing about the servers: a late dataset says "Late",
never why.

A dataset is "Late" once its most recent due time, plus the time its run usually takes (`grace`), has passed with no update since; in
that window it is "Updating". Days a market is shut (weekends, the exchange's holidays) are no due days for a dataset that follows
that market. The answer is worked out at most once a minute (CACHE_FOR) and shared by everyone, and the page and its JSON say the same.

Times are written in India time (IST) for India's datasets and New York time (ET) for the US's, with the zone; a dataset of both
markets is written in IST."""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

from . import db, job_status

IST, ET = ZoneInfo("Asia/Kolkata"), ZoneInfo("America/New_York")
ZONE = {"IN": (IST, "IST"), "US": (ET, "ET"), "both": (IST, "IST")}
MARKET = {"IN": "India", "US": "US", "both": "India and US"}
TZ_OF = {"Asia/Kolkata": IST, "America/New_York": ET}
CACHE_FOR = 60                     # seconds one answer is shared by everyone
EARLY = 10                         # minutes before a due time an update still counts for it (a run that starts a little early)
STATES = {"on_time": "On time", "updating": "Updating", "late": "Late", "not_yet": "Not updated yet", "on_request": "On request"}
CACHE_CONTROL = f"public, max-age={CACHE_FOR}, s-maxage={CACHE_FOR}, stale-while-revalidate={CACHE_FOR}"


@dataclass
class Slot:
    """A daily due time: the clock in a zone, on every day or only on the trading days of a market's calendar."""
    tz: ZoneInfo
    at: str                        # "HH:MM"
    market: str | None = None      # "IN" or "US": only that market's trading days; None: every day


@dataclass
class Dataset:
    id: str                        # a public slug, never a job's internal name
    name: str
    market: str                    # "IN", "US" or "both"
    group: str
    feeds: str                     # what in StratLab uses it, in a few words
    last: Callable[[], tuple]      # () -> (when it was last updated: an ISO time or epoch seconds, the day the data covers or None)
    slots: list[Slot] = field(default_factory=list)
    grace: int = 90                # minutes a run usually takes after its due time
    on_request: bool = False       # updated when someone asks (no clock): never late


# ---------- reading the records ----------
def _main():
    """The running app's module (where the jobs live), or None in a bare import."""
    return sys.modules.get("app.main")


def _kept(attr: str | None, key: str, owner=None) -> dict:
    """A job's status as Admin reads it: the running job's own once it has run, else the one stored before a restart."""
    job = owner if owner is not None else (getattr(_main(), attr, None) if attr else None)
    st = dict(getattr(job, "status", None) or {}) if job is not None else {}
    try:
        return job_status.kept(key, st)
    except Exception:
        return {}


def _first(*fns):
    """The first of these that gives a value without raising."""
    for fn in fns:
        try:
            v = fn()
        except Exception:
            v = None
        if v:
            return v
    return None


def _when(v) -> datetime | None:
    """An ISO time (with or without its zone: none is UTC) or epoch seconds as an aware time; None when it can't be read."""
    if v in (None, "", 0):
        return None
    try:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return datetime.fromtimestamp(float(v), timezone.utc)
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _heat(region: str) -> tuple:
    from . import heatmap
    raw = db.json_value(db.get_setting(heatmap.KEY + region), {}) or {}
    return raw.get("at"), raw.get("day")


def _breadth(region: str) -> tuple:
    from . import breadth
    s = (breadth.status() or {}).get(region) or {}
    return s.get("ran_at"), s.get("as_of")


def _filings(region: str) -> tuple:
    from . import redflags
    s = redflags.state(region) or {}
    return s.get("at"), s.get("through")


def _brief(region: str) -> tuple:
    st = _kept("newsletter_job", "newsletters")
    rep = (st.get("regions") or {}).get(region) or {}
    return rep.get("at"), rep.get("day")


def _flows() -> tuple:
    from . import positioning as P
    st = _kept("positioning_job", "positioning")
    at = st.get("last_run") or _first(lambda: P.state().get("last_run"))
    day = _first(lambda: P.cash_today().get("as_of"))
    return at, day


def _results() -> tuple:
    return _kept("results_job", "results").get("last_run"), None


def _corp() -> tuple:
    from . import corp_actions
    st = _kept("corp_job", "corp")
    return st.get("last_run") or _first(lambda: max(filter(None, (corp_actions.load(r).get("at") for r in corp_actions.REGIONS)), default=None)), None


def _ipos() -> tuple:
    from . import ipo
    st = _kept(None, "ipo", owner=ipo.job)
    return st.get("last_run") or st.get("read"), None


def _events() -> tuple:
    from . import market_events, market_events_routes
    st = _kept(None, "events", owner=market_events_routes.job)
    return st.get("last_run") or _first(lambda: market_events.load_state().get("last_run")), None


def _fo() -> tuple:
    from . import fo_changes, fo_changes_routes
    st = _kept(None, "fo", owner=fo_changes_routes.job)
    return st.get("last_run") or _first(lambda: fo_changes.load_state().get("last_run")), None


def _surveillance() -> tuple:
    st = _kept("surv_job", "surveillance")
    return st.get("last_run"), None


def _vix() -> tuple:
    from . import vix
    st = _kept("vix_job", "vix")
    return st.get("last_run") or st.get("read"), _first(lambda: max(vix.closes(), default=None))


def _themes() -> tuple:
    from . import computed
    from .intel import theme_library
    es = (computed.index(theme_library.KIND).get("entries") or {}).values()
    newest = max((e.get("at") or 0 for e in es if isinstance(e, dict)), default=0)
    return newest or None, None


# ---------- the datasets ----------
def datasets() -> list[Dataset]:
    """Every dataset on the page, in the order it reads. The clocks are the jobs' own constants."""
    from . import breadth, corp_actions, fo_changes, ipo, market_events, positioning, redflags, results, surveillance, vix
    from .newsletter import job as news

    def daily(market: str | None, runs) -> list[Slot]:
        return [Slot(TZ_OF[tz], at, market) for tz, at in runs]

    prices, company, market_wide, briefs = "Prices and the market", "Companies", "Market data", "Briefs and research"
    out = []
    for r in ("IN", "US"):
        where = MARKET[r]
        run = daily(r, [breadth.RUN_AT[r]])
        out.append(Dataset(f"closes-{r.lower()}", f"{where} closing prices", r, prices,
                           "Each stock's daily close: the heatmap, the market movers and the trend scans",
                           lambda r=r: _heat(r), run, grace=150 if r == "IN" else 90))
        out.append(Dataset(f"breadth-{r.lower()}", f"{where} market breadth", r, prices,
                           "Advances and declines, averages, 52-week highs and lows", lambda r=r: _breadth(r), run,
                           grace=150 if r == "IN" else 90))
    pub_from, pub_until = positioning.PUBLISH_FROM, positioning.PUBLISH_UNTIL
    window = (int(pub_until[:2]) * 60 + int(pub_until[3:])) - (int(pub_from[:2]) * 60 + int(pub_from[3:])) + 30
    out.append(Dataset("flows-in", "FII and DII flows", "IN", prices, "Institutions' net buying in the cash market, and Positioning",
                       _flows, daily("IN", [("Asia/Kolkata", pub_from)]), grace=window))
    out.append(Dataset("vix-in", "India VIX", "IN", prices, "The volatility index's daily history", _vix,
                       daily("IN", [("Asia/Kolkata", vix.CLOSE_AT)]), grace=90))
    for r in ("IN", "US"):
        out.append(Dataset(f"filings-{r.lower()}", f"{MARKET[r]} company filings", r, company,
                           "Filings across every company: fund raises, pledges, resignations and other red flags",
                           lambda r=r: _filings(r), daily(r, [redflags.RUN_AT[r]]), grace=120))
    out.append(Dataset("results", "Results calendar", "both", company, "Results days and each quarter's figures", _results,
                       [Slot(IST, t) for t in results.REFRESH_AT["IN"]] + [Slot(ET, t) for t in results.REFRESH_AT["US"]], grace=120))
    out.append(Dataset("corporate-actions", "Corporate actions", "both", company, "Dividends, splits, bonus issues and their dates", _corp,
                       [Slot(IST, t) for t in corp_actions.REFRESH_AT["IN"]] + [Slot(ET, t) for t in corp_actions.REFRESH_AT["US"]], grace=120))
    reads = [at for name, at in ipo.Job.SLOTS if not name.endswith("-alert")]
    out.append(Dataset("ipos", "IPOs", "both", company, "Upcoming, open and listed issues, India and US", _ipos,
                       [Slot(IST, at) for at in reads], grace=120))
    out.append(Dataset("surveillance", "Surveillance lists", "IN", market_wide, "The exchange's surveillance lists", _surveillance,
                       daily("IN", [(tz, at) for _, tz, at in surveillance.Job.RUNS]), grace=120))
    out.append(Dataset("fo-changes", "F&O contract changes", "IN", market_wide, "Lot sizes and stocks entering or leaving F&O", _fo,
                       daily("IN", [(tz, at) for _, tz, at in fo_changes.Job.RUNS]), grace=120))
    out.append(Dataset("market-events", "Market events", "both", market_wide, "Policy meetings, data releases, expiries and holidays", _events,
                       daily(None, [(tz, at) for _, tz, at in market_events.Job.RUNS]), grace=120))
    for r in ("IN", "US"):
        tz, at = news.SEND_AT[r]
        out.append(Dataset(f"brief-{r.lower()}", f"{MARKET[r]} daily brief", r, briefs, "The market brief after each close",
                           lambda r=r: _brief(r), daily(r, [(tz, at)]), grace=90))
    out.append(Dataset("themes", "Themes library", "both", briefs, "Theme maps kept for everyone; a new theme is mapped when someone asks",
                       _themes, on_request=True))
    return out


# ---------- the clock ----------
def _trading(market: str | None, day: date) -> bool:
    if not market:
        return True
    from .data import calendar
    try:
        return calendar.is_trading_day(market, day)
    except Exception:
        return day.weekday() < 5


def _times(slots: list[Slot], now: datetime, back: int = 8, ahead: int = 10):
    """Every due time of these slots from `back` days before `now` to `ahead` days after, oldest first."""
    out = []
    for s in slots:
        h, m = (int(x) for x in s.at.split(":"))
        today = now.astimezone(s.tz).date()
        for k in range(-back, ahead + 1):
            d = today + timedelta(days=k)
            if _trading(s.market, d):
                out.append(datetime(d.year, d.month, d.day, h, m, tzinfo=s.tz))
    return sorted(out)


def judge(ds: Dataset, last: datetime | None, now: datetime) -> tuple[str, datetime | None]:
    """(state, next due time) of a dataset updated at `last`."""
    if ds.on_request:
        return "on_request", None
    times = _times(ds.slots, now)
    nxt = next((t for t in times if t > now), None)
    past = [t for t in times if t <= now]
    if last is None:
        return "not_yet", nxt
    if not past:
        return "on_time", nxt
    due = past[-1]
    if last >= due - timedelta(minutes=EARLY):
        return "on_time", nxt
    if now < due + timedelta(minutes=ds.grace):
        # the latest due time's update isn't in yet but its run still has time; it is late only if the one before was missed too
        before = [t for t in past[:-1] if t + timedelta(minutes=ds.grace) <= now]
        return ("late" if before and last < before[-1] - timedelta(minutes=EARLY) else "updating"), nxt
    return "late", nxt


def _text(t: datetime | None, zone: ZoneInfo, word: str, now: datetime) -> str | None:
    """"12 Nov, 18:31 IST" (the year added when it isn't this year's)."""
    if t is None:
        return None
    local = t.astimezone(zone)
    year = "" if local.year == now.astimezone(zone).year else f" {local.year}"
    return f"{local.day} {local:%b}{year}, {local:%H:%M} {word}"


def _covers(day) -> str | None:
    try:
        d = date.fromisoformat(str(day)[:10])
    except (TypeError, ValueError):
        return None
    return f"{d.day} {d:%b %Y}"


def build(now: datetime | None = None) -> dict:
    """The page's answer: every dataset with its safe facts, grouped, and how many are late."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for ds in datasets():
        try:
            at, day = ds.last()
        except Exception:                   # a record that can't be read is "not updated yet", never an error on a public page
            at, day = None, None
        last = _when(at)
        if last and last > now + timedelta(minutes=5):
            last = None                     # a clock in the future is not a fact
        state, nxt = judge(ds, last, now)
        zone, word = ZONE[ds.market]
        rows.append({"id": ds.id, "name": ds.name, "market": MARKET[ds.market], "group": ds.group, "feeds": ds.feeds, "zone": word,
                     "last": last.isoformat(timespec="seconds") if last else None, "last_text": _text(last, zone, word, now),
                     "covers": _covers(day), "next": nxt.isoformat(timespec="seconds") if nxt else None,
                     "next_text": _text(nxt, zone, word, now) if nxt else ("When someone asks" if ds.on_request else None),
                     "state": state, "state_text": "No time on record" if state == "not_yet" and day else STATES[state]})
    groups = []
    for r in rows:
        if not groups or groups[-1]["title"] != r["group"]:
            groups.append({"title": r["group"], "rows": []})
        groups[-1]["rows"].append({k: v for k, v in r.items() if k != "group"})
    return {"checked_at": now.isoformat(timespec="seconds"), "checked_text": _text(now, IST, "IST", now), "late": sum(r["state"] == "late" for r in rows),
            "total": len(rows), "groups": groups}


_cache: dict = {}
_lock = threading.Lock()


def cached() -> dict:
    """build(), worked out at most once every CACHE_FOR seconds (one request builds it while the others wait for it)."""
    hit = _cache.get("v")
    if hit and time.monotonic() - hit[0] < CACHE_FOR:
        return hit[1]
    with _lock:
        hit = _cache.get("v")
        if hit and time.monotonic() - hit[0] < CACHE_FOR:
            return hit[1]
        v = build()
        _cache["v"] = (time.monotonic(), v)
        return v


def clear() -> None:
    _cache.clear()


# ---------- the routes ----------
router = APIRouter(tags=["data status"])


@router.get("/public/data-status")
def data_status():
    """Each dataset's last update, next due time and state, for anyone (no sign-in)."""
    return JSONResponse(cached(), headers={"Cache-Control": CACHE_CONTROL})


@router.get("/status", response_class=HTMLResponse)
def status_page():
    """The data status page, for visitors and the signed in alike: plain HTML in the site's own frame."""
    return HTMLResponse(page_html(cached()), headers={"Cache-Control": CACHE_CONTROL})


BADGE = {"on_time": "ok", "updating": "wait", "late": "late", "not_yet": "wait", "on_request": "quiet"}


def page_html(v: dict) -> str:
    from html import escape as e
    from . import stock_pages as sp
    from .config import settings
    site = settings.PUBLIC_SITE_URL
    late = v["late"]
    summary = (f"{late} of {v['total']} datasets {'is' if late == 1 else 'are'} late." if late
               else f"All {v['total']} datasets are on time or updating.")
    body = ['<h1>Data status</h1>',
            '<p class="muted">When each dataset StratLab shows was last updated, and when it is next due. India\'s are in India time (IST), '
            "the US's in New York time (ET). A dataset that follows a market is due only on that market's trading days.</p>",
            f'<p class="ds-sum" data-late="{late}"><b>{e(summary)}</b> <span class="muted small">Checked {e(v["checked_text"] or "")}.</span></p>']
    for g in v["groups"]:
        trs = []
        for r in g["rows"]:
            covers = f'<span class="muted small ds-cov">Covers {e(r["covers"])}</span>' if r["covers"] else ""
            last = f'<span class="ds-t">{e(r["last_text"])}</span>' if r["last_text"] else '<span class="muted">Not yet</span>'
            nxt = f'<span class="ds-t">{e(r["next_text"])}</span>' if r["next_text"] else "–"
            trs.append(f'<tr data-id="{e(r["id"])}" data-state="{e(r["state"])}"><th scope="row"><span class="ds-name">{e(r["name"])}</span>'
                       f'<span class="muted small ds-feeds">{e(r["feeds"])}</span></th>'
                       f'<td>{last}{covers}</td><td>{nxt}</td><td><span class="ds-badge" data-kind="{BADGE[r["state"]]}">{e(r["state_text"])}</span></td></tr>')
        body.append(f'<h2>{e(g["title"])}</h2><div class="card tbl ds"><table><caption class="skip">{e(g["title"])}: last update, next due and state</caption>'
                    '<thead><tr><th scope="col">Data</th><th scope="col">Last updated</th><th scope="col">Next due</th><th scope="col">State</th></tr></thead>'
                    f'<tbody>{"".join(trs)}</tbody></table></div>')
    body.append('<h2>What the states mean</h2><dl class="ds-key">'
                "<dt>On time</dt><dd>Updated since it was last due.</dd>"
                "<dt>Updating</dt><dd>Its due time has passed and its update usually takes a little while; nothing is wrong yet.</dd>"
                "<dt>Late</dt><dd>Its update hasn't arrived in the usual time. The pages keep showing the last update, with its date, until it does.</dd>"
                "<dt>On request</dt><dd>Updated when someone asks for it, not on a clock.</dd></dl>"
                f'<p class="small">Something looks wrong? <a href="{site}/help#feedback">Tell us</a>. '
                '<a href="/stocks/in/movers">India market movers</a> · <a href="/stocks/us/movers">US market movers</a></p>')
    style = ("<style>.ds th[scope=row]{text-align:left;white-space:normal;min-width:180px}.ds td{white-space:normal}"
             ".ds table{table-layout:fixed}.ds th:nth-child(1){width:44%}.ds th:nth-child(2),.ds th:nth-child(3){width:20%}.ds th:nth-child(4){width:16%}"
             ".ds-name{display:block;font-weight:600}.ds-feeds,.ds-cov{display:block;font-weight:400}.ds-t{white-space:nowrap}"
             ".ds-badge{display:inline-block;border-radius:999px;padding:2px 10px;font-size:13px;font-weight:600;border:1px solid var(--line-2);white-space:nowrap}"
             ".ds-badge[data-kind=ok]{color:var(--up);border-color:var(--up)}.ds-badge[data-kind=late]{color:var(--down);border-color:var(--down)}"
             ".ds-badge[data-kind=wait]{color:var(--orange-ink);border-color:var(--orange-ink)}.ds-badge[data-kind=quiet]{color:var(--muted)}"
             ".ds-sum{margin:16px 0 4px}.ds-key dt{font-weight:600;margin-top:10px}.ds-key dd{margin:2px 0 0;color:var(--ink-2);max-width:72ch}"
             "@media (max-width:640px){.ds th:nth-child(n){width:auto}.ds table,.ds tbody,.ds tr,.ds th,.ds td{display:block;width:auto}.ds thead{position:absolute;left:-9999px}"
             ".ds tr{padding:10px 0;border-bottom:1px solid var(--line)}.ds th[scope=row],.ds td{border:0;padding:2px 0;text-align:left;position:static;min-width:0}"
             ".ds td:nth-of-type(1)::before{content:'Last updated: ';color:var(--muted)}.ds td:nth-of-type(2)::before{content:'Next due: ';color:var(--muted)}}</style>")
    head = sp._head("Data status · StratLab", "When each StratLab dataset was last updated and when it is next due: prices, breadth, filings, "
                    "results, flows, briefs and more.", f"{site}/status", style)
    return sp._page(head, None, "".join(body))
