"""r65e (R65): the last flags of the live R64 decks (Fertilizers' "Specialty chemicals" over lines that say no chemical, C.H. Robinson's
line read as no word of "Asset-light brokers and agents", Biotech's informative share falling 459 -> 400 of 821), and what a read of the 34
decks found, each fix generic (India and US), each test failing before the fix and passing after it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.intel import theme_base as B


def _rows(vc):
    return {c["ticker"]: (v["layer"], c) for v in vc for c in v.get("companies") or []}


def _other(label: str, n: int = 3) -> dict:
    return {"layer": label, "description": "", "official": True, "basis": "rest",
            "companies": [{"ticker": f"R{i}", "name": f"Rest {i} Ltd", "industry": "Fertilizers", "placed": "words"} for i in range(n)]}


# ---------- 1. Fertilizers p.23: a layer of one official industry none of whose companies' lines say its name ----------
def _agro(words: dict):
    grp = {"layer": "Specialty chemicals", "description": "", "industry_group": True,
           "companies": [{"ticker": s, "name": n, "industry": "Specialty Chemicals", "placed": "ai", "model": "manufacturing"}
                         for s, n in (("FOS", "Foseco India Ltd"), ("DDV", "DDev Plastiks Industries Ltd"))]}
    urea = {"layer": "Urea producers", "description": "Makers of urea and nitrogen fertilisers.",
            "companies": [{"ticker": f"U{i}", "name": f"Urea {i} Ltd", "industry": "Fertilizers"} for i in range(3)]}
    ev = {**words, **{f"U{i}": "Urea Ltd makes urea and nitrogen fertilisers at its plants." for i in range(3)}}
    vc = [urea, grp, _other("Other fertilizers and agrochemical companies")]
    return B.listed_out(vc, lambda s: ev.get(s, ""), "Fertilizers and agrochemicals")


def test_1_a_layer_of_one_industry_whose_companies_lines_say_none_of_it_is_not_made():
    """Fails before: the live R64 Fertilizers deck printed "Specialty chemicals" (its companies filed under the official industry Specialty
    Chemicals) over Foseco, "products used in the metallurgical industry", and DDev Plastiks, "Plastic Compounds": none of its companies'
    lines says chemical (deck_check "layer words"). The industry put them together, nothing they say of their work does: they are listed in
    the theme's "Other" group, still in the theme, with the reason."""
    vc, rows = _agro({"FOS": "Incorporated in 1958, Foseco India Limited is engaged in the manufacture of products used in the metallurgical "
                             "industry which are in the nature of additives and consumables that improve the performance of castings.",
                      "DDV": "Incorporated in 2020, DDev Plastiks Industries Ltd manufactures Plastic Compounds for the wires and cables industry."})
    got = _rows(vc)
    for s in ("FOS", "DDV"):
        assert got[s][0] == "Other fertilizers and agrochemical companies", got[s]
        assert "none of their own words says a word of its name" in got[s][1]["refit"]["why"], got[s][1]
    assert not any(v["layer"] == "Specialty chemicals" for v in vc)
    assert {r["ticker"] for r in rows} >= {"FOS", "DDV"}


def test_1b_a_layer_of_one_industry_one_of_whose_companies_says_its_name_stays():
    # (guard) one line saying it keeps the layer and both its companies
    vc, _ = _agro({"FOS": "Foseco India Limited manufactures specialty chemicals and additives used by foundries.",
                   "DDV": "DDev Plastiks Industries Ltd manufactures Plastic Compounds for the wires and cables industry."})
    got = _rows(vc)
    assert got["FOS"][0] == "Specialty chemicals" and got["DDV"][0] == "Specialty chemicals", got


# ---------- 2. Railroads and trucking deck_diff: C.H. Robinson's line and "Asset-light brokers and agents" ----------
def test_2_a_logistics_provider_says_the_concept_of_asset_light_freight_brokers():
    """Fails before: the live R64 Railroads and trucking deck printed C.H. Robinson's line "C.H. Robinson Worldwide, Inc. is one of the largest
    global logistics providers in the world" in "Asset-light brokers and agents" and deck_diff failed it ("says no word of the layer's
    name"). Arranging others' carriers for shippers is the layer's concept (the layer's own description: "They match shippers with
    third-party carriers"): a logistics provider, third-party logistics, freight brokerage say it."""
    import release_gate as G
    line = "C.H. Robinson Worldwide, Inc. is one of the largest global logistics providers in the world"
    assert G.shares("Asset-light brokers and agents", line), line
    assert B.layer_line("", line + ", with revenues of $16.2 billion in 2025.", "C. H. Robinson Worldwide, Inc.",
                        "Asset-light brokers and agents").startswith("C.H. Robinson Worldwide, Inc. is one of the largest global logistics")
    assert B.concept_said("Freight brokers", "Landstar has the ability to arrange for individual shipments of freight")


def test_2b_the_freight_brokerage_concept_is_no_other_layer_s():
    # (guard) a carrier hauling its own loads says nothing of it; an insurance broker's layer never reads logistics words; the concept's
    # words are read only under a name of freight, trucking, logistics or asset-light brokers or agents
    assert not B.concept_said("Asset-light brokers and agents", "We own tractors and trailers and haul full loads for shippers.")
    assert not B.concept_said("Insurance brokers and agents", "one of the largest global logistics providers in the world")
    assert not B.concept_said("Asset-based truckload carriers", "one of the largest global logistics providers in the world")


# ---------- 3. Biotech: members whose words say the layer sent to "Other" for a figure they don't have ----------
def _bio():
    say = "We are a clinical-stage biopharmaceutical company developing therapies for patients with cancer."
    co = lambda t, cap, **k: {"ticker": t, "name": f"{t} Therapeutics Inc.", "industry": "Biological Products", "placed": "words",      # noqa: E731
                              "cap": cap, "model": "manufacturing", **k}
    big = {"layer": "Large commercial biotechs", "description": "Commercial biotechs with approved medicines.",
           "companies": [co(f"L{i}", 1e5 - i) for i in range(B.FIGURES_MAX)]}
    cos = ([co("E", 3e5)] + [co(f"C{i}", 50 - i) for i in range(4)] + [co("Q", 40)] + [co(f"F{i}", 30 - i) for i in range(2)])
    cos[1].update({"model": "", "model_out": "unknown", "out_why": "no_model"})      # C0: its words state no way of earning
    lay = {"layer": "Specialty and clinical-stage biotechs", "description": "Clinical-stage and specialty biotechs.", "companies": cos}
    words = {**{t: f"{t} {say}" for t in ("E", "C0", "C1", "C2", "C3")},
             "Q": "Quiet Holdings Inc. is a shell company with no operations of its own.",
             **{f"F{i}": "We are a specialty biopharmaceutical company selling medicines for rare diseases." for i in range(2)},
             **{f"L{i}": "Large Inc. sells approved medicines worldwide." for i in range(B.FIGURES_MAX)}}
    # the window read (E among the largest: its page read, a P/B and a return on equity and no revenue), the members beyond it never read
    figs = {**{f"L{i}": {"revenue": 9000.0} for i in range(B.FIGURES_MAX)}, **{f"F{i}": {"revenue": 300.0} for i in range(2)},
            "E": {"read": True}}
    rest = _other("Other biotech companies")
    return B.listed_out([big, lay, rest], lambda s: words.get(s, ""), "Biotech", {}, lambda s: figs.get(s) or {}, {})


def test_3_a_member_whose_words_say_its_layer_is_never_sent_out_for_a_figure_not_read():
    """Fails before: 69 members of the live R64 Biotech deck's "Specialty and clinical-stage biotechs" went to "Other" as "listed ... with no
    figure stored: not counted as the layer's until it is read" (400 of 821 in informative layers against 459 on R63): members beyond the
    figures' window, "a clinical-stage biopharmaceutical company", whose words state no way of earning (C0), and Erasca, Immunovant and
    Kodiak, among the largest, whose pages were read and hold no revenue, as a company before its first sale has none (E)."""
    vc, rows = _bio()
    got = _rows(vc)
    for t in ("E", "C0", "C1", "C2", "C3"):
        assert got[t][0] == "Specialty and clinical-stage biotechs", (t, got[t], rows)
    assert got["C0"][1].get("fig_unread") and not got["E"][1].get("fig_unread")     # (the window never adds one not read to fill a layer)


def test_3b_a_member_with_no_figure_whose_words_say_nothing_of_its_layer_still_goes():
    # (updated on purpose, e81: the owner's review of the R79 decks, P0 "business classification apart from financial-data availability": no
    # stored figure moves a member out of its layer; it stays, marked out of the layer's calculations, and no reason says "no figure stored")
    vc, rows = _bio()
    got = _rows(vc)
    assert got["Q"][0] == "Specialty and clinical-stage biotechs", got["Q"]
    assert got["Q"][1].get("fig_unread") and not any("no figure stored" in str(r.get("why")) for r in rows)


def test_3c_a_page_read_with_no_revenue_is_a_page_read(monkeypatch):
    """Fails before: the placement's stored figures (theme_routes._figures_reader) were {} for a page whose figures hold a P/B and a return
    on equity and no revenue, so listed_out read Erasca's read page as "no figure stored"."""
    from app.intel import theme_routes as TR
    from app.intel import theme_data as TD
    rows = {"ERAS": {"revenue": None, "ebitda": None, "net": None, "pb": 2.1, "roe": -43.3}, "NONE": {"revenue": None, "ebitda": None},
            "AMGN": {"revenue": 33000.0, "ebitda": 40.0, "net": 15.0}}
    monkeypatch.setattr(TR.computed, "get", lambda kind, key: {"value": {"k": key[1]}})
    monkeypatch.setattr(TD, "company_row", lambda region, sym, f: rows.get(sym))
    fig = TR._figures_reader("US")
    assert fig("ERAS") == {"read": True} and fig("NONE") == {} and fig("AMGN")["revenue"] == 33000.0


# ---------- 4. a read of the 34 decks ----------
def test_4a_the_growth_question_asks_what_the_layers_companies_sell_never_what_banks_make(monkeypatch):
    """Fails before: 17 live R64 decks, Regional banks, P&C insurance, REITs, NBFCs, Software and Utilities among them, asked "Is the
    difference in demand, in prices, or in the products each layer's companies make?" of layers of banks, insurers and landlords, which
    make no products. The question asks what each layer's companies offer, whatever their business ("sell" reads as advice: test_r17)."""
    from app import deck as D
    from app.intel import theme_data as TD
    lay = lambda name, g: {"layer": name, "model": {"id": "lending"}, "companies": [   # noqa: E731
        {"name": f"{name} {i}", "symbol": f"{name[:2]}{i}", "sales_1y": g + i, "calc": {"in": True}} for i in range(6)]}
    shown = [lay("Commercial and business banks", 12.0), lay("Foreign banking groups", 4.0)]
    # (the two layers ranked as comparable: the ranking's own rules are other tests')
    monkeypatch.setattr(TD, "rank_pair", lambda gm, *a, **k: (max(gm, key=lambda t: t[1]), min(gm, key=lambda t: t[1])))
    qs = D.economics_questions({"chain": {}}, shown, {}, D._pc)
    q = next(x for x in qs if x.startswith("Median revenue growth in the latest year"))
    assert q.endswith("Is the difference in demand, in prices, or in what each layer's companies offer?"), q
    assert not any("companies make?" in x for x in qs)


def test_4b_a_coverage_fall_says_why_for_the_members_past_the_figures_window():
    """Fails before: the live R64 Biotech deck's coverage flag, "400 of 821 ... against 459 of 821 ...: 7 points fewer ... Why: moved to
    “Other” by what its layer is ...: 4; no longer in the theme: 1", said 5 companies of a fall of 59: fall_why read only the previous
    figures' window, and the companies sent to "Other" were past it. The snapshot keeps every member ("rest"); each is counted."""
    from app.intel import theme_changes as TCH
    snap = {"layers": ["Specialty biotechs", "Other biotech companies"], "cos": {"A": ["A", 0], "B": ["B", 0]},
            "rest": {"C": ["C", 0], "D": ["D", 0], "E": ["E", 1]}, "rest_layers": ["Specialty biotechs", "Other biotech companies"]}
    dive = {"layers": [{"layer": "Specialty biotechs", "companies": [{"symbol": "A"}]},
                       {"layer": "Other biotech companies", "companies": [{"symbol": "B", "refit": {"from": "Specialty biotechs", "why": "x"}}]}]}
    everyone = {"A": {"layer": "Specialty biotechs"}, "B": {"layer": "Other biotech companies", "refit": {"from": "Specialty biotechs"}},
                "C": {"layer": "Other biotech companies", "refit": {"from": "Specialty biotechs", "why": "x"}},
                "D": {"layer": "Other biotech companies"}, "E": {"layer": "Other biotech companies"}}
    why = TCH.fall_why(snap, dive, everyone)
    assert why.get("moved to “Other” by what its layer is (its own words and official industry don't say it)") == 2, why
    assert why.get("fit none of this version's layers") == 1 and "no longer in the theme" not in why, why
    assert not any(k.startswith("new to the theme") for k in why), why
    # (a snapshot that keeps no members past its window is read as before: none of them new to the theme)
    old = {k: v for k, v in snap.items() if k not in ("rest", "rest_layers")}
    assert TCH.fall_why(old, dive, everyone) == {"moved to “Other” by what its layer is (its own words and official industry don't say it)": 1}


def test_1c_firearms_makers_say_a_layer_of_ordnance():
    """Fails before: on the R65 replay of the US Aerospace and defense input the rule of test 1 would have folded "Ordnance and accessories"
    (its official industry) over Sturm Ruger and Smith & Wesson, makers of firearms: ordnance is firearms and their ammunition, so their
    lines say it and the layer stays."""
    words = {"RGR": "Sturm, Ruger & Company, Inc. is principally engaged in the design, manufacture, and sale of firearms to domestic customers.",
             "SWBI": "We are one of the world's leading manufacturers and designers of firearms."}
    grp = {"layer": "Ordnance and accessories", "description": "", "industry_group": True,
           "companies": [{"ticker": s, "name": n, "industry": "Ordnance And Accessories, (No Vehicles/Guided Missiles)", "placed": "ai"}
                         for s, n in (("RGR", "Sturm Ruger & Co Inc"), ("SWBI", "Smith & Wesson Brands, Inc."))]}
    vc, _ = B.listed_out([grp, _other("Other aerospace and defense companies")], lambda s: words.get(s, ""), "Aerospace and defense")
    got = _rows(vc)
    assert got["RGR"][0] == "Ordnance and accessories" and got["SWBI"][0] == "Ordnance and accessories", got
    assert B.concept_said("Ordnance and accessories", words["SWBI"])
    assert not B.concept_said("Ordnance and accessories", "We build commercial aircraft and jet engines.")
