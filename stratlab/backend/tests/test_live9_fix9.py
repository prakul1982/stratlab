"""Lane fix9: the LIVE9A / LIVE9B review findings outside the theme engine (Mood, plans, calendars, flows, breadth, public pages)."""
import threading

import pytest

from app import main  # noqa: F401, I001


# ---------- LIVE9A-008: the headlines read is never a request held open behind another visit's ----------
def test_a_read_someone_else_is_writing_answers_at_once_when_asked_not_to_wait(monkeypatch):
    from fastapi import HTTPException
    from app.intel import ai as A
    from app.intel import routes
    key = ("IN", "", "close", ("k",), None, "mood2")
    monkeypatch.setattr(A, "peek", lambda kind, k: False)
    lock = threading.Lock()
    lock.acquire()
    routes._building[repr(("pulse", key))] = lock
    try:
        with pytest.raises(HTTPException) as e:
            routes.ai_call({"id": "u"}, "pulse", key, 60, False, lambda: {"x": 1}, counted=False, wait_for_other=False)
        assert e.value.status_code == 503 and e.value.detail["code"] == "ai_busy" and "being written now" in e.value.detail["message"]
    finally:
        lock.release()
        routes._building.pop(repr(("pulse", key)), None)


def test_the_pulse_read_does_not_wait_for_another_visit():
    import inspect
    from app.intel import routes
    assert "wait_for_other=False" in inspect.getsource(routes.pulse_ai)


def test_wire_headlines_must_be_about_business():
    from app.newsletter.content import BUSINESS_WORDS, OFF_TOPIC
    for t in ("Robert Pattinson cast as next James Bond", "Bulgaria rescues crew from capsized wheat ship"):
        assert not BUSINESS_WORDS.search(t) or OFF_TOPIC.search(t), t
    assert OFF_TOPIC.search("Scores of Bahraini Shi'ite clerics get life in jail")
    for t in ("Nvidia shares slide as chip curbs widen", "Pfizer to buy Metsera in $4.9 billion deal", "Home Depot cuts annual sales forecast"):
        assert BUSINESS_WORDS.search(t), t


def test_the_us_wire_feed_drops_stories_that_are_not_business(monkeypatch):
    from app.intel import company
    r = company.Research.__new__(company.Research)

    class F:
        def ready(self):
            return True

        def market_news(self):
            return [{"headline": h, "url": f"https://x/{i}", "source": "Reuters", "datetime": 1763300000 + i}
                    for i, h in enumerate(["Robert Pattinson cast as next James Bond", "Pfizer to buy Metsera in $4.9 billion deal",
                                           "Bulgaria rescues crew from capsized wheat ship", "Stocks fall as tech slides"])]
    r.finnhub = F()
    got = [h["headline"] for h in r.headlines("US")]
    assert got and "Robert Pattinson cast as next James Bond" not in got and "Bulgaria rescues crew from capsized wheat ship" not in got
    assert "Pfizer to buy Metsera in $4.9 billion deal" in got


# ---------- LIVE9A-003: what Plans publishes per plan is what the server enforces, and a grace count says it is one ----------
from datetime import datetime, timedelta  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, plans  # noqa: E402
from app.config import settings  # noqa: E402
from app.plans import LIMIT_KEYS, PLANS  # noqa: E402

CHANGE = "2026-11-13T00:00:00+05:30"
AT = datetime.fromisoformat(CHANGE)
BEFORE, AFTER = (AT - timedelta(days=30)).isoformat(), (AT + timedelta(days=1)).isoformat()


@pytest.fixture
def plan_env(monkeypatch, time_machine):
    monkeypatch.setattr(settings, "FREE_TIER_CHANGE_AT", CHANGE)
    monkeypatch.setattr(settings, "RESEARCH_AI_PER_DAY", 60)
    monkeypatch.setattr(plans, "promo_active", lambda now=None: False)
    time_machine.move_to(AT + timedelta(days=3))
    usage = []
    monkeypatch.setattr(db, "count_usage", lambda uid, kind, since: usage.count(kind))
    monkeypatch.setattr(db, "add_usage", lambda uid, kind: usage.append(kind))
    return usage


def _who(plan, made=AFTER):
    base = {"id": "u1", "plan": plan, "_plan": plan, "_paid_plan": plan, "created_at": made}
    return base if plan == "free" else {**base, "plan_status": "active"}


@pytest.mark.parametrize("plan", ["free", "basic", "pro"])
@pytest.mark.parametrize("key", LIMIT_KEYS)
def test_each_published_limit_is_the_enforced_one(plan_env, plan, key):
    # one test per limit and plan: the number /pricing gives the Plans page (public_plans) is the one each request reads (limit_of, plan_info)
    published = plans.public_plans()[plan][key]
    who = _who(plan)
    assert plans.plan_info(plan, who)[key] == published, (plan, key)
    if key == "ai_reads_per_day":
        from app.intel import routes
        assert routes.ai_cap(who) == published                      # the daily fresh-read cap the AI routes hold a person to
    elif key in plans.FREE_BEFORE:
        assert plans.limit_of(who, key) == published


def test_free_after_the_change_gets_no_theme_deck_from_the_route(plan_env, monkeypatch):
    # the theme deck route itself refuses a Free account (the sample deck only); a Basic one is counted
    from app import main
    from app.intel import theme_routes
    monkeypatch.setattr(theme_routes, "map_for_deck", lambda R, profile, region, q, wait=0, pending=None: ("US", "Semiconductors", {}))
    monkeypatch.setattr(theme_routes, "_routes", lambda: None)
    with pytest.raises(HTTPException) as e:
        theme_routes.theme_dive_deck("Semiconductors", "US", "pdf", profile=_who("free"))
    assert e.value.status_code == 402 and e.value.detail["code"] == "deck_limit"
    assert e.value.detail["message"].startswith("Slide decks are on Basic: 5 a month.")
    assert main.check_deep(_who("basic"), "deck", "", "US", mark="deck:theme:US:semiconductors") == "deck:theme:US:semiconductors"
    assert plan_env == []


def test_free_after_the_change_is_held_to_five_fresh_reads(plan_env):
    from app import computed
    from app.intel import routes
    new = _who("free")
    assert routes.ai_cap(new) == 5 and not plans.refreshes_allowed("free", new)
    assert computed.refresh_gate(new, "theme", 1.0) != "go"


def test_my_usage_says_a_grace_count_is_kept_until_a_date(plan_env):
    from app import main
    for who, grace in ((_who("free", BEFORE), True), (_who("free", AFTER), False), (_who("basic", BEFORE), False)):
        main.app.dependency_overrides[main.current_profile] = lambda who=who: who
        try:
            u = TestClient(main.app).get("/me/usage").json()
        finally:
            main.app.dependency_overrides.clear()
        rows = {r["key"]: r for r in u["rows"]}
        if grace:
            assert u["grace"]["until"].startswith((AT + timedelta(days=plans.FREE_GRACE_DAYS)).date().isoformat())
            assert (u["grace"]["reads_after"], u["grace"]["decks_after"]) == (5, 0)
            assert rows["research_ai"]["limit"] == 60 and rows["deck"]["limit"] == 1
        else:
            assert u["grace"] is None
