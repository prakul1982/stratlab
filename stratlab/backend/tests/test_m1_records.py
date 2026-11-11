"""Lane m1-records (outside review of the live R32 decks): one set of records behind every count.
1. A materials or chemicals supplier to chip makers is never shown under an equipment layer (built from what live returned for US
   Semiconductors on 11 Nov 2026: tests/fixtures/themes_live/semis_us_r32.json).
Generic: the rules are the same for every theme and both markets."""
import json
import pathlib

from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_routes as T

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"


# ---------- 1. the live Semiconductors map ----------
def live_semis():
    """(the map as it stood before the split, the kept placement, the companies' stored words): the map's own layers with the companies the
    kept placement left there, every company the split moved (and the "Other" group's) back in the official group it came from."""
    d = json.loads((LIVE / "semis_us_r32.json").read_text())
    own, rest, models, conf, words = [], [], {}, {}, dict(d["about"])
    for v in d["layers"]:
        stay = []
        for c in v["companies"]:
            words.setdefault(c["ticker"], c["what"])
            row = {k: c[k] for k in ("ticker", "name", "what", "industry", "cap", "basis")}
            if c["model"]:
                models[c["ticker"]], conf[c["ticker"]] = c["model"], c["model_confidence"]
            (rest if v.get("official") or v.get("by_model") or c.get("moved") else stay).append(row)
        if not v.get("official") and not v.get("by_model"):
            own.append({"layer": v["layer"], "description": v["description"], "companies": stay})
    m = {"sector": "Semiconductors", "value_chain": own + [{"layer": "Semiconductors & Related Devices", "official": True, "basis": "industry",
                                                            "companies": rest}]}
    kept = {"assign": {c["ticker"]: {"layer": "", "by": "ai"} for c in rest}, "models": models, "model_confidence": conf}
    return d, m, kept, words


def placed_live():
    d, m, kept, words = live_semis()
    out, got = B.place_rest(m, "Semiconductors", lambda s: words.get(s) or "", ask=None, kept=kept)
    return d, out["value_chain"], got


def test_live_kept_the_materials_supplier_as_a_maker_under_equipment():
    """What live returned: Qnity ("a major provider of materials for the semiconductor manufacturing and electronics industries") with the
    model "manufacturing", moved by the split into "Semiconductor equipment" with eight more makers the map never placed there."""
    d = json.loads((LIVE / "semis_us_r32.json").read_text())
    eq = next(v for v in d["layers"] if v["layer"] == "Semiconductor equipment")
    q = next(c for c in eq["companies"] if c["ticker"] == "Q")
    assert q["model"] == "manufacturing" and q["moved"] and "provider of materials for the semiconductor" in q["what"]
    assert {c["ticker"] for c in eq["companies"] if c.get("moved")} >= {"Q", "QRVO", "IPGP", "VIAV", "NLST"}


def test_a_chip_materials_supplier_is_never_under_an_equipment_layer_on_the_live_map():
    d, vc, got = placed_live()
    where = {c["ticker"]: v["layer"] for v in vc for c in v["companies"]}
    row = {c["ticker"]: c for v in vc for c in v["companies"]}
    for s in ("Q", "ENTG"):                    # Qnity (kept as a maker) and Entegris (kept with no model at all): both supply materials
        assert got["models"][s] == "components" and row[s]["model"] == "components" and row[s]["model_confidence"] == "medium", s
        assert "equipment" not in where[s].lower(), (s, where[s])
    assert where["Q"] == where["ENTG"] and ("equipment" not in where["Q"].lower())
    assert where["Q"] in (C.MODELS["components"][1], "Other semiconductor companies")     # ingredient makers, or with the unplaced: never equipment
    # the equipment layer holds only the companies the map and its placement put there: none the split moved
    eq = next(v for v in vc if v["layer"] == "Semiconductor equipment")
    before = next(v for v in d["layers"] if v["layer"] == "Semiconductor equipment")
    assert {c["ticker"] for c in eq["companies"]} == {c["ticker"] for c in before["companies"] if not c.get("moved")}
    assert not any(c.get("moved") for c in eq["companies"])


def test_makers_the_map_placed_nowhere_stay_a_layer_of_their_own_beside_two_layers_of_makers():
    """The map keeps "Semiconductor equipment" and "Foundry and memory manufacturing" apart by what they make; how Qorvo or IPG Photonics
    earn doesn't say which of the two they belong to, so they are a layer named by how they earn, and each line says the three earn alike."""
    _, vc, _ = placed_live()
    made = next(v for v in vc if v["layer"] == C.MODELS["manufacturing"][1])
    assert made.get("by_model") and {"QRVO", "IPGP", "VIAV", "KOPN"} <= {c["ticker"] for c in made["companies"]}
    assert set(made["model"]["same_as"]) == {"Semiconductor equipment", "Foundry and memory manufacturing"}
    fab = next(v for v in vc if v["layer"] == "Fabless chip design")              # one layer has the designers' model: they still join it
    assert fab["model"]["id"] == "fabless" and not any(v["layer"] == C.MODELS["fabless"][1] for v in vc)


def test_a_chip_maker_whose_words_name_its_material_is_not_a_materials_supplier():
    d = json.loads((LIVE / "semis_us_r32.json").read_text())
    said = {c["ticker"]: c["what"] for v in d["layers"] for c in v["companies"]}
    assert "silicon carbide materials and devices" in said["WOLF"] and not C.chip_materials(said["WOLF"])        # live: Wolfspeed
    assert C.refine_model("manufacturing", C.model_evidence("Semiconductors & Related Devices", said["WOLF"])) == "manufacturing"
    assert C.chip_materials(said["ENTG"]) and C.chip_materials(d["about"]["Q"])
    assert not C.chip_materials("makes power chips on silicon carbide substrates for electric cars")
    _, vc, _ = placed_live()
    assert next(v["layer"] for v in vc for c in v["companies"] if c["ticker"] == "WOLF") == "Analog and power integrated device makers"


def test_no_materials_supplier_sits_under_an_equipment_layer_whatever_model_it_was_given():
    words = {"MAT": "supplies specialty chemicals and gases used in semiconductor manufacturing", "EQ0": "makes wafer fab equipment",
             "EQ1": "manufactures etch and deposition equipment", "EQ2": "builds lithography machines"}
    for given in ("manufacturing", "unknown", None):
        vc = [{"layer": "Chip equipment", "description": "Machines for fabs.",
               "companies": [{"ticker": s, "name": s, "what": w, "industry": "Semiconductors", "cap": 10} for s, w in words.items()]}]
        models = {"EQ0": "manufacturing", "EQ1": "manufacturing", "EQ2": "manufacturing", **({"MAT": given} if given else {})}
        ev = lambda s: C.model_evidence("Semiconductors", words[s])          # noqa: E731
        models, conf = B.refine_kept(models, {s: "high" for s in models}, ev, list(words))
        out = B.by_model(vc, models, "Semiconductors", confidence=conf, evidence_of=ev)
        where = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
        assert models["MAT"] == "components" and where["MAT"] != "Chip equipment", given
        assert where["EQ0"] == where["EQ1"] == where["EQ2"] == "Chip equipment"


def test_the_rules_version_moved_so_kept_checks_and_dives_are_worked_out_again_and_placements_carry():
    """The cause on live: the materials rule came in without a new rules version, so the check kept under the old one (and the theme library's
    read of it) was served as it stood. The version is part of every kept check's, library read's and dive's key."""
    assert B.RULES == 40 and T.PLACE_CARRY[34] == 33 and T.PLACE_CARRY[35] == 34 and T.PLACE_CARRY[36] == 35 and T.PLACE_CARRY[37] == 36 and T.PLACE_CARRY[38] == 37 and T.PLACE_CARRY[39] == 38   # lane s1-fit bumped RULES (updated on purpose); lane r2, lane r1, lane n2, q1 bumped RULES (updated on purpose)
    assert T.check_key("US", "Semiconductors", {"generated_at": 5})[-1] == B.RULES


# ---------- 2. one set of records behind every count of a layer ----------
import copy                                                                      # noqa: E402
import re                                                                        # noqa: E402

import pytest                                                                    # noqa: E402

from app import deck                                                             # noqa: E402
from app.intel import theme_data as D                                            # noqa: E402
from tests.synth_structures_r27class import banks_in, it_in, structures as class_structures      # noqa: E402
from tests.synth_structures_r29 import structures as broad_structures            # noqa: E402
from tests.test_r18_deck import deck_of                                          # noqa: E402
from tests.test_r25_deck import EVERY, IDS                                       # noqa: E402


def _row(sym, **kw):
    return {"symbol": sym, "name": f"{sym} Inc", "status": "core", "revenue": 100.0, "ebitda": 20.0, "net": 10.0, "roce": 12.0, **kw}


def live_shaped_layer():
    """The live "Semiconductor equipment" layer's shape: 17 listed, two whose way of earning isn't shown, one with no figure at all, one
    whose net margin is left out of its median."""
    rows = [_row(f"IN{i}") for i in range(13)] + [_row("PART", one_off=True)]
    rows += [_row("KLIC", model_out="unknown"), _row("ICHR", model_out="unknown"),
             {"symbol": "ATEYY", "name": "Advantest Corp", "status": "core", "revenue": None, "ebitda": None, "net": None, "roce": None}]
    return D.layer_block("Semiconductor equipment", rows, set())


def test_every_count_of_the_live_shaped_layer_comes_from_its_rows_records():
    b = live_shaped_layer()
    assert (b["n"], b["listed"]) == (14, 17)                      # live said 15 in one table: the company with no figure counted
    assert D.layer_counts(b) == {"listed": 17, "n": 14, "out": {"way of earning not shown": 2, "no revenue figure": 1}}
    assert [c["symbol"] for c in b["companies"] if not c["calc"]["in"]] == ["KLIC", "ICHR", "ATEYY"]
    assert b["stats"]["ebitda"]["n"] == 14 and b["stats"]["net"]["n"] == 13          # each median is of the 14
    row = D.chain_table([b])["rows"][0]
    assert (row["n"], row["listed"]) == (14, 17) and deck.companies_cell(row["n"], row["listed"]) == "14 of 17"
    cos = b["companies"]
    ins, outs = deck.layer_roll(b, cos)
    assert (len(ins), len(ins) + len(outs)) == (14, 17)
    assert deck.layer_head(b, cos, lambda x: f"${x} m").startswith("17 companies (14 in the layer's calculations)")
    assert deck.roll_line(ins, outs)[0].count("(14 of 17)") == 1
    assert deck.companies_cell(4, 4) == "4" and deck.companies_cell(4, None) == "4"


def test_a_company_with_a_figure_but_no_revenue_stays_in_and_one_with_none_is_out():
    assert D.calc_record({"revenue": None, "roe": 11.0}) == {"in": True, "why": ""}                 # a lender's return with no revenue stored
    assert D.calc_record({"revenue": None}) == {"in": False, "why": "no revenue figure"}
    assert D.calc_record({"revenue": 5, "status": "unverified", "model_out": "unknown"})["why"] == "not confirmed"
    assert D.calc_record({"revenue": 5, "model_out": "other"})["why"] == "other business"
    assert D.calc_record({"revenue": 5, "model_out": True})["why"] == "way of earning not shown"   # a dive kept before the reason was named
    assert set(D.CALC_WHY) == {"other business", "way of earning not shown", "not confirmed", "no revenue figure"} and deck.ROLL_WHY is D.CALC_WHY
    # a row of a dive kept before the record is read the same way
    assert not D.in_calc({"revenue": 5, "model_out": "unknown"}) and D.in_calc({"revenue": 5})
    assert D.in_calc({"revenue": None, "calc": {"in": True, "why": ""}})                         # the kept record is the one read


def _split_deck(t):
    t = copy.deepcopy(t)
    vc = B.by_model(t["map"]["value_chain"], t["models"], t["map"]["sector"], tags=t["tags"], confidence=t["confidence"])
    return deck_of(t["region"], {**t["map"], "value_chain": vc}, t["facts"])


def test_a_layer_with_companies_left_out_states_one_pair_on_every_page():
    v, slides = _split_deck(banks_in())
    said = deck.layer_count_statements(slides)["Retail and commercial lenders"]
    assert {p for p, _ in said} == {(5, 7)}                                       # the same two numbers wherever the layer is counted
    where = {w.split(" (")[0] for _, w in said}
    assert {"The value chain by layer", "Layers side by side", "Layer 1 · Retail and commercial lenders"} <= where, where
    chain = next(b for s in slides if s.title == "The value chain by layer" for b in s.blocks if b["kind"] == "table")
    row = next(r for r in chain["rows"] if r[0] == "Retail and commercial lenders")
    assert row[chain["head"].index("Companies")] == "5 of 7"
    notes = " ".join(p for s in slides if s.title == "The value chain by layer" for b in s.blocks if b["kind"] == "text" for p in b["paras"])
    assert deck.COMPANIES_NOTE in notes                                           # the two scopes are named where they differ
    layer = next(x for x in v["layers"] if x["layer"] == "Retail and commercial lenders")
    assert D.layer_counts(layer) == {"listed": 7, "n": 5, "out": {"way of earning not shown": 2}} and layer["n"] == 5
    assert deck.layer_count_flags(slides) == []
    assert next(x for x in slides[0].gate["items"] if x["id"] == "reconcile")["ok"]


def test_the_gate_fails_when_two_pages_state_different_totals_for_a_layer():
    """The live R32 Semiconductors deck: "15" in the value chain's table, "14 of 17" on the layer's page and in the appendix."""
    v, slides = _split_deck(banks_in())
    chain = next(b for s in slides if s.title == "The value chain by layer" for b in s.blocks if b["kind"] == "table")
    at = chain["head"].index("Companies")
    chain["rows"] = [[*r[:at], "6", *r[at + 1:]] if r[0] == "Retail and commercial lenders" else r for r in chain["rows"]]
    flags = deck.layer_count_flags(slides)
    assert [f["layer"] for f in flags] == ["Retail and commercial lenders"] and "6 on “The value chain by layer”" in flags[0]["text"]
    assert "5 of 7 on" in flags[0]["text"]
    gate = deck.publication_gate(slides, v)
    item = next(x for x in gate["items"] if x["id"] == "reconcile")
    assert not item["ok"] and any(d["text"].startswith("layer counts: Retail and commercial lenders") for d in gate["dropped"])
    # the scope named ("5 of 7") in every place is no failure, and neither is a layer whose every company is counted
    assert deck.layer_count_flags([s for s in slides if s.title != "The value chain by layer"]) == []


@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_no_synthetic_theme_states_two_counts_for_a_layer(name, v, slides):
    assert deck.layer_count_flags(slides) == [], name
    for layer in v["layers"]:
        got = D.layer_counts(layer)
        assert got["n"] == layer["n"] and got["listed"] == layer["listed"] == got["n"] + sum(got["out"].values()), (name, layer["layer"])
    for layer, said in deck.layer_count_statements(slides).items():
        assert len({p for p, _ in said}) == 1 and all(n <= listed for (n, listed), _ in said), (name, layer, said)


STRUCTURES = list(class_structures()) + list(broad_structures())


@pytest.mark.parametrize("name,theme", STRUCTURES, ids=[n for n, _ in STRUCTURES])
def test_no_split_structure_states_two_counts_for_a_layer(name, theme):
    v, slides = _split_deck(theme)
    assert deck.layer_count_flags(slides) == [], name
    assert next(x for x in slides[0].gate["items"] if x["id"] == "reconcile")["ok"], slides[0].gate["dropped"]
    stated = deck.layer_count_statements(slides)
    for layer in v["layers"]:
        got = D.layer_counts(layer)
        for (n, listed), where in stated.get(layer["layer"], []):
            assert (n, listed) == (got["n"], got["listed"]), (name, layer["layer"], where)


# ---------- 3. every company left out of a layer's calculations carries its reason, and the reason is the stored one ----------
def _left_out_named(slides, title):
    """{name: reason} as a layer's page and the appendix's roll say them (the reason before the names it is of)."""
    texts = [p for s in slides if s.title == title for b in s.blocks if b["kind"] == "text" for p in b["paras"] if "Left out (" in p]
    texts += [str(r[2]) for s in slides if s.title.startswith(deck.ROLL_TITLE) for b in s.blocks if b["kind"] == "table"
              for r in b["rows"] if title.endswith("· " + str(r[0]))]
    got = {}
    for t in texts:
        body = t.split("Left out (", 1)[-1].split("): ", 1)[-1] if "Left out (" in t else t.split(": ", 1)[-1]
        body = body.split(". Every one:")[0].rstrip(".")
        for part in re.split(r"; (?=(?:" + "|".join(D.CALC_WHY) + "): )", body):
            why, _, names = part.partition(": ")
            assert why in D.CALC_WHY, (why, t)
            for nm in names.split(", "):
                if not re.match(r"(?:and )?\d+ more$", nm.split(" and ")[-1] if " and " in nm and nm.split(" and ")[-1].endswith("more") else nm):
                    got[nm.split(" and ")[0] if nm.endswith("more") else nm] = why
    return got


def _reasons_carried(v, slides) -> int:
    """How many left-out companies the deck names with the reason their row keeps, on their own row or in a roll; fails on one without."""
    seen = 0
    for layer in [x for x in v["layers"] if any(not D.in_calc(c) for c in x["companies"])]:
        out = {deck._LEGAL.sub("", c["name"]).strip(" ,."): (c["name"], c["calc"]["why"]) for c in layer["companies"] if not c["calc"]["in"]}
        assert all(w in D.CALC_WHY for _, w in out.values())                                # kept on the row, one of the four reasons
        page = next((s for s in slides if deck._LAYER_PAGE.match(s.title or "") and s.title.endswith("· " + layer["layer"])), None)
        if page is None:               # a layer with no page of its own (one confirmed company, or the companies the map doesn't place)
            continue
        named = _left_out_named(slides, page.title)
        rows = [str(r[0]) for b in page.blocks if b["kind"] == "table" for r in b["rows"]]
        for nm, (full, why) in out.items():
            on_row = any(r == f"{full} ({deck.ROLL_TAG[why]})" for r in rows)
            assert on_row or named.get(nm) == why, (layer["layer"], nm, why, named, rows)
            seen += 1
    return seen


def test_every_left_out_company_of_the_it_layer_carries_its_stored_reason():
    """The live R32 IT deck: 4 of 13 in the large-outsourcing layer's calculations; nine names with their one reason after the last of them
    read as "TCS, Wipro, Tech Mahindra have none". Thirty listed, ten left out for three reasons: each is named under its reason."""
    from tests.test_r35_deck import it_theme
    region, m, f = it_theme()
    v, slides = deck_of(region, m, f)
    layer = next(x for x in v["layers"] if x["layer"] == "Large outsourcing")
    assert D.layer_counts(layer) == {"listed": 30, "n": 20, "out": {"other business": 7, "way of earning not shown": 2, "not confirmed": 1}}
    assert _reasons_carried(v, slides) == 10
    assert {p for p, _ in deck.layer_count_statements(slides)["Large outsourcing"]} == {(20, 30)}
    assert deck.layer_count_flags(slides) == []


def test_every_left_out_company_of_every_structure_carries_its_stored_reason():
    seen = sum(_reasons_carried(*_split_deck(theme)) for _, theme in STRUCTURES)
    assert seen >= 1


def test_the_roll_says_each_reason_before_the_companies_it_is_of():
    outs = [("Tata Consultancy Services", "way of earning not shown"), ("Wipro", "way of earning not shown"),
            ("Tech Mahindra", "way of earning not shown"), ("Black Box", "no revenue figure")]
    line, _ = deck.roll_line([("Infosys", ""), ("HCL Technologies", "")], outs)
    assert line == ("In the layer's calculations (2 of 6): Infosys, HCL Technologies. Left out (4): way of earning not shown: Tata Consultancy "
                    "Services, Wipro, Tech Mahindra; no revenue figure: Black Box.")


def test_a_company_with_no_figures_carries_its_reason_on_its_row():
    t = copy.deepcopy(banks_in())
    sym = t["map"]["value_chain"][0]["companies"][1]["ticker"]
    name = t["map"]["value_chain"][0]["companies"][1]["name"]
    f = t["facts"][sym]
    t["facts"][sym] = {k: x for k, x in f.items() if k in ("symbol", "name", "region", "unit", "industry", "market_cap", "cap")}
    v, slides = _split_deck(t)
    row = next((c for x in v["layers"] for c in x["companies"] if c["symbol"] == sym), None)
    if row is None or row["calc"]["in"]:
        pytest.skip("the synthetic store keeps a figure for it")
    assert row["calc"] == {"in": False, "why": "no revenue figure"}
    page = next(s for s in slides if any(str(r[0]).startswith(name) for b in s.blocks if b["kind"] == "table" for r in b["rows"])
                and deck._LAYER_PAGE.match(s.title or ""))
    cell = next(str(r[0]) for b in page.blocks if b["kind"] == "table" for r in b["rows"] if str(r[0]).startswith(name))
    notes = " ".join(p for b in page.blocks if b["kind"] == "text" for p in b["paras"])
    assert cell.endswith("(no figures)") and "(no figures): no revenue figure is stored" in notes or "no revenue figure: " in notes
    assert deck.layer_count_flags(slides) == []


def test_the_versions_moved_with_the_records():
    assert D.DIVE_TEXT == 9 and deck.THEME_DECK_VERSION == 49


# ---------- 4. only layers of one way of earning are ranked together ----------
from tests.synth_structures_r27class import build                               # noqa: E402

RANKING = re.compile(r"\b(?:highest|lowest|fastest|slowest)\b", re.I)


def _mk(prefix, n, name, what, ind, model):
    return [(f"{prefix}{i}", f"{name} {i} Ltd", what, ind, model, (), "high") for i in range(n)]


def realty_live_shape():
    """The live R32 Real estate deck's layers: developers, contractors, landlords and lenders, each with enough companies to be ranked."""
    return build("IN", "Real estate", [
        ("Residential developers", "Sell homes.", _mk("DEV", 8, "Homecrest", "develops and sells residential apartments", "Residential, Commercial Projects",
                                                     "property_development")),
        ("Engineering and construction contracts", "Build for clients.", _mk("EPC", 7, "Buildco", "builds buildings under EPC contracts for clients",
                                                                              "Civil Construction", "construction")),
        ("Office and mall landlords", "Rent.", _mk("LSE", 6, "Mallhold", "owns malls and office space and earns rent on leases", "Realty", "property")),
        ("Home loan lenders", "Lend.", _mk("HFC", 6, "Homeloan", "provides home loans to salaried buyers", "Housing Finance Company", "lending")),
    ], [])


def utilities_live_shape():
    """The live R32 Utilities deck's layers: generators, a regulated network, and two layers of makers (equipment, cables)."""
    return build("IN", "Utilities", [
        ("Thermal and hydro generation", "Generate.", _mk("GEN", 7, "Voltgen", "generates electricity at its thermal plants and sells power", "Power Generation",
                                                           "power_generation")),
        ("Integrated power distribution", "Distribute.", _mk("DIS", 6, "Gridco", "distributes electricity over its network at regulated tariffs",
                                                              "Power Distribution", "regulated_utility")),
        ("Power and grid equipment makers", "Equipment.", _mk("HEQ", 8, "Transfo", "manufactures transformers and switchgear in its plants",
                                                               "Heavy Electrical Equipment", "manufacturing")),
        ("Cables and wires makers", "Cables.", _mk("CAB", 6, "Wirewell", "manufactures power cables and wires in its plants", "Cables - Electricals",
                                                    "manufacturing")),
    ], [])


def _rankings(v, slides):
    """[(slide title, sentence, the layers it names)] for every sentence, headline or card line that names a highest, lowest, fastest or slowest."""
    fams = deck.layer_families(v)
    out = []
    for s in slides[1:]:
        texts = [s.subtitle or ""] if s.title != "Contents" else []
        for b in s.blocks:
            if b["kind"] == "cards":
                texts += [ln for it in b.get("items") or [] for ln in it.get("lines") or [] if isinstance(ln, str)]
            elif b["kind"] == "text":
                texts += [p for p in b.get("paras") or [] if isinstance(p, str)]
        for t in texts:
            t = deck.ranked_part(t)              # the layers a "Shown, not ranked" clause names are said to be outside the ranking
            if RANKING.search(t):
                out.append((s.title, t, deck.layers_named(t, fams)))
    return out


def _one_kind_only(name, v, slides):
    fams = deck.layer_families(v)
    for title, text, named in _rankings(v, slides):
        assert len({fams[n] for n in named}) <= 1, (name, title, text, {n: fams[n] for n in named})


def test_real_estate_ranks_no_developer_against_a_contractor_a_landlord_or_a_lender():
    v, slides = _split_deck(realty_live_shape())
    fams = deck.layer_families(v)
    assert len(set(fams.values())) == 4, fams                                     # four ways of earning, one layer each
    side = next(s for s in slides if s.title.startswith("Layers side by side"))
    assert not RANKING.search(side.subtitle or ""), side.subtitle                  # live: "highest median ROCE in Engineering and construction contracts"
    assert (v.get("chain") or {}).get("highest") is None
    assert [r for r in _rankings(v, slides) if r[2]] == []
    _one_kind_only("real estate", v, slides)
    assert next(x for x in slides[0].gate["items"] if x["id"] == "headline")["ok"]


def test_utilities_rank_only_the_layers_of_makers_against_each_other_and_say_so():
    v, slides = _split_deck(utilities_live_shape())
    fams = deck.layer_families(v)
    makers = {n for n, f in fams.items() if f == "making"}
    assert makers == {"Power and grid equipment makers", "Cables and wires makers"} and len(set(fams.values())) == 3
    side = next(s for s in slides if s.title.startswith("Layers side by side"))
    named = deck.layers_named(side.subtitle, fams)
    assert named and set(named) <= makers, side.subtitle                           # never a generator or a network beside a maker
    assert "among the 2 layers of one kind of business" in side.subtitle
    _one_kind_only("utilities", v, slides)


def test_the_one_rule_is_behind_the_side_by_side_headline():
    rows = [{"layer": "A", "roce": 10.0, "n": 8, "k": 8, "model": {"family": "making"}, "basis": "full", "intensity": 1.0},
            {"layer": "B", "roce": 30.0, "n": 8, "k": 8, "model": {"family": "generation"}, "basis": "full", "intensity": 1.0},
            {"layer": "C", "roce": 20.0, "n": 8, "k": 8, "model": {"family": "making"}, "basis": "full", "intensity": 1.2}]
    kw = dict(of=lambda r: r["n"], model=lambda r: r["model"], basis=lambda r: r["basis"], intensity=lambda r: r["intensity"])
    top, among = D.rank_top(rows, lambda r: r["roce"], lambda r: r["k"], **kw)
    assert top["layer"] == "C" and [r["layer"] for r in among] == ["A", "C"]      # B earns another way: not ranked, though its figure is highest
    assert D.rank_top(rows[:2], lambda r: r["roce"], lambda r: r["k"], **kw) is None           # one of each family: nothing to rank
    few = [{**r, "k": 4} for r in rows]
    assert D.rank_top(few, lambda r: r["roce"], lambda r: r["k"], **kw) is None                 # under the headline floor of 5
    far = [rows[0], {**rows[2], "intensity": 9.0}]
    assert D.rank_top(far, lambda r: r["roce"], lambda r: r["k"], **kw) is None                 # unlike in asset intensity
    assert D.rank_pair(rows, lambda r: r["roce"], lambda r: r["k"], **kw) == (rows[2], rows[0])  # the pair's rule is the same one


def test_the_gate_drops_a_ranking_across_kinds_of_business():
    fams = {"Residential developers": "development", "Engineering and construction contracts": "construction", "Office landlords": "property",
            "Plain layer": ""}
    bad = "Median ROCE is highest in Engineering and construction contracts (10.7%) and lowest in Residential developers (7.7%)"
    assert "different kinds of business" in deck.family_flag(bad, fams)
    assert deck.family_flag("highest median ROCE in Engineering and construction contracts (10.7%)", fams) is None        # one layer named
    assert deck.family_flag("Residential developers and Office landlords both report in March", fams) is None           # no ranking
    assert deck.family_flag("highest in Plain layer, lowest in Office landlords", fams)                                 # no family beside one
    v, slides = _split_deck(realty_live_shape())
    side = next(s for s in slides if s.title.startswith("Layers side by side"))
    side.subtitle = ("Medians by layer: highest median ROCE in Engineering and construction contracts (10.7%); fastest median revenue growth in "
                     "Residential developers (+25%)")
    gate = deck.publication_gate(slides, v)
    assert not next(x for x in gate["items"] if x["id"] == "headline")["ok"]
    assert not RANKING.search(side.subtitle or "")                                 # dropped, never shipped
    assert any("different kinds of business" in d["why"] for d in gate["dropped"])


@pytest.mark.parametrize("name,theme", STRUCTURES, ids=[n for n, _ in STRUCTURES])
def test_no_structure_ranks_layers_of_different_kinds_of_business(name, theme):
    v, slides = _split_deck(theme)
    _one_kind_only(name, v, slides)
    assert not [d for d in slides[0].gate["dropped"] if "different kinds of business" in d.get("why", "")]


@pytest.mark.parametrize("name,v,slides", EVERY, ids=IDS)
def test_no_synthetic_theme_ranks_layers_of_different_kinds_of_business(name, v, slides):
    _one_kind_only(name, v, slides)


def test_a_layer_said_to_be_shown_not_ranked_never_counts_as_ranked():
    fams = {"Cables and wires makers": "making", "Power and grid equipment makers": "making", "Thermal and hydro generation": "generation"}
    ok = ("Among the 2 layers with at least 5 companies with the figure and one kind of business, median EBITDA margin is highest in Cables and "
          "wires makers (26.3%) and lowest in Power and grid equipment makers (23.8%). Shown, not ranked: Thermal and hydro generation (20.0%), "
          "a different kind of business.")
    assert deck.family_flag(ok, fams) is None
    bad = "Median EBITDA margin is highest in Thermal and hydro generation (20%) and lowest in Cables and wires makers (18%)."
    assert deck.family_flag(bad, fams)
    assert "Thermal" not in deck.ranked_part(ok) and deck.ranked_part(bad) == bad
