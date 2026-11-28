"""deck101 (owner, 27 Nov: "I need it to be perfect"): every live R99 theme deck read again as a sell-side reader would, each problem found
fixed as a rule for every theme."""
import copy
import functools
from statistics import median

from app import deck
from app.intel import theme_data as D
from tests.alcobev_fixture import alco_view

LARGER, SMALLER = "Spirits brand owning and bottling (larger)", "Spirits brand owning and bottling (smaller)"
BASE = "Spirits brand owning and bottling"
GRAIN = "Grain distilling and extra neutral alcohol"


@functools.lru_cache(maxsize=None)
def _alco():
    return alco_view()


def _view():
    return copy.deepcopy(_alco())


def _halves(v):
    """The fixture's two spirits layers as the dive splits one layer into halves by market value (scale, sibling)."""
    by = {b["layer"]: b for b in v["layers"]}
    by[LARGER].update(scale="larger", sibling=SMALLER)
    by[SMALLER].update(scale="smaller", sibling=LARGER)
    for r in v["chain"]["rows"]:
        if r["layer"] in (LARGER, SMALLER):
            r["scale"] = "larger" if r["layer"] == LARGER else "smaller"
    return v


def _both_median(v):
    cos = [c for b in v["layers"] if b["layer"] in (LARGER, SMALLER) for c in b["companies"]
           if D.in_calc(c) and not c.get("company_wide") and c.get("ebitda") is not None]
    return round(median(c["ebitda"] for c in cos), 1)


def _rows(slide):
    return [[deck._cell_text(x) for x in r] for b in slide.blocks if b["kind"] == "table" for r in b.get("rows") or [] if not isinstance(r, dict)]


def _page(slides, title):
    return next(s for s in slides if s.title.startswith(title))


MAKING = {"id": "manufacturing", "family": "making", "line": "They earn mainly from making and selling finished products of their own.",
          "known": 5, "of": 5, "out": 0, "also": []}


def _ranked(v, hi_value):
    # each ranked layer's way of earning read, as the live dive's (a ranking of layers whose ways of earning were never read is dropped)
    for x in v["layers"] + v["chain"]["rows"]:
        if x["layer"] in (GRAIN, LARGER, SMALLER):
            x["model"] = dict(MAKING)
    grain = next(r for r in v["chain"]["rows"] if r["layer"] == GRAIN)["ebitda"]
    v["chain"].update(highest=BASE, lowest=GRAIN, measure="ebitda", compared=[GRAIN, BASE],
                      line=f"Median EBITDA margin is highest in {BASE} ({D.HALVES_SAID}{hi_value:.1f}%) and lowest in {GRAIN} ({grain:.1f}%), a gap of "
                           f"{hi_value - grain:.1f} points, among the 2 layers with at least 5 companies with the figure; the \"Other\" group, outside "
                           "the map's layers, is not ranked.")
    return v


def test_a_layer_split_into_halves_has_a_row_of_both_halves_so_a_ranking_of_the_whole_layer_stays():
    # the live R99 Alcoholic beverages deck: "highest in Spirits brand owning and bottling (its larger and smaller halves together, 11.8%)"
    # dropped from the value chain's page and the findings (11.8% on no row of any table), the page left with no headline; Airlines' "Hotels
    # and resorts 27.9%" likewise
    v = _halves(_view())
    both = _both_median(v)
    assert both not in {r.get("ebitda") for r in v["chain"]["rows"]}
    slides, _ = deck.theme_plan(_ranked(v, both))
    chain = _page(slides, "The value chain by layer")
    assert chain.subtitle.startswith(f"Median EBITDA margin is highest in {BASE} ({D.HALVES_SAID}{both:.1f}%)"), chain.subtitle
    rows = _rows(chain)
    names = [r[0] for r in rows]
    assert f"{BASE} (both halves)" in names, names
    i = names.index(f"{BASE} (both halves)")
    assert names[i - 1] == SMALLER and names[i - 2] == LARGER          # right after its halves
    assert f"{both:.1f}%" in rows[i], rows[i]
    assert any(BASE in x and f"{both:.1f}%" in x for x in deck.findings_lines(slides))
    # a theme with no layer split into halves has no such row
    slides, _ = deck.theme_plan(_view())
    assert not any("both halves together" in r[0] for r in _rows(_page(slides, "The value chain by layer")))


def test_the_contents_never_keep_the_tail_of_a_headline_whose_lead_part_was_dropped():
    # the live R99 Alcoholic beverages deck's contents: 'The value chain | the "Other" group, outside the map's layers, is not ranked.'
    v = _ranked(_halves(_view()), 77.7)           # a figure no table shows: the check drops the headline's lead part
    slides, _ = deck.theme_plan(v)
    assert _page(slides, "The value chain by layer").subtitle == ""
    held = {r[0]: r[1] for r in _rows(_page(slides, "Contents"))}
    assert held["The value chain"] == deck.CONTENTS_PLAIN["The value chain"], held
    assert not any(x[:1].islower() for x in held.values()), held
    rows = [["The value chain", 'Lead part; the "Other" group is not ranked.', "4"], ["Findings", "One; two", "3"]]
    assert deck.contents_after(rows, {"Lead part"}) == [["The value chain", deck.CONTENTS_PLAIN["The value chain"], "4"], ["Findings", "One; two", "3"]]
    assert deck.contents_after(rows, {"two"})[1] == ["Findings", "One", "3"]


def test_the_most_revenue_finding_takes_a_layer_split_into_halves_as_one_and_reads_whatever_its_name():
    # the live R99 decks: "Spirits brand owning and bottling (larger) brings in the most revenue" (the larger half, by construction), "Stock
    # broking (larger) brings in", "Steel mills brings in"
    v = _halves(_view())
    by = {b["layer"]: b for b in v["layers"]}
    total = by[LARGER]["revenue"] + by[SMALLER]["revenue"]
    slides, _ = deck.theme_plan(v)
    lines = deck.findings_lines(slides)
    assert any(f"most revenue of the map's own layers is in {BASE} (both halves): " in x for x in lines), lines
    assert not any("(larger) brings in" in x or "brings in the most revenue" in x for x in lines), lines
    got = {t[0]: t[1] for t in deck.revenue_layers([by[LARGER], by[SMALLER], by[GRAIN]])}
    assert got == {f"{BASE} (both halves)": total, GRAIN: by[GRAIN]["revenue"]}


def _layer(name, *cos, wide=()):
    return {"layer": name, "revenue": sum(r for _, r in cos), "company_wide": list(wide),
            "companies": [{"symbol": s, "name": s, "revenue": r, "status": "description_verified"} for s, r in cos]}


def test_the_most_revenue_finding_never_rests_on_a_conglomerates_other_businesses():
    # the live R99 Airlines deck: "Airport operators and conglomerates brings in the most revenue of the map's own layers, ₹1.15 lakh cr",
    # ₹1.00 lakh cr of it Adani Enterprises' whole-company figures; Aerospace's engines layer (GE Aerospace, Honeywell), P&C insurance's
    # "Diversified groups" (Berkshire Hathaway alone)
    money = lambda x: deck.money(x, "₹ crore")          # noqa: E731
    airports = _layer("Airport operators and conglomerates", ("ADANIENT", 100469), ("GMRAIRPORT", 14807), wide=("ADANIENT",))
    airlines = _layer("Airlines and air charter operators", ("INDIGO", 84962), ("TAAL", 197), ("GVH", 521))
    got = deck.most_revenue_line([airports, airlines], money)
    assert got == "Ranked without whole-company figures, the most revenue of the map's own layers is in Airlines and air charter operators: ₹85,680 cr.", got
    # a layer that leads on its own revenue too says its whole-company figures beside its total
    cars = _layer("Passenger vehicle makers", ("MARUTI", 152000), ("M&M", 160000), wide=("M&M",))
    got = deck.most_revenue_line([cars, airlines], money)
    assert got.startswith("Ranked without whole-company figures, the most revenue of the map's own layers is in Passenger vehicle makers: ")
    assert got.endswith(" with the whole-company figures of 1 company that runs other businesses too."), got
    # no whole-company figure anywhere: plainly
    assert deck.most_revenue_line([airlines, _layer("Tour operators", ("THOMASCOOK", 8398))], money) == \
        "The most revenue of the map's own layers is in Airlines and air charter operators: ₹85,680 cr."


def test_one_company_is_said_as_one():
    # the live R99 Airlines, Alcoholic beverages and Capital markets decks: "1 of the 1 added are description-verified"
    assert deck.added_said(1, 1) == "The 1 added is description-verified."
    assert deck.added_said(0, 1) == "The 1 added is not description-verified yet."
    assert deck.added_said(3, 5) == "3 of the 5 added are description-verified; 2 not yet."
    assert deck.added_said(4, 4) == "4 of the 4 added are description-verified."


def test_a_cell_cut_to_whole_clauses_never_ends_on_a_word_that_needs_what_follows_it():
    # the live R99 Alcoholic beverages deck: "Som Distilleries & Breweries Ltd. is one of the leading alcoholic beverages manufacturers in India
    # engaged", with no ellipsis
    t = ("Som Distilleries & Breweries Ltd. is one of the leading alcoholic beverages manufacturers in India engaged in the manufacturing and sale "
         "of Beer and Indian Made Foreign Liquor (IMFL)")
    got = deck.whole_clause(t, 110)
    assert got == "Som Distilleries & Breweries Ltd. is one of the leading alcoholic beverages manufacturers in India", got
    for t in ("Acme Ltd makes forged parts for engines and turbines used in the power, rail and defence sectors across many countries in the region",
              "Beta Industries is a speciality chemicals maker primarily based in Gujarat that supplies dyes, pigments and intermediates to many buyers"):
        got = deck.whole_clause(t, 80)
        assert not deck._DANGLING.search(got) and not got.endswith("…"), got
    assert deck.whole_clause("Gamma Ltd brews beer.", 110) == "Gamma Ltd brews beer."


def test_a_percentage_of_a_thousand_or_more_sets_its_thousands_apart():
    # the live R99 Airlines and Consumer durables decks: "+4520.4%", "−7026.0%"
    assert deck._chg(4520.44) == "+4,520.4%"
    assert deck._pc(-7026.0) == "−7,026.0%"
    assert deck._pc(999.96) == "1,000.0%" and deck._pc(999.4) == "999.4%" and deck._chg(12.3) == "+12.3%"
    assert deck._pcw(1234.0, True) == "1,234%"
    assert D.shown_numbers(["+4,520.4%"])["pct"] == {4520.4}


def test_layers_whose_names_state_different_operating_models_are_said_plainly():
    # the live R99 Capital goods deck: "Their operating models differ (Cables, transformers and electrical equipment makers: equipment making
    # (stated by the layer's own name); Industrial machinery and engines makers: not stated by its name; …)"
    from app.intel.theme_data import OPERATING_WORDS
    ops = list(OPERATING_WORDS)[:2]
    rows = [{"layer": "Cable makers", "model": {"operating": ops[0]}}, {"layer": "Machinery makers", "model": {}},
            {"layer": "Project contractors", "model": {"operating": ops[1]}}, {"layer": "Rolling stock makers", "model": None}]
    got = D.operating_differ(rows)
    assert got == (f"Their operating models differ by the layers' names: {OPERATING_WORDS[ops[0]]} (Cable makers); {OPERATING_WORDS[ops[1]]} "
                   "(Project contractors); the names of Machinery makers and Rolling stock makers state none"), got
    assert "stated by" not in got and "its name" not in got
    assert D.operating_differ(rows[:3]).endswith("; the name of Machinery makers states none")


def test_a_layer_name_ending_in_s_takes_the_apostrophe_alone():
    # the live R99 Defence deck: "Explosives and missile makers's companies together earn 22.7% of their revenue as EBITDA"
    assert D.possessive("Explosives and missile makers") == "Explosives and missile makers'"
    assert D.possessive("Siemens") == "Siemens'" and D.possessive("Two-wheeler maker") == "Two-wheeler maker's"


def test_a_price_period_the_theme_has_no_figure_for_is_no_row():
    # every live R99 deck's Price page: "3 years  –  –  +35.7%  –", the index's figure beside no figure of the theme's
    v = _view()
    assert v["prices"]["returns"]["3Y"]["theme"] is None and v["prices"]["returns"]["3Y"]["bench"] is not None
    slides, _ = deck.theme_plan(v)
    rows = _rows(_page(slides, "Price"))
    periods = [r[0] for r in rows]
    assert "1 year" in periods and "3 years" not in periods, periods


def test_a_sentence_that_turns_from_or_adds_to_one_before_it_is_no_line_of_a_companys_own_words():
    # the live R99 decks: TAAL Tech description-verified in Airlines on "However, after an aircraft accident, company is not operating
    # aircrafts"; Orange on "Furthermore, in the retail markets, …"; Finolex Cables on "Besides manufacturing a wide variety of wires and cables"
    from app.intel.theme_base import own_words
    for t in ("However, after an aircraft accident, company is not operating aircrafts",
              "Furthermore, in the retail markets, the number of new mobile customers for telecommunications services is generally high",
              "Besides manufacturing a wide variety of wires and cables", "Moreover the company sells cement in bags"):
        assert own_words(t) == "", t
    for t in ("Sun TV Network Limited operates television channels in India", "Thus Ltd makes forgings for engines"):
        assert own_words(t) == t, t


def test_a_fund_is_said_to_track_the_theme_only_when_its_name_says_the_themes_work():
    # the live R99 decks: Alcoholic beverages' "Funds that track the theme: NIFTYBEES, CONSUMBEES, MAFANG" (the Nifty 50, a consumption fund, a
    # NYSE FANG+ fund), Airlines' CPSE ETF and Nifty Midcap 100, Insurance's and Utilities' BANKBEES, Medical devices' IBB and PPH
    fund = lambda t, n: {"ticker": t, "name": n}          # noqa: E731
    alco = [fund("NIFTYBEES", "NIPPON INDIA ETF NIFTY 50 BEES"), fund("CONSUMBEES", "NIPPON NIFTY INDIA CONSUMPTION ETF"),
            fund("MAFANG", "MIRAE ASSET NYSE FANG ETF")]
    assert deck.theme_funds(alco, "Alcoholic beverages") == []
    keep = lambda etfs, sector: [e["ticker"] for e in deck.theme_funds(etfs, sector)]          # noqa: E731
    assert keep([fund("AUTOBEES", "NIPPON INDIA NIFTY AUTO ETF"), fund("CPSEETF", "CPSE ETF")], "Automotive") == ["AUTOBEES"]
    assert keep([fund("FMCGIETF", "ICICI PRUDENTIAL NIFTY FMCG ETF"), fund("CONSUMBEES", "NIPPON NIFTY INDIA CONSUMPTION ETF"),
                 fund("NIFTYBEES", "NIPPON INDIA ETF NIFTY 50 BEES")], "FMCG (Fast Moving Consumer Goods)") == ["FMCGIETF", "CONSUMBEES"]
    assert keep([fund("BANKBEES", "NIPPON INDIA NIFTY BANK BEES ETF"), fund("FINIETF", "ICICI PRUDENTIAL NIFTY FINANCIAL SERVICES EX-BANK ETF")],
                "Insurance") == ["FINIETF"]
    assert keep([fund("BANKBEES", "NIPPON INDIA NIFTY BANK BEES ETF"), fund("BFSI", "MIRAE ASSET NIFTY FINANCIAL SERVICES ETF")],
                "Non-bank lenders (NBFCs and housing finance companies)") == ["BFSI"]
    assert keep([fund("ITBEES", "NIPPON INDIA ETF NIFTY IT")], "IT services") == ["ITBEES"]
    assert keep([fund("IHI", "iShares U.S. Medical Devices ETF"), fund("IBB", "ISHARES BIOTECHNOLOGY ETF"), fund("PPH", "VanEck Pharmaceutical ETF")],
                "Medical devices") == ["IHI"]
    assert keep([fund("URA", "Global X Uranium ETF"), fund("NLR", "VANECK URANI & NUCLR ETF-USD")], "Nuclear and SMRs") == ["URA", "NLR"]
    assert keep([fund("IYT", "iShares U.S. Transportation ETF"), fund("JETS", "US GLOBAL JETS ETF")], "Railroads and trucking") == ["IYT"]
    assert keep([fund("SCHH", "SCHWAB US REIT ETF")], "Real estate investment trusts") == ["SCHH"]
    assert keep([fund("MOCAPITAL", "MOTILAL OSWAL NIFTY CAPITAL MARKET ETF")], "Capital goods (India)") == []
    # the method page says only the funds kept, and no line at all when none is
    v = _view()
    v["etfs"] = alco
    slides, _ = deck.theme_plan(v)
    assert "Funds that track the theme" not in " ".join(" ".join(r) for r in _rows(_page(slides, deck.METHOD_TITLE)))


def test_a_companys_name_is_never_cut_to_keep_the_industry_column():
    # the live R99 Fertilizers deck: "Chambal Fertilizers…", "Rashtriya Chemicals…", "Fertilizers & Chemicals…" beside the market-value chart,
    # to keep an industry column that says "Fertilizers" on most rows
    v = _view()
    lay = next(b for b in v["layers"] if b["layer"] == GRAIN)
    long_ = ["Gujarat Narmada Valley Fertilizers and Chemicals Limited", "Rashtriya Chemicals and Fertilizers Limited",
             "Chambal Fertilizers and Chemicals Limited", "Fertilizers and Chemicals Travancore Limited", "Southern Petrochemical Industries Corporation",
             "Madhya Bharat Agro Products Limited"]
    for c, nm, ind in zip(lay["companies"], long_, ["Fertilizers", "Commodity Chemicals", "Fertilizers", "Fertilizers", "Fertilizers", "Fertilizers"]):
        c["name"], c["official_industry"] = nm, ind
    slides, _ = deck.theme_plan(v)
    page = next(s for s in slides if s.title.endswith(GRAIN))
    table = next(b for b in page.blocks if b["kind"] == "table")
    shown = [deck._cell_text(r[0]) for r in deck.table_layout(table, table["box"][2], 99)["rows"] if not isinstance(r, dict)]
    names = [n for n in shown if not n.startswith(("Median", "Range", "Together"))]
    assert len(names) == 6 and not any(n.endswith("…") for n in names), names          # as the page prints them
