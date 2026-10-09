"""Net worth: what the user owns minus what they owe, plus a register of their insurance policies.

Stocks come from My Holdings, mutual funds from the mutual fund module when it exists, and everything else is typed in:
EPF, PPF, NPS, fixed and recurring deposits, gold, sovereign gold bonds, cash, property, crypto, other assets, loans and
policies. Each entry's value today is worked out from what was entered (an FD's interest to date, a loan's balance after
the EMIs paid so far) with the rule written next to it.

Stored per user in app_settings (networth:<uid> for the entries, networthlog:<uid> for the monthly history), seen only by
that user, and deleted in one step. Values are never logged. Facts and arithmetic only: no view on what to hold, buy,
insure or repay."""
import csv
import io
import json
import math
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from . import db
from .email_kit import fmt_date as _day, inr as _inr  # the app's own number and date styles

IST = timezone(timedelta(hours=5, minutes=30))
KEY = "networth:"
LOG = "networthlog:"
SKIP = "networthskip:"               # networthskip:<uid> = the month whose snapshot the user removed (no automatic one then)
RUN = "networthrun"                  # the month the last 1st-of-the-month snapshot ran for
MAX_ITEMS = 300                      # entries one user can keep (a safety cap; plans set the real limit)
MAX_LOG = 400                        # snapshots kept

# rates as notified (change here when a new rate is notified); every entry can set its own
EPF_RATE = 8.25                      # declared for FY 2025-26 (and FY 2024-25)
EPF_RATE_NOTE = "8.25%, the EPF rate declared for FY 2025-26"
PPF_RATE = 7.1                       # notified for October-December 2026 (unchanged since April 2020)
PPF_RATE_NOTE = "7.1%, the PPF rate notified for October-December 2026"
SGB_RATE = 2.5                       # fixed for every tranche, on the issue price
SGB_YEARS = 8
PPF_YEARS = 15

ASSET_KINDS = ("epf", "ppf", "nps", "fd", "rd", "gold", "sgb", "cash", "property", "crypto", "other")
KINDS = ASSET_KINDS + ("loan", "policy")
LABEL = {"epf": "EPF", "ppf": "PPF", "nps": "NPS", "fd": "Fixed deposit", "rd": "Recurring deposit", "gold": "Gold",
         "sgb": "Sovereign gold bond", "cash": "Savings and cash", "property": "Property", "crypto": "Crypto", "other": "Other",
         "loan": "Loan", "policy": "Insurance policy"}
# the asset classes the allocation shows, in this order
CLASSES = [("stocks_in", "Indian stocks"), ("stocks_us", "US stocks"), ("mf", "Mutual funds"), ("epf", "EPF"), ("ppf", "PPF"),
           ("nps", "NPS"), ("deposits", "FDs and RDs"), ("gold", "Gold"), ("sgb", "Sovereign gold bonds"),
           ("cash", "Savings and cash"), ("property", "Property"), ("crypto", "Crypto"), ("other", "Other")]
CLASS_OF = {"fd": "deposits", "rd": "deposits"}
COMPOUNDING = {"monthly": 1, "quarterly": 3, "half-yearly": 6, "yearly": 12, "simple": 0}
LOAN_TYPES = {"home": "Home loan", "car": "Car loan", "personal": "Personal loan", "education": "Education loan",
              "credit_card": "Credit card", "other": "Loan"}
POLICY_TYPES = {"term": "Term", "health": "Health", "life": "Life", "vehicle": "Vehicle", "other": "Other"}
FREQUENCY = {"yearly": 12, "half-yearly": 6, "quarterly": 3, "monthly": 1, "single": 0}


# ---------- dates ----------
def today() -> date:
    return datetime.now(IST).date()


def add_months(d: date, n: int) -> date:
    """The same day n months later (the month's last day when it's shorter)."""
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date(y, m, min(d.day, (nxt - timedelta(days=1)).day))


def months_between(a: date, b: date) -> int:
    """Whole months from a to b (0 when b is before a)."""
    if b <= a:
        return 0
    n = (b.year - a.year) * 12 + b.month - a.month
    return n if add_months(a, n) <= b else n - 1


def fy_start(d: date) -> date:
    """1 April of the financial year d is in."""
    return date(d.year if d.month >= 4 else d.year - 1, 4, 1)


def fy_end(d: date) -> date:
    return date(fy_start(d).year + 1, 3, 31)


def fy_label(d: date) -> str:
    y = fy_start(d).year
    return f"FY {y}-{str(y + 1)[2:]}"


def _date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _r(v, dp=2):
    return None if v is None or not math.isfinite(v) else round(v, dp)


# ---------- deposits ----------
def fd_value(principal: float, rate: float, start: date, at: date, compounding: str = "quarterly",
             maturity: date | None = None) -> float:
    """A fixed deposit's value on `at` (at most its maturity date): interest compounds once a period over whole periods
    since the start, and simple interest runs on the days after the last whole period, as banks work it out.
    "simple" is simple interest throughout (short deposits and payouts)."""
    if maturity and at > maturity:
        at = maturity
    if at <= start or principal <= 0:
        return principal
    r = rate / 100
    step = COMPOUNDING.get(compounding, 3)
    if step == 0:
        return principal * (1 + r * (at - start).days / 365)
    k = months_between(start, at) // step
    last = add_months(start, k * step)
    return principal * (1 + r * step / 12) ** k * (1 + r * (at - last).days / 365)


def rd_instalments(start: date, maturity: date) -> int:
    """Monthly instalments in a recurring deposit: one a month from the start, up to the month before maturity."""
    return max(1, months_between(start, maturity))


def rd_value(monthly: float, rate: float, start: date, maturity: date, at: date) -> tuple[float, float]:
    """(value on `at`, amount paid in) for a recurring deposit: each instalment paid so far (one a month from the start)
    grows like a fixed deposit compounded every quarter, until `at` (at most the maturity date)."""
    at = min(at, maturity)
    n = rd_instalments(start, maturity)
    value = paid = 0.0
    for j in range(n):
        d = add_months(start, j)
        if d > at:
            break
        paid += monthly
        value += fd_value(monthly, rate, d, at, "quarterly")
    return value, paid


# ---------- EPF and PPF ----------
def provident(balance: float, rate: float, start: date, end: date, monthly: float = 0.0, yearly: float = 0.0) -> dict:
    """A provident fund balance carried from `start` to `end`. Interest accrues every month at rate/12 on the balance and
    is credited on 31 March; `monthly` is added after each month, `yearly` on each 1 April passed (PPF deposits made by
    the 5th earn that month's interest). Returns {"value": balance with the interest earned so far, "credited": the
    balance with interest credited only, "interest": interest earned in the period, "paid_in": amounts added}."""
    r = rate / 100 / 12
    bal, accrued, interest, paid_in = float(balance), 0.0, 0.0, 0.0
    if end <= start:
        return {"value": bal, "credited": bal, "interest": 0.0, "paid_in": 0.0}
    d = start
    for k in range(1, 12 * 100):
        nxt = add_months(start, k)
        part = 1.0
        if nxt > end:
            span = (nxt - d).days
            part = (end - d).days / span if span else 0.0
        accrued += bal * r * part
        interest += bal * r * part
        if part < 1.0:
            break
        march = date(d.year if d.month <= 3 else d.year + 1, 3, 31)
        if d < march + timedelta(days=1) <= nxt:        # a financial year ended in this month: interest is credited
            bal += accrued
            accrued = 0.0
            april = march + timedelta(days=1)
            if yearly and april < end:
                bal += yearly
                paid_in += yearly
        bal += monthly
        paid_in += monthly
        d = nxt
        if d >= end:
            break
    return {"value": bal + accrued, "credited": bal, "interest": interest, "paid_in": paid_in}


def ppf_maturity(opened: date) -> date:
    """A PPF account matures after 15 whole financial years from the end of the year it was opened in."""
    return date(fy_end(opened).year + PPF_YEARS, 4, 1)


# ---------- loans ----------
def emi(principal: float, rate: float, months: int) -> float:
    """The monthly instalment that repays `principal` over `months` at `rate`% a year (reducing balance)."""
    if months <= 0:
        return 0.0
    r = rate / 100 / 12
    if r == 0:
        return principal / months
    f = (1 + r) ** months
    return principal * r * f / (f - 1)


def balance_after(principal: float, rate: float, payment: float, k: int) -> float:
    """What is still owed after k monthly payments."""
    r = rate / 100 / 12
    if r == 0:
        return max(0.0, principal - payment * k)
    f = (1 + r) ** k
    return max(0.0, principal * f - payment * (f - 1) / r)


def payoff(balance: float, rate: float, payment: float, cap: int = 1200) -> tuple[int, float]:
    """(months, total interest) to repay `balance` with `payment` a month; the last payment is whatever is left."""
    r = rate / 100 / 12
    months, interest = 0, 0.0
    while balance > 0.005 and months < cap:
        i = balance * r
        if payment <= i:                                 # never repaid at this payment
            return cap, math.inf
        interest += i
        balance = balance + i - payment
        months += 1
    return months, interest


def emis_paid(start: date, months: int, at: date) -> int:
    """EMIs paid by `at`: the first falls a month after the loan starts."""
    return min(months, months_between(start, at))


def loan_state(principal: float, rate: float, months: int, start: date, at: date) -> dict:
    """A loan on `at`: its EMI, EMIs paid and left, the balance owed, interest paid this financial year and so far,
    the end date and the interest still to pay."""
    pay = emi(principal, rate, months)
    k = emis_paid(start, months, at)
    r = rate / 100 / 12
    bal, fy_int, all_int = float(principal), 0.0, 0.0
    since = fy_start(at)
    for j in range(1, k + 1):
        i = bal * r
        bal = max(0.0, bal + i - pay)
        all_int += i
        if add_months(start, j) >= since:
            fy_int += i
    left = months - k
    return {"emi": pay, "paid": k, "left": left, "outstanding": bal if left else 0.0, "interest_fy": fy_int,
            "interest_paid": all_int, "interest_left": max(0.0, pay * left - bal) if left else 0.0,
            "next_emi": add_months(start, k + 1).isoformat() if left else None,
            "ends": add_months(start, months).isoformat()}


def prepay(principal: float, rate: float, months: int, start: date, at: date, amount: float) -> dict:
    """What prepaying `amount` now does, two ways: keep the EMI and finish sooner, or keep the end date and pay a
    smaller EMI. Arithmetic on the entered rate only (a lender may charge for prepaying or work it out differently)."""
    s = loan_state(principal, rate, months, start, at)
    bal, left, pay = s["outstanding"], s["left"], s["emi"]
    if not left or bal <= 0:
        return {"outstanding": 0.0, "closes": True, "error": "This loan is already repaid on the dates entered."}
    old_months, old_int = payoff(bal, rate, pay)
    amount = min(amount, bal)
    new_bal = bal - amount
    if new_bal <= 0.005:
        return {"outstanding": bal, "amount": amount, "closes": True, "emi": pay, "months_left": old_months,
                "interest_saved": old_int, "tenure": None, "lower_emi": None}
    t_months, t_int = payoff(new_bal, rate, pay)
    e2 = emi(new_bal, rate, old_months)
    e_months, e_int = payoff(new_bal, rate, e2)
    return {"outstanding": bal, "amount": amount, "closes": False, "emi": pay, "months_left": old_months, "interest_left": old_int,
            "tenure": {"months_left": t_months, "months_saved": old_months - t_months, "interest_saved": old_int - t_int,
                       "ends": add_months(start, s["paid"] + t_months).isoformat()},
            "lower_emi": {"emi": e2, "emi_change": e2 - pay, "interest_saved": old_int - e_int, "months_left": e_months}}


# ---------- policies ----------
def next_due(due: date, frequency: str, at: date) -> date | None:
    """The next premium date on or after `at`: the entered due date, moved on a period at a time once it has passed.
    A single-premium policy has no next date once its date has passed."""
    step = FREQUENCY.get(frequency, 12)
    if due >= at:
        return due
    if step == 0:
        return None
    n = months_between(due, at)
    k = n // step
    d = add_months(due, k * step)
    while d < at:
        k += 1
        d = add_months(due, k * step)
    return d


def yearly_premium(premium: float, frequency: str) -> float:
    step = FREQUENCY.get(frequency, 12)
    return premium * 12 / step if step else 0.0


# ---------- entries: what each kind takes ----------
class ItemReq(BaseModel):
    """One entry. Only the fields its kind uses are kept; the rest are ignored."""
    kind: Literal["epf", "ppf", "nps", "fd", "rd", "gold", "sgb", "cash", "property", "crypto", "other", "loan", "policy"]
    name: str = Field("", max_length=60)
    value: Optional[float] = Field(None, ge=0, le=1e12)
    as_of: Optional[str] = Field(None, max_length=10)
    balance: Optional[float] = Field(None, ge=0, le=1e12)
    monthly: Optional[float] = Field(None, ge=0, le=1e10)
    yearly: Optional[float] = Field(None, ge=0, le=1e10)
    rate: Optional[float] = Field(None, ge=0, le=60)
    opened: Optional[str] = Field(None, max_length=10)
    tier1: Optional[float] = Field(None, ge=0, le=1e12)
    tier2: Optional[float] = Field(None, ge=0, le=1e12)
    principal: Optional[float] = Field(None, ge=0, le=1e12)
    compounding: Optional[Literal["monthly", "quarterly", "half-yearly", "yearly", "simple"]] = None
    start: Optional[str] = Field(None, max_length=10)
    maturity: Optional[str] = Field(None, max_length=10)
    grams: Optional[float] = Field(None, ge=0, le=1e7)
    purity: Optional[int] = Field(None, ge=1, le=24)
    price_per_g: Optional[float] = Field(None, ge=0, le=1e7)
    units: Optional[float] = Field(None, ge=0, le=1e7)
    issue_price: Optional[float] = Field(None, ge=0, le=1e7)
    coin: Optional[str] = Field(None, max_length=10)
    qty: Optional[float] = Field(None, ge=0, le=1e12)
    loan_type: Optional[Literal["home", "car", "personal", "education", "credit_card", "other"]] = None
    tenure_months: Optional[int] = Field(None, ge=0, le=600)
    lender: Optional[str] = Field(None, max_length=60)
    # a floating-rate loan: its benchmark, the spread over it, how often the rate resets, the last reset and the rate
    # on the latest statement (loan_check.py compares that with the benchmark plus the spread)
    benchmark: Optional[Literal["fixed", "repo", "tbill", "mclr", "other"]] = None
    spread: Optional[float] = Field(None, ge=-10, le=30)
    reset_months: Optional[Literal[1, 3, 6, 12]] = None
    last_reset: Optional[str] = Field(None, max_length=10)
    current_rate: Optional[float] = Field(None, ge=0, le=60)
    policy_type: Optional[Literal["term", "health", "life", "vehicle", "other"]] = None
    insurer: Optional[str] = Field(None, max_length=60)
    sum_assured: Optional[float] = Field(None, ge=0, le=1e12)
    premium: Optional[float] = Field(None, ge=0, le=1e10)
    frequency: Optional[Literal["yearly", "half-yearly", "quarterly", "monthly", "single"]] = None
    due: Optional[str] = Field(None, max_length=10)
    nominee: Optional[str] = Field(None, max_length=60)


class PrepayReq(BaseModel):
    id: str = Field(..., min_length=1, max_length=20)
    amount: float = Field(..., gt=0, le=1e12)


# kind: (fields kept, fields required)
FIELDS = {
    "epf": (("balance", "monthly", "rate", "as_of"), ("balance",)),
    "ppf": (("balance", "yearly", "rate", "as_of", "opened"), ("balance",)),
    "nps": (("tier1", "tier2", "as_of"), ("tier1",)),
    "fd": (("principal", "rate", "compounding", "start", "maturity"), ("principal", "rate", "start", "maturity")),
    "rd": (("monthly", "rate", "start", "maturity"), ("monthly", "rate", "start", "maturity")),
    "gold": (("grams", "purity", "price_per_g", "value", "as_of"), ()),
    "sgb": (("units", "issue_price", "start", "maturity", "price_per_g"), ("units",)),
    "cash": (("value", "as_of"), ("value",)),
    "property": (("value", "as_of"), ("value",)),
    "crypto": (("coin", "qty", "value", "as_of"), ()),
    "other": (("value", "as_of"), ("value",)),
    "loan": (("loan_type", "lender", "principal", "rate", "tenure_months", "start", "benchmark", "spread", "reset_months", "last_reset",
              "current_rate"), ("principal", "rate")),
    "policy": (("policy_type", "insurer", "sum_assured", "premium", "frequency", "due", "nominee"), ("insurer", "premium")),
}
DATES = ("as_of", "opened", "start", "maturity", "due", "last_reset")
WORDS = {"balance": "the balance", "tier1": "the Tier I value", "principal": "the amount", "rate": "the interest rate",
         "start": "the start date", "maturity": "the maturity date", "monthly": "the monthly amount", "units": "the units",
         "value": "the value", "insurer": "the insurer", "premium": "the premium"}


class EntryError(ValueError):
    pass


def clean(req: ItemReq, now: date | None = None) -> dict:
    """The entry to store: only its kind's fields, dates checked, defaults filled. Raises EntryError with a plain message."""
    now = now or today()
    keep, required = FIELDS[req.kind]
    raw = req.model_dump()
    out = {"kind": req.kind, "name": " ".join((req.name or "").split())[:60]}
    for f in keep:
        v = raw.get(f)
        if isinstance(v, str):
            v = " ".join(v.split()) or None
        if isinstance(v, float) and not math.isfinite(v):
            v = None
        if f in DATES and v is not None:
            d = _date(v)
            if not d or not date(1950, 1, 1) <= d <= date(2150, 12, 31):
                raise EntryError(f"{f.replace('_', ' ').capitalize()} isn't a date. Use the date picker.")
            v = d.isoformat()
        if v is not None:
            out[f] = v
    missing = [WORDS.get(f, f) for f in required if out.get(f) in (None, "")]
    if missing:
        raise EntryError(f"{LABEL[req.kind]}: enter {' and '.join(missing)}.")
    k = req.kind
    if k in ("epf", "ppf", "nps", "cash", "property", "other", "gold", "crypto"):
        out.setdefault("as_of", now.isoformat())
    if k == "epf":
        out.setdefault("rate", EPF_RATE)
    if k == "ppf":
        out.setdefault("rate", PPF_RATE)
    if k in ("fd", "rd") and out["maturity"] <= out["start"]:
        raise EntryError("The maturity date has to be after the start date.")
    if k == "fd":
        out.setdefault("compounding", "quarterly")
    if k == "gold":
        if out.get("grams") is None and out.get("value") is None:
            raise EntryError("Gold: enter the grams, or its value.")
        out.setdefault("purity", 24)
    if k == "sgb":
        if out.get("start") and not out.get("maturity"):
            out["maturity"] = add_months(date.fromisoformat(out["start"]), 12 * SGB_YEARS).isoformat()
    if k == "crypto":
        if out.get("coin"):
            out["coin"] = "".join(c for c in out["coin"].upper() if c.isalnum())[:10] or None
            if not out["coin"]:
                out.pop("coin")
        if not ((out.get("coin") and out.get("qty")) or out.get("value") is not None):
            raise EntryError("Crypto: enter the coin and quantity, or its value.")
    if k == "loan":
        out.setdefault("loan_type", "other")
        if out.get("benchmark") in (None, "fixed"):
            for f in ("spread", "reset_months", "last_reset"):
                out.pop(f, None)
        else:
            out.setdefault("reset_months", 12 if out["benchmark"] == "mclr" else 3)
            if out.get("last_reset") and out.get("start") and out["last_reset"] < out["start"]:
                raise EntryError("Loan: the last reset can't be before the loan started.")
        if out.get("tenure_months"):
            if not out.get("start"):
                raise EntryError("Loan: enter the start date, so the EMIs paid so far can be counted.")
            if payoff(out["principal"], out["rate"], emi(out["principal"], out["rate"], out["tenure_months"]))[1] == math.inf:
                raise EntryError("Loan: those numbers never repay the loan.")
    if k == "policy":
        out.setdefault("policy_type", "other")
        out.setdefault("frequency", "yearly")
    return out


# ---------- storage ----------
def load(uid: str) -> dict:
    """{"items": [...], "updated_at"}; empty when the user has none (or the row is damaged)."""
    got = db.json_value(db.get_setting(KEY + uid), {})
    items = [i for i in got.get("items") or [] if isinstance(i, dict) and i.get("kind") in KINDS and i.get("id")]
    return {"items": items, "updated_at": got.get("updated_at")}


def save(uid: str, items: list[dict]):
    if not items:
        db.delete_setting(KEY + uid)
        return
    db.set_setting(KEY + uid, json.dumps({"items": items, "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))


def history(uid: str) -> list[dict]:
    return [h for h in db.json_value(db.get_setting(LOG + uid), []) if isinstance(h, dict) and h.get("d")]


def record(uid: str, totals: dict, why: str, day: date | None = None) -> list[dict]:
    """Add a snapshot of the totals (one a day: a later one the same day replaces it)."""
    d = (day or today()).isoformat()
    rows = [h for h in history(uid) if h["d"] != d]
    snap = {"d": d, "net": _r(totals["net"]), "assets": _r(totals["assets"]), "liabilities": _r(totals["liabilities"]), "why": why}
    rows = sorted(rows + [snap], key=lambda h: h["d"])[-MAX_LOG:]
    db.set_setting(LOG + uid, json.dumps(rows))
    return rows


def drop_snapshot(uid: str, day: str) -> list[dict] | None:
    """Remove one day's snapshot from the history (R7O-013: a test's holdings left a snapshot the owner could only
    clear by deleting everything). None when there was none that day; else the history left."""
    rows = history(uid)
    left = [h for h in rows if h["d"] != day]
    if len(left) == len(rows):
        return None
    if day[:7] == today().strftime("%Y-%m"):
        # this month's snapshot taken out on purpose: the next visit doesn't take the monthly one again at once
        db.set_setting(SKIP + uid, day[:7])
    if left:
        db.set_setting(LOG + uid, json.dumps(left))
    else:
        db.delete_setting(LOG + uid)
    return left


def delete(uid: str):
    """Delete my net worth data: every entry and the history."""
    db.delete_setting(KEY + uid)
    db.delete_setting(LOG + uid)
    db.delete_setting(SKIP + uid)


# ---------- valuing ----------
class Prices:
    """Market prices the page uses when it can; each returns None when it has none. gold() is rupees a gram of 24 carat
    gold with the time it was read; crypto(coin) is dollars a coin; usd_inr() rupees a dollar."""

    def __init__(self, gold: Callable[[], tuple[float, str] | None] = lambda: None,
                 crypto: Callable[[str], float | None] = lambda c: None, usd_inr: Callable[[], float | None] = lambda: None):
        self.gold, self.crypto, self.usd_inr = gold, crypto, usd_inr


def _asset(i: dict, at: date, now_iso: str, gold, crypto, usd_inr) -> dict:
    """One typed-in asset today: value, how it was worked out, the date it's as of, and dates and figures to show."""
    k = i["kind"]
    row = {"id": i["id"], "kind": k, "label": LABEL[k], "name": i.get("name") or LABEL[k], "class": CLASS_OF.get(k, k),
           "value": None, "as_of": at.isoformat(), "basis": "calculated", "rule": "", "facts": {}, "entry": i}
    if k == "epf":
        since = _date(i.get("as_of")) or at
        rate = i.get("rate", EPF_RATE)
        now_v = provident(i["balance"], rate, since, at, monthly=i.get("monthly") or 0)
        year = provident(i["balance"], rate, since, fy_end(at) + timedelta(days=1), monthly=i.get("monthly") or 0) if since <= fy_end(at) else None
        row.update(value=now_v["value"], rule=(f"Balance of {_day(since)}, plus {'the monthly contribution and ' if i.get('monthly') else ''}"
                                               f"interest at {rate:g}% a year, worked out monthly and credited on 31 March"
                                               + (f" ({EPF_RATE_NOTE})" if rate == EPF_RATE else "")))
        row["facts"] = {"interest_so_far": _r(now_v["interest"]), "year_end": _r(year["value"]) if year else None,
                        "year_end_label": f"31 Mar {fy_end(at).year}", "rate": rate}
    elif k == "ppf":
        since = _date(i.get("as_of")) or at
        rate = i.get("rate", PPF_RATE)
        now_v = provident(i["balance"], rate, since, at)
        opened = _date(i.get("opened"))
        row.update(value=now_v["value"], rule=f"Balance of {_day(since)}, plus interest at {rate:g}% a year, worked out monthly and "
                                               "credited on 31 March" + (f" ({PPF_RATE_NOTE})" if rate == PPF_RATE else ""))
        facts = {"interest_so_far": _r(now_v["interest"]), "rate": rate, "maturity": None, "maturity_value": None}
        if opened:
            m = ppf_maturity(opened)
            facts["maturity"] = m.isoformat()
            if m > at:
                proj = provident(i["balance"], rate, since, m, yearly=i.get("yearly") or 0)
                facts["maturity_value"] = _r(proj["value"])
                facts["maturity_rule"] = (f"If the rate stays {rate:g}%" + (f" and {_inr(i['yearly'])} goes in by 5 April each year" if i.get("yearly") else "")
                                          + "; the rate is reset every quarter.")
        row["facts"] = facts
    elif k == "nps":
        row.update(value=(i.get("tier1") or 0) + (i.get("tier2") or 0), basis="as entered", as_of=i.get("as_of") or at.isoformat(),
                   rule="Tier I and Tier II values as entered")
        row["facts"] = {"tier1": i.get("tier1"), "tier2": i.get("tier2")}
    elif k == "fd":
        start, mat = date.fromisoformat(i["start"]), date.fromisoformat(i["maturity"])
        comp = i.get("compounding", "quarterly")
        v = fd_value(i["principal"], i["rate"], start, at, comp, mat)
        m = fd_value(i["principal"], i["rate"], start, mat, comp, mat)
        how = "simple interest" if comp == "simple" else f"compounded {comp}"
        row.update(value=v, as_of=min(at, mat).isoformat(), rule=f"{_inr(i['principal'])} at {i['rate']:g}% a year, {how}, from {_day(start)}"
                                                                 + ("; matured" if at >= mat else ""))
        row["facts"] = {"interest_so_far": _r(v - i["principal"]), "maturity": mat.isoformat(), "maturity_value": _r(m),
                        "matured": at >= mat}
    elif k == "rd":
        start, mat = date.fromisoformat(i["start"]), date.fromisoformat(i["maturity"])
        v, paid = rd_value(i["monthly"], i["rate"], start, mat, at)
        m, total = rd_value(i["monthly"], i["rate"], start, mat, mat)
        row.update(value=v, as_of=min(at, mat).isoformat(), rule=f"{_inr(i['monthly'])} a month from {_day(start)}, each instalment at "
                                                                 f"{i['rate']:g}% a year compounded quarterly")
        row["facts"] = {"paid_in": _r(paid), "instalments": rd_instalments(start, mat), "maturity": mat.isoformat(),
                        "maturity_value": _r(m), "matured": at >= mat, "total_in": _r(total)}
    elif k == "gold":
        purity = i.get("purity", 24)
        g = gold if i.get("price_per_g") is None else None
        if i.get("grams") is not None and (i.get("price_per_g") is not None or g):
            per = i["price_per_g"] if i.get("price_per_g") is not None else g[0] * purity / 24
            row.update(value=i["grams"] * per, basis="your price" if i.get("price_per_g") is not None else "market price",
                       as_of=i.get("as_of") if i.get("price_per_g") is not None else g[1],
                       rule=(f"{i['grams']:g} g × {_inr(per)} a gram" + ("" if i.get("price_per_g") is not None else
                             f" ({purity} carat: the reference 24 carat price × {purity}/24, before making charges and GST)")))
        else:
            row.update(value=i.get("value"), basis="as entered", as_of=i.get("as_of"), rule="Value as entered"
                       + ("; no gold price is available right now" if i.get("grams") is not None else ""))
        row["facts"] = {"grams": i.get("grams"), "purity": purity}
    elif k == "sgb":
        units = i["units"]
        if i.get("price_per_g") is not None:
            row.update(value=units * i["price_per_g"], basis="your price", rule=f"{units:g} units × {_inr(i['price_per_g'])} a gram (your price)")
        elif gold:
            row.update(value=units * gold[0], basis="market price", as_of=gold[1],
                       rule=f"{units:g} units × {_inr(gold[0])} a gram (reference 24 carat price; one unit is one gram)")
        elif i.get("issue_price"):
            row.update(value=units * i["issue_price"], basis="issue price", rule=f"{units:g} units × the issue price (no gold price right now)")
        facts = {"units": units, "rate": SGB_RATE, "yearly_interest": _r(units * i["issue_price"] * SGB_RATE / 100) if i.get("issue_price") else None,
                 "maturity": i.get("maturity"), "next_interest": None}
        start = _date(i.get("start"))
        if start:
            nxt = next_due(start, "half-yearly", at + timedelta(days=1)) if start <= at else add_months(start, 6)
            mat = _date(i.get("maturity"))
            facts["next_interest"] = nxt.isoformat() if nxt and (not mat or nxt <= mat) else None
        row["facts"] = facts
    elif k == "crypto":
        usd = crypto(i["coin"]) if i.get("coin") and i.get("qty") else None
        fx = usd_inr() if usd else None
        if usd and fx:
            row.update(value=i["qty"] * usd * fx, basis="market price", as_of=now_iso,
                       rule=f"{i['qty']:g} {i['coin']} × ${usd:,.2f} × {_inr(fx, 2)} a dollar")
        else:
            row.update(value=i.get("value"), basis="as entered", as_of=i.get("as_of"),
                       rule="Value as entered" + ("; no price for this coin right now" if i.get("coin") else ""))
        row["facts"] = {"coin": i.get("coin"), "qty": i.get("qty")}
    else:                                                   # cash, property, other
        row.update(value=i["value"], basis="as entered", as_of=i.get("as_of"), rule="Value as entered")
    row["value"] = _r(row["value"]) if row["value"] is not None else None
    return row


def _loan(i: dict, at: date) -> dict:
    t = LOAN_TYPES.get(i.get("loan_type", "other"), "Loan")
    row = {"id": i["id"], "kind": "loan", "label": t, "name": i.get("name") or (f"{t}, {i['lender']}" if i.get("lender") else t),
           "value": None, "as_of": at.isoformat(), "basis": "calculated", "rule": "", "facts": {}, "entry": i}
    start = _date(i.get("start"))
    if i.get("tenure_months") and start:
        s = loan_state(i["principal"], i["rate"], i["tenure_months"], start, at)
        row.update(value=_r(s["outstanding"]), rule=f"{_inr(i['principal'])} at {i['rate']:g}% a year over {i['tenure_months']} months from "
                                                     f"{_day(start)}, with the first EMI a month later")
        row["facts"] = {k: (_r(v) if isinstance(v, float) else v) for k, v in s.items()} | {"fy": fy_label(at)}
    else:
        row.update(value=_r(i["principal"]), basis="as entered", rule="Amount owed as entered")
    return row


def _policy(i: dict, at: date) -> dict:
    due = _date(i.get("due"))
    nxt = next_due(due, i.get("frequency", "yearly"), at) if due else None
    return {"id": i["id"], "kind": "policy", "label": POLICY_TYPES.get(i.get("policy_type", "other"), "Other"),
            "name": i.get("name") or f"{POLICY_TYPES.get(i.get('policy_type', 'other'), 'Other')} policy, {i['insurer']}",
            "insurer": i["insurer"], "sum_assured": i.get("sum_assured"), "premium": i["premium"], "frequency": i.get("frequency", "yearly"),
            "yearly_premium": _r(yearly_premium(i["premium"], i.get("frequency", "yearly"))), "next_due": nxt.isoformat() if nxt else None,
            "due_in": (nxt - at).days if nxt else None, "nominee": i.get("nominee"), "entry": i}


def data_day(rows: list[dict], at: date) -> date:
    """The day the market prices in the page are from (India's calendar): the latest of their stamps, never after `at`.
    Out of hours that is the last close, not the day it is now. A page with no market-priced row is as of `at`."""
    days = []
    for r in rows:
        if r.get("basis") != "market price" or not r.get("as_of"):
            continue
        try:
            raw = str(r["as_of"])
            t = datetime.fromisoformat(raw) if "T" in raw and len(raw) > 10 else None
            d = (t.replace(tzinfo=t.tzinfo or IST).astimezone(IST).date()) if t else _date(raw)
        except ValueError:
            d = None
        if d:
            days.append(d)
    return min(max(days), at) if days else at


def build(items: list[dict], stocks: dict | None, mf: dict | None, prices: Prices, at: date | None = None) -> dict:
    """The whole page: totals, the allocation by asset class, every asset and loan with its value and as-of date, and the
    insurance register (kept apart: policies aren't counted in net worth). `stocks` is {"in", "us", "as_of", "count"} in
    rupees from My Holdings; `mf` is {"value", "as_of"} from the mutual fund module (or None)."""
    at = at or today()
    now_iso = datetime.now(timezone.utc).isoformat(timespec="minutes")
    gold_cache: dict = {}

    def gold():
        if "v" not in gold_cache:
            try:
                gold_cache["v"] = prices.gold()
            except Exception:
                gold_cache["v"] = None
        return gold_cache["v"]

    def crypto(c):
        try:
            return prices.crypto(c)
        except Exception:
            return None

    def fx():
        try:
            return prices.usd_inr()
        except Exception:
            return None
    needs_gold = any(i["kind"] in ("gold", "sgb") and i.get("price_per_g") is None for i in items)
    g = gold() if needs_gold else None
    assets, loans, policies = [], [], []
    for i in items:
        try:
            if i["kind"] == "loan":
                loans.append(_loan(i, at))
            elif i["kind"] == "policy":
                policies.append(_policy(i, at))
            else:
                assets.append(_asset(i, at, now_iso, g, crypto, fx))
        except (KeyError, TypeError, ValueError, OverflowError):
            continue                                        # a damaged entry is left out, never breaks the page
    linked = []
    if stocks and stocks.get("count"):
        if stocks.get("in"):
            linked.append({"id": "stocks_in", "kind": "stocks_in", "label": "Indian stocks", "name": "My Holdings: Indian stocks", "class": "stocks_in",
                           "value": _r(stocks["in"]), "as_of": stocks.get("as_of"), "basis": "market price", "rule": "From My Holdings, at today's prices",
                           "facts": {}, "linked": "/holdings"})
        if stocks.get("us"):
            linked.append({"id": "stocks_us", "kind": "stocks_us", "label": "US stocks", "name": "My Holdings: US stocks", "class": "stocks_us",
                           "value": _r(stocks["us"]), "as_of": stocks.get("as_of"), "basis": "market price",
                           "rule": "From My Holdings, at today's prices in rupees"
                                   + (f", at ₹{stocks['usd_inr']:.2f} a dollar" if stocks.get("usd_inr") else ""),
                           "facts": {}, "linked": "/holdings"})
    if mf and mf.get("value"):
        linked.append({"id": "mf", "kind": "mf", "label": "Mutual funds", "name": "Mutual funds", "class": "mf", "value": _r(mf["value"]),
                       "as_of": mf.get("as_of"), "basis": "market price", "rule": "From your mutual fund statement, at the latest NAV",
                       "facts": {}, "linked": mf.get("link")})
    rows = linked + assets
    total_assets = sum(r["value"] or 0 for r in rows)
    total_loans = sum(r["value"] or 0 for r in loans)
    by: dict[str, float] = {}
    for r in rows:
        by[r["class"]] = by.get(r["class"], 0) + (r["value"] or 0)
    allocation = [{"class": c, "label": label, "value": _r(by[c]), "pct": _r(by[c] / total_assets * 100, 1) if total_assets else None}
                  for c, label in CLASSES if by.get(c)]
    dated = [r["as_of"] for r in rows + loans if r.get("as_of")]
    upcoming_due = sorted((p for p in policies if p["due_in"] is not None), key=lambda p: p["due_in"])
    return {"as_of": data_day(rows, at).isoformat(), "computed_at": now_iso,
            "totals": {"assets": _r(total_assets), "liabilities": _r(total_loans), "net": _r(total_assets - total_loans),
                       "oldest_as_of": min(dated) if dated else None},
            "allocation": allocation, "assets": rows, "liabilities": loans,
            "insurance": {"policies": policies, "yearly_premium": _r(sum(p["yearly_premium"] or 0 for p in policies)),
                          "cover": {t: _r(sum(p["sum_assured"] or 0 for p in policies if p["entry"].get("policy_type") == t))
                                    for t in POLICY_TYPES if any(p["entry"].get("policy_type") == t for p in policies)},
                          "next": upcoming_due[0]["next_due"] if upcoming_due else None},
            "gold_price": {"per_g": _r(g[0]), "as_of": g[1]} if g else None,
            "rates": {"epf": EPF_RATE, "epf_note": EPF_RATE_NOTE, "ppf": PPF_RATE, "ppf_note": PPF_RATE_NOTE, "sgb": SGB_RATE}}


# ---------- the money calendar ----------
def upcoming_dates(uid: str, days: int = 60, at: date | None = None) -> list[dict]:
    """This module's dates in the next `days` days, soonest first, for the money calendar: deposit, PPF and SGB
    maturities, SGB interest dates, premium due dates and EMI dates. Each is {"date", "kind", "title", "detail",
    "amount", "url"}; amounts are what the user entered or the arithmetic on it."""
    at = at or today()
    end = at + timedelta(days=max(0, min(int(days), 3660)))
    out = []

    def add(d: date | None, kind: str, title: str, detail: str, amount=None):
        if d and at <= d <= end:
            out.append({"date": d.isoformat(), "kind": kind, "title": title, "detail": detail,
                        "amount": _r(amount) if amount is not None else None, "url": "/money/net-worth"})
    for i in load(uid)["items"]:
        try:
            k, name = i["kind"], i.get("name") or LABEL[i["kind"]]
            if k == "fd":
                mat = date.fromisoformat(i["maturity"])
                add(mat, "fd_maturity", f"{name} matures", "Fixed deposit maturity",
                    fd_value(i["principal"], i["rate"], date.fromisoformat(i["start"]), mat, i.get("compounding", "quarterly"), mat))
            elif k == "rd":
                s, mat = date.fromisoformat(i["start"]), date.fromisoformat(i["maturity"])
                add(mat, "rd_maturity", f"{name} matures", "Recurring deposit maturity", rd_value(i["monthly"], i["rate"], s, mat, mat)[0])
            elif k == "ppf" and _date(i.get("opened")):
                add(ppf_maturity(date.fromisoformat(i["opened"])), "ppf_maturity", f"{name} matures", "PPF: 15 financial years complete")
            elif k == "sgb":
                s, mat = _date(i.get("start")), _date(i.get("maturity"))
                add(mat, "sgb_maturity", f"{name} matures", "Sovereign gold bond maturity")
                if s:
                    d = next_due(s, "half-yearly", at)
                    while d and d <= end and (not mat or d <= mat):
                        add(d, "sgb_interest", f"{name}: interest date", f"{SGB_RATE:g}% a year on the issue price, paid every six months",
                            i["units"] * i["issue_price"] * SGB_RATE / 200 if i.get("issue_price") else None)
                        d = add_months(d, 6)
            elif k == "policy" and _date(i.get("due")):
                d = next_due(date.fromisoformat(i["due"]), i.get("frequency", "yearly"), at)
                step = FREQUENCY.get(i.get("frequency", "yearly"), 12)
                while d and d <= end:
                    add(d, "premium", f"{name or i['insurer']}: premium due", f"{POLICY_TYPES.get(i.get('policy_type', 'other'))} policy, {i['insurer']}",
                        i["premium"])
                    d = add_months(d, step) if step else None
            elif k == "loan" and i.get("tenure_months") and _date(i.get("start")):
                s = date.fromisoformat(i["start"])
                pay = emi(i["principal"], i["rate"], i["tenure_months"])
                label = name if i.get("name") else LOAN_TYPES.get(i.get("loan_type", "other"), "Loan")
                for j in range(emis_paid(s, i["tenure_months"], at - timedelta(days=1)) + 1, i["tenure_months"] + 1):
                    d = add_months(s, j)
                    if d > end:
                        break
                    add(d, "emi", f"{label}: EMI", f"EMI {j} of {i['tenure_months']}", pay)
                if i.get("benchmark") not in (None, "fixed") and i.get("reset_months"):
                    anchor = _date(i.get("last_reset")) or s
                    step, n = int(i["reset_months"]), 1
                    d = add_months(anchor, step)
                    while d < at:
                        n += 1
                        d = add_months(anchor, step * n)
                    while d <= end and d <= add_months(s, i["tenure_months"]):
                        add(d, "loan_reset", f"{label}: rate reset", "The floating rate resets to its benchmark on this date; check the "
                            "new rate on your statement")
                        n += 1
                        d = add_months(anchor, step * n)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return sorted(out, key=lambda x: (x["date"], x["title"]))


# ---------- mutual funds (another module, when it exists) ----------
def mf_value(uid: str) -> dict:
    """{"value", "as_of", "link"} of the user's mutual funds from app/money_mf.py when that module is there; a value of 0
    when it isn't, or has nothing for this user. It may offer net_worth_value(uid) or total_value(uid), returning a
    number or {"value", "as_of"}."""
    try:
        from . import money_mf                              # type: ignore[attr-defined]
    except Exception:
        return {"value": 0, "as_of": None, "link": None}
    fn = getattr(money_mf, "net_worth_value", None) or getattr(money_mf, "total_value", None)
    try:
        got = fn(uid) if fn else 0
    except Exception as e:
        print("net worth: mutual funds unavailable:", type(e).__name__)
        got = 0
    if isinstance(got, dict):
        v = got.get("value")
        return {"value": float(v) if isinstance(v, (int, float)) and math.isfinite(v) else 0, "as_of": got.get("as_of"),
                "link": got.get("link") or "/money/mutual-funds"}
    return {"value": float(got) if isinstance(got, (int, float)) and math.isfinite(got) else 0, "as_of": None, "link": "/money/mutual-funds"}


# ---------- the CSV export ----------
def _cell(v):
    """A text cell that a spreadsheet won't run as a formula (a name or note starting with = + - @ is typed text)."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") and not v[1:2].isdigit():
        return "'" + v
    return v


def to_csv(view: dict, hist: list[dict] | None) -> str:
    """Every number on the page, one row each, with its as-of date and how it was worked out."""
    buf = io.StringIO()
    w = csv.writer(buf)

    def put(row):                                                      # every row, whatever the section
        w.writerow([_cell(x) for x in row])
    put(["Section", "Type", "Name", "Value (INR)", "As of", "How it's worked out", "Details"])

    def details(r):
        return "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in (r.get("facts") or {}).items() if v not in (None, "", {}))
    for r in view["assets"]:
        put(["Asset", r["label"], r["name"], r["value"], r.get("as_of") or "", r.get("rule") or "", details(r)])
    for r in view["liabilities"]:
        put(["Liability", r["label"], r["name"], r["value"], r.get("as_of") or "", r.get("rule") or "", details(r)])
    t = view["totals"]
    for label, v in (("Total assets", t["assets"]), ("Total liabilities", t["liabilities"]), ("Net worth", t["net"])):
        put(["Total", label, "", v, view["as_of"], "", ""])
    for a in view["allocation"]:
        put(["Allocation", a["label"], "", a["value"], view["as_of"], "", f"{a['pct']}% of assets" if a["pct"] is not None else ""])
    for p in view["insurance"]["policies"]:
        put(["Insurance", p["label"], p["name"], p["premium"], view["as_of"], f"Premium, {p['frequency']}",
                    "; ".join(x for x in (f"insurer: {p['insurer']}", f"sum assured: {p['sum_assured']}" if p["sum_assured"] is not None else "",
                                          f"next due: {p['next_due']}" if p["next_due"] else "", f"yearly premium: {p['yearly_premium']}",
                                          f"nominee: {p['nominee']}" if p["nominee"] else "") if x)])
    for h in hist or []:
        put(["History", "Net worth", h.get("why") or "", h.get("net"), h["d"], "", f"assets: {h.get('assets')}; liabilities: {h.get('liabilities')}"])
    return buf.getvalue()


# ---------- the 1st-of-the-month snapshot ----------
class Job:
    """Checks every half hour; on the 1st of each month (India time, after 4 pm, so stock prices are the day's close) it
    records every user's net worth once. The month is marked in the database first, so a restart never records twice."""

    def __init__(self, value_of: Callable[[str], dict | None]):
        self.value_of = value_of
        self.status = {"last_run": None, "recorded": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="net-worth-snapshots").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("net worth snapshots:", type(e).__name__)
            time.sleep(1800)

    def tick(self, now: datetime) -> int:
        local = now.astimezone(IST)
        month = local.strftime("%Y-%m")
        if local.day != 1 or local.hour < 16 or db.get_setting(RUN) == month:
            return 0
        db.set_setting(RUN, month)
        n = 0
        for key, _ in db.all_settings_with_prefix(KEY):
            uid = key[len(KEY):]
            try:
                v = self.value_of(uid)
                if v:
                    record(uid, v["totals"], "month", local.date())
                    n += 1
            except Exception as e:                          # one user's data never stops the others'
                print("net worth snapshot failed:", type(e).__name__)
        self.status.update(last_run=now.isoformat(), recorded=n, last_error=None)
        return n


# ---------- routes ----------
POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="networth")


def deposit_tax(profile) -> dict | None:
    """What the fixed and recurring deposits' interest comes to after tax; None when it can't be worked out."""
    try:
        from . import fixed_income        # imports this module, so not at the top
        return fixed_income.networth_deposits(profile)
    except Exception as e:
        print("net worth: deposit tax unavailable:", type(e).__name__)
        return None


def make_router(current_profile, stocks_of: Callable[[dict], dict | None], prices: Prices,
                item_limit: Callable[[str], int | None], has_history: Callable[[str], bool], throttle: Callable) -> APIRouter:
    """The /money/net-worth routes. stocks_of(profile) gives the My Holdings totals in rupees; item_limit(plan) the
    entries a plan keeps (None: no limit); has_history(plan) whether it shows the history chart."""
    r = APIRouter(prefix="/money/net-worth")

    def bad(status: int, code: str, message: str):
        raise HTTPException(status, {"code": code, "message": message})

    def stocks(profile) -> dict | None:
        try:
            return stocks_of(profile)
        except Exception as e:
            print("net worth: holdings unavailable:", type(e).__name__)
            return None

    def page(profile, why: str | None = None) -> dict:
        uid = profile["id"]
        items = load(uid)["items"]
        # the holdings, the mutual funds, the history and the deposits' tax are separate reads: asked together, not one after
        # another (R9P-008: this page took 16 to 21 s to show anything)
        has_dep = any(i.get("kind") in ("fd", "rd") for i in items)
        f_stocks, f_mf, f_hist = POOL.submit(stocks, profile), POOL.submit(mf_value, uid), POOL.submit(history, uid)
        f_dep = POOL.submit(deposit_tax, profile) if has_dep else None
        v = build(items, f_stocks.result(), f_mf.result(), prices)
        hist = f_hist.result()
        has_any = bool(v["assets"] or v["liabilities"])
        this_month = today().strftime("%Y-%m")
        day = _date(v["as_of"])                              # a snapshot is dated by the prices in it: out of hours, the last close
        if why and has_any:
            hist = record(uid, v["totals"], why, day)
        elif has_any and not any(h["d"].startswith(this_month) for h in hist) and db.get_setting(SKIP + uid) != this_month:
            hist = record(uid, v["totals"], "month", day)   # the 1st-of-the-month run missed this user: taken on the first visit
        plan = profile["_plan"]
        allowed = has_history(plan)
        limit = item_limit(plan)
        dep = f_dep.result() if f_dep else None
        return {**v, "deposit_tax": dep, "history": hist if allowed else None, "history_allowed": allowed, "history_count": len(hist),
                "limit": limit, "count": len(items), "kinds": {k: LABEL[k] for k in KINDS}}

    @r.get("")
    def networth(profile=Depends(current_profile)):
        """Net worth today: assets (My Holdings, mutual funds and typed-in entries) minus loans, with the allocation,
        the history (Basic and up) and the insurance register."""
        return page(profile)

    def _limit_check(profile, n: int):
        cap = item_limit(profile["_plan"])
        if cap is not None and n > cap:
            bad(402, "networth_limit", f"Your plan keeps up to {cap} entries in Net worth (assets, loans and policies). "
                                       "Basic keeps as many as you like, with the history chart.")

    @r.post("/items")
    def add_item(req: ItemReq, profile=Depends(current_profile)):
        """Add an asset, loan or policy."""
        throttle(profile, "networth_edit", 200, 3600, "That's a lot of changes in an hour. Try again a little later.")
        try:
            entry = clean(req)
        except EntryError as e:
            bad(422, "bad_entry", str(e))
        items = load(profile["id"])["items"]
        if len(items) >= MAX_ITEMS:
            bad(400, "too_many", f"Net worth keeps up to {MAX_ITEMS} entries.")
        _limit_check(profile, len(items) + 1)
        entry["id"] = secrets.token_hex(4)
        save(profile["id"], items + [entry])
        return page(profile, "change")

    @r.put("/items/{iid}")
    def edit_item(iid: str, req: ItemReq, profile=Depends(current_profile)):
        """Change an entry (its kind can change too)."""
        throttle(profile, "networth_edit", 200, 3600, "That's a lot of changes in an hour. Try again a little later.")
        items = load(profile["id"])["items"]
        if not any(i["id"] == iid for i in items):
            bad(404, "not_found", "That entry isn't in your net worth any more.")
        try:
            entry = clean(req)
        except EntryError as e:
            bad(422, "bad_entry", str(e))
        save(profile["id"], [{**entry, "id": iid} if i["id"] == iid else i for i in items])
        return page(profile, "change")

    @r.delete("/items/{iid}")
    def delete_item(iid: str, profile=Depends(current_profile)):
        throttle(profile, "networth_edit", 200, 3600, "That's a lot of changes in an hour. Try again a little later.")
        items = load(profile["id"])["items"]
        if not any(i["id"] == iid for i in items):
            bad(404, "not_found", "That entry isn't in your net worth any more.")
        save(profile["id"], [i for i in items if i["id"] != iid])
        return page(profile, "change")

    @r.post("/prepay")
    def prepay_loan(req: PrepayReq, profile=Depends(current_profile)):
        """What prepaying an amount on one loan does to its tenure or EMI, and the interest it saves. Arithmetic only."""
        loan = next((i for i in load(profile["id"])["items"] if i["id"] == req.id and i["kind"] == "loan"), None)
        if not loan:
            bad(404, "not_found", "That loan isn't in your net worth any more.")
        if not (loan.get("tenure_months") and _date(loan.get("start"))):
            bad(400, "no_tenure", "Enter the loan's tenure and start date to work out a prepayment.")
        got = prepay(loan["principal"], loan["rate"], loan["tenure_months"], date.fromisoformat(loan["start"]), today(), req.amount)
        if got.get("error"):
            bad(400, "repaid", got["error"])
        out = {k: (_r(v) if isinstance(v, float) else v) for k, v in got.items()}
        for k in ("tenure", "lower_emi"):
            if out.get(k):
                out[k] = {a: (_r(b) if isinstance(b, float) else b) for a, b in out[k].items()}
        return {**out, "rate": loan["rate"], "as_of": today().isoformat(),
                "note": "Worked out on the rate and dates you entered. Your lender may charge for prepaying, or round differently."}

    @r.get("/upcoming")
    def upcoming(days: int = Query(60, ge=1, le=366), profile=Depends(current_profile)):
        """Maturities, premium dues and EMI dates in the next `days` days."""
        return {"rows": upcoming_dates(profile["id"], days)}

    @r.get("/export")
    def export(profile=Depends(current_profile)):
        """Everything on the page as a CSV file."""
        p = page(profile)
        return Response(to_csv(p, history(profile["id"])), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="stratlab-net-worth-{today().isoformat()}.csv"'})

    @r.delete("/history/{day}")
    def delete_snapshot(day: str, profile=Depends(current_profile)):
        """Remove one day's snapshot from the history chart; the entries and the other days stay."""
        throttle(profile, "networth_edit", 200, 3600, "That's a lot of changes in an hour. Try again a little later.")
        if not _date(day):
            bad(400, "bad_day", "Pick a day from the history.")
        left = drop_snapshot(profile["id"], day[:10])
        if left is None:
            bad(404, "not_found", "There's no snapshot on that day any more.")
        return {"history": left, "history_count": len(left)}

    @r.delete("")
    def delete_all(profile=Depends(current_profile)):
        """Delete my net worth data: every entry, policy and the history, at once. My Holdings isn't touched."""
        delete(profile["id"])
        return {"deleted": True}

    return r
