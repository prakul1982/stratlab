"""Release 46 (lane vf46, the outside review of the live R45 decks).

P0: every checked figure (verified, not reconciled, invalid) carries a source record: the document its year comes from (an Indian company's
annual results, consolidated or standalone; a US company's annual report filed with the SEC, its form and filing day), the period, the stored
page it was read from and the day that page was built, and the statement lines used with their values in the filing's unit. The data-confidence
page's "Verified figures" row names each figure's document, and an appendix page ("Figure sources") lists every record so a reader can work each
figure out again. A part the page doesn't hold is said "not stored", never filled in.

P1: a net margin above the EBITDA margin (17 Real estate companies, Bosch's 13.8% net on a 13% EBITDA margin) is reconciled line by line from
the year's stored statement: income outside operations, other items before tax (exceptional items), a tax credit, and net profit beyond profit
before tax less its tax (a share of associates or joint ventures). R44 checked other income alone, and the stored pages kept no profit before
tax, tax or operating profit (and pages built before 8 Nov no other income either), so a gap any of those covers stayed "not reconciled". The
pages now keep those lines (stock_pages.FACTS_VERSION 10 rebuilds the pages stored before), and each company not reconciled says which line is
not stored. Every company here is synthetic.

P2: a short "Questions the figures raise" card goes under the part's chart, the chart made shorter, instead of alone on a page.
"""
import copy
import re

from app import deck, deepdive, stock_pages
from app.intel import theme_data as D
from scripts import deck_check
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_theme1 import facts

BUILT = "2026-11-10T05:00:00+00:00"


def dev(sym, name, profit, lines=None, sales=1000.0, opm=12.0, basis="consolidated"):
    """A developer's four years to Mar 2026, the latest with `profit` of net profit on ₹1,000 crore of revenue at a 12% EBITDA margin, and the
    latest year's statement lines as the page stores them (`lines`; None: a page built before R46, which keeps none of them)."""
    f = facts(sym, name, [sales * 0.8, sales * 0.85, sales * 0.9, sales], [opm] * 4, [profit * 0.24, profit * 0.26, profit * 0.28, profit],
              industry=("Realty",), basis=basis, built_at=BUILT)
    if lines:
        f["years"][-1].update(lines)
    return f


# the year's lines: operating profit ₹120 crore (12%), then other income, interest, depreciation, profit before tax and its tax rate
ASSOC = {"op": 120.0, "other_income": 50.0, "interest": 30.0, "dep": 10.0, "pbt": 130.0, "tax_pct": 25.0}       # PAT 97.5; net 250: 152.5 after tax
CREDIT = {"op": 120.0, "other_income": 20.0, "interest": 10.0, "dep": 10.0, "pbt": 120.0, "tax_pct": -100.0}    # a tax credit of 120: PAT 240
EXCEPT = {"op": 120.0, "other_income": 10.0, "interest": 10.0, "dep": 10.0, "pbt": 280.0, "tax_pct": 10.0}      # 170 before tax beyond the lines


# ---------- P1: net above EBITDA reconciled line by line ----------
def test_a_share_of_associates_covers_net_above_ebitda_and_the_figure_is_verified_and_kept():
    r = D.company_row("IN", "DEV1", dev("DEV1", "Estate Bridge Ltd", 250.0, ASSOC))
    rec = r["verify"]["net"]
    # before R46 other income (₹50 crore) was the only line checked against the ₹130 crore gap: not reconciled, out of the median
    assert r["net"] == 25.0 and not r["one_off"] and rec["state"] == D.VERIFIED and D.in_median(r, "net") == 25.0
    assert ("above its 12% EBITDA margin (operating profit ₹120 crore) by ₹130 crore, covered by income outside operations of ₹50 crore and "
            "net profit beyond profit before tax less its tax (a share of associates' or joint ventures' profit, or another item after tax) of "
            "₹152 crore") in rec["why"]
    assert rec["bridge"]["items"] == [{"key": "other_income", "value": 50.0}, {"key": "after_tax", "value": 152.5}]
    # the source record: the document, period and stored page, and the lines with their values in the filing's unit
    assert r["source"] == {"document": "annual results, consolidated", "period": "Mar 2026", "filed": None, "page": "/stocks/in/DEV1",
                           "built": "2026-11-10", "unit": "₹ crore"}
    lines = {x["key"]: x["value"] for x in D.source_lines(r["filed"])}
    assert lines == {"sales": 1000.0, "profit": 250.0, "op": 120.0, "opm": 12.0, "other_income": 50.0, "interest": 30.0, "dep": 10.0,
                     "pbt": 130.0, "tax_pct": 25.0}


def test_a_tax_credit_or_items_before_tax_cover_the_gap():
    c = D.company_row("IN", "DEV2", dev("DEV2", "Estate Credit Ltd", 240.0, CREDIT))
    assert c["verify"]["net"]["state"] == D.VERIFIED and not c["one_off"]
    assert "a tax credit of ₹120 crore" in c["verify"]["net"]["why"]
    e = D.company_row("IN", "DEV3", dev("DEV3", "Estate Sale Ltd", 250.0, EXCEPT))
    assert e["verify"]["net"]["state"] == D.VERIFIED and not e["one_off"]
    assert "other items before tax (exceptional items) of ₹170 crore" in e["verify"]["net"]["why"]


def test_a_page_without_the_lines_says_which_line_is_not_stored_and_the_figure_stays_out():
    old = D.company_row("IN", "DEV4", dev("DEV4", "Estate Old Ltd", 250.0, {"other_income": 50.0}))
    rec = old["verify"]["net"]
    assert old["one_off"] and rec["state"] == D.UNVERIFIED and D.in_median(old, "net") is None
    assert rec["why"].endswith("income outside operations of ₹50 crore covers part of it; no profit before tax or tax rate is stored for the year "
                               "(the stored page was built before these lines were kept)")
    # the source gives no profit before tax (the line kept, empty): not stored, said without the page's age
    none = D.company_row("IN", "DEV6", dev("DEV6", "Estate Blank Ltd", 250.0, {"op": 120.0, "other_income": 50.0, "interest": 30.0, "dep": 10.0,
                                                                              "pbt": None, "tax_pct": None}))
    assert none["one_off"] and none["verify"]["net"]["why"].endswith("no profit before tax or tax rate is stored for the year")
    # the stored lines would add up, the net profit filed on another basis: never kept on a guess
    assert D.company_row("IN", "DEV7", dev("DEV7", "Estate Plain Ltd", 250.0))["verify"]["net"]["state"] == D.UNVERIFIED


def test_a_whole_point_ebitda_margin_is_checked_against_the_years_operating_profit():
    # Bosch-like: 13.8% net beside an EBITDA margin filed as 13%, the year's operating profit 13.9% of revenue
    lines = {"op": 2780.0, "other_income": None, "interest": 40.0, "dep": 500.0, "pbt": None, "tax_pct": None}
    r = D.company_row("IN", "AUTO", dev("AUTO", "Auto Parts Ltd", 2760.0, lines, sales=20000.0, opm=13.0))
    assert r["ebitda"] == 13.0 and r["net"] == 13.8 and not r["one_off"] and r["verify"]["net"]["state"] == D.VERIFIED
    assert "at or below its 13% EBITDA margin (operating profit ₹2,780 crore): net profit ₹2,760 crore against operating profit ₹2,780 crore" \
        in r["verify"]["net"]["why"]
    # the same year on a page with no operating profit stored: the whole point leaves it not reconciled
    assert D.company_row("IN", "AUTO", dev("AUTO", "Auto Parts Ltd", 2760.0, sales=20000.0, opm=13.0))["one_off"]


def test_the_theme_net_margin_over_time_keeps_a_year_its_lines_reconcile():
    rows = [D.company_row("IN", s, dev(s, n, 250.0, x)) for s, n, x in
            (("DEV1", "Estate Bridge Ltd", ASSOC), ("DEV4", "Estate Old Ltd", {"other_income": 50.0}))]
    rows += [D.company_row("IN", f"P{i}", dev(f"P{i}", f"Plain {i} Ltd", 80.0)) for i in range(2)]
    h = D.layer_history(rows)
    assert h["one_off"] == ["DEV4"] and h["net_n"] == 3


# ---------- P0: the stored page keeps the lines; the US record names its form ----------
def test_the_stored_page_keeps_each_years_statement_lines_and_older_pages_are_rebuilt():
    p = {"region": "IN", "pl": {"cols": ["Mar 2025", "Mar 2026"], "rows": {
        "Sales": [900.0, 1000.0], "Expenses": [790.0, 880.0], "Operating Profit": [110.0, 120.0], "OPM %": [12.0, 12.0], "Other Income": [40.0, 50.0],
        "Interest": [25.0, 30.0], "Depreciation": [9.0, 10.0], "Profit before tax": [116.0, 130.0], "Tax %": [25.0, 25.0], "Net Profit": [200.0, 250.0]}}}
    y = deepdive.numbers(p)["years"][-1]
    assert {k: y[k] for k in ("op", "other_income", "interest", "dep", "pbt", "tax_pct")} == ASSOC
    f = stock_pages.facts("IN", "DEV1", {"name": "Estate Bridge Ltd"}, deepdive.numbers(p), {}, None, None, [], "NSE")
    assert {k: f["years"][-1][k] for k in ASSOC} == ASSOC
    assert stock_pages.FACTS_VERSION == 10 and f["v"] == 10          # a page kept before these lines is built again (the screens' sweep)


def test_a_us_record_names_the_annual_report_and_says_when_its_form_is_not_stored():
    f = facts("CHIP", "Chip Co", [80, 90, 95, 100], [30] * 4, [8, 9, 9, 70], region="US", unit="$ million", annual_form="10-K",
              annual_filed="2026-10-28", built_at=BUILT)
    src = D.company_row("US", "CHIP", f)["source"]
    assert src["document"] == "10-K annual report filed with the SEC" and src["filed"] == "2026-10-28" and src["page"] == "/stocks/us/CHIP"
    assert deck.source_words(src) == "10-K annual report filed with the SEC, filed 28 Oct 2026; Mar 2026; page /stocks/us/CHIP, built 10 Nov 2026"
    f.pop("annual_form")
    assert D.company_row("US", "CHIP", f)["source"]["document"] == "annual report filed with the SEC (its form is not stored on the page)"
    g = facts("PLAIN", "Plain Co", [80, 90, 95, 100], [30] * 4, [8, 9, 9, 70])
    assert D.company_row("IN", "PLAIN", g)["source"]["document"] == "annual results (consolidated or standalone is not stored on the page)"
    assert deck.source_words(None) == "source not stored"


# ---------- P0 and P1 in the deck ----------
def realty_theme():
    cos = [("DEV1", "Estate Bridge Ltd", 250.0, ASSOC), ("DEV2", "Estate Credit Ltd", 240.0, CREDIT), ("DEV3", "Estate Sale Ltd", 250.0, EXCEPT),
           ("DEV4", "Estate Old Ltd", 250.0, {"other_income": 50.0})] + [(f"P{i}", f"Plain Homes {i} Ltd", 60.0 + 10 * i, None) for i in range(4)]
    f = {s: dev(s, n, p, x) for s, n, p, x in cos}
    m = {"sector": "Real estate", "value_chain": [{"layer": "Residential developers", "description": "Builds and sells homes.",
                                                    "companies": [{"name": n, "ticker": s, "what": "builds and sells homes"} for s, n, _, _ in cos]}],
         "sub_themes": [], "placements": {"checked": True, "pending": 0, "left_out": 0, "placed": len(cos)}}
    return m, f


def conf_rows(slides):
    conf = next(s for s in slides if s.title == "Data confidence")
    return {r[0]: r for b in conf.blocks if b["kind"] == "table" for r in b["rows"]}


def test_the_deck_keeps_the_reconciled_developers_and_shows_each_figures_source_record():
    m, f = realty_theme()
    v, slides = deck_of("IN", m, f)
    ch = v["checks"]
    assert [x["symbol"] for x in ch["verified"]] == ["DEV1", "DEV2", "DEV3"] and [x["symbol"] for x in ch["one_off"]] == ["DEV4"]
    assert v["layers"][0]["stats"]["net"]["n"] == 7                  # the three verified kept in the net margin's median; the one not, out
    assert all(x["source"]["document"] == "annual results, consolidated" and x["lines"] for x in ch["states"])
    rows = conf_rows(slides)
    vf = rows["Verified figures"][1]
    assert vf.startswith("3 unusual figures verified against their own filed figures: Estate Bridge Ltd, net margin 25% (net profit ₹250 crore "
                         "over revenue ₹1,000 crore, Mar 2026: 25%; above EBITDA by ₹130 crore: other income ₹50 crore and items after tax ₹152 crore; "
                         "annual results, consolidated); Estate Credit Ltd, net margin 24% (")
    assert "a tax credit ₹120 crore" in vf and "items before tax ₹170 crore" in vf
    assert re.search(r"Each one's document, stored page and lines: p\. \d+\.$", vf)
    nb = rows["Net above EBITDA margin"][1]
    assert nb.startswith("Net margin above the EBITDA margin at 1 company, that the year's stored lines don't cover: Estate Old Ltd (25% net, 12% EBITDA).")
    assert "1 company whose stored page holds no profit before tax or tax rate (built before these lines were kept)." in nb
    assert "no stored figure that explains it" not in texts(slides)
    # the appendix's source page: one row per checked figure, verified first, each with its document, page, lines and what they show
    page = next(s for s in slides if s.title == deck.SOURCES_TITLE)
    assert page.eyebrow.endswith("Appendix") and page.subtitle.startswith("4 checked figures, 3 verified")
    tab = next(b for b in page.blocks if b["kind"] == "table")
    by = {r[0]: r for r in tab["rows"]}
    assert [r[0] for r in tab["rows"]] == ["Estate Bridge Ltd (DEV1)", "Estate Credit Ltd (DEV2)", "Estate Sale Ltd (DEV3)", "Estate Old Ltd (DEV4)"]
    one = by["Estate Bridge Ltd (DEV1)"]
    assert one[1:] == ["Net margin 25%, verified", "annual results, consolidated; Mar 2026; page built 10 Nov 2026",
                       "₹ crore: revenue 1,000; net profit 250; operating profit 120; EBITDA margin 12%; other income 50; interest 30; depreciation 10; "
                       "profit before tax 130; tax rate 25%", "above EBITDA by 130: covered by other income 50, items after tax 152"]
    assert by["Estate Credit Ltd (DEV2)"][4] == "above EBITDA by 120: covered by other income 20, a tax credit 120"
    old = by["Estate Old Ltd (DEV4)"]
    assert old[1] == "Net margin 25%, not reconciled" and old[3].endswith("other income 50; profit before tax not stored; tax rate not stored")
    assert old[4] == ("above EBITDA by 130; other income 50 covers part; no profit before tax or tax rate stored (page built before these lines "
                      "were kept)")
    note = next(b for b in page.blocks if b["kind"] == "text")["paras"][0]
    assert note.startswith("Each company's year as its stored page holds it (/stocks/in/SYMBOL), in the filing's unit.")
    contents = next(s for s in slides if s.title == "Contents")
    apx = next(r for b in contents.blocks if b["kind"] == "table" for r in b["rows"] if r[0] == "Appendix")
    assert "each checked figure's source and statement lines" in apx[1]
    got = deck_check.check_pages(["\n".join(x for x in texts(slides).split("\n") if x != "None")])      # (texts lists a card's empty fields as None)
    assert not deck_check.failed(got, strict=True), got["findings"][:3]
    assert not deck.CAUSE_WORDS.search(texts(slides))


# ---------- P2: a short questions card under the part's chart, never alone on a page ----------
def test_a_short_questions_card_goes_under_the_chart_rather_than_alone_on_a_page(monkeypatch):
    from tests import test_r25_deck as T
    v = copy.deepcopy(dict(T.families())["insurers with filed figures"][0])
    names = ["Brokers", "Web aggregators", "Distribution and aggregation", "Life insurance underwriting", "General insurance underwriting",
             "Health insurance underwriting", "Reinsurance", "Other insurance companies"]
    v["layers"] = [{**copy.deepcopy(v["layers"][i % len(v["layers"])]), "layer": n} for i, n in enumerate(names)]
    q = "Is the latest year's growth in the layers the base or the business? The deck holds only this one comparison."
    monkeypatch.setattr(deck, "economics_questions", lambda *a, **k: [q])
    slides = deck.theme_plan(v)[0]
    titles = [s.title for s in slides]
    assert "Questions the figures raise" not in titles                 # the live R45 Insurance deck's p.14: one question alone on a page
    chart = next(s for s in slides if s.title == "Median ROE and Net margin by layer")
    cards = [it for b in chart.blocks if b["kind"] == "cards" for it in b["items"]]
    assert cards and cards[0]["title"] == "Questions the figures raise" and cards[0]["lines"] == [q]
    col = next(b for b in chart.blocks if b["kind"] == "columns")
    card = next(b for b in chart.blocks if b["kind"] == "cards")
    assert col["box"][3] >= deck.CHART_MIN and col["box"][1] + col["box"][3] <= card["box"][1]          # the chart shorter, nothing overlaps
    assert chart.subtitle.endswith("; the questions the figures raise under it")
    # a card too tall for the chart to keep CHART_MIN still gets a page of its own
    monkeypatch.setattr(deck, "economics_questions", lambda *a, **k: [q + f" ({i})" for i in range(5)])
    assert "Questions the figures raise" in [s.title for s in deck.theme_plan(v)[0]]
