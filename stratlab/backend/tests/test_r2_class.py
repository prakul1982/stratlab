"""R37 lane r2 (the owner: the remaining clear misclassifications across all themes, fixed globally): checked on the 14 benchmark themes'
live shapes (tests/fixtures/themes_live: GET /research/sector on 11 Nov 2026) through the dive's path for kept models and the placement.
1. Real estate: HDFC Bank in "Home loan lenders" with no model is a lender; "Mall and retail property owners" holds one way of earning.
2. Consumer retail: propane distributors and online sellers out of "Apparel and fashion retail chains", each to the layer of its own kind
   of business (or "Other"), and no other theme reshuffled.
3. Semiconductors: packaging and test services (Amkor, ChipMOS, ASE) counted as contract makers, materials makers in a layer of their own;
   a chip company whose own words say it designs, makes and sells its chips is no fabless one.
4. Unknown models: a company whose own words state how it earns gets that model once they are read; one whose words don't stays unknown."""
import json

import pytest

from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_routes as TR
from tests import test_golden_classification as G
from tests.test_r1_semis import DROPPED, layer_of, replay, row_of

SEMI = "Industry: Semiconductors & Related Devices. "


# ---------- 1. Real estate ----------
def test_a_bank_with_no_model_is_a_lender_in_every_theme():
    assert G.classify(G.company("realty", "HDFCBANK")) == ("lending", "")              # the live map's "Home loan lenders" layer
    for industry in ("Private Sector Bank", "Public Sector Bank", "National Commercial Banks", "Housing Finance Company", "Savings Institution, Federally Chartered"):
        assert C.refine_model("unknown", f"Industry: {industry}.") == "lending", industry
    assert C.refine_model("unknown", "Industry: Investment Banking. An investment bank advising on deals.") == "unknown"   # fees, not interest
    assert C.refine_model("software", "Industry: Banks. Core banking software sold to banks.") == "software"              # a kept model stays
    assert C.refine_model("unknown", "Industry: IT Services. Banking software for lenders.") == "unknown"


PHOENIX = ("Industry: Residential, Commercial Projects. Phoenix Mills Ltd is engaged in the operation & management of malls, construction of "
           "commercial & residential property and hotel business in India. The company is India's largest retail mall operator and offers retail "
           "malls and office spaces on a license basis.")
PROZONE = ("Industry: Residential, Commercial Projects. Prozone Realty Ltd is in the business of developing, owning and operating of Shopping Malls, "
           "Commercial and Residential Premises. It develops large land parcels, about 75% to be developed as Residential and Commercial - Build & Sell.")


def test_a_landlords_own_words_make_it_one_whatever_its_industry_and_a_developer_stays_one():
    assert C.refine_model("property_development", PHOENIX) == "property"
    assert C.refine_model("property_development", PROZONE) == "property_development"
    assert G.classify(G.company("realty", "PHOENIXLTD")) == ("property", "")
    # a developer whose words name rented offices in passing stays a developer (its industry and words of building)
    assert C.refine_model("property_development", "Industry: Residential, Commercial Projects. Develops and sells residential apartments "
                                                  "and also earns rental income from two malls.") == "property_development"


def test_the_mall_owners_layer_holds_one_way_of_earning():
    vc = [{"layer": "Mall and retail property owners", "description": "", "companies": [
              {"ticker": "PHOENIXLTD", "industry": "Residential, Commercial Projects", "cap": 9},
              {"ticker": "NXST-RR", "industry": "", "cap": 3},
              {"ticker": "PROZONER", "industry": "Residential, Commercial Projects", "cap": 1}]},
          {"layer": "Residential developers", "description": "", "companies": [
              {"ticker": f"D{i}", "industry": "Residential, Commercial Projects", "cap": 5} for i in range(4)]}]
    ev = {"PHOENIXLTD": PHOENIX, "PROZONER": PROZONE, "NXST-RR": "", **{f"D{i}": "Industry: Residential, Commercial Projects. Develops and sells homes."
                                                                        for i in range(4)}}
    kept = {"PHOENIXLTD": "property_development", "NXST-RR": "property", "PROZONER": "property_development",
            **{f"D{i}": "property_development" for i in range(4)}}
    conf = {"PHOENIXLTD": "low", "NXST-RR": "low", "PROZONER": "medium", **{f"D{i}": "high" for i in range(4)}}
    models, conf = B.refine_kept(kept, conf, lambda s: ev[s], list(ev))
    out = B.by_model(vc, models, "Real estate", confidence=conf, evidence_of=lambda s: ev[s])
    mall = layer_of(out, "PHOENIXLTD")
    assert mall["model"]["id"] == "property" and "PROZONER" not in {c["ticker"] for c in mall["companies"]}
    assert layer_of(out, "PROZONER")["layer"] == "Residential developers"
    assert {C.model_family(c["model"]) for c in mall["companies"] if not c.get("model_out")} == {"property"}


# ---------- 2. Consumer retail ----------
def test_live_retail_fuel_distributors_and_online_sellers_leave_the_apparel_chains():
    vc = replay("retail_us_r35.json")
    apparel = layer_of(vc, "GAP")
    assert apparel["layer"] == "Apparel and fashion retail chains"
    names = {c["ticker"] for c in apparel["companies"]}
    assert not names & {"CIMG", "FGPR", "SPH", "CPNG", "W", "VIPS", "FCFS", "EZPW", "SVV"}
    for sym in ("CPNG", "W", "VIPS"):                         # online sellers: the online retailers, the layer of their own industry
        assert layer_of(vc, sym)["layer"] == "Online direct-to-consumer retailers", sym
    other = next(v for v in vc if v.get("official") and v.get("basis") == "rest")
    assert "CIMG" in {c["ticker"] for c in other["companies"]}
    # R40 (lane s3-r40, updated on purpose): propane distributors are another business than retail, dropped from the theme
    assert {"FGPR", "SPH"} <= DROPPED["retail_us_r35.json"] and not {"FGPR", "SPH"} & {c["ticker"] for v in vc for c in v["companies"]}
    # the chains the map put there stay, and Amazon keeps its R36 place
    assert {"GAP", "M", "DDS", "ANF", "AEO", "URBN"} <= names
    assert layer_of(vc, "AMZN")["layer"] == "Online direct-to-consumer retailers"


def by_model_one(layers, mover):
    vc = [{"layer": n, "description": d, "companies": [{"ticker": f"{n[:3]}{i}", "industry": ind, "what": w, "cap": 10 - i} for i, (ind, w) in enumerate(cos)]}
          for n, d, cos in layers]
    vc.append({"layer": "Other", "description": "", "official": True, "basis": "rest", "companies": [mover]})
    models = {c["ticker"]: "retail" for v in vc for c in v["companies"]}
    return B.by_model(vc, models, "Retail", confidence={s: "high" for s in models})


def test_a_company_leaving_other_joins_the_largest_layer_only_when_it_holds_its_industry_or_words():
    big = ("Apparel chains", "Chains selling clothing and footwear.", [("Retail-Family Clothing Stores", "sells clothing")] * 5)
    small = ("Online retailers", "Companies selling online.", [("Retail-Catalog & Mail-Order Houses", "sells online")] * 3)
    # of the largest layer's industry: there, as before (no reshuffle)
    out = by_model_one([big, small], {"ticker": "X", "industry": "Retail-Family Clothing Stores", "what": "operates outlet stores", "cap": 1})
    assert layer_of(out, "X")["layer"] == "Apparel chains"
    # the layer whose every company is of its industry and whose words it shares: that layer
    out = by_model_one([big, small], {"ticker": "X", "industry": "Retail-Catalog & Mail-Order Houses", "what": "sells furniture online", "cap": 1})
    assert layer_of(out, "X")["layer"] == "Online retailers"
    # of its industry or its words only: the largest, as before (no move on one sign alone)
    out = by_model_one([big, small], {"ticker": "X", "industry": "Retail-Catalog & Mail-Order Houses", "what": "an e-commerce company", "cap": 1})
    assert layer_of(out, "X")["layer"] == "Apparel chains"
    # R38 lane s1-fit (updated on purpose: the live R37 Consumer retail deck had 34 such companies in its largest layer): one shared word
    # with another layer, none with the largest, and no layer of its family holds its industry: never the largest by default, it stays in
    # "Other"; two shared words place it in that layer
    out = by_model_one([big, small], {"ticker": "X", "industry": "Retail-Miscellaneous Retail", "what": "sells furniture online", "cap": 1})
    assert layer_of(out, "X")["layer"] == "Other"
    home = ("Furniture and home stores", "Stores selling furniture and home decor.", [("Retail-Furniture Stores", "sells furniture")] * 2)
    out = by_model_one([big, small, home], {"ticker": "X", "industry": "Retail-Miscellaneous Retail", "what": "sells furniture and home decor online",
                                            "cap": 1})
    assert layer_of(out, "X")["layer"] == "Furniture and home stores"
    # neither: it stays in "Other", its way of earning shown
    out = by_model_one([big, small], {"ticker": "X", "industry": "Retail-Miscellaneous Retail", "what": "retail distribution of propane", "cap": 1})
    assert layer_of(out, "X")["layer"] == "Other" and row_of(out, "X")["model"] == "retail"
    # no words at all: R38 lane s1-fit (updated on purpose: live, a propane distributor and a pawnbroker with no stored words went to the
    # largest retail layer): the largest only when it holds its industry, else "Other"
    out = by_model_one([big, small], {"ticker": "X", "industry": "Retail-Miscellaneous Retail", "what": "", "cap": 1})
    assert layer_of(out, "X")["layer"] == "Other"
    out = by_model_one([big, small], {"ticker": "X", "industry": "Retail-Family Clothing Stores", "what": "", "cap": 1})
    assert layer_of(out, "X")["layer"] == "Apparel chains"


def test_no_other_theme_reshuffled_beyond_the_layers_of_their_industry():
    # the IN maps' "Other" companies go where they went before when the largest layer holds their industry (auto parts makers to the parts
    # layer); the 14-map replay's other moves are each to the layer of the company's own industry (agrochemicals, petrochemicals, gases)
    vc = [{"layer": "Component suppliers", "description": "", "companies": [
              {"ticker": f"P{i}", "industry": "Auto Components & Equipments", "cap": 9 - i} for i in range(5)]},
          {"layer": "Two-wheeler makers", "description": "", "companies": [{"ticker": "T0", "industry": "2/3 Wheelers", "cap": 9}]},
          {"layer": "Other", "description": "", "official": True, "basis": "rest", "companies": [
              {"ticker": "N", "industry": "Auto Components & Equipments", "what": "makes gears and shafts", "cap": 1}]}]
    models = {**{f"P{i}": "components" for i in range(5)}, "T0": "manufacturing", "N": "components"}
    out = B.by_model(vc, models, "Automotive", confidence={s: "high" for s in models})
    assert layer_of(out, "N")["layer"] == "Component suppliers"


def test_a_company_the_map_placed_keeps_its_layer_when_only_its_words_give_its_model():
    """The live R35 Defence map: Centum and Cyient DLM (electronics contract manufacturers, no model kept) in "Electronics and sub-systems":
    their words now state contract making, and they stay in the map's layer, left out of its figures as another way of earning, never moved
    to a layer of their own; one whose model a rule made from the evidence (a bank's industry) goes by it as before."""
    vc = [{"layer": "Electronics and sub-systems", "description": "", "companies": [
              {"ticker": t, "industry": "Aerospace & Defense", "cap": 9 - i} for i, t in enumerate(("BEL", "DATAPATTNS", "PARAS", "CENTUM"))]},
          {"layer": "Shipbuilders", "description": "", "companies": [{"ticker": "MAZDOCK", "industry": "Ship Building", "cap": 9}]}]
    ev = {"BEL": "Industry: Aerospace & Defense. Bharat Electronics manufactures radars and defence electronics.",
          "DATAPATTNS": "Industry: Aerospace & Defense. Data Patterns manufactures defence electronic systems.",
          "PARAS": "Industry: Aerospace & Defense. Paras Defence manufactures optics and electronics.",
          "CENTUM": "Industry: Aerospace & Defense. Centum Electronics Limited is one of the largest Electronics System Design and Manufacturing "
                    "(ESDM) companies in India.",
          "MAZDOCK": "Industry: Ship Building. Builds warships."}
    m = {"sector": "Defence", "value_chain": vc}
    kept = {"assign": {}, "models": {"BEL": "manufacturing", "DATAPATTNS": "manufacturing", "PARAS": "manufacturing", "MAZDOCK": "construction"},
            "model_confidence": {"BEL": "high", "DATAPATTNS": "high", "PARAS": "high", "MAZDOCK": "high"}}
    out, _ = B.place_rest(m, "Defence", lambda s: ev[s].split(". ", 1)[1], ask=None, kept=kept,
                          facts_of=lambda s: {"industry": ev[s].split(". ")[0].removeprefix("Industry: ")})
    lay = layer_of(out["value_chain"], "CENTUM")
    assert lay["layer"] == "Electronics and sub-systems"
    assert row_of(out["value_chain"], "CENTUM")["model"] == "contract_manufacturing" and row_of(out["value_chain"], "CENTUM")["model_out"] == "other"
    assert lay["model"]["id"] == "manufacturing"


# ---------- 3. Semiconductors ----------
def test_packaging_and_test_services_are_contract_makers_counted_and_materials_makers_keep_their_layer():
    for sym in ("AMKR", "IMOS", "ASX"):
        assert G.classify(G.company("semis", sym)) == ("contract_manufacturing", ""), sym
    for sym in ("Q", "ENTG"):
        assert G.classify(G.company("semis", sym)) == ("components", ""), sym
    vc = replay("semis_us_r35.json")
    contract = layer_of(vc, "AMKR")
    assert contract["model"]["id"] == "contract_manufacturing" and contract["layer"] == "Packaging, test and materials suppliers"
    assert {c["ticker"] for c in contract["companies"]} == {"AMKR", "IMOS", "ASX"}
    assert not any(c.get("model_out") for c in contract["companies"])
    # the foundries keep their own contract layer (a contract maker joins only a contract layer of its kind: theme_check.contract_kind)
    fdy = layer_of(vc, "TSM")
    assert fdy is not contract and fdy["model"]["id"] == "contract_manufacturing" and {"TSM", "UMC", "GFS", "TSEM"} <= {c["ticker"] for c in fdy["companies"]}
    assert C.contract_kind(SEMI + "A provider of semiconductor packaging and test services.") == "osat"
    assert C.contract_kind(SEMI + "As a foundry, we manufacture chips based on designs provided by our customers.") == "foundry"
    assert C.contract_kind("Industry: Pharmaceuticals. A CDMO for global pharma.") == ""
    materials = layer_of(vc, "Q")
    assert materials is layer_of(vc, "ENTG") and materials["model"]["id"] == "components"
    assert {C.model_family(c["model"]) for c in materials["companies"]} == {"components"}
    # an auto parts maker that says it makes to its customers' drawings is not made a chip contract maker by the OSAT rule
    assert C.refine_model("components", "Industry: Auto Components. Makes forgings to customers' designs for OEMs.") == "components"


TI_WIKI = ("Texas Instruments Incorporated (TI) is an American multinational semiconductor company headquartered in Dallas, Texas, United States. "
           "It is one of the top 10 semiconductor companies worldwide based on sales volume. The company's focus is on developing analog chips and "
           "embedded processors, which account for more than 80% of its revenue. TI also produces digital light processing (DLP) technology and "
           "education technology products including calculators, microcontrollers, and multi-core processors.")


def test_a_chip_company_that_designs_makes_and_sells_its_chips_is_no_fabless_one():
    # its encyclopedia words alone leave whether it owns fabs unsaid (so do Marvell's and Broadcom's: "develops and produces"): kept as given
    assert C.refine_model("fabless", SEMI + TI_WIKI) == "fabless"
    assert TR.chip_unsettled(TI_WIKI)
    # an annual report's own-fab words, read first, make it a maker of its own chips
    for opening in ("We design, manufacture, test and sell analog and embedded processing chips.",
                    "We design and make semiconductors that we sell to electronics designers and manufacturers all over the world.",
                    "We own and operate semiconductor manufacturing sites in North America, Asia, Japan and Europe."):
        ev = SEMI + opening + " " + TI_WIKI
        assert C.refine_model("fabless", ev) == "manufacturing", opening
        assert not TR.chip_unsettled(opening + " " + TI_WIKI)
    # fabless and foundry words keep a designer one
    assert C.refine_model("fabless", SEMI + "We are a fabless company; we design, develop and sell chips made by third-party foundries.") == "fabless"
    assert not TR.chip_unsettled("A fabless semiconductor company.") and not TR.chip_unsettled("Supplies semiconductor equipment for wafer fabs.")
    # the live designers stay fabless (their words name no own fabs)
    for sym in ("NVDA", "AMD", "AVGO", "MRVL", "LSCC", "QCOM"):
        assert G.classify(G.company("semis", sym)) == ("fabless", ""), sym


@pytest.fixture
def store(monkeypatch):
    kept: dict = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "")
    TR.EVIDENCE_CACHE.clear()
    yield kept
    TR.EVIDENCE_CACHE.clear()


def test_the_check_puts_a_chip_makers_annual_report_first_once(store, monkeypatch):
    store["theme:evidence:US:TXN"] = json.dumps({"at": "2026-11-01T00:00:00+00:00", "about": TI_WIKI, "v": TR.ABOUT_V})
    store["theme:evidence:US:NVDA"] = json.dumps({"at": "2026-11-01T00:00:00+00:00", "about": "A fabless semiconductor company.", "v": TR.ABOUT_V})
    store["theme:evidence:US:KLAC"] = json.dumps({"at": "2026-11-01T00:00:00+00:00", "about": TI_WIKI, "v": TR.ABOUT_V})
    reads = []
    monkeypatch.setattr(TR, "filed_business", lambda region, sym: reads.append(sym) or ("We design, manufacture and sell analog chips.", False))
    out = {"value_chain": [{"layer": "Chips", "companies": [{"ticker": t, "cap": c} for t, c in (("TXN", 9), ("NVDA", 8), ("KLAC", 7), ("NEW", 1))]}]}
    kept = {"models": {"TXN": "fabless", "NVDA": "fabless", "KLAC": "software"}}
    assert TR.read_chip_making("US", out, kept) == ["TXN"] and reads == ["TXN"]
    got = json.loads(store["theme:evidence:US:TXN"])
    assert got["filed"] and got["about"].startswith("We design, manufacture and sell analog chips.") and "Texas Instruments" in got["about"]
    assert TR.read_chip_making("US", out, kept) == []                                 # once
    assert TR.read_chip_making("IN", out, kept) == []
    # a read still owed (the minute's annual reports taken) waits for a later check, nothing kept
    store["theme:evidence:US:TXN"] = json.dumps({"at": "2026-11-01T00:00:00+00:00", "about": TI_WIKI, "v": TR.ABOUT_V})
    monkeypatch.setattr(TR, "filed_business", lambda region, sym: ("", True))
    assert TR.read_chip_making("US", out, kept) == [] and "filed" not in json.loads(store["theme:evidence:US:TXN"])


# ---------- 4. Unknown models ----------
def test_a_kept_placements_never_read_companies_are_read(store, monkeypatch):
    store["theme:evidence:IN:OLD"] = json.dumps({"at": "2026-11-01T00:00:00+00:00", "about": "x " * 40, "v": TR.ABOUT_V})
    asked = []
    monkeypatch.setattr(TR, "evidence_reader", lambda region, names: (lambda syms: asked.append(list(syms)) or ({}, [])))
    out = {"value_chain": [{"layer": "Parts", "companies": [{"ticker": t, "cap": c} for t, c in (("OLD", 9), ("NEVER", 5), ("KNOWN", 3))]}]}
    kept = {"models": {"KNOWN": "components"}, "model_confidence": {"KNOWN": "high"}}
    assert TR.reread_weak("IN", out, {}, kept) == ["NEVER"] and asked == [["NEVER"]]


SINTERCOM = ("Industry: Auto Components & Equipments. Incorporated in 2007, Sintercom India Ltd manufactures sintered metal components and auto "
             "components. It specializes in manufacturing medium to high density sintered components for automotive engine and powertrain.")


def test_own_words_state_the_model_and_nothing_else_does():
    S = C.stated_model
    assert S(SINTERCOM) == "components"
    assert S("Industry: Auto Components & Equipments. Kranti Industries Ltd is a manufacturer of precision-machined component.") == "components"
    assert S("Industry: Specialty Chemicals. Dynemic Products is in the business of manufacturing and selling of Dyes & Dye Intermediates.") == "manufacturing"
    assert S("Industry: Software Products. Integrated Hitech Ltd provides Software Development Services.") == "project_services"
    assert S("Industry: Commodity Chemicals. Pentokey Organy (India) Ltd trades pharmaceutical products. It is in the business of trading "
             "pharmaceutical products.") == "distribution"
    assert S("Industry: Aerospace & Defense. Centum Electronics Limited is one of the largest Electronics System Design and Manufacturing (ESDM) "
             "companies in India.") == "contract_manufacturing"
    # two ways of earning, a stopped business, its customers, a certificate, or no words: unknown (never a guess)
    for ev in ("Industry: Petrochemicals. Nexxus Petro Industries Ltd manufactures and trades Bitumen.",
               "Industry: Auto Components & Equipments. Sar Auto Products Ltd manufactures gears and transmission components. It is also in the "
               "business of Real Estate Development.",
               "Industry: Auto Components & Equipments. MKP Mobility Ltd is an automobile spare parts distributor in India.",
               "Industry: Specialty Chemicals. Vital Chemtech manufactures phosphorous based chemicals; the group does Manufacturing, Contract "
               "Manufacturing and Exports.",
               "Industry: Commodity Chemicals. TECIL Chemicals is a non-operating listed company that historically manufactured calcium carbide.",
               "Industry: Specialty Chemicals. Unitech International sells its products to auto parts manufacturing companies; it is engaged in the "
               "trading of engineering polymers and has begun manufacturing polymer.",
               "Industry: Auto Components & Equipments.",
               "Industry: Retail-Catalog & Mail-Order Houses. CDW is a multi-brand provider of information technology services."):
        assert S(ev) == "", ev
    assert "contract_manufacturing" != S("Industry: Auto Components. An IATF 16949 and ISO 14001 EMS certified manufacturer of propeller shafts.")


def test_a_stated_model_is_kept_at_medium_and_a_model_its_words_dont_show_is_not():
    ev = {"S": SINTERCOM, "N": "Industry: Industrial Minerals. Nile Ltd is a manufacturer of Pure Lead for battery consumption.",
          "E": "Industry: Auto Components & Equipments."}
    models, conf = B.refine_kept({}, {}, lambda s: ev[s], list(ev))
    assert models["S"] == "components" and conf["S"] == "medium"
    assert models.get("N", "unknown") == "unknown" and models.get("E", "unknown") == "unknown"   # made exact into a mining model its words don't show; no words


# before (the live R35 maps: no model) and after (R37, their words read), unknown models per theme over the golden fixture's companies
UNKNOWN_BEFORE = {"auto": 50, "bank": 0, "semis": 9, "it": 48, "pharma": 0, "insurance": 1, "defence": 7, "cyber": 0, "chem": 125, "realty": 3,
                  "telecom": 1, "retail": 3, "utilities": 1, "metals": 8}
UNKNOWN_AFTER = {"auto": 17, "bank": 0, "semis": 7, "it": 31, "pharma": 0, "insurance": 1, "defence": 4, "cyber": 0, "chem": 72, "realty": 2,
                 "telecom": 1, "retail": 3, "utilities": 1, "metals": 7}


def test_unknown_models_fall_in_every_theme_and_rise_in_none():
    for t in G.GOLDEN["themes"]:
        before = sum(1 for c in t["companies"] if not c["m"])
        after = sum(1 for c in t["companies"] if G.classify(c)[0] == "unknown")
        assert (before, after) == (UNKNOWN_BEFORE[t["key"]], UNKNOWN_AFTER[t["key"]]), t["key"]
        assert after <= before
    assert sum(UNKNOWN_BEFORE.values()) == 256 and sum(UNKNOWN_AFTER.values()) == 146
    # the three layers the owner named
    by_layer = lambda key, layer: [c for t in G.GOLDEN["themes"] if t["key"] == key for c in t["companies"] if c["l"] == layer]   # noqa: E731
    unknown = lambda cos: sum(1 for c in cos if G.classify(c)[0] == "unknown")                                                  # noqa: E731
    assert unknown(by_layer("it", "Engineering R&D services")) == 22              # of 57 (live 39)
    assert unknown(by_layer("chem", "Custom synthesis manufacturers")) == 7        # of 18 (live 10)
    assert unknown(by_layer("auto", "Component and systems suppliers (smaller)")) == 11   # of 66 (live 39)


def test_the_rules_version_moved_with_its_carry():
    assert B.RULES == 48 and TR.PLACE_CARRY[48] == 47 and TR.PLACE_CARRY[47] == 46 and TR.PLACE_CARRY[46] == 45 and TR.PLACE_CARRY[45] == 44 and TR.PLACE_CARRY[44] == 43 and TR.PLACE_CARRY[43] == 42 and TR.PLACE_CARRY[42] == 41 and TR.PLACE_CARRY[41] == 40 and TR.PLACE_CARRY[38] == 37 and TR.PLACE_CARRY[39] == 38   # ex49 (R49): RULES 48, PLACE_CARRY[48] = 47, deck 59, dive text 19, precise exclusion reasons, the business-model ranking rule (updated on purpose); cl48 (R48): RULES 47, PLACE_CARRY[47] = 46, deck 58, dive text 18, primary-business validation and the coverage control (updated on purpose); cv47 (R47): RULES 46, PLACE_CARRY[46] = 45, filing titles are no words of a company's own, the AI's industry pick kept across rules changes (PICK_RULES); deck and dive text unchanged (updated on purpose); tx2 (R45/R46): RULES 45, PLACE_CARRY[45] = 44, deck 57 (dive text stays 16), the taxonomy regression guard and the screening populations (updated on purpose); c1 (R44): RULES 44, PLACE_CARRY[44] = 43, deck 56, dive text 16 (55 and 15 are R44.1's), classification coverage from evidence (updated on purpose); lane d1: RULES 43, PLACE_CARRY[43] = 42, deck 53, dive text 12 (the outside review of the live R41 decks, updated on purpose); lane s3-r40: RULES 42, deck 50, dive text 10 (updated on purpose); lane s2-exact and lane s1-fit bumped RULES (updated on purpose)
