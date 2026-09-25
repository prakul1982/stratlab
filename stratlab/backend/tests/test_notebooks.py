import math
import uuid
from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db, main
from app.data import Registry
from app.data.coinbase import CoinbaseProvider
from app.kite_service import KiteService
from tests.test_data import PRODUCTS
from tests.fake_yahoo import fake_yahoo
from app.intel.yahoo import Yahoo

EMA = {"name": "Trend follower", "tf": "1d",
       "entry": [{"l": {"t": "ema", "p": 10}, "op": "xa", "r": {"t": "ema", "p": 30}}],
       "exit": [{"l": {"t": "ema", "p": 10}, "op": "xb", "r": {"t": "ema", "p": 30}}],
       "risk": {"capital": 10000, "riskPct": 2, "sl": 4, "tgt": 0, "brokerage": 0, "slippage": 0.05}}


def wavy_coinbase():
    def handler(req: httpx.Request):
        if req.url.path == "/products":
            return httpx.Response(200, json=PRODUCTS)
        if req.url.path.endswith("/ticker"):
            return httpx.Response(200, json={"price": "30000"})
        if req.url.path.endswith("/candles"):
            g = int(req.url.params["granularity"])
            s = datetime.fromisoformat(req.url.params["start"]).timestamp()
            e = datetime.fromisoformat(req.url.params["end"]).timestamp()
            out, t = [], int(s // g * g)
            while t <= e:
                d = t / 86400
                c = 30000 * (1 + 0.0004 * (d - 19000)) + 2500 * math.sin(d / 9)
                out.append([t, c * 0.99, c * 1.01, c * 0.998, c, 5.0])
                t += g
            return httpx.Response(200, json=list(reversed(out))[:300])
        return httpx.Response(404)
    return httpx.MockTransport(handler)


@pytest.fixture
def api(monkeypatch):
    rows, usage = {}, []

    def save_strategy(user_id, name, body, token, sid=None):
        sid = sid or str(uuid.uuid4())
        rows[sid] = {"id": sid, "user_id": user_id, "name": name, "body": body, "instrument_token": token,
                     "updated_at": db.now_iso()}
        return dict(rows[sid])

    def list_rows(user_id):
        out = []
        for r in rows.values():
            b = r["body"]
            out.append({"id": r["id"], "name": r["name"], "instrument_token": r["instrument_token"],
                        "updated_at": r["updated_at"], "kind": b.get("kind"), "question": b.get("question"),
                        "instrument": b.get("instrument"), "summary": b.get("summary"), "tf": b.get("tf"),
                        "pinned": b.get("pinned"), "group": b.get("group")})
        return out

    monkeypatch.setattr(db, "save_strategy", save_strategy)
    monkeypatch.setattr(db, "get_strategy", lambda u, sid: dict(rows[sid]) if sid in rows else None)
    monkeypatch.setattr(db, "list_notebook_rows", list_rows)
    monkeypatch.setattr(db, "delete_strategy", lambda u, sid: rows.pop(sid, None))
    monkeypatch.setattr(db, "count_usage", lambda u, kind, since: len(usage))
    monkeypatch.setattr(db, "add_usage", lambda u, kind: usage.append(kind))
    monkeypatch.setattr(main, "markets", Registry(KiteService(), CoinbaseProvider(transport=wavy_coinbase()), yahoo=Yahoo(transport=fake_yahoo())))
    profile = {"id": "user-1", "_plan": "pro", "plan": "pro"}
    main.app.dependency_overrides[main.current_profile] = lambda: profile
    client = TestClient(main.app)
    client.rows, client.usage, client.profile = rows, usage, profile
    yield client
    main.app.dependency_overrides.clear()


def test_markets_catalogue(api):
    m = {x["id"]: x for x in api.get("/markets").json()}
    assert m["CRYPTO"]["status"] == "live" and m["IN"]["status"] == "offline" and m["US"]["status"] == "live"
    assert all(m[x]["status"] == "live" for x in ("UK", "EU", "JP", "FX"))
    assert m["CRYPTO"]["max_days"]["5m"] == 30


def test_search_and_instrument(api):
    hits = api.get("/instruments/search", params={"q": "btc", "market": "crypto"}).json()
    assert hits[0]["id"] == "CRYPTO:BTC-USD"
    assert api.get("/instruments/CRYPTO:ETH-USD").json()["symbol"] == "ETH/USD"
    assert api.get("/instruments/CRYPTO:ETH-USD/ltp").json()["ltp"] == 30000
    assert api.get("/instruments/CRYPTO:NOPE-USD").status_code == 404
    vod = api.get("/instruments/UK:VOD.L").json()
    assert vod["name"] == "VODAFONE GROUP PLC" and vod["currency"] == "GBP" and vod["market"] == "UK"
    assert api.get("/instruments/XX:ABC").status_code == 400


def test_notebook_experiments_flow(api):
    nb = api.post("/notebooks", json={"name": "Trend follower", "question": "Does the 10/30 cross work on BTC?",
                                      "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    assert nb["instrument"]["symbol"] == "BTC/USD" and nb["experiments"] == []

    r = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1500, "label": "First try"})
    assert r.status_code == 200, r.text
    exp = r.json()["experiment"]
    assert exp["v"] == 1 and exp["label"] == "First try"
    assert exp["verdict"]["verdict"] in ("edge", "mixed", "luck", "not_enough", "no_edge")
    assert len(exp["series"]["t"]) <= 240 and len(exp["series"]["t"]) == len(exp["series"]["equity"])
    assert exp["instrument"]["currency"] == "USD"
    assert any(i["label"] == "Exchange fee" for i in exp["costs"]["items"])
    assert exp["stats"]["n"] > 0

    # change the rules, run again: v2, and the list shows the summary
    tighter = {**EMA, "risk": {**EMA["risk"], "sl": 2}}
    api.put(f"/notebooks/{nb['id']}", json={"strategy": tighter, "notes": "Tighter stop next"})
    exp2 = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1500}).json()["experiment"]
    assert exp2["v"] == 2 and exp2["label"] == "Experiment v2" and exp2["strategy"]["risk"]["sl"] == 2
    listed = api.get("/notebooks").json()
    assert listed[0]["summary"]["experiments"] == 2 and listed[0]["question"].startswith("Does")
    full = api.get(f"/notebooks/{nb['id']}").json()
    assert [e["v"] for e in full["experiments"]] == [1, 2] and full["notes"] == "Tighter stop next"

    api.delete(f"/notebooks/{nb['id']}/experiments/1")
    assert [e["v"] for e in api.get(f"/notebooks/{nb['id']}").json()["experiments"]] == [2]
    assert len(api.usage) == 2


def test_uploaded_csv_experiment(api):
    nb = api.post("/notebooks", json={"name": "My data", "strategy": EMA}).json()
    bars = [{"t": f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": 100, "h": 101 + (i % 7), "l": 99,
             "c": 100 + 8 * math.sin(i / 6), "v": 0} for i in range(300)]
    r = api.post(f"/notebooks/{nb['id']}/experiments",
                 json={"bars": bars, "upload": {"name": "GOLD futures", "currency": "USD", "step": 0.01}})
    assert r.status_code == 200, r.text
    exp = r.json()["experiment"]
    assert exp["instrument"]["market"] == "CSV" and exp["instrument"]["symbol"] == "GOLD futures"
    assert exp["candles"] == 240        # the first 60 candles warm up the indicators


def test_bad_upload_is_explained(api):
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA}).json()
    r = api.post(f"/notebooks/{nb['id']}/experiments", json={"bars": [{"t": "yesterday", "o": 1, "h": 1, "l": 1, "c": 1}]})
    assert r.status_code == 400 and "date" in r.json()["detail"]["message"]


def test_old_saved_strategy_opens_as_notebook(api):
    sid = str(uuid.uuid4())
    api.rows[sid] = {"id": sid, "user_id": "user-1", "name": "Old one", "body": EMA, "instrument_token": 256265,
                     "updated_at": db.now_iso()}
    nb = api.get(f"/notebooks/{sid}").json()
    assert nb["kind"] == "notebook" and nb["question"] == "Old one" and nb["strategy"]["name"] == "Trend follower"
    assert nb["instrument"] == {"id": "IN:256265"}
    assert api.get("/notebooks").json()[0]["instrument"] == {"id": "IN:256265"}


def test_backtest_limit(api):
    api.profile["_plan"] = "free"
    api.usage.extend(["backtest"] * 5)
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    r = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 365})
    assert r.status_code == 402 and r.json()["detail"]["code"] == "backtest_limit"


def test_needs_an_instrument(api):
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA}).json()
    r = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 365})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "no_instrument"


def test_us_stock_backtest_uses_us_costs(api):
    nb = api.post("/notebooks", json={"name": "SPY trend", "question": "Does a 10/30 cross work on SPY?",
                                      "strategy": EMA, "instrument": "US:SPY"}).json()
    assert nb["instrument"]["market"] == "US" and nb["instrument"]["currency"] == "USD"
    r = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1500})
    assert r.status_code == 200, r.text
    exp = r.json()["experiment"]
    labels = {i["label"] for i in exp["costs"]["items"]}
    assert exp["stats"]["n"] > 0 and ("SEC fee" in labels or "FINRA fee" in labels)


def test_basket_robustness_check(api):
    nb = api.post("/notebooks", json={"name": "Trend follower", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1500})
    r = api.post(f"/notebooks/{nb['id']}/experiments/1/basket")
    assert r.status_code == 200, r.text
    b = r.json()["basket"]
    ids = [row["id"] for row in b["rows"]]
    # its own instrument is left out, and coins the exchange doesn't list are skipped
    assert ids and "CRYPTO:BTC-USD" not in ids and set(ids) <= {"CRYPTO:ETH-USD", "CRYPTO:SOL-USD"}
    assert b["tested"] >= 1 and b["status"] in ("pass", "warn", "fail") and b["headline"]
    tested = [row for row in b["rows"] if "error" not in row]
    assert all({"ret", "buy_hold", "n", "win"} <= row.keys() for row in tested)
    # the whole check counts as one test, and is kept on the experiment
    assert len(api.usage) == 2
    assert api.get(f"/notebooks/{nb['id']}").json()["experiments"][0]["basket"]["headline"] == b["headline"]
    assert api.post(f"/notebooks/{nb['id']}/experiments/9/basket").status_code == 404


def test_walkforward(api):
    nb = api.post("/notebooks", json={"name": "Trend follower", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1500})
    r = api.post(f"/notebooks/{nb['id']}/experiments/1/walkforward")
    assert r.status_code == 200, r.text
    w = r.json()["walkforward"]
    assert w["status"] in ("pass", "warn", "fail") and w["headline"] and w["total"] == len(w["windows"]) >= 3
    first, last = w["windows"][0], w["windows"][-1]
    assert first["train_to"] == first["test_from"] and first["test_to"] <= w["windows"][1]["test_from"]
    assert all(len(x["chosen"]) == 2 and x["chosen"][0]["label"] == "EMA" for x in w["windows"])   # both lengths re-tuned
    assert last["test_to"] == w["to"] and w["grid_size"] == 25
    assert len(w["series"]["t"]) == len(w["series"]["wf"]) == len(w["series"]["fixed"]) and w["series"]["wf"][0] == 0
    # stitched curve ends at the compounded return of the unseen blocks
    assert abs(w["series"]["wf"][-1] - w["wf_ret"]) < 0.05
    assert len(api.usage) == 2
    assert api.get(f"/notebooks/{nb['id']}").json()["experiments"][0]["walkforward"]["headline"] == w["headline"]


def test_walkforward_skips_rules_with_nothing_to_tune():
    from app.engine import walkforward
    from app.models import Strategy
    from tests.test_engine import bars_from
    bars = bars_from([100 + (i % 30) for i in range(400)])
    s = Strategy(entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 110}}], exit=[], risk=EMA["risk"])
    out = walkforward.run(bars, s, 50)
    assert out["status"] == "skip" and "nothing" in out["detail"].lower()
    short = Strategy(**{k: EMA[k] for k in ("entry", "exit", "risk")})
    assert walkforward.run(bars[:120], short, 50)["status"] == "skip"


def test_pin_and_duplicate(api):
    a = api.post("/notebooks", json={"name": "First", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    b = api.post("/notebooks", json={"name": "Second", "strategy": EMA}).json()
    api.post(f"/notebooks/{a['id']}/experiments", json={"days": 1500})
    api.put(f"/notebooks/{b['id']}", json={"pinned": True})
    listed = api.get("/notebooks").json()
    assert listed[0]["id"] == b["id"] and listed[0]["pinned"] and not listed[1]["pinned"]
    api.put(f"/notebooks/{b['id']}", json={"name": "Renamed"})           # an unrelated edit keeps the pin
    assert api.get(f"/notebooks/{b['id']}").json()["pinned"] is True
    copy = api.post(f"/notebooks/{a['id']}/duplicate").json()
    assert copy["name"] == "First (copy)" and copy["experiments"] == [] and copy["id"] != a["id"]
    assert copy["strategy"]["entry"] == api.get(f"/notebooks/{a['id']}").json()["strategy"]["entry"]
    assert copy["instrument"]["symbol"] == "BTC/USD"
