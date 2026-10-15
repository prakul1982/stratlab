"""The sessions list and the plan limit count every running session, however many newer stopped ones there are."""
import types

import pytest

from app import db, leader, live, main
from tests import world

BASIC, PRO = world.headers("basic-token"), world.headers("pro-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def add(uid, n, status, first="2026-03-01", **kw):
    return [db.create_session({"user_id": uid, "name": f"{status} {i}", "strategy": {}, "instrument": {"symbol": "X"},
                               "status": status, "started_at": f"{first}T10:{i:02d}:00+00:00", **kw}) for i in range(n)]


def test_running_sessions_are_listed_even_when_older_than_the_newest_twenty(w):
    old = add("u-pro", 1, "running", first="2026-01-01")[0]
    add("u-pro", 25, "stopped")
    rows = db.user_sessions("u-pro")
    assert len(rows) == 21 and old["id"] in {r["id"] for r in rows}
    assert [r["started_at"] for r in rows] == sorted((r["started_at"] for r in rows), reverse=True)     # still newest first
    assert len(db.user_sessions("u-pro", 5, running=False)) == 5
    listed = w["client"].get("/live/sessions", headers=PRO).json()
    assert old["id"] in {r["id"] for r in listed} and len(listed) == 21
    assert db.count_running("u-pro") == 1 and db.count_running("u-basic") == 0


def test_a_follower_counts_all_running_sessions_for_the_plan_limit(w, monkeypatch):
    add("u-basic", 2, "running", first="2026-01-01")
    add("u-basic", 25, "stopped")
    monkeypatch.setattr(leader, "leading", lambda: False)
    with pytest.raises(live.LimitError):
        main.manager.start({"id": "u-basic"}, "basic", types.SimpleNamespace(name="x", model_dump=lambda: {}), {"market": "CRYPTO"})


def test_me_counts_running_sessions_from_the_database_on_a_follower(w, monkeypatch):
    add("u-pro", 2, "running")
    add("u-pro", 1, "stopped")
    c = w["client"]
    assert c.get("/me", headers=PRO).json()["live_running"] == 0              # the leader's manager runs none of them here
    monkeypatch.setattr(leader, "leading", lambda: False)
    assert c.get("/me", headers=PRO).json()["live_running"] == 2
