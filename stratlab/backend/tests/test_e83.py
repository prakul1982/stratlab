"""Lane e83 (Release 82): theme-engine items from LIVE19A/B and the R81 decks. Each test fails before its fix and passes after, except those
marked as guards."""
import pytest

from app.intel import sector_metrics as SM


@pytest.fixture
def fake_db(monkeypatch):
    from app import db
    from tests.fake_db import FakeSupabase
    f = FakeSupabase()
    monkeypatch.setattr(db, "_client", f)
    return f


# ---------- 3. LIVE19A-002/005: the FFO a REIT reports, read from the row that is the FFO itself ----------
# Each excerpt is the filing's own text (FY2025 10-K, SEC EDGAR), as StratLab reads it (sec.html_text, spaces joined)
ESSEX_10K = (
    "The table below is a reconciliation of net income available to common stockholders to FFO and Core FFO for the periods presented ($ in "
    "thousands, except per share amounts): Year Ended December 31, 2025 2024 2023 Net income available to common stockholders $ 669,666 $ "
    "741,522 $ 405,825 Adjustments: Depreciation and amortization 607,542 580,220 548,438 Gains not included in FFO (305,043) (386,138) "
    "(59,238) Casualty loss — — 433 Impairment loss from unconsolidated co-investments 12,634 3,726 33,700 Depreciation and amortization from "
    "unconsolidated co-investments 56,848 66,943 71,745 Noncontrolling interest related to Operating Partnership units 23,649 26,414 14,284 "
    "Depreciation attributable to third party ownership and other (160) 31,191 (1,474) Funds from operations attributable to common "
    "stockholders and unitholders $ 1,065,136 $ 1,063,878 $ 1,013,713 FFO per share-diluted $ 15.98 $ 15.99 $ 15.24 Non-core items: "
    "Expensed acquisition and investment related costs $ 25 $ 72 $ 595")
AMT_10K = (
    "Year Ended December 31, Percent Change 2025 vs 2024 2025 2024 Net income (1) $ 2,628.5 $ 2,280.2 15 % Real estate related depreciation, "
    "amortization and accretion 1,899.6 1,879.6 1 Losses from sale or disposal of real estate and real estate related impairment charges (2) "
    "83.5 91.6 (9) Adjustments and distributions for unconsolidated affiliates and noncontrolling interests (3) (450.7) (352.7) 28 Adjustments "
    "for discontinued operations (4) — 1,334.5 (100) Nareit FFO attributable to American Tower Corporation common stockholders $ 4,160.9 $ "
    "5,233.2 (20) % Straight-line revenue (101.0) (277.6) (64)")
KIMCO_10K = (
    "Depreciation and amortization - real estate related 153,001 154,905 622,530 598,741 Noncontrolling interests (1) (756 ) (783 ) (3,009 ) "
    "(3,150 ) FFO available to the Company’s common shareholders (3) (4) $ 294,327 $ 286,901 $ 1,194,094 $ 1,112,076 Weighted average shares "
    "outstanding for FFO calculations: Basic 673,914 673,676 675,050 671,561")
BXP_10K = (
    "Noncontrolling interests in property partnerships 75,181 67,516 78,661 Funds from Operations (FFO) attributable to the Operating "
    "Partnership common unitholders (including BXP, Inc.) 1,209,636 1,248,026 1,274,568 Less: Noncontrolling interest—common units of the "
    "Operating Partnership’s share of funds from operations 120,601 127,548 130,771 Funds from Operations attributable to BXP, Inc. $ "
    "1,089,035 $ 1,120,478 $ 1,143,797")
PLD_10K = (
    "(in millions) Net earnings attributable to common stockholders $ 3,322 $ 3,726 Add (deduct) NAREIT defined adjustments: Real estate "
    "related depreciation and amortization 2,588 2,506 NAREIT defined FFO attributable to common stockholders/unitholders $ 5,680 $ 5,795 "
    "Add (deduct) our modified adjustments: FFO, as modified by Prologis attributable to common stockholders/unitholders $ 5,779 $ 5,741 "
    "Core FFO attributable to common stockholders/unitholders $ 5,561 $ 5,305")
ARE_JV_10K = (
    "Straight-line rent and below-market lease revenue $ 2,723 $ 19,580 $ 139 $ 645 Funds from operations (4) $ 77,922 $ 320,030 $ 526 $ "
    "2,262 Refer to “ Joint venture financial information ” ... (in thousands) Unvested restricted stock awards (5,681) (8,696) (5,175) Funds "
    "from operations attributable to Alexandria Real Estate Equities, Inc.’s common stockholders – diluted (3) 1,310,607 1,431,750 1,577,598 "
    "... Funds from operations attributable to Alexandria Real Estate Equities, Inc.’s common stockholders – diluted, as adjusted $ 1,534,664")


def test_e83_essex_reported_ffo_is_the_years_ffo_row_never_the_gains_not_included_in_ffo():
    """LIVE19A-002: Essex "$305 m (reported)", P/FFO 56.80x, from "Gains not included in FFO (305,043)"; its 10-K: $1,065.1 m."""
    assert SM.reported_ffo(ESSEX_10K) == 1065.1
    got = SM.with_reported_ffo({"ffo": {"v": 977.7, "period": "Fiscal year to Dec 2025", "source": "derived"}}, ESSEX_10K, 1887.3)
    assert got["ffo"]["v"] == 1065.1 and got["ffo"]["basis"] == "reported" and got["ffo_derived"]["v"] == 977.7
    assert got["ffo_share"]["v"] == 56.4


def test_e83_american_tower_and_other_labels_of_reported_ffo_are_read():
    """LIVE19A-005: American Tower's "Nareit FFO attributable to American Tower Corporation common stockholders $ 4,160.9" (millions) was
    missed (shown derived $4.57 bn), as were Prologis' "NAREIT defined FFO", Kimco's year column and BXP's company row."""
    assert SM.reported_ffo(AMT_10K) == 4160.9
    assert SM.reported_ffo(PLD_10K) == 5680.0                       # never the "as modified" or Core rows
    assert SM.reported_ffo(BXP_10K) == 1089.0                       # never the noncontrolling units' "share of funds from operations"
    assert SM.reported_ffo(KIMCO_10K, near=1211.8) == 1194.1        # the year's column, not the quarter's, beside its derived FFO
    assert SM.reported_ffo("Public Storage (amounts in thousands) Eliminate items excluded from FFO: Real estate-related depreciation and "
                           "amortization 1,140,377 1,117,752 FFO allocable to common shares $ 2,780,451 $ 3,025,914 (8.1) %") == 2780.5
    assert SM.reported_ffo("(in thousands) Provision for impairment 78,553 191,185 FFO available to common stockholders and unitholders (2) "
                           "$ 2,399,032 $ 2,027,124 $ 1,915,747 Basic FFO per share and unit $ 6.94") == 2399.0
    assert SM.reported_ffo("(in thousands) distributions and dividends (4,503) (4,897) FFO of the Operating Partnership $ 4,663,305 $ "
                           "4,876,844 FFO allocable to limited partners 636,189 640,886") == 4663.3


def test_e83_a_joint_ventures_row_or_a_figure_far_from_the_derived_one_is_never_the_reported_ffo():
    assert SM.reported_ffo(ARE_JV_10K) == 1310.6                    # the company's own (attributable) row before a bare JV table row
    assert SM.reported_ffo("(in thousands) Funds from operations $ 77,922 $ 320,030", near=1500.0) is None
    assert SM.reported_ffo("(in thousands) Funds from operations $ 77,922", revenue=3026.6) is None          # 2.6% of revenue
    assert SM.REIT_V >= 3                                            # every property owner's piece read again


def test_e83_guards_camden_and_core_lines():
    """Guards: Camden's $744.8 m (e81) still read; Core, Normalized and per-share lines never."""
    from tests.test_e81 import CAMDEN_10K
    assert SM.reported_ffo(CAMDEN_10K) == 744.8
    assert SM.reported_ffo("(in thousands) Core FFO $ 762,551 and Normalized FFO $ 700,000 and FFO per diluted share $ 6.79") is None
    assert SM.reported_ffo("Computation of FFO and Normalized FFO: Net income available for Common Stockholders $ 386,492 $ 366,998") is None


# ---------- 1. LIVE19A-001: the public gate judges every stored entry in full ----------
def test_e83_the_store_index_keeps_the_gate_mark_so_the_gate_judges_a_new_entry(fake_db):
    """The cause: computed.put kept only some meta keys in the index, never "broad", so public_themes.entries read every entry as one kept
    before the gate ("judged on the dive count only")."""
    from app import computed
    computed.reset_for_tests()
    computed.put("theme_library_e83", ["US", "quantum computing"], {"payload": {}}, label="Quantum computing", region="US",
                 meta={"q": "quantum computing", "rules": 1, "broad": True, "generated_at": 5.0})
    m = next(iter(computed.index("theme_library_e83")["entries"].values()))["meta"]
    assert m["broad"] is True and m["generated_at"] == 5.0


def _quantum_index(monkeypatch, pub: dict, meta_q: dict, tally: dict | None = None):
    from app import computed, public_themes
    from app.intel import theme_base, theme_library as TL
    idx = {"entries": {
        "q": {"region": "US", "label": "Quantum computing", "at": 3.0, "meta": {"q": "quantum computing", "rules": theme_base.RULES, **meta_q}},
        "s": {"region": "US", "label": "Semiconductors", "at": 1.0, "meta": {"q": "semiconductor", "rules": theme_base.RULES, "broad": False}}}}
    dives = {"entries": {"d1": {"region": "US", "at": 1.0, "meta": {"q": "semiconductor", "pub": {"all": 104, "listed": 102, "unlisted": [], "unchecked": 1}}},
                         "d2": {"region": "US", "at": 2.0, "meta": {"q": "quantum computing", "pub": pub}}}}
    monkeypatch.setattr(computed, "index", lambda kind: idx if kind == TL.KIND else dives)
    monkeypatch.setattr(public_themes, "payload", lambda e: {"sector": e["name"], "placements": {"industries_by": "ai"}, "value_chain": []})
    monkeypatch.setattr(public_themes, "_dive", lambda r, n, p: {"tally": tally} if tally else {})
    public_themes._GATE_MEMO.clear()
    return public_themes


def test_e83_an_entry_whose_listed_companies_are_a_quarter_not_checked_leaves_the_themes_list_and_its_page(monkeypatch):
    """Quantum computing after the R81 re-check: 386 companies, all listed, 92 not checked (24%): the gate counted only those its page left
    out (none) and let it through."""
    pt = _quantum_index(monkeypatch, {"all": 386, "listed": 386, "unlisted": [], "unchecked": 92}, {"broad": False})
    assert [x["name"] for x in pt.entries("US")] == ["semiconductor"]
    assert pt.find("US", "quantum-computing") == (None, None)                 # its public page: no theme at this address (404)


def test_e83_an_entry_kept_before_the_gate_is_judged_on_its_dives_own_tally_and_its_read(monkeypatch):
    # its index meta has no "broad" and its kept count no "unchecked" (kept before this release): the dive's tally is read
    pt = _quantum_index(monkeypatch, {"all": 386, "listed": 386, "unlisted": []}, {},
                        tally={"total": 386, "membership_unverified": 92, "description_verified": 244})
    assert [x["name"] for x in pt.entries("US")] == ["semiconductor"]
    # guard: the same entry with 10% or fewer not checked stays
    pt = _quantum_index(monkeypatch, {"all": 386, "listed": 386, "unlisted": []}, {},
                        tally={"total": 386, "membership_unverified": 30, "description_verified": 300})
    assert [x["name"] for x in pt.entries("US")] == ["quantum computing", "semiconductor"]


def test_e83_the_gate_mark_is_worked_out_from_an_old_entrys_stored_read(monkeypatch):
    from app.intel import theme_library as TL
    cos = [{"ticker": f"T{i}", "name": f"T{i}"} for i in range(200)]
    p = {"placements": {"industries_by": "ai"}, "value_chain": [{"layer": "Computers", "official": True, "companies": cos}]}
    assert TL.gate_why({"rules": 70}, {"all": 200, "listed": 200, "unlisted": [], "unchecked": 0}, p).startswith("its companies come almost all")
    assert TL.gate_why({"rules": 70}, {"all": 200, "listed": 200, "unlisted": [], "unchecked": 0}, None) == ""       # guard: no read, nothing said


# ---------- 7. LIVE19B-005 (LIVE18B-006): one rule for n.m. and counts across the deck ----------
def test_e83_a_layers_median_count_and_bottom_leave_out_an_nm_margin_as_the_legend_says():
    """The sample Consumer durables deck: "EBITDA margin 6.4% (11 of 11) ... bottom Universus Photo Imagings Ltd −530% (of 11)" while its row
    printed n.m. and the legend said n.m. figures are out of every median, range and aggregate."""
    from app.intel import layer_profiles as LP
    cos = [{"symbol": f"S{i}", "name": f"Small {i}", "ebitda": 4.0 + i, "roce": 8.0 + i, "sales_1y": 2.0 + i} for i in range(10)]
    cos.append({"symbol": "UNI", "name": "Universus Photo Imagings Ltd", "ebitda": -530.0, "roce": -12.1, "sales_1y": -24.0})
    fin = LP.financial({"model": {"family": "making"}, "companies": cos}, "IN")
    eb = next(f for f in fin["figs"] if f["key"] == "ebitda")
    assert eb["n"] == 10 and eb["of"] == 11 and eb["min"] == 4.0
    assert fin["top"]["key"] == "ebitda" and fin["top"]["low"] == (4.0, "Small 0") and fin["top"]["n"] == 10
    assert next(f for f in fin["figs"] if f["key"] == "roce")["n"] == 11         # guard: its other figures stay in


def test_e83_a_series_break_clears_the_layers_growth_as_it_clears_the_appendixs():
    """LIVE18B-006: layer 1 "Revenue growth +22.2% (5 of 5)" while the appendix printed Growth "–" for Dixon and PG Electroplast: the growth
    of a company whose series broke was cleared on the appendix's rows after the layers had copied them."""
    import copy
    from datetime import date
    from app.intel import theme_data as D
    from tests.test_r17_fixes import theme_a
    region, m, f = theme_a()
    m = copy.deepcopy(m)
    sym = m["value_chain"][1]["companies"][0]["ticker"]
    jumped = copy.deepcopy(f.get(sym))
    jumped["years"][-1]["sales"] = jumped["years"][-2]["sales"] * 2          # a year's revenue doubling: a merger moved a business in
    facts = {**{s: f.get(s) for s in [c["ticker"] for v in m["value_chain"] for c in v["companies"]]}, sym: jumped}
    dive = D.build(region, m["sector"], m, D.Sources(date(2026, 10, 5), facts=lambda s: facts.get(s) if s in facts else f.get(s)))
    lead = next(r for r in dive["sections"]["leaders"] if r["symbol"] == sym)
    row = next(r for b in dive["layers"] for r in b["companies"] if r["symbol"] == sym)
    assert lead["sales_1y"] is None and row["sales_1y"] is None and row.get("series_break")


# ---------- 6. LIVE19A-010: no lone unlabelled "–" on a phone card; the column notes after the tables ----------
def test_e83_a_public_cards_missing_ffo_is_labelled_and_the_column_notes_follow_the_tables():
    import re
    from app import public_themes
    page = {"region": "US", "label": "REITs", "slug": "reits", "name": "reit", "evidence": None, "older": False, "rechecking": False,
            "summary": "", "members": 2, "all": 2, "counts": {"listed": 2, "layers": 1, "all": 2, "unlisted": []}, "tally_at": None,
            "prices": None, "day": None, "indexable": False,
            "layers": [{"name": "Residential landlords", "evidence": None, "companies": [
                {"symbol": "CPT", "name": "Camden Property Trust", "page": None, "cap": "$9.6B", "revenue": "$1.6B", "year": "2025",
                 "evidence": "industry_code_supported", "ffo": "$744.8M (reported)"},
                {"symbol": "UDR", "name": "UDR", "page": None, "cap": "$12.0B", "revenue": "$1.7B", "year": "2025", "evidence": None}]}]}
    html_ = public_themes.render(page)
    assert not re.search(r"<td>–</td>", html_)                                # every "–" cell carries its label on a phone card
    assert '<td data-label="FFO">–</td>' in html_
    last_table = html_.rindex("</table>")
    assert html_.index("data-ffo-note") > last_table and html_.index("data-membership-note") > last_table


# ---------- 4. LIVE19A-004: REIT placements that hold, and their reasons ----------
def test_e83_a_reit_named_for_the_property_its_layer_names_stays_there():
    """Omega Healthcare Investors moved from "Healthcare property owners" to "Mortgage REITs": "its own words don't say it sells what
    “Healthcare property owners” is (“owners”)"."""
    from app.intel import theme_base as B
    words = {"OHI": "The Company invests in long-term care real estate and leases it to operators under triple-net leases.",
             "WELL": "Welltower owns senior housing, post-acute communities and outpatient medical properties."}
    out = [{"layer": "Healthcare property owners", "description": "They own healthcare properties.", "companies": [
                {"ticker": "WELL", "name": "Welltower Inc", "industry": "Real Estate Investment Trusts", "model": "property"},
                {"ticker": "OHI", "name": "Omega Healthcare Investors Inc", "industry": "Real Estate Investment Trusts", "model": "property",
                 "moved": True}]},
           {"layer": "Mortgage REITs", "description": "They lend.", "companies": [{"ticker": "KREF", "name": "KKR Real Estate Finance"}]},
           {"layer": "Other real estate investment trust companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    got = B.sold_what(out, {}, lambda v: False, lambda cos: "", lambda c: "", lambda c: words.get(c.get("ticker"), ""),
                      B.kind_stems("Real estate investment trusts"), "Real estate investment trusts", {}, None,
                      {"OHI": ["Mortgage REITs", "Healthcare property owners"]})
    at = {c["ticker"]: v["layer"] for v in got for c in v["companies"]}
    assert at["OHI"] == "Healthcare property owners"
    assert B.named_property({"layer": "Healthcare property owners"}, {"name": "Omega Healthcare Investors Inc", "model": "property"}, "")
    # guards: a name naming no kind, or a lender's words, judge nothing
    assert not B.named_property({"layer": "Healthcare property owners"}, {"name": "Pillarstone Capital REIT", "model": "property"}, "")
    assert not B.named_property({"layer": "Healthcare property owners"}, {"name": "Healthcare Lending Trust", "model": "property"},
                                "It originates senior secured mortgage loans to operators.")


def test_e83_a_diversified_owner_never_goes_on_shared_words_to_a_layer_of_a_kind_of_property_it_doesnt_name():
    """Pillarstone Capital REIT, "engaged in investing in, owning and operating commercial properties", moved into "Hotel and leisure
    property owners" on the words it shares with that layer's description (its 4th layer in 4 days)."""
    from app.intel import theme_base as B
    pil = {"ticker": "PRLEQ", "name": "Pillarstone Capital REIT", "moved": True}
    vc = [{"layer": "Towers, data centres and niche property", "description": "Towers and data centres.", "companies": [
              pil, {"ticker": "AMT", "name": "American Tower"}]},
          {"layer": "Hotel and leisure property owners", "description": "They own and operate hotel and leisure properties, investing in resorts.",
           "companies": [{"ticker": "HST", "name": "Host"}, {"ticker": "PK", "name": "Park"}]},
          {"layer": "Other real estate investment trust companies", "description": "", "official": True, "basis": "rest", "companies": []}]
    words = {"PRLEQ": "The Trust is engaged in investing in, owning and operating commercial properties.",
             "AMT": "We own and operate communications towers and data centres."}
    out, rows = B.compute_fit(vc, words.get, "Real estate investment trusts")
    at = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert at["PRLEQ"] == "Other real estate investment trust companies", rows


def test_e83_a_commercial_mortgage_lender_is_not_held_out_of_the_lenders_layer_for_missing_its_name():
    from app.intel import theme_base as B
    t = "Franklin BSP Realty Trust originates, acquires and manages a portfolio of commercial real estate debt secured by properties."
    assert B.lends_into("Mortgage REITs", {"model": "lending"}, t)
    assert B.lends_into("Mortgage REITs", {"model": "lending", "model_confidence": "medium"}, "The Company is the managing member of the OP.")
    assert not B.lends_into("Mortgage REITs", {"model": "property"}, "We own and lease apartment communities.")        # guard
    assert not B.lends_into("Residential landlords", {"model": "lending"}, t)                                           # guard


def test_e83_a_move_reason_never_names_a_layer_the_company_did_not_leave():
    """BREIT "Mortgage REITs → Other: ... a diversified owner, never a layer of towers and data centres"."""
    from app.intel import theme_base as B, theme_changes as C
    why, _ = B.kind_bar("Towers, data centres and niche property", {"name": "Blackstone Real Estate Income Trust, Inc."},
                        "We are a non-listed REIT that invests in stabilized income-generating commercial real estate.", "Real estate investment trusts")
    assert "“Towers, data centres and niche property”" in why
    assert C.fit_reason(why, "Mortgage REITs", "Other real estate investment trust companies") is None       # said from its own words instead
    assert C.fit_reason(why, "Towers, data centres and niche property", "Other real estate investment trust companies") == why     # guard


# ---------- 9. LIVE19A-009: a move's quote says something of its work and of the layer ----------
def test_e83_a_move_never_quotes_a_line_of_legal_form_size_or_history():
    """The R81 Regional banks deck: moves into "Real estate-focused lenders (bank)" quoting BankUnited's "with total consolidated assets of
    $35 billion at December 31, 2025", Beacon's "a Delaware corporation", Provident's "became the holding company for Provident Bank on
    January 15, 2003"."""
    from app.intel import theme_changes as C
    lay = "Real estate-focused lenders (bank)"
    bku = ("BankUnited, Inc., with total consolidated assets of $35 billion at December 31, 2025, is the bank holding company of BankUnited, "
           "N.A., a national banking association headquartered in Miami Lakes, Florida.")
    pfs = "The Company is a Delaware corporation which became the holding company for Provident Bank on January 15, 2003."
    assert C.layer_quote(bku, "BankUnited, Inc.", lay) == ("", False)
    assert C.layer_quote(pfs, "Provident Financial Services Inc", lay) == ("", False)
    beacon = "Beacon Financial Corporation, a Delaware corporation, is the holding company. The Bank offers commercial real estate loans."
    assert C.layer_quote(beacon, "Beacon Financial Corp", lay) == ("The Bank offers commercial real estate loans", True)
    log = [{"d": "2026-11-20", "moved": [{"symbol": "PFS", "name": "Provident Financial Services Inc", "from": "Other regional bank companies",
                                          "to": lay}]}]
    got = C.reasoned(log, words_of=lambda s: pfs)[0]["moved"][0]["why"]
    assert "Delaware" not in got and "the theme's map places it in" in got
    # guard: a line of what it does is still quoted
    assert C.layer_quote("General Dynamics is a developer and producer of advanced military equipment.", "General Dynamics",
                         "Defense prime contracting")[1] is True


def test_e83_an_encyclopedias_opening_is_never_the_quote_that_moves_a_company():
    """The R81 Biotech deck: Amneal moved to "Established pharmaceutical companies" as "its own words call it a company of another kind than
    the theme's (“is an American publicly traded pharmaceutical company”)"."""
    from app.intel import theme_base as B
    assert B.encyclopedia_like("Amneal Pharmaceuticals, Inc. is an American publicly traded pharmaceutical company.")
    assert not B.encyclopedia_like("Amneal is a global pharmaceutical company that makes generic medicines.")          # guard
    theme_rx = r"\bbiotech"
    words = {"AMRX": "Amneal Pharmaceuticals, Inc. is an American publicly traded pharmaceutical company. It develops generics.",
             "MRK": "Merck is a global pharmaceutical company that discovers and sells medicines.",
             "PFE": "Pfizer is a research-based pharmaceutical company that discovers and sells medicines.",
             "B1": "B1 is a biotechnology company selling specialty medicines.", "B2": "B2 is a biotechnology company selling rare disease medicines."}
    cos = [{"ticker": t_, "name": n_} for t_, n_ in (("AMRX", "Amneal Pharmaceuticals, Inc."), ("MRK", "Merck & Co., Inc"), ("PFE", "Pfizer Inc"),
                                                    ("B1", "B1 Bio"), ("B2", "B2 Bio"))]
    vc = [{"layer": "Commercial specialty biotechs", "description": "They sell approved specialty medicines.", "companies": cos},
          {"layer": "Other biotech companies", "official": True, "basis": "rest", "companies": []}]
    fn = next(f for n_, f in vars(B).items() if callable(f) and getattr(f, "__code__", None) and "an established " in str(f.__code__.co_consts)
              and n_ != "encyclopedia_like")
    got = fn(vc, words.get, "Biotechnology")
    out = got[0] if isinstance(got, tuple) else got
    at = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert at["AMRX"] == at["MRK"] == "Established pharmaceutical companies", at
    why = {r["ticker"]: r["why"] for r in got[1]}
    assert "American publicly traded" not in why["AMRX"] and why["AMRX"].startswith("its description calls it")
    assert why["MRK"].startswith("its own words call it") and "“is a global pharmaceutical company”" in why["MRK"]


def test_e83_a_kept_reason_quoting_no_line_of_work_is_said_again_from_its_words():
    """The stored 15-20 Nov Regional banks moves still quoting FB Bancorp's "New Orleans has one of the busiest ports in the world…" and TFS
    Financial's "statements regarding our business plans…"."""
    from app.intel import theme_changes as C
    lay = "Real estate-focused lenders (bank)"
    old = (f"its own words don't say property is its business (they say “New Orleans has one of the busiest ports in the world…”); a Regional "
           f"banks theme holds “{lay}” only for those whose do")
    log = [{"d": "2026-11-16", "moved": [{"symbol": "FBLA", "name": "FB Bancorp", "from": lay, "to": "Other regional bank companies", "why": old}]}]
    got = C.reasoned(log, words_of=lambda s: "FB Bancorp is the holding company. The Bank offers residential mortgage and commercial loans.")
    why = got[0]["moved"][0]["why"]
    assert "New Orleans" not in why and "The Bank offers residential mortgage and commercial loans" in why
    assert C.unquotable_reason("its own words don't say property is its business (they say “statements regarding our business plans and prospects…”)")
    # guards: a reason quoting a line of its work, or only a layer's name, stands
    assert not C.unquotable_reason("its own words say “The Bank offers commercial real estate and residential mortgage loans”")
    assert not C.unquotable_reason("its own words don't say it sells computing, what “Towers, data centres and niche property” is")


# ---------- 2. LIVE19A-003: "Description-verified" means its own words say the theme's work, not a word of an AI-picked industry ----------
def _gold():
    inds = ["Gold and Silver Ores", "Bituminous Coal & Lignite Surface Mining", "Primary Production Of Aluminum",
            "Mining & Quarrying Of Nonmetallic Minerals"]
    co = lambda t, n, ind: {"ticker": t, "name": n, "base": True, "basis": "industry", "industry": ind, "what": ""}      # noqa: E731
    return {"sector": "Gold miners", "placements": {"industries_by": "ai", "industries": inds},
            "value_chain": [{"layer": "Exploration and development", "description": "Companies mining and developing gold deposits.",
                             "companies": [co("MLM", "Martin Marietta Materials", inds[3]), co("BTU", "Peabody Energy", inds[1])]},
                            {"layer": "Other gold miner companies", "official": True, "basis": "rest",
                             "companies": [co("SCCO", "Southern Copper", inds[3]), co("AEM", "Agnico Eagle Mines", inds[0])]}]}


def test_e83_a_company_of_an_ai_picked_industry_is_description_verified_only_on_the_themes_own_work():
    from app.intel import theme_data as D
    m = _gold()
    words = D.theme_words(m, "Gold miners")
    about = {"MLM": "Martin Marietta is a natural resource-based building materials company that supplies aggregates from its quarrying and mining operations.",
             "BTU": "Peabody is a coal producer engaged in surface mining of thermal and metallurgical coal.",
             "SCCO": "Southern Copper is one of the largest integrated copper producers, mining and smelting copper and molybdenum.",
             "AEM": "Agnico Eagle is a gold mining company producing gold from mines in Canada, Australia and Finland."}
    cos = {c["ticker"]: c for v in m["value_chain"] for c in v["companies"]}
    before = {s: D.evidence_state(c, words, about[s]) for s, c in cos.items()}
    assert before["MLM"] == before["SCCO"] == "description_verified"          # (the industry names' "quarrying", "mining" said)
    wt = D.work_test(m, "Gold miners")
    after = {s: D.work_checked(before[s], c, about[s], wt) for s, c in cos.items()}
    assert after == {"MLM": "industry_code_supported", "BTU": "industry_code_supported", "SCCO": "industry_code_supported",
                     "AEM": "description_verified"}, after
    # the same on the companies checked past the figures' window, and on those an earlier read kept
    got = D.membership_round(m, set(), words, about.get, 10, wt)
    assert got["MLM"] == "industry_code_supported" and got["AEM"] == "description_verified"
    assert D.kept_work_checked(m, {"SCCO": "description_verified"}, about.get, wt) == {"SCCO": "industry_code_supported"}


def test_e83_a_curated_themes_evidence_is_unchanged_and_quantum_needs_both_words():
    from app.intel import theme_data as D
    assert D.work_test({"placements": {"industries_by": "list"}}, "Semiconductors") is None          # guard: the curated table
    q = {"placements": {"industries_by": "ai"}, "value_chain": [{"layer": "Other quantum computing companies", "official": True, "companies": []}]}
    wt = D.work_test(q, "Quantum computing")
    apple = {"ticker": "AAPL", "name": "Apple Inc.", "base": True}
    assert not wt(apple, "Apple designs, manufactures and markets smartphones, personal computers, tablets and wearables.")
    assert wt({"ticker": "IONQ", "name": "IonQ", "base": True}, "IonQ builds quantum computers and sells quantum computing services.")


def test_e83_versions():
    from app import blog_research, deck
    from app.intel import sector_metrics, theme_base, theme_data, theme_routes
    assert theme_base.RULES == 78 and theme_routes.PLACE_CARRY[78] == 77 and theme_routes.EARLIER_MAX == 33
    assert theme_data.DIVE_TEXT == 49 and deck.THEME_DECK_VERSION == 89 and blog_research.GEN == 11
    assert sector_metrics.VERSION == 3 and sector_metrics.REIT_V == 3                    # never sector_metrics.VERSION
