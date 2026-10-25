"""Review DB (24 Oct 2026, the options builder, imports, paper sessions, chart replay and the journal): each test is built
on what the reviewer saw."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import journal as J
from app import main, positioning as P, replay as R, risk
from app.engine import costs as C
from app.main import app
from app.options import importer as oi
from app.options.recorded import Recorded, lot_from_oi

from . import fake_positioning as FP

EXPORT = {"stratlab": "options", "version": 1, "strategy": {
    "name": "NIFTY iron condor", "structure": "iron_condor", "exchange": "NFO", "underlying": "NIFTY", "expiry": "current",
    "offsetUnit": "strikes",
    "legs": [{"side": "sell", "opt": "CE", "offset": 4, "lots": 1}, {"side": "sell", "opt": "PE", "offset": 4, "lots": 1},
             {"side": "buy", "opt": "CE", "offset": 8, "lots": 1}, {"side": "buy", "opt": "PE", "offset": 8, "lots": 1}],
    "timing": {"entry": "09:30", "lastEntry": "14:45", "squareoff": "15:15", "maxEntries": 1, "cooldown": 0},
    "risk": {"stopType": "credit_pct", "stop": 30, "tgtType": "none", "tgt": 0, "trailAfter": 0, "trailBy": 0, "legStopPct": 0, "dailyLoss": 0},
    "costs": {"brokerage": 20, "slippageTicks": 0, "freeze": 0}}}


def export(change) -> tuple:
    d = json.loads(json.dumps(EXPORT))
    change(d["strategy"])
    return oi.from_export(json.dumps(d))


# ---------- DB-002: an export with a leg out of range keeps the leg, clamped, and says why ----------
def test_an_export_with_100000_lots_keeps_all_four_legs_clamped_and_says_the_range():
    s, notes = export(lambda s: s["legs"][0].update(lots=100000))
    assert len(s.legs) == 4 and s.legs[0].lots == 50 and s.legs[0].side == "sell" and s.legs[0].opt == "CE"
    assert notes == ["Leg 1: lots must be 1–50; 100,000 was set to 50."]
    assert s.structure == "custom"                          # no longer an iron condor's card
    assert not any("{" in n for n in notes)                 # never a raw dict
    s, notes = export(lambda s: s["legs"][0].update(lots=0))
    assert len(s.legs) == 4 and s.legs[0].lots == 1 and "lots must be 1–50; 0 was set to 1" in notes[0]
    s, notes = export(lambda s: s["legs"][0].update(offset=9999))
    assert len(s.legs) == 4 and s.legs[0].offset == 5000 and "between −5,000 and 5,000; 9,999 was set to 5,000" in notes[0]
    # never through the AI: the import answers without it
    assert oi.from_json(json.dumps(EXPORT)).structure == "iron_condor"


def test_the_ai_path_names_a_dropped_leg_in_words():
    s, notes = oi.parse_ai({"underlying": "NIFTY", "structure": "iron_condor",
                            "legs": [{"side": "sell", "opt": "CE", "offset": 4, "lots": 100000}, {"side": "sell", "opt": "XX"}]})
    assert len(s.legs) == 1 and s.legs[0].lots == 50 and s.structure == "custom"
    assert all("{" not in n for n in notes) and any("lots must be 1–50" in n for n in notes)
    assert any("Left out leg 2 (sell ?)" in n for n in notes)


# ---------- DB-003: values "fixed" silently are said ----------
def test_negative_lots_a_negative_stop_and_a_word_for_a_target_are_said_and_switched_off():
    s, notes = export(lambda s: s["legs"][1].update(lots=-3))
    assert s.legs[1].lots == 1 and notes == ["Leg 2: lots must be 1–50; −3 was set to 1."]
    s, notes = export(lambda s: s["risk"].update(stop=-50))
    assert s.risk.stopType == "none" and "(−50)" in notes[0] and "there's no stop" in notes[0]
    s, notes = export(lambda s: s["risk"].update(tgtType="credit_pct", tgt="abc"))
    assert s.risk.tgtType == "none" and s.risk.tgt == 0 and "there's no target" in notes[0]
    assert not any("placeholder" in n or "non-numeric" in n for n in notes)


def test_a_bad_entry_time_a_past_expiry_and_a_500pct_stop_are_said():
    s, notes = export(lambda s: s["timing"].update(entry="25:99"))
    assert s.timing.entry == "09:30" and notes == ['Entry time couldn\'t be read ("25:99"), so it is 09:30, the default.']
    s, notes = export(lambda s: s.update(expiry="2020-01-01"))
    assert s.expiry == "current" and notes == ["The expiry 2020-01-01 has passed, so the nearest expiry is used."]
    s, notes = export(lambda s: s["risk"].update(stop=500))
    assert s.risk.stop == 500 and "5 times the premium" in notes[0]
    s, notes = export(lambda s: s["timing"].update(entry="16:00", lastEntry="08:00", squareoff="09:00"))
    assert s.timing.entry == "09:30" and "default times" in notes[0]


def test_the_import_route_sends_the_notes_and_never_asks_the_ai(monkeypatch):
    monkeypatch.setattr(main, "import_options", main.import_options)
    called = []
    monkeypatch.setattr(main.ai_writer, "ask_json", lambda *a, **k: called.append(1) or {})
    d = json.loads(json.dumps(EXPORT))
    d["strategy"]["legs"][0]["lots"] = 100000
    out = main.import_options(json.dumps(d), {"id": "u"})
    assert not called and not out["used_ai"] and len(out["strategy"]["legs"]) == 4 and out["notes"]


# ---------- DB-001: offline, the builder prices on the last recorded chain ----------
AT = datetime(2026, 10, 23, 15, 41, tzinfo=P.IST)


def recording(lot=None):
    rows = FP.chain(22600.0, 0.14, "2026-10-27", AT)
    for r in rows:                                          # open interest in whole lots of 65, as the exchange's is
        r[4], r[8] = r[4] // 65 * 65, r[8] // 65 * 65
    return {"expiry": "2026-10-27", "expiries": ["2026-10-27", "2026-11-03"], "spot": 22600.0, "chain": rows,
            "taken_at": AT.isoformat(timespec="minutes"), "source": "recorded", "lot": lot}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(main.options_data, "ready", lambda: False)
    monkeypatch.setattr(P, "recorded_chain", lambda name, choice, today, now=None: recording() if name == "NIFTY" else None)
    monkeypatch.setattr(P, "ist_now", lambda: datetime(2026, 10, 24, 20, 0, tzinfo=P.IST))     # Saturday evening
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "pro", "plan": "pro"}
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_lot_is_read_off_the_open_interest_when_the_recording_has_none():
    assert lot_from_oi(recording()["chain"]) == 65
    assert Recorded("NFO", "NIFTY", recording()).lot == 65 and Recorded("NFO", "NIFTY", recording(lot=75)).lot == 75
    assert lot_from_oi([[22600, 1, 1, 1, 130, 1, 1, 1, 65]]) is None          # too few strikes to tell


def test_offline_the_chain_is_the_recorded_one_marked_as_of_its_time(offline):
    ch = offline.get("/options/chain", params={"exchange": "NFO", "underlying": "NIFTY"}).json()
    assert ch["recorded"] and ch["as_of"] == AT.isoformat(timespec="minutes") and ch["lot"] == 65 and ch["step"] == 50
    assert ch["spot"] == 22600 and len(ch["rows"]) == 21 and ch["rows"][10]["ce"]["oi"] > 0
    assert ch["model"] and ch["rows"][10]["ce_g"]["iv"] == pytest.approx(0.14, abs=0.01)
    # an underlying with no recording is offline, as before
    r = offline.get("/options/chain", params={"exchange": "MCX", "underlying": "CRUDEOIL"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "data_offline"
    us = offline.get("/options/recorded").json()
    assert [u["name"] for u in us] == ["NIFTY"] and us[0]["lot"] == 65 and us[0]["expiries"][0] == "2026-10-27" and us[0]["freeze"] > 0


def test_offline_the_preview_prices_a_condor_on_the_recording_with_greeks_and_breakevens(offline):
    pv = offline.post("/options/preview", json={"strategy": EXPORT["strategy"]}).json()
    assert pv["recorded"] and pv["as_of"] == AT.isoformat(timespec="minutes") and pv["lot"] == 65
    assert [l["strike"] for l in pv["legs"]] == [22800, 22400, 23000, 22200] and all(l["fill"] for l in pv["legs"])
    assert all(l["sym"] is None for l in pv["legs"]) and pv["margin"] is None
    assert pv["charges"]["breakevens"] and len(pv["charges"]["breakevens"]) == 2 and pv["greeks"]["net"] is not None
    assert pv["model"]["as_of"].startswith("2026-10-23T15:41")
    # a session still needs the live feed
    assert offline.post("/options/sessions", json={"strategy": EXPORT["strategy"]}).status_code == 503


# ---------- DB-022: the session chart's candles keep their volume ----------
def test_a_sessions_candles_carry_their_volume():
    from app.live import chart_bar
    assert chart_bar({"t": "x", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 12.5, "extra": 1}) == {"t": "x", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 12.5}
    assert "v" not in chart_bar({"t": "x", "o": 1, "h": 2, "l": 0.5, "c": 1.5})


# ---------- DB-023: crypto's day is today, not the US calendar's last session ----------
def test_a_crypto_session_on_a_saturday_is_today_not_fridays_session():
    s = {"id": "a", "name": "BTC", "instrument": {"currency": "USD", "market": "CRYPTO"},
         "account": {"capital": 10000, "equity": 9985, "trades": 1}, "equity_curve": [{"t": "2026-10-23T20:00", "eq": 9990}]}
    out = risk.summary([s], today="2026-10-24")
    assert out["currencies"][0]["session"] == "2026-10-24" and out["currencies"][0]["session_pnl"] is None
    us = {**s, "id": "b", "instrument": {"currency": "USD", "market": "US"}}
    both = risk.summary([s, us], today="2026-10-24")["currencies"][0]
    assert both["session_pnl"] is None                                  # one session moves today: the day is "Today"
    assert risk.summary([us], today="2026-10-24")["currencies"][0]["session"] == "2026-10-23"


# ---------- DB-032: a practice order worth trillions is refused ----------
def test_a_practice_order_worth_more_than_about_ten_million_dollars_is_refused():
    bars = [{"t": "2026-01-01", "o": 4590, "h": 4600, "l": 4500, "c": 4590}]
    huge = [{"i": 0, "action": "long", "qty": 1_000_000_000.0}]
    assert "worth more than 10,000,000 in USD" in R.too_big(huge, bars, "USD")
    assert R.too_big([{"i": 0, "action": "long", "qty": 100.0}], bars, "USD") is None
    assert R.too_big([{"i": 0, "action": "long", "qty": 100_000.0}], bars, "INR") is None     # ₹45.9 crore
    assert R.too_big([{"i": 0, "action": "long", "qty": 300_000.0}], bars, "INR")             # ₹137.7 crore


# ---------- DB-040: the DP charge on a delivery sale ----------
def test_a_delivery_sale_pays_the_dp_charge_once_a_day_and_intraday_none():
    assert C.dp_charge() == 15.34
    s = J.clean_settings({})
    m = [{"id": "m1", "sym": "INFY", "side": "long", "ed": "2026-10-20", "xd": "2026-10-22", "qty": 10, "entry": 1500.0, "exit": 1560.0}]
    t = J.manual_trades(m, s)[0]
    base = C.total(C.order_costs("in_eq", "buy", 10, 1500, 0)) + C.total(C.order_costs("in_eq", "sell", 10, 1560, 0))
    assert t["charges"] == pytest.approx(base + 15.34) and round(t["charges"], 2) == pytest.approx(49.33, abs=0.05)
    intraday = J.manual_trades([{**m[0], "xd": "2026-10-20"}], s)[0]
    assert intraday["charges"] == pytest.approx(C.total(C.order_costs("in_eq_mis", "buy", 10, 1500, 20)) + C.total(C.order_costs("in_eq_mis", "sell", 10, 1560, 20)))
    fills = [{"d": "2026-10-01", "side": "B", "qty": 10, "price": 100, "symbol": "ITC"},
             {"d": "2026-10-05", "side": "S", "qty": 4, "price": 110, "symbol": "ITC"},
             {"d": "2026-10-05", "side": "S", "qty": 2, "price": 111, "symbol": "ITC"},
             {"d": "2026-10-07", "side": "S", "qty": 4, "price": 112, "symbol": "ITC"}]
    got = J.pair_fills(fills, s, date(2026, 10, 10))[0][0]
    rates = sum(C.total(C.order_costs("in_eq", sd, q, p, 0)) for sd, q, p in (("buy", 10, 100), ("sell", 4, 110), ("sell", 2, 111), ("sell", 4, 112)))
    assert got["charges"] == pytest.approx(rates + 2 * 15.34)          # two sale days
    assert "depository (DP) charge" in J.ASSUMPTIONS


# ---------- DB-041: one trade is one trade, and the charges' share is one figure ----------
def test_one_trade_is_said_in_the_singular_and_the_charges_share_matches_the_summary():
    assert J.win_rate_line(1, 1) == "With 1 trade, a 100% win rate could easily be luck: tossing a coin once gives a head 50% of the time."
    assert "tossing a coin twice gives 2 heads" in J.win_rate_line(2, 2)
    assert "23 times gives 14 or more heads" in J.win_rate_line(23, 14)
    ts = [{"gross": g, "charges": c, "net": g - c} for g, c in ((1000, 50), (800, 60), (250, 43), (500, 0), (-500, 0))]
    c = J.check_costs(ts)
    assert c["data"]["pct"] == J.summary([{**t, "entry_t": "2026-01-01", "exit_t": "2026-01-02", "hold_days": 1} for t in ts])["charges_pct"]
    assert f"Charges took {c['data']['pct']:.1f}% of the gross profit" in c["detail"]


# ---------- DB-043: a stop on the wrong side of the entry is refused ----------
def test_a_shorts_stop_below_its_entry_is_refused_and_one_above_it_kept():
    assert J.plan_problem("short", 3000, 2950, None) == "A short's planned stop goes above its entry of 3,000."
    assert J.plan_problem("short", 3000, 3050, 2900) is None
    assert J.plan_problem("long", 1500.5, 1490, 1400) == "A long's planned target goes above its entry of 1,500.5."
    assert J.plan_problem(None, 3000, 2950, None) is None


# ---------- DB-044: one trade gets no cost-sensitivity pass ----------
def test_cost_sensitivity_is_not_judged_on_one_trade():
    one = J.check_costs([{"gross": 600, "charges": 34, "net": 566}])
    assert one["status"] == "skip" and "Too few trades" in one["detail"]
