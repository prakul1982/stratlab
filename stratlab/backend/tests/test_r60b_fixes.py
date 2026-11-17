"""R60 (lane r60b): the figures and wording of the owner's outside review of the live R59 decks. Each test fails on 92711df (R59) and
passes after, unless marked a guard.

1. P0 a bank's (and an insurer's) revenue basis: the lines it is made of, named, with the standard, so the deck says it by company and
   names the adjustment a bank's own non-GAAP total adds. Huntington's FY2025 10-K: net interest income $5,991 m + noninterest income
   $2,175 m = $8,166 m (the deck's $8.17 bn, US GAAP); its "Total revenue, FTE (non-GAAP)" $8,231 m adds an FTE adjustment of $65 m.
   Fifth Third: $5,982 m + $3,035 m = $9,017 m, its "Total revenue (FTE)" $9,037 m (+$20 m); M&T $6,948 m + $2,742 m = $9,690 m, its
   taxable-equivalent adjustment $44 m (fixtures: tests/fixtures/sec_r58, the SEC's company facts, cut).
2. P1 an operating-model check apart from the capital-intensity proxy: branded consumer products are never ranked against commodity
   processing and refining, whatever their capital figures.
3. P1 core and adjacent populations said the same way in every count line (never "14 members" for 12 core banks and 2 adjacent financiers).
4. P2 no sparse continuation page (one note and the footer); deck_check's new "sparse page" row.
5. deck_check's "outlier range" on the live Software deck p.30: a company spending ahead of its revenue (−1080.1% EBITDA margin on $7 m),
   counted apart from every median and range, was charted beside the layer's others.
"""
import gzip
import importlib.util
import json
import os
import pathlib
import re

import pytest

from app import deck, stock_pages
from app.intel import sec
from app.intel import theme_data as D
from tests.test_export import table_of
from tests.test_r18_deck import bank_theme, deck_of

SEC_FIX = pathlib.Path(__file__).parent / "fixtures" / "sec_r58"
PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
spec = importlib.util.spec_from_file_location("deck_check_r60b", PATH)
DC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DC)


def sec_facts(name):
    return json.loads(gzip.open(SEC_FIX / f"{name}.json.gz").read())


def notes_rows(slides):
    return [r for s in slides if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in b["rows"]]


# ---------- 1. P0: a bank's revenue basis ----------
@pytest.mark.parametrize("name,nii,nonint,annual_report_total", [("hban", 5991, 2175, 8231), ("fitb", 5982, 3035, 9037), ("mtb", 6948, 2742, None)])
def test_1_a_bank_page_keeps_the_lines_its_revenue_is_made_of(name, nii, nonint, annual_report_total):
    p = sec.build(sec_facts(name), {"sic": "6022"})
    b = p["revenue_basis"]
    assert b["key"] == "bank_nii" and b["standard"] == "US GAAP" and b["fte"] is False and b["year"] == "Dec 2025" and b["filer"] == "bank"
    assert b["lines"] == [{"line": "net interest income", "value": float(nii)}, {"line": "noninterest income", "value": float(nonint)}]
    assert p["pl"]["rows"]["Sales"][-1] == nii + nonint          # the deck's revenue is the sum of the named lines
    if annual_report_total:                 # the annual report's non-GAAP FTE total is higher by its FTE adjustment, never the deck's figure
        assert annual_report_total > nii + nonint


def test_1_an_ifrs_bank_and_an_insurer_say_their_own_lines():
    b = sec.build(sec_facts("bsbr"))["revenue_basis"]
    assert b["standard"] == "IFRS" and "fte" not in b and b["words"] == "net interest income plus net fee and commission income, as filed"

    def yr(v):
        return {"start": "2025-01-01", "end": "2025-12-31", "val": v, "form": "10-K", "filed": "2026-02-20", "fy": 2025, "fp": "FY"}
    f = {"facts": {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [yr(300e6)]}},
                               "PremiumsEarnedNet": {"units": {"USD": [yr(8e9)]}}, "NetInvestmentIncome": {"units": {"USD": [yr(1e9)]}},
                               "NetIncomeLoss": {"units": {"USD": [yr(0.9e9)]}}}}}
    b = sec.build(f, {"sic": "6331"})["revenue_basis"]
    assert b["key"] == "insurer_parts" and [x["line"] for x in b["lines"]] == ["premiums earned", "net investment income"]


def test_1_the_stored_page_keeps_it_and_a_financial_page_built_before_is_built_again_once():
    page = stock_pages.facts("US", "HBAN", {"name": "Huntington"}, {"years": [{"year": "Dec 2025", "sales": 8166.0, "profit": 2200.0}], "bank": True},
                             {}, None, None, [], "Listed in the US", checks={"revenue_basis": {"key": "bank_nii", "words": "x"}})
    assert page["revenue_basis"]["key"] == "bank_nii" and not stock_pages.basis_missing(page)
    old = {k: v for k, v in page.items() if k != "revenue_basis"}
    assert stock_pages.basis_missing(old)                                      # before r60b: no basis, built again
    assert not stock_pages.basis_missing({**old, "revenue_basis": {}})         # a build that read no revenue: the key alone ends it (guard)
    assert not stock_pages.basis_missing({**old, "bank": False})               # not a financial filer (guard)
    assert not stock_pages.basis_missing({**old, "region": "IN"})              # India's pages say their basis by family (guard)


def test_1_a_theme_row_carries_each_bank_s_basis_india_and_us():
    region, m, f, _, _ = bank_theme()
    r = D.company_row("IN", "PVT0", f["PVT0"])
    assert r["revenue_basis"]["key"] == "in_bank" and r["revenue_basis"]["words"].startswith("interest earned")
    us = {**f["PVT0"], "region": "US", "unit": "$ million"}
    assert D.company_row("US", "PVT0", us)["revenue_basis"]["key"] == "not_stored"
    got = D.company_row("US", "PVT0", {**us, "revenue_basis": sec.build(sec_facts("hban"), {"sic": "6022"})["revenue_basis"]})["revenue_basis"]
    assert got["key"] == "bank_nii" and got["fte"] is False and got["lines"][0]["value"] == 5991.0
    assert "revenue_basis" not in D.company_row("IN", "X", {**f["PVT0"], "bank": False, "industry": ["Metals"]})     # not a financial (guard)


def test_1_the_deck_says_each_bank_s_revenue_basis_and_the_fte_adjustment_its_own_total_adds():
    hban = sec.build(sec_facts("hban"), {"sic": "6022"})["revenue_basis"]
    region, m, f, _, _ = bank_theme()
    for i, x in enumerate(f.values()):
        x.update(region="US", unit="$ million")
        if i == 0:
            x["revenue_basis"] = {**hban, "key": "bank_net_total", "words": "total revenue net of interest expense, as filed",
                                  "lines": [{"line": "total revenue net of interest expense", "value": 12000.0}]}
        elif i > 1:
            x["revenue_basis"] = hban
    v, slides = deck_of("US", m, f)
    row = next(r for r in notes_rows(slides) if r[0] == "Revenue")
    assert "net interest income plus noninterest income, as filed (US GAAP): " in row[1] and "every one not named below" in row[1]
    assert "total revenue net of interest expense, as filed (US GAAP): Private Lender 0 Ltd" in row[1]
    assert "not stored on its page yet" in row[1] and "Private Lender 1 Ltd" in row[1]
    assert "fully taxable-equivalent (FTE)" in row[3] and "FTE adjustment" in row[3]
    # India: a bank's revenue is its interest earned, other income apart; no word of FTE
    region, m, f, _, _ = bank_theme()
    v, slides = deck_of(region, m, f)
    row = next(r for r in notes_rows(slides) if r[0] == "Revenue")
    assert "A bank's, lender's or insurer's, by the lines it is made of: interest earned" in row[1] and "FTE" not in row[3]


def test_1_guard_no_bank_net_margin_above_100_percent():
    for name in ("hban", "fitb", "mtb"):
        rows = sec.build(sec_facts(name), {"sic": "6022"})["pl"]["rows"]
        assert all(n / s <= 1.0 for s, n in zip(rows["Sales"], rows["Net Profit"]) if s and n)


# ---------- 2. P1: an operating-model check apart from the capital-intensity proxy ----------
MAKERS = {"id": "manufacturing", "family": "making", "known": 6, "of": 6}


def _block(name, ebitda, intensity=0.5, n=6):
    op = getattr(D, "operating_model", lambda _: "")(name)
    return {"layer": name, "n": n, "listed": n, "revenue": 100.0, "official": False, "basis": None, "companies": [], "intensity": intensity,
            "stats": {"ebitda": {"median": ebitda, "n": n}, "net": {"median": ebitda / 2, "n": n}, "roce": None},
            "model": {**MAKERS, **({"operating": op} if op else {})}}


def test_2_operating_models_are_read_from_the_layer_s_own_name():
    assert D.operating_model("Agri-processing and edible oil refining") == "processing"
    assert D.operating_model("Branded home, personal care and FMCG") == "branded"
    assert D.operating_model("Branded packaged foods manufacturing (larger)") == "branded"
    assert D.operating_model("Farming and plantations") == "farming" and D.operating_model("Distribution and trading") == "trading"
    for name in ("Store retailers of home, auto and beauty goods", "City gas distribution", "Merchant acquiring and processing",
                 "Cable and satellite distribution", "Power transmission and distribution networks", "Pan-India integrated producers"):
        assert D.operating_model(name) == "", name


def test_2_the_capital_figure_alone_never_ranks_branded_makers_against_commodity_processing():
    # the live R59 FMCG figures: capital proxies 0.68, 0.55 and 0.32 (2.1 times: the numerical rule passes)
    ch = D.chain_table([_block("Branded home, personal care and FMCG", 19.0, 0.68), _block("Branded packaged foods manufacturing", 9.9, 0.55),
                        _block("Agri-processing and edible oil refining", 3.65, 0.32)])
    assert ch["highest"] == "Branded home, personal care and FMCG" and ch["lowest"] == "Branded packaged foods manufacturing"
    agri = next(x for x in ch["unranked"] if x["layer"].startswith("Agri"))
    assert agri["why"].startswith("another operating model than the ranked layers' branded consumer products: commodity processing and refining")
    rule = next(r for r in ch["basis"]["rules"] if r["rule"] == "operating model")
    assert rule["passed"] and "branded consumer products" in rule["text"]
    cap = next(r for r in ch["basis"]["rules"] if r["rule"] == "capital intensity")
    assert cap["passed"]                                       # the numerical test alone would have ranked them
    # one of each: described, never ranked, the reason said
    two = D.chain_table([_block("Branded home, personal care and FMCG", 19.0, 0.68), _block("Agri-processing and edible oil refining", 3.65, 0.32)])
    assert two["highest"] is None and "Their operating models differ" in two["line"] and "not ranked" in two["line"]
    assert two["basis"]["why"] == "their operating models differ by the layers' own names"
    assert not next(r for r in two["basis"]["rules"] if r["rule"] == "operating model")["passed"]
    # every other ranking takes the same rule (comparable_rows)
    rows = [{"v": 19.0, "m": _block("Branded home, personal care and FMCG", 0)["model"]},
            {"v": 3.65, "m": _block("Agri-processing and edible oil refining", 0)["model"]}]
    assert D.comparable_rows(rows, lambda r: r["v"], lambda r: 9, model=lambda r: r["m"]) == []


def test_2_guard_layers_whose_names_state_no_operating_model_rank_as_before():
    ch = D.chain_table([_block("Regional integrated producers", 22.0), _block("Ready-mix concrete and cement", 12.0)])
    assert ch["highest"] == "Regional integrated producers" and ch["lowest"] == "Ready-mix concrete and cement"
    two = D.chain_table([_block("Branded home, personal care and FMCG", 19.0), _block("Branded packaged foods manufacturing", 9.9)])
    assert two["highest"] == "Branded home, personal care and FMCG"                 # one operating model: ranked as before


# ---------- 3. P1: core and adjacent populations said the same way ----------
def test_3_no_count_line_calls_core_members_and_adjacent_participants_all_members():
    c = {"considered": 14, "members": 14, "rejected": 0, "adjacent_members": 2}
    assert deck.members_words(c) == "12 core members + 2 adjacent participants"
    assert "14 members" not in deck.counts_words({**c, "rejected": 1, "considered": 15, "with_figures": 12, "counted": 12, "each": [], "adjacent": 2,
                                                  "confirmed": None})
    v = {"layers": [{"layer": "Large banks", "companies": [{"symbol": f"B{i}"} for i in range(12)]},
                    {"layer": "Infrastructure financiers", "adjacent": {"kind": "non-bank financiers"}, "companies": [{"symbol": "F1"}, {"symbol": "F2"}]}]}
    assert deck.adjacent_members(v) == 2
    assert deck.members_words({"members": 208, "adjacent_members": 0}) == "208 members"          # no adjacent participant: as before (guard)


# ---------- 4. P2: no sparse continuation page ----------
FOOT = "StratLab · Medical devices · Theme deep dive · 16 Nov 2026                Not investment advice · 27 / 69"
LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r60b"
_DECKS: dict = {}


def live_deck(key):
    """The theme's placement input as production served it (FMCG, 16 Nov 2026, rules 60) placed by the engine and built into a deck, with
    synthetic figures for the companies the input has figures for (as lanes' offline replays build them)."""
    if key in _DECKS:
        return _DECKS[key]
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))
    import release_gate as G
    from app.intel import theme_base as B
    from tests.test_r48_reconcile import co
    d = G.load(LIVE / f"{key}.json")
    with G.offline():
        out, _ = G.engine(d)
    f, n, figs = {}, 0, d.get("figures") or {}
    for li, v in enumerate(out["value_chain"]):
        base = 6.0 + 3.3 * (li % 7)
        for i, c in enumerate(v["companies"]):
            n += 1
            if c["ticker"] in f or c["ticker"] not in figs:
                continue
            g = figs[c["ticker"]] or {}
            sales = g["revenue"] if isinstance(g.get("revenue"), (int, float)) and g["revenue"] > 0 else 1000.0 + 37 * n
            opm = g["ebitda"] if isinstance(g.get("ebitda"), (int, float)) and abs(g["ebitda"]) <= 100 else base + (i % 3) - 1 + (n % 37) / 10
            net = g["net"] if isinstance(g.get("net"), (int, float)) and abs(g["net"]) <= 100 else base - 4 + (n % 41) / 10
            f[c["ticker"]] = co(c["ticker"], c.get("name") or c["ticker"], sales, opm, sales * net / 100, roce=8.0 + (n % 53) * 0.3)
    m = B.for_figures({**out, "sector": d["theme"], "sub_themes": out.get("sub_themes") or []})[0]
    _DECKS[key] = (d, out, *deck_of(d["region"], m, f, theme=d["theme"], about=d["evidence"].get))
    return _DECKS[key]


def test_4_deck_check_flags_a_continuation_page_of_one_note():
    page = ("MEDICAL DEVICES · THE VALUE CHAIN\n\nLayer 7 · Hospital and care facility operators (notes)\nWho is in the layer's calculations, and "
            "what its table's marks mean\n\n\nMembership of its 8 companies: 7 description-verified, 1 industry-supported, 0 not checked.\n\n\n" + FOOT)
    assert DC.check_pages([page])["counts"]["sparse page"] == 1
    full = page.replace("0 not checked.", "0 not checked.\n" + "\n".join(f"note line {i} of a longer page of notes" for i in range(3)))
    assert DC.check_pages([full])["counts"]["sparse page"] == 0                # a page of notes (guard)
    other = page.replace(" (notes)", "")
    assert DC.check_pages([other])["counts"]["sparse page"] == 0               # not a continuation page (guard)


def test_4_a_layer_s_short_notes_go_with_its_next_companies_never_on_a_page_of_their_own():
    # before: the offline FMCG deck's "Branded home, personal care and FMCG (notes)" held one membership note (two lines) and the footer
    d, out, v, slides = live_deck("fmcg")
    for s in slides:
        if s.title.endswith("(notes)"):
            paras = [p for b in s.blocks if b["kind"] == "text" for p in b["paras"]]
            assert sum(len(deck.wrap(p, deck.BODY_MIN, deck.CW)) for p in paras) > getattr(deck, "SPARSE_LINES", 2), s.title
    s = next(s for s in slides if s.title.startswith("Layer") and "Branded home, personal care and FMCG" in s.title and s.title.endswith("(continued)"))
    assert "who is in the layer's calculations" in s.subtitle
    assert [b["kind"] for b in s.blocks] == ["table", "text", "text"]          # its next companies, where the rest is, then the notes
    assert any("Membership of its" in p for p in s.blocks[2]["paras"])


# ---------- 2 (on the input production served): FMCG's branded makers never ranked against agri-processing ----------
def test_2_fmcg_never_ranks_branded_makers_against_agri_processing():
    d, out, v, slides = live_deck("fmcg")
    agri = "Agri-processing and edible oil refining"
    for b in v.get("comparisons") or []:
        names = [g["layer"] for g in b["groups"]]
        if agri in names and b.get("made", True):
            assert not any(n.startswith("Branded") for n in names), (b["metric"], names)
    blk = next(x for x in v["layers"] if x["layer"] == agri)
    assert (blk.get("model") or {}).get("operating") == "processing"


# ---------- 5. deck_check's "outlier range": a company counted apart is never charted beside the layer's others ----------
def test_5_a_company_spending_ahead_of_its_revenue_is_not_charted_beside_the_layer():
    from tests.test_r18_deck import us_list_theme
    region, m, f = us_list_theme()
    for x in f.values():
        x["years"] = x["years"][-1:]                  # one year each: the layer's page charts its companies, not its margins by year
    y = f["SEC1"]["years"][-1]
    y.update(opm=-1080.1, profit=-y["sales"] * 30.5)  # the live Software deck's lines: −1080.1% EBITDA, −3049.5% net, on $7 m of revenue
    f["SEC1"]["opm"] = -1080.1
    v, slides = deck_of(region, m, f)
    row = next(c for x in v["layers"] for c in x["companies"] if c["symbol"] == "SEC1")
    assert row["developer"] and row["ebitda"] == -1080.1                     # kept on its row, counted apart from every median
    for s in slides:              # before: the Software layer's chart of EBITDA margin by company, 22% ... −1080.1%
        for b in s.blocks:
            if b["kind"] == "hbars" and "margin" in str(b.get("title") or "").lower():
                assert "Secure 1 Inc" not in b["cats"] and -1080.1 not in b["vals"], s.title


# ---------- LIVE9A-012 (the live review of R59): absurd margins never printed as margins ----------
def test_live9a_012_a_margin_beyond_100_percent_of_revenue_is_printed_nm_and_out_of_every_median():
    assert deck.co_cell({"ebitda": -32423.1}, "ebitda", str) == "n.m."           # Atomera: $70,000 of revenue
    assert deck.co_cell({"net": 151.3, "one_off": True}, "net", str) == "n.m.†"  # a net profit above revenue the lines don't give
    assert deck.co_cell({"net": 151.3, "gain": True}, "net", str) == "151.3%‡"   # one the filed lines cover: a gain, marked, out of the median
    assert deck.co_cell({"net": 99.0}, "net", str) == "99.0%"                    # within ±100%: as before (guard)
    assert D.in_median({"net": 151.3}, "net") is None and D.in_median({"ebitda": -1811.0}, "ebitda") is None
    assert D.in_median({"net": 24.0}, "net") == 24.0                              # guard
    from tests.test_r18_deck import us_list_theme
    region, m, f = us_list_theme()
    y = f["SEC1"]["years"][-1]
    y.update(opm=-32423.1, profit=-y["sales"] * 50)
    f["SEC1"]["opm"] = -32423.1
    v, slides = deck_of(region, m, f)
    rows = [r for s in slides if not s.title.startswith(deck.SOURCES_TITLE)          # (the figure's source record states it, with its lines)
            for b in s.blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict) and "Secure 1 Inc" in str(r[0])]
    assert rows and all("32423" not in " ".join(map(str, r)) for r in rows) and any("n.m." in r for r in rows)
    notes = " ".join(p for s in slides for b in s.blocks if b["kind"] == "text" for p in b.get("paras") or [])
    assert deck.NM_NOTE in notes


# ---------- LIVE9A-005 (the live review of R59): one set of dates, the theme's own market's ----------
def test_live9a_005_a_us_deck_is_dated_in_new_york_and_its_cover_says_the_close_its_multiples_are_on():
    from datetime import datetime, timezone
    from tests.test_r18_deck import us_list_theme
    region, m, f = us_list_theme()
    v, _ = deck_of(region, m, f)
    late = datetime(2026, 11, 17, 2, 0, tzinfo=timezone.utc)        # 16 Nov 21:00 in New York, 17 Nov 07:30 in India
    _, footer = deck.theme_plan(v, now=late)
    assert footer.endswith("16 Nov 2026")                            # before: India's date, 17 Nov
    assert deck.theme_plan({**v, "region": "IN"}, now=late)[1].endswith("17 Nov 2026")      # an Indian theme: India's date (guard)
    sec_ = v.get("sections") or {}
    v2 = {**v, "as_of": "2026-11-16", "sections": {**sec_, "valuation": {**(sec_.get("valuation") or {}), "price_at": "2026-11-13"}}}
    assert deck.price_dates_note(v2) == "P/E at the 13 Nov 2026 close"
    cover = deck.theme_plan(v2, now=late)[0][0]
    tile = next(it for b in cover.blocks if b["kind"] == "stats" for it in b["items"] if it[0] == "Prices as of")
    assert tile[1] == "16 Nov 2026" and tile[2] == "P/E at the 13 Nov 2026 close"
    assert deck.price_dates_note({**v2, "as_of": "2026-11-13"}) == ""       # one day: nothing more said (guard)
