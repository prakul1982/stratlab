"""Release 40 (lane s3-r40): the owner's outside review of the live Release 39 decks, each fix generic and proven on the exact replay of the
live placement inputs (tests/test_exact_replay.py, refreshed to the Release 39 inputs: the moves and drops are in its APPROVED and DROPPED).

1. "outside the the theme": the peer set's sentence said as "this theme"; a repeated word said once on the finished pages and counted, in the
   deck's gate and in scripts/deck_check.py.
2. "Online retailers and marketplaces" names both a retailer's and a platform's way of earning: it takes the online sellers of its industry.
3. A company the theme's industry brought in whose own words describe another business (propane under retail, solar under semiconductors)
   is dropped from the theme and named on its coverage.
4. A layer the split named only by how its companies earn ("Makers of their own products") is shown, never ranked.
5. Auto: Bosch and Asahi India Glass in the component suppliers' figures (one industry, kin ways of making); a market-value half showing
   fewer than SPLIT_PART companies in its figures is undone.
6. The coverage says how many companies fit none of the map's layers; deck_check flags a theme where "Other" holds over 40%."""
import importlib.util
import os
import re

from app import deck
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from tests.test_deck_look import full_view
from tests.test_exact_replay import RECOVERED, live, now_layers, pre_map, replay
from tests.test_export import texts

PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py")
spec = importlib.util.spec_from_file_location("deck_check_r40", PATH)
DC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(DC)


# ---------- 1. the repeated word ----------
def test_the_peer_set_never_puts_one_the_beside_another_on_any_wrap():
    for sets in ({"sector": 93, "sector_theme": 1}, {"sector": 5}, {"sector_theme": 4}):
        words = deck.peer_set_words({"sets": sets})
        assert "this theme" in words and "the theme" not in words and deck.untwin(words)[1] == []
        for width in range(3, 14):                     # every line break: the last word of a line is never the first of the next
            toks = words.split()
            for i in range(0, len(toks), width):
                if i + width < len(toks):
                    assert toks[i + width - 1].lower() != toks[i + width].lower()
    assert deck.peer_set_words({"sets": {"sector": 93, "sector_theme": 1}}) == (
        "(own sector, similar market value: outside this theme for 93, with this theme's other companies counted for 1)")
    assert "outside this theme" in deck.PEERS_ROW[1]


def test_a_repeated_word_is_said_once_whatever_its_case_and_a_name_stays():
    assert deck.untwin("outside the the theme") == ("outside the theme", ["repeated word"])
    assert deck.untwin("The the median Of of 5") == ("The median Of 5", ["repeated word"])
    assert deck.untwin("margins margins rose")[0] == "margins rose"
    for clean in ("Bora Bora Resorts", "R R Kabel Ltd", "It had had a merger.", "outside this theme"):
        assert deck.untwin(clean) == (clean, [])


def test_a_word_repeated_after_the_text_was_repaired_is_said_once_before_the_deck_is_stored_and_counted():
    slides = deck.theme_plan(full_view())[0]
    gate = slides[0].gate
    assert all(x["id"] != "prose" or "repeated word" not in x["note"] for x in gate["items"])
    s = slides[2]
    s.blocks.append({"kind": "text", "paras": ["Figures of of the theme's companies"], "box": (1, 1, 5, 0.5)})
    s.subtitle = "The the largest companies"
    lay = deck.layout_gate([s])
    assert s.subtitle == "The largest companies" and s.blocks[-1]["paras"] == ["Figures of the theme's companies"]
    assert len(lay["twins"]) == 2 and all(x["why"] == "repeated word" for x in lay["twins"])
    got = deck.with_layout(gate, {**lay, "all_tidied": lay["twins"]})
    prose = next(x for x in got["items"] if x["id"] == "prose")
    assert prose["note"] == "2 text repairs (doubled words, punctuation, hyphens); 2 repeated words said once"


def test_a_repeated_word_left_in_a_cell_fails_the_prose_item():
    v = full_view()
    slides = deck.theme_plan(v)[0]
    t = next(s for s in slides if any(b["kind"] == "table" for b in s.blocks))
    b = next(b for b in t.blocks if b["kind"] == "table")
    b["rows"] = [list(r) for r in b["rows"]]
    b["rows"][0][0] = "the the cell"
    got = deck.publication_gate(slides, v, [])
    prose = next(x for x in got["items"] if x["id"] == "prose")
    assert not prose["ok"] and any(d["why"] == "text: repeated word" for d in got["dropped"])


def test_deck_check_counts_a_repeated_word_on_a_line_and_across_a_line_break_of_running_text():
    text = ("THEME · VALUATION\nValuation\nMedian P/E for the companies with comparable peers (own sector, similar market value: outside the\n"
            "the theme for 93)\n Of of the 12 companies\n\f")
    r = DC.check_text(text)
    assert r["counts"]["repeated"] == 2 and DC.failed(r)
    assert sorted(f["text"].split(" in: ")[0] for f in r["findings"] if f["kind"] == "repeated") == ["'Of of'", "'the the'"]
    ok = ("A\nB\n Bora Bora Resorts and R R Kabel Ltd; it had had a merger\n"
          "                                     vehicle makers\n"
          "                                                                     makers\n\f")
    assert DC.check_text(ok)["counts"]["repeated"] == 0          # a name, "had had", and another column's cell below: never counted


# ---------- 2. a layer whose name states two ways of earning ----------
def test_a_layer_name_states_each_way_of_earning_it_names():
    assert C.name_models("Online retailers and marketplaces") == {"retail", "platform"}
    assert C.name_models("Online marketplaces") == {"platform"}
    assert C.name_models("Off-price, dollar and discount store chains") == {"retail"}
    assert C.name_models("Tyre manufacturers") == set()


def test_only_online_sellers_join_the_online_layer_on_the_exact_replay():
    d = live("retail")
    was = {c["ticker"] for v in d["value_chain"] if v["layer"] == "Online retailers and marketplaces" for c in v["companies"]}
    now = {s_ for s_, x in now_layers("retail").items() if x == "Online retailers and marketplaces"}
    # lane d1 (updated on purpose): R40's nine online sellers are live since (in the inputs read from Release 41), and stay
    joined = {"CHWY", "RVLV", "SFIX", "DDL", "NXH", "AKA", "HOUR", "LITB", "QVCG"}
    assert was == now and joined <= now
    for s_ in joined:                          # each says "online" or "e-commerce" in its own words
        assert re.search(r"\bonline\b|\be-?commerce\b", d["evidence"][s_], re.I), s_
    # the thrift chain shares its industry, not its words: it stays in "Other"; the pawnbrokers are another business (R43): out of the theme
    assert now_layers("retail")["SVV"] == "Other" and not {"FCFS", "EZPW"} & set(now_layers("retail"))


# ---------- 3. another business filed under the theme's industry ----------
def test_propane_and_heating_oil_distributors_filed_as_retail_are_another_business():
    fuel = C.model_evidence("Retail-Miscellaneous Retail", "is primarily engaged in the retail distribution of propane and related equipment sales.")
    assert C.off_industry(fuel)
    assert C.off_industry(C.model_evidence("Retail-Miscellaneous Retail", "delivers home heating oil and fuel oil to customers."))
    shop = C.model_evidence("Retail-Miscellaneous Retail", "sells propane, outdoor gear and merchandise through its 300 stores.")
    assert not C.off_industry(shop)                                             # a store chain that sells propane among its goods
    assert not C.off_industry(C.model_evidence("Utilities", "distributes propane to homes."))       # not filed as retail: not this rule


def test_another_business_is_dropped_from_the_theme_and_named_once_with_its_industry():
    # lane d1 (updated on purpose): the inputs are read from the live Release 41, whose placement already dropped R40's propane distributors
    # and solar makers (so they are on the live coverage, not in the inputs); the replay under R43 drops the retail filers of another business
    d = live("retail")
    live_off = d["placements"]["off_industry"]
    assert {x["ticker"] for x in live_off} == {"FGPR", "SPH"} and {x["industry"] for x in live_off} == {"Retail-Miscellaneous Retail"}
    out, _ = replay("retail", carried=True)
    off = out["placements"]["off_industry"]
    r43 = {"CDW", "EZPW", "FBCD", "FCFS", "IPSI", "NSIT", "TMS", "WBUY"}
    assert {x["ticker"] for x in off} == r43 and not (r43 | {"FGPR", "SPH"}) & {c["ticker"] for v in out["value_chain"] for c in v["companies"]}
    m = pre_map(d, RECOVERED["origin"].get("retail"), RECOVERED["description"].get("retail"))
    m["placements"] = {"total": 96, "placed": 96, "base": 96}
    counted, _ = B.place_rest(m, d["theme"], lambda s_: d["evidence"].get(s_), ask=None, kept=d["kept"], carried=True)
    assert {k: counted["placements"][k] for k in ("total", "placed", "base")} == {"total": 88, "placed": 88, "base": 88}
    assert {x["ticker"] for x in live("semis")["placements"]["off_industry"]} == {"DQ", "TE", "TYGO", "FTCI", "SUNE", "ASTI", "MAXNQ"}
    v = {"placements": {"off_industry": live_off}}
    assert deck.off_industry_line(v) == ("Filed under Retail-Miscellaneous Retail but in another business: Suburban Propane Partners LP, "
                                         "Ferrellgas Partners L P.")


def test_a_company_the_map_named_is_never_dropped():
    vc = [{"layer": "Chip makers", "companies": [{"ticker": "SOL", "name": "Sol", "industry": "Semiconductors & Related Devices"}]},
          {"layer": "Other", "official": True, "basis": "rest", "companies": [{"ticker": "PV", "name": "PV", "industry": "Semiconductors"}]}]
    ev = {"SOL": "Industry: Semiconductors. Makes solar modules.", "PV": "Industry: Semiconductors. Makes solar modules."}
    out, off = B.without_off_industry(vc, {"PV"}, ev.get)
    assert [x["ticker"] for x in off] == ["PV"] and [v["layer"] for v in out] == ["Chip makers"]          # "Other" left empty: dropped
    assert out[0]["companies"][0]["ticker"] == "SOL"


# ---------- 4. a layer named only by how its companies earn ----------
def test_a_split_layer_named_by_how_its_companies_earn_is_shown_never_ranked():
    out, _ = replay("semis", carried=True)
    makers = next(v for v in out["value_chain"] if v["layer"] == "Makers of their own products")
    assert makers["model"].get("by_how") and makers.get("by_model")
    assert not any((v.get("model") or {}).get("by_how") for v in out["value_chain"] if not v.get("by_model"))
    assert not D.headline_ok(12, 12, makers["model"]) and D.headline_ok(12, 12, {**makers["model"], "by_how": False})

    def blk(name, e, how=False):
        cos = [{"symbol": f"{name}{i}", "status": "core", "year": "Dec 2025"} for i in range(6)]
        return {"layer": name, "n": 6, "revenue": 100.0, "companies": cos, "stats": {"ebitda": {"n": 6, "median": e}, "net": None, "roce": None},
                "model": {"id": "manufacturing", "family": "making", "line": "", **({"by_how": True} if how else {})}}
    ch = D.chain_table([blk("Analog chips", 30.0), blk("Power chips", 20.0), blk("Makers of their own products", 45.0, how=True)])
    assert ch["highest"] == "Analog chips" and set(ch["compared"]) == {"Analog chips", "Power chips"}
    assert ch["line"].endswith("Shown, not ranked: Makers of their own products (45.0%), a group by how they earn, of different businesses.")
    assert ch["line"].startswith("Among the 2 layers with at least 5 companies with the figure and one kind of business")


# ---------- 5. auto ----------
def test_bosch_and_asahi_are_in_the_component_layer_s_figures():
    out, _ = replay("auto", carried=True)
    rows = {c["ticker"]: c for v in out["value_chain"] if v["layer"].startswith("Component and systems suppliers") for c in v["companies"]}
    for s_ in ("BOSCHLTD", "ASAHIINDIA"):
        assert rows[s_]["model"] == "manufacturing" and not rows[s_].get("model_out")
    # a company of another business is never counted for its kin: a solar maker filed as semiconductors in a makers' layer stays out
    vc = [{"layer": "Chip makers", "companies": [{"ticker": f"P{i}", "industry": "Semis"} for i in range(4)] + [{"ticker": "SOL", "industry": "Semis"}]}]
    ev = {**{f"P{i}": "Industry: Semis. Designs and sells parts." for i in range(4)}, "SOL": "Industry: Semiconductors. Makes solar modules."}
    got = B.by_model(vc, {**{f"P{i}": "components" for i in range(4)}, "SOL": "manufacturing"}, "Chips", evidence_of=ev.get)
    assert next(c for c in got[0]["companies"] if c["ticker"] == "SOL").get("model_out") == "other"


def test_a_half_showing_fewer_than_split_part_companies_in_its_figures_is_undone():
    out, _ = replay("auto", carried=True)
    fm, _ = B.for_figures(out)
    shown = {c["ticker"] for v in fm["value_chain"] for c in v["companies"]}
    small = next(v for v in out["value_chain"] if v["layer"] == "Component and systems suppliers (smaller)")
    assert len(small["companies"]) == 69 and len([c for c in small["companies"] if c["ticker"] in shown]) == 1          # why: the figures' cap
    got = B.unsplit_unshown(out["value_chain"], shown)
    layers = [v["layer"] for v in got if v["layer"].startswith("Component and systems suppliers")]
    assert layers == ["Component and systems suppliers"]
    bank, _ = replay("bank", carried=True)                 # both halves show 5: kept
    every = {c["ticker"] for v in bank["value_chain"] for c in v["companies"]}
    assert B.unsplit_unshown(bank["value_chain"], every) == bank["value_chain"]


# ---------- 6. "Other" counted on the coverage ----------
def test_the_coverage_says_how_many_companies_fit_none_of_the_map_s_layers_and_deck_check_flags_over_40_percent():
    v = full_view()
    v["members"] = ([{"symbol": f"A{i}", "layer": "Makers"} for i in range(6)]
                    + [{"symbol": f"O{i}", "layer": "Other test companies", "rest": True} for i in range(4)]
                    + [{"symbol": "S1", "layer": "Named in a sub-theme only"}])
    v["placements"] = {**(v.get("placements") or {}), "off_industry": [{"ticker": "PRO", "name": "Propane Co", "industry": "Retail-Miscellaneous Retail"}]}
    # lane d1 (updated on purpose): every company is counted (a company named in a sub-theme only is in "Other" on a real map), and the row
    # says those that fit none apart from those not checked yet
    assert deck.rest_count(v) == (4, 11, "Other test companies", 0)
    slides = deck.theme_plan(v)[0]
    t = texts(slides)
    assert "in “Other test companies”, listed, never compared: 4 of 11 fit none of the map's layers" in t
    assert "Filed under Retail-Miscellaneous Retail but in another business: Propane Co." in t
    conf = next(s for s in slides if s.title == "Data confidence")
    rows = [r for b in conf.blocks if b["kind"] == "table" and b["head"] == deck.COVERAGE_HEAD for r in b["rows"]]
    assert ["In no layer", "4 of 11"] == rows[[r[0] for r in rows].index("In no layer")][:2]
    assert deck.coverage_table_flags(rows, v, deck.coverage(v)) == []
    low = DC.check_text("A\nB\n In no layer   40 of 100   companies fit none of the map's layers (in “Other”)\n\f")
    high = DC.check_text("A\nB\n In no layer   50 of 100   companies fit none of the map's layers (in “Other”)\n\f")
    assert low["counts"]["other>40%"] == 0 and high["counts"]["other>40%"] == 1
    assert not DC.failed(high) and DC.failed(high, strict=True)
    assert "50 of 100 companies fit none of the map's layers (50%)" in DC.report({"d": high})


# ---------- the deck's cache key (another lane's finding) ----------
def test_the_deck_s_cache_key_changes_with_the_dive_text_and_the_sector_figure_rules(monkeypatch):
    from datetime import date

    from app.intel import sector_metrics as S
    from app.intel import theme_routes as TR
    args = ("IN", "Automotive", "pdf", date(2026, 11, 12), 1, False, (True, False), 0)
    key = TR.deck_key(*args)
    assert key == ("IN", "automotive", "pdf", "2026-11-12", 1, False, (True, False), B.RULES, deck.THEME_DECK_VERSION,
                   f"td{D.DIVE_TEXT}", f"sm{S.VERSION}", 0)
    monkeypatch.setattr(D, "DIVE_TEXT", D.DIVE_TEXT + 1)
    assert TR.deck_key(*args) != key
    monkeypatch.setattr(D, "DIVE_TEXT", D.DIVE_TEXT - 1)
    assert TR.deck_key(*args) == key
    monkeypatch.setattr(S, "VERSION", S.VERSION + 1)
    assert TR.deck_key(*args) != key


def test_a_coloured_table_cell_is_measured_bold_so_its_row_holds_it_whole():
    """R40 (live Consumer retail deck, p. 6: "Online retailers / and…"): the highest and lowest layers' names are drawn bold and coloured;
    measured plain, the lowest one's row had a line too few at the width where bold wraps once more, and the name was cut."""
    from app import deck as D
    D._fonts()
    name = "Online retailers and marketplaces"
    for w0 in (1.43, 1.55, 1.66):
        b = {"head": ["Layer", "Companies"], "rows": [[name, "15"], ["Home improvement", "3"]], "widths": [w0, 1.2],
             "colors": {(0, 0): D.DOWN}, "tight": True}
        lay = D.table_layout(b, w0 + 1.2, 9.0)
        size, cw = lay["size"], lay["widths"][0]
        need = len(D.wrap(name, size, cw - 0.2, True))
        held = round((lay["heights"][1] - 0.12) / (size * 1.3 / 72))
        assert held >= need, (w0, size, need, held)


def test_a_paragraph_cut_to_its_lines_never_ends_on_a_joining_word():
    from app import deck as D
    D._fonts()
    for w in (1.25, 1.4, 1.6, 2.0):
        got = D.fit_paras(["Online retailers and marketplaces of every kind and size"], 11, w, 2 * D._lh(11))
        assert got and not D._JOINER.search(got[-1].rstrip("…")), (w, got)
