"""Lane e78: the owner's review of the live R76 decks (8.85/10): the REIT revenue denominator, metric eligibility, the residential layer,
moves into "Other" with their effect, derived FFO, cross-theme terminology and a page of one dated update."""
import json
import pathlib
import sys
from datetime import datetime, timezone

import pytest

from app import deck, stock_pages
from app.intel import metric_registry as R
from app.intel import sec
from app.intel import theme_base as B
from app.intel import theme_routes as TR
from tests.test_m2_text import updates_view

ROOT = pathlib.Path(__file__).resolve().parents[1]
R66 = ROOT / "tests/fixtures/themes_live/r66/reits.json"


def _flow(val, start="2025-01-01", end="2025-12-31", form="10-K", filed="2026-02-20", fy=2025):
    return {"start": start, "end": end, "val": val, "form": form, "filed": filed, "fy": fy, "fp": "FY", "accn": "0000-26-1"}


def _facts(**lines):
    return {"us-gaap": {c: {"units": {"USD": rows if isinstance(rows, list) else [_flow(rows)]}} for c, rows in lines.items()}}


# ---------- 1. the revenue denominator: the principal revenue line, never a part far below it ----------
def test_camden_revenue_is_its_property_revenue_never_its_fee_income():
    """Fails before: Camden's 2025 10-K tags its fee and asset-management income, $12.967 m, as contract revenue (its only top-line concept)
    and its property revenues, $1,573.544 m, as lease income: the deck showed revenue $13 m and a net margin "n.m."."""
    f = _facts(RevenueFromContractWithCustomerExcludingAssessedTax=12_967_000, OperatingLeaseLeaseIncome=1_573_544_000)
    rev = sec.revenue(f, "annual")
    assert rev["2025-12-31"] == 1_573_544_000
    assert sec.revenue_basis(f, "2025-12-31", rev["2025-12-31"]) == "OperatingLeaseLeaseIncome"


def test_a_total_revenues_line_far_below_the_leasing_revenue_gives_way_to_the_statements_total():
    """Triton International: Revenues $59.5 m beside $1,221.5 m of leasing revenue; its operating profit plus total costs, $1,377.2 m, is the
    income statement's own total."""
    f = _facts(Revenues=59_500_000, OperatingLeaseLeaseIncome=1_221_500_000, OperatingIncomeLoss=600_000_000, CostsAndExpenses=777_200_000)
    assert sec.revenue(f, "annual")["2025-12-31"] == 1_377_200_000


def test_a_total_revenues_line_near_the_lease_income_stands_and_a_company_without_lease_income_is_unchanged():
    # Agree Realty: Revenues $718.4 m, lease income $737.6 m (gross of what it nets): its filed total stands
    assert sec.revenue(_facts(Revenues=718_400_000, OperatingLeaseLeaseIncome=737_600_000), "annual")["2025-12-31"] == 718_400_000
    assert sec.revenue(_facts(RevenueFromContractWithCustomerExcludingAssessedTax=50_000_000), "annual")["2025-12-31"] == 50_000_000
    # a contract-revenue part above the lease income is no part of it (a hotel owner's room revenue beside a little rent)
    f = _facts(RevenueFromContractWithCustomerExcludingAssessedTax=900_000_000, OperatingLeaseLeaseIncome=40_000_000)
    assert sec.revenue(f, "annual")["2025-12-31"] == 900_000_000


def test_quarters_take_the_principal_line_too():
    q = [_flow(3_000_000, "2026-07-01", "2026-09-30", "10-Q", "2026-10-30", 2026)]
    lease = [_flow(381_100_000, "2026-07-01", "2026-09-30", "10-Q", "2026-10-30", 2026)]
    f = _facts(RevenueFromContractWithCustomerExcludingAssessedTax=q, OperatingLeaseLeaseIncome=lease)
    assert sec.revenue(f, "quarter")["2026-09-30"] == 381_100_000


def test_a_page_built_before_the_principal_line_with_revenue_below_its_profit_is_built_again_once():
    old = {"region": "US", "years": [{"year": "Dec 2025", "sales": 13.0, "profit": 168.0}]}
    assert stock_pages.revenue_part_due(old)
    assert not stock_pages.revenue_part_due({**old, "rev_rule": sec.PRINCIPAL_RULE})        # built with the rule: never again by it
    assert not stock_pages.revenue_part_due({**old, "years": [{"year": "Dec 2025", "sales": 1573.5, "profit": 168.0}]})
    assert not stock_pages.revenue_part_due({**old, "region": "IN"})
    now = 2_000_000_000.0
    stored = {"ts": now - 2 * stock_pages.UNREAD_FRESH, "facts": {**old, "v": stock_pages.FACTS_VERSION}}
    assert not stock_pages.fresh(stored, "US", now)                     # rebuilt when next opened (at most hourly)


# ---------- 2. metric eligibility in one place ----------
def _stwd():
    return {"symbol": "STWD", "name": "Starwood Property Trust, Inc.", "profile": "other", "ffo": 490.0, "ffo_share": 26.6, "p_ffo": 8.4,
            "sbc_share": 3.3, "fcf_margin": 5.4, "sector_src": {"ffo_share": {"period": "FY"}, "p_ffo": {"period": "FY"}, "sbc_share": {}}}


def test_a_mortgage_reits_property_ffo_is_never_kept_on_its_row():
    """Fails before: the notes said FFO is not applicable to mortgage REITs, yet Starwood's row carried FFO / revenue 26.6% and P/FFO 8.4x into
    the Mortgage REITs layer and the sector table."""
    r = _stwd()
    gone = R.withhold_inapplicable("US", r, ("ffo", "ffo_share", "affo_share", "p_ffo", "sbc_share", "fcf_margin"), "lending")
    assert set(gone) == {"ffo", "ffo_share", "p_ffo"}
    assert r["ffo"] is None and r["ffo_share"] is None and r["p_ffo"] is None and r["sbc_share"] == 3.3
    assert "ffo_share" not in r["sector_src"] and r["not_applicable"] == ["ffo", "ffo_share", "p_ffo"]
    landlord = {**_stwd(), "symbol": "SPG"}
    assert R.withhold_inapplicable("US", landlord, ("ffo", "ffo_share", "p_ffo"), "property") == [] and landlord["ffo_share"] == 26.6
    assert not R.applies("p_ffo", "US", R.tags("US", {"profile": "other"}, "lending"))
    assert R.applies("p_ffo", "US", R.tags("US", {"profile": "other"}, "property"))


def test_the_deck_says_a_withheld_ffo_is_not_applicable_never_missing():
    r = _stwd()
    R.withhold_inapplicable("US", r, ("ffo", "ffo_share", "p_ffo"), "lending")
    v = {"region": "US", "layers": [{"layer": "Residential landlords", "model": {"family": "property"},
                                     "companies": [{**r, "revenue": 1840.0, "profit": 410.0}]}]}
    st = deck.ffo_states(v)
    assert st["na"] == ["Starwood Property Trust, Inc."] and not st["missing"] and not st["available"]


# ---------- 3. the residential layer ----------
def test_a_concepts_words_are_read_with_the_companys_name_aside_not_each_word_it_shares():
    """Fails before: every word of "American Homes 4 Rent" was taken out of its sentence, leaving "single-family as rental properties"."""
    t = ("American Homes 4 Rent (“AMH” or the “General Partner”) is an internally managed Maryland real estate investment trust. We are focused "
         "on developing, renovating, leasing and managing single-family homes as rental properties.")
    assert B.name_aside("American Homes 4 Rent is a REIT", "American Homes 4 Rent").strip() == "is a REIT"
    line = B.layer_line("", t, "American Homes 4 Rent", "Residential landlords")
    assert "single-family homes as rental properties" in line
    assert not B.layer_line("", "Apartment Income REIT Corp is a holding company.", "Apartment Income REIT Corp", "Residential landlords")


def test_a_move_out_under_a_narrower_earlier_name_is_no_finding_on_the_layer_as_it_is():
    assert B.narrower_name("Manufactured housing and RV communities", "Residential landlords")
    assert not B.narrower_name("Residential landlords", "Residential landlords")
    assert not B.narrower_name("Residential landlords", "Manufactured housing and RV communities")
    assert not B.narrower_name("Fabless chip design", "Chip designers")          # no kinds of property: nothing to judge


def test_essex_10k_opening_passes_over_its_reit_tax_status_to_its_apartment_communities():
    """Fails before: Essex's 10-K opening, read to 700 characters, was its REIT tax election and taxable REIT subsidiaries."""
    text = "\n".join([
        "Item 1. Business", "OVERVIEW",
        "Essex Property Trust, Inc. (“Essex”), a Maryland corporation, is an S&P 500 company that operates as a self-administered and "
        "self-managed real estate investment trust (“REIT”). Essex owns all of its interest in its real estate and other investments directly "
        "or indirectly through Essex Portfolio, L.P. (the “Operating Partnership” or “EPLP”). Essex is the sole general partner of the Operating "
        "Partnership and as of December 31, 2025, had an approximately 96.6% general partner interest in the Operating Partnership.",
        "Essex has elected to be treated as a REIT for federal income tax purposes commencing with the year ended December 31, 1994. In order to "
        "maintain compliance with REIT tax rules, the Company utilizes taxable REIT subsidiaries for various revenue generating or investment "
        "activities. A domestic taxable REIT subsidiary is subject to federal income tax as a regular C Corporation. All taxable REIT subsidiaries "
        "are consolidated by the Company for financial reporting purposes.",
        "The Company is engaged primarily in the ownership, operation, management, acquisition, development and redevelopment of predominantly "
        "apartment communities, located along the West Coast of the United States. As of December 31, 2025, the Company owned or had ownership "
        "interests in 259 operating apartment communities, aggregating 63,077 apartment homes.",
        "BUSINESS STRATEGIES", "x " * 900])
    got = sec.business_opening(text)
    assert "apartment communities" in got and "taxable REIT" not in got and "elected to be treated" not in got
    assert sec.BUSINESS_KEY[1] == 5          # (updated on purpose, e85: 5, a sentence of an operating company held as an LLC passed over)
    stored = ("Essex Property Trust, Inc. is an S&P 500 company that operates as a self-managed REIT. Essex has elected to be treated as a REIT "
              "for federal income tax purposes commencing with the year ended December 31, 1994.")
    assert sec.reit_tax_said(stored)
    assert TR.thin_about({"about": stored, "v": TR.ABOUT_V, "bv": 3, "at": "2026-11-18"}, "US", "Essex Property Trust, Inc.")


@pytest.fixture(scope="module")
def r66_replay():
    sys.path.insert(0, str(ROOT / "scripts"))
    import release_gate as G
    essex = ("Essex Property Trust, Inc. (“Essex”), a Maryland corporation, is an S&P 500 company that operates as a self-administered and "
             "self-managed real estate investment trust (“REIT”). The Company is engaged primarily in the ownership, operation, management, "
             "acquisition, development and redevelopment of predominantly apartment communities, located along the West Coast of the United States.")
    out = {}
    for k, words in (("stored", None), ("read_again", essex)):
        d = G.load(R66)
        if words:
            d["evidence"]["ESS"] = words
        with G.offline():
            got, _ = G.engine(d)
        out[k] = {c["ticker"]: (v["layer"], (c.get("refit") or {}).get("why")) for v in got["value_chain"] for c in v["companies"]}
    return out


def test_american_homes_and_essex_go_to_the_residential_layer_on_their_own_words(r66_replay):
    """Fails before: on the stored R66 REITs input American Homes 4 Rent and Essex sat in "Other", "the last re-check moved it out of that
    layer, and it stays out"; Essex's words as its 10-K's opening now reads them say "apartment communities"."""
    st, again = r66_replay["stored"], r66_replay["read_again"]
    assert st["AMH"][0] == "Residential landlords"
    assert again["ESS"][0] == "Residential landlords" and again["AMH"][0] == "Residential landlords"
    # on its stored words (its REIT tax status, nothing of what it owns) Essex stays where it is published, never on the narrower name's move
    assert st["ESS"][0].startswith("Other ") and "last re-check moved it out" not in (st["ESS"][1] or "")
    for s_ in ("CPT", "MAA", "UDR", "SUI", "ELS", "INVH"):
        if s_ in st:
            assert st[s_][0] == again[s_][0]


def test_rules_are_bumped_and_carried():
    assert B.RULES == 79 and TR.PLACE_CARRY[78] == 77 and TR.PLACE_CARRY[77] == 76 and TR.PLACE_CARRY[76] == 75 and TR.PLACE_CARRY[75] == 74 and TR.PLACE_CARRY[74] == 73 and TR.PLACE_CARRY[73] == 72 and TR.EARLIER_MAX == 34  # e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose); e80 (LIVE16A, the R78 decks): RULES 75, PLACE_CARRY[75] = 74, EARLIER_MAX 30, deck 86, dive text 46 (updated on purpose); e79 (the live R77 decks): RULES 74, PLACE_CARRY[74] = 73, EARLIER_MAX 29, deck 85, dive text 45 (updated on purpose)


# ---------- 4. moves into "Other": each with its reason, and the effect ----------
def test_the_informative_row_names_each_move_into_other_with_its_reason_and_the_effect():
    other = "Other IT service companies"
    v = {"coverage": {"other_name": other}, "changes": {"entries": [
        {"d": "2026-11-18", "moved": [{"symbol": "AXIS", "name": "Axis Solutions Ltd", "from": "Makers of their own products", "to": other,
                                       "why": "its own words hold no line that says what “Makers of their own products” is"},
                                      {"symbol": "TATAELXSI", "name": "Tata Elxsi Limited", "from": other, "to": "Engineering R&D services",
                                       "why": "its own words say what no other layer sells"}]},
        {"d": "2026-11-16", "moved": [{"symbol": "KSS", "name": "KS Smart Technlogies Limited", "from": "Makers of their own products", "to": other},
                                      {"symbol": "AXIS", "name": "Axis Solutions Ltd", "from": "IT infrastructure", "to": "Makers of their own products",
                                       "why": "x"}]}]}}
    got = deck.other_drift(v)
    assert got.startswith("over the 2 stored changes since 16 Nov 2026: 2 moved into “Other IT service companies”, each with its recorded reason:")
    assert "Axis Solutions Ltd (from “IT infrastructure”: its own words hold no line" in got
    assert "KS Smart Technlogies Limited (from “Makers of their own products”: no reason recorded)" in got
    assert "1 moved out of it into a layer the map names" in got and got.endswith("(1 fewer in informative layers from these moves)")
    assert deck.other_drift({"coverage": {"other_name": other}, "changes": {"entries": []}}) == ""


# ---------- 5. derived FFO ----------
def test_ffo_is_labelled_derived_with_what_it_leaves_out_of_nareit_ffo():
    # (updated on purpose, e82 LIVE18A-007: FFO, P/FFO and FFO / revenue are of a company's reported FFO where it reports one, so their
    # labels say FFO and each figure says its basis; AFFO is only ever derived, its labels still say so)
    for k in ("ffo", "ffo_share", "affo_share", "p_ffo", "affo"):
        m = R.BY_ID[k]
        assert "derived" in m.label.lower() or ("derived FFO, an approximation of Nareit FFO" in m.definition and "(reported)" in m.definition)
        assert "impairments of depreciable real estate" in m.limit and "joint ventures" in m.limit and "approximation of Nareit FFO" in m.limit
    assert "derived FFO, an approximation of Nareit FFO" in R.BY_ID["ffo_share"].definition
    cols = dict((k, lab) for k, lab, _ in deck.CO_COLS)
    assert cols["ffo_share"] == "FFO / revenue" and cols["p_ffo"] == "P/FFO" and cols["affo_share"] == "Derived AFFO / revenue"
    v = {"region": "US", "layers": [{"layer": "Office landlords", "model": {"family": "property"},
                                     "companies": [{"symbol": "BXP", "name": "BXP", "revenue": 3400.0, "profit": 10.0, "ffo_share": 30.0}]}]}
    got = deck.not_in_sources(v)
    assert "derived FFO (an approximation of Nareit FFO, impairments of depreciable real estate and the adjustments for unconsolidated" in got
    assert "FFO (NAREIT)" not in got


# ---------- 6. another theme's terminology only on membership evidence ----------
def _fert(with_figures: bool):
    devs = [{"symbol": s, "name": s, "status": "confirmed", "revenue": 22.0 if with_figures and s == "BHARATAGRI" else None, "profit": None}
            for s in ("GENUSPRIME", "BHARATAGRI", "SFPIL")]
    return {"region": "IN", "layers": [
        {"layer": "Urea and nitrogen fertiliser makers", "model": {"family": "making"},
         "companies": [{"symbol": "CHAMBLFERT", "name": "Chambal", "status": "confirmed", "revenue": 20000.0, "profit": 1500.0}]},
        {"layer": "Property developers", "model": {"family": "development"}, "companies": devs}]}


def test_property_developers_words_never_said_of_a_layer_with_no_company_of_it_with_figures():
    """Fails before: the live R76 Fertilizers deck's coverage page said "Property developers: pre-sales (bookings), collections and land bank
    aren't elements of ..." and its notes "Operating profiles: Property developers: fewer than half of its companies are property developers",
    of a layer of three realty companies none of which has figures."""
    assert "Property developers" not in deck.not_in_sources(_fert(False))
    assert "Property developers: pre-sales" in deck.not_in_sources(_fert(True))
    rows = [{"layer": "Property developers", "model": {"family": "development"}, "ops": None, "evidenced": 0}]
    assert deck.profile_short(rows) == []


# ---------- 7. a page of one dated update ----------
def test_a_single_dated_update_goes_under_the_page_before_it_and_its_references_find_it(monkeypatch):
    """Fails before: the live R76 Biotech deck gave its one dated update a page of its own under a short "Coverage, continued" page."""
    real = deck.coverage_table
    monkeypatch.setattr(deck, "coverage_table", lambda v_, cov, today=None: real(v_, cov, today)[:2])       # a short coverage page
    v = updates_view()
    v["sections"]["ownership"]["red_flags"] = v["sections"]["ownership"]["red_flags"][:1]
    v["sections"]["ownership"]["holdings"] = []
    v["sections"]["events"]["results_due"] = []
    slides = deck.theme_plan(v, now=datetime(2026, 11, 7, tzinfo=timezone.utc))[0]
    assert not any(s.title == deck.UPDATES_TITLE for s in slides)
    host = next(s for s in slides if deck.UPDATES_TITLE in (getattr(s, "also", None) or []))
    t = next(b for b in host.blocks if b["kind"] == "table" and (b.get("head") or [None])[0] == "Company" and "Update" in b["head"])
    assert [r[0] for r in t["rows"]] == ["Audit Co"]
    assert not any(x == deck.UPDATES_TITLE for s in slides for _, x in (getattr(slides[0], "unresolved", None) or []))
    contents = [t for s in slides if s.kind == "section" for t, _ in s.contents]
    assert deck.UPDATES_TITLE in contents or not any(s.kind == "section" for s in slides)
    # many updates keep a page of their own
    many = deck.theme_plan(updates_view(), now=datetime(2026, 11, 7, tzinfo=timezone.utc))[0]
    assert any(s.title == deck.UPDATES_TITLE for s in many)


def test_versions():
    assert deck.THEME_DECK_VERSION == 92  # deck89 (changed on purpose, owner 25 Nov: the theme deck remade as research): deck 92; e85 (LIVE21A, the R84 decks): deck 91 (updated on purpose); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose); e80 (LIVE16A, the R78 decks): RULES 75, PLACE_CARRY[75] = 74, EARLIER_MAX 30, deck 86, dive text 46 (updated on purpose); e79 (the live R77 decks): RULES 74, PLACE_CARRY[74] = 73, EARLIER_MAX 29, deck 85, dive text 45 (updated on purpose)
    from app.intel import theme_data as D
    assert D.DIVE_TEXT == 51  # e85 (LIVE21A, the R84 decks): deck 91, dive text 51 (updated on purpose); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose); e80 (LIVE16A, the R78 decks): RULES 75, PLACE_CARRY[75] = 74, EARLIER_MAX 30, deck 86, dive text 46 (updated on purpose); e79 (the live R77 decks): RULES 74, PLACE_CARRY[74] = 73, EARLIER_MAX 29, deck 85, dive text 45 (updated on purpose)
    from app.intel import sector_metrics as S
    assert S.VERSION == 3
