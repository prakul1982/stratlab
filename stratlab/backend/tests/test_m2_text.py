"""Lane m2-text (11 Nov): the outside review of the 14 live R32 decks, its P1/P2 text items.
1. A highest/lowest headline says in its own sentence which layers it ranks (at least HEADLINE_MIN companies with the figure); the table's
   footnote uses the same floor (it said 3) and the chart marks each layer that is shown, not ranked.
2. A shown layer whose median is above the highest or below the lowest named says why it is not ranked, in one short clause.
3. "Worth a watch" is "Dated company updates": each event as a neutral fact with its day, its status (scheduled, announced, filed), its
   source and what the source adds; upcoming results read as scheduled.
4. The text itself is checked before a deck is stored: doubled words, doubled punctuation, a space before punctuation, a broken hyphen.
5. A description cell ends on a whole clause with no ellipsis; a compact table never cuts a name or a figure.
6. A theme with no comparable peers names the price date of its own P/E.
Generic: synthetic themes only, no real company's name or figure."""
import re
from datetime import date, datetime, timezone

import pytest

from app import deck
from app.intel import theme_data as D
from tests.test_deck_look import full_view
from tests.test_export import table_of, texts
from tests.test_r18_deck import deck_of
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
from tests.test_r31_bound import metals_layers, split

FLOOR = f"at least {D.HEADLINE_MIN} companies with the figure"


def steel():
    """Two steel layers of five and six companies, an aluminium layer (another commodity, a higher margin) and a three-company layer (a lower one)."""
    t = metals_layers([("Integrated steel", "IST", 5, "makes steel from iron ore in blast furnaces", "Iron & Steel", "commodity_mining", 22),
                       ("Mini mills", "MML", 6, "makes steel in electric arc furnaces from sponge iron", "Iron & Steel", "commodity_mining", 12),
                       ("Aluminium smelting", "ALS", 5, "smelts aluminium from bauxite", "Aluminium", "commodity_mining", 41),
                       ("Sponge iron makers", "SPG", 3, "makes sponge iron for steel makers in kilns", "Iron & Steel", "commodity_mining", 8)])
    t, _, m = split(t)
    return deck_of(t["region"], m, t["facts"])


def lender_block(name, n, roe, k=None):
    # gl50 (R50, updated on purpose): the layers' way of earning read (lending), else no layer is ranked
    return {"layer": name, "n": n, "revenue": 100.0, "official": False, "stats": {"roe": {"median": roe, "n": k if k is not None else n}}, "companies": [],
            "model": {"id": "lending", "family": "lending"}}


def said(slides) -> list[str]:
    """Every sentence a reader sees in a headline, a card or a paragraph."""
    out = []
    for s in slides:
        out.append(s.subtitle or "")
        for b in s.blocks:
            out += [str(p) for p in b.get("paras") or []]
            out += [str(ln) for it in b.get("items") or [] if isinstance(it, dict) for ln in it.get("lines") or []]
            out += [str(r[1]) for r in b.get("rows") or [] if s.title == "Contents" and not isinstance(r, dict)]
    return [x for x in out if x]


# ---------- 1 and 2. the headline's eligibility and why a shown layer is not ranked ----------
def test_a_ranking_headline_says_which_layers_it_ranks_and_why_a_layer_beyond_it_is_not():
    v, slides = steel()
    ch = v["chain"]
    assert ch["line"].startswith(f"Among the 2 layers with {FLOOR} and one kind of business, median EBITDA margin is highest in Integrated steel (22%)")
    assert ch["line"].endswith(f"Shown, not ranked: Aluminium smelting (41%), a different commodity; Sponge iron makers (8%), fewer than {D.HEADLINE_MIN} "
                               "companies with the figure.")
    assert ch["unranked"] == [{"layer": "Aluminium smelting", "why": "a different commodity"},
                              {"layer": "Sponge iron makers", "why": f"fewer than {D.HEADLINE_MIN} companies with the figure"}]
    # every sentence that names a highest, lowest, fastest or slowest layer says the floor in that same sentence: cover, contents,
    # findings, the value chain's pages, the questions
    ranked = [x for t in said(slides) for x in re.split(r"(?<=[.!?])\s+(?=[A-Z])", t) if re.search(r"\b(?:highest|lowest|fastest|slowest)\b", x)]
    assert len(ranked) >= 6 and all(FLOOR in x for x in ranked), [x for x in ranked if FLOOR not in x]
    assert slides[0].gate["passed"] == slides[0].gate["of"] and not slides[0].gate["dropped"]
    every_rule("steel, a layer above and one below the ranking", v, slides)


def test_the_value_chains_footnote_and_chart_agree_with_the_headline():
    v, slides = steel()
    page = next(s for s in slides if s.title == "The value chain by layer")
    foot = " ".join(p for b in page.blocks if b["kind"] == "text" for p in b["paras"])
    assert (f"among the layers ranked: those with {FLOOR} and one kind of business. "
            "Shown, not ranked: Aluminium smelting, a different commodity; Sponge iron makers, "
            f"fewer than {D.HEADLINE_MIN} companies with the figure.") in foot
    assert f"A median is shown for {D.COMPARE_MIN} companies or more." in foot
    assert "at least 3 companies;" not in foot                                                    # the marks' floor is the headline's, said once
    bars = [b for s in slides if s.title.startswith(("The value chain by layer", "Median EBITDA margin by layer")) for b in s.blocks if b["kind"] == "hbars"]
    assert bars
    for b in bars:
        assert b["cats"] == ["Integrated steel (5)", "Mini mills (6)", "Aluminium smelting (5, not ranked)", "Sponge iron makers (3, not ranked)"]
        assert b["colors"] == [deck.UP, deck.DOWN, deck.MUTED, deck.MUTED]
    # the table marks the same two layers the headline names
    t = next(b for b in page.blocks if b["kind"] == "table")
    assert sorted(t["colors"].values()) == sorted([deck.UP, deck.DOWN])


def test_a_lenders_headline_names_the_layer_below_its_lowest_and_why():
    """Live R32 Private Banks: "lowest in ... (13.1%)" beside a three-company layer at 4.9%."""
    # lane d1 (updated on purpose): 13.1% against 13.5% is a gap under a point, no comparison (R43's headline rule); 12.1% keeps the case
    ch = D.chain_table([lender_block("Large universal banks", 7, 12.1), lender_block("Regional banks, larger", 5, 13.5),
                        lender_block("Regional banks, smaller", 5, 11.2, 4), lender_block("Microfinance lenders", 3, 4.9),
                        lender_block("Payments banks", 2, 1.0)])
    assert ch["measure"] == "roe" and (ch["highest"], ch["lowest"]) == ("Regional banks, larger", "Large universal banks")
    assert ch["line"] == (f"Among the 2 layers with {FLOOR}, median return on equity is highest in Regional banks, larger (13.5%) and lowest in "
                          "Large universal banks (12.1%), a gap of 1.4 points. Shown, not ranked: Regional banks, smaller (11.2%) and "
                          f"Microfinance lenders (4.9%), fewer than {D.HEADLINE_MIN} companies with the figure.")
    # a median of two companies is not shown in the table or the chart: nothing to explain
    assert [x["layer"] for x in ch["unranked"]] == ["Regional banks, smaller", "Microfinance lenders"]
    assert "one kind of business" not in ch["line"]


def test_a_ranking_of_every_shown_layer_adds_no_second_sentence_and_ties_say_no_reason():
    ch = D.chain_table([lender_block("A banks", 6, 15.0), lender_block("B banks", 5, 12.0)])
    assert ch["line"] == f"Among the 2 layers with {FLOOR}, median return on equity is highest in A banks (15%) and lowest in B banks (12%), a gap of 3 points."
    assert ch["unranked"] == []
    inside = D.chain_table([lender_block("A banks", 6, 15.0), lender_block("B banks", 5, 12.0), lender_block("C banks", 3, 13.0)])
    assert "Shown, not ranked" not in inside["line"]                                              # between the two named: the footnote says why
    assert inside["unranked"] == [{"layer": "C banks", "why": f"fewer than {D.HEADLINE_MIN} companies with the figure"}]
    assert deck.unranked_words(inside) == f"Shown, not ranked: C banks, fewer than {D.HEADLINE_MIN} companies with the figure."


def test_the_rankings_own_scope_is_not_a_figure_the_tables_must_show():
    """A deck whose tables show no "5" and no "2" keeps its headline: the scope is the rule, not a claim."""
    shown = {"pct": {22.0, 12.0, 41.0}, "x": set(), "pts": set(), "n": set(), "gaps": set(), "money": set()}
    line = (f"Among the 2 layers with {FLOOR} and one kind of business, median EBITDA margin is highest in A (22%) and lowest in B (12%), "
            "a gap of 10 points. Shown, not ranked: C (41%), a different commodity")
    assert D.claim_mismatches(deck._CHECK_SKIP.sub("", line), shown) == []
    assert D.claim_mismatches(deck._CHECK_SKIP.sub("", f"D (8%), fewer than {D.HEADLINE_MIN} companies with the figure."), {**shown, "pct": {8.0}}) == []
    assert D.claim_mismatches(deck._CHECK_SKIP.sub("", line.replace("(22%)", "(23%)")), shown) == ["23%", "10 points"]      # a figure is still checked, and the gap with it


def test_every_ranking_floor_is_the_headline_floor():
    rows = [{"v": 9.0, "n": 3}, {"v": 4.0, "n": 5}, {"v": 6.0, "n": 6}]
    assert deck.top_of(rows, lambda r: r["v"], lambda r: r["n"]) == rows[2]                       # the three-company layer is never the highest
    src = open(deck.__file__).read()
    assert "among the layers whose median is of at least" not in src


# ---------- 3. dated company updates ----------
def updates_view():
    v = full_view()
    own = v["sections"]["ownership"]
    own["red_flags"] = [{"symbol": "AUD", "name": "Audit Co", "at": "2026-10-31", "label": "Auditor resigned",
                         "subject": "Resignation of Statutory Auditor", "url": "https://filings.example/aud.pdf",
                         "text": "M/s Old & Co have resigned as statutory auditors citing pre-occupation; there are no other material reasons. "
                                 "The Board has appointed M/s New & Co as statutory auditors to fill the casual vacancy."},
                        {"symbol": "AUE", "name": "Bare Co", "at": "2026-10-30", "label": "Auditor resigned", "subject": "Updates", "text": ""}]
    own["holdings"] = [{"symbol": "PRM", "name": "Promoter Co", "quarter": "2026-09-30", "promoter": 59.8, "institutions": 20.0,
                        "promoter_change": -15.0, "institutions_change": 8.0}]
    v["sections"]["events"]["results_due"] = [
        {"symbol": "DUE", "name": "Due Co", "date": "2026-11-09", "purpose": "Financial Results/Other business matters"},
        {"symbol": "OLD", "name": "Passed Co", "date": "2026-11-05", "purpose": "Financial Results"},
        {"symbol": "FAR", "name": "Far Co", "date": "2026-12-20", "purpose": "Financial Results"}]
    v["checks"]["one_off"] = [{"symbol": "ONE", "name": "Margin Co", "net": 30.0, "ebitda": 20.0}]
    return v


def test_each_dated_update_has_its_day_status_source_and_the_context_its_source_gives():
    w = {x["name"]: x for x in deck.watch_list(updates_view(), date(2026, 11, 7))}
    assert w["Audit Co"] == {"name": "Audit Co", "fact": "Resignation of the statutory auditor", "at": "2026-10-31", "status": "Announced",
                             "source": "Exchange filing", "url": "https://filings.example/aud.pdf", "ref": "Events",
                             "context": "The filing says a new auditor was appointed and that the auditor raised no concerns."}
    assert w["Bare Co"]["fact"] == "Resignation of an auditor" and w["Bare Co"]["context"] == ""   # nothing the filing doesn't say
    assert w["Promoter Co"]["status"] == "Filed" and w["Promoter Co"]["source"] == "Shareholding filing"
    assert (w["Due Co"]["fact"], w["Due Co"]["status"]) == ("Financial results; other business matters", "Scheduled")
    assert w["Passed Co"]["status"] == "Was scheduled" and "Announced" not in str(w["Passed Co"])   # no results stored: never said announced
    assert "Far Co" not in w and "Margin Co" not in w                                               # beyond a week; a flag with no day is not a dated update
    assert all(x.get("at") and x.get("status") and x.get("source") for x in w.values())


def test_the_page_is_named_dated_company_updates_everywhere_and_takes_no_side():
    slides = deck.theme_plan(updates_view(), now=datetime(2026, 11, 7, tzinfo=timezone.utc))[0]
    everything = texts(slides)
    assert "Worth a watch" not in everything and "worth a watch" not in everything
    page = next(s for s in slides if s.title == deck.UPDATES_TITLE)
    assert deck.UPDATES_TITLE == "Dated company updates" and "picked by fixed rules, not a view" in page.subtitle
    t = table_of(slides, deck.UPDATES_TITLE)
    assert t["head"][:5] == ["Company", "Update", "Date", "Status", "Source"]
    rows = {r[0]: r for r in t["rows"]}
    assert rows["Due Co"][1:5] == ["Financial results; other business matters", "09 Nov 2026", "Scheduled", "Results calendar"]
    assert rows["Audit Co"][1] == ("Resignation of the statutory auditor. The filing says a new auditor was appointed and that the auditor raised "
                                   "no concerns.") and rows["Audit Co"][2:5] == ["31 Oct 2026", "Announced", {"text": "Exchange filing", "url": "https://filings.example/aud.pdf"}]
    assert rows["Bare Co"][4] == "Exchange filing"                                                 # no address held: the source named, not linked
    assert [r[2] for r in t["rows"]] == sorted((r[2] for r in t["rows"]), key=lambda d: datetime.strptime(d, "%d %b %Y" if d[:2].isdigit() else "%b %Y"),
                                                reverse=True)
    card = next(it for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards" for it in b["items"]
                if "ated company updates" in it["title"])
    assert any("dated updates at" in ln and "each with its date, status and source" in ln for ln in card["lines"])
    assert any("the companies' dated updates" in str(r[1]) for r in table_of(slides, "Contents")["rows"])
    words = " ".join(texts([page]).lower().split())
    for word in ("worth", "warning", "red flag", "concerning", "worrying", "good news", "bad news", "positive", "negative", "trigger", "alert"):
        assert word not in words, word
    assert "results due" not in words                                                              # upcoming results read as scheduled
    assert slides[0].gate["passed"] == slides[0].gate["of"]


def test_the_filings_own_words_reach_the_update():
    rows = D.flagged_rows([{"symbol": "AUD", "at": "2026-10-31", "category": "auditor_resign", "label": "Auditor resigned",
                            "subject": "Resignation of Secretarial Auditor", "text": "The secretarial auditor has resigned."}], {})
    assert rows[0]["text"] == "The secretarial auditor has resigned."
    assert deck.auditor_update(rows[0]) == ("Resignation of the secretarial auditor", "")
    assert deck.results_purpose(None) == "Financial results" and deck.results_purpose("Dividend") == "Financial results; dividend"


# ---------- 4. the text itself ----------
@pytest.mark.parametrize("given,want,why", [
    ("similar market value, outside the the theme)", "similar market value, outside the theme)", "doubled word"),
    ("The the median of of 5 companies", "The median of 5 companies", "doubled word"),
    ("each layer's companies companies added", "each layer's companies added", "doubled word"),
    ("figures yet: Holding, Inc.. Revenue growth above 100%", "figures yet: Holding, Inc. Revenue growth above 100%", "doubled full stop"),
    ("Newer results filed: Qualco, Inc..", "Newer results filed: Qualco, Inc.", "doubled full stop"),
    ("among low-income segments, say.. · 01 Jul 2026", "among low-income segments, say… · 01 Jul 2026", "two dots for an ellipsis"),
    ("margins,, returns;; growth", "margins, returns; growth", "doubled punctuation"),
    ("net margin 5.6% , ROE 4.9% .", "net margin 5.6%, ROE 4.9%.", "space before punctuation"),
    ("helicopters, aero -engines, avionics", "helicopters, aero-engines, avionics", "hyphen broken off its word"),
    ("makes aero- engines", "makes aero-engines", "hyphen broken off its word"),
    ("the gap ( 2 points ) holds", "the gap (2 points) holds", "space inside a bracket"),
])
def test_a_mechanical_defect_is_repaired_and_named(given, want, why):
    got, whys = deck.tidy_text(given)
    assert got == want and why in whys and deck.text_flags(got) == []


@pytest.mark.parametrize("clean", [
    "R R Kabel Ltd", "M M Forgings Ltd", "Bora Bora Resorts Ltd", "It had had a merger.", "pre- and post-tax margins", "new price... · 05 Nov 2026",
    "12% (4 of 5) · 3.5x; −5.6% to +7%", "U.S. companies, e.g. this one.", "1.2x to 384.5x", "– (2)", "n/a", "FY Dec 2025", "p. 19",
    "Considered 20 · confirmed 20 · with figures 19", "a ratio of 1 : 2", "revenue −32.9%.", "⟦How the figures are built⟧", "₹1.09 lakh cr",
    "outside the theme for 93, the theme's other companies counted for 1"])
def test_a_clean_text_a_name_and_a_figure_are_never_touched(clean):
    assert deck.tidy_text(clean) == (clean, [])


def test_every_slide_goes_through_the_repair_and_the_gate_counts_it():
    v = full_view()
    v["layers"][0]["companies"][0]["what"] = "makes helicopters, aero -engines and avionics for the the armed forces , and spares.."
    v["summary"] = "The theme's companies make cells and and packs. Margins vary ."
    slides = deck.theme_plan(v)[0]
    everything = texts(slides)
    for bad in (r"aero -engines", r"\bthe the\b", r"\band and\b", r"forces ,", r"vary \."):
        assert not re.search(bad, everything), bad
    assert "aero-engines" in everything or "cells and packs" in everything
    tidied = slides[0].tidied
    assert tidied and all(x["fixed"] != x["text"] and x["why"] for x in tidied)
    prose = next(x for x in slides[0].gate["items"] if x["id"] == "prose")
    assert prose["ok"] and re.match(r"\d+ text repairs? \(doubled words, punctuation, hyphens\)", prose["note"])
    assert len(slides[0].gate["items"]) == len(deck.GATE_ITEMS)                                   # counted inside the prose item: no new item
    # a deck with nothing to repair says nothing of it
    clean = deck.theme_plan(full_view())[0]
    assert clean[0].tidied == [] and not next(x for x in clean[0].gate["items"] if x["id"] == "prose")["note"]
    for s in clean:
        for t in [s.title, s.subtitle or ""] + [p for b in s.blocks for p in b.get("paras") or []]:
            assert deck.text_flags(t) == [], t


def test_no_template_of_the_deck_or_the_dive_doubles_a_word():
    """The review read "outside the the theme" in a P/E description: no template writes it (the valuation table wraps "…: outside" /
    "the theme for 93, the theme's other…" across its figure cells), and none may."""
    import ast
    from app.intel import theme_base, theme_routes
    for mod in (deck, D, theme_base, theme_routes):
        tree = ast.parse(open(mod.__file__).read())
        docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body
                and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for n in ast.walk(tree):                                   # every string a sentence is built from; docstrings and patterns apart
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs and "\\" not in n.value and "(?" not in n.value:
                assert not re.search(r"\b(the|a|an|of|in|on|to|for|and|or|with|by|from|is|its) \1\b", n.value, re.I), n.value
    for sets in ({"sector": 5}, {"sector_theme": 4}, {"sector": 93, "sector_theme": 1}, {}):
        assert deck.text_flags(deck.peer_set_words({"sets": sets})) == []


# ---------- 5. the last cut lines ----------
@pytest.mark.parametrize("text,want", [
    ("Agrochem Exports is principally engaged in export of agrochemicals (technical grade and formulations) and non-agrochemical products "
     "such as conveyor belts, dyes and dye intermediates", "Agrochem Exports is principally engaged in export of agrochemicals (technical grade and formulations)"),
    ("designs, manufactures, upgrades and provides lifecycle MRO for aircraft, helicopters, aero-engines, avionics and accessories for the "
     "armed forces", "designs, manufactures, upgrades and provides lifecycle MRO for aircraft, helicopters, aero-engines"),
    ("develops and manufactures biosimilars and novel biologics for diabetes, oncology and immunology including insulins, monoclonal antibodies "
     "and recombinant proteins", "develops and manufactures biosimilars and novel biologics for diabetes, oncology and immunology"),
    ("is engaged in the business of Real Estate Development and Leasing of commercial properties and Management and Hospitality services "
     "across the major cities", "is engaged in the business of Real Estate Development and Leasing of commercial properties"),
    ("makes speciality chemicals (agro intermediates, pharma intermediates, dyes and pigments, and many other speciality products for its "
     "customers) in India", "makes speciality chemicals"),
])
def test_a_description_cell_ends_on_a_whole_clause_with_no_ellipsis(text, want):
    got = deck.whole_clause(text, 110)
    assert got == want and "…" not in got and got.count("(") == got.count(")") and len(got) <= 110
    assert deck.sentences(text, 110).endswith("…")                                                 # what the cell held before


def test_whole_sentences_are_still_kept_whole_and_a_short_text_as_it_is():
    assert deck.whole_clause("It makes forgings. " + "A very long second sentence that goes on about plants and products " * 4, 120) == "It makes forgings."
    assert deck.whole_clause("Mines iron ore.", 110) == "Mines iron ore."
    assert deck.whole_clause("", 110) == ""
    cut = deck.whole_clause("word " * 60, 100)
    assert not cut.endswith("…") and len(cut) <= 100


def test_the_smaller_layers_page_never_ends_a_description_in_an_ellipsis():
    v = full_view()
    long = ("designs, manufactures, upgrades and provides lifecycle MRO for aircraft, helicopters, aero-engines, avionics and accessories for the "
            "armed forces of the country")
    one = dict(v["layers"][0]["companies"][0], symbol="SOLO", name="Solo Aero Ltd", what=long)
    v["layers"].append({**v["layers"][0], "layer": "Aircraft makers", "n": 1, "companies": [one]})
    slides = deck.theme_plan(v)[0]
    page = [s for s in slides if s.title.startswith(deck.SMALL_TITLE)]
    if page:                                                                                        # the fixture pages a one-company layer here
        cells = [r[2] for r in table_of(slides, deck.SMALL_TITLE)["rows"]]
        assert cells and not any(str(c).endswith("…") for c in cells)
    src = open(deck.__file__).read()
    assert 'whole_clause(_what(c.get("what") or "", c.get("name") or "")' in src and 'whole_clause(sub.get("detail") or "", 160)' in src   # LIVE6-007 passes the name (updated on purpose)


SECTOR_HEAD = ["Company", "SBC / revenue", "Capex / revenue", "Capex", "Inventory days", "R&D / revenue", "RPO / revenue", "RPO growth",
               "Deferred revenue growth", "FCF margin", "Period"]
SECTOR_ROWS = [["Chipdesign Semiconductor, Inc.", "29.9%", "6.6%", "$14 m", "136 days", "70.9%", "n/a", "n/a", "n/a", "−32.9%", "FY Dec 2025"],
               ["Median (companies)", "4.4% (83 of 98)", "4.4% (83 of 95)", "$34 m (82 of 95)", "127 days (79 of 95)", "18.8% (81 of 97)",
                "1.47x (5 of 6)", "+17.1% (5 of 6)", "+35.2% (4 of 5)", "7.6% (83 of 98)", ""]]


def test_a_compact_tables_last_page_never_cuts_a_name_a_figure_or_a_header_word():
    """Live R32 Semiconductors, the sector table's last page (one company and the medians): "indie…" under "Compa/ny" and a median "+35…"."""
    b = {"kind": "table", "head": SECTOR_HEAD, "rows": SECTOR_ROWS, "widths": [2.3] + [0.95] * 9 + [1.35], "tight": True, "compact": True, "strong": [1]}
    lay = deck.table_layout(b, deck.CW, 5.0)
    assert abs(sum(lay["widths"]) - deck.CW) < 0.01
    cells = [deck._cell_text(c) for r in lay["rows"] for c in r]
    assert not any(c.endswith("…") for c in cells), cells
    assert lay["rows"][0][0] in deck.label_forms("Chipdesign Semiconductor, Inc.") and lay["rows"][0][-1] == "FY Dec 2025"
    assert lay["rows"][1][1:10] == SECTOR_ROWS[1][1:10]                                            # every median with its count, whole
    for hd, cw in zip(SECTOR_HEAD, lay["widths"]):                                                 # no header word broken ("Compa/ny")
        assert set(deck.wrap(hd, deck.BODY_MIN, cw - 0.2, True)) <= set(hd.split()) | {hd} | {" ".join(hd.split()[i:j]) for i in range(4) for j in range(5)}
    for i, r in enumerate(lay["rows"]):
        for c, cw in zip(r, lay["widths"]):
            t = deck._cell_text(c)
            lines = deck.wrap(t, deck.BODY_MIN, cw - 0.2, i == 1)
            assert len(lines) <= 2 and all(w in t.split() for ln in lines for w in ln.split()), (t, lines)
    probe = deck.Slide("Sector operating figures: US companies (8 of 8)", "x")
    probe.add("table", (deck.M, deck.TOP, deck.CW, 2.0), **{k: v_ for k, v_ in b.items() if k != "kind"})
    assert deck.probe(probe) == []


def test_a_table_too_narrow_for_every_floor_keeps_its_widths():
    b = {"head": ["Company", "A"], "rows": [["A very long company name indeed Ltd", "12.3% (4 of 5)"]], "widths": [1.0, 1.0]}
    assert deck._keep_whole(b, [0.4, 0.4]) == [0.4, 0.4]


# ---------- 6. the price date of a theme's own P/E ----------
def test_a_theme_with_no_comparable_peers_names_the_price_date_of_its_own_pe():
    """Live R32 Telecom: the one deck of 14 whose P/E line named no "(prices at the ... close)"."""
    v, slides = steel()
    val = v["sections"]["valuation"]
    assert not D.relative_ok(val) and val["price_at"] == str(v["as_of"])[:10]
    priced = f"prices at the {deck._day(val['price_at'])} close"                                 # a day as the deck writes days
    lines = [x for x in said(slides) if "The theme's own median P/E" in x]
    assert len(lines) >= 2 and all(priced in x for x in lines), lines                              # the findings and the valuation page
    bare = {"pe": {"median": 20.0, "n": 5, "min": 10.0, "max": 30.0}}
    assert "prices at" not in deck.descriptive_line(bare)                                          # no day held: none said
    assert deck.descriptive_line({**bare, "price_at": "2026-11-09"}).endswith(
        "5 companies, 10.0x to 30.0x), prices at the 09 Nov 2026 close; comparable peers for 0 of 5, so no relative figure")


def test_the_versions_are_bumped_so_kept_dives_and_decks_are_made_again():
    assert D.DIVE_TEXT >= 7 and deck.THEME_DECK_VERSION >= 45
