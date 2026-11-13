"""Lane n1-render: rendered-output completeness, text sanitising and last cuts, from the outside review of the live R33 decks. Each fix is
generic (every sector, India and the US) and checked on theme_plan's own slides where it shows on them.
1. The appendix's "Who is in each layer's calculations" names every company: a layer's row taller than a page goes on in "(continued)"
   rows, so no roll page is an empty table and no layer is dropped (Retail p.41, Real Estate p.36).
2. The completeness gate on the finished pages: a table page with no data row, a page with nothing on it, a run of "(k of n)" pages with a
   gap, a heading's count the rows don't make and a row printed twice fail the layout or reconcile item and are logged.
3. Names lose filing tokens ("Diodes Inc /del/"), double spaces and trailing commas; unfilled tokens in any slide text fail the prose item.
4. A findings card of one long sentence ends on a whole clause, never "…".
5. "Capital for each unit of revenue differs more than threefold": each layer's figure, the ratio and the threshold are on the page.
6. "buy", "sell", "accumulate" are advice only as a recommendation; a company buying its inputs is a fact.
7. With no dated update, the findings say so in one line that never gives way.
Synthetic themes only: no real company's name or figure."""
import copy
import logging
import re

from app import deck
from app.deck import Slide
from tests.synth_structures_r27class import _rows, build
from tests.test_r18_deck import deck_of


# ---------- 1. the appendix roll names every company, over as many rows as it takes ----------
def retail_like(n_in=40, n_other=22, n_vague=9):
    """Three layers, each with a long list in its calculations and companies left out for two reasons (the live Retail deck's shape)."""
    def layer(pfx, label):
        return (f"{label} retailers", f"{label}.",
                _rows(pfx + "R", n_in, f"{label} Consolidated Stores", "runs retail stores selling goods to shoppers", "Retailing", "retail")
                + _rows(pfx + "T", n_other, f"{label} Software Licensing", "sells subscriptions for its own software", "Software Products", "software")
                + _rows(pfx + "V", n_vague, f"{label} Diversified Group", "a diversified group", "Retailing", ""))
    t = build("US", "Consumer retail", [layer("A", "Off-price"), layer("B", "Online"), layer("C", "Specialty")], [])
    m = t["map"]
    for x in m["value_chain"]:
        for c in x["companies"]:
            k = c["ticker"][1]
            c.update(model={"R": "retail", "T": "software"}.get(k, ""), model_confidence="high" if k in "RT" else "")
            c["model_out"] = {"T": "other", "V": "unknown"}.get(k, c.get("model_out"))
            if not c["model_out"]:
                c.pop("model_out")
    return t["region"], m, t["facts"]


def roll_pages(slides):
    return [s for s in slides if s.title.startswith(deck.ROLL_TITLE)]


def test_every_roll_page_shows_its_rows_and_every_layer_and_company_is_named():
    region, m, f = retail_like()
    v, slides = deck_of(region, m, f)
    pages = roll_pages(slides)
    assert pages and pages[0].subtitle.startswith("3 layers with a listed company left out")
    rows = []
    for s in pages:
        t = next(b for b in s.blocks if b["kind"] == "table")
        lay = deck.table_layout(t, t["box"][2], t["box"][3])
        assert t["rows"] and len(lay["rows"]) == len(t["rows"]), s.title           # no empty page, no row left off
        rows += t["rows"]
    layers = [r[0].removesuffix(deck.ROLL_MORE) for r in rows]
    assert sorted(set(layers)) == ["Off-price retailers", "Online retailers", "Specialty retailers"]
    assert any(r[0].endswith(deck.ROLL_MORE) for r in rows)                          # a long layer went on in a row of its own
    every = " ".join(str(c) for r in rows for c in r[1:])
    for label in ("Off-price", "Online", "Specialty"):
        assert all(f"{label} Consolidated Stores {i}" in every for i in range(40))      # every company in, named
        assert all(f"{label} Software Licensing {i}" in every for i in range(22))
        assert all(f"{label} Diversified Group {i}" in every for i in range(9))
    assert " more" not in every                                                       # never "and 12 more" in the appendix
    first = next(r for r in rows if r[0] == "Online retailers")
    # (updated on purpose, ex49: each reason is its kind with what exactly, the company's way of earning for a different revenue model)
    assert first[1].startswith("40 of 71: ") and first[2].startswith("31: different revenue model (software products and subscriptions): ")
    cont = [r for r in rows if r[0] == "Online retailers" + deck.ROLL_MORE]
    assert all(r[2].startswith(("different revenue model", "insufficient evidence")) or not r[2] for r in cont)   # the reason before its names
    assert not [d for d in slides[0].gate["dropped"] if "Who is in" in d["slide"]], slides[0].gate["dropped"]


def test_roll_rows_one_row_when_it_fits_and_even_continued_rows_when_not():
    ins = [(f"Company {i}", "") for i in range(4)]
    outs = [("Other 0", "other business")]
    assert deck.roll_rows("Layer A", ins, outs, 5.0) == [["Layer A", "4 of 5: Company 0, Company 1, Company 2, Company 3", "1: other business: Other 0"]]
    ins = [(f"A rather long company name number {i}", "figures in part" if i % 5 == 0 else "") for i in range(120)]
    outs = [(f"Left out company {i}", "not confirmed" if i % 2 else "other business") for i in range(60)]
    rows = deck.roll_rows("Layer B", ins, outs, 3.0)
    assert len(rows) > 1 and rows[0][0] == "Layer B" and all(r[0] == "Layer B (continued)" for r in rows[1:])
    for r in rows:
        assert len(deck.table_layout({"head": deck.ROLL_HEAD, "rows": [r], "widths": deck.ROLL_WIDTHS, "numeric": [False] * 3}, deck.CW, 3.0)["rows"]) == 1
    every = " ".join(c for r in rows for c in r[1:])
    assert all(re.search(rf"A rather long company name number {i}\b", every) for i in range(120))
    assert all(re.search(rf"Left out company {i}\b", every) for i in range(60))


# ---------- 2. the completeness gate ----------
def _table_slide(title, sub, rows, head=("Layer", "In its calculations", "Left out, and why")):
    s = Slide(title, sub)
    s.add("table", (deck.M, deck.TOP, deck.CW, 3.0), head=list(head), rows=rows, widths=[2.6, 4.7, 5.0])
    return s


def test_the_gate_fails_an_empty_table_page_a_gap_in_the_pages_and_a_count_the_rows_dont_make(caplog):
    sub = "3 layers with a listed company left out of the calculations: who is in, and why each of the others is not"
    a = _table_slide(deck.ROLL_TITLE + " (1 of 2)", sub, [["L1", "2 of 3: A, B", "1: other business: C"], ["L2", "1 of 2: D", "1: not confirmed: E"]])
    b = _table_slide(deck.ROLL_TITLE + " (2 of 2)", sub, [])                       # the live Retail deck's p.41: an empty table
    with caplog.at_level(logging.WARNING, logger="stratlab.deck"):
        lay = deck.layout_gate([a, b])
    whys = {(d["rule"], d["why"]) for d in lay["failed"]}
    assert ("layout", "a table page that prints no data row") in whys and ("layout", "a page with nothing on it") in whys
    assert ("reconcile", "says 3 layers, its pages show 2") in whys
    assert "says 3 layers, its pages show 2" in caplog.text
    gate = deck.with_layout({"items": [{"id": k, "label": lbl, "ok": True, "dropped": 0, "note": ""} for k, lbl in deck.GATE_ITEMS],
                             "dropped": [], "dropped_n": 0}, lay)
    items = {x["id"]: x for x in gate["items"]}
    assert not items["layout"]["ok"] and not items["reconcile"]["ok"] and items["reconcile"]["dropped"] == 1 and items["prose"]["ok"]
    # a missing page of a run, and a row printed twice
    c = _table_slide("Every company's figures (1 of 3)", "3 confirmed companies with figures, one row each", [["X", "1", "2"], ["X", "1", "2"]],
                     head=("Company", "Revenue", "Net"))
    d = _table_slide("Every company's figures (3 of 3)", "3 confirmed companies with figures, one row each", [["Y", "1", "2"]], head=("Company", "Revenue", "Net"))
    whys = {d_["why"] for d_ in deck.complete_flags([c, d])}
    assert "its pages run 1 of 3, 3 of 3" in whys and "a row printed twice" in whys
    # continued rows are one layer; a complete run passes
    ok = _table_slide(deck.ROLL_TITLE, "2 layers with a listed company left out", [["L1", "2 of 3: A, B", "1: other business: C"],
                                                                                  ["L1" + deck.ROLL_MORE, "F", ""], ["L2", "1 of 2: D", "1: not confirmed: E"]])
    assert deck.complete_flags([ok]) == []


def test_a_tampered_deck_fails_the_gate_and_the_built_deck_passes_it():
    region, m, f = retail_like(12, 5, 2)
    v, slides = deck_of(region, m, f)
    assert not [d for d in deck.complete_flags(slides)], deck.complete_flags(slides)
    tampered = copy.deepcopy(slides)
    page = next(s for s in tampered if s.title.startswith(deck.ROLL_TITLE))
    t = next(b for b in page.blocks if b["kind"] == "table")
    t["rows"] = t["rows"][:-1]                                                        # a layer dropped from the roll
    figs = next(s for s in tampered if s.title.startswith("Every company's figures"))
    next(b for b in figs.blocks if b["kind"] == "table")["rows"] = []                 # and a figures page emptied
    whys = [d["why"] for d in deck.complete_flags(tampered)]
    assert any(w.startswith("says 3 layers, its pages show 2") for w in whys), whys
    assert "a table page that prints no data row" in whys and any(w.startswith("says ") and "compan" in w for w in whys), whys


# ---------- 3. names and unfilled tokens ----------
def test_filing_tokens_double_spaces_and_trailing_commas_leave_every_name():
    for raw, want in (("Diodes Inc /del/", "Diodes Inc"), ("Acme Corp /DE/", "Acme Corp"), ("Foo Holdings \\DE\\", "Foo Holdings"),
                      ("Bar Co /NEW/", "Bar Co"), ("Baz Bank /MD/", "Baz Bank"), ("Quux  Ltd,", "Quux Ltd"), ("AC/DC Ltd", "AC/DC Ltd"),
                      ("I/O Systems", "I/O Systems")):
        assert deck.clean_name(raw) == want, raw
        assert deck.tidy_text(raw)[0] == want, raw
    assert deck.tidy_text("Diodes Inc /del/ is the largest at $3 bn.")[0] == "Diodes Inc is the largest at $3 bn."


def test_a_filed_name_with_a_token_reaches_no_slide():
    region, m, f = retail_like(6, 2, 1)
    sym = m["value_chain"][0]["companies"][0]["ticker"]
    m["value_chain"][0]["companies"][0]["name"] = "Tokenly Stores Inc /DE/"
    f[sym] = {**f[sym], "name": "Tokenly Stores Inc /DE/"}
    v, slides = deck_of(region, m, f)
    texts = [t for s in slides for t in deck.slide_texts(s)]
    assert any("Tokenly Stores" in t for t in texts) and not any("/DE/" in t for t in texts)
    assert not [d for d in slides[0].gate["dropped"] if d["why"].startswith("unfilled")]


def test_unfilled_tokens_anywhere_on_a_slide_fail_the_prose_item():
    for t in ("Revenue: None", "ROE nan%", "TBD", "Lorem ipsum dolor", "Hello {name}", "Acme /DE/", "NaN"):
        assert deck.token_flags(t), t
    for t in ("None of the companies has a figure.", "none is stored", "Nan Ya Plastics", "AC/DC", "Revenue ₹1,200 cr (5 of 7)"):
        assert deck.token_flags(t) == [], t
    region, m, f = retail_like(6, 2, 1)
    v, slides = deck_of(region, m, f)
    t = next(b for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table")
    t["rows"][0][1] = "TBD"
    gate = deck.publication_gate(slides, v)
    prose = next(x for x in gate["items"] if x["id"] == "prose")
    assert not prose["ok"] and any(d["text"] == "TBD" and d["why"].startswith("unfilled") for d in gate["dropped"])


# ---------- 4. a findings card of one long sentence ends whole ----------
def test_a_single_long_card_line_ends_on_a_whole_clause_never_an_ellipsis():
    line = ("Among layers of at least 5 companies with the figure, revenue grew fastest in the latest year in Regional and mid-sized lenders "
            "(larger) (median +5.6%, median return on equity 13.5%, 5 companies) and slowest in Large deposit-led universal lenders (median "
            "+4.1%, 13.1%, 7 companies), with the other layers between them in the table of every company's figures on the later pages.")
    box = (deck.M, deck.TOP, deck.CW, deck.BOT - deck.TOP)               # the findings page's cards
    items = deck.whole_lines([{"title": "Growth beside return", "lines": [line], "note": "p. 25"}] * 6, box, 3)
    got = items[0]["lines"][0]
    assert got != line and line.startswith(got[:-1]) and got.endswith(".") and not got.endswith("….")
    s = Slide("Key findings", "What the reported figures show")
    s.add("cards", box, cols=3, items=items, fill=True, size=13)
    assert not [x for x in deck.probe(s) if x["kind"] == "cut"]
    assert deck._shorter("Revenue grew most in Large lenders (median +9.1%, 6 companies) and least in Small lenders (+2%, 5 companies).") == \
        "Revenue grew most in Large lenders (median +9.1%, 6 companies)."
    assert deck._shorter("Median return on equity is highest in Regional lenders (13.5%) and lowest in Large lenders (13.1%), a gap of 0.4 points.") == \
        "Median return on equity is highest in Regional lenders (13.5%) and lowest in Large lenders (13.1%)."
    # never inside a layer's name, a bracket, or the first half
    assert deck._shorter("Median margin is highest in Chlor-alkali, soda ash and bulk inorganics among the layers of the theme.") is None
    assert deck._shorter("Short (a 5%, and b).") is None


# ---------- 5. the figures behind "not ranked" for capital needs ----------
def test_the_capital_per_revenue_figures_behind_not_ranked_are_on_the_value_chain_page(monkeypatch):
    from tests.test_r30_valid import HEAVY_LIGHT, _with_debt
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    fn, pbs = HEAVY_LIGHT["utilities"]
    region, m, f, market = _with_debt(fn, pbs)
    v, slides = deck_of(region, m, f, index_rows=lambda: market)
    ch = v["chain"]
    assert "threefold" in ch["line"] and ch["not_ranked"]
    note = deck.intensity_note(ch)
    rows = [r for r in ch["rows"] if r["layer"] in ch["not_ranked"] and r.get("intensity")]
    assert note.startswith("Capital for each unit of revenue (book equity plus debt") and "at most 3 times the lowest" in note
    for r in rows:
        assert f"{r['layer']} {r['intensity']:.2f}" in note
    hi, lo = max(r["intensity"] for r in rows), min(r["intensity"] for r in rows)
    assert f"{hi / lo:.1f} times" in note and hi / lo > 3
    page = next(s for s in slides if s.title.startswith("The value chain by layer"))
    assert any(note in p for b in page.blocks if b["kind"] == "text" for p in b["paras"])
    # ranked layers: no such note
    assert deck.intensity_note({"line": "Median EBITDA margin is highest in A", "rows": rows, "not_ranked": []}) == ""


# ---------- 6. advice words as advice only ----------
def test_buy_and_sell_are_advice_only_as_a_recommendation():
    for t in ("They earn mainly from turning metal they buy into pipes and tubes.", "It buys scrap and sells billets.",
              "It uses cash to buy raw materials.", "Accumulated losses exceed its equity.", "A sell-off hit the sector in March.",
              "The company sells steel and buys back shares through buybacks.", "Power generators sell electricity to the grid.",
              "It may sell the plant, its filing says."):
        assert deck.prose_flag(t) is None, t
    for t in ("Investors should sell the shares.", "Buy now.", "Analysts rate it a buy.", "Buy the stock on dips.", "Accumulate on dips.",
              "It is a strong buy.", "Time to sell."):
        assert (deck.prose_flag(t) or "").startswith("advice"), t


# ---------- 7. no dated update: one line that never gives way ----------
def test_with_no_dated_update_the_findings_say_so_in_a_line_that_stays(monkeypatch):
    from tests.test_r18_deck import bank_theme
    region, m, f = bank_theme()[:3]
    v, slides = deck_of(region, m, f)                           # six cards: the updates card of its own
    cards = next(b for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards")["items"]
    assert not any(s.title == deck.UPDATES_TITLE for s in slides)
    assert next(c for c in cards if c["title"] == deck.UPDATES_TITLE)["lines"] == ["No company meets the rules today."]
    # seven cards (a ranked return card too): the last two share one, and its "no dated update" line comes first, so it never gives way
    # (the live Private Banks deck's merged card had lost it)
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    v, slides = deck_of(region, m, f)
    cards = next(b for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards")["items"]
    card = cards[-1]
    # q1 (changed on purpose; the live R34 Private Banks card kept only the updates line, its coverage line given way): no dated update is
    # said in the title, the card's lines are the coverage summary
    assert len(cards) == 6 and card["title"] == "How far the figures go; no dated company update today"
    assert card["lines"][0].startswith("Considered 8 · confirmed 8") and not any("rules today" in ln for ln in card["lines"])


def test_one_company_listed_under_two_symbols_is_one_row_in_every_companys_figures():
    """R36 (GPT review of the live R33 Retail deck: "Leslie's, Inc." printed on two identical rows of the appendix)."""
    region, m, f = retail_like(12, 5, 2)
    first = m["value_chain"][0]["companies"][0]
    twin = {**copy.deepcopy(first), "ticker": first["ticker"] + "X"}           # live: the twin's market value differed
    m["value_chain"][0]["companies"].append(twin)
    f[twin["ticker"]] = copy.deepcopy(f[first["ticker"]])
    for k_ in ("market_cap", "cap"):
        if isinstance(f[twin["ticker"]], dict) and f[twin["ticker"]].get(k_):
            f[twin["ticker"]][k_] = f[twin["ticker"]][k_] * 0.7
    v, slides = deck_of(region, m, f)
    names = [r[0] for s in slides if s.title.startswith("Every company's figures")
             for b in s.blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict)]
    assert names and len(names) == len(set(names)), [n for n in names if names.count(n) > 1]
    assert not [d for d in deck.complete_flags(slides) if "twice" in d["why"]]
