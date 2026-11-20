"""Lane e81 (Release 80): theme-engine items from LIVE17A, LIVE17B-007 and the R79 decks. Each test fails before its fix and passes after,
except those marked as guards."""
import json
import pathlib
import sys

from app import computed, deck, public_themes
from app.intel import theme_base, theme_changes, theme_data, theme_library, theme_recheck, theme_routes
from tests.test_r66e_fixes import keep, payload, w  # noqa: F401 (the stored-library fixture)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import deck_check  # noqa: E402

# the live stored words of LIVE17A-002 (encyclopedia extracts run into a US record read before e57/e80, no "wiki" field kept)
QCOM = ("Qualcomm Incorporated is an American multinational corporation headquartered in San Diego, California, and incorporated in Delaware. "
        "It creates semiconductors, software, and services related to wireless technology. The company develops and designs technologies for "
        "global communications and computing, including next-generation mobi We are a global leader in the development and commercialization "
        "of foundational technologies for the wireless industry.")
ALAB = ("Astera Labs, Inc., headquartered in San Jose, California, is a fabless manufacturing company that designs connectivity chips. The company "
        "specializes in PCIe retimers for data centers. We design semiconductor-based connectivity solutions purpose-built for AI infrastructure.")
MSFT = ("Microsoft Corporation is an American multinational technology conglomerate headquartered in Redmond, Washington. The company became "
        "influential in the rise of personal computers through software like Windows and has since expanded into areas such as Internet "
        "services, cloud computing, artificial intelligence and video gaming among others.")
CDNS = ("Cadence Design Systems, Inc. is an American multinational technology and computational software company headquartered in San Jose, "
        "California. Initially specialized in electronic design automation (EDA) software for the semiconductor industry, the company currently "
        "makes software and hardware for designing products such as integrated circuits, systems on chips (SoCs), printed circuit boards.")


# ---------- 1. LIVE17A-002: the dive quotes the words the members table reads, never an encyclopedia's, never cut mid-word ----------
def test_e81_the_dive_quotes_no_encyclopedia_sentence_of_a_us_record_read_before_the_extract_was_kept_apart():
    q = theme_base.quotable(QCOM, "US")
    assert "next-generation mobi" not in q and "American multinational" not in q and "The company develops" not in q
    assert q.startswith("We are a global leader")
    assert theme_base.quotable(ALAB, "US") == "We design semiconductor-based connectivity solutions purpose-built for AI infrastructure."
    assert theme_base.quotable(MSFT, "US") == ""
    assert theme_base.quotable(CDNS, "US") == ""
    # every line a layer's row prints comes from those words: none of the live quotes is found there
    for about, layer in ((QCOM, "Wireless and mobile chips"), (MSFT, "Software platforms"), (CDNS, "Design software"), (ALAB, "Connectivity chips")):
        line = theme_base.layer_line("", theme_base.quotable(about, "US"), "", layer)
        assert "Initially specialized" not in line and "became influential" not in line and "headquartered" not in line and "mobi" not in line


def test_e81_a_map_line_of_an_encyclopedia_sentence_is_not_carried_into_the_dive():
    c = {"ticker": "QCOM", "name": "Qualcomm Inc", "what": "The company develops and designs technologies for global communications and computing"}
    v = {"official": True}
    got = theme_data.carried_line(c, v, lambda s_: theme_base.quotable(QCOM, "US"), lambda s_: QCOM)
    assert got == ""
    # guard: a map line of its own filing's words is carried
    c2 = {**c, "what": "We are a global leader in the development and commercialization of foundational technologies"}
    assert theme_data.carried_line(c2, v, lambda s_: theme_base.quotable(QCOM, "US"), lambda s_: QCOM) == c2["what"]


def test_e81_quotable_guards_an_own_description_and_a_short_line_without_a_full_stop():
    """Guard: an Indian profile's "It ..." lines, a 10-K's own words and a short description ending without a full stop stay as they are."""
    ind = "Tata Steel Ltd manufactures steel. It sells flat products to automakers"
    assert theme_base.quotable(ind, "IN") == ind
    own = "We design chips for cars. Our customers are carmakers."
    assert theme_base.quotable(own, "US") == own
    # a fragment a long record was cut on is never quoted
    cut = "We design chips for cars. " + "Our customers are carmakers and makers of industrial equipment. " * 9 + "We also sell softw"
    assert not theme_base.quotable(cut, "US").endswith("softw")


# ---------- 2. LIVE17A-004: placements and their reasons ----------
def test_e81_klx_an_oilfield_services_company_is_never_an_integrated_major_even_held_by_its_published_layer():
    vc = [{"layer": "Integrated oil majors", "companies": [
              {"ticker": "XOM", "name": "Exxon Mobil", "industry": "Petroleum Refining", "cap": 480000.0},
              {"ticker": "KLXE", "name": "KLX Energy Services Holdings, Inc.", "industry": "Oil & Gas Field Services, Nec", "cap": 21.33,
               "held_published": {"from": "Other oil and gas companies", "to": "Integrated oil majors", "why": "kept"}}]},
          {"layer": "Oilfield services and small producers (larger)", "companies": [{"ticker": "SLB", "name": "SLB", "cap": 50000.0}]},
          {"layer": "Oilfield services and small producers (smaller)", "companies": [{"ticker": "TINY", "name": "Tiny", "cap": 5.0}]},
          {"layer": "Other oil and gas companies", "official": True, "basis": "rest", "companies": []}]
    out, rows = theme_base.kind_bars(vc, lambda s_: "", "Oil and gas")
    majors = next(v for v in out if v["layer"] == "Integrated oil majors")
    assert [c["ticker"] for c in majors["companies"]] == ["XOM"]
    small = next(v for v in out if v["layer"].endswith("(smaller)"))
    klx = next(c for c in small["companies"] if c["ticker"] == "KLXE")
    assert "Oil & Gas Field Services" in klx["refit"]["why"] and "held_published" not in klx
    assert rows and rows[0]["ticker"] == "KLXE"
    # and the published-layer hold never puts it back there
    vc2 = [{"layer": "Integrated oil majors", "companies": [{"ticker": "XOM", "name": "Exxon Mobil", "industry": "Petroleum Refining"}]},
           {"layer": "Other oil and gas companies", "official": True, "basis": "rest",
            "companies": [{"ticker": "KLXE", "name": "KLX Energy Services Holdings, Inc.", "industry": "Oil & Gas Field Services, Nec", "cap": 21.33}]}]
    held_vc, held = theme_base.hold_published(vc2, {"KLXE": "Integrated oil majors"}, lambda s_: "", "Oil and gas")
    assert held == []


def test_e81_a_lender_and_a_non_traded_reit_are_never_in_towers_and_data_centres():
    words = {"ICRP": "Among other duties, the Sub-Advisor has the authority to identify, negotiate, acquire and originate our investments. We "
                     "originate, acquire and manage a portfolio of commercial real estate credit investments, including first mortgage loans.",
             "BSTT": "We are a perpetual-life, non-listed REIT that owns a diversified portfolio of rental housing and industrial properties.",
             "HGIT": "",
             "AMT": "We own and operate communications towers and data centers that we lease to wireless carriers."}
    names = {"ICRP": "InPoint Commercial Real Estate Income, Inc.", "BSTT": "Blackstone Real Estate Income Trust, Inc.",
             "HGIT": "Hines Global Income Trust, Inc.", "AMT": "American Tower Corp"}
    vc = [{"layer": "Towers, data centres and niche property", "companies": [{"ticker": s_, "name": n} for s_, n in names.items()]},
          {"layer": "Mortgage REITs", "by_place": True, "companies": [{"ticker": "BXMT", "name": "Blackstone Mortgage Trust"}]},
          {"layer": "Other real estate investment trust companies", "official": True, "basis": "rest", "companies": []}]
    out, rows = theme_base.kind_bars(vc, words.get, "Real estate investment trusts")
    towers = next(v for v in out if v["layer"].startswith("Towers"))
    assert [c["ticker"] for c in towers["companies"]] == ["AMT"]          # guard: a tower owner stays
    mreit = next(v for v in out if v["layer"] == "Mortgage REITs")
    assert "ICRP" in {c["ticker"] for c in mreit["companies"]}
    other = next(v for v in out if v.get("basis") == "rest")
    assert {"BSTT", "HGIT"} <= {c["ticker"] for c in other["companies"]}
    assert any("lends" in r["why"] for r in rows) and any("non-traded" in r["why"] for r in rows)


def test_e81_a_fertilizer_theme_holds_a_property_layer_only_for_companies_whose_words_say_property_is_their_business():
    words = {"GENUSPRIME": "Genus Prime Infra Ltd is engaged in trading of commodities and chemicals.",
             "SFPIL": "Square Four Projects India Ltd trades in fertilisers and agro chemicals.",
             "BHARATAGRI": "The company is engaged in manufacturing of fertilisers and in real estate development at Thane."}
    vc = [{"layer": "Property developers", "companies": [{"ticker": s_, "name": s_} for s_ in words]},
          {"layer": "Other fertilizers and agrochemical companies", "official": True, "basis": "rest", "companies": []}]
    out, rows = theme_base.kind_bars(vc, words.get, "Fertilizers and agrochemicals")
    prop = next((v for v in out if v["layer"] == "Property developers"), None)
    assert prop is not None and [c["ticker"] for c in prop["companies"]] == ["BHARATAGRI"]       # its own words say real estate
    assert {r["ticker"] for r in rows} == {"GENUSPRIME", "SFPIL"}
    # guard: a property layer in a real estate theme is not touched
    vc2 = [{"layer": "Property developers", "companies": [{"ticker": "X", "name": "X"}]},
           {"layer": "Other real estate companies", "official": True, "basis": "rest", "companies": []}]
    assert theme_base.kind_bars(vc2, lambda s_: "X Ltd builds offices.", "Real estate")[1] == []


def test_e81_a_move_never_quotes_an_adviser_or_a_dated_deal_and_quotes_a_line_that_says_its_layer():
    assert theme_changes.work_sentence("Among other duties, the Sub-Advisor has the authority to identify, negotiate, acquire and originate our "
                                       "investments. We originate and manage commercial real estate debt, including first mortgage loans.") \
        .startswith("We originate and manage commercial real estate debt")
    assert theme_changes.work_sentence("On July 18, 2025, we closed on the acquisition of a Tesla sales, service and delivery facility. We own "
                                       "retail, flex and hotel properties.").startswith("We own retail, flex and hotel properties")
    rows = [{"symbol": "MEFCOM", "name": "Mefcom Capital Markets Ltd", "from": "Other capital market companies",
             "to": "Proprietary investing and small financial firms"},
            {"symbol": "MOTILALOFS", "name": "Motilal Oswal Financial Services Ltd", "from": "Other capital market companies", "to": "Stock broking"}]
    words = {"MEFCOM": "Mefcom Capital Markets Ltd is engaged in capital market operations and merchant banking.",
             "MOTILALOFS": "The company offers diversified financial services. It provides broking services to retail and institutional clients."}
    got = {r["symbol"]: r["why"] for r in theme_changes.reasoned([{"moved": rows}], words.get, lambda s_: "")[0]["moved"]}
    assert "merchant banking" in got["MEFCOM"]                 # guard: with no line that says its layer, its work line stands
    assert "broking services" in got["MOTILALOFS"] and "diversified financial services" not in got["MOTILALOFS"]


def test_e81_a_company_whose_words_say_one_layers_name_is_placed_there_not_by_a_long_description():
    layers = [{"layer": "Towers, data centres and niche property",
               "description": "These companies own towers, data centres and a few specialty properties such as farmland, cannabis facilities and "
                              "apartments, and lease them to carriers, cloud customers and other tenants under long leases on what they own."},
              {"layer": "Retail and net lease landlords", "description": "They collect rent from retailers through shopping centres."}]
    words = ("We acquire, reposition, renovate, lease and manage income-producing properties, with a primary focus on retail, flex and hotel "
             "properties, and lease them to tenants under leases.")
    assert theme_base._place_words(layers, words, "Real Estate Investment Trusts") == "Retail and net lease landlords"


# ---------- 3. LIVE17A-005: one count of a theme's companies for every surface ----------
def _p():
    cos = [{"ticker": "A", "name": "A", "basis": "industry", "base": True}, {"ticker": "B", "name": "B", "verified": True},
           {"ticker": "C", "name": "C", "base": False, "verified": False}, {"ticker": "D", "name": "D", "base": False, "verified": False},
           {"ticker": "E", "name": "E", "base": False, "verified": False}, {"ticker": "A2", "name": "A", "basis": "industry", "base": True}]
    return {"sector": "Space", "value_chain": [{"layer": "Launch", "companies": cos[:3]}, {"layer": "Satellites", "companies": cos[3:]}]}


def test_e81_the_page_lists_the_companies_the_dive_confirms_and_says_why_the_rest_are_not_listed():
    """Space and satellites: "19 companies ... (5 more of the theme's 24 not listed: not confirmed ...)" while 23 of 24 were confirmed."""
    dive = {"evidence": {"A": "industry_code_supported", "B": "description_verified", "C": "description_verified", "D": "membership_unverified",
                         "E": "not_confirmed"},
            "duplicates": [{"symbol": "A2", "kept": "A"}], "tally": {"total": 5}}
    c = public_themes.counts(_p(), dive)
    assert c == {"listed": 3, "layers": 1, "all": 5, "unlisted": [["not checked yet", 1], ["whose own words describe other work", 1]]}
    assert public_themes.unlisted_said(c) == "2 more of the theme's 5 not listed: 1 not checked yet, 1 whose own words describe other work"


def test_e81_a_themes_card_says_its_pages_count(w, monkeypatch):
    p = {**payload("Ships", 8), "placements": {"checked": True, "placed": 8}}
    p["value_chain"][0]["companies"][1]["verified"] = False           # one not confirmed: listed on neither
    keep("ships", p)
    stored = theme_library.stored("IN", "ship")["payload"]
    dive = {"sector": "Ships", "layers": [], "duplicates": [{"symbol": stored["value_chain"][0]["companies"][2]["ticker"], "kept": "X"}],
            "evidence": {}, "tally": {"total": 7}}
    key = theme_routes.dive_key("IN", "ship", {**stored, "_library": "ship"})
    computed.put(theme_library.DIVE, key, {"dive": dive, "pieces": {}}, label="Ships", region="IN",
                 meta={"q": "ship", "rules": theme_base.RULES, "pub": public_themes.counts(stored, dive)})
    entry = next(x for x in public_themes.entries("IN") if x["name"] == "ship")
    v = public_themes.view(entry, stored)
    assert v["members"] == 6 and v["all"] == 7
    assert public_themes.card_line(entry).startswith("India · 6 companies")


def test_e81_a_theme_post_says_its_pages_counts_of_companies_and_layers():
    from app import blog_research as BR
    src = {"v": 2, "theme": "Semiconductors", "region": "US", "sector": "Semiconductors", "total": 104, "members": 77, "unit": "$ million",
           "rows": [{"layer": f"L{i}", "n": 5, "listed": 6, "ebitda": 20.0, "ebitda_n": 5, "companies": []} for i in range(9)],
           "page_counts": {"listed": 102, "layers": 10, "all": 104}, "read_on": "2026-11-19"}
    post = BR.theme_post_from(src)
    body = json.dumps(post)
    # (updated on purpose, e82 LIVE18A-006: the post says the companies its page lists and the page's line on the rest, word for word)
    assert "102 listed US companies are in the semiconductors theme as its page lists them (2 more of the theme's 104 not listed)" in body
    assert "into 10 layers" in body and "in the 9 layers that have them" in body


# ---------- 4. LIVE17A-008: re-splits and returns are no moves ----------
def test_e81_a_resplit_into_halves_and_a_move_that_returns_are_not_logged_as_moves():
    log = [{"d": "2026-11-15", "cause": "rules", "counts": {"moved": 2}, "moved": [
               {"symbol": "OSIS", "name": "OSI", "from": "Fabless chip design", "to": "Other semiconductor companies"},
               {"symbol": "AAA", "name": "A", "from": "Oilfield services (larger)", "to": "Oilfield services (smaller)"}]},
           {"d": "2026-11-17", "cause": "rules", "counts": {"moved": 2}, "moved": [
               {"symbol": "BIGBLOC", "name": "BigBloc", "from": "Other cement companies", "to": "Cement integrated producers (smaller)"},
               {"symbol": "OSIS", "name": "OSI", "from": "Other semiconductor companies", "to": "Fabless chip design"}]},
           {"d": "2026-11-18", "cause": "rules", "counts": {"moved": 1}, "moved": [
               {"symbol": "BIGBLOC", "name": "BigBloc", "from": "Cement integrated producers", "to": "Other cement companies"}]},
           {"d": "2026-11-19", "cause": "rules", "counts": {"moved": 1}, "moved": [
               {"symbol": "OSIS", "name": "OSI", "from": "Fabless chip design", "to": "Makers of their own products"}]}]
    got = theme_changes.net_moves(log)
    moves = [(r["symbol"], r["to"]) for e in got for r in e.get("moved") or []]
    assert moves == [("OSIS", "Makers of their own products")]
    assert [e["counts"]["moved"] for e in got] == [1]
    # and a new read never logs a re-split
    was = {"layers": ["Oilfield services (larger)"], "cos": {"AAA": ["A", 0, None, None, None, None]}}
    now = {"layers": ["Oilfield services (smaller)"], "cos": {"AAA": ["A", 0, None, None, None, None]}}
    assert theme_changes.diff(was, now)["moved"] == []


# ---------- 5. LIVE17A-009: a theme page's change log reads each company once, in one round trip a hundred ----------
def test_e81_the_change_log_reads_each_company_once_and_its_industry_only_without_a_line():
    reads, inds, pre = [], [], []

    def words(s_):
        reads.append(s_)
        return "We drill wells and sell crude oil." if s_ != "NOWORDS" else ""
    words.prefetch = lambda syms: pre.append(list(syms))
    log = [{"moved": [{"symbol": s_, "name": s_, "from": "A layer", "to": "Other oil companies"} for s_ in ("X", "Y", "NOWORDS")]} for _ in range(4)]
    theme_changes.reasoned(log, words, lambda s_: inds.append(s_) or "Crude Petroleum")
    assert sorted(reads) == ["NOWORDS", "X", "Y"] and inds == ["NOWORDS"] and pre == [["NOWORDS", "X", "Y"]]


# ---------- 6. memory: the re-check never reads a dive to learn it is kept; large results kept as ASCII; bounded caches ----------
def test_e81_the_recheck_learns_a_dive_is_kept_from_the_index_and_never_reads_it(w, monkeypatch):
    keep("ships", payload("Ships"))
    built = []

    def build(r, theme, fm, src):
        built.append(theme)
        return {"sector": "Ships", "layers": [{"layer": "Yards", "companies": [{"symbol": f"S{i}", "what": "“₹” " * 50} for i in range(50)]}]}
    monkeypatch.setattr(theme_data, "build", build)
    monkeypatch.setattr(theme_routes, "sources", lambda *a, **k: type("S", (), {"pieces": {}, "about": lambda self, s_: None})())
    monkeypatch.setattr(theme_routes, "dive_gaps", lambda *a, **k: [])
    monkeypatch.setattr(theme_routes, "membership_check", lambda *a, **k: {})
    monkeypatch.setattr(theme_routes, "auto_post", lambda *a, **k: None)
    got_dive = []
    real_get = computed.get
    monkeypatch.setattr(computed, "get", lambda kind, key, count=True: got_dive.append(kind) if kind == theme_library.DIVE else real_get(kind, key, count))
    released = []
    monkeypatch.setattr(theme_recheck, "release", lambda: released.append(1))
    theme_recheck.queue()
    assert theme_recheck.step()["outcome"] == "rebuilt"
    assert built and theme_library.DIVE not in got_dive and released == [1]
    # the dive is kept as ASCII JSON (one byte a character in memory), and reads back the same
    hk = next(iter(computed.index(theme_library.DIVE)["entries"]))
    from app import db
    raw = db.get_setting(f"{computed.PREFIX}{theme_library.DIVE}:{hk}")
    assert raw.isascii() and "₹" in json.dumps(json.loads(raw), ensure_ascii=False)
    assert theme_routes.UNKEPT_MAX <= 2


def test_e81_the_members_tables_listed_twice_symbols_are_read_from_the_index_not_the_dive(w, monkeypatch):
    keep("ships", payload("Ships"))
    p = theme_library.stored("IN", "ship")["payload"]
    key = theme_routes.dive_key("IN", "ship", {**p, "_library": "ship"})
    computed.put(theme_library.DIVE, key, {"dive": {"duplicates": [{"symbol": "ESBA"}]}, "pieces": {}}, label="Ships", region="IN",
                 meta={"q": "ship", "rules": theme_base.RULES, "dups": ["ESBA"]})
    theme_routes._DUPS.clear()
    monkeypatch.setattr(computed, "get_hk", lambda *a, **k: (_ for _ in ()).throw(AssertionError("the dive was read")))
    assert theme_routes.dive_duplicates("IN", "ship") == {"ESBA"}


# ---------- 7. the R79 deck checks ----------
def test_e81_each_layer_of_one_profile_names_itself_and_not_available_is_said_once():
    from app.intel import sector_ops
    pid = next(iter(sector_ops.BY_PROFILE))
    rows = [{"layer": f"Hotels and resorts ({h})", "ops": {"profile": pid, "measures": [], "none": ["a", "b"]}} for h in ("larger", "smaller")]
    got = deck.profile_summary(rows)
    text = "Each layer on its own measures\n" + got + " Not in this table (no one way of earning): Other hotel companies."
    said = {}
    for m in deck_check._PROFILES_LINE.finditer(deck_check.flat_text(text)):
        for item in m.group(1).split("; "):
            name, _, rest = item.partition(": ")
            said[name.rsplit(", ", 1)[0].strip().lower()] = rest
    assert {"hotels and resorts (larger)", "hotels and resorts (smaller)"} <= set(said)


def test_e81_a_quote_cut_in_a_change_log_ends_at_a_clause_never_inside_a_word():
    got = theme_changes.clip_words("its own words say “In informative layers located to the north, the bank serves farmers, and also located to "
                                   "the south of the city river basin”", 110)
    assert got.endswith("serves farmers…”") and "south…" not in got


def test_e81_deck_check_reads_a_reason_after_a_name_ending_in_inc():
    t = ("Since the previous version placement rules: added 4: iHeartMedia, Inc., Sirius XM Holdings Inc., Spotify Technology S.A., Unity "
         "Software Inc. (filed under an official industry of the theme); moved between layers 1.")
    assert not deck_check.check_text(t)["counts"]["added unexplained"]
    assert deck_check.check_text("Since the previous version: added 2: Foo Ltd, Bar Ltd; moved 1.")["counts"]["added unexplained"]   # guard


def test_e81_versions():
    from app.intel import sector_metrics
    assert theme_base.RULES == 77 and theme_routes.PLACE_CARRY[77] == 76 and theme_routes.PLACE_CARRY[76] == 75 and theme_routes.EARLIER_MAX == 32          # (updated on purpose: e82 RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48)
    assert theme_data.DIVE_TEXT == 48 and deck.THEME_DECK_VERSION == 88 and sector_metrics.VERSION == 3


# ---------- owner P0-a (R79 REITs deck): the FFO Camden reports, $744.8 m, first; the derived proxy with its gains deducted ----------
# Camden Property Trust's FY2025 10-K, Item 7, its reconciliation as the filing's text reads (SEC EDGAR, accession 0001628280-26-007697)
CAMDEN_10K = ("Reconciliations of net income attributable to common shareholders to FFO, Core FFO, and Core AFFO for the years ended December "
              "31, 2025 and 2024 are as follows: 23 Table of Contents ($ in thousands) 2025 2024 Funds from operations Net income attributable to "
              "common shareholders $ 384,462 $ 163,293 Real estate depreciation and amortization 597,925 569,998 Impairment associated with land "
              "development activities 12,916 40,988 Gain on sale of operating properties (260,910) (43,806) Income allocated to non-controlling "
              "interests 10,436 7,547 Funds from operations $ 744,829 $ 738,020 Casualty-related expenses, net of (recoveries) (1,354) 5,849 "
              "Core FFO $ 762,551 $ 761,190")


def test_e81_camden_reported_nareit_ffo_is_read_and_used_never_the_derived_proxy_in_silence():
    from app.intel import sector_metrics as SM
    assert SM.reported_ffo(CAMDEN_10K) == 744.8
    assert SM.reported_ffo("Core FFO $ 762,551 and Normalized FFO $ 700,000 and FFO per diluted share $ 6.79") is None     # guard
    got = SM.with_reported_ffo({"ffo": {"v": 734.6, "period": "Fiscal year to Dec 2025", "source": "derived"}}, CAMDEN_10K, 1574.0)
    assert got["ffo"]["v"] == 744.8 and got["ffo"]["basis"] == "reported" and got["ffo_derived"]["v"] == 734.6
    assert got["ffo_share"]["v"] == 47.3
    # with no report text, the derived one is marked as derived
    assert SM.with_reported_ffo({"ffo": {"v": 734.6, "period": "p", "source": "s"}}, "", None)["ffo"]["basis"] == "derived"
    assert SM.REIT_V >= 2                         # the property owners' pieces read again


def test_e81_camden_derived_ffo_deducts_its_gains_on_property_sales():
    """The R79 deck's $996 m: Camden's $260.9 m of gains filed as "GainLossOnDispositionOfAssets" were never deducted."""
    from app.intel import sec
    from app.intel import sector_metrics as SM
    facts = sec.drop_scale_slips(json.loads((pathlib.Path(__file__).parent / "fixtures" / "e81_camden_facts.json").read_text()))
    got = SM.reit_figures(facts, "2025-12-31", "USD", 1574e6, "Fiscal year to Dec 2025", "src")
    assert got["ffo"]["v"] == 734.6 and "gains on property sales 260.9" in got["ffo"]["source"]


def test_e81_a_layers_ffo_medians_are_of_one_basis_and_a_reported_ffo_is_marked_on_its_row():
    def row(s_, p, basis):
        return {"symbol": s_, "name": s_, "revenue": 100.0, "ebitda": 50.0, "p_ffo": p, "ffo_share": 40.0, "ffo_basis": basis, "status": "confirmed"}
    rows = [row("CPT", 13.0, "reported"), row("ESS", 20.0, "reported"), row("MAA", 15.0, "reported"), row("X", 40.0, "derived")]
    b = theme_data.layer_block("Residential landlords", rows, set())
    assert b["ffo_basis"] == "reported" and b["ffo_apart"] == 1 and b["stats"]["p_ffo"]["median"] == 15.0
    assert deck.co_cell({**rows[0], "official_industry": "Real Estate Investment Trusts"}, "p_ffo", None) == "13.0x (reported)"
    # (updated on purpose, e82 LIVE18A-007: a derived figure is marked derived on its cell, under a column that names neither)
    assert deck.co_cell({**rows[3], "official_industry": "Real Estate Investment Trusts"}, "p_ffo", None) == "40.0x (derived)"


# ---------- owner P0-b (R79 Textiles and IT services decks): a stored figure never decides a company's layer ----------
def test_e81_no_company_leaves_its_layer_for_having_no_stored_figure_on_the_live_textiles_and_it_services_inputs():
    import copy
    from tests.test_d53_fixes import inputs, replay
    for rel, keeps in (("r60/textiles.json", "ADDIND"), ("inputs_r49/it.json", "OFSS")):
        d = inputs(rel)
        figs = d.get("figures") or {}
        out = replay(copy.deepcopy(d), published=d.get("published") or {}, figures_of=lambda s_, f=figs: f.get(s_))
        rest = [c for v in out["value_chain"] if v.get("official") and v.get("basis") == "rest" for c in v["companies"]]
        assert not [c["ticker"] for c in rest if "no figure stored" in str((c.get("refit") or {}).get("why") or "")], rel
        assert keeps not in {c["ticker"] for c in rest}, rel
        assert all((c.get("refit") or {}).get("why") for c in rest if (c.get("refit") or {}).get("from")), rel    # each with its business reason


# ---------- owner P0-c (R79 Payments deck): each company that crosses into or out of the core members is named ----------
def test_e81_a_company_that_crosses_into_the_core_members_is_named_with_why_in_the_change_log():
    dive = {"population_rule": 2, "adjacent": [{"symbol": "SYF", "kind": "lenders"}],
            "layers": [{"layer": "Card networks", "companies": [{"symbol": "V", "name": "Visa", "revenue": 1.0},
                                                                {"symbol": "TOST", "name": "Toast", "revenue": 2.0},
                                                                {"symbol": "NEW", "name": "Newco", "revenue": 2.0},
                                                                {"symbol": "SYF", "name": "Synchrony", "revenue": 3.0}]}]}
    snap = {"pop": 2, "adj": {"SYF": "lenders"}, "cos": {"V": ["Visa", 0], "TOST": ["Toast", 0, None, None, None, ""], "SYF": ["S", 0]},
            "core": ["V"]}
    pc = theme_changes.population_change(snap, dive)
    assert pc["core"] == [1, 3]
    assert {x["symbol"]: x["why"] for x in pc["core_in"]} == {"NEW": "it is new to the theme",
                                                               "TOST": "its figures are stored now (it had none in the previous version)"}
    said = deck.population_said(pc)
    assert "Core members with figures 1 to 3" in said and "Toast (its figures are stored now" in said
    assert theme_changes.snapshot(dive)["core"] == ["NEW", "TOST", "V"]


def test_e81_a_property_layer_in_a_fertilizer_theme_raises_a_theme_scope_warning():
    assert theme_base.PROPERTY_LAYER.search("Property developers") and not theme_base.PROPERTY_THEME.search("Fertilizers and agrochemicals")
    assert theme_base.PROPERTY_THEME.search("Real estate")
