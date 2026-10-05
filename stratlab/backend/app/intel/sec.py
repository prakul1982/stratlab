"""US company fundamentals from the SEC's EDGAR system (free, no key): the numbers companies file in their 10-K and
10-Q reports (XBRL "company facts"), their industry (SIC code) and their list of filings.

The result has the same shape as the Indian company pages (see screener.parse), in US$ millions instead of ₹ crore,
so the deep dive, checklist, valuation and deck work on it unchanged. Two things are better than the Indian source:
capex is reported directly (no estimate) and cash is reported, so enterprise value can subtract it."""
import re
import threading
import time
from datetime import date, datetime, timedelta

import httpx

from .net import SizedDict, Source, SourceError

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
                "InterestRevenueCalculatedUsingEffectiveInterestMethod",
                # licence and collaboration income: the only revenue many drug developers have
                "RevenueFromCollaborativeArrangementExcludingRevenueFromContractWithCustomer", "LicensesRevenue",
                "LicenseAndServicesRevenue", "TechnologyServicesRevenue", "InterestIncomeOperating")
# ...and when no revenue line is tagged at all, the income statement's own arithmetic: gross profit plus the cost of
# sales, or operating profit plus total costs (each pair from the same period)
COST_OF_SALES = ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold", "CostOfSales")
GROSS_PROFIT = ("GrossProfit",)
TOTAL_COSTS = ("CostsAndExpenses",)
PRETAX = ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
          "ProfitLossBeforeTax")
INTEREST = ("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense", "FinanceCosts")
# a bank's revenue when it files no total: interest and dividend income plus everything else it earns (fees)
BANK_INTEREST = ("InterestAndDividendIncomeOperating", "InterestAndFeeIncomeLoansAndLeases")
BANK_OTHER = ("NoninterestIncome",)
NET_INCOME = ("NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "NetIncomeLossAvailableToCommonStockholdersBasic",
              "ProfitLoss", "IncomeLossFromContinuingOperations",
              "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
              "NetIncomeLossAvailableToCommonStockholdersDiluted", "IncomeLossFromContinuingOperationsAttributableToParent",
              "ProfitLossFromContinuingOperations", "NetIncomeLossAllocatedToLimitedPartners")
OPERATING = ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities")
DEPRECIATION = ("DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                "DepreciationAndAmortization", "CostDepreciationAmortizationAndDepletion", "Depreciation",
                "DepreciationAndAmortisationExpense", "AdjustmentsForDepreciationAndAmortisationExpense")
EPS = ("EarningsPerShareDiluted", "EarningsPerShareBasic", "DilutedEarningsLossPerShare", "BasicEarningsLossPerShare")
PPE = ("PropertyPlantAndEquipmentNet",
       "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
       "PropertyPlantAndEquipment", "RealEstateInvestmentPropertyNet", "OilAndGasPropertyFullCostMethodNet",
       "OilAndGasPropertySuccessfulEffortMethodNet", "MineralPropertiesNet")
EQUITY = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
          "PartnersCapital", "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest", "MembersEquity",
          "EquityAttributableToOwnersOfParent", "Equity")
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
         "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", "PurchaseOfPropertyPlantAndEquipment",
         # lessors' aircraft and equipment, buildings and machinery bought outright, and software built or bought
         "PaymentsToAcquireEquipmentOnLease", "PaymentsToAcquireMachineryAndEquipment", "PaymentsToAcquireBuildings",
         "PaymentsForConstructionInProcess", "PaymentsToAcquireRealEstateHeldForInvestment", "PaymentsToAcquireTimberlands",
         "PaymentsToAcquireOtherProductiveAssets", "PaymentsToDevelopSoftware", "PaymentsForSoftware",
         "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
         "PurchaseOfInvestmentProperty")
DIVIDENDS = ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "DividendsPaidClassifiedAsFinancingActivities",
             "DividendsPaid")
# debt: long-term debt including the part due within a year, or its two halves, plus short-term borrowings
DEBT_TOTAL = ("LongTermDebt", "DebtLongtermAndShorttermCombinedAmount", "Borrowings")
DEBT_PARTS = (("LongTermDebtNoncurrent",), ("LongTermDebtCurrent", "DebtCurrent"))
DEBT_SHORT = ("ShortTermBorrowings", "CommercialPaper")
# every concept a balance sheet's debt can sit under: a report with none of them tagged shows no debt
DEBT_ANY = DEBT_TOTAL + DEBT_PARTS[0] + DEBT_PARTS[1] + DEBT_SHORT + (
    "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent", "LongTermNotesPayable",
    "NotesPayable", "NotesPayableCurrent", "ConvertibleNotesPayable", "ConvertibleNotesPayableCurrent", "SeniorNotes",
    "SecuredDebt", "UnsecuredDebt", "LineOfCredit", "LongTermLineOfCredit", "OtherLongTermDebt", "OtherBorrowings",
    "ShortTermBankLoansAndNotesPayable", "DebtInstrumentCarryingAmount", "FinanceLeaseLiability", "LoansPayable",
    "CurrentBorrowings", "NoncurrentBorrowings", "NotesPayableRelatedPartiesClassifiedCurrent", "DueToRelatedPartiesCurrent")
# the share count when a report's cover page doesn't give one the facts can read (companies with two classes of shares
# give a count per class): the balance sheet's, else the year's diluted average
SHARES = ("CommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding",
          "WeightedAverageNumberOfSharesOutstandingBasic", "NumberOfSharesOutstanding", "AdjustedWeightedAverageShares",
          "WeightedAverageShares")

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


def revenue(facts: dict, kind: str, unit: str = "USD") -> dict[str, float]:
    """{period end: revenue} for "annual" or "quarter": the largest top-line figure filed for each period, else the
    first narrower one, else a bank's interest and other income, else the income statement's own arithmetic (gross
    profit plus cost of sales, or operating profit plus total costs)."""
    read = (lambda cs: flows(facts, cs, "annual", unit)) if kind == "annual" else (lambda cs: quarterly(facts, cs, unit))   # noqa: E731
    out: dict[str, float] = {}
    for c in TOP_LINE:
        for end, v in read((c,)).items():
            if end not in out or v > out[end]:
                out[end] = v
    for end, v in read(REVENUE_ELSE).items():
        out.setdefault(end, v)
    interest, other = read(BANK_INTEREST), read(BANK_OTHER)
    for end, v in interest.items():           # a bank: interest income plus fees and other income
        out.setdefault(end, v + other.get(end, 0))
    gross, cost = read(GROSS_PROFIT), read(COST_OF_SALES)
    for end, v in gross.items():
        if end in cost:
            out.setdefault(end, v + cost[end])
    op, costs = read(OPERATING), read(TOTAL_COSTS)
    for end, v in op.items():
        if end in costs:
            out.setdefault(end, v + costs[end])
    return out


CURRENCY_NAMES = {"CAD": "Canadian dollars", "EUR": "euros", "GBP": "British pounds", "BRL": "Brazilian reais",
                  "JPY": "Japanese yen", "CNY": "Chinese yuan", "ARS": "Argentine pesos", "AUD": "Australian dollars",
                  "CHF": "Swiss francs", "MXN": "Mexican pesos", "INR": "Indian rupees", "HKD": "Hong Kong dollars",
                  "KRW": "South Korean won", "TWD": "Taiwan dollars", "SEK": "Swedish kronor", "DKK": "Danish kroner",
                  "NOK": "Norwegian kroner", "ILS": "Israeli shekels", "CLP": "Chilean pesos", "COP": "Colombian pesos",
                  "PEN": "Peruvian soles", "ZAR": "South African rand", "IDR": "Indonesian rupiah", "PHP": "Philippine pesos",
                  "SGD": "Singapore dollars", "NZD": "New Zealand dollars", "TRY": "Turkish lira", "RUB": "Russian roubles"}


def currency(facts: dict) -> str | None:
    """The currency a company's results are filed in, when it isn't US dollars (a foreign filer, mostly under IFRS):
    read from the units its revenue or profit is reported in."""
    for ns in ("ifrs-full", "us-gaap"):
        for concept in TOP_LINE + NET_INCOME:
            units = ((facts.get(ns) or {}).get(concept) or {}).get("units") or {}
            other = [u for u in units if re.fullmatch(r"[A-Z]{3}", u) and u != "USD"]
            if units and "USD" not in units and other:
                return other[0]
    return None


def _accns(facts: dict, concepts: tuple, unit: str = "USD") -> set[str]:
    """The filings (accession numbers) that tag any of these concepts, for any period."""
    return {f["accn"] for c in concepts for f in _facts(facts, c, unit) if f.get("accn")}


def _accns_for(facts: dict, concepts: tuple, end: str, unit: str = "USD", instant: bool = False) -> set[str]:
    """The annual reports that give one of these concepts for the year ending `end` (a flow over about a year, or
    with `instant` a balance on that day)."""
    out = set()
    for c in concepts:
        for f in _facts(facts, c, unit):
            if f.get("end") != end or f.get("form") not in ANNUAL or not f.get("accn"):
                continue
            if instant and not f.get("start") or not instant and f.get("start") and 340 <= _days(f["start"], end) <= 380:
                out.add(f["accn"])
    return out


def _not_in_report(facts: dict, have: tuple, missing: tuple, end: str, unit: str, instant: bool = False) -> bool:
    """True when the annual reports that give `have` for the year ending `end` tag none of `missing` at all, for any
    period: the line isn't in the statements (no revenue, no capex, no debt), rather than tagged in a way not read."""
    reports = _accns_for(facts, have, end, unit, instant)
    return bool(reports) and not reports & _accns(facts, missing, unit)


def _debt(facts: dict, unit: str = "USD") -> dict[str, float]:
    total = instants(facts, DEBT_TOTAL, unit)
    parts = [instants(facts, p, unit) for p in DEBT_PARTS]
    short = instants(facts, DEBT_SHORT, unit)
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


# a report that tags any of these has a revenue line (cost of sales too: there are no costs of sales without sales)
ALL_REVENUE = TOP_LINE + REVENUE_ELSE + BANK_INTEREST + BANK_OTHER + GROSS_PROFIT + COST_OF_SALES

# what kind of company the filings describe, where the usual business measures don't fit: real estate investment trusts
# (SEC industry code 6798) and business development companies (BDCs: listed lenders to private companies, regulated as
# investment companies, which file N-2 prospectuses beside their 10-Ks and list their holdings at fair value)
BDC_FORMS = {"N-2", "N-2/A", "N-2ASR", "N-2MEF", "N-2 POSASR", "POS 8C", "497", "N-54A", "N-54C", "N-6F", "N-23C3A",
             "N-23C-2"}
KIND_PATHS = {"bdc": ["Finance", "Business Development Company"], "reit": ["Finance", "Real Estate Investment Trusts"]}
NO_MARGIN = {"reit": "Operating margin isn't shown for a real estate investment trust: depreciation of its property and "
                     "gains on property sales swing its operating profit, so the margin doesn't measure the business.",
             "bdc": "Operating margin isn't shown for a business development company: its income is interest and "
                    "gains on its loans and investments, so a margin on it doesn't measure the business."}


def _forms(subs: dict | None) -> set[str]:
    return set((((subs or {}).get("filings") or {}).get("recent") or {}).get("form") or [])


def company_kind(subs: dict | None, facts: dict | None = None) -> str | None:
    """"reit", "bdc" or None (an operating company), from the SEC industry code, the forms filed and the facts."""
    subs = subs or {}
    sic = str(subs.get("sic") or "")
    if sic == "6798":
        return "reit"
    forms = _forms(subs)
    holdings = bool(((facts or {}).get("us-gaap") or {}).get("InvestmentOwnedAtFairValue"))
    if forms & {"10-K", "10-Q"} and (forms & BDC_FORMS or (holdings and sic in ("", "6726", "6799"))):
        return "bdc"
    return None


# why the SEC has no results to show for a company, in plain words: a fact about the company, never a fault
FUND_FORMS = {"N-CSR", "N-CSRS", "N-CSR/A", "N-CEN", "NPORT-P", "NPORT-EX", "N-PX", "N-30D", "N-30B-2", "N-Q", "N-1A",
              "485BPOS", "485APOS", "497K", "N-8A", "40-17G"}
REG_A_FORMS = {"1-K", "1-K/A", "1-SA", "1-U", "1-A", "1-A/A", "1-A POS", "253G2", "1-Z"}
REGISTERING = {"S-1", "S-1/A", "F-1", "F-1/A", "10-12B", "10-12G", "10-12B/A", "10-12G/A", "S-4", "F-4", "424B4", "DRS", "S-11"}
DEREGISTERED = {"15-12G", "15-12B", "15-15D", "15F-12G", "15F-12B", "15F-15D"}
BANK_SIC = {"6021", "6022", "6029", "6035", "6036"}
NO_RESULTS = {
    "fund": "A fund: it files fund reports with the SEC (its holdings and net asset value), not company results, so "
            "there are no business numbers to show.",
    "home": "Files its results with its home-country regulator, not the SEC, so they can't be shown here.",
    "bank": "A bank that files its results with its banking regulator, not the SEC, so they can't be shown here.",
    "reg_a": "Reports under the SEC's small-offering rules (Regulation A), whose reports aren't filed as structured "
             "data, so its results can't be shown here.",
    "no_xbrl": "Files its annual report with the SEC, but not as structured data (XBRL), so its results can't be shown here.",
    "quarters": "Only quarterly results filed so far: the first annual report isn't out yet, so its results can't be shown here.",
    "new": "Registered with the SEC recently: no annual results filed yet, so they can't be shown here.",
    "stopped": "Has deregistered from SEC reporting, so its results can't be shown here.",
    "none": "Doesn't file annual results with the SEC (no 10-K, 20-F or 40-F), so they can't be shown here.",
}
UNREAD = "The company's annual reports are filed as data, but no revenue or profit could be read from them."


def foreign_filer(subs: dict) -> bool:
    """A company based or incorporated outside the US, from the SEC's record of it: its business address marked
    foreign, or a state code for a country or a Canadian province (a letter and a digit: A1 Alberta, X0 the UK)."""
    addr = ((subs.get("addresses") or {}).get("business") or {})
    codes = (addr.get("stateOrCountry"), subs.get("stateOfIncorporation"))
    return bool(addr.get("isForeignLocation")) or any(re.fullmatch(r"[A-Z][0-9]", str(c or "")) for c in codes)


def foreign_otc(symbol: str) -> bool:
    """A foreign company's shares traded over the counter: five letters ending in F (ordinary shares) or Y (ADRs)."""
    return bool(re.fullmatch(r"[A-Z]{4}[FY]", str(symbol or "").upper()))


def no_results(subs: dict | None, facts: dict | None = None, symbol: str = "") -> str:
    """Why there are no annual results to show, from what the company files with the SEC: one of NO_RESULTS."""
    subs = subs or {}
    forms = _forms(subs)
    annual = forms & set(ANNUAL)
    if forms & FUND_FORMS or str(subs.get("sic") or "") in ("6722", "6726") and not annual:
        return NO_RESULTS["fund"]
    cur = currency(facts or {}) or "USD"
    if facts and any(f.get("form") in ANNUAL for ns in ("us-gaap", "ifrs-full") for c in (facts.get(ns) or {}).values()
                     for rows in (c.get("units") or {}).values() for f in rows):
        return UNREAD                         # figures filed as data, but no revenue or profit among them: our gap
    if facts and (quarterly(facts, NET_INCOME, cur) or revenue(facts, "quarter", cur)):
        return NO_RESULTS["quarters"]
    if annual:
        return NO_RESULTS["no_xbrl"]
    if forms & REG_A_FORMS:
        return NO_RESULTS["reg_a"]
    if subs.get("foreign") or foreign_otc(symbol) or forms & {"6-K", "F-6", "SUPPL", "12G3-2B"}:
        return NO_RESULTS["home"]
    if str(subs.get("sic") or "") in BANK_SIC:
        return NO_RESULTS["bank"]
    if forms & DEREGISTERED:
        return NO_RESULTS["stopped"]
    if forms & REGISTERING:
        return NO_RESULTS["new"]
    return NO_RESULTS["none"]


def build(facts_json: dict, subs: dict | None = None, years: int = 12, symbol: str = "") -> dict:
    """The company in the deep dive's shape: P&L, balance sheet and cash flow by year, the last twelve quarters,
    and the industry path, in millions of the currency the company reports in (US dollars for nearly all)."""
    facts = facts_json.get("facts") or {}
    subs = subs or {}
    cur = currency(facts) or "USD"
    rev_a, rev_q = revenue(facts, "annual", cur), revenue(facts, "quarter", cur)
    ni_a, ni_q = flows(facts, NET_INCOME, "annual", cur), quarterly(facts, NET_INCOME, cur)
    op_a, op_q = flows(facts, OPERATING, "annual", cur), quarterly(facts, OPERATING, cur)
    # many companies show no operating profit line (Alcoa, HCA): then profit before tax with the interest it paid added
    # back (EBIT, as EBITDA is usually defined), else revenue less total costs
    read_a = lambda cs: flows(facts, cs, "annual", cur)     # noqa: E731
    read_q = lambda cs: quarterly(facts, cs, cur)           # noqa: E731
    sic = str(subs.get("sic") or "")
    lender = sic[:2] in ("60", "61") or sic[:3] in ("620", "621", "622", "671")     # interest is a lender's cost of sales
    for op, rev, read in ((op_a, rev_a, read_a), (op_q, rev_q, read_q)):
        pretax, interest, costs = ({}, {}, {}) if lender else (read(PRETAX), read(INTEREST), read(TOTAL_COSTS))
        for e, v in pretax.items():
            if e not in op and e in interest:
                op[e] = v + interest[e]
        for e, c in costs.items():
            if e not in op and e in rev:
                op[e] = rev[e] - c
    dep_a, dep_q = flows(facts, DEPRECIATION, "annual", cur), quarterly(facts, DEPRECIATION, cur)
    # operating profit as on the Indian pages: before depreciation (EBITDA), so margins and EV/EBITDA mean the same
    ebitda = lambda op, dep: (op + dep) if op is not None and dep is not None else None   # noqa: E731
    eb_a = {e: ebitda(op_a.get(e), dep_a.get(e)) for e in op_a}
    eb_q = {e: ebitda(op_q.get(e), dep_q.get(e)) for e in op_q}
    eps_a = flows(facts, EPS, "annual", unit=f"{cur}/shares")
    cfo_a, cfi_a = flows(facts, CFO, "annual", cur), flows(facts, CFI, "annual", cur)
    capex_a, div_a = flows(facts, CAPEX, "annual", cur), flows(facts, DIVIDENDS, "annual", cur)
    ppe, debt, equity, cash = instants(facts, PPE, cur), _debt(facts, cur), instants(facts, EQUITY, cur), instants(facts, CASH, cur)

    def no_revenue_line(e: str) -> bool:      # the year's annual report has no revenue line at all
        return e in ni_a and e not in rev_a and _not_in_report(facts, NET_INCOME, ALL_REVENUE, e, cur)

    ends = sorted(set(rev_a) | set(ni_a))
    # the oldest years can come only from a note or another statement that goes back further than the income
    # statement (revenue by segment over three years, profit in the statement of equity): revenue without a profit, or
    # a profit without the revenue the same report gives for other years. Those years are left out.
    while len(ends) > 1 and (ends[0] not in ni_a and any(e in ni_a for e in ends[1:])
                             or ends[0] not in rev_a and not no_revenue_line(ends[0]) and any(e in rev_a for e in ends[1:])):
        ends.pop(0)
    ends = ends[-years:]
    if not ends:
        raise SourceError(SEC.name, no_results(subs, facts, symbol))
    kind = company_kind(subs, facts)
    no_revenue = [_label(e) for e in ends if no_revenue_line(e)]
    for i, e in enumerate(ends):
        # a year whose cash flow statement shows no purchases of plant and equipment at all, and whose plant didn't grow:
        # capex was nil, not missing
        grew = i > 0 and (ppe.get(e) or 0) > (ppe.get(ends[i - 1]) or 0) > 0
        if e not in capex_a and e in cfo_a and not grew and _not_in_report(facts, CFO, CAPEX, e, cur):
            capex_a[e] = 0.0
        # ...and a balance sheet with no borrowings on it, from a report with no interest expense either: no debt
        if e not in debt and e in equity and _not_in_report(facts, EQUITY, DEBT_ANY + INTEREST, e, cur, instant=True):
            debt[e] = 0.0
    cols = [_label(e) for e in ends]
    no_margin = kind in NO_MARGIN
    margin = lambda op, rev: round(op / rev * 100, 1) if op is not None and rev and not no_margin else None   # noqa: E731
    eps_label = "EPS in $" if cur == "USD" else f"EPS in {cur}"
    ttm_rev, ttm_ni, ttm_op, ttm_dep = _ttm(rev_q), _ttm(ni_q), _ttm({e: v for e, v in eb_q.items() if v is not None}), _ttm(dep_q)
    has_ttm = ttm_rev is not None and ttm_ni is not None and max(rev_q) > ends[-1]
    pl_rows = {"Sales": [_mn(rev_a.get(e)) for e in ends],
               "Operating Profit": [_mn(eb_a.get(e)) for e in ends],
               "OPM %": [margin(eb_a.get(e), rev_a.get(e)) for e in ends],
               "Depreciation": [_mn(dep_a.get(e)) for e in ends],
               "Net Profit": [_mn(ni_a.get(e)) for e in ends],
               eps_label: [eps_a.get(e) for e in ends]}
    pl_cols = list(cols)
    if has_ttm:
        pl_cols.append("TTM")
        extra = {"Sales": _mn(ttm_rev), "Operating Profit": _mn(ttm_op), "OPM %": margin(ttm_op, ttm_rev),
                 "Depreciation": _mn(ttm_dep), "Net Profit": _mn(ttm_ni), eps_label: None}
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
           "basis": "consolidated", "unit": "$ million" if cur == "USD" else f"{cur} million", "currency": cur, "region": "US",
           "cik": facts_json.get("cik"), "sic": sic, "shares": shares[1] if shares else None, "fiscal_year_end": subs.get("fiscalYearEnd"),
           "industry_path": sic_path(sic, subs.get("sicDescription")) or KIND_PATHS.get(kind or "", []),
           "bank": kind is None and lender,
           "kind": kind, "no_revenue": no_revenue,
           "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={facts_json.get('cik')}&type=10-K"}
    if no_margin:
        out["margin_note"] = NO_MARGIN[kind]
    if cur != "USD":
        out["currency_name"] = CURRENCY_NAMES.get(cur, cur)
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
        kind = ("annual_report" if form in ("10-K", "10-KT", "20-F", "40-F") else "quarterly_report" if form == "10-Q"
                else "earnings_release" if form == "8-K" and "2.02" in str(it) else None)
        if not kind:
            continue
        folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
        out.append({"kind": kind, "title": {"annual_report": f"Annual report ({form})", "quarterly_report": "Quarterly report (10-Q)",
                                            "earnings_release": "Earnings release (8-K)"}[kind],
                    "at": at, "url": f"{folder}/{doc}", "folder": folder + "/", "form": form})
    return sorted(out, key=lambda d: d["at"], reverse=True)


class SEC(Source):
    name = "The SEC"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://data.sec.gov", per_minute=300, burst=8, transport=transport, timeout=30,
                         headers={"User-Agent": UA, "Accept": "application/json"})
        self._built = SizedDict(max_items=300, max_bytes=64 * 1024 * 1024)   # built companies, bounded in memory
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
                raise SourceError(self.name, f"Couldn't reach {self.name.replace('The ', 'the ', 1)} ({e.__class__.__name__}).", busy=True) from None
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
        """The company's SEC number for a ticker as exchanges and quote screens write it: share classes and preferred
        series with a dot, a dash or a slash (BRK.B, BRK-B, BRK/B), the way the SEC's list writes them (BRK-B)."""
        sym = re.sub(r"[^A-Z0-9.\-/]", "", symbol.upper())
        names = self.tickers()
        pref = re.sub(r"[./-]PR?([A-Z]?)$", r"-P\1", sym)           # preferred series: BAC.PRL, BAC/PL → BAC-PL
        hit = next((names[t] for t in dict.fromkeys((sym, *(re.sub(r"[./-]", x, sym) for x in "-."), pref))
                    if t in names), None)
        if not hit:
            raise SourceError(self.name, f"{sym} isn't a company that files with the SEC (funds and most foreign companies don't).")
        return hit["cik"]

    def submissions(self, cik: int, fresh: bool = False) -> dict:
        """The company's details and recent filing list, cached six hours (`fresh` asks again, for a results day)."""
        key = ("subs", cik)
        hit = None if fresh else self.cache.get(key)
        if hit is None:
            hit = self._json(f"/submissions/CIK{cik:010d}.json")
            recent = dict((hit.get("filings") or {}).get("recent") or {})
            keep = ("form", "filingDate", "accessionNumber", "primaryDocument", "items")
            # the recent list holds a year or the last thousand filings: a bank filing notes every day fills it in months,
            # leaving its 10-K and 10-Qs in the next page of the list, which is read too when the list stops short
            older = ((hit.get("filings") or {}).get("files") or [{}])[0].get("name")
            cut = (date.today() - timedelta(days=2 * 366)).isoformat()
            if older and recent.get("filingDate") and min(recent["filingDate"]) > cut:
                try:
                    more = self._json(f"/submissions/{older}")
                    n = len(more.get("form") or [])
                    for k in keep:
                        recent[k] = list(recent.get(k) or []) + list(more.get(k) or [""] * n)
                except SourceError:
                    pass                          # the recent list alone, rather than nothing
            hit = {**{k: hit.get(k) for k in ("cik", "name", "sic", "sicDescription", "fiscalYearEnd", "website", "tickers")},
                   "foreign": foreign_filer(hit), "filings": {"recent": {k: recent.get(k) for k in keep}}}
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
            raise SourceError(self.name, f"Couldn't reach {self.name.replace('The ', 'the ', 1)} ({e.__class__.__name__}).", busy=True) from None
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
            if hit[1] is None:             # no results to show, found a moment ago: the same reason again
                raise SourceError(self.name, hit[2])
            return hit[1]
        try:
            try:
                subs = self.submissions(cik)
            except SourceError as e:
                if e.busy:
                    raise
                subs = {}                         # no filing list on record: classified from the ticker alone
            try:
                facts = self._json(f"/api/xbrl/companyfacts/CIK{cik:010d}.json")
            except SourceError as e:
                if e.busy:
                    raise
                raise SourceError(self.name, no_results(subs, None, symbol)) from None   # no figures filed as data at all
            p = build(facts, subs, symbol=symbol.upper())
        except SourceError as e:
            if not e.busy:
                with self._build_lock:
                    self._built[str(cik)] = (time.time(), None, str(e))
            raise
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


def usd_rate(p: dict) -> float | None:
    """US dollars to one unit of the currency the company reports in: 1 for dollars, today's rate for another
    currency when it was read (see with_fx), else None."""
    if (p.get("currency") or "USD") == "USD":
        return 1.0
    return (p.get("fx") or {}).get("rate")


def with_fx(p: dict, rate_of) -> dict:
    """A company reporting in another currency, with today's rate to US dollars (`rate_of(currency)`, dollars to one
    unit; it may fail) and the note that says what is in which currency. The figures themselves stay as reported:
    margins, growth and returns don't depend on the currency, and only ratios against the dollar price convert."""
    cur = p.get("currency") or "USD"
    if cur == "USD":
        return p
    p = dict(p)
    try:
        rate = float(rate_of(cur) or 0) or None
    except Exception:                      # no rate today: the reported figures still stand, price ratios don't
        rate = None
    name = p.get("currency_name") or cur
    note = (f"The company reports in {name} ({cur}): its figures here are in {cur} million, as filed. The share price "
            "is in US dollars, so market value, P/E, price to book and dividend yield convert the reported figures ")
    if rate:
        p["fx"] = {"rate": rate, "pair": f"{cur}/USD", "at": date.today().isoformat()}
        note += f"to dollars at today's rate ({_rate_text(cur, rate)})."
    else:
        p.pop("fx", None)
        note += "to dollars at today's rate, which couldn't be read just now, so they aren't shown."
    p["currency_note"] = note
    return p


def _rate_text(cur: str, rate: float) -> str:
    """"1 CAD = 0.7300 USD", or for a currency worth a cent or less "1 USD = 147.20 JPY"."""
    return f"1 {cur} = {rate:.4f} USD" if rate >= 0.01 else f"1 USD = {1 / rate:,.2f} {cur}"


def ratios(p: dict, price: float | None, high: float | None = None, low: float | None = None) -> dict:
    """The headline ratios the Indian pages state, worked out from the filings and the share price: market cap
    ($ million), P/E on the last twelve months' profit, book value per share, ROE, ROCE and dividend yield.
    The share price is in dollars: a company reporting in another currency has its profit, book and dividends turned
    into dollars at today's rate for the ratios against the price; without the rate those ratios are left out."""
    shares = p.get("shares")
    mcap = price * shares / M if price and shares else None
    fx = usd_rate(p)
    usd = lambda v: v * fx if v is not None and fx else None    # noqa: E731
    profit = usd(_latest(p.get("pl"), "Net Profit"))              # the trailing twelve months when there are four quarters
    equity = _latest(p.get("balance"), "Equity")
    debt = _latest(p.get("balance"), "Borrowings") or 0
    fy_profit = _latest(p.get("pl"), "Net Profit", skip_ttm=True)
    ebitda = _latest(p.get("pl"), "Operating Profit", skip_ttm=True)
    dep = _latest(p.get("pl"), "Depreciation", skip_ttm=True) or 0
    divs = usd(_latest(p.get("cashflow"), "Dividends paid"))
    book = usd(equity)
    out = {"Current Price": price, "Market Cap": round(mcap, 1) if mcap else None,
           "Stock P/E": round(mcap / profit, 1) if mcap and profit and profit > 0 else None,
           "Book Value": round(book * M / shares, 2) if book and shares else None,
           "ROE": round(fy_profit / equity * 100, 1) if fy_profit is not None and equity and equity > 0 else None,
           "ROCE": round((ebitda - dep) / (equity + debt) * 100, 1) if ebitda is not None and equity and equity + debt > 0 else None,
           "Dividend Yield": round(abs(divs) / mcap * 100, 2) if divs and mcap else 0.0 if mcap and fx else None}
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
