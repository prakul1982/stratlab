"""Option Greeks and the payoff before expiry (options/greeks.py): Black-76 prices and Greeks against published values
and finite differences, put-call parity, the what-if scenarios, the model built from a chain's quotes, the API routes,
and the fixture the frontend's port (src/lib/greeks.ts) is checked against (it must match this module)."""
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app
from app.options import greeks as G
from app.plans import FEATURE_PLAN
from tests.fake_options_kite import _expiries
from tests.test_options_api import setup

FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "unit" / "fixtures" / "greeks.json"
IST = G.IST


# ---------- Black-76 ----------
def test_prices_match_published_black76_values():
    # Hull, Options, Futures and Other Derivatives: a futures put, F = K = 20, r = 9%, 4 months, 25% vol: about 1.12
    assert G.black76(20, 20, 4 / 12, 0.25, "PE", 0.09) == pytest.approx(1.11664, abs=1e-5)
    # Haug, The Complete Guide to Option Pricing Formulas (Black-76): F = K = 19, T = 0.75, r = 10%, 28% vol: 1.7011
    assert G.black76(19, 19, 0.75, 0.28, "CE", 0.10) == pytest.approx(1.7011, abs=1e-4)
    assert G.black76(19, 19, 0.75, 0.28, "PE", 0.10) == pytest.approx(1.7011, abs=1e-4)
    # Haug's futures-option delta: F = 105, K = 100, T = 0.5, r = 10%, 36% vol: call 0.5946, put −0.3566
    assert G.greeks(105, 100, 0.5, 0.36, "CE", 0.10)["delta"] == pytest.approx(0.5946, abs=1e-4)
    assert G.greeks(105, 100, 0.5, 0.36, "PE", 0.10)["delta"] == pytest.approx(-0.3566, abs=1e-4)
    # no rate: the formula positioning.py has always used, unchanged
    from app import positioning as P
    assert P.black76(25000, 25100, 7 / 365, 0.12, "CE") == G.black76(25000, 25100, 7 / 365, 0.12, "CE", 0.0)


@pytest.mark.parametrize("kind", ["CE", "PE"])
@pytest.mark.parametrize("f,k,t,sigma", [(25000, 25000, 3 / 365, 0.12), (25000, 25600, 10 / 365, 0.16), (55000, 53000, 30 / 365, 0.2),
                                         (88.2, 88.5, 20 / 365, 0.05), (5600, 5400, 0.25, 0.45)])
def test_greeks_match_finite_differences(kind, f, k, t, sigma):
    r = G.RATE
    g = G.greeks(f, k, t, sigma, kind, r)
    p = lambda f=f, t=t, s=sigma: G.black76(f, k, t, s, kind, r)  # noqa: E731
    h = f * 1e-4
    assert g["price"] == p()
    assert g["delta"] == pytest.approx((p(f + h) - p(f - h)) / (2 * h), rel=1e-5, abs=1e-8)
    assert g["gamma"] == pytest.approx((p(f + h) - 2 * p() + p(f - h)) / h ** 2, rel=1e-3, abs=1e-9)
    assert g["vega"] == pytest.approx((p(s=sigma + 1e-4) - p(s=sigma - 1e-4)) / 2e-4 / 100, rel=1e-5)
    dt = 1e-6                    # theta: a calendar day passing is the time left shrinking, the forward held still
    assert g["theta"] == pytest.approx(-(p(t=t + dt) - p(t=t - dt)) / (2 * dt) / 365, rel=1e-4)


def test_put_call_parity_and_the_forward_from_it():
    for f, k, t, s, r in [(25000, 24500, 5 / 365, 0.13, 0.06), (25000, 26000, 40 / 365, 0.2, 0.06), (88.25, 87.75, 9 / 365, 0.04, 0.0),
                          (55000, 55000, 0.5 / 365, 0.3, 0.1)]:
        c, p = G.black76(f, k, t, s, "CE", r), G.black76(f, k, t, s, "PE", r)
        assert c - p == pytest.approx(math.exp(-r * t) * (f - k), abs=1e-7 * f)
        assert G.parity_forward(k, c, p, t, r) == pytest.approx(f, abs=1e-6 * f)
        gc, gp = G.greeks(f, k, t, s, "CE", r), G.greeks(f, k, t, s, "PE", r)
        assert gc["delta"] - gp["delta"] == pytest.approx(math.exp(-r * t))       # parity, differentiated
        assert gc["gamma"] == pytest.approx(gp["gamma"]) and gc["vega"] == pytest.approx(gp["vega"])


def test_implied_vol_round_trip_with_a_rate_and_its_limits():
    for kind in ("CE", "PE"):
        for sigma in (0.06, 0.15, 0.6):
            px = G.black76(25000, 25200, 6 / 365, sigma, kind, G.RATE)
            assert G.implied_vol(px, 25000, 25200, 6 / 365, kind, G.RATE) == pytest.approx(sigma, abs=1e-7)
    assert G.implied_vol(0.0, 25000, 25000, 0.02, "CE") is None
    assert G.implied_vol(30000, 25000, 25000, 0.02, "CE") is None
    assert G.implied_vol(float("nan"), 25000, 25000, 0.02, "CE") is None
    assert G.implied_vol(100, 25000, 25000, 0.02, "CE", float("inf")) is None


def test_at_expiry_an_option_is_its_intrinsic_value():
    assert G.greeks(25100, 25000, 0, 0.2, "CE") == {"price": 100, "delta": 1.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    assert G.greeks(25100, 25000, -0.01, 0.2, "PE")["price"] == 0 and G.greeks(24900, 25000, 0, 0.2, "PE")["delta"] == -1.0


def test_time_runs_to_the_close_on_expiry_day():
    at = datetime(2026, 10, 5, 9, 30, tzinfo=IST)
    assert G.years_to("2026-10-06", at) * 365 == pytest.approx(1 + 6 / 24)
    assert G.years_to("2026-10-05", datetime(2026, 10, 5, 15, 30, tzinfo=IST)) == 0


# ---------- what-if ----------
STRADDLE = [{"side": "sell", "opt": "CE", "strike": 25000.0, "qty": 75, "fill": 150.0, "iv": 0.11, "t": 4 / 365, "basis": 1.0008},
            {"side": "sell", "opt": "PE", "strike": 25000.0, "qty": 75, "fill": 140.0, "iv": 0.12, "t": 4 / 365, "basis": 1.0008}]


def test_scenario_now_is_the_model_value_less_the_fills():
    s = G.scenario(STRADDLE, 25000)
    want = sum(-75 * (G.black76(25000 * 1.0008, 25000, 4 / 365, lg["iv"], lg["opt"], G.RATE) - lg["fill"]) for lg in STRADDLE)
    assert s["pnl"] == pytest.approx(want)
    assert s["delta"] == pytest.approx(-75 * sum(G.greeks(25020, 25000, 4 / 365, lg["iv"], lg["opt"], G.RATE)["delta"] for lg in STRADDLE))
    assert s["theta"] > 0 and s["vega"] < 0 and s["gamma"] < 0          # a sold straddle: time helps it, volatility doesn't


def test_scenario_at_expiry_is_the_payoff_and_the_iv_floor_holds():
    days = 4
    for x in (24000, 24800, 25000, 25300, 26000):
        intrinsic = max(0, x - 25000) + max(0, 25000 - x)
        assert G.scenario(STRADDLE, x, days=days)["pnl"] == pytest.approx(75 * (290 - intrinsic))
        assert G.scenario(STRADDLE, x, days=days + 3)["pnl"] == G.scenario(STRADDLE, x, days=days)["pnl"]
    f, t, s = G.leg_inputs(STRADDLE[0], 25000, iv_shift=-50)
    assert s == G.MIN_VOL and t == STRADDLE[0]["t"] and f == pytest.approx(25020)
    f, t, _ = G.leg_inputs(STRADDLE[0], 25000, days=2)
    assert t == pytest.approx(2 / 365) and f == pytest.approx(25000 * 1.0008 ** 0.5)     # carry shrinks with the time left
    up, down = G.scenario(STRADDLE, 25000, iv_shift=2)["pnl"], G.scenario(STRADDLE, 25000, iv_shift=-2)["pnl"]
    assert up < G.scenario(STRADDLE, 25000)["pnl"] < down
    assert G.curve(STRADDLE, [24900, 25100], days=1) == [G.scenario(STRADDLE, x, days=1)["pnl"] for x in (24900, 25100)]


# ---------- from quotes ----------
def _q(px, spread=1.0):
    return {"bid": px - spread / 2, "ask": px + spread / 2, "ltp": px}


def test_model_takes_the_forward_from_parity_and_falls_back_to_the_spot():
    at = datetime(2026, 10, 5, 10, 0, tzinfo=IST)
    t = G.years_to("2026-10-08", at)
    f = 25060.0
    c, p = G.black76(f, 25050, t, 0.12, "CE", G.RATE), G.black76(f, 25050, t, 0.12, "PE", G.RATE)
    m = G.model(25000, "2026-10-08", 25050, _q(c), _q(p), at)
    assert m["forward_from"] == "parity" and m["forward"] == pytest.approx(f, abs=0.01) and m["basis"] == pytest.approx(f / 25000, abs=1e-6)
    assert m["atm_iv"] == pytest.approx(0.12, abs=1e-6) and m["days"] == pytest.approx(3 + 5.5 / 24, abs=1e-3) and m["rate"] == G.RATE
    assert G.model(25000, "2026-10-08", 25050, None, _q(p), at)["forward_from"] == "spot"
    assert G.model(25000, "2026-10-08", 25050, _q(5000), _q(1), at)["forward_from"] == "spot"     # a forward nowhere near the spot
    assert G.model(25000, "2026-10-01", 25050, _q(c), _q(p), at) is None                         # expired
    assert G.model(None, "2026-10-08", 25050, _q(c), _q(p), at) is None
    # each option's IV from its own middle; one whose price no volatility gives borrows the ATM IV, flagged
    o = G.option(_q(G.black76(f, 25300, t, 0.14, "CE", G.RATE), 0.2), 25300, "CE", m)
    assert o["iv"] == pytest.approx(0.14, abs=1e-4) and o["iv_from"] == "price" and 0 < o["delta"] < 0.5
    o = G.option({"bid": None, "ask": None, "ltp": 0.01}, 27000, "CE", m)
    assert o["iv_from"] in ("price", "atm")
    o = G.option({"bid": 0, "ask": 0, "ltp": 9000}, 25300, "CE", m)
    assert o["iv_from"] == "atm" and o["iv"] == m["atm_iv"]
    assert G.option(None, 25300, "CE", {**m, "atm_iv": None}) == {"mid": None, "iv": None, "iv_from": None}


def test_position_nets_the_legs_and_says_when_one_is_missing():
    at = datetime(2026, 10, 5, 10, 0, tzinfo=IST)
    m = G.model(25000, "2026-10-08", 25000, _q(160), _q(150), at)
    legs = [{"side": "sell", "opt": "CE", "strike": 25000, "qty": 75, "fill": 159.5, "quote": _q(160)},
            {"side": "buy", "opt": "PE", "strike": 24800, "qty": 150, "fill": 80.5, "quote": _q(80)}]
    pos = G.position(legs, m)
    assert pos["complete"] and len(pos["model_legs"]) == 2
    want = -75 * pos["legs"][0]["delta"] + 150 * pos["legs"][1]["delta"]
    assert pos["net"]["delta"] == pytest.approx(want, rel=1e-6)
    assert G.net(legs, pos["legs"])["vega"] == pytest.approx(pos["net"]["vega"], rel=1e-6)
    pos = G.position([*legs, {**legs[0], "fill": None, "quote": None}], {**m, "atm_iv": None})
    assert not pos["complete"] and pos["legs"][2]["iv"] is None


# ---------- the fixture for the frontend's port ----------
def _price_cases() -> list[dict]:
    out = []
    for f, ks in ((25000.0, (24000, 24800, 25000, 25150, 26500)), (55000.0, (52000, 55000, 57000)), (88.25, (87.5, 88.25, 90.0))):
        for k in ks:
            for t in (0.25 / 365, 3 / 365, 30 / 365, 0.5, 0.0):
                for s in (0.04, 0.13, 0.6):
                    for r in (0.0, G.RATE):
                        for kind in ("CE", "PE"):
                            out.append({"f": f, "k": float(k), "t": t, "sigma": s, "kind": kind, "r": r, **G.greeks(f, k, t, s, kind, r)})
    return out


def _positions() -> list[dict]:
    condor = [{"side": side, "opt": opt, "strike": k, "qty": 130, "fill": fill, "iv": iv, "t": 6 / 365, "basis": 1.0011}
              for side, opt, k, fill, iv in (("sell", "CE", 25400.0, 62.0, 0.105), ("buy", "CE", 25800.0, 14.5, 0.118),
                                             ("sell", "PE", 24600.0, 70.0, 0.14), ("buy", "PE", 24200.0, 22.0, 0.165))]
    calendar = [{"side": "sell", "opt": "CE", "strike": 55000.0, "qty": 35, "fill": 410.0, "iv": 0.14, "t": 2 / 365, "basis": 1.0003},
                {"side": "buy", "opt": "CE", "strike": 55000.0, "qty": 35, "fill": 980.0, "iv": 0.15, "t": 30 / 365, "basis": 1.0049}]
    crude = [{"side": "buy", "opt": "CE", "strike": 5700.0, "qty": 100, "fill": 88.0, "iv": 0.42, "t": 12 / 365, "basis": 1.0}]
    return [{"name": "straddle", "legs": STRADDLE, "spot": 25000.0}, {"name": "iron condor", "legs": condor, "spot": 25010.0},
            {"name": "calendar", "legs": calendar, "spot": 54900.0}, {"name": "bought call", "legs": crude, "spot": 5620.0}]


def build_fixture() -> dict:
    out = {"rate": G.RATE, "min_vol": G.MIN_VOL, "prices": _price_cases(), "positions": []}
    for p in _positions():
        spot, legs = p["spot"], p["legs"]
        cases = []
        for pct in (-8, -2.5, 0, 1, 6):
            for days in (0, 0.5, 1, 3, 40):
                for shift in (-30, -3, 0, 4.5):
                    s = G.scenario(legs, spot * (1 + pct / 100), days, shift, G.RATE)
                    cases.append({"spot_pct": pct, "days": days, "iv_shift": shift, **s})
        xs = [spot * (0.9 + 0.2 * i / 40) for i in range(41)]
        out["positions"].append({"name": p["name"], "spot": spot, "legs": legs, "cases": cases,
                                 "curve": {"xs": xs, "days": 1, "iv_shift": 2, "ys": G.curve(legs, xs, 1, 2, G.RATE)}})
    return out


def test_frontend_greeks_fixture_matches_this_module():
    """The frontend's what-if pricing is a port of this module, tested against this fixture (unit/greeks.test.mjs). If
    the maths changes, regenerate it: python -m tests.test_greeks (then the frontend's unit tests show what to port)."""
    assert FIXTURE.exists(), "run python -m tests.test_greeks to write the fixture"
    saved, fresh = json.loads(FIXTURE.read_text()), build_fixture()
    assert saved["rate"] == fresh["rate"] and saved["min_vol"] == fresh["min_vol"]
    assert len(saved["prices"]) == len(fresh["prices"]) and len(saved["positions"]) == len(fresh["positions"])
    for a, b in zip(saved["prices"], fresh["prices"]):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-12)
    for a, b in zip(saved["positions"], fresh["positions"]):
        assert a["legs"] == b["legs"]
        for x, y in zip(a["cases"], b["cases"]):
            assert x == pytest.approx(y, rel=1e-9, abs=1e-9)
        assert a["curve"]["ys"] == pytest.approx(b["curve"]["ys"], rel=1e-9, abs=1e-9)


# ---------- the API ----------
def test_chain_preview_and_position_greeks_on_every_plan(monkeypatch):
    setup(monkeypatch)
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "free", "plan": "free"}
    try:
        c = TestClient(app)
        ch = c.get("/options/chain", params={"exchange": "NFO", "underlying": "NIFTY", "expiry": "next"}).json()
        m = ch["model"]
        assert m["forward_from"] == "parity" and m["rate"] == G.RATE and m["days"] > 0 and 0 < m["atm_iv"] < 1
        for r in ch["rows"]:
            for side, sign in (("ce_g", 1), ("pe_g", -1)):
                g = r[side]
                assert g["iv"] and 0 <= sign * g["delta"] <= 1 and g["gamma"] > 0 and g["theta"] < 0 and g["vega"] > 0
        atm = next(r for r in ch["rows"] if r["strike"] == ch["atm"])
        assert atm["ce_g"]["delta"] - atm["pe_g"]["delta"] == pytest.approx(math.exp(-G.RATE * m["t"]), abs=1e-6)
        assert "ce_g" not in (atm["ce"] or {})            # the cached quotes themselves are left alone

        strat = {"name": "x", "structure": "short_straddle", "exchange": "NFO", "underlying": "NIFTY", "expiry": "next",
                 "legs": [{"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0}]}
        pv = c.post("/options/preview", json={"strategy": strat}).json()
        assert pv["model"]["expiry"] == pv["expiry"] and len(pv["expiries"]) >= 2 and pv["greeks"]["complete"]
        assert [l["side"] for l in pv["greeks"]["model_legs"]] == ["sell", "sell"]
        assert pv["greeks"]["model_legs"][0]["qty"] == pv["lot"] and pv["greeks"]["model_legs"][0]["fill"] == pv["legs"][0]["fill"]
        net = pv["greeks"]["net"]
        assert net["theta"] > 0 and net["vega"] < 0 and net["gamma"] < 0
        assert net["pnl"] < 0          # sold at the bid, valued at the middle: the half-spread

        body = {"exchange": "NFO", "underlying": "NIFTY", "expiry": pv["expiry"],
                "legs": [{"side": "buy", "opt": "CE", "strike": 25000, "qty": 75, "fill": 150}]}
        g = c.post("/options/greeks", json=body).json()
        assert g["complete"] and g["net"]["delta"] == pytest.approx(75 * g["legs"][0]["delta"], rel=1e-6)
        assert g["close_charges"]["orders"] == 1 and g["close_charges"]["total"] > 0
        assert c.post("/options/greeks", json={**body, "expiry": "2020-01-01"}).status_code == 404
        assert c.post("/options/greeks", json={**body, "legs": []}).status_code == 422
    finally:
        app.dependency_overrides.clear()


ROLL = {"exchange": "NFO", "underlying": "NIFTY",
        "legs": [{"side": "sell", "opt": "CE", "strike": 25000, "qty": 75, "fill": 150}, {"side": "sell", "opt": "PE", "strike": 25000, "qty": 75, "fill": 148}]}


def test_roll_preview_prices_both_orders_and_the_greeks_before_and_after(monkeypatch):
    data, _ = setup(monkeypatch)
    try:
        c = TestClient(app)
        ex = [e.isoformat() for e in _expiries()]
        r = c.post("/options/roll", json={**ROLL, "expiry": ex[1], "leg": 0, "strike": 25200}).json()
        q = data.quotes([f"NFO:NIFTY{_expiries()[1]:%y%m%d}25000CE", f"NFO:NIFTY{_expiries()[1]:%y%m%d}25200CE"])
        old, new = q.values()
        assert r["close"]["px"] == old["ask"] and r["close"]["side"] == "buy"      # a sold leg is bought back at the ask
        assert r["open"]["px"] == new["bid"] and r["open"]["side"] == "sell" and r["open"]["strike"] == 25200
        assert r["premium"] == pytest.approx((new["bid"] - old["ask"]) * 75, abs=0.01) and r["premium"] < 0
        assert r["charges"]["orders"] == 2 and r["net"] == pytest.approx(r["premium"] - r["charges"]["total"], abs=0.01)
        assert {i["key"] for i in r["charges"]["items"]} >= {"brokerage", "stt", "gst"}
        # moving the sold call up: the position's delta rises (less short), as the model says it should
        assert r["after"]["delta"] > r["before"]["delta"] and r["complete"]
        assert r["after"]["delta"] == pytest.approx(r["before"]["delta"] + 75 * pv_delta(c, ex[1], 25000) - 75 * r["open"]["delta"], rel=1e-4)
        # another expiry: its own model, its own forward and time
        r2 = c.post("/options/roll", json={**ROLL, "expiry": ex[1], "leg": 1, "strike": 25000, "to_expiry": ex[2]}).json()
        assert r2["model_to"]["expiry"] == ex[2] and r2["model_to"]["t"] > r2["model"]["t"] and r2["open"]["expiry"] == ex[2]
        assert r2["after"]["vega"] < r2["before"]["vega"]                         # a longer-dated sold put: more vega sold
        assert c.post("/options/roll", json={**ROLL, "expiry": ex[1], "leg": 5, "strike": 25200}).status_code == 400
        bad = c.post("/options/roll", json={**ROLL, "expiry": ex[1], "leg": 0, "strike": 25013})
        assert bad.status_code == 400 and "isn't listed" in bad.json()["detail"]["message"]
    finally:
        app.dependency_overrides.clear()


def pv_delta(c, expiry: str, strike: float) -> float:
    """A call's model delta from the chain."""
    ch = c.get("/options/chain", params={"exchange": "NFO", "underlying": "NIFTY", "expiry": expiry}).json()
    return next(r for r in ch["rows"] if r["strike"] == strike)["ce_g"]["delta"]


def test_roll_preview_is_pro_once_payments_are_live(monkeypatch):
    setup(monkeypatch)
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "secret"), ("RAZORPAY_PLAN_BASIC", "plan_b"),
                 ("RAZORPAY_PLAN_PRO", "plan_p")):
        monkeypatch.setattr(main.settings, k, v)          # payments live, so plans gate
    assert FEATURE_PLAN["options_whatif"] == "pro"
    ex = _expiries()[1].isoformat()
    try:
        for plan, code in (("free", 402), ("basic", 402), ("pro", 200)):
            app.dependency_overrides[main.current_profile] = lambda plan=plan: {"id": "u", "_plan": plan, "plan": plan}
            r = TestClient(app).post("/options/roll", json={**ROLL, "expiry": ex, "leg": 0, "strike": 25100})
            assert r.status_code == code, plan
            if code == 402:
                assert "Pro plan" in r.json()["detail"]["message"]
            # the Greeks themselves stay on every plan
            assert TestClient(app).post("/options/greeks", json={**ROLL, "expiry": ex}).status_code == 200
    finally:
        app.dependency_overrides.clear()


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(build_fixture(), separators=(",", ":")) + "\n")
    print("wrote", FIXTURE, f"{FIXTURE.stat().st_size // 1024} KB")
