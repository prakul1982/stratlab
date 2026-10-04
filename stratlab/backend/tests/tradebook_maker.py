"""Sample tradebooks and tax P&L files, laid out the way each broker exports them, for the tax report's tests.

    python -m tests.tradebook_maker      # rebuilds tests/fixtures/tradebooks

One story runs through them, so files from several brokers can be combined: RELIANCE bought in 2023 and sold on both
sides of the 23 July 2024 rate change, an intraday INFY round trip, a pre-2018 lot, bonus-free names elsewhere."""
import csv
import io
from pathlib import Path
from xml.sax.saxutils import escape

from tests.xlsxmaker import make_xlsx

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


def write():
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
