"""EXPORT (4 Nov): the theme deep dive's deck, PowerPoint and PDF, made by the deep dive's own deck builder, and counted against the same
monthly decks. The tables' CSVs are made in the browser (frontend/src/lib/csv.ts, unit/export.test.mjs)."""
import io

from app import deck
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests.test_research_api import api  # noqa: F401  (the research API on the fake sources)
from tests.test_theme1 import CHECKED, src

MAP = {**CHECKED, "summary": "Mining the ore and making the cells.",
       "value_chain": [{**v, "companies": [{**c, "base": i == 0, "basis": "industry" if i == 0 else "added", "verified": c["ticker"] != "CELLB", "cap": 1000.0 * (k + 1)}
                                           for k, c in enumerate(v["companies"])]} for i, v in enumerate(CHECKED["value_chain"])],
       "sub_themes": [{"name": "Recycling", "detail": "", "companies": [{"name": "Scrap Co", "ticker": "SCRAP", "base": False, "verified": False}]}],
       "tailwinds": [{"text": "A battery subsidy", "status": "current",
                      "source": {"headline": "Subsidy scheme extended", "at": "2026-09-01", "outlet": "A daily", "url": "https://example.com/news/subsidy"}}],
       "risks": [{"text": "Ore prices swing", "status": "general", "source": None}],
       "placements": {"checked": True, "pending": 0, "placed": 5, "total": 6, "base": 2, "named": 0, "added": 4, "confirmed": 2, "timed_out": 1}}


def view():
    dive = D.build("IN", "Test theme", MAP, src())
    return T.deck_view("IN", MAP, dive)


def texts(slides):
    out = []
    for s in slides:
        out += [s.title, s.subtitle or ""]
        for b in s.blocks:
            out += [str(x) for x in b.get("paras") or []]
            out += [str(x) for r in b.get("rows") or [] for x in ([r["group"]] if isinstance(r, dict) else r)]
            out += [str(t) for it in b.get("items") or [] for t in (it if isinstance(it, tuple) else
                                                                    [it.get("title"), it.get("value"), it.get("text"), it.get("sub"), it.get("note"), *it.get("lines", [])])]
            out += [str(x) for x in b.get("cats") or []] + [b.get("title") or ""]
    return "\n".join(out)


def test_every_company_is_a_member_row_with_its_layer_figures_and_how_it_is_in():
    rows = view()["members"]
    assert [(r["symbol"], r["layer"]) for r in rows] == [("MINEA", "Mining"), ("MINEB", "Mining"), ("CELLA", "Cells"), ("CELLB", "Cells"),
                                                          ("RELIANCE", "Cells"), ("SCRAP", "Other test theme companies")]      # lane d1: in "Other", never in no layer (updated on purpose)
    by = {r["symbol"]: r for r in rows}
    # LIVE6-006 (updated on purpose): the market value is the dive's, on its one price date, as the page shows it
    assert (by["MINEA"]["revenue"], by["MINEA"]["ebitda"], by["MINEA"]["net"], by["MINEA"]["cap"]) == (1500, 50, 24.0, 40000.0)
    assert by["MINEA"]["by"] == "Official industry"
    assert by["CELLA"]["by"] == "Added, confirmed by its own words" and by["CELLB"]["by"] == "Added, not yet confirmed"
    assert by["SCRAP"]["revenue"] is None and by["SCRAP"]["by"] == "Added, not yet confirmed"       # no stored page: listed, with no figures


def table_of(slides, title):
    return next(b for s in slides if s.title.startswith(title) for b in s.blocks if b["kind"] == "table")


def plain(rows):
    return [r for r in rows if not isinstance(r, dict)]


def test_the_theme_deck_has_the_cover_chain_layers_members_claims_and_notes():
    """DECK (5 Nov): the deck follows the page part by part: each part opens with a section slide, each layer has its own slide."""
    slides, footer = deck.theme_plan(view())
    titles = [s.title for s in slides]
    # R16 (owner, 7 Nov): changed on purpose; findings up front (key findings, data confidence, dated company updates), the companies' figures in the
    # core, every company's own words in the appendix; the cover counts the companies the figures are for instead of the AI's additions
    # R17 (owner, 7 Nov): changed on purpose; data confidence carries the table of counts each total is of (under the checks, or on a page of
    # its own when it doesn't fit), and the Industry economics part follows the value chain
    # R18 (owner, 7 Nov: the core ran 41 pages): changed on purpose; one contents page in place of a divider before each part, each layer on one
    # page, every company's figures in the appendix
    # R19 (owner, 7 Nov: "just keep the important ones not everything"): changed on purpose; no overview page (its words are in the notes), no
    # "Dated company updates" when no company meets the rules, no page for a part with nothing important (an empty sub-theme, margins over time, the
    # balance sheet when it shows nothing), the notes on one page and the appendix one table of every confirmed company's figures
    assert titles == ["Test theme", "Contents", "Key findings", "Data confidence",
                      "The value chain by layer", "Smaller layers", "Layers side by side", "What moved the aggregate margin",       # lane d1: two layers of 2 confirmed companies, one page (updated on purpose)
                      "Tailwinds and risks", "Size and shape", "Growth and profitability", "Valuation", "Price", "How to read this deck",
                      "How the figures are built", "Every company's figures"]       # R25: changed on purpose, the figures' notes before the appendix
    assert slides[0].kind == "cover" and slides[0].subtitle == "India (NSE and BSE) · Theme deep dive" and "Theme deep dive" in footer
    assert not [s for s in slides if s.kind == "section"]
    contents = table_of(slides, "Contents")["rows"]
    assert [(r[0], r[2]) for r in contents[:2]] == [("Findings", "3"), ("The value chain", "5")]          # each part with its first page
    assert contents[-1][0] == "Appendix" and contents[-1][2] == "16"            # R25: one page later (the figures' notes); lane d1: one layer page fewer (updated on purpose)
    assert contents[-2][0] == "How the figures are built" and contents[-2][2] == "15"
    cover = dict((t[0], t[1]) for t in next(b for b in slides[0].blocks if b["kind"] == "stats")["items"])
    # R28: changed on purpose, "with figures" is of the confirmed companies (CELLB, not confirmed, has figures but is never in them)
    assert cover["Companies"] == "6" and cover["Layers"] == "2" and cover["With figures"] == "4"          # R20: its share and the universe beneath
    figs = table_of(slides, "Every company's figures")
    assert figs["head"][:3] == ["Company", "Layer", "Market value"] and figs["rows"][1][:3] == ["Mine A", "Mining", "₹40,000 cr"]
    # changed on purpose (lane t1, LIVE7A-014): a whole figure keeps ".0" in a column where another figure has a decimal (one precision a column)
    row = table_of(slides, deck.SMALL_TITLE)["rows"][0][1:]          # lane d1: a layer of 2 is rows of "Smaller layers" (updated on purpose)
    assert row[0] == "Mine A" and row[2:4] == ["₹1,500 cr", "50%"] and row[4] in ("24%", "24.0%") and row[5] in ("15%", "15.0%") and row[6] == "Mar 2026"   # R16: whole points as filed
    claims = next(b for s in slides if s.title == "Tailwinds and risks" for b in s.blocks if b["kind"] == "flow")["items"]
    assert claims[0]["text"] == "A battery subsidy" and [t[0] for t in claims[0]["tags"]] == ["Tailwind", "Dated source"]   # R16: "Checked" meant only that a headline exists
    assert claims[0]["sub"] == "Subsidy scheme extended · 01 Sep 2026 · A daily" and claims[0]["url"] == "https://example.com/news/subsidy"
    assert [t[0] for t in claims[1]["tags"]] == ["Risk", "General background (AI, no dated source)"] and claims[1]["sub"] is None
    t = texts(slides)
    assert "2 of the 4 added are confirmed by their own description; 2 not yet." in t and "1 couldn't be checked just now" in t
    assert "Not investment advice." in t
    for word in ("buy", "sell", "target price", "recommend"):
        assert word not in t.lower().replace("subsidy", "")


def test_a_long_member_list_runs_over_slides_and_no_row_is_dropped():
    long = [[f"Company with a rather long registered name number {i}", "A layer with a long name", "₹1,000 cr", "₹2,000 cr", "10.0%", "5.0%", "8.0%",
             "Added, not yet confirmed"] for i in range(61)]
    pages = deck.table_pages(deck.MEMBER_HEAD, long, deck.MEMBER_WIDTHS, deck.W_IN - 2 * deck.M, 4.85)
    assert sum(len(p) for p in pages) == 61 and len(pages) > 4
    for p in pages:          # each page's table keeps every row it was given
        assert len(deck.table_layout({"head": deck.MEMBER_HEAD, "rows": p, "widths": deck.MEMBER_WIDTHS}, deck.W_IN - 2 * deck.M, 4.85)["rows"]) == len(p)


def test_evening_out_pages_with_tall_rows_ends_and_drops_no_row():
    """R15 (owner, 7 Nov: "my pdf still isn't downloaded"): two tall rows between short ones made the evened pages end short again, and
    table_pages asked for the same number of rows a page forever: 5 minutes, then a RecursionError and no file. Now it ends at once."""
    import time

    def row(i, n):
        return [f"Company {i} Ltd (C{i})", "Auto parts", "₹1,000 cr", "“" + " ".join(["wheel"] * n) + "”", "Added, not yet confirmed"]
    rows = [row(i, 100 if i in (2, 3) else 1) for i in range(5)]
    t = time.time()
    pages = deck.table_pages(deck.MEMBER_HEAD, rows, deck.MEMBER_WIDTHS, deck.W_IN - 2 * deck.M, deck.BOT - deck.TOP - 0.35, most=16)
    assert time.time() - t < 5
    assert [r for p in pages for r in p] == rows


def test_the_theme_deck_is_a_real_powerpoint_and_a_real_pdf():
    from pptx import Presentation
    v = view()
    pp = deck.build_theme(v)
    prs = Presentation(io.BytesIO(pp))
    words = " ".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
    cells = " ".join(c.text for s in prs.slides for sh in s.shapes if sh.has_table for r in sh.table.rows for c in r.cells)
    assert len(prs.slides) == len(deck.theme_plan(v)[0]) and prs.core_properties.title == "Test theme: theme deep dive"
    assert "Test theme" in words and "Mine A" in cells and "Mining" in cells
    pdf = deck.build_theme(v, pdf=True)
    assert pdf[:5] == b"%PDF-" and b"Test theme: theme deep dive" in pdf


def test_a_us_theme_deck_writes_dollars():
    v = {**view(), "region": "US", "unit": "$ million"}
    slides, _ = deck.theme_plan(v)
    assert slides[0].subtitle == "US · Theme deep dive"
    assert table_of(slides, "Every company's figures")["rows"][1][2] == "$40 bn"
    assert table_of(slides, deck.SMALL_TITLE)["rows"][0][3] == "$1.50 bn"          # lane d1: the layer of 2 is rows of "Smaller layers" (updated on purpose)


def test_the_deck_route_downloads_both_formats_as_one_deck_and_stops_at_the_plan_limit(api):
    from app.intel import routes
    routes_pf = routes.public_facts
    try:
        routes.public_facts = lambda region, sym: None
        r = api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:5] == b"%PDF-"
        from datetime import datetime
        from app.intel import theme_routes
        day = datetime.now(routes.IST).date()
        # R15: the name people see in Downloads, as the page names it (lib/deckName.ts), not "stratlab-theme-ai-data-centers-us.pdf"
        assert r.headers["content-disposition"] == f'attachment; filename="StratLab - AI data centers theme (US) - {day.day} {day:%b %Y}.pdf"'
        built = []
        real_build = deck.build_theme_gated               # R27: the route builds through the gate (the deck and its check's result)
        deck.build_theme_gated = lambda v, pdf=False: built.append(pdf) or real_build(v, pdf)
        try:                                                                           # the same file again today: sent from the kept copy
            again = api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf")
        finally:
            deck.build_theme_gated = real_build
        assert again.status_code == 200 and again.content == r.content and built == [] and len(theme_routes.DECK_CACHE._d) >= 1
        # R20: the file is in the shared store too: after a restart (the process's copy gone) it is sent again without a rebuild
        theme_routes.DECK_CACHE._d.clear()
        deck.build_theme_gated = lambda v, pdf=False: built.append(pdf) or real_build(v, pdf)
        try:
            restarted = api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf")
        finally:
            deck.build_theme_gated = real_build
        assert restarted.status_code == 200 and restarted.content == r.content and built == []
        assert api.usage.count("deck") == 1 and "deck:theme:US:ai-data-centers" in api.usage
        r = api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pptx")      # the same theme's other format: free
        assert r.status_code == 200 and r.content[:2] == b"PK" and r.headers["content-disposition"].endswith('.pptx"')
        assert api.usage.count("deck") == 1
        r = api.get("/research/theme-dive/deck?q=AI%20chips&region=US&format=pdf")                # Free: one deck a month
        assert r.status_code == 402 and r.json()["detail"]["code"] == "deck_limit"
        msg = r.json()["detail"]["message"]
        assert msg.startswith("You've made 1 slide deck this month.") and "A company's or a theme's PDF and PowerPoint count as one deck" in msg
        import pytest
        from fastapi import HTTPException
        from app import main
        with pytest.raises(HTTPException) as e:                                                    # a company's deck shares the count
            main.check_deep({"id": "u1", "_plan": "free", "plan": "free"}, "deck", "TCS", "IN")
        assert e.value.status_code == 402
        assert api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=doc").status_code == 400
    finally:
        routes.public_facts = routes_pf
