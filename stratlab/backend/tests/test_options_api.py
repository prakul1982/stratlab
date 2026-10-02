"""The Options tab's API on a fake option feed: underlyings, chain, preview, sessions and import."""
import uuid
from datetime import datetime

from fastapi.testclient import TestClient

from app import ai_writer, db, main
from app.main import app
from app.options.data import OptionsData
from app.options.session import IST

from .fake_options_kite import FakeOptionsKite

STRAT = {"name": "Short straddle", "structure": "short_straddle", "exchange": "NFO", "underlying": "NIFTY",
         "legs": [{"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0}],
         "timing": {"entry": "00:00", "lastEntry": "23:58", "squareoff": "23:59"}}



def midday() -> datetime:
    """The session's clock for these tests: noon today, inside the entry window whatever time CI runs at."""
    return datetime.now(IST).replace(hour=12, minute=0, second=0, microsecond=0)

def setup(monkeypatch, live=True):
    data = OptionsData(FakeOptionsKite(live=live, drift={}, clock=midday))
    monkeypatch.setattr(main, "options_data", data)
    monkeypatch.setattr(main.manager, "options", data)
    rows = {}

    def create(row):
        row = {**row, "id": str(uuid.uuid4()), "started_at": datetime.now(IST).isoformat(), "state": None}
        rows[row["id"]] = row
        return row
    monkeypatch.setattr(db, "create_session", create)
    monkeypatch.setattr(db, "update_session", lambda sid, **f: rows[sid].update(f))
    monkeypatch.setattr(db, "get_session_row", lambda uid, sid: rows.get(sid))
    monkeypatch.setattr(db, "update_profile", lambda *a, **k: None)
    monkeypatch.setattr(db, "add_usage", lambda *a, **k: None)
    monkeypatch.setattr(db, "add_order", lambda *a, **k: None)
    monkeypatch.setattr(db, "get_profile", lambda uid: {"id": uid, "plan": "pro"})
    monkeypatch.setattr(main, "ai_allowance", lambda p: (0, 50))
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "pro", "plan": "pro"}
    return data, rows


def test_underlyings_chain_and_preview(monkeypatch):
    setup(monkeypatch)
    try:
        c = TestClient(app)
        us = c.get("/options/underlyings").json()
        assert [u["name"] for u in us[:3]] == ["NIFTY", "BANKNIFTY", "SENSEX"] and us[0]["freeze"] == 1800
        assert {u["venue"] for u in us} == {"NSE", "BSE", "MCX"}
        ch = c.get("/options/chain", params={"exchange": "NFO", "underlying": "NIFTY"}).json()
        assert ch["spot"] == 25000 and ch["atm"] == 25000 and ch["step"] == 50 and len(ch["rows"]) == 21
        row = next(r for r in ch["rows"] if r["strike"] == 25000)
        assert row["ce"]["bid"] < row["ce"]["ask"]
        assert c.get("/options/chain", params={"exchange": "XYZ", "underlying": "NIFTY"}).status_code == 400
        pv = c.post("/options/preview", json={"strategy": {**STRAT, "sizing": {"mode": "margin", "capital": 5000000}}}).json()
        assert [l["strike"] for l in pv["legs"]] == [25000, 25000] and all(l["fill"] == l["quote"]["bid"] for l in pv["legs"])
        assert pv["margin_one"] == 150 * 4000 and pv["units"] == int(5000000 * 0.98 // 600000)
        mcx = c.get("/options/chain", params={"exchange": "MCX", "underlying": "CRUDEOIL"}).json()
        assert mcx["spot"] == 5600
    finally:
        app.dependency_overrides.clear()


def test_session_trades_on_live_quotes_and_survives_a_restart(monkeypatch):
    data, rows = setup(monkeypatch)
    try:
        c = TestClient(app)
        snap = c.post("/options/sessions", json={"strategy": STRAT}).json()
        sid = snap["id"]
        s = main.manager.sessions[sid]
        s.on_timer(midday())
        snap = c.get(f"/live/sessions/{sid}").json()
        assert snap["kind"] == "options" and snap["fresh"] and len(snap["legs"]) == 2
        assert snap["position"]["credit"] > 0 and len(snap["orders"]) == 2
        # a restart rebuilds the session from its saved state
        main.manager.persist(only_dirty=False)
        main.manager.sessions.pop(sid)
        main.manager._attach(rows[sid])
        assert main.manager.sessions[sid].engine.pos["legs"][0]["qty"] == 75
        c.post(f"/live/sessions/{sid}/stop")
        snap = c.get(f"/live/sessions/{sid}").json()
        assert snap["status"] == "stopped" and snap["kind"] == "options" and snap["legs"]
    finally:
        main.manager.sessions.clear()
        app.dependency_overrides.clear()


def test_no_entry_on_old_quotes(monkeypatch):
    setup(monkeypatch, live=False)
    try:
        c = TestClient(app)
        sid = c.post("/options/sessions", json={"strategy": STRAT}).json()["id"]
        main.manager.sessions[sid].on_timer(midday())
        snap = c.get(f"/live/sessions/{sid}").json()
        assert snap["position"] is None and not snap["fresh"] and "live prices" in snap["note"]
    finally:
        main.manager.sessions.clear()
        app.dependency_overrides.clear()


def test_import_routes_option_structures(monkeypatch):
    setup(monkeypatch)
    answer = {"name": "NIFTY iron fly", "structure": "iron_fly", "exchange": "NFO", "underlying": "NIFTY",
              "offsetUnit": "points", "legs": [{"side": "sell", "opt": "CE", "offset": 0}, {"side": "sell", "opt": "PE", "offset": 0},
                                              {"side": "buy", "opt": "CE", "offset": 800}, {"side": "buy", "opt": "PE", "offset": 800}],
              "risk": {"stopType": "amount", "stop": 50000, "dailyLoss": 100000},
              "recenter": {"enabled": True, "every": 30, "threshold": 2, "roll": "shorts"},
              "notes": ["Order mechanics (SL-limit) are replaced by fills at the live bid and ask."]}
    monkeypatch.setattr(ai_writer, "ask_json", lambda system, text, max_tokens=2500: dict(answer))
    try:
        c = TestClient(app)
        cfg = '{"structure": {"type": "short_straddle_with_wings", "short_legs": ["ATM CE (SELL)", "ATM PE (SELL)"], "hedge_legs": []}}'
        r = c.post("/import/strategy", json={"text": cfg}).json()
        assert r["kind"] == "options" and r["strategy"]["structure"] == "iron_fly" and r["strategy"]["recenter"]["enabled"]
        assert r["notes"] and r["used_ai"]
        exact = '{"stratlab": "options", "strategy": %s}' % __import__("json").dumps(STRAT)
        r = c.post("/options/import", json={"text": exact}).json()
        assert r["strategy"]["underlying"] == "NIFTY" and not r["used_ai"]
    finally:
        app.dependency_overrides.clear()


def test_admin_lists_options_sessions(monkeypatch):
    from app import admin
    setup(monkeypatch)
    app.dependency_overrides[admin.admin_profile] = lambda: {"id": "u", "is_admin": True}
    try:
        c = TestClient(app)
        sid = c.post("/options/sessions", json={"strategy": STRAT}).json()["id"]
        rows = c.get("/admin/sessions").json()
        row = next(r for r in rows if r["id"] == sid)
        assert row["market"] == "IN" and row["kind"] == "options" and row["capital"] == 500000
    finally:
        main.manager.sessions.clear()
        app.dependency_overrides.clear()
