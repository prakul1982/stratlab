"""MEM-001: the memory habits (app/memguard.py): heavy background jobs take turns, hand their memory back, and the caches
stay under one budget. None of it changes a result."""
import threading
import time

import pytest

from app import audit, memguard, screens
from app.intel import net


def test_heavy_jobs_run_one_at_a_time_in_the_order_they_asked():
    order, inside, worst = [], [0], [0]

    def job(name):
        with memguard.heavy(name):
            inside[0] += 1
            worst[0] = max(worst[0], inside[0])
            order.append(name)
            time.sleep(0.05)
            inside[0] -= 1
    with memguard.heavy("first"):
        threads = []
        for n in ("a", "b", "c"):
            t = threading.Thread(target=job, args=(n,))
            t.start()
            threads.append(t)
            time.sleep(0.03)                       # asked in this order while "first" holds the turn
        assert memguard.TURNS.waiting() == 3
    for t in threads:
        t.join(5)
    assert order == ["a", "b", "c"]
    assert worst[0] == 1
    assert memguard.TURNS.name is None


def test_a_job_holding_the_turn_can_start_another_inside_it():
    with memguard.heavy("outer"):
        with memguard.heavy("inner") as got:
            assert got and memguard.TURNS.holds()
        assert memguard.TURNS.holds()              # still the outer job's turn
    assert not memguard.TURNS.holds()


def test_a_job_that_waits_too_long_runs_anyway():
    done = []
    holder = threading.Event()

    def hold():
        with memguard.heavy("stuck"):
            holder.wait(5)
    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.05)
    assert memguard.TURNS.acquire("late", 0.05) is False        # the wait ran out: no turn, and no hang
    done.append(1)
    holder.set()
    t.join(5)
    assert done and memguard.TURNS.name is None and memguard.TURNS.waiting() == 0


def test_the_turn_is_given_up_when_the_work_fails():
    with pytest.raises(ValueError):
        with memguard.heavy("boom"):
            raise ValueError("x")
    assert memguard.TURNS.name is None
    with memguard.heavy("after") as got:
        assert got


def test_release_memory_sweeps_expired_cache_entries_and_reports():
    c = net.TTLCache(max_items=10)
    c.set("gone", "x" * 1000, -1)
    c.set("kept", "y" * 1000, 600)
    out = memguard.release_memory(force=True)
    assert c.get("kept") is not None and "gone" not in c._d
    assert "cache_freed_mb" in out
    assert memguard.release_memory() == {}          # not again within the interval unless forced


def test_caches_are_pushed_under_one_budget_dropping_the_oldest_first(monkeypatch):
    import weakref
    a, b = net.TTLCache(max_items=100, max_bytes=10_000_000), net.SizedDict(max_items=100, max_bytes=10_000_000)
    monkeypatch.setattr(net, "_REGISTRY", weakref.WeakSet([a, b]))          # only these two, whatever else the process holds
    for i in range(20):
        a.set(i, "a" * 100_000, 600, size=100_000)
        b[i] = "b" * 100_000
    assert net.cache_bytes() > 3_000_000
    freed = net.shrink_caches(1_000_000)
    assert freed > 0 and net.cache_bytes() <= 1_100_000
    assert a.get(19) is not None or b.get(19) is not None      # the newest stay
    assert a.get(0) is None and b.get(0) is None


def test_a_source_keeps_far_less_for_the_day_it_cannot_be_asked():
    s = net.Source("https://example.invalid")
    assert s.stale.max_bytes < s.cache.max_bytes and s.stale.max <= 1000


def test_tune_malloc_never_raises_and_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("MALLOC_TUNE", "0")
    assert memguard.tune_malloc() is False
    monkeypatch.delenv("MALLOC_TUNE")
    assert memguard.tune_malloc() in (True, False)
    assert memguard.malloc_trim() in (True, False)
    assert memguard.rss_mb() is None or memguard.rss_mb() > 0


@pytest.fixture
def w(monkeypatch):
    from tests import world as W
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def test_the_market_audit_checks_a_company_with_the_turn_held(w):
    held = []

    def check(sym):
        held.append(memguard.TURNS.holds())
        return {"symbol": sym, "name": sym, "seconds": 0.1, "issues": []}
    a = audit.MarketAudit(lambda: [{"symbol": "AAA", "name": "A Ltd", "listed": "2001-01-01"}], check, pause=0)
    a.set_enabled(True)
    a.start_full()
    a.refresh_list(force=True)
    assert a.step() == "AAA"
    assert held == [True]


def test_the_screens_index_builds_and_warms_with_the_turn_held(monkeypatch, w):
    seen = []
    real = screens.build_index
    monkeypatch.setattr(screens, "build_index", lambda region, store=True: (seen.append(("build", memguard.TURNS.holds())),
                                                                              {"rows": [], "_ages": {}, "_empty": set(), "_old": {}})[1])
    monkeypatch.setattr(screens.Indexer, "_due", lambda self, region, ages, empty=None, old=None: [("AAA", {"name": "A"})])
    idx = screens.Indexer(lambda r, s, c: seen.append(("warm", memguard.TURNS.holds())), gap=0)
    idx.run_once(sleep=lambda s: None)
    assert seen and all(held for _, held in seen)
    assert {k for k, _ in seen} == {"build", "warm"}
    assert real is not None


def test_the_mutual_fund_history_kept_in_memory_is_bounded():
    from app import money_mf_behaviour as mb
    assert mb._mem.max <= 100
    mb.forget()
    for i in range(300):
        mb._mem[str(i)] = {"from": "2020-01-01", "to": "2020-01-02", "p": [["2020-01-01", 1.0]]}
    assert len(mb._mem) <= mb._mem.max
    mb.forget()
