"""Lane e80 (Release 79): theme-engine items from LIVE16A and the R78 decks. Each test fails before its fix and passes after."""
import json

from app import computed
from app.intel import routes as R
from app.intel import theme_changes, theme_data, theme_library, theme_recheck, theme_routes
from tests.test_r66e_fixes import keep, payload, put_dive, w  # noqa: F401 (the stored-library fixture)


# ---------- 1. LIVE16A-003: a re-checked theme's dive is current within the re-check ----------
def _fake_build(monkeypatch, size: int, mark: str = "new"):
    """theme_data.build giving a dive of about `size` characters (Semiconductors' was 710 KB on 17 Nov)."""
    def build(r, theme, fm, src):
        rows = [{"symbol": f"S{i}", "name": f"Co {i}", "revenue": 100.0, "years": "y" * 900} for i in range(max(1, size // 1000))]
        return {"sector": "Ships", "mark": mark, "as_of": "2026-11-18", "layers": [{"layer": "Yards", "companies": rows}]}
    monkeypatch.setattr(theme_data, "build", build)
    monkeypatch.setattr(theme_routes, "sources", lambda *a, **k: type("S", (), {"pieces": {}, "about": lambda self, s_: None})())
    monkeypatch.setattr(theme_routes, "dive_gaps", lambda *a, **k: [])
    monkeypatch.setattr(theme_routes, "membership_check", lambda *a, **k: {})
    monkeypatch.setattr(theme_routes, "auto_post", lambda *a, **k: None)
    monkeypatch.setattr(theme_changes, "record", lambda *a, **k: None)


def test_e80_a_dive_larger_than_the_old_store_bound_is_kept_and_served_current_after_the_recheck(w, monkeypatch):
    keep("ships", payload("Ships"))
    p = theme_library.stored("IN", "ship")["payload"]
    # the last dive that had fitted, kept under the versions before the deploy
    old_key = theme_routes.dive_key("IN", "ship", {**p, "_library": "ship"})[:-1] + ["td0"]
    computed.put(theme_library.DIVE, old_key, {"dive": {"sector": "Ships", "mark": "old", "layers": []}, "pieces": {}}, label="Ships",
                 region="IN", meta={"q": "ship", "rules": 0})
    _fake_build(monkeypatch, 720_000)
    theme_recheck.queue()
    out = theme_recheck.step()
    assert out["outcome"] == "rebuilt", out
    theme_routes._UNKEPT.clear()                          # another process: only the store
    monkeypatch.setattr(theme_routes, "BEHIND_ON", True)
    monkeypatch.setattr(theme_routes, "_rebuild_behind", lambda *a: True)
    m = theme_routes.with_descriptions("IN", theme_routes.checked("IN", "ships", {**p, "_library": "ship"}))
    got = theme_routes.dive_of("IN", "ships", m, behind=True)
    assert got["mark"] == "new" and not got.get("updating")


def test_e80_a_dive_the_store_refuses_is_served_from_the_process_never_the_older_one(w, monkeypatch):
    keep("ships", payload("Ships"))
    p = theme_library.stored("IN", "ship")["payload"]
    m = theme_routes.with_descriptions("IN", theme_routes.checked("IN", "ships", {**p, "_library": "ship"}))
    _fake_build(monkeypatch, 3000)
    monkeypatch.setattr(computed, "KIND_MAX", {})
    monkeypatch.setattr(computed, "ENTRY_MAX", 1000)
    theme_routes.dive_of("IN", "ships", m, rebuild=True)
    monkeypatch.setattr(theme_routes, "BEHIND_ON", True)
    monkeypatch.setattr(theme_routes, "_rebuild_behind", lambda *a: True)
    got = theme_routes.dive_of("IN", "ships", m, behind=True)
    assert got["mark"] == "new" and not got.get("updating")


def test_e80_a_mark_the_rebuild_could_not_clear_does_not_keep_the_dive_updating(w, monkeypatch):
    """Camden: its page's revenue apart from its piece's after the rebuild too; the dive was marked stale on every read."""
    keep("ships", payload("Ships"))
    p = theme_library.stored("IN", "ship")["payload"]
    m = theme_routes.with_descriptions("IN", theme_routes.checked("IN", "ships", {**p, "_library": "ship"}))
    _fake_build(monkeypatch, 3000)
    monkeypatch.setattr(theme_routes, "pages_restated", lambda r, d: ["CPT"])
    theme_routes.dive_of("IN", "ships", m, rebuild=True)
    behind = []
    monkeypatch.setattr(theme_routes, "BEHIND_ON", True)
    monkeypatch.setattr(theme_routes, "_rebuild_behind", lambda *a: behind.append(1) or True)
    got = theme_routes.dive_of("IN", "ships", m, behind=True)
    assert not got.get("updating") and behind == []
    # guard: a company marked since the dive was kept still works it out again
    monkeypatch.setattr(theme_routes, "pages_restated", lambda r, d: ["CPT", "ESS"])
    got = theme_routes.dive_of("IN", "ships", m, behind=True)
    assert got.get("updating") is True and behind == [1]


# ---------- 4. LIVE16A-004 / LIVE16B-002: theme market values take the stored page's share count ----------
def test_e80_a_split_since_the_piece_takes_the_pages_share_count_not_a_4x_low_value():
    # CrowdStrike's piece kept before its 4-for-1 split (254.6 m shares at $950), its page rebuilt on 1,023.9 m shares
    piece = {"price": 950.0, "price_at": "2026-08-14", "market_cap": 241_870.0, "pe": 400.0, "years": []}
    row = {"symbol": "CRWD", "price": 237.03, "price_at": "2026-11-18", "market_cap": 242_700.0, "pe": 399.0}
    got = theme_data.at_close(piece, row, "US", "CRWD")
    assert abs(got["market_cap"] - 242_700.0) < 1 and got["price"] == 237.03 and got["price_at"] == "2026-11-18" and got["pe"] == 399.0


def test_e80_tcs_in_the_theme_is_its_pages_count_times_the_close():
    # the piece's 363.7 cr shares; the page's (screens' index row) 361.8 cr at the same close: ₹8.48 lakh cr at ₹2,342.70
    piece = {"price": 2342.70, "price_at": "2026-11-19", "market_cap": 2342.70 * 363.7, "years": []}
    row = {"symbol": "TCS", "price": 2342.70, "price_at": "2026-11-19", "market_cap": 2342.70 * 361.8}
    got = theme_data.at_close(piece, row, "IN", "TCS")
    assert round(got["market_cap"] / 1e5, 2) == 8.48
    # guard: a value the page's within rounding is left as it is
    near = {**piece, "market_cap": 2342.70 * 361.81}
    assert theme_data.at_close(near, row, "IN", "TCS")["market_cap"] == near["market_cap"]


# ---------- 2. LIVE16A-002: the encyclopedia's sentences are never a company's own words ----------
ENCYC = [
    ("As the largest U.S.-based oil and gas company, ExxonMobil is the eighth-largest company by revenue in the U.S. and 13th-largest in the world",
     "Exxon Mobil Corp"),
    ('It is one of the oil and gas "supermajors" and one of the world\'s largest companies measured by revenues and profits', "BP p.l.c."),
    ("In Canada, it is a major producer of crude oil", "Imperial Oil Ltd"),
    ("It specializes in production of synthetic crude from oil sands", "Suncor Energy Inc"),
    ("Wipro's services include cloud computing, computer security, digital transformation, artificial intelligence, robotics, data analytics, "
     "and other technologies", "Wipro Ltd"),
    ("It provides endpoint security, threat intelligence, and cyberattack response services", "CrowdStrike Holdings, Inc."),
    ("We expanded our addressable market with the acquisition of ISP (as defined below)… in December 2016", "LightPath Technologies Inc"),
    ("Its businesses cover the entire oil and gas chain, from crude oil and natural gas exploration and production to power generation",
     "TotalEnergies SE"),
]


def test_e80_each_encyclopedia_sentence_seen_live_is_no_line_of_own_words():
    from app.intel import theme_base
    for text, name in ENCYC:            # each as a US company's stored words are read (theme_routes.own_got), then quoted
        theme_routes.own_got("US", "X", {"about": text, "at": "2026-11-19"}, name)
        assert theme_base.own_words(text, name) == "", text
    # guard: the filings' own voice stays
    assert theme_base.own_words("We provide endpoint security software to enterprises", "CrowdStrike Holdings, Inc.")
    assert theme_base.own_words("Exxon Mobil Corporation explores for and produces crude oil and natural gas", "Exxon Mobil Corp")
    assert theme_base.own_words("The Company is engaged in the manufacture of cement", "ACC Ltd")
    assert theme_base.own_words("It manufactures steel wheels for cars", "Steel Strips Wheels Ltd")      # an Indian profile's own


def test_e80_the_encyclopedia_extract_is_kept_apart_by_the_reader_and_never_quoted(monkeypatch):
    """The source: theme_routes.evidence_reader joins the encyclopedia's extract after a thin annual-report opening; it now keeps it apart."""
    from app.intel import theme_base, theme_check
    filed = "We make widgets."
    wiki = "Acme Widgets is a leading maker of precision widgets for aircraft builders across North America."
    stored = {}
    monkeypatch.setattr(theme_routes, "filed_business", lambda *a, **k: (filed, False))
    hub = type("H", (), {"wiki": type("W", (), {"company": staticmethod(lambda name, cached=False: {"title": "Acme Widgets", "extract": wiki})})(),
                         "screener": None})()
    monkeypatch.setattr(theme_routes, "_routes", lambda: type("R", (), {"hub": hub})())
    monkeypatch.setattr(theme_routes, "fits_company", lambda *a: True)
    monkeypatch.setattr(theme_routes, "own_filings", lambda *a: "")
    monkeypatch.setattr(theme_routes.db, "get_setting", lambda k: stored.get(k))
    monkeypatch.setattr(theme_routes.db, "set_setting", lambda k, v: stored.__setitem__(k, v))
    monkeypatch.setattr(theme_routes.EVIDENCE_CACHE, "get", lambda k: None)
    monkeypatch.setattr(theme_check, "gather_evidence", lambda syms, read, budget=None: ({s_: read(s_) for s_ in syms}, []))
    got = theme_routes.evidence_reader("US", {"ACME": "Acme Widgets Inc"})(["ACME"])[0]["ACME"]
    rec = json.loads(stored["theme:evidence:US:ACME"])
    assert rec["wiki"] == wiki and wiki in got["about"]          # kept as evidence, and apart
    theme_base._ENCYC_SEEN.clear()
    theme_base._ENCYC_PRE.clear()
    theme_routes.own_got("US", "ACME", rec, "Acme Widgets Inc")    # every reader of the stored words reads it this way
    assert not theme_base.has_own_line(wiki, "Acme Widgets Inc") and theme_base.own_words(wiki, "Acme Widgets Inc") == ""
    assert theme_base.own_words(wiki[:70], "Acme Widgets Inc") == ""          # a line cut short of the sentence's end too


# ---------- 3. LIVE16A-006: a move's printed reason is of the layer it moved to ----------
def test_e80_a_moves_reason_names_the_layer_it_moved_to_never_a_third_one():
    rows = [{"symbol": "ESS", "name": "Essex Property Trust", "from": "Other real estate investment trust companies", "to": "Residential landlords",
             "why": "its own words say it sells what “Manufactured housing and RV communities” is"},
            {"symbol": "AMH", "name": "American Homes 4 Rent", "from": "Other real estate investment trust companies", "to": "Residential landlords",
             "why": "the map placed it in “Manufactured housing and RV communities” and its own words say what no other layer sells"},
            {"symbol": "ARR", "name": "Armour Residential REIT", "from": "Other real estate investment trust companies", "to": "Mortgage REITs",
             "why": "its own words don't say it sells what “Digital infrastructure owners” is (“owners”), nor does its official industry (REITs)"},
            {"symbol": "OSIS", "name": "OSI Systems", "from": "Fabless chip design", "to": "Makers of their own products",
             "why": "its own words don't say it sells what “Fabless chip design” is (“design”)"}]
    words = {"ARR": "ARMOUR Residential REIT, Inc. invests primarily in residential mortgage backed securities issued or guaranteed by a "
                    "United States government-sponsored enterprise."}
    got = {r["symbol"]: r["why"] for r in theme_changes.reasoned([{"moved": rows}], words.get, lambda s_: "")[0]["moved"]}
    assert got["ESS"] == "its own words say it sells what “Residential landlords” is"
    assert got["AMH"].startswith("the map placed it in “Residential landlords”")
    assert "Digital infrastructure" not in got["ARR"] and "mortgage backed securities" in got["ARR"]
    assert got["OSIS"] == rows[3]["why"]                 # guard: why it left the layer it moved from stands


def test_e80_a_move_said_from_its_words_quotes_its_work_never_who_manages_it_or_its_reit_election():
    words = {"ICR": "Sound Point CRE is a subsidiary of Sound Point Capital Management, LP. We originate, acquire and manage commercial real "
                    "estate debt investments, including first mortgage loans.",
             "MDRR": "We revoked our REIT election effective January 1, 2026. We own and operate retail, flex and hotel properties in the "
                     "southeastern United States.",
             "BREIT": "We are the sole general partner of BREIT Operating Partnership, L.P."}
    rows = [{"symbol": s_, "name": s_, "from": "Other real estate investment trust companies", "to": "Towers, data centres and niche property"}
            for s_ in words]
    got = {r["symbol"]: r["why"] for r in theme_changes.reasoned([{"moved": rows}], words.get, lambda s_: "")[0]["moved"]}
    assert "Sound Point" not in got["ICR"] and "first mortgage loans" in got["ICR"]
    assert "REIT election" not in got["MDRR"] and "retail, flex and hotel" in got["MDRR"]
    assert "general partner" not in got["BREIT"] and "no line of its own words" in got["BREIT"]


def test_e80_a_flag_kept_after_a_stored_reason_is_never_printed():
    e = {"added": [{"symbol": "IHRT", "name": "iHeartMedia, Inc.", "layer": "Other media and entertainment companies",
                    "why": "filed under an official industry of the theme; True"}]}
    assert theme_changes.reasoned([e])[0]["added"][0]["why"] == "filed under an official industry of the theme"


# ---------- 8. LIVE16A-019: no empty "Membership" label on a phone card ----------
def test_e80_a_description_verified_row_carries_no_empty_membership_label(monkeypatch):
    from app import public_themes
    v = {"region": "US", "label": "REITs", "slug": "reits", "name": "reit", "evidence": None, "older": False, "rechecking": False,
         "members": 2, "all": 2, "day": None, "prices": None, "indexable": True, "summary": "",
         "layers": [{"name": "Office landlords", "evidence": None, "companies": [
             {"name": "Boston Properties", "page": None, "symbol": "BXP", "cap": "$11B", "revenue": None, "evidence": "description_verified"},
             {"name": "Paramount Group", "page": None, "symbol": "PGRE", "cap": "$1B", "revenue": None, "evidence": "industry_code_supported"}]}]}
    html = public_themes.render(v)
    assert html.count('data-label="Membership"') == 1 and '<td class="l"></td>' in html
    assert ".cotbl[data-stack] td:empty{display:none}" in html


# ---------- 5. LIVE16A-007: a company listed under two symbols is one row on the app's members table and the public page ----------
def test_e80_empire_state_realty_is_one_row_where_the_dive_found_it_twice(w, monkeypatch):
    p = payload("Ships")
    p["value_chain"][0]["companies"][1] = {**p["value_chain"][0]["companies"][1], "ticker": "ESBA", "name": "Empire State Realty OP, L.P."}
    keep("ships", p)
    stored = theme_library.stored("IN", "ship")["payload"]
    put_dive("ship", stored, {"sector": "Ships", "layers": [], "duplicates": [{"symbol": "ESBA", "kept": "SSH0", "kept_name": "Ships 0 Ltd"}]})
    theme_routes._DUPS.clear()
    got = json.loads(R.sector(q="Ships", region="IN", refresh=False, profile=None).body)
    syms = [c["ticker"] for v in got["value_chain"] for c in v["companies"]]
    assert "ESBA" not in syms and "SSH0" in syms
    from app import public_themes
    entry = public_themes.entries("IN")[0]
    view = public_themes.view(entry, public_themes.payload(entry))
    assert "ESBA" not in [c["symbol"] for v in view["layers"] for c in v["companies"]]


def test_e80_the_public_tally_adds_up_with_the_members_whose_words_describe_other_work():
    from app import public_themes
    dt = {"description_verified": 266, "industry_code_supported": 12, "not_confirmed": 6, "membership_unverified": 0}
    tally = {k: int(dt.get(k) or 0) for k in public_themes.EVIDENCE_PUBLIC}
    assert sum(tally.values()) == 284
    assert public_themes.evidence_said(tally) == "266 description-verified, 12 industry-supported, 6 own words describe other work, 0 not checked"


# ---------- 5. LIVE16A-011: a layer with members but none in the figures says how many it lists ----------
def test_e80_a_layer_none_of_whose_members_is_in_the_figures_window_keeps_its_count(w, monkeypatch):
    keep("ships", payload("Ships"))
    p = theme_library.stored("IN", "ship")["payload"]
    m = theme_routes.with_descriptions("IN", theme_routes.checked("IN", "ships", {**p, "_library": "ship"}))
    m = {**m, "value_chain": m["value_chain"] + [{"layer": "IT services", "companies": [{"ticker": f"IT{i}", "name": f"IT {i}"} for i in range(5)]}]}
    _fake_build(monkeypatch, 3000)
    real = theme_data.build
    monkeypatch.setattr(theme_data, "build", lambda r, t, fm, src: {**real(r, t, fm, src), "layers": [{"layer": "IT services", "companies": [], "placed": 0}]})
    got = theme_routes.dive_of("IN", "ships", m, rebuild=True)
    assert got["layers"][0]["placed"] == 5


# ---------- 7. the R78 decks ----------
def test_e80_a_layer_of_companies_all_based_abroad_says_so_plainly():
    from app import deck
    outs = [(f"Bank {i}", "adjacent participant, listed in the US but based abroad") for i in range(31)]
    line, _ = deck.roll_line([], outs)
    assert line.startswith("Every company of this layer is based abroad") and "all 31 are shown, and none is in the theme's totals" in line
    assert "In the layer's calculations (0 of" not in line
    # guard: a layer with members in its calculations keeps its roll
    line, _ = deck.roll_line([("Amkor Technology", "")], outs[:2])
    assert line.startswith("In the layer's calculations (1 of 3)")


def test_e80_layers_of_one_profile_that_state_none_of_its_measures_are_said_once():
    from app import deck
    from app.intel import sector_ops
    pid = next(iter(sector_ops.BY_PROFILE))
    rows = [{"layer": f"Layer {i}", "ops": {"profile": pid, "measures": [], "none": ["a", "b"]}} for i in range(5)]
    got = deck.profile_summary(rows)
    # (updated on purpose, e81: the R79 decks' "profile unsaid": each layer still names itself, briefly after the first)
    assert got.count("none of its 2 measures stated") == 1 and got.count("none of them either") == 4
    assert all(f"Layer {i}" in got for i in range(5))


def test_e80_a_layer_name_that_only_changes_case_is_no_rename():
    e = {"layers": [{"kind": "renamed", "from": ["It services"], "to": ["IT services"], "n": 5},
                    {"kind": "renamed", "from": ["Chip design"], "to": ["Fabless chip design"], "n": 30}]}
    got = theme_changes.reasoned([e])[0]["layers"]
    assert [x["to"][0] for x in got] == ["Fabless chip design"]


def test_e80_an_older_entry_of_a_theme_kept_now_under_another_name_is_no_page_of_its_own(w, monkeypatch):
    from app import public_themes
    from app.intel import theme_base
    keep("public sector banks", payload("Banks"))           # kept under the older rules by this name
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    assert theme_library.keep("IN", "state owned banks", json.loads(json.dumps(payload("Banks"))))      # today's, under another name
    real = theme_library.find
    monkeypatch.setattr(theme_library, "find", lambda r, q: real(r, "state owned banks") if theme_library.normalise(q, r) == "public bank" else real(r, q))
    rows = public_themes.entries("IN")
    assert [e["name"] for e in rows] == ["state owned bank"] and "public-bank" in rows[0]["aliases"]
    # guard: an older entry no theme of today's rules stands for keeps its page (saying it is being checked again)
    monkeypatch.setattr(theme_library, "find", lambda r, q: None)
    assert sorted(e["name"] for e in public_themes.entries("IN")) == ["public bank", "state owned bank"]


def test_e80_versions():
    from app import deck
    from app.intel import sector_metrics, theme_base
    assert theme_base.RULES == 80 and theme_routes.PLACE_CARRY[80] == 79 and theme_routes.PLACE_CARRY[79] == 78 and theme_routes.PLACE_CARRY[78] == 77 and theme_routes.PLACE_CARRY[77] == 76 and theme_routes.PLACE_CARRY[76] == 75 and theme_routes.PLACE_CARRY[75] == 74 and theme_routes.EARLIER_MAX == 35          # e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose)
    assert theme_data.DIVE_TEXT == 58 and deck.THEME_DECK_VERSION == 98 and sector_metrics.VERSION == 3          # deck101 (changed on purpose, every live R99 deck read again 27 Nov: dive text 58, deck 98, Release 102 taking deck 97); deck99 (changed on purpose, the deck96 audit's open items, 27 Nov: dive text 57, deck 96); rel98 (fix98 and map98 together, 27 Nov: dive text 56, deck 95, changed on purpose); map98 (a company of the map's own layers whose own first business sentence states another principal business listed as other work); fix98 (changed on purpose, members no longer listed: dive text 55, deck 94); deck96 (changed on purpose, every live theme deck checked 26 Nov: dive text 54, deck 93); e90 (changed on purpose, the live R90 alcobev deck: dive text 53 so the kept dives carry the demerger and revenue-basis fixes); deck89 (changed on purpose, owner 25 Nov: the theme deck remade as research): deck 92; e89 (the owner's Alcoholic beverages deck, 25 Nov): RULES 80, PLACE_CARRY[80] = 79, EARLIER_MAX 35, dive text 52 (changed on purpose, e89); e85 (LIVE21A, the R84 decks): deck 91, dive text 51 (updated on purpose); e84 (LIVE20A, the R82 decks): RULES 79, PLACE_CARRY[79] = 78, EARLIER_MAX 34, deck 90, dive text 50, blog GEN 12 (updated on purpose); e83 (LIVE19A, the R81 decks): RULES 78, PLACE_CARRY[78] = 77, EARLIER_MAX 33, deck 89, dive text 49, blog GEN 11 (updated on purpose); e82 (LIVE18A, the R80 decks): RULES 77, PLACE_CARRY[77] = 76, EARLIER_MAX 32, deck 88, dive text 48 (updated on purpose); e81 (LIVE17A, the R79 decks): RULES 76, PLACE_CARRY[76] = 75, EARLIER_MAX 31, deck 87, dive text 47 (updated on purpose)
    assert computed.entry_max(theme_library.DIVE) >= 4 * 1024 * 1024 and computed.entry_max("theme") == computed.ENTRY_MAX
