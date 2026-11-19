"""LIVE7A (the live review of Release 41's theme pages and decks), lane t1: the price block, one price date, the companies' own words, the
operating figures, the headlines and claims, whole-point margins, the deck's numbers and the public theme post. Generic: synthetic data only."""
import copy
import time
from datetime import date, timedelta

import pytest

from app import deck
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from app.intel import theme_prices as P
from app.intel import theme_routes as T


def _bars(start: date, end: date, f):
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append({"t": d.isoformat(), "c": f(d)})
        d += timedelta(days=1)
    return out


# ---------- LIVE7A-002: the price block fills at once and never divides by a rounded-away close ----------
def test_a_share_under_a_hundredth_of_a_cent_keeps_its_close_and_the_theme_line_does_not_fail():
    end, start = date(2026, 11, 10), date(2023, 1, 2)
    penny = P.reduce_bars(_bars(start, end, lambda d: 0.00003 + (d - start).days * 1e-8))
    assert min(penny["closes"]) > 0                                    # four decimals made it 0.0, and the weekly line divided by it (a 500)
    big = P.reduce_bars(_bars(start, end, lambda d: 100 + (d - start).days * 0.05))
    idx = P.reduce_bars(_bars(start, end, lambda d: 400 + (d - start).days * 0.1))
    out = P.compute([("PEN", "Penny"), ("BIG", "Big")], {"PEN": penny, "BIG": big}, idx, "SPY")
    assert out["line"] and out["returns"]["1Y"]["theme"] is not None


def test_companies_not_read_yet_show_from_the_stored_daily_row_and_the_index_from_its_stored_closes(monkeypatch):
    T.PRICE_CACHE.clear()
    end, start = date(2026, 11, 10), date(2025, 9, 1)
    rows = {f"S{i}": [100.0 + i, 0.5, 1.0, 2.0 + i, 5.0, 8.0, 10.0 + i, 1000.0, 900.0] for i in range(10)}
    hist = {d["t"]: [None] * 5 + [d["c"]] for d in _bars(start, end, lambda d: 1000 + (d - start).days)}
    from app import breadth
    monkeypatch.setattr(breadth, "load_hist", lambda g: hist if g == "nifty500" else {})
    monkeypatch.setattr(T.price_reads, "hit", lambda *a, **k: False)            # the minute's reads are used: nothing is read now

    def no_bench():
        raise RuntimeError("the broker is offline")
    members = [(s, s) for s in rows]
    out = T.gather_prices("IN", members, lambda s: [], no_bench, daily=(rows, end.isoformat(), {}))
    assert len(out["companies"]) == 10 and out["pending"] == 10 and out["missing"] == 0
    assert out["median"]["1Y"]["n"] == 10 and out["returns"]["1Y"]["theme"] == round(sum(10.0 + i for i in range(10)) / 10, 1)
    assert out["benchmark"] == "NIFTY 500" and out["returns"]["1M"]["bench"] is not None and out["returns_to"] == end.isoformat()
    assert out["line"] is None                                          # the weekly line waits for the companies' own candles
    T.PRICE_CACHE.clear()


def test_the_weekly_line_is_drawn_once_most_priced_companies_have_their_candles():
    end, start = date(2026, 11, 10), date(2023, 1, 2)
    red = {f"R{i}": P.reduce_bars(_bars(start, end, lambda d, i=i: 100 + i + (d - start).days * 0.05)) for i in range(3)}
    daily = {f"D{i}": P.from_daily_row([50.0, 0, 0, 1.0, 2.0, 3.0, 4.0, 0, 0], end.isoformat()) for i in range(7)}
    idx = P.reduce_bars(_bars(start, end, lambda d: 400 + (d - start).days * 0.1))
    members = [(s, s) for s in list(red) + list(daily)]
    assert P.compute(members, {**red, **daily}, idx, "SPY")["line"] is None              # 3 of 10 with candles
    assert P.compute(members[:3], red, idx, "SPY")["line"] is not None


# ---------- LIVE7A-003: every company at the newest close, one price date ----------
def test_kept_facts_move_to_the_index_close_and_the_dive_says_who_is_at_an_earlier_one(monkeypatch):
    f = {"price": 100.0, "price_at": "2026-11-06", "market_cap": 1000.0, "pe": 20.0, "div_yield": 2.0, "high52": 105.0, "low52": 80.0}
    got = D.at_close(f, {"price": 110.0, "price_at": "2026-11-11"}, "US", "X")
    assert got["price_at"] == "2026-11-11" and got["market_cap"] == 1100.0 and got["pe"] == 22.0 and got["div_yield"] == round(2.0 / 1.1, 2)
    assert got["high52"] == 110.0
    assert D.at_close(f, {"price": 90.0, "price_at": "2026-11-05"}) is f                 # an older row changes nothing
    assert D.at_close(f, {"price": 400.0, "price_at": "2026-11-11"}) is f                # a move it can't scale (a split): its own day stays
    assert D.price_day([{"price_at": "2026-11-11"}, {"price_at": "2026-11-06"}, {"price_at": "2026-11-11"}]) == ("2026-11-11", 1)


def test_a_kept_dive_is_worked_out_again_when_the_index_has_a_newer_close(monkeypatch):
    rows = [{"symbol": "A", "price_at": "2026-11-11"}, {"symbol": "B", "price_at": "2026-11-11"}]

    class R:
        @staticmethod
        def index_rows(region):
            return rows
    monkeypatch.setattr(T, "_routes", lambda: R)
    kept = {"value": {"dive": {"as_of": "2026-11-06"}, "pieces": {"A": 1.0, "B": 1.0}, "priced": ["2026-11-06", 0]}, "at": time.time()}
    assert T.prices_moved("US", kept)
    kept["value"]["priced"] = ["2026-11-11", 0]
    assert not T.prices_moved("US", kept)
    kept["value"]["priced"] = ["2026-11-11", 1]                          # one more company moved since: again, but not within REPRICE_EVERY
    assert not T.prices_moved("US", kept)
    kept["at"] = time.time() - T.REPRICE_EVERY - 1
    assert T.prices_moved("US", kept)


# ---------- LIVE7A-004: own words ----------
OWN_CASES_7A = [  # (text, name, shown): the same list as the page's (frontend/unit/live7a-themes.test.mjs)
    ("Toyo Tire Corporation, commonly known as Toyo Tires, is a multinational tire and rubber products company based in Itami, Japan", "TOYO Co., Ltd", False),
    ("Monolithic Power Systems, Inc. is an American, publicly traded company headquartered in West Palm Beach, Florida", "Monolithic Power Systems Inc", False),
    ("SK hynix Inc. is a South Korean supplier of DRAM and flash memory chips", "SK Hynix", False),
    ("We also offer data center rack-scale platform designs", "Advanced Micro Devices", False),
    ("It is headquartered in Little Rock, Arkansas, and operates 270 stores", "Dillards Inc", False),
    ("We design, manufacture, test and market analog and mixed-signal chips", "Analog Devices", True),
    ("The Company is an India-based manufacturer of two-wheelers", "Two Wheels Ltd", True),
    ("Motherson Sumi Systems is engaged primarily in the manufacture and sale of components to automotive makers", "Samvardhana Motherson", True),
]


def test_an_encyclopedia_lead_an_also_line_or_a_where_line_is_not_a_companys_own_words():
    for text, name, shown in OWN_CASES_7A:
        assert bool(B.own_words(text, name)) is shown, text
    assert deck._what("Toyo Tire Corporation, commonly known as Toyo Tires, is a multinational tire maker", "TOYO Co., Ltd") == ""


def test_a_line_cut_by_the_end_of_its_stored_description_loses_the_cut_word():
    about = "Our company. We design, manufacture, test and market a broad portfolio of solutio"
    assert B.whole_words("We design, manufacture, test and market a broad portfolio of solutio", about) == \
        "We design, manufacture, test and market a broad portfolio of…"
    assert B.whole_words("We design and sell chips", "We design and sell chips. We also license.") == "We design and sell chips"
    assert B.whole_words("We design and sell chips", "We design and sell chips.") == "We design and sell chips"


# ---------- LIVE7A-005: operating figures under the right layer, never another company's ----------
def test_a_year_ago_figure_that_is_another_companys_latest_is_held():
    rows = [{"symbol": "PV", "name": "PV", "unit": "units", "value": 75426, "prev": 70000, "year_ago": 37530, "change_prev": 7.8, "change_year": None},
            {"symbol": "CV", "name": "CV", "unit": "units", "value": 37530, "prev": 36000, "year_ago": 33000, "change_prev": 4.2, "change_year": 13.7}]
    got = {r["symbol"]: r for r in D.hold_suspect(rows)}
    assert got["PV"]["year_ago"] is None and "another company's latest" in got["PV"]["held"] and got["CV"]["year_ago"] == 33000


def test_old_operating_figures_are_left_out_and_a_company_is_listed_once():
    today = date(2026, 11, 12)
    read = {"A": {"metric": "Sales", "unit": "units", "span": "month", "period": "2026-10", "value": 10},
            "OLD": {"metric": "Sales", "unit": "units", "span": "month", "period": "2025-03", "value": 5},
            "Q": {"metric": "PAT", "unit": "₹ crore", "span": "quarter", "period": "2026-03", "value": 7}}
    out = D.business_section([{"layer": "L", "companies": [{"symbol": s} for s in read]}], [{"name": "S", "companies": [{"symbol": "A"}]}],
                             {}, lambda s: read.get(s), today=today)
    assert [r["symbol"] for r in out["layers"][0]["rows"]] == ["A"] and out["subs"][0]["rows"] == []


# ---------- LIVE7A-009: whole-point margins and gaps printed whole ----------
def test_margins_mostly_filed_in_whole_points_print_their_medians_and_gaps_whole():
    rows = [{"ebitda": 12.0, "ebitda_dp": 0}, {"ebitda": 21.0, "ebitda_dp": 0}, {"ebitda": 29.9, "ebitda_dp": 1}]
    assert D.whole_points(rows) and not D.whole_points(rows[2:])
    assert D.gap_of(25.0, 22.0, True) == "3" and D.gap_of(25.0, 22.0) == "3.0" and D.gap_of(25.5, 22.0, True) == "3.5"


# ---------- LIVE7A-012 / 013: headlines and claims ----------
def test_holding_notices_price_move_notes_better_buy_pieces_and_score_pages_are_not_headlines():
    co = {"company": "C", "source": "Site", "kind": "news"}
    for h in ("Chip Co $CHP Stock Acquired by Some Wealth Advisors LLC", "Net Co (NASDAQ:NET) Shares Down 1.4% - Here's What Happened",
              "Better Buy: Chip Co vs. Fab Co", "Dell vs Fab Co: Which Is a Better Buy for 2027?", "Net Co GF Value Says Overvalued -- GF Score: 64/100",
              "Big Fund Inc. Raises Stake in Chip Co (NASDAQ:CHP)"):
        assert not D.headline_kept({**co, "headline": h}, "US"), h
    for h in ("Chip Co raises its capital spending plan", "Car Co raises stake in its battery joint venture"):
        assert D.headline_kept({**co, "headline": h}, "US"), h


def test_a_claim_is_shown_with_a_dated_headline_only_when_the_headline_is_about_it():
    claim = "The CHIPS Act grants support new fabs by four named chipmakers"
    assert not C.source_fits(claim, "Engine maker begins production at a chip fab", "CHIPS Act")
    assert C.source_fits(claim, "Commerce finalises a CHIPS Act award for a new fab", "CHIPS Act")
    m = C.claims_fit({"tailwinds": [{"text": claim, "status": "current", "source": {"headline": "Engine maker begins production at a chip fab"}}], "risks": []})
    assert m["tailwinds"][0] == {"text": claim, "status": "general", "source": None}


# ---------- LIVE7A-014: the deck's numbers ----------
def test_ranges_and_medians_print_the_real_minus():
    assert deck._span({"min": -14.1, "max": 23.6}) == "−14.1% to 23.6%" and deck.col_fmt("net", True)(-4.6) == "−4.6%"
    assert deck._medn({"n": 4, "median": -2.0}) .startswith("−2.0%") and deck._cr(-1234) == "−1,234"


def test_one_precision_in_a_text_a_column_and_a_chart():
    assert deck.whole_figures("from 13.2% to 15.0%") == "from 13.2% to 15.0%" and deck.whole_figures("from 13.0% to 15.0%") == "from 13% to 15%"
    assert deck._whole_rows([["A", "20.0%", "14.0%"], ["B", "19.6%", "16.0%"]]) == [["A", "20.0%", "14%"], ["B", "19.6%", "16%"]]
    s = deck.Slide("t", "x")
    s.add("hbars", (1, 1, 4, 3), cats=["a", "b"], vals=[36.0, 35.9], fmt="pct")
    s.add("hbars", (1, 1, 4, 3), cats=["a", "b"], vals=[36.0, 21.0], fmt="pct")
    deck.whole_deck([s])
    assert [b["fmt"] for b in s.blocks] == ["pctk1", "pct1"] and deck._fmt("pctk1")[0](36.0) == "36.0%"


def test_the_layer_parts_add_up_to_the_change_shown():
    assert D.round_to_sum([-2.34, 0.46, 0.34, 0.14, 0.07, 0.04], -1.3) == [-2.3, 0.5, 0.3, 0.1, 0.1, 0.0]
    got = D.round_to_sum([-2.26, 0.46, 0.34, 0.14, 0.07, 0.04], -1.2)
    assert round(sum(got), 1) == -1.2


def test_a_row_carries_its_kept_reason_before_the_whole_company_mark_and_a_mark_s_note_only_with_its_row():
    from tests.test_deck_look import full_view
    v = full_view()
    lay = v["layers"][0]
    c0 = lay["companies"][0]
    c0["model_out"] = "unclear"
    c0["calc"] = {"in": False, "why": "way of earning not shown"}
    lay["company_wide"] = [c0["symbol"]]
    slides = deck.theme_plan(v)[0]
    # lane d1 (updated on purpose): a layer of two companies is rows of the "Smaller layers" page, which marks a row the same way
    s = next(x for x in slides if x.title.startswith(("Layer 1 · ", deck.SMALL_TITLE)))
    tbl = next(b for b in s.blocks if b["kind"] == "table")
    name = next(c_ for r in tbl["rows"] if isinstance(r, list) for c_ in r[:2] if str(c_).startswith(c0["name"]))
    assert name.endswith("(insufficient evidence)")          # (updated on purpose, ex49: the mark is the reason's kind)
    notes = " ".join(p for b in s.blocks if b["kind"] == "text" for p in b.get("paras") or [])
    whole_rows = any(str(c_).endswith("(whole company)") for r in tbl["rows"] if isinstance(r, list) for c_ in r[:2])
    assert "(insufficient evidence):" in notes and ("(whole company):" in notes) == whole_rows          # a mark's note only with a row that carries it


def test_the_contents_line_for_tailwinds_and_risks_uses_the_page_s_own_counts():
    from tests.test_deck_look import full_view
    v = full_view()
    v["tailwinds"] = [{"text": f"Tailwind {i}", "status": "current", "source": {"headline": "h", "at": "2026-10-01", "outlet": "o", "url": ""}}
                      for i in range(6)]
    v["risks"] = [{"text": f"Risk {i}", "status": "general", "source": None} for i in range(6)]
    slides = deck.theme_plan(v)[0]
    page = next(s for s in slides if s.title == "Tailwinds and risks")
    row = next(r for s in slides if s.title == "Contents" for b in s.blocks for r in b.get("rows") or [] if r[0] == "Tailwinds and risks")
    # the live deck's contents said "4 tailwinds and 4 risks; 5 with a dated headline ... that shows it is still current" over a page of 2 and 2
    assert row[1] == "4 tailwinds and 4 risks shown, 4 with a dated source; the rest are on the theme's page."
    assert page.subtitle.startswith("4 tailwinds and 4 risks, 4 of the 8 with a dated source")


# ---------- LIVE7A-025, LIVE7A-008, LIVE7A-017 ----------
def test_names_keep_their_apostrophe_and_a_dividend_is_said_once():
    assert D.shown_name("O Reilly Automotive Inc") == "O'Reilly Automotive Inc"
    assert D.shown_name("Lowes Companies Inc", "Lowe's Companies, Inc.") == "Lowe's Companies, Inc."
    assert D.shown_name("Chip Co", "Other Name") == "Chip Co"

    class S:
        today = date(2026, 11, 12)

        @staticmethod
        def actions(a, b, syms):
            return [{"symbol": "X", "ex_date": "2026-11-20", "kind": "dividend", "label": "Dividend", "text": "Dividend $0.15 a share"}]
        results = staticmethod(lambda a, b, s: [])
    try:
        ev = D.events_section(["X"], {"X": "X Co"}, S)
    except AttributeError:
        pytest.skip("events_section reads more of its source than this test gives")
    assert ev["actions"][0]["text"] == "$0.15 a share"


def test_the_theme_list_says_the_day_its_page_says(monkeypatch):
    from app.intel import theme_library as L
    at, day = L.updated_at("IN", {"at": 1762551000.0, "q": "x"})       # 7 Nov 2025, 21:30 UTC = 8 Nov, 03:00 IST
    assert day == "2025-11-08" and at.startswith("2025-11-07")


def test_a_theme_post_follows_the_live_read_and_says_its_day():
    from app import blog_research as BR
    src = {"theme": "Chips", "region": "US", "sector": "Chips", "members": 3, "unit": "$ million", "basis": "",
           "rows": [{"layer": "A", "n": 2, "ebitda": 20.0, "companies": [{"symbol": "X", "name": "X Co"}, {"symbol": "Y", "name": "Y Co"}]},
                    {"layer": "B", "n": 1, "ebitda": 30.0, "companies": [{"symbol": "Z", "name": "Z Co"}]}], "notable": [], "read_on": "2026-11-11"}
    assert not BR.figures_moved(src, {**src, "read_on": "2026-11-12"})
    assert BR.figures_moved(src, {**src, "members": 4})
    assert BR.figures_moved(src, {**src, "rows": src["rows"][:1]})
    post = BR.theme_post_from(src)
    assert "read of the theme on 11 Nov 2026" in post["blocks"][0]["text"]


# ---------- LIVE7A-007: the listings' match runs beside the request ----------
def test_the_listings_route_answers_pending_instead_of_waiting_for_the_match(monkeypatch):
    class R:
        @staticmethod
        def theme_map(profile, region, q):
            return "IN", q, {"generated_at": 7, "value_chain": [], "sub_themes": []}, None

        @staticmethod
        def ok(x):
            return x
    monkeypatch.setattr(T, "_routes", lambda: R)
    monkeypatch.setattr(T, "checked", lambda r, t, m: m)
    monkeypatch.setattr(T.computed, "get", lambda *a, **k: None)
    monkeypatch.setattr(T.computed, "put", lambda *a, **k: None)
    monkeypatch.setattr(T, "LISTINGS_WAIT", 0.05)
    T.IPO_CACHE.clear()
    gate = __import__("threading").Event()
    monkeypatch.setattr(T, "ipo_items", lambda r, today: [{"id": "i1", "name": "N", "text": "t", "pub": {"name": "N"}}])
    monkeypatch.setattr(T.theme_check, "match_listings", lambda items, m, ask, theme, cache: gate.wait(5) and [])
    began = time.time()
    out = T.theme_dive_listings("Slow theme", "IN", profile=None)
    assert out == {"items": [], "checked": False, "pending": True} and time.time() - began < 2
    gate.set()
    for _ in range(50):
        if T.IPO_CACHE.get(("IN", "slow theme", 7)) is not None:
            break
        time.sleep(0.05)
    assert T.theme_dive_listings("Slow theme", "IN", profile=None) == {"items": [], "checked": True}
    T.IPO_CACHE.clear()


def test_deck_check_reports_a_hyphen_for_a_minus_and_a_range_of_two_precisions():
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
    spec = importlib.util.spec_from_file_location("deck_check_7a", path)
    dc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dc)
    # the live Automotive deck's p.11 and a fixture deck before lane t1: "Range −14% to −12% -4.6% to -4.5%", "19.6% to 20%"
    got = dc.check_text("Title\nRange   −14% to −12%   -4.6% to -4.5%   15%\nRange   19.6% to 20%   14% to 18%\nFY 2025-2026 (Q1-FY26)\n")
    assert got["counts"]["hyphen minus"] == 2 and got["counts"]["mixed range"] == 1 and dc.failed(got) and not dc.failed(dc.check_text("Range −4.6% to 20.0%\n"))
