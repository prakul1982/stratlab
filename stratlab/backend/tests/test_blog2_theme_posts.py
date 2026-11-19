"""blog2 (the owner, 16 Nov: "fix all the blog shit and old deck ... make it all updated ... keep posting blog of the 9+ decks"): the theme
posts committed with a release (app/blog_themes/*.json, each a theme's live read), what a theme post says by its deck's rules, how a release
stores and publishes them, the script that drafts and checks one, and the public pages that point at old or missing things."""
import copy
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app import blog, blog_pages, blog_research as BR, computed, sample_deck
from app.intel.theme_data import finding_first
from tests import world as W

SEEDS = Path(BR.__file__).with_name("blog_themes")
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
VENDORS = ("yahoo", "screener", "finnhub", "zerodha", "kite connect", "google news", "tickertape", "trendlyne")
# the owner's outside review of the live R59 decks: the themes whose deck scored 9 or more, each with a post (lanes19/owner-r59-review.md)
NINE_PLUS = {"theme-it-services-margins-in", "theme-defence-margins-in", "theme-pharma-margins-in", "theme-metals-and-mining-margins-in",
             "theme-real-estate-margins-in", "theme-chemicals-margins-in", "theme-automotive-margins-in", "theme-utilities-margins-in",
             "theme-capital-goods-margins-in", "theme-hospitals-margins-in", "theme-medical-devices-margins-us", "theme-private-banks-margins-in",
             "theme-cybersecurity-margins-us", "theme-semiconductors-margins-us", "theme-telecom-margins-in", "theme-public-sector-banks-margins-in"}
ADVICE = re.compile(r"\b(buy|sell|hold|accumulate|avoid|cheap|expensive|overpriced|underpriced|overvalued|undervalued|recommend\w*|target price)\b", re.I)


def committed() -> dict[str, dict]:
    return {BR.theme_slug(s): s for s in (json.loads(p.read_text()) for p in sorted(SEEDS.glob("*.json")))}


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    monkeypatch.setattr(BR, "SEED_DIR", SEEDS)                    # the committed posts, as a release has them
    yield world
    world["close"]()


def page_text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


# ---------- the committed posts ----------
def test_every_nine_plus_deck_has_a_committed_post_and_each_file_is_named_for_its_address():
    got = committed()
    assert set(got) == NINE_PLUS
    for p in SEEDS.glob("*.json"):
        src = json.loads(p.read_text())
        assert p.stem == BR.theme_slug(src) and src["v"] == BR.THEME_SRC_V and src["read_on"] and src["stamp"]


@pytest.mark.parametrize("slug", sorted(NINE_PLUS))
def test_every_committed_post_passes_its_checks_and_every_figure_it_prints_is_in_its_source(slug):
    src = committed()[slug]
    post = BR.theme_post_from(src)
    assert BR.theme_post_problems(src, post) == []
    assert BR.figures_not_in_source(src, post) == []
    text = f"{post['title']} {post['summary']} {blog.plain_text(post['blocks'])}"
    assert not ADVICE.search(text) and not any(v in text.lower() for v in VENDORS)
    # the deck's rules: every median of fewer than 3 companies is "–" with its count, never a number; a highest and a lowest only as its chain says
    table = next(b for b in post["blocks"] if b["t"] == "table")
    for row, r in zip(table["rows"], [r for r in src["rows"] if r.get("n")]):
        for cell in row[3:]:
            m = re.match(r"^[−\d.]+%? \((\d+)(?: of \d+)?\)$|^[−\d.]+x? \((\d+) of \d+\)$", cell)
            if m:
                assert int(m.group(1) or m.group(2)) >= 3, (slug, row)
    chain = src["chain"]
    tiles = [t["l"] for t in next(b for b in post["blocks"] if b["t"] == "stats")["items"]]
    assert any("highest" in t for t in tiles) == bool(chain.get("highest") and chain.get("lowest"))
    if chain.get("line"):
        # r66e (LIVE12A-009, updated on purpose): the excerpt is the chain's line with its finding first (theme_data.finding_first)
        assert post["summary"].startswith(finding_first(chain["line"])[:60].replace(".0 points", " points")[:40])
    links = json.dumps(post["blocks"])
    assert src["page"].startswith("/themes/") and f'"href": "{src["page"]}"' in links and '"href": "/research/themes?q=' in links


def test_a_post_prints_the_tampered_figure_as_one_its_source_does_not_hold():
    src = copy.deepcopy(committed()["theme-cybersecurity-margins-us"])
    post = BR.theme_post_from(src)
    post["blocks"][0]["text"] += " Median EBITDA margin 77.7%."
    assert BR.figures_not_in_source(src, post) == ["77.7"]
    assert "figures its source doesn't hold: 77.7" in BR.theme_post_problems(src, post)[0]


def test_the_cybersecurity_post_follows_its_deck_where_the_live_r59_post_did_not():
    """The live post (16 Nov) said "highest layer margin 31.4%, lowest 0.5%" and printed Endpoint −26.6% and Identity −1.8%, medians of one and two
    companies; its deck ranks no layer (none has 5 companies with the figure) and prints those cells "– (1 of 2)" and "– (2)"."""
    src = committed()["theme-cybersecurity-margins-us"]
    post = BR.theme_post_from(src)
    table = next(b for b in post["blocks"] if b["t"] == "table")
    rows = {r[0]: r[1:] for r in table["rows"]}
    assert table["head"] == ["Layer", "Companies", "Revenue", "EBITDA margin", "Net margin", "ROCE"]
    assert rows["Identity and access software"] == ["2 of 3", "$3.99 bn", "– (2)", "– (1 of 2)", "– (1 of 2)"]
    assert rows["Endpoint and detection platforms"] == ["2", "$5.81 bn", "– (1 of 2)", "– (2)", "– (1 of 2)"]
    assert rows["Network security appliances and subscriptions"] == ["3", "$21 bn", "31.4%", "– (2 of 3)", "– (2 of 3)"]
    assert rows["Vulnerability and data security software"][-1] == "19.6% (3 of 5)"
    text = blog.plain_text(post["blocks"])
    assert "−26.6%" not in text and "−1.8%" not in text and "highest" not in text
    assert "A layer is ranked only on a median of at least 5 companies with the figure" in text
    assert "16 listed US companies are in the cybersecurity theme" in text and "15 core members with figures" in text
    who = {b["title"]: blog.plain_text(b["blocks"]) for b in post["blocks"] if b["t"] == "fold"}
    assert re.search(r"Cyberark Software Ltd ?: membership not checked yet; listed, in no figure", who["Identity and access software"])


def test_a_bank_theme_post_reads_its_layers_on_lenders_measures_and_says_its_chains_own_comparison():
    src = committed()["theme-private-banks-margins-in"]
    post = BR.theme_post_from(src)
    assert post["title"] == "Private banks: where the return on equity sits along the chain"
    # r66e (LIVE12A-009, updated on purpose): the excerpt leads with the finding, the layers it ranks said after it
    assert post["summary"].startswith("Median return on equity is highest in Large deposit-led universal banks (13.6%)")
    assert "among the 2 layers with at least 5 companies with the figure" in post["summary"]
    table = next(b for b in post["blocks"] if b["t"] == "table")
    assert table["head"] == ["Layer", "Companies", "Revenue", "Net margin", "ROE", "NII / assets", "Gross NPA", "P/B"]
    assert table["rows"][0] == ["Large deposit-led universal banks", "5", "₹7.75 lakh cr", "27.6%", "13.6%", "3.5%", "– (1 of 5)", "2.1x"]
    chart = next(b for b in post["blocks"] if b["t"] == "hbar")
    assert [r["label"] for r in chart["rows"]][1] == "Regional and mid-sized banks (larger) (5, not ranked)"


# ---------- a release stores and publishes them ----------
def test_the_first_blog_check_after_a_deploy_stores_and_publishes_every_committed_post_once(w):
    now = datetime(2026, 11, 17, 4, tzinfo=timezone.utc)
    # a draft the site stored hidden days before (as live: theme-it-services-margins-in, 8 Nov) and a post from a later read
    it = {**BR.theme_post_from(committed()["theme-it-services-margins-in"], datetime(2026, 11, 8, tzinfo=timezone.utc)), "published": False}
    blog.upsert_research(it, datetime(2026, 11, 8, tzinfo=timezone.utc))
    later = {**committed()["theme-telecom-margins-in"], "read_on": "2026-11-20"}
    later["rows"] = [dict(r) for r in later["rows"]]
    later["rows"][0]["revenue"] = later["rows"][0]["revenue"] + 1000
    blog.upsert_research({**BR.theme_post_from(later), "published": False}, now)
    made, problems = BR.seed_theme_posts(now)
    assert problems == [] and {m["slug"] for m in made} == NINE_PLUS
    for slug in NINE_PLUS:
        got = blog.get(slug)
        assert got["published"] is True and got["indexable"] is True and got["body"]["src"]["v"] == BR.THEME_SRC_V
    assert blog.get("theme-it-services-margins-in")["published_at"].startswith("2026-11-17")          # dated the day it went up
    assert blog.get("theme-telecom-margins-in")["body"]["src"]["read_on"] == "2026-11-20"                # the later read's figures kept
    # once per committed read: a post hidden in Admin afterwards stays hidden, and nothing is written again
    blog.set_published("theme-defence-margins-in", False, now)
    assert BR.seed_theme_posts(now) == ([], [])
    assert blog.get("theme-defence-margins-in")["published"] is False
    rows, total = blog.listing("research")
    assert NINE_PLUS - {"theme-defence-margins-in"} <= {r["slug"] for r in rows} | set()


def test_the_newsletter_clock_stores_the_committed_posts_without_a_version_bump(w, monkeypatch):
    from app.newsletter import job
    monkeypatch.setattr(BR, "GEN_KEY", BR.GEN_KEY)                # nothing else changes: the clock looks at what is committed too
    j = job.Job()
    j.last["blog-gen"] = None
    j.blog_versions(datetime(2026, 11, 17, 4, tzinfo=timezone.utc), blog, BR)
    assert all(blog.get(s) and blog.get(s)["published"] for s in NINE_PLUS)
    assert BR.seed_mark() and j.last.get("blog-gen") and j.last["blog-gen"][-1] == BR.seed_mark()


def test_a_committed_post_whose_checks_fail_is_not_published(w, monkeypatch, tmp_path):
    src = copy.deepcopy(committed()["theme-defence-margins-in"])
    src["rows"] = src["rows"][:1]                                   # one layer: nothing to compare
    (tmp_path / "theme-defence-margins-in.json").write_text(json.dumps(src))
    monkeypatch.setattr(BR, "SEED_DIR", tmp_path)
    made, problems = BR.seed_theme_posts()
    assert made == [] and problems and problems[0].startswith("theme-defence-margins-in: not published")
    assert blog.get("theme-defence-margins-in") is None


def test_every_committed_post_is_a_page_on_desktop_and_phone_and_in_the_sitemap_and_feed(w):
    BR.seed_theme_posts()
    c = w["client"]
    for slug in sorted(NINE_PLUS):
        r = c.get(f"/blog/{slug}")
        assert r.status_code == 200, slug
        html = r.text
        assert html.count("<h1") == 1 and '<link rel="canonical" href="https://stratlab.studio/blog/' + slug + '"' in html
        assert '"@type": "Article"' in html or '"@type":"Article"' in html
        assert 'name="robots" content="index,follow"' in html
        text = page_text(html)
        assert "Facts, not advice" in text
        # the page's own lines that it is not advice or a recommendation (the post's facts line and the site's footer)
        bare = re.sub(r"[^.]*\b(?:not investment advice|nothing here is investment advice)[^.]*\.", " ", text.replace(blog_pages.FACTS, ""))
        assert not ADVICE.search(bare) and not any(v in text.lower() for v in VENDORS), (slug, ADVICE.search(bare))
        assert '<div class="btbl' in html and "<details" in html
    sm = c.get("/sitemaps/blog.xml")
    locs = {u.find(NS + "loc").text for u in ET.fromstring(sm.content)}
    assert {f"https://stratlab.studio/blog/{s}" for s in NINE_PLUS} <= locs
    feed = c.get("/blog/feed.xml").text
    assert all(f"/blog/{s}" in feed for s in sorted(NINE_PLUS)[:10]) or feed.count("/blog/theme-") >= 10


def test_a_kept_post_of_before_takes_the_decks_counts_at_the_themes_next_read():
    old = {"v": 1, "theme": "x", "rows": [{"layer": "A", "n": 3, "ebitda": 1.0, "companies": []}], "members": 3}
    new = {**old, "v": 2}
    assert BR.figures_moved(old, new) and not BR.figures_moved(new, dict(new))
    moved = copy.deepcopy(new)
    moved["rows"][0]["ebitda_n"] = 2
    assert BR.figures_moved(new, moved)                            # how many companies a median is of is part of the figures


# ---------- the script ----------
def test_the_script_checks_every_committed_post_and_drafts_one_from_a_saved_dive(tmp_path, monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("theme_post", Path(__file__).resolve().parents[1] / "scripts" / "theme_post.py")
    tp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tp)
    monkeypatch.setattr(BR, "SEED_DIR", SEEDS)
    assert tp.main(["check"]) == 0
    assert capsys.readouterr().out.count(": passed") == len(NINE_PLUS)
    # a dive saved from the live site: the script writes the post's figures only when its checks pass
    src = committed()["theme-defence-margins-in"]
    dive = {"sector": src["sector"], "unit": src["unit"], "basis": src["basis"], "members": src["members"], "as_of": src["as_of"], "notable": [],
            "placements": {"total": src["total"]}, "checks": {}, "chain": {**src["chain"], "rows": [{k: v for k, v in r.items() if k not in ("companies", "words")} for r in src["rows"]]},
            "layers": [{"layer": r["layer"], "companies": [{"symbol": c["symbol"], "name": c["name"], "what": c["what"], "status": "core",
                                                             "revenue": 1.0, "year": "Mar 2026"} for c in r["companies"]]} for r in src["rows"]]}
    (tmp_path / "d.json").write_text(json.dumps({"data": dive}))
    monkeypatch.setattr(BR, "SEED_DIR", tmp_path / "out")
    assert tp.main(["draft", str(tmp_path / "d.json"), "--theme", "Defence", "--region", "IN", "--write"]) == 0
    out = capsys.readouterr().out
    assert "checks: passed" in out and "| EBITDA margin |" in out
    written = json.loads((tmp_path / "out" / "theme-defence-margins-in.json").read_text())
    assert [r["layer"] for r in written["rows"]] == [r["layer"] for r in src["rows"]]
    one = {**dive, "chain": {"rows": dive["chain"]["rows"][:1]}, "layers": dive["layers"][:1]}
    (tmp_path / "one.json").write_text(json.dumps(one))
    assert tp.main(["draft", str(tmp_path / "one.json"), "--theme", "One", "--region", "IN", "--write"]) == 1
    assert not (tmp_path / "out" / "theme-one-margins-in.json").exists()


# ---------- public pages that pointed at old or missing things ----------
def test_a_theme_page_written_as_people_write_it_answers_301_to_its_page(monkeypatch):
    from app import public_themes as P
    rows = [{"region": "IN", "name": "it service", "label": "IT services", "slug": "it-service", "aliases": [], "at": 1, "hk": "h1"},
            {"region": "IN", "name": "public bank", "label": "Public sector banks", "slug": "public-bank", "aliases": [], "at": 1, "hk": "h2"}]
    monkeypatch.setattr(P, "entries", lambda region=None: [r for r in rows if not region or r["region"] == region])
    assert P.find("IN", "it-service") == (rows[0], None)
    assert P.find("IN", "it-services") == (None, "it-service")
    assert P.find("IN", "public-sector-banks") == (None, "public-bank")
    assert P.find("IN", "railways") == (None, None)
    from fastapi.testclient import TestClient
    from app import main
    r = TestClient(main.app).get("/themes/in/it-services", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/themes/in/it-service"


def test_a_theme_posts_link_is_its_live_theme_page():
    for slug, src in committed().items():
        assert src["page"] == BR.theme_page_path(src["theme"], src["region"]), slug
    assert BR.theme_page_path("Medical devices", "US") == "/themes/us/medical-device"
    assert BR.theme_page_path("Public sector banks", "IN") == "/themes/in/public-bank"


def test_the_sample_deck_is_never_a_deck_an_older_release_made():
    now_v = computed.versions("deck:theme")
    old = {"id": "old", "label": "India defence (PDF, 2026-11-16)", "region": "IN", "meta": {"versions": [v - 1 if isinstance(v, int) else v for v in now_v]}}
    unrecorded = {"id": "u", "label": "India defence (PDF, 2026-11-15)", "region": "IN", "meta": {}}
    cur = {"id": "c", "label": "Railways (PDF, 2026-11-14)", "region": "IN", "meta": {"versions": now_v}}
    assert sample_deck.pick([old, unrecorded, cur])["id"] == "c"
    assert sample_deck.pick([old, unrecorded]) is None


def test_a_name_with_its_own_description_in_brackets_is_no_headline():
    assert not BR.headline_like("Utilities (Indian power, gas and water-linked infrastructure)")
    assert BR.headline_like("Why PSU banks rallied (today)") and BR.headline_like("Nifty hits record high")
