"""The sitemaps say when a page last changed, list the public pages that exist (the landing page's sections, the library and
StratLab's own strategies in it), and leave out company pages that have nothing to show (they are noindex)."""
import re
import xml.etree.ElementTree as ET

import pytest

from app import library, site_pages, stock_pages
from tests import world

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    stock_pages._thin.clear()                 # what this process has already marked belongs to another test's database
    yield built
    built["close"]()


def rows(xml: bytes) -> dict[str, str | None]:
    return {u.find(NS + "loc").text: (u.find(NS + "lastmod").text if u.find(NS + "lastmod") is not None else None) for u in ET.fromstring(xml)}


def test_the_pages_sitemap_lists_every_public_page_with_the_day_it_changed(w):
    got = rows(w["client"].get("/sitemaps/pages.xml").content)
    for path in ("/", "/pricing", "/faq", "/library", "/terms", "/privacy", "/refunds", "/contact"):
        assert "https://stratlab.studio" + path in got, path
    for url, day in got.items():
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""), (url, day)
    assert [p for p, _ in site_pages.PAGES] == ["/", "/pricing", "/faq", "/library", "/terms", "/privacy", "/refunds", "/contact"]


def test_stratlabs_own_strategies_are_listed_and_a_users_are_not(w):
    kv = {}
    mine = {"id": "seed-ema-nifty50", "official": True, "owner": library.OFFICIAL_OWNER, "published_at": "2026-10-02T04:00:00+00:00"}
    theirs = {"id": "user-made-1", "official": False, "owner": "user-9", "published_at": "2026-10-03T04:00:00+00:00"}
    hidden = {"id": "seed-hidden-nifty50", "official": True, "owner": library.OFFICIAL_OWNER, "hidden": True, "published_at": "2026-10-04T04:00:00+00:00"}
    import json
    from app import db
    for e in (mine, theirs, hidden):
        db.set_setting(library.PREFIX + e["id"], json.dumps(e))
    got = rows(w["client"].get("/sitemaps/pages.xml").content)
    assert got["https://stratlab.studio/library/seed-ema-nifty50"] == "2026-10-02"
    assert not any("user-made-1" in u or "seed-hidden" in u for u in got)


def test_company_pages_get_a_day_and_the_empty_ones_are_left_out(w):
    c = w["client"]
    stock_pages.save_list("IN", [{"symbol": f"CO{i:03d}", "name": f"Company {i}"} for i in range(120)])
    before = rows(c.get("/sitemaps/stocks-in-1.xml").content)
    assert "https://stratlab.studio/stocks/in/TCS" in before
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d or "") for d in before.values())
    assert "noindex" in c.get("/stocks/in/TCS").text           # the fake sources have nothing on TCS: a short noindex page
    after = rows(c.get("/sitemaps/stocks-in-1.xml").content)
    assert "https://stratlab.studio/stocks/in/TCS" not in after
    assert "https://stratlab.studio/stocks/in/RELIANCE" in after and len(after) == len(before) - 1
