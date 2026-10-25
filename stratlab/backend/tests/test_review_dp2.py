"""25 Oct 2026 deep audit of the plan locks and limits on the Money pages, the lock wording everywhere, the alerts form,
notifications, Account's usage and the payment window (DP2-003 .. DP2-042, with DP1-007, DP1-018, DP1-023, DP1-024): a
locked figure is no figure, advance tax reminders are Basic on the server too, one lock wording with the plan, the month's
reset and what the next plan gives, ETFs found in the stock search, every kept limit with its count, and an unpaid checkout
used again."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import billing, first_steps, main, money_advance_tax as A, money_itr, plans, suggest, tax_total
from app.newsletter import write
from tests import world

PRO, BASIC, FREE = world.headers("pro-token"), world.headers("basic-token"), world.headers("free-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.fixture
def paid(monkeypatch):
    """Plans enforced (payments live), so Free and Basic see the locked parts."""
    from app import auth
    from app.config import settings
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(plans, "access_plan", lambda p: p.get("plan") or "free")
    monkeypatch.setattr(auth, "access_plan", lambda p: p.get("plan") or "free")


# ---------- DP2-003: a locked number is no number, never a false 0 ----------
def test_locked_lot_counts_are_not_sent_as_zero(w, paid):
    c = w["client"]
    free, pro = c.get("/money/ltcg", headers=FREE).json(), c.get("/money/ltcg", headers=PRO).json()
    assert free["locked"] and free["open_lt"] is None and free["soon_counts"] is None
    assert free["long"] == [] and free["soon"] == [] and free["below_cost"]["rows"] == []
    assert not pro["locked"] and isinstance(pro["open_lt"]["lots"], int) and set(pro["soon_counts"]) == {"30", "60", "90"}


# ---------- DP2-004: advance tax reminders are Basic, on the server too ----------
def test_free_cant_turn_advance_tax_reminders_on(w, paid):
    c = w["client"]
    r = c.put("/money/advance-tax/reminders", headers=FREE, json={"on": True})
    assert r.status_code == 402 and "Advance tax reminders are on the Basic plan." in r.json()["detail"]["message"]
    assert r.json()["detail"]["plan"] == "basic"
    assert c.put("/money/advance-tax/reminders", headers=FREE, json={"on": False}).status_code == 200      # off is always allowed
    v = c.get("/money/advance-tax", headers=FREE).json()
    assert v["remind"] is False and v["remind_locked"] is True and v["remind_plan"] == "Basic"
    assert c.put("/money/advance-tax/reminders", headers=BASIC, json={"on": True}).status_code == 200
    b = c.get("/money/advance-tax", headers=BASIC).json()
    assert b["remind"] is True and b["remind_locked"] is False


def test_a_free_subscriber_saved_before_the_lock_gets_no_reminder(w, paid, monkeypatch):
    sent = []
    monkeypatch.setattr(A, "send", lambda p, subject, text: sent.append(p["id"]) or True)
    monkeypatch.setattr(A, "subscribers", lambda: ["u-free", "u-basic"])
    monkeypatch.setattr(A, "plan_of", lambda p: p.get("plan") or "free")
    from app import db
    db.update_profile("u-free", plan="free")
    db.update_profile("u-basic", plan="basic")
    eve = datetime(2026, 12, 8, 4, 0, tzinfo=timezone.utc)          # 7 days before 15 Dec, after the send time
    assert A.Job().tick(eve) == 1 and sent == ["u-basic"]


# ---------- DP2-022, DP1-018: one lock wording ----------
def test_the_one_limit_wording():
    now = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
    assert plans.resets_on(now) == "1 Nov" and plans.resets_on(datetime(2026, 12, 31, 12, 0, tzinfo=timezone.utc)) == "1 Jan"
    assert plans.resets_on(datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc)) == "1 Feb"          # already January in India
    msg = plans.limit_message("free", "backtests_per_month", "You've used all 10 backtests this month", "backtests", monthly=True)
    assert msg == f"You've used all 10 backtests this month. The count starts again on {plans.resets_on()}. Basic gives 100 a month."
    assert plans.limit_message("basic", "stock_alerts", "Your Basic plan has 25 alerts on at a time. Delete one to add another", "alerts") \
        == "Your Basic plan has 25 alerts on at a time. Delete one to add another. Pro gives 100."
    assert plans.limit_message("pro", "stock_alerts", "Your Pro plan has 100 alerts on at a time", "alerts") == "Your Pro plan has 100 alerts on at a time."
    assert plans.limit_message("basic", "backtests_per_month", "x", "backtests", monthly=True).endswith("Pro has no limit on backtests.")
    assert plans.named_plan("MACD is on the Basic plan.") == "basic" and plans.named_plan("Export is on the Pro plan.") == "pro"
    assert plans.named_plan("Delete one to add another.") is None


def test_a_402_names_its_plan_for_the_price(w):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        main.upgrade("Trend scans are on the Basic plan.")
    assert e.value.status_code == 402 and e.value.detail["plan"] == "basic"


def test_the_alert_limit_says_the_plan_and_what_the_next_gives(w, paid):
    c = w["client"]
    body = {"region": "IN", "symbol": "TCS", "kind": "move", "op": "either", "value": 5}
    for i in range(5):
        assert c.post("/alerts", headers=FREE, json={**body, "value": 5 + i}).status_code == 200
    r = c.post("/alerts", headers=FREE, json=body)
    msg = r.json()["detail"]["message"]
    assert r.status_code == 402 and msg == "Your Free plan has 5 alerts on at a time. Delete one to add another. Basic gives 25."
    assert "see plans" not in msg.lower()                         # the page's button says it, once (DP2-022)


# ---------- DP2-021, DP1-024: ETFs are found in the stock search ----------
def test_etfs_join_the_search_lists():
    rows = suggest.india_rows([{"exchange": "NSE", "symbol": "TCS", "name": "TATA CONSULTANCY"}])
    both = suggest.with_etfs(rows, {"NIFTYBEES": {"name": "Nippon India ETF Nifty 50 BeES", "isin": "INF204KB14I2"}, "TCS": {"name": "x"}})
    assert [r["symbol"] for r in both] == ["TCS", "NIFTYBEES"]
    hit = suggest.rank("niftybees", suggest.index(both, "IN"))
    assert hit and hit[0]["symbol"] == "NIFTYBEES" and hit[0]["id"] == "NIFTYBEES"
    assert suggest.rank("nippon india etf", suggest.index(both, "IN"))[0]["symbol"] == "NIFTYBEES"


def test_the_offline_search_finds_an_etf(w, monkeypatch):
    monkeypatch.setattr(main.etf_nav, "load_live", lambda: {"rows": {"NIFTYBEES": {"name": "Nippon India ETF Nifty 50 BeES", "isin": None}}})
    monkeypatch.setattr(main.kite, "ready", lambda: False)
    main.suggester.clear()
    try:
        rows = w["client"].get("/suggest/companies?q=NIFTYBEES&market=IN", headers=FREE).json()["rows"]
        assert rows and rows[0]["symbol"] == "NIFTYBEES"
    finally:
        main.suggester.clear()


# ---------- DP2-011: the return that fits, and total income's lines add up ----------
def _g(**k):
    y = {"intraday": {"count": 0}, "business": {"segments": []}, "count": 0, "foreign": None}
    return {"y": {**y, **k.pop("y", {})}, "rows": [], "unit_rows": [], "fa": None, "us_div": None, "div_lines": [], **k}


def test_the_return_that_fits():
    assert money_itr.form_fits(_g()) == "Nothing in your files for this year"
    assert money_itr.form_fits(_g(div_lines=[{"amount": 500}])).startswith("ITR-1 if your total income is ₹50 lakh or less")
    assert money_itr.form_fits(_g(rows=[{"gain": 1}], div_lines=[{"amount": 500}])).startswith("ITR-2")
    assert money_itr.form_fits(_g(us_div={"inr": 10})).startswith("ITR-2")
    assert money_itr.form_fits(_g(y={"intraday": {"count": 2}})).startswith("ITR-3")


def test_total_income_has_the_exempt_gains_line():
    buckets = [{"key": "lt", "rate": 0.125, "after_setoff": 173000.0, "exempt": 125000.0, "taxable": 48000.0},
               {"key": "st", "rate": 0.2, "after_setoff": 25000.0, "exempt": 0.0, "taxable": 25000.0}]
    t = tax_total.estimate(2025, tax_total.default_inputs(), buckets, 0.0, 0.0)
    lines = {l["label"]: l["amount"] for l in t["lines"]}
    assert lines["Long-term gains within the exemption (not taxed)"] == 125000
    parts = ("Income taxed at slab rates", "Share gains taxed at special rates (after set-off and exemption)", "Long-term gains within the exemption (not taxed)")
    assert sum(lines[p] for p in parts) == lines["Total income"] == 198000


# ---------- DP2-030: the first step is done once something will arrive ----------
def test_a_chat_id_without_its_code_isnt_a_done_step(w):
    from app import db
    db.update_profile("u-free", created_at=datetime.now(timezone.utc).isoformat(), telegram_chat_id="12345")
    assert not first_steps.done(db.get_profile("u-free"))["alerts"]


# ---------- DP2-031: every kept limit on Account, and the trial's days left ----------
def test_my_limits_lists_every_kept_count(w, paid):
    c = w["client"]
    assert c.post("/alerts", headers=FREE, json={"region": "IN", "symbol": "TCS", "kind": "move", "op": "either", "value": 5}).status_code == 200
    got = c.get("/me/limits", headers=FREE).json()
    rows = {r["key"]: r for r in got["rows"]}
    assert got["plan"] == "Free" and list(rows) == ["stock_alerts", "screens", "holdings", "mf_schemes", "networth_items", "journal_trades"]
    assert rows["stock_alerts"] == {"key": "stock_alerts", "used": 1, "limit": 5, "next": "Basic"}
    assert rows["holdings"]["limit"] == 30 and rows["mf_schemes"]["limit"] == 5 and rows["networth_items"]["limit"] == 5
    assert rows["journal_trades"]["used"] is None and rows["journal_trades"]["limit"] == 50
    pro = {r["key"]: r for r in c.get("/me/limits", headers=PRO).json()["rows"]}
    assert pro["networth_items"]["limit"] is None and pro["stock_alerts"]["next"] is None


def test_the_trial_says_its_market_days_left():
    started = datetime(2026, 10, 26, 4, 0, tzinfo=timezone.utc)            # a Monday, India time
    ends = plans.trial_end(started, 5)
    assert plans.trial_days_left(ends, started) == 5
    assert plans.trial_days_left(ends, started + timedelta(days=2)) == 3
    assert plans.trial_days_left(ends, ends) == 0
    t = plans.trial_state({"live_trial_started_at": None})
    assert t["days_left"] == 5 and not t["started"]


# ---------- DP2-037: the AI's words don't restate the index moves ----------
def test_the_ai_summary_drops_the_index_restatement():
    f = {"indices": [{"name": "NIFTY 50", "change_pct": -2.36}, {"name": "SENSEX", "change_pct": -2.15}]}
    text = ("The NIFTY 50 closed at 22,600.00, down 2.36%, while the SENSEX fell to 73,123.83, down 2.15%. "
            "Five sectors moved on the rotation chart.")
    assert write.not_the_indices(text, f) == "Five sectors moved on the rotation chart."
    assert write.not_the_indices("The NIFTY 50 closed down 2.36%.", f) == ""
    assert "don't restate them" in write.SYSTEM and "never give its price move" in write.SYSTEM


# ---------- DP2-042: an unpaid checkout for the same plan is used again ----------
class FakeSubs:
    def __init__(self, held):
        self.held, self.made, self.cancelled = held, [], []

    def fetch(self, sid):
        return self.held[sid]

    def create(self, body):
        sid = f"sub_new{len(self.made)}"
        self.made.append(body)
        self.held[sid] = {"id": sid, "status": "created", "plan_id": body["plan_id"], "notes": body["notes"]}
        return self.held[sid]

    def cancel(self, sid, body):
        self.cancelled.append(sid)


def test_the_payment_window_reuses_an_unpaid_checkout(monkeypatch):
    from app import db
    from app.config import settings
    for k, v in (("RAZORPAY_KEY_ID", "rzp_test_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "plan_b"), ("RAZORPAY_PLAN_PRO", "plan_p")):
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(billing.pricing, "plan_id", lambda cur, plan, period: None)
    subs = FakeSubs({"sub_old": {"id": "sub_old", "status": "created", "plan_id": "plan_b", "notes": {"user_id": "u1"}}})
    monkeypatch.setattr(billing, "client", lambda: SimpleNamespace(subscription=subs))
    saved = {}
    monkeypatch.setattr(db, "update_profile", lambda uid, **k: saved.update(k))
    profile = {"id": "u1", "email": None, "pending_subscription_id": "sub_old", "razorpay_subscription_id": None}
    assert billing.create_subscription(profile, "basic")["subscription_id"] == "sub_old" and subs.made == [] and saved == {}
    # another plan: a new one, and the replaced unpaid one is cancelled at Razorpay
    got = billing.create_subscription(profile, "pro")
    assert got["subscription_id"] == "sub_new0" and saved["pending_subscription_id"] == "sub_new0" and subs.cancelled == ["sub_old"]
    # a checkout already paid for (authenticated) or expired is never reused
    subs.held["sub_new0"]["status"] = "authenticated"
    assert billing.create_subscription({**profile, "pending_subscription_id": "sub_new0"}, "pro")["subscription_id"] == "sub_new1"
    assert subs.cancelled == ["sub_old"]                        # nor cancelled
