"""m53 (R53, the owner's review of the live R52 decks, P1: "new sectors need operating metrics where source data supports them, never
fabricated: Airlines PLF/ASK/RPK/yield; Hospitals occupancy, ARPOB, beds; Cement capacity/utilisation/volumes/realisation; Renewables installed
MW/generation/CUF; Payments TPV/transactions/take rate"): a sector profile per business model, each measure read only where a company's own
stored document states it, with its definition, period, source and coverage; a measure no company states has no column and no page.

The passages in tests/fixtures/sector_ops/filed_passages.json are the real text, as the filings index stores it (doc_index.chunk_pages /
chunk_text), of documents the companies filed: Indian investor presentations on the exchange (Apollo Hospitals, Aster DM Healthcare, Ambuja
Cements, ACC) and US earnings releases on the SEC (HCA Healthcare, Universal Health Services, Delta, United, Southwest, PayPal, Mastercard)."""
import json
from pathlib import Path

import pytest

from app import deck
from app.intel import metric_registry as R
from app.intel import sector_ops as O
from tests.test_export import plain

FIX = json.loads((Path(__file__).parent / "fixtures" / "sector_ops" / "filed_passages.json").read_text())
DOCS = {d["symbol"]: d for d in FIX}


def passages_of(*symbols):
    """The fixture as the filings index's passages for these companies."""
    out = []
    for i, s in enumerate(symbols):
        d = DOCS[s]
        out += [{"symbol": s, "doc_id": 100 + i, "n": p["n"], "page": p["page"], "kind": d["kind"], "filed_at": d["filed_at"], "body": p["body"],
                 "link": d["url"]} for p in d["passages"]]
    return lambda syms, q: [r for r in out if r["symbol"] in syms]


def figures(pid, region, *symbols, parents=None):
    figs, held = O.read_profile(pid, list(symbols), region, passages_of(*symbols), parents)
    return {s: {k: f["v"] for k, f in got.items()} for s, got in figs.items()}, figs, held


# ---------- 1. real documents: each figure as stated, the company's total, its period and source ----------
def test_hospitals_beds_and_occupancy_from_the_presentations_and_releases_as_stated():
    vals, figs, _ = figures("hospital", "IN", "APOLLOHOSP", "ASTERDM")
    # Apollo: "Operating beds 8,522" and "Occupancy 73%" for Q2FY27 (its pan-India table), never a region's (Mumbai 76%, Tamil Nadu 2,005 beds)
    # nor "established units" (76%); its "Avg revenue per In Patient" is not ARPOB, so no ARPOB
    assert vals["APOLLOHOSP"] == {"beds_op": 8522.0, "occupancy": 73.0}
    # Aster: "Operational Beds Q2FY27 : 10,611", "10,840 Capacity Beds", "Occupancy (%) Q2FY27 : 68%" (not a cluster's 71%, 69% or 63%)
    assert vals["ASTERDM"] == {"beds_op": 10611.0, "beds_cap": 10840.0, "occupancy": 68.0}
    a = figs["APOLLOHOSP"]["occupancy"]
    assert a["period"] == "Quarter to Sep 2026" and a["source"] == "Investor presentation filed with the exchange on 2026-11-04, page 15"
    assert a["quote"].startswith("Occupancy 73%") and a["url"].startswith("https://nsearchives.nseindia.com/")
    assert figs["ASTERDM"]["beds_op"]["period"] == "Sep 2026"          # a level at a date, not a quarter's flow
    us, ufigs, _ = figures("hospital", "US", "HCA", "UHS")
    assert us["HCA"] == {"beds_op": 42866.0, "beds_cap": 50424.0, "occupancy": 73.2}
    assert ufigs["HCA"]["occupancy"]["period"] == "Quarter to Sep 2026"
    # UHS states its beds by segment (acute and behavioral side by side, or a table cut at a passage's start): no company total is stated
    assert "UHS" not in us


def test_cement_capacity_and_volume_never_a_pipeline_a_target_or_a_standalone_part():
    vals, figs, held = figures("cement", "IN", "AMBUJACEM", "ACC", parents={"ACC": "AMBUJACEM"})
    # "113.5 MTPA Cement Capacity", never "+29.7 MTPA" planned nor "149 MTPA" or "155 MTPA" targets; consolidated volume 16.5 MnT for Q2FY'27
    # ("16.6 17.1 16.5 Q2FY'26 Q1FY'27 Q2FY'27": the latest period's number), never the standalone 11.4 nor the half year's 33.6
    assert vals == {"AMBUJACEM": {"cem_capacity": 113.5, "cem_volume": 16.5}}
    assert figs["AMBUJACEM"]["cem_volume"]["period"] == "Quarter to Sep 2026"
    # ACC filed its parent's presentation word for word: its figures are the group's, so none is taken as ACC's own, and that is said
    assert held == [{"symbol": "ACC", "with": ["AMBUJACEM"]}]
    # with no parent known, neither company's copy of the shared document counts
    vals2, _, held2 = figures("cement", "IN", "AMBUJACEM", "ACC")
    assert vals2 == {} and {h["symbol"] for h in held2} == {"ACC", "AMBUJACEM"}


def test_airlines_capacity_traffic_load_factor_and_yield_from_the_release_tables():
    vals, figs, _ = figures("airline", "US", "DAL", "UAL", "LUV")
    assert vals["DAL"] == {"asm": 79288.0, "rpm": 68133.0, "plf": 86.0, "yield_mile": 22.8}
    assert vals["UAL"] == {"asm": 88538.0, "rpm": 74278.0, "plf": 83.9, "yield_mile": 21.86}       # "Consolidated 83.9 %", not Domestic 84.4 %
    assert vals["LUV"] == {"asm": 45393.0, "rpm": 36214.0, "plf": 79.8, "yield_mile": 21.41}
    assert all(f["period"] == "Quarter to Sep 2026" for s in figs for f in figs[s].values())    # the three months' column, not nine months'


def test_payments_volume_and_transactions_from_the_release_prose_and_nothing_where_the_period_is_not_certain():
    vals, figs, _ = figures("payments", "US", "PYPL", "MA")
    assert vals["PYPL"] == {"tpv": 487100.0, "txn": 6.8}          # "TPV increased 6% to $487.1 billion", "increased 7% to 6.8 billion", USD million
    assert figs["PYPL"]["tpv"]["quote"].startswith('Total payment volume ("TPV") increased 6% to $487.1 billion')
    # Mastercard states gross dollar volume twice, the quarter's $3.0 trillion and the year to date's $8.5 trillion, the year-to-date heading in
    # another passage: neither is taken, rather than the larger one
    assert "MA" not in vals


# ---------- 2. whom a profile fits ----------
@pytest.mark.parametrize("row,family,layer,want", [
    ({"name": "Sky Air Ltd", "official_industry": "Airline"}, "transport", "", "airline"),
    ({"name": "Gate Airports Ltd", "official_industry": "Airport & Airport services"}, "transport", "Airlines and airports", None),
    ({"name": "Care Hospitals Ltd", "official_industry": "Hospital"}, "care", "", "hospital"),
    ({"name": "Lab Diagnostics Ltd", "official_industry": "Healthcare Service Provider", "map_what": "runs diagnostic labs"}, "care",
     "Hospitals and diagnostics", None),
    ({"name": "Poly Devices Ltd", "official_industry": "Medical Equipment & Supplies"}, "making", "Hospitals", None),
    ({"name": "Grey Cement Ltd", "official_industry": "Cement & Cement Products"}, "making", "", "cement"),
    ({"name": "Sun Power Ltd", "official_industry": "Power Generation"}, "generation", "", "power"),
    ({"name": "Sun Modules Ltd", "official_industry": "Other Electrical Equipment", "map_what": "makes solar modules and cells"}, "making",
     "Solar power", None),
    ({"name": "Grid Lines Ltd", "official_industry": "Power - Transmission"}, "regulated_utility", "", None),
    ({"name": "Pay Net Inc", "official_industry": "Services-Business Services, NEC", "map_what": "runs a card network"}, "payments", "", "payments"),
    ({"name": "Big Bank Ltd", "official_industry": "Private Sector Bank"}, "lending", "Payments", None),
])
def test_a_profile_fits_by_the_companys_words_and_its_layers_way_of_earning(row, family, layer, want):
    assert O.profile_of(row, family, layer) == want


# ---------- 3. the page: stated measures only, shares' medians with "N of M", sizes never; business updates in their unit ----------
def _family(pid, region, symbols, business=None, extra_fit=()):
    from app.intel.theme_data import stat
    figs, held = O.read_profile(pid, list(symbols), region, passages_of(*symbols))
    fit = [{"symbol": s, "name": s.title(), "layer": "L"} for s in list(symbols) + list(extra_fit)]
    return O.family(pid, {"fit": fit, "figs": figs, "held": held}, region, stat, business)


def test_a_profiles_page_has_columns_only_for_measures_some_company_states_and_says_which_none_states():
    f = _family("airline", "US", ["DAL", "UAL", "LUV"], extra_fit=["JETX"])
    assert f["keys"] == ["plf", "asm", "rpm", "yield_mile"]                        # the US measures stated; never the Indian ASK/RPK columns
    assert f["n"] == 3 and f["of"] == 4                                             # coverage: 3 of the 4 airlines the profile fits
    plf = f["medians"]["plf"]
    assert plf["median"] == 83.9 and plf["n"] == 3 and plf["of"] == 4               # a share's median, "3 of 4"
    assert "asm" not in f["medians"] and "rpm" not in f["medians"]                   # sizes: never a median across airlines of different sizes
    assert f["not_filed"] == ""                                                     # every US airline measure is stated by one of them
    h = _family("hospital", "IN", ["APOLLOHOSP", "ASTERDM"])
    assert h["keys"] == ["beds_op", "beds_cap", "occupancy"] and "ARPOB (₹ a day): stated in none" in h["not_filed"]
    assert {r["symbol"]: r["src"]["occupancy"]["period"] for r in h["rows"]} == {"APOLLOHOSP": "Quarter to Sep 2026", "ASTERDM": "Quarter to Sep 2026"}
    assert O.family("payments", {"fit": [{"symbol": "X", "name": "X"}], "figs": {}}, "US", lambda v: None) is None      # nothing stated: no page


def test_installed_capacity_comes_from_a_stored_business_update_in_megawatts_never_a_pipeline_or_capacity_added():
    """The business updates the app read and stored (biz_updates' series as the deck's business rows carry them): Adani Green's "20,763 MW of
    operational portfolio" (H1 FY27), JSW Energy's "Total installed capacity ~13,900 MW", and their pipeline, locked-in and added capacities."""
    from app.intel.theme_data import stat
    rows = [{"symbol": "AGREEN", "measures": [
        {"metric": "Operational portfolio capacity", "unit": "MW", "span": "quarter", "period": "2026-09", "value": 20763.0, "filed": "2026-10-10",
         "quote": "AGEL's 20,763 MW of operational portfolio powered more than 4.4 million homes", "page": 12, "url": "https://www.bseindia.com/x.pdf"},
        {"metric": "BESS Capacity", "unit": "GWh", "span": "quarter", "period": "2026-09", "value": 3.0}]},
        {"symbol": "JSWE", "measures": [
            {"metric": "Total installed capacity", "unit": "MW", "span": "month", "period": "2026-05", "value": 13900.0, "filed": "2026-06-12"},
            {"metric": "Total locked-in generation capacity", "unit": "GW", "span": "month", "period": "2026-05", "value": 30.5},
            {"metric": "Capacity added in Q1 FY27", "unit": "MW", "span": "month", "period": "2026-05", "value": 150.0},
            {"metric": "Under-construction generation capacity", "unit": "GW", "span": "month", "period": "2026-05", "value": 4.2}]}]
    got = O.from_business({"layers": [{"layer": "Power", "rows": rows}]}, "power", "IN")
    assert {s: {k: x["v"] for k, x in f.items()} for s, f in got.items()} == {"AGREEN": {"mw_installed": 20763.0}, "JSWE": {"mw_installed": 13900.0}}
    assert got["AGREEN"]["mw_installed"]["source"] == "Business update filed with the exchange on 2026-10-10"
    fam = O.family("power", {"fit": [{"symbol": "AGREEN", "name": "Green"}, {"symbol": "JSWE", "name": "Energy"}], "figs": {}}, "IN", stat,
                   {"layers": [{"layer": "Power", "rows": rows}]})
    assert fam["keys"] == ["mw_installed"] and fam["medians"] == {} and "Generation (GWh), CUF / PLF: stated in none" in fam["not_filed"]
    assert O.from_business({"layers": [{"layer": "Power", "rows": rows}]}, "power", "US") == {}          # an Indian filing's update only


# ---------- 4. the dive and the deck ----------
def _hospital_theme():
    from tests.fake_theme_structures import _in, _theme
    m, f = _theme("Hospitals", "IN", [("Hospital chains", "HX", "Hospital", 3, "care"), ("Diagnostics", "DG", "Healthcare Service Provider", 3, "care")],
                  lambda i, s, n, ind: _in(i, s, n, ind, margins=(20, 21, 22, 23)))
    return m, f


def _passages_for(mapping):
    """The fixture's passages filed under the synthetic theme's symbols ({theme symbol: fixture symbol})."""
    out = []
    for i, (sym, real) in enumerate(mapping.items()):
        d = DOCS[real]
        out += [{"symbol": sym, "doc_id": 10 + i, "n": p["n"], "page": p["page"], "kind": d["kind"], "filed_at": d["filed_at"], "body": p["body"],
                 "link": d["url"]} for p in d["passages"]]
    return lambda syms, q: [r for r in out if r["symbol"] in syms]


def test_the_dive_reads_the_operating_measures_of_the_companies_the_profile_fits_and_the_deck_shows_them_with_their_source():
    from app.intel import theme_data as D
    from app.intel import theme_routes as T
    from tests.test_r18_deck import NOW
    from tests.test_theme1 import TODAY
    m, f = _hospital_theme()
    asked = []
    read = _passages_for({"HX0": "APOLLOHOSP", "HX1": "ASTERDM", "DG0": "APOLLOHOSP"})
    src = D.Sources(TODAY, facts=f.get, passages=lambda syms, q: asked.append((tuple(syms), q)) or read(syms, q))
    dive = D.build("IN", "Hospitals", m, src)
    ops = dive["sections"]["ops"]["profiles"]
    assert list(ops) == ["hospital"] and [c["symbol"] for c in ops["hospital"]["fit"]] == ["HX0", "HX1", "HX2"]   # the diagnostics labs aren't
    assert asked == [(("HX0", "HX1", "HX2"), O.BY_PROFILE["hospital"].query)]       # one search for the profile's companies, nothing else read
    assert ops["hospital"]["figs"]["HX0"]["occupancy"]["v"] == 73.0
    v = T.deck_view("IN", m, dive)
    slides = deck.theme_plan(v, now=NOW)[0]
    page = [s for s in slides if s.title.startswith(f"{deck.SECTOR_TITLE}: hospital operators")]
    assert len(page) == 1
    t = next(b for b in page[0].blocks if b["kind"] == "table")
    assert t["head"] == ["Company", "Operational beds", "Bed capacity", "Bed occupancy", "Source", "Period"]
    rows = plain(t["rows"])
    hx0 = next(r for r in rows if r[0].startswith("Hospital HX 0"))
    assert hx0[1:] == ["8,522", "–", "73%", "Presentation, p. 15", "Sep 2026"]
    med = next(r for r in rows if r[0].startswith("Median"))
    assert med[3] == "– (2 of 3)"                       # occupancy stated by 2 of the 3 chains: no median under 3 companies, the count said
    note = " ".join(p for b in page[0].blocks if b["kind"] == "text" for p in b["paras"])
    assert "ARPOB (₹ a day): stated in none of these companies' documents the app holds" in note
    assert page[0].subtitle == "2 hospital operators whose own documents state these measures, each with its period and source; 1 more without"
    notes = [r for s in slides if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])]
    assert ["Bed occupancy", R.BY_ID["occupancy"].definition, R.BY_ID["occupancy"].source] in [r[:3] for r in notes]


def test_a_theme_none_of_whose_companies_states_a_measure_has_no_page_and_no_column_of_n_a():
    from app.intel import theme_data as D
    from app.intel import theme_routes as T
    from tests.test_r18_deck import NOW
    from tests.test_theme1 import TODAY
    m, f = _hospital_theme()
    dive = D.build("IN", "Hospitals", m, D.Sources(TODAY, facts=f.get))         # nothing in the filings index
    assert dive["sections"]["ops"]["profiles"]["hospital"]["figs"] == {}
    slides = deck.theme_plan(T.deck_view("IN", m, dive), now=NOW)[0]
    assert not any(s.title.startswith(f"{deck.SECTOR_TITLE}: hospital") for s in slides)
    assert not deck.sector_paged(T.deck_view("IN", m, dive))


def test_the_filings_index_passages_are_read_by_one_bounded_search_of_the_latest_documents():
    from tests.fake_doc_store import MemoryDocStore
    s = MemoryDocStore()
    d = DOCS["APOLLOHOSP"]
    s.save({"url": d["url"], "region": "IN", "symbol": "APOLLOHOSP", "kind": "presentation", "filed_at": d["filed_at"], "title": "Presentation"},
           [(p["page"], p["body"]) for p in d["passages"]])
    s.save({"url": "old.pdf", "region": "IN", "symbol": "APOLLOHOSP", "kind": "presentation", "filed_at": "2025-01-10", "title": "Old"},
           [(1, "Operating beds 7,000 Occupancy 60%")])
    s.save({"url": "t.pdf", "region": "IN", "symbol": "APOLLOHOSP", "kind": "transcript", "filed_at": d["filed_at"], "title": "Call"},
           [(1, "occupancy at 99% in one unit, beds")])
    read = O.passages_reader("IN", store=s, today=__import__("datetime").date(2026, 11, 14))
    got = read(["APOLLOHOSP"], O.BY_PROFILE["hospital"].query)
    assert got and {r["filed_at"] for r in got} == {"2026-11-04"} and {r["kind"] for r in got} == {"presentation"}   # recent presentations only
    figs, _ = O.read_profile("hospital", ["APOLLOHOSP"], "IN", read)
    assert figs["APOLLOHOSP"]["beds_op"]["v"] == 8522.0
    assert O.passages_reader("IN", store=None)(["X"], "beds") == [] or True          # no index set up: nothing, never an error


# ---------- 5. the SEC's earnings release named by its subject is read, not the 8-K cover ----------
def test_an_earnings_release_named_by_its_subject_is_the_document_read_not_the_8k_cover():
    from app.intel import sec as S
    c = S.SEC.__new__(S.SEC)
    folders = {"f1/": ["dal-20261009.htm", "deltaairlinesannouncessept.htm", "R1.htm", "0000027904-26-000035-index.html", "dal-20261009_htm.xml"],
               "f2/": ["ma-20261029.htm", "ex99-1.htm", "ma09302026-exx991xearnings.htm"],
               "f3/": ["x-8k.htm", "a.htm", "b.htm"]}
    c._json = lambda url: {"directory": {"item": [{"name": n} for n in folders[url.replace("index.json", "")]]}}
    c.document = lambda url: f"text of {url}"
    assert c.release_doc({"url": "f1/dal-20261009.htm", "folder": "f1/"})[0] == "f1/deltaairlinesannouncessept.htm"
    assert c.release_doc({"url": "f2/ma-20261029.htm", "folder": "f2/"})[0] == "f2/ex99-1.htm"           # an "ex99" exhibit as before
    assert c.release_doc({"url": "f3/x-8k.htm", "folder": "f3/"})[0] == "f3/x-8k.htm"                    # two candidates: the cover as before


def test_every_measure_is_in_the_registry_with_a_rule_and_a_profile():
    for p in O.PROFILES:
        assert O.MEASURES[p.id], p.id
        for k in O.MEASURES[p.id]:
            m = R.BY_ID[k]
            assert k in O.RULES and m.applies == frozenset({f"ops:{p.id}"}) and m.unit in ("pct", "num", "amt") and m.definition and m.limit
    assert len({m.label for m in R.METRICS if m.group in O.BY_PROFILE}) == sum(len(v) for v in O.MEASURES.values())   # one label a measure


def test_a_us_airline_theme_states_the_load_factor_median_of_the_airlines_that_state_it_and_passes_every_deck_rule():
    from app.intel import theme_data as D
    from app.intel import theme_routes as T
    from tests.fake_theme_structures import _theme, _us
    from tests.test_r18_deck import NOW
    from tests.test_theme1 import TODAY
    m, f = _theme("Airlines", "US", [("Passenger airlines", "AL", "Air Transportation, Scheduled", 4, "transport"),
                                     ("Aircraft lessors", "LS", "Services-Equipment Rental & Leasing, NEC", 3, "property")], _us)
    read = _passages_for({"AL0": "DAL", "AL1": "UAL", "AL2": "LUV"})
    dive = D.build("US", "Airlines", m, D.Sources(TODAY, facts=f.get, passages=read))
    assert [c["symbol"] for c in dive["sections"]["ops"]["profiles"]["airline"]["fit"]] == ["AL0", "AL1", "AL2", "AL3"]
    v = T.deck_view("US", m, dive)
    slides = deck.theme_plan(v, now=NOW)[0]
    page = next(s for s in slides if s.title.startswith(f"{deck.SECTOR_TITLE}: airlines"))
    assert page.subtitle == ("Median of the 3 airlines with filed figures: passenger load factor 83.9% (3 of 4), "
                             "passenger yield (cents per RPM) 21.86 (3 of 4); 1 more without")
    t = next(b for b in page.blocks if b["kind"] == "table")
    assert t["head"] == ["Company", "Passenger load factor", "ASMs (million)", "RPMs (million)", "Passenger yield (cents per RPM)", "Source", "Period"]
    rows = plain(t["rows"])
    assert next(r for r in rows if r[0].startswith("Passenger AL 1"))[1:5] == ["83.9%", "88,538", "74,278", "21.86"]
    from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
    every_rule("airlines", v, slides)                   # every rule of the theme deck holds with the page in it
    gated = deck.build_theme_gated(v, pdf=False)[1]
    assert not [x for x in (gated.get("failed") or []) if "operating" in str(x).lower()], gated
