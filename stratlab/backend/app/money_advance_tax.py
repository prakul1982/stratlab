"""Advance tax: the four instalments of a financial year, the cumulative amount due by each from the year's total tax
estimate, less the TDS and advance tax the user has paid, and the interest the law adds when an instalment is short.

The rules (Income-tax Act 1961, sections 207 to 211, 234B and 234C; from tax year 2026-27 the Income-tax Act 2025,
section 404 for who pays and sections 424 and 425 for the interest):
- Advance tax is due when the year's tax less TDS is ₹10,000 or more.
- 15% of it by 15 June, 45% by 15 September, 75% by 15 December and all of it by 15 March, cumulative.
- Capital gains and dividends that arise after a due date can't be foreseen, so the tax on them goes into the
  instalments still to come (by 31 March when none is left) without interest: each instalment here is worked out on
  the income that had arisen by its date.
- Section 234C: 1% a month on each instalment's shortfall (in whole ₹100), for 3 months on the first three and 1 month
  on the last; none for June when 12% was paid by then, none for September when 36% was.
- Section 234B: when advance tax paid by 31 March is less than 90% of the tax, 1% a month on the shortfall from
  1 April until it is paid (a part month counts as a month).

The TDS and payments the user enters are stored per user (advtax:<uid>) with their choice of reminders, seen only
by them and deleted with the tax data. Arithmetic on the user's own figures; never a view on what to do."""
import json
import math
import re
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import alerts, db
from .config import settings
from .tax_lots import fy_label, money

KEY = "advtax:"                   # advtax:<uid> = {"remind": bool, "years": {"2026": {"tds", "paid": [{d, amount}]}}}
RUN_KEY = "moneyjob:advtax:"      # moneyjob:advtax:<due date>:<days before> = when it ran
THRESHOLD = 10000.0
INSTALMENTS = ((6, 15, 0.15), (9, 15, 0.45), (12, 15, 0.75), (3, 15, 1.0))
TOLERANCE = {0: 0.12, 1: 0.36}    # paid at least this share by June and September: no 234C interest for that one
RATE = 0.01                       # a month, for 234B and 234C
MONTHS_234C = (3, 3, 3, 1)
RETURN_BY = (7, 31)               # 234B is shown as if the rest is paid with the return, by 31 July
RETURN_BY_BUSINESS = (8, 31)      # with business income and no audit, by 31 August from FY 2025-26 (Finance Act 2026)
MAX_AMOUNT = 1e11
MAX_PAYMENTS = 24
REMIND_DAYS = (7, 1)
REMIND_AT = ("Asia/Kolkata", "09:00")
ASSUMPTIONS = [
    "The tax is the total tax estimate for the year from your tax report: share gains, intraday, F&O and the other "
    "income and dividends included there, at the rates of your chosen regime.",
    "A resident individual under 60 is assumed. A resident aged 60 or more with no business income doesn't pay advance "
    "tax (section 207).",
    "Each instalment is worked out on the share gains and dividends that had arisen by its due date; everything else "
    "(salary, interest, intraday and F&O results) is counted for the whole year at every date.",
    "Interest is shown on whole ₹100 of shortfall, the way rule 119A rounds it. Interest under section 234A (a late "
    "return) isn't included.",
    "Section 234B interest is counted to the return's due date: 31 July, or 31 August with intraday or F&O income from "
    "FY 2025-26 (Finance Act 2026).",
]


def due_dates(fy: int) -> list[dict]:
    """The year's four due dates, with the cumulative share of the tax due by each."""
    out = []
    for i, (m, d, pct) in enumerate(INSTALMENTS):
        day = date(fy if m >= 4 else fy + 1, m, d)
        out.append({"n": i, "date": day.isoformat(), "pct": pct, "label": day.strftime("%-d %b %Y")})
    return out


def floor100(v: float) -> float:
    return math.floor(max(0.0, v) / 100) * 100


def paid_by(payments: list[dict], day: str) -> float:
    return round(sum(p["amount"] for p in payments if p["d"] <= day), 2)


def months_234b(fy: int, pay_day: date) -> int:
    """Months from 1 April after the year to the month of payment, a part month counting as a month."""
    return max(0, (pay_day.year - (fy + 1)) * 12 + pay_day.month - 3)


def return_due(fy: int, business: bool = False) -> date:
    """The return's due date without an audit: 31 July, or 31 August with business income (intraday, F&O) from
    FY 2025-26."""
    return date(fy + 1, *(RETURN_BY_BUSINESS if business and fy >= 2025 else RETURN_BY))


def schedule(fy: int, tax: float, tax_upto: list[float], tds: float, payments: list[dict], today: date,
             business: bool = False) -> dict:
    """The year's instalments. `tax` is the year's total tax; `tax_upto[i]` the same with only the share gains and
    dividends that had arisen by due date i (the last is the whole year). `tds` is the TDS for the year and
    `payments` the advance tax paid ({d, amount}); `business` whether the year has business income, which moves the
    return's due date (and so 234B's months) to 31 August."""
    payments = sorted(payments, key=lambda p: p["d"])
    net = max(0.0, tax - tds)
    due = net >= THRESHOLD
    today_s = today.isoformat()
    rows, nxt = [], None
    for dd, upto in zip(due_dates(fy), tax_upto):
        i = dd["n"]
        base = net if i == 3 else max(0.0, min(net, upto - tds))
        required = round(dd["pct"] * base, 2) if due else 0.0
        paid = paid_by(payments, dd["date"])
        short = round(max(0.0, required - paid), 2)
        passed = today_s > dd["date"]
        tol = TOLERANCE.get(i)
        tolerated = due and short > 0 and tol is not None and paid >= tol * base
        interest = 0.0
        if due and short > 0 and not tolerated:
            interest = round(floor100(short) * RATE * MONTHS_234C[i], 2)
        status = "passed" if passed else "next" if nxt is None else "later"
        if not passed and nxt is None:
            nxt = i
        rows.append({**dd, "base": round(base, 2), "required": required, "paid": paid, "short": short,
                     "to_pay": short if not passed else 0.0, "interest_234c": interest if passed else 0.0,
                     "interest_if_missed": interest if not passed else 0.0, "months": MONTHS_234C[i],
                     "tolerated": tolerated, "status": status})
    paid_year = paid_by(payments, f"{fy + 1}-03-31")
    year_over = today_s > f"{fy + 1}-03-31"
    pay_day = max(today, return_due(fy, business)) if year_over else return_due(fy, business)
    b_short = max(0.0, net - paid_year)
    b_applies = due and paid_year < 0.9 * net
    b_months = months_234b(fy, pay_day)
    b234 = {"applies": b_applies, "paid": paid_year, "ninety_pct": round(0.9 * net, 2), "short": round(b_short, 2),
            "months": b_months, "until": pay_day.isoformat(),
            "interest": round(floor100(b_short) * RATE * b_months, 2) if b_applies else 0.0}
    return {"fy": fy, "label": fy_label(fy), "tax": round(tax, 2), "tds": round(tds, 2), "net": round(net, 2), "due": due,
            "threshold": THRESHOLD, "instalments": rows, "next": nxt, "paid": paid_year,
            "interest_234c": round(sum(r["interest_234c"] for r in rows), 2), "b234": b234, "steps": steps(fy, net, due, rows, b234)}


def steps(fy: int, net: float, due: bool, rows: list[dict], b234: dict) -> list[str]:
    """The working in plain words."""
    if not due:
        return [f"The year's tax less TDS is {money(net)}, below {money(THRESHOLD)}, so no advance tax is due "
                f"(section 208{'; section 404 of the Income-tax Act, 2025' if fy >= 2026 else ''}). Any tax left is paid "
                "as self-assessment tax before filing."]
    out = [f"The year's tax less TDS is {money(net)}: {money(THRESHOLD)} or more, so advance tax is due."]
    for r in rows:
        line = (f"By {r['label']}: {r['pct'] * 100:g}% of {money(r['base'])} = {money(r['required'])}; paid by then "
                f"{money(r['paid'])}.")
        if r["base"] < net - 0.5 and r["n"] < 3:
            line += " Gains and dividends that arose after this date are left out of it (they go into later instalments)."
        if r["status"] == "passed":
            if r["tolerated"]:
                line += f" Short by {money(r['short'])}, but {TOLERANCE[r['n']] * 100:g}% or more was paid, so there's no interest on it."
            elif r["interest_234c"]:
                line += (f" Short by {money(r['short'])}: section 234C interest of 1% a month for {r['months']} "
                         f"month{'s' if r['months'] > 1 else ''} = {money(r['interest_234c'])}.")
        elif r["to_pay"] > 0:
            line += f" Still to pay by then: {money(r['to_pay'])}."
        out.append(line)
    if b234["applies"]:
        out.append(f"Advance tax paid by 31 March, {money(b234['paid'])}, is less than 90% of the tax ({money(b234['ninety_pct'])}), "
                   f"so section 234B interest applies: 1% a month on {money(floor100(b234['short']))} for {b234['months']} "
                   f"months (April to {datetime.fromisoformat(b234['until']).strftime('%B %Y')}) = {money(b234['interest'])}.")
    return out


# ---------- the user's figures ----------
def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def _amount(x) -> float:
    if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x) or x < 0:
        return 0.0
    return round(min(float(x), MAX_AMOUNT), 2)


def clean_year(v) -> dict:
    """TDS and payments as stored, each checked: amounts 0 or more and capped, dates real."""
    v = v if isinstance(v, dict) else {}
    paid = []
    for p in v.get("paid") or []:
        if isinstance(p, dict) and isinstance(p.get("d"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["d"]):
            try:
                date.fromisoformat(p["d"])
            except ValueError:
                continue
            a = _amount(p.get("amount"))
            if a > 0:
                paid.append({"d": p["d"], "amount": a})
    return {"tds": _amount(v.get("tds")), "paid": sorted(paid, key=lambda p: p["d"])[:MAX_PAYMENTS]}


def load(uid: str) -> dict:
    got = db.json_value(db.get_setting(_key(uid)), {})
    got = got if isinstance(got, dict) else {}
    years = got.get("years") if isinstance(got.get("years"), dict) else {}
    return {"remind": bool(got.get("remind")),
            "years": {int(k): clean_year(v) for k, v in years.items() if str(k).isdigit() and 2000 <= int(k) <= 2100}}


def _save(uid: str, data: dict):
    db.set_setting(_key(uid), json.dumps({"uid": uid, "remind": data["remind"],
                                          "years": {str(k): v for k, v in data["years"].items()}}, separators=(",", ":")))


def save_year(uid: str, fy: int, v: dict):
    data = load(uid)
    data["years"][fy] = clean_year(v)
    _save(uid, data)


def set_remind(uid: str, on: bool):
    if not on and not db.get_setting(_key(uid)):
        return                       # nothing saved: nothing to turn off
    data = load(uid)
    data["remind"] = bool(on)
    _save(uid, data)


def delete(uid: str):
    """The figures and the reminder choice, at once."""
    db.delete_setting(_key(uid))


# ---------- reminders ----------
def reminder_text(d: dict, days: int) -> tuple[str, str]:
    """(subject, text) for one reminder. No amounts: those stay on the page."""
    when = "tomorrow" if days == 1 else f"in {days} days"
    subject = f"Advance tax: the {d['label']} instalment is {when}"
    text = (f"The advance tax instalment of {d['label']} is due {when}: by then, {d['pct'] * 100:g}% of the year's tax "
            f"(less TDS) should be paid, counting what was paid before.\n\n"
            f"Your figures: {settings.PUBLIC_SITE_URL}/money/tax-tools?tab=advance\n\n"
            "Dates as the Income-tax Act sets them. Facts, not tax advice; check with a chartered accountant.")
    return subject, text


def reminders_due(today: date) -> list[tuple[dict, int]]:
    """(due date, days before) for the reminders that go out today."""
    out = []
    for fy in (today.year - 1, today.year):
        for d in due_dates(fy):
            for n in REMIND_DAYS:
                if date.fromisoformat(d["date"]) - timedelta(days=n) == today:
                    out.append((d, n))
    return out


def subscribers() -> list[str]:
    out = []
    for _, raw in db.all_settings_with_prefix(KEY):
        got = db.json_value(raw, {})
        if isinstance(got, dict) and got.get("remind") and got.get("uid"):
            out.append(got["uid"])
    return out


def send(profile: dict, subject: str, text: str) -> bool:
    """Email (to a confirmed address, with an unsubscribe link) and a phone notification, where set up."""
    sent = False
    to = alerts.newsletter_email(profile)
    if to and alerts.email_confirmed(profile) and alerts.email_ready():
        try:
            unsub = alerts.unsubscribe_url(profile["id"], "advance_tax")
            alerts.send_email(to, subject, f"{text}\n\nStop these reminders: {unsub}",
                              headers=alerts.list_unsubscribe_headers(profile["id"], "advance_tax"))
            sent = True
        except Exception as e:
            print("advance tax reminder email failed:", str(e)[:160])
    quiet = {**profile, "alert_email": None, "email": None}         # never a second email
    try:
        if alerts.jobs_for(quiet, "", ""):
            alerts.notify(quiet, subject, text.split("\n\n")[0], url="/money/tax-tools?tab=advance")
            sent = True
    except Exception as e:
        print("advance tax reminder push failed:", str(e)[:160])
    return sent


class Job:
    """Checks every ten minutes; each reminder is marked in the database before it goes, so it goes once."""

    def __init__(self):
        self.status = {"last_run": None, "sent": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="advance-tax").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("advance tax reminders:", e)
            time.sleep(600)

    def tick(self, now: datetime) -> int:
        tz, at = REMIND_AT
        local = now.astimezone(ZoneInfo(tz))
        if local.strftime("%H:%M") < at:
            return 0
        sent = 0
        for d, n in reminders_due(local.date()):
            mark = f"{RUN_KEY}{d['date']}:{n}"
            if db.get_setting(mark):
                continue
            db.set_setting(mark, now.isoformat(timespec="minutes"))
            subject, text = reminder_text(d, n)
            for uid in subscribers():
                profile = db.get_profile(uid)
                if profile:
                    sent += send(profile, subject, text)
        self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
        return sent
