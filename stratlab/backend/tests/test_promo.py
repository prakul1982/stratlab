"""The launch offer: the admin opens every feature to everyone for some days, then plans apply again."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import db, main, plans
from app.config import settings


@pytest.fixture
def store(monkeypatch):
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "delete_setting", lambda k: kv.pop(k, None))
    plans._promo.update(read_at=0.0, until=None)
    yield kv
    plans._promo.update(read_at=0.0, until=None)


def test_offer_gives_pro_then_ends(store, monkeypatch):
    free = {"id": "u1", "plan": "free"}
    assert plans.access_plan(free) == "free"
    until = plans.set_promo(10)
    assert timedelta(days=9, hours=23) < until - datetime.now(timezone.utc) <= timedelta(days=10)
    assert plans.access_plan(free) == "pro" and plans.effective_plan(free) == "free"   # what they pay for is unchanged
    assert not plans.promo_active(now=until + timedelta(seconds=1))                   # over by itself at the end
    plans.set_promo(None)
    assert plans.access_plan(free) == "free" and "promo:free_until" not in store


def test_admin_controls_and_me(store, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@x")
    boss = {"id": "boss", "plan": "free", "_plan": "free", "_paid_plan": "free", "email": "boss@x", "_email_verified": True}
    main.app.dependency_overrides[main.current_profile] = lambda: boss
    c = TestClient(main.app)
    try:
        assert c.post("/admin/promo", json={"days": 0}).status_code == 422
        r = c.post("/admin/promo", json={"days": 10}).json()
        assert r["until"] and plans.promo_active()
        assert c.delete("/admin/promo").json() == {"until": None} and not plans.promo_active()
        main.app.dependency_overrides[main.current_profile] = lambda: {**boss, "_email_verified": False}
        assert c.post("/admin/promo", json={"days": 10}).status_code == 403
    finally:
        main.app.dependency_overrides.clear()


def test_can_still_subscribe_during_the_offer(monkeypatch):
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u", "plan": "free", "_plan": "pro", "_paid_plan": "free"}
    monkeypatch.setattr(main.billing, "create_subscription", lambda p, plan, period: {"subscription_id": "sub_1"})
    try:
        assert TestClient(main.app).post("/billing/subscribe", json={"plan": "pro"}).json() == {"subscription_id": "sub_1"}
    finally:
        main.app.dependency_overrides.clear()
