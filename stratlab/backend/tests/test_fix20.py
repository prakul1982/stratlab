"""Lane fix20: R70 engine touch-ups from the live R75 decks.

1. An adjacent kind that is no kind of business said as what it is: "most of its companies' principal business is of listed in the US,
   based abroad" (US Oil and gas, US Telecom) and its like in the dive, the core-and-adjacent row, the layer rolls and the change log.
2. Exxon (owner decision, 18 Nov: "Exxon Mobil Corporation"): the theme member, deck and stock page use the reporting registrant's name.
3. US names with filing artefacts: "Southern Copper Corp/", "Ati" (ATI Inc), "Freeport-Mcmoran", "America Movil Sab De CV/".
4. A figure the filings have that was not read: Metallus' EBITDA margin (no operating profit line, interest as InterestExpenseOperating).
5. deck_diff's "layer words" on Oriental Trimex: supplying imported goods states the way of earning of a distribution and trading layer.
"""
import pathlib
import sys

from app import deck, stock_pages
from app.intel import grounding, sec
from app.intel import theme_changes as C
from app.intel import theme_data as D
from tests.test_sec_live_samples import _xom_transport
from tests.test_sec_us_audit_oct6 import _facts, _yr

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import release_gate as G  # noqa: E402

FOREIGN = {"kind": D.FOREIGN_KIND, "theme": "companies based in the US", "where": "filing",
           "text": "files its annual report with the SEC on Form 20-F, a foreign issuer's report"}
HOLDING = {"kind": D.HOLDING_KIND, "theme": "own business (Automobiles)", "where": "holding",
           "text": "holds 52.5% of M&M Financial, a member of the theme, and its figures are the whole company's"}


# ---------- 1. the adjacent kinds no business is of ----------
def test_fix20_an_adjacent_layer_of_companies_based_abroad_reads_as_a_sentence():
    """Fails before: the US Oil and gas layer card printed "most of its companies' principal business is of listed in the US, based
    abroad, not of the theme's companies based in the US"."""
    said = D.adjacent_layer_said(FOREIGN)
    assert said == ("most of its companies are listed in the US but based abroad (a foreign issuer's annual report, 20-F or 40-F), apart "
                    "from the theme's US companies")
    assert "is of listed" not in said
    held = D.adjacent_layer_said(HOLDING)
    assert held.startswith("most of its companies are holding companies of other members of the theme") and "principal business" not in held
    other = D.adjacent_layer_said({"kind": "lenders and financiers", "theme": "own business (Payments and fintech)"})
    assert other == "most of its companies' principal business is of lenders and financiers, not of the theme's own business (Payments and fintech)"


def test_fix20_a_company_based_abroad_is_said_as_one_in_the_dive_roll_and_comparison():
    """Fails before: "its principal business (its official industry, “files its annual report with the SEC on Form 20-F...”) is of listed
    in the US, based abroad" (US Telecom coverage), and "adjacent participant, another kind of business than the theme's: BHP Group, Rio
    Tinto and 20 more" (US Steel and metals p.15)."""
    said = D.adjacent_said(FOREIGN)
    assert said.startswith("in the theme as an adjacent participant (listed in the US, based abroad); not in its core statistics because it "
                           "is listed in the US but based abroad: it files its annual report with the SEC on Form 20-F")
    assert "principal business" not in said and "is of listed" not in said and "official industry" not in said
    held = D.adjacent_said(HOLDING)
    assert held.startswith("in the theme as an adjacent participant (holding companies of other members)")       # x57's own words kept
    assert "is a holding company of other members of the theme" in held and "is of holding companies" not in held
    rec = D.calc_record({"symbol": "BHP", "model_out": "other", "out_why": "adjacent", "adjacent": FOREIGN, "revenue": 50.0, "profit": 5.0})
    assert rec["label"] == "adjacent participant, listed in the US but based abroad" and rec.get("abroad") and not rec["in"]
    assert D.comparison_said(rec, {}) .startswith("listed in its layer, left out of its figures: in the theme as an adjacent participant")
    lend = D.calc_record({"symbol": "COF", "model_out": "other", "out_why": "adjacent", "revenue": 1.0, "profit": 0.1,
                          "adjacent": {"kind": "lenders and financiers", "theme": "x", "where": "industry", "text": "Banks"}})
    assert lend["label"] == "adjacent participant, another kind of business than the theme's" and "abroad" not in lend
    assert D.calc_record({"symbol": "M", "model_out": "other", "out_why": "adjacent", "adjacent": HOLDING, "revenue": 1.0,
                          "profit": 0.1})["label"] == "adjacent participant, a holding company of other members"


def test_fix20_the_core_and_adjacent_row_names_companies_based_abroad_as_such():
    """Fails before (live R75 Restaurants): "8 companies whose principal business is another kind are adjacent participants: listed in the
    US, based abroad 8 (Luckin Coffee Inc., ...)"."""
    v = {"core_kind": "restaurant operators",
         "adjacent": [{"symbol": "LKNCY", "name": "Luckin Coffee Inc.", **FOREIGN}, {"symbol": "CHA", "name": "Chagee Holdings Ltd.", **FOREIGN},
                      {"symbol": "S", "name": "SRF Ltd", "kind": "commodity chemical and petrochemical makers"}]}
    row = deck.adjacent_row(v)
    assert ("2 companies listed in the US but based abroad (a foreign issuer's annual report, 20-F or 40-F) are adjacent participants "
            "(Luckin Coffee Inc., Chagee Holdings Ltd.)") in row[1]
    assert "1 company whose principal business is another kind are adjacent participants: commodity chemical and petrochemical makers 1 (SRF Ltd)" in row[1]
    assert "based abroad 2" not in row[1] and "listed in the US, based abroad" not in row[1]
    one = deck.adjacent_row({"core_kind": "x", "adjacent": [{"symbol": "L", "name": "Luckin Coffee Inc.", **FOREIGN}]})
    assert "1 company listed in the US but based abroad (a foreign issuer's annual report, 20-F or 40-F) is an adjacent participant" in one[1]
    assert one[2].startswith("Shown, with their layer, as adjacent")


def test_fix20_an_adjacent_layer_based_abroad_is_not_ranked_as_another_kind_of_business():
    assert D.RANK_WHY["abroad"] == "adjacent participants, listed in the US but based abroad"
    assert D.RANK_WHY["adjacent"] == "adjacent participants, another kind of business than the theme's"


def test_fix20_a_company_now_based_abroad_leaves_the_core_with_what_it_is():
    """Fails before: the change log's reason "its principal business (its official industry, “files ... Form 20-F ...”) is of listed in
    the US, based abroad"."""
    def dive(adj):
        cos = [{"symbol": "HSBC", "name": "HSBC Holdings plc", "revenue": 100.0, "ebitda": 10.0, "year": "Dec 2025"},
               {"symbol": "JPM", "name": "JPMorgan Chase & Co", "revenue": 100.0, "ebitda": 10.0, "year": "Dec 2025"}]
        return {"layers": [{"layer": "Banks", "companies": cos}], "population_rule": D.POPULATION,
                "adjacent": [{"symbol": "HSBC", "name": "HSBC Holdings plc", **FOREIGN}] if adj else []}
    pc = C.population_change(C.snapshot(dive(False)), dive(True))
    why = pc["left"][0]["why"]
    assert why.startswith("it is listed in the US but based abroad: it files its annual report with the SEC on Form 20-F") and "is of" not in why


# ---------- 2. Exxon Mobil Corporation ----------
def test_fix20_exxon_is_named_as_its_reporting_registrant_in_the_page_and_the_theme():
    """Fails before: the R75 US Oil and gas deck printed "ExxonMobil Holdings Corp": the theme took the map's listed name over its page's,
    and the page kept no record that its name is the reporting registrant's."""
    p = sec.SEC(transport=_xom_transport([])).company("XOM")
    f = stock_pages.facts("US", "XOM", p, {"years": []}, {}, None, None, [], "NYSE")
    assert f["name"] == "Exxon Mobil Corporation" and f["registrant"] == "ExxonMobil Holdings Corp"
    assert D.member_name("US", "XOM", "ExxonMobil Holdings Corp", f["name"], f) == "Exxon Mobil Corporation"
    # a page without a reporting registrant keeps the map's listed name where the two differ (as before)
    assert D.member_name("US", "GOOGL", "Alphabet Inc.", "Alphabet Inc Class A", {"name": "Alphabet Inc Class A"}) == "Alphabet Inc."
    assert D.member_name("IN", "TCS", "Tata Consultancy Services Ltd", "TCS", {}) == "Tata Consultancy Services Ltd"
    assert "registrant" not in stock_pages.facts("US", "AAPL", {"name": "Apple Inc."}, {"years": []}, {}, None, None, [], "Nasdaq")


# ---------- 3. filing artefacts in US names ----------
def test_fix20_a_lone_trailing_slash_and_title_cased_letters_are_fixed_at_the_source():
    """Fails before: "Southern Copper Corp/", "Ati Inc", "Freeport-Mcmoran Inc", "America Movil Sab De CV/", "Bok Financial Corp",
    "Nov Inc.", "Equinor Asa", "Gatx Corp" from the SEC's names."""
    assert stock_pages.strip_registration("SOUTHERN COPPER CORP/") == "SOUTHERN COPPER CORP"
    assert stock_pages.strip_registration("APPLIED MATERIALS INC /DE/") == "APPLIED MATERIALS INC"
    cases = {("SOUTHERN COPPER CORP/", "SCCO"): "Southern Copper Corp", ("ATI INC", "ATI"): "ATI Inc",
             ("FREEPORT-MCMORAN INC", "FCX"): "Freeport-McMoRan Inc", ("AMERICA MOVIL SAB DE CV/", "AMX"): "America Movil SAB de CV",
             ("BOK FINANCIAL CORP", "BOKF"): "BOK Financial Corp", ("NOV Inc.", "NOV"): "NOV Inc.", ("APA Corp", "APA"): "APA Corp",
             ("EQUINOR ASA", "EQNR"): "Equinor ASA", ("ENI SPA", "E"): "Eni SpA", ("GATX CORP", "GATX"): "GATX Corp", ("EOG RESOURCES INC", "EOG"): "EOG Resources Inc",
             ("OGE ENERGY CORP.", "OGE"): "OGE Energy Corp.", ("MYR GROUP INC.", "MYRG"): "MYR Group Inc.", ("SES AI Corp", "SES"): "SES AI Corp",
             # words stay words, and a name the old rules had right stays right
             ("GAP INC", "GAP"): "Gap Inc", ("SNAP INC", "SNAP"): "Snap Inc", ("ELI LILLY & Co", "LLY"): "Eli Lilly & Co",
             ("MICROSOFT CORP", "MSFT"): "Microsoft Corp", ("COSTCO WHOLESALE CORP /NEW", "COST"): "Costco Wholesale Corp",
             ("NWPX Infrastructure, Inc.", "NWPX"): "NWPX Infrastructure, Inc.", ("BEL FUSE INC /NJ", "BELFB"): "Bel Fuse Inc"}
    for (name, sym), want in cases.items():
        assert stock_pages.proper_name(name, sym) == want, (name, stock_pages.proper_name(name, sym))
    assert stock_pages.proper_name("ATI INC") == "Ati Inc"            # (with no symbol, three letters with a vowel between read as a word)
    assert grounding.listed_name("ATI INC", "ATI", "ATI") == "ATI Inc"


def test_fix20_the_theme_and_the_deck_agree_on_a_us_members_name():
    """A map stored before the fix keeps "Ati Inc" and "Southern Copper Corp/": the theme names the member from its page's own name, tidied
    the same way, and the deck takes a lone trailing "/" out of any name it prints."""
    assert D.member_name("US", "ATI", "Ati Inc", "ATI INC", {"name": "ATI INC"}) == "ATI Inc"
    assert D.member_name("US", "SCCO", "Southern Copper Corp/", "SOUTHERN COPPER CORP/", {}) == "Southern Copper Corp"
    assert D.member_name("US", "FCX", "Freeport-Mcmoran Inc", "FREEPORT-MCMORAN INC", {}) == "Freeport-McMoRan Inc"
    assert D.member_name("US", "ORLY", "O'Reilly Automotive Inc", "O REILLY AUTOMOTIVE INC", {}) == "O'Reilly Automotive Inc"
    assert deck.clean_name("Southern Copper Corp/") == "Southern Copper Corp"
    assert deck.clean_name("America Movil Sab De CV/") == "America Movil Sab De CV"
    text, why = deck.tidy_text("In the layer: Southern Copper Corp/, Freeport-Mcmoran; Plywood Boards/ Laminates and/or more.")
    assert text == "In the layer: Southern Copper Corp, Freeport-Mcmoran; Plywood Boards/ Laminates and/or more." and why
    assert deck.tidy_text("Holding Company/ Investment Group")[0] == "Holding Company/ Investment Group"
    assert deck.tidy_text("Southern Copper Corp/ $13.4 bn")[0] == "Southern Copper Corp $13.4 bn"


# ---------- 4. a figure the filings have ----------
def test_fix20_an_ebitda_margin_with_interest_filed_as_operating_is_read():
    """Fails before: Metallus (live R75 US Steel and metals p.19, "EBITDA margin not stored"): no operating profit line, so EBIT is profit
    before tax plus interest, and its interest is filed as InterestExpenseOperating, which was not read."""
    us = _facts(RevenueFromContractWithCustomerExcludingAssessedTax=[_yr(2024, 1084.0), _yr(2025, 1158.3)],
                IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest=[_yr(2024, 4.0), _yr(2025, 1.9)],
                InterestExpenseOperating=[_yr(2024, 1.2), _yr(2025, 1.8)],
                DepreciationDepletionAndAmortization=[_yr(2024, 54.1), _yr(2025, 56.6)],
                NetIncomeLoss=[_yr(2024, 1.3), _yr(2025, -1.2)])
    p = sec.build({"cik": 1, "facts": {"us-gaap": us}}, {"cik": "1", "name": "Metallus Inc.", "sic": "3312",
                                                          "filings": {"recent": {"form": ["10-K"]}}})
    opm = dict(zip(p["pl"]["cols"], p["pl"]["rows"]["OPM %"]))
    assert opm["Dec 2025"] == 5.2 and opm["Dec 2024"] is not None
    # a lender's interest is its cost of sales, never added back
    bank = sec.build({"cik": 1, "facts": {"us-gaap": us}}, {"cik": "1", "name": "A Bank", "sic": "6022", "filings": {"recent": {"form": ["10-K"]}}})
    assert dict(zip(bank["pl"]["cols"], bank["pl"]["rows"].get("OPM %") or [None] * len(bank["pl"]["cols"]))).get("Dec 2025") != 5.2


# ---------- 5. supplying imported goods is trading ----------
def test_fix20_supplying_imported_goods_states_a_distribution_and_trading_layer():
    """Fails before: deck_diff failed the live R75 Building materials deck ("layer words") on Oriental Trimex, "in the business of supplying
    premium imported marbles", moved into "Distribution and trading". Under the placement contract a company that supplies goods it imports
    earns by trading goods others make."""
    layer = "Distribution and trading"
    assert G.shares(layer, "Oriental Trimex Ltd is in the business of supplying premium imported marbles. OTL is an ISO 9001:2000 certified")
    assert G.shares(layer, "A leading importer of tiles.") and G.shares(layer, "It imports and sells sanitaryware.")
    assert G.trade_said("Building products distributors", "supplies imported laminates")
    # what it makes, and a layer of no trade in goods, say nothing of it
    assert not G.shares(layer, "It cuts, resizes, and polishes raw marble blocks for customers")
    assert not G.trade_said("Stock broking and trading", "importers of goods") and not G.trade_said("Power distribution", "supplies imported coal")
    assert not G.trade_said("Cement manufacturing", "supplying imported clinker")


# ---------- the deck itself ----------
def _us_deck():
    """A US theme with mapped layers: one mostly of Form 20-F filers, and SEC names with filing artefacts (offline, no AI)."""
    from app.intel import theme_base as B
    from tests.test_export import texts
    from tests.test_r18_deck import deck_of, facts
    inds = ["Services-Prepackaged Software"] * 5 + ["Services-Computer Programming Services"] * 4 + ["Telephone Communications"]
    names = ["SAP SE", "OPEN TEXT CORP", "CHECK POINT SOFTWARE TECHNOLOGIES LTD", "NICE Ltd.", "WIX.COM LTD.", "SOUTHERN COPPER CORP/",
             "ATI INC", "FREEPORT-MCMORAN INC", "BOK FINANCIAL CORP", "AMERICA MOVIL SAB DE CV/"]
    syms = ["SAP", "OTEX", "CHKP", "NICE", "WIX", "SCCO", "ATI", "FCX", "BOKF", "AMX"]
    rows = [{"symbol": s, "name": n, "industry": ind, "market_cap": 100000 - i * 8000} for i, (s, n, ind) in enumerate(zip(syms, names, inds))]
    blank = {"sector": "Network defence", "summary": "", "core": "", "value_chain": [], "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 0}
    m = B.with_base(blank, {**blank, "placements": {"checked": True, "pending": 0}}, rows, sorted(set(inds)))
    m["value_chain"] = [{**v, "official": False, "basis": None, "description": f"Companies of {v['layer'].lower()}."} for v in m["value_chain"]]
    f = {}
    for i, r in enumerate(rows):
        f[r["symbol"]] = {**facts(r["symbol"], r["name"], [500, 600, 700, 800 + i * 20], [20.0, 21.0, 22.0, 18.0 + i], [50, 60, 70, 80 + i],
                                  cap=r["market_cap"], pe=40.0, industry=(r["industry"],)), "region": "US", "unit": "$ million"}
    for s in syms[:4] + ["AMX"]:
        f[s] = {**f[s], "annual_form": "20-F", "annual_filed": "2026-03-01"}
    v, slides = deck_of("US", m, f)
    return v, "\f".join(texts([s]) for s in slides)


def test_fix20_the_us_deck_says_its_layer_based_abroad_and_its_names_without_artefacts():
    """Fails before: "Adjacent participants: most of its companies' principal business is of listed in the US, based abroad, not of the
    theme's companies based in the US", and the members' SEC names printed with their artefacts."""
    v, text = _us_deck()
    flat = " ".join(text.split())
    assert "Adjacent participants: most of its companies are listed in the US but based abroad (a foreign issuer's annual report, 20-F or " \
           "40-F), apart from the theme's US companies" in flat
    assert "is of listed in the US" not in flat and "based abroad 5" not in flat
    assert deck.ADJACENT_NOTE_ABROAD in flat and deck.ADJACENT_NOTE not in flat
    names = {r["symbol"]: r["name"] for b in v["layers"] for r in b["companies"]}
    assert names["SCCO"] == "Southern Copper Corp" and names["ATI"] == "ATI Inc" and names["FCX"] == "Freeport-McMoRan Inc"
    assert names["BOKF"] == "BOK Financial Corp" and names["AMX"] == "America Movil SAB de CV"
    assert "Corp/" not in flat and "Ati " not in flat and "Mcmoran" not in flat
