"""A minimal real Excel workbook (.xlsx) from rows of cells, laid out the way Excel saves one (shared strings, cell
references, a workbook and its relationships), so spreadsheet reading is tested without an Excel library.

    python -m tests.xlsxmaker      # rebuilds the broker sample files in tests/fixtures/holdings
"""
import io
import zipfile
from xml.sax.saxutils import escape

CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
      '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
      '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def _ref(row: int, col: int) -> str:
    s, c = "", col + 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return f"{s}{row + 1}"


def make_xlsx(rows: list[list], sheet: str = "Equity") -> bytes:
    """Text cells go in the shared strings, numbers stay numbers; None leaves a cell out, as Excel does."""
    shared: list[str] = []
    index: dict[str, int] = {}
    body = []
    for r, row in enumerate(rows):
        cells = []
        for c, v in enumerate(row):
            if v is None or v == "":
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                cells.append(f'<c r="{_ref(r, c)}"><v>{v}</v></c>')
            else:
                v = str(v)
                if v not in index:
                    index[v] = len(shared)
                    shared.append(v)
                cells.append(f'<c r="{_ref(r, c)}" t="s"><v>{index[v]}</v></c>')
        body.append(f'<row r="{r + 1}">{"".join(cells)}</row>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<workbook {NS}><sheets>'
                                      f'<sheet name="{escape(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                   '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet {NS}><sheetData>{"".join(body)}</sheetData></worksheet>')
        z.writestr("xl/sharedStrings.xml", f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst {NS} count="{len(shared)}" uniqueCount="{len(shared)}">'
                   + "".join(f"<si><t xml:space=\"preserve\">{escape(s)}</t></si>" for s in shared) + "</sst>")
    return out.getvalue()


# ---------- the broker sample files ----------
def zerodha_console() -> list[list]:
    """Console › Portfolio › Holdings › Download XLSX: account lines and a summary above the table, which starts in
    column B, with the quantity split into available, discrepant, long term and pledged."""
    return [[], [None, "Client ID", "AB1234"], [], [None, "Holdings Statement as on 2026-10-02"], [],
            [None, "Summary"], [None, "Invested Value", 412560.5], [None, "Present Value", 455210.75], [None, "Unrealized P&L", 42650.25],
            [None, "Unrealized P&L Pct.", 10.34], [],
            [None, "Equity"],
            [None, "Symbol", "ISIN", "Sector", "Quantity Available", "Quantity Discrepant", "Quantity Long Term",
             "Quantity Pledged (Margin)", "Quantity Pledged (Loan)", "Average Price", "Previous Closing Price", "Unrealized P&L", "Unrealized P&L Pct."],
            [None, "RELIANCE", "INE002A01018", "ENERGY", 40, 0, 40, 10, 0, 2410.35, 2902.1, 24587.5, 20.4],
            [None, "TCS", "INE467B01029", "IT", 12, 0, 12, 0, 0, 3520.0, 4120.55, 7206.6, 17.06],
            [None, "HDFCBANK", "INE040A01034", "FINANCIAL SERVICES", 55, 0, 30, 0, 0, 1498.2, 1702.4, 11231.0, 13.63],
            [None, "SLOWCO-BE", "INE999Z01015", "", 100, 0, 0, 0, 0, 41.25, 39.8, -145.0, -3.52],
            [None, "TINYCO", "INE111T01017", "", 250, 0, 250, 0, 0, 18.5, 22.0, 875.0, 18.92],
            [None, "NIFTYBEES", "INF204KB14I2", "ETF", 30, 0, 30, 0, 0, 230.1, 271.3, 1236.0, 17.9]]


def groww() -> list[list]:
    """Groww › Reports › Holdings statement (Excel): the name and client code above, then only the company's name
    and ISIN for each stock (no trading symbol)."""
    return [["Name", "Asha Kumar"], ["Unique Client Code", "1234567890"], [], ["Holdings statement as on 02-10-2026"], [],
            ["Stock Name", "ISIN", "Quantity", "Average buy price", "Buy value", "Closing price", "Closing value", "Unrealised P&L"],
            ["Infosys Limited", "INE009A01021", 25, 1452.6, 36315, 1890.2, 47255, 10940],
            ["ITC Limited", "INE154A01025", 200, 402.35, 80470, 470.1, 94020, 13550],
            ["Tata Steel Limited", "INE081A01020", 150, 128.4, 19260, 152.75, 22912.5, 3652.5],
            ["Tiny Co Limited", "INE111T01017", 50, 20, 1000, 22, 1100, 100],
            ["Some Unlisted Pvt Ltd", "INE000X01000", 10, 100, 1000, 0, 0, 0]]


def icici_direct() -> list[list]:
    """ICICI Direct › Portfolio › Stocks › Download: its own stock codes (RELIND, not RELIANCE), so the ISIN is what
    matches."""
    return [["Stock Symbol", "Company Name", "ISIN Code", "Qty", "Average Cost Price", "Current Market Price", "% Change over prev close",
             "Value At Cost", "Value At Market Price", "Realized Profit / Loss", "Unrealized Profit / Loss", "Unrealized Profit / Loss %"],
            ["RELIND", "RELIANCE INDUSTRIES LTD", "INE002A01018", "20", "2,388.10", "2,902.10", "0.45", "47,762.00", "58,042.00", "0.00", "10,280.00", "21.52"],
            ["INFTEC", "INFOSYS LTD", "INE009A01021", "10", "1,512.00", "1,890.20", "-0.30", "15,120.00", "18,902.00", "0.00", "3,782.00", "25.01"],
            ["STABAN", "STATE BANK OF INDIA", "INE062A01020", "80", "602.45", "815.30", "1.10", "48,196.00", "65,224.00", "1,250.00", "17,028.00", "35.33"],
            ["ICIBAN", "ICICI BANK LTD", "INE090A01021", "35", "905.00", "1,250.40", "0.20", "31,675.00", "43,764.00", "0.00", "12,089.00", "38.17"]]


def upstox() -> list[list]:
    return [["Scrip Name", "Symbol", "ISIN", "Exchange", "Quantity", "Avg. Price", "LTP", "Invested Value", "Current Value", "Overall P&L", "Day P&L"],
            ["Bharti Airtel Ltd", "BHARTIARTL", "INE397D01024", "NSE", "18", "1105.5", "1630.25", "19899", "29344.5", "9445.5", "120.6"],
            ["Larsen & Toubro Ltd", "LT", "INE018A01030", "NSE", "6", "3120", "3655.8", "18720", "21934.8", "3214.8", "-45"],
            ["Tiny Co Ltd", "TINYCO", "", "BSE", "40", "19.1", "22", "764", "880", "116", "4"]]


def angel_one() -> list[list]:
    return [["Angel One Ltd - Holding Report"], ["Client Code: S123456"], [],
            ["Script Name", "Symbol", "ISIN", "Exchange", "Total Qty", "Buy Avg Price", "LTP", "Buy Value", "Market Value", "Unrealised P&L"],
            ["ASIAN PAINTS LTD", "ASIANPAINT-EQ", "INE021A01026", "NSE", "8", "2890.00", "2455.10", "23120.00", "19640.80", "-3479.20"],
            ["ITC LTD", "ITC-EQ", "INE154A01025", "NSE", "100", "410.20", "470.10", "41020.00", "47010.00", "5990.00"],
            ["ITC LTD", "ITC", "INE154A01025", "BSE", "20", "395.00", "470.05", "7900.00", "9401.00", "1501.00"],
            ["Total", "", "", "", "", "", "", "72040.00", "76051.80", "4011.80"]]


def hdfc_securities_html() -> str:
    """HDFC Securities saves its "Excel" portfolio as an HTML table with an .xls name."""
    rows = [["Security Name", "ISIN", "Exchange", "Quantity", "Avg. Buy Price", "Buy Value", "Market Price", "Market Value", "Unrealised Gain/Loss"],
            ["TATA CONSULTANCY SERVICES LTD", "INE467B01029", "NSE", "5", "3,610.00", "18,050.00", "4,120.55", "20,602.75", "2,552.75"],
            ["HDFC BANK LTD", "INE040A01034", "NSE", "40", "1,550.00", "62,000.00", "1,702.40", "68,096.00", "6,096.00"],
            ["MUTUAL FUND UNITS XYZ", "INF000A01000", "", "12.5", "40.00", "500.00", "44.00", "550.00", "50.00"]]
    head = "<tr>" + "".join(f"<th>{escape(c)}</th>" for c in rows[0]) + "</tr>"
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
    return f"<html><head><meta charset='utf-8'></head><body><h3>HDFC securities - Equity Portfolio</h3><table border='1'>{head}\n{body}</table></body></html>"


def _csv(rows: list[list]) -> str:
    import csv
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    return out.getvalue()


KITE_CSV = ('"Instrument","Qty.","Avg. cost","LTP","Cur. val","P&L","Net chg.","Day chg."\r\n'
            '"SBIN",60,598.35,815.3,48918,13017,36.26,1.1\r\n'
            '"ICICIBANK",25,960.1,1250.4,31260,7257.5,30.24,0.2\r\n'
            '"WIPRO",45,402.05,301.6,13572,-4520.25,-24.98,-0.5\r\n'
            '"GOLDBEES",100,52.3,61.2,6120,890,17.02,0.1\r\n')
GENERIC_CSV = "symbol,quantity,average price\nRELIANCE,10,2500\nTCS,3,\n543210,100,18\nNOTASTOCK,5,10\n"


def write_fixtures():
    from pathlib import Path
    d = Path(__file__).parent / "fixtures" / "holdings"
    d.mkdir(parents=True, exist_ok=True)
    (d / "zerodha_console_holdings.xlsx").write_bytes(make_xlsx(zerodha_console()))
    (d / "zerodha_kite_holdings.csv").write_text(KITE_CSV)
    (d / "groww_holdings_statement.xlsx").write_bytes(make_xlsx(groww(), "Holdings"))
    (d / "icici_direct_portfolio.csv").write_text(_csv(icici_direct()))
    (d / "upstox_holdings.csv").write_text(_csv(upstox()))
    (d / "angel_one_holding_report.xlsx").write_bytes(make_xlsx(angel_one(), "Holdings"))
    (d / "hdfc_securities_portfolio.xls").write_text(hdfc_securities_html())
    (d / "generic.csv").write_text(GENERIC_CSV)


if __name__ == "__main__":
    write_fixtures()
