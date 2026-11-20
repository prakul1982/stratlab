"""Lane e85 (Release 85): theme-engine items from LIVE21A and the R84 decks. Each test fails on Release 84 and passes after, except those
marked as guards."""
import json
import types
from datetime import datetime, timezone

import pytest

from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app import public_themes as P
from app.intel import sec
from app.intel import theme_base as B
from app.intel import theme_data as D
from app.intel import theme_library as L
from app.intel import theme_routes as TR

# Microsoft's stored words on the live R84 Software inputs (an encyclopedia's article, read before e57 put the annual report first) and the
# opening of its 10-K's Item 1, as the SEC reader reads it
MSFT_ARTICLE = ("Microsoft Corporation is an American multinational technology conglomerate headquartered in Redmond, Washington. The company "
                "became influential in the rise of personal computers through software like Windows and has since expanded into areas such as "
                "Internet services, cloud computing, artificial intelligence and video gaming among others. A Big Tech company, Microsoft is the "
                "largest software company by revenue, one of the most valuable public companies, and one of the most valuable brands globally.")
MSFT_10K = ("Microsoft is a technology company committed to making digital technology and artificial intelligence (“AI”) available broadly and "
            "doing so responsibly. Our mission is to empower every person and every organization on the planet to achieve more. We develop and "
            "support a broad portfolio of technology solutions for individuals and businesses, focusing on secure, trusted, and innovative "
            "platforms and applications that meet evolving customer needs across AI, cloud computing, productivity and collaboration, and "
            "personal computing.")
CDNS_ARTICLE = ("Cadence Design Systems, Inc. is an American multinational technology and computational software company headquartered in San "
                "Jose, California. Initially specialized in electronic design automation (EDA) software for the semiconductor industry, the "
                "company currently makes software and hardware for designing products such as integrated circuits, systems on chips (SoCs), "
                "printed circuit boards, as well as develops large-scale molecular modelling applications and toolkits for pharmaceutical drug "
                "developers. The company also licenses intellectual property for the electronics, aerospace, defense and automotive industries.")
MSFT = "Microsoft Corp"


@pytest.fixture
def store(monkeypatch):
    kept: dict = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "")
    monkeypatch.setattr(TR, "filing_reads", TR.Window())
    hub = types.SimpleNamespace(wiki=types.SimpleNamespace(company=lambda name: None))
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None, index_rows=lambda r: []))
    TR.EVIDENCE_CACHE.clear()
    yield kept
    TR.EVIDENCE_CACHE.clear()


def _old_record(about: str) -> dict:
    """A US record as the live R84 store keeps it for Microsoft: current (read days ago), of today's formats, its words an encyclopedia's."""
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "about": about, "industry": "", "op": TR.OWN_PART_V,
            "v": TR.ABOUT_V, "bv": TR.sec_business_v()}


# ---------- 1. LIVE21A-002 (High): flagship US companies' own words read, never left on an encyclopedia's ----------
def test_us_words_with_no_line_a_page_may_quote_are_read_again():
    """Fails on R84: Microsoft's encyclopedia words were current and "said work" (thin_about False), so nothing read its annual report while
    the page refused to quote them: "industry-supported (official industry only)"."""
    assert TR.thin_about(_old_record(MSFT_ARTICLE), "US", MSFT)
    assert TR.thin_about(_old_record(CDNS_ARTICLE), "US", "Cadence Design Systems Inc")
    assert not TR.thin_about(_old_record(MSFT_10K), "US", MSFT)              # guard: its own words stand
    assert not TR.thin_about(_old_record(MSFT_ARTICLE), "IN", MSFT)          # guard: India's profiles are their own words


def test_the_annual_report_replaces_the_encyclopedia_and_the_company_is_verified_on_it(store, monkeypatch):
    """Fails on R84: the stored article was served as it was (no read), so no line of Microsoft's own words could be shown."""
    store["theme:evidence:US:MSFT"] = json.dumps(_old_record(MSFT_ARTICLE))
    reads = []
    monkeypatch.setattr(TR, "_business_read", lambda sym: reads.append(sym) or MSFT_10K)
    got, pending = TR.evidence_reader("US", {"MSFT": MSFT})(["MSFT"])
    assert reads == ["MSFT"] and not pending
    rec = json.loads(store["theme:evidence:US:MSFT"])
    assert rec["about"].startswith("Microsoft is a technology company") and rec["qv"] == TR.QUOTE_V
    assert TR.quotable_work(rec["about"], MSFT) and not TR.thin_about(rec, "US", MSFT)
    # the map's check said yes: description-verified on the line a page shows (before: no line, so "list-supported")
    c = {"ticker": "MSFT", "name": MSFT, "base": False, "verified": True, "what": ""}
    q = B.quotable(rec["about"], "US")
    assert D.evidence_state(c, set(), q) == "description_verified"
    assert D.evidence_state(c, set(), B.quotable(MSFT_ARTICLE, "US") or None) == "list_supported"


def test_a_report_still_owed_keeps_the_words_the_record_has(store, monkeypatch):
    """Fails on R84 (the article served from memory, never read again); guard of r68e (never fewer words): with the minute's reports taken,
    the record and its words stay as they are until a later read."""
    store["theme:evidence:US:MSFT"] = before = json.dumps(_old_record(MSFT_ARTICLE))
    monkeypatch.setattr(TR, "_business_read", lambda sym: MSFT_10K)
    for _ in range(TR.FILING_READS_PER_MINUTE):
        TR.filing_reads.hit("about", TR.FILING_READS_PER_MINUTE)
    got, _ = TR.evidence_reader("US", {"MSFT": MSFT})(["MSFT"])
    assert store["theme:evidence:US:MSFT"] == before and got["MSFT"]["about"] == MSFT_ARTICLE
    assert TR.EVIDENCE_CACHE.get("theme:evidence:US:MSFT") is None          # asked again by the next batch


def test_a_report_with_no_line_of_its_work_keeps_the_old_words_marked_read(store, monkeypatch):
    """Fails on R84 (no read at all); guard of the no-loss rule: a report whose opening says nothing of the work leaves the words as they were,
    marked so the company is not read again each pass."""
    store["theme:evidence:US:MSFT"] = json.dumps(_old_record(MSFT_ARTICLE))
    monkeypatch.setattr(TR, "_business_read", lambda sym: "")
    TR.evidence_reader("US", {"MSFT": MSFT})(["MSFT"])
    rec = json.loads(store["theme:evidence:US:MSFT"])
    assert rec["about"] == MSFT_ARTICLE and rec["qv"] == TR.QUOTE_V and not TR.thin_about(rec, "US", MSFT)


def test_the_largest_companies_and_the_recheck_read_words_that_cannot_be_quoted(store, monkeypatch):
    """Fails on R84: describe_top passed over every company with stored words, and the re-check read none before the dive."""
    store["theme:evidence:US:MSFT"] = json.dumps(_old_record(MSFT_ARTICLE))
    store["theme:evidence:US:CDNS"] = json.dumps(_old_record(CDNS_ARTICLE))
    store["theme:evidence:US:ADBE"] = json.dumps(_old_record("We are a software company that provides creative, document and marketing "
                                                             "products to individuals and enterprises through subscriptions."))
    monkeypatch.setattr(TR, "_business_read", lambda sym: MSFT_10K if sym == "MSFT" else "")
    m = {"value_chain": [{"layer": "Software", "companies": [{"ticker": "CDNS", "name": "Cadence Design Systems Inc", "cap": 80},
                                                              {"ticker": "MSFT", "name": MSFT, "cap": 3700},
                                                              {"ticker": "ADBE", "name": "Adobe Inc", "cap": 150}]}]}
    assert TR.describe_quoted("US", m) == ["MSFT", "CDNS"]                    # largest first; Adobe's own words stand
    assert TR.describe_quoted("US", m) == []                                  # each read once
    assert TR.describe_quoted("IN", m) == []
    store["theme:evidence:US:MSFT"] = json.dumps(_old_record(MSFT_ARTICLE))
    rows = [{"symbol": "MSFT", "name": MSFT, "market_cap": 3700, "industry": "Software"}]
    assert TR.describe_top("US", {"value_chain": []}, rows, ["Software"]) == ["MSFT"]
    assert TR._has_description("US", "CDNS")                                   # marked read: its report gave no line
    assert TR._has_description("US", "MSFT")


def test_a_reit_held_as_an_llc_is_read_past_how_it_is_held():
    """Fails on R84: Welltower's 10-K opening, "the initial member and majority owner of Welltower OP ... fully and unconditionally
    guaranteed ...", was its stored words; Franklin BSP's "managing member of the OP" was read as what it does."""
    well = ("Welltower Inc. is the initial member and majority owner of Welltower OP, with an approximate ownership interest of 98.378% as of "
            "December 31, 2025. Welltower Inc. issues equity from time to time, the net proceeds of which it is obligated to contribute as "
            "additional capital to Welltower OP. All debt including credit facilities, senior notes and secured debt is incurred by Welltower OP "
            "or its subsidiaries and Welltower Inc. has fully and unconditionally guaranteed all existing and future senior unsecured notes.")
    assert sec.structure_only(well)
    fbrt = ("Substantially all of the Company’s business is conducted through FBRT OP LLC, a Delaware limited liability company (the “OP”) and "
            "to its subsidiaries. The Company is the managing member of the OP and directly or indirectly held 91% of the common units of "
            "membership interests in the OP as of December 31, 2025. As discussed in more detail below, the Company’s operations are organized "
            "into two business units: (i) Commercial Real Estate Financing, and (ii) Agency Business.")
    assert sec.structure_opens(fbrt) and not sec.structure_only(fbrt)
    rec = {**_old_record(fbrt), "bv": 4}
    assert TR.reader_due(rec, "US")
    body = ("Item 1. Business\n" + well + "\nWelltower Inc. is a real estate investment trust that owns rental housing for aging seniors "
            "across the United States, United Kingdom and Canada, and outpatient medical properties.\n"
            + "Our portfolio predominantly consists of seniors and wellness housing communities that we own and operate with partners.\n" * 20
            + "Item 1A. Risk Factors\n")
    op = sec.business_opening(body)
    assert op.startswith("Welltower Inc. is a real estate investment trust that owns rental housing") and "Welltower OP" not in op
    assert sec.BUSINESS_KEY[1] == 5          # (updated on purpose: every opening read again by the reader that passes these over)


def test_a_cautionary_note_and_where_a_company_is_registered_are_not_its_opening():
    """Fails on R84: Shopify's opening read again was "In addition, we operate in a highly competitive and rapidly changing environment.
    These statements are inherently uncertain ..."; Clarivate's "incorporated on January 7, 2019 under the laws of Jersey ...". """
    for x in ("In addition, we operate in a highly competitive and rapidly changing environment.",
              "These statements are inherently uncertain and investors are cautioned not to unduly rely upon these statements.",
              "Clarivate Plc is a public limited company incorporated on January 7, 2019 under the laws of Jersey, Channel Islands.",
              "Our principal business offices are located at 70 St. Mary Axe, London EC3A 8BE, United Kingdom."):
        assert sec._REPORT_TALK.search(x), x
    assert not sec._REPORT_TALK.search("Shopify provides essential internet infrastructure for commerce.")


def test_words_read_again_move_no_company_on_a_fixed_rule():
    """Fails on R84: Regeneron's 10-K ("a fully integrated biotechnology company that ... commercializes medicines ... Our products and
    product candidates") read as development-stage; CoreWeave's ("large-scale model training, inference") as selling no computing."""
    regn = ("Regeneron Pharmaceuticals, Inc. is a fully integrated biotechnology company that invents, develops, manufactures, and "
            "commercializes medicines for people with serious diseases. Our products and product candidates in development are designed to "
            "help patients with eye diseases, allergic and inflammatory diseases, cancer.")
    assert B.company_stage(regn)[0] != "development"
    assert B.says_compute("CoreWeave is The Essential Cloud for AI. Our CoreWeave Cloud platform enables the full lifecycle of AI, including "
                          "large-scale model training, inference, data movement, continuous iteration, and agentic workflows.")
    assert not B.says_compute("Shopify's all-in-one platform makes it easier to start, run and grow a business")          # guard


# ---------- 2. LIVE21A-001 (High): the public gate counts evidence of the theme's work, never an industry label alone ----------
def test_quantum_computing_stays_off_the_public_pages():
    """Fails on R84: "66 description-verified, 318 industry-supported, 0 not checked" passed (industry-supported counted as checked)."""
    pub = {"all": 386, "listed": 386, "unlisted": [], "unchecked": 0, "evidenced": 66, "tallied": 386}
    assert L.gate_why({}, pub).startswith("only 66 of its 386 companies")
    reits = {"all": 195, "listed": 194, "unlisted": [], "unchecked": 0, "evidenced": 175, "tallied": 195}
    assert L.gate_why({}, reits) == ""
    rest = {"all": 65, "listed": 65, "unlisted": [], "unchecked": 0, "evidenced": 29, "tallied": 65}          # Restaurants on R84: 45%
    assert L.gate_why({}, rest) == ""
    assert L.GATE_EVIDENCED == 0.40


def test_the_gate_reads_the_dives_tally_where_a_kept_count_has_no_evidence_share(monkeypatch):
    """Fails on R84: a count kept before this release (no "evidenced") was judged on "not checked" only."""
    tally = {"description_verified": 66, "industry_code_supported": 318, "list_supported": 0, "not_confirmed": 2, "membership_unverified": 0,
             "total": 386}
    assert P.evidenced({"tally": tally}) == {"evidenced": 66, "tallied": 386}
    monkeypatch.setattr(P, "payload", lambda row: {"value_chain": [], "placements": {"industries_by": "words"}})
    monkeypatch.setattr(P, "_dive", lambda region, name, p: {"tally": tally})
    P._GATE_MEMO.clear()
    why = P._gate({"hk": "q", "at": 1, "region": "US", "name": "quantum computing"}, {"broad": False},
                  {"all": 386, "listed": 386, "unlisted": [], "unchecked": 0})
    assert why.startswith("only 66 of its 386")


# ---------- 3. LIVE21A-004 (Medium): one close said once, the app's and the page's count the same ----------
def test_the_head_line_says_one_close_and_one_count_of_earlier_ones():
    """Fails on R84: "market values at the 20 Nov 2026 close (9 at the 19 Nov 2026 close) (2 at the 18 Nov 2026 close) ..."."""
    once = {s: "x" for s in ("A", "B", "C", "D")}
    caps = {s: 10.0 for s in once}
    lab = P._price_label(once, caps, {}, {}, {}, {"A": "2026-11-20", "B": "2026-11-19", "C": "2026-11-18", "D": "2026-11-20"}, None, "IN", [])
    assert lab == {"prices": "2026-11-20", "prices_older": 2}


def test_the_app_counts_every_company_at_an_earlier_close_as_the_page_does():
    """Fails on R84: the dive counted only its companies with figures (IT services "2 companies at an earlier close", its page 31)."""
    rows = {"A": {"cap": 5, "price_at": "2026-11-20"}, "B": {"cap": 4, "price_at": "2026-11-19"}}
    idx = [{"symbol": "C", "market_cap": 3, "price_at": "2026-11-17"}, {"symbol": "D", "market_cap": 2, "price_at": "2026-11-20"},
           {"symbol": "E", "market_cap": None, "price_at": "2026-11-01"}]
    assert D.older_count("2026-11-20", rows, ["A", "B", "C", "D", "E"], idx) == 2
