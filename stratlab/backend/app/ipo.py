"""IPOs (Invest → IPOs): India's and the US's public offerings, from the exchanges' and the regulators' own pages.

Each issue is one stored row, read every morning and evening from the sources (intel/ipo_sources.py) and, while an Indian
issue is open for bidding, every quarter of an hour: its dates, price band, lot, size (fresh issue and offer for sale),
the offer document, the bids received by category, and after its listing the listing price against the issue price.
The offer document (the DRHP or RHP filed with SEBI, the S-1 or prospectus filed with the SEC) is read by ipo_docs.py:
the facts a rule can read from it for everyone, and a quote-checked AI summary on Basic and up, made once per document.

Free for everyone: the lists, an issue's page, its subscription and its listing performance. Basic and up: the
summary of the offer document (`ipo_summary`) and alerts when an issue opens, closes, is allotted or lists (`ipo_alerts`).

Facts and arithmetic only, from official pages: no grey market premium (it is not an official number), no view on
whether to apply, and nothing here forecasts a listing. An allotment or listing date the exchange has not published is
the one SEBI's timetable gives (allotment the working day after the close, listing three working days after it), and is
marked as expected."""
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from . import admin, alerts as alerts_mod, db, docs, ipo_docs as D, job_status, leader, memguard, official_close
from .ai_providers import AIError, complete, extract_json
from .auth import current_profile
from .data.calendar import is_trading_day
from .intel import ipo_sources as S
from .intel.net import SourceError, TTLCache
from .plans import FEATURE_PLAN, PLANS, allows, plan_of
from .responses import err, ok

IST = ZoneInfo("Asia/Kolkata")
NY = ZoneInfo("America/New_York")
ROWS_KEY = "ipo:rows:"                # ipo:rows:<IN|US> = {"as_of", "rows": [row], "checked": {...}}
STATE_KEY = "ipo:state"               # the job's last reads and problems
USER_KEY = "ipo:user:"                # ipo:user:<uid> = {"on", "events", "markets", "sme", "sent"}
KEEP_LISTED_DAYS = 120                # a listed issue stays on the list this long
KEEP_FILED_DAYS = 150                 # a filing with no dates yet stays this long after it was filed
PAST_DAYS = 130                       # how far back NSE's past issues are read
DETAIL_FOR_DAYS = 45                  # issues listed within this many days have their own page read for the final figures
BID_CLOSE = "17:00"                   # India: the last day's bidding time when the issue's page gives none (it is shown only when the page gives it, RC2A-004)
LIVE_FROM = "09:55"                   # the bids are read from here, or from the issue's own bidding hours (five minutes before them) to half an hour after its last bidding time
LIVE_EVERY = 900                      # seconds between two reads of the bids of an open issue
LIVE_FIRST = 300                      # ...and between two while an open issue has no bids stored yet: its first bids show within five minutes (RC2A-006)
LIVE_AFTER = 30                       # minutes after an issue's last bidding time that its bids are still read
RETRY_AFTER = 20 * 60                 # a read that met a busy source is read again after this long (twice a day at most), so a rate-limit note doesn't stand all day (RC2A-006)
RETRIES = 2
FINAL_AT = "19:20"                    # the exchange completes a day's bid figures about 19:00: read the final ones after it
MAX_SENT = 600
SEBI_KEY = "ipo:sebi:"                # ipo:sebi:<draft|red_herring> = {"entries": [...], "next": page, "done": bool, "at"}: SEBI's list as read so far
SEBI_BACK_DAYS = 400                  # how far back SEBI's draft list is read (a draft is linked to its red herring prospectus up to a year later)
SEBI_BACKFILL = 4                     # older pages of it read per run until it reaches that far back
RHP_ROW_DAYS = 45                     # a red herring prospectus no exchange list names yet stays a row this long after it was filed
PROBE_DAYS, PROBE_ROWS = 21, 2        # such a row's issue page is looked for for this many days, for this many rows a run
CHECK_DAYS = 60                       # the completeness check compares the exchanges' lists over this many days
# lines of the check that wait on the issuer, not on us: a prospectus filed with the regulator that no exchange lists yet, a US final
# prospectus not yet looked at. Admin shows these as a Check, an exchange's issue missing from ours as a Problem (owner, 26 Oct)
AWAITS = ("filed a red herring prospectus with SEBI", "not yet checked whether it is a first offering")


def awaits(line: str) -> bool:
    return any(a in line for a in AWAITS)


CATCH_LISTED_DAYS = 60                # an issue BSE's table says listed, that no issue list gave, becomes a row for this many days
EVENTS = {"open": "Opens for bidding", "close": "Closes for bidding", "allotment": "Allotment", "listing": "Listing"}
SMALL = 3                             # offer documents the job reads per pass (each is a download and a long read)
AI_PER_DAY = 120                      # summaries the AI writes a day across everyone (each document is summarised once)
NOTE = {"IN": ("Dates, price band, lot size and the bids received are from the exchanges' public-issue pages; the offer documents are the "
               "draft and red herring prospectuses filed with SEBI. An allotment or listing date marked expected is the one SEBI's timetable "
               "gives (allotment the working day after the close, listing three working days after it) until the exchange publishes it. "
               "Facts, not advice."),
        "US": ("Expected, priced and filed offerings are from the public IPO calendar; the documents are the S-1, F-1 and final prospectus "
               "filed with the SEC. US offerings have no public bidding window: the price is set the evening before trading starts. "
               "Facts, not advice.")}

router = APIRouter(tags=["ipo"])
_cache = TTLCache(max_items=300)
_lock = threading.RLock()
_wire = {"feed": None, "calendar": None, "ai": None, "yahoo": None, "sebi": None, "edgar": None, "http": None}


def busy(problem: str) -> bool:
    """Whether a problem line of a read is a source that was busy or rate limited (worth reading again soon), not one that is down."""
    return bool(re.search(r"busy|rate limit", problem or "", re.I))


def hm_add(hm: str, minutes: int) -> str:
    """"17:00" plus 30 minutes is "17:30" (the day's end caps at 23:59)."""
    t = min(int(hm[:2]) * 60 + int(hm[3:5]) + minutes, 23 * 60 + 59)
    return f"{t // 60:02d}:{t % 60:02d}"


def close_at(row: dict) -> str:
    """The last day's bidding time of an Indian issue: the one its exchange page gives, else five o'clock (the usual one) for working out
    the stage; the pages show the time only when it is the page's own (`close_time`)."""
    return row.get("close_time") or BID_CLOSE


def live_window(row: dict) -> tuple[str, str]:
    """When an open Indian issue's bids are read through a day: from its bidding hours' start (or LIVE_FROM) to its last bidding time plus half an hour."""
    start = hm_add(row["open_time"], -5) if row.get("open_time") else LIVE_FROM
    return start, hm_add(close_at(row), LIVE_AFTER)


def setup(feed_fn, calendar_fn, ai_fn, yahoo_fn, sebi_fn=None, edgar_fn=None):
    """Where the sources come from: main.py's clients, or a test's fakes."""
    _wire.update(feed=feed_fn, calendar=calendar_fn, ai=ai_fn, yahoo=yahoo_fn, sebi=sebi_fn or (lambda: S.Sebi()), edgar=edgar_fn or (lambda: S.Edgar()))


def forget():
    _cache.clear()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- rows ----------
def load(market: str) -> dict:
    got = db.json_value(db.get_setting(ROWS_KEY + market), {})
    rows = [r for r in got.get("rows") or [] if isinstance(r, dict) and r.get("id")]
    if market == "IN":
        rows = dedupe_india(rows)             # the rows stored before the merge joined them (RC2A-001) show as one at once
    return {"as_of": got.get("as_of"), "rows": rows, "checked": got.get("checked") if isinstance(got.get("checked"), dict) else {}}


def save(market: str, rows: list[dict], checked: dict, as_of: str | None = None) -> None:
    with _lock:
        db.set_setting(ROWS_KEY + market, json.dumps({"as_of": as_of or _now().isoformat(timespec="seconds"), "rows": rows, "checked": checked},
                                                     separators=(",", ":"), ensure_ascii=False))
        forget()


def state() -> dict:
    return db.json_value(db.get_setting(STATE_KEY), {})


def save_state(st: dict) -> None:
    db.set_setting(STATE_KEY, json.dumps(st, separators=(",", ":")))


def next_working(d: date, n: int) -> date:
    """`n` India working days after `d` (exchange holidays and weekends skipped)."""
    while n > 0:
        d += timedelta(days=1)
        if is_trading_day("IN", d):
            n -= 1
    return d


def stage_of(row: dict, now: datetime | None = None) -> str:
    """filed (an offer document, no dates yet), upcoming, open, closed (awaiting listing) or listed; "withdrawn" for an issue the
    exchange names withdrawn, postponed or cancelled (row["issue_status"] says which), "social" for a Social Stock Exchange fund
    raise, which is not an IPO: neither sits in the stages, an issue that did not go ahead has no bidding, allotment or listing."""
    now = now or _now()
    if row.get("social"):
        return "social"
    if row.get("issue_status"):
        return "withdrawn"
    if row["market"] == "US":
        if row.get("priced"):
            return "listed" if row["priced"] <= now.astimezone(NY).date().isoformat() else "closed"
        return "upcoming" if row.get("expected") else "filed"
    local = now.astimezone(IST)
    today, hm = local.date().isoformat(), local.strftime("%H:%M")
    if row.get("listing") and row["listing"] <= today and not row.get("listing_expected"):
        return "listed"
    if not row.get("open") or not row.get("close"):
        return "filed"
    if today < row["open"]:
        return "upcoming"
    if today < row["close"] or (today == row["close"] and hm < close_at(row)):
        return "open"
    if row.get("listing") and today >= row["listing"]:
        return "listed"
    return "closed"


def timeline(row: dict, now: datetime | None = None) -> dict:
    """The allotment and listing days: the exchange's own when it has published them, else SEBI's timetable (marked expected)."""
    out = {"allotment": row.get("allotment"), "allotment_expected": False, "listing": row.get("listing"), "listing_expected": False}
    if row["market"] != "IN" or not row.get("close") or row.get("issue_status") or row.get("social"):
        return out
    try:
        close = date.fromisoformat(row["close"])
    except ValueError:
        return out
    today = (now or _now()).astimezone(IST).date()
    # SEBI's timetable gives the day; once that day has passed without the exchange publishing one, no date is given (it may have moved)
    if not out["allotment"] and (when := next_working(close, 1)) >= today:
        out["allotment"], out["allotment_expected"] = when.isoformat(), True
    if not out["listing"] and (when := next_working(close, 3)) >= today:
        out["listing"], out["listing_expected"] = when.isoformat(), True
    return out


def sizes(row: dict) -> dict:
    """The issue's size in rupees crore (or dollars): what the issue states, else the shares times the top of the band."""
    if row["market"] == "US":
        shares, price = row.get("shares"), row.get("price") or row.get("high")
        amount = row.get("amount") or (round(shares * price, 0) if shares and price else None)
        return {"amount": amount, "basis": "stated" if row.get("amount") else "shares at the offer price" if amount else None}
    stated = None
    top = row.get("price") or row.get("high")
    fresh_cr, ofs_cr, fresh_sh, ofs_sh = row.get("fresh_cr"), row.get("ofs_cr"), row.get("fresh"), row.get("ofs")
    # a book-built issue with one part in rupees and the other in shares (fresh ₹X crore, offer for sale of N shares): the rupee part
    # alone is not the size. Both parts are shown, and the total once the band says what the shares are worth, at its top
    if (fresh_cr and not ofs_cr and ofs_sh) or (ofs_cr and not fresh_cr and fresh_sh):
        parts = {"fresh_cr": fresh_cr, "ofs_cr": ofs_cr, "fresh": None if fresh_cr else fresh_sh, "ofs": None if ofs_cr else ofs_sh}
        if top:
            total = (fresh_cr or 0) + (ofs_cr or 0) + ((ofs_sh if fresh_cr else fresh_sh) * top / 1e7)
            return {"amount": round(total, 2), "basis": "at the top of the price band" if not row.get("price") else "at the issue price", "parts": parts}
        return {"amount": None, "basis": None, "parts": parts}
    if fresh_cr or ofs_cr:
        stated = round((fresh_cr or 0) + (ofs_cr or 0), 2)
        if fresh_cr and ofs_cr:
            # both parts in rupees: the total, and the two parts it is made of, so "Issue size" says what is new shares and what is a sale
            # by existing holders (LIVE1A-030: SFC Environmental's ₹668 cr against the exchange's share count times the band)
            return {"amount": stated, "basis": "stated", "parts": {"fresh_cr": fresh_cr, "ofs_cr": ofs_cr, "fresh": None, "ofs": None}}
    elif row.get("total_cr"):
        stated = row["total_cr"]
    if stated:
        return {"amount": stated, "basis": "stated"}
    # LIVE2-022: the whole issue (fresh issue and offer for sale) when both are given in shares: the exchange's own "issue size" is the shares
    # in its bid table, which leave out the anchor portion (BLS Polymers: ₹179 cr against 1,70,00,000 fresh shares at ₹150, ₹255 cr)
    whole = (row.get("fresh") or 0) + (row.get("ofs") or 0)
    shares = whole or row.get("size_shares") or None
    if shares and top:
        out = {"amount": round(shares * top / 1e7, 2), "basis": "shares at the top of the price band" if not row.get("price") else "shares at the issue price"}
        bid = row.get("size_shares")
        if whole and bid and bid < whole:
            out["in_bids"] = round(bid * top / 1e7, 2)            # what the exchange's bid table covers: the rest is the anchor portion
        return out
    return {"amount": None, "basis": None}


def public(row: dict, now: datetime | None = None) -> dict:
    """A row as the pages get it: its stage and the arithmetic worked out (minimum investment, size, timeline)."""
    now = now or _now()
    out = {k: v for k, v in row.items() if k not in ("seen", "docs_checked", "detail_at", "_keys")}
    out["stage"] = stage_of(row, now)
    out.update(timeline(row, now))
    sz = sizes(row)
    out["size"], out["size_basis"] = sz["amount"], sz["basis"]
    if sz.get("in_bids"):
        out["size_in_bids"] = sz["in_bids"]
    anchor = re.search(r"anchor[^0-9]{0,30}([\d,]{5,})\s+equity shares", str(row.get("issue_text") or ""), re.I)
    if anchor:
        out["anchor_shares"] = int(anchor.group(1).replace(",", ""))
    if sz.get("parts"):
        out["size_parts"] = {k: v for k, v in sz["parts"].items() if v}
    if row["market"] == "IN" and row.get("lot") and (row.get("high") or row.get("price")):
        out["min_amount"] = round(row["lot"] * (row.get("price") or row["high"]), 2)
        out["min_basis"] = "lot at the issue price" if row.get("price") else "lot at the top of the price band"
    if out["stage"] == "listed" and row["market"] == "IN":
        out["listing_expected"] = False
    return out


# ---------- SEBI's lists, kept ----------
def sebi_index(sebi, kind: str, today: date, problems: list[str], sleep=time.sleep, pace: float = 0.6, backfill: int = SEBI_BACKFILL) -> list[dict]:
    """SEBI's list of draft ("draft") or red herring ("red_herring") offer documents as read over the runs. It is long (the draft list
    has 90 pages of 25) and the site shows one page at a time, newest first, so one page a run kept only the last weeks (a draft filed
    in June, like Jio Platforms', never showed). Each run reads the newest two pages; the draft list's older pages are read a few
    a run, until it reaches SEBI_BACK_DAYS back, and are kept (IPO-001)."""
    label = "draft offer documents" if kind == "draft" else "red herring documents"
    key = SEBI_KEY + kind
    got = db.json_value(db.get_setting(key), {})
    entries = {e["url"]: e for e in got.get("entries") or [] if isinstance(e, dict) and e.get("url") and e.get("date")}
    nxt, done = max(2, int(got.get("next") or 2)), bool(got.get("done")) or kind != "draft"
    cutoff = (today - timedelta(days=SEBI_BACK_DAYS)).isoformat()
    before = len(entries), nxt, done

    def take(rows: list[dict]):
        for e in rows:
            entries[e["url"]] = {"date": e["date"], "url": e["url"], "title": e["title"][:140], "company": e["company"], "kind": e["kind"]}

    for page in (0, 1):
        rows = _try(problems, label if page == 0 else f"{label} (page 2)", lambda page=page: sebi.listing(kind, page), None)
        if rows is None:
            if page == 0:
                backfill = 0              # SEBI isn't answering: the older pages wait for another run
            continue
        take(rows)
        sleep(pace)
    total = (getattr(sebi, "pages", None) or {}).get(kind)
    n = 0
    while not done and n < backfill:
        rows = _try(problems, f"{label} (page {nxt + 1})", lambda: sebi.listing(kind, nxt), None)
        if rows is None:
            break
        take(rows)
        n += 1
        nxt += 1
        if not rows or min(e["date"] for e in rows) < cutoff or (total and nxt >= total):
            done = True
        sleep(pace)
    kept = sorted((e for e in entries.values() if e["date"] >= cutoff), key=lambda e: (e["date"], e["url"]), reverse=True)
    if (len(kept), nxt, done) != before or kept != got.get("entries"):
        db.set_setting(key, json.dumps({"entries": kept, "next": nxt, "done": done, "at": _now().isoformat(timespec="seconds")}, separators=(",", ":"), ensure_ascii=False))
    return kept


# ---------- merging the sources ----------
def _keep_old(old: dict | None, new: dict) -> dict:
    """A row read again: the new facts over the old, but a fact the source didn't give this time is kept."""
    if not old:
        return new
    out = dict(old)
    for k, v in new.items():
        if v not in (None, [], {}, ""):
            out[k] = v
    return out


def _same_issue(a: dict, b: dict) -> bool:
    """Whether two Indian rows are one issue read from two lists: the same company name (case, "Limited" and punctuation aside), or the same
    dates and one name the beginning of the other; but two offers of one name more than 45 days apart are two issues."""
    ka, kb = a.get("nkey"), b.get("nkey")
    if not ka or not kb:
        return False
    if ka != kb:
        short, long_ = sorted((ka, kb), key=len)
        return bool(a.get("open") and a.get("open") == b.get("open") and a.get("close") == b.get("close") and len(short) >= 6 and long_.startswith(short))
    oa, ob = a.get("open"), b.get("open")
    try:
        return not (oa and ob and abs((date.fromisoformat(oa) - date.fromisoformat(ob)).days) > 45)
    except ValueError:
        return True


def _authority(r: dict) -> tuple:
    """Which of two rows of one issue is the more authoritative: the one read from the issue's own NSE page, then NSE's list, then BSE's."""
    return (1 if r.get("detail_at") else 0, 1 if r.get("symbol") else 0, 1 if "NSE" in (r.get("exchanges") or []) else 0, 1 if r.get("size_shares") else 0)


def dedupe_india(rows: list[dict]) -> list[dict]:
    """One row per issue (RC2A-001: SFC Environmental Technologies, BLS Polymers and M. K. Sons Fine Jewels were each listed twice, once from
    NSE's list and once from the row stored when only BSE's list had named them, with two different sizes). The most authoritative row
    stays (its id, symbol, size and dates win); the others lend what it lacks (exchanges, BSE code, documents) and are dropped. Only rows
    with dates or a listing are joined: a filing with no dates is attached to its issue by merge_india."""
    keep: list[dict] = []
    for r in sorted(rows, key=lambda r: (_authority(r), r["id"]), reverse=True):
        mate = next((k for k in keep if r.get("market") == "IN" and k.get("market") == "IN" and (r.get("open") or r.get("listing"))
                     and (k.get("open") or k.get("listing")) and _same_issue(k, r)), None)
        if mate is None:
            keep.append(r)
            continue
        mate["exchanges"] = sorted(set((mate.get("exchanges") or []) + (r.get("exchanges") or [])))
        for k, v in r.items():
            if k in ("id", "nkey", "seen", "exchanges", "docs", "issue_status", "social") or v in (None, [], {}, ""):
                continue
            if mate.get(k) in (None, [], {}, ""):
                mate[k] = v
        have = {d["url"] for d in mate.get("docs") or []}
        mate["docs"] = (mate.get("docs") or []) + [d for d in r.get("docs") or [] if d["url"] not in have]
        mate["issue_status"] = mate.get("issue_status") or r.get("issue_status")
        mate["social"] = mate.get("social") or r.get("social") or None
        if not mate["docs"]:
            mate.pop("docs")
    return keep


def india_id(symbol: str | None, code: str | None, filed_id: str | None = None) -> str:
    if symbol:
        return "in-" + re.sub(r"[^a-z0-9]+", "-", symbol.lower()).strip("-")
    if code:
        return f"in-bse-{code}"
    return f"in-f-{filed_id}"


def merge_india(old_rows: list[dict], nse: dict, bse: list[dict], bse_perf: list[dict], sebi_draft: list[dict], sebi_rhp: list[dict], today: date) -> list[dict]:
    """The Indian rows after a read: NSE's upcoming, current and past issues and BSE's list joined by company name, SEBI's
    offer documents attached by name, and the filings with no dates (a DRHP) kept as "filed"."""
    by_id = {r["id"]: r for r in old_rows}
    out: dict[str, dict] = {}

    def put(row: dict) -> dict:
        got = _keep_old(by_id.get(row["id"]), row)
        # the exchange's note on the issue is what it says now: an issue postponed and announced again loses it (a fact the source
        # doesn't give is otherwise kept)
        got["issue_status"], got["social"] = row.get("issue_status"), bool(row.get("social")) or None
        out[row["id"]] = got
        return got

    for kind in ("past", "current", "upcoming"):         # later kinds override: an issue on the upcoming list is not yet open
        for r in nse.get(kind) or []:
            row = {"id": india_id(r["symbol"], None), "market": "IN", "segment": r["segment"], "name": r["name"], "symbol": r["symbol"],
                   "series": r.get("series"), "open": r.get("open"), "close": r.get("close"), "low": r.get("low"), "high": r.get("high"),
                   "size_shares": r.get("size_shares"), "exchanges": ["NSE"], "currency": "INR", "nkey": S.name_key(r["name"]),
                   "issue_status": r.get("issue_status"), "social": r.get("social")}
            if kind == "past":
                row.update(listing=r.get("listing"), price=r.get("price"))
                if not r.get("listing"):
                    row["listing"] = None
            put(row)
    nkeys = {r["nkey"]: r["id"] for r in out.values() if r.get("nkey")}
    for b in bse:
        key = S.name_key(b["name"])
        if key in nkeys:
            row = out[nkeys[key]]
            row["exchanges"] = sorted(set(row.get("exchanges", []) + ["BSE"]))
            row["bse_code"] = b["code"]
            row.setdefault("face_value", b.get("face_value"))
            row["issue_status"] = row.get("issue_status") or b.get("issue_status")       # either exchange's note stands
            row["social"] = row.get("social") or b.get("social") or None
            continue
        put({"id": india_id(None, b["code"]), "market": "IN", "segment": b["segment"], "name": b["name"].title() if b["name"].isupper() else b["name"],
             "symbol": None, "bse_code": b["code"], "open": b.get("open"), "close": b.get("close"), "low": b.get("low"), "high": b.get("high"),
             "face_value": b.get("face_value"), "size_shares": b.get("size_shares"), "exchanges": ["BSE"], "currency": "INR", "nkey": key,
             "issue_status": b.get("issue_status"), "social": b.get("social")})
    # BSE's table of how its listed issues have traded: the issue price and listing day for the BSE-only ones, and a cross-check
    perf = {S.name_key(p["name"]): p for p in bse_perf}
    for r in out.values():
        p = perf.get(r.get("nkey"))
        if p:
            r["bse_perf"] = {k: p[k] for k in ("issue_price", "listed", "day_close", "latest", "url") if p.get(k) is not None}
            if not r.get("price") and p.get("issue_price"):
                r["price"] = p["issue_price"]
            if not r.get("listing") and p.get("listed"):
                r["listing"] = p["listed"]
    # an issue BSE says has listed that no issue list gave (it closed and listed between two reads, or NSE's past list was down): a
    # listed row from BSE's table, so no issue is missing from "recently listed" for want of one list (IPO-002)
    cutoff_catch = (today - timedelta(days=CATCH_LISTED_DAYS)).isoformat()
    have = {r.get("nkey") for r in out.values()} | {r.get("nkey") for r in old_rows if r.get("open") or r.get("listing")}
    for key, p in perf.items():
        code = re.search(r"/(\d{5,6})/?$", p.get("url") or "")
        if key in have or not code or not p.get("listed") or p["listed"] < cutoff_catch or p["listed"] > today.isoformat():
            continue
        row = {"id": india_id(None, code.group(1)), "market": "IN", "segment": None, "name": p["name"].title() if p["name"].isupper() else p["name"], "symbol": None, "bse_code": code.group(1), "listing": p["listed"],
               "price": p.get("issue_price"), "exchanges": ["BSE"], "currency": "INR", "nkey": key,
               "bse_perf": {k: p[k] for k in ("issue_price", "listed", "day_close", "latest", "url") if p.get(k) is not None}}
        put(row)
    # an issue row stored earlier that no list names now stays for its window: the exchanges' lists drop an issue when it closes, and NSE's
    # past list takes it up only after allotment, so for those days the stored row is the only record (a read that failed must not empty the list)
    cutoff_listed = (today - timedelta(days=KEEP_LISTED_DAYS)).isoformat()
    cutoff_filed = (today - timedelta(days=KEEP_FILED_DAYS)).isoformat()
    for rid, r in by_id.items():
        if rid in out or not (r.get("open") or r.get("listing")):
            continue
        if r.get("listing") and r["listing"] < cutoff_listed:
            continue
        out[rid] = r
    # an issue read from two lists is one row: the row stored when only BSE's list named it, kept above, is NSE's row once NSE lists it (RC2A-001)
    out = {r["id"]: r for r in dedupe_india(list(out.values()))}
    # SEBI's offer documents by company name; a filing with no dates stays a "filed" row. A draft is linked to the issue row of the same
    # company whenever it is found (the draft list is kept over many days, and an older draft is attached when the issue comes) (IPO-001)
    nkeys = {r["nkey"]: r["id"] for r in out.values() if r.get("nkey") and (r.get("open") or r.get("listing") or not r["id"].startswith("in-f-"))}
    for kind, rows in (("DRHP", sebi_draft), ("RHP", sebi_rhp)):
        for e in rows:
            if e["kind"] not in ("drhp", "rhp", "udrhp", "addendum", "prospectus"):
                continue
            key = S.name_key(e["company"])
            fid = re.search(r"_(\d+)\.html", e["url"])
            doc = {"kind": "RHP" if e["kind"] == "rhp" else "DRHP" if e["kind"] in ("drhp", "udrhp") else e["kind"].title(),
                   "label": e["title"], "url": e["url"], "date": e["date"], "source": "sebi"}
            target = out.get(nkeys.get(key, "")) or out.get(india_id(None, None, fid.group(1) if fid else None))
            if target is None:
                # a draft with no dates stays a row for 150 days; a red herring prospectus that no exchange list names yet (the issue opens within
                # days of it) for 45, so an issue the lists have missed is still on ours, and the job looks for its page
                days = KEEP_FILED_DAYS if e["kind"] in ("drhp", "udrhp") else RHP_ROW_DAYS if e["kind"] in ("rhp", "prospectus") else 0
                if not days or e["date"] < (today - timedelta(days=days)).isoformat():
                    continue
                target = put({"id": india_id(None, None, fid.group(1) if fid else key[:20]), "market": "IN", "segment": None, "name": e["company"],
                              "symbol": None, "exchanges": [], "currency": "INR", "nkey": key, "filed": e["date"]})
                nkeys.setdefault(key, target["id"])
            docs_ = [d for d in target.get("docs") or [] if d["url"] != doc["url"]]
            target["docs"] = docs_ + [doc]
            target.setdefault("sebi_url", e["url"])
    # old filings no longer on SEBI's pages stay for their window; one whose company now has an issue row hands its documents to that row
    issue_keys = {r["nkey"]: r for r in out.values() if r.get("nkey") and (r.get("open") or r.get("listing"))}
    for rid, r in by_id.items():
        if rid in out:
            continue
        if (r.get("filed") or "9999") < cutoff_filed:
            continue
        mate = issue_keys.get(r.get("nkey"))
        if mate is not None and mate["id"] != rid:
            have_urls = {d["url"] for d in mate.get("docs") or []}
            mate["docs"] = (mate.get("docs") or []) + [d for d in r.get("docs") or [] if d["url"] not in have_urls]
            mate.setdefault("filed", r.get("filed"))
            continue
        out[rid] = r
    for r in out.values():
        r.setdefault("seen", today.isoformat())
    return sorted(out.values(), key=lambda r: (r.get("open") or r.get("filed") or "", r["id"]), reverse=True)


def merge_us(old_rows: list[dict], cal: list[dict], today: date) -> list[dict]:
    """The US rows after a read: the calendar's expected, priced, filed and withdrawn offerings by deal; withdrawn ones are dropped."""
    by_id = {r["id"]: r for r in old_rows}
    out: dict[str, dict] = {}
    withdrawn = {S.name_key(r["name"]) for r in cal if r["stage"] == "withdrawn"}
    for c in cal:
        if c["stage"] == "withdrawn" or not c["id"]:
            continue
        rid = "us-" + re.sub(r"[^a-z0-9]+", "-", c["id"].lower()).strip("-")
        row = {"id": rid, "market": "US", "segment": None, "name": c["name"].title() if c["name"].isupper() else c["name"], "symbol": c.get("symbol"),
               "exchange": c.get("exchange"), "currency": "USD", "low": c.get("low"), "high": c.get("high"), "shares": c.get("shares"),
               "amount": c.get("amount"), "expected": c.get("expected"), "priced": c.get("priced"), "filed": c.get("filed"),
               "nkey": S.name_key(c["name"])}
        if c["stage"] == "priced":
            row["price"] = c.get("high") or c.get("low")
            row["expected"] = None
        prev = by_id.get(rid)
        merged = _keep_old(prev, row)
        if c["stage"] != "priced" and prev and prev.get("priced"):
            merged["priced"] = prev["priced"]
        # the calendar lists a deal under every stage it has been through (its "filed" line beside its "priced" one): the priced line is the
        # deal's, whichever comes second (an offering priced in September showed as filed, IPO-003)
        same = out.get(rid)
        if c["stage"] != "priced" and same and same.get("priced"):
            merged.update(priced=same["priced"], price=same.get("price"), expected=None)
        out[rid] = merged
    # one row per company: the furthest along wins (a filing, then an expected date, then priced)
    best: dict[str, dict] = {}
    rank = lambda r: (2 if r.get("priced") else 1 if r.get("expected") else 0)   # noqa: E731
    for r in out.values():
        k = r["nkey"]
        if k not in best or rank(r) > rank(best[k]):
            best[k] = r
    out = {r["id"]: r for r in best.values() if r["nkey"] not in withdrawn or r.get("priced")}
    cutoff = (today - timedelta(days=KEEP_LISTED_DAYS)).isoformat()
    for rid, r in by_id.items():
        if rid in out or r["nkey"] in best or r["nkey"] in withdrawn:
            continue
        if (r.get("priced") or r.get("filed") or "9999") >= cutoff:
            out[rid] = r
    for r in out.values():
        r.setdefault("seen", today.isoformat())
    return sorted(out.values(), key=lambda r: (r.get("priced") or r.get("expected") or r.get("filed") or "", r["id"]), reverse=True)


def apply_detail(row: dict, d: dict) -> dict:
    """An issue's own page read into its row (terms, offer document, bids)."""
    for k in ("isin", "industry", "face_value", "lot", "retail_max", "issue_type", "registrar", "issue_text", "close_time", "open_time", "hours"):
        if d.get(k) not in (None, ""):
            row[k] = d[k]
    for k in ("open", "close", "low", "high", "fresh", "ofs", "fresh_cr", "ofs_cr", "total_cr"):
        if d.get(k) is not None:
            row[k] = d[k]
    if re.search(r"zero[- ]coupon|social stock exchange", f"{d.get('issue_type') or ''} {d.get('issue_text') or ''}", re.I):
        row["social"] = True                      # a Social Stock Exchange fund raise: not an IPO
    if d.get("listing"):
        row["listing"] = d["listing"]
    if d.get("lead_managers"):
        row["lead_managers"] = d["lead_managers"]
    for doc in d.get("docs") or []:
        if not any(x["url"] == doc["url"] for x in row.get("docs") or []):
            row["docs"] = (row.get("docs") or []) + [{**doc, "source": "nse"}]
    if d.get("subscription"):
        row["sub"] = d["subscription"]
        row["sub_read"] = _now().isoformat(timespec="seconds")
    row["detail_at"] = _now().isoformat(timespec="seconds")
    return row


def doc_to_read(row: dict) -> dict | None:
    """The document to read an issue from: India, the red herring prospectus, else the draft; US, the final prospectus, else the
    latest amendment, else the first filing."""
    cands = [d for d in row.get("docs") or [] if d.get("url")]
    if not cands:
        return None
    if row["market"] == "US":
        rank = {"424B4": 5, "424B1": 5, "424B3": 4, "424B5": 4, "S-1/A": 3, "F-1/A": 3, "S-1": 2, "F-1": 2}
        return max(cands, key=lambda d: (rank.get(d.get("form") or d.get("kind"), 0), d.get("date") or ""))
    rank = {"RHP": 3, "Prospectus": 3, "DRHP": 2}
    # the exchange's own copy of a red herring prospectus is read before SEBI's page for it (a fixed address, and quicker)
    return max(cands, key=lambda d: (rank.get(d.get("kind"), 1), d.get("source") == "nse", d.get("date") or ""))


# ---------- reading the sources ----------
def _try(problems: list[str], what: str, fn, default=None):
    try:
        return fn()
    except SourceError as e:
        problems.append(f"{what}: {str(e)[:120]}")
    except Exception as e:                       # a source that changed its shape must not stop the others
        problems.append(f"{what}: {type(e).__name__} {str(e)[:100]}")
    return default


def refresh_india(feed, sebi, today: date, now: datetime | None = None, details: int = 30, pace: float = 0.6, sleep=time.sleep,
                  check: list | None = None) -> tuple[list[dict], list[str]]:
    """Read India's sources and rebuild the rows. Returns (rows, problems); a source that fails leaves its part as it was. `check`, a list,
    is filled with what the exchanges' lists have that the rows don't (see india_gaps)."""
    now = now or _now()
    problems: list[str] = []
    old = load("IN")["rows"]
    nse = {"upcoming": S.nse_upcoming(_try(problems, "upcoming issues", feed.nse.ipo_upcoming, [])),
           "current": S.nse_current(_try(problems, "open issues", feed.nse.ipo_current, [])),
           "past": S.nse_past(_try(problems, "past issues", lambda: feed.nse.ipo_past(now - timedelta(days=PAST_DAYS), now), []))}
    bse = S.bse_issues(_try(problems, "the second exchange's issues", feed.bse.ipo_issues, {}))
    perf = S.bse_performance(_try(problems, "listed issues' trading", lambda: feed.bse.ipo_listed(today.year), {}))
    draft = sebi_index(sebi, "draft", today, problems, sleep, pace)
    red = sebi_index(sebi, "red_herring", today, problems, sleep, pace)
    if len(problems) >= 5 and not any(nse.values()) and not bse:        # nothing read at all: keep what is stored
        return old, problems
    rows = merge_india(old, nse, bse, perf, draft, red, today)
    # an issue only SEBI's red herring prospectus names (the exchanges' lists drop an issue when it closes and take it up again after its
    # allotment): its own page on the exchange, found by the company's name (IPO-002)
    rows = find_issue_pages(rows, feed, now, problems, sleep, pace)
    # each issue's own page: terms, the offer document and the bids, for the issues that are near or on their dates
    todo = [r for r in rows if r.get("symbol") and r.get("series") and _wants_detail(r, now)][:details]
    for r in todo:
        got = _try(problems, f"{r['symbol']}", lambda r=r: S.nse_detail(feed.nse.ipo_detail(r["symbol"], r.get("series") or "EQ")))
        if got:
            apply_detail(r, got)
        sleep(pace)
    if check is not None:
        check += india_gaps(rows, nse, bse, perf, red, today, now)
    return rows, problems


def find_issue_pages(rows: list[dict], feed, now: datetime, problems: list[str], sleep=time.sleep, pace: float = 0.6, limit: int = PROBE_ROWS) -> list[dict]:
    """A row that is only a red herring prospectus SEBI lists (no exchange list names the issue, so there is no symbol or date): the
    issue's page on NSE is looked for under the symbols the company's name suggests ("Jio Platforms Limited" is JPL) and accepted only when
    the page names the same company. Found, the row is the issue's row from then on (dates, price band, lot, bids). A row is tried once a
    day, for PROBE_DAYS after the prospectus was filed, a few rows a run."""
    today = now.astimezone(IST).date()
    tried = 0
    for i, r in enumerate(list(rows)):
        rhp = [d for d in r.get("docs") or [] if d.get("kind") in ("RHP", "Prospectus") and d.get("source") == "sebi"]
        if tried >= limit:
            break
        if r["market"] != "IN" or r.get("symbol") or r.get("open") or r.get("bse_code") or not rhp or not r["id"].startswith("in-f-"):
            continue
        filed = max(d.get("date") or "" for d in rhp)
        if filed < (today - timedelta(days=PROBE_DAYS)).isoformat() or (r.get("probe_at") or "") >= today.isoformat():
            continue
        tried += 1
        r["probe_at"] = today.isoformat()
        for guess in S.symbol_guesses(r["name"]):
            got = _try(problems, f"{guess}", lambda guess=guess: S.nse_detail(feed.nse.ipo_detail(guess, "EQ")))
            sleep(pace)
            if got and got.get("open") and S.name_key(got.get("company")) == r.get("nkey"):
                sym = got.get("symbol") or guess
                row = {**r, "id": india_id(sym, None), "symbol": sym, "series": "EQ", "segment": "mainboard", "exchanges": ["NSE"]}
                row.pop("probe_at", None)
                apply_detail(row, got)
                rows[rows.index(r)] = row
                break
    return rows


def india_gaps(rows: list[dict], nse: dict, bse: list[dict], perf: list[dict], red: list[dict], today: date, now: datetime) -> list[str]:
    """What the exchanges' own lists and SEBI's have, for the last CHECK_DAYS, that our rows do not: an issue on NSE's upcoming, open or past
    list or BSE's issue list (main board and SME) with no row, or a row without its dates; an issue BSE's table says listed that is not marked
    listed; a red herring prospectus filed more than three days ago for which no row has dates. Each is a line for Admin (IPO-002): a gap
    between two lists is seen the day it happens."""
    by_key = {r["nkey"]: r for r in rows if r.get("nkey")}
    since = (today - timedelta(days=CHECK_DAYS)).isoformat()
    out: list[str] = []

    def lacks(name: str, key: str, where: str, dates: bool = True):
        row = by_key.get(key)
        if row is None:
            out.append(f"{name} is on {where}, not in our list.")
        elif dates and not row.get("open") and not (row.get("listing") and stage_of(row, now) == "listed"):
            out.append(f"{name} is on {where}; our row has no dates.")

    for kind in ("upcoming", "current", "past"):
        for r in nse.get(kind) or []:
            if r.get("issue_status") or r.get("social") or (r.get("close") or r.get("open") or "9999") < since:
                continue
            lacks(r["name"], S.name_key(r["name"]), f"NSE's {'past' if kind == 'past' else 'open' if kind == 'current' else 'upcoming'} issues")
    for b in bse:
        if b.get("issue_status") or b.get("social") or (b.get("close") or b.get("open") or "9999") < since:
            continue
        lacks(b["name"], S.name_key(b["name"]), f"BSE's {'SME' if b['segment'] == 'sme' else 'main board'} issues")
    for p in perf:
        if p.get("listed") and since <= p["listed"] <= today.isoformat():
            row = by_key.get(S.name_key(p["name"]))
            if row is None:
                out.append(f"{p['name']} is listed on BSE ({p['listed']}), not in our list.")
            elif stage_of(row, now) != "listed" and not row.get("issue_status") and not row.get("social"):
                out.append(f"{p['name']} is listed on BSE ({p['listed']}); our row is not marked listed.")
    late = (today - timedelta(days=3)).isoformat()
    for e in red:
        if e["kind"] in ("rhp", "prospectus") and since <= e["date"] <= late:
            row = by_key.get(S.name_key(e["company"]))
            if row is None or not row.get("open"):
                out.append(f"{e['company']} filed a red herring prospectus with SEBI on {e['date']}; no exchange list names the issue and our row has no dates.")
    return list(dict.fromkeys(out))


def _wants_detail(r: dict, now: datetime) -> bool:
    """Whether an issue's own page is worth reading now: it opens within ten days, is open or closed, or listed within the
    last weeks and its final figures aren't stored yet."""
    st = stage_of(r, now)
    today = now.astimezone(IST).date()
    if st in ("open", "closed"):
        return True
    if st == "upcoming":
        return bool(r.get("open")) and (date.fromisoformat(r["open"]) - today).days <= 10 and (not r.get("detail_at") or r["detail_at"][:10] < today.isoformat())
    if st == "listed" and r.get("listing"):
        age = (today - date.fromisoformat(r["listing"])).days
        return age <= DETAIL_FOR_DAYS and (not r.get("detail_at") or r["detail_at"][:10] <= r["listing"])
    return False


def refresh_us(calendar, edgar, today: date, now: datetime | None = None, lookups: int = 10, check: list | None = None) -> tuple[list[dict], list[str]]:
    """Read the US calendar (last two months, this and the next) and the SEC's filings for the offerings that have a date, then the
    final prospectuses the SEC took in over the last 30 days against the rows (see add_final_prospectuses). `check`, a list, is filled
    with the IPOs that have a final prospectus and no row."""
    now = now or _now()
    problems: list[str] = []
    old = load("US")["rows"]
    cal: list[dict] = []
    months = [date(today.year + (today.month + k - 1) // 12, (today.month + k - 1) % 12 + 1, 1) for k in (-2, -1, 0, 1)]
    for m in months:
        cal += _try(problems, f"{m:%b %Y} calendar", lambda m=m: calendar.ipos(m), [])
    if not cal and len(problems) >= 3:
        return old, problems
    rows = merge_us(old, cal, today)
    finals = _try(problems, "final prospectuses", lambda: edgar.final_prospectuses(today - timedelta(days=FINALS_DAYS), today), [])
    add_final_prospectuses(rows, finals, edgar, today, problems, check)
    n = 0
    for r in rows:
        if n >= lookups:
            break
        if r.get("docs_checked") and (r.get("docs") and r["docs_checked"] >= (today - timedelta(days=2)).isoformat()
                                      or r["docs_checked"] >= (today - timedelta(days=1)).isoformat()):
            continue
        if not (r.get("expected") or r.get("priced") or r.get("filed", "") >= (today - timedelta(days=45)).isoformat()):
            continue
        n += 1
        got = _try(problems, f"SEC filings for {r['name'][:30]}", lambda r=r: edgar.docs_for(r["name"], today))
        r["docs_checked"] = today.isoformat()
        if got and got.get("docs"):
            r["docs"] = [{"kind": d["form"], "form": d["form"], "label": d["form"], "url": d["url"], "link": d.get("link"), "date": d["date"], "source": "sec"}
                         for d in got["docs"][:6]]
            r["cik"], r["industry"] = got["cik"], got.get("industry") or r.get("industry")
            r["symbol"] = r.get("symbol") or got.get("symbol")
    return rows, problems


FINALS_DAYS = 30                       # the SEC's final prospectuses are compared with the US rows over this many days
FIRST_KEY = "ipo:us:first"             # {cik: 1 (its final prospectus was the company's first offering) or 0}: asked of the SEC once per company
FIRST_LOOKUPS = 30                    # (the first run asks about every company in the month; after it, the day's new ones)


def add_final_prospectuses(rows: list[dict], finals: list[dict], edgar, today: date, problems: list[str], check: list | None = None) -> int:
    """The SEC's final prospectuses (424B4, 424B1) of the last 30 days against the US rows. The calendar lists an offering as priced late or
    never (one filed on 5 Oct was still "filed" when its final prospectus was on file on 23 Oct; others were not on it at all), so a company
    whose final prospectus is its first offering (no annual or quarterly report before it) and whose row is not priced is priced from that
    filing's day, and has a row when it had none (IPO-003). A company that is already reporting is selling more shares, not going public.
    Returns how many rows it changed; `check` gets the ones it could not settle."""
    by_key = {r["nkey"]: r for r in rows if r.get("nkey")}
    first = db.json_value(db.get_setting(FIRST_KEY), {})
    asked, changed = 0, 0
    for f in sorted(finals, key=lambda f: f["date"], reverse=True):
        key = S.name_key(f["name"])
        row = by_key.get(key)
        if (row and row.get("priced")) or not key:
            continue
        verdict = first.get(f["cik"])
        if verdict is None:
            if asked >= FIRST_LOOKUPS:
                if check is not None:
                    check.append(f"{f['name']} filed a final prospectus with the SEC on {f['date']}; not yet checked whether it is a first offering.")
                continue
            asked += 1
            sub = _try(problems, f"SEC filings of {f['name'][:30]}", lambda f=f: edgar.filings(f["cik"]))
            if sub is None:
                continue
            verdict = int(S.first_offering(sub, f["date"]))
            first[f["cik"]] = verdict
        if not verdict:
            continue
        if row:
            row.update(priced=f["date"], expected=None, priced_from="sec", symbol=row.get("symbol") or f.get("symbol"))
        else:
            row = {"id": f"us-sec-{f['cik']}", "market": "US", "segment": None, "name": f["name"], "symbol": f.get("symbol"), "exchange": None, "currency": "USD",
                   "priced": f["date"], "priced_from": "sec", "nkey": key, "seen": today.isoformat()}
            rows.append(row)
            by_key[key] = row
        changed += 1
    if asked:
        db.set_setting(FIRST_KEY, json.dumps(dict(list(first.items())[-400:]), separators=(",", ":")))
    rows.sort(key=lambda r: (r.get("priced") or r.get("expected") or r.get("filed") or "", r["id"]), reverse=True)
    return changed


# ---------- listing performance ----------
def yahoo_symbol(row: dict) -> str | None:
    if row["market"] == "US":
        return (row.get("symbol") or "").replace(".", "-") or None
    return f"{row['symbol']}.NS" if row.get("symbol") else (f"{row['bse_code']}.BO" if row.get("bse_code") else None)


def _official(symbol: str, day: str, now: datetime, fetch: bool) -> float | None:
    """The exchange's official close of an NSE stock on a day: the cash bhavcopy's (stored), and with `fetch` the file is read when it is out
    and a same-day quote after the auction. A day before a split or bonus is left to the candle (official_close.before_ex_date)."""
    sym = str(symbol or "").upper()
    if not sym or not day:
        return None
    try:
        if official_close.before_ex_date(sym, day, now):
            return None
        if fetch:
            return official_close.official(sym, day, True, now)
        return (official_close.stored(day) or {}).get(sym)
    except Exception:
        return None


def _settle(row: dict, bars: list[dict], first: dict | None, now: datetime) -> tuple[list[dict], dict | None]:
    """The daily candles of an Indian issue with the closes the exchange calls official (RC2A-002: the list's "latest close" for ZETWERK was
    the 15:25 five-minute price, ₹140.70, the day's official close being ₹138.25). The latest day's close and the listing day's are the
    exchange's own when it is out and on the candle's basis; a session still going on is not a close at all and is left out."""
    if row["market"] == "US" and bars:
        # a US session still going on is not a close either: the 12:00 ET read put a midday price under "Close 28 Oct" (AMRO $6.07, the
        # close $5.86; LIVE1A-060). The last close is the one the session before it ended on.
        ny = now.astimezone(NY)
        if bars[-1]["t"][:10] == ny.date().isoformat() and (ny.hour, ny.minute) < US_CLOSE_SETTLED:
            bars = bars[:-1]
            if first and first["t"][:10] == ny.date().isoformat():
                first = None
        return bars, first
    if row["market"] != "IN" or not bars:
        return bars, first
    today = now.astimezone(IST).date().isoformat()
    if bars[-1]["t"][:10] == today:
        try:
            ended = now >= official_close.out_at(today, "cash")
        except ValueError:
            ended = True
        if not ended:
            bars = bars[:-1]
            if first and first["t"][:10] == today:
                first = None
    if not bars:
        return bars, first

    def fix(b: dict, fetch: bool) -> dict:
        c = _official(row.get("symbol") or "", b["t"][:10], now, fetch)
        if c is None or not official_close.same_basis(c, b.get("c")):
            return b
        return {**b, "c": c, "h": max(c, b.get("h") or c), "l": min(c, b.get("l") or c), "official": True}

    last = fix(bars[-1], True)
    if first is not None:
        first = last if first["t"] == bars[-1]["t"] else fix(first, False)
    return bars[:-1] + [last], first


def performance(row: dict, yahoo, today: date | None = None, now: datetime | None = None) -> dict | None:
    """A listed issue against its issue price, from the daily prices: the listing price (the first session's opening price), that
    session's close, and the latest close, each against the issue price. None until it has traded. An Indian issue's closes are the
    exchange's official ones (see _settle)."""
    sym, issue = yahoo_symbol(row), row.get("price")
    listed = row.get("listing") if row["market"] == "IN" else row.get("priced")
    if not sym or not listed:
        return None
    try:
        age = ((today or _now().date()) - date.fromisoformat(listed)).days
        bars = yahoo.chart(sym, "1d", max(30, min(age + 15, 700)))["candles"]
    except Exception:
        bars = []
    first = next((b for b in bars if b["t"][:10] >= listed), None)
    bars, first = _settle(row, bars, first, now or _now())
    bse = row.get("bse_perf") or {}
    issue = issue or bse.get("issue_price")
    if not issue:
        return None
    if not first or (date.fromisoformat(first["t"][:10]) - date.fromisoformat(listed)).days > 5:
        # the prices couldn't be read: BSE's own table of its listed issues, when it has this one
        if bse.get("day_close") and bse.get("latest"):
            return {"issue_price": issue, "listing_price": None, "listing_change_pct": None, "day_close": bse["day_close"],
                    "day_change_pct": round((bse["day_close"] / issue - 1) * 100, 2), "latest": bse["latest"], "latest_date": None,
                    "change_pct": round((bse["latest"] / issue - 1) * 100, 2), "listed": listed, "basis": "exchange"}
        return None
    last = bars[-1]
    pct = lambda v: round((v / issue - 1) * 100, 2)      # noqa: E731
    return {"issue_price": issue, "listing_price": first["o"], "listing_change_pct": pct(first["o"]), "day_close": first["c"],
            "day_change_pct": pct(first["c"]), "latest": last["c"], "latest_date": last["t"][:10], "change_pct": pct(last["c"]),
            "listed": first["t"][:10], "basis": "prices"}


US_CLOSE_SETTLED = (16, 15)            # New York time: after the 16:00 close and the closing print, a US daily candle is the day's close (LIVE1A-060)
SLOT_UNTIL = {"us-close": "05:30"}     # IST: a slot that may only run in the small hours (LIVE1A-060)
PERF_DAYS = 75                         # issues listed within this many days have their trading since listing read again at every read
PERF_RETRY_DAYS = 7                    # an older listed issue with no figures yet is tried again after this long


def attach_perf(rows: list[dict], now: datetime) -> int:
    """Store each recently listed issue's trading since its listing on its row (the lists show it without a price call each).
    An issue listed longer ago than PERF_DAYS, which the list still holds (KEEP_LISTED_DAYS is 120), is not read again at every read:
    its listing-day figures never change, so it is read once when it has none (the blog's IPO post counted 62 of 115 issues, the rest
    being those past the window), and again only after PERF_RETRY_DAYS if that read found nothing (RC4-003)."""
    n, today = 0, now.astimezone(IST).date() if rows and rows[0]["market"] == "IN" else now.astimezone(NY).date()
    for r in rows:
        listed = r.get("listing") if r["market"] == "IN" else r.get("priced")
        if stage_of(r, now) != "listed" or not listed:
            continue
        if (today - date.fromisoformat(listed)).days > PERF_DAYS:
            if (r.get("perf") or {}).get("day_change_pct") is not None or str(r.get("perf_tried") or "") > (today - timedelta(days=PERF_RETRY_DAYS)).isoformat():
                continue
            r["perf_tried"] = today.isoformat()
        got = performance(r, _wire["yahoo"](), today, now) if _wire["yahoo"] else None
        if got:
            r["perf"] = {**got, "at": now.isoformat(timespec="seconds")}
            n += 1
    return n


def official_perf(row: dict, perf: dict | None, now: datetime | None = None) -> dict | None:
    """A stored performance with the exchange's official closes put in where its bhavcopy is stored now (the figures kept at 20:10 may have
    been worked out before the file was out): the latest close and the listing day's, each against the issue price. Nothing is read."""
    if not perf or row.get("market") != "IN" or not row.get("symbol") or perf.get("basis") != "prices" or not perf.get("issue_price"):
        return perf
    now, out = now or _now(), dict(perf)
    for day_key, px_key, pct_key in (("latest_date", "latest", "change_pct"), ("listed", "day_close", "day_change_pct")):
        c = _official(row["symbol"], out.get(day_key) or "", now, False)
        if c is not None and out.get(px_key) and official_close.same_basis(c, out[px_key]):
            out[px_key], out[pct_key] = c, round((c / out["issue_price"] - 1) * 100, 2)
    return out


def perf_for(row: dict, ttl: float = 600) -> dict | None:
    key = ("perf", row["id"])
    hit = _cache.get(key)
    if hit is not None:
        return hit or None
    got = performance(row, _wire["yahoo"]()) if _wire["yahoo"] else None
    _cache.set(key, got or {}, ttl)
    return got


# ---------- the offer document: facts and summary ----------
def doc_key(d: dict) -> str:
    return D.doc_id(d["url"])


def read_doc(row: dict, d: dict, sebi=None) -> dict:
    """Download and read one offer document: the facts the rules find, and the excerpt the summary is written from. Stored for
    everyone under the document's id; raises SourceError when it can't be fetched."""
    url = d["url"]
    with memguard.heavy("ipo-document", force_release=True):       # the document (up to 40 MB) and its pages: one heavy job at a time, then dropped (MEM-001)
        return _read_doc(row, d, url, sebi)


def _read_doc(row: dict, d: dict, url: str, sebi=None) -> dict:
    if row["market"] == "US":
        text = D.html_text(D.download(url, head=D.HTML_HEAD))
        facts = {"kind": d.get("form") or d.get("kind"), "url": url, "us": D.us_facts(text)}
        excerpt = D.us_excerpt(text)
    else:
        pdf_url = url
        if d.get("source") == "sebi" and url.endswith(".html"):
            pdf_url = (sebi or S.Sebi()).pdf(url)
            if not pdf_url:
                raise SourceError("SEBI", "SEBI's filing page has no offer document attached.")
        pages = D.pdf_pages(D.pdf_from(D.download(pdf_url)))
        facts = {"kind": d.get("kind"), "url": url, "pdf": pdf_url, "pages_read": len(pages), "promoters": D.promoters(pages),
                 "selling": D.selling_holders(pages), "objects": D.objects(pages), "financials": D.financials(pages),
                 # the tables read by fixed rules (O7): the proceeds' use, the risks the document puts first, its key indicators beside its
                 # listed peers', the holders before the offer, the peers' ratios and the earnings per share
                 "utilisation": D.utilisation(pages), "risks": D.risk_headings(pages), "kpis": D.kpis(pages), "holding": D.shareholding(pages),
                 "peers": D.peer_table(pages), "eps": D.eps_rows(pages)}
        excerpt = D.india_excerpt(pages)
    out = {**{k: v for k, v in facts.items() if v not in (None, [], {})}, "reader": D.READER, "read_at": _now().isoformat(timespec="seconds"), "excerpt": excerpt[:34000]}
    db.set_setting(D.FACTS_KEY + doc_key(d), json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    return out


def facts_of(d: dict | None) -> dict | None:
    if not d:
        return None
    got = db.json_value(db.get_setting(D.FACTS_KEY + doc_key(d)), {})
    return got if got.get("reader") == D.READER else None


def summary_of(d: dict | None) -> dict | None:
    if not d:
        return None
    got = db.json_value(db.get_setting(D.SUM_KEY + doc_key(d)), {})
    return got if got.get("reader") == D.SUMMARY_READER else None


def _ai_budget() -> bool:
    """One more summary fits today's cap (shared by everyone); counts it when it does."""
    day = _now().astimezone(IST).date().isoformat()
    n = int(db.get_setting("ipo:ai:" + day) or 0)
    if n >= AI_PER_DAY:
        return False
    db.set_setting("ipo:ai:" + day, str(n + 1))
    return True


def make_summary(row: dict, d: dict, facts: dict, ai) -> dict:
    """The summary of one document, written once and kept (a problem is kept too, so it isn't asked again until the reader changes)."""
    out = {"reader": D.SUMMARY_READER, "at": _now().isoformat(timespec="seconds"), "doc": d["url"], "items": None, "problem": None}
    items = D.summarise(facts.get("excerpt") or "", ai)       # an AIError (the models busy) is raised: nothing is kept, it is tried again
    if not items.get("business") and not any(items.get(k) for k in D.MAX_ITEMS):
        out["problem"] = "No statement could be checked against the document."
    else:
        out["items"] = items
    db.set_setting(D.SUM_KEY + doc_key(d), json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    return out


# ---------- alerts ----------
def prefs(uid: str) -> dict:
    row = db.json_value(db.get_setting(USER_KEY + uid), {})
    events = [e for e in row.get("events") or [] if e in EVENTS] if isinstance(row.get("events"), list) else list(EVENTS)
    markets = [m for m in row.get("markets") or [] if m in ("IN", "US")] if isinstance(row.get("markets"), list) else ["IN"]
    return {"on": bool(row.get("on")), "events": events, "markets": markets, "sme": bool(row.get("sme")),
            "sent": [x for x in row.get("sent") or [] if isinstance(x, str)][-MAX_SENT:]}


def save_prefs(uid: str, p: dict) -> dict:
    db.set_setting(USER_KEY + uid, json.dumps({k: p[k] for k in ("on", "events", "markets", "sme", "sent")}, separators=(",", ":")))
    return p


def money(row: dict, v) -> str:
    if v is None:
        return "–"
    return f"${v:,.2f}" if row["market"] == "US" else f"₹{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) and v != int(v) else f"₹{int(v):,}"


def clock_text(hm: str) -> str:
    """"17:00" is "5 PM", "19:30" is "7:30 PM"."""
    h, m = int(hm[:2]), int(hm[3:5])
    return f"{h % 12 or 12}{f':{m:02d}' if m else ''} {'PM' if h >= 12 else 'AM'}"


def events_on(rows: list[dict], market: str, day: date, now: datetime) -> list[dict]:
    """The dated events of `market`'s issues falling on `day`: [{id, kind, row, text}], the dates as the rows give them (an
    expected allotment or listing counts, and says so)."""
    out = []
    for r in rows:
        if r.get("market") != market or r.get("issue_status") or r.get("social"):      # an issue that did not go ahead has no events
            continue
        pub = public(r, now)
        name = r["name"]
        band = ""
        if r["market"] == "IN" and (r.get("low") or r.get("high")):
            band = (f"price band {money(r, r.get('low'))} to {money(r, r.get('high'))}" if r.get("low") != r.get("high") else f"price {money(r, r.get('high'))}")
            band += f", lot {r['lot']}" if r.get("lot") else ""
        d = day.isoformat()
        if r["market"] == "IN":
            if r.get("open") == d:
                out.append({"id": f"{r['id']}:open:{d}", "kind": "open", "row": r, "text": f"{name} opens for bidding today" + (f" ({band})." if band else ".")})
            if r.get("close") == d:
                out.append({"id": f"{r['id']}:close:{d}", "kind": "close", "row": r, "text": f"{name} closes for bidding today" + (f" at {clock_text(r['close_time'])} IST." if r.get("close_time") else ".")})
            if pub.get("allotment") == d and r.get("open"):
                out.append({"id": f"{r['id']}:allotment:{d}", "kind": "allotment", "row": r,
                            "text": f"{name}: the basis of allotment is expected today" + (" (SEBI's timetable)." if pub.get("allotment_expected") else ".")})
            if pub.get("listing") == d and r.get("open"):
                out.append({"id": f"{r['id']}:listing:{d}", "kind": "listing", "row": r,
                            "text": f"{name} is " + ("expected to list today (SEBI's timetable)." if pub.get("listing_expected") else "listing today.")})
        else:
            if r.get("expected") == d:
                out.append({"id": f"{r['id']}:listing:{d}", "kind": "listing", "row": r,
                            "text": f"{name} is expected to price today" + (f" at {money(r, r.get('low'))} to {money(r, r.get('high'))}." if r.get("low") else ".")})
            if r.get("priced") == d:
                out.append({"id": f"{r['id']}:listing:{d}", "kind": "listing", "row": r,
                            "text": f"{name} starts trading today after pricing at {money(r, r.get('price'))}." if r.get("price") else f"{name} starts trading today."})
    return out


def alert_text(items: list[dict], day: date) -> str:
    lines = [f"IPOs, {day:%a} {day.day} {day:%b}:"] + [f"- {i['text']}" for i in items[:12]]
    if len(items) > 12:
        lines.append(f"- and {len(items) - 12} more on the IPOs page")
    lines.append("Dates as the exchanges and regulators publish them. Facts, not advice.")
    return "\n".join(lines)


def _send(profile: dict, subject: str, text: str) -> list[str]:
    sent = []
    for channel, send in alerts_mod.jobs_for(profile, subject, text, "/invest/ipos", why="You get this because you turned on IPO alerts on StratLab.", label="IPO alert"):
        try:
            if alerts_mod.reached(channel, send()):
                sent.append(channel)
        except Exception as e:
            print("ipo alert failed:", channel, str(e)[:120])
    return sent


def send_alerts(market: str, day: date, now: datetime | None = None, send=None, profile=None) -> int:
    """One message to each user with IPO alerts on (and a plan that has them): the events falling on `day` for the markets and
    kinds they picked, that weren't sent before. Returns how many messages went."""
    now, send, profile = now or _now(), send or _send, profile or db.cached_profile
    rows = load(market)["rows"]
    todays = events_on(rows, market, day, now)
    if not todays:
        return 0
    sent = 0
    for key, raw in db.all_settings_with_prefix(USER_KEY):
        uid = key[len(USER_KEY):]
        row = db.json_value(raw, {})
        if not uid or not isinstance(row, dict) or not row.get("on"):
            continue
        pr = prefs(uid)
        if market not in pr["markets"]:
            continue
        try:
            p = profile(uid)
            if not allows(plan_of(p), "ipo_alerts"):
                continue
        except Exception:
            continue
        done = set(pr["sent"])
        hits = [i for i in todays if i["kind"] in pr["events"] and i["id"] not in done and (pr["sme"] or i["row"].get("segment") != "sme")]
        if not hits:
            continue
        subject = f"StratLab IPOs: {hits[0]['row']['name'][:60]}" + (f" and {len(hits) - 1} more" if len(hits) > 1 else "")
        before = pr["sent"]
        pr["sent"] = (before + [i["id"] for i in hits])[-MAX_SENT:]
        save_prefs(uid, pr)               # before the send: a kill in between drops it, never repeats it
        try:
            reached = send(p, subject[:150], alert_text(hits, day))
        except Exception as e:
            print("ipo alert failed:", str(e)[:120])
            reached = None
        if not reached:                   # an error, or nowhere to reach: the events are unsent again
            pr["sent"] = before
            save_prefs(uid, pr)
            continue
        sent += 1
    return sent


# ---------- the job ----------
def run_marker(name: str) -> str | None:
    return db.get_setting("ipo:ran:" + name)


class Job:
    """Reads the sources on a schedule: India's before the open and in the evening, the US calendar morning and evening (IST);
    the US closes again at 03:30 IST (after the New York close, so the listed issues' latest close is the day's); every quarter hour through the bidding hours it reads the bids of the issues open; the exchange's final figures after
    19:20; then the offer documents and their summaries, a few each pass. IPO alerts go out at 08:00 IST (India's dates)
    and 19:00 IST (the US dates, the New York morning). One leader container runs it; a run marker per slot and day means a
    restart never sends twice."""
    SLOTS = (("in-am", "07:40"), ("in-alert", "08:00"), ("us-am", "08:30"), ("us-alert", "19:00"), ("in-final", FINAL_AT), ("in-pm", "20:10"), ("us-pm", "21:30"), ("us-close", "03:30"))

    def __init__(self, sleep=time.sleep):
        self.sleep = sleep
        self.status = job_status.Status("ipo", {"last_run": None, "read": None, "docs": 0, "summaries": 0, "sent": 0, "problems": [], "last_error": None})
        self._live_at = 0.0
        self._docs_at = 0.0
        self.busy = threading.Lock()

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="ipos").start()

    def _loop(self):
        while True:
            try:
                if leader.leading():
                    self.tick(_now())
            except Exception as e:
                self.status["last_error"] = str(e)[:200]
                print("ipos:", e)
            time.sleep(60)

    def due(self, name: str, at: str, now: datetime) -> str | None:
        local = now.astimezone(IST)
        day = local.date().isoformat()
        if name in SLOT_UNTIL and local.strftime("%H:%M") > SLOT_UNTIL[name]:
            return None                       # the after-the-close read is for the small hours: later, the 08:30 and 21:30 reads have the same day's data
        if local.strftime("%H:%M") >= at and run_marker(name) != day and (local.strftime("%H:%M") < "23:30"):
            return day
        return None

    def tick(self, now: datetime) -> list[str]:
        """One pass: the slots due, the live bids, and a few documents. Returns what ran."""
        ran = []
        if not self.busy.acquire(blocking=False):
            return ran
        try:
            local = now.astimezone(IST)
            for name, at in self.SLOTS:
                day = self.due(name, at, now)
                if not day:
                    continue
                db.set_setting("ipo:ran:" + name, day)          # marked first: a crash mid-read is the next slot's to repair, never a second send
                if name.endswith("-alert"):
                    market = "IN" if name.startswith("in") else "US"
                    n = send_alerts(market, local.date() if market == "IN" else now.astimezone(NY).date(), now)
                    self.status.update(sent=self.status["sent"] + n)
                elif name in ("in-final",):
                    self.read_open(now, final=True)
                else:
                    self.read(name[:2].upper(), now, perf=name.endswith(("-pm", "-close")))
                ran.append(name)
            if self.live_due(now):
                self.read_open(now)
                ran.append("live")
            elif not ran and (m := self.retry_due(now)):
                self.read(m, now)
                ran.append(f"retry-{m.lower()}")
            if not ran and time.time() - self._docs_at > 120 and not self.first_read(now):
                self._docs_at = time.time()
                if self.read_docs(now):
                    ran.append("docs")
        finally:
            self.busy.release()
        return ran

    def first_read(self, now: datetime) -> bool:
        """With nothing stored yet (a new server), read both markets at once."""
        did = False
        for m in ("IN", "US"):
            if not load(m)["rows"] and not (state().get(m) or {}).get("tried", "") > (now - timedelta(minutes=30)).isoformat():
                st = state()
                st[m] = {**(st.get(m) or {}), "tried": now.isoformat(timespec="seconds")}
                save_state(st)
                self.read(m, now, perf=True)
                did = True
        return did

    def live_due(self, now: datetime) -> bool:
        """An open issue's bids are read every quarter hour through its bidding hours, and every five minutes while it has none stored yet,
        so the first bids show at once (RC2A-006: EAAA's came up on NSE at 10:03 and on ours at 10:06, on someone's request)."""
        local = now.astimezone(IST)
        hm = local.strftime("%H:%M")
        if not is_trading_day("IN", local.date()):
            return False
        live = [r for r in load("IN")["rows"] if stage_of(r, now) == "open" and (lambda w: w[0] <= hm <= w[1])(live_window(r))]
        if not live:
            return False
        every = LIVE_FIRST if any(not r.get("sub") for r in live) else LIVE_EVERY
        return time.time() - self._live_at >= every

    def retry_due(self, now: datetime) -> str | None:
        """The market whose last read met a busy source (a rate limit) and is read again, twice a day at most, after RETRY_AFTER: the note
        that "some sources couldn't be read" would otherwise stand until the evening's read (RC2A-006). Inside the job's own loop."""
        local = now.astimezone(IST)
        if not ("08:15" <= local.strftime("%H:%M") <= "22:00"):
            return None
        day = local.date().isoformat()
        for m in ("IN", "US"):
            st = (state().get(m) or {})
            if not any(busy(x) for x in st.get("problems") or []) or not st.get("read"):
                continue
            if datetime.fromisoformat(st["read"]) > now - timedelta(seconds=RETRY_AFTER):
                continue
            tried = db.json_value(db.get_setting(f"ipo:retry:{m}"), {})
            if tried.get("day") == day and tried.get("n", 0) >= RETRIES:
                continue
            db.set_setting(f"ipo:retry:{m}", json.dumps({"day": day, "n": tried.get("n", 0) + 1 if tried.get("day") == day else 1}))
            return m
        return None

    def read(self, market: str, now: datetime, perf: bool = False) -> dict:
        """Read one market's sources and keep the rows; with `perf`, also how each recently listed issue has traded since."""
        today = now.astimezone(IST).date() if market == "IN" else now.astimezone(NY).date()
        missing: list[str] = []
        if market == "IN":
            feed = _wire["feed"]()
            rows, problems = refresh_india(feed, _wire["sebi"](), today, now, sleep=self.sleep, check=missing)
        else:
            rows, problems = refresh_us(_wire["calendar"](), _wire["edgar"](), today, now, check=missing)
        if perf:
            attach_perf(rows, now)
        load_ = load(market)
        # (the check compares with what the lists said this read; when they weren't read, nothing is compared)
        checked = {**load_["checked"], "read": now.isoformat(timespec="seconds"), "problems": problems[:6], "missing": missing[:12]}
        if rows is not load_["rows"] or problems or missing:
            save(market, rows, checked, as_of=now.isoformat(timespec="seconds") if len(problems) < 4 else load_["as_of"])
        st = state()
        st[market] = {**(st.get(market) or {}), "read": now.isoformat(timespec="seconds"), "problems": problems[:6], "missing": missing[:12], "rows": len(rows)}
        save_state(st)
        # Admin shows a gap the same day: what a list has that ours doesn't, from both markets' last reads, as the job's problems (IPO-002);
        # a line that waits on the issuer (AWAITS) is a Check, not a Problem
        lines = [(f"{'India' if m == 'IN' else 'US'}", x) for m in ("IN", "US") for x in (st.get(m) or {}).get("missing", [])[:6]]
        gaps = [f"Missing ({where}): {x}" for where, x in lines if not awaits(x)]
        waits = [f"To check ({where}): {x}" for where, x in lines if awaits(x)]
        self.status.update(last_run=now.isoformat(timespec="seconds"), read=market, problems=(gaps + waits + problems[:5])[:10],
                           last_error=(f"{len(gaps)} issue{'s' if len(gaps) != 1 else ''} on the exchanges' lists {'is' if len(gaps) == 1 else 'are'} missing from ours."
                                       if gaps else problems[0][:200] if problems else None),
                           check=(f"{len(waits)} filing{'s' if len(waits) != 1 else ''} with the regulators {'has' if len(waits) == 1 else 'have'} no exchange "
                                  "listing yet; looked for again each day." if waits else None))
        return {"rows": len(rows), "problems": problems, "missing": missing}

    def read_open(self, now: datetime, final: bool = False) -> int:
        """The bids of the Indian issues open now (or, after 19:20, the issues that closed in the last two days): their own pages."""
        feed = _wire["feed"]()
        rows = load("IN")["rows"]
        local = now.astimezone(IST).date()
        problems, n = [], 0
        for r in rows:
            st = stage_of(r, now)
            recent = r.get("close") and (local - date.fromisoformat(r["close"])).days <= 2
            if not r.get("symbol") or not (st == "open" or (final and (st == "closed" or recent))):
                continue
            got = _try(problems, r["symbol"], lambda r=r: S.nse_detail(feed.nse.ipo_detail(r["symbol"], r.get("series") or "EQ")))
            if got:
                apply_detail(r, got)
                n += 1
            self.sleep(0.6)
        if n:
            load_ = load("IN")
            save("IN", rows, load_["checked"], as_of=load_["as_of"])
        self._live_at = time.time()
        self.status.update(last_run=now.isoformat(timespec="seconds"), read="IN bids", problems=problems[:5], last_error=problems[0][:200] if problems else None)
        return n

    def read_docs(self, now: datetime, limit: int = SMALL) -> int:
        """Read the offer documents not read yet (the ones nearest their dates first), then summarise the ones read: a few a pass."""
        todo = []
        for m in ("IN", "US"):
            for r in load(m)["rows"]:
                d = doc_to_read(r)
                st = stage_of(r, now)
                if d and st in ("open", "upcoming", "closed", "listed", "filed") and not facts_of(d) and (st != "listed" or not (r.get("listing") or r.get("priced") or "") < (now.date() - timedelta(days=30)).isoformat()):
                    todo.append((0 if st in ("open", "closed") else 1 if st == "upcoming" else 2, r.get("open") or r.get("expected") or r.get("filed") or "", r, d))
        todo.sort(key=lambda t: (t[0], t[1]))
        done, problems = 0, []
        for _, _, r, d in todo[:limit]:
            tried = db.json_value(db.get_setting("ipo:try:" + doc_key(d)), {})
            if tried.get("n", 0) >= 3 and tried.get("at", "") > (now - timedelta(days=1)).isoformat():
                continue
            try:
                read_doc(r, d, _wire["sebi"]())
                done += 1
            except Exception as e:
                problems.append(f"{r['name'][:30]}: {str(e)[:100]}")
                db.set_setting("ipo:try:" + doc_key(d), json.dumps({"n": tried.get("n", 0) + 1, "at": now.isoformat(timespec="seconds")}))
        made = 0
        for m in ("IN", "US"):
            for r in load(m)["rows"]:
                d = doc_to_read(r)
                facts = facts_of(d)
                if made >= 2 or not d or not facts or summary_of(d) or not facts.get("excerpt"):
                    continue
                if not _ai_budget():
                    problems.append("Today's summary limit is reached; the rest are written tomorrow.")
                    break
                try:
                    make_summary(r, d, facts, _wire["ai"]() if _wire["ai"] else None)
                    made += 1
                except AIError as e:
                    problems.append(f"{r['name'][:30]}: {str(e)[:100]}")
                    break
        if done or made or problems:
            self.status.update(docs=self.status["docs"] + done, summaries=self.status["summaries"] + made, last_run=now.isoformat(timespec="seconds"),
                               **({"problems": problems[:5], "last_error": problems[0][:200]} if problems else {}))
        return done + made


job = Job()


# ---------- the API ----------
def _rows_of(market: str) -> list[dict]:
    return load(market)["rows"]


def _find(rid: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", rid or ""):
        err(404, "no_ipo", "That IPO isn't on the list.")
    for m in ("IN", "US"):
        for r in _rows_of(m):
            if r["id"] == rid:
                return r
    err(404, "no_ipo", "That IPO isn't on the list.")


DOC_NAMES = {"RHP": "Red herring prospectus (RHP)", "DRHP": "Draft red herring prospectus (DRHP)", "Prospectus": "Prospectus", "Addendum": "Addendum",
             "S-1": "Registration statement (S-1)", "S-1/A": "Amended registration statement (S-1/A)", "F-1": "Registration statement (F-1)",
             "F-1/A": "Amended registration statement (F-1/A)", "424B4": "Final prospectus (424B4)", "424B1": "Final prospectus (424B1)",
             "424B3": "Prospectus (424B3)", "424B5": "Prospectus (424B5)"}
SOURCE_NAMES = {"sebi": "SEBI", "nse": "NSE, ZIP", "sec": "SEC"}
LINK_HOSTS = ("https://www.sebi.gov.in/", "https://nsearchives.nseindia.com/", "https://www.sec.gov/")


def doc_links(row: dict) -> list[dict]:
    """The offer documents to open, from the regulators' and exchanges' own sites, the one the facts are read from first."""
    first = doc_to_read(row)
    out = []
    for d in row.get("docs") or []:
        url = d.get("link") or d.get("url") or ""
        if not url.startswith(LINK_HOSTS):
            continue
        kind = d.get("kind") or ""
        out.append({"kind": kind, "label": DOC_NAMES.get(kind, kind or "Document"), "source": SOURCE_NAMES.get(d.get("source"), ""), "url": url,
                    "date": d.get("date"), "read": bool(first and first.get("url") == d.get("url"))})
    order = {"RHP": 0, "Prospectus": 0, "424B4": 0, "424B1": 0, "DRHP": 1, "S-1/A": 1, "F-1/A": 1, "S-1": 2, "F-1": 2}
    return sorted(out, key=lambda d: (order.get(d["kind"], 3), d["source"] != "SEBI", d["date"] or ""))[:8]


def list_row(row: dict, now: datetime) -> dict:
    pub = public(row, now)
    sub = row.get("sub") or {}
    perf = official_perf(row, row.get("perf"), now)
    keys = ("id", "market", "segment", "name", "symbol", "stage", "open", "close", "close_time", "allotment", "allotment_expected", "listing", "listing_expected",
            "low", "high", "price", "lot", "min_amount", "min_basis", "size", "size_basis", "size_parts", "issue_status", "exchanges", "exchange",
            "expected", "priced", "filed", "shares", "currency")
    out = {k: pub.get(k) for k in keys if pub.get(k) is not None}
    out["docs"] = sorted({d["kind"] for d in doc_links(row) if d["kind"]})
    if sub.get("times") is not None:
        out["sub_times"], out["sub_as_of"] = sub["times"], sub.get("as_of")
        if pub["stage"] == "open" and row.get("sub_read"):
            out["sub_read"] = row["sub_read"]
    if perf:
        out["perf"] = {k: perf.get(k) for k in ("listing_price", "listing_change_pct", "latest", "change_pct", "latest_date", "at") if perf.get(k) is not None}
    return out


ORDER = {"upcoming": (lambda r: r.get("open") or r.get("expected") or "9999", False), "open": (lambda r: r.get("close") or "", False),
         "closed": (lambda r: r.get("listing") or r.get("close") or "", False), "listed": (lambda r: r.get("listing") or r.get("priced") or "", True),
         "filed": (lambda r: r.get("filed") or "", True),
         "withdrawn": (lambda r: r.get("close") or r.get("open") or "", True), "social": (lambda r: r.get("close") or r.get("open") or "", True)}


def channels_of(profile: dict) -> list[str]:
    from . import stock_alerts
    try:
        return stock_alerts.channels(profile)
    except Exception:
        return []


def prefs_view(profile: dict) -> dict:
    p = prefs(profile["id"])
    return {"on": p["on"], "events": p["events"], "markets": p["markets"], "sme": p["sme"], "allowed": allows(profile["_plan"], "ipo_alerts"),
            "plan": PLANS[FEATURE_PLAN["ipo_alerts"]]["name"], "channels": channels_of(profile), "event_names": EVENTS}


@router.get("/invest/ipos")
def ipos_list(market: str = "IN", profile=Depends(current_profile)):
    """One market's issues in their stages (upcoming, open, closed and awaiting listing, recently listed, and offer documents filed with no dates
    yet), each with its dates, price band, lot, size and the bids so far; and your IPO alert settings. Free for everyone."""
    if market not in ("IN", "US"):
        err(404, "no_market", "That market isn't on the list.")
    now = _now()
    got = load(market)
    tabs: dict[str, list] = {k: [] for k in ORDER}
    for r in got["rows"]:
        tabs.setdefault(stage_of(r, now), []).append(r)
    out = {}
    for k, rows in tabs.items():
        key, rev = ORDER[k]
        out[k] = [list_row(r, now) for r in sorted(rows, key=key, reverse=rev)][:120]
    # the bids of the open issues are read through the day, the lists twice: when the newest bids were read, and when the lists' problems were noted
    reads = [r.get("sub_read") for r in tabs.get("open", []) if r.get("sub_read")]
    return ok({"market": market, "as_of": got["as_of"], "bids_read": max(reads) if reads else None, "tabs": out, "counts": {k: len(v) for k, v in tabs.items()}, "note": NOTE[market],
               "problems": (got["checked"].get("problems") or [])[:3], "problems_at": got["checked"].get("read") if got["checked"].get("problems") else None, "prefs": prefs_view(profile), "today": now.astimezone(IST if market == "IN" else NY).date().isoformat()})


_live: dict[str, float] = {}


def live_refresh(row: dict, now: datetime) -> bool:
    """An open Indian issue's bids, read again when the stored ones are older than five minutes (through the bidding hours), so a
    page open during bidding is never a quarter of an hour behind. One read per issue at a time."""
    if row["market"] != "IN" or stage_of(row, now) != "open" or not row.get("symbol") or not _wire["feed"]:
        return False
    local = now.astimezone(IST)
    lo, hi = live_window(row)
    if not (lo <= local.strftime("%H:%M") <= hm_add(hi, -LIVE_AFTER)):
        return False
    if time.time() - _live.get(row["id"], 0) < 300:
        return False
    _live[row["id"]] = time.time()
    try:
        got = S.nse_detail(_wire["feed"]().nse.ipo_detail(row["symbol"], row.get("series") or "EQ"))
    except Exception:
        return False
    if not got:
        return False
    with _lock:
        cur = load("IN")
        for r in cur["rows"]:
            if r["id"] == row["id"]:
                apply_detail(r, got)
                row.update(r)
        save("IN", cur["rows"], cur["checked"], as_of=cur["as_of"])
    return True


def facts_view(row: dict) -> dict:
    d = doc_to_read(row)
    f = facts_of(d)
    if not d:
        return {"state": "none"}
    if not f:
        return {"state": "pending", "kind": d.get("kind")}
    out = {k: f[k] for k in ("promoters", "selling", "objects", "financials", "us", "pages_read", "utilisation", "risks", "kpis", "holding", "peers", "eps") if k in f}
    if out.get("objects"):
        out["objects"] = D.objects_view(out["objects"])
    return {"state": "ready", "kind": f.get("kind"), "read_at": f.get("read_at"), **out}


def summary_view(row: dict, profile: dict) -> dict:
    allowed = allows(profile["_plan"], "ipo_summary")
    plan = PLANS[FEATURE_PLAN["ipo_summary"]]["name"]
    d = doc_to_read(row)
    if not allowed:
        return {"allowed": False, "plan": plan, "state": "locked", "kind": d.get("kind") if d else None}
    if not d:
        return {"allowed": True, "plan": plan, "state": "none"}
    s = summary_of(d)
    if s and s.get("items"):
        return {"allowed": True, "plan": plan, "state": "ready", "kind": d.get("kind"), "at": s.get("at"), "items": D.tidy_summary(s["items"])}
    if s and s.get("problem"):
        return {"allowed": True, "plan": plan, "state": "problem", "kind": d.get("kind"), "message": s["problem"]}
    return {"allowed": True, "plan": plan, "state": "pending", "kind": d.get("kind")}


@router.get("/invest/ipos/alerts")
def ipos_alerts_get(profile=Depends(current_profile)):
    return ok(prefs_view(profile))


class AlertReq(BaseModel):
    on: bool = False
    events: list[str] = Field(default_factory=lambda: list(EVENTS), max_length=len(EVENTS))
    markets: list[str] = Field(default_factory=lambda: ["IN"], max_length=2)
    sme: bool = False


@router.put("/invest/ipos/alerts")
def ipos_alerts_put(req: AlertReq, profile=Depends(current_profile)):
    """Your IPO alert settings: which events, which markets, and whether SME issues count. Turning alerts on is Basic and up."""
    if req.on and not allows(profile["_plan"], "ipo_alerts"):
        err(402, "upgrade_required", f"IPO alerts are on the {PLANS[FEATURE_PLAN['ipo_alerts']]['name']} plan.")
    events = [e for e in dict.fromkeys(req.events) if e in EVENTS]
    markets = [m for m in dict.fromkeys(req.markets) if m in ("IN", "US")]
    if req.on and (not events or not markets):
        err(400, "nothing_picked", "Pick at least one kind of event and one market to be alerted about.")
    p = prefs(profile["id"])
    p.update(on=req.on, events=events, markets=markets, sme=req.sme)
    save_prefs(profile["id"], p)
    return ok(prefs_view(profile))


@router.get("/invest/ipos/{rid}")
def ipo_detail(rid: str, profile=Depends(current_profile)):
    """One issue: its dates, price band, lot, size, the offer document and what a rule reads from it (promoters, selling
    shareholders, the objects, the last three years' revenue and profit), the bids by category, how it has traded since listing, and
    the summary (Basic and up). Free for everyone except the summary."""
    row = _find(rid)
    now = _now()
    live_refresh(row, now)
    pub = public(row, now)
    sub = (row.get("sub") or None)
    perf = row.get("perf") if (row.get("perf") or {}).get("at", "") > (now - timedelta(hours=1)).isoformat() else None
    if pub["stage"] == "listed" and not perf:
        perf = perf_for(row) or row.get("perf")
    perf = official_perf(row, perf, now)
    keys = ("id", "market", "segment", "name", "symbol", "stage", "isin", "industry", "exchanges", "exchange", "open", "close", "close_time", "hours", "allotment", "allotment_expected",
            "listing", "listing_expected", "low", "high", "price", "lot", "retail_max", "face_value", "min_amount", "min_basis", "size", "size_basis", "size_parts", "issue_status",
            "fresh", "ofs", "fresh_cr", "ofs_cr", "size_shares", "issue_type", "issue_text", "lead_managers", "registrar", "expected", "priced", "filed",
            "shares", "amount", "currency", "industry")
    ipo = {k: pub.get(k) for k in keys if pub.get(k) is not None}
    if row["market"] == "IN" and row.get("symbol"):
        ipo["company_link"] = f"/research/IN/{row['symbol']}"
    elif row["market"] == "US" and row.get("symbol"):
        ipo["company_link"] = f"/research/US/{row['symbol']}"
    return ok({"ipo": ipo, "documents": doc_links(row), "facts": facts_view(row), "summary": summary_view(row, profile),
               "subscription": ({**sub, "live": pub["stage"] == "open", "read": row.get("sub_read")} if sub else None), "perf": perf,
               "note": NOTE[row["market"]], "prefs": prefs_view(profile)})


_reading = threading.Lock()


@router.post("/invest/ipos/{rid}/summary")
def ipo_summary(rid: str, profile=Depends(current_profile)):
    """Read the offer document and write its summary now, when the scheduled job hasn't yet (Basic and up). Each document is
    summarised once for everyone; this reads one at a time."""
    if not allows(profile["_plan"], "ipo_summary"):
        err(402, "upgrade_required", f"The summary of the offer document is on the {PLANS[FEATURE_PLAN['ipo_summary']]['name']} plan.")
    row = _find(rid)
    d = doc_to_read(row)
    if not d:
        err(404, "no_document", "No offer document has been found for this issue yet.")
    if not summary_of(d):
        if not _reading.acquire(blocking=False):
            err(429, "busy", "Another offer document is being read. Try again in a minute.")
        try:
            facts = facts_of(d)
            try:
                facts = facts or read_doc(row, d, _wire["sebi"]())
                if not summary_of(d):
                    if not _ai_budget():
                        err(429, "ai_limit", "Today's summary limit is reached. The summary is written tomorrow, or by the schedule when its turn comes.")
                    make_summary(row, d, facts, _wire["ai"]() if _wire["ai"] else None)
            except AIError as e:
                err(503, "ai_unavailable", str(e))
            except SourceError as e:
                err(503, "document_unavailable", str(e))
        finally:
            _reading.release()
    return ok({"facts": facts_view(row), "summary": summary_view(row, profile)})


@router.post("/admin/ipos/refresh")
def ipos_refresh(_=Depends(admin.admin_profile)):
    """Read both markets' sources now, in the background (a minute or two), and the offer documents after them. No alerts go out."""
    if not job.busy.acquire(blocking=False):
        return ok({"started": False, "job": job.status})

    def run():
        try:
            now = _now()
            for m in ("IN", "US"):
                job.read(m, now, perf=True)
            job.read_open(now)
            job.read_docs(now, limit=6)
        except Exception as e:
            job.status["last_error"] = str(e)[:200]
            print("ipos refresh failed:", type(e).__name__, str(e)[:160])
        finally:
            job.busy.release()
    threading.Thread(target=run, daemon=True, name="ipos-refresh").start()
    return ok({"started": True, "job": job.status})
