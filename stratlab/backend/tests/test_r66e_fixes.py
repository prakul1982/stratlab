"""r66e (R66 theme engine): the LIVE12A theme findings. Each test fails before its fix and passes after (guards marked)."""
import json

import pytest

from app import computed, public_themes
from app.intel import routes as R
from app.intel import theme_base, theme_data, theme_library, theme_recheck, theme_routes
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    computed.reset_for_tests()
    theme_library._refreshing.clear()
    theme_recheck._asked.clear()
    yield built
    built["close"]()


def co(t, name, **kw):
    return {"ticker": t, "name": name, "what": f"{name} makes ships for navies", "verified": True, **kw}


def payload(sector="Ships", n=6, at=5):
    return {"sector": sector, "generated_at": at, "ai": None, "placements": {"checked": True, "placed": n},
            "summary": f"{sector} makers.",
            "value_chain": [{"layer": "Yards", "companies": [co(f"S{sector[:2].upper()}{i}", f"{sector} {i} Ltd") for i in range(n)]}],
            "sub_themes": []}


def keep(q, p):
    assert theme_library.keep("IN", q, json.loads(json.dumps(p)))


def put_dive(name, p, dive=None):
    key = theme_routes.dive_key("IN", name, {**p, "_library": name})
    computed.put(theme_library.DIVE, key, {"dive": dive or {"sector": p["sector"], "layers": []}, "pieces": {}}, label=p["sector"], region="IN",
                 meta={"q": name, "rules": theme_base.RULES})


# ---------- item 1: after a version change every stored theme is queued, and the job drains the queue one theme at a time ----------
def test_a_version_bump_queues_every_stored_theme_and_the_job_drains_it(w, monkeypatch):
    keep("ships", payload("Ships"))
    keep("rail", payload("Rail"))
    assert theme_recheck.queue() == 2                      # nothing queued before: both
    assert theme_recheck.queue() == 0                      # the same versions: nothing new
    worked = []

    def work(region, name):                                # the job's rebuild, as rebuild() keeps them: the read under today's rules, its dive
        worked.append(name)
        p = theme_library.stored(region, name)["payload"]
        put_dive(name, p)

    # both still lack a dive under today's versions: each is worked out once, then the queue is empty
    assert theme_recheck.step(work)["outcome"] == "rebuilt"
    assert theme_recheck.step(work)["outcome"] == "rebuilt"
    assert theme_recheck.step(work) is None and sorted(worked) == ["rail", "ship"]
    # the dive text bumped (a deploy): every stored theme queued again, the read stored under the older rules too
    monkeypatch.setattr(theme_data, "DIVE_TEXT", theme_data.DIVE_TEXT + 1)
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    assert theme_recheck.queue() == 2 and theme_recheck.state()["todo"] == 2
    assert theme_recheck.queued("IN", "ship")

    def work2(region, name):
        old = theme_library.older(region, name)
        keep(old["q"], old["payload"])
        put_dive(name, theme_library.stored(region, name)["payload"])
    theme_recheck.step(work2)
    # the queue is kept in the store: a restart (nothing in memory) goes on where it stopped
    theme_recheck._running.clear()
    assert theme_recheck._load()["todo"] and theme_recheck.step(work2)["outcome"] == "rebuilt"
    st = theme_recheck.state()
    assert st["todo"] == 0 and st["done"] == 2 and theme_recheck.current("IN", "ship") and theme_recheck.current("IN", "rail")


def test_a_theme_already_current_is_skipped_and_one_not_finished_is_tried_again_then_left(w, monkeypatch):
    keep("ships", payload("Ships"))
    put_dive("ship", theme_library.stored("IN", "ship")["payload"])
    keep("rail", payload("Rail"))
    theme_recheck.queue()
    called = []

    def never(region, name):
        called.append(name)
        raise theme_recheck.NotDone("its checks are not finished yet")
    outcomes = []
    while (x := theme_recheck.step(never)) is not None:
        outcomes.append((x["theme"][1], x["outcome"]))
    assert ("ship", "current") in outcomes and "ship" not in called          # current: skipped, nothing worked out
    assert called == ["rail"] * theme_recheck.TRIES                            # tried again at the end of the queue, then left
    assert theme_recheck.state()["left"] == {"IN|rail": "its checks are not finished yet"}


def test_a_theme_whose_map_is_not_stored_is_left_without_an_ai_map_being_written(w, monkeypatch):
    keep("ships", payload("Ships"))
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    asked = []
    monkeypatch.setattr(R, "sector_payload", lambda *a, **k: asked.append(a) or {})
    theme_recheck.queue()
    out = theme_recheck.step()
    assert out["outcome"] == "left" and "AI map is not stored" in out["why"] and asked == []


# ---------- item 3: a theme stored under older rules is served at once, saying so, and goes to the front of the queue ----------
def test_a_theme_stored_under_older_rules_is_served_at_once_and_asked_for_first(w, monkeypatch):
    keep("rail", payload("Rail"))
    keep("ships", payload("Ships"))
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    started = []
    monkeypatch.setattr(R, "sector_payload", lambda *a, **k: started.append(a) or (_ for _ in ()).throw(AssertionError("no live check")))
    got = json.loads(R.sector(q="Ships", region="IN", refresh=False, profile=None).body)
    assert got["sector"] == "Ships" and got["ai"] is None and got["older"]["rechecking"] is True and started == []
    assert theme_recheck._load()["todo"][0] == ["IN", "ship"]                 # first in the queue
    # the theme's other parts read the same stored read, marked older (never kept again from it)
    r, theme, m, _ = R.theme_map(None, "IN", "ships")
    assert m["_older"] is True and m["_library"] == "ship"
    # the deck waits for the re-check instead of printing the older read
    pending: list = []
    theme_routes.map_for_deck(R, None, "IN", "ships", pending=pending)
    assert pending == [True]


def test_no_dive_under_todays_versions_serves_the_newest_kept_one_marked_updating(w, monkeypatch):
    p = payload("Ships")
    keep("ships", p)
    put_dive("ship", theme_library.stored("IN", "ship")["payload"], {"sector": "Ships", "layers": [], "mark": "old"})
    monkeypatch.setattr(theme_data, "DIVE_TEXT", theme_data.DIVE_TEXT + 1)       # the dive text bumped: today's key misses
    queued = []
    monkeypatch.setattr(theme_routes, "_rebuild_behind", lambda r, t, m, key: queued.append(t) or True)
    monkeypatch.setattr(theme_routes, "BEHIND_ON", True)
    monkeypatch.setattr(theme_routes, "sources", lambda *a, **k: (_ for _ in ()).throw(AssertionError("worked out in the request")))
    m = {**theme_library.stored("IN", "ship")["payload"], "_library": "ship"}
    got = theme_routes.dive_of("IN", "ships", m, behind=True)
    assert got["mark"] == "old" and got["updating"] is True and queued == ["ships"]
    # a read stored under older rules: the re-check job is asked, and a dive worked out from it is never kept
    got = theme_routes.dive_of("IN", "ships", {**m, "_older": True}, behind=True)
    assert got["updating"] is True and theme_recheck._load()["todo"][0] == ["IN", "ship"]


def test_a_dive_worked_out_from_an_older_read_is_not_kept(w, monkeypatch):
    p = payload("Ships")
    keep("ships", p)
    m = {**theme_library.stored("IN", "ship")["payload"], "_library": "ship", "_older": True}
    monkeypatch.setattr(theme_data, "build", lambda *a, **k: {"sector": "Ships", "layers": []})
    monkeypatch.setattr(theme_routes, "sources", lambda *a, **k: type("S", (), {"pieces": {}})())
    monkeypatch.setattr(theme_routes, "dive_gaps", lambda *a, **k: [])
    monkeypatch.setattr(theme_routes, "membership_check", lambda *a, **k: {})
    kept = []
    monkeypatch.setattr(computed, "put", lambda *a, **k: kept.append(a[0]))
    theme_routes.dive_of("IN", "ships", m)
    assert theme_library.DIVE not in kept


def test_the_public_page_of_a_theme_stored_under_older_rules_says_it_is_checked_again(w, monkeypatch):
    keep("ships", payload("Ships"))
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    theme_recheck.queue()
    entry = public_themes.entries("IN")[0]
    html = public_themes.render(public_themes.view(entry, public_themes.payload(entry)))
    import html as H
    assert "data-older" in html and H.escape(public_themes.OLDER_LINE) in html and H.escape(public_themes.RECHECKING_LINE) in html


def test_guard_a_current_theme_says_nothing_of_an_older_check(w, monkeypatch):
    keep("ships", payload("Ships"))
    entry = public_themes.entries("IN")[0]
    assert "data-older" not in public_themes.render(public_themes.view(entry, public_themes.payload(entry)))
    got = json.loads(R.sector(q="Ships", region="IN", refresh=False, profile=None).body)
    assert "older" not in got
