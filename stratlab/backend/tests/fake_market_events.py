"""Market events made up around today, for the fake world's browser tests (the unit tests read the real samples in
fixtures/market_events): an MPC decision three days ahead and one two months back with its repo rate, a Fed
decision ahead and one behind with its target range, US CPI and jobs dates, India CPI out last month with its figure
and the next one ahead, and index changes taking effect in a week (RELIANCE into the Nifty 100, TCS out of it)."""
import json
from datetime import date, timedelta


def state(today: date | None = None) -> dict:
    t = today or date.today()
    from tests.fake_prices import on_trading_day
    d = lambda n: (t + timedelta(days=n)).isoformat()  # noqa: E731
    # the events are on trading days (the exchanges' and the Fed's and statistics offices' calendars have no weekends)
    i = lambda n: on_trading_day(t + timedelta(days=n), "IN", n < 0).isoformat()  # noqa: E731
    u = lambda n: on_trading_day(t + timedelta(days=n), "US", n < 0).isoformat()  # noqa: E731
    return {
        "rbi": {"meetings": [
            {"start": i(-62), "end": i(-60), "decided": i(-60), "repo": 5.25, "move": "unchanged", "minutes": i(-46),
             "statement_url": "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx?prid=1"},
            {"start": i(1), "end": i(3)}], "as_of": d(0), "checked": d(0) + "T07:20"},
        "fed": {"meetings": [
            {"start": u(-20), "end": u(-19), "sep": True, "low": 3.75, "high": 4.0, "move": "raised",
             "statement_url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary1a.htm"},
            {"start": u(22), "end": u(23), "sep": False}], "as_of": d(0), "checked": d(0) + "T07:20"},
        "us_data": {"releases": [{"kind": "us_jobs", "date": u(-3), "time": "08:30"}, {"kind": "us_cpi", "date": u(9), "time": "08:30"},
                                 {"kind": "us_jobs", "date": u(32), "time": "08:30"}], "as_of": d(0), "checked": d(0) + "T07:20"},
        "india_data": {"calendar": [{"kind": "cpi", "title": "All India Consumer Price Index (CPI)", "date": i(-21), "released": i(-21)},
                                    {"kind": "iip", "title": "All India Index of Industrial Production (IIP)", "date": i(5), "released": None},
                                    {"kind": "cpi", "title": "All India Consumer Price Index (CPI)", "date": i(9), "released": None}],
                       "figures": [{"id": "cpi:" + i(-21), "kind": "cpi", "date": i(-21), "pdf": "https://www.mospi.gov.in/uploads/cpi.pdf",
                                    "figure": {"label": "CPI inflation", "value": 4.82, "period": "last month", "previous": 4.45,
                                               "previous_label": "the month before"}}],
                       "releases": [], "as_of": d(0), "checked": d(0) + "T07:20"},
        "index": {"changes": [{"id": "fakechange01", "url": "https://www.niftyindices.com/Press_Release/x.pdf",
                               "title": "Replacements in indices", "announced": i(-14), "effective": i(7),
                               "sections": [{"index": "Nifty 100", "in": [["RELIANCE", "Reliance Industries Ltd."]],
                                             "out": [["TCS", "Tata Consultancy Services Ltd."]]},
                                            {"index": "Nifty Midcap 150", "in": [["TCS", "Tata Consultancy Services Ltd."]], "out": []}]}],
                  "as_of": d(0), "checked": d(0) + "T07:20"},
        "last_run": d(0) + "T07:20",
    }


def seed(today: date | None = None):
    from app import db, market_events
    db.set_setting(market_events.KEY, json.dumps(state(today)))
    market_events._cache.clear()
