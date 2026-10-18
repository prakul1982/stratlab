"""Round 59 (19 Oct 2026): plan views, emails and Safari — the backend side, each on the reviewer's own example."""
from datetime import date, datetime, timezone

import pytest

from app import db, library, rules_watch as W
from app.engine import verdict as V
from tests.fake_db import FakeSupabase
from tests.test_rules import GOOD, FakeFetch


@pytest.fixture
def fdb(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(db, "_client", fake)
    return fake


def test_a_losing_run_says_after_costs_once():
    # R59-008: "5.3 points behind buy and hold after costs; lost money after costs."
    h = V.fact_headline("no_edge", [], 40, -10.8, -5.5)
    assert h == "5.3 points behind buy and hold; lost money after costs."
    assert h.count("after costs") == 1
    checks = [{"id": i, "status": "pass"} for i in ("luck", "costs", "unseen")] + [{"id": "nearby", "status": "skip"}]
    assert V.fact_headline("edge", checks, 40, 30.0, 10.0) == "20.0 points ahead of buy and hold after costs; 3 of 4 checks run · all 3 passed."


def test_the_checks_count_has_one_wording_everywhere():
    # R59-011: "3 of 4 checks run · all 3 passed" beside "Passed 2 of the 3 checks run" on the next card
    two = [{"id": "luck", "status": "pass"}, {"id": "costs", "status": "warn"}, {"id": "unseen", "status": "pass"}, {"id": "nearby", "status": "skip"}]
    assert V.fact_label("edge", two, 40) == "3 of 4 checks run · 2 passed"
    three = [{**c, "status": "pass"} if c["status"] == "warn" else c for c in two]
    assert V.fact_label("edge", three, 40) == "3 of 4 checks run · all 3 passed"


TODAY, NOW = date(2026, 10, 17), datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)


def test_one_circular_sent_twice_with_different_ids_is_alerted_once(fdb):
    # R59-002: "5 rate or rule changes at the source" over two circulars, the closing-auction one four times
    W.run(FakeFetch(GOOD), TODAY, NOW)
    sub = "Changes in market timings for the Closing Auction Session"
    copies = [{"cirDate": "20261016", "cirDisplayDate": "October 16, 2026", "sub": sub, "circFilelink": "https://x/CMTR76963.zip"},
              {"cirDisplayDate": "October 16, 2026", "cirDate": "20261016", "sub": sub, "circFilelink": "https://x/CMPT76951.zip"}]
    assert len({c["id"] for c in W.read_circulars({"data": copies})}) == 2          # the ids differ, as the exchange's did
    more = {**GOOD, "nse_circulars": {"data": GOOD["nse_circulars"]["data"] + copies + copies}}
    lines = W.run(FakeFetch(more), TODAY, NOW)
    assert len(lines) == 1 and sub in lines[0]
    subject, body = W.alert_text(lines)
    assert subject == "StratLab: 1 rate or rule change at the source"
    assert "Admin → Quality → Rates and rules" in body and "Data checks" not in body
    assert "(" not in lines[0]                       # the address after a dash, never in brackets
