"""Account and profile fixes: prefs saved atomically, the short sign-in cache, the profile cache never keeping a read
from before a change, first sign-in never overwriting a row, and turning alerts off on any plan."""
import json
import time
from types import SimpleNamespace

import pytest

from app import auth, daily_report, db, main
from tests import world

PRO = world.headers("pro-token")
ME = "u-pro"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    main.app.dependency_overrides.clear()
    built["close"]()


def test_prefs_and_onboarding_keep_a_change_made_meanwhile(w, monkeypatch):
    key = daily_report.PREFS + ME
    real, hits = db._swap, []

    def racing(k, new, stamp):                    # another request saves the onboarding between this read and write
        if k == key and not hits:
            hits.append(1)
            db.set_setting(key, json.dumps({"onboarding": {"tour": "done"}}))
        return real(k, new, stamp)
    monkeypatch.setattr(db, "_swap", racing)
    r = w["client"].put("/me/prefs", headers=PRO, json={"level": "new"})
    assert r.status_code == 200, r.text
    got = json.loads(db.get_setting(key))
    assert got["level"] == "new" and got["onboarding"] == {"tour": "done"}
    hits.clear()

    def racing_focus(k, new, stamp):
        if k == key and not hits:
            hits.append(1)
            db.set_setting(key, json.dumps({**json.loads(db.get_setting(key)), "focus": "invest"}))
        return real(k, new, stamp)
    monkeypatch.setattr(db, "_swap", racing_focus)
    assert w["client"].put("/me/onboarding", headers=PRO, json={"welcome": True}).status_code == 200
    got = json.loads(db.get_setting(key))
    assert got["focus"] == "invest" and got["level"] == "new" and got["onboarding"]["welcome"]


def test_checked_token_is_trusted_for_15_seconds(w):
    assert w["client"].get("/me", headers=PRO).status_code == 200
    until = auth._cache["pro-token"][0]
    assert auth.TOKEN_TTL == 15 and until - time.time() <= 15


def test_profile_read_begun_before_an_update_is_not_kept(w, monkeypatch):
    real = db.get_profile

    def slow(uid, email=None):
        row = real(uid, email)                    # the old row, read before the update below commits
        db.update_profile(uid, plan="basic")
        return row
    monkeypatch.setattr(db, "get_profile", slow)
    db._profiles.pop(ME, None)
    db.cached_profile(ME)
    assert ME not in db._profiles
    monkeypatch.setattr(db, "get_profile", real)
    assert db.cached_profile(ME)["plan"] == "basic" and ME in db._profiles


def test_first_sign_in_never_overwrites_a_row_made_meanwhile(w, monkeypatch):
    fake = w["db"]
    fake.tables["profiles"].append({"id": "u-new", "email": "new@example.com", "plan": "pro"})
    missed = []

    class Racing:                                 # the first read misses the row another request is making
        def table(self, name):
            q = fake.table(name)
            if name == "profiles" and not missed:
                missed.append(1)
                q.execute = lambda: SimpleNamespace(data=[], count=None)
            return q
    monkeypatch.setattr(db, "sb", lambda: Racing())
    assert db.get_profile("u-new", "new@example.com")["plan"] == "pro"
    assert next(r for r in fake.tables["profiles"] if r["id"] == "u-new")["plan"] == "pro"
    assert db.get_profile("u-brand-new", "b@example.com")["plan"] == "free"


def test_alerts_can_be_turned_off_or_cleared_on_any_plan(w, monkeypatch):
    saved = []
    monkeypatch.setattr(db, "update_profile", lambda uid, **f: saved.append(f))
    prof = {"id": ME, "_plan": "free", "plan": "free", "telegram_chat_id": "123", "alert_email": "a@b.co"}
    main.app.dependency_overrides[main.current_profile] = lambda: prof
    c = w["client"]
    r = c.put("/me/alerts", json={"alerts_enabled": False, "telegram_chat_id": "", "alert_email": "a@b.co", "daily_report": False})
    assert r.status_code == 200, r.text
    assert saved[-1]["telegram_chat_id"] is None and saved[-1]["alerts_enabled"] is False
    assert json.loads(db.get_setting(daily_report.PREFS + ME))["daily_report"] is False
    assert c.put("/me/alerts", json={"alerts_enabled": False, "alert_email": ""}).status_code == 200
    # anything that adds or turns on still needs the plan
    assert c.put("/me/alerts", json={"alerts_enabled": False, "telegram_chat_id": "999"}).status_code == 402
    assert c.put("/me/alerts", json={"alerts_enabled": False, "daily_report": True}).status_code == 402
    assert c.put("/me/alerts", json={"alerts_enabled": True}).status_code == 402
