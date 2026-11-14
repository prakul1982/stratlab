"""Company pages rebuilt faster in India's night and all weekend (owner, 14 Nov: 13,700 pages rebuilt to new facts at 20 a market a run
took about six days; "markets are closed, do it faster"). Fails before the change (no pace), passes after."""
from datetime import datetime, timezone

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import screens

screens._fw = screens.fast_window


def _at(d, h, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=timezone.utc)          # 12 Nov 2026 is a Thursday


def test_the_app_builds_three_times_as_many_pages_a_run_in_indias_night_and_the_usual_number_by_day():
    job = main.screen_indexer
    assert job.pace(_at(12, 20)) == (60, 12.0) and job.pace(_at(13, 0, 30)) == (60, 12.0)    # Thu/Fri night IST
    assert job.per_run(_at(12, 18, 30)) == 60 and job.per_run(_at(12, 18, 29)) == 20         # midnight IST: night starts
    assert job.pace(_at(12, 9)) == (20, 12.0) and job.per_run(_at(13, 1)) == 20              # weekday daytime


def test_all_weekend_in_india_it_builds_five_times_as_many_with_a_shorter_gap():   # updated on purpose: the gap keeps under the pages' ration (7 s, was 6)
    job = main.screen_indexer
    assert job.pace(_at(14, 9)) == (102, 7.0)                       # Saturday 14:30 IST
    assert job.pace(_at(13, 18, 30)) == (102, 7.0)                  # Saturday 00:00 IST
    assert job.pace(_at(15, 18, 29)) == (102, 7.0)                  # Sunday 23:59 IST
    assert job.pace(_at(15, 18, 30)) == (60, 12.0)                  # Monday 00:00 IST: back to the night pace
    assert job.pace(_at(16, 9)) == (20, 12.0)                       # Monday daytime


def test_the_pace_never_outgrows_the_half_hour_and_is_off_unless_asked():
    assert screens.Indexer(night_per_run=500).per_run(_at(12, 20)) == int(1800 * 0.8 / 12 / 2)   # what fits with a 12 s gap, both markets
    assert screens.Indexer(night_per_run=500).pace(_at(14, 9)) == (int(1800 * 0.8 / 7 / 2), 7.0)
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
    for when, factor in ((_at(14, 9), 2), (_at(12, 20), 2), (_at(12, 9), 1)):
        monkeypatch.setattr(screens, "fast_window", lambda now=None, w=when: screens._fw(w))
        assert store.limit() == store.per_minute * factor
    monkeypatch.setattr(store, "per_minute", 0)
    assert store.limit() == 0                        # a ration of none stays none
    job = main.screen_indexer
    for when in (_at(14, 9), _at(12, 20)):           # the indexer never asks for more builds a minute than the ration of those hours
        n, gap = job.pace(when)
        assert 60 / gap < 6 * screens.FAST_RATION


def test_the_pages_ration_follows_its_limit():
    from app import stock_pages
    built = []
    pages = stock_pages.Pages(lambda region, co: built.append(co) or {"v": stock_pages.FACTS_VERSION}, per_minute=1)
    pages.limit = lambda: 3
    for i in range(3):
        assert pages._may_build()
    assert not pages._may_build()
