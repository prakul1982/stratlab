"""FREE-TIER (owner, Nov: "we aren't giving much for free; the public stuff is only to attract people"): Free's smaller limits, Basic and
Pro unchanged, the 14-day grace for accounts made before the change and its one-time notice, a Free reader sharing the Basic/Pro company
read, a new theme counted once, Free's 0 decks and the sample deck, the tax report's downloads on Basic, and the plan copy saying so."""
import base64
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import db, plans
from app.config import settings
from app.plans import FREE_BEFORE, PLANS

CHANGE = "2026-11-16T00:00:00+05:30"
AT = datetime.fromisoformat(CHANGE)
BEFORE = (AT - timedelta(days=30)).isoformat()          # an account made a month before the change
AFTER = (AT + timedelta(days=1)).isoformat()            # one made the day after


@pytest.fixture(autouse=True)
def _change_date(monkeypatch):
    monkeypatch.setattr(settings, "FREE_TIER_CHANGE_AT", CHANGE)
    monkeypatch.setattr(settings, "RESEARCH_AI_PER_DAY", 60)


def free(made=AFTER, **kw):
    return {"id": "u1", "plan": "free", "_plan": "free", "_paid_plan": "free", "created_at": made, **kw}


def paid(plan, **kw):
    return {"id": "u1", "plan": plan, "plan_status": "active", "_plan": plan, "_paid_plan": plan, "created_at": BEFORE, **kw}


# ---------- the limits ----------
def test_free_limits_are_the_teaser_ones():
    f = PLANS["free"]
    assert (f["backtests_per_month"], f["ai_builds_per_month"], f["group_size"], f["stock_alerts"], f["screens"]) == (5, 5, 5, 3, 1)
    assert (f["deepdives_per_month"], f["decks_per_month"], f["themes_per_month"], f["ai_reads_per_day"], f["search_ai_per_day"]) == (1, 0, 1, 5, 10)
    assert not plans.refreshes_allowed("free")
    assert "tax_export" not in f["features"] and plans.FEATURE_PLAN["tax_export"] == "basic"
    # what Free keeps: holdings, funds, net worth, the journal, Market Watch, the trial
    assert (f["holdings"], f["mf_schemes"], f["networth_items"], f["journal_trades"], f["live_limit"], f["live_trial_days"]) == (30, 5, 5, 50, 1, 5)


def test_basic_and_pro_do_not_change():
    b, p = PLANS["basic"], PLANS["pro"]
    assert (b["backtests_per_month"], b["ai_builds_per_month"], b["group_size"], b["stock_alerts"], b["screens"], b["deepdives_per_month"],
            b["decks_per_month"], b["search_ai_per_day"]) == (100, 100, 25, 25, 10, 15, 5, 40)
    assert (p["backtests_per_month"], p["ai_builds_per_month"], p["group_size"], p["stock_alerts"], p["screens"], p["deepdives_per_month"],
            p["decks_per_month"], p["search_ai_per_day"]) == (None, None, 50, 100, 25, None, None, 40)
    assert plans.refreshes_allowed("basic") and plans.refreshes_allowed("pro")      # each Refresh one fresh AI read (LIVE7B-002)
    assert plans.ai_reads_per_day("basic") == 60 and plans.ai_reads_per_day("pro") is None and plans.ai_reads_per_day("free") == 5
    # the new theme limit (Free 1, Basic 10, Pro none) and the downloads both paid plans have
    assert (b["themes_per_month"], p["themes_per_month"]) == (10, None)
    assert "tax_export" in b["features"] and "tax_export" in p["features"]


def test_basic_ai_reads_still_follow_the_setting(monkeypatch):
    monkeypatch.setattr(settings, "RESEARCH_AI_PER_DAY", 7)
    assert plans.ai_reads_per_day("basic") == 7 and plans.ai_reads_per_day("free") == 5


# ---------- the grace for accounts made before the change ----------
def test_grace_is_for_accounts_made_before_the_change_for_14_days():
    end = AT + timedelta(days=14)
    assert plans.free_grace_until(free(BEFORE), now=AT + timedelta(days=3)) == end
    assert plans.free_grace_until(free(BEFORE), now=AT - timedelta(days=3)) == end      # deployed ahead of the date: kept until then too
    assert plans.free_grace_until(free(BEFORE), now=end + timedelta(seconds=1)) is None
    assert plans.free_grace_until(free(AFTER), now=AT + timedelta(days=3)) is None      # a new account: the new limits at once
    assert plans.free_grace_until({"id": "x", "_plan": "free"}, now=AT) is None          # no date: the new limits
    assert plans.free_grace_until(free(BEFORE, _view_as="free"), now=AT) is None         # the owner's View as shows the plan as it is


def test_an_old_account_keeps_the_old_counts_and_a_new_one_gets_the_new(time_machine):
    time_machine.move_to(AT + timedelta(days=2))
    old, new = free(BEFORE), free(AFTER)
    for key, before in FREE_BEFORE.items():
        assert plans.limit_of(old, key) == before, key
        assert plans.limit_of(new, key) == PLANS["free"][key], key
    assert plans.refreshes_allowed("free", old) and not plans.refreshes_allowed("free", new)
    assert plans.ai_reads_per_day(old) == 60 and plans.ai_reads_per_day(new) == 5
    assert plans.allows_for(old, "tax_export") and not plans.allows_for(new, "tax_export")
    info = plans.plan_info("free", old)
    assert (info["backtests_per_month"], info["deepdives_per_month"], info["decks_per_month"], info["stock_alerts"], info["screens"]) == (10, 2, 1, 5, 2)
    assert info["features"]["tax_export"] is True and plans.plan_info("free", new)["features"]["tax_export"] is False
    # a paid plan is never touched, whenever the account was made
    assert plans.limit_of(paid("basic"), "backtests_per_month") == 100
    time_machine.move_to(AT + timedelta(days=15))           # the grace is over: the old account has the new limits too
    assert plans.limit_of(old, "backtests_per_month") == 5 and plans.ai_reads_per_day(old) == 5


def test_the_notice_says_exactly_what_changes_and_when(time_machine):
    time_machine.move_to(AT + timedelta(days=2))
    n = plans.free_change_notice(free(BEFORE))
    assert n["on"] == (AT + timedelta(days=14)).isoformat()
    rows = {r["key"]: (r["before"], r["after"]) for r in n["rows"]}
    assert rows == {"ai_reads_per_day": (60, 5), "search_ai_per_day": (40, 10), "themes_per_month": (None, 1),
                    "backtests_per_month": (10, 5), "ai_builds_per_month": (10, 5), "deepdives_per_month": (2, 1), "decks_per_month": (1, 0),
                    "stock_alerts": (5, 3), "screens": (2, 1), "group_size": (10, 5)}
    assert n["moves"] == ["Refreshing a stored read (each Refresh is one fresh AI read) moves to Basic",
                          "The tax report's CSV and PDF downloads move to Basic (the report on screen stays free)"]
    assert plans.free_change_notice(free(AFTER)) is None and plans.free_change_notice(paid("basic")) is None


# ---------- each limit enforced ----------
@pytest.fixture
def counts(monkeypatch):
    usage = []
    monkeypatch.setattr(db, "count_usage", lambda uid, kind, since: usage.count(kind))
    monkeypatch.setattr(db, "add_usage", lambda uid, kind: usage.append(kind))
    return usage


def _code(fn, *a):
    with pytest.raises(HTTPException) as e:
        fn(*a)
    return e.value.status_code, e.value.detail


def test_backtests_ai_builds_and_group_size(counts):
    from app import main
    counts.extend(["backtest"] * 4)
    assert main.use_backtest(free()) == 5
    counts.append("backtest")
    status, d = _code(main.use_backtest, free())
    assert status == 402 and "You've used all 5 backtests this month" in d["message"] and "Basic gives 100 a month." in d["message"]
    counts.extend(["ai"] * 5)
    status, d = _code(main.ai_allowance, free())
    assert status == 429 and "You've used all 5 AI builds this month" in d["message"]
    main.check_group_size(free(), 5)
    status, d = _code(main.check_group_size, free(), 6)
    assert status == 402 and "groups of up to 5 instruments" in d["message"]


def test_backtests_and_groups_in_the_grace(counts, time_machine):
    from app import main
    time_machine.move_to(AT + timedelta(days=1))
    counts.extend(["backtest"] * 9)
    assert main.use_backtest(free(BEFORE)) == 10
    main.check_group_size(free(BEFORE), 10)


def test_alerts_and_screens():
    from app import main
    assert main.stock_alert_limit(free()) == 3 and main.screens_limit(free()) == 1
    assert main.stock_alert_limit(paid("basic")) == 25 and main.screens_limit(paid("pro")) == 25


def test_daily_ai_caps_name_the_next_plan(monkeypatch):
    from app.intel import routes
    monkeypatch.setattr(routes, "ai_reads_today", lambda p: 0)
    assert routes.ai_cap(free()) == 5 and routes.ai_cap(paid("basic")) == 60 and routes.ai_cap(paid("pro")) is None
    assert routes.search_cap(free()) == 10 and routes.search_cap(paid("basic")) == 40 and routes.search_cap(paid("pro")) == 40
    assert routes.more_words(free(), "ai") == " Basic gives 60 a day." and routes.more_words(free(), "search") == " Basic gives 40 a day."
    assert routes.more_words(paid("basic"), "ai") == ""


def test_a_free_reader_past_five_reads_is_told_basic_gives_sixty(counts):
    from app.intel import routes
    counts.extend(["research_ai"] * 5)
    status, d = _code(lambda: routes.read_slot(free(), routes.ai_cap(free())).__enter__())
    assert status == 429 and d["code"] == "research_ai_limit"
    assert d["message"].startswith("You've used today's 5 fresh AI reads on your plan.") and d["message"].endswith("Basic gives 60 a day.")
    counts.extend(["search_ai"] * 10)
    status, d = _code(lambda: routes.read_slot(free(), routes.search_cap(free()), routes.SEARCH_KIND).__enter__())
    assert status == 429 and "today's 10 AI answers in the search box" in d["message"] and d["message"].endswith("Basic gives 40 a day.")


def test_free_has_no_refreshes(counts, monkeypatch):
    # (updated on purpose: a Refresh is one fresh AI read, LIVE7B-002, held to the plan's daily count; Free has none)
    from app import computed
    monkeypatch.setattr(computed, "_now", lambda: 1e9)
    assert computed.refresh_gate(free(), "theme", 1.0) == "capped" and counts == []
    assert computed.refresh_gate(paid("basic"), "theme", 1.0) == "go"
    counts.extend(["research_ai"] * 60)                    # Basic's 60 reads used: its Refresh is held too
    assert computed.refresh_gate(paid("basic"), "theme", 1.0) == "capped"
    assert computed.refresh_gate(free(), "mood", 1.0, capped=False) == "go"     # a read no one's count holds (the market mood)


def test_free_refreshes_in_the_grace(counts, monkeypatch, time_machine):
    from app import computed
    time_machine.move_to(AT + timedelta(days=1))
    monkeypatch.setattr(computed, "_now", lambda: 1e9)
    old = free(BEFORE)
    assert computed.refresh_gate(old, "theme", 1.0) == "go"          # held to its old 60 fresh AI reads
    counts.extend(["research_ai"] * 60)
    assert computed.refresh_gate(old, "theme", 1.0) == "capped"


# ---------- decks: none on Free, and the lock reads well for 0 ----------
def test_zero_decks_reads_as_on_basic(counts):
    from app import main
    status, d = _code(main.check_deep, free(), "deck", "AAA", "IN")
    assert status == 402 and d["code"] == "deck_limit"
    # (while no plan can be bought, upgrade_note adds how to get early access after it)
    assert d["message"].startswith("Slide decks are on Basic: 5 a month. The sample deck on the Plans page shows what one holds.")
    assert "0 slide deck" not in d["message"] and "You've made" not in d["message"] and counts == []
    assert plans.not_on_plan("free", "decks_per_month", "Slide decks") == "Slide decks are on Basic: 5 a month."


def test_one_deep_dive_a_month(counts):
    from app import main
    assert main.check_deep(free(), "deepdive", "AAA", "IN") == "deepdive:IN:AAA"
    counts.extend(["deepdive", "deepdive:IN:AAA"])
    assert main.check_deep(free(), "deepdive", "AAA", "IN") is None              # the same company again: free
    status, d = _code(main.check_deep, free(), "deepdive", "BBB", "IN")
    assert status == 402 and "You've opened 1 company in the deep dive this month" in d["message"] and "Basic gives 15 a month." in d["message"]


def test_an_old_account_still_has_its_deck_in_the_grace(counts, time_machine):
    from app import main
    time_machine.move_to(AT + timedelta(days=1))
    assert main.check_deep(free(BEFORE), "deck", "AAA", "IN") == "deck:IN:AAA"


# ---------- new themes ----------
def test_a_new_theme_counts_once_and_free_has_one_a_month(counts, monkeypatch):
    from app.intel import routes
    monkeypatch.setattr(routes.theme_routes, "job_of", lambda key: None)
    routes.use_theme(free(), "IN", "India defence", ("IN", "india defence"))
    routes.use_theme(free(), "IN", "defence stocks", ("IN", "defence stocks"))     # the same theme, written another way: not again
    assert counts.count("theme") == 1
    status, d = _code(routes.use_theme, free(), "IN", "railways", ("IN", "railways"))
    assert status == 402 and d["code"] == "theme_limit"
    assert "You've had 1 new theme mapped this month" in d["message"] and "Every theme already in the library still opens." in d["message"]
    assert "Basic gives 10 a month." in d["message"]
    for i in range(9):                                       # Basic: 10 a month
        routes.use_theme(paid("basic"), "IN", f"theme {i}", ("IN", f"theme {i}"))
    assert counts.count("theme") == 10
    routes.use_theme(paid("pro"), "IN", "anything", ("IN", "anything"))           # Pro: no limit, nothing counted
    assert counts.count("theme") == 10


def test_a_map_someone_else_is_writing_never_counts(counts, monkeypatch):
    from app.intel import routes
    monkeypatch.setattr(routes.theme_routes, "job_of", lambda key: {"state": "running"})
    counts.append("theme")
    routes.use_theme(free(), "IN", "railways", ("IN", "railways"))
    assert counts == ["theme"]


def test_the_theme_library_stays_open_on_free(counts, monkeypatch):
    """A theme already in the library is served from it and counts nothing, even with Free's one new theme used."""
    from app import main
    from app.intel import routes, theme_library
    counts.append("theme")
    monkeypatch.setattr(theme_library, "stored", lambda r, q: {"payload": {"sector": "Defence", "screen": []}, "at": 1.0, "name": "defence"})
    monkeypatch.setattr(routes, "sector_served", lambda r, payload: payload)
    main.app.dependency_overrides[main.current_profile] = lambda: free()
    try:
        r = TestClient(main.app).get("/research/sector?q=India%20defence&region=IN")
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 200 and r.json()["sector"] == "Defence" and counts == ["theme"]


# ---------- the tax report's downloads ----------
def test_tax_downloads_are_on_basic(counts):
    from app import main
    status, d = _code(main.tax_export_file, 2025, "csv", free())
    assert status == 402 and d["message"].startswith("The tax report's CSV and PDF downloads are on the Basic plan.")


def test_tax_downloads_pass_the_gate_on_basic_and_in_the_grace(monkeypatch, time_machine):
    from app import main

    class Past(Exception):
        pass

    def stop(*a, **k):
        raise Past()
    monkeypatch.setattr(main, "throttle", stop)               # the next step after the plan check
    with pytest.raises(Past):
        main.tax_export_file(2025, "csv", paid("basic"))
    time_machine.move_to(AT + timedelta(days=1))
    with pytest.raises(Past):
        main.tax_export_file(2025, "csv", free(BEFORE))


# ---------- the shared company read ----------
def test_a_free_reader_gets_the_basic_pro_read(monkeypatch):
    from app.intel import routes
    have = set()
    monkeypatch.setattr(routes.A, "peek", lambda kind, key: (kind, key) in have)
    assert routes.company_read_key("IN", "TCS", True) == ("IN", "TCS", True)
    assert routes.company_read_key("IN", "TCS", False) == ("IN", "TCS", True)         # nothing written: the new read is the shared one
    have.add(("company", ("IN", "TCS", False)))
    assert routes.company_read_key("IN", "TCS", False) == ("IN", "TCS", False)        # a Free read written before still opens
    have.add(("company", ("IN", "TCS", True)))
    assert routes.company_read_key("IN", "TCS", False) == ("IN", "TCS", True)         # the Basic/Pro read, once there is one


def test_a_free_reader_opening_a_company_basic_already_read_costs_nothing(counts, monkeypatch):
    """Through the route: a Free reader asks for a company whose Basic/Pro read is stored; it is served, no AI call, nothing counted."""
    from app import main
    from app.intel import routes
    stored = {"company": {("US", "NVDA", True): {"summary": "stored", "generated_at": 5}}}
    asked = []
    monkeypatch.setattr(routes.A, "peek", lambda kind, key: key in stored.get(kind, {}))
    monkeypatch.setattr(routes.A, "cached", lambda kind, key, ttl, refresh, build, by=None: (asked.append(key) or (stored[kind][key], False)))
    monkeypatch.setattr(routes.A, "clean_company", lambda read: read)
    main.app.dependency_overrides[main.current_profile] = lambda: free()
    try:
        r = TestClient(main.app).get("/research/company/US/NVDA/ai")
    finally:
        main.app.dependency_overrides.clear()
    assert r.status_code == 200 and r.json()["summary"] == "stored"
    assert asked == [("US", "NVDA", True)] and counts == []


# ---------- the sample deck ----------
def test_the_sample_deck_is_the_kept_theme_pdf(monkeypatch):
    from app import computed, main, sample_deck
    rows = [{"id": "a", "label": "Railways (PDF, 2026-11-10)", "region": "IN"},
            {"id": "b", "label": "India defence (PPTX, 2026-11-09)", "region": "IN"},
            {"id": "c", "label": "India defence (PDF, 2026-11-08)", "region": "IN"}]
    assert sample_deck.pick(rows)["id"] == "c"                        # the fixed theme's newest PDF
    assert sample_deck.pick(rows[:2])["id"] == "a"                    # not kept: the newest PDF of any theme
    assert sample_deck.pick(rows[1:2]) is None
    monkeypatch.setattr(computed, "entries", lambda kind, q="", region="", limit=500: rows if kind == "deck:theme" else [])
    monkeypatch.setattr(computed, "get_hk", lambda kind, hk: {"value": base64.b64encode(b"%PDF-sample").decode()} if hk == "c" else None)
    c = TestClient(main.app)                                          # no sign-in: a visitor
    info = c.get("/pricing/sample-deck/info").json()
    assert info == {"available": True, "theme": "India defence", "region": "IN"}
    r = c.get("/pricing/sample-deck")
    assert r.status_code == 200 and r.content == b"%PDF-sample" and r.headers["content-type"] == "application/pdf"
    assert 'filename="stratlab-sample-deck-india-defence.pdf"' in r.headers["content-disposition"]


def test_no_sample_deck_kept_says_so(monkeypatch):
    from app import computed, main
    monkeypatch.setattr(computed, "entries", lambda kind, q="", region="", limit=500: [])
    c = TestClient(main.app)
    assert c.get("/pricing/sample-deck/info").json()["available"] is False
    r = c.get("/pricing/sample-deck")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_sample_deck"


# ---------- /me ----------
def test_me_carries_the_notice_and_the_theme_count(counts, monkeypatch, time_machine):
    from app import main
    time_machine.move_to(AT + timedelta(days=1))
    for name in ("seen",):
        monkeypatch.setattr(main.lifecycle, name, lambda p: None)
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: None, raising=False)
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    counts.append("theme")
    for who, notice in ((free(BEFORE), True), (free(AFTER), False)):
        main.app.dependency_overrides[main.current_profile] = lambda who=who: who
        try:
            me = TestClient(main.app).get("/me").json()
        finally:
            main.app.dependency_overrides.clear()
        assert (me["free_change"] is not None) is notice
        assert me["usage"]["theme_used"] == 1
        assert me["usage"]["theme_limit"] == (None if notice else 1)
        assert me["plan_info"]["backtests_per_month"] == (10 if notice else 5)
        assert me["usage"]["ai_reads_limit"] == (60 if notice else 5)


def test_my_usage_says_free_has_no_refresh(counts, monkeypatch, time_machine):
    # a Refresh is one fresh AI read (LIVE7B-002): no separate refresh row; Free outside its grace is told Refresh is on Basic
    from app import main
    time_machine.move_to(AT + timedelta(days=1))
    for who, off in ((free(AFTER), True), (free(BEFORE), False), (paid("basic"), False)):
        main.app.dependency_overrides[main.current_profile] = lambda who=who: who
        try:
            u = TestClient(main.app).get("/me/usage").json()
        finally:
            main.app.dependency_overrides.clear()
        rows = {r["key"]: r for r in u["rows"]}
        assert u["refresh_off"] is off and "refresh" not in rows
        assert rows["research_ai"]["label"] == "Fresh AI reads, refreshes included"
