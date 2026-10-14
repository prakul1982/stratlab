"""app/run_marks.py: a job's per-day marker that says how far the run got, so a kill mid-run is resumed, not lost."""
from types import SimpleNamespace

import pytest

from app import db, run_marks

DAY = "2026-10-01"


@pytest.fixture
def kv(monkeypatch):
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    return kv


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(run_marks, "time", SimpleNamespace(time=lambda: now[0]))
    return now


def test_a_run_killed_after_some_recipients_resumes_with_the_rest(kv, clock):
    run = run_marks.claim("job:x", DAY)
    for uid in ("a", "b"):
        run.record(uid)                                    # killed here: "c" and "d" were never reached
    clock[0] += 5
    assert run_marks.claim("job:x", DAY) is None           # still beating: not resumed
    clock[0] += run_marks.STALE
    again = run_marks.claim("job:x", DAY)
    assert again and [u for u in "abcd" if not again.seen(u)] == ["c", "d"]
    for uid in ("c", "d"):
        again.record(uid)
    again.done()
    assert run_marks.status("job:x", DAY) == "done" and sorted(run_marks.read("job:x")["sent"]) == list("abcd")


def test_a_done_marker_skips_and_a_new_day_starts_afresh(kv, clock):
    run = run_marks.claim("job:x", DAY)
    run.record("a")
    run.done()
    clock[0] += 10 * run_marks.STALE
    assert run_marks.claim("job:x", DAY) is None
    nxt = run_marks.claim("job:x", "2026-10-02")
    assert nxt and not nxt.seen("a")


def test_a_fresh_running_marker_is_not_resumed_but_a_stale_one_is(kv, clock):
    run_marks.claim("job:x", DAY)
    clock[0] += run_marks.STALE - 1
    assert run_marks.status("job:x", DAY) == "running" and run_marks.claim("job:x", DAY) is None
    clock[0] += 2
    assert run_marks.status("job:x", DAY) is None and run_marks.claim("job:x", DAY)


def test_a_plain_day_string_from_before_reads_as_done(kv):
    kv["job:x"] = DAY
    assert run_marks.status("job:x", DAY) == "done" and run_marks.claim("job:x", DAY) is None
    kv["job:y"] = "2026-09-14T10:00+00:00"                  # advance tax kept a timestamp; its key is already unique
    assert run_marks.claim("job:y", DAY, once=True) is None
