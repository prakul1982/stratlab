"""Release 20 (owner, 7 Nov: "fixes must be global, not for these three decks"): every rule of the theme deck checked across many synthetic themes
of different shapes, India and the US: an insurer and NBFC theme, IT services, pharma with a demerger, a US theme with an AI map of five layers,
and edge cases (one company in a layer, a layer of loss-makers, a theme where most companies have no figures, a long theme of 60 companies),
beside the earlier ones (packaging, US payments, private banks, US named lists, makers, the every-part fixture). Facts only: no figure or
name is tuned to a real company."""
import re
import threading
from datetime import datetime, timezone

import pytest

from app import deck, stock_pages
from app.intel import theme_base as B
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests.test_deck_look import full_view
from tests.test_export import plain, table_of, texts
from tests.test_r17_fixes import theme_a, theme_b
from tests.test_r18_deck import NOW, bank_facts, bank_theme, deck_of, maker_theme, us_list_theme
from tests.test_theme1 import TODAY, facts

IMPORTANT = ("table", "hbars", "columns", "lines", "cards", "stats", "flow")


def co(sym, name, what="", industry="", base=True, verified=True):
    return {"ticker": sym, "name": name, "what": what, "industry": industry, "base": base, "basis": "industry" if base else "added", "verified": verified}


def placements(n):
    return {"checked": True, "pending": 0, "placed": n, "total": n, "base": n, "named": 0, "added": 0, "confirmed": 0}


# ---------- the new synthetic themes ----------
def nbfc_theme():
    """India, lender-like but no bank: vehicle and housing financiers and life insurers, in the AI's own layers."""
    groups = {"Vehicle finance": ("VF", "Non Banking Financial Company (NBFC)", 3), "Housing finance": ("HF", "Housing Finance Company", 3),
              "Life insurance": ("LI", "Life Insurance", 3)}
    m = {"sector": "Lenders and insurers", "summary": "Non-bank lenders and insurers.", "value_chain": [], "sub_themes": [], "tailwinds": [], "risks": [],
         "placements": placements(9), "generated_at": 1.0}
    f = {}
    for layer, (p_, ind, n) in groups.items():
        cos = [co(f"{p_}{i}", f"{layer.split()[0]} Fin {i} Ltd", f"provides {layer.lower()}", ind) for i in range(n)]
        m["value_chain"].append({"layer": layer, "description": f"Companies in {layer.lower()}.", "companies": cos})
        for i, c in enumerate(cos):
            lend = {"gnpa": 2.0 + i, "nnpa": 1.0, "nii_assets": 6.0 + i * 0.5, "roa": 2.5} if p_ != "LI" else {"roa": 1.0}
            f[c["ticker"]] = {**facts(c["ticker"], c["name"], [3000, 3400, 3900, 4500 + i * 200], [None] * 4, [600, 700, 800, 900 + i * 30],
                                      cap=80000 - i * 9000, pe=22.0, roce=None, de=None), "bank": True, "roe": 14.0 + i * 2, "pb": 3.0 - i * 0.3,
                              "lender": lend}
    return "IN", m, f


def it_theme():
    """India, asset-light: the exchange's two IT industries are the layers; high returns, margins filed with decimals."""
    soft = [co(f"SW{i}", f"Soft {i} Ltd", "provides software and consulting services", "Computers - Software & Consulting") for i in range(5)]
    ites = [co(f"BP{i}", f"Process {i} Ltd", "provides business process services", "IT Enabled Services") for i in range(3)]
    m = {"sector": "IT services", "summary": "Software and IT-enabled services exporters.", "sub_themes": [], "tailwinds": [], "risks": [],
         "value_chain": [{"layer": "Computers - Software & Consulting", "official": True, "basis": "industry", "description": "", "companies": soft},
                         {"layer": "IT Enabled Services", "official": True, "basis": "industry", "description": "", "companies": ites}],
         "placements": {**placements(8), "industries": ["Computers - Software & Consulting", "IT Enabled Services"]}}
    f = {}
    for i, c in enumerate(soft + ites):
        f[c["ticker"]] = facts(c["ticker"], c["name"], [5000, 5600, 6100, 6700 + i * 100], [24.5, 25.1, 23.8, 22.4 + i * 0.7], [800, 900, 950, 1000 + i * 20],
                               cap=200000 - i * 15000, pe=28.0 + i, roce=38.0 + i, latest_yoy={"of": "Sep 2026 vs Sep 2025", "sales": 6.0 + i, "profit": 4.0 - i, "basis": "quarter"})
    return "IN", m, f


def pharma_theme():
    """India, pharmaceuticals and biotech, a demerger in one company's stored corporate actions."""
    ph = [co(f"PH{i}", f"Pharma {i} Ltd", "manufactures generic formulations for domestic and export markets", "Pharmaceuticals") for i in range(6)]
    bt = [co(f"BT{i}", f"Bio {i} Ltd", "develops biosimilars", "Biotechnology") for i in range(3)]
    m = {"sector": "Pharma", "summary": "Generic drug makers and biotech.", "sub_themes": [], "tailwinds": [], "risks": [],
         "value_chain": [{"layer": "Pharmaceuticals", "official": True, "basis": "industry", "description": "", "companies": ph},
                         {"layer": "Biotechnology", "official": True, "basis": "industry", "description": "", "companies": bt}],
         "placements": {**placements(9), "industries": ["Pharmaceuticals", "Biotechnology"]}}
    f = {}
    for i, c in enumerate(ph + bt):
        f[c["ticker"]] = facts(c["ticker"], c["name"], [2000, 2200, 2500, 2700 + i * 50], [21, 22, 20, 19 + i % 4], [300, 320, 350, 380 + i * 10],
                               cap=90000 - i * 7000, pe=30.0)
    return "IN", m, f


def pharma_actions(sym):
    return [{"kind": "demerger", "ex_date": "2025-12-01"}] if sym == "PH1" else []


def us_map_theme():
    """The US with an AI map of five business-model layers, one of them a single company, one all loss-makers; the SEC's industries differ
    inside a layer."""
    spec = {"Endpoint security": 3, "Network security": 3, "Identity": 3, "Cloud security": 3, "Security services": 1}
    inds = ["Services-Prepackaged Software", "Computer Communications Equipment", "Services-Computer Integrated Systems Design"]
    m = {"sector": "Cyber defence", "summary": "Companies that protect computers, networks and identities.", "value_chain": [], "sub_themes": [],
         "tailwinds": [], "risks": [], "placements": placements(13), "generated_at": 1.0}
    f, k = {}, 0
    for layer, n in spec.items():
        cos = [co(f"U{k + i}", f"{layer.split()[0]} Co {i}", f"sells {layer.lower()} products", inds[(k + i) % 3]) for i in range(n)]
        m["value_chain"].append({"layer": layer, "description": f"{layer} products.", "companies": cos})
        for i, c in enumerate(cos):
            loss = layer == "Cloud security"
            f[c["ticker"]] = {**facts(c["ticker"], c["name"], [800, 950, 1100, 1300 + i * 40], [-12.0 - i] * 4 if loss else [18.0, 19.5, 21.0, 22.5 + i],
                                      [-90, -80, -70, -60 - i] if loss else [90, 110, 130, 150 + i * 5], cap=60000 - (k + i) * 3000,
                                      pe=None if loss else 45.0 + i, latest_yoy={"of": "Sep 2026 vs Sep 2025", "sales": 15.0 + i, "profit": 9.0 if not loss else None,
                                                                             "basis": "quarter"}),
                              "region": "US", "unit": "$ million"}
        k += n
    return "US", m, f


def sparse_theme():
    """India, most companies with no stored figures (2 of 9 have them)."""
    cos = [co(f"SP{i}", f"Sparse {i} Ltd", "makes industrial valves", "Industrial Products") for i in range(9)]
    m = {"sector": "Valves", "summary": "", "value_chain": [{"layer": "Industrial Products", "official": True, "basis": "industry", "description": "", "companies": cos}],
         "sub_themes": [], "tailwinds": [], "risks": [], "placements": {**placements(9), "industries": ["Industrial Products"]}}
    f = {c["ticker"]: facts(c["ticker"], c["name"], [400, 420, 450, 480], [14, 14, 15, 15], [30, 32, 34, 36], cap=5000 - i * 300) for i, c in enumerate(cos[:2])}
    f.update({c["ticker"]: {**facts(c["ticker"], c["name"], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], cap=900), "years": [], "net_margin": None, "opm": None,
                            "roce": None, "pe": None} for c in cos[2:4]})          # stored pages with no figure in them
    return "IN", m, f


def long_theme(n=60):
    """India, 60 companies in three of the exchange's industries (the appendix's size)."""
    names = ["Cement & Cement Products", "Iron & Steel", "Civil Construction"]
    layers = []
    f = {}
    for j, ind in enumerate(names):
        cos = [co(f"L{j}{i:02d}", f"Long Registered Company Name Number {j}{i:02d} Limited", "manufactures building materials", ind) for i in range(n // 3)]
        layers.append({"layer": ind, "official": True, "basis": "industry", "description": "", "companies": cos})
        for i, c in enumerate(cos):
            f[c["ticker"]] = facts(c["ticker"], c["name"], [900, 1000, 1100, 1200 + i], [15, 16, 17, 18], [60, 70, 80, 90], cap=50000 - (j * 20 + i) * 500)
    m = {"sector": "Building materials", "summary": "Cement, steel and construction.", "value_chain": layers, "sub_themes": [], "tailwinds": [], "risks": [],
         "placements": {**placements(n), "industries": names}}
    return "IN", m, f


def themes():
    yield "packaging (IN)", deck_of(*theme_a())
    yield "payments (US, one layer)", deck_of(*theme_b())
    yield "private banks (IN)", deck_of(*bank_theme()[:3])
    yield "US list, by industry", deck_of(*us_list_theme())
    yield "US list, one industry", deck_of(*us_list_theme(False))
    yield "makers (IN)", deck_of(*maker_theme())
    yield "NBFC and insurers (IN)", deck_of(*nbfc_theme())
    yield "IT services (IN)", deck_of(*it_theme())
    yield "pharma, a demerger (IN)", deck_of(*pharma_theme(), corp_history=pharma_actions)
    yield "US, AI map of 5 layers", deck_of(*us_map_theme())
    yield "most without figures (IN)", deck_of(*sparse_theme())
    yield "60 companies (IN)", deck_of(*long_theme())
    v = full_view()
    yield "every part (fixture)", (v, deck.theme_plan(v)[0])


ALL = list(themes())


def page_counts() -> dict:
    return {name: len(slides) for name, (_, slides) in ALL}


# ---------- every rule, across every synthetic theme ----------
@pytest.mark.parametrize("name,v,slides", [(n, v, s) for n, (v, s) in ALL], ids=[n for n, _ in ALL])
def test_every_rule_holds_on_every_synthetic_theme(name, v, slides):
    t = texts(slides)
    titles = [s.title for s in slides]
    # page set: no dividers, nothing "continued", the single pages single, every page carries something, the appendix one table at the end
    assert not [s for s in slides if s.kind == "section"]
    assert not any("continued" in x or "all companies" in x for x in titles)
    for single in ("Data confidence", "Dated company updates", "Tailwinds and risks", "Operating figures", "Sub-themes", "How to read this deck",
                   "The latest quarter against a year earlier", "Contents", "Key findings"):
        assert titles.count(single) <= 1 and not any(x.startswith(single + " (") for x in titles), single
    for s in slides[1:]:
        assert any(b["kind"] in IMPORTANT and (b.get("rows") or b.get("items") or b.get("vals") or b.get("series")) for b in s.blocks), s.title
    at = next(i for i, s in enumerate(slides) if s.title.startswith("Every company's figures"))
    # changed on purpose (R35): where a layer's page left names off, "Who is in each layer's calculations" follows it, a table too
    # changed on purpose (R46): each checked figure's source record follows them, a table too
    # changed on purpose (R48): and each comparison's basis (its metric, rule and each layer's companies), a table too
    assert all(s.title.startswith(("Every company's figures", deck.ROLL_TITLE, deck.SOURCES_TITLE, deck.COMPARE_TITLE)) and [b["kind"] for b in s.blocks if b["kind"] != "text"] == ["table"]
               for s in slides[at:])
    # R21: a theme with layers of its own has no exchange-industry layer beside them; a chart plots no layer median under 3
    lays = v.get("layers") or []
    if any(not x.get("official") for x in lays):
        assert all(not x.get("official") or x.get("basis") == "rest" for x in lays), [x["layer"] for x in lays]
    for s in slides:
        for b in s.blocks:
            if b["kind"] == "hbars" and str(b.get("title", "")).startswith("Median"):
                for cat in b["cats"]:
                    assert int(re.search(r"\((\d+)(?: of \d+)?\)$", cat).group(1)) >= 3, cat        # R25: "(5 of 6)" when the layer has more
    # no card line cut with an ellipsis
    for s in slides:
        for b in s.blocks:
            if b["kind"] == "cards":
                assert not any(str(x).endswith("…") for it in b["items"] for x in it.get("lines") or []), s.title
    # no "of 0", no ".0" figure, no advice word
    assert not re.search(r"\bof 0\b", t), re.findall(r".{40}\bof 0\b.{10}", t)
    # changed on purpose (lane t1, LIVE7A-014: "36%" beside "35.9%"): a whole figure keeps its ".0" only where a figure of its unit beside it
    # (its text, table column or chart) has a decimal, so no ".0" figure stands where nothing beside it has one
    assert not deck.precision_problems(slides), deck.precision_problems(slides)[:3]
    for word in ("avoid", "attractive", "undervalued", "overvalued", "recommend", "target price", "outlook", "implication"):
        assert not re.search(rf"\b{word}\b", t.lower()), word
    # lane n1 (changed on purpose): "buy" and "sell" only as a recommendation ("buy the stock", "a buy", "should sell"); a company
    # turning metal it buys into pipes is a fact
    for line in t.splitlines():
        assert not deck._TRADE_ADVICE.search(line), line
    # no column that is "–" in every row
    for s in slides:
        for b in s.blocks:
            if b["kind"] == "table" and len(plain(b["rows"])) >= 2:
                for c in range(1, len(b["head"])):
                    assert any(str(r[c] if not isinstance(r[c], dict) else r[c].get("text")) not in ("–", "") for r in plain(b["rows"])), (s.title, b["head"][c])
    # no median under 3 companies: never "Median of 1/2", a layer is highest or lowest only on 3 or more, and a median row's figure is "–" below 3
    assert not re.search(r"Median of [12] compan", t)
    chain = v.get("chain") or {}
    rows = {r["layer"]: r for r in chain.get("rows") or []}
    for side in ("highest", "lowest"):
        if chain.get(side):
            r = rows[chain[side]]
            assert r[f"{chain.get('measure') or 'ebitda'}_n"] >= 3, (side, r)
    for s in slides:
        if re.match(r"Layer \d+ ·", s.title):
            layer = next(x for x in v["layers"] if f" · {x['layer']}" in s.title)
            tb = next(b for b in s.blocks if b["kind"] == "table")
            med = next((r for r in plain(tb["rows"]) if str(r[0]).startswith("Median")), None)
            heads = tb["head"]
            for key, label in (("ebitda", "EBITDA margin"), ("net", "Net margin"), ("roce", "ROCE"), ("roe", "ROE")):
                if med and label in heads:
                    n = ((layer.get("stats") or {}).get(key) or {}).get("n") or 0
                    cell = med[heads.index(label)]
                    assert (cell.startswith("–") if n < 3 else not cell.startswith("–")), (s.title, label, n, cell)
    # the counts agree: the universe and the figures in one wording on the cover, the findings and data confidence; the quarter's counts
    cov = deck.coverage(v)
    cover = {it[0]: it for b in slides[0].blocks if b["kind"] == "stats" for it in b["items"]}
    assert cover["With figures"][1] == f"{cov['n']:,}" and cov["line"] in t
    counts = next(p for s in slides if s.title == "Data confidence" for b in s.blocks for p in b.get("paras") or [] if p.startswith("Counts:"))
    # R27: the four reconciled counts lead the line, then the universe against the figures in the one wording
    assert counts.startswith(f"Counts: {deck.counts_words(deck.reconciled_counts(v, cov))}.") and cov["line"] in counts
    q = (v.get("sections") or {}).get("quarter") or {}
    if "The latest quarter against a year earlier" in titles:
        tiles = {it[0]: it for s in slides if s.title == "The latest quarter against a year earlier" for b in s.blocks if b["kind"] == "stats" for it in b["items"]}
        n_of = lambda k: (q.get(k) or {}).get("n") or (q.get(f"{k}_up", 0) + q.get(f"{k}_down", 0))      # noqa: E731
        assert tiles["Median revenue change"][2].endswith(f"of {n_of('sales')}") and tiles["Median net profit change"][2].endswith(f"of {n_of('profit')}")
        card = next(c for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards" for c in b["items"] if c["title"] == "What changed")
        said = next((x for x in card["lines"] if x.startswith("Quarter to")), None)
        if said:
            assert f"({_count(q['sales']['n'])})" in said
            if (q.get("profit") or {}).get("n", 0) >= 3:
                assert f"({_count(q['profit']['n'])})" in said
    # "with figures" counts companies whose key figures exist; changed on purpose (R28): only confirmed ones (an unconfirmed company is listed,
    # never in the figures)
    with_f = sum(1 for x in (v.get("sections") or {}).get("leaders") or [] if (x.get("revenue") is not None or x.get("profit") is not None)
                 and (v.get("status") or {}).get(x["symbol"]) != "unverified")
    assert v.get("with_figures") in (None, with_f) or name == "every part (fixture)"


def _count(n):
    return f"{n} compan{'y' if n == 1 else 'ies'}"


def test_page_counts_for_every_synthetic_theme():
    counts = page_counts()
    assert len(counts) >= 13 and all(n <= 22 for n in counts.values()), counts


# ---------- 1. plain names for industries shown as layers ----------
def test_industries_shown_as_layers_have_plain_names_in_both_markets():
    for raw, plain_ in (("Computer Peripheral Equipment, Nec", "Computer hardware"), ("Services-Prepackaged Software", "Software"),
                        ("Services-Business Services, Nec", "Business services"), ("Telephone Communications (No Radiotelephone)", "Telecom services"),
                        ("Services-Help Supply Services", "Help Supply Services"), ("Wholesale-Drugs Proprietaries And Druggists' Sundries",
                                                                                   "Wholesale-Drugs Proprietaries & Druggists' Sundries"),
                        ("Ship Building & Allied Services", "Shipbuilding"), ("Computers - Software & Consulting", "IT services"),
                        ("Explosives", "Explosives"), ("AUTO PARTS", "Auto Parts"), ("", "")):
        assert B.plain_industry(raw) == plain_, raw
    v, _ = deck_of(*us_list_theme())
    assert [x["layer"] for x in v["layers"]] == ["Software", "IT services", "Other industries"]
    rows = [{"symbol": "A", "industry": "Services-Prepackaged Software", "market_cap": 10}, {"symbol": "B", "industry": "Services-Prepackaged Software", "market_cap": 5}]
    out = B.with_base({"value_chain": []}, {"value_chain": [], "sub_themes": []}, rows, ["Services-Prepackaged Software"])
    assert out["value_chain"][0]["layer"] == "Software" and out["placements"]["industries"] == ["Services-Prepackaged Software"]   # matching stays on the raw name


# ---------- 2. a lender theme keeps the AI map's own layers ----------
def test_a_lender_theme_keeps_the_maps_layers_when_the_check_empties_them():
    rows = [{"symbol": f"B{i}", "name": f"Bank {i}", "industry": "Private Sector Bank", "market_cap": 100 - i} for i in range(8)]
    ai = {"value_chain": [{"layer": "Deposit gathering", "companies": [{"ticker": f"B{i}", "name": f"Bank {i}"} for i in range(3)]},
                          {"layer": "Retail and SME lending", "companies": [{"ticker": f"B{i}", "name": f"Bank {i}"} for i in (3, 4, 5, 0)]},
                          {"layer": "Microfinance", "companies": [{"ticker": "OUT1", "name": "Another industry"}]}], "sub_themes": []}
    checked = {"value_chain": [{**x, "companies": []} for x in ai["value_chain"]], "sub_themes": []}       # every "does it do this work" said no
    out = B.with_base(ai, checked, rows, ["Private Sector Bank"])
    lay = {x["layer"]: [c["ticker"] for c in x["companies"]] for x in out["value_chain"]}
    assert lay["Deposit gathering"] == ["B0", "B1", "B2"] and lay["Retail and SME lending"] == ["B3", "B4", "B5"]      # each bank in its first layer
    assert lay["Microfinance"] == [] and lay["Private banks"] == ["B6", "B7"]                     # the rest under its industry (R21: plain name)
    keep = {x["layer"]: [c["ticker"] for c in x["companies"]] for x in B.with_base(ai, {**checked, "value_chain": [
        {**ai["value_chain"][0], "companies": [{"ticker": "B0", "verified": True}]}, {**ai["value_chain"][1], "companies": [{"ticker": "B3", "verified": True}]},
        {**ai["value_chain"][2], "companies": []}]}, rows, ["Private Sector Bank"])["value_chain"]}
    assert keep["Deposit gathering"] == ["B0"] and keep["Retail and SME lending"] == ["B3"]                            # two layers kept: the check stands
    region, m, f, _, _ = bank_theme()
    v, slides = deck_of(region, m, f)
    # lane d1 (updated on purpose): the "Other" group of two confirmed companies is rows of the "Smaller layers" page, not a page of its own
    assert [s.title for s in slides if s.title.startswith("Layer ")] == ["Layer 1 · Deposit gathering", "Layer 2 · Retail and SME lending"]
    small = next(s for s in slides if s.title.startswith(deck.SMALL_TITLE))
    assert "Other private bank companies" in [r[0] for b in small.blocks if b["kind"] == "table" for r in b["rows"]]   # R21; R22: "bank", as an adjective reads


def test_a_map_layer_without_a_name_is_never_drawn():
    # R20 live: the Cybersecurity map came back with four of five layers named "" ("Layer 2 ·", "lowest in (6.6%)")
    from app.intel import ai as A
    assert A.layer_name({"layer": "", "name": "Identity and access"}) == "Identity and access"
    assert A.layer_name({"layer": "  ", "title": " Endpoint  security "}) == "Endpoint security" and A.layer_name({"layer": ""}) == ""
    rows = [{"symbol": f"S{i}", "name": f"Sec {i}", "industry": "Software", "market_cap": 100 - i} for i in range(6)]
    ai = {"value_chain": [{"layer": "Network security", "companies": [{"ticker": "S0"}, {"ticker": "S1"}, {"ticker": "S2"}]},
                          {"layer": "", "companies": [{"ticker": "S3"}, {"ticker": "S4"}]}], "sub_themes": []}
    checked = {"value_chain": [{**x, "companies": [{**c, "verified": True} for c in x["companies"]]} for x in ai["value_chain"]], "sub_themes": []}
    out = B.with_base(ai, checked, rows, ["Software"])                  # a map kept in the store from before the reader's fix
    names = [x["layer"] for x in out["value_chain"]]
    assert "" not in names and all(n.strip() for n in names)
    placed = {c["ticker"] for x in out["value_chain"] for c in x["companies"]}
    assert {"S3", "S4"} <= placed                                       # its companies are still in the deck, under their industry


def test_a_deck_waits_briefly_for_the_map_and_its_check_that_are_being_written(monkeypatch):
    calls = {"n": 0}
    done = threading.Event()
    maps = [{"generated_at": 0}, {"generated_at": 5.0}]

    class R:
        @staticmethod
        def sector_map(profile, region, q, refresh):
            calls["n"] += 1
            return "IN", "x theme", maps[min(calls["n"] - 1, 1)], []

        @staticmethod
        def theme_map(profile, region, q):          # R19: the theme library's stored read first (none kept here)
            return R.sector_map(profile, region, q, False)
    monkeypatch.setattr(T, "job_of", lambda key: {"state": "running", "done": done} if key[0] == "map" else None)
    monkeypatch.setattr(T, "checked", lambda r, theme, m: {**m, "placements": {"checked": True}})
    monkeypatch.setattr(T, "with_descriptions", lambda r, m: m)
    threading.Timer(0.05, done.set).start()
    r, theme, m = T.map_for_deck(R, {}, "IN", "x theme", wait=5)
    assert m["generated_at"] == 5.0 and calls["n"] == 2


# ---------- 3. the appendix fits 20 or more rows a page ----------
def test_the_appendix_of_60_companies_takes_three_pages():
    _, slides = deck_of(*long_theme())
    pages = [s for s in slides if s.title.startswith("Every company's figures")]
    rows = [len(plain(b["rows"])) for s in pages for b in s.blocks if b["kind"] == "table"]
    assert sum(rows) == 60 and len(pages) <= 3 and min(rows[:-1] or rows) >= 20, rows
    for s in pages:                      # every row on one line at the smallest body size, inside its slide
        b = next(b for b in s.blocks if b["kind"] == "table")
        lay = deck.table_layout(b, b["box"][2], b["box"][3])
        assert lay["size"] == deck.BODY_MIN and len(lay["rows"]) == len(b["rows"]) and sum(lay["heights"]) <= b["box"][3] + 1e-6


# ---------- 4. the operating figures' counts ----------
def test_the_operating_figures_subtitle_counts_the_companies_not_the_headings():
    biz = {"metric": "Total sales", "unit": "units", "span": "month", "period": "2026-09", "filed": "2026-10-01", "value": 100, "prev": 90, "year_ago": 80,
           "change_prev": 11.1, "change_year": 25.0}
    v = full_view()
    rows = [{**biz, "symbol": f"S{i}", "name": f"Company with a long name {i}", "metric": "Total dispatches including exports"} for i in range(30)]
    v["business"] = {"layers": [{"layer": "Mining", "rows": rows[:15]}, {"layer": "Cells", "rows": rows[15:]}], "subs": [], "held": []}
    s = next(x for x in deck.theme_plan(v)[0] if x.title == "Operating figures")
    shown = len(plain(next(b for b in s.blocks if b["kind"] == "table")["rows"]))
    assert s.subtitle == f"Operating figures filed with the exchange between results, as filed: {shown} of 30 companies' figures; the rest are on the theme's page"


# ---------- 7, 9, 10: true counts, the P/E's base, lenders' growth ----------
def test_with_figures_means_key_figures_and_the_valuation_says_whose_pe_it_is():
    v, slides = deck_of(*sparse_theme())
    assert v["with_figures"] == 2 and deck.coverage(v)["n"] == 2 and "9 in the exchange's industries · 2 with figures" in texts(slides)
    note = next(p for s in slides if s.title.startswith("Every company's figures") for b in s.blocks for p in b.get("paras") or [] if "No reported figures yet" in p)
    assert "Sparse 2 Ltd, Sparse 3 Ltd" in note
    v, slides = deck_of(*us_map_theme())
    val = table_of(slides, "Valuation")
    assert val["rows"][0][0] == "P/E, the 10 companies with one (77% of 13; 3 loss-makers with none)"           # R22: of the population stated
    assert "P/E of 10 of the 13 companies, 3 loss-makers with none" in next(s.subtitle for s in slides if s.title == "Valuation")


def test_deposit_growth_comes_from_the_reported_balance_sheet_and_only_where_it_is():
    p = {"pl": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Revenue": [100, 120], "Interest": [60, 70], "Net Profit": [15, 18]}},
         "balance": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Total Assets": [1000, 1200], "Deposits": [800, 900]}}}
    assert stock_pages.lender_figures(p)["deposit_growth"] == 12.5
    p["balance"]["rows"].pop("Deposits")
    assert "deposit_growth" not in stock_pages.lender_figures(p)
    region, m, f = nbfc_theme()
    v, slides = deck_of(region, m, f)
    assert "Deposit growth" not in texts(slides)                                     # none stored: no column, said nowhere


# ---------- 11. an AI layer shows the exchange's industry as a column ----------
def test_an_ai_layer_shows_each_companys_industry_as_a_column_not_as_layers():
    v, slides = deck_of(*us_map_theme())
    assert [x["layer"] for x in v["layers"]] == ["Endpoint security", "Network security", "Identity", "Cloud security", "Security services"]
    t = table_of(slides, "Layer 1 · Endpoint security")
    assert t["head"][1] == "Industry" and {r[1] for r in plain(t["rows"]) if not r[0].startswith(("Median", "Range"))} == {"Software", "Networking equipment", "IT services"}
    # changed on purpose (R28, the owner: "only important pages"): a one-company layer has no page of its own, it is a row of "Smaller layers"
    assert not any(s.title.startswith("Layer 5") for s in slides)
    # LIVE6-008 (updated on purpose): one such layer has no "Smaller layers" page for its one row; it is a row of the value chain's table
    assert not any(s.title.startswith("Smaller layers") for s in slides)
    assert "Security services" in [r[0] for r in table_of(slides, "The value chain by layer")["rows"]]
    cloud = table_of(slides, "Layer 4 · Cloud security")
    assert all(r[cloud["head"].index("EBITDA margin")].startswith("−") for r in plain(cloud["rows"])[:3])          # all loss-makers, shown as they are
