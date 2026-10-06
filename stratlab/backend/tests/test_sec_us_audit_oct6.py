"""Fixes from the US whole-market audit of 6 October 2026, on constructed SEC company-facts payloads: the currency a
company reports in, fiscal-year ends filed a few days apart, figures for other 12 months than the fiscal year,
revenue lines that weren't read, and "no revenue" said only when the annual report has no revenue line."""
from app import audit
from app.intel import sec


def _f(v, end, start, form="10-K", accn=None, unit="USD"):
    return {"start": start, "end": end, "val": v * 1_000_000, "form": form, "filed": f"{end[:4]}-12-31", "accn": accn or f"acc-{end}"}


def _yr(y, v, form="10-K", accn=None):
    return _f(v, f"{y}-12-31", f"{y}-01-01", form, accn or f"acc-{y}")


def _facts(**concepts):
    """{"us-gaap": {concept: {"units": {unit: [rows]}}}}; a value is a list of rows or {unit: rows}."""
    out = {}
    for name, rows in concepts.items():
        units = rows if isinstance(rows, dict) else {"USD": rows}
        out[name] = {"units": units}
    return out


def _build(us=None, ifrs=None, forms=("10-K",), sic=""):
    facts = {}
    if us:
        facts["us-gaap"] = _facts(**us)
    if ifrs:
        facts["ifrs-full"] = _facts(**ifrs)
    subs = {"cik": "1", "name": "Co", "sic": sic, "filings": {"recent": {"form": list(forms)}}}
    return sec.build({"cik": 1, "facts": facts}, subs)


# ---------- currency ----------
def test_a_stray_old_figure_in_another_currency_does_not_change_the_currency():
    ifrs = {"Revenue": [_yr(y, 100 + y) for y in range(2021, 2025)], "ProfitLoss": [_yr(y, 10) for y in range(2021, 2025)]}
    us = {"ProfitLoss": {"CAD": [_yr(2019, 5), _yr(2020, 6)]}}
    assert sec.currency({"ifrs-full": _facts(**ifrs), "us-gaap": _facts(**us)}) is None          # dollars, as filed since


def test_euro_annual_results_beside_dollar_interim_figures_are_euros():
    rev = {"EUR": [_yr(2023, 100), _yr(2024, 120)], "USD": [_f(70, "2025-06-30", "2025-01-01", "6-K")]}
    assert sec.currency({"ifrs-full": _facts(Revenue=rev)}) == "EUR"


def test_a_dollar_translation_beside_the_filers_own_currency_is_the_own_currency():
    rev = {"CNY": [_yr(2024, 800)], "USD": [_yr(2024, 110)]}
    assert sec.currency({"ifrs-full": _facts(Revenue=rev)}) == "CNY"


def test_a_canadian_company_that_once_filed_in_dollars_is_read_in_its_latest_currency():
    rev = {"USD": [_yr(2021, 100)], "CAD": [_yr(2023, 130), _yr(2024, 140)]}
    assert sec.currency({"ifrs-full": _facts(Revenue=rev)}) == "CAD"


# ---------- one column per fiscal year ----------
def _year_drift_facts():
    """A 52/53-week company: revenue filed for the year ending 30 Nov, profit for the 29th in one report and the 30th in another."""
    rev = [_f(3000, "2023-12-02", "2022-12-04"), _f(3100, "2024-11-30", "2023-12-03"), _f(3200, "2025-11-29", "2024-12-01")]
    ni = [_f(100, "2023-12-02", "2022-12-04"), _f(110, "2024-11-29", "2023-12-03", accn="a1"), _f(110, "2024-11-30", "2023-12-03", accn="a2"),
          _f(120, "2025-11-29", "2024-12-01")]
    return {"Revenues": rev, "NetIncomeLoss": ni}


def test_a_year_end_filed_a_day_apart_is_one_year_with_its_revenue():
    out = _build(us=_year_drift_facts())
    assert out["pl"]["cols"] == ["Dec 2023", "Nov 2024", "Nov 2025"]
    assert out["pl"]["rows"]["Sales"] == [3000.0, 3100.0, 3200.0]
    assert out["pl"]["rows"]["Net Profit"] == [100.0, 110.0, 120.0]
    assert out["no_revenue"] == []


def test_profit_for_a_tax_year_ending_months_off_the_fiscal_year_is_not_a_year_of_its_own():
    rev = [_f(600, f"{y}-06-30", f"{y - 1}-07-01") for y in (2022, 2023, 2024)]
    ni = [_f(50, f"{y}-06-30", f"{y - 1}-07-01") for y in (2022, 2023, 2024)] + [_f(40, f"{y}-08-31", f"{y - 1}-09-01") for y in (2022, 2023, 2024)]
    out = _build(us={"GrossInvestmentIncomeOperating": rev, "NetIncomeLoss": ni})
    assert out["pl"]["cols"] == ["Jun 2022", "Jun 2023", "Jun 2024"] and out["no_revenue"] == []


def test_revenue_of_a_subsidiary_note_for_other_months_is_not_a_year_of_its_own():
    rev = [_f(5000, f"{y}-03-31", f"{y - 1}-04-01") for y in (2023, 2024)] + [_f(200, f"{y}-12-31", f"{y}-01-01") for y in (2023,)]
    ni = [_f(300, f"{y}-03-31", f"{y - 1}-04-01") for y in (2023, 2024)]
    out = _build(us={"Revenues": rev, "NetIncomeLoss": ni})
    assert out["pl"]["cols"] == ["Mar 2023", "Mar 2024"]


def test_genuinely_separate_years_stay_separate():
    rev = [_yr(y, 100 * y) for y in (2021, 2022, 2023)]
    ni = [_yr(y, 10) for y in (2021, 2022, 2023)]
    assert _build(us={"Revenues": rev, "NetIncomeLoss": ni})["pl"]["cols"] == ["Dec 2021", "Dec 2022", "Dec 2023"]


# ---------- revenue lines ----------
def test_revenue_concepts_of_utilities_banks_airlines_and_advisers_are_read():
    ni = [_yr(2024, 10)]
    assert _build(us={"RegulatedOperatingRevenue": [_yr(2024, 500)], "NetIncomeLoss": ni})["pl"]["rows"]["Sales"] == [500.0]
    assert _build(us={"InvestmentBankingRevenue": [_yr(2024, 700)], "NetIncomeLoss": ni})["pl"]["rows"]["Sales"] == [700.0]
    ifrs = {"RevenueFromRenderingOfTransportServices": [_yr(2024, 900)], "ProfitLoss": ni}
    assert _build(ifrs=ifrs)["pl"]["rows"]["Sales"] == [900.0]
    bank = {"RevenueFromInterest": [_yr(2024, 800)], "FeeAndCommissionIncome": [_yr(2024, 200)], "ProfitLoss": ni}
    assert _build(ifrs=bank)["pl"]["rows"]["Sales"] == [1000.0]


def test_revenue_worked_out_from_costs_is_never_nil_or_negative():
    us = {"OperatingIncomeLoss": [_yr(2024, -18)], "CostsAndExpenses": [_yr(2024, 4)], "NetIncomeLoss": [_yr(2024, -24)]}
    out = _build(us=us)
    assert out["pl"]["rows"]["Sales"] == [None] and out["no_revenue"] == ["Dec 2024"]


def test_a_report_with_only_the_last_quarters_revenue_has_a_revenue_line():
    """The year's total filed with the wrong start date (a 90-day period ending on the year end): the report does tag
    revenue, so it isn't a year without sales."""
    q4 = _f(21_865, "2025-12-31", "2025-10-01", accn="acc-2025")
    out = _build(us={"RevenueFromContractWithCustomerExcludingAssessedTax": [_yr(2023, 19_000), _yr(2024, 20_000), q4],
                     "NetIncomeLoss": [_yr(y, 1_000) for y in (2023, 2024, 2025)]})
    assert out["pl"]["rows"]["Sales"][-1] is None and out["no_revenue"] == []


def test_an_operating_profit_without_revenue_behind_it_is_a_revenue_not_read():
    us = {"OperatingIncomeLoss": [_yr(2024, 90)], "NetIncomeLoss": [_yr(2024, 50)]}
    assert _build(us=us)["no_revenue"] == []
    us = {"OperatingIncomeLoss": [_yr(2024, -90)], "NetIncomeLoss": [_yr(2024, -50)]}
    assert _build(us=us)["no_revenue"] == ["Dec 2024"]


def test_a_revenue_named_line_we_have_no_name_for_is_not_a_year_without_sales():
    us = {"RevenueFromSomethingNew": [_yr(2024, 90)], "NetIncomeLoss": [_yr(2024, 5)]}
    assert _build(us=us)["no_revenue"] == []


# ---------- first report covers part of a year ----------
def test_a_first_annual_report_for_part_of_a_year_is_said_plainly():
    facts = {"us-gaap": _facts(NetIncomeLoss=[_f(-217, "2025-12-31", "2025-03-13")], OperatingIncomeLoss=[_f(-15, "2025-12-31", "2025-03-13")])}
    why = sec.no_results({"filings": {"recent": {"form": ["10-K", "S-1"]}}}, facts, "NEW")
    assert why == sec.NO_RESULTS["part_year"] and any(x in why for x in audit.NOT_COVERED)


# ---------- the audit says "no revenue" only when the report has no revenue line ----------
def _nums(no_revenue):
    years = [{"year": f"Dec {y}", "sales": None, "profit": -5.0, "opm": None, "capex": None} for y in (2022, 2023, 2024)]
    return {"years": years, "no_revenue": no_revenue, "quarters": []}


def _codes(issues):
    return [(i["level"], i["detail"]) for i in issues if i["area"] == "Numbers"]


def test_a_us_company_whose_revenue_wasnt_read_is_a_gap_not_a_company_without_sales():
    p = {"region": "US", "pl": {"cols": [], "rows": {}}}
    got = _codes(audit.check_numbers(p, _nums([]), {}))
    assert ("fact", audit.NO_REVENUE) not in got and any(lv == "gap" and "Revenue or profit missing" in d for lv, d in got)


def test_a_us_company_whose_reports_have_no_revenue_line_is_a_fact():
    p = {"region": "US", "pl": {"cols": [], "rows": {}}}
    assert ("fact", audit.NO_REVENUE) in _codes(audit.check_numbers(p, _nums(["Dec 2022", "Dec 2023", "Dec 2024"]), {}))
