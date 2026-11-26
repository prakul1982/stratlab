"""Lane e84 (Release 83): theme-engine items from LIVE20A/B and the R82 decks. Each test fails before its fix and passes after, except those
marked as guards."""
import json
import sys
from datetime import date
from pathlib import Path

from app.intel import theme_base as B
from app.intel import theme_changes as C
from app.intel import theme_data as D
from app.intel import theme_routes as TR

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _capgoods() -> dict:
    """A Capital goods map as the live one is drawn (AI-picked official industries; the machinery layer split into halves by market value, the
    smaller half made by the split)."""
    return {"sector": "Capital goods", "placements": {"industries_by": "ai", "industries": ["Industrial Machinery", "Heavy Electrical Equipment"]},
            "value_chain": [
                {"layer": "Industrial machinery and engines makers (larger)", "scale": "larger", "sibling": "Industrial machinery and engines makers (smaller)",
                 "description": "Makers of industrial machines, engines, compressors and pumps.", "companies": []},
                {"layer": "Industrial machinery and engines makers (smaller)", "by_model": True, "scale": "smaller",
                 "sibling": "Industrial machinery and engines makers (larger)", "companies": []},
                {"layer": "Cables, transformers and electrical equipment makers", "companies": []},
                {"layer": "Parts, component and ingredient makers", "by_model": True, "model": {"by_how": True}, "companies": []},
                {"layer": "Other capital good companies", "official": True, "basis": "rest", "companies": []}]}


def _co(t, what, base=True):
    return {"ticker": t, "name": t, "what": what, "base": base, "verified": False, "basis": "industry"}


# ---------- 1. LIVE20A-001: Capital goods' machinery makers description-verified by what they make ----------
def test_machinery_makers_are_verified_by_the_machines_cranes_compressors_and_pumps_they_make():
    """Fails before: "machines", "cranes", "compressors" and "pumps" said no word of "Industrial machinery and engines makers"."""
    wt = D.work_test(_capgoods(), "Capital goods")
    for line in ("Jyoti CNC Automation is a leading manufacturer of simultaneous 5-axis CNC machines in India",
                 "Action Construction Equipment Ltd is engaged in the business of manufacturing and marketing of hydraulic mobile cranes",
                 "Ingersoll Rand India Limited is engaged in the business of manufacturing and selling industrial air compressors",
                 "Shakti Pumps (India) Ltd is primarily engaged in manufacturing of pumps and motors of various kinds",
                 "Kirloskar Brothers is engaged in the business of engineering and manufacturing of systems for fluid management"):
        c = _co("X", line)
        assert wt(c, line), line


def test_generic_words_still_never_verify_a_capital_goods_company():
    """Guard (e83's aim): "engineering", "pre-engineered", "equipment" or the products of another business say no layer's work."""
    wt = D.work_test(_capgoods(), "Capital goods")
    for line in ("Epack Prefab Technologies Limited is one of India's leading players in the pre-engineered building industry",
                 "Kanoria Chemicals & Industries Ltd is in the business of manufacturing Industrial Chemicals",
                 "GEE Ltd manufactures Welding Electrodes, Copper Coated Wires, Flux Cored Wires and Welding Fluxes",
                 "Zetwerk Manufacturing Businesses Limited is a technology-led B2B manufacturing platform"):
        assert not wt(_co("X", line), line), line


def test_the_smaller_half_of_a_split_layer_gives_its_name_words():
    """Fails before: the smaller half, marked by_model by the split, was left out of the layers whose words say the work."""
    m = _capgoods()
    m["value_chain"] = [v for v in m["value_chain"] if not v["layer"].endswith("(larger)")]
    wt = D.work_test(m, "Capital goods")
    line = "Macpower CNC Machines Limited is engaged in the manufacture of machinery and lathes"
    assert wt(_co("X", line), line)


def test_textile_makers_by_their_products_and_the_pasta_maker_and_trader_stay_out():
    """Fails before: jute, socks, hosiery, innerwear and elastics makers were industry-supported (e83's Textiles drops)."""
    m = {"sector": "Textiles", "placements": {"industries_by": "ai"}, "value_chain": [
        {"layer": "Home textiles and fabric makers (larger)", "scale": "larger", "companies": []},
        {"layer": "Branded apparel companies", "companies": []}, {"layer": "Other textile companies", "official": True, "companies": []}]}
    wt = D.work_test(m, "Textiles")
    for line in ("Ludlow Jute & Specialities Ltd manufactures and sale of Jute Goods Business",
                 "Filatex Fashions Limited is engaged in the business of manufacturing socks",
                 "Dollar Industries Limited is engaged in manufacture and sale of hosiery products in knitted inner wears",
                 "Premco Global Ltd manufactures Knitted & Narrow woven Elastics"):
        assert wt(_co("X", line), line), line
    for line in ("Tejassvi Aaharam Ltd is a manufacturer of Pasta products",
                 "Grameva Ltd deals in agricultural products and metal handicrafts"):
        c = _co("X", line)
        assert not wt(c, line + " Business Overview: GL is in the business of Jute and Agro trading"), line


# ---------- 2. LIVE20A-019: the stored Gold miners theme judged by its work; no line, no description-verified ----------
def _gold() -> dict:
    return {"sector": "Gold miners", "placements": {"industries_by": "list", "industries": [
        "Metal Mining", "Bituminous Coal & Lignite Surface Mining", "Mining & Quarrying Of  Nonmetallic Minerals (No Fuels)",
        "Gold And Silver Ores", "Silver Ores"]}, "value_chain": [
        {"layer": "Gold producers", "companies": []}, {"layer": "Base and industrial metals miners", "companies": []},
        {"layer": "Other gold miner companies", "official": True, "companies": []}]}


def test_a_theme_of_two_curated_entries_at_once_is_judged_by_its_own_work():
    """Fails before: "Gold miners" (the miners' entry and the gold one) had no work test, so coal, copper and aggregates words verified."""
    wt = D.work_test(_gold(), "Gold miners")
    assert wt is not None
    assert not wt(_co("BTU", "Peabody is a leading producer of metallurgical and thermal coal mining"), "")
    assert not wt(_co("SCCO", "Southern Copper Corporation is one of the largest integrated copper producers and miners in the world"), "")
    assert not wt(_co("BHP", "The company specialises in mining and selling iron ore, copper and coal"), "")
    assert wt(_co("B", "Barrick Mining Corporation is a mining company that produces gold and copper"), "")
    assert wt(_co("KGC", "Kinross currently operates six active gold mines"), "")
    assert wt(_co("NEM", "Doré is sent to refiners to produce bullion that meets the required market standard of 99.95% gold"), "")


def test_a_theme_whose_name_joins_two_entries_with_and_keeps_its_curated_rule():
    """Guard: "Steel and metals" names two entries joined by "and": a union, no work test (unchanged)."""
    m = {"sector": "Steel and metals", "placements": {"industries_by": "list", "industries": ["Metal Mining", "Steel Pipe & Tubes"]},
         "value_chain": []}
    assert D.work_test(m, "Steel and metals") is None


def test_a_company_with_no_line_a_page_shows_is_never_description_verified():
    """Fails before: Martin Marietta was description-verified on an encyclopedia's sentences its page leaves out ("–" for its own words); a
    map pick checked yes with no line of its own was description-verified."""
    words = D.theme_words(_gold(), "Gold miners")
    raw = ("Martin Marietta Materials, Inc. is an American company that supplies aggregates, cement, asphalt, and heavy building materials. "
           "It has operations spanning 26 states, Canada, and the Caribbean.")
    c, q = D.quoted_words({"ticker": "MLM", "name": "Martin Marietta Materials Inc", "what": "", "base": True, "verified": False}, raw, "US", True)
    assert not q                                    # the words a page may quote: none (an encyclopedia's)
    assert D.evidence_state(c, words, q) != "description_verified"
    pick = {"ticker": "TEXRAIL", "name": "Texmaco Rail", "what": "", "base": False, "verified": True}
    assert D.evidence_state(pick, words, None) == "list_supported"
    # (guard) one with a line of its own words is as before
    assert D.evidence_state({**pick, "what": "Texmaco makes rail wagons and gold mining equipment"}, words, None) == "description_verified"


def test_states_kept_under_an_earlier_evidence_rule_are_judged_again():
    """Fails before: a stored theme kept every state beyond the figures' window as an earlier rule judged it (Capital goods' 139
    industry-supported beside the window's new ones)."""
    m = _capgoods()
    m["value_chain"][0]["companies"] = [{**_co("JYOTICNC", ""), "cap": 10}, {**_co("ZZZ", ""), "cap": 5}]
    about = {"JYOTICNC": "Jyoti CNC Automation is a leading manufacturer of simultaneous 5-axis CNC machines in India.",
             "ZZZ": "Zed Ltd is in the business of trading steel products."}.get
    before = {"ev": {"JYOTICNC": "i", "ZZZ": "i"}}
    dive = {"evidence": {}, "coverage": {"placed": 2}}
    got = TR.membership_check("Capital goods", m, m, dive, before, about, date(2026, 11, 20), "IN")
    assert got["outside"]["JYOTICNC"] == "description_verified" and got["outside"]["ZZZ"] == "industry_code_supported"
    assert got["rule"] == D.EVIDENCE_RULE and got["rechecked"] == 1
    # a snapshot of the current rule: its kept states are not all judged again (the rechecks of e83 and h56 only)
    import pytest
    mp = pytest.MonkeyPatch()
    calls = []
    mp.setattr(D, "kept_rejudged", lambda *a, **k: calls.append(a) or a[1])
    try:
        TR.membership_check("Capital goods", m, m, dive, {**before, "ev_rule": D.EVIDENCE_RULE}, about, date(2026, 11, 20), "IN")
        assert calls == []
        TR.membership_check("Capital goods", m, m, dive, before, about, date(2026, 11, 20), "IN")
        assert len(calls) == 1
    finally:
        mp.undo()


def test_the_snapshot_keeps_the_evidence_rule_its_states_are_of():
    dive = {"layers": [{"layer": "L", "companies": [{"symbol": "A", "name": "A"}]}],
            "membership_check": {"outside": {"B": "description_verified"}, "rule": D.EVIDENCE_RULE}}
    snap = C.snapshot(dive, ["A"])
    assert snap.get("ev_rule") == D.EVIDENCE_RULE


def test_a_public_row_says_the_dives_state_so_its_layers_add_up_to_the_headline(monkeypatch):
    """Fails before: a row whose map record was checked yes said description-verified whatever the dive's state (Capital goods' layers
    180 / 137 beside the headline's 178 / 139)."""
    from app import public_themes as P
    from app import screens, stock_pages
    dive = {"as_of": "2026-11-20", "evidence": {"A": "industry_code_supported", "B": "description_verified"},
            "tally": {"description_verified": 1, "industry_code_supported": 1, "total": 2},
            "layers": [{"layer": "L", "companies": [{"symbol": "A", "cap": 10.0, "price_at": "2026-11-20"},
                                                    {"symbol": "B", "cap": 5.0, "price_at": "2026-11-20"}]}]}
    monkeypatch.setattr(P, "_dive", lambda *a, **k: dive)
    monkeypatch.setattr(stock_pages, "companies", lambda region: set())
    monkeypatch.setattr(screens, "load_index", lambda region: {"rows": []})
    p = {"sector": "Gadgets", "value_chain": [{"layer": "L", "companies": [{"ticker": "A", "name": "A", "verified": True},
                                                                         {"ticker": "B", "name": "B", "verified": True}]}]}
    v = P.view({"region": "IN", "label": "Gadgets", "slug": "gadgets", "name": "gadgets", "rules": None}, p)
    lay = v["layers"][0]["evidence"]
    assert lay["description_verified"] == v["evidence"]["description_verified"] == 1
    assert lay["industry_code_supported"] == v["evidence"]["industry_code_supported"] == 1


# ---------- 3. LIVE20A-003/004: Omega where its words put it; one FFO answer; the change log ----------
def test_a_reit_named_for_the_kind_it_owns_whose_words_say_it_owns_it_is_of_that_layer():
    """Fails before: Omega's name ("Healthcare") set aside from its words left them naming no kind of property, and "non-real estate loans"
    read as a lender's words."""
    v = {"layer": "Healthcare property owners", "companies": []}
    words = ("Additionally, during the fourth quarter of 2025, we began utilizing the structure authorized by the REIT Investment Diversification "
             "and Empowerment Act of 2007, whereby we own and operate healthcare facilities through third-party managers. In addition to our core "
             "investments, we make loans to operators. These loans are classified as non-real estate loans.")
    c = {"ticker": "OHI", "name": "Omega Healthcare Investors Inc", "model": "property"}
    assert "own and operate healthcare facilities" in B.owns_named_kind(v, c, words)
    assert not B.LENDS_SAYS.search(words)
    # (guard) a REIT whose name names no kind keeps the rules of its words alone; a lender's words still read as a lender's
    assert B.owns_named_kind({"layer": "Industrial, cold storage and self-storage"},
                             {"name": "Postal Realty Trust, Inc.", "model": "property"},
                             "We acquire properties leased to the USPS, ranging from last-mile post offices to industrial facilities.") == ""
    assert B.LENDS_SAYS.search("We originate commercial real estate loans")


def test_the_live_reits_replay_puts_omega_with_the_healthcare_owners():
    """Fails before: the replay of the live R82 REITs placement inputs (Omega fed in its map layer) kept it in "Mortgage REITs"."""
    from tests.test_d53_fixes import replay
    p = Path(__file__).parent / "fixtures" / "themes_live" / "r82" / "reits_ohi.json"
    d = json.loads(p.read_text())
    out = replay(d, published=d.get("published") or {}, figures_of=lambda s: (d.get("figures") or {}).get(s),
                 moved_before=d.get("moved_before") or {})
    where = {c["ticker"]: v["layer"] for v in out["value_chain"] for c in v["companies"]}
    assert where["OHI"] == "Healthcare property owners", where.get("OHI")


def test_a_row_that_keeps_its_ffo_is_said_with_it_whatever_its_layers_family():
    from app import deck
    v = {"region": "US", "layers": [{"layer": "Mortgage REITs", "model": {"family": "lending"}, "companies": [
        {"symbol": "OHI", "name": "Omega Healthcare Investors Inc", "revenue": 1190.0, "p_ffo": 15.5, "ffo_share": 75.0},
        {"symbol": "AGNC", "name": "AGNC Investment Corp.", "revenue": 900.0, "official_industry": "Real Estate Investment Trusts"}]}]}
    st = deck.ffo_states(v)
    assert "Omega Healthcare Investors Inc" in st["available"] and "AGNC Investment Corp." in st["na"]


def test_a_move_a_later_recheck_undoes_is_logged_on_its_day():
    """Fails before: Franklin BSP out of "Mortgage REITs" on 19 Nov and back on 20 Nov was in no entry (both dropped as undone)."""
    log = [{"d": "2026-11-19", "cause": "rules", "counts": {"moved": 1}, "moved": [
               {"symbol": "FBRT", "name": "Franklin BSP", "from": "Mortgage REITs", "to": "Other real estate investment trust companies"}]},
           {"d": "2026-11-20", "cause": "rules", "counts": {"moved": 1}, "moved": [
               {"symbol": "FBRT", "name": "Franklin BSP", "from": "Other real estate investment trust companies", "to": "Mortgage REITs"}]}]
    got = C.net_moves(log)
    assert [(e["d"], r["to"]) for e in got for r in e["moved"]] == [("2026-11-19", "Other real estate investment trust companies"),
                                                                    ("2026-11-20", "Mortgage REITs")]


def test_a_kept_reason_of_no_work_or_of_another_layer_is_said_again_from_the_words():
    """Fails before: BREIT "Mortgage REITs → Other: ... never a layer of towers and data centres", Cim's Investment Company Act exemption,
    Orchid's "Bimini commenced ... in 2003", BankUnited's "a national banking association headquartered in ...", FB Bancorp's port of New
    Orleans and TFS's offering of 2007 were printed as their reasons."""
    words = {"BSTT": "We currently operate our business in nine reportable segments: Rental Housing, Industrial, Net Lease and Office properties.",
             "CMRF": "We operate our business in a manner that permits us to maintain our exemption from registration under the Investment "
                     "Company Act. We own and operate a portfolio of real estate.",
             "ORC": "Bimini commenced active investment management operations in 2003. Orchid invests in residential mortgage-backed securities.",
             "BKU": "BankUnited, a national banking association headquartered in Miami Lakes, Florida, provides a full range of banking services.",
             "FBNC": "New Orleans has one of the busiest ports in the world. We provide deposit and loan products to the businesses of the city.",
             "TFSL": "We completed our initial public stock offering in 2007. We originate residential mortgage loans."}.get
    entry = {"d": "2026-11-20", "moved": [
        {"symbol": "BSTT", "name": "BREIT", "from": "Mortgage REITs", "to": "Other real estate investment trust companies",
         "why": "its own words say it is a non-traded REIT (“non-listed”), a diversified owner, never a layer of towers and data centres"},
        {"symbol": "CMRF", "name": "Cim Group", "from": "Retail and net lease landlords", "to": "Other real estate investment trust companies",
         "why": "its own words say “We operate our business in a manner that permits us to maintain our exemption from registration under the Investment Company Act”"},
        {"symbol": "ORC", "name": "Orchid Island Capital", "from": "Other real estate investment trust companies", "to": "Mortgage REITs",
         "why": "its own words say “Bimini commenced active investment management operations in 2003”"},
        {"symbol": "BKU", "name": "BankUnited, Inc.", "from": "Other regional bank companies", "to": "Real estate-focused lenders (bank)",
         "why": "its own words say “BankUnited, a national banking association headquartered in Miami Lakes, Florida, provides a full range of banking services”"},
        {"symbol": "FBNC", "name": "FB Bancorp, Inc.", "from": "Deposit-funded retail and commercial banks", "to": "Other regional bank companies",
         "why": "its own words say “New Orleans has one of the busiest ports in the world”"},
        {"symbol": "TFSL", "name": "TFS Financial Corp", "from": "Real estate-focused lenders (bank)", "to": "Other regional bank companies",
         "why": "its own words say “We completed our initial public stock offering in 2007 and issued 100,199,618 shares of common stock”"}]}
    out = {r["symbol"]: r["why"] for r in C.reasoned([entry], words, lambda s: "", None, B.kind_stems("Regional banks"))[0]["moved"]}
    assert "towers" not in out["BSTT"]
    assert "Investment Company Act" not in out["CMRF"]
    assert "Bimini" not in out["ORC"]
    assert "headquartered" not in out["BKU"]
    assert "New Orleans" not in out["FBNC"] and "2007" not in out["TFSL"]
    # (guard) a reason quoting a line of the layer's work stays
    keep = {"symbol": "KREF", "name": "KKR Real Estate Finance Trust", "from": "Other real estate investment trust companies", "to": "Mortgage REITs",
            "why": "its own words say “KREF is a real estate finance company that focuses primarily on originating and acquiring transitional senior loans”"}
    assert C.reasoned([{"moved": [keep]}], lambda s: "", lambda s: "", None, B.kind_stems("Real estate investment trusts"))[0]["moved"][0]["why"] == keep["why"]


def test_a_layer_of_two_companies_is_said_as_two_and_the_subsidiaries_clause_leaves_a_quote():
    why = "a layer of one company a rule would make (“Media and content”), new to the published version: not made"
    entry = {"moved": [{"symbol": "LAMR", "name": "Lamar", "from": "Media and content", "to": "Other real estate investment trust companies", "why": why},
                       {"symbol": "OUT", "name": "OUTFRONT", "from": "Media and content", "to": "Other real estate investment trust companies", "why": why}]}
    out = C.reasoned([entry])[0]["moved"]
    assert all("a layer of 2 companies a rule would make" in r["why"] for r in out)
    r = C.reasoned([{"moved": [{"symbol": "RWT", "name": "Redwood", "from": "Other x", "to": "Mortgage REITs",
                                "why": "its own words say “Redwood Trust, Inc., together with its subsidiaries, is a specialty finance company focused on housing credit”"}]}])
    assert "together with its subsidiaries" not in r[0]["moved"][0]["why"]


# ---------- 4. LIVE20A-020 / LIVE20B-003: one close for the values a page shows; a deck per price date ----------
def test_a_public_page_says_the_close_its_values_are_at(monkeypatch):
    """Fails before: India pages said "market values at the 19 Nov 2026 close" over values of the 20 Nov close (the index's, for companies the
    dive holds none of)."""
    from app import public_themes as P
    from app import screens, stock_pages
    dive = {"as_of": "2026-11-19", "layers": [{"layer": "L", "companies": [{"symbol": "A", "cap": 10.0, "price_at": "2026-11-19"}]}]}
    monkeypatch.setattr(P, "_dive", lambda *a, **k: dive)
    monkeypatch.setattr(stock_pages, "companies", lambda region: set())
    monkeypatch.setattr(screens, "load_index", lambda region: {"rows": [
        {"symbol": s, "market_cap": 5.0, "price_at": "2026-11-19T10:00:00+00:00" if s == "A" else "2026-11-20T10:00:00+00:00"}
        for s in ("A", "B", "C")]})
    p = {"sector": "Gadgets", "value_chain": [{"layer": "L", "companies": [{"ticker": s, "name": s, "verified": True} for s in ("A", "B", "C")]}]}
    v = P.view({"region": "IN", "label": "Gadgets", "slug": "gadgets", "name": "gadgets", "rules": None}, p)
    # (updated on purpose, e85 LIVE21A-004: one count of the values at an earlier close, said once, never a bracket a close)
    assert v["prices"] == "2026-11-20" and v["prices_older"] == 1
    html = P.render(v)
    assert "market values at the 20 Nov 2026 close; 1 company at an earlier close" in html and "(1 at the 19 Nov" not in html


def test_a_deck_is_kept_per_price_date_and_the_sample_is_at_the_newest_close():
    args = ("IN", "durables", "pdf", date(2026, 11, 20), 1, False, (False, False), 0)
    assert TR.deck_key(*args, "2026-11-19") != TR.deck_key(*args, "2026-11-20")
    assert TR.deck_key(*args)[-1] == 0                           # what the dive waits for: last, as before
    from app import sample_deck
    gate, ver = {"items": [{"ok": True}]}, ["v"]
    rows = [{"id": "new", "label": "India consumer durables (PDF, 2026-11-20)", "region": "IN", "meta": {"gate": gate, "prices": "2026-11-19", "versions": ver}},
            {"id": "older", "label": "India cement (PDF, 2026-11-20)", "region": "IN", "meta": {"gate": gate, "prices": "2026-11-20", "versions": ver}}]
    assert sample_deck.pick(rows, versions=ver)["id"] == "older"


# ---------- 7. the R82 deck checks ----------
def test_a_dated_headline_row_is_no_financial_margin_and_consumer_lenders_are_said_by_consumers():
    sys.path.insert(0, str(SCRIPTS))
    import deck_check as DC
    import deck_diff as DD
    got = []
    DC.financial_checks(["ALCOHOLIC BEVERAGES THEME DEEP DIVE\nAlcoholic beverages\n",
                         "neutral alcohol 162.5% Duty on Bulk Scotch Whisky · 20 Nov 2026 · BigGo Finance · Layer:"], lambda *a: got.append(a))
    assert got == []
    DC.financial_checks(["REGIONAL BANKS THEME DEEP DIVE\nRegional banks\n", "Fifth Third Bancorp net margin 3152.5%"], lambda *a: got.append(a))
    assert got and got[0][0] == "financial margin"            # (guard) a bank's margin above 100% still fails
    assert DD._whom_said("Card issuers and consumer lenders", "financial services for consumers and small businesses")
    assert not DD._whom_said("Card issuers and lenders", "financial services for consumers")


def test_versions():
    from app import blog_research, deck
    assert B.RULES == 80 and TR.PLACE_CARRY[80] == 79 and TR.PLACE_CARRY[79] == 78 and TR.EARLIER_MAX == 35          # e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89)
    assert D.DIVE_TEXT == 54 and deck.THEME_DECK_VERSION == 93 and blog_research.GEN == 12          # deck96 (changed on purpose, every live theme deck checked 26 Nov: dive text 54, deck 93); e90 (changed on purpose, the live R90 alcobev deck: dive text 53 so the kept dives carry the demerger and revenue-basis fixes); deck89 (changed on purpose, owner 25 Nov: the theme deck remade as research): deck 92; e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e85 (LIVE21A, the R84 decks): deck 91, dive text 51 (updated on purpose)
