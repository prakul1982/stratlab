"""Lane r58 (R58): the owner's review of the live R57.2 decks, the open items and the Admin issues. Each test fails on origin/main
22cef77 and passes after, unless it says it is a guard."""
import gzip
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts"))

from app.intel import sec          # noqa: E402

SEC_FIX = pathlib.Path(__file__).parent / "fixtures" / "sec_r58"


def facts(name):
    return json.loads(gzip.open(SEC_FIX / f"{name}.json.gz").read())


# ---------- P0-1: a bank's and an insurer's revenue by the sector's own accounting (the companies' FY2025 10-K and 20-F lines, as the
# SEC's company facts give them, cut to the revenue and profit concepts) ----------
@pytest.mark.parametrize("name,nii,nonint", [("fitb", 5982, 3035), ("hban", 5991, 2175), ("mtb", 6948, 2742)])
def test_p01_a_bank_s_revenue_is_net_interest_income_plus_non_interest_income(name, nii, nonint):
    rev = sec.revenue(facts(name)["facts"], "annual")
    assert rev["2025-12-31"] == pytest.approx((nii + nonint) * 1e6)        # not its lease income or its contract-revenue fees


def test_p01_an_ifrs_bank_s_revenue_is_net_interest_and_net_fee_income():
    f = facts("bsbr")["facts"]
    rev = sec.revenue(f, "annual", unit="BRL")
    assert rev["2025-12-31"] == pytest.approx((57634.0 + 17495.0) * 1e6, rel=1e-3)


@pytest.mark.parametrize("name", ["fitb", "hban", "mtb"])
def test_p01_no_bank_net_margin_above_100_percent(name):
    p = sec.build(facts(name))
    rows = p["pl"]["rows"]
    for s, n in zip(rows["Sales"], rows["Net Profit"]):
        if s and n:
            assert n / s <= 1.0, (name, s, n)
    assert p["figure_errors"] == []


def test_p01_a_net_profit_above_a_financial_filer_s_revenue_withholds_the_revenue_and_names_the_line():
    def yr(y, v):
        return {"start": f"{y}-01-01", "end": f"{y}-12-31", "val": v, "form": "10-K", "filed": f"{y + 1}-02-20", "fy": y, "fp": "FY"}
    # a bank whose only revenue-like line is its lease income, and no net interest income line at all: nothing to read its own revenue from
    f = {"facts": {"us-gaap": {"OperatingLeaseLeaseIncome": {"units": {"USD": [yr(2025, 80e6)]}},
                               "NoninterestIncome": {"units": {"USD": [yr(2025, 3e9)]}},
                               "InterestAndDividendIncomeOperating": {"units": {"USD": [yr(2025, 9e9)]}},
                               "NetIncomeLoss": {"units": {"USD": [yr(2025, 2.5e9)]}}}}}
    p = sec.build(f, {"sic": "6022"})
    assert p["pl"]["rows"]["Sales"][-1] == 12000.0      # interest income plus fees (no interest expense filed), not the lease income
    # ...and with a fee line only, the profit is above the revenue: withheld, and the error names the line
    f["facts"]["us-gaap"].pop("InterestAndDividendIncomeOperating")
    f["facts"]["us-gaap"].pop("NoninterestIncome")
    f["facts"]["us-gaap"]["InterestIncomeExpenseNet"] = {"units": {"USD": [yr(2024, 5e9)]}}
    p = sec.build(f, {"sic": "6022"})
    assert p["pl"]["rows"]["Sales"][-1] is None
    assert "OperatingLeaseLeaseIncome" in p["figure_errors"][0] and "withheld" in p["figure_errors"][0]


def test_p01_an_insurer_s_revenue_is_premiums_plus_investment_income_when_its_total_is_only_a_part():
    def yr(v):
        return {"start": "2025-01-01", "end": "2025-12-31", "val": v, "form": "10-K", "filed": "2026-02-20"}
    f = {"us-gaap": {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [yr(300e6)]}},
                     "PremiumsEarnedNet": {"units": {"USD": [yr(8e9)]}},
                     "NetInvestmentIncome": {"units": {"USD": [yr(1e9)]}}}}
    assert sec.revenue(f, "annual") == {"2025-12-31": 9.3e9 - 0.3e9}
    # a total at or above its premiums is the insurer's own total, kept (guard)
    f["us-gaap"]["Revenues"] = {"units": {"USD": [yr(9.6e9)]}}
    assert sec.revenue(f, "annual") == {"2025-12-31": 9.6e9}


# ---------- P0-2: a non-bank financier in a bank theme is adjacent, named and counted apart ----------
from app.intel import theme_base as B          # noqa: E402
from app.intel import theme_data as TD         # noqa: E402

PFC_WORDS = ("Power Finance Corporation Limited is a Systemically Important Non-Deposit taking NBFC registered with the RBI as an Infrastructure "
             "Finance Company. It is engaged in extending financial assistance to the Indian power sector.")
REC_WORDS = ("REC is a Central Public Sector Undertaking under the Ministry of Power involved in financing projects in the complete power sector "
             "value chain from generation to distribution.")
FIN_INST = "Financial Services > Financial Services > Finance > Financial Institution"


def test_p02_infrastructure_finance_nbfcs_are_adjacent_in_a_bank_theme():
    a = TD.scope_adjacent({"industry": FIN_INST}, "Public sector banks", "", PFC_WORDS)
    assert a and a["kind"] == "non-bank financiers"
    assert TD.scope_adjacent({"industry": "Financial Institution"}, "Public sector banks", "", REC_WORDS)["kind"] == "non-bank financiers"
    # its own words alone, with no industry stored
    assert TD.scope_adjacent({"industry": ""}, "Regional banks", "", PFC_WORDS)["kind"] == "non-bank financiers"


def test_p02_guard_a_bank_is_core_and_a_finance_theme_keeps_its_nbfcs():
    bank = "Financial Services > Financial Services > Banks > Public Sector Bank"
    assert TD.scope_adjacent({"industry": bank}, "Public sector banks", "", "State Bank of India is the largest bank.") is None
    assert TD.nonbank_adjacent({"industry": FIN_INST}, "Infrastructure finance companies", PFC_WORDS) is None
    assert TD.nonbank_adjacent({"industry": FIN_INST}, "Defence", PFC_WORDS) is None


# ---------- P0-3: a populated layer never vanishes because it is small or because the rules changed ----------
import release_gate as G          # noqa: E402

LIVE = pathlib.Path(__file__).parent / "fixtures" / "themes_live" / "r58"


def test_p03_a_one_company_layer_of_the_published_version_stays_when_its_words_say_it():
    words = ("PB Fintech is India's largest online platform for insurance and lending products. It runs an asset-light model for distributing "
             "and servicing financial products.")
    vc = [{"layer": "Life insurance underwriting", "companies": [{"ticker": "A"}, {"ticker": "B"}]},
          {"layer": "Distribution and aggregation", "companies": [{"ticker": "PB", "name": "PB Fintech"}]},
          {"layer": "Other insurance companies", "official": True, "basis": "rest", "companies": []}]
    out, rows = B.single_layers([dict(v) for v in vc], lambda s: words if s == "PB" else "", "Insurance", {"PB": "Distribution and aggregation"})
    # r582 (R58.2, updated on purpose: the brief on the live R58.1 decks, "a layer with one company either gains the stored members whose own
    # words support it, or the company folds into the best-fitting layer by its own words"): no company says its name, so the layer of one
    # is not kept; its company goes to "Other", with why
    assert not [v for v in out if v["layer"] == "Distribution and aggregation"] and rows and rows[0]["to"] == "Other insurance companies"
    # guard: a one-company layer no published version had, whose words don't say it, is still folded
    out, rows = B.single_layers([dict(v) for v in vc], lambda s: words if s == "PB" else "", "Insurance", {})
    assert rows and rows[0]["to"] == "Other insurance companies"


def test_p03_retail_s_single_category_specialty_retailers_comes_back_on_the_fresh_live_input():
    d = G.load(LIVE / "retail.json")
    with G.offline():
        out = G.engine(d)[0]
    lay = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out["value_chain"]}
    assert len(lay.get("Single-category specialty retailers") or []) >= 7, sorted(lay)
    assert not [f for f in G.lost_layers(d, out["value_chain"])]


def test_p03_the_gate_fails_a_published_layer_the_placement_loses():
    d = {"theme": "Insurance", "published": {"PB": "Distribution and aggregation", "A": "Life insurance underwriting", "B": "Life insurance underwriting"}}
    vc = [{"layer": "Life insurance underwriting", "companies": [{"ticker": "A"}, {"ticker": "B"}]},
          {"layer": "Other insurance companies", "official": True, "basis": "rest", "companies": [{"ticker": "PB"}]}]
    f = G.lost_layers(d, vc)
    assert [x["subject"] for x in f] == ["Distribution and aggregation"] and "Other insurance companies 1" in f[0]["detail"]
    vc[1]["companies"] = []
    vc.insert(1, {"layer": "Distribution and aggregation", "companies": [{"ticker": "PB"}]})
    assert G.lost_layers(d, vc) == []


# ---------- P1-7: Admin issues ----------
from datetime import datetime, timedelta, timezone      # noqa: E402

from app import ai_reply                                 # noqa: E402
from app.intel import theme_routes as TR                 # noqa: E402
from app.intel import theme_prices                       # noqa: E402


def test_p17_old_errors_age_out_of_the_overview_and_fresh_ones_never_hide():
    from app import main
    now = datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc)
    errs = [{"ref": "A", "at": "2026-10-04T16:43:12.479683+05:30", "error": "KeyError: 819"},
            {"ref": "B", "at": "2026-11-12T17:20:17.099692+05:30", "error": "ZeroDivisionError"},
            {"ref": "C", "at": "not a time", "error": "x"}]
    keep, old = main.fresh_errors(errs, now)
    assert [e["ref"] for e in keep] == ["B", "C"] and old == 1
    assert main.ERRORS_KEEP_DAYS == 7


def test_p17_a_reply_with_braces_around_its_json_or_a_trailing_comma_is_read():
    assert ai_reply.extract_json('Here is the {answer}:\n{"moves": [{"a": 1},], "n": 2,}\nNote: see {x}.') == {"moves": [{"a": 1}], "n": 2}
    assert ai_reply.extract_json('{"a": {"b": 2}} and then {"c": 3}') == {"a": {"b": 2}}
    with pytest.raises(ai_reply.AIError):            # guard: no object at all is still no answer
        ai_reply.extract_json("I cannot answer that.")


def test_p17_guard_the_theme_line_never_divides_by_a_nil_close():
    # (already fixed on main by 60b969c, after the 12 Nov error: a guard that the line stays defined)
    weeks, line = theme_prices.equal_weight([{"weeks": [1, 2], "closes": [0.0, 1.0]}, {"weeks": [1, 2], "closes": [1.0, 1.1]},
                                             {"weeks": [1, 2], "closes": [2.0, 2.2]}])
    assert line[-1] == pytest.approx(110.0)


def test_p17_a_theme_s_data_gaps_are_tried_before_they_escalate_and_each_left_says_why(monkeypatch):
    kept = {}
    monkeypatch.setattr(TR.db, "get_setting", lambda k: kept.get(k))
    monkeypatch.setattr(TR.db, "update_setting", lambda k, fn: kept.__setitem__(k, fn(kept.get(k))) if fn(kept.get(k)) is not None else None)
    TR.flag_gaps("US", "Software", [{"ticker": "AAA", "name": "Aaa Inc", "cap": 9.0, "lacks": ["description"]},
                                    {"ticker": "BBB", "name": "Bbb Inc", "cap": 8.0, "lacks": ["figures"]},
                                    {"ticker": "CCC", "name": "Ccc Inc", "cap": 7.0, "lacks": ["figures"]}])
    words = {}

    def reader(region, names, budget=None, again=()):
        def read(syms):
            for s_ in syms:
                words[s_] = "Aaa makes software for banks."
        return read
    monkeypatch.setattr(TR, "evidence_reader", reader)
    monkeypatch.setattr(TR, "_stored_evidence", lambda region, s_: {"about": words.get(s_)} if s_ in words else {})
    monkeypatch.setattr(TR.computed, "put", lambda *a, **k: None)

    class Busy(Exception):
        pass

    def build(region, s_):
        if s_ == "CCC":
            raise Busy()
        return {"years": [{"year": "2025"}]}
    monkeypatch.setattr(TR._routes(), "build_page", build, raising=False)
    check = TR.data_gap_checks()[0]
    assert check.fix is not None                      # tried, never escalated untried
    got = check.fix()
    assert got == {"tried": 3, "filled": 2, "left": 1}
    left = TR.data_gap_checks()[0]
    assert "Ccc Inc (figures: its company page could not be built now (the pages' per-minute ration was taken))" in left.problem


# ---------- P1-6: the owner's open items ----------
from app.intel import theme_changes as TCH       # noqa: E402


def test_p16_a_removed_layer_never_says_its_companies_left_the_theme_when_they_are_past_the_figures_count():
    was = {"layers": ["Home textiles (larger)", "Spinning mills"], "cos": {"A": ["A", 0], "B": ["B", 0], "C": ["C", 0], "S": ["S", 1]}}
    now = {"layers": ["Spinning mills"], "cos": {"S": ["S", 0]},
           "rest": {"A": ["A", 0], "B": ["B", 0], "C": ["C", 0]}, "rest_layers": ["Home textiles (smaller)"]}
    ev, _ = TCH._layer_events(was, now)
    gone = next(x for x in ev if x["kind"] == "removed")
    assert gone["went"] == {"Home textiles (smaller)": 3}, gone          # none said to be out of the theme


def test_p16_a_parent_and_its_subsidiary_filer_merge_when_the_dive_s_descriptions_leave_the_filer_s_titles_out():
    rows = [{"symbol": "TRP", "name": "TC Energy Corp", "year": "2025", "revenue": 10681.0, "profit": 2470.0, "cap": 67400.0},
            {"symbol": "TCPA", "name": "Transcanada Pipelines Ltd", "year": "2025", "revenue": 10679.5, "profit": 2466.0, "cap": 21400.0}]
    raw = {"TRP": "TC Energy Corporation is a Canadian energy company.", "TCPA": "From its own filings: Annual report (40-F)."}

    def about(s_):
        t = raw.get(s_) or ""
        return None if t.startswith("From its own filings:") else t
    about.filed_only = lambda s_: str(raw.get(s_) or "").startswith("From its own filings:")
    assert TD.same_company(rows, about=about) == {"TCPA": "TRP"}
    del about.filed_only                     # guard: with no word of the filer, two companies with no words stay apart
    assert TD.same_company(rows, about=about) == {}


def test_p16_a_computing_layer_made_by_how_companies_earn_is_not_made_in_an_oil_theme():
    vc = [{"layer": "Midstream pipelines", "companies": [{"ticker": "P"}]},
          {"layer": "Data centres, hosting and networks", "by_model": True, "companies": [{"ticker": "NUAI", "name": "New Era"}, {"ticker": "SEI"}]},
          {"layer": "Other oil and gas companies", "official": True, "basis": "rest", "companies": []}]
    out, rows = B.off_theme_compute([dict(v) for v in vc], "Oil and gas")
    assert [v["layer"] for v in out] == ["Midstream pipelines", "Other oil and gas companies"] and len(rows) == 2
    assert out[-1]["companies"][0]["refit"]["why"].startswith("a group by how they earn")
    out, rows = B.off_theme_compute([dict(v) for v in vc], "Software")         # guard: a computing theme keeps it
    assert not rows


def test_p16_a_name_none_of_its_companies_say_takes_their_word_in_place_not_in_brackets():
    texts = ["Boeing is among the largest global aerospace manufacturers; it builds commercial jetliners and military aircraft",
             "Embraer designs and builds aircraft"]
    assert B.in_place_name("Commercial airframe integration", "aircraft", texts) == "Commercial aircraft"
    assert B.in_place_name("Commercial and business lenders", "bank", ["a bank holding company for commercial and business customers"]) \
        == "Commercial and business banks"
    assert B.in_place_name("Aircraft makers", "aircraft", texts) == ""          # guard: their word in it already


def test_p16_a_company_kept_on_its_own_words_against_one_layer_s_answer_says_so_never_true():
    c = {"base": True, "basis": "words", "verified": False, "industry": "", "placed": "words",
         "kept_member": "kept in the theme: the map's check said no for “Engines” only, one layer's answer; its own words say the theme's work"}
    rec = TD.theme_record(c, "core")
    assert rec["by"] == "words" and "True" not in rec["why"] and rec["why"].startswith("the map's check said no")
    c2 = {"base": True, "industry": "Banks", "kept_member": True}
    assert "True" not in TD.theme_record(c2, "core")["why"]


# ---------- P1-5: national money-centre banks and small community banks are not one comparison ----------
def test_p15_a_layer_joining_a_large_and_a_small_scale_is_split_by_scale():
    caps = [800, 300, 250, 90, 40, 30, 20, 9, 5, 4, 3, 2, 1, 0.5]
    vc = [{"layer": "Large national banks and small community banks", "companies": [{"ticker": f"B{i}", "cap": c * 1000} for i, c in enumerate(caps)]}]
    out = B.scale_bands(vc)
    names = {v["layer"]: [c["ticker"] for c in v["companies"]] for v in out}
    assert set(names) == {"Large national banks", "Mid-sized banks", "Small community banks"}
    assert names["Large national banks"] == ["B0", "B1", "B2", "B3"] and "B13" in names["Small community banks"]
    assert all(c["refit"]["why"].startswith("“Large national banks and small community banks” split by scale") for v in out for c in v["companies"])
    assert B.scale_bands([{"layer": "Deposit-funded banks", "companies": vc[0]["companies"]}])[0]["layer"] == "Deposit-funded banks"   # guard


def test_p16_a_removal_s_quoted_words_hold_no_bracket_of_their_own():
    w = ("SBI Cards and Payment Services Limited (“SBI Card” or the “Company”) is a non-deposit accepting systemically "
         "important nonbanking financial company. It issues credit cards.")
    why = TCH.unnamed_why("no longer in the theme's map", w, "", {"autom", "vehic"})
    assert "(" not in why and ")" not in why and "SBI Cards and Payment Services Limited is a non-deposit" in why


def test_p16_broadband_operators_are_adjacent_in_a_media_theme_and_a_media_group_is_not():
    ch = "Charter Communications is a leading broadband connectivity company with services available to more than 57 million homes."
    cm = "Comcast Corporation is a global media and technology company. Our Connectivity & Platforms business provides broadband and video."
    a = TD.scope_adjacent({"industry": "Cable & Other Pay Television Services"}, "Media and entertainment", "", ch, None, "telecom_services", "medium")
    assert a and a["kind"] == "telecom and broadband operators"
    assert TD.scope_adjacent({"industry": "Cable & Other Pay Television Services"}, "Media and entertainment", "", cm, None, "telecom_services", "medium") is None
    assert TD.scope_adjacent({"industry": ""}, "Telecom", "", ch, None, "telecom_services", "medium") is None


# ---------- P1-4: a coverage fall says why, in companies new to the theme and core vs adjacent ----------
def test_p14_a_fall_from_companies_new_to_the_theme_in_other_is_said():
    snap = {"layers": ["Card networks", "Other payments companies"], "cos": {"V": ["Visa", 0], "MA": ["Mastercard", 0], "X": ["X", 1]}}
    dive = {"layers": [{"layer": "Card networks", "companies": [{"symbol": "V"}, {"symbol": "MA", "adjacent": {"kind": "lenders"}}]},
                       {"layer": "Other payments companies", "companies": [{"symbol": "X"}, {"symbol": "JPM"}, {"symbol": "NU"}]}]}
    why = TCH.fall_why(snap, dive)
    assert why.get("new to the theme, placed in “Other” (the count of companies placed grew; no company left a layer for it)") == 2
    assert why.get("now an adjacent participant (another kind of business), shown apart from the core members") == 1


# ---------- P2-8: no near-empty continuation page, no row's words lost ----------
def test_p28_a_row_taller_than_a_page_is_carried_on_in_pieces_never_a_page_that_draws_none_of_it():
    from app import deck as D
    head, w = D.COVERAGE_HEAD, [1.8, 1.6, 8.0]
    long = " ".join(f"Filed under Retail-Catalog but in another business: Company{i} Inc, a maker of things;" for i in range(120))
    rows = [["A", "1", "short"], ["Screened out:", "", long], ["Since the previous version", "2", "On 16 Nov added 2."]]
    pages = D.table_pages(head, rows, w, D.CW, D.BOT - D.TOP)
    for p in pages:          # every row of every page is drawn
        lay = D.table_layout({"head": head, "rows": p, "widths": w, "numeric": [False] * 3, "strong": (), "compact": False}, D.CW, D.BOT - D.TOP)
        assert len(lay["rows"]) == len(p) >= 2
    assert " ".join(r[2] for p in pages for r in p if r[0].startswith("Screened out:")) == long


def test_p03_guard_a_layer_a_rule_did_not_make_with_its_reason_is_no_lost_layer():
    d = {"theme": "Oil and gas", "published": {"N": "Data centres, hosting and networks", "P": "Midstream"}}
    vc = [{"layer": "Midstream", "companies": [{"ticker": "P"}]},
          {"layer": "Other oil and gas companies", "official": True, "basis": "rest",
           "companies": [{"ticker": "N", "refit": {"from": "Data centres, hosting and networks", "to": "", "why": "a group by how they earn"}}]}]
    assert G.lost_layers(d, vc) == []
