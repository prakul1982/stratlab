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
REVENUE_ELSE = ("RevenuesNetOfInterestExpense",      # a bank's or broker's total, before any part of it (lease income)
                "SalesRevenueGoodsNet", "SalesRevenueServicesNet", "RegulatedAndUnregulatedOperatingRevenue",
                "ElectricUtilityRevenue", "RealEstateRevenueNet", "OperatingLeaseLeaseIncome",
                "OperatingLeasesIncomeStatementLeaseRevenue", "PremiumsEarnedNet",
                "RevenuesExcludingInterestAndDividends", "GrossInvestmentIncomeOperating", "InvestmentIncomeInterestAndDividend",
                "OilAndGasRevenue", "RevenueMineralSales", "HealthCareOrganizationRevenue", "ContractsRevenue",
                "FinancialServicesRevenue", "RevenueFromSaleOfGoods", "RevenueFromRenderingOfServices",
                "InterestRevenueCalculatedUsingEffectiveInterestMethod",
                # licence and collaboration income: the only revenue many drug developers have
                "RevenueFromCollaborativeArrangementExcludingRevenueFromContractWithCustomer", "LicensesRevenue",
                "LicenseAndServicesRevenue", "TechnologyServicesRevenue",
                # advisory and investment banking fees; IFRS airlines, shipowners and telecoms name the service sold
                "RegulatedOperatingRevenue", "RegulatedOperatingRevenueGas", "RegulatedOperatingRevenueElectric",
                "InvestmentBankingRevenue", "RevenueAndOperatingIncome", "RevenueFromRenderingOfTransportServices",
                "RevenueFromRenderingOfTelecommunicationServices")
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
BANK_INTEREST = ("InterestAndDividendIncomeOperating", "InterestIncomeOperating", "InterestAndFeeIncomeLoansAndLeases",
                 "InterestAndFeeIncomeLoansAndLeasesHeldInPortfolio", "RevenueFromInterest")
BANK_OTHER = ("NoninterestIncome", "FeeAndCommissionIncome")
NET_INCOME = ("NetIncomeLoss", "ProfitLossAttributableToOwnersOfParent", "NetIncomeLossAvailableToCommonStockholdersBasic",
              "ProfitLoss", "IncomeLossFromContinuingOperations",
              "IncomeLossFromContinuingOperationsIncludingPortionAttributableToNoncontrollingInterest",
              "NetIncomeLossAvailableToCommonStockholdersDiluted", "IncomeLossFromContinuingOperationsAttributableToParent",
              "ProfitLossFromContinuingOperations", "NetIncomeLossAllocatedToLimitedPartners")
OPERATING = ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities")
DEPRECIATION = ("DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                "DepreciationAndAmortization", "CostDepreciationAmortizationAndDepletion", "Depreciation",
                "DepreciationAndAmortisationExpense", "AdjustmentsForDepreciationAndAmortisationExpense",
                "UtilitiesOperatingExpenseDepreciationAndAmortization")
# ...an IFRS filer that gives its depreciation and amortisation only in parts (AstraZeneca): their sum, else the cash
# flow add-back that includes impairments
DEPRECIATION_PARTS = ("DepreciationPropertyPlantAndEquipment", "DepreciationRightofuseAssets",
                      "AmortisationIntangibleAssetsOtherThanGoodwill")
DEPRECIATION_LAST = ("AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",)
EPS = ("EarningsPerShareDiluted", "EarningsPerShareBasic", "DilutedEarningsLossPerShare", "BasicEarningsLossPerShare")
PPE = ("PropertyPlantAndEquipmentNet",
       "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
       "PropertyPlantAndEquipment", "RealEstateInvestmentPropertyNet", "OilAndGasPropertyFullCostMethodNet",
       "OilAndGasPropertySuccessfulEffortMethodNet", "MineralPropertiesNet")
EQUITY = ("StockholdersEquity", "PartnersCapital", "MembersEquity", "EquityAttributableToOwnersOfParent")
# ...or the total with the minority shareholders' part in it, less that part (see _equity)
EQUITY_TOTAL = ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest", "Equity")
MINORITY = ("MinorityInterest", "NoncontrollingInterests")
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
         "PaymentsToAcquireEquipmentOnLease", "PaymentsForFlightEquipment", "PaymentsToAcquireMachineryAndEquipment", "PaymentsToAcquireBuildings",
         "PaymentsForConstructionInProcess", "PaymentsToAcquireRealEstateHeldForInvestment", "PaymentsToAcquireTimberlands",
         "PaymentsToAcquireOtherProductiveAssets", "PaymentsToDevelopSoftware", "PaymentsForSoftware",
         "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
         "PurchaseOfInvestmentProperty")
DIVIDENDS = ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "DividendsPaidClassifiedAsFinancingActivities",
             "DividendsPaid")
# debt: long-term debt including the part due within a year, or its two halves, plus short-term borrowings
DEBT_TOTAL = ("LongTermDebt", "DebtLongtermAndShorttermCombinedAmount", "Borrowings")
DEBT_PARTS = (("LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"),      # the latter: due after a year (Exxon)
              ("LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent", "DebtCurrent"))
DEBT_SHORT = ("ShortTermBorrowings", "CommercialPaper")
IFRS_DEBT_LINES = ("NoncurrentPortionOfNoncurrentBondsIssued", "CurrentBondsIssuedAndCurrentPortionOfNoncurrentBondsIssued",
                   "LongtermBorrowings", "CurrentPortionOfLongtermBorrowings", "ShorttermBorrowings")
# every concept a balance sheet's debt can sit under: a report with none of them tagged shows no debt
DEBT_ANY = DEBT_TOTAL + DEBT_PARTS[0] + DEBT_PARTS[1] + DEBT_SHORT + (
    "LongTermDebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligationsCurrent", "LongTermNotesPayable",
    "NotesPayable", "NotesPayableCurrent", "ConvertibleNotesPayable", "ConvertibleNotesPayableCurrent", "SeniorNotes",
    "SecuredDebt", "UnsecuredDebt", "LineOfCredit", "LongTermLineOfCredit", "OtherLongTermDebt", "OtherBorrowings",
    "ShortTermBankLoansAndNotesPayable", "DebtInstrumentCarryingAmount", "FinanceLeaseLiability", "LoansPayable",
    "CurrentBorrowings", "NoncurrentBorrowings", "NotesPayableRelatedPartiesClassifiedCurrent", "DueToRelatedPartiesCurrent")
DEBT_ANY += IFRS_DEBT_LINES
# the share count when a report's cover page doesn't give one the facts can read (companies with two classes of shares
# give a count per class): the balance sheet's, else the year's diluted average
SHARES = ("CommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding",
          "WeightedAverageNumberOfSharesOutstandingBasic", "NumberOfSharesOutstanding", "AdjustedWeightedAverageShares",
          "WeightedAverageShares")
# ...the shares outstanding on a balance-sheet day, every class together (no weighted averages)
SHARES_HELD = ("CommonStockSharesOutstanding", "NumberOfSharesOutstanding")

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
NON_COMMON = re.compile(r"[-./](?:P[A-Z]?|PR[A-Z]?|W[A-Z]?|WT[A-Z]?|WS[A-Z]?|U|UN|R|RT|RI)$")


def non_common(t: str) -> bool:
    """A preferred share, warrant, unit or right by its ticker alone, whether or not its common stock is listed too."""
    return bool(NON_COMMON.search(str(t or "").upper()))


def price_symbol(t: str) -> str:
    """A US ticker as quote screens write it for prices: share classes and preferred series with a dash (BRK.B and
    BRK/B → BRK-B; BAC.PRL, BAC/PL and BAC-PRL → BAC-PL)."""
    t = str(t or "").upper().strip()
    t = re.sub(r"[./-]PR?([A-Z]?)$", r"-P\1", t) if re.search(r"[./-]PR?[A-Z]?$", t) else t
    return re.sub(r"[./]", "-", t)


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
        if end in cost and v + cost[end] > 0:        # a total of nothing or less is costs the line doesn't cover, not sales
            out.setdefault(end, v + cost[end])
    op, costs = read(OPERATING), read(TOTAL_COSTS)
    for end, v in op.items():
        if end in costs and v + costs[end] > 0:
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
    the unit of its latest annual revenue or profit. A stray old figure in another unit (a few years' profit once filed
    in Canadian dollars) or an interim figure in dollars beside euro annual results doesn't change it."""
    latest: dict[str, str] = {}              # unit -> the latest year end it is given for, in an annual report
    seen: set[str] = set()
    for ns in ("ifrs-full", "us-gaap"):
        for concept in TOP_LINE + NET_INCOME:
            for unit, rows in (((facts.get(ns) or {}).get(concept) or {}).get("units") or {}).items():
                if not re.fullmatch(r"[A-Z]{3}", unit):
                    continue
                seen.add(unit)
                for f in rows:
                    if f.get("start") and f.get("form") in ANNUAL and 340 <= _days(f["start"], f["end"]) <= 380:
                        latest[unit] = max(latest.get(unit, ""), f["end"])
    if latest:
        best = max(latest, key=lambda u: (latest[u], u != "USD"))     # a tie: the filer's own currency, not the translation
        return None if best == "USD" else best
    other = sorted(seen - {"USD"})
    return other[0] if other and "USD" not in seen else None


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


def _not_in_report(facts: dict, have: tuple, missing: tuple, end: str, unit: str, instant: bool = False,
                   that_year: bool = False) -> bool:
    """True when the annual reports that give `have` for the year ending `end` tag none of `missing` at all, for any
    period: the line isn't in the statements (no revenue, no capex, no debt), rather than tagged in a way not read.
    `that_year`: none of `missing` for that year, though they may for others (revenue in the year before, a dash in
    this one: a drug developer whose partner's payments stopped)."""
    reports = _accns_for(facts, have, end, unit, instant)
    tagged = _accns_ending(facts, missing, end, unit) if that_year else _accns(facts, missing, unit)
    return bool(reports) and not reports & tagged


def _accns_ending(facts: dict, concepts: tuple, end: str, unit: str = "USD") -> set[str]:
    """The filings that tag any of these concepts for a period ending on `end`, of any length: a report that gives only
    the last quarter's revenue (a filer whose year's total was tagged with the wrong start date) does have a revenue
    line, though no full-year figure can be read from it."""
    return {f["accn"] for c in concepts for f in _facts(facts, c, unit) if f.get("end") == end and f.get("accn")}


# a concept named like revenue that isn't on our lists (an airline's passenger transport, a telecom's services)
REVENUE_NAME = re.compile(r"Revenue|Sales|Turnover", re.I)
NOT_REVENUE_NAME = re.compile(r"Cost|Deferred|Receivable|Payable|Liabilit|Tax|ProForma|Percent|Concentration|Unearned|Proceeds|"
                              r"Payments|Increase|Decrease|Contract(Asset|Liab)|Allowance|Unbilled|Reserve|Gain|Loss|Expense|"
                              r"Marketing|Commission|Rebate|Return|Discount|Impair|Repurchase|Related|Segment|Geograph", re.I)


def _revenue_like_accns(facts: dict, end: str, unit: str = "USD") -> set[str]:
    """The filings that tag any concept named like revenue for a period ending on `end`, listed or not."""
    out = set()
    for ns in ("us-gaap", "ifrs-full"):
        for concept, body in (facts.get(ns) or {}).items():
            if REVENUE_NAME.search(concept) and not NOT_REVENUE_NAME.search(concept):
                out |= {f["accn"] for f in ((body.get("units") or {}).get(unit) or []) if f.get("end") == end and f.get("start") and f.get("accn")}
    return out


def _depreciation(facts: dict, kind: str, unit: str = "USD") -> dict[str, float]:
    """{period end: depreciation and amortisation}, always a positive cost: some companies tag the cash flow add-back
    with a minus sign (AES). An IFRS filer giving only the parts has them added up, else the add-back with impairments."""
    read = (lambda cs: flows(facts, cs, "annual", unit)) if kind == "annual" else (lambda cs: quarterly(facts, cs, unit))   # noqa: E731
    out = {e: abs(v) for e, v in read(DEPRECIATION).items()}
    parts = [read((c,)) for c in DEPRECIATION_PARTS]
    for e in parts[0]:                        # plant's depreciation at least, with the rest that is given
        out.setdefault(e, sum(abs(x.get(e, 0)) for x in parts))
    dep, amort = read(("DepreciationExpense",)), read(("AmortisationExpense",))     # or all depreciation in one (TSMC)
    for e, v in dep.items():
        out.setdefault(e, abs(v) + abs(amort.get(e, 0)))
    for e, v in read(DEPRECIATION_LAST).items():
        out.setdefault(e, abs(v))
    return out


def _equity(facts: dict, unit: str = "USD") -> dict[str, float]:
    """{date: the shareholders' equity}: the owners' own, else the total less the minority shareholders' part. A total
    whose minority part isn't given on that day, from a company whose minority part was large when it last was
    (Brookfield: three quarters of its equity), is left out rather than shown several times too big."""
    out = instants(facts, EQUITY, unit)
    total, minority = instants(facts, EQUITY_TOTAL, unit), instants(facts, MINORITY, unit)
    for d, v in total.items():
        if d in out:
            continue
        if d in minority:
            out[d] = v - minority[d]
            continue
        before = [x for x in sorted(minority) if x < d and x in total]
        if not before or abs(minority[before[-1]]) <= 0.05 * abs(total[before[-1]]):
            out[d] = v
    return out


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
    # an IFRS filer: its borrowings in two halves, else bonds and loans line by line (TSMC)
    halves = [instants(facts, (c,), unit) for c in ("NoncurrentBorrowings", "CurrentBorrowings")]
    lines = [instants(facts, (c,), unit) for c in IFRS_DEBT_LINES]
    for d in set(halves[0]) | set(halves[1]):
        out.setdefault(d, halves[0].get(d, 0) + halves[1].get(d, 0))
    for d in set().union(*lines):
        out.setdefault(d, sum(x.get(d, 0) for x in lines))
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
# a REIT that owns no property, only mortgage loans and securities (a mortgage REIT)
MORTGAGE_REIT = ("Operating margin isn't shown for a mortgage real estate investment trust: it earns interest on "
                 "mortgage loans and securities, and gains and losses on their value swing its operating profit, so the "
                 "margin doesn't measure the business.")


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
    "part_year": "Its first annual report covers less than a full year (the months since it began), so its results "
                 "can't be shown here yet.",
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
    if facts:
        statements = NET_INCOME + OPERATING + ALL_REVENUE
        part = [f for ns in ("us-gaap", "ifrs-full") for c in statements for rows in
                (((facts.get(ns) or {}).get(c) or {}).get("units") or {}).values() for f in rows
                if f.get("form") in ANNUAL and f.get("start") and 20 <= _days(f["start"], f["end"]) < 340]
        if part:
            return NO_RESULTS["part_year"]    # the first annual report covers the months since the company began
        if any(f.get("form") in ANNUAL for ns in ("us-gaap", "ifrs-full") for c in (facts.get(ns) or {}).values()
               for rows in (c.get("units") or {}).values() for f in rows):
            return UNREAD                     # figures filed as data, but no revenue or profit among them: our gap
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


PROFIT_TOTAL = ("ProfitLoss",)
MINORITY_PROFIT = ("ProfitLossAttributableToNoncontrollingInterests", "NetIncomeLossAttributableToNoncontrollingInterest")


def owner_sign(owners: dict, total: dict, minority: dict) -> None:
    """The shareholders' profit filed with the wrong sign, put right in place (R7V-003: Santander Chile's reports for
    2019 to 2021 tag the profit attributable to its shareholders as -842,467 for a year whose total profit was +852,428,
    so the page showed a bank losing money in a year it made one). A period whose shareholders' profit has the opposite
    sign to the total profit is a sign error when the minority's share says so (total less minority is the same size
    with the other sign) or, without the minority's figure, when the two are of about the same size; a real gap between
    them (a large minority profit beside a shareholders' loss) stands."""
    for end, v in list(owners.items()):
        t = total.get(end)
        if not v or not t or (v > 0) == (t > 0):
            continue
        if end in minority:
            parent = t - minority[end]
            if abs(parent + v) <= 0.02 * abs(t) and abs(parent - v) > 0.02 * abs(t):
                owners[end] = parent
        elif 0.5 <= abs(v) / abs(t) <= 1.5:
            owners[end] = -v


def eps_ttm(facts: dict, cur: str, year_end: str, year: dict) -> dict | None:
    """Earnings per share over the last four reported quarters (diluted where given, in the reporting currency per
    ordinary share): {"value", "basis": "ttm", "end"}; else the latest year's (`year`: {year end: EPS}), with "basis":
    "year"; None without either. The four quarters must run back to back and reach the latest year end or past it."""
    q = quarterly(facts, EPS, f"{cur}/shares")
    last = sorted(e for e in q if q[e] is not None)[-4:]
    if len(last) == 4 and last[-1] >= year_end and all(80 <= _days(a, b) <= 100 for a, b in zip(last, last[1:])):
        return {"value": round(sum(q[e] for e in last), 4), "basis": "ttm", "end": last[-1]}
    if year.get(year_end) is not None:
        return {"value": year[year_end], "basis": "year", "end": year_end}
    return None


def _merge_year_ends(rev: dict, others: list[dict], balances: list[dict] = ()) -> None:
    """One column per fiscal year. A year's end can be filed a few days apart by different concepts or reports (a
    52/53-week year: 29 and 30 Nov, 24 and 31 Dec), and a note can give figures for other 12 months than the fiscal
    year's (a tax year, an insurance subsidiary's year). Two 12-month period ends under 300 days apart overlap, so
    they are one year: the end with more of the statements behind it (revenue, profit, cash flow...) stands, and
    of two equally covered ends within 10 days of each other the later one. The other is dropped, its values moving
    over only when they are within 10 days and the standing end has none of its own. Equally covered ends further apart
    stay apart. The dicts are changed in place; `balances` (balance-sheet days, quarter ends among them) only gain a
    value on the year's own end."""
    flows_ = [rev, *others]
    score = lambda e: sum(e in d for d in flows_)   # noqa: E731
    ends = sorted(set().union(*flows_))
    groups: list[list[str]] = []
    for e in ends:
        if groups and _days(groups[-1][-1], e) < 300:
            groups[-1].append(e)
        else:
            groups.append([e])
    for g in groups:
        for e in g:
            better = [k for k in g if k != e and abs(_days(e, k)) < 300
                      and (score(k) > score(e) or score(k) == score(e) and k > e and _days(e, k) <= 10)]
            if not better:
                continue
            canon = min(better, key=lambda k: (-score(k), abs(_days(e, k))))
            for d in flows_:
                if e in d:
                    v = d.pop(e)
                    if canon not in d and abs(_days(e, canon)) <= 10:
                        d[canon] = v
            for d in balances:
                if e in d and canon not in d and abs(_days(e, canon)) <= 10:
                    d[canon] = d[e]


def build(facts_json: dict, subs: dict | None = None, years: int = 12, symbol: str = "") -> dict:
    """The company in the deep dive's shape: P&L, balance sheet and cash flow by year, the last twelve quarters,
    and the industry path, in millions of the currency the company reports in (US dollars for nearly all)."""
    facts = facts_json.get("facts") or {}
    subs = subs or {}
    cur = currency(facts) or "USD"
    rev_a, rev_q = revenue(facts, "annual", cur), revenue(facts, "quarter", cur)
    ni_a, ni_q = flows(facts, NET_INCOME, "annual", cur), quarterly(facts, NET_INCOME, cur)
    owner_sign(ni_a, flows(facts, PROFIT_TOTAL, "annual", cur), flows(facts, MINORITY_PROFIT, "annual", cur))
    owner_sign(ni_q, quarterly(facts, PROFIT_TOTAL, cur), quarterly(facts, MINORITY_PROFIT, cur))
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
    dep_a, dep_q = _depreciation(facts, "annual", cur), _depreciation(facts, "quarter", cur)
    # operating profit as on the Indian pages: before depreciation (EBITDA), so margins and EV/EBITDA mean the same
    ebitda = lambda op, dep: (op + dep) if op is not None and dep is not None else None   # noqa: E731
    eb_a = {e: ebitda(op_a.get(e), dep_a.get(e)) for e in op_a}
    eb_q = {e: ebitda(op_q.get(e), dep_q.get(e)) for e in op_q}
    eps_a = flows(facts, EPS, "annual", unit=f"{cur}/shares")
    cfo_a, cfi_a = flows(facts, CFO, "annual", cur), flows(facts, CFI, "annual", cur)
    capex_a, div_a = flows(facts, CAPEX, "annual", cur), flows(facts, DIVIDENDS, "annual", cur)
    ppe, debt, equity, cash = instants(facts, PPE, cur), _debt(facts, cur), _equity(facts, cur), instants(facts, CASH, cur)

    _merge_year_ends(rev_a, [ni_a, op_a, eb_a, dep_a, eps_a, cfo_a, cfi_a, capex_a, div_a], [ppe, debt, equity, cash])

    def no_revenue_line(e: str) -> bool:      # the year's annual report has no revenue line at all
        # (an operating profit with no revenue behind it is a revenue we didn't read, not a year without sales)
        return (e in ni_a and e not in rev_a and not (op_a.get(e) or 0) > 0
                and _not_in_report(facts, NET_INCOME, ALL_REVENUE, e, cur, that_year=True)
                and not _accns_for(facts, NET_INCOME, e, cur) & _revenue_like_accns(facts, e, cur))

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
        # a year whose cash flow statement shows no purchases of plant and equipment at all, and whose plant is known
        # and didn't grow, or which has no plant and no depreciation at all: capex was nil, not missing. Plant that
        # stopped being tagged (a bank folding it into other assets) or depreciation without plant (an aircraft lessor's
        # fleet) leaves it unknown.
        if e in ppe:
            still = i > 0 and ends[i - 1] in ppe and ppe[e] <= ppe[ends[i - 1]]
        else:
            still = not ppe and not dep_a.get(e)
        if e not in capex_a and e in cfo_a and still and _not_in_report(facts, CFO, CAPEX, e, cur):
            capex_a[e] = 0.0
        # ...and a balance sheet with no borrowings on it, from a report with no interest expense either: no debt
        if e not in debt and e in equity and _not_in_report(facts, EQUITY + EQUITY_TOTAL, DEBT_ANY + INTEREST, e, cur, instant=True):
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
    # the latest count on a report's cover page, else the balance sheet's or the year's average. A count from before the
    # latest annual report's year isn't today's: a company with two classes of shares stops giving a single count
    # (Berkshire's cover page last did in 2011), and an old count would put the market value far out. None then.
    fresh = (date.fromisoformat(ends[-1]) - timedelta(days=400)).isoformat()
    shares = None
    for f in ((facts.get("dei") or {}).get("EntityCommonStockSharesOutstanding") or {}).get("units", {}).get("shares", []):
        if f.get("val") and f["end"] >= fresh and (shares is None or f["end"] >= shares[0]):
            shares = (f["end"], float(f["val"]))
    # a cover-page count from before the latest year's end, while the balance sheet gives every share outstanding at
    # that end: the balance sheet's (R8V-002: Itaú's cover count stopped at one class, 4,958,290,359 ordinary shares,
    # in its 2023 report; its later reports give each class on the cover, which the company facts leave out, and
    # 9,776,104,515 shares of both classes on the balance sheet at the end of 2024)
    from_cover = shares is not None
    if shares and shares[0] < (date.fromisoformat(ends[-1]) - timedelta(days=31)).isoformat():
        held = [f for c in SHARES_HELD for f in _facts(facts, c, "shares")
                if f.get("val") and float(f["val"]) > 0 and not f.get("start") and f.get("end", "") >= ends[-1]]
        if held:
            f = max(held, key=lambda f: (f["end"], f.get("filed") or ""))
            shares, from_cover = (f["end"], float(f["val"])), False
    # the latest year's average number of shares outstanding (treasury shares never count in it), to tell whether a
    # cover page's count left treasury shares out (see net_of_treasury)
    avg = None
    for concept in ("WeightedAverageNumberOfSharesOutstandingBasic", "WeightedAverageShares"):
        got = [f for f in _facts(facts, concept, "shares") if f.get("val") and f.get("end", "") >= fresh and f.get("fp") in (None, "FY")]
        if got:
            avg = float(max(got, key=lambda f: (f["end"], f.get("filed") or ""))["val"])
            break
    for concept in SHARES if shares is None else ():
        got = [f for f in _facts(facts, concept, "shares") if f.get("val") and f.get("end", "") >= fresh]
        if got:
            f = max(got, key=lambda f: (f["end"], f.get("filed") or ""))
            shares = (f["end"], float(f["val"]))
            break
    # a cover-page count mistyped in the filing's data (Alibaba's 2026 20-F: 18,580,374,278 shares read as 1,858,037,427)
    # is checked against the latest year's profit over its earnings per share, which is restated for any split before
    # the report was issued; more than three times apart, the count the earnings imply is used
    eps_basic = flows(facts, ("EarningsPerShareBasic", "BasicEarningsLossPerShare"), "annual", f"{cur}/shares")
    # (the latest year that has both, within two years: Bradesco's last two reports tag no earnings per share, and its
    # share count is a thousand times its real one, 10.6 trillion, which made a $46 trillion bank, R6V-001)
    recent = (date.fromisoformat(ends[-1]) - timedelta(days=740)).isoformat()
    both = [e for e in sorted(eps_basic) if e >= recent and abs(eps_basic.get(e) or 0) >= 0.05 and ni_a.get(e)]
    last = ends[-1] if ends[-1] in both else (both[-1] if both else ends[-1])
    if shares and abs(eps_basic.get(last) or 0) >= 0.05 and ni_a.get(last):
        implied = ni_a[last] / eps_basic[last]
        if implied > 0 and not 1 / 3 <= shares[1] / implied <= 3:
            shares = (last, float(round(implied)))
            from_cover = False
    out = {"name": subs.get("name") or facts_json.get("entityName") or "", "ratios": {}, "growth": {}, "pros": [], "cons": [],
           "pl": {"cols": pl_cols, "rows": pl_rows}, "balance": bal, "cashflow": cf, "quarters": quarters,
           "basis": "consolidated", "unit": "$ million" if cur == "USD" else f"{cur} million", "currency": cur, "region": "US",
           "cik": facts_json.get("cik"), "sic": sic, "shares": shares[1] if shares else None, "fiscal_year_end": subs.get("fiscalYearEnd"),
           "shares_from": "cover" if shares and from_cover else None, "avg_shares": avg,
           # the periods the latest figures run to, and earnings per share for the P/E (R7V-002, R7V-003)
           "year_end": ends[-1], "ttm_end": max(rev_q) if has_ttm else None, "eps": eps_ttm(facts, cur, ends[-1], eps_a),
           "industry_path": sic_path(sic, subs.get("sicDescription")) or KIND_PATHS.get(kind or "", []),
           "bank": kind is None and lender,
           "kind": kind, "no_revenue": no_revenue,
           "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={facts_json.get('cik')}&type=10-K"}
    if no_margin:
        out["margin_note"] = MORTGAGE_REIT if kind == "reit" and not any(ppe.get(e) for e in ends) else NO_MARGIN[kind]
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

    def predecessor(self, cik: int, subs: dict) -> tuple[int, dict] | None:
        """The company a new holding company took over from, when the listed company was put under one (Exxon Mobil
        under ExxonMobil Holdings in 2026, filed as an 8-K12B): its own filings carry the years of results. Found among
        the filers of the new company's documents (the old company files the first reports for it), as the one with
        annual reports, the same industry code and the same name before its legal ending."""
        rec = ((subs.get("filings") or {}).get("recent") or {})
        # the filers of its periodic reports first (a company files those itself), then of its other own forms
        order = ("10-Q", "10-K", "11-K", "3", "4", "8-K")
        filers = [int(a.split("-")[0]) for f, a in sorted(zip(rec.get("form") or [], rec.get("accessionNumber") or []),
                                                          key=lambda x: order.index(x[0]) if x[0] in order else 99)
                  if f in order and a and a.split("-")[0].isdigit()]
        stem = lambda n: re.sub(r"[^a-z]", "", str(n).lower())[:6]        # noqa: E731
        for other in list(dict.fromkeys(f for f in filers if f != cik))[:4]:
            try:
                old = self.submissions(other)
            except SourceError as e:
                if e.busy:
                    raise
                continue
            if (_forms(old) & {"10-K", "20-F", "40-F"} and str(old.get("sic") or "") == str(subs.get("sic") or "")
                    and stem(old.get("name")) == stem(subs.get("name")) and len(stem(subs.get("name"))) >= 4):
                return other, old
        return None

    def ads(self, subs: dict) -> dict | None:
        """{"ratio", "ads", "form", "url"} from the latest annual report of a foreign company, whose US shares may be
        depositary shares (see ads_ratio); None for a US company or when the report can't be read. Cached a month."""
        rec = ((subs.get("filings") or {}).get("recent") or {})
        forms = rec.get("form") or []
        i = next((i for i, f in enumerate(forms) if f in ("20-F", "10-K", "40-F")), None)
        if i is None or forms[i] != "20-F" and not subs.get("foreign"):
            return None
        acc, doc = rec["accessionNumber"][i], (rec.get("primaryDocument") or [""] * len(forms))[i]
        url = f"https://www.sec.gov/Archives/edgar/data/{int(subs.get('cik') or 0)}/{acc.replace('-', '')}/{doc}"
        hit = self.cache.get(("ads", url))
        if hit is not None:
            return hit
        # a foreign company's report that couldn't be read now: said, so its market value isn't taken on trust (R6V-001)
        unread = {"ratio": None, "ads": None, "unread": True, "form": forms[i], "url": url}
        if not self.limit.take():
            return unread
        try:
            with self.http.stream("GET", url) as r:
                self.check(r)
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > 60 * 1024 * 1024:
                        break
        except (httpx.HTTPError, SourceError):
            return unread
        text = filing_text(bytes(buf).decode("utf-8", "replace"))
        out = {**ads_ratio(text), "treasury": treasury_held(text), "form": forms[i], "url": url}
        self.cache.set(("ads", url), out, 30 * 86400)
        return out

    def filing_data(self, cik: int, filing: dict) -> dict | None:
        """{"facts": its figures without dimensions in the company facts' shape, "classes": class_shares} from one
        filing's own XBRL instance ({"form", "accn", "filed", "doc"}), cached a month by filing; {} when the filing has
        none, None when it can't be read right now (the rate limit, the SEC down)."""
        acc, doc = filing["accn"], filing["doc"]
        key = ("instance", acc)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        if not doc.lower().endswith((".htm", ".html")) or not self.limit.take():
            return None
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{re.sub(r'[.]html?$', '', doc)}_htm.xml"
        try:
            with self.http.stream("GET", url) as r:
                if r.status_code == 404:          # not an inline XBRL filing: nothing to read, not a fault
                    self.cache.set(key, {}, 30 * 86400)
                    return {}
                self.check(r)
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > 80 * 1024 * 1024:
                        raise SourceError(self.name, "The filing's data is too large to read here.")
            inst = instance(bytes(buf).decode("utf-8", "replace"))
        except (httpx.HTTPError, SourceError, ValueError) as e:
            print("SEC filing data:", acc, str(e)[:120])
            return None
        out = {"facts": instance_facts(inst, filing["form"], filing["filed"], acc), "classes": class_shares(inst)}
        self.cache.set(key, out, 30 * 86400)
        return out

    def with_latest_annual(self, cik: int, subs: dict, facts_json: dict) -> dict:
        """The company facts with the latest annual report's own figures added when the SEC's facts don't have them
        yet (R7V-003: TSMC's and Ecopetrol's 20-F of April 2026, filed under the 2025 IFRS taxonomy, aren't in them;
        R8V-003: Toyota's and Infosys's of June 2026, March years, and BHP's of August 2026, a June year). A report
        that couldn't be read just now (the rate limit, the SEC busy) is marked "annual_unread" with its filing, so the
        company is built again soon rather than kept a year behind for the day."""
        filing = latest_filing(subs, ANNUAL_FORMS)
        if not filing or has_filing(facts_json, filing["accn"]):
            return facts_json
        got = self.filing_data(cik, filing)
        if got is None:
            return {**facts_json, "annual_unread": filing}
        if not got.get("facts"):
            return facts_json
        return merge_facts({"facts": got["facts"]}, facts_json)

    def classes(self, cik: int, subs: dict) -> dict[str, float]:
        """{ticker: shares counted in that ticker's class} for a company with several classes of common stock, from
        its latest report's cover page (see class_shares); {} for one class or when it can't be read now."""
        filing = latest_filing(subs, ANNUAL_FORMS + ("10-Q",))
        got = self.filing_data(cik, filing) if filing else None
        return dict((got or {}).get("classes") or {})

    def company(self, symbol: str) -> dict:
        """The company's numbers in the deep dive's shape (cached six hours), with its filing list under "filings"."""
        cik = self.cik(symbol)
        with self._build_lock:
            hit = self._built.get(str(cik))
        if hit and time.time() - hit[0] < 6 * 3600:
            if hit[1] is None:             # no results to show, found a moment ago: the same reason again
                raise SourceError(self.name, hit[2])
            return for_symbol(hit[1], symbol)
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
                facts = None
            before = self.predecessor(cik, subs) if _forms(subs) & {"8-K12B", "8-K12G3"} else None
            if before:                            # the years before a new holding company took over: the old company's
                try:
                    old = self._json(f"/api/xbrl/companyfacts/CIK{before[0]:010d}.json")
                    facts = merge_facts(old, facts) if facts else old
                except SourceError as e:
                    if e.busy:
                        raise
            if facts is None:                     # no figures filed as data at all
                raise SourceError(self.name, no_results(subs, None, symbol))
            facts = self.with_latest_annual(cik, subs, facts)
            p = build(facts, subs, symbol=symbol.upper())
            if facts.get("annual_unread"):
                p["annual_unread"] = str(facts["annual_unread"].get("filed") or "")[:10] or True
        except SourceError as e:
            if not e.busy:
                with self._build_lock:
                    self._built[str(cik)] = (time.time(), None, str(e))
            raise
        p["symbol"] = symbol.upper()
        # five years of documents: a deep read can look that far back
        p["documents"] = sorted(documents(subs, days=5 * 366) + (documents(before[1], days=5 * 366) if before else []),
                                key=lambda d: d["at"], reverse=True)
        try:
            dep = self.ads(subs)
        except SourceError as e:
            if e.busy:
                raise
            dep = None
        if dep and dep.get("form") == "20-F" and dep.get("treasury"):
            # a 20-F cover page that counts the shares issued, treasury shares included: the market value counts the
            # shares outstanding (R8O-005 builder note: Eni's 3,146,765,114 held 189,083,769 in treasury)
            p = net_of_treasury(p, dep["treasury"])
        if dep and dep.get("ads"):
            known = ADS_RATIO_KNOWN.get(int(cik))
            p = with_ads(p, known or dep.get("ratio"))
            if known and dep.get("ratio") and abs(known - dep["ratio"]) > 1e-9:
                p["share_note"] = p["share_note"].replace(
                    "as its annual report states", f"as the depositary has set it (the annual report's cover page "
                    f"still gives the earlier figure, {dep['ratio']:,g})")
        elif dep and dep.get("unread"):
            p["ads_unread"] = True          # whether its US shares are depositary shares isn't known this time
        # a foreign company (a 20-F or 40-F filer, or depositary shares): its market value is checked against its own
        # profit before it is shown (stock_pages.cap_problem, R8V-001)
        p["foreign"] = bool(dep and (dep.get("form") in ("20-F", "40-F") or dep.get("ads"))) or (p.get("currency") or "USD") != "USD"
        # several classes of common stock (Berkshire, Visa, Alphabet): every class counted in the listed share's terms,
        # from the latest report's cover page, so the market value counts the whole company (R7V-001)
        common = [t for t in subs.get("tickers") or [] if not non_common(t)]
        if not p.get("ads_ratio") and (p.get("shares") is None or len(common) > 1):
            classes = self.classes(cik, subs)
            if classes:
                p["class_shares"] = classes
        with self._build_lock:
            if len(self._built) > 300:
                self._built.pop(next(iter(self._built)))
            # a build without the latest annual report (it couldn't be read just now) is kept a quarter of an hour, not
            # six, so the next look reads the report
            at = time.time() - (6 * 3600 - UNREAD_RETRY if p.get("annual_unread") else 0)
            self._built[str(cik)] = (at, p)
        return for_symbol(p, symbol)


ANNUAL_FORMS = ("10-K", "20-F", "40-F")
UNREAD_RETRY = 15 * 60         # seconds a company built without its latest annual report (unreadable just then) is kept

# depositary-share ratios an annual report states wrongly, by the company's SEC number: ordinary shares per ADS.
# Mizuho (MFG): its 20-F cover page still says "American depositary shares, each of which represents two shares of
# common stock", the ratio from before its 1-for-10 share consolidation of 1 October 2020; since then one ADS has
# stood for 0.2 of a share (five ADSs to a share). Read as two, its market value was a tenth of its real one, $13.3B
# for about $130B, and its P/E 1.8 (R8V-001). The plausibility check in stock_pages.cap_problem catches any other case.
ADS_RATIO_KNOWN = {1335730: 0.2}


def latest_filing(subs: dict, forms: tuple) -> dict | None:
    """The newest filing of one of these forms in the filing list: {"form", "accn", "filed", "doc"}, or None."""
    rec = ((subs or {}).get("filings") or {}).get("recent") or {}
    names = rec.get("form") or []
    docs = rec.get("primaryDocument") or [""] * len(names)
    best = None
    for form, acc, filed, doc in zip(names, rec.get("accessionNumber") or [], rec.get("filingDate") or [], docs):
        if form in forms and acc and (best is None or filed > best["filed"]):
            best = {"form": form, "accn": acc, "filed": filed, "doc": doc or ""}
    return best


def has_filing(facts_json: dict, accn: str) -> bool:
    """Whether the company facts hold the revenue or profit a filing reported (the SEC adds a filing's figures to
    them some time after it is filed, and leaves some out)."""
    facts = (facts_json or {}).get("facts") or {}
    for ns in ("us-gaap", "ifrs-full"):
        for concept in TOP_LINE + NET_INCOME:
            for rows in (((facts.get(ns) or {}).get(concept) or {}).get("units") or {}).values():
                if any(r.get("accn") == accn for r in rows):
                    return True
    return False


def for_symbol(p: dict, symbol: str) -> dict:
    """The company as one of its tickers sees it: with several classes of stock, the share count in that class's
    terms (BRK-B's in Class B shares, BRK-A's in Class A shares), so price times shares is the whole company's value."""
    out = {**p, "symbol": symbol.upper()}
    shares = (p.get("class_shares") or {}).get(price_symbol(symbol))
    if shares:
        out["shares"] = shares
    return out


def merge_facts(old: dict, new: dict) -> dict:
    """Two companies' facts as one (a predecessor's and its successor's): every concept's figures from both; where both
    give a period, the later filing wins as usual."""
    out = {**new, "facts": {}}
    for src in (old, new):
        for ns, concepts in (src.get("facts") or {}).items():
            into = out["facts"].setdefault(ns, {})
            for c, body in concepts.items():
                units = into.setdefault(c, {"units": {}})["units"]
                for u, rows in (body.get("units") or {}).items():
                    units[u] = list(units.get(u) or []) + list(rows)
    return out


def with_ads(p: dict, ratio: float | None) -> dict:
    """A company whose US shares are depositary shares: how many of its ordinary shares one ADS stands for (from the
    annual report), so market value, price to book and the like use the number of ADSs; and the note saying that the
    per-share figures in its accounts are per ordinary share."""
    p = dict(p)
    if ratio:
        p["ads_ratio"] = ratio
        words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 8: "eight", 10: "ten"}
        n = (words.get(ratio) or f"{ratio:,g}") if ratio >= 1 else f"1/{1 / ratio:g} of one"
        p["share_note"] = (f"The US-listed shares are American depositary shares (ADSs), each standing for {n} of the "
                           f"company's ordinary shares, as its annual report states. Earnings per share in its accounts "
                           f"are per ordinary share; market value, P/E and price to book use the number of ADSs.")
    else:
        p.pop("ads_ratio", None)
        p["share_note"] = ("The US-listed shares are American depositary shares (ADSs), and how many ordinary shares each "
                           "stands for couldn't be read from the annual report. Earnings per share in its accounts are "
                           "per ordinary share, and market value and price ratios count one ordinary share per ADS, so "
                           "they may be off by that ratio.")
    return p


def _latest(table: dict | None, label: str, skip_ttm: bool = False, last_only: bool = False):
    """The latest figure of a row; `last_only`: the latest year's or nothing (a balance from years ago isn't today's)."""
    rows = (table or {}).get("rows") or {}
    cols = (table or {}).get("cols") or []
    vals = rows.get(label) or []
    pairs = [(c, v) for c, v in zip(cols, vals) if not (skip_ttm and str(c).upper() == "TTM")]
    if last_only:
        return pairs[-1][1] if pairs else None
    pairs = [(c, v) for c, v in pairs if v is not None]
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


def market_value(p: dict, price: float | None) -> float | None:
    """Price times shares, in $ million (ADSs counted as ADSs)."""
    shares = p.get("shares")
    if shares and p.get("ads_ratio"):
        shares = shares / p["ads_ratio"]
    return price * shares / M if price and shares else None


def pe_and_basis(p: dict, price: float | None, mcap: float | None = None) -> tuple[float | None, dict | None]:
    """(P/E, what its earnings cover) with one definition, the app's and the Indian pages' (R7V-002): the price over
    earnings per share for the last four reported quarters, from the filings. Without quarterly earnings per share,
    market value over the last four quarters' net profit; a company that reports only yearly (most foreign filers),
    the latest year's, said so: {"basis": "ttm" or "year", "end": the day those earnings run to}. A loss has no P/E.
    Earnings per share that don't agree with the market value over profit (several classes of stock, a share count
    read another way) give way to the market value over profit."""
    if not price:
        return None, None
    mcap = mcap if mcap is not None else market_value(p, price)
    fx = usd_rate(p)
    eps = p.get("eps") or {}
    per_share = (eps.get("value") * fx * (p.get("ads_ratio") or 1)) if eps.get("value") is not None and fx else None
    pl = p.get("pl") or {}
    has_ttm = bool(pl.get("cols")) and str(pl["cols"][-1]).upper() == "TTM"
    profit_ttm = _latest(pl, "Net Profit", last_only=True) if has_ttm else None
    profit_year = _latest(pl, "Net Profit", skip_ttm=True, last_only=True) if not has_ttm else _year_value(pl, "Net Profit")
    to_usd = lambda v: v * fx if v is not None and fx else None       # noqa: E731
    by_cap = lambda profit: (mcap / profit if mcap and profit and profit > 0 else None) if profit is not None else None  # noqa: E731
    ttm_end, year_end = p.get("ttm_end"), p.get("year_end")
    for basis, end, eps_ok, profit in (("ttm", ttm_end or eps.get("end"), eps.get("basis") == "ttm", to_usd(profit_ttm)),
                                       ("year", year_end, eps.get("basis") == "year", to_usd(profit_year))):
        if not eps_ok and profit is None:
            continue
        if eps_ok and per_share is not None:
            if per_share <= 0 or profit is not None and profit <= 0:
                return None, {"basis": basis, "end": eps.get("end") or end}
            pe = price / per_share
            cap_pe = by_cap(profit)
            if cap_pe is None or 0.67 <= pe / cap_pe <= 1.5:
                return pe, {"basis": basis, "end": eps.get("end") or end}
            return cap_pe, {"basis": basis, "end": end}
        if profit is not None:
            return by_cap(profit), {"basis": basis, "end": end}
    return None, None


def basis_profit(p: dict, basis: str | None) -> float | None:
    """The net profit a P/E's basis covers ("ttm": the last four quarters', "year": the latest year's), in US dollars
    million at today's rate; None without it or the rate."""
    pl = p.get("pl") or {}
    fx = usd_rate(p)
    has_ttm = bool(pl.get("cols")) and str(pl["cols"][-1]).upper() == "TTM"
    if basis == "ttm":
        v = _latest(pl, "Net Profit", last_only=True) if has_ttm else None
    elif basis == "year":
        v = _year_value(pl, "Net Profit") if has_ttm else _latest(pl, "Net Profit", skip_ttm=True, last_only=True)
    else:
        return None
    return round(v * fx, 2) if v is not None and fx else None


def _year_value(table: dict, label: str):
    """The latest full year's figure of a row, the trailing twelve months' column left out."""
    cols = [str(c).upper() for c in table.get("cols") or []]
    vals = (table.get("rows") or {}).get(label) or []
    years = [v for c, v in zip(cols, vals) if c != "TTM"]
    return years[-1] if years else None


def ratios(p: dict, price: float | None, high: float | None = None, low: float | None = None) -> dict:
    """The headline ratios the Indian pages state, worked out from the filings and the share price: market cap
    ($ million), P/E (see pe_and_basis), book value per share, ROE, ROCE and dividend yield.
    The share price is in dollars: a company reporting in another currency has its profit, book and dividends turned
    into dollars at today's rate for the ratios against the price; without the rate those ratios are left out."""
    shares = p.get("shares")
    if shares and p.get("ads_ratio"):        # depositary shares: the price is per ADS, so count ADSs
        shares = shares / p["ads_ratio"]
    mcap = price * shares / M if price and shares else None
    fx = usd_rate(p)
    usd = lambda v: v * fx if v is not None and fx else None    # noqa: E731
    equity = _latest(p.get("balance"), "Equity", last_only=True)
    debt = _latest(p.get("balance"), "Borrowings") or 0
    fy_profit = _latest(p.get("pl"), "Net Profit", skip_ttm=True)
    ebitda = _latest(p.get("pl"), "Operating Profit", skip_ttm=True)
    dep = _latest(p.get("pl"), "Depreciation", skip_ttm=True) or 0
    divs = usd(_latest(p.get("cashflow"), "Dividends paid"))
    book = usd(equity)
    pe, _ = pe_and_basis(p, price, mcap)
    out = {"Current Price": price, "Market Cap": round(mcap, 1) if mcap else None,
           "Stock P/E": round(pe, 1) if pe else None,
           "Book Value": round(book * M / shares, 2) if book and shares else None,
           "ROE": round(fy_profit / equity * 100, 1) if fy_profit is not None and equity and equity > 0 else None,
           "ROCE": round((ebitda - dep) / (equity + debt) * 100, 1) if ebitda is not None and equity and equity + debt > 0 else None,
           "Dividend Yield": round(abs(divs) / mcap * 100, 2) if divs and mcap else 0.0 if mcap and fx else None}
    if high and low:
        out["High / Low"] = f"{high} / {low}"
    return {k: v for k, v in out.items() if v is not None}


# ---------- American depositary shares ----------
# A foreign company's shares often trade in the US as depositary shares (ADSs), each standing for a fixed number of its
# ordinary shares: five for TSMC, eight for Alibaba, half of one for some. Its filings count ordinary shares, so the
# market value from the ADS price needs that number, which the annual report states in words on its cover page
# ("American Depositary Shares, each representing eight Ordinary Shares") and again where it describes the ADSs.
_SMALL = {"one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "twenty-five": 25, "thirty": 30, "forty": 40,
          "fifty": 50, "one hundred": 100, "hundred": 100, "one thousand": 1000}
_PARTS = {"half": 2, "third": 3, "quarter": 4, "fourth": 4, "fifth": 5, "tenth": 10, "twentieth": 20, "hundredth": 100}
_NUM = (r"\d[\d,]*(?:\.\d+)?\s*/\s*\d[\d,]*(?:th)?|\d[\d,]*(?:\.\d+)?|(?:one|a)[\s-]+(?:" + "|".join(_PARTS) + r")|"
        r"twenty[\s-]five|one\s+hundred|one\s+thousand|" + "|".join(sorted(_SMALL, key=len, reverse=True)))
ADS_RATIO = re.compile(
    r"(?:american\s+deposit[ao]ry\s+(?:shares?|receipts?)|\bADSs?|\bADRs?)\b[^.;]{0,100}?\b"
    r"represent(?:s|ing)\s+(?:an\s+ownership\s+interest\s+in\s+|the\s+right\s+to\s+receive\s+)?"
    r"(?P<n>" + _NUM + r")\s+(?:\(\s*[\d.,/]+\s*\)\s+)?(?:of\s+(?:one|an?)\s+)?(?P<rest>[^.;%]{0,60}?)\b(?:shares?|stock)\b", re.I)
COVER = re.compile(r"pursuant\s+to\s+section\s+12\s*\(\s*b\s*\)", re.I)


def _number(t: str) -> float | None:
    t = re.sub(r"\s+", " ", t.strip().lower())
    m = re.fullmatch(r"([\d,.]+)\s*/\s*([\d,]+)(?:th)?", t)
    if m:
        a, b = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
        return a / b if b else None
    if re.fullmatch(r"\d[\d,]*(?:\.\d+)?", t):
        return float(t.replace(",", ""))
    m = re.fullmatch(r"(?:one|a)[ -](\w+)", t)
    if m and m.group(1) in _PARTS:
        return 1 / _PARTS[m.group(1)]
    return _SMALL.get(t.replace(" ", "-") if t.startswith("twenty") else t)


def ads_ratios(text: str) -> list[float]:
    """Every "each ADS represents N shares" in a filing's text, in order: ordinary shares per depositary share."""
    out = []
    for m in ADS_RATIO.finditer(text):
        if re.search(r"\b(?:ADSs?|ADRs?|deposit[ao]ry|million|billion|thousand)\b", m.group("rest"), re.I):
            continue
        n = _number(m.group("n"))
        if n and 1e-4 <= n <= 1e7:
            out.append(n)
    return out


def ads_ratio(text: str) -> dict:
    """What an annual report says about depositary shares: {"ratio": ordinary shares per ADS, or None, "ads": whether
    its cover page lists depositary shares (or the listed shares are for them)}. The cover page's own figure wins;
    otherwise the figure the report states most often (a past ratio is in the past tense, so isn't read)."""
    cover = ""
    m = COVER.search(text)
    if m:                                     # the cover page: to the table of contents, with its footnotes
        cover = text[m.start(): m.start() + 8000]
        # the table of contents ends the cover, but only one after the list of registered securities: a page header
        # "Table of contents" link can sit above that list (Banco Santander-Chile's 20-F, R6V-001)
        listed = re.search(r"registered\s+pursuant\s+to\s+section\s+12\s*\(\s*b\s*\)\s+of\s+the\s+act", cover[200:], re.I)
        after = max(500, 200 + listed.end()) if listed else 500
        toc = re.search(r"table\s+of\s+contents", cover[after:], re.I)
        cover = cover[: after + toc.start()] if toc else cover
    ads = bool(re.search(r"deposit[ao]ry|\bADSs?\b|\bADRs?\b", cover, re.I))
    if not ads:
        return {"ratio": None, "ads": False}
    first = ads_ratios(cover)
    if first:
        return {"ratio": first[0], "ads": True}
    found = ads_ratios(text)
    if not found:
        return {"ratio": None, "ads": True}
    return {"ratio": max(dict.fromkeys(found), key=found.count), "ads": True}


# treasury shares at the balance sheet date, as an annual report states them in words: "A total of 189,083,769 of Eni's
# ordinary shares (203,137,967 at December 31, 2024) were held in treasury". Only a count said to be held in treasury:
# shares bought back or cancelled during the year, or held after a later cancellation, are other numbers
TREASURY_HELD = re.compile(
    r"(?P<n>\d{1,3}(?:,\d{3}){2,})\s+(?:of\s+[^.;()]{0,60}?\s+)?(?:[\w’']+\s+){0,3}?shares\s*(?:\([^)]{0,120}\)\s*)?"
    r"(?:were|are|was|is|being)?\s*(?:being\s+)?held\s+(?:in|as)\s+treasury", re.I)


def treasury_held(text: str) -> int | None:
    """The treasury shares an annual report says the company held (the first such statement), or None."""
    m = TREASURY_HELD.search(text or "")
    if not m:
        return None
    n = int(m.group("n").replace(",", ""))
    return n if n > 0 else None


def net_of_treasury(p: dict, treasury: float | None) -> dict:
    """A share count from a 20-F's cover page with the treasury shares taken out, when the cover page counted them:
    the count net of them sits closer to the year's average shares outstanding (which never includes them) than the
    cover page's own does. A count already net of treasury shares, or not from the cover page, is left as it is."""
    s, avg = p.get("shares"), p.get("avg_shares")
    if not s or not treasury or p.get("shares_from") != "cover" or treasury >= 0.5 * s:
        return p
    net = s - treasury
    if not avg or abs(net - avg) >= abs(s - avg):
        return p
    return {**p, "shares": float(net), "treasury_shares": float(treasury), "shares_from": "cover net of treasury"}


def filing_text(raw: str) -> str:
    """A filing's HTML as plain words, quickly (a 20-F runs to tens of megabytes): tags dropped, entities decoded,
    the inline XBRL header (thousands of context names) left out."""
    import html as _html
    raw = re.sub(r"(?is)<ix:header>.*?</ix:header>", " ", raw)
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", raw)))


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


# ---------- a filing's own XBRL (the data the SEC's company facts are built from) ----------
# The SEC's company facts can leave a filing out: annual reports filed under the 2025 IFRS taxonomy (TSMC's and
# Ecopetrol's 20-F of April 2026) aren't in them at all, so their pages stopped at Dec 2024 (R7V-003). And they keep only
# figures without dimensions, so a company with several classes of shares (Berkshire, Visa) has no share count in them
# (R7V-001). Both come from the filing's own XBRL instance (<primary document>_htm.xml beside an inline XBRL filing).
_X_CTX = re.compile(r"<(?:[\w-]+:)?context\b[^>]*?\bid=\"([^\"]+)\"[^>]*>(.*?)</(?:[\w-]+:)?context\s*>", re.S)
_X_UNIT = re.compile(r"<(?:[\w-]+:)?unit\b[^>]*?\bid=\"([^\"]+)\"[^>]*>(.*?)</(?:[\w-]+:)?unit\s*>", re.S)
_X_MEASURE = re.compile(r"<(?:[\w-]+:)?measure\s*>\s*([^<\s]+)\s*<", re.S)
_X_DIVIDE = re.compile(r"<(?:[\w-]+:)?unitNumerator\s*>(.*?)</(?:[\w-]+:)?unitNumerator\s*>\s*<(?:[\w-]+:)?unitDenominator\s*>(.*?)"
                       r"</(?:[\w-]+:)?unitDenominator\s*>", re.S)
_X_MEMBER = re.compile(r"<(?:[\w-]+:)?explicitMember\b[^>]*?\bdimension=\"([^\"]+)\"[^>]*>\s*([^<\s]+)\s*<", re.S)
_X_TYPED = re.compile(r"<(?:[\w-]+:)?typedMember\b", re.S)
_X_DATE = {k: re.compile(rf"<(?:[\w-]+:)?{k}\s*>\s*([0-9-]{{10}})", re.S) for k in ("startDate", "endDate", "instant")}
_X_FACT = re.compile(r"<([\w-]+):([A-Za-z][\w.-]*)\b([^>]*?)(?:/>|>([^<]*)</\1:\2\s*>)", re.S)
_X_ATTR = re.compile(r"([\w:.-]+)\s*=\s*\"([^\"]*)\"")
_X_NS = re.compile(r"xmlns:([\w-]+)\s*=\s*\"([^\"]+)\"")
CLASS_AXIS = "StatementClassOfStockAxis"
EPS_CONCEPTS = ("EarningsPerShareBasic", "EarningsPerShareDiluted", "BasicEarningsLossPerShare", "DilutedEarningsLossPerShare")


def _x_namespace(uri: str) -> str | None:
    """The company facts' name for a taxonomy, from its address (any year's: the IFRS one moved to xbrl.ifrs.org in 2025)."""
    u = uri.lower()
    if "ifrs-full" in u:
        return "ifrs-full"
    if "fasb.org/us-gaap" in u:
        return "us-gaap"
    if "xbrl.sec.gov/dei" in u:
        return "dei"
    return None


def _x_unit(body: str) -> str | None:
    """"TWD", "shares" or "TWD/shares", as the company facts name units."""
    bare = lambda m: m.split(":")[-1]          # noqa: E731
    div = _X_DIVIDE.search(body)
    if div:
        num, den = _X_MEASURE.search(div.group(1)), _X_MEASURE.search(div.group(2))
        return f"{bare(num.group(1))}/{bare(den.group(1))}" if num and den else None
    m = _X_MEASURE.search(body)
    return bare(m.group(1)) if m else None


def instance(xml: str) -> dict:
    """A filing's XBRL instance read plainly: {"contexts": {id: {"start", "end", "dims": {axis: member}}}, "units":
    {id: unit}, "facts": [(namespace, concept, context id, unit or None, text)]} for the standard taxonomies (IFRS,
    US GAAP, the SEC's cover page). A document declaring entities is refused (nothing in an instance needs one)."""
    if re.search(r"<!(?:DOCTYPE|ENTITY)", xml[:5000], re.I):
        raise ValueError("an XBRL instance with a document type declaration")
    ns = {p: n for p, uri in _X_NS.findall(xml[:200000]) if (n := _x_namespace(uri))}
    contexts = {}
    for cid, body in _X_CTX.findall(xml):
        d = {k: (m.group(1) if (m := r.search(body)) else None) for k, r in _X_DATE.items()}
        dims = {a.split(":")[-1]: m.split(":")[-1] for a, m in _X_MEMBER.findall(body)}
        if _X_TYPED.search(body):
            dims["typed"] = "typed"
        contexts[cid] = {"start": d["startDate"], "end": d["endDate"] or d["instant"], "dims": dims}
    units = {uid: _x_unit(body) for uid, body in _X_UNIT.findall(xml)}
    facts = []
    for prefix, concept, attrs, text in _X_FACT.findall(xml):
        if prefix not in ns:
            continue
        a = dict(_X_ATTR.findall(attrs))
        if a.get("xsi:nil") == "true" or "contextRef" not in a:
            continue
        facts.append((ns[prefix], concept, a["contextRef"], units.get(a["unitRef"]) if a.get("unitRef") else None, (text or "").strip()))
    return {"contexts": contexts, "units": units, "facts": facts}


def _x_num(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def instance_facts(inst: dict, form: str, filed: str, accn: str) -> dict:
    """A filing's figures without dimensions in the company facts' shape ({namespace: {concept: {"units": {unit:
    [rows]}}}}), so they merge with the SEC's own (see merge_facts)."""
    out: dict = {}
    seen = set()
    for ns, concept, cid, unit, text in inst["facts"]:
        ctx = inst["contexts"].get(cid)
        val = _x_num(text) if unit else None
        if not ctx or ctx["dims"] or val is None or not ctx["end"]:
            continue
        key = (ns, concept, unit, ctx["start"], ctx["end"])
        if key in seen:
            continue
        seen.add(key)
        row = {"end": ctx["end"], "val": val, "accn": accn, "form": form, "filed": filed}
        if ctx["start"]:
            row["start"] = ctx["start"]
        out.setdefault(ns, {}).setdefault(concept, {"units": {}})["units"].setdefault(unit, []).append(row)
    return out


def class_shares(inst: dict) -> dict[str, float]:
    """A company with several classes of common stock, from its report's cover page and earnings per share: {ticker:
    every class's shares counted in that ticker's class}, each class weighted by its earnings per share against the
    ticker's (a Berkshire Class A share earns what 1,500 Class B shares do; Alphabet's three classes earn alike).
    {} for a company with one class, or when a class's earnings per share isn't given (its weight can't be known)."""
    ctx = inst["contexts"]

    def cls(cid):
        # one class however the report names it: Berkshire's cover page says CommonClassAMember, its earnings per share
        # EquivalentClassAMember
        dims = (ctx.get(cid) or {}).get("dims") or {}
        m = dims.get(CLASS_AXIS) if len(dims) == 1 else None
        return re.sub(r"member|equivalent|common|stock|shares?", "", m.lower()) or None if m else None
    tickers: dict[str, str] = {}
    shares: dict[str, tuple[str, float]] = {}
    eps: dict[tuple, dict[str, float]] = {}
    for ns, concept, cid, unit, text in inst["facts"]:
        member = cls(cid)
        if not member:
            continue
        if concept == "TradingSymbol" and text:
            tickers.setdefault(price_symbol(text), member)
        elif concept == "EntityCommonStockSharesOutstanding" and unit == "shares":
            v, end = _x_num(text), ctx[cid]["end"] or ""
            if v and v > 0 and (member not in shares or end > shares[member][0]):
                shares[member] = (end, v)
        elif concept in EPS_CONCEPTS and unit and unit.endswith("/shares") and ctx[cid]["start"]:
            v = _x_num(text)
            if v is not None:
                eps.setdefault((ctx[cid]["start"], ctx[cid]["end"], concept), {}).setdefault(member, v)
    if len(shares) < 2 or not tickers:
        return {}
    # one period's earnings per share for every class: the latest, longest one that covers them all
    full = [(k, v) for k, v in eps.items() if set(shares) <= set(v) and all(v[m] for m in shares)]
    if not full:
        return {}
    _, per = max(full, key=lambda kv: (kv[0][1], _days(kv[0][0], kv[0][1]), kv[0][2] == "EarningsPerShareBasic"))
    return {t: float(round(sum(n * per[m] / per[member] for m, (_, n) in shares.items())))
            for t, member in tickers.items() if member in shares}
