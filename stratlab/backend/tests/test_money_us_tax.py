"""US stocks in Indian tax: the SBI TT buying rate on the right dates (Rule 115, with the step back over holidays and
the labelled RBI fallback), the 24-month rule and the rates either side of 23 Jul 2024, first in first out through a
split, the foreign tax credit, Schedule FA's peak and closing values per lot, reading a US broker's file, the tax
report with US sales set off against Indian ones, the page, the plans and deleting. Every rate here is made up."""
import base64
from datetime import date

import pytest

from app import db, money_fx as fx, money_us_tax as us
from app.config import settings
from tests import fx_rates, world

PRO, FREE = world.headers("pro-token"), world.headers("free-token")


def hist(**kw):
    return fx_rates.history(**kw)


def tr(d, side, sym, qty, price, fees=0.0):
    return {"d": d, "side": side, "sym": sym, "qty": qty, "price": price, "fees": fees}


# ---------- the rate for a date ----------
def test_parse_sbi_keeps_the_tt_buying_rate_and_drops_empty_sheets():
    text = ("DATE,PDF FILE,TT BUY,TT SELL,BILL BUY\n2020-01-04 09:00,x.pdf,0.00,0.00,71.29\n2020-01-06 09:00,x.pdf,71.65,72.50,71.59\n"
            "2025-12-31 09:18,x.pdf,89.47,90.32,89.4\n2025-12-31 15:00,x.pdf,89.50,90.35,89.4\nbad,line,,,\n")
    assert fx.parse_sbi(text) == {"2020-01-06": 71.65, "2025-12-31": 89.50}           # the later sheet of a day wins
    rbi = fx.parse_rbi("date,AED,EUR,GBP,IDR,JPY,USD\n1998-08-25,,,69.57,,29.46,42.50\n2019-01-31,,,,,,71.0749\n2019-02-01,,,,,,\n")
    assert rbi == {"2019-01-31": 71.0749}                                              # kept from 2005, blanks dropped


def test_rule115_uses_the_last_day_of_the_month_before():
    assert fx.month_end_before("2025-08-14") == "2025-07-31"
    assert fx.month_end_before("2025-03-01") == "2025-02-28" and fx.month_end_before("2024-03-31") == "2024-02-29"
    assert fx.month_end_before("2025-01-10") == "2024-12-31"
    h = hist()
    got = fx.rule115(h, "2025-08-14")
    assert got["on"] == "2025-07-31" and got["rate"] == fx_rates.rate(date(2025, 7, 31)) and got["source"] == fx.SBI and not got["fallback"]


def test_a_holiday_steps_back_to_the_last_published_rate():
    h = hist()
    # 31 Aug 2025 was a Sunday: the rate is Friday 29 Aug's, and it says so
    got = fx.rule115(h, "2025-09-10")
    assert got["asked"] == "2025-08-31" and got["on"] == "2025-08-29" and got["rate"] == fx_rates.rate(date(2025, 8, 29))
    del h["sbi"]["2025-08-29"]                                          # a bank holiday too: one more day back
    assert fx.rule115(h, "2025-09-10")["on"] == "2025-08-28"


def test_rbi_reference_rate_is_the_labelled_fallback():
    h = hist()
    got = fx.rule115(h, "2019-06-12")                                   # before SBI's sheets were archived
    assert got["on"] == "2019-05-31" and got["fallback"] and got["source"] == fx.RBI and got["rate"] == fx_rates.rate(date(2019, 5, 31), 69.5)
    gap = {"sbi": {k: v for k, v in h["sbi"].items() if not "2025-06-15" <= k <= "2025-07-05"}, "rbi": h["rbi"]}
    assert fx.rate_on(gap, "2025-06-30")["fallback"]                    # more than a week without an SBI rate
    assert fx.rate_on({"sbi": {}, "rbi": {}}, "2025-06-30") is None


# ---------- the holding period and the rates ----------
def test_long_term_after_more_than_24_months():
    assert not us.long_term("2023-01-15", "2025-01-15")                 # exactly 24 months: still short term
    assert us.long_term("2023-01-15", "2025-01-16")
    assert not us.long_term("2024-02-29", "2026-02-28") and us.long_term("2024-02-29", "2026-03-01")
    assert not us.long_term("2024-06-01", "2025-06-02")                  # a year is long term for Indian shares, not here


def test_rates_either_side_of_23_july_2024():
    assert us.classify("2021-01-04", "2024-09-02") == {"term": "LT", "bucket": "lt_us", "rate": 0.125, "indexed": False}
    assert us.classify("2021-01-04", "2024-07-22") == {"term": "LT", "bucket": "lt_usi", "rate": 0.20, "indexed": True}
    assert us.classify("2024-01-04", "2025-07-22")["bucket"] == "st_us" and us.classify("2024-01-04", "2025-07-22")["rate"] is None
    assert us.index_factor("2021-01-04", "2024-07-22") == 363 / 301         # CII 2023-24 over 2020-21


def test_each_leg_in_rupees_at_its_own_month_end():
    h = hist()
    m = us.match([tr("2022-03-15", "B", "AAPL", 10, 150.0, 1.0), tr("2025-08-14", "S", "AAPL", 10, 230.0, 1.0)])
    r = us.realised(m, h)[0]
    buy_rate, sell_rate = fx_rates.rate(date(2022, 2, 28)), fx_rates.rate(date(2025, 7, 31))
    assert r["rate_buy"]["on"] == "2022-02-28" and r["rate_sell"]["on"] == "2025-07-31"
    assert r["cost_usd"] == pytest.approx(1501) and r["sale_usd"] == pytest.approx(2299)
    assert r["cost_inr"] == pytest.approx(1501 * buy_rate) and r["sale_inr"] == pytest.approx(2299 * sell_rate)
    assert r["gain_inr"] == pytest.approx(2299 * sell_rate - 1501 * buy_rate)
    assert r["term"] == "LT" and r["bucket"] == "lt_us" and r["fy"] == 2025
    row = us.tax_rows([r])[0]
    assert row["key"] == "US:AAPL" and row["bucket"] == "lt_us" and row["gain"] == pytest.approx(r["gain_inr"]) and row["src"] == "us"
    # indexed before 23 Jul 2024
    m = us.match([tr("2021-01-04", "B", "MSFT", 5, 200.0), tr("2024-07-10", "S", "MSFT", 5, 400.0)])
    r = us.realised(m, h)[0]
    assert r["bucket"] == "lt_usi" and r["indexed_cost"] == pytest.approx(r["cost_inr"] * 363 / 301)
    assert r["gain_inr"] == pytest.approx(r["sale_inr"] - r["indexed_cost"])
    # no rate for either date: kept in dollars, out of the tax rows
    r = us.realised(m, {"sbi": {}, "rbi": {}})[0]
    assert r["unpriced"] and us.tax_rows([r]) == []


def test_first_in_first_out_through_a_split():
    trades = [tr("2022-01-10", "B", "NVDA", 10, 100.0), tr("2023-05-02", "B", "NVDA", 5, 200.0), tr("2024-09-02", "S", "NVDA", 60, 120.0)]
    splits = {"NVDA": [{"date": "2024-06-10", "numerator": 10, "denominator": 1}]}
    m = us.match(trades, splits)
    assert len(m["realised"]) == 1 and not m["short"]
    r = m["realised"][0]
    # 10 shares became 100: the sale takes 60 of them, at 60% of their cost, still bought in January 2022
    assert (r["qty"], r["bought"], r["cost_usd"], r["sale_usd"]) == (pytest.approx(60), "2022-01-10", pytest.approx(600), pytest.approx(7200))
    assert [(l["d"], round(l["qty"], 6), round(l["cost_usd"], 2)) for l in m["open"]] == [("2022-01-10", 40, 400), ("2023-05-02", 50, 1000)]
    # without the split the same sale finds too few shares, and says so
    assert us.match(trades, {})["short"]["NVDA"] == pytest.approx(45)


def test_the_foreign_tax_credit_is_the_lower_of_the_two_taxes():
    assert us.ftc(10000, 2500, 0.30) == {"income": 10000, "foreign_tax": 2500, "indian_tax": 3000, "credit": 2500, "not_credited": 0}
    got = us.ftc(10000, 2500, 0.10)
    assert got["indian_tax"] == 1000 and got["credit"] == 1000 and got["not_credited"] == 1500
    assert us.ftc(10000, 2500, 0.0)["credit"] == 0                     # no Indian tax on it: nothing to credit


def test_us_dividends_in_rupees_with_25_percent_withheld():
    h = hist()
    rows = [{"d": "2025-05-15", "sym": "AAPL", "amount": 26.0, "tds": None}, {"d": "2025-08-14", "sym": "AAPL", "amount": 26.0, "tds": 3.9},
            {"d": "2024-11-14", "sym": "AAPL", "amount": 25.0, "tds": None}]
    got = us.dividends(rows, h, 2025, 0.2)
    r1, r2 = fx_rates.rate(date(2025, 4, 30)), fx_rates.rate(date(2025, 7, 31))
    s = got["stocks"][0]
    assert s["count"] == 2 and s["usd"] == 52 and s["tax_usd"] == pytest.approx(6.5 + 3.9)
    assert got["inr"] == pytest.approx(26 * r1 + 26 * r2, abs=0.01) and got["tax_inr"] == pytest.approx(6.5 * r1 + 3.9 * r2, abs=0.01)
    assert got["ftc"]["credit"] == pytest.approx(min(got["tax_inr"], got["inr"] * 0.2), abs=0.01)
    assert [ln["rate_on"] for ln in s["lines"]] == ["2025-04-30", "2025-07-31"]


def test_the_returns_five_periods():
    assert [us.quarter_of(d) for d in ("2025-04-01", "2025-06-15", "2025-06-16", "2025-09-15", "2025-09-16", "2025-12-15",
                                       "2025-12-16", "2026-03-15", "2026-03-16", "2026-03-31")] == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


# ---------- Schedule FA ----------
def closes_for(year: int, fn) -> dict[str, float]:
    out, d = {}, date(year, 1, 1)
    while d.year == year:
        if d.weekday() < 5:
            out[d.isoformat()] = fn(d)
        d = date.fromordinal(d.toordinal() + 1)
    return out


def test_schedule_fa_peak_and_closing_per_lot():
    h = hist()
    # a lot held all year (part sold in March), a lot bought and sold inside the year, a lot sold out the year before
    trades = [tr("2023-03-01", "B", "OLD", 5, 50.0), tr("2024-05-02", "S", "OLD", 5, 60.0),
              tr("2024-06-10", "B", "AAPL", 10, 100.0, 1.0), tr("2025-03-03", "S", "AAPL", 4, 120.0),
              tr("2025-11-03", "B", "AAPL", 2, 150.0), tr("2025-12-01", "S", "AAPL", 8, 160.0)]
    peak_day = "2025-06-18"
    px = closes_for(2025, lambda d: 300.0 if d.isoformat() == peak_day else 140.0)    # 10 x 140 in Jan < 6 x 300 in June
    fa = us.schedule_fa(2025, trades, {}, {"AAPL": px, "OLD": closes_for(2025, lambda d: 55.0)}, {}, h, {"AAPL": "Apple Inc."})
    assert [(r["symbol"], r["lot"]) for r in fa["rows"]] == [("AAPL", 1), ("AAPL", 2)]       # OLD was sold out in 2024
    a, b = fa["rows"]
    rate = lambda s: fx_rates.rate(date.fromisoformat(s))
    assert a["acquired"] == "2024-06-10" and a["initial"] == pytest.approx(1001 * rate("2024-06-10"), abs=0.01)
    assert a["peak_day"] == peak_day and a["peak"] == pytest.approx(6 * 300 * rate(peak_day), abs=0.01)   # 6 shares after March
    # the December sale took the first lot's last 6 shares and 2 of the second: both close the year at nothing
    assert a["closing"] == 0 and b["closing"] == 0 and a["closing_qty"] == 0
    assert a["proceeds"] == pytest.approx(4 * 120 * rate("2025-03-03") + 6 * 160 * rate("2025-12-01"), abs=0.01)
    assert b["proceeds"] == pytest.approx(2 * 160 * rate("2025-12-01"), abs=0.01)
    assert a["country"] == "2-UNITED STATES OF AMERICA" and a["name"] == "Apple Inc."
    assert fa["totals"]["closing"] == 0 and fa["label"].startswith("Calendar year 2025")


def test_schedule_fa_closing_value_and_a_split_in_the_year():
    h = hist()
    trades = [tr("2024-01-10", "B", "NVDA", 10, 500.0)]
    splits = {"NVDA": [{"date": "2025-06-10", "numerator": 10, "denominator": 1}]}
    # the price history is in today's (after-split) shares: 60 before and after the split
    px = closes_for(2025, lambda d: 60.0 if d.isoformat() != "2025-12-31" else 70.0)
    fa = us.schedule_fa(2025, trades, splits, {"NVDA": px}, {"NVDA": [{"d": "2025-03-05", "per_share": 0.01}, {"d": "2025-09-05", "per_share": 0.01}]}, h)
    r = fa["rows"][0]
    end = fx_rates.rate(date(2025, 12, 31))
    assert r["closing_qty"] == 100 and r["closing"] == pytest.approx(100 * 70 * end, abs=0.01)
    assert r["peak_day"] == "2025-12-31" and r["peak"] == pytest.approx(r["closing"])
    # dividends a share in today's shares: 100 shares' worth both times
    inc = 100 * 0.01 * fx_rates.rate(date(2025, 3, 5)) + 100 * 0.01 * fx_rates.rate(date(2025, 9, 5))
    assert r["income"] == pytest.approx(inc, abs=0.01) and r["proceeds"] is None
    # the user's own dividend lines are shared by the lots held that day
    fa = us.schedule_fa(2025, trades + [tr("2025-02-03", "B", "NVDA", 10, 400.0)], splits, {"NVDA": px},
                        {"NVDA": [{"d": "2025-03-05", "amount": 30.0}]}, h)
    assert [round(r["income"], 2) for r in fa["rows"]] == [round(15 * fx_rates.rate(date(2025, 3, 5)), 2)] * 2
    # no prices: the values are blank, and the stock is named
    fa = us.schedule_fa(2025, trades, splits, {}, {}, h)
    assert fa["rows"][0]["peak"] is None and fa["rows"][0]["closing"] is None and fa["missing_prices"] == ["NVDA"]


# ---------- reading a US broker's file ----------
def test_a_us_brokers_csv():
    csv = ("Trade Date,Action,Symbol,Description,Quantity,Price,Commission\n"
           "03/24/2025,Buy,AAPL,Apple Inc,10,$212.50,$1.00\n04/02/2025,Sell,aapl,Apple Inc,4,\"$1,220.00\",0\n"
           "04/15/2025,Dividend,AAPL,Apple Inc,,,\n05/01/2025,Buy,brk.b,Berkshire,2,480,0\n")
    got = us.parse_upload(csv.encode(), "trades.csv")
    assert got["month_first"]
    assert [(r["d"], r["side"], r["sym"], r["qty"], r["price"], r["fees"]) for r in got["rows"]] == [
        ("2025-03-24", "B", "AAPL", 10, 212.5, 1.0), ("2025-04-02", "S", "AAPL", 4, 1220.0, 0.0), ("2025-05-01", "B", "BRK-B", 2, 480.0, 0.0)]
    assert [p["reason"] for p in got["problems"]] == ["Not a purchase or sale (dividends, deposits and the like are left out)"]
    # day first when a date can only be read that way (an Indian app's export)
    got = us.parse_upload(b"Date,Type,Ticker,Shares,Price\n24-03-2025,BUY,MSFT,1,400\n05-04-2025,SELL,MSFT,1,410\n", "x.csv")
    assert [r["d"] for r in got["rows"]] == ["2025-03-24", "2025-04-05"] and not got["month_first"]
    with pytest.raises(us.hf.FileError):
        us.parse_upload(b"Name,Age\nA,3\n", "x.csv")


# ---------- the app ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    fx_rates.seed()
    yield built
    fx.forget()
    built["close"]()


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "pb"), ("RAZORPAY_PLAN_PRO", "pp")):
        monkeypatch.setattr(settings, k, v)


def add(c, h, d, side, sym, qty, price, fees=0.0):
    r = c.post("/money/us-tax/trades", headers=h, json={"d": d, "side": side, "sym": sym, "qty": qty, "price": price, "fees": fees})
    assert r.status_code == 200, r.text
    return r.json()


def test_the_page_the_tax_report_and_deleting(w):
    c = w["client"]
    add(c, PRO, "2022-03-15", "B", "AAPL", 10, 150, 1)
    add(c, PRO, "2025-01-10", "B", "MSFT", 4, 400)
    add(c, PRO, "2025-08-14", "S", "AAPL", 10, 230, 1)
    v = add(c, PRO, "2025-09-01", "S", "MSFT", 4, 380)
    fy = next(y for y in v["years"] if y["fy"] == 2025)
    assert fy["count"] == 2 and fy["lt"] > 0 and fy["st"] < 0 and not v["locked"]
    assert {r["symbol"]: r["term"] for r in fy["rows"]} == {"AAPL": "LT", "MSFT": "ST"}
    assert fy["rows"][0]["rate_sell"]["on"] == "2025-07-31"
    assert v["rates"]["available"] and v["fa"]["cy"] == date.today().year - 1 and v["facts"] and v["assumptions"]
    # the tax report: the US sales are in the year, in their own buckets, with the US loss set off
    rep = c.get("/tax", headers=PRO).json()
    y = next(y for y in rep["years"] if y["fy"] == 2025)
    keys = {b["key"] for b in y["buckets"]}
    assert "lt_us" in keys and y["us"]["count"] == 2 and y["us"]["allowed"]          # a bucket with only a loss isn't listed
    assert any("foreign shares" in s for s in y["steps"])
    lt = next(b for b in y["buckets"] if b["key"] == "lt_us")
    assert lt["after_setoff"] == pytest.approx(lt["gains"] + y["us"]["st"], abs=1)       # the short-term loss set off against it
    assert rep["names"]["US:AAPL"]["symbol"] == "AAPL" and rep["us_trades"] == 4
    # a future date and a bad ticker are refused
    assert c.post("/money/us-tax/trades", headers=PRO, json={"d": "2099-01-01", "side": "B", "sym": "AAPL", "qty": 1, "price": 1}).status_code == 400
    assert c.post("/money/us-tax/trades", headers=PRO, json={"d": "2025-01-01", "side": "B", "sym": "NOT A TICKER", "qty": 1, "price": 1}).status_code == 422
    # one trade deleted, then all of them with the tax data
    tid = v["trades"][0]["id"]
    assert c.delete(f"/money/us-tax/trades/{tid}", headers=PRO).status_code == 200
    assert c.delete("/money/us-tax/trades/nope", headers=PRO).status_code == 404
    assert c.delete("/tax", headers=PRO).status_code == 200
    assert c.get("/money/us-tax", headers=PRO).json()["trades"] == []


def test_a_file_upload_and_my_holdings_gaps(w):
    c = w["client"]
    assert c.put("/holdings", headers=PRO, json={"items": [{"symbol": "AAPL", "qty": 12, "avg": 150, "market": "US"}]}).status_code == 200
    v = c.get("/money/us-tax", headers=PRO).json()
    assert [(g["symbol"], g["missing"]) for g in v["gaps"]] == [("AAPL", 12)]
    csv = "Date,Side,Symbol,Quantity,Price\n2023-03-01,BUY,AAPL,3,150\n"
    r = c.post("/money/us-tax/import?filename=t.csv", headers=PRO, json={"filename": "t.csv", "data": base64.b64encode(csv.encode()).decode()})
    assert r.status_code == 200 and r.json()["added"] == 1
    again = c.post("/money/us-tax/import?filename=t.csv", headers={**PRO, "content-type": "application/octet-stream"}, content=csv.encode())
    assert again.json()["added"] == 0 and again.json()["duplicates"] == 1
    gaps = again.json()["us"]["gaps"]
    assert gaps == []            # 3 shares bought in 2023 are 12 after the 4:1 split in the stock's history: all covered
    assert c.post("/money/us-tax/import", headers={**PRO, "content-type": "application/octet-stream"}, content=b"Name\nx\n").status_code == 400


def test_free_sees_the_totals_and_terms_not_the_workings(w, paid):
    c = w["client"]
    add(c, FREE, "2023-01-10", "B", "AAPL", 5, 120)
    v = add(c, FREE, "2025-06-02", "S", "AAPL", 2, 200)
    assert v["locked"] and v["fa"] is None
    y = next(y for y in v["years"] if y["fy"] == 2025)
    assert y["lt"] > 0 and "rows" not in y and "dividends" not in y
    assert v["open_lots"][0]["term"] == "LT"
    assert c.get("/money/us-tax/schedule-fa.csv?cy=2025", headers=FREE).status_code == 402
    rep = c.get("/tax", headers=FREE).json()
    y = next(y for y in rep["years"] if y["fy"] == 2025)
    assert y["us"] and not y["us"]["allowed"] and "lt_us" not in {b["key"] for b in y["buckets"]}


def test_rates_are_fetched_once_a_day_and_a_failed_fetch_keeps_them(w, monkeypatch):
    calls = []
    sbi = "DATE,PDF FILE,TT BUY\n" + "".join(f"{d.isoformat()} 09:00,x,{fx_rates.rate(d)}\n" for d in map(date.fromisoformat, sorted(fx_rates.history()["sbi"])[:300]))

    def fake_get(url):
        calls.append(url)
        if "sbi" in url:
            return sbi
        raise OSError("down")
    monkeypatch.setattr(fx, "_get", fake_get)
    db.delete_setting("fxhist:USD")
    fx.forget()
    got = fx.ensure()
    assert len(calls) == 2 and len(got["sbi"]) == 300 and got["rbi"] == {} and got["at"]
    fx.forget()
    assert fx.ensure()["sbi"] == got["sbi"] and len(calls) == 2         # stored and fresh: not fetched again
    monkeypatch.setattr(fx, "_get", lambda url: (_ for _ in ()).throw(OSError("down")))
    assert fx.refresh() is False and fx.load()["sbi"] == got["sbi"]       # both down: what was stored stays


def test_schedule_fa_csv_and_stored_privately(w):
    c = w["client"]
    add(c, PRO, "2024-02-01", "B", "AAPL", 3, 180)
    cy = date.today().year - 1
    r = c.get(f"/money/us-tax/schedule-fa.csv?cy={cy}", headers=PRO)
    assert r.status_code == 200 and "Initial value of the investment" in r.text and "2-UNITED STATES OF AMERICA" in r.text
    assert "not a filed return" in r.text
    other = c.get("/money/us-tax", headers=FREE).json()
    assert other["trades"] == []
    assert db.get_setting("ustax:u-pro")
