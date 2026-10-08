"""Dividends: the user's dividend income for each financial year, the TDS the companies should have cut, US
dividends with the US tax withheld (a foreign tax credit figure), and the year's total for the tax estimate.

Three sources, in this order of trust: the dividend sheet of the user's broker tax P&L (read when the ZIP or workbook
is uploaded to the tax report), a dividend CSV the user uploads, and, when neither covers a year, an estimate from
My Holdings × the dividends the companies declared (the stored corporate actions), labelled "estimated".

Stored per user in app_settings (moneydiv:<uid>), seen only by that user, and deleted with the tax data. Facts and
arithmetic on the user's own dividends; never a view on any company."""
import io
import json
import math
import re
import zipfile
from datetime import date, datetime, timezone

from . import corp_actions, db
from . import holdings_file as hf
from .tax_lots import fy_label, fy_of

KEY = "moneydiv:"
MAX_ROWS = 3000                   # dividend lines kept: a long portfolio's years of payments are a few hundred
MAX_FILES = 20
MAX_BYTES = 5 * 1024 * 1024       # a dividend CSV is a few kilobytes
MAX_AMOUNT = 1e10
TDS_RATE = 0.10                   # with a PAN; 20% without one
US_WITHHOLDING = 0.25             # India-US tax treaty, Article 10, for an individual who gave the broker a W-8BEN
FIRST_TAXED_FY = 2020             # dividends became taxable in the shareholder's hands from FY 2020-21

COLUMNS = {
    "symbol": hf.COLUMNS["symbol"] | {"stocksymbol", "scripsymbol"},
    "name": hf.COLUMNS["name"],
    "isin": hf.COLUMNS["isin"],
    "date": {"exdate", "exdividenddate", "recorddate", "date", "paymentdate", "paydate", "creditdate", "dividenddate",
             "datepaid", "paiddate", "receiveddate", "transactiondate"},
    "qty": hf.COLUMNS["qty"],
    "per_share": {"dividendpershare", "dps", "pershare", "amountpershare", "rate", "dividendrate", "ratepershare"},
    "amount": {"grossdividend", "grossamount", "grossdividendamount", "dividendamount", "netdividendamount", "amount",
               "dividend", "totalamount", "totaldividend", "total", "amountreceived", "gross", "netamount"},
    "tds": {"tds", "tdsamount", "taxdeducted", "tdsdeducted", "withholding", "withholdingtax", "taxwithheld", "ustax"},
    "currency": {"currency", "ccy", "cur"},
    "country": {"country", "market", "region"},
}
AMOUNT_ORDER = ["grossdividend", "grossamount", "grossdividendamount", "dividendamount", "netdividendamount", "amount",
                "dividend", "totalamount", "totaldividend", "total", "amountreceived", "gross", "netamount"]


def tds_threshold(fy: int) -> float | None:
    """The yearly dividend from one company above which it cuts TDS from a resident: ₹10,000 from FY 2025-26
    (Finance Act 2025), ₹5,000 before; None before FY 2020-21, when dividends weren't taxed in the shareholder's
    hands."""
    if fy >= 2025:
        return 10000.0
    if fy >= FIRST_TAXED_FY:
        return 5000.0
    return None


def tds_section(fy: int) -> str:
    return ("section 393(1) of the Income-tax Act, 2025 (section 194 of the 1961 Act)" if fy >= 2026
            else "section 194 of the Income-tax Act")


def expected_tds(fy: int, total: float) -> float:
    """TDS one company cuts on a year's dividends: 10% of all of it once the total is over the threshold."""
    t = tds_threshold(fy)
    return round(total * TDS_RATE, 2) if t is not None and total > t else 0.0


# ---------- reading files ----------
def _cols(row: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    keys = [hf.key(c) for c in row]
    for field, names in COLUMNS.items():
        if field == "amount":
            for want in AMOUNT_ORDER:              # the gross amount before any other
                if want in keys:
                    found[field] = keys.index(want)
                    break
            continue
        for i, k in enumerate(keys):
            if k in names and field not in found and i not in found.values():
                found[field] = i
    return found


def _header(rows: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    for i, row in enumerate(rows[:hf.HEADER_SCAN]):
        c = _cols(row)
        if c.keys() & {"symbol", "name", "isin"} and "date" in c and ("amount" in c or {"qty", "per_share"} <= c.keys()):
            return i, c
    return None


def _sym(v: str) -> str:
    return re.sub(r"^(NSE|BSE)[:\s]+|(-EQ|\.NS|\.BO)$", "", str(v or "").strip().upper())[:20]


def rows_from_table(rows: list[list[str]], src: str) -> tuple[list[dict], list[dict]]:
    """(dividends, problems) from one table with a header row. Each dividend is {d, sym, name, isin, qty, ps,
    amount (gross, in its currency), tds, cur, src}. A total line or a line without a date is left out."""
    got = _header(rows)
    if not got:
        return [], []
    start, c = got
    out, problems = [], []

    def cell(r, f):
        i = c.get(f)
        return r[i].strip() if i is not None and i < len(r) else ""
    for n, r in enumerate(rows[start + 1:], start + 2):
        if not any(x.strip() for x in r):
            continue
        sym, name, isin = _sym(cell(r, "symbol")), cell(r, "name")[:60], cell(r, "isin").upper()[:12]
        d = hf.day(cell(r, "date"))
        if not (sym or name or isin) or re.match(r"(?i)total", cell(r, "symbol") or cell(r, "name")):
            continue
        qty, ps = hf.number(cell(r, "qty")), hf.number(cell(r, "per_share"))
        amount = hf.number(cell(r, "amount"))
        if amount is None and qty and ps:
            amount = qty * ps
        if not d or amount is None or amount <= 0 or amount > MAX_AMOUNT:
            problems.append({"line": n, "text": " · ".join(x for x in (sym or name, cell(r, "date"), cell(r, "amount")) if x)[:80],
                             "reason": "No date" if not d else "No dividend amount"})
            continue
        cur_text = (cell(r, "currency") + " " + cell(r, "country")).upper()
        us = bool(re.search(r"\b(USD|US|USA|UNITED STATES)\b", cur_text)) or isin.startswith("US")
        tds = hf.number(cell(r, "tds"))
        out.append({"d": d, "sym": sym or isin or name.upper()[:20], "name": name, "isin": isin,
                    "qty": qty if qty and qty > 0 else None, "ps": ps if ps and ps > 0 else None, "amount": round(amount, 4),
                    "tds": round(abs(tds), 4) if tds else None, "cur": "USD" if us else "INR", "src": src})
        if len(out) >= MAX_ROWS:
            break
    return out, problems[:100]


def _workbook(raw: bytes, src: str, only_dividend_sheets: bool) -> tuple[list[dict], list[dict]]:
    out, problems = [], []
    for name, rows in hf.sheets(raw, hf.MAX_ROWS):
        if only_dividend_sheets and not re.search(r"(?i)dividend", name):
            continue
        got, probs = rows_from_table(rows, src)
        out += got
        problems += probs
    return out, problems


def from_tax_file(data: bytes, filename: str = "") -> list[dict]:
    """The dividends on a broker tax P&L's dividend sheet (Zerodha's workbook has one in newer years), in the ZIP as
    it downloads or the workbook on its own. Anything unreadable gives none: the tax import has its own messages."""
    try:
        if data[:4] != b"PK\x03\x04":
            return []
        if hf._is_xlsx(data):
            return _workbook(data, "statement", True)[0]
        zf = zipfile.ZipFile(io.BytesIO(data))
        budget, out = [hf.ZIP_MAX_UNPACKED], []
        for info in zf.infolist()[:hf.ZIP_MAX_ENTRIES]:
            if not hf._safe_name(info.filename) or hf._junk(info.filename) or info.flag_bits & 0x1:
                continue
            base = hf._base(info.filename)
            if re.search(r"(?i)\.xlsx$", base):
                out += _workbook(hf._unpack(zf, info, budget), "statement", True)[0]
            elif re.search(r"(?i)dividend.*\.(csv|txt)$", base):
                out += rows_from_table(hf.table(hf._unpack(zf, info, budget), MAX_BYTES), "statement")[0]
        return out[:MAX_ROWS]
    except Exception:
        return []


def parse_upload(data: bytes, filename: str = "") -> dict:
    """A dividend file the user uploads: a CSV or Excel file with a date, the company (symbol, name or ISIN) and the
    amount (or quantity and dividend a share), and optionally TDS and currency; or a broker's tax P&L ZIP or
    workbook with a dividend sheet. Raises FileError with a plain message when nothing can be read."""
    if not data:
        raise hf.FileError("That file is empty.")
    if len(data) > hf.TAX_MAX_BYTES:
        raise hf.FileError(f"That file is larger than {hf.TAX_MAX_BYTES // (1024 * 1024)} MB.")
    rows, problems = [], []
    if data[:4] == b"PK\x03\x04" and not hf._is_xlsx(data):
        rows = from_tax_file(data, filename)
    elif data[:4] == b"PK\x03\x04":
        rows, problems = _workbook(data, "csv", True)
        if not rows:
            rows, problems = _workbook(data, "csv", False)
    else:
        rows, problems = rows_from_table(hf.table(data, MAX_BYTES), "csv")
    if not rows:
        raise hf.FileError("No dividends were found in that file. It needs columns for the date, the company (symbol, "
                           "name or ISIN) and the amount (or quantity and dividend a share).")
    return {"rows": rows, "problems": problems}


# ---------- stored ----------
def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def _row_ok(r) -> bool:
    return (isinstance(r, dict) and isinstance(r.get("d"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["d"]) is not None
            and isinstance(r.get("amount"), (int, float)) and math.isfinite(r["amount"]) and r["amount"] > 0
            and r.get("cur") in ("INR", "USD") and isinstance(r.get("sym"), str))


def load(uid: str) -> dict:
    """{"rows", "files", "include": {fy: bool}, "updated_at"}."""
    got = db.json_value(db.get_setting(_key(uid)), {})
    got = got if isinstance(got, dict) else {}
    inc = got.get("include") if isinstance(got.get("include"), dict) else {}
    return {"rows": [r for r in got.get("rows") or [] if _row_ok(r)], "files": [f for f in got.get("files") or [] if isinstance(f, dict)],
            "include": {int(k): bool(v) for k, v in inc.items() if str(k).isdigit() and 2000 <= int(k) <= 2100},
            "updated_at": got.get("updated_at")}


def save(uid: str, data: dict):
    db.set_setting(_key(uid), json.dumps({"rows": data["rows"][-MAX_ROWS:], "files": data["files"][-MAX_FILES:],
                                          "include": {str(k): v for k, v in data["include"].items()},
                                          "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
                                         separators=(",", ":")))


def delete(uid: str):
    db.delete_setting(_key(uid))


def _dedup(r: dict) -> tuple:
    return (r["d"], r.get("isin") or r["sym"], round(r["amount"], 2), r["cur"])


def merge(old: list[dict], new: list[dict]) -> tuple[list[dict], int, int]:
    """(rows, added, already there): the same file uploaded again adds nothing."""
    have = {_dedup(r) for r in old}
    out, added, dup = list(old), 0, 0
    for r in new:
        k = _dedup(r)
        if k in have:
            dup += 1
            continue
        have.add(k)
        out.append(r)
        added += 1
    return out, added, dup


def add(uid: str, rows: list[dict], filename: str, source: str) -> tuple[int, int]:
    """Save a file's dividends with the ones already saved. (added, already there)."""
    data = load(uid)
    data["rows"], added, dup = merge(data["rows"], rows)
    if added:
        data["files"].append({"name": (filename or "file")[:80], "source": source, "rows": added,
                              "at": datetime.now(timezone.utc).isoformat(timespec="minutes")})
        save(uid, data)
    return added, dup


def set_include(uid: str, fy: int, on: bool):
    data = load(uid)
    data["include"][fy] = bool(on)
    save(uid, data)


# ---------- estimated from holdings ----------
def estimate(items: list[dict], actions: dict[str, list[dict]], today: date, fallback_since: str | None,
             market: str = "IN") -> tuple[list[dict], list[dict]]:
    """(paid, ahead): each declared dividend × the shares held at its ex-date, worked back from today's holding
    through any bonus or split, assuming no trades in between. `ahead` are those with an ex-date still to come."""
    paid, ahead = [], []
    fallback = (fallback_since or today.isoformat())[:10]
    for i in items:
        acts = actions.get(i["symbol"]) or []
        since = str(i.get("since") or fallback)[:10]
        adj = sorted((a for a in acts if corp_actions.adjusts(a)), key=lambda a: a["ex_date"])
        for a in acts:
            if a.get("kind") != "dividend" or not isinstance(a.get("amount"), (int, float)) or a["amount"] <= 0:
                continue
            q = corp_actions.qty_before(a["ex_date"], i, since, adj)
            if q <= 0:
                continue
            r = {"d": a.get("record_date") or a["ex_date"], "ex": a["ex_date"], "sym": i["symbol"], "name": a.get("name") or "",
                 "isin": "", "qty": round(q, 4), "ps": a["amount"], "amount": round(q * a["amount"], 4), "tds": None,
                 "cur": "USD" if market == "US" else "INR", "src": "estimated", "label": a.get("label") or "Dividend"}
            (ahead if a["ex_date"] > today.isoformat() else paid).append(r)
    return paid, ahead


# ---------- the view ----------
def _inr(r: dict, usd_inr: float | None) -> float | None:
    if r["cur"] == "INR":
        return r["amount"]
    return r["amount"] * usd_inr if usd_inr else None


def year(fy: int, rows: list[dict], usd_inr: float | None, full: bool = True) -> dict:
    """One financial year's dividends: by company, Indian ones with the TDS expected, US ones with the 25% withheld."""
    by: dict[tuple, dict] = {}
    unpriced = 0
    for r in rows:
        v = _inr(r, usd_inr)
        if v is None:
            unpriced += 1
            continue
        k = (r["cur"], r.get("isin") or r["sym"])
        cur = by.setdefault(k, {"symbol": r["sym"], "name": r.get("name") or "", "country": "US" if r["cur"] == "USD" else "IN",
                                "count": 0, "amount": 0.0, "amount_usd": 0.0 if r["cur"] == "USD" else None, "tds_file": None,
                                "first": r["d"], "last": r["d"]})
        cur["count"] += 1
        cur["amount"] += v
        if r["cur"] == "USD":
            cur["amount_usd"] += r["amount"]
        if r.get("tds"):
            cur["tds_file"] = (cur["tds_file"] or 0.0) + (r["tds"] * (usd_inr or 0) if r["cur"] == "USD" else r["tds"])
        cur["first"], cur["last"] = min(cur["first"], r["d"]), max(cur["last"], r["d"])
    t = tds_threshold(fy)
    companies = []
    for c in by.values():
        c["amount"] = round(c["amount"], 2)
        if c["country"] == "IN":
            c["tds_expected"] = expected_tds(fy, c["amount"])
            c["over_threshold"] = t is not None and c["amount"] > t
        else:
            c["amount_usd"] = round(c["amount_usd"], 2)
            c["withheld_usd"] = round(c["amount_usd"] * US_WITHHOLDING, 2)
            c["withheld"] = round(c["amount"] * US_WITHHOLDING, 2)
        if c["tds_file"] is not None:
            c["tds_file"] = round(c["tds_file"], 2)
        companies.append(c)
    companies.sort(key=lambda c: (c["country"], -c["amount"]))
    india = [c for c in companies if c["country"] == "IN"]
    us = [c for c in companies if c["country"] == "US"]
    india_total = round(sum(c["amount"] for c in india), 2)
    us_total = round(sum(c["amount"] for c in us), 2)
    us_usd = round(sum(c["amount_usd"] for c in us), 2)
    out = {"fy": fy, "label": fy_label(fy), "total": round(india_total + us_total, 2), "india_total": india_total,
           "us_total": us_total, "count": sum(c["count"] for c in companies), "companies_count": len(companies),
           "unpriced": unpriced, "taxed": fy >= FIRST_TAXED_FY,
           "tds": {"threshold": t, "rate": TDS_RATE, "section": tds_section(fy),
                   "expected": round(sum(c["tds_expected"] for c in india), 2),
                   "companies_over": sum(1 for c in india if c["over_threshold"]),
                   "in_file": round(sum(c["tds_file"] or 0 for c in india), 2) if any(c["tds_file"] is not None for c in india) else None},
           "us": {"gross_usd": us_usd, "gross": us_total, "rate": US_WITHHOLDING,
                  "withheld_usd": round(us_usd * US_WITHHOLDING, 2), "withheld": round(us_total * US_WITHHOLDING, 2)} if us else None,
           "companies": companies if full else [], "locked": not full}
    return out


ASSUMPTIONS = [
    "Dividends are income from other sources, taxed at your slab rate (since FY 2020-21; before that the company paid "
    "dividend distribution tax and they were exempt).",
    "Amounts are the gross dividend, before TDS. If your file shows amounts after TDS, the TDS has to be added back.",
    "A dividend is placed in the financial year of its record date (or the date in your file). The law taxes a final "
    "dividend in the year it is declared and an interim one in the year it is paid, which can differ near 31 March.",
    "TDS: a company cuts 10% from a resident with a PAN (20% without) once its dividends to you in the year are over "
    "₹10,000 (₹5,000 before FY 2025-26), on the whole amount. The TDS shown is what that rule gives; Form 26AS or the "
    "AIS has what was actually cut.",
    "US dividends: 25% US tax withheld, the India-US tax treaty rate for someone who gave their broker a W-8BEN. In "
    "India the dividend is taxed at your slab rate, and the US tax can be claimed as a foreign tax credit, up to the "
    "Indian tax on that income, by filing Form 67 before the return.",
    "US amounts are in rupees at today's dollar rate. The rule for the credit uses the State Bank of India's TT buying "
    "rate on the last day of the month before the dividend, so the figure in the return can differ.",
]
EST_ASSUMPTIONS = [
    "Estimated: each dividend the company declared × the shares in My Holdings on its ex-date, worked back from "
    "today's quantity through any bonus or split, assuming you bought or sold none in between. Upload your broker's "
    "dividend statement for the actual figures.",
]


def view(stored: dict, estimated: list[dict], ahead: list[dict], usd_inr: float | None, today: date, full: bool = True) -> dict:
    """Every year with dividends (and this one): the source used for each, whether it goes into the tax estimate, and
    the estimate beside the files' figure when both exist."""
    cur_fy = fy_of(today.isoformat())
    own_years = {fy_of(r["d"]) for r in stored["rows"]}
    fys = sorted(own_years | {fy_of(r["d"]) for r in estimated} | {cur_fy, cur_fy - 1}, reverse=True)
    years = []
    for fy in fys:
        own = [r for r in stored["rows"] if fy_of(r["d"]) == fy]
        est = [r for r in estimated if fy_of(r["d"]) == fy]
        source = "files" if own else "estimated" if est else "none"
        y = year(fy, own or est, usd_inr, full)
        y["source"] = source
        y["include"] = stored["include"].get(fy, source == "files") and source != "none" and y["taxed"]
        y["include_saved"] = fy in stored["include"]
        y["estimate_total"] = round(sum(_inr(r, usd_inr) or 0 for r in est), 2) if est else None
        years.append(y)
    ahead_rows = sorted(ahead, key=lambda r: r["ex"])
    return {"years": years, "current_fy": cur_fy, "files": stored["files"], "updated_at": stored["updated_at"],
            "ahead": [{"symbol": r["sym"], "ex_date": r["ex"], "label": r.get("label"), "qty": r["qty"], "per_share": r["ps"],
                       "currency": r["cur"], "amount": round(r["amount"], 2)} for r in ahead_rows] if full else [],
            "ahead_total": round(sum(_inr(r, usd_inr) or 0 for r in ahead_rows), 2),
            "usd_inr": usd_inr, "as_of": today.isoformat(), "assumptions": ASSUMPTIONS + (EST_ASSUMPTIONS if estimated else []),
            "locked": not full}


def for_total(v: dict) -> dict[int, float]:
    """{fy: dividends} for the years the user includes in the total tax estimate."""
    return {y["fy"]: y["total"] for y in v["years"] if y["include"] and y["total"] > 0}


def events(v: dict, stored: dict, estimated: list[dict], usd_inr: float | None, fy: int) -> list[tuple[str, float]]:
    """(date, rupees) of each dividend in a year whose total goes into the tax estimate: for the advance tax rule
    that income arising after a due date is spread over the later instalments."""
    y = next((x for x in v["years"] if x["fy"] == fy), None)
    if not y or not y["include"]:
        return []
    rows = [r for r in stored["rows"] if fy_of(r["d"]) == fy] if y["source"] == "files" else [r for r in estimated if fy_of(r["d"]) == fy]
    return sorted((r["d"], _inr(r, usd_inr)) for r in rows if _inr(r, usd_inr))
