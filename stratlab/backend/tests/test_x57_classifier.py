"""Lane x57 (Release 57, the audit of the 24 live R56 decks): the earning-model evidence classifier (RC4), the business-model, adjacency and
"whole company" labels (RC5), and parents, subsidiaries and holding companies across layers (RC10). Generic rules; company names only here.

RC4: "insufficient evidence" for companies whose stored description names what they sell (Mahindra & Mahindra, Payoneer, Syngene, Inox
Green), the same stored words with two opposite verdicts in two decks (Syngene), and "(on its words) ... no other way of earning" for
companies with other businesses (Fiserv, J&J, L&T). RC5: Sun Pharma and Hindustan Unilever out of their medians as "whole company", IREDA (a
lender) counted core, American Express an adjacent lender, labs labelled hospitals, Utilities' equipment and cable makers counted core.
RC10: a parent in one layer and its listed subsidiary in another both adding the subsidiary's revenue.

Exact replays use the live R56 placement inputs (GET /research/theme-dive/placement-inputs, lane g57): tests/fixtures/themes_live/inputs_r56.
"""
import copy
import json
import pathlib

import pytest

from app import deck
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from tests import test_exact_replay as X

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "inputs_r56"
# the map layer each map pick the live split moved was named in (recovered as test_exact_replay does: the replay matching every live layer)
ORIGIN = {"payments": {"XYZ": "Merchant acquiring and processing", "FLYW": "Cross-border and B2B payments"}, "hosp": {}, "auto": {}, "telecom": {},
          "pharma": {"DIVISLAB": "Active ingredient and intermediate makers"}, "renew": {"KPIGREEN": "Solar module and cell manufacturing"}}
STALE = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit", "read_low", "also_earns", "read_agrees", "no_read")
INSUFFICIENT = {"no_model", "weak", "no_words"}
_CACHE: dict = {}


def replay(key: str, monkeypatch) -> tuple[dict, dict]:
    if key not in _CACHE:
        d = json.loads((LIVE / f"{key}.json").read_text())
        for v in d["value_chain"]:
            v["companies"] = [{k: x for k, x in c.items() if k not in STALE} for c in v["companies"]]
        sig = ((d.get("kept") or {}).get("model_names") or {}).get("sig")
        if sig:
            monkeypatch.setattr(B, "model_names_signature", lambda layers: sig)
        m = X.pre_map(json.loads(json.dumps(d)), ORIGIN[key], {})
        out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                              figures_of=lambda s: (d.get("figures") or {}).get(s) or {}, carried=d["kept_version"] != B.RULES,
                              previous=d.get("previous") or {}, off_before=d.get("off_before") or {}, moved_before=d.get("moved_before") or {},
                              moved_out=d.get("moved_out") or {})
        _CACHE[key] = (d, out)
    return copy.deepcopy(_CACHE[key])


def rows(out) -> dict:
    return {c["ticker"]: (v, c) for v in out["value_chain"] for c in v["companies"]}


def live_layers(d) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else X._HALF.sub("", v["layer"])) for v in d["value_chain"] for c in v["companies"]}


# ---------- RC4 a: exact replays of the live R56 inputs ----------
@pytest.mark.parametrize("key,sym", [("auto", "M&M"), ("payments", "PAYO"), ("hosp", "SYNGENE"), ("renew", "INOXGREEN"), ("telecom", "GTLINFRA")])
def test_a_top_company_whose_description_names_its_business_is_no_longer_insufficient_evidence(key, sym, monkeypatch):
    """Fails before: each was left out of its layer's figures as "insufficient evidence" (M&M "how it earns read only weakly", Payoneer "its
    words don't state how it earns", Syngene, Inox Green, GTL Infrastructure), each among the 3 largest of its layer by revenue, each with a
    stored description that names what it sells. Its layer is the one the live deck printed (no layer moves)."""
    d, out = replay(key, monkeypatch)
    v, c = rows(out)[sym]
    assert live_layers(d)[sym] == ("Other" if v.get("official") else X._HALF.sub("", v["layer"]))
    assert "model_out" not in c and c.get("out_why") not in INSUFFICIENT, (sym, c.get("out_why"))
    assert c.get("read_low") or c.get("by_words"), sym


def test_no_company_changes_layer_on_the_replays(monkeypatch):
    """The classifier decides who is in a layer's figures, never who is in which layer: every company of the six replays stays where the live
    R56 deck printed it."""
    for key in ORIGIN:
        d, out = replay(key, monkeypatch)
        live = live_layers(d)
        got = {s: ("Other" if v.get("official") else X._HALF.sub("", v["layer"])) for s, (v, c) in rows(out).items()}
        assert got == live, key


def test_the_same_stored_words_give_the_same_verdict_in_two_themes(monkeypatch):
    """Fails before (RC4 b, PH-3): Syngene, with one stored description, was in the Pharma deck's CDMO figures "on its words" and "insufficient
    evidence (how it earns read only weakly)" in the Hospitals deck's "Contract research and life-science services". Now in both, each saying
    the other way its words name as what it also earns from."""
    _, hosp = replay("hosp", monkeypatch)
    _, pharma = replay("pharma", monkeypatch)
    (vh, h), (vp, p) = rows(hosp)["SYNGENE"], rows(pharma)["SYNGENE"]
    assert "model_out" not in h and "model_out" not in p
    assert h.get("by_words") and p.get("by_words")
    assert h["also_earns"] == ["contract_manufacturing"] and p["also_earns"] == ["project_services"]


def test_a_layer_whose_name_states_epc_takes_an_epc_contractor_read_at_low_confidence(monkeypatch):
    """Waaree Renewable Technologies, read (low) as an EPC contractor, was in its Renewable energy layer's figures and "read only weakly" in
    Capital goods' "Power equipment makers and EPC contractors"; a layer whose own name states EPC takes it (NAME_PART_MODEL, its industry the
    layer's), whatever the confidence. Replayed on the synthetic layer of the live shape."""
    vc = [{"layer": "Power equipment makers and EPC contractors", "description": "Makers of transformers and switchgear, and EPC contractors.",
           "companies": [{"ticker": f"M{i}", "name": f"Maker {i}", "industry": "Other Electrical Equipment"} for i in range(4)]
           + [{"ticker": "EPC", "name": "Solar Projects Ltd", "industry": "Other Electrical Equipment", "placed": "ai"}]},
          {"layer": "Cable makers", "description": "Cables.", "companies": [{"ticker": f"K{i}", "name": f"Cable {i}", "industry": "Cables"} for i in range(3)]}]
    ev = {**{f"M{i}": "Maker manufactures transformers, switchgear and power equipment for utilities." for i in range(4)},
          **{f"K{i}": "Cable Ltd manufactures power cables and wires." for i in range(3)},
          "EPC": "Solar Projects Ltd is engaged in the business of generation of power through renewable energy sources and builds solar plants."}
    models = {**{f"M{i}": "manufacturing" for i in range(4)}, **{f"K{i}": "manufacturing" for i in range(3)}, "EPC": "construction"}
    conf = {**{s: "high" for s in models}, "EPC": "low"}
    out = B.by_model(copy.deepcopy(vc), models, "Capital goods", confidence=conf, evidence_of=lambda s: ev.get(s, ""))
    c = rows({"value_chain": out})["EPC"][1]
    assert c.get("by_words") and "model_out" not in c


# ---------- RC4: the rules on synthetic layers (generic) ----------
MAKERS = [{"ticker": f"CAR{i}", "name": f"Carmaker {i} Ltd", "industry": "Passenger Cars & Utility Vehicles"} for i in range(4)]
MAKER_WORDS = "Carmaker Ltd manufactures passenger cars and utility vehicles in its own plants."


def _makers(extra: dict, words: str, model: str = "manufacturing", confidence: str = "low", second=None):
    vc = [{"layer": "Passenger and utility vehicle makers", "description": "These companies make cars and utility vehicles.",
           "companies": copy.deepcopy(MAKERS) + [extra]},
          second or {"layer": "Component suppliers", "description": "Parts makers.",
                     "companies": [{"ticker": f"P{i}", "name": f"Parts {i}", "industry": "Auto Components & Equipments"} for i in range(3)]}]
    ev = {**{c["ticker"]: MAKER_WORDS for c in MAKERS}, **{f"P{i}": "Parts Ltd manufactures auto components for vehicle makers." for i in range(3)},
          extra["ticker"]: words}
    models = {**{c["ticker"]: "manufacturing" for c in MAKERS}, **{f"P{i}": "components" for i in range(3)}}
    conf = {s: "high" for s in models}
    if model:
        models[extra["ticker"]], conf[extra["ticker"]] = model, confidence
    out = B.by_model(vc, models, "Automotive", confidence=conf, evidence_of=lambda s: ev.get(s, ""))
    return rows({"value_chain": out})[extra["ticker"]][1]


def test_a_low_read_of_the_layers_way_with_words_of_its_products_is_in_the_figures():
    """Fails before: Mahindra & Mahindra's shape: read (low confidence) as a maker in a makers' layer, its official industry the layer's, its
    description naming its vehicles, and a later sentence naming the group's components and retail businesses "through its subsidiaries":
    "insufficient evidence (how it earns read only weakly)". Now in the figures, marked as read at low confidence, with the other ways its
    subsidiaries' sentence names as what it also earns from."""
    c = _makers({"ticker": "MM", "name": "Diversified Motors Ltd", "industry": "Passenger Cars & Utility Vehicles"},
                "Diversified Motors Ltd is one of the most diversified automobile company in India with presence across 2-wheelers, 3-wheelers, "
                "PVs, CVs, tractors & earthmovers. It also has presence across financial services, auto components, hospitality, retail and steel "
                "trading through its subsidiaries and group companies.")
    assert c.get("read_low") and "model_out" not in c, c
    assert c["also_earns"] == ["components", "retail"]


def test_a_low_read_with_no_words_of_what_it_makes_stays_out():
    """Strictness kept: a company read (low) as a maker whose description names nothing it makes or does ("a holding company") is still left
    out as read only weakly; its industry alone puts nothing in the figures beside a low read."""
    c = _makers({"ticker": "VG", "name": "Vague Ltd", "industry": "Passenger Cars & Utility Vehicles"}, "Vague Ltd is a group company.")
    assert c.get("model_out") == "unknown" and c["out_why"] == "weak"


def test_a_low_read_contradicted_by_its_principal_words_is_not_read_low():
    """A company read (low) as a maker whose own principal words say it trades the goods (a distributor) is never put in a makers' layer's
    figures on the read; the read and its words disagree, so it stays out as read only weakly."""
    c = _makers({"ticker": "TR", "name": "Trading Ltd", "industry": "Passenger Cars & Utility Vehicles"},
                "Trading Ltd is engaged in the business of trading of passenger cars and utility vehicles of other makers.")
    assert c.get("model_out") and not c.get("read_low")


def test_no_read_and_words_stating_another_way_is_a_different_model_not_insufficient_evidence():
    """Fails before: a company no answer gave a model whose own words state one other way of earning in so many words (a vehicle financier,
    "a non-banking financial company (NBFC)", in a vehicle makers' layer) was "insufficient evidence: its words don't state how it earns".
    Now a different revenue model, the way its words state named. Words that name two ways (it processes and retails dairy) state none."""
    c = _makers({"ticker": "LN", "name": "Vehicle Finance Ltd", "industry": "Passenger Cars & Utility Vehicles"},
                "Vehicle Finance Ltd is a non-banking financial company (NBFC) giving loans to buyers of cars and utility vehicles.", model="")
    assert c.get("model_out") == "other" and c["out_why"] == "model" and c["model"] == "lending"
    assert D.out_reason({**c, "layer_model": "manufacturing", "layer_family": "making", "status": "core"})["kind"] == "different revenue model"
    two = _makers({"ticker": "DY", "name": "Dairy Ltd", "industry": "Passenger Cars & Utility Vehicles"},
                  "Dairy Ltd deals in production and sale of milk. It is in the business of procurement, processing, and retailing of dairy products.",
                  model="")
    assert two.get("model_out") == "unknown" and two["out_why"] == "no_model"


def test_no_read_with_words_saying_a_layer_that_states_its_way_is_in_on_its_words():
    """Fails before (Payoneer's shape): placed by the AI in "Cross-border and B2B payments", no model read, its words saying "across borders"
    and no way of earning: "insufficient evidence". The layer's own name says its companies' way (payments), so its words saying the name say
    how it earns: in the figures on its words, with no "only the AI's read gave it another" (no read). A layer whose name says another way
    than its companies' (a resale layer named for business process services) takes no such company."""
    pay = [{"ticker": f"PY{i}", "name": f"Pay {i}", "industry": "Services-Business Services, Nec"} for i in range(4)]
    vc = [{"layer": "Cross-border and B2B payments", "description": "These firms move money across borders for businesses.",
           "companies": pay + [{"ticker": "XB", "name": "Borderless Inc", "industry": "Finance Services", "placed": "ai"}]},
          {"layer": "Card networks", "description": "Networks.", "companies": [{"ticker": f"N{i}", "name": f"Net {i}", "industry": "X"} for i in range(3)]}]
    ev = {**{c["ticker"]: "Pay Inc processes payments for businesses across borders." for c in pay}, **{f"N{i}": "Net runs a card network." for i in range(3)},
          "XB": "Borderless Inc removes the complexity and barriers of doing business across borders for small businesses with a multi-currency account."}
    models = {**{c["ticker"]: "payments" for c in pay}, **{f"N{i}": "payments" for i in range(3)}}
    out = B.by_model(copy.deepcopy(vc), models, "Payments and fintech", confidence={s: "high" for s in models}, evidence_of=lambda s: ev.get(s, ""))
    c = rows({"value_chain": out})["XB"][1]
    assert c.get("by_words") and c.get("no_read") and "model_out" not in c and c["model"] == "payments"
    said = D.comparison_said({"in": True, "why": "", "by_words": True, "no_read": True}, {"model": {"id": "payments", "family": "payments"}})
    assert "only the AI's read" not in said and "no other way of earning" not in said
    # a layer whose name and description say nothing of its companies' way (resale) takes none on its words
    rs = [{"ticker": f"RS{i}", "name": f"Resale {i}", "industry": "IT Enabled Services"} for i in range(3)]
    vc2 = [{"layer": "Healthcare and digital business process services", "description": "Firms that run processes for clients.",
            "companies": rs + [{"ticker": "HC", "name": "Care Ops Ltd", "industry": "Computers - Software & Consulting", "placed": "ai"}]}, vc[1]]
    ev2 = {**ev, **{c["ticker"]: "Resale Ltd is an authorised reseller of IT hardware for system integrator for businesses." for c in rs},
           "HC": "Care Ops Ltd provides healthcare digital business process services to clients."}
    models2 = {**{c["ticker"]: "hardware_resale" for c in rs}, **{f"N{i}": "payments" for i in range(3)}}
    out2 = B.by_model(copy.deepcopy(vc2), models2, "IT services", confidence={s: "high" for s in models2}, evidence_of=lambda s: ev2.get(s, ""))
    assert rows({"value_chain": out2})["HC"][1].get("model_out")


def test_principal_words_leave_out_the_sentences_on_subsidiaries_and_other_businesses():
    e = ("Industry: Automobiles. A Ltd makes cars. It also has presence across financial services and retail through its subsidiaries and group "
         "companies.")
    assert C.principal_words(e) == "Industry: Automobiles. A Ltd makes cars."
    assert C.secondary_models(e) == {"retail"}
    assert C.principal_words("A Ltd makes cars.") == "A Ltd makes cars."          # nothing to leave out


def test_makes_possible_and_customers_are_no_way_of_earning():
    """Fails before: "the trusted context that makes credible AI outcomes possible" and "that makes business possible" read as a maker's
    words; "towers ... shared by the Wireless Telecom Operators" and "requirements of Telecom Operators" read as a telecom operator's own."""
    assert "manufacturing" not in C.words_models("We help clients manage the workforce infrastructure that makes business possible.")
    assert "manufacturing" not in C.words_models("Our portfolio is the trusted context that makes credible AI outcomes possible.")
    assert "manufacturing" in C.words_models("Acme makes industrial valves and pumps.")
    assert "telecom_services" not in C.words_models("It owns telecom towers that are shared by the Wireless Telecom Operators.")
    assert "telecom_services" not in C.words_models("It addresses the network requirements of Telecom Operators and Tower Companies.")


# ---------- RC4 c: never "no other way of earning" from an absence of words ----------
def test_on_its_words_never_says_no_other_way_of_earning_unless_one_segment_is_stored():
    """Fails before: "(on its words): the map placed it here and its own words say the layer's name and no other way of earning" for Fiserv
    (financial solutions about half its revenue), J&J, Merck, L&T and Fortinet. Now the note says only that its words say the layer's name; a
    company whose words name another way says it also earns from it; "no other way of earning" only with one reportable segment stored."""
    assert "no other way of earning" not in deck.ON_WORDS_NOTE
    base = {"in": True, "why": "", "by_words": True}
    model = {"model": {"id": "payments", "family": "payments"}}
    assert "no other way of earning" not in D.comparison_said(base, model)
    assert "only the AI's read gave it another" in D.comparison_said(base, model)
    assert D.comparison_said({**base, "segments_n": 1}, model).endswith("one reportable segment is stored and its words name no other way of earning")
    assert "no other way" not in D.comparison_said({**base, "segments_n": 6}, model)
    also = D.comparison_said({**base, "also_earns": ["contract_manufacturing"]}, model)
    assert also.endswith("it also earns from making products to other companies' designs and orders")
    note = deck.also_notes([{"name": "Syngene International Ltd", "also_earns": ["contract_manufacturing"]}, {"name": "Plain Ltd"}])
    assert note == (" Syngene International Ltd: its words name the layer's business, and it also earns from making products to other "
                    "companies' designs and orders.")
    assert "read at low confidence" in D.comparison_said({"in": True, "why": "", "read_low": True}, model)


def test_the_flags_reach_the_dive_rows():
    layer = {"layer": "L", "model": {"id": "manufacturing", "family": "making"},
             "companies": [{"ticker": "A", "model": "manufacturing", "model_confidence": "low", "read_low": True, "also_earns": ["retail"]},
                           {"ticker": "B", "model": "payments", "by_words": True, "no_read": True}]}
    a, b = D.model_fields(layer, "A"), D.model_fields(layer, "B")
    assert a["read_low"] and a["also_earns"] == ["retail"] and b["by_words"] and b["no_read"]


# ---------- RC5 c: "whole company" only for a second business of 20% or more ----------
def test_whole_company_reads_segments_as_businesses_and_a_diversified_industry_of_the_theme_s_own_business_is_none():
    """Fails before: Sun Pharma's reported segments are its formulations by market (US 31%, India 31%, emerging markets 18%, rest of world 14%,
    API 6%): no segment of 66% made it "whole company: it runs other businesses too", out of the medians. Hindustan Unilever's industry
    "Diversified FMCG" did the same in the FMCG theme. A second business of 20% or more (L&T's technology services) still does; so does a
    diversified group whose own words name its other businesses (Vedanta's power and ports) and a conglomerate."""
    sun = [{"name": "US Formulations", "share_pct": 31}, {"name": "India Formulations", "share_pct": 31},
           {"name": "Emerging Markets Formulations", "share_pct": 18}, {"name": "Rest of World Formulations", "share_pct": 14},
           {"name": "API & Others", "share_pct": 6}]
    assert D.business_shares(sun) == [100.0]
    assert not D.is_diversified({"symbol": "SUNP", "industry": ["Healthcare", "Pharmaceuticals"]}, sun)
    fmcg = D._stems("FMCG Branded home and personal care Packaged foods")
    hul = "Hindustan Unilever is in the FMCG business comprising primarily of Home Care, Beauty & Personal Care and Foods & Refreshment segments."
    assert not D.is_diversified({"symbol": "HUL", "industry": ["Fast Moving Consumer Goods", "Diversified FMCG"]}, None, fmcg, hul)
    assert D.is_diversified({"symbol": "HUL", "industry": ["Fast Moving Consumer Goods", "Diversified FMCG"]})       # no theme words: as before
    ved = ("Vedanta Ltd is a diversified natural resource group. Its other businesses includes commercial power generation, steel "
           "manufacturing & port operations in India.")
    assert D.is_diversified({"symbol": "VED", "industry": ["Metals & Mining", "Diversified Metals"]}, None, D._stems("Metals and mining zinc"), ved)
    lt = [{"name": "Infrastructure Projects", "share_pct": 47}, {"name": "Energy Projects", "share_pct": 12},
          {"name": "IT & Technology Services", "share_pct": 25}, {"name": "Financial Services", "share_pct": 6}]
    assert D.is_diversified({"symbol": "LT", "industry": ["Construction"]}, lt)
    assert not D.is_diversified({"symbol": "X", "industry": []}, [{"name": "Auto", "share_pct": 60}, {"name": "Farm", "share_pct": 15},
                                                                   {"name": "Parts", "share_pct": 15}, {"name": "Other", "share_pct": 10}])
    assert D.is_diversified({"symbol": "X", "industry": ["Conglomerate"]}, sun)


# ---------- RC5 a, b, d: adjacency on the principal business, said apart from the statistics decision ----------
def test_a_lender_in_a_non_lending_theme_is_adjacent_and_said_so():
    """Fails before (REN-1): IREDA, a government NBFC lender filed as "Financial Institution", was a core member of Renewable energy, its net
    margin and P/E in the theme's medians. Now adjacent, and the deck says it is in the theme as a lender, not in core statistics, and why."""
    a = D.scope_adjacent({"industry": "Financial Institution"}, "Renewable energy", "", "It provides financial assistance to renewable energy projects.")
    assert a and a["kind"] == "lenders and financiers" and a["where"] == "industry"
    said = D.adjacent_said(a)
    assert said.startswith("in the theme as an adjacent participant (lenders and financiers); not in its core statistics because its principal business")


def test_a_card_company_whose_words_state_the_theme_s_way_is_not_an_adjacent_lender():
    """Fails before (PAY-2): American Express, "a bank holding company ... that specializes in payment cards" whose words name its
    "card-issuing, merchant-acquiring and card network businesses", was an adjacent lender on its official industry "Finance Services". A
    card lender whose words state no payments way of earning stays adjacent."""
    amex = ("American Express Company is an American bank holding company and multinational financial services corporation that specializes in "
            "payment cards. Its card-issuing, merchant-acquiring and card network businesses offer products and services to consumers.")
    assert D.scope_adjacent({"industry": "Finance Services"}, "Payments and fintech", "", amex, None, "lending", "medium") is None
    lender = "Capfin Corp is a bank holding company specializing in credit cards, auto loans, banking and savings accounts."
    assert D.scope_adjacent({"industry": "Finance Services"}, "Payments and fintech", "", lender, None, "lending", "medium")["kind"] == "lenders and financiers"


def test_a_laboratory_is_said_as_a_laboratory_never_a_hospital():
    """Fails before (MD-3): "hospitals and care providers 24 (HCA Healthcare, Natera, Labcorp, Quest Diagnostics ...)". The decision is the
    same (another kind than medical devices), the name it is said by is its own; a Hospitals theme keeps its diagnostic chains as core."""
    tk = D.theme_kind("Medical devices")
    assert D.adjacent_of({"industry": "Services-Medical Laboratories"}, tk)["kind"] == "diagnostic and testing laboratories"
    assert D.adjacent_of({"industry": "Services-Hospitals"}, tk)["kind"] == "hospitals and care providers"
    assert D.adjacent_of({"industry": "Healthcare Service Provider"}, D.theme_kind("Hospitals"), "Lab Ltd runs a chain of diagnostic centres.") is None


def test_utilities_equipment_and_cable_makers_are_adjacent():
    """Fails before (UTL-1): 59 of the Utilities deck's 99 companies with figures were its equipment and cable makers, counted core, so the
    theme's medians were mostly a manufacturer's. A generator, a network and a gas distributor stay core."""
    tk = D.theme_kind("Utilities")
    assert tk == "power, gas and water utilities"
    for ind in ("Cables - Electricals", "Heavy Electrical Equipment"):
        assert D.adjacent_of({"industry": ind}, tk)["kind"] == "electrical equipment and cable makers", ind
    for ind in ("Power Generation", "Power - Transmission", "Integrated Power Utilities", "Gas Transmission/Marketing", "LPG/CNG/PNG/LNG Supplier"):
        assert D.adjacent_of({"industry": ind}, tk) is None, ind
    assert D.theme_kind("Capital goods") == "" and D.theme_kind("Renewable energy") == ""        # no rule where the theme's name states none


# ---------- RC10: a parent and its listed subsidiary in different layers ----------
def test_a_parent_in_one_layer_and_its_subsidiary_in_another_add_its_revenue_once():
    """Fails before (CEM-1): Grasim (whole company, 56% of UltraTech) in "Regional integrated producers (larger)" with its consolidated revenue,
    UltraTech's inside it, and UltraTech counted again in "Pan-India producers"; Ambuja (not whole company) and its 72.7% Orient Cement the
    same. Now a parent whose figures are the whole company's is a holding company of a member, in no core figure; another parent's layer
    revenue has the subsidiary's taken out and says so."""
    rows_ = {"GRASIM": {"symbol": "GRASIM", "name": "Grasim Industries Ltd", "revenue": 175000.0, "status": "core"},
             "ULTRA": {"symbol": "ULTRA", "name": "UltraTech Cement Ltd", "revenue": 88512.0, "status": "core"},
             "AMBUJA": {"symbol": "AMBUJA", "name": "Ambuja Cements Ltd", "revenue": 40656.0, "status": "core"},
             "ORIENT": {"symbol": "ORIENT", "name": "Orient Cement Ltd", "revenue": 3000.0, "status": "core"},
             "STAR": {"symbol": "STAR", "name": "Star Cement Ltd", "revenue": 3000.0, "status": "core"}}
    parents = {"ULTRA": {"parent": "GRASIM", "parent_name": "Grasim Industries Ltd", "pct": 56.1, "quarter": "2026-09"},
               "ORIENT": {"parent": "AMBUJA", "parent_name": "Ambuja Cements Ltd", "pct": 72.7, "quarter": "2026-09"}}
    for s_, p in parents.items():
        rows_[s_]["parent"] = p
    layer_of = {"GRASIM": "Regional", "ULTRA": "Pan-India", "AMBUJA": "Pan-India", "ORIENT": "Regional", "STAR": "Regional"}
    D.holding_across(rows_, parents, layer_of, {"GRASIM"}, "Cement")
    assert rows_["GRASIM"]["adjacent"]["kind"] == "holding companies of other members"
    assert "in the theme as an adjacent participant (holding companies of other members)" in D.adjacent_said(rows_["GRASIM"]["adjacent"])
    assert not rows_["AMBUJA"].get("adjacent") and rows_["AMBUJA"]["holds_elsewhere"][0]["symbol"] == "ORIENT"
    pan = D.layer_block("Pan-India", [rows_["ULTRA"], rows_["AMBUJA"]], set())
    assert pan["revenue"] == 88512.0 + 40656.0 - 3000.0 and pan["double_elsewhere"][0]["name"] == "Orient Cement Ltd"
    head = deck.layer_head(pan, pan["companies"], lambda x: f"₹{x:,.0f} cr")
    assert "Orient Cement Ltd's revenue taken out of Ambuja Cements Ltd's, as it holds 72.7% and Orient Cement Ltd is counted in “Regional”" in head
    assert "taken out of the parent's layer's revenue when the two are in different layers" in deck.parents_row(
        {"parents": [{"name": "Orient Cement Ltd", "parent_name": "Ambuja Cements Ltd", "pct": 72.7, "quarter": "2026-09"}]})[2]
