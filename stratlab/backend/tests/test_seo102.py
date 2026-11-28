"""seo102: Search Console showed ~235 pages indexed and ~13,400 "Discovered, currently not indexed" (Google found the company pages
and put off crawling them). Rules, not per-page fixes:

- a search engine's crawler gets a stored company page at once, never the BUILD_WAIT a person waits for a rebuild;
- public pages, sitemaps and robots.txt carry an ETag and answer 304 Not Modified to If-None-Match;
- a company's sitemap <lastmod> is the day its reported content last changed (not the price, not "today" for every page), a directory
  page's the day its list changed, and the sitemap index takes each file's newest;
- a company untraded for a month (its close 30+ days older than the market's newest) is noindex and out of the sitemap and directory;
- every company page has breadcrumbs up to its letter page, links to the theme pages that list it, and answers two questions from
  facts no other page says (its place by market value in its industry, its latest quarter against a year before);
- the hubs (/stocks, /stocks/in) link the later pages of a long letter, so every company is three links from the home page."""
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import pytest

from app import db, main, public_themes, screens, stock_pages
from tests import world

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|target|undervalued|overvalued|recommend\w*|outperform\w*)\b", re.I)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    yield built
    built["close"]()


def rows(xml: bytes) -> dict[str, str | None]:
    return {u.find(NS + "loc").text: (u.find(NS + "lastmod").text if u.find(NS + "lastmod") is not None else None) for u in ET.fromstring(xml)}


# ---------- 1. a crawler is not kept waiting for a rebuild ----------
def test_a_crawler_gets_the_stored_copy_at_once_while_a_person_waits_for_the_build(w, monkeypatch):
    monkeypatch.setattr(stock_pages, "BUILD_WAIT", 1.5)
    assert w["client"].get("/stocks/in/RELIANCE").status_code == 200
    old = {**json.loads(db.get_setting("stocks:page:IN:RELIANCE"))["facts"], "price": 1000.0}
    go = threading.Event()

    def gather(region, co):
        go.wait(10)
        return {**old, "price": 2000.0}
    store = stock_pages.Pages(gather, per_minute=10)
    co = {"sym": "RELIANCE", "bse": None, "name": "Reliance Industries"}
    req = db._in_request.set(True)
    try:
        db.set_setting("stocks:page:IN:RELIANCE", json.dumps({"ts": 0, "facts": old}))      # a day old: due a rebuild
        seen = stock_pages.crawler_visit(GOOGLEBOT)
        try:
            t0 = time.monotonic()
            assert store.get("IN", "RELIANCE", co)["price"] == 1000.0
            assert time.monotonic() - t0 < 0.5                       # no BUILD_WAIT for a crawler
        finally:
            stock_pages._crawler_visit.reset(seen)
        assert store.inflight                                        # the build still started behind it
        seen = stock_pages.crawler_visit("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0")
        try:
            t0 = time.monotonic()
            assert store.get("IN", "RELIANCE", co)["price"] == 1000.0
            assert time.monotonic() - t0 >= 1.2                      # a person still waits for the build first
        finally:
            stock_pages._crawler_visit.reset(seen)
    finally:
        db._in_request.reset(req)
        go.set()


def test_crawlers_are_told_by_their_user_agent():
    assert stock_pages.is_crawler(GOOGLEBOT) and stock_pages.is_crawler("Mozilla/5.0 (compatible; bingbot/2.0)")
    assert not stock_pages.is_crawler("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/604.1") and not stock_pages.is_crawler(None)


# ---------- 2. ETag and 304 ----------
def test_public_pages_sitemaps_and_robots_carry_an_etag_and_answer_304(w):
    c = w["client"]
    for u in ("/stocks/in/RELIANCE", "/stocks", "/stocks/in", "/stocks/in/browse/r", "/sitemap.xml", "/sitemaps/pages.xml", "/robots.txt"):
        r = c.get(u)
        tag = r.headers.get("etag")
        assert r.status_code == 200 and tag and tag.startswith('W/"'), u
        again = c.get(u, headers={"If-None-Match": tag})
        assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == tag, u
        assert again.headers.get("cache-control") == r.headers.get("cache-control"), u
        assert c.get(u, headers={"If-None-Match": 'W/"other"'}).status_code == 200, u
    r = c.head("/stocks/in/RELIANCE", headers={"If-None-Match": c.get("/stocks/in/RELIANCE").headers["etag"]})
    assert r.status_code == 304


def test_an_etag_is_only_on_a_200_page_and_never_on_the_app_api(w):
    c = w["client"]
    r = c.get("/stocks/in/NOSUCHCO")
    assert r.status_code == 404 and "etag" not in r.headers
    assert "etag" not in c.get("/health").headers
    assert main.etag_matches('"abc", W/"def"', 'W/"def"') and main.etag_matches("*", 'W/"x"') and not main.etag_matches('"abc"', 'W/"x"')


# ---------- 3. a true lastmod ----------
def facts(**more) -> dict:
    return {"v": stock_pages.FACTS_VERSION, "name": "Acme Ltd", "industry": ["Metals", "Steel"], "price": 100.0, "price_at": "2026-11-20",
            "years": [{"year": "Mar 2026", "sales": 1000.0, "profit": 80.0}], "filings": [{"at": "2026-11-02", "name": "Results"}], **more}


def test_the_content_print_ignores_the_price_and_follows_the_reported_figures():
    a = stock_pages.content_print(facts())
    assert stock_pages.content_print(facts(price=120.0, price_at="2026-11-27", market_cap=5000.0, pe=12.0, high52=130.0, stage=2,
                                           built_at="2026-11-27T10:00:00+00:00")) == a
    assert stock_pages.content_print(facts(years=[{"year": "Mar 2026", "sales": 1001.0, "profit": 80.0}])) != a
    assert stock_pages.content_print(facts(filings=[{"at": "2026-11-25", "name": "Board meeting"}, {"at": "2026-11-02", "name": "Results"}])) != a


def test_the_change_log_keeps_a_day_until_the_content_changes(w):
    built = time.mktime(date(2026, 11, 20).timetuple()) + 43200
    first = stock_pages.first_day(facts(), built)
    assert first == "2026-11-02"                                      # the newest filing it reports, not the day it was built
    assert stock_pages.first_day(facts(filings=[]), built) == "2026-11-20"
    assert stock_pages.first_day(facts(filings=[{"at": "2027-01-01", "name": "x"}]), built) == "2026-11-20"   # never after it was built
    log = stock_pages.note_content("IN", {"ACME": (stock_pages.content_print(facts()), first)}, today="2026-11-27")
    assert log["ACME"][1] == "2026-11-02"
    log = stock_pages.note_content("IN", {"ACME": (stock_pages.content_print(facts(price=150.0)), first)}, today="2026-11-28")
    assert log["ACME"][1] == "2026-11-02"                             # a new close isn't a change
    log = stock_pages.note_content("IN", {"ACME": (stock_pages.content_print(facts(q={"of": "Sep 2026 vs Sep 2025", "sales": 4.0})), first)},
                                   today="2026-11-29")
    assert log["ACME"][1] == "2026-11-29" and stock_pages.content_days("IN") == {"ACME": "2026-11-29"}
    assert stock_pages.note_content("IN", {}, today="2026-11-30") == {} and stock_pages.content_days("IN") == {}   # no longer stored


def test_the_company_sitemap_says_when_each_page_changed_and_the_index_takes_the_newest(w):
    c = w["client"]
    for s in ("RELIANCE", "INFY", "AAPL"):
        c.get(f"/stocks/{'us' if s == 'AAPL' else 'in'}/{s}")
    screens.build_index("IN")
    screens.build_index("US")
    days = stock_pages.content_days("IN")
    assert days and all(re.fullmatch(r"\d{4}-\d\d-\d\d", d) for d in days.values())
    got = rows(c.get("/sitemaps/stocks-in-1.xml").content)
    assert got["https://stratlab.studio/stocks/in/RELIANCE"] == days["RELIANCE"]
    log = json.loads(db.get_setting(stock_pages.MOD_KEY + "IN"))
    log["RELIANCE"] = [log["RELIANCE"][0], "2026-11-03"]
    db.set_setting(stock_pages.MOD_KEY + "IN", json.dumps(log))
    screens.build_index("IN")                                         # nothing it reports changed: the day stays
    assert rows(c.get("/sitemaps/stocks-in-1.xml").content)["https://stratlab.studio/stocks/in/RELIANCE"] == "2026-11-03"
    index = rows(c.get("/sitemap.xml").content)
    newest = max(d for d in rows(c.get("/sitemaps/stocks-in-1.xml").content).values() if d)
    assert index["https://stratlab.studio/sitemaps/stocks-in-1.xml"] == newest


def test_a_directory_page_keeps_its_day_until_its_list_changes(w, monkeypatch):
    c = w["client"]
    stock_pages.save_list("IN", [{"symbol": f"AL{i:04d}", "name": f"Alpha Holdings {i:04d} Ltd"} for i in range(120)])
    first = rows(c.get("/sitemaps/directory.xml").content)
    a = "https://stratlab.studio/stocks/in/browse/a"
    assert first[a]
    log = json.loads(db.get_setting(stock_pages.DIR_MOD_KEY))
    log["/stocks/in/browse/a"][1] = "2026-10-01"
    db.set_setting(stock_pages.DIR_MOD_KEY, json.dumps(log))
    assert rows(c.get("/sitemaps/directory.xml").content)[a] == "2026-10-01"           # the same companies: the same day
    stock_pages.save_list("IN", [{"symbol": f"AL{i:04d}", "name": f"Alpha Holdings {i:04d} Ltd"} for i in range(121)])
    stock_pages._dir.clear()
    today = stock_pages.datetime.now(stock_pages.timezone.utc).date().isoformat()
    assert rows(c.get("/sitemaps/directory.xml").content)[a] == today                  # one more company: changed today


# ---------- 4. a month without a trade: noindex ----------
def test_a_company_untraded_for_a_month_is_noindex_and_out_of_the_sitemap(w):
    f = facts()
    assert stock_pages.indexable(f) and stock_pages.indexable(f, "2026-12-15")
    assert not stock_pages.indexable(f, "2026-12-21")                # 31 days after its last close
    assert stock_pages.indexable(f, None)                            # no market day known: any price counts
    today = stock_pages.datetime.now(stock_pages.timezone.utc).date()
    assert stock_pages.newest_day([str(today - timedelta(days=3)), "2099-01-01", None, "bad"]) == str(today - timedelta(days=3))  # never the future
    c = w["client"]
    c.get("/stocks/in/RELIANCE")
    stored = json.loads(db.get_setting("stocks:page:IN:RELIANCE"))
    newest = stored["facts"]["price_at"]
    # TCS stored with the same figures, its last close 45 days before RELIANCE's (the market's newest)
    for sym, at in (("TCS", (date.fromisoformat(newest[:10]) - timedelta(days=45)).isoformat()),
                    ("WIPRO", (date.fromisoformat(newest[:10]) - timedelta(days=20)).isoformat())):
        db.set_setting(f"stocks:page:IN:{sym}", json.dumps({**stored, "ts": time.time(), "facts": {**stored["facts"], "symbol": sym, "price_at": at}}))
    screens.build_index("IN")
    listed = rows(c.get("/sitemaps/stocks-in-1.xml").content)
    assert "https://stratlab.studio/stocks/in/RELIANCE" in listed and "https://stratlab.studio/stocks/in/TCS" not in listed
    assert "https://stratlab.studio/stocks/in/WIPRO" in listed                     # 20 days: still trading
    stock_pages._dir.clear()
    assert 'href="/stocks/in/TCS"' not in c.get("/stocks/in/browse/t").text       # the directory links only listed pages
    main.stock_page_store.mem.clear()
    assert 'content="noindex,follow"' in c.get("/stocks/in/TCS").text
    assert 'content="index,follow"' in c.get("/stocks/in/WIPRO").text


# ---------- 5. links: breadcrumbs, themes, the hubs ----------
def test_a_company_page_has_breadcrumbs_up_to_its_letter_page(w):
    t = w["client"].get("/stocks/in/RELIANCE").text
    crumbs = re.search(r'<p class="small muted" data-crumbs>(.*?)</p>', t).group(1)
    assert 'href="/stocks"' in crumbs and 'href="/stocks/in"' in crumbs and 'href="/stocks/in/browse/r"' in crumbs
    assert t.index("data-crumbs") < t.index("<h1>") and t.count("<h1") == 1
    ld = next(x for x in json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', t, re.S).group(1)) if x["@type"] == "BreadcrumbList")
    assert [x["name"] for x in ld["itemListElement"]] == ["StratLab", "Companies", "India", "A to Z: R", "Reliance Industries Ltd"]
    assert ld["itemListElement"][-1]["item"] == "https://stratlab.studio/stocks/in/RELIANCE"


def test_a_company_page_links_the_theme_pages_that_list_it(w, monkeypatch):
    monkeypatch.setattr(public_themes, "themes_of", lambda r: {"RELIANCE": [("/themes/in/oil-and-gas", "Oil and gas", "Refining")]} if r == "IN" else {})
    main.stock_page_store.mem.clear()
    t = w["client"].get("/stocks/in/RELIANCE").text
    assert "<h2>Themes</h2>" in t and '<a href="/themes/in/oil-and-gas">Oil and gas: Refining</a>' in t
    assert "<h2>Themes</h2>" not in w["client"].get("/stocks/us/AAPL").text


def test_the_theme_links_come_from_the_indexable_theme_pages(w, monkeypatch):
    entry = {"region": "IN", "name": "oil", "label": "Oil and gas", "slug": "oil-and-gas", "aliases": [], "at": 1, "hk": "h"}
    co = lambda s: {"ticker": s, "verified": True}                                          # noqa: E731
    big = {"value_chain": [{"layer": "Refining", "companies": [co("RELIANCE"), co("IOC"), co("BPCL"), co("HPCL")]},
                           {"layer": "Exploration", "companies": [co("ONGC"), co("OIL"), co("RELIANCE"), co("GAIL"), co("NOTLISTED")]}]}
    monkeypatch.setattr(public_themes, "entries", lambda region=None: [entry] if region == "IN" else [])
    monkeypatch.setattr(public_themes, "payload", lambda e: big)
    monkeypatch.setattr(public_themes, "theme_layers", lambda p: [{"name": v["layer"], "companies": v["companies"]} for v in p["value_chain"]])
    monkeypatch.setattr(stock_pages, "companies", lambda r: {s: {"name": s} for s in ("RELIANCE", "IOC", "BPCL", "HPCL", "ONGC", "OIL", "GAIL")})
    public_themes._THEMES_OF.clear()
    got = public_themes.themes_of("IN")
    assert got["RELIANCE"] == [("/themes/in/oil-and-gas", "Oil and gas", "Refining")]       # once per theme, its first layer
    assert got["ONGC"] == [("/themes/in/oil-and-gas", "Oil and gas", "Exploration")] and "NOTLISTED" not in got
    monkeypatch.setattr(public_themes, "payload", lambda e: {"value_chain": big["value_chain"][:1]})      # one layer: not indexable
    public_themes._THEMES_OF.clear()
    assert public_themes.themes_of("IN") == {}


def test_the_rank_and_quarter_questions_say_only_facts(w, monkeypatch):
    f = facts(q={"of": "Sep 2026 vs Sep 2025", "sales": 12.34, "profit": -4.0}, market_cap=5000.0)
    assert stock_pages.quarter_said(f) == "In the quarter to Sep 2026, revenue rose 12.3% and net profit fell 4.0% against the quarter to Sep 2025."
    assert stock_pages.quarter_said(facts(q={"of": "Sep 2026 vs Sep 2025", "sales": 5000.0, "profit": None})) is None    # not meaningful
    assert stock_pages.quarter_said(facts(q={"of": "Dec 2025 vs Dec 2024", "sales": 3.0})) is None                       # not the latest
    assert stock_pages.quarter_said(facts(q={"of": "Year to Mar 2026 vs year to Mar 2025", "sales": 3.0})) is None       # a year isn't a quarter
    rows_ = [{"symbol": s, "industry": "Steel", "market_cap": cap, "price_at": "2026-11-20"} for s, cap in (("BIG", 9000.0), ("ACME", 5000.0), ("SMALL", 100.0))]
    monkeypatch.setattr(stock_pages, "_sized", lambda r: rows_)
    assert stock_pages.industry_rank("IN", "ACME", f) == (2, 3, "Steel")
    assert stock_pages.industry_rank("IN", "BIG", f) == (1, 3, "Steel")
    assert stock_pages.industry_rank("IN", "NONE", f) is None
    monkeypatch.setattr(stock_pages, "_sized", lambda r: rows_[:2])
    assert stock_pages.industry_rank("IN", "ACME", f) is None                                # too few to rank
    monkeypatch.setattr(stock_pages, "_sized", lambda r: rows_)
    items = dict(stock_pages.faq_items(f, "IN", "ACME", "Acme Ltd"))
    rank = items["How large is Acme Ltd in its industry?"]
    assert rank.startswith("By market value at the last close, Acme Ltd is the 2nd largest of the 3 companies in Steel")
    assert items["How did Acme Ltd's latest quarter compare with a year before?"].startswith("In the quarter to Sep 2026, revenue rose 12.3%")
    assert not any(ADVICE.search(a) for a in items.values())
    assert "the largest of the 3" in dict(stock_pages.faq_items(f, "IN", "BIG", "Big Ltd"))["How large is Big Ltd in its industry?"]
    assert [stock_pages.ordinal(n) for n in (2, 3, 4, 11, 12, 13, 21, 22, 101)] == ["2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st"]


def test_the_hubs_link_every_later_page_of_a_long_letter(w):
    c = w["client"]
    stock_pages.save_list("IN", [{"symbol": f"AL{i:04d}", "name": f"Alpha Holdings {i:04d} Ltd"} for i in range(900)])
    stock_pages._dir.clear()
    for u in ("/stocks", "/stocks/in"):
        t = c.get(u).text
        assert 'href="/stocks/in/browse/a/2"' in t and 'href="/stocks/in/browse/a/3"' in t and "A, page 2" in t, u
        assert 'href="/stocks/in/browse/a/4"' not in t, u
    # home -> /stocks -> a letter page (any page of it) -> the company: three links
    hub = c.get("/stocks").text
    reached = set()
    for href in set(re.findall(r'href="(/stocks/in/browse/[^"]+)"', hub)):
        reached |= set(re.findall(r'href="/stocks/in/(AL\d{4})"', c.get(href).text))
    assert {f"AL{i:04d}" for i in range(900)} <= reached
