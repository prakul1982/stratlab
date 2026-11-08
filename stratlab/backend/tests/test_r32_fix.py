"""Release 32 (lane r311-fix): three gaps in the live R31 decks, fixed generically.
1. Chip designers that own no fabs are fabless (contract-made own design) with medium confidence or better; own fabs make an IDM (a maker).
2. A layer named by how it earns ("Product designers that outsource making") joins the map's layer of the same primary model, family and
   sub-basis; the merged layer's line reads normally.
3. A split by market value one of whose halves shows no company is undone: one layer, the map's name.
Generic: synthetic themes only, no real company's name or figure."""
import copy

from app import deck
from app.intel import theme_base as B
from app.intel import theme_check as C
from tests.synth_structures_r27class import build
from tests.test_r18_deck import deck_of
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule

ev = C.model_evidence


def _rows(prefix, n, name, what, ind, model, conf="high"):
    return [(f"{prefix}{i}", f"{name} {i} Inc", what, ind, model, (), conf) for i in range(n)]


# ---------- 1. chip designers ----------
def test_a_chip_designer_without_fabs_is_fabless_and_one_with_fabs_an_idm():
    gpu = ev("Semiconductors", "designs and develops graphics processors and systems-on-chip for data centres and gaming")
    assert C.chip_designer(gpu)
    for given in ("manufacturing", "fabless", "unknown", ""):
        assert C.refine_model(given, gpu) == "fabless", given
    assert C.refine_model("unknown", ev("Semiconductors", "designs and makes chips in its own wafer fabs")) == "manufacturing"
    assert C.refine_model("fabless", ev("Semiconductors & Related Devices", "an integrated device manufacturer of analog chips")) == "manufacturing"
    assert C.model_supported("fabless", ev("Semiconductors & Related Devices", "designs GPUs and SoCs"))
    assert C.model_confidence("fabless", ev("Semiconductors", "designs GPUs")) == "high"
    # official industry "Semiconductors" and design words are enough for medium, never low
    assert C.model_confidence("fabless", ev("Semiconductors", "designs and sells computing platforms for gaming"), "low") == "medium"
    assert C.model_from_words(ev("Semiconductors", "develops analog and mixed-signal integrated circuits for cars")) == "fabless"
    assert C.model_from_words(ev("Semiconductors", "designs chips that foundries make")) == "fabless"


def test_what_is_never_a_chip_designer_stays_as_given():
    for given, e in [("unknown", ev("Semiconductors", "provides electronic design automation software used to design chips")),
                     ("unknown", ev("Semiconductors", "licenses its processor architectures and cores to chip companies")),
                     ("manufacturing", ev("Special Industry Machinery", "manufactures semiconductor equipment for wafer fabs")),
                     ("manufacturing", ev("Semiconductors", "manufactures memory chips")),
                     ("unknown", ev("Food Products", "makes potato chips and snacks")),
                     ("unknown", ev("Household Appliances", "designs and develops kitchen food processors"))]:
        assert not C.chip_designer(e), e
        assert C.refine_model(given, e) == given, e


def test_a_kept_placement_s_low_or_unknown_designers_become_fabless_of_medium_or_better():
    e = {"A": ev("Semiconductors", "designs and develops GPUs"), "B": ev("Semiconductors", "designs and sells computing platforms"),
         "C": ev("Semiconductors", "fabless: designs chips that foundries make"), "D": ev("Banks", "takes deposits and lends")}
    models, conf = B.refine_kept({"A": "manufacturing", "B": "unknown", "C": "fabless", "D": "lending"},
                                 {"A": "low", "B": "low", "C": "low", "D": "high"}, e.get)
    assert models == {"A": "fabless", "B": "fabless", "C": "fabless", "D": "lending"}
    assert conf["A"] == conf["B"] == conf["C"] == "medium" and conf["D"] == "high"          # the AI's "low" caps it, the designer's floor lifts it
    assert B.refine_kept({"D": "lending"}, None, e.get) == ({"D": "lending"}, None)


def semis_us():
    """The live US semiconductors map's shape: a "Fabless chip design" layer of designers whose models came back as makers or unknown with
    low confidence (none says "fabless"), a layer the AI named "Product designers that outsource making", fab owners, tools, OSATs, EDA."""
    designers = (_rows("GPU", 3, "Gridcore", "designs and develops graphics processors and accelerators for data centres", "Semiconductors & Related Devices",
                       "manufacturing", "low")
                 + _rows("SOC", 2, "Socwise", "designs systems-on-chip and modems for phones", "Semiconductors & Related Devices", "unknown", "low")
                 + _rows("ANL", 2, "Analogix", "develops analog and mixed-signal integrated circuits", "Semiconductors & Related Devices", "manufacturing", "low"))
    t = build("US", "Semiconductors", [
        ("Fabless chip design", "Designs chips.", designers),
        ("Product designers that outsource making", "Contract made.",
         _rows("OUT", 4, "Foundrysent", "fabless: designs chips and has them made by foundries", "Semiconductors & Related Devices", "fabless")),
        ("Chip makers", "Fabs.", _rows("IDM", 5, "Wafermade", "designs and makes chips in its own fabs", "Semiconductors & Related Devices", "manufacturing")),
        ("Equipment", "Tools.", _rows("EQP", 5, "Etchtool", "manufactures wafer fab equipment", "Special Industry Machinery", "manufacturing")),
        ("Packaging and test", "OSAT.", _rows("OST", 4, "Packright", "packages and tests chips for other companies under contract",
                                              "Semiconductors & Related Devices", "contract_manufacturing")),
        ("Design software", "EDA.", _rows("EDA", 4, "Layoutly", "sells subscription software licences for chip design", "Prepackaged Software", "software")),
    ], [])
    evs = {c["ticker"]: ev(c.get("industry") or "", c.get("what") or "") for v in t["map"]["value_chain"] for c in v["companies"]}
    t["models"], t["confidence"] = B.refine_kept(t["models"], t["confidence"], evs.get)
    return t


def test_on_a_us_semis_set_the_designers_count_and_the_fabless_layers_are_one():
    t = semis_us()
    assert all(t["models"][s] == "fabless" and t["confidence"][s] in ("medium", "high") for s in t["models"] if s[:3] in ("GPU", "SOC", "ANL"))
    vc = B.by_model(copy.deepcopy(t["map"]["value_chain"]), t["models"], "Semiconductors", tags=t["tags"], confidence=t["confidence"])
    names = [v["layer"] for v in vc]
    assert "Product designers that outsource making" not in names
    fab = next(v for v in vc if v["layer"] == "Fabless chip design")
    assert {c["ticker"] for c in fab["companies"]} >= {f"OUT{i}" for i in range(4)} | {f"GPU{i}" for i in range(3)}
    md = fab["model"]
    assert md["id"] == "fabless" and not md.get("sparse") and md["known"] == md["of"] == 11 and not md.get("out")
    assert md["line"].startswith("They earn mainly from selling products of their own design") and "separate layers" not in md["line"]
    assert not any(c.get("model_out") for c in fab["companies"])
    view, slides = deck_of(t["region"], {**t["map"], "value_chain": vc}, t["facts"])
    every_rule("semis designers (US)", view, slides)
    text = " ".join(str(x) for s in slides for b in s.blocks for x in (b.get("paras") or []))
    assert "How they earn is shown for only" not in text


# ---------- 2. a layer named by how it earns joins the map's layer of its primary model ----------
def test_a_model_named_layer_joins_the_map_s_layer_and_two_plain_ones_still_stay():
    t = build("IN", "Automobiles", [
        ("Two-wheelers", "Bikes.", _rows("TWO", 5, "Bikeco", "makes motorcycles and scooters in its plants", "2/3 Wheelers", "manufacturing")),
        ("Makers of their own products", "Made.", _rows("MKR", 3, "Carmake", "makes cars in its plants", "Passenger Cars", "manufacturing")),
        ("Passenger cars", "Cars.", _rows("CAR", 4, "Autoline", "makes passenger cars in its plants", "Passenger Cars", "manufacturing")),
    ], [])
    vc = B.by_model(copy.deepcopy(t["map"]["value_chain"]), t["models"], "Automobiles", tags=t["tags"], confidence=t["confidence"])
    names = [v["layer"] for v in vc if not v.get("official")]
    assert names == ["Two-wheelers", "Passenger cars"]                                   # the model-named layer joins the larger plain one
    two = vc[0]
    assert {c["ticker"] for c in two["companies"]} == {f"TWO{i}" for i in range(5)} | {f"MKR{i}" for i in range(3)}
    assert two["model"]["same_as"] == ["Passenger cars"]                                 # two layers named by what they make both stay


# ---------- 3. a market-value half with no shown company is undone ----------
def realty_split():
    return build("IN", "Real estate", [
        ("Residential developers", "Homes.", _rows("DEV", 10, "Homecrest", "develops and sells residential apartments", "Residential, Commercial Projects",
                                                    "property_development")),
        ("Office landlords", "Rent.", _rows("LSE", 4, "Mallhold", "owns office parks and earns rent on leases", "Realty", "property")),
        ("Construction contractors", "EPC.", _rows("EPC", 4, "Buildco", "builds under EPC contracts", "Civil Construction", "construction")),
    ], [])


def test_a_split_half_with_no_shown_company_is_undone():
    t = realty_split()
    vc = B.by_model(copy.deepcopy(t["map"]["value_chain"]), t["models"], "Real estate", tags=t["tags"], confidence=t["confidence"])
    big = next(v for v in vc if v["layer"] == "Residential developers (larger)")
    small = next(v for v in vc if v["layer"] == "Residential developers (smaller)")
    assert B.unsplit_unshown(vc, {c["ticker"] for v in vc for c in v["companies"]}) == vc          # both halves shown: kept
    one = B.unsplit_unshown(vc, {c["ticker"] for c in big["companies"]})
    res = [v for v in one if v["layer"].startswith("Residential")]
    assert [v["layer"] for v in res] == ["Residential developers"] and not res[0].get("scale") and not res[0].get("sibling")
    assert len(res[0]["companies"]) == 10 and "half of one group" not in res[0]["model"]["line"]
    assert res[0]["model"]["line"].startswith("They earn mainly from") and res[0]["model"]["of"] == 10
    # in the deck: the smaller half's companies have no figures, so none is shown
    facts = {s: f for s, f in t["facts"].items() if s not in {c["ticker"] for c in small["companies"]}}
    view, slides = deck_of(t["region"], {**t["map"], "value_chain": vc}, facts)
    lays = [x["layer"] for x in view["layers"]]
    assert "Residential developers" in lays and not any("(larger)" in x or "(smaller)" in x for x in lays)
    text = " ".join(str(x) for s in slides for b in s.blocks for x in (b.get("paras") or []) + [s.title or ""])
    assert "(smaller)" not in text and "(larger)" not in text
    assert deck.THEME_DECK_VERSION == 33 and B.RULES == 33


def test_a_company_with_no_model_takes_the_one_its_map_layers_name_states():
    """Live R31.1 semis: Qualcomm, Broadcom, AMD... had only "From its own filings: Quarterly report" as evidence and sat unknown in the map's
    "Fabless chip design"; the layer's own name states the model, so they take it at medium confidence. An official group, a name that states
    no single model, and a company whose model is known are left alone."""
    from app.intel.theme_base import models_from_layer
    vc = [{"layer": "Fabless chip design", "companies": [{"ticker": "QCOM"}, {"ticker": "NVDA"}, {"ticker": "AVGO"}]},
          {"layer": "Other semiconductor companies", "companies": [{"ticker": "XYZ"}]},
          {"layer": "Semiconductors", "official": True, "companies": [{"ticker": "OFF"}]}]
    models, conf = models_from_layer(vc, {"NVDA": "fabless", "AVGO": "unknown", "XYZ": ""}, {"NVDA": "high"})
    assert models["QCOM"] == "fabless" and models["AVGO"] == "fabless" and conf["QCOM"] == conf["AVGO"] == "medium"
    assert conf["NVDA"] == "high" and models.get("XYZ", "") == "" and "OFF" not in models


def test_a_layer_name_never_gives_its_model_against_the_companys_own_words():
    """Live R31.1 semis: a materials maker sat in "Fabless chip design"; its own evidence names materials, so the layer's model is not given."""
    from app.intel.theme_base import models_from_layer
    vc = [{"layer": "Fabless chip design", "companies": [{"ticker": "Q"}, {"ticker": "E"}, {"ticker": "D"}]}]
    ev = {"Q": "Industry: Specialty Chemicals. Supplies electronic materials for chip making.",
          "E": "Makes semiconductor equipment for wafer fabs.", "D": "From its own filings: Quarterly report"}
    models, _ = models_from_layer(vc, {}, None, ev)
    assert "Q" not in models and "E" not in models and models["D"] == "fabless"
