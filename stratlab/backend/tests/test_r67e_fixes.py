"""r67e (R67): the owner's GPT review of the live R65 decks.

P0-1 descriptions checked before use (Fertilizers: Tatva Chintan screened out as a batteries-and-torches maker), P0-2 evidence-backed
placement kept (REITs: Vornado out of "Office landlords" on its 10-K's sentences of how it is held), P0-3 every move between an informative
layer and "Other" with a company-level reason, P1/P2 deck items. Company names here are test data only."""
from app import deck
from app.intel import sec
from app.intel import theme_check as C
from app.intel import theme_routes as TR

FERT = "Fertilizers & agrochemicals Urea producers and mixed chemicals makers Crop protection chemicals"
FMCG = "FMCG Branded personal care Hair oils, soaps and razors"
TATVA = ("Tatva Chintan Pharma Chem Ltd was incorporated in 1996 and it is a manufacturer of a diverse portfolio of structure Directing "
         "Agents, Phase Transfer Catalysts, electrolyte salts for batteries, and Pharmaceutical and Agrochemical Intermediates.")


# ---------- P0-1: a company's printed words are about that company, and its exclusion quotes them ----------
def test_a_kind_named_as_what_its_product_is_for_is_not_its_principal_business():
    """Fails before: Tatva Chintan, a maker of catalysts and intermediates, screened out of Fertilizers as of "batteries, torches and
    electrical goods" for "electrolyte salts for batteries"."""
    assert C.off_scope(TATVA, FERT, "Tatva Chintan Pharma Chem Ltd") is None
    assert C.off_scope("Acme Ltd manufactures electrolytes used in batteries and fuel cells.", FMCG, "Acme Ltd") is None


def test_a_kind_named_after_another_product_of_its_list_is_not_its_principal_business():
    """Fails before: "a producer of carbon, cement and advanced materials" screened out as a cement maker."""
    assert C.off_scope("Rain Industries Ltd (RAIN) is a leading vertically integrated producer of carbon, cement and Advanced materials "
                       "products.", FERT, "Rain Industries Ltd") is None
    # guard: the kind its list names first still screens it out, and the words quoted are its own
    got = C.off_scope("Indo National Ltd is a maker of dry cell batteries, torches and electrical accessories.", FMCG, "Indo National Ltd")
    assert got and got["kind"] == "batteries, torches and electrical goods" and got["quote"] == "dry cell batteries"
    got = C.off_scope("Acme makes dry cell batteries and torches.", FMCG, "Acme Ltd")
    assert got and got["said"] == "dry cell" and got["quote"] == "makes dry cell batteries and torches"


def test_a_screening_reason_never_reads_another_companys_words():
    """Fails before: a stored description opening on another company sharing the first word of its name (an encyclopedia's article on
    "Tatva Batteries Corporation") screens the company out on that company's business."""
    about = ("Tatva Batteries Corporation is a maker of dry cell batteries and torches. It sells them across India. "
             "Tatva Chintan Pharma Chem Ltd manufactures phase transfer catalysts and agrochemical intermediates.")
    assert C.off_scope(about, FMCG, "Tatva Chintan Pharma Chem Ltd") is None


def test_the_deck_quotes_the_words_a_company_is_screened_out_on():
    """Fails before: the deck printed "its principal business is of batteries, torches and electrical goods" with none of its words."""
    v = {"placements": {"off_industry": [{"ticker": "INDONATION", "name": "Indo National Ltd", "industry": "Household Products",
                                          "scope": "batteries, torches and electrical goods", "quote": "dry cell batteries"}]}}
    line = deck.off_industry_line(v)
    assert "its principal business is of batteries, torches and electrical goods: its own words, “dry cell batteries”" in line


# ---------- P0-2: the words a placement reads are the company's words about its work ----------
VORNADO_10K = """<html><body><p>PART I</p><p>ITEM 1. BUSINESS</p>
<p>Acme Realty is a fully-integrated REIT and conducts its business through, and substantially all of its interests in properties are held
by, the Operating Partnership, a Delaware limited partnership. Accordingly, Acme Realty's cash flow and ability to pay dividends to its
shareholders are dependent upon the cash flow of the Operating Partnership and the ability of its direct and indirect subsidiaries to first
satisfy their obligations to creditors. Acme Realty is the sole general partner of and owned approximately 91.3% of the common limited
partnership interest in the Operating Partnership as of December 31, 2025.</p>
<p>We currently own all or portions of:</p><p>New York:</p>
<p>&#8226;51 Manhattan operating properties consisting of:</p>
<p>&#8226;19.2 million square feet of office space in 26 of the properties;</p>
<p>&#8226;2.3 million square feet of street retail space in 45 of the properties;</p>
<p>&#8226;1,331 units in two Manhattan residential properties;</p>
<p>OBJECTIVES AND STRATEGY</p>
<p>Our business objective is to maximize shareholder value. We intend to achieve this objective by continuing to pursue our investment
philosophy and to execute our operating strategies through a superior team of operating and investment professionals.</p>
""" + "<p>" + "Filler sentence about the portfolio and its tenants in the city. " * 30 + "</p><p>ITEM 1A. RISK FACTORS</p></body></html>"


def test_a_10k_opening_passes_over_how_the_company_is_held_and_reads_its_list_of_holdings():
    """Fails before: Vornado's stored words were its 10-K's three sentences on its Operating Partnership, none of its offices, so the
    placement found no office evidence and it went from "Office landlords" to "Other"."""
    got = sec.business_opening(sec.report_lines(VORNADO_10K))
    assert "office space" in got and "Operating Partnership" not in got
    assert got.startswith("We currently own all or portions of: 51 Manhattan operating properties consisting of: 19.2 million square feet")


def test_a_stored_description_that_only_says_how_the_company_is_held_is_read_again_once():
    """Fails before: such a stored description stood for EVIDENCE_DAYS and no reader read the annual report again."""
    held = ("Acme Realty is a fully-integrated REIT and conducts its business through, and substantially all of its interests in properties "
            "are held by, the Operating Partnership, a Delaware limited partnership. Acme Realty is the sole general partner of the "
            "Operating Partnership.")
    got = {"about": held, "at": "2026-11-01T00:00:00+00:00", "v": TR.ABOUT_V}
    assert sec.structure_only(held)
    assert TR.thin_about(got, "US")
    assert not TR.thin_about({**got, "bv": sec.BUSINESS_KEY[1]}, "US")           # read with today's reader: not again
    # guard: words that say what it owns stand
    owns = "We own and operate 26 Manhattan office properties and street retail space. Acme Realty is the general partner of its OP."
    assert not sec.structure_only(owns) and not TR.thin_about({**got, "about": owns}, "US")


# ---------- P0-3: every move between an informative layer and "Other" with a company-level reason ----------
from app.intel import theme_changes as CH          # noqa: E402


def _dive(cos):
    return {"layers": [{"layer": lay, "companies": [{"symbol": s, "name": s} for s in syms]} for lay, syms in cos.items()]}


def test_a_move_of_a_member_past_the_figures_carries_the_placements_reason():
    """Fails before: Biotech's 106 moves out of "Other" said only "still in the theme, outside the largest companies whose figures are
    worked out", no reason for the move."""
    was = CH.snapshot(_dive({"Clinical biotechs": ["X"]}), ["X"], 1, 68, everyone={"X": ["X", "Clinical biotechs"], "Y": ["Y", "Other biotech companies"],
                                                                         "Z": ["Z", "Other biotech companies"]})
    now = CH.snapshot(_dive({"Clinical biotechs": ["X"]}), ["X"], 1, 69,
                      everyone={"X": ["X", "Clinical biotechs"], "Z": ["Z", "Other biotech companies"],
                                "Y": ["Y", "Clinical biotechs", "", "its own words say “clinical-stage” of “Clinical biotechs”"]})
    d = CH.diff(was, now)
    assert d["moved"] == [{"symbol": "Y", "name": "Y", "from": "Other biotech companies", "to": "Clinical biotechs", "outside": True,
                           "why": "its own words say “clinical-stage” of “Clinical biotechs”"}]
    assert "rest_mwhy" not in CH.apply({"snap": was}, now)["snap"]                  # read for the entry's reasons, never stored


def test_every_move_in_the_log_says_why_even_with_no_words_stored():
    """Fails before: a kept log's moves with only OUTSIDE_FIGURES, or none, printed with no reason."""
    log = [{"cause": "rules", "moved": [
        {"symbol": "A", "name": "A", "from": "Other biotech companies", "to": "Clinical biotechs", "why": CH.OUTSIDE_FIGURES},
        {"symbol": "B", "name": "B", "from": "Clinical biotechs", "to": "Other biotech companies"},
        {"symbol": "C", "name": "C", "from": "Other biotech companies", "to": "Clinical biotechs"}]}]
    words = {"A": "Acme Bio Inc. is a clinical-stage biotechnology company developing antibodies for cancer."}.get
    got = CH.reasoned(log, words, lambda s: "")[0]["moved"]
    assert got[0]["why"].startswith("its own words say “Acme Bio Inc. is a clinical-stage biotechnology company") and got[0]["outside"]
    assert got[1]["why"] == "no words of its own are stored, so none says a named layer's work"
    assert got[2]["why"] == "no words of its own are stored; the theme's map places it in “Clinical biotechs”"
    assert all(r.get("why") for r in CH.reasoned(log)[0]["moved"])                  # with no reader of its words too


def test_a_layer_of_members_past_the_figures_renamed_is_no_move():
    """Fails before: a layer whose members are all past the figures, renamed, printed each member as moved between the two names."""
    was = CH.snapshot(_dive({"Big": ["X"]}), ["X"], 1, 68, everyone={"X": ["X", "Big"], "Y": ["Y", "Small tools"], "Z": ["Z", "Small tools"]})
    now = CH.snapshot(_dive({"Big": ["X"]}), ["X"], 1, 69, everyone={"X": ["X", "Big"], "Y": ["Y", "Small tool makers"], "Z": ["Z", "Small tool makers"]})
    d = CH.diff(was, now)
    assert d["moved"] == []
    assert [x["kind"] for x in d["layers"]] == ["renamed"]
    # the "Other" group past the figures renamed: no move either
    o1 = CH.snapshot(_dive({"Big": ["X"]}), ["X"], 1, 68, everyone={"X": ["X", "Big"], "Y": ["Y", "Other tool companies"]})
    o2 = CH.snapshot(_dive({"Big": ["X"]}), ["X"], 1, 69, everyone={"X": ["X", "Big"], "Y": ["Y", "Other tool makers"]})
    assert CH.diff(o1, o2)["moved"] == []


def test_the_deck_prints_each_move_into_other_with_its_reason():
    """Fails before: "moved into “Other” 1: Vornado Realty Trust (from “Office landlords”)", no reason printed."""
    why = ("its own words, official industry and name say no word of “Office landlords”: not moved into it, it stays where it is published, "
           "and more words that run past the length a reason is printed at in the deck's coverage table")
    v = {"coverage": {"other_name": "Other REITs"},
         "changes": {"entries": [{"cause": "rules", "counts": {"moved": 1},
                                  "moved": [{"symbol": "VNO", "name": "Vornado Realty Trust", "from": "Office landlords", "to": "Other REITs", "why": why}]}]}}
    row = deck.cohort_row(v)
    assert "Vornado Realty Trust (from “Office landlords”: its own words, official industry and name say no word of “Office landlords”" in row[2]
    assert len(deck.move_reason(why)) <= deck.MOVE_REASON_CHARS and deck.move_reason(why).endswith("…")
