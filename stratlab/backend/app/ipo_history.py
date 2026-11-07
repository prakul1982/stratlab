"""IPO history (India): every main-board and SME issue listed in the last 24 months, kept beside the live IPO rows.

The live list (ipo.py, `ipo:rows:IN`) keeps a listed issue for KEEP_LISTED_DAYS only. This keeps the listed ones for MONTHS, in the
same row shape and in the same store (one stored JSON value, `ipo:history:IN`), so the IPO study (ipo_study.py) has two years to count:

- `backfill` (admin-triggered, POST /admin/ipos/history/backfill): NSE's past issues read a quarter at a time over the window, BSE's
  table of its listed issues for each calendar year in it, then each issue's own NSE page (terms, fresh issue and offer for sale,
  industry, the final bids by category) and its trading since listing (listing open and close, latest close), a bounded number of
  each per run. Running it again adds only what is missing: it is safe to run as often as needed until `pending` is zero.
- `absorb` (the daily IPO job, after each India read): the issues the live list holds as listed are copied in, with their bids and
  trading, so the history stays current without another read of the sources.

Facts from the exchanges' own pages only; nothing here forecasts or advises."""
import json
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as dtime

from fastapi import APIRouter, Depends

from . import admin, db
from . import ipo as I
from .intel import ipo_sources as S
from .responses import ok

router = APIRouter()
HIST_KEY = "ipo:history:IN"
MONTHS = 24
WINDOW_DAYS = 90                  # NSE's past-issues list is asked for a quarter at a time
DETAILS_PER_RUN = 40              # issue pages read per run (each is one call to the exchange)
PRICES_PER_RUN = 80               # issues whose trading since listing is read per run
RETRY_DAYS = 7                    # an issue page or price read that found nothing is tried again after this long
SEGMENTS = ("mainboard", "sme")
DROP = ("docs", "seen", "docs_checked", "_keys", "lead_managers", "registrar", "hours", "open_time", "close_time", "sebi_url", "filed")
_lock = threading.Lock()
status = {"running": False, "last": None, "error": None}


def cutoff(today: date) -> date:
    return today - timedelta(days=round(MONTHS * 365.25 / 12))


def load() -> dict:
    got = db.json_value(db.get_setting(HIST_KEY), {})
    rows = [r for r in got.get("rows") or [] if isinstance(r, dict) and r.get("id")]
    return {"as_of": got.get("as_of"), "rows": rows, "runs": got.get("runs") if isinstance(got.get("runs"), list) else []}


def save(rows: list[dict], run: dict | None = None) -> None:
    cur = load()
    runs = (cur["runs"] + [run])[-10:] if run else cur["runs"]
    db.set_setting(HIST_KEY, json.dumps({"as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": rows, "runs": runs},
                                        separators=(",", ":"), ensure_ascii=False))


def keeps(row: dict, today: date) -> bool:
    """A listed Indian issue in the window: a main-board or SME issue (or one only BSE's table names, segment unknown), not withdrawn
    and not a Social Stock Exchange raise."""
    listing = str(row.get("listing") or "")
    return (row.get("market") == "IN" and not row.get("issue_status") and not row.get("social") and not row.get("listing_expected")
            and row.get("segment") in SEGMENTS + (None,) and bool(listing)
            and cutoff(today).isoformat() <= listing <= today.isoformat())


def slim(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in DROP}


def merge(old: list[dict], past: list[dict], perf: list[dict], today: date) -> list[dict]:
    """The history after a read: NSE's past issues (parsed by S.nse_past) by symbol, BSE's listed-issue table (S.bse_performance) joined
    by company name, and the stored rows kept with every fact a read did not give again. One row per issue, ids as the live list's."""
    by_id = {r["id"]: dict(r) for r in old}
    for p in past:
        if not p.get("listing"):
            continue
        row = {"id": I.india_id(p["symbol"], None), "market": "IN", "segment": p["segment"], "name": p["name"], "symbol": p["symbol"],
               "series": p.get("series"), "open": p.get("open"), "close": p.get("close"), "low": p.get("low"), "high": p.get("high"),
               "price": p.get("price"), "listing": p["listing"], "exchanges": ["NSE"], "currency": "INR", "nkey": S.name_key(p["name"]),
               "issue_status": p.get("issue_status"), "social": p.get("social")}
        by_id[row["id"]] = I._keep_old(by_id.get(row["id"]), row)
    keys = {r.get("nkey"): r for r in by_id.values() if r.get("nkey")}
    for p in perf:
        key, code = S.name_key(p["name"]), re.search(r"/(\d{5,6})/?$", p.get("url") or "")
        facts = {k: p[k] for k in ("issue_price", "listed", "day_close", "latest", "url") if p.get(k) is not None}
        row = keys.get(key)
        if row is None:
            if not code or not p.get("listed"):
                continue
            # (BSE's table of listed issues is its main board's: in the saved answer of 25 Oct 2026 each of the 82 issues it shared with
            # NSE's list from June was a main-board one, and none of NSE's 39 SME issues was in it)
            row = {"id": I.india_id(None, code.group(1)), "market": "IN", "segment": "mainboard", "name": p["name"].title() if p["name"].isupper() else p["name"],
                   "symbol": None, "bse_code": code.group(1), "listing": p["listed"], "price": p.get("issue_price"), "exchanges": ["BSE"],
                   "currency": "INR", "nkey": key}
            row = I._keep_old(by_id.get(row["id"]), row)
            by_id[row["id"]] = keys[key] = row
        row["bse_perf"] = facts
        row["exchanges"] = sorted(set((row.get("exchanges") or []) + ["BSE"]))
        if code:
            row.setdefault("bse_code", code.group(1))
        if not row.get("price") and p.get("issue_price"):
            row["price"] = p["issue_price"]
    rows = I.dedupe_india(list(by_id.values()))
    return sorted((slim(r) for r in rows if keeps(r, today)), key=lambda r: (r["listing"], r["id"]), reverse=True)


def absorb(live: list[dict], today: date, now: datetime | None = None) -> int:
    """The daily job's part: the live list's listed issues copied into the history (their bids, terms and trading included). Returns how
    many rows were added or changed. Nothing is read from the sources."""
    now = now or datetime.now(timezone.utc)
    got = [slim(r) for r in live if r.get("market") == "IN" and I.stage_of(r, now) == "listed" and keeps(r, today)]
    if not got:
        return 0
    with _lock:
        cur = load()
        by_id = {r["id"]: r for r in cur["rows"]}
        n = 0
        for r in got:
            merged = I._keep_old(by_id.get(r["id"]), r)
            if merged != by_id.get(r["id"]):
                by_id[r["id"]], n = merged, n + 1
        if n:
            rows = I.dedupe_india(list(by_id.values()))
            save(sorted((r for r in rows if keeps(r, today)), key=lambda r: (r["listing"], r["id"]), reverse=True))
        return n


def _due(r: dict, key: str, today: date) -> bool:
    return str(r.get(key) or "") <= (today - timedelta(days=RETRY_DAYS)).isoformat()


def wants_detail(r: dict, today: date) -> bool:
    return bool(r.get("symbol") and r.get("series") and not r.get("detail_at") and _due(r, "detail_tried", today))


def wants_prices(r: dict, today: date) -> bool:
    has = (r.get("perf") or {}).get("day_change_pct") is not None
    return bool((r.get("symbol") or r.get("bse_code")) and not has and _due(r, "perf_tried", today))


def backfill(feed, today: date, yahoo=None, details: int = DETAILS_PER_RUN, prices: int = PRICES_PER_RUN, pace: float = 0.6,
             sleep=time.sleep, now: datetime | None = None) -> dict:
    """One run of the two-year import (see the module's note). Returns what it did and what is left for the next run."""
    now = now or datetime.now(timezone.utc)
    problems: list[str] = []
    past: list[dict] = []
    start = cutoff(today)
    frm = start
    while frm <= today:
        to = min(frm + timedelta(days=WINDOW_DAYS - 1), today)
        got = I._try(problems, f"past issues {frm:%d %b %Y} to {to:%d %b %Y}",
                     lambda f=frm, t=to: feed.nse.ipo_past(datetime.combine(f, dtime()), datetime.combine(t, dtime())), [])
        past += S.nse_past(got)
        frm = to + timedelta(days=1)
        sleep(pace)
    perf: list[dict] = []
    for year in range(start.year, today.year + 1):
        perf += S.bse_performance(I._try(problems, f"listed issues of {year}", lambda y=year: feed.bse.ipo_listed(y), {}))
        sleep(pace)
    with _lock:
        before = {r["id"] for r in load()["rows"]}
        rows = merge(load()["rows"], past, perf, today)
        live = {r["id"]: r for r in I.load("IN")["rows"]}
        rows = [I._keep_old(r, slim(live[r["id"]])) if r["id"] in live and I.stage_of(live[r["id"]], now) == "listed" else r for r in rows]
        detailed = priced = 0
        for r in [r for r in rows if wants_detail(r, today)][:details]:
            r["detail_tried"] = today.isoformat()
            got = I._try(problems, r["symbol"], lambda r=r: S.nse_detail(feed.nse.ipo_detail(r["symbol"], r.get("series") or "EQ")))
            if got:
                I.apply_detail(r, got)
                for k in DROP:
                    r.pop(k, None)
                detailed += 1
            sleep(pace)
        if yahoo is not None:
            for r in [r for r in rows if wants_prices(r, today)][:prices]:
                r["perf_tried"] = today.isoformat()
                got = I.performance(r, yahoo, today, now)
                if got:
                    r["perf"] = {**got, "at": now.isoformat(timespec="seconds")}
                    priced += 1
        run = {"at": now.isoformat(timespec="seconds"), "rows": len(rows), "added": len({r["id"] for r in rows} - before), "detailed": detailed,
               "priced": priced, "pending_details": sum(1 for r in rows if wants_detail(r, today)),
               "pending_prices": sum(1 for r in rows if wants_prices(r, today)) if yahoo is not None else None, "problems": problems[:8]}
        save(rows, run)
    return run


def summary(today: date) -> dict:
    cur = load()
    rows = cur["rows"]
    seg = {s or "not recorded": sum(1 for r in rows if r.get("segment") == s) for s in SEGMENTS + (None,)}
    return {"as_of": cur["as_of"], "rows": len(rows), "segments": seg, "from": cutoff(today).isoformat(), "to": today.isoformat(),
            "with_bids": sum(1 for r in rows if r.get("sub")), "with_trading": sum(1 for r in rows if r.get("perf")),
            "last_runs": cur["runs"][-3:], "running": status["running"], "error": status["error"]}


def _spawn(fn) -> None:
    threading.Thread(target=fn, daemon=True, name="ipo-history").start()


@router.get("/admin/ipos/history")
def history_status(_=Depends(admin.admin_profile)):
    """Admin: what the two-year IPO history holds and its last runs."""
    return ok(summary(I._now().astimezone(I.IST).date()))


@router.post("/admin/ipos/history/backfill")
def history_backfill(_=Depends(admin.admin_profile)):
    """Admin: one run of the two-year import, in the background (a few minutes). Run it again until nothing is pending."""
    if status["running"]:
        return ok({"started": False, **summary(I._now().astimezone(I.IST).date())})
    status.update(running=True, error=None)

    def run():
        try:
            yahoo = I._wire["yahoo"]() if I._wire.get("yahoo") else None
            now = I._now()
            status["last"] = backfill(I._wire["feed"](), now.astimezone(I.IST).date(), yahoo, now=now)
        except Exception as e:
            status["error"] = f"{type(e).__name__} {str(e)[:160]}"
            print("ipo history failed:", status["error"])
        finally:
            status["running"] = False
    _spawn(run)
    return ok({"started": True, **summary(I._now().astimezone(I.IST).date())})
