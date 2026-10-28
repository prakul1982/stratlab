"""SEO-1: the company directories (A-Z letter pages and index lists) that link every company page, the cache the pages are sent
with, renamed tickers, and the sentences and FAQ built from each company's own figures."""
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

import pytest

from app import db, main, stock_pages
from tests import world

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|sec\.gov|nseindia|bseindia|wikipedia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|target|undervalued|overvalued|recommend\w*)\b", re.I)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    yield built
    built["close"]()


def words(html: str) -> str:
    """What a reader sees of the page itself: its main part, with no tags, styles or scripts (the footer's disclaimer says
    "nothing here is a recommendation")."""
    main_part = (re.search(r"<main\b.*?</main>", html, re.S) or re.search(r".*", html, re.S)).group(0)
    return re.sub(r"<[^>]*>", " ", re.sub(r"<(style|script)\b.*?</\1>", "", main_part, flags=re.S))


def hrefs(html: str) -> list[str]:
    return re.findall(r'<a [^>]*href="([^"]+)"', html)


def linked_companies(html: str, region: str = "in") -> set[str]:
    """The company pages a page links (not the directory's own addresses)."""
    return {unquote(h.rsplit("/", 1)[1]) for h in hrefs(html) if re.fullmatch(rf"/stocks/{region}/[^/]+", h) and h.rsplit("/", 1)[1] not in ("browse", "index")}


def locs(xml: bytes) -> list[str]:
    return [u.find(NS + "loc").text for u in ET.fromstring(xml)]


def alpha_list(n: int, prefix: str = "Alpha") -> list[dict]:
    """n companies named "Alpha Holdings 0001 Ltd"…, symbols AL0001… (the stored list is only taken from 100 companies up)."""
    return [{"symbol": f"{prefix[:2].upper()}{i:04d}", "name": f"{prefix} Holdings {i:04d} Ltd"} for i in range(n)]


# ---------- 1. the directories ----------
def test_every_company_in_the_sitemap_is_linked_from_a_letter_page(w):
    c = w["client"]
    stock_pages.save_list("IN", alpha_list(120) + [{"symbol": "ZETA1", "name": "Zeta Works Ltd"}, {"symbol": "3MIND", "name": "3M India Ltd"}])
    listed = {unquote(u.rsplit("/", 1)[1]) for u in locs(c.get("/sitemaps/stocks-in-1.xml").content)}
    linked = set()
    for letter in [*"abcdefghijklmnopqrstuvwxyz", "0-9"]:
        r = c.get(f"/stocks/in/browse/{letter}")
        if r.status_code == 200:
            linked |= linked_companies(r.text)
    assert listed and listed <= linked, sorted(listed - linked)[:10]
    assert "3MIND" in linked_companies(c.get("/stocks/in/browse/0-9").text)      # a digit has its own page


def test_a_letter_page_has_the_tags_a_breadcrumb_and_only_facts(w):
    c = w["client"]
    stock_pages.save_list("IN", alpha_list(120))
    r = c.get("/stocks/in/browse/a")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    t = r.text
    assert '<link rel="canonical" href="https://stratlab.studio/stocks/in/browse/a">' in t and 'content="index,follow"' in t
    assert "<title>India listed companies starting with A · StratLab</title>" in t
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', t).group(1))
    assert ld["@type"] == "BreadcrumbList"
    assert [x["name"] for x in ld["itemListElement"]] == ["StratLab", "Companies", "India", "A to Z: A"]
    assert ld["itemListElement"][-1]["item"] == "https://stratlab.studio/stocks/in/browse/a"
    assert 'href="/stocks/in/AL0003"' in t and "Alpha Holdings 0003 Ltd" in t
    seen = words(t)
    assert not ADVICE.search(seen) and not PROVIDERS.search(seen)
    assert "Not investment advice" in c.get("/stocks/in/RELIANCE").text      # the footer says it on every page


def test_long_letters_are_split_into_pages_of_at_most_400_links(w):
    c = w["client"]
    stock_pages.save_list("IN", alpha_list(900))
    sizes = []
    for n, url in enumerate(("/stocks/in/browse/a", "/stocks/in/browse/a/2", "/stocks/in/browse/a/3"), 1):
        r = c.get(url)
        assert r.status_code == 200, url
        sizes.append(len(re.findall(r'<li><a href="/stocks/in/', r.text)))
        assert f'<link rel="canonical" href="https://stratlab.studio{url}">' in r.text
        assert f"page {n} of 3" in r.text if n > 1 else "page 1 of 3" in r.text
        assert 'data-pager' in r.text and 'href="/stocks/in/browse/a/3"' in r.text
    assert sizes[:2] == [400, 400] and 0 < sizes[2] <= 400 and sum(sizes) == stock_pages.directory("IN")["count"]["A"]
    assert c.get("/stocks/in/browse/a/4").status_code == 404 and c.get("/stocks/in/browse/a/0").status_code == 404
    assert c.get("/stocks/in/browse/a/1", follow_redirects=False).headers["location"] == "/stocks/in/browse/a"
    first = c.get("/stocks/in/browse/a").text
    assert "Alpha Holdings 0000 Ltd" in first and "Alpha Holdings 0400 Ltd" not in first


def test_directory_addresses_are_canonical_and_unknown_ones_are_404_and_noindex(w):
    c = w["client"]
    for src, dst in (("/stocks/IN/browse/R", "/stocks/in/browse/r"), ("/stocks/in/browse/r/1", "/stocks/in/browse/r"),
                     ("/stocks/in/index/NIFTY-50", "/stocks/in/index/nifty-50"), ("/stocks/in/browse", "/stocks/in"),
                     ("/stocks/us/index", "/stocks/us")):
        r = c.get(src, follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == dst, src
    for u in ("/stocks/in/browse/q", "/stocks/in/browse/ab", "/stocks/in/browse/1", "/stocks/xx/browse/a", "/stocks/in/index/nifty-9000",
              "/stocks/in/index/<script>", "/stocks/in/browse/a/%3Cb%3E", "/stocks/in/browse/a/99999999"):
        r = c.get(u, follow_redirects=False)
        assert r.status_code == 404 and "noindex" in r.text and "<script>" not in r.text, u


def test_index_lists_link_the_members_the_app_holds(w):
    c = w["client"]
    r = c.get("/stocks/in/index/nifty-50")
    assert r.status_code == 200
    t = r.text
    assert '<link rel="canonical" href="https://stratlab.studio/stocks/in/index/nifty-50">' in t and "<title>NIFTY 50 companies" in t
    members = linked_companies(t)
    held = {s for s in main.universes.symbols("IN", "nifty50") if stock_pages.find("IN", s)}
    assert members == held and "RELIANCE" in members and len(members) >= 10
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', t).group(1))
    assert [x["name"] for x in ld["itemListElement"]][-1] == "NIFTY 50"
    us = c.get("/stocks/us/index/sp-500")
    assert us.status_code == 200 and 'href="/stocks/us/AAPL"' in us.text and "S&amp;P 500 companies" in us.text
    # an index the app keeps no members for is not offered
    assert c.get("/stocks/in/index/nifty-next-50").status_code == 404
    assert "nifty-500" not in c.get("/stocks/in").text
    db.set_setting("breadth:members:nifty500", json.dumps(sorted(held)))
    stock_pages._dir_index.clear()
    assert c.get("/stocks/in/index/nifty-500").status_code == 200 and 'href="/stocks/in/index/nifty-500"' in c.get("/stocks/in").text


def test_directories_are_linked_from_the_market_pages_and_each_company_page(w):
    c = w["client"]
    wanted = {"/stocks": ("/stocks/in/browse/r", "/stocks/us/browse/a", "/stocks/in/index/nifty-50", "/stocks/us/index/sp-500"),
              "/stocks/in": ("/stocks/in/browse/r", "/stocks/in/index/nifty-50"), "/stocks/us": ("/stocks/us/browse/a", "/stocks/us/index/sp-500")}
    for u, links in wanted.items():
        found = hrefs(c.get(u).text)
        for link in links:
            assert link in found, (u, link)
    assert "/stocks/us/browse/a" not in hrefs(c.get("/stocks/in").text)      # an exchange page offers its own market's lists
    t = c.get("/stocks/in/RELIANCE").text
    assert 'data-browse' in t and 'rel="prev"' in t and 'rel="next"' in t
    assert 'href="/stocks/in/browse/r"' in t and 'href="/stocks/in/index/nifty-50"' in t
    prev = re.search(r'rel="prev" href="([^"]+)"', t).group(1)
    nxt = re.search(r'rel="next" href="([^"]+)"', t).group(1)
    order = stock_pages.directory("IN")["order"]
    i = order.index("RELIANCE")
    assert prev == f"/stocks/in/{order[i - 1]}" and nxt == f"/stocks/in/{order[i + 1]}"
    assert 'href="/stocks/us/index/sp-500"' in c.get("/stocks/us/AAPL").text


def test_the_directory_is_bounded_and_builds_from_the_held_list_alone(w, monkeypatch):
    c = w["client"]
    calls = []
    monkeypatch.setattr(main.stock_page_store, "gather", lambda *a, **k: calls.append(a) or None)   # no page may be built for a list
    stock_pages.save_list("IN", alpha_list(2000))
    assert c.get("/stocks/in/browse/a").status_code == 200 and c.get("/sitemaps/directory.xml").status_code == 200
    assert calls == [] and w["ai"].calls == 0
    d = stock_pages.directory("IN")
    assert set(d) == {"order", "pos", "start", "count"} and all(isinstance(s, str) for s in d["order"])
    assert stock_pages.directory("IN") is d                              # kept, not rebuilt for every request
    assert all(isinstance(v, int) for v in d["pos"].values())            # positions, not copies of the companies


def test_the_directory_sitemap_lists_every_letter_page_and_index_and_is_in_the_index(w):
    c = w["client"]
    stock_pages.save_list("IN", alpha_list(900))
    index = ET.fromstring(c.get("/sitemap.xml").content)
    names = [x.find(NS + "loc").text for x in index]
    assert "https://stratlab.studio/sitemaps/directory.xml" in names and "https://stratlab.studio/sitemaps/blog.xml" in names
    r = c.get("/sitemaps/directory.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    got = locs(r.content)
    for u in ("/stocks/in/browse/a", "/stocks/in/browse/a/2", "/stocks/in/browse/a/3", "/stocks/in/browse/r", "/stocks/in/index/nifty-50",
              "/stocks/us/browse/a", "/stocks/us/index/sp-500"):
        assert "https://stratlab.studio" + u in got, u
    assert len(got) == len(set(got)) and "https://stratlab.studio/stocks/in/browse/a/4" not in got
    for u in got:      # every address listed answers 200, is indexable and names itself as canonical
        page = c.get(u.replace("https://stratlab.studio", ""), follow_redirects=False)
        assert page.status_code == 200 and f'<link rel="canonical" href="{u}">' in page.text and "noindex" not in page.text, u
    assert ET.fromstring(r.content).tag == NS + "urlset"
    assert {"pages", "blog"} <= {n.rsplit("/", 1)[1][:-4] for n in names}       # the blog still owns sitemaps/blog.xml


# ---------- 2. the edge keeps the pages ----------
LONG = "public, max-age=300, s-maxage=86400, stale-while-revalidate=604800"


def test_company_directory_and_list_pages_are_kept_a_day_by_the_edge_and_feeds_minutes(w):
    c = w["client"]
    for u in ("/stocks/in/RELIANCE", "/stocks/us/AAPL", "/stocks", "/stocks/in", "/stocks/us", "/stocks/in/browse/r", "/stocks/in/index/nifty-50",
              "/stocks/us/index/sp-500"):
        r = c.get(u)
        assert r.status_code == 200 and r.headers["cache-control"] == LONG, (u, r.headers.get("cache-control"))
    # browsers still ask again after five minutes
    assert int(re.search(r"(?<!s-)max-age=(\d+)", LONG).group(1)) == 300
    short = stock_pages.FEED_CACHE
    assert "s-maxage=900" in short
    for u in ("/stocks?q=rel", "/stocks/in?q=rel", "/sitemap.xml", "/sitemaps/pages.xml", "/sitemaps/directory.xml", "/sitemaps/stocks-in-1.xml", "/robots.txt"):
        assert c.get(u).headers["cache-control"] == short, u
    # a page that is being prepared is never kept; a page that is a close behind is kept a minute
    assert stock_pages.cache_control("IN", {"region": "IN", "price_at": "2000-01-03"}) == stock_pages.BEHIND_CACHE


def test_a_page_still_waiting_for_its_new_close_is_kept_a_minute_and_a_busy_one_not_at_all(w, monkeypatch):
    c = w["client"]
    assert c.get("/stocks/in/RELIANCE").headers["cache-control"] == LONG
    main.stock_page_store.mem.clear()
    monkeypatch.setattr(stock_pages, "behind", lambda f, now=None: True)          # its price is a close older than the market's
    assert c.get("/stocks/in/RELIANCE").headers["cache-control"] == stock_pages.BEHIND_CACHE
    monkeypatch.undo()
    main.stock_page_store.mem.clear()
    monkeypatch.setattr(main.stock_page_store, "per_minute", 0)
    r = c.get("/stocks/in/INFY")
    assert r.status_code == 503 and r.headers["cache-control"] == "no-store"


def test_blog_pages_are_kept_a_day_and_the_feed_ten_minutes(w):
    from app import blog
    blog.add_once({"slug": "seo1-post", "kind": "research", "title": "A post", "summary": "A post.", "blocks": [{"t": "p", "text": "Facts."}], "published": True})
    c = w["client"]
    for u in ("/blog", "/blog/research", "/blog/seo1-post"):
        r = c.get(u)
        assert r.status_code == 200 and r.headers["cache-control"] == LONG, (u, r.headers.get("cache-control"))
    assert c.get("/blog/feed.xml").headers["cache-control"] == "public, max-age=300, s-maxage=600, stale-while-revalidate=600"


def test_vercel_caches_the_rewritten_pages_so_the_edge_headers_are_kept():
    """vercel.json: the pages the API serves through a rewrite are cached by the host when the rewrite says so (the live site
    answers a company page with x-vercel-cache: HIT and an age under its s-maxage), so no header of ours is overridden there."""
    conf = json.loads((Path(__file__).resolve().parents[2] / "frontend" / "vercel.json").read_text())
    rewrites = {h["source"]: {x["key"]: x["value"] for x in h["headers"]} for h in conf["headers"]}
    for src in ("/stocks/:path*", "/blog/:path*", "/sitemap.xml", "/sitemaps/:path*"):
        assert rewrites[src] == {"x-vercel-enable-rewrite-caching": "1"}, src
        assert not any("cache-control" in k.lower() for k in rewrites[src])         # the origin's Cache-Control (with s-maxage) is the policy
