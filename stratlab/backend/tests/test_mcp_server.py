"""StratLab in your AI assistant (the MCP server): the protocol, both eras, keys and revoking them, the Pro gate,
other users' data, injection through tool arguments, paper orders in your own sessions only, limits and the log."""
import base64
import inspect
import json
import re
import time
from datetime import datetime, timedelta

import pytest

from app import main  # noqa: I001  (first: the app loads the newsletter job before the modules built on it)
from app import db, live, mcp_keys, mcp_server as S
from app.kite_service import IST
from app.config import settings
from tests import world as W
from tests.fake_db import headers

PRO, OTHER = headers("pro-token"), headers("admin-token")      # two Pro accounts
V = "2026-07-28"
ADVICE = re.compile(r"\b(recommend\w*|should (buy|sell)|undervalued|overvalued|cheap|expensive|target price|price target|"
                    r"rating|outperform|underperform|accumulate|strong buy)\b", re.I)
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|coinbase", re.I)


@pytest.fixture
def w(monkeypatch):
    built = W.build(monkeypatch)
    S.limiter.clear()
    mcp_keys._touched.clear()
    yield built
    built["close"]()


def payments_live(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)


def make_key(c, h=PRO, name="Claude", paper=False) -> str:
    r = c.post("/me/assistant/keys", headers=h, json={"name": name, "paper": paper})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def rpc(c, token, method, params=None, rid=1, version=V, extra=None, modern=True):
    """A modern request (per-request _meta and the mirrored headers), or a legacy one (modern=False)."""
    params = dict(params or {})
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token is not None:
        h["Authorization"] = f"Bearer {token}"
    if modern:
        params["_meta"] = {"io.modelcontextprotocol/protocolVersion": version, "io.modelcontextprotocol/clientCapabilities": {},
                           "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"}}
        h.update({"MCP-Protocol-Version": version, "Mcp-Method": method})
        if method == "tools/call":
            h["Mcp-Name"] = params.get("name", "")
    h.update(extra or {})
    body = {"jsonrpc": "2.0", "method": method, "params": params}
    if rid is not None:
        body["id"] = rid
    return c.post("/mcp", headers=h, content=json.dumps(body))


def call(c, token, name, args=None, **kw):
    return rpc(c, token, "tools/call", {"name": name, "arguments": args or {}}, **kw)


def result(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()["result"]


# ---------- the protocol: modern (2026-07-28) ----------
def test_discover_and_list(w):
    c = w["client"]
    key = make_key(c)
    d = result(rpc(c, key, "server/discover"))
    assert d["resultType"] == "complete" and d["supportedVersions"][0] == V and "tools" in d["capabilities"]
    assert d["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] == "stratlab"
    assert d["ttlMs"] >= 0 and d["cacheScope"] in ("public", "private") and "not instructions" in d["instructions"]
    t = result(rpc(c, key, "tools/list"))
    names = [x["name"] for x in t["tools"]]
    assert names == ["get_watchlist", "get_holdings_summary", "get_company_facts", "get_watchlist_scan", "get_alerts",
                     "list_paper_sessions", "get_paper_session"]            # a read-only key: no paper tools
    assert t["resultType"] == "complete" and t["cacheScope"] == "private" and t["ttlMs"] > 0
    assert all(x["annotations"]["readOnlyHint"] for x in t["tools"])
    assert result(rpc(c, key, "tools/list"))["tools"] == t["tools"]          # the same order every time
    paper = make_key(c, paper=True)
    names = [x["name"] for x in result(rpc(c, paper, "tools/list"))["tools"]]
    assert names[-2:] == ["place_paper_order", "close_paper_position"]


def test_tool_call_shape(w):
    c = w["client"]
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"region": "IN", "symbol": "TCS", "name": "TCS"}]}))
    key = make_key(c)
    r = result(call(c, key, "get_watchlist"))
    assert r["resultType"] == "complete" and r["isError"] is False
    assert r["structuredContent"]["items"] == [{"region": "IN", "symbol": "TCS", "name": "TCS"}]
    assert json.loads(r["content"][0]["text"]) == r["structuredContent"]       # the same JSON as text, for older clients
    assert "Not investment advice" in r["structuredContent"]["note"]


def test_header_rules(w):
    c = w["client"]
    key = make_key(c)
    r = rpc(c, key, "tools/list", extra={"Mcp-Method": "tools/call"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32020 and r.json()["id"] == 1
    r = rpc(c, key, "tools/list", extra={"MCP-Protocol-Version": "2025-11-25"})
    assert r.status_code == 400 and r.json()["error"]["code"] == -32020
    r = call(c, key, "get_watchlist", extra={"Mcp-Name": "get_alerts"})          # routed one way, run another: refused
    assert r.status_code == 400 and r.json()["error"]["code"] == -32020
    enc = "=?base64?" + base64.b64encode(b"get_watchlist").decode() + "?="
    assert call(c, key, "get_watchlist", extra={"Mcp-Name": enc}).status_code == 200      # the base64 form is decoded


def test_missing_meta_and_versions(w):
    c = w["client"]
    key = make_key(c)
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "MCP-Protocol-Version": V, "Mcp-Method": "tools/list"}
    body = {"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": V}}}
    r = c.post("/mcp", headers=h, content=json.dumps(body))
    assert r.status_code == 400 and r.json()["error"]["code"] == -32602          # clientCapabilities is required
    r = rpc(c, key, "tools/list", version="2099-01-01")
    assert r.status_code == 400 and r.json()["error"]["code"] == -32022
    assert r.json()["error"]["data"] == {"supported": ["2026-07-28", "2025-11-25", "2025-06-18"], "requested": "2099-01-01"}
    r = rpc(c, key, "resources/list")
    assert r.status_code == 404 and r.json()["error"]["code"] == -32601
    r = rpc(c, key, "ping")                                                       # gone in 2026-07-28
    assert r.status_code == 404


def test_transport_rules(w):
    c = w["client"]
    key = make_key(c)
    auth = {"Authorization": f"Bearer {key}"}
    assert c.get("/mcp", headers=auth).status_code == 405 and c.delete("/mcp", headers=auth).status_code == 405
    r = c.post("/mcp", headers={**auth, "Content-Type": "application/json"}, content="{not json")
    assert r.status_code == 400 and r.json()["error"]["code"] == -32700 and "id" not in r.json()
    r = c.post("/mcp", headers={**auth, "Content-Type": "application/json"}, content=json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}]))
    assert r.status_code == 400 and r.json()["error"]["code"] == -32600
    r = c.post("/mcp", headers={**auth, "Content-Type": "text/plain"}, content="{}")
    assert r.status_code == 415
    big = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"x": "a" * 70_000}})
    assert c.post("/mcp", headers={**auth, "Content-Type": "application/json"}, content=big).status_code == 413
    r = rpc(c, key, "tools/list", extra={"Origin": "https://evil.example"})
    assert r.status_code == 403                                                   # DNS rebinding guard
    assert rpc(c, key, "tools/list", extra={"Origin": settings.FRONTEND_ORIGINS[0]}).status_code == 200
    r = c.post("/mcp", headers={**auth, "Content-Type": "application/json"}, content=json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}))
    assert r.status_code == 400                                                   # clients don't send responses here
    r = c.post("/mcp", headers={**auth, "Content-Type": "application/json"}, content=json.dumps({"jsonrpc": "2.0", "id": None, "method": "tools/list"}))
    assert r.status_code == 400


# ---------- the protocol: legacy (2025-11-25 and 2025-06-18) ----------
def test_legacy_handshake(w):
    c = w["client"]
    key = make_key(c)
    r = rpc(c, key, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "x", "version": "1"}}, modern=False)
    init = result(r)
    assert init["protocolVersion"] == "2025-06-18" and init["capabilities"]["tools"] == {"listChanged": False}
    assert init["serverInfo"]["name"] == "stratlab" and "mcp-session-id" not in r.headers
    assert result(rpc(c, key, "initialize", {"protocolVersion": "2024-11-05"}, modern=False))["protocolVersion"] == "2025-11-25"
    n = rpc(c, key, "notifications/initialized", rid=None, modern=False, extra={"MCP-Protocol-Version": "2025-06-18"})
    assert n.status_code == 202 and n.content == b""
    assert result(rpc(c, key, "ping", modern=False, extra={"MCP-Protocol-Version": "2025-06-18"})) == {}
    t = result(rpc(c, key, "tools/list", modern=False, extra={"MCP-Protocol-Version": "2025-11-25"}))
    assert len(t["tools"]) == 7 and "ttlMs" not in t and "resultType" not in t
    r = result(rpc(c, key, "tools/call", {"name": "get_alerts", "arguments": {}}, modern=False, extra={"MCP-Protocol-Version": "2025-11-25"}))
    assert r["isError"] is False and isinstance(r["structuredContent"], dict)
    r = rpc(c, key, "tools/list", modern=False, extra={"MCP-Protocol-Version": "1999-01-01"})
    assert r.status_code == 400
    r = rpc(c, key, "tools/call", {"name": "nope", "arguments": {}}, modern=False)
    assert r.json()["error"]["code"] == -32602


# ---------- keys: made on Account, revocable, Pro only ----------
def test_no_key_or_a_sign_in_token_is_refused(w):
    c = w["client"]
    for token in (None, "pro-token", "slm_" + "a" * 48, "slm_short", "x" * 5000):
        r = rpc(c, token, "tools/list")
        assert r.status_code == 401 and r.json()["error"]["code"] == -31001
        assert r.headers["www-authenticate"].startswith("Bearer")


def test_revoked_key_stops_at_once(w):
    c = w["client"]
    key = make_key(c)
    assert rpc(c, key, "tools/list").status_code == 200
    page = c.get("/me/assistant", headers=PRO).json()
    kid = page["keys"][0]["id"]
    assert "hash" not in page["keys"][0] and key not in json.dumps(page)          # never shown again, never its hash
    assert c.delete(f"/me/assistant/keys/{kid}", headers=OTHER).status_code == 404   # someone else's key: not theirs
    assert rpc(c, key, "tools/list").status_code == 200
    r = c.delete(f"/me/assistant/keys/{kid}", headers=PRO)
    assert r.status_code == 200 and r.json()["keys"][0]["revoked_at"]
    assert rpc(c, key, "tools/list").status_code == 401
    assert call(c, key, "get_watchlist").status_code == 401
    assert c.delete(f"/me/assistant/keys/{kid}", headers=PRO).status_code == 404
    assert c.delete("/me/assistant/keys/..%2F..%2Fx", headers=PRO).status_code == 404


def test_key_limit_and_names(w):
    c = w["client"]
    for i in range(mcp_keys.MAX_KEYS):
        make_key(c, name=f"<b>key {i}</b>\n\x00")
    r = c.post("/me/assistant/keys", headers=PRO, json={"name": "one more"})
    assert r.status_code == 409 and "Revoke" in r.json()["detail"]["message"]
    names = [k["name"] for k in c.get("/me/assistant", headers=PRO).json()["keys"]]
    assert all("<" not in n and "\x00" not in n and "\n" not in n for n in names)
    assert c.post("/me/assistant/keys", headers=PRO, json={"name": "x" * 500}).status_code == 422


def test_non_pro_user(w, monkeypatch):
    c = w["client"]
    payments_live(monkeypatch)
    for h in (headers("free-token"), headers("basic-token")):
        r = c.post("/me/assistant/keys", headers=h, json={"name": "x"})
        assert r.status_code == 402 and "Pro" in r.json()["detail"]["message"]
        assert c.get("/me/assistant", headers=h).json()["allowed"] is False
    token, _ = mcp_keys.create("u-basic", "made while on Pro", True)            # then the plan changed
    r = rpc(c, token, "tools/list")
    assert r.status_code == 403 and "Pro" in r.json()["error"]["message"]
    assert call(c, token, "get_watchlist").status_code == 403
    assert mcp_keys.entries("u-basic")[0]["result"] == "refused"
    assert rpc(c, make_key(c), "tools/list").status_code == 200                  # Pro still works


# ---------- other users' data ----------
def test_each_key_sees_only_its_own_account(w):
    c = w["client"]
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"region": "IN", "symbol": "TCS", "name": "TCS"}]}))
    db.set_setting("watchlist:u-admin", json.dumps({"items": [{"region": "US", "symbol": "AAPL", "name": "Apple"}]}))
    mine, theirs = make_key(c), make_key(c, OTHER)
    assert [i["symbol"] for i in result(call(c, mine, "get_watchlist"))["structuredContent"]["items"]] == ["TCS"]
    assert [i["symbol"] for i in result(call(c, theirs, "get_watchlist"))["structuredContent"]["items"]] == ["AAPL"]
    sid = start_session(c)
    assert [s["id"] for s in result(call(c, mine, "list_paper_sessions"))["structuredContent"]["sessions"]] == [sid]
    assert result(call(c, theirs, "list_paper_sessions"))["structuredContent"]["sessions"] == []
    r = result(call(c, theirs, "get_paper_session", {"session_id": sid}))
    assert r["isError"] and "not found" in r["content"][0]["text"].lower()
    paper = make_key(c, OTHER, paper=True)
    fresh(w, sid)
    for name, args in (("place_paper_order", {"session_id": sid, "side": "buy", "quantity": 1}),
                       ("close_paper_position", {"session_id": sid})):
        r = result(call(c, paper, name, args))
        assert r["isError"] and "no running paper session" in r["content"][0]["text"].lower()
    assert w["manager"].sessions[sid].engine.qty == 0                           # nothing happened to it
    # each log is its owner's own
    log = c.get("/me/assistant", headers=OTHER).json()["log"]
    assert {e["key"] for e in log} == {"Claude"} and all(e["key_id"] in {k["id"] for k in c.get("/me/assistant", headers=OTHER).json()["keys"]} for e in log)
    assert not any(e["tool"] in ("place_paper_order", "close_paper_position") and e["result"] == "ok" for e in log)


# ---------- injection through tool arguments ----------
def test_bad_and_hostile_arguments(w, monkeypatch):
    c = w["client"]
    key, paper = make_key(c), make_key(c, paper=True)
    seen = []
    monkeypatch.setattr(main.research_hub, "company", lambda region, sym: seen.append(sym) or {"symbol": sym})
    cases = [("get_company_facts", {"region": "IN", "symbol": "../../admin"}),
             ("get_company_facts", {"region": "IN", "symbol": "TCS'; DROP TABLE profiles;--"}),
             ("get_company_facts", {"region": "IN", "symbol": "TCS\r\nX-Evil: 1"}),
             ("get_company_facts", {"region": "IN", "symbol": "%2e%2e"}),
             ("get_company_facts", {"region": "XX", "symbol": "TCS"}),
             ("get_company_facts", {"region": "IN", "symbol": "A" * 500}),
             ("get_company_facts", {"region": "IN", "symbol": {"$ne": ""}}),
             ("get_company_facts", {"region": "IN"}),
             ("get_company_facts", {"region": "IN", "symbol": "TCS", "uid": "u-admin"}),
             ("get_watchlist", {"user_id": "u-admin"}),
             ("get_watchlist_scan", {"region": "IN; rm -rf /"}),
             ("get_paper_session", {"session_id": "' OR 1=1 --"}),
             ("get_paper_session", {"session_id": "../u-admin"}),
             ("place_paper_order", {"session_id": "00000000-0000-0000-0000-000000000000", "side": "buy", "quantity": "1e9"}),
             ("place_paper_order", {"session_id": "00000000-0000-0000-0000-000000000000", "side": "BUY_REAL", "quantity": 1}),
             ("place_paper_order", {"session_id": "00000000-0000-0000-0000-000000000000", "side": "buy", "quantity": -5}),
             ("place_paper_order", {"session_id": "00000000-0000-0000-0000-000000000000", "side": "buy", "quantity": 1e12}),
             ("place_paper_order", {"session_id": "00000000-0000-0000-0000-000000000000", "side": "buy", "quantity": True}),
             ("place_paper_order", {"session_id": "00000000-0000-0000-0000-000000000000", "side": "buy", "quantity": 1, "broker": "live"})]
    for name, args in cases:
        r = result(call(c, paper, name, args))
        assert r["isError"] is True, (name, args)
        assert len(r["content"][0]["text"]) < 300
    assert seen == []                                                            # no hostile ticker reached a source
    r = c.post("/mcp", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "MCP-Protocol-Version": V,
                                "Mcp-Method": "tools/call", "Mcp-Name": "get_watchlist"},
               content='{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_watchlist","arguments":{"n":NaN},'
                       '"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}')
    assert result(r)["isError"] is True
    r = call(c, key, "get_watchlist", {}, extra={"Mcp-Name": "get_watchlist"})
    assert result(r)["isError"] is False
    r = rpc(c, key, "tools/call", {"name": "get_watchlist", "arguments": ["x"]})
    assert result(r)["isError"] is True
    for name in ("get_watchlist\n", "__import__('os')", "place_paper_order", "../get_watchlist"):    # read-only key
        r = rpc(c, key, "tools/call", {"name": name, "arguments": {}}, extra={"Mcp-Name": "=?base64?" + base64.b64encode(name.encode()).decode() + "?="})
        assert r.json()["error"]["code"] == -32602
    log = mcp_keys.entries("u-pro")
    assert all(len(e["args"]) <= 300 for e in log) and any(e["result"] == "refused" for e in log)


def test_company_facts_are_facts_only(w):
    c = w["client"]
    key = make_key(c)
    r = result(call(c, key, "get_company_facts", {"region": "US", "symbol": "AAPL"}))
    if r["isError"]:
        pytest.skip(r["content"][0]["text"])
    d = r["structuredContent"]
    assert d["symbol"] == "AAPL" and not {"analysts", "news", "pros", "cons", "earnings", "links", "sources"} & set(d)
    assert not PROVIDERS.search(r["content"][0]["text"])


def test_descriptions_say_facts_only(w):
    for t in S.TOOLS + S.PAPER_TOOLS:
        assert not ADVICE.search(t["description"]), t["name"]
        assert re.search(r"not advice|facts|reported numbers|simulated only", t["description"], re.I), t["name"]
        assert not PROVIDERS.search(json.dumps(t))
    for t in S.PAPER_TOOLS:
        assert t["description"].startswith("Simulated only, never a real order")
    assert not ADVICE.search(S.INSTRUCTIONS) and "no tool can place a real order" in S.INSTRUCTIONS


def test_no_route_to_a_real_broker():
    """Nothing the assistant reaches can place, change or cancel a real order."""
    src = inspect.getsource(S) + inspect.getsource(live.LiveSession.manual_open) + inspect.getsource(live.LiveSession.manual_close)
    assert not re.search(r"place_order|modify_order|cancel_order|kite\.|\.orders\(|kiteconnect", src, re.I)
    assert set(S.RUN) == {t["name"] for t in S.TOOLS + S.PAPER_TOOLS}


# ---------- paper orders ----------
def start_session(c, h=PRO) -> str:
    from tests import stress_requests
    r = c.post("/live/sessions", headers=h, json={"strategy": stress_requests.EMA, "instrument": "CRYPTO:BTC-USD"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def fresh(w, sid, price=30000.0):
    s = w["manager"].sessions[sid]
    s.last_price, s.last_tick_at = price, datetime.now(IST).isoformat()


def test_paper_order_open_and_close(w):
    c = w["client"]
    paper = make_key(c, paper=True)
    sid = start_session(c)
    fresh(w, sid)
    s = w["manager"].sessions[sid]
    cash = s.engine.cash
    r = result(call(c, paper, "place_paper_order", {"session_id": sid, "side": "buy", "quantity": 1.234567891234}))
    assert r["isError"] is False, r
    d = r["structuredContent"]
    assert d["simulated"] is True and d["order"]["side"] == "buy" and d["order"]["reason"] == live.MANUAL_WHY
    from app.engine.costs import floor_to
    assert s.engine.qty == floor_to(1.234567891234, s.engine.qty_step) < 1.234567891234         # rounded down to the step
    assert s.engine.cash < cash - s.engine.qty * 30000                                           # slippage and charges paid
    r = result(call(c, paper, "place_paper_order", {"session_id": sid, "side": "buy", "quantity": 1}))
    assert r["isError"] and "already has an open position" in r["content"][0]["text"]
    fresh(w, sid, 31000.0)
    r = result(call(c, paper, "close_paper_position", {"session_id": sid}))
    assert r["isError"] is False and r["structuredContent"]["order"]["side"] == "sell"
    assert r["structuredContent"]["order"]["pnl_after_charges"] > 0 and s.engine.qty == 0
    assert s.engine.trades[-1]["why"] == live.MANUAL_CLOSE_WHY
    r = result(call(c, paper, "close_paper_position", {"session_id": sid}))
    assert r["isError"] and "no open position" in r["content"][0]["text"]
    for _ in range(50):                                                          # orders are recorded in the background
        if len(w["db"].tables.get("live_orders", [])) < 2:
            time.sleep(0.05)
    orders = [o for o in w["db"].tables.get("live_orders", []) if o["session_id"] == sid]
    assert [o["side"] for o in orders][-2:] == ["buy", "sell"] or len(orders) == 0  # whole quantities only go to the table
    snap = result(call(c, paper, "get_paper_session", {"session_id": sid}))["structuredContent"]
    assert snap["account"]["trades"] == 1 and snap["orders"][0]["reason"] == live.MANUAL_CLOSE_WHY
    tools = [e["tool"] for e in c.get("/me/assistant", headers=PRO).json()["log"]]
    assert tools[:3] == ["get_paper_session", "close_paper_position", "close_paper_position"]


def test_paper_order_refusals(w):
    c = w["client"]
    paper = make_key(c, paper=True)
    sid = start_session(c)
    s = w["manager"].sessions[sid]
    s.last_tick_at = (datetime.now(IST) - timedelta(minutes=10)).isoformat()
    r = result(call(c, paper, "place_paper_order", {"session_id": sid, "side": "buy", "quantity": 1}))
    assert r["isError"] and "more than a few minutes old" in r["content"][0]["text"]
    fresh(w, sid)
    r = result(call(c, paper, "place_paper_order", {"session_id": sid, "side": "sell", "quantity": 1}))
    assert r["isError"] and "long only" in r["content"][0]["text"]               # the strategy doesn't short
    r = result(call(c, paper, "place_paper_order", {"session_id": sid, "side": "buy", "quantity": 1000}))
    assert r["isError"] and "in cash" in r["content"][0]["text"]
    r = result(call(c, paper, "place_paper_order", {"session_id": sid, "side": "buy", "quantity": 1e-12}))
    assert r["isError"] and "at least" in r["content"][0]["text"]
    assert s.engine.qty == 0
    c.post(f"/live/sessions/{sid}/stop", headers=PRO)
    r = result(call(c, paper, "place_paper_order", {"session_id": sid, "side": "buy", "quantity": 1}))
    assert r["isError"] and "no running paper session" in r["content"][0]["text"].lower()


def test_market_hours(w):
    sid = start_session(w["client"])
    s = w["manager"].sessions[sid]
    s.last_tick_at = datetime.now(IST).isoformat()
    assert s.price_problem() is None                                             # crypto: every day, all day
    s.market = "US"
    sunday = datetime(2026, 10, 4, 12, 0, tzinfo=IST)
    assert "closed" in s.price_problem(sunday)
    night = datetime(2026, 10, 5, 23, 0, tzinfo=IST).astimezone(IST)            # 13:30 in New York: open
    s.last_tick_at = night.isoformat()
    assert s.price_problem(night) is None
    assert "closed" in s.price_problem(datetime(2026, 10, 5, 12, 0, tzinfo=IST))   # 02:30 in New York


# ---------- limits ----------
def test_rate_limit(w, monkeypatch):
    c = w["client"]
    monkeypatch.setitem(S.LIMITS, "call", [(3, 60), (1000, 86400)])
    key = make_key(c)
    for _ in range(3):
        assert result(call(c, key, "get_alerts"))["isError"] is False
    r = result(call(c, key, "get_alerts"))
    assert r["isError"] and "Try again in" in r["content"][0]["text"]
    assert mcp_keys.entries("u-pro")[0]["result"] == "rate_limited"
    assert result(call(c, make_key(c), "get_alerts"))["isError"] is False        # per key


def test_limiter_windows():
    lim = S.Limiter()
    assert all(lim.wait("k", "get_watchlist_scan", now=1000 + i) == 0 for i in range(6))
    assert lim.wait("k", "get_watchlist_scan", now=1010) > 0                     # 6 scans an hour
    assert lim.wait("k", "get_alerts", now=1010) == 0                            # other tools still fine
    assert lim.wait("k", "get_watchlist_scan", now=1000 + 3601) == 0


def test_long_answers_are_cut():
    obj = {"rows": [{"n": i, "text": "x" * 100} for i in range(5000)], "total": 1}
    out, text = S.fit(obj, 20_000)
    assert len(text) <= 20_000 and out["truncated"] is True and out["total"] == 1 and 0 < len(out["rows"]) < 5000


def test_log_is_capped(w):
    _, key = mcp_keys.create("u-pro", "k", False)
    for i in range(mcp_keys.MAX_LOG + 5):
        mcp_keys.log("u-pro", key, "get_alerts", {"i": i}, "ok")
    items = mcp_keys.entries("u-pro")
    assert len(items) == mcp_keys.MAX_LOG and json.loads(items[0]["args"]) == {"i": mcp_keys.MAX_LOG + 4}


def test_reads_work(w):
    """Every read-only tool answers for a signed-in Pro user with data, with the facts line and no provider names."""
    c = w["client"]
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"region": "IN", "symbol": "TCS", "name": "TCS"}]}))
    key = make_key(c)
    start_session(c)
    for name, args in (("get_watchlist", {}), ("get_holdings_summary", {}), ("get_alerts", {}), ("list_paper_sessions", {}),
                       ("get_watchlist_scan", {"region": "IN"}), ("get_company_facts", {"region": "IN", "symbol": "TCS"})):
        r = result(call(c, key, name, args))
        text = r["content"][0]["text"]
        assert not PROVIDERS.search(text), (name, text[:300])
        if not r["isError"]:
            assert r["structuredContent"]["note"] == S.FACTS
