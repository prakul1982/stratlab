"""Lane admin90 (owner, 25 Nov: "can you do a admin cleanup and check"): Admin's numbers come from the right rows and say when they
were read, its read-only lists never make a profile, and its clean-up actions are bounded and work.

Users live on Railway's database since 16 Oct, where a profile's id is any text (Supabase's was a uuid tied to a sign-in account): a
job that took a settings key's tail for a user id ("holdings:files:<uid>" read as the user "files:<uid>") made a profile for it there,
and Overview counted it as a user."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import admin, computed, db, library_admin, main, money_networth
from tests import world as W
from tests.fake_db import headers

A = headers("admin-token")


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    main.forget_overview()
    monkeypatch.setattr(admin, "sign_ins", lambda fresh=False: ({}, None))
    yield world
    main.forget_overview()
    world["close"]()


def _now(**kw) -> str:
    return (datetime.now(timezone.utc) + timedelta(**kw)).isoformat()


# ---------- stray profile rows: never a user ----------
def test_a_stray_profile_row_is_left_out_of_every_count_and_the_users_list(w):
    c = w["client"]
    before = c.get("/admin/overview?fresh=1", headers=A).json()["stats"]
    # what the monthly net worth pass made on Railway for a user's imported holdings file: a profile with the key's tail as its id
    db.sb().table("profiles").insert({"id": "files:u-pro", "email": None, "plan": "free", "created_at": _now()}).execute()
    st = c.get("/admin/overview?fresh=1", headers=A).json()["stats"]
    for k in ("users", "new_7d", "signups_today"):
        assert st[k] == before[k], k
    assert st["plans"] == before["plans"]
    assert st["stray_profiles"] == 1
    shown = c.get("/admin/overview?fresh=1&test=1", headers=A).json()["stats"]      # "Show test accounts" shows test accounts, not these
    assert shown["users"] == before["users"]
    assert "files:u-pro" not in {u["id"] for u in c.get("/admin/users", headers=A).json()}
    assert "files:u-pro" not in {u["id"] for u in c.get("/admin/users?plan=free&test=1", headers=A).json()}
    assert admin.week_stats(datetime.now(timezone.utc) - timedelta(days=7))["users"] == before["users"]


def test_the_owner_can_remove_the_stray_rows_and_nothing_else(w):
    c = w["client"]
    for i in range(3):
        db.sb().table("profiles").insert({"id": f"files:u-{i}", "plan": "free", "created_at": _now()}).execute()
    users = c.get("/admin/overview?fresh=1", headers=A).json()["stats"]["users"]
    r = c.post("/admin/stray-profiles/remove", headers=A)
    assert r.status_code == 200 and r.json() == {"removed": 3}
    assert admin.stray_rows() == []
    assert db.find_profile("u-pro") is not None                      # real users stay
    st = c.get("/admin/overview", headers=A).json()["stats"]          # the kept counts were forgotten
    assert st["stray_profiles"] == 0 and st["users"] == users
    assert c.post("/admin/stray-profiles/remove", headers=headers("pro-token")).status_code == 403


def test_the_net_worth_pass_never_takes_a_files_key_for_a_user(monkeypatch):
    seen = []
    keys = {"networth:": [("networth:u1", "{}")], "holdings:": [("holdings:u2", "{}"), ("holdings:files:u2", "{}")], "mf:": [("mf:u3", "{}")]}
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p: keys.get(p, []))
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    monkeypatch.setattr(money_networth, "history", lambda uid: [])

    class Run:
        def seen(self, uid): return False
        def beat(self): pass
        def record(self, uid): pass
        def done(self): pass
    monkeypatch.setattr(money_networth.run_marks, "claim", lambda *a, **k: Run())
    job = money_networth.Job(lambda uid: seen.append(uid) or None)
    job.tick(datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc))
    assert sorted(seen) == ["u1", "u2", "u3"]


# ---------- read-only lists never make a profile ----------
def test_the_paper_sessions_list_never_makes_a_profile_for_a_user_who_has_none(w):
    main.manager.sessions.clear()
    db.create_session({"user_id": "u-gone", "name": "left behind", "status": "running", "instrument": {"symbol": "TCS", "market": "IN"},
                       "strategy": {"risk": {"capital": 1}}})
    rows = w["client"].get("/admin/sessions", headers=A).json()
    assert [(r["name"], r["email"]) for r in rows] == [("left behind", None)]
    assert db.find_profile("u-gone") is None


# ---------- Overview says when its counts were read ----------
def test_overview_counts_carry_the_time_they_were_read_and_keep_it_while_kept(w):
    c = w["client"]
    first = c.get("/admin/overview?fresh=1", headers=A).json()["stats"]
    at = datetime.fromisoformat(first["counted_at"])
    assert abs((datetime.now(timezone.utc) - at).total_seconds()) < 60
    assert c.get("/admin/overview", headers=A).json()["stats"]["counted_at"] == first["counted_at"]     # the kept copy: the same time


# ---------- the kept theme decks nobody gets any more: counted, and removed on the owner's press ----------
@pytest.fixture
def store(monkeypatch):
    s: dict = {}

    class Store(dict):
        def update_setting(self, k, fn):
            v = fn(self.get(k))
            if v is not None:
                self[k] = v
            return self.get(k)
    s = Store()
    monkeypatch.setattr(db, "get_setting", s.get)
    monkeypatch.setattr(db, "set_setting", s.__setitem__)
    monkeypatch.setattr(db, "update_setting", s.update_setting)
    monkeypatch.setattr(db, "delete_setting", lambda k: s.pop(k, None))
    computed.reset_for_tests()
    return s


def test_old_decks_are_counted_and_removed_and_the_current_ones_stay(store, monkeypatch):
    computed.put("deck:theme", ["IN", "today", "pdf"], "Zm9v", label="Today (PDF)", region="IN")
    old = computed.put("deck:theme", ["IN", "yesterday", "pdf"], "Zm9v", label="Yesterday (PDF)", region="IN")
    assert old is not None

    def aged(cur):
        ix = json.loads(cur)
        for e in ix["entries"].values():
            if e["label"].startswith("Yesterday"):
                e["at"] -= 2 * 86400
        return json.dumps(ix)
    db.update_setting(computed.INDEX + "deck:theme", aged)
    assert len(library_admin.old_decks()) == 1
    got = library_admin.library_remove_old_decks()
    assert got == {"removed": 1, "of": 1}
    assert [e["label"] for e in computed.index("deck:theme")["entries"].values()] == ["Today (PDF)"]
    assert library_admin.old_decks() == []


# ---------- at the root: a profile is only ever made for a sign-in account's id ----------
def test_get_profile_never_makes_a_row_for_an_id_that_is_not_a_users(w):
    for bad in ("files:u-pro", "hist:u-pro", "u pro", "", "x" * 65):
        assert db.get_profile(bad) is None, bad
        assert db.find_profile(bad) is None, bad
    assert admin.stray_rows() == []
    made = db.get_profile("u-brand-new", "new@example.com")            # a real sign-in id is still made, as on a first sign-in
    assert made["id"] == "u-brand-new" and made["plan"] == "free"
    assert db.user_id_ok("6f1c2a9e-1d2b-4c3d-9e8f-0a1b2c3d4e5f") and not db.user_id_ok("files:6f1c2a9e-1d2b-4c3d-9e8f-0a1b2c3d4e5f")


def test_the_reported_strategies_queue_shows_a_deleted_author_without_making_a_row(w, monkeypatch):
    from app import library
    monkeypatch.setattr(library, "all_entries", lambda: [{"id": "e1", "name": "Gone", "owner": "u-deleted", "reports": {"r1": {"reason": "spam"}},
                                                          "published_at": "2026-11-01"}])
    rows = w["client"].get("/admin/library", headers=A).json()["entries"]
    assert [(r["name"], r["email"]) for r in rows] == [("Gone", None)]
    assert db.find_profile("u-deleted") is None
