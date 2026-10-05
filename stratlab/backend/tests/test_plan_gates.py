"""The new plans: what each includes, the server-side checks, and what stops after a downgrade."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import alerts, billing, live, main
from app.config import settings
from app.models import Strategy
from app.plans import (FEATURE_PLAN, FEATURES, PLANS, bigger_plan, decks, deepdives, group_size, has_fno, has_indicators,
                       plan_info)


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


def as_plan(plan):
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "u1", "_plan": plan, "plan": plan}
    return TestClient(main.app)


def test_prices_and_limits():
    assert (PLANS["basic"]["price"], PLANS["pro"]["price"]) == (699, 1999)            # rupees, GST included
    assert (PLANS["basic"]["price_year"], PLANS["pro"]["price_year"]) == (6999, 19999)    # about two months free
    row = lambda k: [PLANS[p][k] for p in ("free", "basic", "pro")]  # noqa: E731
    assert row("backtests_per_month") == [10, 100, None] and row("ai_builds_per_month") == [10, 100, None]
    assert row("live_limit") == [1, 2, 10] and row("group_size") == [10, 25, 50]
    assert row("holdings") == [30, 100, 300] and row("stock_alerts") == [5, 25, 100] and row("screens") == [2, 10, 25]
    assert row("deepdives_per_month") == [2, 15, None] and row("decks_per_month") == [1, 5, None]
    assert PLANS["free"]["live_trial_days"] == 5


def test_everything_open_during_early_access(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "")
    assert all(plan_info("free")["features"].values()) and group_size("free") == 50


def test_features_per_plan_once_payments_are_live(paid):
    assert not any(plan_info("free")["features"].values())
    basic = {"indicators", "group_live", "options", "alerts", "daily_report", "newsletter", "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "money_reminders", "breadth", "positioning", "journal", "mf_costs", "etf_gaps", "fo_alerts", "biz_updates", "holders"}
    assert {f for f, on in plan_info("basic")["features"].items() if on} == basic
    assert all(plan_info("pro")["features"].values()) and set(FEATURES) == basic | {"fno", "options_signal", "fast_entries", "export", "tax_tools", "itr_export", "us_tax", "options_whatif"}
    assert {f: FEATURE_PLAN[f] for f in ("indicators", "alerts", "scans", "fno", "export")} == {
        "indicators": "basic", "alerts": "basic", "scans": "basic", "fno": "pro", "export": "pro"}
    assert group_size("free") == 10 and group_size("basic") == 25
    assert (has_indicators("free"), has_indicators("basic"), has_fno("basic"), has_fno("pro")) == (False, True, False, True)
    assert [deepdives(p) for p in ("free", "basic", "pro")] == [2, 15, None] and [decks(p) for p in ("free", "basic", "pro")] == [1, 5, None]
    info = plan_info("free")
    assert (info["indicators"], info["fno"], info["deepdives_per_month"], info["decks_per_month"]) == (False, False, 2, 1)
    assert "pro_features" not in info


def test_which_plan_lifts_each_limit():
    assert bigger_plan("free", "backtests_per_month") == "Basic" and bigger_plan("basic", "backtests_per_month") == "Pro"
    assert bigger_plan("pro", "backtests_per_month") is None and bigger_plan("basic", "live_limit") == "Pro"
    assert main.lift("free", "backtests_per_month", "backtests") == " Basic gives 100."
    assert main.lift("basic", "deepdives_per_month", "deep dives") == " Pro has no limit on deep dives."
    assert main.lift("pro", "stock_alerts", "alerts") == ""


def test_server_refuses_what_the_plan_lacks(paid, monkeypatch):
    monkeypatch.setattr(main.db, "update_profile", lambda *a, **k: None)
    try:
        c = as_plan("free")
        r = c.post("/export/strategy", json={"strategy": {"name": "x", "tf": "1d", "entry": [], "exit": []}})
        assert r.status_code == 402 and "Pro plan" in r.json()["detail"]["message"]
        r = c.put("/me/alerts", json={"alerts_enabled": False, "alert_email": "a@b.co"})
        assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
        opt = {"strategy": {"underlying": "NIFTY", "legs": [{"side": "buy", "opt": "CE"}]}}
        assert c.post("/options/sessions", json=opt).status_code == 402
        c = as_plan("basic")
        assert c.put("/me/alerts", json={"alerts_enabled": True, "alert_email": "a@b.co"}).status_code == 200   # Basic has them
        r = c.post("/export/strategy", json={"strategy": {"name": "x", "tf": "1d", "entry": [], "exit": []}})
        assert r.status_code == 402 and "Pro plan" in r.json()["detail"]["message"]
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


MACD = Strategy(name="m", entry=[{"l": {"t": "macd"}, "op": "gt", "r": {"t": "num", "v": 0}}])
SMA = Strategy(name="s", entry=[{"l": {"t": "price"}, "op": "gt", "r": {"t": "sma", "p": 50}}])
FNO = {"id": "IN:1", "fno": True}


def stop_reason(e) -> str:
    return e.value.detail["message"]


def test_indicators_are_basic_and_fno_is_pro(paid):
    assert live.needs_indicators(MACD) and not live.needs_indicators(SMA)
    assert live.needs_fno(FNO) and not live.needs_fno({"id": "IN:2"}) and not live.needs_fno(None)
    with pytest.raises(Exception) as e:
        main.check_features({"_plan": "free"}, MACD, None)
    assert "Basic unlocks all of them" in stop_reason(e)
    main.check_features({"_plan": "free"}, SMA, None)
    main.check_features({"_plan": "basic"}, MACD, None)                 # every indicator on Basic
    with pytest.raises(Exception) as e:
        main.check_features({"_plan": "basic"}, SMA, FNO)
    assert stop_reason(e) == "Indian F&O is on the Pro plan."
    main.check_features({"_plan": "pro"}, MACD, FNO)
    assert main.all_indicators({"_plan": "basic"}) and not main.fno({"_plan": "basic"}) and main.fno({"_plan": "pro"})


def test_downgrade_stops_only_what_the_new_plan_lacks(paid, monkeypatch):
    """After a plan change: F&O sessions stop below Pro, Basic-indicator sessions stop on Free, the rest keep running."""
    class Sess:
        def __init__(self, sid, strategy, inst):
            self.id, self.user_id, self.strategy, self.inst, self.kind = sid, "u1", strategy, inst, "single"
            self.started_at = sid
    monkeypatch.setattr(live, "LiveSession", Sess)
    monkeypatch.setattr(live, "trial_state", lambda profile: {"active": True, "started": True})
    stopped = {}
    m = live.LiveManager.__new__(live.LiveManager)
    m.sessions = {}
    m.stop = lambda sid, why: stopped.__setitem__(sid, why) or m.sessions.pop(sid, None)

    def run(plan, *sessions):
        stopped.clear()
        m.sessions = {s.id: s for s in sessions}
        monkeypatch.setattr(live.db, "get_profile", lambda uid: {"id": uid, "plan": plan, "plan_status": "active"})
        m._enforce_plans(list(sessions))
        return dict(stopped)

    a, b = Sess("1", MACD, None), Sess("2", SMA, FNO)
    assert run("basic", a, b) == {"2": "Indian F&O is on Pro."}
    assert run("free", Sess("1", MACD, None)) == {"1": "This strategy uses Basic indicators."}
    assert run("pro", Sess("1", MACD, None), Sess("2", SMA, FNO)) == {}


def test_research_open_to_every_plan(paid, monkeypatch):
    """Sector rotation and the red flags on a company page are for everyone; the scan, the watchlist's red flags and
    Watchlist at a glance are Basic."""
    try:
        c = as_plan("free")
        assert c.get("/research/rotation").status_code != 402
        assert c.post("/research/scan", json={"region": "IN", "set": "watchlist"}).status_code == 402
        assert c.put("/research/scan/alerts", json={"on": True}).status_code == 402
        assert c.get("/research/investor").status_code == 402
        r = c.put("/me/alerts", json={"alerts_enabled": True, "alert_email": "a@b.co"})
        assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
    finally:
        main.app.dependency_overrides.clear()


def test_each_limit_says_which_plan_lifts_it(paid, monkeypatch):
    used = {"n": 0}
    monkeypatch.setattr(main.db, "count_usage", lambda uid, kind, since: used["n"])
    used["n"] = 10
    with pytest.raises(Exception) as e:
        main.ai_allowance({"id": "u1", "_plan": "free"})
    assert stop_reason(e) == "You've used all 10 AI builds this month. Basic gives 100."
    used["n"] = 100
    with pytest.raises(Exception) as e:
        main.use_backtest({"id": "u1", "_plan": "basic"})
    assert stop_reason(e) == "You've used all 100 backtests for this month. Pro has no limit on backtests."
    assert main.lift("free", "holdings", "holdings") == " Basic gives 100." and main.lift("basic", "screens", "screens") == " Pro gives 25."
    assert main.lift("free", "live_limit", "paper sessions") == " Basic gives 2." and main.lift("free", "stock_alerts", "x") == " Basic gives 25."
    monkeypatch.setattr(main.db, "update_profile", lambda *a, **k: None)
    try:
        c = as_plan("free")
        r = c.put("/holdings", json={"items": [{"symbol": f"S{i}", "qty": 1} for i in range(31)]})
        assert r.status_code == 402 and r.json()["detail"]["message"] == "Your plan keeps up to 30 stocks in My Holdings. Basic gives 100."
    finally:
        main.app.dependency_overrides.clear()


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
    assert not live.report_on(p("basic", alert_email="a@b.c"))       # an address nobody confirmed isn't a channel
    monkeypatch.setattr(alerts, "email_confirmed", lambda profile: True)
    assert live.report_on(p("basic", alert_email="a@b.c")) and live.alerts_on(p("basic", alerts_enabled=True, alert_email="a@b.c"))
    assert not live.alerts_on({"plan": "free", "alerts_enabled": True, "alert_email": "a@b.c"})     # trade notifications: Basic and up
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
        assert c.put("/me/prefs", json={"level": "pro"}).json() == {"prefs": {"level": "pro", "focus": None, "space": None}}
        assert '"daily_report": false' in store["prefs:u1"] and '"level": "pro"' in store["prefs:u1"]
        # what the user came for is saved alongside, without touching the level
        assert c.put("/me/prefs", json={"focus": "invest"}).json() == {"prefs": {"level": "pro", "focus": "invest", "space": None}}
        # the menu's space is kept too, and "money" is a reason to come
        assert c.put("/me/prefs", json={"focus": "money", "space": "all"}).json() == {"prefs": {"level": "pro", "focus": "money", "space": "all"}}
        assert c.put("/me/prefs", json={"space": "money"}).json()["prefs"]["space"] == "money"
        assert c.put("/me/prefs", json={"space": "bank"}).status_code == 422
        assert c.put("/me/prefs", json={"level": "expert"}).status_code == 422
        assert c.put("/me/prefs", json={"focus": "gamble"}).status_code == 422
        assert main.prefs_of("nobody") == {}
    finally:
        main.app.dependency_overrides.clear()


def test_breakeven_after_costs_is_free(paid, monkeypatch):
    """The builder's preview, with its round-trip charges and breakevens after costs, works on the Free plan."""
    from app.options.data import OptionsData
    from .fake_options_kite import FakeOptionsKite
    monkeypatch.setattr(main, "options_data", OptionsData(FakeOptionsKite(live=True, drift={})))
    try:
        strat = {"underlying": "NIFTY", "legs": [{"side": "sell", "opt": "CE"}, {"side": "sell", "opt": "PE"}],
                 "sizing": {"mode": "lots", "lots": 1}}
        r = as_plan("free").post("/options/preview", json={"strategy": strat})
        assert r.status_code == 200 and r.json()["charges"]["breakevens_after"]
    finally:
        main.app.dependency_overrides.clear()


def test_etf_gap_alerts_are_basic(paid, monkeypatch):
    """The gaps, their history and the badges are for everyone; an alert on the gap is Basic and up, and one set
    before a downgrade isn't checked."""
    from app import etf_nav
    from tests import fake_etf
    rows = etf_nav.parse_exchange(fake_etf.answer())["rows"]
    monkeypatch.setattr(etf_nav, "load_live", lambda: {"read": None, "as_of": None, "rows": rows})
    monkeypatch.setattr(etf_nav, "navs", lambda: {"schemes": {}, "isin": {}})
    monkeypatch.setattr(etf_nav, "_days", lambda: {})
    monkeypatch.setattr(etf_nav, "table", lambda: {"rows": [], "count": len(rows)})
    monkeypatch.setattr(main, "alert_quotes", lambda r, s: {x: {"price": 105.2} for x in s})
    monkeypatch.setattr(main.stock_alerts, "create", lambda uid, body, limit, q: {**body, "id": "abc123", "status": "active"})
    monkeypatch.setattr(main, "alerts_page", lambda profile: {})
    body = {"region": "IN", "symbol": "SILVERBEES", "kind": "etfgap", "op": "above", "value": 2}
    try:
        c = as_plan("free")
        assert c.get("/invest/etf-gaps").json()["alerts"] is False and c.get("/invest/etf-gaps").json()["count"] == 5
        r = c.post("/alerts", json=body)
        assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
        assert c.post("/alerts", json={**body, "kind": "move", "op": "up"}).status_code == 200      # other alerts stay free
        c = as_plan("basic")
        assert c.get("/invest/etf-gaps").json()["alerts"] is True
        assert c.post("/alerts", json=body).status_code == 200
    finally:
        main.app.dependency_overrides.clear()
    monkeypatch.setattr(main.db, "get_setting", lambda k: None)
    assert not main._alert_kind_ok({"id": "u1", "plan": "free"}, "etfgap") and main._alert_kind_ok({"id": "u1", "plan": "free"}, "price")
    assert main._alert_kind_ok({"id": "u1", "plan": "basic", "plan_status": "active"}, "etfgap")


def test_fo_changes_free_to_view_alerts_on_basic(paid, monkeypatch):
    """F&O contract changes: the list and badges for everyone, the alert on Basic and up (turning it off always works)."""
    from tests.fake_db import FakeSupabase
    monkeypatch.setattr(main.db, "_client", FakeSupabase())
    assert FEATURE_PLAN["fo_alerts"] == "basic" and not plan_info("free")["features"]["fo_alerts"]
    try:
        c = as_plan("free")
        assert c.get("/trade/fo-changes").status_code == 200
        r = c.put("/trade/fo-changes/alerts", json={"on": True})
        assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
        assert c.put("/trade/fo-changes/alerts", json={"on": False}).status_code == 200
        for plan in ("basic", "pro"):
            r = as_plan(plan).put("/trade/fo-changes/alerts", json={"on": True})
            assert r.status_code == 200 and r.json()["on"] is True
    finally:
        main.app.dependency_overrides.clear()
