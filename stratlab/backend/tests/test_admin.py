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
    def eq(self, col, v): return FakeQuery([r for r in self.rows if r.get(col) == v])
    def in_(self, col, vs): return FakeQuery([r for r in self.rows if r.get(col) in vs])
    def order(self, *a, **k): return self
    def limit(self, *a): return self

    def ilike(self, col, pat):
        return FakeQuery([r for r in self.rows if pat.strip("%") in (r.get(col) or "")])

    def execute(self):
        return type("R", (), {"data": self.rows, "count": len(self.rows)})()


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


def test_admin_emails_are_case_insensitive(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", " Owner@X.com ,")
    assert admin.is_admin({"email": "owner@x.com", "_email_verified": True})
    assert not admin.is_admin({"email": "owner@x.com"})            # an unverified address is never trusted
    assert not admin.is_admin({"email": "someone@x.com", "_email_verified": True})
    assert not admin.is_admin({"email": None, "_email_verified": True})
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "")
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
    monkeypatch.setattr(db, "sb", lambda: FakeSB())              # u1 has no subscription
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


def test_counts_page_past_the_servers_read_cap(monkeypatch):
    rows = [{"id": f"{i:05d}", "plan": "free", "plan_status": None, "current_period_end": None,
             "created_at": NOW.isoformat(), "razorpay_subscription_id": None} for i in range(2500)]

    class Paged(FakeQuery):
        def __init__(self, rows):
            super().__init__(rows)
            self.after, self.n = "", None
        def gt(self, c, v): self.after = v; return self
        def limit(self, n): self.n = min(n, 1000); return self      # the server never returns more than 1000
        def execute(self):
            got = [r for r in self.rows if r["id"] > self.after][:self.n or 1000]
            return type("R", (), {"data": got, "count": len(self.rows)})()
        def eq(self, *a): return self

    monkeypatch.setattr(db, "sb", lambda: type("S", (), {"table": lambda s, n: Paged(rows)})())
    st = admin.stats(main.month_start_iso())
    assert st["users"] == 2500 and st["plans"]["free"] == 2500 and st["signups_today"] == 2500
    assert st["experiments_month"] == 2500                          # counted by the database, not read back


def test_a_plan_given_by_hand_after_a_cancelled_subscription_is_not_paying():
    sub = {"id": "u9", "plan": "pro", "plan_status": "active", "razorpay_subscription_id": "sub_old"}
    assert admin._paying(sub)
    assert not admin._paying(sub, {"u9"})                          # given by hand (admin.granted)
    assert not admin._paying({**sub, "plan_status": "cancelled"})


def test_set_plan_records_that_it_was_given_by_hand(monkeypatch):
    monkeypatch.setattr(db, "sb", lambda: FakeSB())              # u1 has no subscription
    saved, store = {}, {}
    monkeypatch.setattr(db, "update_profile", lambda uid, **f: saved.update(f) or {"id": uid, **f})
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    admin.set_plan("u1", "pro", 30)
    assert "plan_source" not in saved and admin.granted() == {"u1"}      # no new profile column needed
    admin.set_plan("u1", "free", None)
    assert admin.granted() == set()


def test_users_read_usage_only_for_the_listed_users(client, monkeypatch):
    c, _ = client
    asked = []
    real = FakeQuery.in_
    monkeypatch.setattr(FakeQuery, "in_", lambda self, col, vs: asked.append((col, list(vs))) or real(self, col, vs))
    c.get("/admin/users")
    assert ("user_id", ["u1", "u2"]) in asked                       # not every event of the month


def test_a_user_paying_through_razorpay_keeps_their_plan_until_it_is_cancelled(monkeypatch):
    rows = {"u2": {"id": "u2", "plan_status": "active", "razorpay_subscription_id": "sub_1"},
            "u3": {"id": "u3", "plan_status": "cancelled", "razorpay_subscription_id": "sub_2"}}
    monkeypatch.setattr(db, "sb", lambda: type("S", (), {"table": lambda s, n: FakeQuery(list(rows.values()))})())
    saved = []
    monkeypatch.setattr(db, "update_profile", lambda uid, **f: saved.append(uid) or {"id": uid, **f})
    monkeypatch.setattr(admin, "granted", lambda: set())
    with pytest.raises(admin.HTTPException) as e:
        admin.set_plan("u2", "pro", 30)
    assert e.value.status_code == 409 and e.value.detail["message"] == (
        "This user pays through Razorpay. Cancel their subscription in Razorpay first, then change the plan.")
    assert saved == []
    monkeypatch.setattr(admin, "mark_granted", lambda uid, on: None)
    admin.set_plan("u3", "pro", 30)                                  # the subscription has ended: the plan can change
    assert saved == ["u3"]


def test_stats_count_research_ai_reads_apart_from_builds(monkeypatch):
    monkeypatch.setattr(db, "sb", lambda: FakeSB())
    st = admin.stats(main.month_start_iso())
    assert "ai_reads_month" in st and st["ai_month"] == 1
