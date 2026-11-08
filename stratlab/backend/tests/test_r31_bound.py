"""Release 31 (lane r31-bound): the owner's review of the 14 live R30 decks.
1. P0 real estate: lenders never share a layer with developers or landlords; developers (sell) and landlords (lease, REITs) are apart.
2. P0 metals and mining: a margin headline across layers needs one commodity as well as one family (a family's sub-basis).
3. P0 semiconductors and IT services: fabless = designs and has others make, unless it owns fabs (IDM); no two layers of one primary model.
4. P1 one headline floor, HEADLINE_MIN = 5 companies with the figure in each compared layer; marks keep COMPARE_MIN = 3.
5. P1 the model-specific figures the sources don't hold, and why, once on the coverage table.
6. P1 the analysed universe raised from 60 to 100 companies.
7. P2 a figure missing because its reading was partial says so ("read for N of M; K partial").
Generic: synthetic themes only, no real company's name or figure."""
import copy

import pytest

from app import deck
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from tests import synthetic_themes_r27 as S
from tests.synth_structures_r27class import build, structures as class_structures
from tests.synth_structures_r29 import structures as broad_structures
from tests.test_r18_deck import deck_of
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule


def _rows(prefix, n, name, what, ind, model):
    return [(f"{prefix}{i}", f"{name} {i} Ltd", what, ind, model, (), "high") for i in range(n)]


def _refined(t: dict) -> dict:
    """Each company's model as an AI answer gives it, made exact by its own evidence (theme_check.refine_model), as place_rest does."""
    ev = {c["ticker"]: C.model_evidence(c.get("industry") or "", c.get("what") or "") for v in t["map"]["value_chain"] for c in v["companies"]}
    t["given"] = dict(t["models"])
    t["models"] = {s: C.refine_model(md, ev[s]) for s, md in t["models"].items()}
    return t


def split(t: dict):
    t = copy.deepcopy(t)
    vc = B.by_model(t["map"]["value_chain"], t["models"], t["map"]["sector"], tags=t["tags"], confidence=t["confidence"])
    return t, vc, {**t["map"], "value_chain": vc}


# ---------- 1. real estate: lenders, developers and landlords apart ----------
def realty_mixed():
    """The live realty map's shape: one AI layer mixing developers, landlords (a REIT among them) and two housing-finance companies the AI
    called developers; a leasing layer; contractors."""
    return _refined(build("IN", "Real estate", [
        ("Residential and commercial real estate", "Homes and offices.",
         _rows("DEV", 6, "Homecrest", "develops and sells residential apartments and plotted townships", "Residential, Commercial Projects",
               "property_development")
         + _rows("HFC", 2, "Homeloan", "provides home loans and loans against property to salaried buyers", "Housing Finance Company",
                 "property_development")
         + _rows("RIT", 2, "Officetrust", "owns and leases office parks to tenants; a REIT", "Realty", "property_development")),
        ("Office and mall owners", "Rent.",
         _rows("LSE", 4, "Mallhold", "owns malls and office space and earns rent on leases", "Realty", "property")),
        ("Construction contractors", "Contracts.",
         _rows("EPC", 3, "Buildco", "builds buildings under EPC contracts for clients", "Civil Construction", "construction")),
    ], [("lending", "property_development"), ("lending", "property"), ("property_development", "property"), ("lending", "construction")]))


def test_a_housing_finance_company_is_never_a_developer_and_a_reit_never_a_developer():
    ev = C.model_evidence
    assert C.refine_model("property_development", ev("Housing Finance Company", "lends to home buyers")) == "lending"
    assert C.refine_model("property", ev("Realty", "provides home loans to salaried buyers")) == "lending"
    assert C.refine_model("property_development", ev("Realty", "owns and leases office parks; a REIT")) == "property"
    assert C.refine_model("property", ev("Realty", "develops and sells residential apartments")) == "property_development"
    assert C.refine_model("property_development", ev("Realty", "develops apartments and leases malls")) == "property_development"   # both: as given
    assert C.refine_model("lending", ev("Realty", "develops apartments")) == "lending"                    # a lender's own answer is untouched
    assert len({C.model_family(k) for k in ("lending", "property_development", "property")}) == 3
    assert "housing finance" in C.KEEP_APART and "fabless" in C.KEEP_APART


def test_the_realty_set_splits_lenders_developers_and_landlords_and_every_deck_rule_holds():
    t, vc, m = split(realty_mixed())
    assert t["models"]["HFC0"] == "lending" and t["models"]["RIT0"] == "property" and t["models"]["DEV0"] == "property_development"
    for v in vc:
        ids = {t["models"].get(c["ticker"]) for c in v["companies"]} - {None}
        assert len({C.model_family(x) for x in ids}) <= 1, (v["layer"], ids)
        for a, b in realty_mixed()["apart"]:
            assert not (a in ids and b in ids), (v["layer"], a, b)
    lend = next(v for v in vc if {c["ticker"] for c in v["companies"]} == {"HFC0", "HFC1"})
    assert lend["model"]["family"] == "lending" and lend["layer"] == "Lenders"
    leasing = next(v for v in vc if any(c["ticker"] == "LSE0" for c in v["companies"]))
    assert {"RIT0", "RIT1"} <= {c["ticker"] for c in leasing["companies"]}                # the REIT joins the landlords
    view, slides = deck_of(t["region"], m, t["facts"])
    every_rule("realty mixed (IN)", view, slides)
    ch = view["chain"]
    assert "Lenders" not in (ch.get("compared") or [])                              # a lender is never ranked against developers


# ---------- 2. metals: one commodity as well as one family ----------
def test_each_company_s_commodity_is_read_from_its_industry_then_its_words():
    ev = C.model_evidence
    assert C.commodity_of(ev("Iron & Steel", "makes steel from iron ore and coal in blast furnaces")) == "steel"
    assert C.commodity_of(ev("Aluminium", "smelts aluminium")) == "aluminium"
    assert C.commodity_of(ev("Zinc", "mines zinc, lead and silver")) == "zinc_lead"
    assert C.commodity_of(ev("", "mines copper ore")) == "copper"
    assert C.commodity_of(ev("Industrial Minerals", "mines iron ore and coal")) == "mixed"
    assert C.commodity_of(ev("Industrial Minerals", "mines coal")) == "coal"
    assert C.commodity_of(ev("Ferro Alloys", "makes ferro alloys for steel makers")) == "ferro_alloys"
    assert C.commodity_of(ev("Gold", "refines gold")) == "precious" and C.commodity_of(ev("", "trades goods")) == "other"
    assert C.sub_basis("mining", [ev("Iron & Steel", "x")] * 3 + [ev("Aluminium", "x")]) == "steel"
    assert C.sub_basis("mining", [ev("Iron & Steel", "x"), ev("Aluminium", "x")]) == "mixed"
    assert C.sub_basis("services", [ev("Iron & Steel", "x")]) == ""                   # a family that declares no sub-basis
    assert set(C.SUB_BASIS) >= {"mining", "metal_processing", "resources"}


def metals_layers(spec):
    """A metals theme of the AI's layers, each of one model; spec: [(layer, prefix, n, what, industry, model, margin)]."""
    t = build("IN", "Metals and mining", [(nm, "x", _rows(p, n, nm.split()[0], what, ind, md)) for nm, p, n, what, ind, md, _ in spec], [])
    for nm, p, n, _, _, _, e in spec:
        for i in range(n):
            for y in t["facts"][f"{p}{i}"]["years"]:
                y["opm"] = e
    return t


def test_layers_of_one_family_and_different_commodities_are_described_never_ranked():
    t = metals_layers([("Aluminium smelting", "ALS", 5, "smelts aluminium from bauxite", "Aluminium", "commodity_mining", 41),
                       ("Ferro alloy producers", "FER", 5, "makes ferro alloys in its smelters", "Ferro Alloys", "commodity_mining", 13),
                       ("Coal mining", "COL", 5, "mines coal", "Coal", "commodity_mining", 30)])
    t, vc, m = split(t)
    assert {v["model"].get("sub") for v in vc if not v.get("official")} == {"aluminium", "ferro_alloys", "coal"}
    view, slides = deck_of(t["region"], m, t["facts"])
    ch = view["chain"]
    assert ch["highest"] is None and ch["lowest"] is None and "not ranked" in ch["line"] and "commodities differ" in ch["line"]
    found = " ".join(str(x) for s in slides for b in s.blocks for x in (b.get("paras") or []) + [ln for it in b.get("items") or []
                                                                                                 if isinstance(it, dict) for ln in it.get("lines") or []])
    assert "Median EBITDA margin is highest" not in found and "has the highest median EBITDA margin" not in found
    every_rule("metals by commodity (IN)", view, slides)


def test_layers_of_one_commodity_are_still_ranked_among_themselves():
    t = metals_layers([("Integrated steel", "IST", 5, "makes steel from iron ore in blast furnaces", "Iron & Steel", "commodity_mining", 22),
                       ("Mini mills", "MML", 5, "makes steel in electric arc furnaces from sponge iron", "Iron & Steel", "commodity_mining", 12),
                       ("Aluminium smelting", "ALS", 5, "smelts aluminium from bauxite", "Aluminium", "commodity_mining", 41)])
    t, vc, m = split(t)
    view, _ = deck_of(t["region"], m, t["facts"])
    ch = view["chain"]
    assert set(ch["compared"]) == {"Integrated steel", "Mini mills"} and ch["highest"] == "Integrated steel" and "Aluminium" not in ch["line"]
    rows = [("A", 10.0, 5, {"family": "mining", "sub": "steel"}), ("B", 5.0, 5, {"family": "mining", "sub": "steel"}),
            ("C", 50.0, 5, {"family": "mining", "sub": "copper"})]
    pair = D.rank_pair(rows, lambda r: r[1], lambda r: r[2], model=lambda r: r[3])
    assert pair and {pair[0][0], pair[1][0]} == {"A", "B"}
    assert D.rank_pair(rows[1:], lambda r: r[1], lambda r: r[2], model=lambda r: r[3]) is None              # a tie of commodities: none
    mixed = [("A", 10.0, 5, {"family": "mining", "sub": "mixed"}), ("B", 5.0, 5, {"family": "mining", "sub": "mixed"})]
    assert D.rank_pair(mixed, lambda r: r[1], lambda r: r[2], model=lambda r: r[3]) is None                # "mixed" is no commodity


# ---------- 3. semiconductors and IT services: one boundary, one primary model a layer ----------
def test_fabless_is_designing_and_having_others_make_unless_the_company_owns_fabs():
    ev = C.model_evidence
    assert C.refine_model("manufacturing", ev("Semiconductors", "designs chips and outsources manufacturing to foundries")) == "fabless"
    assert C.refine_model("manufacturing", ev("Semiconductors & Related Devices", "fabless: designs chips that foundries make")) == "fabless"
    assert C.refine_model("fabless", ev("Semiconductors", "designs and makes chips in its own fabs")) == "manufacturing"
    assert C.refine_model("fabless", ev("Semiconductors", "designs chips, makes some in its own fabs and outsources the rest to foundries")) == "fabless"
    assert C.refine_model("manufacturing", ev("Special Industry Machinery", "manufactures wafer fab equipment")) == "manufacturing"


def semis_split_layer():
    """A chip map whose "Fabless chip design" catch-all holds fab owners and fabless designers: the split by model makes a layer of the
    fabless designers beside the map's own fabless layer, the live R30 deck's "Product designers that outsource making"."""
    return _refined(build("US", "Semiconductors", [
        ("Fabless chip design", "Designs chips.",
         _rows("FBA", 3, "Gatesign", "designs chips that foundries make", "Semiconductors & Related Devices", "fabless")),
        ("Chip makers", "Chips.",
         _rows("IDM", 8, "Wafermade", "designs and makes chips in its own fabs", "Semiconductors & Related Devices", "manufacturing")
         + _rows("FBB", 6, "Siliconly", "fabless: designs chips and has them made by foundries", "Semiconductors & Related Devices", "fabless")),
        ("Equipment", "Tools.", _rows("EQP", 3, "Etchtool", "manufactures wafer fab equipment", "Special Industry Machinery", "manufacturing")),
        ("Packaging and test", "OSAT.",
         _rows("OST", 3, "Packright", "packages and tests chips for other companies under contract", "Semiconductors & Related Devices",
               "contract_manufacturing")),
    ], []))


def test_a_layer_the_split_made_joins_the_map_s_own_layer_of_its_primary_model():
    t, vc, m = split(semis_split_layer())
    keys = [(v["model"]["id"], v["model"]["family"], v["model"].get("sub", "")) for v in vc if not v.get("official") and v.get("model", {}).get("id")
            and not v["model"].get("sparse") and not v["model"].get("same_as") and not v.get("scale")]
    assert len(keys) == len(set(keys)), keys                                          # no two layers of one primary model, family and sub-basis
    fab = next(v for v in vc if v["layer"] == "Fabless chip design")
    assert {c["ticker"] for c in fab["companies"]} >= {f"FBB{i}" for i in range(6)} and fab["model"]["id"] == "fabless"
    assert "Product designers that outsource making" not in [v["layer"] for v in vc]
    view, slides = deck_of(t["region"], m, t["facts"])
    every_rule("semis split (US)", view, slides)


def test_two_of_the_map_s_own_layers_of_one_model_both_stay_and_say_so():
    t = build("IN", "Semiconductors", [
        ("Chip makers", "Chips.", _rows("IDM", 4, "Wafermade", "makes chips in its own fabs", "Semiconductors", "manufacturing")),
        ("Equipment makers", "Tools.", _rows("EQP", 4, "Etchtool", "manufactures wafer fab equipment", "Industrial Machinery", "manufacturing")),
    ], [])
    _, vc, _ = split(t)
    a, b = vc[0]["model"], vc[1]["model"]
    assert a["same_as"] == ["Equipment makers"] and b["same_as"] == ["Chip makers"]
    assert "earn the same way as those of “Equipment makers”; the map keeps them as separate layers." in a["line"]


@pytest.mark.parametrize("name,theme", list(class_structures()) + list(broad_structures()),
                         ids=[n for n, _ in list(class_structures()) + list(broad_structures())])
def test_on_every_structure_no_two_layers_share_a_primary_model_unless_the_deck_says_why(name, theme):
    _, vc, _ = split(theme)
    seen = {}
    for v in vc:
        md = v.get("model") or {}
        if v.get("official") or v.get("scale") or not md.get("id") or md.get("sparse") or md.get("sub") == "mixed":
            continue
        k = (md["id"], md["family"], md.get("sub", ""))
        if k in seen:
            assert md.get("same_as") and seen[k] in md["same_as"] and "the map keeps them as separate layers" in md["line"], (name, v["layer"])
        seen.setdefault(k, v["layer"])


# ---------- 4. one headline floor of 5 ----------
def _blk(name, n, e, fam="making"):
    cos = [{"symbol": f"{name}{i}", "status": "core", "year": "Mar 2026"} for i in range(n)]
    return {"layer": name, "n": n, "revenue": 100.0, "companies": cos, "model": {"id": fam, "family": fam, "line": ""},
            "stats": {"ebitda": {"n": n, "median": e}, "net": None, "roce": None}}


def test_a_layer_vs_layer_headline_needs_five_companies_with_the_figure_in_each():
    assert D.HEADLINE_MIN == 5 and D.COMPARE_MIN == 3
    four = D.chain_table([_blk("A", 5, 30.0), _blk("B", 4, 10.0), _blk("C", 5, 20.0)])
    assert four["compared"] == ["A", "C"] and four["highest"] == "A" and four["lowest"] == "C"
    assert D.chain_table([_blk("A", 4, 30.0), _blk("B", 4, 10.0)])["line"] is None
    rows = [("A", 30.0, 5), ("B", 10.0, 4), ("C", 20.0, 5)]
    assert [x[0] for x in D.rank_pair(rows, lambda r: r[1], lambda r: r[2])] == ["A", "C"]
    assert D.rank_pair(rows, lambda r: r[1], lambda r: r[2], floor=3)[1][0] == "B"           # an explicit floor still holds
    assert deck.headline_flag("Median EBITDA margin is highest in A (30%, 4 of 4 companies)") == "ranked on 4 of 4"
    assert deck.headline_flag("Median EBITDA margin is highest in A (30%, 5 of 6 companies)") is None
    # the marks (green, red) keep the floor of 3; the footnote says both
    note = deck.compare_note({"highest": "A"}, "ebitda")
    assert "at least 3 companies" in note and "needs at least 5 companies with the figure in each" in note


def _all_decks():
    for name, v, slides in S.decks():
        yield name, v, slides
    for name, t in list(class_structures()) + list(broad_structures()):
        tt, vc, m = split(t)
        yield name, *deck_of(tt["region"], m, tt["facts"])


def test_no_synthetic_deck_ranks_a_layer_of_fewer_than_five_companies_and_every_rule_holds():
    for name, v, slides in _all_decks():
        ch = v["chain"]
        rows = {r["layer"]: r for r in ch["rows"]}
        if ch.get("highest"):
            k = "ebitda_n" if ch["measure"] == "ebitda" else "roe_n"
            assert all(rows[x][k] >= D.HEADLINE_MIN for x in ch["compared"]), (name, ch["compared"])
        for ln in deck.check_deck(slides) if hasattr(deck, "check_deck") else []:
            assert "ranked on" not in str(ln), (name, ln)
        every_rule(name, v, slides)


# ---------- 5. figures the sources don't hold ----------
def test_the_coverage_table_says_once_which_model_figures_the_sources_don_t_hold_and_why():
    t, vc, m = split(realty_mixed())
    view, slides = deck_of(t["region"], m, t["facts"])
    rows = deck.coverage_table(view, deck.coverage(view))
    gone = next(r for r in rows if r[0] == "Not in the sources")[2]
    assert "Property developers: pre-sales (bookings), collections and land bank aren't elements" in gone
    assert "Property and leasing: occupancy" in gone and gone.count("Property developers") == 1
    assert deck.coverage_table_flags(rows, view, deck.coverage(view)) == []
    # an insurer's: on the coverage table only when no sector table says it already
    ins = {"layers": [{"model": {"family": "life_insurance"}, "companies": []}]}
    assert "VNB, APE and embedded value" in deck.not_in_sources(ins)
    assert deck.not_in_sources({**ins, "sections": {"sector": {"families": {"insurer": {"not_filed": "said"}}}}}) == ""
    # a theme of other models: no row
    region, mm, f, _ = S.chemicals_in()
    v2, _ = deck_of(region, mm, f)
    assert not any(r[0] == "Not in the sources" for r in deck.coverage_table(v2, deck.coverage(v2)))


# ---------- 6. the analysed universe ----------
def test_the_analysed_universe_is_a_hundred_companies_at_most():
    assert B.FIGURES_MAX == 100
    cos = [{"ticker": f"C{i}", "cap": 10000 - i} for i in range(150)]
    m = {"value_chain": [{"layer": "Official", "official": True, "companies": cos}]}
    fm, said = B.for_figures(m)
    assert said == {"shown": 100, "of": 150} and len(fm["value_chain"][0]["companies"]) == 100


# ---------- 7. partial reads ----------
def test_a_figure_missing_because_its_years_were_read_in_part_says_so():
    def row(sym, ebitda, years, year="Mar 2026"):
        return {"symbol": sym, "status": "core", "revenue": 100.0, "ebitda": ebitda, "net": 5.0, "sales_1y": 3.0, "quarter": {"of": "q"},
                "year": year, "years": years, "bank": False}
    full = [{"year": f"Mar {y}", "sales": 100.0, "profit": 5.0, "opm": 10.0} for y in (2023, 2024, 2025, 2026)]
    gap = [full[0], full[2], full[3]]                                              # Mar 2024 not read
    hole = full[:3] + [{"year": "Mar 2026", "sales": 100.0, "profit": 5.0, "opm": None}]
    v = {"layers": [{"companies": [row("A", 10.0, full), row("B", None, hole), row("C", None, gap), row("D", None, full)]}]}
    assert deck.partial_line(v) == "EBITDA margin read for 1 of 4; 2 partial"
    assert deck.partial_line({"layers": [{"companies": [row("A", 10.0, full)]}]}) == ""
    rows = [["Partly read", "", deck.partial_line(v)]]
    assert deck.coverage_table_flags(rows, {"members_with_figures": 4}, {"share": None}) == ["no row: Companies, by count"]   # N of M holds


def test_the_versions_are_bumped_so_kept_maps_and_decks_are_made_again():
    from app.intel import theme_routes as T
    assert B.RULES >= 31 and deck.THEME_DECK_VERSION >= 31 and T.PLACE_CARRY[31] == 30 and T.PLACE_CARRY[32] == 31   # R32 bumped both (updated on purpose)


def test_a_ranking_line_states_how_many_layers_it_compared():
    """Live R31.1 pharma/semis: a layer with a higher or lower median than those named was left out without a word (R34)."""
    t = metals_layers([("Integrated steel", "IST", 5, "makes steel from iron ore in blast furnaces", "Iron & Steel", "commodity_mining", 22),
                       ("Mini mills", "MML", 5, "makes steel in electric arc furnaces from sponge iron", "Iron & Steel", "commodity_mining", 12),
                       ("Aluminium smelting", "ALS", 5, "smelts aluminium from bauxite", "Aluminium", "commodity_mining", 41)])
    t, vc, m = split(t)
    view, _ = deck_of(t["region"], m, t["facts"])
    line = view["chain"]["line"]
    assert "Compared: 2 of the 3 layers with a median" in line and "Aluminium" not in line
