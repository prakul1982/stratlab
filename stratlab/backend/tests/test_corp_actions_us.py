"""US corporate actions for the whole universe: the S&P 500 and StratLab's own groups read one company at a time from
the price histories (past ex-dates only), stored in the calendar, the page's list for every company, and the daily job."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app import corp_actions as C, db, universes
from app.intel.net import SourceError
from tests.test_corp_actions import FakeUS, TODAY, w  # noqa: F401  (w is a fixture)

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|best|cheap|expensive|bullish|bearish|target|should|recommend)\b", re.I)


def div(days_ago, amount=0.5):
    return {"date": (TODAY - timedelta(days=days_ago)).isoformat(), "amount": amount}


def split(days_ago, num=4, den=1):
    return {"date": (TODAY - timedelta(days=days_ago)).isoformat(), "numerator": num, "denominator": den}


EVENTS = {
    "AAPL": {"dividends": [div(3, 0.26), div(95, 0.25)], "splits": []},
    "MSFT": {"dividends": [div(20, 0.83)], "splits": []},
    "NVDA": {"dividends": [], "splits": [split(10, 10, 1)]},
    "KO": {"dividends": [div(200, 0.5)], "splits": []},                    # long ago: in the history, not in the calendar
    "XOM": {"dividends": [], "splits": []},
}


def sleeps():
    got = []
    return got, got.append


def test_the_universe_is_the_sp500_the_groups_and_what_people_track():
    u = C.us_universe({"zzzz", "AAPL"})
    assert "ZZZZ" in u and "AAPL" in u and "BRK-B" in u and len(u) == len(set(u)) and len(u) >= 500
    assert u == sorted(u) and set(universes.sp500_symbols()) <= set(u)


def test_whole_universe_read_stores_recent_dividends_and_splits_with_names(w):
    waits, sleep = sleeps()
    out = C.refresh_universe({"us": FakeUS(EVENTS)}, today=TODAY, symbols=list(EVENTS), pace=0.5, sleep=sleep)
    assert out["read"] == 5 and out["failed"] == 0 and out["rows"] == 3                       # the calendar's window holds AAPL's, MSFT's and NVDA's; AAPL's older one and KO's are history only
    assert waits == [0.5] * 4                                                                  # a pause between companies, not before the first
    cal = C.load("US")
    assert cal["universe"] == 5 and cal["universe_at"] and cal["at"]
    by = {(r["symbol"], r["kind"]): r for r in cal["rows"]}
    assert set(by) == {("AAPL", "dividend"), ("MSFT", "dividend"), ("NVDA", "split")}
    assert by[("AAPL", "dividend")]["name"] == "Apple Inc." and by[("AAPL", "dividend")]["currency"] == "USD" and by[("AAPL", "dividend")]["amount"] == 0.26
    assert by[("NVDA", "split")]["text"] == "Split 10-for-1" and by[("NVDA", "split")]["ex_date"] == (TODAY - timedelta(days=10)).isoformat()
    assert C.hist_load("US", "KO")["rows"][0]["amount"] == 0.5 and len(C.hist_load("US", "AAPL")["rows"]) == 2   # each company's history is kept too


def test_a_company_that_fails_keeps_its_old_rows_and_a_busy_source_stops_the_read(w):
    C.refresh_universe({"us": FakeUS(EVENTS)}, today=TODAY, symbols=["AAPL", "MSFT"], pace=0, sleep=lambda s: None)
    before = {r["symbol"] for r in C.load("US")["rows"]}
    assert before == {"AAPL", "MSFT"}

    class Flaky(FakeUS):
        def events(self, symbol, days=1100):
            if symbol == "MSFT":
                raise SourceError("prices", "no history")
            return super().events(symbol, days)
    out = C.refresh_universe({"us": Flaky(EVENTS)}, today=TODAY, symbols=["AAPL", "MSFT", "NVDA"], pace=0, sleep=lambda s: None)
    assert out["read"] == 2 and out["failed"] == 1 and out["problems"][0].startswith("MSFT")
    assert {r["symbol"] for r in C.load("US")["rows"]} == {"AAPL", "MSFT", "NVDA"}              # MSFT's earlier row stands
    assert C.load("US")["universe"] == 2

    asked = []

    class Busy(FakeUS):
        def events(self, symbol, days=1100):
            asked.append(symbol)
            raise SourceError("prices", "busy", busy=True)
    syms = [f"S{i}" for i in range(20)]
    stored = C.load("US")
    out = C.refresh_universe({"us": Busy()}, today=TODAY, symbols=syms, pace=0, sleep=lambda s: None)
    assert out["rows"] is None and out["read"] == 0 and len(asked) == C.UNIVERSE_GIVE_UP        # it stopped, rather than ask every company
    assert C.load("US") == stored


def test_the_page_lists_every_company_for_four_weeks_back_and_says_nothing_is_ahead(w):
    C.refresh_universe({"us": FakeUS(EVENTS)}, today=TODAY, symbols=list(EVENTS), pace=0, sleep=lambda s: None)
    v = C.view("US", "u-nobody", scope="all", today=TODAY)
    assert v["ahead"] == [] and v["ahead_known"] is False and v["recent_days"] == 28
    assert [r["symbol"] for r in v["recent"]] == ["AAPL", "NVDA", "MSFT"]                      # newest ex-date first; MSFT's 20 days ago is inside the 28
    assert v["universe"]["companies"] == 5 and v["universe"]["updated_at"]
    assert [r["symbol"] for r in C.view("US", "u-nobody", scope="all", q="micro", today=TODAY)["recent"]] == ["MSFT"]      # found by company name
    assert [r["kind"] for r in C.view("US", "u-nobody", scope="all", kind="split", today=TODAY)["recent"]] == ["split"]
    assert C.view("US", "u-nobody", scope="mine", today=TODAY)["recent"] == []
    ind = C.view("IN", "u-nobody", scope="all", today=TODAY)
    assert ind["recent_days"] == C.RECENT_DAYS and ind["universe"] is None
    assert not PROVIDERS.search(json.dumps(v)) and not ADVICE.search(json.dumps(v))


def test_saving_the_tracked_refresh_keeps_the_universe_facts(w):
    C.refresh_universe({"us": FakeUS(EVENTS)}, today=TODAY, symbols=["AAPL", "MSFT"], pace=0, sleep=lambda s: None)
    at = C.load("US")["universe_at"]
    C.refresh("US", {"us": FakeUS(EVENTS)}, {"AAPL"}, TODAY)
    assert C.load("US")["universe_at"] == at and C.load("US")["universe"] == 2
    assert {r["symbol"] for r in C.load("US")["rows"]} == {"AAPL", "MSFT"}                     # the tracked refresh leaves the others' rows alone


def test_the_job_reads_the_universe_at_the_first_chance_then_once_a_day(w, monkeypatch):
    job = C.Job(lambda: {"us": FakeUS(EVENTS), "in": None})
    monkeypatch.setattr(C, "us_universe", lambda tracked=(): list(EVENTS))
    monkeypatch.setattr(C, "UNIVERSE_PACE", 0)
    now = datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc)                              # 04:00 New York: before 06:20
    assert C.load("US").get("universe_at") is None and job._universe_due(now)           # never read: due at once, any hour
    job.start_universe({}, TODAY, wait=True)
    assert C.load("US")["universe"] == 5 and job.status["universe"]["read"] == 5 and not job.universe_running
    assert not job._universe_due(now)                                                    # read; not due again before tomorrow's 06:20
    after = datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc)                           # 07:00 New York next day
    assert job._universe_due(after) and not job._universe_due(after + timedelta(minutes=5))      # once, then marked


def test_a_failed_first_read_waits_half_an_hour(w, monkeypatch):
    class Down(FakeUS):
        def events(self, symbol, days=1100):
            raise SourceError("prices", "down", busy=True)
    monkeypatch.setattr(C, "us_universe", lambda tracked=(): ["AAPL", "MSFT"])
    job = C.Job(lambda: {"us": Down(), "in": None})
    job.start_universe({}, TODAY, wait=True)
    assert job.universe_retry > 0 and not job._universe_due(datetime(2026, 10, 5, 8, 0, tzinfo=timezone.utc))
    assert C.load("US").get("universe_at") is None


def test_admin_can_start_the_universe_read(w, monkeypatch):
    from fastapi.testclient import TestClient
    from app import admin, main
    started = []
    monkeypatch.setattr(main.corp_job, "start_universe", lambda who, day=None, wait=False: started.append(True))
    monkeypatch.setattr(main.corp_job, "refresh", lambda region, who=None, day=None: {"rows": 0, "fresh": 0, "problems": []})
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "admin", "role": "admin"}
    try:
        c = TestClient(main.app)
        assert "universe_started" not in c.post("/admin/corp-actions/refresh").json()
        assert c.post("/admin/corp-actions/refresh?universe=true").json()["universe_started"] is True and started == [True]
    finally:
        main.app.dependency_overrides.pop(admin.admin_profile, None)
