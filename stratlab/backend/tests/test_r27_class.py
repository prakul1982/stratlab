"""Release 27, lane r27-class (the owner's outside review of the eight live R26 decks): each company has one primary revenue model, secondary
tags and a confidence, stored with the map from the same batched answer; a layer names its diversified members ("3 of the 9 also earn from
..."); a company whose model is unknown or of low confidence is listed in its layer but left out of its figures and rankings (one line says how
many and why); more of the stored text (the company page's business read, the earning sentences of a long description) reaches the model's
question; a split never leaves a one-company layer; the model families keep comparable businesses apart in every sector (IT hardware, software,
platforms, BPO and projects; contract makers and product companies; OEMs and components; insurers by type). Generic: synthetic themes only,
India and the US; no name or figure tuned to a real company."""
import copy
import json

import pytest

from app.intel import ai as A
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from tests.synth_structures_r27class import NEW, banks_in, structures
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
from tests.test_r25_class import co


def split(theme: dict) -> tuple:
    t = copy.deepcopy(theme)
    vc = B.by_model(t["map"]["value_chain"], t["models"], t["map"]["sector"], tags=t["tags"], confidence=t["confidence"])
    return t, vc


def layer_of(vc, sym):
    return next(v for v in vc if sym in [c["ticker"] for c in v["companies"]])


# ---------- 5. comparable segments, generic by sector; every deck rule on the new structures ----------
@pytest.mark.parametrize("name,theme", list(structures()), ids=[n for n, _ in structures()])
def test_each_sector_splits_comparable_businesses_apart_and_every_deck_rule_holds(name, theme):
    t, vc = split(theme)
    models = t["models"]
    # one family a layer, never a one-company layer made by the split
    for v in vc:
        fams = {C.model_family(models.get(c["ticker"])) for c in v["companies"] if t["confidence"].get(c["ticker"]) != "low"} - {""}
        assert len(fams) <= 1, (v["layer"], fams)
        if not v.get("official"):
            assert len(v["companies"]) != 1 or not v.get("by_model"), v["layer"]
    # the models that must stay apart never share a layer
    for a, b in t["apart"]:
        for v in vc:
            ids = {models.get(c["ticker"]) for c in v["companies"]}
            assert not (a in ids and b in ids) or v.get("official"), (v["layer"], a, b)
    # every company carries its model, tags and confidence for the checks
    for v in vc:
        for c in v["companies"]:
            assert {"model", "model_tags", "model_confidence"} <= set(c), c["ticker"]
    m = {**t["map"], "value_chain": vc}
    view, slides = deck_of(t["region"], m, t["facts"])
    every_rule(name, view, slides)
    tx = texts(slides)
    assert "In common: they earn mainly from" in tx
    assert "Hotels, travel and consumer services" not in tx
    # the theme data carries each company's model for the quality gate
    rows = [r for x in view.get("layers") or [] for r in x.get("companies") or []]
    assert rows and all("model" in r and "model_confidence" in r and "model_tags" in r for r in rows)


def test_the_new_structures_are_the_ones_the_brief_names():
    assert set(NEW) == {"chemicals (IN)", "real estate (IN)", "telecom (IN)", "telecom (US)", "consumer retail (US)", "utilities and power (IN)",
                        "metals and mining (IN)"}


# ---------- 1. primary model, tags and confidence; the layer names its diversified members ----------
def test_a_layer_names_how_many_of_its_companies_also_earn_another_way():
    t, vc = split(dict(structures())["auto (IN)"])
    oem = layer_of(vc, "OEM0")
    assert oem["model"]["id"] == "manufacturing" and oem["model"]["also"] == [{"id": "lending", "n": 2}]
    assert oem["model"]["line"] == "They earn mainly from making and selling finished products of their own. 2 of the 4 also earn from interest on loans they make."
    assert layer_of(vc, "CMP0") is not oem and layer_of(vc, "CMP0")["model"]["id"] == "components"
    view, slides = deck_of(t["region"], {**t["map"], "value_chain": vc}, t["facts"])
    assert "In common: they earn mainly from making and selling finished products of their own. 2 of the 4 also earn from interest on loans" in texts(slides)
    # a tag of the layer's own family isn't news: pharma brands that also make for others are named, contract makers stay apart
    t, vc = split(dict(structures())["pharma (IN)"])
    brands = layer_of(vc, "FRM0")
    assert "2 of the 4 also earn from making products to other companies' designs and orders." in brands["model"]["line"]
    assert layer_of(vc, "CDM0") is not brands


def test_place_in_layers_reads_primary_model_tags_and_confidence():
    def ask(system, text):
        return {"place": [], "rename": [], "extra": [], "models": {
            "A1": {"model": "manufacturing", "also": ["lending", "made-up", "manufacturing"], "confidence": "High"},
            "A2": "software",                                            # the R25 form still reads
            "A3": {"model": "unknown", "also": ["lending"], "confidence": "high"},
            "ZZ": {"model": "software"}}}                               # not asked about
    got = C.place_in_layers([{"layer": "L", "companies": [{"ticker": "A1", "name": "a"}, {"ticker": "A2", "name": "b"}, {"ticker": "A3", "name": "c"}]}],
                            [], ask, "Autos")
    assert got["models"] == {"A1": "manufacturing", "A2": "software"}
    assert got["tags"] == {"A1": ["lending"]} and got["confidence"] == {"A1": "high"}
    lst = C.place_in_layers([{"layer": "L", "companies": [{"ticker": "A1", "name": "a"}]}], [],
                            lambda s, t: {"models": [{"symbol": "A1", "model": "lending", "also": [], "confidence": "low"}]}, "Banks")
    assert lst["models"] == {"A1": "lending"} and lst["confidence"] == {"A1": "low"}
    assert '"also"' in C.PLACE_SYSTEM2 and '"confidence"' in C.PLACE_SYSTEM2


@pytest.mark.parametrize("model,evidence,said,level", [
    ("software", "Industry: Software Products. Sells subscriptions to its own software.", "", "high"),
    ("software", "Industry: Software Products. Helps firms grow.", "", "medium"),
    ("software", "Industry: Banks. Helps firms grow.", "", "low"),
    ("software", "Industry: Software Products. Sells subscriptions to its own software.", "medium", "medium"),       # never above what the AI said
    ("software", "Industry: Banks. Helps firms grow.", "high", "low"),                                                  # never above the evidence
    ("lending", "Industry: Private Sector Bank. Serves households.", "", "medium"),
    ("unknown", "anything", "high", ""),
])
def test_confidence_is_how_directly_the_evidence_states_the_model(model, evidence, said, level):
    assert C.model_confidence(model, evidence, said) == level


def test_tags_need_words_of_their_kind_and_are_never_the_primary():
    ev = "Industry: Cars. Makes cars under its brands; its financing arm lends to buyers."
    assert C.model_tags(["lending", "manufacturing", "platform", "lending", "x"], "manufacturing", ev) == ["lending"]
    assert C.model_tags("lending", "manufacturing", ev) == [] and C.model_tags(None, "manufacturing", ev) == []


def calls_ai(calls, said=None):
    """A placement answer that gives each company the model, tags and confidence its words show."""
    signs = [("contact centre", "bpo"), ("back-office", "bpo"), ("subscription", "software"), ("project", "project_services"),
             ("consult", "project_services"), ("makes", "manufacturing"), ("lends", "lending")]

    def ask(system, text):
        if system == C.NAMES_SYSTEM:
            calls.append(("names", None))
            return {"rename": []}
        if system == C.MODEL_SYSTEM:
            body = json.loads(text.split("EVIDENCE:\n", 1)[1])
            calls.append(("again", body))
            return {"models": {c["symbol"]: next((m for k, m in signs if k in c["evidence"].lower()), "unknown") for c in body["companies"]}}
        body = json.loads(text.split("COMPANIES:\n", 1)[1])
        calls.append(("place", body))
        models = {}
        words = {mem.split(" · ", 1)[0]: mem.split(" · ", 1)[1] for lay in body["layers"].values() for mem in lay["members"]}
        words.update({c["symbol"]: f"{c['description']} {c.get('evidence') or ''}" for c in body["companies"]})
        for sym, w in words.items():
            md = next((m for k, m in signs if k in w.lower()), "unknown")
            models[sym] = {"model": md, "also": ["lending"] if "financ" in w.lower() else [], "confidence": (said or {}).get(sym, "high")}
        models.update({s: {"model": m, "also": [], "confidence": "high"} for s, m in ((said or {}).get("override") or {}).items()})
        return {"place": [{"symbol": c["symbol"], "layer": "L0"} for c in body["companies"]], "rename": [], "extra": [], "models": models}
    return ask


def autos_map():
    oem = [co(f"OM{i}", f"Carmake {i} Ltd", "makes cars under its brands; its financing arm lends to buyers", "Passenger Cars & Utility Vehicles", cap=90000 - i)
           for i in range(3)]
    return {"sector": "Autos", "summary": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
            "value_chain": [{"layer": "Vehicle makers", "description": "Cars.", "companies": oem},
                            {"layer": "Passenger Cars & Utility Vehicles", "official": True, "basis": "industry", "description": "",
                             "companies": [{"ticker": "OM9", "name": "Carmake 9 Ltd", "industry": "Passenger Cars & Utility Vehicles", "cap": 100,
                                            "base": True, "basis": "industry"}]}]}


def test_tags_and_confidence_are_stored_once_with_the_map_and_not_asked_again():
    calls = []
    about = {"OM9": "Carmake 9 makes cars under its brands."}
    out, got = B.place_rest(copy.deepcopy(autos_map()), "Autos", about.get, ask=calls_ai(calls))
    assert [k for k, _ in calls if k != "names"] == ["place"]                          # one batched answer, as before (names: R26's kept check)
    assert got["model_tags"] == {f"OM{i}": ["lending"] for i in range(3)}
    assert got["model_confidence"]["OM0"] == "high" and got["models"]["OM9"] == "manufacturing"
    lay = next(v for v in out["value_chain"] if v["layer"] == "Vehicle makers")
    assert "3 of the 4 also earn from interest on loans they make." in lay["model"]["line"]
    again, got2 = B.place_rest(copy.deepcopy(autos_map()), "Autos", about.get, ask=lambda s, t: pytest.fail("asked again"), kept=got)
    assert got2 == got and [v["model"] for v in again["value_chain"] if "model" in v] == [v["model"] for v in out["value_chain"] if "model" in v]


# ---------- 2. unknown or low confidence: listed, left out of the layer's figures and rankings ----------
def test_unknown_and_low_confidence_companies_are_listed_but_left_out_of_the_layer_figures():
    t, vc = split(banks_in())
    lay = layer_of(vc, "LND0")
    assert {c["ticker"] for c in lay["companies"]} >= {"LOW0", "UNK0"}                   # listed in their layer
    out = {c["ticker"] for c in lay["companies"] if c.get("model_out")}
    assert out == {"LOW0", "UNK0"}
    assert lay["model"]["line"] == ("They earn mainly from interest on loans they make. 2 of 7 are listed but left out of this layer's figures and "
                                    "rankings, as their evidence doesn't show, or only weakly shows, how they earn.")
    low = next(c for c in lay["companies"] if c["ticker"] == "LOW0")
    assert low["model"] == "lending" and low["model_confidence"] == "low"
    unk = next(c for c in lay["companies"] if c["ticker"] == "UNK0")
    assert unk["model"] == "" and unk["model_confidence"] == ""
    view, slides = deck_of(t["region"], {**t["map"], "value_chain": vc}, t["facts"])
    block = next(x for x in view["layers"] if x["layer"] == lay["layer"])
    assert block["n"] == 5 and block["listed"] == 7 and block["model_out"] == ["LOW0", "UNK0"]
    assert all(r.get("model_out") for r in block["companies"] if r["symbol"] in ("LOW0", "UNK0"))
    # the layer's median is the five lenders' only, and they alone are charted
    five = [r for r in block["companies"] if r["symbol"].startswith("LND")]
    assert block["revenue"] == sum(r["revenue"] for r in five if r.get("revenue"))
    assert all(st is None or st["n"] <= 5 for st in block["stats"].values())
    page = next(s for s in slides if s.title.startswith("Layer ") and lay["layer"] in s.title)
    cells = [str(r[0] if not isinstance(r[0], dict) else r[0].get("text")) for b in page.blocks if b["kind"] == "table" for r in b["rows"]]
    # the five lenders fill the page's rows first; the two left out are in the appendix, so the page carries no "(left out)" note for them
    assert not any(x.endswith("(left out)") for x in cells) and "Lendwell 0 Ltd" in cells
    assert not any("(left out):" in str(p) for b in page.blocks if b["kind"] == "text" for p in b.get("paras") or [])
    assert D.model_fields({"companies": [{"ticker": "X", "model": "lending", "model_tags": [], "model_confidence": "low", "model_out": True}]}, "X") == \
        {"model": "lending", "model_tags": [], "model_confidence": "low", "model_out": True}
    assert D.model_fields({"companies": [{"ticker": "X"}]}, "X") == {}
    for b in page.blocks:
        if b["kind"] == "hbars":
            assert not any("Vaguebank" in c or "Quietfin" in c for c in b["cats"])
    assert "left out of this layer's figures and rankings" in texts(slides)
    every_rule("banks with unsure models (IN)", view, slides)


def test_a_left_out_company_shown_on_the_layer_page_is_marked_with_its_note():
    from tests.synth_structures_r27class import build
    t = build("IN", "Lenders", [
        ("Lenders", "Lend.", [(f"L{i}", f"Loanco {i} Ltd", "a bank that lends", "Private Sector Bank", "lending", (), "high") for i in range(3)]
         + [("LW", "Vaguefin Ltd", "a group", "Private Sector Bank", "lending", (), "low")]),
        ("Fund managers", "Fees.", [(f"F{i}", f"Fundco {i} Ltd", "manages funds for fees", "Asset Management Company", "asset_management", (), "high")
                                    for i in range(3)])], [])
    _, vc = split(t)
    view, slides = deck_of("IN", {**t["map"], "value_chain": vc}, t["facts"])
    page = next(s for s in slides if s.title.startswith("Layer ") and "Lenders" in s.title)
    cells = [str(r[0] if not isinstance(r[0], dict) else r[0].get("text")) for b in page.blocks if b["kind"] == "table" for r in b["rows"]]
    assert "Vaguefin Ltd (left out)" in cells and cells.index("Vaguefin Ltd (left out)") == 3          # after the three counted
    assert any("(left out):" in str(p) for b in page.blocks if b["kind"] == "text" for p in b.get("paras") or [])
    assert "1 of 4 is listed but left out of this layer's figures and rankings, as its evidence shows how it earns only weakly." in texts(slides)
    every_rule("lenders, one left out (IN)", view, slides)


def test_a_low_confidence_model_moves_no_company():
    _, vc = split({**banks_in(), "models": {**banks_in()["models"], "LOW0": "asset_management"}})
    assert layer_of(vc, "LOW0") is layer_of(vc, "LND0")                                  # stays where it was placed


# ---------- 3. more of the stored text reaches the model's question ----------
def it_small_companies():
    """India, the IT services shape: two named layers and 51 base companies of the exchange's industry the map didn't place. 14 describe how they
    earn at the start; 15 only past the start of a long description; 12 have no description but a stored business read; 4 state it in so
    many words the AI leaves unknown ("staff augmentation"); 6 have nothing."""
    out = [co(f"OS{i}", f"Outsource {i} Ltd", "runs back offices for banks as a contact centre and back-office provider", cap=900000 - i) for i in range(4)]
    proj = [co(f"PN{i}", f"Named {i} Ltd", "delivers digital projects and consulting for clients", cap=80000 - i) for i in range(4)]
    base = [{"ticker": f"B{i:02d}", "name": f"Base {i} Ltd", "industry": "IT - Software", "cap": 50000 - i * 500, "base": True,
             "basis": "industry", "verified": False} for i in range(51)]
    m = {"sector": "IT services", "summary": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
         "value_chain": [{"layer": "Outsourcing and back offices", "description": "Run clients' processes.", "companies": out},
                         {"layer": "Digital projects", "description": "Project work.", "companies": proj},
                         {"layer": "IT - Software", "official": True, "basis": "industry", "description": "", "companies": base}]}
    fluff = ("The company was promoted by first-generation engineers and has grown steadily over three decades. It has won several awards for "
             "quality and is ISO certified. Its head office is in Pune and it has offices in four cities. ")
    about, kept = {}, {}
    for i in range(51):
        s = f"B{i:02d}"
        if i < 14:
            about[s] = "The company delivers IT projects and consulting to clients in banking and retail."
        elif i < 29:
            about[s] = fluff + "Its revenue comes from subscriptions to its own payroll software sold to mid-sized firms."
        elif i < 41:
            kept[s] = {"business": C.business_text({"summary": "Earns fees from IT projects delivered for clients.", "segments": [], "customers": "Banks"})}
        elif i < 45:
            about[s] = "The company provides staff augmentation to technology firms."
    return m, about, kept


def known_share(monkeypatch, r26: bool) -> tuple[int, dict]:
    m, about, kept = it_small_companies()
    if r26:      # R26's evidence: no business read, no earning sentences past the description's start, no model from stated words
        monkeypatch.setattr(C, "earning_lines", lambda *a, **k: "")
        monkeypatch.setattr(C, "model_from_words", lambda ev: "")
        monkeypatch.setattr(C, "stated_model", lambda ev: "")          # R37: the stated-words rule reads model_from_words' words itself (updated on purpose)
        kept = {}
    out, got = B.place_rest(copy.deepcopy(m), "IT services", about.get, ask=calls_ai([]), facts_of=lambda s: kept.get(s) or {})
    monkeypatch.undo()
    base = [f"B{i:02d}" for i in range(51)]
    return sum(1 for s in base if s in got["models"]), {"out": out, "got": got}


def test_more_stored_text_gives_more_small_companies_a_model(monkeypatch, capsys):
    before, _ = known_share(monkeypatch, r26=True)
    after, run = known_share(monkeypatch, r26=False)
    assert before == 14 and after == 45, (before, after)
    got = run["got"]
    assert got["models"]["B20"] == "software" and got["model_confidence"]["B20"] == "high"           # the sentence past the start
    assert got["models"]["B30"] == "project_services"                                                # the business read
    assert got["models"]["B42"] == "project_services" and got["model_confidence"]["B42"] == "medium"  # stated in so many words
    assert "B48" not in got["models"]
    with capsys.disabled():
        print(f"\nIT services, 51 small companies: known model before (R26 evidence) {before} of 51 ({before / 51:.0%}); "
              f"after (R27) {after} of 51 ({after / 51:.0%})")


def test_evidence_carries_the_business_read_and_the_earning_sentence():
    long = "Founded long ago by engineers with a vision. " * 8 + "Its revenue comes from licence fees on its own banking software."
    ev = C.model_evidence("IT - Software", long, business=C.business_text({"summary": "Sells core banking software.", "segments": [
        {"name": "Products", "what": "licences"}], "customers": "Banks"}))
    assert ev.startswith("Industry: IT - Software. Business: Sells core banking software. Products: licences. Customers: Banks.")
    assert "licence fees on its own banking software" in ev and len(ev) <= 420
    assert C.business_text(None) == "" and C.business_text({}) == ""
    assert C.model_evidence("x", "", earns="Its revenue comes from rent on its malls.") == "Industry: x. Its revenue comes from rent on its malls."
    assert C.model_from_words("Industry: IT. A CDMO serving innovators.") == "contract_manufacturing"
    assert C.model_from_words("Industry: Fabless chips. Sells products.") == ""                     # the industry alone is not its own words
    # R32 (updated on purpose): own words that it designs chips, with no fab of its own, now state fabless (theme_check.chip_designer)
    assert C.model_from_words("Industry: Fabless chips. Designs chips.") == "fabless"
    assert C.model_from_words("A fabless company and a CDMO.") == ""                               # two models: none


def test_the_facts_reader_adds_the_stored_business_read(monkeypatch):
    from app import db, deepdive
    from app.intel import theme_routes as T
    monkeypatch.setattr(deepdive, "stored", lambda s: {"business": {"summary": "Runs contact centres for telecom firms.",
                                                                   "segments": [{"name": "Voice", "what": "customer care"}]}})
    monkeypatch.setattr(T, "own_filings", lambda r, s: "")
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    f = T._facts_reader("IN")("XYZ")
    assert f["segments"] == ["Voice"] and f["business"] == "Runs contact centres for telecom firms. Voice: customer care."


# ---------- 4. no one-company layer; a label its evidence supports ----------
def it_with_a_visa_firm():
    proj = [co(f"PJ{i}", f"Projectly {i} Ltd", "delivers IT projects and consulting for clients", cap=90000 - i) for i in range(4)]
    mgd = [co(f"MG{i}", f"Runwell {i} Ltd", "runs clients' IT systems under managed services contracts", cap=50000 - i) for i in range(3)]
    visa = co("VIS", "Visaline Ltd", "runs visa and passport application centres and back-office processing for governments", cap=40000)
    return {"sector": "IT services", "summary": "", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
            "value_chain": [{"layer": "IT projects", "description": "Projects.", "companies": proj + [visa]},
                            {"layer": "Managed IT services", "description": "Run systems.", "companies": mgd}]}


def test_a_lone_company_never_gets_its_own_layer_and_a_consumer_label_needs_consumer_words():
    calls = []
    m = it_with_a_visa_firm()
    out, got = B.place_rest(copy.deepcopy(m), "IT services", lambda s: None,
                            ask=calls_ai(calls, said={"override": {"VIS": "consumer_services", "PJ0": "project_services"}}))
    assert not C.model_supported("consumer_services", "Industry: IT. Runs visa and passport application centres for governments.")
    assert C.model_supported("consumer_services", "Runs hotels and resorts.")
    assert got["models"]["VIS"] == "bpo"                                   # asked again with its evidence: back-office work for governments
    names = [v["layer"] for v in out["value_chain"]]
    assert "Hotels, travel and consumer services" not in names
    assert not any(len(v["companies"]) == 1 and not v.get("official") for v in out["value_chain"]), names
    home = next(v for v in out["value_chain"] if "VIS" in [c["ticker"] for c in v["companies"]])
    assert home.get("basis") == "rest" and home["layer"] == "Other IT service companies"


def test_a_lone_company_joins_the_largest_layer_of_its_family_when_there_is_one():
    proj = [co(f"PJ{i}", f"P {i}", "projects", cap=100 - i) for i in range(4)]
    mgd = [co(f"MG{i}", f"M {i}", "managed", cap=50 - i) for i in range(3)]
    soft = [co("SW0", "S 0", "software", cap=10), co("MGX", "M x", "managed", cap=9)]
    vc = [{"layer": "Projects", "companies": proj}, {"layer": "Managed", "companies": mgd}, {"layer": "Products", "companies": soft}]
    models = {**{c["ticker"]: "project_services" for c in proj}, **{c["ticker"]: "managed_services" for c in mgd}, "SW0": "software",
              "MGX": "managed_services"}
    out = B.by_model(vc, models, "IT")
    # "Products" keeps its software firm alone after the managed firm moves: SW0 has no layer of its family, so it goes to "Other"
    assert [v["layer"] for v in out] == ["Projects", "Managed", "Products", "Other IT companies"]
    assert out[2]["companies"] == [] and [c["ticker"] for c in out[3]["companies"]] == ["SW0"]
    assert out[1]["model"]["family"] == "services" and "MGX" in [c["ticker"] for c in out[0]["companies"] + out[1]["companies"]]


# ---------- RULES, prompts ----------
def test_rules_bumped_map_prompt_unchanged_and_new_segments_have_needs():
    assert B.RULES == 41 and A.MAP_V == 23          # lane s2-exact bumped RULES: exact replays of the live placement (updated on purpose); lane s1-fit bumped RULES: the split places by fit (updated on purpose); lane r2 bumped RULES: models stated by companies' own words, layers by kind of business (updated on purpose); lane r1 bumped RULES: foundry vs IDM, platform vs retail, off-industry companies (updated on purpose); q1 bumped RULES: telecom operators (updated on purpose); lane n2 bumped RULES: low-confidence models read again (updated on purpose); lane m1 bumped RULES: the materials rule and the merge rule reach kept checks (updated on purpose); R33 bumped RULES (updated on purpose); R31 bumped RULES: models made exact by the R31 boundaries, layers merged (updated on purpose)
    for new in ("bpo", "components", "fabless", "life_insurance", "general_insurance", "reinsurance", "property_development"):
        assert new in C.MODELS and new in C.MODEL_NEEDS and new in C.PLACE_SYSTEM2
    assert C.model_family("contract_manufacturing") != C.model_family("manufacturing") == C.model_family("fabless")
    assert C.model_family("components") != C.model_family("manufacturing")
    assert C.model_family("bpo") != C.model_family("project_services") == C.model_family("managed_services")
    assert len({C.model_family(x) for x in ("life_insurance", "general_insurance", "reinsurance", "underwriting")}) == 4
    assert set(C.MODEL_NEEDS) <= set(C.MODELS) and set(C.MODEL_WORDS) <= set(C.MODELS) and set(C.MODEL_SAYS) <= set(C.MODELS)
