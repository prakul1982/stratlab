"""scripts/deck_check.py (R35, layout lane): the regression check that reads a folder of deck PDFs as a reader would and reports what must
never ship. Synthetic text only; a real PDF is read through pdftotext where it is installed."""
import importlib.util
import os
import re
import shutil

from app import deck
from app.deck import CW, M, TOP, Slide

PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
spec = importlib.util.spec_from_file_location("deck_check", PATH)
DC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DC)

CLEAN = ("THEME · VALUATION\nValuation\nThe theme's median P/E is 29.9x, 13.1% below its peers' median of 34.4x; P/E of 96 of the 99 companies\n\n"
         " Company                 Layer                    Market value     Revenue\n"
         " Harbour Motor           Component & machinery    ₹4.09 lakh cr    ₹1.99 lakh cr\n"
         " None of the 12 companies has a filed order book. Semiconductor equipment is in the second layer.\n"
         " P/E      Market value over net profit      None for a loss-maker\n\f"
         "THEME · APPENDIX\nEvery company's figures (1 of 2)\n12 confirmed companies with figures, one row each\n\f")
BAD = ("THEME · VALUATION\nValuation\nother companies counted for 1), 13.1% below their peers' median of 34.4x; P/E of 96 of the 99…\n\n"
       " Company                 Layer                    Market value\n"
       " Harbour Motor…          Semiconductor equipm…    ₹4.09 lakh cr\n"
       " Kestrel Auto            Component and…           ₹1.01 lakh cr\n"
       " Semiconductor equipment makers are in the second layer.\n\f"
       "THEME · THE VALUE CHAIN\nThe value chain by layer\nNo listed company is shown for x. 14 of 12 companies have figures\n\n"
       " Median EBITDA margin {ebitda}: None, nan, undefined\n\f")


def kinds(result):
    return {k: n for k, n in result["counts"].items() if n}


def test_a_clean_deck_s_text_has_nothing_to_report():
    r = DC.check_text(CLEAN)
    assert r["pages"] == 2 and kinds(r) == {} and not DC.failed(r) and not DC.failed(r, strict=True)


def test_each_thing_that_must_never_ship_is_found_with_its_page():
    r = DC.check_text(BAD)
    assert r["pages"] == 2 and DC.failed(r)
    by = {}
    for f in r["findings"]:
        by.setdefault(f["kind"], []).append(f)
    assert [f["page"] for f in by["headline"]] == [1] and by["headline"][0]["text"].endswith("of the 99…")
    assert [f["text"].split(" in: ")[0] for f in by["mid-word"]] == ["'equipm…'"]                 # "Motor…" is a whole word: not counted here
    assert [f["text"].split(" in: ")[0] for f in by["joining word"]] == ["'and…'"]
    assert sorted(f["text"].split(" in: ")[0] for f in by["placeholder"]) == ["'None'", "'nan'", "'shown for x'", "'undefined'", "'{ebitda}'"]
    assert [f["text"].split(" in: ")[0] for f in by["count"]] == ["'14 of 12'"] and by["count"][0]["page"] == 2
    assert r["counts"]["cut text"] == 1 and [f["text"] for f in by["cut text"]][0].startswith("Harbour Motor…")
    assert r["counts"] == {"headline": 1, "mid-word": 1, "placeholder": 5, "joining word": 1, "count": 1, "repeated": 0, "cut text": 1,
                           "other>40%": 0, "hyphen minus": 0, "mixed range": 0, "no layer": 0,
                           "unread ranked": 0, "unread kind": 0, "left out>50%": 0, "unchecked as 0": 0,
                           "biz label": 0, "biz making": 0, "stale layer": 0, "same company": 0, "words claim": 0, "partial unsaid": 0,
                           "outlier range": 0, "added unexplained": 0, "verified count": 0, "adjacent ranked": 0, "move unexplained": 0, "scope core": 0, "layer lost unsaid": 0}          # c54 (R53 review): three more (updated on purpose)          # d53 (R53): eight more (updated on purpose)          # rv51 (R51): two more (updated on purpose)          # gl50 (R50): four more (updated on purpose)          # lane d1: "no layer" (updated on purpose); lane s3-r40: the repeated-word and "Other" columns; lane t1 (LIVE7A-014): hyphen minus, mixed range (updated on purpose)


def test_counts_that_reconcile_and_figures_beside_of_are_not_flagged():
    ok = ("A\nB\nC\n\n\n\n\n 5 of 7 companies; 1,204 of 1,300; page (2 of 6); a median of 34.4x of 12 peers; 96 of the 99; growth of 12 of 5.5%; "
          "Q3 of 2026; 100% of the value of the 12 with one\n")
    assert kinds(DC.check_text(ok)) == {}
    bad = DC.check_text("A\nB\nC\n\n 1,300 of 1,204 companies and 8 of the 7 layers\n")
    assert bad["counts"]["count"] == 2


def test_a_cut_label_alone_is_reported_and_fails_only_when_strict():
    r = DC.check_text("A\nB\nC\nD\nE\nF\nG\n Harbour Motor…     Tyre…     ₹4.09 lakh cr\n Tyre makers and Harbour Motor Company\n")
    assert kinds(r) == {"cut text": 2} and not DC.failed(r) and DC.failed(r, strict=True)


def test_the_script_reads_a_folder_reports_a_row_for_each_deck_and_exits_non_zero_on_a_failure(tmp_path, capsys):
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    (good / "a.txt").write_text(CLEAN, encoding="utf-8")
    (bad / "a.txt").write_text(CLEAN, encoding="utf-8")
    (bad / "b.txt").write_text(BAD, encoding="utf-8")
    assert DC.main([str(good)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].split() == ["deck", "pages", "headline", "mid-word", "placeholder", "joining", "word", "count", "repeated", "hyphen",
                                           "minus", "no", "layer", "unread", "ranked", "unread", "kind", "left", "out>50%", "unchecked", "as", "0",
                                           "biz", "label", "biz", "making", "stale", "layer", "same", "company", "words", "claim", "partial", "unsaid",
                                           "outlier", "range", "added", "unexplained", "verified", "count", "adjacent", "ranked",
                                           "move", "unexplained", "scope", "core", "layer", "lost", "unsaid",
                                           "cut", "text", "other>40%", "mixed", "range", "result"]          # c54 (R53 review): three more columns (updated on purpose)          # d53 (R53): eight more columns (updated on purpose)          # rv51 (R51): "biz label", "biz making" (updated on purpose); gl50 (R50): four more columns (updated on purpose)   # lane s3-r40: two columns; lane t1: two more; lane d1: "no layer" (updated on purpose)
    assert out.splitlines()[1].split() == ["a.txt", "2"] + ["0"] * 28 + ["ok"]          # c54: 28 columns (updated on purpose)          # d53: 25 columns (updated on purpose)          # rv51: 17 columns; gl50: 15 columns (updated on purpose)
    assert DC.main([str(bad)]) == 1
    out = capsys.readouterr().out
    # lane t1: the "hyphen minus" and "mixed range" columns (updated on purpose)
    assert re.search(r"b\.txt\s+2\s+1\s+1\s+5\s+1\s+1\s+0\s+0\s+0\s+0\s+0\s+0\s+0\s+0\s+0" + r"\s+0" * 11 + r"\s+1\s+0\s+0\s+FAIL", out) and "b.txt: headline (1)" in out and "p.2: '14 of 12'" in out  # c54: the three new columns (updated on purpose); d53: the eight new columns (updated on purpose); rv51: the two biz columns; gl50: the four new columns (updated on purpose)
    assert DC.main([str(tmp_path / "missing")]) == 2 and DC.main([]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert DC.main([str(empty)]) == 2


def test_a_real_pdf_of_a_deck_is_read_through_pdftotext(tmp_path):
    """A deck made by the app's own PDF writer: a clean page passes, a page with a cut headline and a broken count fails."""
    cover = Slide("Vehicles", "India (NSE and BSE) · Theme deep dive", dark=True)
    ok = Slide("Valuation", "The theme's median P/E is 29.9x; P/E of 96 of the 99 companies", eyebrow="Vehicles · Valuation")
    ok.add("table", (M, TOP, CW, 1.2), head=["Company", "Layer"], rows=[["Harbour Motor", "Component and machinery makers"]], widths=[3.0, 3.0])
    bad = Slide("Growth", "Revenue grew at 14 of 12 companies, the largest moves among the…", eyebrow="Vehicles · Growth")
    bad.add("text", (M, TOP, CW, 0.5), paras=["No listed company is shown for x."], size=11, floor=11)
    if not shutil.which("pdftotext"):          # the reader isn't installed here: the script says so and reads nothing
        (tmp_path / "deck.pdf").write_bytes(deck._render([cover, ok], "foot", "t", pdf=True))
        assert DC.main([str(tmp_path)]) == 2
        return
    (tmp_path / "deck.pdf").write_bytes(deck._render([cover, ok], "foot", "t", pdf=True))
    assert DC.main([str(tmp_path)]) == 0
    (tmp_path / "deck2.pdf").write_bytes(deck._render([cover, ok, bad], "foot", "t", pdf=True))
    assert DC.main([str(tmp_path)]) == 1
    r = DC.check_pages(DC.pages_of(str(tmp_path / "deck2.pdf")))
    assert r["pages"] == 3 and r["counts"]["headline"] == 1 and r["counts"]["count"] == 1 and r["counts"]["placeholder"] == 1
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "empty.pdf").write_bytes(b"")
    assert DC.check_file(str(broken / "empty.pdf"))["error"].startswith("could not be read") and DC.main([str(broken)]) == 1     # reported, never a crash
