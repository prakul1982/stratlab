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
    monkeypatch.setattr(db, "all_settings_with_prefix", lambda p, page=1000: [(k, v) for k, v in kv.items() if k.startswith(p)])
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
    # no reporter is named: "r1" as a value anywhere, not as letters inside the entry's random id
    assert mine["hidden"] and "reports" not in mine and "'r1'" not in repr(mine)
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
    assert api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"author": "StratLab fan"}).status_code == 400    # any name containing it
    assert api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"author": "Strategy fan"}).status_code == 200
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


def test_deleting_and_republishing_does_not_clear_a_hide(api, store):
    nb = api.post("/notebooks", json={"name": "Spammy", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    e = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"description": "x"}).json()
    for uid in ("r1", "r2", "r3"):
        as_user(uid)
        api.post(f"/library/{e['id']}/report", json={"reason": "spam"})
    as_user("user-1")
    assert api.delete(f"/library/{e['id']}").json() == {"deleted": True}
    again = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"description": "fresh"}).json()
    assert again["id"] != e["id"] and again["hidden"]
    as_user("r9")
    assert api.get("/library").json()["total"] == 0


def test_a_copy_does_not_write_over_a_hide_made_meanwhile(api, store):
    nb = api.post("/notebooks", json={"name": "Trend", "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    e = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"description": "x"}).json()
    as_user("copier")
    real = main.visible_entry

    def stale_then_hidden(eid, profile):
        got = real(eid, profile)
        library.save(library.moderate(library.load(eid), "hide"))          # the admin hides it while the copy runs
        return got
    main.visible_entry = stale_then_hidden
    try:
        assert api.post(f"/library/{e['id']}/copy").status_code == 200
    finally:
        main.visible_entry = real
    assert library.load(e["id"])["hidden"] and library.load(e["id"])["copies"] == 1


def _published(api, name="N"):
    nb = api.post("/notebooks", json={"name": name, "strategy": EMA, "instrument": "CRYPTO:BTC-USD"}).json()
    api.post(f"/notebooks/{nb['id']}/experiments", json={"days": 400})
    e = api.post(f"/notebooks/{nb['id']}/experiments/1/library", json={"description": "d"}).json()
    return nb["id"], e


def test_deleting_an_experiment_or_notebook_takes_its_library_entry_down(api, store):
    nid, e = _published(api)
    assert api.delete(f"/notebooks/{nid}/experiments/1").status_code == 200
    assert api.get(f"/library/{e['id']}").status_code == 404
    nid, e = _published(api, "M")
    orphan = dict(library.load(e["id"]))
    nb = api.get(f"/notebooks/{nid}").json()
    nb["experiments"][0].pop("library")                      # an entry no experiment points to any more
    main.save_notebook({"id": "user-1"}, nb)
    assert api.delete(f"/notebooks/{nid}").status_code == 200
    assert library.load(orphan["id"]) is None


def test_a_deleted_version_number_is_not_reused(api, store):
    nid, _ = _published(api)
    api.delete(f"/notebooks/{nid}/experiments/1")
    nb = api.get(f"/notebooks/{nid}").json()
    nb["strategy"]["entry"][0]["l"]["p"] = 7
    api.put(f"/notebooks/{nid}", json={"strategy": nb["strategy"]})
    assert api.post(f"/notebooks/{nid}/experiments", json={"days": 400}).json()["experiment"]["v"] == 2


def test_duplicate_keeps_group_and_gaps(api, store):
    nid, _ = _published(api)
    nb = api.get(f"/notebooks/{nid}").json()
    nb["group"], nb["gaps"] = {"id": "g", "name": "G", "members": []}, {"x": 1}
    main.save_notebook({"id": "user-1"}, nb)
    copy = api.post(f"/notebooks/{nid}/duplicate").json()
    assert copy["group"]["id"] == "g" and copy["gaps"] == {"x": 1}


def test_a_hide_carries_to_the_next_version_until_the_admin_restores_it(store):
    first = {"id": "a1", "owner": "u", "source": {"nid": "n", "v": 1}, "hidden": True, "hidden_by": "reports"}
    library.save(first)
    nxt = library.carry_moderation(None, {"id": "a2", "owner": "u", "source": {"nid": "n", "v": 2}})
    assert nxt["hidden"]
    library.clear_hide(first)
    assert not library.carry_moderation(None, {"id": "a3", "owner": "u", "source": {"nid": "n", "v": 3}}).get("hidden")


def test_reserved_author_names_and_publish_throttle(api, store):
    nid, _ = _published(api)
    r = api.post(f"/notebooks/{nid}/experiments/1/library", json={"author": "Strat-Lab Official"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "author_reserved"
    main._recent.clear()
    codes = [api.post(f"/notebooks/{nid}/experiments/1/library", json={"author": "x"}).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429


def test_a_share_made_meanwhile_keeps_its_token(api, store, monkeypatch):
    nid, _ = _published(api)
    real = main.public.publish

    def racing(nb, exp, image):
        mine = real(nb, exp, image)
        nb2 = main.get_notebook({"id": "user-1"}, nid)         # the other request lands first
        nb2["experiments"][0]["public"] = "theirs-token"
        main.save_notebook({"id": "user-1"}, nb2)
        return mine
    monkeypatch.setattr(main.public, "publish", racing)
    assert api.post(f"/notebooks/{nid}/experiments/1/share", json={}).json()["token"] == "theirs-token"


def test_a_look_alike_stratlab_author_is_refused(api, store):
    nid, _ = _published(api)
    for name in ("ＳｔｒａｔＬａｂ", "ｓｔｒａｔｌａｂ fan", "Strat－Lab"):     # full-width letters and dash
        r = api.post(f"/notebooks/{nid}/experiments/1/library", json={"author": name})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "author_reserved"


def test_publishing_again_after_taking_it_down_leaves_one_entry_even_when_two_land_at_once(api, store, monkeypatch):
    nid, e = _published(api)
    assert api.delete(f"/library/{e['id']}").status_code == 200       # the notebook still points at the removed entry
    real = main.library.save
    state = {"n": 0}

    def racing(entry):
        real(entry)
        if state["n"] == 0:                                            # a second publish lands while the first is mid-way
            state["n"] = 1
            api.post(f"/notebooks/{nid}/experiments/1/library", json={"description": "second"})
    monkeypatch.setattr(main.library, "save", racing)
    first = api.post(f"/notebooks/{nid}/experiments/1/library", json={"description": "first"}).json()
    monkeypatch.setattr(main.library, "save", real)
    mine = [x for x in library.all_entries() if x["owner"] == "user-1"]
    linked = api.get(f"/notebooks/{nid}").json()["experiments"][0]["library"]
    assert [x["id"] for x in mine] == [linked] == [first["id"]]


def test_refreshing_a_link_keeps_a_new_one_made_meanwhile(api, store, monkeypatch):
    nid, _ = _published(api)
    old = api.post(f"/notebooks/{nid}/experiments/1/share", json={}).json()["token"]
    real = main.public.publish

    def racing(nb, exp, image):
        mine = real(nb, exp, image)
        nb2 = main.get_notebook({"id": "user-1"}, nid)                # another tab turned it off and on again
        nb2["experiments"][0]["public"] = "newer-token"
        main.save_notebook({"id": "user-1"}, nb2)
        return mine
    monkeypatch.setattr(main.public, "publish", racing)
    assert api.post(f"/notebooks/{nid}/experiments/1/share", json={}).json()["token"] == "newer-token"
    assert main.public.load(old) is None


def test_a_stratlab_author_spelt_with_cyrillic_look_alikes_is_refused(api, store):
    """acct4: "Strаtlаb" (Cyrillic а) and "Ѕtratlab" (Cyrillic Ѕ) read as StratLab; a name in another script is fine."""
    nid, _ = _published(api)
    for name in ("Strаtlаb", "Ѕtratlab", "STRАTLАB fan"):
        r = api.post(f"/notebooks/{nid}/experiments/1/library", json={"author": name})
        assert r.status_code == 400 and r.json()["detail"]["code"] == "author_reserved", name
    for name in ("Пётр", "Strategy Lab"):
        assert api.post(f"/notebooks/{nid}/experiments/1/library", json={"author": name}).status_code == 200, name
