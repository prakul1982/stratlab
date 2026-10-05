"""Security checks on the last release: the price chart API, the options Greeks and roll routes, the admin routes the
release added (AI, F&O changes, TER, storage), and the AI layer's error text."""
import json
import math

import httpx
import pytest
from fastapi.testclient import TestClient

from app import admin, chart_data as CD, db, main
from app import ai_clients as C
from app.config import settings
from app.main import app
from tests import world
from tests.fake_options_kite import _expiries
from tests.test_options_api import setup as options_setup

PRO = world.headers("pro-token")
FREE = world.headers("free-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


# ---------- every admin route needs the admin check ----------
def _deps(dep) -> list:
    out = [dep.call]
    for d in dep.dependencies:
        out += _deps(d)
    return out


# the broker's login redirect lands here without a session; the signed `state` it carries is checked instead
CALLBACKS = {"/admin/kite/callback"}


def _routes(routes) -> list:
    """Every route, including those of included routers (kept unflattened by newer FastAPI)."""
    out = []
    for r in routes:
        inner = getattr(r, "original_router", None)
        out += _routes(inner.routes) if inner is not None else [r]
    return out


def test_every_admin_route_requires_the_admin_profile():
    missing = []
    every = _routes(app.router.routes)
    for r in every:
        path = getattr(r, "path", "")
        if path.startswith("/admin") and path not in CALLBACKS and hasattr(r, "dependant"):
            if admin.admin_profile not in _deps(r.dependant):
                missing.append(path)
    assert not missing, missing
    paths = {getattr(r, "path", "") for r in every}
    assert {"/admin/ai", "/admin/ai/pin", "/admin/fo-changes/refresh", "/admin/ter", "/admin/ter/read",
            "/admin/storage/move"} <= paths


def test_release_admin_routes_refuse_a_paying_non_admin(w):
    c = w["client"]
    for method, path in (("get", "/admin/ai"), ("post", "/admin/ai/rerank"), ("post", "/admin/ai/pin"), ("post", "/admin/ai/block"),
                         ("post", "/admin/fo-changes/refresh"), ("get", "/admin/ter"), ("post", "/admin/ter/read"),
                         ("get", "/admin/storage"), ("post", "/admin/storage/move")):
        body = {"provider": "groq", "model": "x"}
        r = c.post(path, json=body, headers=PRO) if method == "post" else c.get(path, headers=PRO)
        assert r.status_code == 403, path


# ---------- the price chart ----------
def test_chart_candles_of_futures_and_options_are_pro(w, monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "secret"), ("RAZORPAY_PLAN_BASIC", "plan_b"),
                 ("RAZORPAY_PLAN_PRO", "plan_p")):
        monkeypatch.setattr(main.settings, k, v)          # payments live, so plans gate
    c = w["client"]
    fut = c.get("/instruments/search?q=INFY&market=IN", headers=PRO).json()[0]
    real = main.markets.resolve

    def resolve(inst_id):                                  # the same candles, marked as an NFO contract
        prov, inst = real(inst_id)
        return prov, ({**inst, "fno": True} if inst and inst_id == fut["id"] else inst)
    monkeypatch.setattr(main.markets, "resolve", resolve)
    assert c.get(f"/chart/candles/{fut['id']}?tf=1d", headers=PRO).status_code == 200
    r = c.get(f"/chart/candles/{fut['id']}?tf=1d", headers=FREE)
    assert r.status_code == 402 and "Pro" in r.json()["detail"]["message"]


def test_chart_drawings_stored_per_user_stay_small(w):
    """Every symbol full of the longest drawings must not grow one user's stored row without bound."""
    note = {"kind": "text", "text": "x" * 500, "id": "i" * 80,
            "points": [{"t": 1.7e12 + i, "p": 100.0 + i} for i in range(2)]}
    for s in range(CD.MAX_SYMBOLS + 20):
        CD.save("u-big", f"SYM{s}", [dict(note, id=f"{s}-{i}") for i in range(CD.MAX_DRAWINGS)])
    raw = db.get_setting(CD.KEY + "u-big") or ""
    assert len(raw) <= CD.MAX_BYTES
    assert CD.drawings("u-big", f"SYM{CD.MAX_SYMBOLS + 19}")             # the newest symbol is kept


def test_chart_drawings_reject_odd_input(w):
    c = w["client"]
    for sym in ("../x", "a b", "x" * 41, "<script>", ""):
        assert c.get("/chart/drawings", params={"symbol": sym}, headers=PRO).status_code in (400, 422), sym
    bad = [{"kind": "trend", "points": [{"t": float("nan"), "p": 1}, {"t": 1, "p": float("inf")}]},
           {"kind": "<img>", "points": [{"t": 1, "p": 1}]}, {"kind": "text", "points": [{"t": True, "p": 1}]}]
    r = c.put("/chart/drawings", headers=PRO, content=json.dumps({"symbol": "INFY", "items": bad}),
              params=None, )
    assert r.status_code in (200, 422) and (r.status_code == 422 or r.json()["items"] == [])
    assert c.put("/chart/drawings", headers=PRO, json={"symbol": "INFY", "items": [{}] * (CD.MAX_DRAWINGS + 1)}).status_code == 422


# ---------- options: numbers that aren't numbers ----------
def test_options_greeks_and_roll_refuse_nan_inf_and_huge_values(monkeypatch):
    options_setup(monkeypatch)
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "pro", "plan": "pro"}
    try:
        c = TestClient(app)
        ex = _expiries()[1].isoformat()
        leg = {"side": "sell", "opt": "CE", "strike": 25000, "qty": 75, "fill": 150}
        for bad in ({"strike": "NaN"}, {"strike": "Infinity"}, {"fill": "NaN"}, {"fill": "-Infinity"}, {"strike": 1e300},
                    {"qty": 10 ** 20}, {"strike": 0}, {"fill": -1}):
            raw = json.dumps({"exchange": "NFO", "underlying": "NIFTY", "expiry": ex, "legs": [{**leg, **bad}]})
            raw = raw.replace('"NaN"', "NaN").replace('"Infinity"', "Infinity").replace('"-Infinity"', "-Infinity")
            r = c.post("/options/greeks", content=raw, headers={"content-type": "application/json"})
            assert r.status_code == 422, bad
            raw2 = raw[:-1] + ', "leg": 0, "strike": 25100}'
            assert c.post("/options/roll", content=raw2, headers={"content-type": "application/json"}).status_code == 422, bad
        for bad in ("NaN", "Infinity", "1e400"):
            raw = json.dumps({"exchange": "NFO", "underlying": "NIFTY", "expiry": ex, "legs": [leg], "brokerage": 0}).replace(
                '"brokerage": 0', f'"brokerage": {bad}')
            assert c.post("/options/greeks", content=raw, headers={"content-type": "application/json"}).status_code == 422, bad
        ok = c.post("/options/greeks", json={"exchange": "NFO", "underlying": "NIFTY", "expiry": ex, "legs": [leg]})
        assert ok.status_code == 200
        assert "NaN" not in ok.text and "Infinity" not in ok.text
    finally:
        app.dependency_overrides.clear()


def test_greeks_survive_zero_volatility_and_extreme_inputs():
    from app.options import greeks as G
    for sigma in (0.0, 1e-12, 50.0):
        for f, k in ((25000, 25000), (25000, 1), (1, 1e7)):
            g = G.greeks(f, k, 0.01, sigma, "CE")
            assert all(isinstance(v, (int, float)) and math.isfinite(v) for v in g.values()), (sigma, f, k)
    assert G.implied_vol(float("nan"), 100, 100, 0.1, "CE") is None
    assert G.implied_vol(1.0, float("inf"), 100, 0.1, "CE") is None
    assert G.implied_vol(1.0, 100, 100, 0.0, "CE") is None


# ---------- the AI layer never shows a key ----------
def test_provider_error_text_never_carries_the_key(monkeypatch):
    secret = "gsk_live_9f8e7d6c5b4a3210SECRET"
    monkeypatch.setattr(settings, "GROQ_API_KEY", secret)
    for code in (401, 403, 400, 500, 418):
        r = httpx.Response(code, json={"error": {"message": f"Invalid API Key: {secret} (Bearer {secret})"}})
        e = C.classify("groq", r, "m")
        assert secret not in e.detail and "SECRET" not in e.detail, code
    r = httpx.Response(500, text=f"upstream said key={secret}")
    assert secret not in C.classify("groq", r, "m").detail
