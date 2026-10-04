"""Money tax tools: dividends (the TDS thresholds, US withholding, the broker's dividend sheet, a CSV, the estimate
from holdings, and the year's total in the tax estimate), advance tax (the due dates, the ₹10,000 threshold, gains
after a due date, 234C with its 12% and 36% tolerance, 234B, the reminders) and the long-term exemption tracker."""
import base64
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app import corp_actions, holdings, money_advance_tax as A, money_dividends as D, money_ltcg as L
from app import tax_lots as T, tax_total
from tests import tradebook_maker, world

PRO, BASIC, FREE = world.headers("pro-token"), world.headers("basic-token"), world.headers("free-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.fixture
def paid(monkeypatch):
    """Plans enforced (payments live), so Free and Basic see the locked parts."""
    from app.config import settings
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)
    from app import plans
    monkeypatch.setattr(plans, "access_plan", lambda p: p.get("plan") or "free")
    from app import auth
    monkeypatch.setattr(auth, "access_plan", lambda p: p.get("plan") or "free")


# ---------- dividends: the rules ----------
def test_tds_threshold_by_year():
    assert D.tds_threshold(2019) is None                       # exempt then: the company paid DDT
    assert D.tds_threshold(2020) == 5000 and D.tds_threshold(2024) == 5000
    assert D.tds_threshold(2025) == 10000 and D.tds_threshold(2026) == 10000    # Finance Act 2025
    assert "393(1)" in D.tds_section(2026) and "194" in D.tds_section(2026) and "393" not in D.tds_section(2025)


def test_tds_is_on_the_whole_amount_once_over_the_threshold():
    assert D.expected_tds(2024, 5000) == 0 and D.expected_tds(2024, 5001) == 500.1
    assert D.expected_tds(2025, 9000) == 0 and D.expected_tds(2025, 10000) == 0 and D.expected_tds(2025, 12000) == 1200
    assert D.expected_tds(2019, 50000) == 0


def row(d, sym, amount, cur="INR", **kw):
    return {"d": d, "sym": sym, "name": "", "isin": "", "qty": None, "ps": None, "amount": amount, "tds": None, "cur": cur, "src": "csv", **kw}


def test_a_year_by_company_with_tds_and_us_withholding():
    rows = [row("2025-05-01", "ITC", 7000), row("2025-11-01", "ITC", 4000), row("2025-07-01", "TCS", 9000),
            row("2025-08-14", "AAPL", 100, "USD"), row("2025-11-13", "AAPL", 20, "USD")]
    y = D.year(2025, rows, 85.0)
    itc = next(c for c in y["companies"] if c["symbol"] == "ITC")
    tcs = next(c for c in y["companies"] if c["symbol"] == "TCS")
    aapl = next(c for c in y["companies"] if c["symbol"] == "AAPL")
    assert itc["amount"] == 11000 and itc["tds_expected"] == 1100 and itc["over_threshold"]
    assert tcs["tds_expected"] == 0 and not tcs["over_threshold"]                 # ₹9,000: under ₹10,000
    assert aapl["amount_usd"] == 120 and aapl["amount"] == 10200 and aapl["withheld_usd"] == 30 and aapl["withheld"] == 2550
    assert y["india_total"] == 20000 and y["us_total"] == 10200 and y["total"] == 30200
    assert y["tds"]["expected"] == 1100 and y["tds"]["companies_over"] == 1 and y["tds"]["threshold"] == 10000
    assert y["us"]["withheld"] == 2550 and y["us"]["rate"] == 0.25
    # the same ₹9,000 a year earlier was over the ₹5,000 threshold
    assert D.year(2024, [row("2024-07-01", "TCS", 9000)], None)["tds"]["expected"] == 900
    # no dollar rate: US lines can't be counted in rupees, and say so
    assert D.year(2025, rows, None)["unpriced"] == 2


def test_the_brokers_dividend_sheet_in_the_tax_zip():
    data = tradebook_maker.zerodha_tax_zip(dividends=True)
    got = D.from_tax_file(data, "taxpnl.zip")
    assert [(r["sym"], r["d"], r["amount"]) for r in got] == [("ITC", "2025-05-28", 7850), ("ITC", "2026-02-04", 6500), ("TCS", "2025-07-16", 110)]
    assert all(r["src"] == "statement" and r["cur"] == "INR" for r in got) and got[0]["isin"] == "INE154A01025" and got[0]["qty"] == 1000
    assert D.from_tax_file(tradebook_maker.zerodha_tax_zip(), "taxpnl.zip") == []          # older years: no sheet
    assert D.from_tax_file(b"not a zip", "x.zip") == [] and D.from_tax_file(b"PK\x03\x04junk", "x.zip") == []


def test_a_dividend_csv_with_us_lines_and_bad_lines():
    csv = ("Date,Symbol,Amount,TDS,Currency\n2025-06-10,INFY,2100,0,INR\n10/07/2025,AAPL,26.5,6.63,USD\n"
           ",RELIANCE,500,,INR\n2025-08-01,HDFCBANK,abc,,\nTotal,,2626.5,,\n")
    got = D.parse_upload(csv.encode(), "divs.csv")
    assert [(r["sym"], r["d"], r["amount"], r["cur"]) for r in got["rows"]] == [("INFY", "2025-06-10", 2100, "INR"), ("AAPL", "2025-07-10", 26.5, "USD")]
    assert got["rows"][1]["tds"] == 6.63
    assert {p["reason"] for p in got["problems"]} == {"No date", "No dividend amount"}
    # quantity × dividend a share when there's no amount
    got = D.parse_upload(b"Record date,Company name,Quantity,Dividend per share\n2025-09-01,Infosys,100,21\n", "x.csv")
    assert got["rows"][0]["amount"] == 2100 and got["rows"][0]["sym"] == "INFOSYS"
    with pytest.raises(D.hf.FileError):
        D.parse_upload(b"Name,Age\nA,3\n", "x.csv")
    with pytest.raises(D.hf.FileError):
        D.parse_upload(b"", "x.csv")


def test_merge_skips_the_same_file_twice():
    a = [row("2025-06-10", "INFY", 2100)]
    out, added, dup = D.merge(a, [row("2025-06-10", "INFY", 2100), row("2025-06-11", "INFY", 2100)])
    assert (len(out), added, dup) == (2, 1, 1)


def test_the_estimate_from_holdings_works_back_through_a_bonus():
    today = date(2026, 10, 4)
    item = {"symbol": "TCS", "qty": 20, "since": "2026-09-01"}
    acts = [{"kind": "dividend", "amount": 10, "ex_date": "2026-05-01", "record_date": "2026-05-01", "label": "Interim"},
            {"kind": "bonus", "factor": 2, "ratio": [1, 1], "ex_date": "2026-06-01"},
            {"kind": "dividend", "amount": 5, "ex_date": "2026-07-01", "label": "Final"},
            {"kind": "dividend", "amount": 4, "ex_date": "2026-11-01", "label": "Interim"}]
    paid, ahead = D.estimate([item], {"TCS": acts}, today, None)
    assert [(r["d"], r["qty"], r["amount"]) for r in paid] == [("2026-05-01", 10, 100), ("2026-07-01", 20, 100)]
    assert [(r["ex"], r["amount"]) for r in ahead] == [("2026-11-01", 80)] and all(r["src"] == "estimated" for r in paid)


def test_view_uses_files_first_and_only_includes_them_by_default():
    today = date(2026, 10, 4)
    stored = {"rows": [row("2025-06-10", "INFY", 2100)], "files": [], "include": {}, "updated_at": None}
    est = [row("2025-06-10", "TCS", 500, src="estimated"), row("2026-05-01", "TCS", 700, src="estimated")]
    v = D.view(stored, est, [], None, today)
    y25, y26 = (next(y for y in v["years"] if y["fy"] == f) for f in (2025, 2026))
    assert y25["source"] == "files" and y25["include"] and y25["total"] == 2100 and y25["estimate_total"] == 500
    assert y26["source"] == "estimated" and not y26["include"] and y26["total"] == 700
    assert D.for_total(v) == {2025: 2100}
    stored["include"] = {2026: True, 2025: False}
    assert D.for_total(D.view(stored, est, [], None, today)) == {2026: 700}
    locked = D.view(stored, est, [], None, today, full=False)
    assert locked["locked"] and all(y["companies"] == [] for y in locked["years"]) and locked["years"][0]["total"]


def test_dividends_in_the_total_tax_estimate_at_slab_rate():
    base = tax_total.estimate(2025, {"other": 1500000, "salary": 1500000}, [], 0, 0)
    more = tax_total.estimate(2025, {"other": 1500000, "salary": 1500000}, [], 0, 0, dividends=100000)
    assert more["income"]["dividends"] == 100000 and more["income"]["normal"] == base["income"]["normal"] + 100000
    # ₹14.25 lakh taxable → ₹15.25 lakh: the extra ₹1 lakh is all in the 15% slab (₹12 to 16 lakh)
    assert round(more["slab_tax"] - base["slab_tax"]) == 15000
    assert any("Dividends of ₹1,00,000 are income from other sources" in s for s in more["steps"])
    assert any(l["label"].startswith("Dividends") for l in more["lines"])
    # no standard deduction against dividends, and an F&O loss can be set off against them
    loss = tax_total.estimate(2025, {"other": 0}, [], 0, -40000, dividends=100000)
    assert loss["income"]["normal"] == 60000
    for bad in (float("nan"), -5, "x"):
        assert tax_total.estimate(2025, {"other": 0}, [], 0, 0, dividends=bad)["income"]["dividends"] == 0


# ---------- advance tax ----------
def test_due_dates():
    got = A.due_dates(2026)
    assert [(d["date"], d["pct"]) for d in got] == [("2026-06-15", 0.15), ("2026-09-15", 0.45), ("2026-12-15", 0.75), ("2027-03-15", 1.0)]
    assert got[0]["label"] == "15 Jun 2026"


def sched(tax, tds=0, paid=(), upto=None, today=date(2027, 4, 2)):
    return A.schedule(2026, tax, list(upto or [tax] * 4), tds, [{"d": d, "amount": a} for d, a in paid], today)


def test_below_10000_after_tds_no_advance_tax():
    s = sched(19000, tds=9500)
    assert not s["due"] and s["net"] == 9500 and all(r["required"] == 0 and r["interest_234c"] == 0 for r in s["instalments"])
    assert not s["b234"]["applies"] and "below ₹10,000" in s["steps"][0]
    assert sched(10000)["due"]


def test_cumulative_amounts_and_no_interest_when_paid_on_time():
    s = sched(100000, paid=[("2026-06-15", 15000), ("2026-09-15", 30000), ("2026-12-15", 30000), ("2027-03-15", 25000)])
    assert [r["required"] for r in s["instalments"]] == [15000, 45000, 75000, 100000]
    assert [r["paid"] for r in s["instalments"]] == [15000, 45000, 75000, 100000]
    assert s["interest_234c"] == 0 and not s["b234"]["applies"]


def test_234c_with_the_12_and_36_percent_tolerance():
    # June: 12,000 is 12% of 1 lakh, short of 15% but within the tolerance; September 35,000 is under 36%
    s = sched(100000, paid=[("2026-06-10", 12000), ("2026-09-01", 23000), ("2026-12-15", 35000), ("2027-03-10", 29950)])
    jun, sep, dec, mar = s["instalments"]
    assert jun["short"] == 3000 and jun["tolerated"] and jun["interest_234c"] == 0
    assert sep["short"] == 10000 and not sep["tolerated"] and sep["interest_234c"] == 300          # 1% × 3 months
    assert dec["short"] == 5000 and dec["interest_234c"] == 150
    assert mar["short"] == 50 and mar["interest_234c"] == 0                                        # under ₹100: rounded away
    assert s["interest_234c"] == 450
    # 36% by September: tolerated
    s = sched(100000, paid=[("2026-06-15", 15000), ("2026-09-15", 21000)])
    assert s["instalments"][1]["tolerated"] and s["instalments"][1]["interest_234c"] == 0
    # nothing paid at all: 15,000×3% + 45,000×3% + 75,000×3% + 1,00,000×1%
    assert sched(100000)["interest_234c"] == 450 + 1350 + 2250 + 1000


def test_shortfall_rounds_down_to_100():
    s = sched(100099)
    assert s["instalments"][0]["required"] == 15014.85 and s["instalments"][0]["interest_234c"] == 450      # 15,000 × 3%


def test_gains_after_a_due_date_go_into_the_later_instalments():
    # ₹70,000 of tax from F&O all year, and a share sale in October that adds ₹30,000
    s = sched(100000, upto=[70000, 70000, 100000, 100000], paid=[("2026-06-15", 10500), ("2026-09-15", 21000), ("2026-12-15", 43500), ("2027-03-15", 25000)])
    assert [r["required"] for r in s["instalments"]] == [10500, 31500, 75000, 100000]
    assert s["interest_234c"] == 0
    assert "left out of it" in " ".join(s["steps"])
    # the cut-off never makes an instalment larger than the year's tax would
    assert sched(50000, upto=[90000, 90000, 90000, 50000])["instalments"][0]["required"] == 7500


def test_tds_comes_off_every_instalment():
    s = sched(100000, tds=20000)
    assert s["net"] == 80000 and [r["required"] for r in s["instalments"]] == [12000, 36000, 60000, 80000]


def test_234b_when_less_than_90_percent_paid():
    s = sched(100000, paid=[("2027-03-15", 85000)])
    b = s["b234"]
    assert b["applies"] and b["short"] == 15000 and b["months"] == 4 and b["interest"] == 600 and b["until"] == "2027-07-31"
    assert not sched(100000, paid=[("2027-03-15", 90000)])["b234"]["applies"]
    # after 31 July, the months keep counting to today
    late = sched(100000, today=date(2027, 9, 20))["b234"]
    assert late["months"] == 6 and late["interest"] == 6000
    assert A.months_234b(2026, date(2027, 4, 1)) == 1


def test_upcoming_instalments_show_what_is_left_to_pay():
    s = sched(100000, paid=[("2026-06-15", 15000), ("2026-09-15", 30000)], today=date(2026, 10, 4))
    assert [r["status"] for r in s["instalments"]] == ["passed", "passed", "next", "later"] and s["next"] == 2
    dec = s["instalments"][2]
    assert dec["to_pay"] == 30000 and dec["interest_234c"] == 0 and dec["interest_if_missed"] == 900
    # on the due day itself it can still be paid
    assert sched(100000, today=date(2026, 6, 15))["instalments"][0]["status"] == "next"


def test_stored_figures_are_checked():
    v = A.clean_year({"tds": -5, "paid": [{"d": "2026-06-15", "amount": 100}, {"d": "2026-02-30", "amount": 5}, {"d": "x", "amount": 1},
                                          {"d": "2026-07-01", "amount": float("inf")}, "junk"]})
    assert v == {"tds": 0.0, "paid": [{"d": "2026-06-15", "amount": 100.0}]}


def test_reminders_go_7_days_and_1_day_before():
    assert [(d["date"], n) for d, n in A.reminders_due(date(2026, 12, 8))] == [("2026-12-15", 7)]
    assert [(d["date"], n) for d, n in A.reminders_due(date(2027, 3, 14))] == [("2027-03-15", 1)]
    assert A.reminders_due(date(2026, 12, 9)) == []
    subject, text = A.reminder_text(A.due_dates(2026)[2], 1)
    assert "tomorrow" in subject and "75%" in text and "₹" not in text


# ---------- the long-term exemption ----------
def b(d, qty, price, key="A", **kw):
    return {"d": d, "side": "B", "qty": qty, "price": price, "sym": key, **kw}


def s_(d, qty, price, key="A", **kw):
    return {"d": d, "side": "S", "qty": qty, "price": price, "sym": key, **kw}


def test_exemption_used_left_and_lots_turning_long_term():
    today = "2026-10-04"
    trades = [b("2024-01-10", 20, 100, "A"), s_("2026-05-01", 10, 1100, "A"),        # ₹10,000 long-term gain realised
              b("2025-10-20", 10, 100, "B"),                                     # long-term from 21 Oct 2026: 17 days
              b("2025-11-20", 5, 300, "C"),                                      # from 21 Nov 2026: 48 days
              b("2025-12-25", 5, 100, "D"),                                      # from 26 Dec 2026: 83 days
              b("2026-03-01", 5, 100, "E"),                                      # from 2 Mar 2027: more than 90 days
              b("2017-06-01", 10, 50, "G", fmv=150)]                             # grandfathered at ₹150
    c = T.compute(trades, today=today)
    quotes = {k: {"price": p} for k, p in {"A": 200, "B": 150, "C": 250, "D": 120, "E": 110, "G": 300}.items()}
    t = L.tracker(c, quotes, today)
    assert t["fy"] == 2026 and t["exemption"] == {"limit": 125000, "used": 10000, "left": 115000, "realised_lt_net": 10000, "realised_st_net": 0}
    longs = {r["key"]: r for r in t["long"]}
    assert set(longs) == {"A", "G"}
    assert longs["A"]["gain"] == 1000 and longs["A"]["text"] == "If sold today, the long-term gain would be ₹1,000."
    assert longs["G"]["cost"] == 1500 and longs["G"]["gain"] == 1500 and longs["G"]["grandfathered"]
    soon = {r["key"]: r for r in t["soon"]}
    assert set(soon) == {"B", "C", "D"}
    assert (soon["B"]["long_from"], soon["B"]["days_left"], soon["B"]["window"], soon["B"]["gain"]) == ("2026-10-21", 17, 30, 500)
    assert soon["C"]["window"] == 60 and soon["C"]["gain"] == -250 and "loss is ₹250" in soon["C"]["text"]
    assert soon["D"]["window"] == 90
    assert t["soon_counts"] == {"30": 1, "60": 2, "90": 3}
    assert t["open_lt"] == {"lots": 2, "gains": 2500, "losses": 0, "with_gain": 2}
    words = " ".join([r["text"] for r in t["long"] + t["soon"]] + t["facts"]).lower()
    assert not re.search(r"\b(you should|book|harvest|sell (these|now|them)|recommend)\b", words)
    # locked: the counts and the exemption, not the lots
    locked = L.tracker(c, quotes, today, full=False)
    assert locked["long"] == [] and locked["soon"] == [] and locked["exemption"]["used"] == 10000 and locked["locked"]


def test_unpriced_lots_are_counted_not_guessed():
    c = T.compute([b("2024-01-10", 5, 100, "Z")], today="2026-10-04")
    t = L.tracker(c, {}, "2026-10-04")
    assert t["unpriced"] == 1 and t["long"] == []


# ---------- the API ----------
def up(c, name, data, headers=PRO):
    return c.post("/money/dividends/import", headers=headers, json={"filename": name, "data": base64.b64encode(data).decode()})


def test_dividends_api_upload_toggle_and_the_tax_report(w):
    c = w["client"]
    fy = T.fy_of(date.today().isoformat())
    d1 = f"{fy}-06-10"
    r = up(c, "divs.csv", f"Date,Symbol,Amount\n{d1},INFY,12000\n{d1},TCS,3000\n".encode())
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["added"] == 2 and got["duplicates"] == 0
    y = next(x for x in got["dividends"]["years"] if x["fy"] == fy)
    assert y["source"] == "files" and y["include"] and y["total"] == 15000 and y["tds"]["expected"] == (1200 if fy >= 2025 else 1500)
    assert up(c, "divs.csv", f"Date,Symbol,Amount\n{d1},INFY,12000\n".encode()).json()["added"] == 0
    tax = c.get("/tax", headers=PRO).json()
    total = next(x for x in tax["years"] if x["fy"] == fy)["total"]
    assert total["income"]["dividends"] == 15000 and any(l["label"].startswith("Dividends") for l in total["lines"])
    # left out: the estimate goes back
    r = c.put("/money/dividends/include", headers=PRO, json={"fy": fy, "include": False})
    assert next(x for x in r.json()["years"] if x["fy"] == fy)["include"] is False
    total = next(x for x in c.get("/tax", headers=PRO).json()["years"] if x["fy"] == fy)["total"]
    assert total["income"]["dividends"] == 0
    assert up(c, "x.csv", b"Name,Age\nA,3\n").status_code == 400
    assert c.post("/money/dividends/import", headers=PRO, content=b"\x00\x01", params={"filename": "x.bin"}).status_code == 400
    # nobody else sees them, and deleting the tax data removes them
    assert all(y["total"] == 0 for y in c.get("/money/dividends", headers=FREE).json()["years"])
    assert c.delete("/tax", headers=PRO).status_code == 200
    assert D.load("u-pro")["rows"] == []


def test_the_tax_zip_with_a_dividend_sheet_saves_them(w):
    c = w["client"]
    r = c.post("/tax/import", headers=PRO, json={"filename": "taxpnl-AB1234-2025_2026.zip",
                                                 "data": base64.b64encode(tradebook_maker.zerodha_tax_zip(dividends=True)).decode()})
    assert r.status_code == 200, r.text
    assert r.json()["dividends_added"] == 3
    y = next(x for x in c.get("/money/dividends", headers=PRO).json()["years"] if x["fy"] == 2025)
    assert y["total"] == 14460 and y["source"] == "files"
    itc = next(x for x in y["companies"] if x["symbol"] == "ITC")
    assert itc["tds_expected"] == 1435 and itc["over_threshold"]
    assert next(x for x in c.get("/tax", headers=PRO).json()["years"] if x["fy"] == 2025)["total"]["income"]["dividends"] == 14460


def test_estimated_dividends_from_holdings(w):
    c = w["client"]
    t = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    holdings.save("u-pro", [{"symbol": "ITC", "qty": 100, "avg": 400, "exchange": "NSE"}], "Manual")
    ex = (t - timedelta(days=3)).isoformat()
    corp_actions.hist_save("IN", "ITC", [corp_actions.row("IN", "ITC", {"kind": "dividend", "label": "Interim Dividend", "text": "Interim Dividend Rs 6.5",
                                                                     "amount": 6.5}, date.fromisoformat(ex), record=date.fromisoformat(ex))])
    v = c.get("/money/dividends", headers=PRO).json()
    y = next(x for x in v["years"] if x["fy"] == T.fy_of(ex))
    assert y["source"] == "estimated" and y["total"] == 650 and not y["include"]
    assert any("Estimated" in a for a in v["assumptions"])


def test_advance_tax_api_dates_for_free_amounts_for_pro(w, paid):
    c = w["client"]
    free = c.get("/money/advance-tax", headers=FREE).json()
    assert free["locked"] and len(free["dates"]) == 4 and "schedule" not in free
    assert c.put("/money/advance-tax", headers=FREE, json={"fy": 2026, "tds": 1000}).status_code == 402
    assert c.get("/money/ltcg", headers=FREE).json()["locked"]
    basic = c.get("/money/dividends", headers=BASIC).json()
    assert not basic["locked"]
    assert c.get("/money/dividends", headers=FREE).json()["locked"]
    # Pro: income of ₹20 lakh, so the tax is well above ₹10,000
    assert c.put("/tax/inputs", headers=PRO, json={"fy": free["current_fy"], "regime": "new", "other": 2000000, "salary": 2000000, "deductions": 0}).status_code == 200
    fy = free["current_fy"]
    r = c.put("/money/advance-tax", headers=PRO, json={"fy": fy, "tds": 50000, "paid": [{"d": f"{fy}-06-15", "amount": 10000}]})
    assert r.status_code == 200, r.text
    s = r.json()["schedule"]
    assert s["due"] and s["tds"] == 50000 and s["net"] == round(s["tax"] - 50000, 2)
    assert s["instalments"][0]["paid"] == 10000 and r.json()["inputs"]["paid"] == [{"d": f"{fy}-06-15", "amount": 10000.0}]
    assert c.put("/money/advance-tax", headers=PRO, json={"fy": fy, "tds": -1}).status_code == 422


def test_reminders_opt_in_job_and_unsubscribe(w, monkeypatch):
    c = w["client"]
    assert c.put("/money/advance-tax/reminders", headers=PRO, json={"on": True}).json() == {"remind": True}
    sent = []
    monkeypatch.setattr(A, "send", lambda p, subject, text: sent.append((p["id"], subject)) or True)
    job = A.Job()
    eve = datetime(2026, 12, 8, 4, 0, tzinfo=ZoneInfo("UTC"))            # 09:30 IST, 7 days before 15 Dec
    assert job.tick(eve) == 1 and sent == [("u-pro", "Advance tax: the 15 Dec 2026 instalment is in 7 days")]
    assert job.tick(eve) == 0                                               # once
    assert job.tick(datetime(2026, 12, 9, 4, 0, tzinfo=ZoneInfo("UTC"))) == 0
    assert job.tick(datetime(2026, 12, 14, 2, 0, tzinfo=ZoneInfo("UTC"))) == 0     # 07:30 IST: not yet
    from app import mail_tokens
    t = mail_tokens.make("u-pro", "unsubscribe", "advance_tax")
    assert c.post(f"/unsubscribe?t={t}").status_code == 200
    assert not A.load("u-pro")["remind"]
    assert A.subscribers() == []


def test_ltcg_api(w):
    c = w["client"]
    r = c.post("/tax/import", headers=PRO, json={"filename": "zerodha_console_tradebook.csv",
                                                 "data": base64.b64encode((tradebook_maker.DIR / "zerodha_console_tradebook.csv").read_bytes()).decode()})
    assert r.status_code == 200
    got = c.get("/money/ltcg", headers=PRO).json()
    assert got["exemption"]["limit"] == 125000 and "below_cost" in got and not got["locked"]
    assert got["trades"] > 0


def test_money_routes_need_sign_in(w):
    for path in ("/money/dividends", "/money/advance-tax", "/money/ltcg"):
        assert w["client"].get(path).status_code == 401
