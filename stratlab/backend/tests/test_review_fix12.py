"""fix12: what fix11 left of LIVE10A / LIVE10B / CX2. Each test is built on what the reviewer saw."""
import json
import threading
import time

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app.intel import ai as A, company as C, routes as research_routes


# ---------- LIVE10A-010: "Reading the headlines…" for up to an hour during the session ----------
def _open_market(monkeypatch, store):
    q = {"price": 25375.55, "change_pct": 0.33, "prev_close": 25291.1, "at": "2026-11-17T07:58:00+00:00"}
    monkeypatch.setattr(research_routes, "_levels_now", lambda r, wait: ([C.index_level("S&P 500", q, "US")], None))
    monkeypatch.setattr(research_routes, "market_open", lambda r, now=None: True)
    monkeypatch.setattr(A, "get", lambda kind, key: store.get(repr((kind, key))))
    monkeypatch.setattr(A, "peek", lambda kind, key: repr((kind, key)) in store)

    def keep(kind, key, out, ttl, persist=True):
        store[repr((kind, key))] = json.loads(json.dumps(out))
        return out
    monkeypatch.setattr(A, "keep", keep)


def test_a_new_hours_first_visit_gets_the_sessions_latest_read_at_once_while_the_new_one_is_written(monkeypatch):
    store, calls = {}, []
    _open_market(monkeypatch, store)
    gate = threading.Event()

    def slow(profile, kind, key, ttl, refresh, build, **k):
        calls.append(key)
        gate.wait(5)                       # the AI writing the new hour's read, held up
        return {"tone": f"read {len(calls)}", "hot": [], "flows": [], "themes": [], "generated_at": 100.0 + len(calls)}
    monkeypatch.setattr(research_routes, "ai_call", slow)
    # the session's first read: waited for, and kept as the session's latest
    gate.set()
    first = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u1"}).body)
    assert first["tone"] == "read 1" and not first.get("updating")
    # the hour turns (a new key): the next visit is answered at once with the latest read, marked, and the new one is written behind it
    gate.clear()
    monkeypatch.setattr(research_routes, "mood_key", lambda indices, is_open: ("another hour",))
    t0 = time.time()
    second = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u2"}).body)
    assert time.time() - t0 < 1.0, "the visit waited for the AI"
    assert second["tone"] == "read 1" and second["updating"] is True
    # a third visit while it is being written starts no second write
    json.loads(research_routes.pulse_ai("US", "", False, {"id": "u3"}).body)
    gate.set()
    for _ in range(50):
        if not research_routes._pulse_running:
            break
        time.sleep(0.05)
    assert len(calls) == 2


def test_a_read_of_an_earlier_session_is_never_shown_as_this_sessions(monkeypatch):
    store, calls = {}, []
    _open_market(monkeypatch, store)
    store[repr(("pulse", ("US", "", research_routes.PULSE_LATEST)))] = {
        "tone": "yesterday", "hot": [], "flows": [], "themes": [], "generated_at": 1.0, "session": [["S&P 500", "2026-11-16"]]}

    def call(profile, kind, key, ttl, refresh, build, **k):
        calls.append(key)
        return {"tone": "today", "hot": [], "flows": [], "themes": [], "generated_at": 5.0}
    monkeypatch.setattr(research_routes, "ai_call", call)
    got = json.loads(research_routes.pulse_ai("US", "", False, {"id": "u1"}).body)
    assert got["tone"] == "today" and not got.get("updating") and calls
