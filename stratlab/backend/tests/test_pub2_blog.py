"""PUB-2: the blog's posts: one content width for text and tables, headline numbers as tiles and one small chart, tables whose columns line up,
the method folded, a quiet facts line. Every number stays what it was."""
import re

import pytest

from app import blog, blog_pages, blog_research, stock_pages
from tests import world
from tests.test_blog import index_series, ipo_facts, library_rows


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    yield built
    built["close"]()


def test_a_post_has_one_quiet_facts_line_and_one_width_for_its_text_and_its_tables(w):
    from datetime import datetime, timezone
    from tests.test_blog import issue_for
    blog.save_brief(issue_for("IN"), datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc))
    page = w["client"].get("/blog/india-market-brief-2026-10-01").text
    css = blog_pages.STYLE
    assert len(blog_pages.FACTS) < 130 and blog_pages.FACTS.count(". ") == 1 and 'class="facts">' + blog_pages.FACTS in page and "Facts, not advice." in page
    assert ".facts{font-size:13.5px;color:var(--muted);margin:0 0 22px}" in css and "border-left" not in re.search(r"\.facts\{[^}]*\}", css).group(0)
    assert "article p,article li{max-width:none}" in css and "68ch" not in css                 # the text runs as wide as the tables: one width
    assert ".btbl .l{text-align:left}" in css and "white-space:nowrap" in re.search(r"\.btbl th,\.btbl td\{[^}]*\}", css).group(0)


def test_the_strategy_post_shows_its_headline_numbers_as_tiles_and_a_bar_for_each_market(w):
    post = blog_research.classic_strategies(library_rows())
    blocks = post["blocks"]
    stats = next(b for b in blocks if b["t"] == "stats")
    assert [i["l"] for i in stats["items"]] == ["tests ahead of the passive return", "tests behind it", "tests that traded lost money", "passed their checks"]
    assert all(re.fullmatch(r"\d+ of \d+", i["v"]) for i in stats["items"])
    bars = next(b for b in blocks if b["t"] == "bars")
    assert bars["series"] == ["Ahead", "Behind", "Not compared"] and len(bars["rows"]) == 10
    rows = library_rows()
    assert sum(sum(r["values"]) for r in bars["rows"]) == len(rows)                       # every test is in exactly one bar
    assert sum(r["values"][0] for r in bars["rows"]) == int(stats["items"][0]["v"].split(" ")[0]) and sum(r["values"][1] for r in bars["rows"]) == int(stats["items"][1]["v"].split(" ")[0])
    html = blog.blocks_html(blocks)
    assert html.count('<ul class="kpis">') == 1 and html.count("<li><b>") == 4 and html.count('<figure class="hbars">') == 1
    assert html.count('role="img" aria-label="') == 10 and "Ahead</span>" in html                  # a legend, and every bar says its counts in words
    # the sentences stay below, shorter, for a screen reader and a crawler
    assert "ahead in " in blog.plain_text(blocks) and "passed their checks" in blog.plain_text(blocks)


def test_the_strategy_tables_have_short_unwrapped_headers_fixed_widths_and_no_empty_column(w):
    post = blog_research.classic_strategies(library_rows())
    tables = [b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "Rule set"]
    for t in tables:
        assert t["head"] == ["Rule set", "After costs", "Passive", "Difference", "Trades", "Checks"] and t["align"] == "lrrrrl" and sum(t["widths"]) == 100
        assert len(t["caption"]) < 70 and all(len(r) == 6 for r in t["rows"])                 # a short caption; no "Other period" column
    checks = next(b for b in post["blocks"] if b["t"] == "table" and b["head"][0] == "Check")
    assert checks["head"][1:] == ["Passed", "Failed", "Not run"] and len(checks["rows"]) == 4 and checks["align"] == "lrrr" and "widths" not in checks      # a small table sizes itself to a phone
    html = blog.blocks_html([tables[0]])
    assert '<div class="btbl fx"><table>' in html and "<colgroup>" in html and html.count('<th scope="col" class="l">') == 2 and html.count('<td class="l">') == len(tables[0]["rows"])
    assert 'scope="row" class="l"' in html


def test_a_test_over_another_period_says_so_under_its_name_not_in_a_column():
    rows = library_rows()
    odd = next(r for r in rows if r["market"] == "IN" and r["seed"]["slug"] == "rsi2-revert")
    odd["range"] = {"from": "2026-09-29", "to": "2026-10-28"}
    post = blog_research.classic_strategies(rows)
    india = next(b for b in post["blocks"] if b["t"] == "table" and b["caption"].startswith("India"))
    cell = next(r[0] for r in india["rows"] if isinstance(r[0], list))
    assert cell[1] == {"s": "Tested 29 Sep 2026 to 28 Oct 2026"} and len(india["head"]) == 6
    assert '<small class="sub">Tested 29 Sep 2026 to 28 Oct 2026</small>' in blog.blocks_html([india])


def test_every_post_folds_its_method_and_keeps_its_words_in_the_page(w):
    posts = {"strategies": blog_research.classic_strategies(library_rows()), "ipo": blog_research.ipo_listing_day(ipo_facts()), "sip": blog_research.sip_vs_lump(index_series())}
    for name, title in (("strategies", "How these tests were run"), ("ipo", "How this was worked out"), ("sip", "How the comparison was run")):
        blocks = posts[name]["blocks"]
        assert not any(b["t"] == "h2" and b["text"] == "Method" for b in blocks) and any(b["t"] == "details" and b["title"] == title for b in blocks), name
        html = blog.blocks_html(blocks)
        assert f'<details class="how card" data-method><summary>{title}</summary>' in html and "data-method open" not in html
    assert "slippage" in blog.blocks_html(posts["strategies"]["blocks"]) and "XIRR" in blog.blocks_html(posts["sip"]["blocks"])
    # the IPO and SIP posts lead with tiles too, the SIP one with a bar for each horizon
    assert next(b for b in posts["ipo"]["blocks"] if b["t"] == "stats")["items"][0]["l"] == "issues listed"
    sip = posts["sip"]["blocks"]
    assert len(next(b for b in sip if b["t"] == "stats")["items"]) == 4 and [r["label"] for r in next(b for b in sip if b["t"] == "bars")["rows"]] == ["3 years", "5 years"]
    for p in posts.values():
        assert blog_research.advice_words(p) is None


def test_a_brief_folds_how_it_is_made_and_the_old_blocks_still_draw():
    from tests.test_blog import issue_for
    post = blog.brief_post(issue_for("IN"))
    last = post["blocks"][-1]
    assert last["t"] == "details" and last["title"] == "How this brief is made" and "Nothing here comes from any user's account" in last["items"][0]
    # a stored post written before the tiles, with a "Method" heading and a table with no widths, is drawn as it was
    old = [{"t": "h2", "text": "Method"}, {"t": "ul", "items": ["Data."]}, {"t": "table", "caption": "c", "head": ["A", "B"], "rows": [["x", "1"]]}]
    html = blog.blocks_html(old)
    assert "<h2>Method</h2>" in html and '<div class="btbl"><table>' in html and "<colgroup>" not in html and '<td>1</td>' in html


def test_the_block_cleaner_keeps_only_the_new_blocks_it_knows():
    got = blog.clean_blocks([
        {"t": "stats", "items": [{"v": "3 of 43", "l": "ahead", "s": "after costs"}, {"v": "", "l": "x"}, "junk"]},
        {"t": "bars", "series": ["a", "b"], "rows": [{"label": "India", "values": [1, 2]}, {"label": "", "values": [1]}]},
        {"t": "bars", "series": ["only one"], "rows": [{"label": "India", "values": [1]}]},
        {"t": "details", "title": "How", "items": ["one", ""]}, {"t": "details", "title": "", "items": ["x"]},
        {"t": "table", "head": ["A", "B"], "rows": [["x", "1"]], "align": "lxx", "widths": [10, 10]},
        {"t": "table", "head": ["A", "B"], "rows": [["x", "1"]], "align": "lr", "widths": [40, 60]}, {"t": "script", "text": "<script>"}])
    assert [b["t"] for b in got] == ["stats", "bars", "details", "table", "table"]
    assert got[0]["items"] == [{"v": "3 of 43", "l": "ahead", "s": "after costs"}] and got[1]["rows"] == [{"label": "India", "values": [1, 2]}]
    assert "align" not in got[3] and "widths" not in got[3] and got[4]["align"] == "lr" and got[4]["widths"] == [40, 60]
    html = blog.blocks_html([{"t": "stats", "items": [{"v": "<b>", "l": "<i>"}]}])
    assert "&lt;b&gt;" in html and "<b><b>" not in html


def test_the_list_cards_are_even():
    css = blog_pages.STYLE
    assert "ul.posts a.post{display:grid;gap:4px" in css and "-webkit-line-clamp:2" in css          # a card is its label, its title and at most two lines
