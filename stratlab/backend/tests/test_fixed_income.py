"""Fixed-income rates: reading the Reserve Bank's Current Rates (a trimmed real copy of the home page panel), keeping
the last good copy, the repo rate's history, the small savings table, the after-tax arithmetic at a slab and at the
marginal rate from the user's own tax inputs, the user's deposits, the plan gate and the route's bad input."""
import json
from pathlib import Path

import pytest

from app import db, fixed_income as F, money_networth as nw, rbi_rates as R, tax_total
from app.config import settings
from tests import world

FIX = Path(__file__).parent / "fixtures" / "rates"
PAGE = (FIX / "rbi_home_rates.html").read_text()
PRO, BASIC, FREE = world.headers("pro-token"), world.headers("basic-token"), world.headers("free-token")


@pytest.fixture
def rbi(monkeypatch):
    calls = []

    def fetch(url=R.URL):
        calls.append(url)
        return PAGE
    monkeypatch.setattr(R, "fetch_text", fetch)
    R.forget()
    yield calls
    R.forget()


@pytest.fixture
def w(monkeypatch, rbi):
    built = world.build(monkeypatch)
    yield built
    built["close"]()


@pytest.fixture
def paid(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "pb"), ("RAZORPAY_PLAN_PRO", "pp")):
        monkeypatch.setattr(settings, k, v)


# ---------- the Reserve Bank's rates ----------
def test_reads_the_current_rates_panel():
    r = R.parse(PAGE)
    assert r["repo"] == 5.25 and r["sdf"] == 5.0 and r["msf"] == 5.5 and r["bank_rate"] == 5.5 and r["crr"] == 3.0 and r["slr"] == 18.0
    assert r["tbills"] == {"91": 5.5199, "182": 5.9601, "364": 6.1798}
    assert {"name": "6.36% GS 2031", "year": 2031, "yield": 6.9353} in r["gsecs"] and len(r["gsecs"]) == 5
    assert r["gsec_date"] == "2026-10-01"
    assert R.parse("") == {} and R.parse("<html>You are not authorized to view this page.</html>") == {}


def test_last_good_copy_and_a_failed_read(w, rbi, monkeypatch):
    a = R.current()
    assert a["rates"]["repo"] == 5.25 and a["read_at"] and len(rbi) == 1
    assert R.current()["rates"]["repo"] == 5.25 and len(rbi) == 1           # in memory
    R.forget()
    monkeypatch.setattr(R, "fetch_text", lambda url=R.URL: (_ for _ in ()).throw(OSError("down")))
    assert R.current()["rates"]["repo"] == 5.25                              # the saved copy
    R.forget()
    db.delete_setting(R.KEY)
    assert R.current() == {"rates": {}, "read_at": None}


def test_repo_history_and_a_new_rate_seen(w, rbi, monkeypatch):
    assert R.repo_on("2025-06-05") == 6.0 and R.repo_on("2025-06-06") == 5.5 and R.repo_on("2026-10-05") == 5.25
    assert R.repo_on("2018-01-01") is None
    monkeypatch.setattr(R, "fetch_text", lambda url=R.URL: PAGE.replace("5.25%", "5.00%"))
    R.forget()
    assert R.current()["rates"]["repo"] == 5.0
    h = R.repo_history()
    assert h[-1][1] == 5.0 and h[-2] == ("2025-12-05", 5.25)


# ---------- the arithmetic ----------
def test_after_tax_yield():
    assert F.slab_rate(30) == pytest.approx(0.312)
    assert F.after(7.7, "taxable", 0.312) == pytest.approx(5.30, abs=0.01)
    assert F.after(7.1, "eee", 0.312) == 7.1 and F.after(5.25, "reference", 0.3) is None


def test_marginal_rate_from_the_tax_inputs():
    # new regime, FY 2026-27: ₹30 lakh salary is in the 30% slab; ₹10 lakh is under the ₹12 lakh rebate after the
    # standard deduction, so the next ₹10,000 of interest costs nothing; ₹20 lakh is in the 20% slab
    assert F.marginal(2026, {"regime": "new", "other": 3000000, "salary": 3000000})["rate"] == pytest.approx(0.312, abs=1e-4)
    assert F.marginal(2026, {"regime": "new", "other": 1000000, "salary": 1000000})["rate"] == 0
    assert F.marginal(2026, {"regime": "new", "other": 2000000, "salary": 2000000})["rate"] == pytest.approx(0.208, abs=1e-4)
    assert F.marginal(2026, {"regime": "old", "other": 800000, "salary": 800000})["rate"] == pytest.approx(0.208, abs=1e-4)
    assert F.marginal(1990, {"regime": "new", "other": 1}) is None


def test_small_savings_table_is_the_notified_quarter():
    ss = F.SMALL_SAVINGS
    rates = {k: r for k, _, r, _, _, _ in ss["rows"]}
    assert rates["ppf"] == 7.1 and rates["scss"] == 8.2 and rates["ssy"] == 8.2 and rates["nsc"] == 7.7 and rates["kvp"] == 7.5
    assert ss["from"] == "2026-10-01" and ss["to"] == "2026-12-31"
    assert rates["ppf"] == nw.PPF_RATE                                        # Net worth uses the same PPF rate


# ---------- the route ----------
def test_free_picks_a_slab(w, paid):
    c = w["client"]
    d = c.get("/money/rates?slab=20", headers=FREE).json()
    assert d["full"] is False and d["basis"] == "slab" and d["tax_rate"] == 20.8 and d["plan"] == "Basic"
    t91 = next(x for x in d["market"] if x["key"] == "tbill91")
    assert t91["rate"] == 5.5199 and t91["after_tax"] == pytest.approx(5.5199 * 0.792, abs=0.01)
    assert next(x for x in d["market"] if x["key"] == "repo")["after_tax"] is None
    ppf = next(x for x in d["small_savings"]["rows"] if x["key"] == "ppf")
    assert ppf["after_tax"] == 7.1 and ppf["c80"] is True
    assert d["bonds"][0]["rate"] == 8.05
    d = c.get("/money/rates", headers=FREE).json()
    assert d["tax_rate"] == 31.2 and d["mine"] is None                       # 30% by default; no estimate on Free


def test_basic_uses_the_own_estimate_and_lists_deposits(w, paid):
    c = w["client"]
    uid = "u-basic"
    from app import tax_lots
    from datetime import date
    fy = tax_lots.fy_of(date.today().isoformat())
    tax_total.save_inputs(uid, fy, {"regime": "new", "other": 2000000, "salary": 2000000})
    db.set_setting(nw.KEY + uid, json.dumps({"items": [
        {"id": "a1", "kind": "fd", "name": "Bank FD", "principal": 100000, "rate": 7.0, "compounding": "quarterly",
         "start": "2026-01-01", "maturity": "2027-01-01"}]}))
    d = c.get("/money/rates", headers=BASIC).json()
    assert d["full"] is True and d["basis"] == "estimate" and d["tax_rate"] == 20.8 and d["mine"]["regime"] == "new"
    fd = d["deposits"][0]
    assert fd["name"] == "Bank FD" and fd["after_tax"] == pytest.approx(7 * 0.792, abs=0.01)
    assert fd["interest"] == pytest.approx(7186, abs=2) and fd["interest_after_tax"] == pytest.approx(fd["interest"] * 0.792, abs=1)
    d = c.get("/money/rates?slab=5", headers=BASIC).json()                   # a slab picked wins
    assert d["basis"] == "slab" and d["tax_rate"] == 5.2


def test_bad_input_and_signed_out(w):
    c = w["client"]
    assert c.get("/money/rates?slab=12", headers=PRO).status_code == 400
    assert c.get("/money/rates?slab=abc", headers=PRO).status_code == 422
    assert c.get("/money/rates").status_code == 401


def test_no_rbi_copy_still_shows_small_savings(w, monkeypatch):
    monkeypatch.setattr(R, "fetch_text", lambda url=R.URL: "<html>error</html>")
    R.forget()
    d = w["client"].get("/money/rates?slab=30", headers=PRO).json()
    assert d["market"] == [] and d["market_available"] is False and len(d["small_savings"]["rows"]) == 12
