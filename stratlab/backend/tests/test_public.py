"""Public verdict links: a frozen snapshot without the owner or the rules, an image, a preview page, and turning off."""
import base64
import json
from types import SimpleNamespace

import pytest

from app import db, public
from tests.pngmaker import png_b64
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)

PNG = png_b64(data_url=False)


@pytest.fixture
def store(monkeypatch):
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "delete_setting", lambda k: kv.pop(k, None))
    return kv


def test_share_link_life_cycle(api, store):
    nb = api.post("/notebooks", json={"name": "Trend follower", "question": "Does the 10/30 cross work on BTC?",
                                      "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    exp = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1500}).json()["experiment"]
    r = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={"image": "data:image/png;base64," + PNG}).json()
    token, url = r["token"], r["url"]
    assert url.endswith(f"/v/{token}")
    assert api.get(f"/notebooks/{nb['id']}").json()["experiments"][0]["public"] == token

    snap = api.get(f"/public/v/{token}").json()
    assert snap["verdict"]["headline"] == exp["verdict"]["headline"] and snap["instrument"]["symbol"] == "BTC/USD"
    assert "strategy" not in snap and "user_id" not in str(snap) and "trades" not in snap     # no rules, no owner
    assert len(snap["verdict"]["checks"]) == 4

    page = api.get(f"/v/{token}")
    assert page.status_code == 200 and 'property="og:image"' in page.text and f"/v/{token}.png" in page.text
    assert f"/verdict/{token}" in page.text
    img = api.get(f"/v/{token}.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content.startswith(b"\x89PNG")

    # sharing again keeps the same link
    assert api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={}).json()["token"] == token
    # turning it off
    api.delete(f"/notebooks/{nb['id']}/experiments/1/share")
    assert api.get(f"/public/v/{token}").status_code == 404
    assert api.get(f"/v/{token}", follow_redirects=False).status_code in (302, 307)


def test_verdict_preview_is_kept_out_of_search_and_checks_its_image_without_decoding(api, store, monkeypatch):
    nb = api.post("/notebooks", json={"name": "T", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    token = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={"image": "data:image/png;base64," + PNG}).json()["token"]

    def no_decode(*_a, **_k):
        raise AssertionError("the picture was decoded just to see that it exists")
    monkeypatch.setattr(public, "base64", SimpleNamespace(b64decode=no_decode))
    assert public.has_image(token) is True and public.has_image("nope") is False
    page = api.get(f"/v/{token}")
    assert page.status_code == 200 and '<meta name="robots" content="noindex,follow">' in page.text
    assert f"/v/{token}.png" in page.text and page.headers["cache-control"] == "public, max-age=300"


def test_bad_images_and_tokens_are_refused(api, store):
    nb = api.post("/notebooks", json={"name": "T", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    token = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={"image": base64.b64encode(b"GIF89a").decode()}).json()["token"]
    assert api.get(f"/v/{token}.png").status_code == 404          # not a PNG: no image stored
    assert 'og-image.png' in api.get(f"/v/{token}").text           # falls back to the site image
    assert api.get("/public/v/..%2Fetc").status_code == 404
    # deleting the notebook turns its links off
    api.delete(f"/notebooks/{nb['id']}")
    assert api.get(f"/public/v/{token}").status_code == 404


def test_snapshot_keeps_only_the_stats_the_page_shows(api, store):
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    token = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={}).json()["token"]
    assert set(api.get(f"/public/v/{token}").json()["stats"]) == {"ret", "buy_hold_ret", "mdd", "n"}      # no pnl (it shows the capital)


def test_a_group_snapshot_has_no_member_amounts():
    from app import public
    exp = {"group": {"name": "G", "max_open": 3, "members": [{"symbol": "A", "trades": 4, "pnl": 12345.0, "win": 50, "buy_hold": 7.5}]},
           "stats": {"ret": 5.0, "pnl": 999.0}}
    snap = public.snapshot({"name": "x"}, exp)
    assert snap["group"]["members"] == [{"symbol": "A", "trades": 4, "win": 50, "buy_hold": 7.5}] and "pnl" not in snap["stats"]


def test_the_51st_experiment_turns_off_the_link_of_the_one_it_drops(api, store):
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    token = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={}).json()["token"]
    body = api.rows[nb["id"]]["body"]
    first = body["experiments"][0]
    body["experiments"] = [first] + [{**first, "v": v, "public": None} for v in range(2, 51)]
    assert api.get(f"/public/v/{token}").status_code == 200
    assert api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 730}).status_code == 200
    assert api.get(f"/public/v/{token}").status_code == 404


def test_deleting_a_notebook_turns_off_its_links(api, store):
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    token = api.post(f"/notebooks/{nb['id']}/experiments/1/share", json={}).json()["token"]
    api.delete(f"/notebooks/{nb['id']}")
    assert api.get(f"/public/v/{token}").status_code == 404


def test_the_public_lines_are_the_growth_of_100_not_the_account():
    # the amounts would show the capital: both lines start from 100 at the strategy's start
    from app import public
    snap = public.snapshot({"name": "n"}, {"series": {"t": ["a", "b"], "equity": [250000, 275000], "buy_hold": [250000, 262500]}})
    assert snap["series"]["equity"] == [100.0, 110.0] and snap["series"]["buy_hold"] == [100.0, 105.0]
    assert snap["series"]["indexed"] is True


def test_a_link_shared_before_shows_no_amounts_either(monkeypatch):
    from app import db, public
    old = {"name": "n", "series": {"t": ["a", "b"], "equity": [200000, 220000], "buy_hold": [200000, 210000]},
           "group": {"members": [{"symbol": "A", "pnl": 5000}]}}
    monkeypatch.setattr(db, "get_setting", lambda k: json.dumps(old))
    snap = public.load("a" * 22)
    assert snap["series"]["equity"] == [100.0, 110.0] and "pnl" not in snap["group"]["members"][0]
