"""The Reserve Bank's published rates: the "Current Rates" panel of its home page (policy repo rate, standing facility
rates, the last T-bill auction cut-offs and benchmark G-sec yields, each with its "as on" date), read at most every
few hours with the last good copy kept for everyone (rates:rbi), and the repo rate's history since 2019 from the
Monetary Policy Committee's resolutions, for loan resets.

A repo rate on the home page that differs from the last one in the history is kept as a change seen on that day
(rates:repo_seen), so a new MPC decision counts before this file is updated. Nothing here is per user."""
import html
import json
import re
import threading
import time
from datetime import datetime, timezone

import httpx

from . import db

URL = "https://www.rbi.org.in/"
KEY = "rates:rbi"                  # {"at": unix time, "rates": {...}}
SEEN_KEY = "rates:repo_seen"       # [[YYYY-MM-DD, rate]] repo rates seen on the home page that the history lacks
MAX_AGE = 6 * 3600
RETRY = 1800
TIMEOUT = 30.0
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# the policy repo rate from each MPC decision (effective the day announced), checked against the RBI's monetary policy
# statements; 5.25% from 5 Dec 2025 is what the home page shows on 5 Oct 2026
REPO_HISTORY = [
    ("2019-02-07", 6.25), ("2019-04-04", 6.00), ("2019-06-06", 5.75), ("2019-08-07", 5.40), ("2019-10-04", 5.15),
    ("2020-03-27", 4.40), ("2020-05-22", 4.00), ("2022-05-04", 4.40), ("2022-06-08", 4.90), ("2022-08-05", 5.40),
    ("2022-09-30", 5.90), ("2022-12-07", 6.25), ("2023-02-08", 6.50), ("2025-02-07", 6.25), ("2025-04-09", 6.00),
    ("2025-06-06", 5.50), ("2025-12-05", 5.25),
]
SOURCE = "Reserve Bank of India, Current Rates on rbi.org.in, and the Monetary Policy Committee's resolutions"

_lock = threading.Lock()
_mem: dict = {"at": 0.0, "rates": None, "tried": 0.0}


def forget():
    with _lock:
        _mem.update(at=0.0, rates=None, tried=0.0)


def fetch_text(url: str = URL) -> str:
    """The home page. Tests replace this."""
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": UA, "Accept": "text/html"}) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.text


def _text(page: str) -> str:
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)
    page = re.sub(r"<!--.*?-->", " ", page, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def _when(s: str) -> str | None:
    try:
        return datetime.strptime(s.strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def parse(page: str) -> dict:
    """The rates in the home page's Current Rates panel; {} when they aren't there."""
    t = _text(page)
    out: dict = {}

    def pct(label: str) -> float | None:
        m = re.search(re.escape(label) + r"\s*:\s*(\d{1,2}\.\d{1,4})\s*%", t, re.I)
        return float(m.group(1)) if m else None
    for key, label in (("repo", "Policy Repo Rate"), ("sdf", "Standing Deposit Facility Rate"), ("msf", "Marginal Standing Facility Rate"),
                       ("bank_rate", "Bank Rate"), ("crr", "CRR"), ("slr", "SLR")):
        v = pct(label)
        if v is not None:
            out[key] = v
    tbills = {}
    for m in re.finditer(r"\b(91|182|364) day T-bills\s*:\s*(\d{1,2}\.\d{1,4})\s*%", t, re.I):
        tbills[m.group(1)] = float(m.group(2))
    if tbills:
        out["tbills"] = tbills
    gsecs = []
    for m in re.finditer(r"(\d{1,2}\.\d{2})% GS (20\d\d)\s*:\s*(\d{1,2}\.\d{1,4})\s*%", t):
        gsecs.append({"name": f"{m.group(1)}% GS {m.group(2)}", "year": int(m.group(2)), "yield": float(m.group(3))})
    if gsecs:
        out["gsecs"] = gsecs
    m = re.search(r"Government Securities Market.*?#\s*as on\s+([A-Z][a-z]+ \d{1,2}, \d{4})", t)
    if m:
        out["gsec_date"] = _when(m.group(1))
    return out if "repo" in out else {}


def _save_seen(repo: float, day: str):
    last = repo_history()[-1]
    if abs(last[1] - repo) < 1e-9:
        return
    seen = db.json_value(db.get_setting(SEEN_KEY), [])
    seen = [s for s in seen if isinstance(s, list) and len(s) == 2]
    seen.append([day, repo])
    db.set_setting(SEEN_KEY, json.dumps(seen[-20:]))


def current() -> dict:
    """{"rates": {...}, "read_at": iso or None}: re-read after a few hours, else the copy kept; {} rates when nothing
    could ever be read."""
    now = time.time()
    with _lock:
        if _mem["rates"] is not None and now - _mem["at"] < MAX_AGE:
            return {"rates": _mem["rates"], "read_at": _iso(_mem["at"])}
        if _mem["rates"] is None:
            got = db.json_value(db.get_setting(KEY), {})
            if isinstance(got, dict) and isinstance(got.get("rates"), dict) and got["rates"]:
                _mem.update(rates=got["rates"], at=float(got.get("at") or 0))
                if now - _mem["at"] < MAX_AGE:
                    return {"rates": _mem["rates"], "read_at": _iso(_mem["at"])}
        if now - _mem["tried"] < RETRY:
            return {"rates": _mem["rates"] or {}, "read_at": _iso(_mem["at"]) if _mem["rates"] else None}
        _mem["tried"] = now
    try:
        rates = parse(fetch_text())
        if not rates:
            raise ValueError("no rates on the page")
    except Exception as e:
        print("RBI rates unavailable:", type(e).__name__)
        with _lock:
            return {"rates": _mem["rates"] or {}, "read_at": _iso(_mem["at"]) if _mem["rates"] else None}
    with _lock:
        _mem.update(rates=rates, at=now)
    try:
        db.set_setting(KEY, json.dumps({"at": now, "rates": rates}, separators=(",", ":")))
        _save_seen(rates["repo"], datetime.now(timezone.utc).date().isoformat())
    except Exception as e:
        print("RBI rates not saved:", type(e).__name__)
    return {"rates": rates, "read_at": _iso(now)}


def _iso(t: float) -> str | None:
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="minutes") if t else None


def repo_history() -> list[tuple[str, float]]:
    """Every repo rate change: the table above, then any later change seen on the home page."""
    out = list(REPO_HISTORY)
    try:
        seen = db.json_value(db.get_setting(SEEN_KEY), [])
    except Exception:
        seen = []
    for d, r in sorted(s for s in seen if isinstance(s, list) and len(s) == 2):
        if d > out[-1][0] and abs(out[-1][1] - float(r)) > 1e-9:
            out.append((d, float(r)))
    return out


def repo_on(day: str, history: list[tuple[str, float]] | None = None) -> float | None:
    """The repo rate in force on `day` (None before the history starts)."""
    rate = None
    for d, r in history or repo_history():
        if d <= day:
            rate = r
        else:
            break
    return rate

