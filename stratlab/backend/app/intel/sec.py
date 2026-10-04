"""US company fundamentals from the SEC's EDGAR system (free, no key): the numbers companies file in their 10-K and
10-Q reports (XBRL "company facts"), their industry (SIC code) and their list of filings.

The result has the same shape as the Indian company pages (see screener.parse), in US$ millions instead of ₹ crore,
so the deep dive, checklist, valuation and deck work on it unchanged. Two things are better than the Indian source:
capex is reported directly (no estimate) and cash is reported, so enterprise value can subtract it."""
import re
import threading
import time
from datetime import date, datetime

import httpx

from .net import Source, SourceError

# the SEC asks automated users to say who they are; 10 requests a second at most
UA = "StratLab research (contact@stratlab.studio)"
M = 1_000_000

# each line: the row in the company table, then the XBRL concepts that report it, best first. Companies change the
# concept they use over the years (revenue moved to the ASC 606 names in 2018), so each period takes the first that
# has a value for it. Foreign companies filing a 20-F or 40-F under IFRS use that taxonomy's names (Revenue,
# ProfitLoss...), listed after the US ones.
# Total revenue can sit under any of these, and a company may also tag just a part with one of them (contract revenue
# without the lease income a REIT or tower company earns), so for each period the largest is the top line.
TOP_LINE = ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
            "SalesRevenueNet", "Revenue", "RevenueFromContractsWithCustomers")
# ...and when none of those is filed: narrower lines that are the revenue for some kinds of company (utilities,
# REITs, insurers, brokers, business development companies, miners, IFRS banks)
REVENUE_ELSE = ("SalesRevenueGoodsNet", "SalesRevenueServicesNet", "RegulatedAndUnregulatedOperatingRevenue",
                "ElectricUtilityRevenue", "RealEstateRevenueNet", "OperatingLeaseLeaseIncome",
                "OperatingLeasesIncomeStatementLeaseRevenue", "PremiumsEarnedNet", "RevenuesNetOfInterestExpense",
                "RevenuesExcludingInterestAndDividends", "GrossInvestmentIncomeOperating", "InvestmentIncomeInterestAndDividend",
                "OilAndGasRevenue", "RevenueMineralSales", "HealthCareOrganizationRevenue", "ContractsRevenue",
                "FinancialServicesRevenue", "RevenueFromSaleOfGoods", "RevenueFromRenderingOfServices",
                "InterestRevenueCalculatedUsingEffectiveInterestMethod")
# a bank's revenue when it files no total: interest and dividend income plus everything else it earns (fees)
BANK_INTEREST = ("InterestAndDividendIncomeOperating", "InterestAndFeeIncomeLoansAndLeases")
BANK_OTHER = ("NoninterestIncome",)
NET_INCOME = ("NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "NetIncomeLossAvailableToCommonStockholdersBasic",
              "ProfitLoss", "IncomeLossFromContinuingOperations",
              "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
              "NetIncomeLossAvailableToCommonStockholdersDiluted")
OPERATING = ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities")
DEPRECIATION = ("DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                "DepreciationAndAmortization", "CostDepreciationAmortizationAndDepletion", "Depreciation",
                "DepreciationAndAmortisationExpense", "AdjustmentsForDepreciationAndAmortisationExpense")
EPS = ("EarningsPerShareDiluted", "EarningsPerShareBasic", "DilutedEarningsLossPerShare", "BasicEarningsLossPerShare")
PPE = ("PropertyPlantAndEquipmentNet",
       "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
       "PropertyPlantAndEquipment")
EQUITY = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
          "PartnersCapital", "MembersEquity", "EquityAttributableToOwnersOfParent", "Equity")
CASH = ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "Cash",
        "CashAndCashEquivalents")
CFO = ("NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
       "CashFlowsFromUsedInOperatingActivities")
CFI = ("NetCashProvidedByUsedInInvestingActivities", "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
       "CashFlowsFromUsedInInvestingActivities")
# capex: plant and equipment, or what a REIT, an oil and gas producer or a miner spends on its own kind of asset
CAPEX = ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets", "PaymentsForCapitalImprovements",
         "PaymentsToAcquireOtherPropertyPlantAndEquipment", "PaymentsToAcquireAndDevelopRealEstate",
         "PaymentsToDevelopRealEstateAssets", "PaymentsToAcquireRealEstate", "PaymentsToAcquireOilAndGasPropertyAndEquipment",
         "PaymentsToAcquireOilAndGasProperty", "PaymentsToExploreAndDevelopOilAndGasProperties", "PaymentsToAcquireMiningAssets",
         "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "PurchaseOfPropertyPlantAndEquipment")
DIVIDENDS = ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "DividendsPaidClassifiedAsFinancingActivities",
             "DividendsPaid")
# debt: long-term debt including the part due within a year, or its two halves, plus short-term borrowings
DEBT_TOTAL = ("LongTermDebt", "DebtLongtermAndShorttermCombinedAmount", "Borrowings")
DEBT_PARTS = (("LongTermDebtNoncurrent",), ("LongTermDebtCurrent", "DebtCurrent"))
DEBT_SHORT = ("ShortTermBorrowings", "CommercialPaper")
# the share count when a report's cover page doesn't give one the facts can read (companies with two classes of shares
# give a count per class): the balance sheet's, else the year's diluted average
SHARES = ("CommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding",
          "WeightedAverageNumberOfSharesOutstandingBasic")

ANNUAL = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")

# names of what the SEC lists that isn't an operating company: funds, ETFs and ETNs, commodity and crypto trusts, and
# blank-check companies (SPACs) still looking for a business
NOT_OPERATING = re.compile(r"\bETFs?\b|\bETNs?\b|\bfunds?\b|ishares|\bspdr\b|proshares|municipal|closed[- ]end|"
                           r"\btrust\b.*\b(?:income|bond|treasury|bitcoin|ether(?:eum)?|gold|silver|currency|commodit\w*)\b|"
                           r"\b(?:bitcoin|ether(?:eum)?|gold|silver|commodity)\b.*\btrust\b|"
                           r"\bacquisition (?:corp|co|company|inc|ltd|limited)\b|blank check", re.I)


def not_operating(name: str | None) -> bool:
    return bool(NOT_OPERATING.search(str(name or "")))


# a ticker's suffix that marks a preferred share, warrant, unit or right, never the common stock: AHL-PD, BAC.PRL,
# ACON-W, ALFU-U, XYZ-RT. Share classes of the common stock (BRK-A, BRK-B) are left alone.
NON_COMMON = re.compile(r"[-.](?:P[A-Z]?|PR[A-Z]?|W[A-Z]?|WT[A-Z]?|WS[A-Z]?|U|UN|R|RT|RI)$")


def non_common(t: str) -> bool:
    """A preferred share, warrant, unit or right by its ticker alone, whether or not its common stock is listed too."""
    return bool(NON_COMMON.search(str(t or "").upper()))


def derived_ticker(t: str, siblings: list[str]) -> bool:
    """A preferred share, warrant, right or unit of a company whose main ticker is also listed: AHL-PD beside AHL,
    ACONW beside ACON, ALFUU beside ALFU."""
    if "-" in t or "." in t:
        return True
    return len(t) == 5 and t[-1] in "WUR" and t[:4] in siblings


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _label(end: str) -> str:
    """A period's column name, as on the Indian pages: the month its year or quarter ends ("Sep 2025")."""
    return datetime.strptime(end, "%Y-%m-%d").strftime("%b %Y")


def _facts(facts: dict, concept: str, unit: str = "USD") -> list[dict]:
    for ns in ("us-gaap", "ifrs-full"):
        units = ((facts.get(ns) or {}).get(concept) or {}).get("units") or {}
        if unit in units:
            return units[unit]
        for u, rows in units.items():            # "USD/shares" for per-share numbers
            if u.startswith(unit):
                return rows
    return []


def flows(facts: dict, concepts: tuple, kind: str, unit: str = "USD") -> dict[str, float]:
    """{period end: value} for a flow (income, cash flow) over a year ("annual") or a quarter ("quarter").
    For each period the latest filing wins (restatements); for each period the first concept with a value wins."""
    out: dict[str, float] = {}
    for concept in concepts:
        best: dict[str, tuple[str, float]] = {}
        for f in _facts(facts, concept, unit):
            if not f.get("start") or f.get("val") is None:
                continue
            d = _days(f["start"], f["end"])
            if kind == "annual" and not (340 <= d <= 380 and f.get("form") in ANNUAL):
                continue
            if kind == "quarter" and not (80 <= d <= 100):
                continue
            filed = f.get("filed") or ""
            if f["end"] not in best or filed > best[f["end"]][0]:
                best[f["end"]] = (filed, float(f["val"]))
        for end, (_, v) in best.items():
            out.setdefault(end, v)
    return out


def instants(facts: dict, concepts: tuple, unit: str = "USD") -> dict[str, float]:
    """{date: value} for a balance-sheet number, latest filing winning; first concept with a value for a date."""
    out: dict[str, float] = {}
    for concept in concepts:
        best: dict[str, tuple[str, float]] = {}
        for f in _facts(facts, concept, unit):
            if f.get("start") or f.get("val") is None:
                continue
            filed = f.get("filed") or ""
            if f["end"] not in best or filed > best[f["end"]][0]:
                best[f["end"]] = (filed, float(f["val"]))
        for end, (_, v) in best.items():
            out.setdefault(end, v)
    return out


def quarterly(facts: dict, concepts: tuple, unit: str = "USD") -> dict[str, float]:
    """{quarter end: value}. Quarterly reports give some numbers for the quarter (3 months) and others only for the
    year so far (6 and 9 months, cash flow mostly); the annual report gives 12 months. Each quarter is the year-to-date
    figure less the one before it, unless the quarter is reported on its own. First concept with a value wins."""
    out: dict[str, float] = {}
    for concept in concepts:
        latest: dict[tuple[str, str], tuple[str, float]] = {}
        for f in _facts(facts, concept, unit):
            if not f.get("start") or f.get("val") is None:
                continue
            k = (f["start"], f["end"])
            if k not in latest or (f.get("filed") or "") > latest[k][0]:
                latest[k] = (f.get("filed") or "", float(f["val"]))
        mine: dict[str, float] = {}
        by_start: dict[str, list[tuple[str, float]]] = {}
        for (start, end), (_, v) in latest.items():
            d = _days(start, end)
            if 80 <= d <= 100:
                mine[end] = v
            if any(lo <= d <= hi for lo, hi in ((80, 100), (170, 195), (260, 285), (340, 380))):
                by_start.setdefault(start, []).append((end, v))
        for start, runs in by_start.items():           # the year so far, quarter by quarter
            runs.sort()
            for (e0, v0), (e1, v1) in zip(runs, runs[1:]):
                if 80 <= _days(e0, e1) <= 100 and e1 not in mine:
                    mine[e1] = v1 - v0
        for end, v in mine.items():
            out.setdefault(end, v)
    return out


def revenue(facts: dict, kind: str) -> dict[str, float]:
    """{period end: revenue} for "annual" or "quarter": the largest top-line figure filed for each period, else the
    first narrower one."""
    get = (lambda c: flows(facts, (c,), "annual")) if kind == "annual" else (lambda c: quarterly(facts, (c,)))
    out: dict[str, float] = {}
    for c in TOP_LINE:
        for end, v in get(c).items():
            if end not in out or v > out[end]:
                out[end] = v
    for end, v in (flows(facts, REVENUE_ELSE, "annual") if kind == "annual" else quarterly(facts, REVENUE_ELSE)).items():
        out.setdefault(end, v)
    read = (lambda cs: flows(facts, cs, "annual")) if kind == "annual" else (lambda cs: quarterly(facts, cs))   # noqa: E731
    interest, other = read(BANK_INTEREST), read(BANK_OTHER)
    for end, v in interest.items():           # a bank: interest income plus fees and other income
        out.setdefault(end, v + other.get(end, 0))
    return out


def currency(facts: dict) -> str | None:
    """The currency a company's results are filed in, when it isn't US dollars (a foreign filer under IFRS): read
    from the units its revenue or profit is reported in."""
    for ns in ("ifrs-full", "us-gaap"):
        for concept in TOP_LINE + NET_INCOME:
            units = ((facts.get(ns) or {}).get(concept) or {}).get("units") or {}
            other = [u for u in units if re.fullmatch(r"[A-Z]{3}", u) and u != "USD"]
            if units and "USD" not in units and other:
                return other[0]
    return None


def _debt(facts: dict) -> dict[str, float]:
    total = instants(facts, DEBT_TOTAL)
    parts = [instants(facts, p) for p in DEBT_PARTS]
    short = instants(facts, DEBT_SHORT)
    out = {}
    for d in set(total) | set(parts[0]) | set(parts[1]) | set(short):
        base = total.get(d)
        if base is None and (d in parts[0] or d in parts[1]):
            base = parts[0].get(d, 0) + parts[1].get(d, 0)
        if base is None and d not in short:
            continue
        out[d] = (base or 0) + short.get(d, 0)
    return out


def _mn(v: float | None) -> float | None:
    return round(v / M, 2) if v is not None else None


def _ttm(quarter: dict[str, float]) -> float | None:
    q = sorted(quarter)[-4:]
    if len(q) < 4 or _days(q[0], q[-1]) > 300:
        return None
    return sum(quarter[x] for x in q)


def build(facts_json: dict, subs: dict | None = None, years: int = 12) -> dict:
    """The company in the deep dive's shape: P&L, balance sheet and cash flow by year, the last twelve quarters,
    and the industry path, in US$ millions."""
    facts = facts_json.get("facts") or {}
    rev_a, rev_q = revenue(facts, "annual"), revenue(facts, "quarter")
    ni_a, ni_q = flows(facts, NET_INCOME, "annual"), quarterly(facts, NET_INCOME)
    op_a, op_q = flows(facts, OPERATING, "annual"), quarterly(facts, OPERATING)
    dep_a, dep_q = flows(facts, DEPRECIATION, "annual"), quarterly(facts, DEPRECIATION)
    # operating profit as on the Indian pages: before depreciation (EBITDA), so margins and EV/EBITDA mean the same
    ebitda = lambda op, dep: (op + dep) if op is not None and dep is not None else None   # noqa: E731
    eb_a = {e: ebitda(op_a.get(e), dep_a.get(e)) for e in op_a}
    eb_q = {e: ebitda(op_q.get(e), dep_q.get(e)) for e in op_q}
    eps_a = flows(facts, EPS, "annual", unit="USD/shares")
    cfo_a, cfi_a = flows(facts, CFO, "annual"), flows(facts, CFI, "annual")
    capex_a, div_a = flows(facts, CAPEX, "annual"), flows(facts, DIVIDENDS, "annual")
    ppe, debt, equity, cash = instants(facts, PPE), _debt(facts), instants(facts, EQUITY), instants(facts, CASH)

    ends = sorted(set(rev_a) | set(ni_a))[-years:]
    if not ends:
        cur = currency(facts)
        if cur:
            raise SourceError("SEC EDGAR", f"This company reports its results in {cur}, not US dollars, so they aren't shown here yet.")
        raise SourceError("SEC EDGAR", "The SEC has no annual results filed in XBRL for this company.")
    cols = [_label(e) for e in ends]
    margin = lambda op, rev: round(op / rev * 100, 1) if op is not None and rev else None   # noqa: E731
    ttm_rev, ttm_ni, ttm_op, ttm_dep = _ttm(rev_q), _ttm(ni_q), _ttm({e: v for e, v in eb_q.items() if v is not None}), _ttm(dep_q)
    has_ttm = ttm_rev is not None and ttm_ni is not None and max(rev_q) > ends[-1]
    pl_rows = {"Sales": [_mn(rev_a.get(e)) for e in ends],
               "Operating Profit": [_mn(eb_a.get(e)) for e in ends],
               "OPM %": [margin(eb_a.get(e), rev_a.get(e)) for e in ends],
               "Depreciation": [_mn(dep_a.get(e)) for e in ends],
               "Net Profit": [_mn(ni_a.get(e)) for e in ends],
               "EPS in $": [eps_a.get(e) for e in ends]}
    pl_cols = list(cols)
    if has_ttm:
        pl_cols.append("TTM")
        extra = {"Sales": _mn(ttm_rev), "Operating Profit": _mn(ttm_op), "OPM %": margin(ttm_op, ttm_rev),
                 "Depreciation": _mn(ttm_dep), "Net Profit": _mn(ttm_ni), "EPS in $": None}
        for k in pl_rows:
            pl_rows[k].append(extra[k])
    # balance sheet at each year end (an instant on the fiscal year's last day)
    bal = {"cols": cols, "rows": {"Equity": [_mn(equity.get(e)) for e in ends], "Borrowings": [_mn(debt.get(e)) for e in ends],
                                  "Fixed Assets": [_mn(ppe.get(e)) for e in ends], "Cash": [_mn(cash.get(e)) for e in ends]}}
    cf = {"cols": cols, "rows": {"Cash from Operating Activity": [_mn(cfo_a.get(e)) for e in ends],
                                 "Cash from Investing Activity": [_mn(cfi_a.get(e)) for e in ends],
                                 "Capex": [_mn(capex_a.get(e)) for e in ends],
                                 "Dividends paid": [_mn(div_a.get(e)) for e in ends]}}
    qends = sorted(rev_q)[-12:]
    quarters = {"cols": [_label(e) for e in qends],
                "rows": {"Sales": [_mn(rev_q.get(e)) for e in qends], "Net Profit": [_mn(ni_q.get(e)) for e in qends],
                         "OPM %": [margin(eb_q.get(e), rev_q.get(e)) for e in qends]}}
    subs = subs or {}
    sic = str(subs.get("sic") or "")
    shares = None                    # the latest count on a report's cover page
    for f in ((facts.get("dei") or {}).get("EntityCommonStockSharesOutstanding") or {}).get("units", {}).get("shares", []):
        if f.get("val") and (shares is None or f["end"] >= shares[0]):
            shares = (f["end"], float(f["val"]))
    for concept in SHARES if shares is None else ():
        got = [f for f in _facts(facts, concept, "shares") if f.get("val") and f.get("end")]
        if got:
            f = max(got, key=lambda f: (f["end"], f.get("filed") or ""))
            shares = (f["end"], float(f["val"]))
            break
    out = {"name": subs.get("name") or facts_json.get("entityName") or "", "ratios": {}, "growth": {}, "pros": [], "cons": [],
           "pl": {"cols": pl_cols, "rows": pl_rows}, "balance": bal, "cashflow": cf, "quarters": quarters,
           "basis": "consolidated", "unit": "$ million", "currency": "USD", "region": "US",
           "cik": facts_json.get("cik"), "sic": sic, "shares": shares[1] if shares else None, "fiscal_year_end": subs.get("fiscalYearEnd"),
           "industry_path": sic_path(sic, subs.get("sicDescription")),
           "bank": sic[:2] in ("60", "61") or sic[:3] in ("620", "621", "622", "671"),
           "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={facts_json.get('cik')}&type=10-K"}
    if subs.get("website"):
        out["website"] = subs["website"]
    return out


# SIC divisions (the first two digits), so a company's industry reads like the Indian sector › industry path
DIVISIONS = [(1, 9, "Agriculture"), (10, 14, "Resources"), (15, 17, "Construction"), (20, 39, "Manufacturing"),
             (40, 49, "Transportation & Communications"), (50, 51, "Wholesale Trade"), (52, 59, "Retail Trade"),
             (60, 67, "Finance"), (70, 89, "Services"), (91, 99, "Public Administration")]


def sic_path(sic: str, desc: str | None) -> list[str]:
    if not sic.isdigit():
        return []
    two = int(sic[:2])
    div = next((n for a, b, n in DIVISIONS if a <= two <= b), None)
    words = (desc or "").strip().title()
    return [x for x in (div, words) if x]


def documents(subs: dict, days: int = 730) -> list[dict]:
    """The company's annual and quarterly reports and earnings releases from the filing list, newest first:
    [{kind, title, at, url}], like the Indian filings' documents."""
    rec = ((subs or {}).get("filings") or {}).get("recent") or {}
    forms, dates, accs, docs = (rec.get(k) or [] for k in ("form", "filingDate", "accessionNumber", "primaryDocument"))
    items = rec.get("items") or [""] * len(forms)
    cik = int(subs.get("cik") or 0)
    cut = date.fromordinal(date.today().toordinal() - days).isoformat()
    out = []
    for form, at, acc, doc, it in zip(forms, dates, accs, docs, items):
        if at < cut:
            break
        kind = ("annual_report" if form in ("10-K", "20-F", "40-F") else "quarterly_report" if form == "10-Q"
                else "earnings_release" if form == "8-K" and "2.02" in str(it) else None)
        if not kind:
            continue
        folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
        out.append({"kind": kind, "title": {"annual_report": f"Annual report ({form})", "quarterly_report": "Quarterly report (10-Q)",
                                            "earnings_release": "Earnings release (8-K)"}[kind],
                    "at": at, "url": f"{folder}/{doc}", "folder": folder + "/", "form": form})
    return sorted(out, key=lambda d: d["at"], reverse=True)


class SEC(Source):
    name = "SEC EDGAR"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://data.sec.gov", per_minute=300, burst=8, transport=transport, timeout=30,
                         headers={"User-Agent": UA, "Accept": "application/json"})
        self._built: dict[str, tuple[float, dict]] = {}
        self._build_lock = threading.Lock()

    def _json(self, url: str) -> dict:
        """One uncached call: company facts run to megabytes, so the result is cached once built, not raw."""
        if time.time() < self._down_until:
            raise SourceError(self.name, f"{self.name} isn't answering right now. Try again in a minute.", busy=True)
        if not self.limit.take():
            raise SourceError(self.name, f"{self.name} is busy (our rate limit). Try again in a minute.", busy=True)
        try:
            try:
                r = self.http.get(url)
            except httpx.HTTPError as e:
                raise SourceError(self.name, f"Couldn't reach {self.name} ({e.__class__.__name__}).", busy=True) from None
            self.check(r)
            try:
                out = r.json()
            except ValueError:
                raise SourceError(self.name, f"{self.name} sent something that isn't data.", busy=True) from None
        except SourceError as e:
            self._failed(e.busy)
            raise
        self._failed(False, ok=True)
        return out

    def tickers(self) -> dict[str, dict]:
        """{TICKER: {cik, name}} for every company filing with the SEC; refreshed daily."""
        hit = self.cache.get("tickers")
        if hit is not None:
            return hit
        raw = self._json("https://www.sec.gov/files/company_tickers.json")
        out = {}
        for row in (raw.values() if isinstance(raw, dict) else raw):
            t = str(row.get("ticker") or "").upper()
            if t and row.get("cik_str") is not None:
                out.setdefault(t, {"cik": int(row["cik_str"]), "name": row.get("title") or t})
        if not out:
            raise SourceError(self.name, "The SEC's list of companies came back empty.", busy=True)
        self.cache.set("tickers", out, 86400)
        return out

    def cik(self, symbol: str) -> int:
        sym = re.sub(r"[^A-Z0-9.\-]", "", symbol.upper())
        hit = self.tickers().get(sym) or self.tickers().get(sym.replace(".", "-")) or self.tickers().get(sym.replace("-", "."))
        if not hit:
            raise SourceError(self.name, f"{sym} isn't a company that files with the SEC (funds and most foreign companies don't).")
        return hit["cik"]

    def submissions(self, cik: int, fresh: bool = False) -> dict:
        """The company's details and recent filing list, cached six hours (`fresh` asks again, for a results day)."""
        key = ("subs", cik)
        hit = None if fresh else self.cache.get(key)
        if hit is None:
            hit = self._json(f"/submissions/CIK{cik:010d}.json")
            recent = (hit.get("filings") or {}).get("recent") or {}
            keep = ("form", "filingDate", "accessionNumber", "primaryDocument", "items")
            hit = {**{k: hit.get(k) for k in ("cik", "name", "sic", "sicDescription", "fiscalYearEnd", "website", "tickers")},
                   "filings": {"recent": {k: recent.get(k) for k in keep}}}
            self.cache.set(key, hit, 6 * 3600)
        return hit

    def document(self, url: str, limit: int = 25 * 1024 * 1024) -> str:
        """The text of one document in the SEC's archive (www.sec.gov only), cached for a week."""
        from urllib.parse import urlparse
        if urlparse(url).hostname != "www.sec.gov" or not urlparse(url).path.startswith("/Archives/"):
            raise SourceError(self.name, "That isn't a document in the SEC's archive.")
        hit = self.cache.get(("doc", url))
        if hit is not None:
            return hit
        if not self.limit.take():
            raise SourceError(self.name, f"{self.name} is busy (our rate limit). Try again in a minute.", busy=True)
        try:
            with self.http.stream("GET", url) as r:
                self.check(r)
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > limit:
                        raise SourceError(self.name, "The filing is too large to read here.")
        except httpx.HTTPError as e:
            raise SourceError(self.name, f"Couldn't reach {self.name} ({e.__class__.__name__}).", busy=True) from None
        raw = bytes(buf).decode("utf-8", "replace")
        text = html_text(raw) if "<" in raw[:2000] else raw
        self.cache.set(("doc", url), text, 7 * 86400)
        return text


    def annual(self, d: dict) -> str:
        """A 10-K cut down to what an investor reads first: the business, the risk factors and management's discussion."""
        full = self.document(d["url"])
        parts = [(k, section(full, *SECTIONS[k])) for k in ("business", "risks", "mdna")]
        out = "\n\n".join(f"[{k.upper()}]\n{v}" for k, v in parts if len(v) > 500)
        return out or full[:120000]


    def release_doc(self, d: dict) -> tuple[str, str]:
        """(link, text) of an earnings 8-K's press release: the exhibit 99 file in the filing's folder (the 8-K itself
        is a cover page), so quotes link to the release they came from."""
        idx = self._json(d["folder"] + "index.json")
        names = [i.get("name", "") for i in ((idx.get("directory") or {}).get("item") or [])]
        ex = [n for n in names if re.search(r"ex-?99", n, re.I) and n.lower().endswith((".htm", ".html", ".txt"))]
        url = d["folder"] + sorted(ex)[0] if ex else d["url"]
        return url, self.document(url)

    def release(self, d: dict) -> str:
        return self.release_doc(d)[1]

    def company(self, symbol: str) -> dict:
        """The company's numbers in the deep dive's shape (cached six hours), with its filing list under "filings"."""
        cik = self.cik(symbol)
        with self._build_lock:
            hit = self._built.get(str(cik))
        if hit and time.time() - hit[0] < 6 * 3600:
            return hit[1]
        subs = self.submissions(cik)
        p = build(self._json(f"/api/xbrl/companyfacts/CIK{cik:010d}.json"), subs)
        p["symbol"] = symbol.upper()
        p["documents"] = documents(subs, days=5 * 366)      # five years: a deep read can look that far back
        with self._build_lock:
            if len(self._built) > 300:
                self._built.pop(next(iter(self._built)))
            self._built[str(cik)] = (time.time(), p)
        return p


def _latest(table: dict | None, label: str, skip_ttm: bool = False):
    rows = (table or {}).get("rows") or {}
    cols = (table or {}).get("cols") or []
    vals = rows.get(label) or []
    pairs = [(c, v) for c, v in zip(cols, vals) if v is not None and not (skip_ttm and str(c).upper() == "TTM")]
    return pairs[-1][1] if pairs else None


def ratios(p: dict, price: float | None, high: float | None = None, low: float | None = None) -> dict:
    """The headline ratios the Indian pages state, worked out from the filings and the share price: market cap
    ($ million), P/E on the last twelve months' profit, book value per share, ROE, ROCE and dividend yield."""
    shares = p.get("shares")
    mcap = price * shares / M if price and shares else None
    profit = _latest(p.get("pl"), "Net Profit")                   # the trailing twelve months when there are four quarters
    equity = _latest(p.get("balance"), "Equity")
    debt = _latest(p.get("balance"), "Borrowings") or 0
    fy_profit = _latest(p.get("pl"), "Net Profit", skip_ttm=True)
    ebitda = _latest(p.get("pl"), "Operating Profit", skip_ttm=True)
    dep = _latest(p.get("pl"), "Depreciation", skip_ttm=True) or 0
    divs = _latest(p.get("cashflow"), "Dividends paid")
    out = {"Current Price": price, "Market Cap": round(mcap, 1) if mcap else None,
           "Stock P/E": round(mcap / profit, 1) if mcap and profit and profit > 0 else None,
           "Book Value": round(equity * M / shares, 2) if equity and shares else None,
           "ROE": round(fy_profit / equity * 100, 1) if fy_profit is not None and equity and equity > 0 else None,
           "ROCE": round((ebitda - dep) / (equity + debt) * 100, 1) if ebitda is not None and equity and equity + debt > 0 else None,
           "Dividend Yield": round(abs(divs) / mcap * 100, 2) if divs and mcap else 0.0 if mcap else None}
    if high and low:
        out["High / Low"] = f"{high} / {low}"
    return {k: v for k, v in out.items() if v is not None}


# ---------- reading the filings themselves ----------
def html_text(html: str) -> str:
    """Plain text of an SEC HTML filing: inline XBRL tags, tables and styling flattened to readable lines."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "ix:header"]):
        t.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"[ \t ]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


SECTIONS = {   # 10-K parts worth reading: (start heading, where the part ends)
    "business": (r"item\s*1\.?\s*(?:—|-|:)?\s*business\b", r"\n\s*item\s*1a\.?\s"),
    "risks": (r"item\s*1a\.?\s*(?:—|-|:)?\s*risk\s+factors", r"\n\s*item\s*(?:1b|1c|2)\.?\s"),
    "mdna": (r"item\s*7\.?\s*(?:—|-|:)?\s*management.s\s+discussion", r"\n\s*item\s*(?:7a|8)\.?\s"),
}


def section(text: str, start: str, end: str, cap: int = 60000) -> str:
    """One part of a 10-K. The table of contents names every part too, so of all the places the heading appears,
    the one followed by the longest stretch before the next part is the part itself."""
    best = ""
    for m in re.finditer(start, text, re.I):
        e = re.search(end, text[m.end():], re.I)
        chunk = text[m.start(): m.end() + (e.start() if e else cap)]
        if len(chunk) > len(best):
            best = chunk
    return best[:cap]
