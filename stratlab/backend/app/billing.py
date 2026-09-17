"""Razorpay subscriptions: Basic (Rs 1,999/month) and Pro (Rs 4,900/month)."""
import json
from datetime import datetime, timedelta, timezone

import razorpay
from razorpay.errors import SignatureVerificationError

from . import db
from .config import settings

_client = None


def client() -> razorpay.Client:
    global _client
    if _client is None:
        _client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    return _client


def plan_ids() -> dict:
    return {"basic": settings.RAZORPAY_PLAN_BASIC, "pro": settings.RAZORPAY_PLAN_PRO}


def plan_for(sub: dict) -> str | None:
    notes = sub.get("notes") or {}
    if isinstance(notes, dict) and notes.get("plan") in ("basic", "pro"):
        return notes["plan"]
    return next((k for k, v in plan_ids().items() if v == sub.get("plan_id")), None)


def _ts(v) -> str:
    if v:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).isoformat()
    return (datetime.now(timezone.utc) + timedelta(days=31)).isoformat()


def create_subscription(profile: dict, plan: str) -> dict:
    sub = client().subscription.create({
        "plan_id": plan_ids()[plan],
        "total_count": 120,          # up to 10 years of monthly renewals; users can cancel any time
        "quantity": 1,
        "customer_notify": 1,
        "notes": {"user_id": profile["id"], "plan": plan},
    })
    db.update_profile(profile["id"], pending_subscription_id=sub["id"])
    return {"subscription_id": sub["id"], "key_id": settings.RAZORPAY_KEY_ID,
            "email": profile.get("email"), "plan": plan}


def activate(profile: dict, sub: dict):
    plan = plan_for(sub)
    if not plan:
        return
    old = profile.get("razorpay_subscription_id")
    if old and old != sub["id"] and profile.get("plan_status") == "active":
        try:  # switching plans: stop billing the old subscription now
            client().subscription.cancel(old, {"cancel_at_cycle_end": 0})
        except Exception as e:
            print("could not cancel old subscription:", e)
    db.update_profile(profile["id"], plan=plan, plan_status="active", razorpay_subscription_id=sub["id"],
                      current_period_end=_ts(sub.get("current_end")), pending_subscription_id=None,
                      cancel_at_period_end=False)


def verify_checkout(profile: dict, payment_id: str, sub_id: str, signature: str):
    client().utility.verify_subscription_payment_signature({
        "razorpay_subscription_id": sub_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature,
    })
    sub = client().subscription.fetch(sub_id)
    if (sub.get("notes") or {}).get("user_id") != profile["id"]:
        raise SignatureVerificationError("Subscription belongs to another user.")
    activate(profile, sub)


def handle_webhook(body: bytes, signature: str):
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
    if not sid:
        raise ValueError("No active subscription.")
    client().subscription.cancel(sid, {"cancel_at_cycle_end": 1})
    db.update_profile(profile["id"], cancel_at_period_end=True)
