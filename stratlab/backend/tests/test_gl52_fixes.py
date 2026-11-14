"""Lane gl52 (Release 52), the global fixes from the rotating review of Release 51 (rot51, ten themes, avg 7.6).

1. Evidence gaps: (a) a profile source that says it has nothing for a company is a final answer: the BSE code, the encyclopedia and the
   company's own filings are read next, and the "none" is kept, never retried every pass; (b) a US company whose stored words are only an
   encyclopedia's opening gets its annual report's opening too; (c) "on its industry" applies per company when its words state no way of
   earning and its industry is the one most of the layer's companies share (the layer's own other half is no other layer) or the layer's own
   name names; reasons say what happened ("no description found in any source"), never "read only weakly" for a company never read.
2. AI placements and map picks are checked against what their layer is: one whose words and industry are of another layer is left out of
   the figures ("unfit"), never moved; words any company uses and a description's customers or contrasts are no fit.
3. A low-confidence model is never printed; a medical laboratory's industry states its way of earning; a layer line names a way of earning
   only for 3 or more companies; acronyms keep their case.
4. A payments / transaction-processing model.
5. A conglomerate's theme segment, or "(whole company)", in the theme's size.
6. EPC contractors in a layer whose name says EPC; stock pay more than 2 times apart not ranked; one precision in a headline; halves of a
   split layer ranked as one; the cohort row when no company changed.
7. The walk back for an earlier answer of the same map reads every carried version (the live IT services extra layers).

The live inputs are tests/fixtures/themes_live/inputs_r51 (the owner's read-only placement inputs of 14 Nov 2026, Release 51). Every figure
is synthetic."""
import copy
import json
import pathlib
import types
from datetime import datetime, timezone

import pytest

from app import computed, deck
from app.intel import theme_base as B, theme_check as C, theme_data as D, theme_routes as TR
from app.intel.net import SourceError
from tests import test_exact_replay as X

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"


def replay51(key: str) -> dict:
    """The live Release 51 placement replayed (place_rest) from its inputs; a company the split moved is fed in the map layer it is served in."""
    d = json.loads((LIVE / "inputs_r51" / f"{key}.json").read_text())
    stale = ("out_why", "on_industry", "refit", "own_goods", "by_words", "unfit")
    origin = {}
    for v in d["value_chain"]:
        v["companies"] = [{k: x for k, x in c.items() if k not in stale} for c in v["companies"]]
        for c in v["companies"]:
            if c.get("moved") and not c.get("placed"):
                origin[c["ticker"]] = X._HALF.sub("", v["layer"]) if X._is_map_layer(v) else "?" + c["ticker"]
    m = X.pre_map(d, origin, {})
    out, _ = B.place_rest(m, d["theme"], lambda s: d["evidence"].get(s), ask=None, kept=d["kept"], facts_of=lambda s: d["facts"].get(s) or {},
                          carried=d["kept_version"] != B.RULES, previous=d.get("previous") or {})
    return out


def where(out: dict) -> dict:
    """{symbol: (layer without a half's mark, the company's row)}."""
    return {c["ticker"]: ("Other" if v.get("official") else X._HALF.sub("", v["layer"]), c) for v in out["value_chain"] for c in v["companies"]}


# ---------- 1a. a source with nothing for a company is a final answer ----------
@pytest.fixture
def store(monkeypatch):
    kept: dict = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "")
    monkeypatch.setattr(TR, "filing_reads", TR.Window())
    TR.EVIDENCE_CACHE.clear()
    yield kept
    TR.EVIDENCE_CACHE.clear()


def _hub(monkeypatch, pages=None, wiki=None, busy=()):
    asked = {"profile": [], "wiki": []}

    def company(sym):
        asked["profile"].append(sym)
        if sym in busy:
            raise SourceError("Screener.in", "Screener.in is busy (our rate limit). Try again in a minute.", busy=True)
        if sym not in (pages or {}):
            raise SourceError("Screener.in", "Screener.in has nothing for that.")
        return pages[sym]
    hub = types.SimpleNamespace(screener=types.SimpleNamespace(company=company),
                                wiki=types.SimpleNamespace(company=lambda name: asked["wiki"].append(name) or (wiki or {}).get(name)))
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None))
    return asked


CIAN = ("CIAN Agro Industries & Infrastructure Limited is an Indian company that manufactures and sells edible oils, soya products and "
        "agricultural commodities, and runs warehousing for farm produce in Maharashtra.")


def test_a_profile_source_with_nothing_for_a_company_falls_through_to_the_encyclopedia_and_is_not_retried(store, monkeypatch):
    """Fails before: Screener's "has nothing for that" was raised out of the reader, so the company stayed pending on every pass."""
    asked = _hub(monkeypatch, wiki={"CIAN Agro Industries & Infrastructure": {"title": "CIAN Agro Industries & Infrastructure", "extract": CIAN}})
    monkeypatch.setattr(TR, "_page_code", lambda sym: None)
    got, pending = TR.evidence_reader("IN", {"CIANAGRO": "CIAN Agro Industries & Infrastructure Ltd"})(["CIANAGRO"])
    assert not pending and got["CIANAGRO"]["about"].startswith("CIAN Agro Industries")
    rec = json.loads(store["theme:evidence:IN:CIANAGRO"])
    assert rec["no_page"] and rec["about"]
    TR.EVIDENCE_CACHE.clear()                                    # the next pass (even after a restart): nothing is asked again
    TR.evidence_reader("IN", {})(["CIANAGRO"])
    assert asked["profile"] == ["CIANAGRO"]


def test_a_company_with_nothing_anywhere_is_kept_as_none_found_and_a_busy_source_still_waits(store, monkeypatch):
    _hub(monkeypatch, busy={"BUSY"})
    monkeypatch.setattr(TR, "_page_code", lambda sym: None)
    got, pending = TR.evidence_reader("IN", {})(["NONE", "BUSY"])
    assert "NONE" not in got and pending == {"BUSY"}
    rec = json.loads(store["theme:evidence:IN:NONE"])
    assert rec["about"] == "" and rec["no_page"]
    assert TR._facts_reader("IN")("NONE")["searched"] is True                  # the placement says "none found", never "not checked yet"
    assert "searched" not in TR._facts_reader("IN")("BUSY")


def test_a_bse_only_company_is_read_under_its_code():
    pages = {"523696": {"about": "Fortis Malar Hospitals runs a multi-speciality hospital in Chennai.", "industry_path": ["Healthcare", "Hospital"]}}

    def company(sym):
        if sym not in pages:
            raise SourceError("Screener.in", "Screener.in has nothing for that.")
        return pages[sym]
    scr = types.SimpleNamespace(company=company)
    assert TR.india_profile(scr, "FORTISMLR", code_of=lambda s: "523696")["about"].startswith("Fortis Malar")
    assert TR.india_profile(scr, "GONE", code_of=lambda s: None) is None


def test_gather_evidence_never_holds_a_company_a_source_has_nothing_for():
    """Fails before: any exception was "late", so the company was pending for good."""
    def read(sym):
        if sym == "BUSY":
            raise SourceError("X", "busy", busy=True)
        raise SourceError("X", "X has nothing for that.")
    got, pending = C.gather_evidence(["NONE", "BUSY"], read)
    assert got == {} and pending == {"BUSY"}


# ---------- 1b. a US company with only an encyclopedia's opening ----------
VISA = ("Visa Inc. is an American multinational payment card services corporation headquartered in San Francisco, California, United States. "
        "Its shares are listed on the New York Stock Exchange, and it has been a component of the Dow Jones Industrial Average since 2013.")
VISA_10K = "We are a global payments technology company that facilitates digital payments among consumers, merchants, financial institutions and governments."


def test_a_us_company_whose_words_are_only_an_encyclopedias_opening_gets_its_annual_report_too(store, monkeypatch):
    """Fails before: 40 words that "say work" kept the article alone, so the deck said "No description in its own words yet"."""
    _hub(monkeypatch, wiki={"Visa": {"title": "Visa Inc.", "extract": VISA}})
    reads = []
    monkeypatch.setattr(TR, "_business_read", lambda sym: reads.append(sym) or VISA_10K)
    got, _ = TR.evidence_reader("US", {"V": "Visa Inc."})(["V"])
    assert reads == ["V"] and got["V"]["about"].endswith(VISA_10K)
    assert B.own_words(B.own_line(got["V"]["about"], "Visa Inc."), "Visa Inc.").startswith("We are a global payments technology company")
    # a stored description in the old format with no sentence of its own is read once more
    now = datetime.now(timezone.utc).isoformat()
    assert TR.thin_about({"at": now, "about": VISA, "v": 4}, "US") and not TR.thin_about({"at": now, "about": VISA, "v": TR.ABOUT_V}, "US")
    out = B.described({"value_chain": [{"layer": "Payments", "official": True, "companies": [{"ticker": "V", "name": "Visa Inc."}]}]},
                      lambda s: got["V"]["about"])
    assert out["value_chain"][0]["companies"][0]["what"].startswith("We are a global payments technology company")


# ---------- 1c. on its industry, per company; reasons that say what happened ----------
def test_nestle_india_is_in_the_packaged_foods_figures_on_its_industry_on_the_live_fmcg_inputs():
    """Fails before: its words ("operates in the Food segment") state no way of earning, and the layer's own other half, also mostly
    packaged foods, counted as another layer of that industry, so it was left out ("its words don't state how it earns")."""
    at = where(replay51("fmcg"))
    lay, c = at["NESTLEIND"]
    assert lay == "Branded packaged foods manufacturing" and c.get("on_industry") and not c.get("model_out")
    # an edible oil refiner in packaged foods is still out: its industry is not the layer's
    assert at["AWL"][1].get("model_out")


def test_a_company_with_no_words_is_never_said_to_be_read_weakly_and_one_looked_for_says_none_found():
    words = {f"M{i}": f"Mco {i} runs package tours and holidays for travellers." for i in range(3)}
    vc = [{"layer": "Tour operators", "description": "Package tours.", "companies": [{"ticker": t, "name": t, "industry": "Tour, Travel Related Services"}
                                                                                    for t in [*words, "NW", "OTHER"]]}]
    models = {**{t: "consumer_services" for t in words}, "NW": "consumer_services", "OTHER": "software"}
    conf = {**{t: "high" for t in words}, "NW": "low", "OTHER": "low"}
    got = B.by_model(copy.deepcopy(vc), models, "Airlines and travel", confidence=conf, evidence_of=lambda s: words.get(s, ""))
    cos = {c["ticker"]: c for v in got for c in v["companies"]}
    # no words of its own, the answer's read of it "low": in on its industry; before, "how it earns read only weakly"
    assert cos["NW"].get("on_industry") and not cos["NW"].get("model_out")
    assert cos["OTHER"]["out_why"] == "no_words"
    rec = D.out_reason({"model_out": "unknown", "out_why": "none_found", "status": "core"})
    assert rec["label"] == "insufficient evidence (no description found in any source)" and "read" not in rec["label"]


# ---------- 2. AI placements against what the layer is ----------
def test_drug_makers_are_not_in_the_research_tools_layer_and_novo_is_not_moved_on_generic_words_on_the_live_biotech_inputs():
    """Fails before: AbbVie and Gilead fitted "Research tools and diagnostics suppliers" because its description says its tools are "sold to
    labs and drug developers", and Novo Nordisk fitted "Bioprocessing suppliers and diversified healthcare" on "healthcare"."""
    at = where(replay51("biotech"))
    for s in ("ABBV", "GILD"):
        assert at[s][0] != "Research tools and diagnostics suppliers"
    assert at["NVO"][0] != "Bioprocessing suppliers and diversified healthcare"
    assert at["ILMN"][0] == "Research tools and diagnostics suppliers"            # the real tools maker stays


def test_an_ai_placement_whose_words_and_industry_are_another_layers_is_listed_but_left_out_of_the_figures():
    words = {**{f"T{i}": f"Tco {i} makes sequencers and lab instruments for genetic analysis." for i in range(3)},
             **{f"P{i}": f"Pco {i} sells a broad portfolio of branded drugs." for i in range(3)},
             "DRUG": "Dco produces drugs to treat a wide range of medical issues, with a comprehensive product portfolio."}
    inst, pharma = "Laboratory Analytical Instruments", "Pharmaceutical Preparations"
    vc = [{"layer": "Research tools suppliers", "description": "Make sequencers and instruments.",
           "companies": [{"ticker": f"T{i}", "name": f"Tco {i}", "industry": inst, "placed": "words"} for i in range(3)]
           + [{"ticker": "DRUG", "name": "Dco", "industry": pharma, "placed": "ai"}]},
          {"layer": "Drug portfolios", "description": "Sell branded drugs.",
           "companies": [{"ticker": f"P{i}", "name": f"Pco {i}", "industry": pharma, "placed": "words"} for i in range(3)]}]
    out = B.definition_fit(copy.deepcopy(vc), lambda s: words.get(s, ""), "Biotech", about_of=words.get)
    drug = next(c for v in out for c in v["companies"] if c["ticker"] == "DRUG")
    assert drug["unfit"]["layer"] == "Research tools suppliers" and "Drug portfolios" in drug["unfit"]["why"]
    assert next(v for v in out if any(c["ticker"] == "DRUG" for c in v["companies"]))["layer"] == "Research tools suppliers"      # never moved
    models = {s: "manufacturing" for s in words}
    got = B.by_model(out, models, "Biotech", confidence={s: "high" for s in words}, evidence_of=words.get)
    lay = next(v for v in got if v["layer"] == "Research tools suppliers")
    c = next(c for c in lay["companies"] if c["ticker"] == "DRUG")
    assert c["model_out"] == "other" and c["out_why"] == "unfit"
    rec = D.out_reason({**D.model_fields(lay, "DRUG"), "status": "core"})
    assert rec["kind"] == "another business" and rec["label"] == "another business than the layer's" and "Research tools suppliers" in rec["detail"]


# ---------- 3. ways of earning printed as fact ----------
def test_medical_laboratories_earn_from_tests_on_the_live_medical_devices_inputs():
    """Fails before: Labcorp, Quest and Natera read as managed IT services at low confidence (left out, printed "read as ..."), Guardant as
    consumer services; the layer of 21 labs had 3 in its figures and a line of "stays, trips, meals or courses"."""
    out = replay51("meddev")
    at = where(out)
    for s in ("LH", "DGX", "NTRA", "GH"):
        assert at[s][0] == "Diagnostic and genetic testing labs" and at[s][1]["model"] == "care" and not at[s][1].get("model_out")
    lay = next(v for v in out["value_chain"] if v["layer"].startswith("Diagnostic and genetic testing labs"))
    assert lay["model"]["id"] == "care" and "stays, trips" not in lay["model"]["line"]
    assert C.industry_model("managed_services", "Industry: Services-Medical Laboratories. Natera is a genetic testing company.", "low") == "care"
    assert C.industry_model("manufacturing", "Industry: In Vitro & In Vivo Diagnostic Substances. Makes reagents.", "medium") == "manufacturing"


def test_no_low_confidence_model_is_printed_and_acronyms_keep_their_case():
    rec = D.out_reason({"model_out": "unknown", "out_why": "weak", "model": "managed_services", "status": "core"})
    assert "read as" not in rec["detail"] and "managed" not in rec["detail"]
    lay = {"layer_model": "manufacturing", "layer_family": "making"}
    other = D.out_reason({"model_out": "other", "out_why": "model", "model": "managed_services", "status": "core", **lay})
    assert "managed and outsourced IT services" in other["label"] and " it services" not in other["label"]
    assert deck._low("Managed and outsourced IT services") == "managed and outsourced IT services"


def test_a_way_of_earning_shown_for_fewer_than_three_companies_is_not_said_to_be_what_they_mainly_earn():
    words = {f"C{i}": f"Cco {i} runs clinics." for i in range(2)}
    cos = [{"ticker": t, "name": t} for t in [*words, "U1", "U2", "U3"]]
    got = B.by_model([{"layer": "Labs", "description": "", "companies": cos}], {t: "consumer_services" for t in words}, "Health",
                     confidence={t: "medium" for t in words}, evidence_of=words.get)
    line = got[0]["model"]["line"]
    assert line.startswith("How they earn is shown for only 2 of these 5 companies; ") and "mainly" not in line


# ---------- 4. payments ----------
def test_payment_processors_and_networks_read_as_the_payments_model():
    for t in ("Fiserv processes debit and credit card transactions, loyalty programs and bill pay.",
              "Mastercard provides payment transaction processing and other related-payment services.",
              "Global Payments provides payment technology to merchants, issuers and consumers.",
              "Shift4 is a provider of software and payment processing solutions.",
              "Visa facilitates electronic funds transfers worldwide."):
        assert C.stated_model(t) == "payments" and C.model_supported("payments", t)
    assert C.name_models("Merchant acquiring and processing") == {"payments"} and C.name_models("Card networks") == {"payments"}
    assert C.MODELS["payments"][0] == "payments" and "payments" in C.MODEL_SYSTEM


def test_merchant_acquiring_has_its_companies_in_its_figures_on_the_live_payments_inputs():
    """Fails before: 1 of its 6 companies in its figures (Toast, read as software); Fiserv "read as managed and outsourced it services"."""
    out = replay51("payments")
    lay = next(v for v in out["value_chain"] if v["layer"] == "Merchant acquiring and processing")
    inn = {c["ticker"] for c in lay["companies"] if not c.get("model_out")}
    assert {"FISV", "GPN", "FOUR", "XYZ"} <= inn and len(inn) >= 4
    assert lay["model"]["id"] == "payments"
    fisv = next(c for c in lay["companies"] if c["ticker"] == "FISV")
    assert fisv["model"] == "payments"                                     # never the low read of managed IT services
    cards = next(v for v in out["value_chain"] if v["layer"] == "Card networks")
    assert {c["model"] for c in cards["companies"]} == {"payments"}


# ---------- 5. a conglomerate in the theme's size ----------
def test_a_conglomerate_counts_its_theme_segment_or_says_its_whole_market_value_is_counted():
    rows = [{"symbol": "AIR", "name": "Airco", "cap": 100.0}, {"symbol": "CONG", "name": "Congco", "cap": 400.0},
            {"symbol": "WIDE", "name": "Wideco", "cap": 300.0}, {"symbol": "HOT", "name": "Hotco", "cap": 50.0}]
    segs = {"CONG": [{"name": "Airports", "share_pct": 10.0}, {"name": "Mining", "share_pct": 60.0}, {"name": "Power", "share_pct": 30.0}]}
    s = D.size_section(rows, {"CONG", "WIDE"}, segs.get, lambda sym: B.kind_stems("Airlines and travel airports"))
    big = {x["symbol"]: x for x in s["biggest"]}
    assert big["CONG"]["cap"] == 40.0 and big["CONG"]["segment"] == "Airports" and big["CONG"]["full_cap"] == 400.0
    assert big["WIDE"]["whole"] and s["total_cap"] == 100.0 + 40.0 + 300.0 + 50.0
    assert deck.size_mark(big["CONG"]) == " (its Airports segment, 10.0% of revenue)" and deck.size_mark(big["WIDE"]) == " (whole company)"
    note = deck.size_note(s)
    assert "its segment that is the theme's" in note and "whole market value" in note
    assert D.size_section(rows)["total_cap"] == 850.0                       # with no whole-company member, as before


# ---------- 6. others ----------
def test_epc_contractors_are_in_the_figures_of_a_layer_whose_name_says_epc():
    """Fails before: L&T and KEC were left out of "Power equipment makers and EPC contractors" as a different revenue model."""
    words = {**{f"M{i}": f"Mco {i} manufactures transformers and switchgear." for i in range(4)},
             "LT": "Larsen & Toubro is primarily engaged in providing engineering, procurement and construction (EPC) solutions.",
             "KEC": "KEC International is a global infrastructure EPC major.", "OTH": "Oco builds roads."}
    vc = [{"layer": "Power equipment makers and EPC contractors", "description": "", "companies": [{"ticker": t, "name": t} for t in words]}]
    models = {**{f"M{i}": "manufacturing" for i in range(4)}, "LT": "construction", "KEC": "construction", "OTH": "construction"}
    # (held in the map's layer, as the live L&T and KEC were: R37 `settled`)
    got = B.by_model(copy.deepcopy(vc), models, "Capital goods", confidence={t: "high" for t in models}, evidence_of=words.get, settled={"LT", "KEC"})
    cos = {c["ticker"]: (v["layer"], c) for v in got for c in v["companies"]}
    for s in ("LT", "KEC"):
        assert cos[s][0] == "Power equipment makers and EPC contractors" and not cos[s][1].get("model_out") and cos[s][1].get("by_words")
    lay = next(v for v in got if v["layer"] == "Power equipment makers and EPC contractors")
    assert "a way of earning the layer's own name states too" in lay["model"]["line"]


def _block(name, ebitda, n=6, sbc=None, model=None, **kw):
    stats = {"ebitda": {"median": ebitda, "n": n}, "net": {"median": ebitda / 2, "n": n}, "roce": None}
    if sbc is not None:
        stats["sbc_share"] = {"median": sbc, "n": n}
    return {"layer": name, "n": n, "listed": n, "revenue": 100.0, "stats": stats, "official": False, "basis": None,
            "model": model or {"id": "software", "family": "software", "known": n, "of": n}, "intensity": None, "companies": [], **kw}


def test_layers_whose_stock_pay_is_more_than_twice_apart_are_not_ranked_on_ebitda_margin():
    """Fails before: "a gap of 30.4 points" between layers with stock pay of 21.9% and 8.6% of revenue."""
    ch = D._chain_table([_block("Data infrastructure software", -5.0, sbc=21.9), _block("Design software licences", 25.4, sbc=8.6)])
    assert ch["highest"] is None and ch["stock_pay"] and "Stock-based pay differs 2.5 times" in ch["line"] and "not ranked" in ch["line"]
    ok = D._chain_table([_block("A software", 20.0, sbc=10.0), _block("B software", 10.0, sbc=15.0)])
    assert ok["highest"] == "A software"
    assert D.comparable_rows([{"v": 1, "sbc_share": 5.0}, {"v": 2, "sbc_share": 20.0}], lambda r: r["v"], lambda r: 9) == []


def test_a_headline_gap_prints_both_margins_at_one_precision():
    """Fails before: "25.8% ... 20% ..., a gap of 5.8 points"."""
    cos = lambda k: [{"ebitda": 20.0, "ebitda_dp": 0} for _ in range(k)]      # noqa: E731  (margins filed in whole points)
    ch = D._chain_table([_block("Hospital chains", 25.8, companies=cos(6)), _block("Clinic chains", 20.0, companies=cos(6))])
    assert "(25.8%" in ch["line"] and "(20.0%" in ch["line"] and "a gap of 5.8 points" in ch["line"]
    assert D.one_precision(True, 25.0, 20.0) and not D.one_precision(True, 25.8, 20.0) and not D.one_precision(False, 25.0, 20.0)


def test_the_halves_of_a_split_layer_are_ranked_as_one_against_the_other_layers():
    """Fails before: a theme whose largest layer was split into halves by market value had no ranking at all."""
    from tests.test_r48_reconcile import co
    make = {"id": "manufacturing", "family": "making"}
    rows = []
    for i in range(12):
        r = D.company_row("IN", f"R{i}", co(f"R{i}", f"Regional {i} Ltd", 1000.0 + 10 * i, 14.0 + (i % 3), 80.0))
        rows.append({**r, "model": "manufacturing", "model_confidence": "high", "status": "core"})
    big = D.layer_block("Regional cement makers (larger)", rows[:6], set())
    small = D.layer_block("Regional cement makers (smaller)", rows[6:], set())
    big.update(scale="larger", sibling=small["layer"], model={**make, "known": 6, "of": 6})
    small.update(scale="smaller", sibling=big["layer"], model={**make, "known": 6, "of": 6})
    pan = _block("Pan-India cement makers", 22.0, model={**make, "known": 6, "of": 6})
    ch = D._chain_table([pan, big, small])
    assert ch["highest"] == "Pan-India cement makers" and ch["lowest"] == "Regional cement makers"
    assert "Regional cement makers (larger)" not in ch["line"]


def test_the_cohort_row_says_no_company_changed_when_an_earlier_version_is_stored():
    """Fails before: a log with no entry said "No earlier stored version", though the theme had been stored the day before."""
    row = deck.cohort_row({"changes": {"since": "2026-11-13", "entries": []}})
    assert row[1] == "0" and "13 Nov 2026" in row[2] and "no company with figures added, removed or moved" in row[2]
    assert deck.cohort_row({"changes": {"entries": []}})[2].startswith("No earlier stored version")


# ---------- 7. the earlier answer of the same map, past the nearest ----------
def test_the_walk_back_reaches_the_answer_that_still_has_the_extra_layers(monkeypatch):
    """Fails before: the walk stopped at the nearest earlier answer (rules 48's, which had lost the two extra layers) and never reached rules
    44's, so the live IT services page kept BBOX and SAGILITY in "Other"."""
    d = json.loads((LIVE / "inputs_r49" / "it.json").read_text())
    d = d.get("data", d)
    lost, early = d["kept"], d["earlier"]
    assert not lost.get("extra") and len(early["extra"]) == 2
    store = {TR.PLACE_CARRY[B.RULES]: lost, TR.PLACE_CARRY[TR.PLACE_CARRY[B.RULES]]: lost, 44: early}
    monkeypatch.setattr(computed, "get", lambda kind, key: {"value": store[key[-1]]} if key[-1] in store else None)
    kept, version = TR.kept_placement("IN", "IT services", {"generated_at": d["generated_at"]})
    assert version == TR.PLACE_CARRY[B.RULES]
    assert {x["name"] for x in kept["extra"]} == {"IT infrastructure, cloud and systems integration", "Healthcare and digital business process services"}
    # an older answer fills only what the nearer ones lack
    got = B.fill_earlier({"rename": {"L": {"name": "New"}}, "extra": [{"name": "E1"}]}, {"rename": {"L": {"name": "Old"}, "M": {"name": "M2"}},
                                                                                         "extra": [{"name": "E1"}, {"name": "E2"}]})
    assert got["rename"] == {"L": {"name": "New"}, "M": {"name": "M2"}} and [x["name"] for x in got["extra"]] == ["E1", "E2"]


def test_versions():
    assert B.RULES == 52 and TR.PLACE_CARRY[52] == 51 and TR.PLACE_CARRY[51] == 50 and deck.THEME_DECK_VERSION == 63 and D.DIVE_TEXT == 23          # d53 (R53): RULES 52, PLACE_CARRY[52] = 51, deck 63, dive text 23 (updated on purpose)


# ---------- integrator: "on its industry" for a company with no words only where its industry points to this layer ----------
def _machinery(elsewhere: int) -> dict:
    """A layer whose name names "Industrial Machinery", holding 3 read makers of heavy equipment, 3 read makers of industrial machinery and one
    company of industrial machinery with no words; `elsewhere` read industrial machinery makers in a pumps layer."""
    words, cos_a, cos_b = {}, [], []
    for i in range(3):
        words[f"H{i}"] = f"Hco {i} manufactures cranes and earthmovers."
        cos_a.append({"ticker": f"H{i}", "name": f"Hco {i}", "industry": "Heavy Equipment", "placed": "words"})
    for i in range(3):
        words[f"M{i}"] = f"Mco {i} manufactures lathes and presses."
        cos_a.append({"ticker": f"M{i}", "name": f"Mco {i}", "industry": "Industrial Machinery", "placed": "words"})
    cos_a.append({"ticker": "NW", "name": "Nco", "industry": "Industrial Machinery", "placed": "words"})
    for i in range(3):
        words[f"P{i}"] = f"Pco {i} manufactures pumps and valves."
        cos_b.append({"ticker": f"P{i}", "name": f"Pco {i}", "industry": "Pumps", "placed": "words"})
    for i in range(elsewhere):
        words[f"E{i}"] = f"Eco {i} manufactures machine tools and pumps."
        cos_b.append({"ticker": f"E{i}", "name": f"Eco {i}", "industry": "Industrial Machinery", "placed": "words"})
    vc = [{"layer": "Industrial machinery makers", "description": "", "companies": cos_a},
          {"layer": "Pump makers", "description": "", "companies": cos_b}]
    models = {s: "manufacturing" for s in words}
    got = B.by_model(copy.deepcopy(vc), models, "Capital goods", confidence={s: "high" for s in models}, evidence_of=lambda s: words.get(s, ""))
    return {c["ticker"]: c for v in got for c in v["companies"]}


def test_a_company_with_no_words_counts_on_its_industry_only_where_that_industry_points_mostly_to_its_layer():
    """Fails on e67d9d3: a layer whose name named the industry took every company of it with no words, however that industry's read companies
    were spread (the live Capital goods replay: 128 "Industrial Products" companies with no words counted in "Engines and industrial
    machinery makers", 25 of the 40 read ones there and 15 over six other layers)."""
    broad = _machinery(elsewhere=3)               # 3 of the 6 read industrial machinery makers here: the industry points nowhere
    assert not broad["NW"].get("on_industry") and broad["NW"]["model_out"] and broad["NW"]["out_why"] == "no_words"
    narrow = _machinery(elsewhere=1)              # 3 of 4 here (75%): it points to this layer
    assert narrow["NW"].get("on_industry") and not narrow["NW"].get("model_out")
    assert B.ON_INDUSTRY_SHARE == 2 / 3 and B.ON_INDUSTRY_MIN == 3

