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
            out += [str(x) for r in b.get("rows") or [] for x in r]
            out += [str(t) for it in b.get("items") or [] for t in (it if isinstance(it, tuple) else [it.get("title"), it.get("value"), *it.get("lines", [])])]
    return "\n".join(out)


def test_every_company_is_a_member_row_with_its_layer_figures_and_how_it_is_in():
    rows = view()["members"]
    assert [(r["symbol"], r["layer"]) for r in rows] == [("MINEA", "Mining"), ("MINEB", "Mining"), ("CELLA", "Cells"), ("CELLB", "Cells"),
                                                          ("RELIANCE", "Cells"), ("SCRAP", "Named in a sub-theme only")]
    by = {r["symbol"]: r for r in rows}
    assert (by["MINEA"]["revenue"], by["MINEA"]["ebitda"], by["MINEA"]["net"], by["MINEA"]["cap"]) == (1500, 50, 24.0, 1000.0)
    assert by["MINEA"]["by"] == "Official industry"
    assert by["CELLA"]["by"] == "Added, confirmed by its own words" and by["CELLB"]["by"] == "Added, not yet confirmed"
    assert by["SCRAP"]["revenue"] is None and by["SCRAP"]["by"] == "Added, not yet confirmed"       # no stored page: listed, with no figures


def test_the_theme_deck_has_the_cover_chain_layers_members_claims_and_notes():
    slides, footer = deck.theme_plan(view())
    titles = [s.title for s in slides]
    assert titles == ["Test theme", "The value chain", "What each layer does", "Every company in the theme", "Tailwinds and risks",
                      "Notes: confirmed and not yet confirmed"]
    assert slides[0].dark and slides[0].subtitle == "India (NSE and BSE) · Theme deep dive" and "Theme deep dive" in footer
    cover = dict(next(b for b in slides[0].blocks if b["kind"] == "stats")["items"])
    assert cover["Companies"] == "6" and cover["Layers"] == "2" and cover["AI additions confirmed"] == "2 of 4"
    assert cover["Prices as of"] == "05 Oct 2026"                         # the stored pages' price day (the as-of date)
    members = next(b for b in slides[3].blocks if b["kind"] == "table")
    assert members["head"] == deck.MEMBER_HEAD
    assert members["rows"][0] == ["Mine A", "Mining", "₹1,000 cr", "₹1,500 cr", "50.0%", "24.0%", "15.0%", "Official industry"]
    claims = next(b for b in slides[4].blocks if b["kind"] == "table")
    assert claims["rows"][0][:3] == ["Tailwind", "A battery subsidy", "Subsidy scheme extended (2026-09-01, A daily)"]
    assert claims["rows"][0][3]["url"] == "https://example.com/news/subsidy" and claims["rows"][1][2] == "General background"
    t = texts(slides)
    assert "2 of the 4 added are confirmed" in t and "2 not yet confirmed" in t and "1 couldn't be checked just now" in t
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


def test_the_theme_deck_is_a_real_powerpoint_and_a_real_pdf():
    from pptx import Presentation
    v = view()
    pp = deck.build_theme(v)
    prs = Presentation(io.BytesIO(pp))
    words = " ".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
    cells = " ".join(c.text for s in prs.slides for sh in s.shapes if sh.has_table for r in sh.table.rows for c in r.cells)
    assert len(prs.slides) == 6 and prs.core_properties.title == "Test theme: theme deep dive"
    assert "Test theme" in words and "Mine A" in cells and "Added, not yet confirmed" in cells
    pdf = deck.build_theme(v, pdf=True)
    assert pdf[:5] == b"%PDF-" and b"Test theme: theme deep dive" in pdf


def test_a_us_theme_deck_writes_dollars():
    v = {**view(), "region": "US", "unit": "$ million"}
    slides, _ = deck.theme_plan(v)
    assert slides[0].subtitle == "US · Theme deep dive"
    row = next(b for b in slides[3].blocks if b["kind"] == "table")["rows"][0]
    assert row[2] == "$1.00 bn" and row[3] == "$1.50 bn"


def test_the_deck_route_downloads_both_formats_as_one_deck_and_stops_at_the_plan_limit(api):
    from app.intel import routes
    routes_pf = routes.public_facts
    try:
        routes.public_facts = lambda region, sym: None
        r = api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:5] == b"%PDF-"
        assert r.headers["content-disposition"] == 'attachment; filename="stratlab-theme-ai-data-centers-us.pdf"'
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
