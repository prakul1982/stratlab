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
KEY = "results:cal:"                 # results:cal:<region> = {"at": ISO time, "rows": [...]}
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
    return {"at": cal.get("at"), "rows": [r for r in cal.get("rows") or [] if isinstance(r, dict) and r.get("date")]}


def save(region: str, rows: list[dict]):
    rows = sorted(rows, key=lambda r: (r["date"], r["symbol"]))[:MAX_ROWS]
    db.set_setting(KEY + region, json.dumps({"at": datetime.now(ZoneInfo(TZ[region])).isoformat(timespec="minutes"), "rows": rows}))


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
DAY_ROWS = 40          # rows a day shows at first on "All companies"; the rest of that day opens on request (DE-026)


def view(region: str, uid: str, scope: str = "mine", q: str = "", today: date | None = None, limit: int = DAY_ROWS,
         day: str | None = None) -> dict:
    """This week and next, Monday to Sunday: the user's own stocks, or every company in the calendar, day by day.
    Every day is listed with how many companies it has; on "All companies" a day shows its first `limit` rows (the
    user's own first) and says how many more it has, and `day` (ISO) asks for one day in full. DE-026: a cut at the
    400th row of the week dropped all of Saturday 31 Oct (NTPC among them) under "And 66 more"."""
    today = today or local_today(region)
    cal = load(region)
    mine = set(my_stocks(uid, region))
    q = re.sub(r"[^A-Z0-9&.\- ]", "", (q or "").upper()).strip()[:30]
    day = day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(day or "")) else None
    weeks, more = [], 0
    for label, start in (("This week", week_of(today)[0]), ("Next week", week_of(today)[0] + timedelta(days=7))):
        end = start + timedelta(days=6)
        rows = [r for r in cal["rows"] if start.isoformat() <= r["date"] <= end.isoformat()
                and (scope == "all" or r["symbol"] in mine)
                and (not q or q in r["symbol"] or q in str(r.get("name") or "").upper())]
        rows.sort(key=lambda r: (r["date"], r["symbol"] not in mine, r["symbol"]))
        days, shown = [], []
        for d in sorted({r["date"] for r in rows}):
            on = [r for r in rows if r["date"] == d]
            cap = len(on) if scope != "all" or d == day else max(1, limit)
            shown += on[:cap]
            days.append({"date": d, "count": len(on), "shown": min(cap, len(on))})
            more += max(0, len(on) - cap)
        weeks.append({"label": label, "from": start.isoformat(), "to": end.isoformat(), "days": days,
                      "rows": [{**r, "mine": r["symbol"] in mine} for r in shown]})
    return {"region": region, "scope": scope, "today": today.isoformat(), "updated_at": cal["at"], "weeks": weeks,
            "more": more, "day_rows": limit, "mine_count": len(mine), "alerts": alerts_on(uid), "note": NOTE}
