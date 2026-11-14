"""Lane d53 (Release 53): theme membership, roles and integrity, from the owner's review of the live R52 decks, our deck reviewer (rev51)
and the LIVE8A review.

1. Membership before layers: a company an earlier stored version dropped as another business can't re-enter silently (Suburban Propane in
   Consumer retail); a company's stored words stand until they are read again (the R52 cause: Chewy's and Suburban Propane's words were not
   read at all once marked for a second read); every addition is logged with why.
2. Core vs adjacent: hospital operators in Medical devices and device makers in Hospitals are adjacent participants, shown, in no total,
   median or ranking of the theme.
3. An early-stage layer's large commercial companies out of its figures (Amgen in "Gene-editing developers and big pharma sellers"); companies
   spending ahead of their revenue apart from the margin medians.
4. The map's coverage said honestly: the real count without words, a partial map said in the headline.
6. One company under two symbols merged; layer names a line says are the deck's; the figure-sources head counts arithmetic-only figures apart;
   moves between layers logged; layers lost flagged.
deck_check: a rule for each new failure class.

The live inputs are tests/fixtures/themes_live/inputs_r52 (the owner's read-only placement inputs of 14 Nov 2026, Release 52) and the R49
inputs for the earlier version's exclusions. Every figure is synthetic."""
import importlib.util
import json
import os
import pathlib
from datetime import datetime, timezone

import pytest

from app import deck
from app.intel import theme_base as B, theme_changes as TC, theme_data as D, theme_routes as TR
from tests import test_exact_replay as X
from tests.test_r18_deck import deck_of
from tests.test_r48_reconcile import co

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"
PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
spec = importlib.util.spec_from_file_location("deck_check_d53", PATH)
DC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DC)


def inputs(rel: str) -> dict:
    d = json.loads((LIVE / rel).read_text())
    return d.get("data", d)


def replay(d: dict, evidence: dict | None = None, **kw) -> dict:
    """A live placement replayed (place_rest) from its inputs; a company the split moved is fed in the map layer it is served in."""
    stale = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit")
    origin = {}
    for v in d["value_chain"]:
        v["companies"] = [{k: x for k, x in c.items() if k not in stale} for c in v["companies"]]
        for c in v["companies"]:
            if c.get("moved") and not c.get("placed"):
                origin[c["ticker"]] = X._HALF.sub("", v["layer"]) if X._is_map_layer(v) else "?" + c["ticker"]
    ev = evidence if evidence is not None else d["evidence"]
    m = X.pre_map(d, origin, {})
    out, _ = B.place_rest(m, d["theme"], lambda s: ev.get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d.get("previous") or {}, **kw)
    return out


def where(out: dict) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else X._HALF.sub("", v["layer"]), c) for v in out["value_chain"] for c in v["companies"]}


def synthetic_deck(d: dict, out: dict):
    """The replayed map with synthetic figures (each layer's index sets its margin), built into a dive and a deck (gl52's mkdeck)."""
    f = {}
    for li, v in enumerate(out["value_chain"]):
        base = 6.0 + 3.3 * (li % 7)
        for i, c in enumerate(v["companies"]):
            sales = 1000.0 + 37 * i
            f[c["ticker"]] = co(c["ticker"], c.get("name") or c["ticker"], sales, base + (i % 3) - 1, sales * (base - 4) / 100)
    out = {**out, "sector": d["theme"], "sub_themes": out.get("sub_themes") or []}
    return deck_of(d["region"], out, f, theme=d["theme"], about=d["evidence"].get)


EARLIER_OFF = ("CDW", "FCFS", "EZPW", "SPH", "TMS", "LIVE")


# ---------- 1. membership before layers ----------
def test_a_company_an_earlier_version_dropped_as_another_business_stays_out_on_the_live_r52_retail_inputs():
    """Fails before: the live R52 placement read no words for Suburban Propane, CDW, FirstCash or EZCORP, so nothing kept them out, and the
    deck listed them among the companies "added"; the R49 version had dropped each as another business."""
    earlier = {o["ticker"]: [o["name"], o["industry"]] for o in inputs("inputs_r49/retail.json")["placements"]["off_industry"]}
    assert set(EARLIER_OFF) <= set(earlier)
    plain = where(replay(inputs("inputs_r52/retail.json")))
    assert all(s in plain for s in EARLIER_OFF)                      # the R52 regression, as served
    out = replay(inputs("inputs_r52/retail.json"), off_before=earlier)
    now = where(out)
    assert not any(s in now for s in EARLIER_OFF)
    off = {o["ticker"]: o for o in out["placements"]["off_industry"]}
    assert all(off[s]["before"] for s in EARLIER_OFF)
    assert off["SPH"]["why"] == ("filed under Miscellaneous retail; an earlier version of the theme found its own words describe another business, "
                                 "and no words of its own are read since")
    assert "Found to be in another business by an earlier version of the theme" in deck.off_industry_line({"placements": out["placements"]})
    # one whose own words are read now is judged on them: words of a store retailer bring it back, named with why
    ev = {**inputs("inputs_r52/retail.json")["evidence"], "TMS": "Tile Shop operates specialty retail stores selling tiles to homeowners."}
    back = replay(inputs("inputs_r52/retail.json"), evidence=ev, off_before=earlier)
    assert "TMS" in where(back) and [x["ticker"] for x in back["placements"]["back"]] == ["TMS"]


def test_chewy_is_in_the_online_layer_when_its_stored_words_are_read_on_the_live_r52_inputs():
    """The R52 cause: its stored words (an encyclopedia's opening, marked for a second read by gl52) were read as none, so it went to "Other"
    as not checked yet. With the words it has stored, the same inputs place it in the online retailers' layer."""
    d = inputs("inputs_r52/retail.json")
    assert where(replay(inputs("inputs_r52/retail.json")))["CHWY"][0] == "Other"
    ev = {**d["evidence"], "CHWY": inputs("inputs_r49/retail.json")["evidence"]["CHWY"]}
    got = where(replay(d, evidence=ev))["CHWY"]
    assert got[0] in ("Online stock-holding retailers", "Online retailers and marketplaces") and not got[1].get("model_out")


@pytest.fixture
def store(monkeypatch):
    kept: dict = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "")
    TR.EVIDENCE_CACHE.clear()
    yield kept
    TR.EVIDENCE_CACHE.clear()


CHEWY = ("Chewy, Inc. is an American online retailer of pet food and other pet-related products based in Plantation, Florida. Chewy went public "
         "in 2019 with the ticker symbol CHWY on the New York Stock Exchange.")


def test_stored_words_due_for_a_second_read_are_read_until_it_is_made(store):
    """Fails before: a stored US description with no sentence of its own (thin_about, gl52's ABOUT_V 5) gave the placement nothing at all
    while its second read waited."""
    now = datetime.now(timezone.utc).isoformat()
    store["theme:evidence:US:CHWY"] = json.dumps({"at": now, "about": CHEWY, "v": TR.ABOUT_V - 1})
    assert TR.thin_about(json.loads(store["theme:evidence:US:CHWY"]), "US")
    assert TR._about_reader("US", {"CHWY": "Chewy, Inc."}, 0)("CHWY") == CHEWY
    # words not about a company at all (the R35 case: an encyclopedia's myth) are never used meanwhile
    store["theme:evidence:US:ICHR"] = json.dumps({"at": now, "about": "In Greek mythology, ichor is the ethereal fluid of the gods.", "v": 1})
    TR.EVIDENCE_CACHE.clear()
    assert TR._about_reader("US", {"ICHR": "Ichor Holdings"}, 0)("ICHR") is None


def _dive(layers, off=()):
    return {"layers": [{"layer": n, "companies": [{"symbol": s, "name": s.title(), "theme": {"why": f"filed under X, an official industry of the theme"}}
                                                  for s in cos]} for n, cos in layers],
            "placements": {"off_industry": [{"ticker": s, "name": s.title(), "industry": "Retail-Miscellaneous Retail"} for s in off]}}


def test_earlier_exclusions_are_kept_from_one_version_to_the_next_and_every_addition_says_why():
    """Fails before: the snapshot kept only the latest read's exclusions, and an added row carried no reason."""
    v1 = TC.snapshot(_dive([("A", ["AAA", "BBB"])], off=["SPH"]), ["AAA", "BBB", "SPH"])
    v2 = TC.snapshot(_dive([("A", ["AAA", "BBB", "CCC"])]), ["AAA", "BBB", "CCC", "SPH"])
    got = TC.apply(TC.apply({}, v1), v2)
    assert got["snap"]["off_ever"] == {"SPH": ["Sph", "Retail-Miscellaneous Retail"]}
    assert TC.off_memory(got) == {"SPH": ["Sph", "Retail-Miscellaneous Retail"]}
    added = got["log"][-1]["added"]
    assert added == [{"symbol": "CCC", "name": "Ccc", "layer": "A", "why": "filed under X, an official industry of the theme"}]
    # a logged removal for another business is remembered even when the snapshot lost it
    assert TC.off_memory({"log": [{"removed": [{"symbol": "FGPR", "name": "Ferrellgas", "why": "another business (filed under Retail-Miscellaneous Retail)"}]}]}) \
        == {"FGPR": ["Ferrellgas", "Retail-Miscellaneous Retail"]}
    # re-entry on its own words read now: said in the log, and no longer held
    v3 = TC.snapshot({**_dive([("A", ["AAA", "BBB", "CCC", "SPH"])]), "placements": {"back": [{"ticker": "SPH"}]}}, ["AAA", "BBB", "CCC", "SPH"])
    got3 = TC.apply(got, v3)
    assert "its own words read now show the theme's work" in got3["log"][-1]["added"][0]["why"]
    assert TC.off_memory(got3) == {}
    # the deck's cohort row says each addition's reason
    row = deck.cohort_row({"changes": {"entries": [got["log"][-1]]}, "coverage": {}})
    assert "added 1: Ccc (filed under X, an official industry of the theme)" in row[2]


# ---------- 2. core vs adjacent ----------
def test_device_makers_are_adjacent_in_the_hospitals_theme_on_the_live_r52_inputs():
    """Fails before: the Hospitals deck counted its device makers (Poly Medicure) in its totals and ranked their layer."""
    d = inputs("inputs_r52/hosp.json")
    v, slides = synthetic_deck(d, replay(inputs("inputs_r52/hosp.json")))
    adj = {x["name"]: x for x in v["adjacent"]}
    assert adj["Poly Medicure Ltd"]["kind"] == "medical device and supplies makers" and adj["Poly Medicure Ltd"]["where"] == "industry"
    lay = {b["layer"]: b for b in v["layers"]}
    assert lay["Medical device and consumables makers"]["adjacent"]["theme"] == "hospitals and care providers"
    assert "Contract research and life-science services" in {b["layer"] for b in v["layers"] if b.get("adjacent")}
    assert "Large multi-specialty hospital networks" not in {b["layer"] for b in v["layers"] if b.get("adjacent")}
    ch = v["chain"]
    assert "Medical device and consumables makers" not in ch["compared"] and ch["highest"] and ch["highest"] not in lay or not lay[ch["highest"]].get("adjacent")
    text = "\n".join(str(x) for s in slides for x in s.texts()) if hasattr(slides[0], "texts") else ""
    rows = deck.confidence_rows(v, {"total": 100, "n": 90, "share": 90, "of_what": "x"}, D.date(2026, 11, 14))
    core = next(r for r in rows if r[0] == "Core and adjacent")
    assert core[1].startswith("The theme's core members are hospitals and care providers;") and "Poly Medicure" in core[1]
    del text


def test_hospital_operators_are_adjacent_in_the_medical_devices_theme_and_out_of_its_size():
    d = inputs("inputs_r52/meddev.json")
    v, _ = synthetic_deck(d, replay(inputs("inputs_r52/meddev.json")))
    adj = {x["name"]: x for x in v["adjacent"]}
    assert adj["HCA Healthcare, Inc."]["kind"] == "hospitals and care providers"
    lay = {b["layer"]: b for b in v["layers"]}
    assert lay["Hospital and care facility operators"].get("adjacent") and not lay["Implantable devices"].get("adjacent")
    # a care operator the placement put in a device layer is listed there, out of its figures, with why
    jr = next(c for b in v["layers"] for c in b["companies"] if c["name"] == "Jrsis Health Care Corp")
    assert not jr["calc"]["in"] and jr["calc"]["label"] == "adjacent participant, another kind of business than the theme's"
    # the theme's size and medians are of its core members only
    size_syms = {c["symbol"] for c in v["sections"]["size"].get("largest") or []} if isinstance(v["sections"]["size"].get("largest"), list) else set()
    assert "HCA" not in size_syms
    assert D.theme_kind("Medical devices") == "medical device and supplies makers" and D.theme_kind("Semiconductors") == ""


def test_the_kinds_are_read_from_the_official_industry_then_the_principal_business():
    assert D.company_kind({"industry": "Services-General Medical & Surgical Hospitals, Nec"})[0] == "hospitals and care providers"
    assert D.company_kind({"industry": "Medical Equipment & Supplies"})[0] == "medical device and supplies makers"
    assert D.company_kind({"industry": "", "what": "We make catheters and syringes for hospitals."})[0] == "medical device and supplies makers"
    assert D.company_kind({"industry": "In Vitro & In Vivo Diagnostic Substances"})[0] == ""          # a gene-editing developer's filing: no kind
    assert D.adjacent_of({"industry": "Surgical & Medical Instruments & Apparatus"}, "medical device and supplies makers") is None


# ---------- 3. early-stage layers and companies spending ahead of revenue ----------
def _row(sym, revenue, ebitda, net=None):
    return {"symbol": sym, "name": sym.title(), "revenue": revenue, "ebitda": ebitda, "net": net}


def test_a_large_commercial_company_is_out_of_an_early_stage_layers_figures_as_on_the_live_r52_biotech_deck():
    """Fails before: Merck and Novartis raised the layer's median company's revenue, so Amgen ($36.8 bn, EBITDA 38.8%) stayed in the figures of
    "Gene-editing developers and big pharma sellers" (was "Clinical-stage platform developers")."""
    layer = {"layer": "Gene-editing developers and big pharma sellers", "was": "Clinical-stage platform developers",
             "description": "These companies develop gene editors, small molecules and antibodies."}
    rows = [_row("MRK", 64000.0, 39.2), _row("NVS", 50000.0, 38.0), _row("AMGN", 36800.0, 38.8), _row("ONC", 5340.0, 11.0),
            _row("CRSP", 40.0, -609.9), _row("NTLA", 55.0, -800.0), _row("BEAM", 60.0, -700.0), _row("SRRK", 20.0, -900.0)]
    out = D.stage_check(layer, rows, {"SRRK": "We are a clinical-stage biopharmaceutical company."})
    assert set(out) == {"MRK", "NVS", "AMGN", "ONC"}
    assert "not of the clinical-stage work the layer's name or description states" in rows[2]["stage_out"]
    # a gene-editing name alone states an early-stage activity
    assert D.stage_check({"layer": "Gene-editing developers"}, [_row("A", 30000.0, 30.0), _row("B", 50.0, -300.0), _row("C", 40.0, -200.0)]) == ["A"]


def test_a_company_spending_ahead_of_its_revenue_is_apart_from_the_margin_medians():
    """Fails before: −609.9% and −18,378.7% EBITDA margins, verified as a loss at both levels, were in the layer's median (−258.6%) and range."""
    dev = D.company_row("IN", "DEV", co("DEV", "Dev Labs Ltd", 50.0, -600.0, -400.0))
    biz = D.company_row("IN", "BIZ", co("BIZ", "Biz Pharma Ltd", 5000.0, 20.0, 600.0))
    assert dev["developer"] and dev["verify"]["ebitda"]["state"] == D.VERIFIED and D.in_median(dev, "ebitda") is None
    assert D.in_median(dev, "net") is None and D.in_median(biz, "ebitda") == 20.0
    b = D.layer_block("L", [{**dev, "status": "core"}, {**biz, "status": "core"}], set())
    assert b["stats"]["ebitda"]["median"] == 20.0 and b["stats"]["ebitda"]["n"] == 1 and b["developers"] == ["Dev Labs Ltd"]
    assert deck.part_note({**dev}, ("ebitda", "net")) == "partial: EBITDA margin apart (costs over twice revenue), net margin apart (costs over twice revenue)"


# ---------- 4. coverage honesty ----------
def test_the_membership_row_says_the_real_count_without_words_and_a_partial_map_says_so():
    """Fails before: "Every company with figures has words of its own ... Nothing held back." beside companies with no words, and a map of
    100 checked of 821 read as whole."""
    v = {"layers": [{"layer": "L", "companies": [{"symbol": "A", "name": "Alpha Inc", "status": "core", "revenue": 10.0, "what": "We make chips."},
                                                 {"symbol": "B", "name": "Beta Inc", "status": "core", "revenue": 12.0, "what": None}]}],
         "membership": {"placed": 100, "confirmed": 100, "not_confirmed": 0}, "checks": {}}
    rows = {r[0]: r for r in deck.confidence_rows(v, {"total": 821}, D.date(2026, 11, 14))}
    assert rows["Membership"][1] == "1 company with figures have no description in their own words yet: Beta." or rows["Membership"][1].startswith("1 company with figures")
    assert rows["Membership"][2] != "Nothing held back."
    assert rows["Partial map"][1].startswith("A partial map: 100 of the theme's 821 companies were checked (12%); 721 are not checked yet")
    assert deck.partial_map({**v, "membership": {"placed": 700}}, {"total": 821}) == ""


# ---------- 6. integrity ----------
ICICI_A = co("ICICILIFE", "ICICI Life Insurance Ltd", 63357.0, 5.0, 1584.0)
ICICI_B = co("ICICIPRULI", "ICICI Prudential Life Insurance Company Ltd", 63357.0, 5.0, 1584.0)


def test_one_company_under_two_symbols_is_merged_before_any_median_or_total():
    """Fails before: one_row_each needed the same name, so both ICICI rows were in the Life layer's median, revenue and market value."""
    a, b = D.company_row("IN", "ICICILIFE", ICICI_A), D.company_row("IN", "ICICIPRULI", ICICI_B)
    a["cap"], b["cap"] = 66046.0, 62548.0
    assert D.same_company([a, b]) == {"ICICIPRULI": "ICICILIFE"}
    # two companies of one figure whose names differ by a word of their own stay two (synthetic themes)
    m1, m2 = D.company_row("IN", "M1", co("M1", "Maker 1 Ltd", 100.0, 10.0, 5.0)), D.company_row("IN", "M2", co("M2", "Maker 2 Ltd", 100.0, 10.0, 5.0))
    assert D.same_company([m1, m2]) == {}
    m = {"sector": "Insurance", "value_chain": [{"layer": "Life insurance underwriting", "description": "",
                                                 "companies": [{"ticker": "ICICILIFE", "name": "ICICI Life Insurance Ltd", "what": "a life insurer", "verified": True},
                                                               {"ticker": "ICICIPRULI", "name": "ICICI Prudential Life Insurance Company Ltd", "what": "a life insurer", "verified": True}]}],
         "sub_themes": [], "placements": {"checked": True}}
    v, _ = deck_of("IN", m, {"ICICILIFE": ICICI_A, "ICICIPRULI": ICICI_B})
    assert [c["symbol"] for c in v["layers"][0]["companies"]] in (["ICICILIFE"], ["ICICIPRULI"])
    assert len(v["duplicates"]) == 1
    row = next(r for r in deck.confidence_rows(v, {"total": 2}, D.date(2026, 11, 14)) if r[0] == "Same company twice")
    assert "listed under two symbols with the same latest year, revenue and net profit" in row[1]


def test_a_line_names_layers_as_the_dive_shows_them():
    """Fails before: the live R52 Biotech deck said its companies "earn the same way as those of “Pipeline-stage and royalty-funded drug
    developers”", a name the split had replaced."""
    line = "In common: they make. Its companies earn the same way as those of “Old name”, “Gone”, “B”; the map keeps them as separate layers."
    blocks = [{"layer": "A", "model": {"same_as": ["Old name", "Gone", "B"], "line": line}}, {"layer": "B", "model": {}}, {"layer": "C", "model": {}}]
    D.same_names(blocks, [{"layer": "C", "was": "Clinical", "aka": ["Clinical", "Old name"]}])
    assert blocks[0]["model"]["line"] == "In common: they make. Its companies earn the same way as those of “C”, “B”; the map keeps them as separate layers."
    assert B.renamed_after_split([{"layer": "X"}], {"X"}, {"X": {"name": "Y"}})[0]["aka"] == ["X"]


def test_the_figure_sources_head_counts_arithmetic_only_figures_apart_from_the_verified():
    recs = [{"state": "verified_extreme", "checked": "arithmetic", "source": {"document": "annual results, consolidated"}},
            {"state": "verified_extreme", "checked": "lines", "source": {"document": "annual results, consolidated"}}]
    assert [deck.only_arithmetic(x) for x in recs] == [True, False]
    slides = []
    deck._figure_sources(slides, {"region": "IN", "checks": {"states": [{**x, "symbol": f"S{i}", "name": f"Co {i}", "key": "net", "value": 22.7,
                                                                         "checks": [], "why": "", "lines": []} for i, x in enumerate(recs)]}}, "X")
    assert slides and slides[0].subtitle.startswith("2 checked figures, 1 verified, 1 arithmetic reproduced only:")


def test_a_layer_the_previous_live_read_had_lost_with_no_new_layer_taking_its_companies_is_flagged():
    was = TC.snapshot(_dive([("Electrical cables", ["C1", "C2", "C3", "C4"]), ("Generators", ["G1", "G2", "G3"])]), [])
    # its companies to "Other" and to the halves of a split by market value: lost
    now = _dive([("Generators", ["G1", "G2", "G3"]), ("Other utility companies", ["C1", "C2"]), ("Makers (larger)", ["C3"]), ("Makers (smaller)", ["C4"])])
    assert TC.lost_layers(was, now) == [{"layer": "Electrical cables", "n": 4}]
    # renamed, or taken by a business layer: not lost
    assert TC.lost_layers(was, _dive([("Generators", ["G1", "G2", "G3"]), ("Cable and wire makers", ["C1", "C2", "C3", "C4"])])) == []
    ctl = TC.coverage_control({"informative": 7, "placed": 7}, was, now)
    assert TC.control_line({"informative": 7, "placed": 7, "control": ctl}).endswith("“Electrical cables” (4 companies).")


# ---------- deck_check ----------
def test_deck_check_finds_each_new_failure_class():
    bad = ("BIOTECH · THE VALUE CHAIN\nLayer 1 · Research tools\nIts companies earn the same way as those of “Pipeline-stage developers”; the map keeps them as separate layers.\n"
           "Range −27994.5% to 62.2%\n\f"
           "BIOTECH · FINDINGS\nData confidence\n821 companies; 100 checked (the map's own picks, then the largest by market value): 100 confirmed by their own description, 0 not; 721 not checked yet.\n"
           "Membership Every company with figures has words of its own, or a checked quote, that show the theme's work. Nothing held back.\n"
           "Rambus No description in its own words yet\n"
           "Since the previous version 6 On 14 Nov 2026, against the version stored before it: added 2: CDW Corp, Suburban Propane Partners LP; removed 1: X (gone).\n\f"
           "Figure sources\n15 checked figures, 15 verified: where each comes from\nHDFC Bank 22.7%, arithmetic reproduced\n\f"
           "Every company's figures (1 of 1)\n Company                      Layer       Market value   Revenue      Growth    EBITDA    Net\n"
           " ICICI Life Insurance Ltd     Life        ₹66,047 cr     ₹63,357 cr   −10.5%    –         2.5%\n"
           " ICICI Prudential Life        Life        ₹62,548 cr     ₹63,357 cr   −10.5%    –         2.5%\n\f"
           "The value chain\nAmong the 3 layers, median EBITDA margin is highest in Hospital operators (30.0%) and lowest in Implants (10.0%). "
           "Shown, not ranked: Hospital operators (30.0%), adjacent participants, another kind of business than the theme's.\n")
    k = {x for x, n in DC.check_text(bad)["counts"].items() if n}
    assert {"stale layer", "same company", "words claim", "partial unsaid", "outlier range", "added unexplained", "verified count",
            "adjacent ranked"} <= k
    good = ("BIOTECH · THE VALUE CHAIN\nLayer 1 · Research tools\nLayer 2 · Drug developers\nIts companies earn the same way as those of “Drug developers”; the map keeps them as separate layers.\n"
            "Range −27.5% to 62.2%\n\f"
            "Data confidence\n821 companies; 100 checked (the map's own picks): 100 confirmed by their own description, 0 not; 721 not checked yet.\n"
            "A partial map: 100 of the theme's 821 companies were checked (12%).\n"
            "Since the previous version 2 On 14 Nov 2026: added 2: CDW Corp, Big Lots (filed under Retail stores, an official industry of the theme).\n\f"
            "Figure sources\n15 checked figures, 14 verified, 1 arithmetic reproduced only: where each comes from\n")
    k2 = {x for x, n in DC.check_text(good)["counts"].items() if n}
    assert not k2 & {"stale layer", "same company", "words claim", "partial unsaid", "outlier range", "added unexplained", "verified count", "adjacent ranked"}


def test_deck_check_flags_the_live_r52_failures_from_their_text():
    """The rules read on the live R52 decks' own words (pdftotext of scratchpad/lanes11/r52-decks), as they printed them."""
    insurance = ("Every company's figures (1 of 2)\n Company                                   Layer    Market value   Revenue       Growth   EBITDA   Net\n"
                 " ICICI Life Insurance Ltd     Life insurance underwriting    ₹66,047 cr    ₹63,357 cr    −10.5%    –    2.5%\n"
                 " ICICI Prudential Life Insurance    Life insurance underwriting    ₹62,548 cr    ₹63,357 cr    −10.5%    –    2.5%\n")
    assert DC.check_text(insurance)["counts"]["same company"] == 1
