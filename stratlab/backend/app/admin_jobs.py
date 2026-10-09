"""Admin -> Data and jobs: one read of every background job (what it is, when it last ran, when it runs next, how the last
run went) and the routes that run one now. GET /admin/jobs lists them; each row carries `run`, the admin routes that
start it (empty for a job with no manual trigger). Facts only: the schedule text says when the job's own clock runs it."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from . import admin, job_status

router = APIRouter(tags=["admin"])


def _m():
    """The main module, where the jobs live. Imported late: it imports us."""
    from . import main
    return main


def _iso(unix) -> str | None:
    try:
        return datetime.fromtimestamp(float(unix), tz=timezone.utc).isoformat(timespec="seconds") if unix else None
    except (TypeError, ValueError, OverflowError):
        return None


_ERROR_CLASS = re.compile(r"\s*\((?:[A-Za-z_]+\.)*[A-Z][A-Za-z]*(?:Error|Exception|Timeout)\)")


def plain_error(text: str | None) -> str | None:
    """A job's problem in words for the table: "Couldn't reach www.rbi.org.in." without the "(ConnectError)" the
    reader adds. The log keeps the full text."""
    return _ERROR_CLASS.sub("", text).strip() if text else text


def _row(id: str, name: str, schedule: str, last_run: str | None, error: str | None = None, log: list[str] | None = None,
         run: list[dict] | None = None, running: bool = False, note: str | None = None, parts: int | None = None) -> dict:
    """One job. `parts`: how many sources the last run tried, for a job that reads several (each failed one is a line
    of `log`); when some were read and some weren't, the run is partial: Check, not Problem."""
    state = "bad" if error else "ok" if last_run else "warn"
    problems = [str(x) for x in (log or []) if x] if error else []
    failed = len(problems)
    if error and parts and 0 < failed < parts:
        state = "warn"
        error = f"Partial: {parts - failed} of {parts} sources read. Not read: {plain_error(problems[0])}" + (f" And {failed - 1} more (see the log)." if failed > 1 else "")
    else:
        error = plain_error(error)
    return {"id": id, "name": name, "schedule": schedule, "last_run": last_run, "error": error, "state": state,
            "running": bool(running), "log": [str(x)[:240] for x in (log or []) if x][:8], "run": run or [], "note": note}


def _plain(job, key: str | None = None) -> dict:
    """A job's status; with `key`, the one kept from before a restart while this server hasn't run the job yet."""
    st = dict(getattr(job, "status", None) or {})
    return job_status.kept(key, st) if key else st


def data_at(fn) -> str | None:
    """When a feed's stored data was last written, by the data's own stamp; None when it can't be read. Used when this
    server hasn't run the job and nothing was kept (R6O-003: nine fresh feeds on "Not run yet")."""
    try:
        got = fn()
        return str(got) if got else None
    except Exception:
        return None


def _ran(st: dict, *keys: str, data=None) -> tuple[str | None, list[str]]:
    """(last run, an extra log line): the job's own run when it has one, else the stored data's own time."""
    for k in keys:
        if st.get(k):
            return st[k], []
    at = data_at(data) if data else None
    return at, ["Time from the stored data: this server hasn't run the job since its last restart."] if at else []


def recorded_through(targets: list[str]) -> str | None:
    """The last day any recorded option chain covers (the same summary Positioning shows), or None."""
    from . import positioning
    days = []
    for t in targets:
        name = str(t).split(":", 1)[-1]
        try:
            last = positioning.chain_coverage(name).get("last")
        except Exception:
            last = None
        if last:
            days.append(str(last))
    return max(days) if days else None


def _problems(st: dict) -> list[str]:
    return [str(p) for p in (st.get("problems") or [])]


KEPT = ("positioning", "etf", "results", "corp", "events", "fo", "surveillance", "closing-auction", "vix", "option-chains")


def rows() -> list[dict]:
    """Every job's row. The rows are read side by side (each one's database and file reads), in the order listed, so
    Overview's data feeds no longer wait for each job in turn (R7O-006: 8 to 23 s)."""
    m = _m()
    out: list[dict] = []
    builds: list[tuple[str, object]] = []
    # every kept status in one database read, not one per job (R6O-023: Overview still "Loading the data feeds" at 5 s)
    try:
        from . import db
        db.prefetch_settings([f"jobstatus:{k}" for k in KEPT])
    except Exception:
        pass

    def add(name: str, build):
        builds.append((name, build))

    def breadth():
        s = m.breadth.status() or {}
        ok = {r: v for r, v in s.items() if isinstance(v, dict) and v.get("ran_at")}
        failed = [(r, v) for r, v in s.items() if isinstance(v, dict) and v.get("failed_at") and (not v.get("ran_at") or v["failed_at"] > v["ran_at"])]
        log = [f"{r}: {v.get('loaded', 0)} stocks read, prices to {v.get('as_of')}" + (f", {v['failed']} failed" if v.get("failed") else "") for r, v in ok.items()]
        log += [f"{r}: trend scans of {v['scan_stocks']} stocks took {v['scan_seconds']} s" for r, v in ok.items() if v.get("scan_stocks")]
        err = "; ".join(f"{r}: {v.get('last_error')}" for r, v in failed if v.get("last_error")) or None
        return _row("breadth", "Market breadth", "India about 6:30 PM IST, US about 5:45 PM New York time, on trading days",
                    max((v["ran_at"] for v in ok.values()), default=None), err, log,
                    [{"label": "Run India", "path": "/admin/breadth/run?region=IN&full=true"}, {"label": "Run US", "path": "/admin/breadth/run?region=US&full=true"}],
                    running=m.breadth_runner.running,
                    note="The first run reads two years of prices: a few minutes for the US, 20 to 25 minutes for India (it needs the day's broker login).")
    add("Market breadth", breadth)

    def redflags():
        st = {r: m.redflags.state(r) for r in m.redflags.REGIONS}
        done = {r: v for r, v in st.items() if v.get("at")}
        failed = [(r, v) for r, v in st.items() if v.get("failed_at") and (not v.get("at") or v["failed_at"] > v["at"])]
        log = [f"{r}: read to {v.get('through')}" + (f", {v['companies']} companies" if v.get("companies") else "") for r, v in done.items()]
        err = "; ".join(f"{r}: {v.get('last_error')}" for r, v in failed if v.get("last_error")) or None
        return _row("redflags", "Red flags across companies", "India about 9 PM IST, US about 7:30 PM New York time, on trading days",
                    max((v["at"] for v in done.values()), default=None), err, log,
                    [{"label": "Run India", "path": "/admin/redflags/run?region=IN"}, {"label": "Run US", "path": "/admin/redflags/run?region=US"}],
                    running=bool(m.redflags_runner.running))
    add("Red flags across companies", redflags)

    def positioning():
        st = _plain(m.positioning_job, "positioning")
        from . import positioning as P
        at, why = _ran(st, "last_run", data=lambda: P.state().get("last_run"))
        return _row("positioning", "Positioning", "Trading days from 6:40 PM IST until the day's files are in", at,
                    st.get("last_error"), [str(st.get("last_result") or "")] + why, [{"label": "Run now", "path": "/admin/positioning/run"}],
                    running=m.positioning_runner.running)
    add("Positioning", positioning)

    def etf():
        st = _plain(m.etf_job, "etf")
        from . import etf_nav
        at, why = _ran(st, "read", "last_run", data=lambda: etf_nav.load_live().get("read"))
        return _row("etf", "ETF price against NAV", "Every 4 minutes while the market is open; closing prices after 3:45 PM IST",
                    at, st.get("last_error"),
                    [f"Closing prices recorded for {st['recorded']}" if st.get("recorded") else "", f"{st.get('filled')} NAVs filled in" if st.get("filled") else ""] + why,
                    [{"label": "Read now", "path": "/admin/etf-gaps/refresh"}])
    add("ETF price against NAV", etf)

    def ter():
        s = m.money_mf_ter.status()
        return _row("ter", "Fund costs (TER)", "Every 12 hours when someone opens the page", _iso(s.get("last_ok")), s.get("error"),
                    [f"{s.get('schemes', 0)} schemes for {s.get('month')}" if s.get("last_ok") else "",
                     f"{s.get('stored', 0)} schemes stored over {s.get('months', 0)} months"],
                    [{"label": "Read now", "path": "/admin/ter/read"}], running=bool(s.get("running")))
    add("Fund costs (TER)", ter)

    def holidays():
        a = m.calendar_status().get("auto") or {}
        return _row("holidays", "Exchange holidays", "Every day", a.get("at"), a.get("error"),
                    [f"{a['count']} holidays in the last read" if a.get("at") else ""], [{"label": "Read now", "path": "/admin/holidays/refresh"}])
    add("Exchange holidays", holidays)

    def results():
        st = _plain(m.results_job, "results")
        return _row("results", "Results calendar", "India 7:15 AM and 6:30 PM IST, US 6:00 AM New York time", st.get("last_run"),
                    st.get("last_error"), _problems(st), [{"label": "Run now", "path": "/admin/results/refresh"}])
    add("Results calendar", results)

    def corp():
        st = _plain(m.corp_job, "corp")
        from . import corp_actions
        at, why = _ran(st, "last_run", data=lambda: max(filter(None, (corp_actions.load(r).get("at") for r in corp_actions.REGIONS)), default=None))
        return _row("corp", "Corporate actions", "India 7:20 AM and 6:40 PM IST, US 6:10 AM New York time", at,
                    st.get("last_error"), _problems(st) + why, [{"label": "Run now", "path": "/admin/corp-actions/refresh"},
                                                           {"label": "Read the whole US universe", "path": "/admin/corp-actions/refresh?universe=true"}],
                    running=bool(getattr(m.corp_job, "universe_running", False)),
                    note="The US list covers the S&P 500 and StratLab's own groups, read from price histories at 6:20 AM New York time (several minutes).")
    add("Corporate actions", corp)

    def events():
        from . import market_events_routes as r
        st = _plain(r.job, "events")
        from . import market_events
        at, why = _ran(st, "last_run", data=lambda: market_events.load_state().get("last_run"))
        return _row("events", "Market events", "7:20 AM and 6:40 PM IST", at, st.get("last_error"), _problems(st) + why,
                    [{"label": "Run now", "path": "/admin/events/refresh"}], parts=st.get("parts"))
    add("Market events", events)

    def fo():
        from . import fo_changes_routes as r
        st = _plain(r.job, "fo")
        from . import fo_changes
        at, why = _ran(st, "last_run", data=lambda: fo_changes.load_state().get("last_run"))
        return _row("fo", "F&O contract changes", "8:15 AM and 7:50 PM IST on trading days", at, st.get("last_error"),
                    _problems(st) + why, [{"label": "Run now", "path": "/admin/fo-changes/refresh"}], parts=st.get("parts"))
    add("F&O contract changes", fo)

    def surv():
        st = _plain(m.surv_job, "surveillance")
        from . import surveillance
        at, why = _ran(st, "last_run", data=lambda: max((p.get("checked") or "" for p in surveillance.load().values()), default="") or None)
        return _row("surveillance", "Surveillance lists", "8:20 AM and 7:45 PM IST on trading days", at, st.get("last_error"),
                    _problems(st) + why, [{"label": "Run now", "path": "/admin/surveillance/refresh"}], parts=st.get("parts"))
    add("Surveillance lists", surv)

    def auction():
        st = _plain(m.closing_auction_job, "closing-auction")
        from . import closing_auction
        at, why = _ran(st, "read", "recorded", data=lambda: closing_auction.load_live().get("read"))
        return _row("closing-auction", "Closing auction", "Every 30 seconds from 3:14 to 3:40 PM IST; the day is stored after 3:40",
                    at, st.get("last_error"), [f"Stored for {st['recorded']}" if st.get("recorded") else ""] + why)
    add("Closing auction", auction)

    def vix():
        st = _plain(m.vix_job, "vix")
        from . import vix
        at, why = _ran(st, "last_run", "read", data=lambda: max(vix.closes(), default=None))
        return _row("vix", "India VIX history", "After each trading day's close", at, st.get("last_error"), why)
    add("India VIX history", vix)

    def recorder():
        st = _plain(m.recorder, "option-chains")
        if not st.get("enabled"):
            return _row("option-chains", "Option chain recording", "Off", None, None, [], [], note="Off. Set OPTION_SNAPSHOTS to record option chains.")
        # the recordings' own last day when this server hasn't recorded yet (R7O-006: "Not yet" beside Positioning's
        # "StratLab has recorded NIFTY's chain since 28 Sep")
        at, why = _ran(st, "last_at", data=lambda: recorded_through(st.get("targets") or []))
        return _row("option-chains", "Option chain recording", f"Every {st.get('every_minutes')} minutes in market hours", at,
                    st.get("last_error"), [f"{st.get('today', 0)} saved today"] + why)
    add("Option chain recording", recorder)

    def ibkr_daily():
        st = dict(m.connect_job.status or {})
        r = st.get("ibkr") or {}
        return _row("ibkr-daily", "IBKR daily pull", "Every 30 minutes from 7 AM IST until each connected account has its day's read",
                    st.get("ibkr_at"), st.get("last_error"),
                    [f"{r['users']} accounts due, {r['ok']} read, {r['failed']} failed" if r else ""],
                    [{"label": "Run now", "path": "/admin/connect/run?part=ibkr"}], running=m.connect_job.running)
    add("IBKR daily pull", ibkr_daily)

    def inbox_reminder():
        st = dict(m.connect_job.status or {})
        return _row("statement-reminder", "Statement inbox reminder", "Checked every 30 minutes; one reminder when no statement has come in 40 days",
                    st.get("reminders_at"), st.get("last_error"),
                    [f"{st['reminders']} reminders sent in the last check" if st.get("reminders_at") else ""],
                    [{"label": "Run now", "path": "/admin/connect/run?part=reminders"}], running=m.connect_job.running)
    add("Statement inbox reminder", inbox_reminder)

    def library_seed():
        res = m._seed_result or {}
        out = res.get("result") if isinstance(res.get("result"), dict) else {}
        entries = m.library_seed.seeded()
        log = []
        if out:
            log.append(f"Last run: {len(out.get('published') or [])} published or refreshed, {len(out.get('failed') or [])} failed")
        log.append(f"{len(entries)} StratLab strategies in the library")
        last = res.get("finished") or max((str(e.get("published_at") or "") for e in entries), default="") or None
        return _row("library-seed", "Library seed", "Once, a while after start-up when the library has none; the button refreshes them",
                    last, res.get("error"), log, [{"label": "Run now", "path": "/admin/library/seed"}],
                    running=m._seeding.locked(), note="Runs StratLab's own strategies through the backtest and verdict, which takes a few minutes.")
    add("Library seed", library_seed)

    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    def one(name, build):
        try:
            return build()
        except Exception as e:                       # one unreadable job must not hide the others
            return _row(name.lower().replace(" ", "-"), name, "", None, error=f"Couldn't read its status: {str(e)[:120]}")
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="admin-jobs") as pool:
        # each read in a copy of this request's context, so the settings read once above are shared
        futures = [pool.submit(contextvars.copy_context().run, one, name, build) for name, build in builds]
        out = [f.result() for f in futures]
    return out


@router.get("/admin/jobs")
def admin_jobs(_=Depends(admin.admin_profile)):
    """Every background job: when it last ran, its schedule, how the last run went, and the routes that run it now."""
    return {"jobs": rows()}
