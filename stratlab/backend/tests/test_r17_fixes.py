"""Release 17 fixes: the business-update reader's year-ago column (a group's filing listing two companies' volumes; a table whose other
column is the month before), demergers from corporate-action filings, and the theme deck's layout and wording on synthetic themes."""
from app import biz_updates as B


# ---------- R17-005 (a): the year-ago figure is the year-ago column's ----------
def test_a_groups_filing_gives_each_company_its_own_year_ago_figure():
    # one line of the PDF's text holds both companies' rows under one pair of column headings (Tata Motors PV's and CV's volumes read
    # from one filing: both showed a year-ago 37,530, PV's)
    page = ("Tata Motors Group sales for October 2026\nCompany Oct-26 Oct-25\n"
            "Tata Motors Passenger Vehicles 45,120 37,530 Tata Motors Commercial Vehicles 32,004 30,118")
    quote = "Tata Motors Passenger Vehicles 45,120 37,530 Tata Motors Commercial Vehicles 32,004 30,118"
    for value, ai_prior, want in ((45120, 37530, 37530), (32004, 37530, 30118)):
        reply = {"period": "2026-10", "figures": [{"metric": "Total sales", "value": value, "unit": "units", "basis": "month", "prior": ai_prior,
                                                   "headline": True, "quote": quote, "page": 1}]}
        _, _, figs = B.clean_figures(reply, [page], "2026-11-01T12:00")
        assert (figs[0]["value"], figs[0]["prior"]) == (value, want)


def test_without_headings_the_row_befores_figure_is_not_this_ones():
    quote = "PV 45,120 37,530 CV 32,004 30,118"
    assert B.own_column(32004, 37530, quote, "no headings here", "2026-10") == (32004, None)
    assert B.own_column(32004, 30118, quote, "no headings here", "2026-10") == (32004, 30118)
    # prose: the year-ago figure after the value, months named in between, is kept
    prose = "sales with 672,790 units in September 2026 as against 541,064 units in September 2025."
    assert B.own_column(672790, 541064, prose, prose, "2026-09") == (672790, 541064)


def test_a_table_whose_other_column_is_the_month_before_gives_no_year_ago_figure():
    # Mahindra: 1,14,737 against 38,563, a column that wasn't the year before
    page = "Mahindra & Mahindra sales\nCategory Oct-26 Sep-26\nTotal 1,14,737 38,563"
    reply = {"period": "2026-10", "figures": [{"metric": "Total sales", "value": 114737, "unit": "units", "basis": "month", "prior": 38563,
                                               "headline": True, "quote": "Total 1,14,737 38,563", "page": 1}]}
    _, _, figs = B.clean_figures(reply, [page], "2026-11-01T12:00")
    assert (figs[0]["value"], figs[0]["prior"]) == (114737, None)
    # three columns, this month, the month before and the year before: the year-ago column's figure
    page3 = "Category Oct-26 Sep-26 Oct-25\nTotal 1,14,737 38,563 1,02,110"
    assert B.own_column(114737, 38563, "Total 1,14,737 38,563 1,02,110", page3, "2026-10") == (114737, 102110)
    page3b = "Category Oct-26 Oct-25 Sep-26\nTotal 1,14,737 1,02,110 38,563"
    assert B.own_column(114737, 38563, "Total 1,14,737 1,02,110 38,563", page3b, "2026-10") == (114737, 102110)


# ---------- R17-005 (b): a demerger from the stored corporate actions ----------
def test_a_demerger_in_the_stored_corporate_actions_breaks_the_series_even_without_a_revenue_jump():
    from tests.test_r16_deck import build
    from tests.test_theme1 import TODAY
    acts = {"MINEA": [{"kind": "demerger", "ex_date": "2025-10-14", "text": "Demerger"}, {"kind": "dividend", "ex_date": "2026-07-01"}],
            "MINEB": [{"kind": "dividend", "ex_date": "2025-08-01"}, {"kind": "demerger", "ex_date": "2019-01-01"}]}     # too long ago to matter
    out = build(corp_history=lambda s: acts.get(s, []))
    lead = {x["symbol"]: x for x in out["sections"]["leaders"]}
    assert lead["MINEA"]["sales_1y"] is None and lead["MINEB"]["sales_1y"] is not None
    assert [(x["symbol"], x.get("demerger")) for x in out["checks"]["series"]] == [("MINEA", "2025-10-14")]
    # a source that fails is no demerger, and no crash
    out = build(corp_history=lambda s: (_ for _ in ()).throw(RuntimeError("down")))
    assert out["checks"]["series"] == [] and TODAY


# ---------- R17-006 to R17-015: the theme deck, on synthetic themes of any sector ----------
# Theme A: an Indian manufacturing theme (packaging), three layers from the exchange's own industries, margins filed in whole points, a layer
# whose only companies' own words describe other work, many companies (long tables), quarters, no tailwinds or news.
# Theme B: a US services and financials theme (payments), one layer, loss-makers, most companies with no stored figures, no operating figures,
# no tailwinds. No figure or word here is tuned to any real sector.
import re as _re
from datetime import datetime as _dt, timezone as _tz

from app import deck
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests.test_export import table_of, texts
from tests.test_theme1 import TODAY, facts

NOW = _dt(2026, 10, 5, 6, 0, tzinfo=_tz.utc)
LIST = {"base": True, "basis": "industry", "verified": None}


def _co(sym, name, what, **kw):
    return {"name": name, "ticker": sym, "what": what, **LIST, **kw}


def theme_a():
    film = [_co(f"FILM{i}", f"Film {i} Ltd", "makes plastic film for packaging") for i in range(4)]
    film[0]["what"] = "The Company was established in 1981"                       # says nothing of the work: the industry stands
    conv = [_co(f"CONV{i:02d}", f"Converter {i} Ltd", "converts film into pouches and cartons") for i in range(14)]
    mach = [_co("MACH1", "Machine One Ltd", "supplies software to insurance companies"), _co("MACH2", "Machine Two Ltd", "provides staffing services")]
    m = {"sector": "Packaging", "summary": "Film, converters and machines.",
         "value_chain": [{"layer": "Film", "description": "Makes the plastic film.", "official": True, "companies": film},
                         {"layer": "Converters", "description": "Turn film into pouches, cartons and labels.", "official": True, "companies": conv},
                         {"layer": "Machinery", "description": "Builds packaging machines.", "official": True, "companies": mach}],
         "sub_themes": [], "tailwinds": [], "risks": [],
         "placements": {"checked": True, "pending": 0, "placed": 20, "total": 20, "base": 20, "named": 0, "added": 0, "confirmed": 0}}
    f = {}
    for i, c in enumerate(film):
        f[c["ticker"]] = facts(c["ticker"], c["name"], [1000, 1100, 1200, 1300 + i * 10], [20, 20, 19, 18 + (i % 2) * 2], [100, 110, 120, 130], cap=30000 - i * 1000,
                               latest_yoy={"of": "Jun 2026 vs Jun 2025", "sales": 5.0 + i, "profit": 3.0, "basis": "quarter"})
    for i, c in enumerate(conv):
        f[c["ticker"]] = facts(c["ticker"], c["name"], [500, 520, 560, 600 + i * 5], [12, 12, 11, 12], [30, 31, 32, 30 + i], cap=8000 - i * 100,
                               latest_yoy={"of": "Jun 2026 vs Jun 2025", "sales": -2.0 + i, "profit": 1.0, "basis": "quarter"})
    for c in mach:
        f[c["ticker"]] = facts(c["ticker"], c["name"], [200, 210, 220, 230], [30, 30, 30, 30], [40, 40, 40, 40], cap=5000)
    return "IN", m, f


def theme_b():
    procs = [_co(f"PAY{i}", f"Pay {i} Inc", "operates card payment networks") for i in range(10)]
    m = {"sector": "Payments", "summary": "Card networks and processors.",
         "value_chain": [{"layer": "Processors", "description": "Run card payment networks.", "companies": procs}], "sub_themes": [], "tailwinds": [], "risks": [],
         "placements": {"checked": True, "pending": 0, "placed": 10, "total": 10, "base": 10, "named": 0, "added": 0, "confirmed": 0}}
    f = {}
    for i, (sales, opm, prof) in enumerate([([900, 1000, 1100, 1250], [35.4, 36.1, 34.8, 33.9], [200, 220, 240, 260]),
                                            ([400, 380, 350, 330], [-5.2, -8.1, -9.4, -12.3], [-60, -80, -90, -110]),     # a loss-maker
                                            ([300, 330, 360, 420], [22.5, 23.1, 24.0, 26.4], [40, 45, 50, 64])]):
        f[f"PAY{i}"] = {**facts(f"PAY{i}", f"Pay {i} Inc", sales, opm, prof, cap=90000 // (i + 1), pe=None if prof[-1] < 0 else 25.0 + i, industry=("Payments",)),
                        "region": "US", "unit": "$ million"}
    return "US", m, f


def deck_of(region, m, f, **kw):
    dive = D.build(region, m["sector"], m, D.Sources(TODAY, facts=f.get, **kw))
    v = T.deck_view(region, m, dive)
    return v, deck.theme_plan(v, now=NOW)[0]


def test_a_layer_whose_companies_are_all_not_confirmed_gets_no_slide_and_the_layers_renumber():
    v, slides = deck_of(*theme_a())
    titles = [s.title for s in slides]
    assert not any("Machinery" in t for t in titles if t.startswith("Layer"))
    assert any(t.startswith("Layer 1 · Film") for t in titles) and any(t.startswith("Layer 2 · Converters") for t in titles)
    assert not any(t.startswith("Layer 3") for t in titles)
    assert "No slide for Machinery: none of its companies is confirmed by its own description." in texts(slides)
    _, b = deck_of(*theme_b())
    # changed on purpose (R18): one layer is nothing to set side by side, so no layer slide and no value chain
    assert not [t.title for t in b if t.title.startswith("Layer")] and "The value chain by layer" not in [t.title for t in b]


def test_membership_reads_the_layers_own_words_and_a_sentence_that_says_nothing_of_the_work_leaves_the_industry_standing():
    region, m, f = theme_a()
    v, slides = deck_of(region, m, f)
    assert v["status"]["FILM0"] == "core"                          # "established in 1981"
    assert v["status"]["MACH1"] == "unverified" and v["status"]["MACH2"] == "unverified"
    words = D.theme_words({"value_chain": [{"layer": "Heavy vehicles", "description": "Trucks and buses for haulage."}]}, "Any theme")
    assert D.membership({**LIST, "what": "The company manufactures trucks and buses"}, words) == "core"      # the layer's description, not its name
    assert v["membership"] == {"placed": 20, "confirmed": 18, "not_confirmed": 2}
    t = texts(slides)
    assert "20 in the exchange's industry list; 18 confirmed by their own description, 2 not yet" in t       # p2 and data confidence
    cover = dict((it[0], it[2] if len(it) > 2 else None) for b in slides[0].blocks if b["kind"] == "stats" for it in b["items"])
    assert cover["Companies"] == "in the exchange's industries; 2 not confirmed"          # R20: the universe's one wording, with what isn't confirmed
    # US, most companies with no stored figures: the counts are of every company checked, with figures or not
    vb, sb = deck_of(*theme_b())
    assert vb["membership"]["placed"] == 10 and "10 in the exchange's industry list; 10 confirmed by their own description, 0 not yet" in texts(sb)


def test_whole_points_print_whole_and_a_layers_half_stays():
    v, slides = deck_of(*theme_a())
    film = next(s for s in slides if s.title.startswith("Layer 1 · Film"))
    conv = next(s for s in slides if s.title.startswith("Layer 2 · Converters"))
    for s in (film, conv):
        assert not _re.search(r"\b\d+\.0%", s.subtitle or ""), s.subtitle
        assert not _re.search(r"\b\d+\.0 points", s.subtitle or ""), s.subtitle
    # changed on purpose (R27): the whole map's median is in no table, so no layer sentence quotes it (the deck check dropped it)
    line = D.margin_line({"stats": {"ebitda": {"median": 9.0}}, "left_out": 0, "stats_over": "own", "companies": [1]}, 15.0, whole=True)
    assert line is None
    assert "whole map" not in texts(slides)


def test_the_highest_and_lowest_layer_are_named_when_every_layer_is_an_official_industry(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    v, slides = deck_of(*theme_a())
    chain = v["chain"]
    assert (chain["highest"], chain["lowest"]) == ("Film", "Converters") and chain["gap"] == 7.0
    cards = next(b for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards")["items"]
    where = next(c for c in cards if c["title"] == "Where the margin sits")["lines"][0]
    # R18: whole figures print whole; R22: a highest or lowest median on 4 companies or fewer says its count
    assert where == "Median EBITDA margin is highest in Film (19%, 4 companies) and lowest in Converters (12%), a gap of 7 points."
    assert "stands apart" not in texts(slides)
    _, sb = deck_of(*theme_b())                 # one layer: nothing claimed and (R18, changed on purpose) nothing said about it
    assert "Fewer than two layers" not in texts(sb) and not any(c["title"] == "Where the margin sits" for s in sb if s.title == "Key findings"
                                                               for b in s.blocks if b["kind"] == "cards" for c in b["items"])


def test_long_tables_keep_their_first_page_in_the_core_and_the_rest_in_the_appendix_with_its_page():
    v, slides = deck_of(*theme_a())
    titles = [s.title for s in slides]
    app = next(i for i, s in enumerate(slides) if s.title.startswith("Every company's figures"))
    # changed on purpose (R18, then R19, the owner: "keep the important ones not everything"): the appendix is one table of every confirmed
    # company's figures; a long layer keeps its largest companies on its one page and points there; nothing is "continued"
    assert all(t.startswith("Every company's figures") for t in titles[app:])
    assert not any("continued" in t or "all companies" in t for t in titles)
    conv = next(s for s in slides if s.title == "Layer 2 · Converters")
    assert any(p.endswith(f"every one: appendix, p. {app + 1}.") for b in conv.blocks for p in b.get("paras") or [])


def test_no_divider_without_anything_after_it_and_every_total_says_its_count():
    for theme in (theme_a(), theme_b()):
        v, slides = deck_of(*theme)
        titles = [s.title for s in slides]
        assert "Tailwinds, risks and news" not in titles                # no tailwinds, risks, news or listings
        for i, s in enumerate(slides):
            if s.kind == "section" and s.title != "Appendix":
                assert i + 1 < len(slides) and slides[i + 1].kind != "section", s.title
        size = next(s for s in slides if s.title == "Size and shape")
        assert _re.search(r"\(\d+ compan(y|ies) with figures and a market value\)|\d+ compan(y|ies) with figures and a market value", size.subtitle)
        # changed on purpose (R19): data confidence is one page, its counts one line under the checks
        assert [s.title for s in slides if s.title.startswith("Data confidence")] == ["Data confidence"]
        line = next(p for s in slides if s.title == "Data confidence" for b in s.blocks for p in b.get("paras") or [] if p.startswith("Counts:"))
        # R27: the four reconciled counts lead the line, then the universe against the figures in the one wording
        assert line.startswith(f"Counts: {deck.counts_words(deck.reconciled_counts(v, deck.coverage(v)))}. {deck.coverage(v)['line']};") and "with a market value (the theme's total market value)" in line   # R20: one wording
        assert _re.search(r"in each calculation: EBITDA margin \d+, net margin \d+", line)       # R27: one list of each calculation's count


def test_industry_economics_is_computed_and_traceable(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    v, slides = deck_of(*theme_a())
    md = v["sections"]["margin_drivers"]
    assert md and abs(sum(x["part"] for x in md["layers"]) - md["change"]) < 0.1             # the parts add up to the change
    titles = [s.title for s in slides]
    for t in ("Layers side by side", "What moved the aggregate margin"):
        assert t in titles, t
    assert "Industry economics" in [r[0] for r in table_of(slides, "Contents")["rows"]]          # R18: a part on the contents page, no divider
    # the questions sit under a table of the part when they fit, so no page is half empty
    q = next(it for s in slides for b in s.blocks if b["kind"] == "cards" for it in b["items"] if it.get("title") == "Questions the figures raise")["lines"]
    assert any("on the quarter to Jun 2025" in x for x in q)                                    # the base quarter is stated
    assert any(x.startswith("Film has the highest median EBITDA margin") for x in q)
    t = texts([s for s in slides if s.eyebrow and "Industry economics" in s.eyebrow]).lower()
    for word in ("buy", "sell", "avoid", "attractive", "undervalued", "overvalued", "recommend", "target price"):
        assert not _re.search(rf"\b{word}\b", t), word
    # US, one layer, a loss-maker: what moved the margin is still worked out, the loss-maker's part too; changed on purpose (R18): with one
    # layer there is no industry economics part at all
    vb, sb = deck_of(*theme_b())
    assert "Layers side by side" not in [s.title for s in sb] and "What moved the aggregate margin" not in [s.title for s in sb]
    parts = {x["symbol"]: x["part"] for x in vb["sections"]["margin_drivers"]["companies"]}
    assert set(parts) == {"PAY0", "PAY1", "PAY2"} and abs(sum(parts.values()) - vb["sections"]["margin_drivers"]["change"]) < 0.1
