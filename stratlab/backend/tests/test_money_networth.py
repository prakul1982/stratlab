"""Net worth: the deposit, provident fund and loan arithmetic, the page's totals and allocation, the history, the
insurance register, the calendar hook, plan limits, privacy and deletion."""
import math
import sys
import time
import types
from datetime import date, datetime, timezone

import pytest

from app import db, main
from app import money_networth as nw
from app.config import settings
from tests import world

PRO, FREE = world.headers("pro-token"), world.headers("free-token")


@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    main._nw_prices.clear()
    yield built
    main._nw_prices.clear()
    built["close"]()


def payments_live(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)


# ---------- fixed and recurring deposits ----------
def test_fd_compounds_each_quarter_then_simple_interest_on_the_days_left():
    start = date(2025, 1, 1)
    assert nw.fd_value(100000, 7, start, date(2026, 1, 1)) == pytest.approx(107185.90, abs=0.01)     # 1.0175 ** 4
    # 4 whole quarters and 31 days of simple interest on top
    assert nw.fd_value(100000, 7, start, date(2026, 2, 1)) == pytest.approx(100000 * 1.0175 ** 4 * (1 + 0.07 * 31 / 365))
    assert nw.fd_value(100000, 7, start, date(2026, 1, 1), "monthly") == pytest.approx(100000 * (1 + 0.07 / 12) ** 12)
    assert nw.fd_value(100000, 7, start, date(2026, 1, 1), "yearly") == pytest.approx(107000)
    assert nw.fd_value(100000, 7, start, date(2025, 7, 1), "simple") == pytest.approx(100000 * (1 + 0.07 * 181 / 365))
    assert nw.fd_value(100000, 7, start, date(2024, 6, 1)) == 100000                                  # not started yet
    assert nw.fd_value(100000, 7, start, date(2030, 1, 1), maturity=date(2026, 1, 1)) == pytest.approx(107185.90, abs=0.01)


def test_rd_grows_each_instalment_for_its_own_time():
    v, paid = nw.rd_value(1000, 7, date(2025, 1, 1), date(2026, 1, 1), date(2026, 1, 1))
    assert paid == 12000 and nw.rd_instalments(date(2025, 1, 1), date(2026, 1, 1)) == 12
    expect = sum(nw.fd_value(1000, 7, nw.add_months(date(2025, 1, 1), j), date(2026, 1, 1)) for j in range(12))
    assert v == pytest.approx(expect) and 12400 < v < 12500                                          # banks show about 12,46x
    v, paid = nw.rd_value(1000, 7, date(2025, 1, 1), date(2026, 1, 1), date(2025, 3, 15))
    assert paid == 3000 and 3000 < v < 3030


def test_months_and_dates():
    assert nw.add_months(date(2025, 1, 31), 1) == date(2025, 2, 28) and nw.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert nw.add_months(date(2025, 11, 15), 3) == date(2026, 2, 15)
    assert nw.months_between(date(2025, 1, 31), date(2025, 2, 28)) == 1 and nw.months_between(date(2025, 1, 15), date(2025, 2, 14)) == 0
    assert nw.fy_start(date(2026, 3, 31)) == date(2025, 4, 1) and nw.fy_end(date(2026, 4, 1)) == date(2027, 3, 31)
    assert nw.fy_label(date(2026, 10, 4)) == "FY 2026-27"


# ---------- EPF and PPF ----------
def test_epf_interest_accrues_monthly_and_is_credited_on_31_march():
    got = nw.provident(100000, 8.25, date(2025, 4, 1), date(2026, 4, 1))
    assert got["value"] == pytest.approx(108250) and got["credited"] == pytest.approx(108250)
    half = nw.provident(100000, 8.25, date(2025, 4, 1), date(2025, 10, 1))
    assert half["value"] == pytest.approx(104125) and half["credited"] == 100000                     # earned, not yet credited
    # with a monthly contribution: the running balance earns rate/12 each month
    bal, acc = 100000.0, 0.0
    for _ in range(12):
        acc += bal * 0.0825 / 12
        bal += 5000
    got = nw.provident(100000, 8.25, date(2025, 4, 1), date(2026, 4, 1), monthly=5000)
    assert got["value"] == pytest.approx(bal + acc) and got["paid_in"] == 60000
    assert nw.provident(100000, 8.25, date(2026, 5, 1), date(2026, 4, 1))["value"] == 100000          # a balance dated later


def test_ppf_compounds_yearly_with_deposits_each_april_and_matures_after_15_years():
    got = nw.provident(100000, 7.1, date(2025, 4, 1), date(2027, 4, 1), yearly=150000)
    assert got["value"] == pytest.approx((100000 * 1.071 + 150000) * 1.071)                         # the 2027 deposit is the end, not added
    assert nw.ppf_maturity(date(2015, 6, 10)) == date(2031, 4, 1)
    assert nw.ppf_maturity(date(2016, 3, 31)) == date(2031, 4, 1) and nw.ppf_maturity(date(2016, 4, 1)) == date(2032, 4, 1)
    assert nw.PPF_RATE == 7.1 and nw.EPF_RATE == 8.25


# ---------- loans ----------
def test_emi_and_the_amortisation_schedule():
    pay = nw.emi(5000000, 8.5, 240)
    assert pay == pytest.approx(43391.16, abs=0.01)
    assert nw.emi(120000, 0, 12) == 10000 and nw.balance_after(120000, 0, 10000, 5) == 70000
    assert nw.balance_after(5000000, 8.5, pay, 240) == pytest.approx(0, abs=0.01)
    months, interest = nw.payoff(5000000, 8.5, pay)
    assert months == 240 and interest == pytest.approx(pay * 240 - 5000000, abs=1)
    s = nw.loan_state(5000000, 8.5, 240, date(2024, 1, 10), date(2026, 10, 4))
    assert s["paid"] == 32 and s["left"] == 208 and s["next_emi"] == "2026-10-10" and s["ends"] == "2044-01-10"
    assert s["outstanding"] == pytest.approx(nw.balance_after(5000000, 8.5, pay, 32))
    # interest paid this financial year: the EMIs of 10 April to 10 September 2026
    fy = sum(nw.balance_after(5000000, 8.5, pay, j - 1) * 0.085 / 12 for j in range(27, 33))
    assert s["interest_fy"] == pytest.approx(fy)
    done = nw.loan_state(120000, 10, 12, date(2020, 1, 1), date(2026, 1, 1))
    assert done["outstanding"] == 0 and done["left"] == 0 and done["next_emi"] is None


def test_prepayment_shortens_the_tenure_or_lowers_the_emi():
    start, at = date(2024, 1, 10), date(2026, 10, 4)
    got = nw.prepay(5000000, 8.5, 240, start, at, 500000)
    bal = got["outstanding"]
    assert got["months_left"] == 208 and not got["closes"]
    t_months, t_int = nw.payoff(bal - 500000, 8.5, got["emi"])
    assert got["tenure"]["months_left"] == t_months and got["tenure"]["months_saved"] == 208 - t_months > 30
    assert got["tenure"]["interest_saved"] == pytest.approx(got["interest_left"] - t_int)
    e2 = nw.emi(bal - 500000, 8.5, 208)
    assert got["lower_emi"]["emi"] == pytest.approx(e2) and got["lower_emi"]["emi_change"] == pytest.approx(e2 - got["emi"])
    assert 0 < got["lower_emi"]["interest_saved"] < got["tenure"]["interest_saved"]
    shut = nw.prepay(5000000, 8.5, 240, start, at, 10 ** 9)
    assert shut["closes"] and shut["amount"] == pytest.approx(bal) and shut["interest_saved"] == pytest.approx(got["interest_left"])
    assert nw.prepay(120000, 10, 12, date(2020, 1, 1), at, 1000)["error"]


# ---------- policies ----------
def test_premium_due_dates_roll_forward_and_add_up_to_a_year():
    at = date(2026, 10, 4)
    assert nw.next_due(date(2026, 11, 1), "yearly", at) == date(2026, 11, 1)
    assert nw.next_due(date(2025, 3, 1), "yearly", at) == date(2027, 3, 1)
    assert nw.next_due(date(2026, 1, 15), "quarterly", at) == date(2026, 10, 15)
    assert nw.next_due(date(2026, 1, 15), "single", at) is None
    assert nw.yearly_premium(1000, "monthly") == 12000 and nw.yearly_premium(5000, "half-yearly") == 10000
    assert nw.yearly_premium(50000, "single") == 0


# ---------- entries ----------
def test_entries_keep_only_their_fields_and_fill_defaults():
    got = nw.clean(nw.ItemReq(kind="epf", name="  My   EPF ", balance=500000, grams=10), date(2026, 10, 4))
    assert got == {"kind": "epf", "name": "My EPF", "balance": 500000, "as_of": "2026-10-04", "rate": 8.25}
    got = nw.clean(nw.ItemReq(kind="sgb", units=10, issue_price=5000, start="2020-05-01"))
    assert got["maturity"] == "2028-05-01"
    for bad, words in ((dict(kind="fd", principal=1000, rate=7, start="2026-01-01"), "maturity date"),
                       (dict(kind="fd", principal=1000, rate=7, start="2026-01-01", maturity="2025-01-01"), "after the start"),
                       (dict(kind="cash", value=5, as_of="31/12/2025"), "isn't a date"),
                       (dict(kind="gold"), "grams"), (dict(kind="crypto", coin="!!"), "coin"),
                       (dict(kind="loan", principal=1000, rate=9, tenure_months=12), "start date"),
                       (dict(kind="policy", premium=100), "insurer")):
        with pytest.raises(nw.EntryError, match=words):
            nw.clean(nw.ItemReq(**bad))


# ---------- the page ----------
def add(c, body, headers=PRO):
    r = c.post("/money/net-worth/items", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_page_adds_up_every_kind_with_its_as_of_date(w):
    c = w["client"]
    main._nw_prices["gold"] = (time.time(), (7000.0, "2026-10-04T10:00+00:00"))        # rupees a gram, 24 carat
    assert c.put("/holdings", headers=PRO, json={"items": [{"symbol": "RELIANCE", "qty": 10, "avg": 2500}]}).status_code == 200
    add(c, {"kind": "epf", "balance": 500000, "monthly": 10000, "as_of": "2026-04-01"})
    add(c, {"kind": "ppf", "balance": 300000, "yearly": 150000, "opened": "2015-06-10", "as_of": "2026-04-01"})
    add(c, {"kind": "nps", "tier1": 200000, "tier2": 50000})
    add(c, {"kind": "fd", "name": "SBI FD", "principal": 100000, "rate": 7, "start": "2025-10-04", "maturity": "2027-10-04"})
    add(c, {"kind": "rd", "monthly": 2000, "rate": 6.5, "start": "2026-01-04", "maturity": "2027-01-04"})
    add(c, {"kind": "gold", "grams": 10, "purity": 22})
    add(c, {"kind": "sgb", "units": 5, "issue_price": 4800, "start": "2020-10-20"})
    add(c, {"kind": "cash", "value": 80000})
    add(c, {"kind": "property", "value": 9000000})
    add(c, {"kind": "crypto", "value": 15000})
    add(c, {"kind": "other", "value": 1000})
    add(c, {"kind": "loan", "loan_type": "home", "lender": "HDFC", "principal": 5000000, "rate": 8.5, "tenure_months": 240, "start": "2024-01-10"})
    add(c, {"kind": "loan", "loan_type": "credit_card", "principal": 12000, "rate": 42})
    v = add(c, {"kind": "policy", "policy_type": "term", "insurer": "LIC", "sum_assured": 10000000, "premium": 12000,
                "due": "2026-11-01", "nominee": "Spouse"})
    rows = {r["kind"]: r for r in v["assets"]}
    assert rows["stocks_in"]["value"] > 0 and rows["stocks_in"]["basis"] == "market price"
    assert rows["epf"]["value"] > 500000 + 6 * 10000 and rows["epf"]["facts"]["year_end"] > rows["epf"]["value"]
    assert rows["ppf"]["facts"]["maturity"] == "2031-04-01" and rows["ppf"]["facts"]["maturity_value"] > 300000
    assert rows["nps"]["value"] == 250000 and rows["nps"]["basis"] == "as entered"
    assert rows["fd"]["value"] == pytest.approx(nw.fd_value(100000, 7, date(2025, 10, 4), nw.today()), abs=0.01)
    assert rows["fd"]["facts"]["maturity_value"] == pytest.approx(100000 * 1.0175 ** 8, abs=0.01)
    assert rows["gold"]["value"] == pytest.approx(10 * 7000 * 22 / 24, abs=0.01) and rows["gold"]["as_of"].startswith("2026-10-04")
    assert rows["sgb"]["value"] == 35000 and rows["sgb"]["facts"]["yearly_interest"] == 600
    assert rows["property"]["rule"] == "Value as entered"
    assert all(r["as_of"] for r in v["assets"] + v["liabilities"])                   # every number has its date
    loans = {r["entry"]["loan_type"]: r for r in v["liabilities"]}
    assert loans["home"]["facts"]["emi"] == pytest.approx(43391.16, abs=0.01) and loans["credit_card"]["value"] == 12000
    t = v["totals"]
    assert t["assets"] == pytest.approx(sum(r["value"] or 0 for r in v["assets"]), abs=0.05)
    assert t["net"] == pytest.approx(t["assets"] - t["liabilities"], abs=0.05)
    assert [a["label"] for a in v["allocation"]][:2] == ["Indian stocks", "EPF"]
    assert sum(a["pct"] for a in v["allocation"]) == pytest.approx(100, abs=0.2)
    pol = v["insurance"]["policies"][0]
    assert pol["due_in"] == (date(2026, 11, 1) - nw.today()).days and v["insurance"]["yearly_premium"] == 12000
    assert v["insurance"]["cover"] == {"term": 10000000}
    assert v["history"][-1]["d"] == nw.today().isoformat() and v["history"][-1]["net"] == t["net"] and v["count"] == 14


def test_edit_delete_prepay_upcoming_and_export(w):
    c = w["client"]
    v = add(c, {"kind": "loan", "loan_type": "car", "principal": 800000, "rate": 9, "tenure_months": 60, "start": "2025-06-05"})
    lid = v["liabilities"][0]["id"]
    r = c.post("/money/net-worth/prepay", headers=PRO, json={"id": lid, "amount": 100000}).json()
    assert r["tenure"]["months_saved"] > 0 and r["lower_emi"]["emi_change"] < 0 and "rate and dates you entered" in r["note"]
    assert c.post("/money/net-worth/prepay", headers=PRO, json={"id": "nope", "amount": 1}).status_code == 404
    v = c.put(f"/money/net-worth/items/{lid}", headers=PRO, json={"kind": "loan", "principal": 900000, "rate": 9, "tenure_months": 60,
                                                                    "start": "2025-06-05"}).json()
    assert v["liabilities"][0]["entry"]["principal"] == 900000 and v["liabilities"][0]["id"] == lid
    add(c, {"kind": "fd", "name": "Bank FD", "principal": 100000, "rate": 7, "start": "2025-11-01", "maturity": nw.add_months(nw.today(), 1).isoformat()})
    add(c, {"kind": "policy", "insurer": "Star", "policy_type": "health", "premium": 2000, "frequency": "monthly", "due": nw.today().isoformat()})
    up = c.get("/money/net-worth/upcoming?days=40", headers=PRO).json()["rows"]
    kinds = [u["kind"] for u in up]
    assert "fd_maturity" in kinds and kinds.count("emi") >= 1 and kinds.count("premium") == 2
    assert up == sorted(up, key=lambda u: (u["date"], u["title"]))
    assert nw.upcoming_dates("u-pro", 40) == up                                   # the hook the money calendar reads
    csv = c.get("/money/net-worth/export", headers=PRO)
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert "Net worth" in csv.text and "Bank FD" in csv.text and "Star" in csv.text and "History" in csv.text
    v = c.delete(f"/money/net-worth/items/{lid}", headers=PRO).json()
    assert v["liabilities"] == [] and c.delete(f"/money/net-worth/items/{lid}", headers=PRO).status_code == 404
    bad = c.post("/money/net-worth/items", headers=PRO, json={"kind": "fd", "principal": 1, "rate": 7, "start": "2026-01-01"})
    assert bad.status_code == 422 and "maturity date" in bad.json()["detail"]["message"]


def test_gold_and_crypto_fall_back_to_the_entered_value(w):
    c = w["client"]
    main._nw_prices["gold"] = (time.time(), None)
    main._nw_prices["crypto:ZZZ"] = (time.time(), None)
    v = add(c, {"kind": "gold", "grams": 10, "value": 60000})
    v = add(c, {"kind": "crypto", "coin": "zzz", "qty": 2, "value": 900})
    rows = {r["kind"]: r for r in v["assets"]}
    assert rows["gold"]["value"] == 60000 and rows["gold"]["basis"] == "as entered" and "no gold price" in rows["gold"]["rule"]
    assert rows["crypto"]["value"] == 900 and rows["crypto"]["entry"]["coin"] == "ZZZ"
    main._nw_prices["crypto:ZZZ"] = (time.time(), 2.5)
    v = c.get("/money/net-worth", headers=PRO).json()
    row = next(r for r in v["assets"] if r["kind"] == "crypto")
    rate = main.usd_inr()
    assert row["value"] == (pytest.approx(2 * 2.5 * rate, abs=0.01) if rate else 900)


def test_mutual_funds_come_from_the_mf_module_when_it_exists(w, monkeypatch):
    c = w["client"]
    assert nw.mf_value("u-pro")["value"] == 0                                      # no module: 0
    fake = types.ModuleType("app.money_mf")
    fake.net_worth_value = lambda uid: {"value": 250000.0, "as_of": "2026-10-03"} if uid == "u-pro" else 0
    monkeypatch.setitem(sys.modules, "app.money_mf", fake)
    import app
    monkeypatch.setattr(app, "money_mf", fake, raising=False)
    v = add(c, {"kind": "cash", "value": 1000})
    mf = next(r for r in v["assets"] if r["kind"] == "mf")
    assert mf["value"] == 250000 and mf["as_of"] == "2026-10-03" and v["totals"]["assets"] == 251000
    fake.net_worth_value = lambda uid: 1 / 0                                       # a broken module never breaks the page
    assert c.get("/money/net-worth", headers=PRO).json()["totals"]["assets"] == 1000


# ---------- plans, privacy, deletion ----------
def test_free_keeps_five_entries_and_no_history_once_payments_are_live(w, monkeypatch):
    payments_live(monkeypatch)
    c = w["client"]
    for n in range(5):
        v = add(c, {"kind": "cash", "value": 100 + n}, FREE)
    assert v["limit"] == 5 and v["history"] is None and not v["history_allowed"] and v["history_count"] == 1
    r = c.post("/money/net-worth/items", headers=FREE, json={"kind": "cash", "value": 1})
    assert r.status_code == 402 and "5 entries" in r.json()["detail"]["message"]
    for n in range(6):
        v = add(c, {"kind": "cash", "value": 100 + n}, PRO)
    assert v["limit"] is None and v["history_allowed"] and v["history"]
    from app import plans
    assert plans.networth_items("free") == 5 and plans.networth_items("basic") is None and plans.allows("basic", "networth")


def test_net_worth_is_private_and_deleted_in_one_step(w):
    c = w["client"]
    v = add(c, {"kind": "cash", "value": 5000})
    iid = v["assets"][0]["id"]
    assert c.get("/money/net-worth").status_code == 401
    assert c.get("/money/net-worth", headers=FREE).json()["assets"] == []
    assert c.put(f"/money/net-worth/items/{iid}", headers=FREE, json={"kind": "cash", "value": 1}).status_code == 404
    assert c.delete(f"/money/net-worth/items/{iid}", headers=FREE).status_code == 404
    c.delete("/money/net-worth", headers=FREE)                                     # someone else deleting theirs
    assert c.get("/money/net-worth", headers=PRO).json()["totals"]["assets"] == 5000
    assert db.get_setting("networth:u-pro") and db.get_setting("networthlog:u-pro")
    assert c.delete("/money/net-worth", headers=PRO).json() == {"deleted": True}
    assert db.get_setting("networth:u-pro") is None and db.get_setting("networthlog:u-pro") is None
    assert c.get("/money/net-worth", headers=PRO).json()["assets"] == []
    assert db.get_setting("networthlog:u-pro") is None                             # an empty page records nothing


def test_snapshot_on_the_first_of_each_month_once(w):
    c = w["client"]
    add(c, {"kind": "cash", "value": 7000})
    job = main.networth_job
    first = datetime(2026, 11, 1, 11, 0, tzinfo=timezone.utc)                     # 4:30 pm in India
    assert job.tick(datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc)) == 0
    assert job.tick(datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc)) == 0       # before 4 pm
    assert job.tick(first) == 1 and job.tick(first) == 0
    snap = [h for h in nw.history("u-pro") if h["d"] == "2026-11-01"]
    assert snap and snap[0]["why"] == "month" and snap[0]["net"] == 7000


def test_damaged_rows_never_break_the_page(w):
    db.set_setting("networth:u-pro", '{"items": [{"id": "x", "kind": "fd", "principal": "lots"}, {"kind": "cash"}, 5, null]}')
    db.set_setting("networthlog:u-pro", "not json")
    c = w["client"]
    r = c.get("/money/net-worth", headers=PRO)
    assert r.status_code == 200 and r.json()["assets"] == []
    assert nw.upcoming_dates("u-pro", 30) == []
    assert all(math.isfinite(x) for x in (nw.emi(1e12, 60, 600), nw.fd_value(1e12, 60, date(1950, 1, 1), date(2150, 1, 1))))
