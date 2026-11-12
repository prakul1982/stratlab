"""THEMES (owner, 31 Oct): a theme's companies are every company of its official industries, the AI only adds on top. The sector index
is the screener's stored index (each company's own classification), the theme -> industries map a curated table or the AI's pick from
the official list, and the AI can't remove an indexed company; a check stuck on one company is served as it stands after a while."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.intel import theme_base as B
from app.intel import theme_check as C

# the live index's own classification of the companies the brief names (NSE basic industry, read 4 Nov 2026), market value in ₹ crore
LIVE_IN = [
    ("HAL", "Hindustan Aeronautics Ltd", "Industrials", "Aerospace & Defense", 332201), ("BEL", "Bharat Electronics Ltd", "Industrials", "Aerospace & Defense", 277771),
    ("BDL", "Bharat Dynamics Ltd", "Industrials", "Aerospace & Defense", 37205), ("MAZDOCK", "Mazagon Dock Shipbuilders Ltd", "Industrials", "Ship Building & Allied Services", 71829),
    ("GRSE", "Garden Reach Shipbuilders & Engineers Ltd", "Industrials", "Aerospace & Defense", 24422),
    ("COCHINSHIP", "Cochin Shipyard Ltd", "Industrials", "Ship Building & Allied Services", 31596),
    ("DATAPATTNS", "Data Patterns (India) Ltd", "Industrials", "Aerospace & Defense", 21725), ("SOLARINDS", "Solar Industries India Ltd", "Commodities", "Explosives", 178118),
    ("BEML", "BEML Ltd", "Industrials", "Construction Vehicles", 17098), ("ASTRAMICRO", "Astra Microwave Products Ltd", "Industrials", "Aerospace & Defense", 14491),
    ("PARAS", "Paras Defence and Space Technologies Ltd", "Industrials", "Aerospace & Defense", 9758),
    ("TMPV", "Tata Motors Passenger Vehicles Ltd", "Consumer Discretionary", "Passenger Cars & Utility Vehicles", 102063),
    ("M&M", "Mahindra & Mahindra Ltd", "Consumer Discretionary", "Passenger Cars & Utility Vehicles", 361656),
    ("OLAELEC", "Ola Electric Mobility Ltd", "Consumer Discretionary", "2/3 Wheelers", 17306),
    ("EXIDEIND", "Exide Industries Ltd", "Consumer Discretionary", "Auto Components & Equipments", 29397),
    ("ARE&M", "Amara Raja Energy & Mobility Ltd", "Consumer Discretionary", "Auto Components & Equipments", 12539),
    ("TATAPOWER", "Tata Power Company Ltd", "Utilities", "Integrated Power Utilities", 113898),
    ("HDFCBANK", "HDFC Bank Ltd", "Financial Services", "Private Sector Bank", 1119622), ("SBIN", "State Bank of India", "Financial Services", "Public Sector Bank", 895846),
    ("AUBANK", "AU Small Finance Bank Ltd", "Financial Services", "Other Bank", 66223),
    ("SUNPHARMA", "Sun Pharmaceutical Industries Ltd", "Healthcare", "Pharmaceuticals", 424587),
    ("ADANIGREEN", "Adani Green Energy Ltd", "Utilities", "Power Generation", 220606),
    ("DIGI", "A digital media company", "Consumer Discretionary", "Digital Entertainment", 900),
]
ROWS = [{"symbol": s, "name": n, "sector": sec, "industry": i, "market_cap": cap} for s, n, sec, i, cap in LIVE_IN]
LIVE_US = [{"symbol": "NVDA", "name": "NVIDIA CORP", "sector": "Manufacturing", "industry": "Semiconductors & Related Devices", "market_cap": 4500000},
           {"symbol": "AMD", "name": "ADVANCED MICRO DEVICES INC", "sector": "Manufacturing", "industry": "Semiconductors & Related Devices", "market_cap": 380000},
           {"symbol": "LRCX", "name": "LAM RESEARCH CORP", "sector": "Manufacturing", "industry": "Special Industry Machinery, Nec", "market_cap": 150000},
           {"symbol": "LMT", "name": "LOCKHEED MARTIN CORP", "sector": "Manufacturing", "industry": "Guided Missiles & Space Vehicles & Parts", "market_cap": 110000},
           {"symbol": "JPM", "name": "JPMORGAN CHASE & CO", "sector": "Finance", "industry": "National Commercial Banks", "market_cap": 800000}]


def base_of(region, theme, rows):
    inds = B.industries_for(region, theme, rows, ask=None, get_setting=lambda k: None, set_setting=lambda k, v: None)
    ks = {B.key(i) for i in inds["industries"]}
    got = {r["symbol"] for r in rows if B.key(r["industry"]) in ks and r["symbol"] not in inds.get("except", [])} | set(inds.get("named", []))
    return got, inds


# ---------- the theme -> industries map ----------
def test_india_defence_is_every_company_of_the_defence_industries_from_the_exchanges_own_list():
    got, inds = base_of("IN", "India defence", ROWS)
    assert inds == {"industries": ["Aerospace & Defense", "Ship Building & Allied Services", "Explosives"], "how": "list", "named": ["BEML"], "except": [], "drop": []}
    # BEML: the exchange puts it under construction vehicles; it is in by the theme's own named list (THEMES, 4 Nov)
    assert got == {"HAL", "BEL", "BDL", "MAZDOCK", "GRSE", "COCHINSHIP", "DATAPATTNS", "SOLARINDS", "ASTRAMICRO", "PARAS", "BEML"}


def test_ev_puts_the_carmakers_two_wheelers_and_battery_makers_in_the_chain_without_any_description():
    got, _ = base_of("IN", "EV and battery supply chain", ROWS)
    assert {"TMPV", "M&M", "OLAELEC", "EXIDEIND", "ARE&M"} <= got
    assert base_of("IN", "electric vehicles", ROWS)[0] == got
    assert base_of("IN", "electric vehicles", ROWS)[1] == base_of("IN", "EV and battery supply chain", ROWS)[1]     # not the tyre makers and tractors of "autos"
    assert "TATAPOWER" not in got                     # charging is the AI's to add, checked on its own words


def test_banks_pharma_renewables_and_us_semiconductors_have_their_industries():
    assert base_of("IN", "Indian banks", ROWS)[0] == {"HDFCBANK", "SBIN", "AUBANK"}
    assert base_of("IN", "pharma", ROWS)[0] == {"SUNPHARMA"}
    # India's renewables: the named list only (its power-generation industry mixes in coal and gas plants)
    assert base_of("IN", "Renewables and solar", ROWS)[0] == {"ADANIGREEN", "TATAPOWER"}
    assert base_of("US", "semiconductors", LIVE_US)[0] == {"NVDA", "AMD", "LRCX"}           # Lam Research files under machinery: named
    assert base_of("US", "Defense drones", LIVE_US)[0] == {"LMT"}
    assert base_of("US", "US banks", LIVE_US)[0] == {"JPM"}
    # a narrow theme inside a wide industry has no official base (500 drug makers aren't the GLP-1 chain)
    assert base_of("US", "GLP-1 supply chain", LIVE_US) == (set(), {"industries": [], "how": "list", "named": [], "except": [], "drop": []})
    assert B.curated("IN", "specialty chemicals", {B.key("Specialty Chemicals"): "Specialty Chemicals", B.key("Commodity Chemicals"): "Commodity Chemicals"}) == ["Specialty Chemicals"]


def test_every_curated_name_is_written_as_the_exchanges_list_writes_it():
    # the names are compared case and spacing aside, so the SEC's double spaces ("Of  Nonferrous") still match
    assert B.key("Drawing & Insulating Of  Nonferrous Wire") == B.key("Drawing & Insulating Of Nonferrous Wire")
    for c in B.CONCEPTS:
        for region in ("IN", "US"):
            assert all(isinstance(n, str) and n.strip() == n for n in c.get(region, [])), c


def test_a_free_text_theme_takes_only_names_on_the_official_list_kept_a_month():
    store, asked = {}, []

    def ask(system, text):
        asked.append(text)
        assert "LIST:" in text and "Digital Entertainment" in text
        return {"industries": ["digital  entertainment", "Quantum Widgets"]}          # one on the list (spacing aside), one made up
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    got = B.industries_for("IN", "online gaming", ROWS, ask, store.get, store.__setitem__, now=now)
    assert got == {"industries": ["Digital Entertainment"], "how": "ai", "named": [], "except": []} and len(asked) == 1
    assert B.industries_for("IN", "online gaming", ROWS, ask, store.get, store.__setitem__, now=now + timedelta(days=29))["industries"] == ["Digital Entertainment"]
    assert len(asked) == 1                            # kept: not asked again within the month
    B.industries_for("IN", "online gaming", ROWS, ask, store.get, store.__setitem__, now=now + timedelta(days=31))
    assert len(asked) == 2                            # picked again after a month


def test_an_ai_that_cannot_pick_leaves_the_base_pending_and_keeps_nothing():
    store = {}

    def ask(system, text):
        raise RuntimeError("busy")
    # no industry's name shares a word with "online gaming" here: nothing to fall back on, asked again next time
    assert B.industries_for("IN", "online gaming", ROWS, ask, store.get, store.__setitem__) == {"industries": [], "how": "pending", "named": [], "except": []}
    assert store == {}
    assert B.industries_for("IN", "anything", [], ask, store.get, store.__setitem__)["how"] == "none"
    # ...but one whose words name an industry has it at once, by the words rule (THEMES, 4 Nov)
    assert B.industries_for("IN", "online digital entertainment", ROWS, ask, store.get, store.__setitem__)["industries"] == ["Digital Entertainment"]


# ---------- membership: the AI can't remove an indexed company ----------
MAP = {"sector": "India defence", "value_chain": [
    {"layer": "Missiles", "description": "Missile makers build guided missiles.", "companies": [{"name": "Bharat Dynamics", "ticker": "BDL"}, {"name": "HAL", "ticker": "HAL"}]},
    {"layer": "Defence vehicles", "description": "Vehicles for the army.", "companies": [{"name": "BEML", "ticker": "BEML"}, {"name": "Reliance", "ticker": "RELIANCE"}]}],
    "sub_themes": [], "screen": [], "clusters": []}
ABOUT = {"BDL": "Bharat Dynamics manufactures guided missiles and allied defence equipment for the armed forces.",
         "HAL": "Hindustan Aeronautics designs and builds aircraft, helicopters and engines.",
         "BEML": "BEML makes defence vehicles for the army and earth moving equipment for mines.",
         "RELIANCE": "Reliance refines crude oil and runs retail stores and a telecom network."}


def checked_map(says):
    """check_placements with the AI answering `says[(layer id, symbol)]` (True, False, or missing = no answer), then the base on top."""
    def ask(system, text):
        body = json.loads(text.split("CHECKS:\n", 1)[1])
        out = []
        for c in body["companies"]:
            for g in c["check_groups"]:
                v = says.get((g, c["symbol"]))
                if v is not None:
                    out.append({"id": f"{g}|{c['symbol']}", "does": v, "quote": " ".join(c["description"].split()[1:8]) if v else ""})
        return {"checks": out}
    ev = lambda syms: ({s: {"about": ABOUT[s], "industry": ""} for s in syms if s in ABOUT}, set())     # noqa: E731
    out = C.check_placements(MAP, ev, ask, "India defence", {})
    return B.with_base(MAP, out, ROWS, ["Aerospace & Defense", "Ship Building & Allied Services", "Explosives"])


def test_a_no_from_the_ai_moves_an_indexed_company_out_of_the_layer_never_out_of_the_theme():
    out = checked_map({("L0", "BDL"): True, ("L0", "HAL"): False, ("L1", "BEML"): True, ("L1", "RELIANCE"): False})
    layers = {v["layer"]: v for v in out["value_chain"]}
    assert [c["ticker"] for c in layers["Missiles"]["companies"]] == ["BDL"]
    assert layers["Missiles"]["companies"][0]["verified"] and layers["Missiles"]["companies"][0]["base"]
    # HAL: the AI's "no" for the missile layer moved it to its own industry, with every company the map never named, largest first
    ad = layers["Aerospace and defence"]          # R21: India's industry names plain too
    assert ad["official"] and [c["ticker"] for c in ad["companies"]] == ["HAL", "BEL", "GRSE", "DATAPATTNS", "ASTRAMICRO", "PARAS"]
    assert [c["ticker"] for c in layers["Shipbuilding"]["companies"]] == ["MAZDOCK", "COCHINSHIP"]
    assert [c["ticker"] for c in layers["Explosives"]["companies"]] == ["SOLARINDS"]
    # BEML: an addition from another industry, kept in its own words; Reliance: an addition its own words don't back, left out
    assert [c["ticker"] for c in layers["Defence vehicles"]["companies"]] == ["BEML"] and not layers["Defence vehicles"]["companies"][0]["base"]
    p = out["placements"]
    assert (p["total"], p["base"], p["added"], p["confirmed"], p["left_out"]) == (11, 10, 1, 1, 1)


def test_an_ai_that_says_no_to_everything_still_leaves_every_indexed_company():
    out = checked_map({(g, s): False for g in ("L0", "L1") for s in ABOUT})
    syms = {c["ticker"] for v in out["value_chain"] for c in v["companies"]}
    assert syms == {"HAL", "BEL", "BDL", "MAZDOCK", "GRSE", "COCHINSHIP", "DATAPATTNS", "SOLARINDS", "ASTRAMICRO", "PARAS"}
    assert out["placements"]["added"] == 0 and out["placements"]["left_out"] == 2


def test_an_unanswered_addition_stays_marked_not_yet_confirmed():
    out = checked_map({("L0", "BDL"): True})
    beml = next(c for v in out["value_chain"] for c in v["companies"] if c["ticker"] == "BEML")
    assert beml["verified"] is False and beml["what"] == "" and not beml["base"]
    assert out["placements"]["unconfirmed"] == 2 and out["placements"]["confirmed"] == 0          # BEML and Reliance, neither answered


def test_the_figures_are_worked_out_on_the_named_companies_and_the_largest_of_the_rest():
    out = checked_map({("L0", "BDL"): True, ("L0", "HAL"): False})
    fm, n = B.for_figures(out, cap=6)
    syms = {c["ticker"] for v in fm["value_chain"] for c in v["companies"]}
    assert n == {"shown": 6, "of": 12}
    assert {"BDL", "HAL", "BEML", "RELIANCE"} <= syms and "SOLARINDS" in syms and "PARAS" not in syms      # the largest of the rest first
    assert all(v["companies"] or not v.get("official") for v in fm["value_chain"])                        # no empty official layer


def test_an_official_layers_company_shows_the_first_sentence_of_its_own_description():
    out = checked_map({("L0", "BDL"): True})
    said = B.described(out, lambda s: "Paras Defence makes optics and drone systems for defence. It also does space work." if s == "PARAS" else None)
    rows = {c["ticker"]: c for v in said["value_chain"] if v.get("official") for c in v["companies"]}
    assert rows["PARAS"]["what"] == "Paras Defence makes optics and drone systems for defence"
    assert rows["BEL"]["what"] == ""                   # none known yet: the page says it isn't confirmed from its own description
    assert B.to_describe(out, 2) == ["BEL", "SOLARINDS"]                # HAL, unanswered, stays in the AI's layer


# ---------- the routes: the base on the page, and a check that waits too long ----------
from tests.test_research_api import api  # noqa: E402,F401


def test_the_sector_route_lists_every_company_of_the_industries_and_marks_the_ais_additions(api, monkeypatch):
    from app.intel import routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    monkeypatch.setattr(routes, "index_rows", lambda region: LIVE_US + [{"symbol": "VRT", "name": "Vertiv", "industry": "Electrical Industrial Apparatus", "market_cap": 40000}])
    s = api.get("/research/sector?q=semiconductors&region=US").json()
    chips = s["value_chain"][0]
    assert [(c["ticker"], c["base"]) for c in chips["companies"]] == [("NVDA", True), ("VRT", False)]      # VRT: added, in its own words
    # changed on purpose (R21): every company of the theme's industries and list sits in one of the map's own layers (placed from its words
    # after the map), or in one "Other ... companies" layer when it fits none; never in a layer named after the exchange's industry
    p = s["placements"]
    assert {c["ticker"] for v in s["value_chain"] for c in v["companies"]} == {"NVDA", "VRT", "AMD", "LRCX"}
    assert all(not v.get("official") or v.get("basis") == "rest" for v in s["value_chain"])
    assert all(c.get("placed") for v in s["value_chain"] for c in v["companies"] if c["ticker"] in ("AMD", "LRCX"))
    assert (p["total"], p["base"], p["named"], p["added"], p["industries"], p["industries_by"]) == (4, 3, 1, 1, ["Semiconductors & Related Devices"], "list")
    d = api.get("/research/theme-dive?q=semiconductors&region=US").json()
    assert d["figures"] == {"shown": 4, "of": 4} and [b["official"] for b in d["layers"]] == [bool(v.get("official")) for v in s["value_chain"]]


def test_a_check_stuck_on_a_company_is_served_as_it_stands_after_a_while(api, monkeypatch):
    from app.intel import routes, theme_routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    monkeypatch.setattr(routes, "index_rows", lambda region: LIVE_US)
    # VRT's description can't be read right now (its source is busy): it stays pending
    monkeypatch.setattr(theme_routes, "evidence_reader", lambda region, names: lambda syms: (
        {s: {"about": "Nvidia designs the chips that train AI models in data centers.", "industry": ""} for s in syms if s == "NVDA"}, {s for s in syms if s == "VRT"}))
    clock = {"t": 1000.0}
    monkeypatch.setattr(theme_routes.time, "time", lambda: clock["t"])
    theme_routes._pending_since.clear()
    first = api.get("/research/sector?q=semiconductors&region=US").json()["placements"]
    assert first["checked"] is False and first["pending"] == 1
    clock["t"] += theme_routes.PENDING_GIVE_UP + 1
    later = api.get("/research/sector?q=semiconductors&region=US").json()["placements"]
    assert later["checked"] is True and later["timed_out"] == 1                 # a clear state: VRT shown, not yet confirmed
    again = api.get("/research/sector?q=semiconductors&region=US").json()["placements"]
    assert again["timed_out"] == 1                                              # kept as it stands (checked again two hours on)


def test_a_named_member_is_base_and_a_solar_maker_filed_as_a_chipmaker_is_not_in_the_chip_base():
    rows = LIVE_US + [{"symbol": "FSLR", "name": "FIRST SOLAR, INC.", "industry": "Semiconductors & Related Devices", "market_cap": 20000}]
    inds = B.industries_for("US", "semiconductors", rows, None, lambda k: None, lambda k, v: None)
    assert inds["named"] == ["LRCX"] and "FSLR" in inds["except"]                           # only symbols that are in the index are named
    out = B.with_base({"value_chain": [], "sub_themes": []}, {"value_chain": [], "sub_themes": [], "placements": {}}, rows, inds["industries"],
                      named=inds["named"], exclude=inds["except"])
    layers = {v["layer"]: v for v in out["value_chain"]}
    assert [c["ticker"] for c in layers["Semiconductors"]["companies"]] == ["NVDA", "AMD"]          # R20: the industry's plain name as a layer
    assert [(c["ticker"], c["basis"]) for c in layers["Named in the theme's list"]["companies"]] == [("LRCX", "list")]
    assert (out["placements"]["base"], out["placements"]["named"]) == (3, 1)
    # the solar maker is in renewables' named list instead
    assert "FSLR" in B.industries_for("US", "renewable energy", rows, None, lambda k: None, lambda k, v: None)["named"]


# ---------- item 6: a description that doesn't name a business line is backed by the company's own filings ----------
def test_a_companys_own_filings_back_a_description_that_doesnt_name_the_work(monkeypatch):
    from app import biz_updates
    from app.intel import routes, theme_routes
    monkeypatch.setattr(biz_updates, "stored", lambda sym: {"r1": {}} if sym == "TMPV" else {})
    monkeypatch.setattr(biz_updates, "series", lambda reads: [{"metric": "EV sales", "segment": None,
                                                               "latest": {"source": {"quote": "Electric vehicle sales of 7,012 units in October 2026"}}}] if reads else [])
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: {"filings": [{"name": "Tata Motors launches the Harrier.ev in India"}, {"name": "x"}]} if sym == "TMPV" else None)
    got = theme_routes.own_filings("IN", "TMPV")
    assert got == "From its own filings: Electric vehicle sales of 7,012 units in October 2026. Tata Motors launches the Harrier.ev in India."
    assert theme_routes.own_filings("IN", "NONE") == ""
    # the check reads the description and the filings together, so a quote from a filing places the company
    about = "Tata Motors Passenger Vehicles makes passenger cars and utility vehicles. " + got
    group = "Electric vehicles Makers of battery electric cars and their electric vehicle sales"
    assert C.quote_in("Electric vehicle sales of 7,012 units", C.clean_description(about, C.EVIDENCE_MAX)) and C.supports("Electric vehicle sales of 7,012 units", group)
    assert B.one_line(got) == "From its own filings: Electric vehicle sales of 7,012 units in October 2026"


def test_the_evidence_reader_adds_the_filings_and_reads_a_company_with_only_filings(monkeypatch):
    from app.intel import theme_routes
    monkeypatch.setattr(theme_routes, "own_filings", lambda region, sym: "From its own filings: Electric bus orders from state transport units.")
    store = {f"theme:evidence:IN:OLECTRA": json.dumps({"at": datetime.now(timezone.utc).isoformat(), "about": "", "industry": "",
                                                       "v": theme_routes.ABOUT_V})}         # R34: a record read in the current format
    monkeypatch.setattr(theme_routes.db, "get_setting", lambda k: store.get(k))
    theme_routes.EVIDENCE_CACHE.clear()
    got, pending = theme_routes.evidence_reader("IN", {})(["OLECTRA"])
    assert got["OLECTRA"]["about"] == "From its own filings: Electric bus orders from state transport units." and not pending



# ---------- the whole class (owner, 4 Nov: "all fixes should fix things globally") ----------
# every official industry and listed symbol of both markets, from the live index of 4 Nov 2026
INDEX = json.loads((Path(__file__).parent / "fixtures" / "theme_index_2026_11_04.json").read_text())
SYMBOLS = {m: set(INDEX[m]["symbols"].split()) for m in ("IN", "US")}


def world(region):
    """One company in every official industry of the market, and every listed symbol as a company of its own."""
    rows = [{"symbol": f"CO{i}", "name": f"Company {i}", "industry": ind, "market_cap": 100.0} for i, ind in enumerate(INDEX[region]["industries"])]
    return rows + [{"symbol": s, "name": s, "industry": "", "market_cap": 1.0} for s in SYMBOLS[region]]


def none_picked(system, text):
    return {"industries": []}


def busy(system, text):
    raise RuntimeError("busy")


def test_every_curated_industry_and_named_company_is_on_the_live_official_list():
    for c in B.CONCEPTS:
        for m in ("IN", "US"):
            known = {B.key(i) for i in INDEX[m]["industries"]}
            assert all(B.key(n) in known for n in c.get(m, [])), (m, [n for n in c.get(m, []) if B.key(n) not in known])
            for k in (f"{m}_named", f"{m}_except"):
                assert set(c.get(k, [])) <= SYMBOLS[m], (k, set(c.get(k, [])) - SYMBOLS[m])


def test_every_curated_theme_has_a_base_in_each_market_it_covers():
    for c in B.CONCEPTS:
        word = sorted(c["words"])[0] if c["words"] else c["phrases"][0]
        for m in ("IN", "US"):
            if m not in c:
                continue
            inds = B.industries_for(m, word, world(m), busy, lambda k: None, lambda k, v: None)
            assert inds["how"] == "list" and (inds["industries"] or inds["named"]), (m, word)


def test_every_suggested_theme_on_the_page_is_curated_with_a_base():
    src = (Path(__file__).parents[2] / "frontend" / "src" / "lib" / "research.ts").read_text()
    ideas = re.search(r"THEME_IDEAS[^=]*=\s*\{(.*?)\};", src, re.S).group(1)
    for m, body in re.findall(r"(IN|US): \[([^\]]*)\]", ideas):
        for theme in re.findall(r'"([^"]+)"', body):
            inds = B.industries_for(m, theme, world(m), busy, lambda k: None, lambda k, v: None)
            assert inds["how"] == "list" and (inds["industries"] or inds["named"]), (m, theme)


def test_every_official_industry_typed_as_a_theme_gets_its_own_companies():
    for m in ("IN", "US"):
        rows = world(m)
        for i, ind in enumerate(INDEX[m]["industries"]):
            for ask in (none_picked, busy):
                inds = B.industries_for(m, ind, rows, ask, lambda k: None, lambda k, v: None)
                assert ind in inds["industries"], (m, ind, inds)
                out = B.with_base({"value_chain": [], "sub_themes": []}, {"value_chain": [], "sub_themes": [], "placements": {}}, rows,
                                  inds["industries"], named=inds["named"], exclude=inds["except"])
                assert f"CO{i}" in {c["ticker"] for v in out["value_chain"] for c in v["companies"]}, (m, ind)


def test_typed_themes_fall_back_on_the_industries_their_words_name_in_both_markets():
    store = {}
    for theme in ("cement", "hotels", "ports", "fertilisers", "paints", "data centres", "cloud software", "airlines", "steel", "EV batteries",
                  "tyres", "sugar", "breweries", "insurance brokers", "trucking"):
        for m in ("IN", "US"):
            inds = B.industries_for(m, theme, world(m), none_picked, store.get, store.__setitem__)
            base = inds["industries"] or inds["named"]
            if theme in ("tyres", "sugar", "breweries", "trucking") and m == "US" or theme == "trucking":
                continue                                   # samples one market names and the other doesn't
            assert base, (m, theme, inds)
    assert B.words_pick("paints", {B.key("Paints"): "Paints"}) == ["Paints"]
    assert B.words_pick("fertilisers", {B.key("Fertilizers"): "Fertilizers"}) == ["Fertilizers"]
    assert B.words_pick("the india sector", {B.key("Diversified"): "Diversified"}) == []           # words that name nothing match nothing


def test_every_us_company_without_an_industry_gets_one_from_its_sec_record_a_few_at_a_time():
    rows = [{"symbol": s, "industry": "", "market_cap": None} for s in sorted(SYMBOLS["US"])[:300]] + LIVE_US
    codes = {s: (["Manufacturing", "Semiconductors & Related Devices"] if i % 3 else []) for i, s in enumerate(sorted(SYMBOLS["US"])[:300])}
    reads = []

    def read(sym):
        reads.append(sym)
        if sym == "A":
            raise RuntimeError("SEC busy")
        return codes[sym]
    stored, runs = {}, 0
    now = datetime(2026, 11, 4, tzinfo=timezone.utc)
    while runs < 20:
        stored, n = B.fill_sic(rows, stored, read, now=now, limit=40)
        assert n <= 40
        runs += 1
        if n == 0:
            break
    filled = B.with_sic(rows, stored)
    left = B.unclassified(filled)
    expected = sum(1 for s, p in codes.items() if not p)            # (A, the busy one, has no code either)
    assert left == expected                           # every company with a code has it; the rest are counted, none skipped
    assert all(r["industry"] == "Semiconductors & Related Devices" for r in filled if codes.get(r["symbol"]))
    n_reads = len(reads)
    B.fill_sic(rows, stored, read, now=now + timedelta(days=5))
    assert len(reads) - n_reads == 1                  # a company with no code isn't asked again within the month; a busy one is
    n_reads = len(reads)
    B.fill_sic(rows, stored, read, now=now + timedelta(days=31))
    assert len(reads) - n_reads == 40                 # a month on, the companies with no code are asked again, 40 at a time


# ---------- LIVE3-001: no theme request waits on the AI ----------
def _slow_ai(monkeypatch, gate):
    """The AI's map held until `gate` is set (a provider taking a minute); every other AI call answers as the fake world does."""
    from app.intel import routes
    real = routes.A.sector

    def slow(theme, region, ai):
        gate.wait(60)
        return real(theme, region, ai)
    monkeypatch.setattr(routes.A, "sector", slow)


def test_a_theme_answers_with_its_official_base_at_once_while_the_ai_is_slow_and_fills_in_after(api, monkeypatch):
    import threading
    import time
    from app.intel import routes, theme_routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    monkeypatch.setattr(routes, "index_rows", lambda region: ROWS if region == "IN" else LIVE_US)
    gate = threading.Event()
    _slow_ai(monkeypatch, gate)
    try:
        t0 = time.monotonic()
        s = api.get("/research/sector?q=India%20defence&region=IN").json()
        assert time.monotonic() - t0 < theme_routes.THEME_WAIT + 2                # never the AI's minute (the live cut was at 30 s)
        listed = {c["ticker"] for v in s["value_chain"] for c in v["companies"]}
        assert {"HAL", "BEL", "BDL", "MAZDOCK", "GRSE", "COCHINSHIP", "DATAPATTNS", "SOLARINDS", "BEML", "ASTRAMICRO", "PARAS"} <= listed
        assert s["ai"] == {"state": "working", "message": ""} and s["generated_at"] == 0 and s["summary"] == ""
        # the dive and its parts answer from the same base, also without waiting
        t0 = time.monotonic()
        assert api.get("/research/theme-dive?q=India%20defence&region=IN").status_code == 200
        assert time.monotonic() - t0 < theme_routes.THEME_WAIT + 4
    finally:
        gate.set()
    theme_routes.job_of(("map", "IN", "india defence"))["done"].wait(30)
    later = api.get("/research/sector?q=India%20defence&region=IN").json()
    assert later["generated_at"] > 0 and later["summary"]                       # the AI's map is in on the next ask
    theme_routes.job_of(("check", "IN", "india defence", int(later["generated_at"]), B.RULES))["done"].wait(30)      # the rules' version is in the key (R18)
    done = api.get("/research/sector?q=India%20defence&region=IN").json()
    assert done["ai"] is None and done["placements"]["checked"] is True


def test_every_suggested_and_curated_theme_in_both_markets_answers_without_waiting_on_the_ai(api, monkeypatch):
    """The whole class: every theme the page suggests and every curated concept's words, India and the US."""
    import threading
    import time
    from app.intel import routes, theme_routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    monkeypatch.setattr(routes, "index_rows", lambda region: ROWS if region == "IN" else LIVE_US)
    monkeypatch.setattr(theme_routes, "fill_us_industries", lambda read=None: 0)
    monkeypatch.setattr(routes, "ai_cap", lambda profile: None)                # the daily cap is its own test (test_daily_ai_allowance)
    # (updated on purpose, FREE-TIER: Free maps 1 new theme a month now, so the sweep of every theme runs on Pro; the theme limit is
    # tests/test_free_tier.py's)
    from app import main as _m
    monkeypatch.setitem(_m.app.dependency_overrides, _m.current_profile, lambda: {"id": "u1", "_plan": "pro", "plan": "pro"})
    monkeypatch.setattr(theme_routes, "THEME_WAIT", 0.3)                         # the sweep's own pace; the bound is the same rule
    ideas = re.search(r"THEME_IDEAS[^=]*=\s*\{(.*?)\};", (Path(__file__).parents[2] / "frontend/src/lib/research.ts").read_text(), re.S).group(1)
    themes = {m: re.findall(r'"([^"]+)"', re.search(m + r":\s*\[(.*?)\]", ideas).group(1)) for m in ("IN", "US")}
    for c in B.CONCEPTS:
        for m in ("IN", "US"):
            themes[m].append(max(sorted(c["words"]), key=len) if c.get("words") else c["phrases"][0])
    assert len(themes["IN"]) >= 6 + len(B.CONCEPTS) and len(themes["US"]) >= 6 + len(B.CONCEPTS)
    gate = threading.Event()
    _slow_ai(monkeypatch, gate)
    try:
        for m, qs in themes.items():
            for q in qs:
                t0 = time.monotonic()
                r = api.get(f"/research/sector?q={q}&region={m}")
                took = time.monotonic() - t0
                assert r.status_code == 200, (m, q, r.text[:200])
                assert took < theme_routes.THEME_WAIT + 2, (m, q, took)
                assert r.json()["ai"]["state"] == "working", (m, q)
    finally:
        gate.set()
