"""Release 18 (owner, 7 Nov: "this deck fixes are need to be done globally like for all and any sector not just for this"): the theme deck on
synthetic themes of any sector, India and the US. A lender theme gets lenders' measures; a theme that names a subset keeps only that subset;
an official-industry company stays in its theme unless its own words describe other work; the deck's counts agree with each other; a held
operating figure hides both its comparisons; whole figures print whole; each layer is one page and the core is short; a theme with no AI map
gets its layers from its companies' own industries or no value chain at all; and a page behind a results filing is built again first.
No figure or name here is tuned to any real company."""
import re
from datetime import datetime, timezone

from app import deck, stock_pages
from app.intel import theme_base as B
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests.test_export import plain, table_of, texts
from tests.test_theme1 import TODAY, facts

NOW = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)
ADVICE = ("buy", "sell", "avoid", "attractive", "cheap", "undervalued", "overvalued", "recommend", "target price")


def deck_of(region, m, f, theme=None, **kw):
    dive = D.build(region, theme or m["sector"], m, D.Sources(TODAY, facts=f.get, **kw))
    v = T.deck_view(region, m, dive, kw.pop("extra", None))
    return v, deck.theme_plan(v, now=NOW)[0]


def core(slides):
    """The slides before the appendix (R19: the appendix is the one table of every company's figures, no divider)."""
    at = next((i for i, s in enumerate(slides) if s.eyebrow and s.eyebrow.endswith("· Appendix")), len(slides))
    return slides[:at]


# ---------- the synthetic themes ----------
def bank_facts(sym, name, sales, profits, cap, roe, pb, gnpa, nnpa, nii, roa):
    return {**facts(sym, name, sales, [None] * 4, profits, cap=cap, pe=12.0, roce=None, de=None, industry=("Financial Services", "Banks")),
            "bank": True, "roe": roe, "pb": pb, "lender": {"gnpa": gnpa, "nnpa": nnpa, "nii_assets": nii, "roa": roa, "nii_growth": 9.0, "year": "Mar 2026"}}


def bank_theme():
    """An Indian lender theme that names a subset ("Private banks"): the exchange files banks under three industries, the AI's map has layers
    of its own (deposits, retail lending, an empty fee layer and one with no name) and named one public-sector lender in a layer."""
    rows = ([{"symbol": f"PVT{i}", "name": f"Private Lender {i} Ltd", "industry": "Private Sector Bank", "market_cap": 200000 - i * 15000} for i in range(8)]
            + [{"symbol": f"PSU{i}", "name": f"State Lender {i} Ltd", "industry": "Public Sector Bank", "market_cap": 150000 - i * 20000} for i in range(4)]
            + [{"symbol": f"SFL{i}", "name": f"Small Lender {i} Ltd", "industry": "Other Bank", "market_cap": 9000 - i * 1000} for i in range(2)]
            + [{"symbol": "STEEL", "name": "Steel Co", "industry": "Iron & Steel", "market_cap": 50000}])
    ai = {"sector": "Private banks", "summary": "Private lenders take deposits and lend to households and firms.",
          "value_chain": [{"layer": "Deposit gathering", "description": "Raise current and savings deposits through branches.",
                           "companies": [{"ticker": "PVT0", "name": "Private Lender 0 Ltd", "what": "accepts deposits through branches", "verified": True},
                                         {"ticker": "PVT1", "name": "Private Lender 1 Ltd", "what": "accepts deposits through branches", "verified": True},
                                         {"ticker": "PVT2", "name": "Private Lender 2 Ltd", "what": "accepts deposits through branches", "verified": True},
                                         {"ticker": "PSU0", "name": "State Lender 0 Ltd", "what": "accepts deposits through branches", "verified": True}]},
                          {"layer": "Retail and SME lending", "description": "Lend to households and small firms.",
                           "companies": [{"ticker": "PVT3", "name": "Private Lender 3 Ltd", "what": "lends to households and small firms", "verified": True},
                                         {"ticker": "PVT4", "name": "Private Lender 4 Ltd", "what": "lends to households and small firms", "verified": True},
                                         {"ticker": "PVT5", "name": "Private Lender 5 Ltd", "what": "lends to households and small firms", "verified": True}]},
                          {"layer": "", "description": "", "companies": []},
                          {"layer": "Fee and distribution income", "description": "Sell third-party products.", "companies": []}],
          "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0, "placements": {"checked": True, "pending": 3}}
    inds = B.industries_for("IN", ai["sector"], rows, None, lambda k: None, lambda k, v: None)
    m = B.with_base(ai, ai, rows, inds["industries"], named=inds["named"], exclude=inds["except"], drop=inds["drop"])
    m["placements"]["pending"] = 3                       # the AI's own check of its placements, still running: not a membership count
    f = {}
    for i in range(8):
        f[f"PVT{i}"] = bank_facts(f"PVT{i}", f"Private Lender {i} Ltd", [9000, 10000, 11000, 12000 + i * 500], [1500, 1700, 1900, 2000 + i * 40],
                                  200000 - i * 15000, roe=15.0 + i, pb=2.5 - i * 0.1, gnpa=1.5 + i * 0.2, nnpa=0.4 + i * 0.05, nii=3.0 + i * 0.1, roa=1.6)
    for i in range(4):
        f[f"PSU{i}"] = bank_facts(f"PSU{i}", f"State Lender {i} Ltd", [20000] * 4, [2000] * 4, 150000, roe=12.0, pb=1.0, gnpa=3.0, nnpa=0.8, nii=2.5, roa=1.0)
    return "IN", m, f, inds, rows


def us_list_theme(spread: bool = True):
    """A US theme with no AI map: the theme's own named list only, its companies under the SEC's industries (or one industry: `spread` False)."""
    inds = ["Services-Prepackaged Software"] * 5 + ["Services-Computer Programming Services"] * 3 + ["Services-Business Services, Nec", "Telephone Communications"]
    if not spread:
        inds = ["Services-Prepackaged Software"] * 10
    rows = [{"symbol": f"SEC{i}", "name": f"Secure {i} Inc", "industry": ind, "market_cap": 100000 - i * 8000} for i, ind in enumerate(inds)]
    blank = {"sector": "Network defence", "summary": "", "core": "", "value_chain": [], "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 0}
    m = B.with_base(blank, {**blank, "placements": {"checked": True, "pending": 0}}, rows, [], named=[r["symbol"] for r in rows])
    f = {}
    for i, r in enumerate(rows):
        f[r["symbol"]] = {**facts(r["symbol"], r["name"], [500, 600, 700, 800 + i * 20], [20.0, 21.0, 22.0, 18.0 + i], [50, 60, 70, 80 + i], cap=r["market_cap"],
                                  pe=40.0, industry=(r["industry"],)), "region": "US", "unit": "$ million"}
    return "US", m, f


def maker_theme():
    """An Indian makers' theme (any manufacturing sector): the exchange's own industries are the layers; the companies' own words describe
    their products in the style of real filings, most without repeating the theme's words."""
    say = {"MKR1": "Maker One is one of India's first motorcycle manufacturers",
           "MKR2": "Maker Two is engaged in the business of manufacturing and selling of aluminium die casting, suspension, transmission and braking products",
           "MKR3": "Maker Three is primarily engaged in the manufacturing of storage batteries and allied products in India",
           "MKR4": "Maker Four is one of India's leading engineering conglomerates engaged in the manufacturing of Agri-machinery, Construction & "
                   "Material Handling Equipment and Railway Equipment",
           "MKR5": "Maker Five supplies on-demand software to insurance companies",
           "MKR6": "Maker Six provides staffing and recruitment services"}
    cos = [{"ticker": s, "name": f"Maker {s[-1]} Ltd", "what": w, "base": True, "basis": "industry", "verified": None} for s, w in say.items()]
    m = {"sector": "Vehicles", "summary": "Makers of vehicles and their parts.",
         "value_chain": [{"layer": "2/3 Wheelers", "description": "", "official": True, "basis": "industry", "companies": cos[:2]},
                         {"layer": "Auto Components & Equipments", "description": "", "official": True, "basis": "industry", "companies": cos[2:]}],
         "sub_themes": [], "tailwinds": [], "risks": [],
         "placements": {"checked": True, "pending": 0, "placed": 6, "total": 6, "base": 6, "named": 0, "added": 0, "confirmed": 0,
                        "industries": ["2/3 Wheelers", "Auto Components & Equipments", "Tractors"]}}
    f = {c["ticker"]: facts(c["ticker"], c["name"], [1000, 1100, 1200, 1300], [15, 15, 14, 15], [100, 110, 120, 130], cap=50000 - k * 5000)
         for k, c in enumerate(cos)}
    return "IN", m, f


# ---------- 1. lenders get lenders' measures ----------
def test_a_lender_theme_shows_lenders_measures_and_never_a_column_that_is_empty_everywhere():
    region, m, f, _, _ = bank_theme()
    v, slides = deck_of(region, m, f)
    chain = table_of(slides, "The value chain by layer")
    assert "EBITDA margin" not in chain["head"] and "ROCE" not in chain["head"]
    for col in ("ROE", "NII / assets", "Gross NPA", "P/B"):
        assert col in chain["head"], col
    assert v["chain"]["measure"] == "roe" and v["chain"]["line"].startswith("Median return on equity is highest in")
    cards = next(b for s in slides if s.title == "Key findings" for b in s.blocks if b["kind"] == "cards")["items"]
    assert any(c["title"] == "Where the return sits" for c in cards)
    assert "Fewer than two layers" not in texts(slides) and "EBITDA margin –" not in texts(slides)
    for s in slides:                                           # no table anywhere has a column that is "–" in every row
        for b in s.blocks:
            if b["kind"] != "table" or len(plain(b["rows"])) < 2:
                continue
            for c in range(1, len(b["head"])):
                cells = [str(r[c] if not isinstance(r[c], dict) else r[c].get("text")) for r in plain(b["rows"])]
                assert any(x not in ("–", "") for x in cells), (s.title, b["head"][c])
    lead = table_of(slides, "Every company's figures")
    assert "ROE" in lead["head"] and "P/B" in lead["head"] and "EV/EBITDA" not in lead["head"]
    val = table_of(slides, "Valuation")
    assert not any(r[0].startswith("EV/EBITDA") for r in val["rows"])
    cover = dict((it[0], it[1]) for b in slides[0].blocks if b["kind"] == "stats" for it in b["items"])
    assert "Median ROE" in cover and "Median EBITDA margin" not in cover


def test_a_lenders_own_measures_come_from_its_reported_tables():
    p = {"quarters": {"cols": ["Jun 2026", "Sep 2026"], "rows": {"Gross NPA %": [1.4, 1.3], "Net NPA %": [0.4, None]}},
         "pl": {"cols": ["Mar 2025", "Mar 2026", "TTM"], "rows": {"Revenue": [1000, 1200, 1250], "Interest": [600, 700, 720], "Net Profit": [150, 180, 190]}},
         "balance": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Total Assets": [10000, 12000]}}}
    got = stock_pages.lender_figures(p)
    assert got == {"gnpa": 1.3, "nnpa": 0.4, "npa_of": "Jun 2026", "nii_assets": round(500 / 11000 * 100, 2), "roa": round(180 / 11000 * 100, 2),
                   "nii_growth": 25.0, "year": "Mar 2026"}
    assert stock_pages.lender_figures({}) is None
    row = D.company_row("IN", "PVT0", bank_theme()[2]["PVT0"])
    assert row["roe"] == 15.0 and row["gnpa"] == 1.5 and row["ebitda"] is None and row["ev_ebitda"] is None


# ---------- 2. a theme that names a subset keeps only that subset, in one scheme of layers ----------
def test_a_theme_that_names_a_subset_keeps_only_that_subset_whoever_named_the_rest():
    region, m, f, inds, rows = bank_theme()
    assert inds["industries"] == ["Private Sector Bank"] and inds["drop"] == ["Public Sector Bank", "Other Bank"]
    syms = {c["ticker"] for v in m["value_chain"] for c in v["companies"]}
    assert syms == {f"PVT{i}" for i in range(8)}                    # PSU0, which the AI named, is out too
    assert B.subset_pick("Indian banks", inds["industries"] + inds["drop"])[1] == []          # no subset named: every bank industry
    assert B.subset_pick("PSU banks", ["Private Sector Bank", "Public Sector Bank", "Other Bank"])[0] == ["Public Sector Bank"]
    assert B.subset_pick("Auto components", ["2/3 Wheelers", "Auto Components & Equipments"])[0] == ["Auto Components & Equipments"]
    assert B.subset_pick("Electric vehicles", ["Passenger Cars & Utility Vehicles", "2/3 Wheelers"])[1] == []   # the entry's own words narrow nothing
    us = [{"symbol": f"U{i}", "market_cap": c} for i, c in enumerate([50000, 9000, 3000, 1500, 400])]
    assert B.size_band("Small-cap pharma") == "small" and B.in_band("US", "small", us) == {"U3", "U4"} and B.size_band("Pharma") is None
    ind = [{"symbol": f"I{i}", "market_cap": 1000 - i} for i in range(300)]
    assert B.in_band("IN", "small", ind) == {f"I{i}" for i in range(250, 300)} and len(B.in_band("IN", "mid", ind)) == 150


def test_layers_are_one_scheme_the_maps_own_with_the_rest_in_the_appendix():
    region, m, f, _, _ = bank_theme()
    v, slides = deck_of(region, m, f)
    layer_titles = [s.title for s in core(slides) if re.match(r"Layer \d+ ·", s.title)]
    assert layer_titles == ["Layer 1 · Deposit gathering", "Layer 2 · Retail and SME lending"]
    assert "Private Sector Bank" not in [r[0] for r in table_of(slides, "The value chain by layer")["rows"]]
    t = texts(slides)
    # R19: the unplaced companies are a count and their names (up to five), and rows of the appendix's one table; no list page of their own
    assert ("2 more companies of the theme's industries the map doesn't place in a layer: "
            "Private Lender 6 Ltd, Private Lender 7 Ltd; in every median and total, and in the appendix.") in t
    figs = [r for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table" for r in b["rows"]]
    assert {r[0] for r in figs} >= {f"Private Lender {i} Ltd" for i in range(6, 8)}
    assert "No listed company is shown for Fee and distribution income:" in t and "shown for , " not in t      # never an empty name in a list


# ---------- 3. membership: the exchange's industry stands unless the company's own words describe other work ----------
def test_an_official_industry_company_stays_unless_its_own_words_describe_other_work():
    region, m, f = maker_theme()
    v, slides = deck_of(region, m, f)
    assert {s: v["status"][s] for s in ("MKR1", "MKR2", "MKR3", "MKR4")} == {s: "core" for s in ("MKR1", "MKR2", "MKR3", "MKR4")}
    assert v["status"]["MKR5"] == "unverified" and v["status"]["MKR6"] == "unverified"
    assert v["membership"] == {"placed": 6, "confirmed": 4, "not_confirmed": 2}
    words = D.theme_words({"sector": "Private banks", "placements": {"industries": ["Private Sector Bank"]}}, "Private banks")
    assert D.membership({"base": True, "basis": "industry", "what": "The bank provides retail banking and insurance distribution"}, words) == "core"


def test_the_membership_rules_version_is_in_every_kept_reads_key():
    assert T.check_key("IN", "Private Banks", {"generated_at": 5.5}) == ("IN", "private banks", 5, B.RULES)
    stored = {}
    B.industries_for("IN", "Glass bottles", [{"symbol": "Z", "industry": "Glass"}], lambda s, t: {"industries": ["Glass"]},
                     stored.get, stored.__setitem__)
    key = "theme:industries:IN:glass-bottles"
    assert '"rules": %d' % B.RULES in stored[key]
    stored[key] = stored[key].replace('"rules": %d' % B.RULES, '"rules": 1')          # a pick kept under older rules is made again
    asked = []
    B.industries_for("IN", "Glass bottles", [{"symbol": "Z", "industry": "Glass"}], lambda s, t: asked.append(1) or {"industries": ["Glass"]},
                     stored.get, stored.__setitem__)
    assert asked == [1]


# ---------- 4. the counts agree, and nothing is said that says nothing ----------
def test_the_deck_says_one_count_of_companies_not_confirmed_and_no_line_that_contradicts_another():
    region, m, f, _, _ = bank_theme()
    v, slides = deck_of(region, m, f)
    t = texts(slides)
    assert "Still being checked" not in t and "still being checked" not in t            # the AI's pending checks aren't a membership count
    assert "8 in the exchange's industries · 8 with figures (100% of value)" in t          # R20: one wording of the universe and the figures
    region, m, f = us_list_theme()
    v, slides = deck_of(region, m, f)
    how = next(it for s in slides if s.title == "How to read this deck" for b in s.blocks if b["kind"] == "cards" for it in b["items"])["lines"]
    assert how[0].startswith("No official industry is this theme's core on its own; its companies are the theme's own named list.")
    assert not any("The base is every listed company" in x for x in how)
    v["checks"]["one_off"] = [{"symbol": "SEC0", "name": "Secure 0 Inc", "net": 30.0, "ebitda": 25.0}]
    v["checks"]["net_with"], v["checks"]["net_without"] = 10.02, 9.98                       # the same to one decimal
    rows = deck.confidence_rows(v, deck.coverage(v), TODAY)
    one = next(r for r in rows if r[0] == "One-off earnings")
    assert one[2] == "Marked † and left out of net-margin medians."


# ---------- 5. a held figure hides both its comparisons ----------
def test_a_latest_figure_held_for_a_wild_move_shows_neither_comparison():
    biz = {"metric": "Total sales", "unit": "units", "span": "month", "period": "2026-09", "filed": "2026-10-01", "url": "https://example.com/f"}
    rows = [{**biz, "symbol": "MM", "name": "MM Co", "value": 38563, "prev": 114737, "change_prev": -66.4, "year_ago": 100298, "change_year": -61.6},
            {**biz, "symbol": "OK", "name": "OK Co", "value": 1100, "prev": 1000, "change_prev": 10.0, "year_ago": 900, "change_year": 22.2}]
    out = {r["symbol"]: r for r in D.hold_suspect(rows)}
    assert out["MM"]["year_ago"] is None and out["MM"]["change_year"] is None and out["MM"]["prev"] is None and out["MM"]["held_latest"]
    assert out["OK"]["change_year"] == 22.2 and not out["OK"].get("held_latest")
    slides = []
    deck._biz_slides(slides, "Operating figures", [{"group": "Layer A"}, out["MM"], out["OK"]], "E", TODAY)
    t = table_of(slides, "Operating figures")
    mm = plain(t["rows"])[0]
    assert mm[3] == "held" and mm[4] == "held" and mm[5] == "–" and mm[6] == "–"
    assert t["rows"][0] == {"group": "Layer A"}


# ---------- 6. one formatter: whole figures print whole ----------
def test_whole_figures_print_whole_everywhere_and_others_keep_one_decimal():
    assert deck.whole_figures("15.0%, 43.0x, 0.0 pts, 12.3%, ₹4.0 lakh cr, 100.0%") == "15%, 43x, 0 pts, 12.3%, ₹4 lakh cr, 100%"
    assert deck.whole_figures("Web 3.0 Ltd") == "Web 3.0 Ltd" and deck.whole_figures("1.05x") == "1.05x" and deck.whole_figures("0.0") == "0"
    for theme in (bank_theme()[:3], us_list_theme(), maker_theme()):
        _, slides = deck_of(*theme)
        t = texts(slides)
        assert not re.search(r"(?<![\w.,])\d[\d,]*\.0(?:%|x\b| pts| points)", t), re.findall(r".{20}\d\.0(?:%|x| pts).{10}", t)[:5]
        charts = [b for s in slides for b in s.blocks if b["kind"] in ("hbars", "columns", "lines")]
        assert charts and all(b.get("fmt") in (None, "pctw", "pct0", "num") or b["fmt"].endswith(("1", "1t")) for b in charts)


# ---------- 7. one page a layer, a short core ----------
def test_each_layer_is_one_page_and_the_full_table_is_in_the_appendix_with_its_page():
    from tests.test_r17_fixes import theme_a
    v, slides = deck_of(*theme_a())
    c = core(slides)
    conv = [s for s in c if s.title.startswith("Layer 2 · Converters")]
    assert len(conv) == 1 and conv[0].title == "Layer 2 · Converters"
    note = next(p for b in conv[0].blocks if b["kind"] == "text" for p in b["paras"] if p.startswith("The largest"))
    full = [i for i, s in enumerate(slides, 1) if s.title.startswith("Every company's figures")]          # R19: the appendix's one table
    assert full and note.endswith(f"appendix, p. {full[0]}.") and full[0] > len(c)
    rows = [r[0] for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table" for r in plain(b["rows"])]
    assert len([r for r in rows if r.startswith("Converter")]) == 14
    assert not any(s.title.startswith("Every company's figures") for s in c)            # per-company tables are out of the core
    assert not any(s.kind == "section" for s in c)                                      # one contents page instead of a divider a part
    contents = table_of(slides, "Contents")
    pages = {r[0]: int(r[2]) for r in contents["rows"]}
    assert slides[pages["The value chain"] - 1].title == "The value chain by layer" and slides[pages["Appendix"] - 1].title.startswith("Every company's figures")


def test_page_counts_of_the_synthetic_themes_stay_short():
    from tests.test_r17_fixes import theme_a
    counts = {}
    for name, theme in (("packaging", theme_a()), ("lenders", bank_theme()[:3]), ("us list", us_list_theme()), ("makers", maker_theme())):
        _, slides = deck_of(*theme)
        counts[name] = (len(core(slides)), len(slides))
    assert all(c <= 25 for c, _ in counts.values()), counts


# ---------- 8. no AI map: layers from the companies' own industries, or no value chain ----------
def test_a_theme_with_no_map_takes_its_layers_from_its_companies_industries_or_has_no_value_chain():
    region, m, f = us_list_theme()
    v, slides = deck_of(region, m, f)
    assert [x["layer"] for x in v["layers"]] == ["Software", "IT services", "Other industries"]          # R20: plain names
    titles = [s.title for s in slides]
    assert "The value chain by layer" in titles and "Layer 1 · Software" in titles
    assert "Named in the theme's list" not in [r[0] for r in table_of(slides, "The value chain by layer")["rows"]]
    region, m, f = us_list_theme(spread=False)
    v, slides = deck_of(region, m, f)
    titles = [s.title for s in slides]
    t = texts(slides)
    for gone in ("The value chain by layer", "Layers side by side", "Industry economics"):
        assert gone not in titles, gone
    assert not any(re.match(r"Layer \d+ ·", x) for x in titles)
    assert "Fewer than two layers" not in t and "the layers above don't place" not in t and "Where the margin sits" not in t
    cover = slides[0].blocks[0]["paras"][0]
    assert cover.startswith("Network defence: 10 companies listed in the US, worth $") and "the largest are Secure 0 Inc, Secure 1 Inc and Secure 2 Inc." in cover
    for word in ADVICE:
        assert not re.search(rf"\b{word}\b", t.lower()), word


# ---------- 9. a page behind a results filing is built first ----------
def test_a_page_behind_a_results_filing_is_marked_and_built_first(monkeypatch):
    store = {}
    monkeypatch.setattr(stock_pages, "_setting", lambda k: store.get(k))
    monkeypatch.setattr(stock_pages, "_put", lambda k, v: store.__setitem__(k, v))
    stock_pages.mark_due("US", {"AKX": "2026-11-05"})
    assert stock_pages.due_marks("US") == {"AKX": "2026-11-05"}
    filed = datetime(2026, 11, 5, tzinfo=timezone.utc).timestamp()
    assert stock_pages.filing_due("2026-11-05", filed - 30 * 86400, filed + 2 * 86400)                 # built before the filing: due
    assert not stock_pages.filing_due("2026-11-05", filed + 5 * 86400, filed + 6 * 86400)              # built after its data was out
    assert not stock_pages.filing_due("2026-11-05", filed + 86400, filed + 86400 + 3600)               # built an hour ago: not again yet
    assert not stock_pages.filing_due(None, 0, filed)
    # the dive marks the companies whose newer results are filed but not in their stored figures
    q = D.quarter_section([{"symbol": "AKX", "name": "AKX Inc", "quarter": {"of": "Jun 2026 vs Jun 2025", "sales": 5.0, "profit": 2.0}},
                           {"symbol": "B", "name": "B", "quarter": {"of": "Sep 2026 vs Sep 2025", "sales": 1.0, "profit": 1.0}},
                           {"symbol": "C", "name": "C", "quarter": {"of": "Sep 2026 vs Sep 2025", "sales": 1.0, "profit": 1.0}}],
                          [{"symbol": "AKX", "date": "2026-11-05"}])
    assert q["earlier"][0]["filed_unread"] == "2026-11-05"
