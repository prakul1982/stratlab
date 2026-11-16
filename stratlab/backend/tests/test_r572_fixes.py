"""Lane r572 (R57.2): the live R57.1 decks made to pass, generically. Each test fails on origin/main 6a6a8d2 and passes after."""
import importlib.util
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
spec = importlib.util.spec_from_file_location("deck_check_r572", PATH)
DC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DC)

L = " " * 54
# the live R57.1 Cybersecurity deck's change-log row, as pdftotext -layout prints it: the row's label and count in the left columns, interleaved
# with the lines of its text
LOG = ("THEME · COVERAGE\nCoverage\n\n"
       f"{L}On 15 Nov 2026, the latest change (no change since), against the version stored before it, after a re-check under new\n"
       f"{L}placement rules: removed 1: Example Corp (another business: its own words say it makes design software); moved between layers 1: Cyberark Software Ltd (from “Identity\n"
       " Since the previous\n"
       f"                               7{' ' * 22}access and broad enterprise software (larger)” to “Identity access and broad enterprise software”); layers changed 1:\n"
       " version\n"
       f"{L}“Identity access and broad enterprise software (smaller)” renamed “Identity access and broad enterprise software”, and a longer tail.\n\f")


def test_9_a_left_column_label_is_never_read_into_the_running_text_beside_it():
    flat = DC.flat_text(LOG.split("\f")[0])
    assert "Since the previous version 7 On 15 Nov 2026" in flat
    assert "(from “Identity access and broad enterprise software (larger)” to “Identity access and broad enterprise software”)" in flat
    r = DC.check_text(LOG)
    assert not r["counts"].get("move unexplained"), r["findings"]


def test_9b_the_rule_itself_is_not_loosened_a_real_unexplained_move_in_that_layout_is_still_found():
    bad = LOG.replace("to “Identity access and broad enterprise software”); layers", "to “Cloud security platforms”); layers")
    r = DC.check_text(bad)
    assert r["counts"].get("move unexplained") == 1
    assert "(from “Identity access and broad enterprise software (larger)” to “Cloud security platforms”)" in r["findings"][0]["text"] or any(
        "Cloud security platforms" in f["text"] for f in r["findings"] if f["kind"] == "move unexplained")


# ---------- the placement, replayed on the fresh live inputs (tests/fixtures/themes_live/r572: the placement inputs as production served
# them on 16 Nov under rules 57, with the stored words of the companies the map's check left out added from earlier inputs) ----------
import json            # noqa: E402
import pathlib         # noqa: E402
import sys             # noqa: E402

import pytest          # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
import release_gate as G          # noqa: E402

from app.intel import theme_base as B          # noqa: E402
from app.intel import theme_changes as TC      # noqa: E402
from app.intel import theme_check as C         # noqa: E402
from app.intel import theme_data as TD         # noqa: E402

FIX = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r572"
_OUT: dict = {}


def engine(key):
    if key not in _OUT:
        d = G.load(FIX / f"{key}.json")
        with G.offline():
            _OUT[key] = (d, G.engine(d)[0])
    return _OUT[key]


def row(key, sym):
    _, out = engine(key)
    return next((v, c) for v in out["value_chain"] for c in v["companies"] if c["ticker"] == sym)


def test_0_the_gate_finds_the_largest_left_out_on_the_live_placement_and_none_on_the_engine_s():
    d = G.load(FIX / "restaurants.json")
    g = G.gate(d)
    stored = {f["subject"] for f in g["fails"] if f["fail"] == "largest left out" and f["side"] == "stored"}
    assert {"McDonalds Corp (MCD)", "Yum Brands Inc (YUM)", "Restaurant Brands International Inc. (QSR)"} <= stored
    assert not [f for f in g["fails"] if f["fail"] == "largest left out" and f["side"] != "stored"]


@pytest.mark.parametrize("sym", ["MCD", "YUM", "QSR"])
def test_1a_the_franchisors_are_in_the_figures_of_the_layer_their_name_states(sym):
    v, c = row("restaurants", sym)
    assert v["layer"] == "Franchisors and brand licensors" and v["model"]["id"] == "franchising"
    assert not c.get("out_why") and not c.get("model_out")


@pytest.mark.parametrize("key,sym", [("usoil", "SLB"), ("usoil", "BKR"), ("usoil", "HAL"), ("usoil", "ENB"), ("usmedia", "DIS"),
                                     ("logistics", "TVSSCS")])
def test_1b_the_largest_companies_the_map_placed_are_in_their_layer_s_figures_unless_their_words_contradict_it(key, sym):
    v, c = row(key, sym)
    assert not v.get("official") and not c.get("out_why") and c.get("by_map")


def test_1c_a_largest_company_whose_own_words_state_another_way_stays_out_as_that_way():
    vc = [{"layer": "Franchisors", "description": "", "companies": [
        {"ticker": "A", "name": "A", "industry": "Eating Places", "cap": 900.0},
        {"ticker": "B", "name": "B", "industry": "Eating Places", "cap": 10.0},
        {"ticker": "C", "name": "C", "industry": "Eating Places", "cap": 9.0},
        {"ticker": "D", "name": "D", "industry": "Eating Places", "cap": 8.0}]}]
    ev = {"A": "A is a contract manufacturer of frozen foods for other brands.", "B": "B is a franchisor of sandwich restaurants.",
          "C": "C is a franchisor of pizza restaurants.", "D": "D is a franchisor of burger restaurants."}
    models = {"A": "franchising", "B": "franchising", "C": "franchising", "D": "franchising"}
    conf = {"A": "low", "B": "high", "C": "high", "D": "high"}
    out = B.by_model(vc, models, "Restaurants", confidence=conf, evidence_of=lambda s: ev.get(s, ""))
    a = next(c for v in out for c in v["companies"] if c["ticker"] == "A")
    assert a.get("out_why") and not a.get("by_map")


def test_1d_a_coffee_shop_is_no_retailer_s_words():
    assert "retail" not in C.words_models("A fast food holding company formed by the merger of a burger chain and a coffee shop and fast food "
                                          "restaurant chain.")
    assert "retail" in C.words_models("A chain of 400 grocery shops across the state.")


def test_1e_the_deck_says_why_a_company_is_in_its_layer_s_figures_as_the_map_placed_it():
    said = TD.comparison_said({"in": True, "by_map": True}, {"model": {"id": "franchising", "family": "franchising"}})
    assert "the map placed it here" in said and "name no other way of earning" in said
    said = TD.comparison_said({"in": True, "by_map": True, "no_words": True}, {"model": {"id": "franchising", "family": "franchising"}})
    assert "largest companies" in said and "no description of its own is stored" in said


def test_3_a_removal_the_map_no_longer_names_says_what_its_own_words_say():
    tw = B.kind_stems("Semiconductors Fabless chip design Foundry and memory manufacturing")
    why = TC.unnamed_why("no longer in the theme's map", "Adobe Inc. is an American computer software company. It makes design software.", "", tw)
    assert why == "another business: its own words say “Adobe Inc. is an American computer software company”"
    assert TC.unnamed_why("no longer in the theme's map", None, "Prepackaged Software", tw) == \
        "business membership: the theme's map no longer names it; filed under Prepackaged Software"
    entries = [{"removed": [{"symbol": "ADBE", "name": "ADOBE INC.", "layer": "X", "why": "no longer in the theme's map"},
                            {"symbol": "Q", "name": "Q", "layer": "X", "why": "another business (filed under Y)"}]}]
    got = TC.reasoned(entries, lambda s: "Adobe Inc. is an American computer software company." if s == "ADBE" else None, lambda s: "", tw)
    assert got[0]["removed"][0]["why"].startswith("another business: its own words say") and got[0]["removed"][1]["why"] == "another business (filed under Y)"


def test_3b_a_removal_on_one_layer_s_answer_is_decided_by_the_company_s_own_words():
    vc = [{"layer": "Implantable devices", "description": "", "companies": [{"ticker": "M", "name": "M", "industry": "Surgical"}]},
          {"layer": "Other medical device companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    pl = {"dropped": [{"ticker": "ABT", "name": "Abbott", "groups": ["Implantable devices"], "said": "no"},
                      {"ticker": "BNK", "name": "A Bank", "groups": ["Implantable devices"], "said": "no"},
                      {"ticker": "NW", "name": "No Words", "groups": ["Implantable devices"], "said": "no"}]}
    words = {"ABT": "Abbott Laboratories makes medical devices, diagnostics and nutrition products sold worldwide.",
             "BNK": "A Bank is a lender that takes deposits and makes loans to households across the region."}
    vc2, pl2 = B.layer_answer_removals(vc, pl, lambda s: words.get(s), "Medical devices", lambda s: {})
    other = next(v for v in vc2 if v.get("basis") == "rest")
    assert [c["ticker"] for c in other["companies"]] == ["ABT"] and [x["ticker"] for x in pl2["layer_no"]] == ["ABT"]
    left = {x["ticker"]: x for x in pl2["dropped"]}
    assert left["BNK"]["said"] == "scope" and left["BNK"]["scope"].startswith("another business: its own words say “A Bank is a lender")
    assert left["NW"]["said"] == "no"
    assert "another business" in TC.dropped_why(left["BNK"])


def test_4_a_parent_and_its_subsidiary_filer_of_the_same_figures_are_one_company():
    rows = [{"symbol": "TRP", "name": "TC Energy Corp", "year": 2025, "revenue": 10681.0151, "profit": 2470.0, "cap": 67425.3},
            {"symbol": "TCPA", "name": "Transcanada Pipelines Ltd", "year": 2025, "revenue": 10679.4912, "profit": 2466.0, "cap": 21389.2},
            {"symbol": "OTH", "name": "Other Pipelines Inc", "year": 2025, "revenue": 10000.0, "profit": 2466.0, "cap": 9000.0}]
    about = {"TRP": "TC Energy Corporation is a Canadian energy company whose focus is pipelines.", "TCPA": "From its own filings: Annual report (40-F).",
             "OTH": None}
    assert TD.same_company(rows, about=lambda s: about.get(s)) == {"TCPA": "TRP"}


def test_5_a_one_company_layer_stays_only_when_the_map_named_it_and_its_words_say_it():
    vc = [{"layer": "Reinsurance", "description": "", "companies": [{"ticker": "RE", "name": "Re", "cap": 5.0}]},
          {"layer": "Cold chain operators", "description": "", "companies": [{"ticker": "CC", "name": "Cc", "cap": 4.0}]},
          {"layer": "Data centres, hosting and networks", "description": "", "by_model": True, "companies": [{"ticker": "DC", "name": "Dc", "cap": 3.0}]},
          {"layer": "Freight forwarders", "description": "", "companies": [{"ticker": "F1", "name": "F1"}, {"ticker": "F2", "name": "F2"}]},
          {"layer": "Other logistic companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    words = {"RE": "Re is the country's largest reinsurance company, writing reinsurance for other insurers.",
             "CC": "Cc runs warehouses and trucks for goods that need temperature control; it is a freight forwarder too.",
             "DC": "Dc rents out computing capacity in its data centres."}
    out, rows = B.single_layers(vc, lambda s: words.get(s), "Logistics")
    where = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert where["RE"] == "Reinsurance" and where["CC"] == "Freight forwarders" and where["DC"] == "Other logistic companies"
    assert {r["ticker"] for r in rows} == {"CC", "DC"} and all(r["why"].startswith("a layer of one company") for r in rows)


def test_0b_words_read_after_the_check_place_the_theme_again_with_no_ai(monkeypatch):
    from app.intel import theme_routes as TR
    key = ("US", "restaurants", 1, B.RULES)
    TR._unplaced.clear(), TR._words_since.clear(), TR._replaced_at.clear()
    asked = []

    def placed(region, theme, m, out, ask=None):
        asked.append(ask)
        return {**out, "placements": {"placed": 3}, "value_chain": [{"layer": "L", "companies": [{"ticker": "Y", "out_why": None}]}]}
    monkeypatch.setattr(TR, "placed", placed)
    monkeypatch.setattr(TR, "_stored_evidence", lambda r, s: {"about": "Y is a franchisor."} if s == "Y" else {})
    monkeypatch.setattr(TR.A, "keep", lambda *a, **k: None)
    hit = {"placements": {"checked": True, "industries_by": "ai"}, "value_chain": [{"layer": "L", "companies": [{"ticker": "Y", "out_why": "no_words"}]}],
           "tailwinds": ["t"], "risks": []}
    assert TR.replaced_on_words("US", "Restaurants", {}, key, hit, now=1000.0) is hit           # nothing kept to place again
    TR.keep_unplaced(key, {"value_chain": [{"layer": "L", "companies": [{"ticker": "Y"}]}]})
    assert TR.replaced_on_words("US", "Restaurants", {}, key, hit, now=1000.0) is hit           # no words read since
    assert TR.note_words("US", "Restaurants", ["Y", "Z"]) == 1
    new = TR.replaced_on_words("US", "Restaurants", {}, key, hit, now=1000.0)
    assert asked == [None] and new["value_chain"][0]["companies"][0]["out_why"] is None
    assert new["placements"]["replaced"] == 1 and new["placements"]["industries_by"] == "ai" and new["tailwinds"] == ["t"]
    assert TR.dive_key("US", "Restaurants", {**new, "generated_at": 1})[-1] == "rp1"
