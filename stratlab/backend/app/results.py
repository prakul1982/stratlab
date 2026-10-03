"""The results calendar: when companies report their quarterly results, in India and the US, and the results-day
messages to the people who track them.

India: board meetings called to consider financial results, from the exchange's board-meeting list. Companies listed
only on BSE (and everyone, when that list is down) are read from the board-meeting notices in their announcements.
US: the earnings dates in the US company data; once a company has reported, the same feed carries the reported EPS
and revenue, and the SEC's filing list has the earnings release (8-K, item 2.02).

Each region's calendar is stored as results:cal:<region>, a rolling window from a week back to four weeks ahead,
refreshed in the background. Facts only: a date, the company's own stated purpose and, once results are filed, a
link to the filing and the numbers it states. Never a view on them."""
import json
import re
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import alerts, db
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


def _json(raw, default):
    try:
        v = json.loads(raw or "null")
    except (ValueError, TypeError):
        return default
    return v if isinstance(v, type(default)) else default


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


def india_rows(raw: list) -> list[dict]:
    """The exchange's board meetings that are about financial results."""
    out = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        sym = str(r.get("bm_symbol") or r.get("symbol") or "").strip().upper()
        purpose = str(r.get("bm_purpose") or r.get("purpose") or "").strip()
        desc = re.sub(r"\s+", " ", str(r.get("bm_desc") or r.get("desc") or "")).strip()
        day = parse_day(r.get("bm_date") or r.get("date"))
        if not sym or not day or not RESULTS.search(f"{purpose} {desc}"):
            continue
        out.append(row("IN", sym, day, purpose or "Financial results", name=str(r.get("sm_name") or r.get("company") or "").strip() or None,
                       url=r.get("attachment") or r.get("bm_attachment")))
    return out


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
        day = next((d for d in dates_in(hay) if filed <= d <= filed + timedelta(days=60)), None)
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


def reported(r: dict) -> list[dict]:
    """The numbers a US company reported, as the results feed carries them: EPS and revenue (never the estimates)."""
    out = []
    if isinstance(r.get("epsActual"), (int, float)):
        out.append({"label": "EPS", "value": f"${r['epsActual']:.2f}"})
    rev = r.get("revenueActual")
    if isinstance(rev, (int, float)) and rev > 0:
        out.append({"label": "Revenue", "value": f"${rev / 1e9:,.2f} billion" if rev >= 1e9 else f"${rev / 1e6:,.1f} million"})
    return out


# ---------- storage ----------
def load(region: str) -> dict:
    cal = _json(db.get_setting(KEY + region), {})
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
        out[k] = {**r, "out": prior["out"]} if prior else r
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
    uids |= {_json(raw, {}).get("uid") for _, raw in db.all_settings_with_prefix(newsletter_prefs.KEY)}
    try:
        uids |= {r.get("user_id") for r in db.running_sessions()}
    except Exception:
        pass
    return {u for u in uids if isinstance(u, str) and u}


def my_stocks(uid: str, region: str | None = None) -> list[str]:
    """The user's stocks as the My Stocks newsletter sees them (watchlist, notebooks, paper sessions)."""
    from .newsletter import content
    return [s for r, s in content.my_stocks(uid) if region is None or r == region]


def trackers() -> dict[tuple[str, str], list[str]]:
    """(region, symbol) -> the users tracking it."""
    from .newsletter import content
    out: dict[tuple[str, str], list[str]] = {}
    for uid in sorted(users()):
        try:
            stocks = content.my_stocks(uid)
        except Exception:
            continue
        for k in stocks:
            out.setdefault(k, []).append(uid)
    return out


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
    tracked, rows, problems, whole = set(tracked or ()), [], [], False
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
        fh = sources.get("us")
        try:
            rows += us_rows(fh.earnings_between(frm, to))
            whole = True
        except (SourceError, AttributeError) as e:
            problems.append(str(e)[:160])
        if not whole:
            for sym in sorted(tracked)[:MAX_LOOKUPS]:
                try:
                    rows += us_rows(fh.earnings_calendar(sym))
                except (SourceError, AttributeError) as e:
                    problems.append(f"{sym}: {str(e)[:120]}")
    if not whole and not rows:
        return {"rows": None, "problems": problems}
    with _lock:
        old = load(region)["rows"]
        if not whole:                    # only some companies were asked: keep everyone else's dates as they were
            asked = {r["symbol"] for r in rows} | tracked
            rows += [r for r in old if r["symbol"] not in asked and r["date"] >= frm.isoformat()]
        merged = merge(old, rows, frm, today)
        save(region, merged)
    return {"rows": len(merged), "problems": problems}


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
            rel = next((d for d in sorted(documents(subs, days=14), key=lambda d: d["at"])
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
                    r["out"] = done[(r["symbol"], r["date"])]
            save(region, rows)
    return found


# ---------- the messages ----------
def _day(iso: str) -> str:
    try:
        return date.fromisoformat(iso[:10]).strftime("%a %d %b")
    except ValueError:
        return iso


def describe(r: dict) -> str:
    return r["purpose"] + (f", {r['when']}" if r.get("when") else "")


def morning_text(rows: list[dict]) -> str:
    parts = [f"{r['symbol']}: {describe(r)}" for r in rows[:10]]
    more = f" and {len(rows) - 10} more" if len(rows) > 10 else ""
    return "Results today for your stocks. " + "; ".join(parts) + more + ". " + NOTE


def out_text(r: dict) -> str:
    o = r["out"]
    nums = "; ".join(f"{n['label']} {n['value']}" for n in o.get("numbers") or [])
    return " ".join(x for x in (
        f"{r['symbol']} results are out: {o.get('title') or 'Results'} ({_day(o.get('at') or r['date'])}).",
        f"As stated: {nums}." if nums else "",
        o.get("url") or "", "From the company's filing. Not investment advice.") if x)


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


class Job:
    """Refreshes each region's calendar twice a day (India) or once (US), sends the morning results-day messages and,
    every hour after that, looks for the filings. Every run is marked in the database first, so it happens once."""

    def __init__(self, sources, send=send, can_alert=can_alert):
        self.sources, self.send, self.can_alert = sources, send, can_alert
        self.last: dict[str, str] = {}
        self.status = {"last_run": None, "sent": 0, "last_error": None, "problems": []}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="results-calendar").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(ZoneInfo("UTC")))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("results calendar:", e)
            time.sleep(300)

    def due(self, name: str, now: datetime, region: str, at: str, stamp: str = "%Y-%m-%d") -> date | None:
        """The local day when `name` is due (at or after `at`) and its marker (the day, or the hour) isn't set yet."""
        local = now.astimezone(ZoneInfo(TZ[region]))
        mark = local.strftime(stamp)
        if local.strftime("%H:%M") < at or self.last.get(name) == mark:
            return None
        if db.get_setting(f"resultsjob:{name}") == mark:          # already ran (before a restart)
            self.last[name] = mark
            return None
        self.last[name] = mark
        db.set_setting(f"resultsjob:{name}", mark)
        return local.date()

    def tick(self, now: datetime) -> int:
        sent, ran, who = 0, False, None
        for region in REGIONS:
            for at in REFRESH_AT[region]:
                day = self.due(f"refresh-{region}-{at}", now, region, at)
                if day:
                    who = who if who is not None else trackers()
                    self.refresh(region, who, day)
                    ran = True
            day = self.due(f"morning-{region}", now, region, MORNING_AT[region])
            if day:
                who = who if who is not None else trackers()
                sent, ran = sent + self.morning(region, day, who), True
            day = self.due(f"check-{region}", now, region, CHECK_FROM[region], stamp="%Y-%m-%dT%H")
            if day:
                who = who if who is not None else trackers()
                sent, ran = sent + self.follow_up(region, day, who), True
        if ran:
            self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
        return sent

    def refresh(self, region: str, who: dict | None = None, day: date | None = None) -> dict:
        who = who if who is not None else trackers()
        out = refresh(region, self.sources(), {s for (r, s) in who if r == region}, day)
        self.status["problems"] = out["problems"][:10]
        return out

    def morning(self, region: str, day: date, who: dict) -> int:
        """One message per person listing their stocks with results today."""
        if not load(region)["at"]:
            self.refresh(region, who, day)
        per_user: dict[str, list[dict]] = {}
        for r in between(region, day, day):
            for uid in who.get((region, r["symbol"]), []):
                per_user.setdefault(uid, []).append(r)
        sent = 0
        for uid, rows in per_user.items():
            profile = db.get_profile(uid)
            if not self.can_alert(profile):
                continue
            try:
                self.send(profile, "StratLab: results today", morning_text(rows), f"/research/results?region={region}")
                sent += 1
            except Exception as e:
                print("results message failed:", str(e)[:160])
        return sent

    def follow_up(self, region: str, day: date, who: dict) -> int:
        """Look for the filings of results days just gone, and tell the people tracking each company."""
        symbols = {s for (r, s) in who if r == region}
        sent = 0
        for r in check_out(region, self.sources(), symbols, day):
            for uid in who.get((region, r["symbol"]), []):
                profile = db.get_profile(uid)
                if not self.can_alert(profile):
                    continue
                try:
                    self.send(profile, f"StratLab: {r['symbol']} results are out", out_text(r), f"/research/{region}/{r['symbol']}")
                    sent += 1
                except Exception as e:
                    print("results message failed:", str(e)[:160])
        return sent


# ---------- the page ----------
def view(region: str, uid: str, scope: str = "mine", q: str = "", today: date | None = None, limit: int = 400) -> dict:
    """This week and next, Monday to Sunday: the user's own stocks, or every company in the calendar."""
    today = today or local_today(region)
    cal = load(region)
    mine = set(my_stocks(uid, region))
    q = re.sub(r"[^A-Z0-9&.\- ]", "", (q or "").upper()).strip()[:30]
    weeks, more = [], 0
    for label, start in (("This week", week_of(today)[0]), ("Next week", week_of(today)[0] + timedelta(days=7))):
        end = start + timedelta(days=6)
        rows = [r for r in cal["rows"] if start.isoformat() <= r["date"] <= end.isoformat()
                and (scope == "all" or r["symbol"] in mine)
                and (not q or q in r["symbol"] or q in str(r.get("name") or "").upper())]
        rows.sort(key=lambda r: (r["date"], r["symbol"] not in mine, r["symbol"]))
        more += max(0, len(rows) - limit)
        weeks.append({"label": label, "from": start.isoformat(), "to": end.isoformat(),
                      "rows": [{**r, "mine": r["symbol"] in mine} for r in rows[:limit]]})
    return {"region": region, "scope": scope, "today": today.isoformat(), "updated_at": cal["at"], "weeks": weeks,
            "more": more, "mine_count": len(mine), "alerts": alerts_on(uid), "note": NOTE}
