"""ITR-ready export and the pack for your CA: Schedule 112A's columns in the form's order and its grandfathering
lines, the portal's consolidated line, Schedule CG by section and by period, dividends by period, the ITR-3 business
figures, tax paid, the workbook, the ZIP and the PDF, the label on every file, and the plans."""
import base64
import io
import zipfile
from datetime import datetime

import pytest

from app import holdings_file as hf, money_itr as I, tax_lots as T, xlsx_write
from app.config import settings
from tests import fx_rates, world

PRO, FREE = world.headers("pro-token"), world.headers("free-token")
TODAY = "2026-10-04"


def b(d, qty, price, key="A", **kw):
    return {"d": d, "side": "B", "qty": qty, "price": price, "sym": key, "isin": f"INE{key:0>3}A01011", "name": f"{key} Ltd", **kw}


def s(d, qty, price, key="A", **kw):
    return {"d": d, "side": "S", "qty": qty, "price": price, "sym": key, "isin": f"INE{key:0>3}A01011", "name": f"{key} Ltd", **kw}


def year_rows(trades, fy, fmv=None):
    c = T.compute(trades, fmv=fmv, today=TODAY)
    return [r for r in c["realised"] if r["fy"] == fy], c["names"]


# ---------- Schedule 112A ----------
def test_112a_columns_are_the_forms():
    assert I.COLS_112A[0].endswith("(1a)") and I.COLS_112A[1].endswith("(1b)") and I.COLS_112A[2] == "ISIN Code (2)"
    assert [c.split("(")[-1].split(")")[0] for c in I.COLS_112A[:15]] == ["1a", "1b", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14"]


def test_112a_grandfathering_lines():
    trades = [b("2017-01-02", 10, 100, charges=10), s("2025-06-03", 4, 300, charges=8),       # FMV 150 < sale: col 9 = FMV
              b("2016-05-02", 5, 500, "B"), s("2025-07-01", 5, 400, "B"),                       # FMV 600 > sale: col 9 = sale
              b("2017-03-01", 2, 100, "C"), s("2025-08-01", 2, 90, "C"),                        # FMV 80 < actual: actual cost wins
              b("2019-01-02", 10, 50, "D"), b("2020-01-02", 10, 60, "D"), s("2025-09-01", 15, 80, "D"),   # after 31 Jan 2018
              b("2025-01-02", 1, 10, "E"), s("2025-06-02", 1, 20, "E")]                          # short term: not in 112A
    rows, names = year_rows(trades, 2025, fmv={"A": 150, "B": 600, "C": 80})
    lines = {(v["key"], v["1a"]): v for v in I.rows_112a(rows, names)}
    a = lines[("A", "BE")]
    assert a["1b"] == "AE" and a["isin"] == "INE00AA01011" and a["qty"] == 4
    assert a["gross"] == 1200 and a["exp"] == 8 and a["cost8"] == pytest.approx(404)          # cost with the buy's charges
    assert a["fmv_each"] == 150 and a["fmv"] == 600 and a["col9"] == 600 and a["col7"] == 600  # higher of 404 and min(1200, 600)
    assert a["col13"] == 608 and a["col14"] == 592
    bb = lines[("B", "BE")]
    assert bb["col9"] == 2000 and bb["col7"] == 2500 and bb["col14"] == -500                  # lower of sale 2000 and FMV 3000
    cc = lines[("C", "BE")]
    assert cc["col9"] == 160 and cc["col7"] == 200 and cc["col14"] == -20                     # FMV 160 below the actual 200
    d = lines[("D", "AE")]                                                                     # two lots, one line per company and day
    assert d["qty"] == 15 and d["gross"] == 1200 and d["col7"] == d["cost8"] == 800 and d["col9"] == 0 and d["fmv_each"] is None
    assert ("E", "AE") not in lines
    # the form's own arithmetic holds on every line: 6 = 4 x 5, 7 = max(8, 9), 13 = 7 + 12, 14 = 6 - 13
    for v in lines.values():
        assert v["gross"] == pytest.approx(v["qty"] * v["price"]) and v["col7"] == max(v["cost8"], v["col9"])
        assert v["col13"] == pytest.approx(v["col7"] + v["exp"]) and v["col14"] == pytest.approx(v["gross"] - v["col13"])
    # a sale before 23 Jul 2024 is coded BE in 1b
    rows, names = year_rows([b("2017-01-02", 1, 100), s("2024-06-03", 1, 300)], 2024, fmv={"A": 150})
    assert I.rows_112a(rows, names)[0]["1b"] == "BE"


def test_112a_missing_fmv_and_the_portal_layout():
    rows, names = year_rows([b("2017-01-02", 1, 100), s("2025-06-03", 1, 300), b("2020-01-02", 3, 10, "Z"), s("2025-07-01", 3, 30, "Z"),
                             b("2021-01-02", 2, 10, "Y"), s("2025-08-01", 2, 5, "Y")], 2025)
    g = {"rows": rows, "names": names}
    t = I.t_112a(g)
    a = next(r for r in t["rows"] if r[3] == "A Ltd")
    assert a[0] == "BE" and a[9] == 0 and a[7] == 100 and any("no 31 Jan 2018 price" in n for n in t["notes"])
    assert t["rows"][-1][0] == "Total" and t["rows"][-1][14] == pytest.approx(200 + 60 - 10)
    p = I.t_112a_portal(g)
    assert len(p["columns"]) == 15
    be = [r for r in p["rows"] if r[0] == "BE"]
    ae = [r for r in p["rows"] if r[0] == "AE"]
    assert len(be) == 1 and len(ae) == 1                                    # everything after 31 Jan 2018 is one line
    assert ae[0][2:4] == ["INNOTREQUIRD", "CONSOLIDATED"] and ae[0][4] is None and ae[0][6] == 100 and ae[0][14] == 50
    out = I.portal_csv(p)
    assert out.splitlines()[0].startswith("Share/Unit acquired (1a)") and "Note" not in out and I.LABEL not in out


# ---------- Schedule CG, OS and the rest ----------
def g_for(trades, fy, **kw):
    rows, names = year_rows(trades, fy, kw.pop("fmv", None))
    y = T.with_total(T.year(fy, rows, [], limit=None), [], None)
    base = {"fy": fy, "y": y, "rows": rows, "names": names, "files": [], "fmv_src": {}, "div_lines": [], "div_source": "none",
            "div_year": None, "us_div": None, "fa": None, "us_count": 0, "us_allowed": True, "tds": 0.0, "paid": [], "mf_count": 0,
            "made": datetime(2026, 10, 4)}
    return {**base, **kw}


def test_schedule_cg_by_section_and_by_period():
    trades = [b("2025-01-02", 10, 100), s("2025-05-02", 10, 150),        # short term, period 1
              b("2025-02-02", 10, 100, "B"), s("2025-10-01", 10, 80, "B"),  # short-term loss, period 3
              b("2022-01-02", 10, 100, "C"), s("2025-12-20", 10, 400, "C")]  # long term, period 4
    g = g_for(trades, 2025)
    cg = I.t_cg(g)
    st = next(r for r in cg["rows"] if r[0].startswith("Short-term, section 111A"))
    lt = next(r for r in cg["rows"] if r[0].startswith("Long-term, section 112A"))
    assert st[2:7] == [2, 2300, 2000, 0, 300] and st[7] == 300                # gains 500, loss 200 set off
    assert lt[6] == 3000 and lt[7] == 3000 and lt[8] == 3000 and lt[9] == 0                # all within the ₹1.25 lakh exemption
    assert any("set off" in n for n in cg["notes"]) and any("carry forward" in n for n in cg["notes"])
    f = I.t_cg_periods(g)
    by = {r[0]: r for r in f["rows"]}
    assert by["111A at 20%"][1:7] == [500, 0, -200, 0, 0, 300] and by["112A at 12.5%"][4] == 3000


def test_dividends_by_period_with_tds_and_us_lines():
    lines = [{"d": "2025-05-28", "sym": "ITC", "name": "ITC Ltd", "isin": "INE154A01025", "amount": 7850.0, "cur": "INR"},
             {"d": "2026-02-04", "sym": "ITC", "name": "ITC Ltd", "isin": "INE154A01025", "amount": 6500.0, "cur": "INR"},
             {"d": "2026-03-20", "sym": "TCS", "name": "TCS", "isin": "", "amount": 110.0, "cur": "INR", "tds": 11.0}]
    us_div = {"stocks": [{"symbol": "AAPL", "inr": 2200.0, "tax_inr": 550.0, "lines": [{"d": "2025-08-14", "inr": 2200.0}]}], "estimated": False}
    g = g_for([], 2025, div_lines=lines, div_source="files", us_div=us_div)
    t = I.t_os(g)
    itc = next(r for r in t["rows"] if r[0] == "ITC Ltd")
    assert itc[3:8] == [7850, 0, 0, 6500, 0] and itc[8] == 14350 and itc[9] == 1435 and itc[10] == "expected"
    tcs = next(r for r in t["rows"] if r[0] == "TCS")
    assert tcs[7] == 110 and tcs[9] == 11 and tcs[10] == "your file"
    aapl = next(r for r in t["rows"] if r[0] == "AAPL")
    assert aapl[2] == "United States" and aapl[4] == 2200 and aapl[9] == 550
    total = t["rows"][-1]
    assert total[0] == "Total" and total[8] == 14350 + 110 + 2200


def test_business_and_tax_paid():
    biz = [{"seg": "fno", "fy": 2025, "first": "2025-04-02", "last": "2026-03-20", "pnl": 50000.0, "turnover": 900000.0,
            "turnover_contract": 400000.0, "charges": 8000.0, "stt": 3000.0, "trades": 120}]
    c = T.compute([b("2025-06-02", 10, 100), s("2025-06-02", 10, 110)], today=TODAY)
    y = T.with_total(T.year(2025, c["realised"], c["intraday"], limit=None), biz, None)
    g = g_for([], 2025, y=y, tds=12000.0, paid=[{"d": "2025-06-14", "amount": 5000.0}, {"d": "2026-03-15", "amount": 20000.0},
                                                {"d": "2026-07-20", "amount": 3000.0}])
    t = I.t_business(g)
    intra = t["rows"][0]
    assert intra[0].startswith("Intraday") and intra[2] == 100 and intra[6] == 100
    fno = next(r for r in t["rows"] if r[0].startswith("F&O"))
    assert fno[2:7] == [900000, 400000, 50000, 8000, 42000]
    assert any("sum of the absolute profit or loss" in n for n in t["notes"]) and any("separately" in n for n in t["notes"])
    p = I.t_tax_paid(g)
    kinds = [(r[0], r[2]) for r in p["rows"]]
    assert ("Advance tax", 5000) in kinds and ("Advance tax", 20000) in kinds and ("Self-assessment tax", 3000) in kinds
    assert ("Total advance tax", 25000) in kinds and ("Total self-assessment tax", 3000) in kinds and ("TDS you entered (Schedule TDS)", 12000) in kinds


# ---------- the files ----------
def test_the_workbook_reads_back():
    data = xlsx_write.workbook([("One", [["Head", "Value"], ["a", 1.5], ["=1+1", 2]], {0}), ("A/B: [x]", [["x"]], None),
                                ("One", [["dup"]], None)])
    got = dict(hf.sheets(data))
    assert list(got) == ["One", "A-B- -x-", "One 2"]
    assert got["One"][:3] == [["Head", "Value"], ["a", "1.5"], ["=1+1", "2"]]


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    fx_rates.seed()
    yield built
    from app import money_fx
    money_fx.forget()
    built["close"]()


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "pb"), ("RAZORPAY_PLAN_PRO", "pp")):
        monkeypatch.setattr(settings, k, v)


def load_trades(c, h, advance=True):
    csv = ("Date,Symbol,ISIN,Type,Quantity,Price\n2017-01-02,RELIANCE,INE002A01018,BUY,10,100\n2025-06-03,RELIANCE,INE002A01018,SELL,4,300\n"
           "2024-01-10,RELIANCE,INE002A01018,BUY,5,200\n2025-02-03,RELIANCE,INE002A01018,SELL,2,250\n")
    r = c.post("/tax/import", headers=h, json={"filename": "trades.csv", "data": base64.b64encode(csv.encode()).decode(), "mode": "replace"})
    assert r.status_code == 200, r.text
    assert c.put("/tax/fmv", headers=h, json={"symbol": "RELIANCE", "fmv": 150}).status_code == 200
    r = c.post("/money/us-tax/trades", headers=h, json={"d": "2023-03-01", "side": "B", "sym": "AAPL", "qty": 3, "price": 150})
    assert r.status_code == 200
    assert c.post("/money/us-tax/trades", headers=h, json={"d": "2025-08-14", "side": "S", "sym": "AAPL", "qty": 2, "price": 220}).status_code == 200
    assert not advance or c.put("/money/advance-tax", headers=h, json={"fy": 2025, "tds": 1000, "paid": [{"d": "2025-12-12", "amount": 4000}]}).status_code == 200


def test_preview_and_every_export(w):
    c = w["client"]
    load_trades(c, PRO)
    v = c.get("/money/itr?fy=2025", headers=PRO).json()
    assert v["label"] == "FY 2025-26" and v["ay"] == "2026-27" and not v["locked"] and "not a filed return" in v["label_text"]
    by = {t["key"]: t for t in v["tables"]}
    assert set(by) == {"112a", "112a_portal", "cg", "cg_periods", "os", "business", "tax_paid", "foreign", "form67", "fa"}
    acme = next(r for r in by["112a"]["rows"] if r[2] == "INE002A01018")
    assert acme[0] == "BE" and acme[1] == "AE" and acme[4] == 4 and acme[10] == 150
    assert any(r[0].startswith("Long-term, section 112, foreign shares") for r in by["cg"]["rows"])
    assert any(r[0] == "Advance tax" and r[2] == 4000 for r in by["tax_paid"]["rows"])
    assert by["fa"]["rows"] and by["fa"]["rows"][0][1] == "2-UNITED STATES OF AMERICA"
    assert v["sources"] and v["assumptions"][0] == I.LABEL
    # the workbook
    r = c.get("/money/itr/export?fy=2025&format=xlsx", headers=PRO)
    assert r.status_code == 200 and "spreadsheetml" in r.headers["content-type"]
    sheets = dict(hf.sheets(r.content))
    assert "Read me" in sheets and "112A" in sheets and "FA, Table A3" in sheets
    assert sheets["Read me"][1][0] == I.LABEL and sheets["112A"][2][0] == "Share/Unit acquired (1a)"
    # the CSV files
    r = c.get("/money/itr/export?fy=2025&format=zip", headers=PRO)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert {"README.txt", "schedule-112A.csv", "schedule-112A-portal-upload.csv", "schedule-CG.csv", "schedule-FA-A3.csv",
            "schedule-OS-dividends.csv", "ITR-3-business-income.csv", "schedule-IT-tax-paid.csv"} <= set(z.namelist())
    assert I.LABEL in z.read("schedule-CG.csv").decode("utf-8-sig") and I.LABEL not in z.read("schedule-112A-portal-upload.csv").decode("utf-8-sig")
    # the pack for the CA
    r = c.get("/money/itr/export?fy=2025&format=pdf", headers=PRO)
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and len(r.content) > 5000
    from pypdf import PdfReader
    text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Pack for your CA" in text and "not a filed return" in text and "Schedule 112A" in text and "Table A3" in text
    assert "F&O" in text and "&amp;" not in text                  # regression: table cells were escaped twice
    tax_pdf = c.get("/tax/export?fy=2025&format=pdf", headers=PRO).content
    assert "&amp;" not in " ".join(p.extract_text() for p in PdfReader(io.BytesIO(tax_pdf)).pages)
    assert c.get("/money/itr/export?fy=2025&format=docx", headers=PRO).status_code == 422


def test_a_year_with_nothing_still_exports(w):
    c = w["client"]
    assert c.get("/money/itr?fy=2023", headers=PRO).status_code == 200
    for f in ("xlsx", "zip", "pdf"):
        assert c.get(f"/money/itr/export?fy=2023&format={f}", headers=PRO).status_code == 200


def test_free_sees_what_each_schedule_would_hold(w, paid):
    c = w["client"]
    load_trades(c, FREE, advance=False)              # advance tax amounts are Pro too
    v = c.get("/money/itr?fy=2025", headers=FREE).json()
    assert v["locked"] and v["plan"] == "Pro"
    t = next(t for t in v["tables"] if t["key"] == "112a")
    assert t["count"] >= 1 and "rows" not in t and "columns" not in t
    assert c.get("/money/itr/export?fy=2025&format=xlsx", headers=FREE).status_code == 402
