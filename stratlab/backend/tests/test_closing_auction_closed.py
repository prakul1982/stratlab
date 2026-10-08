"""The closing auction desk when the market is closed: the next auction window, and the last stored auction shown
instead of an empty page."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: I001  (first: the app loads the newsletter job before the modules built on it)
from app import closing_auction as CA, db
from tests import world as W

IST = timezone(timedelta(hours=5, minutes=30))
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|cheap|expensive|squeeze|will close)\b", re.I)
PRO = {"id": "u", "_plan": "pro"}


def ist(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=IST)


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    CA.forget()


def test_the_next_window_is_today_until_the_auction_ends_then_the_next_trading_day(w):
    assert CA.next_window(ist(2026, 10, 5, 10, 0), True, "before") == {"day": "2026-10-05", "today": True, "from": "15:15", "to": "15:35"}
    after = CA.next_window(ist(2026, 10, 5, 16, 0), True, "closed")                       # Monday evening: Tuesday
    assert after == {"day": "2026-10-06", "today": False, "from": "15:15", "to": "15:35"}
    fri = CA.next_window(ist(2026, 10, 9, 16, 0), True, "closed")                         # Friday evening: the Monday after
    assert fri["day"] == "2026-10-12" and not fri["today"]
    sat = CA.next_window(ist(2026, 10, 10, 11, 0), False, "holiday")                      # a Saturday: the same Monday
    assert sat["day"] == "2026-10-12" and date(2026, 10, 12).weekday() == 0


def test_with_nothing_read_the_page_shows_the_last_stored_auction(w):
    day = "2026-10-05"
    db.set_setting(CA.DAY_KEY + day, json.dumps({"stocks": {"TCS": [4000.0, 3952.0, 120000], "INFY": [1500.0, 1500.0, 90000]},
                                                 "indices": {"NIFTY 50": [25000.0, 25075.0]}}))
    CA.forget()
    v = CA.view(PRO, ist(2026, 10, 10, 11, 0).astimezone(timezone.utc))                   # a Saturday, nothing read
    assert v["phase"] == "holiday" and v["from_stored"] is True and v["day"] == day and v["fresh"] is False
    assert [s["symbol"] for s in v["stocks"]] == ["TCS", "INFY"]                          # the widest gap first
    tcs = v["stocks"][0]
    assert tcs["final_out"] and tcs["gap"] == -1.2 and tcs["ref"] == 4000.0 and tcs["final_qty"] == 120000
    assert v["indices"][0]["name"] == "NIFTY 50" and v["indices"][0]["value"] == 25075.0 and v["indices"][0]["close_gap"] == 0.3
    assert v["next"]["day"] == "2026-10-12" and (v["next"]["from"], v["next"]["to"]) == ("15:15", "15:35")
    assert not PROVIDERS.search(json.dumps({k: x for k, x in v.items() if k != "sources"})) and not ADVICE.search(json.dumps(v["next"]))


def test_with_no_stored_day_either_the_page_still_names_the_next_window(w):
    CA.forget()
    v = CA.view(PRO, ist(2026, 10, 5, 20, 0).astimezone(timezone.utc))
    assert v["stocks"] == [] and v["from_stored"] is False and v["next"]["day"] == "2026-10-06"


def test_before_the_market_opens_is_not_continuous_trading(w):
    def phase(h, mi):
        return CA.view(PRO, ist(2026, 10, 5, h, mi).astimezone(timezone.utc))["phase"]
    assert phase(3, 30) == "preopen" and phase(9, 14) == "preopen"                          # a trading day, before 09:15
    assert phase(9, 15) == "before" and phase(15, 14) == "before"                           # continuous trading
    assert phase(16, 0) == "closed"
    v = CA.view(PRO, ist(2026, 10, 5, 3, 30).astimezone(timezone.utc))
    assert v["next"] == {"day": "2026-10-05", "today": True, "from": "15:15", "to": "15:35"}  # the auction later today
