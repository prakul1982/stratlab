"""The public strategy library: publish with the verdict, browse, copy into your own notebook, take down."""
import pytest

from app import db, library, main
from tests.test_notebooks import EMA, api  # noqa: F401  (fixture)


@pytest.fixture
def store(monkeypatch):
    kv = {}
    monkeypatch.setattr(db, "set_setting", lambda k, v: kv.__setitem__(k, v))
    monkeypatch.setattr(db, "get_setting", lambda k: kv.get(k))
    monkeypatch.setattr(db, "delete_setting", lambda k: kv.pop(k, None))
    monkeypatch.setattr(db, "settings_with_prefix", lambda p, limit=1000: [v for k, v in kv.items() if k.startswith(p)])
    return kv


def as_user(uid):
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": uid, "_plan": "pro", "plan": "pro", "email": f"{uid}@x"}


def test_publish_browse_copy_and_take_down(api, store):
    nb = api.post("/notebooks", json={"name": "BTC trend", "question": "Does the cross work on BTC?", "strategy": EMA,
                                      "instrument": "CRYPTO:BTC-USD"}).json()
    exp = api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 1500}).json()["experiment"]
    e = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"description": "A plain EMA cross.", "author": "Prakul"}).json()
    assert e["mine"] and e["author"] == "Prakul" and e["verdict"]["headline"] == exp["verdict"]["headline"]
    assert "owner" not in e and "user-1" not in str(e) and e["strategy"]["entry"]          # rules shared, owner not
    again = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"description": "Updated."}).json()
    assert again["id"] == e["id"] and again["author"] == "A StratLab user"                  # same entry, updated

    as_user("user-2")
    rows = api.get("/library", params={"market": "crypto", "q": "btc"}).json()
    assert rows["total"] == 1 and not rows["entries"][0]["mine"]
    assert api.get("/library", params={"market": "US"}).json()["total"] == 0
    mine = api.post(f"/library/{e['id']}/copy").json()
    assert mine["name"] == "BTC trend" and mine["strategy"]["entry"][0]["l"]["p"] == 10 and mine["strategy"]["entry"][0]["op"] == "xa" and mine["experiments"] == []
    assert "Copied from the strategy library" in mine["notes"] and mine["instrument"]["symbol"] == "BTC/USD"
    assert api.get(f"/library/{e['id']}").json()["copies"] == 1
    assert api.delete(f"/library/{e['id']}").status_code == 403                             # not yours

    as_user("user-1")
    assert api.delete(f"/library/{e['id']}").json() == {"deleted": True}
    assert api.get(f"/library/{e['id']}").status_code == 404


def test_upload_data_cannot_be_published(api, store):
    nb = api.post("/notebooks", json={"name": "CSV", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    saved = api.get(f"/notebooks/{nb['id']}").json()
    saved["experiments"][0]["instrument"]["market"] = "CSV"
    main.save_notebook({"id": "user-1"}, saved)
    r = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={})
    assert r.status_code == 400 and "uploaded data" in r.json()["detail"]["message"]


def test_best_sort_puts_real_edges_first():
    rows = [{"name": "a", "verdict": {"verdict": "luck"}, "stats": {"unseen": 9, "ret": 50}},
            {"name": "b", "verdict": {"verdict": "edge"}, "stats": {"unseen": 2, "ret": 5}},
            {"name": "c", "verdict": {"verdict": "edge"}, "stats": {"unseen": 7, "ret": 3}}]
    assert [r["name"] for r in library.search(rows)] == ["c", "b", "a"]
    assert [r["name"] for r in library.search(rows, verdict="luck")] == ["a"]


def test_reports_hide_an_entry_until_the_owner_of_the_site_reviews_it(api, store, monkeypatch):
    from app import admin as admin_mod
    from app.config import settings
    nb = api.post("/notebooks", json={"name": "Spammy", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    e = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"description": "buy my course"}).json()
    assert api.post(f"/library/{e['id']}/report", json={"reason": "spam"}).status_code == 400        # not your own

    for i, uid in enumerate(["r1", "r2", "r2", "r3"]):
        as_user(uid)
        r = api.post(f"/library/{e['id']}/report", json={"reason": "spam"}).json()
    assert r == {"reported": True, "hidden": True}                  # three different people (r2 counted once)
    assert api.get("/library").json()["total"] == 0 and api.get(f"/library/{e['id']}").status_code == 404
    assert api.post(f"/library/{e['id']}/copy").status_code == 404

    as_user("user-1")                                                # the author still sees it, marked hidden
    mine = api.get(f"/library/{e['id']}").json()
    assert mine["hidden"] and "reports" not in mine and "r1" not in str(mine)
    api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"description": "clean now"})   # re-publishing doesn't clear it
    as_user("r9")
    assert api.get("/library").json()["total"] == 0

    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@x")
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "boss", "_plan": "pro", "email": "boss@x", "_email_verified": True}
    monkeypatch.setattr(db, "get_profile", lambda uid, email=None: {"id": uid, "email": "author@x"})
    queue = api.get("/admin/library").json()["entries"]
    assert queue[0]["reports"] == 3 and queue[0]["reasons"] == {"spam": 3} and queue[0]["hidden"] and queue[0]["email"] == "author@x"
    assert api.post(f"/admin/library/{e['id']}", json={"action": "restore"}).json() == {"ok": True}
    as_user("r9")
    assert api.get("/library").json()["total"] == 1
    assert admin_mod.is_admin({"email": "boss@x", "_email_verified": True})


def _official(store):
    e = {"id": "seed-golden", "owner": library.OFFICIAL_OWNER, "official": True, "name": "Golden cross", "verdict": {"verdict": "mixed"}}
    library.save(e)
    return e


def test_reports_never_hide_an_official_entry(api, store):
    e = _official(store)
    for uid in ("r1", "r2", "r3", "r4"):
        as_user(uid)
        r = api.post(f"/library/{e['id']}/report", json={"reason": "spam"}).json()
    assert r == {"reported": True, "hidden": False}
    assert library.is_public(library.load(e["id"])) and len(library.load(e["id"])["reports"]) == 4       # recorded, not hidden


def test_an_entry_takes_its_group_from_the_experiment_not_the_notebook_now(api, store):
    nb = api.post("/notebooks", json={"name": "Basket", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    body = api.rows[nb["id"]]["body"]
    grp = {"id": "g1", "name": "Majors", "market": "CRYPTO", "maxOpen": 2, "members": [{"symbol": "BTC"}, {"symbol": "ETH"}]}
    inst = {"id": "GROUP:g1", "symbol": "Majors", "name": "Majors", "market": "CRYPTO", "type": "GROUP"}
    ran_on_group = {"v": 1, "strategy": EMA, "instrument": inst, "tf": "1d", "stats": {}, "verdict": {},
                    "group": {"name": "Majors", "max_open": 2, "members": [{"symbol": "BTC", "id": "CRYPTO:BTC-USD"}, {"symbol": "ETH", "id": "CRYPTO:ETH-USD"}]}}
    ran_on_stock = {"v": 2, "strategy": EMA, "instrument": {"id": "CRYPTO:BTC-USD", "symbol": "BTC/USD", "market": "CRYPTO"}, "tf": "1d", "stats": {}, "verdict": {}}
    body["experiments"] = [ran_on_group, ran_on_stock]
    body.pop("group", None)                                  # A: the notebook was switched to one stock
    a = library.entry(api.get(f"/notebooks/{nb['id']}").json(), ran_on_group, "user-1", "", "")
    assert a["instrument"] is None and a["group"]["id"] == "g1" and [m["symbol"] for m in a["group"]["members"]] == ["BTC", "ETH"]
    body["group"] = grp                                      # B: the notebook was switched to a group
    nbk = api.get(f"/notebooks/{nb['id']}").json()
    b = library.entry(nbk, ran_on_stock, "user-1", "", "")
    assert b["group"] is None and b["instrument"]["id"] == "CRYPTO:BTC-USD"
    assert library.entry(nbk, ran_on_group, "user-1", "", "")["group"] == {k: grp[k] for k in ("id", "name", "market", "maxOpen", "members")}


def test_nobody_but_the_owner_may_publish_as_stratlab(api, store, monkeypatch):
    from app.config import settings
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    for name in ("StratLab", " stratlab ", "STRATLAB"):
        r = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"author": name})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "author_reserved"
    assert api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"author": "StratLab fan"}).status_code == 200
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@x")
    main.app.dependency_overrides[main.current_profile] = lambda: {"id": "user-1", "_plan": "pro", "email": "boss@x", "_email_verified": True}
    assert api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"author": "StratLab"}).status_code == 200


def test_deleting_a_notebook_takes_its_library_entries_out(api, store):
    nb = api.post("/notebooks", json={"name": "x", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    e = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={}).json()
    assert library.load(e["id"])
    api.delete(f"/notebooks/{nb['id']}")
    assert library.load(e["id"]) is None
