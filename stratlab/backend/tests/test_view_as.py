"""The site owner's "View as Free / Basic / Pro": the X-View-As header changes what the plan gates and limits say for the
owner alone. It never touches the stored plan, billing, other accounts or admin access, and it is the launch offer's
equal: viewing as a plan bypasses the offer so the locks are visible."""
from datetime import datetime, timedelta, timezone

import pytest

from app import db, plans
from app.config import settings
from app.plans import PLANS
from tests import world

OWNER, PRO, FREE = "admin-token", "pro-token", "free-token"
LOCKED_ON_FREE = ("post", "/research/scan", {"region": "IN", "set": "nifty50", "scan": "st_s2"})      # Basic: scans
LOCKED_ON_BASIC = ("get", "/money/us-tax/schedule-fa.csv?cy=2025", None)                              # Pro: US tax


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    plans._promo.update(read_at=1e18, until=None)
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_PLAN_BASIC", "RAZORPAY_PLAN_PRO"):
        monkeypatch.setattr(settings, k, "")
    yield built
    plans._promo.update(read_at=0.0, until=None)
    built["close"]()


def promo_on():
    plans._promo.update(read_at=1e18, until=datetime.now(timezone.utc) + timedelta(days=3))


def call(c, token, route, view=None):
    method, path, body = route
    h = world.headers(token) | ({"X-View-As": view} if view is not None else {})
    return c.request(method.upper(), path, headers=h, **({"json": body} if body is not None else {}))


def me(c, token, view=None):
    h = world.headers(token) | ({"X-View-As": view} if view is not None else {})
    r = c.get("/me", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def stored(uid="u-admin"):
    return {k: v for k, v in db.get_profile(uid).items() if k not in ("updated_at",)}


# ---------- who can set it ----------
def test_only_the_owner_can_set_it(w):
    c = w["client"]
    for token in (PRO, FREE, "email-signup-admin-token"):          # the last: the owner's address, but not proven by Google
        r = c.put("/admin/view-as", headers=world.headers(token), json={"plan": "free"})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "not_admin"
    assert c.put("/admin/view-as", json={"plan": "free"}).status_code == 401
    for plan in ("free", "basic", "pro", None):
        r = c.put("/admin/view-as", headers=world.headers(OWNER), json={"plan": plan})
        assert r.status_code == 200 and r.json() == {"view_as": plan}
    assert c.put("/admin/view-as", headers=world.headers(OWNER), json={"plan": "enterprise"}).status_code == 422


def test_the_header_does_nothing_for_anyone_else(w):
    c = w["client"]
    for token, real in ((PRO, "pro"), (FREE, "free"), ("email-signup-admin-token", "free")):
        for view in ("free", "basic", "pro"):
            m = me(c, token, view)
            assert (m["plan"], m["view_as"], m["is_admin"]) == (real, None, False), (token, view)
    # and a non-owner cannot use it to look at (or use) a paid feature
    assert call(c, FREE, LOCKED_ON_FREE, view="pro").status_code == 402
    promo_on()
    assert me(c, FREE, "free")["plan"] == "pro" and me(c, FREE, "free")["view_as"] is None     # the offer still applies to them


def test_a_junk_value_is_off(w):
    c = w["client"]
    for junk in ("", "root", "PRO ; drop", "enterprise", "null", "off"):
        m = me(c, OWNER, junk)
        assert (m["plan"], m["view_as"]) == ("pro", None), junk
    assert me(c, OWNER, " Basic ")["view_as"] == "basic"            # the case and stray spaces don't matter


# ---------- gating follows it ----------
def test_gating_follows_the_chosen_plan(w):
    c = w["client"]
    assert call(c, OWNER, LOCKED_ON_FREE).status_code != 402            # the owner has everything
    assert call(c, OWNER, LOCKED_ON_BASIC).status_code != 402
    r = call(c, OWNER, LOCKED_ON_FREE, view="free")
    assert r.status_code == 402 and r.json()["detail"]["code"] == "upgrade_required"
    assert call(c, OWNER, LOCKED_ON_BASIC, view="free").status_code == 402
    assert call(c, OWNER, LOCKED_ON_FREE, view="basic").status_code != 402     # Basic has scans...
    assert call(c, OWNER, LOCKED_ON_BASIC, view="basic").status_code == 402    # ...not US tax
    assert call(c, OWNER, LOCKED_ON_BASIC, view="pro").status_code != 402
    assert call(c, OWNER, LOCKED_ON_FREE).status_code != 402                   # off again: nothing is remembered on the server
    for view in ("free", "basic", "pro"):
        m = me(c, OWNER, view)
        assert (m["plan"], m["view_as"], m["paid_plan"], m["plan_info"]["name"]) == (view, view, view, PLANS[view]["name"])
        assert m["is_admin"] is True


def test_usage_limits_show_as_that_plans(w):
    c = w["client"]
    for view in ("free", "basic", "pro"):
        u = me(c, OWNER, view)["usage"]
        assert (u["deepdive_limit"], u["deck_limit"], u["backtests_limit"], u["ai_limit"]) == (
            PLANS[view]["deepdives_per_month"], PLANS[view]["decks_per_month"], PLANS[view]["backtests_per_month"], PLANS[view]["ai_builds_per_month"])
        assert (u["deepdive_plan_limit"], u["deck_plan_limit"]) == (PLANS[view]["deepdives_per_month"], PLANS[view]["decks_per_month"])
    m = me(c, OWNER, "free")
    assert (m["live_limit"], m["plan_info"]["holdings"], m["plan_info"]["screens"]) == (1, 30, 2)
    assert m["trial"] is not None                                          # Free's paper-trading trial shows


def test_the_limit_itself_is_enforced_as_that_plan(w):
    """The deep dive's monthly count stops at the viewed plan's limit (Free: 2), not the owner's own (unlimited)."""
    c = w["client"]
    for n in range(2):
        db.add_usage("u-admin", "deepdive")
    from app import main
    owner = main.current_profile("Bearer " + OWNER, "free")
    assert owner["_plan"] == "free" and owner["_view_as"] == "free"
    with pytest.raises(Exception) as e:
        main.use_deep(owner, "deepdive", "NEWCO", "IN")
    assert getattr(e.value, "status_code", None) == 402 and "deep dive" in str(e.value.detail["message"])
    off = main.current_profile("Bearer " + OWNER, None)
    main.use_deep(off, "deepdive", "NEWCO", "IN")                          # unlimited when it is off


# ---------- the launch offer ----------
def test_viewing_as_a_plan_bypasses_the_launch_offer(w):
    c = w["client"]
    promo_on()
    assert me(c, FREE)["plan"] == "pro" and me(c, FREE)["promo"] is not None           # everyone is Pro during the offer
    assert call(c, FREE, LOCKED_ON_FREE).status_code != 402
    m = me(c, OWNER, "free")
    assert m["plan"] == "free" and m["promo"] is None and m["usage"]["lifted_by"] is None and m["offer"]["mode"] != "promo"
    assert m["offer"]["promo_until"] is None
    assert call(c, OWNER, LOCKED_ON_FREE, view="free").status_code == 402
    assert call(c, OWNER, LOCKED_ON_BASIC, view="basic").status_code == 402
    off = me(c, OWNER)
    assert off["plan"] == "pro" and off["promo"] is not None and off["offer"]["mode"] == "promo"       # off: as before
    assert plans.promo_active()                                                         # the offer itself was never touched


def test_viewing_as_a_plan_bypasses_free_basic_time(w):
    c = w["client"]
    plans.add_free_basic(db.get_profile("u-free"), 30)                       # invite-earned Basic for a Free user
    assert me(c, FREE)["plan"] == "basic"
    fresh = {**db.get_profile("u-free"), "_view_as": "free"}
    assert plans.access_plan(fresh) == "free"
    assert plans.access_plan({**db.get_profile("u-free")}) == "basic"


# ---------- nothing real changes ----------
def test_billing_and_the_stored_plan_are_untouched(w, monkeypatch):
    c = w["client"]
    before = stored()
    assert before["plan"] == "pro"
    for view in ("free", "basic", "pro"):
        me(c, OWNER, view)
        call(c, OWNER, LOCKED_ON_FREE, view=view)
        call(c, OWNER, LOCKED_ON_BASIC, view=view)
    assert stored() == before                                                 # no plan, status, period or Razorpay field moved
    # the profile the rest of the app reads still carries the real plan beside the viewed one
    from app import main
    p = main.current_profile("Bearer " + OWNER, "free")
    assert (p["plan"], p["_paid_plan"], p["_plan"]) == ("pro", plans.effective_plan(before), "free")
    # /me shows the viewed plan's billing, not the owner's own
    m = me(c, OWNER, "free")
    assert m["billing"] == {"subscribed_plan": None, "status": None, "renews_or_ends": None, "cancel_at_period_end": False, "given_by_owner": False}
    # and no billing action can run while viewing
    started = []
    monkeypatch.setattr(main.billing, "create_subscription", lambda *a, **k: started.append(a) or {"subscription_id": "sub_1"})
    monkeypatch.setattr(main.billing, "cancel", lambda p: started.append(p))
    monkeypatch.setattr(main.billing, "verify_checkout", lambda *a: started.append(a))
    h = world.headers(OWNER) | {"X-View-As": "free"}
    for path, body in (("/billing/subscribe", {"plan": "pro"}), ("/billing/cancel", None),
                       ("/billing/verify", {"razorpay_payment_id": "p", "razorpay_subscription_id": "s", "razorpay_signature": "x"})):
        r = c.post(path, headers=h, **({"json": body} if body else {}))
        assert r.status_code == 409 and r.json()["detail"]["code"] == "view_as_on", path
    assert started == []
    assert stored() == before
    # off again: the billing calls are the owner's as before
    assert c.post("/billing/subscribe", headers=world.headers(OWNER), json={"plan": "basic"}).json() == {"subscription_id": "sub_1"}


def test_other_accounts_never_see_it(w):
    c = w["client"]
    assert me(c, OWNER, "free")["plan"] == "free"
    for token, real in ((PRO, "pro"), (FREE, "free"), ("basic-token", "basic")):
        m = me(c, token)
        assert (m["plan"], m["view_as"]) == (real, None)
    assert me(c, OWNER)["plan"] == "pro"                                       # the owner's own next request is clean


# ---------- admin keeps working ----------
@pytest.mark.parametrize("view", ["free", "basic", "pro"])
def test_admin_pages_stay_reachable(w, view):
    c = w["client"]
    h = world.headers(OWNER) | {"X-View-As": view}
    for path in ("/admin/overview", "/admin/users", "/admin/prices"):
        assert c.get(path, headers=h).status_code == 200, (view, path)
    assert me(c, OWNER, view)["is_admin"] is True
    # an admin action still works while viewing, and does what it did before
    assert c.put("/admin/view-as", headers=h, json={"plan": None}).status_code == 200
    r = c.post("/admin/promo", headers=h, json={"days": 2})
    assert r.status_code == 200 and plans.promo_active()
    assert c.delete("/admin/promo", headers=h).json() == {"until": None}
