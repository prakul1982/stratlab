"""The public blog (BLOG-1): the daily briefs saved as posts, the research posts built from the app's own data, the pages crawlers
read (canonical, JSON-LD, tags), the sitemap and the feed, and that no user's data or advice wording reaches a page."""
import json
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import pytest

from app import blog, blog_pages, blog_research, db, library, main, sip_test, stock_pages
from app.newsletter import content, job, write
from tests import world as W
from tests.fake_db import headers
from tests.test_newsletter import AFTER_IN_CLOSE, THU, market, reader, outbox  # noqa: F401  (fixtures and helpers)

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
ATOM = "{http://www.w3.org/2005/Atom}"
ADMIN = headers("admin-token")
VENDORS = ("yahoo", "screener", "finnhub", "zerodha", "kite connect", "google news")
HOLIDAY = date(2026, 10, 2)                  # Gandhi Jayanti: India's market is shut


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    content._cache.clear()
    write._cache.clear()
    stock_pages._thin.clear()
    yield world
    world["close"]()


def issue_for(region="IN", day=THU, **more):
    """A daily Market Brief issue as the newsletter job builds it, from the test facts of tests/test_newsletter.py."""
    return {**job.make_issue(market(region, False, day), region), **more}


def page(client, path):
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code)
    return r.text


def ld(html: str) -> list[dict]:
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]


def article(html: str) -> dict:
    return next(x for x in sum([v if isinstance(v, list) else [v] for v in ld(html)], []) if x.get("@type") == "Article")


def urls(xml: bytes) -> dict[str, str | None]:
    return {u.find(NS + "loc").text: (u.find(NS + "lastmod").text if u.find(NS + "lastmod") is not None else None) for u in ET.fromstring(xml)}


# ---------- the daily brief becomes a post ----------
def test_a_brief_is_saved_once_per_market_per_day(w):
    first = blog.save_brief(issue_for("IN"))
    assert first is True and blog.save_brief(issue_for("IN")) is False                        # the same day again changes nothing
    assert blog.save_brief(issue_for("US")) is True                                            # the other market has its own
    assert blog.save_brief(issue_for("IN", day=THU + timedelta(days=1))) is True               # and the next day its own
    rows = {r["slug"]: r for r in db.sb().table("blog_posts").select("*").execute().data}
    assert set(rows) == {"india-market-brief-2026-10-01", "us-market-brief-2026-10-01", "india-market-brief-2026-10-02"}
    one = rows["india-market-brief-2026-10-01"]
    assert one["kind"] == "brief" and one["market"] == "IN" and one["indexable"] is True and one["published"] is True
    assert one["title"] == "India market brief, 1 Oct 2026: NIFTY 50 +0.42%"
    assert "24,812.30" in one["summary"] and "+0.42%" in one["summary"]
    kept = json.dumps(one["body"])
    assert "24,812.30" in kept and "Nifty IT" in kept


def test_the_newsletter_job_saves_the_brief_once_even_when_it_runs_again(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-pro", "pro@example.com", market_in="daily")
    job.Job().tick(AFTER_IN_CLOSE)
    job.Job().tick(AFTER_IN_CLOSE)                                       # a restart, the same day
    got = db.sb().table("blog_posts").select("slug").execute().data
    assert [r["slug"] for r in got] == ["india-market-brief-2026-10-01"]
    # the weekly digest is not a daily brief, and a failing blog never stops the send
    assert job.Job().post_brief(issue_for(weekly=True) | {"weekly": True}, True) is False
    monkeypatch.setattr(blog, "save_brief", lambda issue: 1 / 0)
    assert job.Job().post_brief(issue_for(), False) is False


def test_a_holiday_or_a_day_without_a_figure_is_kept_out_of_search(w):
    assert blog.save_brief(issue_for("IN", day=HOLIDAY, indices=[], sections=[]))
    shut = blog.get("india-market-brief-2026-10-02")
    assert shut["indexable"] is False and shut["title"] == "India market brief, 2 Oct 2026: market closed"
    assert "Gandhi Jayanti" in shut["summary"] or "closed" in shut["summary"]
    blog.save_brief(issue_for("IN", day=date(2026, 10, 5), indices=[{"name": "NIFTY 50", "price": 24000.0}]))      # a trading day, no change to report
    assert blog.get("india-market-brief-2026-10-05")["indexable"] is False
    blog.save_brief(issue_for("IN"))
    c = w["client"]
    html = page(c, "/blog/india-market-brief-2026-10-02")
    assert '<meta name="robots" content="noindex,follow">' in html and 'rel="canonical"' not in html
    assert c.get("/blog/india-market-brief-2026-10-02").headers["x-robots-tag"].startswith("noindex")
    assert "india-market-brief-2026-10-02" not in page(c, "/blog") and "india-market-brief-2026-10-02" not in page(c, "/blog/briefs")
    assert "india-market-brief-2026-10-02" not in c.get("/blog/feed.xml").text
    assert "india-market-brief-2026-10-02" not in urls(c.get("/sitemaps/blog.xml").content).__repr__()
    assert "india-market-brief-2026-10-01" in c.get("/sitemaps/blog.xml").text


def test_only_a_daily_market_brief_becomes_a_post_and_no_user_data_is_copied(w):
    mine = job.make_issue({"kind": "my_stocks", "uid": "u-pro", "day": THU.isoformat(), "weekly": False, "since": "2026-09-30",
                           "stocks": [{"symbol": "TCS", "region": "IN", "price": 4100.0, "change_pct": 1.0, "stage": 2, "stage_before": 2, "stage_changed": False,
                                       "st_s2": False, "filings": [], "headlines": [], "changed": True}], "paper": [], "unchanged": []}, "u-pro")
    assert blog.save_brief(mine) is False and blog.save_brief({**mine, "kind": "market"}) is False        # a reader's issue, however it is labelled
    assert blog.save_brief(issue_for(weekly=True)) is False and blog.save_brief({"kind": "market", "region": "UK", "day": "2026-10-01"}) is False
    assert blog.save_brief({"kind": "market", "region": "IN", "day": "not a date"}) is False
    # an issue that carries stray private fields: only the market-level ones are read
    sneaky = issue_for("IN", email="secret@example.com", readers=["u-pro"], paper=[{"name": "my session"}], html="<p>secret@example.com u-pro</p>", text="u-pro",
                       watchlist=["MYSTOCK"])
    assert blog.save_brief(sneaky) is True
    row = json.dumps(blog.get("india-market-brief-2026-10-01"))
    for private in ("secret@example.com", "u-pro", "my session", "MYSTOCK", "readers"):
        assert private not in row, private
    assert "u-pro" not in page(w["client"], "/blog/india-market-brief-2026-10-01")


# ---------- the page a crawler reads ----------
def test_a_post_is_real_html_with_canonical_tags_json_ld_and_links(w):
    blog.save_brief(issue_for("IN"), datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
    blog.save_brief(issue_for("IN", day=date(2026, 10, 5)), datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc))
    blog.save_brief(issue_for("IN", day=HOLIDAY), datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc))      # a holiday between them: not a neighbour
    blog.save_brief(issue_for("US"), datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc))
    c = w["client"]
    html = page(c, "/blog/india-market-brief-2026-10-01")
    assert "<title>India market brief, 1 Oct 2026: NIFTY 50 +0.42% · StratLab</title>" in html
    assert '<link rel="canonical" href="https://stratlab.studio/blog/india-market-brief-2026-10-01">' in html
    desc = re.search(r'<meta name="description" content="([^"]+)"', html).group(1)
    assert desc == "Thursday 1 October 2026: NIFTY 50 closed at 24,812.30 (+0.42%). Facts, not advice."
    for tag in ('property="og:title"', 'property="og:description"', 'property="og:url" content="https://stratlab.studio/blog/india-market-brief-2026-10-01"',
                'property="og:type" content="article"', 'name="twitter:card"', 'name="twitter:title"', 'name="twitter:description"',
                'property="article:published_time"', 'property="article:modified_time"'):
        assert tag in html, tag
    a = article(html)
    assert a["headline"] == "India market brief, 1 Oct 2026: NIFTY 50 +0.42%" and a["datePublished"] == "2026-10-01T11:00:00+00:00"
    assert a["dateModified"] == a["datePublished"] and a["author"] == {"@type": "Organization", "name": "StratLab", "url": "https://stratlab.studio/"}
    assert a["publisher"]["name"] == "StratLab" and a["publisher"]["logo"]["url"].endswith("/icon-512.png")
    assert a["mainEntityOfPage"]["@id"] == "https://stratlab.studio/blog/india-market-brief-2026-10-01"
    assert "Facts, not advice." in html and "not investment advice" in html
    assert "<h1>India market brief, 1 Oct 2026: NIFTY 50 +0.42%</h1>" in html and "<h2>Index closes</h2>" in html and "<table>" in html
    assert "Nifty IT moved from Improving to Leading" in html
    assert '<a href="/stocks/in/TCS">TCS</a> matches the Stage 2 rule' in html            # a company name goes to its page
    for link in ('href="/library"', 'href="/new"', 'href="/stocks"', 'href="/blog/briefs"', 'href="/research/rotation?region=IN"'):
        assert link in html, link
    assert 'rel="alternate" type="application/atom+xml"' in html and '<a href="/blog">Blog</a>' in html          # the feed, and the header's Blog link
    assert "Headline" not in html and "Brokerage says buy" not in html and "Nifty ends higher" not in html     # no news headlines
    # the next brief links back, and this one forward
    assert 'rel="next" href="/blog/india-market-brief-2026-10-05"' in html and 'rel="prev"' not in html
    later = page(c, "/blog/india-market-brief-2026-10-05")
    assert 'rel="prev" href="/blog/india-market-brief-2026-10-01"' in later and "us-market-brief" not in later       # the US brief is another market's
    for bad in ("<script>alert", "javascript:"):
        assert bad not in html
    assert c.head("/blog/india-market-brief-2026-10-01").status_code == 200 and c.head("/blog/india-market-brief-2026-10-01").content == b""


def test_text_in_a_post_is_escaped_and_only_links_inside_the_site_are_kept():
    blocks = blog.clean_blocks([{"t": "p", "text": ["<script>alert(1)</script> and ", {"a": "ok", "href": "/stocks/in/TCS"}, {"a": "bad", "href": "https://evil.example/x"},
                                                   {"a": "worse", "href": "//evil.example"}, {"a": "js", "href": "javascript:alert(1)"}]},
                                {"t": "iframe", "text": "x"}, {"t": "ul", "items": ["Yahoo Finance said so", ["a ", {"a": "b", "href": "/library"}]]},
                                {"t": "table", "head": ["A", "B"], "rows": [["x", "<b>y</b>"]]}])
    html = blog.blocks_html(blocks)
    assert "<script" not in html and "&lt;script&gt;" in html and 'href="/stocks/in/TCS"' in html and 'href="/library"' in html
    assert "evil.example" not in html and "javascript:" not in html and "iframe" not in html
    assert "Yahoo" not in html and "market data source" in html                       # a data provider's name never reaches a page
    assert "<b>y</b>" not in html and "&lt;b&gt;y&lt;/b&gt;" in html
    assert blog.valid_slug("india-market-brief-2026-10-01") and not any(blog.valid_slug(s) for s in ("briefs", "research", "../x", "A b", "x", "feed.xml"))


def test_the_lists_page_newest_first_and_are_paged(w):
    for n in range(45):
        d = date(2026, 6, 1) + timedelta(days=n)
        blog.add_once({"slug": f"post-number-{n:02d}", "kind": "research" if n % 5 == 0 else "brief", "market": None if n % 5 == 0 else "IN",
                       "title": f"Post {n}", "summary": f"Summary {n}.", "blocks": [{"t": "p", "text": "x"}], "published_at": f"{d}T10:00:00+00:00"})
    c = w["client"]
    one, two, three = page(c, "/blog"), page(c, "/blog?page=2"), page(c, "/blog?page=3")
    assert one.count('class="post"') == 20 and two.count('class="post"') == 20 and three.count('class="post"') == 5
    assert one.index("Post 44") < one.index("Post 43") and "Post 24" in two and "Post 4<" in three
    assert 'rel="next" href="https://stratlab.studio/blog?page=2"' in one and 'rel="prev"' not in one
    assert '<link rel="canonical" href="https://stratlab.studio/blog?page=2">' in two and '<link rel="canonical" href="https://stratlab.studio/blog">' in one
    assert 'rel="prev" href="https://stratlab.studio/blog"' in two and 'rel="next"' not in three
    assert c.get("/blog?page=9").status_code == 404 and page(c, "/blog?page=abc").count('class="post"') == 20
    briefs, research = page(c, "/blog/briefs"), page(c, "/blog/research")
    assert briefs.count('class="post"') == 20 and research.count('class="post"') == 9
    assert all(f"Post {n}<" in research for n in range(0, 45, 5))
    assert "<title>Daily market briefs for India and the US · StratLab</title>" in briefs
    assert '<h1>Market briefs</h1>' in briefs and '<h1>Research</h1>' in research and '<h1>StratLab blog</h1>' in one
    assert any(x.get("@type") == "Blog" for x in ld(one)[0])


def test_unknown_hidden_and_unreadable_pages(w, monkeypatch):
    c = w["client"]
    assert c.get("/blog/no-such-post-here").status_code == 404 and c.get("/blog/..%2Fetc").status_code == 404
    assert 'content="noindex,follow"' in c.get("/blog/no-such-post-here").text
    blog.save_brief(issue_for("IN"))
    monkeypatch.setattr(db, "sb", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    r = c.get("/blog/india-market-brief-2026-10-01")
    assert r.status_code == 503 and r.headers["retry-after"] and r.headers["cache-control"] == "no-store"
    assert c.get("/blog").status_code == 503 and c.get("/blog/feed.xml").status_code == 503


# ---------- the sitemap, the feed and robots ----------
def test_the_sitemap_and_the_feed_list_the_posts(w):
    blog.save_brief(issue_for("IN"), datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
    blog.save_brief(issue_for("US"), datetime(2026, 10, 1, 21, 0, tzinfo=timezone.utc))
    blog.add_once({"slug": "hidden-by-an-admin", "kind": "research", "title": "Hidden", "summary": "Hidden.", "blocks": [{"t": "p", "text": "x"}], "published": False})
    c = w["client"]
    index = ET.fromstring(c.get("/sitemap.xml").content)
    locs = {s.find(NS + "loc").text: s.find(NS + "lastmod") for s in index}
    assert "https://stratlab.studio/sitemaps/blog.xml" in locs and locs["https://stratlab.studio/sitemaps/blog.xml"].text == "2026-10-01"
    got = urls(c.get("/sitemaps/blog.xml").content)
    assert got["https://stratlab.studio/blog/india-market-brief-2026-10-01"] == "2026-10-01"
    assert got["https://stratlab.studio/blog/us-market-brief-2026-10-01"] == "2026-10-01"
    for listed in ("/blog", "/blog/briefs", "/blog/research"):
        assert "https://stratlab.studio" + listed in got
    assert not any("hidden-by-an-admin" in u for u in got)
    feed = c.get("/blog/feed.xml")
    assert feed.headers["content-type"].startswith("application/atom+xml")
    root = ET.fromstring(feed.content)
    entries = root.findall(ATOM + "entry")
    assert [e.find(ATOM + "id").text for e in entries] == ["https://stratlab.studio/blog/us-market-brief-2026-10-01", "https://stratlab.studio/blog/india-market-brief-2026-10-01"]
    first = entries[0]
    assert first.find(ATOM + "title").text.startswith("US market brief") and first.find(ATOM + "published").text == "2026-10-01T21:00:00+00:00"
    assert root.find(ATOM + "link[@rel='self']").get("href") == "https://stratlab.studio/blog/feed.xml" and "hidden-by-an-admin" not in feed.text
    robots = c.get("/robots.txt").text
    assert "Allow: /blog\n" in robots and "Disallow: /blog" not in robots
    assert c.head("/blog").status_code == 200 and c.head("/blog/feed.xml").status_code == 200 and c.head("/blog/briefs").status_code == 200


def test_the_headers_and_footers_of_the_company_pages_link_to_the_blog(w):
    html = page(w["client"], "/stocks")
    assert '<a href="/blog">Blog</a>' in html and 'href="https://stratlab.studio/blog">Blog</a>' in html


# ---------- research posts ----------
def entry(slug, market, name, ret, hold, trades=40, verdict="mixed", passed=2, frm="2021-10-01", to="2026-09-30", group="NIFTY 50 stocks", tf="1d"):
    return {"id": f"seed-{slug}-{market.lower()}", "official": True, "owner": library.OFFICIAL_OWNER, "name": f"{name} · {group}", "market": market,
            "group": {"id": "g", "name": group, "market": market}, "tf": tf, "range": {"from": frm, "to": to}, "seed": {"slug": slug, "market": market},
            "verdict": {"verdict": verdict, "passed": passed, "total": 4, "checks": [{"id": "unseen", "status": "pass"}, {"id": "nearby", "status": "skip"},
                                                                                       {"id": "shuffle", "status": "pass"}, {"id": "sample", "status": "pass" if trades >= 30 else "fail"}]},
            "stats": {"ret": ret, "buy_hold": hold, "mdd": -12.0, "trades": trades, "unseen": 3.0}}


def library_rows():
    markets = ["IN", "US", "UK", "EU", "JP", "CRYPTO", "FX", "MCX", "CDS", "CMDTY"]
    rows = [entry("ema-20-50", m, "20/50 EMA cross", 10.0 + n, 20.0 - n) for n, m in enumerate(markets)]
    rows += [entry("golden-cross", m, "Golden cross", -5.0 + n, 4.0 + n, verdict="no_edge", passed=1) for n, m in enumerate(markets[:4])]
    rows += [entry("rsi2-revert", "IN", "RSI(2) mean reversion", 0, 12.0, trades=0, verdict="not_enough", passed=0)]
    return rows


def test_the_strategy_post_states_the_librarys_own_numbers(w):
    rows = library_rows()
    post = blog_research.classic_strategies(rows, datetime(2026, 11, 3, tzinfo=timezone.utc))
    assert post["slug"] == "classic-strategies-ten-markets-after-costs" and post["kind"] == "research"
    text = blog.plain_text(post["blocks"])
    # every table row says the entry's own return, passive return and trade count, and links to its library page
    tables = [b for b in post["blocks"] if b["t"] == "table"]
    assert len(tables) == 10 and sum(len(t["rows"]) for t in tables) == len(rows)
    by_link = {r[0]["href"]: r for t in tables for r in t["rows"]}
    for e in rows:
        got = by_link[f"/library/{e['id']}"]
        st = e["stats"]
        if st["trades"]:
            assert got[1] == f"{'+' if st['ret'] > 0 else blog.MINUS if st['ret'] < 0 else ''}{abs(st['ret']):.1f}%".replace("+0.0%", "0.0%"), (e["id"], got)
        else:
            assert got[1] == "no trades"
        assert got[2] == f"+{st['buy_hold']:.1f}%" and got[4] == str(st["trades"])
        diff = round(st["ret"] - st["buy_hold"], 2)
        if st["trades"]:
            assert got[3] == (f"{diff:+.1f}".replace("-", blog.MINUS) if abs(diff) >= 0.05 else "0.0") + " pts"
    ahead = sum(1 for e in rows if e["stats"]["trades"] and e["stats"]["ret"] > e["stats"]["buy_hold"])
    behind = sum(1 for e in rows if e["stats"]["trades"] and e["stats"]["ret"] < e["stats"]["buy_hold"])
    assert f"ahead in {ahead} of {len(rows)} tests, behind in {behind}" in text
    lost = sum(1 for e in rows if e["stats"]["trades"] and e["stats"]["ret"] < 0)
    assert f"{lost} of the {len(rows) - 1} tests that traded lost money after costs" in text
    for must in ("Method", "Limits", "slippage", "four checks", "70/30", "1,000 times", "past prices", "StratLab's own backtester"):
        assert must in text, must
    assert blog_research.classic_strategies(rows[:9]) is None               # too few tests for a post


IPO_ROWS = [  # name, symbol, segment, listing, issue price, open %, close %, subscription
    ("Alpha Foods", "ALPHA", "mainboard", "2026-09-10", 100.0, 10.0, 8.0, 52.5),
    ("Beta Power", "BETA", "mainboard", "2026-09-14", 250.0, -4.0, -6.5, 4.2),
    ("Gamma Tech", "GAMMA", "sme", "2026-09-20", 60.0, 5.0, 5.0, 120.0),
    ("Delta Rail", "DELTA", "sme", "2026-10-01", 80.0, None, None, 15.0),          # no listing-day price yet
    ("Eps Labs", "EPS", "mainboard", "2026-10-03", 300.0, 0.0, 0.0, None),
]


def ipo_facts():
    return [{"name": n, "symbol": s, "segment": sg, "listing": d, "issue_price": p, "open_pct": o, "close_pct": c, "sub_times": t} for n, s, sg, d, p, o, c, t in IPO_ROWS][::-1]


def test_the_ipo_post_counts_only_issues_with_data_and_says_how_many_lack_it(w):
    post = blog_research.ipo_listing_day(ipo_facts(), datetime(2026, 11, 3, tzinfo=timezone.utc))
    text = blog.plain_text(post["blocks"])
    assert post["slug"] == "ipo-listing-day-india-2026-so-far" and post["title"] == "IPO listing day in India, 2026 so far"
    assert "5 issues listed between 10 Sep 2026 and 3 Oct 2026; 4 have a listing-day close in the tracker and are counted below" in text and "1 lacks it and is left out of every figure" in text
    assert "On listing day 2 closed above the issue price, 1 below it and 1 at it." in text         # +8.0, +5.0 | -6.5 | 0.0
    assert "median 2.5%" not in text and "closed +2.5% from its issue price; the lowest was −6.5% and the highest +8.0%" in text      # median of 8.0, -6.5, 5.0, 0.0
    assert "median +2.5%" in text                                                                 # opening: 10.0, -4.0, 5.0, 0.0 -> (0+5)/2
    assert "1 issue lacks price data" in post["summary"]
    rows = next(b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "Issue")["rows"]
    assert len(rows) == 4 and "Delta Rail" not in json.dumps(rows) and rows[0][1] == "3 Oct 2026" and rows[-1][2] == "₹100.00"
    seg = next(b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "Segment")["rows"]
    assert seg == [["Main board", "3", "1", "1", "+0.0%".replace("+", "")], ["SME", "1", "1", "0", "+5.0%"]]
    sub = next(b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "Subscribed")["rows"]
    assert sub[0][:2] == ["Under 10 times", "1"] and sub[1][:2] == ["10 to 50 times", "0"] and sub[2][:2] == ["Over 50 times", "2"]
    assert blog_research.ipo_listing_day([f for f in ipo_facts() if f["close_pct"] is None]) is None


def test_ipo_facts_read_the_trackers_rows_of_this_years_listings(w):
    now = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
    base = {"market": "IN", "segment": "mainboard", "price": 100.0, "listing": "2026-10-01", "open": "2026-09-24", "close": "2026-09-26"}
    rows = [{**base, "id": "a", "name": "Listed Co", "symbol": "LISTED", "sub": {"times": 33.5, "as_of": "x"},
             "perf": {"basis": "prices", "issue_price": 100.0, "listing_price": 112.0, "listing_change_pct": 12.0, "day_close": 108.0, "day_change_pct": 8.0}},
            {**base, "id": "b", "name": "No Prices", "symbol": "NOPX"},
            {**base, "id": "c", "name": "Last Year", "symbol": "OLD", "listing": "2025-10-01"},
            {**base, "id": "d", "name": "Not Yet", "symbol": "SOON", "listing": "2026-12-01", "listing_expected": True},
            {**base, "id": "e", "name": "Withdrawn Co", "issue_status": "withdrawn"},
            {**base, "id": "f", "name": "US Co", "market": "US"}]
    got = blog_research.ipo_facts(rows, now)
    assert [g["name"] for g in got] == ["No Prices", "Listed Co"] or [g["name"] for g in got] == ["Listed Co", "No Prices"]
    one = next(g for g in got if g["name"] == "Listed Co")
    assert (one["issue_price"], one["open_pct"], one["close_pct"], one["sub_times"], one["listing"]) == (100.0, 12.0, 8.0, 33.5, "2026-10-01")
    assert next(g for g in got if g["name"] == "No Prices")["close_pct"] is None


def index_series(years=9, start=date(2017, 11, 1)):
    """A rising index with dips: closes on weekdays."""
    out, d, level = {}, start, 10000.0
    end = start + timedelta(days=int(years * 365.25))
    n = 0
    while d <= end:
        if d.weekday() < 5:
            n += 1
            level *= 1 + 0.0004 + (0.012 if n % 37 == 0 else 0) - (0.014 if n % 29 == 0 else 0)
            out[d.isoformat()] = round(level, 2)
        d += timedelta(days=1)
    return out


def test_the_sip_post_is_the_sip_test_engines_own_arithmetic(w):
    closes = index_series()
    post = blog_research.sip_vs_lump(closes, datetime(2026, 11, 3, tzinfo=timezone.utc))
    assert post["slug"] == "sip-vs-lump-sum-nifty-50"
    days = sorted(closes)
    leg = {"symbol": "NIFTY 50", "weight": 1.0, "closes": {d: closes[d] / 100 for d in days}, "days": days, "high": {}, "kind": "in_etf"}
    plan = {"mode": "amount", "amount": 10000, "qty": 1, "freq": "monthly", "dom": 1, "weekday": 0, "step_up": 0.0, "rule": "plain", "dip": 0.1, "extra": 0.5,
            "brokerage": 0.0, "lookback": 252}
    start = next(d for d in days if d >= sip_test._add_years(days[-1], -8))
    head = sip_test.simulate([leg], plan, start, days[-1])
    lump = sip_test._once([leg], {**plan, "amount": head["invested"]}, head["start"], days[-1])
    tab = next(b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "")["rows"]
    from app import email_kit as kit
    assert tab[0][1:] == [kit.inr(head["invested"], 0), kit.inr(lump["invested"], 0)] and tab[1][1:] == [kit.inr(head["value"], 0), kit.inr(lump["value"], 0)]
    assert tab[3][1:] == [kit.pct(head["xirr"] * 100, 1), kit.pct(lump["xirr"] * 100, 1)] and tab[5][1] == kit.inr(head["charges"], 0)
    assert head["charges"] > 0 and f"{head['instalments']} months" in blog.plain_text(post["blocks"])
    spread = next(b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "Horizon")["rows"]
    assert [r[0] for r in spread] == ["3 years", "5 years"]
    # the 5-year row: recomputed from the engine for every start month
    starts = [m for m in sip_test._months(days[0], days[-1]) if m >= days[0] and sip_test._add_years(m, 5) <= days[-1]]
    ahead = lump_ahead = windows = 0
    for s in starts:
        e5 = sip_test._add_years(s, 5)
        a = sip_test.simulate([leg], plan, s, e5, keep=False)
        b = sip_test._once([leg], {**plan, "amount": a["invested"]}, a["start"], e5)
        windows += 1
        ahead += a["value"] > b["value"]
        lump_ahead += b["value"] > a["value"]
    assert spread[1][1:4] == [str(windows), str(ahead), str(lump_ahead)]
    text = blog.plain_text(post["blocks"])
    for must in ("price index", "dividends are not included", "stamp duty", "Limits", "Method", "no sale is made"):
        assert must.lower() in text.lower(), must
    assert blog_research.sip_vs_lump({d: v for d, v in list(closes.items())[:300]}) is None            # under four years of history


def test_no_post_uses_advice_wording_or_a_data_providers_name(w):
    posts = [blog_research.classic_strategies(library_rows()), blog_research.ipo_listing_day(ipo_facts()), blog_research.sip_vs_lump(index_series()),
             blog.brief_post(issue_for("IN")), blog.brief_post(issue_for("US")), blog.brief_post(issue_for("IN", day=HOLIDAY, indices=[]))]
    for post in posts:
        assert post is not None
        assert blog_research.advice_words(post) is None, (post["slug"], blog_research.advice_words(post))
        everything = (post["title"] + post["summary"] + blog.plain_text(post["blocks"]) + blog.blocks_html(post["blocks"])).lower()
        for v in VENDORS:
            assert v not in everything, (post["slug"], v)
    # the word list does catch advice
    assert blog_research.advice_words({"title": "t", "summary": "s", "blocks": [{"t": "p", "text": "You should buy this."}]})
    assert blog_research.advice_words({"title": "t", "summary": "s", "blocks": [{"t": "p", "text": "The best stock to own"}]})


def test_a_research_post_is_updated_in_place_and_only_when_its_words_change(w):
    post = blog_research.ipo_listing_day(ipo_facts(), datetime(2026, 11, 3, tzinfo=timezone.utc))
    at = datetime(2026, 11, 3, 5, 0, tzinfo=timezone.utc)
    assert blog.upsert_research({**post, "published_at": at.isoformat()}, at) == "new"
    before = blog.get(post["slug"])
    assert blog.upsert_research(post, at + timedelta(days=30)) == "same"
    assert blog.get(post["slug"])["updated_at"] == before["updated_at"]                       # nothing changed: no new "last changed" day
    more = ipo_facts() + [{"name": "Zeta", "symbol": "ZETA", "segment": "mainboard", "listing": "2026-10-20", "issue_price": 50.0, "open_pct": 1.0, "close_pct": 2.0, "sub_times": 3.0}]
    newer = blog_research.ipo_listing_day(more, datetime(2026, 12, 3, tzinfo=timezone.utc))
    assert blog.upsert_research(newer, datetime(2026, 12, 3, 5, 0, tzinfo=timezone.utc)) == "updated"
    after = blog.get(post["slug"])
    assert after["published_at"] == before["published_at"] and after["updated_at"].startswith("2026-12-03") and "5 have a listing-day close" in json.dumps(after["body"])
    blog.set_published(post["slug"], False)
    assert blog.upsert_research(newer, datetime(2026, 12, 4, tzinfo=timezone.utc)) == "same" and blog.get(post["slug"])["published"] is False      # an admin's hiding stays
    assert len(db.sb().table("blog_posts").select("slug").execute().data) == 1


def test_generate_runs_each_builder_and_one_failing_leaves_the_others(w):
    def boom(now):
        raise RuntimeError("the source is down")
    out = blog_research.generate(datetime(2026, 11, 3, tzinfo=timezone.utc), builders=[
        ("ipo", lambda now: blog_research.ipo_listing_day(ipo_facts(), now)), ("sip", boom), ("none", lambda now: None),
        ("advice", lambda now: {"slug": "bad-advice-post", "kind": "research", "title": "Pick this", "summary": "You should buy it.", "blocks": [{"t": "p", "text": "x"}]})])
    assert [(m["post"], m["result"]) for m in out["made"]] == [("ipo", "new"), ("none", "nothing to say")]
    assert any(p.startswith("sip: RuntimeError") for p in out["problems"]) and any(p.startswith("advice: left out") for p in out["problems"])
    assert blog.get("bad-advice-post") is None and blog.get("ipo-listing-day-india-2026-so-far")
    assert blog_research.last_run()["problems"] == out["problems"]


def test_the_monthly_run_comes_once_a_month_from_the_third(w, monkeypatch):
    runs = []
    monkeypatch.setattr(blog_research, "generate", lambda now=None, builders=None: runs.append(now) or {})
    ist = lambda y, m, d: datetime(y, m, d, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert blog_research.run_monthly(ist(2026, 11, 2)) is None and runs == []
    assert blog_research.run_monthly(ist(2026, 11, 3)) == {} and len(runs) == 1
    assert blog_research.run_monthly(ist(2026, 11, 20)) is None and len(runs) == 1                     # already this month
    assert blog_research.run_monthly(ist(2026, 12, 3)) == {} and len(runs) == 2
    # the newsletter job asks on the days it may run, and once the month's run is done or looked at, not again
    asked = []
    monkeypatch.setattr(blog_research, "run_monthly", lambda now=None: asked.append(now))
    j = job.Job()
    j.research_posts(ist(2027, 1, 2))
    assert len(asked) == 1                                      # too early: asked, and it answered nothing; tried again on the next tick
    j.research_posts(ist(2027, 1, 4))
    assert len(asked) == 2
    j.research_posts(ist(2027, 1, 5)); j.research_posts(ist(2027, 1, 20))
    assert len(asked) == 2                                      # the month is settled: no look at all
    j.research_posts(ist(2027, 2, 3))
    assert len(asked) == 3
    monkeypatch.setattr(blog_research, "run_monthly", lambda now=None: 1 / 0)
    job.Job().research_posts(ist(2027, 3, 3))                   # a failing run never raises into the newsletter job


# ---------- admin ----------
def test_admin_lists_posts_hides_and_shows_them_and_runs_the_generator(w, monkeypatch):
    c = w["client"]
    blog.save_brief(issue_for("IN"))
    blog.save_brief(issue_for("IN", day=HOLIDAY, indices=[], sections=[]))
    assert c.get("/admin/blog").status_code in (401, 403)
    assert c.get("/admin/blog", headers=headers("pro-token")).status_code == 403                    # a paying user isn't the owner
    r = c.get("/admin/blog", headers=ADMIN).json()
    assert sorted(p["slug"] for p in r["posts"]) == ["india-market-brief-2026-10-01", "india-market-brief-2026-10-02"]
    assert all("body" not in p for p in r["posts"]) and r["counts"] == {"posts": 2, "shown": 1, "hidden": 0, "not_indexed": 1}
    assert c.post("/admin/blog/posts/india-market-brief-2026-10-01/published", json={"published": False}).status_code in (401, 403)
    off = c.post("/admin/blog/posts/india-market-brief-2026-10-01/published", json={"published": False}, headers=ADMIN)
    assert off.status_code == 200 and off.json()["published"] is False
    assert c.get("/blog/india-market-brief-2026-10-01").status_code == 404
    assert "india-market-brief-2026-10-01" not in c.get("/blog/feed.xml").text + c.get("/sitemaps/blog.xml").text + c.get("/blog").text
    assert c.get("/admin/blog", headers=ADMIN).json()["counts"]["hidden"] == 1
    on = c.post("/admin/blog/posts/india-market-brief-2026-10-01/published", json={"published": True}, headers=ADMIN)
    assert on.json()["published"] is True and c.get("/blog/india-market-brief-2026-10-01").status_code == 200
    assert c.post("/admin/blog/posts/no-such-post/published", json={"published": True}, headers=ADMIN).status_code == 404
    started = []
    monkeypatch.setattr(blog_research, "generate", lambda now=None, builders=None: started.append(1) or {})
    assert c.post("/admin/blog/research", headers=ADMIN).json() == {"started": True, "running": True}
    assert c.post("/admin/blog/research").status_code in (401, 403)


def test_admin_adds_posts_for_the_briefs_already_stored(w, monkeypatch):
    c = w["client"]
    for region, day in (("IN", THU), ("IN", THU + timedelta(days=1)), ("US", THU)):
        job.save(issue_for(region, day))
    job.save({**issue_for("IN", day=THU + timedelta(days=2)), "weekly": True, "id": "market.IN.2026-10-03-weekly"})
    r = c.post("/admin/blog/briefs", headers=ADMIN).json()
    assert r == {"added": 3, "skipped": 0}
    assert c.post("/admin/blog/briefs", headers=ADMIN).json() == {"added": 0, "skipped": 3}              # nothing twice
    assert len(db.sb().table("blog_posts").select("slug").execute().data) == 3


def test_generate_reads_the_apps_own_library_ipo_tracker_and_index_history(w, monkeypatch):
    """The three research posts from the sources the app holds (not handed data): the library's entries, the tracker's rows and
    the index candles the world serves."""
    import time_machine
    from app import ipo
    for e in library_rows():
        library.save({**e, "published_at": "2026-10-20T00:00:00+00:00", "copies": 0})
    library._official_cache[0] = 0.0
    base = {"market": "IN", "segment": "mainboard", "open": "2026-09-24", "close": "2026-09-26", "price": 100.0, "listing": "2026-10-01"}
    ipo.save("IN", [{**base, "id": "alpha", "name": "Alpha Foods", "symbol": "ALPHA", "sub": {"times": 20.0},
                     "perf": {"basis": "prices", "issue_price": 100.0, "listing_price": 110.0, "listing_change_pct": 10.0, "day_close": 108.0, "day_change_pct": 8.0}},
                    {**base, "id": "beta", "name": "Beta Power", "symbol": "BETA", "listing": "2026-10-06"}], {})
    now = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
    with time_machine.travel(now, tick=False):
        out = blog_research.generate(now, builders=blog_research.source_posts())
    assert out["problems"] == [] and [m["result"] for m in out["made"]] == ["new", "new", "new"]
    assert sorted(m["slug"] for m in out["made"]) == ["classic-strategies-ten-markets-after-costs", "ipo-listing-day-india-2026-so-far", "sip-vs-lump-sum-nifty-50"]
    ipo_post = blog.get("ipo-listing-day-india-2026-so-far")
    assert "2 issues listed between 1 Oct 2026 and 6 Oct 2026; 1 has a listing-day close in the tracker and is counted below. 1 lacks it" in blog.plain_text(
        ipo_post["body"]["blocks"])
    page_html = page(w["client"], "/blog/research")
    assert page_html.count('class="post"') == 3 and "Classic strategies across ten markets, after costs" in page_html
    assert all(urls(w["client"].get("/sitemaps/blog.xml").content).get(f"https://stratlab.studio/blog/{m['slug']}") for m in out["made"])
    again = blog_research.generate(now, builders=blog_research.source_posts())
    assert [m["result"] for m in again["made"]] == ["same", "same", "same"]


def test_a_post_carries_the_ad_slot_only_while_ads_are_on(w, monkeypatch):
    # ADS-1 on the blog: the slot is added as the page is sent, so it follows the switch and a stored post never holds one
    from app.config import settings
    blog.save_brief(issue_for("IN"), datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
    c = w["client"]
    monkeypatch.setattr(settings, "ADS_ENABLED", False)
    assert 'class="ad"' not in c.get("/blog/india-market-brief-2026-10-01").text
    monkeypatch.setattr(settings, "ADS_ENABLED", True)
    monkeypatch.setattr(settings, "ADSENSE_CLIENT", "ca-pub-8125241692814953")
    monkeypatch.setattr(settings, "ADSENSE_SLOT_PUBLIC", "1234567890")
    html = c.get("/blog/india-market-brief-2026-10-01").text
    assert html.count('class="ad"') == 1 and '/ads.js' in html
    assert 'class="ad"' not in c.get("/blog").text                  # the lists stay plain
