import os
import sys

os.environ.setdefault("BACKTEST_PROCESSES", "0")      # backtests in the test process, where fakes are patched in

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


def pytest_runtest_logreport(report):
    """On GitHub, each failing test also becomes an annotation on the pull request, readable without the job log."""
    if not (report.failed and os.environ.get("GITHUB_ACTIONS")):
        return
    path, line, _ = report.location
    text = str(report.longrepr)[-1500:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")
    print(f"\n::error file=stratlab/backend/{path},line={(line or 0) + 1},title={report.nodeid}::{text}")
