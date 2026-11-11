"""Golden layer check on the Release 37 live maps (R38 lane s1-fit, the outside review of the live R37 decks: "Off-price, dollar and
value-format retailers" held 43 companies, 34 moved there by the split: lululemon, Coupang, Wayfair, Chewy, Macy's, pawnbrokers, a propane
distributor; "Semiconductor equipment" held Micron, Intel, SK Hynix, lasers and LED makers). Every company of the 14 benchmark themes'
live maps (11 Nov 2026, Release 37: tests/fixtures/themes_live/layers_r38.json, 1,632 companies, India and US) is placed again from the
map's kept answer (theme_base.place_rest, no AI) and its layer, or "Other", is compared with the one the Release 37 rules (RULES 38) gave
the same map and words ("e"), with the moves below approved on purpose, each with its reason on the company's own words. A rule change
that moves any other company fails here; such a change is made on purpose by editing APPROVED (with its reason), never by loosening the
check. The halves of a layer split by market value count as one layer, and the replay joins them again before placing (the smaller half's
companies the map placed stay in it, as the map placed them). The live split itself (by_model on the live models as the map shows them) is
checked too: no chip maker joins the equipment layer, no online seller or department store the off-price layer."""
import json
import pathlib
import re

from app.intel import theme_base as B
from app.intel.theme_check import model_evidence

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live"
LAYERS = json.loads((LIVE / "layers_r38.json").read_text())
_HALF = re.compile(r"( \((?:larger|smaller)\))+$")

_OTHER = ("no layer of its family holds its industry, the largest (\"Off-price, dollar and value-format retailers\") shares none of its "
          "words and no other layer shares two: stays in Other, never the largest by default")
_KIN = ("an auto parts maker the answer read as a maker of its own products: \"Tyre manufacturers\" (the largest makers' layer) holds none "
        "of its industry; the component suppliers' layer is all of it (listed there, left out of its figures as another way of earning)")

# "theme:symbol" -> (its layer now, why it moved)
APPROVED = {
    "auto:ASAHIINDIA": ("Component and systems suppliers", "automotive and architectural glass: " + _KIN),
    "auto:BOSCHLTD": ("Component and systems suppliers", "fuel injection systems and automotive aftermarket products: " + _KIN),
    "auto:STUDDS": ("Component and systems suppliers", "two-wheeler helmets and accessories, filed as auto components: " + _KIN),
    "auto:VELJAN": ("Component and systems suppliers", "hydraulic pumps, motors and valves, filed as auto components: " + _KIN),
    "retail:BLMH": ("Other", "a cannabis products company: " + _OTHER),
    "retail:BWMX": ("Other", "a consumer products brand company (catalogue seller): " + _OTHER),
    "retail:CHWY": ("Other", "an online pet retailer: " + _OTHER),
    "retail:CPNG": ("Other", "an online retailer (South Korea): " + _OTHER),
    "retail:DDL": ("Other", "an online fresh grocery seller: " + _OTHER),
    "retail:HEPS": ("Other", "an online retailer (Turkey): " + _OTHER),
    "retail:HOUR": ("Resale, rental and small digital commerce", "\"an online retailer engaged in e-commerce\": that layer's words (online, commerce)"),
    "retail:LITB": ("Other", "an online clothing seller: " + _OTHER),
    "retail:LULU": ("Other", "an athletic apparel brand: " + _OTHER),
    "retail:LUXE": ("Other", "an online luxury fashion seller: " + _OTHER),
    "retail:LVLU": ("Other", "a women's clothing brand: " + _OTHER),
    "retail:NEXR": ("Other", "an e-commerce seller on Amazon: " + _OTHER),
    "retail:PLBY": ("Resale, rental and small digital commerce", "licensing, digital subscriptions and online entertainment: that layer's words (digital, online)"),
    "retail:SFIX": ("Other", "an online personal styling service: " + _OTHER),
    "retail:W": ("Resale, rental and small digital commerce", "\"an e-commerce company that sells furniture and home goods online\": that layer's words (online, commerce)"),
}

# moves an earlier review rejected (and this lane's first pass made): these companies keep the layer the Release 37 rules give them
KEEP = {
    "pharma": None,                                           # every company: excipient, animal-health and OTC groups as they are
    "chem": None,                                             # agrochemical, gas and petrochemical makers stay as Release 37 has them
    "cyber": None,
    "metals": {"ARFIN", "HINDALUMI", "MMP", "JAINREC", "20MICRONS", "GOACARBON"},
}


def replay_vc(t, blank: bool = False) -> list[dict]:
    """The value chain when the live map is placed again from its kept answer (theme_base.place_rest, no AI): the map's own layers with
    the companies the kept placement left there (the halves of a layer split by market value joined again: the smaller half's companies the
    map placed stay in it), every company the split moved (and the "Other" group's) back in one official group, each company's words its
    other words and its one line."""
    own, rest, models, conf, tags, words = {}, [], {}, {}, {}, {}
    by_x = {}
    for c in t["companies"]:
        by_x.setdefault(c["x"], []).append(c)
    for i, v in enumerate(t["layers"]):
        base = _HALF.sub("", v["layer"])
        joined = v.get("by_model") and base != v["layer"]
        for c in by_x.get(i, []):
            words[c["s"]] = " ".join(x for x in (c.get("a"), c["w"]) if x)
            row = {"ticker": c["s"], "name": c["n"], "what": c["w"], "industry": c["i"], "cap": c["cap"], "basis": c["b"]}
            if c["m"]:
                models[c["s"]], conf[c["s"]] = c["m"], c["c"]
            if c.get("g"):
                tags[c["s"]] = c["g"]
            if v.get("official") or (v.get("by_model") and not joined) or c.get("mv"):
                if blank:          # its stored evidence holds no words of its own (live: no description read yet)
                    words[c["s"]], row["what"] = "", ""
                rest.append(row)
            else:
                own.setdefault(base, {"layer": base, "description": "", "companies": []})["companies"].append(row)
        if not v.get("official") and (not v.get("by_model") or joined):
            lay = own.setdefault(base, {"layer": base, "description": "", "companies": []})
            lay["description"] = lay["description"] or v.get("description") or ""
    m = {"sector": t["theme"], "value_chain": list(own.values()) + [{"layer": "Official", "official": True, "basis": "industry", "companies": rest}]}
    kept = {"assign": {c["ticker"]: {"layer": "", "by": "ai"} for c in rest}, "models": models, "model_confidence": conf, "model_tags": tags}
    out, _ = B.place_rest(m, t["theme"], lambda s: words.get(s) or "", ask=None, kept=kept)
    return out["value_chain"]


def layer_of(vc) -> dict:
    return {c["ticker"]: ("Other" if v.get("official") else _HALF.sub("", v["layer"])) for v in vc for c in v["companies"]}


def live_split(t) -> dict:
    """{symbol: layer} when the live split (by_model) runs on the live map with the models as the map shows them (no model refined again):
    the companies the split moved (and the "Other" group's) start in "Other", as the live placement had them."""
    own, rest, models, conf, tags, ev = {}, [], {}, {}, {}, {}
    for c in t["companies"]:
        v = t["layers"][c["x"]]
        base = _HALF.sub("", v["layer"])
        joined = v.get("by_model") and base != v["layer"]
        ev[c["s"]] = model_evidence(c["i"], " ".join(x for x in (c.get("a"), c["w"]) if x))
        row = {"ticker": c["s"], "name": c["n"], "what": c["w"], "industry": c["i"], "cap": c["cap"], "basis": c["b"]}
        if c["m"]:
            models[c["s"]], conf[c["s"]] = c["m"], c["c"]
        if c.get("g"):
            tags[c["s"]] = c["g"]
        if v.get("official") or (v.get("by_model") and not joined) or c.get("mv"):
            rest.append(row)
        else:
            own.setdefault(base, {"layer": base, "description": v.get("description") or "", "companies": []})["companies"].append(row)
    for i, v in enumerate(t["layers"]):
        base = _HALF.sub("", v["layer"])
        if not v.get("official") and not v.get("by_model"):
            own.setdefault(base, {"layer": base, "description": v.get("description") or "", "companies": []})
    vc = list(own.values()) + [{"layer": "Other", "official": True, "basis": "rest", "companies": rest}]
    return layer_of(B.by_model(vc, models, t["theme"], tags=tags, confidence=conf, evidence_of=lambda s: ev.get(s) or ""))


def _theme(key):
    return next(t for t in LAYERS["themes"] if t["key"] == key)


def test_the_fixture_holds_the_fourteen_benchmark_maps():
    assert [t["key"] for t in LAYERS["themes"]] == ["auto", "bank", "semis", "it", "pharma", "insurance", "defence", "cyber", "chem", "realty",
                                                    "telecom", "retail", "utilities", "metals"]
    assert sum(len(t["companies"]) for t in LAYERS["themes"]) >= 1600
    assert "Release 37" in LAYERS["note"]


def test_no_company_in_any_theme_changes_its_layer_unless_approved():
    moved = []
    for t in LAYERS["themes"]:
        got = layer_of(replay_vc(t))
        for c in t["companies"]:
            k = f"{t['key']}:{c['s']}"
            want = APPROVED[k][0] if k in APPROVED else c["e"]
            if got[c["s"]] != want:
                moved.append(f"{k} ({c['n']}): expected {want!r}, got {got[c['s']]!r}")
    assert not moved, "a rule change moved these companies to another layer (edit APPROVED, with the reason, if on purpose):\n" + "\n".join(moved)


def test_every_approved_move_is_a_company_of_the_fixture_and_differs_from_release_37():
    every = {f"{t['key']}:{c['s']}": c for t in LAYERS["themes"] for c in t["companies"]}
    for k, (layer, why) in APPROVED.items():
        assert k in every and every[k]["e"] != layer and len(why) > 20, k


def test_the_moves_are_the_intended_ones_only():
    by_theme = {}
    for k in APPROVED:
        by_theme.setdefault(k.split(":")[0], set()).add(k.split(":")[1])
    assert sorted(by_theme) == ["auto", "retail"] and len(APPROVED) == 19
    every = {f"{t['key']}:{c['s']}": c for t in LAYERS["themes"] for c in t["companies"]}
    # nothing moves into the off-price layer or the equipment layer; every retail move leaves the off-price layer, every auto move tyres
    assert not any(layer.startswith("Off-price") or layer == "Semiconductor equipment" for layer, _ in APPROVED.values())
    assert all(every[f"retail:{s}"]["e"].startswith("Off-price") for s in by_theme["retail"])
    assert all(every[f"auto:{s}"]["e"] == "Tyre manufacturers" for s in by_theme["auto"])
    # every company leaving a layer it reached by the split, never a company the map placed in its layer itself
    assert all(every[k].get("mv") or t_layer_official(k) for k in APPROVED), [k for k in APPROVED if not every[k].get("mv") and not t_layer_official(k)]


def test_the_rejected_moves_do_not_happen():
    """The coordinator's review of this lane's first pass: pharma's excipient, animal-health and OTC makers, the aluminium product makers,
    Gen Digital and every chemicals company keep the layer the Release 37 rules give them, and no new layer named by how its companies earn
    appears in a theme whose family already has map layers ("Retail" beside four retail layers)."""
    for key, syms in KEEP.items():
        t = _theme(key)
        got = layer_of(replay_vc(t))
        for c in t["companies"]:
            if syms is None or c["s"] in syms:
                assert got[c["s"]] == c["e"], (key, c["s"], c["e"], got[c["s"]])
    for key in ("retail", "pharma", "chem", "it", "auto", "metals"):
        t = _theme(key)
        before = {c["e"] for c in t["companies"]}
        after = set(layer_of(replay_vc(t)).values())
        assert after <= before | {"Other"}, (key, after - before)
    assert "Retail" not in set(layer_of(replay_vc(_theme("retail"))).values())


def t_layer_official(k):
    key, sym = k.split(":")
    t = _theme(key)
    c = next(c for c in t["companies"] if c["s"] == sym)
    v = t["layers"][c["x"]]
    return bool(v.get("official") or v.get("by_model"))


def test_the_review_items_hold_on_the_live_maps():
    retail = layer_of(replay_vc(_theme("retail")))
    # Vipshop ("online discount sales") shares "discount" with the off-price layer's own words, so the largest stands for it, as before
    for s in ("CPNG", "W", "CHWY", "LULU", "JD"):
        assert not retail[s].startswith("Off-price"), s
    for s in ("SPH", "FCFS", "EZPW", "FGPR"):
        assert retail[s] == "Other", s
    assert retail["JD"] == "Resale, rental and small digital commerce"     # a broad online retailer, out of "Niche": the online commerce layer
    semis = layer_of(replay_vc(_theme("semis")))
    for s in ("MU", "INTC", "SKHY", "QRVO", "IPGP", "LASR", "LEDS", "KOPN", "AAOI", "PLAB"):
        assert semis[s] != "Semiconductor equipment", s
    # the coordinator's cases from the same review: Bosch (fuel injection, auto parts) and Asahi India Glass (auto glass) were moved into
    # "Tyre manufacturers" (the deck showed them under "Batteries and tractor makers"); the component suppliers' layer is theirs. VST
    # Tillers Tractors, which the map placed in "Batteries and tractor makers" itself, stays there
    auto = layer_of(replay_vc(_theme("auto")))
    for s in ("BOSCHLTD", "ASAHIINDIA"):
        assert auto[s] == "Component and systems suppliers", (s, auto[s])
    assert auto["VSTTILLERS"] == "Batteries and tractor makers"


def test_the_live_split_no_longer_joins_chip_makers_to_the_equipment_layer():
    # Release 37 live: the equipment layer's known models were all "manufacturing" (two companies' unknown), so the split's "Makers of their
    # own products" (Micron, Intel, SK Hynix, lasers, LEDs) shared its primary model and joined it whole (step 3b); now only companies
    # whose own words share the equipment layer's words would join, and none of these do
    semis = live_split(_theme("semis"))
    for s in ("MU", "INTC", "SKHY", "QRVO", "NLST", "VIAV", "AAOI", "IPGP", "LASR", "PLAB", "KOPN", "LPTH", "LEDS"):
        assert semis[s] == "Makers of their own products", (s, semis[s])
    for s in ("ASML", "AMAT", "LRCX", "KLAC", "TER"):
        assert semis[s] == "Semiconductor equipment", s
    retail = live_split(_theme("retail"))
    for s in ("CPNG", "W", "CHWY", "LULU", "JD", "FCFS", "EZPW", "SPH"):
        assert not retail[s].startswith("Off-price"), s
    auto = live_split(_theme("auto"))
    for s in ("BOSCHLTD", "ASAHIINDIA", "VELJAN"):
        assert auto[s] == "Component and systems suppliers", s
    assert auto["VSTTILLERS"] == "Batteries and tractor makers"
    for s in ("TJX", "ROST", "BURL", "DG", "DLTR", "FIVE", "OLLI"):
        assert retail[s].startswith("Off-price"), s


def _layer_diff():
    import importlib.util
    path = pathlib.Path(__file__).parent.parent / "scripts" / "layer_diff.py"
    spec = importlib.util.spec_from_file_location("layer_diff", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_layer_diff_lists_every_company_whose_layer_changed(tmp_path, capsys):
    ld = _layer_diff()
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    for d, (where_w, where_m) in ((before, ("Off-price (larger)", "Off-price (smaller)")), (after, ("Online sellers", "Off-price (larger)"))):
        vc = [{"layer": where_w, "companies": [{"ticker": "W", "name": "Wayfair"}]},
              {"layer": where_m, "companies": [{"ticker": "TJX", "name": "TJX"}]},
              {"layer": "Other consumer retail companies", "official": True, "companies": [{"ticker": "SPH", "name": "Suburban Propane"}]}]
        (d / "sec_retail.json").write_text(json.dumps({"sector": "Consumer retail", "value_chain": vc}))
    (before / "sec_semis.json").write_text(json.dumps({"value_chain": []}))
    moves, notes = ld.diff(before, after)
    # the halves of one layer count as one (TJX did not move), the official group is "Other"; a theme on one side only is noted
    assert moves == [{"theme": "retail", "symbol": "W", "name": "Wayfair", "from": "Off-price", "to": "Online sellers"}]
    assert notes == ["semis: only in before"]
    moves, _ = ld.diff(before, after, halves=True)
    assert {m["symbol"] for m in moves} == {"W", "TJX"}
    assert ld.main([str(before), str(after)]) == 0
    out = capsys.readouterr().out
    assert "retail\tW\tWayfair\tOff-price\t->\tOnline sellers" in out and out.strip().endswith("1 companies changed layer")
    assert ld.main([str(before), str(tmp_path / "missing")]) == 2


def test_a_company_with_no_words_joins_the_largest_only_when_it_holds_its_industry():
    """Live R37 Consumer retail: Suburban Propane and FirstCash, whose stored evidence held no words of their own, went to "Off-price, dollar
    and value-format retailers", the largest retail layer, which holds none of their industry (Retail-Miscellaneous Retail): they stay in
    "Other". A company with no words whose industry the largest holds still joins it; with no industry known either, the largest, as before."""
    t = _theme("retail")
    blank = {"SPH", "FCFS", "EZPW"}
    t2 = {**t, "companies": [{**{k: x for k, x in c.items() if k != "a"}, "w": ""} if c["s"] in blank else c for c in t["companies"]]}
    got = layer_of(replay_vc(t2))
    for s in blank:
        assert got[s] == "Other", (s, got[s])
    big = ("Apparel chains", "Chains selling clothing and footwear.", [("Retail-Family Clothing Stores", "sells clothing")] * 5)
    small = ("Online retailers", "Companies selling online.", [("Retail-Catalog & Mail-Order Houses", "sells online")] * 3)
    vc = [{"layer": n, "description": d, "companies": [{"ticker": f"{n[:3]}{i}", "industry": ind, "what": w, "cap": 10 - i} for i, (ind, w) in enumerate(cos)]}
          for n, d, cos in (big, small)]
    vc.append({"layer": "Other", "description": "", "official": True, "basis": "rest", "companies": [
        {"ticker": "P", "industry": "Retail-Miscellaneous Retail", "what": "", "cap": 1},
        {"ticker": "Q", "industry": "Retail-Family Clothing Stores", "what": "", "cap": 1},
        {"ticker": "R", "industry": "", "what": "", "cap": 1}]})
    models = {c["ticker"]: "retail" for v in vc for c in v["companies"]}
    out = layer_of(B.by_model(vc, models, "Retail", confidence={s: "high" for s in models}))
    assert out["P"] == "Other" and out["Q"] == "Apparel chains" and out["R"] == "Apparel chains"


def test_with_every_movers_words_blanked_none_lands_in_a_layer_of_another_industry():
    """Every company the split moves (and the "Other" group's) replayed with no words of its own, as live has them when its stored evidence
    is missing: each ends in "Other", a layer named by how it earns, or a map layer that holds its official industry; never in a layer of
    another industry by default. The review items hold too."""
    for t in LAYERS["themes"]:
        got = layer_of(replay_vc(t, blank=True))
        inds, movers = {}, []
        for c in t["companies"]:
            v = t["layers"][c["x"]]
            base = _HALF.sub("", v["layer"])
            joined = v.get("by_model") and base != v["layer"]
            if v.get("official") or (v.get("by_model") and not joined) or c.get("mv"):
                movers.append(c)
            else:
                inds.setdefault(base, set()).add(B.key(c["i"]))
        wrong = [(c["s"], c["i"], got[c["s"]]) for c in movers if got[c["s"]] in inds and B.key(c["i"]) not in inds[got[c["s"]]]]
        assert not wrong, (t["key"], wrong)
    retail = layer_of(replay_vc(_theme("retail"), blank=True))
    for s in ("SPH", "FCFS", "EZPW", "FGPR", "CPNG", "W", "VIPS", "CHWY", "LULU", "JD"):
        assert retail[s] == "Other", (s, retail[s])
    auto = layer_of(replay_vc(_theme("auto"), blank=True))
    for s in ("BOSCHLTD", "ASAHIINDIA", "VELJAN"):
        assert auto[s] == "Component and systems suppliers", s
    semis = layer_of(replay_vc(_theme("semis"), blank=True))
    for s in ("MU", "INTC", "SKHY"):
        assert semis[s] != "Semiconductor equipment", s
