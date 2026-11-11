"""R16 (owner, 7 Nov: the Automotive theme deck): the theme deck's generator checks its own figures, for every theme. Each check of the
handoff (THEMES-DECK-HANDOFF parts 1 to 5) on synthetic theme data: one-off earnings, broken series, operating figures held or old, one
quarter per median, false precision, mixed bases, membership, segments, peers of similar size, findings with page references, "Worth a
watch" by rule, the shorter deck, the headlines and the layout."""
import copy
import re
from datetime import date, datetime, timezone

from app import deck
from app.intel import theme_base as B
from app.intel import theme_data as D
from tests.test_export import plain, table_of, texts, view
from tests.test_theme1 import CHECKED, FACTS, TODAY, facts, src

NOW = datetime(2026, 11, 7, 6, 0, tzinfo=timezone.utc)
ADVICE = ("buy", "sell", "avoid", "attractive", "expensive", "cheap", "undervalued", "overvalued", "recommend", "target price")


def build(checked=None, facts_=None, **kw):
    f = {**FACTS, **(facts_ or {})}
    return D.build("IN", "Test theme", checked or CHECKED, D.Sources(TODAY, facts=f.get, index_rows=kw.pop("index_rows", lambda: []), **kw))


def slides_of(v):
    return deck.theme_plan(v, now=NOW)[0]


# ---------- part 1: data checks ----------
def test_a_net_margin_above_the_ebitda_margin_is_a_one_off_left_out_of_the_net_median_with_both_aggregates_said():
    gain = facts("GAIN", "Gain Co", [1000, 1100, 1200, 1300], [6, 6, 6, 6], [30, 30, 30, 320])      # 24.6% net on a 6% EBITDA margin
    two = {**CHECKED, "value_chain": [CHECKED["value_chain"][0], {**CHECKED["value_chain"][1], "companies": CHECKED["value_chain"][1]["companies"]
                                                                    + [{"name": "Gain Co", "ticker": "GAIN", "what": "makes cells"}]}]}
    out = build(two, {"GAIN": gain})
    cells = out["layers"][1]
    row = next(c for c in cells["companies"] if c["symbol"] == "GAIN")
    assert row["one_off"] and row["net"] > row["ebitda"]
    assert cells["one_off"] == ["GAIN"] and cells["stats"]["net"]["n"] == 2 and cells["net_all"]["n"] == 3
    ch = out["checks"]
    assert [x["symbol"] for x in ch["one_off"]] == ["GAIN"] and ch["net_with"] != ch["net_without"]
    v = view()
    v["checks"] = {**v.get("checks", {}), "one_off": ch["one_off"], "net_with": 9.9, "net_without": 7.7}
    t = texts(slides_of(v))
    # changed on purpose (R27): the anomaly is flagged, no cause guessed ("a one-off gain"); the filing would show why
    assert "Net above EBITDA margin" in t and "the median net margin is 7.7% without them, 9.9% with them" in t
    assert "one-off" not in t.lower() and "the filing would show why" in t
    assert not D.one_off(10, 9) and not D.one_off(-5, -1) and D.one_off(6, 24.6)


def test_the_theme_net_margin_over_time_never_carries_a_one_off_year():
    gain = facts("GAIN", "Gain Co", [1000, 1100, 1200, 1300], [6, 6, 6, 6], [30, 30, 30, 900])
    h = D.layer_history([D.company_row("IN", s, f) for s, f in (("MINEA", FACTS["MINEA"]), ("MINEB", FACTS["MINEB"]), ("GAIN", gain))])
    assert h["one_off"] == ["GAIN"] and h["net_n"] == 2 and h["n"] == 3
    assert h["net"][-1] < h["ebitda"][-1]


def test_a_demerger_or_a_new_listing_breaks_the_series_and_its_growth_is_not_worked_out():
    split = facts("SPLIT", "Split Co", [5000, 5200, 5400, 1900], [10, 10, 10, 10], [300, 300, 300, 100])      # the year after a demerger
    new = {**facts("NEWCO", "New Co", [1000], [12], [80]), "years": [{"year": "Mar 2026", "sales": 1000, "profit": 80, "opm": 12}]}
    assert D.series_break(D.company_row("IN", "SPLIT", split)) and D.series_break(D.company_row("IN", "NEWCO", new))
    assert not D.series_break(D.company_row("IN", "MINEA", FACTS["MINEA"]))
    two = {**CHECKED, "value_chain": [{**CHECKED["value_chain"][0], "companies": CHECKED["value_chain"][0]["companies"] + [
        {"name": "Split Co", "ticker": "SPLIT", "what": "mines ore"}, {"name": "New Co", "ticker": "NEWCO", "what": "mines ore"}]}, CHECKED["value_chain"][1]]}
    out = build(two, {"SPLIT": split, "NEWCO": new})
    lead = {x["symbol"]: x for x in out["sections"]["leaders"]}
    assert lead["SPLIT"]["sales_1y"] is None and lead["NEWCO"]["sales_1y"] is None and lead["MINEA"]["sales_1y"] is not None
    assert {x["symbol"] for x in out["checks"]["series"]} == {"SPLIT", "NEWCO"}
    assert out["sections"]["growth"]["aggregate"]["revenue_1y"]["n"] == 4           # the two broken series are out of the totals


BIZ = {"metric": "Total sales", "unit": "units", "span": "month", "period": "2026-10", "value": 75426, "prev": 70000, "year_ago": 60000,
       "change_prev": 7.8, "change_year": 25.7, "filed": "2026-11-01", "url": "https://example.com/f", "exchange": "NSE", "points": []}


def test_operating_figures_with_a_prior_shared_by_two_companies_or_a_wild_move_are_held_and_old_ones_marked():
    rows = [{**BIZ, "symbol": "PV", "name": "PV Co", "prev": None, "change_prev": None, "year_ago": 37530, "change_year": 101.0},
            {**BIZ, "symbol": "CV", "name": "CV Co", "value": 47652, "prev": None, "change_prev": None, "year_ago": 37530, "change_year": 27.0},
            {**BIZ, "symbol": "MM", "name": "MM Co", "value": 38563, "prev": 114737, "change_prev": -66.4, "year_ago": 100298, "change_year": -61.6},
            {**BIZ, "symbol": "OK", "name": "OK Co"}]
    out = {r["symbol"]: r for r in D.hold_suspect(rows)}
    assert out["PV"]["year_ago"] is None and out["PV"]["change_year"] is None and "another company's" in out["PV"]["held"]
    assert out["CV"]["year_ago"] is None and out["CV"]["held"]
    assert out["MM"]["prev"] is None and out["MM"]["change_prev"] is None and "−" not in out["MM"]["held"] and "-66.4%" in out["MM"]["held"]
    assert out["OK"]["held"] is None and out["OK"]["change_year"] == 25.7
    sec = D.business_section([{"layer": "L", "companies": [{"symbol": s} for s in ("PV", "CV")]}], [], {}, lambda s: next(r for r in rows if r["symbol"] == s))
    assert {x["symbol"] for x in sec["held"]} == {"PV", "CV"}
    old = {**BIZ, "symbol": "BF", "name": "BF Co", "span": "quarter", "period": "2025-06", "filed": "2025-08-06"}
    assert deck.biz_stale(old, date(2026, 11, 7)) and not deck.biz_stale(BIZ, date(2026, 11, 7))
    slides = []
    deck._biz_slides(slides, "Layer 1 · L: operating figures", [old, {**out["PV"]}], "E", date(2026, 11, 7))
    t = table_of(slides, "Layer 1")
    assert t["rows"][0][1] == "Q1 FY26 (old)" and t["rows"][1][4] == "held"
    assert t["rows"][0][7] == {"text": "06 Aug 2025", "url": "https://example.com/f"}          # the filing's day only: never clipped to "06 Aug 2025 …"


def test_one_quarter_per_median_and_newer_results_filed_but_not_read_are_marked():
    rows = [{"symbol": f"S{i}", "name": f"Co {i}", "quarter": {"of": "Sep 2026 vs Sep 2025", "sales": 10.0 + i, "profit": 5.0}} for i in range(3)]
    rows += [{"symbol": "MM", "name": "MM Co", "quarter": {"of": "Jun 2026 vs Jun 2025", "sales": 27.8, "profit": 37.0}},
             {"symbol": "BO", "name": "BO Co", "quarter": {"of": "Jun 2026 vs Jun 2025", "sales": 22.0, "profit": -36.7}}]
    q = D.quarter_section(rows, [{"symbol": "MM", "date": "2026-11-05"}])
    assert q["quarter"] == "Sep 2026" and q["sales"]["n"] == 3 and q["sales"]["median"] == 11.0
    late = {x["symbol"]: x for x in q["earlier"]}
    assert late["MM"]["filed_unread"] == "2026-11-05" and late["BO"]["filed_unread"] is None
    v = view()
    v["sections"]["quarter"] = q
    slides = slides_of(v)
    # changed on purpose (R19): the latest quarter is a summary page; the companies on an earlier quarter and those with newer results filed are named
    q_lines = next(it for s in slides if s.title == "The latest quarter against a year earlier" for b in s.blocks if b["kind"] == "cards" for it in b["items"])["lines"]
    assert any("still on an earlier quarter, left out of the median: MM Co, BO Co" in x for x in q_lines)
    assert any(x == "Newer results filed but not yet in the figures: MM Co." for x in q_lines)
    # changed on purpose (m2): "Dated company updates", the day in its own column beside the status and the source
    watch = table_of(slides, "Dated company updates")
    assert any(r[0] == "MM Co" and r[1].startswith("Quarterly results; the figures in this deck are still") and r[2:5] == ["05 Nov 2026", "Announced", "Results filing"]
               for r in watch["rows"])


def test_whole_point_margins_print_without_false_precision_and_a_gap_within_rounding_is_not_called():
    assert deck._pcw(13.0, True) == "13%" and deck._pcw(16.5, True) == "16.5%" and deck._pcw(13.0, False) == "13.0%"
    assert D.pts(13.0, True) == "13%" and D.pts(-11.0, True) == "−11%"
    block = {"stats": {"ebitda": {"median": 13.0, "n": 3}}, "left_out": 0, "stats_over": "own", "companies": [1]}
    assert D.margin_line(block, 14.0) is None                                           # 1.0 point below: within the rounding of whole points
    assert D.margin_line(block, 15.5) is None          # changed on purpose (R27): the whole map's median is in no table, so never quoted
    r = D.company_row("IN", "MINEA", FACTS["MINEA"])
    assert r["ebitda_dp"] == 0 and D.company_row("IN", "MINEA", {**FACTS["MINEA"], "years": [{**y, "opm": y["opm"] + 0.4} for y in FACTS["MINEA"]["years"]]})["ebitda_dp"] == 1


def test_the_chain_names_a_highest_and_lowest_only_among_its_own_layers_of_two_or_more(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    blocks = [{"layer": "A", "n": 3, "revenue": 1, "official": False, "stats": {"ebitda": {"median": 17.0, "n": 3}}, "companies": []},
              {"layer": "B", "n": 3, "revenue": 1, "official": False, "stats": {"ebitda": {"median": 13.0, "n": 3}}, "companies": []},
              {"layer": "Official CV", "n": 2, "revenue": 1, "official": True, "stats": {"ebitda": {"median": 9.5, "n": 2}}, "companies": []},
              {"layer": "Lone", "n": 1, "revenue": 1, "official": False, "stats": {"ebitda": {"median": 30.0, "n": 1}}, "companies": []}]
    c = D.chain_table(blocks)
    assert (c["highest"], c["lowest"]) == ("A", "B") and c["compared"] == ["A", "B"]
    close = [{**blocks[0], "stats": {"ebitda": {"median": 14.0, "n": 3}}}, blocks[1]]
    # changed on purpose (R17-011): a gap within the rounding is said, with the layers counted, never left to a sentence that isn't checked
    assert D.chain_table(close)["highest"] is None
    assert D.chain_table(close)["line"] == "The median EBITDA margins of the 2 layers with at least 3 companies are within 1.0 points of each other, the rounding of whole points."   # R20: a base of 3


def test_the_valuation_says_its_bases_the_loss_makers_left_out_and_each_medians_count():
    v = view()
    v["sections"]["valuation"].update(losses=2, n=6)
    v["layers"][0]["stats"]["roce"] = {**(v["layers"][0]["stats"]["roce"] or {}), "n": 1, "median": 15.0, "min": 15.0, "max": 15.0}
    slides = slides_of(v)
    t = texts(slides)
    # changed on purpose (R27, P2): how each is worked out lives on the notes page; the valuation page points there once
    assert "A loss-maker has no P/E: 2 companies left out of the P/E median." in t and "How each is worked out, and who the comparable peers are: p. " in t
    assert "Market value over net profit of the last four quarters" in t and "P/E: the price over the last four" not in t
    layer = table_of(slides, "Layer 1 · Mining")
    # changed on purpose (R20): a median of fewer than 3 companies isn't shown as one: "–" with its count, the companies' own values above it
    med = next(r for r in plain(layer["rows"]) if r[0].startswith("Median"))
    # changed on purpose (R25): a count beside the layer's own reads "N of M" ("– (1 of 2)"), the layer's full count alone ("– (2)")
    assert med[0] == "Median (companies)" and "– (2)" in med and "– (1 of 2)" in med
    assert "P/E, the 4 companies with one (67% of 6; 2 loss-makers with none)" in [r[0] for r in table_of(slides, "Valuation")["rows"]]


# ---------- part 2: classification ----------
def test_a_company_whose_own_words_dont_show_the_work_is_listed_not_confirmed_and_out_of_every_median_and_total():
    words = D.theme_words({"sector": "Automotive sector (India)", "placements": {"industries": ["Auto Components & Equipments", "Passenger Cars & Utility Vehicles"]},
                           "value_chain": [{"layer": "Vehicle assembly and brands"}], "sub_themes": [{"name": "Commercial vehicles", "detail": "Trucks and buses."}]}, "Automotive")
    assert D.membership({"base": True, "basis": "industry", "what": "Olectra makes electric buses and composite insulators"}, words) == "core"
    assert D.membership({"base": True, "basis": "industry", "what": "Ebix supplies on-demand software to insurance companies"}, words) == "unverified"
    # changed on purpose (R17-012): own words that say nothing of the work (none, or "established in 1981") leave the exchange's industry standing
    assert D.membership({"base": True, "basis": "industry", "what": ""}, words) == "core"
    assert D.membership({"base": True, "basis": "industry", "what": "The Company was established in 1981"}, words) == "core"
    assert D.membership({"base": False, "verified": True, "what": "x"}, words) == "exposure"
    assert D.membership({"base": False, "verified": False, "what": ""}, words) == "unverified"
    assert D.membership({"ticker": "OLD"}, words) == "core"                                  # a map from before the checks
    ins = facts("EBIX", "Ebix Co", [500, 600, 700, 800], [30, 30, 30, 30], [100, 120, 140, 160], cap=900000)
    layers = [{**CHECKED["value_chain"][0], "companies": [{**c, "base": True, "basis": "industry", "verified": True} for c in CHECKED["value_chain"][0]["companies"]]
               + [{"name": "Ebix Co", "ticker": "EBIX", "base": True, "basis": "industry", "verified": False, "what": "supplies insurance software"}]},
              CHECKED["value_chain"][1]]
    out = build({**CHECKED, "value_chain": layers}, {"EBIX": ins})
    mining = out["layers"][0]
    assert mining["unverified"] == ["EBIX"] and mining["n"] == 2 and mining["listed"] == 3 and mining["stats"]["ebitda"]["n"] == 2
    assert out["status"]["EBIX"] == "unverified" and out["sections"]["size"]["companies"] == 5          # out of the totals
    assert "EBIX" not in [b["symbol"] for b in out["sections"]["size"]["biggest"]]


def test_a_company_runs_several_businesses_when_its_own_segments_say_so_not_by_a_list():
    row = {"symbol": "MM", "industry": ["Passenger Cars"]}
    assert D.is_diversified(row, [{"name": "Auto", "share_pct": 55}, {"name": "Farm", "share_pct": 30}, {"name": "Finance", "share_pct": 15}])
    assert not D.is_diversified({"symbol": "M&M", "industry": []}, [{"name": "Auto", "share_pct": 80}, {"name": "Farm", "share_pct": 20}])   # segments overrule the list
    assert D.is_diversified({"symbol": "X", "industry": ["Diversified"]}) and not D.is_diversified({"symbol": "X", "industry": ["Metals"]})
    out = build(segments=lambda s: [{"share_pct": 50}, {"share_pct": 50}] if s == "CELLA" else None)
    assert "CELLA" in out["company_wide"]


def test_valuation_is_set_beside_listed_companies_of_similar_market_value_with_growth_and_roce():
    # changed on purpose (R27): ten peers of the companies' own sector (the minimum), of similar value; another sector's never count
    market = [{"symbol": f"P{i}", "market_cap": 20000 + i * 1000, "pe": 10.0, "sales_cagr_3y": 5.0, "roce": 10.0, "sector": "Metals"} for i in range(10)]
    market += [{"symbol": "HUGE", "market_cap": 5_000_000, "pe": 90.0, "sales_cagr_3y": 50.0, "roce": 50.0, "sector": "Metals"},
               {"symbol": "OTHER", "market_cap": 20000, "pe": 90.0, "sales_cagr_3y": 50.0, "roce": 50.0, "sector": "Chemicals"}]
    out = build(index_rows=lambda: market)
    peers = out["sections"]["valuation"]["peers"]
    assert peers["pe"]["peers"] == 10.0 and peers["pe"]["premium"] > 0 and peers["roce"]["peers"] == 10.0 and peers["sales_3y"]["peers"] == 5.0
    v = view()
    v["sections"]["valuation"]["peers"] = peers
    slides = slides_of(v)
    val = table_of(slides, "Valuation")
    # R22: the population said (R27: the column is the comparable peers, sector first, then size)
    assert "Comparable peers" in val["head"] and any(r[0].startswith("ROCE, companies with comparable peers") for r in val["rows"])
    # changed on purpose (R17-010): one P/E basis, the companies with comparable peers against their peers' median, in the headline and the table
    sub = next(s.subtitle for s in slides if s.title == "Valuation")
    pp = peers["pe"]
    # changed on purpose (R18): one formatter, whole figures print whole (21x, 110%, 10x)
    w = deck.whole_figures
    # changed on purpose (R27): the peer set is said and is the companies' own sector of similar value; never the whole market
    # changed on purpose (R35): the line names the close its prices are of (the peers' and the companies' own latest price day)
    assert pp["as_of"] == "2026-10-05" and pp["symbols_n"] == 10 and pp["symbols"] == sorted(f"P{i}" for i in range(10))
    assert sub == w(f"Median P/E {pp['theme']:.1f}x for the {pp['n']} companies with comparable peers (own sector, similar market value, outside the "
                    f"theme), {pp['premium']:.1f}% above their peers' median of 10.0x (prices at the 2026-10-05 close); 1 with no comparable peer set (left out)")
    row = next(r for r in val["rows"] if r[0].startswith("P/E, companies with comparable peers"))
    assert row[1] == w(f"{pp['theme']:.1f}x") and row[4] == "10x" and row[2] == w(f"{pp['premium']:.1f}% above peers")
    assert pp["premium"] == round((pp["theme"] / pp["peers"] - 1) * 100, 1)        # the ratio of the two medians the table shows
    # R27: the same companies against peers with no sector (no comparable set): counted, never compared with the whole market
    bare = build(index_rows=lambda: [{k: x for k, x in m.items() if k != "sector"} for m in market])["sections"]["valuation"]["peers"]
    assert bare["pe"]["n"] == 0 and bare["pe"]["none"] >= 1 and "market" not in bare["pe"]["sets"]


def test_the_cover_and_the_next_slide_say_how_many_companies_the_figures_are_for_and_their_share_of_value():
    v = view()
    v["members"] = v["members"] + [{"symbol": f"Z{i}", "name": f"Z {i}", "layer": "Cells", "cap": 100.0, "by": "Official industry"} for i in range(4)]
    v["placements"] = {**v["placements"], "total": 10}
    cov = deck.coverage(v)
    # changed on purpose (R27): the share names its denominator, whose market value it is a share of; (R28) "with figures" is of the
    # confirmed companies only: the unconfirmed one with figures is listed, never counted
    assert cov["text"] == f"10 in the theme · 4 with figures ({cov['share']}% of the combined market value of the 9 of 10 with one)" and cov["share"] < 100
    slides = slides_of(v)
    cover = dict((t[0], t[1]) for t in next(b for b in slides[0].blocks if b["kind"] == "stats")["items"])
    assert cover["With figures"] == str(cov["n"]) and "Their market value" in cover               # R20: the count, its share beneath
    # R19: no overview page; the findings say it (R27: as the four reconciled counts)
    assert f"{deck.counts_words(deck.reconciled_counts(v, cov))}." in texts([s for s in slides if s.title == "Key findings"])


# ---------- part 3: findings ----------
def full():
    from tests.test_deck_look import full_view
    return full_view()


def test_the_findings_come_first_with_page_references_that_point_at_their_slides():
    slides = slides_of(full())
    titles = [s.title for s in slides]
    assert titles.index("Key findings") < titles.index("The value chain by layer")
    cards = next(b for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards")["items"]
    # changed on purpose (R18): with no layer comparison the figures support (fewer than two layers of two companies with a margin), no
    # "Where the margin sits" card that says it can't be done
    assert [c["title"] for c in cards] == ["Growth beside margin", "Price beside growth and returns", "What changed",
                                           "How far the figures go", "Dated company updates"]
    page = {re.sub(r" \(\d+ of \d+\)$", "", s.title): i for i, s in reversed(list(enumerate(slides, 1)))}
    refs = {c["title"]: c["note"] for c in cards}                                     # the page reference, as the card's note: never cut
    assert refs["Price beside growth and returns"] == f"p. {page['Valuation']}"
    assert refs["How far the figures go"] == f"p. {page['Data confidence']}"
    t = texts(slides)
    assert "⟦" not in t and "⟧" not in t


def test_worth_a_watch_is_a_rule_based_list_each_with_its_factual_trigger_and_no_advice():
    v = full()
    v["sections"]["ownership"]["holdings"].append({"symbol": "TEN", "name": "Tenneco", "quarter": "2026-09-30", "promoter": 59.8, "institutions": 14.9,
                                                   "promoter_change": -15.0, "institutions_change": 8.0})
    v["sections"]["events"]["results_due"] = [{"symbol": "MINEA", "name": "Mine A", "date": "2026-11-09", "purpose": "Financial Results"},
                                              {"symbol": "MINEB", "name": "Mine B", "date": "2026-12-20", "purpose": "Financial Results"}]
    w = deck.watch_list(v, date(2026, 11, 7))
    facts_ = {x["name"]: x["fact"] for x in w}
    assert facts_["Cell B"] == "Resignation of an auditor"                    # changed on purpose (m2): the event, as a neutral fact
    assert facts_["Tenneco"] == "Promoters' stake −15.0 pts to 59.8% in the quarter to Sep 2026"
    assert facts_["Mine A"] == "Financial results" and "Mine B" not in facts_                           # scheduled in the next week only
    assert next(x for x in w if x["name"] == "Mine A")["status"] == "Scheduled"                         # m2: upcoming results read as scheduled
    slides = slides_of(v)
    wt = texts([s for s in slides if s.title.startswith("Dated company updates")])
    assert "picked by fixed rules, not a view" in wt
    for word in ADVICE:
        assert not re.search(rf"\b{word}\b", wt.lower()), word


def test_tailwinds_say_a_recent_headline_exists_and_name_the_layer_they_are_about():
    v = view()
    v["tailwinds"] = [{"text": "Cells demand rises with a battery subsidy", "status": "current", "source": {"headline": "Subsidy", "at": "2026-09-01", "outlet": "A", "url": "u"}}]
    items = next(b for s in slides_of(v) if s.title == "Tailwinds and risks" for b in s.blocks if b["kind"] == "flow")["items"]
    assert items[0]["tags"][1][0] == "Dated source" and items[0]["sub"].endswith("Layer: Cells")          # R21: "Dated source" / "General background (AI, no dated source)"


# ---------- part 4: shorter, cleaner ----------
def test_a_sub_themes_operating_figures_already_shown_under_its_layer_are_not_repeated():
    v = full()
    row = v["business"]["layers"][0]["rows"][0]
    v["subs"] = [{"name": "Ore", "detail": "", "companies": [{"symbol": "MINEA", "name": "Mine A", "what": "mines ore", "cap": 1.0, "sales_1y": 1.0, "ebitda": 10.0}]}]
    v["business"]["subs"] = [{"name": "Ore", "rows": [row]}]
    assert not any(s.title.startswith("Ore: operating figures") for s in slides_of(v))


def test_ownership_lists_the_changes_only_with_quarters_as_months_and_no_signed_zero():
    v = full()
    v["sections"]["ownership"]["holdings"] = [
        {"symbol": "A", "name": "A Co", "quarter": "2026-09-30", "promoter": 50.0, "institutions": 10.0, "promoter_change": 0.01, "institutions_change": -0.2},
        {"symbol": "B", "name": "B Co", "quarter": "2026-09-30", "promoter": 40.0, "institutions": 20.0, "promoter_change": 0.8, "institutions_change": 0.1},
        {"symbol": "C", "name": "C Co", "quarter": "2026-09-30", "promoter": 30.0, "institutions": 20.0, "promoter_change": -0.02, "institutions_change": 1.7}]
    # changed on purpose (R19, the owner: "keep the important ones"): ownership is a per-company list on the theme's page, no deck page; a stake
    # move of a point or more is in "Dated company updates" (m2: its name)
    slides = slides_of(v)
    assert "Ownership" not in [s.title for s in slides]
    assert not any("B Co" in r[0] for r in table_of(slides, "Dated company updates")["rows"])  # 0.8 points: under the rule
    assert deck._pts(-0.04) == "0.0 pts" and deck._pts(0.04) == "0.0 pts" and deck._pts(-1.25) == "−1.2 pts"


def test_red_flags_are_said_once_a_rights_issue_is_a_corporate_action_and_an_auditor_resigning_comes_first():
    items = [{"symbol": "OLA", "at": "2026-10-07", "category": "fund_raise", "label": "Rights issue (fund raise)"},
             {"symbol": "OLA", "at": "2026-10-07", "category": "fund_raise", "label": "Rights issue (fund raise)"},
             {"symbol": "APL", "at": "2026-10-06", "category": "resign", "label": "Director or key officer resigned"},
             {"symbol": "APL", "at": "2026-10-06", "category": "resign", "label": "Director or key officer resigned"},
             {"symbol": "TML", "at": "2026-10-31", "category": "auditor", "label": "Auditor resigned"}]
    flags = D.flagged_rows(items, {})
    assert [(x["symbol"], x["label"]) for x in flags] == [("TML", "Auditor resigned"), ("APL", "Director or key officer resigned")]
    assert [x["symbol"] for x in D.fund_raises(items, {})] == ["OLA"]
    v = full()
    v["sections"]["ownership"]["red_flags"] = [{**x, "name": x["symbol"]} for x in reversed(flags)]
    v["sections"]["ownership"]["fund_raises"] = [{**x, "name": "OLA"} for x in D.fund_raises(items, {})]
    # changed on purpose (R19): no events page; an auditor's resignation is a dated fact in "Dated company updates" (m2: its name)
    slides = slides_of(v)
    assert "Events" not in [s.title for s in slides]
    assert any(r[0] == "TML" and r[1] == "Resignation of an auditor" and r[3] == "Announced" for r in table_of(slides, "Dated company updates")["rows"])


def test_quote_pages_picks_and_other_markets_headlines_are_left_out():
    # LIVE6-018 (updated on purpose): a headline is kept only with its source
    keep = [{"headline": "Mahindra & Mahindra Q2 results: Farm equipment revenue grows", "company": "M&M", "source": "Paper"},
            {"headline": "Skoda Auto Volkswagen India cedes land for crash test site", "company": None, "source": "Paper"},
            {"headline": "Press Release", "company": "Tata Motors", "source": "Exchange filing"}]
    drop = [{"headline": "Mahindra & Mahindra Share Price - Live NSE: M&M Stock Price & Chart", "company": "M&M"},
            {"headline": "MAHINDRA & MAHINDRA LTD Option Chain - Live", "company": "M&M"},
            {"headline": "13,613 Put Contracts at Rs 3,000 Strike on Mahindra & Mahindra Ltd", "company": "M&M"},
            {"headline": "Diwali Stock Picks 2026: L&T, Adani Power, Maruti Suzuki India", "company": "Maruti"},
            {"headline": "Maruti Suzuki India Ltd Shows Mixed Technical Signals Amid Price Momentum Shift", "company": "Maruti"},
            {"headline": "Mexico's Automotive Sector Gains Tax Relief Under 2027 Plan", "company": None},
            {"headline": "Schaeffler to Cut Further 3,460 Jobs in Europe as Auto Industry Deteriorates", "company": None}]
    assert all(D.headline_kept(x, "IN") for x in keep)
    assert not any(D.headline_kept(x, "IN") for x in drop)


def test_what_a_company_does_is_a_business_sentence_never_a_heading_a_glued_word_or_a_sales_line():
    assert B.one_line("**Company Overview ** Steel Strips Wheels Ltd was incorporated in 1985. It manufactures steel wheels for cars.") == "It manufactures steel wheels for cars"
    assert B.one_line("Incorporatedin1994, Uniparts India provides engineering systems to off-highway vehicles.") == "Uniparts India provides engineering systems to off-highway vehicles"
    assert B.one_line("Hero MotoCorp, the world's largest maker of motorcycles, reported total dispatches of 7,34,403 units in October 2026. "
                      "Hero MotoCorp makes motorcycles and scooters.") == "Hero MotoCorp makes motorcycles and scooters"
    assert B.one_line("Incorporated in 1983, RACL Geartech Ltd manufactures automotive gears Business Overview: RACL makes gears.") == "RACL Geartech Ltd manufactures automotive gears"
    long = B.one_line("It makes " + "fuel injection systems, power tools, " * 12)
    assert long.endswith("…") and not long[:-1].endswith(("sys", "too"))                     # cut at a word, with an ellipsis
    v = view()
    v["members"][0]["what"] = "**Company Overview ** Mine A digs ore in Odisha."
    t = texts(slides_of(v))
    assert "**" not in t and "Company Overview" not in t


def test_the_deck_is_shorter_every_companys_own_words_in_the_appendix():
    slides = slides_of(full())
    titles = [s.title for s in slides]
    # changed on purpose (R19): every company's own words are on the theme's page; the appendix is one table of every confirmed company's figures
    assert "Every company in this theme" not in titles and titles.index("How to read this deck") < titles.index("Every company's figures")
    # changed on purpose (R25): the page on how the figures are built follows the notes, before the appendix
    at = titles.index("How to read this deck") + 1
    while titles[at].startswith(deck.NOTES_TITLE):
        at += 1
    assert at > titles.index("How to read this deck") + 1 and all(s.title.startswith("Every company's figures") for s in slides[at:])


# ---------- part 5: layout ----------
def test_no_header_word_or_figure_is_broken_inside_a_word():
    b = {"head": ["Layer", "Companies", "Revenue", "EBITDA margin", "Net margin", "ROCE"], "widths": [2.9, 1.0, 1.2, 1.2, 1.1, 1.0],
         "rows": [["Auto Components & Equipments", "32", "₹3.04 lakh cr", "14%", "6.7%", "19.1%"]]}
    lay = deck.table_layout(b, 7.3, 4.0)
    for hd, w in zip(b["head"], lay["widths"]):
        for word in hd.split():
            assert deck._width(word, lay["size"], True) <= w - 0.2 + 1e-6, word
    assert len(deck.wrap("₹3.04 lakh cr", lay["size"], lay["widths"][2] - 0.2)) == 1
    for name, slides in ((n, s) for n, s in __import__("tests.test_deck_look", fromlist=["decks"]).decks() if n.startswith("theme")):
        for s in slides:
            for blk in s.blocks:
                if blk["kind"] != "table":
                    continue
                x, y, w, h = blk["box"]
                lay = deck.table_layout(blk, w, h)
                for hd, cw in zip(blk["head"], lay["widths"]):
                    for word in str(hd).split():
                        assert deck._width(word, lay["size"], True) <= cw - 0.2 + 1e-6, f"{name}: {s.title}: {word}"


def test_the_contents_list_every_slide_of_a_long_part_and_layers_are_numbered_without_gaps():
    v = full()
    many = [{**v["layers"][0], "layer": f"Layer name {i}"} for i in range(14)]
    v["layers"] = many[:4] + [{"layer": "Financing", "description": "Lends.", "companies": [], "n": 0, "stats": {}, "company_wide": []}] + many[4:]
    v["business"] = None
    slides = slides_of(v)
    # changed on purpose (R18): one contents page lists every part with its first page (no divider before each part); a layer is one page
    contents = {r[0]: int(r[2]) for r in table_of(slides, "Contents")["rows"]}
    assert slides[contents["The value chain"] - 1].title in ("The value chain by layer", "Layer 1 · Layer name 0")
    assert [s.title for s in slides].count("Layer 14 · Layer name 13") == 1
    nums = [int(re.match(r"Layer (\d+) ·", s.title).group(1)) for s in slides if re.match(r"Layer \d+ ·", s.title)]
    assert sorted(set(nums)) == list(range(1, 15))                                            # Layer 4, then Layer 5: no gap for an empty layer


def test_one_minus_sign_and_no_internal_wording_anywhere_in_the_deck():
    v = full()
    v["layers"][1]["companies"][0]["ebitda"] = -11.0
    t = texts(slides_of(v))
    assert not re.search(r"(?<![\w/])-\d", t)                                                 # no hyphen-minus before a figure
    assert deck._pc(-11.0) == "−11.0%" and deck._pc(-0.04) == "0.0%" and deck._chg(-4.0) == "−4.0%" and deck._times(-5.3) == "−5.3x"
    for internal in ("when this deck was made", "weren't read", "Checked"):
        assert internal not in t, internal
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", t)                                         # no raw ISO date


def test_every_closing_note_fits_its_box():
    for name, slides in __import__("tests.test_deck_look", fromlist=["decks"]).decks():
        if not name.startswith("theme"):
            continue
        for s in slides:
            for b in s.blocks:
                if b["kind"] == "text" and b.get("color") == deck.MUTED and b.get("size") == deck.BODY_MIN:
                    x, y, w, h = b["box"]
                    shown = deck.fit_paras(b["paras"], deck.BODY_MIN, w, h)
                    assert shown == b["paras"], f"{name}: {s.title}: {b['paras'][0][:60]}"
