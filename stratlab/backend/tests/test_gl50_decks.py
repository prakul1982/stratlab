"""Release 50 (lane gl50, the rotating review of six unseen live R48 themes: Hospitals, Cement, FMCG India, Software, Biotech US, Capital goods).

G1 (P0): the Biotech and Capital goods decks ranked their layers ("highest in Clinical-stage platform developers (35.0%)") with no company's
way of earning read, and Capital goods said of every company "of the layer's kind" beside "no way of earning read for these companies".
A chain with no way of earning read is shown, not ranked, says why, never says "of the layer's kind", and the publication gate fails a
deck whose pages contradict each other on it.
G2/G6: "100 of the 100 checked confirmed by their own description, 0 not yet" of 821 companies; most of a layer left out for want of a
model read (the placement's one answer asked for hundreds of models; a theme whose answer failed had none and nothing asked again).
G4: a company placed by its words alone is checked against what its layer is (its name and description) and its official industry.
G5: a parent and its listed subsidiary both added into revenue totals (the stored shareholding filings name the parent).
G7: the US decks' latest quarter was the newest one 2 companies reported (fiscal quarters ending in October), 90 left out.
G9: deck_check reads the classification red flags from the text.

The rot49 fixtures are the live R48 sector pages' placements (scratchpad/lanes18/rot49, read GET only); the telecom one is the live R46
placement inputs (cv47)."""
import json
import pathlib

import pytest

from app import deck
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from app.intel import theme_routes as TR
from scripts import deck_check
from tests import test_exact_replay as X
from tests.gl50_read import READ, blocks, read
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_r48_compare import chem

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"


def rot49(key: str) -> dict:
    return json.loads((LIVE / "rot49" / f"{key}.json").read_text())


def merged(vc: list[dict]) -> list[dict]:
    """The map's layers as they were before the split by market value (each half's companies back in one layer)."""
    out, seen = [], {}
    for v in vc:
        name = B._HALF_RX.sub("", v["layer"])
        if v.get("scale") and name in seen:
            seen[name]["companies"] += v["companies"]
            continue
        v = {**v, "layer": name, "companies": list(v["companies"])}
        v.pop("scale", None)
        seen[name] = v
        out.append(v)
    return out


def refits(vc: list[dict]) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else v["layer"], c["refit"]["why"]) for v in vc for c in v["companies"] if c.get("refit")}


# ---------- G1: no ranking with no way of earning read ----------
def test_a_chain_with_no_way_of_earning_read_is_shown_not_ranked_and_says_why():
    bare = [{"layer": n, "n": 6, "revenue": 1.0, "official": False, "stats": {"ebitda": {"median": m, "n": 6}}, "companies": []}
            for n, m in (("Clinical-stage platform developers", 35.0), ("Commercial specialty biotechs", -7.2), ("Research tools", 12.0))]
    c = D.chain_table(bare)
    assert c["highest"] is None and c["lowest"] is None and c["unread"] and c["line"].endswith(D.UNREAD_SAID)
    assert "highest" not in c["line"] and c["basis"]["why"] == D.UNREAD_WHY and not c["basis"]["made"]
    rule = next(r for r in c["basis"]["rules"] if r["rule"] == "like-for-like model")
    assert rule["text"] == "no way of earning read for these companies" and rule["passed"] is False      # it passed before
    ranked = D.chain_table(blocks(bare))
    assert (ranked["highest"], ranked["lowest"]) == ("Clinical-stage platform developers", "Commercial specialty biotechs")
    assert D.one_family([{"m": None}, {"m": None}], lambda r: "") == []                                  # every row before
    assert D.rank_pair([("a", 9.0, 6, 6, None), ("b", 1.0, 6, 6, None)], lambda t: t[1], lambda t: t[2], model=lambda t: t[4]) is None


def test_a_company_of_a_layer_with_no_way_of_earning_read_is_never_said_to_be_of_the_layers_kind():
    said = D.comparison_said({"in": True}, {"model": None})
    assert "layer's kind" not in said and "not read" in said and "not ranked" in said
    assert "of the layer's kind" in D.comparison_said({"in": True}, {"model": dict(READ)})


def test_the_gate_drops_a_ranking_and_fails_a_deck_that_says_of_the_layers_kind_with_no_way_of_earning_read():
    m, f = chem()
    for v_ in m["value_chain"]:
        v_.pop("model")                                  # no way of earning read: the deck ranks nothing and says nothing of a kind
    v, slides = deck_of("IN", m, f)
    t = texts(slides)
    assert v["chain"]["highest"] is None and "is highest in" not in t and "of the layer's kind" not in t
    gate = slides[0].gate
    item = next(x for x in gate["items"] if x["id"] == "classified")
    assert item["ok"] and "never ranked" in item["note"]
    # the same pages with a ranking and "of the layer's kind" written in by hand (the live Capital goods deck): both fail the item
    ranked, _ = deck_of("IN", read(m), f)
    page = next(s for s in slides if s.title == "The value chain by layer")
    page.subtitle = ranked["chain"]["line"]
    page.blocks.append({"kind": "text", "paras": ["comparison: in its layer's figures: confirmed, how it earns shown and of the layer's kind"]})
    got = deck.unread_sweep(slides, v)
    assert {d["why"] for d in got} == {deck.UNREAD_RANK, deck.UNREAD_KIND}
    assert page.subtitle == ""                            # the ranking is dropped from the page


def test_the_appendix_note_says_no_way_of_earning_read_where_none_is():
    m, f = chem()
    for v_ in m["value_chain"]:
        v_.pop("model")
    v, slides = deck_of("IN", m, f)
    assert not deck.unread_sweep(slides, v)


def test_a_clinical_stage_layers_commercial_company_is_out_of_its_figures_as_another_business():
    rows = [{"symbol": f"C{i}", "name": f"Clin {i}", "revenue": 10.0 + i, "ebitda": -80.0} for i in range(5)] + \
           [{"symbol": "BIG", "name": "Big Pharma", "revenue": 60000.0, "ebitda": 35.0}]
    got = D.stage_check({"layer": "Clinical-stage platform developers", "description": "Pre-revenue companies with drugs in trials."}, rows)
    assert got == ["BIG"]
    big = rows[-1]
    rec = D.calc_record(big)
    assert rec["why"] == "other business" and rec["kind"] == "another business" and "commercial company" in rec["label"]
    assert "clinical-stage" in rec["detail"]
    assert D.stage_check({"layer": "Commercial specialty biotechs", "description": ""}, [dict(r) for r in rows]) == []


# ---------- G6: the companies past the check said as not checked yet ----------
def test_the_universe_says_how_many_are_not_checked_yet_never_0_not_yet():
    v = {"placements": {"base": 821, "named": 0}, "membership": {"placed": 100, "confirmed": 100, "not_confirmed": 0}}
    said = deck.membership_words(v, 821)
    assert "721 not checked yet" in said and "0 not yet" not in said and "100 checked (the map's own picks, then the largest by market value)" in said
    # (updated on purpose, e54: a view with no evidence states kept says confirmed in the theme, never "by their own description", which an
    # official-industry record can't be; with the states, each is counted)
    assert deck.membership_words({"placements": {"base": 60}, "membership": {"placed": 60, "confirmed": 58, "not_confirmed": 2}}, 60).endswith(
        "58 confirmed in the theme, 2 not yet")
    assert deck.membership_words({"placements": {"base": 60}, "membership": {"placed": 60, "confirmed": 58, "not_confirmed": 2, "evidence": {
        "description_verified": 40, "industry_code_supported": 18, "not_confirmed": 2}}}, 60).endswith(
        "60 checked: 40 confirmed by their own description, 18 kept on their official industry only, 2 whose own words describe other work")
    old = "Universe 821 companies; 100 of the 100 checked confirmed by their own description, 0 not yet."
    assert deck_check.check_pages([old])["counts"]["unchecked as 0"] == 1
    assert deck_check.check_pages([said])["counts"]["unchecked as 0"] == 0


# ---------- G2: the models read for the companies without one ----------
def _ask(calls, model="manufacturing"):
    def ask(system, text):
        body = json.loads(text.split("EVIDENCE:\n", 1)[1])
        calls.append([c["symbol"] for c in body["companies"]])
        return {"models": {c["symbol"]: model for c in body["companies"]}}
    return ask


def test_every_company_without_a_model_is_asked_in_batches_largest_first_whatever_the_placements_version():
    about = {f"F{i}": f"Food {i} Ltd manufactures biscuits, snacks and noodles in its own plants." for i in range(70)}
    calls = []
    models, _, conf, reasked = B.reask_unknown(None, {}, None, [], list(about), about.get, {}, about.get, _ask(calls), "FMCG")
    assert [len(c) for c in calls] == [B.REASK_BATCH] * (B.REASK_MAX // B.REASK_BATCH) and calls[0][0] == "F0"
    assert len(reasked) == B.REASK_MAX and all(models[s] == "manufacturing" and conf[s] for s in reasked)
    # a carried placement (every kept one, after a rules bump) asks too; each company once
    m = {"value_chain": [{"layer": "Packaged foods", "description": "Biscuits and snacks.", "companies": [{"ticker": "F0", "name": "Food 0", "cap": 9}]},
                         {"layer": "Foods", "official": True, "basis": "industry",
                          "companies": [{"ticker": f"F{i}", "name": f"Food {i}", "cap": 70 - i, "industry": "Packaged Foods"} for i in range(1, 6)]}]}
    kept = {"assign": {f"F{i}": {"layer": "Packaged foods", "by": "ai"} for i in range(1, 6)}, "models": {}}
    asked = []
    _, got = B.place_rest(m, "FMCG", about.get, ask=_ask(asked), kept=kept, carried=True)
    assert asked and sorted(got["reasked"]) == sorted(f"F{i}" for i in range(6))
    names_only = lambda s, t: pytest.fail("asked again") if s == C.MODEL_SYSTEM else {"place": [], "rename": [], "models": {}}   # noqa: E731
    _, again = B.place_rest(m, "FMCG", about.get, ask=names_only, kept=got, carried=True)
    assert again["models"]["F3"] == "manufacturing"


def test_a_company_whose_words_state_its_model_takes_it_when_the_answer_gave_none():
    about = {"MM": "Milky Mist Dairy Food Ltd manufactures milk products, cheese and yoghurt in its own plants",
             "XX": "Holds investments."}
    models, conf, added = B.stated_for_rest(None, None, ["MM", "XX"], lambda s: C.model_evidence("Dairy Products", about[s]))
    assert models == {"MM": "manufacturing"} and conf == {"MM": "medium"} and added == {"MM"}


def _telecom():
    d = json.loads((LIVE / "inputs_r46" / "telecom.json").read_text())
    d = d.get("data", d)
    origin = dict(X.RECOVERED["origin"].get("telecom") or {})
    for v in d["value_chain"]:
        for c in v["companies"]:
            if c.get("moved") and not c.get("placed") and c["ticker"] not in origin:
                origin[c["ticker"]] = "?" + c["ticker"]
    m = X.pre_map(d, origin, X.RECOVERED["description"].get("telecom"))
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d.get("previous") or {})
    return out


def test_live_telecom_a_tower_trust_with_no_words_is_in_the_tower_layers_figures_on_its_industry():
    """The live R48 Telecom deck: Altius Telecom Infrastructure Trust left out of "Tower infrastructure", leaving it at 1 of 4."""
    out = _telecom()
    towers = next(v for v in out["value_chain"] if v["layer"] == "Tower infrastructure")
    alt = next(c for c in towers["companies"] if c["ticker"] == "ALTIUSINVIT")
    assert alt.get("on_industry") and not alt.get("model_out")


# ---------- G4: what the layer is ----------
def test_fmcg_personal_care_makers_nestle_and_a_sugar_maker_leave_layers_their_words_and_industry_dont_fit():
    got = refits(B.definition_fit(merged(rot49("fmcg")["value_chain"]), lambda s: "", "FMCG"))
    assert got["NESTLEIND"][0] == "Branded packaged foods manufacturing" and got["NESTLEIND"][1].startswith("no words of its own; its official industry")
    assert got["ZYDUSWELL"][0] == "Branded packaged foods manufacturing"
    assert got["GILLETTE"][0] == got["PGHH"][0] == got["BAJAJCON"][0] == "Branded home and personal care"
    assert got["EIDPARRY"][0] == "Other" and "“Cigarette and tobacco manufacturers”" in got["EIDPARRY"][1]
    # a dairy maker stays: the packaged foods layer's description names dairy, its official industry; Britannia's words are of the layer
    assert not {"MILKYMIST", "HATSUN", "BRITANNIA", "HINDUNILVR", "ITC", "VBL"} & set(got)


def test_capital_goods_solar_makers_leave_rail_and_defence_and_a_diesel_engine_maker_stays_in_engines():
    got = refits(B.definition_fit(merged(rot49("capgoods")["value_chain"]), lambda s: "", "Capital goods"))
    for s in ("WAAREEENER", "WEBELSOLAR", "RAMRAT", "PREMIERENE"):
        assert got[s][0] == "Other", s
    assert "KIRLOSENG" not in got and "SHAKTIPUMP" not in got           # "diesel engines"; an industry part ("Compressors") the layer names


def test_only_a_placement_by_words_alone_is_checked_never_a_map_pick_or_the_ais():
    vc = merged(rot49("biotech")["value_chain"])
    got = refits(B.definition_fit(vc, lambda s: "", "Biotech"))
    assert {"MRK", "NVS", "AMGN"} <= set(got) and all(x[0] == "Other" for x in got.values())
    placed = {c["ticker"]: c.get("placed") for v in vc for c in v["companies"]}
    assert all(placed[s] == "words" for s in got)
    ai = [{**v, "companies": [{**c, "placed": "ai"} for c in v["companies"]]} for v in vc]
    assert not refits(B.definition_fit(ai, lambda s: "", "Biotech"))


def test_the_coverage_lists_each_company_moved_by_what_its_layer_is():
    v = {"layers": [{"layer": "Other FMCG companies", "basis": "rest", "companies": [
        {"name": "EID Parry (India) Ltd", "refit": {"from": "Cigarette and tobacco manufacturers", "why": "its own words don't say what it is"}}]}]}
    n, said = deck.refit_line(v)
    assert n == 1 and said == "EID Parry (India) Ltd: from “Cigarette and tobacco manufacturers” to “Other”, as its own words don't say what it is."


# ---------- G5: a parent and its listed subsidiary ----------
class _Src:
    def __init__(self, held):
        self.held = held

    def shareholding(self, sym):
        rows = self.held.get(sym)
        return {"q": {"2026-09": {"rows": rows}}} if rows else None


def test_a_listed_subsidiary_is_found_from_its_promoter_holder_and_left_out_of_totals_that_add_its_parent():
    names = {"ULTRA": "UltraTech Cement Limited", "GRASIM": "Grasim Industries Ltd", "ACC": "ACC Ltd", "AMBUJA": "Ambuja Cements Ltd",
             "SHREE": "Shree Cement Ltd"}
    src = _Src({"ULTRA": [["Grasim Industries Limited", "Company", "promoter", 1, 56.1]],
                "ACC": [["Ambuja Cements Limited", "Company", "promoter", 1, 50.6]],
                "SHREE": [["Some Family Trust", "Trust", "promoter", 1, 62.0], ["Grasim Industries Limited", "Company", "public", 1, 2.0]]})
    got = D.parents_of(list(names), names, src)
    assert got == {"ULTRA": {"parent": "GRASIM", "parent_name": "Grasim Industries Ltd", "pct": 56.1, "quarter": "2026-09"},
                   "ACC": {"parent": "AMBUJA", "parent_name": "Ambuja Cements Ltd", "pct": 50.6, "quarter": "2026-09"}}
    rows = [{"symbol": "AMBUJA", "name": "Ambuja", "revenue": 40656.0}, {"symbol": "ACC", "name": "ACC", "revenue": 25962.0, "parent": got["ACC"]},
            {"symbol": "SHREE", "name": "Shree", "revenue": 20000.0}]
    b = D.layer_block("Pan-India integrated producers", rows, set())
    assert b["revenue"] == 60656.0 and b["double"] == [{"symbol": "ACC", "name": "ACC", "parent": "Ambuja Cements Ltd", "pct": 50.6, "revenue": 25962.0}]
    head = deck.layer_head(b, b["companies"], lambda x: f"₹{x:,.0f} cr")
    assert "ACC left out of it, as Ambuja Cements Ltd holds 50.6% and its figures include it" in head
    row = deck.parents_row({"parents": [{"name": "UltraTech Cement Limited", "parent_name": "Grasim Industries Ltd", "pct": 56.1, "quarter": "2026-09",
                                         "basis": "consolidated"}]})
    assert row[0] == deck.PARENTS_LABEL and "UltraTech Cement Limited is 56.1% held by Grasim Industries Ltd (promoter, 2026-09 filing), whose figures are its consolidated ones" in row[1]
    assert "No shareholding filing is read for US companies" in deck.parents_row({"region": "US"})[1]


# ---------- G7: the latest quarter most companies report ----------
def test_the_latest_quarter_is_the_newest_a_third_of_the_companies_report_not_the_newest_two_do():
    rows = [{"symbol": f"S{i}", "name": f"S{i}", "quarter": {"of": "Sep 2026 vs Sep 2025", "sales": 10.0, "profit": 5.0}} for i in range(90)] + \
           [{"symbol": f"O{i}", "name": f"O{i}", "quarter": {"of": "Oct 2026 vs Oct 2025", "sales": 12.0, "profit": 3.0}} for i in range(2)]
    q = D.quarter_section(rows)
    assert q["quarter"] == "Sep 2026" and len(q["companies"]) == 90 and len(q["earlier"]) == 2
    india = [{"symbol": f"J{i}", "name": "", "quarter": {"of": "Jun 2026", "sales": 1.0, "profit": 1.0}} for i in range(6)] + \
            [{"symbol": f"S{i}", "name": "", "quarter": {"of": "Sep 2026", "sales": 1.0, "profit": 1.0}} for i in range(4)]
    assert D.quarter_section(india)["quarter"] == "Sep 2026"          # results season: the newer quarter, once a third report it


# ---------- G9: deck_check's classification checks ----------
def test_deck_check_fails_a_ranking_and_a_kind_beside_no_way_of_earning_read_and_a_layer_mostly_left_out():
    p1 = "EBITDA margin is highest in Clinical-stage platform developers (35.0%) and lowest in Commercial specialty biotechs (−7.2%)"
    p2 = "comparison: in its layer's figures: confirmed, how it earns shown and of the layer's kind"
    p3 = "Like-for-like model: no way of earning read for these companies."
    got = deck_check.check_pages([p1, p2, p3])
    assert got["counts"]["unread ranked"] == 1 and got["counts"]["unread kind"] == 1 and deck_check.failed(got)
    assert deck_check.check_pages([p1, p2])["counts"]["unread ranked"] == 0           # with a way of earning read, a ranking is fine
    left = "In the layer's calculations (2 of 11): Meta Platforms, AppLovin. Left out (9): way of earning not shown: Alphabet"
    assert deck_check.check_pages([left])["counts"]["left out>50%"] == 1
    assert deck_check.check_pages([left.replace("(2 of 11)", "(6 of 11)")])["counts"]["left out>50%"] == 0
    assert deck_check.check_pages(["In the layer's calculations (1 of 3): A."])["counts"]["left out>50%"] == 0      # under 4: the floor


def test_the_versions_moved():
    assert B.RULES == 52 and TR.PLACE_CARRY[52] == 51 and TR.PLACE_CARRY[51] == 50 and TR.PLACE_CARRY[50] == 49 and TR.PLACE_CARRY[49] == 48 and TR.PLACE_CARRY[48] == 47          # d53 (R53): RULES 52, PLACE_CARRY[52] = 51, deck 63, dive text 23 (updated on purpose); gl52 (R52): RULES 51, PLACE_CARRY[51] = 50, deck 62, dive text 22 (updated on purpose); rv51 (R51): RULES 50, PLACE_CARRY[50] = 49, deck 61, dive text 21 (updated on purpose)
    assert deck.THEME_DECK_VERSION == 63 and D.DIVE_TEXT == 23          # d53 (R53): RULES 52, PLACE_CARRY[52] = 51, deck 63, dive text 23 (updated on purpose); gl52 (R52): RULES 51, PLACE_CARRY[51] = 50, deck 62, dive text 22 (updated on purpose); rv51 (R51): RULES 50, PLACE_CARRY[50] = 49, deck 61, dive text 21 (updated on purpose)


def test_deck_check_counts_the_not_checked_yet_in_other_and_reads_a_wrapped_label():
    """The live Biotech deck: "In informative" and "layers" on two lines, 225 of 821 in informative layers, 594 not checked yet: it passed."""
    page = (" Coverage flag                 27%                   27% of the companies placed are in informative layers\n"
            " In informative                225 of 821            in a layer the map names; the other 596 in “Other”: 2 fit none of the map's\n"
            " layers                        (27%)                 layers; 594 not checked yet\n")
    got = deck_check.check_pages([page])
    assert got["counts"]["other>40%"] == 1 and "596 outside them (73%)" in got["findings"][0]["text"]
