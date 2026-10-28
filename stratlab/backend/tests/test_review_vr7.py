"""VR-7 (28 Oct 2026): the visual review that put the phone first and looked at Market Watch."""
import pytest

from app import blog, blog_pages, blog_research, stock_pages
from tests import world
from tests.test_blog import library_rows


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    yield built
    built["close"]()


def test_vr7_002_the_strategy_post_folds_each_market_and_keeps_every_figure(w):
    rows = library_rows()
    post = blog_research.classic_strategies(rows)
    folds = [b for b in post["blocks"] if b["t"] == "fold"]
    assert len(folds) == 10 and all(f["note"].endswith(" tests") for f in folds)
    # the group line and the table are inside the fold; the fold's title is the market's heading (an h2 inside the summary)
    assert [b["t"] for b in folds[0]["blocks"]] == ["p", "table"]
    html = blog.blocks_html(post["blocks"])
    assert html.count('<details class="mk"><summary><h2>') == 10 and "<h2>India</h2>" in html
    # every test's row is still in the HTML: its link and its figures
    assert sum(html.count(f'href="/library/{e["id"]}"') for e in rows) == len(rows)
    assert html.count('data-l="After costs"') >= len(rows) - 5            # (a test with no trades says "no trades" in that cell)
    # a fold's words reach the advice check too
    assert "Group:" in blog.plain_text(post["blocks"])
    # a window over 640px draws it open as before, a phone shows one line a market
    css = blog_pages.STYLE
    assert "details.mk::details-content{content-visibility:visible}" in css and "min-height:56px" in css


def test_vr7_002_a_fold_cleans_to_one_level_and_needs_a_title_and_something_inside():
    got = blog.clean_blocks([{"t": "fold", "title": "India", "note": "10 tests", "blocks": [{"t": "p", "text": "Hi"}, {"t": "fold", "title": "no", "blocks": [{"t": "p", "text": "x"}]}]},
                             {"t": "fold", "title": "", "blocks": [{"t": "p", "text": "x"}]}, {"t": "fold", "title": "Empty", "blocks": []}])
    assert got == [{"t": "fold", "title": "India", "note": "10 tests", "blocks": [{"t": "p", "text": "Hi"}]}]


def test_vr7_003_a_to_z_on_a_phone_fills_its_rows_and_leaves_no_row_of_one():
    from app import stock_pages
    cols = stock_pages._az_cols
    for n in range(8, 30):                       # every count of letters a directory can have
        for widest in (6, 7):
            c = cols(n, widest)
            assert widest - 2 <= c <= widest and (n % c or c) > 1, (n, widest, c)            # never a last row of one
    assert (cols(26, 7), cols(27, 7), cols(22, 6)) == (7, 7, 6)
    src = open(stock_pages.__file__, encoding="utf-8").read()
    assert "repeat(var(--az7,7),minmax(0,1fr))" in src and "repeat(var(--az6,6),minmax(0,1fr))" in src and "nav.links[data-az] a{min-width:44px;min-height:44px" in src


def test_vr7_005_the_blog_links_on_a_phone_are_44px_to_tap_without_moving_a_line():
    css = blog_pages.STYLE
    assert ".btbl.wide th[scope=row] a{display:inline-block;padding:14px 0;margin:-14px 0}" in css
    assert ".blog-eyebrow a{display:inline-block;padding:14px 4px;margin:-14px -4px}" in css
    assert "article>p>a:only-child{display:inline-block;padding:14px 0;margin:-14px 0}" in css       # a paragraph that is a link ("Open the rotation chart")
