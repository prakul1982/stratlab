"""VR-5 (28 Oct 2026): the visual review of the server-drawn pages on a phone. Each test is a fact about a page that looked wrong by eye."""
import re

from app import blog, blog_pages, stock_pages
from tests.test_blog import w  # noqa: F401  (w is the fixture)


def test_a_table_of_five_columns_or_more_is_drawn_as_cards_on_a_phone_and_a_narrow_one_stays_a_table():
    wide = [{"t": "table", "caption": "India", "head": ["Rule set", "Return", "Passive", "Difference", "Trades", "Checks"],
             "rows": [["20/50 EMA cross", "-30.4%", "+14.1%", "-44.5 pts", "41", "Lost money after costs"]]}]
    html = blog.blocks_html(wide)
    assert '<div class="btbl wide">' in html and '<td data-l="Return">-30.4%</td>' in html and '<td data-l="Checks">Lost money after costs</td>' in html
    assert '<th scope="row">20/50 EMA cross</th>' in html                         # the row's name stays its header
    narrow = [{"t": "table", "caption": "x", "head": ["Index", "Close", "Change"], "rows": [["NIFTY 50", "25,000", "+0.5%"]]}]
    assert '<div class="btbl">' in blog.blocks_html(narrow) and "wide" not in blog.blocks_html(narrow)
    css = blog_pages.STYLE
    assert ".btbl.wide thead{display:none}" in css and ".btbl.wide td::before{content:attr(data-l)" in css
    assert "@media (max-width:640px){.btbl table{font-size:13px}.btbl th,.btbl td{padding:8px 5px}" in css      # the four-column table fits 390px


def test_a_directory_of_bare_symbols_goes_two_across_on_a_phone_and_names_keep_a_row_each(w, monkeypatch):
    css = stock_pages.STYLE
    assert "ul.dir[data-short]{grid-template-columns:repeat(2,minmax(0,1fr))}" in css
    monkeypatch.setattr(stock_pages, "label_of", lambda region, sym, co: sym)               # no company name to show
    assert '<ul class="dir" data-companies data-short>' in stock_pages._dir_list("IN", ["AARTIIND", "ABBOTIND"])
    monkeypatch.setattr(stock_pages, "label_of", lambda region, sym, co: f"{sym.title()} Industries Limited")
    assert '<ul class="dir" data-companies>' in stock_pages._dir_list("IN", ["AARTIIND", "ABBOTIND"])       # names are long: one to a row


def test_the_go_further_buttons_share_one_width_on_a_phone():
    css = stock_pages.STYLE
    assert "@media (max-width:640px){.ctas{flex-direction:column}.ctas .btn{justify-content:center;text-align:center}}" in css
    assert re.search(r'<div class="ctas"><a class="btn"', stock_pages._cta("RELIANCE", "/new", "/deep"))
