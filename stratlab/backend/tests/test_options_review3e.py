"""Review 3e on the options and markets code: MCX's winter close in every place that held 23:30, the model's "as of" being
when its prices were struck, an expiry already over not being "current", the IV percentile for the front expiry only, and
a lot for the expiry picked. Clocks are pinned (time_machine, or an explicit now)."""
from datetime import date, datetime, timedelta, timezone

import pytest
import time_machine
from fastapi.testclient import TestClient

from app import main, positioning as P
from app.main import app
from app.options import data as opt_data, greeks as G
from app.options.data import OptionsData
from tests import fake_positioning as FP

from .fake_options_kite import FakeOptionsKite
from .test_options_api import setup as api_setup

IST = P.IST
OCT = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)        # US daylight saving still on: MCX closes at 23:30
NOV = datetime(2026, 11, 11, 6, 0, tzinfo=timezone.utc)        # off: 23:55


# ---------- 1. MCX's winter close ----------
def test_mcx_candle_counts_and_the_marked_close_follow_the_days_close():
    from app.data.cds import CDSProvider
    from app.data.mcx import MCXProvider
    mcx, cds = MCXProvider(None), CDSProvider(None)
    with time_machine.travel(OCT, tick=False):
        assert mcx.day_close() == "23:30" and [mcx.per_day(tf) for tf in ("1h", "15m", "5m")] == [15, 58, 174]
        assert [cds.per_day(tf) for tf in ("1h", "15m", "5m")] == [8, 32, 96] and cds.day_close() == "17:00"
        summer = mcx.warmup_days("15m", 210)
    with time_machine.travel(NOV, tick=False):
        assert mcx.day_close() == "23:55" and [mcx.per_day(tf) for tf in ("1h", "15m", "5m")] == [15, 60, 179]
        assert cds.day_close() == "17:00"
        assert mcx.warmup_days("15m", 210) <= summer              # more candles a day: no more days of warm-up


def test_the_markets_list_the_pages_read_carries_the_same_close_the_broker_is_told():
    """PaperPage's candle-span labels read /markets' hours.close (frontend), which is the day's close for MCX."""
    from app.data import Registry
    from app.data.coinbase import CoinbaseProvider
    from app.kite_service import KiteService
    from .test_data import fake_coinbase
    from app.data.mcx import MCXProvider
    reg = Registry(KiteService(), CoinbaseProvider(transport=fake_coinbase()))
    for day, want in ((OCT, "23:30"), (NOV, "23:55")):
        with time_machine.travel(day, tick=False):
            assert next(m for m in reg.markets() if m["id"] == "MCX")["hours"]["close"] == want == MCXProvider(None).day_close()


# ---------- 2. the model is as of its prices ----------
def _q(px, ts):
    return {"ltp": px, "bid": px - 0.05, "ask": px + 0.05, "ts": ts}


def test_the_models_as_of_is_when_its_prices_were_struck_in_india_not_the_request_time():
    at = datetime(2026, 10, 5, 10, 42, tzinfo=IST)
    c, p = 160.0, 150.0
    m = G.model(25000, "2026-10-08", 25000, _q(c, "2026-10-05T10:41:30"), _q(p, "2026-10-05T10:41:00"), at)
    assert m["as_of"] == "2026-10-05T10:41:30+05:30" and m["fresh"] is True              # a time with no zone is India's
    # the same moment sent with a zone, in UTC
    m = G.model(25000, "2026-10-08", 25000, _q(c, "2026-10-05T05:11:30+00:00"), _q(p, "2026-10-05T05:11:00+00:00"), at)
    assert m["as_of"] == "2026-10-05T10:41:30+05:30"
    # shut: the last quotes are from Friday's close, asked for on Monday at 09:00
    mon = datetime(2026, 10, 12, 9, 0, tzinfo=IST)
    m = G.model(25000, "2026-10-15", 25000, _q(c, "2026-10-09T15:29:58"), _q(p, "2026-10-09T15:29:57"), mon)
    assert m["as_of"] == "2026-10-09T15:29:58+05:30" and m["fresh"] is False
    # the spot's own time counts too, and the newest of them is the model's
    m = G.model(25000, "2026-10-15", 25000, _q(c, "2026-10-09T15:29:58"), _q(p, "2026-10-09T15:29:57"), mon, spot_ts="2026-10-09T15:30:01")
    assert m["as_of"] == "2026-10-09T15:30:01+05:30"
    # no time on any price: none is made up from the clock
    m = G.model(25000, "2026-10-15", 25000, {"ltp": c}, {"ltp": p}, mon)
    assert m["as_of"] is None and m["fresh"] is False
    assert G.model(25000, "2026-10-15", 25000, None, None, mon, spot_ts=datetime(2026, 10, 12, 8, 59, 30))["as_of"] == "2026-10-12T08:59:30+05:30"


def test_a_chain_and_a_preview_say_when_their_quotes_were_struck(monkeypatch):
    chain = {"exchange": "NFO", "expiry": "2026-10-15", "spot": 25000.0, "atm": 25000.0, "spot_ts": "2026-10-09T15:30:01",
             "rows": [{"strike": 25000.0, "ce": _q(160.0, "2026-10-09T15:29:58"), "pe": _q(150.0, "2026-10-09T15:29:57")}]}
    got = G.add_to_chain(chain, datetime(2026, 10, 12, 9, 0, tzinfo=IST))["model"]
    assert got["as_of"] == "2026-10-09T15:30:01+05:30" and got["fresh"] is False and got["exchange"] == "NFO" and got["tick"] == 0.05
    data, _ = api_setup(monkeypatch, live=False)                 # the feed's quotes are three days old
    try:
        c = TestClient(app)
        strat = {"name": "Short straddle", "structure": "short_straddle", "exchange": "NFO", "underlying": "NIFTY",
                 "legs": [{"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0}]}
        pv = c.post("/options/preview", json={"strategy": strat}).json()
        stamp = datetime.fromisoformat(pv["model"]["as_of"])
        stale = datetime.now(IST).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=3)
        assert stamp == stale and pv["model"]["fresh"] is False and pv["spot_ts"]
        cur = c.post("/options/preview", json={"strategy": {**strat, "exchange": "CDS", "underlying": "USDINR"}}).json()
        assert cur.get("tick") == 0.0025 and (cur["model"] or {}).get("tick", 0.0025) == 0.0025
    finally:
        app.dependency_overrides.clear()


# ---------- 3. an expiry already over is not current ----------
def _snap(e, rows):
    return {"expiry": e, "spot": 25000.0, "chain": rows, "lot": 75, "taken_at": "2026-10-27T09:50:00+00:00"}


def test_the_recorded_chain_drops_todays_expiry_once_it_has_closed(monkeypatch):
    """Tuesday 27 Oct 2026: the NIFTY series expiring that day stops trading at 15:40 (data/sessions.py)."""
    today = date(2026, 10, 27)
    monkeypatch.setattr(P, "recorded_last", lambda name, day: [_snap("2026-10-27", []), _snap("2026-11-03", [])])
    monkeypatch.setattr(P, "expiry_fits", lambda ex, name, e: True)
    at = lambda h, m: datetime(2026, 10, 27, h, m, tzinfo=IST)
    assert P.recorded_chain("NIFTY", "current", today, at(15, 39))["expiry"] == "2026-10-27"          # still trading
    after = P.recorded_chain("NIFTY", "current", today, at(17, 0))
    assert after["expiry"] == "2026-11-03" and after["expiries"] == ["2026-11-03"]
    assert P.recorded_chain("NIFTY", "current", today, at(15, 40))["expiry"] == "2026-11-03"          # the minute it stops
    assert P.recorded_chain("NIFTY", "2026-10-27", today, at(17, 0)) is None                          # and asked for by date
    assert P.recorded_chain("NIFTY", "current", today)["expiry"] == "2026-10-27"                      # no clock given: as before


def test_the_chain_shown_after_the_expiry_close_is_the_next_expiry(monkeypatch):
    rows = lambda e: FP.chain(25000.0, 0.12, e, datetime(2026, 10, 27, 15, 20, tzinfo=IST))
    monkeypatch.setattr(P, "recorded_last", lambda name, day: [_snap("2026-10-27", rows("2026-10-27")), _snap("2026-11-03", rows("2026-11-03"))])
    monkeypatch.setattr(P, "expiry_fits", lambda ex, name, e: True)
    monkeypatch.setattr(P, "live_chain", lambda *a, **k: None)             # the feed is offline
    got, at, stats = P.chain_now(None, "NIFTY", "current", datetime(2026, 10, 27, 17, 0, tzinfo=IST))
    assert got["expiry"] == "2026-11-03" and stats["expiry"] == "2026-11-03"
    got, *_ = P.chain_now(None, "NIFTY", "current", datetime(2026, 10, 27, 14, 0, tzinfo=IST))
    assert got["expiry"] == "2026-10-27"


# ---------- 7. the IV percentile is for the front expiry ----------
def test_the_iv_percentile_is_given_only_for_the_front_expiry(monkeypatch):
    expiries = ["2026-10-27", "2026-11-03", "2026-11-10"]
    pick = {"current": 0, "next": 1, "far": 2}

    def live(options_data, exchange, name, choice):
        e = expiries[pick[choice]]
        at = datetime(2026, 10, 27, 11, 0, tzinfo=IST)
        return {"expiry": e, "expiries": expiries, "spot": 25000.0, "chain": FP.chain(25000.0, 0.12, e, at), "source": "live",
                "taken_at": at.isoformat(), "lot": 75}
    monkeypatch.setattr(P, "live_chain", live)
    monkeypatch.setattr(P, "chain_series", lambda name, since=None: [{"day": f"2026-09-{d:02d}", "atm_iv": 10.0 + d / 10} for d in range(1, 26)])
    monkeypatch.setattr(P, "recorded_before", lambda *a, **k: None)
    monkeypatch.setattr(P, "chain_coverage", lambda name: {"days": 25})
    view = lambda choice, now: P.chain_view(None, "NIFTY", choice, full=True, now=now)
    expiry_day = datetime(2026, 10, 27, 11, 0, tzinfo=IST)
    assert view("current", expiry_day)["iv"] is None                       # the expiring chain on its last day
    assert view("next", expiry_day)["iv"]["percentile"] is not None        # the nearest one after the day: the front
    assert view("far", expiry_day)["iv"] is None                           # a later one
    # the day before, the nearest is the front and the one after it is not
    expiries[:] = ["2026-10-27", "2026-11-03", "2026-11-10"]
    eve = datetime(2026, 10, 26, 11, 0, tzinfo=IST)
    monkeypatch.setattr(P, "live_chain", lambda o, e, n, c: {**live(o, e, n, c), "taken_at": eve.isoformat()})
    assert view("current", eve)["iv"]["percentile"] is not None and view("next", eve)["iv"] is None


# ---------- 8. a lot for the expiry picked ----------
def test_each_listed_expiry_has_its_own_lot(monkeypatch):
    od = OptionsData(kite=None)
    today = opt_data.ist_date()
    near, nxt = today + timedelta(days=3), today + timedelta(days=10)
    od._day = today.isoformat()
    od._rows = {"NFO": [{"symbol": f"NIFTY{e}{k}", "name": "NIFTY", "type": "CE", "strike": 25000.0, "expiry": e.isoformat(), "lot": lot,
                         "exchange": "NFO"} for e, lot, k in ((near, 65, "A"), (nxt, 75, "B"))], "BFO": [], "MCX": [], "CDS": []}
    monkeypatch.setattr(opt_data, "keep_listed", lambda ex, name, xs: xs)
    monkeypatch.setattr(opt_data, "expired_today", lambda exch, now=None: False)
    und = next(u for u in od.underlyings() if u["name"] == "NIFTY")
    assert und["lot"] == 65 and und["lots"] == {near.isoformat(): 65, nxt.isoformat(): 75}
    assert od.contracts("NFO", "NIFTY", "next").lot == 75                    # what the chain and the preview use


# ---------- 9. BSE F&O ----------
def test_bse_derivatives_keep_the_derivatives_close_nothing_in_the_repo_says_otherwise():
    """Nothing in the repo documents a different close for BSE's futures and options (BFO): sessions.fo_close applies to both."""
    assert opt_data.expiry_time("BFO", date(2026, 10, 14)) == opt_data.expiry_time("NFO", date(2026, 10, 14)) == "15:40"
