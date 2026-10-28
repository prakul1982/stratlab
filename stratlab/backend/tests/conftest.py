import os
import sys

os.environ.setdefault("BACKTEST_PROCESSES", "0")      # backtests in the test process, where fakes are patched in
os.environ["AI_AUTO_PROBE"] = "0"                     # no background AI model measuring (it would use the network)
os.environ["OFFICIAL_CLOSE_FETCH"] = "0"               # no exchange file or broker read for official closes (app/official_close.py)

import pytest


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
    fake_prices.FROZEN = datetime.now(timezone.utc)
    yield
    fake_prices.FROZEN = None


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
