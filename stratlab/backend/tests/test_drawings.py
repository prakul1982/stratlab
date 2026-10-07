"""Chart drawings saved per user, region and symbol: GET/PUT /me/drawings/{region}/{symbol}. Auth, validation, the size
limit, privacy between users, the layout, the older chart's drawings carried over, and delete."""
import json

import pytest

from app import chart_data as CD, db
from app import drawings_store as DS
from tests import world

PRO = world.headers("pro-token")
FREE = world.headers("free-token")
URL = "/me/drawings/IN/RELIANCE"


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def pt(t=1_700_000_000_000, p=100.0):
    return {"t": t, "p": p}


def trend(i="d1", **extra):
    return {"id": i, "kind": "trend", "points": [pt(), pt(1_710_000_000_000, 120)], **extra}


def long_pos(i="p1"):
    return {"id": i, "kind": "long", "points": [pt(p=100), pt(1_700_900_000_000, 110), pt(1_700_900_000_000, 95)], "risk": 5000}


def test_needs_a_signed_in_user(w):
    c = w["client"]
    assert c.get(URL).status_code == 401
    assert c.put(URL, json={"drawings": []}).status_code == 401
    assert c.delete(URL).status_code == 401
    assert c.delete("/me/drawings").status_code == 401


def test_save_and_read_back_per_user_region_and_symbol(w):
    c = w["client"]
    assert c.get(URL, headers=PRO).json() == {"region": "IN", "symbol": "RELIANCE", "drawings": [], "layout": None, "updated_at": None}
    layout = {"tf": "1h", "range": "1M", "type": "heikin", "volume": False,
              "studies": [{"id": "s1", "type": "sma", "params": [50], "slot": 0}]}
    saved = c.put(URL, headers=PRO, json={"drawings": [trend(), long_pos(), {"id": "n1", "kind": "text", "text": "Note", "color": "magenta",
                                                                             "dash": "dashed", "locked": True, "points": [pt()]}], "layout": layout}).json()
    assert [d["kind"] for d in saved["drawings"]] == ["trend", "long", "text"] and saved["updated_at"]
    got = c.get(URL, headers=PRO).json()
    assert got["drawings"][1]["risk"] == 5000 and got["drawings"][2]["locked"] is True and got["drawings"][2]["color"] == "magenta"
    assert got["layout"]["tf"] == "1h" and got["layout"]["studies"][0]["params"] == [50.0]
    # case-insensitive, and another region or symbol or user does not see it
    assert c.get("/me/drawings/in/reliance", headers=PRO).json()["drawings"][0]["id"] == "d1"
    assert c.get("/me/drawings/US/RELIANCE", headers=PRO).json()["drawings"] == []
    assert c.get("/me/drawings/IN/INFY", headers=PRO).json()["drawings"] == []
    assert c.get(URL, headers=FREE).json()["drawings"] == []
    # a later save replaces
    c.put(URL, headers=PRO, json={"drawings": [trend("d2")]})
    assert [d["id"] for d in c.get(URL, headers=PRO).json()["drawings"]] == ["d2"]
    assert c.get(URL, headers=PRO).json()["layout"] is None


def test_empty_save_removes_the_row(w):
    c = w["client"]
    c.put(URL, headers=PRO, json={"drawings": [trend()]})
    assert any(k.startswith(DS.KEY) for k in _keys())
    c.put(URL, headers=PRO, json={"drawings": []})
    assert not any(k.startswith(DS.KEY) for k in _keys())
    assert c.get(URL, headers=PRO).json()["drawings"] == []
    c.put(URL, headers=PRO, json={"drawings": [], "layout": {"tf": "1d"}})        # a layout alone is kept
    assert c.get(URL, headers=PRO).json()["layout"]["tf"] == "1d"


def _keys():
    rows = db.sb().table("app_settings").select("key").execute().data
    return [r["key"] for r in rows]


@pytest.mark.parametrize("bad", [
    {"id": "x", "kind": "nope", "points": [pt()]},                                          # unknown kind
    {"id": "x", "kind": "trend", "points": [pt()]},                                         # a trend line needs two points
    {"id": "x", "kind": "hline", "points": [pt(), pt()]},                                   # a level needs one
    {"id": "x", "kind": "long", "points": [pt(), pt()]},                                    # a position needs three
    {"id": "x", "kind": "brush", "points": [pt()]},                                         # a stroke needs two
    {"id": "x", "kind": "hline", "points": []},
    {"id": "bad id!", "kind": "hline", "points": [pt()]},                                   # odd characters
    {"id": "", "kind": "hline", "points": [pt()]},
    {"id": "x", "kind": "hline", "points": [{"t": 1, "p": "abc"}]},
    {"id": "x", "kind": "hline", "points": [{"t": 1e300, "p": 1}]},
    {"id": "x", "kind": "hline", "points": [pt()], "color": "#ff0000"},                     # only the palette
    {"id": "x", "kind": "hline", "points": [pt()], "dash": "wavy"},
    {"id": "x", "kind": "text", "points": [pt()], "text": "y" * 201},
    {"id": "x", "kind": "long", "points": [pt(), pt(), pt()], "risk": -5},
    {"id": "x", "kind": "<img src=x>", "points": [pt()]},
])
def test_odd_drawings_are_refused(w, bad):
    r = w["client"].put(URL, headers=PRO, json={"drawings": [bad]})
    assert r.status_code == 422, r.text
    assert w["client"].get(URL, headers=PRO).json()["drawings"] == []


def test_non_finite_numbers_are_refused(w):
    c = w["client"]
    for t in ("NaN", "Infinity", "-Infinity"):
        raw = '{"drawings":[{"id":"x","kind":"hline","points":[{"t":%s,"p":1}]}]}' % t
        r = c.put(URL, headers={**PRO, "Content-Type": "application/json"}, content=raw)
        assert r.status_code == 422, t


def test_layout_is_validated(w):
    c = w["client"]
    for layout in ({"tf": "2m"}, {"range": "7Y"}, {"type": "renko"}, {"volume": "maybe"},
                   {"studies": [{"id": "s", "type": "magic", "params": [1]}]},
                   {"studies": [{"id": "s", "type": "sma", "params": [1, 2, 3, 4, 5]}]},
                   {"studies": [{"id": f"s{i}", "type": "sma", "params": [20]} for i in range(13)]}):
        assert c.put(URL, headers=PRO, json={"drawings": [], "layout": layout}).status_code == 422, layout


def test_limits(w):
    c = w["client"]
    many = [{"id": f"d{i}", "kind": "hline", "points": [pt(p=i + 1)]} for i in range(DS.MAX_DRAWINGS + 1)]
    assert c.put(URL, headers=PRO, json={"drawings": many}).status_code == 422                 # too many drawings
    full = [{"id": f"d{i}", "kind": "hline", "points": [pt(p=i + 1)]} for i in range(DS.MAX_DRAWINGS)]
    assert c.put(URL, headers=PRO, json={"drawings": full}).status_code == 200                   # the most is fine
    strokes = [{"id": f"b{i}", "kind": "brush", "points": [pt(1_700_000_000_000 + j * 86_400_000, 100 + j * 1.2345678901) for j in range(DS.MAX_POINTS)]}
               for i in range(20)]
    r = c.put(URL, headers=PRO, json={"drawings": strokes})                                      # 20 full strokes: past the size limit
    assert r.status_code == 413 and r.json()["detail"]["code"] == "drawings_too_big"
    assert len(c.get(URL, headers=PRO).json()["drawings"]) == DS.MAX_DRAWINGS                    # the earlier save is untouched
    long_stroke = {"id": "b", "kind": "brush", "points": [pt(1 + j, 1 + j) for j in range(DS.MAX_POINTS + 1)]}
    assert c.put(URL, headers=PRO, json={"drawings": [long_stroke]}).status_code == 422


def test_bad_region_or_symbol(w):
    c = w["client"]
    for path in ("/me/drawings/I/X", "/me/drawings/IN/a b", "/me/drawings/IN/%3Cscript%3E", "/me/drawings/1N/X",
                 "/me/drawings/IN/" + "x" * 41, "/me/drawings/IN/..%2Fx"):
        assert c.get(path, headers=PRO).status_code in (400, 404, 422), path
    assert c.get("/me/drawings/IN/M&M", headers=PRO).status_code == 200
    assert c.get("/me/drawings/IN/%5ENSEI", headers=PRO).json()["symbol"] == "^NSEI"


def test_drops_the_oldest_symbols_past_the_cap(w, monkeypatch):
    monkeypatch.setattr(DS, "MAX_SYMBOLS", 3)
    c = w["client"]
    for s in ("AAA", "BBB", "CCC", "DDD"):
        assert c.put(f"/me/drawings/IN/{s}", headers=PRO, json={"drawings": [trend()]}).status_code == 200
    assert c.get("/me/drawings/IN/AAA", headers=PRO).json()["drawings"] == []
    assert c.get("/me/drawings/IN/DDD", headers=PRO).json()["drawings"]


def test_older_chart_drawings_come_across(w):
    c = w["client"]
    c.put("/chart/drawings", headers=PRO, json={"symbol": "IN:RELIANCE", "items": [{"id": "old", "kind": "rect", "points": [pt(), pt(1_710_000_000_000, 90)]}]})
    assert c.get(URL, headers=PRO).json()["drawings"][0]["id"] == "old"
    c.put(URL, headers=PRO, json={"drawings": [trend()]})                    # once saved the new way, that wins
    assert [d["id"] for d in c.get(URL, headers=PRO).json()["drawings"]] == ["d1"]


def test_delete_one_symbol_and_everything(w):
    c = w["client"]
    for s in ("RELIANCE", "INFY"):
        c.put(f"/me/drawings/IN/{s}", headers=PRO, json={"drawings": [trend()]})
    c.put("/me/drawings/IN/INFY", headers=FREE, json={"drawings": [trend("f1")]})
    assert c.delete(URL, headers=PRO).json()["deleted"]
    assert c.get(URL, headers=PRO).json()["drawings"] == []
    assert c.get("/me/drawings/IN/INFY", headers=PRO).json()["drawings"]
    assert c.delete("/me/drawings", headers=PRO).json()["symbols"] == 1
    assert c.get("/me/drawings/IN/INFY", headers=PRO).json()["drawings"] == []
    assert c.get("/me/drawings/IN/INFY", headers=FREE).json()["drawings"][0]["id"] == "f1"        # someone else's stay
    mine = [k for k in _keys() if k.startswith((DS.KEY, DS.INDEX))]
    assert mine and all("u-pro" not in k for k in mine)                                        # only the other user's rows are left


def test_saving_is_rate_limited_per_user(w, monkeypatch):
    from app import drawings_routes
    monkeypatch.setattr(drawings_routes, "WRITES", 5)
    c = w["client"]
    codes = [c.put(URL, headers=PRO, json={"drawings": [trend()]}).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    assert c.put(URL, headers=FREE, json={"drawings": [trend()]}).status_code == 200


def test_kinds_match_the_older_clean_list_and_the_chart(w):
    assert set(DS.POINTS) | {"brush"} == set(DS.KINDS)
    assert {"trend", "hline", "ray", "rect", "fib", "text"} <= set(DS.KINDS)            # the first chart's kinds still load
    assert json.dumps(DS.COLORS)
    assert CD.MAX_DRAWINGS <= DS.MAX_DRAWINGS
