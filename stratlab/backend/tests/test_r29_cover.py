"""Release 29, lane r29-cover (the owner's outside review of the 14 live R27 decks):
1. P0 operating-data sample: the live Private banks deck had "Median of the 7 banks with filed figures" (19 in R26). R27 bumped
   sector_metrics.VERSION, so every bank's figures were read again by the bounded worker; a deck made meanwhile was kept for the day under a key
   that didn't change once they were in, and a read the worker dropped was never queued again while the dive was kept. Now the deck's key
   carries the count still being read, a kept dive queues them again, and the deck says "Filed figures read for 7 of 19 banks so far"; every
   sector figure states "N of M", M the companies it applies to.
2. P0 market-value coverage: "58 companies with figures cover 100% of the value of 105" - the share is now never rounded up to 100, one
   universe (every listed company with a market value) is the denominator, and the publication gate reproduces every stated share.
3. P1 valuation with no comparable peers: descriptive (the theme's own medians and spread, by layer and over time), never relative.
4. P1 business models inside broad themes: regulated networks, generators and traders; miners and processors; stores and marketplaces.
Generic: synthetic themes only."""
import copy

import pytest

from app import deck
from app.intel import metric_registry as Reg
from app.intel import sector_metrics as S
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests import test_r23_metrics as R23
from tests.synth_structures_r29 import structures
from tests.synthetic_themes_r27 import chemicals_in, telecom_in
from tests.test_export import plain, texts
from tests.test_r18_deck import bank_theme, deck_of
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
from tests.test_theme1 import TODAY


def card_lines(slides):
    return [ln for s in slides for b in s.blocks if b["kind"] == "cards" for it in b["items"] for ln in it.get("lines") or []]


# ---------- 1. the operating-data sample ----------
def half_read_banks():
    region, m, f = bank_theme()[:3]
    pieces = R23.bank_pieces(f)
    keep = [s for s in sorted(pieces) if s.startswith("PVT")][:3]          # three confirmed banks read, the rest still being read
    return region, m, f, {s: pieces[s] for s in keep}


def test_a_family_still_being_read_says_how_many_are_read_and_every_figure_is_n_of_m():
    region, m, f, some = half_read_banks()
    v, slides = deck_of(region, m, f, metrics=R23.reader_of(some))
    fam = v["sections"]["sector"]["families"]["bank"]
    waiting = fam["pending"]
    assert fam["n"] == len(some) and waiting > 0 and fam["read"] == fam["of"] - waiting
    # M is every bank the figure applies to, those still being read included: never "7" for 7 of 19
    for k, st in fam["medians"].items():
        assert st["of"] > st["n"] or not waiting, (k, st)
    lines = card_lines(slides)
    assert f"Filed figures read for {fam['read']} of {fam['of']} banks so far; {waiting} still being read." in lines
    page = next(s for s in slides if s.title.startswith("Sector operating figures"))
    assert f"filed figures read for {fam['read']} of {fam['of']} so far, {waiting} still being read" in page.subtitle
    med = next(r for r in plain(next(b for b in page.blocks if b["kind"] == "table")["rows"]) if str(r[0]).startswith("Median"))
    assert all(" of " in c for c in med[1:] if c and c != "–" and "(" in c), med
    # under half read: no sector median headlines (coverage), and the gate sees the families' states (R29: it read the wrong key before)
    assert not any(ln.startswith("Median of the") and "banks with filed figures" in ln for ln in lines)
    item = next(x for x in slides[0].gate["items"] if x["id"] == "applicable")
    assert item["ok"] and item["note"] == "Sector figures carry their applicability and four states"


def test_once_every_bank_is_read_the_sample_is_whole_and_says_so():
    region, m, f = bank_theme()[:3]
    v, slides = deck_of(region, m, f, metrics=R23.reader_of(R23.bank_pieces(f)))
    fam = v["sections"]["sector"]["families"]["bank"]
    assert fam["pending"] == 0 and not any("still being read" in ln for ln in card_lines(slides))
    head = next(ln for ln in card_lines(slides) if ln.startswith("Median of the"))
    assert f"({fam['n']} of {fam['of']})" in head or " of " in head          # each figure states its own sample


def test_a_kept_deck_is_keyed_by_the_figures_still_being_read_and_one_made_meanwhile_is_not_stored(monkeypatch):
    from app import computed, main
    region, m, f = bank_theme()[:3]
    dives = {"now": {"metrics_pending": ["A", "B"], "metrics_families": {"A": "bank", "B": "bank"}}}
    built, stored = [], []
    monkeypatch.setattr(T, "map_for_deck", lambda R, profile, region, q, pending=None: ("US", "Banks", m))
    monkeypatch.setattr(main, "check_deep", lambda *a, **k: None)
    monkeypatch.setattr(T, "dive_of", lambda r, theme, m_, refresh=False, by=None: dives["now"])
    monkeypatch.setattr(T, "deck_view", lambda r, m_, dive, extra=None: {"waiting": len(dive["metrics_pending"])})
    monkeypatch.setattr(T, "deck_extras", lambda *a, **k: {})
    monkeypatch.setattr(deck, "build_theme_gated", lambda v, pdf=False: built.append(v["waiting"]) or (f"deck {v['waiting']}".encode(), {}))
    real_get = computed.get
    monkeypatch.setattr(computed, "get", lambda kind, key, **kw: None if kind == "deck:theme" else real_get(kind, key, **kw))
    monkeypatch.setattr(computed, "put", lambda kind, key, value, **kw: stored.append(key))
    T.DECK_CACHE._d.clear()
    try:
        a = T.theme_dive_deck(q="Banks", region="US", format="pdf", profile={"id": "u"})
        dives["now"] = {"metrics_pending": [], "metrics_families": {}}          # the worker has read them: the dive is worked out again
        b = T.theme_dive_deck(q="Banks", region="US", format="pdf", profile={"id": "u"})
        c = T.theme_dive_deck(q="Banks", region="US", format="pdf", profile={"id": "u"})
    finally:
        T.DECK_CACHE._d.clear()
    assert a.body == b"deck 2" and b.body == b"deck 0" and c.body == b"deck 0" and built == [2, 0]
    assert len(stored) == 1 and stored[0][-1] == 0                 # only the deck with every figure read is kept in the shared store


def test_a_kept_dive_still_waiting_queues_the_reads_the_worker_dropped(monkeypatch):
    region, m, f = bank_theme()[:3]
    kept = {"metrics_pending": ["PVT1", "PSU2"], "metrics_families": {"PVT1": "bank", "PSU2": "bank"}, "layers": []}
    queued = []
    monkeypatch.setattr(T.computed, "get", lambda kind, key, **kw: {"value": {"dive": kept, "pieces": {}}})
    monkeypatch.setattr(T, "pieces_moved", lambda r, pieces: False)
    monkeypatch.setattr(S, "any_stored", lambda r, syms: False)
    monkeypatch.setattr(S, "queue", lambda r, s, fam: queued.append((r, s, fam)))
    assert T.dive_of("IN", "Private banks", m) is kept
    assert queued == [("IN", "PVT1", "bank"), ("IN", "PSU2", "bank")]
    assert T.figures_waiting(kept) == 2 and T.figures_waiting({}) == 0


def test_the_dive_keeps_each_waiting_company_s_family():
    region, m, f = bank_theme()[:3]
    dive = D.build(region, m["sector"], m, D.Sources(TODAY, facts=f.get, metrics=lambda s, fam: None))
    assert dive["metrics_families"] and set(dive["metrics_families"]) == set(dive["metrics_pending"])
    assert set(dive["metrics_families"].values()) == {"bank"}


# ---------- 2. the market-value coverage ----------
def members(n_with, n_without, cap_with=100.0, cap_without=10.0):
    ms = [{"symbol": f"W{i}", "name": f"W{i}", "cap": cap_with, "revenue": 50.0, "net": 5.0} for i in range(n_with)]
    ms += [{"symbol": f"X{i}", "name": f"X{i}", "cap": cap_without} for i in range(n_without)]
    return {"members": ms, "placements": {"total": n_with + n_without + 2}, "status": {}, "with_figures": n_with, "members_with_figures": n_with}


def test_the_share_is_the_value_with_figures_over_every_company_with_a_market_value():
    v = members(58, 47)                     # the live semis shape: 58 with figures, 105 with a market value, 107 in the theme
    got = deck.value_share(v)
    assert got["valued"] == 105 and got["with_value"] == 58 and got["value_with"] == 5800 and got["value_all"] == 6270
    assert got["share"] == round(5800 / 6270 * 100) == 93
    cov = deck.coverage(v)
    assert cov["share"] == 93 and cov["valued"] == 105 and "(93% of the combined market value of the 105 of 107 with one)" in cov["line"]


def test_a_share_short_of_the_whole_is_never_rounded_up_to_100():
    v = members(58, 47, cap_with=1000.0, cap_without=0.5)     # those without figures are tiny: 99.96%, said 99.9%, never "100%"
    assert deck.value_share(v)["share"] == 99.9
    assert deck.pct_of(9996, 10000) == 99.9 and deck.pct_of(9990, 10000) == 99.9 and deck.pct_of(9905, 10000) == 99 and deck.pct_of(10000, 10000) == 100
    assert deck.pct_of(3, 1000) == 0.3 and deck.pct_of(1, 100000) == 0.1 and deck.pct_of(0, 10) == 0 and deck.pct_of(5, 0) is None
    assert "100%" not in deck.coverage(v)["line"]


def test_an_unconfirmed_company_s_value_is_in_the_denominator_never_the_numerator():
    v = members(4, 0)
    v["members"].append({"symbol": "U", "name": "U", "cap": 400.0, "revenue": 10.0})
    v["status"] = {"U": "unverified"}
    assert deck.value_share(v)["share"] == 50 and deck.value_share(v)["valued"] == 5


def test_the_gate_reproduces_every_stated_share_from_the_members_and_drops_one_that_isn_t():
    v = members(5, 3)
    good = f"{deck.coverage(v)['share']}% of the combined market value of the 8 of 10 with one"
    assert deck.share_flag(good, v) is None
    assert deck.share_flag("100% of the combined market value of the 8 of 10 with one", v).startswith("share 100%")
    assert deck.share_flag(f"{deck.coverage(v)['share']}% of the value of the 5 with one", v).startswith("5 with a market value")
    region, m, f = bank_theme()[:3]
    _, slides = deck_of(region, m, f)
    item = next(x for x in slides[0].gate["items"] if x["id"] == "reconcile")
    assert item["ok"]


def test_on_a_theme_with_companies_that_have_a_market_value_and_no_figures_the_deck_states_the_reproduced_share():
    region, m, f, market = chemicals_in()
    gone = [c["ticker"] for v in m["value_chain"] for c in v["companies"]][-3:]
    m = copy.deepcopy(m)
    for v in m["value_chain"]:
        for c in v["companies"]:
            c["cap"] = 5000.0 if c["ticker"] in gone else 20000.0
    f = {s: x for s, x in f.items() if s not in gone}                   # a market value in the map, no figures
    v, slides = deck_of(region, m, f, index_rows=lambda: market)
    vs = deck.value_share(v)
    assert vs["valued"] > vs["with_value"] and vs["share"] < 100 and vs["share"] == deck.pct_of(vs["value_with"], vs["value_all"])
    cover = {it[0]: it for b in slides[0].blocks if b["kind"] == "stats" for it in b["items"]}
    assert cover["With figures"][2] == f"{vs['share']}% of the value of the {vs['valued']:,} with one"
    assert cover["Their market value"][2].endswith("with figures and a market value")
    assert next(x for x in slides[0].gate["items"] if x["id"] == "reconcile")["ok"]
    every_rule("chemicals, market value without figures", v, slides)


# ---------- 3. valuation with no comparable peers ----------
def test_with_no_comparable_peers_the_valuation_is_descriptive_by_layer_and_never_relative():
    region, m, f, market = telecom_in()                  # no listed company of the operators' own sector: no peer set
    v, slides = deck_of(region, m, f, index_rows=lambda: market)
    val = v["sections"]["valuation"]
    assert not D.relative_ok(val) and len(val["by_layer"]) >= 2
    page = next(s for s in slides if s.title == "Valuation")
    assert page.subtitle.startswith("The theme's own median P/E") and "comparable peers for 0 of" in page.subtitle
    tables = [b for b in page.blocks if b["kind"] == "table"]
    assert tables[0]["head"] == ["Measure", "Theme median", "Range", "Companies"]
    assert tables[1]["head"][0] == "Layer: its own medians (companies)" and len(tables[1]["rows"]) == len(val["by_layer"])
    t = texts([page]).lower()
    assert "all listed" not in t and "against" not in t and "premium" not in t and "discount" not in t
    find = next(ln for ln in card_lines(slides) if ln.startswith("The theme's own median"))
    assert "comparable peers for 0 of" in find
    every_rule("telecom, descriptive valuation", v, slides)


def test_relative_valuation_stays_where_peers_cover_half_or_more():
    assert D.relative_ok({"pe": {"n": 10}, "peers": {"pe": {"n": 5}}}) and not D.relative_ok({"pe": {"n": 10}, "peers": {"pe": {"n": 4}}})
    assert not D.relative_ok({"pe": None, "peers": {}})


# ---------- 4. business models inside broad themes ----------
def split(theme: dict) -> tuple:
    t = copy.deepcopy(theme)
    vc = B.by_model(t["map"]["value_chain"], t["models"], t["map"]["sector"], tags=t["tags"], confidence=t["confidence"])
    return t, vc


@pytest.mark.parametrize("name,theme", list(structures()), ids=[n for n, _ in structures()])
def test_broad_themes_split_by_business_model_and_every_deck_rule_holds(name, theme):
    t, vc = split(theme)
    models = t["models"]
    if any(md in ("utility", "resources") for md in t["given"].values()):
        assert models != t["given"]                   # the broad answers were made exact by each company's own evidence
    for v in vc:
        fams = {C.model_family(models.get(c["ticker"])) for c in v["companies"]} - {""}
        assert len(fams) <= 1, (v["layer"], fams)
    for a, b in t["apart"]:
        for v in vc:
            ids = {models.get(c["ticker"]) for c in v["companies"]}
            assert not (a in ids and b in ids), (v["layer"], a, b)
    m = {**t["map"], "value_chain": vc}
    view, slides = deck_of(t["region"], m, t["facts"])
    every_rule(name, view, slides)
    # no headline sets layers of different families side by side
    fam_of = {x["layer"]: D.model_family_of(x.get("model")) for x in view["layers"]}
    compared = view["chain"].get("compared") or []
    if view["chain"].get("highest"):
        assert len({fam_of[x] for x in compared}) == 1, compared


def test_each_broad_model_is_made_exact_by_its_evidence_and_needs_words_of_its_kind():
    ev = C.model_evidence
    assert C.refine_model("utility", ev("Power - Transmission", "runs transmission lines")) == "regulated_utility"
    assert C.refine_model("utility", ev("Power Generation", "thermal plants")) == "power_generation"
    assert C.refine_model("utility", ev("Power", "trades electricity on the power exchange")) == "power_trading"
    assert C.refine_model("utility", ev("Power", "generates power at its plants and runs power distribution in two cities")) == "utility"  # both: as given
    assert C.refine_model("resources", ev("Coal", "mines coal")) == "commodity_mining"
    assert C.refine_model("resources", ev("Oil Exploration", "drills oil and gas wells")) == "resources"
    assert C.refine_model("manufacturing", ev("Aluminium, Copper & Zinc Products", "rolls foils")) == "metal_processing"
    assert C.refine_model("manufacturing", ev("Auto Components", "makes pipes")) == "manufacturing"                  # not a metals industry
    for k in ("regulated_utility", "power_generation", "power_trading", "commodity_mining", "metal_processing"):
        assert k in C.MODELS and k in C.MODEL_NEEDS and k in C.MODEL_SYSTEM and k in C.PLACE_SYSTEM2
        assert not C.model_supported(k, "Industry: Banks. Takes deposits.")
    assert len({C.model_family(k) for k in ("regulated_utility", "power_generation", "power_trading", "utility")}) == 4
    assert C.model_family("commodity_mining") != C.model_family("metal_processing")
    assert C.model_family("retail") != C.model_family("platform")


def test_metrics_apply_per_model_inventory_days_never_for_a_marketplace():
    store = Reg.tags("US", {"official_industry": "Retail-Grocery Stores"}, "resale")
    market = Reg.tags("US", {"official_industry": "Services-Business Services, Nec"}, "platform")
    assert Reg.applies("inventory_days", "US", store) and not Reg.applies("inventory_days", "US", market)
    for fam in ("regulated_utility", "generation", "mining", "metal_processing"):
        assert Reg.applies("capex_share", "US", {fam, "us"})
    assert Reg.applies("inventory_days", "US", {"metal_processing", "us"}) and not Reg.applies("inventory_days", "US", {"regulated_utility", "us"})
    assert Reg.main_family([{"mining"}, {"mining"}, {"metal_processing"}]) == "mining"


def test_no_headline_compares_layers_of_different_families(monkeypatch):
    # R31: a test of the ranking rules on fixtures of 3 or 4 companies a layer, run at the marks' floor (COMPARE_MIN); the headline floor
    # of 5 (HEADLINE_MIN) on the same fixtures is tested in tests/test_r31_bound.py
    monkeypatch.setattr("app.intel.theme_data.HEADLINE_MIN", 3)
    def blk(name, fam, e):
        cos = [{"symbol": f"{name}{i}", "status": "core", "year": "Mar 2026"} for i in range(4)]
        return {"layer": name, "n": 4, "revenue": 100.0, "companies": cos, "model": {"id": fam, "family": fam, "line": ""},
                "stats": {"ebitda": {"n": 4, "median": e}, "net": None, "roce": None}}
    one = D.chain_table([blk("Grid", "regulated_utility", 60.0), blk("Plants", "generation", 30.0), blk("Plants B", "generation", 20.0)])
    assert set(one["compared"]) == {"Plants", "Plants B"} and one["highest"] == "Plants"
    # changed on purpose (m2): a shown layer above the highest is named after the ranking, with why it is not ranked, never inside it
    rank, _, rest = one["line"].partition(" Shown, not ranked: ")
    assert "Grid" not in rank and rest == "Grid (60.0%), a different kind of business."
    tie = D.chain_table([blk("Grid", "regulated_utility", 60.0), blk("Grid B", "regulated_utility", 50.0), blk("Plants", "generation", 30.0),
                         blk("Plants B", "generation", 20.0)])
    assert tie["highest"] is None and tie["line"] is None
    rows = [("A", 10.0, 3, "x"), ("B", 5.0, 3, "y"), ("C", 1.0, 3, "y")]
    pair = D.rank_pair(rows, lambda r: r[1], lambda r: r[2], model=lambda r: {"family": r[3]})
    assert pair and {pair[0][0], pair[1][0]} == {"B", "C"}


def test_the_versions_are_bumped_so_kept_maps_and_decks_are_made_again():
    assert B.RULES == 53 and deck.THEME_DECK_VERSION == 64          # c54 (R53 review): RULES 53, PLACE_CARRY[53] = 52, deck 64, dive text 24 (updated on purpose); d53 (R53): RULES 52, PLACE_CARRY[52] = 51, deck 63, dive text 23 (updated on purpose); gl52 (R52): RULES 51, PLACE_CARRY[51] = 50, deck 62, dive text 22 (updated on purpose); rv51 (R51): RULES 50, PLACE_CARRY[50] = 49, deck 61, dive text 21 (updated on purpose); gl50 (R50): RULES 49, PLACE_CARRY[49] = 48, deck 60, dive text 20 (updated on purpose); ex49 (R49): RULES 48, PLACE_CARRY[48] = 47, deck 59, dive text 19, precise exclusion reasons, the business-model ranking rule (updated on purpose); vr48 (R48): figures reconciled with the year's lines before any is held, the comparison basis (updated on purpose); cl48 (R48): RULES 47, PLACE_CARRY[47] = 46, deck 58, dive text 18, primary-business validation and the coverage control (updated on purpose); cv47 (R47): RULES 46, PLACE_CARRY[46] = 45, filing titles are no words of a company's own, the AI's industry pick kept across rules changes (PICK_RULES); deck and dive text unchanged (updated on purpose); vf46 (R46): dive text 17, each checked figure's source record, net above EBITDA reconciled line by line (updated on purpose); tx2 (R45/R46): RULES 45, PLACE_CARRY[45] = 44, deck 57 (dive text 17 from vf46), the taxonomy regression guard and the screening populations (updated on purpose); c1 (R44): RULES 44, PLACE_CARRY[44] = 43, deck 56, dive text 16 (55 and 15 are R44.1's), classification coverage from evidence (updated on purpose); R44 (lane v1): deck 54, dive text 14, verification states (updated on purpose); lane d1: RULES 43, PLACE_CARRY[43] = 42, deck 53, dive text 12 (the outside review of the live R41 decks, updated on purpose); lane t1: deck 52, dive text 11 (LIVE7A, updated on purpose); R41: deck 51, coloured cells measured bold (updated on purpose); lane s3-r40: RULES 42, deck 50, dive text 10 (updated on purpose); lane s2-exact: RULES 41 (updated on purpose); lane s1-fit: RULES 39 (updated on purpose); R38 bumped the deck version (updated on purpose); R37 lane r2: RULES 38 (updated on purpose); R36 lane r1: RULES 37 (updated on purpose); q1: RULES 36 (updated on purpose); R35 bumped the deck version (updated on purpose; lane n2: RULES 35)
