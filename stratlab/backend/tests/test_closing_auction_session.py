"""India's session table and the closing auction (from 3 Aug 2026): continuous fills stop at 15:15 for stocks with
derivatives, square-offs after that fill at the auction close, daily candles close on the official close, the
derivatives segment runs to 15:40, and expiring options settle at the underlying's close."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from app import rules
from app.data import sessions as S
from app.engine.core import Ctx, Engine
from app.live import CandleBuilder, close_at_auction, drop_forming
from app.models import OptionStrategy, Strategy
from app.options import greeks as G
from app.options import recorder
from app.options.engine import Contracts, OptionsEngine

IST = ZoneInfo("Asia/Kolkata")
AFTER, BEFORE = "2026-10-05", "2026-07-31"        # a Monday after the auction began, a Friday before


def at(day: str, hm: str, s: int = 0) -> datetime:
    h, m = map(int, hm.split(":"))
    y, mo, d = map(int, day.split("-"))
    return datetime(y, mo, d, h, m, s, tzinfo=IST)


# ---------- the table ----------
def test_one_row_per_timetable_and_the_rule_change_day():
    assert [r.since for r in S.TIMES] == sorted(r.since for r in S.TIMES)
    assert S.CAS_FROM == "2026-08-03"
    assert S.timetable("2026-08-02").auction is None and S.timetable("2026-08-03").auction == ("15:15", "15:35")


def test_kinds():
    names = {"RELIANCE", "NIFTY"}
    assert S.kind_of({"exchange": "NSE", "type": "EQ", "symbol": "RELIANCE"}, names) == "cas"
    assert S.kind_of({"exchange": "BSE", "type": "EQ", "symbol": "RELIANCE"}, names) == "cas"
    assert S.kind_of({"exchange": "NSE", "type": "EQ", "symbol": "TINYCO"}, names) == "cash"
    assert S.kind_of({"exchange": "NSE", "type": "INDEX", "symbol": "NIFTY 50"}, names) == "index"
    assert S.kind_of({"exchange": "NFO", "type": "FUT", "symbol": "NIFTY26OCTFUT", "fno": True}, names) == "fo"


@pytest.mark.parametrize("kind,day,end", [
    ("cas", AFTER, time(15, 15)), ("cash", AFTER, time(15, 30)), ("index", AFTER, time(15, 30)), ("fo", AFTER, time(15, 40)),
    ("cas", BEFORE, time(15, 30)), ("fo", BEFORE, time(15, 30)),
])
def test_continuous_session_ends(kind, day, end):
    assert S.continuous(kind, day) == (time(9, 15), end)


def test_close_known_and_settlement_time():
    assert S.close_known("cas", AFTER) == time(15, 35) and S.close_known("index", AFTER) == time(15, 35)
    assert S.close_known("cash", AFTER) == time(15, 30) and S.close_known("cas", BEFORE) == time(15, 30)
    assert S.settle_at(AFTER) == S.settle_at(BEFORE) == time(15, 30)
    assert S.auction("cas", AFTER) == (time(15, 15), time(15, 35)) and S.auction("cash", AFTER) is None


# ---------- candles from ticks ----------
def ticks(b: CandleBuilder, day: str, times: list[str], px=100.0) -> list[dict]:
    out = []
    for i, hm in enumerate(times):
        hh, mm, *ss = hm.split(":")
        out += b.on_tick(px + i, at(day, f"{hh}:{mm}", int(ss[0]) if ss else 0), None)
    return out


def test_no_continuous_candle_after_1515_for_a_stock_with_derivatives():
    b = CandleBuilder("5m", "cas")
    closed = ticks(b, AFTER, ["15:10", "15:14:59", "15:15", "15:20", "15:33"])
    assert [c["t"][11:16] for c in closed] == ["15:10"]          # the 15:10 candle, closed by the 15:15 tick
    assert closed[0]["c"] == 101 and b.cur is None                # nothing after the cut-off made a candle
    b = CandleBuilder("5m", "cas")                                # before 3 Aug it ran to 15:30
    assert [c["t"][11:16] for c in ticks(b, BEFORE, ["15:10", "15:20", "15:29", "15:30"])] == ["15:10", "15:20", "15:25"]


def test_other_stocks_to_1530_and_derivatives_to_1540():
    b = CandleBuilder("5m", "cash")
    assert [c["t"][11:16] for c in ticks(b, AFTER, ["15:25", "15:29:59", "15:30"])] == ["15:25"]
    b = CandleBuilder("15m", "fo")
    closed = ticks(b, AFTER, ["15:20", "15:31", "15:39:59", "15:40"])
    assert [c["t"][11:16] for c in closed] == ["15:15", "15:30"]
    assert closed[-1]["c"] == 102                                 # the 15:30-15:40 candle, cut at the close


def test_daily_candle_waits_for_the_auction_close():
    calls = []

    def official(day):
        calls.append(day)
        return 123.45
    b = CandleBuilder("1d", "cas", official)
    ticks(b, AFTER, ["09:15", "15:14"])
    assert b.flush(at(AFTER, "15:20")) == [] and b.flush(at(AFTER, "15:34")) == [] and not calls
    [c] = b.flush(at(AFTER, "15:35"))
    assert c["c"] == 123.45 and c["h"] >= 123.45 and calls == [AFTER]


def test_daily_candle_falls_back_to_the_last_price_when_no_close_comes():
    b = CandleBuilder("1d", "cas", lambda day: None)
    ticks(b, AFTER, ["09:15", "15:14"])
    assert b.flush(at(AFTER, "15:36")) == []
    [c] = b.flush(at(AFTER, "16:06"))
    assert c["c"] == 101


def test_drop_forming_keeps_todays_daily_candle_only_once_the_close_is_out(monkeypatch):
    import app.live as live
    bars = [{"t": f"{AFTER}T00:00:00+05:30", "o": 1, "h": 1, "l": 1, "c": 1, "v": 0}]

    class Clock(datetime):
        now_at = at(AFTER, "15:32")

        @classmethod
        def now(cls, tz=None):
            return cls.now_at
    monkeypatch.setattr(live, "datetime", Clock)
    assert drop_forming(bars, "1d", "cas") == [] and drop_forming(bars, "1d", "cash") == bars
    Clock.now_at = at(AFTER, "15:35")
    assert drop_forming(bars, "1d", "cas") == bars


# ---------- square-off in the auction ----------
def intraday(squareoff: str) -> Engine:
    s = Strategy(tf="5m", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}],
                 risk={"capital": 100000, "riskPct": 1, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0},
                 session={"squareoff": squareoff})
    e = Engine(s, 1)
    bars = [{"t": f"{AFTER}T15:05:00+05:30", "o": 100, "h": 100, "l": 100, "c": 100, "v": 1},
            {"t": f"{AFTER}T15:10:00+05:30", "o": 100, "h": 100, "l": 100, "c": 100, "v": 1}]
    e.step(bars, Ctx(bars, intraday=True), 1)                     # enters on the candle closing at 15:15
    assert e.qty > 0
    return e


def test_square_off_after_1515_fills_at_the_auction_close():
    e = intraday("15:20")
    assert close_at_auction(e, "cas", at(AFTER, "15:34", 59), lambda: 105.0) is None   # the auction isn't done
    ev = close_at_auction(e, "cas", at(AFTER, "15:35"), lambda: 105.0)
    assert ev["px"] == 105.0 and ev["why"] == "Square-off at the closing auction price" and ev["t"].endswith("15:35:00+05:30")
    assert e.qty == 0 and e.trades[-1]["exit"] == 105.0
    assert close_at_auction(e, "cas", at(AFTER, "15:36"), lambda: 106.0) is None        # once


def test_no_auction_fill_for_futures_without_a_close_or_for_yesterdays_trade():
    assert close_at_auction(intraday("15:20"), "fo", at(AFTER, "15:45"), lambda: 1.0) is None
    assert close_at_auction(intraday("15:20"), "cas", at(AFTER, "15:40"), lambda: None) is None
    assert close_at_auction(intraday("15:20"), "cas", at("2026-10-06", "15:40"), lambda: 1.0) is None


def test_delivery_positions_are_left_alone():
    s = Strategy(tf="5m", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}],
                 risk={"capital": 100000, "riskPct": 1, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0})
    e = Engine(s, 1)
    bars = [{"t": f"{AFTER}T15:05:00+05:30", "o": 100, "h": 100, "l": 100, "c": 100, "v": 1}] * 2
    e.step(bars, Ctx(bars, intraday=True), 1)
    assert e.qty > 0 and close_at_auction(e, "cas", at(AFTER, "15:40"), lambda: 1.0) is None


# ---------- options ----------
STRIKES = [24900, 25000, 25100]


def nifty(expiry=AFTER):
    rows = [{"opt": o, "strike": k, "symbol": f"NIFTY{k}{o}"} for k in STRIKES for o in ("CE", "PE")]
    return Contracts(rows, 75, expiry, "NFO")


def quotes():
    return {f"NFO:NIFTY{k}{o}": {"bid": 99.5, "ask": 100.5, "ltp": 100.0} for k in STRIKES for o in ("CE", "PE")}


def straddle(squareoff="15:45"):
    return OptionStrategy(name="s", underlying="NIFTY", legs=[{"side": "sell", "opt": "CE", "offset": 0},
                                                             {"side": "sell", "opt": "PE", "offset": 0}],
                          timing={"entry": "09:30", "lastEntry": "14:45", "squareoff": squareoff, "maxEntries": 1, "cooldown": 0},
                          costs={"brokerage": 0, "slippageTicks": 0, "freeze": 0})


def test_expiring_options_settle_at_intrinsic_against_the_close():
    asked = []
    e = OptionsEngine(straddle(), settle_fn=lambda exp: asked.append(exp) or 25040.0)
    c = nifty()
    e.step(at(AFTER, "09:31"), 25010, c, quotes(), True)
    assert e.pos and e.pos["expiry"] == AFTER
    assert e.step(at(AFTER, "15:39"), 25010, c, quotes(), False) == [] and e.pos     # still trading to 15:40
    out = e.step(at(AFTER, "15:40"), None, c, {}, False)
    assert asked == [AFTER] and e.pos is None
    legs = {x["sym"]: x["px"] for x in out}
    assert legs == {"NIFTY25000CE": 40.0, "NIFTY25000PE": 0.0}
    t = e.trades[-1]
    assert t["why"] == "Expiry settlement" and t["gross"] == pytest.approx((99.5 - 40 + 99.5 - 0) * 75)


def test_settlement_waits_for_the_price_and_skips_other_days():
    e = OptionsEngine(straddle(), settle_fn=lambda exp: None)
    c = nifty()
    e.step(at(AFTER, "09:31"), 25010, c, quotes(), True)
    assert e.step(at(AFTER, "15:50"), None, c, {}, False) == [] and e.pos         # no close yet: hold
    e2 = OptionsEngine(straddle(), settle_fn=lambda exp: 1 / 0)                    # never asked before expiry
    c2 = nifty("2026-10-06")
    e2.step(at(AFTER, "09:31"), 25010, c2, quotes(), True)
    assert e2.step(at(AFTER, "15:50"), None, c2, {}, False) == [] and e2.pos


def test_greeks_time_runs_to_the_settlement_time():
    assert G.years_to(AFTER, at(AFTER, "15:30")) == 0
    assert G.years_to(AFTER, at(AFTER, "15:15")) * 365 * 24 * 60 == pytest.approx(15)
    assert G.years_to(BEFORE, at(BEFORE, "15:00")) * 365 * 24 * 60 == pytest.approx(30)


def test_recorder_runs_while_derivatives_trade():
    assert recorder.in_hours(at(AFTER, "15:39"))
    assert not recorder.in_hours(at(AFTER, "15:41"))
    assert not recorder.in_hours(at(BEFORE, "15:35"))


def test_session_kind_from_the_instrument_list():
    from app.live import session_kind
    from tests.fake_kite import online
    k = online()
    assert {"NIFTY", "BANKNIFTY"} <= k.derivative_names()
    assert session_kind(k, k.by_symbol("NIFTY 50")) == "index"
    assert session_kind(k, {"exchange": "NSE", "type": "EQ", "symbol": "NIFTY"}) == "cas"
    assert session_kind(k, {"exchange": "NSE", "type": "EQ", "symbol": "TINYCO"}) == "cash"
    assert session_kind(object(), {"exchange": "NSE", "type": "EQ", "symbol": "NIFTY"}) == "cash"   # no list: plain hours


def test_rules_register_lists_the_closing_auction():
    row = next(r for r in rules.registry() if r["id"] == "closing_auction")
    assert row["since"] == "2026-08-03" and "15:15-15:35" in row["value"] and "15:40" in row["value"]
    assert "2765/2026" in row["source"] and "74466" in row["source"]
