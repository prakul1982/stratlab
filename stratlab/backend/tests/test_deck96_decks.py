"""deck96 (owner, 26 Nov: "ok go ahead"): every live theme deck checked for the classes of problem the Alcoholic beverages deck had
(Releases 90-92), each one found fixed as a rule for every theme."""
import copy
import functools

from app import deck
from tests.alcobev_fixture import alco_view


@functools.lru_cache(maxsize=None)
def _alco():
    return alco_view()


def _view():
    return copy.deepcopy(_alco())


def _texts(slides, title):
    out = []
    for s in slides:
        if s.title.startswith(title):
            for b in s.blocks:
                for r in b.get("rows") or []:
                    out += [deck._cell_text(x) for x in ([] if isinstance(r, dict) else r)]
    return out


def test_a_whole_company_mark_is_said_once_in_size_and_shape():
    # the live Capital goods deck: "Larsen & Toubro Limited (whole company) (whole company)" in Size and shape
    v = _view()
    big = v["sections"]["size"]["biggest"]
    big[0]["whole"] = True
    v["company_wide"] = sorted(set(v.get("company_wide") or []) | {big[0]["symbol"]})
    slides, _ = deck.theme_plan(v)
    cells = _texts(slides, "Size and shape")
    assert any("(whole company)" in c for c in cells), cells[:6]
    assert not any("(whole company) (whole company)" in c for c in cells), cells[:6]


def _paras(s):
    return [str(p) for b in s.blocks if b["kind"] == "text" for p in b.get("paras") or []]


def test_a_layer_page_points_only_at_what_the_page_it_names_shows():
    # the live decks: "What the marks on its rows mean, and who is in its figures: p. 28", where p. 28 (Method and sources) has the key to the
    # marks and no layer's list of who is in its figures
    slides, _ = deck.theme_plan(_view())
    layers = [s for s in slides if s.title.startswith("Layer ")]
    assert layers
    said = " ".join(p for s in layers for p in _paras(s))
    assert "who is in its figures: p." not in said
    assert deck.MARKS_POINTER in said and deck.REASON_WHERE in said
    method = next(s for s in slides if s.title.startswith(deck.METHOD_TITLE))
    flat = " ".join(" ".join(deck._cell_text(x) for x in r) for b in method.blocks for r in b.get("rows") or [] if not isinstance(r, dict))
    assert "A word in brackets after a company's" in flat and "on the theme's page in StratLab" in flat


def test_a_median_row_with_no_median_is_no_row():
    # the live Airlines and Hotels decks: "Median (companies)  –  –  –" under "Other airlines and travel companies", fewer than 3 companies with
    # each figure
    v = _view()
    lay = next(b for b in v["layers"] if len(b.get("companies") or []) >= 4)
    for k, st in list((lay.get("stats") or {}).items()):
        if isinstance(st, dict) and st.get("n"):
            lay["stats"][k] = {**st, "n": 2}
    slides, _ = deck.theme_plan(v)
    page = next(s for s in slides if s.title.startswith("Layer ") and s.title.endswith(lay["layer"]))
    rows = [r for b in page.blocks if b["kind"] == "table" for r in b.get("rows") or [] if not isinstance(r, dict)]
    assert rows
    meds = [r for r in rows if deck._cell_text(r[0]).startswith("Median")]
    assert not meds, meds
    assert deck.no_median(["Median (companies)", "–", "– (2 of 4)", ""]) and not deck.no_median(["Median of 3 companies", "14.2%", "–"])


def test_the_findings_never_lead_with_a_layer_of_adjacent_participants():
    # the live Fertilizers and agrochemicals deck: "Specialty and fine chemicals makers brings in the most revenue of the map's own layers",
    # a layer of adjacent participants (another kind of business than the theme's)
    v = _view()
    own = [b for b in v["layers"] if not b.get("official") and b.get("revenue")]
    big = max(own, key=lambda b: b["revenue"])
    slides, _ = deck.theme_plan(copy.deepcopy(v))
    # (changed on purpose, deck101 …: the sentence reads "The most revenue of the map's own layers is in <layer>: <amount>", whatever the
    # layer's name, "Steel mills brings in" no more)
    assert any(f"most revenue of the map's own layers is in {big['layer']}:" in x for x in deck.findings_lines(slides))
    big["adjacent"] = {"kind": "glass bottle makers", "theme": "Alcoholic beverages"}
    slides, _ = deck.theme_plan(v)
    lines = deck.findings_lines(slides)
    assert not any(f"layers is in {big['layer']}:" in x for x in lines), lines          # (changed on purpose, deck101 …)
    assert any("most revenue of the map's own layers is in " in x for x in lines), lines          # (changed on purpose, deck101 …)


def test_a_company_with_no_figures_is_listed_after_every_company_with_figures():
    # the live Airlines deck: "Spicejet (no figures)  –  –  –  –", the second row of its layer's table, between companies with figures
    v = _view()
    lay = next(b for b in v["layers"] if len(b.get("companies") or []) >= 5 and not b.get("official"))
    cos = sorted(lay["companies"], key=lambda c: -(c.get("cap") or 0))
    bare = cos[1]
    for k in list(bare):
        if k not in ("symbol", "name", "cap", "status", "evidence", "theme", "what", "industry", "official_industry", "year"):
            bare.pop(k, None)
    bare["year"] = None
    bare.pop("calc", None)
    slides, _ = deck.theme_plan(v)
    page = next(s for s in slides if s.title.startswith("Layer ") and s.title.endswith(lay["layer"]))
    names = [deck._cell_text(r[0]) for b in page.blocks if b["kind"] == "table" for r in b.get("rows") or [] if not isinstance(r, dict)]
    names = [n for n in names if not n.startswith(("Median", "Range", "Together"))]
    at = next(i for i, n in enumerate(names) if n.startswith(deck.clean_name(bare["name"])))
    assert "(no figures)" in names[at], names
    assert all("(no figures)" in n or "(not confirmed)" in n or "(not checked yet)" in n for n in names[at:]), names


def test_a_recreational_boat_maker_is_not_confirmed_in_aerospace_and_defense_on_the_warship_builders_industry():
    # the live Aerospace and defense deck: MasterCraft, Malibu Boats, Twin Vee PowerCats, Vision Marine and NextBoat in its "Other" group,
    # members on the SEC's "Ship & Boat Building & Repairing", the warship builders' industry
    from app.intel import theme_data as D
    boat = {"ticker": "MCFT", "base": True, "basis": "industry", "industry": "Ship & Boat Building & Repairing",
            "what": "MasterCraft designs, manufactures and markets recreational performance sport boats"}
    navy = {**boat, "ticker": "HII", "what": "America's largest military shipbuilding company, building aircraft carriers and submarines for the U.S. Navy"}
    assert D.not_of_kind("US", "Aerospace and defense", boat, "")
    assert not D.not_of_kind("US", "Aerospace and defense", navy, "")
    assert not D.not_of_kind("US", "Aerospace and defense", {**boat, "what": ""}, "")          # no words read: never removed
    assert not D.not_of_kind("US", "Aerospace and defense", {**boat, "basis": "list"}, "")     # the theme's own list
    assert not D.not_of_kind("US", "Shipbuilding", boat, "") and not D.not_of_kind("IN", "Defence", boat, "")
    # its state: its own words describe other work, listed, in no figure
    assert D.evidence_state(boat, set(), "", status="unverified") == "not_confirmed"


def test_the_companies_table_names_the_largest_core_member_never_an_adjacent_participant():
    # the live Automotive deck: "Bajaj Finance Limited is the largest at ₹6.83 lakh cr" over every company's figures, a lender, an adjacent
    # participant of the theme
    v = _view()
    lay = max((b for b in v["layers"] if not b.get("official")), key=lambda b: max(c.get("cap") or 0 for c in b["companies"]))
    lay["adjacent"] = {"kind": "lenders and financiers", "theme": "own business (Alcoholic beverages)"}
    adj = {c["symbol"] for c in lay["companies"]}
    slides, _ = deck.theme_plan(v)
    heads = [s.subtitle for s in slides if s.title.startswith("Every company's figures")]
    assert heads
    rows = [c for b in v["layers"] for c in b["companies"] if c.get("cap") and c["symbol"] not in adj and c.get("status") != "unverified"]
    top = max(rows, key=lambda c: c["cap"])
    assert all(f"{top['name']} is the largest core member at" in h for h in heads), heads[0]


def test_the_figures_list_on_its_own_page_takes_one_page_two_figures_a_row():
    # 19 of the 49 live decks: "Method and sources (2 of 3)" and "(3 of 3)", eight figures a page, most of each page empty
    long = " ".join(["The AI's layers and additions can be wrong and each company's place and how it was checked are on the theme's page in StratLab."] * 9)
    cards = [{"title": "How the companies got in", "lines": ["Official industries: Hotels & Resorts · Airline. The base is every listed company the "
                                                             "exchange's own industry classification puts in these industries."]},
             {"title": "Who is in it", "lines": ["99 companies in all, each in one layer."]},
             {"title": "Reading the figures", "lines": [deck.MARKS_LINE]},
             {"title": "Not in this deck, and what the AI wrote", "lines": [long + " " + deck.THEME_DISCLAIMER]}]
    built = deck.Slide("How the figures are built")
    figs = [[f"Figure number {i}", "Passenger revenue per revenue passenger kilometre, as the airline states it for the quarter."] for i in range(16)]
    built.add("table", (0, 0, 10, 5), head=["Figure", "How it is built"], rows=figs, widths=[1.5, 5.0])
    pages = deck._method_page([], cards, [built], {"region": "IN"}, "26 Nov 2026", "")
    assert len(pages) == 2, [p.title for p in pages]
    said = [x for p in pages[1:] for b in p.blocks if b["kind"] == "table" for r in b["rows"] for x in r[::2] if x]
    assert said == [f[0] for f in figs]                      # every figure, in its order, none cut
