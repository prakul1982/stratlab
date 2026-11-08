"""Release 26 (the live R25 decks' revenue models): each company's model rests on more of what the app keeps (official industry path, segment
names, filing titles beside its description), a model is kept only when that evidence shows it (else asked once more with the evidence, else
unknown), a layer with under half its companies' models known says so plainly instead of an "In common" line, a layer the split reshaped is
renamed when its name no longer fits how its companies earn, and a deck is never made on a map that is being written again (map_due -> 202).
Generic: synthetic themes only, India and the US; no name or figure tuned to a real company."""
import copy
import json
import threading

import pytest

from app.intel import ai as A
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_routes as T
from tests.test_export import texts
from tests.test_r18_deck import deck_of
from tests.test_r20_deck import test_every_rule_holds_on_every_synthetic_theme as every_rule
from tests.test_r25_class import co, it_mixed, layers_of
from tests.test_research_api import api  # noqa: F401


# ---------- a fake AI that gives a model only when the words it is sent show one ----------
SIGNS = [("resell", "hardware_resale"), ("marketplace", "platform"), ("commission", "platform"), ("managed", "managed_services"),
         ("outsourc", "managed_services"), ("consult", "project_services"), ("project", "project_services"), ("subscription", "software"),
         ("licen", "software"), ("makes its own", "manufacturing")]


def read_model(words: str) -> str:
    w = words.lower()
    return next((m for k, m in SIGNS if k in w), "unknown")


def fake_ai(calls: list, first: dict | None = None, again: dict | None = None, rename: dict | None = None):
    """The placement answer gives each symbol the model its words show (or `first`'s); the evidence re-ask gives `again`; the name check `rename`."""
    def ask(system, text):
        if system == C.NAMES_SYSTEM:
            calls.append(("names", json.loads(text.split("LAYERS:\n", 1)[1])))
            return {"rename": [{"layer": k, **v} for k, v in (rename or {}).items()]}
        if system == C.MODEL_SYSTEM:
            body = json.loads(text.split("EVIDENCE:\n", 1)[1])
            calls.append(("again", body))
            return {"models": {c["symbol"]: (again or {}).get(c["symbol"], "unknown") for c in body["companies"]}}
        body = json.loads(text.split("COMPANIES:\n", 1)[1])
        calls.append(("place", body))
        models = {}
        for lay in body["layers"].values():
            for mem in lay["members"]:
                sym = mem.split(" · ", 1)[0]
                models[sym] = read_model(mem.split(" · ", 1)[1])
        for c in body["companies"]:
            models[c["symbol"]] = read_model(f"{c['description']} {c.get('evidence') or ''}")
        models.update(first or {})
        return {"place": [{"symbol": c["symbol"], "layer": "L1"} for c in body["companies"]], "rename": [], "extra": [], "models": models}
    return ask


# ---------- 1. an IT-services-like theme: a 50-company projects layer with descriptions for only 8 ----------
def it_projects():
    """India: an outsourcing layer, a projects layer the map named 4 companies for, and 50 companies of the exchange's industry the map didn't
    place; 8 have a stored description, the rest only what the app keeps beside it (their industry path, segment names, filing titles)."""
    out = [co(f"OS{i}", f"Outsource {i} Ltd", "runs back offices for banks under multi-year managed service contracts", cap=900000 - i * 9000) for i in range(4)]
    proj = [co(f"PN{i}", f"Named {i} Ltd", "delivers digital engineering projects and consulting for clients", cap=80000 - i * 1000) for i in range(4)]
    base = [{"ticker": f"B{i:02d}", "name": f"Base {i} Ltd", "industry": "IT - Software", "cap": 50000 - i * 500, "base": True,
             "basis": "industry", "verified": False} for i in range(50)]
    m = {"sector": "IT services", "summary": "IT services.", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
         "value_chain": [{"layer": "Large-scale outsourcing and managed services", "description": "Run clients' systems for years.", "companies": out},
                         {"layer": "Digital engineering and consulting projects", "description": "Project work for clients.", "companies": proj},
                         {"layer": "IT - Software", "official": True, "basis": "industry", "description": "", "companies": base}]}
    about = {f"B{i:02d}": "The company delivers IT projects and consulting to clients." for i in range(8)}
    kept = {}
    for i in range(8, 50):
        if i < 34:
            kept[f"B{i:02d}"] = {"industry": "Information Technology > IT - Services > IT Consulting & Software", "segments": ["Digital projects"]}
        elif i < 46:
            kept[f"B{i:02d}"] = {"industry": "Information Technology > IT - Services > IT Enabled Services",
                                 "segments": ["Managed infrastructure services"], "filings": "Contract renewal for outsourced operations"}
    return m, about, kept


def run(m, about, kept=None, calls=None, **kw):
    calls = [] if calls is None else calls
    facts_of = (lambda s: kept.get(s) or {}) if kept is not None else None
    return B.place_rest(copy.deepcopy(m), "IT services", lambda s: about.get(s), ask=fake_ai(calls, **kw), facts_of=facts_of)


def summary(vc):
    return [(v["layer"], len(v["companies"]), (v.get("model") or {}).get("known"), bool((v.get("model") or {}).get("sparse"))) for v in vc]


def test_more_evidence_gives_most_companies_a_model_and_the_catch_all_splits_by_it():
    m, about, kept = it_projects()
    before, got0 = run(m, about)                           # R25: the stored descriptions only
    after, got1 = run(m, about, kept)                      # R26: with the industry path, segments and filings the app keeps
    assert sum(1 for x in got0["models"].values()) == 4 + 4 + 8
    assert sum(1 for x in got1["models"].values()) == 4 + 4 + 8 + 38
    lay0 = {v["layer"]: v for v in before["value_chain"]}
    big0 = [v for v in before["value_chain"] if v.get("model", {}).get("sparse")]
    assert big0, summary(before["value_chain"])            # before: the catch-all rests on a few, said plainly
    assert all(v["model"]["line"].startswith(("How they earn is shown for only", "None of these")) for v in big0)
    lay1 = {v["layer"]: v for v in after["value_chain"]}
    # after: the project firms and the managed-service firms apart; no layer above 40% of the theme with a split possible
    assert "Managed and outsourced services" in lay1 or any(v["model"]["id"] == "managed_services" for v in lay1.values() if v.get("model"))
    total = sum(len(v["companies"]) for v in after["value_chain"])
    assert total == sum(len(v["companies"]) for v in before["value_chain"]) == 58
    for v in after["value_chain"]:
        if not v.get("official"):
            assert not v["model"].get("sparse"), v["layer"]
            ids = {got1["models"].get(c["ticker"]) for c in v["companies"]} - {None}
            assert len(ids) == 1, (v["layer"], ids)                                     # one way of earning a layer
            assert len(v["companies"]) <= 0.4 * total or v.get("scale"), (v["layer"], len(v["companies"]))
    assert lay0 != lay1


def test_the_evidence_is_sent_once_with_the_placement_and_kept_with_the_map():
    m, about, kept = it_projects()
    calls = []
    out, got = run(m, about, kept, calls)
    place = [b for k, b in calls if k == "place"]
    assert len(place) == 1
    sent = {c["symbol"]: c for c in place[0]["companies"]}
    assert "Segments: Managed infrastructure services." in sent["B40"]["evidence"] and "IT Enabled Services" in sent["B40"]["evidence"]
    assert "Contract renewal for outsourced operations" in sent["B40"]["evidence"]
    assert "evidence" not in sent["B49"] or sent["B49"]["evidence"].startswith("Industry: IT - Software")     # nothing kept: its industry only
    again, got2 = B.place_rest(copy.deepcopy(m), "IT services", lambda s: about.get(s), ask=lambda s, t: pytest.fail("asked again"), kept=got,
                               facts_of=lambda s: kept.get(s) or {})
    assert layers_of(again["value_chain"]) == layers_of(out["value_chain"]) and got2 == got


def test_model_evidence_puts_industry_segments_description_and_filings_in_one_text():
    t = C.model_evidence("Financials > Banks > Private Sector Bank", "A bank that takes deposits.", ["Retail banking", "Treasury"], "From its own filings: Results.")
    assert t == "Industry: Financials > Banks > Private Sector Bank. Segments: Retail banking, Treasury. A bank that takes deposits. From its own filings: Results."
    assert C.model_evidence() == "" and len(C.model_evidence("x", "word " * 500)) <= 420


def test_a_layer_resting_on_under_half_its_companies_says_so_plainly_in_the_deck():
    region, m, f, models = it_mixed()
    sparse = {s: x for s, x in models.items() if s not in ("DC2", "HW2", "HW3")}         # 1 of the cloud layer's 4 models known
    vc = B.by_model(m["value_chain"], sparse, "IT services")
    mid = next(v for v in vc if v["layer"].startswith("Cloud"))
    assert mid["model"]["sparse"] and mid["model"]["known"] * 2 < mid["model"]["of"]
    # R27 (changed on purpose): the others are listed but left out of the layer's figures and rankings, said with how many and why
    assert mid["model"]["line"] == (f"How they earn is shown for only {mid['model']['known']} of these {mid['model']['of']} companies, mainly renting "
                                    "out computing, data-centre or network capacity, and connectivity subscriptions; the other 3 are listed but left out "
                                    "of this layer's figures and rankings, as their evidence doesn't show how they earn.")
    from app import deck
    assert deck.layer_common(mid) == mid["model"]["line"]
    assert deck.layer_common({"model": {"line": "They earn mainly from x.", "known": 3, "of": 4}}) == "In common: they earn mainly from x."
    m = {**m, "value_chain": vc}
    v, slides = deck_of(region, m, f)
    t = texts(slides)
    assert mid["model"]["line"] in t
    page = next(s for s in slides if s.title.startswith("Layer ") and "Cloud" in s.title)
    lines = [x for b in page.blocks if b["kind"] == "cards" for it in b["items"] for x in it["lines"]]
    assert not any(str(x).startswith("In common") for x in lines)
    every_rule("IT services, sparse models (IN)", v, slides)


# ---------- 2. a model is kept only when the evidence shows it ----------
@pytest.mark.parametrize("model,evidence,ok", [
    ("platform", "Runs a global network that delivers and secures websites, sold as subscriptions.", False),
    ("platform", "Industry: Software. Edge cloud platform for security and content delivery.", False),
    ("platform", "Runs an online marketplace that connects buyers and sellers and earns commissions.", True),
    ("platform", "Earns from advertising on its classifieds sites.", True),
    ("hardware_resale", "Designs and makes its own firewalls.", False),
    ("hardware_resale", "Resells and installs servers of global brands.", True),
    ("hardware_resale", "A systems integrator for data-centre equipment.", True),
    ("distribution", "Industry: Trading & Distributors.", True),
    ("lending", "Industry: Financials > Banks > Private Sector Bank.", True),
    ("lending", "Makes cement.", False),
    ("underwriting", "Industry: Life Insurance.", True),
    ("software", "", True),                       # a model with no need: any evidence
    ("made-up", "anything", False),
])
def test_model_supported_needs_words_of_its_kind(model, evidence, ok):
    assert C.model_supported(model, evidence) is ok


def cyber():
    """US: a network-security layer of makers, a cloud-delivered layer of two network-subscription firms the first answer calls platforms, an
    endpoint software layer, a marketplace firm and a hardware reseller among the companies the map didn't place, and a maker the first answer
    calls a reseller."""
    sw = "Software"
    makers = [co(f"NM{i}", f"Netwall {i} Inc", "designs and makes its own firewall appliances", sw, cap=90000 - i * 1000)
              for i in range(3)] + [co("MK2", "Boxguard Inc", "designs and makes its own network security appliances", sw, cap=40000)]
    edge = [co("CDN1", "Edgenet Inc", "runs a global network that delivers and protects websites and applications, sold to customers as subscriptions", sw, cap=70000),
            co("CDN2", "Fastlane Inc", "operates a cloud network that speeds up and secures internet traffic for business customers", sw, cap=60000)]
    endpoint = [co(f"EP{i}", f"Endpoint {i} Inc", "sells subscriptions for its own endpoint protection software", sw, cap=50000 - i * 1000) for i in range(4)]
    rest = [{"ticker": "MKT1", "name": "Bountyhub Inc", "industry": "Services-Prepackaged Software", "cap": 9000, "base": True, "basis": "industry"},
            {"ticker": "RS1", "name": "Securesell Inc", "industry": "Wholesale-Computers & Peripheral Equipment", "cap": 8000, "base": True, "basis": "industry"}]
    m = {"sector": "Cybersecurity", "summary": "Security.", "sub_themes": [], "tailwinds": [], "risks": [], "generated_at": 1.0,
         "value_chain": [{"layer": "Network security appliances", "description": "Firewalls and appliances.", "companies": makers},
                         {"layer": "Cloud-delivered security and edge networks", "description": "Security as a service over own networks.", "companies": edge},
                         {"layer": "Endpoint and detection platforms", "description": "Endpoint software.", "companies": endpoint},
                         {"layer": "Services-Prepackaged Software", "official": True, "basis": "industry", "description": "", "companies": rest}]}
    about = {"MKT1": "Runs an online marketplace where companies hire security researchers and earns a commission on each engagement.",
             "RS1": "Resells and installs security appliances made by other companies."}
    return m, about


def test_a_model_the_evidence_does_not_show_is_asked_again_once_then_left_unknown():
    m, about = cyber()
    calls = []
    first = {"CDN1": "platform", "CDN2": "platform", "MK2": "hardware_resale"}            # the R25 deck's mistake, and a maker called a reseller
    out, got = B.place_rest(copy.deepcopy(m), "Cybersecurity", about.get, ask=fake_ai(calls, first=first, again={"CDN1": "software", "CDN2": "platform",
                                                                                                                  "MK2": "manufacturing"}))
    again = [b for k, b in calls if k == "again"]
    assert len(again) == 1 and sorted(c["symbol"] for c in again[0]["companies"]) == ["CDN1", "CDN2", "MK2"]
    assert {c["symbol"]: c["was"] for c in again[0]["companies"]} == first
    assert "delivers and protects websites" in next(c["evidence"] for c in again[0]["companies"] if c["symbol"] == "CDN1")
    ms = got["models"]
    assert ms["CDN1"] == "software"                       # supported by its words: kept
    assert "CDN2" not in ms                               # "platform" again, still not in its words: unknown
    assert ms["MK2"] == "manufacturing" and ms["MKT1"] == "platform" and ms["RS1"] == "hardware_resale"
    lines = {v["layer"]: (v.get("model") or {}).get("line") for v in out["value_chain"]}
    assert not any("commissions, listing fees or advertising" in str(x) for k, x in lines.items() if k.startswith("Cloud-delivered")), lines
    # R27 (changed on purpose): the marketplace firm, alone in its model, is in "Other" with its model, not a one-company layer
    other = next(v for v in out["value_chain"] if v.get("basis") == "rest")
    assert {c["ticker"]: c["model"] for c in other["companies"] if c["ticker"] == "MKT1"} == {"MKT1": "platform"}
    assert not any(len(v["companies"]) == 1 and v.get("by_model") for v in out["value_chain"])


def test_when_the_ai_is_busy_on_the_second_ask_the_unshown_models_stay_unknown():
    m, about = cyber()
    calls = []
    base_ask = fake_ai(calls, first={"CDN1": "platform", "CDN2": "platform"})

    def ask(system, text):
        if system == C.MODEL_SYSTEM:
            raise C.AIError("busy")
        return base_ask(system, text)
    out, got = B.place_rest(copy.deepcopy(m), "Cybersecurity", about.get, ask=ask)
    assert "CDN1" not in got["models"] and "CDN2" not in got["models"] and got["models"]["MKT1"] == "platform"
    assert C.recheck_models([], ask, "x") == {}


# ---------- 3. a layer the split reshaped is renamed when its name no longer fits ----------
def test_a_reshaped_layer_whose_name_no_longer_fits_is_renamed_once_and_kept():
    _, m, _, models = it_mixed()
    todo = [{**c, "base": True} for c in m["value_chain"][-1]["companies"]]
    mapped = {**m, "value_chain": m["value_chain"][:4] + [{"layer": "Computers - Software & Consulting", "official": True, "basis": "industry",
                                                           "description": "", "companies": todo}]}
    calls = []
    # the cloud layer keeps only its data centres once the resellers move; the name check renames it (and tries a stand-in and a taken name)
    rename = {"L0": {"name": "Data-centre and hosting operators", "description": "They rent out computing capacity they run."}}

    def ask(system, text):
        if system == C.NAMES_SYSTEM:
            body = json.loads(text.split("LAYERS:\n", 1)[1])
            calls.append(("names", body))
            ids = {v["name"]: k for k, v in body["layers"].items()}
            out = [{"layer": ids["Cloud, AI infrastructure and hardware"], **rename["L0"]}]
            out += [{"layer": k, "name": "TBD", "description": ""} for k in body["layers"] if k != ids["Cloud, AI infrastructure and hardware"]]
            return {"rename": out}
        calls.append(("place", text))
        return {"place": [{"symbol": "PJX", "layer": "L1"}, {"symbol": "SV1", "layer": "none"}, {"symbol": "NOD", "layer": "none"}], "rename": [],
                "extra": [], "models": models}
    out, got = B.place_rest(mapped, "IT services", lambda s: None, ask=ask)
    names = [b for k, b in calls if k == "names"]
    assert len(names) == 1
    sent = {v["name"]: v for v in names[0]["layers"].values()}
    # only the map's layers the split reshaped are sent, each with how its companies earn; a layer it made or left alone is not
    assert "Cloud, AI infrastructure and hardware" in sent and "Large diversified outsourcers" not in sent and "Hardware resale and integration" not in sent
    assert sent["Cloud, AI infrastructure and hardware"]["how_they_earn"].startswith("They earn mainly from renting out computing")
    lay = {v["layer"]: v for v in out["value_chain"]}
    assert "Data-centre and hosting operators" in lay and lay["Data-centre and hosting operators"]["was"] == "Cloud, AI infrastructure and hardware"
    assert sorted(c["ticker"] for c in lay["Data-centre and hosting operators"]["companies"]) == ["DC1", "DC2"]
    assert not any(A.stand_in(k) for k in lay)
    assert got["model_names"]["rename"]["Cloud, AI infrastructure and hardware"]["name"] == "Data-centre and hosting operators"
    again, got2 = B.place_rest(mapped, "IT services", lambda s: None, ask=lambda s, t: pytest.fail("asked again"), kept=got)
    assert again == out and got2 == got
    quiet, _ = B.place_rest(mapped, "IT services", lambda s: None, kept=got)                  # no AI (a page waiting): the kept names
    assert "Data-centre and hosting operators" in [v["layer"] for v in quiet["value_chain"]]


def test_renamed_after_split_keeps_a_name_another_layer_has_and_only_touches_the_given_layers():
    vc = [{"layer": "A", "companies": []}, {"layer": "B", "companies": []}, {"layer": "C", "companies": [], "was": "Old C"}]
    out = B.renamed_after_split(vc, {"A", "C"}, {"A": {"name": "B", "description": ""}, "B": {"name": "Z", "description": ""},
                                                  "C": {"name": "New C", "description": "d"}})
    assert [v["layer"] for v in out] == ["A", "B", "New C"] and out[2]["was"] == "Old C" and out[2]["description"] == "d"


def test_no_reshaped_layer_means_no_name_check():
    vc = [{"layer": "Soft", "description": "", "companies": [co(f"S{i}", f"S{i}") for i in range(3)]},
          {"layer": "Proj", "description": "", "companies": [co(f"P{i}", f"P{i}") for i in range(3)]}]
    models = {**{f"S{i}": "software" for i in range(3)}, **{f"P{i}": "project_services" for i in range(3)}}
    out, got = B.place_rest({"value_chain": vc}, "x", lambda s: None,
                            ask=lambda s, t: pytest.fail("names asked") if s == C.NAMES_SYSTEM else {"models": models}, kept={"assign": {}})
    assert "model_names" not in got and [v["layer"] for v in out["value_chain"]] == ["Soft", "Proj"]


# ---------- 4. a deck never on a map that is being written again ----------
def fake_routes(maps, calls):
    class R:
        @staticmethod
        def sector_map(profile, region, q, refresh):
            calls.append("sector_map")
            return "IN", "x theme", maps[min(len(calls) - 1, len(maps) - 1)], []

        @staticmethod
        def theme_map(profile, region, q):
            return R.sector_map(profile, region, q, False)
    return R


def test_a_map_due_for_rewriting_answers_preparing_and_checks_nothing(monkeypatch):
    old = {"generated_at": 5.0, "map_v": A.MAP_V - 1, "value_chain": []}
    done = threading.Event()                              # the rewrite still running past the wait
    monkeypatch.setattr(T, "job_of", lambda key: {"state": "running", "done": done} if key[0] == "map" else None)
    monkeypatch.setattr(T, "checked", lambda *a: pytest.fail("a stale map checked"))
    calls, pending = [], []
    T.map_for_deck(fake_routes([old], calls), {}, "IN", "x theme", wait=0.05, pending=pending)
    assert pending == [True]
    # a rewrite that failed is no reason to make a file on the old map either: the next ask starts it again
    monkeypatch.setattr(T, "job_of", lambda key: {"state": "failed", "done": done} if key[0] == "map" else None)
    pending = []
    T.map_for_deck(fake_routes([old], []), {}, "IN", "x theme", wait=0.05, pending=pending)
    assert pending == [True]


def test_the_deck_waits_for_the_new_map_and_is_made_on_it(monkeypatch):
    old = {"generated_at": 5.0, "map_v": A.MAP_V - 1, "value_chain": [], "tag": "old"}
    new = {"generated_at": 9.0, "map_v": A.MAP_V, "value_chain": [], "tag": "new"}
    done = threading.Event()
    seen = []
    monkeypatch.setattr(T, "job_of", lambda key: {"state": "running", "done": done} if key[0] == "map" else None)
    monkeypatch.setattr(T, "checked", lambda r, theme, m: seen.append(m["tag"]) or {**m, "placements": {"checked": True}})
    monkeypatch.setattr(T, "with_descriptions", lambda r, m: m)
    threading.Timer(0.05, done.set).start()
    calls, pending = [], []
    r, theme, m = T.map_for_deck(fake_routes([old, new], calls), {}, "IN", "x theme", wait=5, pending=pending)
    assert m["tag"] == "new" and seen == ["new"] and calls == ["sector_map", "sector_map"]
    monkeypatch.setattr(T, "job_of", lambda key: None)
    assert pending == [False]
    # a library read (kept and checked already) is never held back by the map version
    lib = {**old, "_library": "x"}
    pending = []
    r, theme, m = T.map_for_deck(fake_routes([lib], []), {}, "IN", "x theme", wait=0.05, pending=pending)
    assert pending == [False] and m["tag"] == "old"


def test_the_deck_route_answers_202_on_a_stale_map_then_the_file(api, monkeypatch):    # noqa: F811
    import time

    from app.intel import routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    q = "/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf"
    r = None
    for _ in range(20):                                   # the theme's first map and its check, written in the background (R21)
        r = api.get(q)
        if r.status_code == 200:
            break
        time.sleep(0.3)
    assert r.status_code == 200 and api.usage.count("deck") == 1
    real_theme, real_sector = routes.theme_map, routes.sector_map
    state = {"stale": True}
    stale = lambda got: (*got[:2], {**got[2], "map_v": A.MAP_V - 1} if state["stale"] else got[2], got[3])       # noqa: E731
    monkeypatch.setattr(routes, "theme_map", lambda profile, region, q_: stale(real_theme(profile, region, q_)))
    monkeypatch.setattr(routes, "sector_map", lambda profile, region, q_, refresh: stale(real_sector(profile, region, q_, refresh)))
    r = api.get(q)
    assert r.status_code == 202 and r.json()["preparing"] is True and api.usage.count("deck") == 1
    state["stale"] = False
    r = api.get(q)
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"


# ---------- the report's before and after, on the synthetic sets ----------
def test_before_and_after_for_the_report(capsys, monkeypatch):
    m, about, kept = it_projects()
    before, _ = run(m, about)
    after, _ = run(m, about, kept)
    cm, cabout = cyber()
    first = {"CDN1": "platform", "CDN2": "platform", "MK2": "hardware_resale"}
    c_after, _ = B.place_rest(copy.deepcopy(cm), "Cybersecurity", cabout.get,
                              ask=fake_ai([], first=first, again={"CDN1": "software", "CDN2": "platform", "MK2": "manufacturing"}))
    monkeypatch.setattr(C, "model_supported", lambda model, evidence: model in C.MODELS)       # R25: every model the AI gave was kept
    raw, _ = B.place_rest(copy.deepcopy(cm), "Cybersecurity", cabout.get, ask=fake_ai([], first=first))
    assert any("commissions, listing fees" in str((v.get("model") or {}).get("line")) for v in raw["value_chain"] if v["layer"].startswith("Cloud"))
    with capsys.disabled():
        for title, vc in (("IT before", before), ("IT after", after), ("Cyber, no evidence check", raw), ("Cyber after", c_after)):
            print(f"\n{title}")
            for v in vc["value_chain"]:
                print(f"  {v['layer']} | {len(v['companies'])} | {(v.get('model') or {}).get('line') or ''}")
    assert summary(before["value_chain"]) != summary(after["value_chain"])


def test_rules_bumped_and_map_prompt_unchanged():
    assert B.RULES >= 26 and A.MAP_V == 23          # R27 bumps RULES again (tests/test_r27_class.py)
    assert "evidence" in C.PLACE_SYSTEM2 and "platform only with" in C.PLACE_SYSTEM2
    assert C.MODEL_MEMBERS >= 50 and set(C.MODEL_NEEDS) <= set(C.MODELS)


def test_place_in_layers_sends_member_and_company_evidence():
    seen = []
    layers = [{"layer": "A", "companies": [{"ticker": "X1", "name": "X one", "what": "runs things", "evidence": "Industry: Banks. Segments: Retail."}]}]
    C.place_in_layers(layers, [{"symbol": "Y1", "name": "Y one", "about": "d", "evidence": "Industry: Insurance."}],
                      lambda s, t: seen.append(json.loads(t.split("COMPANIES:\n", 1)[1])) or {}, "Finance")
    assert seen[0]["layers"]["L0"]["members"] == ["X1 · X one: runs things [evidence: Industry: Banks. Segments: Retail.]"]
    assert seen[0]["companies"][0]["evidence"] == "Industry: Insurance."
