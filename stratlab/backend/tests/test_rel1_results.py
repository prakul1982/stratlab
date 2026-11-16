"""rel1 item 4 (CX1 problem 9): filed results supersede an announced date. The results calendar listed Muthoot Microfin for Thu 19 Nov
after it had filed its September-quarter results on 5 Nov. A results meeting held after the quarter ended, with results filed since,
means a later date for that quarter on the exchange's list is not a results day; a meeting that was put off, and the next quarter's
meeting, stay."""
import json
from datetime import date, timedelta

from app import db, results as R
from tests.test_results import FakeIndia, meeting, notice, w  # noqa: F401  (the results tests' own fakes and world)

TODAY = date(2026, 11, 16)


def _past(sym, day):
    db.set_setting(R.PAST_KEY + "IN", json.dumps({"at": "2026-11-10T08:00+05:30", "rows": {sym: [day]}}))


def test_a_quarter_already_reported_has_no_later_results_day(w):
    _past("MFIN", "2026-11-05")
    india = FakeIndia([meeting("MFIN", date(2026, 11, 19)), meeting("OTHER", date(2026, 11, 19))],
                      {"MFIN": [notice("Financial Results", "Financial results for the quarter ended September 30, 2026", "2026-11-05T17:40",
                                       category="results")]})
    R.refresh("IN", {"in": india}, set(), TODAY)
    assert {r["symbol"] for r in R.load("IN")["rows"]} == {"OTHER"}
    assert R.lookup("IN", "MFIN", TODAY)["next"] is None


def test_a_meeting_that_was_put_off_keeps_its_new_date(w):
    _past("MFIN", "2026-11-05")                    # the 5 Nov meeting adjourned: no results filed since
    R.refresh("IN", {"in": FakeIndia([meeting("MFIN", date(2026, 11, 19))], {"MFIN": []})}, set(), TODAY)
    assert R.lookup("IN", "MFIN", TODAY)["next"]["date"] == "2026-11-19"


def test_the_next_quarters_meeting_stays():
    rows = [R.row("IN", "MFIN", date(2027, 1, 28), "Financial Results")]
    got = R.without_reported(rows, {"MFIN": ["2026-11-05"]}, TODAY, lambda s, d: True)
    assert got == rows                              # 28 Jan is after 31 Dec: the December quarter's meeting
    assert R.quarter_end_before(date(2026, 11, 19)) == date(2026, 9, 30) and R.quarter_end_before(date(2027, 1, 2)) == date(2026, 12, 31)
    assert R.without_reported([R.row("IN", "MFIN", date(2026, 11, 19), "Financial Results")], {"MFIN": ["2026-11-05"]}, TODAY) != []
