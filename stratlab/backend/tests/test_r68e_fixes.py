"""Lane r68e (R68 deck engine): the owner's GPT review of the live R66 decks (vs R65).

P0-1 the core vs adjacent financial population is stable: the live R66 Payments deck folded its card issuers, consumer lenders and digital
     banks into the core figures (16 -> 21 with figures, 64% -> 100% of the value, P/E n 13 -> 18) because the re-check job worked the dive
     out under the theme library's normalised name ("payment and financial technology"), whose "financ" made lenders the theme's own kind.
     The rules now read the map's own name (theme_data.theme_name), the split is versioned (theme_data.POPULATION) and every company that
     joins or leaves the core members against the stored read before is named with why (theme_changes.population_change, the deck's
     "Core and adjacent" row).
"""
import pathlib

import pytest
import sys

from app import deck
from app.intel import theme_changes as C
from app.intel import theme_data as D
from app.intel import theme_library as L
from tests import test_c54_fixes as K

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import deck_check  # noqa: E402


def payments_deck(theme: str):
    """The live R53 Payments placement replayed (test_c54_fixes) and built into a deck with the dive worked out under `theme`."""
    from tests.test_export import texts
    from tests.test_r18_deck import deck_of
    from tests.test_r48_reconcile import co
    d = K.inputs("payments")
    out = K.replay("payments")
    f = {}
    for li, v in enumerate(out["value_chain"]):
        for i, c in enumerate(v["companies"]):
            sales = 1000.0 + 37 * i
            f[c["ticker"]] = co(c["ticker"], c.get("name") or c["ticker"], sales, 6.0 + 3.3 * (li % 7), sales * 0.05)
    m = {**out, "sector": d["theme"], "sub_themes": out.get("sub_themes") or []}
    v, slides = deck_of(d["region"], m, f, theme=theme, about=d["evidence"].get)
    return v, "\f".join(texts([s]) for s in slides)


# ---------- P0-1 the core vs adjacent population ----------
def test_the_core_and_adjacent_split_is_the_same_whichever_search_reached_the_stored_map():
    """Fails before: worked out under the library's name for the theme ("payment and financial technology", as the re-check job does),
    the Payments dive had no adjacent participant: the card lenders and the digital bank counted as core members, and the deck named
    "Card issuers…" with no "Core and adjacent" row (deck_check's "scope core" on the live R66 deck). Now the split is the page's."""
    name = L.normalise("Payments and fintech", "US")
    assert "financ" in name
    v_page, _ = payments_deck("Payments and fintech")
    v_lib, text = payments_deck(name)
    page = {x["symbol"]: x["kind"] for x in v_page["adjacent"]}
    assert {"SYF", "AFRM", "DAVE"} <= set(page)
    assert {x["symbol"]: x["kind"] for x in v_lib["adjacent"]} == page
    assert v_lib["with_figures"] == v_page["with_figures"] and v_lib["sections"]["medians"] == v_page["sections"]["medians"]
    assert "Core and adjacent" in text and not deck_check.check_text(text)["counts"]["scope core"]
    assert v_lib["population_rule"] == D.POPULATION and D.POPULATION_RULE[D.POPULATION]


def test_theme_name_is_the_maps_own():
    assert D.theme_name("payment and financial technology", {"sector": "Payments and fintech"}) == "Payments and fintech"
    assert D.theme_name("fintech", {"sector": ""}) == "fintech"
    assert D.theme_name("x", None) == "x"


def _dive(adjacent: list, rule: int | None = None, extra: dict | None = None) -> dict:
    rule = getattr(D, "POPULATION", 1) if rule is None else rule
    cos = [{"symbol": s_, "name": n_, "revenue": 100.0, "ebitda": 10.0, "year": "Dec 2025", "official_industry": ind}
           for s_, n_, ind in (("COF", "Capital One Financial Corp", "Commercial banks"), ("SYF", "Synchrony Financial", "Finance Services"),
                               ("V", "Visa Inc", "Business services"))]
    for c in cos:
        c.update((extra or {}).get(c["symbol"], {}))
    by = {x[0]: x for x in adjacent}
    return {"layers": [{"layer": "Card issuers and consumer lenders", "companies": cos[:2]}, {"layer": "Card networks", "companies": cos[2:]}],
            "adjacent": [{"symbol": s_, "name": next(c["name"] for c in cos if c["symbol"] == s_), "kind": "lenders and financiers",
                          "where": "industry", "text": next(c["official_industry"] for c in cos if c["symbol"] == s_)} for s_ in by],
            "population_rule": rule}


def test_each_company_joining_or_leaving_the_core_members_is_named_with_why():
    """Fails before: R66's 16 -> 21 core members with figures named no company. Now, against the stored read before, each company that left
    the core members (now adjacent) or joined them (adjacent before) is named with its reason, and a change of the rules' version is said."""
    before = C.snapshot(_dive([("COF",), ("SYF",)]))
    assert before["pop"] == D.POPULATION and before["adj"] == {"COF": "lenders and financiers", "SYF": "lenders and financiers"}
    now = _dive([("COF",)], extra={"SYF": {"core_kept": "it runs several businesses, one of them the theme's: card payments"}})
    pc = C.population_change(before, now)
    assert pc["left"] == [] and [x["symbol"] for x in pc["joined"]] == ["SYF"] and "card payments" in pc["joined"][0]["why"]
    pc = C.population_change(C.snapshot(_dive([])), _dive([("COF",), ("SYF",)]))
    assert [x["symbol"] for x in pc["left"]] == ["COF", "SYF"] and "“Commercial banks”" in pc["left"][0]["why"] and "rule" not in pc
    pc = C.population_change(C.snapshot(_dive([("COF",)], rule=D.POPULATION - 1)), _dive([]))
    assert pc["rule"] == [D.POPULATION - 1, D.POPULATION] and "rules changed" in pc["joined"][0]["why"]
    assert "its official industry (Commercial banks)" in pc["joined"][0]["why"]
    # nothing moved, or a stored read of an older engine that keeps no split: nothing said
    assert C.population_change(C.snapshot(_dive([("COF",)])), _dive([("COF",)])) is None
    old = {k: v for k, v in C.snapshot(_dive([])).items() if k not in ("pop", "adj")}
    assert C.population_change(old, _dive([("COF",)])) is None
    # a read stored again unchanged keeps the change said (the split before the last change, as the coverage's "cover_was")
    log = C.apply(C.apply(None, C.snapshot(_dive([("COF",), ("SYF",)]))), C.snapshot(_dive([])))
    log = C.apply(log, C.snapshot(_dive([])))
    assert [x["symbol"] for x in C.population_change(log["snap"], _dive([]))["joined"]] == ["COF", "SYF"]


def test_the_deck_names_the_companies_that_joined_or_left_the_core_members():
    v = {"adjacent": [], "core_kind": "", "population_change": {"left": [], "joined": [
        {"symbol": "COF", "name": "Capital One Financial Corp", "was": "lenders and financiers", "why": "its official industry (Commercial banks) ..."}]}}
    row = deck.adjacent_row(v)
    assert row[0] == "Core and adjacent" and "Capital One Financial Corp (its official industry (Commercial banks)" in row[1]
    assert "1 company joined the core members against the previous stored version" in row[1]
    v = {"adjacent": [{"symbol": "COF", "name": "Capital One Financial Corp", "kind": "lenders and financiers"}],
         "population_change": {"left": [{"symbol": "COF", "name": "Capital One Financial Corp", "kind": "lenders and financiers",
                                         "why": "its principal business (its official industry, “Commercial banks”) is of lenders and financiers"}],
                               "joined": []}}
    row = deck.adjacent_row(v)
    assert "lenders and financiers 1 (Capital One Financial Corp)" in row[1] and "1 company left the core members" in row[1]
    assert deck.population_said(None) == ""


# ---------- P0-2 a property owner's layer by the kind of property its own words name ----------
CAMDEN = ("As of December 31, 2025, we owned interests in, operated, or were developing 175 multifamily properties comprised of 59,921 "
          "apartment homes across the United States.")
R66 = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r66"


def test_a_property_owners_layer_is_said_by_the_kind_of_property_its_words_name():
    """Fails before: Camden's words ("multifamily properties ... apartment homes") said "Manufactured housing and RV communities" by the word
    they share ("communities" of "multifamily communities") and, in R65, "Healthcare property owners" by the words they share most. Now a
    property owner's layer is said by the kinds of property its name and the company's words name."""
    from app.intel import theme_base as B
    assert B.property_fit("Manufactured housing and RV communities", CAMDEN + " We own apartment communities.") is False
    assert B.property_fit("Healthcare property owners", CAMDEN) is False
    assert B.property_fit("Residential landlords", CAMDEN) is True
    assert B.name_says("Manufactured housing and RV communities", CAMDEN.lower() + " apartment communities", set()) == (True, False)
    assert B.name_says("Residential landlords", CAMDEN.lower(), set())[1]
    cases = {"Office landlords": "We own 12 office properties in Manhattan.",
             "Healthcare property owners": "We invest in skilled nursing facilities and senior housing communities.",
             "Industrial, cold storage and self-storage": "We own and lease industrial and logistics properties throughout the United States.",
             "Retail and net lease landlords": "We own sixty-two retail shopping centers leased to grocers.",
             "Towers, data centres and niche property": "In addition, we own and operate towers in South America.",
             "Manufactured housing and RV communities": "We own manufactured housing and recreational vehicle communities."}
    for name, text in cases.items():
        assert B.property_fit(name, text) is True, (name, text)
        assert all(B.property_fit(other, text) is False for other in cases if other != name and B.layer_property_types(other)
                   and not (B.layer_property_types(other) & B.company_property_types(text))), name
    # a list of kinds before what is owned: an office, retail and apartment owner is of the office layer too
    mixed = "a REIT that owns and operates a portfolio of well-located office, retail, and multifamily assets"
    assert B.company_property_types(mixed) == {"office", "retail", "multifamily"} and B.property_fit("Office landlords", mixed)
    # (guard) a name that states no property owner's business judges nothing; words of no property owned judge nothing
    assert B.property_fit("Office products", "We own office properties.") is None
    assert B.property_fit("Hotel operators", "We own select-service hotel properties.") is None
    assert B.property_fit("Office landlords", "We make office chairs and desks.") is None
    assert B.property_fit("Mortgage REITs", CAMDEN) is None


def _reits(evidence: dict | None = None):
    import release_gate as G
    d = G.load(R66 / "reits.json")
    d["evidence"] = {**d["evidence"], **(evidence or {})}
    with G.offline():
        out, _ = G.engine(d)
    return d, out


def test_camden_is_with_the_apartment_owners_on_the_live_r66_reits_input():
    """Fails before: the replay of the live R66 REITs placement input put Camden, Mid-America, UDR and Independence Realty, apartment owners,
    in "Manufactured housing and RV communities" (the map's "Residential landlords" renamed for its three manufactured-housing members), SBA
    Communications, a tower owner, in "Healthcare property owners", and office, retail, hotel, apartment and nursing-home owners in "Towers,
    data centres and niche property". Now the layer keeps its name, and every company whose own words name a kind of property is in a layer
    whose name names it, or in "Other"; each move quotes its words."""
    from app.intel import theme_base as B
    d, out = _reits()
    where = {c["ticker"]: (v["layer"], c) for v in out["value_chain"] for c in v["companies"]}
    assert where["CPT"][0] == "Residential landlords" and {"MAA", "UDR", "SUI", "ELS"} <= {s for s, x in where.items() if x[0] == "Residential landlords"}
    assert where["SBAC"][0] == "Towers, data centres and niche property"
    assert where["STRW"][0] == "Healthcare property owners" and "“skilled nursing”" in where["STRW"][1]["refit"]["why"]
    assert where["NYC"][0] == "Office landlords" and where["PRXA"][0] == "Hotel and leisure property owners"
    for s_, (layer, c) in where.items():
        assert B.property_fit(B._HALF_RX.sub("", layer), B.own_text(d["evidence"].get(s_) or "")) is not False, (s_, layer)
    assert any("name property of “Residential landlords”" in str(r.get("why")) for r in out["placements"].get("renames") or []) or \
        "Manufactured housing and RV communities" not in {v["layer"] for v in out["value_chain"]}


def test_vornado_with_its_10k_list_is_an_office_landlord_on_the_live_r66_reits_input():
    """Fails before: R67's Vornado fix (its 10-K's list of what it owns read as its opening) did not hold on the live R66 REITs input:
    with that opening Vornado stayed in "Other" (its words say "office space", which no rule read as the office layer's work once the
    published memory held it out). Now its words name office property, and it is in "Office landlords"."""
    vno = ("We currently own all or portions of: 51 Manhattan operating properties consisting of: 19.2 million square feet of office space "
           "in 26 of the properties; 2.3 million square feet of street retail space in 60 of the properties.")
    _, out = _reits({"VNO": vno})
    assert next(v["layer"] for v in out["value_chain"] for c in v["companies"] if c["ticker"] == "VNO") == "Office landlords"


# ---------- P0-3 no loss of verified evidence ----------
JINDAL = ("Jindal Steel & Power Limited (JSPL) is an Indian steel and energy company. It manufactures steel through blast furnace and "
          "direct reduced iron routes, with plants at Raigarh and Angul, and makes plates, rails, structurals and wire rods.")


def test_a_companys_earlier_or_fuller_name_is_not_another_companys():
    """Fails before: R66's reader of another company's opening (own_part) read "Jindal Steel & Power Limited", Jindal Steel Limited's name
    before 2025, as another company's and left it no words of its own: description-verified as a steel mill in R65, "no description of its
    own is stored yet" in R66. A subject saying every word of a name of two words or more is the company itself."""
    from app.intel import theme_base as B
    assert B.own_part(JINDAL, "Jindal Steel Limited") == JINDAL
    assert B.own_part("Adani Ports and Special Economic Zone Limited is India's largest port operator.", "Adani Ports & SEZ Ltd")
    # (guard, r66e) a name of one word, or a subject naming another company, still loses those sentences
    assert B.own_part("Toyo Tire Corporation is a Japanese tire maker.", "TOYO Co., Ltd") == ""
    assert B.names_other("Jindal Saw Limited makes ductile iron pipes.", "Jindal Steel Limited")


@pytest.fixture
def w(monkeypatch):
    from app import computed
    from app.intel import theme_library, theme_recheck
    from tests import world
    built = world.build(monkeypatch)
    computed.reset_for_tests()
    theme_library._refreshing.clear()
    theme_recheck._asked.clear()
    yield built
    built["close"]()


def test_a_read_that_leaves_no_words_keeps_the_words_the_record_had(w, monkeypatch):
    """Fails before: a stored description read as another company's was dropped and the record read again, and a read that left no words of
    the company's own (its fuller name read as another's) was stored over it: the words it was verified on were gone. Now the record keeps
    the words it had ("was_about", with what the new read opened on), each later reader reads them again, and a record left with no words by
    an earlier version of that reader is read once more."""
    import json
    from app import db
    from app.intel import theme_base as B
    from app.intel import theme_routes as T
    key = "theme:evidence:IN:JINDALSTEL"
    db.set_setting(key, json.dumps({"at": "2026-11-16T00:00:00+00:00", "about": JINDAL, "industry": "Iron & Steel", "v": T.ABOUT_V}))
    monkeypatch.setattr(T, "_index_name", lambda region, sym: "Jindal Steel Limited")
    monkeypatch.setattr(T, "own_filings", lambda region, sym: "")
    # an older reader's verdict (another company's words), as R66's: the record is read again and the read gives none of its own
    real = B.own_part
    monkeypatch.setattr(T.theme_base, "own_part", lambda about, name="": "" if "Jindal Steel & Power" in str(about) else real(about, name))
    monkeypatch.setattr(T, "india_profile", lambda screener, sym, code_of=None: {"about": JINDAL, "industry_path": ["Iron & Steel"]})
    T.EVIDENCE_CACHE.pop(key)
    got = T.evidence_reader("IN", {"JINDALSTEL": "Jindal Steel Limited"})(["JINDALSTEL"])[0]
    stored = json.loads(db.get_setting(key))
    assert not stored["about"] and stored["was_about"] == JINDAL and stored["other"].startswith("Jindal Steel & Power Limited")
    assert stored["op"] == T.OWN_PART_V and not (got.get("JINDALSTEL") or {}).get("about")
    # today's reader reads the kept words as its own again
    monkeypatch.setattr(T.theme_base, "own_part", real)
    assert T.own_got("IN", "JINDALSTEL", stored, "Jindal Steel Limited")[0]["about"] == JINDAL
    T.EVIDENCE_CACHE.pop(key)
    assert T._about_reader("IN", {"JINDALSTEL": "Jindal Steel Limited"}, 0)("JINDALSTEL") == JINDAL
    # a record with no words kept before this reader's version, of a company with a page, is read once more; one of today's is not
    assert T.thin_about({"at": "2026-11-17T09:00:00+00:00", "about": "", "v": T.ABOUT_V})
    assert not T.thin_about({"at": "2026-11-10T00:00:00+00:00", "about": "", "v": T.ABOUT_V})          # kept before R66 ran: never emptied by it
    assert not T.thin_about({"at": "2026-11-16T00:00:00+00:00", "about": "", "v": T.ABOUT_V, "op": T.OWN_PART_V})
    assert not T.thin_about({"at": "2026-11-16T00:00:00+00:00", "about": "", "v": T.ABOUT_V, "no_page": True})


def test_a_company_whose_words_were_read_as_another_companys_says_so_where_it_is_not_checked():
    """Fails before: "no description of its own is stored yet" for a company whose stored description was read as another company's. Now
    the reason quotes what it opened on."""
    why = D.unchecked_why({"name": "TOYO Co., Ltd"}, None, "Toyo Tire Corporation is a Japanese tire maker.")
    assert "opens on another company's name (“Toyo Tire Corporation is a Japanese tire maker.”)" in why
    assert D.unchecked_why({"name": "X Ltd"}, None) == "no description of its own is stored yet, so its membership is not checked yet"


# ---------- P1-1 the coverage effect of moves into "Other" ----------
def test_moves_into_other_say_what_they_take_from_the_informative_layers():
    """Fails before: the live R66 Textiles deck's "moved into “Other textile companies” 10" said neither how many companies its informative
    layers lost nor what share of the theme's value. Now the change log says both (deck_check still reads each move's reason)."""
    import importlib
    deck_check_ = importlib.import_module("deck_check")
    entry = {"d": "2026-11-18", "cause": "rules", "counts": {"moved": 2},
             "moved": [{"symbol": "A", "name": "Addi Industries Ltd", "from": "Garment contract manufacturers", "to": "Other textile companies",
                        "why": "its own words don't say what “Garment contract manufacturers” is"},
                       {"symbol": "K", "name": "Kizi Apparels Ltd", "from": "Garment contract manufacturers", "to": "Other textile companies",
                        "why": "no words of its own are stored"}]}
    v = {"changes": {"entries": [entry]}, "coverage": {"other_name": "Other textile companies"},
         "members": [{"symbol": "A", "cap": 30.0}, {"symbol": "K", "cap": 10.0}, {"symbol": "B", "cap": 960.0}]}
    row = deck.cohort_row(v)
    assert "moved into “Other textile companies” 2 (2 companies fewer in its informative layers, 4.0% of the theme's market value): " in row[2]
    assert not deck_check_.check_text(row[2])["counts"]["move unexplained"]
    entry["moved"][1].pop("why")          # (guard) a move with no reason is still flagged in the new form
    assert deck_check_.check_text(deck.cohort_row(v)[2])["counts"]["move unexplained"]
    v["members"] = []
    assert "moved into “Other textile companies” 2 (2 companies fewer in its informative layers): " in deck.cohort_row(v)[2]


# ---------- P1-2 REIT metric completeness, company by company ----------
def test_each_reit_is_said_by_its_ffo_state():
    """Fails before: the REITs deck said only how many property owners had FFO ("not available for the N"), naming none, and said nothing of
    its mortgage REITs. Now each company with figures is named by its state: FFO worked out (AFFO too where filed), missing in the stored
    data (with why), or not applicable (a mortgage REIT earns on loans)."""
    own = lambda s, **k: {"symbol": s, "name": f"{s} Trust", "revenue": 900.0, "profit": 90.0, **k}      # noqa: E731
    v = {"region": "US", "layers": [
        {"layer": "Office landlords", "model": {"family": "property"},
         "companies": [own("BXP", ffo_share=50.0, p_ffo=12.0, affo_share=40.0), own("SLG", ffo_share=44.0), own("VNO")]},
        {"layer": "Mortgage REITs", "model": {"family": "lending"}, "companies": [own("AGNC", official_industry="Real Estate Investment Trusts")]}]}
    st = deck.ffo_states(v)
    assert st == {"available": ["BXP Trust", "SLG Trust"], "missing": ["VNO Trust"], "na": ["AGNC Trust"], "affo": 1}
    got = deck.not_in_sources(v)
    assert "worked out for 2 of the 3 property owners with figures (AFFO too for 1): BXP Trust, SLG Trust" in got
    assert "missing in the stored data for 1 (the filed gains on property sales" in got and "): VNO Trust" in got
    assert "not applicable to the 1 mortgage REITs and other lenders with figures, which earn on loans, not on property they own: AGNC Trust" in got


# ---------- P2 a short table chunk never takes a near-empty page ----------
def test_a_tables_page_less_than_half_full_takes_the_part_of_its_next_row_that_fits():
    """Fails before: the live R66 REITs deck's coverage table put two short rows on p.6 and left the page mostly empty, the next row (nearly
    a page tall) whole on p.7. Now the page takes the part of that row that fits, the rest carried on in "<row> (continued)"; no word is
    lost and the table takes no more pages."""
    head, widths, w, h = deck.COVERAGE_HEAD, [1.8, 1.4, 8.9], deck.CW, deck.BOT - deck.TOP
    long_ = " ".join(f"Company {i} Inc.: from “Layer A” to “Other”, as its own words don't say it sells what “Layer A” is;" for i in range(60))
    rows = [["Not in the sources", "", "Property and leasing: occupancy and rent per square foot aren't in the results formats read."],
            ["In informative layers", "142 of 195", "in a layer the map names; the other 53 in “Other”."],
            ["Moved by what its layer is", "11", long_]]
    while len(deck.table_pages(head, [rows[2]], widths, w, h)) > 1:          # the long row: one page whole, as the live one
        rows[2][2] = rows[2][2].rsplit(";", 2)[0] + ";"
    pages = deck.table_pages(head, rows, widths, w, h)
    assert len(pages) <= 2
    assert pages[0][-1][0] == "Moved by what its layer is" and pages[1][0][0] == "Moved by what its layer is (continued)"
    assert " ".join(r[2] for p in pages for r in p if r[0].startswith("Moved")).split() == rows[2][2].split()
    # (guard) a page already half full sends a row that doesn't fit to the next page whole
    full = [[f"Row {i}", "1", "a short line of text " * 12] for i in range(6)] + [rows[2]]
    got = deck.table_pages(head, full, widths, w, h)
    assert all(not r[0].endswith("(continued)") for p in got for r in p) or deck.table_height(head, got[0][:-1], widths, w) < deck.FLOW_FILL * h
