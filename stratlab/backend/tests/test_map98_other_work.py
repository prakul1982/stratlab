"""map98 (owner, 27 Nov: "go"): the deck96 audit of the 54 live theme decks found off-theme companies the AI map placed in its own layers,
its check saying yes: Vulcan Materials (construction aggregates) and a uranium miner in Steel and metals, Paccar (trucks) among the railcar
makers, Dominion Energy (a utility) among the power equipment makers, airlines in Hotels and tourism, animal-health makers and Abbott in
Biotech. A company of one of the map's own layers whose own first business sentence states a principal business of another kind than the
theme's (or, of the theme's kind, than its layer's) is listed as describing other work, its sentence quoted, in no figure. The replay of the
rule on the 54 saved live dives moved those companies and no real member (Nucor, Steel Dynamics, Amgen, Vertex, Regeneron, Microsoft,
Oracle, Trinity, GNFC ...)."""
from app.intel import theme_base as B
from app.intel import theme_data as D
from tests.test_theme1 import TODAY, facts

# the companies' own first business sentences, as the saved live dives quote them
VMC = ("Vulcan Materials Company operates primarily in the U.S. and is the nation’s largest supplier of construction aggregates (mainly "
       "crushed stone, sand and gravel) and a major producer of aggregates-intensive downstream products")
UEC = "We are a uranium mining and development company"
NUE = ("Nucor is the largest steel producer in the United States, making structural steel, merchant bar steel, steel joist and deck and "
       "steel piling from recycled scrap")
PCAR = ("(1)The Truck segment includes the design, manufacture and distribution of high-quality, light-, medium- and heavy-duty commercial "
        "trucks")
RAIL = ("We design and manufacture a broad variety of railcar types for transportation of bulk commodities and containerized freight products "
        "primarily in North America")
DOM = "Dominion Energy’s mission is to provide the reliable, affordable and increasingly clean energy that powers its customers every day"
ZTS = ("Zoetis Inc., headquartered in Parsippany, New Jersey, is the largest producer of medicine and vaccinations for pets and livestock "
       "worldwide")
VRTX = ("We are a global biotechnology company that invests in scientific innovation to create transformative medicines for people with "
        "serious diseases, with a focus on specialty markets")
INDIGO = "Interglobe Aviation Ltd (Indigo) is India’s largest passenger airline operating as a low-cost carrier"


def test_a_principal_business_of_another_kind_than_the_theme_is_other_work():
    # Steel and metals: the aggregates supplier and the uranium miner the map placed in its layers describe other work; the steel maker
    # doesn't
    lay = "Specialty alloys, aggregates and nuclear fuel suppliers"
    o = D.other_principal("Steel and metals", lay, VMC)
    assert o and o["of"] == "theme" and o["kind"] == "construction aggregates", o
    assert D.other_principal("Steel and metals", "Mining and mineral exploration", UEC)["kind"] == "uranium mining"
    assert D.other_principal("Steel and metals", "Mini-mill steel, pipe and alloy makers", NUE) is None
    # the kind is the theme's own where the theme's name makes it so (a uranium miner in Nuclear and SMRs, aggregates in Building materials)
    assert D.other_principal("Nuclear and SMRs", "Uranium mining", UEC) is None
    assert D.other_principal("Building materials", "Aggregates", VMC) is None
    # Hotels and tourism: an airline; Biotech: an animal-health maker, never a biotechnology company
    assert D.other_principal("Hotels and tourism", "Airlines", INDIGO)["kind"] == "airline"
    assert D.other_principal("Airlines and travel", "Airlines and air charter operators", INDIGO) is None
    assert D.other_principal("Biotech", "Bioprocessing, animal health and mixed healthcare products", ZTS)["kind"] == "animal health"
    assert D.other_principal("Biotech", "Branded and generic drug portfolio makers", VRTX) is None


def test_a_principal_business_of_another_kind_than_the_layers_is_other_work():
    # Railroads and trucking: a truck maker in the railcar makers' layer; Electric utilities: a utility in the power equipment makers'
    rail = "Railcar and rail equipment suppliers and lessors"
    o = D.other_principal("Railroads and trucking", rail, PCAR)
    assert o and o["of"] == "layer" and o["kind"] == "truck making", o
    assert D.other_principal("Railroads and trucking", rail, RAIL) is None
    assert D.other_principal("Electric utilities", "Grid and power equipment makers", DOM)["of"] == "layer"
    assert D.other_principal("Electric utilities", "Regulated vertically integrated utilities", DOM) is None


def test_only_the_principal_business_counts_never_a_mention_and_no_words_never_remove():
    # the first thing its sentence names, never the last of a list, whom it sells to, or a later clause
    escorts = ("Escorts Ltd. is one of India’s leading engineering conglomerates engaged in the manufacturing of Agri-machinery, Construction & "
               "Material Handling Equipment and Railway Equipment")
    assert D.principal_kind(escorts) is None
    assert D.principal_kind("Valiant Communications Ltd manufactures communication equipment, primarily for power utilities") is None
    assert D.principal_kind("This segment develops, produces and markets commercial jet aircraft principally to the commercial airline "
                            "industry worldwide") is None
    assert D.principal_kind("We are a leading producer of commercial aircraft and offer a family of commercial jetliners designed to meet "
                            "the passenger and cargo requirements of airlines") is None
    # a sentence that says the theme's own work too stays the theme's
    assert D.other_principal("Indian Pharma", "Export-focused generic formulation makers",
                             "Sequent Scientific Limited provides a wide-ranging portfolio of animal health products, including APIs, as well "
                             "as analytical services to the pharmaceutical and life sciences industries") is None
    for theme, lay in (("Steel and metals", "Mining and mineral exploration"), ("Railroads and trucking", "Railcar and rail equipment suppliers")):
        assert D.other_principal(theme, lay, "") is None and D.other_principal(theme, lay, None) is None


def _dive(theme, layer, cos, what):
    rows = [{"symbol": s, "name": n, "industry": ind, "market_cap": cap} for s, n, ind, cap in cos]
    ai = {"sector": theme, "summary": "", "core": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 0,
          "value_chain": [{"layer": layer, "description": "",
                           "companies": [{"ticker": r["symbol"], "name": r["name"], "what": what[r["symbol"]], "verified": True} for r in rows]}]}
    m = B.with_base(ai, {**ai, "placements": {"checked": True, "pending": 0}}, rows, [])
    f = {r["symbol"]: {**facts(r["symbol"], r["name"], [500, 600, 700, 800 + i * 20], [20.0, 21.0, 22.0, 18.0 + i], [50, 60, 70, 80 + i],
                               cap=r["market_cap"], pe=12.0, industry=(r["industry"],)), "region": "US", "unit": "$ million",
                       "annual_form": "10-K", "annual_filed": "2026-02-01"}
         for i, r in enumerate(rows)}
    return D.build("US", theme, m, D.Sources(TODAY, facts=f.get, about=lambda s: what.get(s)))


STEEL = "Steel Works, Blast Furnaces & Rolling Mills (Coke Ovens)"


def _steel(what):
    return _dive("Steel and metals", "Steel makers and alloy suppliers",
                 [("NUE", "Nucor Corp", STEEL, 30000), ("STLD", "Steel Dynamics Inc", STEEL, 20000), ("CLF", "Cleveland-Cliffs Inc", STEEL, 6000),
                  ("VMC", "Vulcan Materials Co", STEEL, 35000)], what)


def _row(dive, sym):
    return next(c for v in dive["layers"] for c in v["companies"] if c["symbol"] == sym)


def test_the_dive_lists_it_with_its_sentence_in_no_figure_and_keeps_the_real_members():
    """Fails before: Vulcan Materials, filed with the steel makers and placed in the map's steel layer, counted in its figures and the theme's
    totals as description-verified."""
    what = {"NUE": NUE, "STLD": "Steel Dynamics is one of the largest domestic steel producers and metals recyclers in the United States",
            "CLF": "Cleveland-Cliffs is the largest flat-rolled steel producer in North America", "VMC": VMC}
    dive = _steel(what)
    vmc = _row(dive, "VMC")
    assert vmc["status"] == "unverified" and vmc["evidence"] == "not_confirmed", (vmc["status"], vmc["evidence"])
    assert vmc["calc"]["in"] is False and "construction aggregates" in vmc["calc"]["detail"], vmc["calc"]
    assert "own words describe other work" in vmc["theme"]["why"] and "nation’s largest supplier of construction aggregates" in vmc["theme"]["why"]
    assert vmc["other_work"]["kind"] == "construction aggregates" and vmc["other_work"]["of"] == "theme"
    # listed in its layer, never silently dropped; in none of its figures
    lay = next(v for v in dive["layers"] if any(c["symbol"] == "VMC" for c in v["companies"]))
    assert "VMC" in lay["unverified"] and "VMC" not in (lay.get("in_stats") or {})
    for s in ("NUE", "STLD", "CLF"):          # (guard) the steel makers stay, confirmed by their own words
        r = _row(dive, s)
        assert r["status"] != "unverified" and r["evidence"] == "description_verified" and r["calc"]["in"], (s, r["status"], r["calc"])
    # (guard) with no words of its own read it stays as it was: missing words never remove a member
    dive = _steel({**what, "VMC": ""})
    assert _row(dive, "VMC")["status"] != "unverified"


def test_a_truck_maker_in_the_railcar_makers_layer_is_in_none_of_its_figures():
    """Fails before: Paccar, a truck maker the map named from another industry, counted among the railcar makers."""
    rail = "Railroad Equipment"
    what = {"RAIL": RAIL, "TRN": "We operate industry-leading railcar leasing, manufacturing, and services businesses",
            "GBX": "Greenbrier designs, builds and markets freight railcars in North America and Europe", "PCAR": PCAR}
    dive = _dive("Railroads and trucking", "Railcar and rail equipment suppliers and lessors",
                 [("RAIL", "FreightCar America Inc", rail, 300), ("TRN", "Trinity Industries Inc", rail, 2500),
                  ("GBX", "Greenbrier Companies Inc", rail, 1500), ("PCAR", "Paccar Inc", "Motor Vehicles & Passenger Car Bodies", 55000)], what)
    p = _row(dive, "PCAR")
    assert p["status"] == "unverified" and p["evidence"] == "not_confirmed" and p["calc"]["in"] is False, (p["status"], p["evidence"], p["calc"])
    assert p["other_work"]["of"] == "layer" and p["other_work"]["kind"] == "truck making"
    assert "commercial trucks" in p["theme"]["why"] and "Railcar and rail equipment suppliers and lessors" in p["theme"]["why"]
    assert p["calc"]["label"].startswith("not confirmed in the theme")
    for s in ("RAIL", "TRN", "GBX"):          # (guard) the railcar makers stay
        assert _row(dive, s)["status"] != "unverified" and _row(dive, s)["calc"]["in"], s
