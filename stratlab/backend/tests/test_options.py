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
