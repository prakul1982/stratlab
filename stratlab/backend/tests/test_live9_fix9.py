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


# ---------- LIVE9A-010 / 023: the heatmap's day count is the breadth count, and placeholders are not companies ----------
def test_a_tiny_fall_is_a_fall_on_the_heatmap():
    from app import heatmap
    days, closes = ["2026-11-12", "2026-11-13"], [250.0, 249.99]          # −0.004%
    assert heatmap.changes(days, closes)[0] < 0


def test_a_placeholder_symbol_is_not_counted_as_a_member(monkeypatch):
    from app import breadth, heatmap
    monkeypatch.setattr(heatmap, "load", lambda region: {"day": "2026-11-16", "stocks": {"AAA": [10.0, 1.0, 0, 0, 0, 0, 0, 1.0, 1.0]}})
    monkeypatch.setattr(breadth, "members", lambda group: ["AAA", "DUMMYHEG"])
    monkeypatch.setattr(heatmap, "_facts", lambda region: ({}, {}))
    v = heatmap.view("IN", "nifty500")
    assert v["members"] == 1 and v["with_prices"] == 1


# ---------- LIVE9A-015: a US offering past its expected day, and a size with the underwriters' option ----------
def test_a_us_offering_past_its_expected_day_is_not_upcoming():
    from datetime import datetime, timezone
    from app import ipo
    now = datetime(2026, 11, 16, 19, 30, tzinfo=timezone.utc)                    # Mon 16 Nov, 14:30 ET
    row = lambda **k: {"market": "US", "name": "X", **k}                          # noqa: E731
    assert ipo.stage_of(row(expected="2026-11-12"), now) == "filed"
    assert ipo.stage_of(row(expected="2026-11-13"), now) == "filed"
    assert ipo.stage_of(row(expected="2026-11-15"), now) == "upcoming"            # a day's grace for the calendar
    assert ipo.stage_of(row(expected="2026-11-18"), now) == "upcoming"
    assert ipo.stage_of(row(expected="2026-11-12", priced="2026-11-12"), now) == "listed"


def test_a_us_size_with_the_underwriters_option_says_so():
    from app import ipo
    s = ipo.sizes({"market": "US", "shares": 825_000_000, "price": 78.0, "amount": 74_002_500_000})
    assert s["basis"] == ipo.OPTION_BASIS and s["base"] == 64_350_000_000
    plain = ipo.sizes({"market": "US", "shares": 10_000_000, "high": 13.0, "amount": 130_000_000})
    assert plain["basis"] == "stated" and "base" not in plain


# ---------- LIVE9A-021: a stored brief's day change follows the exchange's own closes, a special session included ----------
def test_the_9_nov_brief_is_measured_against_the_muhurat_session(monkeypatch):
    from datetime import date
    from app import blog, official_close
    from app.data import calendar as tc
    files = {"2026-11-09": {"NIFTY 50": 25043.85, "NIFTY BANK": 56000.0}, "2026-11-08": {"NIFTY 50": 24986.40, "NIFTY BANK": 55900.0}}
    monkeypatch.setattr(official_close, "index_closes", lambda d, fetch=False, now=None: files.get(d))
    monkeypatch.setattr(tc, "is_trading_day", lambda m, d: d.weekday() < 5 or d.isoformat() == "2026-11-08")
    monkeypatch.setattr(tc, "special_days", lambda m: {"2026-11-08"})
    issue = {"kind": "market", "region": "IN", "day": "2026-11-09", "at": "2026-11-09T19:00:00+05:30",
             "indices": [{"name": "NIFTY 50", "price": 25043.85, "change_pct": 0.06}, {"name": "SENSEX", "price": 81500.0, "change_pct": 0.05},
                         {"name": "NIFTY BANK", "price": 56000.0, "change_pct": 0.3}],
             "sections": [{"title": "Indices", "items": [{"text": "NIFTY 50: 25,043.85, +0.06% on the day"}]}]}
    post = blog.brief_post(issue)
    assert "NIFTY 50 +0.23%" in post["title"]
    text = blog.plain_text(post["blocks"])
    assert "+0.06%" not in text and "+0.23%" in text
    fixed, changed = blog.official_changes("IN", date(2026, 11, 9), issue["indices"])
    assert changed and [i["change_pct"] for i in fixed] == [0.23, None, 0.18]       # SENSEX: no file, the session before was special
    # a US brief and a day without the files are left as they are
    assert blog.official_changes("US", date(2026, 11, 9), issue["indices"]) == (issue["indices"], False)
    assert blog.official_changes("IN", date(2026, 11, 10), issue["indices"])[1] is False


# ---------- LIVE9A-024: a bank with 31 billion shares and a holding company have their market value ----------
def test_large_share_counts_and_holding_companies_keep_their_value():
    from app import stock_pages as sp
    yes = {"region": "IN", "market_cap": 56_600.0, "price": 18.02, "unit": "₹ crore", "market_cap_unit": "₹ crore",
           "years": [{"year": "Mar 2026", "sales": 30_000.0, "profit": 2_400.0}]}
    assert sp.cap_problem(yes) is None and sp.shown_cap(yes) == 56_600.0
    holding = {"region": "IN", "market_cap": 130_000.0, "price": 11_700.0, "unit": "₹ crore", "market_cap_unit": "₹ crore",
               "years": [{"year": "Mar 2026", "sales": 1_500.0, "profit": 7_000.0}]}
    assert sp.cap_problem(holding) is None
    # still caught: a value 1,000 times off, with no profit to bear it out
    assert sp.cap_problem({**holding, "market_cap": 130_000_00.0, "years": [{"year": "Mar 2026", "sales": 1_500.0, "profit": 7_000.0}]}) is not None
    assert sp.cap_problem({**yes, "market_cap": 56_600_000.0}) is not None


# ---------- LIVE9A-011 / 020: public theme pages as sorted tables, one title pattern, short card names with a count ----------
def test_public_theme_layers_are_tables_sorted_by_value_with_clean_names(monkeypatch):
    from app import public_themes as pt
    payload = {"summary": "Companies that build ships.", "value_chain": [{"layer": "Ships", "companies": [
        {"ticker": "SMALL", "name": "SMALL SHIPS INC", "verified": True, "what": "builds ships"},
        {"ticker": "BIG", "name": "Bank Of Montreal /can/", "verified": True, "what": "builds ships"},
        {"ticker": "NONE", "name": "No Value Ltd", "verified": True, "what": "builds ships"}]}]}
    monkeypatch.setattr(pt, "_dive", lambda r, n, p: {})
    monkeypatch.setattr(pt, "_index_caps", lambda r: {"SMALL": 500.0, "BIG": 90_000.0})
    monkeypatch.setattr(pt, "_price_day", lambda r, syms: "2026-11-16")
    monkeypatch.setattr(pt.stock_pages, "companies", lambda r: set())
    v = pt.view({"region": "IN", "name": "Ships", "label": "Capital goods (India)", "slug": "ships", "at": None}, payload)
    assert [c["symbol"] for c in v["layers"][0]["companies"]] == ["BIG", "SMALL", "NONE"]
    assert [c["name"] for c in v["layers"][0]["companies"]][:2] == ["Bank of Montreal", "Small Ships Inc"]
    page = pt.render(v)
    assert "<table" in page and '<th scope="col">Market value</th>' in page
    assert "<h1>Capital goods <span" in page and "Listed companies in India" in page and "(India) companies" not in page
    assert "market values at the 16 Nov 2026 close" in page
    assert page.index("data-layer") < page.index("About the theme")               # companies before the paragraph
    assert pt.short_label("Utilities (Indian power, gas and water-linked infrastructure)") == "Utilities"
    assert pt.short_label("FMCG (Fast Moving Consumer Goods)") == "FMCG"
    assert pt.short_label("Defence (India)") == "Defence" and pt.short_label("Private banks") == "Private banks"


def test_the_directory_cards_say_market_count_and_date(monkeypatch):
    from app import public_themes as pt
    monkeypatch.setattr(pt, "payload", lambda x: {"value_chain": [{"layer": "A", "companies": [{"ticker": "X", "name": "X", "verified": True, "what": "w"},
                                                                                              {"ticker": "Y", "name": "Y", "verified": True, "what": "w"}]}]})
    line = pt.card_line({"region": "IN", "at": 1763251200})
    assert line.startswith("India · 2 companies · ") and "Nov" in line
