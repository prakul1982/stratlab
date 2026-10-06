"""Admin -> Data and jobs: one read of every background job (what it is, when it last ran, when it runs next, how the last
run went) and the routes that run one now. GET /admin/jobs lists them; each row carries `run`, the admin routes that
start it (empty for a job with no manual trigger). Facts only: the schedule text says when the job's own clock runs it."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from . import admin

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


def _row(id: str, name: str, schedule: str, last_run: str | None, error: str | None = None, log: list[str] | None = None,
         run: list[dict] | None = None, running: bool = False, note: str | None = None) -> dict:
    state = "bad" if error else "ok" if last_run else "warn"
    return {"id": id, "name": name, "schedule": schedule, "last_run": last_run, "error": error, "state": state,
            "running": bool(running), "log": [str(x)[:240] for x in (log or []) if x][:8], "run": run or [], "note": note}


def _plain(job) -> dict:
    return dict(getattr(job, "status", None) or {})


def _problems(st: dict) -> list[str]:
    return [str(p) for p in (st.get("problems") or [])]


def rows() -> list[dict]:
    m = _m()
    out: list[dict] = []

    def add(name: str, build):
        try:
            out.append(build())
        except Exception as e:                       # one unreadable job must not hide the others
            out.append(_row(name.lower().replace(" ", "-"), name, "", None, error=f"Couldn't read its status: {str(e)[:120]}"))

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
        st = _plain(m.positioning_job)
        return _row("positioning", "Positioning", "Trading days from 6:40 PM IST until the day's files are in", st.get("last_run"),
                    st.get("last_error"), [str(st.get("last_result") or "")], [{"label": "Run now", "path": "/admin/positioning/run"}],
                    running=m.positioning_runner.running)
    add("Positioning", positioning)

    def etf():
        st = _plain(m.etf_job)
        return _row("etf", "ETF price against NAV", "Every 4 minutes while the market is open; closing prices after 3:45 PM IST",
                    st.get("read") or st.get("last_run"), st.get("last_error"),
                    [f"Closing prices recorded for {st['recorded']}" if st.get("recorded") else "", f"{st.get('filled')} NAVs filled in" if st.get("filled") else ""],
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
        st = _plain(m.results_job)
        return _row("results", "Results calendar", "India 7:15 AM and 6:30 PM IST, US 6:00 AM New York time", st.get("last_run"),
                    st.get("last_error"), _problems(st), [{"label": "Run now", "path": "/admin/results/refresh"}])
    add("Results calendar", results)

    def corp():
        st = _plain(m.corp_job)
        return _row("corp", "Corporate actions", "India 7:20 AM and 6:40 PM IST, US 6:10 AM New York time", st.get("last_run"),
                    st.get("last_error"), _problems(st), [{"label": "Run now", "path": "/admin/corp-actions/refresh"},
                                                           {"label": "Read the whole US universe", "path": "/admin/corp-actions/refresh?universe=true"}],
                    running=bool(getattr(m.corp_job, "universe_running", False)),
                    note="The US list covers the S&P 500 and StratLab's own groups, read from price histories at 6:20 AM New York time (several minutes).")
    add("Corporate actions", corp)

    def events():
        from . import market_events_routes as r
        st = _plain(r.job)
        return _row("events", "Market events", "7:20 AM and 6:40 PM IST", st.get("last_run"), st.get("last_error"), _problems(st),
                    [{"label": "Run now", "path": "/admin/events/refresh"}])
    add("Market events", events)

    def fo():
        from . import fo_changes_routes as r
        st = _plain(r.job)
        return _row("fo", "F&O contract changes", "8:15 AM and 7:50 PM IST on trading days", st.get("last_run"), st.get("last_error"),
                    _problems(st), [{"label": "Run now", "path": "/admin/fo-changes/refresh"}])
    add("F&O contract changes", fo)

    def surv():
        st = _plain(m.surv_job)
        return _row("surveillance", "Surveillance lists", "8:20 AM and 7:45 PM IST on trading days", st.get("last_run"), st.get("last_error"),
                    _problems(st), [{"label": "Run now", "path": "/admin/surveillance/refresh"}])
    add("Surveillance lists", surv)

    def auction():
        st = _plain(m.closing_auction_job)
        return _row("closing-auction", "Closing auction", "Every 30 seconds from 3:14 to 3:40 PM IST; the day is stored after 3:40",
                    st.get("read") or st.get("recorded"), st.get("last_error"), [f"Stored for {st['recorded']}" if st.get("recorded") else ""])
    add("Closing auction", auction)

    def vix():
        st = _plain(m.vix_job)
        return _row("vix", "India VIX history", "After each trading day's close", st.get("last_run") or st.get("read"), st.get("last_error"))
    add("India VIX history", vix)

    def recorder():
        st = dict(m.recorder.status or {})
        if not st.get("enabled"):
            return _row("option-chains", "Option chain recording", "Off", None, None, [], [], note="Off. Set OPTION_SNAPSHOTS to record option chains.")
        return _row("option-chains", "Option chain recording", f"Every {st.get('every_minutes')} minutes in market hours", st.get("last_at"),
                    st.get("last_error"), [f"{st.get('today', 0)} saved today"])
    add("Option chain recording", recorder)
    return out


@router.get("/admin/jobs")
def admin_jobs(_=Depends(admin.admin_profile)):
    """Every background job: when it last ran, its schedule, how the last run went, and the routes that run it now."""
    return {"jobs": rows()}
