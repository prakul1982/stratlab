"""ADS-1: Google AdSense is ready to switch on and does nothing until it is. The helper the server-rendered pages call is empty
while ads are off, a page gets its ad as it is sent (the stored copy never holds one)."""
import re

import pytest

from app import ads, main
from app.config import settings
from tests import world

CLIENT = "ca-pub-1234567890123456"
SLOT = "9876543210"


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
    on(monkeypatch)
    h = ads.ad_slot_html()
    assert f'data-client="{CLIENT}"' in h and f'data-slot="{SLOT}"' in h and "data-ads" in h
    assert '<p class="ad-label">Advertisement</p>' in h and 'aria-label="Advertisement"' in h      # AdSense policy: labelled
    assert "min-height:280px" in h                                                                  # reserved height: no layout shift
    assert h.count('<script src="/ads.js" defer></script>') == 1 and "adsbygoogle" not in h         # Google's script loads only after consent
    assert "pagead2.googlesyndication.com" not in h
    # a page kind with no ID of its own shares the public one; a name that isn't a plain word is "public"
    assert f'data-slot="{SLOT}"' in ads.ad_slot_html("blog") and 'data-name="blog"' in ads.ad_slot_html("blog")
    assert 'data-name="public"' in ads.ad_slot_html('x"><b')
    # facts only: nothing in the box is advice, and it names no data vendor
    assert not re.search(r"\b(buy|sell|hold|target)\b|yahoo|screener|finnhub", h, re.I)


def test_add_to_page_puts_the_ad_at_the_end_of_main(monkeypatch):
    on(monkeypatch)
    page = "<html><body><main><h1>x</h1></main><footer>f</footer></body></html>"
    got = ads.add_to_page(page, "company")
    assert got.index("</main>") > got.index('class="ad"') > got.index("<h1>") and got.endswith("<footer>f</footer></body></html>")
    assert ads.add_to_page("<p>no main</p>", "company") == "<p>no main</p>"


def test_company_page_has_no_ad_while_off_and_one_when_on(w, monkeypatch):
    c = w["client"]
    off = c.get("/stocks/in/RELIANCE").text
    assert 'class="ad"' not in off and "ads.js" not in off
    on(monkeypatch)
    t = c.get("/stocks/in/RELIANCE").text
    assert t.count('class="ad"') == 1 and t.count("/ads.js") == 1
    assert t.index("Not investment advice") < t.index('class="ad"') < t.index("<footer")       # in the lower part, above the footer
    # the stored page never holds the ad, so switching it off shows on the next request
    assert 'class="ad"' not in (main.stock_page_store.mem.get("html:IN:RELIANCE") or "")
    monkeypatch.setattr(settings, "ADS_ENABLED", False)
    assert 'class="ad"' not in c.get("/stocks/in/RELIANCE").text
    monkeypatch.setattr(settings, "ADS_ENABLED", True)
    # an invite link keeps the page's own links carrying the code, and the ad is still there once
    assert c.get("/stocks/in/RELIANCE?ref=ABCDEFGH").text.count('class="ad"') == 1


def test_no_ad_on_pages_that_are_not_a_company(w, monkeypatch):
    on(monkeypatch)
    c = w["client"]
    for url in ("/stocks", "/stocks/in", "/stocks/in/NOPE", "/sitemap.xml", "/robots.txt"):
        assert 'class="ad"' not in c.get(url).text, url
