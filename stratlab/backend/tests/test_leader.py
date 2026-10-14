"""The leader lease: only one of two overlapping containers runs the jobs and live sessions (app/leader.py)."""
import threading
import time
import types

import pytest
from fastapi.testclient import TestClient

from app import db, leader, live, main, market_store  # noqa: F401  (main first: it loads the newsletter job without a cycle)
from app.newsletter import job as news


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class MemLease:
    """The lease row with the same rules as leader.CLAIM: a claim wins if the row is free, ours, or past its end."""

    def __init__(self, clock):
        self.clock, self.rows, self.down = clock, {}, False

    def claim(self, name, owner, secs):
        if self.down:
            raise ConnectionError("database unreachable")
        row = self.rows.get(name)
        if row is None or row["owner"] == owner or row["until"] <= self.clock():
            self.rows[name] = {"owner": owner, "until": self.clock() + secs}
            return True
        return False

    def release(self, name, owner):
        row = self.rows.get(name)
        if row and row["owner"] == owner:
            row["until"] = self.clock()

    def read(self, name):
        return self.rows.get(name)


def pair():
    clock = Clock()
    mem = MemLease(clock)
    return clock, mem, leader.Leader(lambda: mem, clock), leader.Leader(lambda: mem, clock)


def test_only_one_of_two_containers_leads_until_the_first_releases():
    clock, mem, a, b = pair()
    assert a.renew() and a.leading()
    assert not b.renew() and not b.leading()
    a.release()
    assert not a.leading() and b.renew() and b.leading()
    assert not a.renew()                     # the old one can't take it back


def test_renewal_keeps_the_lease_and_expiry_hands_it_over():
    clock, mem, a, b = pair()
    a.renew()
    for _ in range(10):                      # renewed every 15 s: held well past one lease
        clock.t += 15
        assert a.renew() and not b.renew()
    clock.t += 61                            # a stops renewing (frozen, killed): b takes over after the lease
    assert b.renew() and not a.renew() and not a.leading()


def test_a_database_error_keeps_the_lease_only_until_it_would_have_ended():
    clock, mem, a, _ = pair()
    a.renew()
    mem.down = True
    clock.t += 45
    assert a.renew() and a.leading()         # still inside the lease we hold
    clock.t += 16
    assert not a.renew() and not a.leading()  # past it by our own clock: step down
    mem.down = False
    assert a.renew()                         # nobody took it meanwhile: ours again


def test_kill_switch_and_no_database_make_every_container_lead(monkeypatch):
    monkeypatch.setattr(market_store, "store", lambda: None)
    a, b = leader.Leader(), leader.Leader()
    assert a.leading() and b.leading() and a.renew() and b.renew()
    monkeypatch.setattr(market_store, "store", lambda: object())
    monkeypatch.setenv("LEADER_LEASE", "off")
    assert leader._backend() is None
    assert a.leading() and b.leading()
    monkeypatch.delenv("LEADER_LEASE")
    assert isinstance(leader._backend(), leader.PgLease)


def test_the_run_loop_waits_then_leads_and_steps_down_on_a_lost_lease():
    mem = MemLease(time.monotonic)
    mem.rows[leader.NAME] = {"owner": "old-container", "until": time.monotonic() + 60}
    me = leader.Leader(lambda: mem, renew=0.01, retry=0.01)
    events = []
    t = threading.Thread(target=me.run, args=(lambda: events.append("gain"), lambda: events.append("lose")), daemon=True)
    t.start()
    time.sleep(0.05)
    assert events == []                      # the old container still holds it
    mem.release(leader.NAME, "old-container")
    _wait(lambda: events == ["gain"])
    mem.rows[leader.NAME] = {"owner": "intruder", "until": time.monotonic() + 60}
    _wait(lambda: events == ["gain", "lose"])
    me._stop.set()
    t.join(1)


def _wait(cond, limit=1.0):
    end = time.time() + limit
    while time.time() < end:
        if cond():
            return
        time.sleep(0.005)
    assert cond()


# ---------- the lifespan ----------
def test_lifespan_starts_jobs_only_once_leading_and_releases_at_shutdown(monkeypatch):
    from app import main
    mem = MemLease(time.monotonic)
    mem.rows[leader.NAME] = {"owner": "old-container", "until": time.monotonic() + 60}
    me = leader.Leader(lambda: mem, renew=0.01, retry=0.01)
    monkeypatch.setattr(leader, "current", me)
    calls = []
    monkeypatch.setattr(main, "start_jobs", lambda: calls.append("jobs"))
    monkeypatch.setattr(main, "_jobs_started", False)
    monkeypatch.setattr(db, "forget_mirror", lambda: calls.append("mirror"))
    monkeypatch.setattr(main.manager, "persist", lambda *a, **k: calls.append("persist"))
    monkeypatch.setattr(main.manager, "resume", lambda *a, **k: calls.append("resume"))
    monkeypatch.setattr(main, "warm_caches", lambda: None)
    monkeypatch.setattr(main.trading_calendar, "warm", lambda: None)
    monkeypatch.setattr(main.kite, "load_saved_token", lambda: None)
    with TestClient(main.app) as c:
        assert c.get("/health").json()["ok"]       # requests are served while waiting
        time.sleep(0.05)
        assert calls == []                         # no job, no session while another container leads
        mem.release(leader.NAME, "old-container")
        _wait(lambda: calls == ["mirror", "jobs"])
    assert calls == ["mirror", "jobs", "persist"]  # saved, then let go
    assert mem.rows[leader.NAME]["owner"] == me.me and mem.rows[leader.NAME]["until"] <= time.monotonic()


def test_a_follower_saves_nothing_at_shutdown(monkeypatch):
    from app import main
    mem = MemLease(time.monotonic)
    mem.rows[leader.NAME] = {"owner": "old-container", "until": time.monotonic() + 60}
    monkeypatch.setattr(leader, "current", leader.Leader(lambda: mem, renew=0.01, retry=0.01))
    calls = []
    monkeypatch.setattr(main, "start_jobs", lambda: calls.append("jobs"))
    monkeypatch.setattr(main.manager, "persist", lambda *a, **k: calls.append("persist"))
    monkeypatch.setattr(main, "warm_caches", lambda: None)
    monkeypatch.setattr(main.trading_calendar, "warm", lambda: None)
    monkeypatch.setattr(main.kite, "load_saved_token", lambda: None)
    with TestClient(main.app):
        time.sleep(0.03)
    assert calls == [] and mem.rows[leader.NAME]["owner"] == "old-container"


# ---------- live sessions ----------
class FakeSession:
    def __init__(self, row):
        self.id, self.user_id, self.inst = row["id"], row["user_id"], row.get("instrument") or {}
        self.dirty, self.polled, self.started_at = False, True, ""
        self.lock = threading.Lock()
        self.attached = False

    def attach(self, hub):
        self.attached = True

    def detach(self, hub):
        self.attached = False

    def state(self):
        return {"cash": 1}

    def final_state(self):
        return {"cash": 1, "final": True}

    def snapshot(self):
        return {"id": self.id, "status": "running"}


@pytest.fixture
def mgr(monkeypatch):
    m = live.LiveManager(types.SimpleNamespace(ready=lambda: True), None)
    monkeypatch.setattr(m, "_build", FakeSession)
    rows, writes = {}, []
    monkeypatch.setattr(db, "running_sessions", lambda: [r for r in rows.values() if r["status"] == "running"])
    monkeypatch.setattr(db, "update_session", lambda sid, **f: writes.append((sid, f)))
    monkeypatch.setattr(leader, "current", leader.Leader(lambda: None))      # leading
    return m, rows, writes


def test_reconcile_attaches_sessions_started_elsewhere_and_detaches_stopped_ones(mgr):
    m, rows, writes = mgr
    rows["a"] = {"id": "a", "user_id": "u", "status": "running", "instrument": {"market": "CRYPTO"}}
    m.reconcile()
    assert set(m.sessions) == {"a"} and m.sessions["a"].attached
    s = m.sessions["a"]
    rows["a"]["status"] = "stopped"            # stopped through the other container
    m.reconcile()
    assert m.sessions == {} and not s.attached
    assert writes == [("a", {"state": {"cash": 1, "final": True}})]      # its final state kept, its status left alone


def test_reconcile_never_reattaches_a_session_just_stopped_here(mgr):
    m, rows, writes = mgr
    rows["a"] = {"id": "a", "user_id": "u", "status": "running", "instrument": {"market": "CRYPTO"}}
    m.reconcile()
    m.stop("a", "Stopped by you.")             # the row still reads running in a reconcile that started earlier
    m.resume([dict(rows["a"])])
    assert m.sessions == {}


def test_a_follower_neither_resumes_nor_saves_and_starts_sessions_for_the_leader(mgr, monkeypatch):
    m, rows, writes = mgr
    rows["a"] = {"id": "a", "user_id": "u", "status": "running", "instrument": {"market": "CRYPTO"}}
    clock = Clock()
    mem = MemLease(clock)
    mem.rows[leader.NAME] = {"owner": "other", "until": clock() + 60}
    monkeypatch.setattr(leader, "current", leader.Leader(lambda: mem, clock))
    m.resume()
    assert m.sessions == {}
    monkeypatch.setattr(db, "user_sessions", lambda uid: [r for r in rows.values() if r["user_id"] == uid])
    monkeypatch.setattr(db, "create_session", lambda r: rows.setdefault("b", {**r, "id": "b"}))
    s = m.start({"id": "u"}, "pro", types.SimpleNamespace(name="x", model_dump=lambda: {}), {"market": "CRYPTO"})
    assert s.snapshot()["pending"] is True and m.sessions == {} and rows["b"]["status"] == "running"
    m.persist([s], only_dirty=False)
    assert writes == []


def test_losing_the_lease_drops_sessions_without_saving(mgr):
    m, rows, writes = mgr
    rows["a"] = {"id": "a", "user_id": "u", "status": "running", "instrument": {"market": "CRYPTO"}}
    m.reconcile()
    s = m.sessions["a"]
    m.drop_all()
    assert m.sessions == {} and not s.attached and writes == []
    m.reconcile()                              # leading again later: the row is attached again
    assert set(m.sessions) == {"a"}


# ---------- the newsletter job's bootstrap ----------
class Stop(Exception):
    pass


def test_a_database_error_at_boot_is_retried_on_the_next_pass(monkeypatch):
    monkeypatch.setattr(leader, "current", leader.Leader(lambda: None))
    j = news.Job(None)
    tries, ticks, passes = [], [], []

    def repair():
        tries.append(1)
        if len(tries) == 1:
            raise ConnectionError("Supabase unreachable")
    monkeypatch.setattr(j, "repair_once", repair)
    for name in ("restyle_once", "headlines_once", "r7_once", "et_once", "facts_once"):
        monkeypatch.setattr(j, name, lambda: None)
    monkeypatch.setattr(j, "tick", lambda now: ticks.append(now))

    def sleep(_):
        passes.append(1)
        if len(passes) == 3:
            raise Stop()
    monkeypatch.setattr(news, "time", types.SimpleNamespace(sleep=sleep))
    with pytest.raises(Stop):
        j._loop()
    assert len(tries) == 2 and len(ticks) == 3       # retried once, then done; the sends ran every pass


def test_a_follower_runs_none_of_the_jobs(monkeypatch):
    from app import audit, corp_actions, deals, money_networth, results, scan, screens
    from app.connect import jobs as connect_jobs
    from app.intel import filings
    monkeypatch.setattr(leader, "leading", lambda: False)
    ran = []

    def job(cls, **attrs):
        j = object.__new__(cls)
        j.status, j.lock = {}, threading.Lock()
        for name in ("tick", "run_once", "step"):
            setattr(j, name, lambda *a, _n=name: ran.append((cls.__name__, _n)))
        j.__dict__.update(attrs)
        return j
    for name in ("send_weekly_summary", "stock_price_refresh_once"):
        monkeypatch.setattr(main, name, lambda *a, _n=name: ran.append(_n))
    monkeypatch.setattr(main.pricing, "refresh_rates", lambda *a: ran.append("rates"))
    loops = [
        (results, job(results.Job)._loop), (corp_actions, job(corp_actions.Job)._loop),
        (money_networth, job(money_networth.Job)._loop), (filings, job(filings.Alerts)._loop),
        (scan, job(scan.Alerts, checks=[lambda now: ran.append("stock alerts")])._loop),
        (connect_jobs, job(connect_jobs.Job)._loop), (screens, job(screens.Indexer, every=1).loop),
        (audit, job(audit.MarketAudit, full_once=lambda: None, pause=0, cool=0).loop),
        (news, job(deals.Job, booted=True, repair_once=lambda: ran.append("repair"))._loop),
        (main, main.rates_job), (main, main.weekly_job), (main, main.stock_price_refresh_job),
    ]
    for mod, loop in loops:
        passes = []

        def sleep(_):
            passes.append(1)
            if len(passes) == 3:
                raise Stop()
        monkeypatch.setattr(mod, "time", types.SimpleNamespace(sleep=sleep, time=time.time))
        with pytest.raises(Stop):
            loop()
    assert ran == []
