"""Harsh correctness review of the Money and Invest sides (RC3M): the numbers checked against hand sums, and what was wrong
fixed at the root. Each test names the finding it proves."""
import json
from datetime import date, datetime, timezone

import pytest

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
