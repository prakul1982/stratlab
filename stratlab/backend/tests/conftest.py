import os
import sys

os.environ.setdefault("BACKTEST_PROCESSES", "0")      # backtests in the test process, where fakes are patched in
os.environ["AI_AUTO_PROBE"] = "0"                     # no background AI model measuring (it would use the network)
os.environ["AUTOFIX"] = "0"                           # no background self-healing sweep (tests run it by hand)
os.environ["THEME_AUTO_POST"] = "0"                   # no blog post drafted beside a theme read (tests call auto_post with wait=True)
os.environ["OFFICIAL_CLOSE_FETCH"] = "0"               # no exchange file or broker read for official closes (app/official_close.py)

import pytest


def _pin_the_clock():
    """Every test runs at one fixed moment, the browser tests' (tests/e2e_clock.py OPEN: Wed 28 Oct 2026, 11:00 IST), and
    its clock runs on from there (CLOCK follow-up, owner 4 Nov: "fix things globally"). The fake world's prices, candles,
    headlines and dates are drawn from "now", so a suite read at the machine's clock passed in October and failed in
    November (a 31 Jan 2018 price looked up for grandfathering, a fixed end date that had passed, a figure that only
    matched while the month was 10). Started as this file loads, before any test module imports the app, so even the
    times modules read as they load are the moment's. A test that needs another moment travels there itself (nested
    travels work); TESTS_NOW=closed / <ISO with zone> picks another moment, TESTS_NOW=real the machine's clock.
    Its own travel, not e2e_clock.start's, so tests of e2e_clock can start and stop theirs."""
    from tests import e2e_clock
    at = e2e_clock.moment(os.environ.get("TESTS_NOW") or "open")
    if at is None:
        return None
    travel = e2e_clock._time_machine().travel(at, tick=True)
    travel.start()
    return travel


_PINNED = _pin_the_clock()


@pytest.fixture(autouse=True)
def no_clock_left_moved():
    """Every test leaves the clock as it found it (R2 integration: test_fix1b::test_live1b_008 failed only in a combined
    run). time_machine keeps ONE stack of travels and its stop() pops the top one, whoever started it: a travel started
    and never stopped (a fixture that raised after clock.start(), before its yield) leaves every later test in that worker
    at its moment, frozen when tick=False; a travel stopped twice pops the suite's own pin and the world reads the
    machine's clock. So after each test the stack is put back exactly as it was and the test that moved it errors with
    its name, whichever test, fixture or travel kind it was (tests/test_clock_guard.py proves both directions)."""
    tm = sys.modules.get("time_machine")
    before = list(tm.traveller_stack) if tm else []
    yield
    moved = clock_moved(before)
    if moved:
        pytest.fail(f"the test {moved} time_machine travel(s) (started without a stop, or stopped twice); "
                    "use `with time_machine.travel(...)` or request.addfinalizer(travel.stop) right after start()", pytrace=False)


MOVED_AT_IMPORT: list[str] = []      # test modules whose import moved the clock (tests/test_clock_guard.py asserts none)


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    """The same for importing every test module (collection, before any test runs): a module that starts a travel as it
    loads (tests/visual_server.py did) would move every later test in that worker. Put back and named."""
    tm = sys.modules.get("time_machine")
    before = list(tm.traveller_stack) if tm else []
    yield
    moved = clock_moved(before)
    if moved:
        MOVED_AT_IMPORT.append(f"{collector.nodeid}: {moved}")


def clock_moved(before: list) -> str | None:
    """None when time_machine's stack holds exactly the travels of `before`; else it is put back and what happened said."""
    tm = sys.modules.get("time_machine")
    if tm is None or [id(t) for t in tm.traveller_stack] == [id(t) for t in before]:
        return None
    return _restore_clock(tm, before)


def _restore_clock(tm, before: list) -> str:
    """Put time_machine's stack back to `before`: stop what was left on top, start again what was popped (each at its
    own moment, ticking as it did). Returns what happened, for the failure message."""
    after = tm.traveller_stack
    keep = 0
    while keep < min(len(after), len(before)) and after[keep] is before[keep]:
        keep += 1
    extra, lost = len(after) - keep, len(before) - keep
    while len(tm.traveller_stack) > keep:
        tm.travel(0).stop()                      # stop() pops the top of the shared stack (and unpatches when it empties)
    for t in before[keep:]:
        tm.travel(_moment_ns(tm, t) / 1e9, tick=t._tick).start()
    return f"left {extra} and popped {lost}"


def _moment_ns(tm, t) -> int:
    """Where a stopped travel's clock stands now (Traveller.time_ns reads the real clock only while some travel runs)."""
    if not t._tick or not t._requested:
        return t._destination_timestamp_ns
    import time
    real = tm._time_machine.original_time_ns() if tm.traveller_stack else time.time_ns()
    return t._destination_timestamp_ns + (real - t._real_start_timestamp_ns)


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    """Every test client calls from the same address, so the server's per-minute request limit would carry over from
    one test to the next and fail whichever test happens to come after a busy one. Each test starts with it cleared."""
    yield
    main = sys.modules.get("app.main")
    if main is None:
        return
    main._recent.clear()          # per-user "a few times an hour" limits (test emails and the like) too
    from app.guard import Guard
    node = getattr(main.app, "middleware_stack", None)
    while node is not None:
        if isinstance(node, Guard):
            node.window._d.clear()
        node = getattr(node, "app", None)


@pytest.fixture(autouse=True)
def fresh_kept_answers():
    """The answers kept to serve at once (app/swr.py: deals, business updates) start empty in every test: one test's fake
    feed must not answer for the next."""
    swr = sys.modules.get("app.swr")
    if swr is not None:
        swr.clear()
    yield


@pytest.fixture(autouse=True)
def fresh_shared_quotes():
    """Stock quotes shared for a few seconds (app/quote_share.py), and the answers the pages read each minute and the server keeps
    for a few seconds, start empty in every test: one test's fake feed must not answer for the next."""
    def clear():
        qs, main = sys.modules.get("app.quote_share"), sys.modules.get("app.main")
        if qs is not None:
            qs.forget()
        co = sys.modules.get("app.intel.company")
        if co is not None:
            co.forget_closed_quotes()            # quotes kept after a close (LIVE5-001)
        if main is not None and hasattr(main, "_breadth_views"):
            main._breadth_views.clear()          # the breadth route's stored days, kept a few seconds (LIVE-1)
        tr = sys.modules.get("app.intel.theme_routes")
        if tr is not None:
            for j in list(tr._jobs.values()):     # a theme's AI parts written in the background (LIVE3-001): finished before the next test
                j["done"].wait(30)
            tr._jobs.clear()
    clear()
    yield
    clear()


@pytest.fixture(autouse=True)
def no_monthly_blog_research(monkeypatch):
    """The newsletter job's monthly run of the blog's research generator (app/blog_research.py) reads the library, the IPO
    tracker and the index history; a newsletter test whose clock is past the third of a month writes no research posts. The
    blog's own tests (tests/test_blog.py) pass their own builders."""
    import importlib
    monkeypatch.setattr(importlib.import_module("app.blog_research"), "POSTS", ())
    yield


@pytest.fixture(autouse=True)
def razorpay_confirms_what_the_event_says(monkeypatch):
    """A webhook's subscription is checked against Razorpay's own copy (app/billing.py _confirmed) before anything acts on
    it; tests have no Razorpay, so the event's copy stands for it. tests/test_billing_events.py checks _confirmed itself."""
    import importlib
    billing = importlib.import_module("app.billing")      # loaded here, so a test that imports it later is covered too
    monkeypatch.setattr(billing, "_confirmed", lambda sub: sub)
    yield


@pytest.fixture(autouse=True)
def no_official_close_reads():
    """The official-close store (app/official_close.py) never reads the exchange's file or the broker from a test: a
    test that wants it sets its own sources. Its memory doesn't carry over from one test to the next."""
    oc = sys.modules.get("app.official_close")
    if oc is not None:
        oc.setup(None, None)
        oc.forget()
    yield
    oc = sys.modules.get("app.official_close")
    if oc is not None:
        oc.setup(None, None)
        oc.forget()


@pytest.fixture(autouse=True, scope="session")
def still_market_clock():
    """The fake market's clock stands still for the whole run (tests/fake_prices.py): in the session, a price read by a
    test and the same price read by a page a moment later, or kept in a quote cache by the test before, never fall on
    two sides of a minute."""
    from datetime import datetime, timezone
    from tests import fake_prices
    fake_prices.FROZEN = fake_prices.SESSION_FROZEN = datetime.now(timezone.utc)
    yield
    fake_prices.FROZEN = fake_prices.SESSION_FROZEN = None


@pytest.fixture(autouse=True)
def market_clock_follows_the_day(monkeypatch):
    """The session's frozen market clock (above) is set once, so a run that starts before India's midnight and carries
    on past it, or a test clock that sits on another day, would read prices and candles stamped with yesterday's date.
    When the clock is on a different India day than the frozen one, the fake market moves to now; within a day it
    stands still, as the session fixture promises."""
    from datetime import datetime, timedelta, timezone
    from tests import fake_prices
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(timezone.utc)
    if fake_prices.FROZEN is not None and fake_prices.FROZEN.astimezone(ist).date() != now.astimezone(ist).date():
        monkeypatch.setattr(fake_prices, "FROZEN", now)
    monkeypatch.setattr(fake_prices, "_followed", None)     # a day an earlier test travelled to (fake_prices.clock_now)
    yield


@pytest.fixture(autouse=True)
def fresh_settings_mirror():
    """The in-memory copy of the stored company pages (app/db.py) doesn't carry over from one test to the next."""
    from app import admin, corp_actions, db
    db.forget_mirror()
    admin.forget_owners()               # the owner ids read from settings too
    corp_actions.forget_cached()        # and the parsed corporate-actions calendar
    _forget_overview()
    yield
    db.forget_mirror()
    admin.forget_owners()
    corp_actions.forget_cached()


def _forget_overview():
    m = sys.modules.get("app.main")
    if m is not None:
        m.forget_overview()
        m._errors_due[0], m._errors_saved_at[0] = False, float("-inf")     # an earlier test's crash doesn't delay this one's save


def _forget_company_lists():
    sp, sc = sys.modules.get("app.stock_pages"), sys.modules.get("app.screens")
    if sp is not None:
        sp._companies.clear()
    if sc is not None:
        with sc._mem_lock:
            sc._mem.clear()
            sc._built.clear()
            sc._priced.clear()      # the newer closes the price job noted (LIVE3-003)


@pytest.fixture(autouse=True)
def fresh_company_lists():
    """The public pages (app/stock_pages.py) and the stock screens (app/screens.py) keep the company lists they read in
    memory for the process. A test that built them from its own small world left that list for whichever test came next
    on the same worker (the demo world's screens saw 5 companies instead of its 20 when they ran after the stock-page
    tests), so the lists don't carry over from one test to the next."""
    _forget_company_lists()
    yield
    _forget_company_lists()


@pytest.fixture(autouse=True)
def fresh_ai():
    """What the AI layer learnt about models, and the answers it cached, don't carry over from one test to the next;
    it keeps them in memory instead of the database."""
    from app import ai_providers, ai_rank
    ai_rank.STORE = ai_rank.MemoryStore()
    ai_providers.reset()
    yield


def pytest_runtest_logreport(report):
    """On GitHub, each failing test also becomes an annotation on the pull request, readable without the job log."""
    if not (report.failed and os.environ.get("GITHUB_ACTIONS")):
        return
    path, line, _ = report.location
    text = str(report.longrepr)[-1500:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"\n::error file=stratlab/backend/{path},line={(line or 0) + 1},title={report.nodeid}::{text}")


@pytest.fixture(autouse=True)
def fresh_trackers():
    """The hour's list of who tracks which stock (app/results.py) doesn't carry over from one test to the next."""
    from app import results
    results.forget_trackers()
    yield
    results.forget_trackers()


@pytest.fixture(autouse=True)
def fresh_pulse_snapshots():
    """The market pulse's index levels and headlines are served from memory (app/intel/snapshot.py, R24-001): a test's
    levels don't carry over to the next test on the same worker."""
    routes = sys.modules.get("app.intel.routes")
    hub = getattr(routes, "hub", None) if routes else None
    if hub is not None and hasattr(hub, "forget_snapshots"):
        hub.forget_snapshots()
    yield
    hub = getattr(routes, "hub", None) if routes else None
    if hub is not None and hasattr(hub, "forget_snapshots"):
        hub.forget_snapshots()
