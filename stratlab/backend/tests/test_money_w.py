"""The MONEY lane (Instinct deep QA, 1–2 Nov): one check for every imported line (holdings, the tax report's trades and
the trade journal), what a holdings upload says it saved, and the small money fixes."""
import base64

import pytest

from app import holdings, holdings_file as hf, journal
from tests import world

PRO = world.headers("pro-token")

# Instinct's fixture: one good line, then each kind of bad line
HOLDINGS_BAD = (b"symbol,quantity,avg_price\n"
                b"INFY,10,1500\n"
                b"SBIN,notanumber,abc\n"
                b",7,500\n"
                b"TATAMOTORS,-5,800\n"
                b"FAKESYM123,3,100\n")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


def reasons(problems):
    return {p["line"]: p["reason"] for p in problems}


def test_every_bad_holdings_line_is_reported_with_its_line_and_why():
    got = hf.parse(HOLDINGS_BAD, "mine.csv")
    assert [(r["line"], r["symbol"], r["qty"], r["avg"]) for r in got["rows"]] == [(2, "INFY", 10, 1500), (6, "FAKESYM123", 3, 100)]
    why = reasons(got["problems"])
    assert why[3] == 'The quantity "notanumber" isn\'t a number.'           # vanished before (Instinct)
    assert why[4] == "No stock symbol, ISIN or name on this line."         # vanished before (Instinct)
    assert why[5].startswith("The quantity is below 0")
    assert len(why) == 3                                                   # FAKESYM123 is read; the matcher says it's unknown


def test_header_variants_are_read_alike():
    for head in (b"symbol,quantity,avg_price", b"Symbol,Quantity,Average Price", b"SYMBOL,QTY,AVG", b"Ticker,Shares Held,Avg Buy Cost",
                 b"symbol , quantity , average"):
        got = hf.parse(head + b"\nINFY,10,1500\n", "mine.csv")
        assert [(r["symbol"], r["qty"], r["avg"]) for r in got["rows"]] == [("INFY", 10, 1500)], head


def test_blank_lines_totals_notes_and_repeated_headers_stay_unseen():
    got = hf.parse(b"Symbol,Quantity,Average price\nINFY,10,1500\n,,\nSymbol,Quantity,Average price\nTotal,10,\n"
                   b"Prices are indicative,,\n", "mine.csv")
    assert [r["symbol"] for r in got["rows"]] == ["INFY"] and got["problems"] == []


def test_the_upload_reports_the_file_stocks_saved_and_each_line_left_out(w):
    c = w["client"]
    holdings.save("u-pro", [{"symbol": "TCS", "exchange": "NSE", "name": "TCS", "qty": 2.0, "avg": 3000.0}], "Manual")
    r = c.post("/holdings/import", headers=PRO, json={"filename": "mine.csv", "data": base64.b64encode(HOLDINGS_BAD).decode(), "mode": "add"})
    assert r.status_code == 200, r.text
    body = r.json()
    # "N saved" is the file's stocks saved (adding said the total of every holding), and each one is named
    assert body["saved"] and body["imported"] == 1
    assert [(x["symbol"], x["qty"]) for x in body["saved_lines"]] == [("INFY", 10)]
    assert {u["line"] for u in body["unmatched"]} == {3, 4, 5, 6} and body["unmatched_count"] == 4
    assert {x["symbol"] for x in body["holdings"]["rows"]} == {"INFY", "TCS"}


def test_a_file_with_nothing_usable_saves_nothing(w):
    c = w["client"]
    holdings.save("u-pro", [{"symbol": "TCS", "exchange": "NSE", "name": "TCS", "qty": 2.0, "avg": 3000.0}], "Manual")
    bad = b"Symbol,Quantity,Average price\nSBIN,notanumber,abc\n,7,500\n"
    r = c.post("/holdings/import", headers=PRO, json={"filename": "bad.csv", "data": base64.b64encode(bad).decode(), "mode": "replace"})
    assert r.status_code == 200, r.text
    assert not r.json()["saved"] and r.json()["imported"] == 0 and r.json()["saved_lines"] == []
    assert [i["symbol"] for i in holdings.load("u-pro")["items"]] == ["TCS"]


TRADES = (b"Date,Symbol,Type,Quantity,Price\n"
          b"2024-05-02,INFY,Buy,10,1400\n"
          b"2024-05-03,,Buy,7,500\n"
          b"2024-05-04,TCS,Buy,notanumber,3000\n"
          b"2099-01-01,WIPRO,Buy,5,400\n"
          b"31/02/2024,SBIN,Buy,5,600\n")


def test_tax_trades_say_each_bad_line_and_refuse_a_future_date():
    got = hf.parse_trades(TRADES, "trades.csv")
    assert [(t["line"], t["symbol"]) for t in got["trades"]] == [(2, "INFY")]
    why = reasons(got["problems"])
    assert why[3] == "No stock symbol, ISIN or name on this line."
    assert why[4] == 'The quantity "notanumber" isn\'t a number.'
    assert why[5] == "The trade date (1 Jan 2099) is after today, so it's left out."     # was saved: "Held -26,359 days"
    assert why[6] == "The trade date couldn't be read."


def test_a_tax_pnl_line_sold_in_the_future_is_refused():
    pnl = (b"Symbol,ISIN,Quantity,Buy Date,Buy Price,Sell Date,Sell Price\n"
           b"INFY,INE009A01021,10,2023-04-03,1400,2024-05-02,1500\n"
           b"TCS,INE467B01029,5,2023-04-03,3000,2099-01-01,3500\n")
    got = hf.parse_trades(pnl, "pnl.csv")
    assert {t["symbol"] for t in got["trades"]} == {"INFY"}
    assert reasons(got["problems"])[3] == "The buy or sale date (1 Jan 2099) is after today, so it's left out."


def test_the_journal_uses_the_same_check():
    got = journal.parse(TRADES, "trades.csv")
    why = {p["line"]: p["reason"] for p in got["problems"]}
    assert why[3] == "No stock symbol, ISIN or name on this line."
    assert why[4] == 'The quantity "notanumber" isn\'t a number.'
    assert why[5] == "The trade date (1 Jan 2099) is after today, so it's left out."
    assert len(got["fills"]) == 1


def test_adding_a_stock_already_held_merges_and_says_so(w):
    c = w["client"]
    holdings.save("u-pro", [{"symbol": "TCS", "exchange": "NSE", "name": "TCS", "qty": 5.0, "avg": 3000.0}], "Manual")
    r = c.put("/holdings", headers=PRO, json={"changes": [{"op": "add", "symbol": "TCS", "qty": 10, "avg": 3300, "market": "IN"}]})
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["holdings"]["rows"] if x["symbol"] == "TCS")
    assert row["qty"] == 15 and abs(row["avg"] - 3200) < 1e-6                     # the merge stays: weighted by quantity
    assert r.json()["notes"] == ["TCS was already held (5), so the 10 are added to it: 15 now."]
