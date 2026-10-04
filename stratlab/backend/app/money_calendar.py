"""Money calendar: the user's own dated money events in one list and month view, and as a private calendar feed.

- Tax: advance-tax instalments, the return due dates, the last day for a belated or revised return and the
  last day for the year's tax-saving investments (old regime), as the law sets them.
- Holdings: results meetings, corporate actions (ex-dates and record dates of dividends, bonuses, splits and the
  like, and the record dates announced with an AGM) for the user's holdings and watchlist, from the stored results
  and corporate-actions calendars; gold bonds' maturity months.
- Other Money pages, when they exist: maturities, premiums and EMIs (money_networth), advance-tax amounts
  (money_advance_tax) and SIP dates (money_mf), each through an optional hook that gives nothing when missing.
- The user's own events, once, every month or every year.

The feed is an ICS file at a private, unguessable link (a token only its owner sees, turned off or replaced at any
time), so Google Calendar or Apple Calendar can subscribe. It leaves out the user's amounts unless they ask for
them. Reminders (Basic and up) go a set number of days before, by email or phone notification, per category.

Stored per user in app_settings (moneycal:<uid>), seen only by that user, and deleted in one step; the feed's
token is looked up by its hash (moneycalfeed:<sha256>). Values are never logged. Dated facts only; never a view on
what to do."""
import hashlib
import importlib
import json
import math
import re
import secrets
import threading
import time
import uuid
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import db
from .auth import current_profile
from .branding import public_text
from .responses import err as _err
from .plans import FEATURE_PLAN, PLANS, access_plan, allows

IST = ZoneInfo("Asia/Kolkata")
KEY = "moneycal:"                 # moneycal:<uid> = {"events": [...], "feed": {...}, "reminders": {...}}
FEED_KEY = "moneycalfeed:"        # moneycalfeed:<sha256 of the token> = uid
JOB_KEY = "moneycaljob:reminders"  # the last day the reminders went out
CATS = ("tax", "holdings", "money", "custom")
CAT_NAMES = {"tax": "Tax", "holdings": "Holdings", "money": "Money", "custom": "Your events"}
MAX_EVENTS = 200                  # the user's own events
MAX_SPAN = 400                    # days in one view
FEED_BEHIND, FEED_AHEAD = 30, 400  # what the feed holds, around today
FEED_RATE = (60, 3600)            # requests a token may make in that many seconds (a calendar app asks every few hours)
MAX_LIST = 1500                   # events in one answer
REMIND_DAYS = (1, 2, 3, 7, 14)
REMIND_AT = "08:40"               # India time, each day
HOOKS = [("money_networth", "upcoming_dates", "money"), ("money_advance_tax", "upcoming_dates", "tax"),
         ("money_mf", "upcoming_dates", "money"), ("money_mf", "sip_dates", "money")]
NOTES = [
    "Tax dates are the ones the law sets for a resident individual; the tax department can extend them. Advance tax "
    "is due only when the year's tax, after TDS, is ₹10,000 or more.",
    "Results and corporate-action dates are as the companies announced them, for your holdings and watchlist. A "
    "dividend's total is the amount a share times the shares you hold today, an estimate.",
    "Dates from your other Money pages are what you entered there.",
]


def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def load(uid: str) -> dict:
    """{"events", "feed", "reminders"}; empty parts when the user has none (or the row is damaged)."""
    got = db.json_value(db.get_setting(_key(uid)), {})
    events = [e for e in got.get("events") or [] if _event_ok(e)]
    feed = got.get("feed") if isinstance(got.get("feed"), dict) and isinstance(got["feed"].get("token"), str) else None
    return {"events": events[:MAX_EVENTS], "feed": feed, "reminders": clean_reminders(got.get("reminders"))}


def save(uid: str, data: dict):
    db.set_setting(_key(uid), json.dumps({"events": data["events"][:MAX_EVENTS], "feed": data.get("feed"),
                                          "reminders": data.get("reminders")}, separators=(",", ":")))


def delete(uid: str):
    """Every event, the feed (its link stops working) and the reminder settings."""
    data = load(uid)
    if data["feed"]:
        db.delete_setting(FEED_KEY + _hash(data["feed"]["token"]))
    db.delete_setting(_key(uid))


def _event_ok(e) -> bool:
    return (isinstance(e, dict) and isinstance(e.get("id"), str) and isinstance(e.get("title"), str) and isinstance(e.get("date"), str)
            and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"])) and e.get("repeat", "none") in ("none", "monthly", "yearly"))


def clean_reminders(r) -> dict:
    r = r if isinstance(r, dict) else {}
    cats = [c for c in r.get("cats") or [] if c in CATS] if isinstance(r.get("cats"), list) else list(CATS)
    return {"on": bool(r.get("on")), "days": r.get("days") if r.get("days") in REMIND_DAYS else 3,
            "channel": r.get("channel") if r.get("channel") in ("email", "push", "both") else "both", "cats": cats}


# ---------- tax dates: the law's own ----------
def _ev(day: date, title: str, cat: str, kind: str, detail: str = "", *, amount=None, symbol=None, ref=None, url=None) -> dict:
    eid = f"{cat}:{kind}:{day.isoformat()}:{ref or symbol or ''}"[:120]
    return {"id": eid, "date": day.isoformat(), "title": title[:120], "cat": cat, "kind": kind, "detail": detail[:400],
            "amount": round(float(amount), 2) if isinstance(amount, (int, float)) and math.isfinite(amount) else None,
            "symbol": symbol, "url": url}


def fy_label(y: int) -> str:
    return f"FY {y}-{str(y + 1)[2:]}"


def tax_dates(fy: int) -> list[dict]:
    """One financial year's dates (fy is its first year: 2025 for FY 2025-26).

    Advance tax: section 211 of the 1961 Act (section 404 of the Income-tax Act, 2025 from tax year 2026-27): 15%,
    45%, 75% and 100% by 15 Jun, 15 Sep, 15 Dec and 15 Mar; the presumptive scheme (44AD/44ADA) pays it all by 15 Mar.
    Returns (section 139): 31 Jul without an audit; from FY 2025-26 the Finance Act 2026 moved non-audit business and
    profession returns (ITR-3, ITR-4) to 31 Aug; 31 Oct with an audit. Belated return by 31 Dec (139(4)); revised by
    31 Dec, or by 31 Mar from FY 2025-26 (Finance Act 2026). Sources, checked 4 Oct 2026:
    https://cleartax.in/s/due-date-tax-filing and the Budget 2026 summaries on the ITR due dates."""
    lab, ay = fy_label(fy), fy + 1
    sec = "263" if fy >= 2026 else "139"     # the Income-tax Act, 2025 renumbers section 139 from tax year 2026-27
    out = []
    for (m, d, pct, when) in ((6, 15, 15, "first"), (9, 15, 45, "second"), (12, 15, 75, "third"), (3, 15, 100, "last")):
        day = date(fy + (1 if m == 3 else 0), m, d)
        detail = (f"{pct}% of {lab}'s estimated tax, less TDS, paid by today (cumulative). Due only when the year's tax "
                  "after TDS is ₹10,000 or more; residents over 60 without business income are exempt.")
        if m == 3:
            detail += " Under the presumptive scheme (44AD, 44ADA) the whole amount is due by today."
        out.append(_ev(day, f"Advance tax, {when} instalment ({pct}%)", "tax", "advance_tax", detail, ref=lab))
    out.append(_ev(date(fy + 1, 3, 31), f"Last day for {lab} tax-saving investments (old regime)", "tax", "tax_saving",
                   "Deductions under the old regime (80C, 80D, 80CCD(1B) and the like) count only for payments made by 31 "
                   "March. PPF and Sukanya Samriddhi accounts need their yearly minimum deposit by then to stay active.", ref=lab))
    if fy >= 2025:
        out.append(_ev(date(ay, 7, 31), f"ITR due date for {lab} (no business income)", "tax", "itr",
                       "Return due date for individuals without business or professional income (ITR-1, ITR-2).", ref=lab))
        out.append(_ev(date(ay, 8, 31), f"ITR due date for {lab} (business, no audit)", "tax", "itr",
                       "Return due date for business or professional income without a tax audit (ITR-3, ITR-4), from "
                       "FY 2025-26. Intraday and F&O trading count as business income.", ref=lab))
    else:
        out.append(_ev(date(ay, 7, 31), f"ITR due date for {lab} (no audit)", "tax", "itr",
                       "Return due date when the accounts don't need a tax audit.", ref=lab))
    out.append(_ev(date(ay, 10, 31), f"ITR due date for {lab} (audit cases)", "tax", "itr",
                   "Return due date when the accounts need a tax audit (section 44AB).", ref=lab + " audit"))
    if fy >= 2025:
        out.append(_ev(date(ay, 12, 31), f"Last day for a belated {lab} return", "tax", "itr_late",
                       f"A return filed after its due date (section {sec}(4)), with the late fee. Losses can't be carried forward "
                       "from a late return.", ref=lab))
        out.append(_ev(date(ay + 1, 3, 31), f"Last day to revise the {lab} return", "tax", "itr_revise",
                       f"A revised return (section {sec}(5)) can be filed until 31 March from FY 2025-26.", ref=lab))
    else:
        out.append(_ev(date(ay, 12, 31), f"Last day for a belated or revised {lab} return", "tax", "itr_late",
                       "A late return (section 139(4)) or a revised one (139(5)). Losses can't be carried forward from a "
                       "late return.", ref=lab))
    return out


def tax_between(frm: date, to: date) -> list[dict]:
    first = (frm.year if frm.month >= 4 else frm.year - 1) - 2          # a revised return reaches two years on
    last = to.year if to.month >= 4 else to.year - 1
    out = []
    for fy in range(first, last + 1):
        out += [e for e in tax_dates(fy) if frm.isoformat() <= e["date"] <= to.isoformat()]
    return out


# ---------- holdings and watchlist ----------
def tracked(uid: str) -> tuple[dict[str, dict], list[tuple[str, str]]]:
    """(the Indian holdings by symbol, (region, symbol) for the watchlist)."""
    from . import holdings
    items = holdings.load(uid)["items"]
    held = {i["symbol"]: i for i in holdings.indian(items)}
    watch = []
    raw = db.json_value(db.get_setting(f"watchlist:{uid}"), {})
    for i in raw.get("items") or [] if isinstance(raw, dict) else []:
        if isinstance(i, dict) and i.get("region") in ("IN", "US") and isinstance(i.get("symbol"), str):
            watch.append((i["region"], i["symbol"].upper()[:20]))
    us_held = [("US", i["symbol"]) for i in items if holdings.market_of(i) == "US"]
    return held, (watch + us_held)[:300]


def _day(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _money(v: float) -> str:
    from .tax_lots import money
    return money(v)


def holdings_events(uid: str, frm: date, to: date) -> list[dict]:
    """Results meetings and corporate actions for the user's holdings and watchlist, from the stored calendars."""
    from . import corp_actions, instrument_kinds, results
    held, watch = tracked(uid)
    out: list[dict] = []
    for region in ("IN", "US"):
        syms = ({s for s in held} if region == "IN" else set()) | {s for r, s in watch if r == region}
        if not syms:
            continue
        for r in results.between(region, frm, to, syms):
            d = _day(r["date"])
            if d:
                why = f" ({r['when']})" if r.get("when") else ""
                out.append(_ev(d, f"{r['symbol']}: results{why}", "holdings", "results", r.get("purpose") or "Board meeting on results.",
                               symbol=r["symbol"], url=f"/research/{region}/{r['symbol']}"))
    cal = corp_actions.load("IN")["rows"]
    rows: dict[str, dict] = {}
    for s in held:
        for a in corp_actions.actions_for("IN", s, None, None, fetch=False, cal=cal):
            rows[a["id"]] = a
    watch_in = {s for r, s in watch if r == "IN"} - set(held)
    for a in corp_actions.between("IN", frm - timedelta(days=60), to, watch_in) if watch_in else []:
        rows[a["id"]] = a
    for a in rows.values():
        out += _action_events(a, held.get(a["symbol"]), frm, to)
    for s, i in held.items():                         # gold bonds: the month they mature, from the symbol
        if instrument_kinds.base(i.get("kind") or instrument_kinds.classify(s, i.get("isin"), i.get("name"))) == "sgb":
            m = instrument_kinds.sgb_maturity(s)
            d = date(int(m[:4]), int(m[5:]), 1) if m else None
            if d and frm <= d <= to:
                out.append(_ev(d, f"{s}: gold bond matures this month", "holdings", "maturity",
                               "Sovereign Gold Bonds mature eight years after issue; the exact day is in the bond's terms. "
                               "Redemption at maturity is exempt for an individual who subscribed at issue.", symbol=s))
    return out


def _action_events(a: dict, item: dict | None, frm: date, to: date) -> list[dict]:
    """The ex-date (and the record date, when it's another day) of one action, with the estimated total of a
    dividend on the shares held today."""
    out = []
    sym = a["symbol"]
    agm = bool(re.search(r"\bAGM\b|annual\s+general\s+meeting", a.get("purpose") or "", re.I))
    total = None
    if a.get("kind") == "dividend" and a.get("amount") and item:
        total = float(item.get("qty") or 0) * float(a["amount"])
    url = f"/research/IN/{sym}"
    ex, rec = _day(a.get("ex_date")), _day(a.get("record_date"))
    what = a.get("text") or a.get("label") or a.get("kind")
    held = " You hold this stock." if item else " On your watchlist."
    if ex and frm <= ex <= to:
        out.append(_ev(ex, f"{sym}: ex-date, {a.get('short') or a.get('label')}", "holdings", f"ex_{a.get('kind')}",
                       f"{what}. Shares bought from today don't get it.{held}", amount=total, symbol=sym, ref=a["id"], url=url))
    if rec and rec != ex and frm <= rec <= to:
        out.append(_ev(rec, f"{sym}: record date, {a.get('short') or a.get('label')}", "holdings", f"record_{a.get('kind')}",
                       f"{what}.{held}", amount=total, symbol=sym, ref=a["id"], url=url))
    if agm and rec and frm <= rec <= to:
        out.append(_ev(rec, f"{sym}: AGM record date", "holdings", "agm",
                       "The record date announced with the company's annual general meeting (AGM): who holds shares on it "
                       f"can vote.{held}", symbol=sym, ref=a["id"], url=url))
    return out


# ---------- other Money pages, through optional hooks ----------
def _hook(module: str, fn: str, *args) -> list:
    """What another Money page's `fn` gives, or [] when the page isn't there or fails."""
    try:
        mod = importlib.import_module(f"app.{module}")
    except ImportError:
        return []
    f = getattr(mod, fn, None)
    if not callable(f):
        return []
    try:
        got = f(*args)
    except Exception as e:
        print("money calendar hook failed:", module, fn, type(e).__name__)
        return []
    return got if isinstance(got, list) else []


def hook_events(uid: str, frm: date, to: date) -> list[dict]:
    """Each hook gives [{date, title, detail?, amount?, kind?, id?}]; anything else in it is left out."""
    days = max(1, min(800, (to - date.today()).days + 1))
    out = []
    for module, fn, cat in HOOKS:
        for x in _hook(module, fn, uid, days)[:500]:
            d = _day(x.get("date")) if isinstance(x, dict) else None
            if not d or not frm <= d <= to or not isinstance(x.get("title"), str) or not x["title"].strip():
                continue
            kind = re.sub(r"[^a-z0-9_]", "", str(x.get("kind") or module).lower())[:30] or module
            out.append(_ev(d, x["title"].strip(), cat, kind, str(x.get("detail") or "")[:400],
                           amount=x.get("amount") if isinstance(x.get("amount"), (int, float)) and not isinstance(x.get("amount"), bool) else None,
                           ref=f"{module}:{str(x.get('id') or x['title'])[:40]}", url=x.get("url") if str(x.get("url") or "").startswith("/") else None))
    return out


# ---------- the user's own events ----------
def _shift_month(d: date, n: int, day: int) -> date:
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    return date(y, m, min(day, monthrange(y, m)[1]))


def occurrences(e: dict, frm: date, to: date) -> list[date]:
    """The days one event falls on in the window: once, every month (the 31st falls back to the month's last day)
    or every year (29 Feb to 28 Feb)."""
    start = _day(e["date"])
    if not start or start > to:
        return []
    rep = e.get("repeat") or "none"
    if rep == "none":
        return [start] if start >= frm else []
    out = []
    if rep == "monthly":
        n = max(0, (frm.year - start.year) * 12 + frm.month - start.month - 1)
        while len(out) < 500:
            d = _shift_month(start, n, start.day)
            if d > to:
                break
            if d >= frm:
                out.append(d)
            n += 1
    else:
        for y in range(max(start.year, frm.year), to.year + 1):
            d = date(y, start.month, min(start.day, monthrange(y, start.month)[1]))
            if frm <= d <= to and d >= start:
                out.append(d)
    return out


def custom_events(data: dict, frm: date, to: date) -> list[dict]:
    out = []
    for e in data["events"]:
        for d in occurrences(e, frm, to):
            rep = {"monthly": " Repeats every month.", "yearly": " Repeats every year."}.get(e.get("repeat") or "none", "")
            out.append({**_ev(d, e["title"], "custom", "custom", (e.get("note") or "") + rep, amount=e.get("amount"), ref=e["id"]),
                        "event_id": e["id"], "repeat": e.get("repeat") or "none"})
    return out


# ---------- everything together ----------
def events(uid: str, frm: date, to: date, cats: set[str] | None = None, data: dict | None = None) -> list[dict]:
    """Every event in the window, by date, in the categories asked for. A part that fails is left out, never the
    whole calendar."""
    cats = set(cats or CATS)
    data = data if data is not None else load(uid)
    out: list[dict] = []
    parts = []
    if "tax" in cats:
        parts.append(lambda: tax_between(frm, to))
    if "holdings" in cats:
        parts.append(lambda: holdings_events(uid, frm, to))
    if cats & {"money", "tax"}:
        parts.append(lambda: [e for e in hook_events(uid, frm, to) if e["cat"] in cats])
    if "custom" in cats:
        parts.append(lambda: custom_events(data, frm, to))
    for p in parts:
        try:
            out += p()
        except Exception as e:
            print("money calendar part failed:", type(e).__name__)
    # an advance-tax page's own instalments (with amounts) stand in for the plain dates
    own = {e["date"] for e in out if e["cat"] == "tax" and e["kind"] != "advance_tax" and "advance" in e["kind"]}
    out = [e for e in out if not (e["kind"] == "advance_tax" and e["date"] in own)]
    seen, uniq = set(), []
    for e in sorted(out, key=lambda e: (e["date"], CATS.index(e["cat"]), e["title"])):
        if e["id"] not in seen:
            seen.add(e["id"])
            uniq.append(e)
    return uniq[:MAX_LIST]


# ---------- the feed (ICS) ----------
def _ics_text(s: str) -> str:
    return re.sub(r"\r\n|\r|\n", r"\\n", str(s or "").replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,"))


def _fold(line: str) -> str:
    """Lines of at most 75 bytes, continued with a space (RFC 5545 3.1), never splitting a character."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not out else 74):
            out.append(cur)
            cur = ""
        cur += ch
    out.append(cur)
    return "\r\n ".join(out)


def to_ics(evs: list[dict], amounts: bool, now: datetime | None = None) -> str:
    """The events as an iCalendar file: all-day events, each with a stable id so a calendar app updates it in place.
    The user's amounts are left out unless `amounts`."""
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//StratLab//Money calendar//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             "X-WR-CALNAME:StratLab money calendar", "X-WR-TIMEZONE:Asia/Kolkata", "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
             "X-PUBLISHED-TTL:PT12H"]
    for e in evs:
        d = date.fromisoformat(e["date"])
        desc = e.get("detail") or ""
        if amounts and e.get("amount") is not None:
            desc = f"Amount: {_money(e['amount'])}. {desc}"
        uid = hashlib.sha256(e["id"].encode()).hexdigest()[:32]
        lines += ["BEGIN:VEVENT", f"UID:{uid}@stratlab.studio", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}", f"SUMMARY:{_ics_text(public_text(e['title']))}",
                  f"DESCRIPTION:{_ics_text(public_text(desc.strip()))}", f"CATEGORIES:{_ics_text(CAT_NAMES[e['cat']])}",
                  "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def new_feed(uid: str, amounts: bool) -> dict:
    """A new private link, the old one (if any) turned off."""
    data = load(uid)
    if data["feed"]:
        db.delete_setting(FEED_KEY + _hash(data["feed"]["token"]))
    token = secrets.token_urlsafe(32)
    db.set_setting(FEED_KEY + _hash(token), uid)
    data["feed"] = {"token": token, "amounts": bool(amounts), "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    save(uid, data)
    return data["feed"]


def revoke_feed(uid: str):
    data = load(uid)
    if data["feed"]:
        db.delete_setting(FEED_KEY + _hash(data["feed"]["token"]))
        data["feed"] = None
        save(uid, data)


def feed_owner(token: str) -> str | None:
    """The user a feed token belongs to, or None (a made-up, old or turned-off one)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token or ""):
        return None
    uid = db.get_setting(FEED_KEY + _hash(token))
    if not uid:
        return None
    feed = load(uid)["feed"]
    return uid if feed and secrets.compare_digest(feed["token"], token) else None


# ---------- reminders ----------
def reminder_text(evs: list[dict], days: int) -> str:
    when = "tomorrow" if days == 1 else f"in {days} days"
    lines = [f"Coming up {when}, on {date.fromisoformat(evs[0]['date']):%a %d %b %Y}:"]
    lines += [f"- {public_text(e['title'])}" for e in evs[:20]]
    if len(evs) > 20:
        lines.append(f"…and {len(evs) - 20} more.")
    lines.append("Dates as the law sets them or the companies announced them. Not advice.")
    return "\n".join(lines)


def _send(profile: dict, channel: str, subject: str, text: str) -> list[str]:
    """Through the alerts' own channels, only the ones the user picked here."""
    from . import alerts
    want = {"email", "push"} if channel == "both" else {channel}
    jobs = [(c, j) for c, j in alerts.jobs_for(profile, subject, text, "/money/calendar") if c in want]
    sent = []
    for c, j in jobs:
        try:
            j()
            sent.append(c)
        except Exception as e:
            print("money calendar reminder failed:", c, type(e).__name__)
    return sent


def send_reminders(today: date, send=_send) -> int:
    """One message per user with reminders on, listing their events `days` from today in the categories they chose.
    Only for plans with reminders."""
    sent = 0
    for k, raw in db.all_settings_with_prefix(KEY):
        uid = k[len(KEY):]
        if not uid or ":" in uid:
            continue
        r = clean_reminders(db.json_value(raw, {}).get("reminders"))
        if not r["on"] or not r["cats"]:
            continue
        try:
            profile = db.get_profile(uid)
            if not allows(access_plan(profile), "money_reminders"):
                continue
            target = today + timedelta(days=r["days"])
            evs = events(uid, target, target, set(r["cats"]))
            if evs and send(profile, r["channel"], f"StratLab: {len(evs)} money date{'s' if len(evs) != 1 else ''} coming up",
                            reminder_text(evs, r["days"])):
                sent += 1
        except Exception as e:
            print("money calendar reminders:", type(e).__name__)
    return sent


class Job:
    """Sends the day's reminders once, after REMIND_AT India time; the day is marked in the database first."""

    def __init__(self, send=_send):
        self.send = send
        self.last: str | None = None
        self.status = {"last_run": None, "sent": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="money-calendar").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = type(e).__name__
                print("money calendar job:", type(e).__name__)
            time.sleep(300)

    def tick(self, now: datetime) -> int:
        local = now.astimezone(IST)
        day = local.date().isoformat()
        if local.strftime("%H:%M") < REMIND_AT or self.last == day:
            return 0
        self.last = day
        if db.get_setting(JOB_KEY) == day:
            return 0
        db.set_setting(JOB_KEY, day)
        n = send_reminders(local.date(), self.send)
        self.status.update(last_run=now.isoformat(), sent=n, last_error=None)
        return n


# ---------- the API ----------
router = APIRouter(prefix="/money/calendar", tags=["money"])
_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()


def _limit(key: str, times: int, per: float, message: str):
    now = time.time()
    with _hits_lock:
        hits = [t for t in _hits.get(key, []) if now - t < per]
        if len(hits) >= times:
            _err(429, "slow_down", message)
        _hits[key] = hits + [now]
        if len(_hits) > 20000:
            _hits.clear()


def _ok(data) -> JSONResponse:
    return JSONResponse(content=data)


def _today() -> date:
    return datetime.now(IST).date()


def _reminders_allowed(profile) -> bool:
    return allows(profile["_plan"], "money_reminders")


def view(profile, start: date, end: date, cats: set[str] | None = None) -> dict:
    uid = profile["id"]
    data = load(uid)
    feed = data["feed"]
    return {"events": events(uid, start, end, cats, data), "start": start.isoformat(), "end": end.isoformat(),
            "today": _today().isoformat(), "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "cats": [{"id": c, "label": CAT_NAMES[c]} for c in CATS],
            "own": [e for e in data["events"]], "own_max": MAX_EVENTS,
            "feed": {"path": f"/money/calendar/feed/{feed['token']}.ics", "amounts": feed["amounts"], "created_at": feed.get("created_at")} if feed else None,
            "reminders": data["reminders"], "reminders_allowed": _reminders_allowed(profile),
            "reminders_plan": PLANS[FEATURE_PLAN["money_reminders"]]["name"], "remind_days": list(REMIND_DAYS), "notes": NOTES}


@router.get("")
def calendar(start: str | None = Query(None, max_length=10), end: str | None = Query(None, max_length=10),
             cats: str | None = Query(None, max_length=60), profile=Depends(current_profile)):
    """The user's money dates between two days (by default the past week and the next 90 days): tax dates, results
    and corporate actions for their holdings and watchlist, the other Money pages' dates and their own events."""
    today = _today()
    s = _day(start) if start else today - timedelta(days=7)
    e = _day(end) if end else today + timedelta(days=90)
    if not s or not e or e < s:
        _err(400, "bad_dates", "Pick a start date on or before the end date.")
    if (e - s).days > MAX_SPAN:
        _err(400, "too_long", f"Ask for at most {MAX_SPAN} days at a time.")
    if s < today - timedelta(days=3 * 366) or e > today + timedelta(days=5 * 366):
        _err(400, "out_of_range", "The calendar covers the last three years and the next five.")
    want = {c for c in (cats or "").split(",") if c in CATS} or None
    return _ok(view(profile, s, e, want))


class EventReq(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    title: str = Field(min_length=1, max_length=80)
    note: str = Field("", max_length=200)
    amount: float | None = Field(None, ge=0, le=1e12)
    repeat: str = Field("none", pattern="^(none|monthly|yearly)$")


def _clean_event(req: EventReq, eid: str) -> dict:
    d = _day(req.date)
    if not d or not date(2000, 1, 1) <= d <= date(2100, 12, 31):
        _err(400, "bad_date", "That date isn't a real day.")
    title = " ".join(req.title.split())
    if not title:
        _err(400, "no_title", "Give the event a name.")
    return {"id": eid, "date": d.isoformat(), "title": title[:80], "note": " ".join(req.note.split())[:200],
            "amount": round(req.amount, 2) if req.amount else None, "repeat": req.repeat}


@router.post("/events")
def add_event(req: EventReq, profile=Depends(current_profile)):
    """Add one of the user's own dates (an FD maturing, a premium, a birthday gift), once or repeating."""
    _limit(f"edit:{profile['id']}", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    data = load(profile["id"])
    if len(data["events"]) >= MAX_EVENTS:
        _err(400, "too_many", f"The calendar keeps up to {MAX_EVENTS} of your own events. Delete one first.")
    data["events"].append(_clean_event(req, uuid.uuid4().hex[:16]))
    save(profile["id"], data)
    return _ok(view(profile, _today() - timedelta(days=7), _today() + timedelta(days=90)))


@router.put("/events/{eid}")
def edit_event(eid: str, req: EventReq, profile=Depends(current_profile)):
    _limit(f"edit:{profile['id']}", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    data = load(profile["id"])
    if not any(e["id"] == eid for e in data["events"]):
        _err(404, "not_found", "That event isn't in your calendar any more.")
    data["events"] = [_clean_event(req, eid) if e["id"] == eid else e for e in data["events"]]
    save(profile["id"], data)
    return _ok(view(profile, _today() - timedelta(days=7), _today() + timedelta(days=90)))


@router.delete("/events/{eid}")
def delete_event(eid: str, profile=Depends(current_profile)):
    data = load(profile["id"])
    if not any(e["id"] == eid for e in data["events"]):
        _err(404, "not_found", "That event isn't in your calendar any more.")
    data["events"] = [e for e in data["events"] if e["id"] != eid]
    save(profile["id"], data)
    return {"deleted": True}


class FeedReq(BaseModel):
    amounts: bool = False


@router.post("/feed")
def make_feed(req: FeedReq, profile=Depends(current_profile)):
    """A new private feed link (any older one stops working). Amounts are left out unless asked for."""
    _limit(f"feed:{profile['id']}", 20, 3600, "That's a lot of new links in an hour. Try again a little later.")
    feed = new_feed(profile["id"], req.amounts)
    return _ok({"path": f"/money/calendar/feed/{feed['token']}.ics", "amounts": feed["amounts"], "created_at": feed["created_at"]})


@router.put("/feed")
def feed_settings(req: FeedReq, profile=Depends(current_profile)):
    """Whether the feed shows the user's amounts. The link stays the same."""
    data = load(profile["id"])
    if not data["feed"]:
        _err(404, "no_feed", "Make a feed link first.")
    data["feed"]["amounts"] = req.amounts
    save(profile["id"], data)
    f = data["feed"]
    return _ok({"path": f"/money/calendar/feed/{f['token']}.ics", "amounts": f["amounts"], "created_at": f.get("created_at")})


@router.delete("/feed")
def delete_feed(profile=Depends(current_profile)):
    """Turn the feed link off: calendars subscribed to it stop getting updates."""
    revoke_feed(profile["id"])
    return {"deleted": True}


@router.get("/feed/{token}.ics")
def feed(token: str, request: Request):
    """The private feed, for a calendar app: no sign-in, the token is the key. Limited per link."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,80}", token or ""):
        _err(404, "not_found", "No calendar at this link.")
    _limit(f"ics:{_hash(token)}", *FEED_RATE, "This calendar link was asked for too often. Try again later.")
    uid = feed_owner(token)
    if not uid:
        _err(404, "not_found", "No calendar at this link. It may have been turned off.")
    today = _today()
    data = load(uid)
    body = to_ics(events(uid, today - timedelta(days=FEED_BEHIND), today + timedelta(days=FEED_AHEAD), None, data), data["feed"]["amounts"])
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "private, max-age=900", "Content-Disposition": 'inline; filename="stratlab-money.ics"',
                             "X-Robots-Tag": "noindex"})


class RemindReq(BaseModel):
    on: bool
    days: int = Field(3, ge=1, le=14)
    channel: str = Field("both", pattern="^(email|push|both)$")
    cats: list[str] = Field(default_factory=lambda: list(CATS), max_length=len(CATS))


@router.put("/reminders")
def reminders(req: RemindReq, profile=Depends(current_profile)):
    """Reminders a few days before each date, by email or phone notification, for the categories picked (Basic and up)."""
    if req.on and not _reminders_allowed(profile):
        _err(402, "upgrade_required", f"Money calendar reminders are on the {PLANS[FEATURE_PLAN['money_reminders']]['name']} plan.")
    if req.days not in REMIND_DAYS:
        _err(400, "bad_days", "Pick 1, 2, 3, 7 or 14 days before.")
    data = load(profile["id"])
    data["reminders"] = clean_reminders({"on": req.on, "days": req.days, "channel": req.channel, "cats": [c for c in req.cats if c in CATS]})
    save(profile["id"], data)
    return _ok({"reminders": data["reminders"]})


@router.delete("")
def delete_all(profile=Depends(current_profile)):
    """Delete my money calendar: my own events, the feed link and the reminder settings, at once."""
    delete(profile["id"])
    return {"deleted": True}
