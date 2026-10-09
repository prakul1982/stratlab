"""Mutual funds (Money space): the user's own funds from their Consolidated Account Statement (the detailed CAS PDF
from CAMS or KFintech) or a plain CSV, valued at the latest published NAV, with XIRR, allocation by category and
capital gains per financial year (first in, first out, per folio and scheme).

The PDF is read in memory and its password is used only to open it: neither is ever stored or logged. What is kept is
the list of transactions (date, type, units, amount, NAV) and each scheme's name, folio, ISIN and code, per user in
app_settings (mf:<uid>), seen only by that user and deleted in one step. The investor's name, PAN, email and address
on the statement are never kept.

Tax rules, Income-tax Act, 1961 (the Income-tax Act, 2025 carries them over from 1 April 2026 under new section
numbers), checked against the Act as amended by the Finance Act, 2023 and the Finance (No. 2) Act, 2024:
- Equity-oriented fund (65% or more in shares of Indian listed companies, section 112A Explanation (a); a fund of
  funds that puts 90% in such ETFs counts too): short term when held 12 months or less (section 2(42A) first
  proviso). Short-term gains: section 111A, 15%, 20% for transfers from 23 July 2024. Long-term gains: section 112A,
  10% above the yearly exemption, 12.5% from 23 July 2024 (exemption ₹1 lakh, ₹1.25 lakh from FY 2024-25); exempt
  under section 10(38) before 1 April 2018. Units bought on or before 31 Jan 2018 cost at least their NAV on that day
  (section 55(2)(ac): for unlisted units the NAV on 31 Jan 2018), but not more than the sale value.
- Specified mutual fund (section 50AA, inserted by the Finance Act, 2023): units bought on or after 1 April 2023 are
  short term whatever the holding period, so taxed at the slab rate. Who counts changed (Finance (No. 2) Act, 2024,
  from assessment year 2026-27, i.e. sales from 1 April 2025): before, a fund with no more than 35% in shares of
  Indian companies (debt funds, and gold and overseas funds of funds too); from then, a fund with more than 65% in
  debt and money market instruments, or a fund of funds with 65% or more in such funds.
- Every other fund (and specified-fund units bought before 1 April 2023): for transfers from 23 July 2024, long term
  after more than 24 months (section 2(42A) as amended), taxed at 12.5% without indexation (section 112(1)); before
  that, long term after more than 36 months, at 20% after indexation (section 48 second proviso, with the Cost
  Inflation Index notified by the CBDT each year). Short-term gains are taxed at the slab rate.
- Transfers that aren't taxed as sales: a gift (section 47(iii)), and a scheme merger (section 47(xix)), where the new
  units keep the old cost and purchase date (sections 49(2AD) and 2(42A)). Stamp duty on a purchase is part of its
  cost; STT is not deductible (section 48). Dividends (IDCW) are income at the slab rate from FY 2020-21, not gains.

Facts and arithmetic on the user's own transactions: no ratings, no comparisons between funds, never a suggestion."""
import base64
import binascii
import csv
import io
import json
import math
import re
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from . import db, money_mf_nav as navs, tax_lots
from .auth import current_profile
from .responses import err, ok
from .kite_service import IST
from .plans import FEATURE_PLAN, PLANS, allows, mf_limit

KEY = "mf:"
MAX_PDF = 5 * 1024 * 1024             # as base64 it stays under the server's 8 MB request cap
MAX_CSV = 2 * 1024 * 1024
MAX_TXNS = 20000
MAX_SCHEMES = 300
MAX_FILES = 40
EPS = 1e-6

SPECIFIED_FROM = "2023-04-01"           # section 50AA: units bought from this day
SPECIFIED_REDEFINED = "2025-04-01"      # the new definition applies to sales from this day (AY 2026-27)
RATE_CHANGE = tax_lots.RATE_CHANGE      # 23 July 2024: new rates and the 24-month holding period
ELSS_LOCK_YEARS = 3                     # ELSS units are locked in for three years from each purchase

# Cost Inflation Index, base year 2001-02 (CBDT Notification No. 44/2017 and the yearly notifications after it).
# Only needed for long-term gains on non-equity funds sold before 23 July 2024.
CII = {2001: 100, 2002: 105, 2003: 109, 2004: 113, 2005: 117, 2006: 122, 2007: 129, 2008: 137, 2009: 148, 2010: 167,
       2011: 184, 2012: 200, 2013: 220, 2014: 240, 2015: 254, 2016: 264, 2017: 272, 2018: 280, 2019: 289, 2020: 301,
       2021: 317, 2022: 331, 2023: 348, 2024: 363, 2025: 376}

KINDS = {
    "equity": "Equity-oriented: 65% or more in shares of Indian companies",
    "debt": "Debt: more than 65% in debt and money market instruments",
    "hybrid": "Other: between 35% and 65% in shares of Indian companies",
    "other": "Other: under 35% in shares of Indian companies, and not mainly debt (gold, overseas funds)",
}
IN_TYPES = {"purchase", "sip", "switch_in", "merger_in", "div_reinvest", "gift_in", "segregation", "opening"}
OUT_TYPES = {"redeem", "switch_out", "merger_out", "gift_out"}
INFO_TYPES = {"stamp", "stt", "tds", "div_payout", "reversal"}
TYPES = IN_TYPES | OUT_TYPES | INFO_TYPES
PRIORITY = {"opening": 0, "merger_out": 0, "reversal": 3, "stamp": 2}      # same-day order: buys, charges, then sales

DISCLAIMER = ("Facts and arithmetic from your own statement, valued at the latest published NAV. Not investment or tax "
              "advice. Check tax figures with a chartered accountant (CA) before you file.")
ASSUMPTIONS = [
    "Units are valued at the latest NAV published for each scheme (its date is shown). Where none is available, the NAV "
    "printed on your statement is used and marked.",
    "Invested is the cost of the units you still hold, matched first in, first out, including stamp duty.",
    "XIRR uses every purchase, redemption and dividend paid out as dated cash flows, with today's value as the last "
    "one. It isn't shown for less than 30 days of history.",
    "The tax kind of each scheme is read from its category and name; change it for any scheme where it's wrong. "
    "Balanced advantage and dynamic asset allocation funds are taken as equity-oriented, which most of them are run to be.",
]


# ---------- dates ----------
def _d(s: str) -> date:
    return date.fromisoformat(s)


def add_months(d: str, n: int) -> date:
    """The same day n months later (the month's last day when it has no such day)."""
    b = _d(d)
    m = b.month - 1 + n
    y, m = b.year + m // 12, m % 12 + 1
    for day in (b.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def held_over(buy: str, sale: str, months: int) -> bool:
    """Held for more than `months` months: sold after the same day that many months on."""
    return _d(sale) > add_months(buy, months)


def today_ist() -> str:
    return datetime.now(IST).date().isoformat()


# ---------- the scheme's kind and category ----------
_INTL = re.compile(r"\b(us|u\.s\.|usa|nasdaq|s&p|s ?& ?p 500|global|international|overseas|world|emerging|greater china|china|"
                   r"hang seng|japan|europe|asia|fang|taiwan|developed)\b", re.I)
_GOLD = re.compile(r"\b(gold|silver|precious)\b", re.I)
_DEBT = re.compile(r"\b(gilt|g-?sec|sdl|bond|debt|crisil|liquid|overnight|money market|psu|target maturity|treasury|t-?bill|"
                   r"income|corporate|credit|duration|floater|floating|fmp|fixed maturity|banking)\b", re.I)


def kind_of(category: str, name: str, hint: str = "") -> str:
    """The scheme's tax kind from its official category (and its name where the category alone can't tell, as with index
    funds, ETFs and funds of funds). `hint`: EQUITY or DEBT where nothing else is known."""
    c, n = (category or "").lower(), name or ""
    hint = hint.upper() if (hint or "").upper() in ("EQUITY", "DEBT") else ""
    if "equity scheme" in c or c in ("growth", "elss"):
        return "other" if "thematic" in c and _INTL.search(n) else "equity"
    if "debt scheme" in c or c in ("income", "gilt", "money market", "liquid"):
        return "debt"
    if "hybrid scheme" in c:
        if "conservative" in c:
            return "debt"
        if any(w in c for w in ("aggressive", "arbitrage", "equity savings", "balanced advantage", "dynamic asset")):
            return "equity"
        return "hybrid"
    if "solution oriented" in c:
        return "debt" if _DEBT.search(n) and "equity" not in n.lower() else "equity" if "equity" in n.lower() else "hybrid"
    if c or not hint:
        if _GOLD.search(n) or _INTL.search(n):
            return "other"
        if _DEBT.search(n):
            return "debt"
        if re.search(r"hybrid|balanced|asset allocation|multi asset", n, re.I):
            return "hybrid"
        if "fof" in c or "fund of fund" in n.lower():
            return "hybrid"
        if c or re.search(r"equity|index|nifty|sensex|cap|elss|tax saver|flexi|focused|value|contra", n, re.I):
            return "equity"
    return "debt" if hint.upper() == "DEBT" else "equity" if hint.upper() == "EQUITY" else "hybrid"


def broad_of(category: str, kind: str) -> tuple[str, str]:
    """(broad class, sub-category) for the allocation, from the official category."""
    c = category or ""
    m = re.match(r"\s*(.+?)\s*-\s*(.+)$", c)
    head, sub = (m.group(1), m.group(2)) if m else (c, "")
    h = head.lower()
    if h.startswith("equity"):
        return "Equity", sub
    if h.startswith("debt"):
        return "Debt", sub
    if h.startswith("hybrid"):
        return "Hybrid", sub
    if h.startswith("solution"):
        return "Solution oriented", sub
    if h.startswith("other"):
        s = sub.lower()
        if "index" in s:
            return "Index funds", ""
        if "etf" in s:
            return "ETFs", sub
        if "fof" in s:
            return "Funds of funds", sub
        return "Other", sub
    if h in ("income", "gilt", "money market", "liquid"):
        return "Debt", head
    if h in ("growth", "elss"):
        return "Equity", head
    return {"equity": "Equity", "debt": "Debt", "hybrid": "Hybrid"}.get(kind, "Other"), ""


def is_elss(category: str, name: str) -> bool:
    return "elss" in (category or "").lower() or bool(re.search(r"\belss\b|tax ?saver", name or "", re.I))


# ---------- stored data ----------
def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def empty() -> dict:
    return {"schemes": [], "txns": [], "files": [], "kinds": {}, "fmv": {}, "updated_at": None}


def _num(x) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def _txn_ok(t) -> bool:
    return (isinstance(t, dict) and isinstance(t.get("k"), str) and t.get("t") in TYPES and isinstance(t.get("d"), str)
            and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["d"])))


def load(uid: str) -> dict:
    got = db.json_value(db.get_setting(_key(uid)), {})
    got = got if isinstance(got, dict) else {}
    out = empty()
    out["schemes"] = [s for s in got.get("schemes") or [] if isinstance(s, dict) and isinstance(s.get("k"), str)][:MAX_SCHEMES]
    keys = {s["k"] for s in out["schemes"]}
    out["txns"] = [{**t, "u": _num(t.get("u")), "a": _num(t.get("a")), "n": _num(t.get("n"))}
                   for t in got.get("txns") or [] if _txn_ok(t) and t["k"] in keys][:MAX_TXNS]
    out["files"] = [f for f in got.get("files") or [] if isinstance(f, dict)][-MAX_FILES:]
    out["kinds"] = {k: v for k, v in (got.get("kinds") or {}).items() if k in keys and v in KINDS}
    out["fmv"] = {k: float(v) for k, v in (got.get("fmv") or {}).items() if k in keys and _num(v) and v > 0}
    out["updated_at"] = got.get("updated_at")
    return out


def save(uid: str, data: dict):
    body = {**data, "updated_at": datetime.now(timezone.utc).isoformat(timespec="minutes")}
    db.set_setting(_key(uid), json.dumps(body, separators=(",", ":")))


def delete(uid: str):
    db.delete_setting(_key(uid))


# ---------- reading the statement ----------
class FileError(ValueError):
    """A file that can't be read, with a message for the user."""


CAS_TYPES = {"PURCHASE": "purchase", "PURCHASE_SIP": "sip", "REDEMPTION": "redeem", "DIVIDEND_PAYOUT": "div_payout",
             "DIVIDEND_REINVEST": "div_reinvest", "SWITCH_IN": "switch_in", "SWITCH_IN_MERGER": "merger_in",
             "SWITCH_OUT": "switch_out", "SWITCH_OUT_MERGER": "merger_out", "STT_TAX": "stt", "STAMP_DUTY_TAX": "stamp",
             "TDS_TAX": "tds", "SEGREGATION": "segregation", "GIFT_IN": "gift_in", "GIFT_OUT": "gift_out", "REVERSAL": "reversal"}


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def scheme_key(folio: str, isin: str = "", code: str = "", name: str = "") -> str:
    return f"{(folio or 'CSV').strip()[:40]}|{(isin or code or ' '.join(name.split())[:80]).strip()}"


def parse_cas(data: bytes, password: str) -> dict:
    """The detailed CAS PDF, opened in memory with the password, as {"schemes", "txns", "period", "problems"}. The
    investor's name, PAN and contact details on the statement are dropped here."""
    from .connect import pdfsandbox          # imported here: the connect package imports this module
    try:
        cas = pdfsandbox.read_cas(data, password or "")
    except pdfsandbox.SandboxError as e:
        if e.kind == "password":
            raise FileError("That password didn't open the PDF. A CAS is locked with the password you chose when you asked "
                            "for it (often your PAN in capitals).") from None
        if e.kind == "parse":
            raise FileError("This PDF doesn't look like a CAMS or KFintech Consolidated Account Statement.") from None
        if e.kind == "limit":
            raise FileError("This PDF is too large or complex to read here. Ask for the statement for a shorter period.") from None
        raise FileError("This PDF couldn't be read. Check it's the CAS as it was emailed to you.") from None
    if not hasattr(cas, "folios"):
        raise FileError("This is a depository statement. Upload the detailed CAS from CAMS or KFintech instead, "
                        "which lists every transaction.")
    return from_cas(cas)


def from_cas(cas) -> dict:
    """The schemes and transactions of an opened CAMS or KFintech CAS, as parse_cas returns them."""
    if str(getattr(cas.cas_type, "value", cas.cas_type)) != "DETAILED":
        raise FileError("This is the summary statement, which has no transactions. Ask for the detailed CAS "
                        "(\"with transactions\"), from the start date you want.")
    period = getattr(cas, "statement_period", None)
    start = _day(getattr(period, "from_", None) or "") if period else None
    schemes, txns, problems = [], [], []
    for folio in cas.folios:
        for s in folio.schemes:
            k = scheme_key(folio.folio, s.isin or "", s.amfi or "", s.scheme)
            val = s.valuation
            schemes.append({"k": k, "name": " ".join(str(s.scheme).split())[:160], "amc": " ".join(str(folio.amc).split())[:80],
                            "folio": str(folio.folio)[:40], "isin": s.isin or "", "amfi": str(s.amfi or ""),
                            "hint": str(s.type or "")[:10], "stmt_nav": _f(val.nav) or None,
                            "stmt_date": val.date.isoformat() if hasattr(val.date, "isoformat") else _day(str(val.date))})
            opening = _f(s.open) or 0.0
            if opening > EPS:
                txns.append({"k": k, "d": start or "1990-01-01", "t": "opening", "u": round(opening, 4), "a": None, "n": None})
            for t in s.transactions:
                kind = CAS_TYPES.get(str(getattr(t.type, "value", t.type)))
                units, amount, nav = _f(t.units), _f(t.amount), _f(t.nav)
                if kind is None:
                    if not units:
                        continue                # a note row: nominee registered, address changed
                    kind = "purchase" if units > 0 else "redeem"
                d = t.date.isoformat() if hasattr(t.date, "isoformat") else _day(str(t.date))
                if not d:
                    problems.append({"text": str(t.description)[:80], "reason": "No date could be read."})
                    continue
                txns.append({"k": k, "d": d, "t": kind, "u": round(units, 4) if units is not None else None,
                             "a": round(abs(amount), 2) if amount is not None else None, "n": nav})
    for w in getattr(cas, "parse_warnings", None) or []:
        problems.append({"text": "", "reason": "A unit balance in the statement didn't add up; a row may be missing."})
        if len(problems) > 20:
            break
    if not schemes:
        raise FileError("No schemes were found in this statement.")
    return {"schemes": schemes, "txns": txns, "period": start, "problems": problems[:100]}


def _day(s: str) -> str | None:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d-%B-%Y", "%d/%m/%y", "%d-%b-%y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


CSV_COLS = {
    "date": ("date", "transaction date", "txn date", "trade date"),
    "scheme": ("scheme", "scheme name", "fund", "fund name", "name"),
    "isin": ("isin",),
    "amfi": ("amfi", "amfi code", "scheme code", "code"),
    "units": ("units", "quantity", "qty"),
    "amount": ("amount", "value", "amount (inr)", "amount (rs)"),
    "type": ("type", "transaction", "transaction type", "txn type", "action"),
    "nav": ("nav", "price"),
    "folio": ("folio", "folio no", "folio number"),
}
CSV_TYPES = [(r"stamp", "stamp"), (r"\bstt\b", "stt"), (r"\btds\b", "tds"), (r"reinvest", "div_reinvest"),
             (r"dividend|idcw|payout", "div_payout"), (r"switch.*in|stp.*in", "switch_in"), (r"switch.*out|stp.*out", "switch_out"),
             (r"\bsip\b|systematic", "sip"), (r"redeem|redemption|sell|sale|\bswp\b|withdraw", "redeem"),
             (r"purchase|buy|invest|lump", "purchase")]


def _money(s: str) -> float | None:
    s = re.sub(r"[₹,\s]|rs\.?|inr", "", str(s or ""), flags=re.I)
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return None
    return -v if neg else v if math.isfinite(v) else None


def parse_csv(data: bytes) -> dict:
    """A plain CSV with the columns Date, Scheme, ISIN or AMFI code, Units, Amount and Type (NAV and Folio optional),
    one transaction a line. Lines that can't be read are listed with the reason."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    head_at, cols = None, {}
    for i, r in enumerate(rows[:10]):
        names = [c.strip().lower() for c in r]
        found = {f: names.index(a) for f, alts in CSV_COLS.items() for a in alts if a in names}
        if {"date", "units", "type"} <= found.keys() and ({"isin", "amfi", "scheme"} & found.keys()):
            head_at, cols = i, found
            break
    if head_at is None:
        raise FileError("The CSV needs a header row with Date, Scheme, ISIN or AMFI code, Units, Amount and Type.")
    schemes: dict[str, dict] = {}
    txns, problems = [], []
    for n, r in enumerate(rows[head_at + 1:], start=head_at + 2):
        if not any(c.strip() for c in r):
            continue
        get = lambda f: r[cols[f]].strip() if f in cols and cols[f] < len(r) else ""     # noqa: E731
        d = _day(get("date"))
        kind = next((t for rx, t in CSV_TYPES if re.search(rx, get("type"), re.I)), None)
        units, amount, nav = _money(get("units")), _money(get("amount")), _money(get("nav"))
        isin = get("isin").upper() if re.fullmatch(r"IN[A-Z0-9]{10}", get("isin").upper()) else ""
        code = get("amfi") if get("amfi").isdigit() else ""
        name = " ".join(get("scheme").split())[:160]
        reason = ("No date could be read." if not d else "The type isn't one of purchase, SIP, redemption, switch in or out, "
                  "dividend, stamp duty or STT." if not kind else "No ISIN, AMFI code or scheme name." if not (isin or code or name)
                  else "No units." if kind in IN_TYPES | OUT_TYPES and not units
                  else "No amount." if kind in ("stamp", "stt", "tds", "div_payout") and not amount else None)
        if reason:
            problems.append({"line": n, "text": ", ".join(r)[:120], "reason": reason})
            continue
        k = scheme_key(get("folio"), isin, code, name)
        schemes.setdefault(k, {"k": k, "name": name or isin or code, "amc": "", "folio": get("folio")[:40] or "CSV", "isin": isin,
                               "amfi": code, "hint": "", "stmt_nav": None, "stmt_date": None})
        u = abs(units) if units is not None else None
        if u is not None and kind in OUT_TYPES:
            u = -u
        txns.append({"k": k, "d": d, "t": kind, "u": round(u, 4) if u is not None else None,
                     "a": round(abs(amount), 2) if amount is not None else None, "n": abs(nav) if nav else None})
        if len(txns) > MAX_TXNS:
            break
    if not txns:
        raise FileError("No transactions could be read from this CSV." + (f" Line {problems[0]['line']}: {problems[0]['reason']}" if problems else ""))
    return {"schemes": list(schemes.values()), "txns": txns, "period": None, "problems": problems[:200]}


def read_file(data: bytes, filename: str, password: str) -> dict:
    if data[:5] == b"%PDF-" or filename.lower().endswith(".pdf"):
        if len(data) > MAX_PDF:
            raise FileError(f"That PDF is larger than {MAX_PDF // (1024 * 1024)} MB. A CAS is usually much smaller.")
        return {**parse_cas(data, password), "kind": "cas"}
    if len(data) > MAX_CSV:
        raise FileError(f"That CSV is larger than {MAX_CSV // (1024 * 1024)} MB.")
    return {**parse_csv(data), "kind": "csv"}


def _sig(t: dict) -> tuple:
    return (t["k"], t["d"], t["t"], None if t.get("u") is None else round(t["u"], 3), None if t.get("a") is None else round(t["a"], 2))


def merge(before: dict, got: dict, limit: int | None) -> tuple[dict, dict]:
    """Add a file's schemes and transactions to what's saved: transactions already there are skipped, and an opening
    balance is dropped for a scheme whose earlier transactions are already saved. Returns (data, counts)."""
    out = {**before, "schemes": list(before["schemes"]), "txns": list(before["txns"])}
    have = {s["k"]: s for s in out["schemes"]}
    first = {}
    for t in out["txns"]:
        first[t["k"]] = min(first.get(t["k"], t["d"]), t["d"])
    # new schemes in order of what they hold, then what was put in, so a limit keeps the ones that matter most
    weight: dict[str, tuple] = {}
    for t in got["txns"]:
        w = weight.get(t["k"], (0.0, 0.0))
        weight[t["k"]] = (w[0] + (t.get("u") or 0) * (t["t"] in IN_TYPES | OUT_TYPES), w[1] + ((t.get("a") or 0) if t["t"] in IN_TYPES else 0))
    new = sorted((s for s in got["schemes"] if s["k"] not in have), key=lambda s: (-(weight.get(s["k"], (0, 0))[0] > EPS), -weight.get(s["k"], (0, 0))[1]))
    cap = min(MAX_SCHEMES, limit) if limit is not None else MAX_SCHEMES
    room = max(0, cap - len(have))
    over = [s["name"] for s in new[room:]]
    for s in new[:room]:
        have[s["k"]] = s
        out["schemes"].append(s)
    for s in got["schemes"]:                  # a newer statement's NAV and any ISIN or code it adds
        if s["k"] in have and have[s["k"]] is not s:
            cur = have[s["k"]]
            for f in ("isin", "amfi", "amc", "hint"):
                cur[f] = cur.get(f) or s.get(f) or ""
            if s.get("stmt_date") and (not cur.get("stmt_date") or s["stmt_date"] >= cur["stmt_date"]):
                cur["stmt_nav"], cur["stmt_date"] = s.get("stmt_nav"), s["stmt_date"]
    seen = {_sig(t) for t in out["txns"]}
    added = dup = 0
    for t in got["txns"]:
        if t["k"] not in have:
            continue
        if t["t"] == "opening" and t["k"] in first and first[t["k"]] <= t["d"]:
            continue
        sig = _sig(t)
        if sig in seen:
            dup += 1
            continue
        if len(out["txns"]) >= MAX_TXNS:
            break
        seen.add(sig)
        out["txns"].append(t)
        added += 1
    return out, {"added": added, "duplicates": dup, "over_limit": over, "schemes": len(got["schemes"])}


# ---------- lots, sales and cash flows ----------
def _amount(t: dict) -> float | None:
    if t.get("a") is not None:
        return t["a"]
    if t.get("u") is not None and t.get("n"):
        return abs(t["u"]) * t["n"]
    return None


def classify(kind: str, bought: str, sold: str, cost: float, sale: float, qty: float, gf_nav: float | None) -> dict:
    """One matched sale's tax treatment: term, the tax bucket, the rate (None: slab rate), the cost used (after
    grandfathering or indexation) and the grandfathering mark."""
    gf = None
    if kind == "equity":
        lt = tax_lots.long_term(bought, sold)
        if lt and bought <= tax_lots.GF_DATE and sold >= tax_lots.LTCG_START:
            if gf_nav:
                gf = "applied"
                cost = max(cost, min(gf_nav * qty, sale))
            else:
                gf = "missing"
        st_rate, lt_rate = tax_lots.rates(sold)
        return {"term": "LT" if lt else "ST", "bucket": None, "rate": lt_rate if lt else st_rate, "cost": cost, "gf": gf}
    specified = bought >= SPECIFIED_FROM and (kind == "debt" or (kind == "other" and sold < SPECIFIED_REDEFINED))
    if specified:
        return {"term": "ST", "bucket": "st_slab", "rate": None, "cost": cost, "gf": None, "specified": True}
    if sold >= RATE_CHANGE:
        if held_over(bought, sold, 24):
            return {"term": "LT", "bucket": "lt_112", "rate": 0.125, "cost": cost, "gf": None}
    elif held_over(bought, sold, 36):
        fb, fs = tax_lots.fy_of(bought), tax_lots.fy_of(sold)
        idx = CII.get(min(max(fs, 2001), 2025), 100) / CII.get(min(max(fb, 2001), 2025), 100)
        return {"term": "LT", "bucket": "lt_112i", "rate": 0.20, "cost": cost * idx, "gf": None, "indexed": round(cost * idx, 2)}
    return {"term": "ST", "bucket": "st_slab", "rate": None, "cost": cost, "gf": None}


def compute(data: dict, kinds: dict[str, str], gf: dict[str, float]) -> dict:
    """Every scheme's open lots, realised sales (classified), cash flows and dividends, first in first out per folio
    and scheme. Scheme mergers carry the old lots over to the new scheme within the folio."""
    lots: dict[str, list[dict]] = {s["k"]: [] for s in data["schemes"]}
    folio_of = {s["k"]: s.get("folio") or "" for s in data["schemes"]}
    out = {"realised": [], "flows": {k: [] for k in lots}, "dividends": {}, "stt": {}, "unknown": {}, "short": {},
           "notes": set(), "lots": lots}
    pending: list[dict] = []           # merger-outs waiting for their merger-in
    order = sorted(enumerate(data["txns"]), key=lambda x: (x[1]["d"], PRIORITY.get(x[1]["t"], 1 if x[1]["t"] in IN_TYPES else 4), x[0]))

    def sell(k: str, d: str, units: float, sale: float | None, taxed: bool) -> list[dict]:
        """Take units out first in first out; with `taxed`, each piece is a realised sale."""
        left, taken = units, []
        each = (sale / units) if sale is not None and units > EPS else None
        while left > EPS and lots[k]:
            l = lots[k][0]
            q = min(l["u"], left)
            frac = q / l["u"]
            piece = {"d": l["d"], "u": q, "cost": None if l["cost"] is None else l["cost"] * frac, "gift": l.get("gift", False)}
            l["u"] -= q
            if l["cost"] is not None:
                l["cost"] -= piece["cost"]
            if l["u"] <= EPS:
                lots[k].pop(0)
            left -= q
            taken.append(piece)
            if not taxed:
                continue
            if piece["cost"] is None or each is None:
                out["unknown"][k] = out["unknown"].get(k, 0.0) + q
                continue
            proceeds = q * each
            c = classify(kinds[k], piece["d"], d, piece["cost"], proceeds, q, gf.get(k))
            out["realised"].append({"key": k, "bought": piece["d"], "sold": d, "fy": tax_lots.fy_of(d), "qty": q,
                                    "cost": c["cost"], "actual_cost": piece["cost"], "sale": proceeds,
                                    "gain": proceeds - c["cost"], "term": c["term"], "bonus": False, "gf": c["gf"],
                                    "rate": c["rate"], "kind": kinds[k], "src": "mf",
                                    **({"bucket": c["bucket"]} if c["bucket"] else {})})
            if piece.get("gift"):
                out["notes"].add("gift")
        if left > EPS:
            out["short"][k] = out["short"].get(k, 0.0) + left
        return taken

    for _, t in order:
        k, typ, d = t["k"], t["t"], t["d"]
        if k not in lots:
            continue
        u = abs(t.get("u") or 0.0)
        amt = _amount(t)
        if typ in IN_TYPES:
            if u <= EPS:
                continue
            if typ == "merger_in":
                hit = next((p for p in pending if p["folio"] == folio_of[k] and abs((_d(d) - _d(p["d"])).days) <= 7 and p["k"] != k), None)
                if hit:
                    pending.remove(hit)
                    scale = u / hit["u"] if hit["u"] > EPS else 1.0
                    for p in hit["lots"]:
                        lots[k].append({"d": p["d"], "u": p["u"] * scale, "cost": p["cost"], "gift": p.get("gift", False)})
                    lots[k].sort(key=lambda l: l["d"])
                    out["flows"][k].append((d, -(amt or 0.0)))
                    out["flows"][hit["k"]].append((hit["d"], hit["amt"] or 0.0))
                    continue
            cost = None if typ == "opening" else (0.0 if typ == "segregation" else amt if amt is not None else None)
            if typ == "segregation":
                out["notes"].add("segregation")
            if typ in ("gift_in",):
                out["notes"].add("gift_in")
            lots[k].append({"d": d, "u": u, "cost": cost, "gift": typ == "gift_in"})
            if typ not in ("div_reinvest", "opening", "segregation") and cost is not None:
                out["flows"][k].append((d, -cost))
        elif typ == "stamp":
            lot = next((l for l in reversed(lots[k]) if l["d"] == d and l["cost"] is not None), None)
            if lot and amt:
                lot["cost"] += amt
                out["flows"][k].append((d, -amt))
        elif typ == "reversal":
            left = u
            while left > EPS and lots[k]:            # a purchase that didn't go through: the latest units go
                l = lots[k][-1]
                q = min(l["u"], left)
                if l["cost"] is not None and l["u"] > EPS:
                    paid = l["cost"] * q / l["u"]
                    l["cost"] -= paid
                    out["flows"][k].append((d, paid))
                l["u"] -= q
                left -= q
                if l["u"] <= EPS:
                    lots[k].pop()
        elif typ == "merger_out":
            taken = sell(k, d, u, amt, taxed=False)
            pending.append({"k": k, "folio": folio_of[k], "d": d, "u": u, "lots": taken, "amt": amt})
        elif typ in OUT_TYPES:
            sell(k, d, u, amt, taxed=typ != "gift_out")
            if typ != "gift_out" and amt:
                out["flows"][k].append((d, amt))
        elif typ == "div_payout" and amt:
            fy = tax_lots.fy_of(d)
            out["dividends"][fy] = out["dividends"].get(fy, 0.0) + amt
            out["flows"][k].append((d, amt))
        elif typ == "stt" and amt:
            fy = tax_lots.fy_of(d)
            out["stt"][fy] = out["stt"].get(fy, 0.0) + amt
    for p in pending:                         # a merger with no new scheme in the file: counted as a sale
        k = p["k"]
        lots[k].extend(p["lots"])
        lots[k].sort(key=lambda l: l["d"])
        sell(k, p["d"], p["u"], p["amt"], taxed=True)
        if p["amt"]:
            out["flows"][k].append((p["d"], p["amt"]))
        out["notes"].add("merger")
    return out


def xirr(flows: list[tuple[str, float]]) -> float | None:
    """The annual rate that makes the dated cash flows add up to zero (money in negative, money out positive), or None
    when it can't be worked out (one-sided flows, under 30 days, or no answer between -99% and 10,000%)."""
    flows = [(d, a) for d, a in flows if a and math.isfinite(a)]
    if len(flows) < 2 or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    t0 = min(_d(d) for d, _ in flows)
    span = (max(_d(d) for d, _ in flows) - t0).days
    if span < 30:
        return None
    ts = [((_d(d) - t0).days / 365.0, a) for d, a in flows]

    def npv(r):
        return sum(a / (1 + r) ** t for t, a in ts)
    lo, hi = -0.9999, 100.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7 or hi - lo < 1e-10:
            break
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return round((lo + hi) / 2, 6)


# ---------- the page ----------
def _r(v, dp=2):
    return None if v is None else round(v, dp)


def _resolve(data: dict, daily: dict) -> dict[str, dict]:
    """Each scheme with its record in the daily NAV file (or None), its category, tax kind and NAV."""
    out = {}
    for s in data["schemes"]:
        rec = navs.find(daily, s.get("isin") or "", s.get("amfi") or "", s.get("name") or "")
        category = rec["category"] if rec else ""
        auto = kind_of(category, s.get("name") or (rec or {}).get("name", ""), s.get("hint") or "")
        kind = data["kinds"].get(s["k"]) or auto
        nav, nav_date, src = (rec["nav"], rec["date"], "daily") if rec else (s.get("stmt_nav"), s.get("stmt_date"), "statement")
        out[s["k"]] = {"rec": rec, "category": category, "kind_auto": auto, "kind": kind, "nav": nav or None,
                       "nav_date": nav_date, "nav_source": src if nav else None}
    return out


def _gf(data: dict, info: dict[str, dict], need: bool) -> dict[str, float]:
    """31 Jan 2018 NAV per scheme: the user's own figure, else the public one (read only when some lot needs it)."""
    out = dict(data["fmv"])
    if not need:
        return out
    navs_2018 = navs.gf_navs()
    for s in data["schemes"]:
        if s["k"] in out:
            continue
        rec = info[s["k"]]["rec"] or {}
        for code in (s.get("amfi"), rec.get("code")):
            if code and code in navs_2018.get("code", {}):
                out[s["k"]] = navs_2018["code"][code]
                break
        else:
            for i in (s.get("isin"), rec.get("isin"), rec.get("isin2")):
                if i and i in navs_2018.get("isin", {}):
                    out[s["k"]] = navs_2018["isin"][i]
                    break
    return out


def _needs_gf(data: dict, kinds: dict[str, str]) -> bool:
    early = {t["k"] for t in data["txns"] if t["t"] in IN_TYPES and t["d"] <= tax_lots.GF_DATE and kinds.get(t["k"]) == "equity"}
    return any(t["k"] in early and t["t"] in OUT_TYPES and t["d"] >= tax_lots.LTCG_START for t in data["txns"])


def worked(data: dict, daily: dict | None = None) -> dict:
    """Everything the page and the tax report need, worked out once."""
    daily = daily if daily is not None else navs.daily()
    info = _resolve(data, daily)
    kinds = {k: v["kind"] for k, v in info.items()}
    gf = _gf(data, info, _needs_gf(data, kinds))
    return {"info": info, "kinds": kinds, "gf": gf, "c": compute(data, kinds, gf), "daily": daily}


def names(data: dict) -> dict[str, dict]:
    return {s["k"]: {"symbol": s["name"][:60], "name": s["name"], "isin": s.get("isin") or "", "listed": False, "mf": True}
            for s in data["schemes"]}


def holdings(data: dict, w: dict, today: str) -> dict:
    """Per scheme and in total: units, invested (cost of units held), value, gain and XIRR; and the allocation."""
    rows, all_flows = [], []
    for s in data["schemes"]:
        k, inf = s["k"], w["info"][s["k"]]
        lots = w["c"]["lots"][k]
        units = sum(l["u"] for l in lots)
        unknown = any(l["cost"] is None for l in lots)
        invested = sum(l["cost"] for l in lots if l["cost"] is not None)
        value = units * inf["nav"] if inf["nav"] and units > EPS else (0.0 if units <= EPS else None)
        flows = list(w["c"]["flows"][k])
        if value:
            flows.append((today, value))
        known = not unknown and k not in w["c"]["unknown"] and k not in w["c"]["short"]
        x = xirr(flows) if known else None
        if known:
            all_flows += flows
        realised = sum(r["sale"] - (r.get("actual_cost") or r["cost"]) for r in w["c"]["realised"] if r["key"] == k)
        rec = inf["rec"] or {}
        broad, sub = broad_of(inf["category"], inf["kind"])
        elss = None
        if is_elss(inf["category"], s["name"]):
            locked = [(l["d"], l["u"]) for l in lots if add_months(l["d"], 12 * ELSS_LOCK_YEARS) > _d(today)]
            if locked:
                elss = {"locked_units": _r(sum(u for _, u in locked), 4),
                        "next_free": add_months(min(d for d, _ in locked), 12 * ELSS_LOCK_YEARS).isoformat(),
                        "all_free": add_months(max(d for d, _ in locked), 12 * ELSS_LOCK_YEARS).isoformat()}
        rows.append({"key": k, "name": s["name"], "amc": s.get("amc") or rec.get("amc") or "", "folio": s.get("folio") or "",
                     "isin": s.get("isin") or rec.get("isin") or "", "amfi": s.get("amfi") or rec.get("code") or "",
                     "category": inf["category"], "broad": broad, "sub": sub, "kind": inf["kind"], "kind_auto": inf["kind_auto"],
                     "kind_set": k in data["kinds"], "units": _r(units, 4), "nav": inf["nav"], "nav_date": inf["nav_date"],
                     "nav_source": inf["nav_source"], "invested": None if unknown else _r(invested),
                     "value": _r(value), "gain": None if unknown or value is None else _r(value - invested),
                     "gain_pct": None if unknown or not invested or value is None else _r((value - invested) / invested * 100, 2),
                     "xirr": x, "realised": _r(realised), "cost_unknown": unknown or k in w["c"]["unknown"],
                     "short_units": _r(w["c"]["short"].get(k), 4), "elss": elss,
                     "txns": sum(1 for t in data["txns"] if t["k"] == k), "fmv_2018": w["gf"].get(k), "fmv_yours": k in data["fmv"]})
    rows.sort(key=lambda r: (-(r["value"] or 0), r["name"]))
    held = [r for r in rows if (r["units"] or 0) > EPS]
    value = sum(r["value"] or 0 for r in held)
    known = [r for r in held if r["invested"] is not None]
    invested = sum(r["invested"] for r in known)
    x = xirr(all_flows + []) if all_flows else None
    alloc: dict[str, dict] = {}
    for r in held:
        a = alloc.setdefault(r["broad"], {"broad": r["broad"], "value": 0.0, "schemes": 0, "subs": {}})
        a["value"] += r["value"] or 0
        a["schemes"] += 1
        if r["sub"]:
            a["subs"][r["sub"]] = a["subs"].get(r["sub"], 0.0) + (r["value"] or 0)
    allocation = [{"broad": a["broad"], "value": _r(a["value"]), "pct": _r(a["value"] / value * 100, 1) if value else None,
                   "schemes": a["schemes"], "subs": [{"sub": s, "value": _r(v), "pct": _r(v / value * 100, 1) if value else None}
                                                     for s, v in sorted(a["subs"].items(), key=lambda x: -x[1])]}
                  for a in sorted(alloc.values(), key=lambda a: -a["value"])]
    dates = sorted({r["nav_date"] for r in held if r["nav_date"]})
    return {"schemes": rows, "allocation": allocation,
            "total": {"value": _r(value), "invested": _r(invested), "gain": _r(sum((r["value"] or 0) for r in known) - invested),
                      "xirr": x, "held": len(held), "schemes": len(rows), "unknown_cost": len(held) - len(known),
                      "nav_dates": [dates[0], dates[-1]] if dates else None}}


def _year(fy: int, w: dict, data: dict, limit: int | None = 500) -> dict:
    y = tax_lots.year(fy, w["c"]["realised"], [], limit=limit)
    y["dividends"] = _r(w["c"]["dividends"].get(fy, 0.0))
    y["stt"] = _r(w["c"]["stt"].get(fy, 0.0))
    y["by_kind"] = {}
    for r in w["c"]["realised"]:
        if r["fy"] == fy:
            y["by_kind"][r["kind"]] = _r((y["by_kind"].get(r["kind"]) or 0) + r["gain"])
    return y


GAIN_NOTES = [
    "Each redemption or switch out is matched to the oldest units in the same folio and scheme first (first in, first out).",
    "Equity-oriented funds: short term when held 12 months or less, at 15% (20% for sales from 23 Jul 2024); long term "
    "at 10% (12.5% from 23 Jul 2024) above the yearly exemption, which is shared with your listed shares. Units held on "
    "31 Jan 2018 cost at least that day's NAV, but not more than the sale value.",
    "Debt funds bought from 1 Apr 2023 (and, for sales before 1 Apr 2025, gold and overseas funds bought from then): "
    "gains are short term whatever the holding period, taxed at your slab rate (section 50AA).",
    "Other funds: for sales from 23 Jul 2024, long term after more than 24 months, at 12.5% without indexation; for "
    "earlier sales, after more than 36 months, at 20% with indexation. Short-term gains are taxed at your slab rate.",
    "Switches between schemes are sales and new purchases. Gifts aren't sales. A scheme merger keeps the original cost and dates.",
    "Dividends (IDCW) paid out are income at your slab rate, not capital gains: add them to your other income in the tax report.",
    "Stamp duty is part of the cost. STT isn't deductible.",
]


def gains(data: dict, w: dict, today: str) -> dict:
    fys = {r["fy"] for r in w["c"]["realised"]} | set(w["c"]["dividends"])
    if fys:       # the year being filed now is always listed, so every Money page opens on the same year
        fys |= {tax_lots.fy_of(today) - 1}
    fys = sorted(fys, reverse=True)
    missing = sorted({r["key"] for r in w["c"]["realised"] if r["gf"] == "missing"})
    return {"years": [_year(fy, w, data) for fy in fys], "current_fy": tax_lots.fy_of(today), "notes": GAIN_NOTES,
            "gf_missing": missing, "unknown_units": {k: _r(v, 4) for k, v in w["c"]["unknown"].items()},
            "flags": sorted(w["c"]["notes"])}


def view(uid: str, plan: str) -> dict:
    data = load(uid)
    today = today_ist()
    w = worked(data)
    h = holdings(data, w, today)
    can = allows(plan, "mf_gains")
    limit = mf_limit(plan)
    return {**h, "gains": gains(data, w, today) if can else None, "gains_allowed": can,
            "gains_plan": PLANS[FEATURE_PLAN["mf_gains"]]["name"], "limit": limit,
            "files": data["files"], "updated_at": data["updated_at"], "txns": len(data["txns"]),
            "kinds": KINDS, "names": names(data), "nav_date": max((r.get("date") or "" for r in w["daily"].get("schemes", {}).values()), default="") or None,
            "assumptions": ASSUMPTIONS, "disclaimer": DISCLAIMER, "as_of": today}


# ---------- for the tax report and net worth ----------
def realised(uid: str) -> tuple[list[dict], dict[str, dict]]:
    """Every realised mutual fund sale, in the tax report's row shape (with its bucket for the non-equity rules), and
    the scheme names keyed like the rows. Empty when the user has no funds saved."""
    data = load(uid)
    if not data["txns"]:
        return [], {}
    w = worked(data)
    return w["c"]["realised"], names(data)


def for_tax(uid: str) -> dict:
    """What the tax report adds: every realised sale (merged with the share sales so set-off and the exemption are
    shared), the scheme names, and per financial year a short summary for its "Mutual funds" section."""
    data = load(uid)
    if not data["txns"]:
        return {"rows": [], "names": {}, "years": {}}
    w = worked(data)
    rows, years = w["c"]["realised"], {}
    for r in rows:
        y = years.setdefault(r["fy"], {"count": 0, "gain": 0.0, "equity": 0.0, "slab": 0.0, "other_lt": 0.0, "dividends": 0.0})
        y["count"] += 1
        y["gain"] += r["gain"]
        y["equity" if r["kind"] == "equity" else "slab" if r.get("bucket") == "st_slab" else "other_lt"] += r["gain"]
    for fy, v in w["c"]["dividends"].items():
        years.setdefault(fy, {"count": 0, "gain": 0.0, "equity": 0.0, "slab": 0.0, "other_lt": 0.0, "dividends": 0.0})["dividends"] = v
    return {"rows": rows, "names": names(data), "years": {fy: {k: _r(v) if isinstance(v, float) else v for k, v in y.items()}
                                                          for fy, y in years.items()}}


def capital_gains(uid: str, fy: int) -> dict:
    """One financial year's mutual fund gains in the tax report's year shape (buckets, set-off, exemption, rows), with
    dividends paid out that year. The exemption here is the funds' alone; the tax report shares it with shares."""
    data = load(uid)
    w = worked(data)
    return {**_year(fy, w, data), "names": names(data)}


def total_value(uid: str) -> float:
    """What the user's mutual funds are worth today at the latest NAV (₹), for net worth. 0 with none saved."""
    data = load(uid)
    if not data["txns"]:
        return 0.0
    return float(holdings(data, worked(data), today_ist())["total"]["value"] or 0.0)


# ---------- API ----------
router = APIRouter(prefix="/money/mutual-funds", tags=["money"])
_throttle = None


def setup(throttle):
    """The app's per-user action limit, shared with the other routes."""
    global _throttle
    _throttle = throttle


def _limit(profile, what: str, times: int, message: str):
    if _throttle:
        _throttle(profile, what, times, 3600, message)


class ImportReq(BaseModel):
    filename: str = Field("", max_length=200)
    data: str = Field(..., max_length=MAX_PDF * 4 // 3 + 64)
    password: str = Field("", max_length=64)
    mode: str = Field("add", pattern="^(add|replace)$")


class KindReq(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    kind: str | None = Field(None, pattern="^(equity|debt|hybrid|other)$")


class FmvReq(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    nav: float | None = Field(None, gt=0, lt=1e7)


@router.get("")
def mf_view(profile=Depends(current_profile)):
    """The user's mutual funds: holdings with value, gain and XIRR, allocation by category, and capital gains per
    financial year (Basic and up)."""
    return ok(view(profile["id"], profile["_plan"]))


@router.post("/import")
async def mf_import(req: ImportReq, profile=Depends(current_profile)):
    """Read a detailed CAS PDF (opened in memory with the password, neither ever stored) or a CSV of transactions,
    and save its schemes and transactions with the ones already saved, duplicates skipped."""
    _limit(profile, "mf_import", 30, "That's a lot of uploads in an hour. Try again a little later.")
    raw = re.sub(r"^data:[^,]{0,200},", "", req.data.strip())
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        err(400, "bad_upload", "The file didn't arrive whole. Pick it again.")
    if not data:
        err(400, "bad_upload", "The file is empty.")
    return await run_in_threadpool(_import, profile, data, req.filename, req.password, req.mode)


def _import(profile, data: bytes, filename: str, password: str, mode: str):
    try:
        got = read_file(data, filename, password)
    except FileError as e:
        err(400, "wrong_password" if "password" in str(e) else "bad_file", str(e))
    uid = profile["id"]
    counts, limit = apply_import(profile, got, filename, mode)
    return ok({"kind": got["kind"], **counts, "problems": got["problems"], "limit": limit,
               "upgrade": f"{PLANS['basic']['name']} keeps every scheme." if counts["over_limit"] else None,
               "view": view(uid, profile["_plan"])})


def apply_import(profile, got: dict, filename: str, mode: str = "add") -> tuple[dict, int | None]:
    """Save a read statement with the user's mutual funds (duplicates skipped, history kept): (counts, plan limit). The
    upload route and the statement inbox both end here."""
    uid = profile["id"]
    before = empty() if mode == "replace" else load(uid)
    if mode == "replace":
        old = load(uid)
        before["kinds"], before["fmv"] = old["kinds"], old["fmv"]
    merged, counts = merge(before, got, mf_limit(profile["_plan"]))
    if counts["added"] or mode == "replace":
        merged["files"] = (merged["files"] + [{"name": (filename or got["kind"])[:80], "kind": got["kind"], "txns": counts["added"],
                                               "at": datetime.now(timezone.utc).isoformat(timespec="minutes")}])[-MAX_FILES:]
        keys = {s["k"] for s in merged["schemes"]}
        merged["kinds"] = {k: v for k, v in merged["kinds"].items() if k in keys}
        merged["fmv"] = {k: v for k, v in merged["fmv"].items() if k in keys}
        save(uid, merged)
    return counts, mf_limit(profile["_plan"])


@router.put("/kind")
def mf_kind(req: KindReq, profile=Depends(current_profile)):
    """Set (or clear, back to the one read from the category) how a scheme is taxed."""
    _limit(profile, "mf_edit", 120, "That's a lot of changes in an hour. Try again a little later.")
    data = load(profile["id"])
    if not any(s["k"] == req.key for s in data["schemes"]):
        err(404, "no_scheme", "That scheme isn't in your saved funds.")
    kinds = {k: v for k, v in data["kinds"].items() if k != req.key}
    if req.kind:
        kinds[req.key] = req.kind
    save(profile["id"], {**data, "kinds": kinds})
    return ok(view(profile["id"], profile["_plan"]))


@router.put("/fmv")
def mf_fmv(req: FmvReq, profile=Depends(current_profile)):
    """Set (or clear) a scheme's NAV on 31 Jan 2018, used to grandfather units bought by then."""
    _limit(profile, "mf_edit", 120, "That's a lot of changes in an hour. Try again a little later.")
    data = load(profile["id"])
    if not any(s["k"] == req.key for s in data["schemes"]):
        err(404, "no_scheme", "That scheme isn't in your saved funds.")
    fmv = {k: v for k, v in data["fmv"].items() if k != req.key}
    if req.nav:
        fmv[req.key] = round(float(req.nav), 4)
    save(profile["id"], {**data, "fmv": fmv})
    return ok(view(profile["id"], profile["_plan"]))


@router.delete("")
def mf_delete(profile=Depends(current_profile)):
    """Delete my mutual fund data: every scheme, transaction and setting, at once."""
    delete(profile["id"])
    return {"deleted": True}
