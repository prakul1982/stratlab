"""LIVE10B: the findings of the live end-to-end review of Release 60, each with the test that proves it. Plain asserts on the
existing fixtures and the `world` helpers."""
import base64
from pathlib import Path

import pytest

from app import holdings
from tests import world

FIX = Path(__file__).parent / "fixtures" / "holdings"
PRO = world.headers("pro-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def file_upload(c, name: str, mode="replace", **extra):
    body = {"filename": name, "data": base64.b64encode((FIX / name).read_bytes()).decode(), "mode": mode, **extra}
    return c.post("/holdings/import", headers=PRO, json=body)


def qtys(body):
    return {x["symbol"]: x["qty"] for x in body["holdings"]["rows"]}


def test_live10b_024_a_file_of_stocks_already_held_is_never_added_silently(w):
    """Re-uploading the same Zerodha file (after an ICICI file was added) doubled every quantity."""
    c = w["client"]
    file_upload(c, "zerodha_kite_holdings.csv", "replace")
    merged = file_upload(c, "icici_direct_portfolio.csv", "add").json()
    assert merged["saved"] is False and merged["overlap"] == ["ICICIBANK", "SBIN"]   # held already: asked first
    assert qtys(merged)["SBIN"] == 60
    merged = file_upload(c, "icici_direct_portfolio.csv", "add", overlap_ok=True).json()
    assert merged["saved"] is True and qtys(merged)["SBIN"] == 140                   # the user's word: more shares
    again = file_upload(c, "zerodha_kite_holdings.csv", "add").json()
    assert again["saved"] is False and qtys(again)["SBIN"] == 140                   # the same file: not doubled


def test_live10b_024_the_same_holdings_in_a_file_not_remembered_count_as_the_same_file(w, monkeypatch):
    """Holdings imported before the file's fingerprint was kept: the same lines again are recognised by their content."""
    c = w["client"]
    file_upload(c, "zerodha_kite_holdings.csv", "replace")
    monkeypatch.setattr(holdings, "file_seen", lambda uid, digest: False)
    body = file_upload(c, "zerodha_kite_holdings.csv", "add").json()
    assert body["duplicate"] is True and body["saved"] is False and qtys(body)["SBIN"] == 60


def test_live10b_013_a_daily_candle_started_mid_day_takes_the_days_real_open_high_and_low():
    """A paper session started at 13:48 IST built today's candle from its own first tick: O = H = 25,422.55."""
    from datetime import datetime
    from app import live
    from app.live import IST
    b = live.CandleBuilder("1d", "index")
    day = {"open": 25277.30, "high": 25501.35, "low": 25267.30, "close": 25291.10}
    b.on_tick(25422.55, datetime(2026, 11, 17, 13, 48, tzinfo=IST), None, day)
    b.on_tick(25420.60, datetime(2026, 11, 17, 13, 49, tzinfo=IST), None, day)
    assert (b.cur["o"], b.cur["h"], b.cur["l"], b.cur["c"]) == (25277.30, 25501.35, 25267.30, 25420.60)
    # a minute candle is its own: the day's figures leave it alone
    m = live.CandleBuilder("5m", "index")
    m.on_tick(25422.55, datetime(2026, 11, 17, 13, 48, tzinfo=IST), None, day)
    assert (m.cur["o"], m.cur["h"], m.cur["l"]) == (25422.55, 25422.55, 25422.55)
    # no day figures (or nonsense ones): the ticks alone, as before
    n = live.CandleBuilder("1d", "index")
    n.on_tick(100.0, datetime(2026, 11, 17, 13, 48, tzinfo=IST), None, {"open": 0, "high": 0, "low": 0})
    assert (n.cur["o"], n.cur["h"], n.cur["l"]) == (100.0, 100.0, 100.0)


def test_live10b_013_the_snapshot_sends_the_forming_candles_open_high_and_low():
    import inspect
    from app import live
    src = inspect.getsource(live.LiveSession.snapshot)
    assert '"o": forming["o"], "h": forming["h"]' in src and '"l": forming["l"], "c": forming["c"]' in src


def test_live10b_028_stopping_an_options_session_squares_off_its_open_legs():
    """A short straddle left open at the stop stayed "Open since 14:05" for good, though its contracts expired that day."""
    from tests.test_options import at, contracts, opt_row, quotes, straddle, StubData
    from app.options.engine import OptionsEngine
    from app.options.session import OptionSession
    e = OptionsEngine(straddle())
    e.step(at("09:31"), 25000, contracts(), quotes(25000), True)
    s = OptionSession(None, opt_row(straddle(), e.dump()), StubData())
    s.quotes = quotes(25100)
    assert s.engine.pos
    st = s.final_state(at("10:05"))
    assert st.get("pos") is None and s.engine.pos is None                      # nothing left open
    last = s.engine.trades[-1]
    assert last["why"] == "Session stopped" and all(l["exit"] is not None for l in last["legs"])
    assert st["equity_curve"][-1]["eq"] == round(s.engine.cash, 2)            # the account is its cash once flat
    # nothing open: the state as it was
    assert OptionSession(None, opt_row(straddle()), StubData()).final_state(at("10:05"))["equity_curve"] == []


def test_live10b_011_a_partial_exit_is_a_closed_round_trip():
    """INFY, SBIN, ITC and RELIANCE were "Still open … +₹18,000 on the part closed": their realised sales were left out."""
    from datetime import date
    from app import journal as J
    S = J.clean_settings({})
    fill = lambda d, side, q, px: {"d": d, "t": "", "side": side, "qty": q, "price": px, "symbol": "INFY", "exchange": "NSE", "seg": "EQ"}
    fs = [fill("2026-01-02", "B", 50, 1000.0), fill("2026-01-05", "B", 50, 1100.0), fill("2026-03-02", "S", 60, 1300.0)]
    got, open_, unmatched = J.pair_fills(fs, S, date(2026, 11, 17))
    assert len(got) == 1 and not unmatched
    t = got[0]
    # first in, first out: the 60 sold are the 50 at 1,000 and 10 of the 50 at 1,100
    assert t["qty"] == 60 and t["entry"] == pytest.approx((50 * 1000 + 10 * 1100) / 60) and t["gross"] == pytest.approx(60 * 1300 - 61000)
    assert open_[0]["qty"] == 40 and open_[0]["avg"] == pytest.approx(1100.0) and open_[0]["realised"] == 0
    # a short partly bought back is the same, and stays out of "sold with no purchase before it"
    fs = [{**fill("2026-01-02", "S", 10, 500.0), "seg": "FUT", "symbol": "INFY26JANFUT"}, {**fill("2026-01-03", "B", 4, 450.0), "seg": "FUT", "symbol": "INFY26JANFUT"}]
    got, open_, unmatched = J.pair_fills(fs, S, date(2026, 1, 10))
    assert len(got) == 1 and got[0]["qty"] == 4 and open_[0]["qty"] == 6 and not unmatched


def test_live10b_011_the_journal_says_how_many_tax_trades_are_not_brought_in_yet(w):
    """After "Bring them in" the page still offered "the newer ones" (the report's newest line was a buy), and the press did nothing."""
    from app import tax_lots
    c = w["client"]
    tax_lots.save("u-pro", [{"d": "2025-01-02", "side": "B", "qty": 5, "price": 100, "symbol": "ITC", "src": "trades"},
                            {"d": "2025-02-02", "side": "S", "qty": 5, "price": 110, "symbol": "ITC", "src": "trades"},
                            {"d": "2025-03-02", "side": "B", "qty": 5, "price": 120, "symbol": "ITC", "src": "trades"}], [])
    assert c.get("/trade/journal", headers=PRO).json()["tax_new"] == 3
    r = c.post("/trade/journal/import-tax", headers=PRO).json()
    assert r["added"] == 3 and r["journal"]["tax_new"] == 0                     # nothing newer to offer once brought in


def test_live10b_039_a_delivery_trade_whose_file_charges_leave_stt_out_is_marked():
    """ITC 100 @380 -> 490 showed charges of Rs 2.00 from the file, though its STT alone is Rs 87."""
    from app import journal as J
    S = J.clean_settings({})
    line = {"sym": "ITC", "ed": "2024-01-02", "et": "", "xd": "2024-06-03", "xt": "", "qty": 100.0, "bv": 38000.0, "sv": 49000.0,
            "charges": 2.0, "side": None, "exchange": "NSE"}
    t = J.line_trades([line], S)[0]
    assert t["charges"] == 2.0 and t["no_stt"] is True                       # the file's figure kept, and marked
    assert J.line_trades([{**line, "charges": 120.0}], S)[0]["no_stt"] is False   # a total that holds STT
    assert J.line_trades([{**line, "charges": None}], S)[0]["no_stt"] is False    # worked out at the rates: STT in
    assert J.line_trades([{**line, "xd": "2024-01-02", "charges": 2.0}], S)[0]["no_stt"] is False   # intraday: no delivery STT
