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


# ---------- item 7 (CX1 problems 8 and 9): peers of a like size, with the rule said ----------
def test_peers_are_of_a_like_size_and_the_rule_is_said():
    from app import company_tables as T
    rows = [{"symbol": "BIG", "industry": "Refineries", "sector": "Energy", "market_cap": 1819000.0},
            *[{"symbol": s, "industry": "Refineries", "sector": "Energy", "market_cap": c}
              for s, c in (("IOC", 200000.0), ("BPCL", 140000.0), ("HPCL", 92000.0), ("MRPL", 25000.0), ("MICRO1", 498.0), ("MICRO2", 74.0), ("NOCAP", None))]]
    own, peers, basis = T.peer_set(rows, "BIG")
    assert basis == "industry" and [p["symbol"] for p in peers] == ["IOC", "BPCL", "HPCL"]     # ₹25,000 cr and the micro-caps are out
    v = T.peers_view("IN", "BIG", rows, None, {"full": True, "export": True})
    assert v["median"]["market_cap"] == 140000 and "between 1/20 of its own and 20 times it" in v["basis_words"]
    # a small company's peers are small ones
    _, small, _ = T.peer_set(rows, "MICRO1")
    assert [p["symbol"] for p in small] == ["MICRO2"]


# ---------- LIVE9A-017: the sector chart from the copy kept at the close; a busy benchmark said once, in plain words ----------
def test_the_sector_chart_is_served_from_the_copy_kept_at_the_close(monkeypatch):
    import json as _json
    from datetime import date as _date
    from fastapi.testclient import TestClient
    from app import db as _db, main
    from tests.fake_db import FakeSupabase
    monkeypatch.setattr(_db, "_client", FakeSupabase())

    class Prov:
        def ready(self):
            return True
    monkeypatch.setattr(main.markets, "provider", lambda r: Prov())
    monkeypatch.setattr(main.stock_pages, "last_close", lambda r, now=None: (_date(2026, 11, 16), None))
    monkeypatch.setattr(main, "heavy_read_throttle", lambda p: None)
    ran = []
    monkeypatch.setattr(main.rotation, "run", lambda *a, **k: ran.append(a) or {"rows": [{"points": [{"t": "2026-11-16"}]}], "skipped": [],
                                                                             "as_of": "2026-11-16", "v": main.rotation.VERSION})
    main._results.clear()
    _db.set_setting("rotation:last:IN:sectors:weekly:5", _json.dumps({"name": "NSE sector indices", "market": "IN", "rows": [{"kept": 1}],
                                                                      "skipped": [], "as_of": "2026-11-16", "v": main.rotation.VERSION}))
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "plan": "pro", "_plan": "pro"}
    try:
        v = TestClient(main.app).get("/research/rotation?region=IN").json()
        assert v["rows"] == [{"kept": 1}] and ran == []                       # no member's prices read again
        main._results.clear()
        _db.set_setting("rotation:last:IN:sectors:weekly:5", _json.dumps({"rows": [{"kept": 1}], "as_of": "2026-11-13", "v": main.rotation.VERSION}))
        v = TestClient(main.app).get("/research/rotation?region=IN").json()
        assert len(ran) == 1 and v["as_of"] == "2026-11-16"                   # a copy a session behind is worked out again
    finally:
        main.app.dependency_overrides.clear()
        main._results.clear()


def test_a_busy_benchmark_is_said_once_in_plain_words():
    import pytest
    from app import rotation
    from app.intel.net import SourceError

    class Reg:
        def provider(self, m):
            return None

    def load(iid, days):
        raise SourceError("Yahoo Finance", "the market data source is busy (our rate limit). Try again in a minute.", busy=True)
    with pytest.raises(LookupError) as e:
        rotation.compute(Reg(), "US", [], "weekly", 5, load, bench=("x", "SPY"))
    msg = str(e.value)
    assert msg == "The benchmark's prices couldn't be read just now: the market data source is busy. Try again in a minute."
    assert msg.count("Try again") == 1 and "rate limit" not in msg
