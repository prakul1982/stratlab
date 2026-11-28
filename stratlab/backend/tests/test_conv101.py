"""Lane conv101 (owner, 27 Nov: "I need to make money now"; the funnel report: the server-drawn pages untracked with their ways in buried, nothing
to try without an account, the owner's own visits 92% of the numbers, sign-ups and checkouts counted by the browser only). The server's side:
the pageview beacon and ?from= on every page it draws, StratLab's own accounts left out, sign-up and checkout events from the server, a
visitor's one try, the stock page's way in at the top and its peers by size, the theme page's way in and deck preview, the sample deck's own
page, and the theme deck's footer address."""
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on it)
from app import db, guard, guest_try, product_analytics, public_themes, sample_deck, screens, stock_pages
from app.config import settings
from tests import world
from tests.fake_db import headers

KEY = "phc_conv101TestKey"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    guest_try.forget()
    yield built
    built["close"]()


@pytest.fixture
def posts(monkeypatch):
    """PostHog's capture calls, sent in the calling thread."""
    sent = []
    monkeypatch.setattr(product_analytics, "BACKGROUND", False)
    monkeypatch.setattr(product_analytics.httpx, "post", lambda url, json=None, timeout=None: sent.append(json) or SimpleNamespace(status_code=200, text=""))
    monkeypatch.setattr(settings, "POSTHOG_KEY", KEY)
    return sent


# ---------- T1: the beacon and ?from= on every page the server draws ----------
def test_every_server_page_carries_the_beacon_with_its_kind_and_its_app_links_say_where_they_came_from(w, monkeypatch):
    monkeypatch.setattr(settings, "POSTHOG_KEY", KEY)
    c = w["client"]
    stock_pages._thin.clear()
    for url, kind in (("/stocks/in/RELIANCE", "stock"), ("/stocks", "directory"), ("/stocks/in", "directory"), ("/blog", "blog"),
                      ("/themes", "theme"), ("/status", "status"), ("/sample-deck", "sample-deck")):
        r = c.get(url)
        assert r.status_code == 200, url
        tag = re.search(r'<script src="/stocks/pv\.js\?v=(\w+)" data-k="([^"]+)" data-kind="([^"]+)" defer></script></body>', r.text)
        assert tag, url
        assert tag.group(1) == stock_pages.PV_JS_V and tag.group(2) == KEY and tag.group(3) == kind, url
        # every link into the app carries ?from=<kind> (the header's Sign in too)
        for href in re.findall(r'href="(https://stratlab\.studio/(?:research|new|mine)[^"]*)"', r.text):
            assert f"from={kind}" in href, (url, href)
        # the page may run the site's own script and post to its own address, and nothing else
        csp = r.headers["content-security-policy"]
        assert "script-src 'self';" in csp and "connect-src 'self';" in csp and "'unsafe-inline'" not in csp.split("style-src")[0], url
    page = c.get("/stocks/in/RELIANCE").text
    assert 'href="https://stratlab.studio/new?market=IN&amp;symbol=RELIANCE&amp;from=stock"' in page
    assert 'href="https://stratlab.studio/research/IN/RELIANCE?from=stock" rel="nofollow">Sign in</a>' in page
    # no key, no beacon (and nothing else changes)
    monkeypatch.setattr(settings, "POSTHOG_KEY", "")
    stock_pages._thin.clear()
    assert "/stocks/pv.js" not in c.get("/blog").text
    # the API's other pages stay script-free
    assert "script-src" not in (c.get("/unsubscribe", params={"t": "bad"}).headers.get("content-security-policy") or "")
    js = c.get("/stocks/pv.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript") and js.text == stock_pages.PV_JS


def test_from_is_added_once_before_a_hash_and_only_to_links_into_the_app():
    assert stock_pages._with_from("https://stratlab.studio/research/IN/X#co-numbers", "stock") == "https://stratlab.studio/research/IN/X?from=stock#co-numbers"
    assert stock_pages._with_from("https://stratlab.studio/new?market=IN&amp;symbol=X", "stock") == "https://stratlab.studio/new?market=IN&amp;symbol=X&amp;from=stock"
    assert stock_pages._with_from("https://stratlab.studio/mine?from=blog", "stock") == "https://stratlab.studio/mine?from=blog"
    html = stock_pages._mark_app_links('<a href="https://stratlab.studio/pricing">Plans</a><a href="https://stratlab.studio/mine">Open</a>', "theme")
    assert 'href="https://stratlab.studio/pricing">' in html and 'href="https://stratlab.studio/mine?from=theme" rel="nofollow">Open (needs sign-in)</a>' in html


def test_the_beacon_keeps_the_apps_rules():
    pv = stock_pages.PV_JS
    for rule in ("n.doNotTrack", "globalPrivacyControl === true", "n.webdriver === true", '"stratlab.internal"', "HeadlessChrome",
                 'fetch("/ingest/i/v0/e/"', "location.origin + location.pathname", '$process_person_profile: false'):
        assert rule in pv, rule
    assert "document.cookie" not in pv and "location.search, " not in pv


def test_the_csp_rule_covers_the_site_pages_and_nothing_else():
    for path in ("/stocks", "/stocks/in/browse/r", "/themes/in/defence", "/blog/x", "/status", "/sample-deck"):
        assert dict(guard.security_headers(path, True))[b"content-security-policy"] == guard.CHART_CSP[1], path
    for path in ("/unsubscribe", "/v/abc", "/email/confirm", "/sample-deck.pdf"):
        assert dict(guard.security_headers(path, True))[b"content-security-policy"] == guard.HTML_CSP[1], path


# ---------- T2: StratLab's own accounts ----------
def test_admins_their_test_aliases_recorded_tests_and_listed_addresses_are_internal(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    monkeypatch.setattr(settings, "ANALYTICS_INTERNAL_EMAILS", "tester@example.org, other@example.org")
    monkeypatch.setattr(db, "get_setting", lambda k: '{"u-rec": {"email": "x@y.z"}}' if k == "test-accounts" else None)
    assert product_analytics.internal({"id": "a", "email": "Owner@Example.com"})
    assert product_analytics.internal({"id": "b", "email": "owner+sl-free@example.com"})
    assert product_analytics.internal({"id": "c", "email": "other@example.org"})
    assert product_analytics.internal({"id": "u-rec", "email": "someone@else.com"})
    assert not product_analytics.internal({"id": "d", "email": "someone@else.com"})
    assert not product_analytics.internal({"id": "e", "email": "owner+friend@example.com"}), "a + alias that isn't a test account's"
    assert not product_analytics.internal(None)


def test_me_says_internal_for_the_owner_and_not_for_a_customer(w):
    c = w["client"]
    assert c.get("/me", headers=headers("admin-token")).json()["internal"] is True
    assert c.get("/me", headers=headers("pro-token")).json()["internal"] is False


def test_an_internal_account_sends_nothing_from_the_server(posts, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com")
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    monkeypatch.setattr(db, "set_setting", lambda k, v: None)
    assert not product_analytics.checkout({"id": "u1", "email": "owner@example.com"}, "started", "basic", "month")
    assert product_analytics.checkout({"id": "u2", "email": "someone@else.com"}, "started", "basic", "month")
    assert [p["event"] for p in posts] == ["checkout started"]


# ---------- T3: sign-up and checkout from the server ----------
def test_signed_up_goes_once_per_account_with_its_source_at_the_moment_it_was_made(posts, monkeypatch):
    saved = {}
    monkeypatch.setattr(product_analytics.db, "get_setting", lambda k: saved.get(k))
    monkeypatch.setattr(product_analytics.db, "set_setting", lambda k, v: saved.__setitem__(k, v))
    now = datetime(2026, 11, 27, 12, tzinfo=timezone.utc)
    made = (now - timedelta(minutes=40)).isoformat()
    who = {"id": "u-new", "email": "new@example.com", "created_at": made}
    assert product_analytics.signed_up(who, "stock", now)
    assert not product_analytics.signed_up(who, "stock", now), "once per account, whatever the browser"
    assert len(posts) == 1
    body = posts[0]
    assert body["event"] == "signed up" and body["distinct_id"] == "u-new" and body["properties"]["source"] == "stock"
    assert body["timestamp"] == made and "new@example.com" not in str(body)
    old = {"id": "u-old", "created_at": (now - timedelta(days=3)).isoformat()}
    assert not product_analytics.signed_up(old, None, now), "an account made days ago signing in is not a sign-up"
    odd = {"id": "u-odd", "created_at": made}
    assert product_analytics.signed_up(odd, "<b>x</b>", now) and "source" not in posts[-1]["properties"], "only a plain word"


def test_checkout_steps_carry_plan_and_period_only():
    assert not product_analytics.checkout({"id": "u"}, "bought", "basic", "month")
    assert not product_analytics.checkout({"id": "u"}, "started", "gold", "month")
    assert not product_analytics.checkout({"id": "u"}, "started", "basic", "week")


def test_the_endpoints_respect_a_browser_that_is_left_out(w, posts):
    c = w["client"]
    for row in w["db"].tables["profiles"]:
        if row["id"] == "u-free":
            row["created_at"] = datetime.now(timezone.utc).isoformat()
    db.forget_profile("u-free")
    assert c.post("/analytics/signup", json={"from": "theme"}, headers={**headers("free-token"), "X-Analytics": "off"}).json() == {"first": False}
    assert posts == []
    assert c.post("/analytics/signup", json={"from": "theme"}, headers=headers("free-token")).json() == {"first": True}
    assert c.post("/analytics/signup", json={"from": "theme"}, headers=headers("free-token")).json() == {"first": False}
    assert [p["event"] for p in posts] == ["signed up"] and posts[0]["properties"] == {"source": "theme", "$lib": "stratlab-server"}
    assert c.post("/billing/checkout-event", json={"event": "dismissed", "plan": "basic", "period": "month"}, headers=headers("free-token")).json() == {"recorded": True}
    assert c.post("/billing/checkout-event", json={"event": "failed", "plan": "pro", "period": "year"}, headers={**headers("free-token"), "X-Analytics": "off"}).json() == {"recorded": False}
    assert c.post("/billing/checkout-event", json={"event": "paid", "plan": "pro", "period": "year"}, headers=headers("free-token")).status_code == 400
    assert [p["event"] for p in posts] == ["signed up", "checkout dismissed"]
    assert c.post("/analytics/signup", json={}).status_code == 401
    assert c.post("/billing/checkout-event", json={"event": "dismissed", "plan": "basic", "period": "month"}).status_code == 401


# ---------- P1: one try without an account ----------
def test_a_visitor_tries_one_idea_with_nothing_stored_and_a_few_tries_a_day(w):
    c = w["client"]
    opts = c.get("/public/try").json()
    assert {i["id"] for i in opts["ideas"]} == set(guest_try.IDEAS) and {i["id"] for i in opts["instruments"]} == set(guest_try.INSTRUMENTS)
    before = {k: len(v) for k, v in w["db"].tables.items()}
    r = c.post("/public/try", json={"idea": "ema", "instrument": "CRYPTO:BTC-USD"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["verdict"]["headline"] and j["verdict"]["total"] >= 3 and {x["id"] for x in j["verdict"]["checks"]} >= {"unseen", "sample"}
    assert set(j["stats"]) == {"ret", "buy_hold", "mdd", "trades", "unseen"} and j["kept"] is False and j["left"] == guest_try.PER_ADDRESS_PER_DAY - 1
    assert "trades" not in j or isinstance(j.get("trades"), (int, type(None))), "no trade list"
    assert {k: len(v) for k, v in w["db"].tables.items()} == before, "nothing written to the database"
    # the same pick again today: the kept result, not counted
    again = c.post("/public/try", json={"idea": "ema", "instrument": "CRYPTO:BTC-USD"}).json()
    assert again["kept"] is True and again["left"] == guest_try.PER_ADDRESS_PER_DAY - 1 and again["verdict"] == j["verdict"]
    assert c.post("/public/try", json={"idea": "made-up", "instrument": "CRYPTO:BTC-USD"}).status_code == 400
    assert c.post("/public/try", json={"idea": "ema", "instrument": "US:TSLA"}).status_code == 400


def test_the_limits_count_fresh_runs_per_address_and_for_everyone(monkeypatch):
    guest_try.forget()
    ran = []
    monkeypatch.setattr(guest_try.research, "load", lambda reg, s, req: {"inst": req.instrument})
    monkeypatch.setattr(guest_try.research, "record", lambda out, s, l, v, n: {"verdict": {"verdict": "luck", "headline": "h", "passed": 1, "total": 4, "checks": []},
                                                                               "stats": {"ret": 1, "buy_hold": 2, "n": 3}, "range": {"from": "a", "to": "b"}, "instrument": {}})
    runner = lambda s, d: ran.append(d["inst"]) or {}        # noqa: E731
    picks = [(i, k) for i in guest_try.IDEAS for k in guest_try.INSTRUMENTS]
    for n, (idea, inst) in enumerate(picks[:guest_try.PER_ADDRESS_PER_DAY]):
        assert guest_try.run(None, runner, idea, inst, "1.2.3.4")["left"] == guest_try.PER_ADDRESS_PER_DAY - n - 1
    with pytest.raises(Exception) as over:
        guest_try.run(None, runner, *picks[guest_try.PER_ADDRESS_PER_DAY], "1.2.3.4")
    assert getattr(over.value, "status_code", None) == 429 and "Sign up free" in str(getattr(over.value, "detail", ""))
    assert guest_try.run(None, runner, *picks[0], "1.2.3.4")["kept"] is True, "a kept result is served even past the limit"
    assert guest_try.run(None, runner, *picks[guest_try.PER_ADDRESS_PER_DAY], "5.6.7.8")["kept"] is False, "another address"
    monkeypatch.setattr(guest_try, "RUNS_PER_DAY", len(ran))
    with pytest.raises(Exception) as busy:
        guest_try.run(None, runner, *picks[-1], "9.9.9.9")
    assert getattr(busy.value, "status_code", None) == 503
    # nothing about the address is kept as it was given
    assert all("1.2.3.4" not in k for k in guest_try._tries)
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    assert guest_try.run(None, runner, *picks[-1], "1.2.3.4", now=tomorrow)["left"] == guest_try.PER_ADDRESS_PER_DAY - 1, "a new day starts again"
    guest_try.forget()


# ---------- P3: the stock page ----------
def _row(s, ind, cap, sector, at="2026-10-08"):
    return {"symbol": s, "name": s, "sector": sector, "industry": ind, "market_cap": cap, "cap_checked": True, "price_at": at}


def test_a_large_companys_wider_sector_lists_companies_of_its_size_and_the_larger_list_comes_first(monkeypatch):
    """Reliance (27 Nov, live): "Same sector" listed Gulf Oil Lubricants, Veedol, Rajasthan Securities and Kotyark before "Same industry"'s IOC,
    BPCL and HPCL: the wider sector's list for a large company kept every company left over, however small, and came first."""
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "prefetch_settings", lambda keys: None)
    screens._mem.clear()
    import json
    rows = [_row("IOC", "Refineries & Marketing", 190_000.0, "Energy"), _row("BPCL", "Refineries & Marketing", 140_000.0, "Energy"),
            _row("HINDPETRO", "Refineries & Marketing", 90_000.0, "Energy"), _row("MRPL", "Refineries & Marketing", 25_000.0, "Energy"),
            _row("GULFOILLUB", "Lubricants", 6_000.0, "Energy"), _row("VEEDOL", "Lubricants", 2_500.0, "Energy"), _row("KOTYARK", "Lubricants", 300.0, "Energy"),
            _row("ONGC", "Oil Exploration", 310_000.0, "Energy")]
    store[screens.INDEX_KEY + "IN"] = json.dumps({"at": "2026-10-09", "rows": rows})
    cos = {s: {"name": s, "sym": s, "bse": None} for s in [r["symbol"] for r in rows] + ["RELIANCE"]}
    monkeypatch.setattr(stock_pages, "companies", lambda r: cos)
    monkeypatch.setattr(stock_pages, "nse_twins", lambda: {})
    secs = stock_pages.peer_sections("IN", "RELIANCE", ["Energy", "Refineries & Marketing"], 2_000_000.0)
    listed = [s for sec in secs for s, _ in sec["rows"]]
    assert not {"GULFOILLUB", "VEEDOL", "KOTYARK"} & set(listed), "under 1% of Reliance's value: not its peers"
    assert secs[0]["title"] == "Same sector" and [s for s, _ in secs[0]["rows"]] == ["ONGC"], "the sector's list has a larger company than the industry's"
    assert [s for s, _ in secs[1]["rows"]][:3] == ["IOC", "BPCL", "HINDPETRO"]
    # without ONGC the sector adds nothing of Reliance's size: the industry's list alone, IOC first
    store[screens.INDEX_KEY + "IN"] = json.dumps({"at": "2026-10-09", "rows": [r for r in rows if r["symbol"] != "ONGC"]})
    screens._mem.clear()
    secs = stock_pages.peer_sections("IN", "RELIANCE", ["Energy", "Refineries & Marketing"], 2_000_000.0)
    assert [s["title"] for s in secs] == ["Same industry"] and secs[0]["rows"][0][0] == "IOC"


def test_the_stock_pages_ways_in_are_under_the_price_and_the_footer_names_sebi_and_the_data(w):
    page = w["client"].get("/stocks/in/RELIANCE").text
    top = page.index("data-cta-top")
    assert page.index("data-price") < top < page.index("data-chart") if "data-chart" in page else page.index("data-price") < top
    assert "Free sign-in: test a strategy on RELIANCE</a>" in page and "Sign in for the full deep dive</a>" in page
    assert "Free sign-in: test a strategy on RELIANCE (needs sign-in)" not in page
    assert "Go further with RELIANCE" in page, "the way in at the foot stays"
    assert "StratLab is not a SEBI-registered investment adviser or research analyst." in page
    assert "(NSE, BSE and the SEC)" in page
    assert not re.search(r"\b(buy|sell) (now|this)\b", page, re.I)


# ---------- P2: the theme page ----------
def _theme_view(n=3):
    rows = [{"symbol": f"S{i}", "name": f"Company {i}", "page": None, "cap": "₹1.2 lakh cr", "cap_v": 1.0, "revenue": None, "evidence": "description_verified"}
            for i in range(4)]
    return {"region": "IN", "label": "Defence", "slug": "defence", "name": "defence", "members": 12, "all": 12, "evidence": {}, "older": False,
            "rechecking": False, "summary": "About.", "prices": None, "day": None, "indexable": True,
            "layers": [{"name": f"Layer {k}", "companies": rows, "evidence": {}} for k in range(n)]}


def test_the_theme_pages_way_in_and_deck_preview_are_at_the_top_and_promise_no_free_deck():
    html = public_themes.render(_theme_view())
    top, first = html.index("data-cta-top"), html.index("data-layer")
    assert top < first
    assert "Sign in free to open the theme</a>" in html and "from=theme" in html
    assert 'href="https://stratlab.studio/sample-deck">Preview a theme deck, no sign-in</a>' in html
    assert "What the Defence slide deck holds" in html and "The value chain: 3 layers" in html and "companies and figures (12 companies)" in html
    assert "Slide decks are on Basic and Pro." in html
    assert "Download the full deck" not in html and "free deck" not in html.lower(), "Free has no decks of its own (plans.PLANS decks_per_month 0)"
    assert len(re.findall(r">Sign in free to open the[^<]*</a>", html)) == 2, "the way in at the foot stays too"


# ---------- coordinator: the sample deck's own page, and the deck's footer ----------
def test_the_sample_deck_has_a_page_with_a_preview_and_a_stable_pdf_address(w, monkeypatch):
    c = w["client"]
    none = c.get("/sample-deck")
    assert none.status_code == 200 and 'content="noindex,follow"' in none.text and "no sample deck" in none.text
    row = {"id": "deck-1", "label": "India defence (PDF, 2026-11-20)", "region": "IN", "meta": {}}
    monkeypatch.setattr(sample_deck, "chosen", lambda deck_id=None: row)
    monkeypatch.setattr(sample_deck.computed, "get_hk", lambda kind, hk: {"value": "JVBERi0xLjQK"})       # "%PDF-1.4\n"
    page = c.get("/sample-deck")
    t = page.text
    assert page.status_code == 200 and 'content="index,follow"' in t
    assert '<meta property="og:title" content="Sample theme deck: India defence · StratLab">' in t and '<link rel="canonical" href="https://stratlab.studio/sample-deck">' in t
    assert 'href="https://stratlab.studio/sample-deck.pdf?id=deck-1" download>Download the sample deck (PDF)</a>' in t
    assert "Slide decks are on Basic (5 a month) and Pro (unlimited)" in t
    assert "not a SEBI-registered investment adviser or research analyst" in t
    pdf = c.get("/sample-deck.pdf?id=deck-1")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"


def test_a_theme_decks_footer_names_the_site_and_the_themes_public_page(monkeypatch):
    from app import deck
    assert deck.THEME_DECK_VERSION == 97
    monkeypatch.setattr(public_themes, "entries", lambda region=None: [{"region": "IN", "name": "defence", "label": "Defence", "slug": "defence", "aliases": []}])
    assert public_themes.public_address("IN", "Defence") == "stratlab.studio/themes/in/defence"
    assert public_themes.public_address("IN", "Unmapped thing") == "stratlab.studio/themes/in"
    assert public_themes.public_address(None, "x") == "stratlab.studio/themes"
    assert deck.theme_address("IN", "Defence") == "stratlab.studio/themes/in/defence"
    monkeypatch.setattr(public_themes, "public_address", lambda r, n: (_ for _ in ()).throw(RuntimeError("store down")))
    assert deck.theme_address("IN", "Defence") == "stratlab.studio"
