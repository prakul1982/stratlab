"""Admin -> Users -> "Delete this user's data": one user's app data goes (drawings, Connect records, holdings, net worth,
notebooks, alerts, preferences), another user's stays, and only an admin can do it."""
import json
import threading
import types

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
    assert gone["notebooks"] == [] and gone["alerts"] is None and gone["prefs"][0] is None and gone["prefs"][2] is None
    assert lifecycle.tips_on(ME) is False                    # a "no tips" choice outlives the erase (the account stays)
    assert gone["inbox_index"] is None                       # the forwarding address stops working
    counts = {r["key"]: r["count"] for r in got["done"]}
    assert counts["drawings"] == 1 and counts["holdings"] == 1 and counts["notebooks"] == 1 and counts["connect"] == 3


def test_erase_does_not_turn_tips_back_on(w):
    seed(ME)
    user_data.erase(ME)
    assert db.json_value(db.get_setting(lifecycle.PREFS + ME), {}) == {"uid": ME, "tips": False}
    db.set_setting(lifecycle.PREFS + OTHER, json.dumps({"uid": OTHER, "tips": True}))
    user_data.erase(OTHER)
    assert db.get_setting(lifecycle.PREFS + OTHER) is None


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


def test_erase_takes_down_share_links_and_library_entries(w):
    from app import library
    db.save_strategy(ME, "Shared", {"kind": "notebook", "experiments": [{"v": 1, "public": "tok-share-1", "library": "lib-entry-1"}]}, None)
    db.set_setting("share:tok-share-1", "{}")
    db.set_setting("shareimg:tok-share-1", "png")
    library.save({"id": "lib-entry-1", "owner": ME, "name": "n"})
    library.save({"id": "lib-orphan-1", "owner": ME, "name": "its experiment was dropped"})
    library.save({"id": "lib-theirs-1", "owner": OTHER, "name": "someone else's"})
    assert user_data.erase(ME)["failed"] == []
    assert db.get_setting("share:tok-share-1") is None and db.get_setting("shareimg:tok-share-1") is None
    assert library.load("lib-entry-1") is None and library.load("lib-orphan-1") is None
    assert library.load("lib-theirs-1") is not None


# ---------- every per-user store (newsletters, screens, reminders, MCP, invites, sessions, profile alert fields) ----------
def seed_more(uid: str):
    from app import company_cards, invite_rewards, market_events, mcp_keys, newsletter_prefs, plans, screens
    from app.connect import kite_user
    db.set_setting(newsletter_prefs.PREFIX + uid, json.dumps({"uid": uid}))
    db.set_setting(screens.KEY + uid, json.dumps({"uid": uid, "items": [{"id": "s"}]}))
    db.set_setting(market_events.USER_KEY + uid, json.dumps({"remind": True}))
    db.set_setting(alerts.ALERT_OFF + uid, "1")
    db.set_setting(lifecycle.SEEN + uid, "2026-10-01")
    db.set_setting("watchlist:" + uid, json.dumps({"items": [{"symbol": "TCS"}]}))
    token, _ = mcp_keys.create(uid, "Claude", True)
    mcp_keys.log(uid, mcp_keys.resolve(token)[1], "quote", {}, "ok")
    db.set_setting(mcp_keys.KEY_INDEX + "stale-" + uid, json.dumps({"uid": uid, "id": "gone"}))
    db.set_setting(f"ref:user:{uid}", "CODE-" + uid)
    db.set_setting(f"ref:code:CODE-{uid}", uid)
    db.set_setting(f"ref:by:{uid}", json.dumps({"by": "u-someone", "at": "2026-09-01T00:00:00+00:00"}))
    db.set_setting(f"ref:joined:{uid}", json.dumps([{"id": "u-friend", "at": "2026-09-02T00:00:00+00:00"}]))
    db.set_setting(invite_rewards.DAYS + uid, json.dumps(["2026-09-02"]))
    db.set_setting(invite_rewards.ROW + uid, json.dumps({"by": "u-someone", "status": "given"}))
    db.set_setting(plans.FREE_KEY + uid, json.dumps({"until": None, "banked": 30}))
    db.set_setting(f"cards:user:{uid}", json.dumps([{"t": "cardTok" + uid[-3:], "k": f"cardtok:{uid}:IN:TCS"}]))
    db.set_setting(f"cardtok:{uid}:IN:TCS", "cardTok" + uid[-3:])
    db.set_setting(f"card:cardTok{uid[-3:]}", "{}")
    assert company_cards.TOKEN.match("cardTok" + uid[-3:])
    db.set_setting(kite_user.PENDING + "p-" + uid, json.dumps({"uid": uid, "at": 0}))
    s = db.create_session({"user_id": uid, "name": "paper", "status": "stopped"})
    db.add_order({"session_id": s["id"], "user_id": uid, "side": "buy", "qty": 1, "price": 1.0})
    db.add_usage(uid, "backtest")
    db.sb().table("invoices").insert({"user_id": uid, "number": "INV-1"}).execute()
    db.update_profile(uid, telegram_chat_id="12345", alert_email="a@b.com", alerts_enabled=True)
    return token


def more_keys(uid: str) -> list[str]:
    from app import invite_rewards, market_events, mcp_keys, newsletter_prefs, plans, screens
    from app.connect import kite_user
    return [newsletter_prefs.PREFIX + uid, screens.KEY + uid, market_events.USER_KEY + uid, alerts.ALERT_OFF + uid,
            lifecycle.SEEN + uid, "watchlist:" + uid, mcp_keys.KEY_USER + uid, mcp_keys.KEY_LOG + uid,
            mcp_keys.KEY_INDEX + "stale-" + uid, f"ref:user:{uid}", f"ref:code:CODE-{uid}", f"ref:by:{uid}",
            f"ref:joined:{uid}", invite_rewards.DAYS + uid, plans.FREE_KEY + uid, f"cards:user:{uid}",
            f"cardtok:{uid}:IN:TCS", f"card:cardTok{uid[-3:]}", kite_user.PENDING + "p-" + uid]


def test_erase_reaches_every_per_user_store(w):
    from app import invite_rewards, mcp_keys
    seed(ME), seed(OTHER)
    mine, theirs = seed_more(ME), seed_more(OTHER)
    from app import main
    sid = db.create_session({"user_id": ME, "name": "running"})["id"]
    main.manager.sessions[sid] = types.SimpleNamespace(id=sid, user_id=ME, lock=threading.Lock(), state=lambda: {},
                                                    detach=lambda hub: None)
    got = user_data.erase(ME)
    assert got["failed"] == [] and "usage counts" in got["kept"]
    assert sid not in main.manager.sessions                                  # stopped in the live manager first
    assert [k for k in more_keys(ME) if db.get_setting(k) is not None] == []
    assert mcp_keys.resolve(mine) is None                                 # the key stops working
    gone = left(ME)
    assert gone["connect"] == {} and gone["holdings"] == [] and gone["prefs"][0] is None and gone["prefs"][2] is None
    assert lifecycle.tips_on(ME) is False                    # only a "no tips" choice stays (the account stays)
    rows = lambda t: [r for r in db.sb().table(t).select("*").eq("user_id", ME).execute().data]  # noqa: E731
    assert rows("live_sessions") == [] and rows("live_orders") == []
    p = db.get_profile(ME)
    assert (p["telegram_chat_id"], p["alert_email"], p["alerts_enabled"]) == (None, None, False)
    # kept: usage counts, invoices, and the reward row the inviter's caps count
    assert rows("usage_events") and rows("invoices") and db.get_setting(invite_rewards.ROW + ME)
    # the other user's data is untouched
    assert [k for k in more_keys(OTHER) if db.get_setting(k) is None] == []
    assert mcp_keys.resolve(theirs) is not None
    assert left(OTHER)["holdings"] and db.get_profile(OTHER)["telegram_chat_id"] == "12345"
    assert db.sb().table("live_sessions").select("id").eq("user_id", OTHER).execute().data


def test_export_has_sessions_assistant_referrals_usage_and_no_secrets(w):
    token = seed_more(ME)
    out = user_data.export(db.get_profile(ME))
    assert out["not_included"] == []
    assert len(out["sessions"]["sessions"]) == 1 and len(out["sessions"]["orders"]) == 1
    assert out["ai_assistant"]["assistant_keys"][0]["name"] == "Claude" and len(out["ai_assistant"]["calls"]) == 1
    assert out["referrals"]["code"] == "CODE-" + ME and out["referrals"]["invited_by"] == "u-someone"
    assert out["usage"] == {"backtest": 1}
    assert out["watchlist"]["watchlist"]["items"][0]["symbol"] == "TCS"
    assert out["preferences"]["newsletters"] == {"uid": ME}
    assert {"screens:user", "mktevents:user"} <= set(out["alerts"])
    assert out["free_basic"]["freebasic"]["banked"] == 30
    text = json.dumps(out)
    from app import mcp_keys
    assert token not in text and mcp_keys.digest(token) not in text


def test_notebooks_are_read_past_the_servers_row_cap(w, monkeypatch):
    from tests import fake_db
    real = fake_db.Query.execute

    def capped(self):                                     # the server returns at most 1000 rows a read
        r = real(self)
        if self.op == "select" and isinstance(r.data, list):
            r.data = r.data[:1000]
        return r
    monkeypatch.setattr(fake_db.Query, "execute", capped)
    w["db"].tables.setdefault("strategies", []).extend(
        {"id": f"s{i:05d}", "user_id": ME, "name": "n", "body": {}} for i in range(1005))
    assert len(user_data.export(db.get_profile(ME))["notebooks"]) == 1005
    assert {r["key"]: r["count"] for r in user_data.erase(ME)["done"]}["notebooks"] == 1005
    assert db.sb().table("strategies").select("id").eq("user_id", ME).execute().data == []



def test_erase_and_export_include_the_telegram_verification(w):
    """The Telegram verification record (the confirmed chat and a code waiting to be entered) was neither erased nor
    exported."""
    for uid in (ME, OTHER):
        db.set_setting(alerts.TG_VERIFY + uid, json.dumps({"verified": "12345", "pending": {"chat": "678", "code_hash": "h-" + uid,
                                                                                           "expires": 0, "tries": 0}}))
    out = user_data.export(db.get_profile(ME))
    tg = out["preferences"]["tgverify"]
    assert tg["verified"] == "12345" and tg["pending"]["chat"] == "678" and "h-" + ME not in json.dumps(out)
    assert user_data.erase(ME)["failed"] == []
    assert db.get_setting(alerts.TG_VERIFY + ME) is None and db.get_setting(alerts.TG_VERIFY + OTHER) is not None
