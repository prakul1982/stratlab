"""VR-6 (28 Oct 2026): the harsh visual review of the public company page and the blog after PUB-2, and of the most-used pages. Each test is a
fact about a page that looked wrong by eye."""
import re

import pytest

from app import blog, blog_pages, blog_research, stock_pages
from tests import world
from tests.test_blog import issue_for
from tests.test_pub1 import _facts


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    yield built
    built["close"]()


def _page(**kw) -> str:
    f = _facts(**{"price": 2000.0, "high52": 2400.0, "low52": 1700.0, **kw})
    return stock_pages.render(f, "IN", f["symbol"], f["name"])


def test_the_blogs_tiles_bars_and_folded_method_are_drawn():
    """The merge of PUB-2 into the release dropped the code that drew them: a post showed no headline tiles, no bars and no method fold."""
    html = blog.blocks_html([
        {"t": "stats", "items": [{"v": "3 of 43", "l": "ahead", "s": "after costs"}]},
        {"t": "bars", "series": ["a", "b"], "rows": [{"label": "India", "values": [1, 2]}]},
        {"t": "details", "title": "How", "items": ["one"]}])
    assert '<ul class="kpis"><li><b>3 of 43</b><span>ahead</span><small>after costs</small></li></ul>' in html
    assert '<figure class="hbars">' in html and '<details class="how card" data-method><summary>How</summary>' in html


def test_the_brief_leads_with_one_line_and_a_tile_for_each_index_not_a_paragraph_and_a_table_saying_the_same_figures():
    post = blog.brief_post(issue_for("IN"))
    kinds = [b["t"] for b in post["blocks"]]
    assert kinds[:3] == ["p", "h2", "stats"] and "table" not in kinds[:4]
    assert len(post["blocks"][0]["text"]) < 90                                              # "The India market on Thursday 1 October 2026, from the day's closing figures."
    tiles = post["blocks"][2]["items"]
    assert tiles[0] == {"v": "24,812.30", "l": "NIFTY 50", "s": "+0.42% on the day"}
    assert 'class="kpis"' in blog.blocks_html(post["blocks"])


def test_the_research_posts_say_their_headline_figures_once_in_tiles_and_keep_the_sentences_folded():
    from tests.test_pub2_blog import library_rows
    post = blog_research.classic_strategies(library_rows())
    assert not any(b["t"] == "ul" and b["items"][0].startswith("Against the passive return") for b in post["blocks"])          # not printed under the tiles and bars
    words = next(b for b in post["blocks"] if b["t"] == "details" and b["title"] == "The headline figures in words")
    assert any(i.startswith("Against the passive return, after costs: ahead in") for i in words["items"])
    html = blog.blocks_html(post["blocks"])
    assert html.count("The headline figures in words") == 1 and '<details class="how card" data-words><summary>The headline figures in words' in html
    assert html.count("data-method") == 1                                                      # the method is the one fold the page's tests look for


def test_a_table_of_three_or_four_columns_wraps_to_fit_a_phone_and_the_four_checks_go_four_across():
    css = blog_pages.STYLE
    assert ".btbl:not(.wide) thead th,.btbl:not(.wide) tbody th,.btbl caption{white-space:normal}" in css
    assert ".btbl.wide.w4 tr{grid-template-columns:repeat(4,minmax(0,1fr))}" in css
    assert ".kpis li:last-child:nth-child(odd){grid-column:1/-1}" in css                       # three tiles: the third takes its row, not half of one
    five = [{"t": "table", "head": ["Check", "Passed", "Warning", "Failed", "Not run"], "rows": [["Unseen data", "10", "10", "23", "0"]]}]
    assert '<div class="btbl wide w4">' in blog.blocks_html(five)
    six = [{"t": "table", "head": ["A", "B", "C", "D", "E", "F"], "rows": [["x", "1", "2", "3", "4", "5"]]}]
    assert '<div class="btbl wide">' in blog.blocks_html(six)


def test_a_long_tile_is_half_a_row_on_a_phone_like_the_others_and_only_an_odd_last_tile_takes_its_row():
    """The merge of PUB-2 kept an older rule that gave a long tile (a market cap in lakh crore) a row of its own, so the last-child rule
    stranded the tile before it ("Net margin" alone above "Dividend yield")."""
    css = stock_pages.STYLE
    assert ".stat.wide,.stat.long{grid-column:1/-1}" not in css and ".grid{grid-template-columns:repeat(2" not in css
    assert ".tiles>.stat:last-child:nth-child(odd){grid-column:1/-1}" in css and ".stat.long b{font-size:17px}" in css
    t = _page(market_cap=1895000.0, profit_ttm=88167.0)
    assert re.search(r'<div class="stat long"[^>]*><span>Market cap</span>', t)               # still marked long (a smaller figure), and no longer a row of its own


def test_surveillance_comes_after_the_key_figures_with_a_heading_like_the_others_and_no_grey_paragraph_of_its_own():
    flags = [{"short": "LT-ASM 2", "label": "Long-term ASM, Stage 2", "text": "Margin rules apply.", "as_of": "2026-10-28"}]
    block = stock_pages.surveillance_html(flags)
    assert block.startswith("<h2>Exchange surveillance</h2><div class=\"card\" data-surveillance>") and block.count("not a view on the company") == 1
    assert '<p class="small muted">' not in block
    page = _page()
    got = stock_pages.with_surveillance(page, flags)
    assert got.index("<h2>Key figures</h2>") < got.index("<h2>Exchange surveillance</h2>") < got.index("<h2>Revenue and profit</h2>")
    assert got.index("<h2>Share price</h2>") < got.index("<h2>Exchange surveillance</h2>")


def test_the_folds_do_not_say_show_twice_and_a_day_is_not_plural_for_one():
    t = _page()
    assert "<summary>The closes as a table</summary>" in t and "Show the closes" not in t
    assert stock_pages._trading_days(1) == "1 trading day" and stock_pages._trading_days(16) == "16 trading days"
    t1 = _page(stage="2", stage_days=1, st_up=True, st_days=1)
    assert "for 1 trading day." in t1 and "1 trading days" not in t1


def test_the_note_about_a_missing_market_cap_has_no_word_about_rebuilding_the_page():
    src = open(stock_pages.__file__, encoding="utf-8").read()
    assert "worked out again when the page is next rebuilt" not in src


def test_the_faq_text_runs_the_card_width_like_the_about_card_and_the_line_under_a_name_wraps_on_a_phone():
    css = stock_pages.STYLE
    assert ".faq p{margin:0 0 6px;color:var(--ink-2)}" in css                                   # no 70ch cap: the right third of the card was empty
    assert "@media (max-width:640px){.sub{white-space:normal;overflow:visible}" in css


def test_a_page_with_no_chart_shows_a_short_card_not_280_pixels_of_nothing():
    assert "[data-empty] .plot{height:96px}" in stock_pages.STYLE
    js = open(stock_pages.__file__.replace("stock_pages.py", "stock_chart.js"), encoding="utf-8").read()
    assert 'root.setAttribute("data-empty", "1")' in js
