"""Picking option strikes by rule (model delta, a delta range, premium, a share of the ATM straddle) and the India VIX
entry filter, in the engine, a live session and the API."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import main
from app.main import app
from app.models import OptionStrategy, OptLeg, OptVix
from app.options import greeks as G
from app.options import importer as oi
from app.options import strikes as SR
from app.options.engine import VIX_KEY, OptionsEngine

from .test_options import at, contracts, premium, quotes, straddle
from .test_options_api import STRAT, midday, setup
from .test_plan_gates import as_plan, paid  # noqa: F401  (a fixture)

SPOT = 25000


def model(q, now=None):
    c = contracts()
    return SR.model_for(c, c.atm(SPOT), SPOT, q, now or at("10:00"))


def leg(**kw):
    return OptLeg(**{"side": "sell", "opt": "PE", **kw})


def test_delta_rule_picks_the_strike_nearest_the_delta():
    c, q = contracts(), quotes(SPOT)
    m = model(q)
    k, why = SR.pick(c, 25000, leg(pick="delta", delta=0.2), q, m)
    # every quoted put's model delta, worked out the same way: the pick is the nearest to -0.20
    ds = {s: G.option(q[f"NFO:NIFTY{int(s)}PE"], s, "PE", m)["delta"] for s in c.strikes}
    best = min(ds, key=lambda s: abs(ds[s] + 0.2))
    assert k == best and k < 25000 and why.startswith(f"PE {best:,.0f} picked: model delta −") and "nearest to −0.20" in why
    kc, why_c = SR.pick(c, 25000, leg(opt="CE", pick="delta", delta=0.2), q, m)
    assert kc > 25000 and "nearest to 0.20" in why_c


def test_delta_range_and_nothing_inside_it():
    c, q = contracts(), quotes(SPOT)
    m = model(q)
    k, why = SR.pick(c, 25000, leg(opt="CE", pick="delta_range", delta=0.3, deltaTo=0.45), q, m)
    d = G.option(q[f"NFO:NIFTY{int(k)}CE"], k, "CE", m)["delta"]
    assert 0.3 <= d <= 0.45 and "inside 0.30 to 0.45" in why
    k, why = SR.pick(c, 25000, leg(opt="CE", pick="delta_range", delta=0.01, deltaTo=0.02), q, m)
    assert k is None and "between 0.01 and 0.02" in why
    assert SR.pick(c, 25000, leg(pick="delta"), q, None)[0] is None          # no model, no delta pick
    with pytest.raises(ValidationError):
        OptLeg(side="sell", opt="CE", pick="delta_range", delta=0.4, deltaTo=0.3)


def test_premium_rules():
    c, q = contracts(), quotes(SPOT)
    mid = lambda s, o="PE": premium(o, s, SPOT)                               # noqa: E731  (bid-ask middle)
    k, why = SR.pick(c, 25000, leg(pick="premium", premium=50), q, None)
    assert abs(mid(k) - 50) == min(abs(mid(s) - 50) for s in c.strikes) and "nearest to ₹50.00" in why
    k, why = SR.pick(c, 25000, leg(pick="premium", premium=50, premiumOp="gte"), q, None)
    assert mid(k) >= 50 and all(mid(s) < 50 or mid(s) >= mid(k) for s in c.strikes) and "lowest at or above" in why
    k, why = SR.pick(c, 25000, leg(pick="premium", premium=50, premiumOp="lte"), q, None)
    assert mid(k) <= 50 and all(mid(s) > 50 or mid(s) <= mid(k) for s in c.strikes)
    assert SR.pick(c, 25000, leg(pick="premium", premium=1, premiumOp="lte"), q, None)[0] is None
    k, why = SR.pick(c, 25000, leg(opt="CE", pick="straddle_pct", pct=25), q, None)
    target = 0.25 * (mid(25000, "CE") + mid(25000, "PE"))
    assert abs(mid(k, "CE") - target) == min(abs(mid(s, "CE") - target) for s in c.strikes) and "25% of the at-the-money straddle" in why


def test_rule_words_and_keys():
    assert SR.describe(leg(pick="delta", delta=0.2)) == "model delta nearest 0.20"
    assert SR.describe(leg(pick="premium", premium=40, premiumOp="gte")) == "premium at or above ₹40.00"
    assert SR.describe(leg(offset=2)) == "2 strikes out of the money"
    c = contracts()
    assert SR.keys_for(c, 25000, [leg()]) == []                              # offsets need nothing extra
    keys = SR.keys_for(c, 25000, [leg(pick="delta")])
    assert "NFO:NIFTY25000CE" in keys and "NFO:NIFTY24500PE" in keys and "NFO:NIFTY25100CE" not in keys


def test_engine_enters_on_the_rule_and_logs_why():
    s = straddle(legs=[{"side": "sell", "opt": "CE", "pick": "delta", "delta": 0.25},
                       {"side": "sell", "opt": "PE", "pick": "premium", "premium": 60}])
    e, c = OptionsEngine(s), contracts()
    out = e.step(at("09:31"), SPOT, c, quotes(SPOT), True)
    assert len(out) == 2 and all(x["pick"] and " picked: " in x["pick"] for x in out)
    pe = next(x for x in out if x["opt"] == "PE")
    assert pe["pick"].startswith(f"PE {pe['strike']:,.0f} picked: premium")
    # the session state keeps the log line through a restart
    e2 = OptionsEngine(s, state=e.dump())
    assert e2.events[-1]["pick"] == out[-1]["pick"]


def test_engine_waits_when_no_strike_fits():
    s = straddle(legs=[{"side": "sell", "opt": "CE", "pick": "premium", "premium": 1, "premiumOp": "lte"}])
    e = OptionsEngine(s)
    assert e.step(at("09:31"), SPOT, contracts(), quotes(SPOT), True) == []
    assert "at or below ₹1.00" in e.note and "No entry until a strike fits" in e.note


def test_recentre_repicks_by_the_rule():
    s = straddle(legs=[{"side": "sell", "opt": "CE", "pick": "delta", "delta": 0.3}],
                 recenter={"enabled": True, "every": 5, "threshold": 2, "roll": "shorts"}, risk={"stopType": "none"})
    e, c = OptionsEngine(s), contracts()
    first = e.step(at("09:31"), SPOT, c, quotes(SPOT), True)[0]["strike"]
    out = e.step(at("09:40"), 25200, c, quotes(25200), True)
    assert [x["why"] for x in out] == ["Re-centre", "Re-centre"] and out[1]["strike"] > first and out[1]["pick"]


def vix_quotes(v):
    return {**quotes(SPOT), VIX_KEY: {"ltp": v, "bid": None, "ask": None}}


def test_vix_filter_skips_outside_the_band_once_a_day():
    e, c = OptionsEngine(straddle(vix={"min": 11, "max": 18})), contracts()
    assert e.step(at("09:31"), SPOT, c, vix_quotes(21.4), True) == []
    assert e.note.startswith("India VIX is 21.40, above 18; entries wait until it is between 11 and 18")
    e.step(at("09:36"), SPOT, c, vix_quotes(21.9), True)
    skips = [x for x in e.events if x.get("kind") == "skip"]
    assert len(skips) == 1 and skips[0]["why"] == "Skipped: India VIX 21.40, above 18"
    assert e.step(at("09:41"), SPOT, c, quotes(SPOT), True) == [] and "Waiting for India VIX" in e.note
    out = e.step(at("09:46"), SPOT, c, vix_quotes(15.2), True)
    assert len(out) == 2 and not e.note
    e2 = OptionsEngine(straddle(vix={"min": 12}))
    e2.step(at("09:31"), SPOT, c, vix_quotes(10.5), True)
    assert "below 12" in e2.note and "at or above 12" in e2.note
    with pytest.raises(ValidationError):
        OptVix(min=0, max=0)
    with pytest.raises(ValidationError):
        OptVix(min=20, max=15)
    with pytest.raises(ValidationError):
        OptionStrategy(**{**STRAT, "vix": {"min": 150}})


def test_session_quotes_the_window_and_vix(monkeypatch):
    data, rows = setup(monkeypatch)
    try:
        c = TestClient(app)
        strat = {**STRAT, "legs": [{"side": "sell", "opt": "CE", "pick": "delta", "delta": 0.2},
                                   {"side": "sell", "opt": "PE", "pick": "delta", "delta": 0.2}], "vix": {"max": 30}}
        snap = c.post("/options/sessions", json={"strategy": strat}).json()
        s = main.manager.sessions[snap["id"]]
        s.on_timer(midday())
        s.next_poll = 0
        s.on_timer(midday())
        snap = s.snapshot()
        assert len(snap["legs"]) == 2 and all(ev.get("pick") for ev in snap["events"])
        ce = next(l for l in snap["legs"] if l["opt"] == "CE")
        assert ce["strike"] > 25000
        # with the VIX above the band, a fresh session waits and logs one skip line (not an order)
        data.kite.vix = 33.5
        data._qcache.clear()
        snap = c.post("/options/sessions", json={"strategy": strat}).json()
        s = main.manager.sessions[snap["id"]]
        s.on_timer(midday())
        s.next_poll = 0
        s.on_timer(midday())
        snap = s.snapshot()
        assert snap["legs"] == [] and "India VIX is 33.50, above 30" in snap["note"]
        assert [e["why"] for e in snap["events"]] == ["Skipped: India VIX 33.50, above 30"]
        assert main.orders_from(snap["events"]) == []
    finally:
        app.dependency_overrides.clear()
        for sid in list(main.manager.sessions):
            main.manager.sessions.pop(sid, None)


def test_preview_shows_what_each_rule_picks(monkeypatch):
    setup(monkeypatch)
    try:
        c = TestClient(app)
        strat = {**STRAT, "legs": [{"side": "sell", "opt": "CE", "pick": "premium", "premium": 30},
                                   {"side": "sell", "opt": "PE", "offset": 2}]}
        pv = c.post("/options/preview", json={"strategy": strat}).json()
        ce, pe = pv["legs"]
        assert ce["strike"] > 25000 and ce["pick"].startswith(f"CE {ce['strike']:,.0f} picked: premium ₹") and ce["rule"] == "premium nearest ₹30.00"
        assert pe["strike"] == 24900 and pe["pick"] is None and pe["rule"] == "2 strikes out of the money"
        bad = c.post("/options/preview", json={"strategy": {**strat, "legs": [{"side": "sell", "opt": "CE", "pick": "magic"}]}})
        assert bad.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_strike_rules_are_pro_and_the_vix_filter_basic(paid, monkeypatch):  # noqa: F811
    setup(monkeypatch)
    rules = {**STRAT, "legs": [{"side": "sell", "opt": "CE", "pick": "delta", "delta": 0.2}]}
    vix = {**STRAT, "vix": {"min": 11, "max": 18}}
    try:
        r = as_plan("basic").post("/options/sessions", json={"strategy": rules})
        assert r.status_code == 402 and "Picking strikes by delta or premium is on the Pro plan" in r.json()["detail"]["message"]
        r = as_plan("free").post("/options/sessions", json={"strategy": vix})
        assert r.status_code == 402
        assert as_plan("basic").post("/options/sessions", json={"strategy": vix}).status_code == 200
        assert as_plan("pro").post("/options/sessions", json={"strategy": rules}).status_code == 200
        # the preview of what a rule picks is for everyone
        assert as_plan("free").post("/options/preview", json={"strategy": rules}).status_code == 200
    finally:
        app.dependency_overrides.clear()
        for sid in list(main.manager.sessions):
            main.manager.sessions.pop(sid, None)


def test_import_maps_delta_and_vix_wording():
    s, notes = oi.parse_ai({"name": "0.2 delta strangle", "underlying": "NIFTY", "legs": [
        {"side": "sell", "opt": "CE", "pick": "delta", "delta": 0.2}, {"side": "sell", "opt": "PE", "pick": "delta", "delta": 0.2}],
        "vix": {"min": 11, "max": 18}})
    assert [l.pick for l in s.legs] == ["delta", "delta"] and s.vix.max == 18 and notes == []
    s, notes = oi.parse_ai({"underlying": "NIFTY", "legs": [{"side": "sell", "opt": "CE"}], "vix": {"min": 30, "max": 10}})
    assert s.vix is None and any("vix" in n for n in notes)
    assert oi.is_options("Sell the 0.2 delta strangle on NIFTY at 9:20", "words")
    exact = OptionStrategy(**{**STRAT, "legs": [{"side": "sell", "opt": "CE", "pick": "straddle_pct", "pct": 30}]})
    import json
    back = oi.from_json(json.dumps({"stratlab": "options", "strategy": exact.model_dump()}))
    assert back.legs[0].pick == "straddle_pct" and back.legs[0].pct == 30


def test_old_strategies_still_load():
    s = OptionStrategy(**STRAT)
    assert s.vix is None and all(l.pick == "offset" for l in s.legs) and not SR.uses_rules(s.legs)
    assert datetime  # imported for the helpers' clock
