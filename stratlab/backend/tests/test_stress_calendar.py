"""Stress: the whole app at the moments that trip trading apps up. Exchange holidays (including one on the weekly
expiry day), the minutes around market open, close and an expiry, just after midnight in India (when the server's
UTC date is still yesterday), the broker's 6 am token reset, a weekend, year end, the US and UK clock changes, and the
day past the end of the known holiday calendar. At each, every page and action runs and the background jobs tick."""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

time_machine = pytest.importorskip("time_machine")

from app import main  # noqa: E402
from app.data import calendar  # noqa: E402
from tests import world  # noqa: E402
from tests.test_stress_failures import run_all  # noqa: E402
from tests.test_stress_fuzz import seed  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
MOMENTS = {
    "holiday on the weekly expiry (Tue 20 Oct 2026)": datetime(2026, 10, 20, 11, 0, tzinfo=IST),
    "the day before, the moved expiry (Mon 19 Oct)": datetime(2026, 10, 19, 15, 29, tzinfo=IST),
    "expiry day, a minute after the close": datetime(2026, 10, 13, 15, 31, tzinfo=IST),
    "1 am India time, UTC still yesterday": datetime(2026, 10, 14, 1, 0, tzinfo=IST),
    "5:59 am, before the broker token reset": datetime(2026, 10, 14, 5, 59, tzinfo=IST),
    "6:01 am, after it": datetime(2026, 10, 14, 6, 1, tzinfo=IST),
    "a minute before the open": datetime(2026, 10, 14, 9, 14, tzinfo=IST),
    "the open": datetime(2026, 10, 14, 9, 15, 30, tzinfo=IST),
    "Saturday noon": datetime(2026, 10, 17, 12, 0, tzinfo=IST),
    "Diwali, Sunday": datetime(2026, 11, 8, 18, 30, tzinfo=IST),
    "US clocks just went back": datetime(2026, 11, 2, 20, 30, tzinfo=IST),
    "UK clocks just went back": datetime(2026, 10, 26, 13, 30, tzinfo=IST),
    "MCX late session": datetime(2026, 10, 14, 23, 40, tzinfo=IST),
    "year end, a minute to midnight": datetime(2026, 12, 31, 23, 59, tzinfo=IST),
    "new year, past the known calendar": datetime(2027, 1, 1, 0, 1, tzinfo=IST),
    "Republic Day 2027, a Tuesday past the known calendar": datetime(2027, 1, 26, 10, 0, tzinfo=IST),
}


@pytest.fixture(params=list(MOMENTS), ids=list(MOMENTS))
def at(request, monkeypatch):
    # given in UTC, so the machine's own zone stays UTC like the live server's (a zone-aware India time would also
    # switch the process to India time and hide "today" bugs)
    with time_machine.travel(MOMENTS[request.param].astimezone(timezone.utc), tick=True):
        w = world.build(monkeypatch, real_clock=True)
        w["moment"] = request.param
        yield w
        w["close"]()


def test_everything_works_at_this_moment(at):
    w = at
    ctx = seed(w)
    problems = []
    run_all(w, ctx, w["moment"], problems)
    m = w["manager"]
    m._last_persist = m._last_plan = 0.0                   # what the background loop sets before its first tick
    m._tick()                                              # paper sessions' timers, at this moment
    for job in (getattr(main, "scan_alerts_job", None), getattr(main, "filing_alerts_job", None)):
        if job is not None and hasattr(job, "tick"):
            try:
                job.tick(datetime.now(IST))
            except Exception as e:                         # background jobs log and carry on; they must not raise
                problems.append(f"{job.__class__.__name__} raised {e!r}")
    assert not problems, "\n".join(dict.fromkeys(problems))
    today = datetime.now(IST).date().isoformat()
    chain = w["client"].get("/options/chain", headers=world.headers("pro-token"),
                            params={"exchange": "NFO", "underlying": "NIFTY"}).json()
    if "expiry" in chain:
        assert chain["expiry"] >= today, f"offered an expiry that has passed: {chain['expiry']} on {today}"
        assert all(e >= today for e in chain["expiries"])
        for e in chain["expiries"]:
            assert calendar.is_trading_day("IN", date.fromisoformat(e)), f"expiry on a closed day: {e}"


def test_the_calendar_doesnt_run_out():
    """Past the installed calendar (it ends with 2026), India's fixed national holidays still close the market."""
    assert not calendar.is_trading_day("IN", date(2027, 1, 26))          # Republic Day, a Tuesday
    assert not calendar.is_trading_day("IN", date(2028, 5, 1))           # Maharashtra Day, a Monday
    assert not calendar.is_trading_day("MCX", date(2028, 8, 15))         # Independence Day, a Tuesday
    assert calendar.is_trading_day("IN", date(2027, 1, 27))
    assert calendar.is_trading_day("US", date(2027, 1, 26))              # India's holidays don't close New York


def test_pasted_exchange_holidays_close_those_days(monkeypatch):
    store = {}
    monkeypatch.setattr(main.db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(main.db, "get_setting", lambda k: store.get(k))
    calendar._extra.clear()
    days = main.parse_holidays("Holi 22-Mar-2027 Monday\nGood Friday 26/03/2027\nbad 31-Feb-2027")
    calendar.set_extra_holidays("IN", days)
    assert not calendar.is_trading_day("IN", date(2027, 3, 22)) and not calendar.is_trading_day("MCX", date(2027, 3, 26))
    assert calendar.is_trading_day("IN", date(2027, 3, 23))
    calendar._extra.clear()


def test_the_exchanges_holiday_list_is_read_by_itself(monkeypatch):
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        calendar._extra.clear()
        assert calendar.is_trading_day("IN", date(2027, 3, 22))              # Holi 2027: not known yet
        r = w["client"].post("/admin/holidays/refresh", headers=W.headers("admin-token")).json()
        assert r["auto"]["count"] == 2 and r["auto"]["error"] is None and r["covered_until"] >= "2027-12-31"
        assert [m["market"] for m in r["markets"]][:3] == ["IN", "MCX", "CDS"] and r["markets"][0]["known_until"] >= "2027-12-31"
        assert not calendar.is_trading_day("IN", date(2027, 3, 22)) and not calendar.is_trading_day("MCX", date(2027, 3, 22))
        w["faults"]["exchange"].mode = "down"                               # the exchange down: the last good list stays
        r = w["client"].post("/admin/holidays/refresh", headers=W.headers("admin-token")).json()
        assert r["auto"]["count"] == 2 and r["auto"]["error"]
        assert not calendar.is_trading_day("IN", date(2027, 3, 22))
        assert w["client"].post("/admin/holidays/refresh", headers=W.headers("pro-token")).status_code == 403
    finally:
        calendar._extra.clear()
        w["close"]()
