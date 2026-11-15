"""Lane r571x (Release 57.1): the 10 new live R57 themes (lanes11/r57-new-decks, deck_check r57new-deckcheck.txt) left their largest
companies out of their layers' figures as "insufficient evidence": Yum Brands and Restaurant Brands International in "Franchisors earning
royalties" ("its words don't state how it earns": the model list had no franchisor), Atmos Energy and its peers in "Regulated gas distribution
utilities", Enbridge in "Midstream pipelines and processing", Mahindra Logistics and TVS Supply Chain in "Contract logistics and supply
chain", Walt Disney in "Broadcast, cable networks and studios" ("read only weakly"), GE Aerospace and RTX ("read only weakly") and Honeywell
Aerospace ("different revenue model: makers of their own products") in "Engines and propulsion".

The decks print these companies' figures but not their stored words, and no placement input of these themes exists outside production
(lane g57: none fetched). So each case is built here in its live shape: the live layer's name, the live read where the deck states it,
and the company's business in the words its public profile uses. Generic rules; company names only here.
"""
import copy

from app.intel import theme_base as B
from app.intel import theme_check as C


def rows(vc) -> dict:
    return {c["ticker"]: (v, c) for v in vc for c in v["companies"]}


def place(layers, models, conf, ev, theme, previous=None):
    vc = [{"layer": n, "description": d, "companies": [{"ticker": s, "name": s, "industry": ind, **({"placed": "ai"} if s in ev else {})}
                                                       for s, ind in cos]} for n, d, cos in layers]
    models = dict(models)
    models, conf2 = B.models_from_layer(vc, models, dict(conf), lambda s: ev.get(s, ""))
    return rows(B.by_model(copy.deepcopy(vc), models, theme, confidence=conf2, evidence_of=lambda s: ev.get(s, ""), previous=previous))


def test_a_franchisor_is_a_way_of_earning_and_a_franchisors_layer_says_it():
    """Fails before: no model of the list was a franchisor's, so "Franchisors earning royalties" stated no way of earning, and Yum Brands and
    Restaurant Brands International, with no model read and words naming their brands, were left out as "its words don't state how it earns".
    Now the layer's name states franchising (models_from_layer gives it to a company whose words state no other way), and they are in its
    figures. A franchisor's own words state it too."""
    assert "franchising" in C.MODELS and C.model_from_words("Franchisors earning royalties") == "franchising"
    assert C.stated_model("Domino's is the largest pizza company in the world; nearly all of its stores are franchised stores run by "
                          "independent franchisees paying royalties and fees from franchisees.") == "franchising"
    ev = {"YUM": "Yum! Brands, Inc. is an American fast food corporation. It operates the brands KFC, Pizza Hut, Taco Bell and The Habit Burger Grill.",
          "QSR": "Restaurant Brands International Inc. is a Canadian-American multinational fast food holding company: Tim Hortons, Burger King, "
                 "Popeyes and Firehouse Subs.",
          "DPZ": "Domino's Pizza is a pizza restaurant chain operated largely by franchisees; a franchisor earning royalties.",
          "WING": "Wingstop is a franchisor of chicken wing restaurants."}
    got = place([("Franchisors earning royalties", "These companies license their brands to franchisees and earn royalties and fees.",
                  [("YUM", "Retail-Eating Places"), ("QSR", "Retail-Eating Places"), ("DPZ", "Retail-Eating Places"), ("WING", "Retail-Eating Places")]),
                 ("Company-operated restaurant chains", "Chains that run their own restaurants.",
                  [("CMG", "Retail-Eating Places"), ("CAVA", "Retail-Eating Places"), ("SG", "Retail-Eating Places")])],
                {"CMG": "retail", "CAVA": "retail", "SG": "retail"}, {"CMG": "high", "CAVA": "high", "SG": "high"},
                {**ev, "CMG": "Chipotle runs restaurants it owns.", "CAVA": "CAVA runs restaurants.", "SG": "Sweetgreen runs restaurants."},
                "Restaurants")
    for s_ in ("YUM", "QSR"):
        c = got[s_][1]
        assert c["model"] == "franchising" and "model_out" not in c, (s_, c)


def test_regulated_gas_utilities_pipelines_logistics_and_media_say_their_business_in_so_many_words():
    """Fails before: Atmos Energy ("one of the country's largest natural-gas-only distributors"), Enbridge ("pipelines that transport crude
    oil, liquids and natural gas"), Mahindra Logistics ("integrated third-party logistics (3PL) service provider"), TVS Supply Chain ("a
    global supply chain solutions provider") and Walt Disney ("an American multinational mass media and entertainment conglomerate") stated no
    way of earning in the words the rules read."""
    cases = {"regulated_utility": ["Atmos Energy Corporation is one of the country's largest natural-gas-only distributors, delivering natural "
                                   "gas to over 3 million distribution customers in eight states.",
                                   "New Jersey Resources is an energy services holding company providing regulated natural gas distribution services."],
             "transport": ["Enbridge Inc. is a North American energy infrastructure company that operates pipelines that transport crude oil, "
                           "liquids and natural gas.",
                           "Mahindra Logistics Ltd is an integrated third-party logistics (3PL) service provider, specialising in supply chain management.",
                           "TVS Supply Chain Solutions is a global supply chain solutions provider to automotive and industrial customers."],
             "media": ["The Walt Disney Company is an American multinational mass media and entertainment conglomerate with television networks, "
                       "film studios and streaming services."]}
    for md, texts in cases.items():
        for t in texts:
            assert C.stated_model(t) == md, (md, t)
    # never a maker that sells to them, nor a games company calling itself an entertainment company
    assert C.stated_model("Acme Ltd manufactures meters and valves for gas distribution utilities and electric utilities.") != "regulated_utility"
    assert C.stated_model("Playco is a mobile games entertainment company.") != "media"


def test_a_utility_with_no_read_is_in_its_layer_s_figures_by_the_layer_s_own_name():
    """Atmos Energy's shape on the live US Oil and gas deck: no model read, its peers too ("In the layer's calculations (1 of 7): National
    Grid"); the layer's name, "Regulated gas distribution utilities", now states the way, and its words say so."""
    ev = {"ATO": "Atmos Energy Corporation is one of the country's largest natural-gas-only distributors.",
          "NFG": "National Fuel Gas is a diversified energy company with utility and pipeline businesses.",
          "NJR": "New Jersey Resources provides regulated natural gas distribution services.",
          "NGG": "National Grid owns and operates electricity and gas networks.",
          "XOM": "Exxon Mobil explores for and produces crude oil and natural gas.", "CVX": "Chevron produces oil and gas.", "COP": "ConocoPhillips explores for oil."}
    got = place([("Regulated gas distribution utilities", "Utilities that distribute natural gas at regulated tariffs.",
                  [("ATO", "Natural Gas Distribution"), ("NFG", "Natural Gas Distribution"), ("NJR", "Natural Gas Distribution"),
                   ("NGG", "Electric & Other Services Combined")]),
                 ("Integrated oil majors", "Oil majors.", [("XOM", "Petroleum Refining"), ("CVX", "Petroleum Refining"), ("COP", "Crude Petroleum")])],
                {"NGG": "regulated_utility", "XOM": "resources", "CVX": "resources", "COP": "resources"},
                {"NGG": "high", "XOM": "high", "CVX": "high", "COP": "high"}, ev, "Oil and gas")
    for s_ in ("ATO", "NJR"):
        assert got[s_][1]["model"] == "regulated_utility" and "model_out" not in got[s_][1], s_


def test_a_maker_of_its_own_products_is_of_a_parts_makers_layer_s_kin_when_its_words_say_the_layer():
    """Fails before: GE Aerospace and RTX (read at low confidence as makers of their own products) and Honeywell Aerospace (read at medium)
    were left out of "Engines and propulsion", read as a layer of parts makers, its companies of several official industries. A maker and a
    parts maker are one kin of making; one whose own words say the layer's name is in its figures. One whose words say nothing of the layer
    stays out."""
    ev = {"SAE": "StandardAero makes and overhauls aircraft engine components for engine makers.",
          "P1": "Parts Inc makes engine parts and turbine components for aircraft engines.",
          "P2": "Blades Inc makes turbine blades and engine components.",
          "GE": "GE Aerospace designs and manufactures jet engines and propulsion systems for commercial and military aircraft.",
          "RTX": "RTX is an aerospace and defense company whose Pratt & Whitney business makes aircraft engines.",
          "HON": "Honeywell Aerospace makes aircraft engines, auxiliary power units, avionics and cockpit systems.",
          "TOY": "Toyco makes toys and games."}
    models = {"SAE": "components", "P1": "components", "P2": "components", "GE": "manufacturing", "RTX": "manufacturing", "HON": "manufacturing",
              "TOY": "manufacturing"}
    conf = {"SAE": "high", "P1": "high", "P2": "high", "GE": "low", "RTX": "low", "HON": "medium", "TOY": "medium"}
    got = place([("Engines and propulsion", "Makers of aircraft engines, turbines and propulsion parts.",
                  [("SAE", "Aircraft Engines & Engine Parts"), ("P1", "Aircraft Parts & Auxiliary Equipment"), ("P2", "Aircraft Parts & Auxiliary Equipment"),
                   ("GE", "Electronic & Other Electrical Equipment"), ("RTX", "Aircraft Engines & Engine Parts"), ("HON", "Aircraft Parts & Auxiliary Equipment"),
                   ("TOY", "Games, Toys & Children's Vehicles")]),
                 ("Aircraft maintenance services", "Repair and overhaul for airlines.",
                  [("AAR", "Services-Equipment Rental & Leasing"), ("VSE", "Services-Equipment Rental & Leasing"), ("FTAI", "Services-Equipment Rental & Leasing")])],
                {**models, "AAR": "project_services", "VSE": "project_services", "FTAI": "project_services"},
                {**conf, "AAR": "high", "VSE": "high", "FTAI": "high"},
                {**ev, "AAR": "AAR provides repair services for airlines.", "VSE": "VSE provides repair services.", "FTAI": "FTAI provides services."},
                "Aerospace and defense", previous={"HON": "Engines and propulsion"})       # held in its live layer, as on the live deck
    for s_ in ("GE", "RTX", "HON"):
        v, c = got[s_]
        assert v["layer"] == "Engines and propulsion" and "model_out" not in c, (s_, c)
    v, c = got["TOY"]
    assert v["layer"] != "Engines and propulsion" or c.get("model_out")
