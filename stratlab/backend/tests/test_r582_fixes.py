"""R58.2 (lane r582): the flags left on the live R58.1 decks. Each test fails on 21a7a33 (R58.1) and passes after, unless marked a guard.
Fixtures: tests/fixtures/themes_live/r582, the placement inputs of six themes as production served them on 16 Nov 2026 (R58.1, rules 60)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

from app.intel import theme_base as B  # noqa: E402
from app.intel import theme_check as C  # noqa: E402
import release_gate as G  # noqa: E402

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r582"
_ENGINE: dict = {}


def _engine(key):
    if key not in _ENGINE:
        d = G.load(LIVE / f"{key}.json")
        with G.offline():
            _ENGINE[key] = (d, G.engine(d)[0])
    return _ENGINE[key]


def _layers(out):
    return {v["layer"]: v for v in out["value_chain"]}


# ---------- 3. one-company layers: a layer of one gains the companies whose words say its name, else its company goes elsewhere ----------
_ALLOYS = "M manufactures superalloys, titanium alloys and special purpose steel for strategic sectors."
_FORGE = "BF is engaged in the manufacturing and selling of forged and machined components for the auto and industrial sectors."


def _defence(rest_words):
    words = {"M": _ALLOYS, "BF": rest_words, "A": "A builds drones.", "B": "B makes precision parts.", "C": "C makes aerospace parts."}
    vc = [{"layer": "Specialty alloys and forged components", "companies": [{"ticker": "M", "name": "M Ltd"}]},
          {"layer": "Precision aerospace components and drones", "companies": [{"ticker": t, "name": t} for t in "ABC"]},
          {"layer": "Other defence companies", "official": True, "basis": "rest", "companies": [{"ticker": "BF", "name": "BF Ltd"}]}]
    return B.single_layers(vc, lambda s: words.get(s, ""), "Defence", {"M": "Specialty alloys and forged components"})


def test_a_one_company_layer_gains_a_company_whose_words_say_its_name():
    out, rows = _defence(_FORGE)
    lay = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out}
    assert lay["Specialty alloys and forged components"] == ["M", "BF"]
    bf = next(c for v in out for c in v["companies"] if c["ticker"] == "BF")
    assert bf["refit"]["to"] == "Specialty alloys and forged components" and "its own words say what" in bf["refit"]["why"]
    assert rows and rows[0]["ticker"] == "BF"


def test_a_one_company_layer_no_company_joins_is_not_kept_with_one():
    # r58 kept a published layer of one whose member's words say its name; R58.2: its company goes where its words say, else "Other".
    # (updated on purpose, r60: the owner's R59 review P0, a layer the map named whose one company's own words say what it is, in a line a
    # deck prints, stays with it, said to be one company, with no statistic; one whose words don't say it still folds)
    out, rows = _defence("BF makes household fans.")
    lay = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out}
    assert lay["Specialty alloys and forged components"] == ["M"] and not rows
    kept = next(v for v in out if v["layer"] == "Specialty alloys and forged components")
    assert "one company" in kept["single_kept"]
    words = {"M": "M makes household fans and kitchen appliances.", "A": "A builds drones.", "B": "B makes precision parts.", "C": "C makes aerospace parts."}
    vc = [{"layer": "Specialty alloys and forged components", "companies": [{"ticker": "M", "name": "M Ltd"}]},
          {"layer": "Precision aerospace components and drones", "companies": [{"ticker": t, "name": t} for t in "ABC"]},
          {"layer": "Other defence companies", "official": True, "basis": "rest", "companies": []}]
    out, rows = B.single_layers(vc, lambda s: words.get(s, ""), "Defence")
    lay = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out}
    assert "Specialty alloys and forged components" not in lay
    assert "M" in lay["Other defence companies"] and rows[0]["ticker"] == "M" and rows[0]["to"] == "Other defence companies"


def test_the_live_defence_and_insurance_layers_of_one_are_gone():
    # (updated on purpose, r60: the owner's R59 review P0 and the independent review of the live R59 Defence deck: HAL, whose own words
    # say it "designs, manufactures ... aircraft, helicopters", stays the one company of "Aircraft and helicopter manufacturing", said to be
    # one company; a layer of one stays only on its company's words, and no layer is lost unsaid)
    d, out = _engine("defence")
    named = [v for v in out["value_chain"] if not v.get("official")]
    assert all(v.get("single_kept") for v in named if len(v["companies"]) == 1)
    hal = next((v, c) for v in out["value_chain"] for c in v["companies"] if c["ticker"] == "HAL")
    assert hal[0]["layer"] == "Aircraft and helicopter manufacturing" and hal[0].get("single_kept")
    assert not G.lost_layers(d, out["value_chain"])                    # moved out with the layer named and why


def test_the_figures_window_never_holds_one_company_of_a_layer():
    big = [{"ticker": f"Z{i}", "cap": 1000 - i, "placed": "words"} for i in range(4)]
    m = {"value_chain": [{"layer": "Big layer", "companies": big},
                         {"layer": "Payment networks", "companies": [{"ticker": "P1", "cap": 999, "placed": "words"},
                                                                      {"ticker": "P2", "cap": 5, "placed": "words"},
                                                                      {"ticker": "P3", "cap": 4, "placed": "words", "model_out": "other"},
                                                                      {"ticker": "P4", "cap": 3, "placed": "words"}]}]}
    got = B.for_figures(m, cap=3)[0]
    pay = next(v for v in got["value_chain"] if v["layer"] == "Payment networks")
    assert [c["ticker"] for c in pay["companies"]] == ["P1", "P2", "P4"]       # those in its figures first, up to WINDOW_LAYER_MIN
    assert [c["ticker"] for c in next(v for v in got["value_chain"] if v["layer"] == "Big layer")["companies"]] == ["Z0", "Z1", "Z2"]
    small = {"value_chain": [{"layer": "Two only", "companies": [{"ticker": "T1", "cap": 9, "placed": "words"}, {"ticker": "T2", "cap": 8, "placed": "words"}]}]}
    assert len(B.for_figures(small, cap=1)[0]["value_chain"][0]["companies"]) == 2           # (guard) a layer gains only companies it has


def test_the_gate_fails_any_layer_of_one_company():
    # (updated on purpose, r60: the owner's R59 review P0, a layer of one company whose own words say what it is in a line a deck prints
    # stands, so the gate fails only one whose words don't: "Alpha reinsures insurers" now passes, a layer its member's words say nothing
    # of still fails)
    d = {"theme": "Widgets", "evidence": {"A": "Alpha reinsures insurers.", "B": "Beta runs hotels and resorts in three countries."},
         "facts": {}, "placements": {},
         "value_chain": [{"layer": "Reinsurance", "companies": [{"ticker": "A", "name": "Alpha"}]},
                         {"layer": "Cold chain operators", "companies": [{"ticker": "B", "name": "Beta"}]},
                         {"layer": "Other widget companies", "official": True, "basis": "rest", "companies": [{"ticker": "D", "name": "Delta"}]}]}
    found = [f for f in G.checks(d, d["value_chain"], {}) if f["fail"] == "one-company layer"]
    assert [f["subject"] for f in found] == ["“Cold chain operators”"]


# ---------- 1. Hospitals: a layer whose name says contract research is read as earning fees for projects ----------
def test_a_name_that_says_contract_research_states_project_fees():
    assert C.name_models("Contract research and life-science services") == {"project_services"}
    assert "project_services" not in C.name_models("Contract research and manufacturing services")      # (guard) both, so neither
    assert C.name_models("Regional hospital groups") == set()                                               # (guard)


def test_the_live_contract_research_layer_holds_most_of_its_companies_in_its_figures():
    _, out = _engine("hosp")
    v = _layers(out)["Contract research and life-science services"]
    assert v["model"]["family"] == "services"
    inside = [c for c in v["companies"] if not c.get("model_out")]
    assert len(inside) * 2 >= len(v["companies"]), [(c["ticker"], c.get("out_why")) for c in v["companies"]]


# ---------- 1. Consumer retail: a map pick whose words name no other layer's business is no "another business" ----------
def test_the_live_specialty_retailers_are_not_left_out_as_another_business():
    _, out = _engine("retail")
    v = _layers(out)["Single-category specialty retailers"]
    unfit = [c["ticker"] for c in v["companies"] if isinstance(c.get("unfit"), dict)]
    assert "LESL" not in unfit and "FLWS" not in unfit, unfit          # pool supplies, flowers: their words name no other layer's business
    inside = [c for c in v["companies"] if not c.get("model_out")]
    assert len(inside) * 2 >= len(v["companies"])


def test_a_company_whose_words_say_another_layer_is_still_left_out():
    # (guard) sold_what's unfit stays for a map pick whose own words say what another layer sells
    words = {"X": "X runs a chain of pet supply stores selling pet food and pet care products.",
             "Y": "Y sells flowers and gifts online.", "W": "W sells pet food and pet supplies."}
    out = [{"layer": "Garden and floral retailers", "description": "", "companies": [{"ticker": "Y", "name": "Y"}, {"ticker": "X", "name": "X"}]},
           {"layer": "Pet supply retailers", "description": "", "companies": [{"ticker": "W", "name": "W"}]},
           {"layer": "Other retail companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    placed = {"X": "Garden and floral retailers", "Y": "Garden and floral retailers", "W": "Pet supply retailers"}
    got = B.sold_what(out, placed, lambda v: False, lambda cos: "", lambda c: "", lambda c: words.get(c.get("ticker"), ""),
                      B.kind_stems("Consumer retail"), "Consumer retail", {"X": "Pet supply retailers"}, None, {})
    x = next(c for v in got for c in v["companies"] if c["ticker"] == "X")
    assert isinstance(x.get("unfit"), dict) or isinstance(x.get("refit"), dict)


# ---------- 2. layer words: a name none of its companies' lines say ----------
def test_the_live_media_us_layer_takes_a_name_its_companies_lines_say():
    d, out = _engine("usmedia")
    v = next(v for v in out["value_chain"] if any(c["ticker"] == "ROKU" for c in v["companies"]))
    assert v["layer"] != "Connected-TV platforms and radio broadcasting"
    lines = [B.layer_line("", d["evidence"].get(c["ticker"]) or "", c.get("name") or "", v["layer"]) for c in v["companies"]]
    assert any(lines), v["layer"]


def test_a_layer_named_by_a_way_of_earning_none_of_whose_companies_say_it_is_not_made():
    d, out = _engine("textiles")
    assert "Resale and distribution" not in _layers(out)
    fe = G.checks(d, out["value_chain"], d.get("placements") or {})
    assert not [f for f in fe if f["fail"] in ("layer words", "layer lost")]
    vedant = next(c for v in out["value_chain"] for c in v["companies"] if c["ticker"] == "MANYAVAR")
    # (updated on purpose, r60: the replay's recover_origin now finds Vedant's map layer by the stored result the r60 rules reproduce
    # differently (a way of earning never takes a company out of a layer its words name: theme_base.by_how_back), so where it starts is the
    # harness's guess; what holds is that it is in no "Resale and distribution" and its place carries the reason)
    assert vedant["refit"]["why"]


# ---------- the gate's replay: a layer the contract renamed in place with its words changed ----------
def test_a_layer_the_contract_renamed_in_place_is_handed_on_under_its_map_name():
    d = {"theme": "T", "kept": {"assign": {"A": {"layer": "Commercial and business lenders", "by": "ai"}}},
         "placements": {"contract": {"layers": [{"layer": "Commercial and business lenders", "renamed": "Commercial and business banks"}]}},
         "value_chain": [{"layer": "Commercial and business banks", "aka": ["Commercial and business lenders"], "companies": [{"ticker": "A"}]}]}
    assert [v["layer"] for v in G.pre_map(d)["value_chain"]] == ["Commercial and business lenders"]


def test_the_live_regional_banks_replay_matches_the_stored_placement():
    d, out = _engine("regbanks")
    stored = {s: x[0] for s, x in G.rows_of(d["value_chain"]).items()}
    assert {s: x[0] for s, x in G.rows_of(out["value_chain"]).items()}.get("COLB") == stored["COLB"]


# ---------- 5. Biotech: a company the words placement left in no layer before its words were stored ----------
def test_a_company_left_in_other_before_its_words_were_stored_is_placed_by_them():
    words = {"N": "N is a clinical-stage biotechnology company developing gene editing therapies for rare diseases.",
             "R": "R is a clinical-stage biotechnology company developing gene editing medicines.",
             "Q": "Q is a holding company."}
    vc = [{"layer": "Gene editing developers", "companies": [{"ticker": "G1"}, {"ticker": "G2"}]},
          {"layer": "Other biotech companies", "official": True, "basis": "rest", "companies": [
              {"ticker": "N", "name": "N Inc", "placed": "words"},
              {"ticker": "Q", "name": "Q Inc", "placed": "words"},
              {"ticker": "R", "name": "R Inc", "placed": "words", "refit": {"from": "Gene editing developers", "to": "", "why": "a rule's"}}]}]
    out, rows = B.words_from_other(vc, lambda s: words.get(s, ""), "Biotech")
    lay = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out}
    assert lay["Gene editing developers"] == ["G1", "G2", "N"]
    assert lay["Other biotech companies"] == ["Q", "R"]          # no words of a layer; moved there by a rule with its reason
    assert rows[0]["to"] == "Gene editing developers" and "its own words say" in rows[0]["why"]


# ---------- 4. Logistics: a description-verified company with no line to show is not "no description in its own words" ----------
def test_a_description_verified_company_with_no_line_is_said_apart_from_one_with_no_words():
    from app import deck
    v = {"evidence": {"A": "description_verified", "B": "industry_code_supported"},
         "layers": [{"layer": "Shipping", "companies": [{"symbol": "A", "name": "A Maritime Ltd", "revenue": 10.0, "what": ""},
                                                       {"symbol": "B", "name": "B Roadways Ltd", "revenue": 5.0, "what": ""},
                                                       {"symbol": "C", "name": "C Ports Ltd", "revenue": 7.0, "what": "C runs ports."}]}]}
    assert deck.without_words(v) == ["B Roadways Ltd"]
    assert deck.without_words(v, described=True) == ["A Maritime Ltd"]
    said = deck.described_said(["A Maritime"])
    assert "description-verified" in said and "no description" not in said


# ---------- 1. Media: a cable operator whose principal words name its layer's work is of the theme's work ----------
def test_a_cable_operator_in_a_cable_distribution_layer_is_not_an_adjacent_connectivity_operator():
    from app.intel import theme_data as D
    adj = {"kind": "telecom and broadband operators", "where": "description",
           "text": "GTPL Hathway Limited is India's largest MSO providing Digital Cable TV services and is one of the largest Private "
                   "Wireline Broadband service provider in India"}
    assert D.own_layer_work(adj, "Cable and satellite distribution", adj["text"])
    # (guard) a layer whose name says the kind's own words (the US Media map's broadband layer) keeps its operators adjacent
    charter = {**adj, "text": "We are a leading broadband connectivity company; we have evolved from providing cable TV to streaming"}
    assert not D.own_layer_work(charter, "Cable and broadband connectivity providers", charter["text"])
    # (guard) adjacent by its official industry: not this rule's
    assert not D.own_layer_work({**adj, "where": "industry"}, "Cable and satellite distribution", adj["text"])
