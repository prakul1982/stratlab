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
    # lane m1 (updated on purpose; live R32 Semiconductors showed nine makers under "Semiconductor equipment", the larger of two layers of
    # makers): with two layers named by what they make, how the model-named layer's companies earn doesn't say which they belong to: it stays
    assert names == ["Two-wheelers", "Makers of their own products", "Passenger cars"]
    two = vc[0]
    assert {c["ticker"] for c in two["companies"]} == {f"TWO{i}" for i in range(5)}
    assert two["model"]["same_as"] == ["Makers of their own products", "Passenger cars"]   # each line says the three earn the same way
    # one layer named by what it makes: the model-named layer joins it, as before
    one = copy.deepcopy(t["map"]["value_chain"])[:2]
    vc = B.by_model(one, t["models"], "Automobiles", tags=t["tags"], confidence=t["confidence"])
    assert [v["layer"] for v in vc if not v.get("official")] == ["Two-wheelers"]
    assert {c["ticker"] for c in vc[0]["companies"]} == {f"TWO{i}" for i in range(5)} | {f"MKR{i}" for i in range(3)}


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
    assert deck.THEME_DECK_VERSION == 47 and B.RULES == 35          # lane m1 bumped RULES (updated on purpose; lane n2: RULES 35)


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


def test_the_shown_companies_label_matches_who_was_ranked():
    """Live R31.1 IT: "The largest 3 of 6 by market value" listed three while three larger ones (left out of figures) sat below."""
    from app.deck import shown_label
    big_first = [{"cap": 9}, {"cap": 7}, {"cap": 5}, {"cap": 1}]
    assert shown_label(big_first, 2) == "The largest 2 of 4 by market value"
    in_figs_first = [{"cap": 5}, {"cap": 3}, {"cap": 9, "model_out": True}, {"cap": 8, "model_out": True}]
    assert shown_label(in_figs_first, 2).startswith("The first 2 of 4: companies in the layer's figures first")


def test_a_stored_dive_is_made_again_when_its_sentences_change():
    """Live R31.4: the ranking line's new wording never reached the deck: the stored dive's key held only the rules' and metrics' versions."""
    from app.intel import theme_data, theme_routes
    m = {"generated_at": 1, "value_chain": [], "placements": {"placed": 3}}
    assert theme_routes.dive_key("IN", "x", m)[-1] == f"td{theme_data.DIVE_TEXT}"


def test_clipped_text_ends_on_a_whole_sentence_when_one_fits():
    """GPT review of R31.5: layer descriptions ended mid-thought with an ellipsis though a whole first sentence fitted."""
    from app.deck import clip
    text = "These firms design chips. " + "They earn from a long catalogue sold over many years to industrial buyers. " * 6
    out = clip(text, 10, 3.0, 2)
    assert out == "These firms design chips." or (out.endswith(".") and not out.endswith("…"))
    assert clip("One very long sentence " * 40, 10, 3.0, 2).endswith("…")     # no whole sentence fits: the ellipsis stays


def test_a_chip_materials_supplier_is_an_ingredient_maker_not_an_equipment_maker():
    """GPT review of R31.5: Qnity, a supplier of semiconductor and electronics materials, sat among equipment makers."""
    from app.intel import theme_check as C
    ev = C.model_evidence
    assert C.refine_model("manufacturing", ev("Semiconductors", "supplies advanced semiconductor and electronics materials and interconnect solutions")) == "components"
    assert C.refine_model("manufacturing", ev("Semiconductor Equipment", "makes wafer fab equipment and process tools")) == "manufacturing"
    assert C.refine_model("manufacturing", ev("Specialty Chemicals", "makes dyes and pigments for textiles")) == "manufacturing"


def test_a_sub_theme_takes_its_layers_companies_whose_own_words_name_it():
    """GPT review of R31.5: Bharti Airtel left out of "Mobile network operators" though in the "Mobile and broadband operators" layer."""
    from app.intel.theme_data import sub_members
    layers = [{"layer": "Mobile and broadband operators", "companies": [
        {"ticker": "BHARTIARTL", "what": "Mobile, home broadband and enterprise services"}, {"ticker": "IDEA", "what": "Mobile services"},
        {"ticker": "QUADRANT", "what": "Cable and broadband internet"}]}]
    got = [c["ticker"] for c in sub_members({"name": "Mobile network operators", "companies": [{"ticker": "IDEA"}]}, layers)]
    assert got == ["IDEA", "BHARTIARTL"]
    wide = {"name": "Tower and passive infrastructure sharing", "companies": [{"ticker": "IDEA"}]}
    assert [c["ticker"] for c in sub_members(wide, layers)] == ["IDEA"]          # three words that set it apart: left as the map has it


def test_a_company_out_of_a_layers_figures_says_why():
    """GPT review of R31.5 (IT: 13 with records, 4 in the layer's calculations, no reason for the other 9): a company of another way of
    earning is marked "other", one whose way of earning isn't shown "unknown"."""
    from app.intel.theme_base import by_model
    vc = [{"layer": "IT services", "companies": [{"ticker": t} for t in ("A", "B", "C", "P", "U")]}]
    models = {"A": "managed_services", "B": "managed_services", "C": "managed_services", "P": "software", "U": ""}
    got = by_model(vc, models)
    out = {c["ticker"]: c.get("model_out") for v in got for c in v["companies"]}
    it = next(v for v in got if v["layer"] == "IT services")
    assert out["U"] == "unknown" and not out["A"] and "P" not in {c["ticker"] for c in it["companies"]}     # another way: its own group


def test_a_cut_table_cell_ends_on_a_whole_word():
    """GPT review of R31.5: table cells read "Semiconductor equipm…" and "Defence syst…"."""
    from app.deck import fit_chars, _width
    out = fit_chars("Semiconductor equipment makers", 9, _width("Semiconductor equipm…", 9))
    assert out == "Semiconductor…"
    assert fit_chars("Short", 9, 5.0) == "Short"
    one = fit_chars("Supercalifragilistic", 9, _width("Supercal…", 9))
    assert one.endswith("…") and len(one) > 1                     # one long word: cut, still an ellipsis


def test_a_layer_name_with_no_word_is_never_named_in_a_note():
    """GPT review of R31.7, Defence p.6: "No listed company is shown for x." """
    import re as _re
    from app import deck
    src = open(deck.__file__).read()
    assert 'not x.get("companies") and re.search(r"[A-Za-z]{3,}"' in src and 'x not in none_ and re.search(r"[A-Za-z]{3,}"' in src
    assert not _re.search(r"[A-Za-z]{3,}", "x") and _re.search(r"[A-Za-z]{3,}", "Missile systems")


def test_a_cut_table_cell_never_ends_on_a_joining_word():
    from app.deck import fit_chars, _width
    assert fit_chars("Grid and power equipment makers", 9, _width("Grid and powe…", 9)) == "Grid…"


def test_a_fitted_paragraph_ends_on_a_whole_sentence_when_one_fits():
    """GPT review of R31.9: the summary page's ranking line ended "…companies with the figure and one kind of…"."""
    from app.deck import fit_paras
    text = ("Among the 3 of 7 comparable layers, median EBITDA margin is highest in A and lowest in B. "
            "Comparable: at least 5 companies with the figure and one kind of business.")
    out = fit_paras([text], 10, 3.2, 0.62)
    assert out and out[0].endswith(".") and not out[0].endswith("…")


def test_a_thin_stored_description_is_read_again_once_and_names_lose_their_legal_form():
    """GPT reviews of R31.5-R31.9: Bharti Airtel's stored line named no mobile service and Qnity's held only its name, so no rule could
    place them; a thin description kept before R34 is read once more, with the encyclopedia summary beside it."""
    from app.intel.theme_routes import thin_about, plain_name, ABOUT_V
    assert thin_about({"at": "2026-11-01", "about": "Qnity Electronics, Inc"})
    assert not thin_about({"at": "2026-11-01", "about": "x", "v": ABOUT_V})                         # read again already: kept
    assert not thin_about({"at": "2026-11-01", "about": " ".join(["word"] * 40)})                 # full enough: kept
    assert plain_name("Qnity Electronics, Inc.") == "Qnity Electronics" and plain_name("Bharti Airtel Ltd") == "Bharti Airtel"
    assert plain_name("Apple") == "Apple"


def test_the_peer_pe_line_names_its_price_date():
    """GPT review of R31.9: the retail peer median moved from 19.2x to 18.4x between runs a day apart; the line says which close."""
    from app.deck import pe_peer_line
    pp = {"theme": 18.8, "peers": 18.4, "premium": 2.2, "n": 37, "sets": {"sector": 37}, "as_of": "2026-11-09"}
    assert "(prices at the 09 Nov 2026 close)" in pe_peer_line(pp)          # LIVE6-006: day-month (updated on purpose)
    assert "prices at" not in pe_peer_line({k: v for k, v in pp.items() if k != "as_of"})


def test_a_placeholder_sentence_never_ships():
    """GPT review of R31.7: "No listed company is shown for x." reached a published deck; the publication check now drops such a sentence."""
    from app.deck import PLACEHOLDER
    assert PLACEHOLDER.search("No listed company is shown for x.") and PLACEHOLDER.search("Revenue of {layer} rose") and PLACEHOLDER.search("Median nan")
    assert not PLACEHOLDER.search("No listed company is shown for Missile systems.") and not PLACEHOLDER.search("Nonetheless, margins rose.")
    assert not PLACEHOLDER.search("None of these 3 companies' descriptions shows how it earns.")


def test_the_layer_name_guard_reads_a_companys_evidence_from_a_reader_too():
    """The placement passes a reader (a function), not a dict: the guard applies to it the same way."""
    from app.intel import theme_base
    vc = [{"layer": "Fabless chip design", "companies": [{"ticker": "MAT"}, {"ticker": "FAB"}]}]
    words = {"MAT": "A provider of materials and specialty chemicals for semiconductor manufacturing", "FAB": "From its own filings: Quarterly report"}
    by_reader, _ = theme_base.models_from_layer(vc, {"MAT": "unknown", "FAB": "unknown"}, {}, lambda s_: words.get(s_, ""))
    by_dict, _ = theme_base.models_from_layer(vc, {"MAT": "unknown", "FAB": "unknown"}, {}, words)
    assert by_reader == by_dict
    assert by_reader["MAT"] == "unknown" and by_reader["FAB"] not in ("", "unknown")
