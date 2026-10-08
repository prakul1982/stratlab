"""Round 5, the owner's review: database reconnects (R5O-002) and the other fixes in this round that are pure backend."""
import socket
import threading

import httpx
import pytest

from app import db


# ---------- R5O-002: the database connection drops ----------
class Flaky(httpx.BaseTransport):
    """Fails the first `fail` requests with `exc`, then answers 200."""

    def __init__(self, exc, fail=1):
        self.exc, self.fail, self.calls = exc, fail, []

    def handle_request(self, request):
        self.calls.append(request.method)
        if len(self.calls) <= self.fail:
            raise self.exc("Server disconnected without sending a response.", request=request)
        return httpx.Response(200, json=[{"id": 1}])


def test_a_read_is_tried_once_more_when_the_connection_drops():
    inner = Flaky(httpx.RemoteProtocolError)
    with httpx.Client(transport=db.RetryReads(inner)) as c:
        r = c.get("https://db.example/rest/v1/profiles")
    assert r.json() == [{"id": 1}] and inner.calls == ["GET", "GET"]


def test_a_read_fails_after_one_retry_not_forever():
    inner = Flaky(httpx.RemoteProtocolError, fail=5)
    with httpx.Client(transport=db.RetryReads(inner)) as c, pytest.raises(httpx.RemoteProtocolError):
        c.get("https://db.example/rest/v1/profiles")
    assert inner.calls == ["GET", "GET"]


def test_a_write_is_not_sent_twice_when_it_may_have_landed():
    inner = Flaky(httpx.RemoteProtocolError)
    with httpx.Client(transport=db.RetryReads(inner)) as c, pytest.raises(httpx.RemoteProtocolError):
        c.post("https://db.example/rest/v1/usage_events", json={"kind": "x"})
    assert inner.calls == ["POST"]


def test_a_write_that_never_left_is_sent_again():
    inner = Flaky(httpx.ConnectError)
    with httpx.Client(transport=db.RetryReads(inner)) as c:
        r = c.post("https://db.example/rest/v1/usage_events", json={"kind": "x"})
    assert r.status_code == 200 and inner.calls == ["POST", "POST"]


def test_the_database_client_uses_a_pool_of_http1_connections(monkeypatch):
    """HTTP/2 shared by every thread raised KeyError: 819 (a stream number) in count_usage and "Server disconnected"
    for every request in flight; the client is HTTP/1.1 with the retrying transport."""
    monkeypatch.setattr(db, "_client", None)
    monkeypatch.setattr(db.settings, "SUPABASE_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(db.settings, "SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
    c = db.sb()
    try:
        session = c.postgrest.session
        assert isinstance(session._transport, db.RetryReads)
        pool = session._transport.inner._pool
        assert pool._http2 is False and pool._http1 is True
    finally:
        monkeypatch.setattr(db, "_client", None)


def _server(replies):
    """A one-thread HTTP server on localhost: the first connection is closed without an answer, the rest answer."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(8)
    seen = []

    def run():
        while True:
            try:
                conn, _ = s.accept()
            except OSError:
                return
            with conn:
                data = conn.recv(65536)
                if not data:
                    continue
                seen.append(data.split(b"\r\n", 1)[0].decode())
                if len(seen) <= replies.get("drop", 0):
                    continue            # close without a word: "Server disconnected without sending a response"
                body = b'[{"id": 7}]'
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Range: 0-0/3\r\n"
                             b"Connection: close\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)
    threading.Thread(target=run, daemon=True).start()
    return s, seen


def test_a_real_count_survives_a_dropped_connection(monkeypatch):
    srv, seen = _server({"drop": 1})
    try:
        monkeypatch.setattr(db, "_client", None)
        monkeypatch.setattr(db, "RETRY_PAUSE", 0.0)
        monkeypatch.setattr(db.settings, "SUPABASE_URL", f"http://127.0.0.1:{srv.getsockname()[1]}")
        monkeypatch.setattr(db.settings, "SUPABASE_SERVICE_KEY", "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.x")
        assert db.count_usage("u1", "backtest", "2026-10-01T00:00:00+00:00") == 3
        assert len(seen) == 2 and all(x.startswith("GET /rest/v1/usage_events") for x in seen)
    finally:
        srv.close()
        monkeypatch.setattr(db, "_client", None)


def test_admin_sessions_lists_an_options_session_with_its_market():
    """'OptionSession' object has no attribute 'market' (25 Sep): the session carries its market now."""
    from app.options.session import OptionSession
    src = OptionSession.__init__.__code__.co_names
    assert "market" in src


# ---------- R5O-008: the theme map's tickers ----------
LISTED_IN = [{"symbol": "BHARTIARTL", "name": "BHARTI AIRTEL"}, {"symbol": "BHEL", "name": "BHARAT HEAVY ELECTRICALS"},
             {"symbol": "BEL", "name": "BHARAT ELECTRONICS"}, {"symbol": "MAZDOCK", "name": "MAZAGON DOCK SHIPBUILDERS"},
             {"symbol": "HAL", "name": "HINDUSTAN AERONAUTICS"}, {"symbol": "TATAELXSI", "name": "TATA ELXSI"},
             {"symbol": "MODEFENCE", "name": "MOTILAL OSWAL NIFTY INDIA DEFENCE ETF"},
             {"symbol": "SOLARINDS", "name": "SOLAR INDUSTRIES (I) LTD"}]


def fake_lookup(q, region):
    """A stand-in for the market's list: the exact symbol, else names with the first two words typed."""
    from app.intel.grounding import _words, _same_word
    exact = [r for r in LISTED_IN if r["symbol"] == q.upper()]
    if exact:
        return exact
    want = _words(q)
    return [r for r in LISTED_IN if want and all(any(_same_word(w, x) for x in _words(r["name"])) for w in want[:2])]


def test_names_agree():
    from app.intel.grounding import names_agree
    assert names_agree("Bharat Heavy Electricals Ltd", "BHARAT HEAVY ELECTRICALS")
    assert names_agree("Solar Industries India", "SOLAR INDUSTRIES (I) LTD")
    assert names_agree("Tata Consultancy Services", "TATA CONSULTANCY SERV LT")
    assert names_agree("Vertiv", "Vertiv Holdings Co")
    assert not names_agree("Bharat Heavy Electricals Ltd", "BHARTI AIRTEL")
    assert not names_agree("Bharat Heavy Electricals", "BHARAT ELECTRONICS")
    assert not names_agree("Tata Advanced Systems", "TATA ELXSI")
    assert not names_agree("Hindustan Aeronautics", "HINDUSTAN UNILEVER")


def test_theme_tickers_are_checked_against_the_list():
    from app.intel.grounding import ground_sector
    ai = {"screen": [{"name": "Bharat Heavy Electricals Ltd", "ticker": "BHARTIARTL", "layer": "OEM"},
                     {"name": "Mazagon Dock Shipbuilders", "ticker": "MDSL", "layer": "Shipyards"},
                     {"name": "Tata Advanced Systems", "ticker": "TATASYS", "layer": "Private OEM"},
                     {"name": "Hindustan Aeronautics", "ticker": "HAL", "layer": "Aircraft"}],
          "clusters": [{"name": "State-owned OEMs", "companies": [
              {"name": "Bharat Heavy Electricals Ltd", "ticker": "BHARTIARTL"}, {"name": "Tata Advanced Systems", "ticker": "TATASYS"},
              {"name": "Antrix", "ticker": ""}, {"name": "Bharat Electronics", "ticker": "BEL"}]}],
          "value_chain": [{"layer": "Ships", "companies": [{"name": "Mazagon Dock", "ticker": "MDSL"}]}],
          "etfs": [{"ticker": "NIFTYDEF", "name": "Nifty India Defence ETF"}, {"ticker": "INDDEF", "name": "India Defence Fund"},
                   {"ticker": "MODEFENCE", "name": "Motilal Oswal Nifty India Defence ETF"}]}
    out = ground_sector(ai, "IN", fake_lookup)
    assert [(s["ticker"], s["name"]) for s in out["screen"]] == [
        ("BHEL", "Bharat Heavy Electricals Ltd"), ("MAZDOCK", "Mazagon Dock Shipbuilders"), ("HAL", "Hindustan Aeronautics")]
    cos = out["clusters"][0]["companies"]
    assert [(c["name"], c["ticker"], c["listed"]) for c in cos] == [
        ("Bharat Heavy Electricals Ltd", "BHEL", True), ("Tata Advanced Systems", "", False), ("Antrix", "", False),
        ("Bharat Electronics", "BEL", True)]
    assert out["value_chain"][0]["companies"][0]["ticker"] == "MAZDOCK"
    assert out["etfs"] == [{"ticker": "MODEFENCE", "name": "MOTILAL OSWAL NIFTY INDIA DEFENCE ETF"}]


def test_a_theme_map_is_grounded_before_it_is_cached():
    """The route runs the check on what the AI wrote, so a cached map never carries an unchecked ticker."""
    from app.intel import routes
    src = open(routes.__file__).read()
    assert "grounding.ground_sector(A.sector(theme, r, _ai), r, hub.search)" in src


def test_when_the_list_is_down_nothing_passes_as_checked():
    from app.intel.grounding import ground_sector

    def down(q, region):
        raise RuntimeError("list down")
    out = ground_sector({"screen": [{"name": "Hindustan Aeronautics", "ticker": "HAL"}], "etfs": [{"ticker": "X", "name": "Y"}]},
                        "IN", down)
    assert out["screen"] == [] and out["etfs"] == []


# ---------- R5O-014: the library's cards beside buy and hold ----------
def test_library_entries_carry_their_return_beside_buy_and_hold():
    from app import library
    e = {"stats": {"ret": 55.8, "buy_hold": 172.9, "trades": 40}, "verdict": {"verdict": "edge", "checks": []}}
    assert library.public(e)["vs_hold"] == {"ret": 55.8, "hold": 172.9, "gap": -117.1}
    assert library.public({**e, "stats": {**e["stats"], "trades": 0}})["vs_hold"] is None       # never traded: nothing to compare
    assert library.public({**e, "stats": {"ret": 5.0, "buy_hold": None, "trades": 20}})["vs_hold"] is None


# ---------- R5O-010: notebook defaults ----------
@pytest.fixture
def w(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_the_questions_about_an_idea_stay_with_the_notebook(w):
    c, h = w["client"], w["headers"]("pro-token")
    gaps = {"mentioned": ["sl"], "notes": [], "instName": None, "usedAI": True, "fallback": ""}
    strat = {"name": "EMA", "entry": [{"l": {"t": "ema", "p": 20}, "op": "xa", "r": {"t": "ema", "p": 50}}], "risk": {"sl": 2, "tgt": 0}}
    nb = c.post("/notebooks", headers=h, json={"name": "EMA", "strategy": strat, "gaps": gaps}).json()
    assert c.get(f"/notebooks/{nb['id']}", headers=h).json()["gaps"]["mentioned"] == ["sl"]
    # an answer is kept: the person leaves and comes back to the same place
    r = c.put(f"/notebooks/{nb['id']}", headers=h, json={"gaps": {**gaps, "answered": {"exit": "Sell when EMA 20 drops below EMA 50"}}})
    assert r.status_code == 200
    back = c.get(f"/notebooks/{nb['id']}", headers=h).json()
    assert back["gaps"]["answered"] == {"exit": "Sell when EMA 20 drops below EMA 50"}
    assert back["strategy"]["risk"]["tgt"] == 0          # no target was asked for, none is stored
    # an unrelated save keeps them; "Close" clears them
    c.put(f"/notebooks/{nb['id']}", headers=h, json={"notes": "x"})
    assert c.get(f"/notebooks/{nb['id']}", headers=h).json()["gaps"]["mentioned"] == ["sl"]
    c.put(f"/notebooks/{nb['id']}", headers=h, json={"clearGaps": True})
    assert not c.get(f"/notebooks/{nb['id']}", headers=h).json().get("gaps")


def test_gaps_are_bounded(w):
    c, h = w["client"], w["headers"]("pro-token")
    nb = c.post("/notebooks", headers=h, json={"name": "X"}).json()
    r = c.put(f"/notebooks/{nb['id']}", headers=h, json={"gaps": {"mentioned": ["x" * 50]}})
    assert r.status_code == 422


def test_the_ai_builders_internal_notes_are_not_shown():
    from app.ai_writer import user_note
    assert not user_note("No timeframe specified, left as null.")
    assert not user_note("Timeframe not specified; defaulted to daily.")
    assert not user_note("No stop loss was given.")
    assert not user_note("The user did not mention an exit.")
    assert user_note("Option legs can't be tested here, so the straddle part was left out.")
    assert user_note("Advanced indicators need the Basic plan, so MACD was left out.")
    assert user_note("The volume filter you mentioned isn't available, so it was skipped.")


def test_write_strategy_drops_internal_notes(monkeypatch):
    import json as _json
    from app import ai_writer
    reply = {"entry": [{"l": {"t": "ema", "p": 20}, "op": "xa", "r": {"t": "ema", "p": 50}}], "exit": [], "tf": None,
             "risk": {"sl": 2}, "mentioned": ["sl"],
             "notes": ["No timeframe specified, left as null.", "Short selling on delivery isn't possible, so only longs are tested."]}
    monkeypatch.setattr(ai_writer, "complete", lambda *a, **k: _json.dumps(reply))
    out = ai_writer.write_strategy("Buy when EMA 20 crosses above EMA 50, stop loss 2%", False)
    assert out["notes"] == ["Short selling on delivery isn't possible, so only longs are tested."]
    assert "tgt" not in out.get("risk", {})
    assert "Never invent exits, stops or targets" in ai_writer.SYSTEM
