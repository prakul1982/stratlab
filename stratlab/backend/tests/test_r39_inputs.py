"""R39: the owner's read of what a theme's placement reads (stored, nothing asked of the AI), so rule changes are replayed on exactly that."""
from app.intel import theme_base as B
from app.intel import theme_routes as T
from tests.test_research_api import api  # noqa: F401  (the research API on the fake sources)


def test_placement_inputs_is_for_the_owner_only(api):
    r = api.get("/research/theme-dive/placement-inputs?q=Utilities&region=IN")
    assert r.status_code == 403


def test_placement_inputs_returns_the_checked_map_the_kept_answer_and_each_stored_description(api, monkeypatch):
    from app import admin
    from app.intel import routes
    monkeypatch.setattr(admin, "is_admin", lambda profile: True)
    m = {"sector": "Utilities", "generated_at": 7.0, "value_chain": []}
    monkeypatch.setattr(routes, "theme_map", lambda profile, region, q: ("IN", "Utilities", m, None))
    vc = [{"layer": "Cable and wire makers", "companies": [{"ticker": "POLYCAB", "name": "Polycab", "model": "manufacturing"}]},
          {"layer": "Other", "official": True, "companies": [{"ticker": "X", "name": "X Ltd", "moved": True}]}]
    monkeypatch.setattr(T, "checked", lambda region, theme, mm, wait=False: {"value_chain": vc, "placements": {"checked": True}})
    monkeypatch.setattr(T, "_about_reader", lambda region, names, limit=0: (lambda s: {"POLYCAB": "makes cables and wires"}.get(s)))
    asked = []
    monkeypatch.setattr(T, "kept_placement", lambda region, theme, mm: (asked.append(theme) or {"assign": {"X": {"layer": "", "by": "ai"}}}, 38))
    r = api.get("/research/theme-dive/placement-inputs?q=Utilities&region=IN")
    assert r.status_code == 200
    d = r.json().get("data", r.json())
    assert d["rules"] == B.RULES and d["kept_version"] == 38 and d["kept"]["assign"]["X"]["layer"] == ""
    assert d["value_chain"][0]["companies"][0]["ticker"] == "POLYCAB" and d["placements"]["checked"] is True
    assert d["evidence"] == {"POLYCAB": "makes cables and wires", "X": None} and asked == ["Utilities"]


def test_kept_placement_names_the_version_it_found_the_answer_under(monkeypatch):
    from app import computed
    monkeypatch.setattr(computed, "get", lambda kind, key: {"value": {"assign": {"A": {}}}} if key[-1] == 37 else None)
    kept, v = T.kept_placement("IN", "Utilities", {"generated_at": 1.0})
    assert v == 37 and kept == {"assign": {"A": {}}}
    monkeypatch.setattr(computed, "get", lambda kind, key: None)
    assert T.kept_placement("IN", "Utilities", {"generated_at": 1.0}) == ({}, None)
