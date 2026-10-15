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
    monkeypatch.setattr(scan, "session_day", lambda market, now=None: None)         # the candles are made up, dated before today
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
    after_close = datetime(2026, 10, 1, 20, 55, tzinfo=timezone.utc)          # 16:55 in New York (the alert waits for 16:50)
    job.tick(after_close)
    job.tick(after_close + timedelta(minutes=10))
    assert len(sent) == 1 and "AAA" in sent[0] and "not advice" in sent[0]
    job2 = scan.Alerts(reg, notify=lambda p, s, t, url: sent.append(t), can_alert=lambda p: True)
    job2.tick(after_close + timedelta(minutes=20))                                   # a restart doesn't resend
    assert len(sent) == 1


def test_a_new_notebook_keeps_its_group(api):
    body = {"name": "ST S2 on a group", "strategy": scan.ST_S2,
            "group": {"id": "us_mega", "name": "20 of the largest US companies", "market": "us", "maxOpen": 5,
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


def test_one_failing_user_does_not_stop_the_alert_for_the_rest(monkeypatch, store):
    import json
    reg = fake_setup(monkeypatch)
    up = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 180, 15)) + [199.0]
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: bars_from(up))
    for uid in ("a", "b"):
        store[f"watchlist:{uid}"] = json.dumps({"items": [{"region": "US", "symbol": "AAA"}]})
        scan.set_alert(uid, True)

    def profile(uid):
        if uid == "a":
            raise RuntimeError("db down")
        return {"id": uid}
    monkeypatch.setattr(db, "get_profile", profile)
    sent = []
    job = scan.Alerts(reg, notify=lambda p, s, t, url: sent.append(p["id"]), can_alert=lambda p: True)
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda m, d: True)
    job.tick(datetime(2026, 10, 1, 20, 55, tzinfo=timezone.utc))              # 16:55 in New York
    assert sent == ["b"]


def test_the_us_alert_waits_for_the_closing_prints_to_settle(monkeypatch, store):
    job = scan.Alerts(None, notify=lambda *a, **k: None, can_alert=lambda p: True)
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda m, d: True)
    assert job.due("US", datetime(2026, 10, 1, 20, 30, tzinfo=timezone.utc)) is None      # 16:30 New York
    assert job.due("US", datetime(2026, 10, 1, 20, 55, tzinfo=timezone.utc)) == "2026-10-01"


def test_a_daily_alert_run_killed_mid_way_resumes_with_the_subscribers_left(monkeypatch, store):
    import json
    from types import SimpleNamespace
    from app import run_marks
    reg = fake_setup(monkeypatch)
    up = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 180, 15)) + [199.0]
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: bars_from(up))
    for u in ("u1", "u2", "u3"):
        store[f"watchlist:{u}"] = json.dumps({"items": [{"region": "US", "symbol": "AAA"}]})
        scan.set_alert(u, True)
    clock = [1000.0]
    monkeypatch.setattr(run_marks, "time", SimpleNamespace(time=lambda: clock[0]))
    kill = [True]

    def profile(uid):
        if uid == "u2" and kill[0]:
            kill[0] = False
            raise KeyboardInterrupt                         # the deploy's SIGTERM
        return {"id": uid}
    monkeypatch.setattr(db, "get_profile", profile)
    monkeypatch.setattr("app.data.calendar.is_trading_day", lambda m, d: True)
    sent = []
    mk = lambda: scan.Alerts(reg, notify=lambda p, s, t, url: sent.append(p["id"]), can_alert=lambda p: True)  # noqa: E731
    at = datetime(2026, 10, 1, 20, 55, tzinfo=timezone.utc)
    with pytest.raises(KeyboardInterrupt):
        mk().tick(at)
    n = len(sent)
    mk().tick(at)
    assert len(sent) == n                                   # still beating: not resumed
    clock[0] += run_marks.STALE + 1
    mk().tick(at)
    assert sorted(sent) == ["u1", "u2", "u3"]               # each once; the ones before the kill weren't resent
    clock[0] += run_marks.STALE + 1
    mk().tick(at)
    assert len(sent) == 3                                   # done: skipped


def test_run_leaves_out_a_stock_whose_last_candle_is_weeks_old(monkeypatch):
    reg = fake_setup(monkeypatch)
    live = bars_from(list(np.linspace(100, 200, 300)) + list(np.linspace(200, 185, 12)) + list(np.linspace(185, 198, 4)))
    halted = live[:-40]                         # suspended: its last candle is 40 days before the others'
    series = {"AAA": live, "BBB": halted}
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series[iid.split(":")[1]])
    out = scan.run(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}])
    assert [r["symbol"] for r in out["rows"]] == ["AAA"]
    assert out["problems"] == ["BBB: no recent daily prices"]


def test_scan_fills_a_blank_name_from_the_stored_company_lists(monkeypatch):
    """R29D-001: the broker's list leaves some names blank (WIPRO, ITC); the stored company lists supply them."""
    from app import stock_pages
    reg = fake_setup(monkeypatch)
    reg.prov.instrument = lambda key: {"symbol": key, "name": "" if key == "AAA" else "Bee Ltd", "currency": "USD"}
    monkeypatch.setattr(stock_pages, "companies", lambda region: {"AAA": {"name": "Aaa Corp", "sym": "AAA", "bse": None}})
    monkeypatch.setattr(stock_pages, "_setting", lambda key: None)
    rows = {r["symbol"]: r for r in scan.run(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}])["rows"]}
    assert rows["AAA"]["name"] == "Aaa Corp" and rows["BBB"]["name"] == "Bee Ltd"
    monkeypatch.setattr(stock_pages, "companies", lambda region: {})
    monkeypatch.setattr(stock_pages, "_setting", lambda key: {"facts": {"name": "Aaa From Facts"}} if key.endswith(":AAA") else None)
    assert scan.company_name("US", {"symbol": "AAA", "name": None}, "US:AAA") == "Aaa From Facts"


def test_stage_days_flag_a_stage_that_began_before_the_look_back():
    """R29D-002: a stage running since the first candle read is a lower bound, not a fact."""
    r = scan.analyse(bars_from(list(np.linspace(100, 300, 420))))
    assert r["stage"] == 2 and r["stage_capped"] is True
    up = list(np.linspace(200, 90, 200)) + list(np.linspace(90, 200, 120))      # stage 2 begins well inside the window
    r = scan.analyse(bars_from(up))
    assert r["stage"] == 2 and r["stage_capped"] is False and r["stage_days"] < 120
