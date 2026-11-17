"""r63e (R63): the deck items R62 left (the owner's review of the live R60 decks, LIVE10A-018 / -034, the Airlines deck_diff item) and the
flags of the live R62 decks, each fix generic (India and US), each test failing before the fix and passing after it."""
import copy
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app import deck
from app.intel import theme_base as B
from app.intel import theme_data as D


def _plain(rows):
    return [r for r in rows if not isinstance(r, dict)]


# ---------- LIVE10A-034: one layer's two halves by market value keep one name ----------
def _halves():
    big = [{"ticker": f"B{i}", "name": f"Big Cement {i} Ltd", "industry": "Cement & Cement Products", "cap": 90000 - i * 5000} for i in range(4)]
    small = [{"ticker": f"S{i}", "name": f"Small Cement {i} Ltd", "industry": "Cement & Cement Products", "cap": 3000 - i * 200} for i in range(4)]
    vc = [{"layer": "Regional integrated producers (larger)", "description": "", "companies": big, "scale": "larger",
           "sibling": "Regional integrated producers (smaller)"},
          {"layer": "Regional integrated producers (smaller)", "description": "", "companies": small, "scale": "smaller", "by_model": True,
           "sibling": "Regional integrated producers (larger)"}]
    words = {c["ticker"]: f"{c['name']} manufactures and sells cements and clinker from its integrated plants." for c in big + small}
    return vc, words


def test_1_a_half_by_market_value_is_renamed_with_its_other_half_never_alone():
    vc, words = _halves()
    out, rows = B.truthful_layers(copy.deepcopy(vc), {}, lambda s: words.get(s, ""), "Cement")
    names = [v["layer"] for v in out]
    bases = {B._HALF_RX.sub("", n) for n in names}
    assert len(bases) == 1, names                                   # live R60: "Cements integrated producers (larger)" beside "Regional ... (smaller)"
    assert names[0].endswith("(larger)") and names[1].endswith("(smaller)")
    assert out[0]["sibling"] == names[1] and out[1]["sibling"] == names[0]
    assert "Regional" not in names[0]                              # the word none of them say gives way, in both


def test_1b_a_word_put_before_its_noun_is_singular():
    assert B.in_place_name("Regional integrated producers", "cements", ["cement maker"]) == "Cement integrated producers"
    assert B.in_place_name("Commercial and business lenders", "bank", ["a bank"]) == "Commercial and business banks"       # plural where it was
    assert B.in_place_name("Commercial airframe integration", "aircraft", ["aircraft maker"]) == "Commercial aircraft"


def test_1c_halves_of_one_name_are_said_once_in_the_ranking_never_as_shown_not_ranked():
    rows = [{"layer": "Pan-India producers", "ebitda": 19.1, "ebitda_n": 5, "n": 5, "model": None, "official": False},
            {"layer": "Cement integrated producers (larger)", "ebitda": 13.0, "ebitda_n": 12, "n": 12, "scale": "larger", "model": None, "official": False},
            {"layer": "Cement integrated producers (smaller)", "ebitda": 3.2, "ebitda_n": 13, "n": 14, "scale": "smaller", "model": None, "official": False}]
    have = [rows[0], {"layer": "Cement integrated producers", "model": None}]
    assert D.unranked_rows(rows, have, "ebitda") == []


# ---------- LIVE10A-018: the theme's P/E history only over its own membership ----------
def test_2_a_kept_weekly_median_of_another_membership_is_no_point_of_the_theme_s_history():
    pts = [{"d": "2026-10-31", "pe": 9.0, "n": 41}, {"d": "2026-11-07", "pe": 9.2, "n": 41}, {"d": "2026-11-14", "pe": 14.1, "n": 21},
           {"d": "2026-11-17", "pe": 14.3, "n": 20}, {"d": "2026-11-17", "pe": 14.0}]
    keep, apart = D.same_population(pts, 20)
    assert [p["n"] for p in apart] == [41, 41] and len(keep) == 3
    from tests.test_r18_deck import bank_theme, deck_of
    region, m, f, _, _ = bank_theme()
    old = [{"d": "2026-10-24", "pe": 9.1, "n": 41}, {"d": "2026-10-31", "pe": 9.0, "n": 41}, {"d": "2026-11-07", "pe": 9.2, "n": 41}]
    v, slides = deck_of(region, m, f, history=lambda k, p: old + [p])
    val = v["sections"]["valuation"] if "sections" in v and "valuation" in v["sections"] else None
    hist = (val or {}).get("history")
    if hist is None:                                  # (the dive's own valuation, wherever the view keeps it)
        hist = next(x for x in _walk(v) if isinstance(x, dict) and "history" in x and "peers" in x)["history"]
    assert all(p.get("n") != 41 for p in hist)
    notes = [ln for s in slides if s.title == "Valuation" for b in s.blocks if b["kind"] == "cards" for it in b["items"] for ln in it["lines"]]
    assert any("3 earlier weekly medians of another membership (41 companies" in ln for ln in notes), notes


def _walk(x):
    yield x
    if isinstance(x, dict):
        for y in x.values():
            yield from _walk(y)
    elif isinstance(x, list):
        for y in x:
            yield from _walk(y)


# ---------- LIVE10A-018: one money unit in the operating figures' table ----------
def test_3_rupee_amounts_filed_in_billion_print_in_crore_beside_those_filed_in_crore():
    base = {"span": "quarter", "period": "2026-09", "filed": "2026-10-15", "url": "https://example.com/f"}
    rows = [{"group": "Large private banks"},
            {**base, "symbol": "A", "name": "A Bank", "metric": "Deposits", "unit": "₹ billion", "value": 33275, "prev": 32000, "year_ago": 29000,
             "change_prev": 4.0, "change_year": 14.7},
            {**base, "symbol": "B", "name": "B Bank", "metric": "Advances", "unit": "₹ crore", "value": 651491, "prev": 640000, "year_ago": 600000,
             "change_prev": 1.8, "change_year": 8.6},
            {**base, "symbol": "C", "name": "C Bank", "metric": "Customers", "unit": "units", "value": 5000, "prev": 4900}]
    slides = []
    deck._biz_slides(slides, "Operating figures", rows, "E", date(2026, 11, 17))
    t = next(b for s in slides for b in s.blocks if b["kind"] == "table")
    cells = " ".join(str(c) for r in _plain(t["rows"]) for c in r)
    assert "billion" not in cells and "₹33,27,500 crore" in cells and "₹6,51,491 crore" in cells
    assert "+14.7%" in cells and "5,000 units" in cells                  # a ratio and a count as they were
    # US: dollars in the scale most of the table files
    us = deck.one_money_unit([{"unit": "$ million", "value": 7.0}, {"unit": "USD billion", "value": 2.0}, {"unit": "$ million", "value": 5.0}])
    assert [(r["unit"], r["value"]) for r in us] == [("$ million", 7.0), ("$ million", 2000.0), ("$ million", 5.0)]
    assert deck._bizval(2000.0, "$ million") == "$2,000 million"
    assert deck.one_money_unit([{"unit": "$ million", "value": 7.0}]) == [{"unit": "$ million", "value": 7.0}]


# ---------- the Airlines deck_diff item: a whole company's line says its layer ----------
def test_4_a_line_cut_before_the_words_that_say_its_layer_keeps_the_item_that_does():
    adani = ("Adani Enterprises Ltd has business interests in various economic areas such as mining, integrated resources management, mining "
             "services, commercial mining, new energy ecosystem, data center, airports, roads, copper and petrochemicals.")
    cell = deck.layer_cell(adani, "Airport operators", 110)
    assert len(cell) <= 110 and cell.endswith("… airports") and cell.startswith("Adani Enterprises Ltd has business interests")
    assert deck.layer_cell("GMR Airports runs airports in Delhi and Hyderabad.", "Airport operators", 110) == \
        "GMR Airports runs airports in Delhi and Hyderabad."
    assert deck.layer_cell(adani, "Steel makers", 110) == deck.whole_clause(adani, 110)        # nothing of the layer in its words: as cut


# ---------- the owner's review (R60, still on R62): Huntington's revenue basis said where its stored page keeps no lines yet ----------
def test_5_a_us_bank_whose_page_keeps_no_revenue_lines_still_says_its_revenue_is_not_on_the_fte_basis():
    from tests.test_r18_deck import bank_theme
    region, m, f, _, _ = bank_theme()
    us = {**f["PVT0"], "region": "US", "unit": "$ million", "name": "Huntington Bancshares Inc"}
    r = D.company_row("US", "HBAN", us)
    assert r["revenue_basis"]["key"] == "not_stored" and r["revenue_basis"]["fte"] is False
    line = deck.basis_line([{**r, "symbol": "HBAN", "revenue": 8166.0}])
    assert "not on the fully taxable-equivalent (FTE) basis of a bank's own non-GAAP total revenue" in line
    assert "net interest income plus noninterest income" in line
    # an insurer's or lender's page with no lines: no word of FTE, a bank's adjustment (guard)
    ins = D.revenue_basis_of("US", {"region": "US"}, "insurer")
    assert "fte" not in ins and "FTE" not in deck.basis_line([{"symbol": "I", "revenue": 1.0, "revenue_basis": ins}])
