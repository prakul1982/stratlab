"""Read-modify-write races on the per-user settings blobs: db.update_setting, and each site that uses it. A second
writer is slipped in between the first one's read and write (or run in a thread), and both changes must survive."""
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from app import db, holdings, lifecycle, money_networth as nw, stock_alerts as sa
from app.connect import statements, sync
from tests.fake_db import FakeSupabase

IN_OPEN = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def fake(monkeypatch):
    f = FakeSupabase()
    monkeypatch.setattr(db, "_client", f)
    return f


def between(monkeypatch, fn):
    """Run `fn` once, right after the next update_setting function has read its value (the other writer's turn)."""
    real, done = db.update_setting, []

    def wrapped(key, f, tries=10):
        def spy(raw):
            out = f(raw)
            if not done:
                done.append(1)
                fn()
            return out
        return real(key, spy, tries)
    monkeypatch.setattr(db, "update_setting", wrapped)


# ---------- the primitive ----------
def test_update_setting_retries_on_a_write_in_between(fake, monkeypatch):
    db.set_setting("k", "a")
    between(monkeypatch, lambda: db.set_setting("k", "ab"))
    seen = []
    assert db.update_setting("k", lambda v: seen.append(v) or v + "c") == "abc"      # redone on "ab", not on "a"
    assert seen == ["a", "ab"] and db.get_setting("k") == "abc"


def test_update_setting_creates_leaves_and_removes(fake):
    assert db.update_setting("n", lambda v: "1" if v is None else None) == "1"
    assert db.update_setting("n", lambda v: None) == "1" and db.get_setting("n") == "1"
    assert db.update_setting("n", lambda v: db.REMOVE) is None and db.get_setting("n") is None
    assert db.update_setting("n", lambda v: db.REMOVE) is None


def test_two_creators_of_the_same_new_key_both_land(fake, monkeypatch):
    between(monkeypatch, lambda: db.update_setting("new", lambda v: "x"))      # inserted while the first read "absent"
    db.update_setting("new", lambda v: (v or "") + "y")
    assert db.get_setting("new") == "xy"


def test_update_setting_in_threads_loses_nothing(fake):
    def add(i):
        db.update_setting("t", lambda v: json.dumps(json.loads(v or "[]") + [i]))
    ts = [threading.Thread(target=add, args=(i,)) for i in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(json.loads(db.get_setting("t"))) == list(range(12))


def test_update_setting_in_the_second_database(fake, monkeypatch):
    from app import market_store
    from app.config import settings
    from tests.test_storage import FakeStore
    s = FakeStore()
    s.update = lambda key, fn: (lambda new: (s.set(key, new), new)[1] if new is not None else s.get(key))(fn(s.get(key)))
    monkeypatch.setattr(settings, "MARKET_DATABASE_URL", "postgresql://second")
    market_store.use(s)
    try:
        db.set_setting("stocks:x", "1")
        assert db.update_setting("stocks:x", lambda v: v + "2") == "12"
        assert db.get_setting("stocks:x") == "12" and s.get("stocks:x") == "12"
    finally:
        market_store.use(None)


# ---------- lifecycle ----------
def test_two_claims_of_one_email_send_once(fake):
    now = datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc)
    won, gate = [], threading.Barrier(2)
    real = db.update_setting

    def meet(key, f, tries=10):                  # both claimers have read before either writes
        def spy(raw):
            out = f(raw)
            try:
                gate.wait(timeout=0.5)
            except threading.BrokenBarrierError:
                pass
            return out
        return real(key, spy, tries)
    db.update_setting = meet
    try:
        ts = [threading.Thread(target=lambda: won.append(lifecycle._claim("u1", "welcome", now))) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    finally:
        db.update_setting = real
    assert sorted(won) == [False, True]


def test_a_claim_keeps_the_other_emails_keys(fake, monkeypatch):
    now = datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc)
    between(monkeypatch, lambda: db.set_setting(lifecycle.SENT + "u1", json.dumps({"receipt:1": "t"})))
    assert lifecycle._claim("u1", "welcome", now) is True
    assert set(lifecycle.sent("u1")) == {"welcome", "receipt:1"}
    assert lifecycle._claim("u1", "welcome", now) is False


# ---------- stock alerts ----------
def new_alert(uid="u1"):
    return sa.create(uid, {"region": "IN", "symbol": "RELIANCE", "kind": "price", "op": "above", "value": 3000}, 5, {"price": 2990})


def test_an_alert_edit_and_the_jobs_flush_both_survive(fake, monkeypatch):
    a = new_alert()
    texts = sa.apply("u1", {a["id"]: ("RELIANCE crossed above ₹3,000", {}, a["rev"], sa._seen(a))}, IN_OPEN)
    assert texts
    between(monkeypatch, lambda: sa.create("u1", {"region": "IN", "symbol": "TCS", "kind": "price", "op": "below", "value": 1}, 5, {"price": 5}))
    assert sa.flush("u1", {"id": "u1"}, texts, IN_OPEN, send=lambda *x: ["push"]) is True
    row = sa._read("u1")
    assert len(row["items"]) == 2 and len(row["sent"]) == 1                    # the new alert and the sent mark


def test_an_edit_during_apply_is_kept(fake, monkeypatch):
    a = new_alert()
    between(monkeypatch, lambda: sa.create("u1", {"region": "IN", "symbol": "TCS", "kind": "price", "op": "below", "value": 1}, 5, {"price": 5}))
    sa.apply("u1", {a["id"]: ("fired", {"side": "above"}, a["rev"], sa._seen(a))}, IN_OPEN)
    items = {x["symbol"]: x for x in sa._read("u1")["items"]}
    assert set(items) == {"RELIANCE", "TCS"} and items["RELIANCE"]["status"] == "triggered"


def test_a_repeating_alert_does_not_fire_twice_from_one_check(fake):
    a = sa.create("u1", {"region": "IN", "symbol": "RELIANCE", "kind": "price", "op": "above", "value": 3000, "repeat": True}, 5, {"price": 2990})
    change = {a["id"]: ("RELIANCE crossed above ₹3,000", {"side": "above"}, a["rev"], sa._seen(a))}
    assert sa.apply("u1", change, IN_OPEN)                                    # the check applied once…
    assert sa.apply("u1", change, IN_OPEN) == []                              # …and again (a second container's copy of it)
    row = sa._read("u1")
    assert row["items"][0]["fired"] == 1 and row["pending"] == []


# ---------- holdings ----------
def rows(*syms, qty=10.0):
    return [{"symbol": s, "isin": {"INFY": "INE009A01021", "ITC": "INE154A01025"}[s], "name": s, "qty": qty, "avg": 100.0} for s in syms]


@pytest.fixture
def broker(monkeypatch):
    from tests import world
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_a_sync_and_a_hand_edit_both_survive(broker, monkeypatch):
    uid = "u-pro"
    profile = sync.profile_for(uid)
    holdings.save(uid, [{"symbol": "ITC", "exchange": "NSE", "name": "ITC", "qty": 5.0, "avg": 380.0}], "Manual")
    # the user adds a stock by hand after the sync read the holdings but before it wrote
    def user_edit():
        cur = holdings.load(uid)
        holdings.save(uid, cur["items"] + [{"symbol": "TCS", "exchange": "NSE", "name": "TCS", "qty": 3.0, "avg": None}], "Manual")
    between(monkeypatch, user_edit)
    sync.sync_holdings(profile, rows("INFY"), "kite", "Zerodha Kite", replace=False)
    assert {i["symbol"] for i in holdings.load(uid)["items"]} == {"ITC", "TCS", "INFY"}


def test_the_corp_action_route_and_a_sync_both_survive(broker, monkeypatch):
    uid = "u-pro"
    holdings.save(uid, [{"symbol": "ITC", "exchange": "NSE", "name": "ITC", "qty": 5.0, "avg": 380.0}], "Manual")
    between(monkeypatch, lambda: sync.sync_holdings(sync.profile_for(uid), rows("INFY"), "kite", "Zerodha Kite", replace=False))
    holdings.update(uid, lambda h: ([{**i, "qty": 6.0} if i["symbol"] == "ITC" else i for i in h["items"]], h["source"], True))
    got = {i["symbol"]: i["qty"] for i in holdings.load(uid)["items"]}
    assert got == {"ITC": 6.0, "INFY": 10.0}


def test_holdings_update_removes_and_keeps(fake):
    holdings.save("u9", [{"symbol": "ITC", "exchange": "NSE", "name": "ITC", "qty": 1.0, "avg": None}], "Manual")
    assert holdings.update("u9", lambda h: None) is None and len(holdings.load("u9")["items"]) == 1
    holdings.update("u9", lambda h: db.REMOVE)
    assert holdings.load("u9")["items"] == []


# ---------- net worth ----------
def entry(i, name="x"):
    return {"id": i, "kind": "nps", "name": name, "tier1": 1.0, "as_of": "2026-01-01"}


def test_a_statement_save_and_a_net_worth_edit_both_survive(fake, monkeypatch):
    uid = "u8"
    nw.save(uid, [{**entry("aa", "old"), "kind": "ppf"}])
    between(monkeypatch, lambda: nw.update(uid, lambda items: items + [{**entry("bb", "typed"), "kind": "gold"}]))
    assert statements.save_nps(uid, {"tier1": 7.0, "tier2": 0.0}, "2026-09-30", "pro") == ""
    ids = {i["id"] for i in nw.load(uid)["items"]}
    assert {"aa", "bb"} <= ids and len(ids) == 3                  # the typed entry, the old one and the statement's NPS
