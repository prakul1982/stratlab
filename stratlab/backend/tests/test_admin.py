from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import admin, db, main
from app.config import settings
from app.plans import effective_plan

NOW = datetime.now(timezone.utc)
PROFILES = [
    {"id": "u1", "email": "owner@x.com", "plan": "free", "plan_status": None, "current_period_end": None,
     "razorpay_subscription_id": None, "created_at": (NOW - timedelta(days=30)).isoformat()},
    {"id": "u2", "email": "trader@x.com", "plan": "pro", "plan_status": "active",
     "current_period_end": (NOW + timedelta(days=10)).isoformat(), "razorpay_subscription_id": None,
     "created_at": (NOW - timedelta(days=2)).isoformat()},
]
USAGE = [{"user_id": "u2", "kind": "backtest"}, {"user_id": "u2", "kind": "backtest"}, {"user_id": "u2", "kind": "ai"}]


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def select(self, *a, **k): return self
    def gte(self, *a): return self
    def order(self, *a, **k): return self
    def limit(self, *a): return self

    def ilike(self, col, pat):
        return FakeQuery([r for r in self.rows if pat.strip("%") in (r.get(col) or "")])

    def execute(self):
        return type("R", (), {"data": self.rows})()


class FakeSB:
    def table(self, name):
        return FakeQuery(PROFILES if name == "profiles" else USAGE)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(db, "sb", lambda: FakeSB())
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "Owner@x.com, other@x.com")
    who = {"profile": dict(PROFILES[0], _plan="free", _email_verified=True)}
    main.app.dependency_overrides[main.current_profile] = lambda: who["profile"]
    yield TestClient(main.app), who
    main.app.dependency_overrides.clear()


def test_admin_emails_are_case_insensitive():
    settings.ADMIN_EMAILS = " Owner@X.com ,"
    assert admin.is_admin({"email": "owner@x.com", "_email_verified": True})
    assert not admin.is_admin({"email": "owner@x.com"})            # an unverified address is never trusted
    assert not admin.is_admin({"email": "someone@x.com", "_email_verified": True})
    assert not admin.is_admin({"email": None, "_email_verified": True})
    settings.ADMIN_EMAILS = ""
    assert not admin.is_admin({"email": "", "_email_verified": True})


def test_non_admin_gets_403(client):
    c, who = client
    who["profile"] = dict(PROFILES[1], _plan="pro")
    for method, path in [("get", "/admin/overview"), ("get", "/admin/users"), ("post", "/admin/users/u1/plan"),
                         ("get", "/admin/sessions"), ("post", "/admin/ai/test"), ("post", "/admin/kite/login-url")]:
        r = c.post(path, json={"plan": "pro"}) if method == "post" else c.get(path)
        assert r.status_code == 403, path


def test_users_and_stats(client):
    c, _ = client
    users = c.get("/admin/users").json()
    assert [u["email"] for u in users] == ["owner@x.com", "trader@x.com"]
    trader = users[1]
    assert trader["plan"] == "pro" and trader["experiments"] == 2 and trader["ai_builds"] == 1
    assert [u["email"] for u in c.get("/admin/users?q=trader").json()] == ["trader@x.com"]
    stats = admin.stats(main.month_start_iso())
    assert stats["users"] == 2 and stats["plans"]["pro"] == 1 and stats["new_7d"] == 1
    assert stats["experiments_month"] == 2 and stats["ai_month"] == 1


def test_me_says_who_is_admin(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(db, "count_usage", lambda *a: 0)
    assert c.get("/me").json()["is_admin"] is True


def test_set_plan_grants_and_clears(monkeypatch):
    saved = {}
    monkeypatch.setattr(db, "update_profile", lambda uid, **f: saved.update(f) or {"id": uid, **f})
    admin.set_plan("u1", "basic", 30)
    assert saved["plan"] == "basic" and saved["plan_status"] == "active"
    assert effective_plan(saved) == "basic"
    until = datetime.fromisoformat(saved["current_period_end"])
    assert timedelta(days=29) < until - NOW < timedelta(days=31)
    admin.set_plan("u1", "pro", None)
    assert saved["current_period_end"] is None and effective_plan(saved) == "pro"
    admin.set_plan("u1", "free", None)
    assert saved["plan"] == "free" and effective_plan(saved) == "free"


def test_plan_request_is_validated(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(db, "update_profile", lambda uid, **f: {"id": uid, "email": "x", **f})
    assert c.post("/admin/users/u2/plan", json={"plan": "gold"}).status_code == 422
    assert c.post("/admin/users/u2/plan", json={"plan": "pro", "days": 0}).status_code == 422
    assert c.post("/admin/users/u2/plan", json={"plan": "pro", "days": 30}).json() == {"ok": True}


def test_old_key_urls_are_gone_and_callback_needs_the_state(client):
    c, _ = client
    for method, path in [("get", "/admin/kite/login?key=x"), ("get", "/admin/status?key=x"), ("post", "/admin/kite/auto-login?key=x")]:
        assert getattr(c, method)(path).status_code in (404, 405), path
    main.kite.login_state = "good"
    r = c.get("/admin/kite/callback?status=success&request_token=t&state=<script>")
    assert r.status_code == 403 and "<script>" not in r.text
