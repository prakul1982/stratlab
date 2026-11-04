"""SECMEM lane (Wed 4 Nov): one account can't read, change or delete another account's things by id (item 1d).
Two Pro accounts (so no plan lock hides a hole behind a 402): A makes one of each, B tries every by-id route on it.
Each must refuse (404/403/422) and A's item must stay exactly as it was."""

import json

import pytest

from app import guard
from tests import stress_requests as SR, world as W

A, B = W.headers("pro-token"), W.headers("money-23")
REFUSED = (403, 404, 422)
BTC = "CRYPTO:BTC-USD"


@pytest.fixture(scope="module")
def c():
    mp = pytest.MonkeyPatch()
    w = W.build(mp)
    mp.setattr(guard, "BAD_TOKENS_PER_MINUTE", 10**6)
    yield w["client"]
    w["close"]()
    mp.undo()


def ok(r):
    assert r.status_code == 200, r.text[:300]
    return r.json()


def refused(c, tries):
    for method, url, body in tries:
        r = c.request(method, url, headers=B, json=body)
        assert r.status_code in REFUSED, f"{method} {url} as another account: {r.status_code} {r.text[:160]}"


def owner_can(c, tries):
    """The same calls, made by the owner, go through: so the refusals above came from whose item it is, not a bad body."""
    for method, url, body in tries:
        r = c.request(method, url, headers=A, json=body)
        assert r.status_code == 200, f"{method} {url} as the owner: {r.status_code} {r.text[:160]}"


def test_watchlists(c):
    lists = ok(c.post("/watch/lists", headers=A, json={"name": "A list"}))["lists"]
    lid = next(x["id"] for x in lists if x["name"] == "A list")
    ok(c.put(f"/watch/lists/{lid}/items", headers=A, json={"items": [{"id": "IN:RELIANCE"}]}))
    before = ok(c.get("/watch/lists", headers=A))["lists"]
    refused(c, [("PATCH", f"/watch/lists/{lid}", {"name": "Stolen"}), ("DELETE", f"/watch/lists/{lid}", None),
                ("PUT", f"/watch/lists/{lid}/items", {"items": [{"id": "IN:TCS"}]})])
    assert ok(c.get("/watch/lists", headers=A))["lists"] == before
    assert lid not in json.dumps(ok(c.get("/watch/lists", headers=B)))
    owner_can(c, [("PATCH", f"/watch/lists/{lid}", {"name": "Renamed"}), ("PUT", f"/watch/lists/{lid}/items", {"items": [{"id": "IN:TCS"}]})])


def test_stock_and_breadth_alerts(c):
    aid = ok(c.post("/alerts", headers=A, json={"region": "IN", "symbol": "RELIANCE", "kind": "deal"}))["alert"]["id"]
    refused(c, [("PUT", f"/alerts/{aid}", {"region": "IN", "symbol": "TCS", "kind": "deal"}), ("DELETE", f"/alerts/{aid}", None)])
    mine = ok(c.get("/alerts", headers=A))["active"]
    assert [(x["id"], x["symbol"]) for x in mine] == [(aid, "RELIANCE")]
    assert aid not in json.dumps(ok(c.get("/alerts", headers=B)))
    owner_can(c, [("PUT", f"/alerts/{aid}", {"region": "IN", "symbol": "TCS", "kind": "deal"})])
    got = ok(c.post("/invest/breadth/alerts", headers=A, json={"group": "nifty500", "level": 60}))
    bid = got["items"][0]["id"]
    refused(c, [("DELETE", f"/invest/breadth/alerts/{bid}", None)])
    assert [x["id"] for x in ok(c.get("/invest/breadth/alerts", headers=A))["items"]] == [bid]


def test_holdings_and_tax(c):
    ok(c.put("/holdings", headers=A, json={"items": [{"symbol": "RELIANCE", "qty": 5, "avg": 1200, "market": "IN"}]}))
    assert ok(c.get("/holdings", headers=B))["rows"] == []
    c.delete("/holdings", headers=B)                                        # B clearing their own holdings leaves A's
    assert [x["symbol"] for x in ok(c.get("/holdings", headers=A))["rows"]] == ["RELIANCE"]
    t = ok(c.post("/money/us-tax/trades", headers=A, json={"d": "2025-03-03", "side": "B", "sym": "AAPL", "qty": 2, "price": 150}))
    tid = t["trades"][0]["id"]
    refused(c, [("DELETE", f"/money/us-tax/trades/{tid}", None)])
    assert [x["id"] for x in ok(c.get("/money/us-tax", headers=A))["trades"]] == [tid]
    assert ok(c.get("/money/us-tax", headers=B))["trades"] == []


def test_journal_trades(c):
    body = {"symbol": "INFY", "side": "long", "entry_date": "2026-03-02", "exit_date": "2026-03-03", "qty": 10,
            "entry_price": 1500, "exit_price": 1510}
    tid = ok(c.post("/trade/journal/trades", headers=A, json=body))["trades"][0]["id"]
    refused(c, [("PUT", f"/trade/journal/trades/{tid}/note", {"notes": "stolen"}), ("DELETE", f"/trade/journal/trades/{tid}", None)])
    mine = ok(c.get("/trade/journal", headers=A))["trades"]
    assert [x["id"] for x in mine] == [tid] and not mine[0].get("notes")
    assert ok(c.get("/trade/journal", headers=B))["trades"] == []
    owner_can(c, [("PUT", f"/trade/journal/trades/{tid}/note", {"notes": "mine"})])


def test_paper_sessions_and_signal_webhooks(c):
    sid = ok(c.post("/live/sessions", headers=A, json={"strategy": SR.EMA, "instrument": BTC}))["id"]
    refused(c, [("GET", f"/live/sessions/{sid}", None), ("POST", f"/live/sessions/{sid}/stop", None), ("DELETE", f"/live/sessions/{sid}", None)])
    assert ok(c.get(f"/live/sessions/{sid}", headers=A))["status"] == "running"
    assert sid not in json.dumps(ok(c.get("/live/sessions", headers=B)))
    # a forward test fed by an outside signal: B can't read it, test it, or reach it through B's own webhook
    fid = ok(c.post("/trade/signals/sessions", headers=A, json={"instrument": BTC, "capital": 100000}))["id"]
    refused(c, [("GET", f"/trade/signals/sessions/{fid}", None), ("POST", f"/trade/signals/sessions/{fid}/test", {"action": "buy"})])
    path = ok(c.post("/trade/signals/hook", headers=B))["path"]
    r = c.post(path, content=json.dumps({"session": fid, "action": "buy", "qty": 1}).encode(), headers={"Content-Type": "application/json"})
    assert r.status_code in REFUSED, r.text
    assert not ok(c.get(f"/trade/signals/sessions/{fid}", headers=A)).get("trade_list")
    owner_can(c, [("POST", f"/trade/signals/sessions/{fid}/test", {"action": "buy", "qty": 1}), ("POST", f"/live/sessions/{sid}/stop", None)])


def test_notebook_runs_and_library(c):
    nid = ok(c.post("/notebooks", headers=A, json={"name": "Mine", "market": "IN"}))["id"]
    refused(c, [("GET", f"/notebooks/{nid}/experiments/1/trades.csv", None), ("POST", f"/notebooks/{nid}/experiments/1/walkforward", None),
                ("POST", f"/notebooks/{nid}/experiments/1/basket", None),
                ("POST", f"/notebooks/{nid}/experiments/1/library", {"title": "Stolen", "description": "x"}),
                ("DELETE", f"/notebooks/{nid}/experiments/1/share", None)])
    assert ok(c.get(f"/notebooks/{nid}", headers=A))["name"] == "Mine"


def test_money_items_events_screens_scans_follows_keys_replays(c):
    iid = ok(c.post("/money/net-worth/items", headers=A, json={"kind": "cash", "value": 50000}))["assets"]
    iid = next(x["id"] for x in iid if x["kind"] == "cash")
    refused(c, [("PUT", f"/money/net-worth/items/{iid}", {"kind": "cash", "value": 1}), ("DELETE", f"/money/net-worth/items/{iid}", None)])
    assert [x["value"] for x in ok(c.get("/money/net-worth", headers=A))["assets"] if x["id"] == iid] == [50000]
    owner_can(c, [("PUT", f"/money/net-worth/items/{iid}", {"kind": "cash", "value": 1})])

    ev = ok(c.post("/money/calendar/events", headers=A, json={"date": "2026-11-05", "title": "FD matures"}))
    eid = ev["own"][0]["id"]
    refused(c, [("PUT", f"/money/calendar/events/{eid}", {"date": "2026-11-06", "title": "Stolen"}), ("DELETE", f"/money/calendar/events/{eid}", None)])
    assert [(x["id"], x["title"]) for x in ok(c.get("/money/calendar", headers=A))["own"]] == [(eid, "FD matures")]
    owner_can(c, [("PUT", f"/money/calendar/events/{eid}", {"date": "2026-11-06", "title": "Renamed"})])

    screen = {"name": "Low debt", "region": "IN", "filters": {"sector": ["Energy"]}, "notify": True}
    sid = ok(c.post("/research/screens/saved", headers=A, json=screen))["screen"]["id"]
    refused(c, [("PUT", f"/research/screens/saved/{sid}", {**screen, "name": "Stolen"}), ("DELETE", f"/research/screens/saved/{sid}", None)])
    assert [x["name"] for x in ok(c.get("/research/screens/saved", headers=A))["items"]] == ["Low debt"]
    owner_can(c, [("PUT", f"/research/screens/saved/{sid}", {**screen, "name": "Renamed"})])

    rules = [{"l": {"t": "volume"}, "op": "gt", "r": {"t": "vol_sma", "p": 20, "ago": 1, "k": 2}}]
    cid = ok(c.put("/research/scan/custom", headers=A, json={"name": "Volume", "region": "IN", "rules": rules}))["items"][0]["id"]
    c.delete(f"/research/scan/custom/{cid}", headers=B)
    c.put("/research/scan/custom", headers=B, json={"name": "Stolen", "region": "IN", "rules": rules, "id": cid})
    assert [x["name"] for x in ok(c.get("/research/scan/custom", headers=A))["items"]] == ["Volume"]   # B's copy is B's own

    fid = ok(c.put("/invest/holders/follow", headers=A, json={"label": "Ashish Kacholia", "names": ["ASHISH KACHOLIA"]}))["follows"][0]["id"]
    refused(c, [("DELETE", f"/invest/holders/follow/{fid}", None)])
    assert [x["id"] for x in ok(c.get("/invest/holders", headers=A))["follows"]] == [fid]

    kid = ok(c.post("/me/assistant/keys", headers=A, json={"name": "Laptop"}))["key"]["id"]
    refused(c, [("DELETE", f"/me/assistant/keys/{kid}", None)])
    assert any(k["id"] == kid and not k.get("revoked_at") for k in ok(c.get("/me/assistant", headers=A))["keys"])

    rid = ok(c.post("/trade/replay", headers=A, json={"instrument": BTC, "tf": "1d", "start": "2025-01-06"}))["id"]
    refused(c, [("GET", f"/trade/replay/{rid}", None), ("POST", f"/trade/replay/{rid}/finish", {"cursor": 1}), ("DELETE", f"/trade/replay/{rid}", None)])
    assert ok(c.get(f"/trade/replay/{rid}", headers=A))["id"] == rid
    owner_can(c, [("DELETE", f"/trade/replay/{rid}", None), ("DELETE", f"/me/assistant/keys/{kid}", None),
                  ("DELETE", f"/invest/holders/follow/{fid}", None)])
