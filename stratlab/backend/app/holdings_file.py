"""Read a holdings export from the user's broker: CSV, Excel (.xlsx) or the HTML tables some brokers save as .xls.

Zerodha (Console and Kite), Groww, Upstox, Angel One, ICICI Direct and HDFC Securities are told apart by their
column names and by the broker's name in the lines above the table. Any other file works too when it has a column
for the stock (symbol, ISIN or name) and one for the quantity, with the average price optional. A file is untrusted:
its size, rows and cells are capped, and anything unreadable becomes a plain message, never a crash.

For the tax report it also reads tradebooks and tax P&L files, and the ZIP of tax P&L files a broker gives, with
the same care: capped, never unpacked to disk, and anything it doesn't cover left out with the reason."""
import csv
import io
import math
import re
import zipfile
from html.parser import HTMLParser
from xml.parsers import expat

MAX_BYTES = 2 * 1024 * 1024        # a holdings file is a few kilobytes; this is far more than a big portfolio needs
MAX_ROWS = 5000
MAX_COLS = 60
MAX_XML = 20 * 1024 * 1024         # one sheet inside an .xlsx, unpacked (a zip bomb stops here)
MAX_NODES = 400_000                # elements in one sheet: a big portfolio has a few thousand (each costs server time)
NODES_A_ROW = 80                   # the element cap grows with the row cap: a tradebook's rows are allowed more
MAX_SHEETS = 20                    # sheets read from one workbook (a tax P&L workbook has ten)
HEADER_SCAN = 60                   # the column names are within the first rows, after the broker's account lines

# column names, lower case with everything but letters and digits removed ("Avg. cost" -> "avgcost")
COLUMNS = {
    "isin": {"isin", "isincode", "isinno", "isinnumber"},
    "symbol": {"symbol", "tradingsymbol", "instrument", "stocksymbol", "scrip", "scripcode", "scripsymbol", "ticker",
               "nsesymbol", "nsecode", "stockcode", "securitycode", "scripid", "bsecode", "tradingsymbolnse"},
    "name": {"stockname", "companyname", "scripname", "scriptname", "securityname", "security", "name", "company",
             "stock", "instrumentname", "securitydescription", "description", "shortname"},
    "qty": {"quantity", "qty", "totalquantity", "totalqty", "netqty", "netquantity", "holdingquantity", "holdingqty",
            "freeqty", "availableqty", "currentqty", "noofshares", "shares", "balanceqty", "quantityavailable", "units"},
    "avg": {"averageprice", "avgprice", "avgcost", "averagecost", "averagecostprice", "averagebuyprice", "avgbuyprice",
            "buyavg", "buyaverage", "buyavgprice", "buyprice", "purchaseprice", "costprice", "avgrate", "averagerate",
            "avgtradingprice", "avgcostprice", "averagepurchaseprice", "buyavgrate", "avgbuyrate"},
    "exchange": {"exchange", "exch", "exchg"},
}
# Zerodha Console splits the quantity: shares pledged or not yet settled are held too, so they count
EXTRA_QTY = {"quantitydiscrepant", "quantitypledgedmargin", "quantitypledgedloan"}

# (broker, column names that only its export has together); checked in order
BROKERS = [
    ("Zerodha Console", {"quantityavailable", "averageprice"}),
    ("Zerodha Kite", {"instrument", "avgcost"}),
    ("Groww", {"stockname", "averagebuyprice"}),
    ("ICICI Direct", {"isincode", "averagecostprice"}),
    ("HDFC Securities", {"securityname", "unrealisedgainloss"}),
    ("Angel One", {"buyavgprice"}),
    ("Upstox", {"investedvalue", "overallpl"}),
]
# the broker's name in the lines above the table (or the file name) settles it
BRAND = [("zerodha", "Zerodha"), ("groww", "Groww"), ("upstox", "Upstox"), ("angel", "Angel One"),
         ("icici", "ICICI Direct"), ("hdfc", "HDFC Securities")]
ISIN = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")


class FileError(ValueError):
    """A file we can't use, with a message the user can act on."""


def key(header) -> str:
    return re.sub(r"[^a-z0-9]", "", str(header or "").lower())


def number(v) -> float | None:
    """A quantity or price as the broker wrote it: commas, ₹, Rs and brackets for negatives are fine."""
    s = str(v or "").strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"(?i)rs\.?|inr|₹|[,\s()]", "", s)
    if s in ("", "-", "--", "NA", "na"):
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    if not math.isfinite(x):
        return None
    return -x if neg else x


# ---------- reading the table ----------
def _col(ref: str) -> int:
    """Column number (0-based) from a cell reference like "AB12"."""
    n = 0
    for ch in re.match(r"[A-Z]*", ref or "").group(0):
        n = n * 26 + ord(ch) - 64
    return max(0, n - 1)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class _Stop(Exception):
    """Enough read: a handler ends the stream early."""


def _too_large():
    return FileError("That spreadsheet is too large to read.")


def _stream(zf: zipfile.ZipFile, name: str, start=None, end=None, text=None, nodes: int = MAX_NODES):
    """Read one XML file in the workbook as a stream of start, end and text events, element and attribute names
    without their namespaces. Nothing is kept but what the handlers keep, so millions of empty elements cost
    nothing; the unpacked size is capped (a zip bomb stops there); and a document type declaration is refused, so
    no entity is ever expanded or fetched. A handler raises _Stop to end early. KeyError when the file is missing."""
    info = zf.getinfo(name)
    if info.file_size > MAX_XML:
        raise _too_large()
    p = expat.ParserCreate(namespace_separator="}")

    def refuse(*_):
        raise FileError("That spreadsheet has parts we don't read. Open it and save it again as .xlsx or CSV.")
    p.StartDoctypeDeclHandler = p.EntityDeclHandler = refuse
    seen = [0]

    def on_start(tag, attrs):
        seen[0] += 1
        if seen[0] > nodes:
            raise _too_large()
        if start:
            start(_local(tag), {_local(k): v for k, v in attrs.items()})
    p.StartElementHandler = on_start
    if end:
        p.EndElementHandler = lambda tag: end(_local(tag))
    if text:
        p.CharacterDataHandler = text
    size = 0
    try:
        with zf.open(info) as f:
            while chunk := f.read(1 << 16):
                size += len(chunk)
                if size > MAX_XML:
                    raise _too_large()
                p.Parse(chunk, False)
        p.Parse(b"", True)
    except _Stop:
        pass


def _first_sheet(zf: zipfile.ZipFile) -> str:
    names = set(zf.namelist())
    try:                                   # the workbook's first sheet, through its relationships file
        found: dict = {}

        def sheet(tag, attrs):
            if tag == "sheet":
                found["rid"] = attrs.get("id")
                raise _Stop

        def rel(tag, attrs):
            if tag == "Relationship" and attrs.get("Id") == found.get("rid"):
                found["target"] = attrs.get("Target", "")
                raise _Stop
        _stream(zf, "xl/workbook.xml", start=sheet)
        _stream(zf, "xl/_rels/workbook.xml.rels", start=rel)
        target = found.get("target") or ""
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if target and path in names:
            return path
    except (KeyError, expat.ExpatError):
        pass
    sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    if not sheets:
        raise FileError("That Excel file has no sheets we can read.")
    return sheets[0]


def _shared(zf: zipfile.ZipFile, limit: int = MAX_ROWS) -> list[str]:
    """The workbook's shared strings (each cell's text when the cell points at one), up to what a sheet can use."""
    out: list[str] = []
    cur: dict = {"si": None, "t": False}

    def start(tag, attrs):
        if tag == "si":
            cur["si"] = []
        elif tag == "t":
            cur["t"] = True

    def end(tag):
        if tag == "t":
            cur["t"] = False
        elif tag == "si" and cur["si"] is not None:
            out.append("".join(cur["si"]))
            cur["si"] = None
            if len(out) >= limit * MAX_COLS:
                raise _Stop

    def text(data):
        if cur["t"] and cur["si"] is not None:
            cur["si"].append(data)
    if "xl/sharedStrings.xml" in zf.namelist():
        _stream(zf, "xl/sharedStrings.xml", start, end, text, nodes=max(MAX_NODES, limit * NODES_A_ROW))
    return out


def _sheet_list(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """(name, path) of each sheet in the workbook, in order, through the workbook's relationships file."""
    names, rels, out = [], {}, []

    def sheet(tag, attrs):
        if tag == "sheet" and len(names) < MAX_SHEETS:
            names.append((attrs.get("name") or "", attrs.get("id")))

    def rel(tag, attrs):
        if tag == "Relationship" and len(rels) < 500:
            rels[attrs.get("Id")] = attrs.get("Target", "")
    try:
        _stream(zf, "xl/workbook.xml", start=sheet)
        _stream(zf, "xl/_rels/workbook.xml.rels", start=rel)
    except (KeyError, expat.ExpatError):
        return []
    have = set(zf.namelist())
    for name, rid in names:
        target = rels.get(rid) or ""
        path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        if target and path in have:
            out.append((name[:80], path))
    return out


def _xlsx(data: bytes, limit: int = MAX_ROWS, sheet: str | None = None) -> list[list[str]]:
    """The rows of the workbook's first sheet, or of the sheet at `sheet` (its path inside the file)."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise FileError("That file looks like Excel but couldn't be opened. Save it again as .xlsx or CSV.") from None
    shared = _shared(zf, limit)
    rows: list[list[str]] = []
    st: dict = {"cells": None, "n": 0, "cell": None, "in": None}

    def start(tag, attrs):
        if tag == "row":
            st.update(cells={}, n=0)
        elif tag == "c" and st["cells"] is not None:
            ref = attrs.get("r")
            st["cell"] = {"col": _col(ref) if ref else st["n"], "kind": attrs.get("t"), "v": [], "t": [], "got_v": False}
            st["n"] += 1
        elif tag in ("v", "t") and st["cell"] is not None and not (tag == "v" and st["cell"]["got_v"]):
            st["in"] = tag

    def end(tag):
        c = st["cell"]
        if tag in ("v", "t"):
            if tag == "v" and c is not None and st["in"] == "v":
                c["got_v"] = True          # the first value only
            st["in"] = None
        elif tag == "c" and c is not None:
            st["cell"] = None
            if c["col"] >= MAX_COLS:
                return
            if c["kind"] == "inlineStr":
                value = "".join(c["t"])
            else:
                value = "".join(c["v"])
                if c["kind"] == "s":
                    try:
                        value = shared[int(value)]
                    except (ValueError, IndexError):
                        value = ""
            st["cells"][c["col"]] = value
        elif tag == "row" and st["cells"] is not None:
            cells = st["cells"]
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
            st["cells"] = None
            if len(rows) >= limit:
                raise _Stop

    def text(data):
        if st["in"] and st["cell"] is not None:
            st["cell"][st["in"]].append(data)
    _stream(zf, sheet or _first_sheet(zf), start, end, text, nodes=max(MAX_NODES, limit * NODES_A_ROW))
    return rows


def sheets(data: bytes, limit: int = MAX_ROWS) -> list[tuple[str, list[list[str]]]]:
    """(name, rows) for every sheet in a workbook, each read with the same caps as one sheet."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise FileError("That file looks like Excel but couldn't be opened. Save it again as .xlsx or CSV.") from None
    return [(name, _xlsx(data, limit, path)) for name, path in _sheet_list(zf)]


class _Tables(HTMLParser):
    """Rows of the HTML tables some brokers save with an .xls name."""

    def __init__(self, limit: int = MAX_ROWS):
        super().__init__()
        self.limit = limit
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr" and len(self.rows) < self.limit:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None and self.cell is not None:
            if len(self.row) < MAX_COLS:
                self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _text(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _csv(text: str, limit: int = MAX_ROWS) -> list[list[str]]:
    head = text[:4000]
    delim = max((",", "\t", ";", "|"), key=lambda d: head.count(d))
    rows = []
    try:
        for r in csv.reader(io.StringIO(text), delimiter=delim):
            rows.append([c.strip() for c in r[:MAX_COLS]])
            if len(rows) >= limit:
                break
    except csv.Error:
        raise FileError("That CSV file is broken (a quote or a very long cell). Export it again from your broker.") from None
    return rows


def table(data: bytes, max_bytes: int = MAX_BYTES, limit: int = MAX_ROWS,
          too_big: str = "A holdings export is much smaller; check it's the right file.") -> list[list[str]]:
    """The rows of the file's first table, as text: at most `limit` rows from a file of at most `max_bytes`."""
    if not data:
        raise FileError("That file is empty.")
    if len(data) > max_bytes:
        raise FileError(f"That file is larger than {max_bytes // (1024 * 1024)} MB. {too_big}")
    if data[:4] == b"PK\x03\x04":
        return _xlsx(data, limit)
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise FileError("That is an old-style Excel file (.xls). Open it and save it as .xlsx or CSV, then upload that.")
    if data[:5] == b"%PDF-":
        raise FileError("That is a PDF. Download the holdings as Excel or CSV from your broker instead.")
    text = _text(data)
    if "\x00" in text[:4096]:
        raise FileError("That doesn't look like a CSV or Excel file.")
    if re.match(r"\s*<", text) and re.search(r"<t[dr][\s>]", text[:200000], re.I):
        p = _Tables(limit)
        p.feed(text)
        p.close()
        return p.rows
    return _csv(text, limit)


# ---------- finding the holdings in it ----------
def _columns(row: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for i, cell in enumerate(row):
        k = key(cell)
        for field, names in COLUMNS.items():
            if k in names and field not in found:
                found[field] = i
    return found


def _header(rows: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    for i, row in enumerate(rows[:HEADER_SCAN]):
        cols = _columns(row)
        if "qty" in cols and cols.keys() & {"isin", "symbol", "name"}:
            return i, cols
    return None


def broker(header: list[str], before: list[list[str]], filename: str = "") -> str:
    """Which broker's export this is, or "CSV" for a file of our generic shape. Only a label: every file is read the
    same way, by its column names."""
    keys = {key(c) for c in header}
    for name, needs in BROKERS:
        if needs <= keys:
            return name
    words = " ".join([filename] + [" ".join(r) for r in before]).lower()
    for word, name in BRAND:
        if word in words:
            return name
    return "CSV"


def _bare(rows: list[list[str]]) -> bool:
    """A list without column names: symbol, quantity and maybe the average price on each line."""
    full = [r for r in rows if any(c.strip() for c in r)]
    return bool(full) and all(1 < len([c for c in r if c.strip()]) <= 3 and number(r[1]) is not None for r in full[:20])


def _cell(row: list[str], i: int | None) -> str:
    return row[i].strip() if i is not None and i < len(row) else ""


def parse(data: bytes, filename: str = "") -> dict:
    """{"broker", "rows": [{line, symbol, isin, name, exchange, qty, avg}], "problems": [{line, text, reason}]}.
    Raises FileError when there's no holdings table in the file at all."""
    try:
        rows = table(data)
    except FileError:
        raise
    except Exception:                       # a damaged file of any kind: one plain answer
        raise FileError("We couldn't read that file. Export the holdings again as CSV or Excel and upload that.") from None
    found = _header(rows)
    if found:
        at, cols = found
        name = broker(rows[at], rows[:at], filename)
        extra = [i for i, c in enumerate(rows[at]) if key(c) in EXTRA_QTY]
        body = rows[at + 1:]
        first = at + 2
    elif _bare(rows):
        cols, name, extra, body, first = {"symbol": 0, "qty": 1, "avg": 2}, "CSV", [], rows, 1
    else:
        raise FileError("We couldn't find the holdings in that file. It needs a column for the stock (symbol, ISIN or "
                        "name) and one for the quantity. If your broker isn't listed, make a CSV with the columns "
                        "Symbol, Quantity, Average price.")
    out, problems = [], []
    for n, row in enumerate(body, start=first):
        sym, isin, nm = _cell(row, cols.get("symbol")), _cell(row, cols.get("isin")).upper(), _cell(row, cols.get("name"))
        text = " · ".join(c for c in (sym, isin, nm) if c)[:80]
        if not text or re.match(r"(?i)^(total|grand total|sub ?total)\b", sym or nm or ""):
            continue                        # blank lines, totals and notes under the table
        qty = number(_cell(row, cols.get("qty")))
        if qty is not None:
            qty += sum(number(_cell(row, i)) or 0 for i in extra)
        if qty is None:
            if any(number(c) is not None for c in row):
                problems.append({"line": n, "text": text, "reason": "No quantity on this line."})
            continue                        # a heading or a note between the rows
        if qty <= 0:
            continue                        # sold, or only listed for its history
        avg = number(_cell(row, cols.get("avg")))
        out.append({"line": n, "symbol": sym.upper(), "isin": isin if ISIN.match(isin) else "", "name": nm,
                    "exchange": _cell(row, cols.get("exchange")).upper()[:6], "qty": qty,
                    "avg": avg if avg and avg > 0 else None, "text": text})
        if len(out) >= MAX_ROWS:
            break
    if not out and not problems:
        raise FileError("That file has the right columns but no holdings in it.")
    return {"broker": name, "rows": out, "problems": problems}


# ---------- tradebooks and tax P&L exports, for the tax report ----------
TRADE_COLUMNS = {
    "date": {"tradedate", "date", "transactiondate", "executiondate", "executiondateandtime", "tradedatetime", "orderdate",
             "datetime", "tradedon", "dateoftransaction"},
    "time": {"tradetime", "orderexecutiontime", "executiontime", "time", "ordertime", "tradetimestamp"},
    "side": {"tradetype", "type", "side", "buysell", "bs", "action", "transactiontype", "buyorsell", "trantype",
             "buysellindicator", "transaction"},
    "qty": COLUMNS["qty"] | {"tradeqty", "tradedquantity", "quantitytraded", "filledqty", "tradedqty", "executedqty"},
    "price": {"price", "tradeprice", "rate", "transactionprice", "tradedprice", "averageprice", "avgprice", "executionprice",
              "marketrate", "grossrate", "pricepershare", "executedprice"},
    "value": {"value", "tradevalue", "amount", "totalvalue", "grossamount", "transactionvalue", "grossvalue"},
    "trade_id": {"tradeid", "tradeno", "tradenum", "tradenumber", "exchangetradeid", "tradereference"},
    "segment": {"segment", "instrumenttype", "series", "assetclass"},
    "status": {"orderstatus", "status"},
}
# what a sold lot shows in a tax P&L export: one line per sale, with its buy
PNL_COLUMNS = {
    "buy_date": {"buydate", "entrydate", "purchasedate", "dateofpurchase", "acquisitiondate", "dateofacquisition", "buytradedate"},
    "sell_date": {"selldate", "exitdate", "saledate", "dateofsale", "transferdate", "dateoftransfer", "selltradedate"},
    "buy_price": {"buyprice", "buyrate", "purchaseprice", "buyavg", "buyaverage", "entryprice", "avgbuyprice", "purchaserate", "costprice"},
    "sell_price": {"sellprice", "sellrate", "saleprice", "exitprice", "avgsellprice", "salerate"},
    "buy_value": {"buyvalue", "purchasevalue", "costofacquisition", "buyamount", "purchaseamount", "entryvalue", "totalbuyvalue"},
    "sell_value": {"sellvalue", "salevalue", "salesconsideration", "sellamount", "exitvalue", "fullvalueofconsideration", "totalsellvalue"},
    "fmv": {"fairmarketvalue", "fmv", "fmvason31jan2018", "fmv31jan2018", "fairmarketvalueason31012018", "fmvpershare"},
}
# charges a broker lists per trade: brokerage and the like are part of the cost (or come off the sale); STT isn't
CHARGE_TOTAL = {"totalcharges", "charges", "totalbrokerageandcharges", "brokerageandcharges", "taxesandcharges"}
CHARGE_PARTS = {"brokerage", "totalbrokerage", "brokeragegst", "brokerageservicetax", "brokerageinclofservicetax",
                "brokerageinclgst", "transactioncharges", "exchangetransactioncharges", "exchangecharges", "turnovercharges",
                "transactionandsebiturnovercharges", "sebicharges", "sebifees", "sebiturnoverfees", "stampduty", "gst", "cgst",
                "sgst", "igst", "servicetax", "ipft", "othercharges", "clearingcharges"}
STT = {"stt", "securitiestransactiontax", "sttctt"}
TRADE_BROKERS = [
    ("Zerodha Console", {"tradedate", "tradetype", "tradeid"}),
    ("Zerodha", {"entrydate", "exitdate", "taxableprofit"}),          # the tax P&L's tradewise exits
    ("Groww", {"executiondateandtime", "exchangeorderid"}),
    ("Upstox", {"tradenum", "side"}),
    ("ICICI Direct", {"action", "orderref"}),
    ("HDFC Securities", {"securityname", "rate", "tradeno"}),
    ("Angel One", {"buysell", "tradeno", "tradeprice"}),
]
NOT_EQUITY = re.compile(r"(?i)^(f ?& ?o|nfo|bfo|fo|fut|futures?|opt|options?|ce|pe|cds|currency|mcx|com|commodity|derivatives?|mf|mutual ?funds?)$")
DONE = re.compile(r"(?i)^(executed|complete|completed|traded|filled|success|successful|done)$")
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
MAX_TRADES = 20000


def day(v) -> str | None:
    """A trade date as the broker wrote it, as YYYY-MM-DD: 2024-07-22, 22-07-2024, 22/07/24, 22-Jul-2024,
    Jul 22, 2024, with or without a time after it, or an Excel date number. Day first when it's ambiguous."""
    from datetime import date as _date, timedelta
    s = str(v or "").strip()
    if not s:
        return None
    try:
        if re.fullmatch(r"\d{5}(\.\d+)?", s) and 20000 < float(s) < 80000:          # Excel's day count
            return (_date(1899, 12, 30) + timedelta(days=int(float(s)))).isoformat()
        m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", s)
        if m:
            y, mo, d = map(int, m.groups())
            return _date(y, mo, d).isoformat()
        m = re.match(r"(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2,4})(?!\d)", s)
        if m:
            d, mo, y = map(int, m.groups())
            if mo > 12 and d <= 12:
                d, mo = mo, d
            return _date(y + 2000 if y < 100 else y, mo, d).isoformat()
        m = re.match(r"(\d{1,2})[-/ ]?([A-Za-z]{3})[A-Za-z]*[-/ ,]*(\d{2,4})(?!\d)", s)
        if m and m.group(2).lower() in MONTHS:
            y = int(m.group(3))
            return _date(y + 2000 if y < 100 else y, MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
        m = re.match(r"([A-Za-z]{3})[A-Za-z]*[-/ ]+(\d{1,2}),?[-/ ]+(\d{4})(?!\d)", s)
        if m and m.group(1).lower() in MONTHS:
            return _date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
    except (ValueError, OverflowError):
        return None
    return None


def side(v) -> str | None:
    """"B" for a buy, "S" for a sale, however the broker words it."""
    s = re.sub(r"[^a-z]", "", str(v or "").lower())
    if s in ("b", "bought", "purchase", "purchased") or s.startswith("buy"):
        return "B"
    if s in ("s", "sold", "sale") or s.startswith("sell"):
        return "S"
    return None


def _trade_columns(row: list[str]) -> dict[str, int]:
    found = _columns(row)
    for i, cell in enumerate(row):
        k = key(cell)
        for field, names in {**TRADE_COLUMNS, **PNL_COLUMNS}.items():
            if k in names and field not in found:
                found[field] = i
    return found


def _trade_header(rows: list[list[str]]) -> tuple[int, dict[str, int], str] | None:
    """(row, columns, "trades" or "pnl") for the first row that names a tradebook's or a tax P&L's columns."""
    for i, row in enumerate(rows[:HEADER_SCAN]):
        cols = _trade_columns(row)
        if not cols.keys() & {"isin", "symbol", "name"} or "qty" not in cols:
            continue
        if {"buy_date", "sell_date"} <= cols.keys() and cols.keys() & {"buy_price", "buy_value"} and cols.keys() & {"sell_price", "sell_value"}:
            return i, cols, "pnl"
        if "date" in cols and "side" in cols and cols.keys() & {"price", "value"}:
            return i, cols, "trades"
    return None


def trade_broker(header: list[str], before: list[list[str]], filename: str = "") -> str:
    """Which broker's tradebook this is (only a label), or "CSV"."""
    keys = {key(c) for c in header}
    for name, needs in TRADE_BROKERS:
        if needs <= keys:
            return name
    words = " ".join([filename] + [" ".join(r) for r in before]).lower()
    for word, name in BRAND:
        if word in words:
            return name
    return "CSV"


def _charges(row: list[str], header: list[str]) -> float:
    """Brokerage and the other charges on one line, without STT (which the tax law doesn't let you deduct)."""
    keys = [key(c) for c in header]
    total = [i for i, k in enumerate(keys) if k in CHARGE_TOTAL]
    stt = sum(abs(number(_cell(row, i)) or 0) for i, k in enumerate(keys) if k in STT)
    if total:
        return max(0.0, abs(number(_cell(row, total[0])) or 0) - stt)
    return sum(abs(number(_cell(row, i)) or 0) for i, k in enumerate(keys) if k in CHARGE_PARTS)


def _fmv(v: float | None, qty: float, buy_price: float) -> float | None:
    """The 31 Jan 2018 value a share, from a column that may hold it a share or for the whole line: whichever is
    nearer the buy price."""
    if not v or v <= 0:
        return None
    if qty <= 1 or not buy_price or buy_price <= 0:
        return v
    each, whole = v, v / qty
    return each if abs(math.log(each / buy_price)) <= abs(math.log(whole / buy_price)) else whole


def _read_trades(rows: list[list[str]], filename: str = "") -> dict:
    """The trades in one table: {"broker", "kind", "trades", "problems", "gross", "taxable"}: what the tax P&L lines add
    up to before charges, sales less purchases, and the same with the 31 Jan 2018 value as the cost where it's higher
    (brokers' summaries show one or the other). Raises FileError when there are none."""
    found = _trade_header(rows)
    if not found:
        if summary(rows):
            raise FileError("That is the summary page of a tax P&L: totals by company, without the buy and sale dates. "
                            "Upload the whole ZIP file your broker gives you, or the \"Tradewise Exits\" CSV files in it.")
        if _header(rows):
            raise FileError("That looks like a holdings file, which has no trade dates. For the tax report, upload your "
                            "tradebook (every buy and sale) or your broker's tax P&L instead.")
        raise FileError("We couldn't find any trades in that file. It needs columns for the date, the stock (symbol or "
                        "ISIN), buy or sell, the quantity and the price. If your broker isn't listed, make a CSV with "
                        "the columns Date, Symbol, Type (buy or sell), Quantity, Price.")
    at, cols, kind = found
    header = rows[at]
    name = trade_broker(header, rows[:at], filename)
    out, problems, gross, taxable = [], [], 0.0, 0.0
    for n, row in enumerate(rows[at + 1:], start=at + 2):
        sym, isin, nm = _cell(row, cols.get("symbol")), _cell(row, cols.get("isin")).upper(), _cell(row, cols.get("name"))
        text = " · ".join(c for c in (sym, isin, nm) if c)[:80]
        if not text or re.match(r"(?i)^(total|grand total|sub ?total)\b", sym or nm or ""):
            continue
        seg = _cell(row, cols.get("segment"))
        if (seg and NOT_EQUITY.match(seg)) or (not ISIN.match(isin) and DERIVATIVE.search(sym.upper())):
            problems.append({"line": n, "text": text, "reason": "Futures, options and other non-equity trades are left out of a tradebook (F&O is "
                             "business income, read from the F&O tax P&L file instead)."})
            continue
        status = _cell(row, cols.get("status"))
        if status and not DONE.match(status):
            continue                         # a cancelled or rejected order: nothing traded
        qty = number(_cell(row, cols.get("qty")))
        qty = abs(qty) if qty else qty       # some brokers write a sale's quantity as negative
        if not qty:
            if any(number(c) is not None for c in row):
                problems.append({"line": n, "text": text, "reason": "No quantity on this line."})
            continue
        base = {"isin": isin if ISIN.match(isin) else "", "symbol": sym.upper()[:40], "name": nm[:80],
                "exchange": _cell(row, cols.get("exchange")).upper()[:6], "text": text, "line": n}
        charges = round(_charges(row, header), 2)
        if kind == "pnl":
            bd, sd = day(_cell(row, cols.get("buy_date"))), day(_cell(row, cols.get("sell_date")))
            bp = number(_cell(row, cols.get("buy_price")))
            bp = bp if bp is not None else (number(_cell(row, cols.get("buy_value"))) or 0) / qty
            sp = number(_cell(row, cols.get("sell_price")))
            sp = sp if sp is not None else (number(_cell(row, cols.get("sell_value"))) or 0) / qty
            if not bd or not sd:
                problems.append({"line": n, "text": text, "reason": "The buy or sale date couldn't be read."})
                continue
            if sd < bd or bp < 0 or sp <= 0:
                problems.append({"line": n, "text": text, "reason": "The dates or prices on this line don't add up."})
                continue
            fmv = _fmv(number(_cell(row, cols.get("fmv"))), qty, bp) if bd <= "2018-01-31" else None
            gross += qty * (sp - bp)
            taxable += qty * (sp - max(bp, min(fmv, sp))) if fmv else qty * (sp - bp)
            pid = f"pnl:{bd}:{sd}:{qty:g}:{bp:.4f}:{sp:.4f}"
            # a sale and its own buy, which the tax report keeps together (the ids end :b and :s); prices to 6 places,
            # so a line adds up to what the broker shows
            out.append({**base, "d": bd, "t": "", "side": "B", "qty": qty, "price": round(bp, 6), "charges": 0.0, "tid": pid + ":b", "fmv": fmv, "src": "pnl"})
            out.append({**base, "d": sd, "t": "", "side": "S", "qty": qty, "price": round(sp, 6), "charges": charges, "tid": pid + ":s", "fmv": None, "src": "pnl"})
        else:
            d, sd_ = day(_cell(row, cols.get("date"))), side(_cell(row, cols.get("side")))
            if not d:
                problems.append({"line": n, "text": text, "reason": "The trade date couldn't be read."})
                continue
            if not sd_:
                problems.append({"line": n, "text": text, "reason": "It doesn't say whether this was a buy or a sale."})
                continue
            price = number(_cell(row, cols.get("price")))
            if not price and cols.get("value") is not None:
                v = number(_cell(row, cols.get("value")))
                price = abs(v) / qty if v else None
            if not price or price <= 0:
                problems.append({"line": n, "text": text, "reason": "No price on this line."})
                continue
            tm = _cell(row, cols.get("time"))
            if not tm:
                hit = re.search(r"\d{1,2}:\d{2}(:\d{2})?(\s*[AP]M)?", _cell(row, cols.get("date")), re.I)
                tm = hit.group(0) if hit else ""
            fmv = _fmv(number(_cell(row, cols.get("fmv"))), qty, price) if sd_ == "B" and d <= "2018-01-31" else None
            out.append({**base, "d": d, "t": tm[:20], "side": sd_, "qty": qty, "price": round(price, 4), "charges": charges,
                        "tid": _cell(row, cols.get("trade_id"))[:40], "fmv": fmv, "src": "trades"})
        if len(out) >= MAX_TRADES:
            break
    if not out:
        if problems:
            raise FileError(f"No equity trades could be read from that file. Line {problems[0]['line']}: {problems[0]['reason']}")
        raise FileError("That file has the right columns but no trades in it.")
    return {"broker": name, "kind": kind, "trades": out, "problems": problems, "gross": gross, "taxable": taxable}


def parse_trades(data: bytes, filename: str = "") -> dict:
    """A tradebook (each buy and sale), a tax P&L export (each sale with its buy), or the ZIP of tax P&L files a
    broker gives, from any of the brokers or a plain CSV with date, symbol or ISIN, buy/sell, quantity and price. An
    F&O, commodity or currency P&L file is read as business income: totals per year, not trades.

    {"broker", "kind": "trades"|"pnl"|"business", "trades": [{line, d, t, side, qty, price, charges, isin, symbol, name,
    exchange, tid, fmv, src, text}], "problems": [{line, text, reason}], "skipped": [{name, reason}], "check": [{section,
    file, summary, ok}], "files": [{name, section, lines}], "business": [per segment and year, see _Business]}. Raises
    FileError when there are no trades and no F&O lines at all."""
    if data[:4] == b"PK\x03\x04" and not _is_xlsx(data):
        return parse_tax_zip(data, filename)
    k = _skipped_kind(filename) if re.search(r"(?i)tradewise|taxpnl|tax[\s_-]*p\s*&?\s*l", filename or "") else None
    if k:
        raise FileError(f"That is the {k[0]} file of a tax P&L: {k[1]}, so the tax report leaves it out. "
                        "Upload the equity, F&O, commodity or currency files instead.")
    seg = business_kind(filename)
    if seg:
        return parse_business(data, filename, seg)
    try:
        rows = table(data, TAX_MAX_BYTES, MAX_TRADE_ROWS, TOO_BIG)
    except FileError:
        raise
    except Exception:
        raise FileError("We couldn't read that file. Export the tradebook again as CSV or Excel and upload that.") from None
    if looks_derivative(rows):
        return parse_business(data, filename, None)
    got = _read_trades(rows, filename)
    if NON_EQUITY_FILE.search(filename or ""):
        got = _units_only(got)
    return {**got, "problems": got["problems"][:500], "skipped": [], "check": [], "files": [], "business": []}


# ---------- a broker's ZIP of tax P&L files ----------
TAX_MAX_BYTES = 10 * 1024 * 1024        # one tradebook, tax P&L or ZIP of them (a busy year's ZIP is a few MB)
TAX_MAX_REQUEST = 25 * 1024 * 1024      # one upload request; the page sends each picked file on its own
TOO_BIG = "Split the tradebook by year and upload each one."
MAX_TRADE_ROWS = 20000                  # lines in one file: a tax P&L for a very busy year has a few thousand
ZIP_MAX_UNPACKED = 40 * 1024 * 1024     # everything read from one ZIP, unpacked (a zip bomb stops here)
ZIP_MAX_ENTRIES = 200                   # a broker's ZIP has a dozen, with the Mac's __MACOSX copies
TABLE_EXT = re.compile(r"(?i)\.(csv|txt|tsv|xlsx|xls)$")
ARCHIVE_EXT = re.compile(r"(?i)\.(zip|jar|7z|rar|gz|tgz|bz2|xz|tar)$")
# (file name, what it is, why it's left out): non-equity and mutual funds sit beside the equity and F&O files
TAX_SKIP = [
    (re.compile(r"(?i)mutual[\s_-]*funds?"), "Mutual funds", "mutual funds aren't covered yet"),
]
# the equity files read, by name, and which line of the summary sheet each one adds up to
TAX_EQUITY = [(re.compile(r"(?i)non[\s_-]*equity"), "Non-equity", "non_equity"),      # ETFs, gold bonds (instrument_kinds)
              (re.compile(r"(?i)intraday|speculative"), "Equity intraday", "intraday"),
              (re.compile(r"(?i)short[\s_-]*term"), "Equity short term", "short"),
              (re.compile(r"(?i)long[\s_-]*term"), "Equity long term", "long")]
SUMMARY = {"intradayspeculativeprofit": "intraday", "intradayprofit": "intraday", "speculativeprofit": "intraday",
           "shorttermprofit": "short", "longtermprofit": "long", "nonequityprofit": "non_equity"}
SECTION_NAMES = {"intraday": "Equity intraday", "short": "Equity short term", "long": "Equity long term", "non_equity": "Non-equity"}
NON_EQUITY_FILE = re.compile(r"(?i)non[\s_-]*equity")
NOT_COVERED = "Bonds, debentures and other non-equity securities aren't covered yet (ETFs, REITs, InvITs and gold bonds are)."


def _units_only(got: dict) -> dict:
    """A non-equity file's trades without the ones that are neither an ETF, a REIT or InvIT nor a gold bond (a
    company's bond or debenture), which are listed as left out. The ones kept carry their kind."""
    from .instrument_kinds import classify
    keep, dropped, gross, taxable = [], {}, 0.0, 0.0
    for t in got["trades"]:
        code = classify(t.get("symbol"), t.get("isin"), t.get("name"))
        if code == "stock":
            dropped.setdefault(t["line"], t)
            continue
        keep.append({**t, "kind": code})
    for t in dropped.values():
        got["problems"].append({"line": t["line"], "text": t["text"], "reason": NOT_COVERED})
    if dropped and got.get("kind") == "pnl":             # the totals checked against the summary: the kept lines only
        pairs: dict[str, dict] = {}
        for t in keep:
            pairs.setdefault(t["tid"][:-2], {})[t["side"]] = t
        for p in pairs.values():
            if "B" in p and "S" in p:
                gross += p["S"]["qty"] * (p["S"]["price"] - p["B"]["price"])
        got["gross"] = got["taxable"] = gross
    if not keep:
        raise FileError(f"Nothing in that file is covered yet. {NOT_COVERED}")
    return {**got, "trades": keep}


def _skipped_kind(filename: str) -> tuple[str, str] | None:
    """(what, why) when a tax P&L file's name says it holds trades the tax report leaves out."""
    for rx, what, why in TAX_SKIP:
        if rx.search(filename or ""):
            return what, why
    return None


def _is_xlsx(data: bytes) -> bool:
    """An Excel workbook (itself a ZIP inside) rather than a ZIP of files."""
    try:
        names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    except Exception:
        return True                          # not a ZIP we can open at all: the spreadsheet reader says so plainly
    return "xl/workbook.xml" in names or ("[Content_Types].xml" in names and any(n.startswith("xl/") for n in names))


def summary(rows: list[list[str]]) -> dict[str, float]:
    """The realised totals on a tax P&L's summary sheet ("Short Term profit" and the like), by kind."""
    out: dict[str, float] = {}
    for row in rows[:HEADER_SCAN * 2]:
        for i, cell in enumerate(row):
            kind = SUMMARY.get(key(cell))
            if kind and kind not in out:
                v = next((x for x in (number(c) for c in row[i + 1:]) if x is not None), None)
                if v is not None:
                    out[kind] = v
    return out


def _safe_name(name: str) -> bool:
    """A plain path inside the ZIP: not absolute, no "..", no drive letter, no control characters."""
    if not name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name) or re.search(r"[\x00-\x1f]", name):
        return False
    return ".." not in re.split(r"[\\/]", name)


def _junk(name: str) -> bool:
    """A folder, the Mac's __MACOSX copies and other hidden files: nothing to read or mention."""
    parts = [p for p in re.split(r"[\\/]", name) if p]
    return (name.endswith(("/", "\\")) or not parts or parts[0] == "__MACOSX" or any(p.startswith(".") for p in parts)
            or parts[-1].lower() in ("thumbs.db", "desktop.ini"))


def _base(name: str) -> str:
    return re.split(r"[\\/]", name.rstrip("/\\"))[-1][:120]


def _unpack(zf: zipfile.ZipFile, info: zipfile.ZipInfo, budget: list[int], cap: int | None = None) -> bytes:
    """One file from the ZIP, read in pieces and stopped as soon as it passes the size caps, whatever its header
    claims (a zip bomb gets no further than that)."""
    cap = cap or TAX_MAX_BYTES
    out = bytearray()
    with zf.open(info) as f:
        while chunk := f.read(1 << 16):
            out += chunk
            if len(out) > cap:
                raise FileError(f"{_base(info.filename)} is larger than {cap // (1024 * 1024)} MB unpacked. {TOO_BIG}")
            if len(out) > budget[0]:
                raise FileError(f"That ZIP unpacks to more than {ZIP_MAX_UNPACKED // (1024 * 1024)} MB. Upload the equity files from it on their own.")
    budget[0] -= len(out)
    return bytes(out)


def parse_tax_zip(data: bytes, filename: str = "") -> dict:
    """The ZIP a broker gives for its tax P&L: a CSV per segment and a summary workbook. The equity files are read
    (short term, long term and intraday) as trades; F&O, commodity and currency as business income, streamed and added
    up per year (the F&O file runs to many MB); non-equity and mutual funds are left out by name, unread, and listed
    with the reason. The summary's totals are checked against what was read.

    The ZIP is untrusted: its size, number of files and what they unpack to are capped, paths that climb out of it
    and ZIPs inside it are refused, and nothing is written to disk."""
    if len(data) > TAX_MAX_BYTES:
        raise FileError(f"That file is larger than {TAX_MAX_BYTES // (1024 * 1024)} MB. {TOO_BIG}")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        infos = zf.infolist()
    except Exception:
        raise FileError("That ZIP file couldn't be opened. Download it again from your broker.") from None
    if len(infos) > ZIP_MAX_ENTRIES:
        raise FileError(f"That ZIP has more than {ZIP_MAX_ENTRIES} files in it. Upload the equity files from it on their own.")
    for info in infos:                       # every name is checked before anything is unpacked
        if not _safe_name(info.filename):
            raise FileError("That ZIP has file paths we don't accept. Unzip it and upload the CSV files in it instead.")
        if not _junk(info.filename) and ARCHIVE_EXT.search(info.filename):
            raise FileError("That ZIP has another ZIP inside it. Unzip it and upload the files in it instead.")
    budget = [ZIP_MAX_UNPACKED]
    trades, problems, skipped, read, sums, brokers = [], [], [], [], {}, []
    sheet: dict[str, float] = {}
    biz, biz_sheet, biz_files = _Business(), {}, set()
    try:
        for info in infos:
            if _junk(info.filename):
                continue
            base = _base(info.filename)
            if not TABLE_EXT.search(base):
                skipped.append({"name": base, "reason": "Not a CSV or Excel file."})
                continue
            k = _skipped_kind(base)
            if k:                            # left out by its name, never unpacked
                skipped.append({"name": base, "reason": f"{k[0]}: {k[1]}."})
                continue
            if info.flag_bits & 0x1:
                raise FileError("That ZIP is password-protected. Unzip it on your computer and upload the CSV files in it.")
            seg = business_kind(base)
            if seg:                          # F&O, commodity, currency: streamed and added up, never held whole
                label = SEGMENT_NAMES[seg]
                try:
                    if re.search(r"(?i)\.(csv|txt|tsv)$", base):
                        with zf.open(info) as f:
                            capped = _Capped(f, base, FNO_MAX_BYTES, budget)
                            try:
                                n, probs = _biz_rows(_csv_stream(capped), base, seg, biz, label)
                            finally:
                                budget[0] -= capped.seen
                    else:
                        n, probs = _biz_rows(business_rows(_unpack(zf, info, budget, FNO_MAX_BYTES)), base, seg, biz, label)
                except FileError as e:
                    skipped.append({"name": base, "reason": str(e)})
                    continue
                read.append({"name": base, "section": label, "lines": n})
                biz_files.add(seg)
                problems += probs
                continue
            raw = _unpack(zf, info, budget)
            if raw[:4] == b"PK\x03\x04" and not _is_xlsx(raw):
                raise FileError("That ZIP has another ZIP inside it. Unzip it and upload the files in it instead.")
            section = next(((label, kind) for rx, label, kind in TAX_EQUITY if rx.search(base)), None)
            try:
                rows = table(raw, TAX_MAX_BYTES, MAX_TRADE_ROWS, TOO_BIG)
            except FileError as e:
                skipped.append({"name": base, "reason": str(e)})
                continue
            totals = summary(rows) if not section else {}
            if not section and _is_xlsx(raw) and raw[:4] == b"PK\x03\x04":
                for name, srows in sheets(raw):      # the workbook's F&O, commodity and currency sheets
                    s_seg = business_kind(name)
                    if s_seg and (got_ := business_summary(srows)) and s_seg not in biz_sheet:
                        biz_sheet[s_seg] = got_
            if not section and (totals or biz_sheet):
                sheet.update({k_: v for k_, v in totals.items() if k_ not in sheet})
                continue                     # the summary workbook: its totals check the files read
            try:
                got = _read_trades(rows, base)
                if section and section[1] == "non_equity":
                    got = _units_only(got)
            except FileError as e:
                skipped.append({"name": base, "reason": str(e)})
                continue
            label = section[0] if section else base
            sales = sum(1 for t in got["trades"] if t["side"] == "S") if got["kind"] == "pnl" else len(got["trades"])
            read.append({"name": base, "section": label, "lines": sales})
            brokers.append(got["broker"])
            if section and got["kind"] == "pnl":
                was = sums.get(section[1], (0.0, 0.0))
                sums[section[1]] = (was[0] + got["gross"], was[1] + got["taxable"])
            trades += got["trades"]
            problems += [{**p, "text": f"{label} · {p['text']}"[:120]} for p in got["problems"]]
            if len(trades) >= MAX_TRADES:
                break
    except FileError:
        raise
    except Exception:                        # a damaged entry of any kind: one plain answer
        raise FileError("That ZIP file is damaged. Download it again from your broker.") from None
    business = biz.result()
    if not trades and not business:
        left = "; ".join(f"{s['name']} ({s['reason'].rstrip('.')})" for s in skipped[:6])
        raise FileError("No equity, F&O, commodity or currency trades were found in that ZIP." + (f" Left out: {left}." if left else ""))
    check = []
    for kind in ("short", "long", "intraday", "non_equity") if sheet else ():
        both, theirs = sums.get(kind), sheet.get(kind)
        if both is None and (theirs is None or abs(theirs) < 0.005):
            continue                         # nothing of that kind, on either side
        near = [v for v in both or () if theirs is not None and abs(v - theirs) <= max(1.0, abs(theirs) * 1e-6)]
        mine, ok = (near[0] if near else both[0] if both else None), bool(near)
        check.append({"section": SECTION_NAMES[kind], "file": None if mine is None else round(mine, 2), "summary": theirs, "ok": ok})
    check += business_check(business, biz_sheet, biz_files)
    zerodha = any(re.match(r"(?i)(tradewise exits|taxpnl)", _base(i.filename)) for i in infos)
    broker = "Zerodha" if zerodha else next((b for b in brokers if b != "CSV"), "CSV")
    kind = "business" if not trades else "pnl" if all(t["src"] == "pnl" for t in trades) else "trades"
    return {"broker": broker, "kind": kind, "trades": trades[:MAX_TRADES], "problems": problems[:500], "skipped": skipped[:50],
            "check": check, "files": read, "business": business}


def business_check(business: list[dict], sheet: dict[str, dict], files: set[str]) -> list[dict]:
    """The F&O, commodity and currency totals read, against the summary sheet's: the result before charges, and the
    turnover netted per contract (the way the summary adds it up)."""
    out = []
    for seg in ("fno", "commodity", "currency"):
        theirs = sheet.get(seg) or {}
        rows = [b for b in business if b["seg"] == seg]
        if not rows and not any(abs(v) >= 0.005 for v in theirs.values()):
            continue
        name = SEGMENT_NAMES[seg]
        for what, mine_key in (("pnl", "pnl"), ("turnover", "turnover_contract")):
            if what not in theirs:
                continue
            mine = round(sum(b[mine_key] for b in rows), 2) if seg in files else None
            ok = mine is not None and abs(mine - theirs[what]) <= max(1.0, abs(theirs[what]) * 1e-6)
            out.append({"section": name if what == "pnl" else f"{name} turnover", "file": mine, "summary": round(theirs[what], 2),
                        "ok": ok, "what": what})
    return out


# ---------- F&O, commodity and currency: business income, read as totals ----------
FNO_MAX_BYTES = 20 * 1024 * 1024        # one F&O, commodity or currency file, unpacked (a busy year's F&O runs to ~12 MB)
FNO_MAX_ROWS = 300_000                  # lines in one such file (a busy year has tens of thousands)
MAX_CONTRACTS = 200_000                 # contracts netted at once, for the turnover the broker's summary shows
TOP_UNDERLYINGS = 25                    # per segment and year: the biggest by result, the rest as one line
# (file name, segment): which tax P&L files are business income, read as totals, not trades
BUSINESS = [(re.compile(r"(?i)f\s*&\s*o|(^|[^a-z])fno([^a-z]|$)|futures|options|derivative"), "fno"),
            (re.compile(r"(?i)commodit"), "commodity"),
            (re.compile(r"(?i)currenc"), "currency")]
SEGMENT_NAMES = {"fno": "F&O", "commodity": "Commodity", "currency": "Currency"}
BIZ_COLUMNS = {
    "symbol": {"contract", "contractname", "instrumentname", "scripname", "contractdescription"},
    "date": PNL_COLUMNS["sell_date"] | {"closedate", "closingdate", "squareoffdate", "exitdatetime", "selldatetime"},
    "pnl": {"profit", "pnl", "realisedpnl", "realizedpnl", "realisedprofit", "realizedprofit", "netpnl", "grosspnl",
            "profitloss", "realisedprofitloss", "realizedprofitloss", "bookedpnl", "bookedprofitloss", "realisedgainloss",
            "realizedgainloss", "profitorloss"},
    "buy_value": PNL_COLUMNS["buy_value"],
    "sell_value": PNL_COLUMNS["sell_value"],
}
BIZ_TAX = STT | {"ctt", "commoditiestransactiontax", "commoditytransactiontax"}
DERIVATIVE = re.compile(r"\d.*(FUT|CE|PE)$")
COMMODITIES = re.compile(r"^(CRUDEOIL|NATURALGAS|NATGAS|GOLD|SILVER|COPPER|ZINC|LEAD|ALUMINI|ALUMINIUM|NICKEL|COTTON|"
                         r"MENTHAOIL|CARDAMOM|KAPAS|CASTORSEED|GUARSEED|JEERA|TURMERIC|DHANIYA|STEEL)")
CURRENCIES = re.compile(r"^(USDINR|EURINR|GBPINR|JPYINR|EURUSD|GBPUSD|USDJPY)")
SUMMARY_BIZ = {"optionsrealizedprofit": "pnl", "futuresrealizedprofit": "pnl", "optionsrealisedprofit": "pnl",
               "futuresrealisedprofit": "pnl", "optionsturnover": "turnover", "futuresturnover": "turnover"}
NOT_SUPPORTED = ("F&O, commodity and currency results are read only from Zerodha's tax P&L for now (the \"Tradewise "
                 "Exits\" files or the ZIP), or a P&L file of the same shape: a column for the contract, the exit date "
                 "and the profit.")


def business_kind(filename: str) -> str | None:
    """"fno", "commodity" or "currency" when a tax P&L file's name says it holds that segment."""
    for rx, seg in BUSINESS:
        if rx.search(filename or ""):
            return seg
    return None


def underlying(symbol: str) -> str:
    """What a contract is on: NIFTY25APR23000CE -> NIFTY, CRUDEOILM25MAYFUT -> CRUDEOILM."""
    s = str(symbol or "").strip().upper()
    m = re.match(r"([A-Z&\-]+?)(?=\d)", s)
    return (m.group(1) if m else s)[:20] or "?"


def _segment_of(symbol: str) -> str:
    u = underlying(symbol)
    if CURRENCIES.match(u):
        return "currency"
    if COMMODITIES.match(u):
        return "commodity"
    return "fno"


def _biz_columns(row: list[str]) -> dict[str, int]:
    found = {f: i for f, i in _columns(row).items() if f in ("symbol", "name", "isin")}
    for i, cell in enumerate(row):
        k = key(cell)
        for field, names in BIZ_COLUMNS.items():
            if k in names and field not in found:
                found[field] = i
    return found


def _biz_header(row: list[str]) -> dict[str, int] | None:
    cols = _biz_columns(row)
    if "symbol" in cols and "date" in cols and ("pnl" in cols or {"buy_value", "sell_value"} <= cols.keys()):
        return cols
    return None


class _Business:
    """F&O, commodity and currency lines added up as they are read, per segment and financial year: the result,
    the turnover (the total of profits and losses, trade by trade, and netted per contract as brokers' summaries
    show it), the charges, and the biggest underlyings. No line is kept."""

    def __init__(self):
        self.years: dict[tuple, dict] = {}
        self.contracts: dict[tuple, float] = {}
        self.rows = 0

    def add(self, seg: str, d: str, symbol: str, pnl: float, charges: float, tax: float):
        y, m = int(d[:4]), int(d[5:7])
        fy = y if m >= 4 else y - 1
        cur = self.years.get((seg, fy))
        if cur is None:
            cur = self.years[(seg, fy)] = {"seg": seg, "fy": fy, "first": d, "last": d, "trades": 0, "pnl": 0.0, "turnover": 0.0,
                                           "charges": 0.0, "stt": 0.0, "options": {"pnl": 0.0, "turnover": 0.0, "trades": 0},
                                           "futures": {"pnl": 0.0, "turnover": 0.0, "trades": 0}, "by": {}}
        cur["first"], cur["last"] = min(cur["first"], d), max(cur["last"], d)
        cur["trades"] += 1
        cur["pnl"] += pnl
        cur["turnover"] += abs(pnl)
        cur["charges"] += charges
        cur["stt"] += tax
        kind = "options" if re.search(r"\d.*(CE|PE)$", symbol) else "futures"
        cur[kind]["pnl"] += pnl
        cur[kind]["turnover"] += abs(pnl)
        cur[kind]["trades"] += 1
        u = underlying(symbol)
        if u not in cur["by"] and len(cur["by"]) >= 5000:
            u = "Others"
        by = cur["by"].setdefault(u, {"pnl": 0.0, "turnover": 0.0, "trades": 0})
        by["pnl"] += pnl
        by["turnover"] += abs(pnl)
        by["trades"] += 1
        k = (seg, fy, symbol)
        if k in self.contracts or len(self.contracts) < MAX_CONTRACTS:
            self.contracts[k] = self.contracts.get(k, 0.0) + pnl
        self.rows += 1

    def result(self) -> list[dict]:
        nets: dict[tuple, float] = {}
        for (seg, fy, _), v in self.contracts.items():
            nets[(seg, fy)] = nets.get((seg, fy), 0.0) + abs(v)
        out = []
        for (seg, fy), cur in sorted(self.years.items()):
            by = sorted(cur["by"].items(), key=lambda kv: -abs(kv[1]["pnl"]))
            top, rest = by[:TOP_UNDERLYINGS], by[TOP_UNDERLYINGS:]
            lines = [{"u": u, "pnl": round(x["pnl"], 2), "turnover": round(x["turnover"], 2), "trades": x["trades"]} for u, x in top]
            if rest:
                lines.append({"u": "Others", "pnl": round(sum(x["pnl"] for _, x in rest), 2),
                              "turnover": round(sum(x["turnover"] for _, x in rest), 2), "trades": sum(x["trades"] for _, x in rest)})
            out.append({"seg": seg, "fy": fy, "first": cur["first"], "last": cur["last"], "trades": cur["trades"],
                        "pnl": round(cur["pnl"], 2), "turnover": round(cur["turnover"], 2),
                        "turnover_contract": round(nets.get((seg, fy), 0.0), 2), "charges": round(cur["charges"], 2),
                        "stt": round(cur["stt"], 2), "options": {k: round(v, 2) for k, v in cur["options"].items()},
                        "futures": {k: round(v, 2) for k, v in cur["futures"].items()}, "by": lines})
        return out


def _biz_rows(rows, filename: str, seg: str | None, acc: _Business, label: str) -> tuple[int, list[dict]]:
    """Add one table's lines to the running totals: (lines read, problems). `rows` is any iterator of rows, so a
    big CSV is read as it streams. Raises FileError when the table has no F&O columns."""
    it = iter(rows)
    head: list[list[str]] = []
    cols = None
    for row in it:
        head.append(row)
        cols = _biz_header(row)
        if cols or len(head) >= HEADER_SCAN:
            break
    if not cols:
        raise FileError(f"{label}: we couldn't find the columns. " + NOT_SUPPORTED)
    keys = [key(c) for c in head[-1]]
    total = next((i for i, k in enumerate(keys) if k in CHARGE_TOTAL), None)
    parts = [i for i, k in enumerate(keys) if k in CHARGE_PARTS]
    taxes = [i for i, k in enumerate(keys) if k in BIZ_TAX]
    n, problems, line = 0, [], len(head)
    for row in it:
        line += 1
        if line - len(head) > FNO_MAX_ROWS:
            raise FileError(f"{label} has more than {FNO_MAX_ROWS:,} lines. Upload it a quarter at a time.")
        sym = _cell(row, cols.get("symbol")).upper()
        if not sym or re.match(r"(?i)^(total|grand total|sub ?total)\b", sym):
            continue
        d = day(_cell(row, cols.get("date")))
        if not d:
            if any(number(c) is not None for c in row):
                problems.append({"line": line, "text": f"{label} · {sym[:40]}", "reason": "The exit date couldn't be read."})
            continue
        if "pnl" in cols:
            pnl = number(_cell(row, cols["pnl"]))
        else:
            b, s_ = number(_cell(row, cols["buy_value"])), number(_cell(row, cols["sell_value"]))
            pnl = None if b is None or s_ is None else s_ - b
        if pnl is None or abs(pnl) > 1e11:
            problems.append({"line": line, "text": f"{label} · {sym[:40]}", "reason": "No profit or loss on this line."})
            continue
        tax = min(sum(abs(number(_cell(row, i)) or 0) for i in taxes), 1e10)
        if total is not None:
            charges = max(abs(number(_cell(row, total)) or 0), tax)
        else:
            charges = sum(abs(number(_cell(row, i)) or 0) for i in parts) + tax
        acc.add(seg or _segment_of(sym), d, sym[:40], pnl, min(charges, 1e10), tax)
        n += 1
    return n, problems[:500]


class _Capped(io.RawIOBase):
    """A file inside the ZIP, read as it unpacks and stopped as soon as it passes the caps, whatever its header says."""

    def __init__(self, f, name: str, cap: int, budget: list[int]):
        self.f, self.name, self.cap, self.budget, self.seen = f, name, cap, budget, 0

    def readable(self):
        return True

    def readinto(self, b):
        n = self.f.readinto(b)
        self.seen += n or 0
        if self.seen > self.cap:
            raise FileError(f"{self.name} is larger than {self.cap // (1024 * 1024)} MB unpacked. Upload it a quarter at a time.")
        if self.seen > self.budget[0]:
            raise FileError(f"That ZIP unpacks to more than {ZIP_MAX_UNPACKED // (1024 * 1024)} MB. Upload the files from it on their own.")
        return n


def _csv_stream(raw):
    """The rows of a CSV read from a binary stream, a piece at a time."""
    text = io.TextIOWrapper(io.BufferedReader(raw, 1 << 16), encoding="utf-8-sig", errors="replace", newline="")
    head: list[str] = []
    for _ in range(HEADER_SCAN):
        ln = text.readline(20000)
        if not ln:
            break
        head.append(ln)
        if sum(map(len, head)) > 4000:
            break
    sample = "".join(head)
    if "\x00" in sample:
        raise FileError("That doesn't look like a CSV or Excel file.")
    delim = max((",", "\t", ";", "|"), key=lambda d: sample.count(d))

    def rows():
        import itertools
        try:
            for r in csv.reader(itertools.chain(head, text), delimiter=delim):
                yield [c.strip() for c in r[:MAX_COLS]]
        except csv.Error:
            raise FileError("That CSV file is broken (a quote or a very long cell). Export it again from your broker.") from None
    return rows()


def business_rows(data: bytes):
    """The rows of one F&O, commodity or currency file already in memory: a CSV streams, a workbook is read whole."""
    if not data:
        raise FileError("That file is empty.")
    if len(data) > FNO_MAX_BYTES:
        raise FileError(f"That file is larger than {FNO_MAX_BYTES // (1024 * 1024)} MB. Upload it a quarter at a time.")
    if (data[:4] == b"PK\x03\x04" or data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" or data[:5] == b"%PDF-"
            or re.match(rb"\s*<", data[:200])):
        return iter(table(data, FNO_MAX_BYTES, FNO_MAX_ROWS))
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return iter(_csv(_text(data), FNO_MAX_ROWS + HEADER_SCAN))
    return _csv_stream(io.BytesIO(data))


def looks_derivative(rows: list[list[str]]) -> bool:
    """A P&L table of futures and options: F&O columns, no ISIN, and contract names on most lines."""
    for i, row in enumerate(rows[:HEADER_SCAN]):
        cols = _biz_header(row)
        if not cols:
            continue
        if "isin" in cols:
            return False
        syms = [_cell(r, cols["symbol"]).upper() for r in rows[i + 1:i + 51] if _cell(r, cols["symbol"])]
        return bool(syms) and sum(1 for s in syms if DERIVATIVE.search(s)) >= max(1, len(syms) * 0.6)
    return False


def business_summary(rows: list[list[str]]) -> dict[str, float]:
    """The realised result and turnover on a tax P&L workbook's F&O, commodity or currency sheet."""
    out: dict[str, float] = {}
    for row in rows[:HEADER_SCAN]:
        for i, cell in enumerate(row):
            kind = SUMMARY_BIZ.get(key(cell))
            if kind:
                v = next((x for x in (number(c) for c in row[i + 1:]) if x is not None), None)
                if v is not None:
                    out[kind] = out.get(kind, 0.0) + v
                break
    return out


def parse_business(data: bytes, filename: str = "", seg: str | None = None) -> dict:
    """One F&O, commodity or currency P&L file on its own, as per-year totals."""
    acc = _Business()
    label = SEGMENT_NAMES.get(seg or "", "F&O")
    try:
        n, problems = _biz_rows(business_rows(data), filename, seg, acc, label)
    except FileError:
        raise
    except Exception:
        raise FileError("We couldn't read that file. " + NOT_SUPPORTED) from None
    if not n:
        raise FileError(f"No {label} lines could be read from that file. " + NOT_SUPPORTED)
    broker = "Zerodha" if re.match(r"(?i)tradewise exits", filename or "") else trade_broker([], [], filename)
    return {"broker": broker, "kind": "business", "trades": [], "problems": problems, "skipped": [], "check": [],
            "files": [{"name": _base(filename or "file"), "section": label, "lines": n}], "business": acc.result()}
