"""Index option expiries by the exchanges' rules: NIFTY (NSE) and SENSEX (BSE) expire weekly; BANKNIFTY, FINNIFTY,
MIDCPNIFTY and the other index options only monthly (since 20 Nov 2024). NSE expiries fall on Tuesdays and BSE's on
Thursdays from 1 Sep 2025, a day earlier on a holiday."""
from datetime import date, timedelta

import pytest

from app import db, main, positioning as P
from app.data import expiries as E
from app.data.calendar import is_trading_day
from app.options.data import OptionsData
from tests import fake_positioning as FP
from tests import world as W
from tests.fake_options_kite import FakeOptionsKite

TODAY = date(2026, 10, 7)          # a Wednesday


def _is_rule_day(d: date, wd: int) -> bool:
    """On the expiry weekday, or the trading day before a holiday that falls on it."""
    if d.weekday() == wd:
        return True
    nxt = d + timedelta(days=1)
    while nxt.weekday() != wd and nxt - d < timedelta(days=7):
        if is_trading_day("IN", nxt):
            return False
        nxt += timedelta(days=1)
    return nxt.weekday() == wd and not is_trading_day("IN", nxt)


def test_only_nifty_and_sensex_are_weekly():
    assert E.cycle("NFO", "NIFTY") == "weekly"
    assert E.cycle("BFO", "SENSEX") == "weekly"
    for ex, name in (("NFO", "BANKNIFTY"), ("NFO", "FINNIFTY"), ("NFO", "MIDCPNIFTY"), ("NFO", "NIFTYNXT50"),
                     ("BFO", "BANKEX"), ("BFO", "SENSEX50"), ("NFO", "RELIANCE")):
        assert E.cycle(ex, name) == "monthly", name
    assert E.cycle("MCX", "CRUDEOIL") is None and E.cycle("CDS", "USDINR") is None


def test_banknifty_expires_monthly_on_the_last_tuesday():
    got = E.rule_expiries("NFO", "BANKNIFTY", TODAY, 4)
    assert got[0] == date(2026, 10, 27)                        # not the weekly 13 Oct
    assert [d.month for d in got] == [10, 11, 12, 1]           # one a month
    for d in got:
        assert _is_rule_day(d, 1) and E.fits("NFO", "BANKNIFTY", d), d
        assert d == E.monthly_expiry("NFO", d.year, d.month)
    assert E.rule_expiries("NFO", "FINNIFTY", TODAY, 1) == E.rule_expiries("NFO", "MIDCPNIFTY", TODAY, 1) == [date(2026, 10, 27)]


def test_nifty_expires_every_tuesday_and_sensex_every_thursday():
    nifty = E.rule_expiries("NFO", "NIFTY", TODAY, 4)
    assert nifty[0] == date(2026, 10, 13)
    assert all(_is_rule_day(d, 1) for d in nifty)
    assert all(timedelta(days=5) <= b - a <= timedelta(days=8) for a, b in zip(nifty, nifty[1:]))
    sensex = E.rule_expiries("BFO", "SENSEX", TODAY, 2)
    assert sensex[0] == date(2026, 10, 8) and all(_is_rule_day(d, 3) for d in sensex)


def test_a_monthly_only_index_never_keeps_a_weekly_date():
    listed = ["2026-10-13", "2026-10-20", "2026-10-27", "2026-11-24"]
    assert E.keep_listed("NFO", "BANKNIFTY", listed) == ["2026-10-27", "2026-11-24"]
    assert E.keep_listed("NFO", "NIFTY", listed) == listed
    assert E.keep_listed("MCX", "CRUDEOIL", listed) == listed
    assert E.fits("NFO", "BANKNIFTY", "2024-11-13")            # BANKNIFTY's last weekly expiry, before the change
    assert not E.fits("NFO", "BANKNIFTY", "2026-10-13")
    # a monthly expiry moved a day earlier by a holiday still fits
    moved = E.monthly_expiry("NFO", 2026, 11)
    assert E.fits("NFO", "BANKNIFTY", moved)


def test_the_option_list_offers_banknifty_monthly_and_nifty_weekly():
    data = OptionsData(FakeOptionsKite())
    bank = data.expiries("NFO", "BANKNIFTY")
    assert bank and all(E.fits("NFO", "BANKNIFTY", e) for e in bank)
    assert len({e[:7] for e in bank}) == len(bank)              # one expiry a month
    nifty = data.expiries("NFO", "NIFTY")
    assert date.fromisoformat(nifty[1]) - date.fromisoformat(nifty[0]) <= timedelta(days=8)
    unds = {u["name"]: u for u in data.underlyings()}
    assert unds["BANKNIFTY"]["expiries"] == bank[:6]
    assert data.pick_expiry("NFO", "BANKNIFTY", "current") == data.pick_expiry("NFO", "BANKNIFTY", "month")


def test_a_broker_list_with_a_weekly_banknifty_date_is_cut_to_the_monthly(monkeypatch):
    data = OptionsData(FakeOptionsKite())
    data._load()
    rows = data._rows["NFO"]
    month_end = next(r for r in rows if r["name"] == "BANKNIFTY")["expiry"]
    weekly = (date.fromisoformat(month_end) - timedelta(days=7)).isoformat()
    rows.append({"symbol": "BANKNIFTYWEEKLYCE", "name": "BANKNIFTY", "type": "CE", "strike": 55000.0, "expiry": weekly, "lot": 35, "exchange": "NFO"})
    if weekly >= date.today().isoformat():
        assert weekly not in data.expiries("NFO", "BANKNIFTY")
        assert data.pick_expiry("NFO", "BANKNIFTY", "current") != weekly


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    P.clear_cache()


def test_put_call_ratio_table_reads_each_index_on_its_own_cycle(w):

    table = {r["name"]: r for r in P.pcr_table(main.options_data)}
    assert table["NIFTY"]["cycle"] == "weekly" and table["SENSEX"]["cycle"] == "weekly"
    for name in ("BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"):
        r = table[name]
        assert r["cycle"] == "monthly" and E.fits("NFO", name, r["expiry"]), r
        assert (date.fromisoformat(r["expiry"]) + timedelta(days=7)).month != date.fromisoformat(r["expiry"]).month or \
            r["expiry"] == E.monthly_expiry("NFO", int(r["expiry"][:4]), int(r["expiry"][5:7])).isoformat()


def test_old_weekly_recordings_of_a_monthly_index_are_passed_over(w, monkeypatch):

    monkeypatch.setattr(main.options_data, "ready", lambda: False)
    today = date.today()
    day = FP.weekdays_before(today, 1)
    FP.record_days(db.add_option_snapshot, "BANKNIFTY", day, spot=55000.0, gap=100)
    # a weekly date recorded under the old list: nearer than the month's expiry, so it would be "current"
    near = next(d for d in (today + timedelta(days=i) for i in range(1, 8)) if d.weekday() == 1)
    if (near + timedelta(days=7)).month == near.month:
        from datetime import datetime, time as dtime, timezone
        at = datetime.combine(day[0], dtime(15, 20), P.IST)
        db.add_option_snapshot({"taken_at": at.astimezone(timezone.utc).isoformat(), "exchange": "NFO", "name": "BANKNIFTY",
                                "expiry": near.isoformat(), "spot": 55000.0, "lot": 35,
                                "chain": FP.chain(55000.0, 0.12, near.isoformat(), at, 100)})
        P.clear_cache()
    got = P.recorded_chain("BANKNIFTY", "current", today)
    assert got and E.fits("NFO", "BANKNIFTY", got["expiry"]) and all(E.fits("NFO", "BANKNIFTY", e) for e in got["expiries"])
