"""R19: the shared store (computed.py), the theme library (intel/theme_library.py), Refresh with its guard window and daily cap,
Admin → Library and the person's usage (owner, 7 Nov: "store it once ... reuse it ... tell them their daily quota left")."""
import json

import pytest
from fastapi.testclient import TestClient

from app import computed, db, main, plans
from app.intel import ai as A
from app.intel import routes, theme_base, theme_library as L, theme_routes
from tests.test_research_api import api  # noqa: F401  (the research pages' fake world, signed in as a Free user)

U2 = {"id": "u2", "_plan": "free", "plan": "free"}


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
    A._missed.clear()
    L._refreshing.clear()
    return s


@pytest.fixture
def lib(api, store):  # noqa: F811
    return api


# ---------- the store ----------
def test_kept_once_served_to_everyone_with_hits_sizes_and_totals(store):
    assert computed.get("ai:company", ["IN", "TCS"]) is None                       # a miss
    e = computed.put("ai:company", ["IN", "TCS"], {"summary": "x"}, label="TCS", region="IN")
    assert e["size"] > 0 and e["refreshes"] == 0
    assert computed.get("ai:company", ["IN", "TCS"])["value"] == {"summary": "x"}
    computed.get("ai:company", ["IN", "TCS"])
    row = next(s for s in computed.stats() if s["kind"] == "ai:company")
    assert row["entries"] == 1 and row["hits"] == 2 and row["misses"] == 1 and row["hit_rate"] == 66.7 and row["bytes"] == e["size"]
    assert row["saved_ai_calls"] == 2 and row["saved_seconds"] > 0
    computed.put("ai:company", ["IN", "TCS"], {"summary": "y"}, label="TCS", region="IN", by="pro")       # a Refresh, by a Pro user
    row = next(s for s in computed.stats() if s["kind"] == "ai:company")
    assert row["refreshes"] == 1 and row["by"]["pro"] == 1 and row["entries"] == 1
    assert computed.entries("ai:company")[0]["refreshes"] == 1 and computed.entries("ai:company")[0]["hits"] == 2


def test_a_result_too_big_is_not_kept_and_nothing_is_evicted_on_its_own(store, monkeypatch):
    monkeypatch.setattr(computed, "ENTRY_MAX", 200)
    assert computed.put("theme", ["IN", "big", 18], {"x": "a" * 500}) is None
    for i in range(30):
        computed.put("ai:ask", [f"q{i}"], {"a": i})
    assert len(computed.index("ai:ask")["entries"]) == 30                 # no cap: the owner removes in Admin


def test_remove_takes_it_out_for_everyone(store):
    e = computed.put("ai:ask", ["q"], {"a": 1})
    assert computed.remove("ai:ask", e["hk"]) and computed.get("ai:ask", ["q"]) is None and not computed.index("ai:ask")["entries"]


def test_an_unreachable_store_is_a_miss_never_an_error(monkeypatch):
    def boom(*a):
        raise RuntimeError("down")
    monkeypatch.setattr(db, "get_setting", boom)
    monkeypatch.setattr(db, "set_setting", boom)
    assert computed.get("ai:ask", ["q"]) is None and computed.put("ai:ask", ["q"], {"a": 1}) is None


# ---------- Refresh: guard window and daily cap ----------
def test_the_guard_window_and_the_daily_cap(store, monkeypatch):
    used = []
    monkeypatch.setattr(db, "count_usage", lambda u, k, since: sum(1 for x in used if x == k))
    monkeypatch.setattr(db, "add_usage", lambda u, k: used.append(k))
    monkeypatch.setattr(plans, "REFRESHES_PER_DAY", {"free": 2, "basic": 10, "pro": 30})
    now = computed._now()
    me = {"id": "u1", "_plan": "free", "plan": "free"}
    assert computed.refresh_gate(me, "ai:company", now - 60) == "fresh" and used == []         # written a minute ago
    assert computed.refresh_gate(me, "ai:company", None) == "go" and used == []                # nothing kept yet: not counted
    old = now - 7 * 3600
    assert [computed.refresh_gate(me, "ai:company", old) for _ in range(3)] == ["go", "go", "capped"] and used == ["refresh", "refresh"]
    assert computed.refresh_gate(me, "ai:pulse", now - 400) == "capped"                          # the mood's window is 5 minutes


# ---------- the theme library's matching ----------
@pytest.mark.parametrize("a,b", [("EV", "electric vehicles"), ("Electric Vehicle", "EVs"), ("India defence", "defense"),
                                 ("private banks", "Private Sector Banks"), ("PSU banks", "public sector banks"), ("Autos", "automotive"),
                                 ("AI data centres", "AI data centers")])
def test_one_theme_however_it_is_written(a, b):
    assert L.normalise(a, "IN") == L.normalise(b, "IN")


@pytest.mark.parametrize("a,b", [("private banks", "public banks"), ("IT services", "IT hardware"), ("solar", "polar"),
                                 ("defence", "india"), ("steel", "steam")])
def test_never_a_different_theme(a, b):
    na, nb = L.normalise(a, "IN"), L.normalise(b, "IN")
    assert na != nb and not L.close(na, nb)


def test_find_by_name_alias_or_close_spelling_and_never_the_wrong_one(store):
    payload = {"sector": "Private Sector Banks", "generated_at": 5, "ai": None, "placements": {"checked": True, "pending": 0},
               "value_chain": [{"layer": "Banks", "companies": [{"ticker": "HDFCBANK"}, {"ticker": "ICICIBANK"}]}], "sub_themes": []}
    assert L.keep("IN", "private banks", payload)
    assert L.find("IN", "Private sector bank")["name"] == "private bank"
    assert L.find("IN", "privat banks")["name"] == "private bank"                    # a typo, over the high bar
    assert L.find("IN", "public banks") is None and L.find("US", "private banks") is None
    assert computed.index("theme")["entries"][L.find("IN", "private banks")["id"]]["meta"]["members"] == 2


def test_an_unfinished_read_is_not_kept(store):
    assert not L.keep("IN", "rail", {"sector": "Rail", "generated_at": 0, "ai": None, "placements": {"checked": True}})
    assert not L.keep("IN", "rail", {"sector": "Rail", "generated_at": 5, "ai": {"state": "working"}, "placements": {"checked": True}})
    assert not L.keep("IN", "rail", {"sector": "Rail", "generated_at": 5, "ai": None, "placements": {"checked": False}})


def test_a_rules_change_is_a_new_key(store, monkeypatch):
    L.keep("IN", "rail", {"sector": "Rail", "generated_at": 5, "ai": None, "placements": {"checked": True}, "value_chain": []})
    assert L.stored("IN", "railways") is not None
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    assert L.stored("IN", "railways") is None


# ---------- GET /research/sector from the library ----------
def _sector(api, q, refresh=False):  # noqa: F811
    return api.get(f"/research/sector?q={q}&region=US" + ("&refresh=true" if refresh else "")).json()


def test_a_second_search_however_written_is_served_from_the_library_with_no_ai(lib):
    first = _sector(lib, "AI data centers")
    assert first["ai"] is None and first["generated_at"] > 0
    calls = len(lib.calls)
    again = _sector(lib, "ai data centres")
    assert len(lib.calls) == calls and again["generated_at"] == first["generated_at"]
    assert [c["ticker"] for v in again["value_chain"] for c in v["companies"]] == [c["ticker"] for v in first["value_chain"] for c in v["companies"]]
    assert "refresh_state" not in again and "_library" not in again
    assert theme_library_suggest(lib, "data")[0]["searched"] >= 1


def theme_library_suggest(api, q):  # noqa: F811
    computed.flush(force=True)
    return api.get(f"/research/theme-library/suggest?q={q}&region=US").json()["items"]


def test_a_stored_read_is_served_unchanged_however_old(lib, store):
    first = _sector(lib, "AI data centers")
    for k, v in list(store.items()):                  # kept a year ago
        if k.startswith("cres:theme:") and v:
            e = json.loads(v)
            e["at"] -= 365 * 86400
            store[k] = json.dumps(e)
    calls = len(lib.calls)
    assert _sector(lib, "AI data centers")["generated_at"] == first["generated_at"] and len(lib.calls) == calls


def test_refresh_updates_the_shared_read_for_the_next_person_with_a_guard_and_a_cap(lib, monkeypatch, request):
    first = _sector(lib, "AI data centers")
    calls = len(lib.calls)
    assert _sector(lib, "AI data centers", refresh=True)["refresh_state"] == "fresh" and len(lib.calls) == calls     # just written
    import time
    import time_machine
    later = time_machine.travel(time.time() + 7 * 3600, tick=True)          # past the guard window
    later.start()
    request.addfinalizer(later.stop)
    monkeypatch.setattr(plans, "REFRESHES_PER_DAY", {"free": 1, "basic": 1, "pro": 1})
    monkeypatch.setattr(computed, "DEFAULT_GUARD", 0)                         # (u2 refreshes right after)
    mine = []                                                                 # each person's own count
    monkeypatch.setattr(db, "count_usage", lambda u, k, since: sum(1 for x in mine if x == (u, k)))
    monkeypatch.setattr(db, "add_usage", lambda u, k: mine.append((u, k)))
    got = _sector(lib, "AI data centers", refresh=True)
    assert got["refresh_state"] == "done" and len(lib.calls) > calls and got["generated_at"] > first["generated_at"]
    main.app.dependency_overrides[main.current_profile] = lambda: U2          # someone else, next
    calls = len(lib.calls)
    seen = _sector(lib, "AI data center")
    assert seen["generated_at"] == got["generated_at"] and len(lib.calls) == calls
    on = time_machine.travel(time.time() + 60, tick=True)                    # a minute on (a map's checks are keyed to the second)
    on.start()
    request.addfinalizer(on.stop)
    capped = _sector(lib, "AI data centers", refresh=True)                    # u2's first refresh: allowed
    assert capped["refresh_state"] == "done"
    capped = _sector(lib, "AI data centers", refresh=True)                    # u2's second: past the day's one
    assert capped["refresh_state"] == "capped" and capped["generated_at"] > 0
    row = next(s for s in computed.stats() if s["kind"] == "theme")
    assert row["refreshes"] == 2 and row["by"]["free"] == 2


def test_a_failed_refresh_keeps_the_old_read_with_its_date(lib, monkeypatch):
    old = lib.get("/research/company/US/NVDA/ai").json()
    monkeypatch.setattr(computed, "DEFAULT_GUARD", 0)
    from app.ai_providers import AIError

    def down(*a, **k):
        raise AIError("every provider is busy")
    monkeypatch.setattr(A, "complete", down)
    got = lib.get("/research/company/US/NVDA/ai?refresh=true")
    assert got.status_code == 200 and got.json()["refresh_state"] == "failed"
    assert got.json()["summary"] == old["summary"] and got.json()["generated_at"] == old["generated_at"]


def test_an_ai_read_survives_a_restart_from_the_shared_store(lib):
    first = lib.get("/research/company/US/NVDA/ai").json()
    calls = len(lib.calls)
    A._cache.clear()                                   # a new process: its memory is empty
    again = lib.get("/research/company/US/NVDA/ai").json()
    assert again["summary"] == first["summary"] and len(lib.calls) == calls


# ---------- company figures kept once and shared by two themes ----------
def test_a_refresh_of_one_theme_updates_the_company_figures_another_theme_uses(store, monkeypatch):
    facts = {"X": {"v": 1}, "Y": {"v": 10}}
    monkeypatch.setattr(routes, "public_facts", lambda r, s: dict(facts[s]))
    built = []

    def build(r, theme, fm, src):
        built.append(theme)
        return {"x": src.facts("X")["v"], "theme": theme}
    monkeypatch.setattr(theme_routes.theme_data, "build", build)
    monkeypatch.setattr(theme_routes, "auto_post", lambda *a, **k: None)

    def themap(t, other):
        return {"sector": t, "generated_at": 1, "placements": {"checked": True, "placed": 2},
                "value_chain": [{"layer": "L", "official": True, "companies": [{"ticker": "X"}, {"ticker": other}]}], "sub_themes": []}
    a, b = themap("Auto parts", "Y"), themap("Auto ancillaries", "Y")
    assert theme_routes.dive_of("IN", "Auto parts", a)["x"] == 1 and theme_routes.dive_of("IN", "Auto ancillaries", b)["x"] == 1
    facts["X"] = {"v": 2}                                # the company's page changes: nothing moves on its own
    assert theme_routes.dive_of("IN", "Auto parts", a)["x"] == 1 and theme_routes.dive_of("IN", "Auto ancillaries", b)["x"] == 1
    n = len(built)
    assert theme_routes.dive_of("IN", "Auto parts", a, refresh=True)["x"] == 2            # a Refresh of one theme...
    assert theme_routes.dive_of("IN", "Auto ancillaries", b)["x"] == 2                    # ...and the other has X's new figures
    assert len(built) == n + 2
    assert theme_routes.dive_of("IN", "Auto ancillaries", b)["x"] == 2 and len(built) == n + 2       # then served as kept


# ---------- Admin → Library ----------
def test_admin_library_is_admin_only_and_shows_every_store(lib):
    assert lib.get("/admin/stored").status_code == 403
    _sector(lib, "AI data centers")
    from app import admin
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "ad", "_plan": "pro", "plan": "pro", "email": "owner@example.com"}
    v = lib.get("/admin/stored").json()
    kinds = {s["kind"]: s for s in v["stores"]}
    assert kinds["theme"]["entries"] == 1 and kinds["ai:sector"]["entries"] >= 1 and {"stocks:", "deep:"} <= {s["prefix"] for s in v["stored"]}
    t = v["themes"][0]
    assert t["region"] == "US" and t["members"] > 0 and t["size"] > 0 and t["q"]
    assert lib.get("/admin/stored/entries?kind=ai:sector").json()["rows"]
    assert lib.post("/admin/stored/remove", json={"kind": "theme", "id": t["id"]}).json()["ok"]
    assert lib.get("/admin/stored").json()["themes"] == []
    assert lib.post("/admin/stored/remove", json={"kind": "nope", "id": "abcdef"}).status_code == 400


# ---------- the person's usage ----------
def test_my_usage_lists_every_limit_and_the_refreshes_left(lib, monkeypatch):
    rows = {r["key"]: r for r in lib.get("/me/usage").json()["rows"]}
    assert rows["refresh"]["limit"] == plans.REFRESHES_PER_DAY["free"] and rows["refresh"]["used"] == 0 and rows["refresh"]["resets"] == "day"
    assert {"research_ai", "backtest", "deck", "deepdive", "screens", "holdings"} <= set(rows)
    assert rows["deck"]["resets"] == "month" and rows["holdings"]["resets"] is None
    _sector(lib, "AI data centers")
    monkeypatch.setattr(computed, "DEFAULT_GUARD", 0)
    _sector(lib, "AI data centers", refresh=True)
    r = {x["key"]: x for x in lib.get("/me/usage").json()["rows"]}["refresh"]
    assert r["used"] == 1 and r["left"] == r["limit"] - 1
