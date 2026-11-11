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
    assert B.RULES == 34 and T.PLACE_CARRY[34] == 33
    assert T.check_key("US", "Semiconductors", {"generated_at": 5})[-1] == B.RULES
