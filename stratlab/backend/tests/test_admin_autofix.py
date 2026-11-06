"""Admin checks (owner, 4 Nov: "a whole check on admin pages — a lot of warnings") and the self-healing layer on top of them
("fix it so that in real time everything is fixed, and only if it's not able to, then bug me")."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import admin_jobs, ai_providers, audit, autofix, db, platform_check
from app.data import calendar
from tests import world

T0 = datetime(2026, 11, 4, 16, 0, tzinfo=timezone.utc)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def _mailer():
    sent = []
    return sent, (lambda subject, text: sent.append((subject, text)) or True)


def _check(problem, fix=None, **kw):
    return autofix.Check(id=kw.pop("id", "job:ipo"), name=kw.pop("name", "IPOs"), problem=problem, fix=fix, **kw)


# ---------- the remedy: tried on its backoff, and the history says it was fixed ----------
def test_a_problem_is_retried_on_its_backoff_and_written_up_as_fixed_with_no_mail():
    sent, send = _mailer()
    ran = []
    run = lambda c: ran.append(c.id) or (True, "")             # noqa: E731
    fix = lambda: None                                          # noqa: E731
    st = autofix.sweep([_check("final prospectuses: The SEC is having trouble (500).", fix, fix_text="re-ran the job")], T0, autofix._empty(), send, run)
    assert ran == [] and st["open"]["job:ipo"]["next"]          # first seen: the first try waits its backoff (the source may be busy)
    st = autofix.sweep([_check("final prospectuses: The SEC is having trouble (500).", fix, fix_text="re-ran the job")], T0 + timedelta(minutes=16), st, send, run)
    assert ran == ["job:ipo"] and len(st["open"]["job:ipo"]["tried"]) == 1
    st = autofix.sweep([_check(None, fix, fix_text="re-ran the job")], T0 + timedelta(minutes=30), st, send, run)
    assert "job:ipo" not in st["open"] and sent == []
    fixed = st["history"][0]
    assert fixed["event"] == "fixed" and fixed["name"] == "IPOs" and fixed["text"].startswith("re-ran the job at 4 Nov 9:46 PM IST") and fixed["text"].endswith("fixed")
    assert [h["event"] for h in st["history"]] == ["fixed", "tried"]


def test_tries_used_up_escalate_once_and_a_changed_problem_is_a_new_issue():
    sent, send = _mailer()
    run = lambda c: (False, "The SEC is having trouble (500).")    # noqa: E731
    c = lambda p: _check(p, lambda: None, fix_text="re-ran the job", action="Open Admin → Data and jobs.")    # noqa: E731
    st, t = autofix._empty(), T0
    for _ in range(40):                                         # ten-minute sweeps for 6 h 40 min
        st = autofix.sweep([c("final prospectuses: The SEC is having trouble (500).")], t, st, send, run)
        t += timedelta(minutes=10)
    issue = st["open"]["job:ipo"]
    assert len(issue["tried"]) == autofix.TRIES and len(sent) == 1           # three tries, then one mail, never a second
    subject, text = sent[0]
    assert subject.startswith("[StratLab needs you] IPOs: final prospectuses")
    assert "What was tried: re-ran the job, 3 times" in text and "What to do: Open Admin → Data and jobs." in text
    # the numbers in a problem don't make it a new issue ("running for 2 h" / "3 h")...
    assert autofix.fingerprint("job:x", "Stuck: running for 2 h") == autofix.fingerprint("job:x", "Stuck: running for 3 h")
    # ...a different failure does: tried again from the start, and mailed again once its tries are used up
    for _ in range(40):
        st = autofix.sweep([c("a different failure")], t, st, send, run)
        t += timedelta(minutes=10)
    assert len(sent) == 2 and "a different failure" in sent[1][0]


def test_an_owner_only_check_escalates_at_once_and_a_check_without_a_remedy_waits_for_its_own_next_run():
    sent, send = _mailer()
    key = autofix.Check(id="ai:mistral", name="AI provider Mistral", problem="rejected its key (401)", owner_only=True, action="Replace MISTRAL_API_KEY.")
    st = autofix.sweep([key], T0, autofix._empty(), send)
    assert len(sent) == 1 and "Nothing can fix this automatically." in sent[0][1]
    wait = _check("Late: the last round was at 11:00 IST", id="job:breadth-live", name="Intraday breadth rounds")
    st = autofix.sweep([key, wait], T0 + timedelta(hours=1), st, send)
    assert len(sent) == 1                                       # the job's own next run gets the same window a remedy would
    st = autofix.sweep([key, wait], T0 + timedelta(hours=5), st, send)
    assert len(sent) == 2 and "Intraday breadth rounds" in sent[1][0]


def test_escalation_mails_are_capped_per_day_and_the_rest_wait_for_the_next():
    sent, send = _mailer()
    checks = [autofix.Check(id=f"x{i}", name=f"Check {i}", problem="down", owner_only=True) for i in range(autofix.MAILS_PER_DAY + 2)]
    st = autofix.sweep(checks, T0, autofix._empty(), send)
    assert len(sent) == autofix.MAILS_PER_DAY
    held = [i for i in autofix.status(st)["escalated"] if i["held"]]
    assert len(held) == 2                                       # listed in Needs your attention all the same
    st = autofix.sweep(checks, T0 + timedelta(hours=1), st, send)
    assert len(sent) == autofix.MAILS_PER_DAY                   # still today (IST)
    st = autofix.sweep(checks, T0 + timedelta(days=1), st, send)
    assert len(sent) == autofix.MAILS_PER_DAY + 2               # the next day: the two held ones, once each


def test_no_secret_or_account_id_reaches_a_mail():
    sent, send = _mailer()
    c = autofix.Check(id="ai:nvidia", name="AI provider NVIDIA", problem="404: Function not found for account 1a2b3c4d-1111-2222-3333-444455556666",
                      owner_only=True)
    autofix.sweep([c], T0, autofix._empty(), send)
    assert "1a2b3c4d-1111-2222-3333-444455556666" not in sent[0][0] + sent[0][1]


def test_the_state_is_kept_bounded_and_round_trips_through_the_database(w):
    st = autofix._empty()
    for i in range(80):
        autofix._note(st, T0 + timedelta(minutes=i), {"id": f"x{i}", "name": "X"}, "fixed", "cleared by itself — fixed")
    assert len(st["history"]) == autofix.HISTORY_MAX
    autofix._note(st, T0 + timedelta(days=9), {"id": "y", "name": "Y"}, "fixed", "x")
    assert len(st["history"]) == 1                              # a week's history at most
    autofix.save(st)
    assert autofix.load()["history"][0]["id"] == "y"
    sent, send = _mailer()
    autofix.report(autofix.Check(id="platform", name="Feature check", problem="1 check failing", owner_only=True), send=send, now=T0)
    autofix.report(autofix.Check(id="platform", name="Feature check", problem="1 check failing", owner_only=True), send=send, now=T0 + timedelta(days=1))
    assert len(sent) == 1                                       # the same failure the next day: no second mail
    autofix.report(autofix.Check(id="platform", name="Feature check", problem=None), send=send, now=T0 + timedelta(days=2))
    assert autofix.load()["history"][0]["event"] == "fixed" and "platform" not in autofix.load()["open"]


# ---------- Admin's job rows say what the self-healing is doing ----------
def test_a_job_being_fixed_is_a_check_that_says_so_and_one_given_up_on_is_a_problem_that_says_you_were_emailed():
    st = autofix._empty()
    st = autofix.sweep([_check("The SEC is having trouble (500).", lambda: None)], T0, st, lambda s, t: True, lambda c: (True, ""))
    row = {"id": "ipo", "name": "IPOs", "state": "bad", "error": "The SEC is having trouble (500)."}
    got = autofix.annotate([row, {"id": "fo", "state": "ok", "error": None}], st)
    assert got[0]["state"] == "warn" and "Being fixed automatically: next try 4 Nov 9:45 PM IST." in got[0]["error"]
    assert got[1]["state"] == "ok"
    st["open"]["job:ipo"].update(escalated=T0.isoformat(), mailed=T0.isoformat(), tried=[{"at": T0.isoformat()}] * 3)
    got = autofix.annotate([row], st)[0]
    assert got["state"] == "bad" and got["error"].endswith("Retried automatically 3 times without luck; you were emailed.")
    # a job with no remedy of its own: its next scheduled run is the retry, said as such
    st = autofix.sweep([_check("Late", id="job:breadth-live")], T0, autofix._empty(), lambda s, t: True)
    got = autofix.annotate([{"id": "breadth-live", "state": "warn", "error": "Late."}], st)[0]
    assert "read again at its next run by itself" in got["error"]


def test_every_failing_job_gets_a_check_and_its_remedy_is_its_own_run_now(monkeypatch):
    rows = [{"id": "breadth", "name": "Market breadth", "state": "bad", "error": "US: 3 stocks failed", "running": False,
             "run": [{"label": "Run India", "path": "/admin/breadth/run?region=IN&full=true"}, {"label": "Run US", "path": "/admin/breadth/run?region=US&full=true"}]},
            {"id": "ipo", "name": "IPOs", "state": "warn", "error": "Offer documents: the catch-up hasn't run today", "running": False,
             "run": [{"label": "Run now", "path": "/admin/ipos/refresh"}]},
            {"id": "vix", "name": "India VIX history", "state": "ok", "error": None, "run": []},
            {"id": "newsletters", "name": "Newsletters", "state": "bad", "error": "x", "run": [{"label": "Run", "path": "/admin/newsletters/run"}]}]
    monkeypatch.setattr(admin_jobs, "rows", lambda: rows)
    checks = {c.id: c for c in admin_jobs.job_checks()}
    assert "job:newsletters" not in checks                      # a job that mails users is never re-run by the sweep
    assert checks["job:breadth"].problem == "US: 3 stocks failed" and checks["job:ipo"].problem and checks["job:vix"].problem is None
    assert admin_jobs.remedy_paths(rows[0]) == ["/admin/breadth/run?region=US&full=true"]     # the market the problem names
    assert admin_jobs.remedy_paths({**rows[0], "error": "stalled"}) == ["/admin/breadth/run?region=IN&full=true"]
    assert checks["job:vix"].fix is None


def test_a_remedy_calls_the_route_as_the_button_would_without_the_whole_history_flags(monkeypatch):
    from fastapi import Depends, FastAPI
    app, got = FastAPI(), {}

    def gate():
        raise AssertionError("the admin gate is the button's, not the sweep's")

    @app.post("/admin/breadth/run")
    def run(region: str = "IN", full: bool = False, _=Depends(gate)):
        got.update(region=region, full=full)
        return {"started": True}
    monkeypatch.setattr(autofix, "_app", app)
    assert autofix.call_route("/admin/breadth/run?region=US&full=true") == {"started": True}
    assert got == {"region": "US", "full": False}
    with pytest.raises(LookupError):
        autofix.call_route("/admin/nothing")


# ---------- the daily feature check: what still fails after its retry is mailed once, not every day ----------
def test_the_daily_feature_check_mails_the_same_failure_once(w, monkeypatch):
    from app import main
    monkeypatch.setattr(main, "platform_checks", lambda: [
        ("Prices: FX", "Prices", lambda: platform_check._result("Prices: FX", "Prices", "fail", "1 candle of EUR/USD on 2 Nov is off"))])
    told = []
    monkeypatch.setattr(main, "tell_admins", lambda subject, text: told.append((subject, text)) or 1)
    main.daily_platform_check(retry_after=0.01)
    main.daily_platform_check(retry_after=0.01)
    assert len(told) == 1 and told[0][0].startswith("[StratLab needs you] Feature check: 1 check failing")
    assert main.platform_checks_failing()[0].problem.startswith("1 check failing after a retry: Prices: FX")


# ---------- AI: a rejected key goes to the owner; a passing fault is nobody's problem ----------
def test_ai_checks_escalate_a_rejected_key_and_leave_a_passing_fault_alone(monkeypatch):
    from types import SimpleNamespace as NS
    rows = [{"name": "mistral", "configured": True, "answering": False, "state": "fail", "state_text": "Failing: 401", "result": "failed"},
            {"name": "gemini", "configured": True, "answering": True, "state": "ok", "state_text": "Working.", "result": "working"},
            {"name": "groq", "configured": True, "answering": False, "state": "fail", "state_text": "Failing: server error 503", "result": "failed"},
            {"name": "cloudflare", "configured": True, "answering": True, "state": "idle",
             "state_text": "Not tried yet, and the provider listed no models when asked, which often means the key is wrong.", "result": "untested"}]
    monkeypatch.setattr(ai_providers, "health", lambda: rows)
    kinds = {"mistral": "auth", "groq": "transient"}
    monkeypatch.setattr(ai_providers, "status", lambda n: NS(last_error="401 Unauthorized" if n in kinds else None, last_error_at=2.0, last_ok=1.0,
                                                            last_error_kind=kinds.get(n)))
    checks = {c.id: c for c in ai_providers.ai_checks()}
    assert checks["ai:mistral"].owner_only and checks["ai:mistral"].fix is None and "MISTRAL" in checks["ai:mistral"].action
    assert checks["ai:groq"].problem is None and checks["ai:gemini"].problem is None
    assert checks["ai:cloudflare"].problem == "lists no models for its key" and checks["ai:cloudflare"].fix
    assert checks["ai:all"].problem is None                    # one answers
    for r in rows:
        r["answering"] = False
    assert ai_providers.ai_checks()[-1].problem.startswith("no provider is answering")


# ---------- the whole sweep over the real sources, in the test world ----------
def test_the_sweep_lists_every_source_and_runs_end_to_end(w, monkeypatch):
    from app import main  # noqa: F401  (registers the holidays and feature-check sources)
    sent, send = _mailer()
    monkeypatch.setattr(autofix, "_send", send)
    ids = {c.id for c in autofix.gather()}
    assert {"holidays", "platform", "ai:all"} <= ids and any(i.startswith("job:") for i in ids)
    st = autofix.tick(T0)
    assert set(st) == {"open", "history", "mail"}
    ov = w["client"].get("/admin/overview", headers=world.headers("admin-token")).json()
    assert set(ov["server"]["autofix"]) == {"trying", "escalated", "history"}
    jobs = w["client"].get("/admin/jobs", headers=world.headers("admin-token")).json()["jobs"]
    assert jobs and all("state" in j for j in jobs)


# ---------- the holidays light and its self-healing follow the season rule ----------

def test_the_holidays_light_and_the_self_healing_follow_the_season_rule(w, monkeypatch):
    from app import main
    monkeypatch.setattr(calendar, "covered_until", lambda m: date(2026, 12, 31) if m in calendar.LISTED else date(2027, 11, 4))

    class Day(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 4, 22, 0, tzinfo=main.IST)
    monkeypatch.setattr(main, "datetime", Day)
    cal = main.calendar_status()
    assert cal["state"] == "ok" and cal["note"] == calendar.AWAITED
    assert main.holiday_checks()[0].problem is None

    class Late(Day):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 12, 22, 9, 0, tzinfo=main.IST)
    monkeypatch.setattr(main, "datetime", Late)
    assert main.calendar_status()["state"] == "warn"
    c = main.holiday_checks()[0]
    assert "31 Dec" in c.problem or "2026-12-31" in c.problem
    assert c.fix and c.backoff[0] >= 6 * 3600 and "paste them" in c.action



# ---------- every remedy's route exists in the real app (LIVE4-016: "No route /admin/ipos/refresh", 8 tries, 2 mails) ----------
def _remedy_paths_in_source() -> set[str]:
    import re
    from pathlib import Path
    out = set()
    for f in (Path(__file__).resolve().parents[1] / "app").rglob("*.py"):
        out |= set(re.findall(r'"path":\s*f?"(/admin/[^"?{]+)', f.read_text()))
    return out


def test_every_remedy_route_in_the_registry_is_a_real_post_route_of_the_app(w):
    from app import main, route_list
    rows = admin_jobs.rows()
    paths = {p for r in rows for p in [x.get("path") for x in r.get("run") or []] if p}
    assert "/admin/ipos/refresh" in paths and len(paths) >= 10
    paths |= _remedy_paths_in_source()
    from urllib.parse import urlsplit
    missing = sorted(p for p in paths if route_list.find(main.app, urlsplit(p).path, "POST") is None)
    assert not missing, f"remedies that call a route the app doesn't have: {missing}"


def test_a_remedy_finds_a_route_that_lives_on_an_included_router(monkeypatch):
    from fastapi import APIRouter, Depends, FastAPI
    app, router, got = FastAPI(), APIRouter(), {}

    @router.post("/admin/ipos/refresh")
    def refresh(_=Depends(lambda: None)):
        got["ran"] = True
        return {"started": True}
    app.include_router(router)
    monkeypatch.setattr(autofix, "_app", app)
    assert autofix.call_route("/admin/ipos/refresh") == {"started": True} and got == {"ran": True}


def test_the_live_app_resolves_the_ipo_remedy_to_the_ipo_refresh_endpoint():
    from app import ipo, main, route_list
    r = route_list.find(main.app, "/admin/ipos/refresh", "POST")
    assert r is not None and r.endpoint is ipo.ipos_refresh
