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
from tests.test_export import texts
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
    assert [t.title for t in b if t.title.startswith("Layer")][0].startswith("Layer 1 · Processors")


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
    assert cover["Companies"] == "18 confirmed, 2 not yet"
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
    line = D.margin_line({"stats": {"ebitda": {"median": 9.0}}, "left_out": 0, "stats_over": "own", "companies": [1]}, 15.0, whole=True)
    assert line == "The median EBITDA margin (9%) is 6 points below the median of the whole map (15%)."
    half = D.margin_line({"stats": {"ebitda": {"median": 16.5}}, "left_out": 0, "stats_over": "own", "companies": [1]}, 13.0, whole=True)
    assert "(16.5%) is 3.5 points above" in half


def test_the_highest_and_lowest_layer_are_named_when_every_layer_is_an_official_industry():
    v, slides = deck_of(*theme_a())
    chain = v["chain"]
    assert (chain["highest"], chain["lowest"]) == ("Film", "Converters") and chain["gap"] == 7.0
    cards = next(b for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards")["items"]
    where = next(c for c in cards if c["title"] == "Where the margin sits")["lines"][0]
    assert where == "Median EBITDA margin is highest in Film (19%) and lowest in Converters (12%), a gap of 7.0 points."
    assert "stands apart" not in texts(slides)
    _, sb = deck_of(*theme_b())                 # one layer: said so, nothing claimed
    assert "Fewer than two layers have 2 or more companies with an EBITDA margin, so no highest and lowest are named." in texts(sb)


def test_long_tables_keep_their_first_page_in_the_core_and_the_rest_in_the_appendix_with_its_page():
    v, slides = deck_of(*theme_a())
    titles = [s.title for s in slides]
    app = titles.index("Appendix")
    for base in ("Every company's figures", "The latest quarter against a year earlier"):
        assert base in titles[:app], base
        cont = [i for i, t in enumerate(titles) if t.startswith(f"{base}, continued")]
        assert cont and all(i > app for i in cont), base
        first = slides[titles.index(base)]
        rest = next(p for b in first.blocks if b["kind"] == "text" for p in b["paras"] if p.startswith("The rest of this table"))
        assert rest.endswith(f"appendix, p. {cont[0] + 1}.")
    assert not any(_re.search(r"\(\d+ of \d+\)$", t) and t.split(" (")[0] in deck.SPILL for t in titles)
    assert app <= 40                                                     # the core before the appendix stays short


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
        dc = [b for s in slides if s.title.startswith("Data confidence") for b in s.blocks if b["kind"] == "table" and b["head"][0] == "Companies"]
        rows = {r[0]: r[1] for r in dc[0]["rows"]}
        assert rows["Companies in the theme's list"] == str(v["placements"]["total"]) and "With a market value (the theme's total market value)" in rows
        each = next(r[2] for r in dc[0]["rows"] if r[0] == "In each median and total")
        assert _re.search(r"EBITDA margin \d+ · net margin \d+", each)


def test_industry_economics_is_computed_and_traceable():
    v, slides = deck_of(*theme_a())
    md = v["sections"]["margin_drivers"]
    assert md and abs(sum(x["part"] for x in md["layers"]) - md["change"]) < 0.1             # the parts add up to the change
    titles = [s.title for s in slides]
    for t in ("Industry economics", "Layers side by side", "What moved the aggregate margin", "Questions the figures raise"):
        assert t in titles, t
    q = next(b for s in slides if s.title == "Questions the figures raise" for b in s.blocks if b["kind"] == "cards")["items"][0]["lines"]
    assert any("on the quarter to Jun 2025" in x for x in q)                                    # the base quarter is stated
    assert any(x.startswith("Film has the highest median EBITDA margin") for x in q)
    t = texts([s for s in slides if s.eyebrow and "Industry economics" in s.eyebrow]).lower()
    for word in ("buy", "sell", "avoid", "attractive", "undervalued", "overvalued", "recommend", "target price"):
        assert not _re.search(rf"\b{word}\b", t), word
    # US, one layer, a loss-maker: the part still draws what exists, and the loss-maker has no P/E
    vb, sb = deck_of(*theme_b())
    side = next(b for s in sb if s.title == "Layers side by side" for b in s.blocks if b["kind"] == "table")
    assert side["rows"][0][0] == "Processors" and side["rows"][0][5].endswith("(2)")
