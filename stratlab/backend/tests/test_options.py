"""Options paper trading: fills on bid/ask, stops, leg stops, re-centring, square-off, caps and sizing."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.models import OptionStrategy
from app.options import importer as oi
from app.options.engine import Contracts, OptionsEngine, fill_price

IST = ZoneInfo("Asia/Kolkata")
STRIKES = [24500 + 50 * i for i in range(21)]   # 24500 .. 25500


def contracts():
    rows = [{"opt": o, "strike": k, "symbol": f"NIFTY{int(k)}{o}"} for k in STRIKES for o in ("CE", "PE")]
    return Contracts(rows, 75, "2026-09-29", "NFO")


def premium(opt, strike, spot):
    """A made-up price: intrinsic value plus time value that fades away from the money."""
    intrinsic = max(0.0, spot - strike) if opt == "CE" else max(0.0, strike - spot)
    return round(intrinsic + max(5.0, 120 - 0.4 * abs(spot - strike)), 2)


def quotes(spot, bump=0.0, spread=1.0):
    q = {}
    for k in STRIKES:
        for o in ("CE", "PE"):
            p = premium(o, k, spot) + bump
            q[f"NFO:NIFTY{k}{o}"] = {"bid": p - spread / 2, "ask": p + spread / 2, "ltp": p}
    return q


def at(hm, day=24):
    h, m = map(int, hm.split(":"))
    return datetime(2026, 9, day, h, m, tzinfo=IST)


def straddle(**kw):
    base = {"name": "Short straddle", "underlying": "NIFTY", "legs": [
        {"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0}],
        "timing": {"entry": "09:30", "lastEntry": "14:45", "squareoff": "15:15", "maxEntries": 1, "cooldown": 0},
        "risk": {"stopType": "amount", "stop": 5000}, "costs": {"brokerage": 20, "slippageTicks": 0, "freeze": 0}}
    for k, v in kw.items():
        base[k] = {**base.get(k, {}), **v} if isinstance(v, dict) else v
    return OptionStrategy(**base)


def test_contracts_strikes_and_points():
    c = contracts()
    assert c.step(25000) == 50 and c.atm(25012) == 25000 and c.atm(25030) == 25050
    assert c.strike_for(25000, "CE", 2, "strikes") == 25100 and c.strike_for(25000, "PE", 2, "strikes") == 24900
    assert c.strike_for(25000, "CE", 320, "points") == 25300 and c.strike_for(25000, "PE", 320, "points") == 24700
    assert c.strike_for(25000, "CE", 50, "strikes") is None


def test_fills_use_bid_and_ask():
    q = {"bid": 100.0, "ask": 101.0, "ltp": 100.5}
    assert fill_price(q, "sell", 0) == 100.0 and fill_price(q, "buy", 0) == 101.0
    assert fill_price(q, "sell", 2) == 99.9 and fill_price(q, "buy", 2) == 101.1
    assert fill_price({"bid": 0, "ask": 0, "ltp": 50}, "sell", 0) == 50
    assert fill_price({"ltp": None}, "sell", 0) is None


def test_waits_for_entry_time_and_live_prices():
    e, c = OptionsEngine(straddle()), contracts()
    assert e.step(at("09:20"), 25000, c, quotes(25000), True) == []
    assert e.step(at("09:31"), 25000, c, quotes(25000), False) == [] and "live prices" in e.note
    out = e.step(at("09:31"), 25010, c, quotes(25010), True)
    assert [(x["side"], x["sym"]) for x in out] == [("sell", "NIFTY25000CE"), ("sell", "NIFTY25000PE")]
    # sold at the bid: each leg's premium at 25010 less half the spread
    assert out[0]["px"] == premium("CE", 25000, 25010) - 0.5 and out[0]["qty"] == 75
    assert e.pos["credit"] == pytest.approx(75 * (premium("CE", 25000, 25010) + premium("PE", 25000, 25010) - 1))


def test_stop_loss_on_mtm_and_one_entry_a_day():
    e, c = OptionsEngine(straddle()), contracts()
    e.step(at("09:30"), 25000, c, quotes(25000), True)
    e.step(at("10:00"), 25000, c, quotes(25000, bump=30), True)          # 2 legs x 30 x 75 = -4,500 (+spread): holds
    assert e.pos
    out = e.step(at("10:05"), 25000, c, quotes(25000, bump=40), True)    # -6,000: stopped
    assert e.pos is None and {x["why"] for x in out} == {"Stop loss"}
    t = e.trades[-1]
    assert t["gross"] == pytest.approx(-75 * 2 * (40 + 1)) and t["costs"] > 0 and t["pnl"] < t["gross"]
    assert e.step(at("11:00"), 25000, c, quotes(25000), True) == []      # max one entry a day
    assert e.step(at("09:30", day=25), 25000, c, quotes(25000), True)    # a new day, a new entry


def test_credit_pct_target_and_trailing():
    e, c = OptionsEngine(straddle(risk={"stopType": "none", "tgtType": "credit_pct", "tgt": 20})), contracts()
    e.step(at("09:30"), 25000, c, quotes(25000), True)
    credit = e.pos["credit"]
    e.step(at("10:00"), 25000, c, quotes(25000, bump=-20), True)
    assert e.pos   # (20 - 1) x 150 = 2,850, under 20% of about 36,000
    e.step(at("10:10"), 25000, c, quotes(25000, bump=-50), True)
    assert e.pos is None and e.trades[-1]["why"] == "Target" and e.trades[-1]["gross"] >= 0.2 * credit
    e2 = OptionsEngine(straddle(risk={"stopType": "none", "trailAfter": 3000, "trailBy": 1500}))
    e2.step(at("09:30"), 25000, c, quotes(25000), True)
    e2.step(at("10:00"), 25000, c, quotes(25000, bump=-30), True)        # up 4,350
    e2.step(at("10:05"), 25000, c, quotes(25000, bump=-25), True)        # gave back 750: holds
    assert e2.pos
    e2.step(at("10:10"), 25000, c, quotes(25000, bump=-15), True)        # gave back 2,250: trailed out
    assert e2.pos is None and e2.trades[-1]["why"] == "Trailing stop"


def test_leg_stop_closes_one_side_and_hedges_follow():
    s = straddle(structure="iron_fly", risk={"stopType": "none", "legStopPct": 50}, legs=[
        {"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0},
        {"side": "buy", "opt": "CE", "offset": 4}, {"side": "buy", "opt": "PE", "offset": 4}])
    e, c = OptionsEngine(s), contracts()
    out = e.step(at("09:30"), 25000, c, quotes(25000), True)
    assert [x["side"] for x in out] == ["buy", "buy", "sell", "sell"]   # hedges first
    out = e.step(at("10:00"), 25150, c, quotes(25150), True)           # the call is now well in the money
    assert [(x["sym"], x["why"]) for x in out] == [("NIFTY25000CE", "Leg stop")]
    assert e.pos and sum(l["open"] for l in e.pos["legs"]) == 3
    out = e.step(at("10:30"), 24800, c, quotes(24800), True)
    assert e.pos is None and e.trades[-1]["why"] == "Leg stops hit" and len(out) == 3


def test_recentre_rolls_the_sold_legs_only():
    s = straddle(risk={"stopType": "none"}, recenter={"enabled": True, "every": 30, "threshold": 2, "roll": "shorts"},
                 legs=[{"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0},
                       {"side": "buy", "opt": "CE", "offset": 6}, {"side": "buy", "opt": "PE", "offset": 6}])
    e, c = OptionsEngine(s), contracts()
    e.step(at("09:30"), 25000, c, quotes(25000), True)
    assert e.step(at("09:45"), 25200, c, quotes(25200), True) == []    # not time to check yet
    assert e.step(at("10:00"), 25060, c, quotes(25060), True) == []    # checked: one strike isn't enough
    out = e.step(at("10:30"), 25120, c, quotes(25120), True)
    assert [(x["side"], x["sym"]) for x in out] == [("buy", "NIFTY25000CE"), ("buy", "NIFTY25000PE"),
                                                   ("sell", "NIFTY25100CE"), ("sell", "NIFTY25100PE")]
    assert e.pos["center"] == 25100 and e.pos["rolls"] == 1
    assert {l["sym"] for l in e.pos["legs"] if l["open"]} == {"NIFTY25100CE", "NIFTY25100PE", "NIFTY25300CE", "NIFTY24700PE"}


def test_square_off_daily_cap_and_cooldown():
    e, c = OptionsEngine(straddle(timing={"maxEntries": 3, "cooldown": 60}, risk={"stopType": "none"})), contracts()
    e.step(at("09:30"), 25000, c, quotes(25000), True)
    e.step(at("15:15"), 25000, c, quotes(25000), True)
    assert e.pos is None and e.trades[-1]["why"] == "Square-off"
    assert e.step(at("15:20"), 25000, c, quotes(25000), True) == []

    e = OptionsEngine(straddle(timing={"maxEntries": 3, "cooldown": 60}, risk={"stopType": "amount", "stop": 3000, "dailyLoss": 5000}))
    e.step(at("09:30"), 25000, c, quotes(25000), True)
    e.step(at("09:40"), 25000, c, quotes(25000, bump=25), True)        # -3,900: stop
    assert e.pos is None and e.cool_until
    assert e.step(at("10:00"), 25000, c, quotes(25000), True) == []    # cooling down
    assert e.step(at("10:41"), 25000, c, quotes(25000), True)          # second entry
    e.step(at("10:50"), 25000, c, quotes(25000, bump=12), True)        # -1,950 today plus the -3,900 before: cap
    assert e.pos is None and e.trades[-1]["why"] == "Daily loss cap" and e.halted
    assert e.step(at("13:00"), 25000, c, quotes(25000), True) == []


def test_freeze_limit_splits_orders_and_margin_sizing():
    calls = []

    def margin(legs):
        calls.append(sum(l["qty"] for l in legs))
        return 1.0 * sum(l["qty"] for l in legs) * 1000   # 1,000 of margin per unit

    s = straddle(sizing={"mode": "margin", "capital": 5000000, "safety": 0.98}, costs={"freeze": 1800})
    e, c = OptionsEngine(s, margin_fn=margin), contracts()
    out = e.step(at("09:30"), 25000, c, quotes(25000), True)
    # one unit is 150 units of margin = 150,000; 4.9M / 150k = 32 units = 2,400 per leg = 2 slices each
    assert e.pos["units"] == 32 and out[0]["qty"] == 2400 and out[0]["slices"] == 2 and e.pos["orders"] == 4
    e2 = OptionsEngine(straddle(sizing={"mode": "margin", "capital": 100000}), margin_fn=lambda legs: None)
    e2.step(at("09:30"), 25000, c, quotes(25000), True)
    assert e2.pos["units"] == 1 and "margin" in e2.note


def test_state_round_trip():
    e, c = OptionsEngine(straddle()), contracts()
    e.step(at("09:30"), 25000, c, quotes(25000), True)
    e2 = OptionsEngine(straddle(), state=e.dump())
    assert e2.pos["legs"] == e.pos["legs"] and e2.entries_today == 1
    e2.step(at("10:05"), 25000, c, quotes(25000, bump=40), True)
    assert e2.trades[-1]["why"] == "Stop loss"


def test_detects_option_structures_only():
    straddle_cfg = '{"structure": {"type": "short_straddle_with_wings", "short_legs": ["ATM CE (SELL)"], "hedge_legs": []}}'
    momentum_cfg = '{"entry": {"signal": "day change"}, "token": {"$comment": "waits for the straddle bot"}}'
    assert oi.is_options(straddle_cfg, "json") and not oi.is_options(momentum_cfg, "json")
    assert oi.is_options("sell a short straddle at 9:20 with a 30% stop", "words")


def test_parse_ai_answer_keeps_what_validates():
    s, notes = oi.parse_ai({"name": "Iron fly", "structure": "iron_fly", "exchange": "NFO", "underlying": "NIFTY",
                            "offsetUnit": "points", "legs": [{"side": "sell", "opt": "CE", "offset": 0},
                                                             {"side": "buy", "opt": "CE", "offset": 800},
                                                             {"side": "sell", "opt": "XX"}],
                            "timing": {"entry": "9:30"}, "risk": {"stopType": "amount", "stop": 50000},
                            "notes": ["SL-limit orders are simulated as fills at the bid/ask"]})
    assert len(s.legs) == 2 and s.risk.stop == 50000 and s.timing.entry == "09:30"
    assert any("leg" in n for n in notes) and any("timing" in n for n in notes)


def test_missing_leg_is_named_and_old_notes_clear_after_hours():
    e, c = OptionsEngine(straddle()), contracts()
    q = quotes(25000)
    q["NFO:NIFTY25000PE"] = {"bid": 0, "ask": 0, "ltp": 0}          # one leg with no price at all
    assert e.step(at("09:31"), 25000, c, q, True) == []
    assert "25000 PE (sell)" in e.note and "25000 CE" not in e.note
    # after the entry window the note says why nothing happens, instead of the morning's quote problem
    assert e.step(at("15:40"), 25000, c, q, False) == [] and "Entries stop at 14:45" in e.note
    assert e.step(at("09:00", day=25), 25000, c, q, False) == [] and e.note == ""


# ---------- leg stops on long structures, expiry times per exchange, settlement, tick on the Greeks/roll endpoints ----------
def test_a_long_structure_with_a_leg_stop_stays_open_on_unchanged_quotes():
    s = straddle(legs=[{"side": "buy", "opt": "CE", "offset": 0}, {"side": "buy", "opt": "PE", "offset": 0}],
                 risk={"stopType": "none", "legStopPct": 30})
    e, c = OptionsEngine(s), contracts()
    e.step(at("09:31"), 25000, c, quotes(25000), True)
    assert e.step(at("09:36"), 25000, c, quotes(25000), True) == [] and e.pos


def test_expiry_time_per_exchange_and_mcx_across_us_daylight_saving():
    from datetime import date
    from app.options.data import expiry_time, expired_today
    assert expiry_time("NFO", date(2026, 10, 14)) == "15:40" and expiry_time("CDS") == "12:30"
    assert expiry_time("MCX", date(2026, 10, 14)) == "23:30" and expiry_time("MCX", date(2026, 11, 2)) == "23:55"
    assert expiry_time("MCX", date(2027, 3, 5)) == "23:55" and expiry_time("MCX", date(2027, 3, 15)) == "23:30"
    assert not expired_today("NFO", datetime(2026, 10, 14, 15, 35, tzinfo=IST))
    assert expired_today("NFO", datetime(2026, 10, 14, 15, 40, tzinfo=IST))


def cds_contracts(expiry="2026-09-24"):
    rows = [{"opt": o, "strike": k, "symbol": f"USDINR{k:g}{o}"} for k in (95.0, 96.0, 97.0) for o in ("CE", "PE")]
    return Contracts(rows, 1000, expiry, "CDS")


def cds_strategy():
    return OptionStrategy(name="Short call", underlying="USDINR", exchange="CDS",
                          legs=[{"side": "sell", "opt": "CE", "offset": 0}],
                          timing={"entry": "09:30", "lastEntry": "16:15", "squareoff": "16:45", "maxEntries": 1, "cooldown": 0},
                          risk={"stopType": "none"}, costs={"brokerage": 0, "slippageTicks": 0, "freeze": 0})


def test_a_currency_option_settles_at_the_underlying_after_12_30_and_says_it_is_an_estimate():
    q = {"CDS:USDINR96CE": {"bid": 0.5, "ask": 0.51, "ltp": 0.5}}
    e, c = OptionsEngine(cds_strategy(), settle_fn=lambda ex: 96.0), cds_contracts()
    e.step(at("09:31"), 96.0, c, q, True)
    assert e.step(at("12:29"), 96.0, c, q, True) == []
    out = e.step(at("12:30"), 96.0, c, q, True)
    assert out[0]["px"] == 0.0 and "estimate" in out[0]["why"] and "RBI reference rate" in out[0]["why"]
    assert e.pos is None and e.trades[-1]["why"] == "Expiry settlement"


def test_no_entry_on_expiry_day_after_the_exchange_stopped_trading():
    q = {"CDS:USDINR96CE": {"bid": 0.5, "ask": 0.51, "ltp": 0.5}}
    e, c = OptionsEngine(cds_strategy()), cds_contracts()
    assert e.step(at("13:00"), 96.0, c, q, True) == [] and e.pos is None and "expired" in e.note
    assert e.step(at("12:00"), 96.0, c, q, True)          # before 12:30 it enters


def test_greeks_and_roll_price_a_currency_option_at_its_own_tick(monkeypatch):
    from app import main
    c = cds_contracts()
    monkeypatch.setattr(main, "_held", lambda req, expiry=None: (c, 96.0, {}))
    monkeypatch.setattr(main.options_data, "quotes", lambda keys: {k: {"bid": 0.0125, "ask": 0.015, "ltp": 0.0125} for k in keys})
    monkeypatch.setattr(main.opt_greeks, "position", lambda legs, m: {"legs": [{} for _ in legs]})
    monkeypatch.setattr(main.opt_charges, "orders_cost", lambda orders, kind, b, f: seen.append(orders) or {"total": 0, "orders": 1, "items": []})
    monkeypatch.setattr(main.opt_charges, "labelled", lambda items, kind: items)
    monkeypatch.setattr(main.opt_greeks, "public_model", lambda m: {})
    seen = []
    from app.models import OptGreeksReq
    req = OptGreeksReq(exchange="CDS", underlying="USDINR", expiry="2026-09-24",
                       legs=[{"side": "sell", "opt": "CE", "strike": 96.0, "qty": 1000, "fill": 0.02}])
    main.options_greeks(req, profile={})
    assert seen[-1][0]["fill"] == 0.015              # not floored to 0.05


def test_a_currency_structure_with_a_dead_hedge_does_not_enter():
    # the sold call is live, the bought hedge has only a stale last price: no entry, none counted
    s = cds_strategy().model_copy(update={"legs": cds_strategy().legs + [cds_strategy().legs[0].model_copy(update={"side": "buy", "offset": 1})]})
    q = {"CDS:USDINR96CE": {"bid": 0.5, "ask": 0.51, "ltp": 0.5},
         "CDS:USDINR97CE": {"ltp": 0.1, "bid": None, "ask": None, "volume": 0}}
    e, c = OptionsEngine(s), cds_contracts("2026-09-30")
    assert e.step(at("09:31"), 96.0, c, q, True) == []
    assert e.pos is None and e.entries_today == 0 and "97 CE (buy)" in e.note


def test_a_leg_that_fails_to_open_closes_the_others_and_the_entry_is_not_counted(monkeypatch):
    e, c = OptionsEngine(straddle(timing={"cooldown": 30})), contracts()
    real = e._open_leg
    monkeypatch.setattr(e, "_open_leg", lambda now, cs, q, opt, *a, **k: opt != "PE" and real(now, cs, q, opt, *a, **k))
    out = e.step(at("09:31"), 25000, c, quotes(25000), True)
    assert [(x["side"], x["sym"]) for x in out] == [("sell", "NIFTY25000CE"), ("buy", "NIFTY25000CE")]
    assert e.pos is None and e.entries_today == 0 and e.cool_until is None
    assert e.trades[-1]["why"] == "A leg couldn't open"


class StubData:
    kite = None

    def __init__(self):
        self.loads = 0

    def margin(self, legs):
        return None

    def expiries(self, exchange, underlying):
        return ["2026-09-29"]

    def contracts(self, exchange, underlying, expiry):
        self.loads += 1
        return contracts()

    def spot_key(self, exchange, underlying, expiry):
        return "NSE:NIFTY 50"

    def quotes(self, keys):
        return {"NSE:NIFTY 50": {"ltp": 25000.0}, **quotes(25000)}

    def fresh(self, q, now):
        return True


def opt_row(strategy, state=None):
    return {"id": "o1", "user_id": "u", "name": "x", "strategy": strategy.model_dump(), "instrument": {"market": "IN"},
            "started_at": "2026-09-24T09:00:00+05:30", "state": state}


def test_a_restarted_session_with_a_position_open_loads_its_contracts():
    from app.options.session import OptionSession
    e = OptionsEngine(straddle())
    e.step(at("09:31"), 25000, contracts(), quotes(25000), True)
    data = StubData()
    s = OptionSession(None, opt_row(straddle(), e.dump()), data)
    assert s.engine.pos and s.contracts is None
    s.on_timer(at("09:40"))
    assert data.loads == 1 and s.snapshot()["expiry"] == "2026-09-29" and s.snapshot()["lot"] == 75


def test_mcx_and_cds_sessions_are_reported_at_their_own_exchange_close():
    from app.options.session import OptionSession
    assert OptionSession(None, opt_row(cds_strategy()), StubData()).market == "CDS"
    assert OptionSession(None, opt_row(straddle()), StubData()).market == "IN"


def test_a_sold_leg_stop_judges_the_middle_not_the_ask_it_exits_at():
    s = straddle(legs=[{"side": "sell", "opt": "CE", "offset": 0}], risk={"stopType": "none", "legStopPct": 20})
    e, c = OptionsEngine(s), contracts()
    q = {"NFO:NIFTY25000CE": {"bid": 5.0, "ask": 6.0, "ltp": 5.5}}
    e.step(at("09:31"), 25000, c, q, True)
    assert e.pos["legs"][0]["entry"] == 5.0
    assert e.step(at("09:36"), 25000, c, q, True) == [] and e.pos       # same quotes: no stop
    q = {"NFO:NIFTY25000CE": {"bid": 6.0, "ask": 7.0, "ltp": 6.5}}      # middle 6.5 is +30%
    out = e.step(at("09:41"), 25000, c, q, True)
    assert out and out[0]["why"] == "Leg stop" and out[0]["px"] == 7.0  # still exits at the ask


class SettleData:
    """OptionsData.settlement_price's collaborators."""
    kite = type("K", (), {"by_symbol": lambda self, sym, ex: {"symbol": sym, "token": 1}})()

    def spot_key(self, exchange, name, expiry):
        return "MCX:CRUDEOILFUT"

    def spot(self, exchange, name, expiry):
        return 6500.0, {}, "quote"


def test_mcx_and_cds_settle_at_the_expiry_days_close_when_checked_long_after_it(monkeypatch):
    from app.options.data import OptionsData
    from app import live
    monkeypatch.setattr(live, "official_close", lambda kite, inst, day: 6400.0 if day == "2026-09-24" else None)
    d = SettleData()
    assert OptionsData.settlement_price(d, "MCX", "CRUDEOIL", "2026-09-24") == 6400.0       # expiry passed days ago
    assert OptionsData.settlement_price(d, "MCX", "CRUDEOIL", "2026-09-23") is None         # no candle: hold the leg
    assert OptionsData.settlement_price(d, "MCX", "CRUDEOIL", "2099-01-29") == 6500.0       # at the time: the live price
