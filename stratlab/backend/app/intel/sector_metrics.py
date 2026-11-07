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

KIND = "sector:metrics"
VERSION = 1                     # part of a stored piece's key and of a dive's: figures read under older rules are read again
BUDGET = 20.0                   # seconds of reading a theme's build may spend on filings before the rest go to the worker
MAX_QUEUE = 200
PAUSE = 1.0                     # seconds between documents from the exchange's archive (shareholders.py's pace)
LIST_PATH = "/api/integrated-filing-results"
REFERER = "https://www.nseindia.com/companies-listing/corporate-integrated-filing"
CRORE = 1e7
FAMILIES = ("bank", "insurer", "us")
FAMILY_NAMES = {"bank": "Banks", "insurer": "Insurers", "us": "US companies"}
# every figure: (key, label, family, format, how it is worked out). Formats: pct (a share, %), chg (a change, %), x (times)
METRICS = (
    ("gnpa_f", "Gross NPA", "bank", "pct", "Gross non-performing assets as a share of gross advances, as filed for the quarter's end."),
    ("nnpa_f", "Net NPA", "bank", "pct", "Net non-performing assets as a share of net advances, as filed for the quarter's end."),
    ("cet1", "CET1 ratio", "bank", "pct", "Common equity tier 1 capital over risk-weighted assets, as filed (the filing has no total capital adequacy ratio)."),
    ("roa_f", "ROA", "bank", "pct", "Net profit for the year to date, annualised, over the average of total assets at the period's end and a year earlier "
                                    "(banks file their own ROA on different bases, some annualised and some not)."),
    ("nii_q", "NII, quarter", "bank", "amt", "Net interest income: interest earned less interest expended in the quarter."),
    ("nii_growth_f", "NII growth", "bank", "chg", "Net interest income against the same quarter a year before."),
    ("advances_growth", "Advances growth", "bank", "chg", "Advances against a year before, from the half-year balance sheets."),
    ("deposit_growth_f", "Deposit growth", "bank", "chg", "Deposits against a year before, from the half-year balance sheets."),
    ("credit_cost", "Credit cost", "bank", "pct", "Provisions other than tax for the year to date, annualised, over the average of advances at the "
                                                  "period's end and a year earlier."),
    ("nim", "NIM", "bank", "pct", "Net interest margin, as the filing states it."),
    ("casa", "CASA", "bank", "pct", "Current and savings deposits as a share of deposits, as the filing states it."),
    ("solvency", "Solvency ratio", "insurer", "x", "Available over required solvency margin, as filed for the quarter's end."),
    ("claims_ratio", "Claims ratio", "insurer", "pct", "Incurred claims over net premium earned, as filed for the year to date (general insurers)."),
    ("combined_ratio", "Combined ratio", "insurer", "pct", "Claims, commission and expenses over premium, as filed for the year to date (general insurers)."),
    ("persistency_13", "13th-month persistency", "insurer", "pct", "Policies still paying premium in their 13th month, as filed for the year to date (life insurers)."),
    ("premium_growth", "Premium growth", "insurer", "chg", "Gross premium against the same quarter a year before."),
    ("vnb_margin", "VNB margin", "insurer", "pct", "Value of new business over annualised premium equivalent, as the filing states it."),
    ("sbc_share", "SBC / revenue", "us", "pct", "Stock-based compensation over revenue, the latest fiscal year."),
    ("rpo_cover", "RPO / revenue", "us", "x", "Remaining performance obligations at the latest date filed, over the latest fiscal year's revenue."),
    ("rpo_growth", "RPO growth", "us", "chg", "Remaining performance obligations against a year before."),
    ("deferred_growth", "Deferred revenue growth", "us", "chg", "Deferred revenue (contract liabilities) at the fiscal year's end against a year before."),
    ("fcf_margin", "FCF margin", "us", "pct", "Free cash flow (cash from operations less capital spending) over revenue, the latest fiscal year."),
)
KEYS = tuple(m[0] for m in METRICS)
BY_KEY = {m[0]: m for m in METRICS}
# the filed figure that replaces the page tables' own when a filing gives it (R22: one number per metric wherever it is shown)
REPLACES = {"gnpa_f": "gnpa", "nnpa_f": "nnpa", "nii_growth_f": "nii_growth", "deposit_growth_f": "deposit_growth"}
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
        return "us" if prof == "other" else None
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


def _fig(v, period: str, source: str) -> dict | None:
    return None if v is None else {"v": v, "period": period, "source": source}


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
        out["nii_growth_f"] = _fig(_growth(nii, before), f"Quarter to {end} on {_label(ago['end'])}", src)
    h, h0 = (cur, ago) if cur.get("at", {}).get("Advances") else (half, half_ago)
    if h and h0 and h.get("at") and h0.get("at"):
        hl = f"{_label(h['end'])} on {_label(h0['end'])}"
        out["advances_growth"] = _fig(_growth(h["at"].get("Advances"), h0["at"].get("Advances")), hl, src)
        out["deposit_growth_f"] = _fig(_growth(h["at"].get("Deposits"), h0["at"].get("Deposits")), hl, src)
        adv = [x for x in (h["at"].get("Advances"), h0["at"].get("Advances")) if x]
        prov = h["ytd"].get("ProvisionsOtherThanTaxAndContingencies")
        assets = [x for x in (h["at"].get("Assets"), h0["at"].get("Assets")) if x]
        profit = h["ytd"].get("ProfitLossForThePeriod")
        if len(assets) == 2 and profit is not None:
            hm = _months(h)
            out["roa_f"] = _fig(_within(round(profit * 12 / hm / (sum(assets) / 2) * 100, 2), -10, 10), f"{hm} months to {_label(h['end'])}, annualised", src)
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
        out["premium_growth"] = _fig(_growth(gross(cur), gross(ago)), f"Quarter to {end} on {_label(ago['end'])}", src)
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
    fy = f"Fiscal year to {_label(end)}"
    src = "Annual report (10-K) facts filed with the SEC"
    r = rev[end]
    out = {}
    share = lambda v: round(v / r * 100, 1) if v is not None and r and r > 0 else None      # noqa: E731
    sbc = sec.flows(facts, SBC, "annual", unit).get(end)
    out["sbc_share"] = _fig(_within(share(sbc), 0, 200), fy, src)
    cfo, capex = sec.flows(facts, CFO, "annual", unit).get(end), sec.flows(facts, CAPEX, "annual", unit).get(end)
    out["fcf_margin"] = _fig(_within(share(cfo - abs(capex)) if cfo is not None and capex is not None else None, -500, 200), fy, src)
    rpo = sec.instants(facts, RPO, unit)
    if rpo:
        last = max(rpo)
        at = end if end in rpo else last           # at the fiscal year's end where filed, over that year's revenue
        out["rpo_cover"] = _fig(round(rpo[at] / r, 2) if r and r > 0 and rpo[at] > 0 else None,
                                f"{_label(at)}, over the fiscal year to {_label(end)}", "Filed with the SEC")
        prior = next((d for d in sorted(rpo, reverse=True) if 350 <= (_day(last) - _day(d)).days <= 380), None)
        if prior:
            out["rpo_growth"] = _fig(_growth(rpo[last], rpo[prior]), f"{_label(last)} on {_label(prior)}", "Filed with the SEC")
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
            out["deferred_growth"] = _fig(_growth(dr[end], dr[prev]), f"{_label(end)} on {_label(prev)}", src)
    out = {k: v for k, v in out.items() if v}
    return {**out, "_end": end} if out else out


def read_us(symbol: str, sec_client) -> dict:
    cik = sec_client.cik(symbol)
    facts = sec_client._json(f"/api/xbrl/companyfacts/CIK{cik:010d}.json")
    got = us_figures(facts or {})
    end = got.pop("_end", None)
    return {"family": "us", "metrics": got, "end": end, **({} if got else {"none": "no revenue in the SEC's company facts"})}


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
    computed.put(KIND, key(region, symbol), got, label=symbol, region=region)
    return got


_q: list = []
_qlock = threading.Lock()
_worker = {"on": False}


def _work():
    while True:
        with _qlock:
            if not _q:
                _worker["on"] = False
                return
            region, symbol, family = _q.pop(0)
        if stored(region, symbol) is None:
            read(region, symbol, family)


def queue(region: str, symbol: str, family: str) -> None:
    """Read later, on the one worker thread (started here, it stops when the queue is empty). Nothing is queued with no source set up."""
    if _feeds["sec" if family == "us" else "nse"] is None:
        return
    with _qlock:
        if (region, symbol, family) in _q or len(_q) >= MAX_QUEUE:
            return
        _q.append((region, symbol, family))
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
    return get


def any_stored(region: str, symbols: list) -> bool:
    """Whether a figure a dive was waiting for has been kept since (the dive is then worked out again from the stored pieces)."""
    if not symbols:
        return False
    ix = computed.index(KIND).get("entries") or {}
    return any(computed.hkey(key(region, s)) in ix for s in symbols)


# ---------- a theme's figures ----------
def apply(row: dict, piece: dict | None) -> None:
    """A company's line takes its filed figures (each under its key, `sector_src` keeping period and source), and a filed gross or net NPA,
    NII growth or deposit growth replaces the page tables' own figure (one number per metric)."""
    got = (piece or {}).get("metrics") or {}
    row["sector_src"] = {}
    end = (piece or {}).get("end")
    row["sector_as_of"] = (("FY " if (piece or {}).get("family") == "us" else "") + _label(end)) if end and got else None
    for k, fig in got.items():
        if k in BY_KEY and isinstance(fig, dict) and fig.get("v") is not None:
            row[k] = fig["v"]
            row["sector_src"][k] = {"period": fig.get("period"), "source": fig.get("source")}
            if k in REPLACES:
                row[REPLACES[k]] = fig["v"]


def section(rows: list[dict], region: str, layer_of: dict, pending: list, stat) -> dict:
    """The theme's sector figures by family: each company's figures with their periods and sources, the median of each over the companies that
    have it (`stat`: theme_data.stat), the figures each family has, what was checked and what isn't filed; empty when no company has one."""
    fams = {}
    for fam in FAMILIES:
        cos = [r for r in rows if family_of(region, r) == fam]
        have = [k for k in KEYS if BY_KEY[k][2] == fam and any(r.get(k) is not None for r in cos)]
        if not have:
            continue
        with_ = [r for r in cos if any(r.get(k) is not None for k in have)]
        fams[fam] = {"keys": have, "n": len(with_), "of": len(cos), "medians": {k: stat(r.get(k) for r in with_) for k in have},
                     "rows": [{"symbol": r["symbol"], "name": r["name"], "layer": layer_of.get(r["symbol"]), "as_of": r.get("sector_as_of"),
                               **{k: r.get(k) for k in have}, "src": r.get("sector_src") or {}} for r in with_],
                     "periods": sorted({(r.get("sector_src") or {}).get(k, {}).get("period") or "" for r in with_ for k in have} - {""}),
                     "checked": CHECKED[fam], "not_filed": NOT_FILED[fam]}
    return {"families": fams, "pending": sorted(set(pending))} if fams or pending else {}
