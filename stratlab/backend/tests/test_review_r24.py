"""Round 24, India's open: the pulse answers from memory and never waits on a slow read, the broker's request turns go in
order without the lock held while waiting, the breadth rounds keep the quarter-hour clock, live counts reconcile with the
group, the PCR table has one basis, the two ATM IV figures are named apart, index changes round half up, the build is
shown, and the platform check says which build ran it. Fixed clocks only: nothing depends on the time of day."""
import json
import threading
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app import main  # noqa: F401, I001  (first: the app loads its modules in a fixed order)
from app import admin_jobs, breadth_live as BL, build_info, positioning as PO, vix
from app.intel import routes
from app.intel.company import Research, change_2dp, index_level
from app.intel.net import SourceError
from app.intel.snapshot import Snapshot
from app.kite_service import IST, KiteBusy, KiteService
from tests import fake_kite
from tests.test_breadth import mem  # noqa: F401  (fixture: the settings in memory, the three-stock market)
from tests.test_breadth_live import live, with_base


def ist(hm: str, day: str = "2026-10-01") -> datetime:          # Thursday 1 Oct 2026, a trading day
    h, m, *s = (int(x) for x in hm.split(":"))
    return datetime.fromisoformat(day).replace(hour=h, minute=m, second=s[0] if s else 0, tzinfo=IST)


# ---------- R24-001: the pulse never waits on a slow read ----------
class SlowYahoo:
    def __init__(self):
        self.gate, self.slow, self.reads = threading.Event(), False, 0

    def meta(self, sym):
        self.reads += 1
        if self.slow:
            self.gate.wait(20)
        return {"price": 22774.65, "prev_close": 22666.8, "change_pct": 0.4758, "high52": 26277.0, "low52": 21000.0,
                "at": "2026-10-15T09:46:00+05:30"}


class SlowNews:
    def __init__(self, gate):
        self.gate, self.slow = gate, False

    def search(self, q, region, limit=20):
        if self.slow:
            self.gate.wait(20)
        return [{"headline": "Nifty ends higher as banks gain", "url": "https://example.com/a"}]


def slow_hub():
    y = SlowYahoo()
    n = SlowNews(y.gate)
    hub = Research(None, finnhub=SimpleNamespace(ready=lambda: False), yahoo=y, screener=object(), news=n, wiki=object())
    return hub, y, n


def test_the_pulse_answers_from_memory_while_the_read_behind_it_is_held(monkeypatch):
    hub, y, n = slow_hub()
    monkeypatch.setattr(routes, "hub", hub)
    try:
        first = json.loads(routes.pulse(region="IN", focus="", profile={"id": "u1"}).body)
        assert [i["name"] for i in first["indices"]] == ["NIFTY 50", "SENSEX", "NIFTY BANK"] and first["headlines"]
        # every source now hangs, and every copy is due a fresh read
        y.slow = n.slow = True
        hub._levels_snap.fresh_for = hub._news_snap.fresh_for = 0
        t = time.monotonic()
        again = json.loads(routes.pulse(region="IN", focus="", profile={"id": "u1"}).body)
        assert time.monotonic() - t < 1.0                      # the request didn't wait on the held reads
        assert [i["price"] for i in again["indices"]] == [i["price"] for i in first["indices"]] and again["headlines"]
        assert again["read_at"]
    finally:
        y.gate.set()


def test_the_first_read_waits_only_so_long_and_says_it_is_pending():
    hub, y, _ = slow_hub()
    y.slow = True
    try:
        t = time.monotonic()
        assert hub.indices_now("IN", wait=0.2) == (None, None)
        assert time.monotonic() - t < 1.0
    finally:
        y.gate.set()


def test_the_mood_reads_the_same_levels_from_memory(monkeypatch):
    hub, y, n = slow_hub()
    monkeypatch.setattr(routes, "hub", hub)
    try:
        hub.indices_now("IN", wait=5)
        hub.headlines_now("IN", wait=5)
        y.slow = n.slow = True
        hub._levels_snap.fresh_for = hub._news_snap.fresh_for = 0
        monkeypatch.setattr(routes.A, "pulse", lambda *a, **k: {"tone": "Calm.", "hot": [], "flows": [], "themes": []})
        monkeypatch.setattr(routes, "ai_call", lambda profile, kind, key, ttl, refresh, build, **k: build())
        monkeypatch.setattr(routes, "flows_today", lambda: None)
        t = time.monotonic()
        routes.pulse_ai(region="IN", focus="", refresh=False, profile={"id": "u1", "_plan": "pro"})
        assert time.monotonic() - t < 1.0                      # the levels and headlines from memory, the held reads behind
    finally:
        y.gate.set()


def test_a_snapshot_gives_up_on_a_hung_read_and_starts_another():
    clock = [1000.0]
    s = Snapshot(fresh_for=10, give_up=30, clock=lambda: clock[0])
    gate, calls = threading.Event(), []

    def hung():
        calls.append(1)
        gate.wait(5)
        return "late"
    try:
        s.put("k", "old", at=900.0)
        assert s.get("k", hung, wait=1) == ("old", 900.0)          # the kept copy at once, a read started behind it
        time.sleep(0.05)
        assert len(calls) == 1
        assert s.get("k", hung, wait=1)[0] == "old"
        assert len(calls) == 1                                  # one read at a time
        clock[0] += 31                                          # that read has hung past give_up: a new one starts
        s.get("k", hung, wait=1)
        time.sleep(0.05)
        assert len(calls) == 2
    finally:
        gate.set()


def test_a_snapshot_keeps_the_last_good_copy_when_a_read_fails():
    s = Snapshot(fresh_for=0)
    s.put("k", "good", at=time.time() - 60)

    def boom():
        raise SourceError("x", "down", busy=True)
    assert s.get("k", boom, wait=1)[0] == "good"
    time.sleep(0.05)
    assert s.kept("k")[1] == "good" and "down" in s.errors["k"]
    fresh = Snapshot(fresh_for=10)
    with pytest.raises(SourceError):                            # nothing kept: the first read's own error
        fresh.get("k", boom, wait=1)


def test_the_index_levels_never_wait_long_on_the_52_week_source(monkeypatch):
    gate = threading.Event()

    class Hung:
        def meta(self, sym):
            gate.wait(10)
            return {}

    class Kite:
        def ready(self):
            return True

        def index_quotes(self, keys):
            return {k: {"price": 22774.65, "prev_close": 22666.8, "change_pct": 0.4758, "at": "2026-10-15T09:46:00+05:30"} for k in keys}
    hub = Research(Kite(), finnhub=SimpleNamespace(ready=lambda: False), yahoo=Hung(), screener=object(), news=object(), wiki=object())
    monkeypatch.setattr(hub, "LEVELS_WITHIN", 0.3)
    try:
        t = time.monotonic()
        got = hub.indices("IN", now=datetime(2026, 10, 15, 4, 16, tzinfo=timezone.utc))
        assert time.monotonic() - t < 1.5 and len(got) == 3 and got[0]["price"] == 22774.65
    finally:
        gate.set()


# ---------- R24-001 / R24-010: the broker's request turns ----------
def test_a_pages_quote_gives_up_at_once_behind_a_long_queue_of_turns():
    k = fake_kite.online()
    k.GAP = 0.36
    k._last_call = time.time() + 30                            # the jobs have booked half a minute of turns
    t = time.monotonic()
    with pytest.raises(KiteBusy):
        k.quote(["RELIANCE"], max_wait=2)
    assert time.monotonic() - t < 0.5
    assert k.quote(["RELIANCE"])["RELIANCE"]["price"]          # a job's read (no limit) still goes


def test_turns_go_in_order_and_nobody_sleeps_holding_the_lock():
    k = KiteService()
    k.GAP = 0.3
    order = []
    k._slot(None)                                               # the first turn is now

    def take(n):
        k._slot(None)
        order.append(n)
    a = threading.Thread(target=take, args=(1,))
    a.start()
    time.sleep(0.05)
    b = threading.Thread(target=take, args=(2,))
    b.start()
    time.sleep(0.05)
    assert k._lock.acquire(timeout=0.05)                       # both are waiting for their turns, neither holds the lock
    k._lock.release()
    a.join(2), b.join(2)
    assert order == [1, 2]


def test_a_restricted_series_stock_is_quoted_by_its_broker_symbol():
    k = fake_kite.online()
    got = k.quote(["SLOWCO", "RELIANCE"])
    assert got["SLOWCO"]["price"] and got["RELIANCE"]["price"]      # R24-003: SLOWCO trades as SLOWCO-BE
    both = k.quote(["SLOWCO", "SLOWCO-BE"])
    assert both["SLOWCO"]["price"] == both["SLOWCO-BE"]["price"]


# ---------- R24-002: rounds on the quarter-hour clock ----------
def test_the_quarter_hour_of_a_moment():
    assert [BL.slot_of(ist(t)) for t in ("09:15", "09:29:59", "09:30", "09:44", "09:45:01", "15:29", "15:30")] == \
        ["09:15", "09:15", "09:30", "09:30", "09:45", "15:15", "15:30"]


def test_rounds_follow_the_clock_and_catch_up_after_a_restart(mem):
    with_base(mem)
    calls = []
    job = BL.LiveJob(live(mem, calls=calls))
    assert job.tick(ist("09:15:20")) == 1
    assert job.tick(ist("09:29:50")) == 0                      # still the 09:15 quarter
    assert job.tick(ist("09:30:05")) == 1                      # on the clock, not 15 minutes after the last round ended
    # a deploy restarts the server at 09:41: the new process remembers nothing, the stored rounds say 09:30 is done
    job = BL.LiveJob(live(mem, calls=calls))
    assert job.tick(ist("09:41:00")) == 0
    # down through 09:45: the quarter hour that is due runs as soon as the new process looks, with its own time
    assert job.tick(ist("09:52:00")) == 1
    assert job.tick(ist("10:00:10")) == 1
    assert [p[0] for p in BL.load("nifty500", "2026-10-01")["points"]] == ["09:15", "09:30", "09:52", "10:00"]
    assert BL.status()["IN"]["slot"] == "10:00"


def test_the_first_look_after_a_start_is_within_a_minute():
    assert BL.STARTUP <= 60 and BL.TICK <= 30                  # not 15 minutes after the process started (R24-002)


def test_a_failed_round_is_tried_again_in_two_minutes_within_its_quarter(mem, monkeypatch):
    with_base(mem)
    q = {"v": RuntimeError("down")}
    lv = BL.Live(lambda syms: (_ for _ in ()).throw(q["v"]) if isinstance(q["v"], Exception) else q["v"], lambda: True,
                 sleep=lambda s: None, pause=0)
    job = BL.LiveJob(lv)
    t = [1_000_000.0]
    monkeypatch.setattr(BL.time, "time", lambda: t[0])
    assert job.tick(ist("10:15:10")) == 0 and "down" in BL.status()["IN"]["error"]
    t[0] += 60
    assert job.due("IN", ist("10:16:10")) is None
    t[0] += 61
    from tests.test_breadth_live import quotes
    q["v"] = quotes()
    assert job.tick(ist("10:17:11")) == 1


def test_a_slow_round_holds_the_next_only_until_it_ends(mem):
    with_base(mem)
    lv = live(mem)
    job = BL.LiveJob(lv)
    lv.lock.acquire()                                          # a round is still going (a slow read)
    try:
        assert job.tick(ist("10:30:10")) == 0
        assert "IN" not in lv.failed                           # busy is not a failure: no two-minute wait after it
    finally:
        lv.lock.release()
    assert job.tick(ist("10:31:00")) == 1                      # the due round runs the moment the slow one is done


def test_a_round_that_reads_too_long_gives_up(mem, monkeypatch):
    with_base(mem)
    monkeypatch.setattr(BL, "BATCH", 2)
    ticks = iter(range(0, 10_000, 300))                         # five minutes pass between each look at the clock
    lv = BL.Live(lambda syms: {}, lambda: True, sleep=lambda s: None, pause=0, clock=lambda: next(ticks))
    res = lv.round("IN", ist("11:00"))
    assert res["ok"] is False and "still reading" in BL.status()["IN"]["error"]


def test_the_card_says_when_its_newest_point_is_late(mem):
    with_base(mem)
    live(mem).round("IN", ist("09:15"))
    v = BL.view("nifty500", ist("09:41"))
    assert v["state"] == "live" and v["late"] is True and v["age_minutes"] == 26 and v["as_of"] == "09:15"
    on_time = BL.view("nifty500", ist("09:30"))
    assert on_time["late"] is False and on_time["age_minutes"] == 15


def test_admin_has_a_row_for_the_rounds_and_says_when_they_are_late():
    st = {"IN": {"at": "2026-10-01T03:45:30+00:00", "day": "2026-10-01", "time": "09:15", "slot": "09:15", "quoted": 2344,
                 "stocks": 2563, "seconds": 9.4, "error": None}}
    row = admin_jobs.breadth_live_row(st, {}, ist("09:41"))
    assert row["id"] == "breadth-live" and row["state"] == "warn" and "Late" in row["error"] and "09:15" in row["error"]
    assert "2,344 of 2,563 stocks read" in row["log"][0]
    ok = admin_jobs.breadth_live_row(st, {}, ist("09:20"))
    assert ok["state"] == "ok" and ok["error"] is None
    failed = admin_jobs.breadth_live_row({"IN": {**st["IN"], "failed_at": "2026-10-01T04:00:00+00:00", "error": "No live prices came back."}}, {}, ist("09:31"))
    assert failed["state"] == "bad" and failed["error"] == "No live prices came back."


def test_admin_jobs_list_the_rounds(monkeypatch):
    monkeypatch.setattr(BL, "status", lambda: {})
    assert any(r["id"] == "breadth-live" for r in admin_jobs.rows())


# ---------- R24-003: the counts reconcile with the group ----------
def test_stocks_without_a_price_today_are_counted_apart():
    base = {s: [100.0, 30, 1900.0, None, None] for s in "ABCDE"}
    q = {"A": {"price": 101.0, "prev_close": 100.0, "at": "2026-10-01T09:20:00+05:30"},
         "B": {"price": 99.0, "prev_close": 100.0, "at": "2026-10-01T09:20:00+05:30"},
         "C": {"price": 100.0, "prev_close": 100.0, "at": "2026-09-30T15:29:00+05:30"},    # no trade yet today: not "unchanged"
         "D": {"price": None}}                                                             # E: no quote at all
    c = BL.count(base, q, list("ABCDE"), "2026-10-01")
    assert (c["adv"], c["dec"], c["unch"], c["of"], c["unread"]) == (1, 1, 0, 5, 3)
    assert c["adv"] + c["dec"] + c["unch"] + c["unread"] == c["of"]


def test_a_live_point_carries_the_group_size_and_the_unread(mem):
    with_base(mem)
    q = {"UP": {"price": 1005.0, "prev_close": 999.0}, "DOWN": {"price": 95.0, "prev_close": 101.0}, "NIFTY 500": {"price": 24000.5}}
    BL.Live(lambda syms: q, lambda: True, sleep=lambda s: None, pause=0).round("IN", ist("10:30"))
    latest = BL.view("nifty500", ist("10:31"))["latest"]
    assert latest["of"] == 3 and latest["unread"] == 1 and latest["adv"] + latest["dec"] + latest["unch"] == 2


# ---------- R24-004: one PCR basis for every row ----------
def _chain(n: int, missing: int = 0, centre: float = 22750.0):
    half = n // 2
    rows = [[k, 0, 0, 0, 1000 + (k - centre) / 50, 0, 0, 0, 900 - (k - centre) / 50, 500, 400]
            for k in (centre + 50 * (i - half) for i in range(n))]          # each strike's open interest is its own
    for r in rows[half - missing // 2: half - missing // 2 + missing]:
        r[4] = None
    return rows


def test_every_pcr_row_counts_the_same_window_and_says_so(monkeypatch):
    live = {"expiry": "2026-10-20", "spot": 22750.0, "chain": _chain(81), "source": "live", "taken_at": "2026-10-15T09:18:00+05:30"}
    rec = {"expiry": "2026-10-20", "spot": 22750.0, "chain": _chain(31), "source": "recorded", "taken_at": "2026-10-15T09:35:00+05:30"}
    part = {**rec, "chain": _chain(31, missing=4)}
    monkeypatch.setattr(PO, "live_chains", lambda od, names, choice, quick=False: {"NIFTY": live, "BANKNIFTY": rec, "SENSEX": part})
    out = {r["name"]: r for r in PO.pcr_table(object(), ist("09:40", "2026-10-15"), ("NIFTY", "BANKNIFTY", "SENSEX"))}
    assert out["NIFTY"]["strikes_read"] == 81 and out["BANKNIFTY"]["strikes_read"] == 31
    assert {r["strikes_counted"] for r in (out["NIFTY"], out["BANKNIFTY"])} == {31}
    assert all(r["basis"] == "near" and r["strikes_window"] == 31 for r in out.values())
    assert out["NIFTY"]["pcr_oi"] == out["BANKNIFTY"]["pcr_oi"]          # the same 31 strikes, the same PCR
    assert out["SENSEX"]["partial"] is True and out["SENSEX"]["strikes_counted"] == 27 and not out["NIFTY"]["partial"]


# ---------- R24-005: the VIX card's ATM IV names its strike ----------
def test_the_vix_cards_atm_iv_says_its_strike(monkeypatch):
    got = {"taken_at": "2026-10-15T09:40:00+05:30", "source": "live"}
    monkeypatch.setattr(PO, "chain_now", lambda od, name, choice, now: (got, now, {"atm_iv": 13.45, "atm": 22750.0}))
    monkeypatch.setattr(PO, "chain_series", lambda name, since=None: [])
    today = vix.nifty_iv(object(), ist("09:41", "2026-10-15"))["today"]
    assert today["iv"] == 13.45 and today["strike"] == 22750.0


# ---------- R24-006: an index's change rounds half up, from its level ----------
def test_an_index_change_is_rounded_not_cut():
    assert change_2dp(22774.65, 22666.8) == 0.48                   # +0.4758%
    assert change_2dp(None, None, 0.475) == 0.48 and change_2dp(None, None, -0.475) == -0.48
    assert change_2dp(None, None, 0.4749) == 0.47 and change_2dp(None, None, None) is None
    row = index_level("NIFTY 50", {"price": 22774.65, "prev_close": 22666.8, "change_pct": 0.47, "at": "2026-10-15T09:46:00+05:30"}, "IN",
                      ist("09:47", "2026-10-15"))
    assert row["change_pct"] == 0.48
    assert index_level("NIFTY 50", row, "IN", ist("09:47", "2026-10-15"))["change_pct"] == 0.48     # served again, unchanged


def test_the_broker_level_keeps_its_own_previous_close():
    class Kite:
        def ready(self):
            return True

        def index_quotes(self, keys):
            return {k: {"price": 22774.65, "prev_close": 22666.8, "change_pct": 0.4758, "at": "2026-10-15T09:46:00+05:30"} for k in keys}

    class Y:
        def meta(self, sym):
            return {"price": 22700.0, "prev_close": 22600.0, "change_pct": 0.44, "high52": 26277.0}
    hub = Research(Kite(), finnhub=SimpleNamespace(ready=lambda: False), yahoo=Y(), screener=object(), news=object(), wiki=object())
    nifty = hub.indices("IN", now=ist("09:47", "2026-10-15"))[0]
    assert nifty["prev_close"] == 22666.8 and nifty["change_pct"] == 0.48 and nifty["high52"] == 26277.0


# ---------- R24-009: the build is shown ----------
def test_the_build_comes_from_the_deploy_and_nothing_else():
    env = {"RAILWAY_GIT_COMMIT_SHA": "4610D78ABCDEF0123456789ABCDEF0123456789A", "RAILWAY_GIT_BRANCH": "main",
           "BUILD_TIME": "2026-10-15T03:54:10Z", "RAILWAY_ENVIRONMENT_NAME": "production",
           "KITE_API_SECRET": "s3cret", "SUPABASE_SERVICE_KEY": "k3y"}
    b = build_info.info(env)
    assert b["sha"] == "4610d78abcdef0123456789abcdef0123456789a" and b["short"] == "4610d78" and b["branch"] == "main"
    assert b["built_at"] == "2026-10-15T03:54:10+00:00" and b["environment"] == "production" and b["started_at"]
    assert "s3cret" not in json.dumps(b) and "k3y" not in json.dumps(b)
    bad = build_info.info({"RAILWAY_GIT_COMMIT_SHA": "not a sha; rm -rf", "BUILD_TIME": "yesterday", "RAILWAY_GIT_BRANCH": "a b"})
    assert bad["sha"] is None and bad["built_at"] is None and bad["branch"] is None


def test_health_and_version_name_the_build(monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "4610d78abcdef0123456789abcdef0123456789a")
    c = TestClient(main.app)
    assert c.get("/health").json()["version"] == "4610d78"
    v = c.get("/version").json()
    assert v["short"] == "4610d78" and set(v) == {"sha", "short", "branch", "built_at", "started_at", "environment", "deployment"}
    assert main.server_status()["build"]["short"] == "4610d78"


# ---------- R24-010: the platform check says which build ran it ----------
def test_the_kept_platform_check_names_its_build(monkeypatch):
    from app import platform_check as pc
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "4610d78abcdef0123456789abcdef0123456789a")
        monkeypatch.setattr(main, "platform_checks", lambda: [("Fine", "Server", lambda: pc._result("Fine", "Server", "pass", "ok"))])
        out = main.run_platform_check(retry_after=0)
        assert out["build"] == "4610d78"
        last = w["client"].get("/admin/platform/last", headers=W.headers("admin-token")).json()["last"]
        assert last["build"] == "4610d78"
        # a scan has its own limit, well past the 45 s of the other checks, and stops reading inside it
        assert pc.TIMEOUTS["Scans"] > pc.SCAN_BUDGET > pc.TIMEOUT
    finally:
        w["close"]()
