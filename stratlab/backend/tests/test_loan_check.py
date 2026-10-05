"""Floating-rate loan check: reset dates, the expected rate of a repo-linked loan after each reset, the gap to the
statement rate in points and rupees, what each change did (new EMI or new tenure), MCLR loans, the new Net worth
fields, reset dates in the money calendar, the plan gate and bad input."""
from datetime import date

import pytest

from app import loan_check as L, money_networth as nw, rbi_rates as R
from app.config import settings
from tests import world
from tests.test_fixed_income import PAGE

PRO, BASIC, FREE = world.headers("pro-token"), world.headers("basic-token"), world.headers("free-token")
AT = date(2026, 10, 5)
H = list(R.REPO_HISTORY)


def home(**kw) -> dict:
    return {"id": "l1", "kind": "loan", "loan_type": "home", "lender": "Example Bank", "principal": 5000000, "rate": 8.5,
            "tenure_months": 240, "start": "2024-04-01", "benchmark": "repo", "reset_months": 3, "last_reset": "2026-07-01", **kw}


@pytest.fixture
def w(monkeypatch):
    monkeypatch.setattr(R, "fetch_text", lambda url=R.URL: PAGE)
    R.forget()
    built = world.build(monkeypatch)
    yield built
    built["close"]()
    R.forget()


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "pb"), ("RAZORPAY_PLAN_PRO", "pp")):
        monkeypatch.setattr(settings, k, v)


def test_reset_dates_line_up_on_the_last_reset():
    d = L.reset_dates(date(2024, 4, 1), date(2026, 7, 1), 3, AT)
    assert d[0] == date(2024, 7, 1) and d[-1] == date(2026, 10, 1) and len(d) == 10
    assert L.reset_dates(date(2024, 4, 15), date(2024, 4, 15), 12, AT) == [date(2025, 4, 15), date(2026, 4, 15)]


def test_repo_linked_loan_follows_the_repo_rate():
    p = L.rate_path(home(), AT, H)
    # sanctioned at 8.5% when the repo rate was 6.5%: a spread of 2 points, worked out
    assert p["spread"] == 2.0 and p["inferred"] is True
    assert [(c["date"], c["from"], c["to"]) for c in p["changes"]] == [
        ("2025-04-01", 8.5, 8.25), ("2025-07-01", 8.25, 7.5), ("2026-01-01", 7.5, 7.25)]
    assert p["expected"] == 7.25 and p["last_reset"] == "2026-10-01" and p["next_reset"] == "2027-01-01"
    p = L.rate_path(home(spread=2.4), AT, H)
    assert p["expected"] == 7.65 and p["inferred"] is False


def test_gap_to_the_statement_rate_and_what_each_change_did():
    c = L.check(home(current_rate=7.65), AT, H)
    assert c["expected"] == 7.25 and c["gap"]["pts"] == 0.4 and c["gap"]["matches"] is False
    assert c["gap"]["rupees_year"] == pytest.approx(c["outstanding"] * 0.004, abs=1)
    first = c["changes"][0]
    assert first["date"] == "2025-04-01" and first["emi_before"] == pytest.approx(nw.emi(5000000, 8.5, 240), abs=0.01)
    assert first["emi_change"] < 0 and first["months_change"] < 0                     # a cut: a lower EMI, or fewer months
    assert first["interest_if_same_emi"] < first["interest_before"] and first["interest_if_new_emi"] < first["interest_before"]
    assert c["emis_paid"] == 30 and c["left"] == 210
    same = L.check(home(current_rate=7.25), AT, H)
    assert same["gap"]["matches"] is True and same["gap"]["rupees_year"] == 0


def test_a_rise_lengthens_the_loan():
    hist = H + [("2026-08-01", 6.25)]
    c = L.check(home(current_rate=8.25), AT, hist)
    last = c["changes"][-1]
    # the EMI was kept through the cuts, so the balance fell faster: the same EMI now takes more months than before
    assert last["date"] == "2026-10-01" and last["to"] == 8.25 and last["months_change"] > 0
    assert last["interest_if_same_emi"] > last["interest_before"] and last["interest_if_new_emi"] > last["interest_before"]


def test_mclr_and_fixed_loans():
    m = L.check(home(benchmark="mclr", reset_months=12, last_reset="2026-04-01", current_rate=8.0), AT, H)
    assert m["expected"] is None and m["gap"] is None and m["next_reset"] == "2027-04-01"
    assert [(x["from"], x["to"]) for x in m["changes"]] == [(8.5, 8.0)]
    f = L.check(home(benchmark="fixed"), AT, H)
    assert f["why"] == "fixed" and f["changes"] == []
    assert L.check(home(tenure_months=None), AT, H)["ready"] is False


def test_net_worth_keeps_the_fields_and_the_calendar_gets_resets(w):
    c = w["client"]
    c.delete("/money/net-worth", headers=PRO)
    r = c.post("/money/net-worth/items", headers=PRO, json={"kind": "loan", "loan_type": "home", "principal": 5000000, "rate": 8.5,
                                                           "tenure_months": 240, "start": "2024-04-01", "benchmark": "repo",
                                                           "reset_months": 3, "last_reset": "2026-07-01", "current_rate": 7.65})
    assert r.status_code == 200
    item = nw.load("u-pro")["items"][0]
    assert item["benchmark"] == "repo" and item["reset_months"] == 3 and item["current_rate"] == 7.65
    resets = [e for e in nw.upcoming_dates("u-pro", 200, AT) if e["kind"] == "loan_reset"]
    assert [e["date"] for e in resets] == ["2027-01-01", "2027-04-01"]
    # a fixed loan keeps no reset fields; a reset before the start is refused
    r = c.post("/money/net-worth/items", headers=PRO, json={"kind": "loan", "principal": 100000, "rate": 10, "benchmark": "fixed", "spread": 1, "reset_months": 3})
    assert "spread" not in nw.load("u-pro")["items"][-1]
    r = c.post("/money/net-worth/items", headers=PRO, json={"kind": "loan", "principal": 100000, "rate": 10, "tenure_months": 12, "start": "2026-01-01",
                                                           "benchmark": "repo", "last_reset": "2025-01-01"})
    assert r.status_code == 422
    assert c.post("/money/net-worth/items", headers=PRO, json={"kind": "loan", "principal": 1, "rate": 10, "benchmark": "libor"}).status_code == 422
    assert c.post("/money/net-worth/items", headers=PRO, json={"kind": "loan", "principal": 1, "rate": 10, "reset_months": 5}).status_code == 422


def test_route_and_plan_gate(w, paid):
    c = w["client"]
    for h, uid in ((BASIC, "u-basic"), (FREE, "u-free")):
        c.delete("/money/net-worth", headers=h)
        assert c.post("/money/net-worth/items", headers=h, json={"kind": "loan", "loan_type": "home", "principal": 5000000, "rate": 8.5,
                                                                "tenure_months": 240, "start": "2024-04-01", "benchmark": "repo",
                                                                "current_rate": 7.65}).status_code == 200
    d = c.get("/money/loans/check", headers=BASIC).json()
    assert d["full"] is True and d["floating"] == 1 and d["repo"]["now"] == 5.25 and len(d["checks"]) == 1
    assert d["checks"][0]["expected"] is not None and d["draft"]["status"].startswith("Draft")
    d = c.get("/money/loans/check", headers=FREE).json()
    assert d["full"] is False and d["checks"] == [] and d["plan"] == "Basic" and d["floating"] == 1
    assert c.get("/money/loans/check").status_code == 401
    text = str(c.get("/money/loans/check", headers=BASIC).json()).lower()
    for word in ("switch lender", "refinance", "you should", "recommend"):
        assert word not in text
