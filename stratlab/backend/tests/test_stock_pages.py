"""Public company pages for search engines: a page per listed company with facts and a sign-up link, no provider
names, 404 for unknown symbols, valid chunked sitemaps, robots, and no AI or source hammering from crawlers."""
import json
import re
import xml.etree.ElementTree as ET

import pytest

from app import db, main, stock_pages
from tests import world

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|sec\.gov|nseindia|bseindia|wikipedia", re.I)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def test_an_indian_company_page_has_the_facts_and_the_tags(w):
    c = w["client"]
    r = c.get("/stocks/in/RELIANCE")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "s-maxage" in r.headers["cache-control"]
    t = r.text
    assert "<title>Reliance Industries Ltd (RELIANCE) share price" in t
    assert '<link rel="canonical" href="https://stratlab.studio/stocks/in/RELIANCE">' in t
    assert 'property="og:title"' in t and 'name="description"' in t and 'content="index,follow"' in t
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', t).group(1))
    assert ld[0]["@type"] == "Corporation" and ld[0]["tickerSymbol"] == "RELIANCE"
    for part in ("Last price", "1-year range", "Revenue and profit", "Recent filings", "Price trend", "As of ",
                 "Test a strategy on RELIANCE", "Open the full deep dive", "/new?market=IN&amp;symbol=RELIANCE",
                 "/research/IN/RELIANCE/deep", "Same sector", 'href="/stocks/in/ONGC"', "Not investment advice"):
        assert part in t, part
    for word in (r"\bbuy\b", r"\bsell\b", r"\baccumulate\b", r"\bavoid\b", r"\btarget\b"):   # facts, not advice
        assert not re.search(word, t, re.I), word


def test_a_us_company_page(w):
    t = w["client"].get("/stocks/us/AAPL").text
    assert "Apple Inc. (AAPL)" in t and "$" in t and "Test a strategy on AAPL" in t and "/research/US/AAPL/deep" in t
    assert 'href="https://stratlab.studio/stocks/us/AAPL"' in t


def test_no_provider_names_anywhere_public(w):
    c = w["client"]
    pages = [c.get(u).text for u in ("/stocks/in/RELIANCE", "/stocks/us/AAPL", "/stocks/in/NOPE", "/stocks/in/TCS",
                                     "/sitemap.xml", "/sitemaps/stocks-in-1.xml", "/robots.txt")]
    for text in pages:
        visible = re.sub(r"<style>.*?</style>", "", text, flags=re.S)
        assert not PROVIDERS.search(visible), PROVIDERS.search(visible).group(0)


def test_unknown_symbols_are_404_and_addresses_are_canonical(w):
    c = w["client"]
    for u in ("/stocks/in/NOPE", "/stocks/us/ZZZZZZ", "/stocks/xx/RELIANCE", "/stocks/in/%3Cscript%3E"):
        r = c.get(u)
        assert r.status_code == 404 and "noindex" in r.text and "<script>" not in r.text, u
    assert c.get("/stocks/in/..%2F..%2Fetc").status_code == 404
    r = c.get("/stocks/IN/reliance", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/stocks/in/RELIANCE"


def test_a_bse_only_company_by_symbol_and_code(w, monkeypatch):
    db.set_setting("audit:bse-only", json.dumps({"543210": {"ts": "TINYCO", "token": 1, "name": "TINY CO"}}))
    db.set_setting("audit:market:list", json.dumps({"BSE:543210": {"name": "TINY CO"}, "RELIANCE": {"name": "Reliance"}}))
    stock_pages._companies.clear()
    c = w["client"]
    assert c.get("/stocks/in/543210", follow_redirects=False).headers["location"] == "/stocks/in/TINYCO"
    t = c.get("/stocks/in/TINYCO").text
    assert "Tiny Co Ltd" in t and "BSE" in t
    assert "https://stratlab.studio/stocks/in/TINYCO" in c.get("/sitemaps/stocks-in-1.xml").text


def test_a_listed_company_without_numbers_is_a_short_noindex_page(w):
    t = w["client"].get("/stocks/in/TCS").text     # listed, but the fake fundamentals source has no page for it
    assert "noindex" in t and "Test a strategy on TCS" in t


def test_sitemaps_are_valid_and_chunked(w, monkeypatch):
    c = w["client"]
    stock_pages.save_list("IN", [{"symbol": f"CO{i:05d}", "name": f"Company {i}"} for i in range(stock_pages.CHUNK * 2 + 10)])
    root = ET.fromstring(c.get("/sitemap.xml").content)
    assert root.tag == NS + "sitemapindex"
    locs = [x.find(NS + "loc").text for x in root]
    assert "https://stratlab.studio/sitemaps/stocks-in-3.xml" in locs and "https://stratlab.studio/sitemaps/stocks-us-1.xml" in locs
    seen = set()
    for loc in locs:
        r = c.get(loc.replace("https://stratlab.studio", ""))
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
        urls = ET.fromstring(r.content)
        assert urls.tag == NS + "urlset" and 0 < len(urls) <= stock_pages.CHUNK
        seen |= {u.find(NS + "loc").text for u in urls}
    assert "https://stratlab.studio/stocks/in/RELIANCE" in seen and "https://stratlab.studio/stocks/us/AAPL" in seen
    assert "https://stratlab.studio/stocks/in/CO00042" in seen and "https://stratlab.studio/" in seen
    assert c.get("/sitemaps/stocks-in-4.xml").status_code == 404 and c.get("/sitemaps/nope.xml").status_code == 404
    assert c.get("/sitemaps/stocks-in-0.xml").status_code == 404
    r = c.get("/robots.txt")
    assert "Sitemap: https://stratlab.studio/sitemap.xml" in r.text and "Disallow: /admin" in r.text


def test_crawlers_never_reach_the_ai_and_fresh_builds_are_rationed(w, monkeypatch):
    c = w["client"]
    calls = []
    real = main.stock_page_facts
    store = stock_pages.Pages(lambda r, co: calls.append(co["sym"]) or real(r, co), per_minute=2)
    monkeypatch.setattr(main, "stock_page_store", store)
    for _ in range(3):
        assert c.get("/stocks/in/RELIANCE").status_code == 200
    assert calls == ["RELIANCE"]                        # built once, then from memory
    store.mem.clear()
    assert c.get("/stocks/in/RELIANCE").status_code == 200 and calls == ["RELIANCE"]   # then from storage
    assert c.get("/stocks/us/AAPL").status_code == 200
    r = c.get("/stocks/in/INFY")                        # the minute's ration is used up and nothing is stored
    assert r.status_code == 503 and r.headers["retry-after"] and r.json()["detail"]["code"] == "busy"
    assert calls == ["RELIANCE", "AAPL"] and w["ai"].calls == 0


def test_a_source_down_serves_the_stored_copy_or_busy(w, monkeypatch):
    c = w["client"]
    assert c.get("/stocks/in/RELIANCE").status_code == 200
    w["faults"]["fundamentals"].mode = "down"
    main.stock_page_store.mem.clear()
    key = "stocks:page:IN:RELIANCE"
    old = json.loads(db.get_setting(key))
    db.set_setting(key, json.dumps({**old, "ts": 0}))   # a day old: due a rebuild, which fails
    r = c.get("/stocks/in/RELIANCE")
    assert r.status_code == 200 and "Reliance Industries" in r.text
    assert c.get("/stocks/in/INFY").status_code == 503


def test_hostile_text_is_escaped(w):
    f = stock_pages.facts("IN", "ACME", {"name": "\"><script>alert(1)</script>", "industry_path": ["</script><b>x"]},
                          {"years": []}, {}, None, None, [{"at": "2026-09-01", "title": "<img src=x onerror=alert(1)>"}], "NSE")
    page = stock_pages.render(f, "IN", "ACME", None)
    assert "<script>alert" not in page and "<img src=x" not in page and "&lt;script&gt;" in page
    assert page.count("</script>") == 1                 # only the JSON-LD block's own end


def test_a_sitemap_name_with_a_huge_number_is_a_404_not_a_crash(w):
    c = w["client"]
    assert c.get("/sitemaps/stocks-in-" + "9" * 5000 + ".xml").status_code == 404
    assert c.get("/sitemaps/stocks-in-1.xml").status_code == 200
