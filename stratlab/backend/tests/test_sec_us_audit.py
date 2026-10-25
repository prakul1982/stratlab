"""Fixes from the US whole-market audit sheet (October 2026), on constructed SEC company-facts and submissions payloads:
why a company has no results to show, results in another currency, revenue, profit, capex and debt read from what the
annual report does and doesn't tag, REITs and business development companies, and fair price comparisons."""
from datetime import datetime, timezone

import httpx
import pytest
import time_machine

from app import audit, checklist, deepdive, industry
from app.intel import sec
from app.intel.net import SourceError


def _f(v, end="2024-12-31", start="2024-01-01", form="10-K", filed="2025-02-20", accn="0001-25-000001"):
    return {"start": start, "end": end, "val": v, "form": form, "filed": filed, "accn": accn}


def _i(v, end="2024-12-31", form="10-K", filed="2025-02-20", accn="0001-25-000001"):
    return {"end": end, "val": v, "form": form, "filed": filed, "accn": accn}


def _yr(y, v, accn=None):
    return _f(v, f"{y}-12-31", f"{y}-01-01", filed=f"{y + 1}-02-20", accn=accn or f"0001-{y + 1}-1")


def _subs(forms, sic="", **kw):
    return {"cik": "1", "name": "Co", "sic": sic, "sicDescription": kw.pop("desc", ""),
            "filings": {"recent": {"form": forms, "filingDate": ["2026-03-01"] * len(forms),
                                   "accessionNumber": [f"0001-26-{i:06d}" for i in range(len(forms))],
                                   "primaryDocument": ["d.htm"] * len(forms), "items": [""] * len(forms)}}, **kw}


# ---------- why there are no results ----------
@pytest.mark.parametrize("subs,symbol,key", [
    (_subs(["N-CSR", "N-CEN", "NPORT-P"]), "AIO", "fund"),                         # a closed-end fund
    (_subs(["6-K", "F-6"]), "ADOOY", "home"),                                     # an ADR of a company filing at home
    (_subs([]), "AZZTF", "home"),                                                 # foreign ordinary shares over the counter
    (_subs(["D"], foreign=True), "AYA", "home"),                                  # based abroad, files nothing here
    (_subs(["4", "SC 13G"], sic="6022"), "PFBC", "bank"),                         # a bank filing with its bank regulator
    (_subs(["1-K", "1-SA", "253G2"]), "AVSBS", "reg_a"),                          # Regulation A
    (_subs(["10-K", "10-Q"]), "SJT", "no_xbrl"),                                  # an annual report, no data filed
    (_subs(["15-12G", "8-K"]), "ALMP", "stopped"),                                # deregistered
    (_subs(["10-12B", "S-1"]), "AXM", "new"),                                     # a spin-off registered recently
    (_subs(["D"]), "ALBC", "none"),
])
def test_no_results_says_why_in_plain_words(subs, symbol, key):
    why = sec.no_results(subs, None, symbol)
    assert why == sec.NO_RESULTS[key]
    assert any(x in why for x in audit.NOT_COVERED)                     # a fact about the company, never a fault
    assert "EDGAR" not in why and "nothing for that" not in why


def test_annual_figures_filed_but_unread_is_our_gap_not_a_fact():
    facts = {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [_i(100)]}}}}      # an income statement line, tagged a way we can't read
    why = sec.no_results(_subs(["10-K"]), facts, "XYZ")
    assert why == sec.UNREAD and not any(x in why for x in audit.NOT_COVERED)
    q = {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [_f(-5, "2025-03-31", "2025-01-01", "10-Q")]}}}}
    assert sec.no_results(_subs(["10-Q"]), q, "NEWCO") == sec.NO_RESULTS["quarters"]


def _transport(subs, facts_status=404, facts=None, calls=None):
    def handler(r: httpx.Request):
        if calls is not None:
            calls.append(r.url.path)
        if r.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": 7, "ticker": "AIO", "title": "Virtus Fund"},
                                             "1": {"cik_str": 8, "ticker": "BRK-B", "title": "Berkshire"},
                                             "2": {"cik_str": 9, "ticker": "BAC-PL", "title": "Bank of America"}})
        if r.url.path.startswith("/submissions/CIK"):
            return httpx.Response(200, json=subs)
        if "companyfacts" in r.url.path:
            return httpx.Response(facts_status, json=facts or {})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_company_page_explains_a_fund_instead_of_a_raw_not_found():
    calls = []
    s = sec.SEC(transport=_transport(_subs(["N-CSR", "N-CEN"]), calls=calls))
    for _ in range(2):
        with pytest.raises(SourceError) as e:
            s.company("AIO")
        assert str(e.value) == sec.NO_RESULTS["fund"] and not e.value.busy
    assert sum("companyfacts" in c for c in calls) == 1                 # the reason is remembered, not asked again
    assert s.name == "The SEC"


def test_tickers_with_dots_slashes_and_preferred_series_find_the_filer():
    s = sec.SEC(transport=_transport(_subs([])))
    assert s.cik("BRK.B") == s.cik("BRK/B") == s.cik("brk-b") == 8
    assert s.cik("BAC.PRL") == s.cik("BAC-PL") == 9


@time_machine.travel(datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc))      # its filings are from 2025: inside the two years read
def test_a_heavy_filer_reads_the_next_page_of_its_filing_list():
    recent = _subs(["424B2"] * 3)["filings"]["recent"]
    subs = {"cik": "1", "name": "Big Bank", "sic": "6021", "filings": {"recent": recent, "files": [{"name": "CIK0000000001-submissions-001.json"}]}}
    older = {"form": ["10-Q", "10-K"], "filingDate": ["2025-11-01", "2025-02-20"], "accessionNumber": ["a-1", "a-2"],
             "primaryDocument": ["q.htm", "k.htm"]}

    def handler(r):
        if r.url.path.endswith("-001.json"):
            return httpx.Response(200, json=older)
        return httpx.Response(200, json=subs)
    got = sec.SEC(transport=httpx.MockTransport(handler)).submissions(1)
    assert got["filings"]["recent"]["form"][-2:] == ["10-Q", "10-K"] and len(got["filings"]["recent"]["items"]) == 5
    kinds = {d["kind"] for d in sec.documents(got)}
    assert {"annual_report", "quarterly_report"} <= kinds


# ---------- another currency ----------
def _cad():
    years = range(2020, 2025)
    return {"facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2025-02-01", "val": 100_000_000}]}}},
        "ifrs-full": {
            "Revenue": {"units": {"CAD": [_yr(y, 1000e6 + 100e6 * i) for i, y in enumerate(years)]}},
            "ProfitLoss": {"units": {"CAD": [_yr(y, 100e6 + 10e6 * i) for i, y in enumerate(years)]}},
            "ProfitLossFromOperatingActivities": {"units": {"CAD": [_yr(y, 150e6) for y in years]}},
            "DepreciationAndAmortisationExpense": {"units": {"CAD": [_yr(y, 50e6) for y in years]}},
            "Equity": {"units": {"CAD": [_i(800e6, f"{y}-12-31", accn=f"0001-{y + 1}-1") for y in years]}},
            "Borrowings": {"units": {"CAD": [_i(200e6, f"{y}-12-31", accn=f"0001-{y + 1}-1") for y in years]}},
            "BasicEarningsLossPerShare": {"units": {"CAD/shares": [_yr(y, 1.4) for y in years]}},
        }}}


def test_a_canadian_filer_is_shown_in_canadian_dollars_with_price_ratios_in_dollars():
    p = sec.build(_cad(), _subs(["40-F"], desc="Gold Ores", sic="1040"))
    assert p["currency"] == "CAD" and p["unit"] == "CAD million" and p["currency_name"] == "Canadian dollars"
    assert p["pl"]["rows"]["Sales"][-1] == 1400.0 and "EPS in CAD" in p["pl"]["rows"]
    p = sec.with_fx(p, lambda cur: 0.73 if cur == "CAD" else None)
    assert p["fx"]["rate"] == 0.73 and "1 CAD = 0.7300 USD" in p["currency_note"] and "CAD million" in p["currency_note"]
    r = sec.ratios(p, 20.0)                                       # $20 a share, 100m shares: $2,000m
    assert r["Market Cap"] == 2000.0
    assert r["Stock P/E"] == round(2000 / (140 * 0.73), 1)        # profit turned into dollars at today's rate
    assert r["Book Value"] == round(800 * 0.73 / 100, 2)
    assert r["ROE"] == round(140 / 800 * 100, 1)                  # a ratio within the filings: no conversion
    nums = deepdive.numbers(p)
    assert p["currency_note"] in nums["notes"] and nums["unit"] == "CAD million"
    assert deepdive.money(1500, nums["unit"]) == "CAD 1.50 bn"
    # EV/EBITDA for a miner: the dollar market value set against reported debt and EBITDA in CAD
    v = industry.valuation(p, {"market_cap_cr": 2000.0}, "cyclical", "metal")
    assert v["value"] == round((2000 / 0.73 + 200) / 200, 1)


def test_the_pe_fallback_converts_a_foreign_filers_market_value():
    p = sec.with_fx(sec.build(_cad(), _subs(["40-F"])), lambda cur: 0.73)
    v = industry.valuation(p, {"market_cap_cr": 2000.0}, "general", "general")       # no P/E given: worked out
    assert v["value"] == round(2000 / 0.73 / 140, 1)


def test_without_todays_rate_the_price_ratios_are_left_out_not_mixed():
    p = sec.with_fx(sec.build(_cad(), _subs(["40-F"])), lambda cur: (_ for _ in ()).throw(SourceError("x", "down", busy=True)))
    assert "fx" not in p and "couldn't be read" in p["currency_note"]
    r = sec.ratios(p, 20.0)
    assert r["Market Cap"] == 2000.0 and "Stock P/E" not in r and "Book Value" not in r and "Dividend Yield" not in r
    assert industry.valuation(p, {"market_cap_cr": 2000.0}, "cyclical", "metal")["value"] is None


def test_audit_compares_a_foreign_filers_pe_in_dollars():
    p = sec.with_fx(sec.build(_cad(), _subs(["40-F"])), lambda cur: 0.73)
    p["pl"] = {"cols": ["Dec 2024", "TTM"], "rows": {"Net Profit": [140.0, 140.0], "Sales": [1400.0, 1400.0]}}
    snap = {"pe": round(2000 / (140 * 0.73), 1), "market_cap_cr": 2000.0}
    assert not [i for i in audit.check_numbers(p, {"years": []}, snap) if i["area"] == "Valuation"]


# ---------- revenue, profit, capex and debt from what the report tags ----------
def test_revenue_from_gross_profit_and_cost_and_ebit_from_pretax_profit():
    facts = {"us-gaap": {"GrossProfit": {"units": {"USD": [_f(40)]}}, "CostOfRevenue": {"units": {"USD": [_f(60)]}}}}
    assert sec.revenue(facts, "annual") == {"2024-12-31": 100.0}
    facts = {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [_f(1000e6)]}}, "NetIncomeLoss": {"units": {"USD": [_f(70e6)]}},
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": {"units": {"USD": [_f(90e6)]}},
        "InterestExpense": {"units": {"USD": [_f(30e6)]}},
        "DepreciationDepletionAndAmortization": {"units": {"USD": [_f(80e6)]}}}}}
    p = sec.build(facts, _subs(["10-K"], sic="3334"))            # no operating profit line (an aluminium maker)
    assert p["pl"]["rows"]["Operating Profit"] == [200.0]          # EBITDA: pre-tax 90 + interest 30 + D&A 80


def test_a_year_whose_report_has_no_revenue_line_is_a_fact_not_a_gap():
    rev = [_yr(2020, 5e6), _yr(2021, 8e6)]                          # collaboration revenue for two years, then none
    ni = [_yr(y, -50e6) for y in range(2020, 2025)]
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "NetIncomeLoss": {"units": {"USD": ni}},
                                   "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [_yr(y, -40e6) for y in range(2020, 2025)]}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert p["no_revenue"] == ["Dec 2022", "Dec 2023", "Dec 2024"]
    nums = deepdive.numbers(p)
    found = audit.check_numbers(p, nums, {})
    assert not [i for i in found if i["level"] == "gap" and i["area"] == "Numbers"]
    assert any(i["level"] == "fact" and i["detail"].startswith("No revenue in Dec 2022") for i in found)
    # the checklist's sales growth over those years is explained by the same fact
    view = {"numbers": nums, "checklist": {"checks": [{"label": "Sales growth, 3 years", "state": "na"},
                                                      {"label": "EBITDA margin holding up", "state": "na"},
                                                      {"label": "Return on capital employed", "state": "na"}]},
            "valuation": {"value": 1}}
    assert not [i for i in audit.check_view(view) if i["area"] == "Checklist" and i["level"] == "gap"]
    # capex: the cash flow statements tag no purchases of plant and equipment at all, so it was nil
    assert p["cashflow"]["rows"]["Capex"][-3:] == [0.0, 0.0, 0.0]


def test_a_missing_revenue_figure_in_a_report_that_tags_revenue_stays_a_gap():
    rev = [_yr(2020, 5e6), _yr(2021, 8e6), _yr(2023, 9e6)]
    ni = [_yr(y, -50e6) for y in range(2020, 2025)]
    other = [_yr(2022, 4e6)]                                         # a revenue line that year under a name we don't read
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "NetIncomeLoss": {"units": {"USD": ni}},
                                   "RevenueFromWidgetSales": {"units": {"USD": other}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert "Dec 2022" not in p["no_revenue"] and "Dec 2022" not in p["sales_untagged"]       # tagged, not read: ours to look into
    found = audit.check_numbers(p, deepdive.numbers(p), {})
    assert any(i["level"] == "gap" and "Dec 2022" in i["detail"] for i in found)


def test_the_oldest_year_from_a_note_is_left_out():
    rev = [_yr(y, 100e6) for y in range(2021, 2025)]
    ni = [_yr(y, 10e6) for y in range(2022, 2025)]                  # the income statement goes back three years
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "NetIncomeLoss": {"units": {"USD": ni}}}}}
    assert sec.build(facts, _subs(["10-K"]))["pl"]["cols"] == ["Dec 2022", "Dec 2023", "Dec 2024"]


def test_no_borrowings_on_the_balance_sheet_is_no_debt():
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [_f(100e6)]}}, "NetIncomeLoss": {"units": {"USD": [_f(10e6)]}},
                                   "StockholdersEquity": {"units": {"USD": [_i(50e6)]}}}}}
    assert sec.build(facts, _subs(["10-K"]))["balance"]["rows"]["Borrowings"] == [0.0]
    facts["facts"]["us-gaap"]["NotesPayable"] = {"units": {"USD": [_i(5e6)]}}     # debt tagged another way: unknown
    assert sec.build(facts, _subs(["10-K"]))["balance"]["rows"]["Borrowings"] == [None]


def test_no_capex_and_no_plant_is_a_fact():
    p = {"region": "US", "balance": {"cols": ["a", "b", "c"], "rows": {"Fixed Assets": [None, None, None]}}}
    nums = {"years": [{"year": y, "sales": 1, "profit": 1, "capex": None} for y in ("a", "b", "c", "d", "e")]}
    assert audit._issue("fact", "Capex", audit.NO_PLANT) in audit.check_numbers(p, nums, {})
    p["balance"]["rows"]["Fixed Assets"] = [5.0, 6.0, 7.0]
    assert any(i["level"] == "gap" and i["area"] == "Capex" for i in audit.check_numbers(p, nums, {}))


# ---------- REITs and business development companies ----------
def _reit_facts():
    return {"facts": {"us-gaap": {
        "Revenues": {"units": {"USD": [_yr(y, 100e6) for y in range(2020, 2025)]}},
        "NetIncomeLoss": {"units": {"USD": [_yr(y, 60e6) for y in range(2020, 2025)]}},
        "OperatingIncomeLoss": {"units": {"USD": [_yr(y, 90e6) for y in range(2020, 2025)]}},       # gains on sales in it
        "DepreciationDepletionAndAmortization": {"units": {"USD": [_yr(y, 40e6) for y in range(2020, 2025)]}}}}}


def test_a_reit_has_no_operating_margin_to_judge():
    p = sec.build(_reit_facts(), _subs(["10-K"], sic="6798", desc="Real Estate Investment Trusts"))
    assert p["kind"] == "reit" and all(v is None for v in p["pl"]["rows"]["OPM %"])
    assert p["pl"]["rows"]["Operating Profit"][-1] == 130.0              # still shown, not turned into a margin
    nums = deepdive.numbers(p)
    assert p["margin_note"] in nums["notes"]
    assert not [i for i in audit.check_numbers(p, nums, {}, "reit") if "above 100%" in i["detail"]]
    cl = checklist.evaluate(p, nums)
    assert cl["industry"]["group"] == "reit" and not [c for c in cl["checks"] if c["label"] == "EBITDA margin holding up"]


def test_a_bdc_is_classified_from_its_filings_and_valued_on_book():
    subs = _subs(["10-K", "10-Q", "N-2", "497"])                       # no SEC industry code, like ARCC
    p = sec.build(_reit_facts(), subs)
    assert p["kind"] == "bdc" and p["industry_path"] == ["Finance", "Business Development Company"] and not p["bank"]
    nums = deepdive.numbers(p)
    cl = checklist.evaluate(p, nums)
    assert cl["industry"]["group"] == "bdc" and cl["industry"]["path"]
    assert any(c["label"] == "Return on equity" for c in cl["checks"])
    assert not [c for c in cl["checks"] if c["label"] in ("EBITDA margin holding up", "Free cash flow, 3 years", "Total debt / equity")]
    v = industry.valuation(p, {"pb": 0.95}, "bdc", "general")
    assert v["short"] == "P/B" and v["value"] == 0.95 and "net asset value" in v["why"]
    view = {"checklist": cl, "valuation": v, "numbers": nums}
    assert not [i for i in audit.check_view(view) if i["area"] == "Industry"]


# ---------- documents, prices and stored findings ----------
def test_quarterly_reports_without_an_annual_one_is_a_fact():
    view = {"region": "US", "documents": [{"kind": "quarterly_report", "form": "10-Q"}], "checklist": {"checks": []},
            "valuation": {"value": 1}}
    assert [i for i in audit.check_view(view) if i["area"] == "Documents"] == [audit._issue("fact", "Documents", audit.LATE_ANNUAL)]
    old = audit._issue("gap", "Documents", "No annual report (10-K, 20-F or 40-F) filed in the last two years")
    assert audit.restate(old, us=True) == audit._issue("fact", "Documents", audit.LATE_ANNUAL)


def test_a_close_inside_the_pages_day_range_is_the_same_session():
    # a fast-moving penny stock: our close read a few minutes before the page's quote, inside its day's range
    assert audit.check_prices({"price": 0.07}, {"price": 0.05}, None, None, (0.07, 0.14, 0.09, 0.04)) == []
    found = audit.check_prices({"price": 0.07}, {"price": 0.02}, None, None, (0.07, 0.14, 0.09, 0.04))
    assert found and found[0]["level"] == "mismatch"


def test_us_trailing_revenue_is_in_dollars_and_small_rounding_is_not_a_mismatch():
    p = {"region": "US", "unit": "$ million", "pl": {"cols": ["Dec 2024", "TTM"], "rows": {"Sales": [0.1, 0.04]}}}
    found = audit.check_numbers(p, {"years": [], "quarters": [{"sales": 0.0}] * 4}, {})
    assert not [i for i in found if i["level"] == "mismatch"]                                     # ACON: 0 vs 0
    assert audit.restate(audit._issue("mismatch", "Numbers", "Trailing revenue 0 cr vs last four quarters 0 cr"), us=True) is None


def test_old_raw_not_found_rows_read_plainly():
    got = audit.restate(audit._issue("fact", "Company page", "SEC EDGAR has nothing for that."), us=True)
    assert got["level"] == "fact" and "EDGAR" not in got["detail"] and "nothing for that" not in got["detail"]


def test_us_deep_dive_states_why_there_are_no_daily_prices(monkeypatch):
    from app import main
    from tests import world as W
    w = W.build(monkeypatch)
    try:
        trend, why = main.price_status("NOPEX", "US")
        assert trend is None and why == "untraded"
        base = main.deep_base_us("AAPL")
        assert "trend_why" in base and base["quote"] and "high" in base["quote"]
    finally:
        w["close"]()


def test_nil_capex_and_debt_need_the_rest_of_the_report_to_agree():
    years = range(2022, 2025)
    base = {"Revenues": {"units": {"USD": [_yr(y, 100e6) for y in years]}},
            "NetIncomeLoss": {"units": {"USD": [_yr(y, 10e6) for y in years]}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [_yr(y, 12e6) for y in years]}},
            "StockholdersEquity": {"units": {"USD": [_i(50e6, f"{y}-12-31", accn=f"0001-{y + 1}-1") for y in years]}}}
    # plant growing every year: something was bought, so capex is unknown rather than nil
    plant = [_i(10e6 * (y - 2020), f"{y}-12-31", accn=f"0001-{y + 1}-1") for y in years]
    p = sec.build({"facts": {"us-gaap": {**base, "PropertyPlantAndEquipmentNet": {"units": {"USD": plant}}}}}, _subs(["10-K"]))
    assert p["cashflow"]["rows"]["Capex"] == [None, None, None]        # the first year too: no year before to compare
    # interest paid in the same report: there is debt somewhere, tagged in a way not read
    owes = {**base, "InterestExpense": {"units": {"USD": [_yr(y, 1e6) for y in years]}}}
    assert sec.build({"facts": {"us-gaap": owes}}, _subs(["10-K"]))["balance"]["rows"]["Borrowings"] == [None, None, None]
    assert sec.build({"facts": {"us-gaap": base}}, _subs(["10-K"]))["balance"]["rows"]["Borrowings"] == [0.0, 0.0, 0.0]


def test_a_report_with_cost_of_sales_has_a_revenue_line():
    ni = [_yr(y, 5e6) for y in range(2022, 2025)]
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [_yr(2022, 50e6)]}}, "NetIncomeLoss": {"units": {"USD": ni}},
                                   "CostOfRevenue": {"units": {"USD": [_yr(2023, 30e6)]}}}}}      # revenue tagged a way not read
    assert "Dec 2023" not in sec.build(facts, _subs(["10-K"]))["no_revenue"]


# ---------- MS1: the readers' root causes (companies the whole-market audit left as gaps on 25 Oct) ----------
def test_annual_reports_with_no_income_statement_in_the_data_are_a_fact(MS1=True):
    """MS1-013: AIB, DAVI, MMTRS and WBQNL file annual reports whose data holds notes and a cash flow but no income
    statement line at all: the results aren't in the data, which the page says, not an unread figure (error before)."""
    facts = {"us-gaap": {"ManagementFeeExpense": {"units": {"USD": [_f(284000)]}}, "Assets": {"units": {"USD": [_i(100)]}}}}
    why = sec.no_results(_subs(["10-K"]), facts, "AIB")
    assert why == sec.NO_RESULTS["untagged"] and any(x in why for x in audit.NOT_COVERED)
    assert "XBRL" in why and "EDGAR" not in why


def test_a_loss_before_tax_is_the_profit_when_nothing_else_is_tagged():
    """MS1-013: Micromem's 20-F tags ProfitLossBeforeTax and no net profit; a loss with no tax is that loss."""
    pre = [_yr(y, v) for y, v in ((2023, -3.0e6), (2024, -0.7e6))]
    rev = [_yr(2023, 0.0), _yr(2024, 0.0)]
    facts = {"facts": {"ifrs-full": {"ProfitLossBeforeTax": {"units": {"USD": pre}}, "Revenue": {"units": {"USD": rev}}}}}
    p = sec.build(facts, _subs(["20-F"]))
    assert p["pl"]["rows"]["Net Profit"][-2:] == [-3.0, -0.7]


def test_a_concept_in_both_taxonomies_reads_both(MS1=True):
    """MS1-010: Alcon filed US GAAP up to 2010 and IFRS from 2017: ProfitLoss is in both, and only the first was read, so
    2017 to 2022 had sales and no profit."""
    old = [_yr(2009, 2.0e9), _yr(2010, 2.2e9)]
    new = [_yr(2021, 3.7e8), _yr(2022, 3.3e8), _yr(2023, 9.7e8)]
    rev = [_yr(y, 7e9) for y in (2009, 2010, 2021, 2022, 2023)]
    facts = {"facts": {"us-gaap": {"ProfitLoss": {"units": {"USD": old}}, "Revenues": {"units": {"USD": rev}}},
                       "ifrs-full": {"ProfitLoss": {"units": {"USD": new}}}}}
    p = sec.build(facts, _subs(["20-F"]))
    assert p["pl"]["rows"]["Net Profit"] == [2000.0, 2200.0, 370.0, 330.0, 970.0]
    assert p["profit_untagged"] == []


def test_a_later_report_filing_a_figure_a_thousand_times_too_big_does_not_win():
    """MS1-009: Coherent's 2025 annual report tags 2023 depreciation 681,687,000,000 where the others say 681,687,000: an
    operating margin of 13,000%. The value most filings agree on stands; a tie goes to the concept's usual scale."""
    def dep(y, v, filed):
        return {**_yr(y, v), "filed": filed, "accn": f"0001-{filed}"}
    rows = [dep(2022, 600e6, "2023-08-18"), dep(2023, 681687000, "2023-08-18"), dep(2023, 681687000, "2024-08-16"),
            dep(2023, 681687000000, "2025-08-15"), dep(2023, 681687000, "2025-12-16"), dep(2024, 560e6, "2025-08-15")]
    facts = {"us-gaap": {"DepreciationAndAmortization": {"units": {"USD": rows}}}}
    got = sec.drop_scale_slips(facts)["us-gaap"]["DepreciationAndAmortization"]["units"]["USD"]
    assert sorted(f["val"] for f in got if f["end"] == "2023-12-31") == [681687000] * 3
    tie = [dep(2021, 150e3, "2022-03-01"), dep(2022, 188000, "2023-03-01"), dep(2022, 188000000, "2024-03-01"), dep(2023, 160e3, "2024-03-01")]
    got = sec.drop_scale_slips({"us-gaap": {"DepreciationAndAmortization": {"units": {"USD": tie}}}})["us-gaap"]["DepreciationAndAmortization"]["units"]["USD"]
    assert [f["val"] for f in got if f["end"] == "2022-12-31"] == [188000]                  # the scale of its other years
    shares = [{**_yr(2023, 4401), "filed": "2026-04-30"}, {**_yr(2023, 158436534), "filed": "2024-04-30"}]
    same = sec.drop_scale_slips({"us-gaap": {"WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": shares}}}})
    assert len(same["us-gaap"]["WeightedAverageNumberOfDilutedSharesOutstanding"]["units"]["shares"]) == 2     # a reverse split restates counts


def test_depreciation_larger_than_the_whole_business_is_not_added_back():
    """MS1-009: InspireMD's depreciation of $188 million beside $5 million of sales (a unit slip in every report) gave an
    operating margin of 3,000%; with no usable depreciation there is no EBITDA, not a wrong one."""
    rev = [_yr(y, 5e6) for y in (2022, 2023, 2024)]
    op = [_yr(y, -19e6) for y in (2022, 2023, 2024)]
    dep = [_yr(y, 188e6) for y in (2022, 2023, 2024)]
    ni = [_yr(y, -18e6) for y in (2022, 2023, 2024)]
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "OperatingIncomeLoss": {"units": {"USD": op}},
                                   "DepreciationAndAmortization": {"units": {"USD": dep}}, "NetIncomeLoss": {"units": {"USD": ni}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert p["pl"]["rows"]["OPM %"] == [None, None, None] and "margin_left_out" not in p


def test_an_operating_margin_above_100_percent_is_left_out_and_said_so():
    """MS1-009: a gain inside operating profit (Anterix 2026: $6.5 million of sales, $94 million of operating profit) or
    nil or negative sales is no margin; the page leaves it out and says so, as the Indian pages do."""
    rev = [_yr(2024, 6.0e6), _yr(2025, 6.5e6), _yr(2026, -0.07e6)]
    op = [_yr(2024, -11e6), _yr(2025, 94.4e6), _yr(2026, -10e6)]
    dep = [_yr(y, 0.4e6) for y in (2024, 2025, 2026)]
    ni = [_yr(y, v) for y, v in ((2024, -11e6), (2025, 90.6e6), (2026, -10e6))]
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "OperatingIncomeLoss": {"units": {"USD": op}},
                                   "DepreciationAndAmortization": {"units": {"USD": dep}}, "NetIncomeLoss": {"units": {"USD": ni}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert p["pl"]["rows"]["OPM %"][0] is not None and p["pl"]["rows"]["OPM %"][1:] == [None, None]
    assert p["margin_left_out"] == ["Dec 2025", "Dec 2026"] and "Dec 2025" in p["margin_note"]
    nums = deepdive.numbers(p)
    assert nums["margin_left_out"] == p["margin_left_out"] and p["margin_note"] in nums["notes"]
    out = audit.check_numbers(p, nums, {})
    assert [i["level"] for i in out if "margin" in i["detail"]] == ["fact"] and "gap" not in [i["level"] for i in out]


def test_a_loss_year_with_no_revenue_figure_of_any_kind_is_a_year_without_sales():
    """MS1-011: a development-stage company's report tags a gross profit of nil or a total since it began; no revenue-like
    figure above nil for the year is no sales that year, not a figure missed."""
    rev = [_yr(2022, 4e6)]
    ni = [_yr(y, -2e6) for y in (2022, 2023, 2024)]
    gp = [_f(0, "2023-12-31", "2023-01-01", filed="2024-02-20", accn="0001-2024-9"), _f(0.0, "2024-12-31", "2024-01-01", filed="2025-02-20", accn="0001-2025-9")]
    since = [_f(14059, "2024-12-31", "2012-05-11", filed="2025-02-20", accn="0001-2025-9")]          # a total since inception: not a year
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev + since}}, "NetIncomeLoss": {"units": {"USD": ni}}, "GrossProfit": {"units": {"USD": gp}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert p["no_revenue"] == ["Dec 2023", "Dec 2024"] and p["sales_untagged"] == []


def test_a_sales_line_the_company_labels_itself_is_a_fact_about_the_data():
    """MS1-011: Intrepid Potash's sales for 2018 to 2022 aren't tagged with any standard label, while its operating profit
    is: not a figure we missed, and the page says the data has no sales for those years."""
    ni = [_yr(y, 5e6) for y in (2022, 2023, 2024)]
    op = [_yr(y, 8e6) for y in (2022, 2023, 2024)]
    rev = [_yr(2022, 240e6), _yr(2024, 255e6)]
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "NetIncomeLoss": {"units": {"USD": ni}}, "OperatingIncomeLoss": {"units": {"USD": op}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert p["sales_untagged"] == ["Dec 2023"] and p["no_revenue"] == []
    nums = deepdive.numbers(p)
    out = audit.check_numbers(p, nums, {})
    assert [i["level"] for i in out if i["detail"].startswith("Sales for Dec 2023")] == ["fact"]
    assert "gap" not in [i["level"] for i in out]


def test_no_capex_line_in_the_cash_flow_statements_is_a_fact():
    """MS1-012: a company whose last three cash flow statements show no purchase of plant and equipment spent none."""
    ni = [_yr(y, -1e6) for y in (2022, 2023, 2024)]
    rev = [_yr(y, 1e6) for y in (2022, 2023, 2024)]
    cfo = [_yr(y, -0.5e6) for y in (2022, 2023, 2024)]
    ppe = [_i(4e6, "2024-12-31", filed="2025-02-20", accn="0001-2025-1")]       # plant on the books only in the last year (an acquisition)
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "NetIncomeLoss": {"units": {"USD": ni}},
                                   "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": cfo}},
                                   "PropertyPlantAndEquipmentNet": {"units": {"USD": ppe}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert p["capex_untagged"] is True
    nums = deepdive.numbers(p)
    got = [(i["level"], i["area"]) for i in audit.check_numbers(p, nums, {}) if i["area"] == "Capex"]
    assert got == [("fact", "Capex")]


def test_royalty_clinic_and_data_service_revenue_are_read_but_equity_method_and_discontinued_revenue_are_not():
    """MS1-011: 14 companies whose only revenue line is a royalty, a clinic's patient revenue or a data service were left with
    sales "missing"; the revenue of an equity-method investee or of a discontinued business is not the company's own."""
    ni = [_yr(y, -2e6) for y in (2022, 2023, 2024)]
    royalty = [_yr(y, 8e6) for y in (2022, 2023, 2024)]
    investee = [_yr(y, 40e6) for y in (2022, 2023, 2024)]
    facts = {"facts": {"us-gaap": {"RoyaltyRevenue": {"units": {"USD": royalty}}, "NetIncomeLoss": {"units": {"USD": ni}},
                                   "EquityMethodInvestmentSummarizedFinancialInformationRevenue": {"units": {"USD": investee}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert p["pl"]["rows"]["Sales"] == [8.0, 8.0, 8.0] and p["sales_untagged"] == []
    only = {"facts": {"us-gaap": {"DisposalGroupIncludingDiscontinuedOperationRevenue": {"units": {"USD": investee}},
                                  "NetIncomeLoss": {"units": {"USD": ni}}, "OperatingIncomeLoss": {"units": {"USD": ni}}}}}
    p = sec.build(only, _subs(["10-K"]))
    assert p["pl"]["rows"]["Sales"] == [None] * 3 and p["no_revenue"] == ["Dec 2022", "Dec 2023", "Dec 2024"]       # a loss and no sales of its own
