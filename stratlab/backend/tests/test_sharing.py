"""Growth through sharing: company fact cards with a public link that previews as the card and opens the company's
public page, and invite links that remember who brought whom (once, never yourself, no rewards)."""
import base64
import json
import re
from datetime import datetime, timedelta, timezone

import pytest

from app import company_cards, db, referrals, stock_pages
from tests import world

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()
PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|sec\.gov|nseindia|bseindia", re.I)
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|target|cheap|expensive|undervalued|overvalued)\b", re.I)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def _h(token):
    return world.headers(token)


def _new_account(w, uid, hours_ago=0.5):
    """Make a fake user's account this many hours old."""
    for p in w["db"].tables["profiles"]:
        if p["id"] == uid:
            p["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    db.forget_profile(uid)


# ---------- company fact cards ----------
def test_card_data_is_facts_from_the_public_page(w):
    c = w["client"]
    r = c.get("/cards/company/IN/RELIANCE", headers=_h("pro-token"))
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["name"].startswith("Reliance") and card["symbol"] == "RELIANCE" and card["region"] == "IN"
    assert card["price"].startswith("₹") and " to " in card["range"]
    assert 1 <= len(card["facts"]) <= 4 and all(len(f) == 2 and f[1] != "–" for f in card["facts"])
    assert card["page"] == "https://stratlab.studio/stocks/in/RELIANCE"
    text = json.dumps(card)
    assert not PROVIDERS.search(text) and not ADVICE.search(text)
    us = c.get("/cards/company/us/aapl", headers=_h("pro-token")).json()
    assert us["symbol"] == "AAPL" and us["price"].startswith("$")
    assert w["ai"].calls == 0                                 # no AI anywhere in a card


def test_cards_need_sign_in_and_a_real_company(w):
    c = w["client"]
    assert c.get("/cards/company/IN/RELIANCE").status_code == 401
    assert c.post("/cards/company/IN/RELIANCE", json={}).status_code == 401
    for path in ("/cards/company/IN/NOPE", "/cards/company/XX/RELIANCE", "/cards/company/IN/%3Cscript%3E"):
        assert c.get(path, headers=_h("pro-token")).status_code == 404


def test_a_shared_card_previews_and_opens_the_company_page_with_the_invite(w):
    c = w["client"]
    r = c.post("/cards/company/IN/RELIANCE", headers=_h("pro-token"), json={"image": PNG}).json()
    token, url = r["token"], r["url"]
    assert url == f"https://stratlab.studio/c/{token}"
    again = c.post("/cards/company/IN/RELIANCE", headers=_h("pro-token"), json={}).json()
    assert again["token"] == token                           # one link per user and company
    other = c.post("/cards/company/IN/RELIANCE", headers=_h("free-token"), json={}).json()
    assert other["token"] != token

    page = c.get(f"/c/{token}")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    t = page.text
    code = c.get("/me/referrals", headers=_h("pro-token")).json()["code"]
    for part in ('property="og:title"', 'property="og:description"', f'content="https://stratlab.studio/c/{token}.png"',
                 'name="twitter:card" content="summary_large_image"', f"/stocks/in/RELIANCE?ref={code}", "Facts, not advice"):
        assert part in t, part
    assert not PROVIDERS.search(t) and not ADVICE.search(t)
    img = c.get(f"/c/{token}.png")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content.startswith(b"\x89PNG")
    # without an image the preview falls back to the site's own
    assert "/og-image.png" in c.get(f"/c/{other['token']}").text
    assert c.get(f"/c/{other['token']}.png").status_code == 404


def test_bad_card_tokens_and_images(w):
    c = w["client"]
    for t in ("nope", "x" * 40, "..%2F..%2Fetc", "%3Cscript%3E", "abc def"):
        r = c.get(f"/c/{t}", follow_redirects=False)
        assert r.status_code in (307, 404), (t, r.status_code)
        assert c.get(f"/c/{t}.png").status_code == 404
    r = c.post("/cards/company/IN/RELIANCE", headers=_h("basic-token"), json={"image": "data:image/png;base64,bm90IGEgcG5n"}).json()
    assert c.get(f"/c/{r['token']}.png").status_code == 404           # not a PNG: no image kept
    db.set_setting("card:brokenone", "{not json")
    assert c.get("/c/brokenone", follow_redirects=False).status_code == 307


def test_the_preview_escapes_what_it_shows():
    card = {"region": "IN", "symbol": "X", "name": '"><script>alert(1)</script>', "price": None, "range": None,
            "facts": [["<b>", "1"]], "ref": '"><x'}
    t = company_cards.preview_html("tok123", card, False)
    assert "<script>alert" not in t and "<b>" not in t
    assert "?ref=" not in t                                   # a code that isn't one is left off


def test_stock_page_links_carry_a_valid_invite_code(w):
    c = w["client"]
    code = c.get("/me/referrals", headers=_h("pro-token")).json()["code"]
    t = c.get(f"/stocks/in/RELIANCE?ref={code}").text
    assert f'href="https://stratlab.studio/?ref={code}"' in t                        # sign up
    assert f"symbol=RELIANCE&amp;ref={code}" in t                                     # test a strategy
    assert f"/research/IN/RELIANCE/deep?ref={code}" in t
    assert '<link rel="canonical" href="https://stratlab.studio/stocks/in/RELIANCE">' in t
    assert 'href="/stocks/in/ONGC"' in t                                              # other company pages unchanged
    plain = c.get("/stocks/in/RELIANCE").text
    assert "?ref=" not in plain and "&amp;ref=" not in plain
    for bad in ("<script>", "short", "x" * 40, '"onmouseover'):
        assert "?ref=" not in c.get("/stocks/in/RELIANCE", params={"ref": bad}).text
    r = c.get(f"/stocks/in/reliance?ref={code}", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"].endswith(f"/stocks/in/RELIANCE?ref={code}")


# ---------- invite links ----------
def test_each_user_has_one_unguessable_code(w):
    c = w["client"]
    a = c.get("/me/referrals", headers=_h("pro-token")).json()
    assert referrals.CODE.match(a["code"]) and a["link"] == f"https://stratlab.studio/?ref={a['code']}" and a["joined"] == 0
    assert c.get("/me/referrals", headers=_h("pro-token")).json()["code"] == a["code"]
    b = c.get("/me/referrals", headers=_h("free-token")).json()
    assert b["code"] != a["code"]
    assert c.get("/me/referrals").status_code == 401


def test_a_new_account_is_counted_once_and_nothing_is_granted(w, monkeypatch):
    c = w["client"]
    code = c.get("/me/referrals", headers=_h("pro-token")).json()["code"]
    _new_account(w, "u-free")
    calls = []
    monkeypatch.setattr(referrals, "on_referral_joined", lambda ref, new: calls.append((ref["id"], new["id"])))
    before = {k: dict(p) for p in w["db"].tables["profiles"] for k in [p["id"]]}
    assert c.post("/me/referral", headers=_h("free-token"), json={"code": code}).json() == {"recorded": True}
    assert calls == [("u-pro", "u-free")]
    assert c.post("/me/referral", headers=_h("free-token"), json={"code": code}).json() == {"recorded": False}
    assert c.get("/me/referrals", headers=_h("pro-token")).json()["joined"] == 1
    assert referrals.referred_by("u-free") == "u-pro"
    # no plan time, no plan change, for either side
    after = {p["id"]: p for p in w["db"].tables["profiles"]}
    for uid in ("u-pro", "u-free"):
        for k in ("plan", "plan_status", "current_period_end"):
            assert after[uid].get(k) == before[uid].get(k)
    # another code later doesn't move them
    other = c.get("/me/referrals", headers=_h("basic-token")).json()["code"]
    assert c.post("/me/referral", headers=_h("free-token"), json={"code": other}).json() == {"recorded": False}
    assert referrals.referred_by("u-free") == "u-pro"
    assert c.get("/me/referrals", headers=_h("basic-token")).json()["joined"] == 0


def test_the_hook_does_nothing_yet():
    assert referrals.on_referral_joined({"id": "a"}, {"id": "b"}) is None


def test_no_self_referral_no_old_accounts_no_made_up_codes(w):
    c = w["client"]
    code = c.get("/me/referrals", headers=_h("free-token")).json()["code"]
    _new_account(w, "u-free")
    assert c.post("/me/referral", headers=_h("free-token"), json={"code": code}).json()["recorded"] is False
    # the fake world's accounts are a month old: not new, not counted
    assert c.post("/me/referral", headers=_h("basic-token"), json={"code": code}).json()["recorded"] is False
    _new_account(w, "u-basic", hours_ago=30)
    assert c.post("/me/referral", headers=_h("basic-token"), json={"code": code}).json()["recorded"] is False
    for bad in ("", None, "AAAAAAAAAAAA", "x" * 64, "<script>", code.lower() if code.lower() != code else code.upper()):
        assert c.post("/me/referral", headers=_h("pro-token"), json={"code": bad}).json()["recorded"] is False
    assert c.get("/me/referrals", headers=_h("free-token")).json()["joined"] == 0


def test_same_mailbox_counts_as_yourself():
    assert referrals._mailbox("A.B+x@GoogleMail.com") == referrals._mailbox("ab@gmail.com")
    assert referrals._mailbox("a.b@example.com") != referrals._mailbox("ab@example.com")
    assert referrals._mailbox(None) == ""


def test_admin_sees_invite_counts(w):
    c = w["client"]
    code = c.get("/me/referrals", headers=_h("pro-token")).json()["code"]
    _new_account(w, "u-free")
    _new_account(w, "u-basic")
    c.post("/me/referral", headers=_h("free-token"), json={"code": code})
    c.post("/me/referral", headers=_h("basic-token"), json={"code": code})
    rows = {u["id"]: u for q in ("pro@example", "free@example")
            for u in c.get("/admin/users", params={"q": q}, headers=_h("admin-token")).json()}
    assert rows["u-pro"]["referrals"] == 2 and rows["u-free"]["referrals"] == 0
    assert c.get("/admin/users", headers=_h("pro-token")).status_code == 403


def test_damaged_stored_values_dont_break_anything(w):
    db.set_setting("ref:joined:u-pro", "{oops")
    db.set_setting("ref:user:u-pro", "not-a-code")
    c = w["client"]
    r = c.get("/me/referrals", headers=_h("pro-token")).json()
    assert referrals.CODE.match(r["code"]) and r["joined"] == 0
    assert c.get("/admin/users", headers=_h("admin-token")).status_code == 200


def test_with_ref_only_touches_app_links():
    site = "https://stratlab.studio"
    page = (f'<link rel="canonical" href="{site}/stocks/in/X"><a class="brand" href="{site}/">S</a>'
            f'<a href="{site}/new?market=IN&amp;symbol=X">t</a><a href="{site}/stocks/in/Y">y</a><a href="/stocks/in/Z">z</a>')
    out = stock_pages.with_ref(page, "abcdefghijkl")
    assert f'href="{site}/?ref=abcdefghijkl"' in out and "symbol=X&amp;ref=abcdefghijkl" in out
    assert f'href="{site}/stocks/in/Y"' in out and f'href="{site}/stocks/in/X"' in out and 'href="/stocks/in/Z"' in out
