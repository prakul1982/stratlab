"""m57 (R57, the owner's review of the live R56 decks: themes below 9 for "Airlines and travel: limited airline/hotel operating measures; Cement:
limited capacity, utilisation and volume statistics; Hospitals and Medical devices: sector operating metrics; Renewable energy: generation,
equipment and EPC businesses need distinct financial profiles; Payments: small sample"):
1 each layer's sector operating measures, read only where its companies' own stored documents state them, printed as a layer figure only where
  at least half of the layer's companies state the measure, with the count and period; a layer whose companies state none says so in one line;
2 each layer summarised on the financial figures that fit how its companies earn (power producers on debt over EBITDA and interest cover,
  contractors on cash conversion, lenders on return on equity, processors on free cash flow), never one comparison across ways of earning;
3 deck_check fails a layer with a profile that prints neither its measures nor a "Not available" line.

The hotel, contractor and cement passages below are synthetic (no real company's figures); the PayPal and Delta passages are the real releases
of tests/fixtures/sector_ops/filed_passages.json (test_m53_sector_ops)."""
import shutil
import subprocess

import pytest

from app import deck
from app.intel import layer_profiles as LP
from app.intel import metric_registry as R
from app.intel import sector_ops as O
from app.intel import theme_data as D
from app.intel import theme_routes as T
from scripts import deck_check as DC
from tests.fake_theme_structures import _in, _theme, _us
from tests.test_export import plain
from tests.test_m53_sector_ops import _passages_for
from tests.test_r18_deck import NOW
from tests.test_theme1 import TODAY

FILED = "2026-11-05"


def _doc(body, kind="presentation", filed=FILED):
    return [{"body": body, "page": 7, "kind": kind, "filed_at": filed, "link": "https://example.org/p.pdf"}]


def _vals(got):
    return {k: (f["v"], f["period"]) for k, f in got.items()}


# ---------- 1. the new profiles' measures, each only as stated ----------
def test_hotel_rooms_occupancy_room_rate_and_revpar_as_stated_never_a_periods_tail_or_a_column_of_several_periods():
    got = O.document_figures(_doc("Portfolio highlights Q2 FY27 Operational rooms 5,210 Occupancy 71.5% ARR (₹) 8,450 RevPAR (₹) 6,042 "
                                  "Hotels signed in the quarter 6"), "IN", O.MEASURES["hotel"])
    assert _vals(got) == {"rooms": (5210.0, "Sep 2026"), "room_occ": (71.5, "Quarter to Sep 2026"), "arr": (8450.0, "Quarter to Sep 2026"),
                          "revpar_in": (6042.0, "Quarter to Sep 2026")}            # never "27 Operational rooms" out of "FY27"
    two = O.document_figures(_doc("Key operating metrics Q2 FY26 Q2 FY27 Occupancy 68% 71% ARR ₹ 7,900 ₹ 8,450. The company had 5,210 "
                                  "operational keys at 30 Sep 2026; 1,900 rooms in the pipeline."), "IN", O.MEASURES["hotel"])
    assert _vals(two) == {"rooms": (5210.0, "Sep 2026")}       # the heads' two periods: the document's own date, never the older column's
    assert O.document_figures(_doc("RevPAR $ 128 ADR $ 181 Occupancy 70.7% third quarter 2026", "earnings_release", "2026-10-30"), "US",
                              O.MEASURES["hotel"])["adr"]["v"] == 181.0


def test_contractors_orders_in_hand_won_and_book_to_bill_only_as_stated_and_the_us_backlog():
    got = O.document_figures(_doc("Order book of ₹ 12,480 crore as on 30 Sep 2026. Order inflow ₹ 2,310 crore in Q2 FY27. Book-to-bill 1.4x"),
                             "IN", O.MEASURES["epc"])
    assert _vals(got) == {"orders_held": (12480.0, "Sep 2026"), "orders_won": (2310.0, "Quarter to Sep 2026"),
                          "book_to_bill": (1.4, "Quarter to Sep 2026")}
    us = O.document_figures(_doc("Backlog was $41.2 billion at the end of the third quarter of 2026.", "earnings_release", "2026-10-28"), "US",
                            O.MEASURES["epc"])
    assert _vals(us) == {"orders_held": (41200.0, "Sep 2026")}
    assert O.document_figures(_doc("Order inflow of ₹ 9,000 crore expected in H2 FY27; targeted order book ₹ 30,000 crore by FY28"), "IN",
                              O.MEASURES["epc"]) == {}                       # a plan or a target, never a figure


def test_cement_ebitda_a_tonne_only_where_the_company_states_it():
    got = O.document_figures(_doc("EBITDA per tonne ₹ 1,050 in Q2 FY27 against ₹ 980 a year earlier. Capacity utilisation 68%"), "IN",
                             O.MEASURES["cement"])
    assert got["cem_ebitda_t"]["v"] == 1050.0 and got["cem_util"]["v"] == 68.0
    none = O.document_figures(_doc("Operating EBITDA ₹ 1,464 crore. Sales volume 16.5 million tonnes in Q2 FY27"), "IN", O.MEASURES["cement"])
    assert "cem_ebitda_t" not in none                           # never worked out from EBITDA over a volume


@pytest.mark.parametrize("row,family,layer,want", [
    ({"name": "Grand Stays Ltd", "official_industry": "Hotels & Resorts"}, "consumer_services", "Hotels and resorts", "hotel"),
    # a layer named by a way of earning ("Hotels, travel and consumer services") never makes an education app a hotel operator
    ({"name": "Lingo Learn Inc", "official_industry": "Services-Educational Services", "map_what": "digital language-learning app"},
     "consumer_services", "Hotels, travel and consumer services", None),
    ({"name": "Trip Book Ltd", "official_industry": "Tour, Travel Related Services", "map_what": "online travel booking platform for hotels"},
     "platform", "Online travel", None),
    ({"name": "Build Co Ltd", "official_industry": "Civil Construction"}, "construction", "", "epc"),
    ({"name": "Solar EPC Ltd", "official_industry": "Construction & Engineering", "map_what": "solar EPC contractor"}, "construction",
     "Solar and energy EPC contractors", "epc"),
    ({"name": "Grid Gear Ltd", "official_industry": "Heavy Electrical Equipment"}, "making", "", "epc"),
    ({"name": "Sun Modules Ltd", "official_industry": "Other Electrical Equipment", "map_what": "makes solar modules and cells"}, "making", "", None),
    ({"name": "Grey Cement Ltd", "official_industry": "Cement & Cement Products"}, "making", "", "cement"),
])
def test_the_new_profiles_fit_by_the_companys_own_words(row, family, layer, want):
    assert O.profile_of(row, family, layer) == want


# ---------- 2. debt over EBITDA, from one year's filed lines ----------
def test_debt_over_ebitda_from_the_same_years_filed_lines_and_none_without_a_positive_ebitda():
    assert D.debt_ebitda({"debt": 400, "sales": 1000, "opm": 20}) == 2.0
    assert D.debt_ebitda({"debt": 400, "sales": 1000, "opm": -5}) is None
    assert D.debt_ebitda({"sales": 1000, "opm": 20}) is None and D.debt_ebitda(None) is None
    assert R.BY_ID["debt_ebitda"].unit == "x" and "same year" in R.BY_ID["debt_ebitda"].definition


# ---------- 3. the page: each layer on its own measures ----------
HOTEL_DOC = ("Portfolio highlights Q2 FY27 Operational rooms 5,210 Occupancy 71.5% ARR (₹) 8,450 RevPAR (₹) 6,042",
             "Portfolio highlights Q2 FY27 Operational rooms 3,020 Occupancy 66% ARR (₹) 6,900 RevPAR (₹) 4,554",
             "Portfolio highlights Q2 FY27 Operational rooms 1,480 Occupancy 74% ARR (₹) 5,100 RevPAR (₹) 3,774")


def _synthetic_passages(mapping, kind="presentation", filed=FILED):
    out = [{"symbol": s, "doc_id": 500 + i, "n": 1, "page": 7, "kind": kind, "filed_at": filed, "body": b, "link": "https://example.org/p.pdf"}
           for i, (s, b) in enumerate(mapping.items())]
    return lambda syms, q: [r for r in out if r["symbol"] in syms]


def _slides(region, sector, layers, fact, passages, today=TODAY):
    m, f = _theme(sector, region, layers, fact)
    dive = D.build(region, sector, m, D.Sources(today, facts=f.get, passages=passages))
    v = T.deck_view(region, m, dive)
    return v, deck.theme_plan(v, now=NOW)[0]


def _page(slides):
    pages = [s for s in deck.with_held(slides) if s.title.startswith(deck.LAYER_PROFILE_TITLE)]  # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    assert pages, [s.title for s in slides]
    cols = {h: i for i, h in enumerate(deck.LAYER_PROFILE_HEAD)}
    rows = [[dict(zip(b["head"], r)).get(h, "–") for h in deck.LAYER_PROFILE_HEAD]        # a page's column of "–" only is left out (drop_empty)
            for s in pages for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])]
    note = " ".join(p for s in pages for b in s.blocks if b["kind"] == "text" for p in b["paras"])
    note += " ".join(x for s in pages for b in s.blocks if b["kind"] == "cards" for it in b["items"] for x in it["lines"])
    assert len(cols) == 5
    return pages, {r[0].replace(" (adjacent)", ""): r for r in rows}, note


def _travel():
    def fact(i, sym, name, ind):
        return _in(i, sym, name, ind, margins=(18, 19, 20, 21))
    return _slides("IN", "Airlines and travel", [("Airlines and air charter operators", "AL", "Airline", 4, "transport"),
                                                 ("Hotels and resorts", "HT", "Hotels & Resorts", 4, "consumer_services"),
                                                 ("Tour operators", "TO", "Tour, Travel Related Services", 3, "consumer_services")],
                   fact, _synthetic_passages({"HT0": HOTEL_DOC[0], "HT1": HOTEL_DOC[1], "HT2": HOTEL_DOC[2]}))


def test_a_layer_whose_companies_state_none_of_its_measures_says_so_and_a_layer_figure_needs_half_of_the_layer():
    v, slides = _travel()
    pages, rows, note = _page(slides)
    air = rows["Airlines and air charter operators"]
    assert air[1] == "Transport and logistics"
    assert air[3] == ("Not available: passenger load factor, ASKs (billion), RPKs (billion), yield (₹ per RPK) (stated in no document the app "
                      "holds from its 4 airlines)")
    hot = rows["Hotels and resorts"]
    # 3 of the 4 hotel operators state each: a share's median, an amount's range, with the count and the period
    assert hot[3] == ("Rooms in operation 1,480 to 5,210 (3 of 4); Room occupancy 71.5% (3 of 4); Average room rate (₹) 6,900 (3 of 4); "
                      "RevPAR (₹) 4,554 (3 of 4); latest Sep 2026")
    assert rows["Tour operators"][3] == "–"                     # no sector operating profile for how they earn
    assert "The 8 largest companies a profile fits: 3 state one of its measures." in note     # audit RC12 (at most the 10 largest)
    assert ("Operating profiles: Airlines and air charter operators, airlines: none of its 4 measures stated; Hotels and resorts, hotel "
            "operators: 4 of 4 stated, 4 by half or more of its companies.") in note
    assert "a layer figure only where at least half of the companies the profile fits state the measure, else the count" in note
    one = _slides("IN", "Airlines and travel", [("Hotels and resorts", "HT", "Hotels & Resorts", 4, "consumer_services")],
                  lambda i, s, n, ind: _in(i, s, n, ind), _synthetic_passages({"HT0": HOTEL_DOC[0]}))[1]
    assert ("Sector operating measures, as stated: Stated by under half, no layer figure: rooms in operation 1 of 4, room occupancy 1 of 4, "
            "average room rate (₹) 1 of 4, RevPAR (₹) 1 of 4; latest Sep 2026" in _page(one)[2])                                   # one layer: its lines as text, never a page for a table of one row
    notes = [r[0] for s in deck.with_held(slides) if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])]  # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    assert {"Room occupancy", "Debt / EBITDA"} <= set(notes) and "Passenger load factor" not in notes     # each figure it states is defined


def test_each_way_of_earning_is_summarised_on_its_own_figures_and_ranked_only_inside_its_layer():
    def fact(i, sym, name, ind):
        f = _in(i, sym, name, ind, margins=(30 + i, 31 + i, 32 + i, 33 + i * 2))
        return {**f, "interest_cover": 2.0 + i / 2} if sym.startswith("PG") else f
    v, slides = _slides("IN", "Renewable energy", [("Power generation", "PG", "Power Generation", 4, "generation"),
                                                   ("Solar EPC contractors", "EP", "Civil Construction", 3, "construction"),
                                                   ("Module makers", "MM", "Other Electrical Equipment", 3, "making")],
                        fact, _synthetic_passages({"EP0": "Order book of ₹ 12,480 crore as on 30 Sep 2026. Order inflow ₹ 2,310 crore in Q2 FY27",
                                                   "EP1": "Order book of ₹ 4,100 crore as on 30 Sep 2026"}))
    pages, rows, note = _page(slides)
    gen, epc, mod = rows["Power generation"], rows["Solar EPC contractors"], rows["Module makers"]
    assert gen[2].startswith("EBITDA margin ") and "Debt / EBITDA 0." in gen[2] and "Interest cover 2.8x (4 of 4)" in gen[2]
    assert "Cash from operations / net profit 1.2x (3 of 3)" in epc[2] and "not stored: working capital days" in epc[2]
    assert "Debt / EBITDA" not in epc[2] and "Interest cover" not in mod[2] and "ROCE" in mod[2] and "Revenue growth" in mod[2]
    assert epc[3].startswith("Orders in hand ₹4,100 cr to ₹12,480 cr (2 of 3); stated by under half, no layer figure: orders won in the "
                             "quarter 1 of 3; latest Sep 2026; not stated: book-to-bill (times)")
    assert gen[3] == "Not available: installed capacity (MW), generation (GWh), CUF / PLF (stated in no document the app holds from its 4 power producers)"
    assert mod[3] == "–"
    assert gen[4].startswith("EBITDA margin: top Power PG 3 Ltd") and "(of 4)" in gen[4]        # inside the layer, never across layers
    assert "3 ways of earning, never ranked against each other" in pages[0].subtitle


def test_us_lenders_and_processors_are_read_on_different_figures_and_the_processors_payment_volume_as_stated():
    v, slides = _slides("US", "Payments and fintech", [("Card issuers and lenders", "CI", "Personal Credit Institutions", 3, "lending"),
                                                       ("Payment processors", "PP", "Services-Business Services, NEC", 3, "payments")],
                        _us, _passages_for({"PP0": "PYPL"}), today=__import__("datetime").date(2026, 11, 10))
    pages, rows, _ = _page(slides)
    lend, proc = rows["Card issuers and lenders"], rows["Payment processors"]
    assert lend[2].startswith("ROE ") and "P/B" in lend[2] and "EBITDA margin" not in lend[2]
    assert "not stored: net interest margin and credit cost (not in the figures the app stores for US lenders)" in lend[2]
    assert proc[2].startswith("EBITDA margin ") and "FCF margin" in proc[2]
    assert proc[3].startswith("Stated by under half, no layer figure: payment volume 1 of 3")
    assert lend[3] == "–"


def test_rows_group_layers_of_one_way_of_earning_together_and_leave_out_a_group_of_no_one_way():
    v = {"region": "IN", "layers": [{"layer": "A", "model": {"family": "making"}, "companies": []},
                                    {"layer": "B", "model": {"family": "construction"}, "companies": []},
                                    {"layer": "C", "model": {"family": "making"}, "companies": []},
                                    {"layer": "Other", "model": {"family": ""}, "companies": []}]}
    assert [r["layer"] for r in LP.rows(v)] == ["A", "C", "B"]


# ---------- 4. deck_check ----------
LAYER_PAGE = ("AIRLINES AND TRAVEL · THE VALUE CHAIN\n\n\nLayer 1 · Airlines and air charter operators\n4 companies\n\n"
              "In common: they earn mainly from fees for moving and storing goods or people.\n")


def test_deck_check_fails_a_profiled_layer_with_no_measures_and_no_not_available_line():
    bad = DC.check_pages([LAYER_PAGE])
    assert bad["counts"]["profile unsaid"] == 1 and "Airlines and air charter operators: a layer of airlines" in bad["findings"][0]["text"]
    said = (f"X · THE THEME IN NUMBERS\n\n\n{deck.LAYER_PROFILE_TITLE}\n1 layer\n Not available: passenger load factor (stated in no document\n"
            "Operating profiles: Airlines and air charter operators, airlines: none of its 4 measures stated. Its last column: the.\n")
    assert DC.check_pages([LAYER_PAGE, said])["counts"]["profile unsaid"] == 0
    paged = "X · THE THEME IN NUMBERS\n\n\nSector operating figures: airlines\n1 airline whose own documents state these measures\n"
    assert DC.check_pages([LAYER_PAGE, paged])["counts"]["profile unsaid"] == 0          # a profile's own page of company figures
    unsaid = said.replace(" Not available: passenger load factor (stated in no document\n", "\n")
    assert DC.check_pages([LAYER_PAGE, unsaid])["counts"]["profile unsaid"] == 1          # "none stated" with no "Not available" line printed


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="pdftotext (poppler) is not installed")
def test_the_rendered_deck_passes_deck_check_and_every_deck_rule(tmp_path):
    from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
    v, slides = _travel()
    every_rule("travel", v, slides)
    gated = deck.build_theme_gated(v, pdf=True)
    assert not gated[1].get("failed"), gated[1]
    p = tmp_path / "travel.pdf"
    p.write_bytes(gated[0])
    text = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(p), "-"], capture_output=True, check=True).stdout.decode()
    got = DC.check_text(text)
    assert got["counts"]["profile unsaid"] == 0, got["findings"]
    # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed): each layer on its own measures is a record kept with the deck, which says it
    from tests.test_export import texts
    assert "Operating profiles: Airlines and air charter operators, airlines: none of its 4 measures stated" in " ".join(texts(deck.with_held(slides)).split())


# ---------- 5. the largest companies' passages first, a cap a company (audit RC12: the 10 largest carry the measures) ----------
def _alphabet_store(store, put):
    """Three companies' presentations: AAA (small, many matching pages), MMM, ZZZ (the largest, last in the alphabet)."""
    put(store, 1, symbol="AAA", kind="presentation", filed="2026-11-04", pages=[(i, f"Operational rooms {1000 + i} Occupancy 70%") for i in range(1, 8)])
    put(store, 2, symbol="MMM", kind="presentation", filed="2026-11-04", pages=[(1, "Operational rooms 2,000 Occupancy 66%")])
    put(store, 3, symbol="ZZZ", kind="presentation", filed="2026-11-04", pages=[(1, "Operational rooms 9,000 Occupancy 75%")])


def _check_order(store):
    got = store.passages("occupancy", "IN", ["ZZZ", "MMM", "AAA"], ["presentation"], "2026-05-01", 4, 2)
    assert [r["symbol"] for r in got] == ["ZZZ", "MMM", "AAA", "AAA"]        # the order given (largest first), at most 2 of one company
    old = store.passages("occupancy", "IN", ["ZZZ", "MMM", "AAA"], ["presentation"], "2026-05-01", 4)
    assert [r["symbol"] for r in old] == ["ZZZ", "MMM", "AAA", "AAA"]        # no cap given: the limit alone, still the order given


def test_the_memory_store_reads_the_given_order_first_and_at_most_a_cap_a_company():
    from tests.fake_doc_store import MemoryDocStore
    from tests.test_doc_search import put
    s = MemoryDocStore()
    _alphabet_store(s, put)
    _check_order(s)


def test_a_profile_reads_its_largest_companies_first_so_a_long_alphabet_never_cuts_them_off():
    asked = []
    rows = [{"symbol": s, "name": s, "cap": cap, "official_industry": "Hotels & Resorts"} for s, cap in (("AAA", 10), ("ZZZ", 900), ("MMM", 50))]
    O.section(rows, "IN", {r["symbol"]: "Hotels" for r in rows}, {r["symbol"]: "consumer_services" for r in rows},
              lambda syms, q: asked.append(list(syms)) or [])
    assert asked == [["ZZZ", "MMM", "AAA"]]
    assert O.PER_COMPANY * 20 <= O.PASSAGES                 # a cap a company that lets at least 20 companies be read in one search


try:
    from tests.test_doc_search import needs_pg, pg, put as _put  # noqa: F401  (the Postgres fixture)
except Exception:            # pragma: no cover
    needs_pg = pytest.mark.skip(reason="no Postgres fixture")


@needs_pg
def test_postgres_passages_read_the_given_order_first_and_at_most_a_cap_a_company(pg):
    _alphabet_store(pg, _put)
    _check_order(pg)


# ---------- 6. handed over by y57 and dat57 (R57 audit REN-2, HOS-9, PAY-17; the data check's P/E and P/B words) ----------
def test_an_ebitda_margin_filed_in_whole_points_is_worked_out_to_one_decimal_from_the_years_filed_lines():
    from tests.test_theme1 import facts
    f = facts("ONE", "One Ltd", [1000, 1100, 1210, 1330], [20, 21, 22, 23], [100, 110, 121, 133])
    f["years"][-1]["op"] = 302.0                                         # 22.7% of 1,330, filed as 23
    row = D.company_row("IN", "ONE", f)
    assert row["ebitda"] == 22.7 and row["ebitda_dp"] == 1
    f["years"][-1]["op"] = 400.0                                         # 30.1%: doesn't agree with the filed 23, so the filed margin stays
    assert D.company_row("IN", "ONE", f)["ebitda"] == 23.0
    assert D.margin_of({"op": 302.0, "sales": 1330}) == 22.7 and D.margin_of({"sales": 1330}) is None


def test_a_median_over_layers_that_earn_differently_says_it_is_pooled():
    v, slides = _travel()                                               # transport and consumer services
    growth = next(s for s in slides if s.title == "Growth and profitability")
    # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed): each layer on its own measures is kept with the deck, on the theme's page
    assert f"pooled across layers that earn in different ways (each layer on its own figures: {deck.THEME_PAGE})" in growth.subtitle
    one = _slides("IN", "Hotels", [("Hotels and resorts", "HT", "Hotels & Resorts", 4, "consumer_services"),
                                   ("Resorts", "RS", "Hotels & Resorts", 3, "consumer_services")], lambda i, s, n, ind: _in(i, s, n, ind),
                  _synthetic_passages({}))[1]
    assert "pooled" not in next(s for s in one if s.title == "Growth and profitability").subtitle


def test_r_and_d_not_filed_is_a_dash_for_any_us_company_and_the_pe_and_pb_words_say_what_is_computed():
    assert R.applies("rd_share", "US", {"us", "payments"})              # a payments company that files no R&D line: "–", never "n/a"
    assert R.BY_ID["pe"].definition.startswith("Price over earnings per share of the last four quarters")
    assert "latest year's end (US)" in R.BY_ID["pb"].source


def test_power_layers_say_how_the_source_classifies_ebitda_and_regulated_networks_lead_on_return_on_equity():
    v, slides = _slides("IN", "Utilities", [("Power generators", "PG", "Power Generation", 4, "generation"),
                                            ("Transmission networks", "TN", "Power - Transmission", 3, "regulated_utility")],
                        lambda i, s, n, ind: _in(i, s, n, ind), _synthetic_passages({}))
    pages, rows, note = _page(slides)
    assert ("Power generators, Transmission networks: " + LP.EBITDA_SOURCE_NOTE + ".") in note
    assert rows["Transmission networks"][2].startswith("ROE ") and not rows["Transmission networks"][4].startswith("EBITDA")     # never ranked on EBITDA
    assert LP.FIN["regulated_utility"][0] == "roe"
