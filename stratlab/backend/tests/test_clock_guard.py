"""R2 integration: no test leaves the clock moved for the next one (tests/conftest.py no_clock_left_moved). The leak that
failed test_fix1b::test_live1b_008 only in a combined run was one of a class: any time_machine travel started and not
stopped, or stopped once too often, changes the clock of every later test in that worker. The guard catches both
directions for every test; these prove it puts the stack back each way."""
from datetime import datetime, timezone

import time_machine

from tests import conftest, e2e_clock


def _now():
    return datetime.now(timezone.utc)


def test_the_suite_runs_at_the_pinned_moment_and_its_clock_ticks():
    pin = e2e_clock.moment("open")
    assert conftest._PINNED is not None and time_machine.traveller_stack
    assert abs((_now() - pin).total_seconds()) < 24 * 3600                   # the pinned day, not the machine's


def test_a_travel_left_running_is_stopped_and_named():
    before = list(time_machine.traveller_stack)
    time_machine.travel(datetime(2020, 1, 1, tzinfo=timezone.utc), tick=False).start()       # never stopped
    assert _now().year == 2020
    assert conftest.clock_moved(before) == "left 1 and popped 0"
    assert [id(t) for t in time_machine.traveller_stack] == [id(t) for t in before] and _now().year == 2026


def test_a_travel_stopped_twice_has_the_travel_under_it_put_back():
    # a travel of this test's own stands in for the suite's pin (the guard would otherwise see the pin restarted)
    day = datetime(2026, 10, 28, 5, 30, tzinfo=timezone.utc)
    time_machine.travel(day, tick=True).start()
    before = list(time_machine.traveller_stack)
    t = time_machine.travel(datetime(2020, 1, 1, tzinfo=timezone.utc))
    t.start()
    t.stop()
    t.stop()                                                                   # pops the travel under it
    assert time_machine.traveller_stack[-1:] != before[-1:]
    assert conftest.clock_moved(before) == "left 0 and popped 1"
    assert len(time_machine.traveller_stack) == len(before)
    assert 0 <= (_now() - day).total_seconds() < 600                           # back at its moment, still ticking
    assert conftest.clock_moved(list(time_machine.traveller_stack)) is None
    time_machine.travel(0).stop()                                              # this test's own travel, stopped


def test_a_clean_travel_moves_nothing():
    before = list(time_machine.traveller_stack)
    with time_machine.travel(datetime(2020, 1, 1, tzinfo=timezone.utc), tick=False):
        assert _now().year == 2020
    assert conftest.clock_moved(before) is None


def test_no_test_module_moves_the_clock_as_it_loads():
    """Every module collected in this run (the whole suite in a full run) was imported without moving the clock; the
    browser tests' server module, the one that did, is checked here even when run alone."""
    import importlib
    import sys
    if "tests.visual_server" not in sys.modules:
        before = list(time_machine.traveller_stack)
        importlib.import_module("tests.visual_server")
        assert conftest.clock_moved(before) is None
    assert conftest.MOVED_AT_IMPORT == []
