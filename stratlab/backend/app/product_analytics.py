"""Usage analytics from the server: the events the browser can't be trusted to send (a payment going through, which
an ad blocker or a closed tab would lose), sent to PostHog's capture API.

Off unless POSTHOG_KEY is set. Each send runs in a background thread with a short timeout, so a slow or broken
analytics service never holds up or fails a request. Events carry the internal user id and a few plain words (plan,
period), never an email, a name or an amount."""
import threading
import uuid
from datetime import datetime, timezone

import httpx

from . import db
from .config import settings

BACKGROUND = True                 # tests turn this off to send in the calling thread
TIMEOUT = 5
SENT = "posthog-sent:"            # app_settings marker: an event that must go once (a payment) went


def enabled() -> bool:
    return bool(settings.POSTHOG_KEY)


def _post(body: dict):
    try:
        r = httpx.post(f"{settings.POSTHOG_HOST}/i/v0/e/", json=body, timeout=TIMEOUT)
        if r.status_code >= 400:
            print("posthog capture refused:", r.status_code, r.text[:160])
    except Exception as e:
        print("posthog capture failed:", str(e)[:160])


def capture(user_id: str, event: str, props: dict | None = None, once: str = "", at: datetime | None = None) -> bool:
    """Send one event for a user, off the request. `once` names it for good (a payment id), so a webhook that comes
    again doesn't count it twice. False when analytics is off or it was already sent; never raises."""
    if not enabled() or not user_id:
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
                   once=f"pay:{payment.get('id')}", at=at)
