"""Release 25 (the owner's outside review of the R23 decks, classification lowest: "avoid grouping businesses with fundamentally different revenue
models just because they belong to the same broad theme"): every company carries its revenue model from the placement answer (kept with the map),
a layer holds one way of earning (outliers move to the layer of their model, or a new layer named by it), no catch-all above 40% when a split is
possible, "Other" only for what the evidence can't place, and each layer's page says in one line what its companies have in common. Generic:
every synthetic theme, India and the US; synthetic data only, no figure or name tuned to a real company."""
import copy

import pytest

from app.intel import ai as A
from app.intel import theme_base as B
from app.intel import theme_check as C
from tests.test_export import texts
from tests.test_r17_fixes import theme_a, theme_b
from tests.test_r18_deck import bank_theme, deck_of, maker_theme, us_list_theme
from tests.test_r20_deck import (it_theme, long_theme, nbfc_theme, pharma_actions, pharma_theme, sparse_theme, us_map_theme,
                                 test_every_rule_holds_on_every_synthetic_theme as every_rule)
from tests.test_theme1 import facts


def co(sym, name, what="", industry="Computers - Software & Consulting", base=True, verified=True, cap=None):
    c = {"ticker": sym, "name": name, "what": what, "industry": industry, "base": base, "basis": "industry" if base else "added", "verified": verified}
    return {**c, "cap": cap} if cap is not None else c


# ---------- an IT-services-like theme: a hardware reseller and a software-product firm mixed into services ----------
def it_mixed():
    """India, the shape of the live IT services map: an outsourcer layer, an 18-company "mid-tier" catch-all with a hardware reseller and a
    software-product firm in it, a cloud layer mixing data-centre operators and hardware resellers, a software layer, and companies the map
    didn't place (one a server maker, one with no description)."""
    out = [co(f"OS{i}", f"Outsource {i} Ltd", "runs applications and back offices for banks under multi-year contracts", cap=900000 - i * 90000) for i in range(5)]
    mid = [co(f"PJ{i:02d}", f"Digital {i} Ltd", "builds digital and cloud systems for clients on projects", cap=60000 - i * 2000) for i in range(10)]
    mid += [co(f"MG{i}", f"Ops {i} Ltd", "runs clients' infrastructure under managed service contracts", cap=45000 - i * 2000) for i in range(6)]
    mid += [co("HW1", "Boxline Ltd", "resells and installs servers, storage and networking equipment of global brands", cap=30000),
            co("SW1", "Codeset Ltd", "sells licences and subscriptions for its own banking software", cap=28000)]
    cloud = [co("DC1", "Rackhouse Ltd", "rents out data-centre and GPU capacity", cap=20000), co("HW2", "Kitwise Ltd", "resells computer hardware", cap=18000),
             co("DC2", "Hostgrid Ltd", "runs cloud hosting and colocation", cap=9000), co("HW3", "Partsmart Ltd", "distributes and installs hardware", cap=7000)]
    soft = [co(f"SP{i}", f"Product {i} Ltd", "sells subscriptions for its own software", cap=40000 - i * 5000) for i in range(3)]
    rest = [co("SV1", "Servermake Ltd", "designs and makes its own servers", cap=8000), co("PJX", "Projectly Ltd", "delivers IT projects for clients", cap=5000),
            co("NOD", "Quiet Ltd", "", cap=1000)]
    m = {"sector": "IT services", "summary": "Software and IT services.", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
         "value_chain": [{"layer": "Large diversified outsourcers", "description": "Run clients' technology for years at a time.", "companies": out},
                         {"layer": "Mid-tier digital and cloud specialists", "description": "Mid-sized digital firms.", "companies": mid},
                         {"layer": "Cloud, AI infrastructure and hardware", "description": "Computing capacity and hardware.", "companies": cloud},
                         {"layer": "Software products and platforms", "description": "Own software sold to companies.", "companies": soft},
                         {"layer": "Other IT service companies", "official": True, "basis": "rest", "description": "",
                          "companies": [{**c, "placed": "ai"} for c in rest]}],
         "placements": {"checked": True, "pending": 0, "placed": 41, "total": 41, "base": 41, "named": 0, "added": 0, "confirmed": 0,
                        "industries": ["Computers - Software & Consulting"]}}
    models = {**{f"OS{i}": "managed_services" for i in range(5)}, **{f"PJ{i:02d}": "project_services" for i in range(10)},
              **{f"MG{i}": "managed_services" for i in range(6)}, "HW1": "hardware_resale", "SW1": "software", "DC1": "capacity", "HW2": "hardware_resale",
              "DC2": "capacity", "HW3": "hardware_resale", **{f"SP{i}": "software" for i in range(3)}, "SV1": "manufacturing", "PJX": "project_services",
              "NOD": "unknown"}
    f = {}
    for i, c in enumerate(c for v in m["value_chain"] for c in v["companies"]):
        f[c["ticker"]] = facts(c["ticker"], c["name"], [900, 1000, 1100, 1200 + i * 10], [18, 18, 19, 19 + (i % 5)], [90, 100, 110, 120 + i],
                               cap=c.get("cap") or 1000, pe=25.0, roce=20.0 + i % 7)
    return "IN", m, f, models


def layers_of(vc):
    return {v["layer"]: sorted(c["ticker"] for c in v["companies"]) for v in vc}


def test_it_services_mixed_layers_are_split_by_how_they_earn():
    _, m, _, models = it_mixed()
    before = layers_of(m["value_chain"])
    vc = B.by_model(m["value_chain"], {s: x for s, x in models.items() if x in C.MODELS}, "IT services")
    after = layers_of(vc)
    # the reseller and the software firm leave the services catch-all; the cloud layer keeps its data centres, its resellers join HW1
    assert after["Hardware resale and integration"] == ["HW1", "HW2", "HW3"]
    assert after["Cloud, AI infrastructure and hardware"] == ["DC1", "DC2"]
    assert after["Software products and platforms"] == ["SP0", "SP1", "SP2", "SW1"]
    # "Other" keeps the company the evidence can't place; R27 (changed on purpose): the server maker, alone in its model, joins "Other" instead
    # of a one-company layer; the project firm joins services
    assert after["Other IT service companies"] == ["NOD", "SV1"] and "Makers of their own products" not in after
    # the 18-company catch-all (over 40% of the theme) is split by model: project firms and managed-service firms apart
    assert after["Mid-tier digital and cloud specialists"] == sorted([f"PJ{i:02d}" for i in range(10)] + ["PJX"])
    # R31 (changed on purpose: no two layers of one primary model): the managed-service firms split out of the catch-all join the map's own
    # layer of managed services instead of a second "Managed and outsourced IT services" layer
    assert "Managed and outsourced IT services" not in after
    assert after["Large diversified outsourcers"] == sorted([f"MG{i}" for i in range(6)] + [f"OS{i}" for i in range(5)])
    total = sum(len(x) for x in after.values())
    assert total == sum(len(x) for x in before.values())                                 # nobody lost or doubled
    assert all(len(x) <= 0.4 * total for k, x in after.items())
    # one family a layer, and each says what its companies have in common
    for v in vc:
        fams = {C.model_family(models.get(c["ticker"])) for c in v["companies"]} - {""}
        assert len(fams) <= 1, (v["layer"], fams)
        if not v.get("official"):
            assert v["model"]["line"].startswith("They earn mainly from"), v["layer"]
    hw = next(v for v in vc if v["layer"] == "Hardware resale and integration")
    assert hw["model"]["line"] == "They earn mainly from selling and installing hardware that others make." and not hw.get("official")
    # the "Other" group stays last
    assert vc[-1]["layer"] == "Other IT service companies"


def test_before_and_after_layer_list_for_the_report():
    _, m, _, models = it_mixed()
    vc = B.by_model(m["value_chain"], models, "IT services")
    assert [(v["layer"], len(v["companies"])) for v in m["value_chain"]] == [
        ("Large diversified outsourcers", 5), ("Mid-tier digital and cloud specialists", 18), ("Cloud, AI infrastructure and hardware", 4),
        ("Software products and platforms", 3), ("Other IT service companies", 3)]
    assert [(v["layer"], len(v["companies"])) for v in vc] == [
        ("Large diversified outsourcers", 11), ("Mid-tier digital and cloud specialists", 11),
        ("Cloud, AI infrastructure and hardware", 2), ("Software products and platforms", 4), ("Hardware resale and integration", 3),
        ("Other IT service companies", 2)]          # R27: no one-company layer, the server maker is in "Other"; R31 (on purpose): the managed-
    #                                                 service firms join the map's own managed-services layer


def test_a_catch_all_of_one_model_is_split_by_market_value():
    big = [co(f"P{i:02d}", f"Proj {i} Ltd", cap=1000 - i * 10) for i in range(12)]
    vc = [{"layer": "Digital specialists", "description": "", "companies": big},
          {"layer": "Products", "description": "", "companies": [co(f"S{i}", f"Soft {i}", cap=50) for i in range(4)]}]
    models = {**{c["ticker"]: "project_services" for c in big}, **{f"S{i}": "software" for i in range(4)}}
    out = B.by_model(vc, models, "IT services")
    names = [v["layer"] for v in out]
    assert names == ["Digital specialists (larger)", "Digital specialists (smaller)", "Products"]
    assert [c["ticker"] for c in out[0]["companies"]] == [f"P{i:02d}" for i in range(6)]
    assert "the other half is “Digital specialists (smaller)”" in out[0]["model"]["line"]
    # a small layer, or one too small to halve, is left alone
    small = [{"layer": "Digital specialists", "description": "", "companies": big[:5]}, vc[1]]
    assert [v["layer"] for v in B.by_model(small, models, "IT services")] == ["Digital specialists", "Products"]


def test_no_model_known_or_no_layers_of_its_own_leaves_the_map_as_it_is():
    _, m, _, models = it_mixed()
    assert B.by_model(m["value_chain"], {}, "IT services") == m["value_chain"]
    official = [{**v, "official": True, "basis": "industry"} for v in m["value_chain"][:2]]
    assert B.by_model(official, models, "IT services") == official


# ---------- the placement answer carries the models, asked once a map ----------
def test_the_models_come_with_the_one_placement_answer_and_are_kept_with_it():
    _, m, _, models = it_mixed()
    todo = [{**c, "base": True} for c in m["value_chain"][-1]["companies"]]
    mapped = {**m, "value_chain": m["value_chain"][:4] + [{"layer": "Computers - Software & Consulting", "official": True, "basis": "industry",
                                                           "description": "", "companies": todo}]}
    asked = []

    named = []

    def ask(system, text):
        if system == C.NAMES_SYSTEM:              # R26: the layers the split reshaped get the name check once (changed on purpose: a second call)
            named.append(text)
            return {"rename": []}
        asked.append(text)
        assert "4. MODEL" in system and "hardware_resale" in system and "HW1 · Boxline Ltd" in text
        return {"place": [{"symbol": "PJX", "layer": "L1"}, {"symbol": "SV1", "layer": "none"}, {"symbol": "NOD", "layer": "none"}], "rename": [], "extra": [],
                "models": {**models, "ZZZ": "software", "SP0": "made-up"}}                      # a symbol not asked and a model off the list: dropped
    out, got = B.place_rest(mapped, "IT services", lambda s: None, ask=ask)
    assert len(asked) == 1 and len(named) == 1 and "ZZZ" not in got["models"] and "SP0" not in got["models"] and got["models"]["HW1"] == "hardware_resale"
    names = [v["layer"] for v in out["value_chain"]]
    assert "Hardware resale and integration" in names and names[-1] == "Other IT service companies"
    again, got2 = B.place_rest(mapped, "IT services", lambda s: None, ask=lambda s, t: pytest.fail("asked again"), kept=got)
    assert again == out and got2 == got                                                         # kept: never asked again for this map
    plain, _ = B.place_rest(mapped, "IT services", lambda s: None)                              # no AI and nothing kept: no split
    assert "Hardware resale and integration" not in [v["layer"] for v in plain["value_chain"]]


def test_a_placement_kept_from_before_the_models_asks_once_for_them():
    _, m, _, models = it_mixed()
    calls = []
    first, got = B.place_rest(m, "IT services", lambda s: None, ask=lambda s, t: calls.append(t) or {"place": [], "rename": [], "extra": []})
    old = {k: v for k, v in got.items() if k != "models"}                                       # an answer kept before R25
    out, got2 = B.place_rest(m, "IT services", lambda s: None, ask=lambda s, t: calls.append(t) or {"models": models}, kept=old)
    # changed on purpose (R26): the models' ask, then the name check of the layers the split reshaped (each kept with the map)
    assert len(calls) == 3 and got2["models"] and got2["model_names"]["rename"] == {} and "Hardware resale and integration" in [v["layer"] for v in out["value_chain"]]


def test_place_in_layers_reads_models_as_a_list_too():
    layers = [{"layer": "A", "companies": [{"ticker": "X1", "name": "X one"}]}]
    ans = C.place_in_layers(layers, [{"symbol": "Y1", "name": "Y one"}], lambda s, t: {"models": [{"symbol": "X1", "model": "lending"},
                                                                                            {"symbol": "Y1", "model": "unknown"}]}, "Banks")
    assert ans["models"] == {"X1": "lending"}


def test_the_prompts_ask_for_one_way_of_earning_a_layer_and_old_maps_are_written_again():
    src = open(A.__file__).read()
    assert "The companies of a layer earn the same way" in src and "no catch-all layer" in src
    assert A.MAP_V >= 23 and A.map_due({"generated_at": 5.0, "map_v": 22}) and B.RULES >= 25
    assert "how they earn" in C.PLACE_SYSTEM2 and "Never a catch-all name" in C.PLACE_SYSTEM2
    assert all(len(x) == 3 and x[0] for x in C.MODELS.values()) and set(C.FAMILIES) <= {x[0] for x in C.MODELS.values()}


# ---------- the deck says what each layer has in common; every rule still holds ----------
def test_the_deck_states_each_layers_revenue_model_in_one_line():
    region, m, f, models = it_mixed()
    m = {**m, "value_chain": B.by_model(m["value_chain"], models, "IT services")}
    v, slides = deck_of(region, m, f)
    t = texts(slides)
    assert "In common: they earn mainly from selling and installing hardware that others make." in t
    assert "In common: they earn mainly from fees for projects and time worked for clients." in t
    for s in slides:
        if s.title.startswith("Layer ") and "Other IT service" not in s.title:
            card = next(b for b in s.blocks if b["kind"] == "cards")
            assert any(str(x).startswith("In common: ") for x in card["items"][0]["lines"]), s.title
    every_rule("IT services, split by model (IN)", v, slides)


ODD = {"lending": "manufacturing", "underwriting": "manufacturing"}             # an outlier's model: hardware resale unless the layer resells


def synthetic():
    yield "packaging (IN)", theme_a(), {}
    yield "payments (US, one layer)", theme_b(), {}
    yield "private banks (IN)", bank_theme()[:3], {}
    yield "US list, by industry", us_list_theme(), {}
    yield "US list, one industry", us_list_theme(False), {}
    yield "makers (IN)", maker_theme(), {}
    yield "NBFC and insurers (IN)", nbfc_theme(), {}
    yield "IT services (IN)", it_theme(), {}
    yield "pharma, a demerger (IN)", pharma_theme(), {"corp_history": pharma_actions}
    yield "US, AI map of 5 layers", us_map_theme(), {}
    yield "most without figures (IN)", sparse_theme(), {}
    yield "60 companies (IN)", long_theme(), {}
    r, m, f, _ = it_mixed()
    yield "IT services, mixed (IN)", (r, m, f), {}


POOL = ["manufacturing", "lending", "software", "project_services", "underwriting", "capacity", "distribution"]


@pytest.mark.parametrize("name,theme,kw", list(synthetic()), ids=[n for n, _, _ in synthetic()])
def test_on_every_synthetic_theme_an_outlier_moves_out_and_every_rule_still_holds(name, theme, kw):
    region, m, f = copy.deepcopy(theme)
    own = [v for v in m["value_chain"] if not v.get("official")]
    # each layer of the map earns one way (synthetic: one model a layer), then a company that earns another way is put in the largest layer
    models = {c["ticker"]: POOL[i % len(POOL)] for i, v in enumerate(own) for c in v["companies"]}
    if own:
        big = max(own, key=lambda v: len(v["companies"]))
        first = big["companies"][0]
        odd_model = ODD.get(models[first["ticker"]], "hardware_resale")
        big["companies"].append({**first, "ticker": "ODD1", "name": "Oddline Trading Ltd", "what": "resells equipment made by others"})
        f["ODD1"] = {**f[first["ticker"]], "symbol": "ODD1", "name": "Oddline Trading Ltd"}
        models["ODD1"] = odd_model
    vc = B.by_model(m["value_chain"], models, m.get("sector") or name)
    if not own:
        assert vc == m["value_chain"]                    # the exchange's industries only (no map of its own): nothing to split by model
    else:
        home = next(v for v in vc if "ODD1" in [c["ticker"] for c in v["companies"]])
        assert home["layer"] != big["layer"]
        if home.get("official"):        # R27 (changed on purpose): alone in its family, the outlier joins "Other", never a one-company layer
            assert home.get("basis") == "rest" and next(c for c in home["companies"] if c["ticker"] == "ODD1")["single"]
        else:
            assert C.model_family(models["ODD1"]) == home["model"]["family"]
        assert not any(len(v["companies"]) == 1 and v.get("by_model") for v in vc)
        total = sum(len(v["companies"]) for v in vc)
        for v in vc:
            fams = {C.model_family(models.get(c["ticker"])) for c in v["companies"]} - {""}
            assert len(fams) <= 1, (v["layer"], fams)
            if not v.get("official") and v["companies"]:
                assert v.get("model"), v["layer"]
                n = len(v["companies"])
                one = len({models.get(c["ticker"]) for c in v["companies"]}) == 1
                assert not (n > 0.4 * total and n >= B.SPLIT_MIN and not one and n // 2 >= B.SPLIT_PART) or v.get("scale"), (v["layer"], n, total)
    m["value_chain"] = vc
    v, slides = deck_of(region, m, f, **kw)
    every_rule(name, v, slides)
    if own:
        assert "In common: they earn mainly from" in texts(slides)


# ---------- a layer named by a stand-in ("placeholder" in the live R24 Insurance map) is nameless ----------
@pytest.mark.parametrize("name", ["placeholder", "Placeholder.", "PLACE-HOLDER", "TBD", "t.b.d.", "N/A", "n.a.", "unknown", "None", "Layer", "Layer 1",
                                  "layer-2", "Segment", "Segment B", "Example", "misc.", "Miscellaneous", "  ", "3", "Other", "Untitled", "XXX"])
def test_a_stand_in_layer_name_is_no_name(name):
    assert A.stand_in(name) and A.layer_name({"layer": name}) == ""


def test_real_layer_names_are_kept_and_a_stand_in_layer_is_dropped_everywhere():
    for real in ("Life insurers", "General insurers", "Insurance brokers", "Unknown-risk specialty underwriters", "Segment reporting software",
                 "Other services", "Layer 1 chip designers", "Reinsurance"):
        assert not A.stand_in(real) and A.layer_name({"layer": real}) == real, real
    assert A.layer_name({"layer": "placeholder", "name": "Health insurers"}) == "Health insurers"    # the name under another key is used
    # a map kept in the store from before: the stand-in layer is dropped, its companies placed as any the AI didn't name
    rows = [{"symbol": s, "name": s, "industry": "Life Insurance", "market_cap": 100} for s in ("LI1", "LI2", "LI3")]
    m = {"sector": "Insurance", "sub_themes": [], "value_chain": [
        {"layer": "Life insurers", "description": "x", "companies": [{"ticker": "LI1", "name": "LI1", "verified": True}]},
        {"layer": "Placeholder", "description": "", "companies": [{"ticker": "LI2", "name": "LI2", "verified": True}]},
        {"layer": "TBD", "description": "", "companies": []}]}
    out = B.with_base(m, m, rows, ["Life Insurance"])
    names = [v["layer"] for v in out["value_chain"]]
    assert not any(A.stand_in(n) for n in names) and "LI2" in {c["ticker"] for v in out["value_chain"] for c in v["companies"]}
    # the placement answer never renames a layer to a stand-in or proposes one
    ans = C.place_in_layers([{"layer": "Life insurers", "companies": []}], [{"symbol": "A1", "name": "A"}, {"symbol": "A2", "name": "B"}],
                            lambda s, t: {"place": [{"symbol": "A1", "layer": "none"}, {"symbol": "A2", "layer": "none"}],
                                          "rename": [{"layer": "L0", "name": "N/A", "description": "x"}],
                                          "extra": [{"name": "placeholder", "symbols": ["A1", "A2"]}]}, "Insurance")
    assert ans["rename"] == {} and ans["extra"] == []
