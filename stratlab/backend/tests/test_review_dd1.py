"""A harsh audit of the signed-in company pages' data (DD-003 to DD-071): a BSE code that found nothing, a stray suggestion,
a new listing's change against its open, a merged company shown as live, growth across a merger, a bank's measures, special
and pre-bonus dividends, ratios without their periods, a profit fall against a quarter lifted by one-off income, growth off a
tiny base, US results against estimates checked by the filings, a rounding split, an interest cover nobody disclosed, the
report card's units, and the watchlist's unknown symbols and Stage."""
import pytest

from app import checklist, corp_actions, deepdive, main, report_card, suggest
from app.intel import ai as A
from app.intel import company, grounding, key_facts, routes
from app.kite_service import bse_only_rows, bse_twin_codes
from tests import world


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    main.suggester.clear()
    yield built
    main.suggester.clear()
    built["close"]()


def bse(ts, code, name):
    return {"instrument_token": int(code) * 10, "exchange_token": code, "tradingsymbol": ts, "name": name, "segment": "BSE",
            "instrument_type": "EQ"}


NSE = [{"symbol": "RELIANCE", "name": "RELIANCE INDUSTRIES", "exchange": "NSE", "type": "EQ"},
       {"symbol": "TCS", "name": "TATA CONSULTANCY SERV LT", "exchange": "NSE", "type": "EQ"}]


# ---------- DD-003: a BSE code of an NSE company finds it ----------
def test_a_bse_code_of_a_company_on_both_exchanges_is_mapped_to_its_nse_symbol():
    raw = [bse("RELIANCE", 500325, "RELIANCE INDUSTRIES"), bse("TCSLTD", 532540, "TATA CONSULTANCY SERV LT"), bse("TINYCO", 543210, "TINY CO")]
    assert bse_twin_codes(raw, NSE) == {"RELIANCE": "500325", "TCS": "532540"}
    rows = suggest.india_rows([{**r, "token": 1} for r in NSE], None, {"RELIANCE": "500325"})
    assert suggest.rank("500325", rows)[0]["symbol"] == "RELIANCE"
    # with the broker offline, the stored list carries the saved code for its NSE company
    stored = suggest.plain_rows("IN", {"RELIANCE": {"name": "Reliance Industries", "bse": None, "twin": "500325"}})
    assert suggest.rank("500325", stored)[0]["id"] == "RELIANCE"


def test_the_search_and_the_company_page_resolve_a_bse_code_to_the_nse_company(w):
    h = world.headers("pro-token")
    rows = w["client"].get("/suggest/companies?q=500325&market=IN", headers=h).json()["rows"]
    assert rows and rows[0]["symbol"] == "RELIANCE" and rows[0]["id"] == "RELIANCE"
    c = w["client"].get("/research/company/IN/500325?lean=true", headers=h).json()
    assert c["symbol"] == "RELIANCE" and c["exchange"] == "NSE" and c["quote"]["price"]
    assert main.nse_twin_of("500325") == "RELIANCE" and main.nse_twin_of("543210") is None     # a BSE-only company stays at its code


# ---------- DD-004: one suggestion per company ----------
def test_a_scrip_listed_twice_on_the_broker_is_one_row_and_one_suggestion():
    raw = [bse("540709", 540709, "RELIANCE HOME FINANCE"), bse("RHFL", 540709, "RELIANCE HOME FINANCE")]
    got = bse_only_rows(raw, [])
    assert [x["tradingsymbol"] for x in got] == ["RHFL"]
    rows = [suggest._entry("540709", "RELIANCE HOME FINANCE", "BSE", "IN", code="540709", ident="540709"),
            suggest._entry("RHFL", "RELIANCE HOME FINANCE", "BSE", "IN", code="540709", ident="540709")]
    s = suggest.Suggester({"IN": lambda: rows, "US": lambda: []}, {"IN": dict, "US": dict})
    found = s.search("reliance home", "IN")
    assert [r["id"] for r in found] == ["540709"]


# ---------- DD-010, DD-011: a new listing ----------
def test_a_first_session_is_changed_against_the_issue_price_never_the_open():
    q = {"price": 1133.80, "prev_close": 1160.0, "change": -26.2, "change_pct": -2.26, "at": "2026-10-23T15:30:00+05:30"}
    bars = [{"t": "2026-10-23T00:00:00+05:30", "c": 1133.8}]
    assert company.first_session(q, bars) and not company.first_session(q, [{"t": "2026-10-22T00:00:00+05:30"}, *bars])
    got = company.against_issue(q, 700.0)
    assert got["prev_close"] == 700.0 and got["change"] == 433.8 and got["change_pct"] == 61.97 and got["ref"] == "issue"
    # without an issue price no change is given, rather than one against the open
    assert company.against_issue(q, None)["change_pct"] is None


def test_yahoos_first_session_reference_is_its_issue_price():
    from app.intel.yahoo import _previous_close
    from datetime import datetime, timezone
    at = lambda h: datetime(2026, 10, 23, h, 0, tzinfo=timezone.utc).timestamp()      # noqa: E731
    meta = {"regularMarketTime": at(10), "exchangeTimezoneName": "Asia/Kolkata", "firstTradeDate": at(3),
            "previousClose": 159.25, "chartPreviousClose": 151.0}
    assert _previous_close(meta, [{"t": "2026-10-23", "c": 138.25}]) == 151.0
    older = {**meta, "firstTradeDate": 1500000000}
    assert _previous_close(older, [{"t": "2026-10-23", "c": 138.25}]) == 159.25


def test_a_new_listings_range_is_since_listing_and_its_value_on_the_shares_now_in_issue():
    from datetime import date
    assert company.listing_day([{"t": "2026-10-23"}], date(2026, 10, 25)) == "2026-10-23"
    assert company.listing_day([{"t": "2025-10-20"}], date(2026, 10, 25)) is None
    assert company.balance_before({"balance": {"cols": ["Mar 2025", "Mar 2026"]}}, "2026-10-23")
    assert not company.balance_before({"balance": {"cols": ["Mar 2026", "Sep 2026"]}}, "2026-09-10")
    c = {"quote": {"price": 1133.8, "low": 1013.7, "high": 1211.0}, "range52": {"low": 1013.7, "high": 1211.0, "since": "2026-10-23"}}
    assert company.with_today_range(c)["range52"]["since"] == "2026-10-23"


# ---------- DD-012: a company that no longer trades ----------
def test_a_merged_company_says_so_and_its_name_is_tidy():
    assert company.tidy_name("Housing Development Finance CorporationLtd(Merged)") == "Housing Development Finance Corporation Ltd (Merged)"
    d = company.delisted_of("HDFC", "Housing Development Finance Corporation Ltd (Merged)")
    assert d == {"how": "merged", "into": "HDFC Bank", "into_symbol": "HDFCBANK", "on": "2023-07-13"}
    assert company.delisted_of("XYZ", "Xyz Ltd (Delisted)")["how"] == "delisted"
    assert company.delisted_of("TCS", "Tata Consultancy Services Ltd") is None
    facts = A.company_facts({"name": "HDFC", "symbol": "HDFC", "region": "IN", "delisted": d})
    assert "merged into HDFC Bank" in facts["status"] and "past tense" in facts["status"]


# ---------- DD-013: a merger inside a growth rate, a bank's measures, dividends in today's shares ----------
HDFCBANK = {
    "pl": {"cols": ["Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026", "TTM"],
           "rows": {"Revenue": [127753.0, 170754.0, 283649.0, 336367.0, 348615.0, 359956.0],
                    "Interest": [55744.0, 77780.0, 154139.0, 183894.0, 185491.0, 189335.0], "Financing Profit": [1.0] * 6}},
    "balance": {"cols": ["Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026", "Sep 2026"],
                "rows": {"Equity Capital": [555.0, 558.0, 760.0, 765.0, 1539.0, 1542.0],
                         "Deposits": [1559217.0, 1882663.0, 2376887.0, 2710898.0, 3099638.0, 3324146.0],
                         "Total Assets": [2123000.0, 2530432.0, 4030194.0, 4392110.0, 4907701.0, 5165842.0]}},
    "quarters": {"cols": ["Jun 2026", "Sep 2026"], "rows": {"Gross NPA %": [1.33, 1.24], "Net NPA %": [0.43, None]}},
}


def test_a_merger_year_is_found_and_said_beside_growth_across_it_but_a_bonus_is_not_one():
    m = company.merger_year(HDFCBANK, "HDFCBANK")
    assert m == {"year": "Mar 2024", "shares": 36, "assets": 59, "with": "HDFC Ltd merged into it"}       # FY26's 1:1 bonus isn't one
    note = company.merger_note(m, ["Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"])
    assert "Includes Mar 2024: HDFC Ltd merged into it" in note and "like-for-like" in note
    assert company.merger_note(m, ["Mar 2024", "Mar 2025", "Mar 2026"]) is None        # a rate from FY24 on doesn't span it


def test_a_bank_shows_its_own_measures_where_its_tables_have_them():
    got = {i["label"]: i for i in company.bank_metrics(HDFCBANK)}
    assert got["Gross NPA"]["value"] == 1.24 and got["Gross NPA"]["note"] == "Quarter to Sep 2026"
    assert got["Net NPA"]["value"] == 0.43 and got["Net NPA"]["note"] == "Quarter to Jun 2026"
    nii = (348615.0 - 185491.0) / ((4907701.0 + 4392110.0) / 2) * 100
    assert got["Net interest income / assets"]["value"] == pytest.approx(nii) and "not the bank's own NIM" in got["Net interest income / assets"]["note"]
    assert got["Deposits"]["value"] == 3324146.0 and got["Deposits"]["note"] == "as of Sep 2026"
    assert "CASA" not in got and "Capital adequacy" not in got            # not in the tables: not shown


def test_a_dividend_before_a_bonus_is_given_in_todays_shares_too():
    rows = [{"kind": "dividend", "amount": 22.0, "ex_date": "2025-06-27", "label": "Final dividend"},
            {"kind": "bonus", "factor": 2.0, "ex_date": "2025-08-27", "label": "Bonus 1:1", "short": "1:1 bonus"},
            {"kind": "dividend", "amount": 13.0, "ex_date": "2026-06-26", "label": "Final dividend"}]
    got = corp_actions.in_todays_shares("IN", rows)
    assert got[0]["now_amount"] == 11.0 and got[0]["now_note"] == "₹11 a share in today's shares, after the 1:1 bonus of 27 Aug 2025"
    assert "now_amount" not in got[2] and corp_actions.in_todays_shares("US", rows) == rows
    assert "now_amount" not in corp_actions.in_todays_shares("IN", rows, "2025-08-01")[0]     # a bonus still ahead changes nothing yet


# ---------- DD-014: a special dividend named beside the yield ----------
def test_a_stored_special_dividend_is_named_even_without_its_sub():
    assert corp_actions.is_special({"label": "Special dividend", "id": "TCS|dividend|2026-01-16|special"})
    assert corp_actions.is_special({"id": "TCS|dividend|2026-01-16|special"}) and not corp_actions.is_special({"label": "Interim dividend"})
    row = corp_actions.row("IN", "TCS", corp_actions.parse_purpose("Special Dividend - Rs 46 Per Share")[0], __import__("datetime").date(2026, 1, 16))
    assert row["sub"] == "special"
    c = {"quote": {"price": 2540.0}, "metrics": [{"title": "Valuation", "items": [{"label": "Div yield", "value": 2.5, "unit": "%"}]}]}
    divs = [{"kind": "dividend", "label": "Interim dividend", "amount": 11, "ex_date": "2026-01-16"},
            {"kind": "dividend", "label": "Special dividend", "amount": 46, "ex_date": "2026-01-16"},
            {"kind": "dividend", "label": "Dividend", "amount": 31, "ex_date": "2026-05-25"}]
    note = company.with_dividend_yield(c, divs, "2026-10-24")["metrics"][0]["items"][0]["note"]
    assert "including a ₹46 special dividend" in note
    # the AI read is told it too
    facts = A.company_facts({"name": "TCS", "symbol": "TCS", "region": "IN", "metrics": [{"title": "Valuation", "items": [
        {"label": "Div yield", "value": 3.46, "unit": "%", "note": note}]}]})
    assert "special" in facts["metrics"]["Valuation: Div yield"]


# ---------- DD-015: each ratio says its period ----------
def test_each_ratio_says_the_period_it_is_of(w):
    c = w["client"].get("/research/company/IN/RELIANCE?lean=true", headers=world.headers("pro-token")).json()
    items = {(g["title"], i["label"]): i for g in c["metrics"] for i in g["items"]}
    pe = items[("Valuation", "P/E")]
    assert pe.get("note") in ("Last 12 months",) or pe["note"].startswith("Year to")
    for label in ("ROE", "Net margin", "EBITDA margin"):
        it = items.get(("Returns and quality", label))
        if it:
            assert it["note"].startswith("Year to ") and it["period"] == it["note"], label
    us = company._of(company._item("Gross margin", 46.2, "%"), company.TTM)
    assert us["note"] == "Last 12 months" and us["period"] == "Last 12 months"
    assert company._of(company._item("ROE", None, "%"), "Year to Mar 2026")["value"] is None and "note" not in company._of(company._item("ROE", None, "%"), "x")


# ---------- DD-016: a quarter moved by one-off income, and only figures as notable figures ----------
def test_a_quarter_lifted_by_one_off_other_income_is_said_and_given_to_the_ai_read():
    scr = {"quarters": {"cols": ["Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026"],
                        "rows": {"Other Income": [15119.0, 4300.0, 3900.0, 4100.0, 4000.0],
                                 "Profit before tax": [36000.0, 24000.0, 25000.0, 26000.0, 25500.0],
                                 "Tax %": [17.0, 25.0, 25.0, 26.0, 25.0]}}}
    got = company.base_effects(scr)
    assert [e["quarter"] for e in got] == ["Jun 2025"]
    assert "other income of ₹15,119 crore against a median of ₹4,050 crore" in got[0]["text"] and "tax rate of 17%" in got[0]["text"]
    facts = A.company_facts({"name": "Reliance", "symbol": "RELIANCE", "region": "IN", "base_effects": got,
                             "quarters": {"cols": ["Jun 2026"], "sales": [1.0], "profit": [1.0], "opm": [15.0], "other_income": [4000.0], "tax_pct": [25.0]}})
    assert "Jun 2025 had other income" in facts["base_effects"] and facts["quarterly_results"]["ebitda_margin_pct"] == [15.0]


def test_notable_figures_are_lines_with_a_figure():
    assert A.figures_only(["Exposure to volatile energy markets", "Net margin 9.1% in FY26"]) == ["Net margin 9.1% in FY26"]
    kept = A.clean_company({"summary": "x", "bull": ["Exposure to volatile energy markets"], "bear": ["Debt is 0.4 times equity"], "facts": []})
    assert kept["bull"] == [] and kept["bear"] == ["Debt is 0.4 times equity"]


# ---------- DD-017: the year's change to the page's own decimals ----------
def test_the_one_year_change_is_written_with_the_pages_decimals():
    bars = [{"t": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", "c": 100.0 + i} for i in range(300)]
    whole = key_facts.price_trend(bars, -17.0, 0)
    assert {i["label"]: i["text"] for i in whole["items"]}["1-year price change"] == "-17%"
    assert {i["label"]: i["text"] for i in key_facts.price_trend(bars, -17.3)["items"]}["1-year price change"] == "-17.3%"


# ---------- DD-018: growth off a tiny base ----------
def test_growth_off_a_tiny_base_is_not_meaningful():
    assert deepdive.tiny_base([1.0, 69.0, 73.0, 50.0], 3) == 0
    # NVIDIA's profit, 4,368 to 99,000 on 26,974 of FY23 sales: a low year (16% of sales), not a tiny base
    assert deepdive.tiny_base([4368.0, 29760.0, 72880.0, 99000.0], 3, [26974.0, 60922.0, 130497.0, 180000.0]) is None
    assert deepdive.tiny_base([1.0, 69.0, 73.0, 50.0], 3, [97.0, 428.0, 469.0, 361.0]) == 0
    p = {"pl": {"cols": ["Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026"], "rows": {"Sales": [97.0, 428.0, 469.0, 361.0], "Net Profit": [1.0, 69.0, 73.0, 50.0]}}}
    n = deepdive.numbers(p)
    assert n["growth_nm"] == {"profit_cagr_3y": {"from": 1.0, "year": "Mar 2023"}}
    row = key_facts.growth({}, n)
    assert {i["label"]: i["text"] for i in row["items"]}["Net profit, 3 years"] == "n/m (from a base of ₹1 crore in Mar 2023)"
    item = company._nm(company._item("3Y CAGR", 268.4, "%±"), n["growth_nm"]["profit_cagr_3y"])
    assert item["value"] is None and item["text"] == "n/m" and "₹1 cr in Mar 2023" in item["note"]
    assert company._groups(("Profit growth", [item]))[0]["items"] == [item]          # kept, as n/m
    years = [{"year": f"Mar 202{i}", "opm": 20.0 + i} for i in range(3, 7)]
    m = key_facts.margins_and_returns({}, {"years": years}, {})
    assert m["items"][0]["label"] == "EBITDA margin, 4 years"


# ---------- DD-030, DD-031: results against estimates, checked by the filings ----------
def test_a_results_row_that_disagrees_with_the_filing_takes_the_filed_gaap_figure():
    rows = [{"period": p, "actual": a, "estimate": e, "surprise_pct": 0} for p, a, e in
            (("2025-09-30", 1.84, 1.77), ("2025-12-31", 2.84, 2.67), ("2026-03-31", 2.01, 1.95), ("2026-06-30", 1.91, 1.93))]
    got, basis = routes.filed_results(rows, {"2025-09-27": 1.84, "2025-12-27": 2.84, "2026-03-28": 2.01, "2026-06-27": 2.02}, 9)
    assert basis == "gaap" and got[-1]["actual"] == 2.02 and got[-1]["surprise_pct"] > 0 and got[-1]["fiscal"] == "Q3 FY26"
    assert sum(r["actual"] for r in got) == pytest.approx(8.71)


def test_adjusted_results_keep_their_figures_are_dated_by_the_filed_quarter_and_carry_gaap():
    rows = [{"period": p, "actual": a, "estimate": e, "surprise_pct": 1} for p, a, e in
            (("2025-12-31", 1.30, 1.25), ("2026-03-31", 1.62, 1.5), ("2026-06-30", 1.87, 1.8), ("2026-09-30", 2.22, 2.1))]
    got, basis = routes.filed_results(rows, {"2025-10-26": 1.30, "2026-01-25": 1.76, "2026-04-26": 2.39, "2026-07-26": 2.46}, 1)
    assert basis == "adjusted" and [r["actual"] for r in got] == [1.30, 1.62, 1.87, 2.22]
    assert [r["period"] for r in got] == ["2025-10-26", "2026-01-25", "2026-04-26", "2026-07-26"]
    assert [r["fiscal"] for r in got] == ["Q3 FY26", "Q4 FY26", "Q1 FY27", "Q2 FY27"] and got[-1]["gaap"] == 2.46


def test_the_us_page_takes_the_filings_results_and_says_interest_cover_is_not_meaningful(monkeypatch):
    f = {"eps_q": {"2025-12-27": 2.84, "2026-06-27": 2.02, "2026-03-28": 2.01}, "no_interest": True, "years": [{"year": "Sep 2025"}]}
    monkeypatch.setattr(routes, "public_facts", lambda r, s: f)
    c = {"symbol": "AAPL", "earnings": [{"period": "2025-12-31", "actual": 2.84, "estimate": 2.67, "surprise_pct": 6},
                                        {"period": "2026-03-31", "actual": 2.01, "estimate": 1.95, "surprise_pct": 3},
                                        {"period": "2026-06-30", "actual": 1.91, "estimate": 1.93, "surprise_pct": -1}],
         "metrics": [{"title": "Financial health", "items": [{"label": "Interest coverage", "value": 623.0, "unit": "x"}]}]}
    out = routes.with_filed_results("US", c)
    cover = out["metrics"][0]["items"][0]
    assert cover["value"] is None and cover["text"] == "n/m" and "No interest expense" in cover["note"]
    assert out["earnings_basis"] == "gaap" and out["earnings"][-1]["actual"] == 2.02
    assert routes.with_filed_results("IN", c) is c


# ---------- DD-033: one rounding for the page and the AI read ----------
def test_a_figure_is_rounded_for_the_ai_read_as_the_page_rounds_it():
    assert grounding.page_value(0.25, "%") == "0.3%"           # the page's toFixed(1); Python's round-half-even said 0.2%
    assert grounding.page_value(5.35, "%") == "5.3%" and grounding.page_value(-2.45, "%±") == "-2.5%"


# ---------- DD-050: the report card's units, voices and amount targets ----------
def test_a_crore_target_is_never_a_percentage_and_an_amount_target_is_checked():
    g = {"metric": "other", "low": 40000.0, "high": 50000.0, "period": "FY26", "what": "Deposit growth of INR 40,000–50,000 crore a quarter",
         "quote": "we should add INR 40,000 to 50,000 crore every quarter", "said_at": "2025-07-20", "source": {}}
    assert report_card.unit_of(g) == "crore"
    assert report_card.check(g, {"years": [], "quarters": []})["unit"] == "crore"
    rev = {**g, "metric": "revenue_growth", "low": 9000.0, "high": None, "what": "Revenue of Rs 9,000 crore in FY26", "quote": "we will do Rs 9,000 crore of revenue"}
    nums = {"years": [{"year": "Mar 2025", "sales": 8000.0}, {"year": "Mar 2026", "sales": 9100.0}], "quarters": [], "fye": 3}
    got = report_card.check(rev, nums, __import__("datetime").date(2026, 10, 1))
    assert got["metric"] == "revenue" and got["result"] == "met" and got["actual"] == 9100.0 and got["unit"] == "crore"
    assert report_card.unit_of({"what": "EBITDA margin of 20%", "quote": "capex of Rs 500 crore"}) == "%"


def test_a_remark_about_the_economy_is_not_the_companys_target():
    assert not report_card.ours("consumption component of GDP is about 60%")
    assert report_card.ours("our retail mix will be about 60% of loans") and report_card.ours("EBITDA margin should be about 20% in FY26")
    card = {"guidance": [{"metric": "other", "low": 60.0, "high": None, "period": "FY26", "what": "retail mix 60%",
                          "quote": "consumption component of GDP is about 60%", "said_at": "2025-07-20", "source": {"title": "t", "at": "2025-07-20", "url": "u"}}],
            "at": "2025-08-01"}
    assert report_card.view(card, {"years": [], "quarters": []})["rows"] == []


# ---------- DD-052: an EBITDA margin is called one ----------
def test_the_checklist_calls_the_yearly_margin_an_ebitda_margin():
    import inspect
    src = inspect.getsource(checklist)
    assert '"EBITDA margin holding up"' in src and '"Operating margin holding up"' not in src


# ---------- DD-070: the watchlist takes listed instruments only ----------
def test_the_watchlist_refuses_a_symbol_that_isnt_a_listed_instrument(w):
    h, c = world.headers("pro-token"), w["client"]
    bad = c.put("/research/watchlist", json={"items": [{"region": "IN", "symbol": "ZZZZQQ"}]}, headers=h)
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "unknown_symbol"
    assert c.get("/research/watchlist", headers=h).json()["items"] == []
    ok = c.put("/research/watchlist", json={"items": [{"region": "IN", "symbol": "RELIANCE"}, {"region": "IN", "symbol": "TINYCO"}]}, headers=h)
    assert ok.status_code == 200 and [i["symbol"] for i in ok.json()["items"]] == ["RELIANCE", "TINYCO"]


# ---------- DD-071: At a glance's Stage is the company page's ----------
def test_at_a_glances_stage_is_worked_out_as_the_company_page_does(monkeypatch):
    closes = [100.0 + i * 0.5 for i in range(260)]
    bars = [{"t": f"2025-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": c, "h": c, "l": c, "c": c, "v": 1} for i, c in enumerate(closes)]
    monkeypatch.setattr(main, "price_trend", lambda s, m="IN": None)              # the broker offline: no scans' candles
    monkeypatch.setattr(main.research_hub, "chart", lambda r, s, rng="1y", *a, **k: {"candles": bars})
    got = main.glance_trend("TCS", "IN")
    page = {i["label"]: i["text"] for i in key_facts.price_trend(bars)["items"]}["Stage (150-day average)"]
    assert got["stage"] == 2 and key_facts.STAGE[got["stage"]] == page and got["signal"] in ("fresh", "st_s2", "stage2")
