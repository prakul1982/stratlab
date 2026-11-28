"""social103 (owner, 28 Nov: "daily posting on X and LinkedIn fully automated; I have no time to post"): Admin → Social connects X (OAuth 2.0
with PKCE) and LinkedIn (OpenID Connect + Share on LinkedIn) server-side, keeps the tokens sealed, posts one facts-only theme post a day per
network when switched on, never twice, retries a refused post once, and says what failed in Admin. No real X or LinkedIn call is ever made:
HTTP is a fake here, and the real one refuses under tests."""
import json
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from cryptography.fernet import Fernet

from app import computed, db, public_themes, social, social_post, source_health
from app.config import settings
from app.intel import theme_library
from tests import world

IST = timezone(timedelta(hours=5, minutes=30))
ADMIN, PRO = world.headers("admin-token"), world.headers("pro-token")
SECRETS = ("acc-X-1", "ref-X-1", "acc-X-2", "ref-X-2", "acc-LI-1", "the-x-client-secret", "the-li-client-secret")


def co(t, name, verified=True):
    return {"ticker": t, "name": name, "what": "makes it" if verified else "", "verified": verified}


def theme(sector, layers):
    return {"sector": sector, "generated_at": 1795000000, "ai": None, "placements": {"checked": True}, "summary": f"{sector} companies.",
            "value_chain": [{"layer": n, "companies": [co(t, f"{t.title()} Ltd") for t in ts]} for n, ts in layers], "sub_themes": []}


DEFENCE = theme("Defence", [("Shipyards", ["SHIPA", "SHIPB", "SHIPC", "SHIPD"]), ("Electronics", ["ELA", "ELB", "ELC"]), ("Ammunition", ["AMA", "AMB"])])
RAIL = theme("Railways", [("Coaches", ["RA", "RB", "RC", "RD"]), ("Signalling", ["SA", "SB", "SC", "SD"])])


class FakeNet:
    """X and LinkedIn as the tests need them: every call recorded; answers queued per (method, url) or a default."""

    def __init__(self):
        self.calls = []
        self.queue: dict = {}
        self.tweet = 100

    def answer(self, method, url, *responses):
        self.queue.setdefault((method, url), []).extend(responses)

    def __call__(self, method, url, **kw):
        self.calls.append((method, url, kw))
        q = self.queue.get((method, url))
        if q:
            got = q.pop(0)
            if isinstance(got, Exception):
                raise got
            return got
        if url == social.X_TOKEN:
            return httpx.Response(200, json={"token_type": "bearer", "access_token": "acc-X-1", "refresh_token": "ref-X-1", "expires_in": 7200,
                                             "scope": social.SCOPES["x"]})
        if url == social.X_ME:
            return httpx.Response(200, json={"data": {"id": "42", "username": "stratlab"}})
        if url == social.X_TWEETS:
            self.tweet += 1
            return httpx.Response(201, json={"data": {"id": str(self.tweet), "text": kw["json"]["text"]}})
        if url == social.LI_TOKEN:
            return httpx.Response(200, json={"access_token": "acc-LI-1", "expires_in": 5184000, "scope": "openid,profile,w_member_social"})
        if url == social.LI_ME:
            return httpx.Response(200, json={"sub": "abc123", "name": "The Owner"})
        if url == social.LI_POSTS:
            return httpx.Response(201, json={}, headers={"x-restli-id": "urn:li:share:777"})
        raise AssertionError(f"unexpected call {method} {url}")

    def posts(self, url=None):
        return [kw for m, u, kw in self.calls if u == (url or social.X_TWEETS)]


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    computed.reset_for_tests()
    theme_library._refreshing.clear()
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "X_CLIENT_ID", "the-x-client")
    monkeypatch.setattr(settings, "X_CLIENT_SECRET", "the-x-client-secret")
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_ID", "the-li-client")
    monkeypatch.setattr(settings, "LINKEDIN_CLIENT_SECRET", "the-li-client-secret")
    monkeypatch.setattr(settings, "PUBLIC_API_URL", "https://stratlab-production-ca25.up.railway.app")
    # every company with a market value at the 27 Nov close, as the screens' index has them (the page's largest companies)
    caps = {t: 1000.0 * (i + 1) for i, t in enumerate(["SHIPA", "SHIPB", "SHIPC", "SHIPD", "ELA", "ELB", "ELC", "AMA", "AMB",
                                                       "RA", "RB", "RC", "RD", "SA", "SB", "SC", "SD"])}
    monkeypatch.setattr(public_themes, "_index_caps", lambda region: dict(caps))
    monkeypatch.setattr(public_themes, "_index_days", lambda region: {k: "2026-11-27" for k in caps})
    net = FakeNet()
    monkeypatch.setattr(social, "HTTP", net)
    social.forget_preview()
    source_health.reset()
    built["net"] = net
    yield built
    social.forget_preview()
    built["close"]()


def keep(region, q, payload):
    assert theme_library.keep(region, q, json.loads(json.dumps(payload)))


def connect(c, net_name):
    url = c.post(f"/admin/social/{net_name}/connect", headers=ADMIN).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = c.get(f"/admin/social/{net_name}/callback", params={"code": "the-code", "state": state}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith(f"/admin/social?social={net_name}&result=connected")
    return url


# ---------- the post: lengths, banned words, link, rotation ----------
def view(**kw):
    v = {"region": "IN", "label": "Defence (India)", "slug": "defence", "name": "defence", "members": 9, "all": 11,
         "layers": [{"name": "Shipyards", "companies": [{"symbol": "SHIPA", "name": "Ship A Ltd", "cap": "₹19.00 lakh crore", "cap_v": 1900000.0},
                                                        {"symbol": "SHIPB", "name": "Ship B Ltd", "cap": "₹12,345 crore", "cap_v": 12345.0},
                                                        {"symbol": "SHIPC", "name": "Ship C Ltd", "cap": None, "cap_v": None},
                                                        {"symbol": "SHIPD", "name": "Ship D Ltd", "cap": "₹900 crore", "cap_v": 900.0}]},
                    {"name": "Electronics", "companies": [{"symbol": "ELA", "name": "Elec A Ltd", "cap": "₹40,000 crore", "cap_v": 40000.0},
                                                          {"symbol": "ELB", "name": "Elec B Ltd", "cap": None, "cap_v": None}]},
                    {"name": "Ammunition", "companies": [{"symbol": "AMA", "name": "Ammo A Ltd", "cap": None, "cap_v": None},
                                                         {"symbol": "AMB", "name": "Ammo B Ltd", "cap": None, "cap_v": None},
                                                         {"symbol": "AMC", "name": "Ammo C Ltd", "cap": None, "cap_v": None}]}],
         "day": "2026-11-20", "prices": "2026-11-27", "evidence": {"description_verified": 8, "industry_code_supported": 3}, "tally_at": "2026-11-21"}
    v.update(kw)
    return v


def test_x_post_is_a_thread_of_facts_with_dates_link_and_not_advice_each_part_within_280():
    got = social_post.build("x", view(), "https://stratlab.studio")
    parts = got["parts"]
    assert 3 <= len(parts) <= 5 and all(len(p) <= social_post.X_LIMIT for p in parts)
    assert parts[0].startswith("Defence in India: 9 listed companies in 3 layers (map made 20 Nov 2026).")
    assert "Facts only, not investment advice." in parts[0] and "https://stratlab.studio/themes/in/defence?from=x" in parts[0]
    assert parts[1] == "Largest layer: Shipyards, with 4 of the 9 companies."
    assert parts[2] == ("Largest by market value at the 27 Nov 2026 close: Ship A Ltd (₹19.00 lakh crore), Elec A Ltd (₹40,000 crore), "
                        "Ship B Ltd (₹12,345 crore).")
    assert parts[3].startswith("Membership check of 21 Nov 2026: 8 of the 11 companies")
    assert got["figures"] >= 4 and got["theme"] == {"region": "IN", "slug": "defence", "label": "Defence", "name": "defence"}
    for p in parts:
        assert social_post.lint(p) == [] and "%" not in p and "median" not in p.lower() and "margin" not in p.lower()


def test_linkedin_post_is_one_post_within_1300_with_every_fact_and_its_own_link():
    got = social_post.build("linkedin", view(), "https://stratlab.studio")
    assert len(got["parts"]) == 1
    text = got["parts"][0]
    assert len(text) <= social_post.LINKEDIN_LIMIT and text.endswith("Facts only, not investment advice.")
    assert "https://stratlab.studio/themes/in/defence?from=linkedin" in text and "?from=x" not in text
    for bit in ("9 listed companies in 3 layers (map made 20 Nov 2026)", "Its layers: Shipyards, Electronics, Ammunition.", "27 Nov 2026 close",
                "Membership check of 21 Nov 2026"):
        assert bit in text


def test_a_long_theme_still_fits_both_networks():
    many = [{"name": f"Layer number {i} with a long descriptive name", "companies": [
        {"symbol": f"S{i}{j}", "name": f"A Company With A Very Long Registered Name Number {i}{j} Limited", "cap": "₹1,23,456 crore",
         "cap_v": 123456.0 - i * 10 - j} for j in range(5)]} for i in range(30)]
    v = view(label="Electronics manufacturing services and components (Indian contract makers)", layers=many, members=150, all=150)
    for net, limit in (("x", social_post.X_LIMIT), ("linkedin", social_post.LINKEDIN_LIMIT)):
        got = social_post.build(net, v, "https://stratlab.studio")
        assert got and all(len(p) <= limit for p in got["parts"]), net
        assert "…" not in "".join(got["parts"])                       # a name is left out whole, never cut


def test_banned_words_block_a_post_and_a_fact_line_holding_one_is_left_out():
    for bad in ("Buy these shares", "a price target of 500", "We recommend it", "sell now", "strong upside", "Target: 900",
                "These look undervalued", "the top picks", "accumulate on dips"):
        assert social_post.lint(bad), bad
        with pytest.raises(social_post.PostRefused):
            social_post.check("x", [f"{bad}. Facts only, not investment advice. https://s/t?from=x"], "https://s/t?from=x")
    assert social_post.lint("Defence in India: 9 listed companies in 3 layers. Facts only, not investment advice.") == []
    # a company called "Target Corp" among the largest: its name is left out, the post still goes with the others
    v = view(layers=[{"name": "Stores", "companies": [{"symbol": "TGT", "name": "Target Corp", "cap": "$60.0B", "cap_v": 60000.0},
                                                     {"symbol": "WMT", "name": "Walmart Inc", "cap": "$700.0B", "cap_v": 700000.0}]},
                     {"name": "Clubs", "companies": [{"symbol": "COST", "name": "Costco Wholesale Corp", "cap": "$400.0B", "cap_v": 400000.0}]}],
             region="US", label="Retail (US)", slug="retail", members=3, all=3)
    got = social_post.build("x", v, "https://stratlab.studio")
    text = "\n".join(got["parts"])
    assert "Target" not in text and "Walmart Inc ($700.0B)" in text and got["parts"][0].startswith("Retail in the US")
    # a theme whose very name trips the lint gives no post at all
    assert social_post.build("x", view(label="Stocks to buy"), "https://stratlab.studio") is None


def test_check_refuses_a_post_without_its_link_or_not_advice_line_or_over_length():
    link = "https://stratlab.studio/themes/in/defence?from=x"
    with pytest.raises(social_post.PostRefused, match="no link"):
        social_post.check("x", ["Defence. Facts only, not investment advice."], link)
    with pytest.raises(social_post.PostRefused, match="not investment advice"):
        social_post.check("x", [f"Defence. {link}"], link)
    with pytest.raises(social_post.PostRefused, match="over 280"):
        social_post.check("x", [f"Facts only, not investment advice. {link} " + "x" * 280], link)
    social_post.check("linkedin", [f"Facts only, not investment advice. {link} " + "x" * 1000], link)


def test_rotation_takes_turns_by_market_and_never_repeats_a_theme_within_30_days():
    entries = [{"region": "IN", "slug": s} for s in ("a", "b", "c")] + [{"region": "US", "slug": s} for s in ("x", "y")]
    assert [social_post.theme_key(e) for e in social_post.order(entries)] == ["IN/a", "US/x", "IN/b", "US/y", "IN/c"]
    make = lambda e: {"theme": e}  # noqa: E731
    today = date(2026, 11, 28)
    assert social_post.pick("x", entries, [], today, make)["theme"]["slug"] == "a"
    rows = [{"net": "x", "day": "2026-11-27", "status": "posted", "theme": {"region": "IN", "slug": "a"}, "at": "2026-11-27T04:10:00+00:00"}]
    assert social_post.pick("x", entries, rows, today, make)["theme"]["slug"] == "x"            # the next in turn
    assert social_post.pick("linkedin", entries, rows, today, make)["theme"]["slug"] == "a"     # each network its own rotation
    # every theme posted in the last 30 days but one: that one; a theme 30 days back is free again
    rows = [{"net": "x", "day": (today - timedelta(days=i)).isoformat(), "status": "posted", "theme": {"region": e["region"], "slug": e["slug"]},
             "at": (today - timedelta(days=i)).isoformat()} for i, e in enumerate(entries[:4])]
    assert social_post.pick("x", entries, rows, today, make)["theme"]["slug"] == "y"
    old = [{**r, "day": "2026-10-29", "at": "2026-10-29"} for r in rows] + [{"net": "x", "day": "2026-11-28", "status": "posted", "theme": {"region": "US", "slug": "y"},
                                                          "at": "2026-11-28"}]
    assert social_post.pick("x", entries, old, today, make)["theme"]["slug"] == "c"
    # a failed post doesn't hold its theme back; one that may have gone out ("unknown") does
    assert social_post.recent([{"net": "x", "day": "2026-11-28", "status": "failed", "theme": {"region": "IN", "slug": "a"}}], "x", today) == set()
    assert social_post.recent([{"net": "x", "day": "2026-11-28", "status": "unknown", "theme": {"region": "IN", "slug": "a"}}], "x", today) == {"IN/a"}
    # themes that give no fit post are passed over
    assert social_post.pick("x", entries, [], today, lambda e: None if e["slug"] == "a" else {"theme": e})["theme"]["slug"] == "x"


# ---------- connecting: state, PKCE, tokens never shown ----------
def test_connect_x_uses_pkce_and_a_one_time_state_and_stores_the_tokens_sealed(w):
    c, net = w["client"], w["net"]
    url = connect(c, "x")
    q = parse_qs(urlparse(url).query)
    assert url.startswith(social.X_AUTHORIZE)
    assert q["scope"] == ["tweet.read tweet.write users.read offline.access"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["https://stratlab-production-ca25.up.railway.app/admin/social/x/callback"] and q["client_id"] == ["the-x-client"]
    m, u, kw = next(x for x in net.calls if x[1] == social.X_TOKEN)
    assert kw["data"]["grant_type"] == "authorization_code" and kw["data"]["code"] == "the-code" and kw["auth"] == ("the-x-client", "the-x-client-secret")
    assert social.challenge(kw["data"]["code_verifier"]) == q["code_challenge"][0]           # the verifier matches the challenge sent
    assert 43 <= len(kw["data"]["code_verifier"]) <= 128
    a = social.auth("x")
    assert a["account"] == {"id": "42", "name": "@stratlab"}
    raw = db.get_setting("social:auth:x")
    assert "acc-X-1" not in raw and "ref-X-1" not in raw                                     # sealed
    assert social.access_token("x")[0] == "acc-X-1"
    # the state answers once: the same callback again is refused and changes nothing
    r = c.get("/admin/social/x/callback", params={"code": "again", "state": q["state"][0]}, follow_redirects=False)
    assert r.headers["location"].endswith("result=expired")
    # Admin sees the account, never a token
    page = c.get("/admin/social", headers=ADMIN).json()
    text = json.dumps(page)
    assert all(s not in text for s in SECRETS)
    x = next(n for n in page["networks"] if n["key"] == "x")
    assert x["connected"] and x["account"] == "@stratlab" and x["enabled"] is False and x["callback"].endswith("/admin/social/x/callback")


def test_a_wrong_old_or_other_networks_state_is_refused(w, time_machine):
    time_machine.move_to(at("2026-11-28", "11:00"))
    c, net = w["client"], w["net"]
    r = c.get("/admin/social/x/callback", params={"code": "c", "state": "made-up"}, follow_redirects=False)
    assert r.headers["location"].endswith("social=x&result=expired")
    url = c.post("/admin/social/linkedin/connect", headers=ADMIN).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = c.get("/admin/social/x/callback", params={"code": "c", "state": state}, follow_redirects=False)       # LinkedIn's state at X's door
    assert r.headers["location"].endswith("result=expired")
    url = c.post("/admin/social/x/connect", headers=ADMIN).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    time_machine.shift(social.STATE_TTL + 5)
    r = c.get("/admin/social/x/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert r.headers["location"].endswith("result=expired")
    url = c.post("/admin/social/x/connect", headers=ADMIN).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = c.get("/admin/social/x/callback", params={"error": "access_denied", "state": state}, follow_redirects=False)
    assert r.headers["location"].endswith("result=denied")
    assert not [x for x in net.calls if x[1] == social.X_TOKEN] and social.auth("x") == {}


def test_only_an_admin_starts_a_connection_and_it_says_what_is_missing(w, monkeypatch):
    c = w["client"]
    assert c.post("/admin/social/x/connect", headers=PRO).status_code == 403
    assert c.get("/admin/social", headers=PRO).status_code == 403
    monkeypatch.setattr(settings, "X_CLIENT_SECRET", "")
    r = c.post("/admin/social/x/connect", headers=ADMIN)
    assert r.status_code == 400 and "X_CLIENT_ID and X_CLIENT_SECRET" in r.json()["detail"]["message"]
    monkeypatch.setattr(settings, "CONNECT_SECRET_KEY", "")
    r = c.post("/admin/social/linkedin/connect", headers=ADMIN)
    assert r.status_code == 400 and "CONNECT_SECRET_KEY" in r.json()["detail"]["message"]
    assert c.post("/admin/social/myspace/connect", headers=ADMIN).status_code == 404


def test_a_refused_code_exchange_says_why_in_admin_without_the_secret(w):
    c, net = w["client"], w["net"]
    net.answer("POST", social.X_TOKEN, httpx.Response(400, json={"error": "invalid_request", "error_description": "Value passed for the authorization code was invalid."}))
    url = c.post("/admin/social/x/connect", headers=ADMIN).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = c.get("/admin/social/x/callback", params={"code": "bad", "state": state}, follow_redirects=False)
    assert r.headers["location"].endswith("result=failed")
    x = next(n for n in c.get("/admin/social", headers=ADMIN).json()["networks"] if n["key"] == "x")
    assert not x["connected"] and "authorization code was invalid" in x["problem"] and "the-x-client-secret" not in x["problem"]


def test_linkedin_connects_with_openid_and_shows_when_its_sign_in_ends(w, time_machine):
    time_machine.move_to(at("2026-11-28", "11:00"))
    c, net = w["client"], w["net"]
    url = connect(c, "linkedin")
    q = parse_qs(urlparse(url).query)
    assert url.startswith(social.LI_AUTHORIZE) and q["scope"] == ["openid profile w_member_social"]
    assert q["redirect_uri"] == ["https://stratlab-production-ca25.up.railway.app/admin/social/linkedin/callback"]
    m, u, kw = next(x for x in net.calls if x[1] == social.LI_TOKEN)
    assert kw["data"]["client_secret"] == "the-li-client-secret" and kw["data"]["grant_type"] == "authorization_code"
    assert "acc-LI-1" not in db.get_setting("social:auth:linkedin")
    li = next(n for n in c.get("/admin/social", headers=ADMIN).json()["networks"] if n["key"] == "linkedin")
    assert li["account"] == "The Owner" and li["days_left"] in (59, 60) and li["expires_at"]
    # 54 days on: six days left, said on Overview for Needs your attention
    time_machine.shift(timedelta(days=54))
    row = next(x for x in c.get("/admin/overview?fresh=1", headers=ADMIN).json()["server"]["social"] if x["key"] == "linkedin")
    assert row["connected"] and row["days_left"] <= social.LINKEDIN_WARN_DAYS
    time_machine.shift(timedelta(days=7))
    with pytest.raises(social.SocialError, match="run out"):
        social.access_token("linkedin")


# ---------- tokens: X's refresh, rotated ----------
def test_an_x_token_near_its_end_is_renewed_and_the_new_refresh_token_replaces_the_old(w, time_machine):
    time_machine.move_to(at("2026-11-28", "11:00"))
    c, net = w["client"], w["net"]
    connect(c, "x")
    net.answer("POST", social.X_TOKEN, httpx.Response(200, json={"access_token": "acc-X-2", "refresh_token": "ref-X-2", "expires_in": 7200}))
    time_machine.shift(7200 - social.REFRESH_BEFORE + 1)
    assert social.access_token("x")[0] == "acc-X-2"
    m, u, kw = [x for x in net.calls if x[1] == social.X_TOKEN][-1]
    assert kw["data"] == {"refresh_token": "ref-X-1", "grant_type": "refresh_token", "client_id": "the-x-client"}
    raw = db.get_setting("social:auth:x")
    assert "ref-X-2" not in raw and "acc-X-2" not in raw
    from app.connect import vault
    assert vault.unseal(json.loads(raw)["refresh"]) == "ref-X-2"                            # rotated: the spent one is gone
    n = len(net.calls)
    assert social.access_token("x")[0] == "acc-X-2" and len(net.calls) == n                 # fresh: not renewed again


def test_a_turned_down_refresh_asks_the_owner_to_connect_again(w, time_machine):
    time_machine.move_to(at("2026-11-28", "11:00"))
    c, net = w["client"], w["net"]
    connect(c, "x")
    net.answer("POST", social.X_TOKEN, httpx.Response(400, json={"error": "invalid_request", "error_description": "Value passed for the token was invalid."}))
    time_machine.shift(7200)
    with pytest.raises(social.SocialError, match="Connect X again"):
        social.access_token("x")
    assert not social.connected("x")
    x = next(n for n in c.get("/admin/social", headers=ADMIN).json()["networks"] if n["key"] == "x")
    assert not x["connected"] and "Connect X again" in x["problem"]


# ---------- the daily job: once a day, retried once, never twice ----------
def on(c, *nets):
    for n in nets:
        connect(c, n)
        r = c.put(f"/admin/social/{n}", headers=ADMIN, json={"enabled": True})
        assert r.status_code == 200


def at(day: str, hm: str) -> datetime:
    h, m = (int(x) for x in hm.split(":"))
    d = date.fromisoformat(day)
    return datetime(d.year, d.month, d.day, h, m, tzinfo=IST)


def test_switches_start_off_and_turn_on_only_once_connected(w):
    c = w["client"]
    page = c.get("/admin/social", headers=ADMIN).json()
    assert [(n["key"], n["enabled"], n["connected"]) for n in page["networks"]] == [("x", False, False), ("linkedin", False, False)]
    r = c.put("/admin/social/x", headers=ADMIN, json={"enabled": True})
    assert r.status_code == 400 and "Connect X first" in r.json()["detail"]["message"]
    keep("IN", "defence", DEFENCE)
    assert social.job.tick(at("2026-11-30", "09:45")) == {}                                  # off: nothing posted
    assert w["net"].posts() == []


def test_the_daily_job_posts_once_a_day_at_its_time_and_never_twice(w, time_machine):
    c, net = w["client"], w["net"]
    keep("IN", "defence", DEFENCE)
    keep("IN", "railways", RAIL)
    on(c, "x", "linkedin")
    time_machine.move_to(at("2026-11-30", "09:00"))
    assert social.job.tick(at("2026-11-30", "09:00")) == {}                                  # before its time
    time_machine.move_to(at("2026-11-30", "09:41"))
    assert social.job.tick(at("2026-11-30", "09:41")) == {"x": "posted", "linkedin": "posted"}
    tweets = net.posts()
    assert 3 <= len(tweets) <= 5
    assert "reply" not in tweets[0]["json"] and all(t["json"]["reply"]["in_reply_to_tweet_id"] == str(101 + i) for i, t in enumerate(tweets[1:]))
    assert tweets[0]["headers"]["Authorization"] == "Bearer acc-X-1"
    li = net.posts(social.LI_POSTS)
    assert len(li) == 1 and li[0]["json"]["author"] == "urn:li:person:abc123" and li[0]["json"]["visibility"] == "PUBLIC"
    assert li[0]["headers"]["X-Restli-Protocol-Version"] == "2.0.0" and len(li[0]["headers"]["LinkedIn-Version"]) == 6
    assert "\\(" in li[0]["json"]["commentary"]                                              # little text: reserved characters escaped
    # again the same day, in the same window, or after a restart: nothing more
    for hm in ("09:46", "10:30", "13:00"):
        time_machine.move_to(at("2026-11-30", hm))
        assert social.job.tick(at("2026-11-30", hm)) == {}
    assert len(net.posts()) == len(tweets) and len(net.posts(social.LI_POSTS)) == 1
    log = c.get("/admin/social", headers=ADMIN).json()["posts"]
    assert [(p["net"], p["status"], p["kind"]) for p in log] == [("linkedin", "posted", "daily"), ("x", "posted", "daily")]
    xrow = next(p for p in log if p["net"] == "x")
    assert xrow["url"] == "https://x.com/stratlab/status/101" and xrow["theme"] in ("Defence", "Railways") and "?from=x" in xrow["link"]
    assert next(p for p in log if p["net"] == "linkedin")["url"] == "https://www.linkedin.com/feed/update/urn:li:share:777/"
    # the next day: the other theme (never the same one within 30 days); Sunday: nothing
    time_machine.move_to(at("2026-12-01", "09:41"))
    social.job.tick(at("2026-12-01", "09:41"))
    log = c.get("/admin/social", headers=ADMIN).json()["posts"]
    xs = [p["theme"] for p in log if p["net"] == "x"]
    assert len(xs) == 2 and xs[0] != xs[1]
    time_machine.move_to(at("2026-12-06", "09:41"))
    assert at("2026-12-06", "09:41").weekday() == 6 and social.job.tick(at("2026-12-06", "09:41")) == {}


def test_a_refused_post_is_tried_once_more_then_shown_in_admin_and_data_sources(w, time_machine):
    c, net = w["client"], w["net"]
    keep("IN", "defence", DEFENCE)
    on(c, "linkedin")
    refused = httpx.Response(422, json={"message": "Something about the content was refused."})
    net.answer("POST", social.LI_POSTS, refused, httpx.Response(500, json={"message": "Internal error."}))
    time_machine.move_to(at("2026-11-30", "09:41"))
    assert social.job.tick(at("2026-11-30", "09:41")) == {"linkedin": "failed"}
    time_machine.move_to(at("2026-11-30", "09:50"))
    assert social.job.tick(at("2026-11-30", "09:50")) == {}                                   # not before RETRY_AFTER
    time_machine.move_to(at("2026-11-30", "09:57"))
    assert social.job.tick(at("2026-11-30", "09:57")) == {"linkedin": "failed"}               # its one retry
    time_machine.move_to(at("2026-11-30", "10:30"))
    assert social.job.tick(at("2026-11-30", "10:30")) == {}                                   # no third try
    assert len(net.posts(social.LI_POSTS)) == 2
    row = c.get("/admin/social", headers=ADMIN).json()["posts"][0]
    assert row["status"] == "failed" and row["attempts"] == 2 and "LinkedIn answered 500" in row["error"]
    ov = c.get("/admin/overview?fresh=1", headers=ADMIN).json()["server"]
    li = next(x for x in ov["social"] if x["key"] == "linkedin")
    assert li["failed"]["status"] == "failed" and "500" in li["failed"]["error"]
    src = next(x for x in ov["sources"] if x["key"] == "linkedin")
    assert src["state"] == "bad" and src["owner"] and "Admin → Social" in src["action"]


def test_a_retry_after_a_thread_broke_halfway_carries_on_from_the_part_that_failed(w, time_machine):
    c, net = w["client"], w["net"]
    keep("IN", "defence", DEFENCE)
    on(c, "x")
    ok1 = httpx.Response(201, json={"data": {"id": "501"}})
    net.answer("POST", social.X_TWEETS, ok1, httpx.Response(503, json={"title": "Service Unavailable"}))
    time_machine.move_to(at("2026-11-30", "09:41"))
    assert social.job.tick(at("2026-11-30", "09:41")) == {"x": "failed"}
    time_machine.move_to(at("2026-11-30", "10:00"))
    assert social.job.tick(at("2026-11-30", "10:00")) == {"x": "posted"}
    tweets = net.posts()
    firsts = [t for t in tweets if "reply" not in t["json"]]
    assert len(firsts) == 1                                                                   # the first part went once, never again
    assert tweets[2]["json"]["reply"]["in_reply_to_tweet_id"] == "501"                        # the retry replied to it
    row = c.get("/admin/social", headers=ADMIN).json()["posts"][0]
    assert row["status"] == "posted" and row["url"] == "https://x.com/stratlab/status/501"


def test_a_send_cut_off_without_an_answer_is_unknown_and_never_sent_again(w, time_machine):
    c, net = w["client"], w["net"]
    keep("IN", "defence", DEFENCE)
    on(c, "linkedin")
    net.answer("POST", social.LI_POSTS, httpx.ReadTimeout("timed out"))
    time_machine.move_to(at("2026-11-30", "09:41"))
    assert social.job.tick(at("2026-11-30", "09:41")) == {"linkedin": "unknown"}
    time_machine.move_to(at("2026-11-30", "11:00"))
    assert social.job.tick(at("2026-11-30", "11:00")) == {}
    assert len(net.posts(social.LI_POSTS)) == 1
    row = c.get("/admin/social", headers=ADMIN).json()["posts"][0]
    assert row["status"] == "unknown" and "may have gone out" in row["error"]


def test_a_row_left_sending_by_a_stopped_server_is_never_sent_again(w, time_machine):
    c, net = w["client"], w["net"]
    keep("IN", "defence", DEFENCE)
    on(c, "x")
    time_machine.move_to(at("2026-11-30", "09:41"))
    post = social.next_post("x", date(2026, 11, 30), fresh=True)
    assert social.claim_daily("x", "2026-11-30", post)                                       # the server stopped right after claiming
    assert social.claim_daily("x", "2026-11-30", post) is None                                # a second claim of the day: refused
    time_machine.move_to(at("2026-11-30", "10:00"))
    assert social.job.tick(at("2026-11-30", "10:00")) == {}
    assert net.posts() == []
    assert social.rows()[-1]["status"] == "unknown"


def test_post_now_sends_the_next_post_at_once_and_a_double_click_is_one_post(w, time_machine):
    c, net = w["client"], w["net"]
    keep("IN", "defence", DEFENCE)
    assert c.post("/admin/social/x/post-now", headers=ADMIN).status_code == 400              # not connected
    connect(c, "x")
    r = c.post("/admin/social/x/post-now", headers=ADMIN)
    assert r.status_code == 200 and r.json()["post"]["status"] == "posted" and r.json()["post"]["kind"] == "manual"
    n = len(net.posts())
    r = c.post("/admin/social/x/post-now", headers=ADMIN)
    assert r.status_code == 400 and "last 10 minutes" in r.json()["detail"]["message"]
    assert len(net.posts()) == n
    assert c.post("/admin/social/x/post-now", headers=PRO).status_code == 403
    # the theme posted by hand counts for the 30 days: the next post is another theme, or none
    page = c.get("/admin/social", headers=ADMIN).json()
    x = next(m for m in page["networks"] if m["key"] == "x")
    assert x["next"] is None and x["next_note"].startswith("Every public theme (1) was posted on X in the last 30 days")


def test_the_admin_page_previews_the_next_post_per_network(w):
    c = w["client"]
    keep("IN", "defence", DEFENCE)
    page = c.get("/admin/social", headers=ADMIN).json()
    x, li = page["networks"]
    assert x["next"]["theme"] == "Defence" and x["next"]["parts"][0].startswith("Defence in India:") and "?from=x" in x["next"]["link"]
    assert li["next"]["parts"][0].endswith("Facts only, not investment advice.") and "?from=linkedin" in li["next"]["link"]
    assert x["vars"] == ["X_CLIENT_ID", "X_CLIENT_SECRET"] and li["vars"] == ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"]
    assert page["schedule"] == "9:40 AM India time, Monday to Saturday" and page["posts"] == []


def test_disconnect_forgets_the_sign_in_and_switches_off(w):
    c = w["client"]
    on(c, "x")
    r = c.post("/admin/social/x/disconnect", headers=ADMIN)
    x = next(n for n in r.json()["networks"] if n["key"] == "x")
    assert not x["connected"] and not x["enabled"] and db.get_setting("social:auth:x") is None


def test_the_real_http_never_leaves_the_machine_under_tests(monkeypatch):
    monkeypatch.delenv("SOCIAL_OFFLINE", raising=False)
    with pytest.raises(social.SocialError, match="no call to X or LinkedIn"):
        social._real_http("POST", social.X_TWEETS, json={"text": "hi"})


def test_errors_shown_in_admin_never_carry_a_token():
    long = "Bearer " + "a1B2" * 20
    assert "a1B2a1B2" not in social.clean(f"refused {long} at https://api.x.com/2/tweets?access_token=zzz")
    assert "access_token" not in social.clean("see https://api.x.com/2/tweets?access_token=zzz")


def test_linkedin_version_is_a_recent_published_month():
    assert social.li_version(date(2026, 11, 28)) == "202609"
    assert social.li_version(date(2026, 1, 5)) == "202511"
