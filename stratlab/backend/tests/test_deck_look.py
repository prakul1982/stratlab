"""DECK (owner, 5 Nov: "this is shite can you make it better; all the decks we are giving are not so good looking, their themes and all;
also it doesn't contain everything there is on the page about the theme"). The theme deck carries every part of the theme's page; both
decks share the app's look; no slide has text under 11 pt, a block over another, a block off the slide or a table that drops a row."""
import copy
import io

from app import deck
from tests.test_export import plain, table_of, texts, view
from tests.test_investor import view_for_deck

BIZ = {"symbol": "MINEA", "name": "Mine A", "metric": "Ore dispatched", "unit": "tonnes", "span": "month", "period": "2026-09", "value": 123456,
       "prev": 120000, "year_ago": 110000, "change_prev": 2.9, "change_year": 12.2, "filed": "2026-10-03", "url": "https://example.com/f/1", "page": 2,
       "exchange": "NSE", "points": []}


def full_view() -> dict:
    """The fixture theme with every part of the page filled: the parts the page reads on its own (news, listings, prices, business
    updates) and the sections the fixture's stored pages leave empty (ownership, events, management, the latest quarter)."""
    v = copy.deepcopy(view())
    v.update(core="ore turned into cells", etfs=[{"ticker": "BATT", "name": "A battery fund"}],
             news=[{"at": "2026-10-04", "headline": "Mine A ships record ore", "company": "Mine A", "source": "Exchange filing", "url": "https://example.com/n/1"}],
             listings=[{"id": "i1", "name": "New Cells Ltd", "symbol": "NEWC", "stage": "open", "open": "2026-10-10", "close": None, "listing": None,
                        "groups": ["Cells"], "what": "makes lithium cells"}],
             prices={"companies": [{"symbol": "MINEA", "ret": {"1M": 2.0, "3M": 5.0, "1Y": 20.0, "3Y": 40.0}}], "benchmark": "Nifty 50",
                     "median": {"1M": {"median": 2.0, "n": 1}, "3M": {"median": 5.0, "n": 1}, "1Y": {"median": 20.0, "n": 1}, "3Y": None},
                     "returns": {"1M": {"theme": 2.0, "bench": 1.0}, "3M": {"theme": 5.0, "bench": 3.0}, "1Y": {"theme": 20.0, "bench": 10.0}, "3Y": {"theme": None, "bench": None}},
                     "above200": {"n": 5, "count": 4, "share": 80.0}, "line": {"weeks": ["2026-09-01", "2026-09-08", "2026-09-15"], "theme": [100, 102, 104],
                                                                              "bench": [100, 101, 101.5], "rs": [100, 101, 102.5]}},
             business={"allowed": True, "layers": [{"layer": "Mining", "rows": [BIZ]}], "subs": []})
    sec = v["sections"]
    sec["quarter"] = {"companies": [{"symbol": "MINEA", "name": "Mine A", "of": "Jun 2026", "sales": 12.0, "profit": 8.0},
                                    {"symbol": "CELLA", "name": "Cell A", "of": "Jun 2026", "sales": -3.0, "profit": -9.0}],
                      "sales_up": 1, "sales_down": 1, "profit_up": 1, "profit_down": 1, "sales": {"n": 2, "median": 4.5, "min": -3, "max": 12}, "profit": None}
    sec["ownership"] = {"holdings": [{"symbol": "MINEA", "name": "Mine A", "quarter": "Sep 2026", "promoter": 55.0, "institutions": 20.0, "promoter_change": 0.5,
                                      "institutions_change": -0.2}], "promoter_up": 1, "promoter_down": 0, "promoter_median": None,
                        "insider_buys": [{"symbol": "MINEB", "name": "Mine B", "at": "2026-09-20"}],
                        "pledges": [], "red_flags": [{"symbol": "CELLB", "name": "Cell B", "at": "2026-09-12", "label": "Auditor resigned", "url": "https://example.com/r/1"}]}
    sec["events"] = {"results_due": [{"symbol": "MINEA", "name": "Mine A", "date": "2026-10-20", "purpose": "Quarterly results"}],
                     "results_filed": [{"symbol": "CELLA", "name": "Cell A", "date": "2026-09-30", "numbers": [{"label": "Revenue", "value": "₹800 cr"}], "url": None}],
                     "actions": [{"symbol": "MINEB", "name": "Mine B", "date": "2026-10-15", "kind": "dividend", "label": "Dividend", "text": "₹5 a share"}]}
    sec["management"] = {"companies": [{"symbol": "MINEA", "name": "Mine A", "met": 3, "missed": 1}], "met": 3, "missed": 1, "with_card": 1}
    sec["valuation"]["history"] = [{"d": "2026-09-01", "pe": 18.0, "n": 5}, {"d": "2026-09-08", "pe": 18.5, "n": 5}]
    return v


def test_the_theme_deck_carries_every_part_of_the_page():
    """Each card of the theme page that carries something important has its slide (R19, the owner: "just keep the important ones not
    everything"): the per-company lists (members in their own words, headlines, listings, ownership, events, management) stay on the page."""
    v = full_view()
    slides, _ = deck.theme_plan(v)
    titles = [s.title for s in slides]
    page = ["Contents", "Key findings", "Data confidence", "Dated company updates",
            "The value chain by layer",                 # ChainCard
            *[f"Layer {i + 1} · {x['layer']}" for i, x in enumerate(v["layers"])],      # LayerCard, every layer with companies
            # (operating figures: one company files them in this fixture, under 3: a line in data confidence, no page, R21)
            "Tailwinds and risks",                      # ClaimsCard
            "Size and shape", "Growth and profitability", "Valuation", "The latest quarter against a year earlier",       # NumbersCards
            "How to read this deck",                    # the page's notes
            "Every company's figures"]                  # LeadersCard: the appendix
    for t in page:
        assert t in titles, t
    for gone in ("The theme at a glance", "Every company in this theme", "Latest on this theme", "New listings in the theme", "Margins over time",
                 "Ownership", "Events", "Management report cards"):
        assert gone not in titles, gone
    words = texts(slides)
    for must in ("ore turned into cells", "BATT", "Digs it out.", "Makes cells.", "Subsidy scheme extended", "filed operating figures between results",
                 "Resignation of an auditor", "Quarterly results",          # changed on purpose (m2): the event as a neutral fact "Written by AI from general knowledge"):
        assert must in words, must
    lead = [r[0].removesuffix(" (whole company)") for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table" for r in b["rows"]]
    assert sorted(lead) == sorted(x["name"] for x in v["sections"]["leaders"] if v["status"].get(x["symbol"]) != "unverified")      # confirmed, once each
    notes = texts([s for s in slides if s.title == "How to read this deck"])
    assert "Not read when this deck was made" not in notes and "On the theme's page: the latest headlines and new listings" in notes


def test_a_part_the_page_has_nothing_for_is_said_once_never_drawn_empty():
    v = view()
    v["layers"] = v["layers"] + [{"layer": "Recycling", "description": "Melts it down.", "companies": [], "n": 0, "stats": {}, "company_wide": []}]
    v["chain"] = {**v["chain"], "rows": v["chain"]["rows"] + [{"layer": "Recycling", "n": 0, "revenue": None, "ebitda": None, "net": None, "roce": None}]}
    slides, _ = deck.theme_plan(v)
    words = texts(slides)
    assert not any("Recycling" in s.title for s in slides)                                    # no slide (or card) for a layer with no company
    assert "0 companies" not in words and "0 company" not in words
    assert words.count("No listed company is shown for Recycling") == 1
    assert "Recycling" not in [r[0] for r in table_of(slides, "The value chain by layer")["rows"]]
    notes = texts([s for s in slides if s.title == "How to read this deck"])
    assert "On the theme's page: the latest headlines and new listings" in notes       # R16: no internal wording ("when this deck was made")


def boxes_overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax + aw > bx + 0.01 and bx + bw > ax + 0.01 and ay + ah > by + 0.01 and by + bh > ay + 0.01


def decks():
    long = copy.deepcopy(view())
    long["members"] = [{**long["members"][0], "symbol": f"S{i}", "name": f"A company with a long registered name number {i}", "layer": f"Layer {i // 9}",
                        "what": "makes a long list of things for a long list of customers in many countries"} for i in range(61)]
    lead = long["sections"]["leaders"][0]
    long["sections"] = {**long["sections"], "leaders": [{**lead, "symbol": f"S{i}", "name": f"A company with a long registered name number {i}"} for i in range(61)]}
    sparse = {"region": "US", "sector": "Nothing here", "members": [], "layers": [], "chain": {}, "sections": {}}
    yield "theme", deck.theme_plan(full_view())[0]
    yield "theme, bare", deck.theme_plan(view())[0]
    yield "theme, long", deck.theme_plan(long)[0]
    yield "theme, empty", deck.theme_plan(sparse)[0]
    yield "company", deck.plan(view_for_deck())[0]
    bare = view_for_deck()
    bare.update(reads=None, card=None, checklist=None)
    yield "company, bare", deck.plan(bare)[0]


def test_every_slide_of_every_deck_fits_its_slide_with_body_text_from_11_pt():
    for name, slides in decks():
        for s in slides:
            where = f"{name}: {s.title}"
            for b in s.blocks:
                x, y, w, h = b["box"]
                assert x >= deck.M - 0.01 and x + w <= deck.W_IN - deck.M + 0.01, where
                assert y + h <= (deck.BOT if s.kind == "content" else 6.95) + 0.01, where
                if s.kind == "content":
                    assert y >= 1.6, where                                   # below the title and its takeaway
                if b["kind"] == "text":
                    assert b.get("floor", deck.BODY_MIN) >= deck.BODY_MIN or s.kind == "cover", where
                if b["kind"] == "table":
                    lay = deck.table_layout(b, w, h)
                    assert lay["size"] >= deck.BODY_MIN and len(lay["rows"]) == len(b["rows"]), where       # nothing below 11 pt, no row dropped
                    assert all(len(r) == len(b["head"]) for r in b["rows"] if not isinstance(r, dict)), where
            for i, a in enumerate(s.blocks):
                for b in s.blocks[i + 1:]:
                    assert not boxes_overlap(a["box"], b["box"]), f"{where}: {a['kind']} over {b['kind']}"


def test_long_tables_run_on_with_their_page_count_and_never_end_on_a_crumb():
    # R19: the long table is the appendix's one table of every company's figures
    _, slides = next(d for d in decks() if d[0] == "theme, long")
    pages = [s.title for s in slides if s.title.startswith("Every company's figures")]
    assert len(pages) > 2 and pages[0].endswith(f"(1 of {len(pages)})") and pages[-1].endswith(f"({len(pages)} of {len(pages)})")
    sizes = [len(plain(b["rows"])) for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table"]
    assert sum(sizes) == 61 and min(sizes) >= 3


def test_text_is_cut_to_its_box_with_an_ellipsis_and_long_words_break():
    para = "word " * 200
    out = deck.fit_paras([para], 12, 3.0, 1.0)
    lines = sum(len(deck.wrap(p, 12, 3.0)) for p in out)
    assert lines * 12 * 1.25 / 72 <= 1.02 and out[-1].endswith("…")
    assert all(deck._width(ln, 11) <= 1.0 for ln in deck.wrap("https://example.com/a/very/long/link/that/has/no/spaces/at/all", 11, 1.0))
    assert deck.fit_paras(["Short."], 12, 3.0, 1.0) == ["Short."]


def test_both_decks_wear_the_apps_look_in_both_files():
    """The paper and ink of styles.css, the serif headings and sans body the app uses, and the mark, in the PDF and in PowerPoint."""
    from pptx import Presentation
    from pypdf import PdfReader
    pdf = deck.build_theme(full_view(), pdf=True)
    fonts = {f for p in PdfReader(io.BytesIO(pdf)).pages for f in (p.get("/Resources") or {}).get("/Font", {}).values()
             for f in [str(f.get_object().get("/BaseFont"))]}
    assert any("Fraunces" in f for f in fonts) and any("IBMPlexSans" in f for f in fonts)
    assert len(PdfReader(io.BytesIO(pdf)).pages) == len(Presentation(io.BytesIO(deck.build_theme(full_view()))).slides)
    prs = Presentation(io.BytesIO(deck.build(view_for_deck())))
    fills = {str(s.background.fill.fore_color.rgb) for s in prs.slides}
    assert fills == {deck.DARK, deck.PAPER}                              # the dark cover, every other slide on the app's paper
    assert all(sum(1 for sh in s.shapes if sh.shape_type == 5) >= 5 for s in prs.slides)      # the mark's five shapes on every slide (freeforms)
    assert deck.PAPER == "F5F1E8" and deck.INK == "1D1B17" and deck.UP == "0F7452" and deck.DOWN == "B23B3B"
