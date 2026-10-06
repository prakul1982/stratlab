"""Trend scan presets: each rule set on a made-up chart built to meet it (and a chart that doesn't), the stored daily
results, the live scan and the endpoints, the speed over a 500-stock group, and facts-only wording."""
import re
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app import db, scan, scan_presets as P, universes
from app.engine.indicators import rsi

ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|best|cheap|expensive|bullish|bearish|target|should|recommend)\b", re.I)
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|nseindia|bseindia", re.I)


def weekdays(end: date, n: int) -> list[date]:
    d, out = end, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def bars(closes, vol=1000.0, end=date(2026, 9, 30), high=1.0, low=1.0):
    days = weekdays(end, len(closes))
    v = vol if hasattr(vol, "__len__") else [vol] * len(closes)
    return [{"t": f"{d}T00:00:00+05:30", "o": c, "h": c * high, "l": c * low, "c": float(c), "v": float(v[i])}
            for i, (d, c) in enumerate(zip(days, closes))]


def noise(n, seed=1, scale=0.01):
    return np.random.default_rng(seed).normal(0, scale, n)


def matches(closes, preset, **kw):
    r = P.evaluate(bars(closes, **kw), only=[preset])
    return (r or {}).get("matches", {}).get(preset)


# ---------- the rule sets ----------
def test_every_preset_is_a_valid_rule_set_with_words_and_no_advice():
    ids = [p["id"] for p in P.PRESETS]
    assert {"high52", "golden_cross", "rsi_bounce", "volume_surge", "bb_squeeze", "near_low52", "pullback"} <= set(ids)
    for p in P.listing():
        assert p["name"] and p["text"] and p["rules"] and p["within"] >= 1
        assert not ADVICE.search(p["text"] + " ".join(p["rules"]) + p["name"]), p["id"]


def test_high52_breakout_first_close_above_the_previous_252_day_high():
    flat = list(100 + noise(280, 3, 0.4))
    top = max(flat[-252:])
    hit = matches(flat + [top + 5], "high52")
    assert hit and hit["days_ago"] == 0 and "previous 252-day high" in hit["detail"]
    again = matches(flat + [top + 5, top + 6], "high52")
    assert again and again["days_ago"] == 1                                               # the cross was yesterday, within 3 days
    assert matches(flat + [top - 5], "high52") is None
    assert matches(flat + [top + 5] + [top + 4] * 5, "high52") is None                    # older than 3 candles


def test_golden_cross_50_over_200_within_five_days():
    closes = list(np.concatenate([np.linspace(200, 100, 250), np.linspace(100, 260, 120)]))
    df = pd.Series(closes)
    cross = next(i for i in range(201, len(closes)) if df.rolling(50).mean()[i] > df.rolling(200).mean()[i]
                 and df.rolling(50).mean()[i - 1] <= df.rolling(200).mean()[i - 1])
    assert matches(closes[:cross + 1], "golden_cross")["days_ago"] == 0
    assert matches(closes[:cross + 4], "golden_cross")["days_ago"] == 3
    assert matches(closes[:cross + 12], "golden_cross") is None
    assert matches(closes[:cross - 3], "golden_cross") is None
    hit = matches(closes[:cross + 1], "golden_cross")
    assert "50-day average" in hit["detail"] and "200-day" in hit["detail"]


def test_rsi_oversold_bounce_crosses_back_above_30():
    closes = list(np.concatenate([np.linspace(100, 60, 60), np.linspace(60, 75, 30)]))
    r = rsi(pd.Series(closes), 14)
    cross = next(i for i in range(15, len(closes)) if r[i] > 30 >= r[i - 1])
    hit = matches(closes[:cross + 1], "rsi_bounce")
    assert hit and hit["days_ago"] == 0 and "RSI" in hit["detail"]
    assert matches(closes[:cross - 2], "rsi_bounce") is None
    assert matches(closes[:cross + 8], "rsi_bounce") is None


def test_volume_surge_needs_double_the_20_day_average_and_an_up_close():
    closes = [100.0 + (i % 3) * 0.1 for i in range(80)]
    vol = [1000.0] * 80
    up = closes + [closes[-1] + 1]
    assert matches(up, "volume_surge", vol=vol + [2500.0])["days_ago"] == 0
    assert matches(up, "volume_surge", vol=vol + [1900.0]) is None                      # under 2 times
    assert matches(closes + [closes[-1] - 1], "volume_surge", vol=vol + [2500.0]) is None   # a down close
    hit = matches(up, "volume_surge", vol=vol + [2500.0])
    assert "2.5 times" in hit["detail"]
    assert matches(up, "volume_surge", vol=[0.0] * 81) is None                          # no volume (an index): nothing to say


def test_bollinger_squeeze_breakout_after_narrow_bands():
    wide = list(100 + noise(120, 7, 2.5))
    quiet = list(100 + noise(60, 8, 0.05))
    base = wide + quiet
    hit = matches(base + [103.0], "bb_squeeze")
    assert hit and hit["days_ago"] == 0 and "after a squeeze" in hit["detail"]
    assert matches(wide + [100.0] * 0 + list(100 + noise(60, 9, 2.5)) + [112.0], "bb_squeeze") is None   # bands were never narrow
    assert matches(base + [100.01], "bb_squeeze") is None                                # no close above the upper band


def test_near_52_week_low_within_five_percent_or_below():
    closes = list(np.concatenate([np.linspace(150, 100, 260), [100.0] * 5]))
    low = min(closes[-253:-1])
    near = matches(closes + [low * 1.03], "near_low52")
    assert near and "above the previous 252-day low" in near["detail"]
    assert matches(closes + [low * 0.95], "near_low52")["detail"].endswith(f"{low:,.2f}")       # below the old low
    assert matches(closes + [low * 1.2], "near_low52") is None


def test_pullback_in_an_uptrend():
    up = list(np.linspace(100, 200, 280))
    dip = up + [198.0, 196.5, 195.0]
    ema20 = pd.Series(dip).ewm(span=20, adjust=False).mean().iloc[-1]
    assert 195.0 < ema20 and 195.0 > pd.Series(dip).rolling(50).mean().iloc[-1]
    hit = matches(dip, "pullback")
    assert hit and "below the 20-day" in hit["detail"]
    assert matches(up, "pullback") is None                                                # still above its 20-day
    assert matches(list(np.linspace(200, 100, 280)), "pullback") is None                  # a downtrend


def test_st_s2_preset_is_the_stage_2_plus_supertrend_rule():
    up = list(np.linspace(100, 200, 300)) + list(np.linspace(200, 185, 12)) + list(np.linspace(185, 198, 4))
    hit = matches(up, "st_s2")
    assert hit and hit["days_ago"] == 0 and "Stage 2" in hit["detail"]
    assert matches(list(np.linspace(200, 90, 320)), "st_s2") is None


def test_too_little_history_and_odd_candles_say_nothing():
    assert P.evaluate(bars([100.0] * 30)) is None
    assert P.evaluate([]) is None
    assert P.evaluate(None) is None
    bad = bars(list(np.linspace(100, 120, 100)))
    bad[-1]["c"] = float("nan")
    assert P.evaluate(bad) is None


def test_only_candles_up_to_the_day_asked_for_count():
    flat = list(100 + noise(280, 3, 0.4))
    top = max(flat[-252:])
    b = bars(flat + [top + 5, top - 20])                                  # a half-made (or later) candle after the breakout
    assert P.evaluate(b, only=["high52"])["matches"]["high52"]["days_ago"] == 1
    cut = b[-2]["t"][:10]
    got = P.evaluate(b, through=cut, only=["high52"])
    assert got["as_of"] == cut and got["matches"]["high52"]["days_ago"] == 0


# ---------- the stored daily results ----------
def test_build_store_and_read_back(monkeypatch):
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    flat = list(100 + noise(280, 3, 0.4))
    top = max(flat[-252:])
    per = {"AAA": P.evaluate(bars(flat + [top + 5])), "BBB": P.evaluate(bars(flat + [top - 1])), "CCC": None}
    doc = P.build(per)
    assert doc["checked"] == 2 and doc["counts"]["high52"] == 1 and doc["as_of"] == "2026-09-30"
    assert [r["s"] for r in doc["rows"] if "high52" in r["m"]] == ["AAA"]
    P.save("nifty500", doc)
    got = P.stored_view("nifty500", "high52")
    assert got["checked"] == 2 and [r["symbol"] for r in got["rows"]] == ["AAA"]
    assert got["rows"][0]["days_ago"] == 0 and got["rows"][0]["day"] == "2026-09-30" and "previous 252-day high" in got["rows"][0]["detail"]
    assert P.stored_view("nifty500", "golden_cross")["rows"] == []
    assert P.stored_view("sp500", "high52") is None and P.stored_view("nifty500", "nope") is None
    store[P.KEY + "damaged"] = "{not json"
    assert P.load("damaged") is None


def test_a_group_of_500_stocks_is_worked_out_in_reasonable_time():
    """The daily run reads 500 stocks' candles anyway; the presets add a few milliseconds each (measured at about 15 ms
    a stock on a laptop). The bound is generous so a busy machine doesn't fail it, and still catches a slow rule."""
    rng = np.random.default_rng(11)
    data = [bars(list(100 * np.exp(np.cumsum(rng.normal(0.0004, 0.018, 300)))), vol=list(rng.integers(500, 3000, 300))) for _ in range(500)]
    began = time.perf_counter()
    got = [P.evaluate(b, through="2026-09-30") for b in data]
    took = time.perf_counter() - began
    assert all(g is not None for g in got)
    assert took < 60, f"500 stocks took {took:.1f}s"
    doc = P.build({f"S{i}": g for i, g in enumerate(got)})
    assert doc["checked"] == 500 and len(doc["rows"]) < 500
    assert len(str(doc)) < 400_000                         # small enough to store as one setting


# ---------- the live scan of a small group ----------
class FakeProv:
    def ready(self): return True
    def instrument(self, key): return {"symbol": key, "name": key.title(), "currency": "USD"}


class FakeRegistry:
    def __init__(self, series): self.series, self.prov = series, FakeProv()
    def provider(self, m): return self.prov
    def resolve(self, iid):
        return (self.prov, {"symbol": iid.split(":")[1]}) if iid.split(":")[1] in self.series else (self.prov, None)


def test_live_scan_of_a_small_group_lists_matches_with_dates(monkeypatch):
    scan._cache.clear()
    flat = list(100 + noise(280, 3, 0.4))
    top = max(flat[-252:])
    series = {"AAA": bars(flat + [top + 5]), "BBB": bars(flat + [top - 5]), "CCC": bars([100.0] * 10)}
    reg = FakeRegistry(series)
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series[iid.split(":")[1]])
    out = scan.run_preset(reg, "US", [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}, {"symbol": "ZZZ"}], "high52")
    assert [r["symbol"] for r in out["rows"]] == ["AAA"]
    assert out["checked"] == 2 and out["as_of"] == "2026-09-30" and out["missing"] == ["ZZZ"] and len(out["problems"]) == 1
    row = out["rows"][0]
    assert row["day"] == "2026-09-30" and row["days_ago"] == 0 and row["name"] == "Aaa"
    with pytest.raises(KeyError):
        scan.run_preset(reg, "US", [{"symbol": "AAA"}], "nope")
    scan._cache.clear()


# ---------- the endpoints ----------
@pytest.fixture
def client(monkeypatch):
    """The app with an in-memory settings store, a made-up market whose every US stock is flat but AAPL (a breakout today),
    and a Pro profile that tests can swap."""
    from fastapi.testclient import TestClient
    from app import main
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    flat = list(100 + noise(280, 3, 0.4))
    top = max(flat[-252:])
    series = {"AAPL": bars(flat + [top + 5])}

    class Reg(FakeRegistry):
        def resolve(self, iid):
            return self.prov, {"symbol": iid.split(":")[1]}

    reg = Reg(series)
    monkeypatch.setattr(scan, "_bars", lambda registry, iid: series.get(iid.split(":")[1]) or bars(flat))
    monkeypatch.setattr(main, "markets", reg)
    scan._cache.clear()
    main._results.clear()
    who = {"p": {"id": "u1", "plan": "pro", "_plan": "pro"}}
    main.app.dependency_overrides[main.current_profile] = lambda: who["p"]
    c = TestClient(main.app)
    c.kv, c.who, c.flat, c.top = kv, who, flat, top
    yield c
    main.app.dependency_overrides.clear()
    scan._cache.clear()
    main._results.clear()


def test_scan_sets_list_the_scans_and_the_big_group(client):
    r = client.get("/research/scan/sets?region=US").json()
    ids = [s["id"] for s in r["scans"]]
    assert ids[0] == "st_s2" and "high52" in ids and "golden_cross" in ids and len(ids) == len(P.PRESETS)
    assert all(x["name"] and x["text"] and x["rules"] for x in r["scans"])
    assert any(s["id"] == "sp500" and s["stored"] and s["count"] == 0 for s in r["sets"])           # nothing stored yet
    assert any(s["id"] == "nifty500" and s["stored"] for s in client.get("/research/scan/sets?region=IN").json()["sets"])
    assert r["template"]["entry"] and r["sets"][0]["id"] == "watchlist"


def test_a_stored_group_scan_reads_the_daily_result(client):
    P.save("sp500", P.build({"AAPL": P.evaluate(bars(client.flat + [client.top + 5])), "MSFT": P.evaluate(bars(client.flat))}))
    sets = client.get("/research/scan/sets?region=US").json()["sets"]
    assert next(s for s in sets if s["id"] == "sp500")["count"] == 2
    r = client.post("/research/scan", json={"region": "US", "set": "sp500", "scan": "high52"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "preset" and body["stored"] and body["as_of"] == "2026-09-30" and body["checked"] == 2 and body["matches"] == 1
    assert body["scan_name"] == "52-week high breakout" and body["name"] == "S&P 500"
    row = body["rows"][0]
    assert row["symbol"] == "AAPL" and row["name"] == "Apple Inc." and row["currency"] == "USD" and row["day"] == "2026-09-30" and row["detail"]
    assert not ADVICE.search(str(body)) and not PROVIDERS.search(str(body))
    none = client.post("/research/scan", json={"region": "US", "set": "sp500", "scan": "golden_cross"}).json()
    assert none["rows"] == [] and none["matches"] == 0 and none["checked"] == 2
    missing = client.post("/research/scan", json={"region": "IN", "set": "nifty500", "scan": "high52"})
    assert missing.status_code == 404 and "hasn't been checked" in missing.text


def test_a_live_group_scan_reads_the_candles_and_st_s2_keeps_its_old_answer(client):
    live = client.post("/research/scan", json={"region": "US", "set": "us_mega", "scan": "high52"})
    assert live.status_code == 200, live.text
    body = live.json()
    assert body["kind"] == "preset" and body["stored"] is False and body["checked"] == 20
    assert [r["symbol"] for r in body["rows"]] == ["AAPL"] and body["rows"][0]["days_ago"] == 0
    st = client.post("/research/scan", json={"region": "US", "set": "us_mega"})
    assert st.status_code == 200 and st.json()["kind"] == "st_s2" and "counts" in st.json()
    assert client.post("/research/scan", json={"region": "US", "set": "us_mega", "scan": "nope"}).status_code == 404


def test_scans_are_a_paid_feature_once_payments_are_live(client, monkeypatch):
    from app.config import settings
    for k, v in (("RAZORPAY_KEY_ID", "rzp_test_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "plan_b"), ("RAZORPAY_PLAN_PRO", "plan_p")):
        monkeypatch.setattr(settings, k, v)
    client.who["p"] = {"id": "u1", "plan": "free", "_plan": "free"}
    assert client.post("/research/scan", json={"region": "US", "set": "us_mega", "scan": "high52"}).status_code == 402


def test_sp500_list_is_committed_with_its_source_and_date():
    doc = universes.sp500_doc()
    assert doc["source"] and re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["as_of"]) and doc["name"] == "S&P 500"
    syms = universes.sp500_symbols()
    assert 480 <= len(syms) <= 520 and len(set(syms)) == len(syms)
    assert {"AAPL", "MSFT", "BRK-B", "JPM"} <= set(syms) and all(re.fullmatch(r"[A-Z0-9-]{1,6}", s) for s in syms)
    assert all(isinstance(c, int) and c > 0 for c in universes.sp500_ciks().values())
    assert set(universes.sp500_names()) == set(syms)
    assert set(universes.us_universe()) >= set(syms) and len(universes.us_universe()) == len(set(universes.us_universe()))
