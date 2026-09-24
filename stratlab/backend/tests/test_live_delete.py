"""Deleting old paper-trading sessions: stopped ones go, running ones are protected."""
import uuid

from fastapi.testclient import TestClient

from app import db, main
from app.main import app


def test_delete_stopped_sessions(monkeypatch):
    stopped, running, other = (str(uuid.uuid4()) for _ in range(3))
    rows = {stopped: {"id": stopped, "user_id": "u", "status": "stopped"},
            running: {"id": running, "user_id": "u", "status": "running"},
            other: {"id": other, "user_id": "someone-else", "status": "stopped"}}
    monkeypatch.setattr(db, "get_session_row", lambda uid, sid: rows.get(sid) if rows.get(sid, {}).get("user_id") == uid else None)
    monkeypatch.setattr(db, "delete_session", lambda uid, sid: rows.pop(sid))

    def clear(uid):
        gone = [k for k, r in rows.items() if r["user_id"] == uid and r["status"] != "running"]
        for k in gone:
            rows.pop(k)
        return len(gone)
    monkeypatch.setattr(db, "delete_stopped_sessions", clear)
    app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "_plan": "free"}
    try:
        c = TestClient(app)
        r = c.delete(f"/live/sessions/{running}")
        assert r.status_code == 409 and "Stop" in r.json()["detail"]["message"]
        assert c.delete(f"/live/sessions/{other}").status_code == 404        # not yours
        assert c.delete(f"/live/sessions/{stopped}").json() == {"deleted": True} and stopped not in rows
        rows[stopped] = {"id": stopped, "user_id": "u", "status": "stopped"}
        assert c.delete("/live/sessions").json() == {"deleted": 1}
        assert set(rows) == {running, other}
    finally:
        app.dependency_overrides.clear()
