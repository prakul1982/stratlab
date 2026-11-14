"""Lane ex49 (Release 49), the outside review of the live Release 48 decks (avg 9.09; Consumer retail US 8.8).

1. P0: page 41 of the live R48 Consumer retail deck left lululemon out of "Apparel and consumer brand owners" as "other business", though its
   own words ("principally a designer, distributor, and retailer of technical athletic apparel") placed it there. A real difference in
   revenue model, insufficient evidence and partial comparability were said with the same words. Now every company left out of a layer's
   figures carries one precise reason (theme_data.out_reason): a different revenue model names both models, insufficient evidence says what
   is missing, another business says its words describe another business than its industry; a company in the figures in part says which
   part. A company read as a retailer whose own words say it designs the goods it sells, in a layer of makers its words name, is in that
   layer's figures (theme_base.by_model `own_goods`, theme_check.own_goods). Acceptance on the live R46 placement inputs: lululemon is in
   its layer's figures and no other exclusion changes (tests/fixtures/themes_live/inputs_r46; the 14 themes are in the lane's report).
2. P1: the capital-intensity check is labelled as a proxy for capital needs wherever it is used, its inputs are checked (both parts stored,
   the debt of the revenue's year, a positive revenue; what is missing is said), and passing it never makes layers comparable alone. Layers
   are ranked only of one business model the map's words support (theme_data.one_business): a layer the map names for custom synthesis or
   contract manufacturing is shown, not ranked, beside makers of their own products.
3. P1: a net margin above EBITDA says per company which line is still missing (theme_data.missing_said), and a stored page rebuilt with the
   lines (FACTS_VERSION 10) is read without a Refresh (theme_routes.facts_piece, pages_rebuilt).
4. Presentation: one comparison a page, its claim the takeaway, its rules a line each in larger type, one table.

Every company outside the live fixtures is synthetic."""
import copy
import json
import pathlib

import pytest

from app import computed, db, deck
from app.intel import routes, theme_base as B, theme_check as T, theme_data as D, theme_routes as TR
from tests import test_exact_replay as X
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_r48_compare import basis_pages, chem
from tests.test_r48_reconcile import co

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"
BRANDS = "Apparel and consumer brand owners"


def replay46(key: str) -> dict:
    d = json.loads((LIVE / "inputs_r46" / f"{key}.json").read_text())
    d = d.get("data", d)
    m = X.pre_map(d, X.RECOVERED["origin"].get(key), X.RECOVERED["description"].get(key))
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d["previous"])
    return out


def outs_of(vc) -> dict:
    """{symbol: (layer, out_reason)} of every company listed in a layer of the map but left out of its figures."""
    return {c["ticker"]: (v["layer"], D.out_reason({**D.model_fields(v, c["ticker"]), "status": "core"}))
            for v in vc if not v.get("official") for c in v["companies"] if c.get("model_out")}


# ---------- 1. P0: precise exclusion reasons; lululemon in its layer's figures ----------
def test_lululemon_is_in_the_brand_owners_figures_on_the_live_release_46_inputs():
    """Fails before: lululemon was listed in "Apparel and consumer brand owners" with model_out "other", printed "other business"."""
    out = replay46("retail")
    layer = next(v for v in out["value_chain"] if v["layer"] == BRANDS)
    lulu = next(c for c in layer["companies"] if c["ticker"] == "LULU")
    assert lulu["model"] == "retail" and "model_out" not in lulu and lulu["own_goods"]
    row = {**D.model_fields(layer, "LULU"), "status": "core", "revenue": 10.0}
    assert D.calc_record(row) == {"in": True, "why": ""} and row["own_goods"]
    assert "designs the goods it sells" in D.comparison_said({**D.calc_record(row), "own_goods": True}, {"model": layer["model"]})
    # every other exclusion on the live Consumer retail inputs is unchanged and said precisely: the online marketplaces in the online
    # retailers' layer, a different revenue model with both models named; the Honest Company and Newegg, insufficient evidence with what is missing
    got = outs_of(out["value_chain"])
    assert set(got) == {"HNST", "GCT", "DIBS", "MELI", "EBAY", "NEGG"}
    for s_ in ("GCT", "DIBS", "MELI", "EBAY"):
        r = got[s_][1]
        assert r["kind"] == "different revenue model" and r["label"] == "different revenue model (platforms and marketplaces, the layer's retail)"
        assert r["detail"].startswith("the way of earning of “Platforms and marketplaces” (commissions, listing fees or advertising on platforms they run), "
                                      "not the layer's, that of “Retail” (the margin on goods bought")
    # gl52 (R52, updated on purpose): a low-confidence read is never printed as what the company was read as
    assert got["HNST"][1] == {"kind": "insufficient evidence", "label": "insufficient evidence (how it earns read only weakly)",
                              "detail": "its evidence shows how it earns only weakly (low confidence)"}
    assert got["NEGG"][1]["label"] == "insufficient evidence (its words don't state how it earns)"


def test_no_other_exclusion_changes_on_the_live_utilities_inputs_and_each_says_what_is_missing():
    out = replay46("utilities")
    got = outs_of(out["value_chain"])
    # gl52 (R52, updated on purpose): the 7 heavy electrical makers with no description of their own are in "Heavy electrical equipment"'s
    # figures on their industry, which the layer's own name names; only KPEL is still left out
    assert set(got) == {"KPEL"} and {r["kind"] for _, r in got.values()} == {"insufficient evidence"}
    heavy = next(v for v in out["value_chain"] if v["layer"] == "Heavy electrical equipment")
    assert {"KPGEL", "VANS", "RAKSAN", "UVDRHOR", "ACCORDTS", "STARDELTA", "JYOTI"} <= {c["ticker"] for c in heavy["companies"] if c.get("on_industry")}
    # gl50 (R50, updated on purpose): a company with no description of its own read is "not checked yet"
    assert all(r["label"] in ("insufficient evidence (not checked yet, no description of its own)", "insufficient evidence (how it earns read only weakly)")
               for _, r in got.values())


def test_a_designer_and_retailer_of_its_goods_sells_products_of_its_own_and_a_retailer_of_others_does_not():
    assert T.own_goods("Industry: Apparel. Acme is principally a designer, distributor, and retailer of technical athletic apparel.")
    assert T.own_goods("Acme designs and sells furniture through its own stores.")
    assert T.own_goods("Acme manufactures cookware sold under the Acme brand.")
    assert not T.own_goods("Acme operates 400 stores selling apparel and home goods from national brands.")
    assert not T.own_goods("Acme sells its products to designers of apparel.")            # its customers are not its own business
    # by_model: in a makers' layer whose name its words say, it is in the figures; with no design words it stays out, both models named
    words = {"D": "Dco is a designer and retailer of branded apparel.", "R": "Rco runs department stores selling apparel.",
             **{f"M{i}": f"Mco {i} makes branded apparel and footwear." for i in range(3)}}
    vc = [{"layer": "Apparel brand owners", "description": "Design and sell branded apparel.",
           "companies": [{"ticker": t, "name": t, "what": words[t]} for t in words]}]
    models = {"D": "retail", "R": "retail", **{f"M{i}": "manufacturing" for i in range(3)}}
    tags = {"D": ["manufacturing"], "R": ["manufacturing"]}
    got = B.by_model(copy.deepcopy(vc), models, "Consumer retail", tags=tags, confidence={k: "medium" for k in models}, evidence_of=words.get,
                     settled={"D", "R"})
    cos = {c["ticker"]: c for v in got for c in v["companies"]}
    assert cos["D"].get("own_goods") and not cos["D"].get("model_out")
    assert cos["R"]["model_out"] == "other" and cos["R"]["out_why"] == "model"


def test_each_left_out_reason_is_one_precise_kind_and_old_records_get_theirs():
    lay = {"layer_model": "manufacturing", "layer_family": "making"}
    assert D.calc_record({"revenue": 5, "model_out": "other", "out_why": "off_industry"})["kind"] == "another business"
    r = D.calc_record({"revenue": 5, "model_out": "other", "out_why": "model", "model": "distribution", **lay})
    assert r["why"] == "other business" and r["kind"] == "different revenue model"
    assert r["label"] == "different revenue model (distribution and trading, the layer's makers of their own products)"
    assert D.calc_record({"revenue": 5, "model_out": "unknown", "out_why": "no_words"})["label"] == "insufficient evidence (not checked yet, no description of its own)"
    assert D.calc_record({"revenue": 5, "model_out": "unknown", "out_why": "no_model"})["detail"] == "its own words don't state how it earns"
    assert D.calc_record({"revenue": 5, "status": "unverified"})["kind"] == "not confirmed in the theme"
    assert D.calc_record({"revenue": None})["kind"] == "no figure stored"
    # a record kept before this release (no kind) gets its kind when read; the coverage page's sentence says it
    old = D.calc_of({"calc": {"in": False, "why": "other business"}, "model_out": "other"})
    assert old["kind"] == "different revenue model"
    assert D.comparison_said({"in": False, "why": "way of earning not shown"}, {}) == \
        "listed in its layer, left out of its figures: insufficient evidence, its evidence doesn't show clearly how it earns"
    # and never "other business" for an insufficient evidence or the reverse: the roll groups by the precise label, kinds in order
    _, line = None, deck.roll_line([("A", "")], [("B", "insufficient evidence (not checked yet, no description of its own)"),
                                                 ("C", "different revenue model (retail, the layer's makers of their own products)")])[0]
    assert line.startswith("In the layer's calculations (1 of 3): A. Left out (2): different revenue model (retail, the layer's makers of their "
                           "own products): C; insufficient evidence (not checked yet, no description of its own): B.")


def test_a_company_in_the_figures_in_part_says_which_part():
    c = {"symbol": "P", "ebitda": None, "net": 9.0}
    assert deck.part_note(c, ("ebitda", "net")) == "partial: EBITDA margin not stored"
    held = {"symbol": "Q", "ebitda": 12.0, "net": 30.0, "one_off": True, "verify": {"net": {"state": D.UNVERIFIED}}}
    assert deck.part_note(held, ("ebitda", "net")) == "partial: net margin not reconciled"
    assert deck.part_note({"symbol": "R", "ebitda": 12.0, "net": None, "held": {"net": {"state": D.INVALID}}}, ("ebitda", "net")) == "partial: net margin invalid"
    assert deck.part_note({"symbol": "S", "ebitda": 12.0, "net": 5.0, "nc": ["net"]}, ("ebitda", "net")) == "partial: net margin on another period basis"


def test_a_layer_page_names_both_models_of_a_company_left_out_for_its_revenue_model():
    m, f = chem(model={"id": "retail", "family": "resale", "known": 6, "of": 6})
    lay = m["value_chain"][0]
    lay["companies"][0].update(model="platform", model_out="other", out_why="model")
    for c in lay["companies"][1:]:
        c.update(model="retail")
    v, slides = deck_of("IN", m, f)
    page = next(s for s in slides if s.title.endswith("· " + lay["layer"]))
    rows = [str(r[0]) for b in page.blocks if b["kind"] == "table" for r in b["rows"]]
    notes = " ".join(p for b in page.blocks if b["kind"] == "text" for p in b["paras"])
    assert "Custom Chem 0 Ltd (different model)" in rows
    assert ("(different model): Custom Chem 0 Ltd: the way of earning of “Platforms and marketplaces” (commissions, listing fees or advertising "
            "on platforms they run), not the layer's, that of “Retail”") in notes
    assert "(other business)" not in texts(slides) and "(left out)" not in texts(slides)


# ---------- 2. P1: the capital-intensity proxy, its inputs; the business model apart ----------
def test_the_capital_proxy_needs_both_parts_of_one_year_and_a_positive_revenue():
    assert D.capital_inputs(1000, 2.0, 500, None, 1000) == {"capital_rev": 1.0, "capital_missing": []}
    assert D.capital_inputs(1000, 2.0, None, None, 1000) == {"capital_rev": None, "capital_missing": ["debt"]}      # before: debt taken as 0
    assert D.capital_inputs(None, None, None, None, 1000)["capital_missing"] == ["debt", "book equity"]
    assert D.capital_inputs(1000, 2.0, 500, None, 0, year="Mar 2026")["capital_missing"] == ["a positive revenue for Mar 2026"]
    # the debt of the revenue's own year, not a later balance sheet's
    assert D.capital_inputs(1000, 2.0, 900, None, 1000, year_debt=500)["capital_rev"] == 1.0


def test_the_comparison_basis_labels_the_proxy_and_says_which_input_is_missing():
    m, f = chem()
    f["CS0"].pop("debt")
    f["CS0"]["years"][-1].pop("debt")
    v, slides = deck_of("IN", m, f)
    b = v["chain"]["basis"]
    it = next(r for r in b["rules"] if r["rule"] == "capital intensity")
    assert it["proxy"] and D.CAPITAL_PROXY in it["text"] and "never comparability on its own" in it["text"]
    assert ["Custom synthesis manufacturers", "Custom Chem 0 Ltd", ["debt", "book equity"]] in it["missing"]      # its equity read from its debt too
    _, rules_, _ = basis_pages(slides)[0]
    line = next(x for x in rules_ if x.startswith("Capital intensity, a proxy for capital needs"))
    assert "passing it alone never makes layers comparable" in line and "inputs missing: Custom Chem 0 Ltd (debt and book equity)" in line


def test_a_layer_the_map_names_for_custom_synthesis_is_shown_not_ranked_beside_makers_of_their_own_products():
    # by_model reads the business model the map's own name states, apart from how its companies earn
    words = {f"{p}{i}": "makes chemicals" for p in ("CS", "BO") for i in range(3)}
    vc = [{"layer": "Custom synthesis manufacturers", "description": "", "companies": [{"ticker": f"CS{i}", "name": f"CS{i}"} for i in range(3)]},
          {"layer": "Basic organic intermediates", "description": "", "companies": [{"ticker": f"BO{i}", "name": f"BO{i}"} for i in range(3)]}]
    got = B.by_model(vc, {s: "manufacturing" for s in words}, "Chemicals", confidence={s: "medium" for s in words}, evidence_of=words.get)
    md = {v["layer"]: v["model"] for v in got}
    assert md["Custom synthesis manufacturers"]["named"] == "contract_manufacturing" and "named" not in md["Basic organic intermediates"]
    # the deck: before, "highest Custom synthesis manufacturers" against the commodity layers; now the two commodity layers are ranked and
    # the custom synthesis layer is shown, not ranked, with the reason
    make = {"id": "manufacturing", "family": "making", "known": 6, "of": 6}
    m, f = chem(model=make)
    m["value_chain"][0]["model"] = {**make, "named": "contract_manufacturing"}
    v, slides = deck_of("IN", m, f)
    ch = v["chain"]
    assert ch["highest"] == "Chlor-alkali and soda ash producers" and ch["lowest"] == "Basic organic intermediates"
    left = {x["layer"]: x["why"] for x in ch["basis"]["left"]}
    # rv51 (R51, updated on purpose): the model is read from the layer's own name, and said so (theme_data.named_fit)
    assert left["Custom synthesis manufacturers"] == "a different business model: contract manufacturing (stated by the layer's own name)"
    rule = next(r for r in ch["basis"]["rules"] if r["rule"] == "business model")
    assert rule["passed"] and rule["text"] == "one business model: makers of their own products (how its companies earn)"
    # gl52 (R52, updated on purpose): every figure of the headline at one precision (its highest and lowest print a decimal)
    assert "Custom synthesis manufacturers (22.0%), a different business model" in ch["line"]
    # two layers alone, of two business models: described, never ranked
    m2, f2 = chem(model=make)
    m2["value_chain"] = m2["value_chain"][:2]
    m2["value_chain"][0]["model"] = {**make, "named": "contract_manufacturing"}
    ch2 = deck_of("IN", m2, f2)[0]["chain"]
    assert ch2["highest"] is None and "Their business models differ (Custom synthesis manufacturers: contract manufacturing" in ch2["line"]
    assert ch2["basis"]["why"] == "their business models differ by the map's own words"


# ---------- 3. P1: net above EBITDA, the lines still missing; a rebuilt page read ----------
def test_each_net_margin_above_ebitda_says_which_line_is_still_missing():
    assert D.missing_said({"missing": ["other_income", "pbt", "tax_pct"], "unkept": ["op", "pbt", "tax_pct"]}) == (
        "still missing: other income, profit before tax and tax rate (the stored page was built before profit before tax and tax rate were "
        "kept; read again once it is rebuilt)")
    assert D.missing_said({"missing": ["tax_pct"], "unkept": []}) == "still missing: tax rate (none stored for the year)"
    assert D.missing_said({"missing": [], "unkept": []}) == ""
    # the live R48 Swan Corp lines (revenue ₹4,371 crore, net profit ₹271 crore, EBITDA margin −4.7%, page built 8 Nov without the lines)
    r = D.company_row("IN", "SWANCORP", co("SWANCORP", "Swan Corp Ltd", 4371.0, -4.7, 271.0, roce=-1.0))
    assert "is stored to explain it; still missing: other income, profit before tax and tax rate (the stored page was built before" in r["verify"]["net"]["why"]
    # rebuilt with the lines: reconciled with them (here they cover the gap), the rule unchanged
    lines = {"op": -205.0, "other_income": 600.0, "interest": 30.0, "dep": 60.0, "pbt": 305.0, "tax_pct": 11.0}
    r2 = D.company_row("IN", "SWANCORP", co("SWANCORP", "Swan Corp Ltd", 4371.0, -4.7, 271.0, roce=-1.0, lines=lines))
    assert r2["verify"]["net"]["state"] == D.VERIFIED and "income outside operations" in r2["verify"]["net"]["why"]


@pytest.fixture
def store(monkeypatch):
    from tests.test_r19_library import Store
    s = Store()
    monkeypatch.setattr(db, "get_setting", lambda k: s.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: s.__setitem__(k, v))
    monkeypatch.setattr(db, "update_setting", s.update_setting)
    monkeypatch.setattr(db, "delete_setting", lambda k: s.pop(k, None))
    computed.reset_for_tests()
    return s


def test_a_page_rebuilt_with_the_lines_is_read_and_the_dive_worked_out_again_without_a_refresh(store, monkeypatch):
    old = {"v": 9, "years": [{"year": "Mar 2026", "sales": 100.0}]}
    new = {"v": 10, "years": [{"year": "Mar 2026", "sales": 100.0, "pbt": 12.0, "tax_pct": 25.0}]}
    pages = {"X": old, "Y": {"v": 10, "years": []}}
    monkeypatch.setattr(routes, "public_facts", lambda r, s: dict(pages[s]))
    assert TR.facts_piece("IN", "X")[0]["v"] == 9                           # kept once
    pages["X"] = new
    assert TR.facts_piece("IN", "X")[0]["v"] == 10                          # before: the piece built before the lines, until a Refresh
    pages["X"] = {**new, "v": 11}
    assert TR.facts_piece("IN", "X")[0]["v"] == 10                          # a current piece is served as kept
    # a kept dive whose checked figure waits for the lines is worked out again once its page keeps them; once only
    dive = {"checks": {"states": [{"symbol": "X", "bridge": {"unkept": ["op", "pbt", "tax_pct"]}}, {"symbol": "Y", "bridge": {"unkept": []}}]}}
    pages["X"] = old
    assert TR.pages_rebuilt("IN", dive) == []
    pages["X"] = new
    assert TR.pages_rebuilt("IN", dive) == ["X"]
    pages["X"] = {"v": 10, "years": [{"year": "Mar 2026", "sales": 100.0}]}       # rebuilt but the lines not kept: no rebuild on every read
    assert TR.pages_rebuilt("IN", dive) == []
    built = []

    def build(r, theme, fm, src):
        built.append(src.facts("X")["v"])
        return {"x": src.facts("X")["v"], "checks": {"states": [{"symbol": "X", "bridge": {"unkept": ["pbt", "tax_pct"] if src.facts("X")["v"] < 10 else []}}]}}
    monkeypatch.setattr(TR.theme_data, "build", build)
    monkeypatch.setattr(TR, "auto_post", lambda *a, **k: None)
    monkeypatch.setattr(TR.theme_changes, "record", lambda *a, **k: None)
    monkeypatch.setattr(TR.theme_changes, "flag", lambda *a, **k: None)
    store.clear()
    computed.reset_for_tests()
    pages["X"] = old
    m = {"sector": "Chemicals", "generated_at": 1, "placements": {"checked": True, "placed": 1},
         "value_chain": [{"layer": "L", "official": True, "companies": [{"ticker": "X"}]}], "sub_themes": []}
    assert TR.dive_of("IN", "Chemicals", m)["x"] == 9
    assert TR.dive_of("IN", "Chemicals", m)["x"] == 9 and len(built) == 1      # kept
    pages["X"] = new
    assert TR.dive_of("IN", "Chemicals", m)["x"] == 10 and len(built) == 2     # the page rebuilt with the lines: read, no Refresh
    assert TR.dive_of("IN", "Chemicals", m)["x"] == 10 and len(built) == 2     # then kept again


# ---------- 4. presentation: one comparison a page ----------
def test_each_comparison_is_one_page_with_its_rules_in_larger_type_and_one_table():
    m, f = chem()
    v, slides = deck_of("IN", m, f)
    pages = [s for s in slides if s.title.startswith(deck.COMPARE_TITLE)]
    recs = v["comparisons"] if "comparisons" in v else None
    claims = [s.subtitle for s in pages]
    assert len(pages) == len(set(claims)) == 2                               # before: one table of claims, rules and layers over 5 pages
    for s in pages:
        assert [b["kind"] for b in s.blocks if b["kind"] != "text"] == ["table"]
        rules = next(b for b in s.blocks if b["kind"] == "text" and b.get("size") == deck.RULES_SIZE)
        assert deck.RULES_SIZE > deck.BODY_MIN and all("(met)" in p or "(not met)" in p or p.startswith("Shown, not ranked") for p in rules["paras"])
        tab = next(b for b in s.blocks if b["kind"] == "table")
        assert tab["head"][0] == "Layer" and tab["head"][-1] == "Companies in the figure"
        assert tab["box"][1] + tab["box"][3] <= deck.BOT + 1e-6
    assert recs is None or recs
    assert next(x for x in slides[0].gate["items"] if x["id"] == "sourced")["ok"], slides[0].gate["dropped"]


def test_the_versions_moved():
    assert B.RULES == 51 and TR.PLACE_CARRY[51] == 50 and TR.PLACE_CARRY[50] == 49 and TR.PLACE_CARRY[49] == 48 and TR.PLACE_CARRY[48] == 47 and B.PICK_RULES == 45          # gl52 (R52): RULES 51, PLACE_CARRY[51] = 50, deck 62, dive text 22 (updated on purpose); rv51 (R51): RULES 50, PLACE_CARRY[50] = 49, deck 61, dive text 21 (updated on purpose); gl50 (R50): RULES 49, PLACE_CARRY[49] = 48, deck 60, dive text 20 (updated on purpose)
    assert deck.THEME_DECK_VERSION == 62 and D.DIVE_TEXT == 22          # gl52 (R52): RULES 51, PLACE_CARRY[51] = 50, deck 62, dive text 22 (updated on purpose); rv51 (R51): RULES 50, PLACE_CARRY[50] = 49, deck 61, dive text 21 (updated on purpose); gl50 (R50): RULES 49, PLACE_CARRY[49] = 48, deck 60, dive text 20 (updated on purpose)


# ---------- G3 (the rotating review of the live R48 decks): the same exclusion beyond Consumer retail ----------
def test_the_maps_own_picks_whose_words_say_their_layer_are_in_its_figures_and_arm_states_its_real_reason():
    """Fails before: Fortinet, Akamai (Cybersecurity), Route Mobile (Telecom) and ASE (Semiconductors) were listed in their layers as "other
    business". Each is the map's own pick (or, ASE, placed there with words stating the layer's way of earning), and each one's own words say
    the layer's name and no other way of earning: only the AI's read gave it another. Arm stays out: its own words state design services
    ("the design of central processing unit cores"), not software licences; that reason is said with both models. The R39 inputs of the same
    themes (tests/fixtures/themes_live/inputs_r39): no placement changes."""
    got = {}
    for key in ("cyber", "semis", "telecom", "pharma"):
        out, _ = X.replay(key)
        for v in out["value_chain"]:
            for c in v["companies"]:
                got[c["ticker"]] = (v, c)
    for s_ in ("FTNT", "AKAM", "ROUTE", "ASX"):
        v, c = got[s_]
        assert c.get("by_words") and "model_out" not in c, s_
        assert "only the AI's read gave it another" in D.comparison_said({"in": True, "why": "", "by_words": True}, {"model": v.get("model")})
    v, arm = got["ARM"]
    assert arm["model_out"] == "other" and arm["out_why"] == "model" and not arm.get("by_words")
    r = D.out_reason({**D.model_fields(v, "ARM"), "status": "core"})
    assert r["label"] == "different revenue model (project and consulting services, the layer's software products and subscriptions)"
    # placed after the map with words that state no way of earning: the answer's other read stands, with both models said
    for s_ in ("HIKAL", "BROOKS"):
        v, c = got[s_]
        assert c["model_out"] == "other" and D.out_reason({**D.model_fields(v, s_), "status": "core"})["label"] == \
            "different revenue model (makers of their own products, the layer's contract manufacturing)"
    # a retailer's own words (stores) are a way of earning of their own
    assert T.words_models("Rco runs department stores selling apparel.") == {"retail"}
