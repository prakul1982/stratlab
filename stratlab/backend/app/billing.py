"""Razorpay subscriptions: Basic and Pro, monthly or (when those plans are set up) yearly. Prices live in plans.py."""
import json
from datetime import datetime, timedelta, timezone

import razorpay
from razorpay.errors import BadRequestError, SignatureVerificationError

from . import db
from .config import settings

_client = None


def client() -> razorpay.Client:
    global _client
    if _client is None:
        _client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    return _client


def plan_ids(period: str = "month") -> dict:
    if period == "year":
        return {"basic": settings.RAZORPAY_PLAN_BASIC_YEAR, "pro": settings.RAZORPAY_PLAN_PRO_YEAR}
    return {"basic": settings.RAZORPAY_PLAN_BASIC, "pro": settings.RAZORPAY_PLAN_PRO}


def enabled() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and all(plan_ids().values()))


def yearly_enabled() -> bool:
    return enabled() and all(plan_ids("year").values())


def plan_for(sub: dict) -> str | None:
    notes = sub.get("notes") or {}
    if isinstance(notes, dict) and notes.get("plan") in ("basic", "pro"):
        return notes["plan"]
    ids = {v: k for period in ("month", "year") for k, v in plan_ids(period).items() if v}
    return ids.get(sub.get("plan_id"))


def _ts(v) -> str:
    if v:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).isoformat()
    return (datetime.now(timezone.utc) + timedelta(days=31)).isoformat()


def _mask(v: str) -> str:
    return f"{v[:9]}…{v[-4:]}" if len(v) > 14 else ("set" if v else "missing")


def check_setup() -> dict:
    """Ask Razorpay whether the keys work and each plan exists, for the admin's "Check payments setup" button.
    Nothing secret is returned: the key ID is shortened and the secret only reported by length."""
    key, secret = settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET
    mode = "live" if key.startswith("rzp_live_") else "test" if key.startswith("rzp_test_") else "unknown"
    out = {"key_id": _mask(key), "mode": mode, "secret_length": len(secret),
           "webhook_secret_set": bool(settings.RAZORPAY_WEBHOOK_SECRET), "keys_ok": False, "keys_error": None, "plans": []}
    if not key or not secret:
        out["keys_error"] = "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must both be set."
        return out
    probe = razorpay.Client(auth=(key, secret))   # a fresh client, so a changed key is tried now
    try:
        probe.plan.all({"count": 1})
        out["keys_ok"] = True
    except Exception as e:
        out["keys_error"] = (str(e) or e.__class__.__name__)[:200]
        return out
    for label, pid in (("Basic monthly", settings.RAZORPAY_PLAN_BASIC), ("Pro monthly", settings.RAZORPAY_PLAN_PRO),
                       ("Basic yearly", settings.RAZORPAY_PLAN_BASIC_YEAR), ("Pro yearly", settings.RAZORPAY_PLAN_PRO_YEAR)):
        row = {"label": label, "id": pid or None, "ok": False, "detail": "Not set" if not pid else None}
        if pid:
            try:
                p = probe.plan.fetch(pid)
                item = p.get("item") or {}
                row.update(ok=True, detail=f"{item.get('name', '')}: ₹{(item.get('amount') or 0) / 100:,.0f} every "
                                           f"{p.get('interval', 1)} {p.get('period', '')}".strip())
            except Exception as e:
                row["detail"] = f"Razorpay can't find this plan with these keys ({(str(e) or 'error')[:120]})"
        out["plans"].append(row)
    return out


def create_subscription(profile: dict, plan: str, period: str = "month") -> dict:
    if not enabled():
        raise ValueError("Payments aren't set up on the server yet.")
    if period == "year" and not yearly_enabled():
        raise ValueError("Yearly billing isn't set up yet; pick monthly.")
    sub = client().subscription.create({
        "plan_id": plan_ids(period)[plan],
        "total_count": 10 if period == "year" else 120,   # up to 10 years of renewals; users can cancel any time
        "quantity": 1,
        "customer_notify": 1,
        "notes": {"user_id": profile["id"], "plan": plan, "period": period},
    })
    db.update_profile(profile["id"], pending_subscription_id=sub["id"])
    return {"subscription_id": sub["id"], "key_id": settings.RAZORPAY_KEY_ID,
            "email": profile.get("email"), "plan": plan}


def activate(profile: dict, sub: dict):
    plan = plan_for(sub)
    if not plan:
        return
    old = profile.get("razorpay_subscription_id")
    # Save the new subscription first, so the "cancelled" webhook for the old one is ignored
    db.update_profile(profile["id"], plan=plan, plan_status="active", razorpay_subscription_id=sub["id"],
                      current_period_end=_ts(sub.get("current_end")), pending_subscription_id=None,
                      cancel_at_period_end=False)
    if old and old != sub["id"] and profile.get("plan_status") == "active":
        try:  # switching plans: stop billing the old subscription now
            client().subscription.cancel(old, {"cancel_at_cycle_end": 0})
        except Exception as e:
            print("could not cancel old subscription:", e)


def verify_checkout(profile: dict, payment_id: str, sub_id: str, signature: str):
    client().utility.verify_subscription_payment_signature({
        "razorpay_subscription_id": sub_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature,
    })
    sub = client().subscription.fetch(sub_id)
    if (sub.get("notes") or {}).get("user_id") != profile["id"]:
        raise SignatureVerificationError("Subscription belongs to another user.")
    activate(profile, sub)


def handle_webhook(body: bytes, signature: str):
    if not settings.RAZORPAY_WEBHOOK_SECRET or not signature:
        # an empty secret would let anyone forge a valid signature
        raise SignatureVerificationError("Webhook secret is not configured.")
    client().utility.verify_webhook_signature(body.decode(), signature, settings.RAZORPAY_WEBHOOK_SECRET)
    event = json.loads(body)
    name = event.get("event", "")
    sub = (event.get("payload", {}).get("subscription") or {}).get("entity")
    if not sub:
        return
    profile = db.profile_by_subscription(sub["id"])
    if not profile:
        uid = (sub.get("notes") or {}).get("user_id")
        profile = db.get_profile(uid) if uid else None
    if not profile:
        return
    if name in ("subscription.activated", "subscription.charged", "subscription.resumed"):
        activate(profile, sub)
    elif name in ("subscription.cancelled", "subscription.completed", "subscription.halted", "subscription.paused"):
        if profile.get("razorpay_subscription_id") == sub["id"]:
            db.update_profile(profile["id"], plan="free", plan_status=sub.get("status", "cancelled"),
                              cancel_at_period_end=False)


def cancel(profile: dict):
    sid = profile.get("razorpay_subscription_id")
    if not sid or profile.get("plan_status") != "active":
        raise ValueError("No active subscription.")
    if profile.get("cancel_at_period_end"):
        raise ValueError("Your subscription is already cancelled.")
    try:
        client().subscription.cancel(sid, {"cancel_at_cycle_end": 1})
    except BadRequestError as e:
        raise ValueError(f"Razorpay couldn't cancel the subscription: {e}")
    db.update_profile(profile["id"], cancel_at_period_end=True)
