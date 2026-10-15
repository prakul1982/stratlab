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
  1 April until it is paid (a part month counts as a month); a self-assessment payment stops it on the amount paid
  (section 234B(2)).

The TDS and payments the user enters are stored per user (advtax:<uid>) with their choice of reminders, seen only
by them and deleted with the tax data. Arithmetic on the user's own figures; never a view on what to do."""
import json
import math
import re
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import alerts, db, leader, run_marks
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
RETURN_BY_AUDIT = (10, 31)        # with a tax audit (section 44AB): 31 October, as the tax report says (R29B-015)
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
    "Payments dated after 31 March are self-assessment tax. Section 234B interest runs to each one on the shortfall then "
    "outstanding, and after it only on what is left (section 234B(2)). On an amount still unpaid it is counted to the "
    "return's due date (31 July, 31 August with intraday or F&O income from FY 2025-26 under Finance Act 2026, or 31 October when a tax audit applies), or to "
    "today once that date has passed.",
    "Section 234C: tax on gains and dividends that arose after 15 March carries no interest for March when paid by "
    "31 March (first proviso to section 234C).",
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


def return_due(fy: int, business: bool = False, audit: bool = False) -> date:
    """The return's due date: 31 October when a tax audit applies, else 31 July, or 31 August with business income
    (intraday, F&O) from FY 2025-26."""
    if audit:
        return date(fy + 1, *RETURN_BY_AUDIT)
    return date(fy + 1, *(RETURN_BY_BUSINESS if business and fy >= 2025 else RETURN_BY))


def split_paid(fy: int, payments: list[dict]) -> tuple[list[dict], list[dict]]:
    """(advance tax, self-assessment tax): payments dated by 31 March of the year are advance tax, later ones
    self-assessment tax (section 140A). The ITR export splits them the same way."""
    end = f"{fy + 1}-03-31"
    return [p for p in payments if p["d"] <= end], [p for p in payments if p["d"] > end]


def month_no(fy: int, day: date) -> int:
    """The month of `day` counted from April after the year (April = 1)."""
    return (day.year - (fy + 1)) * 12 + day.month - 3


def interest_234b(fy: int, short: float, later: list[dict], today: date, return_by: date) -> dict:
    """Section 234B month by month: 1% a month or part of a month on the shortfall from 1 April after the year. On a
    self-assessment payment the interest runs to it on the shortfall then outstanding, and after it only on what is
    left (section 234B(2)). Fully paid: it stops at the month of the last payment needed. Still unpaid: it runs to the
    return's due date, or to today once that has passed."""
    left = short
    paid_months: dict[int, float] = {}
    paid_until = None
    for p in sorted(later, key=lambda p: p["d"]):
        if left <= 0.005:
            break
        n = max(1, month_no(fy, date.fromisoformat(p["d"])))
        use = min(left, p["amount"])
        paid_months[n] = paid_months.get(n, 0.0) + use
        left = round(left - use, 2)
        paid_until = p["d"]
    unpaid = left > 0.005
    end = max(today, return_by) if unpaid else date.fromisoformat(paid_until) if paid_until else return_by
    last = month_no(fy, end) if unpaid or paid_until else 0
    periods, out, cur = [], short, 0.0
    for m in range(1, max(0, last) + 1):
        base = floor100(out)
        if periods and periods[-1]["base"] == base:
            periods[-1]["months"] += 1
        elif base > 0:
            periods.append({"base": base, "months": 1})
        cur += base * RATE
        out = round(out - paid_months.get(m, 0.0), 2)        # paid in month m: interest for m on the amount before it
        if out <= 0.005:
            break
    return {"interest": round(cur, 2), "months": sum(x["months"] for x in periods), "periods": periods,
            "until": end.isoformat(), "unpaid": round(max(0.0, left), 2), "fully_paid": not unpaid,
            "self_assessment": round(sum(p["amount"] for p in later), 2), "to_today": unpaid and today > return_by}


def schedule(fy: int, tax: float, tax_upto: list[float], tds: float, payments: list[dict], today: date,
             business: bool = False, audit: bool = False) -> dict:
    """The year's instalments. `tax` is the year's total tax; `tax_upto[i]` the same with only the share gains and
    dividends that had arisen by due date i (the last is to 15 March). `tds` is the TDS for the year and `payments`
    the tax paid ({d, amount}): by 31 March advance tax, after it self-assessment tax. `business` is whether the year
    has business income, which moves the return's due date (and so 234B's months) to 31 August."""
    payments = sorted(payments, key=lambda p: p["d"])
    advance, later = split_paid(fy, payments)
    net = max(0.0, tax - tds)
    due = net >= THRESHOLD
    today_s = today.isoformat()
    paid_march_end = paid_by(advance, f"{fy + 1}-03-31")
    rows, nxt = [], None
    for dd, upto in zip(due_dates(fy), tax_upto):
        i = dd["n"]
        base = max(0.0, min(net, upto - tds))
        paid = paid_by(advance, dd["date"])
        late = 0.0
        if i == 3:
            # first proviso to section 234C: tax on gains and dividends that arose after 15 March carries no interest
            # when paid by 31 March; whatever of it isn't paid by then counts in the March shortfall
            late = round(net - base, 2)
            late_short = max(0.0, late - max(0.0, paid_march_end - min(paid, base)))
            required = round(net, 2) if due else 0.0
            short = round(max(0.0, base - paid) + late_short, 2) if due else 0.0
        else:
            required = round(dd["pct"] * base, 2) if due else 0.0
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
                     "tolerated": tolerated, "status": status, "late": late,
                     "paid_by_31_march": paid_march_end if i == 3 else None})
    paid_year = paid_march_end
    b_short = round(max(0.0, net - paid_year), 2)
    b_applies = due and paid_year < 0.9 * net
    rb = return_due(fy, business, audit)
    b = interest_234b(fy, b_short, later, today, rb) if b_applies else None
    b234 = {"applies": b_applies, "paid": paid_year, "ninety_pct": round(0.9 * net, 2), "short": b_short,
            "months": b["months"] if b else 0, "until": b["until"] if b else rb.isoformat(),
            "interest": b["interest"] if b else 0.0, "periods": b["periods"] if b else [],
            "self_assessment": round(sum(p["amount"] for p in later), 2), "unpaid": b["unpaid"] if b else 0.0,
            "fully_paid": b["fully_paid"] if b else True, "to_today": b["to_today"] if b else False,
            "return_by": rb.isoformat()}
    return {"fy": fy, "label": fy_label(fy), "tax": round(tax, 2), "tds": round(tds, 2), "net": round(net, 2), "due": due,
            "threshold": THRESHOLD, "instalments": rows, "next": nxt, "paid": paid_year,
            "self_assessment": b234["self_assessment"],
            "interest_234c": round(sum(r["interest_234c"] for r in rows), 2), "b234": b234, "steps": steps(fy, net, due, rows, b234)}


def _month(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%B %Y")


def steps(fy: int, net: float, due: bool, rows: list[dict], b234: dict) -> list[str]:
    """The working in plain words."""
    if not due:
        return [f"The year's tax less TDS is {money(net)}, below {money(THRESHOLD)}, so no advance tax is due "
                f"(section 208{'; section 404 of the Income-tax Act, 2025' if fy >= 2026 else ''}). Any tax left is paid "
                "as self-assessment tax before filing."]
    out = [f"The year's tax less TDS is {money(net)}: {money(THRESHOLD)} or more, so advance tax is due."]
    for r in rows:
        if r["n"] < 3:
            line = (f"By {r['label']}: {r['pct'] * 100:g}% of {money(r['base'])} = {money(r['required'])}; paid by then "
                    f"{money(r['paid'])}.")
            if r["base"] < net - 0.5:
                line += " Gains and dividends that arose after this date are left out of it (they go into later instalments)."
        else:
            line = f"By {r['label']}: all of {money(net)}; paid by then {money(r['paid'])}."
            if r["late"] > 0.5:
                line += (f" Of the tax, {money(r['late'])} is on gains and dividends that arose after 15 March: there's no "
                         f"234C interest on it when paid by 31 March (paid by 31 March: {money(r['paid_by_31_march'])}).")
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
        line = (f"Advance tax paid by 31 March, {money(b234['paid'])}, is less than 90% of the tax ({money(b234['ninety_pct'])}), "
                f"so section 234B interest applies from 1 April on the shortfall of {money(b234['short'])}")
        if b234["self_assessment"] > 0:
            parts = [f"{money(p['base'])} for {p['months']} month{'s' if p['months'] > 1 else ''}" for p in b234["periods"]]
            line += (f". Self-assessment tax of {money(b234['self_assessment'])} was paid after 31 March; interest runs to each "
                     f"payment on the amount then outstanding and after it only on what is left: 1% a month on "
                     f"{', then '.join(parts) or money(0)} = {money(b234['interest'])}.")
        else:
            line += (f": 1% a month on {money(floor100(b234['short']))} for {b234['months']} months (April to "
                     f"{_month(b234['until'])}) = {money(b234['interest'])}.")
        if b234["fully_paid"] and b234["self_assessment"] > 0:
            line += f" The shortfall was fully paid in {_month(b234['until'])}, so the interest stops there."
        elif b234["to_today"]:
            line += (f" {money(b234['unpaid'])} is still unpaid, so the interest is counted to today ({_month(b234['until'])}) "
                     "and goes up by 1% of it each month until it is paid.")
        else:
            line += (f" {money(b234['unpaid'])} is still unpaid; the interest is shown as if it is paid by the return's due "
                     f"date, {datetime.fromisoformat(b234['return_by']).strftime('%-d %B %Y')}.")
        out.append(line)
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
            f"(less TDS) is due, counting what was paid before.\n\n"
            f"Your figures: {settings.PUBLIC_SITE_URL}/money/tax-tools?tab=advance\n\n"
            "Dates as the Income-tax Act sets them. Facts, not tax advice; check with a chartered accountant.")
    return subject, text


def reminder_email(d: dict, days: int) -> tuple[str, str, str]:
    """(subject, html, text) for one reminder in the shared email design: the instalment, its date and the share of the
    year's tax due by then as tiles, and a button to the page with the person's own figures. No amounts here."""
    from . import email_kit as kit
    subject, _ = reminder_text(d, days)
    when = "tomorrow" if days == 1 else f"in {days} days"
    due = date.fromisoformat(d["date"])
    html, text = kit.render(
        f"Advance tax is due {when}", [
            kit.tiles([kit.Tile("Instalment", f"{d['n'] + 1} of 4"), kit.Tile("Due by", f"{due:%a} {due.day} {due:%b}", sub=str(due.year)),
                       kit.Tile("Share of the year's tax", f"{d['pct'] * 100:g}%", sub="paid by then, less TDS")]),
            kit.para(f"By {d['label']}, {d['pct'] * 100:g}% of the year's tax (less TDS) is due, counting what was paid before."),
        ], kit.Footer(why="You get this because you turned on advance tax reminders.", unsubscribe="Stop advance tax reminders",
                      legal="Dates as the Income-tax Act sets them. Facts, not tax advice; check with a chartered accountant."),
        # the header's date is the day the email goes out, as on every other email; the due date is in the tiles (R6V-016)
        label="Advance tax", date=kit.fmt_date(due - timedelta(days=days), year=False, weekday=True),
        summary=f"The {d['label']} instalment is due {when}.",
        cta=("Open your advance tax figures", "/money/tax-tools?tab=advance"), subject=subject)
    return subject, html, text


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


_current: tuple[dict, int] | None = None        # the reminder the job is sending now (send() keeps its three arguments)


def send(profile: dict, subject: str, text: str) -> bool:
    """Email (to a confirmed address, with an unsubscribe link) and a phone notification, where set up."""
    sent = False
    to = alerts.newsletter_email(profile)
    if to and alerts.email_confirmed(profile) and alerts.email_ready():
        try:
            from . import email_kit as kit
            if _current:
                _, html, plain = reminder_email(*_current)
            else:
                html, plain = kit.message(subject, text, "/money/tax-tools?tab=advance", "Advance tax",
                                          "You get this because you turned on advance tax reminders.")
            html, plain, headers = kit.finish(html, plain, profile["id"], "advance_tax")
            alerts.send_email(to, subject, plain, html=html, headers=headers)
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
                if leader.leading():      # another container leads: it runs this pass
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
            run = run_marks.claim(f"{RUN_KEY}{d['date']}:{n}", local.date().isoformat(), once=True)      # or the run a restart cut short
            if not run:
                continue
            subject, text = reminder_text(d, n)
            for uid in subscribers():
                if run.seen(uid):
                    continue
                run.beat()
                try:                               # one subscriber's failure never stops the rest
                    profile = db.get_profile(uid)
                    if profile:
                        globals()["_current"] = (d, n)
                        run.record(uid)            # before the send: a kill in between drops one, never doubles
                        sent += send(profile, subject, text)
                except Exception as e:
                    print("advance tax reminder failed:", type(e).__name__)
            run.done()
        self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
        return sent
