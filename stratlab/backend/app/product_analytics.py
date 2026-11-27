"""Usage analytics from the server: the events the browser can't be trusted to send (a payment going through, which
an ad blocker or a closed tab would lose), sent to PostHog's capture API.

Off unless POSTHOG_KEY is set. Each send runs in a background thread with a short timeout, so a slow or broken
analytics service never holds up or fails a request. Events carry the internal user id and a few plain words (plan,
period), never an email, a name or an amount."""
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from . import db
from .config import settings

BACKGROUND = True                 # tests turn this off to send in the calling thread
TIMEOUT = 5
SENT = "posthog-sent:"            # app_settings marker: an event that must go once (a payment) went


def enabled() -> bool:
    return bool(settings.POSTHOG_KEY)


def internal(profile: dict | None) -> bool:
    """conv101 (T2): one of StratLab's own accounts, left out of analytics: an ADMIN_EMAILS address, an admin's "+sl-" test account (or one
    POST /admin/test-account recorded), or an ANALYTICS_INTERNAL_EMAILS address. /me says it (`internal`), so the browser sends nothing either."""
    if not profile:
        return False
    from . import admin
    email = (profile.get("email") or "").strip().lower()
    extra = {x.strip().lower() for x in (settings.ANALYTICS_INTERNAL_EMAILS or "").split(",") if x.strip()}
    try:
        if email and (email in admin.admin_emails() or email in extra or admin.is_test_email(email)):
            return True
        return str(profile.get("id") or "") in admin.recorded_tests()
    except Exception as e:
        print("analytics internal check failed:", str(e)[:160])
        return False


def off(header: str | None) -> bool:
    """The browser said it is left out of analytics (X-Analytics: off: Do Not Track, a robot, StratLab's own device)."""
    return (header or "").strip().lower() == "off"


def _post(body: dict):
    try:
        r = httpx.post(f"{settings.POSTHOG_HOST}/i/v0/e/", json=body, timeout=TIMEOUT)
        if r.status_code >= 400:
            print("posthog capture refused:", r.status_code, r.text[:160])
    except Exception as e:
        print("posthog capture failed:", str(e)[:160])


def capture(user_id: str, event: str, props: dict | None = None, once: str = "", at: datetime | None = None, profile_of: dict | None = None) -> bool:
    """Send one event for a user, off the request. `once` names it for good (a payment id), so a webhook that comes
    again doesn't count it twice. `profile_of`: the account, so one of StratLab's own sends nothing (internal). False when analytics is off or
    it was already sent; never raises."""
    if not enabled() or not user_id:
        return False
    if profile_of is not None and internal(profile_of):
        return False
    try:
        if once:
            if db.get_setting(SENT + once):
                return False
            db.set_setting(SENT + once, "1")
        body = {
            "api_key": settings.POSTHOG_KEY, "event": event, "distinct_id": str(user_id),
            "properties": {**(props or {}), "$lib": "stratlab-server"},
            "timestamp": (at or datetime.now(timezone.utc)).isoformat(),
            # the same event id every time for the same once-key, so PostHog drops a repeat as well
            "uuid": str(uuid.uuid5(uuid.NAMESPACE_URL, f"stratlab:{event}:{once}")) if once else str(uuid.uuid4()),
        }
    except Exception as e:
        print("posthog capture skipped:", str(e)[:160])
        return False
    if BACKGROUND:
        threading.Thread(target=_post, args=(body,), daemon=True, name="posthog").start()
    else:
        _post(body)
    return True


def payment_completed(profile: dict, payment: dict, plan: str, period: str):
    """A plan payment went through (checkout or the renewal webhook): plan and period only, not the amount."""
    created = payment.get("created_at")
    at = datetime.fromtimestamp(created, timezone.utc) if isinstance(created, (int, float)) and created > 0 else None
    return capture(profile.get("id", ""), "payment completed", {"plan": plan, "period": period},
                   once=f"pay:{payment.get('id')}", at=at, profile_of=profile)


WORD = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")
SIGNUP_WINDOW = timedelta(days=1)          # an account made this long ago or less, signing in, is a sign-up


def _created(profile: dict) -> datetime | None:
    try:
        at = datetime.fromisoformat(str(profile.get("created_at") or "").replace("Z", "+00:00"))
        return at if at.tzinfo else at.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def signed_up(profile: dict, source: str | None, now: datetime | None = None) -> bool:
    """conv101 (T3): "signed up", from the server, once per account (an ad blocker or a second browser can't drop or double it), at the
    moment the account was made, with where the visit came from (`source`: stock, theme, blog, directory… from the public page's link; one
    plain word or nothing). Only for an account made in the last day. True when it was sent now (the first time)."""
    at = _created(profile)
    now = now or datetime.now(timezone.utc)
    if not at or now - at > SIGNUP_WINDOW:
        return False
    props = {"source": source} if isinstance(source, str) and WORD.match(source) else {}
    return capture(profile.get("id", ""), "signed up", props, once=f"signup:{profile.get('id')}", at=at, profile_of=profile)


CHECKOUT_EVENTS = {"started": "checkout started", "dismissed": "checkout dismissed", "failed": "checkout failed"}


def checkout(profile: dict, step: str, plan: str, period: str) -> bool:
    """conv101 (T3): a checkout step from the server: started (a subscription was made for the payment window), dismissed or failed (the
    window told the page, which told the server). Completed is payment_completed. Plan and period only, never an amount."""
    event = CHECKOUT_EVENTS.get(step)
    if not event or plan not in ("basic", "pro") or period not in ("month", "year"):
        return False
    return capture(profile.get("id", ""), event, {"plan": plan, "period": period}, profile_of=profile)
