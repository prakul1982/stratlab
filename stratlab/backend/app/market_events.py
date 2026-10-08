"""Market events calendar: one dated list of the scheduled events traders and investors plan around, each from the
body that sets it, with the published figure once it is out (never a forecast).

- The central bank's monetary policy meetings (the MPC): its published schedule for the year, the decision day with
  the repo rate from its policy statement, and the minutes (due by law on the 14th day after a meeting).
- India's data releases (CPI inflation, industrial output and GDP): the statistics ministry's advance release
  calendar, with the headline figure read from each press release once it is out.
- The US Fed's decisions (the FOMC's published calendar, with the target range from each statement) and the US CPI
  and jobs reports (the labour statistics bureau's release schedule), with their India times.
- Index changes: the index provider's press releases on stocks going in and out of its main indices, with the day
  they take effect; the stocks get a badge on their company pages.
- Monthly and weekly F&O expiries and exchange holidays, from the contracts and the holiday list the app already
  keeps (worked out when asked, never stored twice).
- Anything without a published calendar (the Budget) is added by the admins, with its official link.

Results days, dividends and F&O contract changes have their own calendars (results.py, corp_actions.py,
fo_changes.py); the page links to them rather than copying them.

Kept in app_settings: what each source last gave (mktevents:cal:state, in the market store) and the admins' own
events (mktevents:cal:custom). Each user's choices (mktevents:user:<uid>): reminders (Basic and up) by the alerts'
channels, the kinds they want, how many days before, and whether the events also go into their Money calendar and
its feed. Dates and published figures only; nothing here says what a release will show or what to do about it."""
import calendar as _cal
import hashlib
import html as _html
import io
import json
import re
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import db
from .intel.filings import ist_now
from .intel.net import BROWSER_UA, SourceError, TTLCache
from .newsletter import job as news_job

IST, NY = ZoneInfo("Asia/Kolkata"), ZoneInfo("America/New_York")
KEY = "mktevents:cal:state"          # {"rbi": {...}, "fed": {...}, "us_data": {...}, "india_data": {...}, "index": {...}}
CUSTOM_KEY = "mktevents:cal:custom"  # [event] the admins added (the Budget, anything without a calendar)
USER_KEY = "mktevents:user:"         # mktevents:user:<uid> = {"remind", "kinds", "days", "money_calendar", "sent"}

KINDS = {"rbi": "RBI policy", "india": "India data", "us": "US Fed and data", "budget": "Budget and government",
         "index": "Index changes", "expiry": "F&O expiries", "holiday": "Exchange holidays"}
REMIND_DAYS = (0, 1, 2, 7)           # 0: on the morning of the day
MAX_SENT = 400
KEEP_BACK = 400                      # days of past events kept
VIEW_BACK, VIEW_AHEAD = 180, 400     # what the page shows around today
BADGE_AFTER = 30                     # an index badge stays this long after the change takes effect
PAUSE = 1.5                          # seconds between two requests to one site
PDF_PAGES = 60
INDEX_PDFS_PER_RUN, FIGURE_PDFS_PER_RUN, STATEMENTS_PER_RUN = 3, 3, 2

RBI_LIST = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx"
RBI_PR = "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid={}"
FED_CAL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FED_BASE = "https://www.federalreserve.gov"
BLS_ICS = "https://www.bls.gov/schedule/news_release/bls.ics"
BLS_UA = "StratLab/1.0 (market events calendar; +https://stratlab.studio)"   # the bureau asks robots to say who they are
MOSPI_API = "https://www.mospi.gov.in/api/"
MOSPI_SITE = "https://www.mospi.gov.in/"
INDEX_LIST = "https://www.niftyindices.com/press-release"
INDEX_BASE = "https://www.niftyindices.com"

SOURCES = {"rbi": "Central bank (MPC)", "india_data": "Statistics ministry", "fed": "US Fed (FOMC)",
           "us_data": "US labour statistics", "index": "Index provider"}
NOTE = ("Dates are as each body publishes them: the central bank's MPC schedule and policy statements, the statistics "
        "ministry's advance release calendar and press releases, the US Fed's FOMC calendar and statements, the US "
        "labour statistics bureau's release schedule and the index provider's press releases. A data release set for a "
        "weekend comes on the next working day; any date can change, and the body's own page has the last word. "
        "Figures are the published ones, never a forecast. Facts, not advice.")

# the indices whose changes are kept (the provider's own names), the first ones first on a company's badge
MAIN_INDICES = ("Nifty 50", "Nifty Next 50", "Nifty Bank", "Nifty Financial Services", "Nifty Midcap Select", "Nifty IT",
                "Nifty 100", "Nifty 200", "Nifty Midcap 50", "Nifty Midcap 100", "Nifty Midcap 150", "Nifty Smallcap 50",
                "Nifty Smallcap 100", "Nifty Smallcap 250", "Nifty 500", "Nifty Auto", "Nifty FMCG", "Nifty Metal",
                "Nifty Pharma", "Nifty Realty", "Nifty Energy", "Nifty PSU Bank", "Nifty Private Bank", "Nifty Media",
                "Nifty Oil & Gas", "Nifty Healthcare Index", "Nifty Consumer Durables", "Nifty India Defence")
BADGE_INDICES = MAIN_INDICES[:15]
MONTHS = {m.lower(): i for i, m in enumerate(_cal.month_name) if m} | {m.lower(): i for i, m in enumerate(_cal.month_abbr) if m}
MONTH_RX = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

_cache = TTLCache(max_items=20)
_lock = threading.Lock()


# ---------- small helpers ----------
def _month(name: str) -> int | None:
    n = (name or "").strip().lower().rstrip(".")
    return MONTHS.get(n) or MONTHS.get(n[:3])


def _iso(d) -> str | None:
    return d.isoformat() if isinstance(d, date) else None


def _day(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def nice(d) -> str:
    """"7 Oct 2026"."""
    d = d if isinstance(d, date) else _day(d)
    return f"{d.day} {d:%b %Y}" if d else ""


def _short(d) -> str:
    d = d if isinstance(d, date) else _day(d)
    return f"{d.day} {d:%b}" if d else ""


def plain(html_text: str) -> str:
    """The words of an HTML page, one space between them."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html_text or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


def _id(*parts) -> str:
    return ":".join(str(p) for p in parts)[:120]


def _pct(v: float | None, places: int = 2) -> str | None:
    return None if v is None else f"{v:.{places}f}%"


def ist_time(day: date, hhmm: str, tz: ZoneInfo) -> tuple[date, str]:
    """(the India date, "HH:MM") of a local time somewhere else."""
    h, m = map(int, hhmm.split(":"))
    t = datetime(day.year, day.month, day.day, h, m, tzinfo=tz).astimezone(IST)
    return t.date(), t.strftime("%H:%M")


def mark_weekend(e: dict) -> dict:
    """A dated event that falls on a Saturday or Sunday says so (`weekend`, and a sentence in its detail): the exchanges
    are shut that day. Holidays and expiries are about the calendar itself and are left alone."""
    d = _day(e.get("date"))
    if d and d.weekday() >= 5 and e.get("kind") not in ("holiday", "expiry"):
        name = f"{d:%A}"
        e["weekend"] = name
        e["detail"] = ((e.get("detail") or "").rstrip() + f" This day is a {name}, so the exchanges are closed.").strip()
    return e


def _weekday_after(d: date) -> date:
    """A weekend day moved to the Monday after (a data release set for a weekend comes on the next working day)."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


# ---------- the central bank: MPC schedule, statements, minutes ----------
def read_rbi_list(html_text: str) -> list[dict]:
    """[{prid, date, title}] from the press-release list: day headings, each followed by its releases."""
    out, day = [], None
    for m in re.finditer(r"tableheader[^>]*>\s*<b>\s*([A-Z][a-z]{2} \d{1,2}, \d{4})|prid=(\d+)['\"]?>([^<]+)<", html_text or ""):
        if m.group(1):
            try:
                day = datetime.strptime(m.group(1), "%b %d, %Y").date()
            except ValueError:
                day = None
        elif day:
            out.append({"prid": m.group(2), "date": day.isoformat(), "title": re.sub(r"\s+", " ", _html.unescape(m.group(3))).strip()})
    return out


_SPAN = re.compile(rf"({MONTH_RX})\s+(\d{{1,2}})((?:\s*,\s*\d{{1,2}})*\s*(?:and|&|to|-|–)\s*)(?:({MONTH_RX})\s+)?(\d{{1,2}}),?\s+(\d{{4}})", re.I)


def meeting_span(text: str) -> tuple[date, date] | None:
    """(first day, last day) of a meeting written "October 5, 6 and 7, 2026", "August 3 to 5, 2026" or "September 29
    to October 1, 2025"."""
    m = _SPAN.search(text or "")
    if not m:
        return None
    y = int(m.group(6))
    m1, m2 = _month(m.group(1)), _month(m.group(4) or m.group(1))
    try:
        start = date(y - (1 if m2 < m1 else 0), m1, int(m.group(2)))
        end = date(y, m2, int(m.group(5)))
    except (TypeError, ValueError):
        return None
    return (start, end) if 0 <= (end - start).days <= 7 else None


def read_rbi_schedule(text: str) -> list[dict]:
    """The meetings a schedule release lists: [{start, end}]."""
    out, seen = [], set()
    for m in _SPAN.finditer(plain(text)):
        span = meeting_span(m.group(0))
        if span and span not in seen:
            seen.add(span)
            out.append({"start": span[0].isoformat(), "end": span[1].isoformat()})
    return out


def read_rbi_statement(text: str) -> dict | None:
    """{"repo": 5.25, "move": "unchanged" | "cut" | "raised" | None} from a policy statement's resolution."""
    t = plain(text)
    m = re.search(r"policy repo rate[^.]{0,260}?\b(?:at|to)\s+(\d+(?:\.\d+)?)\s*per\s*cent", t, re.I)
    if not m:
        return None
    before = t[max(0, m.start() - 120):m.end()].lower()
    move = ("unchanged" if "unchanged" in before or "keep" in before or "maintain" in before
            else "cut" if re.search(r"\b(reduc|cut|lower)", before) else "raised" if re.search(r"\b(increas|rais|hike)", before) else None)
    return {"repo": float(m.group(1)), "move": move}


def _rbi_kind(title: str) -> str | None:
    if re.search(r"Meeting Schedule of the Monetary Policy Committee|Schedule of (?:the )?(?:meetings of )?(?:the )?Monetary Policy Committee", title, re.I):
        return "schedule"
    if re.match(r"\s*Monetary Policy Statement", title, re.I):
        return "statement"
    if re.match(r"\s*Minutes of the Monetary Policy Committee", title, re.I):
        return "minutes"
    return None


def _rbi_months(today: date, deep: bool) -> list[tuple[int, int]]:
    """The months of press releases to read: this one and the last; with `deep`, back to the last January (the
    year's schedule comes out in February or March)."""
    out = [(today.year, today.month)]
    y, m = today.year, today.month
    back = (m - 3) % 12 + 2 if deep else 1
    for _ in range(back):
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
        out.append((y, m))
    return out


def refresh_rbi(web, st: dict, today: date) -> dict:
    """Read this month's and last month's press releases (back to February when the year's schedule isn't kept yet)
    and each schedule, policy statement and minutes not read before."""
    part = dict(st or {})
    meetings = {m["end"]: m for m in part.get("meetings") or [] if isinstance(m, dict) and m.get("end")}
    read = set(part.get("read") or [])
    have_ahead = any(_day(m["end"]) and _day(m["end"]) > today + timedelta(days=60) for m in meetings.values())
    month = today.strftime("%Y-%m")
    deep = not have_ahead and part.get("backscan") != month          # at most one long look back a month
    items: list[dict] = []
    for i, (y, mo) in enumerate(_rbi_months(today, deep)):
        page = web.rbi_month(y, mo, first=i == 0)
        items += read_rbi_list(page)
    for it in sorted(items, key=lambda x: x["date"]):
        kind = _rbi_kind(it["title"])
        if not kind or it["prid"] in read:
            continue
        url = RBI_PR.format(it["prid"])
        if kind == "minutes":
            span = meeting_span(it["title"])
            if span:
                m = meetings.setdefault(span[1].isoformat(), {"start": span[0].isoformat(), "end": span[1].isoformat()})
                m.update(minutes=it["date"], minutes_url=url)
            read.add(it["prid"])
            continue
        page = web.text(url)
        if kind == "schedule":
            for s in read_rbi_schedule(page):
                meetings.setdefault(s["end"], {}).update(s)
        else:
            span = meeting_span(it["title"]) or meeting_span(plain(page)[:600])
            got = read_rbi_statement(page)
            if span:
                m = meetings.setdefault(span[1].isoformat(), {"start": span[0].isoformat(), "end": span[1].isoformat()})
                m.update(decided=it["date"], statement_url=url, **(got or {}))
        read.add(it["prid"])
    cut = (today - timedelta(days=KEEP_BACK)).isoformat()
    part["meetings"] = sorted((m for m in meetings.values() if m["end"] >= cut), key=lambda m: m["end"])
    part["read"] = sorted(read)[-300:]
    if deep:
        part["backscan"] = month
    return part


# ---------- the US Fed: FOMC calendar and statements ----------
def _frac(s: str) -> float | None:
    """3.75 from "3-3/4", 4.0 from "4", 0.25 from "1/4"."""
    m = re.fullmatch(r"(\d+)(?:-(\d)/(\d))?|(\d)/(\d)", (s or "").strip())
    if not m:
        return None
    if m.group(4):
        return int(m.group(4)) / int(m.group(5))
    return int(m.group(1)) + (int(m.group(2)) / int(m.group(3)) if m.group(2) else 0)


def read_fomc(html_text: str) -> list[dict]:
    """The scheduled meetings on the FOMC calendar page: [{start, end, sep, statement_url, minutes}]. Notation votes
    and unscheduled meetings are left out."""
    out = []
    for blk in re.split(r'<div class="panel panel-default">', html_text or "")[1:]:
        h = re.search(r"(\d{4}) FOMC Meetings", blk)
        if not h:
            continue
        year = int(h.group(1))
        rows = re.split(r'<div class="(?:fomc-meeting--shaded )?row fomc-meeting', blk)[1:]
        for r in rows:
            mo = re.search(r"fomc-meeting__month[^>]*>\s*<strong>([^<]+)</strong>", r)
            dt = re.search(r'fomc-meeting__date[^>]*>([^<]+)<', r)
            if not mo or not dt:
                continue
            days = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*(\*)?\s*", dt.group(1))
            if not days:
                continue                                  # "22 (notation vote)", "(unscheduled)"
            names = [n for n in re.split(r"[/-]", mo.group(1)) if n.strip()]
            m1, m2 = _month(names[0]), _month(names[-1])
            if not m1 or not m2:
                continue
            try:
                start, end = date(year, m1, int(days.group(1))), date(year, m2, int(days.group(2)))
            except ValueError:
                continue
            st = re.search(r'href="(/newsevents/pressreleases/monetary\d{8}a\.htm)"', r)
            mins = re.search(r"\(Released\s+([A-Z][a-z]+ \d{1,2}, \d{4})\)", r)
            out.append({"start": start.isoformat(), "end": end.isoformat(), "sep": bool(days.group(3)),
                        "statement_url": FED_BASE + st.group(1) if st else None,
                        "minutes": datetime.strptime(mins.group(1), "%B %d, %Y").date().isoformat() if mins else None})
    return sorted(out, key=lambda m: m["end"])


def read_fed_statement(text: str) -> dict | None:
    """{"low": 3.75, "high": 4.0, "move": "raised" | "cut" | "unchanged"} from an FOMC statement."""
    t = plain(text)
    m = re.search(r"target range for the federal funds rate[^.]{0,120}?\b(?:at|to)\s+(\d+(?:-\d/\d)?)\s+to\s+(\d+(?:-\d/\d)?)\s+percent", t, re.I)
    if not m:
        return None
    lo, hi = _frac(m.group(1)), _frac(m.group(2))
    if lo is None or hi is None:
        return None
    before = t[max(0, m.start() - 60):m.start() + 40].lower()
    move = "raised" if "raise" in before else "cut" if "lower" in before else "unchanged" if "maintain" in before else None
    return {"low": lo, "high": hi, "move": move}


def refresh_fed(web, st: dict, today: date) -> dict:
    part = dict(st or {})
    old = {m["end"]: m for m in part.get("meetings") or [] if isinstance(m, dict)}
    meetings = read_fomc(web.text(FED_CAL))
    if not meetings:
        raise ValueError("No meetings found on the FOMC calendar page.")
    budget = STATEMENTS_PER_RUN
    for m in meetings:
        prev = old.get(m["end"]) or {}
        for k in ("low", "high", "move"):
            if prev.get(k) is not None:
                m[k] = prev[k]
    for m in reversed(meetings):                          # the latest statements first
        end = _day(m["end"])
        if m.get("statement_url") and m.get("low") is None and end and today - timedelta(days=200) <= end <= today and budget:
            budget -= 1
            try:
                got = read_fed_statement(web.text(m["statement_url"]))
            except (SourceError, ValueError) as e:            # one statement missing never loses the calendar
                print("market events: FOMC statement unread:", str(e)[:120])
                got = None
            if got:
                m.update(got)
    cut = (today - timedelta(days=KEEP_BACK)).isoformat()
    part["meetings"] = [m for m in meetings if m["end"] >= cut]
    return part


# ---------- US data: the labour statistics bureau's release schedule ----------
US_RELEASES = {"Consumer Price Index": "us_cpi", "Employment Situation": "us_jobs"}


def read_bls_ics(text: str) -> list[dict]:
    """[{kind, date, time}] (New York date and time) for the CPI and jobs reports in the bureau's calendar file."""
    out = []
    for b in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text or "", re.S):
        s = re.search(r"^SUMMARY:(.*?)\r?$", b, re.M)
        d = re.search(r"^DTSTART[^:\r\n]*:(\d{8})(?:T(\d{2})(\d{2}))?", b, re.M)
        kind = US_RELEASES.get((s.group(1).strip() if s else ""))
        if not kind or not d:
            continue
        day = datetime.strptime(d.group(1), "%Y%m%d").date()
        out.append({"kind": kind, "date": day.isoformat(), "time": f"{d.group(2)}:{d.group(3)}" if d.group(2) else "08:30"})
    return sorted(out, key=lambda r: (r["date"], r["kind"]))


def refresh_us_data(web, st: dict, today: date) -> dict:
    rows = read_bls_ics(web.text(BLS_ICS, ua=BLS_UA))
    if not rows:
        raise ValueError("No CPI or jobs releases in the release schedule.")
    cut = (today - timedelta(days=KEEP_BACK)).isoformat()
    old = [r for r in (st or {}).get("releases") or [] if isinstance(r, dict) and r.get("date", "") >= cut and r["date"] < rows[0]["date"]]
    return {**(st or {}), "releases": old + [r for r in rows if r["date"] >= cut]}


# ---------- India data: the statistics ministry's calendar and press releases ----------
INDIA_KINDS = (("cpi", re.compile(r"Consumer Price Index|\bCPI\b", re.I)),
               ("iip", re.compile(r"Index of Industrial Production|\bIIP\b", re.I)),
               ("gdp", re.compile(r"\bGDP\b|Gross Domestic Product", re.I)))
INDIA_TITLES = {"cpi": "India CPI inflation", "iip": "India industrial output (IIP)", "gdp": "India GDP estimates"}
_ORD = rf"(\d{{1,2}})\s*(?:st|nd|rd|th)\s*({MONTH_RX})\b"


def _india_kind(title: str) -> str | None:
    if re.search(r"Services Production|\bISP\b|PLFS|Labour Force", title, re.I):
        return None
    return next((k for k, rx in INDIA_KINDS if rx.search(title)), None)


def read_arc(text: str) -> list[dict]:
    """The CPI, IIP and GDP releases in the advance release calendar: [{kind, title, date, released}] ("released"
    when the calendar says the day it actually came)."""
    t = re.sub(r"\s+", " ", text or "")
    fy = re.search(r"RELEASE CALENDAR\s*\(\s*(\d{4})\s*-\s*\d{2,4}\s*\)", t, re.I) or re.search(r"(\d{4})\s*-\s*\d{2}", t)
    if not fy:
        return []
    first = int(fy.group(1))

    def when(day, mon, year=None):
        mo = _month(mon)
        if not mo:
            return None
        y = int(year) if year else (first if mo >= 4 else first + 1)
        try:
            return date(y, mo, int(day))
        except ValueError:
            return None
    t = re.sub(rf"(?:Released|Launched) on\s+(\d{{1,2}})\s*(?:st|nd|rd|th)?\s+({MONTH_RX})[a-z]*,?\s*(\d{{4}})",
               lambda m: f" @@{_iso(when(m.group(1), m.group(2), m.group(3))) or ''}@@ ", t, flags=re.I)
    marks = list(re.finditer(_ORD, t, re.I))
    out = []
    for i, m in enumerate(marks):
        body = t[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(t)]
        d = when(m.group(1), m.group(2))
        rel = re.search(r"@@(\d{4}-\d{2}-\d{2})@@", body)
        title = re.sub(r"https?://\S+|Advance Release Calendar.*?Press Release Link|(?<!\w)o(?!\w)", " ", body.split("@@")[0])
        title = re.sub(rf"\s\d{{1,2}}\s+{MONTH_RX}\s+\d{{4}}\s*$", " ", re.sub(r"\s+", " ", title)).strip(" -–")
        kind = _india_kind(title)
        if d and kind:
            out.append({"kind": kind, "title": title[:160], "date": d.isoformat(), "released": rel.group(1) if rel else None})
    return out


def read_mospi_releases(data) -> list[dict]:
    """[{kind, date, title, pdf}] from the ministry's list of releases this year."""
    out = []
    for x in (data or {}).get("data") or [] if isinstance(data, dict) else []:
        try:
            d = date(int(x["year"]), int(x["month"]), int(x["day"]))
        except (KeyError, TypeError, ValueError):
            continue
        title = re.sub(r"\s+", " ", str(x.get("title") or "")).strip()
        kind = _india_kind(title)
        link = re.search(r'href="(https?://[^"]+\.pdf)"', str(x.get("description") or ""), re.I)
        pdf = link.group(1) if link else (MOSPI_SITE + x["doc_url"] if str(x.get("doc_url") or "").endswith(".pdf") else None)
        if kind:
            out.append({"kind": kind, "date": d.isoformat(), "title": title[:160], "pdf": pdf})
    return out


def _num(s: str) -> float:
    s = s.replace(" ", "")
    neg = s.startswith("(-)") or s.startswith("-")
    v = float(re.sub(r"^\(-\)|^-", "", s))
    return -v if neg else v


def read_india_figure(kind: str, text: str) -> dict | None:
    """The headline figure of a CPI, IIP or GDP press release: {"value", "label", "period", "previous", "previous_label"}."""
    t = re.sub(r"\s+", " ", text or "")
    if kind == "cpi":
        m = re.search(r"Year-on-year inflation rate based on All India Consumer Price Index.{0,120}?month of (\w+),? (\d{4}).{0,60}?is\s*(-?\d+(?:\.\d+)?)\s*%", t, re.I)
        if not m:
            return None
        row = re.search(r"CPI\s*\(General\)\s+" + r"\s+".join([r"(-?\d+\.\d+)"] * 6), t)
        prev = float(row.group(3)) if row and abs(float(row.group(6)) - float(m.group(3))) < 0.005 else None
        return {"label": "CPI inflation", "value": float(m.group(3)), "period": f"{m.group(1)} {m.group(2)}", "previous": prev,
                "previous_label": "the month before"}
    if kind == "iip":
        m = re.search(r"IIP growth rate for the month of (\w+ \d{4}) is\s*((?:\(-\)\s*)?-?\d+(?:\.\d+)?) percent which was\s*((?:\(-\)\s*)?-?\d+(?:\.\d+)?) percent.{0,40}?in the month of (\w+ \d{4})", t, re.I)
        if not m:
            return None
        return {"label": "IIP growth", "value": _num(m.group(2)), "period": m.group(1), "previous": _num(m.group(3)), "previous_label": m.group(4)}
    if kind == "gdp":
        m = re.search(r"Real GDP has been estimated to grow by\s*(-?\d+(?:\.\d+)?)\s*%\s*in (?:the )?(Q\d|FY)[^,]{0,40}?(\d{4}\s*-\s*\d{2}),?\s*against (?:the )?growth of\s*(-?\d+(?:\.\d+)?)\s*%", t, re.I)
        if not m:
            return None
        fy = re.sub(r"\s", "", m.group(3))
        return {"label": "Real GDP growth", "value": float(m.group(1)), "period": f"{m.group(2)} FY {fy}" if m.group(2) != "FY" else f"FY {fy}",
                "previous": float(m.group(4)), "previous_label": "a year earlier"}
    return None


def refresh_india(web, st: dict, today: date) -> dict:
    """The latest advance release calendar (read again when the ministry posts a new copy, or weekly), this year's
    releases, and the figure of each release in the last 60 days not read yet."""
    part = dict(st or {})
    latest = web.json(MOSPI_API + "documents/get-latest-release-calender")
    doc = (latest or {}).get("data") if isinstance(latest, dict) else None
    if not isinstance(doc, dict) or not doc.get("url"):
        raise ValueError("The ministry didn't say where its release calendar is.")
    stale = (today - (_day(part.get("arc_read")) or date(2000, 1, 1))).days >= 7
    if doc.get("filename") != part.get("arc") or stale or not part.get("calendar"):
        rows = read_arc(web.pdf_text(MOSPI_SITE + doc["url"].lstrip("/")))
        if not rows:
            raise ValueError("No CPI, IIP or GDP dates found in the release calendar.")
        keep = {r["date"]: r for r in part.get("calendar") or [] if isinstance(r, dict) and r.get("date", "") < rows[0]["date"]}
        part["calendar"] = sorted(list(keep.values()) + rows, key=lambda r: r["date"])
        part["arc"], part["arc_read"] = doc.get("filename"), today.isoformat()
    released = []
    for y in sorted({today.year, (today - timedelta(days=45)).year}):
        released += read_mospi_releases(web.json(MOSPI_API + "release-calender/fetch-all-release-calender-Web",
                                                 body={"lang": "en", "page": 1, "limit": 100, "year": y}))
    figures = {r["id"]: r for r in part.get("figures") or [] if isinstance(r, dict) and r.get("id")}
    budget = FIGURE_PDFS_PER_RUN
    for r in sorted(released, key=lambda r: r["date"], reverse=True):
        rid = _id(r["kind"], r["date"])
        d = _day(r["date"])
        if rid in figures or not r.get("pdf") or not d or (today - d).days > 60:
            continue
        if not budget:
            break
        budget -= 1
        fig = read_india_figure(r["kind"], web.pdf_text(r["pdf"], pages=4))
        figures[rid] = {"id": rid, "kind": r["kind"], "date": r["date"], "pdf": r["pdf"], "figure": fig}
    part["releases"] = sorted(released, key=lambda r: r["date"])[-80:]
    cut = (today - timedelta(days=KEEP_BACK)).isoformat()
    part["figures"] = sorted((f for f in figures.values() if f["date"] >= cut), key=lambda f: f["date"])
    part["calendar"] = [r for r in part.get("calendar") or [] if r.get("date", "") >= cut]
    return part


# ---------- index changes: the index provider's press releases ----------
INDEX_WORDS = re.compile(r"replacement|inclusion|exclusion|changes? in (?:the )?(?:\w+ )?indices|reconstitut|demerg|scheme of arrangement", re.I)
INDEX_SKIP = re.compile(r"Nifty IPO|Fixed Income|bond|SME|G-?Sec|T-?Bill|Maturity|launch|Corporate action adjustment|dissemination|Debt|REIT|InvIT", re.I)


def read_index_list(html_text: str) -> list[dict]:
    """[{date, url, title}] from the press-release list, only those about stocks going in or out of indices."""
    out = []
    for m in re.finditer(r'data-date="([^"]+)"[^>]*>\s*<p>[^<]*</p>\s*<a href=[\'"]([^\'"]+)[\'"][^>]*>([^<]+)</a>', html_text or ""):
        title = re.sub(r"\s+", " ", _html.unescape(m.group(3))).strip()
        if not INDEX_WORDS.search(title) or INDEX_SKIP.search(title):
            continue
        try:
            d = datetime.strptime(m.group(1).strip(), "%b %d, %Y").date()
        except ValueError:
            continue
        url = m.group(2) if m.group(2).startswith("http") else INDEX_BASE + "/" + m.group(2).lstrip("/")
        out.append({"date": d.isoformat(), "url": url, "title": title[:200]})
    return out


def _effective(text: str, title: str = "") -> date | None:
    for src in (text[:3000], title):
        m = re.search(rf"(?:effective from|w\.?\s?e\.?\s?f\.?)\s*(?:the\s+)?({MONTH_RX})\s+(\d{{1,2}}),?\s*(\d{{4}})", re.sub(r"\s+", " ", src or ""), re.I)
        if m:
            try:
                return date(int(m.group(3)), _month(m.group(1)), int(m.group(2)))
            except (TypeError, ValueError):
                continue
    return None


def _index_name(raw: str) -> str | None:
    name = re.sub(r"\s+", " ", raw).strip(" :")
    for n in MAIN_INDICES:
        if name.lower() == n.lower() or name.lower() == n.lower().replace(" index", ""):
            return n
    return None


def read_index_changes(text: str, title: str = "") -> dict:
    """{"effective", "sections": [{"index", "in": [[symbol, name]], "out": [...]}]} from a press release's text, for
    the main indices (MAIN_INDICES); the rest are left out."""
    sections, cur, mode = [], None, None
    for line in (text or "").splitlines():
        s = line.strip()
        h = re.match(r"^\d{1,2}\)\s+(Nifty[\w &\-]*?)\s*(?:index)?\s*$", s, re.I)
        if h:
            name = _index_name(h.group(1))
            cur = {"index": name, "in": [], "out": []} if name else None
            if cur:
                sections.append(cur)
            mode = None
            continue
        if re.match(r"^[A-Z]\.\s", s):
            cur, mode = None, None
            continue
        low = s.lower()
        if "being excluded" in low or "are excluded" in low:
            mode = "out"
            continue
        if "being included" in low or "are included" in low:
            mode = "in"
            continue
        if low.startswith("note"):
            mode = None
            continue
        r = re.match(r"^\d{1,3}\s+(.+?)\s+([A-Z0-9][A-Z0-9&\-]{1,19})$", s)
        if cur is not None and mode and r and not r.group(1).lower().startswith("company name"):
            pair = [r.group(2), r.group(1)[:80]]
            if pair not in cur[mode] and len(cur[mode]) < 150:
                cur[mode].append(pair)
    eff = _effective(text, title)
    return {"effective": _iso(eff), "sections": [s for s in sections if s["in"] or s["out"]]}


def refresh_index(web, st: dict, today: date) -> dict:
    part = dict(st or {})
    changes = {c["url"]: c for c in part.get("changes") or [] if isinstance(c, dict) and c.get("url")}
    tried = {k: v for k, v in (part.get("tried") or {}).items() if isinstance(v, int)}
    items = [i for i in read_index_list(web.text(INDEX_LIST)) if (today - date.fromisoformat(i["date"])).days <= 120]
    budget = INDEX_PDFS_PER_RUN
    for it in items:
        if it["url"] in changes or tried.get(it["url"], 0) >= 3 or not budget:
            continue
        budget -= 1
        try:
            got = read_index_changes(web.pdf_text(it["url"]), it["title"])
        except (SourceError, ValueError) as e:
            tried[it["url"]] = tried.get(it["url"], 0) + 1
            print("market events: index release unread:", str(e)[:120])
            continue
        changes[it["url"]] = {"id": hashlib.sha1(it["url"].encode()).hexdigest()[:12], "url": it["url"], "title": it["title"],
                              "announced": it["date"], "effective": got["effective"] or _iso(_effective("", it["title"])),
                              "sections": got["sections"]}
    cut = (today - timedelta(days=KEEP_BACK)).isoformat()
    part["changes"] = sorted((c for c in changes.values() if (c.get("effective") or c["announced"]) >= cut),
                             key=lambda c: (c.get("effective") or c["announced"], c["announced"]))
    part["tried"] = {k: v for k, v in tried.items() if k in {i["url"] for i in items}}
    return part


# ---------- the web, politely ----------
class Web:
    """The few requests the calendar makes: a browser-like client (the bureau's file asks for a named robot), a pause
    between two requests to one site, and every failure as a SourceError."""

    def __init__(self, transport=None, pause: float | None = None, sleep=time.sleep):
        import httpx
        self.http = httpx.Client(timeout=40, follow_redirects=True, transport=transport,
                                 headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-IN,en;q=0.9",
                                          "Accept": "text/html,application/xhtml+xml,application/json,application/pdf,*/*;q=0.8"})
        self.pause = PAUSE if pause is None else pause
        self.sleep = sleep
        self._last: dict[str, float] = {}

    def _send(self, method: str, url: str, **kw):
        import httpx
        host = re.sub(r"^https?://([^/]+).*", r"\1", url)
        wait = self._last.get(host, 0) + self.pause - time.time()
        if wait > 0:
            self.sleep(wait)
        try:
            r = self.http.request(method, url, **kw)
        except httpx.HTTPError as e:
            raise SourceError(host, f"Couldn't reach {host} ({e.__class__.__name__}).", busy=True) from None
        finally:
            self._last[host] = time.time()
        if r.status_code >= 400:
            raise SourceError(host, f"{host} answered {r.status_code}.", busy=r.status_code in (429, 503) or r.status_code >= 500)
        if r.headers.get("content-type", "").startswith("text/html") and "Unauthorised Access" in r.text[:600]:
            raise SourceError(host, f"{host} turned the request away.", busy=True)
        return r

    def text(self, url: str, ua: str | None = None) -> str:
        return self._send("GET", url, headers={"User-Agent": ua} if ua else None).text

    def json(self, url: str, body: dict | None = None):
        r = self._send("POST" if body is not None else "GET", url, json=body,
                       headers={"Referer": "https://mospi.gov.in/release-calendar", "Origin": "https://mospi.gov.in"} if "mospi" in url else None)
        try:
            return r.json()
        except ValueError:
            raise SourceError("data", f"{url[:60]} sent something that isn't data.", busy=True) from None

    def pdf_text(self, url: str, pages: int = PDF_PAGES) -> str:
        data = self._send("GET", url.replace(" ", "%20")).content
        if not data.startswith(b"%PDF"):
            raise ValueError("Not a PDF.")
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:pages])
        except Exception as e:
            raise ValueError(f"The PDF couldn't be read ({type(e).__name__}).") from None

    def rbi_month(self, year: int, month: int, first: bool = False) -> str:
        """The press releases of one month (the list page's own month picker: a form post with its hidden fields)."""
        if first or not getattr(self, "_rbi_form", None):
            page = self.text(RBI_LIST)
            self._rbi_form = dict(re.findall(r'<input type="hidden" name="([^"]+)" id="[^"]+"(?: value="([^"]*)")?', page))
        form = {**self._rbi_form, "hdnYear": str(year), "hdnMonth": str(month)}
        return self._send("POST", RBI_LIST, data=form, headers={"Referer": RBI_LIST}).text


# ---------- reading every source ----------
READERS = (("rbi", refresh_rbi), ("fed", refresh_fed), ("us_data", refresh_us_data), ("india_data", refresh_india),
           ("index", refresh_index))


def load_state() -> dict:
    hit = _cache.get("state")
    if hit is not None:
        return hit
    try:
        st = db.json_value(db.get_setting(KEY), {})
    except Exception:
        st = {}
    _cache.set("state", st, 300)
    return st


def load_custom() -> list[dict]:
    hit = _cache.get("custom")
    if hit is not None:
        return hit
    try:
        got = db.json_value(db.get_setting(CUSTOM_KEY), [])
    except Exception:
        got = []
    got = [e for e in got if isinstance(e, dict) and e.get("id") and _day(e.get("date"))]
    _cache.set("custom", got, 300)
    return got


def refresh(web=None, today: date | None = None, now: datetime | None = None, only: set[str] | None = None) -> dict:
    """Read each source (or those in `only`); keep what each one gave, and for one that failed, its last good copy
    with the error. Returns {"problems": [...], "read": [...]}."""
    today = today or ist_now().date()
    stamp = (now or ist_now()).isoformat(timespec="minutes")
    web = web or Web()
    problems, read = [], []
    with _lock:
        st = db.json_value(db.get_setting(KEY), {})
        for name, fn in READERS:
            if only and name not in only:
                continue
            old = st.get(name) if isinstance(st.get(name), dict) else {}
            try:
                part = fn(web, old, today)
                part.update(as_of=today.isoformat(), checked=stamp, error=None)
                st[name] = part
                read.append(name)
            except (SourceError, ValueError, TypeError, KeyError, AttributeError) as e:
                problems.append(f"{SOURCES[name]}: {str(e)[:160]}")
                st[name] = {**old, "error": str(e)[:200], "tried": stamp}
        st["last_run"] = stamp
        db.set_setting(KEY, json.dumps(st, separators=(",", ":")))
    _cache.clear()
    return {"problems": problems, "read": read}


# ---------- the dated list ----------
def _ev(kind: str, day: date, title: str, detail: str = "", *, eid: str, time_ist: str | None = None, figure: str | None = None,
        previous: str | None = None, url: str | None = None, status: str = "scheduled", **extra) -> dict:
    return {"id": eid, "kind": kind, "date": day.isoformat(), "time": time_ist, "title": title, "detail": detail,
            "figure": figure, "previous": previous, "url": url, "status": status, **extra}


def rbi_events(part: dict, today: date) -> list[dict]:
    out, last_repo = [], None
    for m in sorted(part.get("meetings") or [], key=lambda m: m["end"]):
        start, end = _day(m.get("start")), _day(m.get("end"))
        if not start or not end:
            continue
        repo = m.get("repo")
        fig = f"Repo rate {_pct(repo)}" + (f", {m['move']}" if m.get("move") else "") if repo is not None else None
        prev = f"Before: {_pct(last_repo)}" if repo is not None and last_repo is not None else None
        status = "released" if repo is not None else "scheduled" if end >= today else "awaiting"
        out.append(_ev("rbi", end, "RBI policy decision (MPC)",
                       f"The Monetary Policy Committee meets {_short(start)} to {nice(end)}; the decision and the policy "
                       "statement come on the last day.", eid=_id("rbi", end), figure=fig, previous=prev,
                       url=m.get("statement_url"), status=status))
        if m.get("minutes"):
            out.append(_ev("rbi", _day(m["minutes"]), "RBI MPC minutes", f"Minutes of the {_short(start)} to {nice(end)} meeting.",
                           eid=_id("rbi-min", end), url=m.get("minutes_url"), status="released"))
        else:
            due = end + timedelta(days=14)
            out.append(_ev("rbi", due, "RBI MPC minutes (due)", f"Minutes of the {_short(start)} to {nice(end)} meeting, due by law on "
                           "the 14th day after it.", eid=_id("rbi-min", end), status="scheduled" if due >= today else "awaiting"))
        last_repo = repo                                  # "before" is the meeting just before, or nothing
    return out


def fed_events(part: dict, today: date) -> list[dict]:
    out, last = [], None
    for m in sorted(part.get("meetings") or [], key=lambda m: m["end"]):
        start, end = _day(m.get("start")), _day(m.get("end"))
        if not start or not end:
            continue
        day, at = ist_time(end, "14:00", NY)
        rng = f"{_pct(m['low'])} to {_pct(m['high'])}" if m.get("low") is not None and m.get("high") is not None else None
        fig = f"Target range {rng}" + (f", {m['move']}" if m.get("move") else "") if rng else None
        prev = f"Before: {last}" if rng and last else None
        sep = " With the Summary of Economic Projections." if m.get("sep") else ""
        out.append(_ev("us", day, "US Fed decision (FOMC)",
                       f"The FOMC meets {_short(start)} to {nice(end)} in Washington. The statement comes at 2:00 pm New York "
                       f"time, {at} India time on {nice(day)}.{sep}", eid=_id("fomc", end), time_ist=at, figure=fig, previous=prev,
                       url=m.get("statement_url"), status="released" if rng or (m.get("statement_url") and day < today)
                       else "scheduled" if day >= today else "awaiting"))
        last = rng                                        # "before" is the meeting just before, or nothing
    return out


US_TITLES = {"us_cpi": ("US consumer prices (CPI)", "The US consumer price index for the month before."),
             "us_jobs": ("US jobs report", "US employment and unemployment for the month before (the Employment Situation).")}


def us_events(part: dict, today: date) -> list[dict]:
    out = []
    for r in part.get("releases") or []:
        d = _day(r.get("date"))
        if not d or r.get("kind") not in US_TITLES:
            continue
        day, at = ist_time(d, r.get("time") or "08:30", NY)
        title, what = US_TITLES[r["kind"]]
        out.append(_ev("us", day, title, f"{what} Released at {r.get('time') or '08:30'} New York time, {at} India time.",
                       eid=_id(r["kind"], d), time_ist=at, status="released" if day < today else "scheduled"))
    return out


def _figure_text(f: dict | None) -> tuple[str | None, str | None]:
    """("CPI inflation 4.82% (August 2026)", "The month before: 4.45%") from a release's figure."""
    if not f or f.get("value") is None:
        return None, None
    places = 2 if f.get("label") == "CPI inflation" else 1
    fig = f"{f['label']} {f['value']:.{places}f}% ({f['period']})"
    lab = str(f.get("previous_label") or "before")
    prev = f"{lab[:1].upper()}{lab[1:]}: {f['previous']:.{places}f}%" if f.get("previous") is not None else None
    return fig, prev


def india_events(part: dict, today: date) -> list[dict]:
    out = []
    figures = [f for f in part.get("figures") or [] if isinstance(f, dict)]
    releases = [r for r in part.get("releases") or [] if isinstance(r, dict)]
    for r in part.get("calendar") or []:
        planned = _day(r.get("date"))
        if not planned or r.get("kind") not in INDIA_TITLES:
            continue
        actual = _day(r.get("released"))
        if not actual:   # the ministry's list of releases says when it came
            near = [x for x in releases if x["kind"] == r["kind"] and _day(x["date"]) and abs((_day(x["date"]) - planned).days) <= 6]
            actual = _day(near[0]["date"]) if near else None
        day = actual or _weekday_after(planned)
        moved = (f" Set for {nice(planned)}, a {planned:%A}; released on the next working day." if day != planned and not actual
                 else f" Set for {nice(planned)}; released on {nice(actual)}." if actual and actual != planned else "")
        fig_row = next((f for f in figures if f["kind"] == r["kind"] and _day(f["date"]) and abs((_day(f["date"]) - day).days) <= 6), None)
        fig, prev = _figure_text(fig_row.get("figure") if fig_row else None)
        title = INDIA_TITLES[r["kind"]]
        if r["kind"] == "gdp":
            title = "India GDP: " + re.sub(r"^(?:o\s+)?", "", r.get("title") or "estimates")[:90]
        status = "released" if (actual or fig) and day <= today else "scheduled" if day >= today else "awaiting"
        out.append(_ev("india", day, title, f"{r.get('title') or title}. Press release at 4:00 pm.{moved}", eid=_id(r["kind"], planned),
                       time_ist="16:00", figure=fig, previous=prev, url=fig_row.get("pdf") if fig_row else None, status=status))
    return out


def index_events(part: dict, today: date) -> list[dict]:
    out = []
    for c in part.get("changes") or []:
        eff = _day(c.get("effective")) or _day(c.get("announced"))
        if not eff or not c.get("sections"):
            continue
        names = [s["index"] for s in c["sections"]]
        lines = []
        for s in c["sections"][:6]:
            ins = ", ".join(x[0] for x in s["in"][:8]) + (f" and {len(s['in']) - 8} more" if len(s["in"]) > 8 else "")
            outs = ", ".join(x[0] for x in s["out"][:8]) + (f" and {len(s['out']) - 8} more" if len(s["out"]) > 8 else "")
            lines.append(f"{s['index']}: " + "; ".join(p for p in (f"in {ins}" if ins else "", f"out {outs}" if outs else "") if p))
        more = f" Changes in {len(names) - 6} more indices too." if len(names) > 6 else ""
        title = f"Index changes take effect: {names[0]}" + (f" and {len(names) - 1} more" if len(names) > 1 else "")
        out.append(_ev("index", eff, title, f"Announced on {nice(c['announced'])}, from the start of {nice(eff)}. " + ". ".join(lines) + "." + more,
                       eid=_id("index", c["id"]), url=c.get("url"), status="released" if eff <= today else "scheduled",
                       change=c["id"], symbols=sorted({x[0] for s in c["sections"] for x in s["in"] + s["out"]})[:400]))
    return out


def expiry_events(today: date, listed=None, frm: date | None = None, to: date | None = None) -> list[dict]:
    """The monthly F&O expiry (the listed contracts' when the app has them, else the exchange's rule) and NIFTY's
    weekly ones, from `frm` to `to`. `listed(exchange, name)` gives the listed option expiries (ISO), or nothing."""
    from .fo_changes import rule_expiry
    from .data.calendar import is_trading_day
    frm, to = frm or today - timedelta(days=VIEW_BACK), to or today + timedelta(days=VIEW_AHEAD)
    to = min(to, today + timedelta(days=120))           # expiries further out than the listed contracts would be guesses
    got = []
    try:
        got = [d for d in (listed("NFO", "NIFTY") if listed else []) if isinstance(d, str)]
    except Exception:
        got = []
    out, monthly = [], set()
    y, m = frm.year, frm.month
    while date(y, m, 1) <= to:
        key = f"{y:04d}-{m:02d}"
        mine = sorted(d for d in got if d.startswith(key))
        d = _day(mine[-1]) if mine else rule_expiry(key)
        if d and frm <= d <= to:
            monthly.add(d)
            out.append(_ev("expiry", d, "Monthly F&O expiry", "The month's index and stock futures and options expire (NIFTY, BANKNIFTY "
                           "and the stocks)" + (", as listed." if mine else ". The date is the exchange's rule: the last Tuesday, a "
                                                "day earlier when that is a holiday."), eid=_id("exp-m", d), time_ist="15:30",
                           status="released" if d < today else "scheduled"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    weekly = {_day(d) for d in got} - {None}
    if not weekly:                                       # the rule: every Tuesday, the trading day before on a holiday
        d = frm + timedelta(days=(1 - frm.weekday()) % 7)
        while d <= to:
            e = d
            for _ in range(5):
                try:
                    if is_trading_day("IN", e):
                        break
                except Exception:
                    break
                e -= timedelta(days=1)
            weekly.add(e)
            d += timedelta(days=7)
    for d in sorted(weekly):
        if frm <= d <= to and d not in monthly:
            out.append(_ev("expiry", d, "NIFTY weekly expiry", "NIFTY's weekly options expire" + (", as listed." if got else
                           " (the exchange's rule: Tuesdays, a day earlier on a holiday)."), eid=_id("exp-w", d), time_ist="15:30",
                           status="released" if d < today else "scheduled"))
    return out


def holiday_events(today: date, frm: date | None = None, to: date | None = None) -> list[dict]:
    from .data import calendar as tc
    frm, to = frm or today - timedelta(days=VIEW_BACK), to or today + timedelta(days=VIEW_AHEAD)
    out = []
    try:
        days = tc.holidays("IN", frm, (to - frm).days + 1)
    except Exception:
        days = []
    for iso in days:
        d = _day(iso)
        name = None
        try:
            name = tc.holiday_name("IN", d)
        except Exception:
            pass
        out.append(_ev("holiday", d, f"Exchange holiday{': ' + name if name else ''}", "The exchanges are closed for equities and F&O.",
                       eid=_id("hol", d), status="released" if d < today else "scheduled"))
    return out


def custom_events(today: date) -> list[dict]:
    out = []
    for e in load_custom():
        d = _day(e["date"])
        out.append(_ev(e.get("kind") if e.get("kind") in KINDS else "budget", d, e["title"], e.get("detail") or "", eid=_id("custom", e["id"]),
                       time_ist=e.get("time"), url=e.get("url"), status="released" if d < today else "scheduled", custom=e["id"]))
    return out


def events(today: date | None = None, listed=None, frm: date | None = None, to: date | None = None) -> list[dict]:
    """Every event between `frm` and `to` (by default the last 180 days and the next 400), by date and time. A part that
    fails is left out, never the whole list."""
    today = today or ist_now().date()
    frm, to = frm or today - timedelta(days=VIEW_BACK), to or today + timedelta(days=VIEW_AHEAD)
    st = load_state()
    parts = [lambda: rbi_events(st.get("rbi") or {}, today), lambda: fed_events(st.get("fed") or {}, today),
             lambda: us_events(st.get("us_data") or {}, today), lambda: india_events(st.get("india_data") or {}, today),
             lambda: index_events(st.get("index") or {}, today), lambda: expiry_events(today, listed, frm, to),
             lambda: holiday_events(today, frm, to), lambda: custom_events(today)]
    out = []
    for p in parts:
        try:
            out += p()
        except Exception as e:
            print("market events part failed:", type(e).__name__, str(e)[:120])
    seen, uniq = set(), []
    for e in sorted(out, key=lambda e: (e["date"], e.get("time") or "99:99", list(KINDS).index(e["kind"]), e["title"])):
        if e["id"] not in seen and frm.isoformat() <= e["date"] <= to.isoformat():
            seen.add(e["id"])
            uniq.append(mark_weekend(e))
    return uniq


def index_changes(today: date | None = None) -> list[dict]:
    """Each kept index change in full, newest effective date first: [{id, url, title, announced, effective, sections}]."""
    return sorted((load_state().get("index") or {}).get("changes") or [], key=lambda c: c.get("effective") or c["announced"], reverse=True)


def badges(today: date | None = None) -> dict[str, list[dict]]:
    """{symbol: [{short, text, date, index, way}]} for stocks going into or out of a main index: from the announcement
    until BADGE_AFTER days after it takes effect. The biggest index first; two badges at most a stock."""
    today = today or ist_now().date()
    out: dict[str, list[dict]] = {}
    for c in index_changes(today):
        eff = _day(c.get("effective"))
        if not eff or eff < today - timedelta(days=BADGE_AFTER):
            continue
        for s in c.get("sections") or []:
            if s["index"] not in BADGE_INDICES:
                continue
            for way, rows in (("in", s["in"]), ("out", s["out"])):
                for sym, name in rows:
                    ahead = eff > today
                    verb = ("Joins" if ahead else "Joined") if way == "in" else ("Leaves" if ahead else "Left")
                    short = f"{verb} {re.sub(r'^Nifty', 'NIFTY', s['index'])} {'from' if ahead else 'on'} {_short(eff)}"
                    text = (f"{name} {'goes into' if way == 'in' else 'comes out of'} the {s['index']} index from {nice(eff)}, as the index "
                            f"provider announced on {nice(c['announced'])}.")
                    out.setdefault(sym, []).append({"short": short, "text": text, "date": eff.isoformat(), "index": s["index"], "way": way,
                                                    "rank": BADGE_INDICES.index(s["index"])})
    for sym, bs in out.items():
        bs.sort(key=lambda b: (b["rank"], b["date"]))
        uniq, seen = [], set()
        for b in bs:
            if (b["way"], b["date"]) not in seen:
                seen.add((b["way"], b["date"]))
                uniq.append({k: v for k, v in b.items() if k != "rank"})
        out[sym] = uniq[:2]
    return out


def sources() -> list[dict]:
    st = load_state()
    out = []
    for k, label in SOURCES.items():
        p = st.get(k) if isinstance(st.get(k), dict) else {}
        out.append({"id": k, "label": label, "as_of": p.get("as_of"), "checked": p.get("checked"), "failed": bool(p.get("error"))})
    return out


def view(today: date | None = None, listed=None) -> dict:
    today = today or ist_now().date()
    dated = [s["as_of"] for s in sources() if s["as_of"]]
    return {"events": events(today, listed), "index_changes": index_changes(today)[:12], "badges": badges(today), "sources": sources(),
            "as_of": max(dated) if dated else None, "kinds": KINDS, "today": today.isoformat(), "note": NOTE}


# ---------- each user's choices: reminders and the Money calendar ----------
def prefs(uid: str) -> dict:
    row = db.json_value(db.get_setting(USER_KEY + uid), {})
    kinds = [k for k in row.get("kinds") or [] if k in KINDS] if isinstance(row.get("kinds"), list) else ["rbi", "india", "us", "budget", "index"]
    return {"remind": bool(row.get("remind")), "kinds": kinds, "days": row.get("days") if row.get("days") in REMIND_DAYS else 1,
            "money_calendar": bool(row.get("money_calendar")), "sent": [x for x in row.get("sent") or [] if isinstance(x, str)][-MAX_SENT:]}


def save_prefs(uid: str, p: dict) -> dict:
    db.set_setting(USER_KEY + uid, json.dumps({k: p[k] for k in ("remind", "kinds", "days", "money_calendar", "sent")}, separators=(",", ":")))
    return p


def for_money_calendar(uid: str, frm: date, to: date) -> list[dict]:
    """The events of the kinds the user picked, for their Money calendar and its feed, when they turned that on."""
    p = prefs(uid)
    if not p["money_calendar"]:
        return []
    want = set(p["kinds"]) or set(KINDS)
    return [e for e in events(None, None, frm, to) if e["kind"] in want]


def reminder_text(evs: list[dict], days: int, day: date) -> str:
    when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
    lines = [f"Market events {when}, {day:%a} {nice(day)}:"]
    for e in evs[:15]:
        lines.append(f"- {e['title']}" + (f" at {e['time']} IST" if e.get("time") else ""))
    if len(evs) > 15:
        lines.append(f"- and {len(evs) - 15} more on the Events page")
    lines.append("Dates as each body publishes them. Facts, not advice.")
    return "\n".join(lines)


def send_reminders(today: date, allowed, send, profile=None) -> int:
    """One message to each user with reminders on (and a plan that has them, `allowed(profile)`), listing the events
    of their kinds `days` from today that weren't sent before. Returns how many messages went."""
    profile = profile or db.cached_profile
    sent = 0
    cache: dict[str, list[dict]] = {}
    for key, raw in db.all_settings_with_prefix(USER_KEY):
        uid = key[len(USER_KEY):]
        row = db.json_value(raw, {})
        if not uid or not isinstance(row, dict) or not row.get("remind"):
            continue
        try:
            p = profile(uid)
            if not allowed(p):
                continue
        except Exception:
            continue
        pr = prefs(uid)
        target = today + timedelta(days=pr["days"])
        if target.isoformat() not in cache:
            cache[target.isoformat()] = events(today, None, target, target)
        done = set(pr["sent"])
        hits = [e for e in cache[target.isoformat()] if e["kind"] in pr["kinds"] and e["id"] not in done]
        if not hits:
            continue
        subject = f"StratLab: {hits[0]['title']}" + (f" and {len(hits) - 1} more" if len(hits) > 1 else "") + f", {_short(target)}"
        try:
            reached = send(p, subject[:150], reminder_text(hits, pr["days"], target))
        except Exception as e:
            print("market events reminder failed:", str(e)[:120])
            continue
        pr = prefs(uid)
        pr["sent"] = (pr["sent"] + [e["id"] for e in hits])[-MAX_SENT:]
        save_prefs(uid, pr)
        sent += 1 if reached else 0
    return sent


class Job(news_job.Job):
    """Twice a day (before the open and in the evening, after the day's 4 pm releases): reads every source; after the
    morning read, sends the reminders. Uses the newsletter job's run markers (newsjob:mktevents-am / -pm), so a restart
    never sends twice. With nothing stored yet (a new server), it reads at once."""
    RUNS = (("mktevents-am", "Asia/Kolkata", "07:20"), ("mktevents-pm", "Asia/Kolkata", "18:40"))

    def __init__(self, web_fn, remind_fn):
        super().__init__()
        self.web_fn, self.remind_fn = web_fn, remind_fn
        self.status.update(problems=[])
        self._first_try = 0.0

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="market-events").start()

    def tick(self, now: datetime) -> int:
        for name, tz, at in self.RUNS:
            day = self.due(name, now, tz, at)
            if day:
                self.mark(name, day)
                return self.run(now, day, remind=name.endswith("-am"))
        if not load_state().get("last_run") and time.time() - self._first_try > 1800:
            self._first_try = time.time()
            self.run(now, ist_now().date(), remind=False)
        return 0

    def run(self, now: datetime, day: date, remind: bool = True) -> int:
        out = refresh(self.web_fn(), day)
        sent = self.remind_fn(day) if remind else 0
        self.record(now, out["problems"], len(READERS), sent=sent)
        return sent
