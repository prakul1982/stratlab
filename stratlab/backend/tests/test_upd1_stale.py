"""Lane upd1: nothing stale served after a rules or wording change, and Admin's figures from one source each.

- A kept theme deck is keyed by every version it is made from (computed.VERSIONS), so a deploy that changes only the dive's sentences or
  the sector figures' rules never serves the day's deck made before it.
- Admin -> Library says which kept theme reads and decks are no longer served (older rules, an earlier day's file), and dates its entries
  by the India day.
- A stored theme blog post whose figures were worked out under older theme rules takes the figures of the theme's next dive (or is worked
  out again from the library's read after a deploy), keeping its address and whether it is published; Admin's blog list says which posts
  are stale and doesn't count a post the site answers "not found" for.
- Overview's "Revenue, last 30 days" sums 30 India days, and Users' "Last active" counts what Overview's "Active users" counts."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app import admin, blog, blog_pages, blog_research as BR, computed, db, invoices, library_admin, main
from app.intel import sector_metrics, theme_base, theme_data
from app.kite_service import IST


class Store(dict):
    """app_settings in memory: get, set, update (atomic here) and delete."""

    def update_setting(self, k, fn):
        new = fn(self.get(k))
        if new is None:
            return self.get(k)
        if new is db.REMOVE:
            self.pop(k, None)
            return None
        self[k] = new
        return new


@pytest.fixture
def store(monkeypatch):
    s = Store()
    monkeypatch.setattr(db, "get_setting", lambda k: s.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: s.__setitem__(k, v))
    monkeypatch.setattr(db, "update_setting", s.update_setting)
    monkeypatch.setattr(db, "delete_setting", lambda k: s.pop(k, None))
    computed.reset_for_tests()
    return s


# ---------- the kept theme deck ----------
def test_a_kept_deck_is_not_served_after_the_dive_sentences_or_the_sector_rules_change(store, monkeypatch):
    key = ["IN", "defence", "pdf", "2026-11-12", 1, False, (False, False), theme_base.RULES, 49, 0]
    computed.put("deck:theme", key, "Zm9v", label="Defence (PDF, 2026-11-12)", region="IN")
    assert computed.get("deck:theme", key)["value"] == "Zm9v"                       # the same code: served
    monkeypatch.setattr(theme_data, "DIVE_TEXT", theme_data.DIVE_TEXT + 1)
    assert computed.get("deck:theme", key) is None                                 # the dive's sentences changed: made again
    monkeypatch.setattr(theme_data, "DIVE_TEXT", theme_data.DIVE_TEXT - 1)
    assert computed.get("deck:theme", key)["value"] == "Zm9v"
    monkeypatch.setattr(sector_metrics, "VERSION", sector_metrics.VERSION + 1)
    assert computed.get("deck:theme", key) is None                                 # the sector figures' rules changed: made again


def test_only_the_deck_kind_takes_the_versions_so_other_keys_and_their_short_names_are_unchanged(store):
    computed.put("theme:facts", ["IN", "TCS"], {"x": 1})
    assert computed.hkey(["IN", "TCS"]) in computed.index("theme:facts")["entries"]     # theme_routes.pieces_moved reads it so
    assert computed.versions("theme:facts") is None and computed.versions("deck:theme")


def test_admin_library_says_which_decks_and_theme_reads_are_no_longer_served(store, monkeypatch):
    computed.put("deck:theme", ["IN", "a", "pdf"], "Zm9v", label="A (PDF)", region="IN")
    row = library_admin._decks()[0]
    made = datetime.fromisoformat(row["at"])
    assert library_admin.deck_served({"versions": computed.versions("deck:theme")}, row["at"], made) is None
    assert library_admin.deck_served({"versions": computed.versions("deck:theme")}, row["at"], made + timedelta(days=1)) == "earlier day"
    assert library_admin.deck_served({}, row["at"], made) == "older version"           # kept before its versions were recorded
    monkeypatch.setattr(theme_data, "DIVE_TEXT", theme_data.DIVE_TEXT + 1)
    assert library_admin._decks()[0]["stale"] == "older version"
    # the theme library: a read kept under older rules is never served (theme_library.find) and says so, listed after the served ones
    computed.put("theme", ["IN", "old", theme_base.RULES - 1], {"payload": {}}, label="Old", region="IN", meta={"q": "old", "rules": theme_base.RULES - 1})
    computed.put("theme", ["IN", "new", theme_base.RULES], {"payload": {}}, label="New", region="IN", meta={"q": "new", "rules": theme_base.RULES})
    rows = library_admin._themes()
    assert [(r["label"], r["current"]) for r in rows] == [("New", True), ("Old", False)]


def test_the_library_dates_an_entry_by_the_india_day():
    src = open(__file__.replace("backend/tests/test_upd1_stale.py", "frontend/src/pages/admin/library.ts")).read()
    assert "tz: IST" in src and "slice(0, 10)" not in src.split("export const keptDay")[1].split(";")[0]


# ---------- the theme blog posts ----------
def _src(rows, stamp=None):
    s = {"v": 1, "theme": "Chips", "region": "US", "sector": "Chips", "members": 6, "unit": "$ million", "basis": "", "notable": [], "rows": rows}
    return {**s, "stamp": stamp} if stamp is not None else s


ROWS_OLD = [{"layer": "Equipment", "n": 3, "revenue": 900, "ebitda": 30.0, "net": 20.0, "roce": 25.0, "ebitda_n": 3, "official": False, "basis": None,
             "companies": [{"symbol": "AMAT", "name": "Applied Materials"}, {"symbol": "MU", "name": "Micron"}, {"symbol": "LRCX", "name": "Lam"}]},
            {"layer": "Designers", "n": 3, "revenue": 800, "ebitda": 40.0, "net": 30.0, "roce": 30.0, "ebitda_n": 3, "official": False, "basis": None,
             "companies": [{"symbol": "NVDA", "name": "Nvidia"}, {"symbol": "AMD", "name": "AMD"}, {"symbol": "QCOM", "name": "Qualcomm"}]}]
ROWS_NEW = [{**ROWS_OLD[0], "n": 2, "companies": ROWS_OLD[0]["companies"][:1] + ROWS_OLD[0]["companies"][2:]},
            {"layer": "Memory makers", "n": 1, "revenue": 300, "ebitda": 35.0, "net": 25.0, "roce": 20.0, "ebitda_n": 1, "official": False, "basis": None,
             "companies": [{"symbol": "MU", "name": "Micron"}]}, ROWS_OLD[1]]


@pytest.fixture
def posts(monkeypatch):
    kept: dict = {}

    def upsert(post, now=None):
        old = kept.get(post["slug"])
        row = {"slug": post["slug"], "kind": "research", "title": post["title"], "summary": post["summary"], "published": post.get("published", True),
               "published_at": (old or post)["published_at"], "body": {"blocks": post["blocks"], "src": post.get("src")}}
        if old:
            row["published"] = old["published"]               # blog.upsert_research never changes whether it is published
        kept[post["slug"]] = row
        return "updated" if old else "new"
    monkeypatch.setattr(blog, "get", lambda slug: kept.get(slug))
    monkeypatch.setattr(blog, "upsert_research", upsert)
    monkeypatch.setattr(blog, "set_published", lambda slug, on, now=None: kept[slug].update(published=on))
    monkeypatch.setattr(blog, "admin_rows", lambda limit=200: [{k: v for k, v in r.items() if k != "body"} for r in kept.values()])
    return kept


def _store_post(posts, rows, stamp, published=True):
    post = BR.theme_post_from(_src(rows, stamp), datetime(2026, 11, 1, tzinfo=timezone.utc))
    posts[post["slug"]] = {"slug": post["slug"], "kind": "research", "title": post["title"], "summary": post["summary"], "published": published,
                           "published_at": post["published_at"], "body": {"blocks": post["blocks"], "src": post["src"]}}
    return post["slug"]


def test_a_new_theme_post_carries_the_versions_its_figures_were_made_under():
    src = BR.theme_source({"chain": {"rows": []}, "layers": []}, "Chips", "US")
    assert src["stamp"] == BR.theme_stamp() == [theme_base.RULES, theme_data.DIVE_TEXT, sector_metrics.VERSION]
    assert not BR.stale_figures(src) and BR.stale_figures({**src, "stamp": [0, 0, 0]}) and BR.stale_figures({"rows": []})


def test_a_stored_post_from_older_rules_takes_the_new_figures_and_keeps_its_address_and_state(posts):
    slug = _store_post(posts, ROWS_OLD, [theme_base.RULES - 1, theme_data.DIVE_TEXT, sector_metrics.VERSION])
    assert "Micron" in json.dumps(posts[slug]["body"]["blocks"][-3:])
    assert BR.carry_to_stored(slug, _src(ROWS_NEW, BR.theme_stamp())) == "updated"
    got = posts[slug]
    assert got["published"] is True and got["body"]["src"]["stamp"] == BR.theme_stamp()
    assert [r["layer"] for r in got["body"]["src"]["rows"]] == ["Equipment", "Memory makers", "Designers"]
    who = next(b for b in got["body"]["blocks"] if b.get("t") == "table" and b["head"] == ["Layer", "Companies"])
    assert "Micron" not in json.dumps(who["rows"][0]) and "Micron" in json.dumps(who["rows"][1])


def test_a_stored_post_from_todays_rules_is_left_alone_and_one_the_new_figures_cant_stand_is_hidden(posts):
    slug = _store_post(posts, ROWS_OLD, BR.theme_stamp())
    assert BR.carry_to_stored(slug, _src(ROWS_NEW, BR.theme_stamp())) is None
    assert [r["layer"] for r in posts[slug]["body"]["src"]["rows"]] == ["Equipment", "Designers"]
    old = _store_post(posts, ROWS_OLD, None)                      # kept before posts carried their versions: stale
    assert BR.carry_to_stored(old, _src(ROWS_OLD[:1], BR.theme_stamp())) == "hidden" and posts[old]["published"] is False


def test_the_theme_read_that_builds_a_new_dive_brings_the_stored_post_up_to_date(posts, monkeypatch):
    from app.intel import theme_routes as T
    monkeypatch.setattr(BR, "same_day_twin", lambda post, rows=None: None)
    slug = _store_post(posts, ROWS_OLD, [0, 0, 0], published=False)
    dive = {"sector": "Chips", "members": 6, "unit": "$ million", "notable": [],
            "chain": {"rows": [{k: r[k] for k in ("layer", "n", "revenue", "ebitda", "net", "roce", "ebitda_n")} for r in ROWS_NEW]},
            "layers": [{"layer": r["layer"], "companies": r["companies"]} for r in ROWS_NEW]}
    T.auto_post("US", "Chips", dive, wait=True)                  # what dive_of does with each new checked dive
    assert posts[slug]["body"]["src"]["stamp"] == BR.theme_stamp() and posts[slug]["published"] is False
    assert len(posts) == 1                                        # no second post: the address it has


def test_after_a_deploy_the_stale_posts_are_worked_out_again_from_the_librarys_read(posts, store):
    a = _store_post(posts, ROWS_OLD, [0, 0, 0])
    asked = []

    def dive_for(region, theme):
        asked.append((region, theme))
        return {"sector": "Chips", "members": 6, "unit": "$ million", "notable": [],
                "chain": {"rows": [{k: r[k] for k in ("layer", "n", "revenue", "ebitda", "net", "roce", "ebitda_n")} for r in ROWS_NEW]},
                "layers": [{"layer": r["layer"], "companies": r["companies"]} for r in ROWS_NEW]}
    out = BR.refresh_stale_theme_posts(dive_for=dive_for)
    assert asked == [("US", "Chips")] and out["made"] == [{"post": "theme", "slug": a, "result": "updated"}]
    assert BR.refresh_stale_theme_posts(dive_for=dive_for)["made"] == [] and len(asked) == 1        # up to date: not asked again
    # the stamp: due until a run has done what it can, then not looked at again for these rules
    assert BR.theme_posts_due()
    assert BR.refresh_theme_posts_if_due() is not None and not BR.theme_posts_due() and BR.refresh_theme_posts_if_due() is None


def test_a_theme_the_library_holds_no_current_read_of_waits_for_its_next_read(posts, store):
    a = _store_post(posts, ROWS_OLD, [0, 0, 0])
    out = BR.refresh_stale_theme_posts(dive_for=lambda r, t: None)
    assert out["waiting"] == [a] and out["made"] == [] and BR.stale_figures(posts[a]["body"]["src"])


def test_admin_blog_marks_stale_posts_and_doesnt_count_a_post_the_site_answers_not_found_for(posts, monkeypatch):
    good = _store_post(posts, ROWS_OLD, [0, 0, 0])
    empty = BR.theme_post_from(_src([], BR.theme_stamp()) | {"theme": "Empty"})
    posts[empty["slug"]] = {"slug": empty["slug"], "kind": "research", "title": "Empty", "summary": "x", "published": True, "indexable": True,
                            "published_at": empty["published_at"], "body": {"src": empty["src"]}}
    for r in posts.values():
        r.setdefault("indexable", True)
    monkeypatch.setattr(blog, "theme_sources", lambda limit=500: {s: r["body"]["src"] for s, r in posts.items()})
    monkeypatch.setattr(BR, "last_run", lambda: {})
    out = blog_pages.admin_blog(None)
    body = json.loads(out.body) if hasattr(out, "body") else out
    rows = {p["slug"]: p for p in body["posts"]}
    assert rows[good]["stale_figures"] and not rows[good]["not_shown"]
    assert rows[empty["slug"]]["not_shown"] and not rows[empty["slug"]]["stale_figures"]
    assert body["counts"]["shown"] == 1 and body["counts"]["posts"] == 2


# ---------- Overview ----------
def test_revenue_of_the_last_30_days_sums_30_india_days(monkeypatch):
    today = datetime.now(timezone.utc).astimezone(IST).date()
    rows = [{"date": (today - timedelta(days=d)).isoformat(), "total": 100.0, "currency": "INR"} for d in range(0, 40)]
    monkeypatch.setattr(invoices, "of_year", lambda y: [r for r in rows if invoices.fy(datetime.fromisoformat(r["date"] + "T12:00:00+05:30")) == y])
    got = main.revenue_since(30)
    assert got["count"] == 30 and got["by_currency"] == {"INR": 3000.0}


@pytest.fixture
def w(monkeypatch):
    from tests import world as W
    world = W.build(monkeypatch)
    main.forget_overview()
    yield world
    main.forget_overview()
    world["close"]()


def test_last_active_counts_what_active_users_counts(w, monkeypatch):
    """An AI read counts as activity on Overview ("Active users, last 7 days"); the Users list's "Last active" counts it too."""
    from tests.fake_db import headers
    now = datetime.now(timezone.utc)
    seen = {"u-basic": {"email": "basic@example.com", "created_at": (now - timedelta(days=30)).isoformat(),
                        "last_sign_in_at": (now - timedelta(days=9)).isoformat()}}
    monkeypatch.setattr(admin, "sign_ins", lambda fresh=False: (seen, None))
    db.sb().table("usage_events").insert({"user_id": "u-basic", "kind": "research_ai", "created_at": (now - timedelta(hours=2)).isoformat()}).execute()
    assert admin.active_users(7) >= 1
    row = next(u for u in w["client"].get("/admin/users?q=basic@", headers=headers("admin-token")).json() if u["id"] == "u-basic")
    assert row["last_active"] > seen["u-basic"]["last_sign_in_at"]
