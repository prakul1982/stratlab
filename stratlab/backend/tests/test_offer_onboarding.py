"""One answer to "what can people buy and use today" (plans.offer_state), shared by the landing page (/pricing), Plans
and the app (/me); prices in a currency still charged in rupees shown at the rupee price's rate; the first-run guide
kept on the account; the public company lookup behind "Sign in to see …"; assistant keys need a name."""
from datetime import datetime, timedelta, timezone

import pytest

from app import plans, pricing
from app.config import settings
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    plans._promo.update(read_at=0.0, until=None)
    yield built
    plans._promo.update(read_at=0.0, until=None)
    built["close"]()


def _payments(monkeypatch, on: bool):
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_PLAN_BASIC", "RAZORPAY_PLAN_PRO"):
        monkeypatch.setattr(settings, k, "plan_x" if on else "")


def test_offer_modes(w, monkeypatch):
    _payments(monkeypatch, False)
    o = plans.offer_state()
    assert o["mode"] == "early" and not o["payments"] and o["promo_until"] is None
    # payments off changes nothing about what Free includes: its own limits, exactly as Pricing lists them
    for k in plans.LIMIT_KEYS:
        assert o["free_now"][k] == plans.PLANS["free"][k], k
    assert o["free_trial_days"] == plans.PLANS["free"]["live_trial_days"]

    _payments(monkeypatch, True)
    o = plans.offer_state()
    assert o["mode"] == "paid" and o["payments"]
    assert o["free_now"]["deepdives_per_month"] == plans.PLANS["free"]["deepdives_per_month"]   # Free's own limits

    until = datetime.now(timezone.utc) + timedelta(days=5)
    plans._promo.update(read_at=1e18, until=until)              # the launch offer is on (no database read)
    o = plans.offer_state()
    assert o["mode"] == "promo" and o["promo_until"] == until.isoformat()
    assert plans.offer_state(now=until + timedelta(seconds=1))["mode"] == "paid"     # over by itself


def test_pricing_and_me_carry_the_same_offer(w, monkeypatch):
    _payments(monkeypatch, False)
    c = w["client"]
    pub = c.get("/pricing").json()
    me = c.get("/me", headers=world.headers("free-token")).json()
    assert pub["offer"] == me["offer"] and pub["offer"]["mode"] == "early"
    assert me["offer"]["payments"] is me["billing_enabled"]


def test_dollar_visitors_see_the_admin_tables_dollar_prices(monkeypatch):
    """$8 and $20, the owner's dollar prices, whatever today's rate (no "about $23" conversion)."""
    saved = {"fx-rates": '{"rates": {"USD": 88.0, "GBP": 118.0}}'}
    pricing.forget()
    pricing._rates_cache[0] = 0.0
    monkeypatch.setattr(pricing.db, "get_setting", lambda k: saved.get(k))
    monkeypatch.setattr(pricing.db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    try:
        pub = pricing.public()["currencies"]
        assert (pub["USD"]["basic"], pub["USD"]["pro"], pub["USD"]["charged_in"]) == (8, 20, "INR")
        assert (pub["INR"]["basic"], pub["INR"]["pro"]) == (699, 1999)
        assert "approx" not in pub["USD"] and "rate" not in pub["USD"]
        pricing.save({"USD": {"basic": 9}})                                   # the admin's table is the truth
        assert pricing.public()["currencies"]["USD"]["basic"] == 9
    finally:
        pricing.forget()
        pricing._rates_cache[0] = 0.0


def test_onboarding_is_kept_on_the_account(w):
    c = w["client"]
    h = world.headers("load-11")
    assert c.get("/me", headers=h).json()["onboarding"] == {"welcome": None, "tour": None}
    r = c.put("/me/onboarding", headers=h, json={"welcome": True})
    assert r.status_code == 200 and r.json()["onboarding"]["welcome"] and r.json()["onboarding"]["tour"] is None
    first = r.json()["onboarding"]["welcome"]
    assert c.put("/me/onboarding", headers=h, json={"tour": "skipped"}).json()["onboarding"]["tour"] == "skipped"
    assert c.put("/me/onboarding", headers=h, json={"tour": "done"}).json()["onboarding"]["tour"] == "done"
    # only moves forward: done stays done, and the welcome keeps its first time
    again = c.put("/me/onboarding", headers=h, json={"welcome": True, "tour": "skipped"}).json()["onboarding"]
    assert again == {"welcome": first, "tour": "done"}
    assert c.put("/me/onboarding", headers=h, json={"tour": "maybe"}).status_code == 422
    # the experience answers live beside it, untouched, and /me on any device sees the same
    assert c.put("/me/prefs", headers=h, json={"level": "new"}).json() == {"prefs": {"level": "new", "focus": None, "space": None}}
    assert c.get("/me", headers=h).json()["onboarding"] == {"welcome": first, "tour": "done"}
    assert c.put("/me/onboarding", json={"welcome": True}).status_code == 401                   # signed in only


def test_public_company_lookup(w):
    from app import stock_pages
    c = w["client"]
    r = c.get("/public/company/IN/reliance")                     # on StratLab's own lists, with no name stored yet
    assert r.status_code == 200
    assert r.json() == {"region": "IN", "symbol": "RELIANCE", "name": "RELIANCE", "page": "/stocks/in/RELIANCE"}
    # the link the "Sign in to see …" screen offers is a route that answers 200 as written (no redirect on the way, so the
    # site's host forwarding /stocks/* to the API serves it), whatever case the visitor typed
    page = c.get(r.json()["page"], follow_redirects=False)
    assert page.status_code == 200 and "RELIANCE" in page.text
    assert c.get("/stocks/IN/reliance", follow_redirects=False).status_code == 301   # the other spellings redirect to that one address
    stock_pages.save_list("IN", [{"symbol": "RELIANCE", "name": "Reliance Industries Ltd"}] + [{"symbol": f"X{i}"} for i in range(100)])
    assert c.get("/public/company/IN/RELIANCE").json()["name"] == "Reliance Industries Ltd"
    assert c.get("/public/company/IN/NOSUCHCO").status_code == 404
    assert c.get("/public/company/XX/RELIANCE").status_code == 404
    assert c.get("/public/company/IN/" + "A" * 40).status_code == 404


def test_the_policies_name_the_seller_once_it_is_set(w):
    from app import invoices
    c = w["client"]
    assert c.get("/public/business").json() == {"legal_name": "", "address": "", "email": ""}
    invoices.save_seller({"legal_name": "Example Labs LLP", "address": "1 Road, Pune", "state": "27", "email": "hello@example.com", "pan": "X" * 10})
    assert c.get("/public/business").json() == {"legal_name": "Example Labs LLP", "address": "1 Road, Pune", "email": "hello@example.com"}


def test_an_assistant_key_needs_a_name(w, monkeypatch):
    c = w["client"]
    h = world.headers("pro-token")
    for name in ("", "   ", "<>"):
        r = c.post("/me/assistant/keys", headers=h, json={"name": name})
        assert r.status_code == 422 and r.json()["detail"]["code"] == "name_needed", name
    assert c.post("/me/assistant/keys", headers=h, json={"name": "Claude on my laptop"}).status_code == 200
