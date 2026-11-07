"""Release 23: the layer-name check reaches every stored theme (it runs once a map and its placements, even when nothing is left to place),
a map written under an older map prompt is written again once and then reused, and one money format (no decimal at 1,000 bn or more)."""
import pytest

from app import deck
from app.intel import ai as A
from app.intel import routes
from app.intel import theme_base as B
from app.intel import theme_routes as T


def fully_placed():
    """A map with layers of its own and nothing left to place, one layer's name not fitting what its companies do."""
    return {"sector": "Automotive", "sub_themes": [], "value_chain": [
        {"layer": "Raw materials and castings", "description": "Steel and rubber producers.",
         "companies": [{"ticker": "F1", "name": "Forge One", "what": "forges crankshafts and axle beams", "verified": True},
                       {"ticker": "F2", "name": "Forge Two", "what": "makes fasteners and precision forgings", "verified": True}]},
        {"layer": "Vehicle makers", "description": "Make cars and trucks.", "companies": [{"ticker": "V1", "name": "Car One", "what": "makes cars", "verified": True}]}]}


def test_a_map_with_nothing_left_to_place_still_has_its_layer_names_checked_once():
    asked = []

    def ask(system, text):
        asked.append(text)
        return {"place": [], "rename": [{"layer": "L0", "name": "Forgings and metal components", "description": "Forge and machine metal parts for vehicle makers."}],
                "extra": []}
    out, got = B.place_rest(fully_placed(), "Automotive", lambda s: None, ask=ask)
    assert len(asked) == 1 and "Forge One: forges crankshafts" in asked[0]                  # the members' own words go with the check
    assert [v["layer"] for v in out["value_chain"]] == ["Forgings and metal components", "Vehicle makers"] and out["value_chain"][0]["was"] == "Raw materials and castings"
    assert got["names_for"] and got["rename"]
    again, got2 = B.place_rest(fully_placed(), "Automotive", lambda s: None, ask=lambda s, t: pytest.fail("asked again"), kept=got)
    assert again == out and got2 == got                                                     # once a map and its placements
    moved = fully_placed()
    moved["value_chain"][1]["companies"].append({"ticker": "V2", "name": "Car Two", "verified": True})
    B.place_rest(moved, "Automotive", lambda s: None, ask=ask, kept=got)
    assert len(asked) == 2                                                                  # the members changed: checked again
    same, _ = B.place_rest(fully_placed(), "Automotive", lambda s: None)                    # no AI: the map's names kept
    assert same["value_chain"][0]["layer"] == "Raw materials and castings"


def test_the_check_is_kept_with_the_placements_in_the_shared_store(monkeypatch):
    import json
    from app import computed
    store = {}
    monkeypatch.setattr(computed, "get", lambda kind, key, count=True: {"value": store[(kind, json.dumps(key))]} if (kind, json.dumps(key)) in store else None)
    monkeypatch.setattr(computed, "put", lambda kind, key, value, **kw: store.__setitem__((kind, json.dumps(key)), value) or {"value": value})
    monkeypatch.setattr(T, "_about_reader", lambda region, names, limit=0: (lambda s: None))
    calls = []
    ask = lambda s, t: calls.append(1) or {"place": [], "rename": [{"layer": "L0", "name": "Forgings and metal components", "description": "x y."}], "extra": []}   # noqa: E731
    m = {"sector": "Automotive", "generated_at": 9.0}
    first = T.placed("IN", "Automotive", m, fully_placed(), ask=ask)
    second = T.placed("IN", "Automotive", m, fully_placed(), ask=ask)
    page = T.placed("IN", "Automotive", m, fully_placed(), ask=None)
    assert calls == [1] and first == second == page and first["value_chain"][0]["layer"] == "Forgings and metal components"


def test_a_map_from_an_older_prompt_is_written_again_once_then_reused(monkeypatch):
    old = {"sector": "Private banks", "generated_at": 5.0, "value_chain": [{"layer": n, "companies": [{"ticker": "B"}]} for n in
                                                                           ("Deposit gathering", "Retail lending", "Corporate banking", "Treasury")]}
    assert A.map_due(old) and A.map_due({**old, "map_v": A.MAP_V - 1}) and not A.map_due({**old, "map_v": A.MAP_V})
    started = []
    kept = {"map": old}
    monkeypatch.setattr(routes, "index_rows", lambda r: [])
    monkeypatch.setattr(routes.grounding, "looks_like_theme", lambda t, v: True)
    monkeypatch.setattr(routes.A, "peek", lambda kind, key: True)
    monkeypatch.setattr(routes, "ai_call", lambda profile, kind, key, ttl, refresh, build, gated=False: kept["map"])
    monkeypatch.setattr(routes.theme_routes, "later", lambda key, work, wait=None: started.append(key) or {"state": "running"})
    routes.sector_map({}, "IN", "Private banks", False)
    assert started == [("map", "IN", "private banks")]                                     # written again, in the background
    kept["map"] = {**old, "map_v": A.MAP_V}                                                 # the new map carries the prompt's version
    routes.sector_map({}, "IN", "Private banks", False)
    assert len(started) == 1                                                                # then reused


def test_one_money_format_no_decimal_at_a_thousand_billion_or_more():
    w = deck.whole_figures
    assert w("$1,947.2 bn beside $4,498.0 bn") == "$1,947 bn beside $4,498 bn"
    assert w("$999.5 bn, $12.5 bn, $1,000.5 bn, CAD 2,345.6 bn") == "$999.5 bn, $12.5 bn, $1,001 bn, CAD 2,346 bn"
    assert w("₹1,234.5 cr and ₹56.9 lakh cr") == "₹1,234.5 cr and ₹56.9 lakh cr"
    from tests.test_r20_deck import ALL
    import re
    for name, (_, slides) in ALL:
        from tests.test_export import texts
        assert not re.search(r"\d{1,3}(?:,\d{3})+\.\d+ (?:bn|billion)\b", texts(slides)), name
