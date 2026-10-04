"""Sample tradebooks and tax P&L files, laid out the way each broker exports them, for the tax report's tests.

    python -m tests.tradebook_maker      # rebuilds tests/fixtures/tradebooks and tests/fixtures/taxpnl

One story runs through them, so files from several brokers can be combined: RELIANCE bought in 2023 and sold on both
sides of the 23 July 2024 rate change, an intraday INFY round trip, a pre-2018 lot, bonus-free names elsewhere."""
import csv
import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from tests.xlsxmaker import make_workbook, make_xlsx

DIR = Path(__file__).parent / "fixtures" / "tradebooks"


def _csv(rows: list[list]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    return out.getvalue()


# Console › Reports › Tradebook › Download CSV (equity)
ZERODHA = [["symbol", "isin", "trade_date", "exchange", "segment", "series", "trade_type", "auction", "quantity", "price", "trade_id", "order_id", "order_execution_time"],
           ["RELIANCE", "INE002A01018", "2023-05-10", "NSE", "EQ", "EQ", "buy", "false", "10.000000", "2400.000000", "40012231", "1300000004785512", "2023-05-10T10:05:11"],
           ["RELIANCE", "INE002A01018", "2023-08-01", "NSE", "EQ", "EQ", "buy", "false", "5.000000", "2500.000000", "40012675", "1300000005812345", "2023-08-01T11:21:40"],
           ["RELIANCE", "INE002A01018", "2024-06-14", "NSE", "EQ", "EQ", "sell", "false", "8.000000", "2900.000000", "51022310", "1300000007712030", "2024-06-14T14:02:09"],
           ["RELIANCE", "INE002A01018", "2024-08-20", "NSE", "EQ", "EQ", "sell", "false", "7.000000", "3000.000000", "51029877", "1300000008811200", "2024-08-20T09:48:55"],
           ["INFY", "INE009A01021", "2024-09-02", "NSE", "EQ", "EQ", "buy", "false", "20.000000", "1800.000000", "61002231", "1300000009100001", "2024-09-02T09:20:00"],
           ["INFY", "INE009A01021", "2024-09-02", "NSE", "EQ", "EQ", "sell", "false", "20.000000", "1815.000000", "61002999", "1300000009100777", "2024-09-02T15:01:12"],
           ["TCS", "INE467B01029", "2024-01-15", "BSE", "EQ", "A", "buy", "false", "2.000000", "3600.000000", "71000012", "1300000003311111", "2024-01-15T12:00:00"],
           ["NIFTY24SEP25000CE", "", "2024-09-10", "NFO", "FO", "", "buy", "false", "25.000000", "120.500000", "81000001", "1300000009990001", "2024-09-10T10:00:00"]]

# Groww › Reports › Stocks › Order history (Excel): who it's for above, value instead of price, and the order status
GROWW = [["Name", "Asha Kumar"], ["Unique Client Code", "1234567890"], [], ["Order history for 01-04-2024 to 31-03-2025"], [],
         ["Stock name", "Symbol", "ISIN", "Type", "Quantity", "Value", "Exchange", "Exchange Order Id", "Execution date and time", "Order status"],
         ["ITC LIMITED", "ITC", "INE154A01025", "BUY", 100, 41020, "NSE", "1100000012345678", "15-04-2024 10:15 AM", "Executed"],
         ["ITC LIMITED", "ITC", "INE154A01025", "SELL", 40, 19600, "NSE", "1100000023456789", "10-02-2025 02:30 PM", "Executed"],
         ["TATA STEEL LIMITED", "TATASTEEL", "INE081A01020", "BUY", 150, 19260, "NSE", "1100000034567890", "05-06-2024 11:00 AM", "Executed"],
         ["TATA STEEL LIMITED", "TATASTEEL", "INE081A01020", "SELL", 150, 22912.5, "NSE", "", "05-07-2024 09:30 AM", "Cancelled"]]

# Upstox › Reports › Trade book (CSV)
UPSTOX = [["Date", "Company", "Amount", "Exchange", "Segment", "Scrip Code", "Instrument Type", "Strike Price", "Expiry", "Trade Num", "Trade Time", "Side", "Quantity", "Price"],
          ["12-03-2024", "BHARTI AIRTEL LTD", "22110.00", "NSE", "EQ", "BHARTIARTL", "EQUITY", "", "", "300011", "10:02:11", "Buy", "18", "1228.33"],
          ["18-04-2025", "BHARTI AIRTEL LTD", "32400.00", "NSE", "EQ", "BHARTIARTL", "EQUITY", "", "", "300987", "13:45:02", "Sell", "18", "1800.00"],
          ["20-05-2024", "LARSEN & TOUBRO LTD", "21900.00", "NSE", "EQ", "LT", "EQUITY", "", "", "301234", "11:11:11", "Buy", "6", "3650.00"],
          ["21-10-2024", "LARSEN & TOUBRO LTD", "19800.00", "NSE", "EQ", "LT", "EQUITY", "", "", "301999", "14:20:00", "Sell", "6", "3300.00"]]

# Angel One › Reports › Trade book (Excel): a title above, the symbol with its series, charges per trade
ANGEL = [["Angel One Ltd - Trade Book"], ["Client Code: S123456"], [],
         ["Trade Date", "Trade Time", "Symbol", "Exchange", "Segment", "Buy/Sell", "Quantity", "Trade Price", "Trade Value", "Order No", "Trade No", "Brokerage", "STT", "Total Charges"],
         ["02-Jan-2023", "10:05:00", "ASIANPAINT-EQ", "NSE", "Equity", "B", 8, 3100.00, 24800.00, "230102000123", "5001", 20.00, 24.80, 52.30],
         ["15-Mar-2025", "11:30:00", "ASIANPAINT-EQ", "NSE", "Equity", "S", 8, 2250.00, 18000.00, "250315000456", "9001", 20.00, 18.00, 41.10]]

# ICICI Direct › Trade book (CSV): its own stock codes, charges itemised
ICICI = [["Date", "Stock", "Action", "Qty", "Price", "Trade Value", "Order Ref.", "Settlement", "Segment", "DP Id - Client DP Id", "Exchange",
          "ISIN", "STT", "Transaction and SEBI Turnover charges", "Stamp Duty", "Brokerage + GST"],
         ["05-Apr-2016", "STABAN", "Buy", "100", "195.00", "19,500.00", "20160405N900012", "2016066", "Cash", "IN301234-12345678", "NSE",
          "INE062A01020", "19.50", "0.70", "2.00", "40.00"],
         ["02-Jan-2020", "STABAN", "Sell", "100", "334.00", "33,400.00", "20200102N900456", "2020001", "Cash", "IN301234-12345678", "NSE",
          "INE062A01020", "33.40", "1.20", "0.00", "60.00"]]


def hdfc_html() -> str:
    """HDFC Securities saves its trade book as an HTML table with an .xls name."""
    rows = [["Trade Date", "Order No", "Trade No", "Security Name", "ISIN", "Exchange", "Buy/Sell", "Quantity", "Rate", "Brokerage", "Net Rate", "Total"],
            ["11/09/2023", "1000123", "77001", "HDFC BANK LTD", "INE040A01034", "NSE", "BUY", "40", "1,600.00", "32.00", "1,600.80", "64,032.00"],
            ["25/11/2024", "1000456", "77002", "HDFC BANK LTD", "INE040A01034", "NSE", "SELL", "40", "1,790.00", "35.80", "1,789.11", "71,564.20"]]
    head = "<tr>" + "".join(f"<th>{escape(c)}</th>" for c in rows[0]) + "</tr>"
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
    return f"<html><head><meta charset='utf-8'></head><body><h3>HDFC securities - Trade Book</h3><table border='1'>{head}\n{body}</table></body></html>"


# Console › Reports › Tax P&L › Tradewise exits (Excel): one line per sale with its buy, the 31 Jan 2018 value
ZERODHA_PNL = [[], [None, "Client ID", "AB1234"], [None, "Tradewise Exits from 2024-04-01 to 2025-03-31"], [], [None, "Equity"],
               [None, "Symbol", "ISIN", "Entry Date", "Exit Date", "Quantity", "Buy Value", "Sell Value", "Profit", "Period of Holding",
                "Fair Market Value", "Taxable Profit", "Turnover", "Brokerage", "Exchange Transaction Charges", "IPFT", "SEBI Charges",
                "CGST", "SGST", "IGST", "Stamp Duty", "STT"],
               [None, "WIPRO", "INE075A01022", "2017-06-12", "2024-12-16", 50, 13000, 15000, 2000, 2744, 15500, 0, 2000, 0, 0.6, 0, 0.02, 0, 0, 0.11, 0, 15],
               [None, "SBIN", "INE062A01020", "2024-05-02", "2025-01-20", 30, 24600, 22800, -1800, 263, 0, -1800, 1800, 0, 0.9, 0, 0.03, 0, 0, 0.17, 0, 22.8]]

GENERIC = "Date,Symbol,Type,Quantity,Price\n2024-04-10,ICICIBANK,BUY,25,1080\n2025-02-03,ICICIBANK,SELL,10,1250\n2024-10-01,NOTASTOCK,BUY,5,10\n"


# Console › Reports › Tax P&L › Download: a ZIP of one CSV per segment and the summary workbook, in a folder, with the
# __MACOSX copies a Mac adds. Made-up trades in the real column layout. The F&O file is the big one in real life.
ZIP_DIR = Path(__file__).parent / "fixtures" / "taxpnl"
PNL_HEAD = ["Symbol", "ISIN", "Entry Date", "Exit Date", "Quantity", "Buy Value", "Sell Value", "Profit", "Period of Holding",
            "Fair Market Value", "Taxable Profit", "Turnover", "Brokerage", "Exchange Transaction Charges", "IPFT", "SEBI Charges",
            "CGST", "SGST", "IGST", "Stamp Duty", "STT"]
DERIV_HEAD = ["Symbol", "Entry Date", "Exit Date", "Quantity", "Buy Value", "Sell Value", "Profit", "Turnover", "Brokerage",
              "Exchange Transaction Charges", "IPFT", "SEBI Charges", "CGST", "SGST", "IGST", "Stamp Duty", "STT"]
TAX_SHORT = [PNL_HEAD,
             # RELIANCE: the second line was bought the day the first was sold, which is not an intraday trade
             ["RELIANCE", "INE002A01018", "2024-05-10", "2024-09-16", 10, 24000, 29000, 5000, 129, 0, 5000, 0, 0, 0.9, 0.03, 0.03, 0, 0, 0.17, 0, 29],
             ["RELIANCE", "INE002A01018", "2024-09-16", "2024-12-02", 5, 14600, 13000, -1600, 77, 0, -1600, 0, 0, 0.42, 0.01, 0.01, 0, 0, 0.08, 2.19, 13],
             ["TCS", "INE467B01029", "2024-06-03", "2025-01-15", 3, 11400, 12300, 900, 226, 0, 900, 0, 0, 0.38, 0.01, 0.01, 0, 0, 0.07, 0, 12.3]]
TAX_LONG = [PNL_HEAD,
            ["WIPRO", "INE075A01022", "2017-06-12", "2024-12-16", 50, 13000, 15000, 2000, 2744, 15500, 0, 0, 0, 0.6, 0.02, 0.02, 0, 0, 0.11, 0, 15],
            ["ITC", "INE154A01025", "2023-04-10", "2024-10-21", 100, 38000, 49000, 11000, 560, 0, 11000, 0, 0, 1.6, 0.05, 0.05, 0, 0, 0.3, 0, 49]]
TAX_INTRADAY = [PNL_HEAD,
                ["INFY", "INE009A01021", "2024-09-02", "2024-09-02", 20, 36000, 36300, 300, 0, 0, 300, 300, 20, 2.1, 0.07, 0.07, 0, 0, 4.0, 1.08, 9.07],
                ["INFY", "INE009A01021", "2024-09-02", "2024-09-02", 10, 18010, 17990, -20, 0, 0, -20, 20, 10, 1.05, 0.04, 0.04, 0, 0, 2.0, 0.54, 4.5],
                ["SBIN", "INE062A01020", "2024-11-05", "2024-11-05", 50, 41000, 40800, -200, 0, 0, -200, 200, 20, 2.4, 0.08, 0.08, 0, 0, 4.4, 1.23, 10.2]]
# F&O: one option contract traded twice (a gain, then a loss), a futures loss and another option's gain. Results
# 1,087.5 - 400 - 2,500 + 600 = -1,212.5; turnover trade by trade 4,587.5, netted per contract 3,787.5 (as the
# summary sheet adds it up); charges 50 + 20 + 120 + 30 = 220
TAX_FNO = [DERIV_HEAD,
           ["NIFTY24SEP25000CE", "2024-09-10T10:00:00", "2024-09-12T14:00:00", 25, 3012.5, 4100, 1087.5, 1087.5, 40, 1.4, 0.01, 0.99, 0, 0, 5, 0.1, 2.5],
           ["NIFTY24SEP25000CE", "2024-09-13T09:30:00", "2024-09-13T15:00:00", 25, 4000, 3600, -400, 400, 15, 0.5, 0, 0.5, 0, 0, 2, 0, 2],
           ["BANKNIFTY24OCTFUT", "2024-10-01T09:20:00", "2024-10-03T15:10:00", 15, 780000, 777500, -2500, 2500, 40, 30, 0.5, 1.5, 0, 0, 13, 20, 15],
           ["RELIANCE24NOV3000PE", "2024-11-04T10:00:00", "2024-11-06T11:00:00", 250, 5000, 5600, 600, 600, 20, 2, 0, 0.5, 0, 0, 4, 0.5, 3]]
# commodity: a crude oil futures gain and a gold futures loss (1,500 net, turnover 2,500, charges 51.2 + 20 = 71.2)
TAX_COMMODITY = [DERIV_HEAD,
                 ["CRUDEOIL24AUGFUT", "2024-08-01T10:00:00", "2024-08-02T10:00:00", 1, 650000, 652000, 2000, 2000, 40, 3, 0, 0.1, 0, 0, 7.9, 0.2, 0],
                 ["GOLDM24OCTFUT", "2024-10-01T10:00:00", "2024-10-08T10:00:00", 1, 750000, 749500, -500, 500, 15, 2, 0, 0, 0, 0, 3, 0, 0]]
TAX_CURRENCY = [DERIV_HEAD, ["USDINR24AUGFUT", "2024-08-01T10:00:00", "2024-08-05T10:00:00", 1000, 83500, 83600, 100, 100, 40, 0.3, 0, 0, 0, 0, 7.3, 0.01, 0]]


def deriv_summary(segment: str, options: tuple[float, float], futures: tuple[float, float]) -> list[list]:
    """A segment's sheet of the summary workbook: (result, turnover) for options and for futures."""
    return [[], [None, "Client ID", "AB1234"], [], [None, f"Taxpnl Statement for {segment} from 2024-04-01 to 2025-03-31"], [],
            [None, "Realized Profit Breakdown"], [], [None, "Options Realized Profit", options[0]], [None, "Futures Realized Profit", futures[0]],
            [], [None, "Turnover Breakdown"], [], [None, "Options Turnover", options[1]], [None, "Futures Turnover", futures[1]]]


DERIV_SHEETS = [("F&O", deriv_summary("F&O", (1287.5, 1287.5), (-2500, 2500))),
                ("Currency", deriv_summary("Currency", (0, 0), (100, 100))),
                ("Commodity", deriv_summary("Commodity", (0, 0), (1500, 2500)))]
TAX_NON_EQUITY = [PNL_HEAD, ["GOLDBEES", "INF204KB17I5", "2024-04-15", "2024-11-20", 100, 6100, 6600, 500, 219, 0, 500, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]
TAX_SUMMARY = [[], [None, "Client ID", "AB1234"], [None, "Client Name", "Asha Kumar"], [None, "PAN", "ABCDE1234F"], [],
               [None, "Taxpnl Statement for Equity from 2024-04-01 to 2025-03-31"], [], [None, "Realized Profit Breakdown"], [],
               [None, "Intraday/Speculative profit", 80], [None, "Short Term profit", 4300], [None, "Long Term profit", 13000],
               [None, "Non Equity profit", 500], [], [None, "Intraday"], [],
               [None, "Symbol", "Quantity", "Buy Value", "Sell Value", "Realized P&L"],
               [None, "INFY", 30, 54010, 54290, 280], [None, "SBIN", 50, 41000, 40800, -200], [],
               [None, "Short Term Trades"], [], [None, "Symbol", "Quantity", "Buy Value", "Sell Value", "Realized P&L"],
               [None, "RELIANCE", 15, 38600, 42000, 3400], [None, "TCS", 3, 11400, 12300, 900]]


# the dividend sheet newer years' workbooks have (not in the saved fixture, which is FY 2024-25 as it was)
DIVIDEND_SHEET = [[], [None, "Client ID", "AB1234"], [], [None, "Equity Dividends from 2025-04-01 to 2026-03-31"], [],
                  [None, "Symbol", "ISIN", "Ex-Date", "Quantity", "Dividend Per Share", "Net Dividend Amount"],
                  [None, "ITC", "INE154A01025", "2025-05-28", 1000, 7.85, 7850], [None, "ITC", "INE154A01025", "2026-02-04", 1000, 6.5, 6500],
                  [None, "TCS", "INE467B01029", "2025-07-16", 10, 11, 110], [], [None, "Total Dividend Amount", None, None, None, None, 14460]]


def zerodha_tax_zip(summary: list[list] | None = None, deriv: bool = True, dividends: bool = False) -> bytes:
    """The whole ZIP, the way Console gives it (fixed dates inside, so only the workbook's own stamp varies);
    `dividends` adds the newer years' dividend sheet."""
    folder = "taxpnl-AB1234-2024_2025-Q1-Q4/"
    exits = "Tradewise Exits from 2024-04-01 to 2025-03-31-"
    files = [(f"{exits}Commodity.csv", _csv(TAX_COMMODITY).encode()), (f"{exits}Non Equity.csv", _csv(TAX_NON_EQUITY).encode()),
             ("taxpnl-2024_2025-Q1-Q4.xlsx", make_workbook([("Equity and Non Equity", summary or TAX_SUMMARY), ("Mutual Funds", [[]])]
                                                          + (DERIV_SHEETS if deriv else [])
                                                          + ([("Equity Dividends", DIVIDEND_SHEET)] if dividends else []))),
             (f"{exits}Equity - Short Term.csv", _csv(TAX_SHORT).encode()), (f"{exits}Equity - Long Term.csv", _csv(TAX_LONG).encode()),
             (f"{exits}Equity - Intraday.csv", _csv(TAX_INTRADAY).encode()), (f"{exits}F&O.csv", _csv(TAX_FNO).encode()),
             (f"{exits}Currency.csv", _csv(TAX_CURRENCY).encode())]
    out = io.BytesIO()
    stamp = (2025, 6, 23, 9, 46, 0)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo(folder, stamp), b"")
        z.writestr(zipfile.ZipInfo("__MACOSX/._" + folder.rstrip("/"), stamp), b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        ")
        for name, data in files:
            z.writestr(zipfile.ZipInfo(folder + name, stamp), data, zipfile.ZIP_DEFLATED)
            z.writestr(zipfile.ZipInfo(f"__MACOSX/{folder}._{name}", stamp), b"\x00\x05\x16\x07\x00\x02\x00\x00Mac OS X        ")
    return out.getvalue()


def write():
    ZIP_DIR.mkdir(parents=True, exist_ok=True)
    (ZIP_DIR / "zerodha_taxpnl_2024_2025.zip").write_bytes(zerodha_tax_zip())
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / "zerodha_console_tradebook.csv").write_text(_csv(ZERODHA))
    (DIR / "groww_order_history.xlsx").write_bytes(make_xlsx(GROWW, "Orders"))
    (DIR / "upstox_tradebook.csv").write_text(_csv(UPSTOX))
    (DIR / "angel_one_tradebook.xlsx").write_bytes(make_xlsx(ANGEL, "Trades"))
    (DIR / "icici_direct_tradebook.csv").write_text(_csv(ICICI))
    (DIR / "hdfc_securities_tradebook.xls").write_text(hdfc_html())
    (DIR / "zerodha_tax_pnl.xlsx").write_bytes(make_xlsx(ZERODHA_PNL, "Tradewise Exits"))
    (DIR / "generic_trades.csv").write_text(GENERIC)


if __name__ == "__main__":
    write()
