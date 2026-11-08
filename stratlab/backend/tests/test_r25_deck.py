"""Release 25 (the owner's outside review of the eight R23 decks): one minimum base for every comparison of layers, said in the footnote; counts
that read "N of M" wherever a figure is of fewer companies than its group; every headline and finding figure looked for again in the deck's
own tables before the deck is stored (dropped and logged when it isn't there); one page on how the figures shown are built; the deck version
bumped once. Generic: every synthetic theme, India and the US, and the sector-figure families (banks, insurers, US companies); synthetic data only."""
import logging
import re

import pytest

from app import deck
from app.intel import theme_data as D
from tests.test_deck_look import full_view
from tests.test_export import plain, table_of, texts
from tests.test_r18_deck import bank_theme, deck_of
from tests.test_r20_deck import ALL, us_map_theme
from tests import test_r23_metrics as R23

ADVICE = ("buy", "sell", "avoid", "attractive", "cheap", "expensive", "undervalued", "overvalued", "recommend", "healthy", "strong", "weak", "good", "bad")


def families():
    """The R24 sector-figure families as decks: banks, insurers and US companies, each with its filed figures."""
    region, m, f = bank_theme()[:3]
    yield "banks with filed figures", deck_of(region, m, f, metrics=R23.reader_of(R23.bank_pieces(f)))
    region, m, f, pieces = R23.insurer_theme()
    yield "insurers with filed figures", deck_of(region, m, f, metrics=R23.reader_of(pieces))
    region, m, f = us_map_theme()
    pieces = {}
    for i, sym in enumerate(sorted(f)):
        got = R23.S.us_figures(R23.companyfacts())
        got.pop("_end")
        pieces[sym] = {"family": "us", "end": "2026-01-31", "metrics": {k: {**x, "v": round(x["v"] + i, 1)} for k, x in got.items()}}
    yield "US software with filed figures", deck_of(region, m, f, metrics=R23.reader_of(pieces))


EVERY = [(n, v, s) for n, (v, s) in list(ALL) + list(families())]
IDS = [n for n, _, _ in EVERY]


def block(name, n, med, k=None, official=False, revenue=100.0):
    return {"layer": name, "n": n, "revenue": revenue, "official": official, "stats": {"ebitda": {"median": med, "n": k if k is not None else n}}, "companies": []}


def chain_of(v, *specs):
    """The fixture's chain from (layer, companies, median, companies with it), each layer's revenue its own (the same rows as its page)."""
    rev = {x["layer"]: x.get("revenue") for x in v["layers"]}
    return D.chain_table([block(nm, n, med, k, revenue=rev.get(nm)) for nm, n, med, k in specs])


# ---------- 1. one minimum base for every comparison of layers ----------
def test_a_layer_under_the_minimum_base_is_shown_but_never_ranked_and_fewer_than_two_over_it_says_nothing():
    assert D.COMPARE_MIN == D.MIN_BASE == deck.MIN_BASE == 3
    two = D.chain_table([block("A", 2, 40.0), block("B", 6, 12.0), block("C", 5, 20.0)])
    assert (two["highest"], two["lowest"]) == ("C", "B") and "A" not in two["compared"]       # a 2-company layer is never the highest
    alone = D.chain_table([block("A", 2, 40.0), block("B", 6, 12.0)])
    assert alone["highest"] is None and alone["line"] is None                                # one layer over the base: no comparison sentence
    assert [r["layer"] for r in alone["rows"]] == ["A", "B"]                                 # both still shown
    assert D.rank_pair([("x", 5.0, 3), ("y", 5.0, 4)], lambda t: t[1], lambda t: t[2]) is None             # a tie names no layer
    assert D.rank_pair([("x", 9.0, 3), ("y", 5.0, 2)], lambda t: t[1], lambda t: t[2]) is None             # one over the base
    assert deck.top_of([{"v": 4.0, "n": 3}, {"v": 4.0, "n": 5}], lambda r: r["v"], lambda r: r["n"]) is None


def test_the_value_chain_footnote_says_the_base_and_marks_only_layers_over_it(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    v = full_view()
    blocks = [block("Mining", 6, 30.0, 5), block("Cells", 4, 12.0, 3)]
    v["chain"] = D.chain_table(blocks)
    s = next(x for x in deck.theme_plan(v)[0] if x.title == "The value chain by layer")
    foot = " ".join(p for b in s.blocks if b["kind"] == "text" for p in b["paras"])
    assert "among the layers whose median is of at least 3 companies; a layer with fewer is shown but not ranked." in foot
    assert "at least two" not in foot
    t = next(b for b in s.blocks if b["kind"] == "table")
    assert set(t["colors"].values()) == {deck.UP, deck.DOWN}
    v["chain"] = D.chain_table([block("Mining", 6, 30.0, 5), block("Cells", 4, 12.0, 2)])        # Cells under the base: nothing marked
    s = next(x for x in deck.theme_plan(v)[0] if x.title == "The value chain by layer")
    assert not next(b for b in s.blocks if b["kind"] == "table")["colors"]
    assert "A layer is ranked only on a median of at least 3 companies" in " ".join(p for b in s.blocks if b["kind"] == "text" for p in b["paras"])


@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_no_layer_is_called_highest_fastest_or_slowest_on_a_base_under_three_or_against_itself(name, v, slides):
    t = texts(slides)
    fast = re.search(r"Fastest revenue growth in the latest year: (.+?), median", t)
    slow = re.search(r"Slowest: (.+?), median", t)
    if fast or slow:
        assert fast and slow and fast.group(1) != slow.group(1), (fast and fast.group(1), slow and slow.group(1))
    for m_ in re.finditer(r"(?:highest|fastest) median [^;]*? in ([^(;]+?) \(", t):
        layer = next((x for x in v["layers"] if x["layer"] == m_.group(1).strip()), None)
        assert layer is None or layer.get("n", 0) >= 3, m_.group(0)
    for m_ in re.finditer(r"\((?:[^()]*?), (\d+)(?: of \d+)? companies\)", t):
        assert int(m_.group(1)) >= 3 or "highest" not in t[max(0, m_.start() - 80):m_.start()], m_.group(0)


# ---------- 2. counts that read "N of M" ----------
def test_a_median_of_fewer_companies_than_its_group_reads_n_of_m_in_tables_charts_and_headlines(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    assert deck._medn({"n": 5, "median": 15.0}, 6) == "15.0% (5 of 6)" and deck._medn({"n": 6, "median": 15.0}, 6) == "15.0%"
    assert deck._medn({"n": 2, "median": 15.0}, 6) == "– (2 of 6)" and deck._medn({"n": 2, "median": 15.0}) == "– (2)"
    assert D.few(3, 5) == ", 3 of 5 companies" and D.few(3, 3) == ", 3 companies" and D.few(9, 9) == ""
    assert D.of_words(4, 6) == "4 of 6 companies" and D.of_words(1, None) == "1 company"
    v = full_view()
    v["chain"] = D.chain_table([block("Mining", 6, 30.0, 5), block("Cells", 4, 12.0, 3)])
    slides = deck.theme_plan(v)[0]
    s = next(x for x in slides if x.title == "The value chain by layer")
    t = next(b for b in s.blocks if b["kind"] == "table")
    row = next(r for r in t["rows"] if r[0] == "Mining")
    assert row[t["head"].index("Companies")] == "6" and row[t["head"].index("EBITDA margin")] == "30% (5 of 6)"
    chart = next(b for b in s.blocks if b["kind"] == "hbars")
    assert chart["cats"] == ["Mining (5 of 6)", "Cells (3 of 4)"]
    assert "highest in Mining (30%, 5 of 6 companies) and lowest in Cells (12%, 3 of 4 companies)" in s.subtitle
    assert deck.sector_lines({"sector": {"families": {"insurer": {"n": 6, "medians": {"combined_ratio": {"n": 3, "median": 106.0}}}}}}) == \
        ["Median of the 6 insurers with filed figures: combined ratio 106.0% (3 of 6)."]


@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_every_count_beside_a_layer_figure_is_n_of_its_companies(name, v, slides):
    for s in slides:
        for b in s.blocks:
            if b["kind"] != "table" or "Companies" not in b["head"] or b["head"][0] != "Layer":
                continue
            at = b["head"].index("Companies")
            for r in plain(b["rows"]):
                for cell in r[at + 1:]:
                    for k, of in re.findall(r"\((\d+)(?: of (\d+))?\)", str(cell)):
                        if of:                                  # never "6" beside "15% (5)": "(5 of 6)", or the layer's own count alone
                            assert int(of) == int(r[at]) and int(k) < int(of), (s.title, r[0], cell)
                        else:
                            assert int(k) == int(r[at]), (s.title, r[0], cell)
    for a, b in re.findall(r"(\d+) of (\d+)\b", texts(slides)):
        assert int(a) <= int(b), (a, b)


# ---------- 3. every headline and finding figure found again in the tables before the deck is stored ----------
@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_every_headline_and_finding_figure_is_one_the_tables_show_on_every_synthetic_theme_and_family(name, v, slides):
    assert slides[0].checked == [], slides[0].checked          # the check ran before the deck was made, and nothing had to be dropped
    assert deck.check_deck(slides) == []                       # and it finds nothing on the finished deck either


def test_a_figure_no_table_shows_is_dropped_and_logged_never_shipped(caplog, monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    v = full_view()
    v["chain"] = chain_of(v, ("Mining", 6, 30.0, 5), ("Cells", 4, 12.0, 3))
    assert deck.theme_plan(v)[0][0].checked == []                                          # the same rows: nothing dropped
    v["chain"]["line"] = re.sub(r"\(30(?:\.0)?%", "(37.7%", v["chain"]["line"])
    assert "(37.7%" in v["chain"]["line"]                    # a sentence that no longer matches its table
    with caplog.at_level(logging.WARNING, logger="stratlab.deck"):
        slides = deck.theme_plan(v)[0]
    dropped = slides[0].checked
    assert dropped and all("37.7%" in d["figures"] for d in dropped)
    assert {d["slide"] for d in dropped} >= {"The value chain by layer"}
    assert "37.7%" not in texts(slides) and "deck check: dropped" in caplog.text
    assert next(x for x in slides if x.title == "The value chain by layer").subtitle == ""


def test_the_check_reads_percentages_gaps_counts_multiples_and_money_against_the_table_figures():
    shown = D.shown_numbers(["19%", "12.0%", "+5.5%", "1.90x", "₹8,855 cr", "6", "(5 of 6)", 14.04])
    ok = D.claim_mismatches
    assert ok("highest in A (19%, 5 of 6 companies) and lowest in B (12.0%), a gap of 7 points.", shown) == []
    assert ok("median revenue +5.5% (6 companies), solvency 1.90x, revenue ₹8,855 cr", shown) == []
    assert ok("a margin of 14.0%", shown) == []                                             # a chart's plotted value counts
    assert ok("a gap of 8 points between 19% and 12.0%", shown) == ["8 points"]               # a gap is the difference of its two figures
    assert ok("median 21.5%", shown) == ["21.5%"] and ok("2.10x", shown) == ["2.10x"] and ok("₹9,000 cr", shown) == ["₹9,000 cr"]
    assert ok("(7 companies)", shown) == ["7"] and "7 of 6" in ok("7 of 6 companies", shown)
    s = deck.Slide("Layers side by side", "Medians by layer: highest median ROCE in A (44.0%); fastest median revenue growth in B (+5.5%)")
    s.add("table", (0, 0, 1, 1), head=["Layer", "ROCE", "Growth"], rows=[["A", "15.0%", "+5.5%"], ["B", "12.0%", "+1.0%"]], widths=[1, 1, 1])
    k = deck.Slide("Key findings")
    k.add("cards", (0, 0, 1, 1), items=[{"title": "Growth", "lines": ["Median ROCE 15.0%.", "Median ROCE 16.2%."]}])
    got = deck.check_deck([deck.Slide("cover"), s, k])
    assert [d["text"] for d in got] == ["Medians by layer: highest median ROCE in A (44.0%)", "Median ROCE 16.2%."]
    assert s.subtitle == "" and k.blocks[0]["items"][0]["lines"] == ["Median ROCE 15.0%."]       # a headline that loses its lead says nothing


def test_a_gap_said_beside_two_figures_is_the_difference_of_the_figures_as_printed(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    b = {"layer": "X", "stats": {"ebitda": {"median": 26.55, "n": 3}}, "left_out": 0, "stats_over": "own", "companies": []}
    assert D.margin_line(b, 24.94) is None                  # changed on purpose (R27): the whole map's median is in no table, so never quoted
    c = D.chain_table([block("A", 3, 26.55), block("B", 5, 24.94)])
    assert c["line"].endswith("a gap of 1.7 points.")


# ---------- 4. one page on how the figures shown are built ----------
@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_the_notes_page_explains_only_the_figures_the_deck_shows_with_period_source_and_limits(name, v, slides):
    pages = [s for s in slides if s.title.startswith(deck.NOTES_TITLE)]
    assert 1 <= len(pages) <= 2
    titles = [s.title for s in slides]
    assert titles.index(pages[0].title) == titles.index("How to read this deck") + 1
    rows = [r for s in pages for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])]
    assert all(len(r) == 4 and all(str(c).strip() for c in r) for r in rows)
    names = [r[0] for r in rows]
    assert len(names) == len(set(names))                                                      # one row a figure (a filed figure replaces the page's own)
    rest = [s for s in slides if not s.title.startswith(deck.NOTES_TITLE)]
    heads = {h for s in rest for b in s.blocks if b["kind"] == "table" for h in b["head"]}
    for nm in names:                                                                          # nothing the deck doesn't show
        assert nm in heads or any(nm in str(b.get("title") or "") or any(nm in str(r[0]) for r in plain(b.get("rows") or []) if r)
                                  for s in rest for b in s.blocks) or nm in texts(rest), (name, nm)
    words = " ".join(" ".join(r[1:]) for r in rows).lower()
    for w in ADVICE:
        assert not re.search(rf"\b{w}\b", words), (name, w)
    assert not any(s.title.endswith("how each is worked out") for s in slides)                # no second page of definitions
    assert "Lenders: ROE is net profit over shareholders' equity" not in texts(rest)           # no definition repeated page by page


def test_each_family_gets_its_own_figures_explained_and_no_other_familys():
    got = {name: {r[0]: r for s in sl if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])}
           for name, (_, sl) in families()}
    bank, ins, us = got["banks with filed figures"], got["insurers with filed figures"], got["US software with filed figures"]
    assert {"Gross NPA", "CET1 ratio", "Credit cost", "ROA", "ROE"} <= set(bank) and "EBITDA margin" not in bank and "Solvency ratio" not in bank
    assert bank["CET1 ratio"][1].startswith("Common equity tier 1 capital") and "exchange filing" in bank["CET1 ratio"][2]
    assert bank["Gross NPA"][1].startswith("Gross non-performing assets as a share of gross advances, as filed")       # the filed definition, once
    assert {"Solvency ratio", "Combined ratio", "Claims ratio"} <= set(ins) and "General insurers" in ins["Combined ratio"][3]
    assert {"SBC / revenue", "FCF margin", "RPO growth", "EBITDA margin"} <= set(us) and "SEC" in us["FCF margin"][2]
    assert "CET1 ratio" not in us and "Gross NPA" not in us and "Solvency ratio" not in us
    _, plain_slides = ALL[0][1]
    pk = {r[0] for s in plain_slides if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])}
    assert {"Revenue", "EBITDA margin", "Net margin"} <= pk and not pk & {"Gross NPA", "CET1 ratio", "SBC / revenue", "NII / assets"}


def test_the_contents_lists_the_notes_page_and_references_point_at_it():
    _, v, slides = EVERY[0]
    crow = plain(table_of(slides, "Contents")["rows"])
    at = next(int(r[2]) for r in crow if r[0] == deck.NOTES_TITLE)
    assert slides[at - 1].title.startswith(deck.NOTES_TITLE)
    assert "⟦" not in texts(slides) and f"p. {at}" in texts(slides)


# ---------- 5. the version ----------
def test_the_deck_version_is_27_so_kept_deck_files_are_made_again_once():
    assert deck.THEME_DECK_VERSION == 34                     # R33 bumped it (R25's test, updated: a new release makes kept files again)


# ---------- 6. the live R24 decks: a layer's columns follow its family; notes name only the families shown ----------
def chain_head(slides):
    return table_of(slides, "The value chain by layer")["head"]


def test_an_insurer_only_theme_shows_insurers_measures_never_a_banks_and_says_nothing_of_lenders():
    region, m, f, pieces = R23.insurer_theme()
    for sym in ("GEN0", "LIF1"):              # an insurer whose page carries a lender's ratio (the live Insurance deck: "NII / assets" for insurers)
        f[sym] = {**f[sym], "lender": {"nii_assets": 2.1, "gnpa": 0.4, "nnpa": 0.1}}
    v, slides = deck_of(region, m, f, metrics=R23.reader_of(pieces))
    head = chain_head(slides)
    assert "NII / assets" not in head and "Gross NPA" not in head and "CET1" not in head
    assert "Solvency" in head and "Combined ratio" in head and "ROE" in head
    for s in slides:
        if s.title.startswith("Layer "):
            lh = next(b for b in s.blocks if b["kind"] == "table")["head"]
            assert not {"NII / assets", "Gross NPA", "Net NPA", "Deposit growth"} & set(lh), (s.title, lh)
    t = texts(slides)
    for word in ("NII", "NPA", "Lenders:", "Banks and lenders have no", "CET1", "deposit"):
        assert word not in t, word
    assert slides[0].checked == []


def test_a_theme_with_no_bank_lender_or_insurer_never_mentions_them():
    from tests.test_r20_deck import it_theme
    v, slides = deck_of(*it_theme())
    t = texts(slides)
    for word in ("lender", "Lender", "bank", "Bank", "insurer", "NII", "NPA"):
        assert word not in t, (word, re.findall(rf".{{40}}{word}.{{40}}", t)[:2])
    head = chain_head(slides)
    assert not {"ROE", "NII / assets", "Gross NPA", "Solvency", "CET1"} & set(head)


def test_banks_and_us_software_get_their_own_value_chain_columns():
    got = {name: (v, sl) for name, (v, sl) in families()}
    bank = chain_head(got["banks with filed figures"][1])
    assert {"ROE", "NII / assets", "Gross NPA", "CET1"} <= set(bank) and "Solvency" not in bank and "SBC / revenue" not in bank
    us = chain_head(got["US software with filed figures"][1])
    assert {"SBC / revenue", "FCF margin"} <= set(us) and not {"NII / assets", "Gross NPA", "Solvency", "CET1"} & set(us)


@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_every_table_row_is_drawn_so_a_figure_a_sentence_checks_against_is_on_the_page(name, v, slides):
    for s in slides:
        for b in s.blocks:
            if b["kind"] == "table":
                x, y, w, h = b["box"]
                assert len(deck.table_layout(b, w, h)["rows"]) == len(b["rows"]), (name, s.title)     # no row left off a page
