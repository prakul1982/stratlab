"""Lane e82 (Release 81): theme-engine items from LIVE18A and the R80 decks. Each test fails before its fix and passes after, except those
marked as guards."""
import copy
import json
import pathlib
import sys

from app import deck, public_themes
from app.intel import theme_base, theme_changes, theme_data, theme_routes
from tests.test_d53_fixes import inputs, replay

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import deck_check  # noqa: E402,F401

REST = "Other real estate investment trust companies"


def _placed(rel: str) -> dict:
    d = inputs(rel)
    figs = d.get("figures") or {}
    kw = {"published": d.get("published") or {}, "figures_of": (lambda s_, f=figs: f.get(s_))}
    if d.get("moved_before"):
        kw["moved_before"] = d["moved_before"]
    out = replay(copy.deepcopy(d), **kw)
    return {c["ticker"]: ("Other" if v.get("official") else theme_base._HALF_RX.sub("", v["layer"]), c)
            for v in out["value_chain"] for c in v["companies"]}


# ---------- 1a. LIVE18A-008 / R80 deck "layer vanished": a bank's lending layer is never a property layer ----------
def test_e82_regional_banks_keep_their_real_estate_focused_lenders_layer_on_the_live_input():
    """The live R80 Regional banks: "Real estate-focused lenders (bank)" emptied into "Other" ("their own words don't say property is its
    business"), quoting a bank's name, a forward-looking statement and offering proceeds."""
    got = _placed("r582/regbanks.json")
    lenders = {t for t, (lay, _) in got.items() if lay == "Real estate-focused lenders (bank)"}
    assert lenders == {"VLY", "TFSL", "PNFP", "CVBF", "PFS"}       # (CATY, FLG, WAFD, BKU, BBT: placed elsewhere by older rules, as before)
    assert not [t for t, (_, c) in got.items() if "property is its business" in str((c.get("refit") or {}).get("why") or "")]
    assert theme_base.property_scope_layer("Real estate-focused lenders (bank)", "Regional banks") is False
    # guard: a property developers' layer in a fertilizer theme is still the theme-scope case
    assert theme_base.property_scope_layer("Property developers", "Fertilizers and agrochemicals") is True
    assert theme_base.property_scope_layer("Property developers", "Real estate") is False


def test_e82_a_property_scope_reason_quotes_a_business_sentence_never_boilerplate():
    words = ("This report contains statements regarding our business plans and prospects and growth and operating strategies. "
             "Genus Prime Infra Ltd is engaged in trading of commodities and chemicals.")
    why, _ = theme_base.kind_bar("Property developers", {"ticker": "G", "name": "Genus Prime Infra Ltd"}, words, "Fertilizers and agrochemicals")
    assert "trading of commodities" in why and "statements regarding" not in why
    for boiler in ("Total net proceeds from the offering were approximately $6.9 million.",
                   "The second-step conversion was completed on October 31, 2023, with gross proceeds of $7.2 million."):
        assert theme_changes.work_sentence(boiler + " We are a savings bank serving Louisiana.") == "We are a savings bank serving Louisiana"


# ---------- 1b. LIVE18A-004: a lender on its principal business; no figure-reason memory; diversified owners not in towers ----------
OMEGA = ("Omega Healthcare Investors, Inc. is a self-administered real estate investment trust that invests in healthcare facilities, primarily "
         "skilled nursing and assisted living facilities, in the United States and the United Kingdom. Our portfolio consists of long-term "
         "triple-net leases and mortgages with healthcare operators. We also hold real estate loans and other investments.")
BREIT = ("We are the sole general partner of BREIT Operating Partnership L.P. (“BREIT OP”), and we own substantially all of our assets through "
         "BREIT OP. We currently operate our business in nine reportable segments: Rental Housing, Industrial, Net Lease, Data Centers, "
         "Hospitality, Self Storage, Retail, and Office properties, and Investments in Real Estate Debt.")
KREF = ("KREF is a real estate finance company that focuses primarily on originating and acquiring transitional senior loans secured by "
        "institutional-quality commercial real estate properties that are owned and operated by experienced and well-capitalized sponsors.")
PILLARSTONE = ("Pillarstone Capital REIT is a Maryland real estate investment trust engaged in investing in, owning and operating commercial "
               "properties. Its properties are retail centres leased to tenants in Texas.")


def test_e82_a_property_owner_whose_later_words_name_loans_stays_with_the_owners_and_a_lender_moves():
    vc = [{"layer": "Healthcare property owners", "companies": [{"ticker": "OHI", "name": "Omega Healthcare Investors Inc"}]},
          {"layer": "Residential landlords", "companies": [{"ticker": "BSTT", "name": "Blackstone Real Estate Income Trust, Inc."},
                                                            {"ticker": "KREF", "name": "KKR Real Estate Finance Trust Inc."}]},
          {"layer": "Mortgage REITs", "companies": [{"ticker": "BXMT", "name": "Blackstone Mortgage Trust"}]},
          {"layer": REST, "official": True, "basis": "rest", "companies": []}]
    words = {"OHI": OMEGA, "BSTT": BREIT, "KREF": KREF}
    out, rows = theme_base.kind_bars(vc, words.get, "Real estate investment trusts")
    at = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert at["OHI"] == "Healthcare property owners" and at["BSTT"] == "Residential landlords"
    assert at["KREF"] == "Mortgage REITs"                       # guard: a lender in its principal words still moves
    assert [r["ticker"] for r in rows] == ["KREF"]


def test_e82_a_property_owner_is_never_put_in_a_lending_layer_on_shared_words():
    """Pillarstone: "investing in, owning and operating commercial properties" put in "Mortgage REITs" by compute_fit's words shared."""
    vc = [{"layer": "Towers, data centres and niche property", "companies": [{"ticker": "PRLEQ", "name": "Pillarstone Capital REIT", "placed": "ai"},
                                                                            {"ticker": "AMT", "name": "American Tower"}]},
          {"layer": "Mortgage REITs", "description": "They invest in real estate debt and commercial properties' loans, investing capital.",
           "companies": [{"ticker": "BXMT"}, {"ticker": "ARI"}]},
          {"layer": REST, "official": True, "basis": "rest", "companies": []}]
    words = {"PRLEQ": PILLARSTONE, "AMT": "We own and operate communications towers."}
    out, rows = theme_base.compute_fit(vc, words.get, "Real estate investment trusts")
    at = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert at["PRLEQ"] != "Mortgage REITs"


def test_e82_a_move_made_for_no_stored_figure_is_no_memory_a_later_placement_holds():
    """Franklin BSP: R79 moved it out of "Mortgage REITs" "with no figure stored"; R80 kept it out on that memory ("the last re-check moved
    it out of that layer, and it stays out")."""
    got = {"log": [{"moved": [{"symbol": "FBRT", "from": "Mortgage REITs", "to": REST,
                               "why": "listed in “Mortgage REITs” with no figure stored: not counted as the layer's until it is read"},
                              {"symbol": "X", "from": "Office landlords", "to": REST, "why": "its own words name retail property"}]}]}
    assert theme_changes.move_memory(got) == {"X": ["Office landlords", REST]}


def test_e82_a_diversified_owner_of_commercial_property_is_not_in_towers_and_data_centres():
    vc = [{"layer": "Towers, data centres and niche property", "companies": [
              {"ticker": "MDRR", "name": "Medalist Diversified, Inc."}, {"ticker": "SQFT", "name": "Presidio Property Trust, Inc."},
              {"ticker": "LAND", "name": "Gladstone Land Corp"}, {"ticker": "NLCP", "name": "NewLake Capital Partners, Inc."},
              {"ticker": "AMT", "name": "American Tower Corp"}]},
          {"layer": REST, "official": True, "basis": "rest", "companies": []}]
    words = {"MDRR": "Medalist Diversified, Inc. serves as the general partner of Medalist Diversified Holdings, LP.",
             "SQFT": "Presidio Property Trust is an internally-managed REIT. We own 10 commercial properties in fee interest.",
             "LAND": "We are an agricultural REIT primarily in the business of owning and leasing farmland.",
             "NLCP": "We owned a geographically diversified portfolio of 34 cannabis properties.",
             "AMT": "We own and operate communications towers."}
    out, rows = theme_base.kind_bars(vc, words.get, "Real estate investment trusts")
    assert {r["ticker"] for r in rows} == {"MDRR", "SQFT"}      # farmland, cannabis and towers stay (niche property)


def test_e82_reits_replay_moves_breit_to_other_and_keeps_the_owners():
    got = _placed("r66/reits.json")
    assert got["BSTT"][0] == "Other" and "non-traded" in got["BSTT"][1]["refit"]["why"]
    assert got["OHI"][0] == "Healthcare property owners" and got["FBRT"][0] == "Mortgage REITs"
    assert got["SQFT"][0] == "Other" and got["KREF"][0] == "Mortgage REITs" and got["SACH"][0] == "Mortgage REITs"
    assert got["AMT"][0] == got["LAND"][0] == got["NLCP"][0] == "Towers, data centres and niche property"


# ---------- 3. LIVE18A-003: one source of own words: the members table quotes what the dive may quote ----------
ALAB = ("Astera Labs, Inc., headquartered in San Jose, California, is a fabless manufacturing company that develops connectivity technologies. "
        "The company specializes in PCIe retimers for data centers.")
MSFT = ("Microsoft Corporation is an American multinational technology conglomerate headquartered in Redmond, Washington. The company became "
        "influential in the rise of personal computers through software like Windows and has since expanded into areas such as Internet "
        "services, cloud computing, artificial intelligence and video gaming among others.")


def test_e82_the_members_table_never_quotes_an_encyclopedia_sentence_the_dive_refuses():
    m = {"sector": "Quantum computing", "value_chain": [{"layer": "Other quantum computing companies", "official": True, "companies": [
        {"ticker": "ALAB", "name": "Astera Labs", "what": ALAB.split(". ")[0]},
        {"ticker": "MSFT", "name": "Microsoft", "what": MSFT.split(". ")[1]},
        {"ticker": "IONQ", "name": "IonQ", "what": "We are developing quantum computers based on trapped ions"}]}]}
    about = {"ALAB": ALAB, "MSFT": MSFT, "IONQ": "We are developing quantum computers based on trapped ions. We sell access through clouds."}
    got = {c["ticker"]: c["what"] for v in theme_base.described(m, about.get, "US")["value_chain"] for c in v["companies"]}
    assert got["ALAB"] == "" and got["MSFT"] == "" and got["IONQ"].startswith("We are developing quantum computers")
    # a map stored before: its lines kept only while the quotable words hold them (theme_data.quoted_line), the stored words as the dive reads them
    assert theme_data.quoted_line(ALAB.split(". ")[0], ALAB, "US") == ""
    assert theme_data.quoted_line(MSFT.split(". ")[1], MSFT, "US") == ""
    w = "We are developing quantum computers based on trapped ions"
    assert theme_data.quoted_line(w, about["IONQ"], "US") == w                      # guard
    assert theme_data.quoted_line("Makes cement and clinker", "", "IN") == "Makes cement and clinker"   # guard: no words stored, a plain line


def test_e82_a_served_map_drops_the_stored_encyclopedia_lines(monkeypatch):
    m = {"sector": "Semiconductors", "generated_at": "x", "value_chain": [{"layer": "Connectivity", "companies": [
        {"ticker": "ALAB", "name": "Astera Labs", "what": ALAB.split(". ")[0]}, {"ticker": "NVDA", "name": "Nvidia", "what": "We design GPUs"}]}]}
    words = {"ALAB": ALAB, "NVDA": "We design GPUs. We sell systems."}
    monkeypatch.setattr(theme_routes, "kept_about", lambda r: words.get)
    theme_routes._WHATS.clear()
    got = {c["ticker"]: c["what"] for c in theme_routes.own_whats("US", m)["value_chain"][0]["companies"]}
    assert got == {"ALAB": "", "NVDA": "We design GPUs"}


# ---------- 5. LIVE18A-005/006: one count; the true reason for each company a page doesn't list; posts say the page's count ----------
def test_e82_a_page_says_a_company_listed_twice_never_not_confirmed():
    """Indian Pharma "211 companies ... (1 more of the theme's 212 not listed: not confirmed by their own words or official industry yet)"
    beside "205 description-verified, 7 industry-supported, 0 not checked"."""
    p = {"sector": "Pharma", "value_chain": [{"layer": "Generics", "companies": [
        {"ticker": "A", "name": "A", "verified": True}, {"ticker": "B", "name": "B", "verified": True}, {"ticker": "B2", "name": "B", "verified": True}]}]}
    dive = {"evidence": {"A": "description_verified", "B": "description_verified", "B2": "description_verified"},
            "duplicates": [{"symbol": "B2", "kept": "B"}], "tally": {"total": 3, "description_verified": 3, "membership_unverified": 0}}
    c = public_themes.counts(p, dive)
    assert c["listed"] == 2 and c["all"] == 3
    said = public_themes.unlisted_said(c)
    assert "not confirmed" not in said and said == "1 more of the theme's 3 not listed: the same company under a second symbol, listed once"
    # one the membership check counts that no stored layer holds
    dive2 = {**dive, "duplicates": [], "tally": {"total": 4}}
    p2 = {"sector": "Pharma", "value_chain": [{"layer": "Generics", "companies": p["value_chain"][0]["companies"]}]}
    assert "counted by the membership check, in none of the stored layers" in public_themes.unlisted_said(public_themes.counts(p2, dive2))


def test_e82_a_theme_post_keeps_a_proper_first_word_and_is_written_again_when_its_page_count_moves():
    from app import blog_research as BR
    assert BR._lower_first("Indian Pharma") == "Indian Pharma" and BR._lower_first("Cybersecurity") == "cybersecurity"
    old = {"v": 2, "rows": [], "members": 5, "total": 252, "chain": {}, "page_counts": {"listed": 252, "layers": 10, "all": 252}}
    assert BR.figures_moved(old, {**old, "page_counts": {"listed": 252, "layers": 11, "all": 252}})
    assert not BR.figures_moved(old, dict(old))                                    # guard


# ---------- 2. LIVE18A-004/007: FFO with its basis on every surface; medians of one basis ----------
def _ffo_rows():
    def row(s_, nm, ffo, p, share, basis):
        return {"symbol": s_, "name": nm, "ffo": ffo, "p_ffo": p, "ffo_share": share, "ffo_basis": basis}
    # the R80 REITs deck's rows: Camden's reported $745 m (P/FFO 12.90x, 47.3%) printed under "Derived FFO" / "P/FFO (derived)"
    return [row("CPT", "Camden Property Trust", 744.8, 12.9, 47.3, "reported"), row("ESS", "Essex", 1100.0, 17.0, 55.0, "reported"),
            row("MAA", "Mid-America", 1000.0, 15.0, 45.0, "reported"), row("AKR", "Acadia", 172.0, 16.6, 41.8, "derived"),
            row("ADC", "Agree", 438.0, 20.8, 61.0, "derived")]


def test_e82_the_sector_table_marks_each_ffo_with_its_basis_under_headers_that_name_neither():
    from app.intel import metric_registry as R
    assert R.BY_ID["ffo"].label == "FFO" and R.BY_ID["p_ffo"].label == "P/FFO" and R.BY_ID["ffo_share"].label == "FFO / revenue"
    rows = _ffo_rows()
    fmt_amt = lambda x: f"${x:,.0f} m"            # noqa: E731
    assert deck._state_cell(rows[0], "ffo", None, fmt_amt) == "$745 m (reported)"
    assert deck._state_cell(rows[0], "p_ffo", None, deck.sector_fmt("p_ffo")) == "12.90x (reported)"
    assert deck._state_cell(rows[3], "ffo_share", None, deck.sector_fmt("ffo_share")) == "41.8% (derived)"
    assert deck._state_cell({"sbc_share": 1.6}, "sbc_share", None, deck.sector_fmt("sbc_share")) == "1.6%"          # guard


def test_e82_the_themes_ffo_medians_are_of_one_basis_and_say_it():
    from app.intel import sector_metrics, theme_data as td
    rows = _ffo_rows()
    meds = {k: {"median": 99.0, "n": 5, "of": 5} for k in ("ffo", "p_ffo", "ffo_share", "sbc_share")}
    got = sector_metrics.one_ffo_basis(rows, ["ffo", "p_ffo", "ffo_share", "sbc_share"], meds, td.stat)
    assert got["ffo_basis"] == "reported" and got["ffo_apart"] == 2
    assert got["medians"]["p_ffo"]["median"] == 15.0 and got["medians"]["p_ffo"]["n"] == 3 and got["medians"]["p_ffo"]["of"] == 5
    assert got["medians"]["sbc_share"]["median"] == 99.0                       # guard: another figure untouched
    fam = {"n": 5, "of": 5, "headline": ["p_ffo", "ffo_share"], "keys": ["p_ffo", "ffo_share"], **got}
    line = " ".join(deck.sector_lines({"sector": {"families": {"us": fam}}}, waiting=False))
    assert "P/FFO on reported FFO 15.00x (3 of 5)" in line and "FFO / revenue on reported FFO" in line
    assert "FFO medians of reported FFO only, 2 on derived FFO apart" in line and "derived FFO / revenue" not in line


def test_e82_the_app_and_the_public_page_show_ffo_with_its_basis():
    from app.intel import theme_data as td
    rows = _ffo_rows()
    v = td.p_ffo_of(rows)
    assert v["p_ffo"]["median"] == 15.0 and v["p_ffo_basis"] == "reported" and v["p_ffo_apart"] == 2
    lead = td.leaders([{**r, "cap": 9630.0} for r in rows])
    assert lead[0]["p_ffo"] == 12.9 and lead[0]["ffo_basis"] == "reported"
    dive = {"layers": [{"layer": "Residential landlords", "companies": rows}]}
    assert public_themes.reported_ffos(dive) == {"CPT": 744.8, "ESS": 1100.0, "MAA": 1000.0}        # derived: StratLab's, never on the page
    page = {"region": "US", "label": "REITs", "slug": "reits", "name": "reit", "evidence": None, "older": False, "rechecking": False,
            "summary": "", "members": 2, "all": 2, "counts": {"listed": 2, "layers": 1, "all": 2, "unlisted": []}, "tally_at": None,
            "prices": None, "day": None, "indexable": False,
            "layers": [{"name": "Residential landlords", "evidence": None, "companies": [
                {"symbol": "CPT", "name": "Camden Property Trust", "page": None, "cap": "$9.6B", "revenue": "$1.6B", "year": "2025",
                 "evidence": None, "ffo": "$744.8M (reported)"},
                {"symbol": "AKR", "name": "Acadia", "page": None, "cap": "$2.9B", "revenue": "$0.4B", "year": "2025", "evidence": None}]}]}
    html_ = public_themes.render(page)
    assert '<th scope="col">FFO</th>' in html_ and "$744.8M (reported)" in html_ and "data-ffo-note" in html_


# ---------- 4. LIVE18A-002: a fresh theme is published only once it passes the quality gate ----------
def _quantum(own_n: int, total: int = 386, how: str = "ai") -> dict:
    hw = [{"ticker": f"H{i}", "name": f"H{i}", "base": True, "basis": "industry"} for i in range(total - own_n)]
    own = [{"ticker": f"Q{i}", "name": f"Q{i}", "verified": True} for i in range(own_n)]
    return {"sector": "Quantum computing", "placements": {"checked": True, "industries_by": how},
            "value_chain": [{"layer": "Quantum processors", "companies": own},
                            {"layer": "Computer Peripheral Equipment", "official": True, "basis": "industry", "companies": hw}]}


def test_e82_a_theme_of_broad_ai_picked_industries_or_an_unfinished_check_is_not_public():
    from app.intel import theme_library as TL
    assert TL.broad_industries(_quantum(3)) is True                    # 3 of 386 in the AI's own layers
    assert TL.broad_industries(_quantum(60)) is False                  # guard: the AI's layers hold enough of them
    assert TL.broad_industries(_quantum(3, how="list")) is False       # guard: the curated table's industries
    assert TL.broad_industries(_quantum(3, total=40)) is False         # guard: a small theme
    meta = {"rules": theme_base.RULES, "broad": False}
    assert "not checked yet" in TL.gate_why(meta, {"all": 386, "listed": 197, "unlisted": [["not checked yet", 189]]})
    # (updated on purpose, e83: with no dive kept there is no count to judge by (the page shows none); a dive kept with no count is judged
    # on its own tally of companies not checked)
    assert TL.gate_why(meta, None) == ""
    assert TL.gate_why(meta, {"total": 386}, unchecked=189) == "189 of its 386 companies not checked yet"
    assert TL.gate_why({**meta, "broad": True}, {"all": 386, "listed": 386, "unlisted": []}).startswith("its companies come almost all")
    assert TL.gate_why(meta, {"all": 24, "listed": 23, "unlisted": [["not checked yet", 1]]}) == ""       # guard: Space and satellites
    assert TL.gate_why({"rules": 76}, None) == ""                                                         # guard: kept before the gate


def test_e82_the_themes_list_leaves_out_a_theme_whose_newest_entry_fails_the_gate(monkeypatch):
    from app import computed
    from app.intel import theme_library as TL
    idx = {"entries": {
        "a": {"region": "US", "label": "Quantum computing", "at": 2.0, "meta": {"q": "quantum computing", "rules": theme_base.RULES, "broad": True}},
        "b": {"region": "US", "label": "Quantum computing", "at": 1.0, "meta": {"q": "quantum computing", "rules": theme_base.RULES - 1}},
        "c": {"region": "US", "label": "Semiconductors", "at": 1.0, "meta": {"q": "semiconductor", "rules": theme_base.RULES, "broad": False}}}}
    dives = {"entries": {"d": {"region": "US", "at": 1.0, "meta": {"q": "semiconductor", "pub": {"all": 104, "listed": 102, "unlisted": []}}}}}
    monkeypatch.setattr(computed, "index", lambda kind: idx if kind == TL.KIND else dives)
    assert [x["name"] for x in public_themes.entries("US")] == ["semiconductor"]


# ---------- 7. R80 Biotech informative 505 -> 491: clinical-stage companies sent to "Other" when the AI renamed their layer ----------
def test_e82_a_company_left_out_of_a_renamed_layer_goes_to_the_layer_its_words_say_never_other():
    words = {f"C{i}": f"C{i} Medicine is a clinical-stage genome editing company dedicated to developing transformative medicines."
             for i in range(6)}
    words["V"] = "Valneva is a vaccine company developing, producing and selling vaccines."      # guard: one shared word
    cos = [{"ticker": s_, "name": f"{s_} Medicine Inc" if s_ != "V" else "Valneva SE", "model_out": "unknown"} for s_ in words]
    words.update({"K1": "K1 sells commercial specialty medicines for rare diseases.", "K2": "K2 markets commercial specialty drugs."})
    cos += [{"ticker": "K1", "name": "K1"}, {"ticker": "K2", "name": "K2"}]
    vc = [{"layer": "Commercial specialty biotechs", "description": "They sell approved specialty medicines.", "companies": cos},
          {"layer": "Clinical-stage platform developers", "description": "Clinical-stage companies developing therapies on a platform.",
           "companies": [{"ticker": "P1", "name": "P1"}, {"ticker": "P2", "name": "P2"}]},
          {"layer": "Other biotech companies", "official": True, "basis": "rest", "companies": []}]
    out, rows = theme_base.listed_out(vc, words.get, "Biotechnology")
    at = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert all(at[f"C{i}"] == "Clinical-stage platform developers" for i in range(6)), at
    assert at["K1"] == at["K2"] == "Commercial specialty biotechs"
    assert at["V"] == "Other biotech companies"
    assert any("they say what “Clinical-stage platform developers” is" in r["why"] for r in rows)


# ---------- 6. LIVE18A-010: the dive the re-check keeps is the one the page reads after prices move ----------
def test_e82_the_dives_key_does_not_follow_the_figures_window(monkeypatch):
    cos = [{"ticker": f"S{i}", "name": f"S{i}", "what": "We make chips" if i % 2 else "", "cap": 100.0 - i} for i in range(10)]
    m = {"_library": "semiconductor", "generated_at": 1.0, "placements": {"placed": 10},
         "value_chain": [{"layer": "Semiconductors", "official": True, "companies": cos}]}
    k1 = theme_routes.dive_key("US", "Semiconductors", m)
    # a close moves a described company across the figures' window's edge
    monkeypatch.setattr(theme_base, "for_figures", lambda m_: ({**m_, "value_chain": [{**m_["value_chain"][0], "companies": cos[:3]}]}, None))
    assert theme_routes.dive_key("US", "Semiconductors", m) == k1


def test_e82_a_public_tally_is_dated_in_the_markets_own_day():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    assert str(theme_routes.market_day("US")) == datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    assert str(theme_routes.market_day("IN")) == datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()


def test_e82_versions():
    from app import blog_research
    from app.intel import sector_metrics
    assert theme_base.RULES == 80 and theme_routes.PLACE_CARRY[80] == 79 and theme_routes.PLACE_CARRY[79] == 78 and theme_routes.PLACE_CARRY[78] == 77 and theme_routes.PLACE_CARRY[77] == 76 and theme_routes.EARLIER_MAX == 35          # e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose)
    assert theme_data.DIVE_TEXT == 57 and deck.THEME_DECK_VERSION == 96 and blog_research.GEN == 12 and sector_metrics.VERSION == 3          # deck99 (changed on purpose, the deck96 audit's open items, 27 Nov: dive text 57, deck 96); rel98 (fix98 and map98 together, 27 Nov: dive text 56, deck 95, changed on purpose); map98 (a company of the map's own layers whose own first business sentence states another principal business listed as other work); fix98 (changed on purpose, members no longer listed: dive text 55, deck 94); deck96 (changed on purpose, every live theme deck checked 26 Nov: dive text 54, deck 93); e90 (changed on purpose, the live R90 alcobev deck: dive text 53 so the kept dives carry the demerger and revenue-basis fixes); deck89 (changed on purpose, owner 25 Nov: the theme deck remade as research): deck 92; e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e85 (LIVE21A, the R84 decks): deck 91, dive text 51 (updated on purpose); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose)
