"""A sector's own operating figures, as the companies file them (R23, the owner's outside reviews: "the biggest improvement would be a
sector-specific analytical engine"; banks scored 6.3 and insurers 6.9 because the decks had no sector operating metrics).

Three families, each from filings the app can read cheaply, each figure with its source and its period, and nothing interpreted:
- India banks: the quarterly results each bank files with the exchange in the SEBI banking format (the exchange's "Integrated Filing -
  Financials" XBRL): gross and net NPA %, the CET1 ratio, return on assets (the year to date's net profit, annualised, over average total
  assets: banks file their own ROA on different bases), net interest income (interest earned less interest expended) and its growth on the same quarter a year before, advances and deposits on a year before (from the
  half-year balance sheets the March and September filings carry), and the credit cost: provisions other than tax for the year to date,
  annualised, over the average of advances at the period's end and a year earlier. NIM and CASA only where a filing states them (the banking
  format has no element for either), and the total capital adequacy ratio is not in it (CET1 and AT1 are).
- India insurers: the same exchange filing in the life ("LI") and general ("GI") insurance formats: the solvency ratio; for general insurers
  the incurred claims ratio and the combined ratio; for life insurers the 13th-month persistency; gross premium on the same quarter a year
  before. VNB, APE and embedded value only where a filing states them (neither format has elements for them).
- US companies outside finance: the SEC's company facts the app already reads: stock-based compensation as a share of revenue, remaining
  performance obligations (RPO) over the year's revenue and their growth on a year before, deferred revenue on the year before, and free cash
  flow (cash from operations less capital spending) as a share of revenue, each for the latest fiscal year (RPO: the latest date filed).
R27: whom each figure applies to, its four states and the headline rule are metric_registry's; banks' net interest income over average assets
from the same half-year filings (never called NIM); US makers' capital spending (and its share of revenue), inventory days and R&D over revenue;
a growth figure keeps its base (from, to) so an unusual one can say it; insurers are summarised by type (life, general, health, reinsurance).
Indian IT services companies' headcount and attrition aren't in any filing the app reads, so that family has none.

Each company's figures are read once and kept in the shared store (computed.py, kind "sector:metrics"), served until a theme's Refresh. A
theme's figures read at most BUDGET seconds of filings while it is built; the rest are read by one worker thread that stops when its short
queue is empty (no job of its own, MAX_QUEUE at most), and the dive is worked out again from the stored pieces once they are in."""
import re
import threading
import time
from datetime import date, datetime
from xml.etree import ElementTree

from .. import computed
from . import metric_registry as registry

KIND = "sector:metrics"
VERSION = 3                     # part of a stored piece's key and of a dive's: figures read under older rules are read again (R27: NII / assets,
                                # capex, inventory days, R&D, the bases of growth figures; dat57: the larger R&D line, a revenue year far
                                # behind the latest report)
BUDGET = 20.0                   # seconds of reading a theme's build may spend on filings before the rest go to the worker
MAX_QUEUE = 200
# r69e (the live REITs theme: FFO and P/FFO missing for most property owners, their US pieces read before a property owner's FFO lines were
# part of the read, kept under VERSION 3 and never read again): the lines a US piece's read holds, kept with it; a property owner's piece
# read before them is read once more (stale_for_property), within the memory guard's turn, never the whole sector's figures (VERSION stays)
REIT_V = 3                      # e81: 2, disposition gains deducted and the FFO the company reports read from its annual report
#                                 e83: 3, the reported FFO read from the row that is the FFO itself (Essex, American Tower: LIVE19A-002/005)
# e79 (LIVE15A-008, the live R77 REITs deck: Camden Property Trust "SBC / revenue 130.8%", its stock pay over the $13 m of fee income its
# piece was read on, beside the $1.57 bn of property revenue its rebuilt page and the appendix give): a US piece keeps the revenue its shares of
# revenue were worked out on ("rev", USD million, REV_V); a piece whose revenue is not the row's own, or one read before it was kept for a
# company whose revenue is now its principal line (sec.PRINCIPAL), is read once more, its shares of revenue withheld meanwhile
REV_V = 1
REV_SHARES = ("sbc_share", "fcf_margin", "capex_share", "rd_share", "rpo_cover", "ffo_share", "affo_share")
REV_GAP = 0.02                  # a revenue apart from the row's by more than this share (theme_changes.REVENUE_SHARE: a restated revenue)
_PROPERTY_ROW = re.compile(r"real estate|\breits?\b|property", re.I)
PAUSE = 1.0                     # seconds between documents from the exchange's archive (shareholders.py's pace)
LIST_PATH = "/api/integrated-filing-results"
REFERER = "https://www.nseindia.com/companies-listing/corporate-integrated-filing"
CRORE = 1e7
FAMILIES = ("bank", "insurer", "us")
# every figure: (key, label, family, format, how it is worked out), from the one registry of figures (R27: metric_registry, which also says
# whom each applies to, its period, source and limitation). Formats: pct (a share, %), chg (a change, %), x (times), amt (money), days
METRICS = tuple((m.id, m.label, m.group, m.unit, m.definition + ".") for m in registry.METRICS if m.group in FAMILIES)
KEYS = tuple(m[0] for m in METRICS)
BY_KEY = {m[0]: m for m in METRICS}
# the filed figure that replaces the page tables' own when a filing gives it (R22: one number per metric wherever it is shown)
REPLACES = {"gnpa_f": "gnpa", "nnpa_f": "nnpa", "nii_growth_f": "nii_growth", "deposit_growth_f": "deposit_growth", "nii_assets_f": "nii_assets"}
# what each family's figures were looked for in, for the notes and the report (the sources checked)
CHECKED = {"bank": "the quarterly results filed with the exchange (banking format)",
           "insurer": "the quarterly results filed with the exchange (life and general insurance formats)",
           "us": "the SEC's company facts (annual reports)"}
NOT_FILED = {"bank": "NIM and CASA aren't elements of the banking results format, and the total capital adequacy ratio isn't in it",
             "insurer": "VNB, APE and embedded value aren't elements of the insurance results formats",
             "us": ""}

_feeds = {"nse": None, "sec": None}


def setup(nse=None, sec=None):
    """Where filings are read from: main.py's exchange and SEC clients (each a callable giving the client), or a test's fakes."""
    _feeds["nse"], _feeds["sec"] = nse, sec


def forget():
    """Drop the queue (between tests)."""
    with _qlock:
        _q.clear()


def family_of(region: str, row: dict) -> str | None:
    """The family whose figures a company has: an Indian bank (or a lender the page flags as a bank: its filing's format decides), an Indian
    insurer, or a US company outside finance; None for every other."""
    prof = row.get("profile") or ("lender" if row.get("bank") else "other")
    if region == "IN":
        return "insurer" if prof == "insurer" else "bank" if prof in ("bank", "lender") else None
    if region == "US":
        # r62: a US insurer reads its underwriting ratios from its own company facts too (us_figures, its premiums earned)
        return "us" if prof in ("other", "insurer") else None
    return None


# ---------- reading a results filing ----------
class BadFiling(ValueError):
    """The document isn't a results filing this reads."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _num(v):
    try:
        x = float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return x if x == x and abs(x) < 1e18 else None


def _day(s) -> date | None:
    try:
        return date.fromisoformat(str(s).strip()[:10])
    except ValueError:
        return None


def parse_results(data: bytes | str) -> dict:
    """A results XBRL as {"symbol", "start", "end", "ytd_start", "standalone", "q": {name: value}, "ytd": {...}, "at": {...}, "names"}:
    the quarter's figures, the year to date's and the period end's (the balance sheet, when the filing has one), from the contexts with no
    dimension. Numbers as filed (rupees; ratios as fractions)."""
    raw = data.encode() if isinstance(data, str) else bytes(data)
    if b"<!DOCTYPE" in raw[:4000].upper() or b"<!ENTITY" in raw.upper():
        raise BadFiling("an XBRL document never needs a DTD")       # rules out entity-expansion tricks
    try:
        root = ElementTree.fromstring(raw)   # nosec B314: a document with a DTD is refused above
    except ElementTree.ParseError:
        raise BadFiling("not XML") from None
    spans: dict[str, tuple] = {}
    facts: dict[str, dict] = {}
    for el in root:
        tag = _local(el.tag)
        if tag == "context":
            if any(x.get("dimension") for x in el.iter()):
                continue
            d = {_local(x.tag): (x.text or "").strip() for x in el.iter() if _local(x.tag) in ("startDate", "endDate", "instant")}
            if d.get("instant"):
                spans[el.get("id") or ""] = (None, _day(d["instant"]))
            elif d.get("startDate") and d.get("endDate"):
                spans[el.get("id") or ""] = (_day(d["startDate"]), _day(d["endDate"]))
        elif el.get("contextRef"):
            facts.setdefault(el.get("contextRef"), {}).setdefault(tag, " ".join((el.text or "").split()))
    spans = {k: v for k, v in spans.items() if v[1] and k in facts}
    if not spans:
        raise BadFiling("no period")
    end = max(v[1] for v in spans.values())
    durs = {k: v for k, v in spans.items() if v[0] and v[1] == end}
    qk = next((k for k, v in sorted(durs.items(), key=lambda t: t[1][0], reverse=True) if 80 <= (v[1] - v[0]).days <= 100), None)
    yk = min(durs, key=lambda k: durs[k][0]) if durs else None
    ik = next((k for k, v in spans.items() if v[0] is None and v[1] == end), None)
    meta = {}
    for f in facts.values():
        for k in ("Symbol", "NatureOfReportStandaloneConsolidated", "ResultType"):
            if f.get(k) and k not in meta:
                meta[k] = f[k]
    nums = lambda k: {n: x for n, t in (facts.get(k) or {}).items() if (x := _num(t)) is not None} if k else {}   # noqa: E731
    return {"symbol": str(meta.get("Symbol") or "").upper(), "end": end.isoformat(), "start": durs[qk][0].isoformat() if qk else None,
            "ytd_start": durs[yk][0].isoformat() if yk else None, "standalone": "consolidated" not in str(meta.get("NatureOfReportStandaloneConsolidated") or "").lower(),
            "q": nums(qk), "ytd": nums(yk), "at": nums(ik), "names": sorted({n for f in facts.values() for n in f})}


def _label(iso: str | None) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%b %Y") if iso else ""


def _months(p: dict) -> int:
    a, b = _day(p.get("ytd_start")), _day(p.get("end"))
    return max(1, round(((b - a).days + 1) / 30.44)) if a and b else 12


def _ratio(v, hi: float = 1.0):
    """A ratio filed as a fraction (0.0111) as a percent (1.11); one filed as a percent already (above `hi`) as it is."""
    return None if v is None else round(v * 100 if abs(v) <= hi else v, 2)


def _within(v, lo, hi):
    return v if v is not None and lo <= v <= hi else None


def _growth(a, b):
    return round((a / b - 1) * 100, 1) if a is not None and b and b > 0 and a > 0 else None


def _find(p: dict, part: str, pat: str):
    """The first figure in a part ("q", "ytd", "at") whose element name matches `pat` (for elements only some filings carry)."""
    rx = re.compile(pat, re.I)
    return next((v for k, v in (p.get(part) or {}).items() if rx.search(k)), None)


def _fig(v, period: str, source: str, base: tuple | None = None, unit: str = "") -> dict | None:
    """One figure with its period and source; a growth figure with its `base` (from, to) in `unit` (R27: an unusual growth says its base)."""
    if v is None:
        return None
    out = {"v": v, "period": period, "source": source}
    if base and None not in base:
        out["base"] = [round(base[0], 1), round(base[1], 1)]
        out["unit"] = unit
    return out


def _cr(v):
    return None if v is None else v / CRORE


def bank_figures(cur: dict, ago: dict | None = None, half: dict | None = None, half_ago: dict | None = None, filed: str = "") -> dict:
    """A bank's figures from its latest results filing (`cur`), the same quarter a year before (`ago`) and, when the latest has no balance sheet,
    the latest half-year filing and the one a year before it (`half`, `half_ago`). Each {"v", "period", "source"}."""
    src = "Results filed with the exchange" + (f" on {filed}" if filed else "") + (", standalone" if cur.get("standalone") else ", consolidated")
    q, ytd, end = cur["q"], cur["ytd"], _label(cur["end"])
    out = {}
    out["gnpa_f"] = _fig(_within(_ratio(q.get("PercentageOfGrossNpa", ytd.get("PercentageOfGrossNpa"))), 0, 40), end, src)
    out["nnpa_f"] = _fig(_within(_ratio(q.get("PercentageOfNpa", ytd.get("PercentageOfNpa"))), 0, 25), end, src)
    out["cet1"] = _fig(_within(_ratio(q.get("CET1Ratio", ytd.get("CET1Ratio"))), 3, 60), end, src)
    nii = (q["InterestEarned"] - q["InterestExpended"]) if q.get("InterestEarned") is not None and q.get("InterestExpended") is not None else None
    out["nii_q"] = _fig(round(nii / CRORE, 1) if nii is not None else None, f"Quarter to {end}", src)
    if ago and nii is not None:
        a = ago["q"]
        before = (a["InterestEarned"] - a["InterestExpended"]) if a.get("InterestEarned") is not None and a.get("InterestExpended") is not None else None
        out["nii_growth_f"] = _fig(_growth(nii, before), f"Quarter to {end} on {_label(ago['end'])}", src, (_cr(before), _cr(nii)), "₹ crore")
    h, h0 = (cur, ago) if cur.get("at", {}).get("Advances") else (half, half_ago)
    if h and h0 and h.get("at") and h0.get("at"):
        hl = f"{_label(h['end'])} on {_label(h0['end'])}"
        out["advances_growth"] = _fig(_growth(h["at"].get("Advances"), h0["at"].get("Advances")), hl, src,
                                      (_cr(h0["at"].get("Advances")), _cr(h["at"].get("Advances"))), "₹ crore")
        out["deposit_growth_f"] = _fig(_growth(h["at"].get("Deposits"), h0["at"].get("Deposits")), hl, src,
                                       (_cr(h0["at"].get("Deposits")), _cr(h["at"].get("Deposits"))), "₹ crore")
        adv = [x for x in (h["at"].get("Advances"), h0["at"].get("Advances")) if x]
        prov = h["ytd"].get("ProvisionsOtherThanTaxAndContingencies")
        assets = [x for x in (h["at"].get("Assets"), h0["at"].get("Assets")) if x]
        profit = h["ytd"].get("ProfitLossForThePeriod")
        if len(assets) == 2 and profit is not None:
            hm = _months(h)
            out["roa_f"] = _fig(_within(round(profit * 12 / hm / (sum(assets) / 2) * 100, 2), -10, 10), f"{hm} months to {_label(h['end'])}, annualised", src)
        # R27: net interest income over average assets from the same filings (the live R26 Banks deck had "–" for most banks' NII / assets: the
        # stored pages' annual tables often lack it, the filings read here carry it); never called a net interest margin
        ie, ix = h["ytd"].get("InterestEarned"), h["ytd"].get("InterestExpended")
        if len(assets) == 2 and ie is not None and ix is not None:
            hm = _months(h)
            out["nii_assets_f"] = _fig(_within(round((ie - ix) * 12 / hm / (sum(assets) / 2) * 100, 2), 0, 15), f"{hm} months to {_label(h['end'])}, annualised", src)
        if len(adv) == 2 and prov is not None:
            hm = _months(h)
            out["credit_cost"] = _fig(_within(round(prov * 12 / hm / (sum(adv) / 2) * 100, 2), -5, 20), f"{hm} months to {_label(h['end'])}, annualised", src)
    out["nim"] = _fig(_within(_ratio(_find(cur, "q", r"netinterestmargin")), 0, 15), end, src)
    out["casa"] = _fig(_within(_ratio(_find(cur, "q", r"casa")), 0, 100), end, src)
    return {k: v for k, v in out.items() if v}


def _solvency(v):
    """The solvency ratio in times: filed as 1.97, or as hundredths (0.0275 for 2.75, one insurer's filing) or as a percent (197)."""
    if v is None or v <= 0:
        return None
    x = v * 100 if v < 0.5 else v / 100 if v > 20 else v
    return _within(round(x, 2), 0.5, 15)


def insurer_figures(cur: dict, ago: dict | None = None, kind: str = "", filed: str = "") -> dict:
    """An insurer's figures from its latest results filing and the same quarter a year before (gross premium's growth)."""
    src = "Results filed with the exchange" + (f" on {filed}" if filed else "")
    q, ytd, end = cur["q"], cur["ytd"], _label(cur["end"])
    ytd_l = f"{_months(cur)} months to {end}"
    out = {"solvency": _fig(_solvency(q.get("SolvencyRatio", ytd.get("SolvencyRatio"))), end, src),
           "claims_ratio": _fig(_within(_ratio(ytd.get("IncurredClaimRatio"), 3), 0, 300), ytd_l, src),
           "combined_ratio": _fig(_within(_ratio(ytd.get("CombinedRatio"), 3), 0, 300), ytd_l, src),
           "persistency_13": _fig(_within(_ratio(ytd.get("PersistencyRatio13ThMonth")), 0, 100), ytd_l, src)}
    gross = lambda p: p["q"].get("GrossPremiumIncome", p["q"].get("GrossPremiumsWritten"))     # noqa: E731
    if ago:
        out["premium_growth"] = _fig(_growth(gross(cur), gross(ago)), f"Quarter to {end} on {_label(ago['end'])}", src, (_cr(gross(ago)), _cr(gross(cur))), "₹ crore")
    vnb = _find(cur, "ytd", r"valueofnewbusiness(?!.*amount)")
    ape = _find(cur, "ytd", r"annuali[sz]edpremiumequivalent")
    margin = _find(cur, "ytd", r"vnbmargin|newbusinessmargin")
    if margin is None and vnb is not None and ape:
        margin = vnb / ape
    out["vnb_margin"] = _fig(_within(_ratio(margin), 0, 100), ytd_l, src)
    return {k: v for k, v in out.items() if v}


# ---------- the exchange's list of results filings ----------
_KIND = re.compile(r"INTEGRATED_FILING_([A-Z]+)_", re.I)
FAMILY_KINDS = {"bank": ("BANKING",), "insurer": ("LI", "GI")}


def _qe(v) -> date | None:
    try:
        return datetime.strptime(str(v or "").strip()[:11].title(), "%d-%b-%Y").date()
    except ValueError:
        return None


def filing_rows(data, family: str) -> list[dict]:
    """The exchange's results list as [{"end": date, "kind", "url", "filed"}], standalone filings of the family's format, the newest filing of
    each quarter, newest quarter first."""
    rows = data.get("data") if isinstance(data, dict) else data
    best: dict = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or "financial" not in str(r.get("type") or "Financials").lower():
            continue
        url = str(r.get("xbrl") or "").strip()
        m = _KIND.search(url)
        end = _qe(r.get("qe_Date"))
        cons = str(r.get("consolidated") or "").lower()
        if not m or m.group(1).upper() not in FAMILY_KINDS.get(family, ()) or not end or (cons and "standalone" not in cons and "non-consolidated" not in cons):
            continue
        filed = str(r.get("broadcast_Date") or "")
        try:
            stamp = datetime.strptime(filed.strip().title(), "%d-%b-%Y %H:%M:%S")
        except ValueError:
            stamp = datetime.min
        if end not in best or stamp > best[end]["stamp"]:
            best[end] = {"end": end, "kind": m.group(1).upper(), "url": url, "filed": stamp.date().isoformat() if stamp != datetime.min else "", "stamp": stamp}
    return sorted(best.values(), key=lambda x: x["end"], reverse=True)


def _year_before(rows: list[dict], end: date) -> dict | None:
    return next((r for r in rows if 350 <= (end - r["end"]).days <= 380), None)


def read_india(symbol: str, family: str, nse, fetch=None, pause: float = PAUSE) -> dict:
    """A bank's or an insurer's figures from the exchange: its results list, then the latest filing, the one a year before and, for a bank
    whose latest has no balance sheet, the latest half-year filing and the one a year before (five reads at most)."""
    from .. import shareholders
    fetch = fetch or (lambda url: shareholders.fetch_xbrl(nse, url))
    data = nse._get(LIST_PATH, {"index": "equities", "symbol": symbol, "type": "Integrated Filing- Financials"}, referer=REFERER, circuit="metrics")
    rows = filing_rows(data, family)
    if not rows:
        return {"family": family, "none": f"no {family} results filing in XBRL on the exchange", "metrics": {}}
    docs: dict = {}

    def doc(r):
        if r is None:
            return None
        if r["url"] not in docs:
            if docs and pause:
                time.sleep(pause)
            try:
                docs[r["url"]] = parse_results(fetch(r["url"]))
            except BadFiling:
                docs[r["url"]] = None
        return docs[r["url"]]
    top = rows[0]
    cur, ago = doc(top), doc(_year_before(rows, top["end"]))
    if not cur:
        return {"family": family, "none": "the latest results filing couldn't be read", "metrics": {}}
    if family == "bank":
        half = half_ago = None
        if not cur.get("at", {}).get("Advances"):
            h = next((r for r in rows if r["end"].month in (3, 9) and r["end"] < top["end"]), None)
            half = doc(h)
            half_ago = doc(_year_before(rows, h["end"])) if h else None
        got = bank_figures(cur, ago, half, half_ago, filed=top["filed"])
    else:
        got = insurer_figures(cur, ago, top["kind"], filed=top["filed"])
    return {"family": family, "kind": top["kind"], "end": cur["end"], "metrics": got}


# ---------- the SEC's company facts ----------
SBC = ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense", "ShareBasedPaymentArrangementNoncashExpense")
CFO = ("NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")
CAPEX = ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets")
RPO = ("RevenueRemainingPerformanceObligation",)
DEFERRED = ("ContractWithCustomerLiability", "DeferredRevenue")
DEFERRED_PARTS = (("ContractWithCustomerLiabilityCurrent", "ContractWithCustomerLiabilityNoncurrent"), ("DeferredRevenueCurrent", "DeferredRevenueNoncurrent"))
INVENTORY = ("InventoryNet", "InventoryGross")
RD = ("ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost")
# r62 (the owner's review of the live R60 decks, P0 sector metric schemas): a REIT's funds from operations, from its own filed lines (net income
# + real-estate depreciation and amortisation − gains on sales of property; AFFO less its recurring capital spending where filed), and a P&C
# insurer's underwriting ratios (loss, expense and combined), each only where its company facts file the lines
PROPERTY = ("RealEstateInvestmentPropertyNet", "RealEstateInvestmentPropertyAtCost", "RealEstateGrossAtCarryingValue")
RE_DEPRECIATION = ("RealEstateDepreciationAndAmortization", "DepreciationAndAmortizationRealEstate", "DepreciationDepletionAndAmortization",
                   "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet")
# e81 (the owner's review of the R79 REITs deck, P0: Camden's derived FFO $996 m against its reported Nareit FFO $744.8 m): Camden files its
# $260.9 m of gains on property sales as "GainLossOnDispositionOfAssets", a tag the read did not know, so no gain was deducted; a property
# owner's disposition gains are its property sales' (the read runs only for a filer holding real-estate property)
PROPERTY_GAINS = ("GainsLossesOnSalesOfInvestmentRealEstate", "GainLossOnSaleOfRealEstateInvestmentProperty", "GainLossOnSaleOfProperties",
                  "GainLossOnDispositionOfRealEstate", "GainLossOnSaleOfPropertyPlantEquipment", "GainLossOnDispositionOfAssets",
                  "GainLossOnDispositionOfAssets1")
RECURRING_CAPEX = ("PaymentsForCapitalImprovements", "PaymentsToDevelopRealEstateAssetsRecurring")
PREMIUMS_EARNED = ("PremiumsEarnedNet",)
CLAIMS_INCURRED = ("PolicyholderBenefitsAndClaimsIncurredNet", "LiabilityForClaimsAndClaimsAdjustmentExpenseIncurredClaims1")
UNDERWRITING_COSTS = (("DeferredPolicyAcquisitionCostAmortizationExpense",), ("OtherUnderwritingExpense", "UnderwritingExpenses",
                                                                               "GeneralInsuranceExpense"))


def reit_figures(facts: dict, end: str, unit: str, r: float, fy: str, src: str) -> dict:
    """r62: a property owner's FFO and AFFO for the fiscal year ending `end` (USD million, with their share of revenue), from its filed net income,
    real-estate depreciation and amortisation and gains on property sales; AFFO only where its recurring capital spending is filed. {} for a
    company that files no real-estate property or no depreciation."""
    from . import sec
    if not any(sec.instants(facts, (c,), unit) for c in PROPERTY):
        return {}
    ni = sec.flows(facts, sec.NET_INCOME, "annual", unit).get(end)
    da = sec.flows(facts, RE_DEPRECIATION, "annual", unit).get(end)
    if ni is None or da is None:
        return {}
    gains = sec.flows(facts, PROPERTY_GAINS, "annual", unit).get(end) or 0.0
    ffo = ni + abs(da) - gains
    lines = f"net income {ni / MILLION:,.1f} + depreciation and amortisation {abs(da) / MILLION:,.1f} − gains on property sales {gains / MILLION:,.1f}"
    out = {"ffo": _fig(round(ffo / MILLION, 1), fy, f"{src}: {lines}") if unit == "USD" else None,
           "ffo_share": _fig(_within(round(ffo / r * 100, 1) if r and r > 0 else None, -200, 300), fy, f"{src}: {lines}")}
    capex = sec.flows(facts, RECURRING_CAPEX, "annual", unit).get(end)
    if capex is not None:
        affo = ffo - abs(capex)
        out["affo"] = _fig(round(affo / MILLION, 1), fy, f"{src}: FFO less recurring capital spending {abs(capex) / MILLION:,.1f}") if unit == "USD" else None
        out["affo_share"] = _fig(_within(round(affo / r * 100, 1) if r and r > 0 else None, -200, 300), fy,
                                 f"{src}: FFO less recurring capital spending {abs(capex) / MILLION:,.1f}")
    return {k: v for k, v in out.items() if v}


def insurer_ratios(facts: dict, end: str, unit: str, fy: str, src: str) -> dict:
    """r62: a P&C insurer's loss ratio (claims and claim expenses incurred over premiums earned), expense ratio (policy acquisition and other
    underwriting expenses over premiums earned) and combined ratio (their sum), for the fiscal year ending `end`; each only where its lines are
    filed (no expense ratio, and so no combined ratio, without them)."""
    from . import sec
    prem = sec.flows(facts, PREMIUMS_EARNED, "annual", unit).get(end)
    if not prem or prem <= 0:
        return {}
    out = {}
    claims = sec.flows(facts, CLAIMS_INCURRED, "annual", unit).get(end)
    loss = round(claims / prem * 100, 1) if claims is not None else None
    out["loss_ratio"] = _fig(_within(loss, 0, 300), fy, src)
    parts = [sec.flows(facts, cs, "annual", unit).get(end) for cs in UNDERWRITING_COSTS]
    cost = sum(abs(x) for x in parts if x is not None) if any(x is not None for x in parts) else None
    exp = round(cost / prem * 100, 1) if cost is not None else None
    out["expense_ratio"] = _fig(_within(exp, 0, 200), fy, src)
    if loss is not None and exp is not None:
        out["combined_ratio"] = _fig(_within(round(loss + exp, 1), 0, 400), fy, src)
    return {k: v for k, v in out.items() if v}
STALE_DAYS = 548            # about 18 months: a period this far behind the company's own latest report, or the theme's typical latest one, isn't current
MILLION = 1e6


def us_figures(facts: dict) -> dict:
    """A US company's figures from its company facts: shares of the latest fiscal year's revenue and growth on a year before, so the filing's
    currency doesn't matter. Each {"v", "period", "source"}."""
    from . import sec
    facts = sec.drop_scale_slips(facts.get("facts") or {}) if "facts" in facts else facts
    unit = sec.currency(facts) or "USD"
    rev = sec.revenue(facts, "annual", unit)
    if not rev:
        return {}
    end = max(rev)
    # a revenue year far behind the company's own latest annual report (lane dat57: Agassi Sports Entertainment's FY2025 10-K tags no
    # revenue, its latest revenue is of 2014/2015, and the R56 retail deck listed its figures as of "FY Dec 2014"): not current, none shown
    latest = max((e for e in sec.flows(facts, sec.NET_INCOME + sec.OPERATING, "annual", unit)), default=end)
    if (_day(latest) - _day(end)).days > STALE_DAYS:
        return {"_stale": end}
    fy = f"Fiscal year to {_label(end)}"
    src = "Annual report (10-K) facts filed with the SEC"
    r = rev[end]
    out = {}
    # r62: an insurer's figures are its underwriting ratios (an insurer's stock pay and free cash flow say nothing of how it underwrites)
    ins = insurer_ratios(facts, end, unit, fy, src)
    if ins:
        return {**ins, "_end": end}
    out.update(reit_figures(facts, end, unit, r, fy, src))
    share = lambda v: round(v / r * 100, 1) if v is not None and r and r > 0 else None      # noqa: E731
    sbc = sec.flows(facts, SBC, "annual", unit).get(end)
    out["sbc_share"] = _fig(_within(share(sbc), 0, 200), fy, src)
    cfo, capex = sec.flows(facts, CFO, "annual", unit).get(end), sec.flows(facts, CAPEX, "annual", unit).get(end)
    out["fcf_margin"] = _fig(_within(share(cfo - abs(capex)) if cfo is not None and capex is not None else None, -500, 200), fy, src)
    # R27: a maker's own figures (semiconductors and hardware): capital spending, inventory days, R&D; each only where filed
    if capex is not None:
        out["capex_share"] = _fig(_within(share(abs(capex)), 0, 300), fy, src)
        if unit == "USD":                   # an amount only in the theme's currency (a share needs none)
            out["capex"] = _fig(round(abs(capex) / MILLION, 1), fy, src)
    cost = sec.flows(facts, sec.COST_OF_SALES, "annual", unit).get(end)
    inv = sec.instants(facts, INVENTORY, unit).get(end)
    if cost and cost > 0 and inv is not None and inv >= 0:
        out["inventory_days"] = _fig(_within(round(inv / cost * 365), 0, 2000), f"{_label(end)}, over the fiscal year to {_label(end)}", src)
    # the larger of the two R&D lines: the total includes the part without acquired in-process R&D, so a total filed below that part is
    # another line under the total's name (lane dat57: Johnson & Johnson's 2025 10-K gives $109 m as ResearchAndDevelopmentExpense
    # beside $14,665 m excluding acquired in-process R&D, and its R&D showed 0.1% of revenue against 15.6%)
    rds = [v for v in (sec.flows(facts, (c,), "annual", unit).get(end) for c in RD) if v is not None]
    rd = max(rds) if rds else None
    out["rd_share"] = _fig(_within(share(rd), 0, 300), fy, src)
    rpo = sec.instants(facts, RPO, unit)
    if rpo:
        last = max(rpo)
        at = end if end in rpo else last           # at the fiscal year's end where filed, over that year's revenue
        out["rpo_cover"] = _fig(round(rpo[at] / r, 2) if r and r > 0 and rpo[at] > 0 else None,
                                f"{_label(at)}, over the fiscal year to {_label(end)}", "Filed with the SEC")
        prior = next((d for d in sorted(rpo, reverse=True) if 350 <= (_day(last) - _day(d)).days <= 380), None)
        if prior:
            out["rpo_growth"] = _fig(_growth(rpo[last], rpo[prior]), f"{_label(last)} on {_label(prior)}", "Filed with the SEC",
                                     (rpo[prior] / MILLION, rpo[last] / MILLION), f"{unit} million")
    years = sorted(rev)
    prev = years[-2] if len(years) > 1 and 350 <= (_day(end) - _day(years[-2])).days <= 380 else None
    if prev:
        dr = sec.instants(facts, DEFERRED, unit)
        if end not in dr or prev not in dr:
            for a, b in DEFERRED_PARTS:
                ca, cb = sec.instants(facts, (a,), unit), sec.instants(facts, (b,), unit)
                if all(d in ca for d in (end, prev)):
                    dr = {d: ca[d] + cb.get(d, 0.0) for d in (end, prev)}
                    break
        if end in dr and prev in dr:
            out["deferred_growth"] = _fig(_growth(dr[end], dr[prev]), f"{_label(end)} on {_label(prev)}", src, (dr[prev] / MILLION, dr[end] / MILLION),
                                          f"{unit} million")
    out = {k: v for k, v in out.items() if v}
    return {**out, "_end": end} if out else out


def us_revenue(facts: dict, end: str | None) -> float | None:
    """e79: the fiscal year's revenue (USD million) a US piece's shares of revenue are worked out on (us_figures' own reading), None for
    another currency or no year."""
    from . import sec
    facts = sec.drop_scale_slips(facts.get("facts") or {}) if "facts" in facts else facts
    unit = sec.currency(facts) or "USD"
    r = sec.revenue(facts, "annual", unit).get(end) if end and unit == "USD" else None
    return round(r / MILLION, 3) if r else None


# e81 (the owner's review of the R79 REITs deck, P0 "reported Nareit FFO first"): the FFO a property owner reports, from its annual report's
# reconciliation (Item 7: "FFO attributable to common shareholders ... $ 744,814", "Funds from operations (as defined by Nareit) ..."), the
# fiscal year's column first; never a Core, Normalized, Adjusted or per-share line. Amounts in thousands unless the text says millions
# e83 (LIVE19A-002/005: Essex "$305 m (reported)", P/FFO 56.80x, read from its line "Gains not included in FFO (305,043)" while its 10-K's
# "Funds from operations attributable to common stockholders and unitholders $ 1,065,136" was passed over; American Tower's "Nareit FFO
# attributable to American Tower Corporation common stockholders $ 4,160.9" (in millions) missed, as were Prologis' "NAREIT defined FFO
# attributable to common stockholders/unitholders", Public Storage's "FFO allocable to common shares", Digital Realty's "FFO available to
# common stockholders and unitholders" and Simon's "FFO of the Operating Partnership"): a reported FFO is the amount of a reconciliation row
# whose label is the FFO itself: nothing before "FFO" but "Nareit" (or "Nareit defined", "Total"; never "Gains not included in",
# "Core", "share of"), after it only how it is defined ("(Nareit)", "as defined by Nareit", a footnote mark), whom it is attributable,
# available or allocable to, "of the Operating Partnership" or ", basic"/", diluted"; its amount positive, in the table's own unit (the
# nearest "in thousands" or "in millions" before it); and, where StratLab's derived FFO is known, of its order (FFO_NEAR): a figure a
# fraction or a multiple of it is another line's (one quarter's, a joint venture's), never the company's year
_FFO_WORD = re.compile(r"(?:funds\s+from\s+operations|\bFFO\b(?!A))", re.I)
_FFO_TAIL = re.compile(r"(?:\s*\(\s*[a-z0-9]{1,2}\s*\)|\s*[⁽⁾⁰¹²³⁴⁵⁶⁷⁸⁹]+|\s*\(\s*[“\"']?(?:Nareit\s+)?FFO[”\"']?\s*\)|\s*\(\s*as\s+defined\s+by\s+nareit\s*\)"
                       r"|\s*\(\s*nareit(?:[\s-]+defined)?\s*\)|\s*,?\s*as\s+defined\s+by\s+nareit\s*,?|\s*[-–—]\s*nareit)*"
                       r"(?:\s+(?:attributable|available|allocable)\s+(?:to|for)\s+(?P<who>[^$\d:;()%]{1,100}?))?"
                       r"(?:\s+of\s+the\s+operating\s+partnership)?(?:\s*[,–—-]\s*(?:basic|diluted))?"
                       r"(?:\s*\(\s*[a-z0-9]{1,2}\s*\)|\s*[⁽⁾⁰¹²³⁴⁵⁶⁷⁸⁹]+)*\s*[:\-–]?\s*(?P<dollar>\$)?\s*(?P<amt>\(?\d[\d,]*(?:\.\d+)?\)?)(?![\d,.]*\s*%)", re.I)
_FFO_HEAD_OK = {"", "nareit", "nareit defined", "nareitdefined", "total"}
_FFO_WHO_NOT = re.compile(r"\b(?:net\s+income|net\s+earnings|income|loss|core|adjusted|normali[sz]ed|non-?controlling|limited\s+partners)\b", re.I)
_FFO_NOT = re.compile(r"\b(?:core|normali[sz]ed|adjusted|as\s+adjusted|per\s+(?:diluted\s+)?(?:share|unit)|AFFO|modified|recurring)\b", re.I)
_SCALE = re.compile(r"in\s+millions|\(\s*millions|millions\s+of\s+(?:U\.S\.\s+)?dollars|in\s+thousands|\(\s*thousands|thousands\s+of\s+(?:U\.S\.\s+)?dollars"
                    r"|\$\s*000s?\b|\(\s*\$\s*000", re.I)
FFO_NEAR = (0.4, 2.5)              # e83: a reported FFO this far (a share or a multiple) from the derived one is another line's figure
FFO_SHARE = (0.05, 1.5)            # e83: ... and, with no derived FFO to hold it to, one this small or large a share of revenue (a joint venture's)


def _ffo_scale(t: str, at: int) -> str | None:
    """e83: the unit of a table, from the nearest "in thousands"/"in millions" (or "$000") said before position `at`; None with none."""
    last = None
    for m in _SCALE.finditer(t, max(0, at - 8000), at):
        last = m
    if last is None:
        return None
    return "m" if "million" in last.group(0).lower() else "k"


def reported_ffo(text: str, near: float | None = None, revenue: float | None = None) -> float | None:
    """e81: a property owner's FFO as its annual report states it ($ million), or None. e83: the first row of its reconciliation whose label is
    the FFO itself (see above), its amount positive and in the table's unit; with `near` (StratLab's derived FFO, $ million, positive) only
    a figure within FFO_NEAR of it, else with `revenue` ($ million) only one within FFO_SHARE of it."""
    t = " ".join(str(text or "").replace("\u200b", " ").replace("\xa0", " ").split())
    # a row that says whom the FFO is attributable (or available, allocable) to first: a bare "Funds from operations" row of a report that has
    # one is a joint venture's or a segment's table; the bare rows only where no such row is the company's FFO
    for whose in (True, False):
        got = _ffo_rows(t, near, revenue, whose)
        if got is not None:
            return got
    return None


def _ffo_rows(t: str, near: float | None, revenue: float | None, whose: bool) -> float | None:
    for w in _FFO_WORD.finditer(t):
        m = _FFO_TAIL.match(t, w.end())
        if not m or bool(m.group("who")) != whose:
            continue
        # the row's label before "FFO": back to the previous row's last figure (or a mark that ends a label)
        lead = t[max(0, w.start() - 80):w.start()]
        cut = max((lead.rfind(ch) for ch in "0123456789)]—–$%:"), default=-1)
        head = re.sub(r"[^a-z ]+", "", lead[cut + 1:].lower()).strip()
        head = " ".join(head.split())
        if head not in _FFO_HEAD_OK or _FFO_NOT.search(m.group(0)) or (m.group("who") and _FFO_WHO_NOT.search(m.group("who"))):
            continue
        unit = _ffo_scale(t, w.start())
        # the row's figures: the fiscal year's column first; a later column (a table of quarters, then the year) only where the first is
        # not of the derived FFO's order
        row = [m.group("amt")] + _ROW_MORE.match(t, m.end()).group(0).replace("$", " ").split()[:4]
        for raw in row:
            if raw.startswith("(") or raw.endswith(")"):
                break                                 # a negative figure: a deduction's row, never the year's FFO
            try:
                v = float(raw.replace(",", ""))
            except ValueError:
                break
            if unit == "m" or (unit is None and re.search(r"\.\d$", raw) and "," in raw):
                mn = v                                # "(in millions)", or a table of figures to one decimal (never one of thousands)
            elif v >= 1000 and "," in raw:
                mn = v / 1000.0                       # "(in thousands)", the usual table
            else:
                break
            if not 1 <= mn <= 50000:
                break
            if isinstance(near, (int, float)) and near > 0:
                if not FFO_NEAR[0] * near <= mn <= FFO_NEAR[1] * near:
                    continue
            elif isinstance(revenue, (int, float)) and revenue > 0 and not FFO_SHARE[0] * revenue <= mn <= FFO_SHARE[1] * revenue:
                continue
            return round(mn, 1)
    return None


_ROW_MORE = re.compile(r"(?:\s*\$?\s*\(?\d[\d,]*(?:\.\d+)?\)?(?![\d,.]*\s*%))*")


def with_reported_ffo(got: dict, text: str, r_million: float | None) -> dict:
    """e81: a US piece's figures with the FFO its annual report states in place of the derived one (kept as "ffo_derived"), each FFO marked by
    its basis ("reported" or "derived"); the figures as they are with no FFO."""
    if not isinstance(got.get("ffo"), dict):
        return got
    der = got["ffo"].get("v")
    rep = reported_ffo(text, der if isinstance(der, (int, float)) and der > 0 else None, r_million) if text else None
    if rep is None:
        return {**got, "ffo": {**got["ffo"], "basis": "derived"}}
    period = got["ffo"].get("period")
    out = {**got, "ffo_derived": {**got["ffo"], "basis": "derived"},
           "ffo": {"v": rep, "period": period, "source": "Annual report (10-K): FFO as the company reports it (Nareit's definition)", "basis": "reported"}}
    if r_million and r_million > 0:
        out["ffo_share"] = {"v": _within(round(rep / r_million * 100, 1), -200, 300), "period": period,
                            "source": "Annual report (10-K): FFO as the company reports it, over revenue", "basis": "reported"}
        if out["ffo_share"]["v"] is None:
            out.pop("ffo_share")
    return out


def annual_report_text(sec_client, cik: int) -> str:
    """e81: the text of the company's latest annual report (10-K), "" when it can't be read."""
    from . import sec
    try:
        f = sec.latest_filing(sec_client.submissions(cik), ("10-K",))
        if not f or not f.get("doc"):
            return ""
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{f['accn'].replace('-', '')}/{f['doc']}"
        return sec.html_text(sec_client.document(url))
    except Exception as e:
        print("sector metrics: annual report not read for FFO:", cik, type(e).__name__, str(e)[:100])
        return ""


def read_us(symbol: str, sec_client) -> dict:
    cik = sec_client.cik(symbol)
    facts = sec_client._json(f"/api/xbrl/companyfacts/CIK{cik:010d}.json")
    # data100: the SEC's facts named for another registrant are a combined report's main registrant's (NSTAR Electric's are Eversource's):
    # none of them is this company's
    from . import sec
    try:
        own = sec.own_name(facts, sec_client.submissions(cik))
    except Exception:
        own = True
    if not own:
        return {"family": "us", "metrics": {}, "end": None, "none": "the SEC's company facts are another registrant's (a combined report)"}
    got = us_figures(facts or {})
    end = got.pop("_end", None)
    if isinstance(got.get("ffo"), dict):          # e81: a property owner: the FFO it reports first
        got = with_reported_ffo(got, annual_report_text(sec_client, cik), us_revenue(facts or {}, end) if end else None)
    rev = us_revenue(facts or {}, end) if got and not got.get("_stale") else None
    if got.get("_stale"):
        return {"family": "us", "metrics": {}, "end": None, "none": f"latest figures are for FY {_label(got['_stale'])}"}
    return {"family": "us", "metrics": got, "end": end, **({"rev": rev} if rev else {}),
            **({} if got else {"none": "no revenue in the SEC's company facts"})}


# ---------- kept once, read within a budget ----------
def key(region: str, symbol: str) -> list:
    return [region, symbol, VERSION]


def stored(region: str, symbol: str) -> dict | None:
    hit = computed.get(KIND, key(region, symbol), count=False)
    return hit["value"] if hit and isinstance(hit.get("value"), dict) else None


def read(region: str, symbol: str, family: str) -> dict | None:
    """Read a company's figures from its filings now and keep them; None when the source couldn't be reached (nothing kept, read again later)."""
    try:
        if family == "us":
            client = _feeds["sec"]() if _feeds["sec"] else None
            if client is None:
                return None
            got = read_us(symbol, client)
        else:
            feed = _feeds["nse"]() if _feeds["nse"] else None
            nse = getattr(feed, "nse", feed)
            if nse is None:
                return None
            got = read_india(symbol, family, nse)
    except Exception as e:
        print("sector metrics: not read:", region, symbol, type(e).__name__, str(e)[:100])
        return None
    if family == "us":
        got = {**got, "reit_v": REIT_V, "rev_v": REV_V}          # r69e: read with a property owner's FFO lines; e79: with its revenue
    computed.put(KIND, key(region, symbol), got, label=symbol, region=region)
    return got


def property_row(row: dict) -> bool:
    """r69e: a company whose industry names real estate or property (a REIT, a property owner), from its page's or the map's industry."""
    ind = row.get("industry")
    text = " ".join([*(ind if isinstance(ind, (list, tuple)) else [ind or ""]), str(row.get("map_industry") or ""), str(row.get("sector") or "")])
    return bool(_PROPERTY_ROW.search(text))


def stale_for_property(row: dict, piece: dict | None) -> bool:
    """r69e: a US property owner's piece read before its FFO lines were part of the read (no "reit_v"): read once more."""
    return isinstance(piece, dict) and piece.get("family") == "us" and int(piece.get("reit_v") or 0) < REIT_V and property_row(row)


def current_piece(piece: dict | None) -> bool:
    """r69e: a stored piece that stands as read (any piece but a US one read before the FFO lines; that one stands only off a property owner)."""
    return isinstance(piece, dict) and (piece.get("family") != "us" or int(piece.get("reit_v") or 0) >= REIT_V)


def fresh_piece(piece: dict | None) -> bool:
    """e79: a stored piece that stands as read now (current_piece), a US one read with the revenue its shares are of (REV_V)."""
    return current_piece(piece) and (piece.get("family") != "us" or int(piece.get("rev_v") or 0) >= REV_V)


def stale_for_revenue(row: dict, piece: dict | None) -> bool:
    """e79: whether a US piece's shares of revenue rest on another revenue than its row's: the piece's revenue ("rev") more than REV_GAP from
    the row's for the same fiscal year, or, for a piece read before its revenue was kept, a row whose revenue its page reads from the principal
    revenue line (sec.PRINCIPAL: the rule that changed it, e78)."""
    from .sec import PRINCIPAL
    if not isinstance(piece, dict) or piece.get("family") != "us" or not piece.get("metrics") or not isinstance(row, dict):
        return False
    if int(piece.get("rev_v") or 0) < REV_V:
        return str(row.get("rev_line") or "") in PRINCIPAL
    rev, own = piece.get("rev"), row.get("revenue")
    if not isinstance(rev, (int, float)) or not isinstance(own, (int, float)) or own <= 0 or row.get("currency") not in (None, "USD"):
        return False
    return _label(piece.get("end")) == str(row.get("year") or "") and abs(rev - own) > REV_GAP * own


def withhold_shares(row: dict) -> list[str]:
    """e79: a row's shares of revenue taken off while its piece is read again on its row's revenue (stale_for_revenue); the keys taken."""
    gone = [k for k in REV_SHARES if row.get(k) is not None]
    for k in gone:
        row.pop(k, None)
        (row.get("sector_src") or {}).pop(k, None)
    return gone


_q: list = []
_qlock = threading.Lock()
_worker = {"on": False}


def _work():
    while True:
        with _qlock:
            if not _q:
                _worker["on"] = False
                return
            region, symbol, family, *again = _q.pop(0)
        if again and again[0]:
            # r69e: a property owner's piece read again for its FFO lines, once (it is kept with them), in the memory guard's turn; e79: or
            # for the revenue its shares are of ("rev": a piece read before that revenue was kept with it)
            if not (fresh_piece if again[0] == "rev" else current_piece)(stored(region, symbol)):
                from .. import memguard
                with memguard.heavy("sector metrics: property lines"):
                    read(region, symbol, family)
        elif stored(region, symbol) is None:
            read(region, symbol, family)


def queue(region: str, symbol: str, family: str, again: bool | str = False) -> None:
    """Read later, on the one worker thread (started here, it stops when the queue is empty). Nothing is queued with no source set up.
    `again` (r69e): read even though a piece is stored (a property owner's piece without its FFO lines); e79: "rev", a piece read before the
    revenue its shares are of was kept with it."""
    if _feeds["sec" if family == "us" else "nse"] is None:
        return
    item = (region, symbol, family, again) if again else (region, symbol, family)
    with _qlock:
        if item in _q or (region, symbol, family) in _q or len(_q) >= MAX_QUEUE:
            return
        _q.append(item)
        if _worker["on"]:
            return
        _worker["on"] = True
    threading.Thread(target=_work, name="sector-metrics", daemon=True).start()


def reader(region: str, fresh: bool = False, budget: float = BUDGET):
    """A dive's reader: (symbol, family) -> the stored piece, read now while the budget lasts, else queued for the worker (None, said as
    pending). With `fresh` (a Refresh) a stored piece is read again while the budget lasts."""
    until = [None]

    def get(symbol: str, family: str):
        kept = stored(region, symbol)
        if kept is not None and not fresh:
            return kept
        if until[0] is None:
            until[0] = time.time() + budget
        if time.time() < until[0]:
            got = read(region, symbol, family)
            if got is not None:
                return got
        if kept is None:
            queue(region, symbol, family)
        return kept

    def again(symbol: str, family: str, rev: bool = False):
        """r69e: a stored piece read once more (a property owner's, for its FFO lines; e79, `rev`: for the revenue its shares are of): now
        while the budget lasts, else on the worker."""
        if until[0] is None:
            until[0] = time.time() + budget
        if time.time() < until[0]:
            got = read(region, symbol, family)
            if got is not None:
                return got
        queue(region, symbol, family, again="rev" if rev else True)
        return None
    get.again = again
    return get


def any_stored(region: str, symbols: list) -> bool:
    """Whether a figure a dive was waiting for has been kept since (the dive is then worked out again from the stored pieces)."""
    if not symbols:
        return False
    ix = computed.index(KIND).get("entries") or {}
    # r69e: a pending piece counts once it is stored as read now (a property owner's re-read with its FFO lines, not its older piece)
    return any(computed.hkey(key(region, s)) in ix and current_piece(stored(region, s)) for s in symbols)


# ---------- a theme's figures ----------
def apply(row: dict, piece: dict | None) -> None:
    """A company's line takes its filed figures (each under its key, `sector_src` keeping period, source and a growth figure's base), and a filed
    gross or net NPA, NII growth, deposit growth or NII / assets replaces the page tables' own figure (one number per metric). An insurer's
    filing format (LI, GI) is kept as `sector_kind` (its type: metric_registry.insurer_type)."""
    got = (piece or {}).get("metrics") or {}
    row["sector_src"] = {}
    end = (piece or {}).get("end")
    row["sector_as_of"] = (("FY " if (piece or {}).get("family") == "us" else "") + _label(end)) if end and got else None
    row["sector_end"] = end if end and got else None
    if (piece or {}).get("kind"):
        row["sector_kind"] = piece["kind"]
    for k, fig in got.items():
        if k in BY_KEY and isinstance(fig, dict) and fig.get("v") is not None:
            row[k] = fig["v"]
            row["sector_src"][k] = {x: fig[x] for x in ("period", "source", "base", "unit") if fig.get(x) is not None}
            if k in REPLACES:
                row[REPLACES[k]] = fig["v"]
                row.setdefault("filed_basis", []).append(REPLACES[k])
    # r62: a property owner's price to its funds from operations (market value and FFO both in USD million), in place of its P/E
    ffo, cap = row.get("ffo"), row.get("cap")
    if "ffo" in got and isinstance(got["ffo"], dict):
        row["ffo_basis"] = got["ffo"].get("basis") or "derived"          # e81: reported (the company's own Nareit FFO) or derived
    if isinstance(ffo, (int, float)) and ffo > 0 and isinstance(cap, (int, float)) and cap > 0 and "ffo" in got:
        row["p_ffo"] = round(cap / ffo, 1)
        row["sector_src"]["p_ffo"] = {"period": (got["ffo"] or {}).get("period"),
                                      "source": "market value over FFO as the company reports it" if row.get("ffo_basis") == "reported"
                                      else "market value over derived FFO"}


INSURER_TYPES = ("life", "general", "health", "reinsurance")
TYPE_NAMES = {"life": ("life insurer", "life insurers"), "general": ("general insurer", "general insurers"),
              "health": ("health insurer", "health insurers"), "reinsurance": ("reinsurer", "reinsurers")}


def _summary(rows: list[dict], keys: list[str], region: str, tagsets: list[set], stat, rest: list[set] | None = None) -> dict:
    """One group's figures: each company's state per figure, each figure's median over its "value" rows with the count it applies to, the
    unusual growth figures with their bases, and the figures that may headline (metric_registry.headline_ok). `rest`: the tags of the group's
    companies with no filed figure yet (none filed, or still being read: R29): each counts in the M of "N of M" of every figure that applies
    to it, so a median of 7 banks read is "7 of 19", never "7"."""
    sts = {k: registry.states(k, region, rows, tagsets) for k in keys}
    main = registry.main_family(tagsets)
    meds, extreme, head = {}, [], []
    for k in keys:
        vals = [r.get(k) for r in rows]
        meds[k] = registry.coverage(vals, sts[k], stat)
        meds[k]["of"] += sum(1 for t in rest or () if registry.applies(k, region, t))
        n_ext = 0
        if BY_KEY[k][3] == "chg":
            bases = [((r.get("src") or {}).get(k) or {}).get("base") for r in rows]
            froms = [b[0] for b, s_ in zip(bases, sts[k]) if b and s_ == registry.VALUE]
            mid = sorted(froms)[len(froms) // 2] if froms else None
            for r, b, s_ in zip(rows, bases, sts[k]):
                if s_ == registry.VALUE and registry.is_extreme(r.get(k), b[0] if b else None, mid):
                    n_ext += 1
                    extreme.append({"symbol": r["symbol"], "name": r["name"], "key": k, "v": r.get(k), "base": b,
                                    "unit": ((r.get("src") or {}).get(k) or {}).get("unit")})
        if registry.headline_ok(k, meds[k], registry.fits_main(k, region, tagsets, main), n_ext):
            head.append(k)
    return {"states": sts, "medians": meds, "extreme": extreme, "headline": head, "main": main}


def one_ffo_basis(rows: list[dict], keys: list[str], meds: dict, stat) -> dict:
    """e82 (LIVE18A-007, the R80 REITs deck: "derived FFO / revenue 41.8% (79 of 89), P/FFO (derived) 16.20x (79 of 89)", 36 of them the
    companies' reported FFO): the theme's FFO medians are of one basis, the FFO its companies report where most of those with one report it,
    else the derived one (theme_data.layer_block's rule); {"medians", "ffo_basis", "ffo_apart"}, {} with no FFO figure."""
    fk = [k for k in keys if k in registry.FFO_BASIS_KEYS]
    with_ = [r for r in rows if any(r.get(k) is not None for k in fk)]
    if not fk or not with_:
        return {}
    rep_n = sum(1 for r in with_ if r.get("ffo_basis") == "reported")
    basis = "reported" if rep_n and rep_n * 2 >= len(with_) else "derived"
    same = [r for r in with_ if (r.get("ffo_basis") or "derived") == basis]
    out = dict(meds)
    for k in fk:
        st = stat(r.get(k) for r in same if r.get(k) is not None) or {}
        out[k] = {**{x: y for x, y in (meds.get(k) or {}).items() if x != "median"}, **st, "n": st.get("n", 0),
                  "of": (meds.get(k) or {}).get("of"), "basis": basis}
    return {"medians": out, "ffo_basis": basis, "ffo_apart": len(with_) - len(same)}


def section(rows: list[dict], region: str, layer_of: dict, pending: list, stat, model_of: dict | None = None) -> dict:
    """The theme's sector figures by family (R23; R27: metric_registry): each company's figures with their periods and sources and its state for
    each figure (value, unavailable, not applicable, not comparable), the median of each over its "value" rows with "N of M" the companies it
    applies to (`stat`: theme_data.stat), the figures that may headline, the unusual growth figures with their bases, what was checked and what
    isn't filed; insurers summarised by type (life, general, health, reinsurance), never one median across types. Empty when no company has one.
    `model_of`: symbol -> its layer's revenue model family (theme_base.by_model), for which figures apply."""
    model_of = model_of or {}
    waiting = set(pending or ())
    fams = {}
    for fam in FAMILIES:
        cos = [r for r in rows if family_of(region, r) == fam]
        have = [k for k in KEYS if BY_KEY[k][2] == fam and any(r.get(k) is not None for r in cos)]
        if not have:
            late = sum(1 for r in cos if r["symbol"] in waiting)
            if late:                # none read yet: said as such (R29), never a family that silently isn't there
                fams[fam] = {"keys": [], "n": 0, "of": len(cos), "pending": late, "read": len(cos) - late, "rows": [], "medians": {},
                             "headline": [], "states": {}, "extreme": [], "periods": [], "checked": CHECKED[fam], "not_filed": NOT_FILED[fam]}
            continue
        with_ = [r for r in cos if any(r.get(k) is not None for k in have)]
        # a company whose figures end far before the family's typical latest period isn't shown with them as current: left out of the
        # rows and medians, with the reason for the deck to print (lane dat57: "latest figures are for FY Dec 2014")
        ends = sorted(str(r.get("sector_end")) for r in with_ if r.get("sector_end"))
        typical = ends[len(ends) // 2] if ends else None
        gap = lambda r: (_day(typical) - _day(str(r["sector_end"]))).days if typical and r.get("sector_end") and _day(typical) and _day(str(r["sector_end"])) else 0   # noqa: E731
        stale = [r for r in with_ if gap(r) > STALE_DAYS]
        with_ = [r for r in with_ if r not in stale]
        if not with_:
            continue
        out_rows = [{"symbol": r["symbol"], "name": r["name"], "layer": layer_of.get(r["symbol"]), "as_of": r.get("sector_as_of"),
                     **{k: r.get(k) for k in have}, "src": r.get("sector_src") or {},
                     **({"ffo_basis": r["ffo_basis"]} if r.get("ffo_basis") and any(r.get(k) is not None for k in registry.FFO_BASIS_KEYS) else {}),
                     **({"type": registry.insurer_type(r, r.get("sector_kind") or "")} if fam == "insurer" else {})} for r in with_]
        tagsets = [registry.tags(region, r, model_of.get(r["symbol"])) for r in with_]
        # a figure is a column only where it applies to one of the companies (R27: no column of "n/a")
        keys = [k for k in have if any(registry.applies(k, region, t) and r.get(k) is not None for r, t in zip(with_, tagsets))]
        if not keys:
            continue
        rest = [r for r in cos if not any(r.get(k) is not None for k in have)]
        rest_tags = [registry.tags(region, r, model_of.get(r["symbol"])) for r in rest]
        summ = _summary(out_rows, keys, region, tagsets, stat, rest_tags)
        # R29 (the live R27 Banks deck: "Median of the 7 banks with filed figures" while 12 were still being read after VERSION 2): how many of
        # the family's companies are still being read, so the deck says "read for 7 of 19 so far" instead of a silently smaller sample
        late = sum(1 for r in rest if r["symbol"] in waiting)
        summ = {**summ, **one_ffo_basis(out_rows, keys, summ["medians"], stat)}
        f = {"keys": keys, "n": len(with_), "of": len(cos), "pending": late, "read": len(cos) - late, **summ,
             "rows": out_rows,
             "periods": sorted({(r.get("sector_src") or {}).get(k, {}).get("period") or "" for r in with_ for k in keys} - {""}),
             "checked": CHECKED[fam], "not_filed": NOT_FILED[fam],
             "stale": [{"symbol": r["symbol"], "name": r["name"], "as_of": r.get("sector_as_of"),
                        "reason": f"latest figures are for {r.get('sector_as_of')}"} for r in stale]}
        if fam == "insurer":
            types = {}
            for t in INSURER_TYPES:
                idx = [i for i, r in enumerate(out_rows) if r["type"] == t]
                if not idx:
                    continue
                sub = [out_rows[i] for i in idx]
                tk = [k for k in keys if any(registry.applies(k, region, tagsets[i]) for i in idx)]
                rt = [x for r, x in zip(rest, rest_tags) if registry.insurer_type(r, r.get("sector_kind") or "") == t]
                types[t] = {"n": len(sub), "keys": tk, **_summary(sub, tk, region, [tagsets[i] for i in idx], stat, rt)}
            f["types"] = types
            if len(types) > 1:      # one median a type: the family's own medians are only of figures with one meaning across types
                f["medians"] = {k: f["medians"][k] for k in keys if k in ("solvency", "premium_growth")}
                f["headline"] = []
        fams[fam] = f
    return {"families": fams, "pending": sorted(set(pending))} if fams or pending else {}
