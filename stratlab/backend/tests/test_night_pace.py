"""Company pages rebuilt faster in India's night (owner, 14 Nov: 13,700 pages rebuilt to new facts at 20 a market a run took about six
days). Fails before the change (no per_run, no night pace), passes after."""
from datetime import datetime, timezone

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import screens


def _at(h, m=0):
    return datetime(2026, 11, 14, h, m, tzinfo=timezone.utc)


def test_the_app_builds_three_times_as_many_pages_a_run_in_indias_night_and_the_usual_number_by_day():
    job = main.screen_indexer
    assert job.per_run(_at(20)) == 60 and job.per_run(_at(0, 30)) == 60          # 01:30 and 06:00 IST
    assert job.per_run(_at(18, 30)) == 60                                         # midnight IST: night starts
    assert job.per_run(_at(1)) == 20 and job.per_run(_at(9)) == 20               # 06:30 and 14:30 IST: day
    assert job.per_run(_at(18, 29)) == 20


def test_the_night_pace_never_outgrows_the_half_hour_and_is_off_unless_asked():
    assert screens.Indexer(night_per_run=500).per_run(_at(20)) == int(1800 * 0.8 / 12 / 2)       # what fits with a 12 s gap, both markets
    assert screens.Indexer().per_run(_at(20)) == 20                                              # off by default (tests, other uses)
    ages = {s: 0 for s in ("AAPL", "MSFT", "NVDA")}
    assert len(screens.Indexer(warm_per_run=2, night_per_run=3)._due("US", ages, set(), {}, n=1)) <= 1
