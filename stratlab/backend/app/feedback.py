"""Help & feedback (owner, 4 Nov): anyone, signed in or not, reports something broken, a feature that isn't working, or an idea.

Each report is stored in the app's settings store with the last MAX_KEPT kept (no table, no job), and listed in Admin →
Feedback with a status (New / Seen / Fixed). What is attached is only what helps find the problem: the page's path, the app's
version, the browser and system in a few words, the screen size, the plan and whether the person was signed in. Never the
form's other fields, tokens or anything else about the person. A reply address is kept only when a reply is asked for: the
account's own email for a signed-in person (looked up here, never sent by the page), or the one a signed-out person typed.

Each new report is emailed to the admins (ADMIN_EMAILS, the same addresses as every owner-only alert) through the app's mail
path, at most FEEDBACK_EMAILS_PER_DAY a day; past that the reports wait in the inbox and the next day's first email says how
many did. Mail is sent after the report is saved, off the request, and a failure never loses or blocks the report."""
import json
import re
import secrets
import threading
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from . import admin, db, guard
from .auth import current_profile
from .config import settings
from .responses import err

KEY = "feedback"                    # the reports, newest last
MAIL_KEY = "feedback_mail"          # {"day", "sent", "held"}: today's emails and the reports past the cap
MAX_KEPT = 1000                     # a report is at most ~2.5 KB, so the store stays small
MAX_TEXT = 2000
TYPES = {"broken": "Something's broken", "not_working": "A feature isn't working", "idea": "Idea for a new feature"}
STATUSES = ("new", "seen", "fixed")
SIGNED_IN_HOUR, SIGNED_OUT_HOUR = 10, 3   # reports an hour: a person, and (stricter) an address with nobody signed in
SEND_IN_BACKGROUND = True           # tests send in line, to read what went out
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,}$")
IST = ZoneInfo("Asia/Kolkata")

router = APIRouter()
_lock = threading.Lock()


def _m():
    from . import main
    return main


class Report(BaseModel):
    type: Literal["broken", "not_working", "idea"]
    text: str = Field(..., min_length=1, max_length=MAX_TEXT)
    reply: bool = False
    email: str | None = Field(None, max_length=200)          # signed out only; ignored for a signed-in person
    path: str = Field("/", max_length=300)
    version: str = Field("", max_length=40)
    browser: str = Field("", max_length=120)                  # "Chrome 130 on Android": a few words, not the full user agent
    screen: str = Field("", max_length=20)                    # "390×844"


class StatusReq(BaseModel):
    status: Literal["new", "seen", "fixed"]


def _load() -> list[dict]:
    try:
        rows = json.loads(db.get_setting(KEY) or "[]")
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _save(rows: list[dict]) -> None:
    db.set_setting(KEY, json.dumps(rows[-MAX_KEPT:], ensure_ascii=False))


def _clean_path(p: str) -> str:
    """The page's path only: no query or fragment (they can hold a search, a token or a sign-in code)."""
    p = (p or "/").split("?")[0].split("#")[0].strip()
    return p if p.startswith("/") else "/"


def _plain(s: str, n: int) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", " ", s or "").strip()[:n]


def new_count() -> int:
    return sum(1 for r in _load() if r.get("status") == "new")


def mail_text(r: dict) -> tuple[str, str]:
    """The email for one report: its type, page, plan, signed in or not, the words and whether a reply is wanted. Nothing else
    about the person (no address, no account id)."""
    words = " ".join(r["text"].split())
    first = words[:60] + ("…" if len(words) > 60 else "")
    subject = f"[StratLab feedback] {TYPES[r['type']]}: {first}"
    body = "\n".join([f"Type: {TYPES[r['type']]}", f"Page: {r['path']}", f"Plan: {r['plan']}",
                      f"Signed in: {'yes' if r['signed_in'] else 'no'}", f"Reply wanted: {'yes' if r['reply'] else 'no'}", "",
                      r["text"], "", "Every report is in Admin → Feedback."])
    return subject, body


def _mail(r: dict) -> None:
    """Email the admins about a new report, within the day's cap. Never raises."""
    try:
        if not settings.FEEDBACK_EMAILS:
            return
        from . import alerts
        to = sorted(admin.admin_emails())
        if not to or not alerts.email_ready():
            return
        day = datetime.now(IST).date().isoformat()
        with _lock:
            try:
                st = json.loads(db.get_setting(MAIL_KEY) or "{}")
            except Exception:
                st = {}
            carried = 0
            if st.get("day") != day:
                carried, st = int(st.get("held") or 0), {"day": day, "sent": 0, "held": 0}
            if st["sent"] >= settings.FEEDBACK_EMAILS_PER_DAY:
                st["held"] += 1
                db.set_setting(MAIL_KEY, json.dumps(st))
                return
            st["sent"] += 1
            db.set_setting(MAIL_KEY, json.dumps(st))
        subject, body = mail_text(r)
        if carried:     # the day's summary of the ones past yesterday's cap, in the first email of the day
            body += f"\n\n{carried} more report{'' if carried == 1 else 's'} came in yesterday after the day's {settings.FEEDBACK_EMAILS_PER_DAY} emails: see Admin → Feedback."
        for addr in to:
            try:
                alerts.send_email(addr, subject, body)
            except Exception as e:
                print("feedback email failed:", e)
    except Exception as e:
        print("feedback email failed:", e)


@router.post("/feedback")
def send_feedback(req: Report, request: Request, authorization: str | None = Header(None)):
    """One report, from anyone. Signed in: throttled per person, the plan read here. Signed out: per address, stricter."""
    m = _m()
    profile = current_profile(authorization, None) if authorization else None
    if profile:
        m.throttle(profile, "feedback", SIGNED_IN_HOUR, 3600, "That's a lot of reports in an hour. Try again later.")
    else:
        m.throttle({"id": "ip:" + guard.address(request.scope)}, "feedback", SIGNED_OUT_HOUR, 3600, "That's a lot of reports in an hour. Try again later.")
    text = _plain(req.text, MAX_TEXT)
    if len(text) < 5:
        err(400, "too_short", "Say a few words about what happened, so it can be found.")
    reply_to = None
    if req.reply:
        if profile:
            reply_to = (profile.get("email") or "").strip().lower() or None
        else:
            e = (req.email or "").strip()
            if e and not EMAIL.match(e):
                err(400, "bad_email", "That email address doesn't look right.")
            reply_to = e.lower() or None
    from . import plans
    r = {"id": secrets.token_urlsafe(8), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "type": req.type, "text": text,
         "path": _clean_path(req.path)[:200], "version": _plain(req.version, 40), "browser": _plain(req.browser, 120), "screen": _plain(req.screen, 20),
         "plan": plans.plan_of(profile) if profile else "signed out", "signed_in": bool(profile), "reply": bool(reply_to),
         "reply_to": reply_to, "user_id": profile["id"] if profile else None, "status": "new"}
    with _lock:
        rows = _load()
        rows.append(r)
        _save(rows)
    if SEND_IN_BACKGROUND:
        threading.Thread(target=_mail, args=(r,), daemon=True, name="feedback-mail").start()
    else:
        _mail(r)
    return {"ok": True, "id": r["id"]}


@router.get("/admin/feedback")
def list_feedback(type: str = "", status: str = "", profile=Depends(admin.admin_profile)):
    rows = list(reversed(_load()))
    counts = {s: sum(1 for r in rows if r.get("status") == s) for s in STATUSES}
    if type in TYPES:
        rows = [r for r in rows if r.get("type") == type]
    if status in STATUSES:
        rows = [r for r in rows if r.get("status") == status]
    # the reply address is shown only where a reply was asked for; the account id stays on the server
    return {"rows": [{k: v for k, v in r.items() if k != "user_id"} for r in rows[:500]], "total": len(rows), "counts": counts, "types": TYPES}


@router.put("/admin/feedback/{fid}")
def set_feedback_status(fid: str, req: StatusReq, profile=Depends(admin.admin_profile)):
    with _lock:
        rows = _load()
        hit = next((r for r in rows if r.get("id") == fid), None)
        if hit is None:
            err(404, "not_found", "That report isn't there any more.")
        hit["status"] = req.status
        _save(rows)
    return {"ok": True, "status": req.status}
