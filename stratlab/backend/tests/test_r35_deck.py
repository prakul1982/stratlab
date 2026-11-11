"""Release 35 (lane l1-deck): theme deck content fixes from the GPT reviews of the live R31.5-R31.9 decks, each generic (every sector, India
and the US) and each checked on theme_plan's own slides.
1. The peer P/E line names the close its prices are of on every slide that states it (publication_gate set it after the slides were written).
2. A layer page with companies left out of its calculations says who is in and why each of the others is not; names it leaves off are in
   the appendix's "Who is in each layer's calculations".
3. Each peer median keeps the peers behind it and their price date; a median more than 5% from the stored run before it is said with both.
4. A compact table never cuts a figure with its count ("74 days (59 of 90)"): the column is widened, else the cell wraps.
5. The appendix says in full each layer name its table shows cut.
Synthetic themes only: no real company's name or figure."""
import copy
import json
import re

from app import deck
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests.synth_structures_r27class import _rows, build
from tests.synthetic_themes_r27 import chemicals_in
from tests.test_export import plain, texts
from tests.test_r18_deck import NOW, deck_of
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
from tests.test_r29_cover import card_lines

PRICED = "(prices at the 2026-10-06 close)"


def chemicals(day="2026-10-06"):
    region, m, f, market = chemicals_in()
    return region, m, f, [{**x, "price_at": day} for x in market]


def paras(slides, title):
    return [p for s in slides if s.title.startswith(title) for b in s.blocks if b["kind"] == "text" for p in b["paras"]]


# ---------- 1. the peer P/E line's price date ----------
def test_every_slide_that_states_the_peer_pe_names_its_price_date():
    region, m, f, market = chemicals()
    v, slides = deck_of(region, m, f, index_rows=lambda: market)
    pp = v["sections"]["valuation"]["peers"]["pe"]
    assert pp["as_of"] == "2026-10-06" and pp["premium"] is not None          # the peers' close, a day after the companies' own
    said = [x for x in [s.subtitle or "" for s in slides] + card_lines(slides) if "their peers' median of" in x]
    assert len(said) >= 3 and all(PRICED in x for x in said), said               # the findings, the questions and the valuation page
    assert PRICED in next(s.subtitle for s in slides if s.title == "Valuation")
    assert next(x for x in slides[0].gate["items"] if x["id"] == "reconcile")["ok"] and not slides[0].gate["dropped"]
    every_rule("chemicals, peers priced", v, slides)


def test_a_dive_kept_from_before_takes_the_decks_own_day_before_any_slide_is_written():
    region, m, f, market = chemicals()
    v, _ = deck_of(region, m, f, index_rows=lambda: market)
    v = copy.deepcopy(v)
    v["sections"]["valuation"]["peers"]["pe"].pop("as_of")                      # as a dive stored before R35 holds it
    slides = deck.theme_plan(v, now=NOW)[0]
    said = [x for x in [s.subtitle or "" for s in slides] + card_lines(slides) if "their peers' median of" in x]
    assert len(said) >= 3 and all(f"(prices at the {v['as_of']} close)" in x for x in said), said
    # every reader of the peers goes through the one function that dates them
    src = open(deck.__file__).read()
    assert src.count("pe_peer_line(") - 1 == 3 and src.count("peers = dated_peers(v)") == 4
    assert not re.search(r"peers = \(?\(?(?:sec|val|v)\.get", src)


# ---------- 2. who is in a layer's calculations ----------
def it_theme():
    """One layer of thirty listed companies with twenty in its calculations (the live IT deck's shape: 27 listed, 17 in), and one of four."""
    t = build("IN", "IT services", [
        ("Large outsourcing", "Runs clients' systems.",
         _rows("RUN", 20, "Runwell Managed Services", "runs clients' IT systems under managed services contracts", "Computers - Software & Consulting",
               "managed_services")
         + _rows("TAG", 7, "Tagalong Software", "sells subscriptions for its own software", "Software Products", "software")
         + _rows("VAG", 2, "Vague", "a technology group", "Computers - Software & Consulting", "")
         + _rows("STR", 1, "Stranger", "a maker of steel pipes and tubes", "Iron & Steel Products", "")),
        ("Software products", "Sells software.", _rows("SAS", 4, "Cloudly", "sells subscriptions for its own SaaS software", "Software Products", "software")),
    ], [])
    m = t["map"]
    for c in m["value_chain"][0]["companies"]:
        kind = c["ticker"][:3]
        c.update(model={"RUN": "managed_services", "TAG": "software"}.get(kind, ""), model_confidence="high" if kind in ("RUN", "TAG") else "")
        if kind == "TAG":
            c["model_out"] = "other"
        elif kind == "VAG":
            c["model_out"] = "unknown"
        elif kind == "STR":
            c.update(base=False, basis="added", verified=False, model_out="unknown")
    for c in m["value_chain"][1]["companies"]:
        c.update(model="software", model_confidence="high")
    return t["region"], m, t["facts"]


def test_a_layer_page_says_who_is_in_its_calculations_and_why_each_other_is_not():
    region, m, f = it_theme()
    v, slides = deck_of(region, m, f)
    page = next(s for s in slides if s.title.endswith("· Large outsourcing"))
    assert page.subtitle.startswith("30 companies (20 in the layer's calculations)")
    at = next(i for i, s in enumerate(slides, 1) if s.title.startswith(deck.ROLL_TITLE))
    run, tag = "Runwell Managed Services", "Tagalong Software"
    note = paras(slides, page.title)
    roll_note = next(p for p in note if p.startswith("In the layer's calculations"))
    # thirty long names take more than two lines, and six of each group still do: three of each, the count of the rest, and the appendix page
    # that names every one
    assert roll_note == ("In the layer's calculations (20 of 30): " + ", ".join(f"{run} {i}" for i in range(3)) + " and 17 more. "
                         "Left out (10): " + ", ".join(f"{tag} {i}" for i in range(3)) + " and 4 more (other business); "
                         f"Vague 0, Vague 1 (way of earning not shown); Stranger 0 (not confirmed). Every one: appendix, p. {at}.")
    assert len(deck.wrap(roll_note, deck.BODY_MIN, deck.CW)) <= deck.ROLL_LINES
    assert not any(p.startswith("(not confirmed)") for p in note)             # no "(not confirmed)" row on the page: the roll's line says it
    text = next(b for b in page.blocks if b["kind"] == "text" and roll_note in b["paras"])
    assert sum(deck.note_h(p) for p in text["paras"]) <= text["box"][3] + 1e-6 and text["box"][1] + text["box"][3] <= deck.BOT + 1e-6    # in its room
    # the layer with every company in its calculations has no such line, and no row in the appendix
    assert not [p for p in paras(slides, "Layer 2") if "In the layer's calculations" in p]
    roll = slides[at - 1]
    assert roll.eyebrow.endswith("· Appendix") and at > next(i for i, s in enumerate(slides, 1) if s.title.startswith("Every company's figures"))
    table = next(b for b in roll.blocks if b["kind"] == "table")
    assert table["head"] == ["Layer", "In its calculations", "Left out, and why"] and [r[0] for r in table["rows"]] == ["Large outsourcing"]
    row = table["rows"][0]
    assert row[1] == "20 of 30: " + ", ".join(f"{run} {i}" for i in range(20))                  # every one named
    assert row[2] == ("10: " + ", ".join(f"{tag} {i}" for i in range(7)) + " (other business); Vague 0, Vague 1 (way of earning not shown); "
                      "Stranger 0 (not confirmed)")
    lay = deck.table_layout(table, table["box"][2], table["box"][3])
    assert len(lay["rows"]) == 1                                                               # the row is on its page whole
    assert "who is in each layer's calculations" in texts([s for s in slides if s.title == "Contents"])
    assert slides[0].gate["passed"] == slides[0].gate["of"], slides[0].gate
    # the appendix is its tables: every company's figures, then the roll (the every-rule check, changed on purpose for R35)
    assert all(s.title.startswith(("Every company's figures", deck.ROLL_TITLE)) for s in slides if s.eyebrow and s.eyebrow.endswith("· Appendix"))
    every_rule("IT, a long roll", v, slides)


def test_a_short_roll_stays_on_the_layer_page_and_adds_no_appendix_page():
    from tests.synth_structures_r27class import banks_in
    from app.intel import theme_base as B
    t = banks_in()
    vc = B.by_model(copy.deepcopy(t["map"]["value_chain"]), t["models"], "Banks", tags=t["tags"], confidence=t["confidence"])
    v, slides = deck_of(t["region"], {**t["map"], "value_chain": vc}, t["facts"])
    page = next(s for s in slides if s.title.endswith("· Retail and commercial lenders"))
    assert "(5 in the layer's calculations)" in page.subtitle
    assert ("In the layer's calculations (5 of 7): Lendwell 0, Lendwell 1, Lendwell 2, Lendwell 3, Lendwell 4. "
            "Left out (2): Vaguebank 0, Quietfin 0 (way of earning not shown).") in " ".join(paras(slides, page.title))
    assert not any(s.title.startswith(deck.ROLL_TITLE) for s in slides)
    every_rule("banks, a short roll", v, slides)


def test_a_page_that_shows_every_company_says_it_on_their_rows_and_keeps_its_room():
    t = build("IN", "Lenders", [
        ("Lenders", "Lend.", [(f"L{i}", f"Loanco {i} Ltd", "a bank that lends", "Private Sector Bank", "lending", (), "high") for i in range(3)]
         + [("LW", "Vaguefin Ltd", "a group", "Private Sector Bank", "lending", (), "low")]),
        ("Fund managers", "Fees.", [(f"F{i}", f"Fundco {i} Ltd", "manages funds for fees", "Asset Management Company", "asset_management", (), "high")
                                    for i in range(3)])], [])
    from app.intel import theme_base as B
    vc = B.by_model(copy.deepcopy(t["map"]["value_chain"]), t["models"], "Lenders", tags=t["tags"], confidence=t["confidence"])
    _, slides = deck_of("IN", {**t["map"], "value_chain": vc}, t["facts"])
    page = next(s for s in slides if s.title.startswith("Layer ") and "Lenders" in s.title)
    assert "(3 in the layer's calculations)" in page.subtitle
    cells = [str(r[0]) for b in page.blocks if b["kind"] == "table" for r in b["rows"]]
    assert cells[:4] == ["Loanco 0 Ltd", "Loanco 1 Ltd", "Loanco 2 Ltd", "Vaguefin Ltd (left out)"]            # every company, the one left out marked
    note = " ".join(paras(slides, page.title))
    assert "(left out):" in note and "In the layer's calculations" not in note


def test_the_roll_counts_as_the_header_does_and_names_each_reason():
    cos = [{"symbol": "A", "name": "Alpha Ltd", "revenue": 10, "ebitda": 20.0, "net": 9.0},
           {"symbol": "B", "name": "Beta Limited", "revenue": 10, "ebitda": 20.0, "net": None},
           {"symbol": "C", "name": "Gamma Inc.", "revenue": 10, "ebitda": 20.0, "net": 30.0, "one_off": True},
           {"symbol": "W", "name": "Wide Corp", "revenue": 99, "ebitda": 11.0, "net": 5.0, "company_wide": True},
           {"symbol": "N", "name": "Nofig Ltd", "revenue": None},
           {"symbol": "O", "name": "Other Ltd", "revenue": 5, "model_out": "other"},
           {"symbol": "U", "name": "Unknown Ltd", "revenue": 5, "model_out": "unknown"},
           {"symbol": "X", "name": "Unsure Ltd", "revenue": 5, "status": "unverified", "model_out": "unknown"}]
    layer = {"layer": "L", "n": 5, "revenue": 129, "stats_over": "own"}
    ins, outs = deck.layer_roll(layer, cos)
    assert ins == [("Alpha", ""), ("Beta", "figures in part"), ("Gamma", "figures in part"), ("Wide", "whole company: revenue only")]
    assert outs == [("Nofig", "no revenue figure"), ("Other", "other business"), ("Unknown", "way of earning not shown"), ("Unsure", "not confirmed")]
    assert deck.layer_head(layer, cos, lambda x: f"₹{x} cr").startswith("8 companies (4 in the layer's calculations)")
    line, cut = deck.roll_line(ins, outs)
    assert not cut and line == ("In the layer's calculations (4 of 8): Alpha; Beta (figures in part), Gamma (figures in part), Wide (whole company: "
                                "revenue only). Left out (4): Other (other business); Unknown (way of earning not shown); Unsure (not confirmed); "
                                "Nofig (no revenue figure).")
    # a layer whose every company is the whole company's keeps them in its medians: no "revenue only"
    assert deck.layer_roll({**layer, "stats_over": "all"}, cos)[0][3] == ("Wide", "")


# ---------- 3. the peers behind a peer median, and a median that moved ----------
def test_each_peer_median_keeps_its_peers_and_their_price_date():
    region, m, f, market = chemicals()
    v, _ = deck_of(region, m, f, index_rows=lambda: market)
    peers = v["sections"]["valuation"]["peers"]
    names = {x["symbol"] for x in market}
    for key in ("pe", "sales_3y", "roce"):
        pp = peers[key]
        assert pp["as_of"] == "2026-10-06" and 0 < len(pp["symbols"]) <= D.PEER_KEEP and pp["symbols_n"] >= len(pp["symbols"])
        assert set(pp["symbols"]) <= names and not set(pp["symbols"]) & set(f)             # peers outside the theme, by symbol
    assert "moved" not in peers["pe"]                                                       # a first run has nothing before it
    # bounded: a market of more peers than are kept names the most used and counts the rest
    rows = [{"symbol": f"T{i}", "pe": 20.0 + i, "cap": 10000.0, "sector": "Chemicals", "price_at": "2026-10-05"} for i in range(3)]
    wide = [{"symbol": f"M{i:03d}", "pe": 15.0, "market_cap": 9000.0 + i, "sector": "Chemicals", "price_at": "2026-10-07"} for i in range(D.PEER_KEEP + 30)]
    got = D.peers_section(rows, wide)["pe"]
    assert len(got["symbols"]) == D.PEER_KEEP and got["symbols_n"] == D.PEER_KEEP + 30 and got["as_of"] == "2026-10-07"
    assert D.peers_section(rows, [{k: x for k, x in w.items() if k != "price_at"} for w in wide], "2026-10-01")["pe"]["as_of"] == "2026-10-05"


def test_a_peer_median_more_than_five_percent_from_the_run_before_is_said_with_both():
    region, m, f, market = chemicals()
    base, _ = deck_of(region, m, f, index_rows=lambda: market)
    now = base["sections"]["valuation"]["peers"]["pe"]["peers"]
    was = round(now * 1.08, 1)
    asked = []

    def history(prev):
        def read(key, point):
            asked.append((key, point))
            return [{"d": "2026-09-01", "peers": 9.9, "k": 5}, prev, point]
        return read
    v, slides = deck_of(region, m, f, index_rows=lambda: market, peer_history=history({"d": "2026-10-01", "peers": was, "k": 24}))
    key, point = asked[-1]
    assert key == D.slug(m["sector"]) and point == {"d": "2026-10-06", "peers": now, "k": 24, "n": 11}
    mv = v["sections"]["valuation"]["peers"]["pe"]["moved"]
    assert mv == {"from": was, "on": "2026-10-01", "to": now, "at": "2026-10-06", "pct": round((now / was - 1) * 100, 1), "peers_from": 24, "peers_to": 24,
                  "n_from": None, "n_to": 11}
    note = next(ln for ln in card_lines([s for s in slides if s.title == "Valuation"]) if ln.startswith("Their peers' median P/E was"))
    w = deck.whole_figures
    assert note == w(f"Their peers' median P/E was {was:.1f}x at the 2026-10-01 close and is {now:.1f}x at the 2026-10-06 close: "
                     "prices moved between the two closes.")
    assert slides[0].gate["passed"] == slides[0].gate["of"], slides[0].gate
    every_rule("chemicals, peer median moved", v, slides)
    # within 5%: nothing is said; the same close with another peer list: said as that, with both counts
    v2, slides2 = deck_of(region, m, f, index_rows=lambda: market, peer_history=history({"d": "2026-10-01", "peers": round(now * 1.04, 1), "k": 24}))
    assert "moved" not in v2["sections"]["valuation"]["peers"]["pe"] and "Their peers' median P/E was" not in " ".join(card_lines(slides2))
    same = deck.peer_moved_line({"moved": D.peer_moved([{"d": "2026-10-06", "peers": 19.2, "k": 212, "n": 37},
                                                        {"d": "2026-10-06", "peers": 18.0, "k": 208, "n": 35}])})
    assert w(same) == ("Their peers' median P/E was 19.2x at an earlier run on the 2026-10-06 close and is 18x now: the peers or their reported "
                       "figures changed; 37 of the theme's companies compared then, 35 now; 212 peers behind it then, 208 now.")
    assert D.peer_moved([{"d": "2026-10-06", "peers": 18.0}]) is None and D.peer_moved([]) is None and deck.peer_moved_line({}) == ""
    for word in ("cheap", "expensive", "fell", "rose", "worse", "better"):
        assert word not in note and word not in same


def test_the_kept_peer_medians_are_one_a_run_that_differs_and_never_more_than_a_few(monkeypatch):
    store = {}
    monkeypatch.setattr(T.db, "get_setting", lambda k, *a: store.get(k))
    monkeypatch.setattr(T.db, "set_setting", lambda k, val: store.__setitem__(k, val))
    read = T.sources("IN", "Speciality chemicals").peer_history
    first = read("x", {"d": "2026-10-01", "peers": 19.2, "k": 30})
    assert first == [{"d": "2026-10-01", "peers": 19.2, "k": 30}]
    assert read("x", {"d": "2026-10-01", "peers": 19.2, "k": 30}) == first                 # the same run again: not kept twice
    for i in range(2, 20):
        pts = read("x", {"d": f"2026-10-{i:02d}", "peers": 19.0 + i / 10, "k": 30})
    assert len(pts) == D.PEER_RUNS and pts[-1]["d"] == "2026-10-19" and pts[0]["d"] == "2026-10-12"
    assert list(store) == ["theme:peers:IN:speciality-chemicals"] and len(json.loads(store["theme:peers:IN:speciality-chemicals"])) == D.PEER_RUNS
    assert len(store["theme:peers:IN:speciality-chemicals"]) < 600                          # bounded storage
    assert T.sources("US", "Speciality chemicals").peer_history("x", {"d": "2026-10-01", "peers": 30.0, "k": 9}) == [{"d": "2026-10-01", "peers": 30.0, "k": 9}]
    assert D.DIVE_TEXT == 6


# ---------- 4. a median row's figure with its count is never cut ----------
def us_sector_deck():
    from tests.test_r20_deck import us_map_theme
    from tests.test_r23_metrics import companyfacts
    from app.intel import sector_metrics as S
    region, m, f = us_map_theme()
    pieces = {}
    for i, sym in enumerate(sorted(f)):
        got = S.us_figures(companyfacts())
        got.pop("_end")
        if i % 3 == 0:
            for k in ("sbc_share", "rpo_growth", "deferred_growth", "fcf_margin"):
                got.pop(k, None)                             # figures fewer companies file: "N of M" in their median cells
        pieces[sym] = {"family": "us", "end": "2026-01-31", "metrics": got}
    return deck_of(region, m, f, metrics=lambda s, fam: pieces.get(s))


def test_a_sector_tables_median_row_shows_every_count_whole():
    v, slides = us_sector_deck()
    pages = [s for s in slides if s.title.startswith(f"{deck.SECTOR_TITLE}: US companies")]
    assert pages
    seen = 0
    for s in pages:
        table = next(b for b in s.blocks if b["kind"] == "table")
        assert table.get("compact")                                   # one line a company
        lay = deck.table_layout(table, table["box"][2], table["box"][3])
        assert len(lay["rows"]) == len(table["rows"])                 # no row left off its page
        for given, shown in zip(table["rows"], lay["rows"]):
            if str(given[0]).startswith("Median"):
                assert shown[1:] == given[1:] and not any("…" in str(c) for c in shown[1:]), shown
                seen += sum(1 for c in given[1:] if deck.counted_cell(c))
    assert seen >= 3
    every_rule("US sector figures", v, slides)


def test_a_counted_cell_gets_room_from_the_other_columns_and_wraps_when_there_is_none():
    head = ["Company", "SBC / revenue", "Capex / revenue", "Capex", "Inventory days", "R&D / revenue", "FCF margin", "Period"]
    med = ["Median (companies)", "0.7% (71 of 90)", "1.4% (4 of 5)", "$113 m (4 of 5)", "74 days (59 of 90)", "– (1 of 5)", "2.3% (69 of 90)", ""]
    rows = [[f"Storefront Holdings {i} Inc", "0.2%", "n/a", "n/a", "161 days", "n/a", "–", "FY Jan 2026"] for i in range(12)] + [med]
    table = {"head": head, "rows": rows, "widths": [2.6] + [1.05] * 6 + [1.15], "tight": True, "compact": True}
    lay = deck.table_layout(table, deck.CW, 99)
    assert lay["rows"][-1] == med                                                              # the live Retail table read "74 days (59…"
    assert all(deck._width(c, deck.BODY_MIN, True) <= w - 0.2 for c, w in zip(med[1:7], lay["widths"][1:7]))        # each on one line
    assert lay["rows"][0][-1] == "FY Jan 2026" and abs(sum(lay["widths"]) - deck.CW) < 1e-6    # no column that fitted is cut for it
    assert lay["heights"][-1] == lay["heights"][-2]
    # nine such columns: no room to give, so the cell wraps (a taller row), still never cut
    head9 = ["Company"] + [f"Figure {i}" for i in range(9)] + ["Period"]
    med9 = ["Median (companies)"] + ["12.34% (119 of 119)"] * 9 + [""]
    lay9 = deck.table_layout({"head": head9, "rows": [["Some Bank Ltd"] + ["1.2%"] * 9 + ["H1 FY27"]] * 12 + [med9], "widths": [2.3] + [0.95] * 9 + [1.35],
                              "tight": True, "compact": True}, deck.CW, 99)
    assert lay9["rows"][-1] == med9 and lay9["heights"][-1] > lay9["heights"][-2]
    assert deck.counted_cell("19.5% (4)") and deck.counted_cell("$113 m (4 of 5)") and not deck.counted_cell("Alpha (India) Ltd") \
        and not deck.counted_cell("Median (companies)") and not deck.counted_cell("(4 of 5)")


# ---------- 5. the appendix's layer names in full ----------
def long_layers():
    return build("IN", "IT services", [
        ("Large-scale outsourcing and managed services for global enterprises", "Runs clients' systems.",
         _rows("RUN", 5, "Runwell", "runs clients' IT systems under managed services contracts", "Computers - Software & Consulting", "managed_services")),
        ("Digital engineering and consulting projects for chosen industries", "Projects.",
         _rows("PRJ", 5, "Codecraft", "delivers IT projects and consulting to clients", "Computers - Software & Consulting", "project_services")),
        ("Software", "Sells software.", _rows("SAS", 5, "Cloudly", "sells subscriptions for its own SaaS software", "Software Products", "software")),
    ], [])


def test_the_appendix_says_in_full_each_layer_name_it_shows_cut():
    t = long_layers()
    v, slides = deck_of(t["region"], t["map"], t["facts"])
    pages = [s for s in slides if s.title.startswith("Every company's figures")]
    full = {x["layer"] for x in v["layers"]}
    keyed = 0
    for s in pages:
        table = next(b for b in s.blocks if b["kind"] == "table")
        col = table["head"].index("Layer")
        lay = deck.table_layout(table, table["box"][2], table["box"][3])
        assert len(lay["rows"]) == len(table["rows"])
        cut = {}
        for given, shown in zip(table["rows"], lay["rows"]):
            if shown[col] != given[col]:
                cut[shown[col]] = given[col]
        note = " ".join(p for b in s.blocks if b["kind"] == "text" for p in b["paras"])
        assert "Software" not in cut.values() and set(cut.values()) <= full
        for short, name in cut.items():
            assert f"{short} = {name}" in note, (short, note)      # a name shown shorter (or cut) is given in full under the table
            keyed += 1
        assert ("Layer names in full:" in note) == bool(cut)
        text = next(b for b in s.blocks if b["kind"] == "text")
        assert deck.note_h(note) <= text["box"][3] + 1e-6 and table["box"][1] + table["box"][3] <= text["box"][1] + 1e-6       # the key has its room
    # with the same release's layout work the Layer column takes the room the figure columns don't use, so here every name is shown whole;
    # a name that is ever shown otherwise carries its key (the loop above) and is tested in the next test
    assert keyed == 0
    every_rule("IT, long layer names", v, slides)


def test_layer_names_take_the_room_the_figure_columns_dont_use_and_one_still_cut_is_said_in_full():
    head = ["Company", "Layer", "Market value", "Revenue", "Growth", "EBITDA", "Net", "ROCE", "P/E", "P/B"]
    widths = [2.5, 1.9, 1.2, 1.15, 0.95, 0.95, 0.9, 0.85, 0.8, 0.8]
    rows = [["Runwell 0 Ltd", "Other IT service companies", "₹9.04 lakh cr", "₹2.67 lakh cr", "+4.6%", "27%", "18.5%", "63%", "17.6x", "7.6x"],
            ["Codecraft 0 Ltd", "Digital engineering and consulting projects for industries", "₹95,645 cr", "₹14,748 cr", "+23.5%", "19%", "12.6%", "34.4%", "52.9x", "11.1x"],
            ["Codecraft 1 Ltd", "Digital engineering and consulting projects for governments", "₹390 cr", "₹693 cr", "−4.5%", "−2.6%", "5.1%†", "13%", "17.5x", "1x"]]
    # with the layout work of the same release every column takes the room its neighbours don't use, so these names are shown whole
    for t in ({"head": head, "rows": rows, "widths": widths, "compact": True}, {"head": head, "rows": rows, "widths": widths, "compact": True, "full": [1]}):
        lay = deck.table_layout(t, deck.CW, 99)
        assert [r[1] for r in lay["rows"]] == [r[1] for r in rows] and lay["widths"][1] > widths[1] * deck.CW / sum(widths)
        assert all(r[2:] == g[2:] for r, g in zip(lay["rows"], rows))                                                    # no figure cut for it
    assert deck.short_names(head, rows, widths, 1) == ""                                                                 # nothing to explain
    # where the figure columns leave no room (each carries its count), a name not shown as written is given in full under the table
    tight = [r[:2] + [x + " (59 of 90)" for x in r[2:]] for r in rows]
    key = deck.short_names(head, tight, [2.5, 0.9, 1.2, 1.15, 0.95, 0.95, 0.9, 0.85, 0.8, 0.8], 1)
    assert key.startswith("Layer names in full: ") and key.endswith(" = Other IT service companies.")
    assert deck.short_names(head, rows[:1], widths, 1) == "" and deck.short_names(head, rows, widths, None) == ""
    assert deck.THEME_DECK_VERSION == 44
