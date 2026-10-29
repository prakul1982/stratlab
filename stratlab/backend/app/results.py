"""The results calendar: when companies report their quarterly results, in India and the US, and the results-day
messages to the people who track them.

India: board meetings called to consider financial results, from the exchange's board-meeting list. Companies listed
only on BSE (and everyone, when that list is down) are read from the board-meeting notices in their announcements.
US: the companies reporting each day, from the US market calendar (with the session they announced: before the open
or after the close), and the earnings dates in the US company data; once a company has reported, the SEC's filing
search has its earnings release (8-K, item 2.02) for the whole market, and the company data carries the reported EPS
and revenue (DE-025: the company data alone came back empty in the middle of the reporting season).

Each region's calendar is stored as results:cal:<region>, a rolling window from a week back to four weeks ahead,
refreshed in the background. Facts only: a date, the company's own stated purpose and, once results are filed, a
link to the filing and the numbers it states. Never a view on them."""
import json
import re
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import alerts, db, leader, run_marks
from .intel.net import SourceError

REGIONS = ("IN", "US")
TZ = {"IN": "Asia/Kolkata", "US": "America/New_York"}
KEY = "results:cal:"                 # results:cal:<region> = {"at": ISO time, "rows": [...], "v": CAL_VERSION}
# how the stored list was read: a list stored by an older reader is read again at once, not at the next scheduled slot (RC1-005:
# the US list stored empty by the first reader stayed empty for the day after the market calendar was added, DE-025). 2: the US
# list from the market calendar and the SEC's earnings releases
CAL_VERSION = 2
ALERT_KEY = "resultsalert:"          # resultsalert:<uid> = "off" when someone turned the messages off
AHEAD_DAYS = 21                      # how far ahead each refresh asks for
BEHIND_DAYS = 3                      # ...and how far back (so a refresh also sees what was just reported)
KEEP_DAYS = 7                        # past results stay listed this long
MAX_ROWS = 3000
MAX_LOOKUPS = 80                     # per-company lookups in one refresh (BSE-only companies, or a feed that's down)
OUT_DAYS = 2                         # how many days after the results day we keep looking for the filing
NOTE = "Dates as the companies announced them. Not investment advice."
_lock = threading.Lock()

MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATES = [  # (pattern, order of day/month/year groups)
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/.,]*(?:day of\s+)?" + _MON + r"[\s\-/.,]*(\d{4})\b", re.I), "dmy"),
    (re.compile(r"\b" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})\b", re.I), "mdy"),
    (re.compile(r"\b(\d{1,2})[\-/.](\d{1,2})[\-/.](\d{4})\b"), "dmy"),
]
RESULTS = re.compile(r"financial results|\bresults\b", re.I)
PAST = re.compile(r"outcome|approved the|were approved|has approved", re.I)          # a meeting already held
NOTICE = re.compile(r"intimation|to consider|will be held|is scheduled|scheduled to|prior intimation|proposes to", re.I)
WHEN = {"bmo": "before the open", "amc": "after the close", "dmh": "during market hours"}


def local_today(region: str) -> date:
    return datetime.now(ZoneInfo(TZ[region])).date()


def parse_day(s) -> date | None:
    """A date in any of the ways the feeds write one: 2026-10-15, 15-Oct-2026, 15-10-2026, 15/10/2026."""
    s = str(s or "").strip()[:20]
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%B-%Y"):
        for cand in (s, s[:10], s[:11]):            # a time may follow the date
            try:
                return datetime.strptime(cand, fmt).date()
            except ValueError:
                continue
    return None


def dates_in(text: str) -> list[date]:
    """Every date written out in a notice, in the order they appear."""
    found = []
    for rx, order in _DATES:
        for m in rx.finditer(text or ""):
            g = m.groups()
            try:
                if order == "mdy":
                    d = date(int(g[2]), MONTHS[g[0][:3].lower()], int(g[1]))
                elif g[1].isdigit():
                    d = date(int(g[2]), int(g[1]), int(g[0]))
                else:
                    d = date(int(g[2]), MONTHS[g[1][:3].lower()], int(g[0]))
            except (ValueError, KeyError):
                continue
            found.append((m.start(), d))
    return [d for _, d in sorted(found)]


# ---------- the feeds' rows as calendar rows ----------
def row(region: str, symbol: str, day: date, purpose: str, *, name=None, when=None, url=None, src="exchange", period=None) -> dict:
    return {"region": region, "symbol": symbol.upper(), "name": name, "date": day.isoformat(), "when": when,
            "purpose": purpose[:160], "url": url if str(url or "").startswith("https://") else None, "src": src, "period": period}


GENERIC = re.compile(r"^(?:board meeting(?: intimation)?|intimation|prior intimation)?$", re.I)


def purpose_of(purpose: str, desc: str) -> str:
    """The meeting's purpose as the exchange's list names it ("Financial Results/Dividend"). A notice filed under the
    bare "Board Meeting Intimation" heading says what the meeting is for in its text: it is named from that (DE-027:
    71 results meetings, NTPC's among them, read "Board Meeting Intimation")."""
    if purpose and not GENERIC.match(purpose.strip()):
        return purpose
    parts = ["Financial Results"] + [w for w, rx in (("Dividend", r"dividend"), ("Fund Raising", r"fund rais|raising of funds"),
                                                      ("Bonus", r"\bbonus\b"), ("Stock Split", r"split|sub-?division"))
                                     if re.search(rx, desc, re.I)]
    return "/".join(parts)


def india_rows(raw: list) -> list[dict]:
    """The exchange's board meetings that are about financial results, one per company and day: a company that filed
    both the bare intimation and the itemised notice for the same meeting is listed once, under the itemised one."""
    out: dict = {}
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("bm_symbol") or r.get("symbol") or "").strip().upper()
        purpose = str(r.get("bm_purpose") or r.get("purpose") or "").strip()
        desc = re.sub(r"\s+", " ", str(r.get("bm_desc") or r.get("desc") or "")).strip()
        day = parse_day(r.get("bm_date") or r.get("date"))
        if not sym or not day or not RESULTS.search(f"{purpose} {desc}"):
            continue
        x = row("IN", sym, day, purpose_of(purpose, desc), name=str(r.get("sm_name") or r.get("company") or "").strip() or None,
                url=r.get("attachment") or r.get("bm_attachment"))
        have = out.get((sym, x["date"]))
        if have is None or (GENERIC.match(have.get("_said") or "") and not GENERIC.match(purpose)):
            out[(sym, x["date"])] = {**x, "_said": purpose}
    return [{k: v for k, v in x.items() if k != "_said"} for x in out.values()]


def from_announcements(symbol: str, items: list[dict], today: date) -> list[dict]:
    """Upcoming results meetings read from a company's own notices: a board-meeting notice that mentions financial
    results and names a date on or after the day it was filed (and within two months of it)."""
    out = []
    for i in items or []:
        hay = f"{i.get('subject') or ''}. {i.get('text') or ''}"
        if not (re.search(r"board meeting", hay, re.I) and RESULTS.search(hay)) or PAST.search(hay):
            continue
        filed = parse_day(str(i.get("at") or "")[:10])
        if not filed or (today - filed).days > 45:
            continue
        # a date after the filing day first: the letter's own date ("Date: October 28") is the filing day, not the meeting's;
        # the filing day itself only when the notice names no later one (a meeting held the same day)
        found = [d for d in dates_in(hay) if filed <= d <= filed + timedelta(days=60)]
        day = next((d for d in found if d > filed), found[0] if found else None)
        if day and day >= today - timedelta(days=KEEP_DAYS):
            out.append(row("IN", symbol, day, "Board meeting to consider financial results", url=i.get("url"), src="announcement"))
    return out[:1]                      # the newest notice wins (items come newest first)


def us_rows(raw: list) -> list[dict]:
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        sym, day = str(r.get("symbol") or "").strip().upper(), parse_day(r.get("date"))
        if not sym or not day or not re.fullmatch(r"[A-Z0-9.\-]{1,12}", sym):
            continue
        q, y = r.get("quarter"), r.get("year")
        period = f"Q{q} {y}" if q and y else None
        x = row("US", sym, day, "Quarterly results" + (f" ({period})" if period else ""), when=WHEN.get(str(r.get("hour") or "")),
                src="company data", period=period)
        rep = reported(r)
        if rep:
            x["reported"] = rep
        out.append(x)
    return out


def _quarter(p: str | None) -> str | None:
    """"Sep/2026" (a fiscal quarter's last month) as "Sep 2026"."""
    m = re.fullmatch(r"([A-Za-z]{3})/(\d{4})", str(p or "").strip())
    return f"{m.group(1).title()} {m.group(2)}" if m else None


def us_name(name: str | None) -> str | None:
    """A US company's name for the list: the SEC's filing name in capitals ("INTERNATIONAL BUSINESS MACHINES CORP") in
    title case, and a listing's share-class tail ("Common Stock") left out."""
    from .stock_pages import proper_name
    name = re.sub(r"\s+(?:Class [A-Z] )?(?:Common Stock|Common Shares|Ordinary Shares|American Depositary Shares)\b.*$", "", str(name or "").strip())
    return proper_name(name) or None


def calendar_rows(raw: list, names: dict | None = None) -> list[dict]:
    """The companies reporting each day as the US market calendar lists them, with the session they announced (DE-025).
    Names: the S&P 500 list's where it has one."""
    names = names or {}
    out = []
    for r in raw if isinstance(raw, list) else []:
        sym, day = str((r or {}).get("symbol") or "").upper(), parse_day((r or {}).get("date"))
        if not sym or not day:
            continue
        q = _quarter(r.get("period"))
        out.append(row("US", sym, day, "Quarterly results" + (f" (quarter ended {q})" if q else ""), when=WHEN.get(str(r.get("hour") or "")),
                       name=names.get(sym) or us_name(r.get("name")), src="market calendar", period=q))
    return out


def with_filings(rows: list[dict], filed: list[dict], today: date, names: dict | None = None) -> list[dict]:
    """The earnings releases filed with the SEC (8-K, item 2.02) put on the calendar (DE-025): on the company's row for
    that results day (or the three days before it, for a release filed the day after a late call), else as a row of
    its own on the filing day. A release filed in the last OUT_DAYS days is marked for its people to be told."""
    names = names or {}
    by_sym: dict = {}
    for r in rows:
        if r["region"] == "US":
            by_sym.setdefault(r["symbol"], []).append(r)
    for f in filed:
        day = parse_day(f.get("at"))
        if not day or not f.get("symbol"):
            continue
        out = {"at": day.isoformat(), "title": "Earnings release (8-K)", "url": f.get("url") if str(f.get("url") or "").startswith("https://") else None,
               "numbers": []}
        told = {"told": False} if day >= today - timedelta(days=OUT_DAYS) else {}
        near = [r for r in by_sym.get(f["symbol"], []) if (day - timedelta(days=3)).isoformat() <= r["date"] <= day.isoformat()]
        if near:
            r = max(near, key=lambda r: r["date"])
            if not r.get("out"):
                r.update(out=out, **told)
            continue
        x = row("US", f["symbol"], day, "Quarterly results", name=names.get(f["symbol"]) or us_name(f.get("name")), src="filing")
        x.update(out=out, **told)
        rows.append(x)
        by_sym.setdefault(f["symbol"], []).append(x)
    return rows


def weekdays(frm: date, to: date) -> list[date]:
    return [frm + timedelta(days=i) for i in range((to - frm).days + 1) if (frm + timedelta(days=i)).weekday() < 5]


def reported(r: dict) -> list[dict]:
    """The numbers a US company reported, as the results feed carries them: EPS and revenue (never the estimates)."""
    out = []
    if isinstance(r.get("epsActual"), (int, float)):
        eps = round(r["epsActual"], 2) + 0.0         # -0.001 is $0.00, never -$0.00
        out.append({"label": "EPS", "value": f"-${-eps:.2f}" if eps < 0 else f"${eps:.2f}"})
    rev = r.get("revenueActual")
    if isinstance(rev, (int, float)) and rev > 0:
        out.append({"label": "Revenue", "value": f"${rev / 1e9:,.2f} billion" if rev >= 1e9 else f"${rev / 1e6:,.1f} million"})
    return out


# ---------- storage ----------
def load(region: str) -> dict:
    cal = db.json_value(db.get_setting(KEY + region), {})
    return {"at": cal.get("at"), "v": cal.get("v") or 1, "rows": [r for r in cal.get("rows") or [] if isinstance(r, dict) and r.get("date")]}


def save(region: str, rows: list[dict]):
    rows = sorted(rows, key=lambda r: (r["date"], r["symbol"]))[:MAX_ROWS]
    db.set_setting(KEY + region, json.dumps({"at": datetime.now(ZoneInfo(TZ[region])).isoformat(timespec="minutes"), "v": CAL_VERSION, "rows": rows}))


def merge(old: list[dict], new: list[dict], frm: date, today: date) -> list[dict]:
    """The stored rows from before the window just fetched, plus the fresh ones. Inside the window the fresh list
    wins, so a meeting the company moved shows only on its new date. What we learnt after a results day (the
    filing, the numbers) carries over. Rows older than a week drop off."""
    keep_from = (today - timedelta(days=KEEP_DAYS)).isoformat()
    learnt = {(r["symbol"], r["date"]): r for r in old if r.get("out")}
    out = {(r["symbol"], r["date"]): r for r in old if keep_from <= r["date"] < frm.isoformat()}
    exchange = {r["symbol"] for r in new if r.get("src") != "announcement"}
    for r in new:
        if r.get("src") == "announcement" and r["symbol"] in exchange:
            continue                     # the exchange's own list is the better source for that company
        k = (r["symbol"], r["date"])
        prior = learnt.get(k)
        out[k] = {**r, "out": prior["out"], **{f: prior[f] for f in ("told", "told_to") if f in prior}} if prior else r
    return list(out.values())


def lookup(region: str, symbol: str, today: date | None = None) -> dict:
    """One company's next results date, and its latest past one in the window (with the filing, once it's out)."""
    today = today or local_today(region)
    rows = [r for r in load(region)["rows"] if r["symbol"] == symbol.upper()]
    ahead = sorted((r for r in rows if r["date"] >= today.isoformat()), key=lambda r: r["date"])
    past = sorted((r for r in rows if r["date"] < today.isoformat()), key=lambda r: r["date"], reverse=True)
    return {"next": ahead[0] if ahead else None, "last": past[0] if past else None}


def between(region: str, frm: date, to: date, symbols: set[str] | None = None) -> list[dict]:
    return [r for r in load(region)["rows"] if frm.isoformat() <= r["date"] <= to.isoformat()
            and (symbols is None or r["symbol"] in symbols)]


def week_of(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


# ---------- who tracks what ----------
def users() -> set[str]:
    """Everyone with something to track: a watchlist, a newsletter choice or a running paper session."""
    from . import newsletter_prefs
    uids = {k.split(":", 1)[1] for k, _ in db.all_settings_with_prefix("watchlist:") if ":" in k}
    uids |= {db.json_value(raw, {}).get("uid") for _, raw in db.all_settings_with_prefix(newsletter_prefs.KEY)}
    try:
        uids |= {r.get("user_id") for r in db.running_index()}
    except Exception:
        pass
    return {u for u in uids if isinstance(u, str) and u}


def my_stocks(uid: str, region: str | None = None) -> list[str]:
    """The user's stocks as the My Stocks newsletter sees them (watchlist, notebooks, paper sessions)."""
    from .newsletter import content
    return [s for r, s in content.my_stocks(uid) if region is None or r == region]


_trackers: dict = {}               # hour -> {(region, symbol): users}: one read of every user's stocks an hour, for both jobs
_trackers_lock = threading.Lock()


def forget_trackers() -> None:
    with _trackers_lock:
        _trackers.clear()


def trackers(region: str | None = None, now: datetime | None = None) -> dict[tuple[str, str], list[str]]:
    """(region, symbol) -> the users tracking it, for one region or both. Built from every user's stocks, so it is
    kept for the hour (by region too: both regions' jobs, and this job and the corporate actions job, share it)."""
    from .newsletter import content
    hour = (now or datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H")
    with _trackers_lock:
        have = _trackers.get(hour)
    if have is None:
        have = {}
        for uid in sorted(users()):
            try:
                stocks = content.my_stocks(uid)
            except Exception:
                continue
            for k in stocks:
                have.setdefault(k, []).append(uid)
        with _trackers_lock:
            _trackers.clear()
            _trackers[hour] = have
    return have if region is None else {k: v for k, v in have.items() if k[0] == region}


def _get(who):
    """The trackers map, from the map itself or from the function that builds it when first needed."""
    return who() if callable(who) else who


def alerts_on(uid: str) -> bool:
    return db.get_setting(ALERT_KEY + uid) != "off"


def set_alerts(uid: str, on: bool):
    db.set_setting(ALERT_KEY + uid, "on" if on else "off")


# ---------- refreshing ----------
def refresh(region: str, sources: dict, tracked: set[str] | None = None, today: date | None = None) -> dict:
    """Ask the feeds for the next three weeks (and the last few days) and store the merged calendar.
    {"rows": n, "problems": [...]}; the stored calendar is left alone when every source failed."""
    today = today or local_today(region)
    frm, to = today - timedelta(days=BEHIND_DAYS), today + timedelta(days=AHEAD_DAYS)
    tracked, rows, problems, whole, unread = set(tracked or ()), [], [], False, set()
    if region == "IN":
        feed = sources.get("in")
        try:
            rows += india_rows(feed.board_meetings(datetime.combine(frm, datetime.min.time()), datetime.combine(to, datetime.min.time())))
            whole = True
        except (SourceError, AttributeError) as e:
            problems.append(str(e)[:160])
        code_of = getattr(feed, "code_of", lambda s: None)
        need = sorted(s for s in tracked if not whole or code_of(s))
        for sym in need[:MAX_LOOKUPS]:
            try:
                rows += from_announcements(sym, feed.announcements(sym, 60), today)
            except SourceError as e:
                problems.append(f"{sym}: {str(e)[:120]}")
    else:
        rows, whole, unread = us_refresh(sources, tracked, frm, to, today, problems)
    if not whole and not rows:
        return {"rows": None, "problems": problems}
    with _lock:
        old = load(region)["rows"]
        if not whole:                    # only some companies were asked: keep everyone else's dates as they were
            asked = {r["symbol"] for r in rows} | tracked
            rows += [r for r in old if r["symbol"] not in asked and r["date"] >= frm.isoformat()]
        elif unread:                     # a day of the calendar that didn't answer keeps the dates it had
            have = {r["symbol"] for r in rows}
            rows += [r for r in old if r["date"] in unread and r["symbol"] not in have]
        merged = merge(old, rows, frm, today)
        save(region, merged)
    add_past(region, merged, today)          # the days gone by stay on a company's list of earlier results days (the table's usual move)
    return {"rows": len(merged), "problems": problems}


def us_refresh(sources: dict, tracked: set[str], frm: date, to: date, today: date, problems: list) -> tuple[list[dict], bool, set[str]]:
    """The US window's rows: (rows, whether they cover every company, the days whose calendar didn't answer).

    The market calendar for each weekday of the window, the company data's whole-market list on top, and the SEC's
    earnings releases of the days gone by (DE-025: the company data answered an empty list for the whole window in the
    middle of the reporting season, and an empty answer was stored as "no company reports"; an empty list now counts
    as not answering). Only when neither list answered are the tracked companies asked one by one."""
    from . import universes
    names = universes.sp500_names()
    fh, cal, sec = sources.get("us"), sources.get("cal"), sources.get("sec")
    rows, whole, unread = [], False, set()
    try:
        got = us_rows(fh.earnings_between(frm, to))
        if got:
            rows, whole = got, True
        else:
            problems.append("The US company data's results calendar came back empty.")
    except (SourceError, AttributeError) as e:
        problems.append(str(e)[:160])
    if cal is not None:
        listed, answered = [], 0
        for d in weekdays(frm, to):
            try:
                listed += calendar_rows(cal.earnings(d), names)
                answered += 1
            except (SourceError, AttributeError) as e:
                unread.add(d.isoformat())
                problems.append(f"{d.isoformat()}: {str(e)[:120]}")
        if listed:
            # the calendar names the session; the company data's row for the same company and day keeps its numbers
            mine = {(r["symbol"], r["date"]): r for r in rows}
            for r in listed:
                k = (r["symbol"], r["date"])
                mine[k] = {**r, **({"reported": mine[k]["reported"]} if mine.get(k, {}).get("reported") else {})}
            rows = list(mine.values())
            whole = whole or answered > 0
        if not whole:
            unread = set()
    if sec is not None:
        filed = []
        for d in weekdays(frm, min(to, today)):
            try:
                filed += sec.earnings_filed(d)
            except (SourceError, AttributeError) as e:
                problems.append(f"filings {d.isoformat()}: {str(e)[:120]}")
        rows = with_filings(rows, filed, today, names)
    if not whole:
        fh_ok = fh is not None and getattr(fh, "ready", lambda: True)()
        for sym in sorted(tracked)[:MAX_LOOKUPS] if fh_ok else []:
            try:
                rows += us_rows(fh.earnings_calendar(sym))
            except (SourceError, AttributeError) as e:
                problems.append(f"{sym}: {str(e)[:120]}")
    return rows, whole, (unread if whole else set())


# ---------- results are out ----------
_NUM = re.compile(r"(revenue from operations|total income|total revenue|revenue|net profit|profit after tax|\bpat\b)"
                  r"[^.\d₹]{0,40}?(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d+)?)\s*(crores?|cr\b\.?|lakhs?|million|billion)", re.I)
LABELS = {"revenue from operations": "Revenue from operations", "total income": "Total income", "total revenue": "Total revenue",
          "revenue": "Revenue", "net profit": "Net profit", "profit after tax": "Profit after tax", "pat": "Profit after tax"}


def india_numbers(text: str) -> list[dict]:
    """Headline numbers a results filing states in its summary (revenue, profit), worded as the filing has them."""
    out, seen = [], set()
    for m in _NUM.finditer(text or ""):
        label = LABELS[m.group(1).lower()]
        if label in seen:
            continue
        seen.add(label)
        unit = "crore" if m.group(3).lower().startswith("cr") else m.group(3).lower().rstrip("s")
        out.append({"label": label, "value": f"₹{m.group(2)} {unit}"})
    return out[:3]


def india_out(feed, r: dict) -> dict | None:
    """The results filing a company made on or after its board meeting, if it's in yet."""
    found = []
    for i in feed.announcements(r["symbol"], 30):
        hay = f"{i.get('subject') or ''}. {i.get('text') or ''}"
        if str(i.get("at") or "")[:10] < r["date"] or not RESULTS.search(hay) or NOTICE.search(hay):
            continue
        if i.get("category") in ("results", "board") or re.search(r"financial results", hay, re.I):
            found.append(i)
    if not found:
        return None
    i = min(found, key=lambda x: x["at"])
    return {"at": i["at"], "title": i.get("subject") or "Financial results", "url": i.get("url"),
            "numbers": india_numbers(f"{i.get('subject') or ''}. {i.get('text') or ''}")}


def us_out(fh, sec, r: dict) -> dict | None:
    """The earnings release (8-K, item 2.02) filed on or after the results day, and the reported EPS and revenue."""
    from .intel.sec import documents
    rel, nums = None, []
    if sec is not None:
        try:
            subs = sec.submissions(sec.cik(r["symbol"]), fresh=True)
            back = max(14, (local_today("US") - date.fromisoformat(r["date"])).days + 1)     # back to the results day
            rel = next((d for d in sorted(documents(subs, days=back), key=lambda d: d["at"])
                        if d["kind"] == "earnings_release" and d["at"] >= r["date"]), None)
        except SourceError:
            rel = None
    if fh is not None:
        try:
            day = date.fromisoformat(r["date"])
            hit = next((x for x in fh.earnings_between(day, day + timedelta(days=1)) if str(x.get("symbol") or "").upper() == r["symbol"]), None)
            nums = reported(hit) if hit else []
        except (SourceError, AttributeError, ValueError):
            nums = []
    if not rel and not nums:
        return None
    return {"at": rel["at"] if rel else r["date"], "title": rel["title"] if rel else "Results reported",
            "url": rel["url"] if rel else None, "numbers": nums}


def check_out(region: str, sources: dict, symbols: set[str], today: date | None = None) -> list[dict]:
    """For tracked companies whose results day was today or the last two days and whose filing we haven't seen:
    look for it. Each one found is stored on its calendar row and returned (once)."""
    today = today or local_today(region)
    frm = (today - timedelta(days=OUT_DAYS)).isoformat()
    waiting = [r for r in load(region)["rows"] if frm <= r["date"] <= today.isoformat() and not r.get("out") and r["symbol"] in symbols]
    found = []
    for r in waiting[:MAX_LOOKUPS]:
        try:
            out = india_out(sources.get("in"), r) if region == "IN" else us_out(sources.get("us"), sources.get("sec"), r)
        except (SourceError, AttributeError) as e:
            print("results check:", r["symbol"], str(e)[:120])
            continue
        if out:
            found.append({**r, "out": out})
    if found:
        with _lock:
            done = {(r["symbol"], r["date"]): r["out"] for r in found}
            rows = load(region)["rows"]
            for r in rows:
                if (r["symbol"], r["date"]) in done:
                    r["out"], r["told"] = done[(r["symbol"], r["date"])], False    # told once its people have it
            save(region, rows)
    return found


# ---------- the messages ----------
def _day(iso: str) -> str:
    """A day in the app's format: Mon 5 Oct."""
    from .email_kit import fmt_date
    return fmt_date(str(iso), year=False, weekday=True)


def describe(r: dict) -> str:
    return r["purpose"] + (f", {r['when']}" if r.get("when") else "")


def morning_text(rows: list[dict]) -> str:
    parts = [f"{r['symbol']}: {describe(r)}" for r in rows[:10]]
    more = f" and {len(rows) - 10} more" if len(rows) > 10 else ""
    return "Results today for your stocks. " + "; ".join(parts) + more + ". " + NOTE


def out_text(r: dict) -> str:
    """The message, one fact a line: what was filed and when, the numbers as the filing states them (a row each), the
    filing's address, and the small print. A phone shows the lines; an email turns the rows into figures and the
    address into a link."""
    o = r["out"]
    nums = [f"- {n['label']}: {n['value']}" for n in o.get("numbers") or []]
    return "\n".join([
        f"{r['symbol']} results are out: {o.get('title') or 'Results'} ({_day(o.get('at') or r['date'])}).",
        *(["As stated in the filing:", *nums] if nums else []),
        *([f"Read the filing: {o['url']}"] if o.get("url") else []),
        "From the company's filing. Not investment advice."])


def quiet(profile: dict) -> dict:
    """The profile with email left out: these go by phone notification or Telegram (email readers get the newsletter)."""
    return {**profile, "alert_email": None, "email": None}


def can_alert(profile: dict) -> bool:
    return bool(profile.get("id")) and alerts_on(profile["id"]) and bool(alerts.jobs_for(quiet(profile), "", ""))


def send(profile: dict, subject: str, text: str, url: str):
    alerts.notify(quiet(profile), subject, text, url=url)


# ---------- the schedule ----------
REFRESH_AT = {"IN": ("07:15", "18:30"), "US": ("06:00",)}
MORNING_AT = {"IN": "08:00", "US": "07:30"}
CHECK_FROM = {"IN": "10:00", "US": "07:00"}          # hourly from then until midnight, local time
RETRY_MINUTES = 30                                   # a refresh that read nothing is asked again after this long


class Job:
    """Refreshes each region's calendar twice a day (India) or once (US), sends the morning results-day messages and,
    every hour after that, looks for the filings. Every run is marked in the database (the sending ones per recipient),
    so it happens once and a run a crash cut short resumes."""

    def __init__(self, sources, send=send, can_alert=can_alert):
        self.sources, self.send, self.can_alert = sources, send, can_alert
        self.last: dict[str, str] = {}
        self.status = {"last_run": None, "sent": 0, "last_error": None, "problems": []}
        self.down: dict[str, str] = {}               # region -> why its last refresh read nothing (shown until one does)
        self.retry: dict[str, datetime] = {}         # refresh slot -> not asked again before this time

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="results-calendar").start()

    def _loop(self):
        while True:
            try:
                if leader.leading():      # another container leads: it runs this pass
                    self.tick(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("results calendar:", e)
            time.sleep(300)

    def due(self, name: str, now: datetime, region: str, at: str, stamp: str = "%Y-%m-%d", commit: bool = True) -> date | None:
        """The local day when `name` is due (at or after `at`) and its marker (the day, or the hour) isn't set yet.
        `commit=False` leaves the marker for the caller to set (`mark`) once the run has finished."""
        local = now.astimezone(ZoneInfo(TZ[region]))
        mark = local.strftime(stamp)
        if local.strftime("%H:%M") < at or self.last.get(name) == mark:
            return None
        if db.get_setting(f"resultsjob:{name}") == mark:          # already ran (before a restart)
            self.last[name] = mark
            return None
        if commit:
            self.mark(name, mark)
        return local.date()

    def mark(self, name: str, mark: str) -> None:
        self.last[name] = mark
        db.set_setting(f"resultsjob:{name}", mark)

    def claim(self, name: str, now: datetime, region: str, at: str, stamp: str = "%Y-%m-%d"):
        """Like due(), for a run that sends: (local day, run marker), or (None, None) when it isn't due, is done or is
        being worked on. The marker records each recipient, so a run a crash cut short resumes without doubling."""
        local = now.astimezone(ZoneInfo(TZ[region]))
        mark = local.strftime(stamp)
        if local.strftime("%H:%M") < at or self.last.get(name) == mark:
            return None, None
        st = run_marks.status(f"resultsjob:{name}", mark)
        if st == "done":                                    # already ran (before a restart)
            self.last[name] = mark
        run = run_marks.claim(f"resultsjob:{name}", mark) if st is None else None
        return (local.date(), run) if run else (None, None)

    def tick(self, now: datetime) -> int:
        sent, ran = 0, False
        who = lambda: trackers(now=now)           # read when a run needs it, and then once an hour
        for region in REGIONS:
            for at in REFRESH_AT[region]:
                name = f"refresh-{region}-{at}"
                if now < self.retry.get(name, now):
                    continue
                day = self.due(name, now, region, at, commit=False)      # marked once the refresh has finished
                if day:
                    try:
                        out = self.refresh(region, who(), day)
                    except Exception as e:       # this region's failure stops neither the other region nor the sends below
                        print("results refresh failed:", region, str(e)[:160])
                        self.down[region] = f"{region}: {type(e).__name__}: {str(e)[:120]}"
                        self.status["last_error"] = self.down[region]
                        self.retry[name] = now + timedelta(minutes=RETRY_MINUTES)
                        ran = True
                        continue
                    if out["rows"] is None:      # every feed failed: the slot isn't used up, it is asked again in half an hour
                        self.retry[name] = now + timedelta(minutes=RETRY_MINUTES)
                    else:
                        self.mark(name, day.strftime("%Y-%m-%d"))
                    ran = True
            name = f"history-{region}"            # once a week: the results days of the last sixteen months, for each company's usual move
            week = now.astimezone(ZoneInfo(TZ[region])).strftime("%G-W%V")
            if now >= self.retry.get(name, now) and self.due(name, now, region, REFRESH_AT[region][0], stamp="%G-W%V", commit=False):
                try:
                    backfill(region, self.sources(), now.astimezone(ZoneInfo(TZ[region])).date())
                    self.mark(name, week)
                except Exception as e:
                    print("results history failed:", region, str(e)[:160])
                    self.retry[name] = now + timedelta(minutes=RETRY_MINUTES)
                ran = True
            name = f"reread-{region}"
            if load(region)["v"] < CAL_VERSION and now >= self.retry.get(name, now):
                # the stored list is from an older reader: read again now, again in half an hour if no feed answered
                try:
                    out = self.refresh(region, who(), now.astimezone(ZoneInfo(TZ[region])).date())
                    if out["rows"] is None:
                        self.retry[name] = now + timedelta(minutes=RETRY_MINUTES)
                except Exception as e:
                    print("results re-read failed:", region, str(e)[:160])
                    self.retry[name] = now + timedelta(minutes=RETRY_MINUTES)
                ran = True
            for step, at, stamp, work in (("morning", MORNING_AT[region], "%Y-%m-%d", self.morning),
                                          ("check", CHECK_FROM[region], "%Y-%m-%dT%H", self.follow_up)):
                day, run = self.claim(f"{step}-{region}", now, region, at, stamp=stamp)
                if not day:
                    continue
                ran = True
                try:
                    sent += work(region, day, who, run)
                except Exception as e:           # this region's failure stops neither the other region nor the next step
                    print(f"results {step} failed:", region, str(e)[:160])
                    self.down[region] = f"{region}: {type(e).__name__}: {str(e)[:120]}"
                    self.status["last_error"] = self.down[region]
                    continue                     # the run isn't marked done: it resumes at a later pass
                run.done()
        if ran:
            self.status.update(last_run=now.isoformat(), sent=sent, last_error=next(iter(self.down.values()), None))
            from . import job_status
            job_status.keep("results", self)       # Admin shows this run after a restart too
        return sent

    def unmark(self, name: str) -> None:
        """Take a slot's day mark back (a read that got nothing must not use the slot up)."""
        self.last.pop(name, None)
        db.delete_setting(f"resultsjob:{name}")

    def refresh(self, region: str, who: dict | None = None, day: date | None = None) -> dict:
        who = who if who is not None else trackers()
        out = refresh(region, self.sources(), {s for (r, s) in who if r == region}, day)
        self.status["problems"] = out["problems"][:10]
        if out["rows"] is None:                      # no feed answered: Admin says so, not "OK"
            self.down[region] = f"{region}: {(out['problems'] or ['no feed answered'])[0]}"[:200]
        else:
            self.down.pop(region, None)
        self.status["last_error"] = next(iter(self.down.values()), None)
        return out

    def morning(self, region: str, day: date, who, run) -> int:
        """One message per person listing their stocks with results today. `who`: the trackers map, or a function that
        gives it (read only when there is something to tell)."""
        if not load(region)["at"]:
            self.refresh(region, _get(who), day)
        today = between(region, day, day)
        if not today:
            return 0
        who = _get(who)
        per_user: dict[str, list[dict]] = {}
        for r in today:
            for uid in who.get((region, r["symbol"]), []):
                per_user.setdefault(uid, []).append(r)
        sent = 0
        for uid, rows in per_user.items():
            if run.seen(uid):
                continue
            run.beat()
            try:
                profile = db.get_profile(uid)
                if not self.can_alert(profile):
                    continue
                run.record(uid)                # before the send: a kill in between drops one, never doubles
                self.send(profile, "StratLab: results today", morning_text(rows), f"/research/results?region={region}")
                sent += 1
            except Exception as e:             # one person's failure doesn't stop the rest
                print("results message failed:", uid, str(e)[:160])
        return sent

    def follow_up(self, region: str, day: date, who, run) -> int:
        """Look for the filings of results days just gone, and tell the people tracking each company. Each person told
        is written on the row (told_to), so a run cut short and resumed in a later hour doesn't tell them again."""
        frm = (day - timedelta(days=OUT_DAYS)).isoformat()
        if not any(frm <= r["date"] <= day.isoformat() and (not r.get("out") or r.get("told") is False) for r in load(region)["rows"]):
            return 0                       # no results day in the window is waiting for a filing or for its people: nobody to look up
        who = _get(who)
        symbols = {s for (r, s) in who if r == region}
        sent = 0
        check_out(region, self.sources(), symbols, day)
        told = [r for r in load(region)["rows"] if frm <= r["date"] <= day.isoformat() and r.get("out")
                and r.get("told") is False and r["symbol"] in symbols]  # filed but not (fully) told: a cut-short run resumes
        # (a row filed before "told" was kept has no flag: it was told then)
        for r in told:
            for uid in who.get((region, r["symbol"]), []):
                if run.seen(f"{uid}:{r['symbol']}") or uid in (r.get("told_to") or []):
                    continue
                run.beat()
                try:
                    profile = db.get_profile(uid)
                    if not self.can_alert(profile):
                        continue
                    run.record(f"{uid}:{r['symbol']}")       # before the send: a kill in between drops one, never doubles
                    self._told(region, r, uid)
                    self.send(profile, f"StratLab: {r['symbol']} results are out", out_text(r), f"/research/{region}/{r['symbol']}")
                    sent += 1
                except Exception as e:         # one person's failure doesn't stop the rest
                    print("results message failed:", uid, str(e)[:160])
        if told:
            with _lock:
                done = {(r["symbol"], r["date"]) for r in told}
                rows = load(region)["rows"]
                for r in rows:
                    if (r["symbol"], r["date"]) in done:
                        r["told"] = True
                        r.pop("told_to", None)          # everyone is told: the flag is enough
                save(region, rows)
        return sent

    def _told(self, region: str, row: dict, uid: str):
        """Write on the calendar row that this person is being told (before the send, like the run marker)."""
        with _lock:
            rows = load(region)["rows"]
            for r in rows:
                if (r["symbol"], r["date"]) == (row["symbol"], row["date"]) and uid not in (r.get("told_to") or []):
                    r["told_to"] = (r.get("told_to") or []) + [uid]
            save(region, rows)
        row["told_to"] = (row.get("told_to") or []) + [uid]


# ---------- the page ----------
DAY_ROWS = 25          # rows a day shows at first on "All companies"; the rest of that day opens on request (DE-026)
INDEX_SETS = {         # the indices a table can be narrowed to: id -> name, per market (the members are read from what the app keeps)
    "IN": (("nifty50", "NIFTY 50"), ("banknifty", "NIFTY Bank"), ("nifty500", "NIFTY 500"), ("midcap150", "NIFTY Midcap 150"),
           ("smallcap250", "NIFTY Smallcap 250")),
    "US": (("sp500", "S&P 500"),)}
SIZES = ("large", "mid", "small", "micro")
SORTS = ("cap", "name", "move", "sales", "profit")      # market value (largest first), name, the usual results-day move, revenue and profit growth
PLAIN_RESULTS = re.compile(r"^(?:board meeting to consider )?(?:financial|quarterly) results(?: \(.*\))?$", re.I)
_sets = None


def _members(region: str, pid: str) -> set[str]:
    """One index's stocks as the app keeps them (the exchange's last list, or the app's own for the NIFTY 50 and Bank)."""
    from . import breadth, universes
    try:
        if pid == "sp500":
            return set(universes.sp500_symbols())
        if pid in ("nifty50", "banknifty"):
            return set(universes.symbols("IN", pid))
        key = {"nifty500": "nifty500", "midcap150": "midcap150", "smallcap250": "smallcap250"}[pid]
        return {x for x in db.json_value(db.get_setting(breadth.MEMBERS_KEY + key), []) if isinstance(x, str)}
    except Exception:                          # a list that can't be read narrows to nothing, it never breaks the page
        return set()


def index_sets(region: str) -> dict[str, tuple[str, set[str]]]:
    """{id: (name, members)} for a market's indices, kept for ten minutes."""
    from .intel.net import TTLCache
    global _sets
    if _sets is None:
        _sets = TTLCache(max_items=4, max_bytes=2 * 1024 * 1024)
    hit = _sets.get(region)
    if hit is None:
        hit = {pid: (name, _members(region, pid)) for pid, name in INDEX_SETS.get(region, ())}
        _sets.set(region, hit, 600)
    return hit


def fo_symbols() -> set[str]:
    """The stocks that have futures and options, from the exchange's lot-size file the F&O changes page keeps."""
    from . import fo_changes
    try:
        rows = (fo_changes.load_state().get("lots") or {}).get("rows") or {}
        return {s for s, r in rows.items() if isinstance(r, dict) and not r.get("index")}
    except Exception:
        return set()


def band_of(region: str, r: dict | None) -> str | None:
    """A company's size, by the definitions the screener uses: India by rank in market value, the US by amount."""
    from . import screens
    if not r or screens._num(r.get("market_cap")) is None:
        return None
    for b in SIZES:
        if screens._in_band(region, r, [b]):
            return b
    return None


def _snap(region: str) -> dict[str, dict]:
    """{symbol: the screener's stored row}: market value, sector, last close, the latest quarter against its year-ago quarter."""
    from . import screens
    try:
        return {r["symbol"]: r for r in screens.load_index(region).get("rows") or []}
    except Exception as e:
        print("results: the screener's rows could not be read:", str(e)[:120])
        return {}


class Context:
    """What the app keeps about the companies of a market, read once for a page: the screener's stored rows (market value, sector, last
    close, the latest quarter against a year before), the indices' members and the stocks with futures and options. `facts(symbol)` is
    what a calendar row says about its company; `facets(...)` what the filters offer."""

    def __init__(self, region: str):
        self.region = region
        self.snaps = _snap(region)
        self.sets = index_sets(region)
        self.fos = fo_symbols() if region == "IN" else set()

    def facts(self, symbol: str) -> dict:
        s = self.snaps.get(symbol) or {}
        return {"cap": s.get("market_cap"), "band": band_of(self.region, s), "sector": s.get("sector"), "last": s.get("price"),
                "last_at": s.get("price_at"), "fo": symbol in self.fos, "indices": [name for pid, (name, mem) in self.sets.items() if symbol in mem],
                "q": ({"sales": s.get("q_sales"), "profit": s.get("q_profit"), "of": s.get("q_of")} if s.get("q_sales") is not None or s.get("q_profit") is not None else None)}

    def passes(self, r: dict, size=(), sector: str = "", index: str = "", fo: bool = False) -> bool:
        """Whether a row (with its company's facts) meets the size, sector, index and F&O choices."""
        return ((not size or r["band"] in size) and (not sector or r["sector"] == sector) and (not index or self.sets[index][0] in r["indices"])
                and (not fo or r["fo"]))

    def clean(self, size=(), sector: str = "", index: str = "") -> tuple[list[str], str, str]:
        """The choices as they can be used: sizes that exist, a sector as text, an index of this market (else none)."""
        return [b for b in (size or ()) if b in SIZES], str(sector or "")[:80], index if index in self.sets else ""

    def facets(self, rows: list[dict]) -> dict:
        return facets(self.region, rows, self.sets, bool(self.fos))


def _plain(r: dict) -> bool:
    """A meeting about the results alone, not "Financial Results/Dividend" or "...Fund Raising"."""
    return bool(PLAIN_RESULTS.match(str(r.get("purpose") or "").strip()))


def _moves_of(region: str, symbol: str, store: dict) -> dict | None:
    got = (store.get("rows") or {}).get(symbol)
    if not got or not got.get("moves"):
        return None
    pcts = [m[1] for m in got["moves"] if isinstance(m, list) and len(m) == 2 and isinstance(m[1], (int, float))]
    if not pcts:
        return None
    return {"avg": round(sum(abs(x) for x in pcts) / len(pcts), 1), "n": len(pcts), "last": pcts[:4], "dates": [m[0] for m in got["moves"]][:4]}


def _today_dates(day: str | None, today: date) -> str | None:
    """The `on` choice as an ISO date: "today", "tomorrow" or a date; None for every day."""
    if day in ("today", "tomorrow"):
        return (today + timedelta(days=1 if day == "tomorrow" else 0)).isoformat()
    return day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day or "")) else None


def view(region: str, uid: str, scope: str = "mine", q: str = "", today: date | None = None, limit: int = DAY_ROWS,
         day: str | None = None, *, size=(), sector: str = "", index: str = "", fo: bool = False, purpose: str = "", on: str = "",
         sort: str = "cap", desc: bool | None = None) -> dict:
    """This week and next, Monday to Sunday: the user's own stocks, or every company in the calendar, day by day, narrowed by
    company size, sector, index, F&O and the meeting's purpose, and sorted. Every day is listed with how many companies it has;
    on "All companies" a day shows its first `limit` rows (the user's own first) and says how many more it has, and `day` (ISO)
    asks for one day in full. DE-026: a cut at the 400th row of the week dropped all of Saturday 31 Oct (NTPC among them) under
    "And 66 more". Each row carries what the app already keeps about the company (its market value, sector, last close, the
    latest quarter against a year before and its usual move on a results day) and whether it has futures and options."""
    today = today or local_today(region)
    cal = load(region)
    mine = set(my_stocks(uid, region))
    q = re.sub(r"[^A-Z0-9&.\- ]", "", (q or "").upper()).strip()[:30]
    day = day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day or "")) else None
    ctx = Context(region)
    size, sector, index = ctx.clean(size, sector, index)
    only = _today_dates(on, today)
    sort = sort if sort in SORTS else "cap"
    desc = (sort != "name") if desc is None else bool(desc)
    mv = load_moves(region)
    first, last = week_of(today)[0], week_of(today)[0] + timedelta(days=13)

    def rich(r: dict) -> dict:
        out = {**r, "mine": r["symbol"] in mine, **ctx.facts(r["symbol"]), "moves": _moves_of(region, r["symbol"], mv)}
        if not r.get("name") and (ctx.snaps.get(r["symbol"]) or {}).get("name"):
            out["name"] = ctx.snaps[r["symbol"]]["name"]
        return out

    window = [rich(r) for r in cal["rows"] if first.isoformat() <= r["date"] <= last.isoformat()
              and (scope == "all" or r["symbol"] in mine) and (not q or q in r["symbol"] or q in str(r.get("name") or "").upper())]

    def keep(r: dict) -> bool:
        return (ctx.passes(r, size, sector, index, fo) and (purpose != "results" or _plain(r)) and (purpose != "more" or not _plain(r))
                and (not only or r["date"] == only))

    narrowed = [r for r in window if keep(r)]
    val = {"cap": lambda r: r["cap"], "name": lambda r: str(r.get("name") or r["symbol"]).lower(), "move": lambda r: (r["moves"] or {}).get("avg"),
           "sales": lambda r: (r["q"] or {}).get("sales"), "profit": lambda r: (r["q"] or {}).get("profit")}[sort]

    def ordered(rows: list[dict]) -> list[dict]:
        """By the figure chosen (a company without it after the rest), then by day, the user's own stocks first within each."""
        rows = sorted(rows, key=lambda r: r["symbol"])
        have = sorted((r for r in rows if val(r) is not None), key=val, reverse=desc)
        rows = have + [r for r in rows if val(r) is None]
        return sorted(rows, key=lambda r: (r["date"], r["symbol"] not in mine))

    weeks, more = [], 0
    for label, start in (("This week", first), ("Next week", first + timedelta(days=7))):
        end = start + timedelta(days=6)
        rows = ordered([r for r in narrowed if start.isoformat() <= r["date"] <= end.isoformat()])
        days, shown = [], []
        for d in sorted({r["date"] for r in rows}):
            on_day = [r for r in rows if r["date"] == d]
            cap = len(on_day) if scope != "all" or d == day else max(1, limit)
            shown += on_day[:cap]
            days.append({"date": d, "count": len(on_day), "shown": min(cap, len(on_day))})
            more += max(0, len(on_day) - cap)
        weeks.append({"label": label, "from": start.isoformat(), "to": end.isoformat(), "days": days, "rows": shown})
    unknown = sum(1 for r in window if r["band"] is None) if size else 0
    return {"region": region, "scope": scope, "today": today.isoformat(), "updated_at": cal["at"], "weeks": weeks,
            "more": more, "day_rows": limit, "mine_count": len(mine), "alerts": alerts_on(uid), "note": NOTE,
            "total": len(window), "matching": len(narrowed), "unknown_size": unknown,
            "filters": {"size": size, "sector": sector, "index": index, "fo": bool(fo), "purpose": purpose if purpose in ("results", "more") else "", "on": on if only else "", "sort": sort},
            "facets": ctx.facets(window)}


def facets(region: str, rows: list[dict], sets: dict, has_fo: bool) -> dict:
    """What the filters offer for these companies, each with how many it holds: the sizes, the sectors, the indices, F&O stocks."""
    sectors: dict[str, int] = {}
    sizes: dict[str, int] = {}
    for r in rows:
        if r.get("sector"):
            sectors[r["sector"]] = sectors.get(r["sector"], 0) + 1
        if r.get("band"):
            sizes[r["band"]] = sizes.get(r["band"], 0) + 1
    from . import screens
    return {"sizes": [{"id": b, "label": screens.CAP_BANDS[region][b][0], "count": sizes.get(b, 0)} for b in SIZES],
            "sectors": [{"name": n, "count": c} for n, c in sorted(sectors.items(), key=lambda kv: (-kv[1], kv[0]))],
            "indices": [{"id": pid, "name": name, "count": sum(1 for r in rows if name in r["indices"])} for pid, (name, _) in sets.items()],
            "fo": sum(1 for r in rows if r.get("fo")) if has_fo else None}


# ---------- what the app keeps about a company's earlier results days ----------
PAST_KEY = "results:past:"           # results:past:<region> = {"at", "rows": {symbol: [ISO dates, newest first, at most PAST_KEEP]}}
MOVES_KEY = "results:mv:"            # results:mv:<region> = {"rows": {symbol: {"at", "moves": [[date, % move], ...]}}}
PAST_KEEP = 6                        # results days kept for each company
PAST_BACK_DAYS = 480                 # how far back the weekly read of the calendar goes
PAST_CHUNK = 92                      # days asked for in one read
MOVES_PER_ASK = 6                    # companies' price histories read for one request: the rest wait for the next
MAX_PAST = 4000                      # companies in either store
HISTORY_DAYS = 500                   # days of daily prices read for a company's moves
_hist = {"fn": None, "options": None}


def setup(history=None, options=None):
    """Where the daily prices (region, symbol, days) and a stock's option chain (symbol, expiry) come from: main.py's readers, or a test's."""
    _hist["fn"], _hist["options"] = history, options


def load_past(region: str) -> dict:
    got = db.json_value(db.get_setting(PAST_KEY + region), {})
    return {"at": got.get("at"), "rows": got.get("rows") if isinstance(got.get("rows"), dict) else {}}


def add_past(region: str, rows: list[dict], today: date) -> int:
    """Put results days (calendar rows with a date before `today`) in the company's list of earlier ones. Returns how many were new."""
    new = 0
    with _lock:
        st = load_past(region)
        have = st["rows"]
        for r in rows:
            if not r.get("date") or r["date"] >= today.isoformat() or not r.get("symbol"):
                continue
            ds = have.get(r["symbol"]) or []
            if r["date"] not in ds:
                ds = sorted(set(ds) | {r["date"]}, reverse=True)[:PAST_KEEP]
                have[r["symbol"]] = ds
                new += 1
        if new:
            if len(have) > MAX_PAST:
                for s in sorted(have, key=lambda s: have[s][0])[: len(have) - MAX_PAST]:
                    have.pop(s)
            db.set_setting(PAST_KEY + region, json.dumps({"at": datetime.now(ZoneInfo(TZ[region])).isoformat(timespec="minutes"), "rows": have}, separators=(",", ":")))
    return new


def backfill(region: str, sources: dict, today: date | None = None) -> int:
    """The results days of the last sixteen months, read from the same feeds as the calendar (India's board meetings, the US results
    list) a quarter at a time: what a company's earlier moves are worked out from. Returns how many days were new."""
    today = today or local_today(region)
    new = 0
    for k in range(0, PAST_BACK_DAYS, PAST_CHUNK):
        to = today - timedelta(days=k + 1)
        frm = max(today - timedelta(days=PAST_BACK_DAYS), to - timedelta(days=PAST_CHUNK - 1))
        try:
            if region == "IN":
                got = india_rows(sources["in"].board_meetings(datetime.combine(frm, datetime.min.time()), datetime.combine(to, datetime.min.time())))
            else:
                got = us_rows(sources["us"].earnings_between(frm, to))
        except (SourceError, AttributeError, KeyError) as e:
            print("results history:", region, str(e)[:120])
            continue
        new += add_past(region, [r for r in got if frm.isoformat() <= r["date"] <= to.isoformat()], today)
    return new


def load_moves(region: str) -> dict:
    try:
        got = db.json_value(db.get_setting(MOVES_KEY + region), {})
    except Exception:
        return {"rows": {}}
    return {"rows": got.get("rows") if isinstance(got.get("rows"), dict) else {}}


def reaction(bars: list[dict], day: date) -> float | None:
    """The change in the close over a results day and the next session: the close of the session after the results day (or the
    day itself when it is the last one so far) against the close of the session before it. A results day falls before the open, in
    the session or after the close, so one figure for both. None without a session on each side."""
    seen = sorted(((str(b["t"])[:10], float(b["c"])) for b in bars if b.get("c")), key=lambda x: x[0])
    before = [c for d, c in seen if d < day.isoformat()]
    after = [c for d, c in seen if d > day.isoformat()]
    on = [c for d, c in seen if d == day.isoformat()]
    end = after[0] if after else (on[0] if on else None)
    if not before or end is None or before[-1] <= 0:
        return None
    return round((end / before[-1] - 1) * 100, 2)


SINCE_DAYS = 7                       # a results day this recent has "since the results" beside it
_since = None


def recent_event(region: str, symbol: str, today: date) -> str | None:
    """The date of this company's newest results day in the last SINCE_DAYS days that has come (a day before today, or today's once
    its results are filed), from the stored calendar."""
    frm = (today - timedelta(days=SINCE_DAYS)).isoformat()
    days = [r["date"] for r in load(region)["rows"] if r["symbol"] == symbol and frm <= r["date"] <= today.isoformat()
            and (r["date"] < today.isoformat() or r.get("out"))]
    return max(days) if days else None


def since_move(bars: list[dict], day: date) -> float | None:
    """The change from the close before a results day to the latest close, once a session on or after the day has traded."""
    seen = sorted(((str(b["t"])[:10], float(b["c"])) for b in bars if b.get("c")), key=lambda x: x[0])
    before = [c for d, c in seen if d < day.isoformat()]
    if not before or not seen or seen[-1][0] < day.isoformat() or before[-1] <= 0:
        return None
    return round((seen[-1][1] / before[-1] - 1) * 100, 2)


def moves_for(region: str, symbols: list[str], today: date | None = None) -> dict[str, dict | None]:
    """For each company: {"moves": ..., "since": ...}. `moves`: what its price did over its earlier results days (see reaction),
    worked out from its daily prices, read once and kept (a company's list changes only when it has a new results day); `since`:
    the change from the close before its newest results day (the last week's) to the latest close, kept ten minutes. At most
    MOVES_PER_ASK companies' price histories are read in one call, the rest on the next; a company with neither is None."""
    from .intel.net import TTLCache
    global _since
    if _since is None:
        _since = TTLCache(max_items=500, max_bytes=1024 * 1024)
    today = today or local_today(region)
    past = load_past(region)["rows"]
    store = load_moves(region)
    rows = store["rows"]
    uniq = list(dict.fromkeys(symbols))
    events = {s: recent_event(region, s, today) for s in uniq}
    todo = [s for s in uniq if (past.get(s) and (not rows.get(s) or rows[s].get("dates") != past[s]))
            or (events[s] and _since.get((region, s, events[s])) is None)]
    read = _hist.get("fn")
    done, changed = 0, False
    for s in todo:
        if read is None or done >= MOVES_PER_ASK:
            break
        done += 1
        try:
            bars = read(region, s, HISTORY_DAYS)
        except Exception as e:
            print("results moves:", region, s, str(e)[:100])
            if past.get(s):
                rows[s] = {"at": today.isoformat(), "dates": past[s], "moves": []}
                changed = True
            if events[s]:
                _since.set((region, s, events[s]), {"pct": None}, 600)
            continue
        if past.get(s) and (not rows.get(s) or rows[s].get("dates") != past[s]):
            mv = [[d, reaction(bars, date.fromisoformat(d))] for d in past[s][:PAST_KEEP]]
            rows[s] = {"at": today.isoformat(), "dates": past[s], "moves": [m for m in mv if m[1] is not None]}
            changed = True
        if events[s]:
            _since.set((region, s, events[s]), {"pct": since_move(bars, date.fromisoformat(events[s]))}, 600)
    if changed:
        with _lock:
            fresh = load_moves(region)["rows"]
            fresh.update({s: rows[s] for s in uniq if s in rows})
            if len(fresh) > MAX_PAST:
                for s in sorted(fresh, key=lambda s: fresh[s].get("at") or "")[: len(fresh) - MAX_PAST]:
                    fresh.pop(s)
            db.set_setting(MOVES_KEY + region, json.dumps({"rows": fresh}, separators=(",", ":")))
        rows = fresh
    out: dict[str, dict | None] = {}
    for s in uniq:
        got = (_since.get((region, s, events[s])) or {}).get("pct") if events[s] else None
        mv = _moves_of(region, s, {"rows": rows})
        out[s] = {"moves": mv, "since": {"date": events[s], "pct": got} if got is not None else None} if (mv or got is not None) else None
    return out


def implied_for(symbols: list[str], day: str | None = None) -> dict[str, dict | None]:
    """For stocks with futures and options: the at-the-money straddle of the first expiry on or after the results day, as a share
    of the price (the move the options price in to that expiry). From the option prices the app already reads; None for a stock
    without them now (the broker is not connected, no quote for the strike, no expiry that late). At most 8 stocks."""
    fn = _hist.get("options")
    out: dict[str, dict | None] = {}
    fos = fo_symbols()
    for s in list(dict.fromkeys(symbols))[:8]:
        out[s] = None
        if fn is None or s not in fos:
            continue
        try:
            got = fn(s, day)
        except Exception as e:
            print("results implied:", s, str(e)[:100])
            continue
        out[s] = got
    return out


def straddle_move(chain: dict) -> dict | None:
    """The implied move from an option chain read around the money: ({"spot", "atm", "expiry", "rows": [{"strike", "ce", "pe"}]})."""
    spot, rows = chain.get("spot"), chain.get("rows") or []
    if not spot or not rows or not chain.get("expiry"):
        return None
    near = min(rows, key=lambda r: abs(r["strike"] - spot))
    px = lambda q: (q or {}).get("ltp") if (q or {}).get("ltp") else None          # noqa: E731
    ce, pe = px(near.get("ce")), px(near.get("pe"))
    if ce is None or pe is None:
        return None
    return {"pct": round((ce + pe) / spot * 100, 1), "strike": near["strike"], "expiry": chain["expiry"], "straddle": round(ce + pe, 2)}
