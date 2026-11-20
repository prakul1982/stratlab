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
    # the opening starts at the company's own name doing its work, or a sentence opening "We operate ..." (PayPal's opening began at its
    # fourth sentence, "When shopping, we offer consumers ...")
    assert sec._SAYS_WORK.search("Shopify provides essential internet infrastructure for commerce.")
    assert sec._SAYS_WORK.search("We operate a global, two-sided network at scale that connects consumers and merchants.")
    assert not sec._SAYS_WORK.search("This segment provides services to the group.")


def test_words_read_again_move_no_company_on_a_fixed_rule():
    """Fails on R84: Regeneron's 10-K ("a fully integrated biotechnology company that ... commercializes medicines ... Our products and
    product candidates") read as development-stage; CoreWeave's ("large-scale model training, inference") as selling no computing."""
    regn = ("Regeneron Pharmaceuticals, Inc. is a fully integrated biotechnology company that invents, develops, manufactures, and "
            "commercializes medicines for people with serious diseases. Our products and product candidates in development are designed to "
            "help patients with eye diseases, allergic and inflammatory diseases, cancer.")
    assert B.company_stage(regn)[0] != "development"
    assert B.says_compute("CoreWeave is The Essential Cloud for AI. Our CoreWeave Cloud platform enables the full lifecycle of AI, including "
                          "large-scale model training, inference, data movement, continuous iteration, and agentic workflows.")
    assert B.says_compute('We offer Slurm on Kubernetes ("SUNK") to support large-scale AI research and training workloads.')
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


# ---------- 4. LIVE21A-009/020: moves that hold, reasons of the work, one state, foreign banks apart ----------
def test_a_move_of_the_last_days_under_the_same_rules_is_not_moved_back():
    """Fails on R84: the REITs log moved Omega Healthcare to Mortgage REITs on 19 Nov and back on 20 Nov (Alexandria, Medalist the same)."""
    from datetime import date
    from app.intel import theme_changes as C
    log = {"log": [{"d": "2026-11-19", "rules": B.RULES, "moved": [{"symbol": "ARE", "from": "Other real estate investment trust companies",
                                                                    "to": "Healthcare property owners"}]},
                   {"d": "2026-11-10", "rules": B.RULES, "moved": [{"symbol": "MDRR", "from": "Other", "to": "Towers"}]},
                   {"d": "2026-11-19", "moved": [{"symbol": "OHI", "from": "Healthcare property owners", "to": "Mortgage REITs"}]}]}
    got = C.recent_moves(log, B.RULES, date(2026, 11, 20))
    assert got == {"ARE": ["Other real estate investment trust companies", "Healthcare property owners"]}     # an old move, or one kept
    assert C.recent_moves(log, B.RULES + 1, date(2026, 11, 20)) == {}          # before e85 with no version, holds nothing; new rules: none
    vc = [{"layer": "Healthcare property owners", "companies": [{"ticker": "WELL"}]},
          {"layer": "Other real estate investment trust companies", "official": True, "basis": "rest", "companies": [{"ticker": "ARE"}]}]
    vc, rows = B.hold_reversals(vc, got)
    assert [c["ticker"] for c in vc[0]["companies"]] == ["WELL", "ARE"] and not vc[1]["companies"] and rows[0]["to"] == "Healthcare property owners"
    assert C._entry({"counts": {}, **{k: [] for k in C.KINDS}}, "rules", datetime(2026, 11, 20, tzinfo=timezone.utc), 79)["rules"] == 79


def test_a_reason_quoting_how_a_company_is_held_or_cut_after_its_subsidiaries_is_said_again():
    """Fails on R84: Franklin BSP "→ Mortgage REITs: its own words say “The Company is the managing member of the OP ...”"; Redwood's
    "“Redwood Trust, Inc., together with its subsidiaries, is …”"."""
    from app.intel import theme_changes as C
    assert C.unquotable_reason("its own words say “The Company is the managing member of the OP and directly or indirectly held 91% of the "
                               "common units of membership interests in the OP as of December 31, 2025”", "Franklin BSP Realty Trust")
    assert C.unquotable_reason("its own words say “Redwood Trust, Inc., together with its subsidiaries, is…”", "Redwood Trust")
    assert not C.unquotable_reason("its own words say “We originate and acquire commercial real estate loans across the United States”", "X")
    words = ("Redwood Trust, Inc., together with its subsidiaries, is a specialty finance company focused on several distinct areas of "
             "housing credit, with a mission to make quality housing accessible.")
    e = [{"moved": [{"symbol": "RWT", "name": "Redwood Trust", "from": "Other real estate investment trust companies", "to": "Mortgage REITs"}]}]
    why = C.reasoned(e, words_of=lambda s: words)[0]["moved"][0]["why"]
    assert "together with its subsidiaries" not in why and "specialty finance company" in why


def test_a_row_placed_on_words_a_page_does_not_quote_is_not_marked_on_its_words():
    """Fails on R84: Welltower "(on its words)" in the REITs deck beside "industry-supported" on its page."""
    from app import deck as K
    assert K.on_words({"by_words": True, "evidence": "description_verified"})
    assert not K.on_words({"by_words": True, "evidence": "industry_code_supported"})


def test_a_foreign_issuer_in_a_us_banks_layer_goes_to_the_foreign_banks_layer():
    """Fails on R84: UBS in "Custody and asset servicing banks", Banco Santander (Brasil) in "Mid-sized banks", HSBC and RBC apart."""
    vc = [{"layer": "Foreign banking groups earning loan interest", "companies": [{"ticker": "HSBC", "cap": 200}, {"ticker": "RY", "cap": 180}]},
          {"layer": "Custody and asset servicing banks", "companies": [{"ticker": "BK", "cap": 80}, {"ticker": "UBS", "cap": 100}]},
          {"layer": "Other regional bank companies", "official": True, "basis": "rest", "companies": []}]
    filings = {"HSBC": "Annual report (20-F)", "RY": "Annual report (40-F)", "BK": "Annual report (10-K)", "UBS": "Annual report (20-F). (6-K)"}
    vc, rows = B.domicile_moves(vc, lambda s: {"filings": filings.get(s, "")})
    assert [c["ticker"] for c in vc[0]["companies"]] == ["HSBC", "RY", "UBS"] and [c["ticker"] for c in vc[1]["companies"]] == ["BK"]
    assert rows == [{"ticker": "UBS", "name": None, "from": "Custody and asset servicing banks", "to": "Foreign banking groups earning loan interest",
                     "why": rows[0]["why"]}] and "foreign issuer's (20-F, 6-K)" in rows[0]["why"]


# ---------- 5. The R84 decks: insurers' ratios are no margins; a layer added and removed the same day is no change ----------
def test_a_combined_ratio_under_a_wrapped_head_and_an_roe_are_not_read_as_margins():
    """Fails on R84: the Insurance deck's "financial margin" (3): Employers Holdings' combined ratio 114.3%, its range, Verisk's ROE 293.9%."""
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import deck_check
    cover = "\n\nTHEME DEEP DIVE\nInsurance\n"
    page = ("                         Revenue\n"
            "                                        EBITDA                                                                       Combined      SBC /        FCF\n"
            " Company                     (US                            Net margin            Loss ratio    Expense ratio                                                Year\n"
            "                                        margin                                                                           ratio     revenue      margin\n"
            " Employers Holdings, Inc.  $859 m        –                        1.3%                 76.4%            37.9%            114.3%     –            –            Dec 2025\n"
            "                                                                                                                      69.0% to\n"
            " Range                                                 −11.8% to 29.6%    50.4% to 76.4%       9.5% to 37.9%\n"
            "                                                                                                                       114.3%\n")
    app = (" Company                                    Layer                                       Revenue    Growth     EBITDA         Net     ROCE         ROE         P/E        P/B\n"
           " Verisk Analytics, Inc.                     Risk data and software           $25.7 bn   $3.07 bn    +6.6%      52.2%      29.6%     26.4%      293.9%       30.4x      86.2x\n")
    got = deck_check.check_text("\f".join([cover, page, app]))
    assert not got["counts"]["financial margin"], got["findings"]
    bank = (" Company           Revenue      EBITDA margin      Net margin\n"
            " Fifth Third Bancorp   $80 m        –              3152.5%\n")
    assert deck_check.check_text("\f".join(["\n\nTHEME DEEP DIVE\nRegional banks\n", bank]))["counts"]["financial margin"] == 1   # guard


def test_a_layer_added_and_removed_the_same_day_is_no_change_of_the_day():
    """Fails on R84: the Capital markets deck's "“Other capital market companies” added (2 companies); ... removed (2 companies ...)"."""
    from app.intel import theme_changes as C
    other = "Other capital market companies"
    es = [{"d": "2026-11-20", "cause": "rules", "counts": {"layers": 1}, "layers": [{"kind": "added", "from": [], "to": [other], "n": 2}]},
          {"d": "2026-11-20", "cause": "rules", "counts": {"layers": 2}, "layers": [{"kind": "removed", "from": [other], "to": [], "n": 2},
                                                                                  {"kind": "renamed", "from": ["A"], "to": ["B"], "n": 3}]}]
    got = C.one_a_day(es)
    assert len(got) == 1 and got[0]["layers"] == [{"kind": "renamed", "from": ["A"], "to": ["B"], "n": 3}] and got[0]["counts"]["layers"] == 1


# ---------- 6. LIVE21A-015/018: the brief's 52-week gap from its own close; the sample deck at the newer close ----------
def test_the_briefs_52_week_gap_is_from_the_days_close(monkeypatch):
    """Fails on R84: the 18 Nov US post "S&P 500 7,323.63 ... 6.9% below" (the 19 Nov 10:52 ET level's gap, kept when the level was set to
    the close); from the close and the 7,844.52 high, 6.6%."""
    from datetime import date, timedelta
    from app.newsletter import content
    day = date(2026, 11, 18)
    candles = [{"t": (day - timedelta(days=400 - i)).isoformat() + "T00:00:00", "c": 7000.0, "h": 7050.0} for i in range(399)]
    candles[200]["h"] = 7844.52
    candles += [{"t": "2026-11-17T00:00:00", "c": 7340.53, "h": 7400.0}, {"t": "2026-11-18T00:00:00", "c": 7323.63, "h": 7360.0}]
    candles = [c for c in candles if c["t"][:10] <= "2026-11-18"]
    monkeypatch.setattr(main.research_hub, "yahoo", types.SimpleNamespace(closing_chart=lambda sym, back: {"candles": candles}))
    got = content.index_close("^GSPC", day, prev="2026-11-17")
    assert got["price"] == 7323.63 and got["from_high_pct"] == -6.6 and got["high52"] == 7844.52


def test_a_stored_brief_with_the_gap_of_another_level_is_set_to_its_closes_gap_keeping_its_words(monkeypatch):
    """Fails on R84: repair_closes set the level and kept the old gap; a gap-only repair keeps the issue's words (its AI summary)."""
    from datetime import date
    from app import blog, db
    from app.newsletter import content, job
    monkeypatch.setattr(content, "INDICES", {"US": [("S&P 500", "^GSPC")]})
    monkeypatch.setattr(content, "index_close", lambda sym, day, since=None, prev=None:
                        {"price": 7323.63, "change_pct": -0.23, "high52": 7844.52, "from_high_pct": -6.6})
    monkeypatch.setattr(content, "reference_day", lambda r, d, w: date(2026, 11, 17))
    today = date.today().isoformat()
    iid = f"market.US.{today}"
    issue = {"id": iid, "kind": "market", "region": "US", "day": today, "weekly": False, "subject": "S", "summary": "s", "ai": True,
             "ai_summary": "The S&P 500 fell 0.23%.", "indices": [{"name": "S&P 500", "price": 7323.63, "change_pct": -0.23, "from_high_pct": -6.9}],
             "sections": []}
    store = {"news-index:market:US": json.dumps([iid]), f"news:market:US:{today}": json.dumps(issue)}
    monkeypatch.setattr(db, "get_setting", store.get)
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(blog, "rewrite_brief", lambda i: True)
    assert job.repair_closes("US") == [iid]
    kept = json.loads(store[f"news:market:US:{today}"])
    assert kept["indices"][0]["from_high_pct"] == -6.6 and kept["ai_summary"] == "The S&P 500 fell 0.23%." and kept["subject"] == "S"
    assert job.repair_closes("US") == []


def test_the_sample_deck_is_made_again_at_its_themes_newer_close(monkeypatch):
    """Fails on R84: nothing made the sample again; "Prices as of 19 Nov 2026" 5 h after the 20 Nov closes landed."""
    from app import sample_deck
    row = {"id": "d1", "region": "IN", "label": "Consumer durables (PDF, 2026-11-20)", "meta": {"prices": "2026-11-19"}}
    monkeypatch.setattr(sample_deck, "chosen", lambda deck_id=None: row)
    m = {"placements": {"checked": True}, "generated_at": 1}
    monkeypatch.setattr(TR, "map_for_deck", lambda R, p, region, q, wait=0, pending=None: ("IN", "Consumer durables", m))
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(IST=timezone.utc))
    dive = {"as_of": "2026-11-20"}
    monkeypatch.setattr(TR, "dive_of", lambda r, t, m_: dive)
    made = []
    monkeypatch.setattr(TR, "deck_file", lambda R, r, t, m_, p, f, b: made.append((r, t, f, b)) or b"%PDF")
    TR._SAMPLE_TRIED.clear()
    assert TR.refresh_sample({"id": ""}) == "2026-11-20" and made == [("IN", "Consumer durables", "pdf", False)]
    assert TR.refresh_sample({"id": ""}) is None                     # once a close
    TR._SAMPLE_TRIED.clear()
    dive["updating"] = True
    assert TR.refresh_sample({"id": ""}) is None                     # its dive still being worked out
    row["meta"]["prices"] = "2026-11-20"
    dive.pop("updating")
    assert TR.refresh_sample({"id": ""}) is None and len(made) == 1  # already at the newest close


# ---------- the owner's review of the R84 decks (P0/P1) ----------
def test_a_hotel_reit_s_words_say_property_is_its_business():
    """Fails on R84: Host Hotels, Ryman, Sunstone and Xenia out of "Hotel property owners (lodging REITs)" as words that "don't say property
    is its business"."""
    for w in ("We are the largest publicly traded lodging REIT, with a geographically diverse portfolio of luxury and upper-upscale hotels.",
              "We specialize in group-oriented, destination hotel assets in urban and resort markets. As a REIT, we generally will not be "
              "subject to federal corporate income taxes.",
              "Xenia Hotels & Resorts, Inc. is a Maryland corporation that primarily invests in uniquely positioned luxury and upper upscale "
              "hotels and resorts."):
        assert B.PROPERTY_SAYS.search(B.principal_words(w)), w
    assert not B.PROPERTY_SAYS.search("We operate casinos and hotels owned by third parties under management contracts")   # guard


def test_the_decks_rule_says_list_supported_members_count_as_they_do():
    """Fails on R84: "Only description-verified and industry-supported companies count" beside 6 list-supported core members with figures."""
    from app import deck as K
    assert "list-supported" in K.EVIDENCE_RULE_SAID


def test_ffo_columns_only_in_a_reit_themes_value_chain():
    """Fails on R84: the US Insurance deck's value chain carried P/FFO."""
    from app import deck as K
    rows = [{"layer": "A", "p_ffo": 14.0, "combined_ratio": 95.0}]
    assert [c[0] for c in K.chain_family_cols(rows, "Insurance")] == ["combined_ratio"]
    assert "p_ffo" in [c[0] for c in K.chain_family_cols(rows, "Real estate investment trusts")]


def test_every_fall_from_description_verified_is_kept_with_its_reason():
    """Fails on R84: Software's 467 -> 395 fell with no reason in the deck or the change log."""
    from app.intel import theme_changes as C
    before = {"ev": {"MSFT": "d", "ADBE": "d", "ORCL": "i"}}
    dive = {"evidence": {"MSFT": "industry_code_supported", "ADBE": "description_verified", "ORCL": "description_verified"}}
    down = TR.evidence_down(before, dive, lambda s: MSFT_ARTICLE, "US", {"MSFT": MSFT})
    assert [x["symbol"] for x in down] == ["MSFT"] and "may quote" in down[0]["why"]
    snap = C.snapshot({"layers": [{"layer": "L", "companies": [{"symbol": "MSFT", "name": MSFT}]}], "evidence_down": down,
                       "evidence": dive["evidence"]}, ["MSFT"], 1, B.RULES)
    assert snap["ev_down"][0][0] == "MSFT" and snap["ev"]["ADBE"] == "d"
    got = C.apply({"snap": {**snap, "ev_down": None}}, snap)
    assert got["log"][-1]["down"][0]["symbol"] == "MSFT" and "ev_down" not in got["snap"]


def test_no_company_outside_the_stated_evidence_states_is_in_a_calculation_cohort_on_any_theme_fixture():
    """The owner's R84 reassessment (Payments, Medical devices, Hotels & Casinos, Aerospace, Telecom, Building materials: the rule printed
    beside the figures and the companies in them disagreed). Guard over every live theme fixture: a company the membership check keeps in
    the theme (in a layer's calculations when it has figures) is description-verified, industry-supported or list-supported, the three
    states the deck's rule names (deck.EVIDENCE_RULE_SAID); not checked and other work are in none."""
    import glob
    import pathlib
    from app import deck as K
    for s_ in ("Description-verified", "industry-supported", "list-supported"):
        assert s_ in K.EVIDENCE_RULE_SAID
    ok = {"description_verified", "industry_code_supported", "list_supported"}
    seen = 0
    for p in sorted(glob.glob(str(pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "*" / "*.json"))):
        try:
            d = json.load(open(p))
        except ValueError:
            continue
        d = d.get("data", d) if isinstance(d, dict) else d
        if not isinstance(d, dict) or "evidence" not in d or "value_chain" not in d:
            continue
        theme, region = d.get("theme") or d.get("sector") or "", d.get("region") or "US"
        words, named, wt = D.theme_words(d, theme), D.name_words(d, theme), D.work_test(d, theme)
        for v in d["value_chain"]:
            for c in v["companies"]:
                raw = d["evidence"].get(c["ticker"])
                st = D.membership(c, words, raw, None, named=named)
                qc, q = D.quoted_words(c, raw, region, bool(v.get("official")))
                ev = D.work_checked(D.evidence_state(qc, words, q, None, st), qc, q, wt)
                assert st == "unverified" or ev in ok, (p, c["ticker"], st, ev)
        seen += 1
    assert seen >= 50


def test_a_property_developers_layer_in_a_theme_of_another_business_is_folded_with_why():
    """Fails on R84: Fertilizers & Agrochemicals showed a "Property developers" layer (pp.10-11); Bharat Agri Fert & Realty's reason said its
    words don't say property while quoting its construction words."""
    vc = [{"layer": "Urea and nitrogen fertiliser makers", "companies": [{"ticker": "U1"}]},
          {"layer": "Property developers", "companies": [{"ticker": "BHARATAGRI"}]},
          {"layer": "Other fertilizers and agrochemicals companies", "official": True, "basis": "rest", "companies": []}]
    out = B.fold_scope_layers(vc, "Fertilizers and agrochemicals", "Fertilizers and agrochemicals")
    assert [v["layer"] for v in out if v["companies"]] == ["Urea and nitrogen fertiliser makers", "Other fertilizers and agrochemicals companies"]
    assert out[1]["folded"] and out[2]["companies"][0]["refit"]["why"].startswith("“Property developers” is a property business beside the theme's own work")
    hotels = [{"layer": "Hotel property owners (lodging REITs)", "companies": [{"ticker": "HST"}]}]
    assert B.fold_scope_layers(hotels, "Hotels and casinos", "Hotels and casinos") == hotels          # guard: the theme's own kind
    assert B.PROPERTY_SAYS.search("The company is engaged in the construction of residential and commercial buildings")


def test_a_small_share_of_companies_with_figures_says_its_selection_and_bias():
    """Fails on R84: Biotech's figures of 85 of 807 core companies with no word of how they were chosen."""
    from app import deck as K
    line = K.selection_said({"n": 85, "total": 807, "share": 71, "of_what": "the theme's market value"})
    assert line.startswith("The figures are of 85 of the theme's 807 companies") and "lean towards larger" in line
    assert K.selection_said({"n": 60, "total": 100}) == ""


def test_deck_check_fails_a_stated_cohort_rule_its_population_breaks_and_layer_words_only_warns():
    """Fails on R84: no check caught "Only description-verified and industry-supported" beside "with figures (every median and total is of
    these) 16 (10 description-verified, 0 industry-supported, 6 list-supported)" (Payments; Medical devices, Hotels & Casinos, Aerospace,
    Telecom, Building materials the same); and "layer words" failed Cybersecurity's correct "Endpoint and detection platforms"."""
    import pathlib
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
    import deck_check
    page = ("Universe Only description-verified and industry-supported companies count in a median or total. "
            "in the theme, with figures (every median and total is of these) 16 (10 description-verified, 0 industry-supported, 6 list-supported)")
    got = deck_check.check_text(page)
    assert got["counts"]["cohort rule"] == 1 and deck_check.failed(got)
    fixed = page.replace("Only description-verified and industry-supported companies count", "Description-verified, industry-supported and "
                         "list-supported companies count")
    assert not deck_check.check_text(fixed)["counts"]["cohort rule"]
    assert "layer words" in deck_check.WARN and "layer words" not in deck_check.FAIL
    # the Cybersecurity and Semiconductors inputs of R84 (their list-supported core members) are among the loop test's fixtures
    here = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r84"
    assert (here / "cyber.json").exists() and (here / "semis.json").exists()
