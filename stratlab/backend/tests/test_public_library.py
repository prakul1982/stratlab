"""StratLab's own library strategies, readable without an account (R5V-011): read only, official and not hidden, and
nothing of anyone else's."""
import pytest

from app import library, main
from tests.test_library import as_user, store  # noqa: F401  (fixtures and helper)
from tests.test_notebooks import api  # noqa: F401  (fixture)


def _entry(eid, owner="stratlab", official=True, **more):
    return {"id": eid, "name": f"Strategy {eid}", "question": "", "description": "Rules as tested.", "author": "StratLab" if official else "Asha",
            "market": "IN", "instrument": None, "group": {"id": "nifty50", "name": "NIFTY 50", "market": "IN", "maxOpen": 10, "members": [{"symbol": "TCS"}]},
            "tf": "1d", "side": "long", "range": None, "strategy": {"entry": [], "exit": []},
            "verdict": {"verdict": "luck", "headline": "Probably luck.", "summary": "Lost on unseen years.", "passed": 1, "total": 4, "checks": []},
            "stats": {"ret": 5.0, "buy_hold": 9.0, "mdd": -12.0, "trades": 40, "unseen": -3.0}, "published_at": "2026-10-01T00:00:00+00:00",
            "copies": 2, "owner": owner, "source": {"nid": "nb-secret", "v": 3}, "official": official, "badge": "StratLab" if official else None,
            "seed": {"slug": "x", "version": 1}, **more}


def test_visitors_see_only_stratlabs_own_published_strategies(api, store):
    library.save(_entry("seed-ema-nifty50"))
    library.save(_entry("seed-hidden-nifty50", hidden=True, hidden_by="admin"))
    library.save(_entry("user-made-1", owner="user-9", official=False))
    library.save(_entry("forged-flag-1", owner="user-9", official=True))        # an "official" flag on someone else's entry doesn't count
    main.app.dependency_overrides.pop(main.current_profile, None)               # no sign-in at all
    try:
        r = api.get("/public/library")
        q = api.get("/public/library", params={"q": "ema"})
        none = api.get("/public/library", params={"verdict": "edge"})
    finally:
        as_user("user-1")
    assert r.status_code == 200
    body = r.json()
    assert [e["id"] for e in body["entries"]] == ["seed-ema-nifty50"] and body["total"] == 1
    e = body["entries"][0]
    for private in ("owner", "source", "seed", "mine", "reported", "reports", "hidden", "hidden_by"):
        assert private not in e, private
    assert "user-9" not in r.text and "nb-secret" not in r.text and "Asha" not in r.text
    assert e["verdict"]["headline"] == "Probably luck." and e["strategy"] == {"entry": [], "exit": []}      # the rules and the verdict, as they came out
    assert r.headers["cache-control"].startswith("public")
    assert q.json()["total"] == 1 and none.json()["entries"] == []


def test_one_public_entry_is_read_only_and_only_for_stratlabs_own(api, store):
    library.save(_entry("seed-ema-nifty50"))
    library.save(_entry("seed-hidden-nifty50", hidden=True))
    library.save(_entry("user-made-1", owner="user-9", official=False))
    main.app.dependency_overrides.pop(main.current_profile, None)
    try:
        ok = api.get("/public/library/seed-ema-nifty50")
        gone = {g: api.get(f"/public/library/{g}").status_code for g in ("seed-hidden-nifty50", "user-made-1", "no-such-entry-1", "x")}
        writes = {u: getattr(api, m)(u).status_code for m, u in (("post", "/public/library/seed-ema-nifty50"), ("delete", "/public/library/seed-ema-nifty50"),
                                                                    ("post", "/public/library"), ("put", "/public/library/seed-ema-nifty50"))}
    finally:
        as_user("user-1")
    assert ok.status_code == 200 and ok.json()["name"] == "Strategy seed-ema-nifty50" and "owner" not in ok.json()
    assert set(gone.values()) == {404}, gone
    assert set(writes.values()) == {405}, writes


def test_the_library_behind_sign_in_is_unchanged(api, store):
    library.save(_entry("user-made-1", owner="user-9", official=False))
    library.save(_entry("seed-ema-nifty50"))
    assert api.get("/library").json()["total"] == 2          # signed in: everyone's, as before
    assert api.get("/library", params={"official": "true"}).json()["total"] == 1
