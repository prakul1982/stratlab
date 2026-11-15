"""Company pages rebuilt faster in India's night and all weekend (owner, 14 Nov: 13,700 pages rebuilt to new facts at 20 a market a run
took about six days; "markets are closed, do it faster"). Fails before the change (no pace), passes after."""
from datetime import datetime, timezone

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import screens

screens._fw = screens.fast_window


def _at(d, h, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=timezone.utc)          # 12 Nov 2026 is a Thursday


def test_the_app_builds_many_more_pages_a_run_in_indias_night_and_the_usual_number_by_day():   # updated on purpose: owner 15 Nov, finish by tonight (240 a market with a 2 s gap, was 60 with 12 s)
    job = main.screen_indexer
    assert job.pace(_at(12, 20)) == (240, 2.0) and job.pace(_at(13, 0, 30)) == (240, 2.0)    # Thu/Fri night IST
    assert job.per_run(_at(12, 18, 30)) == 240 and job.per_run(_at(12, 18, 29)) == 20        # midnight IST: night starts
    assert job.pace(_at(12, 9)) == (20, 12.0) and job.per_run(_at(13, 1)) == 20              # weekday daytime


def test_all_weekend_and_all_night_in_india_it_builds_at_one_fast_pace():   # updated on purpose: owner 15 Nov, night = weekend pace (240, 2 s; was 102, 7 s at the weekend)
    job = main.screen_indexer
    assert job.pace(_at(14, 9)) == (240, 2.0)                       # Saturday 14:30 IST
    assert job.pace(_at(13, 18, 30)) == (240, 2.0)                  # Saturday 00:00 IST
    assert job.pace(_at(15, 18, 29)) == (240, 2.0)                  # Sunday 23:59 IST
    assert job.pace(_at(15, 18, 30)) == (240, 2.0)                  # Monday 00:00 IST: the night, same pace
    assert job.pace(_at(16, 9)) == (20, 12.0)                       # Monday daytime


def test_the_pace_never_outgrows_the_half_hour_and_is_off_unless_asked():
    assert screens.Indexer(night_per_run=500).per_run(_at(12, 20)) == int(1800 * 0.8 / 2 / 2)    # updated on purpose: what fits with the 2 s gap, both markets
    assert screens.Indexer(night_per_run=500).pace(_at(14, 9)) == (int(1800 * 0.8 / 2 / 2), 2.0)
    assert screens.Indexer().pace(_at(14, 9)) == (20, 12.0)                                       # off by default (tests, other uses)


def test_a_run_builds_the_paced_number_with_the_paced_gap(monkeypatch):
    built, slept = [], []
    job = screens.Indexer(lambda r, s, c: built.append(s), night_per_run=60)
    monkeypatch.setattr(job, "pace", lambda now=None: (3, 6.0))
    monkeypatch.setattr(screens, "REGIONS", ("US",))
    job.run_once(sleep=slept.append)
    assert len(built) <= 3 and all(g == 6.0 for g in slept)


def test_pages_are_built_twice_as_many_a_minute_in_indias_night_and_at_the_weekend(monkeypatch):
    """The indexer's faster pace ran into the pages' ration of 6 a minute: past it a page is served as stored, not rebuilt."""
    store = main.stock_page_store
    for when, factor in ((_at(14, 9), screens.FAST_RATION), (_at(12, 20), screens.FAST_RATION), (_at(12, 9), 1)):   # updated on purpose: FAST_RATION 6 (was 2)
        monkeypatch.setattr(screens, "fast_window", lambda now=None, w=when: screens._fw(w))
        assert store.limit() == store.per_minute * factor
    monkeypatch.setattr(store, "per_minute", 0)
    assert store.limit() == 0                        # a ration of none stays none
    job = main.screen_indexer
    for when in (_at(14, 9), _at(12, 20)):           # the indexer never asks for more builds a minute than the ration of those hours
        n, gap = job.pace(when)
        assert 60 / gap < 6 * screens.FAST_RATION and screens.FAST_RATION * 6 <= 36   # never more than 36 builds a minute


def test_the_pages_ration_follows_its_limit():
    from app import stock_pages
    built = []
    pages = stock_pages.Pages(lambda region, co: built.append(co) or {"v": stock_pages.FACTS_VERSION}, per_minute=1)
    pages.limit = lambda: 3
    for i in range(3):
        assert pages._may_build()
    assert not pages._may_build()


class _Busy(Exception):
    pass


def test_both_markets_are_taken_in_turn_and_a_busy_page_is_skipped_not_the_rest_of_the_run(monkeypatch):
    """Owner 15 Nov: the rebuild must go faster. A run used to stop a market at its first busy answer; now that page waits for the
    next run and the rest are built, the two markets alternating."""
    built = []

    def warm(region, sym, co):
        if sym == "IN2":
            raise _Busy("busy")
        built.append(sym)
    job = screens.Indexer(warm, night_per_run=60)
    monkeypatch.setattr(screens, "REGIONS", ("IN", "US"))
    monkeypatch.setattr(screens, "build_index", lambda region, store=True: {"rows": [], "_ages": {}})
    monkeypatch.setattr(job, "_due", lambda region, ages, empty=None, old=None, n=None: [(f"{region}{i}", {}) for i in range(1, 5)])
    job.run_once(sleep=lambda s: None)
    assert built == ["IN1", "US1", "US2", "IN3", "US3", "IN4", "US4"]


def test_a_market_rests_after_three_busy_answers_in_a_row(monkeypatch):
    built = []

    def warm(region, sym, co):
        if region == "IN":
            raise _Busy("busy")
        built.append(sym)
    job = screens.Indexer(warm, night_per_run=60)
    tried = []
    monkeypatch.setattr(screens, "REGIONS", ("IN", "US"))
    monkeypatch.setattr(screens, "build_index", lambda region, store=True: {"rows": [], "_ages": {}})
    monkeypatch.setattr(job, "_due", lambda region, ages, empty=None, old=None, n=None: [(f"{region}{i}", {}) for i in range(1, 7)])
    orig = job.warm
    job.warm = lambda r, s, c: (tried.append(s), orig(r, s, c))
    job.run_once(sleep=lambda s: None)
    assert [s for s in tried if s.startswith("IN")] == ["IN1", "IN2", "IN3"] and len(built) == 6


def test_runs_start_every_half_hour_from_the_start_not_a_half_hour_after_a_long_run(monkeypatch):
    t = [0.0]
    slept = []
    job = screens.Indexer(lambda r, s, c: None, night_per_run=60)
    monkeypatch.setattr(screens.leader, "leading", lambda: True)
    monkeypatch.setattr(job, "run_once", lambda sleep=None: t.__setitem__(0, t[0] + 1500))     # a 25-minute run
    job.loop(clock=lambda: t[0], sleep=slept.append, runs=1)
    assert slept == [300, 300]                                       # startup pause, then 1800 - 1500
    t[0] = 0.0
    slept.clear()
    monkeypatch.setattr(job, "run_once", lambda sleep=None: t.__setitem__(0, t[0] + 3000))     # longer than the half hour
    job.loop(clock=lambda: t[0], sleep=slept.append, runs=1)
    assert slept == [300, job.MIN_REST]
