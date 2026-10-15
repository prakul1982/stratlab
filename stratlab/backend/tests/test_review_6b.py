"""Review 6b: official library entries past the read cap, stale share card, share cache headers, sitemap and /stocks links."""
import pytest

from app import db, library, library_seed, public, site_pages, stock_pages
from app.config import settings
from tests.pngmaker import png_b64
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)

PNG = png_b64(data_url=False)


@pytest.fixture
def capped(monkeypatch):
    """A store whose plain prefix read gives only the newest CAP rows, as the real one does at 1000."""
    kv, cap = {}, 3
    monkeypatch.setattr(db, "set_setting", lambda k, v: (kv.pop(k, None), kv.__setitem__(k, v)))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "delete_setting", lambda k: kv.pop(k, None))
    monkeypatch.setattr(db, "settings_with_prefix",
                        lambda p, limit=cap: [v for k, v in reversed(list(kv.items())) if k.startswith(p)][:limit])
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, page=1000: [(k, v) for k, v in kv.items() if k.startswith(p)])
    library._official_cache[0] = 0.0
    return kv


def test_official_entries_stay_listed_under_newer_user_entries(capped):
    library.save({"id": "seed-golden", "owner": library.OFFICIAL_OWNER, "official": True, "name": "Golden", "verdict": {}})
    for i in range(10):                                        # many newer user entries, well over the cap of 3
        library.save({"id": f"user-{i}", "owner": f"u{i}", "name": f"Mine {i}", "verdict": {}})
    assert [e["id"] for e in library.public_entries()] == ["seed-golden"]
    assert [e["id"] for e in library_seed.seeded()] == ["seed-golden"]
    assert len(library.all_entries()) == 3


def test_a_refresh_without_a_valid_picture_drops_the_old_one(api, capped):
    nb = api.post("/notebooks", json={"name": "T", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    token = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={"image": "data:image/png;base64," + PNG}).json()["token"]
    assert public.has_image(token)
    api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={"image": "data:image/png;base64,bm90IGEgcG5n"})
    assert not public.has_image(token) and api.get(f"/v/{token}.png").status_code == 404
    assert api.get(f"/public/v/{token}").status_code == 200       # the link itself stays


def test_share_responses_are_not_kept_long(api, capped):
    nb = api.post("/notebooks", json={"name": "T", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    token = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={"image": "data:image/png;base64," + PNG}).json()["token"]
    assert api.get(f"/v/{token}").headers["cache-control"] == "public, max-age=60"
    assert api.get(f"/v/{token}.png").headers["cache-control"] == "no-cache"


def test_the_pages_sitemap_lists_the_market_lists_and_they_are_indexable(api, monkeypatch):
    monkeypatch.setattr(site_pages, "library_pages", lambda: [])
    xml = stock_pages.sitemap("pages")
    for r in ("in", "us"):
        assert f"<loc>{settings.PUBLIC_SITE_URL}/stocks/{r}</loc>" in xml
        page = api.get(f"/stocks/{r}")
        assert page.status_code == 200 and "noindex" not in page.text and 'content="index,follow"' in page.text


def test_with_ref_leaves_the_stocks_links_alone():
    site = settings.PUBLIC_SITE_URL
    html = (f'<a href="{site}/stocks">all</a><a href="{site}/stocks/in">in</a><a href="{site}/stocks/in/TCS">c</a>'
            f'<a href="{site}/signup">s</a>')
    out = stock_pages.with_ref(html, "abc")
    assert f'href="{site}/stocks"' in out and f'href="{site}/stocks/in"' in out and f'href="{site}/stocks/in/TCS"' in out
    assert f'href="{site}/signup?ref=abc"' in out
