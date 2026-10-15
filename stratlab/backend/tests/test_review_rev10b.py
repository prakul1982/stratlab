"""Review rev10b: the tax and money reports. Section 234B with self-assessment tax (234B(2)) and 234C's proviso for gains
after 15 March; F&O totals from two brokers; P&L columns already after charges and written "P&L"; short options closed
in the next year; F&O sheets in a tax P&L workbook; "₹ (1,234)"; US dividends at the Rule 115 rate in the estimate;
the journal against the tax report (which lines a tradebook covers, identical lines, same-day STT, a tradebook's own
charges); US sales apart from the Indian totals; Schedule FA's missing prices for a lot sold; segments by file name."""
import io
import zipfile
from datetime import date

from app import holdings_file as hf, journal as J, money_advance_tax as A, money_dividends as D, money_itr, money_ltcg as L
from app import money_us_tax as us, tax_export, tax_lots as T
from tests.xlsxmaker import make_workbook

S = J.clean_settings({})


# ---------- 1. section 234B: self-assessment tax stops the interest on what it pays ----------
def test_234b_stops_at_the_self_assessment_payment():
    s = A.schedule(2025, 100000.0, [100000.0] * 4, 0.0, [{"d": "2026-05-10", "amount": 100000.0}], date(2026, 10, 15))
    b = s["b234"]
    assert b["applies"] and b["months"] == 2 and b["interest"] == 2000 and b["until"] == "2026-05-10" and b["fully_paid"]
    assert "fully paid in May 2026, so the interest stops there" in s["steps"][-1]
    # fully paid: the figure doesn't grow with time
    later = A.schedule(2025, 100000.0, [100000.0] * 4, 0.0, [{"d": "2026-05-10", "amount": 100000.0}], date(2027, 6, 1))
    assert later["b234"]["interest"] == 2000


def test_234b_runs_on_what_is_left_after_a_part_payment():
    # 50,000 paid in May: 1,00,000 for April and May, then 50,000 from June to October (today)
    s = A.schedule(2025, 100000.0, [100000.0] * 4, 0.0, [{"d": "2026-05-10", "amount": 50000.0}], date(2026, 10, 15))
    b = s["b234"]
    assert b["interest"] == 2 * 1000 + 5 * 500 and b["unpaid"] == 50000 and b["to_today"] and not b["fully_paid"]
    assert b["periods"] == [{"base": 100000, "months": 2}, {"base": 50000, "months": 5}]
    assert "still unpaid, so the interest is counted to today (October 2026)" in s["steps"][-1]
    # before the return's due date, an unpaid rest is shown as if paid by it
    early = A.schedule(2025, 100000.0, [100000.0] * 4, 0.0, [], date(2026, 4, 20))["b234"]
    assert early["months"] == 4 and early["until"] == "2026-07-31" and not early["to_today"]
    # advance tax paid by 31 March still counts for the 90% test; a payment after it is self-assessment tax
    adv, later = A.split_paid(2025, [{"d": "2026-03-31", "amount": 1}, {"d": "2026-04-01", "amount": 2}])
    assert [p["amount"] for p in adv] == [1] and [p["amount"] for p in later] == [2]


def test_itr_export_splits_payments_as_the_234b_working_does():
    g = {"fy": 2025, "paid": [{"d": "2026-03-15", "amount": 10000.0}, {"d": "2026-05-10", "amount": 5000.0}], "tds": 0, "div_year": None}
    rows = money_itr.t_tax_paid(g)["rows"]
    assert ["Advance tax", "2026-03-15", 10000.0, "", ""] in rows and ["Self-assessment tax", "2026-05-10", 5000.0, "", ""] in rows
    assert ["Total self-assessment tax", "", 5000.0, "", ""] in rows


# ---------- 2. section 234C: gains after 15 March, paid by 31 March, carry no interest ----------
def test_234c_no_march_interest_on_gains_after_15_march_paid_by_31_march():
    s = A.schedule(2025, 100000.0, [0.0, 0.0, 0.0, 0.0], 0.0, [{"d": "2026-03-25", "amount": 100000.0}], date(2026, 4, 10))
    mar = s["instalments"][3]
    assert mar["late"] == 100000 and mar["short"] == 0 and s["interest_234c"] == 0 and not s["b234"]["applies"]
    # not paid by 31 March: the proviso doesn't apply, and the March shortfall carries its interest
    s = A.schedule(2025, 100000.0, [0.0, 0.0, 0.0, 0.0], 0.0, [], date(2026, 4, 10))
    assert s["instalments"][3]["short"] == 100000 and s["interest_234c"] == 1000
    # gains before 15 March are still due by then
    s = A.schedule(2025, 100000.0, [0.0, 0.0, 0.0, 60000.0], 0.0, [{"d": "2026-03-25", "amount": 100000.0}], date(2026, 4, 10))
    assert s["instalments"][3]["short"] == 60000 and s["interest_234c"] == 600


# ---------- 3. F&O totals from two brokers ----------
def test_a_second_brokers_fo_file_is_added_not_dropped_or_swapped():
    z = b"Symbol,Exit Date,Profit\nNIFTY25APR23000CE,2025-04-10,1000\nNIFTY25MAY23000CE,2026-03-20,500\n"
    u = b"Symbol,Exit Date,Profit\nBANKNIFTY25JUN50000PE,2025-06-10,-300\n"
    u_year = b"Symbol,Exit Date,Profit\nBANKNIFTY25JUN50000PE,2025-04-05,-300\nBANKNIFTY25JUN50000PE,2026-03-25,-300\n"
    first = T.merge_business([], hf.parse_trades(z, "zerodha F&O.csv")["business"])[0]
    inside = T.merge_business(first, hf.parse_trades(u, "upstox F&O.csv")["business"])
    assert inside[1:4] == (1, 0, 0) and T.business_year(2025, inside[0])["pnl"] == 1200
    cover = T.merge_business(first, hf.parse_trades(u_year, "upstox F&O.csv")["business"])
    assert cover[1:4] == (1, 0, 0) and T.business_year(2025, cover[0])["pnl"] == 900
    # within one source the old rules hold: the same file again is the same, a full year replaces a quarter
    assert T.merge_business(first, hf.parse_trades(z, "zerodha F&O.csv")["business"])[3] == 1
    q = T.merge_business([], hf.parse_trades(u, "upstox F&O.csv")["business"])[0]
    assert T.merge_business(q, hf.parse_trades(u_year, "upstox F&O.csv")["business"])[2] == 1
    # totals saved before sources were kept match any source, as before
    legacy = [{k: v for k, v in c.items() if k != "src"} for c in first]
    assert T.merge_business(legacy, hf.parse_trades(z, "zerodha F&O.csv")["business"])[3] == 1


# ---------- 4 and 5. P&L columns: already net, and written "P&L" or "P/L" ----------
def test_a_net_pnl_column_is_already_after_charges():
    csv = b"Contract,Exit Date,Net PnL,Total Charges\nNIFTY25APR23000CE,2025-04-10,900,100\n"
    b = T.business_year(2025, hf.parse_trades(csv, "fno_pnl.csv")["business"])
    assert (b["pnl"], b["charges"], b["net"]) == (1000, 100, 900)
    # with a gross column beside it, the gross is read
    csv = b"Contract,Exit Date,Net P&L,Gross P&L,Total Charges\nNIFTY25APR23000CE,2025-04-10,900,1000,100\n"
    assert T.business_year(2025, hf.parse_trades(csv, "fno_pnl.csv")["business"])["net"] == 900


def test_pnl_columns_written_with_ampersand_or_slash():
    for h in ("Realised P&L", "Net P&L", "Realized P/L", "P&L", "Booked P&L"):
        csv = f"Contract,Exit Date,{h}\nNIFTY25APR23000CE,10-04-2025,900\n".encode()
        assert hf.parse_trades(csv, "fno_pnl.csv")["business"][0]["pnl"] == 900, h
    # the broker's figure, not one worked out from the buy and sell values
    csv = b"Contract,Exit Date,Buy Value,Sell Value,Realised P&L\nNIFTY25APR23000CE,2025-04-10,1000,2000,950\n"
    assert hf.parse_trades(csv, "fno_pnl.csv")["business"][0]["pnl"] == 950


# ---------- 6. a short option closed in the next year ----------
def test_a_short_option_lands_in_the_year_it_was_bought_back():
    csv = b"Scrip Name,Buy Date,Sell Date,Quantity,Buy Value,Sell Value,Realised P&L\nNIFTY25APR23000CE,2025-04-02,2025-03-28,75,1000,5000,4000\n"
    b = hf.parse_trades(csv, "fno_pnl.csv")["business"]
    assert [(x["fy"], x["first"], x["pnl"]) for x in b] == [(2025, "2025-04-02", 4000)]


# ---------- 7. F&O sheets in a tax P&L workbook ----------
EQ = [["Symbol", "ISIN", "Entry Date", "Exit Date", "Quantity", "Buy Value", "Sell Value", "Profit"],
      ["TCS", "INE467B01029", "2024-03-31", "2025-03-31", 10, 30000, 40000, 10000]]
FO = [["Symbol", "Entry Date", "Exit Date", "Quantity", "Buy Value", "Sell Value", "Profit"],
      ["NIFTY25APR23000CE", "2025-01-02", "2025-01-10", 75, 1000, 5000, 4000]]


def test_fo_sheets_of_a_workbook_are_read():
    wb = make_workbook([("Equity", EQ), ("F&O", FO)])
    r = hf.parse_trades(wb, "taxpnl-AB1234-2024_2025-Q1-Q4.xlsx")
    assert len(r["trades"]) == 2 and [(b["fy"], b["pnl"]) for b in r["business"]] == [(2024, 4000)]
    assert any("F&O" in f["name"] for f in r["files"])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("taxpnl-AB1234-2024_2025-Q1-Q4.xlsx", wb)
    r = hf.parse_trades(buf.getvalue(), "taxpnl.zip")
    assert len(r["trades"]) == 2 and [(b["fy"], b["pnl"]) for b in r["business"]] == [(2024, 4000)]
    # a sheet of contracts that can't be read is said, not passed over; one with totals only is left alone
    bad = make_workbook([("Equity", EQ), ("F&O", [["Thing", "Day", "Amt"], ["NIFTY25APR23000CE", "x", "y"]])])
    r = hf.parse_trades(bad, "taxpnl.xlsx")
    assert r["business"] == [] and any("F&O" in s["name"] for s in r["skipped"])
    totals = make_workbook([("Equity", EQ), ("F&O", [["Summary", ""], ["Charges", "0"]])])
    assert hf.parse_trades(totals, "taxpnl.xlsx")["skipped"] == []


def test_a_zip_with_its_own_fo_file_doesnt_count_the_workbook_sheet_too():
    wb = make_workbook([("Equity", EQ), ("F&O", FO)])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("taxpnl-AB1234-2024_2025-Q1-Q4.xlsx", wb)
        z.writestr("Tradewise Exits from 2024-04-01 - F&O.csv", "Symbol,Exit Date,Profit\nNIFTY25APR23000CE,2025-01-10,4000\n")
    r = hf.parse_trades(buf.getvalue(), "taxpnl.zip")
    assert [(b["fy"], b["pnl"]) for b in r["business"]] == [(2024, 4000)]


# ---------- 8. a rupee sign before brackets ----------
def test_rupee_sign_before_brackets_is_negative():
    assert hf.number("₹ (1,234.00)") == -1234 and hf.number("Rs.(500)") == -500 and hf.number("INR (5)") == -5
    assert hf.number("(₹1,234)") == -1234 and hf.number("₹1,234") == 1234


# ---------- 9. US dividends at Rule 115's rate in the estimate ----------
def test_us_dividends_in_the_estimate_use_the_rule_115_rate():
    stored = {"rows": [{"d": "2024-08-15", "sym": "AAPL", "amount": 1000.0, "cur": "USD", "src": "csv", "tds": 250.0}],
              "include": {2024: True}, "files": [], "updated_at": None}
    hist = {"sbi": {"2024-07-31": 83.6}, "rbi": {}}
    v = D.view(stored, [], [], 88.0, date(2026, 10, 15), hist=hist)
    schedule_os = us.dividends([{"d": "2024-08-15", "sym": "AAPL", "amount": 1000.0, "tds": 250.0}], hist, 2024, 0.3)["inr"]
    assert D.for_total(v)[2024] == schedule_os == 83600
    # it doesn't move with today's rate
    assert D.for_total(D.view(stored, [], [], 95.0, date(2026, 10, 15), hist=hist))[2024] == 83600
    assert D.events(v, stored, [], 88.0, 2024, hist=hist) == [("2024-08-15", 83600.0)]
    # dividends still to come stay at today's rate
    ahead = [{"d": "2026-12-01", "ex": "2026-12-01", "sym": "AAPL", "qty": 10, "ps": 1.0, "amount": 10.0, "cur": "USD", "label": "Dividend"}]
    assert D.view(stored, [], ahead, 88.0, date(2026, 10, 15), hist=hist)["ahead_total"] == 880


# ---------- 10 to 13. the journal against the tax report ----------
def journal(trades):
    g = J.from_tax(trades)
    fills, lines = J.reconcile(g["fills"], g["lines"])
    a, _, _ = J.pair_fills(fills, S, date(2026, 10, 4), {})
    return a + J.line_trades(lines, S)


def tax(trades):
    c = T.compute(trades, {}, {}, "2026-10-04")
    return round(sum(r["gain"] for r in c["realised"]) + sum(i["pnl"] for i in c["intraday"]), 2)


def test_journal_keeps_a_pnl_line_the_tradebook_only_spans():
    pid = "pnl:2025-06-02:2025-07-01:50:500.0000:600.0000"
    tr = [{"d": "2025-05-02", "side": "B", "qty": 100, "price": 1000, "symbol": "ITC", "src": "trades", "t": "10:00:00", "charges": 0.0},
          {"d": "2025-08-04", "side": "S", "qty": 100, "price": 1100, "symbol": "ITC", "src": "trades", "t": "10:00:00", "charges": 0.0},
          {"d": "2025-06-02", "side": "B", "qty": 50, "price": 500, "symbol": "ITC", "src": "pnl", "tid": pid + ":b", "charges": 0.0},
          {"d": "2025-07-01", "side": "S", "qty": 50, "price": 600, "symbol": "ITC", "src": "pnl", "tid": pid + ":s", "charges": 0.0}]
    ts = journal(tr)
    assert sum(t["gross"] for t in ts) == 15000 == tax(tr)
    assert sorted(t["src"] for t in ts) == ["pnl", "tradebook"]


def test_journal_drops_a_line_the_tradebook_has_and_charges_it_as_the_tax_report():
    pid = "pnl:2025-05-02:2025-08-04:100:1000.0000:1100.0000"
    tr = [{"d": "2025-05-02", "side": "B", "qty": 100, "price": 1000, "symbol": "ITC", "src": "trades", "t": "10:00:00"},
          {"d": "2025-08-04", "side": "S", "qty": 100, "price": 1100, "symbol": "ITC", "src": "trades", "t": "10:00:00"},
          {"d": "2025-05-02", "side": "B", "qty": 100, "price": 1000, "symbol": "ITC", "src": "pnl", "tid": pid + ":b", "charges": 0.0},
          {"d": "2025-08-04", "side": "S", "qty": 100, "price": 1100, "symbol": "ITC", "src": "pnl", "tid": pid + ":s", "charges": 300.0}]
    ts = journal(tr)
    assert [(t["src"], t["net"], t["charges_from"]) for t in ts] == [("tradebook", 9700.0, "file")] and tax(tr) == 9700


def test_journal_counts_two_identical_pnl_lines():
    pid = "pnl:2025-05-02:2025-08-04:10:1000.0000:1100.0000"
    line = [{"d": "2025-05-02", "side": "B", "qty": 10, "price": 1000, "symbol": "ITC", "src": "pnl", "tid": pid + ":b", "charges": 0.0},
            {"d": "2025-08-04", "side": "S", "qty": 10, "price": 1100, "symbol": "ITC", "src": "pnl", "tid": pid + ":s", "charges": 5.0}]
    merged = T.merge([], line + [dict(x) for x in line])[0]
    g = J.from_tax(merged)
    assert len(g["lines"]) == 2
    assert sum(t["net"] for t in J.line_trades(g["lines"], S)) == 1990 == tax(merged)


def test_journal_same_day_pnl_line_takes_off_the_stt_the_tax_report_does():
    pid = "pnl:2025-06-02:2025-06-02:100:1000.0000:1010.0000"
    tr = [{"d": "2025-06-02", "side": "B", "qty": 100, "price": 1000, "symbol": "ITC", "src": "pnl", "tid": pid + ":b", "charges": 0.0},
          {"d": "2025-06-02", "side": "S", "qty": 100, "price": 1010, "symbol": "ITC", "src": "pnl", "tid": pid + ":s", "charges": 20.0}]
    ts = journal(tr)
    assert [(t["segment"], round(t["net"], 2)) for t in ts] == [("eq_intraday", 954.75)] and tax(tr) == 954.75
    # the file's STT when it has one
    tr[1] = {**tr[1], "stt": 10.0}
    assert round(journal(tr)[0]["net"], 2) == 970 == tax(tr)


def test_journal_uses_a_tradebooks_own_charges():
    tr = [{"d": "2025-05-02", "side": "B", "qty": 100, "price": 1000, "symbol": "ITC", "src": "trades", "charges": 150.0, "stt": 100.0, "t": "10:00:00"},
          {"d": "2025-08-04", "side": "S", "qty": 100, "price": 1100, "symbol": "ITC", "src": "trades", "charges": 150.0, "stt": 110.0, "t": "10:00:00"}]
    ts = journal(tr)
    assert [(t["net"], t["charges_from"]) for t in ts] == [(9700.0, "file")] and tax(tr) == 9700
    # kept when a tradebook is uploaded to the journal itself
    assert J._fill({**tr[0], "symbol": "ITC"})["charges"] == 150 and J._fill({**tr[0], "symbol": "ITC"})["stt"] == 100
    # intraday from a tradebook: charges and the STT, as the tax report's intraday
    day = [{"d": "2025-06-02", "side": "B", "qty": 100, "price": 1000, "symbol": "ITC", "src": "trades", "charges": 10.0, "t": "10:00:00"},
           {"d": "2025-06-02", "side": "S", "qty": 100, "price": 1010, "symbol": "ITC", "src": "trades", "charges": 10.0, "stt": 25.0, "t": "11:00:00"}]
    assert round(journal(day)[0]["net"], 2) == 955 == tax(day)
    # no charges columns at all: the published rates, as before
    bare = [{**t, "charges": 0.0} for t in tr]
    for t in bare:
        t.pop("stt")
    assert journal(bare)[0]["charges_from"] == "rates"


# ---------- section 2 ----------
def us_row(gain, term="ST", sold="2025-06-10"):
    return {"key": "AAPL", "bought": "2024-01-10", "sold": sold, "fy": 2025, "qty": 1, "cost": 1000.0, "sale": 1000.0 + gain,
            "gain": gain, "term": term, "bonus": False, "gf": None, "bucket": "st_us" if term == "ST" else "lt_us", "src": "us", "rate": None}


def test_us_sales_are_apart_from_the_indian_share_totals():
    c = T.compute([{"d": "2025-01-10", "side": "B", "qty": 10, "price": 100, "sym": "ABC"},
                   {"d": "2025-06-10", "side": "S", "qty": 10, "price": 110, "sym": "ABC"}], today="2026-10-15")
    y = T.year(2025, c["realised"] + [us_row(500)], c["intraday"])
    assert y["stcg"]["net"] == 100 and y["foreign"]["st"]["net"] == 500 and y["foreign"]["lt"]["net"] == 0
    assert sum(b["gains"] for b in y["buckets"]) == 600            # the tax still counts both
    assert T.year(2025, c["realised"], c["intraday"])["foreign"] is None
    # the ITR summary and the CSV label them apart
    yt = T.with_total(y, [], None)
    g = {"fy": 2025, "y": yt, "div_lines": [], "us_div": None, "paid": [], "tds": 0, "fa": None}
    lines = dict(money_itr.summary(g))
    assert lines["Short-term gains, Indian shares and funds (net)"] == "₹100" and lines["US shares: short-term gains (net)"] == "₹500"
    assert dict(tax_export.summary_lines(yt))["US shares: short-term gains (net)"] == "₹500"


def test_ltcg_tracker_keeps_us_long_term_gains_apart():
    c = T.compute([{"d": "2024-01-10", "side": "B", "qty": 10, "price": 100, "sym": "ABC"},
                   {"d": "2026-06-10", "side": "S", "qty": 10, "price": 110, "sym": "ABC"}], today="2026-10-15")
    c["realised"].append({**us_row(700, "LT", "2026-06-10"), "fy": 2026, "bought": "2023-01-10"})
    ex = L.tracker(c, {}, "2026-10-15")["exemption"]
    assert ex["realised_lt_net"] == 100 and ex["realised_us_lt_net"] == 700


def test_schedule_fa_lists_a_lot_sold_in_the_year_with_no_prices():
    trades = [{"d": "2024-03-04", "side": "B", "sym": "XYZ", "qty": 10, "price": 50.0, "fees": 0},
              {"d": "2025-08-04", "side": "S", "sym": "XYZ", "qty": 10, "price": 60.0, "fees": 0}]
    hist = {"sbi": {"2024-03-04": 82.5, "2025-08-04": 87.0, "2025-12-31": 89.9}, "rbi": {}}
    fa = us.schedule_fa(2025, trades, {}, {}, {}, hist)
    assert fa["rows"][0]["peak"] is None and fa["missing_prices"] == ["XYZ"]


def test_commodity_and_currency_files_keep_their_own_segment():
    assert hf.business_kind("MCX Commodity Futures P&L.csv") == "commodity"
    assert hf.business_kind("commodity_options_pnl.csv") == "commodity"
    assert hf.business_kind("Currency Futures and Options.csv") == "currency"
    assert hf.business_kind("Currency Derivatives.csv") == "currency"
    assert hf.business_kind("F&O.csv") == "fno" and hf.business_kind("Index Options.csv") == "fno"
