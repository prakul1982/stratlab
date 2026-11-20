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
