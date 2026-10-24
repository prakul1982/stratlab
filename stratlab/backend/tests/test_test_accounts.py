"""24 Oct 2026 (owner: "add more accounts"): an admin makes test accounts on "+" aliases of their own address, each on a
plan, and gets a one-time sign-in link at that alias (their own inbox), so several reviewers can sign in at once."""
from types import SimpleNamespace as NS

from tests.test_admin_alerts import _smtp


def test_an_admin_makes_test_accounts_on_their_own_alias(monkeypatch):
    from app import admin, db, main
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        made, asked, plans, store = [], [], [], {}
        real = db.sb()

        def create_user(p):
            if p["email"] in made:
                raise RuntimeError("A user with this email address has already been registered")
            made.append(p["email"])

        def generate_link(p):
            asked.append(p)
            return NS(properties=NS(action_link="https://auth.example.com/verify?token=t9&type=magiclink"), user=NS(id=f"u-{p['email']}"))
        monkeypatch.setattr(db, "sb", lambda: NS(auth=NS(admin=NS(create_user=create_user, generate_link=generate_link),
                                                         get_user=real.auth.get_user), table=real.table))
        monkeypatch.setattr(db, "get_profile", lambda uid, email=None: {"id": uid, "email": email})
        monkeypatch.setattr(admin, "set_plan", lambda uid, plan, days: plans.append((uid, plan, days)) or {})
        monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
        monkeypatch.setattr(db, "update_setting", lambda k, fn, tries=10: store.__setitem__(k, fn(store.get(k))) or store[k])
        sent = _smtp(monkeypatch)
        h = W.headers("admin-token")
        r = w["client"].post("/admin/test-account", headers=h, json={"label": "basic-1", "plan": "basic"}).json()
        assert r["plan"] == "basic" and made == ["owner+sl-basic-1@example.com"]
        assert asked[0] == {"type": "magiclink", "email": "owner+sl-basic-1@example.com", "options": asked[0]["options"]}
        assert plans == [("u-owner+sl-basic-1@example.com", "basic", None)]
        assert sent[-1][0] == "owner+sl-basic-1@example.com" and "token=t9" in str(sent[-1])
        # asked again: the account is reused, the link is new
        assert w["client"].post("/admin/test-account", headers=h, json={"label": "basic-1", "plan": "pro"}).status_code == 200
        assert made == ["owner+sl-basic-1@example.com"] and plans[-1][1] == "pro"
        assert w["client"].get("/admin/test-accounts", headers=h).json()["accounts"]["u-owner+sl-basic-1@example.com"]["plan"] == "pro"
        # only an admin, only sane labels and plans, and never more than the cap
        assert w["client"].post("/admin/test-account", headers=W.headers("pro-token"), json={"label": "x"}).status_code == 403
        assert w["client"].post("/admin/test-account", headers=h, json={"label": "Bad Label!"}).status_code == 422
        assert w["client"].post("/admin/test-account", headers=h, json={"label": "x", "plan": "gold"}).status_code == 400
        for i in range(main.MAX_TEST_ACCOUNTS - 1):
            assert w["client"].post("/admin/test-account", headers=h, json={"label": f"t{i}"}).status_code == 200
        assert w["client"].post("/admin/test-account", headers=h, json={"label": "one-more"}).status_code == 409
    finally:
        w["close"]()


def test_the_alias_keeps_the_admins_own_address():
    from app import main
    assert main.test_account_email("prakul@gmail.com", "free") == "prakul+sl-free@gmail.com"
    assert main.test_account_email("me+work@x.com", "pro-2") == "me+sl-pro-2@x.com"
