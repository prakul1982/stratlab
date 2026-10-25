"""The US stocks upload takes a realised-gains tax report such as Vested's yearly one (MO-1): the lots sold become purchases
and sales, the dividend, interest and other sections are never read as trades, the user's personal sheet is never read or
kept, a second upload adds nothing, and the ready-made schedule workbooks and PDFs get a message of their own. The files here
are made up: a fake name, PAN and account number stand in for the personal sheet."""
import json

import pytest

from app import db, money_us_tax as us
from tests import fx_rates, world
from tests.xlsxmaker import make_workbook

PRO = world.headers("pro-token")
FAKE = ("Jane Q Testperson", "ABCDE1234F", "DW12345678")
LOT = ["Security", "Quantity Sold", "Date Acquired", "Buying Price (USD)", "Date Sold", "Selling Price (USD)", "Proceeds (USD)",
       "Cost Basis (USD)", "Gains/Losses (USD)", "USD-INR Conversion Rate", "Gains/Losses (INR)"]
DIV = ["Security", "Dividend Date", "Dividend Per Share (USD)", "Dividend Received (USD)", "Dividend Tax (USD)", "Net Dividend (USD)",
       "USD-INR Conversion Rate", "Net Dividend (INR)"]


def history(short=None, long=None) -> list[list]:
    """The "Transaction History" sheet laid out the way the report has it: a title row, a blank line, a section title, its
    column names, then the lines; formulas left blank."""
    short = [["NVDA", 2, "2025-04-07", 96.3, "2025-06-12", 142.1, 284.2, 192.6, None, 85.6, None],
             ["NVDA", 0.123456, "2025-04-07", 96.3, "2025-07-01", 150.0, 18.52, 11.89, None, 85.6, None],
             ["AAPL", 3, "2025-02-03", 200.0, "2025-08-04", 210.0, 630, 600, None, 85.6, None]] if short is None else short
    long = [["MSFT", 1.5, "2022-01-10", 300.0, "2025-09-09", 500.0, 750, 450, None, 85.6, None]] if long is None else long
    return ([["Proceeds from Transactions"], [], ["Short Term Gains (Losses)"], LOT, *short, [],
             ["Long Term Gains (Losses)"], LOT, *long, [],
             ["Dividends"], DIV, ["KO", "2025-03-14", 0.51, 5.1, 1.28, 3.82, 85.4, 326.2],
             ["NVDA", "2025-06-27", 0.01, 0.2, 0.05, 0.15, 85.6, 12.8], [],
             ["Note: Please note that dividend payout dates may differ"], [],
             ["Interest Income"], ["Interest Paid Date", "Interest Amount (USD)", "Interest Tax (USD)"], ["2025-05-01", 1.1, 0.27], [],
             ["SLIP Income"], ["Security", "Date", "Amount (USD)"], ["TSLA", "2025-05-02", 0.4], [],
             ["Income from Spinoff"], ["Security", "Date", "Amount (USD)"], ["GE", "2025-04-02", 9.9]])


def report(**kw) -> bytes:
    return make_workbook([("Transaction History", history(**kw)), ("Summary", [["Total Gains (USD)", 12.5], ["Security", "Quantity"]]),
                          ("User Details", [["Name", FAKE[0]], ["PAN", FAKE[1]], ["Account Number", FAKE[2]]])])


def trades(got):
    return [(r["d"], r["side"], r["sym"], r["qty"], r["price"]) for r in got["rows"]]


def test_the_lots_sold_are_read_as_a_purchase_and_a_sale_each():
    got = us.parse_upload(report(), "2025.xlsx")
    assert sorted(trades(got)) == sorted([
        ("2025-04-07", "B", "NVDA", 2, 96.3), ("2025-06-12", "S", "NVDA", 2, 142.1),
        ("2025-04-07", "B", "NVDA", 0.123456, 96.3), ("2025-07-01", "S", "NVDA", 0.123456, 150.0),     # a fractional lot
        ("2025-02-03", "B", "AAPL", 3, 200.0), ("2025-08-04", "S", "AAPL", 3, 210.0),
        ("2022-01-10", "B", "MSFT", 1.5, 300.0), ("2025-09-09", "S", "MSFT", 1.5, 500.0)])             # the long-term section too
    assert got["problems"] == [] and got["date_note"] is None


def test_nothing_below_the_gains_sections_is_a_trade_and_the_personal_sheet_is_never_kept():
    got = us.parse_upload(report(), "2025.xlsx")
    assert {r["sym"] for r in got["rows"]} == {"NVDA", "AAPL", "MSFT"}                  # no KO, TSLA or GE: their lines are not lots
    blob = json.dumps(got)
    assert not [x for x in FAKE if x in blob] and "Interest" not in blob and "Dividend" not in blob.replace("Dividends", "")
    # the same, with no long-term lines at all (an empty section) and no short-term ones
    only_long = us.parse_upload(report(short=[]), "2025.xlsx")
    assert {r["sym"] for r in only_long["rows"]} == {"MSFT"}
    with pytest.raises(us.hf.FileError):
        us.parse_upload(report(short=[], long=[]), "2025.xlsx")


def test_other_apps_column_names_and_a_csv_work_and_unreadable_lines_are_reported():
    csv = ("Realised gains\nStock,Qty,Purchase Date,Buy Price,Sale Date,Sell Price\nTSLA,2,2024-01-02,180,2025-03-04,260\n"
           "TSLA,1,not a date,180,2025-03-04,260\nTSLA,1,2024-01-02,,2025-03-04,260\nTSLA,1,2025-05-05,180,2025-03-04,260\nTotal,4,,,,\n")
    got = us.parse_upload(csv.encode(), "gains.csv")
    assert trades(got) == [("2024-01-02", "B", "TSLA", 2, 180.0), ("2025-03-04", "S", "TSLA", 2, 260.0)]
    assert [p["reason"] for p in got["problems"]] == ["No date", "No price", "Sold before it was acquired"]
    assert [p["line"] for p in got["problems"]] == [4, 5, 6]


def test_it_says_it_is_a_realised_gains_report_and_a_trade_list_says_nothing_of_the_kind():
    note = us.parse_upload(report(), "2025.xlsx")["note"]
    assert "realised-gains report" in note and "Schedule FA" in note and "still hold" in note
    assert not any(w in note.lower() for w in ("you should", "recommend", "drivewealth"))      # facts only, no vendor name
    assert us.parse_upload(b"Date,Side,Symbol,Quantity,Price\n2023-03-01,BUY,AAPL,3,150\n", "t.csv")["note"] is None


def test_the_ready_made_schedules_and_a_pdf_get_their_own_message():
    for label, sheet, file in (("Schedule FA", "Schedule FA", "2025-Schedule FA.xlsx"), ("Schedule FSI", "FSI", "2025-Schedule FSI.xlsx"),
                               ("Schedule TR", "Sheet1", "2025-Schedule TR.xlsx"), ("Form 67", "Form 67", "2025-Form 67.xlsx")):
        # by the sheet's name, or by the title row, and by the file name alone
        for data, name in ((make_workbook([(sheet, [[label], ["Country", "Entity", "Amount"], ["US", "X Corp", 5]])]), "a.xlsx"),
                           (make_workbook([("Sheet1", [[f"{label} - details"], ["Country", "Entity", "Amount"], ["US", "X Corp", 5]])]), "a.xlsx"),
                           (make_workbook([("Sheet1", [["Country", "Entity", "Amount"], ["US", "X Corp", 5]])]), file)):
            with pytest.raises(us.hf.FileError) as e:
                us.parse_upload(data, name)
            assert f"ready-made {label} table, not a list of trades" in str(e.value) and "Transaction History" in str(e.value), (label, name)
    with pytest.raises(us.hf.FileError) as e:
        us.parse_upload(b"%PDF-1.7\n1 0 obj\n", "2025.pdf")
    assert str(e.value) == "PDFs can't be read: upload the Excel (.xlsx) or CSV version of the same report."
    with pytest.raises(us.hf.FileError) as e:                                            # any other workbook keeps the general message
        us.parse_upload(make_workbook([("Sheet1", [["Name", "Age"], ["A", 3]])]), "x.xlsx")
    assert str(e.value).startswith("No US trades were found in that file")


def test_two_equal_lots_both_count_and_a_second_upload_adds_nothing():
    same = [["NVDA", 2, "2025-04-07", 96.3, "2025-06-12", 142.1, None, None, None, None, None],
            ["NVDA", 2, "2025-04-07", 96.3, "2025-06-12", 142.1, None, None, None, None, None],         # a second, identical lot
            ["NVDA", 2, "2025-04-07", 96.3, "2025-07-12", 150.0, None, None, None, None, None]]       # the same purchase, sold another day
    got = us.parse_upload(report(short=same, long=[]), "2025.xlsx")
    first, added, dup = us.merge([], got["rows"])
    assert (added, dup, len(first)) == (6, 0, 6)
    again, added, dup = us.merge(first, us.parse_upload(report(short=same, long=[]), "2025.xlsx")["rows"])
    assert (added, dup, len(again)) == (0, 6, 6)
    m = us.match(first)
    assert sorted((r["bought"], r["sold"], r["qty"]) for r in m["realised"]) == [("2025-04-07", "2025-06-12", 2)] * 2 + [("2025-04-07", "2025-07-12", 2)]
    assert not m["open"] and not m["short"]


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    fx_rates.seed()
    yield built
    built["close"]()


def test_the_upload_route_keeps_the_report_note_and_nothing_personal(w):
    c = w["client"]
    h = {**PRO, "content-type": "application/octet-stream"}
    r = c.post("/money/us-tax/import?filename=2025.xlsx", headers=h, content=report())
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["read"] == 8 and j["added"] == 8 and j["duplicates"] == 0 and "realised-gains report" in j["note"]
    stored = json.dumps(db.get_setting("ustax:u-pro")) + json.dumps(j) + json.dumps(c.get("/money/us-tax", headers=PRO).json())
    assert not [x for x in FAKE if x in stored]
    again = c.post("/money/us-tax/import?filename=2025.xlsx", headers=h, content=report()).json()
    assert again["added"] == 0 and again["duplicates"] == 8 and len(again["us"]["trades"]) == 8
    bad = c.post("/money/us-tax/import?filename=2025-Schedule FA.xlsx", headers=h,
                 content=make_workbook([("Schedule FA", [["Schedule FA"], ["Country", "Amount"], ["US", 1]])]))
    assert bad.status_code == 400 and "ready-made Schedule FA table" in bad.json()["detail"]["message"]
    pdf = c.post("/money/us-tax/import?filename=2025.pdf", headers=h, content=b"%PDF-1.4 x")
    assert pdf.status_code == 400 and "PDFs can't be read" in pdf.json()["detail"]["message"]
