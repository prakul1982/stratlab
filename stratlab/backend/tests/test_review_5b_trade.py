"""Review 5b, the backend side of the Trade space fixes: a test signal from the page carries its own id (a double click
is a repeat, never a second fill), the signal session list says each session's market and zone, a stopped options
session's "today" is None once its saved day has gone, and an uploaded CSV keeps the currency picked for it."""
import math
from datetime import datetime

import pytest

from app import main
from app.options.session import IST, stopped_snapshot
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)
from tests.test_signals import PRO, session, w  # noqa: F401  (fixture)


# ---------- signal sessions ----------
def test_a_test_signal_sent_twice_with_its_id_fills_once(w):
    c = w["client"]
    s = session(c)
    body = {"action": "buy", "qty": 0.1, "id": "page-abc-123"}
    first = c.post(f"/trade/signals/sessions/{s['id']}/test", headers=PRO, json=body)
    again = c.post(f"/trade/signals/sessions/{s['id']}/test", headers=PRO, json=body)
    assert first.status_code == 200 and first.json()["status"] == "filled"
    assert again.status_code == 200 and again.json()["status"] == "duplicate"
    snap = c.get(f"/trade/signals/sessions/{s['id']}", headers=PRO).json()
    assert snap["account"]["qty"] == pytest.approx(0.1)                       # one fill, not two
    assert [x["status"] for x in snap["signals"]] == ["filled", "duplicate"]
    assert snap["signals"][0]["id"] == "page-abc-123"
    # without an id each send is its own signal, as before
    assert c.post(f"/trade/signals/sessions/{s['id']}/test", headers=PRO, json={"action": "buy", "qty": 0.1}).json()["status"] == "filled"
    # an id outside the alert format is refused like any bad field
    assert c.post(f"/trade/signals/sessions/{s['id']}/test", headers=PRO, json={**body, "id": "no spaces!"}).status_code == 422


def test_the_signal_session_list_says_each_sessions_market_and_zone(w):
    c = w["client"]
    s = session(c)
    row = next(r for r in c.get("/trade/signals", headers=PRO).json()["sessions"] if r["id"] == s["id"])
    assert row["market"] == "CRYPTO" and "tz" in row


def test_a_paused_signal_session_is_stopped_then_deleted(w, monkeypatch):
    c = w["client"]
    s = session(c)
    monkeypatch.setattr(main.manager, "sessions", {})                         # saved as running, attached nowhere
    assert next(r for r in c.get("/trade/signals", headers=PRO).json()["sessions"] if r["id"] == s["id"])["status"] == "paused"
    assert c.delete(f"/live/sessions/{s['id']}", headers=PRO).status_code == 409
    assert c.post(f"/live/sessions/{s['id']}/stop", headers=PRO).status_code == 200
    assert c.delete(f"/live/sessions/{s['id']}", headers=PRO).status_code == 200


# ---------- a stopped options session's day ----------
def _row(day: str | None, day_realised: float) -> dict:
    strategy = {"underlying": "NIFTY", "legs": [{"side": "sell", "opt": "CE", "offset": 2, "lots": 1}]}
    return {"id": "s1", "name": "Straddle", "status": "stopped", "stop_reason": "Stopped by you.", "instrument": {"type": "OPTIONS"},
            "strategy": strategy, "started_at": "2026-10-12T03:50:00+00:00", "stopped_at": "2026-10-12T09:00:00+00:00",
            "state": {"cash": 500000, "day": day, "day_realised": day_realised, "trades": [], "events": []}}


def test_a_stopped_options_sessions_old_day_is_not_today():
    now = datetime(2026, 10, 15, 11, 0, tzinfo=IST)
    old = stopped_snapshot(_row("2026-10-12", -1800.0), now)
    assert old["account"]["today"] is None                                   # an earlier day's P&L isn't today's
    same = stopped_snapshot(_row("2026-10-15", -1800.0), now)
    assert same["account"]["today"] == -1800.0                               # stopped today: today's figure stands
    assert stopped_snapshot(_row(None, 0.0), now)["account"]["today"] is None  # never traded


# ---------- an uploaded CSV's currency ----------
def test_an_uploaded_csv_keeps_the_currency_picked_for_it(api):
    nb = api.post("/notebooks", json={"name": "My data", "strategy": EMA}).json()
    put = api.put(f"/notebooks/{nb['id']}", json={"instrument": "CSV:Gold futures", "currency": "USD"})
    assert put.status_code == 200, put.text
    inst = api.get(f"/notebooks/{nb['id']}").json()["instrument"]
    assert inst["market"] == "CSV" and inst["symbol"] == "Gold futures" and inst["currency"] == "USD"
    made = api.post("/notebooks", json={"name": "Euro data", "strategy": EMA, "instrument": "CSV:Bund", "currency": "eur"}).json()
    assert made["instrument"]["currency"] == "EUR"
    assert api.put(f"/notebooks/{nb['id']}", json={"instrument": "CSV:x", "currency": "US$"}).status_code == 422


def test_an_upload_saved_without_its_currency_takes_it_from_the_run(api):
    nb = api.post("/notebooks", json={"name": "My data", "strategy": EMA, "instrument": "CSV:Gold futures"}).json()
    assert nb["instrument"]["currency"] == ""                                # an older client sent none
    bars = [{"t": f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": 100, "h": 101 + (i % 7), "l": 99,
             "c": 100 + 8 * math.sin(i / 6), "v": 0} for i in range(300)]
    r = api.post(f"/notebooks/{nb['id']}/experiments", json={"bars": bars, "upload": {"name": "Gold futures", "currency": "USD", "step": 0.01}})
    assert r.status_code == 200, r.text
    assert api.get(f"/notebooks/{nb['id']}").json()["instrument"]["currency"] == "USD"
