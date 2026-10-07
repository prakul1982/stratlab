"""Floating-rate loan check (Money → Net worth): for each loan the user marks as floating, whether its rate is
following its benchmark. For a repo-linked loan: the rate expected after each reset (the repo rate in force on the
reset date plus the spread), beside the rate the user enters from their statement, with any gap in points and in
rupees a year; and what each past rate change did, worked out both ways a lender can pass it on (a different EMI, or
the same EMI for more or fewer months), with the interest over the remaining life. For MCLR, T-bill-linked and other
loans, where the benchmark isn't public in a form we read, the change from the sanctioned rate to the statement rate.

Arithmetic on the user's own loan and the Reserve Bank's published repo rate. Never "switch lender" or "refinance";
a gap is a fact with where it can be raised, and the RBI's 2026 draft on loan pricing is shown as a draft."""
import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from . import money_networth as nw, rbi_rates
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import ok

BENCHMARKS = {"repo": "Repo-linked (external benchmark)", "tbill": "T-bill-linked (external benchmark)",
              "mclr": "MCLR (the lender's own rate)", "other": "Another internal rate (base rate, BPLR)", "fixed": "Fixed rate"}
GAP_PTS = 0.05                      # smaller differences are rounding
IST = ZoneInfo("Asia/Kolkata")


def today() -> date:
    """Today in India (the server runs on UTC, a day behind from midnight to 5:30 AM IST)."""
    return datetime.now(IST).date()


DRAFT = {
    "title": "Interest Rates on Loans and Advances Directions, 2026: a draft",
    "status": "Draft issued by the Reserve Bank on 13 Aug 2026; comments closed on 11 Sep 2026; proposed to apply from 1 Apr 2027. "
              "Not in force: the final rules may differ.",
    "points": [
        "Floating-rate loans would reset to their benchmark at least once every three months.",
        "The parts of the spread that aren't about your credit risk would stay fixed for three years.",
    ],
}
RAISE = [
    "First, your lender's grievance desk: ask for the benchmark, spread and reset dates used, and how the last change was applied.",
    "If there's no reply within 30 days, or the reply doesn't settle it, a complaint can go to the RBI Ombudsman at cms.rbi.org.in.",
]
DISCLAIMER = ("Arithmetic on the loan details you entered and the Reserve Bank's published repo rate. Your loan agreement and "
              "statement are the final word. Not advice on any lender or loan.")
NOTES = [
    "Expected rate for a repo-linked loan: the repo rate in force on the last reset date, plus your spread. The reset dates "
    "step from your last reset (or the start) by the reset period you entered.",
    "With no spread entered, it is taken as the sanctioned rate less the repo rate on the start date.",
    "Each change is shown both ways a lender can pass it on: a new EMI for the same remaining months, or the same EMI for "
    "more or fewer months. Balances follow the expected rates with the EMI unchanged.",
    "The gap in rupees a year is the balance owed today times the difference between the two rates.",
]


def _d(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def reset_dates(start: date, anchor: date, step: int, until: date) -> list[date]:
    """Reset dates from the loan's start to `until`, every `step` months, lined up on `anchor`."""
    n = 0
    while nw.add_months(anchor, -step * (n + 1)) > start:
        n += 1
    out, k = [], -n
    while True:
        d = nw.add_months(anchor, step * k)
        if d > until:
            break
        if d > start:
            out.append(d)
        k += 1
    return out


def rate_path(loan: dict, at: date, history: list[tuple[str, float]]) -> dict:
    """A repo-linked loan's expected rate at the start and after each reset up to `at`."""
    start = _d(loan["start"])
    spread = loan.get("spread")
    repo0 = rbi_rates.repo_on(start.isoformat(), history)
    inferred = spread is None
    if inferred:
        spread = round(loan["rate"] - repo0, 2) if repo0 is not None else None
    if spread is None:
        return {"spread": None, "inferred": inferred, "resets": [], "changes": [], "expected": None}
    step = int(loan.get("reset_months") or 3)
    anchor = _d(loan.get("last_reset")) or start
    resets = reset_dates(start, anchor, step, at)
    points = [(start, loan["rate"], repo0)]
    for d in resets:
        repo = rbi_rates.repo_on(d.isoformat(), history)
        if repo is not None:
            points.append((d, round(repo + spread, 2), repo))
    changes = [{"date": b[0].isoformat(), "from": a[1], "to": b[1], "repo": b[2]} for a, b in zip(points, points[1:]) if abs(b[1] - a[1]) > 1e-9]
    nxt = nw.add_months(anchor, step)
    while nxt <= at:
        nxt = nw.add_months(nxt, step)
    return {"spread": spread, "inferred": inferred, "reset_months": step, "last_reset": resets[-1].isoformat() if resets else None,
            "next_reset": nxt.isoformat(), "changes": changes, "expected": points[-1][1], "repo_at_reset": points[-1][2]}


def walk(principal: float, rate0: float, months: int, start: date, changes: list[dict], at: date) -> tuple[list[dict], float, int]:
    """Follow the loan month by month with the EMI kept, the rate changing on each change date: each change's effect
    both ways, the balance owed at `at` and EMIs paid by then."""
    rate = rate0
    pay = nw.emi(principal, rate0, months)
    bal = float(principal)
    out = []
    by_date = sorted(changes, key=lambda c: c["date"])
    ci = 0
    paid = nw.emis_paid(start, months, at)
    for j in range(1, months + 1):
        due = nw.add_months(start, j)
        while ci < len(by_date) and by_date[ci]["date"] <= due.isoformat():
            c = by_date[ci]
            left_months = months - (j - 1)
            old_m, old_int = nw.payoff(bal, c["from"], pay)
            new_emi = nw.emi(bal, c["to"], left_months)
            same_emi_m, same_emi_int = nw.payoff(bal, c["to"], pay)
            _, new_emi_int = nw.payoff(bal, c["to"], new_emi)
            out.append({**c, "balance": round(bal, 2), "emi_before": round(pay, 2),
                        "new_emi": round(new_emi, 2), "emi_change": round(new_emi - pay, 2),
                        "months_before": old_m, "months_if_same_emi": None if same_emi_int == math.inf else same_emi_m,
                        "months_change": None if same_emi_int == math.inf else same_emi_m - old_m,
                        "interest_before": None if old_int == math.inf else round(old_int, 2),
                        "interest_if_same_emi": None if same_emi_int == math.inf else round(same_emi_int, 2),
                        "interest_if_new_emi": round(new_emi_int, 2)})
            rate = c["to"]
            ci += 1
        if j > paid or bal <= 0.005:
            break
        r = rate / 1200
        if pay <= bal * r:                              # the EMI no longer covers the interest: it is raised to keep the tenure
            pay = nw.emi(bal, rate, max(1, months - j + 1))
        bal = max(0.0, bal * (1 + r) - pay)
    return out, bal, paid


def check(loan: dict, at: date, history: list[tuple[str, float]]) -> dict:
    """One loan's check."""
    bench = loan.get("benchmark") or "fixed"
    start = _d(loan.get("start"))
    months = loan.get("tenure_months")
    out = {"id": loan["id"], "name": loan.get("name") or (f"{nw.LOAN_TYPES.get(loan.get('loan_type', 'other'), 'Loan')}"
                                                           + (f", {loan['lender']}" if loan.get("lender") else "")),
           "benchmark": bench, "benchmark_label": BENCHMARKS[bench], "rate": loan["rate"], "current_rate": loan.get("current_rate"),
           "reset_months": loan.get("reset_months"), "ready": bool(start and months), "changes": [], "gap": None}
    if bench == "fixed" or not out["ready"]:
        out["why"] = "fixed" if bench == "fixed" else "Enter the tenure and start date to check this loan."
        return out
    if bench == "repo":
        p = rate_path(loan, at, history)
        out.update(spread=p["spread"], spread_inferred=p["inferred"], expected=p["expected"], last_reset=p.get("last_reset"),
                   next_reset=p.get("next_reset"), repo_at_reset=p.get("repo_at_reset"))
        changes = p["changes"]
    else:
        changes = []
        cur = loan.get("current_rate")
        if cur is not None and abs(cur - loan["rate"]) > 1e-9:
            changes = [{"date": (loan.get("last_reset") or at.isoformat()), "from": loan["rate"], "to": cur, "repo": None}]
        anchor = _d(loan.get("last_reset")) or start
        step = int(loan.get("reset_months") or 12)
        nxt = nw.add_months(anchor, step)
        while nxt <= at:
            nxt = nw.add_months(nxt, step)
        out.update(expected=None, next_reset=nxt.isoformat(), last_reset=loan.get("last_reset"))
    effects, bal, paid = walk(loan["principal"], loan["rate"], months, start, changes, at)
    out.update(changes=effects, outstanding=round(bal, 2), emis_paid=paid, left=months - paid)
    cur = loan.get("current_rate")
    if bench == "repo" and cur is not None and out.get("expected") is not None:
        diff = round(cur - out["expected"], 2)
        out["gap"] = {"pts": diff, "rupees_year": round(bal * diff / 100, 2), "matches": abs(diff) < GAP_PTS,
                      "after": out.get("last_reset")}
    return out


def view(profile: dict) -> dict:
    full = allows(profile["_plan"], "loan_check")
    at = today()
    loans = [i for i in nw.load(profile["id"])["items"] if i.get("kind") == "loan"]
    floating = [i for i in loans if (i.get("benchmark") or "fixed") != "fixed"]
    history = rbi_rates.repo_history()
    rbi = rbi_rates.current()
    base = {"full": full, "plan": PLANS[FEATURE_PLAN["loan_check"]]["name"], "loans": len(loans), "floating": len(floating),
            "repo": {"now": rbi_rates.repo_on(at.isoformat(), history), "history": [{"date": d, "rate": r} for d, r in history[-8:]],
                     "read_at": rbi["read_at"]},
            "draft": DRAFT, "raise": RAISE, "notes": NOTES, "disclaimer": DISCLAIMER, "as_of": at.isoformat(),
            "benchmarks": BENCHMARKS}
    if not full:
        return {**base, "checks": []}
    return {**base, "checks": [check(i, at, history) for i in floating]}


router = APIRouter(prefix="/money/loans", tags=["money"])


@router.get("/check")
def loans_check(profile=Depends(current_profile)):
    """Each floating-rate loan in Net worth against its benchmark: the expected rate after each reset, the gap to the
    rate on your statement, and what each change did to the EMI or the tenure (Basic and up)."""
    return ok(view(profile))
