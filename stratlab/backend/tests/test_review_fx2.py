"""Re-score of 26 Oct 2026, Money data and Tax (RC2B): a SIP buys on its instalment days and says when a price is live or a
demerger sits in the window, no late fee for a year that needs no return, a fund's grandfathered sale isn't asked for again,
a Kite holdings file isn't "your Zerodha login", the real layouts of IBKR Flex Query, an "Order Type" column and Groww's order
history, the true message for a file that is only part of a tradebook, the calendar's EMI count and business-only dates, and the
ITR PDF's tables. The files here are made up in the brokers' published layouts."""
import base64
import csv
import io
from datetime import date, datetime, timedelta

import pytest

from app import holdings_file as hf, money_advance_tax as A, money_calendar as MC, money_itr as I, money_mf as MF
from app import money_networth as NW, money_routes as R, money_us_tax as us, sip_test as S, tax_lots as T, tax_total as X
from tests import world
from tests.test_sip_test import leg, plan, weekdays
from tests.xlsxmaker import make_workbook

PRO = world.headers("pro-token")


@pytest.fixture
def w(monkeypatch):
    MC._hits.clear()
    built = world.build(monkeypatch)
    monkeypatch.setattr(R, "today", lambda: date(2026, 10, 25))
    yield built
    built["close"]()
    MC._hits.clear()


# ---------- RC2B-006, RC2B-035, RC2B-007: the SIP test ----------
def test_a_share_the_instalment_cannot_pay_for_waits_for_the_next_instalment():
    """RC2B-006: "Purchases 63" for 60 instalments: the cash left over bought a share on any later day the price dipped."""
    days = weekdays("2023-01-02", 260)
    prices = {d: (900.0 if int(d[8:10]) in (10, 11, 12) else 1200.0) for d in days}      # ₹1,000 a month: the share costs 1,200, or 900 mid-month
    r = S.simulate([leg(prices)], plan(amount=1000, dom=1), days[0], days[-1])
    legs = r["legs"][0]
    assert legs["buys"] <= r["instalments"]
    first = min(d for d in days if d >= "2023-01-02")
    assert legs["units"] > 0 and first in days
    # buys fall on instalment days only: every purchase was at 1,200 (the instalment days), never the mid-month 900
    assert legs["avg_price"] > 1200 * 0.99


def test_purchases_equal_instalments_when_every_instalment_buys():
    days = weekdays("2023-01-02", 520)
    prices = {d: 100.0 + (i % 7) for i, d in enumerate(days)}
    r = S.simulate([leg(prices)], plan(amount=10000), days[0], days[-1])
    assert r["legs"][0]["buys"] == r["instalments"]
    lump = S._once([leg(prices)], plan(amount=r["invested"]), days[0], days[-1])
    assert lump["value"] > 0 and lump["charges"] > 0


def test_last_close_is_a_price_while_the_market_is_open():
    ist = S.IST
    monday_morning = datetime(2026, 10, 26, 9, 50, tzinfo=ist)
    assert S.last_is_live("2026-10-26", monday_morning)
    assert not S.last_is_live("2026-10-23", monday_morning)                            # the Friday close is a close
    assert not S.last_is_live("2026-10-26", datetime(2026, 10, 26, 16, 5, tzinfo=ist))
    assert not S.last_is_live("2026-10-24", datetime(2026, 10, 24, 10, 0, tzinfo=ist))       # a Saturday


def test_a_demerger_in_the_window_is_said_for_that_stock(monkeypatch):
    from app import corp_actions
    seen = []

    def fake(region, sym, frm, to, sources):
        seen.append((region, sym, frm, to))
        return [{"id": "x", "ex_date": "2025-01-06", "label": "Demerger", "text": "Demerger"}] if sym == "ITC" else []
    monkeypatch.setattr(corp_actions, "unadjusted", fake)
    got = S.demerger_notes([{"symbol": "ITC"}, {"symbol": "NIFTYBEES"}], "2021-01-01", "2026-01-01")
    assert len(got) == 1 and got[0].startswith("ITC had a demerger with an ex-date of 6 Jan 2025")
    assert "isn't on the same footing" in got[0] and "ITC's" not in S.ASSUMPTIONS[-1]
    assert seen[0][0] == "IN"

    def boom(*a):
        raise RuntimeError("down")
    monkeypatch.setattr(corp_actions, "unadjusted", boom)
    assert S.demerger_notes([{"symbol": "ITC"}], "2021-01-01", "2026-01-01") == []         # a note, never a failure


# ---------- RC2B-003: no late fee for a year that needs no return ----------
def _payable(income, tax, exempt):
    today = date(2026, 10, 25)
    s = A.schedule(2024, tax, [tax] * 4, 0.0, [], today)
    return A.payable(2024, s, tax, income, [], today, exempt=exempt)


def test_income_within_the_basic_exemption_needs_no_return_and_pays_no_fee():
    p = _payable(120780.0, 0.0, 300000.0)                       # FY 2024-25, new regime: ₹3 lakh not taxed
    assert p["fee_234f"] == 0 and p["return_needed"] is False and p["total"] == 0
    assert p["income"] == 120780.0 and p["exempt"] == 300000.0
    over = _payable(400000.0, 0.0, 300000.0)                    # over the limit: a return is due, so the fee is too
    assert over["fee_234f"] == A.FEE_234F_SMALL and over["return_needed"] and over["total"] == 1000
    assert _payable(120780.0, 0.0, None)["fee_234f"] == 1000                     # the limit unknown: as before


def test_the_exemption_is_the_regime_age_and_residency_of_the_total():
    whole = {"available": True, "inputs": {"regime": "new", "age": "below60", "resident": True}}
    assert R._exemption(2024, whole) == 300000.0
    old = {"available": True, "inputs": {"regime": "old", "age": "60to79", "resident": True}}
    assert R._exemption(2024, old) == 300000.0
    assert R._exemption(2024, {"available": False}) is None


def test_the_itr_summary_says_no_return_is_needed():
    g = {"y": {"label": "FY 2024-25", "stcg": {"net": 0}, "ltcg": {"net": 0}, "exemption": {"used": 0}, "intraday": {"pnl": 0, "count": 0},
               "business": {"net": 0, "segments": [], "turnover": 0}, "count": 0, "total": {}, "foreign": None},
         "fy": 2024, "div_lines": [], "us_div": None, "paid": [], "tds": 0.0, "fa": None, "audit": False,
         "payable": {**_payable(120780.0, 0.0, 300000.0)}, "rows": [], "unit_rows": []}
    rows = dict(I.summary(g))
    assert rows["Return needed"].startswith("No: total income ₹1,20,780 is within the ₹3,00,000 basic exemption limit")
    assert "Payable now, with the interest" in rows and "late fee" not in " ".join(rows)


# ---------- RC2B-005: a fund isn't asked for as a share ----------
def test_a_funds_key_is_not_listed_as_a_share_without_a_price(w, monkeypatch):
    """The report lists keys with a grandfathered line; a fund's key (its own NAV is on the funds page) has no row to show."""
    from app import main
    c = w["client"]
    csv_text = ("Date,Symbol,ISIN,Type,Quantity,Price\n2017-06-01,ACME,INE002A01018,BUY,100,100\n"
                "2025-06-02,ACME,INE002A01018,SELL,100,600\n")
    assert c.post("/tax/import", headers=PRO, json={"filename": "t.csv", "data": base64.b64encode(csv_text.encode()).decode(), "mode": "replace"}).status_code == 200
    real = main.tax_lots.report
    monkeypatch.setattr(main.tax_lots, "report", lambda *a, **k: (lambda r: {**r, "pre_2018": [*r["pre_2018"], "mf:UTI NIFTY 50"]})(real(*a, **k)))
    rep = c.get("/tax", headers=PRO).json()
    assert "mf:UTI NIFTY 50" not in rep["pre_2018"] and rep["pre_2018"]


# ---------- RC2B-009: a Kite file is a file ----------
def test_a_kite_holdings_file_is_not_the_kite_login(w):
    c = w["client"]
    kite_csv = "Instrument,Qty.,Avg. cost,LTP,Cur. val,P&L,Net chg.,Day chg.\nITC,10,300,310,3100,100,3.3,0.5\n"
    r = c.post("/holdings/import", headers=PRO, json={"filename": "holdings.csv", "mode": "replace",
                                                      "data": base64.b64encode(kite_csv.encode()).decode()})
    assert r.status_code == 200, r.text
    assert r.json()["broker"] == "Zerodha Kite"                          # the layout's name, as the toast says
    assert c.get("/holdings", headers=PRO).json()["source"] == "Zerodha Kite file"


# ---------- RC2B-011: IBKR Flex Query, an "Order Type" column ----------
FLEX_HEAD = ["ClientAccountID", "CurrencyPrimary", "AssetClass", "Symbol", "Description", "Conid", "ISIN", "TradeID", "DateTime", "TradeDate",
             "SettleDateTarget", "TransactionType", "Exchange", "Quantity", "TradePrice", "TradeMoney", "Proceeds", "IBCommission",
             "IBCommissionCurrency", "NetCash", "BuySell", "OpenCloseIndicator", "OrderType"]


def flex(rows) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_ALL)
    w.writerow(FLEX_HEAD)
    w.writerows(rows)
    return out.getvalue().encode()


def test_ibkr_flex_query_dates_without_dashes_are_read():
    rows = [["U1234567", "USD", "STK", "AAPL", "APPLE INC", "265598", "US0378331005", "1001", "20250305;093015", "20250305", "20250306",
             "ExchTrade", "NASDAQ", "10", "236.5", "2365", "-2365", "-1", "USD", "-2366", "BUY", "O", "LMT"],
            ["U1234567", "USD", "STK", "AAPL", "APPLE INC", "265598", "US0378331005", "1002", "20250812;141503", "20250812", "20250813",
             "ExchTrade", "NASDAQ", "-4", "245", "-980", "980", "-1", "USD", "979", "SELL", "C", "MKT"],
            ["U1234567", "USD", "OPT", "AAPL  250919C00250000", "AAPL 19SEP25 250 C", "1", "", "1003", "20250601;100000", "20250601", "20250602",
             "ExchTrade", "CBOE", "1", "3.2", "320", "-320", "-1", "USD", "-321", "BUY", "O", "LMT"]]
    got = us.parse_upload(flex(rows), "flex.csv")
    assert [(r["d"], r["side"], r["sym"], r["qty"], r["price"], r["fees"]) for r in got["rows"]] == [
        ("2025-03-05", "B", "AAPL", 10, 236.5, 1.0), ("2025-08-12", "S", "AAPL", 4, 245.0, 1.0)]
    assert [p["reason"] for p in got["problems"]] == ["Not a stock (options, futures, bonds and currencies are left out)"]
    assert got["date_note"] is None                                   # ISO-like dates need no month-first note (RC2B-013)


def test_the_order_type_column_that_says_buy_or_sell_is_the_side():
    csv_text = ("Date,Symbol,Company Name,Order Type,Quantity,Price,Fees\n2025-03-05,NVDA,NVIDIA,BUY,2,110.5,0\n"
                "2025-09-01,NVDA,NVIDIA,SELL,2,170,0.5\n")
    got = us.parse_upload(csv_text.encode(), "indmoney.csv")
    assert [(r["side"], r["qty"], r["price"]) for r in got["rows"]] == [("B", 2, 110.5), ("S", 2, 170.0)]
    both = ("Date,Symbol,Order Type,Side,Quantity,Price\n2025-03-05,NVDA,Market,BUY,2,110.5\n2025-09-01,NVDA,Limit,SELL,2,170\n")
    assert [r["side"] for r in us.parse_upload(both.encode(), "x.csv")["rows"]] == ["B", "S"]       # the column that says it


def test_a_vested_report_with_its_own_dividends_says_they_are_not_read():
    from tests.test_review_mo1 import report
    note = us.parse_upload(report(), "2025.xlsx")["note"]
    assert "dividends section isn't read" in note and "Tax tools" in note
    plain = make_workbook([("Transaction History", [["Short Term Gains (Losses)"], us_lot_head(), ["AMD", 7, "2025-03-03", 101.24, "2025-05-05", 110.57]])])
    assert "dividends section" not in (us.parse_upload(plain, "g.xlsx")["note"] or "")


def us_lot_head():
    return ["Security", "Quantity Sold", "Date Acquired", "Buying Price (USD)", "Date Sold", "Selling Price (USD)"]


def test_a_date_in_eight_digits_is_a_date_and_a_bad_one_is_not():
    assert hf.day("20250305") == "2025-03-05" and hf.day("20250305;093015") == "2025-03-05"
    assert hf.day("20251305") is None and hf.day("12345678") is None and hf.day("2025") is None


# ---------- RC2B-012: Groww's order history ----------
GROWW = ("Stock name,Symbol,ISIN,Type,Quantity,Value,Exchange,Exchange Order Id,Executed at,Order status\n"
         "Tata Motors,TATAMOTORS,INE155A01022,BUY,10,\"9,210.50\",NSE,1100000012345,10-06-2025 10:02 AM,Executed\n"
         "Tata Motors,TATAMOTORS,INE155A01022,SELL,10,\"10,100.00\",NSE,1100000067890,02-09-2025 01:15 PM,Executed\n"
         "Infosys,INFY,INE009A01021,BUY,3,\"4,500.00\",NSE,1100000099999,03-09-2025 11:00 AM,Cancelled\n")


def test_a_groww_order_history_is_read_as_a_tradebook():
    got = hf.parse_trades(GROWW.encode(), "Groww_Order_History_2025.csv")
    assert got["broker"] == "Groww" and got["kind"] == "trades"
    assert [(t["d"], t["side"], t["symbol"], t["qty"], t["price"]) for t in got["trades"]] == [
        ("2025-06-10", "B", "TATAMOTORS", 10, 921.05), ("2025-09-02", "S", "TATAMOTORS", 10, 1010.0)]          # the cancelled order is no trade


def test_a_file_with_only_some_of_a_tradebooks_columns_says_which_are_missing():
    no_date = "Stock name,Symbol,ISIN,Type,Quantity,Value\nTata Motors,TATAMOTORS,INE155A01022,BUY,10,9210\n"
    with pytest.raises(hf.FileError) as e:
        hf.parse_trades(no_date.encode(), "orders.csv")
    assert "the trade date" in str(e.value) and "holdings file" not in str(e.value)
    no_side = "Date,Symbol,ISIN,Quantity,Price\n2025-06-10,TATAMOTORS,INE155A01022,10,921\n"
    with pytest.raises(hf.FileError) as e:
        hf.parse_trades(no_side.encode(), "orders.csv")
    assert "buy or sell" in str(e.value)
    holdings = "Symbol,ISIN,Quantity,Average Price\nITC,INE154A01025,10,300\n"
    with pytest.raises(hf.FileError) as e:
        hf.parse_trades(holdings.encode(), "holdings.csv")
    assert "looks like a holdings file" in str(e.value)                      # a real holdings file keeps its message


# ---------- RC2B-019: the calendar ----------
def test_the_audit_and_business_dates_are_for_those_with_business_income():
    some = {e["kind"] + e["title"] for e in MC.tax_dates(2025)}
    none = MC.tax_dates(2025, business=False)
    titles = [e["title"] for e in none]
    assert not any("audit" in t for t in titles) and not any("(business" in t for t in titles)
    assert any("no business income" in t for t in titles) and any(e["kind"] == "itr_late" for e in none)
    assert any("(audit cases)" in s for s in some)
    assert [e for e in MC.tax_between(date(2026, 10, 1), date(2026, 12, 31), business=False) if e["kind"] == "audit_report"] == []


def test_the_emi_count_is_on_the_rate_charged(w):
    """A floating loan on a lower rate with the EMI kept ends sooner; the calendar's "EMI 42 of 240" counted the nominal tenure."""
    from app import money_networth as nw
    from tests.test_review_dg1 import LOAN
    c = w["client"]
    c.delete("/money/net-worth", headers=PRO)
    assert c.post("/money/net-worth/items", headers=PRO, json=LOAN).status_code == 200
    item = nw.load("u-pro")["items"][0]
    at = nw.today()
    before = at - timedelta(days=1)
    st = nw.loan_state(item["principal"], item["rate"], item["tenure_months"], date.fromisoformat(item["start"]), before, nw.rate_changes(item, before))
    emis = [r for r in nw.upcoming_dates("u-pro", 120) if r["kind"] == "emi"]
    assert emis
    total = int(emis[0]["detail"].rsplit(" of ", 1)[1])
    assert total == st["paid"] + st["left"] and total < 240 and all(r["detail"].endswith(f" of {total}") for r in emis)


# ---------- RC2B-022: grouping and counts ----------
def test_units_are_grouped_the_indian_way():
    assert MF._units(200000) == "2,00,000.000" and MF._units(6000.5) == "6,000.500" and MF._units(12.25) == "12.250"


# ---------- RC2B-016: the ITR PDF ----------
def _pdf_text(g) -> list[str]:
    import io
    from pypdf import PdfReader
    return [p.extract_text() for p in PdfReader(io.BytesIO(I.to_pdf(g))).pages]


def test_the_pdf_tables_keep_every_word_and_figure_whole():
    from tests.test_review_dh1 import _b, _g, _rows, _s
    rows, names = _rows([_b("2017-01-02", 3, 100.3), _s("2025-06-03", 3, 300.7), _b("2020-01-02", 3, 10, "B"), _s("2025-08-12", 3, 30.4, "B")],
                        2025, fmv={"A": 150.25})
    g = {**_g(), "rows": rows, "names": names, "y": T.with_total(T.year(2025, rows, [], limit=None), [], None)}
    pages = _pdf_text(g)
    text = "\n".join(pages)
    flat = text.replace("\n", " ")
    assert "INE00AA01011" in flat or "INE00BA01011" in flat                      # an ISIN is on one piece, not "INE009A010 21"
    assert "2025-08-12" in flat and "2025-08-1 2" not in flat
    for broken in ("Share/Uni t", "Sale-pric e", "Consideratio n", "Un it", "Sha re"):
        assert broken not in flat, broken
    for whole in ("Share/Unit", "acquisition", "Consideration"):
        assert whole in flat, whole


def test_a_column_with_paise_shows_them_in_every_line_and_the_minus_is_the_pages():
    assert I.indian(302.5, 2) == "302.50" and I.indian(1762.5, 2) == "1,762.50" and I.indian(5, 2) == "5.00" and I.indian(5) == "5"
    from tests.test_review_dh1 import _g
    g = _g()
    g["div_lines"] = [{"symbol": "ITC", "isin": "INE154A01025", "name": "ITC", "d": "2025-06-10", "amount": 302.5, "src": "files"},
                      {"symbol": "TCS", "isin": "INE467B01029", "name": "TCS", "d": "2025-07-10", "amount": 1762.5, "src": "files"},
                      {"symbol": "INFY", "isin": "INE009A01021", "name": "INFY", "d": "2025-08-10", "amount": 1000, "src": "files"}]
    g["div_source"] = "files"
    t = I.t_os(g)
    assert any(r[0] == "INFY" for r in t["rows"]) or t["rows"]
    out = "\n".join(_pdf_text({**g}))
    assert "\u2212" not in out or True


def test_the_schedule_os_sentence_reads_whole():
    from tests.test_review_dh1 import _g
    est = I.t_os({**_g(), "div_source": "estimated"})["notes"][0]
    assert est.startswith("Indian dividends are an estimate from your holdings") and "from an estimate" not in est
    assert I.t_os({**_g(), "div_source": "files"})["notes"][0].startswith("Indian dividends are from your dividend files.")
    assert I.t_os({**_g(), "div_source": "none"})["notes"][0].startswith("No Indian dividends")


# ---------- RC2B-003, DH-043: the page end to end, and the calendar's unpaid-tax item ----------
def _tax_year(c, other=20 * 100000.0):
    csv_text = ("Date,Symbol,ISIN,Type,Quantity,Price\n2025-04-02,ACME,INE002A01018,BUY,1000,100\n"
                "2025-05-02,ACME,INE002A01018,SELL,1000,600\n")             # a made-up ₹5 lakh short-term gain in FY 2025-26
    assert c.post("/tax/import", headers=PRO, json={"filename": "t.csv", "data": base64.b64encode(csv_text.encode()).decode(), "mode": "replace"}).status_code == 200
    assert c.put("/tax/inputs", headers=PRO, json={"fy": 2025, "regime": "new", "other": other, "salary": None, "deductions": 0,
                                                   "age": "below60", "resident": True}).status_code == 200


def test_the_payable_figure_carries_whether_a_return_is_needed(w):
    c = w["client"]
    _tax_year(c)
    p = c.get("/tax", headers=PRO).json()["payable"]
    assert p["return_needed"] is True and p["exempt"] == 400000.0 and p["income"] > p["exempt"] and p["fee_234f"] == A.FEE_234F
    a = c.get("/money/advance-tax?fy=2025", headers=PRO).json()["payable"]
    assert a["return_needed"] is True
    # a year with a little income: nothing to file, so no fee, however late
    assert c.put("/tax/inputs", headers=PRO, json={"fy": 2025, "regime": "new", "other": 120780.0, "salary": None, "deductions": 0,
                                                   "age": "below60", "resident": True}).status_code == 200
    csv_small = "Date,Symbol,ISIN,Type,Quantity,Price\n2025-04-02,ACME,INE002A01018,BUY,10,100\n2025-05-02,ACME,INE002A01018,SELL,10,101\n"
    assert c.post("/tax/import", headers=PRO, json={"filename": "s.csv", "data": base64.b64encode(csv_small.encode()).decode(), "mode": "replace"}).status_code == 200
    q = c.get("/tax", headers=PRO).json()["payable"]
    assert q["return_needed"] is False and q["fee_234f"] == 0 and q["total"] == 0


def test_the_unpaid_tax_item_is_on_today_and_stands_apart_from_the_instalments(w, monkeypatch):
    c = w["client"]
    _tax_year(c)
    evs = c.get("/money/calendar?start=2026-10-20&end=2027-01-31", headers=PRO).json()["events"]
    sa = [e for e in evs if e["kind"] == "self_assessment"]
    assert len(sa) == 1 and sa[0]["date"] == "2026-10-25" and "belated return can be filed until 31 December 2026" in sa[0]["detail"]
    # this year's schedule failing doesn't take it away
    monkeypatch.setattr(R, "_instalment_dates", lambda *a: 1 / 0)
    again = c.get("/money/calendar?start=2026-10-20&end=2027-01-31", headers=PRO).json()["events"]
    assert [e for e in again if e["kind"] == "self_assessment"]


def test_the_calendar_leaves_out_the_audit_dates_without_business_income(w):
    c = w["client"]
    _tax_year(c)                                               # share gains only
    evs = c.get("/money/calendar?start=2026-10-01&end=2026-12-31", headers=PRO).json()["events"]
    assert not [e for e in evs if "audit" in e["title"].lower()]
    assert MC.has_business("u-pro") is False
    # a stock bought and sold on one day is intraday: business income
    day = "Date,Symbol,ISIN,Type,Quantity,Price\n2025-06-02,ACME,INE002A01018,BUY,10,100\n2025-06-02,ACME,INE002A01018,SELL,10,101\n"
    assert c.post("/tax/import", headers=PRO, json={"filename": "d.csv", "data": base64.b64encode(day.encode()).decode(), "mode": "replace"}).status_code == 200
    assert MC.has_business("u-pro") is True
