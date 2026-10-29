"""SEO-1: the company directories (A-Z letter pages and index lists) that link every company page, the cache the pages are sent
with, renamed tickers, and the sentences and FAQ built from each company's own figures."""
import json
from datetime import date
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
    from app import blog, blog_pages
    blog.add_once({"slug": "seo1-post", "kind": "research", "title": "A post", "summary": "A post.", "blocks": [{"t": "p", "text": "Facts."}], "published": True})
    c = w["client"]
    for u in ("/blog", "/blog/research"):                                           # the lists change each trading day (LIVE1B-082): minutes
        r = c.get(u)
        assert r.status_code == 200 and r.headers["cache-control"] == blog_pages.LIST_CACHE, (u, r.headers.get("cache-control"))
    r = c.get("/blog/seo1-post")                                                    # a post's page is kept the day
    assert r.status_code == 200 and r.headers["cache-control"] == LONG, r.headers.get("cache-control")
    assert c.get("/blog/feed.xml").headers["cache-control"] == "public, max-age=300, s-maxage=600, stale-while-revalidate=600"


def test_vercel_caches_the_rewritten_pages_so_the_edge_headers_are_kept():
    """vercel.json: the pages the API serves through a rewrite are cached by the host when the rewrite says so (the live site
    answers a company page with x-vercel-cache: HIT and an age under its s-maxage), so no header of ours is overridden there."""
    conf = json.loads((Path(__file__).resolve().parents[2] / "frontend" / "vercel.json").read_text())
    rewrites = {h["source"]: {x["key"]: x["value"] for x in h["headers"]} for h in conf["headers"]}
    for src in ("/stocks/:path*", "/blog/:path*", "/sitemap.xml", "/sitemaps/:path*"):
        assert rewrites[src] == {"x-vercel-enable-rewrite-caching": "1"}, src
        assert not any("cache-control" in k.lower() for k in rewrites[src])         # the origin's Cache-Control (with s-maxage) is the policy


# ---------- 3. renamed and merged tickers ----------
def _renames(*pairs):
    """Store F&O rename circulars (old symbol, new symbol, effective day), as the F&O changes desk keeps them."""
    from app import fo_changes
    db.set_setting(fo_changes.EVENTS_KEY, json.dumps([{"id": f"rename:{a}>{b}", "kind": "rename", "symbol": b, "was_symbol": a, "segment": "stock", "effective": d}
                                                      for a, b, d in pairs]))
    fo_changes._cache.clear()


def test_an_old_ticker_redirects_for_good_to_the_company_it_became(w):
    c = w["client"]
    assert stock_pages.find("IN", "ZOMATO") is None and stock_pages.find("IN", "ETERNAL")
    for src, dst in (("/stocks/in/ZOMATO", "/stocks/in/ETERNAL"), ("/stocks/in/zomato", "/stocks/in/ETERNAL"), ("/stocks/IN/Zomato", "/stocks/in/ETERNAL"),
                     ("/stocks/in/ZOMATO/", "/stocks/in/ETERNAL"), ("/stocks/ZOMATO", "/stocks/in/ETERNAL"),
                     ("/stocks/in/TATAMOTORS", "/stocks/in/TMPV"),                    # the known symbol change the company-data reader keeps
                     ("/stocks/in/HDFC", "/stocks/in/HDFCBANK"),                      # a company merged into another
                     ("/stocks/us/FACEBOOK", "/stocks/us/META"), ("/stocks/us/AT%26T", "/stocks/us/T")):
        r = c.get(src, follow_redirects=False)
        assert r.status_code == 301 and r.headers["location"] == dst, (src, r.status_code, r.headers.get("location"))
    r = c.get("/stocks/in/ZOMATO", follow_redirects=True)
    assert r.status_code == 200 and str(r.url).endswith("/stocks/in/ETERNAL") and "ETERNAL" in r.text
    # a shared card's invite code goes with it
    code = "abc123xy"
    from app import referrals
    if referrals.CODE.match(code):
        assert c.get(f"/stocks/in/ZOMATO?ref={code}", follow_redirects=False).headers["location"] == f"/stocks/in/ETERNAL?ref={code}"


def test_renames_come_from_the_f_and_o_circulars_and_follow_a_chain_but_not_a_loop(w):
    c = w["client"]
    _renames(("OLDCO", "MIDCO", "2026-01-05"), ("MIDCO", "RELIANCE", "2026-06-01"), ("LOOPA", "LOOPB", "2026-01-01"), ("LOOPB", "LOOPA", "2026-02-01"),
             ("GHOSTA", "NOSUCHCO", "2026-03-01"))
    assert c.get("/stocks/in/OLDCO", follow_redirects=False).headers["location"] == "/stocks/in/RELIANCE"
    assert c.get("/stocks/in/MIDCO", follow_redirects=False).headers["location"] == "/stocks/in/RELIANCE"
    for u in ("/stocks/in/LOOPA", "/stocks/in/GHOSTA"):         # a loop, or a new name that has no page: still a 404
        r = c.get(u, follow_redirects=False)
        assert r.status_code == 404 and "noindex" in r.text, u
    _renames(("OLDCO", "TCS", "2025-01-01"), ("OLDCO", "RELIANCE", "2026-01-01"))
    assert stock_pages.renamed_to("IN", "OLDCO") == "RELIANCE"          # renamed twice: the latest says


def test_an_unknown_ticker_stays_a_404_with_noindex_and_a_company_is_never_redirected(w, monkeypatch):
    c = w["client"]
    for u in ("/stocks/in/ZZNOPE", "/stocks/us/ZOMATO", "/stocks/ZZNOPE", "/stocks/in/ZZNOPE/", "/stocks/in/NIFTY"):
        r = c.get(u, follow_redirects=False)
        assert r.status_code in (404, 200) and r.status_code != 301, u
    r = c.get("/stocks/in/ZZNOPE")
    assert r.status_code == 404 and "noindex" in r.text and "canonical" not in r.text
    assert stock_pages.renamed_to("IN", "ZZNOPE") is None and stock_pages.renamed_to("XX", "ZOMATO") is None and stock_pages.renamed_to("IN", "") is None
    assert stock_pages.renamed_to("IN", "Z" * 40) is None
    # an alias whose target has no page, or that names two companies, is not a rename
    from app import name_search
    monkeypatch.setitem(name_search.ALIASES["IN"], "GONEALIAS", ["NOSUCHCO"])
    monkeypatch.setitem(name_search.ALIASES["IN"], "TWOALIAS", ["RELIANCE", "TCS"])
    assert c.get("/stocks/in/GONEALIAS", follow_redirects=False).status_code == 404
    assert c.get("/stocks/in/TWOALIAS", follow_redirects=False).status_code == 404
    # a company that has a page is served, not redirected, whatever the alias table says
    monkeypatch.setitem(name_search.ALIASES["IN"], "RELIANCE", ["TCS"])
    assert c.get("/stocks/in/RELIANCE", follow_redirects=False).status_code == 200


# ---------- 4. a company's own sentences and the questions its page answers ----------
def stored_facts(sym: str, region: str = "IN") -> dict:
    return json.loads(db.get_setting(f"stocks:page:{region}:{sym}"))["facts"]


def about_of(html: str) -> str:
    """The About section's sentences, one to a line (PUB-2), as one text."""
    items = re.search(r'<ul class="plain" data-about>(.*?)</ul>', html, re.S).group(1)
    return " ".join(re.findall(r"<li>(.*?)</li>", items, re.S)).replace("&#x27;", "'").replace("&amp;", "&")


def rupees(v: float) -> str:
    """₹ crore as the page words it, written out here independently of the page's code (Indian grouping for under a lakh crore)."""
    return f"₹{v / 1e5:,.2f} lakh crore" if round(v) >= 1e5 else f"₹{round(v):,} crore"


def dollars(v: float) -> str:
    """$ million as "$416.2B"."""
    return f"${v / 1e6:,.2f}T" if round(v / 1e3, 1) >= 1e3 else f"${v / 1e3:,.1f}B" if v >= 1e3 else f"${round(v):,}M"


def test_the_paragraph_uses_the_pages_own_figures_for_an_indian_company(w):
    c = w["client"]
    t = c.get("/stocks/in/RELIANCE").text
    f = stored_facts("RELIANCE")
    text = about_of(t)
    last = f["years"][-1]
    assert text.startswith("Reliance Industries Ltd is in the Energy sector, in the Refineries industry, listed on NSE.")
    assert f"Its last close was ₹{f['price']:,.2f} on " in text and f"between ₹{f['low52']:,.2f} and ₹{f['high52']:,.2f} (intraday)" in text
    assert f"In its latest reported year ({last['year']}) it reported revenue of {rupees(last['sales'])} and net profit of {rupees(last['profit'])}" in text
    assert f"its revenue grew {f['growth']['sales_cagr_3y']:,.1f}% a year" in text and f"its net profit grew {f['growth']['profit_cagr_3y']:,.1f}% a year" in text
    assert f"Its market value is {rupees(f['market_cap'])}" in text and f"with a P/E of {f['pe']:,.1f}" in text
    assert f"<b data-price>₹{f['price']:,.2f}</b>" in t                   # the header shows the same last close
    assert t.index("Key figures</h2>") < t.index("data-about") < t.index("data-how")      # PUB-2: the About section is near the end, the explanations last
    assert t.count("<li>") > 5 and "</li>" in t.split("data-about>")[1]


def test_the_paragraph_uses_the_pages_own_figures_for_a_us_company(w):
    t = w["client"].get("/stocks/us/AAPL").text
    f = stored_facts("AAPL", "US")
    text = about_of(t)
    last = f["years"][-1]
    assert text.startswith("Apple Inc. is in the ") and "listed in the US." in text
    assert f"Its last close was ${f['price']:,.2f} on " in text and f"between ${f['low52']:,.2f} and ${f['high52']:,.2f}" in text
    assert f"revenue of {dollars(last['sales'])} and net profit of {dollars(last['profit'])}" in text
    assert f"net profit over the last 12 months was {dollars(f['profit_ttm'])}" in text
    assert f"Its market value is {dollars(f['market_cap'])}" in text


def synthetic(**more) -> dict:
    f = stock_pages.facts("IN", "ACME", {"name": "Acme Ltd", "industry_path": ["Metals", "Steel"]},
                          {"years": [{"year": "Mar 2025", "sales": 1200.0, "profit": -35.5, "opm": 10, "debt": 20.0}], "unit": "₹ crore",
                           "growth": {"sales_cagr_3y": 4.2, "profit_cagr_3y": None}},
                          {"market_cap_cr": 4321.0, "pe": None}, None, {"price": 250.0, "price_at": "2026-10-27", "price_basis": "close", "low52": 200.0, "high52": 300.0},
                          [], "BSE")
    return {**f, **more}


def test_losses_missing_figures_and_other_currencies_are_worded_plainly():
    f = synthetic()
    text = stock_pages.about_text(f, "IN", "ACME", "Acme Ltd")
    assert "reported revenue of ₹1,200 crore and a net loss of ₹36 crore; over three years" in text      # as the table rounds -35.5
    assert "Acme Ltd is in the Metals sector, in the Steel industry, listed on BSE." in text
    assert "P/E" not in text and "its revenue grew 4.2% a year" in text and "net profit grew" not in text
    bare = stock_pages.about_text({**f, "years": [], "price": None, "market_cap": None, "profit_ttm": None}, "IN", "ACME", "Acme Ltd")
    assert bare == "Acme Ltd is in the Metals sector, in the Steel industry, listed on BSE."          # nothing is invented for what is missing
    foreign = stock_pages.about_text({**f, "region": "US", "currency": "USD", "unit": "EUR million", "industry": ["Banks"]}, "US", "ACME", "Acme Plc")
    assert "revenue of 1,200 EUR million" in foreign and "listed in the US" in foreign


def test_no_advice_wording_or_vendor_name_in_any_paragraph_question_or_answer(w):
    c = w["client"]
    seen = 0
    for u in ("/stocks/in/RELIANCE", "/stocks/us/AAPL", "/stocks/in/ONGC", "/stocks/us/MSFT"):
        t = c.get(u).text
        for chunk in re.findall(r'<ul class="plain" data-about>.*?</ul>|<div class="card faq" data-faq>.*?</div>', t, re.S):
            seen += 1
            assert not ADVICE.search(words(chunk)) and not PROVIDERS.search(words(chunk)), (u, ADVICE.search(words(chunk)))
        assert not ADVICE.search(words(t)), (u, ADVICE.search(words(t)).group(0))
    assert seen >= 2
    # a purpose from the exchange with such a word never reaches the answer
    items = stock_pages.faq_items(synthetic(), "IN", "ACME", "Acme Ltd", {"results": {"date": "2026-11-05", "when": None, "purpose": "Buy back of shares", "as_of": "2026-10-28"}})
    answer = dict(items)["When are Acme Ltd's next results?"]
    assert "5 Nov 2026" in answer and "Buy back" not in answer and not ADVICE.search(answer)


def test_the_questions_are_only_those_the_page_can_answer_and_the_json_ld_matches_the_text(w):
    from app import results, shareholders
    c = w["client"]
    main.stock_page_store.mem.clear()
    t = c.get("/stocks/in/RELIANCE").text
    qs = re.findall(r"<h3>(.*?)</h3>", t)
    assert qs == ["What is Reliance Industries Ltd&#x27;s market value?"]                  # no results date or holders are stored: not asked
    # stored: the results calendar and the shareholding pattern
    results.save("IN", [results.row("IN", "RELIANCE", date(2026, 11, 6), "Financial Results", when="amc"),
                        results.row("IN", "RELIANCE", date(2026, 8, 1), "Financial Results")])
    shareholders.store("RELIANCE", {"quarter": "2026-09-30", "rec": "r1", "filed": "2026-10-20", "url": "https://example.com/x"},
                       {"name": "Reliance Industries Ltd", "holders": [
                           {"name": "Promoter Group Trust", "kind": "promoter", "group": "promoter", "shares": 5000, "pct": 50.31},
                           {"name": "Insurance Corporation", "kind": "public", "group": "public", "shares": 600, "pct": 6.2},
                           {"name": "Index Fund One", "kind": "public", "group": "public", "shares": 300, "pct": 3.15},
                           {"name": "Index Fund Two", "kind": "public", "group": "public", "shares": 200, "pct": 2.0},
                           {"name": "Small Fund", "kind": "public", "group": "public", "shares": 100, "pct": 1.1}]})
    main.stock_page_store.mem.clear()
    t = c.get("/stocks/in/RELIANCE").text
    flat = t.replace("&#x27;", "'")
    assert re.findall(r"<h3>(.*?)</h3>", flat) == ["What is Reliance Industries Ltd's market value?", "When are Reliance Industries Ltd's next results?",
                                                   "Who are Reliance Industries Ltd's largest named shareholders?"]
    assert "next results are listed for 6 Nov 2026, after the close" in flat and "(the exchange's notice: Financial Results)" in flat
    assert ("the quarter ended 30 Sep 2026, the largest named holders above 1% were: Promoter Group Trust (promoter group) 50.31%; "
            "Insurance Corporation (public) 6.2%; Index Fund One (public) 3.15%. Percentages are of all shares.") in flat
    assert "Small Fund" not in flat and "Index Fund Two" not in flat                         # the three largest only
    ld = [x for x in json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', t, re.S).group(1)) if x["@type"] == "FAQPage"]
    assert len(ld) == 1
    asked = [(q["name"], q["acceptedAnswer"]["text"]) for q in ld[0]["mainEntity"]]
    shown = [(re.sub(r"<[^>]+>", "", q), re.sub(r"<[^>]+>", "", a)) for q, a in re.findall(r"<h3>(.*?)</h3><p>(.*?)</p>", t, re.S)]
    unesc = lambda s: s.replace("&#x27;", "'").replace("&amp;", "&")      # noqa: E731
    assert [(unesc(q), unesc(a)) for q, a in shown] == asked and len(asked) == 3
    # a company in the US has no holders question; a past results date is not offered
    results.save("US", [results.row("US", "AAPL", date(2026, 7, 30), "Earnings")])
    main.stock_page_store.mem.clear()
    assert "next results" not in c.get("/stocks/us/AAPL").text and "largest named" not in c.get("/stocks/us/AAPL").text


def test_a_page_with_nothing_to_show_has_no_paragraph_and_no_questions(w):
    t = w["client"].get("/stocks/in/TCS").text            # no numbers: a short noindex page
    assert "data-about" not in t and "data-faq" not in t and "FAQPage" not in t


# ---------- 5. Search Console: the sitemaps still validate ----------
def all_sitemaps(c) -> dict[str, list[tuple[str, str | None]]]:
    index = ET.fromstring(c.get("/sitemap.xml").content)
    assert index.tag == NS + "sitemapindex"
    out = {}
    for s in index:
        loc = s.find(NS + "loc").text
        r = c.get(loc.replace("https://stratlab.studio", ""))
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml"), loc
        root = ET.fromstring(r.content)
        assert root.tag == NS + "urlset"
        out[loc] = [(u.find(NS + "loc").text, u.find(NS + "lastmod").text if u.find(NS + "lastmod") is not None else None) for u in root]
    return out


def test_every_sitemap_in_the_index_is_valid_and_no_address_is_listed_twice(w):
    c = w["client"]
    stock_pages.save_list("IN", alpha_list(900))
    maps = all_sitemaps(c)
    names = {k.rsplit("/", 1)[1] for k in maps}
    assert {"pages.xml", "blog.xml", "directory.xml", "stocks-in-1.xml", "stocks-us-1.xml"} <= names
    seen: dict[str, str] = {}
    for loc, rows in maps.items():
        assert 0 < len(rows) <= 50_000, loc
        for url, day in rows:
            assert url.startswith("https://stratlab.studio/") and "?" not in url and "#" not in url and url == url.strip(), url
            assert day is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", day), (url, day)
            assert url not in seen, (url, seen.get(url), loc)
            seen[url] = loc
    assert maps["https://stratlab.studio/sitemaps/blog.xml"] is not None            # the blog still owns its file
    assert "https://stratlab.studio/stocks/in/browse/a/3" in seen and "https://stratlab.studio/stocks/in/RELIANCE" in seen


def test_the_sitemap_company_files_are_unchanged_by_the_directories(w):
    """The company chunks list exactly the companies with a page that has facts, as before: the directories are a file of their own."""
    c = w["client"]
    before = locs(c.get("/sitemaps/stocks-in-1.xml").content)
    stock_pages.save_list("IN", alpha_list(900))
    after = locs(c.get("/sitemaps/stocks-in-1.xml").content)
    assert set(before) <= set(after) and len(after) == len(before) + 900
    assert not any("/browse/" in u or "/index/" in u for u in after)


def test_thirteen_thousand_companies_make_a_small_bounded_directory(w):
    """The market sizes Search Console reported (about 6,000 Indian and 7,300 US pages): every page is linked once from a letter
    page of at most 400 links, the sitemap stays tiny, and the directory holds symbols and positions only."""
    import time
    import tracemalloc
    c = w["client"]
    letters = "ABCDEFGHIJKLMNOPRSTUVW"
    def rows(n, tag):
        return [{"symbol": f"{tag}{i:05d}", "name": f"{letters[(i * 7) % len(letters)]}{letters[(i * 3) % len(letters)].lower()}nova {i} Ltd"} for i in range(n)]
    stock_pages.save_list("IN", rows(6000, "I"))
    stock_pages.save_list("US", rows(7300, "U"))
    stock_pages._dir.clear()
    stock_pages.companies("IN"), stock_pages.companies("US")        # the companies list is the app's own, kept anyway: not the directory's
    tracemalloc.start()
    t0 = time.time()
    d_in, d_us = stock_pages.directory("IN"), stock_pages.directory("US")
    took = time.time() - t0
    current, _peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert len(d_in["order"]) >= 6000 and len(d_us["order"]) >= 7300 and took < 5
    assert current < 3_000_000, current                      # kept: the symbols and their positions, a megabyte or two
    linked = {"IN": set(), "US": set()}
    for region in ("in", "us"):
        R = region.upper()
        d = stock_pages.directory(R)
        for L in [*stock_pages.LETTERS, stock_pages.OTHER]:
            if not d["count"].get(L):
                continue
            for page in range(1, stock_pages.pages_of(d["count"][L]) + 1):
                got = linked_companies(stock_pages.letter_page(R, L, page), region)
                assert 0 < len(got) <= stock_pages.DIR_PAGE
                linked[R] |= got
        assert linked[R] == set(d["order"])
    got = locs(c.get("/sitemaps/directory.xml").content)
    assert 50 < len(got) < 200
