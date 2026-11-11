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

_AGRO = ("an agrochemical maker: the one layer holding its industry, \"Custom synthesis manufacturers\", is named for contract making, and "
         "\"Specialty and performance chemicals\" (additives, surfactants, dyes) holds neither its industry nor its words: stays in Other")
_PHARMA = ("its industry (Pharmaceuticals) is most of three of the map's layers and its words name none of them (not export generics): a "
           "layer named by how it earns, not the largest by default")
_OFFPRICE = "no layer of its family holds its industry and shares its words (not an off-price, dollar or variety format): stays in Other"

# "theme:symbol" -> (its layer now, why it moved)
APPROVED = {
    "auto:ASAHIINDIA": ("Component and systems suppliers", "an automotive glass maker, not a tyre maker: no makers' layer holds its industry or its words; the component suppliers' layer is all of its industry (left out of its figures as another way of earning)"),
    "auto:BOSCHLTD": ("Component and systems suppliers", "fuel injection systems and auto parts, not tyres: no makers' layer holds its industry or its words; the component suppliers' layer is all of its industry (left out of its figures as another way of earning)"),
    "auto:STUDDS": ("Other", "a helmet and motorcycle accessories maker: its words name two-wheelers but its industry is another layer's, so not a two-wheeler maker"),
    "auto:VELJAN": ("Component and systems suppliers", "hydraulic pumps, motors and valves, not tyres: the component suppliers' layer is all of its industry (left out of its figures as another way of earning)"),
    "chem:ADVANCE": ("Other", _AGRO),
    "chem:ANDHRSUGAR": ("Chlor-alkali and soda ash producers", "its words name chlor-alkali products, and that layer holds its industry"),
    "chem:ASTEC": ("Other", _AGRO),
    "chem:BAYERCROP": ("Other", _AGRO),
    "chem:BEPL": ("Other", "ABS and other engineering resins: no layer holds its industry and shares its words (not niche additives or dyes)"),
    "chem:BESTAGRO": ("Other", _AGRO),
    "chem:BHAGCHEM": ("Other", _AGRO),
    "chem:BHARATRAS": ("Other", _AGRO),
    "chem:DEEPAKFERT": ("Basic organic intermediates", "fertilisers and petrochemicals: that layer converts petrochemical feedstocks and holds its industry"),
    "chem:DHANUKA": ("Other", _AGRO),
    "chem:DHARMAJ": ("Other", _AGRO),
    "chem:ELLEN": ("Fluorochemicals and refrigerants", "an industrial gases maker: the layer where the map keeps the industrial gas makers, sharing its words (gases)"),
    "chem:GNFC": ("Other", "its words say nothing of what it makes and its industry (Commodity Chemicals) is spread over the map: no layer by default"),
    "chem:GSPCROP": ("Other", _AGRO),
    "chem:HERANBA": ("Other", _AGRO),
    "chem:INSECTICID": ("Other", _AGRO),
    "chem:IPL": ("Other", _AGRO),
    "chem:KOTHARIPET": ("Basic organic intermediates", "a petrochemical maker (polyisobutylene): that layer converts petrochemical feedstocks and holds its industry"),
    "chem:LINDEINDIA": ("Fluorochemicals and refrigerants", "an industrial and medical gases maker: the layer where the map keeps the industrial gas makers, sharing its words (gases)"),
    "chem:MOL": ("Other", _AGRO),
    "chem:PASUPTAC": ("Other", "acrylic fibre and film: no layer holds its industry and shares its words (not niche additives or dyes)"),
    "chem:RAIN": ("Other", "carbon, cement and advanced materials: no layer holds its industry and shares its words; its industry is most of none"),
    "chem:RALLIS": ("Other", _AGRO),
    "chem:SHIVALIK": ("Other", _AGRO),
    "chem:SPLPETRO": ("Basic organic intermediates", "a petrochemical maker (polystyrene): that layer converts petrochemical feedstocks and holds its industry"),
    "chem:SUMICHEM": ("Other", _AGRO),
    "chem:TNPETRO": ("Basic organic intermediates", "a petrochemical products maker: that layer converts petrochemical feedstocks and holds its industry"),
    "chem:UPL": ("Other", _AGRO),
    "cyber:GEN": ("Other", "its words say only \"software company\" and its industry is most of several layers: no layer by default (alone in a layer of its way of earning, so Other)"),
    "it:ACESOFT": ("Digital engineering and consulting projects", "document management, digital publishing, data conversion and technology consulting: that layer's words"),
    "it:MCLOUD": ("Project and consulting services", "IT services, surveillance and drones: its industry is most of several layers and its words fit none: a layer named by how it earns"),
    "it:TREJHARA": ("Project and consulting services", "software services and licences: its industry is most of several layers and its words fit none: a layer named by how it earns"),
    "metals:20MICRONS": ("Coal, iron ore and mineral mining", "industrial minerals: that layer holds its industry and shares its words (industrial minerals), not ferro alloys"),
    "metals:ARFIN": ("Other", "non-ferrous metals: its industry (Aluminium) is no makers' layer's and its words fit none"),
    "metals:GOACARBON": ("Coal, iron ore and mineral mining", "calcined petroleum coke: its industry (Industrial Minerals) is most of that layer's companies; not ferro alloys"),
    "metals:HINDALUMI": ("Other", "aluminium products and power: one shared word, its industry (Aluminium) not that layer's: stays in Other"),
    "metals:JAINREC": ("Other", "a scrap recycler: no metal processors' layer holds its industry and shares its words"),
    "metals:MMP": ("Other", "aluminium powder: one shared word, its industry (Aluminium) not that layer's: stays in Other, as the live map has it"),
    "pharma:AARTIPHARM": ("Makers of their own products", _PHARMA),
    "pharma:AMBALALSA": ("Makers of their own products", _PHARMA),
    "pharma:AMRUTANJAN": ("Makers of their own products", _PHARMA + "; an ayurvedic balm maker"),
    "pharma:ANUHPHR": ("Makers of their own products", _PHARMA + "; a bulk drug maker"),
    "pharma:BALPHARMA": ("Makers of their own products", _PHARMA + "; no words"),
    "pharma:HESTERBIO": ("Makers of their own products", _PHARMA + "; an animal vaccine maker"),
    "pharma:KOPRAN": ("Makers of their own products", _PHARMA + "; formulations and ingredients, sold globally"),
    "pharma:MAKERSL": ("Makers of their own products", _PHARMA),
    "pharma:NATCAPSUQ": ("Makers of their own products", _PHARMA + "; no words"),
    "pharma:PANCHSHEEL": ("Makers of their own products", _PHARMA + "; no words"),
    "pharma:SAKAR": ("Makers of their own products", _PHARMA),
    "pharma:SIGACHI": ("Makers of their own products", _PHARMA + "; an excipient maker"),
    "pharma:VIYASH": ("Makers of their own products", _PHARMA + "; an animal health company"),
    "retail:AKA": ("Other", "a fashion brand: " + _OFFPRICE),
    "retail:BLMH": ("Other", "a cannabis products company: one shared word only: " + _OFFPRICE),
    "retail:BWMX": ("Other", "a consumer products brand company: " + _OFFPRICE),
    "retail:CHWY": ("Niche specialty and category retailers", "an online pet retailer: that layer's words (pets, online)"),
    "retail:CIMG": ("Other", "a food distributor in Asia: " + _OFFPRICE + ", as the live map has it"),
    "retail:CPNG": ("Other", "an online retailer: one shared word (online) only: " + _OFFPRICE),
    "retail:CURV": ("Other", "a women's apparel chain: " + _OFFPRICE),
    "retail:DDL": ("Other", "an online fresh grocery seller: " + _OFFPRICE),
    "retail:DDS": ("Other", "a department store chain: " + _OFFPRICE),
    "retail:DLTH": ("Other", "a workwear and apparel brand: " + _OFFPRICE),
    "retail:HEPS": ("Other", "an online marketplace retailer: " + _OFFPRICE),
    "retail:HOUR": ("Resale, rental and small digital commerce", "an online e-commerce retailer: that layer's words (online commerce)"),
    "retail:JD": ("Retail", "an e-commerce retailer: its industry is most of three layers and its words fit none twice: a layer named by how it earns"),
    "retail:JL": ("Other", "a garment trims distributor: " + _OFFPRICE),
    "retail:KSS": ("Other", "a department store chain: " + _OFFPRICE),
    "retail:LITB": ("Other", "an online clothing seller: " + _OFFPRICE),
    "retail:LULU": ("Other", "an athletic apparel brand: " + _OFFPRICE),
    "retail:LUXE": ("Other", "an online luxury fashion seller: " + _OFFPRICE),
    "retail:LVLU": ("Other", "a women's clothing brand (\"accessible prices\" is no accessory): " + _OFFPRICE),
    "retail:M": ("Other", "a department store chain: " + _OFFPRICE),
    "retail:NEXR": ("Other", "an e-commerce seller on Amazon: " + _OFFPRICE),
    "retail:NXH": ("Other", "an e-commerce brand owner: " + _OFFPRICE),
    "retail:PLBY": ("Resale, rental and small digital commerce", "licensing, digital subscriptions and online: that layer's words (digital, online)"),
    "retail:RVLV": ("Other", "an online fashion seller (\"discovery\" is no discount): " + _OFFPRICE),
    "retail:SFIX": ("Other", "an online styling service: " + _OFFPRICE),
    "retail:SVV": ("Other", "a thrift store operator: " + _OFFPRICE),
    "retail:TLYS": ("Other", "an apparel store chain: " + _OFFPRICE),
    "retail:VIPS": ("Resale, rental and small digital commerce", "an e-commerce site for online discount sales: that layer's words (online commerce)"),
    "retail:W": ("Resale, rental and small digital commerce", "an e-commerce company selling home goods online: that layer's words (online commerce)"),
    "retail:YJ": ("Retail", "a membership shopping app: its industry is most of three layers and its words fit none: a layer named by how it earns"),
    "retail:ZUMZ": ("Other", "a specialty clothing store: " + _OFFPRICE),
    "telecom:PACEDIGITK": ("Tower infrastructure", "telecom infrastructure: no makers' layer holds its industry or its words; the tower layer is all of its industry (left out of its figures as another way of earning)"),
    "utilities:INA": ("Other", "a solar panel maker: its industry (Power Generation) is no equipment layer's and its words fit none"),
    "utilities:NAVA": ("Other", "ferro alloys, metals and power abroad: its words fit no generation layer twice; alone in a layer of its way of earning, so Other"),
}


def replay_vc(t) -> list[dict]:
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
    assert sorted(by_theme) == ["auto", "chem", "cyber", "it", "metals", "pharma", "retail", "telecom", "utilities"]
    assert len(APPROVED) == 89
    every = {f"{t['key']}:{c['s']}": c for t in LAYERS["themes"] for c in t["companies"]}
    # nothing moves into the off-price layer or the equipment layer; every off-price move leaves it
    assert not any(layer.startswith("Off-price") or layer == "Semiconductor equipment" for layer, _ in APPROVED.values())
    assert all(every[f"retail:{s}"]["e"].startswith("Off-price") for s in by_theme["retail"] - {"JD", "YJ"})
    # every company leaving a layer it reached as the largest of its family, never a company the map placed in its layer itself
    assert all(every[k].get("mv") or t_layer_official(k) for k in APPROVED), [k for k in APPROVED if not every[k].get("mv") and not t_layer_official(k)]


def t_layer_official(k):
    key, sym = k.split(":")
    t = _theme(key)
    c = next(c for c in t["companies"] if c["s"] == sym)
    v = t["layers"][c["x"]]
    return bool(v.get("official") or v.get("by_model"))


def test_the_review_items_hold_on_the_live_maps():
    retail = layer_of(replay_vc(_theme("retail")))
    for s in ("CPNG", "W", "VIPS", "CHWY", "LULU", "M", "KSS", "DDS"):
        assert not retail[s].startswith("Off-price"), s
    for s in ("SPH", "FCFS", "EZPW", "FGPR"):
        assert retail[s] == "Other", s
    assert not retail["JD"].startswith("Niche")         # a broad online retailer (its own layer of retailers: no layer fits it twice)
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
    for s in ("CPNG", "W", "VIPS", "CHWY", "LULU", "M", "KSS", "DDS", "FCFS", "EZPW", "SPH"):
        assert not retail[s].startswith("Off-price"), s
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
