"""Lane e79: theme engine items from LIVE15A and the R77 decks (Release 78).

1. LIVE15A-004 (+ R77 decks): OSI Systems kept in "Fabless chip design" by the RULES 73 re-check. Its stored words, as production holds them
   (the 10-K's opening, quoted on the live Semiconductors blog post), are "a vertically integrated designer and manufacturer of specialized
   electronic systems ...": the published-member shortcut took it as printing the layer ("designer" says "design"), so it was never judged.
   Essex Property Trust kept in "Other" on its REIT tax sentences: e78's reader never ran for it before the placement (a known model is never
   read again), and the audit quoted its tax election as evidence.
2. LIVE15A-035: the foreign-issuer rule applied per layer: "Integrated oil majors" adjacent for its 20-F filers, so Exxon and Chevron (10-K
   filers) were in no total, median or ranking while Shell, TotalEnergies and BP sat in the layer's figures.
3. LIVE15A-017/008: Camden's $13 m (its fee income) kept in the theme's piece, the public page and the deck's SBC / revenue after its page
   was rebuilt to $1,574 m; Empire State Realty's REIT and its operating partnership two rows.
4. LIVE15A-005/020: third-party and history sentences quoted as own words; TOYO Co. quoted with Toyo Tire's words.
5./6. Public tallies dated by the dive's price day; app/public map dates in two time zones; empty-layer sentence beside a layer's members;
   "amounts in $ million" over "$ bn" cells; "among the map's layers, the "Other" group left out"; several log entries a day.
"""
import json
import pathlib
import sys
import time

from app import computed, deck, public_themes
from app.intel import sector_metrics as SM
from app.intel import theme_base as B
from app.intel import theme_changes as C
from app.intel import theme_data as D
from app.intel import theme_routes as TR
from tests.test_e77 import R69, _live_semis, _where
from tests.test_theme1 import TODAY, facts

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import release_gate as G  # noqa: E402

# OSI Systems' stored words as production holds them: its FY2026 10-K's opening (sec.business_opening on the filing of 21 Aug 2026), the
# line the live Semiconductors blog post quotes for it
OSI_10K = ("OSI Systems, Inc., together with our subsidiaries, is a vertically integrated designer and manufacturer of specialized electronic "
           "systems and components for critical applications. We sell our products and provide related services in diversified markets, "
           "including homeland security, healthcare, defense and aerospace.")


# ---------- 1. OSI Systems: the re-check applies today's rules to a carried move ----------
def test_e79_osi_leaves_fabless_on_its_stored_10k_words_as_production_holds_them():
    """Fails before: the replay of the live R77 input (OSI moved from "Other" into "Fabless chip design" on 18 Nov, published there, its
    words its 10-K's opening) kept OSI in Fabless under RULES 73: "designer" printed a word of the layer's name, so the published-member
    shortcut never judged it. e77's replay used its older encyclopedia words, which never print the layer."""
    d = G.load(R69 / "semis.json")
    _live_semis(d)
    d["evidence"]["OSIS"] = OSI_10K
    fabless = {x["ticker"] for v in d["value_chain"] if v["layer"] == "Fabless chip design" for x in v["companies"]}
    with G.offline():
        out, _ = G.engine(d)
    lay, c = _where(out, "OSIS")
    assert lay != "Fabless chip design", (lay, c)
    why = (c.get("refit") or {}).get("why") or ""
    assert "Fabless chip design" in why and "own words don't say" in why, why
    for s in ("NVDA", "AVGO", "QCOM", "AMD", "MRVL"):          # (guard) the layer's chip designers stay
        if s in fabless:
            assert _where(out, s)[0] == "Fabless chip design", s


def test_e79_a_known_models_words_kept_before_todays_annual_report_reader_are_read_again_before_the_placement(monkeypatch):
    """Fails before: reread_weak read again only companies whose kept model was unknown or of low confidence, so Essex Property Trust (a
    property owner, its model known) kept its REIT tax sentences through the RULES 73 re-check and stayed in "Other"."""
    old = {"at": "2026-11-01T00:00:00+00:00", "v": TR.ABOUT_V, "bv": 3,
           "about": "Essex has elected to be treated as a REIT for federal income tax purposes commencing with the year ended December 31, 1994."}
    fresh = {**old, "bv": TR.sec_business_v(), "about": "Essex Property Trust, Inc. owns apartment communities on the West Coast."}
    store = {"ESS": old, "PLD": fresh}
    monkeypatch.setattr(TR, "_stored_evidence", lambda region, s: store.get(s, {}))
    asked = []
    monkeypatch.setattr(TR, "evidence_reader", lambda region, names, *a, **k: (lambda syms: asked.extend(syms) or ({}, [])))
    out = {"value_chain": [{"layer": "Residential landlords", "companies": [{"ticker": "ESS", "cap": 17000}, {"ticker": "PLD", "cap": 90000}]}]}
    kept = {"models": {"ESS": "property", "PLD": "property"}, "model_confidence": {"ESS": "high", "PLD": "high"}}
    assert TR.reread_weak("US", out, {}, kept) == ["ESS"] and asked == ["ESS"]
    assert TR.reader_due(old, "US") and not TR.reader_due(fresh, "US") and not TR.reader_due(old, "IN")


def test_e79_an_audit_quote_of_how_a_company_is_held_or_taxed_is_no_evidence():
    """Fails before: Essex Property Trust moved from its layer to "Other" on "its own words: “Essex has elected to be treated as a REIT for
    federal income tax purposes ...”, not what ... names"."""
    assert B.structure_quote("Essex has elected to be treated as a REIT for federal income tax purposes commencing with the year ended "
                             "December 31, 1994.")
    assert B.structure_quote("The Company conducts its business through the Operating Partnership")
    # (guard) a sentence of what it owns or does is evidence, tax words or not
    assert not B.structure_quote("Essex owns apartment communities in California and has elected to be treated as a REIT")
    assert not B.structure_quote("develops and markets security and inspection systems such as airport security X-ray machines")


# ---------- 2. the foreign-issuer rule company by company ----------
def _oil(forms):
    cos = [(s, n, f, cap) for s, n, f, cap in forms]
    ep = [(f"EP{i}", f"Driller {i} Inc", "10-K", 50000 - i * 1000) for i in range(6)]
    rows = [{"symbol": s, "name": n, "industry": "Petroleum Refining", "market_cap": c} for s, n, _, c in cos + ep]
    ai = {"sector": "Oil and gas", "summary": "", "core": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 0,
          "value_chain": [{"layer": "Integrated oil majors", "description": "Large companies spanning exploration, production and refining.",
                           "companies": [{"ticker": s, "name": n, "what": "explores for, produces and refines crude oil and natural gas",
                                          "verified": True} for s, n, _, _ in cos]},
                          {"layer": "Exploration and production", "description": "Drill for crude oil and natural gas.",
                           "companies": [{"ticker": s, "name": n, "what": "explores for and produces crude oil and natural gas", "verified": True}
                                         for s, n, _, _ in ep]}]}
    m = B.with_base(ai, {**ai, "placements": {"checked": True, "pending": 0}}, rows, [])
    f = {}
    for i, (s, n, form, cap) in enumerate(cos + ep):
        f[s] = {**facts(s, n, [500, 600, 700, 800 + i * 20], [20.0, 21.0, 22.0, 18.0 + i], [50, 60, 70, 80 + i], cap=cap, pe=12.0,
                        industry=("Petroleum Refining",)), "region": "US", "unit": "$ million", "annual_form": form, "annual_filed": "2026-02-01"}
    return D.build("US", "Oil and gas", m, D.Sources(TODAY, facts=f.get))


def test_e79_us_filers_stay_core_and_foreign_filers_adjacent_whatever_their_layer_mates_file():
    """Fails before: the layer with four 20-F filers of six was adjacent, its 10-K filers Exxon and Chevron in no total, median or ranking
    of the theme, and Shell, TotalEnergies, BP and Equinor in the layer's own calculations."""
    dive = _oil([("XOM", "Exxon Mobil Corporation", "10-K", 600000), ("CVX", "Chevron Corp", "10-K", 400000),
                 ("SHEL", "Shell plc", "20-F", 270000), ("TTE", "TotalEnergies SE", "20-F", 190000), ("BP", "BP PLC", "20-F", 110000),
                 ("EQNR", "Equinor ASA", "20-F", 100000)])
    majors = next(b for b in dive["layers"] if b["layer"] == "Integrated oil majors")
    assert not majors.get("adjacent")
    calc = {c["symbol"]: D.in_calc(c) for c in majors["companies"]}
    assert calc["XOM"] and calc["CVX"]
    assert not any(calc[s] for s in ("SHEL", "TTE", "BP", "EQNR"))
    assert {a["symbol"] for a in dive["adjacent"]} == {"SHEL", "TTE", "BP", "EQNR"}
    assert not any(r["layer"] == "Integrated oil majors" and r.get("adjacent") for r in dive["chain"]["rows"])
    # (guard) a layer the theme's own business kind makes adjacent stays adjacent; a layer of US filers is untouched
    ep = next(b for b in dive["layers"] if b["layer"] == "Exploration and production")
    assert all(D.in_calc(c) for c in ep["companies"]) and not ep.get("adjacent")


def test_e79_a_us_filer_in_a_layer_of_foreign_filers_is_in_the_layers_figures():
    """Amkor (10-K) in a packaging layer of 20-F filers: in its layer's figures and the theme's, the 20-F filers listed beside it."""
    dive = _oil([("AMKR", "Amkor Technology Inc", "10-K", 9000), ("ASX", "ASE Technology Holding", "20-F", 30000),
                 ("ChipMOS", "ChipMOS Technologies", "20-F", 800)])
    lay = next(b for b in dive["layers"] if b["layer"] == "Integrated oil majors")
    calc = {c["symbol"]: D.in_calc(c) for c in lay["companies"]}
    assert calc == {"AMKR": True, "ASX": False, "ChipMOS": False} and not lay.get("adjacent")


# ---------- 3. Camden: the rebuilt page's revenue everywhere ----------
def test_e79_a_us_piece_read_on_another_revenue_is_read_again_and_its_shares_withheld():
    """Fails before: Camden's piece, read on its $13 m of fee income, gave "SBC / revenue 130.8%" beside its rebuilt page's $1,573.5 m."""
    old = {"family": "us", "end": "2025-12-31", "metrics": {"sbc_share": {"v": 130.8}, "ffo": {"v": 996.0}}, "reit_v": 1}
    row = {"revenue": 1573.5, "year": "Dec 2025", "currency": "USD", "rev_line": "OperatingLeaseLeaseIncome", "sbc_share": 130.8,
           "sector_src": {"sbc_share": {}}}
    assert SM.stale_for_revenue(row, old) and not SM.fresh_piece(old)
    assert SM.withhold_shares(row) == ["sbc_share"] and "sbc_share" not in row and "sbc_share" not in row["sector_src"]
    new = {**old, "rev": 1573.544, "rev_v": SM.REV_V, "reit_v": SM.REIT_V}          # (updated on purpose, e81: REIT_V 2, Camden's FFO read again)
    assert not SM.stale_for_revenue(row, new) and SM.fresh_piece(new)
    assert SM.stale_for_revenue(row, {**new, "rev": 12.967})          # a piece kept on another revenue for the same year
    # (guard) an old piece of a company whose revenue is its top line stands
    assert not SM.stale_for_revenue({**row, "rev_line": "Revenues"}, old)
    facts_ = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 2_000_000_000, "form": "10-K", "fy": 2025,
                                        "fp": "FY", "filed": "2026-02-01"}]}},
        "ShareBasedCompensation": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 40_000_000, "form": "10-K",
                                                      "fy": 2025, "fp": "FY", "filed": "2026-02-01"}]}}}}}
    got = SM.us_figures(facts_)
    assert got["sbc_share"]["v"] == 2.0 and SM.us_revenue(facts_, got["_end"]) == 2000.0


def test_e79_the_dive_takes_the_rebuilt_page_and_the_public_page_its_restated_revenue(monkeypatch):
    """Fails before: the public REITs page and the app's dive kept Camden's "$13M" after its page was rebuilt to $1,574 m."""
    idx = [{"symbol": "CPT", "sales": 1573.5, "sales_year": "Dec 2025", "sales_unit": "$ million"},
           {"symbol": "PLD", "sales": 8000.0, "sales_year": "Dec 2025", "sales_unit": "$ million"}]
    monkeypatch.setattr(TR, "_routes", lambda: type("R", (), {"index_rows": staticmethod(lambda region: idx)})())
    dive = {"layers": [{"companies": [{"symbol": "CPT", "revenue": 12.967, "year": "Dec 2025", "unit": "$ million"},
                                      {"symbol": "PLD", "revenue": 8010.0, "year": "Dec 2025", "unit": "$ million"}]}]}
    assert TR.pages_restated("US", dive) == ["CPT"]
    piece = {"unit": "$ million", "years": [{"year": "Dec 2024", "sales": 11.0}, {"year": "Dec 2025", "sales": 12.967}]}
    assert TR.restated_since("US", "CPT", piece) and not TR.restated_since("US", "CPT", {**piece, "years": [{"year": "Dec 2025", "sales": 1573.5}]})
    got = public_themes.restated_sales({"CPT": (1573.5, "Dec 2025", "$ million"), "PLD": (8000.0, "Dec 2025", "$ million")},
                                       {"CPT": (12.967, "Dec 2025", "$ million"), "PLD": (8010.0, "Dec 2025", "$ million")})
    assert got["CPT"][0] == 1573.5 and got["PLD"][0] == 8010.0          # (guard) a figure within rounding keeps the dive's


def test_e79_a_reits_operating_partnership_is_one_row_with_the_reit():
    rows = [{"symbol": "ESRT", "name": "Empire State Realty Trust, Inc.", "revenue": 760.0, "profit": 50.0, "year": "Dec 2025", "cap": 1500},
            {"symbol": "ESBA", "name": "Empire State Realty OP, L.P.", "revenue": 760.0, "profit": 61.0, "year": "Dec 2025", "cap": None},
            {"symbol": "O", "name": "Realty Income Corp", "revenue": 5000.0, "profit": 800.0, "year": "Dec 2025"}]
    assert D.same_company(rows, about=lambda s: None) == {"ESBA": "ESRT"}
    rows[1]["revenue"] = 900.0                                          # (guard) another revenue: another company
    assert D.same_company(rows, about=lambda s: None) == {}


# ---------- 4. own words ----------
def test_e79_third_party_accounts_and_history_are_no_line_of_own_words():
    """Fails before: each of these, from the live 19 Nov pages, was shown as the company's own words."""
    bad = [("The Kopin Corporation is a Westborough, Massachusetts-based electronics manufacturer, best known for its microdisplay devices", "Kopin Corp"),
           ("Founded as Science Applications International Corporation (SAIC), Leidos merged with Lockheed Martin's IT sector in 2016", "Leidos"),
           ("Wipro Limited provides information technology services and is one of India's Big Six IT services companies", "Wipro Ltd"),
           ("It is vertically integrated across the entire oil and gas industry", "Exxon Mobil Corporation"),
           ("It is the largest independent producer of natural gas in Western Canada", "Canadian Natural Resources"),
           ("Historically, we operated in the optics market selling lenses", "LightPath Technologies"),
           ("From that time until February 2010, we focused on developing additional products and applications", "Metalink Ltd"),
           ("WFOE acquired approximately 82.49% equity interest in Hangzhou Intchains", "Intchains Group"),
           ("The company, formerly known as Square Four Housing, develops real estate projects", "Square Four Projects")]
    for t, n in bad:
        assert not B.own_words(t, n), t
    good = [("It manufactures steel wheels for cars", "Steel Strips Wheels Ltd"),
            ("Hindustan Foods Limited is an India-based company, which is engaged in contract manufacturing of FMCG products", "Hindustan Foods"),
            ("We provide cloud-based software to banks", "Acme Inc"), ("It is a leading provider of cloud software to retailers", "Acme Inc")]
    for t, n in good:
        assert B.own_words(t, n), t


def test_e79_another_companys_article_run_on_after_its_own_words_is_left_out():
    """Fails before: TOYO Co., Ltd (solar cells) quoted as "The company owns and operates eight factories ... distributes tires", Toyo Tire's
    article run on after its own lines."""
    t = ("We are a holding company incorporated in the Cayman Islands. Toyo Tire Corporation is a Japanese tire manufacturer. The company owns "
         "and operates eight factories in Asia, North America, and Europe and distributes tires and automotive components through fourteen "
         "sales companies throughout the world.")
    assert B.own_part(t, "TOYO Co., Ltd") == "We are a holding company incorporated in the Cayman Islands."
    t2 = ("TOYO Co., Ltd makes solar cells in Vietnam. Toyo Tire Corporation is a Japanese tire maker. The company owns factories. "
          "TOYO sells its cells to module makers in the United States.")
    assert B.own_part(t2, "TOYO Co., Ltd") == "TOYO Co., Ltd makes solar cells in Vietnam. TOYO sells its cells to module makers in the United States."
    assert B.own_part("Toyo Tire Corporation is a Japanese tire maker. The company owns factories.", "TOYO Co., Ltd") == ""     # (as before)
    # a map line kept from before is shown only while the words as read now hold it
    c = {"ticker": "TOYO", "what": "The company owns and operates eight factories in Asia, North America, and Europe"}
    assert D.carried_line(c, {"official": True}, lambda s: B.own_part(t, "TOYO Co., Ltd")) == ""
    assert D.carried_line(c, {"official": True}, lambda s: t) == c["what"]
    assert D.carried_line(c, {"official": False}, lambda s: "") == c["what"]           # (guard) a line the map's AI wrote is kept


# ---------- 5./6. dates, counts and wording ----------
def test_e79_the_tally_is_dated_by_the_day_of_the_read_and_logs_one_entry_a_day():
    import inspect
    src = inspect.getsource(TR.dive_of)
    # (updated on purpose, e82 LIVE18A-010: the day of the read in the market's own time, as the app's head says it, never a UTC date)
    assert 'hit["tally_at"] = market_day(r).isoformat()' in src
    L = "Fabless chip design"

    def e(at, **kw):
        base = {"at": f"2026-11-18T{at}:00:00+00:00", "d": "2026-11-18", "cause": "rules", "added": [], "removed": [], "moved": [], "layers": [],
                "restated": []}
        base.update(kw)
        base["counts"] = {k: len(base[k]) for k in C.KINDS}
        return base
    log = [e("01", moved=[{"symbol": "A", "from": "Other", "to": L}], removed=[{"symbol": "T"}]),
           e("03", added=[{"symbol": "T"}], restated=[{"symbol": "CPT", "revenue": [13, 900], "margin": [1, 2]}]),
           e("05", moved=[{"symbol": "B", "from": L, "to": "Other"}], restated=[{"symbol": "CPT", "revenue": [900, 1574], "margin": [2, 3]}]),
           e("07", added=[{"symbol": "Z"}])]
    out = C.net_by_day(log)
    assert len(out) == 1 and out[0]["entries"] == 4
    one = out[0]
    assert [r["symbol"] for r in one["moved"]] == ["A", "B"] and one["removed"] == [] and [r["symbol"] for r in one["added"]] == ["Z"]
    assert one["restated"][0]["revenue"] == [13, 1574] and one["counts"]["moved"] == 2 and one["counts"]["added"] == 1


def test_e79_the_chain_tables_units_are_read_off_its_revenue_column_and_other_is_said_plainly():
    import inspect
    assert 'next((i for i, h in enumerate(head) if str(h).lower().startswith("revenue")), 1)' in inspect.getsource(deck)
    assert deck.units_shown(["$191.7 bn", "$74.3 bn"], "$ million") == "$ billion"
    from tests.test_r25_deck import block
    blocks = [block("A", 6, 26.55), block("B", 6, 14.9), {**block("Other cement companies", 6, 30.0), "official": True, "basis": "rest"}]
    line = D.chain_table(blocks)["line"]
    assert line.endswith('; the "Other" group, outside the map\'s layers, is not ranked.') and "among the map's layers" not in line


def test_e79_a_layer_with_members_and_no_figures_says_how_many_it_lists(monkeypatch):
    dive = _oil([("XOM", "Exxon Mobil Corporation", "10-K", 600000), ("CVX", "Chevron Corp", "10-K", 400000)])
    assert {b["layer"]: b["placed"] for b in dive["layers"]}["Integrated oil majors"] == 2


def test_e79_versions():          # e80 (LIVE16A, the R78 decks): RULES 75, EARLIER_MAX 30, deck 86, dive text 46 (updated on purpose)
    assert B.RULES == 80 and TR.PLACE_CARRY[78] == 77 and TR.PLACE_CARRY[77] == 76 and TR.PLACE_CARRY[76] == 75 and TR.PLACE_CARRY[75] == 74 and TR.PLACE_CARRY[74] == 73 and TR.EARLIER_MAX == 35          # e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose)
    assert D.DIVE_TEXT == 58 and deck.THEME_DECK_VERSION == 97 and SM.VERSION == 3          # data100 (changed on purpose, company data wrong at the source, 27 Nov: dive text 58, deck 97); deck99 (changed on purpose, the deck96 audit's open items, 27 Nov: dive text 57, deck 96); rel98 (fix98 and map98 together, 27 Nov: dive text 56, deck 95, changed on purpose); map98 (a company of the map's own layers whose own first business sentence states another principal business listed as other work); fix98 (changed on purpose, members no longer listed: dive text 55, deck 94); deck96 (changed on purpose, every live theme deck checked 26 Nov: dive text 54, deck 93); e90 (changed on purpose, the live R90 alcobev deck: dive text 53 so the kept dives carry the demerger and revenue-basis fixes); deck89 (changed on purpose, owner 25 Nov: the theme deck remade as research): deck 92; e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e85 (LIVE21A, the R84 decks): deck 91, dive text 51 (updated on purpose); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose)
    assert json and computed and time        # (imports kept for the replays above)
