"""r66e (R66 theme engine): the LIVE12A theme findings. Each test fails before its fix and passes after (guards marked)."""
import json

import pytest

from app import computed, public_themes
from app.intel import routes as R
from app.intel import theme_base, theme_data, theme_library, theme_recheck, theme_routes
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    computed.reset_for_tests()
    theme_library._refreshing.clear()
    theme_recheck._asked.clear()
    yield built
    built["close"]()


def co(t, name, **kw):
    return {"ticker": t, "name": name, "what": f"{name} makes ships for navies", "verified": True, **kw}


def payload(sector="Ships", n=6, at=5):
    return {"sector": sector, "generated_at": at, "ai": None, "placements": {"checked": True, "placed": n},
            "summary": f"{sector} makers.",
            "value_chain": [{"layer": "Yards", "companies": [co(f"S{sector[:2].upper()}{i}", f"{sector} {i} Ltd") for i in range(n)]}],
            "sub_themes": []}


def keep(q, p):
    assert theme_library.keep("IN", q, json.loads(json.dumps(p)))


def put_dive(name, p, dive=None):
    key = theme_routes.dive_key("IN", name, {**p, "_library": name})
    computed.put(theme_library.DIVE, key, {"dive": dive or {"sector": p["sector"], "layers": []}, "pieces": {}}, label=p["sector"], region="IN",
                 meta={"q": name, "rules": theme_base.RULES})


# ---------- item 1: after a version change every stored theme is queued, and the job drains the queue one theme at a time ----------
def test_a_version_bump_queues_every_stored_theme_and_the_job_drains_it(w, monkeypatch):
    keep("ships", payload("Ships"))
    keep("rail", payload("Rail"))
    assert theme_recheck.queue() == 2                      # nothing queued before: both
    assert theme_recheck.queue() == 0                      # the same versions: nothing new
    worked = []

    def work(region, name):                                # the job's rebuild, as rebuild() keeps them: the read under today's rules, its dive
        worked.append(name)
        p = theme_library.stored(region, name)["payload"]
        put_dive(name, p)

    # both still lack a dive under today's versions: each is worked out once, then the queue is empty
    assert theme_recheck.step(work)["outcome"] == "rebuilt"
    assert theme_recheck.step(work)["outcome"] == "rebuilt"
    assert theme_recheck.step(work) is None and sorted(worked) == ["rail", "ship"]
    # the dive text bumped (a deploy): every stored theme queued again, the read stored under the older rules too
    monkeypatch.setattr(theme_data, "DIVE_TEXT", theme_data.DIVE_TEXT + 1)
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    assert theme_recheck.queue() == 2 and theme_recheck.state()["todo"] == 2
    assert theme_recheck.queued("IN", "ship")

    def work2(region, name):
        old = theme_library.older(region, name)
        keep(old["q"], old["payload"])
        put_dive(name, theme_library.stored(region, name)["payload"])
    theme_recheck.step(work2)
    # the queue is kept in the store: a restart (nothing in memory) goes on where it stopped
    theme_recheck._running.clear()
    assert theme_recheck._load()["todo"] and theme_recheck.step(work2)["outcome"] == "rebuilt"
    st = theme_recheck.state()
    assert st["todo"] == 0 and st["done"] == 2 and theme_recheck.current("IN", "ship") and theme_recheck.current("IN", "rail")


def test_a_theme_already_current_is_skipped_and_one_not_finished_is_tried_again_then_left(w, monkeypatch):
    keep("ships", payload("Ships"))
    put_dive("ship", theme_library.stored("IN", "ship")["payload"])
    keep("rail", payload("Rail"))
    theme_recheck.queue()
    called = []

    def never(region, name):
        called.append(name)
        raise theme_recheck.NotDone("its checks are not finished yet")
    outcomes = []
    while (x := theme_recheck.step(never)) is not None:
        outcomes.append((x["theme"][1], x["outcome"]))
    assert ("ship", "current") in outcomes and "ship" not in called          # current: skipped, nothing worked out
    assert called == ["rail"] * theme_recheck.TRIES                            # tried again at the end of the queue, then left
    assert theme_recheck.state()["left"] == {"IN|rail": "its checks are not finished yet"}


def test_a_theme_whose_map_is_not_stored_is_left_without_an_ai_map_being_written(w, monkeypatch):
    keep("ships", payload("Ships"))
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    asked = []
    monkeypatch.setattr(R, "sector_payload", lambda *a, **k: asked.append(a) or {})
    theme_recheck.queue()
    out = theme_recheck.step()
    assert out["outcome"] == "left" and "AI map is not stored" in out["why"] and asked == []


# ---------- item 3: a theme stored under older rules is served at once, saying so, and goes to the front of the queue ----------
def test_a_theme_stored_under_older_rules_is_served_at_once_and_asked_for_first(w, monkeypatch):
    keep("rail", payload("Rail"))
    keep("ships", payload("Ships"))
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    started = []
    monkeypatch.setattr(R, "sector_payload", lambda *a, **k: started.append(a) or (_ for _ in ()).throw(AssertionError("no live check")))
    got = json.loads(R.sector(q="Ships", region="IN", refresh=False, profile=None).body)
    assert got["sector"] == "Ships" and got["ai"] is None and got["older"]["rechecking"] is True and started == []
    assert theme_recheck._load()["todo"][0] == ["IN", "ship"]                 # first in the queue
    # the theme's other parts read the same stored read, marked older (never kept again from it)
    r, theme, m, _ = R.theme_map(None, "IN", "ships")
    assert m["_older"] is True and m["_library"] == "ship"
    # the deck waits for the re-check instead of printing the older read
    pending: list = []
    theme_routes.map_for_deck(R, None, "IN", "ships", pending=pending)
    assert pending == [True]


def test_no_dive_under_todays_versions_serves_the_newest_kept_one_marked_updating(w, monkeypatch):
    p = payload("Ships")
    keep("ships", p)
    put_dive("ship", theme_library.stored("IN", "ship")["payload"], {"sector": "Ships", "layers": [], "mark": "old"})
    monkeypatch.setattr(theme_data, "DIVE_TEXT", theme_data.DIVE_TEXT + 1)       # the dive text bumped: today's key misses
    queued = []
    monkeypatch.setattr(theme_routes, "_rebuild_behind", lambda r, t, m, key: queued.append(t) or True)
    monkeypatch.setattr(theme_routes, "BEHIND_ON", True)
    monkeypatch.setattr(theme_routes, "sources", lambda *a, **k: (_ for _ in ()).throw(AssertionError("worked out in the request")))
    m = {**theme_library.stored("IN", "ship")["payload"], "_library": "ship"}
    got = theme_routes.dive_of("IN", "ships", m, behind=True)
    assert got["mark"] == "old" and got["updating"] is True and queued == ["ships"]
    # a read stored under older rules: the re-check job is asked, and a dive worked out from it is never kept
    got = theme_routes.dive_of("IN", "ships", {**m, "_older": True}, behind=True)
    assert got["updating"] is True and theme_recheck._load()["todo"][0] == ["IN", "ship"]


def test_a_dive_worked_out_from_an_older_read_is_not_kept(w, monkeypatch):
    p = payload("Ships")
    keep("ships", p)
    m = {**theme_library.stored("IN", "ship")["payload"], "_library": "ship", "_older": True}
    monkeypatch.setattr(theme_data, "build", lambda *a, **k: {"sector": "Ships", "layers": []})
    monkeypatch.setattr(theme_routes, "sources", lambda *a, **k: type("S", (), {"pieces": {}})())
    monkeypatch.setattr(theme_routes, "dive_gaps", lambda *a, **k: [])
    monkeypatch.setattr(theme_routes, "membership_check", lambda *a, **k: {})
    kept = []
    monkeypatch.setattr(computed, "put", lambda *a, **k: kept.append(a[0]))
    theme_routes.dive_of("IN", "ships", m)
    assert theme_library.DIVE not in kept


def test_the_public_page_of_a_theme_stored_under_older_rules_says_it_is_checked_again(w, monkeypatch):
    keep("ships", payload("Ships"))
    monkeypatch.setattr(theme_base, "RULES", theme_base.RULES + 1)
    theme_recheck.queue()
    entry = public_themes.entries("IN")[0]
    html = public_themes.render(public_themes.view(entry, public_themes.payload(entry)))
    import html as H
    assert "data-older" in html and H.escape(public_themes.OLDER_LINE) in html and H.escape(public_themes.RECHECKING_LINE) in html


def test_guard_a_current_theme_says_nothing_of_an_older_check(w, monkeypatch):
    keep("ships", payload("Ships"))
    entry = public_themes.entries("IN")[0]
    assert "data-older" not in public_themes.render(public_themes.view(entry, public_themes.payload(entry)))
    got = json.loads(R.sector(q="Ships", region="IN", refresh=False, profile=None).body)
    assert "older" not in got


# ---------- item 2 (LIVE12A-001): a description fetched for another company is not the company's own words ----------
TOYO = ("Toyo Tire Corporation , commonly known as Toyo Tires, is a multinational tire and rubber products company based in Itami, Japan. "
        "The company owns and operates eight factories in Asia, North America, and Europe and distributes tires and automotive components "
        "through fourteen sales companies throughout the world.")
INNO = ("INNOvative Retail BV, is an upmarket Belgian department store chain that operates sixteen branches around Belgium. INNO HOLDINGS INC. "
        "(“INNO,” “we,” “us,” or “Company”) is an innovative technology company that engages in the business of recycled consumer electronic "
        "devices. We source and purchase pre-owned consumer electronic devices such as smartphones and tablets from suppliers.")


def test_a_description_that_opens_on_another_company_is_not_its_own_words():
    assert theme_base.own_part(TOYO, "TOYO Co., Ltd") == ""                       # wholly the tyre maker's: nothing of TOYO's own
    got = theme_base.own_part(INNO, "Inno Holdings Inc.")
    assert got.startswith("INNO HOLDINGS INC.") and "Belgian" not in got           # the other company's opening left off, its own words kept


def test_guard_a_companys_own_name_in_its_description_is_never_read_as_another_company():
    for text, name in [("OSI Systems, Inc. is an American company.", "OSI Systems Inc"),
                       ("Exxon Mobil Corporation is an American oil company.", "ExxonMobil Holdings Corp"),
                       ("The Coca-Cola Company is a beverage company.", "Coca-Cola Co"),
                       ("Rent the Runway is an American e-commerce platform.", "Rent the Runway, Inc."),
                       ("Larsen & Toubro Limited, commonly known as L&T, is an Indian company.", "Larsen & Toubro Ltd"),
                       ("Amazon.com, Inc. is an online retailer.", "Amazon.com Inc"),
                       ("Taiwan Semiconductor Manufacturing Company Limited (TSMC) is a foundry.", "Taiwan Semiconductor Manufacturing Co Ltd ADR"),
                       ("HDFC Bank Limited (also known as HDFC) is a bank.", "HDFC Bank Ltd"),
                       ("Microchip Technology Incorporated makes microcontrollers.", "Microchip Technology Inc"),
                       ("Incorporated in 2015, BigBloc Construction Ltd manufactures AAC blocks.", "BIGBLOC CONSTRUCTION LTD")]:
        assert not theme_base.names_other(text, name), name
        assert theme_base.own_part(text, name) == text


def test_a_stored_description_of_another_company_is_read_by_no_check_and_shown_by_no_page(w, monkeypatch):
    from app import db
    db.set_setting("theme:evidence:US:TOYO", json.dumps({"at": "2026-11-10T00:00:00+00:00", "about": TOYO, "industry": "", "v": theme_routes.ABOUT_V}))
    monkeypatch.setattr(theme_routes, "_index_name", lambda region, sym: "TOYO Co., Ltd")
    assert not theme_routes._stored_evidence("US", "TOYO").get("about")
    theme_routes.EVIDENCE_CACHE.pop("theme:evidence:US:TOYO")
    monkeypatch.setattr(theme_routes, "own_filings", lambda region, sym: "")
    assert theme_routes._about_reader("US", {"TOYO": "TOYO Co., Ltd"}, 0)("TOYO") is None


def test_a_dated_head_count_or_a_history_line_is_not_a_companys_own_words_about_its_work():
    assert theme_base.own_words("As of June 2010, the company employs approximately 3,180 personnel globally and includes subsidiary "
                                "companies Spacelabs Healthcare, Rapiscan Systems and OSI Optoelectronics", "OSI Systems Inc") == ""
    assert theme_base.own_words("The company rebranded to SMART Global Holdings (SGH) and held an initial public offering in 2017, after "
                                "spending years as a subsidiary of other companies", "Penguin Solutions Inc") == ""
    # guard: its work line stands, and a filing's bracket defining its own name is left out of the line
    assert theme_base.own_words("OSI Systems develops and markets security and inspection systems such as airport security X-ray machines",
                                "OSI Systems Inc")
    assert theme_base.own_words("Aeluma, Inc. (together with our subsidiary, “we,” “our,” “us,” or the “Company”) develops high-performance "
                                "photonic and electronic technologies for communications and sensing", "Aeluma Inc") \
        == "Aeluma, Inc. develops high-performance photonic and electronic technologies for communications and sensing"


# ---------- the live R65 decks' flags (coordinator's extra input) ----------
def test_a_removed_layer_says_the_one_reason_its_companies_moves_give(w):
    """agro p.7: "“Commodity chemicals” removed (18 companies: 18 to “Other fertilizers and agrochemical companies”)", no reason."""
    from app import deck
    from app.intel import theme_changes
    from scripts import deck_check
    why = "“Commodity chemicals” is made of its companies' official industry, and none of their own words says a word of its name: listed in the theme's “Other” group"
    was = {"layers": ["Commodity chemicals", "Crop protection", "Other fertilizers and agrochemical companies"],
           "cos": {s_: [s_, 0] for s_ in "ABCDE"} | {"F": ["F", 1], "G": ["G", 2]}}
    now = {"layers": ["Other fertilizers and agrochemical companies", "Crop protection"],
           "cos": {s_: [s_, 0] for s_ in "ABCDEG"} | {"F": ["F", 1]}, "mwhy": {s_: why for s_ in "ABCDE"}}
    ev, _ = theme_changes._layer_events(was, now)
    gone = next(x for x in ev if x["kind"] == "removed")
    assert gone["why"].startswith("it is made of its companies' official industry")
    line = deck.removed_said(gone)
    assert deck_check.check_text(f"layers changed 1: {line}.")["counts"]["layer vanished"] == 0
    # guard: companies moved out for reasons of their own give the layer none
    now["mwhy"]["A"] = "its own words hold no line that says what “Commodity chemicals” is"
    assert "why" not in next(x for x in theme_changes._layer_events(was, now)[0] if x["kind"] == "removed")


def test_a_stored_reason_cut_short_never_ends_on_a_joining_word():
    """usmetal p.11: '“ready-mix concrete and asphalt) and…”'."""
    from app.intel import theme_changes
    text = ("its own words: “is an aggregates-based construction materials provider” (what “Specialty alloys” is), and "
            "“ready-mix concrete and asphalt) and other products for heavy civil construction”, not what it names")
    got = theme_changes.clip_words(text, text.index(" other products") + 3)
    assert got.endswith("asphalt)…”") and not got.rstrip("…”").endswith(" and")


def test_recycled_or_pre_owned_consumer_goods_say_a_resale_layer():
    """retail deck_diff: Inno Holdings' "the business of recycled consumer electronic devices" read as no word of "Resale, rental and small
    digital commerce"."""
    from scripts import release_gate as G
    layer = "Resale, rental and small digital commerce"
    assert G.shares(layer, "INNO HOLDINGS INC. is an innovative technology company that engages in the business of recycled consumer electronic devices")
    assert G.shares(layer, "We sell pre-owned luxury goods online")
    # guard: a recycler of materials or a maker says nothing of it
    assert not G.shares(layer, "We make recycled plastic pellets for packaging makers")


# ---------- item 4 (LIVE12A-006): one money unit on the app's operating figures; a move's quote says what the company makes ----------
def test_the_apps_operating_figures_are_in_one_money_unit_as_the_decks():
    sec = {"layers": [{"layer": "Large banks", "rows": [{"symbol": "A", "metric": "Deposits", "unit": "₹ billion", "value": 33275.0, "prev": 32000.0},
                                                         {"symbol": "B", "metric": "Deposits", "unit": "₹ crore", "value": 651491.0}]},
                      {"layer": "Small banks", "rows": [{"symbol": "C", "metric": "Advances", "unit": "Rs billion", "value": 1702.0}]}],
           "subs": [{"name": "Digital", "rows": []}], "companies": 3}
    got = theme_routes.one_unit_section(sec)
    rows = [r for g in got["layers"] for r in g["rows"]]
    assert {r["unit"] for r in rows} == {"₹ crore"} and rows[0]["value"] == 3327500.0 and rows[0]["prev"] == 3200000.0
    assert rows[2]["value"] == 170200.0 and got["subs"] == [{"name": "Digital", "rows": []}] and got["companies"] == 3


def test_a_moves_quote_leaves_off_the_founding_history_and_says_what_the_company_makes():
    from app.intel import theme_changes
    q = theme_changes.first_sentence("Incorporated in 2015, BigBloc Construction Ltd manufactures, sells and marketing of AAC Blocks Business "
                                     "Overview : BBCL is a manufacturer of AAC (Aerated Autoclave Concrete) block and related products manufacturing "
                                     "company in India")
    assert q.startswith("BigBloc Construction Ltd manufactures") and "AAC Blocks" in q and not q.endswith("manufactures")
    assert theme_changes.first_sentence("It sells to the U.S. Army and others. Then more.") == "It sells to the U.S. Army and others"   # guard


# ---------- item 5 (LIVE12A-009/014) ----------
def test_a_total_from_a_thousand_billion_up_is_said_in_trillions():
    from app.deepdive import money
    assert money(12_265_000, "$ million") == "$12.3 tn" and money(999_999, "$ million") == "$1.00 tn"
    assert money(215_938, "$ million") == "$215.9 bn" and money(999.6, "$ million") == "$1.00 bn"        # guard: billions as before


def test_a_theme_posts_excerpt_leads_with_its_finding():
    line = ("Among the 4 layers with at least 5 companies with the figure and one kind of business, median EBITDA margin is highest in "
            "Foundries (19.1%) and lowest in Packaging (8.2%), a gap of 10.9 points. Two more sentences.")
    got = theme_data.finding_first(line)
    assert got.startswith("Median EBITDA margin is highest in Foundries (19.1%)")
    assert "among the 4 layers with at least 5 companies with the figure and one kind of business." in got and got.endswith("Two more sentences.")
    assert theme_data.finding_first("Median ROE by layer: A 12%.") == "Median ROE by layer: A 12%."          # guard


def test_the_public_page_shows_the_market_values_the_app_shows(w, monkeypatch):
    p = payload("Ships")
    keep("ships", p)
    sym = p["value_chain"][0]["companies"][0]["ticker"]
    put_dive("ship", theme_library.stored("IN", "ship")["payload"],
             {"sector": "Ships", "as_of": "2026-11-17", "layers": [{"layer": "Yards", "companies": [{"symbol": sym, "cap": 97122.0}]}]})
    monkeypatch.setattr(public_themes, "_index_caps", lambda region: {sym: 97008.0})
    entry = public_themes.entries("IN")[0]
    v = public_themes.view(entry, public_themes.payload(entry))
    row = next(c for x in v["layers"] for c in x["companies"] if c["symbol"] == sym)
    assert row["cap_v"] == 97122.0 and v["prices"] == "2026-11-17"
