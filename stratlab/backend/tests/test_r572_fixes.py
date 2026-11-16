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
    # round 2 (updated on purpose): one with no words and no official industry stays too, its answer alone moving nothing (test_r2_6)
    assert [c["ticker"] for c in other["companies"]] == ["ABT", "NW"] and [x["ticker"] for x in pl2["layer_no"]] == ["ABT", "NW"]
    left = {x["ticker"]: x for x in pl2["dropped"]}
    assert left["BNK"]["said"] == "scope" and left["BNK"]["scope"].startswith("another business: its own words say “A Bank is a lender")
    assert "NW" not in left
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


def test_1f_a_largest_map_pick_held_unfit_only_for_want_of_fitting_words_is_in_the_figures_and_a_small_one_stays_out():
    lay = "Ad-funded consumer platforms and games"
    vc = [{"layer": lay, "description": "", "companies": [
        {"ticker": "BIG", "name": "Big", "industry": "Computer Programming", "cap": 3000.0, "placed": "ai", "unfit": {"layer": lay, "why": "w"}},
        {"ticker": "SM", "name": "Sm", "industry": "Computer Programming", "cap": 1.0, "placed": "ai", "unfit": {"layer": lay, "why": "w"}},
        {"ticker": "P1", "name": "P1", "industry": "Computer Programming", "cap": 900.0},
        {"ticker": "P2", "name": "P2", "industry": "Computer Programming", "cap": 800.0},
        {"ticker": "P3", "name": "P3", "industry": "Computer Programming", "cap": 700.0}]},
          {"layer": "Other software companies", "description": "", "official": True, "basis": "rest",
           "companies": [{"ticker": f"O{i}", "name": f"O{i}", "industry": "Prepackaged Software", "cap": 1000.0 + i} for i in range(10)]}]
    ev = {"BIG": "Big Inc. is a technology holding company; it is the parent of a search engine and several former subsidiaries.",
          "SM": "Sm Inc. is a technology company.", "P1": "P1 runs an online platform funded by advertising.",
          "P2": "P2 runs an online platform funded by advertising.", "P3": "P3 runs an online platform funded by advertising."}
    models = {"P1": "platform", "P2": "platform", "P3": "platform"}
    out = B.by_model(vc, models, "Software", confidence={s: "high" for s in models}, evidence_of=lambda s: ev.get(s, ""))
    got = {c["ticker"]: c for v in out for c in v["companies"]}
    assert got["BIG"].get("by_map") and not got["BIG"].get("out_why")
    assert got["SM"].get("out_why") == "unfit"


# ---------- round 2 ----------
# the stored words of the live R57.1 Software input (lanes19/r572/in/software.json), their first 400 characters
SW_WORDS = {
    'SHOP': 'Shopify Inc. is a Canadian multinational e-commerce company headquartered in Ottawa, Ontario, that operates a cloud e-commerce management platform (CEMP) for retail point-of-sale systems. The company has over five million customers and processed US$292.3 billion in transactions in 2024, of which 57% was in the United States. Major customers include Tesla, LVMH, Nestlé, PepsiCo, AB InBev, Kraft Hei',
    'TWLO': 'Twilio Inc. is an American cloud communications company based in San Francisco, California, which provides programmable communication tools for making and receiving phone calls, sending and receiving text messages, and performing other communication functions using its web service APIs. Founded in 2008, the company received multiple rounds of funding prior to its 2016 initial public offering. Twil',
    'MSFT': 'Microsoft Corporation is an American multinational technology conglomerate headquartered in Redmond, Washington. The company became influential in the rise of personal computers through software like Windows and has since expanded into areas such as Internet services, cloud computing, artificial intelligence and video gaming among others. A Big Tech company, Microsoft is the largest software compa',
    'ORCL': 'Oracle Corporation is an American multinational technology company headquartered in Austin, Texas. Co-founded in Santa Clara, California, in 1977 by Bob Miner, Ed Oates, and current chairman of the board and chief technology officer Larry Ellison, Oracle is among the 50 largest companies in the world by market cap, and ranked 52nd on the Forbes Global 2000 as of 2026. Through our worldwide sales f',
    'CRWV': 'CoreWeave, Inc. is an American cloud-computing company based in Livingston, New Jersey. As of 2026, the company operates 51 AI data centers, specialized data centers designed for higher parallel computing performance via heavy use of graphics processing units (GPUs). Such data centers are vital to the training and running of generative AI models, such as large language models and text-to-video mod',
    'NBIS': 'Nebius Group N.V., headquartered in Amsterdam, is a technology company that provides artificial intelligence infrastructure. It is headquartered in Amsterdam, Netherlands with offices in Israel and the United States. Nebius, a global AI cloud platform, delivers a unified full-stack AI cloud that spans the complete AI journey – from compute capacity to software and services that enable fast and eff',
}


def test_r2_1_a_compute_layer_keeps_only_companies_whose_words_say_computing_and_re_places_the_rest_in_the_theme():
    lay = "Cloud and AI compute providers (larger)"
    vc = [{"layer": lay, "description": "", "companies": [
              {"ticker": "MSFT", "name": "Microsoft", "cap": 3e6},                                    # the map's own pick
              {"ticker": "ORCL", "name": "Oracle", "cap": 6e5},                                       # the map's own pick, words say no computing
              {"ticker": "SHOP", "name": "Shopify", "cap": 2e5, "moved": True, "placed": "ai", "model": "software"},
              {"ticker": "TWLO", "name": "Twilio", "cap": 3e4, "moved": True, "placed": "ai", "model": "software"},
              {"ticker": "CRWV", "name": "CoreWeave", "cap": 3e4, "moved": True, "placed": "ai"},
              {"ticker": "NBIS", "name": "Nebius", "cap": 2e4, "placed": "ai"}]},
          {"layer": "Data and developer infrastructure software", "description": "APIs, developer tools and communication platforms for "
           "programmable communication", "companies": [{"ticker": "D1", "name": "D1"}, {"ticker": "D2", "name": "D2"}]},
          {"layer": "Enterprise application subscriptions", "description": "", "companies": [{"ticker": "E1", "name": "E1"}, {"ticker": "E2", "name": "E2"}],
           "model": {"id": "software"}},
          {"layer": "Other software companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    assert B.says_compute(SW_WORDS["CRWV"]) and B.says_compute(SW_WORDS["NBIS"]) and B.says_compute(SW_WORDS["MSFT"])
    assert not B.says_compute(SW_WORDS["SHOP"]) and not B.says_compute(SW_WORDS["TWLO"])
    out, rows = B.compute_fit(vc, lambda s: SW_WORDS.get(s), "Software")
    where = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert {where[s] for s in ("MSFT", "ORCL", "CRWV", "NBIS")} == {lay}
    assert where["TWLO"] == "Data and developer infrastructure software" and where["SHOP"] == "Other software companies"
    assert {r["ticker"] for r in rows} == {"SHOP", "TWLO"} and all("“cloud” said of another product" in r["why"] for r in rows)


def test_r2_2_a_move_with_no_reason_says_what_its_own_words_say_and_a_move_between_halves_is_a_split():
    entries = [{"moved": [{"symbol": "GD", "name": "General Dynamics", "from": "Naval and defense shipbuilding", "to": "Defense prime contracting"},
                          {"symbol": "H", "name": "H", "from": "Content production (larger)", "to": "Content production (smaller)"},
                          {"symbol": "K", "name": "K", "from": "A", "to": "B", "why": "its own words say what “B” is"}]}]
    got = TC.reasoned(entries, lambda s: "General Dynamics is a developer and producer of advanced military equipment. It also builds jets."
                      if s == "GD" else None, lambda s: "")[0]["moved"]
    assert got[0]["why"] == "its own words say “General Dynamics is a developer and producer of advanced military equipment”"
    assert got[1]["why"] == "the same layer, split into halves by market value" and got[2]["why"] == "its own words say what “B” is"


def test_r2_3_a_layer_split_into_its_halves_is_said_as_a_split_never_as_gone():
    snap = {"layers": ["Content production", "Radio"], "cos": {f"C{i}": [f"C{i}", 0] for i in range(6)} | {"R": ["R", 1]}}
    dive = {"layers": [{"layer": "Content production (larger)", "companies": [{"symbol": f"C{i}", "name": f"C{i}"} for i in range(3)]},
                       {"layer": "Content production (smaller)", "companies": [{"symbol": f"C{i}", "name": f"C{i}"} for i in range(3, 6)]},
                       {"layer": "Radio", "companies": [{"symbol": "R", "name": "R"}]}]}
    lost = TC.lost_layers(snap, dive)
    assert lost == [{"layer": "Content production", "n": 6, "halves": ["Content production (larger)", "Content production (smaller)"]}]
    line = TC.control_line({"informative": 1, "placed": 9, "control": {"low": True, "split": lost}})
    assert "“Content production” (6 companies) split into “Content production (larger)” and “Content production (smaller)”" in line
    assert "gone" not in line


def test_r2_4_a_map_layer_whose_name_its_companies_never_say_takes_the_industry_their_filings_say():
    vc = [{"layer": "Commercial airframe integration", "description": "", "companies": [
        {"ticker": "BA", "name": "Boeing Co", "industry": "Aircraft", "cap": 2e5}, {"ticker": "EMBJ", "name": "Embraer S.A.", "industry": "Aircraft", "cap": 3e4}]}]
    ev = {"BA": "The Boeing Company designs and manufactures airplanes, rotorcraft, rockets, satellites and missiles worldwide.",
          "EMBJ": "We are the leading manufacturer of jets with up to 150 seats in the world, based on the number of aircraft delivered over the last decade."}
    out, rows = B.truthful_layers(vc, {}, lambda s: ev.get(s, ""), "Aerospace and defense")
    assert out[0]["layer"] == "Commercial airframe integration (aircraft)" and "Commercial airframe integration" in out[0]["aka"]
    assert B.says_name(out[0]["layer"], ["Industry: Aircraft. " + ev["BA"]]) and B.says_name("Commercial airframe integration", list(ev.values())) is False


def test_r2_4b_the_design_of_processor_cores_is_no_fabless_chip_maker_s_words():
    arm = ("Arm Holdings plc is a British semiconductor and software design company, whose primary business is the design of central processing "
           "unit (CPU) cores that implement the ARM architecture family of instruction sets.")
    assert C.stated_model("Industry: Semiconductors. " + arm) != "fabless"
    assert C.stated_model("Industry: Semiconductors. Q Inc. designs and sells chips that foundries make for it.") == "fabless"


def test_r2_5_a_layer_page_under_min_5_rows_goes_on_to_a_continued_page_and_a_hotel_named_layer_says_why_it_has_no_measures():
    from app import deck
    rows_ = [{"layer": "Restaurants and food service and hotels and resorts", "ops": None, "model": {"id": "consumer_services"}},
             {"layer": "Quick-service chains", "ops": None, "model": {"id": "consumer_services"}}]
    assert deck.profile_short(rows_) == [("Restaurants and food service and hotels and resorts", "hotel operators")]
    said = deck.profile_summary([], deck.profile_short(rows_))
    assert said == ("Operating profiles: Restaurants and food service and hotels and resorts, hotel operators: fewer than half of its companies "
                    "are hotel operators, so no measures of theirs are shown.")


def test_r2_5b_deck_check_reads_a_coverage_row_s_last_layer_and_a_state_only_in_its_rows():
    page = ("THEME · COVERAGE\nCoverage\n companies with figures: Large national banks 4 of 4 · Government-owned infrastructure financiers 2 of 2 "
            "Each figure EBITDA margin 12\n In common: they earn mainly from interest. Its companies earn the same way as those of “Large national "
            "banks”, “Government-owned infrastructure financiers”; the map keeps them as separate layers.\n\f"
            "THEME · APPENDIX\nFigure sources\n3 checked figures, 3 verified: where each comes from\n A Corp   Net margin 1.0%, verified\n"
            " Verified: the lines checked; arithmetic reproduced: net profit over revenue worked out again.\n\f")
    r = DC.check_text(page)
    assert not r["counts"].get("stale layer") and not r["counts"].get("verified count")
    bad = page.replace("Net margin 1.0%, verified", "Net margin 1.0%, arithmetic reproduced")
    assert DC.check_text(bad)["counts"].get("verified count") == 1


def test_r2_6_a_removal_with_no_words_is_decided_by_its_industry_and_with_neither_the_member_stays():
    vc = [{"layer": "Card issuers", "description": "", "companies": [{"ticker": "M", "name": "M"}]},
          {"layer": "Other payments companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    pl = {"dropped": [{"ticker": "NONE", "name": "None Co", "groups": ["Card issuers"], "said": "no"},
                      {"ticker": "STEEL", "name": "Steel Co", "groups": ["Card issuers"], "said": "no"},
                      {"ticker": "PAY", "name": "Pay Co", "groups": ["Card issuers"], "said": "no"}]}
    facts = {"STEEL": {"industry": "Basic Materials > Steel Works"}, "PAY": {"industry": "Services > Payment Processing"}}
    vc2, pl2 = B.layer_answer_removals(vc, pl, lambda s: None, "Payments and fintech", lambda s: facts.get(s) or {})
    other = {c["ticker"]: c for v in vc2 if v.get("basis") == "rest" for c in v["companies"]}
    assert set(other) == {"NONE", "PAY"} and "moves nothing" in other["NONE"]["theme"]["why"]
    assert [(x["ticker"], x["said"]) for x in pl2["dropped"]] == [("STEEL", "scope")] and "filed under Steel Works" in pl2["dropped"][0]["scope"]


def test_r2_6b_a_split_move_into_a_layer_its_words_never_say_goes_to_other_unless_it_was_published_there():
    vc = [{"layer": "Engineering R&D services", "description": "", "companies": [
              {"ticker": "E1", "name": "E1"}, {"ticker": "RID", "name": "Riddhi Corporate Services Ltd", "moved": True, "industry": "IT Enabled Services"},
              {"ticker": "PUB", "name": "Pub Ltd", "moved": True, "industry": "IT Enabled Services"}]},
          {"layer": "Other IT service companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    words = {"RID": "Riddhi offers document management, inbound and outbound contact centre, data entry and verification services.",
             "PUB": "Pub offers data entry and verification services."}
    out, rows = B.unsaid_moves(vc, lambda s: words.get(s), "IT services", {"PUB": "Engineering R&D services"})
    where = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert where["RID"] == "Other IT service companies" and where["PUB"] == "Engineering R&D services" and [r["ticker"] for r in rows] == ["RID"]
