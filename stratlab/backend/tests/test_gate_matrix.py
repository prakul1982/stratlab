"""Every paid feature, enforced on the server for each kind of account: Free, Basic, Pro, anyone during the launch offer,
and the site owner. Plans gate whether or not payments are set up (the owner's decision, 7 Oct); a refusal is a 402
with a code, and while no plan can be bought its message says how to ask for early access."""
from datetime import datetime, timedelta, timezone

import pytest

from app import plans
from app.config import settings
from app.plans import FEATURE_PLAN, FEATURES, PLANS, allows, plan_of
from tests import world
from tests.stress_requests import EMA

RANK = {"free": 0, "basic": 1, "pro": 2}

# who → (token, what they can use)
ACCOUNTS = {"free": "free-token", "basic": "basic-token", "pro": "pro-token"}


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    plans._promo.update(read_at=1e18, until=None)            # no launch offer unless a test starts one
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_PLAN_BASIC", "RAZORPAY_PLAN_PRO"):
        monkeypatch.setattr(settings, k, "")                 # payments off: plans still gate
    yield built
    plans._promo.update(read_at=0.0, until=None)
    built["close"]()


def promo_on():
    plans._promo.update(read_at=1e18, until=datetime.now(timezone.utc) + timedelta(days=3))


# ---------- the rule, for every feature ----------
@pytest.mark.parametrize("feature", FEATURES)
def test_each_feature_on_each_plan(feature, monkeypatch):
    """allows(): a feature is on the plan its Pricing card names and every plan above it, nowhere below."""
    for k in ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"):
        monkeypatch.setattr(settings, k, "")
    need = FEATURE_PLAN[feature]
    for plan in ("free", "basic", "pro"):
        assert allows(plan, feature) == (RANK[plan] >= RANK[need]), f"{feature} on {plan}"


def test_who_gets_which_plan(monkeypatch):
    """plan_of(): the plan a request is checked against."""
    free = {"id": "u", "plan": "free"}
    basic = {"id": "u", "plan": "basic", "plan_status": "active"}
    lapsed = {"id": "u", "plan": "pro", "plan_status": "cancelled"}
    granted = {"id": "u", "plan": "pro", "plan_status": "active", "current_period_end": None}   # the owner's Change plan
    plans._promo.update(read_at=1e18, until=None)
    monkeypatch.setattr(plans, "free_basic_until", lambda p, now=None: None)
    try:
        assert [plans.access_plan(p) for p in (free, basic, lapsed, granted)] == ["free", "basic", "free", "pro"]
        assert plan_of({**free, "_plan": "pro"}) == "pro"           # what sign-in resolved wins (the site owner)
        promo_on()
        assert plans.access_plan(free) == "pro" and plans.access_plan(lapsed) == "pro"
    finally:
        plans._promo.update(read_at=0.0, until=None)


# ---------- the routes: (feature, method, path, body) that refuse outright without the plan ----------
ROUTES = [
    ("scans", "post", "/research/scan", {"region": "IN", "set": "nifty50", "scan": "st_s2"}),
    ("scans", "put", "/research/scan/alerts", {"on": True}),
    ("filings", "get", "/research/filings", None),
    ("filings", "put", "/research/filings/alerts", {"on": True}),
    ("filings", "get", "/research/redflags?scope=watchlist", None),
    ("investor_home", "get", "/research/investor", None),
    ("export", "post", "/export/strategy", {"strategy": EMA}),
    ("breadth", "post", "/invest/breadth/alerts", {"group": "nifty50", "level": 50}),
    ("positioning", "get", "/trade/positioning/history", None),
    ("cas_history", "get", "/trade/closing-auction/history", None),
    ("fo_alerts", "put", "/trade/fo-changes/alerts", {"on": True}),
    ("event_reminders", "put", "/trade/events/prefs", {"remind": True}),
    ("chart_replay", "post", "/trade/replay", {"instrument": "CRYPTO:BTC-USD", "tf": "1d", "random": True}),
    ("signal_webhooks", "post", "/trade/signals/hook", None),
    ("itr_export", "get", "/money/itr/export?fy=2025&format=xlsx", None),
    ("us_tax", "get", "/money/us-tax/schedule-fa.csv?cy=2025", None),
    ("tax_tools", "put", "/money/advance-tax", {"fy": 2026, "tds": 0, "paid": []}),
    ("assistant", "post", "/me/assistant/keys", {"name": "Claude"}),
    ("alerts", "put", "/me/alerts", {"alerts_enabled": True}),
    ("newsletter", "put", "/me/newsletters", {"market_in": "daily"}),
    ("biz_updates", "get", "/invest/business-updates?sector=autos", None),
    ("biz_updates", "get", "/invest/business-updates/mine", None),
    ("holders", "get", "/invest/holders?q=life", None),
    ("money_reminders", "put", "/money/calendar/reminders", {"on": True, "days": 3}),
    ("journal", "get", "/trade/journal/compare?tag=x&session=s1", None),
]


def _call(c, method, path, body, token):
    h = world.headers(token)
    return c.request(method.upper(), path, headers=h, json=body) if body is not None else c.request(method.upper(), path, headers=h)


@pytest.mark.parametrize("feature,method,path,body", ROUTES, ids=[f"{r[0]}:{r[2]}" for r in ROUTES])
def test_route_matrix(w, feature, method, path, body, monkeypatch):
    c = w["client"]
    need = FEATURE_PLAN[feature]
    for who, token in ACCOUNTS.items():
        r = _call(c, method, path, body, token)
        if RANK[who] < RANK[need]:
            assert r.status_code == 402, f"{feature} on {who}: {r.status_code} {r.text[:200]}"
            d = r.json()["detail"]
            assert d["code"] == "upgrade_required" and d["payments"] is False
            assert PLANS[need]["name"] in d["message"] and "ask us at support@stratlab.studio for early access" in d["message"]
        else:
            assert r.status_code != 402, f"{feature} on {who}: refused {r.text[:200]}"
    # the launch offer opens it for Free; the site owner always has it
    promo_on()
    assert _call(c, method, path, body, "free-token").status_code != 402, f"{feature} during the launch offer"
    plans._promo.update(read_at=1e18, until=None)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "free@example.com")
    assert _call(c, method, path, body, "free-token").status_code != 402, f"{feature} for the owner"


def test_every_paid_feature_is_refused_somewhere_on_the_server():
    """The features with a route above, plus where the rest are enforced (checked by their own tests)."""
    elsewhere = {"indicators": "check_features, live.session_needs", "fno": "check_features, charts, replay",
                 "group_live": "POST /live/groups", "fast_entries": "POST /live/groups", "options": "POST /options/sessions",
                 "options_signal": "POST /options/sessions", "vix_filter": "POST /options/sessions", "strike_rules": "POST /options/sessions",
                 "options_whatif": "POST /options/roll", "daily_report": "PUT /me/alerts", "networth": "net worth entry count",
                 "mf_gains": "mutual fund view", "dividends": "dividends view", "money_reminders": "money calendar reminders",
                 "journal": "journal view and /trade/journal/compare", "mf_costs": "fund costs view", "etf_gaps": "ETF gap alerts",
                 "biz_updates": "business update views and alert", "holders": "holder search", "stock_futures": "history views and MWPL alert",
                 "mtf": "history views and alert", "mf_behaviour": "fund behaviour view", "sip_luck": "dip rules in the SIP test",
                 "rates_slab": "rates at your own slab", "loan_check": "loan check view"}
    covered = {r[0] for r in ROUTES} | set(elsewhere)
    assert covered == set(FEATURES), set(FEATURES) ^ covered
