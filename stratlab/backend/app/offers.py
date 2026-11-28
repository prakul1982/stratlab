"""price102 (owner, 28 Nov: "all ok to do"; GTM plan section 3, P1 and P3): the founding-member yearly prices and the student price.

Founding members (P1): Basic ₹4,999 and Pro ₹14,999 a year (the yearly prices are ₹6,999 and ₹19,999) for whoever subscribes before
FOUNDING_UNTIL (31 Dec 2026, 23:59 IST) or before FOUNDING_SEATS (100) paying customers, whichever comes first. The price is a Razorpay
plan of its own, so a founding member's subscription renews at it for as long as it runs (Razorpay charges every renewal on the plan the
subscription was made with); nothing here touches a renewal. Monthly prices don't change.

Students (P3): Basic at ₹2,499 a year, given by hand. A signed-in person sends a request (a college email or a note about their ID);
the owner approves it in Admin → Users, either at the student price (checkout then uses the student plan) or by giving Basic for a year
by hand (admin.set_plan, as Admin's Change plan does), or turns it down.

The three plans are made once, in rupees and yearly, with the app's own Razorpay key (Admin → Prices, "Make the offer plans") or in the
Razorpay dashboard and pasted in Admin; a Railway variable works too (config.RAZORPAY_PLAN_*_FOUNDING/_STUDENT). Until both founding
plans are set, the founding prices are never shown: no page offers a price that checkout couldn't charge."""
import json
import re
import time
from datetime import datetime, timedelta, timezone

from . import db
from .config import settings

IST = timezone(timedelta(hours=5, minutes=30))
FOUNDING_UNTIL = datetime(2026, 12, 31, 23, 59, tzinfo=IST)     # the offer is closed from this instant on
FOUNDING_SEATS = 100                                            # paying customers, the founding members among them
FOUNDING_PRICE = {"basic": 4999, "pro": 14999}                  # rupees a year, GST included like every rupee price (plans.py)
STUDENT_PRICE = {"basic": 2499}

PLANS_KEY = "offer-plans"            # {field: Razorpay plan id}, set in Admin → Prices
CLOSED_KEY = "founding:closed"       # {"at", "why": "seats"}: once the 100th paying customer is counted the offer stays closed
STUDENT_KEY = "student:"             # student:<uid>: the request and the owner's decision
FIELDS = ("founding_basic_year", "founding_pro_year", "student_basic_year")
ENV = {"founding_basic_year": "RAZORPAY_PLAN_BASIC_YEAR_FOUNDING", "founding_pro_year": "RAZORPAY_PLAN_PRO_YEAR_FOUNDING",
       "student_basic_year": "RAZORPAY_PLAN_BASIC_YEAR_STUDENT"}
AMOUNT = {"founding_basic_year": FOUNDING_PRICE["basic"], "founding_pro_year": FOUNDING_PRICE["pro"],
          "student_basic_year": STUDENT_PRICE["basic"]}
LABEL = {"founding_basic_year": "Basic yearly, founding member", "founding_pro_year": "Pro yearly, founding member",
         "student_basic_year": "Basic yearly, student"}
TTL = 60.0
_cache: dict = {"plans": (0.0, None), "paying": (0.0, None)}


class OfferChanged(Exception):
    """The price the page showed (founding, student or the standard one) is not the one checkout would charge now."""


def forget() -> None:
    _cache.update(plans=(0.0, None), paying=(0.0, None), closed=(0.0, None))


# ---------- the Razorpay plans ----------
def plan_ids() -> dict:
    """{field: plan id or None}: Admin's value, else the Railway variable."""
    at, got = _cache["plans"]
    if got is None or time.monotonic() - at > TTL:
        try:
            got = db.json_value(db.get_setting(PLANS_KEY), {}) or {}
        except Exception:
            got = got or {}
        _cache["plans"] = (time.monotonic(), got)
    return {f: (got.get(f) or getattr(settings, ENV[f], "") or None) for f in FIELDS}


def save_plan_ids(changes: dict) -> dict:
    """Store plan IDs from Admin; a blank one clears it (back to the Railway variable, if any)."""
    cur = db.json_value(db.get_setting(PLANS_KEY), {}) or {}
    for f in FIELDS:
        if f not in (changes or {}):
            continue
        v = str(changes[f] or "").strip()
        if v and not re.fullmatch(r"plan_[A-Za-z0-9]{1,35}", v):
            raise ValueError(f"\"{v[:40]}\" doesn't look like a Razorpay plan ID (plan_…).")
        if v:
            cur[f] = v
        else:
            cur.pop(f, None)
    db.set_setting(PLANS_KEY, json.dumps(cur))
    forget()
    return plan_ids()


def all_offer_ids() -> dict[str, tuple[str, str]]:
    """{plan id: (plan, offer)} so a subscription on an offer plan is matched to Basic or Pro (billing.plan_for)."""
    out = {}
    for f, pid in plan_ids().items():
        if pid:
            kind, plan, _ = f.split("_")
            out[pid] = (plan, kind)
    return out


def amount(offer: str | None, plan: str) -> int | None:
    """The yearly rupee price of an offer for a plan, or None."""
    return (FOUNDING_PRICE if offer == "founding" else STUDENT_PRICE if offer == "student" else {}).get(plan)


# ---------- the founding offer ----------
def _paying_ids() -> set[str] | None:
    """Everyone who has paid: each payment's user (billing.PAYMENT_SUB, kept for every payment since invoices began) and each profile on
    a live subscription now (a payment older than that record), less the owner's test accounts. None when it can't be read."""
    from . import admin, billing
    try:
        ids = set()
        for _, raw in db.all_settings_with_prefix(billing.PAYMENT_SUB):
            uid = (db.json_value(raw, {}) or {}).get("user")
            if uid:
                ids.add(str(uid))
        given = admin.granted()
        ids |= {r["id"] for r in admin._paid_profiles() if admin._paying(r, given)}
        tests = admin.recorded_tests()
        return {i for i in ids if i not in tests and not admin.is_stray(i)}
    except Exception as e:
        print("founding offer: couldn't count paying customers:", str(e)[:160])
        return None


def paying_customers() -> int | None:
    """How many people have paid so far (kept a minute); the last count when a read fails, None before any."""
    at, n = _cache["paying"]
    if n is None or time.monotonic() - at > TTL:
        ids = _paying_ids()
        if ids is not None:
            n = len(ids)
        _cache["paying"] = (time.monotonic(), n)
    return n


def closed_why(now: datetime | None = None) -> str | None:
    """Why the founding offer is closed ("date": past FOUNDING_UNTIL; "seats": 100 paying customers reached), or None while it runs.
    Reaching 100 is kept, so a refund later never opens it again."""
    now = now or datetime.now(timezone.utc)
    if now >= FOUNDING_UNTIL:
        return "date"
    at, kept = _cache.get("closed", (0.0, None))
    if kept is None or time.monotonic() - at > TTL:          # read a minute at a time: /me and /pricing ask on every page
        try:
            kept = bool((db.json_value(db.get_setting(CLOSED_KEY), {}) or {}).get("why"))
        except Exception:
            kept = bool(kept)
        _cache["closed"] = (time.monotonic(), kept)
    if kept:
        return "seats"
    n = paying_customers()
    if n is not None and n >= FOUNDING_SEATS:
        try:
            db.set_setting(CLOSED_KEY, json.dumps({"at": now.isoformat(timespec="seconds"), "why": "seats", "count": n}))
            _cache["closed"] = (time.monotonic(), True)
        except Exception as e:
            print("founding offer: couldn't record that it closed:", str(e)[:160])
        return "seats"
    return None


def founding_ready() -> bool:
    ids = plan_ids()
    return bool(ids["founding_basic_year"] and ids["founding_pro_year"])


def founding_open(now: datetime | None = None) -> bool:
    """Founding prices can be bought now: payments are on, both founding plans are set, and the offer hasn't closed."""
    from . import billing
    return billing.enabled() and founding_ready() and closed_why(now) is None


def founding_public(now: datetime | None = None) -> dict | None:
    """What the pages say while the offer runs (plans.offer_state's "founding"): the deadline, the seats, the prices and what they
    replace. How many seats are left is not said (Admin has it)."""
    if not founding_open(now):
        return None
    from .plans import PLANS
    was = {p: PLANS[p]["price_year"] for p in FOUNDING_PRICE}
    return {"open": True, "until": FOUNDING_UNTIL.astimezone(timezone.utc).isoformat(), "seats": FOUNDING_SEATS,
            "prices": dict(FOUNDING_PRICE), "was": was, **founding_words(was)}


def _rupees(v: int) -> str:
    return f"₹{v:,}"           # the prices are under a lakh, where Indian and Western grouping agree


def founding_words(was: dict) -> dict:
    """The offer in words, once, for every page (the landing page's JavaScript budget is too tight to carry them): the deadline, the line
    above the plan cards, a yearly card's note and a lock's yearly price. Facts only."""
    day = f"{FOUNDING_UNTIL.day} {FOUNDING_UNTIL:%b %Y}, 11:59 pm IST"
    seats, p = FOUNDING_SEATS, FOUNDING_PRICE
    return {"deadline": day,
            "line": (f"Founding-member prices for the first {seats} members, until {day}: Basic {_rupees(p['basic'])} a year (was {_rupees(was['basic'])}), "
                     f"Pro {_rupees(p['pro'])} a year (was {_rupees(was['pro'])}). The price stays the same for as long as you renew. Monthly prices don't change."),
            "note": {k: f"Founding-member price for the first {seats} members, until {day}. Renews at {_rupees(p[k])} a year for as long as you keep it."
                     for k in p},
            "year": {k: f"{_rupees(p[k])} a year (founding-member price until {day}, for the first {seats} members; was {_rupees(was[k])})" for k in p}}


# ---------- students ----------
def student_of(uid: str) -> dict | None:
    try:
        row = db.json_value(db.get_setting(STUDENT_KEY + uid), {})
    except Exception:
        return None
    return row or None


def student_public(uid: str) -> dict | None:
    """The person's own request, for /me: its status, and the price their Basic yearly checkout is at once approved at it."""
    row = student_of(uid)
    if not row:
        return None
    priced = row.get("status") == "approved" and row.get("mode") == "price" and bool(plan_ids()["student_basic_year"])
    return {"status": row.get("status"), "mode": row.get("mode"), "at": row.get("at"), "decided_at": row.get("decided_at"),
            "price": STUDENT_PRICE["basic"] if priced else None}


EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}")


def apply(profile: dict, college: str, college_email: str, note: str, now: datetime | None = None) -> dict:
    """A student's request: the college, and a college email or a note about their student ID (one of the two). A pending or approved
    request is not sent again; a refused one can be."""
    college, college_email, note = (college or "").strip()[:120], (college_email or "").strip()[:200], (note or "").strip()[:500]
    if not college:
        raise ValueError("Say which college or university you study at.")
    if college_email and not EMAIL.fullmatch(college_email):
        raise ValueError("That college email doesn't look like an email address.")
    if not college_email and len(note) < 8:
        raise ValueError("Give your college email, or a short note about your student ID (its number and the year it is valid to).")
    have = student_of(profile["id"])
    if have and have.get("status") in ("pending", "approved"):
        raise ValueError("You've already asked; your request is " + ("being looked at." if have["status"] == "pending" else "approved."))
    row = {"uid": profile["id"], "email": profile.get("email"), "college": college, "college_email": college_email, "note": note,
           "at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"), "status": "pending"}
    db.set_setting(STUDENT_KEY + profile["id"], json.dumps(row))
    return row


def requests() -> list[dict]:
    """Every student request, the pending ones first, newest first within each."""
    rows = []
    for _, raw in db.all_settings_with_prefix(STUDENT_KEY):
        row = db.json_value(raw, {})
        if row.get("uid"):
            rows.append(row)
    rows.sort(key=lambda r: r.get("at") or "", reverse=True)
    return sorted(rows, key=lambda r: r.get("status") != "pending")


def decide(uid: str, decision: str, who: str | None = None, now: datetime | None = None) -> dict:
    """The owner's decision: "price" (their Basic yearly checkout is at STUDENT_PRICE; needs the student plan), "grant" (Basic for a
    year now, given by hand: admin.set_plan) or "reject"."""
    row = student_of(uid)
    if not row:
        raise LookupError("No student request from that user.")
    if decision not in ("price", "grant", "reject"):
        raise ValueError("Approve at the student price, give Basic for a year by hand, or turn it down.")
    if decision == "price" and not plan_ids()["student_basic_year"]:
        raise ValueError("The student plan isn't set in Admin → Prices yet: make or paste it there first, or give Basic for a year by hand.")
    if decision == "grant":
        from . import admin
        admin.set_plan(uid, "basic", 365)
    row.update(status="rejected" if decision == "reject" else "approved", mode=None if decision == "reject" else decision,
               decided_at=(now or datetime.now(timezone.utc)).isoformat(timespec="seconds"), decided_by=who)
    db.set_setting(STUDENT_KEY + uid, json.dumps(row))
    return row


# ---------- checkout ----------
def checkout_plan(profile: dict, plan: str, period: str, charged: str, now: datetime | None = None) -> tuple[str | None, str | None]:
    """(offer, Razorpay plan id) for a new subscription, or (None, None) for the standard price. Only yearly and charged in rupees: an
    approved student's Basic first (the lower price), else the founding price while it runs."""
    if period != "year" or charged != "INR":
        return None, None
    ids = plan_ids()
    if plan == "basic" and ids["student_basic_year"]:
        row = student_of(profile["id"]) or {}
        if row.get("status") == "approved" and row.get("mode") == "price":
            return "student", ids["student_basic_year"]
    if founding_open(now):
        return "founding", ids[f"founding_{plan}_year"]
    return None, None


def admin_view(now: datetime | None = None) -> dict:
    """Admin → Prices' offer box and Users' student requests: the plans, the deadline, the count against the 100, and why it is closed."""
    from . import billing
    ids = plan_ids()
    return {"plans": [{"field": f, "label": LABEL[f], "id": ids[f], "amount": AMOUNT[f]} for f in FIELDS],
            "founding": {"until": FOUNDING_UNTIL.astimezone(timezone.utc).isoformat(), "seats": FOUNDING_SEATS, "paying": paying_customers(),
                         "prices": dict(FOUNDING_PRICE), "ready": founding_ready(), "payments": billing.enabled(),
                         "closed": closed_why(now), "open": founding_open(now)},
            "student_price": STUDENT_PRICE["basic"], "students": requests()}
