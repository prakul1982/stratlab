"""Lane r69e (R69 theme engine): the LIVE13A theme findings and the live R67 deck flags.

001 a move's reason must quote words that say the layer's work: OSI Systems (airport X-ray and inspection systems) moved into "Fabless chip
    design" because "designer" says the name's last word; Burnpur Cement ("now completely non-operational"), Kanoria (A.C. pressure pipes) and
    BigBloc (AAC blocks) moved from "Other" into "Cement integrated producers (smaller)" by their official industry and way of earning, a half
    of a layer split by market value never judged.
"""
import json
import pathlib
import sys

import pytest

from app.intel import theme_base as B
from tests.test_r66e_fixes import keep, payload, w  # noqa: F401 (the stored-library fixture)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
R69 = pathlib.Path(__file__).resolve().parent / "fixtures" / "themes_live" / "r69"

OSI_10K = ("OSI Systems, Inc. is a vertically integrated designer and manufacturer of specialized electronic systems and components for "
           "critical applications in the security, healthcare, defense and aerospace industries. We sell our products and provide related "
           "services in diversified markets, including homeland security, healthcare, defense and aerospace.")
BURNPUR = ("Burnpur Cement Ltd is a formerly operating cement manufacturer that is now completely non-operational. All production assets "
           "have been sold, operating revenue has remained nil since FY25, and management and auditors assess the company as not a going "
           "concern. Historically, BCL manufactured Portland Slag Cement, OPC and PPC products for housing and infrastructure.")


def _replay(path: pathlib.Path, edit=None):
    import release_gate as G
    d = G.load(path)
    if edit:
        edit(d)
    with G.offline():
        out, _ = G.engine(d)
    return d, out


def _where(out: dict, sym: str):
    for v in out["value_chain"]:
        for c in v["companies"]:
            if c["ticker"] == sym:
                return v["layer"], c
    return None, None


def _semis_layers():
    d = json.loads((R69 / "semis.json").read_text())
    return [v for v in d["value_chain"] if not v.get("official")]


def test_a_head_naming_an_act_is_said_only_with_what_it_is_done_to():
    """Fails before: "a vertically integrated designer and manufacturer of specialized electronic systems" sold what "Fabless chip design"
    is ("designer" says "design") and what "Analog and power integrated device makers" is ("vertically integrated" says "integrated")."""
    named = _semis_layers()
    tw = B.kind_stems("Semiconductors")
    said = [v["layer"] for v in named if B.sells_layer(v, named, B.sold_text(OSI_10K, "Osi Systems Inc"), None, tw)]
    assert "Fabless chip design" not in said and "Analog and power integrated device makers" not in said, said
    # (guard) a chip designer's words still say it; so do an analog chip maker's
    fab = B.sold_text("Ambarella is a fabless semiconductor design company that designs video processing chips.", "Ambarella Inc")
    assert "Fabless chip design" in [v["layer"] for v in named if B.sells_layer(v, named, fab, None, tw)]
    ana = B.sold_text("We design and manufacture analog and power integrated circuits and discrete power devices.", "X Corp")
    assert "Analog and power integrated device makers" in [v["layer"] for v in named if B.sells_layer(v, named, ana, None, tw)]


def test_osi_with_its_10k_words_is_not_put_back_into_fabless_chip_design_on_the_live_input():
    """Fails before: the replay of the live R67-era Semiconductors input, OSI Systems' stored words its 10-K's opening, put it back into
    "Fabless chip design" ("its own words say it sells what “Fabless chip design” is"), the layer an earlier re-check moved it out of."""
    d, out = _replay(R69 / "semis.json", lambda d: d["evidence"].__setitem__("OSIS", OSI_10K))
    lay, c = _where(out, "OSIS")
    assert lay != "Fabless chip design", (lay, c)
    why = (c.get("refit") or {}).get("why") or ""
    assert "Fabless chip design" in why and "own words" in why, why
    # (guard) the chip designers of the layer stay in it
    for s in ("NVDA", "AVGO", "QCOM"):
        if s in {x["ticker"] for v in d["value_chain"] for x in v["companies"] if v["layer"] == "Fabless chip design"}:
            assert _where(out, s)[0] == "Fabless chip design", s


def test_words_that_say_the_company_runs_no_business_now():
    assert "non-operational" in B.not_operating(BURNPUR)
    assert B.not_operating("Orangekloud USA has been dormant during the years ended December 31, 2024 and 2025.")
    # (guard) a closed unit, a former product or a past discontinued segment is no such word
    for t in ("ACC Limited manufactures cement. It has discontinued operations of its ready-mix unit in Goa.",
              "The company suspended production at its Bhilai plant for maintenance in 2025.",
              "We make semiconductors. Results from discontinued operations are shown separately.",
              "KCP is engaged in the business of manufacture and sale of cement, sugar, heavy engineering."):
        assert B.not_operating(t) == "", t


def test_the_themes_own_product_named_as_what_a_company_makes():
    tw = B.kind_stems("Cement")
    for t in ("engaged in the business of manufacture and sale of cement, sugar, heavy engineering",
              "manufacturing and selling of Cement and Ready Mix Concrete", "operates cement plants in Rajasthan",
              "produces Portland Cement under the brand X"):
        assert B.says_theme_product(t, tw), t
    for t in ("manufacturing of A.C. Pressure Pipes, Couplings, A.C. Sheet & Moulded Goods and laying & jointing of Asbestos Cement Products. "
              "KEIL manufactures Asbestos Cement (A.C.) Pressure Pipes, A.C. Corrugated Roofing Sheets",
              "manufactures, sells and marketing of AAC Blocks. BBCL is a manufacturer of AAC (Aerated Autoclave Concrete) block"):
        assert not B.says_theme_product(t, tw), t
    # a former business is no word of what it makes now; its name is no word of it either
    assert "Portland" not in B.business_text(BURNPUR, "Burnpur Cement Ltd")
    assert "cement" in B.business_text("Shree Digvijay Cement Co Ltd is engaged in the manufacture of cement.", "Shree Digvijay Cement Co Ltd")


CEMENT_OUT = ("BURNPUR", "KEIL", "BIGBLOC")
CEMENT_KEEP = ("SCANPRO", "KEERTHI", "PANCM", "SKCIL", "SRICC", "VAICC")


def _to_other(d):
    """The live input as it was before the 17 Nov re-check: Burnpur, Kanoria and BigBloc published in "Other"."""
    oth = next(v for v in d["value_chain"] if v["layer"].startswith("Other"))
    for v in d["value_chain"]:
        if v is oth:
            continue
        mv = [c for c in v["companies"] if c["ticker"] in CEMENT_OUT]
        v["companies"] = [c for c in v["companies"] if c["ticker"] not in CEMENT_OUT]
        oth["companies"] += [{k: x for k, x in c.items() if k not in ("fit", "moved")} for c in mv]
    for s in CEMENT_OUT:
        d["previous"][s] = d["published"][s] = oth["layer"]
        d["moved_before"].pop(s, None)


@pytest.mark.parametrize("before", [False, True])
def test_non_cement_and_non_operating_makers_are_out_of_the_cement_producers_on_the_live_input(before):
    """Fails before: on the live Cement input (published after the 17 Nov re-check) and on it as it was before (the three in "Other"),
    Burnpur ("now completely non-operational"), Kanoria (A.C. pressure pipes and sheets) and BigBloc (AAC blocks) are in "Cement integrated
    producers (smaller)", moved there by their official industry and way of earning. Now each is in "Other" with its words quoted; the
    small cement makers moved in from "Other" before stay (their words name cement as what they make)."""
    _, out = _replay(R69 / "cement.json", _to_other if before else None)
    for s in CEMENT_OUT:
        lay, c = _where(out, s)
        assert lay == "Other cement companies", (s, lay)
        why = (c.get("refit") or {}).get("why") or ""
        assert "own words" in why, (s, why)
    assert "no business now" in _where(out, "BURNPUR")[1]["refit"]["why"]
    assert "Pressure Pipes" in _where(out, "KEIL")[1]["refit"]["why"]
    assert "AAC Blocks" in _where(out, "BIGBLOC")[1]["refit"]["why"]
    for s in CEMENT_KEEP:
        lay, _ = _where(out, s)
        assert lay and "producers" in lay, (s, lay)


# ---------- 003: one date logic in the theme's head ----------
def test_a_stored_theme_read_says_when_it_was_checked_beside_its_maps_date(w):
    """Fails before: the stored read carried only its map's date ("generated_at", 7 Nov), so the head said "Last updated 7 Nov" beside a
    check of 18 Nov; now the read says when it was checked ("checked_at"), the head labels each (frontend mapStamp)."""
    from app.intel import routes as R
    keep("ships", payload("Ships"))
    got = json.loads(R.sector(q="Ships", region="IN", refresh=False, profile=None).body)
    assert got.get("checked_at") and str(got["checked_at"])[:2] == "20", got.get("checked_at")
    assert "older" not in got


# ---------- 004: the public theme page's market values at the latest completed session ----------
def _public_view(monkeypatch, index_day: str):
    from app import public_themes as P
    from app import screens, stock_pages
    dive = {"as_of": "2026-11-13", "layers": [{"layer": "Fabless", "companies": [{"symbol": "NVDA", "cap": 4_300_000.0},
                                                                               {"symbol": "AMD", "cap": 400_000.0}]}]}
    monkeypatch.setattr(P, "_dive", lambda *a, **k: dive)
    monkeypatch.setattr(stock_pages, "companies", lambda region: set())
    monkeypatch.setattr(screens, "load_index", lambda region: {"rows": [
        {"symbol": "NVDA", "market_cap": 4_100_000.0, "price_at": index_day + "T21:00:00+00:00"},
        {"symbol": "AMD", "market_cap": 380_000.0, "price_at": index_day + "T21:00:00+00:00"}]})
    p = {"sector": "Semiconductors", "value_chain": [{"layer": "Fabless", "companies": [
        {"ticker": "NVDA", "name": "NVIDIA", "verified": True}, {"ticker": "AMD", "name": "AMD", "verified": True}]}]}
    entry = {"region": "US", "label": "Semiconductors", "slug": "semiconductors", "name": "semiconductors", "rules": None}
    return P.view(entry, p)


def test_the_public_theme_page_shows_market_values_at_the_latest_close(monkeypatch):
    """Fails before: the US public pages printed the stored dive's values "at the 13 Nov 2026 close" while the app and the heatmap showed the
    17 Nov close (NVIDIA $3.92T here, $3.75T on the heatmap). Now a company the screens' index prices at a later close shows that close's
    value, and the page says that close."""
    v = _public_view(monkeypatch, "2026-11-17")
    caps = {c["symbol"]: c["cap_v"] for x in v["layers"] for c in x["companies"]}
    assert caps == {"NVDA": 4_100_000.0, "AMD": 380_000.0} and v["prices"] == "2026-11-17"
    # (guard) at the dive's own close, the dive's values stand (the app's and the deck's, r66e)
    v = _public_view(monkeypatch, "2026-11-13")
    caps = {c["symbol"]: c["cap_v"] for x in v["layers"] for c in x["companies"]}
    assert caps == {"NVDA": 4_300_000.0, "AMD": 400_000.0} and v["prices"] == "2026-11-13"


# ---------- 010 / LIVE13B-008: one rounding of one figure, the unit note from the cells, one margin source ----------
def test_one_rounding_and_the_unit_note_read_off_the_cells():
    """Fails before: the Semiconductors deck p.8 headline "18.3%" (theme_data.f1, a half up) over its table row "18.2%" (Python's
    half-to-even of the float 18.25), and "in $ million" over cells printed "$110.4 bn"."""
    from app import deck
    from app.intel import theme_data as D
    for v in (18.25, 12.35, -0.05, 7.0, 33.449):
        assert deck._pc(v).replace("−", "-").rstrip("%") == D.f1(v) or deck._pc(v) == "0.0%", v
    assert deck._pc(18.25) == "18.3%"
    assert deck.units_shown(["$387.3 bn", "$110.4 bn", "–"], "$ million") == "$ billion"
    assert deck.units_shown(["$950 m", "$1.20 bn"], "$ million") == "$ million and $ billion"
    assert deck.units_shown(["₹88,512 cr", "₹1.20 lakh cr"], "₹ crore") == "₹ crore and ₹ lakh crore"
    assert deck.units_shown(["–"], "₹ crore") == "₹ crore"


def test_a_years_margin_is_worked_out_as_the_latest_one_is():
    """Fails before: "What moved the aggregate margin" read each year's margin as filed in whole points (UltraTech 17.0% → 19.0%) beside
    19.2% on its layer's page, worked out from the year's operating profit over its revenue."""
    from app.intel import theme_data as D
    assert D.year_margin({"opm": 19, "op": 16990.0, "sales": 88512.0}) == 19.2
    assert D.year_margin({"opm": 19, "op": 15000.0, "sales": 88512.0}) == 19        # not within its rounding: the filed margin
    assert D.year_margin({"opm": 18.7, "op": 16990.0, "sales": 88512.0}) == 18.7     # filed to a decimal: as filed
    assert D.year_margin({"opm": 19}) == 19 and D.year_margin(None) is None


# ---------- 014: a sub-theme whose name joins parts takes the layer that says each ----------
def test_a_sub_theme_of_two_parts_takes_the_layer_that_says_each():
    """Fails before: "Two-wheelers and three-wheelers" showed no company beside "Two-wheeler makers" (Bajaj, TVS, Hero), because "Commercial
    vehicle makers", once named "Commercial and three-wheeler vehicle makers", tied it on two words of three."""
    from app.intel import theme_data as D
    co = lambda t, what: {"ticker": t, "name": t, "what": what}      # noqa: E731
    layers = [{"layer": "Two-wheeler makers", "companies": [co("BAJAJ-AUTO", "makes motorcycles"), co("TVSMOTOR", "makes scooters")]},
              {"layer": "Commercial vehicle makers", "was": "Commercial vehicle makers", "aka": ["Commercial and three-wheeler vehicle makers"],
               "companies": [co("ASHOKLEY", "makes trucks and buses"), co("ATULAUTO", "makes three-wheelers for goods and passengers")]}]
    got = [c["ticker"] for c in D.sub_picked({"name": "Two-wheelers and three-wheelers", "companies": [], "detail": ""}, layers)]
    assert got == ["BAJAJ-AUTO", "TVSMOTOR", "ATULAUTO"], got          # the truck maker's words say no three-wheeler


# ---------- 013 (public): one set of columns on every layer table; a mark only where a company is not description-verified ----------
def test_public_layer_tables_have_one_set_of_columns_and_marks_only_the_exceptions():
    """Fails before: Semiconductors' public layer tables had 4 or 5 columns (the Ticker edge jumping) and "description-verified" on 31 of 39 rows."""
    from app import public_themes as P
    rows = lambda *evs: [{"symbol": f"S{i}", "name": f"Co {i}", "page": None, "cap": "$1B", "cap_v": 1.0, "revenue": None, "year": None,      # noqa: E731
                          "evidence": ev} for i, ev in enumerate(evs)]
    v = {"region": "US", "label": "Semiconductors", "slug": "semiconductors", "name": "semiconductors", "members": 4, "all": 4,
         "evidence": {"description_verified": 3, "industry_code_supported": 1}, "older": False, "rechecking": False, "summary": "",
         "prices": None, "day": None, "indexable": True,
         "layers": [{"name": "Fabless", "companies": rows("description_verified", "description_verified"), "evidence": {"description_verified": 2}},
                    {"name": "Foundry", "companies": rows("description_verified", "industry_code_supported"),
                     "evidence": {"description_verified": 1, "industry_code_supported": 1}}]}
    html = P.render(v)
    assert html.count('<th scope="col" class="l">Membership</th>') == 2              # both tables, one set of columns
    assert ">description-verified</td>" not in html and P.MARK_NOTE.split(":")[0] in html


# ---------- next-engine: a quoted reason never cut on a joining word ----------
def test_a_cut_quote_never_ends_on_a_joining_word():
    """Fails before: the live R67 US Steel and metals deck p.8 printed "…custom smelters”, and “the…”" (R66 caught "and…" only)."""
    from app.intel import theme_changes as C
    t = ("its own words say “carbon material we produce are sold to custom smelters”, and “the carbon products we make are sold to steel "
         "mills worldwide”")
    got = C.clip_words(t, 92)
    assert not got.rstrip("…”").endswith(("the", "“the", "and", ",")) and got.endswith("…") or got.endswith("…”"), got
    assert B.cut_end("sold to custom smelters, and the") == "sold to custom smelters"
    assert B.cut_end("pipes, sheets &") == "pipes, sheets"


# ---------- 009: the finding first ----------
def test_a_ranking_line_leads_with_its_finding():
    """Fails before: the chain's line (printed on the deck, the blog excerpt and the page), the deck's question and its growth line opened
    "Among the 4 layers with at least 5 companies with the figure, ..."."""
    from tests.test_r25_deck import block
    from app.intel import theme_data as D
    c = D.chain_table([block("A", 6, 26.55), block("B", 6, 14.9)])
    assert c["line"].startswith("Median EBITDA margin is highest in A") and ", among the 2 layers with at least" in c["line"], c["line"]
    import inspect
    from app import deck
    src = inspect.getsource(deck)
    assert 'f"Among the {len(chain.get(' not in src and 'f"Among layers of at least' not in src


# ---------- owner, 18 Nov: a US-listed company based abroad is no core member of a US theme ----------
def test_a_us_listed_company_based_abroad_is_shown_beside_the_core_and_counted_in_no_figure():
    """Fails before: HSBC and National Grid, Form 20-F filers, counted in US themes' core figures. Now each is an adjacent row, "listed in the
    US, based abroad", in no median or total; a 10-K filer stays in the core."""
    from app.intel import theme_data as D
    from tests.test_r18_deck import deck_of, us_list_theme
    region, m, f = us_list_theme()
    f["SEC0"] = {**f["SEC0"], "annual_form": "20-F", "annual_filed": "2026-03-01"}
    f["SEC1"] = {**f["SEC1"], "annual_form": "10-K", "annual_filed": "2026-02-01"}
    v, _ = deck_of(region, m, f)
    adj = {a["symbol"]: a for a in v.get("adjacent") or []}
    assert "SEC0" in adj and adj["SEC0"]["kind"] == D.FOREIGN_KIND and "20-F" in adj["SEC0"]["text"], adj
    assert "SEC1" not in adj
    assert v.get("population_rule") == D.POPULATION == 2


# ---------- LIVE13B-009 / next-engine: the deck's own sentences ----------
def test_the_decks_own_sentences_read_as_english():
    """Fails before: "Property developers, property developers: fewer than half ...", "1 company with figures have no description in their
    own words yet", "1 of the 5 also earn from ...", "the 1 adjacent participants"."""
    import inspect
    from app import deck
    got = deck.profile_summary([], [("Property developers", "property developers"), ("Hotels", "hotel operators")])
    assert "Property developers: fewer than half" in got and "Property developers, property developers" not in got
    assert "Hotels, hotel operators: fewer than half" in got
    src = inspect.getsource(deck)
    assert "{'has' if len(names_) == 1 else 'have'}" in src and "the 1 adjacent participant'" in src
    from app.intel import theme_base as TB
    assert "also earn{'s' if n_ == 1 else ''}" in inspect.getsource(TB)


def test_a_layer_whose_companies_are_beyond_the_figures_window_is_not_said_to_have_none():
    """Fails before: the live R67 Fertilizers deck said "No listed company is shown for Distribution and trading, Property developers: no
    member of the theme is placed there" beside a change log moving companies into both (their members were beyond the companies whose
    figures are worked out)."""
    import inspect
    from app import deck
    src = inspect.getsource(deck)
    assert "listed in it, none among the companies whose figures are" in src and "none_ = [x for x in none_ if x not in beyond]" in src


# ---------- 002: one tally of the theme's members, of one read, on every surface ----------
def test_the_deck_and_the_public_page_say_the_dives_one_tally(monkeypatch):
    """Fails before: one theme at one time had three sets of counts (app 101 of 103: 93 · 8 · 2, deck 103 of 103: 94 · 9 · 0, public 101 companies:
    91 · 8 · 2). Now the dive keeps one tally (theme_routes.dive_of) and the deck and the public page say it, the public page naming its read."""
    import inspect
    from app import deck
    from app.intel import theme_routes
    t = {"total": 103, "checked": 101, "description_verified": 93, "industry_code_supported": 8, "list_supported": 0, "not_confirmed": 0,
         "membership_unverified": 2, "beyond": 0}
    v = {"membership_evidence": {"description_verified": 90, "industry_code_supported": 9}, "membership_check": {"outside": {}}, "tally": t}
    assert deck.evidence_tally(v, 103) == t
    assert 'hit["tally"] = theme_data.checked_tally(' in inspect.getsource(theme_routes.dive_of)
    from app import public_themes as P
    monkeypatch.setattr(P, "_dive", lambda *a, **k: {"as_of": "2026-11-13", "tally": t, "tally_at": "2026-11-18",
                                                     "layers": [{"layer": "Fabless", "companies": [{"symbol": "NVDA", "cap": 4.3e6}]}]})
    p = {"sector": "Semiconductors", "value_chain": [{"layer": "Fabless", "companies": [{"ticker": "NVDA", "name": "NVIDIA", "verified": True}]}]}
    got = P.view({"region": "US", "label": "Semiconductors", "slug": "semiconductors", "name": "semiconductors", "rules": None}, p)
    assert got["all"] == 103 and got["evidence"]["description_verified"] == 93 and got["evidence"]["membership_unverified"] == 2
    html = P.render(got)
    assert "Membership of the theme's 103 companies, as checked on" in html


# ---------- next-engine (the live R67 Hotels deck): a move's quote never says the layer it moves the company out of ----------
def test_an_audit_quote_saying_the_present_layers_name_moves_nobody():
    """Fails before: on the live Hotels input (18 Nov), TBO Tek went from "Platforms and marketplaces" to "Travel booking and tour package
    sellers" with the reason "“is in the business of operating multiple online technology platforms”, not what “Platforms and marketplaces”
    names". Now it stays with the platforms."""
    _, out = _replay(R69 / "hotels.json")
    lay, c = _where(out, "TBOTEK")
    assert lay == "Platforms and marketplaces", (lay, c.get("refit"))


# ---------- the REITs theme's FFO: a property owner's piece read before its FFO lines is read once more ----------
def test_a_property_owners_piece_read_before_its_ffo_lines_is_read_once_more(monkeypatch):
    """Fails before: the live REITs dive had FFO and P/FFO for almost none of its property owners: their US pieces were read before FFO's lines
    were part of the read and, kept under the same version, were never read again. Now such a piece (no "reit_v") of a company whose industry
    names real estate is read once more, its older figures standing meanwhile and the company waiting for its figures; once read (kept with
    "reit_v") it stands, and no other company's piece is read again."""
    from app import computed
    from app.intel import sector_metrics as M
    reit = {"symbol": "O", "industry": ["Real Estate Investment Trusts"], "profile": "other"}
    soft = {"symbol": "MSFT", "industry": ["Services-Prepackaged Software"], "profile": "other"}
    old = {"family": "us", "metrics": {"sbc_share": {"v": 1.0}}, "end": "2025-12-31"}
    new = {**old, "metrics": {**old["metrics"], "ffo": {"v": 3500.0, "period": "FY 2025"}, "ffo_share": {"v": 65.0, "period": "FY 2025"}},
           "reit_v": M.REIT_V}
    assert M.stale_for_property(reit, old) and not M.stale_for_property(soft, old) and not M.stale_for_property(reit, new)
    assert not M.current_piece(old) and M.current_piece(new) and M.current_piece({"family": "bank"}) and not M.current_piece(None)
    # a read now keeps the piece with the lines it was read with
    monkeypatch.setitem(M._feeds, "sec", lambda: object())
    monkeypatch.setattr(M, "read_us", lambda sym, client: {"family": "us", "metrics": {}, "end": "2025-12-31"})
    puts = []
    monkeypatch.setattr(computed, "put", lambda kind, k, v, **kw: puts.append(v))
    assert M.read("US", "O", "us")["reit_v"] == M.REIT_V and puts[-1]["reit_v"] == M.REIT_V
    # the reader reads it again within the budget; past it, the worker is asked (again=True)
    monkeypatch.setattr(M, "read", lambda region, sym, fam: new)
    get = M.reader("US")
    assert get.again("O", "us") is new
    queued = []
    monkeypatch.setattr(M, "read", lambda region, sym, fam: None)
    monkeypatch.setattr(M, "queue", lambda region, sym, fam, again=False: queued.append((sym, again)))
    get = M.reader("US", budget=0.0)
    assert get.again("O", "us") is None and queued == [("O", True)]
    # a dive waiting on it is worked out again only once its piece is the new one
    monkeypatch.setattr(computed, "index", lambda kind: {"entries": {computed.hkey(M.key("US", "O")): {}}})
    monkeypatch.setattr(M, "stored", lambda region, sym: old)
    assert M.any_stored("US", ["O"]) is False
    monkeypatch.setattr(M, "stored", lambda region, sym: new)
    assert M.any_stored("US", ["O"]) is True


def test_the_dive_takes_a_property_owners_re_read_ffo(monkeypatch):
    """theme_data.build: the stale piece is read again through the reader's `again`, and its FFO reaches the company's row."""
    from app.intel import sector_metrics as M
    from app.intel import theme_data as D
    old = {"family": "us", "metrics": {}, "end": "2025-12-31"}
    new = {"family": "us", "metrics": {"ffo": {"v": 3500.0, "period": "FY 2025"}, "ffo_share": {"v": 65.0, "period": "FY 2025"}},
           "end": "2025-12-31", "reit_v": M.REIT_V}

    def metrics(sym, fam):
        return old
    metrics.again = lambda sym, fam: new
    row = {"symbol": "O", "industry": ["Real Estate Investment Trusts"], "profile": "other", "cap": 50000.0}
    assert M.stale_for_property(row, metrics("O", "us"))
    import inspect
    assert "again = getattr(src.metrics, \"again\", None)" in inspect.getsource(D.build)
    piece = metrics.again("O", "us")
    M.apply(row, piece)
    assert row["ffo_share"] == 65.0 and row["p_ffo"] == round(50000.0 / 3500.0, 1)


def test_the_worker_reads_a_property_owners_piece_again_once_in_the_memory_guards_turn(monkeypatch):
    from app import memguard
    from app.intel import sector_metrics as M
    old = {"family": "us", "metrics": {}}
    store = {"O": old, "MSFT": old}
    reads, turns = [], []
    monkeypatch.setattr(M, "stored", lambda region, sym: store.get(sym))

    def read(region, sym, fam):
        reads.append(sym)
        store[sym] = {**old, "reit_v": M.REIT_V}
    monkeypatch.setattr(M, "read", read)
    real = memguard.heavy

    def heavy(name, force_release=False):
        turns.append(name)
        return real(name, force_release)
    monkeypatch.setattr(memguard, "heavy", heavy)
    M._q[:] = [("US", "O", "us", True), ("US", "O", "us", True), ("US", "MSFT", "us")]
    M._worker["on"] = True
    M._work()
    assert reads == ["O"] and turns == ["sector metrics: property lines"]       # once; a plain item with a piece stored is not read
