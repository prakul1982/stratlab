"""One fixed moment for the browser tests' fake world (CLOCK, owner 31 Oct: "the PR fails are a real issue").

The e2e world read the machine's clock, so the same commit passed on a Wednesday morning and failed on a Saturday (no
session today, the weekly brief first), in India's market hours (the chart's Live badge) or at a month's end. Now
tests/visual_server.py starts at E2E_NOW and its clock runs on from there (time-machine, ticking, so caches still
expire and asyncio's timers still fire): every date.today(), datetime.now() and time.time() the app reads, through
whichever helper, is that moment plus the seconds since the server started. Production never imports this.

    E2E_NOW unset      OPEN: Wed 28 Oct 2026, 11:00 IST: India mid-session, no holiday within two weeks
    E2E_NOW=closed     CLOSED: Sun 1 Nov 2026, 15:00 IST: every market shut, and a month's first day dated by
                       the last close in the month before (the net worth's two snapshots, R7O-013)
    E2E_NOW=<ISO>      that moment (a time zone is required)
    E2E_NOW=real       the machine's clock, as before

The browser runs at the same moment (frontend/e2e/fixtures.ts reads it from /e2e/now). Tests that check shut-market
behaviour ask for CLOSED: a second world, built at that moment on its own port (visual_server.closed_world).
The two moments are pinned equal to the frontend's in frontend/unit/review-clock.test.mjs.
"""
import os
import subprocess
import sys
from datetime import datetime

OPEN = "2026-10-28T11:00:00+05:30"
CLOSED = "2026-11-01T15:00:00+05:30"
NAMED = {"open": OPEN, "closed": CLOSED}


def moment(value: str | None = None) -> datetime | None:
    """The moment E2E_NOW names: None for the machine's clock."""
    v = (os.environ.get("E2E_NOW", "") if value is None else value).strip() or OPEN
    if v.lower() == "real":
        return None
    at = datetime.fromisoformat(NAMED.get(v.lower(), v))
    if at.tzinfo is None:
        raise SystemExit(f"E2E_NOW={v!r} needs a time zone, e.g. {OPEN}")
    return at


def _time_machine():
    try:
        import time_machine
    except ImportError:
        # every CI job installs it beside requirements.txt (tests.yml: backend, browser, ui-lint); production must not
        # carry a test library, so this is only the fallback for a local machine without it: fetch it once
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "time-machine>=2.16,<4"], check=True)
        import time_machine
    return time_machine


_travel = None


def start(value: str | None = None) -> datetime | None:
    """Move this process's clock to the moment (and let it run on). Called before the app is imported, so even the
    times its modules read as they load are the world's."""
    global _travel
    at = moment(value)
    if _travel is not None:
        _travel.stop()
        _travel = None
    if at is not None:
        _travel = _time_machine().travel(at, tick=True)
        _travel.start()
    return at
