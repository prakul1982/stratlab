"""VR-4 (28 Oct 2026): the visual review of what shipped that day. Each test is a fact about a page that looked wrong by eye."""
import re
from datetime import date, datetime, timezone
from pathlib import Path

from app import blog, blog_pages, blog_research, stock_pages
from tests.test_blog import entry, issue_for, library_rows, page, w  # noqa: F401  (w is the fixture)

APP = Path(__file__).resolve().parents[1] / "app"


def test_a_research_posts_table_says_its_period_once_and_a_column_only_where_one_test_differs(w):
    rows = library_rows()
    post = blog_research.classic_strategies(rows, datetime(2026, 11, 3, tzinfo=timezone.utc))
    tables = [b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "Rule set"]     # (the four checks have a table of their own)
    assert tables and all("Period" not in t["head"] and "Other period" not in t["head"] for t in tables)        # every row had the same period
    assert all(len(r) == 6 for t in tables for r in t["rows"])
    assert all("tested 1 Oct 2021 to 30 Sep 2026" in t["caption"] for t in tables), tables[0]["caption"]
    # one test over another period: its row names it in small type under its name (PUB-2: no column that is blank for all the others)
    other = library_rows()
    other[0] = entry("ema-20-50", "IN", "20/50 EMA cross", 10.0, 20.0, frm="2026-09-29")
    post = blog_research.classic_strategies(other, datetime(2026, 11, 3, tzinfo=timezone.utc))
    india = next(b for b in post["blocks"] if b["t"] == "table" and b["caption"].startswith("India"))
    assert "Other period" not in india["head"] and all(len(r) == 6 for r in india["rows"])
    named = [r[0][1]["s"] for r in india["rows"] if isinstance(r[0], list)]
    assert named == ["Tested 29 Sep 2026 to 30 Sep 2026"] and len(india["rows"]) > 1


def test_a_brief_does_not_show_the_scans_shorthand(w):
    blog.save_brief(issue_for("IN"), datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
    html = page(w["client"], "/blog/india-market-brief-2026-10-01")
    assert "matches the Stage 2 rule" in html and "(ST S2)" not in html and "ST S2" not in html


def test_the_blog_list_gives_each_brief_its_figures_not_its_day_and_not_the_footer_line_again(w):
    blog.save_brief(issue_for("IN"), datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
    html = page(w["client"], "/blog")
    card = re.search(r'<a class="post" href="/blog/india-market-brief-2026-10-01">.*?</a>', html, re.S).group(0)
    assert "NIFTY 50 closed at 24,812.30 (+0.42%)" in card
    assert "Thursday 1 October 2026" not in card and "Facts, not advice" not in card
    assert "Facts, not advice" in html                      # the page's own lead says it once
    # the post's own description and the feed keep the whole summary
    assert "Facts, not advice." in page(w["client"], "/blog/india-market-brief-2026-10-01")
    assert blog_pages._card_text({"kind": "research", "summary": "A study. Facts, not advice."}) == "A study."
    assert blog_pages._card_text({"kind": "brief", "summary": "The India market was closed on Friday 2 October 2026 (holiday)."}).startswith("The India market was closed")


def test_a_markets_own_directory_page_names_its_market(w):
    c = w["client"]
    both, india, us = page(c, "/stocks"), page(c, "/stocks/in"), page(c, "/stocks/us")
    assert "<h1>Company pages</h1>" in both and "Every company listed in India (NSE and BSE) and the US:" in both
    assert "<h1>Companies listed in India</h1>" in india and "Every company listed in India (NSE and BSE): its last close" in india
    assert "and the US" not in india.split("<h1>")[1].split("</p>")[0]
    assert "<h1>Companies listed in the US</h1>" in us and "Every company listed in the US:" in us
    assert "<title>Company pages: India · StratLab</title>" in india and "<title>Company pages: US · StratLab</title>" in us


def test_the_company_pages_figures_and_table_fit_a_phone():
    src = (APP / "stock_pages.py").read_text()
    # a long value ("₹18.94 lakh crore") is set smaller and never wraps in a phone's half-width column beside a one-line value (PUB-2: it no longer takes the row)
    assert '"long": len(val) > 12' in src and ".stat.long b{font-size:17px}" in src and "white-space:nowrap}" in src
    # the revenue table shows whole years, three at a time (two on a narrower card) beside the labels, whatever the phone's width
    assert 'class="tbl fin"' in src and "(100cqw - 110px) / 3" in src and "(100cqw - 110px) / 2" in src and ".tbl.fin{container-type:inline-size;scroll-padding-left:110px}" in src


def test_the_share_price_text_under_the_chart_does_not_say_the_headline_again():
    js = (APP / "stock_chart.js").read_text()
    # the headline says "over 1 year, A to B"; the line under it keeps the highest and lowest close, the screen reader's label keeps the whole sentence
    assert 'sum.textContent = extremes(s) + " Closing prices.";' in js
    assert 'function words(s)' in js and '"The close was " + price(s.c[0])' in js and "Use the left and right arrow keys" in js
    assert 'sum.textContent = words(s)' not in js
