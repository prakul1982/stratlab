"""/trade/fo-changes: the F&O contract changes desk's API (the Trade space).

The dated list and the badges are for everyone signed in; the alert on changes touching your watchlist or paper
sessions is on Basic and up. The admins can read the sources at once."""
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from . import admin, fo_changes as F, stock_alerts
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, access_plan, allows

router = APIRouter(tags=["fo-changes"])


def _m():
    """The main module, for the shared helpers and the exchange client. Imported late: it imports us."""
    from . import main
    return main


class FoAlertReq(BaseModel):
    on: bool


def listed_expiries():
    """expiry(symbol, month): the month's last listed futures expiry from the day's contract list when the app has
    it, else the exchange's rule."""
    idx: dict[tuple[str, str], str] = {}
    try:
        od = _m().options_data
        od._load()
        for r in getattr(od, "_rows", {}).get("NFO", []):
            if r.get("type") == "FUT" and r.get("expiry"):
                k = (str(r.get("name") or "").upper(), r["expiry"][:7])
                idx[k] = max(idx.get(k, ""), r["expiry"])
    except Exception:
        idx = {}

    def expiry(sym: str, month: str) -> date:
        hit = idx.get((sym, month))
        return date.fromisoformat(hit) if hit else F.rule_expiry(month)
    return expiry


def alerts_allowed(profile: dict) -> bool:
    return allows(access_plan(profile), "fo_alerts")


def _send(profile: dict, subject: str, text: str) -> list[str]:
    """Phone and Telegram as set up in Account, and email only to an address the user confirmed (as the stock
    alerts do), each opening the F&O changes page."""
    from . import alerts
    sent = []
    for channel, send in alerts.jobs_for(profile, subject, text, "/trade/fo-changes"):
        if channel == "email":
            continue
        try:
            send()
            sent.append(channel)
        except Exception as e:
            print("fo changes alert failed:", channel, str(e)[:120])
    to = alerts.newsletter_email(profile)
    if to and alerts.email_ready() and alerts.email_confirmed(profile):
        try:
            alerts.send_message(to, subject, text, "/trade/fo-changes", "F&O changes",
                                "You get this because you turned on F&O change alerts on StratLab.")
            sent.append("email")
        except Exception as e:
            print("fo changes alert failed: email", str(e)[:120])
    return sent


# the job: twice a trading day, through the exchange client (the tests swap main.filings_feed)
job = F.Job(lambda: _m().filings_feed, lambda new: F.fire(new, alerts_allowed, _send), expiry=listed_expiries)


def _alerts(profile: dict) -> dict:
    row = F.alert_row(profile["id"])
    return {"on": row["on"], "allowed": allows(profile["_plan"], "fo_alerts"), "plan": PLANS[FEATURE_PLAN["fo_alerts"]]["name"],
            "channels": stock_alerts.channels(profile)}


@router.get("/trade/fo-changes")
def fo_changes_view(profile=Depends(current_profile)):
    """Every F&O contract change kept, newest date first, with the badges for the stocks they touch, the stocks on
    your watchlist and in your paper sessions (for the "only mine" filter), and your alert setting."""
    v = F.view()
    try:
        mine = sorted(F.tracked(profile["id"], running_only=False))
    except Exception:
        mine = []
    return _m().ok({**v, "mine": mine, "alerts": _alerts(profile)})


@router.put("/trade/fo-changes/alerts")
def fo_changes_alerts(req: FoAlertReq, profile=Depends(current_profile)):
    """Turn the alert on changes touching your watchlist or running paper sessions on or off (on: Basic and up)."""
    if req.on:
        _m().need(profile, "fo_alerts", "Alerts on F&O contract changes")
    F.set_alert(profile["id"], req.on)
    return _m().ok(_alerts(profile))


@router.post("/admin/fo-changes/refresh")
def fo_changes_refresh(_=Depends(admin.admin_profile)):
    """Read the contract file and the circulars now (no alerts are sent from here) and say what each answered."""
    out = F.refresh(_m().filings_feed, expiry=listed_expiries())
    job.record(F.ist_now(), out["problems"], F.SOURCES_READ, added=out["added"])
    return _m().ok({"added": out["added"], "problems": out["problems"], "sources": F.view()["sources"], "job": job.status})
