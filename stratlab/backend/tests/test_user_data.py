"""Admin -> Users -> "Delete this user's data": one user's app data goes (drawings, Connect records, holdings, net worth,
notebooks, alerts, preferences), another user's stays, and only an admin can do it."""
import json

import pytest

from app import db, drawings_store, holdings, money_networth, user_data
from app import alerts, daily_report, lifecycle, stock_alerts
from app.connect import state
from tests import world

ADMIN = world.headers("admin-token")
PRO = world.headers("pro-token")
ME, OTHER = "u-pro", "u-basic"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def seed(uid: str):
    drawings_store.save(uid, "IN", "RELIANCE", drawings_store.Payload(
        drawings=[{"id": "d1", "kind": "trend", "points": [{"t": 1_700_000_000_000, "p": 100.0}, {"t": 1_710_000_000_000, "p": 120.0}]}]))
    state.update(uid, "kite", token="sealed-kite-token", kite_user="AB1234")
    state.update(uid, "ibkr", token="sealed-flex-token", query="123")
    state.update(uid, "inbox", local="abc123", pw="sealed-statement-password")
    db.set_setting(state.INDEX + "abc123", uid)
    holdings.save(uid, [{"symbol": "TCS", "qty": 3, "avg": 3000.0}], "Manual")
    money_networth.save(uid, [{"id": "n1", "name": "Savings", "kind": "cash", "value": 1000}])
    db.save_strategy(uid, "My idea", {"kind": "rules", "question": "q"}, None)
    db.set_setting(stock_alerts.KEY + uid, json.dumps({"uid": uid, "items": [{"id": "a1"}]}))
    db.set_setting(daily_report.PREFS + uid, json.dumps({"daily_report": False}))
    db.set_setting(lifecycle.PREFS + uid, json.dumps({"uid": uid, "tips": False}))
    db.set_setting(alerts.CONFIRMED + uid, "me@example.com")


def left(uid: str) -> dict:
    return {
        "drawings": drawings_store.load(uid, "IN", "RELIANCE")["drawings"],
        "connect": state.load(uid),
        "inbox_index": db.get_setting(state.INDEX + "abc123"),
        "holdings": holdings.load(uid)["items"],
        "networth": db.get_setting(money_networth.KEY + uid),
        "notebooks": db.list_notebook_rows(uid),
        "alerts": db.get_setting(stock_alerts.KEY + uid),
        "prefs": [db.get_setting(daily_report.PREFS + uid), db.get_setting(lifecycle.PREFS + uid), db.get_setting(alerts.CONFIRMED + uid)],
    }


def test_erase_removes_everything_of_one_user_and_nothing_of_another(w):
    seed(ME)
    got = user_data.erase(ME)
    assert got["failed"] == []
    gone = left(ME)
    assert gone["drawings"] == [] and gone["connect"] == {} and gone["holdings"] == [] and gone["networth"] is None
    assert gone["notebooks"] == [] and gone["alerts"] is None and gone["prefs"] == [None, None, None]
    assert gone["inbox_index"] is None                       # the forwarding address stops working
    counts = {r["key"]: r["count"] for r in got["done"]}
    assert counts["drawings"] == 1 and counts["holdings"] == 1 and counts["notebooks"] == 1 and counts["connect"] == 3


def test_erase_leaves_other_users_alone(w):
    seed(ME)
    db.set_setting(drawings_store.KEY + "other-keeps", "x")
    other = drawings_store.Payload(drawings=[{"id": "d9", "kind": "trend", "points": [{"t": 1_700_000_000_000, "p": 1.0}, {"t": 1_710_000_000_000, "p": 2.0}]}])
    drawings_store.save(OTHER, "IN", "RELIANCE", other)
    holdings.save(OTHER, [{"symbol": "INFY", "qty": 1, "avg": 1500.0}], "Manual")
    state.update(OTHER, "kite", token="sealed-other")
    user_data.erase(ME)
    assert len(drawings_store.load(OTHER, "IN", "RELIANCE")["drawings"]) == 1
    assert holdings.load(OTHER)["items"][0]["symbol"] == "INFY"
    assert state.section(OTHER, "kite")["token"] == "sealed-other"
    assert db.get_setting(drawings_store.KEY + "other-keeps") == "x"


def test_erase_can_run_twice_and_on_a_user_with_nothing(w):
    assert user_data.erase("u-nobody")["failed"] == []
    seed(ME)
    assert user_data.erase(ME)["failed"] == []
    assert user_data.erase(ME)["failed"] == []


def test_one_failing_store_does_not_stop_the_rest(w, monkeypatch):
    seed(ME)
    monkeypatch.setattr(holdings, "delete", lambda uid: (_ for _ in ()).throw(RuntimeError("down")))
    got = user_data.erase(ME)
    assert [f["key"] for f in got["failed"]] == ["holdings"]
    assert left(ME)["connect"] == {} and left(ME)["networth"] is None


def test_kite_logout_failing_still_removes_the_sealed_token(w, monkeypatch):
    seed(ME)
    from app.connect import kite_user
    monkeypatch.setattr(kite_user, "disconnect", lambda uid: (_ for _ in ()).throw(RuntimeError("broker down")))
    user_data.erase(ME)
    assert state.load(ME) == {}


def test_endpoint_is_admin_only(w):
    c = w["client"]
    seed(ME)
    assert c.post(f"/admin/users/{ME}/delete-data").status_code == 401
    assert c.post(f"/admin/users/{ME}/delete-data", headers=PRO).status_code == 403
    assert left(ME)["holdings"]                                # untouched


def test_endpoint_erases_and_reports(w):
    c = w["client"]
    seed(ME)
    r = c.post(f"/admin/users/{ME}/delete-data", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["email"] == "pro@example.com" and not body["failed"]
    assert {d["key"] for d in body["done"]} >= {"drawings", "connect", "holdings", "networth", "notebooks", "alerts", "prefs"}
    assert left(ME)["connect"] == {} and left(ME)["holdings"] == []
    # the sign-in account is not touched: the profile row is still there
    assert db.sb().table("profiles").select("id").eq("id", ME).execute().data


def test_endpoint_unknown_or_odd_ids(w):
    c = w["client"]
    assert c.post("/admin/users/u-nobody/delete-data", headers=ADMIN).status_code == 404
    assert c.post("/admin/users/a%20b%3B/delete-data", headers=ADMIN).status_code == 404
