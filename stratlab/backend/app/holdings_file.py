"""Read a holdings export from the user's broker: CSV, Excel (.xlsx) or the HTML tables some brokers save as .xls.

Zerodha (Console and Kite), Groww, Upstox, Angel One, ICICI Direct and HDFC Securities are told apart by their
column names and by the broker's name in the lines above the table. Any other file works too when it has a column
for the stock (symbol, ISIN or name) and one for the quantity, with the average price optional. A file is untrusted:
its size, rows and cells are capped, and anything unreadable becomes a plain message, never a crash."""
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


def _stream(zf: zipfile.ZipFile, name: str, start=None, end=None, text=None):
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
        if seen[0] > MAX_NODES:
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


def _shared(zf: zipfile.ZipFile) -> list[str]:
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
            if len(out) >= MAX_ROWS * MAX_COLS:
                raise _Stop

    def text(data):
        if cur["t"] and cur["si"] is not None:
            cur["si"].append(data)
    if "xl/sharedStrings.xml" in zf.namelist():
        _stream(zf, "xl/sharedStrings.xml", start, end, text)
    return out


def _xlsx(data: bytes) -> list[list[str]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise FileError("That file looks like Excel but couldn't be opened. Save it again as .xlsx or CSV.") from None
    shared = _shared(zf)
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
            if len(rows) >= MAX_ROWS:
                raise _Stop

    def text(data):
        if st["in"] and st["cell"] is not None:
            st["cell"][st["in"]].append(data)
    _stream(zf, _first_sheet(zf), start, end, text)
    return rows


class _Tables(HTMLParser):
    """Rows of the HTML tables some brokers save with an .xls name."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr" and len(self.rows) < MAX_ROWS:
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


def _csv(text: str) -> list[list[str]]:
    head = text[:4000]
    delim = max((",", "\t", ";", "|"), key=lambda d: head.count(d))
    rows = []
    try:
        for r in csv.reader(io.StringIO(text), delimiter=delim):
            rows.append([c.strip() for c in r[:MAX_COLS]])
            if len(rows) >= MAX_ROWS:
                break
    except csv.Error:
        raise FileError("That CSV file is broken (a quote or a very long cell). Export it again from your broker.") from None
    return rows


def table(data: bytes) -> list[list[str]]:
    """The rows of the file's first table, as text."""
    if not data:
        raise FileError("That file is empty.")
    if len(data) > MAX_BYTES:
        raise FileError(f"That file is larger than {MAX_BYTES // (1024 * 1024)} MB. A holdings export is much smaller; check it's the right file.")
    if data[:4] == b"PK\x03\x04":
        return _xlsx(data)
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise FileError("That is an old-style Excel file (.xls). Open it and save it as .xlsx or CSV, then upload that.")
    if data[:5] == b"%PDF-":
        raise FileError("That is a PDF. Download the holdings as Excel or CSV from your broker instead.")
    text = _text(data)
    if "\x00" in text[:4096]:
        raise FileError("That doesn't look like a CSV or Excel file.")
    if re.match(r"\s*<", text) and re.search(r"<t[dr][\s>]", text[:200000], re.I):
        p = _Tables()
        p.feed(text)
        p.close()
        return p.rows
    return _csv(text)


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
