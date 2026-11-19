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
import threading

from app import deck, stock_pages
from app.intel import grounding, sec
from app.intel import theme_changes as C
from app.intel import theme_data as D
from tests.test_sec_live_samples import _xom_transport
from tests.test_r66e_fixes import keep, payload, w  # noqa: F401 (the stored-library fixture)
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
    # e79 (LIVE15A-035, updated on purpose): where a company is based is its own, never its layer's: the layer of four 20-F filers is no
    # adjacent layer (its 10-K filer, Wix, stays in its figures), each company based abroad is marked so on its row and said as an adjacent
    # participant, never "another business"
    assert "Adjacent participants: most of its companies are listed in the US but based abroad" not in flat
    assert "5 companies listed in the US but based abroad (a foreign issuer's annual report, 20-F or 40-F) are adjacent participants" in flat
    assert "SAP SE (based abroad)" in flat and "SAP SE (another business)" not in flat and "In the layer's calculations (1 of 5): Wix.com" in flat
    assert "is of listed in the US" not in flat and "based abroad 5" not in flat
    assert deck.ADJACENT_NOTE_ABROAD not in flat and deck.ADJACENT_NOTE not in flat
    names = {r["symbol"]: r["name"] for b in v["layers"] for r in b["companies"]}
    assert names["SCCO"] == "Southern Copper Corp" and names["ATI"] == "ATI Inc" and names["FCX"] == "Freeport-McMoRan Inc"
    assert names["BOKF"] == "BOK Financial Corp" and names["AMX"] == "America Movil SAB de CV"
    assert "Corp/" not in flat and "Ati " not in flat and "Mcmoran" not in flat


# ---------- LIVE14A-002 / -005: a theme's re-check never yields for ever ----------
def test_fix20_a_rebuild_that_keeps_yielding_takes_its_turn(w, monkeypatch):  # noqa: F811 (the fixture)
    """Fails before: on a busy server the memory guard's turn was never free for YIELD_WAIT seconds, so the most-read theme yielded at the front
    of the queue again and again (Semiconductors, then Software and REITs behind it, "being worked out" for 10 hours). After YIELD_MAX yields
    in a row its rebuild waits for its turn like any other heavy job."""
    from app import memguard
    from app.intel import theme_recheck
    keep("ships", payload("Ships"))
    theme_recheck.queue()
    held, release = threading.Event(), threading.Event()

    def price_job():                       # a job holding the turn the whole time: the idle turn never comes
        with memguard.heavy("page-prices"):
            held.set()
            release.wait(10)
    t = threading.Thread(target=price_job)
    t.start()
    held.wait(5)
    monkeypatch.setattr(theme_recheck, "YIELD_WAIT", 0.05)
    phases = []

    def work(region, name):
        with theme_recheck._turn("dive"):
            phases.append(theme_recheck._force.get("on", False))
        return None
    try:
        outs = [theme_recheck.step(work)["outcome"] for _ in range(theme_recheck.YIELD_MAX)]
        assert outs == ["yielded"] * theme_recheck.YIELD_MAX and phases == []
        threading.Timer(0.3, release.set).start()          # the price job ends; the forced turn waits for it, then runs
        last = theme_recheck.step(work)
    finally:
        release.set()
        t.join(5)
    assert phases == [True] and last["outcome"] == "failed"           # (this work keeps no dive: "its dive was not kept")
    assert not theme_recheck._force and "IN|ship" not in (theme_recheck._load().get("yields") or {})


# ---------- LIVE14A-003: a third party's sentences are no company's own words ----------
def test_fix20_encyclopedia_rankings_history_and_headings_never_pass_as_own_words():
    """Fails before: Shell "...was the ninth-largest corporate producer of greenhouse gas emissions in the period 1988–2015" as its own words;
    Andhra Cements' quote running into "Corporate History & Ownership Changes"; Prism Johnson "was incorporated in 1992 and is ..."."""
    from app.intel.theme_base import own_words
    from app.intel.theme_changes import first_sentence
    shell = ("Measured by both its own emissions, and the emissions of all the fossil fuels it sells, Shell was the ninth-largest corporate "
             "producer of greenhouse gas emissions in the period 1988–2015.")
    assert own_words(shell, "Shell plc") == ""
    assert own_words("Exxon was one of the largest oil companies by market value in 2010.", "Exxon Mobil Corporation") == ""
    andhra = ("Andhra Cements Limited is engaged in manufacturing and selling cement Corporate History & Ownership Changes Andhra Cements "
              "Limited has undergone multiple ownership changes.")
    assert own_words(andhra, "Andhra Cements Ltd") == "Andhra Cements Limited is engaged in manufacturing and selling cement"
    prism = "Prism Johnson Limited was incorporated in 1992 and is amongst the largest integrated building materials companies in India."
    assert own_words(prism, "Prism Johnson Ltd").startswith("Prism Johnson Limited is amongst the largest integrated building materials")
    assert "1992" not in first_sentence(prism)
    # the company's own words about itself, in the present, stay
    assert own_words("We are the largest cement maker in India, making grey and white cement.", "UltraTech Cement Ltd")
    assert own_words("The Company manufactures and sells cement under the Birla brand.", "X Ltd")


# ---------- LIVE14B-005: the IT services sample deck ----------
def test_fix20_an_industry_layer_keeps_its_acronym():
    """Fails before: "It services", a layer named from the official industry "IT Services ..." in sentence case."""
    from app.intel import theme_base as TB
    assert TB.industry_label("IT Services & Consulting") == "IT services and consulting"
    assert TB.industry_label("IT Enabled Services") == "IT-enabled services"
    assert TB.industry_label("Retail-Apparel & Accessory Stores") == "Apparel and accessory stores"


def test_fix20_a_reason_said_of_several_companies_is_plural_and_staying_out_reads_as_one():
    """Fails before (LIVE14A-007 / LIVE13A-021, LIVE14B-005): "Hypersoft Technologies Ltd and Innovana Thinklabs Ltd: ... as its own words
    don't say ..."; "the last re-check moved it out, it stays where it was"."""
    why = "its own words don’t say it sells what “X” is, nor does its official industry"
    assert deck.reason_for(why, 2) == "their own words don’t say they sell what “X” is, nor do their official industries"
    assert deck.reason_for(why, 1) == why
    out = deck.reason_for("its own words hold no line that says what “M” is: the last re-check moved it out, it stays where it was", 1)
    assert out.endswith("the last re-check moved it out of that layer, and it stays out")
    v = {"layers": [{"layer": "Engineering R&D services", "companies": [
        {"name": "Hypersoft Technologies Ltd", "refit": {"from": "Mid-tier digital", "why": why}},
        {"name": "Innovana Thinklabs Ltd", "refit": {"from": "Mid-tier digital", "why": why}}]}]}
    n, said = deck.refit_line(v)
    assert n == 2 and "as their own words don’t say they sell" in said and "as its own words" not in said


def test_fix20_the_low_confidence_note_says_its_tag_once():
    assert deck.LOW_NOTE.count("low confidence") == 2 and "how it earns is read at low confidence" not in deck.LOW_NOTE
    assert deck.PROFILE_MORE.count("{notes}") == 1


def test_fix20_the_public_tally_names_every_state_so_it_adds_up():
    """Fails before (LIVE14A-004): Fertilizers "284 companies ...: 266 description-verified, 12 industry-supported, 0 not checked" (278)."""
    from app import public_themes as P
    said = P.evidence_said({"description_verified": 266, "industry_code_supported": 12, "not_confirmed": 6, "membership_unverified": 0})
    assert said == "266 description-verified, 12 industry-supported, 6 own words describe other work, 0 not checked"
    assert "own words" not in P.evidence_said({"description_verified": 3, "industry_code_supported": 1, "membership_unverified": 0})


def test_fix20_the_sample_deck_is_one_whose_gate_passed():
    """Fails before (LIVE14B-005): the sample was the newest kept PDF, whatever its gate said (the IT services deck with engine notes)."""
    from app import sample_deck as S
    ok = {"items": [{"id": "a", "ok": True}, {"id": "b", "ok": True}]}
    bad = {"items": [{"id": "a", "ok": True}, {"id": "b", "ok": False}]}
    rows = [{"id": "1", "label": "India IT services (PDF, 2026-11-19)", "region": "IN", "meta": {"versions": [1], "gate": bad}},
            {"id": "2", "label": "India cement (PDF, 2026-11-18)", "region": "IN", "meta": {"versions": [1], "gate": ok}},
            {"id": "3", "label": "India defence (PDF, 2026-11-17)", "region": "IN", "meta": {"versions": [1], "gate": bad}}]
    assert S.pick(rows, [1])["id"] == "2"
    rows[2]["meta"]["gate"] = ok
    assert S.pick(rows, [1])["id"] == "3"                    # the sample theme, clean, first
    for r in rows:
        r["meta"]["gate"] = bad
    assert S.pick(rows, [1])["id"] == "3"                    # none clean: as before
