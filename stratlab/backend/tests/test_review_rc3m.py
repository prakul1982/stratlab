"""Harsh correctness review of the Money and Invest sides (RC3M): the numbers checked against hand sums, and what was wrong
fixed at the root. Each test names the finding it proves."""
import json
from datetime import date, datetime, timezone

import pytest
import time_machine

from app import corp_actions as C, db, main, tax_lots as T
from app.plans import plan_of
from tests import world
from tests.test_corp_actions import FakeIndia, nse

TODAY = date(2026, 10, 5)


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


# ---------- RC3M-001: bonuses and splits older than three years in the tax report ----------
def test_a_bonus_older_than_three_years_is_in_the_history_and_dividends_that_old_are_not():
    feed = FakeIndia(history={"X": [nse("X", "Bonus 1:1", date(2021, 5, 10)), nse("X", "Dividend - Rs 5 Per Share", date(2021, 6, 1)),
                                    nse("X", "Dividend - Rs 6 Per Share", date(2026, 6, 1))]})
    got = C.fetch_history("IN", "X", {"in": feed}, TODAY)
    assert sorted((r["kind"], r["ex_date"]) for r in got) == [("bonus", "2021-05-10"), ("dividend", "2026-06-01")]
    old_split = FakeIndia(history={"X": [nse("X", "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Re 1/- Per Share", date(2019, 3, 4))]})
    assert [(r["kind"], r["factor"]) for r in C.fetch_history("IN", "X", {"in": old_split}, TODAY)] == [("split", 10.0)]


def test_the_tax_report_counts_a_lot_bought_before_an_old_bonus_in_the_shares_sold(w, monkeypatch):
    uid = "u-pro"
    feed = FakeIndia(history={"RELIANCE": [nse("RELIANCE", "Bonus 1:1", date(2021, 5, 10))]})
    monkeypatch.setattr(main.corp_job, "sources", lambda: {"in": feed, "us": None, "cal": None})
    T.save(uid, [{"d": "2019-06-03", "side": "B", "qty": 100, "price": 1000.0, "sym": "RELIANCE", "isin": "INE002A01018", "name": "Reliance"},
                 {"d": "2026-06-03", "side": "S", "qty": 200, "price": 1500.0, "sym": "RELIANCE", "isin": "INE002A01018", "name": "Reliance"}],
           [{"name": "x"}])
    prof = db.get_profile(uid)
    i = main.tax_inputs({**prof, "_plan": plan_of(prof)})
    assert [a["ex_date"] for a in i["acts"]["RELIANCE"]] == ["2021-05-10"]
    c = T.compute(i["trades"], i["acts"], i["fmv"], i["today"])
    assert c["unmatched"] == [] and c["open"] == []
    # 100 shares at ₹1,000 and 100 bonus shares at nothing, sold for 200 x 1,500: a gain of ₹2,00,000, all long term
    assert sorted((r["qty"], r["gain"], r["term"], r["bonus"]) for r in c["realised"]) == [(100, 50000.0, "LT", False), (100, 150000.0, "LT", True)]


def test_a_history_stored_before_old_bonuses_were_kept_is_read_again(w, monkeypatch):
    feed = FakeIndia(history={"Y": [nse("Y", "Bonus 2:1", date(2020, 2, 3))]})
    db.set_setting("corpact:hist:IN:Y", json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="minutes"), "rows": []}))   # a day-fresh copy of the old kind
    assert not C.hist_kept("IN", "Y") and C.hist_stale("IN", C.hist_load("IN", "Y"))
    got = C.history("IN", "Y", {"in": feed}, TODAY)
    assert [(r["kind"], r["ex_date"]) for r in got] == [("bonus", "2020-02-03")]
    assert C.hist_kept("IN", "Y") and not C.hist_stale("IN", C.hist_load("IN", "Y"))
    assert feed.asked == ["Y"]
    C.history("IN", "Y", {"in": feed}, TODAY)
    assert feed.asked == ["Y"]                                      # the new copy stands for the day


# ---------- RC3M-002: a US trades file that would pass the limit is refused whole ----------
def test_a_us_file_past_the_limit_is_refused_not_saved_in_part(w, monkeypatch):
    from app import money_us_tax as us
    uid = "u-pro"
    monkeypatch.setattr(us, "MAX_TRADES", 5)
    rows = lambda n, d: [{"d": d, "side": "B", "sym": "AAPL", "qty": float(i + 1), "price": 100.0, "fees": 0.0, "src": "file"} for i in range(n)]
    assert us.add(uid, rows(3, "2025-01-02"), "a.csv") == (3, 0)
    with pytest.raises(Exception) as e:
        us.add(uid, rows(4, "2025-02-03"), "b.csv")                 # 7 in all: the newest used to vanish, the page saying 4 were added
    assert "7 US trades" in str(e.value) and "up to 5" in str(e.value)
    assert len(us.load(uid)["trades"]) == 3 and len(us.load(uid)["files"]) == 1
    assert us.add(uid, rows(2, "2025-03-04"), "c.csv") == (2, 0) and len(us.load(uid)["trades"]) == 5
    r = w["client"].post("/money/us-tax/import", headers=world.headers("pro-token"),
                         json={"filename": "d.csv", "data": __import__("base64").b64encode(b"Date,Action,Symbol,Quantity,Price\n2025-04-01,Buy,MSFT,1,300\n").decode()})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "too_many" and "6 US trades" in r.json()["detail"]["message"]


# ---------- RC3M-003: dividend TDS at 7.5% from 14 May 2020 to 31 March 2021 ----------
def test_dividend_tds_was_7_5_percent_for_payments_in_the_covid_relief_window():
    from app import money_dividends as D
    assert D.tds_rate("2020-05-13") == 0.10 and D.tds_rate("2020-05-14") == 0.075
    assert D.tds_rate("2021-03-31") == 0.075 and D.tds_rate("2021-04-01") == 0.10 and D.tds_rate(None) == 0.10
    row = lambda d, a: {"d": d, "sym": "ITC", "name": "", "isin": "", "qty": None, "ps": None, "amount": a, "tds": None, "cur": "INR", "src": "csv"}
    # FY 2020-21 (threshold ₹5,000): ₹4,000 on 10 May at 10% and ₹6,000 on 1 Sep at 7.5% -> 400 + 450
    y = D.year(2020, [row("2020-05-10", 4000), row("2020-09-01", 6000)], None)
    assert y["tds"]["expected"] == 850.0 and y["tds"]["rate"] == 0.075 and "7.5%" in y["tds"]["note"]
    assert D.expected_tds(2020, 10000) == 750.0                            # no days given: the year's rate
    # the other years are as before
    y = D.year(2024, [row("2025-01-10", 6000)], None)
    assert y["tds"]["expected"] == 600.0 and y["tds"]["rate"] == 0.10 and y["tds"]["note"] is None
    assert D.expected_tds(2024, 5001) == 500.1 and D.expected_tds(2025, 12000) == 1200
    assert D.year(2020, [row("2020-09-01", 5000)], None)["tds"]["expected"] == 0.0        # not over the threshold


def test_schedule_os_expects_the_reduced_tds_for_that_year(w):
    from app import money_itr as I
    g = {"fy": 2020, "div_lines": [{"d": "2020-09-01", "sym": "ITC", "name": "ITC", "isin": "", "amount": 8000.0, "cur": "INR"}],
         "us_div": None, "div_source": "files"}
    row = I.t_os(g)["rows"][0]
    assert row[-2] == 600.0 and row[-1] == "expected"


# ---------- RC3M-004: the day a PDF is made is India's ----------
def test_the_tax_pdf_is_dated_by_the_india_day():
    import io
    import time_machine
    from datetime import timezone
    from pypdf import PdfReader
    from app import tax_export
    y = T.year(2025, [], [])
    with time_machine.travel(datetime(2026, 10, 26, 22, 30, tzinfo=timezone.utc)):         # 4 AM on 27 Oct in India
        text = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(tax_export.to_pdf(y, {}))).pages)
    assert "Made by StratLab on 27 Oct 2026" in text


def test_the_itr_pack_is_dated_by_the_india_day():
    from app import money_itr
    src = open(money_itr.__file__).read()
    assert '"made": datetime.now(IST)' in src and "datetime.now(timezone.utc)" not in src


# ---------- RC3M-005: the after-tax rate works the saved income under this year's rules ----------
@time_machine.travel(datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc))
def test_the_marginal_rate_uses_this_years_rules_on_income_saved_for_an_older_year(w):
    from app import fixed_income as F, tax_total
    uid = "u-basic"
    cur = 2026
    tax_total.save_inputs(uid, 2023, {"regime": "new", "other": 1000000, "salary": 1000000})
    prof = {**db.get_profile(uid), "_plan": "pro"}
    t, basis, mine, fy = F.tax_basis(prof, None, True)
    assert fy == cur and basis == "estimate" and mine["fy"] == 2023 and mine["rules_fy"] == cur
    # ₹10 lakh of salary is 9.5 lakh after the standard deduction: inside this year's 12 lakh rebate, so the next ₹10,000 of
    # interest is taxed at nothing; under FY 2023-24's own rules (15% from 9 lakh, rebate only to 7 lakh) it was 15.6%
    assert mine["rate"] == 0 and t == 0
    assert F.marginal(2023, {"regime": "new", "other": 1000000, "salary": 1000000})["rate"] == pytest.approx(0.156, abs=1e-4)


def test_the_itr_pack_names_a_file_by_the_india_day_it_was_uploaded():
    from app import money_itr
    assert money_itr._india_day("2026-10-26T22:30+00:00") == "2026-10-27" and money_itr._india_day("2026-10-26T10:00+00:00") == "2026-10-26"
    assert money_itr._india_day("2026-10-26T10:00") == "2026-10-26" and money_itr._india_day(None) == "" and money_itr._india_day("junk") == "junk"
    g = {"files": [{"name": "t.csv", "broker": "Zerodha", "trades": 3, "at": "2026-10-26T22:30+00:00"}], "mf_count": 0, "us_count": 0, "us_div": None,
         "fmv_src": {}, "div_source": "none"}
    assert "uploaded 27 Oct 2026" in money_itr.sources(g)[0]


def test_the_company_card_stays_three_years_while_the_history_keeps_the_old_bonus(w):
    feed = FakeIndia(history={"Z": [nse("Z", "Bonus 1:1", date(2020, 5, 4)), nse("Z", "Dividend - Rs 3 Per Share", date(2026, 6, 1))]})
    got = C.company("IN", "Z", {"in": feed}, TODAY)
    assert [r["kind"] for r in got["past"]] == ["dividend"]                      # the card: the last three years
    assert [r["ex_date"] for r in C.actions_for("IN", "Z", None, TODAY, fetch=False) if r["kind"] == "bonus"] == ["2020-05-04"]   # the tax report's input


# ---------- RC3M-006: the first tax report has every company's bonuses and splits ----------
def test_the_first_tax_report_waits_for_every_companys_bonuses_and_splits(w, monkeypatch):
    uid = "u-pro"
    syms = [f"S{i}" for i in range(12)]                         # more than the eight a holdings page fetches while it waits
    feed = FakeIndia(history={s: [nse(s, "Bonus 1:1", date(2025, 5, 10))] for s in syms})
    monkeypatch.setattr(main.corp_job, "sources", lambda: {"in": feed, "us": None, "cal": None})
    T.save(uid, [t for s in syms for t in ({"d": "2025-01-03", "side": "B", "qty": 100, "price": 100.0, "sym": s, "isin": "", "name": s},
                                              {"d": "2026-06-03", "side": "S", "qty": 200, "price": 150.0, "sym": s, "isin": "", "name": s})],
           [{"name": "x"}])
    prof = db.get_profile(uid)
    i = main.tax_inputs({**prof, "_plan": plan_of(prof)})
    assert all(i["acts"][s] for s in syms) and i["corp_left"] == 0           # the first look, not the second
    assert sorted(feed.asked) == sorted(syms)
    # a company the feed won't answer for is named by count, and its lots are counted as bought
    class Down(FakeIndia):
        def actions_of(self, symbol):
            from app.intel.net import SourceError
            raise SourceError("the exchange", "busy", busy=True)
    monkeypatch.setattr(main.corp_job, "sources", lambda: {"in": Down(), "us": None, "cal": None})
    T.save(uid, [{"d": "2025-01-03", "side": "B", "qty": 100, "price": 100.0, "sym": "NEWCO", "isin": "", "name": "N"}], [{"name": "x"}])
    i = main.tax_inputs({**prof, "_plan": plan_of(prof)})
    assert i["corp_left"] == 1 and i["acts"]["NEWCO"] == []
