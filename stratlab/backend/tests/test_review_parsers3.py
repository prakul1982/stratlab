"""Review of the broker connections and file parsers (round 3): IBKR's levels of detail and unmatched sales, files over the
row caps, a US broker's side and fee columns, dividends from several sources, the AIS JSON, spreadsheet formula guards,
two-digit years, a tradebook uploaded as holdings, and the smaller parsing fixes. Every file here is made up."""
import json
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest
import time_machine

from app import holdings_file as hf, money_dividends as divs, money_itr, money_mf, money_networth, money_us_tax as us
from app.connect import docs, ibkr
from tests import xlsxmaker

TRADEBOOKS = Path(__file__).parent / "fixtures" / "tradebooks"


def flex(body: str) -> ET.Element:
    return ET.fromstring(f"<FlexQueryResponse><FlexStatements><FlexStatement>{body}</FlexStatement></FlexStatements></FlexQueryResponse>")


def trade(side, qty, price, day, tid, oc=None, level=None, sym="AAPL"):
    q = -qty if side == "SELL" else qty
    return (f'<Trade assetCategory="STK" currency="USD" symbol="{sym}" buySell="{side}" quantity="{q}" tradePrice="{price}" '
            f'tradeDate="{day}" dateTime="{day};100000" tradeID="{tid}" ibCommission="-1"'
            + (f' openCloseIndicator="{oc}"' if oc else "") + (f' levelOfDetail="{level}"' if level else "") + "/>")


# ---------- 1. a sale with no purchase in the window ----------
def test_a_sale_of_shares_bought_before_the_window_opens_no_short_lot():
    root = flex("<Trades>" + trade("SELL", 10, 190, "20250310", "1", oc="C") + trade("BUY", 10, 170, "20250410", "2", oc="O") + "</Trades>")
    assert ibkr.closed_trades(ibkr.fills(root)) == []                    # not a short from March to April


def test_a_sale_opens_a_short_only_when_ibkr_says_it_opens():
    root = flex("<Trades>" + trade("SELL", 10, 190, "20250310", "1", oc="O") + trade("BUY", 10, 170, "20250410", "2", oc="C") + "</Trades>")
    got = ibkr.closed_trades(ibkr.fills(root))
    assert [(t["side"], t["qty"], t["entry"], t["exit"]) for t in got] == [("short", 10.0, 190.0, 170.0)]


def test_the_unmatched_rest_of_a_sale_is_dropped_but_the_matched_part_pairs():
    root = flex("<Trades>" + trade("BUY", 4, 100, "20250301", "1", oc="O") + trade("SELL", 10, 120, "20250310", "2", oc="C")
                + trade("BUY", 6, 90, "20250320", "3", oc="O") + "</Trades>")
    got = ibkr.closed_trades(ibkr.fills(root))
    assert [(t["side"], t["qty"], t["entry"], t["exit"]) for t in got] == [("long", 4.0, 100.0, 120.0)]    # the other 6 are not a short


# ---------- 2. one position or trade listed at several levels of detail ----------
POSITIONS = ('<OpenPosition assetCategory="STK" currency="USD" symbol="AAPL" position="10" costBasisPrice="150" levelOfDetail="SUMMARY"/>'
             '<OpenPosition assetCategory="STK" currency="USD" symbol="AAPL" position="4" costBasisPrice="140" levelOfDetail="LOT"/>'
             '<OpenPosition assetCategory="STK" currency="USD" symbol="AAPL" position="6" costBasisPrice="156.6667" levelOfDetail="LOT"/>')


def test_positions_are_counted_once_when_the_lots_are_listed_too():
    rows, left = ibkr.positions(flex(f"<OpenPositions>{POSITIONS}</OpenPositions>"))
    assert [(r["symbol"], r["qty"], r["avg"]) for r in rows] == [("AAPL", 10.0, 150.0)] and left == 0


def test_positions_from_lots_alone_are_added_up():
    lots = POSITIONS.split("/>")[1:3]
    rows, _ = ibkr.positions(flex("<OpenPositions>" + "/>".join(lots) + "/></OpenPositions>"))
    assert [(r["symbol"], r["qty"]) for r in rows] == [("AAPL", 10.0)]


def test_only_executions_are_trades():
    root = flex("<Trades>" + trade("BUY", 10, 100, "20250101", "1", level="EXECUTION") + trade("BUY", 10, 100, "20250101", "", level="ORDER")
                + trade("SELL", 10, 120, "20250201", "3", level="EXECUTION") + trade("SELL", 10, 120, "20250201", "3", level="CLOSED_LOT")
                + trade("BUY", 1, 100, "20250102", "5") + "</Trades>")
    assert [(f["side"], f["qty"]) for f in ibkr.fills(root)] == [("B", 10.0), ("B", 1.0), ("S", 10.0)]       # no level counts as an execution


# ---------- 3. files over the row caps ----------
def holdings_csv(n: int) -> bytes:
    return ("Symbol,Quantity,Average Price\n" + "".join(f"S{i},1,10\n" for i in range(n))).encode()


def test_a_holdings_file_over_the_cap_is_refused_not_cut():
    with pytest.raises(hf.FileError, match=r"more than 5,000 lines; split it by year or quarter"):
        hf.parse(holdings_csv(hf.MAX_ROWS + 1), "h.csv")
    assert len(hf.parse(holdings_csv(hf.MAX_ROWS), "h.csv")["rows"]) == hf.MAX_ROWS             # the header is not a line of data


def test_a_workbook_and_an_html_table_over_the_cap_are_refused_too():
    sheet = lambda n: [["Symbol", "Quantity"]] + [[f"S{i}", 1] for i in range(n)]               # noqa: E731
    with pytest.raises(hf.FileError, match="more than 5,000 lines"):
        hf.parse(xlsxmaker.make_xlsx(sheet(hf.MAX_ROWS + 1)), "h.xlsx")
    assert len(hf.parse(xlsxmaker.make_xlsx(sheet(hf.MAX_ROWS)), "h.xlsx")["rows"]) == hf.MAX_ROWS
    html = lambda n: ("<table><tr><td>Symbol</td><td>Quantity</td></tr>" + "".join(f"<tr><td>S{i}</td><td>1</td></tr>" for i in range(n)) + "</table>").encode()  # noqa: E731
    with pytest.raises(hf.FileError, match="more than 5,000 lines"):
        hf.parse(html(hf.MAX_ROWS + 1), "h.xls")
    assert len(hf.parse(html(hf.MAX_ROWS), "h.xls")["rows"]) == hf.MAX_ROWS


def tradebook_csv(n: int) -> bytes:
    lines = ["symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,order_execution_time"]
    lines += [f"RELIANCE,INE002A01018,2024-01-{i % 28 + 1:02d},NSE,EQ,EQ,buy,false,1,2500,{i},{i},2024-01-01T10:00:00" for i in range(n)]
    return "\n".join(lines).encode()


def test_a_tradebook_over_the_cap_is_refused_not_cut():
    with pytest.raises(hf.FileError, match=r"more than 20,000 lines; split it by year or quarter"):
        hf.parse_trades(tradebook_csv(hf.MAX_TRADES + 1), "tb.csv")
    assert len(hf.parse_trades(tradebook_csv(hf.MAX_TRADES), "tb.csv")["trades"]) == hf.MAX_TRADES


def test_a_tax_pnl_counts_its_lines_not_the_two_trades_each_makes():
    head = "Symbol,Quantity,Buy Date,Sell Date,Buy Price,Sell Price\n"
    rows = lambda n: head + "".join("INFY,1,2023-01-02,2024-01-02,100,120\n" for _ in range(n))   # noqa: E731
    with pytest.raises(hf.FileError, match="more than 10,000 lines"):
        hf.parse_trades(rows(hf.MAX_TRADES // 2 + 1).encode(), "pnl.csv")
    assert len(hf.parse_trades(rows(hf.MAX_TRADES // 2).encode(), "pnl.csv")["trades"]) == hf.MAX_TRADES


def test_us_trades_and_dividends_over_their_caps_are_refused():
    csv = lambda n: ("Date,Action,Symbol,Quantity,Price\n" + "".join("03/20/2025,Buy,AAPL,1,170\n" for _ in range(n))).encode()   # noqa: E731
    with pytest.raises(hf.FileError, match="more than 5,000 lines"):
        us.parse_upload(csv(us.MAX_TRADES + 1), "us.csv")
    assert len(us.parse_upload(csv(us.MAX_TRADES), "us.csv")["rows"]) == us.MAX_TRADES
    div = lambda n: ("Date,Symbol,Amount\n" + "".join("2025-03-15,TCS,100\n" for _ in range(n))).encode()                          # noqa: E731
    with pytest.raises(hf.FileError, match="more than 3,000 lines"):
        divs.parse_upload(div(divs.MAX_ROWS + 1), "d.csv")
    assert len(divs.parse_upload(div(divs.MAX_ROWS), "d.csv")["rows"]) == divs.MAX_ROWS


# ---------- 4. a US broker's side and fee columns ----------
ROBINHOOD = (b"Activity Date,Process Date,Settle Date,Instrument,Description,Trans Code,Quantity,Price,Amount\n"
             b"3/20/2025,3/20/2025,3/21/2025,AAPL,Apple Inc,Buy,10,$170.00,($1700.00)\n"
             b"4/10/2025,4/10/2025,4/11/2025,AAPL,Apple Inc,Sell,10,$190.00,$1900.00\n"
             b"4/12/2025,4/12/2025,4/12/2025,AAPL,Apple Inc,CDIV,,,$0.50\n")
SCHWAB = (b"Date,Action,Symbol,Description,Quantity,Price,Fees & Comm,Amount\n"
          b"03/20/2025,Buy,AAPL,APPLE INC,10,$170.00,$0.65,-$1700.65\n"
          b"04/10/2025,Sell,AAPL,APPLE INC,10,$190.00,$0.65,$1899.35\n")


def test_robinhoods_trans_code_says_buy_or_sell():
    got = us.parse_upload(ROBINHOOD, "rh.csv")
    assert [(r["d"], r["side"], r["qty"]) for r in got["rows"]] == [("2025-03-20", "B", 10.0), ("2025-04-10", "S", 10.0)]
    assert [p["line"] for p in got["problems"]] == [4]                                          # the dividend line is not a trade


def test_schwabs_fees_and_comm_column_is_read_as_fees():
    assert [(r["side"], r["fees"]) for r in us.parse_upload(SCHWAB, "sc.csv")["rows"]] == [("B", 0.65), ("S", 0.65)]


def test_a_file_with_no_side_column_and_no_negative_quantity_is_refused():
    with pytest.raises(hf.FileError, match="purchases and which are sales"):
        us.parse_upload(b"Date,Symbol,Quantity,Price\n03/20/2025,AAPL,10,170\n04/10/2025,AAPL,10,190\n", "x.csv")
    got = us.parse_upload(b"Date,Symbol,Quantity,Price\n03/20/2025,AAPL,10,170\n04/10/2025,AAPL,-10,190\n", "x.csv")     # a sale as a negative
    assert [r["side"] for r in got["rows"]] == ["B", "S"]


# ---------- 5. the same dividends from several sources ----------
def row(d, sym, amount, src):
    return {"d": d, "sym": sym, "name": "", "isin": "", "qty": None, "ps": None, "amount": amount, "tds": None, "cur": "INR", "src": src}


def dividend_view(rows):
    stored = {"rows": rows, "files": [], "include": {}, "updated_at": None}
    return divs.view(stored, [], [], None, date(2026, 10, 15))


def fy2025(v):
    return next(y for y in v["years"] if y["fy"] == 2025)


def test_ais_lines_are_set_aside_for_a_year_the_brokers_sheet_covers():
    v = dividend_view([row("2025-06-12", "TCS", 1000.0, "statement"), row("2025-06-12", "TATA CONSULTANCY SERVICES LTD", 1000.0, "AIS"),
                       row("2025-12-20", "BETA BANK LTD", 500.0, "AIS")])
    y = fy2025(v)
    assert y["total"] == 1000.0 and y["count"] == 1 and y["ais_set_aside"] == 2 and "2 AIS dividend lines not counted" in y["ais_note"]
    assert divs.for_total(v) == {2025: 1000.0}
    assert divs.events(v, {"rows": [row("2025-06-12", "TCS", 1000.0, "statement"), row("2025-06-12", "TCS LTD", 1000.0, "AIS")]},
                       [], None, 2025) == [("2025-06-12", 1000.0)]


def test_a_users_csv_also_wins_over_the_ais_and_the_ais_alone_is_counted():
    assert fy2025(dividend_view([row("2025-06-12", "TCS", 700.0, "csv"), row("2025-06-12", "TCS LTD", 700.0, "AIS")]))["total"] == 700.0
    y = fy2025(dividend_view([row("2025-06-12", "TCS LTD", 700.0, "AIS")]))
    assert y["total"] == 700.0 and y["ais_set_aside"] == 0 and y["ais_note"] is None


def test_the_same_line_from_a_trusted_source_replaces_the_ais_one():
    merged, added, dup = divs.merge([row("2025-06-12", "TCS", 1000.0, "AIS")], [row("2025-06-12", "TCS", 1000.0, "statement")])
    assert (added, dup) == (0, 1) and [r["src"] for r in merged] == ["statement"]


# ---------- 6. the AIS JSON ----------
def test_a_section_total_and_its_lines_are_not_added_twice():
    doc = {"dividendIncome": {"informationDescription": "Dividend income", "amount": 3000,
                              "details": [{"informationDescription": "Dividend", "amount": 1000, "dateOfPayment": "15/03/2025", "sourceName": "A"},
                                          {"amount": 2000, "dateOfPayment": "16/03/2025", "sourceName": "B"}]},
           "financialYear": "2024-25"}
    got = docs.read_ais_json(json.dumps(doc).encode())
    assert got["dividend"] == 3000.0 and len(got["lines"]) == 2 and got["fy"] == 2024


def test_the_year_comes_from_the_year_keys_not_from_a_date():
    line = {"informationDescription": "Dividend", "amount": 1000, "dateOfPayment": "2025-03-15", "sourceName": "A"}
    assert docs.read_ais_json(json.dumps({"x": [line], "assessmentYear": "2025-26"}).encode())["fy"] == 2024     # AY 2025-26 is FY 2024-25
    assert docs.read_ais_json(json.dumps({"x": [line], "financialYear": "2025-26"}).encode())["fy"] == 2025
    assert docs.read_ais_json(json.dumps({"x": [line]}).encode())["fy"] is None                                  # 2025-03 is a month, not a year


def test_a_deeply_nested_or_broken_ais_file_is_a_clean_error():
    for raw in (b"[" * 200000, b'{"a": ' * 100000, b"{broken", b"\xff\xfe"):
        with pytest.raises(docs.DocError) as e:
            docs.read_ais_json(raw)
        assert e.value.code == "unreadable"
    deep = b"[" * 300 + b"]" * 300
    assert docs.read_ais_json(deep)["dividend"] is None                       # deep but fine: no recursion of ours to run out


# ---------- 8. formula guards ----------
@pytest.mark.parametrize("guard", [money_itr._safe, money_networth._cell])
def test_text_that_starts_like_a_formula_is_escaped(guard):
    for v in ("=1+1", "=9", "=HYPERLINK(\"http://x\",\"a\")", "@SUM(1+1)", "@1", "+1+2", "-2+3", "-1-1", "+cmd|' /C calc'!A0", "-", "\t=1", "\r1"):
        assert guard(v) == "'" + v, v
    for v in ("-5", "+5", "-1,234.50", "-0.5", "+.5", "-1e5", "plain", "", "5-3"):
        assert guard(v) == v, v
    assert guard(-5) == -5


# ---------- 9. two-digit years ----------
@time_machine.travel("2026-10-15")
def test_two_digit_years_are_this_century_unless_that_is_after_next_year():
    assert hf.day("22/07/24") == "2024-07-22" and hf.day("22-Jul-24") == "2024-07-22"
    assert hf.day("01/01/27") == "2027-01-01"                   # next year
    assert hf.day("01/01/28") == "1928-01-01" and hf.day("1/2/99") == "1999-02-01" and hf.day("05-Jun-45") == "1945-06-05"


def test_a_three_digit_year_is_not_a_date():
    assert hf.day("22-07-202") is None and hf.day("22-Jul-202") is None and hf.day("22/07/2024") == "2024-07-22"


# ---------- 10. a tradebook is not a holdings file ----------
@pytest.mark.parametrize("name", ["zerodha_console_tradebook.csv", "upstox_tradebook.csv", "icici_direct_tradebook.csv", "generic_trades.csv"])
def test_a_tradebook_uploaded_as_holdings_is_refused_with_where_to_take_it(name):
    with pytest.raises(hf.FileError, match="tradebook.*tax report or the trade journal"):
        hf.parse((TRADEBOOKS / name).read_bytes(), name)


# ---------- 11. smaller items ----------
def test_a_mutual_fund_csv_with_a_broken_field_is_a_clean_error():
    big = b"Date,Scheme,ISIN,Units,Amount,Type\n01/01/2024," + b"x" * 200000 + b",INF000000001,10,1000,Purchase\n"
    with pytest.raises(money_mf.FileError, match="broken"):
        money_mf.parse_csv(big)


def test_the_unicode_minus_is_a_minus_and_a_decimal_comma_is_not_read_as_thousands():
    assert hf.number("−5") == -5 and hf.number("−1,234.5") == -1234.5
    assert hf.number("1 234,5") is None and hf.number("1,5") is None and hf.number("1.234,56") is None
    assert hf.number("12,34,567") == 1234567 and hf.number("1,234") == 1234 and hf.number("1,23,456.78") == 123456.78 and hf.number("1 234.5") == 1234.5
