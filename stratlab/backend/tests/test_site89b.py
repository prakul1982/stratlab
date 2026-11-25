"""Release 89 site items (lane site89b): the US results calendar's duplicate rows, the Results page's "Usual move", the US heatmap and
sector rotation against India's, server paging for the corporate actions and earnings calls lists, and honest coverage counts."""
import json
from datetime import date

import pytest

from app import db, results as R
from app.intel import us_calendar
from tests import world


@pytest.fixture
def w(monkeypatch):
    world_ = world.build(monkeypatch)
    yield world_
    world_["close"]()


# ---------- 1. the US results calendar: one row per company per results ----------
class CompanyData:
    """The US company data's whole-market list (its fiscal quarters, no session for most)."""

    def __init__(self, rows):
        self.rows = rows

    def earnings_between(self, frm, to, ttl=3600):
        return [r for r in self.rows if frm.isoformat() <= r["date"] <= to.isoformat()]

    def earnings_calendar(self, sym):
        return []


class MarketCalendar:
    """The US market calendar, a day at a time (its quarter-end month, the session)."""

    def __init__(self, days: dict):
        self.days = days

    def earnings(self, d):
        return us_calendar.earnings_rows({"data": {"rows": self.days.get(d.isoformat(), [])}}, d)


TODAY_US = date(2026, 11, 25)                 # a Wednesday, as on the live site when the duplicates were seen


def live_like_sources():
    """The answers of 23-27 Nov 2026 as the live calendar had them: Burlington dated Mon 23 by the company data and Tue 24 (before the
    open) by the market calendar; Chagee and Nordic American on Thanksgiving by one and Fri 27 by the other; CrowdStrike on the calendar on
    two days for the same quarter; ABLT given two different fiscal quarters by the company data (two results, both kept)."""
    data = CompanyData([
        {"symbol": "BURL", "date": "2026-11-23", "quarter": 3, "year": 2027},
        {"symbol": "CHA", "date": "2026-11-26", "quarter": 3, "year": 2026},
        {"symbol": "NAT", "date": "2026-11-26", "hour": "bmo", "quarter": 3, "year": 2026},
        {"symbol": "ABLT", "date": "2026-11-23", "quarter": 3, "year": 2026},
        {"symbol": "ABLT", "date": "2026-12-01", "quarter": 1, "year": 2026},
        {"symbol": "DE", "date": "2026-11-25", "hour": "bmo", "quarter": 4, "year": 2026},
    ])
    cal = MarketCalendar({
        "2026-11-23": [{"symbol": "CRWD", "name": "CrowdStrike Holdings, Inc.", "time": "time-not-supplied", "fiscalQuarterEnding": "Oct/2026"}],
        "2026-11-24": [{"symbol": "BURL", "name": "Burlington Stores, Inc.", "time": "time-pre-market", "fiscalQuarterEnding": "Oct/2026"}],
        "2026-11-27": [{"symbol": "CHA", "name": "Chagee Holdings Limited", "time": "time-not-supplied", "fiscalQuarterEnding": "Sep/2026"},
                       {"symbol": "NAT", "name": "Nordic American Tankers Limited", "time": "time-not-supplied", "fiscalQuarterEnding": "Sep/2026"}],
        "2026-12-01": [{"symbol": "CRWD", "name": "CrowdStrike Holdings, Inc.", "time": "time-after-hours", "fiscalQuarterEnding": "Oct/2026"}],
    })
    return {"us": data, "cal": cal, "sec": None}


def test_the_us_calendar_lists_each_company_once_per_results(w):
    R.refresh("US", live_like_sources(), set(), TODAY_US)
    rows = R.load("US")["rows"]
    by: dict = {}
    for r in rows:
        by.setdefault(r["symbol"], []).append(r)
    assert [r["date"] for r in by["BURL"]] == ["2026-11-24"]                  # the calendar's day, with its session
    assert by["BURL"][0]["when"] == "before the open"
    assert [r["date"] for r in by["CHA"]] == ["2026-11-27"] and [r["date"] for r in by["NAT"]] == ["2026-11-27"]
    assert by["NAT"][0]["when"] == "before the open"                          # the company data's session carries over
    assert len(by["CRWD"]) == 1                                               # one quarter (Oct 2026) on two calendar days: one row
    assert sorted(r["date"] for r in by["ABLT"]) == ["2026-11-23", "2026-12-01"]   # two different quarters stay two rows
    assert len(by["DE"]) == 1
    # the page's answer, every company, day by day: nobody twice in the two weeks
    v = R.view("US", "u-pro", "all", today=TODAY_US, limit=50)
    shown = [r["symbol"] for wk in v["weeks"] for r in wk["rows"]]
    assert sorted(s for s in shown if s != "ABLT") == sorted(set(s for s in shown if s != "ABLT"))
    # the earnings calls list (US: the results calendar's rows) has each company once too
    from app import concalls
    calls = [r["symbol"] for r in concalls.us_rows(date(2026, 11, 23), date(2026, 12, 6)) if r["symbol"] != "ABLT"]
    assert sorted(calls) == sorted(set(calls)) and "CHA" in calls
    # the days gone by kept for the usual move: Burlington's results day once, on the calendar's day
    assert R.load_past("US")["rows"].get("BURL") is None or R.load_past("US")["rows"]["BURL"] == ["2026-11-24"]


def test_a_stored_us_calendar_with_both_dates_is_served_once(w):
    """The list stored before the fix (both rows) is served with one row per results at once, without waiting for the next refresh; what
    the dropped row learnt (the filing, who was told) stays on the kept one."""
    out = {"at": "2026-11-24", "title": "Earnings release (8-K)", "url": "https://www.sec.gov/x.htm", "numbers": []}
    stored = [R.row("US", "BURL", date(2026, 11, 23), "Quarterly results (fiscal Q3 2027)", src="company data", period="Q3 2027"),
              R.row("US", "BURL", date(2026, 11, 24), "Quarterly results (quarter ended Oct 2026)", when="before the open",
                    src="market calendar", period="Oct 2026")]
    stored[0].update(out=out, told=True)
    stored[1].update(out=out, told=False)
    db.set_setting(R.KEY + "US", json.dumps({"at": "2026-11-24T06:00", "v": R.CAL_VERSION, "rows": stored}))
    rows = R.load("US")["rows"]
    assert len(rows) == 1 and rows[0]["date"] == "2026-11-24" and rows[0]["when"] == "before the open"
    assert rows[0]["told"] is True                                            # already told under the other date: not told again
    # India's rows are left as they are
    db.set_setting(R.KEY + "IN", json.dumps({"at": "x", "v": R.CAL_VERSION, "rows": [
        R.row("IN", "TCS", date(2026, 11, 23), "Financial Results"), R.row("IN", "TCS", date(2026, 11, 26), "Financial Results")]}))
    assert len(R.load("IN")["rows"]) == 2
