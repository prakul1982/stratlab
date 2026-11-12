"""Lane d1 (the final theme-deck round; the outside review of the 14 live Release 41 decks, lanes11/r41-deck-review.md): coverage honesty,
headline rules, layer pages and the placement rules of RULES 43, each on a synthetic case. Facts only: no figure or name is tuned to a real
company; the exact replays of the live inputs (tests/test_exact_replay.py) list every company the rules move, with why."""
import importlib.util
import os

from app import deck
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests.test_r18_deck import deck_of
from tests.test_theme1 import facts


_spec = importlib.util.spec_from_file_location("deck_check", os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "deck_check.py"))
deck_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deck_check)


def co(sym, name, what="", industry="", base=True, verified=True, **kw):
    return {"ticker": sym, "name": name, "what": what, "industry": industry, "base": base, "basis": "industry" if base else "added",
            "verified": verified, **kw}


def placements(n):
    return {"checked": True, "pending": 0, "placed": n, "total": n, "base": n, "named": 0, "added": 0, "confirmed": 0}


# ---------- A. coverage honesty ----------
def _map_with_rest():
    own = [{"layer": "Pump makers", "description": "Make pumps for farms and factories.",
            "companies": [co(f"P{i}", f"Pump {i} Ltd", "makes pumps", "Pumps") for i in range(3)]}]
    rest = [{"layer": "Diversified", "official": True, "basis": "industry", "description": "",
             "companies": [co("Q1", "Quiet Holdings Ltd", "", "Diversified", verified=False), co("Q2", "Two Ltd", "", "Diversified", verified=False)]}]
    subs = [{"name": "Water", "detail": "", "companies": [co("S1", "Sub Only Ltd", "makes pumps", "Engines", base=False)]}]
    return {"sector": "Pumps", "value_chain": own + rest, "sub_themes": subs, "placements": placements(6)}


def test_a_company_named_in_a_sub_theme_only_is_placed_and_never_in_no_layer():
    """The live R41 decks listed SAIL, GAIL, MercadoLibre, O'Reilly and Etsy in no layer and not in "Other" (layer "–")."""
    about = {"S1": "Sub Only Ltd makes pumps for farms.", "Q1": "Quiet Pump Ltd sells insurance.", "Q2": ""}
    out, got = B.place_rest(_map_with_rest(), "Pumps", about.get, ask=None)
    where = {c["ticker"]: v["layer"] for v in out["value_chain"] for c in v["companies"]}
    assert where["S1"] == "Pump makers"                      # placed by its words like one of the theme's own
    assert set(where) >= {"P0", "P1", "P2", "Q1", "Q2", "S1"}
    # a map with no layers of its own: the company is in "Other", never in neither
    m = {"sector": "Pumps", "value_chain": [{"layer": "Pumps", "official": True, "basis": "industry", "companies": [co("Q1", "Quiet Pump Ltd")]}],
         "sub_themes": [{"name": "Water", "companies": [co("S1", "Sub Only Ltd", base=False)]}]}
    got_m = B.with_sub_only(m, "Pumps")
    assert any(v.get("basis") == "rest" and [c["ticker"] for c in v["companies"]] == ["S1"] for v in got_m["value_chain"])
    members = T.members_of(m, {"layers": [], "subs": []})
    assert "Named in a sub-theme only" not in {x["layer"] for x in members}
    assert next(x for x in members if x["symbol"] == "S1").get("rest")


def test_a_company_with_no_words_in_no_layer_is_not_checked_yet_and_the_coverage_says_so_apart():
    """The live R41 IT deck: "In no layer 115 of 252" counted 82 companies never read as fitting none of the map's layers."""
    about = {"Q1": "Quiet Holdings Ltd sells insurance policies."}
    out, _ = B.place_rest(_map_with_rest(), "Pumps", about.get, ask=None)
    rest = next(v for v in out["value_chain"] if v.get("basis") == "rest")
    marks = {c["ticker"]: bool(c.get("unread")) for c in rest["companies"]}
    assert marks == {"Q1": False, "Q2": True}
    v = {"members": [{"symbol": "A", "layer": "L"}, {"symbol": "B", "layer": "Other x", "rest": True},
                     {"symbol": "C", "layer": "Other x", "rest": True, "unread": True}], "layers": []}
    rc = deck.rest_count(v)
    assert rc == (2, 3, "Other x", 1)
    words = deck.rest_words(rc, v)
    assert "1 of 3 fit none of the map's layers" in words and "1 not checked yet" in words
    # deck_check flags only the share that fits none
    page = f"In no layer   2 of 3   {words}"
    got = deck_check.check_pages([page])
    assert got["counts"]["other>40%"] == 0
    assert deck_check.check_pages(["In no layer 3 of 4 in “Other”, listed, never compared: 3 of 4 fit none of the map's layers"])["counts"]["other>40%"] == 1


def test_deck_check_fails_a_company_of_the_appendix_in_no_layer():
    head = " Company                         Layer                     Market value   Revenue   Growth"
    ok = " Alpha Ltd                       Pump makers                 ₹100 cr      ₹50 cr    +5%"
    bad = " Beta Ltd                        –                           ₹90 cr       ₹40 cr    +4%"
    wrapped = "                                 –                           ₹90 cr       ₹40 cr    +4%"
    page = "Every company's figures (1 of 1)\n" + "\n".join([head, ok, wrapped, bad])
    got = deck_check.check_pages([page])
    assert got["counts"]["no layer"] == 1 and "Beta Ltd" in got["findings"][0]["text"]


# ---------- B. headline rules ----------
def _block(name, ebitda, n=6, scale=None, roe=None):
    rows = [{"symbol": f"{name[:2]}{i}", "name": f"{name} {i}", "revenue": 100.0, "ebitda": ebitda, "net": 5.0, "roce": 10.0, "year": "Mar 2026",
             "status": "core", "roe": roe, "company_wide": False} for i in range(n)]
    b = D.layer_block(name, rows, set())
    b.update(model={"id": "manufacturing", "family": "making"}, official=False, basis=None)
    if scale:
        b["scale"] = scale
    return b


def test_a_half_of_a_layer_split_by_market_value_is_never_ranked_on_its_own():
    """The live R41 Banks deck's headline set "(larger)", one half of a layer split by market value, against another layer."""
    blocks = [_block("Makers (larger)", 20.0, scale="larger"), _block("Makers (smaller)", 12.0, scale="smaller"), _block("Assemblers", 9.0),
              _block("Fitters", 15.0)]
    got = D.chain_table(blocks)
    assert set(got["compared"]) == {"Assemblers", "Fitters"}
    assert "highest in Makers" not in (got["line"] or "") and "lowest in Makers" not in (got["line"] or "")
    assert any(u["why"] == D.RANK_WHY["half"] for u in got["unranked"])


def test_no_comparison_on_a_gap_under_a_point():
    """The live R41 Banks deck: "13.5% vs 13.3%, a gap of 0.2 points" as its headline."""
    blocks = [_block("Lenders A", None, roe=13.5), _block("Lenders B", None, roe=13.3)]
    for b in blocks:
        b["model"] = {"id": "lending", "family": "lending"}
    got = D.chain_table(blocks)
    assert got["highest"] is None and got["lowest"] is None
    assert "no layer stands apart" in got["line"]
    rows = [("A", 10.4, 6, 6), ("B", 10.0, 6, 6)]
    assert D.rank_pair(rows, lambda t: t[1], lambda t: t[2], of=lambda t: t[3]) is None
    assert D.rank_pair([("A", 11.5, 6, 6), ("B", 10.0, 6, 6)], lambda t: t[1], lambda t: t[2], of=lambda t: t[3]) is not None


def test_the_peer_pe_gap_is_said_only_against_named_like_for_like_peers():
    """The live R41 Banks, Insurance and Cybersecurity decks: "50.4% below peers' 22.6x" with no peer named, peers of the broad sector."""
    rows = [{"symbol": f"T{i}", "pe": 20.0, "cap": 1000.0, "sector": "Fin", "map_industry": "Insurers", "region": "IN"} for i in range(4)]
    other = [{"symbol": f"M{i}", "name": f"Lender {i} Ltd", "pe": 30.0, "market_cap": 1000.0, "sector": "Fin", "industry": "Lenders"} for i in range(12)]
    got = D.peers_section(rows, other)["pe"]
    assert got["like"] is False and got["names"][:1] == ["Lender 0 Ltd"]
    val = {"pe": {"n": 4, "median": 20.0, "min": 20.0, "max": 20.0}, "peers": {"pe": got}}
    assert not D.relative_ok(val)                                   # descriptive: no gap stated
    assert "mostly of other industries, so no relative figure" in deck.descriptive_line(val)
    same = [{**m, "industry": "Insurers"} for m in other]
    like = D.peers_section(rows, same)["pe"]
    assert like["like"] is True and D.relative_ok({**val, "peers": {"pe": like}})
    assert "peers most used: Lender 0" in deck.pe_peer_line(like)


# ---------- C. layer pages ----------
def _long_theme():
    big = [co(f"BG{i}", f"Big Layer Company Number {i} Limited", "manufactures heavy industrial gear", "Heavy Electrical Equipment and Machinery")
           for i in range(12)]
    two = [co(f"TW{i}", f"Two Co {i} Ltd", "runs data centres", "Data Processing Services") for i in range(2)]
    one = [co("ON0", "One Co Ltd", "leases towers", "Telecom Towers")]
    desc = ("These companies design, make and service heavy industrial gear for power plants, steel mills and refineries. Margins depend on "
            "order books, input costs and execution. Working capital is high and long contracts carry penalties for delays.")
    m = {"sector": "Gear", "summary": "", "sub_themes": [], "tailwinds": [], "risks": [], "placements": placements(15), "generated_at": 1.0,
         "value_chain": [{"layer": "Heavy gear makers", "description": desc, "companies": big},
                         {"layer": "Data centres", "description": "Run data centres.", "companies": two},
                         {"layer": "Towers", "description": "Lease towers.", "companies": one}]}
    f = {}
    for i, c in enumerate(big + two + one):
        f[c["ticker"]] = facts(c["ticker"], c["name"], [900, 1000, 1100, 1200 + i], [15, 16, 17, 18 + i % 3], [60, 70, 80, 90], cap=50000 - i * 900)
    return "IN", m, f


def test_a_layer_page_shows_at_least_five_companies_and_small_layers_share_one_page():
    """The live R41 decks: "The largest 1 of 78 by market value"; IT's and Cybersecurity's 2-company layers each a page of "– (2)"."""
    _, slides = deck_of(*_long_theme())
    page = next(s for s in slides if s.title.endswith("Heavy gear makers"))
    tab = next(b for b in page.blocks if b["kind"] == "table")
    shown = [r for r in tab["rows"] if not isinstance(r, dict) and not str(r[0]).startswith(("Median", "Range"))]
    assert len(shown) >= deck.LAYER_ROWS_MIN
    assert not any(s.title.endswith(("Data centres", "Towers")) for s in slides)
    small = next(s for s in slides if s.title.startswith(deck.SMALL_TITLE))
    rows = [r for b in small.blocks if b["kind"] == "table" for r in b["rows"]]
    assert len(rows) == 3 and [r[0] for r in rows].count("") == 1          # the 2-company layer said on its first row
    assert "2 layers of 2 confirmed companies or fewer, 3 companies" in small.subtitle


# ---------- D. placement rules (RULES 43) ----------
def _vc(*layers):
    return [{"layer": n, "description": d, "companies": cs} for n, d, cs in layers]


def test_a_map_named_company_of_a_way_of_earning_no_layer_has_stays_in_its_layer():
    """The live R41 Cybersecurity deck: Fortinet, the map's own pick for its network security layer, in "Other" (read as a maker)."""
    vc = _vc(("Network security", "Firewalls and subscriptions.", [co("PA", "Pa Net"), co("CK", "Ck Point"),
                                                                   co("FT", "Ft Net", "develops and sells network security firewalls")]),
             ("Identity", "Identity software.", [co("OK", "Ok Id"), co("CY", "Cy Id")]))
    vc.append({"layer": "Other security companies", "official": True, "basis": "rest", "description": "", "companies": []})
    models = {"PA": "software", "CK": "software", "FT": "manufacturing", "OK": "software", "CY": "software"}
    out = B.by_model(vc, models, "Security")
    where = {c["ticker"]: (v["layer"], c.get("model_out")) for v in out for c in v["companies"]}
    assert where["FT"] == ("Network security", "other")
    # one whose words don't say what the layer's name says goes to "Other" as before (a materials supplier in an equipment layer: lane m1)
    vc[0]["companies"][2] = co("FT", "Ft Net", "supplies specialty chemicals and gases")
    out = B.by_model(vc, models, "Security")
    assert next(v for v in out for c in v["companies"] if c["ticker"] == "FT").get("basis") == "rest"


def test_retail_chains_the_largest_s_name_does_not_describe_make_a_layer_of_their_industry():
    """The live R41 Consumer retail deck: Gap, Abercrombie, Urban Outfitters in "Off-price, dollar and discount store chains" by their
    industry, American Eagle and Buckle in "Other"."""
    ind = "Retail-Family Clothing Stores"
    off = [co(f"OP{i}", f"Offprice {i}", "", ind) for i in range(4)] + [co(f"DS{i}", f"Dollar {i}", "", "Retail-Variety Stores") for i in range(2)]
    web = [co(f"WB{i}", f"Web {i}", "", "Retail-Catalog & Mail-Order Houses") for i in range(5)]
    club = [co(f"CL{i}", f"Club {i}", "", "Retail-Variety Stores") for i in range(3)]
    chains = [co(f"AP{i}", f"Apparel Chain {i}", "", ind, placed="ai") for i in range(3)]
    plain = [co(f"NM{i}", f"No Model Chain {i}", "", ind, placed="ai") for i in range(2)]
    vc = _vc(("Off-price and dollar stores", "Resell others' goods at low prices.", off), ("Online retailers", "Sell online.", web),
             ("Warehouse clubs", "Large stores, membership fees.", club))
    vc.append({"layer": "Other retail companies", "official": True, "basis": "rest", "description": "", "companies": chains + plain})
    words = {**{c["ticker"]: "Industry: " + ind + ". The leading off-price apparel retailer." for c in off[:4]},
             **{c["ticker"]: "Industry: Retail-Variety Stores. A chain of dollar and discount stores." for c in off[4:]},
             **{c["ticker"]: "Industry: Retail-Catalog. An online retailer selling through its website." for c in web},
             **{c["ticker"]: "Industry: Retail-Variety Stores. Membership warehouse clubs." for c in club},
             **{c["ticker"]: "Industry: " + ind + ". A clothing and accessories retailer with 400 stores in malls." for c in chains + plain}}
    models = {c["ticker"]: "retail" for c in off + web + club + chains}
    out = B.by_model(vc, models, "Consumer retail", evidence_of=words.get)
    where = {c["ticker"]: v["layer"] for v in out for c in v["companies"]}
    assert {where[c["ticker"]] for c in chains + plain} == {"Family clothing stores"}
    assert {where[c["ticker"]] for c in off} == {"Off-price and dollar stores"}
    grp = next(v for v in out if v["layer"] == "Family clothing stores")
    assert grp.get("industry_group") and not grp.get("official")
    assert B.industry_label("Retail-Apparel & Accessory Stores") == "Apparel and accessory stores"
    # a hyphenated word of a name is one word: "spun off" is no "off-price"
    assert B.name_says("Off-price stores", "It was spun off in 2015.", set()) == (True, False)
    assert B.name_says("Off-price stores", "An off price retailer.", set()) == (True, True)


def test_pawnbrokers_it_resellers_and_banks_filed_as_retail_are_another_business():
    for words in ("operates retail pawn stores in the U.S.", "provider of information technology services, serving business, government, education",
                  "We are a blank check company formed for a business combination", "a commercial bank licensed by the reserve bank"):
        assert C.off_industry(C.model_evidence("Retail-Miscellaneous Retail", words)), words
    assert not C.off_industry(C.model_evidence("Retail-Family Clothing Stores", "A clothing retailer with 400 stores."))
    assert not C.off_industry(C.model_evidence("Retail-Catalog & Mail-Order Houses", "A business-to-business e-commerce marketplace."))


def test_a_maker_read_as_a_telecom_operator_and_a_real_estate_developer_with_rentals():
    ev = C.model_evidence("Cables - Electricals", "Acme Ltd is engaged in manufacturing of wires and cables for power and telecom. "
                                                  "b) Telecom: optical fibre cables, FTTH")
    assert C.refine_model("telecom_services", ev) == "manufacturing"
    op = C.model_evidence("Telecom - Services", "Acme Ltd is a telecom services provider offering mobile and broadband services.")
    assert C.refine_model("telecom_services", op) == "telecom_services"
    dev = C.model_evidence("Residential, Commercial Projects", "Acme Land is in the business of real estate development. It also earns "
                                                               "income from renting of properties. a) Lease Rental")
    assert C.refine_model("property", dev) == "property_development"


def test_a_weak_evidence_company_of_the_layer_s_industry_is_in_its_figures_on_its_industry():
    """The live R41 Automotive deck: Mahindra & Mahindra, the largest company, out of its passenger vehicle layer's figures."""
    ind = "Passenger Cars & Utility Vehicles"
    vc = _vc(("Car makers", "Make cars.", [co(f"C{i}", f"Car {i}", "", ind) for i in range(4)] + [co("MM", "Big Group", "", ind)]),
             ("Bike makers", "Make bikes.", [co(f"B{i}", f"Bike {i}", "", "2/3 Wheelers") for i in range(3)]))
    models = {**{f"C{i}": "manufacturing" for i in range(4)}, **{f"B{i}": "manufacturing" for i in range(3)}, "MM": "manufacturing"}
    out = B.by_model(vc, models, "Auto", confidence={"MM": "low"})
    mm = next(c for v in out for c in v["companies"] if c["ticker"] == "MM")
    assert mm.get("on_industry") and not mm.get("model_out")
    # one of another industry with weak evidence stays out
    vc2 = _vc(("Car makers", "Make cars.", [co(f"C{i}", f"Car {i}", "", ind) for i in range(4)] + [co("XX", "Odd Co", "", "Software")]),
              ("Bike makers", "Make bikes.", [co(f"B{i}", f"Bike {i}", "", "2/3 Wheelers") for i in range(3)]))
    out2 = B.by_model(vc2, {**models, "XX": "manufacturing"}, "Auto", confidence={"XX": "low"})
    assert next(c for v in out2 for c in v["companies"] if c["ticker"] == "XX").get("model_out") == "unknown"


# ---------- E. the coverage on a page of its own when the checks need the room ----------
def test_the_checks_table_never_prints_its_heading_alone():
    """The live R41 Semiconductors, Real estate, Telecom and Utilities decks: "Check | What it found | What the deck does" and no row, the
    coverage table under it taking the page; now the coverage has a page of its own after the checks."""
    import copy

    from tests.test_deck_look import full_view
    v = full_view()
    base = v["layers"][0]
    v["layers"] = [{**copy.deepcopy(base), "layer": f"A rather long layer name for test group number {k}"} for k in range(14)]
    v["placements"] = {**(v.get("placements") or {}), "off_industry": [
        {"ticker": f"X{i}", "name": f"Another Business Company {i} Holdings", "industry": "Retail-Miscellaneous Retail"} for i in range(12)]}
    v["members"] = (v.get("members") or []) + [{"symbol": f"O{i}", "layer": "Other test companies", "rest": True} for i in range(30)]
    slides = deck.theme_plan(v)[0]
    conf = next(s for s in slides if s.title == "Data confidence")
    rows = [r for b in conf.blocks if b["kind"] == "table" for r in b["rows"] if not isinstance(r, dict)]
    assert len(rows) >= 3 and "Universe" in [r[0] for r in rows]
    cov = next(s for s in slides if s.title == deck.COVERAGE_TITLE)
    assert any(b["kind"] == "table" and b["head"] == deck.COVERAGE_HEAD for b in cov.blocks)
    assert any(str(p).startswith("Counts:") for b in conf.blocks if b["kind"] == "text" for p in b.get("paras") or [])
