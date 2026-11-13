"""AS1: what AdSense's program policies ask of the public pages. Thin company pages are kept out of search results and the
sitemap, every page the server draws has the site's menu (Home, Library, Companies, Themes, Blog, Plans, About, Contact), a link
into the app says it needs sign-in, the sitemap lists public pages only (with /about), and /themes/ is answered on the site's own
host, never by a redirect to the API's."""
import re

import pytest

from app import blog, site_pages, stock_pages
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def _facts(**kw) -> dict:
    base = {"region": "IN", "symbol": "ACME", "name": "Acme Ltd", "exchange": "NSE", "industry": ["Industrials"], "currency": "INR",
            "unit": "₹ crore", "price": 100.0, "price_at": "2026-10-07", "price_basis": "close", "high52": 120.0, "low52": 80.0,
            "market_cap": 770345.0, "pe": 14.3, "roe": 12.0, "opm": 28.0, "net_margin": 19.4, "debt_equity": 0.1, "div_yield": 1.1,
            "years": [{"year": f"Mar 202{i}", "sales": 100.0 * (i - 1), "profit": 20.0 + i, "opm": 26.0, "debt": 1.0} for i in range(2, 7)],
            "growth": {"sales_cagr_3y": 6.4, "profit_cagr_3y": 1.0}, "filings": [], "built_at": "2026-10-08T05:00:00+00:00"}
    return {**base, **kw}


MENU = ['<a href="/">Home</a>', '<a href="/library">Library</a>', '<a href="/stocks">Companies</a>', '<a href="/themes">Themes</a>',
        '<a href="/blog">Blog</a>', '<a href="/pricing">Plans</a>', '<a href="/about">About</a>', '<a href="/contact">Contact</a>']


def _menu(page: str) -> bool:
    nav = re.search(r'<nav aria-label="Site">(.*?)</nav>', page, re.S)
    return bool(nav) and all(m in nav.group(1) for m in MENU) and '<details class="menu"><summary>Menu</summary>' in page


def test_a_company_page_without_a_recent_price_is_thin_noindex_and_out_of_the_sitemap():
    rich, thin = _facts(), _facts(price=None, price_at=None)
    assert stock_pages.indexable(rich) and stock_pages.sitemap_ok(rich)
    assert not stock_pages.indexable(thin) and not stock_pages.sitemap_ok(thin)
    assert not stock_pages.indexable(_facts(no_numbers="no reported numbers"))
    assert '<meta name="robots" content="index,follow">' in stock_pages.render(rich, "IN", "ACME", "Acme Ltd")
    page = stock_pages.render(thin, "IN", "ACME", "Acme Ltd")
    assert '<meta name="robots" content="noindex,follow">' in page and 'rel="canonical"' not in page
    assert "No recent share price is available" in page                  # the visitor still reads what there is


def test_every_page_the_server_draws_has_the_sites_menu(w):
    c = w["client"]
    for url in ("/stocks", "/stocks/in", "/stocks/in/RELIANCE", "/blog", "/themes", "/themes/in", "/status", "/stocks/in/NOPE"):
        r = c.get(url)
        assert r.status_code in (200, 404), url
        assert _menu(r.text), url
    assert _menu(stock_pages.render(_facts(), "IN", "ACME", "Acme Ltd"))
    # the menu itself leads nowhere that asks for sign-in; Sign in says so and isn't followed
    top = stock_pages._top()
    assert not any(stock_pages.APP_PATH.match(h) for h in re.findall(r'href="([^"]*)"', top.split('class="btn')[0]))
    assert re.search(r'<a class="btn ghost sm" href="[^"]*" rel="nofollow">Sign in</a>', top)


def test_a_link_into_the_app_says_it_needs_sign_in_and_is_not_followed():
    page = stock_pages.render(_facts(), "IN", "ACME", "Acme Ltd")
    main = page[page.index("<main"):page.index("</main>")]
    app_links = [m for m in re.finditer(r'<a ([^>]*)href="([^"]*)"([^>]*)>(.*?)</a>', main, re.S) if stock_pages.APP_PATH.match(m.group(2))]
    assert app_links                                                       # the page's "Test a strategy" and "Open the full deep dive"
    for m in app_links:
        assert "nofollow" in m.group(1) + m.group(3), m.group(0)
        assert re.search(r"sign[ -]?in", re.sub(r"<[^>]+>", " ", m.group(4)), re.I), m.group(0)
    assert ">Test a strategy on ACME (needs sign-in)</a>" in main
    # a public page's own links are left as they are
    got = stock_pages._mark_app_links('<main><a href="/stocks/in/TCS">TCS</a><a href="/research/IN/TCS">TCS in the app</a>'
                                      '<a href="https://elsewhere.example/research/x">x</a><a href="/login">Sign in</a></main>')
    assert '<a href="/stocks/in/TCS">TCS</a>' in got and '<a href="https://elsewhere.example/research/x">x</a>' in got
    assert '<a href="/research/IN/TCS" rel="nofollow">TCS in the app (needs sign-in)</a>' in got
    assert '<a href="/login" rel="nofollow">Sign in</a>' in got


def test_the_sitemap_lists_public_pages_only_with_about(w):
    c = w["client"]
    pages = c.get("/sitemaps/pages.xml").text
    locs = re.findall(r"<loc>([^<]+)</loc>", pages)
    site = locs[0].rstrip("/")
    paths = [u[len(site):] or "/" for u in locs]
    assert "/about" in paths and ("/about", "2026-11-13") in site_pages.PAGES
    assert not [p for p in paths if stock_pages.APP_PATH.match(p)]
    for name in ("blog", "themes", "directory"):
        assert not [u for u in re.findall(r"<loc>([^<]+)</loc>", c.get(f"/sitemaps/{name}.xml").text) if stock_pages.APP_PATH.match(u)], name


def test_themes_with_a_trailing_slash_is_answered_here_not_redirected(w):
    r = w["client"].get("/themes/", follow_redirects=False)
    assert r.status_code == 200 and _menu(r.text)


def test_the_blogs_more_links_into_the_app_say_they_need_sign_in(w):
    from datetime import datetime, timezone
    from tests.test_blog import issue_for
    blog.save_brief(issue_for("IN"), datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
    t = w["client"].get("/blog/india-market-brief-2026-10-01").text
    assert re.search(r'<a href="/new" rel="nofollow">Test a trading idea on past prices \(needs sign-in\)</a>', t)
    assert re.search(r'<a href="/research/rotation\?region=IN" rel="nofollow">Sector rotation chart \(needs sign-in\)</a>', t)
