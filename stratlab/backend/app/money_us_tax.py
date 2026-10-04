"""US stocks, Indian tax: capital gains on US shares in rupees the way Rule 115 converts them, US dividends with the
25% US tax and the foreign tax credit (Form 67), and the calendar-year Schedule FA table, for a resident individual.

The rules (checked 4 Oct 2026; sources in rules.py):
- Shares listed abroad are not "listed on a recognised stock exchange in India", so they are taxed like unlisted
  shares: long term when held for more than 24 months; long-term gains at 12.5% without indexation for transfers
  from 23 July 2024 (section 112 as amended by the Finance (No. 2) Act 2024), 20% with indexation before that; short
  term at the slab rate. No ₹1.25 lakh exemption (that is section 112A, Indian listed shares only), no STT.
- Rupees: each leg at SBI's TT buying rate on the last day of the month before (Rule 115): the sale in the month
  before the sale, the cost in the month before the purchase (money_fx.py).
- The US does not tax a non-resident's gains on US shares; it withholds 25% of dividends (India-US treaty, Article
  10, with a W-8BEN). India taxes the dividend at the slab rate and allows a credit for the US tax, up to the Indian
  tax on that income (section 90, Rule 128), claimed on Form 67 by the end of the assessment year.
- Schedule FA (ITR-2 and ITR-3, residents): every foreign asset held at any time in the calendar year ending in the
  previous year, one line per purchase lot in Table A3, with the initial, peak and closing value and the income, each
  at the TT buying rate on its own date. It is a disclosure with no minimum; leaving it out can draw a ₹10 lakh
  penalty under the Black Money Act (none since 1 Oct 2024 when the assets other than property total ₹20 lakh or
  less).

The user's US trades (bought and sold, in dollars) are stored per user (ustax:<uid>), seen only by them, never
logged, and deleted with the tax data. Arithmetic on the user's own trades; never a view on what to do."""
import json
import math
import re
from datetime import date, datetime, timezone

from . import db, holdings_file as hf, money_fx as fx
from .money_mf import CII, held_over
from .tax_lots import RATE_CHANGE, fy_label, fy_of

KEY = "ustax:"
MAX_TRADES = 5000
MAX_FILES = 20
MAX_BYTES = 5 * 1024 * 1024
MAX_QTY, MAX_PRICE = 1e9, 1e7
LT_MONTHS = 24                    # unlisted (and foreign) shares: long term when held more than 24 months
LT_RATE, LT_RATE_OLD = 0.125, 0.20
US_WITHHOLDING = 0.25             # India-US treaty, Article 10(2)(b), for an individual with a W-8BEN
COUNTRY = "2-UNITED STATES OF AMERICA"   # as the ITR's country list writes it
EPS = 1e-9

COLUMNS = {
    "date": hf.TRADE_COLUMNS["date"] | {"settlementdate", "tradedateutc", "activitydate", "runtime"},
    "side": hf.TRADE_COLUMNS["side"] | {"activity", "activitytype", "buysellflag"},
    "symbol": {"symbol", "ticker", "stocksymbol", "stock", "instrument", "security", "securitysymbol", "scrip"},
    "name": {"name", "companyname", "securityname", "description", "stockname"},
    "qty": hf.TRADE_COLUMNS["qty"] | {"shares", "units", "noofshares", "numberofshares"},
    "price": hf.TRADE_COLUMNS["price"] | {"priceusd", "tradepriceusd", "fillprice", "avgfillprice", "costpershare"},
    "fees": {"fees", "fee", "commission", "commissions", "charges", "brokerage", "commfee", "ibcommission", "totalfees", "feesusd"},
    "value": hf.TRADE_COLUMNS["value"] | {"amountusd", "proceeds", "netamount"},
}
ASSUMPTIONS = [
    "You are a resident (and ordinarily resident) individual in the year; non-residents don't report foreign assets "
    "and are taxed differently.",
    "US shares are taxed like unlisted shares: long term when held more than 24 months, at 12.5% without indexation "
    "for sales from 23 July 2024 (20% with indexation before), short term at your slab rate. No ₹1.25 lakh exemption.",
    "Rupees under Rule 115: the sale at SBI's TT buying rate on the last day of the month before the sale, and the "
    "cost at the rate on the last day of the month before the purchase (a common reading; some convert both at the "
    "sale's rate). Where SBI's rate for a date isn't known, the RBI reference rate is used and labelled.",
    "Purchases and sales are matched first in, first out per stock across everything you entered; fees are added to "
    "the cost and taken off the sale. Splits are applied from the stock's history.",
    "US dividends: 25% US tax withheld unless your file says otherwise. The credit is the lower of that tax and the "
    "Indian tax on the dividend, worked out at your average rate of tax from the total tax estimate.",
    "Schedule FA: one line per purchase lot held at any time in the calendar year; values at SBI's TT buying rate on "
    "each date (purchase, the day of the highest value, 31 December, each dividend and sale). Prices are each day's "
    "close. Your broker's own year statement wins where it differs.",
]
FACTS = [
    "Schedule FA covers the calendar year (1 January to 31 December) that ends in the financial year: for the return "
    "of FY 2025-26 (AY 2026-27), calendar 2025.",
    "Schedule FA is filed with the return, by its due date: 31 July, or 31 August with business income and no audit "
    "(from FY 2025-26), or 31 October with an audit. A belated or revised return can add it.",
    "Form 67 (the foreign tax credit statement) has to be filed on or before the end of the assessment year (Rule "
    "128(9) as amended in August 2022): by 31 March 2027 for FY 2025-26. From tax year 2026-27 it becomes Form 44 "
    "under the Income-tax Rules 2026.",
    "Leaving a foreign asset out of Schedule FA can draw a ₹10 lakh penalty under the Black Money Act; since 1 October "
    "2024 there is none when the foreign assets other than property total ₹20 lakh or less. The disclosure itself has "
    "no minimum.",
    "The US doesn't tax a non-resident's gains on US shares, so there is no US tax to credit on them.",
]


# ---------- reading files ----------
def _cols(row: list[str]) -> dict[str, int]:
    keys = [hf.key(c) for c in row]
    found: dict[str, int] = {}
    for field, names in COLUMNS.items():
        for i, k in enumerate(keys):
            if k in names and field not in found and i not in found.values():
                found[field] = i
    return found


def _money(v: str) -> float | None:
    s = re.sub(r"(?i)usd|us\$|\$", "", str(v or "")).strip()
    return hf.number(s)


def _side(v: str) -> str | None:
    s = str(v or "").strip().lower()
    if re.match(r"^(b|buy|bought|purchase|buy to open|market buy|limit buy|bot)\b", s) or s in ("b", "buy"):
        return "B"
    if re.match(r"^(s|sell|sold|sale|sell to close|market sell|limit sell|sld)\b", s):
        return "S"
    return None


def _dates(values: list[str]) -> str:
    """"mdy" when a slashed date in the column only reads month first (03/24/2025), else "dmy" (Indian files)."""
    first = second = False
    for v in values:
        m = re.match(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", v or "")
        if m:
            first |= int(m.group(1)) > 12
            second |= int(m.group(2)) > 12
    return "mdy" if second and not first else "dmy"


def _day(v: str, order: str) -> str | None:
    m = re.match(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", v or "")
    if m and order == "mdy":
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None
    return hf.day(v)


def parse_upload(data: bytes, filename: str = "") -> dict:
    """US trades from a CSV or Excel file: the date, purchase or sale, the ticker, the quantity and the price in dollars
    (and optionally fees). {"rows", "problems", "month_first"}. Raises FileError when nothing can be read."""
    if not data:
        raise hf.FileError("That file is empty.")
    if len(data) > MAX_BYTES:
        raise hf.FileError(f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    tables = [rows for _, rows in hf.sheets(data, hf.MAX_ROWS)] if data[:4] == b"PK\x03\x04" else [hf.table(data, MAX_BYTES)]
    for rows in tables:
        for i, row in enumerate(rows[:hf.HEADER_SCAN]):
            c = _cols(row)
            if {"date", "symbol", "qty"} <= c.keys() and ("price" in c or "value" in c):
                return _rows(rows[i + 1:], c, i + 2)
    raise hf.FileError("No US trades were found in that file. It needs columns for the date, the trade (purchase or sale), "
                       "the ticker, the quantity and the price in dollars.")


def _rows(rows: list[list[str]], c: dict[str, int], first_line: int) -> dict:
    def cell(r, f):
        i = c.get(f)
        return r[i].strip() if i is not None and i < len(r) else ""
    order = _dates([cell(r, "date") for r in rows])
    out, problems = [], []
    for n, r in enumerate(rows, first_line):
        if not any(x.strip() for x in r):
            continue
        sym = re.sub(r"[^A-Z0-9.\-]", "", cell(r, "symbol").upper()).replace(".", "-")[:10]
        qty = _money(cell(r, "qty"))
        side = _side(cell(r, "side")) if "side" in c else ("S" if qty is not None and qty < 0 else "B")
        qty = abs(qty) if qty is not None else None
        price = _money(cell(r, "price"))
        if price is None and qty:
            v = _money(cell(r, "value"))
            price = abs(v) / qty if v is not None else None
        d = _day(cell(r, "date"), order)
        fees = abs(_money(cell(r, "fees")) or 0.0)
        text = " · ".join(x for x in (cell(r, "date"), cell(r, "side"), sym, cell(r, "qty")) if x)[:80]
        if not sym or re.match(r"(?i)total", cell(r, "symbol")):
            continue
        why = ("No date" if not d else "Not a purchase or sale (dividends, deposits and the like are left out)" if not side
               else "No quantity" if not qty or qty > MAX_QTY else "No price" if price is None or price < 0 or price > MAX_PRICE else None)
        if why:
            problems.append({"line": n, "text": text, "reason": why})
            continue
        out.append({"d": d, "side": side, "sym": sym, "qty": round(qty, 6), "price": round(price, 6), "fees": round(min(fees, MAX_PRICE), 4),
                    "name": cell(r, "name")[:60], "src": "file"})
        if len(out) >= MAX_TRADES:
            break
    if not out:
        raise hf.FileError("No US trades could be read from that file: " + (problems[0]["reason"].lower() if problems else "it has no lines") + ".")
    return {"rows": out, "problems": problems[:100], "month_first": order == "mdy"}


# ---------- stored ----------
def _key(uid: str) -> str:
    return f"{KEY}{uid}"


def _ok(t) -> bool:
    return (isinstance(t, dict) and t.get("side") in ("B", "S") and isinstance(t.get("sym"), str) and t["sym"]
            and isinstance(t.get("d"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["d"]) is not None
            and all(isinstance(t.get(k), (int, float)) and not isinstance(t.get(k), bool) and math.isfinite(t[k]) for k in ("qty", "price"))
            and 0 < t["qty"] <= MAX_QTY and 0 <= t["price"] <= MAX_PRICE)


def load(uid: str) -> dict:
    """{"trades", "files", "updated_at"}."""
    got = db.json_value(db.get_setting(_key(uid)), {})
    got = got if isinstance(got, dict) else {}
    return {"trades": [t for t in got.get("trades") or [] if _ok(t)], "files": [f for f in got.get("files") or [] if isinstance(f, dict)],
            "updated_at": got.get("updated_at")}


def save(uid: str, data: dict):
    keep = ("d", "side", "sym", "qty", "price", "fees", "name", "src", "id")
    db.set_setting(_key(uid), json.dumps({"trades": [{k: t[k] for k in keep if t.get(k) not in (None, "")} for t in data["trades"][:MAX_TRADES]],
                                          "files": data["files"][-MAX_FILES:],
                                          "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, separators=(",", ":")))


def delete(uid: str):
    db.delete_setting(_key(uid))


def _dedup(t: dict) -> tuple:
    return (t["d"], t["side"], t["sym"], round(t["qty"], 4), round(t["price"], 4))


def merge(old: list[dict], new: list[dict]) -> tuple[list[dict], int, int]:
    """(trades, added, already there): the same file uploaded again adds nothing; two equal fills in one file both count."""
    have: dict[tuple, int] = {}
    for t in old:
        have[_dedup(t)] = have.get(_dedup(t), 0) + 1
    out, added, dup = list(old), 0, 0
    for t in new:
        k = _dedup(t)
        if have.get(k, 0) > 0:
            have[k] -= 1
            dup += 1
            continue
        out.append(t)
        added += 1
    return out, added, dup


def add(uid: str, rows: list[dict], filename: str) -> tuple[int, int]:
    data = load(uid)
    data["trades"], added, dup = merge(data["trades"], rows)
    if added:
        data["files"].append({"name": (filename or "file")[:80], "rows": added, "at": datetime.now(timezone.utc).isoformat(timespec="minutes")})
        save(uid, data)
    return added, dup


def remove(uid: str, tid: str) -> bool:
    data = load(uid)
    keep = [t for t in data["trades"] if t.get("id") != tid]
    if len(keep) == len(data["trades"]):
        return False
    data["trades"] = keep
    save(uid, data)
    return True


# ---------- matching ----------
def split_factor(s: dict) -> float | None:
    try:
        f = float(s["numerator"]) / float(s["denominator"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None
    return f if math.isfinite(f) and f > 0 and abs(f - 1) > 1e-9 else None


def match(trades: list[dict], splits: dict[str, list[dict]] | None = None, upto: str | None = None) -> dict:
    """First in, first out per stock, with splits applied to the lots open before each split's date. {"realised":
    [{sym, bought, sold, qty, cost_usd, sale_usd, lot}], "open": [{sym, d, qty, cost_usd, lot, qty0}], "short":
    {sym: shares sold with no purchase}}. `lot` numbers each purchase, so Schedule FA can follow it. `upto` stops
    after that day."""
    by: dict[str, list[dict]] = {}
    for t in trades:
        if upto is None or t["d"] <= upto:
            by.setdefault(t["sym"], []).append(t)
    out = {"realised": [], "open": [], "short": {}}
    n = 0
    for sym in sorted(by):
        events = [(t["d"], 1 if t["side"] == "B" else 2, t) for t in by[sym]]
        first = min(e[0] for e in events)
        for s in (splits or {}).get(sym) or []:
            f = split_factor(s)
            if f and first < s.get("date", "") and (upto is None or s["date"] <= upto):
                events.append((s["date"], 0, f))
        events.sort(key=lambda e: (e[0], e[1]))
        lots: list[dict] = []
        for d, kind, p in events:
            if kind == 0:
                for l in lots:
                    l["qty"] = l["qty"] * p
                continue
            if kind == 1:
                n += 1
                lots.append({"sym": sym, "d": d, "qty": p["qty"], "qty0": p["qty"], "cost_usd": p["qty"] * p["price"] + (p.get("fees") or 0.0), "lot": n})
                continue
            left, each = p["qty"], p["price"] - (p.get("fees") or 0.0) / p["qty"]
            while left > EPS and lots:
                l = lots[0]
                q = min(l["qty"], left)
                cost = l["cost_usd"] * q / l["qty"]
                l["qty"] -= q
                l["cost_usd"] -= cost
                left -= q
                out["realised"].append({"sym": sym, "bought": l["d"], "sold": d, "qty": q, "cost_usd": cost, "sale_usd": q * each, "lot": l["lot"]})
                if l["qty"] <= 1e-7:
                    lots.pop(0)
            if left > 1e-7:
                out["short"][sym] = out["short"].get(sym, 0.0) + left
        out["open"] += [l for l in lots if l["qty"] > 1e-7]
    return out


def long_term(bought: str, sold: str) -> bool:
    """Held for more than 24 months."""
    return held_over(bought, sold, LT_MONTHS)


def classify(bought: str, sold: str) -> dict:
    """The tax treatment of one matched sale: term, the tax report's bucket and the rate (None: slab rate)."""
    if not long_term(bought, sold):
        return {"term": "ST", "bucket": "st_us", "rate": None, "indexed": False}
    if sold >= RATE_CHANGE:
        return {"term": "LT", "bucket": "lt_us", "rate": LT_RATE, "indexed": False}
    return {"term": "LT", "bucket": "lt_usi", "rate": LT_RATE_OLD, "indexed": True}


def index_factor(bought: str, sold: str) -> float:
    """The Cost Inflation Index of the sale's year over the purchase's (base year 2001-02)."""
    fb, fs = fy_of(bought), fy_of(sold)
    last = max(CII)
    return CII.get(min(max(fs, 2001), last), 100) / CII.get(min(max(fb, 2001), last), 100)


def realised(m: dict, hist: dict) -> list[dict]:
    """Each matched sale in rupees under Rule 115, with its term, bucket and rate. A sale whose rate isn't known for
    either date keeps its dollar figures and `unpriced`."""
    out = []
    for r in m["realised"]:
        rb, rs = fx.rule115(hist, r["bought"]), fx.rule115(hist, r["sold"])
        c = classify(r["bought"], r["sold"])
        row = {**r, **c, "fy": fy_of(r["sold"]), "rate_buy": rb, "rate_sell": rs, "unpriced": not (rb and rs)}
        if rb and rs:
            cost = r["cost_usd"] * rb["rate"]
            idx = index_factor(r["bought"], r["sold"]) if c["indexed"] else 1.0
            sale = r["sale_usd"] * rs["rate"]
            row.update({"cost_inr": cost, "indexed_cost": cost * idx if c["indexed"] else None, "sale_inr": sale,
                        "gain_inr": sale - cost * idx, "fallback": rb["fallback"] or rs["fallback"]})
        out.append(row)
    return out


def tax_rows(rows: list[dict]) -> list[dict]:
    """The rupee sales in the tax report's row shape, so set-off with Indian gains and losses happens there."""
    out = []
    for r in rows:
        if r["unpriced"]:
            continue
        cost = r["indexed_cost"] if r["indexed_cost"] is not None else r["cost_inr"]
        out.append({"key": f"US:{r['sym']}", "bought": r["bought"], "sold": r["sold"], "fy": r["fy"], "qty": r["qty"], "cost": cost,
                    "actual_cost": r["cost_inr"], "sale": r["sale_inr"], "gain": r["sale_inr"] - cost, "term": r["term"], "bonus": False,
                    "gf": None, "rate": r["rate"], "bucket": r["bucket"], "src": "us", "kind": "us"})
    return out


def names(trades: list[dict], known: dict[str, str] | None = None) -> dict[str, dict]:
    """The tax report's name entries for the US stocks: "US:AAPL" -> {symbol, name, isin, listed, kind}."""
    out = {}
    for t in trades:
        k = f"US:{t['sym']}"
        n = out.setdefault(k, {"symbol": t["sym"], "name": (known or {}).get(t["sym"]) or t.get("name") or "", "isin": "", "listed": False,
                               "kind": "stock", "market": "US"})
        n["name"] = n["name"] or t.get("name") or ""
    return out


# ---------- dividends and the foreign tax credit ----------
def ftc(income_inr: float, withheld_inr: float, indian_rate: float) -> dict:
    """The foreign tax credit on one income: the lower of the foreign tax and the Indian tax on that income (Rule
    128(6)); any excess is not refunded or carried forward."""
    indian = max(0.0, income_inr) * max(0.0, indian_rate)
    credit = min(max(0.0, withheld_inr), indian)
    return {"income": round(income_inr, 2), "foreign_tax": round(withheld_inr, 2), "indian_tax": round(indian, 2),
            "credit": round(credit, 2), "not_credited": round(max(0.0, withheld_inr - credit), 2)}


def dividends(rows: list[dict], hist: dict, fy: int, indian_rate: float) -> dict:
    """One financial year's US dividends in rupees (Rule 115 for the income, Rule 128 for the tax: the same month-end
    rate), by stock and in total, with the foreign tax credit. `rows` are the dividend lines in dollars ({d, sym,
    amount, tds?})."""
    by: dict[str, dict] = {}
    unpriced = 0
    for r in rows:
        if fy_of(r["d"]) != fy:
            continue
        rt = fx.rule115(hist, r["d"])
        if not rt:
            unpriced += 1
            continue
        tax_usd = r["tds"] if r.get("tds") else r["amount"] * US_WITHHOLDING
        c = by.setdefault(r["sym"], {"symbol": r["sym"], "count": 0, "usd": 0.0, "tax_usd": 0.0, "inr": 0.0, "tax_inr": 0.0, "fallback": False,
                                     "lines": []})
        c["count"] += 1
        c["usd"] += r["amount"]
        c["tax_usd"] += tax_usd
        c["inr"] += r["amount"] * rt["rate"]
        c["tax_inr"] += tax_usd * rt["rate"]
        c["fallback"] |= rt["fallback"]
        c["lines"].append({"d": r["d"], "usd": round(r["amount"], 2), "tax_usd": round(tax_usd, 2), "rate": rt["rate"], "rate_on": rt["on"],
                           "inr": round(r["amount"] * rt["rate"], 2), "estimated": r.get("src") == "estimated"})
    stocks = []
    for c in sorted(by.values(), key=lambda c: -c["inr"]):
        stocks.append({**{k: round(v, 2) if isinstance(v, float) else v for k, v in c.items()}, **{"ftc": ftc(c["inr"], c["tax_inr"], indian_rate)}})
    inr, tax = sum(c["inr"] for c in by.values()), sum(c["tax_inr"] for c in by.values())
    return {"fy": fy, "stocks": stocks, "usd": round(sum(c["usd"] for c in by.values()), 2), "inr": round(inr, 2),
            "tax_inr": round(tax, 2), "ftc": ftc(inr, tax, indian_rate), "indian_rate": round(indian_rate, 4), "unpriced": unpriced}


def quarter_of(d: str) -> int:
    """The advance-tax period a date falls in (0: to 15 Jun, 1: to 15 Sep, 2: to 15 Dec, 3: to 15 Mar, 4: to 31 Mar),
    as the ITR's quarterly tables split income."""
    md = d[5:]
    if "04-01" <= md <= "06-15":
        return 0
    if "06-16" <= md <= "09-15":
        return 1
    if "09-16" <= md <= "12-15":
        return 2
    if md >= "12-16" or md <= "03-15":
        return 3
    return 4




# ---------- Schedule FA ----------
def _after_factor(splits: list[dict], day: str) -> float:
    """Shares on `day` × this = the same holding in today's shares (each split after that day)."""
    f = 1.0
    for s in splits:
        x = split_factor(s)
        if x and s.get("date", "") > day:
            f *= x
    return f


def _qty_on(changes: list[tuple[str, float]], day: str) -> float:
    """A lot's shares at the end of `day`, from its list of (day, shares from then on)."""
    q = 0.0
    for d, v in changes:
        if d > day:
            break
        q = v
    return q


def replay(trades: list[dict], splits: list[dict], upto: str) -> list[dict]:
    """One stock's purchase lots up to a day, first in first out, each with how many shares it held from each day on
    (`changes`, in that day's shares) and its sales ([(day, shares, dollars after fees)])."""
    ts = sorted((t for t in trades if t["d"] <= upto), key=lambda t: (t["d"], 0 if t["side"] == "B" else 1))
    if not ts:
        return []
    events = [(t["d"], 1 if t["side"] == "B" else 2, t) for t in ts]
    events += [(s["date"], 0, split_factor(s)) for s in splits if split_factor(s) and ts[0]["d"] < s.get("date", "") <= upto]
    events.sort(key=lambda e: (e[0], e[1]))
    lots, open_ = [], []
    for d, kind, p in events:
        if kind == 0:
            for l in open_:
                l["qty"] *= p
                l["changes"].append((d, l["qty"]))
        elif kind == 1:
            l = {"lot": len(lots) + 1, "d": p["d"], "qty": p["qty"], "cost_usd": p["qty"] * p["price"] + (p.get("fees") or 0.0),
                 "changes": [(d, p["qty"])], "sales": []}
            lots.append(l)
            open_.append(l)
        else:
            left, each = p["qty"], p["price"] - (p.get("fees") or 0.0) / p["qty"]
            while left > EPS and open_:
                l = open_[0]
                q = min(l["qty"], left)
                l["qty"] -= q
                left -= q
                l["sales"].append((d, q, q * each))
                if l["qty"] <= 1e-7:
                    l["qty"] = 0.0
                    open_.pop(0)
                l["changes"].append((d, l["qty"]))
    return lots


def schedule_fa(cy: int, trades: list[dict], splits: dict[str, list[dict]], closes: dict[str, dict[str, float]],
                divs: dict[str, list[dict]], hist: dict, names_of: dict[str, str] | None = None) -> dict:
    """Table A3 for a calendar year: one row per purchase lot held at any time from 1 January to 31 December, with the
    initial value (its cost, at the rate on the purchase day), the peak (the highest of shares × that day's close ×
    that day's rate), the closing value on 31 December, the dividends credited and the sale proceeds in the year.
    `closes` is each stock's daily close in today's (split-adjusted) shares; `divs` each stock's dividends: {d,
    amount} for the user's whole holding (from their own file), shared by the lots held that day, or {d, per_share}
    in today's shares (from the stock's history)."""
    start, end = f"{cy}-01-01", f"{cy}-12-31"
    rows, missing_prices, missing_rates = [], set(), 0
    for sym in sorted({t["sym"] for t in trades}):
        sp = sorted(splits.get(sym) or [], key=lambda s: s.get("date", ""))
        lots = replay([t for t in trades if t["sym"] == sym], sp, end)
        px = closes.get(sym) or {}
        days = [k for k in sorted(px) if start <= k <= end]
        for lot in lots:
            ch = lot["changes"]
            held = _qty_on(ch, f"{cy - 1}-12-31") > 1e-7 or any(start <= d <= end for d, _ in ch)
            if not held:
                continue
            init = fx.rate_on(hist, lot["d"])
            peak = peak_day = None
            for k in days:
                q = _qty_on(ch, k)
                rt = fx.rate_on(hist, k) if q > 1e-7 else None
                if rt:
                    v = q * _after_factor(sp, k) * px[k] * rt["rate"]
                    if peak is None or v > peak:
                        peak, peak_day = v, k
            q_end = _qty_on(ch, end)
            end_rate = fx.rate_on(hist, end)
            if q_end <= 1e-7:
                closing = 0.0
            elif days and end_rate:
                closing = q_end * _after_factor(sp, days[-1]) * px[days[-1]] * end_rate["rate"]
            else:
                closing = None
            if closing is None or (peak is None and q_end > 1e-7):
                missing_prices.add(sym)
            income = 0.0
            for dv in divs.get(sym) or []:
                q = _qty_on(ch, dv["d"]) if start <= dv["d"] <= end else 0.0
                if q <= 1e-7:
                    continue
                rt = fx.rate_on(hist, dv["d"])
                if not rt:
                    missing_rates += 1
                    continue
                if "per_share" in dv:
                    income += q * _after_factor(sp, dv["d"]) * dv["per_share"] * rt["rate"]
                else:
                    whole = sum(_qty_on(x["changes"], dv["d"]) for x in lots)
                    income += dv["amount"] * q / whole * rt["rate"] if whole > 0 else 0.0
            sold = [(d, q, usd) for d, q, usd in lot["sales"] if start <= d <= end]
            proceeds = 0.0
            for d, _, usd in sold:
                rt = fx.rate_on(hist, d)
                if rt:
                    proceeds += usd * rt["rate"]
                else:
                    missing_rates += 1
            if init is None:
                missing_rates += 1
            rows.append({"symbol": sym, "name": (names_of or {}).get(sym) or sym, "lot": lot["lot"], "acquired": lot["d"],
                         "country": COUNTRY, "nature": "Company", "interest": "Direct",
                         "initial_usd": round(lot["cost_usd"], 2), "initial_rate": init,
                         "initial": round(lot["cost_usd"] * init["rate"], 2) if init else None,
                         "peak": round(peak, 2) if peak is not None else None, "peak_day": peak_day,
                         "closing": round(closing, 2) if closing is not None else None, "closing_qty": round(q_end, 6),
                         "closing_rate": end_rate if q_end > 1e-7 else None,
                         "income": round(income, 2), "proceeds": round(proceeds, 2) if sold else None})
    tot = lambda k: round(sum(r[k] or 0.0 for r in rows), 2)
    return {"cy": cy, "fy": cy, "label": f"Calendar year {cy} (1 Jan to 31 Dec {cy}), reported in the return for {fy_label(cy)}",
            "rows": rows, "totals": {k: tot(k) for k in ("initial", "peak", "closing", "income", "proceeds")},
            "missing_prices": sorted(missing_prices), "missing_rates": missing_rates,
            "fallback": any((r["initial_rate"] or {}).get("fallback") for r in rows)}
