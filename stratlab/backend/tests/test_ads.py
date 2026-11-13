"""ADS-1: Google AdSense is ready to switch on and does nothing until it is. The helper the server-rendered pages call is empty
while ads are off, a page gets its ad as it is sent (the stored copy never holds one)."""
import re

import pytest

from app import ads, main
from app.config import settings
from tests import world

CLIENT = "ca-pub-1234567890123456"
SLOT = "9876543210"
# a page with enough of its own words to carry an ad (AS1: ads.MIN_ORIGINAL_WORDS)
PROSE = " ".join(f"Sentence {i} of the page's own words, written for this page alone." for i in range(40))
RICH = f"<html><body><main><h1>x</h1><p>{PROSE}</p></main><footer>f</footer></body></html>"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def on(monkeypatch, client=CLIENT, slot=SLOT, switch=True):
    monkeypatch.setattr(settings, "ADS_ENABLED", switch)
    monkeypatch.setattr(settings, "ADSENSE_CLIENT", client)
    monkeypatch.setattr(settings, "ADSENSE_SLOT_PUBLIC", slot)


def test_off_by_default():
    # the shipped defaults: no switch, no IDs
    assert settings.ADS_ENABLED is False and not settings.ADSENSE_SLOT_PUBLIC
    assert settings.ADSENSE_CLIENT == "ca-pub-8125241692814953"          # the owner's publisher ID is the default; no slot ID, so nothing draws
    assert ads.ad_slot_html() == "" and ads.ad_slot_html("blog") == "" and not ads.enabled()
    assert ads.add_to_page("<main>x</main></body>", "company") == "<main>x</main></body>"


@pytest.mark.parametrize("client,slot,switch", [
    (CLIENT, SLOT, False),               # the kill switch beats the IDs
    ("", SLOT, True), (CLIENT, "", True),  # both IDs are needed (the publisher ID is blank here only because the env cleared it)
    ("pub-1234567890123456", SLOT, True), ('ca-pub-1234567890123456"><script>', SLOT, True),   # a pasted mistake never reaches the HTML
    (CLIENT, "12ab", True),
])
def test_helper_is_empty_unless_switch_client_and_slot_are_all_set(monkeypatch, client, slot, switch):
    on(monkeypatch, client, slot, switch)
    assert ads.ad_slot_html() == "" and not ads.enabled()


def test_helper_when_on_is_a_labelled_box_that_holds_its_height_and_one_script(monkeypatch):
    # (updated on purpose, AS1: the helper is given the page it goes on and draws only on one with enough original content)
    on(monkeypatch)
    assert ads.ad_slot_html() == "" and ads.ad_slot_html("public", "<main><p>A few words.</p></main>") == ""
    h = ads.ad_slot_html("public", RICH)
    assert f'data-client="{CLIENT}"' in h and f'data-slot="{SLOT}"' in h and "data-ads" in h
    assert '<p class="ad-label">Advertisement</p>' in h and 'aria-label="Advertisement"' in h      # AdSense policy: labelled
    assert "min-height:280px" in h                                                                  # reserved height: no layout shift
    assert h.count('<script src="/ads.js" defer></script>') == 1 and "adsbygoogle" not in h         # Google's script loads only after consent
    assert "pagead2.googlesyndication.com" not in h
    # a page kind with no ID of its own shares the public one; a name that isn't a plain word is "public"
    assert f'data-slot="{SLOT}"' in ads.ad_slot_html("blog", RICH) and 'data-name="blog"' in ads.ad_slot_html("blog", RICH)
    assert 'data-name="public"' in ads.ad_slot_html('x"><b', RICH)
    # facts only: nothing in the box is advice, and it names no data vendor
    assert not re.search(r"\b(buy|sell|hold|target)\b|yahoo|screener|finnhub", h, re.I)


def test_add_to_page_puts_the_ad_at_the_end_of_main(monkeypatch):
    # (updated on purpose, AS1: the page needs enough original content; a heading alone gets no ad)
    on(monkeypatch)
    assert ads.add_to_page("<html><body><main><h1>x</h1></main></body></html>", "company") == "<html><body><main><h1>x</h1></main></body></html>"
    page = RICH
    got = ads.add_to_page(page, "company")
    assert got.index("</main>") > got.index('class="ad"') > got.index("<h1>") and got.endswith("<footer>f</footer></body></html>")
    assert ads.add_to_page("<p>no main</p>", "company") == "<p>no main</p>"


def test_company_page_has_no_ad_while_off_or_on(w, monkeypatch):
    # (updated on purpose, AS1: a company page is one template filled in with the company's figures, so it has no original content of
    # its own by the rule in docs/ADMIN.md and never carries an ad, even with ads on: AdSense allows no ad on auto-generated pages)
    c = w["client"]
    off = c.get("/stocks/in/RELIANCE").text
    assert 'class="ad"' not in off and "ads.js" not in off
    on(monkeypatch)
    t = c.get("/stocks/in/RELIANCE").text
    assert '<main id="main" data-shared>' in t and ads.original_words(t) == 0
    assert 'class="ad"' not in t and "/ads.js" not in t
    assert 'class="ad"' not in c.get("/stocks/in/RELIANCE?ref=ABCDEFGH").text


def test_no_ad_on_pages_that_are_not_a_company(w, monkeypatch):
    on(monkeypatch)
    c = w["client"]
    for url in ("/stocks", "/stocks/in", "/stocks/in/NOPE", "/sitemap.xml", "/robots.txt"):
        assert 'class="ad"' not in c.get(url).text, url


def test_original_words_counts_the_pages_own_text_only():
    """AS1: the measurable rule (docs/ADMIN.md). Words in <main> count; navigation, header, footer, forms, tables, charts, buttons, link
    text and anything marked data-shared don't, and a number is not a word."""
    nav = "<nav>" + "Home Blog Library " * 50 + "</nav>"
    table = "<table><tr><td>" + "Revenue profit margin " * 50 + "</td></tr></table>"
    links = "<ul>" + "".join(f'<li><a href="/x{i}">Company name {i}</a></li>' for i in range(60)) + "</ul>"
    shared = "<p data-shared>" + "Facts, not advice. " * 60 + "</p>"
    numbers = "<p>" + "1,234.5 +2.4% 12 Nov 2026 " * 40 + "</p>"
    page = f"<header>{'Menu ' * 40}</header><main><h1>Title words here</h1>{nav}{table}{links}{shared}{numbers}<p>Five words of own text.</p></main><footer>{'Terms ' * 40}</footer>"
    assert ads.original_words(page) == 3 + 5 + 40          # the heading, the sentence, and the month of each of the 40 dates
    assert ads.original_words('<main data-shared><p>' + "Template words. " * 200 + "</p></main>") == 0
    assert ads.original_words("<p>" + "outside main " * 400 + "</p>") == 0
    assert not ads.enough_content(page) and ads.enough_content(RICH)
    assert ads.MIN_ORIGINAL_WORDS == 300
