"""A fake SEC EDGAR: the ticker list, a filing list and XBRL company facts for one company shaped like the real thing
(fiscal years ending in late September, the revenue concept changing in 2018, a restated year, six- and nine-month
year-to-date figures in the quarterly reports, and the fourth quarter only inside the annual report)."""
import re
from datetime import date, timedelta

import httpx

CIK = 320193
FY_ENDS = ["2019-09-28", "2020-09-26", "2021-09-25", "2022-09-24", "2023-09-30", "2024-09-28", "2025-09-27"]
REVENUE = [260174, 274515, 365817, 394328, 383285, 391035, 416161]          # $ millions
NET = [55256, 57411, 94680, 99803, 96995, 93736, 112010]
OPER = [63930, 66288, 108949, 119437, 114301, 123216, 133050]
DEP = [12547, 11056, 11284, 11104, 11519, 11445, 11700]
CAPEX = [10495, 7309, 11085, 10708, 10959, 9447, 12715]
M = 1_000_000


def _start(end: str, days: int) -> str:
    return (date.fromisoformat(end) - timedelta(days=days)).isoformat()


def _flow(vals, concept_for=lambda i: "x", restated=None):
    """Annual rows, each reported in its own 10-K and again (as a comparative) in the next one."""
    rows = []
    for i, (end, v) in enumerate(zip(FY_ENDS, vals)):
        filed = (date.fromisoformat(end) + timedelta(days=35)).isoformat()
        rows.append({"start": _start(end, 364), "end": end, "val": v * M, "form": "10-K", "filed": filed, "fy": int(end[:4])})
        if i + 1 < len(FY_ENDS):                         # the comparative in next year's report, maybe restated
            later = (date.fromisoformat(FY_ENDS[i + 1]) + timedelta(days=35)).isoformat()
            val = (restated or {}).get(end, v)
            rows.append({"start": _start(end, 364), "end": end, "val": val * M, "form": "10-K", "filed": later})
    return rows


def _quarters(annual_vals, next_year_quarters):
    """Each year's first three quarters as filed in the quarterly reports (3 months each), plus the six- and
    nine-month year-to-date figures those reports also carry; then quarters of the year in progress."""
    rows = []
    for end, total in zip(FY_ENDS, annual_vals):
        fs = date.fromisoformat(_start(end, 364))
        q = [round(total * w) for w in (0.3, 0.22, 0.22)]
        for k in range(3):
            qs, qe = fs + timedelta(days=91 * k), fs + timedelta(days=91 * (k + 1) - 1)
            filed = (qe + timedelta(days=30)).isoformat()
            rows.append({"start": qs.isoformat(), "end": qe.isoformat(), "val": q[k] * M, "form": "10-Q", "filed": filed})
            if k:
                rows.append({"start": fs.isoformat(), "end": qe.isoformat(), "val": sum(q[:k + 1]) * M, "form": "10-Q", "filed": filed})
    fs = date.fromisoformat(FY_ENDS[-1]) + timedelta(days=1)
    for k, v in enumerate(next_year_quarters):
        qs, qe = fs + timedelta(days=91 * k), fs + timedelta(days=91 * (k + 1) - 1)
        rows.append({"start": qs.isoformat(), "end": qe.isoformat(), "val": v * M, "form": "10-Q",
                     "filed": (qe + timedelta(days=30)).isoformat()})
    return rows


def _ytd(annual_vals, next_year_quarters):
    """Cash-flow style: the quarterly reports give the first quarter, then only the year so far (6 and 9 months)."""
    rows = []
    years = [(_start(e, 364), [round(t * w) for w in (0.25, 0.25, 0.25)]) for e, t in zip(FY_ENDS, annual_vals)]
    years.append(((date.fromisoformat(FY_ENDS[-1]) + timedelta(days=1)).isoformat(), list(next_year_quarters)))
    for fs, qs in years:
        start = date.fromisoformat(fs)
        for k in range(len(qs)):
            end = (start + timedelta(days=91 * (k + 1) - 1)).isoformat()
            rows.append({"start": fs, "end": end, "val": sum(qs[:k + 1]) * M, "form": "10-Q", "filed": _start(end, -30)})
    return rows


def facts() -> dict:
    rev = _flow(REVENUE, restated={"2023-09-30": 383300})
    old = [r for r in rev if r["end"] < "2019-12-31"]
    new = [r for r in rev if r["end"] >= "2019-12-31"]
    rev_q = _quarters(REVENUE, [124300, 95400])
    instant = lambda vals: [{"end": e, "val": v * M, "form": "10-K", "filed": _start(e, -35)} for e, v in zip(FY_ENDS, vals)]  # noqa: E731
    return {"cik": CIK, "entityName": "Apple Inc.", "facts": {
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-01-20", "val": 14_800_000_000}]}}},
        "us-gaap": {
            "SalesRevenueNet": {"units": {"USD": old + [{"start": "2018-09-30", "end": "2019-09-28", "val": 1 * M, "form": "10-K", "filed": "2019-11-01"}]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": new + [r for r in rev_q]}},
            "NetIncomeLoss": {"units": {"USD": _flow(NET) + _quarters(NET, [36300, 24800])}},
            "OperatingIncomeLoss": {"units": {"USD": _flow(OPER) + _quarters(OPER, [42800, 29600])}},
            "DepreciationDepletionAndAmortization": {"units": {"USD": _flow(DEP) + _ytd(DEP, [2900, 2950])}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [{**r, "val": r["val"] / M / 1000} for r in _flow([2975, 3280, 5610, 6110, 6130, 6080, 7460])]}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": _flow(CAPEX)}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": _flow([69391, 80674, 104038, 122151, 110543, 118254, 111482])}},
            "NetCashProvidedByUsedInInvestingActivities": {"units": {"USD": _flow([45896, -4289, -14545, -22354, 3705, 2935, 15195])}},
            "PropertyPlantAndEquipmentNet": {"units": {"USD": instant([37378, 36766, 39440, 42117, 43715, 45680, 49834])}},
            "LongTermDebtNoncurrent": {"units": {"USD": instant([91807, 98667, 109106, 98959, 95281, 85750, 78328])}},
            "LongTermDebtCurrent": {"units": {"USD": instant([10260, 8773, 9613, 11128, 9822, 10912, 12350])}},
            "CommercialPaper": {"units": {"USD": instant([5980, 4996, 6000, 9982, 5985, 9967, 8000])}},
            "StockholdersEquity": {"units": {"USD": instant([90488, 65339, 63090, 50672, 62146, 56950, 73733])}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": instant([48844, 38016, 34940, 23646, 29965, 29943, 35934])}},
        }}}


def subs() -> dict:
    recent = {"form": ["8-K", "10-Q", "10-K", "4", "8-K", "10-Q"],
              "filingDate": ["2026-05-01", "2026-05-02", "2025-10-31", "2025-10-20", "2025-10-30", "2025-08-01"],
              "accessionNumber": ["0000320193-26-000011", "0000320193-26-000012", "0000320193-25-000079", "0000320193-25-000070",
                                  "0000320193-25-000077", "0000320193-25-000073"],
              "primaryDocument": ["a8-k.htm", "a10-q.htm", "a10-k.htm", "xslF345X05/wk-form4.xml", "a8-k.htm", "a10-q.htm"],
              "items": ["2.02,9.01", "", "", "", "2.02,9.01", ""]}
    return {"cik": str(CIK), "name": "Apple Inc.", "sic": "3571", "sicDescription": "ELECTRONIC COMPUTERS",
            "fiscalYearEnd": "0927", "website": "", "tickers": ["AAPL"], "filings": {"recent": recent}}


FILLER = "The company continues to invest in research and development across its product lines. " * 40
TEN_K = f"""<html><body><ix:header><p>hidden xbrl header</p></ix:header>
<p>TABLE OF CONTENTS</p><p>Item 1. Business 1</p><p>Item 1A. Risk Factors 9</p><p>Item 2. Properties 20</p>
<p>Item 7. Management's Discussion and Analysis 25</p><p>Item 8. Financial Statements 40</p>
<p>PART I</p><p>Item 1. Business</p>
<p>The Company designs, manufactures and markets smartphones, personal computers, tablets, wearables and accessories,
and sells a variety of related services. iPhone net sales were 51% of total net sales.</p><p>{FILLER}</p>
<p>Item 1A. Risk Factors</p><p>The Company's business depends on global supply chains concentrated in Asia.</p><p>{FILLER}</p>
<p>Item 1B. Unresolved Staff Comments</p><p>None.</p><p>Item 2. Properties</p><p>Offices in Cupertino.</p>
<p>Item 7. Management's Discussion and Analysis</p><p>Liquidity and Capital Resources. The Company expects capital
expenditures of approximately $14 billion in fiscal 2026, mainly for data centers.</p><p>{FILLER}</p>
<p>Item 7A. Quantitative and Qualitative Disclosures</p><p>Item 8. Financial Statements</p></body></html>"""
RELEASE = f"""<html><body><p>Apple reports second quarter results.</p><p>The Company expects revenue to grow in the
low to mid single digits in the June quarter.</p><p>{FILLER}</p></body></html>"""


HOLDERS = ["Northfield Asset Management LP", "Ridgeway Capital Partners", "Harbor Index Advisors", "Lakeshore Investment Group", "Summit Pension Trust"]


def other_subs(cik: int) -> dict:
    """A made-up filing list for any other S&P 500 company (by its number): a few 8-K items and 13D/13G filings, dated
    from today so they fall inside the stored windows. Which company has which depends only on its number."""
    day = lambda n: (date.today() - timedelta(days=n)).isoformat()
    rows = []                                                     # (form, filed, accession, document, items)
    acc = lambda k: f"{cik:010d}-26-{k:06d}"
    if cik % 5 == 0:
        rows.append(("8-K", day(3 + cik % 30), acc(1), "a8-k.htm", "4.01,9.01"))
    if cik % 7 == 0:
        rows.append(("8-K", day(1 + cik % 20), acc(2), "b8-k.htm", "5.02"))
    if cik % 23 == 0:
        rows.append(("8-K", day(5 + cik % 40), acc(3), "c8-k.htm", "4.02,9.01"))
    if cik % 31 == 0:
        rows.append(("8-K", day(2 + cik % 50), acc(4), "d8-k.htm", "3.01"))
    if cik % 11 == 0:
        rows.append(("SCHEDULE 13G/A", day(2 + cik % 60), acc(5), "xslSCHEDULE_13G_X02/primary_doc.xml", ""))
    if cik % 53 == 0:
        rows.append(("SC 13D", day(4 + cik % 80), acc(6), "d13.htm", ""))
    rows.append(("8-K", day(30), acc(7), "e8-k.htm", "2.02,9.01"))        # an earnings release: not flagged
    rows.sort(key=lambda x: x[1], reverse=True)
    cols = list(zip(*rows))
    recent = dict(zip(("form", "filingDate", "accessionNumber", "primaryDocument", "items"), map(list, cols)))
    return {"cik": str(cik), "name": f"Company {cik}", "sic": "3571", "sicDescription": "X", "fiscalYearEnd": "1231", "website": "",
            "tickers": [], "filings": {"recent": recent}}


def cover_text(cik: int) -> str:
    """A 13D/13G cover page's text for one made-up holder of the company with this number."""
    holder, pct = HOLDERS[cik % len(HOLDERS)], 5.1 + (cik % 90) / 10
    return (f"SCHEDULE 13G Company {cik} (Name of Issuer) Common Stock 1 Names of Reporting Persons {holder} 2 Check the appropriate box if a member "
            f"of a Group (see instructions) 9 Aggregate Amount Beneficially Owned by Each Reporting Person {cik * 1000:,}.00 11 Percent of class "
            f"represented by amount in row (9) {pct:.2f} % 12 Type of Reporting Person IA")


def transport(calls: list | None = None) -> httpx.MockTransport:
    def handler(r: httpx.Request):
        if calls is not None:
            calls.append(r.url.path)
        m = re.fullmatch(r"/submissions/CIK(\d{10})\.json", r.url.path)
        if m and int(m.group(1)) not in (CIK, 1067983):
            return httpx.Response(200, json=other_subs(int(m.group(1))))
        m = re.match(r"/Archives/edgar/data/(\d+)/\d+/(xslSCHEDULE_13G_X02/primary_doc\.xml|d13\.htm)$", r.url.path)
        if m:
            return httpx.Response(200, text=cover_text(int(m.group(1))), headers={"content-type": "text/plain"})
        if r.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": CIK, "ticker": "AAPL", "title": "Apple Inc."},
                                             "1": {"cik_str": 1067983, "ticker": "BRK-B", "title": "Berkshire Hathaway Inc"}})
        if r.url.path == f"/submissions/CIK{CIK:010d}.json":
            return httpx.Response(200, json=subs())
        if r.url.path == f"/api/xbrl/companyfacts/CIK{CIK:010d}.json":
            return httpx.Response(200, json=facts())
        if r.url.path.endswith("/000032019325000079/a10-k.htm"):
            return httpx.Response(200, text=TEN_K, headers={"content-type": "text/html"})
        if r.url.path.endswith("/000032019326000011/index.json"):
            return httpx.Response(200, json={"directory": {"item": [{"name": "a8-k.htm"}, {"name": "a8-kex991q2.htm"},
                                                                    {"name": "0000320193-26-000011-index.html"}]}})
        if r.url.path.endswith("/000032019326000011/a8-kex991q2.htm"):
            return httpx.Response(200, text=RELEASE, headers={"content-type": "text/html"})
        return httpx.Response(404, json={})
    return httpx.MockTransport(handler)
