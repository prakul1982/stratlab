"""PUB-2: the top half of a company's public page: the name, the price, the share-price chart, then even key figures whose values share a
baseline, the explanations last. Every number stays what it was; only where it sits and how it is set out changed."""
import re
from html import unescape

import pytest

from app import stock_pages
from tests import world
from tests.test_pub1 import _facts


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()
    yield built
    built["close"]()


def _page(**kw) -> str:
    f = _facts(**{"price": 2000.0, "high52": 2400.0, "low52": 1700.0, **kw})       # a price the test company's market cap agrees with (the share count is in range)
    return stock_pages.render(f, "IN", f["symbol"], f["name"])


# ---------- the company page ----------
def test_the_page_runs_price_chart_figures_then_sections_then_about_then_the_folded_explanations(w):
    for url in ("/stocks/in/RELIANCE", "/stocks/us/AAPL"):
        t = w["client"].get(url).text
        marks = ["<b data-price>", "<h2>Share price</h2>", "<h2>Key figures</h2>", "<h2>Price trend</h2>", "<h2>Revenue and profit</h2>", "data-faq",
                 "Go further with", "<h2>Browse companies</h2>", "data-how"]
        at = [t.index(m) for m in marks if m in t]
        assert len(at) >= 8 and at == sorted(at), (url, [m for m in marks if m in t])
        assert t.count("<h1>") == 1 and t.count("<details class=\"card how\" data-how>") == 1
        # the long wording of the P/E and the minority interests is at the foot, folded, and still in the page
        how = t[t.index("data-how"):]
        assert "P/E: the last close divided by earnings per share" in how and "<summary>How these figures are worked out</summary>" in how
    reliance = w["client"].get("/stocks/in/RELIANCE").text
    assert reliance.index("data-pe-basis") > reliance.index("Go further with")          # the P/E against the profit shown: with the explanations, not under the figures


def test_the_header_is_the_name_one_quiet_line_the_price_and_one_short_advice_line(w):
    t = w["client"].get("/stocks/in/RELIANCE").text
    head = t[t.index("<h1>"):t.index("<h2>Share price</h2>") if "<h2>Surveillance" not in t else t.index("<h2>")]
    assert re.search(r'<h1>Reliance Industries Ltd <span class="muted">\(RELIANCE\)</span></h1>', head)
    assert '<p class="sub muted" title="NSE · Energy · Refineries">NSE · Energy · Refineries</p>' in head and "eyebrow" not in t
    assert re.search(r'<p class="px-line"><b data-price>₹[\d,.]+</b><span class="px-chg" data-day hidden></span></p>', head)
    assert re.search(r'<p class="small muted" data-as-of>As of \d+ \w{3} \d{4} close\.</p>', head)
    assert '<p class="small muted" data-advice>Facts from reported results and exchange filings. Not investment advice.</p>' in head
    assert "Prices are closing prices" not in t and len(re.sub(r"<[^>]*>", "", head).split("Not investment advice")[0]) < 400        # no paragraph before the chart
    assert "data-price=" in t and "data-price-at=" in t                      # what the chart's script checks the day's move against


def test_the_script_fills_in_the_days_move_only_from_the_closes_it_reads():
    js = stock_pages.CHART_JS
    assert "function dayChange()" in js and "[data-day]" in js
    assert "data.t[n - 1] !== at" in js and "Math.abs(last - shown) > shown * 0.005" in js and "data.t[n - 1] - data.t[n - 2] > 5" in js       # the day and price of the page, and a gap of days is no day's move
    assert "\\u2212" in js and "out.hidden = false" in js


def test_key_figures_are_tiles_with_a_short_label_a_value_and_a_unit_line():
    t = _page()
    tiles = re.findall(r'<div class="stat[^"]*" title="([^"]*)"><span>([^<]*)</span><b>([^<]*)</b><small>([^<]*)</small></div>', t)
    got = {label: (value, unescape(line)) for _, label, value, line in tiles}
    assert got["Market cap"] == ("₹7.70 lakh crore", "last close × shares") and got["P/E"] == ("14.3", "on reported profit, last four quarters")
    assert got["Return on equity"][1] == "year to Mar 2026" and got["EBITDA margin"][0] == "28%" and got["Debt to equity"][0] == "0.10"
    assert got["Dividend yield"] == ("1.10%", "last 12 months") and got["Net margin"][0] == "19.4%"
    assert all(len(label) <= stock_pages.TILE_LABEL_MAX for _, label, _, _ in tiles)            # a label is short: one line, two on a phone, never three
    # the price is in the header and the range is a row of its own, so neither is a tile
    assert "Last close" not in "".join(label for _, label, _, _ in tiles) and "range" not in "".join(label for _, label, _, _ in tiles).lower()


def test_the_minority_interest_case_keeps_both_profits_each_named_in_a_short_label():
    t = _page(profit_ttm=88167.0)
    got = {label: (value, line) for _, label, value, line in re.findall(r'<div class="stat[^"]*" title="([^"]*)"><span>([^<]*)</span><b>([^<]*)</b><small>([^<]*)</small></div>', t)}
    assert got["Profit, last 12 months"] == ("₹53,870 cr", "to shareholders") and got["Profit incl. minorities"] == ("₹88,167 cr", "last 12 months")
    assert got["Profit, last 12 months"][0].startswith("₹") and got["Profit, last 12 months"][0].endswith(" cr")
    assert re.search(r'title="Net profit incl\. minority interests, last 12 months \(₹ crore\)"', t)        # the full wording is the tile's title


def test_a_figure_that_isnt_there_has_no_tile_and_no_n_a_and_a_page_with_none_has_no_card():
    t = _page(pe=None, div_yield=None, roe=None, opm=None, net_margin=None, debt_equity=None)
    assert "<span>P/E</span>" not in t and "<span>Dividend yield</span>" not in t and "<b>n/a</b>" not in t and "<b>–</b>" not in t
    assert "<span>Market cap</span>" in t
    bare = _page(pe=None, div_yield=None, roe=None, opm=None, net_margin=None, debt_equity=None, market_cap=None, high52=None, low52=None, profit_ttm=None)
    assert "Key figures" not in bare and 'class="tiles' not in bare and "data-range" not in bare


def test_the_tiles_fill_their_rows_so_no_place_is_empty():
    for t in (_page(), _page(profit_ttm=-40.0, pe=None), _page(div_yield=None), _page(bank=True), _page(pe=None, div_yield=None, roe=None)):
        cols = int(re.search(r'class="tiles c(\d)"', t).group(1))
        n = len(re.findall(r'<div class="stat', t))
        rest = (-n) % cols
        assert cols in (2, 3, 4) and rest <= (-n) % 4 and rest <= (-n) % 3 or cols == min(n, 4)          # the column count that leaves the fewest empty places
        # a short last row's last tile takes the places that are left (fillN spans N columns); otherwise the rows are whole
        assert (f"fill{rest + 1}" in t) == bool(rest), (n, cols)


def test_the_range_is_its_own_full_width_row_with_the_last_close_marked_between_its_ends():
    t = _page(price=100.0, low52=80.0, high52=120.0, market_cap=None)
    row = re.search(r'<div class="range" data-range>.*?</div>', t, re.S).group(0)
    assert "1-year range (intraday)" in row and 'x="50.0%"' in row and "Last close ₹100.00" in row
    assert re.search(r'<small>Low</small> <b>₹80\.00</b>', row) and re.search(r'<small>High</small> <b>₹120\.00</b>', row)
    assert 'aria-label="From a low of ₹80.00 to a high of ₹120.00, with the last close at ₹100.00"' in row
    assert t.index("data-range") < t.index('class="tiles')                      # above the tiles, not a tile beside them
    assert 'x="100.0%"' in _page(price=2400.0, high52=2400.0) and 'x="0.0%"' in _page(price=1700.0, low52=1700.0)       # the ends of the bar, never beyond
    since = _page(range_since="2026-10-01")
    assert "Range since listing on 1 Oct 2026 (intraday)" in since


def test_the_css_gives_each_row_one_baseline_and_two_to_a_row_on_a_phone():
    css = stock_pages.STYLE
    # label, value and unit line are three grid rows the tiles of a row share (subgrid), the label sitting on the value: one baseline whatever the label's length
    assert "@supports (grid-template-rows:subgrid){.stat{display:grid;grid-row:span 3;grid-template-rows:subgrid" in css and ".stat span{align-self:end}" in css
    assert ".stat b{display:block;font-size:22px;line-height:1.25;font-weight:600;white-space:nowrap}" in css
    assert ".tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))" in css and ".tiles.c3{grid-template-columns:repeat(3,minmax(0,1fr))}" in css
    assert "@media (max-width:640px){.tiles,.tiles.c3,.tiles.c4{grid-template-columns:repeat(2,minmax(0,1fr))" in css and ".tiles>.stat:last-child:nth-child(odd){grid-column:1/-1}" in css
    assert ".stat small{display:block;font-size:12.5px" in css and ".rb-now{fill:var(--ink-2);font-size:13px" in css      # nothing under 12 px


def test_there_is_no_about_section_saying_the_figures_again_and_the_us_page_has_the_same_top(w):
    t = w["client"].get("/stocks/us/AAPL").text
    assert "data-about" not in t and "<h2>About Apple Inc.</h2>" not in t                       # (LIVE2-018) the figures are in the tiles, the table and the questions
    assert re.search(r'<b data-price>\$[\d,.]+</b>', t) and "<h2>Key figures</h2>" in t and "$" in re.search(r'class="range-ends".*?</p>', t, re.S).group(0)
    assert "Its last close was" not in t and "Its market value is" not in t
