"""Razorpay subscriptions: Basic and Pro, monthly or (when those plans are set up) yearly. Prices live in plans.py."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import razorpay
from razorpay.errors import BadRequestError, SignatureVerificationError

from . import db, invite_rewards, invoices, lifecycle, pricing, product_analytics
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
    if sub.get("plan_id") in ids:
        return ids[sub["plan_id"]]
    other = pricing.all_plan_ids().get(sub.get("plan_id"))       # a plan in another currency
    return other[1] if other else None


def _ts(v) -> str:
    if v:
        return datetime.fromtimestamp(int(v), tz=timezone.utc).isoformat()
    return (datetime.now(timezone.utc) + timedelta(days=31)).isoformat()


def _mask(v: str) -> str:
    return f"{v[:9]}…{v[-4:]}" if len(v) > 14 else ("set" if v else "missing")


INTERNATIONAL_WHERE = "Razorpay Dashboard → Account & Settings → International payments"


def international_status(key: str = "", secret: str = "") -> dict:
    """Whether the account takes cards issued outside India, as an info row: Razorpay has no public API that reports
    it. The one call that looked like it would (GET /v1/methods) takes the key ID alone, as checkout does, so with
    the key and secret it is refused (the HTTPStatusError the admin saw), and its answer lists the methods on offer,
    not whether international cards are switched on. So the admin is pointed to the dashboard, without a warning."""
    return {"enabled": None, "info": True,
            "detail": f"Check in {INTERNATIONAL_WHERE}. Razorpay's API doesn't report this setting."}


LAST_WEBHOOK = "billing:last-webhook"       # {"at", "event"}: the last signed event Razorpay delivered


def mode() -> str:
    key = settings.RAZORPAY_KEY_ID or ""
    return "live" if key.startswith("rzp_live_") else "test" if key.startswith("rzp_test_") else "unknown"


def _when(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat(timespec="seconds") if ts else None
    except (TypeError, ValueError, OverflowError):
        return None


def activity(count: int = 50) -> dict:
    """Admin → Money (DJ-016, DJ-017), read from Razorpay and nothing changed: the newest subscriptions, refunds and
    failed payments, the key's mode, when the last webhook arrived, and which currencies have their own plans. Each list
    says its own error when Razorpay didn't answer it."""
    out: dict = {"mode": mode(), "enabled": enabled(), "last_webhook": db.json_value(db.get_setting(LAST_WEBHOOK), {}) or None,
                 "currency_plans": sorted({cur for cur, _, _ in pricing.all_plan_ids().values()}),
                 "subscriptions": [], "refunds": [], "failed": [], "errors": {}}
    if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
        out["errors"]["all"] = "Razorpay's keys aren't set on the server."
        return out
    c = client()
    try:
        subs = (c.subscription.all({"count": count}) or {}).get("items") or []
        out["subscriptions"] = [{"id": x.get("id"), "status": x.get("status"), "plan": plan_for(x), "plan_id": x.get("plan_id"),
                                 "created_at": _when(x.get("created_at")), "current_end": _when(x.get("current_end")),
                                 "paid_count": x.get("paid_count")} for x in subs]
    except Exception as e:
        out["errors"]["subscriptions"] = (str(e) or e.__class__.__name__)[:200]
    try:
        refs = (c.refund.all({"count": count}) or {}).get("items") or []
        out["refunds"] = [{"id": x.get("id"), "payment_id": x.get("payment_id"), "amount": (x.get("amount") or 0) / 100,
                           "currency": x.get("currency") or "INR", "status": x.get("status"), "created_at": _when(x.get("created_at"))}
                          for x in refs]
    except Exception as e:
        out["errors"]["refunds"] = (str(e) or e.__class__.__name__)[:200]
    try:
        pays = (c.payment.all({"count": 100}) or {}).get("items") or []
        out["failed"] = [{"id": x.get("id"), "amount": (x.get("amount") or 0) / 100, "currency": x.get("currency") or "INR",
                          "created_at": _when(x.get("created_at")), "why": x.get("error_description") or x.get("error_reason")}
                         for x in pays if x.get("status") == "failed"][:count]
    except Exception as e:
        out["errors"]["failed"] = (str(e) or e.__class__.__name__)[:200]
    return out


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
    out["international"] = international_status(key, secret)
    currencies = set()
    for label, pid in (("Basic monthly", settings.RAZORPAY_PLAN_BASIC), ("Pro monthly", settings.RAZORPAY_PLAN_PRO),
                       ("Basic yearly", settings.RAZORPAY_PLAN_BASIC_YEAR), ("Pro yearly", settings.RAZORPAY_PLAN_PRO_YEAR)):
        row = {"label": label, "id": pid or None, "ok": False, "detail": "Not set" if not pid else None}
        if pid:
            try:
                p = probe.plan.fetch(pid)
                item = p.get("item") or {}
                currencies.add(item.get("currency") or "INR")
                cur = item.get("currency") or "INR"
                sign = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(cur, cur + " ")
                row.update(ok=True, detail=f"{item.get('name', '')}: {sign}{(item.get('amount') or 0) / 100:,.0f} every "
                                           f"{p.get('interval', 1)} {p.get('period', '')}".strip())
            except Exception as e:
                row["detail"] = f"Razorpay can't find this plan with these keys ({(str(e) or 'error')[:120]})"
        out["plans"].append(row)
    for pid, (cur, plan, period) in sorted(pricing.all_plan_ids().items(), key=lambda kv: kv[1]):
        row = {"label": f"{plan.title()} {'yearly' if period == 'year' else 'monthly'} in {cur}", "id": pid, "ok": False, "detail": None}
        try:
            p = probe.plan.fetch(pid)
            item = p.get("item") or {}
            got = item.get("currency") or "INR"
            currencies.add(got)
            amount = (item.get("amount") or 0) / 100
            shown = (pricing.table().get(cur) or {}).get(plan + ("_year" if period == "year" else ""))
            same = shown is not None and abs(amount - float(shown)) < 0.005
            row.update(ok=got == cur and same, detail=f"{item.get('name', '')}: {got} {amount:,.2f} every "
                                                      f"{p.get('interval', 1)} {p.get('period', '')}".strip()
                       + ("" if got == cur else f". This plan is in {got}, not {cur}: fix it in Admin → Prices.")
                       + ("" if same else f". The Plans page shows {cur} {shown}: fix that price in Admin → Prices to match."))
        except Exception as e:
            row["detail"] = f"Razorpay can't find this plan with these keys ({(str(e) or 'error')[:120]})"
        out["plans"].append(row)
    out["currencies"] = sorted(currencies)
    return out


def create_subscription(profile: dict, plan: str, period: str = "month", currency: str = "INR") -> dict:
    """Subscribe in the visitor's currency when that currency's Razorpay plan is set up, otherwise in rupees
    (international cards are charged the rupee price and converted by the card)."""
    if not enabled():
        raise ValueError("Payments aren't set up on the server yet.")
    own = pricing.plan_id(currency, plan, period)
    if period == "year" and not yearly_enabled() and not own:
        raise ValueError("Yearly billing isn't set up yet; pick monthly.")
    charged = currency if own else "INR"
    plan_id = own or plan_ids(period)[plan]
    # the payment window opened again for the same plan and period: the checkout started before, still unpaid, is used again
    # rather than a new subscription made at Razorpay every time (DP2-042: five made in one sitting). Razorpay lets a
    # subscription that is still "created" be paid until it expires; any other state, or another plan, gets a new one.
    sub = _reusable(profile.get("pending_subscription_id"), plan_id, profile["id"])
    if sub is None:
        sub = client().subscription.create({
            "plan_id": plan_id,
            "total_count": 10 if period == "year" else 120,   # up to 10 years of renewals; users can cancel any time
            "quantity": 1,
            "customer_notify": 1,
            "notes": {"user_id": profile["id"], "plan": plan, "period": period, "currency": charged},
        })
        _drop_unpaid(profile.get("pending_subscription_id"), profile.get("razorpay_subscription_id"))
        db.update_profile(profile["id"], pending_subscription_id=sub["id"])
    return {"subscription_id": sub["id"], "key_id": settings.RAZORPAY_KEY_ID,
            "email": profile.get("email"), "plan": plan, "currency": charged}


def _reusable(sid: str | None, plan_id: str, uid: str) -> dict | None:
    """The user's unpaid checkout `sid` when it is for this Razorpay plan and can still be paid ("created": no payment
    authorised yet), else None. A fetch that fails is no reuse: a new subscription is made, as before."""
    if not sid:
        return None
    try:
        sub = client().subscription.fetch(sid)
    except Exception as e:
        print("razorpay: couldn't read the pending checkout:", str(e)[:160])
        return None
    notes = sub.get("notes") if isinstance(sub.get("notes"), dict) else {}
    if sub.get("status") == "created" and sub.get("plan_id") == plan_id and notes.get("user_id") in (None, uid):
        return sub
    return None


def _drop_unpaid(sid: str | None, current: str | None):
    """Cancel the checkout replaced by a new one (another plan or period), so an abandoned one isn't left open at Razorpay.
    Never the subscription the user pays for now; a failure only leaves it to expire by itself."""
    if not sid or sid == current:
        return
    try:
        if (client().subscription.fetch(sid) or {}).get("status") == "created":
            client().subscription.cancel(sid, {"cancel_at_cycle_end": 0})
    except Exception as e:
        print("razorpay: couldn't cancel the replaced checkout:", str(e)[:160])


def activate(profile: dict, sub: dict):
    plan = plan_for(sub)
    if not plan:
        return
    old = profile.get("razorpay_subscription_id")
    # Save the new subscription first, so the "cancelled" webhook for the old one is ignored
    db.update_profile(profile["id"], plan=plan, plan_status="active", razorpay_subscription_id=sub["id"],
                      current_period_end=_ts(sub.get("current_end")), pending_subscription_id=None,
                      cancel_at_period_end=old == sub["id"] and bool(profile.get("cancel_at_period_end")))
    try:                                   # a subscription now: no longer a plan given by hand
        from . import admin
        admin.mark_granted(profile["id"], False)
    except Exception as e:
        print("could not clear the hand-given mark:", str(e)[:160])
    if old and old != sub["id"] and profile.get("plan_status") == "active":
        try:  # switching plans: stop billing the old subscription now
            client().subscription.cancel(old, {"cancel_at_cycle_end": 0})
        except Exception as e:
            print("could not cancel old subscription:", e)


FINAL = ("refunded", "cancelled", "completed", "expired")     # a subscription in one of these never comes back


def _stale(profile: dict, sub: dict) -> bool:
    """A late or retried event for a subscription that must not change the plan: it has ended, or the user has since
    moved to another active one (and this one isn't the checkout in progress), or a refund ended it."""
    if sub.get("status") in ("cancelled", "completed", "halted", "expired"):
        return True
    cur = profile.get("razorpay_subscription_id")
    if profile.get("plan_status") in FINAL and cur == sub["id"]:
        return True                            # ended for good: a late "activated" or "charged" for it can't bring it back
    return bool(profile.get("plan_status") == "active" and cur and cur != sub["id"]
                and sub["id"] != profile.get("pending_subscription_id"))


PAYMENT_SUB = "payment-sub:"


INVOICE_FAILS = "invoice-fails:"
INVOICE_TRIES = 5          # transient failures for one payment that are raised (and so retried) before giving up


def _transient(e: BaseException) -> bool:
    """A failure that a retry can get past: another server holds the payment's claim, or the database (or the
    network to it) failed to answer a read or a write. Anything else (bad data, a bug) fails the same way every time."""
    import httpx
    kinds: tuple = (invoices.InvoiceBusy, db.SettingConflict, httpx.TransportError, ConnectionError, TimeoutError)
    try:
        from postgrest.exceptions import APIError
        kinds += (APIError,)
    except ImportError:
        pass
    try:
        from psycopg import OperationalError
        kinds += (OperationalError,)
    except ImportError:
        pass
    return isinstance(e, kinds)


def _invoice_failed(payment: dict, profile: dict, e: Exception, why: str) -> None:
    """Tell the site owner a payment was left without an invoice (it has to be issued by hand)."""
    pid = payment.get("id")
    print(f"invoice given up for payment {pid}: {why}:", str(e)[:160])
    try:
        from . import alerts
        alerts.tell_admins(f"StratLab: no invoice for payment {pid}",
                           f"The invoice for payment {pid} (user {profile.get('id')}, {profile.get('email') or 'no email'}) "
                           f"couldn't be made: {why}. The error: {type(e).__name__}: {str(e)[:300]}. The payment went "
                           "through and the plan is set; the invoice needs to be issued by hand.")
    except Exception as x:
        print("invoice alert failed:", str(x)[:160])


def _failures(pid: str) -> int | None:
    """This payment's transient invoice failures so far, this one included; None when they can't be counted."""
    try:
        got = db.update_setting(INVOICE_FAILS + pid[:80], lambda raw: json.dumps(int(db.json_value(raw, 0) or 0) + 1))
        return int(json.loads(got))
    except Exception as x:
        print("invoice failure count failed:", str(x)[:160])
        return None


def invoice_for(profile: dict, sub: dict, payment: dict | None):
    """The payment's invoice. A transient failure to make it (another server holds the payment's claim, or the database
    failed) is raised: the webhook then isn't marked handled, and Razorpay's retry issues it. The rest of the event is
    safe to run again (the plan change sets the same values, the receipt, analytics and invite reward go once per
    payment). After INVOICE_TRIES of them for one payment, or at once for any other failure (one a retry would only
    repeat), it is logged and the site owner alerted instead, and None returned: a failure that never clears must not
    fail the webhook over and over, or Razorpay disables it and every plan update stops. The checkout callback catches
    what is raised, so the plan still switches on there and the webhook issues the invoice."""
    if not payment or not payment.get("id") or payment.get("status") not in (None, "captured", "authorized"):
        return None
    notes = sub.get("notes") or {}
    plan, period = plan_for(sub) or "pro", notes.get("period") or "month"
    try:
        inv = invoices.make(payment, profile, plan, period)
    except Exception as e:
        print("invoice failed:", str(e)[:160])
        if not _transient(e):
            _invoice_failed(payment, profile, e, "an error a retry would repeat")
            return None
        n = _failures(payment["id"])
        if n is not None and n > INVOICE_TRIES:
            _invoice_failed(payment, profile, e, f"it failed {n} times")
            return None
        raise
    try:   # which subscription and user a payment belongs to, for a later refund or chargeback
        db.set_setting(PAYMENT_SUB + payment["id"], json.dumps({"sub": sub.get("id"), "user": profile.get("id")}))
    except Exception as e:
        print("payment mapping failed:", str(e)[:160])
    lifecycle.later(lifecycle.receipt, profile, inv, plan, period)      # once per payment, however often this runs
    try:
        product_analytics.payment_completed(profile, payment, plan, period)   # usage analytics, once per payment
    except Exception as e:
        print("payment analytics failed:", str(e)[:160])
    return inv


def _sig(signature: str) -> str:
    """A signature is hex: anything else (non-ASCII crashes the comparison) is simply a mismatch."""
    if not signature or not signature.isascii():
        raise SignatureVerificationError("Malformed signature.")
    return signature


def verify_checkout(profile: dict, payment_id: str, sub_id: str, signature: str):
    signature = _sig(signature)
    client().utility.verify_subscription_payment_signature({
        "razorpay_subscription_id": sub_id, "razorpay_payment_id": payment_id, "razorpay_signature": signature,
    })
    sub = client().subscription.fetch(sub_id)
    if (sub.get("notes") or {}).get("user_id") != profile["id"]:
        raise SignatureVerificationError("Subscription belongs to another user.")
    if _stale(profile, sub):
        raise SignatureVerificationError("This subscription has ended or was refunded.")     # a replayed checkout gets nothing
    activate(profile, sub)
    try:
        payment = client().payment.fetch(payment_id)
    except Exception as e:
        print("could not fetch the payment for its invoice:", e)
        return
    try:
        invoice_for(profile, sub, payment)
    except Exception:
        pass             # the plan is on; the charged webhook issues the invoice (it is retried until it does)
    invite_rewards.safe_paid(profile, payment)    # an invited friend's first payment (the webhook brings it too)


def handle_webhook(body: bytes, signature: str, event_id: str = ""):
    """Act on a signed Razorpay event. Each event is handled once, by its id and by the hash of its signed body, so a
    captured event replayed later (even under a new, unsigned id header) does nothing."""
    if not settings.RAZORPAY_WEBHOOK_SECRET or not signature:
        # an empty secret would let anyone forge a valid signature
        raise SignatureVerificationError("Webhook secret is not configured.")
    client().utility.verify_webhook_signature(body.decode(errors="replace"), _sig(signature), settings.RAZORPAY_WEBHOOK_SECRET)
    event = json.loads(body)
    try:                                # when Razorpay last reached us, for Admin's Payments row (DJ-017)
        db.set_setting(LAST_WEBHOOK, json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                 "event": str(event.get("event") or "")[:60]}))
    except Exception as e:
        print("could not record the webhook's time:", str(e)[:160])
    # The event id is a header Razorpay doesn't sign, so the signed body's hash is always a key too; either one seen skips it.
    keys = ["rzp-body:" + hashlib.sha256(body).hexdigest()]
    if event_id:
        keys.append(f"rzp-event:{event_id[:80]}")
    claimed = []
    for k in keys:
        if not _claim_mark(k):
            for c in claimed:                  # seen under another key: give back what this delivery just took
                db.update_setting(c, lambda cur: db.REMOVE)
            return
        claimed.append(k)
    try:
        _act(event)
    except Exception:
        for c in claimed:                      # not handled: free the marks so Razorpay's retry of a failed one still runs
            db.update_setting(c, lambda cur: db.REMOVE)
        raise


def _claim_mark(key: str) -> bool:
    """Set a mark only if absent (compare-and-set): False when it was already set, so two deliveries can't both act."""
    won = []

    def claim(cur):
        won.clear()
        if cur:
            return None
        won.append(1)
        return "1"
    db.update_setting(key, claim)
    return bool(won)


REVERSALS = ("refund.created", "refund.processed", "payment.dispute.created", "payment.dispute.lost")


def _entity(event: dict, name: str) -> dict:
    payload = event.get("payload")
    part = payload.get(name) if isinstance(payload, dict) else None
    ent = part.get("entity") if isinstance(part, dict) else None
    return ent if isinstance(ent, dict) else {}


def _reversed_payment(event: dict) -> str | None:
    """The payment a refund or dispute event is about."""
    return (_entity(event, "refund").get("payment_id") or _entity(event, "dispute").get("payment_id")
            or _entity(event, "payment").get("id"))


def _payment_owner(event: dict, payment_id: str) -> tuple[str | None, dict | None]:
    """The subscription a payment paid for and its user's profile: from the saved mapping, else from the payment's invoice."""
    try:
        saved = db.json_value(db.get_setting(PAYMENT_SUB + payment_id), {})
        sub_id, uid = saved.get("sub"), saved.get("user")
        if not sub_id:                          # an older payment, made before the mapping was kept
            inv_id = _entity(event, "payment").get("invoice_id")
            sub_id = (client().invoice.fetch(inv_id) or {}).get("subscription_id") if inv_id else None
        profile = db.profile_by_subscription(sub_id) if sub_id else None       # none when it's no longer their current one
        return sub_id, profile if profile and (not uid or profile["id"] == uid) else None
    except Exception as e:
        print("could not find the subscription of a reversed payment:", str(e)[:160])
        return None, None


def _paid_in_full(event: dict, payment_id: str) -> bool:
    pay = _entity(event, "payment")
    if pay.get("status") == "refunded" or (pay.get("amount") and pay.get("amount_refunded") == pay.get("amount")):
        return True                            # the payment's own state: all of it is back
    amount = _entity(event, "refund").get("amount")
    paid = pay.get("amount")
    if paid is None:
        try:
            paid = client().payment.fetch(payment_id).get("amount")
        except Exception as e:
            print("could not fetch the refunded payment:", str(e)[:160])
    return bool(amount) and amount == paid


def _end_plan(event: dict, payment_id: str):
    """A full refund or a lost chargeback ends the plan, if the payment was for the current subscription."""
    sub_id, profile = _payment_owner(event, payment_id)
    if not sub_id or not profile or profile.get("razorpay_subscription_id") != sub_id or profile.get("plan_status") == "refunded":
        return
    try:
        client().subscription.cancel(sub_id, {"cancel_at_cycle_end": 0})
    except Exception as e:
        print("could not cancel the refunded subscription:", e)
    db.update_profile(profile["id"], plan="free", plan_status="refunded", cancel_at_period_end=False)
    if profile.get("plan") in ("basic", "pro"):
        lifecycle.later(lifecycle.plan_ended, profile, sub_id, profile.get("plan"))


def _confirmed_check(sub: dict) -> dict | None:
    """Razorpay's own copy of a subscription an event names; None when Razorpay doesn't know it. A lookup that fails
    for a network reason is raised, so the webhook isn't marked handled and Razorpay's retry tries again."""
    sid = str(sub.get("id") or "")
    if not sid.startswith("sub_"):
        return None
    try:
        got = client().subscription.fetch(sid)
    except BadRequestError:
        return None                             # no such subscription on this account: a made-up event
    return got if isinstance(got, dict) and got.get("id") == sid else None


_confirmed = _confirmed_check          # what _act calls (tests, which have no Razorpay, stand the event's copy in for it)


def _act(event: dict):
    name = event.get("event", "")
    if name in REVERSALS:                      # these carry no subscription: invite rewards, and a full refund or lost dispute
        pid = _reversed_payment(event)
        full = bool(pid) and name == "refund.processed" and _paid_in_full(event, pid)
        if name.startswith("payment.dispute.") or full:      # a partial (goodwill) refund keeps the invite reward
            invite_rewards.safe_refunded(pid)
        if pid and (name == "payment.dispute.lost" or full):
            _end_plan(event, pid)
        return
    sub = (event.get("payload", {}).get("subscription") or {}).get("entity")
    if not sub:
        return
    # the subscription as Razorpay itself has it, not as the event says: a signed event is trusted only as far as its
    # secret, and Railway's 21 Oct breach may have exposed that secret (a forged "charged" event would switch a plan on)
    sub = _confirmed(sub)
    if not sub:
        return
    profile = db.profile_by_subscription(sub["id"])
    if not profile:
        uid = (sub.get("notes") or {}).get("user_id")
        # find, never make: a late event for a closed account (RC2B-031) must not bring its profile back
        profile = db.find_profile(uid) if uid else None
    if not profile:
        return
    if name in ("subscription.activated", "subscription.charged", "subscription.resumed"):
        if not _stale(profile, sub):
            activate(profile, sub)
        if name == "subscription.charged":      # a real payment still gets its invoice, whatever the plan
            payment = (event.get("payload", {}).get("payment") or {}).get("entity")
            invoice_for(profile, sub, payment)
            invite_rewards.safe_paid(profile, payment)      # an invited friend's first real payment
    elif name in ("subscription.cancelled", "subscription.completed", "subscription.halted", "subscription.paused"):
        # only the current subscription, and never out of a final state: a late "halted" after "cancelled" would
        # otherwise let a later "activated" bring the plan back (a halted one can recover; a new id starts fresh)
        if profile.get("razorpay_subscription_id") == sub["id"] and profile.get("plan_status") not in FINAL:
            db.update_profile(profile["id"], plan="free", plan_status=sub.get("status", "cancelled"),
                              cancel_at_period_end=False)
            if profile.get("plan") in ("basic", "pro"):
                lifecycle.later(lifecycle.plan_ended, profile, sub["id"], profile.get("plan"))


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
