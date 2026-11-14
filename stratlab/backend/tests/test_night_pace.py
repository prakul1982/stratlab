"""Company pages rebuilt faster in India's night and all weekend (owner, 14 Nov: 13,700 pages rebuilt to new facts at 20 a market a run
took about six days; "markets are closed, do it faster"). Fails before the change (no pace), passes after."""
from datetime import datetime, timezone

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import screens


def _at(d, h, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=timezone.utc)          # 12 Nov 2026 is a Thursday


def test_the_app_builds_three_times_as_many_pages_a_run_in_indias_night_and_the_usual_number_by_day():
    job = main.screen_indexer
    assert job.pace(_at(12, 20)) == (60, 12.0) and job.pace(_at(13, 0, 30)) == (60, 12.0)    # Thu/Fri night IST
    assert job.per_run(_at(12, 18, 30)) == 60 and job.per_run(_at(12, 18, 29)) == 20         # midnight IST: night starts
    assert job.pace(_at(12, 9)) == (20, 12.0) and job.per_run(_at(13, 1)) == 20              # weekday daytime


def test_all_weekend_in_india_it_builds_six_times_as_many_with_half_the_gap():
    job = main.screen_indexer
    assert job.pace(_at(14, 9)) == (120, 6.0)                       # Saturday 14:30 IST
    assert job.pace(_at(13, 18, 30)) == (120, 6.0)                  # Saturday 00:00 IST
    assert job.pace(_at(15, 18, 29)) == (120, 6.0)                  # Sunday 23:59 IST
    assert job.pace(_at(15, 18, 30)) == (60, 12.0)                  # Monday 00:00 IST: back to the night pace
    assert job.pace(_at(16, 9)) == (20, 12.0)                       # Monday daytime


def test_the_pace_never_outgrows_the_half_hour_and_is_off_unless_asked():
    assert screens.Indexer(night_per_run=500).per_run(_at(12, 20)) == int(1800 * 0.8 / 12 / 2)   # what fits with a 12 s gap, both markets
    assert screens.Indexer(night_per_run=500).pace(_at(14, 9)) == (int(1800 * 0.8 / 6 / 2), 6.0)
    assert screens.Indexer().pace(_at(14, 9)) == (20, 12.0)                                       # off by default (tests, other uses)


def test_a_run_builds_the_paced_number_with_the_paced_gap(monkeypatch):
    built, slept = [], []
    job = screens.Indexer(lambda r, s, c: built.append(s), night_per_run=60)
    monkeypatch.setattr(job, "pace", lambda now=None: (3, 6.0))
    monkeypatch.setattr(screens, "REGIONS", ("US",))
    job.run_once(sleep=slept.append)
    assert len(built) <= 3 and all(g == 6.0 for g in slept)
