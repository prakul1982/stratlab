"""Saved searches and AI reads (R19): save, list, rename, update with what changed, remove; one person never sees another's; the limit;
the snapshot bounds; the erase and export of a person's data; the admin's counts by kind."""
import pytest

from app import db, saved_searches as S, user_data
from tests import world as W
from tests.fake_db import headers

THEME = {"kind": "theme", "name": "India defence", "params": {"q": "  India   defence ", "region": "in"}}


def snap(rows: dict, **figures) -> dict:
    """A theme read's snapshot as the Themes page sends it: each company's ticker -> [name, market value], and the key figures."""
    return {"rows": {t: [n, v] for t, (n, v) in rows.items()}, "figures": figures}


FIRST = snap({"HAL": ("Hindustan Aeronautics", 300000), "BEL": ("Bharat Electronics", 200000), "BEML": ("BEML", 15000)},
             companies=3, market_value=515000)
SECOND = snap({"HAL": ("Hindustan Aeronautics", 330000), "BEL": ("Bharat Electronics", 200000), "MAZDOCK": ("Mazagon Dock", 90000)},
              companies=3, market_value=620000)


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()


def test_save_list_rename_update_remove_through_the_api(w):
    c, h = w["client"], headers("basic-token")
    assert c.get("/me/saved", headers=h).json() == {"items": [], "count": 0, "limit": S.LIMIT}
    r = c.post("/me/saved", headers=h, json={**THEME, "snap": FIRST})
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert r.json()["new"] is True
    assert item["params"] == {"q": "India defence", "region": "IN"} and item["kind_label"] == "Theme"
    assert item["path"] == "/research/themes" and item["query"] == {"q": "India defence", "region": "IN"}
    assert item["read_at"] and item["rows"] == 3 and item["figures"] == {"companies": 3, "market_value": 515000}
    # a second click on the same search is the one already kept, not a copy
    again = c.post("/me/saved", headers=h, json={**THEME, "params": {"q": "India defence", "region": "IN"}})
    assert again.json()["new"] is False and again.json()["item"]["id"] == item["id"] and again.json()["count"] == 1
    # rename
    r = c.patch(f"/me/saved/{item['id']}", headers=h, json={"name": "  Defence   names "})
    assert r.status_code == 200 and r.json()["item"]["name"] == "Defence names"
    assert c.patch(f"/me/saved/{item['id']}", headers=h, json={"name": "   "}).status_code == 400
    # update: what changed since the saved read, facts only
    r = c.post(f"/me/saved/{item['id']}/update", headers=h, json={"snap": SECOND})
    assert r.status_code == 200, r.text
    ch = r.json()["changes"]
    assert [a["key"] for a in ch["added"]] == ["MAZDOCK"] and ch["added_count"] == 1
    assert [x["key"] for x in ch["removed"]] == ["BEML"] and ch["removed"][0]["label"] == "BEML"
    assert ch["moves"] == [{"key": "HAL", "label": "Hindustan Aeronautics", "before": 300000, "after": 330000, "pct": 10.0}]
    figs = {f["name"]: f for f in ch["figures"]}
    assert figs["market_value"]["change"] == 105000 and figs["market_value"]["pct"] == 20.4 and figs["companies"]["change"] == 0
    assert ch["same"] is False and r.json()["item"]["figures"]["market_value"] == 620000
    # the same read again: nothing changed
    same = c.post(f"/me/saved/{item['id']}/update", headers=h, json={"snap": SECOND}).json()["changes"]
    assert same["same"] is True and same["added"] == [] and same["removed"] == [] and same["moves"] == []
    # remove
    assert c.delete(f"/me/saved/{item['id']}", headers=h).json()["items"] == []
    assert c.delete(f"/me/saved/{item['id']}", headers=h).status_code == 404
    assert c.post(f"/me/saved/{item['id']}/update", headers=h, json={"snap": SECOND}).status_code == 404
    assert db.get_setting(f"{S.SNAP}u-basic:{item['id']}") is None                  # its snapshot went with it


def test_a_first_update_of_a_search_saved_without_a_read_keeps_the_read(w):
    c, h = w["client"], headers("free-token")
    item = c.post("/me/saved", headers=h, json=THEME).json()["item"]
    assert item["read_at"] is None and item["rows"] is None
    r = c.post(f"/me/saved/{item['id']}/update", headers=h, json={"snap": FIRST}).json()
    assert r["changes"] is None and r["item"]["read_at"] and r["item"]["rows"] == 3


def test_one_person_never_sees_or_changes_another_persons_saved_items(w):
    c, a, b = w["client"], headers("basic-token"), headers("pro-token")
    mine = c.post("/me/saved", headers=a, json={**THEME, "snap": FIRST}).json()["item"]
    assert c.get("/me/saved", headers=b).json()["items"] == []
    assert c.patch(f"/me/saved/{mine['id']}", headers=b, json={"name": "x"}).status_code == 404
    assert c.post(f"/me/saved/{mine['id']}/update", headers=b, json={"snap": SECOND}).status_code == 404
    assert c.delete(f"/me/saved/{mine['id']}", headers=b).status_code == 404
    assert [x["id"] for x in c.get("/me/saved", headers=a).json()["items"]] == [mine["id"]]
    assert c.get("/me/saved").status_code == 401                                       # signed out: nothing
    for bad in ("..%2Fx", "ffffff", "zzzzzzzzzzzz"):
        assert c.delete(f"/me/saved/{bad}", headers=a).status_code == 404


def test_the_limit_is_the_same_on_every_plan(w):
    c, h = w["client"], headers("free-token")
    for i in range(S.LIMIT):
        assert c.post("/me/saved", headers=h, json={**THEME, "params": {"q": f"theme number {i}", "region": "IN"}}).status_code == 200
    assert c.get("/me/saved/usage", headers=h).json() == {"count": S.LIMIT, "limit": S.LIMIT}
    assert c.get("/me/saved/usage", headers=headers("pro-token")).json() == {"count": 0, "limit": S.LIMIT}
    r = c.post("/me/saved", headers=h, json={**THEME, "params": {"q": "one more theme", "region": "IN"}})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "saved_limit" and f"{S.LIMIT} saved" in r.json()["detail"]["message"]
    # the one already kept still answers (no copy, no limit)
    assert c.post("/me/saved", headers=h, json={**THEME, "params": {"q": "theme number 3", "region": "IN"}}).json()["new"] is False


@pytest.mark.parametrize("body", [
    {"kind": "nope", "name": "x", "params": {"q": "India defence", "region": "IN"}},
    {"kind": "theme", "name": "x", "params": {"q": "x", "region": "IN"}},
    {"kind": "theme", "name": "x", "params": {"q": "India defence", "region": "UK"}},
    {"kind": "theme", "name": "", "params": {"q": "India defence", "region": "IN"}},
    {"kind": "company_ai", "name": "x", "params": {"region": "IN", "symbol": "../etc"}},
    {"kind": "filings", "name": "x", "params": {"region": "IN", "view": "everyone"}},
])
def test_what_cant_be_kept_is_refused_in_words(w, body):
    r = w["client"].post("/me/saved", headers=headers("basic-token"), json=body)
    assert r.status_code in (400, 422) and r.status_code != 500


def test_unknown_params_are_dropped_and_ai_reads_open_their_own_page():
    p = S.clean_params("filings", {"region": "in", "flag": "pledge", "page": "4", "evil": "x"})
    assert p == {"region": "IN", "flag": "pledge"}
    item = {"id": "a" * 12, "kind": "company_ai", "name": "x", "params": S.clean_params("company_ai", {"region": "IN", "symbol": "m&m"})}
    v = S.view(item)
    assert v["path"] == "/research/IN/M&M" and v["query"] == {} and v["ai"] is True and v["open_only"] is False
    assert S.view({**item, "kind": "deep_dive"})["open_only"] is True


def test_a_snapshot_is_bounded():
    big = {"rows": {f"S{i}": [f"Company {i}" * 20, i] for i in range(S.ROWS_MAX + 50)}, "figures": {f"f{i}": i for i in range(30)} | {"Bad Name": 1}}
    s = S.clean_snap(big)
    assert len(s["rows"]) == S.ROWS_MAX and s["cut"] is True
    assert "S0" not in s["rows"] and f"S{S.ROWS_MAX + 49}" in s["rows"]           # the largest by value stay
    assert all(len(v[0]) <= S.LABEL_MAX for v in s["rows"].values())
    assert len(s["figures"]) <= S.FIGURES_MAX and "Bad Name" not in s["figures"]
    odd = S.clean_snap({"rows": {"OK": ["x", float("nan")], "bad key!": ["y", 1], "B": ["z", True]}, "figures": {"n": "12"}})
    assert odd["rows"] == {"OK": ["x", None], "B": ["z", None]} and odd["figures"] == {"n": None}


def test_changes_list_the_largest_first_and_cap_the_lists():
    old = snap({f"O{i}": (f"Old {i}", i) for i in range(80)}, companies=80)
    new = snap({f"N{i}": (f"New {i}", i) for i in range(70)}, companies=70)
    ch = S.changes(old, new)
    assert ch["added_count"] == 70 and len(ch["added"]) == S.LIST_MAX and ch["added"][0]["key"] == "N69"
    assert ch["removed_count"] == 80 and ch["removed"][0]["key"] == "O79"
    assert ch["figures"] == [{"name": "companies", "before": 80, "after": 70, "change": -10, "pct": -12.5}]
    assert S.changes(None, new) is None


def test_erase_and_export_of_a_persons_data_include_saved_searches(w):
    c, h = w["client"], headers("basic-token")
    item = c.post("/me/saved", headers=h, json={**THEME, "snap": FIRST}).json()["item"]
    other = c.post("/me/saved", headers=headers("pro-token"), json={**THEME, "snap": FIRST}).json()["item"]
    assert "saved_searches" in [k for k, _, _ in user_data.STEPS]
    exported = dict((k, fn) for k, _, fn in user_data.EXPORT)["saved_searches"]("u-basic")
    assert [x["id"] for x in exported] == [item["id"]]
    assert S.forget("u-basic") == 1
    assert S.items("u-basic") == [] and db.get_setting(f"{S.SNAP}u-basic:{item['id']}") is None
    assert [x["id"] for x in S.items("u-pro")] == [other["id"]]                       # someone else's stays


def test_the_admin_sees_counts_by_kind_and_nobody_else_does(w):
    c = w["client"]
    c.post("/me/saved", headers=headers("basic-token"), json={**THEME, "snap": FIRST})
    c.post("/me/saved", headers=headers("basic-token"), json={"kind": "company_ai", "name": "TCS read", "params": {"region": "IN", "symbol": "TCS"}})
    c.post("/me/saved", headers=headers("pro-token"), json=THEME)
    assert c.get("/admin/saved-searches", headers=headers("basic-token")).status_code == 403
    r = c.get("/admin/saved-searches", headers=headers("admin-token")).json()
    assert r["kinds"]["theme"] == 2 and r["kinds"]["company_ai"] == 1 and r["total"] == 3 and r["people"] == 2
    assert r["labels"]["theme"] == "Theme" and "India" not in str(r)                   # counts only: no one's words
