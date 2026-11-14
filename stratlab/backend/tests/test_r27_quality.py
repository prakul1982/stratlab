"""Release 27, quality lane (the owner's outside review of the eight live R26 decks): every deck states four reconciled counts and every share
of value names its denominator; no cause is inferred from numbers (an anomaly is flagged, "the filing would show why"); a comparison
headlines only on enough companies, enough coverage, one business model and one period basis; peers are the company's own sector first,
never the whole market; and a publication gate runs before a deck is stored, its result kept with the deck and shown in Admin -> Library.
Generic: every synthetic theme (the earlier ones, the eight benchmark families and the R27 structures: chemicals, real estate, telecom in
India and the US, US retail, utilities, metals and mining). Synthetic data only."""
import logging
import re

import pytest

from app import computed, deck, library_admin
from app.intel import theme_data as D
from tests.synthetic_themes_r27 import decks as r27_decks
from tests.test_deck_look import full_view
from tests.test_export import plain, table_of, texts
from tests.test_r19_library import lib, store  # noqa: F401  (the shared store in memory, and the research pages' fake world)
from tests.test_research_api import api  # noqa: F401
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
from tests.test_r25_deck import EVERY
from tests.test_r25_deck import test_every_count_beside_a_layer_figure_is_n_of_its_companies as counts_n_of_m
from tests.test_r25_deck import test_no_layer_is_called_highest_fastest_or_slowest_on_a_base_under_three_or_against_itself as no_rank_under_three
from tests.test_r25_deck import test_the_notes_page_explains_only_the_figures_the_deck_shows_with_period_source_and_limits as notes_page

NEW = list(r27_decks())
ALL27 = [(n, v, s) for n, v, s in NEW] + EVERY
IDS27 = [n for n, _, _ in ALL27]


def engine_text(slides) -> str:
    """Every line the engine writes (the AI's tailwinds and risks, each with its own dated source, apart)."""
    return texts([s for s in slides if s.title != "Tailwinds and risks"])


# ---------- every rule on the new structures ----------
@pytest.mark.parametrize("name,v,slides", NEW, ids=[n for n, _, _ in NEW])
def test_every_earlier_deck_rule_holds_on_the_r27_structures(name, v, slides):
    every_rule(name, v, slides)
    counts_n_of_m(name, v, slides)
    no_rank_under_three(name, v, slides)
    notes_page(name, v, slides)
    assert slides[0].checked == [] and deck.check_deck(slides) == []


# ---------- 1. reconciled counts, denominators named ----------
@pytest.mark.parametrize("name,v,slides", ALL27, ids=IDS27)
def test_every_deck_states_the_four_counts_the_same_everywhere_and_every_share_names_its_denominator(name, v, slides):
    cov = deck.coverage(v)
    c = deck.reconciled_counts(v, cov)
    words = deck.counts_words(c)
    assert words.startswith(f"Considered {c['considered']:,} · ") and f"with figures {c['with_figures']:,}" in words
    assert "confirmed" in words and (not c["each"] or "in each calculation: " in words)
    conf = next(p for s in slides if s.title == "Data confidence" for b in s.blocks for p in b.get("paras") or [] if p.startswith("Counts:"))
    find = next(ln for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards" for it in b["items"] for ln in it["lines"]
                if ln.startswith("Considered"))
    assert conf.startswith(f"Counts: {words}.") and find == f"{words}."
    t = texts(slides)
    assert not deck._BARE_SHARE.search(t), deck._BARE_SHARE.findall(t)[:3]          # never "100% of value" without "of what"
    for m in re.finditer(r"(\d+)% of the (?:combined )?market value of (?:all (\d[\d,]*)|the (\d[\d,]*) of (\d[\d,]*) with one)", t):
        if m.group(2):
            assert int(m.group(2).replace(",", "")) == c["considered"]
        else:
            assert int(m.group(4).replace(",", "")) == c["considered"] and int(m.group(3).replace(",", "")) <= c["considered"]
    for m in re.finditer(r"\b(\d[\d,]*) with figures\b", t):                         # one count of companies with figures, wherever it is said
        # ...except the one line that adds the adjacent participants to it, naming both populations ("40 core members + 20 adjacent
        # participants = 60 with figures": e54, R54), whose core part is that count (updated on purpose)
        both = re.search(r"(\d[\d,]*) core members? \+ (\d[\d,]*) adjacent participants? = $", t[max(0, m.start() - 80):m.start()])
        if both:
            assert int(both.group(1).replace(",", "")) == c["with_figures"] and \
                int(both.group(1).replace(",", "")) + int(both.group(2).replace(",", "")) == int(m.group(1).replace(",", "")), m.group(0)
            continue
        assert int(m.group(1).replace(",", "")) == c["with_figures"], m.group(0)


def test_the_denominator_says_whose_market_value_and_how_many_have_one():
    assert deck.share_of_what(112, 112) == "the market value of all 112"
    assert deck.share_of_what(58, 112) == "the combined market value of the 58 of 112 with one"
    v = full_view()
    v["members"] = v["members"] + [{"symbol": f"Z{i}", "name": f"Z {i}", "layer": "Cells", "by": "Official industry"} for i in range(3)]
    cov = deck.coverage(v)
    assert cov["figs"].endswith(f"({cov['share']}% of {deck.share_of_what(cov['valued'], cov['total'])})")


def test_a_sentence_whose_counts_shares_or_periods_dont_reconcile_is_dropped_and_logged(caplog):
    counts, periods = {"considered": 112, "with_figures": 58, "confirmed": 60}, {"Sep 2026", "Mar 2026"}
    f = deck.reconcile_flag
    assert f("112 in the theme · 58 with figures (100% of value).", counts, periods) == "a share of value with no denominator"
    assert f("58 with figures (100% of the market value of all 112).", counts, periods) is None
    assert "with figures 57" in f("57 with figures.", counts, periods)
    assert "confirmed 61" in f("Considered 112 · confirmed 61 · with figures 58.", counts, periods)
    assert f("Quarter to Jun 2026: median revenue +5%.", counts, periods) == "period Jun 2026 is in no table"
    assert f("The quarter to Sep 2026 against the quarter to Sep 2025.", counts, periods) is None       # the year-ago base of a shown period
    v = full_view()
    slides = deck.theme_plan(v)[0]
    k = next(s for s in slides if s.title == "Key findings")
    card = next(b for b in k.blocks if b["kind"] == "cards")["items"][0]
    card["lines"] = card["lines"] + ["999 with figures (100% of value).", "Quarter to Jan 2019: median revenue +5%."]
    with caplog.at_level(logging.WARNING, logger="stratlab.deck"):
        gate = deck.publication_gate(slides, v)
    rec = next(x for x in gate["items"] if x["id"] == "reconcile")
    assert not rec["ok"] and rec["dropped"] == 2
    assert "999 with figures" not in texts(slides) and "Jan 2019" not in texts(slides) and "deck gate: reconcile" in caplog.text
    assert {d["rule"] for d in gate["dropped"]} == {"reconcile"}


def test_rounding_is_reconciled_a_sentence_never_states_more_precision_than_its_table():
    shown = D.shown_numbers(["19%", "12.4%"])
    assert D.claim_mismatches("a median of 19%", shown) == [] and D.claim_mismatches("a median of 12%", shown) == []
    assert D.claim_mismatches("a median of 19.4%", shown) == ["19.4%"]                # the table printed it whole
    assert D.claim_mismatches("a median of 12.6%", shown) == ["12.6%"]


# ---------- 2. no unsupported causes ----------
@pytest.mark.parametrize("name,v,slides", ALL27, ids=IDS27)
def test_no_cause_is_inferred_from_numbers_and_no_advice_or_forecast_is_written(name, v, slides):
    t = engine_text(slides)
    assert "one-off" not in t.lower(), re.findall(r".{40}one-off.{20}", t, re.I)[:2]
    assert not deck.CAUSE_WORDS.search(t), deck.CAUSE_WORDS.findall(t)[:3]
    for s in slides:
        for line in [s.subtitle or ""] + [ln for b in s.blocks if b["kind"] == "cards" and s.title != "Tailwinds and risks" for it in b["items"] for ln in it["lines"]]:
            assert deck.prose_flag(line) is None, (s.title, line)


def test_a_net_margin_above_the_ebitda_margin_is_flagged_as_an_anomaly_never_explained():
    v = full_view()
    v["checks"] = {**(v.get("checks") or {}), "one_off": [{"symbol": "X", "name": "X Ltd", "net": 24.6, "ebitda": 6.0}], "net_with": 9.9, "net_without": 7.7}
    slides = deck.theme_plan(v)[0]
    t = texts(slides)
    # changed on purpose (m2): a flag with no day is not a dated update; it is on the data-confidence page, still with no cause named
    assert "X Ltd (24.6% net, 6% EBITDA)" in t and "with them; the filing would show why." in t
    assert not any(x["name"] == "X Ltd" for x in deck.watch_list(v, __import__("datetime").date(2026, 11, 7)))
    assert "Net above EBITDA margin" in t and "one-off" not in t.lower() and not re.search(r"\bgains?\b", t, re.I)
    assert deck.prose_flag("Net margin is above the EBITDA margin: a one-off gain is in it.") == "cause: one-off gain"
    assert deck.prose_flag("Margins rose, driven by lower costs.") == "cause: driven by"
    assert deck.prose_flag("Revenue fell due to weak demand.") == "cause: due to"
    assert deck.prose_flag("Prices will rise next year.").startswith("advice or forecast")
    assert deck.prose_flag("The company sells steel and buys back shares through buybacks.") is None      # a business that sells is a fact
    assert deck.prose_flag("Net margin is above EBITDA margin; the filing would show why.") is None
    assert deck.prose_flag("Power generators sell electricity to the plants and the grid.") is None
    assert deck.prose_flag("Investors should sell the shares.").startswith("advice") and deck.prose_flag("Buy now.").startswith("advice")


def test_a_cause_or_advice_sentence_never_ships_from_a_card_a_headline_or_a_note(caplog):
    v = full_view()
    slides = deck.theme_plan(v)[0]
    k = next(s for s in slides if s.title == "Key findings")
    card = next(b for b in k.blocks if b["kind"] == "cards")["items"][0]
    card["lines"] = card["lines"] + ["Margins rose because costs fell."]
    val = next(s for s in slides if s.title == "Valuation")
    val.subtitle = val.subtitle + "; the shares look undervalued"
    note = next(s for s in slides if any(b["kind"] == "text" for b in s.blocks) and s.title not in ("Contents",) and s.kind == "content")
    tb = next(b for b in note.blocks if b["kind"] == "text")
    tb["paras"] = [tb["paras"][0] + " Growth was driven by exports."]
    with caplog.at_level(logging.WARNING, logger="stratlab.deck"):
        gate = deck.publication_gate(slides, v)
    prose = next(x for x in gate["items"] if x["id"] == "prose")
    assert not prose["ok"] and prose["dropped"] == 3
    t = texts(slides)
    assert "because costs fell" not in t and "undervalued" not in t and "driven by exports" not in t
    assert val.subtitle and "deck gate: prose" in caplog.text


# ---------- 3. headline eligibility ----------
def test_a_comparison_headlines_only_on_sample_coverage_one_model_and_one_period_basis(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    assert D.COVERAGE_MIN == 0.5
    assert D.headline_ok(3, 6) and not D.headline_ok(2, 3) and not D.headline_ok(3, 7) and D.headline_ok(4, 7)
    assert not D.headline_ok(21, 53) and D.headline_ok(27, 53)                      # the live Semis deck's "RPO growth -3.9% (21 of 53)"
    assert not D.headline_ok(5, 5, {"sparse": True, "line": "x"}) and D.headline_ok(5, 5, {"family": "f", "line": "x"}) and D.headline_ok(5, 5, None)
    assert D.period_basis([{"year": "Mar 2026"}, {"year": "Mar 2025"}]) == "full" and D.period_basis([{"year": "Mar 2026 9m"}]) == "part"
    assert D.period_basis([{"year": "Mar 2026"}, {"year": "Mar 2026 9m"}]) == "mixed" and D.period_basis([]) == ""
    assert D.same_basis(["full", "full", ""]) and not D.same_basis(["full", "part"]) and not D.same_basis(["mixed"])
    rows = [("A", 30.0, 3, 4), ("B", 10.0, 3, 9), ("C", 20.0, 5, 6)]
    assert D.rank_pair(rows, lambda t: t[1], lambda t: t[2]) == (rows[0], rows[1])
    assert D.rank_pair(rows, lambda t: t[1], lambda t: t[2], of=lambda t: t[3]) == (rows[0], rows[2])     # B: 3 of 9 is under half
    assert D.rank_pair(rows, lambda t: t[1], lambda t: t[2], basis=lambda t: "part" if t[0] == "C" else "full") is None


def block(name, n, k, med, model=None, year="Mar 2026"):
    # gl50 (R50, updated on purpose): a layer given no model has its way of earning read (READ), else no layer is ranked
    from tests.gl50_read import READ
    return {"layer": name, "n": n, "revenue": 100.0, "official": False, "model": dict(READ) if model is None else model, "stats": {"ebitda": {"median": med, "n": k}},
            "companies": [{"symbol": f"{name}{i}", "year": year} for i in range(n)]}


def test_the_value_chain_names_no_layer_whose_figure_covers_under_half_or_mixes_models_or_periods(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    c = D.chain_table([block("A", 4, 4, 40.0), block("B", 10, 4, 5.0), block("C", 6, 6, 20.0)])
    assert (c["highest"], c["lowest"]) == ("A", "C") and "B" not in c["compared"]                 # B: 4 of 10
    c = D.chain_table([block("A", 4, 4, 40.0, {"sparse": True}), block("B", 5, 5, 5.0), block("C", 6, 6, 20.0)])
    assert (c["highest"], c["lowest"]) == ("C", "B")                                              # A's models mostly unknown
    c = D.chain_table([block("A", 4, 4, 40.0, year="Mar 2026 9m"), block("B", 5, 5, 5.0)])
    assert c["highest"] is None and c["line"] is None and [r["layer"] for r in c["rows"]] == ["A", "B"]     # shown, never ranked


def test_a_sector_figure_for_under_half_its_family_is_a_tables_never_a_findings_line():
    sec = {"sector": {"families": {"us": {"n": 53, "medians": {"sbc_share": {"n": 53, "median": 4.6}, "fcf_margin": {"n": 52, "median": 17.8},
                                                               "rpo_growth": {"n": 21, "median": -3.9}, "deferred_growth": {"n": 35, "median": 17.2}}}}}}
    line = deck.sector_lines(sec)[0]
    assert "RPO" not in line and "SBC / revenue 4.6%" in line and "deferred revenue growth +17.2% (35 of 53)" in line
    assert not any("RPO" in q for q in deck.sector_questions(sec))
    assert deck.headline_flag("Median margin is highest in A (30%, 2 of 6 companies).") == "ranked on 2 of 6"
    assert deck.headline_flag("Median margin is highest in A (30%, 5 of 6 companies).") is None
    assert deck.headline_flag("Median margin 30% (2 of 6 companies).") is None                    # data, not a ranking


@pytest.mark.parametrize("name,v,slides", ALL27, ids=IDS27)
def test_every_ranking_a_deck_headlines_passes_sample_and_coverage(name, v, slides):
    for s in slides:
        for line in [s.subtitle or ""] + [ln for b in s.blocks if b["kind"] == "cards" for it in b["items"] for ln in it["lines"]]:
            assert deck.headline_flag(line) is None, (s.title, line)


# ---------- 4. peers ----------
def test_peers_are_judged_sector_first_then_size_then_market_and_accounts_and_never_the_whole_market():
    me = {"symbol": "A", "cap": 10000, "sector": "Chemicals", "region": "IN"}
    same = [{"symbol": f"S{i}", "market_cap": 9000 + i * 100, "sector": "Chemicals", "pe": 20.0} for i in range(12)]
    big = [{"symbol": f"B{i}", "market_cap": 90000, "sector": "Chemicals", "pe": 50.0} for i in range(12)]
    other = [{"symbol": f"O{i}", "market_cap": 10000, "sector": "Metals", "pe": 5.0} for i in range(40)]
    peers, basis = D.comparable_peers(me, same + big + other, {"A"})
    assert basis == "sector" and {p["symbol"] for p in peers} == {p["symbol"] for p in same}     # size within the sector; another sector never
    assert D.comparable_peers(me, big + other, {"A"}) == ([], "none")                             # 40 of similar size elsewhere: still none
    abroad = [{**p, "region": "US"} for p in same]
    assert D.comparable_peers(me, abroad, {"A"}) == ([], "none")                                  # another market is not comparable
    assert D.comparable_peers({**me, "sector": None}, same, {"A"}) == ([], "none")
    got = D.peers_section([{**me, "pe": 25.0}, {"symbol": "Z", "cap": 10000, "sector": "Metals", "pe": 9.0}], same)
    assert got["pe"]["sets"] == {"sector": 1, "none": 1} and got["pe"]["n"] == 1


def test_the_deck_labels_each_peer_figure_with_its_set_and_counts_the_companies_with_none():
    v = full_view()
    v["sections"]["valuation"]["peers"] = {"pe": {"n": 4, "theme": 30.0, "peers": 20.0, "premium": 50.0, "sets": {"sector": 4, "none": 2}, "none": 2}}
    slides = deck.theme_plan(v)[0]
    val = table_of(slides, "Valuation")
    rows = {r[0]: r for r in plain(val["rows"])}
    assert "P/E, companies with comparable peers (own sector, similar market value, outside this theme)" in rows          # lane s3-r40: "this theme", no "the the" on a wrap (updated on purpose)
    none = rows["P/E, companies with no comparable peer set"]
    assert none[val["head"].index("Companies")] == "2" and "not comparable" in none
    t = texts(slides)
    assert "2 with no comparable peer set (left out)" in t and "whole market" not in t.lower()
    v["sections"]["valuation"]["peers"] = {"pe": {"n": 0, "theme": None, "peers": None, "premium": None, "sets": {"none": 5}, "none": 5}}
    slides = deck.theme_plan(v)[0]
    t = texts(slides)
    # R29 (updated on purpose): no company with a peer set makes the valuation descriptive: the theme's own medians, no relative claim
    pe_n = v["sections"]["valuation"]["pe"]["n"]
    assert f"comparable peers for 0 of {pe_n}, so no relative figure" in t
    assert table_of(slides, "Valuation")["head"] == ["Measure", "Theme median", "Range", "Companies"]


@pytest.mark.parametrize("name,v,slides", ALL27, ids=IDS27)
def test_no_deck_sets_a_company_against_the_whole_market(name, v, slides):
    assert "whole market" not in texts(slides).lower()
    peers = ((v.get("sections") or {}).get("valuation") or {}).get("peers") or {}
    assert not any("market" in (x.get("sets") or {}) for x in peers.values())


# ---------- 5. the publication gate ----------
@pytest.mark.parametrize("name,v,slides", ALL27, ids=IDS27)
def test_the_gate_runs_on_every_deck_before_it_is_stored_and_every_item_passes_on_the_synthetic_themes(name, v, slides):
    g = slides[0].gate
    assert [x["id"] for x in g["items"]] == [k for k, _ in deck.GATE_ITEMS] and g["of"] == 10          # R35 added the layout item (updated on purpose)
    assert g["passed"] == 10, [(x["id"], x["dropped"]) for x in g["items"] if not x["ok"]]
    skipped = {x["id"]: x["note"] for x in g["items"] if x["note"].startswith("Skipped")}
    assert set(skipped) <= {"classified", "applicable"}                                         # the later lanes' data, a pass with a note until then
    reading = next(it for s in slides if s.title == "How to read this deck" for b in s.blocks if b["kind"] == "cards" for it in b["items"]
                   if it["title"] == "Reading the figures")
    assert deck.MARKS_LINE in reading["lines"]                                                  # missing, n/a, not comparable: three marks


def test_a_failing_item_drops_what_failed_and_the_result_lists_it():
    v = full_view()
    slides = deck.theme_plan(v)[0]
    t = next(b for s in slides for b in s.blocks if b["kind"] == "table" and s.title == "Every company's figures")
    t["rows"][0][1] = "None"
    t["rows"][1][2] = "N/A"
    # merged with lane r27-class: a layer's companies carry "model"; one with none, still in its layer's figures, fails the check
    lay = [dict(b) for b in v["layers"]]
    i = next(k for k, b in enumerate(lay) if not b.get("official") and b.get("companies"))
    cos = [{**c, "model": "project_services"} for c in lay[i]["companies"]]
    cos[-1] = {**cos[-1], "model": ""}
    lay[i] = {**lay[i], "companies": cos}
    v2 = {**v, "layers": lay}
    v2["sections"] = {**v["sections"], "valuation": {**v["sections"]["valuation"], "peers": {"pe": {"n": 3, "sets": {"market": 3}}}}}
    g = deck.publication_gate(slides, v2)
    by = {x["id"]: x for x in g["items"]}
    assert not by["marks"]["ok"] and by["marks"]["dropped"] == 2 and t["rows"][0][1] == "–" and t["rows"][1][2] == "–"
    assert not by["classified"]["ok"] and not by["peers"]["ok"] and by["reproduce"]["ok"] and g["passed"] == 7      # of 10 (R35: the layout item, checked on the finished pages)
    assert len(g["dropped"]) == g["dropped_n"] == 4 and all(set(d) == {"rule", "slide", "text", "why"} for d in g["dropped"])


def test_a_figure_with_no_period_source_or_formula_is_never_shipped_bare(monkeypatch):
    v = full_view()
    slides = deck.theme_plan(v)[0]
    # merged with lane r27-metrics: the notes are read from the registry, so the registry's ROCE loses its formula and source
    from app.intel import metric_registry as MR
    monkeypatch.setitem(MR.BY_ID, "roce", MR.BY_ID["roce"]._replace(definition="", source=""))
    assert "ROCE" in table_of(slides, "Every company's figures")["head"]
    g = deck.publication_gate(slides, v)
    src = next(x for x in g["items"] if x["id"] == "sourced")
    assert not src["ok"] and src["dropped"] >= 1
    assert not any("ROCE" in b["head"] for s in slides for b in s.blocks if b["kind"] == "table" and s.title.startswith("Every company"))


def test_the_gate_result_is_kept_with_the_deck_and_admin_library_lists_it_per_deck(store):  # noqa: F811
    gate = deck.theme_plan(full_view())[0][0].gate
    computed.put("deck:theme", ["IN", "test", "pdf"], "Zm9v", label="Test theme (PDF, 2026-11-08)", region="IN", meta={"gate": gate})
    computed.put("deck:theme", ["IN", "old", "pdf"], "Zm9v", label="Old theme (PDF, 2026-10-01)", region="IN")
    rows = {r["label"]: r for r in library_admin._decks()}
    got = rows["Test theme (PDF, 2026-11-08)"]["gate"]
    assert got["passed"] == gate["passed"] and [x["id"] for x in got["items"]] == [x["id"] for x in gate["items"]]
    assert rows["Old theme (PDF, 2026-10-01)"]["gate"] is None                                   # kept before the gate: says so


def test_a_deck_made_through_the_route_carries_its_gate_into_admin_library(lib, monkeypatch):  # noqa: F811
    # (updated on purpose, FREE-TIER: Free has no decks of its own now; the deck's route is shown on Basic)
    from app import main as _m
    _m.app.dependency_overrides[_m.current_profile] = lambda: {"id": "u1", "_plan": "basic", "plan": "basic"}    # the api fixture clears it
    from app import admin, main
    from app.intel import routes, theme_routes
    real = routes.public_facts
    routes.public_facts = lambda region, sym: None
    theme_routes.DECK_CACHE._d.clear()            # the process's kept files: never another test's deck (nor ours left for the next)
    try:
        r = lib.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf")
    finally:
        routes.public_facts = real
        theme_routes.DECK_CACHE._d.clear()
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    main.app.dependency_overrides[admin.admin_profile] = lambda: {"id": "ad", "_plan": "pro", "plan": "pro", "email": "owner@example.com"}
    try:
        decks = lib.get("/admin/stored").json()["decks"]
    finally:
        main.app.dependency_overrides.pop(admin.admin_profile, None)
    assert len(decks) == 1 and decks[0]["gate"]["of"] == 10 and len(decks[0]["gate"]["items"]) == 10
    assert all({"id", "label", "ok", "dropped", "note"} <= set(x) for x in decks[0]["gate"]["items"])


# ---------- 6. methodology once ----------
def test_how_the_valuation_is_worked_out_lives_on_the_notes_page_with_one_pointer():
    v = full_view()
    v["sections"]["valuation"]["peers"] = {"pe": {"n": 4, "theme": 30.0, "peers": 20.0, "premium": 50.0, "sets": {"sector": 4}}}
    slides = deck.theme_plan(v)[0]
    val = next(s for s in slides if s.title == "Valuation")
    lines = [ln for b in val.blocks if b["kind"] == "cards" for it in b["items"] for ln in it["lines"]]
    assert sum(1 for ln in lines if "How each is worked out" in ln) == 1 and not any(ln.startswith(("P/E: the price", "Comparable peers:")) for ln in lines)
    notes = {r[0]: r for s in slides if s.title.startswith(deck.NOTES_TITLE) for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])}
    assert "Comparable peers" in notes and "P/E" in notes and "own sector" in notes["Comparable peers"][3]


# ---------- the R25 check's drops on new structures, fixed at their source (lane r27-metrics' report) ----------
def test_layers_that_tie_get_no_comparison_sentence_and_no_line_quotes_the_whole_maps_median(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    tie = D.chain_table([block("A", 4, 4, 20.0), block("B", 5, 5, 20.0)])
    assert tie["line"] is None and tie["highest"] is None                                       # never "within 0.0 points"
    near = D.chain_table([block("A", 4, 4, 20.0), block("B", 5, 5, 19.5)])
    assert "within 0.5 points" in near["line"]
    b = {"layer": "X", "stats": {"ebitda": {"median": 30.0, "n": 4}}, "left_out": 0, "stats_over": "own", "companies": [1]}
    assert D.margin_line(b, 20.0) is None
    assert "within 0.0" not in " ".join(texts(s) for _, _, s in ALL27) and "whole map" not in " ".join(texts(s) for _, _, s in ALL27)


def test_the_gate_reads_the_merged_models_and_the_sector_states():
    """After the merge with r27-class and r27-metrics: a company left out of its layer's figures ("model_out") passes the classification
    check, and sector figures that carry their four states pass the applicability check; neither is "Skipped"."""
    v = full_view()
    slides = deck.theme_plan(v)[0]
    lay = [dict(b) for b in v["layers"]]
    i = next(k for k, b in enumerate(lay) if not b.get("official") and b.get("companies"))
    cos = [{**c, "model": "project_services"} for c in lay[i]["companies"]]
    cos[-1] = {**cos[-1], "model": "", "model_out": True}
    lay[i] = {**lay[i], "companies": cos}
    fam = {"n": 3, "states": {"gnpa_f": ["value", "value", "unavailable"]}, "medians": {}}
    v2 = {**v, "layers": lay, "sections": {**v["sections"], "sector": {"sector": {"families": {"bank": fam}}}}}
    by = {x["id"]: x for x in deck.publication_gate(slides, v2)["items"]}
    assert by["classified"]["ok"] and by["applicable"]["ok"]
    assert "Skipped" not in str(by["classified"]) and "Skipped" not in str(by["applicable"])
