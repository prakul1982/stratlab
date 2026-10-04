"""Mutual fund NAVs: the latest NAV of every scheme from the industry body's public daily file, and every scheme's NAV
on 31 Jan 2018 (for grandfathering long-term gains on equity-oriented funds). Both are public, free files.

The daily file is read at most every few hours and kept in memory, with the last good copy saved so a restart or an
outage still has prices. The 31 Jan 2018 NAVs never change, so they are saved once. Nothing here is per user."""
import json
import re
import threading
import time
from datetime import datetime, timezone

import httpx

from . import db

DAILY_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
# the NAV history report for one day, every scheme
GF_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt=31-Jan-2018&todt=31-Jan-2018"
DAILY_KEY = "mfnav:daily"          # the last good daily file, compact: {"at", "cats", "amcs", "rows"}
GF_KEY = "mfnav:2018-01-31"        # {"code": {amfi code: nav}, "isin": {isin: nav}}
MAX_AGE = 6 * 3600                 # the daily file is published each evening; re-read it after this long
RETRY = 1800                       # after a failed read, wait this long before trying again
TIMEOUT = 30.0
MAX_BYTES = 20 * 1024 * 1024
MIN_SCHEMES = 50                   # fewer in a file means it came back cut short or as an error page

_lock = threading.Lock()
_daily: dict = {"at": 0.0, "data": None, "tried": 0.0}
_gf: dict = {"data": None, "tried": 0.0}

CATEGORY_RX = re.compile(r"^\s*(Open Ended|Close Ended|Interval Fund)\s+Schemes?\s*\(\s*(.+?)\s*\)\s*$", re.I)


def fetch_text(url: str) -> str:
    """One public file, as text. Tests replace this."""
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (StratLab)"}) as c:
        r = c.get(url)
        r.raise_for_status()
        if len(r.content) > MAX_BYTES:
            raise ValueError("file too large")
        return r.text


def forget():
    """Drop the copies in memory (between tests)."""
    with _lock:
        _daily.update(at=0.0, data=None, tried=0.0)
        _gf.update(data=None, tried=0.0)


def _num(s: str) -> float | None:
    try:
        v = float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return v if v > 0 and v < 1e9 else None


def _isin(s: str) -> str:
    s = (s or "").strip().upper()
    return s if re.fullmatch(r"IN[A-Z0-9]{10}", s) else ""


def _day(s: str) -> str | None:
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except (ValueError, AttributeError):
            continue
    return None


def _columns(header: str) -> dict[str, int] | None:
    """Where each field sits, from the file's header line (the daily file and the history report order them
    differently)."""
    cols = [c.strip().lower() for c in header.split(";")]
    if not any("scheme code" in c for c in cols):
        return None
    out = {}
    for i, c in enumerate(cols):
        if "scheme code" in c:
            out["code"] = i
        elif "scheme name" in c:
            out["name"] = i
        elif "isin" in c and "reinvest" in c:
            out["isin2"] = i
        elif "isin" in c:
            out["isin"] = i
        elif "net asset value" in c:
            out["nav"] = i
        elif c == "date":
            out["date"] = i
    return out if {"code", "nav"} <= out.keys() else None


def parse(text: str) -> dict:
    """The daily NAV file (or the NAV history report) as {"schemes": {code: {code, isin, isin2, name, nav, date,
    category, amc}}, "isin": {isin: code}}. Section lines carry the scheme category ("Open Ended Schemes(Equity Scheme
    - Large Cap Fund)") and the fund house; a scheme without a NAV is left out."""
    cols, category, amc = None, "", ""
    schemes: dict[str, dict] = {}
    by_isin: dict[str, str] = {}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if ";" not in line:
            m = CATEGORY_RX.match(line)
            if m:
                category, amc = m.group(2).strip(), ""
            elif len(line) < 120:
                amc = line
            continue
        if cols is None:
            cols = _columns(line)
            continue
        f = line.split(";")
        get = lambda k: f[cols[k]].strip() if k in cols and cols[k] < len(f) else ""     # noqa: E731
        code = get("code")
        nav = _num(get("nav"))
        if not code.isdigit() or nav is None:
            continue
        row = {"code": code, "isin": _isin(get("isin")), "isin2": _isin(get("isin2")), "name": " ".join(get("name").split())[:200],
               "nav": nav, "date": _day(get("date")), "category": category[:120], "amc": amc[:120]}
        schemes[code] = row
        for i in (row["isin"], row["isin2"]):
            if i:
                by_isin[i] = code
    return {"schemes": schemes, "isin": by_isin}


def _pack(data: dict, at: float) -> str:
    cats, amcs, rows = [], [], []
    ci, ai = {}, {}
    for r in data["schemes"].values():
        c = ci.setdefault(r["category"], len(ci))
        if c == len(cats):
            cats.append(r["category"])
        a = ai.setdefault(r["amc"], len(ai))
        if a == len(amcs):
            amcs.append(r["amc"])
        rows.append([r["code"], r["isin"], r["isin2"], r["name"], r["nav"], r["date"], c, a])
    return json.dumps({"at": at, "cats": cats, "amcs": amcs, "rows": rows}, separators=(",", ":"))


def _unpack(raw) -> tuple[dict, float] | None:
    got = db.json_value(raw, {})
    if not isinstance(got, dict) or not isinstance(got.get("rows"), list):
        return None
    cats, amcs = got.get("cats") or [], got.get("amcs") or []
    schemes, by_isin = {}, {}
    for r in got["rows"]:
        try:
            code, isin, isin2, name, nav, day, c, a = r
            schemes[code] = {"code": code, "isin": isin, "isin2": isin2, "name": name, "nav": float(nav), "date": day,
                             "category": cats[c] if 0 <= c < len(cats) else "", "amc": amcs[a] if 0 <= a < len(amcs) else ""}
        except (TypeError, ValueError, IndexError):
            continue
        for i in (isin, isin2):
            if i:
                by_isin[i] = code
    return ({"schemes": schemes, "isin": by_isin}, float(got.get("at") or 0)) if schemes else None


def daily() -> dict:
    """Every scheme's latest NAV: read from the public file when the copy in memory is a few hours old, else the copy.
    When the file can't be read, the last good copy (saved), or an empty list. Adds "read_at" (unix time)."""
    now = time.time()
    with _lock:
        if _daily["data"] is not None and now - _daily["at"] < MAX_AGE:
            return _daily["data"]
        if _daily["data"] is None:
            try:
                got = _unpack(db.get_setting(DAILY_KEY))
            except Exception:
                got = None
            if got:
                _daily["data"], _daily["at"] = {**got[0], "read_at": got[1]}, got[1]
                if now - got[1] < MAX_AGE:
                    return _daily["data"]
        if now - _daily["tried"] < RETRY:
            return _daily["data"] or {"schemes": {}, "isin": {}, "read_at": None}
        _daily["tried"] = now
    try:
        data = parse(fetch_text(DAILY_URL))
        if len(data["schemes"]) < MIN_SCHEMES:
            raise ValueError("too few schemes")
    except Exception as e:                      # keep the last good copy
        print("daily NAV file unavailable:", type(e).__name__)
        with _lock:
            return _daily["data"] or {"schemes": {}, "isin": {}, "read_at": None}
    with _lock:
        _daily.update(data={**data, "read_at": now}, at=now)
    try:
        db.set_setting(DAILY_KEY, _pack(data, now))
    except Exception as e:
        print("daily NAV file not saved:", type(e).__name__)
    return _daily["data"]


def gf_navs() -> dict:
    """Every scheme's NAV on 31 Jan 2018 as {"code": {code: nav}, "isin": {isin: nav}}: saved once read; {} parts
    when it can't be read (tried again after a while)."""
    with _lock:
        if _gf["data"] is not None:
            return _gf["data"]
    got = db.json_value(db.get_setting(GF_KEY), {})
    if isinstance(got, dict) and isinstance(got.get("code"), dict) and got["code"]:
        with _lock:
            _gf["data"] = got
        return got
    now = time.time()
    with _lock:
        if now - _gf["tried"] < RETRY:
            return {"code": {}, "isin": {}}
        _gf["tried"] = now
    try:
        data = parse(fetch_text(GF_URL))
        if len(data["schemes"]) < MIN_SCHEMES:
            raise ValueError("too few schemes")
    except Exception as e:
        print("31 Jan 2018 NAVs unavailable:", type(e).__name__)
        return {"code": {}, "isin": {}}
    out = {"code": {c: r["nav"] for c, r in data["schemes"].items()}, "isin": {}}
    for c, r in data["schemes"].items():
        for i in (r["isin"], r["isin2"]):
            if i:
                out["isin"][i] = r["nav"]
    try:
        db.set_setting(GF_KEY, json.dumps(out, separators=(",", ":")))
    except Exception as e:
        print("31 Jan 2018 NAVs not saved:", type(e).__name__)
    with _lock:
        _gf["data"] = out
    return out


# ---------- finding a scheme ----------
_STOP = {"fund", "plan", "option", "the", "scheme", "mf", "mutual", "of", "and", "&", "a", "an", "formerly", "erstwhile", "series"}
_SYN = {"dividend": "idcw", "div": "idcw", "payout": "idcw", "reinvestment": "idcw", "reinvest": "idcw", "gr": "growth",
        "dir": "direct", "reg": "regular", "cap": "cap"}


def tokens(name: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    return {_SYN.get(w, w) for w in words if w not in _STOP}


def _flags(t: set[str]) -> tuple:
    return ("direct" in t, "idcw" in t, "bonus" in t)


def find(data: dict, isin: str = "", code: str = "", name: str = "") -> dict | None:
    """A scheme in the daily file: by AMFI code, else ISIN, else by name (same plan and option, most words in common,
    and clearly ahead of the next best). None when nothing fits well enough."""
    schemes = data.get("schemes") or {}
    if code and code in schemes:
        return schemes[code]
    if isin and isin in (data.get("isin") or {}):
        return schemes.get(data["isin"][isin])
    want = tokens(name)
    if len(want) < 2:
        return None
    best, second, hit = 0.0, 0.0, None
    for r in schemes.values():
        have = tokens(r["name"])
        if _flags(have) != _flags(want):
            continue
        score = len(want & have) / len(want | have)
        if score > best:
            best, second, hit = score, best, r
        elif score > second:
            second = score
    return hit if best >= 0.6 and best - second >= 0.05 else None


def as_of(read_at: float | None) -> str | None:
    return datetime.fromtimestamp(read_at, timezone.utc).isoformat(timespec="minutes") if read_at else None
