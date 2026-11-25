"""Lane e89 (Release 89 engine): theme map hygiene from the owner's Alcoholic beverages deck (25 Nov) and the open engine items. Each test fails
on Release 88 (origin/main c5cce2b) and passes after, except those marked as guards. The companies' words and figures are the live ones of
the Alcoholic beverages dive read on 25 Nov 2026 (GET /research/theme-dive, region IN)."""
from app import main  # noqa: F401, I001  (main first: it loads the modules in the order they need)
from app.intel import theme_base as B
from app.intel import theme_data as D

BOROSIL = ("Borosil Renewables is engaged in manufacturing extra clear patterned glass and Low Iron Solar Glass for application in Photovoltaic "
           "panels, Flat plate collectors and Greenhouses")
AGI = ("Incorporated in 1960, AGI Greenpac Ltd manufactures and sells Container Glass bottles, PET bottles and Security Caps and Closures under "
       "Packaging Products.")


def _alco_vc() -> list[dict]:
    """The live Alcoholic beverages map's layers (17 Nov 2026), its "Other" group last."""
    return [{"layer": "Glass bottle and packaging manufacturing", "companies": [{"ticker": "AGI", "name": "AGI Greenpac Limited"}]},
            {"layer": "Grain distilling and extra neutral alcohol", "companies": [{"ticker": "GLOBUSSPR", "name": "Globus Spirits Limited"}]},
            {"layer": "Spirits brand owning and bottling (larger)", "companies": [{"ticker": "UNITDSPR", "name": "United Spirits Limited"}]},
            {"layer": "Beer brewing and sale", "companies": [{"ticker": "UBL", "name": "United Breweries Limited"}]},
            {"layer": "Wine making and sales", "companies": [{"ticker": "SULA", "name": "Sula Vineyards Limited"}]},
            {"layer": "Other alcoholic beverage companies", "official": True, "basis": "rest", "companies": []}]


# ---------- 1. Off-theme companies: one shared word of another trade keeps no company in the theme ----------
def test_a_solar_glass_maker_is_not_kept_in_the_theme_on_glass_and_extra():
    """Fails on R88: Borosil Renewables (solar glass, filed under Glass - Industrial), left out by the map's check for "Packaging inputs: glass
    bottles", was kept in "Other alcoholic beverage companies" as description-verified on "glass" (the bottle layer's) and "extra" (of "extra
    neutral alcohol"), its 28% margin in the Other group's medians."""
    pl = {"dropped": [{"ticker": "BORORENEW", "name": "Borosil Renewables Limited", "groups": ["Packaging inputs: glass bottles"], "said": "no"}]}
    vc, got = B.layer_answer_removals(_alco_vc(), pl, lambda s: BOROSIL, "Alcoholic beverages", lambda s: {"industry": "Glass - Industrial"})
    assert "BORORENEW" not in {c["ticker"] for v in vc for c in v["companies"]}
    assert [(x["ticker"], x["said"]) for x in got["dropped"]] == [("BORORENEW", "scope")]
    assert got["dropped"][0]["scope"].startswith("another business: its own words say “Borosil Renewables is engaged in manufacturing extra clear")
    assert not got.get("layer_no")
    assert B.layer_work_stems(B.kind_stems(B.own_text(BOROSIL)), _alco_vc(), "Alcoholic beverages") == set()


def test_guard_words_that_say_a_layers_work_or_the_theme_still_keep_a_company():
    """Guard: a glass-bottle maker's words ("Container Glass bottles") say the bottle layer's work, and words naming the theme ("alcoholic
    beverages") or two words of a layer ("extra neutral alcohol") keep a company against one layer's answer, quoted."""
    words = {"G": AGI, "A": "Ace Ltd makes alcoholic beverages for the domestic market.", "E": "Eno Ltd produces extra neutral alcohol from grain."}
    pl = {"dropped": [{"ticker": t, "name": t, "groups": ["Packaging inputs: glass bottles"], "said": "no"} for t in words]}
    vc, got = B.layer_answer_removals(_alco_vc(), pl, words.get, "Alcoholic beverages", lambda s: {})
    other = {c["ticker"]: c for c in vc[-1]["companies"]}
    assert set(other) == {"G", "A", "E"} and not got.get("dropped")
    assert "Container Glass bottles" in other["G"]["theme"]["why"] and "alcoholic beverages" in other["A"]["theme"]["why"]


# ---------- 6a. Semiconductors' missing own words: the annual-report reader finds Item 1 where it missed it ----------
def _openings() -> dict:
    import json
    import pathlib
    return json.loads((pathlib.Path(__file__).parent / "fixtures" / "sec_openings_e89.json").read_text())


def test_the_annual_report_reader_finds_the_opening_of_item_1_in_five_flagship_reports():
    """Fails on R88: Skyworks' and MACOM's contents pages print "ITEM 1A: RISK FACTORS." (a colon), so the contents page's Item 1 ran on and
    their cautionary notes were read as what they do; Intel's and McDonald's 10-Ks, set out of the form's order, gave nothing; Arm's 20-F
    gave "In today’s technology-driven world, semiconductors are ...". The texts are the reports' own lines (sec.report_lines) around the
    parts read, from their latest annual reports on the SEC's site (read 25 Nov 2026)."""
    from app.intel import sec
    got = {k: sec.business_opening(v) for k, v in _openings().items()}
    assert got["SWKS"].startswith("Skyworks Solutions, Inc., together with its consolidated subsidiaries")
    assert got["MTSI"].startswith("We design, develop and manufacture differentiated radio frequency")
    assert got["INTC"].startswith("We are a global designer and manufacturer of semiconductor products.")
    assert got["MCD"].startswith("The Company franchises and owns and operates McDonald’s restaurants")
    assert got["ARM"].startswith("The Company is a global leader in the semiconductor industry.")
    for k, v in got.items():
        assert B.has_own_line(B.quotable(v, "US") or ""), k          # each a line a page may quote about its work


def test_a_record_read_by_the_old_reader_with_no_line_to_quote_is_read_once_more():
    """Fails on R88: Intel's record, read under QUOTE_V 1 by a reader that found no opening, was marked read (qv 1) and never asked again, so
    it stayed "industry-supported (official industry only)"; the reads kept a month (sec.BUSINESS_KEY) are the new reader's too."""
    from datetime import datetime, timezone
    from app.intel import sec
    from app.intel import theme_routes as TR
    old = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "op": TR.OWN_PART_V, "v": TR.ABOUT_V, "bv": 5, "qv": 1,
           "about": "Intel Corporation is an American multinational technology company headquartered in Santa Clara, California.", "industry": ""}
    assert TR.quote_due(old, "US", "Intel Corp") and TR.thin_about(old, "US", "Intel Corp")
    assert not TR.quote_due({**old, "qv": TR.QUOTE_V}, "US", "Intel Corp")          # guard: read once by this reader, not again
    assert sec.BUSINESS_KEY[1] == 6 and TR.QUOTE_V == 2          # (changed on purpose, e89)


# ---------- 2. Shells and dust: one size and quality floor for every theme's layer tables and medians ----------
def _alco_dive(extra: dict | None = None, corp: dict | None = None, spirits: tuple = ()):
    """A dive of three spirits makers and Tahmar Enterprises as the live store holds it (₹2.3 crore of revenue in its year to Mar 2026, no
    market value, −361.7% EBITDA margin), its figures as the live dive printed them."""
    from tests.test_theme1 import TODAY, facts
    F = {"UNITDSPR": facts("UNITDSPR", "United Spirits Limited", [10000, 11000, 11900, 12467], [16, 17, 18, 19], [1100, 1200, 1500, 1700],
                           cap=107487),
         "GLOBUSSPR": facts("GLOBUSSPR", "Globus Spirits Limited", [2300, 2400, 2600, 2710], [9, 8, 7, 8], [100, 60, 30, 70], cap=2367),
         "ASALCBR": facts("ASALCBR", "Associated Alcohols & Breweries Ltd.", [700, 800, 950, 1020], [8, 9, 10, 11], [40, 50, 70, 80], cap=1060),
         "TAHMARENT": facts("TAHMARENT", "Tahmar Enterprises Ltd", [2.56, 5.45, 3.87, 2.3], [-5.08, -44.95, -206.2, -361.74],
                            [0.0, 0.05, -2.61, -5.6], cap=None),
         **(extra or {})}
    grain = [{"ticker": s, "name": F[s]["name"], "what": "manufactures extra neutral alcohol and liquor", "verified": True}
             for s in ("GLOBUSSPR", "ASALCBR", "TAHMARENT") + tuple(x for x in (extra or {}) if x not in spirits)]
    checked = {"sector": "Alcoholic beverages", "sub_themes": [], "placements": {"checked": True, "pending": 0},
               "value_chain": [{"layer": "Spirits brand owning and bottling", "description": "", "companies": [
                                   {"ticker": s, "name": F[s]["name"], "what": "makes and sells whisky", "verified": True}
                                   for s in ("UNITDSPR",) + spirits]},
                               {"layer": "Grain distilling and extra neutral alcohol", "description": "", "companies": grain}]}
    return D.build("IN", "Alcoholic beverages", checked, D.Sources(TODAY, facts=F.get, corp_history=lambda s: (corp or {}).get(s) or []))


def test_a_shell_is_in_no_layers_table_or_median_and_listed_once_with_why():
    """Fails on R88: Tahmar Enterprises (₹2.3 crore of revenue, no market value) was a row of "Grain distilling and extra neutral alcohol",
    its −361.7% EBITDA margin in the layer's median."""
    dive = _alco_dive()
    grain = next(b for b in dive["layers"] if b["layer"].startswith("Grain distilling"))
    assert "TAHMARENT" not in {c["symbol"] for c in grain["companies"]}
    assert grain["stats"]["ebitda"]["min"] > 0 and grain["n"] == 2
    small = {x["symbol"]: x for x in dive["too_small"]}
    assert set(small) == {"TAHMARENT"} and small["TAHMARENT"]["layer"] == "Grain distilling and extra neutral alcohol"
    assert small["TAHMARENT"]["why"] == "revenue of ₹2 crore in Mar 2026 and no market value"
    assert dive["evidence"]["TAHMARENT"]              # still a member of the theme, with its evidence
    assert "TAHMARENT" not in {r["symbol"] for r in dive["sections"]["size"].get("biggest") or []}


def test_the_floor_takes_small_or_stale_companies_and_leaves_the_rest():
    """The floor (dust_of): revenue and market value both under it, no market value with small revenue, or a latest year a year or more
    before the theme's; guards: a small company over either floor, a pre-revenue company with a large market value."""
    base = {"status": "core", "revenue": 9.0, "cap": 75.18, "year": "Mar 2026", "profit": -10.0}       # Kati Patang Lifestyle, live
    assert D.dust_of("IN", base, "Mar 2026").startswith("revenue of ₹9 crore in Mar 2026 and a market value of ₹75 crore, both under")
    assert D.dust_of("IN", {**base, "revenue": None, "cap": 200.71}, "Mar 2026").startswith("no revenue in Mar 2026")     # Cupid Breweries
    assert D.dust_of("IN", {**base, "year": "Mar 2025 (S)", "revenue": 500.0, "cap": 900.0}, "Mar 2026") == \
        "its latest full year is Mar 2025 (S), a year or more before the theme's Mar 2026"
    assert D.dust_of("IN", {**base, "revenue": 19.8, "cap": 42.04}, "Mar 2026") == ""         # Ravikumar Distilleries: revenue over the floor
    assert D.dust_of("IN", {**base, "revenue": 9.0, "cap": 337.0}, "Mar 2026") == ""          # a market value over the floor
    assert D.dust_of("US", {**base, "revenue": None, "cap": 900.0, "year": "Dec 2025"}, "Dec 2025") == ""      # pre-revenue, valued
    assert D.dust_of("US", {**base, "revenue": 0.7, "cap": 1.2, "year": "Dec 2025"}, "Dec 2025").startswith("revenue of $0.7 million")
    assert D.dust_of("IN", {**base, "status": "unverified"}, "Mar 2026") == ""
    assert D.theme_period([{"year": "Mar 2026", "revenue": 5, "status": "core"}] * 3 + [{"year": "Dec 2025", "revenue": 5, "status": "core"}]) == "Mar 2026"


def test_the_deck_lists_the_floors_companies_once_in_its_appendix():
    """Fails on R88: the deck printed Tahmar's row of n.m. in the layer's table; now one appendix page lists it, with why, and no layer
    table holds it."""
    from app import deck
    from app.intel import theme_routes as TR
    from tests.test_r18_deck import NOW
    dive = _alco_dive()
    m = {"sector": "Alcoholic beverages", "value_chain": [], "placements": {"checked": True}}
    slides = deck.theme_plan(TR.deck_view("IN", m, dive), now=NOW)[0]
    small = [s for s in slides if s.title.startswith(deck.DUST_TITLE)]
    assert len(small) == 1
    rows = [r for b in small[0].blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict)]
    assert rows == [["Tahmar Enterprises Ltd", "Grain distilling and extra neutral alcohol", "revenue of ₹2 crore in Mar 2026 and no market value"]]
    others = [r for s in slides if not s.title.startswith(deck.DUST_TITLE) for b in s.blocks if b["kind"] == "table"
              for r in b["rows"] if not isinstance(r, dict) and any("Tahmar" in str(x) for x in r)]
    assert not others


# ---------- 4. Indian flagships with no stored words of their own: a profile page under the company's earlier name ----------
KPIL = ("Kalpataru Power Transmission Ltd is a global EPC player with diversified interest in power transmission and distribution, oil and gas "
        "pipeline, railways and biomass based power generation.")


def test_an_indian_profile_page_under_the_companys_earlier_name_is_kept_as_its_own_words(monkeypatch):
    """Fails on R88: Kalpataru Projects International (₹22,648 crore, Capital goods) had no description of its own: its profile page, read by
    its symbol, opens on its earlier name "Kalpataru Power Transmission Ltd", which own_part took for another company's (Gujarat Energy's
    "Gujarat Gas Limited (GGL) is ...", Accelya's "Accelya Kale Solutions Is ..." the same)."""
    import json
    import types
    from app.intel import theme_routes as TR
    key, kept = "theme:evidence:IN:KPIL", {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "set_setting", lambda k, v: kept.__setitem__(k, v))
    hub = types.SimpleNamespace(wiki=types.SimpleNamespace(company=lambda name: None), screener=None)
    monkeypatch.setattr(TR, "_routes", lambda: types.SimpleNamespace(hub=hub, public_facts=None, index_rows=lambda r: []))
    monkeypatch.setattr(TR, "own_filings", lambda region, sym: "")
    monkeypatch.setattr(TR, "india_profile", lambda screener, sym, code_of=None: {"about": KPIL, "industry_path": ["Civil Construction"]})
    TR.EVIDENCE_CACHE.pop(key)
    got = TR.evidence_reader("IN", {"KPIL": "Kalpataru Projects International Ltd"})(["KPIL"])[0]
    assert got["KPIL"]["about"].startswith("Kalpataru Power Transmission Ltd is a global EPC player")
    stored = json.loads(kept[key])
    assert stored["about"].startswith("Kalpataru Power Transmission") and stored["page"] and stored["op"] == TR.OWN_PART_V == 3
    assert TR.own_got("IN", "KPIL", stored, "Kalpataru Projects International Ltd")[0]["about"] == stored["about"]
    assert B.earlier_name("Gujarat Gas Limited (GGL) is a government company u/s 2(45) of Companies Act 2013.", "Gujarat Energy Ltd")
    # guards: another company's encyclopedia article (no profile page of its own) is still cut; a fuller name is own_part's own case
    assert B.own_part("Toyo Tire Corporation is a Japanese tire maker.", "TOYO Co., Ltd") == ""
    assert not B.earlier_name("Jindal Steel & Power Limited is an Indian steel maker.", "Jindal Steel Limited")
    TR.EVIDENCE_CACHE.pop(key)


def test_a_flagship_spirits_makers_words_verify_it_by_the_drinks_it_makes():
    """Fails on R88: Radico Khaitan ("one of the most recognised IMFL (Indian Made Foreign Liquor) brands in India"), Silver Oak ("processing
    country liquor") and Winsome Breweries ("manufacturing and selling of beers") were "industry-supported (official industry only)": the
    theme's names say "spirits", "beer", "alcohol", never "liquor", "IMFL" or "beers" (the live map; its industries picked by the AI)."""
    checked = {"sector": "Alcoholic beverages", "placements": {"industries_by": "ai", "industries": ["Breweries & Distilleries"]},
               "value_chain": [{"layer": n, "companies": []} for n in ("Glass bottle and packaging manufacturing",
                                                                       "Grain distilling and extra neutral alcohol",
                                                                       "Spirits brand owning and bottling (larger)", "Beer brewing and sale",
                                                                       "Wine making and sales")]
               + [{"layer": "Other alcoholic beverage companies", "official": True, "basis": "rest", "companies": []}]}
    wt = D.work_test(checked, "Alcoholic beverages")
    for name, line in (("Radico Khaitan Limited", "Incorporated in the year 1943, Radico Khaitan is one of the most recognised IMFL (Indian Made "
                                                  "Foreign Liquor) brands in India"),
                       ("Silver Oak (India) Ltd", "Silver Oak India Ltd is engaged in the business of processing country liquor"),
                       ("Winsome Breweries Ltd", "Winsome Breweries Ltd is in the business of manufacturing and selling of beers")):
        c = {"ticker": "X", "name": name, "what": line, "base": True, "verified": False, "basis": "industry"}
        assert D.work_checked("description_verified", c, line, wt) == "description_verified", name
    # guard: a word of another trade still verifies none (a chemicals maker's words)
    c = {"ticker": "Y", "name": "Chem Ltd", "what": "Chem Ltd manufactures specialty chemicals and natural gums", "base": True, "verified": False}
    assert D.work_checked("description_verified", c, c["what"], wt) == "industry_code_supported"


# ---------- 6b. Host Hotels: a lodging REIT's own words say its work ----------
def test_a_lodging_reits_own_words_are_a_line_of_its_work():
    """Fails on R88: Host Hotels' 10-K opening, "We are the largest publicly traded lodging REIT, with a geographically diverse portfolio of
    luxury and upper-upscale hotels", was no line of its own words (no word of work), so it was industry-supported with "no description in
    its own words", placed by the AI alone and once in "Other" though a hotel REITs layer exists."""
    from app.intel import theme_routes as TR
    hst = ("We are the largest publicly traded lodging REIT, with a geographically diverse portfolio of luxury and upper-upscale hotels. As of "
           "February 20, 2026, our consolidated lodging portfolio consists of 76 primarily luxury and upper-upscale hotels containing "
           "approximately 41,700 rooms.")
    assert TR.quotable_work(hst, "Host Hotels & Resorts, Inc.")
    assert B.own_line(hst, "Host Hotels & Resorts, Inc.").startswith("We are the largest publicly traded lodging REIT")
    c = {"ticker": "HST", "name": "Host Hotels & Resorts, Inc.", "what": "", "base": True, "verified": False, "basis": "industry"}
    words = D._stems("Real estate investment trusts Hotel and leisure property owners hotels resorts lodging")
    assert D.evidence_state(c, words, B.quotable(hst, "US")) == "description_verified"


# ---------- 5. Size split sanity: a company that demerged the theme's business since its latest year is the whole company ----------
def test_a_company_whose_spirits_business_was_demerged_since_its_year_sets_no_layer_median():
    """Fails on R88: India Glycols (mostly chemicals) stood in "Spirits brand owning and bottling (larger)" on its whole year to Mar 2026,
    its spirits business demerged on 2 Sep 2026 (its Sep 2026 quarter's revenue 66.8% below the year before), its figures in the layer's
    median: the "(whole company)" rule did not cover it (no segments stored, filed under Breweries & Distilleries)."""
    from tests.test_theme1 import facts
    ig = facts("INDIAGLYCO", "India Glycols Ltd", [2651, 3294, 3768, 4211], [11.5, 12.6, 13.6, 15.4], [141, 173, 231, 293], cap=1980,
               latest_yoy={"basis": "quarter", "of": "Sep 2026 vs Sep 2025", "sales": -66.8, "profit": -63.1})
    corp = {"INDIAGLYCO": [{"kind": "demerger", "ex_date": "2026-09-02", "text": "Demerger of the potable spirits business"}]}
    dive = _alco_dive({"INDIAGLYCO": ig}, corp=corp, spirits=("INDIAGLYCO",))
    assert "INDIAGLYCO" in dive["company_wide"]
    sp = next(b for b in dive["layers"] if b["layer"].startswith("Spirits brand"))
    assert sp["stats"]["ebitda"]["n"] == 1 and sp["stats"]["ebitda"]["median"] == 19          # United Spirits' alone
    # guard: a demerger with revenue since that did not fall (Vedanta's, +57.5%) leaves the figures as they are
    assert not D.split_since({"demerger": "2026-04-30", "year": "Mar 2026", "quarter": {"of": "Sep 2026 vs Sep 2025", "sales": 57.5}})
    assert not D.split_since({"demerger": "2025-12-29", "year": "Dec 2025", "quarter": {"of": "Sep 2026 vs Sep 2025", "sales": -70.0}})


# ---------- 3. Revenue basis: one basis (net of excise duty) for the alcohol layers, labelled where it can't be checked ----------
def test_a_liquor_makers_one_stored_year_on_an_unchecked_excise_basis_is_labelled_and_in_no_median():
    """Fails on R88: IGL Spirits' ₹8,416 crore (its only stored year, Mar 2026; India Glycols, the whole company its spirits business was
    demerged from, ₹4,211 crore) stood beside its layer's revenue net of excise duty, in the totals and the margin medians."""
    from tests.test_theme1 import facts
    igl = facts("IGLSPIRITS", "IGL Spirits Ltd", [8416, 8416, 8416, 8416], [5.8] * 4, [244] * 4, cap=5341,
                industry=("Fast Moving Consumer Goods", "Beverages", "Breweries & Distilleries"))
    igl["years"] = igl["years"][-1:]
    usl = facts("UNITDSPR", "United Spirits Limited", [10000, 11000, 11900, 12467], [16, 17, 18, 19], [1100, 1200, 1500, 1700], cap=107487,
                industry=("Fast Moving Consumer Goods", "Beverages", "Breweries & Distilleries"))
    dive = _alco_dive({"IGLSPIRITS": igl, "UNITDSPR": usl}, spirits=("IGLSPIRITS",))
    sp = next(b for b in dive["layers"] if b["layer"].startswith("Spirits brand"))
    row = next(c for c in sp["companies"] if c["symbol"] == "IGLSPIRITS")
    assert row["calc"]["in"] is False and row["calc"]["kind"] == D.BASIS_KIND
    assert row["calc"]["detail"].startswith("its revenue (₹8,416 crore, Mar 2026) is its only stored year")
    assert sp["stats"]["ebitda"]["n"] == 1 and sp["n"] == 1                        # United Spirits' alone
    assert D.EXCISE_NOTE in dive["basis"]
    # guards: a liquor maker with its series stored, and a company of another industry with one year, are on the store's basis
    assert D.basis_apart("IN", {"industry": ["Breweries & Distilleries"], "revenue": 6037.0, "years": [{"sales": 4843}, {"sales": 6037}]}) == ""
    assert D.basis_apart("IN", {"industry": ["Chemicals"], "revenue": 900.0, "years": [{"sales": 900}]}) == ""


# ---------- 6c. Gold miners: Peabody moved on a coal sentence; Newmont verified with no line of its own ----------
def test_a_coal_producer_is_not_moved_into_a_gold_and_silver_layer_on_metallurgical():
    """Fails on R88: Peabody's "Peabody is a leading producer of metallurgical and thermal coal." (and Core Natural Resources' coals)
    moved it into "Mid-sized gold, silver and mineral miners": "metallurgical" shares its first five letters with the description's
    "metals". Guards: a word the description says whole ("steel" of "steel-making inputs") still says it, and gold and silver words do."""
    desc = ("These companies mine and sell ore and primary metals such as gold, silver, steel-making inputs and rare earths from a small "
            "number of operating mines. They earn from selling what they produce at market prices, so results depend on each mine's grade "
            "and cost; this layer sets itself apart by mixing mid-sized gold and silver producers with a few other mineral miners and developers.")
    dest = {"layer": "Mid-sized gold, silver and mineral miners", "description": desc, "companies": []}
    tw = B.kind_stems("Gold miners")
    assert B.desc_fit(dest, "Peabody is a leading producer of metallurgical and thermal coal.", tw) == []
    assert B.desc_fit(dest, "We are a world-class producer and exporter of high-quality, low-cost coals, including metallurgical and thermal "
                            "coals.", tw) == []
    assert B.desc_fit(dest, "we reliably supply metallurgical coal products to the steel industry", tw) == ["steel"]
    assert "silve" in B.desc_fit(dest, "We mine silver at three operating mines in Nevada.", tw)


def test_newmonts_opening_is_its_own_sentence_and_old_reads_of_annual_reports_are_read_again():
    """Fails on R88: Newmont's 10-K opens "Newmont Corporation was incorporated in 1921 and is primarily a gold producer ...", passed over
    as a sentence of when it was formed (and the heading's "(dollars in millions ...)" read as prose), so its stored words were "Doré is an
    alloy ... Doré is sent to refiners ...": description-verified with no line of its own a deck quotes. Its record, read from its annual
    report by the earlier reader, is read once more."""
    from datetime import datetime, timezone
    from app.intel import sec
    from app.intel import theme_routes as TR
    got = sec.business_opening(_openings()["NEM"])
    assert got.startswith("Newmont Corporation was incorporated in 1921 and is primarily a gold producer")
    old = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "op": TR.OWN_PART_V, "v": TR.ABOUT_V, "bv": 5, "qv": 1, "filed": True,
           "about": "Doré is an alloy consisting primarily of gold but also containing silver and other metals. Doré is sent to refiners to "
                    "produce bullion that meets the required market standard of 99.95% gold.", "industry": ""}
    assert TR.quote_due(old, "US", "Newmont Corp")
    assert not TR.quote_due({**old, "bv": sec.BUSINESS_KEY[1], "qv": 1}, "US", "Newmont Corp")      # guard: read by today's reader
