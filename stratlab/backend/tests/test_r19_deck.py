"""Release 19 (owner, 7 Nov: "The page optimisation was not fixed at 25 made as many as you want just keep the important ones not
everything"): no page target; every page carries something important, low-value pages and tables are dropped (not moved to the appendix), and
the appendix is one compact table of every confirmed company's figures. Synthetic themes of any sector, India and the US."""
import copy
import re

from app import deck
from tests.test_deck_look import full_view
from tests.test_export import plain, table_of
from tests.test_r17_fixes import theme_a, theme_b
from tests.test_r18_deck import bank_theme, deck_of, maker_theme, us_list_theme

IMPORTANT = ("table", "hbars", "columns", "lines", "cards", "stats", "flow")


def themes():
    yield "packaging", deck_of(*theme_a())[1]
    yield "payments (US, one layer)", deck_of(*theme_b())[1]
    yield "lenders", deck_of(*bank_theme()[:3])[1]
    yield "US list, by industry", deck_of(*us_list_theme())[1]
    yield "US list, one industry", deck_of(*us_list_theme(False))[1]
    yield "makers", deck_of(*maker_theme())[1]
    yield "every part", deck.theme_plan(full_view())[0]


def appendix_at(slides) -> int:
    return next((i for i, s in enumerate(slides) if s.title.startswith("Every company's figures")), len(slides))


def test_every_page_carries_something_important():
    for name, slides in themes():
        for s in slides:
            if s.kind == "cover":
                continue
            assert s.kind == "content", f"{name}: a divider {s.title}"
            blocks = [b for b in s.blocks if b["kind"] in IMPORTANT and (b.get("rows") or b.get("items") or b.get("vals") or b.get("series"))]
            assert blocks, f"{name}: {s.title} has nothing but text"
            for b in s.blocks:                          # no table that is a single "nothing to show" line
                if b["kind"] == "table":
                    assert plain(b["rows"]), f"{name}: {s.title}: an empty table"


def test_no_continued_pages_and_none_of_the_dropped_parts():
    dropped = ("The theme at a glance", "Every company in this theme", "Latest on this theme", "New listings in the theme", "Margins over time",
               "Ownership", "Events", "Management report cards", "In the theme, not placed in a layer", "Appendix")
    for name, slides in themes():
        titles = [s.title for s in slides]
        assert not any("continued" in t or "all companies" in t for t in titles), name
        for t in dropped:
            assert t not in titles, (name, t)
        for single in ("Data confidence", "Dated company updates", "Tailwinds and risks", "Operating figures", "Sub-themes", "How to read this deck",
                       "The latest quarter against a year earlier"):
            assert len([x for x in titles if x == single or x.startswith(single + " (")]) <= 1, (name, single)
            assert not any(x.startswith(single + " (") for x in titles), (name, single)


def test_the_appendix_is_one_table_of_every_confirmed_company():
    for name, slides in themes():
        at = appendix_at(slides)
        assert at < len(slides), name
        # deck89 (changed on purpose, owner 25 Nov: the story first, the audit in the appendix): the appendix opens with the one table of
        # every company's figures, then "Method and coverage" (what the notes and the data-confidence pages said) and how the figures are built
        tail = [x for x in slides[at:] if x.title.startswith("Every company's figures")]
        n = len(tail)
        assert slides[at:at + n] == tail, name
        for k, s in enumerate(tail, 1):
            assert s.title == ("Every company's figures" + (f" ({k} of {n})" if n > 1 else "")), (name, s.title)
            assert [b["kind"] for b in s.blocks if b["kind"] != "text"] == ["table"], (name, s.title)
            assert s.blocks[0]["head"] == tail[0].blocks[0]["head"]
        rest = [x.title for x in slides[at + n:]]
        assert rest and rest[0].startswith(deck.METHOD_TITLE) and all(deck.is_appendix(x) for x in slides[at:]), name
        assert not any(t.startswith(deck.NOTES_TITLE) for t in [x.title for x in slides[:at]]), name
    v, slides = deck_of(*maker_theme())
    rows = [r[0] for s in slides[appendix_at(slides):] if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table" for r in b["rows"]]
    assert len(rows) == len(set(rows)) == 4 and not any("not confirmed" in r for r in rows)          # one row each, confirmed only
    notes = " ".join(deck.plain_section(slides, "Who is in it"))          # deck89 (changed on purpose): the notes in "Method and coverage"
    assert "2 companies whose own words don't show the work, left out of every median and total: Maker 5 Ltd, Maker 6 Ltd." in notes


def test_data_confidence_is_one_page_with_its_counts_and_worth_a_watch_only_with_rows():
    # deck89 (changed on purpose, owner 25 Nov): the checks and their counts are one table and one line of the appendix's "Method and coverage"
    for name, slides in themes():
        assert not [s for s in slides if s.title.startswith("Data confidence")], name
        dc = deck.joined(deck.with_held(slides))  # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
        assert dc and deck.table_with(deck.with_held(slides), deck.CONF_HEAD) and any(p.startswith("Counts: ") for b in dc.blocks for p in b.get("paras") or []), name  # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    v = full_view()
    v["checks"]["series"] = [{"symbol": f"X{i}", "name": f"X {i}"} for i in range(9)]
    v["checks"]["unverified"] = [{"symbol": f"U{i}", "name": f"U {i}"} for i in range(9)]
    slides = deck.theme_plan(v)[0]
    assert len([b for s in deck.with_held(slides) for b in s.blocks if b["kind"] == "table" and b["head"] == deck.CONF_HEAD]) >= 1  # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    _, packaging = deck_of(*theme_a())
    assert "Dated company updates" not in [s.title for s in packaging]                         # no company meets the rules (m2: the page's name)
    # deck89 (changed on purpose): said once among the appendix's notes, not as a card of the findings
    notes = deck.table_with(deck.with_held(packaging), deck.NOTES_HEAD)["rows"]          # deck89 round 2 (changed on purpose, coordinator 25 Nov: the full records are kept with the deck, on the theme's page, not printed)
    assert ["Dated company updates", "No company meets the rules today."] in notes
    v = full_view()
    v["sections"]["events"]["results_due"] = [{"symbol": f"R{i}", "name": f"Results Co {i}", "date": f"2026-11-{1 + i % 7:02d}", "purpose": "Results"} for i in range(30)]
    slides = deck.theme_plan(v, now=__import__("datetime").datetime(2026, 10, 31, tzinfo=__import__("datetime").timezone.utc))[0]
    watch = [s for s in slides if s.title.startswith("Dated company updates")]
    assert len(watch) == 1 and watch[0].title == "Dated company updates" and "latest by date of" in watch[0].subtitle
    dates = [r[2] for r in table_of(slides, "Dated company updates")["rows"]]
    assert dates == sorted(dates, key=lambda d: __import__("datetime").datetime.strptime(d, "%d %b %Y") if d != "–" else __import__("datetime").datetime.min, reverse=True)


def test_price_and_balance_pages_only_when_they_show_something():
    v = full_view()
    v["sections"]["price"]["stage2"] = {"n": 10, "count": 5, "share": 50}
    v["prices"]["returns"]["1Y"] = {"theme": 10.0, "bench": 8.0}
    v["sections"]["balance"].update(above_1=0, with_debt_equity=10, cover_under_2=0)
    titles = [s.title for s in deck.theme_plan(v)[0]]
    assert "Price" not in titles and "Balance sheet and cash" not in titles
    v["prices"]["returns"]["1Y"] = {"theme": 20.0, "bench": 8.0}                                # 12 points above its index
    v["sections"]["balance"].update(above_1=4)                                                  # 4 of 10 borrow above their equity
    titles = [s.title for s in deck.theme_plan(v)[0]]
    assert "Price" in titles and "Balance sheet and cash" in titles


def test_sub_themes_are_one_compact_page_of_names():
    v = copy.deepcopy(full_view())
    many = [{"symbol": f"C{i}", "name": f"Cell Co {i}", "cap": 1000 - i} for i in range(9)]
    v["subs"] = [{"name": "Cell making", "detail": "Cells.", "companies": many}, {"name": "Empty one", "detail": "Nothing.", "companies": []}]
    slides = deck.theme_plan(v)[0]
    # deck89 (changed on purpose, owner 25 Nov: "Sub-themes" repeats the layers): no page; how many have a listed company, and where each is
    assert "Sub-themes" not in [s.title for s in slides]
    assert "The 1 sub-theme with a listed company, each with its companies: on the theme's page." in deck.plain_section(slides, "Not in this deck, and what the AI wrote")


def test_page_counts_of_the_synthetic_themes():
    counts = {name: len(slides) for name, slides in themes()}
    assert all(n <= 22 for n in counts.values()), counts
    assert counts["US list, one industry"] < counts["US list, by industry"]                   # no value chain when there is nothing to compare
    for name, slides in themes():
        # changed on purpose (lane t1, LIVE7A-014): a ".0%" only beside a decimal percentage in the same line (one precision a text)
        assert all(deck.whole_figures(s.subtitle or "") == (s.subtitle or "") for s in slides), name
