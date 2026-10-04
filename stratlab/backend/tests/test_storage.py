"""The databases' size readout, the second database for market data, and moving the data across."""
import json
import os
import socket
from pathlib import Path

import pytest

from app import db, market_store, storage
from app.config import settings
from tests.fake_db import FakeSupabase

PG = os.environ.get("MARKET_TEST_DSN", "postgresql://postgres@127.0.0.1:55432/market")


class FakeStore:
    """market_store.Store's methods over dicts."""
    def __init__(self):
        self.kv, self.snaps, self.stamp = {}, [], 0

    def get(self, k): return self.kv.get(k, (None, None))[1]
    def set(self, k, v):
        self.stamp += 1
        self.kv[k] = (f"2030-01-01T00:00:{self.stamp:02d}+00:00", v)
    def set_many(self, rows):
        for k, v in rows:
            self.set(k, v)
    def delete(self, k): self.kv.pop(k, None)
    def with_prefix(self, p, limit=1000):
        return sorted(((k, v, t) for k, (t, v) in self.kv.items() if k.startswith(p)), key=lambda x: x[2], reverse=True)[:limit]
    def all_with_prefix(self, p): return sorted((k, v) for k, (t, v) in self.kv.items() if k.startswith(p))
    def add_snapshot(self, r): self.snaps.append(dict(r))
    def add_snapshots(self, rows): self.snaps += [dict(r) for r in rows]
    def delete_snapshots_before(self, iso): self.snaps = [r for r in self.snaps if r["taken_at"] >= iso]
    def snapshots(self, name, since, until, limit=12):
        rows = [r for r in self.snaps if r["name"] == name and since <= r["taken_at"] < until]
        return sorted(rows, key=lambda r: r["taken_at"], reverse=True)[:limit]
    def usage(self): return {"total": 1234, "tables": []}


@pytest.fixture
def fake(monkeypatch):
    f = FakeSupabase()
    monkeypatch.setattr(db, "_client", f)
    return f


@pytest.fixture
def second(monkeypatch):
    s = FakeStore()
    monkeypatch.setattr(settings, "MARKET_DATABASE_URL", "postgresql://second")
    market_store.use(s)
    yield s
    market_store.use(None)


def test_the_size_sql_in_the_server_matches_the_schema_file():
    text = (Path(__file__).resolve().parents[2] / "supabase" / "schema.sql").read_text()
    a, b = text.index("-- usage-function:start"), text.index("-- usage-function:end")
    assert text[a:b].split("\n", 1)[1].strip() == storage.usage_sql()


def test_without_a_second_database_everything_stays_in_the_main_one(fake, monkeypatch):
    monkeypatch.setattr(settings, "MARKET_DATABASE_URL", "")
    assert market_store.store() is None
    db.set_setting("breadth:hist:N500", "x")
    assert db.get_setting("breadth:hist:N500") == "x"
    assert any(r["key"] == "breadth:hist:N500" for r in fake.tables["app_settings"])


def test_market_keys_go_to_the_second_database_and_users_data_stays(fake, second):
    db.set_setting("breadth:hist:N500", "hist")
    db.set_setting("holdings:u1", "mine")
    db.set_setting("breadth:alerts:u1", "alerts")       # a user's alerts, though under breadth:
    keys = {r["key"] for r in fake.tables["app_settings"]}
    assert "breadth:hist:N500" not in keys and {"holdings:u1", "breadth:alerts:u1"} <= keys
    assert second.get("breadth:hist:N500") == "hist" and second.get("holdings:u1") is None
    assert db.get_setting("breadth:hist:N500") == "hist"
    db.delete_setting("breadth:hist:N500")
    assert db.get_setting("breadth:hist:N500") is None


def test_data_not_moved_yet_is_still_read_from_the_main_database(fake, second):
    fake.tables["app_settings"] = [{"key": "deep:v3:TCS", "value": "old", "updated_at": "2026-01-01T00:00:00+00:00"},
                                   {"key": "breadth:hist:N50", "value": "stale", "updated_at": "2026-01-01T00:00:00+00:00"}]
    second.set("breadth:hist:N50", "fresh")
    assert db.get_setting("deep:v3:TCS") == "old"
    assert db.get_setting("breadth:hist:N50") == "fresh"            # the second database's copy wins
    assert dict(db.all_settings_with_prefix("breadth:")) == {"breadth:hist:N50": "fresh"}
    assert db.settings_with_prefix("breadth:hist:") == ["fresh"]


def test_option_chains_merge_both_databases_newest_first(fake, second):
    fake.tables["option_snapshots"] = [{"id": 1, "name": "NIFTY", "taken_at": "2026-10-01T04:00:00+00:00", "expiry": "2026-10-07",
                                        "spot": 1, "chain": []}]
    db.add_option_snapshot({"name": "NIFTY", "taken_at": "2026-10-02T04:00:00+00:00", "expiry": "2026-10-07", "spot": 2, "chain": [],
                            "exchange": "NFO", "lot": 75})
    assert len(fake.tables["option_snapshots"]) == 1 and len(second.snaps) == 1
    got = db.option_snapshots("NIFTY", "2026-09-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00")
    assert [r["spot"] for r in got] == [2, 1]
    db.delete_option_snapshots_before("2026-10-01T12:00:00+00:00")
    assert fake.tables["option_snapshots"] == [] and len(second.snaps) == 1


def test_move_copies_market_data_and_deletes_it_from_the_main_database(fake, second):
    fake.tables["app_settings"] = ([{"key": f"deep:v3:S{i:03d}", "value": f"v{i}"} for i in range(450)]
                                   + [{"key": "holdings:u1", "value": "mine"}, {"key": "audit:last", "value": "a"}])
    second.set("deep:v3:S001", "newer")
    fake.tables["option_snapshots"] = [{"id": i, "name": "NIFTY", "taken_at": f"2026-10-01T04:{i % 60:02d}:00+00:00",
                                        "expiry": "2026-10-07", "exchange": "NFO", "spot": i, "lot": 75, "chain": [[1]]} for i in range(1, 431)]
    moved = market_store.move(db, second, batch=200)
    assert moved == {"settings": 451, "snapshots": 430}
    assert [r["key"] for r in fake.tables["app_settings"]] == ["holdings:u1"]
    assert fake.tables["option_snapshots"] == [] and len(second.snaps) == 430
    assert second.get("deep:v3:S001") == "newer" and second.get("deep:v3:S449") == "v449"
    assert market_store.move(db, second) == {"settings": 0, "snapshots": 0}      # running it again does nothing


def test_report_asks_for_the_size_function_until_it_exists(fake, monkeypatch):
    monkeypatch.setattr(settings, "MARKET_DATABASE_URL", "")
    r = storage.report()
    assert r["missing"] and "stratlab_db_usage" in r["sql"]
    assert storage.check()["state"] == "warn"
    fake.usage = {"total": 450 * 1024 * 1024, "tables": [{"name": "public.option_snapshots", "bytes": 300 * 1024 * 1024}], "settings": []}
    r = storage.report()
    assert r["share"] == 0.9 and not r.get("missing")
    c = storage.check()
    assert c["state"] == "warn" and "MARKET_DATABASE_URL" in c["detail"]
    fake.usage["total"] = 100 * 1024 * 1024
    assert storage.check()["state"] == "pass"


def test_admin_routes(fake, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.fake_db import headers
    monkeypatch.setattr(settings, "MARKET_DATABASE_URL", "")
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    c = TestClient(app)
    admin_token = "admin-token"
    assert c.get("/admin/storage").status_code in (401, 403)
    r = c.get("/admin/storage", headers=headers(admin_token))
    assert r.status_code == 200 and r.json()["missing"]
    assert c.post("/admin/storage/move", headers=headers(admin_token)).json()["detail"]["code"] == "no_market_db"


def _pg_up() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 55432), timeout=0.3).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _pg_up(), reason="needs a local Postgres on port 55432 (MARKET_TEST_DSN)")
def test_the_real_postgres_store_round_trips():
    s = market_store.Store(PG)
    s._run("truncate app_settings, option_snapshots")
    s.set("deep:v3:A_1%", "one")
    s.set("deep:v3:A_1%", "two")
    s.set_many([("deep:v3:B", "b"), ("deep:v3:AX1", "x")])
    assert s.get("deep:v3:A_1%") == "two" and s.get("nope") is None
    assert [k for k, _ in s.all_with_prefix("deep:v3:A_")] == ["deep:v3:A_1%"]     # _ and % are literal
    s.add_snapshots([{"taken_at": "2026-10-01T04:00:00+00:00", "exchange": "NFO", "name": "NIFTY", "expiry": "2026-10-07",
                      "spot": 25000.5, "lot": 75, "chain": [[25000, 1, 2]]}])
    got = s.snapshots("NIFTY", "2026-09-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00")
    assert got[0]["chain"] == [[25000, 1, 2]] and got[0]["expiry"] == "2026-10-07" and got[0]["spot"] == 25000.5
    s.delete_snapshots_before("2026-10-02T00:00:00+00:00")
    assert s.snapshots("NIFTY", "2026-09-01T00:00:00+00:00", "2026-11-01T00:00:00+00:00") == []
    u = s.usage()
    assert u["total"] > 0 and {t["name"] for t in u["tables"]} >= {"app_settings", "option_snapshots"}
    s.delete("deep:v3:B")
    assert s.get("deep:v3:B") is None
