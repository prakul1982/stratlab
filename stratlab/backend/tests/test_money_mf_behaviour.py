"""Fund behaviour (Money: mutual funds): the fund's own NAV return beside the user's XIRR and the gap in rupees, the SIP
record, redemptions after a fall from the high, holding periods, reading and keeping the public NAV history (a real
trimmed sample and synthetic ones), the background read, the plan gate and the route."""
import json
from datetime import date
from pathlib import Path

import pytest

from app import db, money_mf as M, money_mf_behaviour as B
from tests import fake_mf_history
from tests.test_money_mf import BASIC, FREE, PRO, navfiles, paid, statement, upload, w  # noqa: F401  (fixtures)

FIX = Path(__file__).parent / "fixtures" / "mf"


@pytest.fixture
def hist(monkeypatch):
    """A synthetic history for scheme 900001 (high of 24 in June 2024, 20 on the day of the redemption); counts reads."""
    calls = []

    def fetch(code, start, end):
        calls.append((code, start, end))
        return fake_mf_history.fetch(code, start, end, first="2022-01-10")
    monkeypatch.setattr(B, "fetch_json", fetch)
    monkeypatch.setattr(B, "BACKGROUND", False)
    monkeypatch.setattr(B, "PAUSE", 0)
    B.forget()
    yield calls
    B.forget()


def sipper():
    return {"code": "X12G", "name": "Example Flexi Cap Fund - Direct Plan - Growth", "isin": "INF000X01AB1",
            "rows": [("10-Jan-2022", "Purchase - via Internet", "10,000.00", "1,000.000", "10.0000", "1,000.000"),
                     ("05-Feb-2022", "Systematic Investment Purchase Instalment No 1", "1,000.00", "100.000", "10.0000", "1,100.000"),
                     ("05-Mar-2022", "Systematic Investment Purchase Instalment No 2", "1,000.00", "100.000", "10.0000", "1,200.000"),
                     ("05-May-2022", "Systematic Investment Purchase Instalment No 3", "1,000.00", "100.000", "10.0000", "1,300.000"),
                     ("06-Jun-2022", "Systematic Investment Purchase Instalment No 4", "1,000.00", "100.000", "10.0000", "1,400.000"),
                     ("15-Aug-2024", "Redemption - ELECTRONIC PAYMENT", "(6,000.00)", "(300.000)", "20.0000", "1,100.000")],
            "close": "1,100.000", "nav": "25.0000", "nav_date": "30-Sep-2026", "cost": "11,000.00", "value": "27,500.00"}


# ---------- the arithmetic ----------
def test_fund_return_is_the_nav_growth_as_a_yearly_rate():
    assert B.annual(10, 20, "2020-01-01", "2020-12-31") == pytest.approx(1.0, abs=0.01)
    assert B.annual(10, 12.1, "2020-01-01", "2022-01-01") == pytest.approx(0.1, abs=0.001)
    assert B.annual(10, 20, "2020-01-01", "2020-01-15") is None          # under 30 days
    assert B.annual(0, 20, "2020-01-01", "2021-01-01") is None and B.annual(10, None, "2020-01-01", "2021-01-01") is None


def test_money_grown_at_the_funds_rate():
    # ₹100 in two years ago at 10% comes to ₹121; ₹50 taken out a year ago stops growing (₹55 less)
    flows = [("2020-01-01", -100.0), ("2021-01-01", 50.0)]
    assert B.grown(flows, 0.10, "2022-01-01") == pytest.approx(121.0 - 55.0, abs=0.2)
    assert B.grown([], 0.1, "2022-01-01") == 0


def test_sip_record_paid_missed_runs_and_stopped():
    s = B.sip_record(["2024-01-05", "2024-02-05", "2024-03-05", "2024-05-05", "2024-06-05", "2024-07-05", "2024-08-05", "2024-08-20"], "2024-09-10")
    assert s["months_paid"] == 7 and s["instalments"] == 8 and s["months_missed"] == 1 and s["missed"] == ["2024-04"]
    assert s["longest_run"] == 4 and (s["longest_from"], s["longest_to"]) == ("2024-05", "2024-08")
    assert s["stopped"] is False and s["current_run"] == 4
    s = B.sip_record(["2023-11-05", "2023-12-05", "2024-01-05"], "2024-03-02")
    assert s["stopped"] is True and s["stopped_after"] == "2024-01" and s["current_run"] == 0 and s["longest_run"] == 3
    assert B.sip_record([], "2024-01-01") is None
    across = B.sip_record(["2023-12-05", "2024-01-05"], "2024-01-20")         # across a year end
    assert across["longest_run"] == 2 and across["months_missed"] == 0


def test_highest_nav_up_to_a_day():
    pts = [["2024-01-01", 10], ["2024-02-01", 15], ["2024-03-01", 12], ["2024-04-01", 18]]
    assert B.high_before(pts, "2024-01-01", "2024-03-15") == (15, "2024-02-01")
    assert B.high_before(pts, "2024-02-02", "2024-03-15") == (12, "2024-03-01")
    assert B.high_before(pts, "2025-01-01", "2025-02-01") is None


def test_ranges_are_split_under_five_years():
    parts = B.chunks("2014-01-01", "2026-10-05")
    assert parts[0][0] == "2014-01-01" and parts[-1][1] == "2026-10-05"
    for a, b in parts:
        assert (date.fromisoformat(b) - date.fromisoformat(a)).days < 5 * 365
    for (_, b), (a, _) in zip(parts, parts[1:]):
        assert (date.fromisoformat(a) - date.fromisoformat(b)).days == 1


# ---------- the NAV history service ----------
def test_reads_the_real_answer_shape():
    got = json.loads((FIX / "nav_history_120505.json").read_text())
    pts = B.parse_history(got)
    assert len(pts) >= 4 and pts[0] == ["2026-09-01", 144.46] and all(a[0] < b[0] for a, b in zip(pts, pts[1:]))
    assert B.parse_history({}) == [] and B.parse_history({"message": "No records to display"}) == []
    assert B.parse_history({"data": {"nav_groups": [{"historical_records": [{"date": "x", "nav": 1}, {"date": "2024-01-01", "nav": "-1"},
                                                                             {"date": "2024-01-02", "nav": "12.5"}]}]}}) == [["2024-01-02", 12.5]]
    assert B.parse_history("<html>") == []


def test_history_is_kept_and_only_the_missing_part_read(w, hist):
    h = B.read("900001", "2022-01-10", "2023-06-30")
    assert h and h["from"] == "2022-01-10" and len(hist) == 1
    assert json.loads(db.get_setting(B.HIST_KEY + "900001"))["to"] == "2023-06-30"
    got, pending = B.histories({"900001": ("2022-02-01", "2023-01-01")})
    assert "900001" in got and pending == [] and len(hist) == 1            # covered: no new read
    B.forget()                                                             # a restart: the kept copy
    got, _ = B.histories({"900001": ("2022-01-10", "2024-08-15")})
    assert len(hist) == 2 and hist[-1][1] == "2023-07-01"                  # only the new part
    assert got["900001"][-1][0] == "2024-08-15"


def test_a_failed_read_is_not_retried_at_once(w, hist, monkeypatch):
    def down(code, a, b):
        hist.append((code, a, b))
        raise OSError("down")
    monkeypatch.setattr(B, "fetch_json", down)
    assert B.histories({"900001": ("2022-01-10", "2024-08-15")}) == ({}, [])
    assert B.histories({"900001": ("2022-01-10", "2024-08-15")}) == ({}, []) and len(hist) == 1


def test_background_read_reports_pending(w, hist, monkeypatch):
    import threading
    go = threading.Event()
    monkeypatch.setattr(B, "BACKGROUND", True)
    real = B.fetch_json

    def slow(code, a, b):
        go.wait(5)
        return real(code, a, b)
    monkeypatch.setattr(B, "fetch_json", slow)
    got, pending = B.histories({"900001": ("2022-01-10", "2024-08-15")})
    assert got == {} and pending == ["900001"]
    got, pending = B.histories({"900001": ("2022-01-10", "2024-08-15")})
    assert pending == ["900001"]                                           # queued once
    go.set()
    for _ in range(100):
        if B.stored("900001"):
            break
        threading.Event().wait(0.05)
    assert B.histories({"900001": ("2022-01-10", "2024-08-15")})[1] == []


# ---------- the page ----------
def test_behaviour_for_a_sip_that_stopped_and_a_sale_after_a_fall(w, hist):
    c = w["client"]
    c.delete("/money/mutual-funds", headers=PRO)
    assert upload(c, statement(sipper())).status_code == 200
    d = c.get("/money/mutual-funds/behaviour", headers=PRO).json()
    assert d["full"] is True and d["pending"] == 0 and d["last_txn"] == "2024-08-15"
    s = d["schemes"][0]
    assert s["held"] is True and s["from"] == "2022-01-10" and s["start_nav"] == 10 and s["end_nav"] == 25
    # 10 to 25 from Jan 2022 to today
    years = (date.fromisoformat(d["as_of"]) - date(2022, 1, 10)).days / 365
    assert s["fund"] == pytest.approx(2.5 ** (1 / years) - 1, abs=1e-4)
    assert s["xirr"] is not None and s["gap_pp"] == pytest.approx((s["xirr"] - s["fund"]) * 100, abs=0.01)
    # the gap in rupees: today's ₹27,500 less the same flows at the fund's rate
    flows = [("2022-01-10", -10000), ("2022-02-05", -1000), ("2022-03-05", -1000), ("2022-05-05", -1000), ("2022-06-06", -1000), ("2024-08-15", 6000)]
    assert s["gap_rupees"] == pytest.approx(27500 - B.grown(flows, s["fund"], d["as_of"]), abs=1)
    sip = s["sip"]
    assert sip["months_paid"] == 4 and sip["missed"] == ["2022-04"] and sip["longest_run"] == 2 and sip["stopped"] is True
    # sold at 20 with the high at 24 on 3 Jun 2024: a 16.7% fall; the 300 units are worth ₹7,500 today
    assert s["high_source"] == "history" and len(s["falls"]) == 1
    f = s["falls"][0]
    assert f["high"] == 24 and f["high_date"] == "2024-06-03" and f["fall_pct"] == 16.7
    assert f["received"] == 6000 and f["worth_today"] == 7500 and f["difference"] == 1500
    # the 300 units sold were the first bought (10 Jan 2022): held 948 days
    assert s["avg_days_held"] == (date(2024, 8, 15) - date(2022, 1, 10)).days
    assert s["long_share"] == pytest.approx(100.0) and s["long_value"] == 27500           # all bought over 3 years ago
    t = d["total"]
    assert t["sips"] == 1 and t["sips_stopped"] == 1 and t["months_missed"] == 1 and t["falls"] == 1 and t["falls_worth_today"] == 7500
    assert t["held_under_year_pct"] == 0 and t["long_share"] == 100
    assert hist and hist[0][0] == "900001" and hist[0][1] == "2022-01-10" and hist[-1][2] == "2024-08-15"
    text = json.dumps(d).lower()
    for word in ("should", "recommend", "switch to", "don't stop", "better"):
        assert word not in text


def test_without_history_the_statement_navs_find_the_high(w, hist, monkeypatch):
    monkeypatch.setattr(B, "fetch_json", lambda *a: {})
    c = w["client"]
    c.delete("/money/mutual-funds", headers=PRO)
    assert upload(c, statement(sipper())).status_code == 200
    s = c.get("/money/mutual-funds/behaviour", headers=PRO).json()["schemes"][0]
    # the statement's NAVs top out at 20 (the sale itself), so no fall is seen
    assert s["high_source"] == "statement" and s["falls"] == []


def test_free_sees_both_returns_basic_sees_everything(w, hist, paid):
    c = w["client"]
    assert upload(c, statement(sipper()), headers=FREE).status_code == 200
    d = c.get("/money/mutual-funds/behaviour", headers=FREE).json()
    assert d["full"] is False and d["plan"] == "Basic"
    s = d["schemes"][0]
    assert s["fund"] is not None and s["gap_pp"] is not None and s["gap_rupees"] is None and "sip" not in s and "falls" not in s
    assert "gap_rupees" not in d["total"] and hist == []                   # no history read for a free view
    assert upload(c, statement(sipper()), headers=BASIC).status_code == 200
    d = c.get("/money/mutual-funds/behaviour", headers=BASIC).json()
    assert d["full"] is True and d["schemes"][0]["sip"]["months_paid"] == 4


def test_no_funds_and_signed_out(w, hist):
    c = w["client"]
    c.delete("/money/mutual-funds", headers=PRO)
    d = c.get("/money/mutual-funds/behaviour", headers=PRO).json()
    assert d["schemes"] == [] and d["total"] is None and hist == []
    assert c.get("/money/mutual-funds/behaviour").status_code == 401


def test_an_exited_fund_compares_to_the_last_redemption(w, hist):
    data = {**M.empty(), "schemes": [{"k": "F|A", "name": "Fund A - Growth", "folio": "F", "isin": "", "amfi": ""}],
            "txns": [{"k": "F|A", "d": "2020-01-01", "t": "purchase", "u": 100, "a": 1000, "n": 10},
                     {"k": "F|A", "d": "2022-01-01", "t": "redeem", "u": 100, "a": 1500, "n": 15}]}
    w_ = M.worked(data, {"schemes": {}, "isin": {}, "read_at": None})
    row = M.holdings(data, w_, "2026-10-05")["schemes"][0]
    s = B.scheme_behaviour(data["schemes"][0], row, w_, data, "2026-10-05", "2022-01-01", None, True)
    assert s["held"] is False and s["to"] == "2022-01-01" and s["fund"] == pytest.approx(1.5 ** (365 / 731) - 1, abs=1e-4)
    assert s["gap_pp"] == pytest.approx(0, abs=0.05) and abs(s["gap_rupees"]) < 2       # one purchase, one sale: no timing gap
    assert s["sip"] is None and s["falls"] == [] and s["avg_days_held"] == 731
