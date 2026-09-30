"""Company filings from the exchange (NSE corporate announcements), sorted into a timeline and checked against
fixed red-flag rules: fund raises (QIP, preferential, rights, warrants), promoter pledges, key resignations,
defaults, regulator action and rating downgrades.

Everything here is a fact from a public filing and a fixed keyword rule the user can read, never a judgement or
advice. The exchange's own wording and document link are always shown next to our label."""
import json
import re
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .. import db
from .net import BROWSER_UA, SourceError, TTLCache, RateLimit

IST = ZoneInfo("Asia/Kolkata")
WINDOW_DAYS = 90             # the "last 3 months" summary
LOOKBACK_DAYS = 365          # how far back the timeline goes

# (id, label, severity, patterns). First match wins, so the specific rules come before the broad ones.
# severity: "red" = a red flag the investor asked to see, "amber" = worth a look, "info" = routine.
RULES: list[tuple[str, str, str, list[str]]] = [
    ("auditor_resign", "Auditor resigned", "red", [r"resignation of (the )?(statutory |secretarial |internal )?auditor", r"auditors? .{0,40}resign"]),
    ("default", "Default or delayed payment", "red", [r"\bdefault\b", r"delay in (payment|servicing)", r"non[- ]payment of (interest|principal)"]),
    ("insolvency", "Insolvency proceedings", "red", [r"insolvency", r"\bnclt\b", r"\bibc\b", r"corporate insolvency resolution"]),
    ("qip", "QIP (fund raise)", "red", [r"qualified institutions? placement", r"\bqip\b"]),
    ("preferential", "Preferential issue (fund raise)", "red", [r"preferential (issue|allotment|basis)"]),
    ("rights", "Rights issue (fund raise)", "red", [r"rights issue", r"issue .{0,20}on rights basis"]),
    ("warrants", "Warrants issued (fund raise)", "red", [r"convertible warrants", r"issue of warrants", r"allotment of warrants"]),
    ("fund_raise", "Fund raise approved or planned", "red", [r"fund[- ]?rais", r"raising of funds", r"raise funds"]),
    ("pledge", "Promoter pledge or encumbrance", "red", [r"\bpledge", r"encumbrance", r"regulation 31\b"]),
    ("regulator", "Regulator or tax action", "red", [r"\bsebi\b.{0,40}(order|penalt|show cause|adjudicat)", r"show[- ]cause", r"search (and|&) seizure",
                                                   r"income tax (search|survey)", r"enforcement directorate", r"\bpenalty\b"]),
    ("rating_down", "Credit rating downgraded", "red", [r"downgrad", r"rating .{0,30}(revised|placed) .{0,30}(negative|watch)"]),
    ("kmp_resign", "Director or key officer resigned", "amber", [r"resignation", r"resigned", r"cessation"]),
    ("ncd", "Debt raise (NCDs or bonds)", "amber", [r"non[- ]convertible debentures", r"\bncds?\b", r"commercial paper", r"\bbonds?\b"]),
    ("results", "Financial results", "info", [r"financial results", r"outcome of board meeting.{0,60}results", r"\bresults\b"]),
    ("concall", "Earnings call", "info", [r"transcript", r"earnings call", r"conference call", r"analysts?/institutional investor meet", r"investor meet"]),
    ("presentation", "Investor presentation", "info", [r"investor presentation", r"presentation"]),
    ("dividend", "Dividend", "info", [r"dividend"]),
    ("buyback", "Buyback", "info", [r"buy[- ]?back"]),
    ("order", "Order or contract", "info", [r"order (win|received|bagged)", r"bagging", r"receipt of (an )?order", r"award of contract", r"letter of award"]),
    ("deal", "Acquisition, merger or stake", "info", [r"acquisition", r"amalgamation", r"merger", r"scheme of arrangement", r"stake"]),
    ("rating", "Credit rating", "info", [r"credit rating", r"\brating\b"]),
    ("board", "Board meeting", "info", [r"board meeting"]),
    ("agm", "Shareholder meeting", "info", [r"\bagm\b", r"\begm\b", r"annual general meeting", r"postal ballot"]),
]
_COMPILED = [(i, label, sev, [re.compile(p, re.I) for p in pats]) for i, label, sev, pats in RULES]
FUND_RAISE = {"qip", "preferential", "rights", "warrants", "fund_raise"}
LABEL = {i: label for i, label, _, _ in RULES} | {"other": "Other update"}


def ist_now() -> datetime:
    """Now in India, without a zone, to compare with the exchange's (IST, zoneless) filing times."""
    return datetime.now(IST).replace(tzinfo=None)


def classify(desc: str, text: str) -> tuple[str, str]:
    """(category id, severity) for one announcement, from the exchange's subject and summary."""
    hay = f"{desc or ''} || {text or ''}"
    for cid, _, sev, rx in _COMPILED:
        if any(r.search(hay) for r in rx):
            return cid, sev
    return "other", "info"


def _date(s: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime((s or "").strip(), fmt)
        except ValueError:
            continue
    return None


def normalise(raw: list[dict]) -> list[dict]:
    """The exchange's rows as timeline items, newest first; rows without a date are dropped."""
    out, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        when = _date(r.get("sort_date") or r.get("an_dt") or r.get("exchdisstime") or "")
        if not when:
            continue
        subject = str(r.get("desc") or "").strip()[:200]
        text = re.sub(r"\s+", " ", str(r.get("attchmntText") or "")).strip()[:600]
        key = r.get("seq_id") or (when.isoformat(), subject, text[:80])
        if key in seen:
            continue
        seen.add(key)
        cid, sev = classify(subject, text)
        link = str(r.get("attchmntFile") or "")
        out.append({"id": str(r.get("seq_id") or abs(hash(key)))[:40], "at": when.isoformat(timespec="minutes"),
                    "category": cid, "label": LABEL[cid], "severity": sev, "subject": subject, "text": text,
                    "url": link if link.startswith("https://") else None})
    out.sort(key=lambda x: x["at"], reverse=True)
    return out


def summarise(items: list[dict], now: datetime | None = None) -> dict:
    """The last-3-months view: red flags, whether a fund raise happened, and counts by category."""
    now = now or ist_now()
    cutoff = (now - timedelta(days=WINDOW_DAYS)).isoformat()
    recent = [i for i in items if i["at"] >= cutoff]
    red = [i for i in recent if i["severity"] == "red"]
    counts: dict[str, int] = {}
    for i in recent:
        counts[i["category"]] = counts.get(i["category"], 0) + 1
    raise_ = [i for i in recent if i["category"] in FUND_RAISE]
    return {"days": WINDOW_DAYS, "total": len(recent), "red": len(red), "amber": sum(1 for i in recent if i["severity"] == "amber"),
            "fund_raise": bool(raise_), "fund_raise_last": raise_[0]["at"] if raise_ else None,
            "flags": [{"category": c, "label": LABEL[c], "count": n} for c, n in sorted(counts.items(), key=lambda kv: -kv[1])
                      if any(i["category"] == c and i["severity"] != "info" for i in recent)]}


class NSEFilings:
    """NSE's public corporate-announcements feed. The site hands out session cookies on its home page and refuses
    API calls without them, so we visit the home page first and again whenever the cookies expire."""
    name = "the exchange"
    BASE = "https://www.nseindia.com"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.http = httpx.Client(base_url=self.BASE, timeout=15, transport=transport, follow_redirects=True,
                                 headers={"User-Agent": BROWSER_UA, "Accept": "application/json, text/plain, */*",
                                          "Accept-Language": "en-US,en;q=0.9", "Referer": self.BASE + "/"})
        self.limit = RateLimit(30, 5)
        self.cache = TTLCache(max_items=2000)
        self._primed = 0.0
        self._lock = threading.Lock()

    def _prime(self, force: bool = False):
        with self._lock:
            if not force and time.time() - self._primed < 600:
                return
            try:
                self.http.get("/", headers={"Accept": "text/html"})
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"Couldn't reach the exchange ({e.__class__.__name__}).", busy=True) from None
            self._primed = time.time()

    def _get(self, path: str, params: dict):
        self._prime()
        for attempt in (0, 1):
            if not self.limit.take():
                raise SourceError(self.name, "The exchange feed is busy (our rate limit). Try again in a minute.", busy=True)
            try:
                r = self.http.get(path, params=params)
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"Couldn't reach the exchange ({e.__class__.__name__}).", busy=True) from None
            if r.status_code in (401, 403) and attempt == 0:
                self._prime(force=True)          # cookies expired: fetch fresh ones once
                continue
            if r.status_code == 429 or r.status_code >= 500:
                raise SourceError(self.name, f"The exchange feed is busy ({r.status_code}). Try again in a minute.", busy=True)
            if r.status_code >= 400:
                raise SourceError(self.name, f"The exchange feed refused the request ({r.status_code}).")
            try:
                return r.json()
            except ValueError:
                raise SourceError(self.name, "The exchange sent a page instead of data (it may be blocking us).") from None
        raise SourceError(self.name, "The exchange feed refused the request after a fresh session.")

    def announcements(self, symbol: str, days: int = LOOKBACK_DAYS) -> list[dict]:
        key = (symbol, days)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        to = ist_now()
        data = self._get("/api/corporate-announcements", {
            "index": "equities", "symbol": symbol,
            "from_date": (to - timedelta(days=days)).strftime("%d-%m-%Y"), "to_date": to.strftime("%d-%m-%Y")})
        rows = data.get("data") if isinstance(data, dict) else data
        items = normalise(rows or [])
        self.cache.set(key, items, 1800)
        return items


def report(feed, symbol: str) -> dict:
    """Timeline plus the 3-month summary for one NSE symbol."""
    items = feed.announcements(symbol)
    return {"symbol": symbol, "items": items[:200], "summary": summarise(items), "window_days": WINDOW_DAYS,
            "lookback_days": LOOKBACK_DAYS}


# ---------- the daily watchlist red-flag alert ----------
ALERT_KEY = "filingalert:"            # app_settings: filingalert:<uid> = {"uid", "on", "seen": ISO time of the newest filing seen}
SEND_AT = "20:30"                     # IST, after most companies have filed for the day
MAX_SYMBOLS = 25


def alert_state(uid: str) -> dict:
    try:
        return json.loads(db.get_setting(ALERT_KEY + uid) or "{}")
    except (ValueError, TypeError):
        return {}


def set_alert(uid: str, on: bool):
    st = alert_state(uid)
    st.update(uid=uid, on=bool(on))
    if on and not st.get("seen"):     # start from now: only filings made after switching on are sent
        st["seen"] = ist_now().isoformat(timespec="minutes")
    db.set_setting(ALERT_KEY + uid, json.dumps(st))


def watchlist_symbols(uid: str) -> list[str]:
    try:
        items = json.loads(db.get_setting(f"watchlist:{uid}") or "{}").get("items") or []
    except (ValueError, TypeError):
        items = []
    return [i["symbol"] for i in items if i.get("region") == "IN" and i.get("symbol")][:MAX_SYMBOLS]


def overview(feed, symbols: list[str]) -> dict:
    """The 3-month summary for each watchlist stock, the ones with red flags first."""
    rows, problems = [], []
    for sym in symbols:
        try:
            items = feed.announcements(sym)
        except SourceError as e:
            problems.append(f"{sym}: {e}")
            continue
        s = summarise(items)
        cutoff = (ist_now() - timedelta(days=WINDOW_DAYS)).isoformat()
        rows.append({"symbol": sym, "summary": s,
                     "flags": [i for i in items if i["severity"] != "info" and i["at"] >= cutoff][:5]})
    rows.sort(key=lambda r: (-r["summary"]["red"], -r["summary"]["amber"], r["symbol"]))
    return {"rows": rows, "problems": problems, "days": WINDOW_DAYS}


def alert_text(new: list[tuple[str, dict]]) -> str:
    parts = [f"{sym}: {i['label']}" for sym, i in new[:8]]
    more = f" and {len(new) - 8} more" if len(new) > 8 else ""
    return "New filings on your watchlist: " + "; ".join(parts) + more + ". From the exchange's filings; not advice."


class Alerts:
    """Once a day in the evening, send each subscriber the red and amber filings their watchlist stocks made since
    the last message."""

    def __init__(self, feed, notify, can_alert):
        self.feed, self.notify, self.can_alert = feed, notify, can_alert
        self.last_day = None
        self.status = {"last_run": None, "sent": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="filing-alerts").start()

    def _loop(self):
        while True:
            try:
                self.tick(datetime.now(IST))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("filing alerts:", e)
            time.sleep(300)

    def due(self, now: datetime) -> str | None:
        local = now.astimezone(IST)
        day = local.date().isoformat()
        if local.strftime("%H:%M") < SEND_AT or self.last_day == day:
            return None
        if db.get_setting("filingalert-day") == day:         # already sent today (before a restart)
            self.last_day = day
            return None
        return day

    def tick(self, now: datetime):
        day = self.due(now)
        if not day:
            return
        self.last_day = day
        db.set_setting("filingalert-day", day)
        sent = 0
        for raw in db.settings_with_prefix(ALERT_KEY):
            try:
                sub = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if not sub.get("on"):
                continue
            profile = db.get_profile(sub["uid"])
            symbols = watchlist_symbols(sub["uid"])
            if not symbols or not self.can_alert(profile):
                continue
            seen, newest, new = sub.get("seen") or "", sub.get("seen") or "", []
            for sym in symbols:
                try:
                    items = self.feed.announcements(sym)
                except SourceError:
                    continue
                for i in items:
                    if i["at"] > seen and i["severity"] != "info":
                        new.append((sym, i))
                    newest = max(newest, i["at"])
            if new:
                new.sort(key=lambda x: (x[1]["severity"] != "red", x[1]["at"]))
                self.notify(profile, "StratLab: new filings to look at", alert_text(new), url="/research/filings")
                sent += 1
            sub["seen"] = newest
            db.set_setting(ALERT_KEY + sub["uid"], json.dumps(sub))
        self.status.update(last_run=now.isoformat(), sent=sent, last_error=None)
