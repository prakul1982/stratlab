"""Your SIP and fund behaviour (Money: mutual funds): from the transactions already read from the user's statement, per
scheme the user's own money-weighted return (XIRR) beside the scheme's own NAV return over the same dates, and the
gap between them in points and rupees; the SIP record (months paid, missed and stopped, the longest unbroken run);
redemptions made after the NAV had fallen 10% or more from its high since the user's first purchase, with what those
units are worth today; and how long redeemed units were held, and how much of today's value has been held over 3 years.

What happened, worked out from the user's own transactions and public NAVs: never a suggestion about what to do. The
"worth today" figures are hindsight arithmetic and say so.

NAV history comes from the industry body's public NAV history service, one scheme at a time, read only for schemes
with redemptions (to find the high before each one) and kept per scheme code (mfnav:hist:<code>) for everyone, since
past NAVs don't change. A read can take many seconds, so it runs in the background; until it lands the page uses the
NAVs on the user's own transactions, and says so."""
import json
import math
import threading
import time
from datetime import date, timedelta

import httpx
from fastapi import APIRouter, Depends

from . import db, money_mf as mf
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, allows
from .responses import ok

HIST_URL = "https://www.amfiindia.com/api/nav-history"
HIST_KEY = "mfnav:hist:"           # mfnav:hist:<scheme code> = {"at", "from", "to", "p": [[YYYY-MM-DD, nav], ...]}
CHUNK_DAYS = 1800                  # the service answers ranges under five years
TIMEOUT = 60.0
PAUSE = 1.0                        # between requests in one background run
RETRY = 3 * 3600                   # after a failed read of a scheme, wait this long
BACKGROUND = True                  # read in a thread (tests turn it off and read inline)
FALL = 0.10                        # a redemption counts as "after a fall" at 10% or more below the high
SIP_GAP_MONTHS = 2                 # no instalment for this many months before the statement's last date: stopped
LONG_YEARS = 3

DISCLAIMER = ("What happened, from your own transactions and public NAVs. Hindsight arithmetic, not investment advice "
              "and not a suggestion to start, stop or change a SIP or a fund.")
ASSUMPTIONS = [
    "Your return is the XIRR of every purchase, redemption and dividend paid out in the scheme, with today's value as the last "
    "flow while you still hold units.",
    "The fund's return is its NAV from the day of your first purchase to today (or to your last redemption when you hold "
    "nothing), as a yearly rate. It is what one rupee kept in the fund throughout earned, whatever the timing of your money.",
    "The gap in rupees is your value (with what you took out) less what the same purchases and redemptions would come to at "
    "the fund's yearly rate. Positive means your timing added to the fund's return; negative means it took away.",
    "For IDCW (dividend) options the NAV drops on each payout, so the fund's NAV return understates what it paid; your XIRR "
    "counts the payouts.",
    "Under a year, both rates are annualised from a short span and swing widely.",
    "SIP months are the calendar months with at least one instalment marked as a SIP in the statement. Missed months are "
    "months between the first and last instalment with none. A SIP counts as stopped when there has been no instalment for "
    "two months before the statement's latest transaction.",
    "A redemption after a fall: its NAV was 10% or more below the highest NAV since your first purchase in the scheme. "
    "Worth today is those units at today's NAV: hindsight arithmetic, known only afterwards.",
    "Holding periods are worked out first in, first out, the way capital gains are.",
]

_lock = threading.Lock()
_mem: dict[str, dict] = {}         # code -> the stored history, once read from the database
_tried: dict[str, float] = {}      # code -> when a read last failed
_queue: list[tuple[str, str, str]] = []
_running = {"on": False}


def forget():
    """Drop the copies in memory (between tests)."""
    with _lock:
        _mem.clear()
        _tried.clear()
        _queue.clear()
        _running["on"] = False


# ---------- NAV history ----------
def fetch_json(code: str, start: str, end: str) -> dict:
    """One scheme's NAV history for a range under five years, as the service sends it. Tests replace this."""
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
               "Accept": "application/json"}
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers=headers) as c:
        r = c.get(HIST_URL, params={"query_type": "historical_period", "from_date": start, "to_date": end, "sd_id": code})
        if r.status_code == 200 and "No records" in r.text[:200]:
            return {}
        r.raise_for_status()
        return r.json()


def parse_history(got: dict) -> list[list]:
    """[[date, nav], ...] sorted by date from the service's answer; [] for anything else. When the answer holds more
    than one plan, the first group is the scheme asked for."""
    groups = ((got or {}).get("data") or {}).get("nav_groups") if isinstance(got, dict) else None
    if not isinstance(groups, list) or not groups:
        return []
    out = {}
    for rec in (groups[0] or {}).get("historical_records") or []:
        d, n = rec.get("date"), rec.get("nav")
        try:
            n = float(n)
            date.fromisoformat(str(d)[:10])
        except (TypeError, ValueError):
            continue
        if math.isfinite(n) and n > 0:
            out[str(d)[:10]] = n
    return [[d, out[d]] for d in sorted(out)]


def chunks(start: str, end: str) -> list[tuple[str, str]]:
    a, b, out = date.fromisoformat(start), date.fromisoformat(end), []
    while a <= b:
        c = min(b, a + timedelta(days=CHUNK_DAYS - 1))
        out.append((a.isoformat(), c.isoformat()))
        a = c + timedelta(days=1)
    return out


def stored(code: str) -> dict | None:
    with _lock:
        if code in _mem:
            return _mem[code]
    got = db.json_value(db.get_setting(HIST_KEY + code), {})
    if not (isinstance(got, dict) and isinstance(got.get("p"), list) and got.get("from") and got.get("to")):
        return None
    with _lock:
        _mem[code] = got
    return got


def covers(h: dict | None, start: str, end: str) -> bool:
    return bool(h) and h["from"] <= start and h["to"] >= end


def read(code: str, start: str, end: str) -> dict | None:
    """Read and keep one scheme's NAVs from `start` to `end` (joined with what is kept). None when the read failed."""
    h = stored(code)
    lo, hi = (min(start, h["from"]), max(end, h["to"])) if h else (start, end)
    points = {p[0]: p[1] for p in (h or {}).get("p") or []}
    day = lambda s, n: (date.fromisoformat(s) + timedelta(days=n)).isoformat()      # noqa: E731
    if h:                                      # only the parts not kept yet
        parts = (chunks(lo, day(h["from"], -1)) if lo < h["from"] else []) + (chunks(day(h["to"], 1), hi) if hi > h["to"] else [])
    else:
        parts = chunks(lo, hi)
    try:
        for i, (a, b) in enumerate(parts):
            if i and PAUSE:
                time.sleep(PAUSE)
            for d, n in parse_history(fetch_json(code, a, b)):
                points[d] = n
    except Exception as e:                     # keep what was there
        print("NAV history unavailable:", code, type(e).__name__)
        with _lock:
            _tried[code] = time.time()
        return None
    out = {"at": time.time(), "from": lo, "to": hi, "p": [[d, points[d]] for d in sorted(points)]}
    try:
        db.set_setting(HIST_KEY + code, json.dumps(out, separators=(",", ":")))
    except Exception as e:
        print("NAV history not saved:", type(e).__name__)
    with _lock:
        _mem[code] = out
    return out


def _run():
    while True:
        with _lock:
            if not _queue:
                _running["on"] = False
                return
            code, start, end = _queue.pop(0)
        read(code, start, end)
        if PAUSE:
            time.sleep(PAUSE)


def histories(needs: dict[str, tuple[str, str]]) -> tuple[dict[str, list], list[str]]:
    """The NAV history each scheme code needs ({code: (start, end)}): what is kept now, and the codes still being read
    (queued in the background). A code whose read failed lately is left out of both."""
    got, pending, start = {}, [], False
    for code, (a, b) in needs.items():
        h = stored(code)
        if covers(h, a, b):
            got[code] = h["p"]
            continue
        with _lock:
            failed = time.time() - _tried.get(code, 0) < RETRY
            queued = any(q[0] == code for q in _queue)
        if failed:
            continue
        if not BACKGROUND:
            h = read(code, a, b)
            if h:
                got[code] = h["p"]
            continue
        pending.append(code)
        with _lock:
            if not queued:
                _queue.append((code, a, b))
            if not _running["on"]:
                _running["on"] = start = True
    if start:
        threading.Thread(target=_run, daemon=True, name="mf-nav-history").start()
    return got, pending


# ---------- the arithmetic ----------
def _d(s: str) -> date:
    return date.fromisoformat(s)


def annual(start_nav: float, end_nav: float, start: str, end: str) -> float | None:
    """The NAV's growth from `start` to `end` as a yearly rate (None under 30 days or without both NAVs)."""
    days = (_d(end) - _d(start)).days
    if not start_nav or not end_nav or start_nav <= 0 or end_nav <= 0 or days < 30:
        return None
    return round((end_nav / start_nav) ** (365.0 / days) - 1, 6)


def grown(flows: list[tuple[str, float]], rate: float, end: str) -> float:
    """What the flows (money in negative, out positive) come to on `end` at a yearly rate: money put in grows, money
    taken out stops growing. Positive means more went in than came out, after growth."""
    return sum(-a * (1 + rate) ** ((_d(end) - _d(d)).days / 365.0) for d, a in flows)


def months(a: str, b: str) -> int:
    """Calendar months from the month of `a` to the month of `b` (0 for the same month)."""
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def _month_after(m: str, n: int = 1) -> str:
    y, mo = int(m[:4]), int(m[5:7]) - 1 + n
    return f"{y + mo // 12:04d}-{mo % 12 + 1:02d}"


def sip_record(dates: list[str], last_txn: str) -> dict | None:
    """SIP months from the instalment dates: paid, missed in between, the longest unbroken run, and whether it has
    stopped (no instalment for SIP_GAP_MONTHS months before the statement's latest transaction)."""
    if not dates:
        return None
    paid = sorted({d[:7] for d in dates})
    span = months(paid[0], paid[-1]) + 1
    best = run = 1
    best_from = run_from = paid[0]
    best_to = paid[0]
    for a, b in zip(paid, paid[1:]):
        if months(a, b) == 1:
            run += 1
        else:
            run, run_from = 1, b
        if run > best:
            best, best_from, best_to = run, run_from, b
    missed = [m for m in (_month_after(paid[0], i) for i in range(span)) if m not in set(paid)]
    stopped = months(paid[-1], last_txn[:7]) >= SIP_GAP_MONTHS
    return {"first": paid[0], "last": paid[-1], "months_paid": len(paid), "months_missed": len(missed),
            "missed": missed[-12:], "instalments": len(dates), "longest_run": best, "longest_from": best_from,
            "longest_to": best_to, "current_run": 0 if stopped else run, "stopped": stopped,
            "stopped_after": paid[-1] if stopped else None}


def high_before(points: list[list], start: str, day: str) -> tuple[float, str] | None:
    """The highest NAV from `start` up to and including `day`, and its date."""
    best = None
    for d, n in points:
        if d < start:
            continue
        if d > day:
            break
        if best is None or n > best[0]:
            best = (n, d)
    return best


def _r(v, dp=2):
    return None if v is None else round(v, dp)


def scheme_behaviour(s: dict, row: dict, w: dict, data: dict, today: str, last_txn: str, hist: list | None, full: bool) -> dict:
    """One scheme: the two returns and the gap; with `full`, the SIP record, the redemptions after a fall and the
    holding periods."""
    k = s["k"]
    txns = sorted((t for t in data["txns"] if t["k"] == k), key=lambda t: t["d"])
    nav_now = w["info"][k]["nav"]
    ins = [t for t in txns if t["t"] in mf.IN_TYPES and t["t"] not in ("opening", "segregation", "div_reinvest")]
    outs = [t for t in txns if t["t"] in ("redeem", "switch_out")]
    held = (row["units"] or 0) > mf.EPS
    out = {"key": k, "name": s["name"], "folio": s.get("folio") or "", "held": held, "xirr": row["xirr"], "fund": None,
           "gap_pp": None, "gap_rupees": None, "from": None, "to": None, "start_nav": None, "end_nav": None,
           "idcw": "idcw" in s["name"].lower() or "dividend" in s["name"].lower(), "short_span": False, "full": full}
    first = ins[0] if ins else None
    if first:
        end = today if held else (outs[-1]["d"] if outs else None)
        start_nav = first.get("n") or next((p[1] for p in reversed(hist or []) if p[0] <= first["d"]), None)
        end_nav = nav_now if held else (outs[-1].get("n") if outs else None)
        if end and start_nav and end_nav:
            fund = annual(start_nav, end_nav, first["d"], end)
            out.update(fund=fund, start_nav=start_nav, end_nav=end_nav, **{"from": first["d"], "to": end},
                       short_span=(_d(end) - _d(first["d"])).days < 365)
            if fund is not None and row["xirr"] is not None:
                out["gap_pp"] = round((row["xirr"] - fund) * 100, 2)
                if full:
                    flows = list(w["c"]["flows"][k])
                    at_fund = grown(flows, fund, end)
                    out["gap_rupees"] = _r((row["value"] or 0) - at_fund) if held else _r(-at_fund)
    if not full:
        return out
    sips = [t["d"] for t in txns if t["t"] == "sip"]
    out["sip"] = sip_record(sips, last_txn)
    # redemptions after a fall from the high since the first purchase
    falls = []
    for t in outs:
        n = t.get("n") or ((t.get("a") or 0) / abs(t["u"]) if t.get("u") else None)
        if not n or not first:
            continue
        pts = hist if hist else [[x["d"], x["n"]] for x in txns if x.get("n")]
        hi = high_before(sorted(pts), first["d"], t["d"])
        if not hi or hi[0] <= 0:
            continue
        fall = 1 - n / hi[0]
        if fall < FALL - 1e-9:
            continue
        units = abs(t.get("u") or 0)
        got = t.get("a") if t.get("a") is not None else units * n
        worth = units * nav_now if nav_now else None
        falls.append({"date": t["d"], "type": t["t"], "units": _r(units, 4), "nav": n, "high": hi[0], "high_date": hi[1],
                      "fall_pct": round(fall * 100, 1), "received": _r(abs(got)), "worth_today": _r(worth),
                      "difference": _r(worth - abs(got)) if worth is not None else None})
    out["falls"] = falls
    out["high_source"] = "history" if hist else "statement"
    # holding periods of redeemed units (first in, first out, from the gains matching)
    sold = [r for r in w["c"]["realised"] if r["key"] == k]
    units = sum(r["qty"] for r in sold)
    out["redeemed_units"] = _r(units, 4)
    out["avg_days_held"] = round(sum((_d(r["sold"]) - _d(r["bought"])).days * r["qty"] for r in sold) / units) if units > mf.EPS else None
    # how much of today's value was bought more than 3 years ago
    lots = [l for l in w["c"]["lots"][k] if l["u"] > mf.EPS]
    cut = mf.add_months(today, -12 * LONG_YEARS).isoformat()
    total_u = sum(l["u"] for l in lots)
    long_u = sum(l["u"] for l in lots if l["d"] <= cut)
    out["value"] = row["value"]
    out["long_value"] = _r(long_u * nav_now) if nav_now and lots else None
    out["long_share"] = round(long_u / total_u * 100, 1) if total_u > mf.EPS else None
    return out


def behaviour(uid: str, plan: str) -> dict:
    """Every scheme's behaviour facts, and the totals, for the page."""
    data = mf.load(uid)
    full = allows(plan, "mf_behaviour")
    today = mf.today_ist()
    base = {"full": full, "plan": PLANS[FEATURE_PLAN["mf_behaviour"]]["name"], "assumptions": ASSUMPTIONS,
            "disclaimer": DISCLAIMER, "as_of": today, "fall_pct": round(FALL * 100), "long_years": LONG_YEARS}
    if not data["txns"]:
        return {**base, "schemes": [], "total": None, "pending": 0, "last_txn": None}
    w = mf.worked(data)
    h = mf.holdings(data, w, today)
    rows = {r["key"]: r for r in h["schemes"]}
    last_txn = max(t["d"] for t in data["txns"])
    needs = {}
    if full:
        for s in data["schemes"]:
            code = s.get("amfi") or ((w["info"][s["k"]]["rec"] or {}).get("code")) or ""
            ds = sorted(t["d"] for t in data["txns"] if t["k"] == s["k"])
            sales = [t["d"] for t in data["txns"] if t["k"] == s["k"] and t["t"] in ("redeem", "switch_out")]
            if code and sales and ds:
                a, b = needs.get(code, (ds[0], max(sales)))
                needs[code] = (min(a, ds[0]), max(b, max(sales)))
    got, pending = histories(needs) if needs else ({}, [])
    out = []
    for s in data["schemes"]:
        code = s.get("amfi") or ((w["info"][s["k"]]["rec"] or {}).get("code")) or ""
        out.append(scheme_behaviour(s, rows[s["k"]], w, data, today, last_txn, got.get(code), full))
    out.sort(key=lambda r: (not r["held"], -((rows[r["key"]]["value"]) or 0), r["name"]))
    total = {"schemes": len(out), "compared": sum(1 for r in out if r["gap_pp"] is not None)}
    if full:
        gaps = [r["gap_rupees"] for r in out if r["gap_rupees"] is not None]
        sold = [r for r in w["c"]["realised"]]
        units = sum(r["qty"] for r in sold)
        val = sum(r["value"] or 0 for r in out if r["held"] and r.get("long_value") is not None)
        long_val = sum(r["long_value"] or 0 for r in out if r["held"] and r.get("long_value") is not None)
        sips = [r["sip"] for r in out if r.get("sip")]
        all_falls = [f for r in out for f in r.get("falls", [])]
        total.update(
            gap_rupees=_r(sum(gaps)) if gaps else None,
            sips=len(sips), sips_running=sum(1 for x in sips if not x["stopped"]), sips_stopped=sum(1 for x in sips if x["stopped"]),
            months_missed=sum(x["months_missed"] for x in sips),
            falls=len(all_falls), falls_received=_r(sum(f["received"] or 0 for f in all_falls)),
            falls_worth_today=_r(sum(f["worth_today"] or 0 for f in all_falls if f["worth_today"] is not None)),
            avg_days_held=round(sum((_d(r["sold"]) - _d(r["bought"])).days * r["qty"] for r in sold) / units) if units > mf.EPS else None,
            held_under_year_pct=round(sum(r["qty"] for r in sold if (_d(r["sold"]) - _d(r["bought"])).days <= 365) / units * 100, 1) if units > mf.EPS else None,
            long_share=round(long_val / val * 100, 1) if val else None, long_value=_r(long_val) if val else None)
    return {**base, "schemes": out, "total": total, "pending": len(pending), "last_txn": last_txn}


router = APIRouter(prefix="/money/mutual-funds", tags=["money"])


@router.get("/behaviour")
def mf_behaviour(profile=Depends(current_profile)):
    """Your return beside each fund's own NAV return over the same dates (everyone); the gap in rupees, the SIP record,
    redemptions after a fall and holding periods (Basic and up)."""
    return ok(behaviour(profile["id"], profile["_plan"]))
