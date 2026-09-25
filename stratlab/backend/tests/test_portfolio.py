"""Group (portfolio) backtests: shared slots, a portfolio-wide daily loss cap, the API."""
import pytest

from app.engine import portfolio
from app.models import Strategy
from tests.test_engine_intraday import day
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)

ALWAYS = [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}]


def ds(sym, bars):
    return {"inst": {"symbol": sym, "id": f"X:{sym}"}, "bars": bars, "start": 0, "lot": 1, "kind": "flat"}


def S(**kw):
    base = {"tf": "15m", "entry": ALWAYS, "exit": [], "risk": {"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0,
                                                                "sizing": "capital", "perTrade": 20000, "maxBars": 2}}
    base.update(kw)
    return Strategy(**base)


def test_slots_are_shared():
    a = day("2026-01-05", [100 + i for i in range(12)])
    b = day("2026-01-05", [50 + i for i in range(12)])
    out = portfolio.run([ds("A", a), ds("B", b)], S(), max_open=1)
    assert out["most_open"] == 1
    # both instruments get turns, but never at the same time
    spans = sorted((t["entry_t"], t["exit_t"]) for t in out["trades"])
    assert all(spans[k][1] <= spans[k + 1][0] for k in range(len(spans) - 1))
    assert {t["symbol"] for t in out["trades"]} <= {"A", "B"} and len(out["members"]) == 2
    both = portfolio.run([ds("A", a), ds("B", b)], S(), max_open=2)
    assert both["most_open"] == 2 and len(both["trades"]) > len(out["trades"])


def test_portfolio_loss_cap_closes_everything():
    a = day("2026-01-05", [100, 100, 95, 90, 85, 80])
    b = day("2026-01-05", [100, 100, 99, 98, 97, 96])
    s = S(risk={"capital": 100000, "sl": 0, "tgt": 0, "brokerage": 0, "slippage": 0, "sizing": "capital", "perTrade": 50000},
          session={"dailyLossPct": 3})
    out = portfolio.run([ds("A", a), ds("B", b)], s, max_open=2)
    whys = {t["why"] for t in out["trades"]}
    assert whys == {"Daily loss cap"} and len(out["trades"]) == 2 and not out["open_trades"]
    assert out["stats"]["ret"] < 0


def test_group_notebook_api(api):  # noqa: F811
    nb = api.post("/notebooks", json={"name": "Coins", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    presets = api.get("/groups", params={"market": "CRYPTO"}).json()
    assert presets[0]["id"] == "top_coins" and presets[0]["count"] == 10
    r = api.put(f"/notebooks/{nb['id']}", json={"group": {"id": "top_coins", "name": "10 large coins", "market": "CRYPTO", "maxOpen": 2,
                                                          "members": [{"symbol": s} for s in presets[0]["symbols"]]}})
    assert r.status_code == 200 and r.json()["group"]["maxOpen"] == 2
    listed = api.get("/notebooks").json()[0]
    assert listed["instrument"]["symbol"] == "10 large coins (10)"
    e = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400}).json()["experiment"]
    g = e["group"]
    assert e["instrument"]["type"] == "GROUP" and g["max_open"] == 2 and g["most_open"] <= 2
    assert {m["symbol"] for m in g["members"]} == {"BTC/USD", "ETH/USD", "SOL/USD"}      # the fake exchange lists three
    assert len(g["skipped"]) == 7 and any("not listed" in x for x in g["skipped"])
    assert len(e["series"]["t"]) == len(e["series"]["equity"]) and e["series"]["close"] == []
    assert {c["id"]: c["status"] for c in e["verdict"]["checks"]}["nearby"] == "skip"
    assert all("symbol" in t for t in e["trades"])
    assert api.post(f"/notebooks/{nb['id']}/experiments/1/walkforward").status_code == 400
    # picking one instrument again replaces the group
    api.put(f"/notebooks/{nb['id']}", json={"instrument": "CRYPTO:ETH-USD"})
    assert not api.get(f"/notebooks/{nb['id']}").json().get("group")
