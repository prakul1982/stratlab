"""Admin -> Data and jobs: one read of every background job (what it is, when it last ran, when it runs next, how the last
run went) and the routes that run one now. GET /admin/jobs lists them; each row carries `run`, the admin routes that
start it (empty for a job with no manual trigger). Facts only: the schedule text says when the job's own clock runs it."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from . import admin, job_status, leader
from .connect.redact import redact_ids

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


HOLIDAYS_ENOUGH = 30          # days of holidays on file that keep a failed read of the exchange's list a Check (R13-012)


# What a source left unread means, and whose fault it looks like (DJ-021: "Not read: … answered 404" said neither what was
# missing nor whether anything had to be done)
_SITE_FAULT = re.compile(r"answered (4\d\d|5\d\d)|couldn't (be )?reach|timed out|refused|redirect", re.I)


def missing_words(problem: str, effects: dict[str, str] | None, next_run: str | None) -> str:
    """" Index rebalance dates may be missing. The provider's site isn't answering, not StratLab; tried again at 6:40 PM
    IST.": what the unread source leaves out, and that nothing needs doing when the site is at fault."""
    label = problem.split(":", 1)[0].strip()
    effect = (effects or {}).get(label)
    if not effect:
        return ""
    fault = (" Its site isn't answering properly, so the fault looks like the site's, not StratLab's: nothing to do"
             if _SITE_FAULT.search(problem) else " Its page may have changed: the reader needs a look")
    return f" {effect}.{fault}{f'; it is tried again at {next_run}' if next_run else ''}."


def _row(id: str, name: str, schedule: str, last_run: str | None, error: str | None = None, log: list[str] | None = None,
         run: list[dict] | None = None, running: bool = False, note: str | None = None, parts: int | None = None,
         effects: dict[str, str] | None = None, next_run: str | None = None) -> dict:
    """One job. `parts`: how many sources the last run tried, for a job that reads several (each failed one is a line
    of `log`); when some were read and some weren't, the run is partial: Check, not Problem. `effects` says, per source,
    what is missing while it is unread (DJ-021), `next_run` when it is tried again."""
    state = "bad" if error else "ok" if last_run else "warn"
    problems = [str(x) for x in (log or []) if x] if error else []
    failed = len(problems)
    if error and parts and 0 < failed < parts:
        state = "warn"
        error = (f"Partial: {parts - failed} of {parts} sources read. Not read: {plain_error(problems[0])}"
                 + missing_words(problems[0], effects, next_run) + (f" And {failed - 1} more (see the log)." if failed > 1 else ""))
    else:
        error = plain_error(error)
    # a provider's own error text can carry an account identifier: Admin shows it hidden (R29B-022)
    return {"id": id, "name": name, "schedule": schedule, "last_run": last_run, "error": redact_ids(error), "state": state,
            "running": bool(running), "log": [redact_ids(str(x)[:240]) for x in (log or []) if x][:8], "run": run or [], "note": note}


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


def news_run_at(at: str) -> str:
    """When a newsletter run went, in UTC as the job records it: "14 Oct 10:47 UTC"."""
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return str(at)
    return f"{t.day} {t:%b %H:%M} UTC"


def plural(n: int, one: str) -> str:
    return f"{n} {one}{'' if n == 1 else 's'}"


def _problems(st: dict) -> list[str]:
    return [str(p) for p in (st.get("problems") or [])]


def clock(hhmm: str) -> str:
    """"18:40" as "6:40 PM"."""
    h, m = (int(x) for x in hhmm.split(":"))
    return f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}"


def next_slot(runs, now: datetime | None = None) -> str | None:
    """The next of a job's daily runs ((name, zone, "HH:MM"), ...), as "6:40 PM IST" (with the day when it is tomorrow)."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    best = None
    for _, tz, at in runs:
        local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(tz))
        h, m = (int(x) for x in at.split(":"))
        t = local.replace(hour=h, minute=m, second=0, microsecond=0)
        if t <= local:
            t += timedelta(days=1)
        if best is None or t < best[0]:
            best = (t, tz, local)
    if not best:
        return None
    t, tz, local = best
    zone = "IST" if tz == "Asia/Kolkata" else "New York time" if tz == "America/New_York" else tz
    return f"{clock(t.strftime('%H:%M'))} {zone}" + ("" if t.date() == local.date() else " tomorrow")


def results_schedule(R) -> str:
    """The results job's whole clock (DJ-022: a run at 5 PM New York time beside "US 6:00 AM" read as off-schedule): the
    calendar's refreshes, the morning notes, and the hourly look for new filings."""
    return (f"Calendar: India {' and '.join(clock(t) for t in R.REFRESH_AT['IN'])} IST, US {' and '.join(clock(t) for t in R.REFRESH_AT['US'])} "
            f"New York time. Results-day notes {clock(R.MORNING_AT['IN'])} IST and {clock(R.MORNING_AT['US'])} New York time. "
            f"New filings looked for every hour from {clock(R.CHECK_FROM['IN'])} IST and {clock(R.CHECK_FROM['US'])} New York time until midnight")


def corp_schedule(C) -> str:
    """The corporate-actions job's whole clock (DJ-022): the list, the price histories, and the evening-before notes."""
    return (f"List: India {' and '.join(clock(t) for t in C.REFRESH_AT['IN'])} IST, US {' and '.join(clock(t) for t in C.REFRESH_AT['US'])} "
            f"New York time. Price histories {clock(C.HISTORY_AT['IN'])} IST and {clock(C.HISTORY_AT['US'])} New York time. "
            f"Evening-before notes {clock(C.EVE_AT['IN'])} IST and {clock(C.EVE_AT['US'])} New York time")


KEPT = ("newsletters", "positioning", "etf", "results", "corp", "events", "ipo", "fo", "surveillance", "closing-auction", "vix", "option-chains", "connect")


def breadth_live_row(st: dict, job: dict | None = None, now: datetime | None = None) -> dict:
    """The quarter-hour breadth rounds while India's market is open (R24-002: Admin had no row for them, and two rounds
    were missed unseen): the last round's time, how many stocks it read, and whether the latest is late or failed."""
    from . import breadth_live as BL
    now = now or datetime.now(timezone.utc)
    s = (st or {}).get("IN") or {}
    log = []
    if s.get("time"):
        log.append(f"Last round {s.get('day')} {s['time']} IST: {s.get('quoted', 0):,} of {s.get('stocks', 0):,} stocks read"
                   + (f" in {s['seconds']:g} s" if isinstance(s.get("seconds"), (int, float)) else ""))
    error = None
    if s.get("failed_at") and (not s.get("at") or s["failed_at"] > s["at"]):
        error = s.get("error") or "The last round failed."
    row = _row("breadth-live", "Intraday breadth rounds", "Every quarter hour (09:15 to 15:30 IST) while the Indian market is open",
               s.get("at"), error, log + ([f"Scheduler: {(job or {})['last_error']}"] if (job or {}).get("last_error") else []),
               note="Each round reads the live prices of every stock in the India breadth groups, a few requests in all.")
    if not error and BL.is_open("IN", now):
        day, slot = now.astimezone(BL.IST).date().isoformat(), BL.slot_of(now)
        if s.get("day") == day and s.get("time"):
            last = datetime.fromisoformat(f"{day}T{s['time']}:00").replace(tzinfo=BL.IST)
            age = int((now - last).total_seconds() // 60)
            if age * 60 > BL.LATE_AFTER:
                row["state"], row["error"] = "warn", f"Late: the last round was at {s['time']} IST, {age} minutes ago (the {slot} round is due)."
    return row


def _connect_status(m) -> dict:
    """The connect jobs' status: this server's once it has run, else the one kept before the restart."""
    from . import job_status
    return job_status.kept("connect", dict(m.connect_job.status or {}))


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
        return _row("breadth", "Market breadth", f"India about 6:30 PM IST, US about {m.breadth.due_label('US').replace(' ET', '')} New York time, on trading days",
                    max((v["ran_at"] for v in ok.values()), default=None), err, log,
                    [{"label": "Run India", "path": "/admin/breadth/run?region=IN&full=true"}, {"label": "Run US", "path": "/admin/breadth/run?region=US&full=true"}],
                    running=m.breadth_runner.running,
                    note="The first run reads two years of prices: a few minutes for the US, 20 to 25 minutes for India (it needs the day's broker login).")
    add("Market breadth", breadth)
    add("Intraday breadth rounds", lambda: breadth_live_row(m.breadth_live.status(), m.breadth_live_job.status))

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

    def newsletters():
        # who got each brief, per region, and who didn't and why (R7M-005: the 8 Oct India brief never reached its reader and
        # nothing said so)
        from .newsletter import job as news
        st = _plain(m.newsletter_job, "newsletters")
        label = {"IN": "India", "US": "US", "IN-weekly": "India, weekly", "US-weekly": "US, weekly", "stocks": "My stocks", "stocks-weekly": "My stocks, weekly"}
        log, failed = [], 0
        regions = st.get("regions") or {}
        for key in label:
            rep = regions.get(key)
            if not rep:
                continue
            why = rep.get("skipped") or {}
            failed += sum(n for w, n in why.items() if w in (news.WHY["error"], news.WHY["profile"]))
            readers = rep.get("readers")
            line = f"{label[key]}, {rep.get('day')}: sent to {rep.get('sent', 0)}" + (f" of {plural(readers, 'reader')}" if readers is not None else "")
            if rep.get("other_edition"):
                line += f"; {rep['other_edition']} chose the other edition"
            # the skipped count and why, said even when it is none, so a reader left out is never invisible (R8B-007)
            line += f"; skipped {sum(why.values())}" + (": " + ", ".join(f"{n} {w}" for w, n in why.items()) if why else "")
            if rep.get("error"):
                line += f"; {rep['error']}"
            if rep.get("at"):
                line += f" (run {news_run_at(rep['at'])})"    # each market's own last run (R23-002)
            log.append(line)
        # a market whose daily brief was due today and has no run recorded says so, rather than nothing (R23-002)
        for region in news.SEND_AT:
            due = news.due_today(region)
            rep = regions.get(region) or {}
            if due and rep.get("day") != due:
                log.append(f"{label[region]}, {due}: no run recorded yet (due at {news.SEND_AT[region][1]} {'IST' if region == 'IN' else 'New York time'})")
        at, extra = _ran(st, "last_run", data=lambda: max((i.get("at") or "" for r in news.SEND_AT for i in news.recent("market", r, 1)), default="") or None)
        error = st.get("last_error") or (f"{plural(failed, 'reader')} couldn't be sent an issue; it is tried again during the day" if failed else None)
        return _row("newsletters", "Newsletters", f"{news.SEND_WORDS} on trading days; the weekly digest on Saturday 8 AM IST",
                    at, error, (_problems(st) if st.get("last_error") else []) + log + extra,
                    note="Readers whose address isn't confirmed yet, or whose email failed, are tried again through the day they were due.")
    add("Newsletters", newsletters)

    def positioning():
        st = _plain(m.positioning_job, "positioning")
        from . import positioning as P
        at, why = _ran(st, "last_run", data=lambda: P.state().get("last_run"))
        line, waiting = P.run_sentence(st.get("last_result"))
        row = _row("positioning", "Positioning", "Trading days from 6:40 PM IST until the day's files are in", at,
                   st.get("last_error"), [line] + why, [{"label": "Run now", "path": "/admin/positioning/run"}],
                   running=m.positioning_runner.running)
        if waiting and row["state"] == "ok":          # a file isn't out yet: Check until it arrives
            row["state"] = "warn"
        return row
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
        cal = m.calendar_status()
        a = cal.get("auto") or {}
        row = _row("holidays", "Exchange holidays", "Every day", a.get("at"), a.get("error"),
                   [f"{a['count']} holidays in the last read" if a.get("at") else ""], [{"label": "Read now", "path": "/admin/holidays/refresh"}])
        left = cal.get("days_left")
        if row["state"] == "bad" and isinstance(left, int) and left >= HOLIDAYS_ENOUGH:
            # holidays are published months ahead: the live list being unreachable (the exchange turns this server away)
            # is a Check while the days on file still cover the weeks ahead, not a Problem (R13-012), in the words the
            # Services light uses (R12-010)
            row = {**row, "state": "warn", "note": f"Holidays on file for {left} more days · live feed down"}
        return row
    add("Exchange holidays", holidays)

    def results():
        st = _plain(m.results_job, "results")
        from . import results as R
        return _row("results", "Results calendar", results_schedule(R), st.get("last_run"),
                    st.get("last_error"), _problems(st), [{"label": "Run now", "path": "/admin/results/refresh"}])
    add("Results calendar", results)

    def corp():
        st = _plain(m.corp_job, "corp")
        from . import corp_actions
        at, why = _ran(st, "last_run", data=lambda: max(filter(None, (corp_actions.load(r).get("at") for r in corp_actions.REGIONS)), default=None))
        return _row("corp", "Corporate actions", corp_schedule(corp_actions), at,
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
                    [{"label": "Run now", "path": "/admin/events/refresh"}], parts=st.get("parts"),
                    effects=market_events.MISSING, next_run=next_slot(r.job.RUNS))
    add("Market events", events)

    def ipos():
        from . import ipo
        st = _plain(ipo.job, "ipo")
        at, why = _ran(st, "last_run", data=lambda: max(filter(None, ((ipo.state().get(r) or {}).get("read") for r in ("IN", "US"))), default=None))
        return _row("ipo", "IPOs", "India 7:40 AM and 8:10 PM IST, US 8:30 AM and 9:30 PM IST; bids every 15 minutes from 9:55 AM to 5:30 PM IST while an issue is open; "
                    "alerts 8:00 AM (India) and 7:00 PM (US dates) IST", at, st.get("last_error"), _problems(st) + why,
                    [{"label": "Run now", "path": "/admin/ipos/refresh"}], note="Offer documents are read and summarised a few at a time between the reads.")
    add("IPOs", ipos)

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

    def page_prices():
        # the public company pages' prices after each close (R81-005: every US page sat on 20 Oct's close and Admin
        # had no row for this job, so nothing said so)
        # kept across a restart like the other jobs' (R94-001: "Not run yet" on Check after every weekend deploy, its
        # next pass not due until Monday's close)
        st = job_status.kept("page-prices", dict(getattr(m, "price_refresh_status", None) or {}))
        names = {"IN": "India", "US": "US"}
        log, errors = [], []
        for r, name in names.items():
            x = st.get(r)
            if not isinstance(x, dict):
                continue
            if x.get("error"):
                errors.append(f"{name}: {x['error']}")
                continue
            if x.get("source_down"):
                # the source turned the pass away (India's broker before the morning login): the pages wait for it,
                # not a problem (R84-005: red "no page's price could be read (1 tried)" at 06:30 IST)
                log.append(f"{name}: waiting for the price source (the broker's daily login, for India); "
                           f"{x.get('left', 0)} pages are read once it's back")
                continue
            err = x.get("errors", x.get("failed", 0))       # reads that raised; the rest of `failed` had no newer close yet
            late = max(0, (x.get("failed") or 0) - err)
            log.append(f"{name}: {x.get('refreshed', 0)} updated, {x.get('left', 0)} waiting, "
                       f"{late} without a newer close yet (a small company that didn't trade, or not out yet), {err} not read")
            # which ones, and where their candles stop: a quiet tail (a small company's last trade days back) told apart
            # from the source without the close (R90-002: "0 updated, 974 waiting, 300 without a newer close" for 17 hours)
            if late and x.get("behind"):
                log.append(f"{name}, for example: {', '.join(x['behind'])}")
            # a Problem only when reads fail and none worked: the long tail of companies that didn't trade at the last
            # close is normal, not a problem (R82: "India: no page's price could be read" over 299 such pages)
            if err and not x.get("refreshed"):
                errors.append(f"{name}: no page's price could be read in the last pass ({err} tried)")

        return _row("page-prices", "Company pages' prices", "After each market's close, every 15 minutes until every stored page has it",
                    st.get("last_run"), "; ".join(errors) or None, errors + log)
    add("Company pages' prices", page_prices)

    def ibkr_daily():
        st = _connect_status(m)
        r = st.get("ibkr") or {}
        row = _row("ibkr-daily", "IBKR daily pull", "Every 30 minutes from 7 AM IST until each connected account has its day's read",
                   st.get("ibkr_at"), st.get("ibkr_error") or st.get("last_error"),
                   [f"{r['users']} accounts due, {r['ok']} read, {r['failed']} failed" if r else ""],
                   [{"label": "Run now", "path": "/admin/connect/run?part=ibkr"}], running=m.connect_job.running)
        if row["state"] == "ok" and r.get("failed"):      # a run that read some accounts and not others is a Check, not "OK"
            row = {**row, "state": "warn", "note": f"{plural(int(r['failed']), 'account')} could not be read in the last run"}
        return row
    add("IBKR daily pull", ibkr_daily)

    def inbox_reminder():
        st = _connect_status(m)
        return _row("statement-reminder", "Statement inbox reminder", "Checked every 30 minutes; one reminder when no statement has come in 40 days",
                    st.get("reminders_at"), st.get("reminders_error") or st.get("last_error"),
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
    # which container runs the jobs (a deploy overlaps two for a minute) and until when its lease holds
    return {"jobs": rows(), "leader": leader.current.status()}
