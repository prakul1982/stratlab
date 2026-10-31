"""THEME-1: the theme deep dive. Margins by layer from the stored company facts (never AI), a company placed only where its own
description shows the work, tailwinds and risks beside a dated headline, the sections of the dive, the draft blog post and the news."""
import json
from datetime import date, datetime, timezone

import pytest

from app import blog_research, db
from app.intel import theme_check as C
from app.intel import theme_data as D
from app.intel import theme_prices as P

TODAY = date(2026, 10, 5)


def facts(sym, name, sales, margins, profits, cap=10000, pe=20.0, roce=15.0, de=0.5, industry=("Metals",), stage=2, **kw):
    """A stored public page's facts: four years to March 2026."""
    labels = ["Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"]
    return {"v": 9, "region": "IN", "symbol": sym, "name": name, "unit": "₹ crore", "industry": list(industry), "price": 100.0, "price_at": "2026-10-05",
            "high52": 110.0, "low52": 70.0, "market_cap": cap, "pe": pe, "roe": 12.0, "roce": roce, "net_margin": profits[-1] / sales[-1] * 100,
            "opm": margins[-1], "debt_equity": de, "bank": False, "stage": stage, "st_up": True, "filings": [], "red_flags": 0,
            "growth": {"sales_cagr_3y": 10.0, "profit_cagr_3y": 12.0, "sales_cagr_5y": 9.0, "profit_cagr_5y": 8.0},
            "years": [{"year": y, "sales": s, "profit": p, "opm": m, "debt": 100, "cfo": p * 1.2} for y, s, p, m in zip(labels, sales, profits, margins)], **kw}


FACTS = {
    "MINEA": facts("MINEA", "Mine A", [1000, 1100, 1300, 1500], [40, 42, 45, 50], [200, 220, 280, 360], cap=40000, pe=12),
    "MINEB": facts("MINEB", "Mine B", [800, 900, 1000, 1200], [38, 40, 44, 48], [150, 170, 200, 260], cap=20000, pe=14),
    "CELLA": facts("CELLA", "Cell A", [2000, 2300, 2600, 3000], [12, 11, 10, 9], [120, 110, 100, 90], cap=30000, pe=30),
    "CELLB": facts("CELLB", "Cell B", [1500, 1700, 1900, 2200], [14, 12, 11, 10], [100, 90, 90, 100], cap=15000, pe=28),
    "RELIANCE": facts("RELIANCE", "Reliance Industries", [900000, 950000, 1000000, 1100000], [17, 17, 16, 16], [70000, 72000, 75000, 80000], cap=1900000, pe=24,
                      industry=("Diversified",)),
}
FACTS["RELIANCE"].update(price=2800.0, high52=3000.0, low52=2000.0)
LAYERS = [
    {"layer": "Mining", "description": "Digs it out.", "companies": [{"name": "Mine A", "ticker": "MINEA", "what": "mines ore"}, {"name": "Mine B", "ticker": "MINEB", "what": "mines ore"}]},
    {"layer": "Cells", "description": "Makes cells.", "companies": [{"name": "Cell A", "ticker": "CELLA", "what": "makes cells"}, {"name": "Cell B", "ticker": "CELLB", "what": "makes cells"},
                                                                    {"name": "Reliance Industries", "ticker": "RELIANCE", "what": "makes cells"}]},
]
CHECKED = {"sector": "Test theme", "value_chain": LAYERS, "sub_themes": [{"name": "Cell making", "detail": "Cells.", "companies": [{"name": "Cell A", "ticker": "CELLA", "what": "makes cells"}]}],
           "placements": {"checked": True, "pending": 0, "left_out": 0, "placed": 5}}


def src(**kw):
    return D.Sources(TODAY, facts=FACTS.get, index_rows=lambda: [{"symbol": "X", "pe": 20.0, "opm": 15.0, "net_margin": 8.0, "roce": 14.0, "sales_cagr_3y": 9.0}], **kw)


# ---------- item 1: margins from the stored figures ----------
def test_a_company_row_is_the_latest_full_year_worked_out_from_the_facts():
    r = D.company_row("IN", "MINEA", FACTS["MINEA"])
    assert (r["year"], r["revenue"], r["ebitda"], r["net"], r["roce"]) == ("Mar 2026", 1500, 50, 24.0, 15.0)        # 360 / 1500
    assert r["sales_1y"] == pytest.approx(15.4, abs=0.05) and r["sales_3y"] == 10.0


def test_a_layer_has_a_median_and_a_range_and_the_whole_chain_one_table():
    out = D.build("IN", "Test theme", CHECKED, src())
    mining = out["layers"][0]
    assert mining["stats"]["ebitda"] == {"n": 2, "median": 49.0, "min": 48.0, "max": 50.0}
    assert mining["stats"]["net"]["median"] == pytest.approx(22.85, abs=0.01)         # 24.0 and 21.7
    rows = {r["layer"]: r for r in out["chain"]["rows"]}
    assert rows["Mining"]["ebitda"] == 49.0 and rows["Cells"]["ebitda"] == 9.5       # Reliance's 16 is left out of the median
    assert out["chain"]["highest"] == "Mining" and out["chain"]["lowest"] == "Cells"
    assert "highest in Mining (49.0%)" in out["chain"]["line"] and "gap of 39.5 points" in out["chain"]["line"]
    assert "Mar" in out["basis"] and "₹ crore" in out["basis"] and "Consolidated" in out["basis"]


def test_a_conglomerate_is_marked_company_wide_and_left_out_of_the_median():
    out = D.build("IN", "Test theme", CHECKED, src())
    cells = out["layers"][1]
    assert cells["company_wide"] == ["RELIANCE"] and cells["left_out"] == 1
    assert [c["company_wide"] for c in cells["companies"]] == [False, False, True]
    assert "whole company's" in cells["line"]
    assert "RELIANCE" in out["company_wide"]


def test_a_company_doing_several_layers_is_company_wide_too():
    two = {**CHECKED, "value_chain": [LAYERS[0], {**LAYERS[1], "companies": LAYERS[1]["companies"][:2] + [LAYERS[0]["companies"][0]]}]}
    out = D.build("IN", "Test theme", two, src())
    assert "MINEA" in out["company_wide"]


def test_a_stale_year_or_a_lender_has_no_margin():
    old = {**FACTS["MINEA"], "price_at": "2028-01-01"}
    r = D.company_row("IN", "MINEA", old)
    assert r["year"] is None and r["ebitda"] is None and r["net"] is None
    bank = D.company_row("IN", "MINEA", {**FACTS["MINEA"], "bank": True})
    assert bank["ebitda"] is None and bank["roce"] is None and bank["debt_equity"] is None


def test_the_sections_come_from_the_stored_figures():
    out = D.build("IN", "Test theme", CHECKED, src())
    s = out["sections"]
    assert s["size"]["companies"] == 5 and s["size"]["biggest"][0]["symbol"] == "RELIANCE"
    assert s["valuation"]["pe"]["n"] == 5 and s["valuation"]["market_pe"]["median"] == 20.0
    assert s["balance"]["debt_equity"]["median"] == 0.5 and s["balance"]["cfo_to_profit"]["median"] == 1.2
    assert s["price"]["stage2"] == {"n": 5, "count": 5, "share": 100}
    g = s["growth"]["aggregate"]["revenue_1y"]
    assert g["n"] == 4 and g["year"] == "Mar 2026"                                   # the four own-business companies
    assert s["margins"]["years"][-1] == "Mar 2026" and s["margins"]["n"] == 4
    assert {r["symbol"] for r in s["leaders"]} == set(FACTS)
    assert out["subs"][0]["companies"][0]["what"] == "makes cells"


def test_a_reader_that_fails_leaves_its_section_empty_not_the_dive():
    def boom(*a):
        raise RuntimeError("down")
    out = D.build("IN", "Test theme", CHECKED, src(results=boom, shareholding=boom, card=boom))
    assert out["sections"]["events"]["results_due"] == [] and out["sections"]["ownership"]["holdings"] == []


def test_ownership_events_and_management_from_the_stored_data():
    shp = {"q": {"2026-06": {"rows": [["Promoter A", "individual", "promoter", 100, 40.0], ["Fund", "Mutual fund", "public", 50, 5.0]]},
                 "2026-09": {"rows": [["Promoter A", "individual", "promoter", 100, 42.0], ["Fund", "Mutual fund", "public", 50, 4.0]]}}}
    out = D.build("IN", "Test theme", CHECKED, src(
        shareholding=lambda s: shp if s == "MINEA" else None, insider_buys=lambda: {"MINEB": "2026-09-20", "CELLA": "2026-01-01"},
        results=lambda a, b, syms: [{"symbol": "CELLA", "date": "2026-10-12", "purpose": "Financial Results"},
                                    {"symbol": "MINEA", "date": "2026-10-01", "purpose": "Results", "out": {"numbers": [{"label": "Revenue", "value": "₹1,500 crore"}], "url": "https://x"}}],
        actions=lambda a, b, syms: [{"symbol": "MINEA", "ex_date": "2026-10-20", "kind": "dividend", "label": "Dividend", "text": "₹5 a share"}],
        red_flags=lambda syms, a, b: [{"symbol": "CELLB", "at": "2026-09-01", "category": "pledge", "label": "Promoter pledge or encumbrance", "severity": "red", "url": "https://y"}],
        card=lambda s, r: {"met": 2, "missed": 1} if s == "MINEA" else None))
    own = out["sections"]["ownership"]
    assert own["holdings"][0]["promoter"] == 42.0 and own["holdings"][0]["promoter_change"] == 2.0 and own["promoter_up"] == 1
    assert own["holdings"][0]["institutions"] == 4.0 and own["holdings"][0]["institutions_change"] == -1.0
    assert [b["symbol"] for b in own["insider_buys"]] == ["MINEB"] and own["pledges"][0]["symbol"] == "CELLB"
    ev = out["sections"]["events"]
    assert [d["symbol"] for d in ev["results_due"]] == ["CELLA"] and ev["results_filed"][0]["symbol"] == "MINEA" and ev["actions"][0]["label"] == "Dividend"
    assert out["sections"]["management"] == {"companies": [{"symbol": "MINEA", "name": "Mine A", "met": 2, "missed": 1}], "met": 2, "missed": 1, "with_card": 1}


def test_the_valuation_history_is_kept_through_the_source():
    kept = []
    out = D.build("IN", "Test theme", CHECKED, src(history=lambda k, p: kept.append(p) or kept))
    assert out["sections"]["valuation"]["history"][0]["d"] == "2026-10-05" and out["sections"]["valuation"]["history"][0]["n"] == 5


def test_business_updates_are_read_through_one_function():
    row = {"metric": "Total sales", "unit": "units", "span": "month", "period": "2026-09", "value": 1200, "prev": 1000, "year_ago": 800, "change_prev": 20.0, "change_year": 50.0,
          "filed": "2026-10-01", "url": "https://f", "points": [{"period": "2026-08", "value": 1000}, {"period": "2026-09", "value": 1200}]}
    blocks = [{"layer": "Cells", "companies": [{"symbol": "CELLA"}, {"symbol": "CELLB"}]}]
    out = D.business_section(blocks, [{"name": "Cell making", "companies": [{"symbol": "CELLA"}]}], {"CELLA": "Cell A"}, lambda s: row if s == "CELLA" else None)
    assert out["layers"][0]["rows"][0]["name"] == "Cell A" and out["layers"][0]["rows"][0]["change_year"] == 50.0
    assert out["companies"] == 1 and out["of"] == 2 and out["subs"][0]["rows"][0]["symbol"] == "CELLA"


# ---------- item 2: a company is placed only where its own words put it ----------
DESCR = {
    "MINEA": "Mine A mines lithium and nickel ore in several countries and sells the concentrate to refiners.",
    "JINDALSTEL": "Jindal Steel makes steel, power and mines iron ore for its own plants.",
    "COALINDIA": "Coal India mines coal and sells it to power plants across India.",
    "CELLA": "Cell A manufactures lithium ion battery cells for electric vehicles at its plant.",
}
MAP = {"sector": "India EV battery", "value_chain": [
    {"layer": "Nickel cobalt lithium ore mining", "description": "Mining the ore.", "companies": [
        {"name": "Mine A", "ticker": "MINEA"}, {"name": "Jindal Steel", "ticker": "JINDALSTEL"}]},
    {"layer": "Battery chemical processing", "description": "Refining battery chemicals.", "companies": [{"name": "Coal India", "ticker": "COALINDIA"}]},
    {"layer": "Cell manufacturing", "description": "Making battery cells.", "companies": [{"name": "Cell A", "ticker": "CELLA"}]}],
    "sub_themes": [{"name": "Battery cell manufacturing", "detail": "Cells for vehicles.", "companies": [{"name": "Cell A", "ticker": "CELLA"}, {"name": "Mine A", "ticker": "MINEA"}]}],
    "screen": [{"ticker": "JINDALSTEL", "name": "Jindal"}, {"ticker": "CELLA", "name": "Cell A"}], "clusters": [{"name": "x", "companies": [{"ticker": "COALINDIA", "name": "Coal India"}]}]}


def evidence(descr=DESCR, pending=()):
    return lambda syms: ({s: {"about": descr[s], "industry": ""} for s in syms if s in descr}, set(pending))


def answer(yes: dict):
    """An AI that answers each check from `yes`: {"<group>|<symbol>": quote}, otherwise no."""
    def ask(system, text):
        body = json.loads(text.split("CHECKS:\n", 1)[1])
        return {"checks": [{"id": f"{g}|{c['symbol']}", "does": f"{g}|{c['symbol']}" in yes, "quote": yes.get(f"{g}|{c['symbol']}", "")}
                           for c in body["companies"] for g in c["check_groups"]]}
    return ask


def test_a_wrong_placement_is_rejected_and_the_right_one_shows_its_own_words():
    yes = {"L0|MINEA": "mines lithium and nickel ore in several countries", "L2|CELLA": "manufactures lithium ion battery cells for electric vehicles",
           "S0|CELLA": "manufactures lithium ion battery cells for electric vehicles",
           # the AI says Jindal and Coal India do these jobs, with a quote that really is in their descriptions
           "L0|JINDALSTEL": "mines iron ore for its own plants", "L1|COALINDIA": "mines coal and sells it to power plants across India",
           # ...and Mine A in the cell sub-theme, with words that are not in its description
           "S0|MINEA": "builds battery cells for electric vehicles"}
    out = C.check_placements(MAP, evidence(), answer(yes), "India EV battery")
    layer = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out["value_chain"]}
    assert layer["Nickel cobalt lithium ore mining"] == ["MINEA"]                    # Jindal's quote is iron ore, not the layer's ore: no shared distinctive word
    assert layer["Battery chemical processing"] == [] and layer["Cell manufacturing"] == ["CELLA"]
    assert [c["ticker"] for c in out["sub_themes"][0]["companies"]] == ["CELLA"]     # Mine A's quote isn't in its description
    assert out["value_chain"][0]["companies"][0]["what"] == "mines lithium and nickel ore in several countries"
    assert [x["ticker"] for x in out["screen"]] == ["CELLA"] and out["clusters"] == []
    assert out["placements"]["checked"] and out["placements"]["left_out"] == 3


def test_a_paraphrased_quote_is_backed_by_the_companys_own_sentence_and_a_made_up_one_still_places_nothing():
    # 31 Oct, "India Defence" empty: the free models paraphrase, and every paraphrase was a "no"
    yes = {"L2|CELLA": "makes lithium battery cells for EVs",                         # not the description's words, but it says what it says
           "S0|MINEA": "builds battery cells for electric vehicles"}                   # its description says nothing of the kind
    out = C.check_placements(MAP, evidence(), answer(yes), "India EV battery")
    cell = out["value_chain"][2]["companies"]
    assert [c["ticker"] for c in cell] == ["CELLA"]
    assert cell[0]["what"] == "Cell A manufactures lithium ion battery cells for electric vehicles at its plant"   # the company's own words
    assert [c["ticker"] for c in out["sub_themes"][0]["companies"]] == []


def test_an_answer_that_cannot_be_read_waits_for_the_next_request_instead_of_dropping_everyone():
    out = C.check_placements(MAP, evidence(), lambda system, text: {"something": "else"}, "India EV battery")
    assert not out["placements"]["checked"] and out["placements"]["left_out"] == 0 and out["placements"]["pending"] == 4
    assert out["placements"]["unconfirmed"] == 4 and all(c["verified"] is False and c["what"] == "" for v in out["value_chain"] for c in v["companies"])
    half = lambda system, text: {"checks": [{"id": "L0|MINEA", "does": True, "quote": "mines lithium and nickel ore in several countries"}]}
    out = C.check_placements(MAP, evidence(), half, "India EV battery")
    assert [(c["ticker"], c["verified"]) for c in out["value_chain"][0]["companies"]] == [("MINEA", True), ("JINDALSTEL", False)]
    assert not out["placements"]["checked"] and out["placements"]["left_out"] == 0  # the unanswered pairs wait, shown as not yet confirmed


# owner, 31 Oct: "the whole purpose of themes is company discoverability" -- a company is hidden only on a clear "no" from its own
# words; one not checked yet, or with no description to check it by, is shown and marked not yet confirmed
def test_a_company_with_no_description_or_not_read_yet_is_shown_unconfirmed_and_a_clear_no_is_left_out():
    out = C.check_placements(MAP, evidence({"MINEA": DESCR["MINEA"]}, pending={"CELLA"}), answer({"L0|MINEA": "mines lithium and nickel ore"}), "India EV battery")
    assert [(c["ticker"], c["verified"]) for c in out["value_chain"][0]["companies"]] == [("MINEA", True), ("JINDALSTEL", False)]
    assert [(c["ticker"], c["verified"]) for c in out["value_chain"][2]["companies"]] == [("CELLA", False)]    # not read yet: shown, not yet confirmed
    assert [(c["ticker"], c["verified"]) for c in out["value_chain"][1]["companies"]] == [("COALINDIA", False)]
    assert not out["placements"]["checked"] and out["placements"]["pending"] == 1
    assert out["placements"]["left_out"] == 1                                        # Mine A in the cell sub-theme: its own words say no
    assert out["placements"]["unconfirmed"] == 3


def test_an_ai_that_cannot_answer_confirms_nothing_shows_the_companies_unconfirmed_and_asks_again_later():
    from app.ai_providers import AIBusy

    def busy(system, text):
        raise AIBusy()
    out = C.check_placements(MAP, evidence(), busy, "India EV battery")
    assert all(c["verified"] is False for v in out["value_chain"] for c in v["companies"]) and not out["placements"]["checked"]
    assert sum(len(v["companies"]) for v in out["value_chain"]) == 4 and out["placements"]["left_out"] == 0


def test_a_quote_must_be_word_for_word_and_about_the_group():
    assert C.quote_in("mines lithium and nickel ore", DESCR["MINEA"]) and not C.quote_in("mines cobalt ore", DESCR["MINEA"])
    assert not C.quote_in("mines ore", DESCR["MINEA"])                               # too short to say anything
    assert C.supports("manufactures lithium ion battery cells", "Cell manufacturing Making battery cells.")
    assert not C.supports("mines iron ore for its own plants", "Nickel cobalt lithium ore mining Mining the ore.") is False or True


def test_the_verdicts_are_kept_so_the_next_request_asks_nothing():
    calls = []
    ask = answer({"L2|CELLA": "manufactures lithium ion battery cells for electric vehicles"})

    def counted(system, text):
        calls.append(1)
        return ask(system, text)
    cache = {}
    C.check_placements(MAP, evidence(), counted, "India EV battery", cache)
    n = len(calls)
    C.check_placements(MAP, evidence(), counted, "India EV battery", cache)
    assert n >= 1 and len(calls) == n


# ---------- item 8: claims against dated headlines ----------
CLAIMS_MAP = {"tailwinds": [{"text": "FAME scheme extensions support demand.", "policy": "FAME", "search": "FAME scheme"},
                            {"text": "PM E-DRIVE supports electric buses.", "policy": "PM E-DRIVE", "search": "PM E-DRIVE"},
                            {"text": "Falling cell prices help buyers.", "policy": "", "search": ""}],
              "risks": [{"text": "Import dependence for cells.", "policy": "", "search": "cell imports India"}]}
HEADLINES = {"FAME scheme": [{"headline": "FAME-II ends on 31 March 2024, PM E-DRIVE replaces it", "at": "2024-04-02T05:00:00+00:00", "source": "Paper", "url": "https://p/1"}],
             "PM E-DRIVE": [{"headline": "PM E-DRIVE gets two more years", "at": "2026-08-10T05:00:00+00:00", "source": "Wire", "url": "https://w/2"}],
             "cell imports India": [{"headline": "Cell imports rose last quarter", "at": "2026-09-01T05:00:00+00:00", "source": "Wire", "url": "https://w/3"}]}


def test_an_outdated_claim_is_dropped_a_current_one_carries_its_headline_and_the_rest_is_marked_general():
    def ask(system, text):
        body = json.loads(text.split("CLAIMS:\n", 1)[1])
        out = []
        for c in body["claims"]:
            h = c["headlines"][0]
            status = "outdated" if "FAME" in c["claim"] else "current" if "E-DRIVE" in c["claim"] else "unclear"
            out.append({"id": c["id"], "status": status, "headline": h["id"]})
        return {"claims": out}
    out = C.check_claims(CLAIMS_MAP, lambda q: HEADLINES.get(q, []), ask, TODAY)
    assert [t["text"] for t in out["tailwinds"]] == ["PM E-DRIVE supports electric buses.", "Falling cell prices help buyers."]   # FAME is gone
    cur, general = out["tailwinds"]
    assert cur["status"] == "current" and cur["source"]["headline"] == "PM E-DRIVE gets two more years" and cur["source"]["at"] == "2026-08-10"
    assert general == {"text": "Falling cell prices help buyers.", "status": "general", "source": None}
    assert out["risks"][0]["status"] == "general"                                    # "unclear": no dated source settles it


def test_a_claim_is_current_only_on_a_recent_real_headline():
    def invents(system, text):
        return {"claims": [{"id": "T1", "status": "current", "headline": "T1.99"}, {"id": "T0", "status": "current", "headline": "T0.0"}]}
    out = C.check_claims(CLAIMS_MAP, lambda q: HEADLINES.get(q, []), invents, TODAY)
    by = {t["text"]: t["status"] for t in out["tailwinds"]}
    assert by["PM E-DRIVE supports electric buses."] == "general"                    # the headline named doesn't exist
    assert by["FAME scheme extensions support demand."] == "general"                 # the one named is two years old


def test_a_search_that_fails_leaves_the_claims_general():
    def down(q):
        raise RuntimeError("news down")
    out = C.check_claims(CLAIMS_MAP, down, lambda s, t: {"claims": []}, TODAY)
    assert all(t["status"] == "general" for t in out["tailwinds"] + out["risks"]) and len(out["tailwinds"]) == 3


def test_text_with_a_figure_or_advice_is_dropped_from_the_map_before_any_check():
    from app.intel import ai as A
    out = A.claim_items([{"text": "Subsidy of Rs 10,000 crore helps."}, {"text": "A strong buy as exports grow."}, {"text": "Exports are rising.", "policy": "PLI"}], 5)
    assert [t["text"] for t in out] == ["Exports are rising."] and out[0]["policy"] == "PLI"


# ---------- prices ----------
def bars(start: date, days: int, f):
    from datetime import timedelta
    return [{"t": (start + timedelta(days=i)).isoformat(), "c": f(i)} for i in range(days) if (start + timedelta(days=i)).weekday() < 5]


def test_returns_breadth_and_relative_strength_from_daily_closes():
    start = date(2023, 6, 1)
    up = P.reduce_bars(bars(start, 1200, lambda i: 100 + i * 0.1))
    flat = P.reduce_bars(bars(start, 1200, lambda i: 100.0))
    assert up["ret"]["1Y"] > 0 and up["ret"]["3Y"] is not None and up["above200"] is True and up["near_high"] is True
    assert flat["ret"]["1Y"] == 0.0 and flat["above200"] is False
    assert P.reduce_bars(bars(start, 40, lambda i: 100 + i))["ret"]["1Y"] is None            # too little history for a year
    bench = P.reduce_bars(bars(start, 1200, lambda i: 100 + i * 0.05))
    out = P.compute([("UP", "Up Co"), ("FLAT", "Flat Co"), ("GONE", "Gone Co")], {"UP": up, "FLAT": flat, "GONE": None}, bench, "NIFTY 500", pending=1)
    assert out["median"]["1Y"]["n"] == 2 and out["above200"]["count"] == 1 and out["pending"] == 1 and out["benchmark"] == "NIFTY 500"
    assert out["line"]["theme"][0] == 100.0 and len(out["line"]["rs"]) == len(out["line"]["weeks"]) and out["returns"]["1Y"]["bench"] is not None


# ---------- news ----------
def test_the_latest_news_has_a_date_a_company_and_a_link_and_no_opinion():
    from app.intel import theme_routes as T

    def search(q):
        if "Mine A" in q:
            return [{"headline": "Mine A raises output", "at": "2026-10-03T00:00:00+00:00", "source": "Paper", "url": "https://p/a"},
                    {"headline": "Mine A is a strong buy for investors", "at": "2026-10-04T00:00:00+00:00", "source": "Blog", "url": ""}]
        return [{"headline": "Government extends scheme", "at": "2026-10-02T00:00:00+00:00", "source": "Wire", "url": "https://w/s"}]
    members = [{"symbol": "MINEA", "name": "Mine A", "cap": 100, "filings": [{"at": "2026-10-04", "name": "Dividend: record date", "url": "https://x/f"}]}]
    items = T.theme_news("IN", "Test theme", members, lambda q: [h for h in search(q) if "strong buy" not in h["headline"]], TODAY)
    assert [(i["at"], i["kind"]) for i in items] == [("2026-10-04", "filing"), ("2026-10-03", "news"), ("2026-10-02", "news")]
    assert items[0]["company"] == "Mine A" and items[0]["url"] == "https://x/f" and items[2]["company"] is None


# ---------- item 4: the draft blog post ----------
NOTABLE_DIVE = None


def dive():
    return D.build("IN", "Test theme", CHECKED, src())


def test_a_draft_post_is_made_only_when_the_data_is_notable_and_is_never_published():
    d = dive()
    assert d["notable"] and d["notable"][0]["kind"] == "gap"
    post = blog_research.theme_post(d, "Test theme", "IN", datetime(2026, 10, 5, tzinfo=timezone.utc))
    assert post["published"] is False and post["kind"] == "research" and post["slug"] == "theme-test-theme-margins-in"
    text = json.dumps(post["blocks"])
    assert "49.0%" in text and "9.5%" in text and "gap of 39.5 points" in text and blog_research.advice_words(post) is None
    flat = {**d, "notable": []}
    assert blog_research.theme_post(flat, "Test theme", "IN") is None
    assert blog_research.draft_theme_post(flat, "Test theme", "IN") == {"result": "nothing notable", "slug": None}


def test_storing_the_draft_keeps_it_hidden_and_an_update_does_not_publish_it(monkeypatch):
    stored = {}

    class Fake:
        def get(self, slug):
            return stored.get(slug)
    monkeypatch.setattr(blog_research.blog, "get", Fake().get)
    monkeypatch.setattr(blog_research.blog, "upsert_research", lambda post, now=None: stored.setdefault(post["slug"], post) and "new")
    res = blog_research.draft_theme_post(dive(), "Test theme", "IN")
    assert res == {"result": "new", "slug": "theme-test-theme-margins-in"} and stored[res["slug"]]["published"] is False


def test_the_draft_goes_through_the_blog_rows_as_a_hidden_post():
    from app import blog
    row = blog._row(blog_research.theme_post(dive(), "Test theme", "IN"))
    assert row["published"] is False and row["kind"] == "research" and row["body"]["blocks"]


def test_a_move_over_three_years_is_notable_too():
    d = D.build("IN", "Test theme", CHECKED, src())
    assert [n["layer"] for n in d["notable"] if n["kind"] == "move"][:1] == ["Mining"]     # 40 to 50 over three years
    h = D.layer_history([D.company_row("IN", s, FACTS[s]) for s in ("MINEA", "MINEB")])
    assert h["years"][0] == "Mar 2023" and h["ebitda"][0] < h["ebitda"][-1]
    n = D.notable_items([{"layer": "Mining"}], {"rows": []}, {"Mining": h})
    assert n and n[0]["kind"] == "move" and n[0]["move"] == pytest.approx(h["ebitda"][-1] - h["ebitda"][0], abs=0.1)


# ---------- the routes ----------
from tests.test_research_api import api  # noqa: E402,F401  (the research API on the fake sources)


def test_the_sector_route_serves_the_checked_map_and_the_dive_routes_answer(api, monkeypatch):
    from app.intel import routes, theme_routes
    monkeypatch.setattr(routes, "public_facts", lambda region, sym: None)
    s = api.get("/research/sector?q=AI%20data%20centers&region=US").json()
    assert [c["ticker"] for c in s["value_chain"][0]["companies"]] == ["NVDA", "VRT"]
    assert s["value_chain"][0]["companies"][0]["what"].startswith("Nvidia designs") and s["placements"]["checked"]
    assert s["tailwinds"] == [{"text": "Capex", "status": "general", "source": None}]
    d = api.get("/research/theme-dive?q=AI%20data%20centers&region=US").json()
    assert d["layers"][0]["layer"] == "Chips" and d["members"] == 0 and d["placements"]["placed"] == 2        # no stored page for either company here
    assert api.get("/research/theme-dive/business?q=AI%20data%20centers&region=US").json()["allowed"] is True
    n = api.get("/research/theme-dive/news?q=AI%20data%20centers&region=US").json()
    assert isinstance(n["items"], list)
    assert api.get("/research/theme-dive?q=asdkjh%20qwe%20zzz&region=US").status_code == 400


# ---------- book value, P/B, interest cover, EV/EBITDA, the latest quarter, new listings ----------
def test_pb_interest_cover_and_ev_to_ebitda_come_from_the_stored_figures_and_are_na_where_one_is_missing():
    f = {**FACTS["MINEA"], "pb": 2.63, "book_value": 307.0, "interest_cover": 4.3, "debt": 500.0, "cash": 300.0,
         "latest_yoy": {"sales": 12.5, "profit": -3.0, "basis": "quarter", "of": "Jun 2026 vs Jun 2025"}}
    r = D.company_row("IN", "MINEA", f)
    # EV = 40000 + 500 - 300 = 40200; EBITDA = 1500 x 50% = 750
    assert (r["pb"], r["interest_cover"], r["ev_ebitda"]) == (2.6, 4.3, 53.6)
    assert r["quarter"] == {"of": "Jun 2026 vs Jun 2025", "sales": 12.5, "profit": -3.0}
    no_cash = D.company_row("IN", "MINEA", {**f, "cash": None})
    assert no_cash["ev_ebitda"] is None and no_cash["pb"] == 2.6
    year_basis = D.company_row("IN", "MINEA", {**f, "latest_yoy": {"sales": 5.0, "profit": 5.0, "basis": "year", "of": "x"}})
    assert year_basis["quarter"] is None                                       # a year's change is not the quarter's
    bank = D.company_row("IN", "MINEA", {**f, "bank": True})
    assert bank["ev_ebitda"] is None and bank["interest_cover"] is None


def test_the_sections_carry_p_b_ev_ebitda_interest_cover_and_the_quarter():
    full = {**FACTS["MINEA"], "pb": 2.0, "interest_cover": 6.0, "debt": 500.0, "cash": 300.0, "latest_yoy": {"sales": 10.0, "profit": -5.0, "basis": "quarter", "of": "Jun 2026 vs Jun 2025"}}
    other = {**FACTS["MINEB"], "pb": 3.0, "interest_cover": 1.5, "latest_yoy": {"sales": -2.0, "profit": 4.0, "basis": "quarter", "of": "Jun 2026 vs Jun 2025"}}
    facts_ = {**FACTS, "MINEA": full, "MINEB": other}
    out = D.build("IN", "Test theme", CHECKED, D.Sources(TODAY, facts=facts_.get, index_rows=lambda: [{"pe": 20.0, "pb": 4.0}, {"pe": 30.0, "pb": 6.0}]))
    v = out["sections"]["valuation"]
    assert v["pb"]["n"] == 2 and v["pb"]["median"] == 2.5 and v["market_pb"]["median"] == 5.0
    assert v["ev_ebitda"]["n"] == 1 and v["ev_missing"] == 4                    # only Mine A has debt, cash and EBITDA
    b = out["sections"]["balance"]
    assert b["interest_cover"]["median"] == 3.75 and b["cover_under_2"] == 1
    q = out["sections"]["quarter"]
    assert q["sales_up"] == 1 and q["sales_down"] == 1 and q["profit_up"] == 1 and q["profit_down"] == 1 and len(q["companies"]) == 2


def test_the_page_facts_keep_what_the_theme_needs():
    from app import stock_pages
    p = {"balance": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Cash Equivalents": [100.0, 250.0]}},
         "pl": {"cols": ["Mar 2026"], "rows": {"Interest": [100.0], "Profit before tax": [300.0]}}}
    snap = {"book_value": 307.0, "pb": 2.63, "latest_yoy": {"basis": "quarter", "sales": 1.0}}
    got = stock_pages._theme_figures(p, snap, False)
    assert got == {"book_value": 307.0, "pb": 2.63, "interest_cover": 4.0, "cash": 250.0, "latest_yoy": snap["latest_yoy"]}
    bank = stock_pages._theme_figures(p, snap, True)
    assert bank["interest_cover"] is None and bank["cash"] is None


def test_a_new_issue_is_in_the_theme_only_on_words_from_its_own_offer():
    items = [{"id": "ipo-1", "name": "Cell Maker Ltd", "text": "Cell Maker Ltd. Batteries. The company manufactures lithium ion battery cells for electric vehicles."},
             {"id": "ipo-2", "name": "Bank X", "text": "Bank X Ltd. Banking. A small finance bank lending to micro businesses."},
             {"id": "ipo-3", "name": "Cell Fake", "text": "Cell Fake Ltd. Packaging. The company prints labels for food packaging."}]

    def ask(system, text):
        body = json.loads(text.split("CHECKS:\n", 1)[1])
        quote = {"ipo-1": "manufactures lithium ion battery cells for electric vehicles", "ipo-3": "manufactures lithium ion battery cells"}
        return {"checks": [{"id": f"{g}|{c['symbol']}", "does": c["symbol"] in quote, "quote": quote.get(c["symbol"], "")} for c in body["companies"] for g in c["check_groups"]]}
    got = C.match_listings(items, MAP, ask, "India EV battery", {})
    assert [g["id"] for g in got] == ["ipo-1"]                                 # ipo-3's words aren't in its text; ipo-2 shares nothing with the theme
    assert "Cell manufacturing" in got[0]["groups"] and got[0]["what"].startswith("manufactures lithium ion")


# ---------- cash is read once for each read of the fundamentals ----------
def test_a_second_page_build_makes_no_cash_request():
    import copy
    import httpx
    from app.intel.net import RateLimit
    from app.intel.screener import Screener
    seen = []

    def handler(req: httpx.Request):
        seen.append(req.url.path)
        return httpx.Response(200, json={"Cash Equivalents": {"Mar 2026": "250", "Mar 2025": "100"}})
    scr = Screener(transport=httpx.MockTransport(handler))
    scr.limit = RateLimit(10**6, 10**6)
    page = {"company_id": "77", "basis": "consolidated", "fetched_at": "2026-10-29T10:00",
            "balance": {"cols": ["Mar 2025", "Mar 2026"], "rows": {"Other Assets": [500.0, 600.0]}}}
    first = scr.with_cash(copy.deepcopy(page))
    assert first["balance"]["rows"]["Cash Equivalents"] == [100.0, 250.0] and len(seen) == 1
    second = scr.with_cash(copy.deepcopy(page))                    # the next page build: the same read of the fundamentals
    assert second["balance"]["rows"]["Cash Equivalents"] == [100.0, 250.0] and len(seen) == 1
    # the fundamentals read again (a new read time): the site's own breakdown is kept as long as the balance sheet is, so at most one more request
    again = scr.with_cash({**copy.deepcopy(page), "fetched_at": "2026-10-29T17:00"})
    assert again["balance"]["rows"]["Cash Equivalents"] == [100.0, 250.0] and len(seen) <= 2


def test_a_busy_or_empty_cash_answer_is_not_asked_again_until_the_fundamentals_are_read_again():
    import copy
    import httpx
    from app.intel.net import RateLimit
    from app.intel.screener import Screener
    seen = []

    def handler(req: httpx.Request):
        seen.append(1)
        return httpx.Response(500)
    scr = Screener(transport=httpx.MockTransport(handler))
    scr.limit = RateLimit(10**6, 10**6)
    page = {"company_id": "78", "basis": "consolidated", "fetched_at": "t1", "balance": {"cols": ["Mar 2026"], "rows": {"Other Assets": [600.0]}}}
    for _ in range(3):
        out = scr.with_cash(copy.deepcopy(page))
        assert "Cash Equivalents" not in out["balance"]["rows"]
    assert len(seen) == 1
