"""Lane q1-class (11 Nov): the GPT review of the live R34 decks.
1. Telecom: every operator was "software" (the layer's line "licences and subscriptions for software they own") and Jio Platforms and
   Vodafone Idea were left out at "low". A network operator's subscriptions are telecom_services, its own model and family; its customers
   named ("to wireless telecom operators") are never its model.
2. Semiconductors: GlobalFoundries sat in "Other semiconductor companies" as TSMC and UMC were called makers of their own products, so no
   layer was a contract maker's. Foundry words (and OSAT words) make a contract maker; the foundry layer takes GlobalFoundries."""
import copy

from app.intel import metric_registry as MR
from app.intel import theme_base as B
from app.intel import theme_check as C

TEL = "Telecommunication > Telecom Services > Telecom - Cellular & Fixed line services"
# the live R34 shapes (their stored descriptions as the dive shows them)
OPERATORS = {
    "JPL": (TEL, "Incorporated in November 2019, JPL is the parent entity of RJIL. RIL holds 66.43% stake in JPL. The company has created an "
                 "ecosystem, comprising networks, devices, applications and content to provide seamless services. Business Overview: Jio "
                 "Platforms Ltd (JPL) holds Reliance Industries' telecom and digital services businesses. Its wholly owned subsidiary, Reliance "
                 "Jio Infocomm (RJIL), runs the mobile and home broadband business, while JPL handles digital services, technology platforms "
                 "and enterprise solutions."),
    "BHARTIARTL": ("", "Bharti Airtel Ltd is one of the world's leading providers of telecommunication services with presence in 18 countries."),
    "BHARTIHEXA": ("", "Incorporated in 1995, Bharti Hexacom Ltd provides consumer mobile services, fixed- line telephone and broadband services "
                       "in Rajasthan and Northeast telecom circles."),
    "TTML": ("", "Tata Teleservices Ltd is engaged in the business of Wired and wireless telecommunication activities and holds a Unified "
                 "License with Access Service Authorisation in Maharashtra and Goa."),
    "MTNL": ("", "Mahanagar Telephone Nigam Ltd is a Government of India-controlled telecom and infrastructure-asset company serving Delhi and "
                 "Mumbai through landline, broadband/FTTH, mobile, leased-line and enterprise services."),
    "IDEA": ("", "Vodafone Idea is one of the leading telecom service providers in India."),
    "QUADRANT": (TEL, ""),
}
NOT_OPERATORS = {
    "ROUTE": ("Telecommunication > Other Telecom Services", "Route Mobile Limited is a cloud communications platform service provider catering "
                                                             "to enterprises, OTT players, and mobile network operators (MNOs)."),
    "INDUSTOWER": ("Telecommunication > Telecom - Infrastructure", "It leases tower space mainly to wireless telecom operators on a shared basis "
                                                                    "under long-term contracts."),
    "GTLINFRA": ("Telecommunication > Telecom - Infrastructure", "GTL Infrastructure Ltd provides passive telecom infrastructure sharing and "
                                                                  "energy management solutions."),
    "SAAS": ("Services-Prepackaged Software", "It provides subscription software to telecom operators and enterprises."),
    "EQIX": ("Real Estate Investment Trusts", "It operates colocation data centers and interconnection services."),
}


def _ev(ind, about):
    return C.model_evidence(ind, about)


# ---------- 1. telecom operators ----------
def test_an_operators_subscriptions_are_telecom_services_never_software():
    assert C.MODELS["telecom_services"][0] == "telecom_services" and "software" not in C.MODELS["telecom_services"][2]
    assert "connectivity subscriptions" not in C.MODELS["capacity"][2]
    for s_, (ind, about) in OPERATORS.items():
        ev = _ev(ind, about)
        assert C.telecom_operator(ev), s_
        for was in ("software", "capacity", "unknown"):
            assert C.refine_model(was, ev) == "telecom_services", (s_, was)
        assert C.model_supported("telecom_services", ev) and C.model_confidence("telecom_services", ev) in ("high", "medium"), s_
    for s_, (ind, about) in NOT_OPERATORS.items():
        ev = _ev(ind, about)
        assert not C.telecom_operator(ev), s_
        assert C.refine_model("software", ev) == "software" and C.refine_model("capacity", ev) == "capacity", s_
    # a US wireless carrier by its SEC industry and its words
    assert C.refine_model("software", _ev("Radiotelephone Communications", "It provides wireless services to customers.")) == "telecom_services"
    # a model that isn't software, capacity or unknown is never changed (a tower landlord, an equipment maker)
    assert C.refine_model("property", _ev(TEL, "It provides mobile services.")) == "property"
    # the model's own words in a layer's name; customers named are not its model
    assert C.model_from_words("Mobile and broadband operators") == "telecom_services"
    assert C.model_from_words(_ev(*NOT_OPERATORS["ROUTE"])) != "telecom_services"
    assert "telecom_services" in C.MODEL_SYSTEM and "telecom_services" in C.PLACE_SYSTEM2 and "telecom_services" in C.KEEP_APART


def test_the_kept_live_telecom_placement_puts_every_operator_with_words_in_the_layers_figures():
    """The live R34 placement as kept: the AI's answer gave every operator "software", five of them at "low". Worked out again with no AI
    call, the operators are telecom_services, the low ones read from their own evidence (at most "medium"), and the layer's line says how
    operators earn."""
    ops = list(OPERATORS)
    m = {"value_chain": [
        {"layer": "Mobile and broadband operators", "description": "Operators sell connectivity through subscription plans.",
         "companies": [{"ticker": s_, "name": s_, "cap": 100 - i, "what": OPERATORS[s_][1][:200]} for i, s_ in enumerate(ops)]},
        {"layer": "Network equipment makers", "description": "They make network gear.",
         "companies": [{"ticker": t, "name": t, "cap": 5, "what": "It designs and manufactures wireline and wireless networking products."}
                       for t in ("TEJASNET", "ITI")]}]}
    low = {"JPL", "MTNL", "QUADRANT", "IDEA"}
    kept = {"assign": {}, "models": {**{s_: "software" for s_ in ops}, "TEJASNET": "manufacturing", "ITI": "manufacturing"},
            "model_confidence": {**{s_: "low" if s_ in low else "medium" for s_ in ops}, "TEJASNET": "high", "ITI": "high"}}
    facts = {s_: {"industry": OPERATORS[s_][0]} for s_ in ops}
    about = {s_: OPERATORS[s_][1] for s_ in ops}
    out, got = B.place_rest(copy.deepcopy(m), "Telecom", lambda s_: about.get(s_, ""), ask=None, kept=kept, facts_of=lambda s_: facts.get(s_) or {})
    lay = next(v for v in out["value_chain"] if v["layer"] == "Mobile and broadband operators")
    assert lay["model"]["id"] == "telecom_services" and lay["model"]["family"] == "telecom_services"
    assert lay["model"]["known"] == len(ops) and not lay["model"].get("sparse") and not any(c.get("model_out") for c in lay["companies"])
    assert lay["model"]["line"] == ("They earn mainly from subscriptions and usage charges for mobile, broadband and fixed-line services on "
                                    "networks they run.")
    assert all(got["model_confidence"][s_] in ("high", "medium") for s_ in ops) and got["models"]["JPL"] == "telecom_services"
    gear = next(v for v in out["value_chain"] if v["layer"] == "Network equipment makers")
    assert gear["model"]["id"] == "manufacturing" and {c["ticker"] for c in gear["companies"]} == {"TEJASNET", "ITI"}


def test_a_rule_made_model_of_another_family_is_not_held_at_the_answers_low():
    assert B.said_for("telecom_services", "software", "low") == "medium"
    assert B.said_for("telecom_services", "software", "high") == "high"
    assert B.said_for("fabless", "manufacturing", "low") == "low"            # same family: the answer's word still holds
    assert B.said_for("software", "software", "low") == "low"


def test_telecom_operators_are_an_asset_heavy_family_with_no_software_contract_figures():
    tags = MR.tags("IN", {"profile": "other", "industry": TEL.split(" > ")}, "telecom_services")
    assert "telecom_services" in tags and "software" not in tags
    us = MR.tags("US", {"profile": "other", "industry": ["Radiotelephone Communications"]}, "telecom_services")
    assert MR.applies("rpo_cover", "US", MR.tags("US", {"profile": "other"}, "software")) and not MR.applies("rpo_cover", "US", us)
    assert "telecom_services" in MR.ASSETS_HEAVY and MR.main_family([{"telecom_services"}, {"telecom_services", "telecom"}]) == "telecom_services"


# ---------- 2. foundries ----------
SEMI = "Manufacturing > Semiconductors & Related Devices"
FOUNDRIES = {
    "TSM": "As a foundry, we manufacture semiconductors using our manufacturing processes for our customers based on proprietary integrated "
           "circuit designs provided by them.",
    "UMC": "United Microelectronics Corporation is a leading global semiconductor foundry company, providing wafer manufacturing services.",
    "GFS": "GlobalFoundries Inc. is a multinational semiconductor technology development, design and contract manufacturing company domiciled in "
           "the Cayman Islands and headquartered in Malta, New York.",
    "TSEM": "Tower Semiconductor is an independent specialty foundry that manufactures integrated circuits using specialty process technologies.",
    "AMKR": "Amkor Technology, Inc. is an American semiconductor product packaging and test services provider.",
}
NOT_FOUNDRIES = {
    "INTC": "Intel Corporation designs, manufactures, and sells computer components such as central processing units (CPUs). Intel Foundry "
            "provides foundry services.",
    "AMAT": "Applied Materials provides manufacturing equipment, services and software to the semiconductor industry; customers include "
            "semiconductor foundries and memory makers.",
    "NVDA": "NVIDIA designs GPUs and relies on third-party foundries such as TSMC to manufacture them.",
    "MU": "Micron manufactures DRAM and NAND memory in its own fabs.",
}


def test_foundry_words_make_a_contract_maker_and_its_customers_or_suppliers_words_do_not():
    for s_, t in FOUNDRIES.items():
        ev = _ev(SEMI, t)
        assert C.foundry(ev), s_
        assert C.refine_model("manufacturing", ev) == "contract_manufacturing" and C.refine_model("unknown", ev) == "contract_manufacturing", s_
    for s_, t in NOT_FOUNDRIES.items():
        assert not C.foundry(_ev(SEMI, t)), s_
        assert C.refine_model("manufacturing", _ev(SEMI, t)) != "contract_manufacturing", s_
    assert C.refine_model("fabless", _ev(SEMI, NOT_FOUNDRIES["NVDA"])) == "fabless"


def test_the_foundry_layer_takes_globalfoundries_out_of_other():
    """The live R34 Semiconductors placement as kept: TSMC, UMC and Tower "manufacturing" in "Foundry and memory manufacturing" beside Micron
    and Intel; GlobalFoundries "contract_manufacturing" in the "Other" group, alone in its family, so a layer of one went back to "Other"."""
    about = {**FOUNDRIES, **NOT_FOUNDRIES, "QRVO": "Qorvo makes RF chips in its own fabs.", "IPGP": "IPG Photonics manufactures fiber lasers.",
             "KOPN": "Kopin manufactures microdisplays."}
    m = {"value_chain": [
        {"layer": "Makers of their own products", "companies": [{"ticker": t, "name": t, "cap": 10} for t in ("QRVO", "IPGP", "KOPN")]},
        {"layer": "Foundry and memory manufacturing", "companies": [{"ticker": t, "name": t, "cap": c} for t, c in
                                                                    (("TSM", 900), ("MU", 100), ("INTC", 90), ("UMC", 20), ("TSEM", 5))]},
        {"layer": "Other semiconductor companies", "official": True, "basis": "rest", "companies": [{"ticker": "GFS", "name": "GFS", "cap": 21}]}]}
    models = {"TSM": "manufacturing", "MU": "manufacturing", "INTC": "manufacturing", "UMC": "manufacturing", "TSEM": "manufacturing",
              "GFS": "contract_manufacturing", "QRVO": "manufacturing", "IPGP": "manufacturing", "KOPN": "manufacturing"}
    conf = {s_: "medium" for s_ in models}
    models, conf = B.refine_kept(models, conf, lambda s_: _ev(SEMI, about.get(s_, "")), list(models))
    assert all(models[s_] == "contract_manufacturing" for s_ in ("TSM", "UMC", "TSEM", "GFS")) and models["MU"] == models["INTC"] == "manufacturing"
    vc = B.by_model(m["value_chain"], models, "Semiconductors", confidence=conf, evidence_of=lambda s_: _ev(SEMI, about.get(s_, "")))
    fdy = next(v for v in vc if v["layer"] == "Foundry and memory manufacturing")
    assert {c["ticker"] for c in fdy["companies"]} == {"TSM", "UMC", "TSEM", "GFS"} and fdy["model"]["id"] == "contract_manufacturing"
    assert not any(c["ticker"] == "GFS" for v in vc if v.get("basis") == "rest" for c in v["companies"])
    makers = next(v for v in vc if v["layer"] == "Makers of their own products")
    assert {"MU", "INTC"} <= {c["ticker"] for c in makers["companies"]}


# ---------- 4. one deduplicated list for every count ----------
def test_the_live_twin_listings_collapse_and_every_count_reads_the_same_list():
    """The live R34 Consumer retail dive: Leslie's, Inc. as LESL ($1.0 m) and LESLQ ($0.68 m), the same filed revenue; Baozun with margins
    but no revenue or profit (counted "with figures" by the appendix, 97, but not by page 4, 96)."""
    from app.intel import theme_data as D
    from tests.test_n1_render import retail_like
    from tests.test_r18_deck import deck_of
    rows = [{"symbol": "LESL", "name": "Leslie's, Inc.", "revenue": 1241.91, "cap": 1.0}, {"symbol": "LESLQ", "name": "Leslie's, Inc.", "revenue": 1241.91, "cap": 0.68},
            {"symbol": "LESLX", "name": "Leslie's Inc", "revenue": 1241.91, "cap": None}]
    assert [r["symbol"] for r in D.one_row_each(rows)] == ["LESL"]
    region, m, f = retail_like(12, 5, 2)
    first = m["value_chain"][0]["companies"][0]
    twin = {**copy.deepcopy(first), "ticker": first["ticker"] + "Q"}
    m["value_chain"][0]["companies"].append(twin)
    f[twin["ticker"]] = {**copy.deepcopy(f[first["ticker"]]), "symbol": twin["ticker"], "market_cap": f[first["ticker"]]["market_cap"] * 0.68}
    bz = m["value_chain"][0]["companies"][1]["ticker"]
    f[bz] = {**f[bz], "report_currency": "CNY"}           # live Baozun: reports in yuan, no rate kept: its margins stand, its money figures out
    v, slides = deck_of(region, m, f)
    import re
    said = [int(re.match(r"(\d+) confirmed compan", s.subtitle or "").group(1)) for s in slides
            if s.title.startswith("Every company's figures") and re.match(r"(\d+) confirmed compan", s.subtitle or "")]
    rows_ = [r[0] for s in slides if s.title.startswith("Every company's figures") for b in s.blocks if b["kind"] == "table"
             for r in b["rows"] if not isinstance(r, dict)]
    assert said and set(said) == {v["with_figures"]} == {len(rows_)}, (said, v["with_figures"], len(rows_))
    assert len(rows_) == len(set(rows_))
