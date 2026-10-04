"""Mutual funds (Money space): reading the password-protected CAS PDF (synthetic statements, never a real one) and the
CSV, the daily NAV file, first-in-first-out lots, every tax rule (equity 111A and 112A with grandfathering, the
specified-fund rule and its 2025 redefinition, the 24- and 36-month rules with and without indexation, mergers,
gifts, reversals), XIRR, the page, the plan limits, the tax report, privacy and deletion."""
import base64
import json
from pathlib import Path

import pytest

from app import db, money_mf as M, money_mf_nav as N, tax_lots as T, tax_total
from app.config import settings
from tests import world
from tests.casmaker import make_cas

FIX = Path(__file__).parent / "fixtures" / "mf"
DAILY = (FIX / "NAVAll.txt").read_text()
GF2018 = (FIX / "nav_2018-01-31.txt").read_text()
PRO, BASIC, FREE = world.headers("pro-token"), world.headers("basic-token"), world.headers("free-token")
PAN = "ABCDE1234F"


@pytest.fixture
def navfiles(monkeypatch):
    """The two public NAV files, from fixtures; counts how often each is read."""
    calls = {"daily": 0, "gf": 0}

    def fetch(url):
        if url == N.DAILY_URL:
            calls["daily"] += 1
            return DAILY
        calls["gf"] += 1
        return GF2018
    monkeypatch.setattr(N, "fetch_text", fetch)
    monkeypatch.setattr(N, "MIN_SCHEMES", 1)
    N.forget()
    yield calls
    N.forget()


@pytest.fixture
def w(monkeypatch, navfiles):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "pb"), ("RAZORPAY_PLAN_PRO", "pp")):
        monkeypatch.setattr(settings, k, v)


def flexi(rows=None, close="1,100.000"):
    return {"code": "X12G", "name": "Example Flexi Cap Fund - Direct Plan - Growth", "isin": "INF000X01AB1",
            "rows": rows or [("10-Jan-2018", "Purchase - via Internet", "10,000.00", "1,000.000", "10.0000", "1,000.000"),
                             ("10-Jan-2018", "*** Stamp Duty ***", "0.50", "", "", ""),
                             ("05-Feb-2019", "Systematic Investment Purchase Instalment No 1", "5,000.00", "400.000", "12.5000", "1,400.000"),
                             ("15-Aug-2024", "Redemption - ELECTRONIC PAYMENT", "(6,000.00)", "(300.000)", "20.0000", "1,100.000"),
                             ("15-Aug-2024", "*** STT Paid ***", "0.06", "", "", "")],
            "close": close, "nav": "25.0000", "nav_date": "30-Sep-2026", "cost": "11,000.00", "value": "27,500.00"}


def debt():
    return {"code": "S20G", "name": "Sample Short Duration Fund - Direct Plan - Growth", "isin": "INF111Y01SD2",
            "rows": [("03-Jul-2023", "Purchase", "20,000.00", "1,000.000", "20.0000", "1,000.000"),
                     ("02-Sep-2025", "Redemption", "(12,500.00)", "(500.000)", "25.0000", "500.000")],
            "close": "500.000", "nav": "30.0000", "nav_date": "30-Sep-2026", "cost": "10,000.00", "value": "15,000.00"}


def statement(*schemes, password=PAN, **kw) -> bytes:
    return make_cas(password, [{"amc": "Example Mutual Fund", "folio": "1234567 / 89", "schemes": list(schemes)}], **kw)


def upload(c, raw: bytes, name="cas.pdf", password=PAN, headers=PRO, mode="add"):
    return c.post("/money/mutual-funds/import", headers=headers,
                  json={"filename": name, "data": base64.b64encode(raw).decode(), "password": password, "mode": mode})


def data_of(schemes: list[dict], txns: list[dict]) -> dict:
    return {**M.empty(), "schemes": schemes, "txns": txns}


def sch(k="F|A", name="Fund A", folio="F"):
    return {"k": k, "name": name, "folio": folio, "isin": "", "amfi": ""}


def tx(d, t, u=None, a=None, k="F|A", n=None):
    return {"k": k, "d": d, "t": t, "u": u, "a": a, "n": n}


def gains_of(kind, txns, gf=None, schemes=None):
    schemes = schemes or [sch()]
    return M.compute(data_of(schemes, txns), {s["k"]: kind for s in schemes}, gf or {})


# ---------- the public NAV file ----------
def test_nav_file_reads_categories_fund_houses_and_isins():
    d = N.parse(DAILY)
    s = d["schemes"]["900002"]
    assert s["name"] == "Example Flexi Cap Fund - Direct Plan - IDCW" and s["nav"] == 14.5 and s["date"] == "2026-10-03"
    assert s["category"] == "Equity Scheme - Flexi Cap Fund" and s["amc"] == "Example Mutual Fund"
    assert d["isin"]["INF000X01AD7"] == "900002" and d["isin"]["INF000X01AC9"] == "900002"
    assert "900021" not in d["schemes"]                       # N.A. NAV: left out
    assert d["schemes"]["900070"]["category"] == "Income" and d["schemes"]["900001"]["isin2"] == ""


def test_nav_history_report_has_its_own_column_order():
    d = N.parse(GF2018)
    assert d["schemes"]["900001"]["nav"] == 12.0 and d["schemes"]["900001"]["isin"] == "INF000X01AB1"
    assert d["schemes"]["900001"]["date"] == "2018-01-31"


def test_nav_file_garbage_and_empty():
    assert N.parse("")["schemes"] == {} and N.parse("<html>Access denied</html>")["schemes"] == {}
    assert N.parse("Scheme Code;Net Asset Value\nabc;1\n1;-5\n2;x")["schemes"] == {}


def test_finding_a_scheme_by_code_isin_and_name():
    d = N.parse(DAILY)
    assert N.find(d, code="900003")["name"].endswith("Regular Plan - Growth")
    assert N.find(d, isin="INF000X01AD7")["code"] == "900002"
    assert N.find(d, name="Example Flexi Cap Fund Direct Growth")["code"] == "900001"
    assert N.find(d, name="Example Flexi Cap Fund - Regular Growth")["code"] == "900003"     # plan must match
    assert N.find(d, name="Example Flexi Cap Fund - Direct - Dividend")["code"] == "900002"  # dividend is IDCW
    assert N.find(d, name="Something Else Entirely Fund") is None and N.find(d, name="") is None


def test_daily_file_is_cached_and_the_last_good_copy_survives(w, navfiles, monkeypatch):
    N.forget()
    navfiles["daily"] = 0
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        return DAILY
    monkeypatch.setattr(N, "fetch_text", fetch)
    assert len(N.daily()["schemes"]) == 13 and len(N.daily()["schemes"]) == 13 and calls["n"] == 1
    N.forget()                                     # a restart: the saved copy, without a new read
    assert len(N.daily()["schemes"]) == 13 and calls["n"] == 1
    db.delete_setting(N.DAILY_KEY)
    N.forget()

    def down(url):
        raise OSError("down")
    monkeypatch.setattr(N, "fetch_text", down)
    assert N.daily()["schemes"] == {} and N.daily()["read_at"] is None


def test_31_jan_2018_navs_are_read_once_and_kept(w, monkeypatch):
    N.forget()
    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        return GF2018
    monkeypatch.setattr(N, "fetch_text", fetch)
    g = N.gf_navs()
    assert g["code"]["900010"] == 40.0 and g["isin"]["INF000X01AB1"] == 12.0
    N.forget()
    assert N.gf_navs()["code"]["900001"] == 12.0 and calls["n"] == 1      # saved


# ---------- kinds and categories ----------
@pytest.mark.parametrize("cat,name,kind", [
    ("Equity Scheme - Large Cap Fund", "X Bluechip Fund", "equity"),
    ("Equity Scheme - ELSS", "X Tax Saver", "equity"),
    ("Equity Scheme - Sectoral/ Thematic", "X US Bluechip Equity Fund", "other"),
    ("Debt Scheme - Liquid Fund", "X Liquid Fund", "debt"),
    ("Hybrid Scheme - Conservative Hybrid Fund", "X", "debt"),
    ("Hybrid Scheme - Aggressive Hybrid Fund", "X", "equity"),
    ("Hybrid Scheme - Arbitrage Fund", "X", "equity"),
    ("Hybrid Scheme - Balanced Advantage", "X", "equity"),
    ("Hybrid Scheme - Multi Asset Allocation", "X", "hybrid"),
    ("Hybrid Scheme - Balanced Hybrid Fund", "X", "hybrid"),
    ("Other Scheme - Index Funds", "X Nifty 50 Index Fund", "equity"),
    ("Other Scheme - Index Funds", "X Crisil IBX Gilt Index - Apr 2032 Fund", "debt"),
    ("Other Scheme - FoF Overseas", "X US Equity Fund of Fund", "other"),
    ("Other Scheme - Gold ETF", "X Gold ETF", "other"),
    ("Income", "X Fixed Maturity Plan", "debt"),
    ("", "Unknown Liquid Fund", "debt"),
    ("", "Unknown Flexi Cap Fund", "equity"),
])
def test_kind_from_category_and_name(cat, name, kind):
    assert M.kind_of(cat, name) == kind


def test_broad_class_for_the_allocation():
    assert M.broad_of("Equity Scheme - Flexi Cap Fund", "equity") == ("Equity", "Flexi Cap Fund")
    assert M.broad_of("Other Scheme - Index Funds", "equity") == ("Index funds", "")
    assert M.broad_of("Other Scheme - FoF Overseas", "other") == ("Funds of funds", "FoF Overseas")
    assert M.broad_of("Income", "debt") == ("Debt", "Income") and M.broad_of("", "hybrid") == ("Hybrid", "")


# ---------- reading the statement ----------
def test_cas_pdf_is_read_with_its_password():
    got = M.parse_cas(statement(flexi(), debt()), PAN)
    assert len(got["schemes"]) == 2 and got["period"] == "2017-01-01"
    s = got["schemes"][0]
    assert s["name"] == "Example Flexi Cap Fund - Direct Plan - Growth" and s["folio"] == "1234567 / 89" and s["amc"] == "Example Mutual Fund"
    assert s["stmt_nav"] == 25.0 and s["stmt_date"] == "2026-09-30"
    ts = [t for t in got["txns"] if t["k"] == s["k"]]
    assert [t["t"] for t in ts] == ["purchase", "stamp", "sip", "redeem", "stt"]
    assert ts[0] == {"k": s["k"], "d": "2018-01-10", "t": "purchase", "u": 1000.0, "a": 10000.0, "n": 10.0}
    assert ts[3]["u"] == -300.0 and ts[3]["a"] == 6000.0 and ts[1]["a"] == 0.5 and ts[1]["u"] is None
    assert "PAN" not in json.dumps(got) and "AAAAA0000A" not in json.dumps(got) and "test@example.com" not in json.dumps(got)


def test_cas_wrong_password_and_not_a_cas():
    with pytest.raises(M.FileError, match="password"):
        M.parse_cas(statement(flexi()), "WRONG")
    with pytest.raises(M.FileError):
        M.parse_cas(b"%PDF-1.4 not really", "")
    from tests.pdfmaker import make_pdf
    with pytest.raises(M.FileError, match="doesn't look like"):
        M.parse_cas(make_pdf(["A letter about something else"]), "")


def test_cas_with_an_opening_balance_and_dividends_switches_and_reversal():
    rows = [("01-Apr-2020", "Purchase", "1,000.00", "100.000", "10.0000", "600.000"),
            ("02-Apr-2020", "Purchase Reversal - cheque dishonoured", "(1,000.00)", "(100.000)", "10.0000", "500.000"),
            ("10-May-2021", "IDCW Reinvestment @ Rs.1.00 per unit", "50.00", "4.000", "12.5000", "504.000"),
            ("11-Jun-2021", "Switch Out - To Sample Short Duration Fund", "(1,300.00)", "(100.000)", "13.0000", "404.000")]
    s = {**flexi(rows, close="404.000"), "open": "500.000", "name": "Example Flexi Cap Fund - Direct Plan - IDCW", "isin": "INF000X01AC9"}
    got = M.parse_cas(statement(s, period=("01-Apr-2020", "30-Sep-2026")), PAN)
    types = [(t["t"], t["u"]) for t in got["txns"]]
    assert types == [("opening", 500.0), ("purchase", 100.0), ("reversal", -100.0), ("div_reinvest", 4.0), ("switch_out", -100.0)]
    assert got["txns"][0]["d"] == "2020-04-01" and got["txns"][0]["a"] is None


def test_csv_import_with_its_own_headers_and_bad_lines():
    raw = ("Transaction Date,Scheme Name,ISIN,AMFI Code,Units,Amount (INR),Transaction Type,NAV\n"
           "2024-01-15,Example Flexi Cap Fund - Direct Plan - Growth,INF000X01AB1,,100,\"2,000.00\",Purchase,20\n"
           "16/02/2024,Example Flexi Cap Fund - Direct Plan - Growth,INF000X01AB1,,50,1100,SIP,22\n"
           "17-Mar-2025,Example Flexi Cap Fund - Direct Plan - Growth,INF000X01AB1,,30,750,Redemption,25\n"
           "17-Mar-2025,Example Flexi Cap Fund - Direct Plan - Growth,INF000X01AB1,,,0.01,STT,\n"
           "18-03-2025,Sample Short Duration Fund,,900020,10,300,Switch In,30\n"
           "not a date,X,INF000X01AB1,,1,1,Purchase,1\n"
           "2025-01-01,X,INF000X01AB1,,1,1,Lunch,1\n"
           "2025-01-01,X,INF000X01AB1,,,1,Purchase,1\n").encode()
    got = M.parse_csv(raw)
    assert [t["t"] for t in got["txns"]] == ["purchase", "sip", "redeem", "stt", "switch_in"]
    assert got["txns"][2]["u"] == -30.0 and got["txns"][0]["a"] == 2000.0 and got["txns"][1]["d"] == "2024-02-16"
    assert {s["amfi"] for s in got["schemes"]} == {"", "900020"} and len(got["schemes"]) == 2
    assert [p["line"] for p in got["problems"]] == [7, 8, 9]
    with pytest.raises(M.FileError, match="header"):
        M.parse_csv(b"a,b,c\n1,2,3\n")
    with pytest.raises(M.FileError, match="No transactions"):
        M.parse_csv(b"Date,Scheme,Units,Type\nx,y,1,buy\n")


def test_merge_skips_duplicates_and_a_later_opening_balance():
    first = M.parse_cas(statement(flexi()), PAN)
    data, n = M.merge(M.empty(), first, None)
    assert n["added"] == 5 and n["duplicates"] == 0
    again, n = M.merge(data, first, None)
    assert n["added"] == 0 and n["duplicates"] == 5
    later = M.parse_cas(statement({**flexi([("01-Jan-2026", "Purchase", "2,500.00", "100.000", "25.0000", "1,200.000")], close="1,200.000"),
                                   "open": "1,100.000"},
                                  period=("01-Jan-2025", "30-Sep-2026")), PAN)
    later["schemes"][0]["k"] = first["schemes"][0]["k"]
    assert later["txns"][0]["t"] == "opening"
    merged, n = M.merge(data, later, None)
    assert n["added"] == 1 and not any(t["t"] == "opening" for t in merged["txns"])


def test_merge_keeps_the_biggest_schemes_within_a_limit():
    got = {"schemes": [sch(f"F|{i}", f"Fund {i}") for i in range(7)],
           "txns": [tx("2024-01-01", "purchase", 10, 1000 * (i + 1), k=f"F|{i}") for i in range(7)]}
    data, n = M.merge(M.empty(), got, 5)
    assert [s["k"] for s in data["schemes"]] == ["F|6", "F|5", "F|4", "F|3", "F|2"]
    assert n["over_limit"] == ["Fund 1", "Fund 0"] and n["added"] == 5


# ---------- lots and the tax rules ----------
def test_equity_fifo_short_and_long_term_with_stamp_duty():
    c = gains_of("equity", [tx("2023-01-10", "purchase", 100, 1000), tx("2023-01-10", "stamp", a=0.05),
                            tx("2023-06-01", "purchase", 100, 1200), tx("2024-03-01", "redeem", -150, 2250)])
    a, b = c["realised"]
    assert (a["bought"], a["qty"], a["term"], round(a["cost"], 2), a["sale"]) == ("2023-01-10", 100, "LT", 1000.05, 1500)
    assert (b["bought"], b["qty"], b["term"], b["cost"], b["sale"], b["rate"]) == ("2023-06-01", 50, "ST", 600, 750, 0.15)
    assert a["rate"] == 0.10 and "bucket" not in a
    assert c["lots"]["F|A"] == [{"d": "2023-06-01", "u": 50, "cost": 600, "gift": False}]


def test_equity_twelve_months_and_the_july_2024_rates():
    c = gains_of("equity", [tx("2023-07-23", "purchase", 10, 100), tx("2024-07-23", "redeem", -5, 60), tx("2024-07-24", "redeem", -5, 70)])
    a, b = c["realised"]
    assert a["term"] == "ST" and a["rate"] == 0.20          # exactly 12 months: still short term, at the new rate
    assert b["term"] == "LT" and b["rate"] == 0.125


def test_grandfathering_at_the_31_jan_2018_nav():
    txns = [tx("2017-06-01", "purchase", 100, 1000), tx("2017-06-01", "purchase", 100, 1000, k="F|B"),
            tx("2016-06-01", "purchase", 100, 1000, k="F|C"),
            tx("2019-06-01", "redeem", -100, 1500), tx("2019-06-01", "redeem", -100, 1100, k="F|B"), tx("2018-03-01", "redeem", -100, 1500, k="F|C")]
    schemes = [sch(), sch("F|B", "B"), sch("F|C", "C")]
    c = M.compute(data_of(schemes, txns), {"F|A": "equity", "F|B": "equity", "F|C": "equity"}, {"F|A": 12.0, "F|B": 12.0})
    r = {x["key"]: x for x in c["realised"]}
    assert r["F|A"]["cost"] == 1200 and r["F|A"]["gf"] == "applied" and r["F|A"]["gain"] == 300     # NAV 12 on 31 Jan 2018
    assert r["F|B"]["cost"] == 1100 and r["F|B"]["gain"] == 0          # not above the sale value
    assert r["F|C"]["gf"] is None and r["F|C"]["term"] == "LT"         # sold before 1 Apr 2018: exempt then
    missing = gains_of("equity", [tx("2017-06-01", "purchase", 100, 1000), tx("2019-06-01", "redeem", -100, 1500)])
    assert missing["realised"][0]["gf"] == "missing" and missing["realised"][0]["cost"] == 1000
    y = T.year(2017, c["realised"], [])
    assert y["exempt_old"] == 500 and y["buckets"] == []


def test_debt_bought_from_april_2023_is_always_short_term_at_slab_rate():
    c = gains_of("debt", [tx("2023-04-01", "purchase", 100, 1000), tx("2026-06-01", "redeem", -100, 1300)])
    r = c["realised"][0]
    assert r["term"] == "ST" and r["bucket"] == "st_slab" and r["rate"] is None and r["gain"] == 300
    old = gains_of("debt", [tx("2023-03-31", "purchase", 100, 1000), tx("2025-04-01", "redeem", -100, 1300)])
    assert old["realised"][0]["bucket"] == "lt_112" and old["realised"][0]["rate"] == 0.125      # 24 months and a day


def test_older_debt_24_months_from_july_2024_and_36_months_with_indexation_before():
    after = gains_of("debt", [tx("2022-08-01", "purchase", 100, 1000), tx("2024-08-01", "redeem", -50, 600), tx("2024-08-02", "redeem", -50, 600)])
    a, b = after["realised"]
    assert a["term"] == "ST" and a["bucket"] == "st_slab"        # exactly 24 months
    assert b["term"] == "LT" and b["bucket"] == "lt_112" and b["cost"] == 500
    before = gains_of("debt", [tx("2020-05-01", "purchase", 100, 1000), tx("2023-05-01", "redeem", -50, 700), tx("2023-05-02", "redeem", -50, 700)])
    a, b = before["realised"]
    assert a["term"] == "ST" and a["bucket"] == "st_slab"        # exactly 36 months
    assert b["bucket"] == "lt_112i" and b["rate"] == 0.20
    assert round(b["cost"], 2) == round(500 * 348 / 301, 2) and round(b["gain"], 2) == round(700 - 500 * 348 / 301, 2)
    assert b["actual_cost"] == 500
    gap = gains_of("debt", [tx("2021-08-01", "purchase", 100, 1000), tx("2024-07-22", "redeem", -100, 1300)])
    assert gap["realised"][0]["term"] == "ST"                  # 35 months, sold before 23 Jul 2024


def test_gold_and_overseas_funds_follow_the_2025_redefinition():
    before = gains_of("other", [tx("2023-06-01", "purchase", 100, 1000), tx("2025-03-31", "redeem", -100, 1300)])
    assert before["realised"][0]["bucket"] == "st_slab"           # specified fund until 31 Mar 2025
    after = gains_of("other", [tx("2023-06-01", "purchase", 100, 1000), tx("2025-07-01", "redeem", -100, 1300)])
    assert after["realised"][0]["bucket"] == "lt_112"             # no longer specified: 24 months, 12.5%
    hybrid = gains_of("hybrid", [tx("2023-06-01", "purchase", 100, 1000), tx("2024-06-01", "redeem", -100, 1300)])
    assert hybrid["realised"][0]["bucket"] == "st_slab" and hybrid["realised"][0].get("specified") is None


def test_switches_gifts_reversals_and_mergers():
    s = [sch(), sch("F|B", "B")]
    k = {"F|A": "equity", "F|B": "equity"}
    c = M.compute(data_of(s, [tx("2022-01-01", "purchase", 100, 1000), tx("2022-01-02", "purchase", 10, 100),
                              tx("2022-01-03", "reversal", -10, 100), tx("2022-06-01", "gift_out", -20, 300),
                              tx("2023-06-01", "merger_out", -80, 1600), tx("2023-06-01", "merger_in", 160, 1600, k="F|B"),
                              tx("2024-06-01", "redeem", -160, 2400, k="F|B")]), k, {})
    assert len(c["realised"]) == 1
    r = c["realised"][0]
    assert r["key"] == "F|B" and r["bought"] == "2022-01-01" and r["qty"] == 160 and r["cost"] == 800 and r["term"] == "LT"
    alone = gains_of("equity", [tx("2022-01-01", "purchase", 100, 1000), tx("2023-06-01", "merger_out", -100, 1600)])
    assert alone["realised"][0]["sale"] == 1600 and "merger" in alone["notes"]


def test_unknown_cost_and_oversold_units_are_kept_out():
    c = gains_of("equity", [tx("2020-04-01", "opening", 50), tx("2021-01-01", "purchase", 10, 100), tx("2022-01-01", "redeem", -70, 1400)])
    assert len(c["realised"]) == 1 and c["realised"][0]["qty"] == 10 and c["unknown"]["F|A"] == 50 and c["short"]["F|A"] == 10


def test_dividends_paid_out_and_stt_by_year():
    c = gains_of("equity", [tx("2024-01-01", "purchase", 100, 1000), tx("2024-03-01", "div_payout", a=50),
                            tx("2024-05-01", "div_payout", a=40), tx("2024-05-01", "redeem", -10, 120), tx("2024-05-01", "stt", a=0.01)])
    assert c["dividends"] == {2023: 50, 2024: 40} and c["stt"] == {2024: 0.01}


# ---------- XIRR ----------
def test_xirr():
    assert M.xirr([("2023-01-01", -1000), ("2024-01-01", 1100)]) == pytest.approx(0.0998, abs=1e-3)   # 365 days
    assert M.xirr([("2020-01-01", -1000), ("2021-01-01", -1000), ("2022-01-01", 2300)]) == pytest.approx(0.0968, abs=1e-3)
    assert M.xirr([("2023-01-01", -1000), ("2024-01-01", 500)]) == pytest.approx(-0.5, abs=2e-3)
    assert M.xirr([("2023-01-01", -1000)]) is None and M.xirr([("2023-01-01", -1000), ("2023-01-10", 1100)]) is None
    assert M.xirr([("2023-01-01", 1000), ("2024-01-01", 1100)]) is None


# ---------- the tax report's year and estimate ----------
def test_fund_buckets_share_set_off_but_not_the_exemption():
    rows = gains_of("debt", [tx("2023-05-01", "purchase", 100, 1000), tx("2025-06-01", "redeem", -100, 1500)])["realised"]
    rows += gains_of("debt", [tx("2020-05-01", "purchase", 100, 1000, k="F|B"), tx("2025-06-01", "redeem", -100, 3000, k="F|B")],
                     schemes=[sch("F|B")])["realised"]
    rows += gains_of("equity", [tx("2025-05-01", "purchase", 100, 1000, k="F|C"), tx("2025-06-02", "redeem", -100, 800, k="F|C")],
                     schemes=[sch("F|C")])["realised"]
    y = T.year(2025, rows, [])
    b = {x["key"]: x for x in y["buckets"]}
    assert b["st_slab"]["gains"] == 500 and b["st_slab"]["slab"] is True and b["st_slab"]["tax"] == 0
    assert b["lt_112"]["gains"] == 2000 and b["lt_112"]["exempt"] == 0     # no section 112A exemption
    # the 200 short-term equity loss goes against the slab-rate gains... after the 20% equity gains (none here)
    assert b["st_slab"]["after_setoff"] == 300
    assert y["tax"] == pytest.approx(2000 * 0.125)
    est = tax_total.estimate(2025, {"regime": "new", "other": 1500000, "salary": 1500000}, y["buckets"], 0, 0)
    assert est["income"]["normal"] == 1500000 - 75000 + 300 and est["income"]["special"] == 2000
    assert any("slab rate" in s for s in est["steps"]) and est["parts"]["capital_gains"] > 2000 * 0.125


def test_estimate_without_funds_is_unchanged():
    base = tax_total.estimate(2025, {"regime": "new", "other": 1500000, "salary": 1500000}, [], 0, 0)
    assert base["income"]["normal"] == 1425000 and not any("Mutual fund" in s for s in base["steps"])


# ---------- the API ----------
def test_upload_view_and_holdings(w):
    c = w["client"]
    r = upload(c, statement(flexi(), debt()))
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["added"] == 7 and got["kind"] == "cas"
    v = got["view"]
    rows = {s["name"]: s for s in v["schemes"]}
    f = rows["Example Flexi Cap Fund - Direct Plan - Growth"]
    assert f["units"] == 1100 and f["nav"] == 25.0 and f["nav_source"] == "daily" and f["nav_date"] == "2026-10-03"
    assert f["value"] == 27500 and f["invested"] == pytest.approx(700 * 10.0005 + 5000, abs=0.01) and f["kind"] == "equity"
    assert f["broad"] == "Equity" and f["xirr"] is not None and f["amfi"] == "900001"
    d = rows["Sample Short Duration Fund - Direct Plan - Growth"]
    assert d["kind"] == "debt" and d["value"] == 15000 and d["invested"] == 10000
    assert v["total"]["value"] == 42500 and v["total"]["held"] == 2
    assert {a["broad"] for a in v["allocation"]} == {"Equity", "Debt"} and sum(a["pct"] for a in v["allocation"]) == pytest.approx(100, abs=0.2)
    g = {y["fy"]: y for y in v["gains"]["years"]}
    assert g[2024]["buckets"][0]["key"] == "lt_new" and g[2025]["buckets"][0]["key"] == "st_slab"
    assert v["gains"]["gf_missing"] == []                      # the 31 Jan 2018 NAV was found
    eq = [r for r in g[2024]["rows"] if r["key"] == f["key"]][0]
    assert eq["gf"] == "applied" and eq["cost"] == pytest.approx(3600)      # 300 units at the 2018 NAV of 12


def test_wrong_password_and_bad_files(w):
    c = w["client"]
    r = upload(c, statement(flexi()), password="nope")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "wrong_password"
    r = upload(c, b"%PDF-1.4 rubbish")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_file"
    r = c.post("/money/mutual-funds/import", headers=PRO, json={"filename": "x.pdf", "data": "%%%", "password": ""})
    assert r.status_code == 400
    r = upload(c, b"hello,world\n1,2", name="x.csv")
    assert r.status_code == 400 and "header" in r.json()["detail"]["message"]
    assert c.get("/money/mutual-funds", headers=PRO).json()["schemes"] == []


def test_neither_the_pdf_nor_the_password_nor_the_investor_is_stored(w):
    c = w["client"]
    assert upload(c, statement(flexi(), name="SECRET PERSON")).status_code == 200
    raw = db.get_setting("mf:u-pro")
    assert raw and PAN not in raw and "SECRET PERSON" not in raw and "test@example.com" not in raw and "AAAAA0000A" not in raw
    assert "%PDF" not in raw


def test_csv_upload_and_the_add_and_replace_modes(w):
    c = w["client"]
    csv1 = b"Date,Scheme,ISIN,Units,Amount,Type\n2024-01-15,Example Flexi Cap Fund - Direct Plan - Growth,INF000X01AB1,100,2000,Purchase\n"
    assert upload(c, csv1, name="mine.csv").json()["added"] == 1
    assert upload(c, csv1, name="mine.csv").json()["duplicates"] == 1
    assert upload(c, statement(flexi())).json()["added"] == 5
    v = c.get("/money/mutual-funds", headers=PRO).json()
    assert len(v["schemes"]) == 2 and len(v["files"]) == 2
    r = upload(c, csv1, name="mine.csv", mode="replace").json()
    assert len(r["view"]["schemes"]) == 1 and r["view"]["txns"] == 1


def test_kind_and_31_jan_2018_nav_can_be_set(w):
    c = w["client"]
    v = upload(c, statement(flexi(), debt())).json()["view"]
    k = next(s["key"] for s in v["schemes"] if s["kind"] == "debt")
    v = c.put("/money/mutual-funds/kind", headers=PRO, json={"key": k, "kind": "hybrid"}).json()
    s = next(s for s in v["schemes"] if s["key"] == k)
    assert s["kind"] == "hybrid" and s["kind_set"] and s["kind_auto"] == "debt"
    assert c.put("/money/mutual-funds/kind", headers=PRO, json={"key": k, "kind": None}).json()["schemes"]
    assert c.put("/money/mutual-funds/kind", headers=PRO, json={"key": "nope", "kind": "debt"}).status_code == 404
    assert c.put("/money/mutual-funds/kind", headers=PRO, json={"key": k, "kind": "stocks"}).status_code == 422
    e = next(s["key"] for s in v["schemes"] if s["kind"] == "equity")
    v = c.put("/money/mutual-funds/fmv", headers=PRO, json={"key": e, "nav": 15}).json()
    s = next(s for s in v["schemes"] if s["key"] == e)
    assert s["fmv_2018"] == 15 and s["fmv_yours"]
    row = [r for y in v["gains"]["years"] if y["fy"] == 2024 for r in y["rows"]][0]
    assert row["cost"] == pytest.approx(4500)
    assert c.put("/money/mutual-funds/fmv", headers=PRO, json={"key": e, "nav": -1}).status_code == 422


def test_free_keeps_five_schemes_and_no_gains_once_payments_are_live(w, paid):
    c = w["client"]
    schemes = [{**debt(), "code": f"S{i}", "name": f"Sample Fund Number {i} - Direct Plan - Growth", "isin": f"INF111Y0{i}XX0"} for i in range(7)]
    r = upload(c, statement(*schemes), headers=FREE).json()
    assert len(r["view"]["schemes"]) == 5 and len(r["over_limit"]) == 2 and r["limit"] == 5 and r["upgrade"]
    assert r["view"]["gains"] is None and r["view"]["gains_allowed"] is False and r["view"]["gains_plan"] == "Basic"
    b = upload(c, statement(*schemes), headers=BASIC).json()
    assert len(b["view"]["schemes"]) == 7 and b["view"]["gains"] is not None and b["limit"] is None
    t = c.get("/tax", headers=FREE).json()
    assert t["mf"] == {"allowed": False, "count": 0, "plan": "Basic"}


def test_tax_report_adds_fund_gains_to_the_estimate(w):
    c = w["client"]
    upload(c, statement(flexi(), debt()))
    t = c.get("/tax", headers=PRO).json()
    assert t["mf"]["allowed"] and t["mf"]["count"] == 2
    y = {y["fy"]: y for y in t["years"]}
    assert y[2025]["mutual_funds"]["slab"] == pytest.approx(2500) and y[2024]["mutual_funds"]["equity"] > 0
    assert any(b["key"] == "st_slab" for b in y[2025]["buckets"])
    assert any(l["label"] == "Mutual fund gains taxed at slab rates" for l in y[2025]["total"]["lines"])
    names = t["names"]
    assert any(n.get("mf") for n in names.values())
    r = c.get("/tax/export?fy=2025&format=csv", headers=PRO)
    assert r.status_code == 200 and "Sample Short Duration" in r.text
    assert c.get("/tax/export?fy=2025&format=pdf", headers=PRO).status_code == 200


def test_capital_gains_and_total_value_hooks(w):
    upload(w["client"], statement(flexi(), debt()))
    g = M.capital_gains("u-pro", 2025)
    assert g["fy"] == 2025 and g["buckets"][0]["key"] == "st_slab" and g["count"] == 1 and g["names"]
    assert M.capital_gains("u-pro", 2019)["count"] == 0
    assert M.total_value("u-pro") == 42500 and M.total_value("nobody") == 0.0
    assert M.for_tax("nobody") == {"rows": [], "names": {}, "years": {}}


def test_statement_nav_when_the_daily_file_is_down(w, monkeypatch):
    def down(url):
        raise OSError("down")
    monkeypatch.setattr(N, "fetch_text", down)
    N.forget()
    v = upload(w["client"], statement(flexi())).json()["view"]
    s = v["schemes"][0]
    assert s["nav"] == 25.0 and s["nav_source"] == "statement" and s["nav_date"] == "2026-09-30" and s["kind"] == "equity"


def test_elss_lock_in(w):
    s = {"code": "E1", "name": "Example Tax Saver Fund - Direct Plan - Growth", "isin": "INF000X01EL1",
         "rows": [("10-Jan-2025", "Purchase", "8,000.00", "100.000", "80.0000", "100.000"),
                  ("10-Jan-2026", "Purchase", "8,000.00", "100.000", "80.0000", "200.000")],
         "close": "200.000", "nav": "80.0000", "nav_date": "30-Sep-2026", "cost": "16,000.00", "value": "16,000.00"}
    v = upload(w["client"], statement(s)).json()["view"]
    e = v["schemes"][0]["elss"]
    assert e == {"locked_units": 200, "next_free": "2028-01-10", "all_free": "2029-01-10"}


def test_delete_my_fund_data(w):
    c = w["client"]
    upload(c, statement(flexi()))
    assert db.get_setting("mf:u-pro")
    assert c.delete("/money/mutual-funds", headers=PRO).json() == {"deleted": True}
    assert db.get_setting("mf:u-pro") is None and c.get("/money/mutual-funds", headers=PRO).json()["schemes"] == []
    assert c.get("/money/mutual-funds").status_code == 401


def test_other_users_never_see_my_funds(w):
    c = w["client"]
    upload(c, statement(flexi()))
    assert c.get("/money/mutual-funds", headers=BASIC).json()["schemes"] == []
    k = c.get("/money/mutual-funds", headers=PRO).json()["schemes"][0]["key"]
    assert c.put("/money/mutual-funds/kind", headers=BASIC, json={"key": k, "kind": "debt"}).status_code == 404


def test_stored_garbage_is_ignored(w):
    db.set_setting("mf:u-pro", json.dumps({"schemes": [{"k": "a", "name": "A"}, 5, None], "txns": [{"k": "a", "d": "x", "t": "purchase"},
                                           {"k": "a", "d": "2024-01-01", "t": "purchase", "u": "lots", "a": 1}, {"k": "b", "d": "2024-01-01", "t": "sip"}],
                                           "kinds": {"a": "weird"}, "fmv": {"a": "x"}}))
    v = w["client"].get("/money/mutual-funds", headers=PRO)
    assert v.status_code == 200 and v.json()["txns"] == 1
    db.set_setting("mf:u-pro", "not json")
    assert w["client"].get("/money/mutual-funds", headers=PRO).status_code == 200
