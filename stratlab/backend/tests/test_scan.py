"""Stage 2 + Supertrend scans: the analysis, ranking, the ST S2 strategy, the endpoints and the daily alert."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import db, main, scan
from app.config import settings
from app.models import Strategy
from tests.test_notebooks import api  # noqa: F401  (fixture)


def bars_from(closes):
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [{"t": (t0 + timedelta(days=i)).isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000}
            for i, c in enumerate(closes)]


def test_analyse_finds_stage_2_and_a_fresh_supertrend_flip():
    up = list(np.linspace(100, 200, 300))
    dip = list(np.linspace(200, 185, 12)) + list(np.linspace(185, 198, 4))      # a pullback, then turning back up
    r = scan.analyse(bars_from(up + dip))
    assert r["stage"] == 2 and r["st_up"] and r["st_days"] <= scan.FRESH and r["signal"] == "fresh"
    down = scan.analyse(bars_from(list(np.linspace(200, 90, 320))))
    assert down["stage"] == 4 and not down["st_up"] and down["signal"] is None
    assert scan.analyse(bars_from([100] * 10)) is None                           # too short


def test_st_s2_template_is_a_valid_strategy():
    s = Strategy(**scan.ST_S2)
    assert s.entry[0].l.t == "stage" and s.entry[0].op == "eq" and s.exit[0].r.t == "supertrend"


class FakeProv:
    def ready(self): return True
    def instrument(self, key): return {"symbol": key, "name": key.title(), "currency": "USD"}


class FakeRegistry:
    def __init__(self, series): self.series, self.prov = series, FakeProv()
    def provider(self, m): return self.prov
    def resolve(self, iid):
        return (self.prov, {"symbol": iid.split(":")[1]}) if iid.split(":")[1] in self.series else (self.prov, None)


def fake_setup(monkeypatch):
    up = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 185, 12)) + list(np.linspace(185, 198, 4))
    series = {"AAA": bars_from(up), "BBB": bars_from(list(np.linspace(200, 90, 320)))}
    reg = FakeRegistry(series)
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series[iid.split(":")[1]])
    scan._cache.clear()
    return reg


def test_run_ranks_signals_and_reports_missing(monkeypatch):
    reg = fake_setup(monkeypatch)
    out = scan.run(reg, "US", [{"symbol": "BBB"}, {"symbol": "AAA"}, {"symbol": "ZZZ"}])
    assert [r["symbol"] for r in out["rows"]] == ["AAA", "BBB"] and out["missing"] == ["ZZZ"]
    assert out["counts"]["fresh"] == 1


@pytest.fixture
def store(monkeypatch):
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "settings_with_prefix", lambda p, limit=1000: [v for k, v in kv.items() if k.startswith(p)])
    return kv


def test_endpoints_are_pro_and_use_the_watchlist(monkeypatch, store):
    import json
    reg = fake_setup(monkeypatch)
    monkeypatch.setattr(main, "markets", reg)
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "s")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")
    store["watchlist:u1"] = json.dumps({"items": [{"region": "US", "symbol": "AAA"}, {"region": "IN", "symbol": "TCS"}]})
    who = {"p": {"id": "u1", "plan": "free", "_plan": "free"}}
    main.app.dependency_overrides[main.current_profile] = lambda: who["p"]
    c = TestClient(main.app)
    try:
        sets = c.get("/research/scan/sets?region=US").json()
        assert sets["sets"][0] == {"id": "watchlist", "name": "Your watchlist", "count": 1} and sets["template"]["entry"]
        assert c.post("/research/scan", json={"region": "US", "set": "watchlist"}).status_code == 402      # Pro only
        who["p"] = {"id": "u1", "plan": "pro", "_plan": "pro"}
        r = c.post("/research/scan", json={"region": "US", "set": "watchlist"}).json()
        assert r["name"] == "Your watchlist" and r["rows"][0]["symbol"] == "AAA" and r["rows"][0]["signal"] == "fresh"
        assert c.put("/research/scan/alerts", json={"on": True}).json() == {"alerts": True} and scan.alert_on("u1")
    finally:
        main.app.dependency_overrides.clear()


def test_daily_alert_sends_once_per_day_to_subscribers(monkeypatch, store):
    import json
    reg = fake_setup(monkeypatch)
    # make AAA's flip happen on the very last candle
    up = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 180, 15)) + [199.0]
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: bars_from(up))
    store["watchlist:u1"] = json.dumps({"items": [{"region": "US", "symbol": "AAA"}]})
    scan.set_alert("u1", True)
    monkeypatch.setattr(db, "get_profile", lambda uid: {"id": uid})
    sent = []
    job = scan.Alerts(reg, notify=lambda p, s, t, url: sent.append(t), can_alert=lambda p: True)
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda m, d: True)
    after_close = datetime(2026, 10, 1, 20, 30, tzinfo=timezone.utc)          # 16:30 in New York
    job.tick(after_close)
    job.tick(after_close + timedelta(minutes=10))
    assert len(sent) == 1 and "AAA" in sent[0] and "not advice" in sent[0]
    job2 = scan.Alerts(reg, notify=lambda p, s, t, url: sent.append(t), can_alert=lambda p: True)
    job2.tick(after_close + timedelta(minutes=20))                                   # a restart doesn't resend
    assert len(sent) == 1


def test_a_new_notebook_keeps_its_group(api):
    body = {"name": "ST S2 on a group", "strategy": scan.ST_S2,
            "group": {"id": "us_mega", "name": "20 US large caps", "market": "us", "maxOpen": 5,
                      "members": [{"symbol": "AAPL"}, {"symbol": "MSFT", "id": "US:MSFT"}]}}
    nb = api.post("/notebooks", json=body).json()
    assert nb["group"]["market"] == "US" and [m["symbol"] for m in nb["group"]["members"]] == ["AAPL", "MSFT"]
    assert nb["strategy"]["entry"][0]["op"] == "eq"


def test_st_s2_strategy_actually_trades_a_trending_stock():
    """Regression: "crosses above" never lined up with Stage 2 on the same day, so the template never traded."""
    from app.engine.core import backtest
    rng = np.random.default_rng(1)
    path = np.r_[np.linspace(100, 200, 400), np.linspace(200, 150, 200), np.linspace(150, 260, 400)] * (1 + rng.normal(0, 0.012, 1000))
    out = backtest(bars_from(list(path)), Strategy(**scan.ST_S2), 200, 1, "flat")
    assert out["stats"]["n"] >= 1 or out["open_trade"]
    assert out["diagnostics"]["all_true_on"] > 100
