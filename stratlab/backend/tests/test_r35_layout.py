"""Release 35, layout lane (the owner's review of the live R31.11 decks: "Component…", "Tyre…", "Mahindra & Mahindra…" down every table
and chart, headlines ending "…of the 99…", a cover tile with its note and no figure):
1. a label that doesn't fit is said shorter, whole (short_label), a one-line table gives a column the room its neighbours don't use and a
   name that still doesn't fit takes a second line: no "…" in a table cell or on a chart's axis;
2. the publication gate has a layout item: every slide is laid out as the files draw it (probe), what is cut is re-fitted the mildest way
   (a smaller headline, whole sentences, a clause or a card's last line left off), each change logged, and what can't be put right fails;
3. scripts/deck_check.py reads a folder of deck PDFs and reports what must never ship (tests/test_deck_check.py);
4. a value-chain table of more than four figure columns keeps the full width and its chart has a page of its own after it.
Generic: synthetic themes and made-up names only."""
import io
import logging

import pytest

from app import deck
from app.deck import BODY_MIN, CW, M, TOP, Slide
from tests.test_r27_quality import ALL27, IDS27

LAYERS = ["Component and machinery makers", "Tractors and farm machinery makers", "Commercial and electric bus makers", "Passenger vehicle makers",
          "Two-wheeler makers", "Tyre manufacturers", "Vehicle financiers"]
HEAD = ["Company", "Layer", "Market value", "Revenue", "Growth", "EBITDA", "Net", "ROCE", "P/E", "P/B"]
WIDTHS = [2.5, 1.9, 1.2, 1.15, 0.95, 0.95, 0.9, 0.85, 0.8, 0.8]


def appendix_rows(n=12):
    names = ["Northfield & Northfield Financial Services Limited", "Harbour Motor Company Ltd", "Stonebridge Forgings (India) Limited", "Kestrel Auto Ltd"]
    return [[names[i % 4], LAYERS[i % len(LAYERS)], "₹4.09 lakh cr", "₹1.99 lakh cr", "+24.8%", "19%", "9.4%", "15.1%", "21.1x", "4.2x"] for i in range(n)]


# ---------- 1. labels said shorter, never cut ----------
def test_a_label_that_does_not_fit_is_said_shorter_and_whole():
    w = deck._width
    assert deck.short_label("Short", 11, 3.0) == "Short"
    assert deck.short_label("Component and machinery makers", 11, w("Component & machinery", 11) + 0.01) == "Component & machinery"
    assert deck.short_label("Harbour Motor Company Limited", 11, w("Harbour Motor", 11) + 0.01) == "Harbour Motor"
    assert deck.short_label("Stonebridge Forgings (India) Ltd", 11, w("Stonebridge Forgings", 11) + 0.01) == "Stonebridge Forgings"
    two = deck.short_label("Northfield Life Insurance Company Limited", 11, 1.4, 2)            # two lines: the name itself before a shorter form
    assert two == "Northfield Life Insurance Company Limited" or not two.endswith("…")
    forms = deck.label_forms("Tractors and farm machinery makers")
    assert forms[0] == "Tractors and farm machinery makers" and forms[-1] == "Tractors & farm machinery"
    assert all(len(a) > len(b) for a, b in zip(forms, forms[1:]))                               # each form shorter than the one before


def test_a_figure_a_count_and_a_sentence_have_no_shorter_form():
    for text in ("+15.9% (5 of 7)", "₹4.09 lakh cr", "21.1x", "It makes forgings. It sells them to vehicle makers.", "https://example.com/a/b",
                 "Median, life insurers (5 of 7 companies)"):
        assert deck.label_forms(text) in ([text], [text, text.replace(" and ", " & ")]), text
    assert "(5 of 7)" in deck.short_label("+15.9% (5 of 7)", 11, 0.8, 2)                       # wrapped, never shortened


def test_a_label_no_form_of_which_fits_is_cut_at_a_whole_word_never_on_a_joining_word():
    w = deck._width
    assert deck.short_label("Semiconductor equipment makers", 11, w("Semiconductor…", 11) + 0.02) == "Semiconductor…"
    assert deck.short_label("Grid and power equipment makers", 11, w("Grid & power…", 11) - 0.05) == "Grid…"
    assert deck.short_label("Regional and rural banks and lenders of the north", 11, 1.2, 2) == "Regional & rural banks…"
    one = deck.short_label("Supercalifragilistic", 11, 0.6)
    assert one.endswith("…") and len(one) > 2                                                   # one word wider than its line: nothing whole to keep


def test_a_one_line_table_shows_every_long_name_whole():
    """The appendix's table: "Component…", "Passenger…", "Mahindra & Mahindra…" in the live decks."""
    b = {"head": HEAD, "rows": appendix_rows(), "widths": WIDTHS, "compact": True}
    lay = deck.table_layout(b, CW, 99)
    cells = [x for r in lay["rows"] for x in r]
    assert not any(str(x).endswith("…") for x in cells), [x for x in cells if str(x).endswith("…")]
    assert abs(sum(lay["widths"]) - CW) < 1e-6                                                   # the table is as wide as before
    assert lay["widths"][1] > CW * WIDTHS[1] / sum(WIDTHS)                                       # the layer's column took room the figures don't use
    layers = {r[1] for r in lay["rows"]}
    assert layers <= {f for x in LAYERS for f in deck.label_forms(x)}                            # each a layer's name or a shorter form of it
    for row, hh in zip(lay["rows"], lay["heights"][1:]):                                         # a row is as tall as its tallest cell: none is cut by its row
        lines = max(len(deck.wrap(str(x), BODY_MIN, cw - 0.2)) for x, cw in zip(row, lay["widths"]))
        assert lines <= 2 and hh + 0.02 >= lines * deck._lh(BODY_MIN)
    s = Slide("Every company's figures", "12 companies")
    s.add("table", (M, TOP, CW, sum(lay["heights"])), **b)
    assert deck.probe(s) == []


def test_a_one_line_table_pages_the_same_rows_it_draws():
    rows = appendix_rows(60)
    pages = deck.table_pages(HEAD, rows, WIDTHS, CW, 4.6, most=26, compact=True)
    assert sum(len(p) for p in pages) == 60
    for p in pages:
        assert len(deck.table_layout({"head": HEAD, "rows": p, "widths": WIDTHS, "compact": True}, CW, 4.6)["rows"]) == len(p)     # no row left off


def test_a_chart_s_names_are_whole_on_their_lines():
    names = ["Northfield Life Insurance Corporation Of India", "Harbour Prudential Life Insurance Company Limited", "Kestrel Life",
             "Stonebridge Life Insurance Company Limited", "Canal General Insurance Company Ltd", "Maxwell Financial Services Ltd"]
    lw, labels, size = deck.hbar_labels(names, 3.5, 3.4)
    assert lw <= 3.5 * 0.45 + 1e-6 and size in (BODY_MIN, 10)
    assert not any(ls[-1].endswith("…") for ls in labels), labels
    assert all(deck._width(ln, size) <= lw - 0.12 + 0.01 for ls in labels for ln in ls)
    cols, fs = deck.column_labels(LAYERS, CW - 0.75, 11)
    assert not any(ls[-1].endswith("…") for ls in cols) and all(len(ls) <= 2 for ls in cols)
    assert deck.chart_title("Margins by year", 4.0) == (12, 1)
    long = "Revenue against the same quarter a year before, the 14 largest moves"
    assert deck.chart_title(long, 4.0) == (BODY_MIN, 2)
    s = Slide("Growth", "x")
    s.add("hbars", (M, TOP, 4.0, 3.0), title=long, cats=["A", "B"], vals=[1.0, 2.0])
    assert deck.probe(s) == []                                                                   # two lines hold it: nothing cut


def test_two_names_never_shorten_to_the_same_label():
    given = ["Thermal power producers", "Thermal power operators", "Grid"]
    assert deck._distinct(given, ["Thermal power", "Thermal power", "Grid"]) == given
    assert deck._distinct(given, ["Thermal producers", "Thermal operators", "Grid"]) == ["Thermal producers", "Thermal operators", "Grid"]
    b = {"head": ["Layer", "Revenue"], "widths": [1.0, 1.0], "compact": True,
         "rows": [["Thermal power producers", "₹1,00,000 cr"], ["Thermal power operators", "₹2,00,000 cr"], ["Thermal power producers", "₹3,00,000 cr"]]}
    assert deck.short_label("Thermal power producers", BODY_MIN, 0.85, 2, tight=True) == "Thermal power"      # alone, the kind of business is left off
    lay = deck.table_layout(b, 2.2, 99)
    assert [r[0] for r in lay["rows"]] == ["Thermal power producers", "Thermal power operators", "Thermal power producers"]   # side by side, each in full
    assert all(hh + 0.02 >= len(deck.wrap(r[0], BODY_MIN, lay["widths"][0] - 0.2)) * deck._lh(BODY_MIN) for r, hh in zip(lay["rows"], lay["heights"][1:]))


def test_a_long_title_is_set_smaller_then_on_two_lines_never_cut():
    """Live: "Utilities (Indian power, gas and water-linked…" on a cover, "…grade and formulations) and…" in a part's list."""
    assert deck.title_size(Slide("Valuation", "x")) == 28 and deck.title_size(Slide("Automotive", "India", dark=True)) == 42
    cover = Slide("Utilities (Indian power, gas and water-linked utilities and their suppliers)", "India (NSE and BSE) · Theme deep dive", dark=True)
    assert 18 <= deck.title_size(cover) < 28 and deck.probe(cover) == []
    long = Slide("Layer 4 · Specialty chemicals (performance, electronic grade and formulations) and agrochemical intermediates", "12 companies")
    assert 16 <= deck.title_size(long) <= 21 and deck.probe(long) == []
    part = Slide("The value chain", "Eight layers.", dark=True, kind="section")
    part.contents = [("The value chain by layer", 5), (long.title, 9), ("Sector operating figures: US companies", 12)]
    assert deck.probe(part) == []
    for files in (True, False):                                                                  # and both files are made
        assert len(deck._render([cover, part, long], "foot", "t", pdf=files)) > 1000


def test_whole_sentences_are_kept_before_any_is_cut():
    long = "A very long second sentence that goes on about plants and products " * 4
    assert deck.sentences("It makes forgings. " + long, 120) == "It makes forgings."
    assert deck.sentences("Pumps for utilities. Exports grew. It is", 400) == "Pumps for utilities. Exports grew."
    over = "This first sentence runs a little over the limit that was set for it here."
    assert deck.sentences(over + " And a second one follows it.", 60) == over                    # a little over: said whole
    cut = deck.sentences("word and " * 80, 100)
    assert cut.endswith("…") and not cut[:-1].rstrip().endswith(" and")                         # no sentence to keep: cut, never on a joining word


# ---------- 2. the gate's layout item ----------
@pytest.mark.parametrize("name,v,slides", ALL27, ids=IDS27)
def test_nothing_is_cut_broken_or_left_off_on_any_slide_of_any_synthetic_deck(name, v, slides):
    g = slides[0].gate
    item = next(x for x in g["items"] if x["id"] == "layout")
    assert item["ok"] and item["dropped"] == 0, g["dropped"]
    assert g["refit_n"] == len(g["refit"]) and all(set(d) == {"rule", "slide", "text", "why"} and d["rule"] == "layout" for d in g["refit"])
    left = [(s.title, f) for s in slides for f in deck.probe(s)]
    assert left == [], left[:3]                                                                  # the pages as they print: nothing more to re-fit
    for s in slides:                                                                             # and no ellipsis a renderer would add
        for b in s.blocks:
            if b["kind"] == "table":
                lay = deck.table_layout(b, b["box"][2], b["box"][3])
                assert not any(deck._cell_text(x).endswith("…") and not deck._cell_text(y).endswith("…")
                               for r, r0 in zip(lay["rows"], b["rows"]) if not isinstance(r, dict) for x, y in zip(r, r0)), s.title


@pytest.mark.parametrize("name,v,slides", ALL27, ids=IDS27)
def test_every_tile_shows_its_figure(name, v, slides):
    """Every live cover: "Their market value" with a three-line note and no figure under its label."""
    seen = 0
    for s in slides:
        for b in s.blocks:
            if b["kind"] != "stats":
                continue
            x, y, w, h = b["box"]
            iw = (w - 0.18 * (len(b["items"]) - 1)) / len(b["items"]) - 0.36
            for it in b["items"]:
                lh = len(deck.wrap(deck.short_label(it[0], BODY_MIN, iw, 2), BODY_MIN, iw)) * deck._lh(BODY_MIN)
                note = it[2] if len(it) > 2 else None
                nh = min(0.6, len(deck.wrap(note, BODY_MIN, iw)) * deck._lh(BODY_MIN)) if note else 0
                vy = 0.13 + lh + 0.06
                nh = min(nh, max(0.0, h - vy - 0.14 - deck._lh(15)))
                assert h - vy - nh - (0.14 if note else 0.08) + 0.02 >= deck._lh(15), (s.title, it)     # a line for the figure, at 15 pt or more
                assert not note or nh + 0.02 >= len(deck.wrap(note, BODY_MIN, iw)) * deck._lh(BODY_MIN), (s.title, it)   # and its note whole
                seen += 1
    assert seen >= 5


def test_a_long_headline_is_set_smaller_then_loses_whole_clauses_and_each_change_is_logged(caplog):
    part = "the theme's median P/E is 29.9x against 34.4x for its comparable peers"
    s = Slide("Valuation", "; ".join([part] * 4))
    assert deck.headline_size(s.subtitle) < 14 and deck.probe(s) == []                           # three lines at a smaller size hold it
    refit, failed = deck.fit_slide(s)
    assert failed == [] and len(refit) == 1 and "pt to fit" in refit[0]["why"] and s.subtitle.count(part) == 4
    s = Slide("Valuation", "; ".join([part] * 9))
    assert any(f["kind"] == "cut" for f in deck.probe(s))                                        # too long at any size: the page would cut it
    with caplog.at_level(logging.INFO, logger="stratlab.deck"):
        lay = deck.layout_gate([s])
    assert lay["failed"] == [] and 1 <= s.subtitle.count(part) < 9 and not s.subtitle.endswith(("…", ";"))
    assert deck.probe(s) == []
    assert any("a headline's last clause left off to fit" in d["why"] for d in lay["refit"])
    assert "deck layout: re-fitted on 'Valuation'" in caplog.text


def test_a_cut_note_keeps_its_whole_sentences_and_a_cut_card_gives_up_its_last_part():
    s = Slide("Notes", "x")
    note = "The first sentence of the note. " + "Another sentence that says more about how the figures are built. " * 12
    s.add("text", (M, TOP, 6.0, 0.8), paras=[note.strip()], size=BODY_MIN, floor=BODY_MIN)
    lines = ["These firms design chips. " * 5, "How they earn is shown for only 4 of these 15 companies, mainly selling products of their own; "
             "the other 11 are listed under several other ways of earning that the map names for this layer of the chain."]
    s.add("cards", (M, 3.0, 4.2, 1.5), cols=1, fill=True, items=[{"title": "What this layer does", "lines": [x.strip() for x in lines]}])
    refit, failed = deck.fit_slide(s)
    assert failed == [] and len(refit) >= 2 and deck.probe(s) == []
    para = s.blocks[0]["paras"][0]
    assert para.startswith("The first sentence of the note.") and para.endswith(".") and len(para) < len(note)
    kept = s.blocks[1]["items"][0]["lines"]
    assert kept and all(not x.endswith("…") for x in kept) and "".join(kept) != "".join(x.strip() for x in lines)


def test_what_cannot_be_put_right_fails_the_item_and_is_listed():
    s = Slide("Layers", "x")
    s.add("columns", (M, TOP, 3.0, 3.0), cats=LAYERS + ["Supercalifragilistic expialidocious layer"], series=[("a", [1.0] * 8, deck.BLUE)])
    table = {"head": ["Company", "Total"], "rows": [[f"Row {i}", "1"] for i in range(30)], "widths": [3.0, 1.0]}
    s.add("table", (M + 4, TOP, 4.0, 2.0), **table)
    refit, failed = deck.fit_slide(s)
    why = {d["why"].split(":")[0] for d in failed}
    assert "cut with an ellipsis" in why and "rows left off the slide" in why
    cover = Slide("Theme", "India", dark=True)
    cover.gate = deck.publication_gate([cover, s], {"layers": [], "sections": {}})
    base = cover.gate
    assert next(x for x in base["items"] if x["id"] == "layout")["ok"] and base["of"] == len(deck.GATE_ITEMS) == 10
    g = deck.with_layout(base, {"refit": refit, "failed": failed})
    item = next(x for x in g["items"] if x["id"] == "layout")
    assert not item["ok"] and item["dropped"] == len(failed) and g["passed"] == base["passed"] - 1
    assert g["dropped_n"] == base["dropped_n"] + len(failed) and any(d["rule"] == "layout" for d in g["dropped"])


def test_a_text_that_arrives_cut_on_a_joining_word_loses_the_word():
    s = Slide("Smaller layers", "x")
    s.add("text", (M, TOP, CW, 1.0), paras=["It provides lifecycle services for aircraft, helicopters and…"], size=BODY_MIN, floor=BODY_MIN)
    refit, failed = deck.fit_slide(s)
    assert failed == [] and s.blocks[0]["paras"] == ["It provides lifecycle services for aircraft, helicopters…"] and refit[0]["why"] == "ended on a joining word"


# ---------- 4. a wide table's chart on a page of its own ----------
@pytest.mark.parametrize("name,v,slides", ALL27, ids=IDS27)
def test_a_wide_value_chain_table_keeps_the_full_width_and_its_chart_follows_on_its_own_page(name, v, slides):
    titles = [s.title for s in slides]
    pages = [s for s in slides if s.title.startswith("The value chain by layer")]
    own = [s for s in slides if s.title.startswith("Median ") and s.title.endswith(" by layer") and any(b["kind"] == "hbars" for b in s.blocks)]
    for s in pages:
        t = next(b for b in s.blocks if b["kind"] == "table")
        beside = [b for b in s.blocks if b["kind"] in ("hbars", "columns")]
        assert not (len(t["head"]) > 5 and beside), (name, t["head"])                            # no chart pressed beside a wide table
        assert len(t["head"]) <= 5 or abs(t["box"][2] - CW) < 1e-6
    if own:
        assert len(own) == 1 and pages and titles.index(own[0].title) == titles.index(pages[-1].title) + 1
        chart = next(b for b in own[0].blocks if b["kind"] == "hbars")
        assert len(chart["cats"]) >= 2 and len(chart["cats"]) == len(chart["vals"]) and abs(chart["box"][2] - CW) < 1e-6
        key = "roe" if "ROE" in own[0].title else "ebitda"
        rows = {r["layer"]: r for r in v["chain"]["rows"]}
        for cat in chart["cats"]:                                                                # each bar a layer on a median of MIN_BASE companies or more
            r = rows[cat.rsplit(" (", 1)[0]]
            assert (r.get(f"{key}_n") or 0) >= deck.MIN_BASE and r.get(key) is not None, cat
        assert any(b["kind"] == "text" and "every layer is in the table before this page" in b["paras"][0] for b in own[0].blocks)
    side = [s for s in slides if s.title.startswith("Layers side by side")]
    for s in side:
        t = next(b for b in s.blocks if b["kind"] == "table")
        assert not (len(t["head"]) > 5 and any(b["kind"] == "columns" for b in s.blocks)), name
    cols = [s for s in slides if s.title.startswith("Median ") and any(b["kind"] == "columns" for b in s.blocks)]
    assert len(own) + len(cols) <= 1                                                             # one page charting the layers' medians, not two
    for s in cols:
        assert titles.index(s.title) == titles.index(side[-1].title) + 1 and abs(next(b for b in s.blocks if b["kind"] == "columns")["box"][2] - CW) < 1e-6


def test_some_synthetic_deck_has_each_kind_of_chart_page_and_one_has_none():
    own = [n for n, _, sl in ALL27 if any(s.title.startswith("Median ") and any(b["kind"] == "hbars" for b in s.blocks) for s in sl)]
    cols = [n for n, _, sl in ALL27 if any(s.title.startswith("Median ") and any(b["kind"] == "columns" for b in s.blocks) for s in sl)]
    none = [n for n, _, sl in ALL27 if not any(s.title.startswith("Median ") for s in sl)]
    assert own and cols and none, (own, cols, none)


def test_fewer_than_two_layers_on_enough_companies_get_no_chart_page():
    name, v, _ = next(x for x in ALL27 if any(s.title == "Median EBITDA margin by layer" for s in x[2]))
    v2 = {**v, "chain": {**v["chain"], "rows": [{**r, "ebitda_n": 2 if i else r.get("ebitda_n")} for i, r in enumerate(v["chain"]["rows"])]}}
    slides = deck.theme_plan(v2)[0]
    assert not any(s.title == "Median EBITDA margin by layer" for s in slides)


# ---------- what the layout check found on the way ----------
def test_a_line_chart_with_a_series_of_no_points_is_drawn_without_it_in_both_files():
    """A layer's margins by year with no net margin on file: the PDF was never made ("Polyline must have 2 or more points")."""
    b = {"kind": "lines", "box": (M, TOP, 5.0, 3.0), "title": "Margins by year, the same 3 companies", "cats": ["Mar 2024", "Mar 2025", "Mar 2026"],
         "series": [("EBITDA margin", [8.2, 7.6, 7.0], deck.BLUE), ("Net margin", [None, None, None], deck.ORANGE)], "fmt": "pct", "labels": True}
    assert [x[0] for x in deck.drawn_lines(b)["series"]] == ["EBITDA margin"]
    s = Slide("Layer 3 · Fertilizers", "x")
    s.blocks.append(b)
    empty = Slide("Layer 4", "y")
    empty.blocks.append({**b, "series": [("Net margin", [None, 4.0, None], deck.ORANGE)]})
    cover = Slide("Theme", "India", dark=True)
    assert deck._render([cover, s, empty], "foot", "t", pdf=True)[:5] == b"%PDF-"
    from pptx import Presentation
    prs = Presentation(io.BytesIO(deck._render([cover, s, empty], "foot", "t", pdf=False)))
    assert len(prs.slides) == 3


def test_every_synthetic_deck_with_a_line_chart_is_made_as_a_pdf():
    done = 0
    for name, v, slides in ALL27:
        if any(b["kind"] == "lines" and len(deck.drawn_lines(b)["series"]) < len(b["series"]) for s in slides for b in s.blocks):
            assert deck._render(slides, "foot", name, pdf=True)[:5] == b"%PDF-", name
            done += 1
    assert done >= 1


def test_the_page_of_what_moved_the_margin_keeps_its_total_row_whatever_the_names_lengths():
    name, v, _ = next(x for x in ALL27 if any(s.title == "What moved the aggregate margin" for s in x[2]))
    md = v["sections"]["margin_drivers"]
    long = [{**c, "name": f"{c['name']} Precision Engineering and Components Manufacturing Company (India) Limited", "layer": LAYERS[2]} for c in md["companies"]]
    v2 = {**v, "sections": {**v["sections"], "margin_drivers": {**md, "companies": long * 3}}}
    s = next(x for x in deck.theme_plan(v2)[0] if x.title == "What moved the aggregate margin")
    t = next(b for b in s.blocks if b["kind"] == "table" and b["head"][0] == "Company")
    assert t["rows"][-1][0].startswith("All ") and len(deck.table_layout(t, t["box"][2], t["box"][3])["rows"]) == len(t["rows"])
    assert not any(f["kind"] == "rows" for f in deck.probe(s))


def test_the_deck_version_is_44_so_kept_files_are_made_again():
    assert deck.THEME_DECK_VERSION == 55          # R44.1: deck 55, dive text 15, a loss in a verification reason with the real minus (updated on purpose); R44 (lane v1): deck 54, dive text 14, verification states (updated on purpose); lane d1: RULES 43, PLACE_CARRY[43] = 42, deck 53, dive text 12 (the outside review of the live R41 decks, updated on purpose); lane t1: deck 52, dive text 11 (LIVE7A, updated on purpose); R41: deck 51, coloured cells measured bold (updated on purpose); lane s3-r40: RULES 42, deck 50, dive text 10 (updated on purpose)
