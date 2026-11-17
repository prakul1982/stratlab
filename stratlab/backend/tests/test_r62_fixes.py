"""r62 (R62): the owner's outside review of the live R60 decks and the R60 deck_check flags, each fix generic (India and US), each test
failing before the fix and passing after it."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


def _fy(end: str, start: str, v: float, filed: str = "2026-02-20") -> dict:
    return {"start": start, "end": end, "val": v, "form": "10-K", "filed": filed, "fp": "FY"}


def _at(end: str, v: float, filed: str = "2026-02-20") -> dict:
    return {"end": end, "val": v, "form": "10-K", "filed": filed, "fp": "FY"}


# ---------- deck_check: the R60 FAILs that were the check's own reading ----------
INSURANCE_P11 = """INSURANCE · THE VALUE CHAIN


Smaller layers
2 layers of 2 member companies or fewer, 2 companies: the company, what it does and its key figures, one row each



 Layer                                  Company                         What it does                                                Revenue         Net margin      Year


                                                                        PB Fintech Ltd, popularly known as Policy Bazar is
 Distribution and aggregation           PB Fintech Limited                                                                         ₹6,794 cr               9.9%     Mar 2026
                                                                        India’s largest online platform for insurance


                                        General Insurance Corporation   General Insurance Corporation of India is engaged
 Reinsurance                                                                                                                      ₹52,986 cr             18.2%      Mar 2026
                                        of India                        in the business of Reinsurance

Each of these layers has 2 member companies or fewer, so it has no median, range or ranking (a median is of 3 or more) and no page of its own.
"""


def test_layer_words_reads_the_layers_concept_in_the_printed_line():
    """The live R60 Insurance deck p.11: "Distribution and aggregation" over PB Fintech's printed "India's largest online platform for insurance"
    (the placement's own concept of insurance distribution, r60 rule 2) was a "layer words" FAIL."""
    import deck_check as K
    got = K.check_text(INSURANCE_P11)
    assert got["counts"]["layer words"] == 0
    # (a printed line that says neither the name nor the concept still fails)
    bad = INSURANCE_P11.replace("India’s largest online platform for insurance", "India’s largest maker of steel pipes and tubes")
    bad = bad.replace("PB Fintech Ltd, popularly known as Policy Bazar is", "Acme Pipes Ltd, a company that is")
    assert K.check_text(bad)["counts"]["layer words"] == 1


CASINOS_NOTE = """HOTELS AND CASINOS · APPENDIX


Every company's figures (1 of 3)

 Company                                   Layer                                   Market value     Revenue       Growth      EBITDA          Net
 Marriott International Inc                Hotel franchisors and managers            $109.6 bn      $26.2 bn       +4.3%       16.4%         9.9%

Latest full year. Revenue growth above 100% either
way, or from a base under 5% of the median company's, with its base: Hotel101 Global Holdings Corp. +1177.3%, from $6 m to $76 m; Hi-Great Group
Holding Co −42.9%, from $0 m to $0 m.
"""


def test_outlier_range_never_reads_a_growth_printed_with_its_base():
    """The live R60 Hotels and casinos deck pp.38-40: the note "... with its base: Hotel101 +1177.3%, from $6 m to $76 m" read as a range for
    its word "median"; a range's own end beyond ±1,000% still fails."""
    import deck_check as K
    assert K.check_text(CASINOS_NOTE)["counts"]["outlier range"] == 0
    rng = CASINOS_NOTE + "\n Range                    −2.1% to 45.2%        12.5% to 6588.1%\n"
    assert K.check_text(rng)["counts"]["outlier range"] == 1


# ---------- P0 3: a lender's NII / assets ----------
def test_nii_assets_beyond_half_of_assets_is_not_meaningful():
    """The live R60 Non-bank lenders deck: "NII / assets 6588.1%", 157.6%, 486.6% and a range "12.5% to 6588.1%"."""
    from app import deck
    from app.intel import theme_data as D
    c = {"symbol": "X", "name": "X", "nii_assets": 6588.1, "net": 0.1, "revenue": 8273.0}
    assert D.in_median(c, "nii_assets") is None
    assert deck.not_meaningful(c, "nii_assets") and deck.co_cell(c, "nii_assets", str) == deck.NM
    ok = {**c, "nii_assets": 8.6}
    assert D.in_median(ok, "nii_assets") == 8.6 and deck.co_cell(ok, "nii_assets", str) == "8.6%"


# ---------- 7: an addition outside the figures says why ----------
def test_a_member_added_outside_the_figures_says_why():
    """The live R60 Biotech deck: "added 3: Genenta Science S.p.A., Vicore Pharma Holding AB, Windward Bio Group AG" with no reason."""
    from app.intel import theme_changes as T
    dive = {"layers": [{"layer": "Big", "companies": [{"symbol": "A", "name": "A Co", "revenue": 10, "year": "2025"}]}]}
    was = T.snapshot(dive, ["A"], 1, 63, everyone={"A": ["A Co", "Big"]})
    c = {"ticker": "G", "name": "Genenta", "basis": "industry", "industry": "Biological Products", "verified": False, "what": ""}
    now = T.snapshot(dive, ["A", "G"], 1, 64, everyone={"A": ["A Co", "Big"], "G": ["Genenta", "Specialty", T.member_why(c, "Specialty")]})
    d = T.diff(was, now)
    assert [x["symbol"] for x in d["added"]] == ["G"]
    assert d["added"][0]["why"].startswith("filed under its official industry, Biological Products, one of the theme's")
    assert "not checked yet" in d["added"][0]["why"]
    stored = T.apply({"snap": was, "log": []}, now)
    assert "rest_why" not in stored["snap"]                    # read for the entry's reasons, never stored
    assert T.member_why({"basis": "ai", "verified": True}, "Other") == "the theme's map places it in “Other”"


# ---------- 7: a one-company layer prints the sentence that says it ----------
def test_a_line_that_says_the_layer_with_cater_to_is_its_line():
    """The live R60 Homebuilders deck: Toll Brothers in "Luxury and custom homebuilding" printed "In recent years, we have pursued a strategy of
    broadening our product lines", its "We cater to luxury first-time ... buyers" read as no work."""
    from app.intel import theme_base as B
    about = ("In recent years, we have pursued a strategy of broadening our product lines, price points and geographic footprint. We cater to "
             "luxury first-time, move-up, empty-nester (move-down), active-adult and second-home buyers in the United States.")
    line = B.layer_line("In recent years, we have pursued a strategy of broadening our product lines, price points", about, "Toll Brothers, Inc.",
                        "Luxury and custom homebuilding")
    assert "luxury" in line.lower()


# ---------- 7: the same company under two symbols ----------
def test_a_subsidiary_with_its_parents_description_and_figures_is_kept_once_under_the_parent():
    """The live R60 Electric utilities deck: "Southern Co and Georgia Power Co: $29.6 bn · +10.4% · 45.1% · 14.7%"."""
    from app.intel.theme_data import same_company
    t = ("Southern Company is a holding company that owns all of the outstanding common stock of three traditional electric operating "
         "companies. The traditional electric operating companies – Alabama Power, Georgia Power, and Mississippi Power – are each vertically "
         "integrated utilities.")
    rows = [{"symbol": "SO", "name": "Southern Co", "year": "2025", "revenue": 29553.0, "profit": 4344.3, "cap": 106687.0},
            {"symbol": "GPJA", "name": "Georgia Power Co", "year": "2025", "revenue": 29553.0, "profit": 4344.3, "cap": 19757.0},
            {"symbol": "X", "name": "Other Utility", "year": "2025", "revenue": 120.0, "profit": 9.0}]
    assert same_company(rows, about=lambda s: t if s in ("SO", "GPJA") else "Other Utility runs a gas network in one state.") == {"GPJA": "SO"}
    # (two companies with different descriptions and the same figures are not merged by this rule)
    assert same_company(rows, about=lambda s: {"SO": t, "GPJA": "Georgia Power is an electric utility serving Georgia customers."}.get(s, "")) == {}


# ---------- gate: a company never moved into a layer on no word of its own ----------
def test_a_company_moved_into_a_layer_its_words_industry_and_name_never_say_stays_where_it_is_published():
    """The R62 replays of the live R60 inputs: Tahmar Enterprises, published in "Other", put into "Spirits brand owning and bottling" by how it
    earns; Naga Dhunseri, an investment company, into "Microfinance and small-ticket lenders" (release_gate "layer words ... moved in")."""
    from app.intel import theme_base as B
    rest = {"layer": "Other drinks companies", "official": True, "basis": "rest", "companies": []}
    co = lambda t, n, i="Breweries & Distilleries": {"ticker": t, "name": n, "industry": i, "placed": "ai"}     # noqa: E731
    lay = {"layer": "Spirits brand owning and bottling (smaller)", "scale": "smaller",
           "companies": [co("A", "A Spirits"), co("B", "B Bottlers"), co("C", "C Brands"), co("T", "Tahmar Enterprises Ltd", "Distilleries")]}
    words = {"A": "A makes and bottles spirits brands.", "B": "B bottles whisky and rum brands it owns.",
             "C": "C owns spirits brands.", "T": "Tahmar is in the business of Manufacture of Extra Neutral Alcohol and pharma grade solvents."}
    vc, rows = B.listed_out([lay, rest], words.get, "Alcoholic beverages", {}, None,
                            {"A": "Spirits brand owning and bottling", "B": "Spirits brand owning and bottling", "C": "Spirits brand owning and bottling",
                             "T": "Other drinks companies"})
    assert [c["ticker"] for c in rest["companies"]] == ["T"] and [r["ticker"] for r in rows] == ["T"]
    assert "say no word of “Spirits brand owning and bottling”" in rows[0]["why"]
    assert B.gate_says("Spirits brand owning and bottling", words["A"]) and B.gate_says("Components and chips", "an American semiconductor company")


# ---------- P1 5: a domestic filer is never a foreign banking group ----------
def test_a_us_domestic_filer_leaves_a_layer_of_foreign_banking_groups():
    """The owner's review of the live R60 Regional banks deck: Capital One under "Foreign banking groups earning loan interest"."""
    from app.intel import theme_base as B
    foreign = {"layer": "Foreign banking groups earning loan interest", "description": "Large non-US banking groups that lend.",
               "companies": [{"ticker": "HSBC", "name": "HSBC", "industry": "Commercial Banks, Nec", "cap": 200000},
                             {"ticker": "RY", "name": "Royal Bank of Canada", "industry": "Commercial Banks, Nec", "cap": 180000},
                             {"ticker": "COF", "name": "Capital One Financial Corp", "industry": "National Commercial Banks", "cap": 116000}]}
    big = {"layer": "Large national banks", "companies": [{"ticker": "JPM", "industry": "National Commercial Banks", "cap": 800000},
                                                          {"ticker": "C", "industry": "National Commercial Banks", "cap": 150000}]}
    small = {"layer": "Small community banks", "companies": [{"ticker": "S1", "industry": "National Commercial Banks", "cap": 300},
                                                             {"ticker": "S2", "industry": "National Commercial Banks", "cap": 500}]}
    rest = {"layer": "Other banks", "official": True, "basis": "rest", "companies": []}
    filings = {"HSBC": "From its own filings: Annual report (20-F).", "RY": "From its own filings: Annual report (40-F).",
               "COF": "From its own filings: Quarterly report (10-Q). Earnings release (8-K)."}
    vc, rows = B.domicile_moves([foreign, big, small, rest], lambda s: {"filings": filings.get(s, "")})
    assert [c["ticker"] for c in foreign["companies"]] == ["HSBC", "RY"]
    assert [c["ticker"] for c in big["companies"]][-1] == "COF" and rows[0]["to"] == "Large national banks"
    assert "domestic filer's (10-Q, 8-K)" in rows[0]["why"]


# ---------- "retail customers" ----------
def test_retail_customers_name_whom_a_company_sells_to_never_a_retailers_way_of_earning():
    """The live R60 Electric utilities deck: Southern's "providing electric service to retail customers" read as a retailer, so the theme's largest
    company was left out of its layer as insufficient evidence."""
    from app.intel.theme_check import words_models
    assert "retail" not in words_models("The operating companies are vertically integrated utilities providing electric service to retail customers.")
    assert "retail" in words_models("Acme operates 300 retail stores selling apparel to retail customers.")


# ---------- P1 6: utilities' operating models ----------
def test_regulated_merchant_and_equipment_layers_are_never_ranked_together():
    """The owner's review of the live R60 Electric utilities deck, P1."""
    from app.intel import theme_data as D
    assert D.operating_model("Regulated vertically integrated utilities") == "regulated"
    assert D.operating_model("Transmission and distribution utilities") == "regulated"
    assert D.operating_model("Competitive power generation") == "merchant"
    assert D.operating_model("Grid and power equipment makers") == "equipment"
    assert D.operating_model("Utility and grid construction contractors") == "contracting"
    assert D.operating_model("Construction chemicals") == "" and D.operating_model("Branded packaged foods makers") == "branded"
    rows = ["Regulated vertically integrated utilities", "Transmission and distribution utilities", "Competitive power generation",
            "Grid and power equipment makers", "Renewable-focused integrated utilities"]
    got = D.one_operating(rows, lambda r: {"operating": D.operating_model(r)})
    assert got == ["Regulated vertically integrated utilities", "Transmission and distribution utilities", "Renewable-focused integrated utilities"]


# ---------- P0 1: core farm inputs before layers ----------
def test_farm_inputs_are_the_core_of_a_fertilizers_theme_and_chemical_suppliers_are_not():
    """The owner's review of the live R60 Fertilizers and agrochemicals deck, P0: Pidilite (adhesives), industrial gases and commodity
    petrochemicals counted with the farm-input makers."""
    from app.intel import theme_data as D
    kind = D.theme_kind("Fertilizers and agrochemicals")
    assert kind == "fertiliser and crop-protection makers"
    pid = {"name": "Pidilite Industries Ltd", "industry": "Specialty Chemicals"}
    a = D.adjacent_of(pid, kind, "Pidilite Industries Ltd is a manufacturer of adhesives and sealants, construction chemicals and art materials.")
    assert a["kind"] == "specialty and industrial chemical makers" and a.get("unrelated")
    gas = D.adjacent_of({"name": "Linde India Ltd", "industry": "Industrial Gases"}, kind, "Linde India makes industrial gases for steel plants.")
    assert gas["kind"] == "industrial gas makers" and gas.get("unrelated")
    petro = D.adjacent_of({"name": "SRF Ltd", "industry": "Commodity Chemicals"}, kind,
                          "SRF makes refrigerants, packaging films and fluorochemicals, among them intermediates for agrochemicals.")
    assert petro["kind"] == "commodity chemical and petrochemical makers" and not petro.get("unrelated")       # a supplier: adjacent
    assert D.adjacent_of({"name": "UPL Ltd", "industry": "Pesticides & Agrochemicals"}, kind, "UPL makes crop protection products.") is None
    assert D.adjacent_of({"name": "National Fertilizers Ltd", "industry": "Commodity Chemicals"}, kind, "It makes urea.") is None
    # (a Chemicals theme's name states no kind: its agrochemical makers are never adjacent there)
    assert D.theme_kind("Chemicals") == ""
    row = D.adjacent_said(a)
    assert row.startswith("outside the theme's core business (specialty and industrial chemical makers")


def test_the_core_and_adjacent_row_says_who_is_outside_the_core_business():
    from app import deck
    v = {"core_kind": "fertiliser and crop-protection makers",
         "adjacent": [{"symbol": "P", "name": "Pidilite Industries Ltd", "kind": "specialty and industrial chemical makers", "unrelated": True},
                      {"symbol": "S", "name": "SRF Ltd", "kind": "commodity chemical and petrochemical makers"}]}
    row = deck.adjacent_row(v)
    assert "1 company whose principal business is another kind are adjacent participants: commodity chemical and petrochemical makers 1 (SRF Ltd)" in row[1]
    assert "outside the theme's core business: specialty and industrial chemical makers 1 (Pidilite Industries Ltd)" in row[1]


# ---------- P0 2: provisional members ----------
def test_members_not_checked_yet_are_said_provisional_in_the_counts():
    """The owner's review of the live R60 Non-bank lenders deck: 126 not checked yet 295 in informative layers."""
    from app import deck
    assert deck.provisional_words(125) == "; 125 of them provisional: not yet checked against their own descriptions"
    assert deck.provisional_words(1) == "; 1 of them provisional: not yet checked against its own description" and deck.provisional_words(0) == ""
    v = {"evidence": {"A": "description_verified", "B": "industry_code_supported"},
         "membership_evidence": {"description_verified": 1, "industry_code_supported": 1},
         "members": [{"symbol": s, "layer": "L"} for s in ("A", "B", "C", "D")]}
    got = deck.informative_mix(v, 4)
    assert got.endswith("2 not checked; 2 of them provisional: not yet checked against their own descriptions")


# ---------- P0 3: sector metric schemas ----------
def test_a_reits_ffo_affo_and_p_ffo_from_its_filed_lines():
    """The owner's review of the live R60 REITs deck: no FFO or AFFO."""
    from app.intel import sector_metrics as S
    y = lambda v: [_fy("2025-12-31", "2025-01-01", v)]       # noqa: E731
    facts = {"us-gaap": {"Revenues": {"units": {"USD": y(4000e6)}}, "NetIncomeLoss": {"units": {"USD": y(1000e6)}},
                         "RealEstateInvestmentPropertyNet": {"units": {"USD": [_at("2025-12-31", 30000e6)]}},
                         "DepreciationDepletionAndAmortization": {"units": {"USD": y(1200e6)}},
                         "GainsLossesOnSalesOfInvestmentRealEstate": {"units": {"USD": y(200e6)}},
                         "PaymentsForCapitalImprovements": {"units": {"USD": y(300e6)}}}}
    got = S.us_figures(facts)
    assert got["ffo"]["v"] == 2000.0 and got["ffo_share"]["v"] == 50.0
    assert got["affo"]["v"] == 1700.0 and got["affo_share"]["v"] == 42.5
    assert "net income 1,000.0 + depreciation and amortisation 1,200.0 − gains on property sales 200.0" in got["ffo"]["source"]
    row = {"cap": 40000.0}
    S.apply(row, {"family": "us", "metrics": got, "end": "2025-12-31"})
    assert row["p_ffo"] == 20.0
    # a company with no real-estate property filed has no FFO; AFFO without its recurring capital spending is not filed
    del facts["us-gaap"]["PaymentsForCapitalImprovements"]
    assert "affo" not in S.us_figures(facts)
    del facts["us-gaap"]["RealEstateInvestmentPropertyNet"]
    assert "ffo" not in S.us_figures(facts)


def test_a_pc_insurers_loss_expense_and_combined_ratios_from_its_filed_lines():
    """The owner's review of the live R60 Property and casualty insurance deck: no loss or combined ratios."""
    from app.intel import sector_metrics as S
    y = lambda v: [_fy("2025-12-31", "2025-01-01", v)]       # noqa: E731
    facts = {"us-gaap": {"Revenues": {"units": {"USD": y(12000e6)}}, "PremiumsEarnedNet": {"units": {"USD": y(10000e6)}},
                         "PolicyholderBenefitsAndClaimsIncurredNet": {"units": {"USD": y(6500e6)}},
                         "DeferredPolicyAcquisitionCostAmortizationExpense": {"units": {"USD": y(1800e6)}},
                         "OtherUnderwritingExpense": {"units": {"USD": y(1100e6)}},
                         "ShareBasedCompensation": {"units": {"USD": y(50e6)}}}}
    got = S.us_figures(facts)
    assert (got["loss_ratio"]["v"], got["expense_ratio"]["v"], got["combined_ratio"]["v"]) == (65.0, 29.0, 94.0)
    assert "sbc_share" not in got                                # an insurer's stock pay says nothing of how it underwrites
    assert S.family_of("US", {"profile": "insurer"}) == "us"
    from app import deck
    assert [c[0] for c in deck.co_cols([{"loss_ratio": 65.0, "combined_ratio": 94.0, "profile": "insurer", "bank": True}])
            if c[0] in ("loss_ratio", "combined_ratio")] == ["loss_ratio", "combined_ratio"]


def test_a_banks_revenue_basis_is_printed_under_the_table_of_its_figure():
    """The owner's review of the live R60 Regional banks deck: Huntington's $8.17 bn against $8.231 bn, "a stated basis visible in the deck"."""
    from app import deck
    hban = {"symbol": "HBAN", "name": "Huntington Bancshares Inc", "revenue": 8166.0, "cap": 25000.0,
            "revenue_basis": {"key": "bank_nii", "words": "net interest income plus noninterest income, as filed", "standard": "US GAAP", "fte": False,
                              "lines": [{"line": "net interest income", "value": 5991.0}, {"line": "noninterest income", "value": 2175.0}]}}
    got = deck.basis_line([hban])
    assert got.startswith("Revenue, as each company files it: net interest income plus noninterest income, as filed (US GAAP): all 1")
    assert "not on the fully taxable-equivalent (FTE) basis" in got
    assert "Huntington Bancshares Inc: net interest income $5,991 m + noninterest income $2,175 m = $8,166 m" in got
    assert deck.basis_line([{"symbol": "X", "revenue": 1.0}]) == ""


# ---------- P1 4: the sources of the companies add up ----------
def test_the_universe_line_names_every_source_so_the_counts_add_up():
    """The owner's review of the live R60 Homebuilders deck: "38 companies (29 in the exchange's industry list, 6 added by the AI)"."""
    from app import deck
    v = {"placements": {"base": 29, "named": 0, "added": 6},
         "members": [{"symbol": s, "name": n, "source": "words"} for s, n in (("TPH", "Tri Pointe Homes, Inc."), ("MHK", "Mohawk Industries Inc"),
                                                                              ("BLDR", "Builders FirstSource, Inc."))]}
    got = deck.membership_words(v, 38)
    assert got.startswith("38 companies (29 in the exchange's industry list, 6 added by the AI, 3 kept on their own words from other industries (Tri Pointe")
    assert "Mohawk Industries" in got and "Builders FirstSource" in got


# ---------- LIVE10A (the live review of R61), the theme engine's part ----------
def test_cut_markup_ranked_or_another_companys_text_is_never_printed_as_own_words():
    """LIVE10A-004: Ambuja "is among the leading cement companies in India", Shree "…is ** one of the lowest cost producers", ASML "…industry
    and", Arteris "particularl”", Intel's Fortune 500 ranking, TOYO Co. quoted with Toyo Tire's words."""
    from app.intel.theme_base import own_words, other_subject
    bad = [("is among the leading cement companies in India", "Ambuja Cements Ltd"),
           ("…is ** one of the lowest cost producers of cement", "Shree Cement Ltd"),
           ("ASML makes lithography systems for the semiconductor industry and", "ASML Holding NV"),
           ("Arteris provides interconnect IP, particularl”", "Arteris Inc"),
           ("Intel is the third-largest semiconductor company by revenue in 2024 and ranks in the Fortune 500", "Intel Corp"),
           ("Toyo Tire Corporation is a Japanese company that manufactures tires", "TOYO Co., Ltd."),
           ("Created by the divestiture of AMD's manufacturing arm, it makes chips", "GlobalFoundries Inc"),
           ("From our inception through the third quarter of 1994, we developed products", "Metalink Ltd")]
    assert [own_words(t, n) for t, n in bad] == [""] * len(bad)
    good = [("Bajaj Auto Limited is a manufacturer of motorcycles", "Bajaj Auto Ltd"),
            ("Mahindra & Mahindra manufactures tractors and utility vehicles", "Mahindra & Mahindra Ltd"),
            ("HDFC Bank Limited is a bank providing loans", "HDFC Bank Ltd"),
            ("Shree Cement is one of the lowest cost producers of cement in India.", "Shree Cement Ltd"),
            ("“Arteris provides interconnect IP to chip makers”", "Arteris Inc")]
    assert all(own_words(t, n) for t, n in good)
    assert other_subject("Tata Steel Limited is a steel maker", "Tata Motors Ltd") and not other_subject("Tata Motors Limited makes cars", "Tata Motors Ltd")


def test_a_sub_theme_with_no_company_takes_the_layer_its_name_maps_to():
    """LIVE10A-009: the live Automotive page "No listed company is shown for these sub-themes: Vehicle assembly, Two-wheelers and
    three-wheelers, Components and systems" beside Maruti, Bajaj and Bosch."""
    from app.intel.theme_data import sub_picked
    lay = [{"layer": "Passenger and commercial vehicle makers (larger)", "companies": [{"ticker": "MARUTI"}]},
           {"layer": "Passenger and commercial vehicle makers (smaller)", "companies": [{"ticker": "FORCE"}]},
           {"layer": "Two-wheeler and three-wheeler makers", "companies": [{"ticker": "BAJAJ"}]},
           {"layer": "Component and systems suppliers", "companies": [{"ticker": "BOSCH"}]}]
    got = {n: [c["ticker"] for c in sub_picked({"name": n, "companies": []}, lay, lambda s: "its own words")]
           for n in ("Vehicle assembly", "Two-wheelers and three-wheelers", "Components and systems", "Electric buses")}
    assert got == {"Vehicle assembly": ["MARUTI", "FORCE"], "Two-wheelers and three-wheelers": ["BAJAJ"], "Components and systems": ["BOSCH"],
                   "Electric buses": []}


def test_the_companies_csv_prints_a_margin_beyond_revenue_as_nm():
    """LIVE10A-018: Atomera "−32423.1%" printed as a margin outside the deck."""
    from app.intel import theme_routes as TR
    m = {"sector": "Semiconductors", "value_chain": [{"layer": "Makers", "companies": [{"ticker": "ATOM", "name": "Atomera Inc"},
                                                                                        {"ticker": "TXN", "name": "Texas Instruments"}]}]}
    dive = {"layers": [{"layer": "Makers", "companies": [{"symbol": "ATOM", "name": "Atomera Inc", "revenue": 0.07, "ebitda": -32423.1, "net": -30000.0},
                                                         {"symbol": "TXN", "name": "Texas Instruments", "revenue": 17000.0, "ebitda": 45.0, "net": 30.0}]}]}
    body = TR.companies_csv(m, dive, "US").decode("utf-8")
    atom = next(ln for ln in body.splitlines() if ln.startswith("Atomera"))
    txn = next(ln for ln in body.splitlines() if ln.startswith("Texas"))
    assert "n.m.,n.m." in atom and "-32423" not in atom and ",45.0,30.0," in txn


def test_two_listings_of_one_company_are_kept_once_under_the_one_with_words():
    """The R62 replay of the live R60 Electric utilities input: "Brookfield Renewable Partners L.P" in a layer's calculations and "Brookfield
    Renewable" (Brookfield Renewable Corp, no description of its own) left out of it in one sentence."""
    from app.intel.theme_data import same_company
    rows = [{"symbol": "BEP", "name": "Brookfield Renewable Partners L.P.", "year": "2025", "revenue": 6407.0, "profit": -70.0},
            {"symbol": "BEPC", "name": "Brookfield Renewable Corp", "year": "2025", "revenue": 3728.0, "profit": -2300.0},
            {"symbol": "BAM", "name": "Brookfield Asset Management", "year": "2025", "revenue": 10.0, "profit": 1.0}]
    words = {"BEP": "Brookfield Renewable operates hydro, wind and solar plants.", "BAM": "Brookfield Asset Management manages funds for clients."}
    assert same_company(rows, about=lambda s: words.get(s, "")) == {"BEPC": "BEP"}
