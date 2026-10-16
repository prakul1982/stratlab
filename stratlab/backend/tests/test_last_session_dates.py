"""R41A: on a day the market does not trade (a weekend, a holiday) the pages name the last trading session instead of
today, and say nothing that reads as a fault or an empty day. Every test runs on a fake clock (time_machine), so none
depends on the real day of the week."""
from datetime import date, datetime, timedelta, timezone

import pytest
import time_machine

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app import last_session, risk

UTC = timezone.utc
SATURDAY = datetime(2026, 10, 17, 4, 0, tzinfo=UTC)         # Saturday 17 Oct 2026, 09:30 IST
FRIDAY = datetime(2026, 10, 16, 5, 0, tzinfo=UTC)           # Friday 16 Oct 2026, 10:30 IST, the market open
MONDAY_EARLY = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)     # Monday 19 Oct, 06:30 IST, before the open


# ---------- the one rule ----------
def test_on_or_before_names_the_last_trading_day():
    assert last_session.on_or_before("IN", date(2026, 10, 17)) == date(2026, 10, 16)      # Saturday
    assert last_session.on_or_before("IN", date(2026, 10, 18)) == date(2026, 10, 16)      # Sunday
    assert last_session.on_or_before("IN", date(2026, 10, 16)) == date(2026, 10, 16)      # a trading day is itself
    assert last_session.on_or_before("US", date(2026, 10, 17)) == date(2026, 10, 16)


# ---------- net worth, rates, US tax: "Prices as of" / "up to" ----------
def test_net_worth_prices_are_dated_the_last_session_on_a_weekend():
    from app import money_networth as nw
    assert nw.data_day([], date(2026, 10, 17)) == date(2026, 10, 16)                      # nothing priced: not the Saturday
    gold = [{"basis": "market price", "kind": "gold", "as_of": "2026-10-17T09:30:00+05:30"}]
    assert nw.data_day(gold, date(2026, 10, 17)) == date(2026, 10, 16)                    # gold is read at any hour
    close = [{"basis": "market price", "kind": "stocks_in", "as_of": "2026-10-16T15:29:59+05:30"}]
    assert nw.data_day(close, date(2026, 10, 17)) == date(2026, 10, 16)
    assert nw.data_day([], date(2026, 10, 16)) == date(2026, 10, 16)                      # a trading day keeps its own date


def test_the_ltcg_prices_date_is_the_last_session_on_a_weekend():
    from app import money_ltcg
    assert money_ltcg.session_day("2026-10-17") == "2026-10-16"
    assert money_ltcg.session_day("2026-10-16") == "2026-10-16"


def test_rates_and_us_tax_pages_say_the_last_session_on_a_weekend(monkeypatch):
    from app import fixed_income, money_us_routes
    with time_machine.travel(SATURDAY, tick=False):
        assert fixed_income.on_or_before("IN", fixed_income.today()).isoformat() == "2026-10-16"
        assert money_us_routes.on_or_before("IN", money_us_routes.today()).isoformat() == "2026-10-16"


# ---------- paper trading: "Today" ----------
def _snap(curve, cap=100000, eq=100000):
    return {"id": "a", "name": "a", "instrument": {"currency": "INR", "market": "IN"},
            "account": {"capital": cap, "equity": eq, "trades": 2}, "equity_curve": curve}


def test_paper_overview_names_fridays_result_on_a_saturday_not_a_zero_today():
    s = _snap([{"t": "2026-10-15T15:00", "eq": 101000}, {"t": "2026-10-16T15:00", "eq": 98500}], eq=98500)
    c = risk.summary([s], today="2026-10-17")["currencies"][0]
    assert c["today"] == 0 and c["session"] == "2026-10-16" and c["session_pnl"] == -2500.0
    row = risk.summary([s], today="2026-10-17")["sessions"][0]
    assert row["session"] == "2026-10-16" and row["session_pnl"] == -2500.0


def test_paper_overview_on_a_trading_day_is_today():
    s = _snap([{"t": "2026-10-15T15:00", "eq": 101000}], eq=102000)
    c = risk.summary([s], today="2026-10-16")["currencies"][0]
    assert c["today"] == 1000 and c["session"] == "2026-10-16" and c["session_pnl"] is None


# ---------- India VIX: "Not updated today" ----------
@pytest.mark.parametrize("now, session", [(SATURDAY, "2026-10-16"), (FRIDAY, "2026-10-16"), (MONDAY_EARLY, "2026-10-16")])
def test_the_vix_panel_carries_the_session_a_reading_belongs_to(now, session):
    from app import vix
    assert vix.session_now(now.astimezone(timezone(timedelta(hours=5, minutes=30)))) == session


@pytest.fixture
def w(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_the_vix_panel_payload_has_the_session(w):
    from app import vix
    vix.forget()
    try:
        class Down:
            def _get(self, *a, **k):
                raise RuntimeError("down")
        vix.store({"2026-10-15": [14, 15, 13, 14.2], "2026-10-16": [14, 15, 13, 16.73]})
        p = vix.panel(None, SATURDAY, feed=Down())
        assert p["today"] == "2026-10-17" and p["session"] == "2026-10-16" and p["value_day"] == "2026-10-16"
    finally:
        vix.forget()
