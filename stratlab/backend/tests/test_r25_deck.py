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


# gl50 (R50, updated on purpose): a chain whose layers have no way of earning read is never ranked, so the fixture's layers carry one
READ = {"id": "manufacturing", "family": "making"}


def block(name, n, med, k=None, official=False, revenue=100.0):
    return {"layer": name, "n": n, "revenue": revenue, "official": official, "stats": {"ebitda": {"median": med, "n": k if k is not None else n}}, "companies": [],
            "model": dict(READ)}


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
    slides_ = deck.theme_plan(v)[0]
    s = next(x for x in slides_ if x.title == "The value chain by layer")
    foot = deck.page_said(deck.with_held(slides_), "The value chain by layer")          # deck89 (changed on purpose): its footnote in full among the appendix's notes; deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    # changed on purpose (m2): one floor for the marks and the headline, said once; the floor a median is shown on beside it
    assert "among the layers ranked: those with at least 3 companies with the figure; any other layer is shown, not ranked." in foot
    assert "A median is shown for 3 companies or more." in foot
    assert "at least two" not in foot
    t = next(b for b in s.blocks if b["kind"] == "table")
    assert set(t["colors"].values()) == {deck.UP, deck.DOWN}
    v["chain"] = D.chain_table([block("Mining", 6, 30.0, 5), block("Cells", 4, 12.0, 2)])        # Cells under the base: nothing marked
    slides_ = deck.theme_plan(v)[0]
    s = next(x for x in slides_ if x.title == "The value chain by layer")
    assert not next(b for b in s.blocks if b["kind"] == "table")["colors"]
    assert "A layer is ranked only on a median of at least 3 companies with the figure" in deck.page_said(deck.with_held(slides_), "The value chain by layer")   # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)


@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_no_layer_is_called_highest_fastest_or_slowest_on_a_base_under_three_or_against_itself(name, v, slides):
    t = texts(slides)
    # changed on purpose (m2): the fastest and the slowest are one sentence that says which layers it ranks
    fast = re.search(r"revenue grew fastest in the latest year in (.+?) \(median", t)
    slow = re.search(r"\) and slowest in (.+?) \(median", t)
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
    for x in v["layers"]:              # gl50 (updated on purpose): the layers' way of earning read, as the chain's (READ)
        x["model"] = x.get("model") or dict(READ)
    v["chain"] = D.chain_table([block("Mining", 6, 30.0, 5), block("Cells", 4, 12.0, 3)])
    slides = deck.theme_plan(v)[0]
    s = next(x for x in slides if x.title == "The value chain by layer")
    t = next(b for b in s.blocks if b["kind"] == "table")
    row = next(r for r in t["rows"] if r[0] == "Mining")
    assert row[t["head"].index("Companies")] == "6" and row[t["head"].index("EBITDA margin")] == "30% (5 of 6)"
    chart = next(b for b in s.blocks if b["kind"] == "hbars" and str(b.get("title") or "").startswith("Median"))          # deck89: the medians' chart, beside the revenue's
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
                # lane m1 (updated on purpose): the cell is the companies in the layer's calculations, "of" those it lists where some are
                # left out ("14 of 17"); each figure's count is of the first
                own, _, listed = str(r[at]).partition(" of ")
                assert not listed or int(own) < int(listed), (s.title, r[0], r[at])
                for cell in r[at + 1:]:
                    for k, of in re.findall(r"\((\d+)(?: of (\d+))?\)", str(cell)):
                        if of:                                  # never "6" beside "15% (5)": "(5 of 6)", or the layer's own count alone
                            assert int(of) == int(own) and int(k) < int(of), (s.title, r[0], cell)
                        else:
                            assert int(k) == int(own), (s.title, r[0], cell)
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
    assert "a gap of 1.7 points, among the " in c["line"]  # r69e (LIVE13A-009, updated on purpose): the finding first, the layers it ranks after it


# ---------- 4. one page on how the figures shown are built ----------
@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_the_notes_page_explains_only_the_figures_the_deck_shows_with_period_source_and_limits(name, v, slides):
    # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed): the notes page is kept with the deck; the printed method page names each of its figures, one line each, in its order
    pages = [s for s in deck.held(slides) if s.title.startswith(deck.NOTES_TITLE)]
    assert 1 <= len(pages) <= 2
    rows = [r for s in pages for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])]
    said = [x for s in slides if s.title.startswith(deck.METHOD_TITLE) for b in s.blocks if b["kind"] == "table" and b["head"][:2] == ["Figure", "What it is"]
            for r in plain(b["rows"]) for x in r[::2] if x]          # (one figure a row beside the plain words, or two a row under them)
    assert said == [r[0] for r in rows], (name, said)
    assert all(len(r) == 4 and all(str(c).strip() for c in r) for r in rows)
    names = [r[0] for r in rows]
    assert len(names) == len(set(names))                                                      # one row a figure (a filed figure replaces the page's own)
    rest = [s for s in deck.with_held(slides) if not s.title.startswith((deck.NOTES_TITLE, deck.METHOD_TITLE))]          # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
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
    # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed): the notes page read among the records kept with the deck
    got = {name: {r[0]: r for s in deck.held(sl) if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])}
           for name, (_, sl) in families()}
    bank, ins, us = got["banks with filed figures"], got["insurers with filed figures"], got["US software with filed figures"]
    assert {"Gross NPA", "CET1 ratio", "Credit cost", "ROA", "ROE"} <= set(bank) and "EBITDA margin" not in bank and "Solvency ratio" not in bank
    assert bank["CET1 ratio"][1].startswith("Common equity tier 1 capital") and "exchange filing" in bank["CET1 ratio"][2]
    assert bank["Gross NPA"][1].startswith("Gross non-performing assets as a share of gross advances, as filed")       # the filed definition, once
    assert {"Solvency ratio", "Combined ratio", "Claims ratio"} <= set(ins) and "General insurers" in ins["Combined ratio"][3]
    assert {"SBC / revenue", "FCF margin", "RPO growth", "EBITDA margin"} <= set(us) and "SEC" in us["FCF margin"][2]
    assert "CET1 ratio" not in us and "Gross NPA" not in us and "Solvency ratio" not in us
    _, plain_slides = ALL[0][1]
    pk = {r[0] for s in deck.held(plain_slides) if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])}
    assert {"Revenue", "EBITDA margin", "Net margin"} <= pk and not pk & {"Gross NPA", "CET1 ratio", "SBC / revenue", "NII / assets"}


def test_the_contents_lists_the_notes_page_and_references_point_at_it():
    _, v, slides = EVERY[0]
    crow = plain(table_of(slides, "Contents")["rows"])
    # deck89 (changed on purpose, owner 25 Nov): the page is in the appendix, which the contents' last row names ("how each figure is built")
    # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed): the printed method page says what each figure is, a line each; a reference to how a figure is built points to it
    assert crow[-1][0] == "Appendix" and "what each figure is" in crow[-1][1]
    at = next(i for i, s in enumerate(slides, 1) if s.title.startswith(deck.METHOD_TITLE))
    assert "⟦" not in texts(slides) and f"p. {at}" in texts(slides)


# ---------- 5. the version ----------
def test_the_deck_version_is_27_so_kept_deck_files_are_made_again_once():
    assert deck.THEME_DECK_VERSION == 93                     # deck96 (changed on purpose, every live theme deck checked 26 Nov: dive text 54, deck 93); deck89 (changed on purpose, owner 25 Nov: the theme deck remade as research): deck 92; e85 (LIVE21A, the R84 decks): deck 91 (updated on purpose); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose); e80 (LIVE16A, the R78 decks): RULES 75, PLACE_CARRY[75] = 74, EARLIER_MAX 30, deck 86, dive text 46 (updated on purpose); e79 (the live R77 decks): RULES 74, PLACE_CARRY[74] = 73, EARLIER_MAX 29, deck 85, dive text 45 (updated on purpose); e78 (the live R76 decks): RULES 73, PLACE_CARRY[73] = 72, EARLIER_MAX 28, deck 84, dive text 44 (updated on purpose); e77 (the live R76 decks): RULES 72, PLACE_CARRY[72] = 71, EARLIER_MAX 27, deck 83, dive text 43 (updated on purpose); fix20 (the live R75 decks): RULES 71 kept, deck 82, dive text 42 (updated on purpose); r69e (R69): RULES 71, PLACE_CARRY[71] = 70, EARLIER_MAX 26, deck 81, dive text 41 (updated on purpose); r68e (R68): deck 80, dive text 40 (updated on purpose); r67e (R67): RULES 69, PLACE_CARRY[69] = 68, EARLIER_MAX 24, deck 79, dive text 39 (updated on purpose); r66e (R66): RULES 68, PLACE_CARRY[68] = 67, EARLIER_MAX 23, deck 78, dive text 38 (updated on purpose); r65e (R65): RULES 67, PLACE_CARRY[67] = 66, EARLIER_MAX 22, deck 77, dive text 37 (updated on purpose); r64e (R64): RULES 66, PLACE_CARRY[66] = 65, EARLIER_MAX 21, deck 76, dive text 36 (updated on purpose); r63e (R63): RULES 65, PLACE_CARRY[65] = 64, EARLIER_MAX 20, deck 75, dive text 35 (updated on purpose); r62 (R62): RULES 64, PLACE_CARRY[64] = 63, EARLIER_MAX 19, deck 74, dive text 34 (updated on purpose); r60 (R60): RULES 63, PLACE_CARRY[63] = 62, EARLIER_MAX 18, deck 73, dive text 33 (updated on purpose); r59 (R59): RULES 62, PLACE_CARRY[62] = 61, EARLIER_MAX 17, deck 72, dive text 32 (updated on purpose); r582 (R58.2): RULES 61, PLACE_CARRY[61] = 60, EARLIER_MAX 16, deck 71, dive text 31 (updated on purpose); r581 (R58.1): RULES 60, PLACE_CARRY[60] = 59, EARLIER_MAX 15, deck 70, dive text 30 (updated on purpose); r58 (R58): RULES 59, PLACE_CARRY[59] = 58, EARLIER_MAX 14, deck 69, dive text 29 (updated on purpose); r572 (R57.2): RULES 58, PLACE_CARRY[58] = 57, EARLIER_MAX 13, deck 68, dive text 28 (updated on purpose); p57 (R56 review): RULES 56, PLACE_CARRY[56] = 55, deck 67, dive text 27 (updated on purpose); t56 (R55 review): RULES 55, PLACE_CARRY[55] = 54, deck 66, dive text 26 (updated on purpose); v55 (R55 review): RULES 54, PLACE_CARRY[54] = 53, deck 65, dive text 25 (updated on purpose); c54 (R53 review): RULES 53, PLACE_CARRY[53] = 52, deck 64, dive text 24 (updated on purpose); d53 (R53): RULES 52, PLACE_CARRY[52] = 51, deck 63, dive text 23 (updated on purpose); gl52 (R52): RULES 51, PLACE_CARRY[51] = 50, deck 62, dive text 22 (updated on purpose); rv51 (R51): RULES 50, PLACE_CARRY[50] = 49, deck 61, dive text 21 (updated on purpose); gl50 (R50): RULES 49, PLACE_CARRY[49] = 48, deck 60, dive text 20 (updated on purpose); ex49 (R49): RULES 48, PLACE_CARRY[48] = 47, deck 59, dive text 19, precise exclusion reasons, the business-model ranking rule (updated on purpose); vr48 (R48): figures reconciled with the year's lines before any is held, the comparison basis (updated on purpose); cl48 (R48): deck 58, dive text 18, the coverage flag row and who earns another way said in layer lines (updated on purpose); vf46 (R46): dive text 17, each checked figure's source record, net above EBITDA reconciled line by line (updated on purpose); tx2 (R45/R46): RULES 45, PLACE_CARRY[45] = 44, deck 57 (dive text 17 from vf46), the taxonomy regression guard and the screening populations (updated on purpose); c1 (R44): RULES 44, PLACE_CARRY[44] = 43, deck 56, dive text 16 (55 and 15 are R44.1's), classification coverage from evidence (updated on purpose); R44 (lane v1): deck 54, dive text 14, verification states (updated on purpose); lane d1: RULES 43, PLACE_CARRY[43] = 42, deck 53, dive text 12 (the outside review of the live R41 decks, updated on purpose); lane t1: deck 52, dive text 11 (LIVE7A, updated on purpose); R41: deck 51, coloured cells measured bold (updated on purpose); lane s3-r40: RULES 42, deck 50, dive text 10 (updated on purpose); R35 bumped it (R25's test, updated: a new release makes kept files again)


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
