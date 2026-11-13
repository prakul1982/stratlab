"""Release 48 (lane vr48, the outside review of the live R46 decks).

P1: every highest/lowest claim between layers is reproducible. The live R46 Chemicals deck said "median EBITDA margin is highest in Custom
synthesis manufacturers (22%) and lowest in Basic organic intermediates (9.5%)" with no company set or eligibility rule beside it ("the
comparability rationale is thin"). Each comparison the deck makes, or declines to make, now records its metric, each compared layer's
companies by name with its count, and the rules applied with their figures (the headline floor and coverage, one way of earning, one period
basis, and the capital-intensity test with each layer's capital for each unit of revenue and the threshold); an appendix page, "Comparison
basis", prints them and each page that ranks points to it.

P2: every provenance reference resolves. The publication gate's source item fails when a checked figure has no row on the "Figure sources"
pages, when a data-confidence row names checked figures with no reference to them, when a compared layer has no row of its companies, or when a
page reference finds no page (the live decks' findings cards pointed to "The latest quarter" and "Sector operating figures" pages that some
decks don't have, printed as nothing).

Every company here is synthetic; the layer names and margins are those of the live R46 Chemicals headline."""
from app import deck
from app.intel import theme_data as D
from scripts import deck_check
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_r48_reconcile import chem_facts, chem_map, co

LAYERS = (("Custom synthesis manufacturers", "CS", 6, 22.0, 0.20), ("Basic organic intermediates", "BO", 8, 9.5, 0.04),
          ("Chlor-alkali and soda ash producers", "CA", 6, 15.0, 0.10))


def chem(debt=None, model=None):
    """Three layers of chemical makers: each company's EBITDA margin about its layer's, revenue growth by layer, debt `debt[prefix]` times
    revenue (capital for each unit of revenue), and the layers' way of earning (`model`: a theme_base.by_model dict for every layer)."""
    f, vc = {}, []
    for lname, pre, n, opm, grow in LAYERS:
        cos = []
        for i in range(n):
            sym, sales = f"{pre}{i}", 1000.0 + 50 * i
            x = co(sym, f"{lname.split()[0]} Chem {i} Ltd", sales, opm + (i % 3) - 1, sales * (opm - 8) / 100)
            for j, y in enumerate(x["years"]):
                y["sales"] = sales / (1 + grow) ** (3 - j)
            x["debt"] = x["years"][-1]["debt"] = sales * (debt or {}).get(pre, 1.0)
            f[sym] = x
            cos.append({"name": x["name"], "ticker": sym, "what": "makes chemicals"})
        vc.append({"layer": lname, "description": "Makes chemicals.", "companies": cos, **({"model": dict(model)} if model else {})})
    m = {"sector": "Chemicals", "value_chain": vc, "sub_themes": [], "placements": {"checked": True, "pending": 0, "left_out": 0,
                                                                                    "placed": sum(len(x["companies"]) for x in vc)}}
    return m, f


def it_text(b):
    return next(r["text"] for r in b["rules"] if r["rule"] == "capital intensity")


def table(slides, title):
    return [r for s in slides if s.title == title or s.title.startswith(title + " (") for b in s.blocks if b["kind"] == "table"
            for r in b["rows"] if not isinstance(r, dict)]


def basis_pages(slides):
    """ex49: each comparison's page: (its claim, its rules' lines, its table's rows)."""
    return [(s.subtitle, [p for b in s.blocks if b["kind"] == "text" and b.get("size") == deck.RULES_SIZE for p in b["paras"]],
             [r for b in s.blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict)])
            for s in slides if s.title.startswith(deck.COMPARE_TITLE)]


# ---------- P1: the comparison basis ----------
def test_the_chemicals_ranking_states_its_metric_company_sets_and_rule():
    m, f = chem()
    v, slides = deck_of("IN", m, f)
    ch = v["chain"]
    assert ch["highest"] == "Custom synthesis manufacturers" and ch["lowest"] == "Basic organic intermediates"
    b = ch["basis"]
    assert b["metric"] == "EBITDA margin" and b["made"] and (b["high"], b["low"]) == (ch["highest"], ch["lowest"])
    g = {x["layer"]: x for x in b["groups"]}
    assert g["Custom synthesis manufacturers"]["n"] == 6 and g["Custom synthesis manufacturers"]["names"] == [f"Custom Chem {i} Ltd" for i in range(6)]
    assert g["Basic organic intermediates"]["n"] == 8 and len(g["Basic organic intermediates"]["names"]) == 8
    rules = {r["rule"]: r for r in b["rules"]}
    # (updated on purpose, ex49: the business model is a rule of its own, apart from the way of earning)
    assert set(rules) == {"headline floor", "like-for-like model", "period basis", "business model", "capital intensity"} and all(r["passed"] for r in rules.values())
    it = rules["capital intensity"]["test"]
    assert it["threshold"] == D.INTENSITY_FACTOR and it["ratio"] == 1.0 and {x["layer"]: x["value"] for x in it["values"]}["Basic organic intermediates"] == 3.0
    # printed: the appendix page, a row per compared layer with its companies by name; the value chain and the findings point to it
    # (updated on purpose, ex49: one comparison a page, its claim the page's takeaway, its rules a line each, one table of its layers)
    claim, rules_, rows = next(p for p in basis_pages(slides) if p[0].startswith("EBITDA margin by layer"))
    assert claim.startswith("EBITDA margin by layer, among layers with at least 5 companies with the figure: highest Custom synthesis manufacturers, "
                            "lowest Basic organic intermediates. p. ")
    assert any(x.startswith("Headline floor (met): each layer with at least 5 companies with the figure") for x in rules_)
    assert ("Capital intensity, a proxy for capital needs (met): the largest layer figure of capital for each unit of revenue is 1.0 times the "
            "smallest; ranked only at 3 times or less; passing it alone never makes layers comparable.") in rules_
    first = next(r for r in rows if r[0] == "Custom synthesis manufacturers")
    assert first[1:3] == ["22% (6)", "3.00 (6)"] and first[-1].startswith("Custom Chem 0 Ltd, Custom Chem 1 Ltd")
    assert any(r[0] == "Basic organic intermediates" and r[1] == "9.5% (8)" and "Basic Chem 7 Ltd" in r[-1] for r in rows)
    vc = next(s for s in slides if s.title == "The value chain by layer")
    page = next(i for i, s in enumerate(slides, 1) if s.title.startswith(deck.COMPARE_TITLE))
    assert f"Each compared layer's companies by name, the rules and the capital figures: p. {page}." in " ".join(p for bl in vc.blocks for p in bl.get("paras") or [])
    con = table(slides, "Contents")
    assert "each comparison's companies and rule" in next(r for r in con if r[0] == "Appendix")[1]
    got = deck_check.check_pages(["\n".join(x for x in texts(slides).split("\n") if x != "None")])
    assert not deck_check.failed(got, strict=True), got["findings"][:3]


def test_layers_whose_capital_needs_differ_are_not_ranked_and_the_test_figures_are_printed():
    m, f = chem(debt={"CS": 8.0})
    v, slides = deck_of("IN", m, f)
    b = v["chain"]["basis"]
    assert v["chain"]["highest"] is None and not b["made"] and b["why"] == "capital for each unit of revenue differs more than threefold"
    it = next(r for r in b["rules"] if r["rule"] == "capital intensity")
    assert not it["passed"] and it["test"]["ratio"] == 8.0 and it["test"]["high"] == "Custom synthesis manufacturers"
    claim, rules_, rows = basis_pages(slides)[0]          # (updated on purpose, ex49: the claim, the rules' lines and the table apart)
    assert claim.startswith("EBITDA margin by layer: not ranked, capital for each unit of revenue differs more than threefold.")
    assert any(x.startswith("Capital intensity, a proxy for capital needs (not met): ") and "is 8.0 times the smallest; ranked only at 3 times or less" in x
               for x in rules_)
    assert next(r for r in rows if r[0] == "Custom synthesis manufacturers")[1:3] == ["22% (6)", "24.00 (6)"]
    assert "Custom synthesis manufacturers 24.00 (6 companies)" in it_text(b)


def test_the_way_of_earning_each_layer_is_shown_for_is_in_the_like_for_like_rule():
    model = {"id": "manufacturing", "family": "making", "known": 6, "of": 6}
    m, f = chem(model=model)
    v, _ = deck_of("IN", m, f)
    rule = next(r for r in v["chain"]["basis"]["rules"] if r["rule"] == "like-for-like model")
    assert rule["passed"] and rule["text"] == "one way of earning: making and selling finished products of their own"


def test_every_ranking_the_deck_makes_has_its_basis_and_the_findings_point_to_it():
    m, f = chem()
    v, slides = deck_of("IN", m, f)
    t = texts(slides)
    assert "revenue grew fastest in the latest year in Custom synthesis manufacturers" in t
    claims = [p[0] for p in basis_pages(slides)]          # (updated on purpose, ex49: each comparison's claim is its page's takeaway)
    assert any(c.startswith("Revenue growth in the latest year (median) by layer, among layers with at least 5 companies with the figure: highest "
                            "Custom synthesis manufacturers, lowest Basic organic intermediates. p. ") for c in claims)
    assert any(c.startswith("Median ROCE by layer") or c.startswith("Revenue growth") for c in claims)
    cards = next(s for s in slides if s.title == "Key findings")
    page = next(i for i, s in enumerate(slides, 1) if s.title.startswith(deck.COMPARE_TITLE))
    notes = [it.get("note") for b in cards.blocks if b["kind"] == "cards" for it in b["items"]]
    assert any(f"p. {page}" in str(n) for n in notes)
    assert next(x for x in slides[0].gate["items"] if x["id"] == "sourced")["ok"]       # each claim's layers have their rows (P2)


# ---------- P2: every provenance reference resolves ----------
def test_the_gate_passes_when_every_source_and_comparison_row_renders():
    for m, f in (chem(), (chem_map(), chem_facts())):
        v, slides = deck_of("IN", m, f)
        assert getattr(slides[0], "unresolved", None) is None
        src = next(x for x in slides[0].gate["items"] if x["id"] == "sourced")
        assert src["ok"], slides[0].gate["dropped"]


def test_a_checked_figure_with_no_source_row_or_a_dead_reference_fails_the_gate():
    v, slides = deck_of("IN", chem_map(), chem_facts())
    view = {**v, "comparisons": v["chain"].get("basis") and [v["chain"]["basis"]] or []}
    assert not [x for x in deck.provenance_flags(slides, view) if "source row" in x["why"]]
    for s in slides:                      # the Swan Corp row taken off the source page
        if s.title.startswith(deck.SOURCES_TITLE):
            for b in s.blocks:
                if b["kind"] == "table":
                    b["rows"] = [r for r in b["rows"] if isinstance(r, dict) or "SWANCORP" not in r[0]]
    got = deck.provenance_flags(slides, view)
    assert {"slide": deck.SOURCES_TITLE, "text": "Swan Corp Ltd (SWANCORP), net margin", "why": "a checked figure with no source row",
            "rule": "sourced"} in got
    # a page reference that finds no page is kept for the gate, never printed as nothing unnoticed
    s = deck.Slide("A page", "⟦No such page⟧ and ⟦A page⟧")
    deck._refs([s])
    assert s.unresolved == [("A page", "No such page")] and s.subtitle.endswith("and p. 1")


def test_the_findings_cards_point_only_to_pages_the_deck_has(monkeypatch):
    # the synthetic decks have no quarter page and no sector-figures page: their findings cards pointed to both, printed as nothing
    from tests import synthetic_themes_r27 as S
    for name, v, slides in S.decks():
        assert getattr(slides[0], "unresolved", None) is None, name
        assert next(x for x in slides[0].gate["items"] if x["id"] == "sourced")["ok"], name
    # every reference as written, before the page numbers are set, names a page the deck has
    monkeypatch.setattr(deck, "_refs", lambda slides: None)
    for name, v, _ in S.decks():
        slides, _ = deck.theme_plan(v)
        titles = [s.title for s in slides]
        refs = {m.group(1) for t in texts(slides).split("\n") for m in deck.REF.finditer(t)}
        assert refs and all(any(t.startswith(r) for t in titles) for r in refs), (name, sorted(r for r in refs if not any(t.startswith(r) for t in titles)))


def test_a_data_confidence_row_of_checked_figures_points_to_their_source_rows():
    v, slides = deck_of("IN", chem_map(), chem_facts())
    view = {**v, "comparisons": []}
    # before R48 the "Figure checks" row named its figures with no reference to their source rows
    for s in slides:
        if s.title == "Data confidence":
            for b in s.blocks:
                if b["kind"] == "table":
                    b["rows"] = [r if isinstance(r, dict) or r[0] != "Net above EBITDA margin" else [r[0], r[1].split(" Each one's")[0], r[2]]
                                 for r in b["rows"]]
    assert {"slide": "Data confidence", "text": "Net above EBITDA margin", "why": "checked figures named with no reference to their source rows",
            "rule": "sourced"} in deck.provenance_flags(slides, view)
    held = deck.confidence_rows({**v, "checks": {**v["checks"], "held": [{"symbol": "X", "name": "X Ltd", "key": "roce", "value": -2.0,
                                                                          "checks": ["c"], "state": D.INVALID}]}}, deck.coverage(v), deck.date(2026, 11, 13))
    row = next(r for r in held if r[0] == "Figure checks")
    assert row[1].startswith("1 figure failed a check: X Ltd, ROCE −2.0% (invalid: c). Its source and lines: ⟦Figure sources⟧.")
