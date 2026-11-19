"""c1 (R44, the outside review of the live Release 43 decks): classification coverage only from the companies' own words or official
industry, never forced; a layer named by how its companies earn says why it is never ranked; a company the map names from another industry
says why it is in the theme, apart from whether it is in its layer's figures. Proven on the exact replay of the live Release 43 placement
inputs (tests/test_exact_replay.py) and on made-up rows."""
from app import deck
from app.intel import theme_base as B
from app.intel import theme_data as D
from tests import test_exact_replay as T


def _replay(key: str):
    d = T.live(key)
    out, _ = T.replay(key, carried=d["kept_version"] != B.RULES)
    return d, out


def _layer_of(out: dict) -> dict:
    return {c["ticker"]: v for v in out["value_chain"] for c in v["companies"]}


def _other(out: dict) -> set:
    return {c["ticker"] for v in out["value_chain"] if v.get("official") and v.get("basis") == "rest" for c in v["companies"]}


def test_metals_ferro_alloy_makers_are_a_layer_of_their_industry_not_miners():
    """Ten "Ferro & Silica Manganese" companies, five with words of their own (ferro chrome, ferro alloys), were in "Mining of coal and iron
    ore" or "Other": they are one layer of their official industry; the miners stay; "Other" holds 14 of 65, not 32."""
    d, out = _replay("metals")
    at = _layer_of(out)
    ferro = {s for s, v in at.items() if v["layer"] == "Ferro alloys"}
    assert {"IMFA", "MAITHANALL", "VISACHROME", "SHYAMCENT", "IMPEXFERRO"} <= ferro and len(ferro) == 10
    assert all(at[s].get("industry_group") for s in ferro)
    assert at["COALINDIA"]["layer"] == at["NMDC"]["layer"] == "Mining of coal and iron ore"
    assert at["HINDALCO"]["layer"] == "Aluminium and copper smelting"         # the smelters keep their layer
    was = sum(1 for v in d["value_chain"] if v.get("official") and v.get("basis") == "rest" for _ in v["companies"])
    assert was == 32 and len(_other(out)) == 14


def test_a_company_whose_words_name_another_business_is_never_forced_into_a_layer():
    """Words of another way of earning (coal logistics, transport, a non-ferrous metals dealer) keep a company in "Other" whatever its
    official industry; so do words read at "low" (Siemens Energy India)."""
    _, metals = _replay("metals")
    assert {"CMLL", "SINDHUTRAD", "BONLON", "JAINREC"} <= _other(metals)
    _, util = _replay("utilities")
    assert {"GVPIL", "JYOTISTRUC", "PTC", "ENRIN"} <= _other(util)


def test_utilities_cable_makers_and_equipment_makers_are_apart_by_their_industry():
    _, out = _replay("utilities")
    at = _layer_of(out)
    assert at["POLYCAB"]["layer"] == at["KEI"]["layer"] == at["SYSTEMATIC"]["layer"] == "Electrical cables"
    assert at["BHEL"]["layer"] == at["SIEMENS"]["layer"] == at["VANS"]["layer"] == "Heavy electrical equipment"
    assert all(c.get("placed_by") in ("by_industry", "by_words") for c in at["POLYCAB"]["companies"])


def test_retail_other_share_falls_by_evidence_and_other_businesses_leave_the_theme():
    """Consumer retail: 29 of 90 in "Other" live. A sportsbook, a broadcast network, an enterprise software house, a VR concert producer and a
    diversified holding company filed as retail leave the theme, each named on the coverage with its reason; specialty clothing chains
    whose words say "clothing" or "apparel" join "Family clothing stores"; "Other" holds 19 of 85."""
    _, out = _replay("retail")
    gone = {x["ticker"]: x for x in (out.get("placements") or {}).get("off_industry") or []}
    assert {"VIPZ", "MDEX", "ESSI", "AMZE", "LIVE"} <= set(gone)
    assert all(x.get("why", "").startswith("filed under ") and "another business" in x["why"] for x in gone.values())
    at = _layer_of(out)
    assert {at[s]["layer"] for s in ("ZUMZ", "TLYS", "DLTH", "PLCE")} == {"Family clothing stores"}
    assert at["DDS"].get("basis") == "rest" and at["SVV"].get("basis") == "rest"       # no layer says what they do
    # cl48 (R47, updated on purpose): lululemon and TheRealReal, in "Off-price" by default with no words of it, are in "Other"
    # (test_exact_replay APPROVED: 21 of 85); Torrid, there by "branched off", joins "Family clothing stores" by its words
    assert len(_other(out)) == 21 and len(at) == 85
    assert {"LULU", "REAL"} <= _other(out) and at["CURV"]["layer"] == "Family clothing stores"


def test_a_map_pick_from_another_industry_whose_words_say_its_layer_is_confirmed():
    """Insurance: PB Fintech, the map's own pick for "Distribution and aggregation", filed under fintech, was listed as not confirmed on the
    live Release 43 (its check timed out); its own words say "distribution", so it is in the theme by them. The REITs, whose words don't say
    their layer's name, are not confirmed by it."""
    _, out = _replay("insurance")
    pb = next(c for v in out["value_chain"] for c in v["companies"] if c["ticker"] == "POLICYBZR")
    assert pb["verified"] and pb["verified_by"] == "words"
    rec = D.theme_record({**pb, "industry": "Financial Technology (Fintech)"}, D.membership(pb, set()))
    assert rec["in"] and rec["by"] == "other_industry" and "its own words say what that layer's name says" in rec["why"]
    _, realty = _replay("realty")
    reit = [c for v in realty["value_chain"] if v["layer"] == "Rent-yielding commercial property trusts" for c in v["companies"]
            if c.get("base") is False]
    assert reit and not any(c.get("verified_by") == "words" for c in reit)


def test_a_layer_named_by_how_its_companies_earn_says_why_it_is_never_ranked():
    """Semiconductors US: "Makers of their own products" holds memory, processor, RF, laser, optics and photomask makers: kept together and
    never ranked (no group of them by what they make is confirmed by their words), and its page says why."""
    _, out = _replay("semis")
    v = next(v for v in out["value_chain"] if v["layer"] == "Makers of their own products")
    assert {"MU", "INTC", "IPGP", "PLAB"} <= {c["ticker"] for c in v["companies"]}
    assert v["model"]["by_how"] and B.BY_HOW_SAID in v["model"]["line"]
    assert not D.headline_ok(12, 12, v["model"])
    assert B.BY_HOW_SAID in deck.layer_common(v)
    assert B.BY_HOW_SAID.rstrip(".").split(": ", 1)[1] == D.RANK_WHY["how"].replace("they earn", "its companies earn")


def test_theme_membership_and_comparison_are_two_records_each_with_its_reason():
    base = {"base": True, "industry": "Life Insurance"}
    assert D.theme_record(base, "core") == {"in": True, "status": "core", "by": "industry",
                                             "why": "filed under Life Insurance, an official industry of the theme"}
    off = D.theme_record({"base": True, "industry": "General Insurance"}, "unverified")
    assert not off["in"] and off["why"].endswith("but its own words describe other work")
    assert D.theme_record({"base": False, "verified": False, "industry": "X"}, "unverified")["by"] == "other_industry"
    # the comparison decision, apart: in the theme yet out of the figures for how it earns, or in the figures of a layer never ranked
    assert D.comparison_said({"in": False, "why": "other business"}, {}).startswith("listed in its layer, left out of its figures")
    assert D.comparison_said({"in": False, "why": "not confirmed"}, {}) == "left out of every figure: not confirmed in the theme"
    assert "never ranked" in D.comparison_said({"in": True, "why": ""}, {"model": {"by_how": True}})
    assert D.comparison_said({"in": True, "why": ""}, {"model": {"id": "x"}}).startswith("in its layer's figures")


def test_the_coverage_page_says_which_companies_are_in_the_theme_from_other_industries_and_why():
    why = ("the theme's map names it in one of its own layers, from another industry (Financial Technology (Fintech)); its own words say "
           "what that layer's name says")
    v = {"layers": [
        {"layer": "Distribution and aggregation", "companies": [
            {"symbol": "PB", "name": "PB Fintech Ltd", "map_industry": "Financial Technology (Fintech)", "status": "exposure",
             "theme": {"in": True, "status": "exposure", "by": "other_industry", "why": why},
             "calc": {"in": True, "why": ""},
             "comparison": "in its layer's figures: confirmed, how it earns shown and of the layer's kind, with a figure"}]},
        {"layer": "Life insurance underwriting", "companies": [
            {"symbol": "L", "name": "Life Co", "status": "core", "theme": {"in": True, "by": "industry", "why": "filed under Life Insurance"},
             "calc": {"in": True, "why": ""}}]}]}
    n, line = deck.other_industry_line(v)
    assert n == 1
    assert line == ("In “Distribution and aggregation”, a layer of the theme's map, all its companies of other industries: PB Fintech Ltd "
                    "(Financial Technology (Fintech)): membership: the theme's map names it in one of its own layers, from another industry; "
                    "its own words say what that layer's name says; comparison: in its layer's figures: confirmed, how it earns shown and "
                    "of the layer's kind, with a figure.")
    rows = deck.coverage_table(v, {"total": 2, "n": 2})
    assert [deck.COVERAGE_KINDS[8], "1", line] in rows
    assert not deck.coverage_table_flags(rows, v, {"total": 2, "n": 2})
    assert deck.other_industry_line({"layers": v["layers"][1:]}) == (0, "")
