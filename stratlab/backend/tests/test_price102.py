"""price102 (owner, 28 Nov: "all ok to do", the GTM plan's P1-P3): founding-member yearly prices until 31 Dec 2026 23:59 IST or the
first 100 paying customers, kept on renewal; one theme deck a month on Free, a PDF marked "Made with StratLab · stratlab.studio" with the
theme's public link; Basic at ₹2,499 a year for students the owner approves."""
import io
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import billing, db, offers, plans
from app.config import settings

IST = timezone(timedelta(hours=5, minutes=30))
DEADLINE = datetime(2026, 12, 31, 23, 59, tzinfo=IST)
IDS = {"founding_basic_year": "plan_FoundBasic1", "founding_pro_year": "plan_FoundPro1", "student_basic_year": "plan_StudentBasic1"}


@pytest.fixture
def store(monkeypatch):
    """Settings in a dict, payments on, the offer plans set and nobody paid yet."""
    rows: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: rows.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: rows.__setitem__(k, v))
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, page=1000: [(k, v) for k, v in sorted(rows.items()) if k.startswith(p)])
    for k, v in (("RAZORPAY_KEY_ID", "rzp_test_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "plan_B"), ("RAZORPAY_PLAN_PRO", "plan_P"),
                 ("RAZORPAY_PLAN_BASIC_YEAR", "plan_BY"), ("RAZORPAY_PLAN_PRO_YEAR", "plan_PY")):
        monkeypatch.setattr(settings, k, v)
    rows[offers.PLANS_KEY] = json.dumps(IDS)
    paying = {"ids": set()}
    monkeypatch.setattr(offers, "_paying_ids", lambda: set(paying["ids"]))
    offers.forget()
    yield SimpleNamespace(rows=rows, paying=paying)
    offers.forget()


def _seats(store, n):
    store.paying["ids"] = {f"u{i}" for i in range(n)}
    offers.forget()


# ---------- P1: the founding offer's window ----------
def test_the_founding_offer_ends_exactly_at_the_deadline(store):
    assert offers.FOUNDING_UNTIL == DEADLINE and offers.FOUNDING_UNTIL.astimezone(timezone.utc).isoformat() == "2026-12-31T18:29:00+00:00"
    assert offers.founding_open(DEADLINE - timedelta(microseconds=1))
    assert not offers.founding_open(DEADLINE) and offers.closed_why(DEADLINE) == "date"
    assert not offers.founding_open(DEADLINE + timedelta(days=1))
    # what the pages are told while it runs, and nothing after
    pub = offers.founding_public(DEADLINE - timedelta(minutes=1))
    assert pub == {"open": True, "until": "2026-12-31T18:29:00+00:00", "seats": 100, "prices": {"basic": 4999, "pro": 14999},
                   "was": {"basic": 6999, "pro": 19999}}
    assert offers.founding_public(DEADLINE) is None
    assert plans.offer_state(DEADLINE - timedelta(minutes=1))["founding"] == pub
    assert plans.offer_state(DEADLINE)["founding"] is None


def test_the_founding_offer_closes_at_the_hundredth_paying_customer_and_stays_closed(store):
    now = DEADLINE - timedelta(days=20)
    _seats(store, 99)
    assert offers.founding_open(now) and offers.paying_customers() == 99
    _seats(store, 100)
    assert not offers.founding_open(now) and offers.closed_why(now) == "seats"
    assert json.loads(store.rows[offers.CLOSED_KEY])["why"] == "seats"
    _seats(store, 98)                                  # a refund later never opens it again
    assert offers.closed_why(now) == "seats" and offers.founding_public(now) is None


def test_the_founding_prices_are_never_shown_without_both_plans_or_payments(store, monkeypatch):
    now = DEADLINE - timedelta(days=5)
    store.rows[offers.PLANS_KEY] = json.dumps({"founding_basic_year": "plan_FoundBasic1"})
    offers.forget()
    assert not offers.founding_ready() and offers.founding_public(now) is None
    store.rows[offers.PLANS_KEY] = json.dumps(IDS)
    offers.forget()
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "")                # payments off: nothing can be bought
    assert offers.founding_public(now) is None and plans.offer_state(now)["founding"] is None
    # a Railway variable stands in for Admin's field
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_B")
    store.rows[offers.PLANS_KEY] = json.dumps({})
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC_YEAR_FOUNDING", "plan_EnvB")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO_YEAR_FOUNDING", "plan_EnvP")
    offers.forget()
    assert offers.founding_ready() and offers.plan_ids()["founding_pro_year"] == "plan_EnvP"


def test_paying_customers_are_everyone_who_paid_or_pays_now_less_test_accounts(monkeypatch):
    from app import admin
    rows = [("payment-sub:pay_1", json.dumps({"sub": "sub_1", "user": "a"})), ("payment-sub:pay_2", json.dumps({"sub": "sub_1", "user": "a"})),
            ("payment-sub:pay_3", json.dumps({"sub": "sub_2", "user": "t"})), ("payment-sub:pay_4", "not json")]
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, page=1000: rows if p == billing.PAYMENT_SUB else [])
    monkeypatch.setattr(admin, "granted", lambda: {"g"})
    monkeypatch.setattr(admin, "_paid_profiles", lambda: [
        {"id": "b", "razorpay_subscription_id": "sub_9", "plan_status": "active"},       # pays, its payment older than the record
        {"id": "g", "razorpay_subscription_id": "sub_8", "plan_status": "active"},       # given by hand: not paying
        {"id": "c", "razorpay_subscription_id": None, "plan_status": "active"}])
    monkeypatch.setattr(admin, "recorded_tests", lambda: {"t"})
    assert offers._paying_ids() == {"a", "b"}


# ---------- P1: checkout and renewals ----------
class FakeRazorpay:
    def __init__(self):
        self.made = []
        self.subscription = SimpleNamespace(create=self.create, fetch=lambda sid: {"id": sid, "status": "active"}, cancel=lambda *a: None)

    def create(self, body):
        self.made.append(body)
        return {"id": f"sub_{len(self.made)}", **body}


@pytest.fixture
def rz(monkeypatch):
    fake = FakeRazorpay()
    monkeypatch.setattr(billing, "_client", fake)
    monkeypatch.setattr(db, "update_profile", lambda uid, **kw: {"id": uid, **kw})
    return fake


def test_a_yearly_checkout_in_rupees_is_on_the_founding_plan_while_it_runs(store, rz, time_machine):
    time_machine.move_to(DEADLINE - timedelta(days=3))
    who = {"id": "u1", "email": "a@x.com"}
    out = billing.create_subscription(who, "basic", "year", "INR", expect_offer="founding")
    assert out["offer"] == "founding" and rz.made[-1]["plan_id"] == "plan_FoundBasic1"
    assert rz.made[-1]["notes"] == {"user_id": "u1", "plan": "basic", "period": "year", "currency": "INR", "offer": "founding"}
    billing.create_subscription(who, "pro", "year", "INR", expect_offer="founding")
    assert rz.made[-1]["plan_id"] == "plan_FoundPro1"
    # monthly prices are unchanged
    out = billing.create_subscription(who, "basic", "month", "INR", expect_offer=None)
    assert out["offer"] is None and rz.made[-1]["plan_id"] == "plan_B" and "offer" not in rz.made[-1]["notes"]
    # a currency charged on its own plans is not the rupee offer
    from app import pricing
    store.rows[pricing.KEY] = json.dumps({"USD": {"plan_basic_year": "plan_UB", "plan_pro_year": "plan_UP"}})
    pricing.forget()
    try:
        billing.create_subscription(who, "basic", "year", "USD")
        assert rz.made[-1]["plan_id"] == "plan_UB" and "offer" not in rz.made[-1]["notes"]
    finally:
        pricing.forget()


def test_a_page_showing_an_offer_that_ended_gets_no_checkout(store, rz, time_machine):
    time_machine.move_to(DEADLINE + timedelta(minutes=1))
    with pytest.raises(offers.OfferChanged):
        billing.create_subscription({"id": "u1"}, "basic", "year", "INR", expect_offer="founding")
    assert rz.made == []                                       # nothing made at Razorpay
    out = billing.create_subscription({"id": "u1"}, "basic", "year", "INR", expect_offer=None)
    assert out["offer"] is None and rz.made[-1]["plan_id"] == "plan_BY"
    # the other way too: a page that showed the standard price while the offer runs is told the price changed
    time_machine.move_to(DEADLINE - timedelta(days=1))
    with pytest.raises(offers.OfferChanged):
        billing.create_subscription({"id": "u1"}, "basic", "year", "INR", expect_offer=None)


def test_the_subscribe_route_answers_409_when_the_price_changed(store, rz, monkeypatch, time_machine):
    from fastapi.testclient import TestClient
    from app import main
    time_machine.move_to(DEADLINE + timedelta(hours=1))
    monkeypatch.setattr(main.product_analytics, "checkout", lambda *a, **k: None)
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "plan": "free", "_plan": "free", "_paid_plan": "free"}
    try:
        c = TestClient(main.app)
        r = c.post("/billing/subscribe", json={"plan": "basic", "period": "year", "currency": "INR", "offer": "founding"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "price_changed"
        assert "founding-member price has ended" in r.json()["detail"]["message"] and rz.made == []
        r = c.post("/billing/subscribe", json={"plan": "basic", "period": "year", "currency": "INR"})      # an older page: no offer said
        assert r.status_code == 200 and r.json()["offer"] is None
    finally:
        main.app.dependency_overrides.clear()


def test_a_founding_members_renewal_keeps_the_price_after_the_offer_ends(store, monkeypatch, time_machine):
    time_machine.move_to(DEADLINE + timedelta(days=365))               # a year on: the offer is long closed
    _seats(store, 250)
    profile = {"id": "u", "plan": "basic", "plan_status": "active", "razorpay_subscription_id": "sub_f", "cancel_at_period_end": False}
    monkeypatch.setattr(db, "profile_by_subscription", lambda sid: dict(profile) if sid == profile["razorpay_subscription_id"] else None)
    monkeypatch.setattr(db, "find_profile", lambda uid: dict(profile))
    monkeypatch.setattr(db, "update_profile", lambda uid, **kw: profile.update(kw) or dict(profile))
    monkeypatch.setattr("app.admin.mark_granted", lambda *a: None)
    invoiced = []
    monkeypatch.setattr(billing, "invoice_for", lambda p, sub, pay: invoiced.append((sub["plan_id"], pay["amount"])))
    monkeypatch.setattr(billing.invite_rewards, "safe_paid", lambda *a: None)
    sub = {"id": "sub_f", "status": "active", "plan_id": "plan_FoundBasic1", "current_end": 1830000000,
           "notes": {"user_id": "u", "plan": "basic", "period": "year", "currency": "INR", "offer": "founding"}}
    billing._act({"event": "subscription.charged", "payload": {"subscription": {"entity": sub},
                                                               "payment": {"entity": {"id": "pay_r", "amount": 499900, "status": "captured"}}}})
    assert (profile["plan"], profile["plan_status"], profile["razorpay_subscription_id"]) == ("basic", "active", "sub_f")
    assert invoiced == [("plan_FoundBasic1", 499900)]                 # the renewal is the founding plan's ₹4,999, as Razorpay charged it
    assert billing.price_of(sub) == {"amount": 4999.0, "currency": "INR", "period": "year", "offer": "founding"}
    # an event without notes is still matched to its plan by the founding plan's id
    assert billing.plan_for({"plan_id": "plan_FoundPro1"}) == "pro" and billing.plan_for({"plan_id": "plan_StudentBasic1"}) == "basic"


# ---------- P3: students ----------
def test_a_student_request_is_checked_and_sent_once(store):
    me = {"id": "s1", "email": "s@gmail.com"}
    with pytest.raises(ValueError, match="which college"):
        offers.apply(me, "", "x@iitb.ac.in", "")
    with pytest.raises(ValueError, match="doesn't look like an email"):
        offers.apply(me, "IIT Bombay", "not an email", "")
    with pytest.raises(ValueError, match="college email, or a short note"):
        offers.apply(me, "IIT Bombay", "", "id")
    row = offers.apply(me, "IIT Bombay", "s1@iitb.ac.in", "")
    assert row["status"] == "pending" and row["email"] == "s@gmail.com"
    with pytest.raises(ValueError, match="already asked"):
        offers.apply(me, "IIT Bombay", "s1@iitb.ac.in", "")
    assert offers.student_public("s1")["status"] == "pending" and offers.student_public("s1")["price"] is None
    assert [r["uid"] for r in offers.requests()] == ["s1"]


def test_an_approved_student_checks_out_basic_yearly_at_the_student_price(store, rz, time_machine):
    time_machine.move_to(DEADLINE - timedelta(days=3))
    offers.apply({"id": "s1"}, "Delhi University", "", "Student ID 2024/1234, valid to June 2027")
    assert offers.checkout_plan({"id": "s1"}, "basic", "year", "INR") == ("founding", "plan_FoundBasic1")     # pending: not yet
    offers.decide("s1", "price", "owner@x.com")
    assert offers.student_public("s1") == {**offers.student_public("s1"), "status": "approved", "mode": "price", "price": 2499}
    out = billing.create_subscription({"id": "s1"}, "basic", "year", "INR", expect_offer="student")
    assert out["offer"] == "student" and rz.made[-1]["plan_id"] == "plan_StudentBasic1" and rz.made[-1]["notes"]["offer"] == "student"
    assert billing.price_of(rz.made[-1])["amount"] == 2499.0
    # the student price is Basic's, yearly, in rupees: Pro yearly is the founding price while it runs, monthly the standard one
    assert offers.checkout_plan({"id": "s1"}, "pro", "year", "INR")[0] == "founding"
    assert offers.checkout_plan({"id": "s1"}, "basic", "month", "INR") == (None, None)


def test_the_owner_can_give_basic_by_hand_or_turn_a_request_down(store, monkeypatch):
    given = []
    monkeypatch.setattr("app.admin.set_plan", lambda uid, plan, days: given.append((uid, plan, days)) or {"id": uid})
    offers.apply({"id": "s2"}, "NIT Trichy", "s2@nitt.edu", "")
    offers.decide("s2", "grant", "owner@x.com")
    assert given == [("s2", "basic", 365)] and offers.student_of("s2")["mode"] == "grant"
    assert offers.student_public("s2")["price"] is None              # given by hand: nothing to pay
    offers.apply({"id": "s3"}, "Some College", "", "Student ID card 778812")
    offers.decide("s3", "reject")
    assert offers.student_of("s3")["status"] == "rejected"
    offers.apply({"id": "s3"}, "Some College", "s3@college.edu", "")      # turned down: may ask again
    assert offers.student_of("s3")["status"] == "pending"
    with pytest.raises(LookupError):
        offers.decide("nobody", "reject")
    store.rows[offers.PLANS_KEY] = json.dumps({k: v for k, v in IDS.items() if k != "student_basic_year"})
    offers.forget()
    with pytest.raises(ValueError, match="student plan isn't set"):
        offers.decide("s3", "price")


def test_the_student_routes_and_admin_routes(store, monkeypatch):
    from fastapi.testclient import TestClient
    from app import admin, main
    me = {"id": "s4", "email": "s4@gmail.com", "plan": "free", "_plan": "free"}
    main.app.dependency_overrides[main.current_profile] = lambda: me
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "u-admin", "email": "owner@example.com"}
    try:
        c = TestClient(main.app)
        r = c.post("/student/apply", json={"college": "BITS Pilani", "college_email": "f2025@pilani.bits-pilani.ac.in"})
        assert r.status_code == 200 and r.json()["student"]["status"] == "pending"
        assert c.post("/student/apply", json={"college": "BITS Pilani", "college_email": "x"}).status_code == 400
        v = c.get("/admin/offers").json()
        assert [x["uid"] for x in v["students"]] == ["s4"] and v["founding"]["seats"] == 100 and v["student_price"] == 2499
        assert {p["field"]: p["amount"] for p in v["plans"]} == {"founding_basic_year": 4999, "founding_pro_year": 14999, "student_basic_year": 2499}
        r = c.post("/admin/students/s4", json={"decision": "price"})
        assert r.status_code == 200 and r.json()["request"]["status"] == "approved"
        assert c.post("/admin/students/none", json={"decision": "reject"}).status_code == 404
        assert c.put("/admin/offers/plans", json={"student_basic_year": "nope"}).status_code == 400
        r = c.put("/admin/offers/plans", json={"student_basic_year": ""})        # cleared
        assert r.status_code == 200 and {p["field"]: p["id"] for p in r.json()["plans"]}["student_basic_year"] is None
    finally:
        main.app.dependency_overrides.clear()


def test_make_the_offer_plans_makes_each_missing_one_yearly_in_rupees(store, monkeypatch):
    """The owner's button (Admin → Prices): never pressed by a test against Razorpay; here a fake client stands in."""
    from fastapi.testclient import TestClient
    from app import admin, main
    store.rows[offers.PLANS_KEY] = json.dumps({"founding_basic_year": "plan_Kept1"})
    offers.forget()
    made = []
    monkeypatch.setattr(billing, "_client", SimpleNamespace(plan=SimpleNamespace(create=lambda body: made.append(body) or {"id": f"plan_New{len(made)}"})))
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "u-admin", "email": "owner@example.com"}
    try:
        r = TestClient(main.app).post("/admin/offers/razorpay-plans")
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 200 and r.json()["made"] == {"founding_pro_year": "plan_New1", "student_basic_year": "plan_New2"}
    assert [(b["period"], b["interval"], b["item"]["amount"], b["item"]["currency"]) for b in made] == [("yearly", 1, 1499900, "INR"), ("yearly", 1, 249900, "INR")]
    assert made[0]["item"]["name"] == "StratLab Pro (founding member, yearly)" and made[1]["item"]["name"] == "StratLab Basic (student, yearly)"
    assert offers.plan_ids() == {"founding_basic_year": "plan_Kept1", "founding_pro_year": "plan_New1", "student_basic_year": "plan_New2"}


# ---------- P2: one theme deck a month on Free, a PDF, marked ----------
def test_free_makes_one_theme_pdf_a_month_and_nothing_else():
    assert plans.PLANS["free"]["decks_per_month"] == 1
    assert plans.deck_rules("free") == {"kinds": ("theme",), "formats": ("pdf",), "mark": True}
    assert plans.deck_refusal("free", "theme", "pdf") is None
    assert plans.deck_refusal("free", "theme", "pptx") == ("PowerPoint decks are on Basic: 5 a month, of a company or a theme. "
                                                           "Free makes 1 theme deck a month, as a PDF.")
    assert plans.deck_refusal("free", "company", "pdf").startswith("A company's slide deck is on Basic: 5 a month")
    for p in ("basic", "pro"):
        assert not plans.deck_rules(p)["mark"] and all(plans.deck_refusal(p, k, f) is None for k in ("company", "theme") for f in ("pdf", "pptx"))
    pub = plans.public_plans()
    assert (pub["free"]["deck_kinds"], pub["free"]["deck_formats"], pub["free"]["deck_mark"]) == (["theme"], ["pdf"], True)


def test_every_page_of_a_marked_deck_says_made_with_stratlab_and_the_themes_link(monkeypatch):
    from pypdf import PdfReader
    from app import deck
    from tests.test_export import view
    monkeypatch.setattr(deck, "theme_address", lambda region, sector: "stratlab.studio/themes/in/test-theme")
    v = view()
    marked, _ = deck.build_theme_gated(v, pdf=True, marked=True)
    pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(marked)).pages]
    assert len(pages) > 3
    for i, t in enumerate(pages):
        flat = " ".join(t.split())
        assert "Made with StratLab · stratlab.studio" in flat and "stratlab.studio/themes/in/test-theme" in flat, i
    plain, _ = deck.build_theme_gated(v, pdf=True)
    assert all("Made with StratLab" not in (p.extract_text() or "") for p in PdfReader(io.BytesIO(plain)).pages)


def test_the_free_deck_route_gives_one_marked_pdf_a_month(monkeypatch):
    from app import main
    from app.intel import theme_routes
    usage = []
    monkeypatch.setattr(db, "count_usage", lambda uid, kind, since: usage.count(kind))
    monkeypatch.setattr(db, "add_usage", lambda uid, kind: usage.append(kind))
    monkeypatch.setattr(theme_routes, "map_for_deck", lambda R, profile, region, q, wait=0, pending=None: ("IN", q, {}))
    monkeypatch.setattr(theme_routes, "_routes", lambda: None)
    made = []
    monkeypatch.setattr(theme_routes, "deck_file", lambda R, r, theme, m, profile, fmt, biz, marked=False: made.append((theme, fmt, marked)) or b"%PDF-1.4")
    monkeypatch.setattr(theme_routes, "market_day", lambda r: datetime(2026, 11, 28).date())
    free = {"id": "u1", "plan": "free", "_plan": "free", "created_at": "2026-11-20T00:00:00+05:30"}
    assert theme_routes.theme_dive_deck("Defence", "IN", "pdf", profile=free).status_code == 200
    assert made == [("Defence", "pdf", True)] and usage == ["deck", "deck:theme:IN:defence"]
    assert theme_routes.theme_dive_deck("Defence", "IN", "pdf", profile=free).status_code == 200      # the same theme again: not counted
    assert usage.count("deck") == 1
    with pytest.raises(HTTPException) as e:
        theme_routes.theme_dive_deck("Banks", "IN", "pdf", profile=free)                             # a second theme this month
    assert e.value.status_code == 402 and e.value.detail["message"].startswith("You've made 1 slide deck this month.")
    with pytest.raises(HTTPException) as e:
        theme_routes.theme_dive_deck("Defence", "IN", "pptx", profile=free)
    assert e.value.detail["message"].startswith("PowerPoint decks are on Basic")
    basic = {"id": "u2", "plan": "basic", "_plan": "basic"}
    theme_routes.theme_dive_deck("Defence", "IN", "pptx", profile=basic)
    assert made[-1] == ("Defence", "pptx", False)


def test_a_marked_deck_is_kept_apart_from_the_shared_store(monkeypatch):
    from app import computed, deck
    from app.intel import theme_routes as T
    from tests.test_export import MAP
    put = []
    monkeypatch.setattr(computed, "put", lambda *a, **k: put.append(a))
    monkeypatch.setattr(computed, "get", lambda *a, **k: None)
    built = []
    monkeypatch.setattr(deck, "build_theme_gated", lambda v, pdf=False, marked=False: built.append(marked) or (b"%PDF-" + (b"M" if marked else b"P"), {}))
    monkeypatch.setattr(T, "deck_view", lambda r, m, dive, extras: {})
    monkeypatch.setattr(T, "deck_extras", lambda *a, **k: {})
    monkeypatch.setattr(T, "dive_of", lambda r, theme, m: {"as_of": "2026-11-27"})
    monkeypatch.setattr(T, "figures_waiting", lambda dive: 0)
    T.DECK_CACHE._d.clear()
    R = SimpleNamespace(IST=IST)
    a = T.deck_file(R, "IN", "Test theme", MAP, {"id": "u"}, "pdf", False, marked=True)
    b = T.deck_file(R, "IN", "Test theme", MAP, {"id": "u"}, "pdf", False)
    assert (a, b) == (b"%PDF-M", b"%PDF-P") and built == [True, False] and len(put) == 1     # only the unmarked one is shared
    assert T.deck_file(R, "IN", "Test theme", MAP, {"id": "u"}, "pdf", False, marked=True) == a and built == [True, False]
