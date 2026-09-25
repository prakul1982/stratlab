"""Importing strategies: StratLab exports, Pine Script (with and without the AI), other code."""
import json

import pytest
from fastapi.testclient import TestClient

from app import ai_writer, db, importer, main
from app.ai_providers import AIBusy
from app.main import app
from app.models import Strategy

PINE = """
//@version=5
strategy("Golden cross with RSI", overlay=true)
fastLen = input.int(20, "Fast")
slowLen = input.int(50, "Slow")
stopPct = input.float(2.0, "Stop %")
fast = ta.sma(close, fastLen)
slow = ta.sma(close, slowLen)
r = ta.rsi(close, 14)
longCond = ta.crossover(fast, slow) and r > 50
if longCond
    strategy.entry("Long", strategy.long)
if ta.crossunder(fast, slow)
    strategy.close("Long")
strategy.exit("Stop", "Long", stop=strategy.position_avg_price * (1 - stopPct / 100))
"""


def test_detect():
    assert importer.detect(PINE) == "pine"
    assert importer.detect('{"format": "stratlab-strategy-v1", "strategy": {}}') == "stratlab"
    assert importer.detect("import backtrader as bt\nclass S(bt.Strategy):\n    pass") == "python"
    assert importer.detect("void OnTick() { double ma = iMA(NULL,0,20,0,MODE_SMA,PRICE_CLOSE,0); }") == "mql"
    assert importer.detect("Buy = Cross(MA(C, 20), MA(C, 50));\nSell = Cross(MA(C, 50), MA(C, 20));") == "afl"
    assert importer.detect("Buy Reliance when RSI is below 30") == "text"
    assert importer.detect("anything", "algo.pine") == "pine"


def test_pine_reader_offline():
    out = importer.pine(PINE)
    assert out["name"] == "Golden cross with RSI" and out["side"] == "long"
    assert out["entry"] == [{"l": {"t": "sma", "p": 20}, "op": "xa", "r": {"t": "sma", "p": 50}},
                            {"l": {"t": "rsi", "p": 14}, "op": "gt", "r": {"t": "num", "v": 50.0}}]
    assert out["exit"] == [{"l": {"t": "sma", "p": 20}, "op": "xb", "r": {"t": "sma", "p": 50}}]
    assert out["risk"] == {"sl": 2.0} and out["notes"] == []


def test_pine_long_and_short_and_untranslatable():
    code = """strategy("Flip")
e = ta.ema(close, 12)
if ta.crossover(close, e)
    strategy.entry("L", strategy.long)
if ta.crossunder(close, e) and ta.vwma(close, 5) > 3
    strategy.entry("S", strategy.short)
strategy.exit("x", "L", loss=100)"""
    out = importer.pine(code)
    assert out["side"] == "long" and out["entry"][0]["op"] == "xa" and out["entry"][0]["r"] == {"t": "ema", "p": 12}
    assert out["exit"][0] == {"l": {"t": "price"}, "op": "xb", "r": {"t": "ema", "p": 12}}
    notes = " ".join(out["notes"])
    assert "also trades short" in notes and "vwma" in notes and "ticks or points" in notes


def test_stratlab_export_round_trip():
    s = {"name": "Mine", "tf": "1h", "side": "short", "entry": [{"l": {"t": "rsi", "p": 14}, "op": "gt", "r": {"t": "num", "v": 70}}],
         "exit": [], "risk": {"capital": 5000, "riskPct": 1, "sl": 3, "tgt": 0, "trail": 4, "maxBars": 10, "brokerage": 0, "slippage": 0.05}}
    out = importer.from_json(json.dumps({"format": "stratlab-strategy-v1", "instrument": {"id": "US:AAPL"}, "strategy": s}))
    assert out["instrument_id"] == "US:AAPL" and out["strategy"]["side"] == "short" and out["strategy"]["risk"]["trail"] == 4
    with pytest.raises(ValueError):
        importer.from_json(json.dumps({"strategy": {"entry": []}}))


@pytest.fixture
def client(monkeypatch):
    usage = []
    monkeypatch.setattr(db, "count_usage", lambda u, kind, since: len(usage))
    monkeypatch.setattr(db, "add_usage", lambda u, kind: usage.append(kind))
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "free", "plan": "free"}
    c = TestClient(app)
    c.usage = usage
    yield c
    app.dependency_overrides.clear()


def test_import_api(client, monkeypatch):
    calls = []

    def fake_complete(system, text, **kw):
        calls.append(text)
        return json.dumps({"name": "MA cross", "entry": [{"l": {"t": "sma", "p": 20}, "op": "xa", "r": {"t": "sma", "p": 50}}],
                           "exit": [], "notes": ["Position sizing was left out."]})
    monkeypatch.setattr(ai_writer, "complete", fake_complete)
    r = client.post("/import/strategy", json={"text": "import backtrader as bt\nclass S(bt.Strategy): pass", "filename": "s.py"}).json()
    assert r["source"] == "python" and r["used_ai"] and r["entry"][0]["op"] == "xa" and r["notes"]
    assert "Python" in calls[0] and "backtrader" in calls[0] and client.usage == ["ai"]
    # a StratLab export needs no AI and counts nothing
    exp = {"format": "stratlab-strategy-v1", "strategy": {"name": "X", "entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 1}}]}}
    r = client.post("/import/strategy", json={"text": json.dumps(exp)}).json()
    assert r["source"] == "stratlab" and r["strategy"]["name"] == "X" and not r["used_ai"] and client.usage == ["ai"]

    # AI down: Pine still imports with the built-in reader; other languages explain why not
    def busy(*a, **k):
        raise AIBusy("all busy")
    monkeypatch.setattr(ai_writer, "complete", busy)
    r = client.post("/import/strategy", json={"text": PINE}).json()
    assert r["source"] == "pine" and not r["used_ai"] and len(r["entry"]) == 2
    r = client.post("/import/strategy", json={"text": "void OnTick() { OrderSend(); }"})
    assert r.status_code == 503 and "Pine Script" in r.json()["detail"]["message"]
    r = client.post("/import/strategy", json={"text": '{"format": "stratlab-strategy-v1", "strategy": {"entry": []}}'})
    assert r.status_code == 400


def test_ai_writer_keeps_intraday_features(monkeypatch):
    reply = {"name": "Intraday momentum", "tf": "5m", "side": "both", "product": "intraday",
             "entry": [{"l": {"t": "day_chg"}, "op": "gt", "r": {"t": "num", "v": 2}}],
             "shortEntry": [{"l": {"t": "day_chg"}, "op": "lt", "r": {"t": "num", "v": -2}}],
             "session": {"start": "09:30", "end": "14:45", "squareoff": "15:00", "maxTradesDay": 2, "cooldown": 6, "dailyLossPct": 2},
             "risk": {"sl": 0.5, "tgt": 1, "sizing": "capital", "perTrade": 200000, "leverage": 5, "capital": 5000000},
             "instrument": "RELIANCE", "market": "IN", "universe": {"preset": "fno_liquid", "maxOpen": 25},
             "notes": ["Spread filter left out."]}
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: json.dumps(reply))
    out = ai_writer.write_strategy("momentum json", pro=True)
    assert out["universe"] == {"preset": "fno_liquid", "symbols": [], "maxOpen": 25} and out["instrument"] is None
    assert out["side"] == "both" and out["shortEntry"][0]["r"]["v"] == -2 and out["product"] == "intraday"
    assert out["session"]["squareoff"] == "15:00" and out["session"]["maxTradesDay"] == 2
    assert out["risk"]["sizing"] == "capital" and out["risk"]["leverage"] == 5
    s = Strategy(**{k: out[k] for k in ("entry", "exit", "shortEntry", "shortExit", "side", "session", "product")},
                 tf=out["tf"], risk=out["risk"])
    assert s.session.dailyLossPct == 2
    # a 7-EMA rejection with a higher timeframe, candle shape and a score
    reply2 = {"tf": "15m", "side": "long", "entryJoin": "score", "minScore": 5,
              "entry": [{"l": {"t": "price", "ago": 1}, "op": "gt", "r": {"t": "ema", "p": 7, "ago": 1}, "w": 2},
                        {"l": {"t": "lower_wick"}, "op": "gt", "r": {"t": "body", "k": 1.5}, "w": 3},
                        {"l": {"t": "price", "tf": "1h"}, "op": "gt", "r": {"t": "ema", "p": 7, "tf": "1h"}, "w": 2}],
              "risk": {"sl": 5, "stopType": "swing", "tgt": 3, "tgtType": "r"}}
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: json.dumps(reply2))
    out = ai_writer.write_strategy("ema7", pro=True)
    assert out["entryJoin"] == "score" and out["minScore"] == 5 and out["entry"][1]["r"]["k"] == 1.5
    assert out["entry"][2]["l"]["tf"] == "1h" and out["risk"]["stopType"] == "swing" and out["risk"]["tgtType"] == "r"


def test_universe_needs_a_preset_or_a_list():
    assert ai_writer._universe({"preset": "made_up"}) is None
    assert ai_writer._universe({"symbols": ["SBIN"]}) is None
    assert ai_writer._universe({"symbols": ["sbin", "tcs"], "maxOpen": 5}) == {"preset": None, "symbols": ["SBIN", "TCS"], "maxOpen": 5}
