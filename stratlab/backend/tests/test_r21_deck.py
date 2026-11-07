"""Release 21 (owner, 7 Nov: "do it globally fix all the themes"): every confirmed company sits in one of the map's own layers (placed after the
map from its own words: one AI answer a theme, kept in the shared store, else by the words it shares with each layer), a stored theme from the
older rules is rebuilt that way, a first deck waits for its map ("preparing"), charts follow the tables' small-base rule, a page needs three
companies' operating figures, findings never cut a sentence, tailwinds and risks show evenly with their evidence said, and each industry
family has its metric profile. Generic: every sector, India and the US. Facts only."""
import json

import pytest

from app import deck
from app.intel import ai as A
from app.intel import theme_base as B
from app.intel import theme_check as C
from app.intel import theme_data as D
from app.intel import theme_routes as T
from tests.test_deck_look import full_view
from tests.test_export import plain, table_of, texts
from tests.test_r18_deck import deck_of
from tests.test_r20_deck import it_theme
from tests.test_theme1 import facts
from tests.test_research_api import api  # noqa: F401


def mapped(theme="Defence"):
    """A map with layers of its own naming a few companies, and the exchange's industries holding the rest (as with_base leaves them)."""
    own = [{"layer": "Missiles and rockets", "description": "Guided missiles, rockets and their propellants.", "companies": [{"ticker": "MS1", "name": "Missile One", "verified": True}]},
           {"layer": "Warships", "description": "Builds and repairs naval ships and submarines.", "companies": [{"ticker": "SH1", "name": "Ship One", "verified": True}]},
           {"layer": "Defence electronics", "description": "Radars, sonars and electronic warfare systems.", "companies": [{"ticker": "EL1", "name": "Elec One", "verified": True}]}]
    rest = [{"layer": "Aerospace and defence", "official": True, "basis": "industry", "description": "",
             "companies": [{"ticker": s, "name": n, "industry": "Aerospace & Defense", "cap": c, "base": True, "basis": "industry"} for s, n, c in
                           (("EL2", "Elec Two", 900), ("MS2", "Missile Two", 800), ("XX1", "Uniform Maker", 100))]},
            {"layer": "Shipbuilding", "official": True, "basis": "industry", "description": "",
             "companies": [{"ticker": "SH2", "name": "Ship Two", "industry": "Ship Building & Allied Services", "cap": 700, "base": True, "basis": "industry"}]}]
    return {"sector": theme, "value_chain": own + rest, "sub_themes": []}


ABOUT = {"EL2": "Elec Two makes radars and electronic warfare systems for the armed forces.", "MS2": "Missile Two makes rocket propellants and guided missiles.",
         "SH2": "Ship Two builds and repairs naval ships.", "XX1": "Uniform Maker stitches clothing for institutions."}


# ---------- 1. every company in one of the map's layers ----------
def test_every_base_company_goes_to_one_of_the_maps_layers_by_its_own_words_or_to_one_other_layer():
    out, got = B.place_rest(mapped(), "Defence", ABOUT.get)
    lay = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out["value_chain"]}
    assert lay == {"Missiles and rockets": ["MS1", "MS2"], "Warships": ["SH1", "SH2"], "Defence electronics": ["EL1", "EL2"], "Other defence companies": ["XX1"]}
    assert not any(v.get("official") and v.get("basis") != "rest" for v in out["value_chain"])         # no exchange industry beside the map's layers
    placed = [c for v in out["value_chain"] for c in v["companies"] if c.get("placed")]
    assert {c["ticker"] for c in placed} == {"EL2", "MS2", "SH2", "XX1"} and all(c["verified"] is False and c["base"] for c in placed)
    assert {s: x["by"] for s, x in got["assign"].items()} == {"EL2": "words", "MS2": "words", "SH2": "words", "XX1": "words"}      # R22: one answer, kept whole


def test_one_ai_answer_places_them_and_a_kept_answer_is_never_asked_again():
    asked = []

    def ask(system, text):
        asked.append(json.loads(text.split("COMPANIES:\n", 1)[1]))
        return {"place": [{"symbol": "EL2", "layer": "L2"}, {"symbol": "MS2", "layer": "L0"}, {"symbol": "SH2", "layer": "L1"}, {"symbol": "XX1", "layer": "none"},
                          {"symbol": "NOTASKED", "layer": "L0"}, {"symbol": "EL2", "layer": "L9"}]}
    out, got = B.place_rest(mapped(), "Defence", ABOUT.get, ask=ask)
    assert len(asked) == 1 and [c["symbol"] for c in asked[0]["companies"]] == ["EL2", "MS2", "SH2", "XX1"]       # one batch, largest first
    a_ = got["assign"]
    assert a_["MS2"] == {"layer": "Missiles and rockets", "by": "ai"} and a_["XX1"] == {"layer": "", "by": "ai"} and "NOTASKED" not in a_
    again, _ = B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: pytest.fail("asked again"), kept=got)
    assert again == out
    # the AI busy: the words place them now
    busy, got2 = B.place_rest(mapped(), "Defence", ABOUT.get, ask=lambda s, t: (_ for _ in ()).throw(RuntimeError("busy")))
    assert all(x["by"] == "words" for x in got2["assign"].values()) and busy == B.place_rest(mapped(), "Defence", ABOUT.get)[0]


def test_the_answer_is_kept_in_the_shared_store_with_the_map(monkeypatch):
    from app import computed
    store = {}
    monkeypatch.setattr(computed, "get", lambda kind, key, count=True: {"value": store[(kind, json.dumps(key))]} if (kind, json.dumps(key)) in store else None)
    monkeypatch.setattr(computed, "put", lambda kind, key, value, **kw: store.__setitem__((kind, json.dumps(key)), value) or {"value": value})
    monkeypatch.setattr(T, "_about_reader", lambda region, names, limit=0: (lambda s: ABOUT.get(s)))
    calls = []

    def ask(system, text):
        calls.append(1)
        return {"place": [{"symbol": "EL2", "layer": "L2"}, {"symbol": "MS2", "layer": "L0"}, {"symbol": "SH2", "layer": "L1"}, {"symbol": "XX1", "layer": "none"}]}
    m = {"sector": "Defence", "generated_at": 7.0}
    first = T.placed("IN", "Defence", m, mapped(), ask=ask)
    second = T.placed("IN", "Defence", m, mapped(), ask=ask)
    page = T.placed("IN", "Defence", m, mapped(), ask=None)                # the page's quick read: the kept answer, no AI
    assert calls == [1] and first == second == page
    assert ("theme:place", json.dumps(["place", "IN", "defence", 7, B.RULES])) in store


def test_it_services_has_the_maps_layers_only_and_plain_industry_names():
    region, m, f = it_theme()
    ai = {"layer": "Application development and maintenance", "description": "Builds and maintains software applications for clients.",
          "companies": [{"ticker": "SW0", "name": "Soft 0 Ltd", "verified": True}]}
    rest = [{**v, "layer": B.plain_industry(v["layer"]), "companies": [c for c in v["companies"] if c["ticker"] != "SW0"]} for v in m["value_chain"]]
    m2, _ = B.place_rest({**m, "value_chain": [ai] + rest}, "IT services", lambda s: None)
    names = [v["layer"] for v in m2["value_chain"]]
    assert names[0] == "Application development and maintenance" and not any(n in ("Computers - Software & Consulting", "IT services", "IT-enabled services") for n in names)
    assert B.plain_industry("Computers - Software & Consulting") == "IT services" and B.plain_industry("IT Enabled Services") == "IT-enabled services"
    v, slides = deck_of(region, m2, f, theme="IT services")
    assert all(not x.get("official") or x.get("basis") == "rest" for x in v["layers"])


def test_a_company_placed_after_the_map_has_its_own_words_and_figures_by_size():
    out, _ = B.place_rest(mapped(), "Defence", ABOUT.get)
    desc = B.described(out, ABOUT.get)
    el2 = next(c for v in desc["value_chain"] for c in v["companies"] if c["ticker"] == "EL2")
    assert el2["what"] == "Elec Two makes radars and electronic warfare systems for the armed forces"
    fm, figs = B.for_figures(out, cap=5)
    assert figs == {"shown": 5, "of": 7}                                   # the three the AI named, then the two largest placed ones
    assert {c["ticker"] for v in fm["value_chain"] for c in v["companies"]} == {"MS1", "SH1", "EL1", "EL2", "MS2"}
    assert set(B.to_describe(out)) >= {"EL2", "MS2", "SH2", "XX1"}


def test_a_stored_theme_from_the_older_rules_is_rebuilt_with_every_company_placed(api, monkeypatch):
    from app.intel import routes, theme_library
    from tests.test_themes_base import LIVE_US
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    monkeypatch.setattr(routes, "index_rows", lambda region: LIVE_US + [{"symbol": "VRT", "name": "Vertiv", "industry": "Electrical Industrial Apparatus", "market_cap": 40000}])
    old = {"sector": "Semiconductors", "generated_at": 5.0, "placements": {"checked": True, "pending": 0},
           "value_chain": [{"layer": "Chips", "companies": [{"ticker": "NVDA"}]}, {"layer": "Semiconductors & Related Devices", "official": True, "basis": "industry",
                                                                                  "companies": [{"ticker": "AMD"}]}], "ai": None}
    monkeypatch.setattr(B, "RULES", B.RULES - 3)
    theme_library.keep("US", "semiconductors", old)
    monkeypatch.setattr(B, "RULES", B.RULES + 3)
    assert theme_library.stored("US", "semiconductors") is None                   # the older rules' read is never served
    s = api.get("/research/sector?q=semiconductors&region=US").json()
    assert {c["ticker"] for v in s["value_chain"] for c in v["companies"]} == {"NVDA", "VRT", "AMD", "LRCX"}
    assert all(not v.get("official") or v.get("basis") == "rest" for v in s["value_chain"])
    assert not any(v["layer"] in ("Semiconductors & Related Devices", "Semiconductors") for v in s["value_chain"])


def test_a_map_from_the_older_prompt_with_few_layers_is_written_again_once():
    coarse = {"generated_at": 3.0, "value_chain": [{"layer": "Semiconductors", "companies": [{"ticker": "A"}]}, {"layer": "Named", "companies": [{"ticker": "B"}]}]}
    assert A.map_due(coarse) and not A.map_due({**coarse, "map_v": A.MAP_V}) and not A.map_due({"generated_at": 0, "value_chain": []})
    fine = {"generated_at": 3.0, "value_chain": [{"layer": f"L{i}", "companies": [{"ticker": f"T{i}"}]} for i in range(4)]}
    assert not A.map_due(fine)                                                     # four named layers with companies: kept
    from app.intel import ai
    src = open(ai.__file__).read()
    assert "4-6 value-chain layers" in src and "as many risks\nas tailwinds" in src and "production chain or business models" in src


# ---------- 2. the first deck of a theme waits for its map: 202, then the file, counted once ----------
def test_the_deck_answers_preparing_while_the_map_is_written_then_the_file_counted_once(api, monkeypatch):
    from app.intel import routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    real = T.map_for_deck
    state = {"pending": True}

    def fake(R, profile, region, q, wait=T.DECK_MAP_WAIT, pending=None):
        out = real(R, profile, region, q, wait=0.1)
        if pending is not None:
            pending.append(state["pending"])
        return out
    monkeypatch.setattr(T, "map_for_deck", fake)
    r = api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf")
    assert r.status_code == 202 and r.json() == {"preparing": True, "retry_after": T.DECK_RETRY, "message": "Preparing the deck: the AI map is being written."}
    assert api.usage.count("deck") == 0                                            # nothing counted until the file comes
    state["pending"] = False
    r = api.get("/research/theme-dive/deck?q=AI%20data%20centers&region=US&format=pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-" and api.usage.count("deck") == 1


# ---------- 3. charts follow the small-base rule; each layer's count shown ----------
def test_the_layer_chart_plots_only_medians_of_three_or_more_with_their_count():
    v = full_view()
    v["chain"]["rows"] = [{**r, "ebitda_n": n, "n": max(n, r.get("n") or 0)} for r, n in zip(v["chain"]["rows"], (1, 3))]
    v["chain"]["rows"][1]["ebitda"] = 12.0
    s = next(x for x in deck.theme_plan(v)[0] if x.title == "The value chain by layer")
    t = next(b for b in s.blocks if b["kind"] == "table")
    assert t["rows"][0][t["head"].index("EBITDA margin")] == "– (1)"
    charts = [b for b in s.blocks if b["kind"] == "hbars"]
    assert not charts or all(c.endswith(("(3)",)) or int(c.rsplit("(", 1)[1][:-1]) >= 3 for b in charts for c in b["cats"])


# ---------- 4. operating figures: a page only for three companies or more ----------
def test_operating_figures_of_one_or_two_companies_are_a_line_in_data_confidence_not_a_page():
    v = full_view()
    biz = {"metric": "Total sales", "unit": "units", "span": "month", "period": "2026-09", "filed": "2026-10-01", "value": 100, "prev": 90, "year_ago": 80,
           "change_prev": 11.1, "change_year": 25.0}
    v["business"] = {"layers": [{"layer": "Mining", "rows": [{**biz, "symbol": "S1", "name": "Solo Co"}]}], "subs": [], "held": []}
    slides = deck.theme_plan(v)[0]
    assert "Operating figures" not in [s.title for s in slides]
    rows = table_of(slides, "Data confidence")["rows"]
    assert ["Operating figures filed", "1 company filed operating figures between results: Solo Co.", "Too few to set side by side: no page of their own."] in rows
    v["business"]["layers"][0]["rows"] = [{**biz, "symbol": f"S{i}", "name": f"Co {i}"} for i in range(3)]
    assert "Operating figures" in [s.title for s in deck.theme_plan(v)[0]]


# ---------- 5. findings in whole sentences ----------
def test_findings_cards_never_cut_a_sentence_and_promoter_moves_read_plainly():
    assert deck.promoter_words(0, 8, 32) == "Promoters' stake fell at 8 of 32 companies last quarter and rose at none."
    assert deck.promoter_words(5, 2, 30) == "Promoters' stake rose at 5 of 30 companies last quarter and fell at 2."
    assert deck.promoter_words(0, 0, 9) == "Promoters' stake was unchanged at all 9 companies with a filing last quarter."
    long = [{"title": "What changed", "lines": ["A sentence about the quarter with many words in it, " * 6 + "end.", "Second sentence.", "Third sentence."], "note": "p. 4"}] * 6
    fitted = deck.whole_lines(long, (deck.M, deck.TOP, deck.CW, deck.BOT - deck.TOP), 3)
    cw, room = (deck.CW - 0.5) / 3, (deck.BOT - deck.TOP - 0.25) / 2
    assert all(deck.card_height(it, cw, False, deck.BODY_MIN) <= room or len(it["lines"]) == 1 for it in fitted)
    assert all(x in long[0]["lines"] for it in fitted for x in it["lines"])          # whole lines only, never a cut one


# ---------- 6 and 10: tailwinds and risks evenly, the evidence said in the row ----------
def test_tailwinds_and_risks_show_evenly_with_their_evidence_in_the_row():
    v = full_view()
    src = {"headline": "Scheme extended", "at": "2026-09-01", "outlet": "A daily", "url": "https://example.com/a"}
    v["tailwinds"] = [{"text": f"Tailwind {i}", "status": "current", "source": src if i == 3 else None} for i in range(6)]
    v["risks"] = [{"text": "Risk 0", "status": "general", "source": None}]
    s = next(x for x in deck.theme_plan(v)[0] if x.title == "Tailwinds and risks")
    items = next(b for b in s.blocks if b["kind"] == "flow")["items"]
    kinds = [it["tags"][0][0] for it in items]
    assert kinds[:2] == ["Tailwind", "Risk"] and kinds.count("Tailwind") <= deck.CLAIMS_EACH
    assert items[0]["text"] == "Tailwind 3" and items[0]["tags"][1][0] == "Dated source"                 # dated evidence first
    assert all(it["tags"][1][0] == "General background (AI, no dated source)" for it in items[1:])
    assert "the map names fewer risks (1) than tailwinds (6)" in s.subtitle


# ---------- 8. metric profiles by industry family ----------
def test_each_industry_family_has_its_metric_profile_in_one_place():
    ins = {**facts("INS", "Insurer Co", [1000, 1100, 1200, 1300], [15, 15, 15, 15], [80, 90, 100, 110]), "industry": ["Financial Services", "Insurance", "Life Insurance"]}
    nbfc = {**facts("NB", "Lender Co", [1000, 1100, 1200, 1300], [40, 40, 40, 40], [80, 90, 100, 110]), "industry": ["Financial Services", "Non Banking Financial Company (NBFC)"]}
    bank = {**facts("BK", "Bank Co", [1000, 1100, 1200, 1300], [30, 30, 30, 30], [80, 90, 100, 110]), "industry": ["Financial Services", "Banks", "Private Sector Bank"]}
    soft = {**facts("SW", "Banking Software Co", [1000, 1100, 1200, 1300], [25, 25, 25, 25], [80, 90, 100, 110]), "industry": ["Information Technology", "Software Products"]}
    assert [D.profile_of(f) for f in (ins, nbfc, bank, soft)] == ["insurer", "lender", "bank", "other"]
    for f in (ins, nbfc, bank):
        row = D.company_row("IN", f["symbol"], f)
        assert row["ebitda"] is None and row["roce"] is None and row["ev_ebitda"] is None and row["bank"] and row["roe"] == 12.0
    row = D.company_row("IN", "SW", soft)
    assert row["ebitda"] == 25.0 and not row["bank"] and row["profile"] == "other"
    assert set(D.PROFILES) == {"bank", "lender", "insurer", "other"} and "ebitda" not in D.PROFILES["insurer"]
