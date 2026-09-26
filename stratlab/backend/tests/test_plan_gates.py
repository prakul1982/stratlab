"""The new plans: what each includes, the server-side checks, and what stops after a downgrade."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import billing, live, main
from app.config import settings
from app.plans import PLANS, allows, group_size, plan_info


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")


def as_plan(plan):
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": plan, "plan": plan}
    return TestClient(main.app)


def test_prices_and_limits():
    assert (PLANS["basic"]["price"], PLANS["pro"]["price"]) == (999, 2999)
    assert (PLANS["basic"]["price_year"], PLANS["pro"]["price_year"]) == (9990, 29990)
    assert [PLANS[p]["live_limit"] for p in ("free", "basic", "pro")] == [1, 2, 10]
    assert [PLANS[p]["group_size"] for p in ("free", "basic", "pro")] == [10, 25, 50]


def test_everything_open_during_early_access(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    assert all(plan_info("free")["features"].values()) and group_size("free") == 50


def test_features_per_plan_once_payments_are_live(paid):
    assert not any(allows("free", f) for f in ("group_live", "options", "daily_report", "alerts", "export"))
    assert allows("basic", "group_live") and allows("basic", "options") and allows("basic", "daily_report")
    assert not allows("basic", "options_signal") and not allows("basic", "fast_entries") and not allows("basic", "alerts")
    assert all(plan_info("pro")["features"].values())
    assert group_size("free") == 10 and group_size("basic") == 25


def test_server_refuses_what_the_plan_lacks(paid):
    try:
        c = as_plan("free")
        r = c.post("/export/strategy", json={"strategy": {"name": "x", "tf": "1d", "entry": [], "exit": []}})
        assert r.status_code == 402 and "Pro plan" in r.json()["detail"]["message"]
        r = c.put("/me/alerts", json={"alerts_enabled": False, "alert_email": "a@b.co"})
        assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
        opt = {"strategy": {"underlying": "NIFTY", "legs": [{"side": "buy", "opt": "CE"}]}}
        assert c.post("/options/sessions", json=opt).status_code == 402
        c = as_plan("basic")
        r = c.put("/me/alerts", json={"alerts_enabled": True, "alert_email": "a@b.co"})
        assert r.status_code == 402 and "Trade alerts are on the Pro plan" in r.json()["detail"]["message"]
        sig = {"strategy": {**opt["strategy"], "signal": {"rules": {"name": "e", "tf": "5m", "entry": [], "exit": []}}}}
        r = c.post("/options/sessions", json=sig)
        assert r.status_code == 402 and "signal" in r.json()["detail"]["message"]
    finally:
        main.app.dependency_overrides.clear()


def test_group_size_is_checked_before_counting_an_experiment(paid):
    with pytest.raises(Exception) as e:
        main.check_group_size({"_plan": "free"}, 11)
    assert "up to 10" in str(e.value.detail["message"]) and "Basic goes up to 25" in str(e.value.detail["message"])
    main.check_group_size({"_plan": "basic"}, 25)


def test_downgrade_stops_sessions_the_plan_no_longer_covers(paid):
    group = SimpleNamespace(kind="group", fast={"ticks": True})
    opt_sig = SimpleNamespace(kind="options", strategy=SimpleNamespace(signal=object()))
    assert live.session_needs(group, "free") == "Paper trading a group"
    assert live.session_needs(group, "basic") == "Faster group entries" and live.session_needs(group, "pro") is None
    assert live.session_needs(opt_sig, "basic") == "Options on a signal"
    assert live.session_needs(SimpleNamespace(kind="single"), "free") is None


def test_alerts_and_report_follow_the_plan(paid, monkeypatch):
    for k, v in (("SMTP_HOST", "smtp.x"), ("SMTP_USER", "u"), ("SMTP_PASSWORD", "p")):
        monkeypatch.setattr(settings, k, v)                      # email counts as a channel only when the server can send it
    p = lambda plan, **kw: {"plan": plan, "plan_status": "active", **kw}
    assert live.report_on(p("basic", alert_email="a@b.c")) and not live.alerts_on(p("basic", alerts_enabled=True, alert_email="a@b.c"))
    assert live.alerts_on(p("pro", alerts_enabled=True)) and not live.report_on(p("pro"))       # no channel set
    assert not live.report_on({"plan": "free", "alert_email": "a@b.c"})
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert not live.report_on(p("basic", alert_email="a@b.c"))                                  # no SMTP: no channel


def test_yearly_plans_map_back(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_bm")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO_YEAR", "plan_py")
    assert billing.plan_for({"plan_id": "plan_py"}) == "pro" and billing.plan_for({"plan_id": "plan_bm"}) == "basic"
    assert billing.plan_for({"plan_id": "x", "notes": {"plan": "basic"}}) == "basic"


def test_experience_level_is_saved_with_other_prefs(monkeypatch):
    from app import db
    store = {"prefs:u1": '{"daily_report": false}'}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    try:
        c = as_plan("free")
        assert c.put("/me/prefs", json={"level": "pro"}).json() == {"prefs": {"level": "pro"}}
        assert '"daily_report": false' in store["prefs:u1"] and '"level": "pro"' in store["prefs:u1"]
        assert c.put("/me/prefs", json={"level": "expert"}).status_code == 422
        assert main.prefs_of("nobody") == {}
    finally:
        main.app.dependency_overrides.clear()
