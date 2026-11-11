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


# ---------- 3. a layer's cohort against the run before ----------
def test_a_layer_whose_cohort_fell_by_a_third_or_three_names_who_left_and_why():
    from app.intel import theme_data as D
    blocks = [{"layer": "Mobile and broadband operators", "companies": [
        {"symbol": s_, "name": n, "calc": {"in": s_ in ("BHARTIARTL", "BHARTIHEXA", "TTML"), "why": "" if s_ in ("BHARTIARTL", "BHARTIHEXA", "TTML")
                                                       else "way of earning not shown"}}
        for s_, n in (("JPL", "Jio Platforms Ltd"), ("BHARTIARTL", "Bharti Airtel Ltd"), ("BHARTIHEXA", "Bharti Hexacom Ltd"),
                      ("TTML", "Tata Teleservices (Maharashtra) Ltd"), ("MTNL", "Mahanagar Telephone Nigam Ltd"), ("IDEA", "Vodafone Idea Ltd"),
                      ("QUADRANT", "Quadrant Televentures Ltd"), ("CITYONLINE", "City Online Services Ltd"))]},
              {"layer": "Tower infrastructure", "companies": [{"symbol": "INDUSTOWER", "name": "Indus Towers Ltd", "calc": {"in": True, "why": ""}},
                                                              {"symbol": "RAILTEL", "name": "RailTel", "calc": {"in": True, "why": ""}}]}]
    from datetime import date
    now = D.cohort_point(blocks, date(2026, 11, 10))
    assert now["layers"]["Mobile and broadband operators"] == ["BHARTIARTL", "BHARTIHEXA", "TTML"]
    was = {"d": "2026-11-04", "layers": {"Mobile operators and broadband": ["BHARTIARTL", "BHARTIHEXA", "IDEA", "JPL", "MTNL", "RCOM"],
                                         "Tower infrastructure": ["INDUSTOWER"]},
           "names": {"JPL": "Jio Platforms Ltd", "IDEA": "Vodafone Idea Ltd", "MTNL": "Mahanagar Telephone Nigam Ltd", "RCOM": "Reliance Communications Ltd",
                     "BHARTIARTL": "Bharti Airtel Ltd", "BHARTIHEXA": "Bharti Hexacom Ltd", "INDUSTOWER": "Indus Towers Ltd"}}
    drops = D.cohort_drops([was, now], blocks)          # renamed layer: matched by the companies it held
    assert drops == [{"layer": "Mobile and broadband operators", "from": 6, "to": 3, "on": "2026-11-04", "left": [
        {"symbol": "JPL", "name": "Jio Platforms Ltd", "why": "way of earning not shown"},
        {"symbol": "MTNL", "name": "Mahanagar Telephone Nigam Ltd", "why": "way of earning not shown"},
        {"symbol": "RCOM", "name": "Reliance Communications Ltd", "why": "no longer in the theme"},
        {"symbol": "IDEA", "name": "Vodafone Idea Ltd", "why": "way of earning not shown"}]}]
    # a fall of a third or less and fewer than three is not said; nor a rise; nor a first run
    small = {**was, "layers": {"Mobile and broadband operators": ["BHARTIARTL", "BHARTIHEXA", "TTML", "JPL"]}}
    assert D.cohort_drops([small, now], blocks) == [] and D.cohort_drops([now], blocks) == []
    nine = {**was, "layers": {"Mobile and broadband operators": ["BHARTIARTL", "BHARTIHEXA", "TTML", "JPL", "IDEA", "MTNL", "X1", "X2", "X3"]}}
    blocks9 = copy.deepcopy(blocks)
    for c in blocks9[0]["companies"][:7]:
        c["calc"] = {"in": c["symbol"] not in ("JPL", "IDEA", "MTNL"), "why": "" if c["symbol"] not in ("JPL", "IDEA", "MTNL") else "other business"}
    six = D.cohort_point(blocks9 + [{"layer": "Other telecom companies", "companies": [{"symbol": "X1", "name": "X1 Ltd", "calc": {"in": True, "why": ""}}]}],
                         date(2026, 11, 10))
    got = D.cohort_drops([nine, six], blocks9 + [{"layer": "Other telecom companies", "companies": [{"symbol": "X1", "name": "X1 Ltd", "calc": {"in": True, "why": ""}}]}])
    assert got[0]["from"] == 9 and got[0]["to"] == 4 and {"symbol": "X1", "name": "X1 Ltd", "why": "moved to Other telecom companies"} in got[0]["left"]


def test_the_deck_says_a_fallen_cohort_on_the_data_confidence_page_and_the_gate_logs_it(caplog):
    import logging

    from app import deck
    from tests.test_n1_render import retail_like
    from tests.test_r18_deck import deck_of
    hist = []

    def kept(_, p):
        if not hist or hist[-1]["layers"] != p["layers"]:
            hist.append(p)
        return hist[-6:]
    region, m, f = retail_like(12, 5, 2)
    v1, _ = deck_of(region, m, f, cohort_history=kept)
    assert v1["checks"]["cohort"] == [] and len(hist) == 1
    lay = m["value_chain"][0]
    gone = [c for c in lay["companies"] if c["ticker"][1] == "R"][:5]
    for c in gone:
        c["model_out"] = "unknown"
    v2, slides = deck_of(region, m, f, cohort_history=kept)
    drops = v2["checks"]["cohort"]
    assert len(hist) == 2 and drops and drops[0]["from"] - drops[0]["to"] == 5
    assert {x["symbol"] for x in drops[0]["left"]} == {c["ticker"] for c in gone} and {x["why"] for x in drops[0]["left"]} == {"way of earning not shown"}
    page = next(s for s in slides if s.title == "Data confidence")
    rows = [r for b in page.blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict)]
    said = next(r for r in rows if r[0] == "Since the run before")
    assert f"{drops[0]['from']} in its calculations at the run of" in said[1] and "(way of earning not shown)" in said[1]
    with caplog.at_level(logging.WARNING, logger="stratlab.deck"):
        gate = deck.publication_gate(slides, v2)
    assert gate["cohort"] and any("deck gate: cohort:" in r.getMessage() for r in caplog.records)
    v3, _ = deck_of(region, m, f, cohort_history=kept)          # the same cohorts again: not kept twice, still said against the run before
    assert len(hist) == 2 and v3["checks"]["cohort"] == drops


# ---------- 5. a ranking states the capital figures that let it rank ----------
def test_a_ranked_value_chain_states_the_capital_per_revenue_figures_that_pass_the_rule():
    """The live R34 Chemicals chain: four layers ranked (capital per revenue 1.06 to 2.20, within threefold); R33's layers (with polymers and
    petrochemicals) were not. The rule is still applied to the new layers, and the page now shows the figures it passed on."""
    from app import deck
    from app.intel import theme_data as D
    rows = [{"layer": "Chlor-alkali and soda ash producers", "intensity": 1.31}, {"layer": "Basic organic intermediates", "intensity": 1.21},
            {"layer": "Fluorochemicals and refrigerants", "intensity": 1.51}, {"layer": "Custom synthesis manufacturers", "intensity": 2.2},
            {"layer": "Specialty and performance chemicals", "intensity": 1.06}]
    compared = ["Chlor-alkali and soda ash producers", "Basic organic intermediates", "Custom synthesis manufacturers", "Specialty and performance chemicals"]
    assert D.comparable_intensity([r for r in rows if r["layer"] in compared], lambda r: r["intensity"])
    chain = {"line": "Among the 4 layers ...", "highest": "Custom synthesis manufacturers", "lowest": "Basic organic intermediates", "compared": compared, "rows": rows}
    note = deck.intensity_note(chain)
    assert note.startswith("Capital for each unit of revenue") and "Custom synthesis manufacturers 2.20" in note and "Specialty and performance chemicals 1.06" in note
    assert "Fluorochemicals" not in note and "2.1 times the lowest, within the 3 times" in note
    # a layer three times as capital-hungry still stops the ranking (the rule, unchanged)
    assert not D.comparable_intensity([{"i": 1.0}, {"i": 3.2}], lambda r: r["i"])
    assert deck.intensity_note({**chain, "highest": None, "lowest": None}) == ""
