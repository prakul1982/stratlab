"""Users' data on Railway's Postgres: the query calls the app makes give what Supabase gave (app/pgdb.py), the one-time
move copies every table whole or nothing (app/maindb.py), and Admin's button asks for it and restarts."""
import json
import os
import socket
import time

import pytest

from app import db, maindb, market_store, pgdb
from app.config import settings
from tests.fake_db import FakeSupabase, headers

SERVER = os.environ.get("MAIN_TEST_SERVER", "postgresql://postgres@127.0.0.1:55432")
PG = SERVER + "/maindbtest"          # its own database: the market store's tests use another


def _pg_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 55432), timeout=0.3).close()
        return True
    except OSError:
        return False


needs_pg = pytest.mark.skipif(not _pg_up(), reason="needs a local Postgres on port 55432 (MAIN_TEST_SERVER)")


@pytest.fixture(autouse=True)
def one_at_a_time():
    """The tests here share one database; test workers running side by side take turns (a lock in Postgres)."""
    if not _pg_up():
        yield
        return
    import psycopg
    with psycopg.connect(SERVER + "/postgres", autocommit=True) as c:
        try:
            c.execute("create database maindbtest")
        except psycopg.errors.DuplicateDatabase:
            pass
        except psycopg.errors.UniqueViolation:       # two workers creating it at once
            pass
    with psycopg.connect(PG, autocommit=True) as lock:
        lock.execute("select pg_advisory_lock(4242)")
        try:
            yield
        finally:
            lock.execute("select pg_advisory_unlock(4242)")


def _wipe(url: str = PG):
    import psycopg
    with psycopg.connect(url, autocommit=True) as c:
        c.execute("drop schema if exists app cascade")
        c.execute("create table if not exists public.app_settings (key text primary key, value text, updated_at timestamptz not null default now())")
        c.execute("delete from public.app_settings where key = %s", (maindb.STATE_KEY,))


@pytest.fixture
def pg(monkeypatch):
    """Users' data on a fresh Postgres, with the fake's sign-ins."""
    _wipe()
    fake = FakeSupabase()
    client = pgdb.PgClient(PG, auth_source=lambda: fake)
    monkeypatch.setattr(db, "_client", client)
    db.forget_mirror()
    yield client
    client.close()


# ---------- the query calls ----------
@needs_pg
def test_profiles_are_made_once_read_and_updated(pg):
    p = db.get_profile("u-1", "a@example.com")
    assert p["id"] == "u-1" and p["plan"] == "free" and p["cancel_at_period_end"] is False
    assert isinstance(p["created_at"], str) and p["created_at"].endswith("+00:00")
    assert db.get_profile("u-1", "other@example.com")["email"] == "a@example.com"      # never overwritten
    row = db.update_profile("u-1", plan="pro", current_period_end="2026-11-16T00:00:00+05:30")
    assert row["plan"] == "pro" and row["current_period_end"] == "2026-11-15T18:30:00+00:00"
    assert db.update_profile("nobody", plan="pro") is None
    assert db.find_profile("u-1")["plan"] == "pro" and db.find_profile("nobody") is None
    assert [r["id"] for r in db.all_profiles(page=1)] == ["u-1"]


@needs_pg
def test_notebooks_keep_their_json_and_list_without_history(pg):
    body = {"kind": "notebook", "question": "EMA cross", "instrument": {"symbol": "NIFTY", "market": "IN"},
            "summary": {"runs": 2}, "tf": "1d", "experiments": [{"v": 1, "big": "x" * 1000}]}
    nb = db.save_strategy("u-1", "EMA", body, 256265)
    assert nb["body"] == body and nb["instrument_token"] == 256265 and len(nb["id"]) == 36
    assert db.save_strategy("u-1", "EMA 2", {**body, "tf": "1h"}, None, sid=nb["id"])["name"] == "EMA 2"
    assert db.save_strategy("u-2", "not mine", body, None, sid=nb["id"]) is None
    rows = db.list_notebook_rows("u-1")
    assert rows == [{"id": nb["id"], "name": "EMA 2", "instrument_token": None, "updated_at": rows[0]["updated_at"],
                     "kind": "notebook", "question": "EMA cross", "instrument": {"symbol": "NIFTY", "market": "IN"},
                     "summary": {"runs": 2}, "tf": "1h", "pinned": None, "group": None}]
    assert db.has_strategy("u-1") and not db.has_strategy("u-2")
    db.delete_strategy("u-1", nb["id"])
    assert db.get_strategy("u-1", nb["id"]) is None


@needs_pg
def test_live_sessions_and_orders(pg):
    s = db.create_session({"user_id": "u-1", "name": "S", "strategy": {"entry": []}, "instrument": {"symbol": "X"},
                           "state": {"equity_curve": [{"t": "2026-10-16", "eq": 1.5}]}})
    assert s["status"] == "running" and s["state"]["equity_curve"][0]["eq"] == 1.5 and s["stopped_at"] is None
    db.add_order({"session_id": s["id"], "user_id": "u-1", "side": "buy", "qty": 3, "price": 101.25, "pnl": None})
    db.update_session(s["id"], state={"n": 2})
    assert db.get_session_row("u-1", s["id"])["state"] == {"n": 2}
    assert db.count_running("u-1") == 1 and [r["id"] for r in db.running_index()] == [s["id"]]
    assert db.sessions_by_ids([s["id"], "missing"])[0]["id"] == s["id"]
    assert db.stopped_among([s["id"]]) == set()
    db.delete_session("u-1", s["id"])                          # a running session is never deleted
    assert db.get_session_row("u-1", s["id"]) is not None
    assert db.stop_running_session(s["id"], "test") is True and db.stop_running_session(s["id"], "again") is False
    assert db.stopped_among([s["id"]]) == {s["id"]}
    assert [r["status"] for r in db.user_sessions("u-1")] == ["stopped"]
    assert db.delete_stopped_sessions("u-1") == 1
    with pg.connection() as c:
        assert c.execute("select count(*) from app.live_orders").fetchone()[0] == 0     # the orders went with it


@needs_pg
def test_usage_counts_and_times(pg):
    for _ in range(3):
        db.add_usage("u-1", "backtest")
    db.add_usage("u-1", "ai")
    assert db.count_usage("u-1", "backtest", "2000-01-01T00:00:00+05:30") == 3
    assert db.count_usage("u-1", "backtest", "2999-01-01T00:00:00+00:00") == 0
    assert len(db.usage_times("u-1", "ai", "2000-01-01T00:00:00Z", "2999-01-01T00:00:00Z")) == 1


@needs_pg
def test_settings_read_write_atomic_update_and_prefix(pg):
    assert db.get_setting("k:1") is None
    db.set_setting("k:1", "a")
    db.set_setting("k:1", "b")
    assert db.get_setting("k:1") == "b"
    assert db.update_setting("k:2", lambda cur: "1" if cur is None else str(int(cur) + 1)) == "1"
    assert db.update_setting("k:2", lambda cur: str(int(cur) + 1)) == "2"
    assert db.update_setting("k:2", lambda cur: db.REMOVE) is None and db.get_setting("k:2") is None
    for i in range(5):
        db.set_setting(f"p:{i}", str(i))
    assert db.all_settings_with_prefix("p:", page=2) == [(f"p:{i}", str(i)) for i in range(5)]
    assert db.settings_with_prefix("p:", limit=2) == ["4", "3"]
    db.delete_setting("p:0")
    assert db.get_setting("p:0") is None


@needs_pg
def test_a_duplicate_insert_reads_as_one(pg):
    pg.table("app_settings").insert({"key": "dup", "value": "1"}).execute()
    with pytest.raises(Exception) as e:
        pg.table("app_settings").insert({"key": "dup", "value": "2"}).execute()
    assert db._is_duplicate(e.value)


@needs_pg
def test_counts_deletes_and_filters_as_postgrest(pg):
    for i, plan in enumerate(["free", "basic", "pro", "pro"]):
        pg.table("profiles").insert({"id": f"u{i}", "email": f"U{i}@Example.com", "plan": plan}).execute()
    r = pg.table("profiles").select("id", count="exact").in_("plan", ["basic", "pro"]).limit(1).execute()
    assert r.count == 3 and len(r.data) == 1
    assert [x["id"] for x in pg.table("profiles").select("id").ilike("email", "%u2@%").execute().data] == ["u2"]
    assert [x["id"] for x in pg.table("profiles").select("id").neq("plan", "pro").order("id", desc=True).execute().data] == ["u1", "u0"]
    assert pg.table("profiles").select("id").in_("id", []).execute().data == []
    gone = pg.table("profiles").delete(count="exact", returning="minimal").eq("plan", "pro").execute()
    assert gone.count == 2 and gone.data == []
    with pytest.raises(ValueError):
        pg.table("profiles").select("id; drop table app.profiles").execute()


@needs_pg
def test_size_readout(pg):
    db.set_setting("stocks:x", "y" * 100)
    u = db.usage()
    assert u["total"] > 0 and any(t["name"] == "app.app_settings" for t in u["tables"])
    assert u["settings"][0]["prefix"] == "stocks"


@needs_pg
def test_sign_in_checks_still_go_to_supabase(pg):
    assert pg.auth.get_user("pro-token").user.id == "u-pro"


@needs_pg
def test_a_request_that_cant_get_a_connection_gets_a_503(pg, monkeypatch):
    from psycopg_pool import PoolTimeout

    class Busy:
        def connection(self):
            raise PoolTimeout("no connection")
    monkeypatch.setattr(pg, "_pool", lambda lane: Busy())
    token = db._in_request.set(True)
    try:
        with pytest.raises(db.DatabaseUnavailable):
            db.find_profile("u-1")
    finally:
        db._in_request.reset(token)


# ---------- the move ----------
def _source() -> FakeSupabase:
    src = FakeSupabase()
    src.tables["profiles"] = src.tables["profiles"][:3]
    src.tables["strategies"] = [{"id": f"00000000-0000-0000-0000-00000000000{i}", "user_id": "u-pro", "name": f"N{i}",
                                 "body": {"kind": "notebook", "i": i}, "instrument_token": None,
                                 "created_at": "2026-10-01T00:00:00+00:00", "updated_at": "2026-10-02T00:00:00+00:00"} for i in range(3)]
    src.tables["usage_events"] = [{"id": i, "user_id": "u-pro", "kind": "ai", "created_at": "2026-10-03T00:00:00+00:00"} for i in range(1, 6)]
    src.tables["live_sessions"] = [{"id": "s1", "user_id": "u-pro", "name": "S", "strategy": {}, "instrument": {"symbol": "X"},
                                    "status": "running", "state": {"cash": 1}, "stop_reason": None,
                                    "started_at": "2026-10-04T00:00:00+00:00", "stopped_at": None}]
    src.tables["live_orders"] = [{"id": 7, "session_id": "s1", "user_id": "u-pro", "side": "buy", "qty": 1, "price": 10.5,
                                  "reason": None, "pnl": None, "candle_time": None, "ts": "2026-10-04T01:00:00+00:00"}]
    src.tables["app_settings"] = [{"key": f"prefs:{i}", "value": str(i), "updated_at": "2026-10-05T00:00:00+00:00"} for i in range(4)]
    src.tables["option_snapshots"] = []
    return src


@needs_pg
def test_the_move_copies_every_table_and_marks_it_done():
    _wipe()
    src = _source()
    src.tables["profiles"][0]["referred_by"] = "u-free"            # a column added in Supabase later is carried too
    client = pgdb.PgClient(PG, auth_source=lambda: src)
    try:
        copied = maindb.move(src, client)
        assert copied == {"profiles": 3, "strategies": 3, "usage_events": 5, "live_sessions": 1, "live_orders": 1,
                          "app_settings": 4, "option_snapshots": 0}
        rows = client.table("strategies").select("*").order("id").execute().data
        assert [r["body"] for r in rows] == [{"kind": "notebook", "i": i} for i in range(3)]
        assert client.table("profiles").select("referred_by").eq("id", src.tables["profiles"][0]["id"]).execute().data[0]["referred_by"] == "u-free"
        assert client.table("live_orders").select("price").execute().data == [{"price": 10.5}]
        nxt = client.table("usage_events").insert({"user_id": "u-pro", "kind": "ai"}).execute().data[0]
        assert nxt["id"] == 6                                     # the numbering carries on after the copied rows
        ms = market_store.Store(PG)
        assert json.loads(ms.get(maindb.STATE_KEY))["state"] == "done"
        # a second try (after a failed one, say) replaces what's there rather than doubling it
        assert maindb.move(src, client)["strategies"] == 3
        assert len(client.table("strategies").select("id").execute().data) == 3
    finally:
        client.close()


@needs_pg
def test_a_move_that_fails_part_way_keeps_nothing():
    _wipe()
    src = _source()
    real = src.table

    def table(name):
        if name == "live_orders":
            raise RuntimeError("Supabase went away")
        return real(name)
    src.table = table
    client = pgdb.PgClient(PG, auth_source=lambda: src)
    try:
        with pytest.raises(RuntimeError):
            maindb.move(src, client)
        assert client.table("profiles").select("id").execute().data == []
        assert market_store.Store(PG).get(maindb.STATE_KEY) is None
    finally:
        client.close()


@pytest.fixture
def at_start(monkeypatch):
    """maindb.start() with the market database on the test Postgres and Supabase as the fake."""
    _wipe()
    src = _source()
    monkeypatch.setattr(settings, "MARKET_DATABASE_URL", PG)
    monkeypatch.setattr(market_store, "_store", None, raising=False)
    monkeypatch.setattr(db, "_supabase", src)
    monkeypatch.setattr(db, "_client", src)
    monkeypatch.delenv("MAIN_DATABASE", raising=False)
    monkeypatch.setattr(maindb, "READ_PAUSE", 0.01)
    yield src
    if db.on_railway():
        db._client.close()
    if market_store.store() is not None:
        market_store.store().pool().close()


@needs_pg
def test_start_stays_on_supabase_until_asked(at_start):
    assert maindb.start() == "supabase" and db.sb() is at_start


@needs_pg
def test_start_moves_when_asked_then_reads_railway_on_every_start(at_start, monkeypatch):
    maindb.request(market_store.store())
    assert maindb.start() == "railway" and db.on_railway()
    assert db.get_setting("prefs:2") == "2" and db.find_profile(at_start.tables["profiles"][0]["id"]) is not None
    assert maindb.status()["on"] == "railway" and maindb.status()["state"] == "done"
    assert any(r["key"] == maindb.STATE_KEY for r in at_start.tables["app_settings"])    # Supabase knows too
    db._client.close()
    monkeypatch.setattr(db, "_client", at_start)
    assert maindb.start() == "railway" and db.on_railway()          # the next start: no copy, straight to Railway
    monkeypatch.setenv("MAIN_DATABASE", "supabase")
    db._client.close()
    monkeypatch.setattr(db, "_client", at_start)
    assert maindb.start() == "supabase" and not db.on_railway()     # the way back, by hand


@needs_pg
def test_start_carries_on_with_supabase_when_the_move_fails(at_start, monkeypatch):
    maindb.request(market_store.store())
    monkeypatch.setattr(maindb, "move", lambda src, pg: (_ for _ in ()).throw(RuntimeError("boom")))
    assert maindb.start() == "supabase" and db.sb() is at_start
    st = maindb.state()
    assert st["state"] == "failed" and "boom" in st["error"]


def test_start_wont_serve_supabases_old_copy_when_railway_is_unreachable(monkeypatch):
    src = FakeSupabase()
    src.tables["app_settings"] = [{"key": maindb.STATE_KEY, "value": json.dumps({"state": "done"}), "updated_at": "2026-10-16T00:00:00+00:00"}]

    class Down:
        def get(self, key):
            raise OSError("connection refused")
    monkeypatch.setattr(market_store, "store", lambda: Down())
    monkeypatch.setattr(db, "_supabase", src)
    monkeypatch.setattr(maindb, "READ_PAUSE", 0.0)
    monkeypatch.delenv("MAIN_DATABASE", raising=False)
    with pytest.raises(RuntimeError):
        maindb.start()
    src.tables["app_settings"] = []                    # never moved: Supabase is still the place
    assert maindb.start() == "supabase"


# ---------- Admin ----------
def test_admin_asks_for_the_move_and_restarts(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    fake = FakeSupabase()
    monkeypatch.setattr(db, "_client", fake)
    asked, restarted = [], []

    class Store:
        def get(self, key): return None
        def set(self, key, value): asked.append((key, json.loads(value)))
    monkeypatch.setattr(market_store, "store", lambda: Store())
    monkeypatch.setattr(main, "restart_process", lambda *a, **k: restarted.append(True))
    from app import leader
    monkeypatch.setattr(leader, "leading", lambda: True)
    monkeypatch.delenv("MAIN_DATABASE", raising=False)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    c = TestClient(main.app)
    assert c.post("/admin/storage/move-users", headers=headers("pro-token")).status_code == 403
    r = c.post("/admin/storage/move-users", headers=headers("admin-token"))
    assert r.status_code == 200 and r.json() == {"restarting": True}
    assert asked[-1][0] == maindb.STATE_KEY and asked[-1][1]["state"] == "pending" and restarted == [True]
    monkeypatch.setenv("MAIN_DATABASE", "supabase")
    assert c.post("/admin/storage/move-users", headers=headers("admin-token")).status_code == 400


@needs_pg
def test_a_server_that_caps_one_read_still_has_every_row_copied(monkeypatch):
    """Supabase returns at most 1000 rows a read: a short page isn't the end of the table (code review, 16 Oct)."""
    from tests import fake_db
    _wipe()
    src = _source()
    src.tables["usage_events"] = [{"id": i, "user_id": "u-pro", "kind": "ai", "created_at": "2026-10-03T00:00:00+00:00"}
                                  for i in range(1000, 3500)]   # four digits: the fake sorts as text
    real_limit = fake_db.Query.limit
    monkeypatch.setattr(fake_db.Query, "limit", lambda self, n: real_limit(self, min(n, 700)))
    client = pgdb.PgClient(PG, auth_source=lambda: src)
    try:
        assert maindb.move(src, client)["usage_events"] == 2500
        assert client.table("usage_events").select("id", count="exact").execute().count == 2500
    finally:
        client.close()
