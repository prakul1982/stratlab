"""/trade/events: the market events calendar's API (the Trade space; its next events also show on the Invest home).

The dated list, the index changes and their badges are for everyone signed in, and so is sending the events to your
own Money calendar; reminders by phone, Telegram or email are on Basic and up. The admins can read the sources at
once and add events that have no published calendar (the Budget)."""
import json
import re
import threading
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import admin, db, market_events as M, stock_alerts
from .auth import current_profile
from .intel.filings import ist_now
from .intel.net import TTLCache
from .plans import FEATURE_PLAN, PLANS, allows, plan_of
from .responses import err

router = APIRouter(tags=["market-events"])
_views = TTLCache(max_items=8)
MAX_CUSTOM = 200


def _m():
    """The main module, for the shared helpers and the option contracts. Imported late: it imports us."""
    from . import main
    return main


def listed(exchange: str, name: str) -> list[str]:
    """The listed option expiries of an underlying (ISO dates from today), or nothing when the contracts aren't loaded."""
    try:
        return list(_m().options_data.expiries(exchange, name))
    except Exception:
        return []


def view(today: date | None = None) -> dict:
    """The shared answer, kept five minutes (expiries and holidays are worked out each time it is built)."""
    today = today or ist_now().date()
    hit = _views.get(today.isoformat())
    if hit is None:
        hit = M.view(today, listed)
        _views.set(today.isoformat(), hit, 300)
    return hit


def forget():
    _views.clear()
    M._cache.clear()


def reminders_allowed(profile: dict) -> bool:
    return allows(plan_of(profile), "event_reminders")


def _send(profile: dict, subject: str, text: str) -> list[str]:
    """Phone and Telegram as set up in Account, and email only to an address the user confirmed (as the other alerts
    do), each opening the Events page."""
    from . import alerts
    sent = []
    for channel, send in alerts.jobs_for(profile, subject, text, "/trade/events"):
        if channel == "email":
            continue
        try:
            send()
            sent.append(channel)
        except Exception as e:
            print("market events reminder failed:", channel, str(e)[:120])
    to = alerts.newsletter_email(profile)
    if to and alerts.email_ready() and alerts.email_confirmed(profile):
        try:
            alerts.send_message(to, subject, text, "/trade/events", "Market events",
                                "You get this because you turned on market event reminders on StratLab.")
            sent.append("email")
        except Exception as e:
            print("market events reminder failed: email", str(e)[:120])
    return sent


# the job: twice a day, reading the official pages (the tests swap the readers' web for fixtures)
job = M.Job(lambda: M.Web(), lambda day: M.send_reminders(day, reminders_allowed, _send))


def _week_counts(today: date) -> dict:
    """How many results meetings and corporate actions the stored calendars hold for the next seven days (both
    calendars have their own pages; this only points there)."""
    from . import corp_actions, results
    out = {"results": None, "actions": None}
    try:
        out["results"] = len(results.between("IN", today, today + timedelta(days=6)))
    except Exception:
        pass
    try:
        out["actions"] = len(corp_actions.between("IN", today, today + timedelta(days=6)))
    except Exception:
        pass
    return out


def _prefs(profile: dict) -> dict:
    p = M.prefs(profile["id"])
    return {"remind": p["remind"], "kinds": p["kinds"], "days": p["days"], "money_calendar": p["money_calendar"],
            "allowed": allows(profile["_plan"], "event_reminders"), "plan": PLANS[FEATURE_PLAN["event_reminders"]]["name"],
            "channels": stock_alerts.channels(profile), "remind_days": list(M.REMIND_DAYS)}


@router.get("/trade/events")
def events_view(profile=Depends(current_profile)):
    """Every scheduled market event from six months back to a year ahead, the index changes, the badges for the stocks
    they touch, each source's date, your reminder choices and the week's counts from the results and dividends
    calendars."""
    today = ist_now().date()
    return _m().ok({**view(today), "prefs": _prefs(profile), "week": _week_counts(today),
                    "custom_kinds": {k: M.KINDS[k] for k in ("budget", "rbi", "india", "us", "index")}})


class PrefsReq(BaseModel):
    remind: bool = False
    kinds: list[str] = Field(default_factory=lambda: ["rbi", "india", "us", "budget", "index"], max_length=len(M.KINDS))
    days: int = Field(1, ge=0, le=7)
    money_calendar: bool = False


@router.put("/trade/events/prefs")
def events_prefs(req: PrefsReq, profile=Depends(current_profile)):
    """Your reminder choices (on: Basic and up), the kinds of event and how many days before, and whether the events
    also go into your Money calendar and its feed (every plan)."""
    if req.remind:
        _m().need(profile, "event_reminders", "Reminders of market events")
    if req.days not in M.REMIND_DAYS:
        err(400, "bad_days", "Pick the day itself, or 1, 2 or 7 days before.")
    kinds = [k for k in dict.fromkeys(req.kinds) if k in M.KINDS]
    if req.remind and not kinds:
        err(400, "no_kinds", "Pick at least one kind of event to be reminded of.")
    p = M.prefs(profile["id"])
    p.update(remind=req.remind, kinds=kinds, days=req.days, money_calendar=req.money_calendar)
    M.save_prefs(profile["id"], p)
    return _m().ok(_prefs(profile))


@router.get("/trade/events/badges")
def events_badges(profile=Depends(current_profile)):
    """Only the index badges ({symbol: [...]}), for company pages."""
    return _m().ok({"badges": view()["badges"]})


_refreshing = threading.Lock()


@router.post("/admin/events/refresh")
def events_refresh(_=Depends(admin.admin_profile)):
    """Read every source again now, in the background (the first read takes a minute or two); no reminders are sent
    from here."""
    if not _refreshing.acquire(blocking=False):
        return _m().ok({"started": False, "sources": M.sources(), "job": job.status})

    def run():
        try:
            out = M.refresh(M.Web())
            job.record(ist_now(), out["problems"], len(M.READERS))
        except Exception as e:
            print("market events refresh failed:", type(e).__name__, str(e)[:160])
        finally:
            forget()
            _refreshing.release()
    threading.Thread(target=run, daemon=True, name="market-events-refresh").start()
    return _m().ok({"started": True, "sources": M.sources(), "job": job.status})


class CustomReq(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: str = Field("budget", pattern="^(budget|rbi|india|us|index)$")
    title: str = Field(min_length=3, max_length=100)
    detail: str = Field("", max_length=400)
    time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    url: str | None = Field(None, max_length=300)


@router.post("/admin/events/custom")
def events_custom_add(req: CustomReq, _=Depends(admin.admin_profile)):
    """Add an event with no published calendar (the Budget, a special session), with its official link."""
    d = M._day(req.date)
    today = ist_now().date()
    if not d or not today - timedelta(days=400) <= d <= today + timedelta(days=800):
        err(400, "bad_date", "Pick a real day within the last year or the next two.")
    if req.url and not re.match(r"^https://[\w.-]+\.(?:gov\.in|nic\.in|org\.in|gov|com|in)(?:/\S*)?$", req.url):
        err(400, "bad_url", "Give the official https link, or none.")
    rows = db.json_value(db.get_setting(M.CUSTOM_KEY), [])
    if len(rows) >= MAX_CUSTOM:
        err(400, "too_many", f"Up to {MAX_CUSTOM} added events; delete an old one first.")
    rows.append({"id": uuid.uuid4().hex[:12], "date": d.isoformat(), "kind": req.kind, "title": " ".join(req.title.split()),
                 "detail": " ".join(req.detail.split()), "time": req.time, "url": req.url})
    db.set_setting(M.CUSTOM_KEY, json.dumps(rows, separators=(",", ":")))
    forget()
    return _m().ok({"custom": rows})


@router.delete("/admin/events/custom/{cid}")
def events_custom_delete(cid: str, _=Depends(admin.admin_profile)):
    rows = db.json_value(db.get_setting(M.CUSTOM_KEY), [])
    if not any(isinstance(r, dict) and r.get("id") == cid for r in rows):
        err(404, "not_found", "That event isn't there any more.")
    rows = [r for r in rows if not (isinstance(r, dict) and r.get("id") == cid)]
    db.set_setting(M.CUSTOM_KEY, json.dumps(rows, separators=(",", ":")))
    forget()
    return _m().ok({"custom": rows})
