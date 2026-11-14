"""Bet 3 MVP: public, shareable research. Share links to a deep dive or a theme (/r/<token>: a frozen, dated teaser with no user
data, noindex, turned off by its owner, counted by plan and throttled), public theme pages (/themes/<in|us>/<slug>: checked members
only, reported figures only, indexed only when rich enough, in the sitemap), and embeddable charts (/embed/...: the only addresses
another site may frame)."""
import json
import re
from pathlib import Path

import pytest

from app import computed, db, guard, public_themes, share, user_data
from app.intel import theme_library
from tests import world

PROVIDERS = re.compile(r"kite|zerodha|yahoo|screener|finnhub|edgar|mistral|gemini", re.I)
ADVICE = re.compile(r"\b(buy|sell|accumulate|upside|downside|target price|undervalued|overvalued|top picks?|beneficiar\w*)\b", re.I)
DERIVED = re.compile(r"\bmedian|\baverage\b|\brank|\bmargin|%", re.I)
VERCEL = json.loads((Path(__file__).resolve().parents[2] / "frontend" / "vercel.json").read_text())


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    computed.reset_for_tests()
    theme_library._refreshing.clear()
    share._made.clear()
    yield built
    built["close"]()


def h(token):
    return world.headers(token)


def co(t, name, verified=True, **kw):
    return {"ticker": t, "name": name, "what": "makes it" if verified else "", "verified": verified, **kw}


RICH = {"sector": "Defence", "generated_at": 5, "ai": None, "placements": {"checked": True},
        "summary": "Companies that design and build defence equipment. Buy the stock now for big upside. These are the top picks.",
        "value_chain": [
            {"layer": "Shipyards", "companies": [co("RELIANCE", "Reliance Industries Ltd"), co("SHIPA", "Ship A Ltd"), co("SHIPB", "Ship B Ltd"),
                                                  co("UNCHK", "Unchecked Ltd", verified=False, basis="added")]},
            {"layer": "Electronics", "companies": [co("ELA", "Elec A Ltd"), co("ELB", "Elec B Ltd"), co("ELC", "Elec C Ltd")]},
            {"layer": "Ammunition", "official": True, "basis": "industry",
             "companies": [co("AMA", "Ammo A Ltd", verified=False, base=True, basis="industry"), co("AMB", "Ammo B Ltd", verified=False, base=True, basis="industry")]},
            {"layer": "Only unchecked", "companies": [co("UNCHK2", "Also Unchecked Ltd", verified=False, basis="added")]},
        ], "sub_themes": []}
THIN = {"sector": "Rail", "generated_at": 6, "ai": None, "placements": {"checked": True}, "summary": "Rail makers.",
        "value_chain": [{"layer": "Coaches", "companies": [co("RA", "Rail A Ltd"), co("RB", "Rail B Ltd")]}], "sub_themes": []}


def keep(region="IN", q="defence", payload=RICH):
    assert theme_library.keep(region, q, json.loads(json.dumps(payload)))


def stored_snap(token):
    return json.loads(db.get_setting(f"rshare:{token}"))


# ---------- share links ----------
def test_deep_dive_link_is_a_frozen_dated_teaser_with_no_user_data(w):
    c = w["client"]
    from app import deepdive
    deepdive.store("RELIANCE", {"business": {"summary": "Reliance refines oil and runs retail stores. Buy the stock for upside.",
                                             "segments": [{"name": "Oil to chemicals", "share_pct": 55}, {"name": "Retail", "share_pct": 30}]},
                                "plans": {"capex": [{"what": "secret plan"}]}, "problems": [], "read": []})
    r = c.post("/research/share/deep/IN/RELIANCE", headers=h("pro-token"))
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert r.json()["url"] == f"https://stratlab.studio/r/{token}"
    snap = stored_snap(token)
    assert set(snap) <= share.SNAP_KEYS
    raw = json.dumps(snap)
    assert "u-pro" not in raw and "@" not in raw and "watchlist" not in raw.lower() and "secret plan" not in raw      # no user data, no plans
    page = c.get(f"/r/{token}")
    assert page.status_code == 200
    assert page.headers["x-robots-tag"] == "noindex, follow" and '<meta name="robots" content="noindex,follow">' in page.text
    assert 'property="og:title"' in page.text and "twitter:card" in page.text
    assert "See the full research on StratLab" in page.text and "/research/IN/RELIANCE/deep" in page.text
    assert "Reliance refines oil and runs retail stores." in page.text and "Oil to chemicals (55% of revenue)" in page.text
    assert "Shared from StratLab" in page.text and "a snapshot of this deep dive taken on" in page.text
    assert not PROVIDERS.search(page.text) and not ADVICE.search(page.text.split("<body>")[1])
    assert "<script" not in page.text.split("</head>")[1]
    # frozen: a later read of the company changes nothing on the link
    deepdive.store("RELIANCE", {"business": {"summary": "Something else entirely.", "segments": []}, "problems": [], "read": []})
    assert "Reliance refines oil" in c.get(f"/r/{token}").text and "Something else entirely" not in c.get(f"/r/{token}").text


def test_share_needs_sign_in_and_a_real_company_or_stored_theme(w):
    c = w["client"]
    assert c.post("/research/share/deep/IN/RELIANCE").status_code == 401
    assert c.post("/research/share/theme?q=defence&region=IN").status_code == 401
    assert c.get("/research/shares").status_code == 401
    for p in ("/research/share/deep/IN/NOPE", "/research/share/deep/XX/RELIANCE", "/research/share/deep/IN/%3Cscript%3E"):
        assert c.post(p, headers=h("pro-token")).status_code == 404, p
    assert c.post("/research/share/theme?q=defence&region=IN", headers=h("pro-token")).status_code == 404     # not in the library yet


def test_theme_link_shows_layers_and_counts_then_its_owner_turns_it_off(w):
    c = w["client"]
    keep()
    r = c.post("/research/share/theme?q=Defence&region=IN", headers=h("basic-token"))
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    page = c.get(f"/r/{token}").text
    assert "Layers of the theme" in page and "Shipyards" in page and "3 checked companies" in page
    assert "Ammunition" in page and "2 checked companies" in page
    assert "Only unchecked" not in page and "Unchecked Ltd" not in page          # an unconfirmed member is never public
    assert "Ship A Ltd" not in page                                            # a teaser: no member list on a share link
    assert not ADVICE.search(page.split("<body>")[1]) and "Companies that design and build defence equipment." in page
    assert "/themes/in/defence" in page
    # someone else can't turn it off; the owner can, and the link then answers the gone page, kept out of search
    assert c.delete(f"/research/shares/{token}", headers=h("pro-token")).status_code == 404
    assert c.get(f"/r/{token}").status_code == 200
    assert c.delete(f"/research/shares/{token}", headers=h("basic-token")).status_code == 200
    gone = c.get(f"/r/{token}")
    assert gone.status_code == 404 and gone.headers["x-robots-tag"] == "noindex" and "isn't available" in gone.text
    rows = c.get("/research/shares", headers=h("basic-token")).json()
    assert rows["links"][0]["token"] == token and rows["links"][0]["on"] is False and rows["used"] == 1 and rows["limit"] == 30


def test_free_plan_makes_one_link_a_month_and_says_which_plan_gives_more(w):
    c = w["client"]
    keep()
    assert c.post("/research/share/theme?q=defence&region=IN", headers=h("free-token")).status_code == 200
    r = c.post("/research/share/deep/IN/RELIANCE", headers=h("free-token"))
    assert r.status_code == 402 and r.json()["detail"]["code"] == "share_limit"
    msg = r.json()["detail"]["message"]
    assert "You've made 1 share link this month." in msg and "Basic gives 30 a month." in msg and "The count starts again on" in msg
    assert c.get("/research/shares", headers=h("free-token")).json()["limit"] == 1
    for _ in range(3):                                         # Pro has no limit
        assert c.post("/research/share/theme?q=defence&region=IN", headers=h("pro-token")).status_code == 200


def test_making_links_is_throttled_per_hour(w):
    c = w["client"]
    keep()
    for _ in range(share.PER_HOUR):
        assert c.post("/research/share/theme?q=defence&region=IN", headers=h("pro-token")).status_code == 200
    r = c.post("/research/share/theme?q=defence&region=IN", headers=h("pro-token"))
    assert r.status_code == 429 and r.json()["detail"]["code"] == "slow_down"


def test_tokens_cant_be_guessed_and_odd_ones_are_refused(w):
    tokens = {share.new_token() for _ in range(5000)}
    assert len(tokens) == 5000
    assert all(len(t) == 24 and share.TOKEN.match(t) for t in tokens)
    assert share.TOKEN_BYTES * 8 >= 128                                    # at least 128 random bits
    for bad in ("", "abc", "../../etc", "a" * 40, "aaaaaaaaaaaaaaaaaaaaaa%00", "card:xyz", "share:aaaaaaaaaaaaaaaaaaaa"):
        assert share.load(bad) is None
    c = w["client"]
    for bad in ("abc", "a" * 24, "....................."):
        assert c.get(f"/r/{bad}").status_code == 404


def test_public_words_drop_advice_and_vendor_names():
    assert share.public_words("It makes cars. Buy the stock now. Top picks for 2027 below.") == "It makes cars."
    assert share.public_words("Prices from Yahoo Finance and Screener.in.") == "Prices from the market data source and the fundamentals source."
    assert share.public_words("A long sentence about refining oil and chemicals", 20).endswith("…")


def test_the_owners_erase_takes_their_links_down(w):
    c = w["client"]
    keep()
    token = c.post("/research/share/theme?q=defence&region=IN", headers=h("pro-token")).json()["token"]
    user_data.erase("u-pro")
    assert c.get(f"/r/{token}").status_code == 404 and db.get_setting("rshares:user:u-pro") is None


# ---------- public theme pages ----------
def test_public_theme_page_lists_checked_members_with_reported_figures_only(w, monkeypatch):
    c = w["client"]
    keep()
    monkeypatch.setattr(public_themes, "_index_caps", lambda region: {"RELIANCE": 1900000.0, "SHIPA": 12345.0})
    r = c.get("/themes/in/defence")
    assert r.status_code == 200 and "x-robots-tag" not in r.headers
    t = r.text
    assert '<meta name="robots" content="index,follow">' in t and '<link rel="canonical" href="https://stratlab.studio/themes/in/defence">' in t
    assert '"@type": "Dataset"' in t and '"isAccessibleForFree": true' in t and "BreadcrumbList" in t
    for name in ("Ship A Ltd", "Elec C Ltd", "Ammo B Ltd", "Reliance Industries Ltd"):
        assert name in t
    assert "Unchecked Ltd" not in t and "Only unchecked" not in t
    assert '<a href="/stocks/in/RELIANCE">Reliance Industries Ltd</a>' in t                 # members link to their public pages
    assert "Market value ₹19.00 lakh crore" in t and "Market value ₹12,345 crore" in t
    layers = "".join(re.findall(r"<section class=\"card\" data-layer>.*?</section>", t, re.S))
    assert layers and not DERIVED.search(layers)                                             # no figure StratLab works out
    assert "median" not in t.lower()
    assert "See the full theme on StratLab" in t and "/research/themes?q=defence&amp;region=IN" in t
    assert "Companies that design and build defence equipment." in t and not ADVICE.search(t.split("<body>")[1])
    assert not PROVIDERS.search(t) and "How this page is made" in t and "Download" not in t and "<table" not in t
    assert c.head("/themes/in/defence").status_code == 200


def test_revenue_shows_only_as_the_company_reported_it(w, monkeypatch):
    keep()
    from app.intel import theme_routes
    monkeypatch.setattr(theme_routes, "dive_key", lambda r, theme, m: ["IN", "defence-dive"])
    computed.put(theme_library.DIVE, ["IN", "defence-dive"], {"dive": {"layers": [{"companies": [
        {"symbol": "SHIPA", "revenue": 5000.0, "year": "Mar 2026", "unit": "₹ crore", "fx": None},
        {"symbol": "SHIPB", "revenue": 900.0, "year": "Dec 2025", "unit": "₹ crore", "fx": {"rate": 83.0, "at": "2026-01-01"}}]}]}},
        label="Defence", region="IN")
    entry, _ = public_themes.find("IN", "defence")
    v = public_themes.view(entry, public_themes.payload(entry))
    rows = {x["symbol"]: x for layer in v["layers"] for x in layer["companies"]}
    assert rows["SHIPA"]["revenue"] == "₹5,000 crore" and rows["SHIPA"]["year"] == "Mar 2026"
    assert rows["SHIPB"]["revenue"] is None                      # turned from another currency: StratLab's figure, left out


def test_thin_themes_are_noindex_and_only_rich_ones_are_in_the_sitemap(w):
    c = w["client"]
    keep()
    keep("IN", "rail", THIN)
    thin = c.get("/themes/in/rail")
    assert thin.status_code == 200 and thin.headers["x-robots-tag"] == "noindex, follow" and 'content="noindex,follow"' in thin.text
    assert "canonical" not in thin.text
    names = c.get("/sitemap.xml").text
    assert "https://stratlab.studio/sitemaps/themes.xml" in names
    xml = c.get("/sitemaps/themes.xml").text
    assert "<loc>https://stratlab.studio/themes/in/defence</loc><lastmod>1970-01-01</lastmod>" not in xml        # the entry's own day
    assert re.search(r"<loc>https://stratlab.studio/themes/in/defence</loc><lastmod>\d{4}-\d\d-\d\d</lastmod>", xml)
    assert "/themes/in/rail" not in xml and "<loc>https://stratlab.studio/themes</loc>" in xml
    directory = c.get("/themes/in").text
    assert '<a href="/themes/in/defence">Defence</a>' in directory and '<a href="/themes/in/rail">Rail</a>' in directory


def test_one_page_per_theme_an_alias_answers_301_and_unknowns_404(w):
    c = w["client"]
    keep("IN", "defence")
    keep("IN", "defense sector")                      # another way of writing it: the same stored theme, an alias
    entry, _ = public_themes.find("IN", "defence")
    assert entry is not None
    for bad in ("/themes/in/nope", "/themes/xx/defence", "/themes/in/%3Cscript%3E", "/themes/in/" + "a" * 90):
        r = c.get(bad, follow_redirects=False)
        assert r.status_code == 404 and r.headers["x-robots-tag"] == "noindex", bad
    meta = computed.index(theme_library.KIND)["entries"][entry["hk"]]["meta"]
    computed.touch(theme_library.KIND, entry["hk"], aliases=sorted(set(meta["aliases"]) | {"defence equipment"}))
    r = c.get("/themes/in/defence-equipment", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/themes/in/defence"


# ---------- embeds and the frame headers ----------
def frame(resp):
    return resp.headers.get("x-frame-options"), resp.headers.get("content-security-policy", "")


def test_only_embeds_may_be_framed_by_another_site(w):
    c = w["client"]
    keep()
    token = c.post("/research/share/theme?q=defence&region=IN", headers=h("pro-token")).json()["token"]
    for path in ("/embed/theme/in/defence", "/embed/price/in/RELIANCE", "/embed/price/RELIANCE"):
        r = c.get(path)
        assert r.status_code == 200, path
        xfo, csp = frame(r)
        assert xfo is None and "frame-ancestors *" in csp and "script-src" not in csp, path
    for path in ("/themes", "/themes/in/defence", f"/r/{token}", "/stocks/in/RELIANCE", "/research/shares", "/sitemap.xml"):
        r = c.get(path, headers=h("pro-token"))
        xfo, csp = frame(r)
        assert xfo == "DENY", path
        assert "frame-ancestors *" not in csp, path
    assert dict(guard.security_headers("/embed/x", True))[b"content-security-policy"].endswith(b"frame-ancestors *")
    assert dict(guard.security_headers("/embedded", True))[b"x-frame-options"] == b"DENY"      # only the /embed/ folder


def vercel_headers(path):
    out = {}
    for rule in VERCEL["headers"]:
        src = rule["source"]
        if ":" in src:
            continue                                  # the :path* rules set caching only
        if re.fullmatch(src, path):
            out.update({x["key"]: x["value"] for x in rule["headers"]})
    return out


def test_the_host_relaxes_framing_for_embeds_only():
    for p in ("/embed/price/in/TCS", "/embed/theme/us/semiconductor"):
        got = vercel_headers(p)
        assert "X-Frame-Options" not in got and got["Content-Security-Policy"].endswith("frame-ancestors *"), p
        assert got["Strict-Transport-Security"] and got["X-Content-Type-Options"] == "nosniff"
    for p in ("/", "/research/IN/TCS", "/themes/in/defence", "/r/abc", "/embedx", "/account"):
        got = vercel_headers(p)
        assert got["X-Frame-Options"] == "DENY" and "frame-ancestors 'none'" in got["Content-Security-Policy"], p
    rewrites = {r["source"]: r["destination"] for r in VERCEL["rewrites"]}
    for src in ("/r/:token", "/themes/:path*", "/embed/:path*"):
        assert rewrites[src].endswith(src.replace("/:token", "/:token")), src
    assert VERCEL["rewrites"][-1]["destination"] == "/index.html"


def test_embeds_carry_source_date_and_backlink_and_no_vendor(w):
    c = w["client"]
    keep()
    t = c.get("/embed/theme/in/defence").text
    assert "<svg" in t and 'role="img"' in t and "Shipyards 3" in t and "Ammunition 2" in t
    assert "Source: company filings" in t and "As of " in t and 'href="https://stratlab.studio/themes/in/defence" target="_blank"' in t
    assert 'content="noindex,follow"' in t and "<script" not in t and not PROVIDERS.search(t)
    p = c.get("/embed/price/in/RELIANCE").text
    assert "<polyline" in p and "Source: exchange closing prices" in p and "As of " in p and "https://stratlab.studio/stocks/in/RELIANCE" in p
    assert not PROVIDERS.search(p)
    assert c.get("/embed/price/in/NOPE").status_code == 404 and c.get("/embed/theme/in/nope").status_code == 404


def test_a_rules_bump_keeps_a_public_theme_page_until_the_theme_is_read_again(w, monkeypatch):
    """LIVE8A-001: a rules bump took 15 of 21 public theme pages to 404 until each theme was read again; the newest stored entry stands meanwhile."""
    from app.intel import theme_base
    c = w["client"]
    keep("IN", "defence")
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)      # a release with new rules; the theme not read again yet
    assert c.get("/themes/in/defence", follow_redirects=False).status_code == 200
    assert "/themes/in/defence" in c.get("/themes/in").text
    assert [e["slug"] for e in public_themes.entries("IN")] == ["defence"]                 # one page per theme, not one per rules
    keep("IN", "defence")                                                                  # read again under the new rules
    entries = public_themes.entries("IN")
    meta = computed.index(theme_library.KIND)["entries"][entries[0]["hk"]]["meta"]
    assert len(entries) == 1 and meta["rules"] == theme_base.RULES                         # the new entry wins
