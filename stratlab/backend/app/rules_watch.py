"""The daily rules watch: the official sources that publish a rate or rule in a form a program can read, fetched once
a day and compared with what StratLab uses (rules.py lists them all). A change is emailed to the admins and shown in
Admin → Quality → Rates and rules until an admin marks it seen. Nothing is ever applied by itself: a changed rate is changed in the
code, with a test, by a person.

Sources:
- NSE's F&O lot sizes (fo_mktlots.csv): the index lots, against the last copy read (the app reads lots from the
  broker each day, so this is for the record).
- The SEC's fee rate advisories: the latest Section 31 advisory (linked from the list page) against engine/costs.py US_SEC_FEE.
- The PPF rate table on the National Savings Institute's site against money_networth.py PPF_RATE.
- NSE's circulars: any new one about transaction charges, freeze limits, lot sizes, STT, expiry days or trading hours.
  Freeze limits come only this way: NSE stopped publishing its qtyfreeze file in March 2024 (NSE/FAOP/61157), and
  the old address now opens that circular.

Kept in one app_settings row (ruleswatch:state); the day it last ran in ruleswatch:day, so a restart never runs it
twice or sends an alert twice."""
import csv
import hashlib
import html
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from . import alerts, db, leader
from .http_retry import real_transport

KEY = "ruleswatch:state"
DAY_KEY = "ruleswatch:day"
IST = ZoneInfo("Asia/Kolkata")
RUN_AT = "07:40"                     # India time, every day: before the market opens
TIMEOUT = 20
MAX_SEEN = 400                       # circulars remembered
INDICES = ("NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50", "NIFTYFPI")
CIRCULAR_DAYS = 14
CIRCULAR_WORDS = re.compile(r"transaction charge|quantity freeze|freeze limit|lot size|securities transaction tax|\bSTT\b|"
                            r"expiry day|weekly expiry|trading hours|market timing|contract specification|\bIPFT\b", re.I)
SEC_UA = "StratLab research (contact@stratlab.studio)"


# ---------- reading each source ----------
def _cells(line: str) -> list[str]:
    """One line's cells: comma or tab separated, quotes ("1,440") kept together."""
    row = next(csv.reader([line], delimiter="\t" if "\t" in line else ","), [])
    return [c.strip() for c in row]


def read_lots(text: str) -> dict[str, int]:
    """{index: lot size} for the nearest month, from NSE's market lots CSV (UNDERLYING, SYMBOL, then a lot per month)."""
    out = {}
    for line in (text or "").splitlines():
        cells = _cells(line)
        up = [c.upper() for c in cells]
        hit = next((i for i, c in enumerate(up) if c in INDICES), None)
        if hit is None or up[hit] in out:
            continue
        lot = next((int(c) for c in cells[hit + 1:] if re.fullmatch(r"\d+", c)), None)
        if lot:
            out[up[hit]] = lot
    if not out:
        raise ValueError("No index lot sizes found in the file.")
    return out


def _text(page: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page or "")))


def sec_advisory_link(page: str) -> str | None:
    """The newest Section 31 advisory's address from the SEC's list page: the list names filing-fee (Section 6(b))
    advisories too, and holds no rate itself (R84-007: unread for 20 days after the page moved the rates out)."""
    for m in re.finditer(r'<a\b[^>]*href="([^"]*fee-rate-advisories/\d{4}-\d+)"[^>]*>(.*?)</a>', page or "", re.I | re.S):
        if re.search(r"Section\s*31", _text(m.group(2)), re.I):
            return m.group(1) if m.group(1).startswith("http") else "https://www.sec.gov" + m.group(1)
    return None


def read_sec_fee(page: str) -> float:
    """The latest Section 31 rate, in dollars a million, from the SEC's fee rate advisories page (the first one
    named on it is the newest)."""
    m = re.search(r"\$\s?(\d{1,3}\.\d{2})\s*per\s*million", _text(page), re.I)
    if not m:
        raise ValueError("No fee rate ($ per million) found on the page.")
    return float(m.group(1))


def read_ppf(page: str) -> float:
    """The PPF rate, % a year: the newest row of the National Savings Institute's rate table ("01.04.2020 TO
    30.09.2026 7.1"), else the first rate named after PPF on a rates page."""
    t = _text(page)
    rows = re.findall(r"(\d{2})\.(\d{2})\.(\d{4})\s*TO\s*\d{2}\.\d{2}\.\d{4}\s*(\d{1,2}\.\d{1,2})(?![\d.])", t, re.I)
    if rows and re.search(r"Public\s+Provident\s+Fund|\bPPF\b", t, re.I):
        d, m, y, rate = max(rows, key=lambda r: (r[2], r[1], r[0]))
        if 3 <= float(rate) <= 15:
            return float(rate)
    for m in re.finditer(r"(?:Public\s+Provident\s+Fund|\bPPF\b)(.{0,240})", _text(page), re.I):
        for n in re.finditer(r"(?<![\d.])(\d{1,2}\.\d{1,2})(?![\d.])", m.group(1)):
            v = float(n.group(1))
            if 3 <= v <= 15:
                return v
    raise ValueError("No PPF rate found on the page.")


def read_circulars(data, words: re.Pattern | None = None) -> list[dict]:
    """[{id, date, subject, url}] from NSE's circulars answer, read loosely (whatever the fields are called), keeping
    only those about the rules StratLab hard-codes (or those whose subject matches `words`)."""
    words = words or CIRCULAR_WORDS
    rows: list[dict] = []

    def walk(x, depth=0):
        if depth > 5:
            return
        if isinstance(x, list):
            for r in x:
                if isinstance(r, dict):
                    rows.append(r)
                walk(r, depth + 1)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v, depth + 1)
    walk(data)
    out = []
    for r in rows:
        subject = next((str(v) for k, v in r.items() if "sub" in str(k).lower() and isinstance(v, str)), "")
        if not subject or not words.search(subject):
            continue
        day = next((str(v) for k, v in r.items() if "date" in str(k).lower() and v), "")
        link = next((str(v) for k, v in r.items() if any(w in str(k).lower() for w in ("link", "file")) and isinstance(v, str)
                     and v.startswith("http")), "")
        no = next((str(v) for k, v in r.items() if re.search(r"no$|number", str(k), re.I) and isinstance(v, (str, int))), "")
        # the department that wrote it ("FAOP" for equity F&O), when the answer says
        low = {str(k).lower(): v for k, v in r.items()}
        dept = next((str(low[k]) for k in ("filedept", "dept", "circdepartment", "department")
                     if isinstance(low.get(k), str) and low[k]), "")
        cid = hashlib.sha1(f"{day}|{subject}".encode()).hexdigest()[:16]
        # NSE sends both "cirDate": "20261001" and "cirDisplayDate": "October 01, 2026": the id keeps the first (so a
        # circular seen before stays seen), the message shows the one people read
        shown = next((str(v) for k, v in r.items() if "display" in str(k).lower() and "date" in str(k).lower() and v), day)
        out.append({"id": cid, "date": shown[:30], "subject": subject[:300], "url": link[:300], "no": no[:60], "dept": dept[:60]})
    return out


# ---------- the sources ----------
def _expected_sec(today: date):
    from .engine.costs import US_SEC_FEE
    return round(US_SEC_FEE * 1e6, 2)


def _expected_ppf(today: date):
    from .money_networth import PPF_RATE
    return PPF_RATE


SOURCES = [
    {"id": "nse_lots", "name": "NSE index lot sizes", "area": "market_rules", "how": "nse_file",
     "url": "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv", "read": read_lots, "expected": None,
     "where": "read from the broker each day; for the record"},
    {"id": "sec_fee", "name": "SEC fee rate", "area": "trading_costs", "how": "sec",
     "url": "https://www.sec.gov/rules-regulations/fee-rate-advisories", "read": read_sec_fee, "expected": _expected_sec,
     "where": "engine/costs.py US_SEC_FEE ($ a million)"},
    {"id": "ppf", "name": "PPF rate", "area": "interest_rates", "how": "web",
     # the table page, over http: the https site sends a certificate chain that can't be checked (R84-007), and Id_Pk=79
     # was the scheme's rules, whose first rate is 1968's 4.8%
     "url": "http://www.nsiindia.gov.in/InternalPage.aspx?Id_Pk=178", "read": read_ppf, "expected": _expected_ppf,
     "where": "money_networth.py PPF_RATE (% a year)"},
    {"id": "nse_circulars", "name": "NSE circulars on charges and contract rules", "area": "market_rules", "how": "nse_circulars",
     "url": "https://www.nseindia.com/resources/exchange-communication-circulars", "read": read_circulars, "expected": None,
     "where": "engine/costs.py, options/data.py"},
]


def _same(value, expected) -> bool:
    """Whether what the source says matches what the code uses: every index both name for a table, else the number."""
    if isinstance(value, dict) and isinstance(expected, dict):
        return all(expected[k] == v for k, v in value.items() if k in expected)
    try:
        return abs(float(value) - float(expected)) < 1e-6
    except (TypeError, ValueError):
        return value == expected


def _moved(was, value) -> bool:
    """Whether a source's value changed: for a table, a row it had that now reads differently or is gone. A row read for
    the first time (NIFTYFPI's lot, once the file listed it) is kept without an alert (R85-003)."""
    if isinstance(was, dict) and isinstance(value, dict):
        return any(k not in value or value[k] != v for k, v in was.items())
    return json.dumps(was, sort_keys=True) != json.dumps(value, sort_keys=True)


def _diff_keys(was, value) -> set | None:
    """A table's rows that moved, for the alert to name; None for a single value."""
    if isinstance(was, dict) and isinstance(value, dict):
        return {k for k in set(was) | set(value) if was.get(k) != value.get(k)}
    return None


def _only(value, keys):
    return {k: v for k, v in value.items() if k in keys} if keys and isinstance(value, dict) else value


def _show(value) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k} {v:,}" if isinstance(v, (int, float)) else f"{k} {v}" for k, v in value.items())
    return f"{value:g}" if isinstance(value, float) else str(value)


# ---------- the stored state ----------
def state() -> dict:
    """{"sources": [...], "last_run"}: each source with its last value, what the code uses, the change waiting for an
    admin (pending) and the last error."""
    got = db.json_value(db.get_setting(KEY), {})
    got = got if isinstance(got, dict) else {}
    have = {s.get("id"): s for s in got.get("sources") or [] if isinstance(s, dict)}
    out = []
    for src in SOURCES:
        s = have.get(src["id"]) or {}
        out.append({"id": src["id"], "name": src["name"], "area": src["area"], "url": src["url"], "where": src["where"],
                    "checked": s.get("checked"), "value": s.get("value"), "shown": s.get("shown"),
                    "expected": s.get("expected"), "error": _plain_error(s.get("error")), "fails": int(s.get("fails") or 0),
                    "pending": _added_only(_once(s.get("pending"))), "alerted": s.get("alerted"), "seen": s.get("seen") or []})
    return {"sources": out, "last_run": got.get("last_run")}


def _plain_error(e) -> str | None:
    """A source's failure in words: "[SSL: CERTIFICATE_VERIFY_FAILED] …" says the site's certificate couldn't be checked
    (R57-014); anything else as it came. Takes the exception, or an error already stored (R58-002: one saved before this
    showed raw until the next morning's read)."""
    if e is None:
        return None
    text = e if isinstance(e, str) else (str(getattr(e, "message", None) or e) or e.__class__.__name__)
    if "CERTIFICATE_VERIFY_FAILED" in text or "SSLCertVerificationError" in text:
        return "The site's security certificate couldn't be checked, so the page wasn't read."
    return text[:200]


def _rows(text) -> dict | None:
    """A table as _show writes it ("NIFTY 65, BANKNIFTY 30, NIFTYFPI 1,100") back into its rows; None for one value."""
    if not isinstance(text, str) or not text:
        return None
    out = {}
    for part in re.split(r",\s+(?=[A-Za-z])", text):
        name, _, val = part.strip().rpartition(" ")
        if not name:
            return None
        out[name] = val
    return out


def _added_only(pending):
    """None for a "changed at the source" table whose rows all read as they did, with rows only added: stored before a
    first-time row stopped counting as a change (R90-003: "NSE index lot sizes" waiting for a look, NIFTYFPI newly listed
    and every other lot the same), it no longer waits for one."""
    if not isinstance(pending, dict) or pending.get("why") != "changed at the source":
        return pending
    was, now = _rows(pending.get("was")), _rows(pending.get("now"))
    if was and now and all(now.get(k) == v for k, v in was.items()):
        return None
    return pending


def _once(pending):
    """A change waiting for a look with each circular in it once: a list stored before the exchange's repeats were
    dropped named one circular four times (R56-007)."""
    if not isinstance(pending, dict) or not isinstance(pending.get("items"), list):
        return pending
    seen, items = set(), []
    for c in pending["items"]:
        # by day and subject: the four copies may carry ids made from different date fields
        key = (str(c.get("date")), " ".join(str(c.get("subject")).lower().split())) if isinstance(c, dict) else repr(c)
        if key not in seen:
            seen.add(key)
            items.append(c)
    return {**pending, "items": items}


def _save(st: dict):
    db.set_setting(KEY, json.dumps(st, separators=(",", ":"), default=str))


def mark_seen(source_id: str) -> bool:
    """An admin has looked at a source's change: it stops showing (the same value never alerts again)."""
    st = state()
    hit = next((s for s in st["sources"] if s["id"] == source_id), None)
    if not hit or not hit["pending"]:
        return False
    hit["pending"] = None
    _save(st)
    return True


# ---------- one run ----------
class Fetcher:
    """How each kind of source is read: NSE's files and API through the exchange feed (it holds the cookies NSE asks
    for), anything else with a plain request."""

    def __init__(self, feed=None, http: httpx.Client | None = None):
        self.feed = feed
        self.http = http

    def _client(self) -> httpx.Client:
        if self.http is None:
            self.http = httpx.Client(timeout=TIMEOUT, follow_redirects=True, transport=real_transport(), headers={"User-Agent": SEC_UA})
        return self.http

    def get(self, src: dict, today: date):
        if src["how"] == "nse_file":
            return self.feed().nse._surv_text(src["url"])
        if src["how"] == "nse_circulars":
            frm = (today - timedelta(days=CIRCULAR_DAYS)).strftime("%d-%m-%Y")
            return self.feed().nse._get("/api/circulars", {"fromDate": frm, "toDate": today.strftime("%d-%m-%Y")},
                                        referer=src["url"], circuit="rules")
        r = self._client().get(src["url"])
        r.raise_for_status()
        if src["how"] == "sec" and (link := sec_advisory_link(r.text)):
            r = self._client().get(link)
            r.raise_for_status()
        return r.text


def run(fetch: Fetcher, today: date, now: datetime | None = None) -> list[str]:
    """Read every source once, keep what came back, and return the lines to alert the admins with (none when nothing
    changed). A source that can't be read keeps its last value and counts the failure."""
    now = now or datetime.now(timezone.utc)
    st = state()
    by = {s["id"]: s for s in st["sources"]}
    lines: list[str] = []
    for src in SOURCES:
        s = by[src["id"]]
        s["checked"] = now.isoformat(timespec="minutes")
        try:
            value = src["read"](fetch.get(src, today))
        except Exception as e:
            s["error"] = _plain_error(e)
            s["fails"] += 1
            continue
        s["error"], s["fails"] = None, 0
        if src["id"] == "nse_circulars":
            first = not s["seen"]            # the first run only learns what is there
            # once each: the exchange's list can carry one circular twice (R52-009: "5 changes", 3 circulars)
            # by id and by day and subject: copies of one circular can carry ids made from different date fields, and
            # the alert listed one circular four times under "5 rate or rule changes" (R59-002)
            seen_now: set = set()
            key = lambda c: (str(c.get("date")), " ".join(str(c.get("subject")).lower().split()))
            # and by its file: one circular's zip listed under two subjects (R69-005: "5 changes", CMTR76963.zip twice)
            new = [c for c in value if c["id"] not in set(s["seen"])
                   and not (c["id"] in seen_now or key(c) in seen_now or (c.get("url") and c["url"] in seen_now)
                            or seen_now.update(x for x in (c["id"], key(c), c.get("url")) if x))]
            if new and not first:
                s["pending"] = _once({"at": now.isoformat(timespec="minutes"), "why": "new circular",
                                      "items": (((s["pending"] or {}).get("items") or []) + new)[-20:]})
                # the address after a dash, not in brackets: the email turns it into a link, which left a stray "(" (R52-009)
                lines += [f"- NSE circular {c['date']}: {_whole(c['subject'])}" + (f" — {c['url']}" if c["url"] else "") for c in new[:10]]
            s["seen"] = (s["seen"] + [c["id"] for c in new])[-MAX_SEEN:] or ["-"]
            # each circular once: the exchange's list repeats some, and "5 matching" sat over a list of 2 (R57-014)
            n = len({(c.get("date"), " ".join(str(c.get("subject")).lower().split())) for c in value})
            s["value"], s["shown"] = n, f"{n} matching circular{'' if n == 1 else 's'} in the last {CIRCULAR_DAYS} days"
            continue
        expected = src["expected"](today) if src["expected"] else None
        fp = hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]
        was = s["value"]
        changed = was is not None and _moved(was, value)
        differs = expected is not None and not _same(value, expected)
        if (changed or differs) and fp != s["alerted"]:
            why = "differs from what StratLab uses" if differs else "changed at the source"
            # a table names only what moved: "now NIFTY 65, BANKNIFTY 30, … was NIFTY 65, BANKNIFTY 30, …" read as no change (R85-003)
            keys = _diff_keys(was, value) if changed and not differs else None
            s["pending"] = {"at": now.isoformat(timespec="minutes"), "why": why, "was": _show(_only(was, keys)) if was is not None else None,
                            "now": _show(_only(value, keys)), "uses": _show(expected) if expected is not None else None}
            s["alerted"] = fp
            lines.append(f"- {src['name']}: {why}. Source now says {_show(_only(value, keys))}"
                         + (f"; StratLab uses {_show(expected)} ({src['where']})" if expected is not None else
                            f"; it said {_show(_only(was, keys))} before" if was is not None else "") + f". {src['url']}")
        elif expected is not None and not differs and s["pending"] and s["pending"].get("why") == "differs from what StratLab uses":
            s["pending"] = None        # the code was updated to match
        s["value"], s["shown"] = value, _show(value)
        s["expected"] = _show(expected) if expected is not None else None
    st["last_run"] = now.isoformat(timespec="minutes")
    _save(st)
    return lines


def _whole(subject) -> str:
    """A circular's subject without a bracket the exchange's list cut off ("… Corporate Bonds (" read as a broken line,
    R69-005)."""
    t = " ".join(str(subject or "").split())
    while t.count("(") > t.count(")") and "(" in t:
        t = t[:t.rfind("(")].rstrip(" -–:,")
    return t


def alert_text(lines: list[str]) -> tuple[str, str]:
    n = len(lines)
    return (f"StratLab: {n} rate or rule change{'s' if n > 1 else ''} at the source",
            "Today's rules watch found:\n" + "\n".join(lines) + "\n\nNothing in StratLab changes by itself. Check the source, "
            "update the value in the code (with a test) if it applies, and mark it seen in Admin → Quality → Rates and rules.")


class Job:
    """Once a day at RUN_AT (India time); the day is marked before it runs, so it runs and alerts once."""

    def __init__(self, feed=None, tell=None, fetcher: Fetcher | None = None):
        self.fetcher = fetcher or Fetcher(feed)
        self.tell = tell or alerts.tell_admins
        self.status = {"last_run": None, "alerted": 0, "last_error": None}

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="rules-watch").start()

    def _loop(self):
        while True:
            try:
                if leader.leading():      # another container leads: it runs this pass
                    self.tick(datetime.now(timezone.utc))
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("rules watch:", e)
            time.sleep(600)

    def tick(self, now: datetime) -> int:
        local = now.astimezone(IST)
        day = local.date().isoformat()
        if local.strftime("%H:%M") < RUN_AT or db.get_setting(DAY_KEY) == day:
            return 0
        db.set_setting(DAY_KEY, day)
        return self.run_now(now)

    def run_now(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        lines = run(self.fetcher, now.astimezone(IST).date(), now)
        if lines:
            self.tell(*alert_text(lines))
        self.status.update(last_run=now.isoformat(), alerted=len(lines), last_error=None)
        return len(lines)
