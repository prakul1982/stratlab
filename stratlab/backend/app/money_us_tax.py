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

from . import db, holdings_file as hf, money_fx as fx, tax_due
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
    "side": hf.TRADE_COLUMNS["side"] | {"activity", "activitytype", "buysellflag", "transcode", "transactioncode", "trancode",
                                        "orderside", "tradeside", "tradeaction", "buysellcode"},     # Robinhood: "Trans Code"
    "symbol": {"symbol", "ticker", "stocksymbol", "stock", "instrument", "security", "securitysymbol", "scrip"},
    "name": {"name", "companyname", "securityname", "description", "stockname"},
    "qty": hf.TRADE_COLUMNS["qty"] | {"shares", "units", "noofshares", "numberofshares"},
    "price": hf.TRADE_COLUMNS["price"] | {"priceusd", "tradepriceusd", "fillprice", "avgfillprice", "costpershare"},
    "fees": {"fees", "fee", "commission", "commissions", "charges", "brokerage", "commfee", "ibcommission", "totalfees", "feesusd",
             "feescomm", "feesandcomm", "feescommissions", "feesandcommissions", "commissionsfees", "commissionandfees"},    # Schwab: "Fees & Comm"
    "value": hf.TRADE_COLUMNS["value"] | {"amountusd", "proceeds", "netamount"},
}
# MO-1: a realised-gains tax report (Vested's yearly one, other Indian US-stock apps' similar ones): one line per lot sold,
# with the day it was acquired and the day it was sold, instead of a list of trades
GAINS = {
    "symbol": COLUMNS["symbol"],
    "qty": {"quantitysold", "quantity", "qty", "sharessold", "unitssold", "soldquantity", "qtysold", "noofshares", "numberofshares",
            "shares", "units"},
    "bought": {"dateacquired", "acquired", "acquireddate", "dateofacquisition", "acquisitiondate", "purchasedate", "dateofpurchase",
               "purchaseddate", "datepurchased", "buydate", "buyingdate", "datebought", "bought"},
    "bprice": {"buyingpriceusd", "buyingprice", "buypriceusd", "buyprice", "purchasepriceusd", "purchaseprice", "acquisitionpriceusd",
               "acquisitionprice", "costpershare", "costpersharesusd", "purchasepricepershare"},
    "sold": {"datesold", "sold", "solddate", "saledate", "dateofsale", "selldate", "sellingdate", "dateofsell"},
    "sprice": {"sellingpriceusd", "sellingprice", "sellpriceusd", "sellprice", "salepriceusd", "saleprice", "salespriceusd",
               "salepricepershare"},
}
# a lot's whole sale proceeds and cost, when the report has them: its prices are rounded to the cent, these aren't, so the
# gains come out as the report's own summary has them (Vested's 2025 report: $4.43 apart over 132 lots read from the prices)
GAINS_TOTALS = {"proceeds": {"proceedsusd", "proceeds", "saleproceedsusd", "saleproceeds", "salevalueusd", "salevalue"},
                "cost": {"costbasisusd", "costbasis", "totalcostusd", "totalcost", "purchasevalueusd", "purchasevalue"}}
# the workbooks Vested (and others) give next to the tax report: schedules already worked out, not trades
READY_MADE = [("Schedule FA", re.compile(r"(?i)schedule[\s_-]*fa(?![a-z])")), ("Schedule FSI", re.compile(r"(?i)schedule[\s_-]*fsi(?![a-z])")),
              ("Schedule TR", re.compile(r"(?i)schedule[\s_-]*tr(?![a-z])")), ("Form 67", re.compile(r"(?i)form[\s_-]*67(?!\d)"))]
GAINS_NOTE = ("This is a realised-gains report: it has the lots you sold, not the shares you still hold. Schedule FA needs "
              "everything held in the calendar year, so the shares still held are missing from it until you add their purchases "
              "(or upload your broker's full transaction or activity statement).")
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
    # DH-030: the due dates come from the one table with the CBDT's extensions (tax_due.py), not a fixed "31 October"
    "Schedule FA is filed with the return, by its due date. " + tax_due.return_dates(2025) + " A belated or revised "
    "return can add it.",
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
    """How a US broker's file writes its dates: "mdy", month first, the US way (03/05/2025 is 5 March), unless a date
    in the column can only be read day first (24/03/2025, an Indian app's export): then "dmy"."""
    for v in values:
        m = re.match(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", v or "")
        if m and int(m.group(1)) > 12:
            return "dmy"
    return "mdy"


def date_order(values: list[str], broker: str | None = None) -> tuple[str, str | None]:
    """(order, note) for a column of US dates. Month first unless a date can only be read day first (_dates). When every
    such date reads either way (03/05/2025), an Indian broker's export (`broker`, from its columns or its name: it writes
    the Indian way, US lines too) is read day first; any other file month first. The note says which was taken."""
    order = _dates(values)
    split = [m for m in (re.match(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", v or "") for v in values) if m]
    if order == "dmy" or not split or any(int(m.group(2)) > 12 for m in split):
        return order, None
    if broker:
        return "dmy", f"Dates like 03/05/2025 were read day first (3 May), as {broker} writes them."
    return order, "Dates like 03/05/2025 were read as month/day (5 March)."


def indian_export(rows: list[list[str]], head: int, filename: str = "") -> str | None:
    """The Indian broker whose export this is (by its column names, or its name above the table or in the file name),
    or None."""
    name = hf.trade_broker(rows[head], rows[:head], filename)
    return None if name == "CSV" else name


def _day(v: str, order: str) -> str | None:
    m = re.match(r"^\s*(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", v or "")
    if m and order == "mdy":
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            return date(hf._year(m.group(3)), mo, d).isoformat()
        except ValueError:
            return None
    return hf.day(v)


def _side_col(rows: list[list[str]], head: int, c: dict[str, int]) -> dict[str, int]:
    """The side column whose lines say buy or sell: a file can have another column under a side's name before it (an
    order "Type" of Market or Limit beside the "Side"), which would read every line as neither."""
    keys = [hf.key(x) for x in rows[head]]
    taken = {i for f, i in c.items() if f != "side"}
    options = [i for i, k in enumerate(keys) if k in COLUMNS["side"] and i not in taken]
    if len(options) < 2:
        return c
    data = [r for r in rows[head + 1:head + 1 + 500] if any(x.strip() for x in r)]

    def says(i):
        return sum(1 for r in data if i < len(r) and _side(r[i]))
    best = max(options, key=lambda i: (says(i), -i))
    return {**c, "side": best} if says(best) else c


def _head(rows: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    """(index, columns) of the table's column names: a date, the ticker, the quantity and the price or value."""
    for i, row in enumerate(rows[:hf.HEADER_SCAN]):
        c = _cols(row)
        if {"date", "symbol", "qty"} <= c.keys() and ("price" in c or "value" in c):
            return i, _side_col(rows, i, c)
    return None


def _gains_cols(row: list[str]) -> dict[str, int]:
    keys = [hf.key(c) for c in row]
    found: dict[str, int] = {}
    for field, names in (GAINS | GAINS_TOTALS).items():
        for i, k in enumerate(keys):
            if k in names and field not in found and i not in found.values():
                found[field] = i
    return found


def _gains_heads(rows: list[list[str]]) -> list[int]:
    """The rows that name a realised-gains table's columns (the ticker, the quantity sold, the day acquired and the day sold
    and a price for each): a report has one under each of its sections, anywhere down the sheet."""
    return [i for i, row in enumerate(rows) if GAINS.keys() <= _gains_cols(row).keys()]


def _ready_made(data: bytes, filename: str) -> str | None:
    """"Schedule FA", "Schedule FSI", "Schedule TR" or "Form 67" when the workbook is one of those ready-made tables (by the file
    name, the sheet names, then the title rows at the top), else None."""
    texts = [filename]
    try:
        for name, rows in hf.sheets(data, 30, whole=False):
            texts.append(name)
            texts += [c for r in rows[:12] for c in r if c.strip()]
    except hf.FileError:
        pass
    for text in texts:
        for label, rx in READY_MADE:
            if rx.search(text or ""):
                return label
    return None


def parse_upload(data: bytes, filename: str = "") -> dict:
    """US trades from a CSV or Excel file: the date, purchase or sale, the ticker, the quantity and the price in dollars
    (and optionally fees), or a realised-gains tax report (MO-1), whose lot lines are read as a purchase and a sale.
    {"rows", "problems", "month_first", "date_note", "note"}. Raises FileError when nothing can be read."""
    if not data:
        raise hf.FileError("That file is empty.")
    if len(data) > MAX_BYTES:
        raise hf.FileError(f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    if data[:5] == b"%PDF-":
        raise hf.FileError("PDFs can't be read: upload the Excel (.xlsx) or CSV version of the same report.")
    if data[:4] == b"PK\x03\x04":                      # a workbook: the sheet with the trades, read whole; the others only at the top
        tables = [rows for _, rows in hf.sheets(data, hf.MAX_ROWS, wanted=lambda rows: bool(_gains_heads(rows)) or _head(rows) is not None)][:1]
    else:
        tables = [hf.table(data, MAX_BYTES)]
    for rows in tables:
        heads = _gains_heads(rows)
        if heads:
            return _gains(rows, heads, indian_export(rows, heads[0], filename))
        got = _head(rows)
        if got:
            i, c = got
            return _rows(rows[i + 1:], c, i + 2, indian_export(rows, i, filename))
    ready = _ready_made(data, filename) if data[:4] == b"PK\x03\x04" else None
    if ready:
        raise hf.FileError(f"This is a ready-made {ready} table, not a list of trades. Upload the tax report workbook (the yearly one, "
                           "such as 2025.xlsx, with the Transaction History sheet) instead: StratLab works the schedules out from the trades.")
    raise hf.FileError("No US trades were found in that file. It needs columns for the date, the trade (purchase or sale), "
                       "the ticker, the quantity and the price in dollars.")


def _gains(rows: list[list[str]], heads: list[int], broker: str | None = None) -> dict:
    """A realised-gains report as trades: each lot line under a "… Gains (Losses)" heading becomes a purchase (the day it was
    acquired, at the buying price) and a sale (the day it was sold, at the selling price) of the same shares. A section ends at
    the first blank line or title line (so dividends, interest and the rest below are never read as trades); only the columns
    for the lot are read, whatever else the sheet holds."""
    lots: list[tuple[int, list[str], dict[str, int]]] = []
    for h in heads:
        c = _gains_cols(rows[h])
        for n in range(h + 1, len(rows)):
            r = rows[n]
            if sum(1 for x in r if x.strip()) < 2 or GAINS.keys() <= _gains_cols(r).keys():
                break
            lots.append((n + 1, r, c))

    def cell(r, c, f):
        i = c.get(f)
        return r[i].strip() if i is not None and i < len(r) else ""
    order, note = date_order([cell(r, c, f) for _, r, c in lots for f in ("bought", "sold")], broker)
    out, problems = [], []
    for n, r, c in lots:
        sym = re.sub(r"[^A-Z0-9.\-]", "", cell(r, c, "symbol").upper()).replace(".", "-")[:10]
        qty, bp, sp = (_money(cell(r, c, f)) for f in ("qty", "bprice", "sprice"))
        qty = abs(qty) if qty is not None else None
        if qty:                     # each price from the lot's own proceeds and cost where the report has them (GAINS_TOTALS)
            whole_s, whole_b = _money(cell(r, c, "proceeds")), _money(cell(r, c, "cost"))
            sp = abs(whole_s) / qty if whole_s else sp
            bp = abs(whole_b) / qty if whole_b else bp
        bd, sd = _day(cell(r, c, "bought"), order), _day(cell(r, c, "sold"), order)
        if re.match(r"(?i)total", cell(r, c, "symbol")) or (not sym and not bd and not sd):      # a totals line
            continue
        text = " · ".join(x for x in (cell(r, c, "symbol"), cell(r, c, "qty"), cell(r, c, "bought"), cell(r, c, "sold")) if x)[:80]
        why = ("No ticker" if not sym else "No date" if not bd or not sd else "Sold before it was acquired" if sd < bd
               else "No quantity" if not qty or qty > MAX_QTY
               else "No price" if bp is None or sp is None or min(bp, sp) < 0 or max(bp, sp) > MAX_PRICE else None)
        if why:
            problems.append({"line": n, "text": text, "reason": why})
            continue
        if len(out) + 2 > MAX_TRADES:
            raise hf.too_many(MAX_TRADES // 2)
        for d, side, price in ((bd, "B", bp), (sd, "S", sp)):
            out.append({"d": d, "side": side, "sym": sym, "qty": round(qty, 6), "price": round(price, 6), "fees": 0.0, "name": "", "src": "file"})
    if not out:
        raise hf.FileError("No US trades could be read from that file: " + (problems[0]["reason"].lower() if problems else "it has no lot lines") + ".")
    return {"rows": out, "problems": problems[:100], "month_first": order == "mdy", "date_note": note, "note": GAINS_NOTE}


def _rows(rows: list[list[str]], c: dict[str, int], first_line: int, broker: str | None = None) -> dict:
    def cell(r, f):
        i = c.get(f)
        return r[i].strip() if i is not None and i < len(r) else ""
    order, note = date_order([cell(r, "date") for r in rows], broker)
    if "side" not in c and not any((_money(cell(r, "qty")) or 0) < 0 for r in rows):
        raise hf.FileError("That file doesn't say which lines are purchases and which are sales: it has no column for it "
                           "(Action, Type, Side or Trans Code, say) and no negative quantities. Add one and upload it again.")
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
        if len(out) >= MAX_TRADES:
            raise hf.too_many(MAX_TRADES)
        out.append({"d": d, "side": side, "sym": sym, "qty": round(qty, 6), "price": round(price, 6), "fees": round(min(fees, MAX_PRICE), 4),
                    "name": cell(r, "name")[:60], "src": "file"})
    if not out:
        raise hf.FileError("No US trades could be read from that file: " + (problems[0]["reason"].lower() if problems else "it has no lines") + ".")
    return {"rows": out, "problems": problems[:100], "month_first": order == "mdy", "date_note": note, "note": None}


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
    {sym: shares sold with no purchase}, "short_sales": [{sym, d, qty}] (the same, sale by sale)}. `lot` numbers each
    purchase, so Schedule FA can follow it. `upto` stops after that day."""
    by: dict[str, list[dict]] = {}
    for t in trades:
        if upto is None or t["d"] <= upto:
            by.setdefault(t["sym"], []).append(t)
    out = {"realised": [], "open": [], "short": {}, "short_sales": []}
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
                out["short_sales"].append({"sym": sym, "d": d, "qty": left})
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
        tax_usd = r["tds"] if r.get("tds") is not None else r["amount"] * US_WITHHOLDING      # 0 withheld stays 0
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
            if closing is None or peak is None:     # a lot sold in the year needs its peak too
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
