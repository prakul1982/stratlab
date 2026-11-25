"""deck89 (the owner, 25 Nov, of the live alcoholic-beverages deck: "it looks absolutely trash ... Just make a deck yourself and see ... Sort
everything out and get fixing everything"; R19: "just keep the important ones not everything"; 5 Nov: "make it better ... good looking").
The theme deck reads like research: the story first (findings as big numbers, the value chain, each layer, growth, valuation, price,
tailwinds and risks), a chart on most pages, plain words, short footnotes, no placeholder cells and no near-empty page; the checks, the
coverage, the marks and the long method notes in the appendix's "Method and coverage", so nothing true is lost."""
import functools
import io
import re

from app import deck
from tests.alcobev_fixture import ROWS, alco_view
from tests.test_deck_look import full_view
from tests.test_export import texts

CHARTS = ("hbars", "columns", "lines")


@functools.lru_cache(maxsize=None)
def built(name: str):
    v = alco_view() if name == "alco" else full_view()
    slides, footer = deck.theme_plan(v)
    return v, slides


def body(slides):
    return [s for s in slides if s.kind == "content" and not deck.is_appendix(s) and s.title != "Contents"]


def test_no_placeholder_cell_on_any_slide():
    for name in ("alco", "fixture"):
        _, slides = built(name)
        for s in slides:
            for b in s.blocks:
                for r in b.get("rows") or []:
                    for x in ([] if isinstance(r, dict) else r):
                        assert not deck.PLACEHOLDER_CELL.match(deck._cell_text(x).strip()), (name, s.title, x)
                for it in b.get("items") or []:
                    if isinstance(it, tuple):
                        assert not deck.PLACEHOLDER_CELL.match(str(it[1]).strip()), (name, s.title, it)


def test_no_engine_wording_on_the_story_pages():
    for name in ("alco", "fixture"):
        _, slides = built(name)
        for s in body(slides) + [slides[0]]:
            t = texts([s])
            assert not deck.AUDIT_WORDS.search(t), (name, s.title, deck.AUDIT_WORDS.findall(t))
        # the full counts live in the appendix's "Method and coverage"
        method = texts([s for s in slides if s.title.startswith(deck.METHOD_TITLE)])
        assert "description-verified" in method and "Counts:" in method


def test_most_story_pages_have_a_chart_and_none_is_mostly_empty():
    for name in ("alco", "fixture"):
        _, slides = built(name)
        pages = body(slides)
        words = [s for s in pages if s.title in ("Tailwinds and risks", "Dated company updates")]      # claims and dated news: words by nature
        charted = [s for s in pages if any(b["kind"] in CHARTS or b.get("big") for b in s.blocks)]      # the findings' big numbers count
        assert len(charted) >= 0.6 * (len(pages) - len(words)), (name, [s.title for s in pages if s not in charted])
        for s in pages:
            assert deck.body_fill(s) >= deck.FILL_MIN, (name, s.title, round(deck.body_fill(s), 2))


def test_the_story_runs_in_order_and_the_appendix_comes_last():
    _, slides = built("alco")
    titles = [s.title for s in slides]
    at = lambda t: next(i for i, x in enumerate(titles) if x.startswith(t))      # noqa: E731
    assert slides[0].kind == "cover" and titles[1] == "Contents" and titles[2] == "Key findings"
    assert at("Key findings") < at("The value chain by layer") < at("Layer 1 ·") < at(deck.SMALL_TITLE) < at("Growth and profitability") \
        < at("Valuation") < at("Price") < at("Tailwinds and risks") < at("Every company's figures") < at(deck.METHOD_TITLE)
    first_apx = next(i for i, s in enumerate(slides) if deck.is_appendix(s))
    assert all(deck.is_appendix(s) for s in slides[first_apx:])
    assert not any(t in titles for t in ("Data confidence", "Coverage", "How to read this deck", "Sub-themes", "Questions the figures raise"))
    # the contents name each part at its first page, the appendix last
    rows = next(b for b in slides[1].blocks if b["kind"] == "table")["rows"]
    assert [r[0] for r in rows][:2] == ["Findings", "The value chain"] and rows[-1][0] == "Appendix" and rows[-1][2] == str(first_apx + 1)


def test_key_findings_are_big_numbers_with_one_plain_sentence_and_no_page_reference():
    v, slides = built("alco")
    kf = next(s for s in slides if s.title == "Key findings")
    tiles = next(b for b in kf.blocks if b["kind"] == "stats")["items"]
    assert 3 <= len(tiles) <= 4
    for t in tiles:
        assert t[2].endswith(".") and not re.search(r"\bp\. \d", t[2]), t
    sec = v["sections"]
    got = {t[0]: t[1] for t in tiles}
    assert got["The theme's market value"] == deck.cap_inr(sec["size"]["total_cap"])
    assert got["Revenue growth"] == deck.whole_figures(deck._chg(sec["growth"]["aggregate"]["revenue_1y"]["value"]))


def test_footnotes_are_short_and_said_in_full_in_the_appendix():
    _, slides = built("alco")
    notes = [r for s in slides if s.title.startswith(deck.METHOD_TITLE) for b in s.blocks if b["kind"] == "table" and b["head"] == deck.NOTES_HEAD
             for r in b["rows"] if not isinstance(r, dict)]
    for s in body(slides):
        foot = deck._footnote(s)
        if foot is not None:
            assert deck._lines(foot["paras"], foot["box"][2]) <= deck.FOOT_LINES, s.title
    assert any(r[0].startswith("Layer 1 ·") for r in notes)          # a layer's marks and who is in its figures, in full


def test_nothing_true_is_lost():
    v, slides = built("alco")
    # every company with figures has its row in the appendix
    lead = {r[0] for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table" for r in b["rows"]
            if not isinstance(r, dict)}
    assert {r[1] for r in ROWS} <= {x.removesuffix(" (whole company)") for x in lead}
    # the checks, their counts and the coverage table are in the appendix, with the key to the marks
    method = [s for s in slides if s.title.startswith(deck.METHOD_TITLE)]
    heads = [b["head"] for s in method for b in s.blocks if b["kind"] == "table"]
    assert deck.CONF_HEAD in heads and deck.COVERAGE_HEAD in heads
    assert any(deck.MARKS_LINE in str(p) for s in method for b in s.blocks if b["kind"] == "text" for p in b.get("paras") or [])
    gate = slides[0].gate
    assert gate["passed"] == gate["of"], gate["dropped"]


def test_the_alcobev_deck_is_shorter_and_its_story_short():
    _, slides = built("alco")
    assert len(body(slides)) <= 18, [s.title for s in body(slides)]
    assert len(slides) <= 32


def test_rises_are_green_and_falls_red():
    _, slides = built("alco")
    tab = next(b for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table")
    g = tab["head"].index("Growth")
    for k, r in enumerate(tab["rows"]):
        if isinstance(r, dict) or r[g] in ("–", ""):
            continue
        assert tab["tints"][(k, g)] == (deck.UP if r[g].startswith("+") else deck.DOWN), r


def test_chart_text_is_never_under_11_pt():
    lw, labels, size = deck.hbar_labels(["Spirits brand owning and bottling (smaller)"] * 8, 4.0, 2.0)
    assert size >= deck.BODY_MIN
    assert deck.column_labels(["Grain distilling and extra neutral alcohol"] * 7, 10.0, 11)[1] >= deck.BODY_MIN


def test_pdf_and_powerpoint_keep_the_same_pages_and_the_powerpoint_reopens():
    from pptx import Presentation
    from pypdf import PdfReader
    v = alco_view()
    pdf = deck.build_theme(v, pdf=True)
    pp = deck.build_theme(v)
    prs = Presentation(io.BytesIO(pp))
    again = Presentation(io.BytesIO(pp))
    assert len(PdfReader(io.BytesIO(pdf)).pages) == len(prs.slides) == len(again.slides) == len(built("alco")[1])
