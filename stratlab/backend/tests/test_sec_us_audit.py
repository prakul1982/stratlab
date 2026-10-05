"""Fixes from the US whole-market audit sheet (October 2026), on constructed SEC company-facts and submissions payloads:
why a company has no results to show, results in another currency, revenue, profit, capex and debt read from what the
annual report does and doesn't tag, REITs and business development companies, and fair price comparisons."""
import httpx
import pytest

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
    facts = {"us-gaap": {"Assets": {"units": {"USD": [_i(100)]}}}}
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
                                                      {"label": "Operating margin holding up", "state": "na"},
                                                      {"label": "Return on capital employed", "state": "na"}]},
            "valuation": {"value": 1}}
    assert not [i for i in audit.check_view(view) if i["area"] == "Checklist" and i["level"] == "gap"]
    # capex: the cash flow statements tag no purchases of plant and equipment at all, so it was nil
    assert p["cashflow"]["rows"]["Capex"][-3:] == [0.0, 0.0, 0.0]


def test_a_missing_revenue_figure_in_a_report_that_tags_revenue_stays_a_gap():
    rev = [_yr(2020, 5e6), _yr(2021, 8e6), _f(9e6, "2023-12-31", "2023-01-01", accn="0001-2023-1")]
    ni = [_yr(y, -50e6) for y in range(2020, 2025)]
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": rev}}, "NetIncomeLoss": {"units": {"USD": ni}}}}}
    p = sec.build(facts, _subs(["10-K"]))
    assert "Dec 2022" not in p["no_revenue"]                         # its report (filed 2023) tags revenue: not read
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
    assert cl["industry"]["group"] == "reit" and not [c for c in cl["checks"] if c["label"] == "Operating margin holding up"]


def test_a_bdc_is_classified_from_its_filings_and_valued_on_book():
    subs = _subs(["10-K", "10-Q", "N-2", "497"])                       # no SEC industry code, like ARCC
    p = sec.build(_reit_facts(), subs)
    assert p["kind"] == "bdc" and p["industry_path"] == ["Finance", "Business Development Company"] and not p["bank"]
    nums = deepdive.numbers(p)
    cl = checklist.evaluate(p, nums)
    assert cl["industry"]["group"] == "bdc" and cl["industry"]["path"]
    assert any(c["label"] == "Return on equity" for c in cl["checks"])
    assert not [c for c in cl["checks"] if c["label"] in ("Operating margin holding up", "Free cash flow, 3 years", "Debt to equity")]
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
    assert p["cashflow"]["rows"]["Capex"] == [0.0, None, None]
    # interest paid in the same report: there is debt somewhere, tagged in a way not read
    owes = {**base, "InterestExpense": {"units": {"USD": [_yr(y, 1e6) for y in years]}}}
    assert sec.build({"facts": {"us-gaap": owes}}, _subs(["10-K"]))["balance"]["rows"]["Borrowings"] == [None, None, None]
    assert sec.build({"facts": {"us-gaap": base}}, _subs(["10-K"]))["balance"]["rows"]["Borrowings"] == [0.0, 0.0, 0.0]


def test_a_report_with_cost_of_sales_has_a_revenue_line():
    ni = [_yr(y, 5e6) for y in range(2022, 2025)]
    facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [_yr(2022, 50e6)]}}, "NetIncomeLoss": {"units": {"USD": ni}},
                                   "CostOfRevenue": {"units": {"USD": [_yr(2023, 30e6)]}}}}}      # revenue tagged a way not read
    assert "Dec 2023" not in sec.build(facts, _subs(["10-K"]))["no_revenue"]
