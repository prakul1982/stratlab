"""Net worth: the deposit, provident fund and loan arithmetic, the page's totals and allocation, the history, the
insurance register, the calendar hook, plan limits, privacy and deletion."""
import json
import math
import sys
import time
import types
from datetime import date, datetime, timezone

import pytest
import time_machine

from app import db, main
from app import money_networth as nw
from app.config import settings
from tests import world

PRO, FREE = world.headers("pro-token"), world.headers("free-token")


@pytest.fixture
def w(monkeypatch):
    """The page is read on Monday 5 October 2026, 10:30 IST (the dates in these tests, such as a policy due on 1 November,
    are written for that day), whatever day the tests actually run on; the fake market's clock stands there too."""
    from tests import fake_prices
    day = datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(fake_prices, "FROZEN", day)
    with time_machine.travel(day, tick=True):
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
    assert v["history"][-1]["d"] == v["as_of"] and v["history"][-1]["net"] == t["net"] and v["count"] == 14


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


def test_free_gets_no_history_in_the_export_or_its_delete(w, monkeypatch):
    payments_live(monkeypatch)
    c = w["client"]
    v = add(c, {"kind": "cash", "value": 100}, FREE)
    assert v["history_count"] == 1
    day = nw.history("u-free")[0]["d"]
    assert "History," not in c.get("/money/net-worth/export", headers=FREE).text
    r = c.delete(f"/money/net-worth/history/{day}", headers=FREE)
    assert r.status_code == 402 and r.json()["detail"]["code"] == "networth_history"
    add(c, {"kind": "cash", "value": 100}, PRO)
    assert "History," in c.get("/money/net-worth/export", headers=PRO).text


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
    assert job.tick(datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc)) == 0       # before 4 pm
    assert job.tick(first) == 1 and job.tick(first) == 0
    assert job.tick(datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc)) == 0      # the month is done
    snap = [h for h in nw.history("u-pro") if h["d"] == "2026-11-01"]
    assert snap and snap[0]["why"] == "month" and snap[0]["net"] == 7000


def test_a_missed_first_is_caught_up_later_in_the_month_and_a_killed_run_resumes(w, monkeypatch):
    from app import run_marks
    c = w["client"]
    add(c, {"kind": "cash", "value": 7000})
    db.set_setting("networth:u-free", json.dumps({"items": []}))
    job, seen = main.networth_job, []
    value_of = job.value_of

    def kill_after_first(uid):
        seen.append(uid)
        if len(seen) == 2:
            raise KeyboardInterrupt                                                # a deploy kills it mid-run
        return value_of(uid)
    monkeypatch.setattr(job, "value_of", kill_after_first)
    third = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)                       # the leader was down over the 1st
    with pytest.raises(KeyboardInterrupt):
        job.tick(third)
    assert job.tick(third) == 0                                                    # still beating: left alone
    monkeypatch.setattr(run_marks, "STALE", 0)
    job.tick(third)
    assert sorted(seen) == sorted([seen[0], seen[1], seen[1]])                     # the first user isn't valued again
    assert [h["why"] for h in nw.history("u-pro") if h["d"] == "2026-11-03"] == ["month"]
    assert job.tick(third) == 0


def test_a_partial_total_is_named_and_only_the_month_is_recorded_flagged(w, monkeypatch):
    c = w["client"]
    add(c, {"kind": "cash", "value": 7000})
    before = nw.history("u-pro")

    def broken(profile):
        raise RuntimeError("holdings down")
    monkeypatch.setattr(main, "holdings_view", broken)
    v = add(c, {"kind": "cash", "value": 1000})
    assert v["totals"]["partial"] == ["My Holdings couldn't be read"] and nw.history("u-pro") == before
    # the month's snapshot is taken anyway, flagged with what's missing (a fund never valued mustn't stop the history)
    assert main.networth_job.tick(datetime(2026, 11, 1, 11, 0, tzinfo=timezone.utc)) == 1
    snap = [h for h in nw.history("u-pro") if h["d"] == "2026-11-01"]
    assert len(snap) == 1 and snap[0]["partial"] == ["My Holdings couldn't be read"] and snap[0]["why"] == "month"
    t = nw.build([], {"in": 100.0, "us": 0, "count": 2, "us_no_rate": True}, {"value": 500.0, "at_cost": 1, "missing": 0}, nw.Prices())
    assert t["totals"]["partial"] == ["US stocks (no dollar rate right now)"]
    assert "1 fund without a NAV at cost" in next(r for r in t["assets"] if r["kind"] == "mf")["rule"]
    assert nw.build([], {"in": 100.0, "us": 50.0, "count": 2}, None, nw.Prices())["totals"]["partial"] is None


def test_stocks_without_a_price_make_the_total_partial(w, monkeypatch):
    """B2: a stock without a price counts at cost and leaves the total whole (said in a note); only one with neither a
    price nor a buy price makes it partial, and then the change is still recorded, flagged."""
    c = w["client"]
    assert c.put("/holdings", headers=PRO, json={"items": [{"symbol": "RELIANCE", "qty": 10, "avg": 2500},
                                                           {"symbol": "TCS", "qty": 3}]}).status_code == 200
    monkeypatch.setattr(main.kite, "ready", lambda: False)                      # no quotes: TCS has no cost either
    v = add(c, {"kind": "cash", "value": 1000})
    row = next(r for r in v["assets"] if r["kind"] == "stocks_in")
    assert v["totals"]["partial"] == ["no price or buy price for 1 stock"] and v["totals"]["partial_lasting"]
    assert v["totals"]["notes"] == ["1 stock counted at cost (no price)"]
    assert [(h["why"], h.get("partial")) for h in nw.history("u-pro") if h["d"] == nw.today().isoformat()] == [
        ("change", ["no price or buy price for 1 stock"])]
    assert row["value"] == 25000 and row["basis"] == "at cost" and "at cost" in row["rule"]
    # some priced, some at cost: market price, the rule says how many are at cost, and the total is whole
    t = nw.build([], {"in": 100.0, "us": 0, "count": 3, "unpriced": {"in": 1, "us": 0}, "unvalued": {"in": 0, "us": 0},
                      "priced": {"in": 2, "us": 0}}, None, nw.Prices())
    r = t["assets"][0]
    assert r["basis"] == "market price" and "1 without a price counted at cost" in r["rule"]
    assert t["totals"]["partial"] is None and t["totals"]["notes"] == ["1 stock counted at cost (no price)"]
    # every stock unpriced and none with a cost: no row, but the total says so (it used to be silently left out)
    t = nw.build([], {"in": 0, "us": 0, "count": 1, "unpriced": {"in": 1, "us": 0}, "unvalued": {"in": 1, "us": 0},
                      "priced": {"in": 0, "us": 0}}, None, nw.Prices())
    assert t["assets"] == [] and t["totals"]["partial"] == ["no price or buy price for 1 stock"]


def test_damaged_rows_never_break_the_page(w):
    db.set_setting("networth:u-pro", '{"items": [{"id": "x", "kind": "fd", "principal": "lots"}, {"kind": "cash"}, 5, null]}')
    db.set_setting("networthlog:u-pro", "not json")
    c = w["client"]
    r = c.get("/money/net-worth", headers=PRO)
    assert r.status_code == 200 and r.json()["assets"] == []
    assert nw.upcoming_dates("u-pro", 30) == []
    assert all(math.isfinite(x) for x in (nw.emi(1e12, 60, 600), nw.fd_value(1e12, 60, date(1950, 1, 1), date(2150, 1, 1))))


def test_the_csv_does_not_hand_a_spreadsheet_a_formula(w):
    """Security review, 7 Oct 2026: a name typed (or read from a statement) as =HYPERLINK(...) stays text in the export."""
    c = w["client"]
    add(c, {"kind": "cash", "name": '=HYPERLINK("http://evil.test","x")', "value": 5000})
    add(c, {"kind": "cash", "name": "@SUM(1+1)", "value": 100})
    text = c.get("/money/net-worth/export", headers=PRO).text
    cells = [cell.strip('"') for line in text.splitlines() for cell in line.split(",")]
    assert not any(x.startswith(("=", "@")) for x in cells), text
    assert "'=HYPERLINK" in text and "'@SUM" in text


def test_an_asset_without_a_price_makes_the_total_partial_and_is_named(w):
    cash = {"id": "c1", "kind": "cash", "name": "Wallet", "value": 1000, "as_of": "2026-10-05"}
    btc = {"id": "c2", "kind": "crypto", "name": "BTC", "coin": "BTC", "qty": 1}
    t = nw.build([cash, btc], None, None, nw.Prices(), date(2026, 10, 5))
    assert t["totals"]["assets"] == 1000 and t["totals"]["partial"] == ["no price for BTC"]
    assert nw.record("u-x", t["totals"], "visit") == [] and nw.history("u-x") == []


def test_allocation_percentages_add_to_exactly_100():
    assert round(sum(nw.pct_split([1, 1, 1])), 1) == 100 and nw.pct_split([1, 1, 1]) == [33.4, 33.3, 33.3]
    items = [{"id": f"i{n}", "kind": k, "value": 1000, "as_of": "2026-10-05"} for n, k in enumerate(["cash", "property", "other"])]
    t = nw.build(items, None, None, nw.Prices(), date(2026, 10, 5))
    assert round(sum(a["pct"] for a in t["allocation"]), 1) == 100.0


def test_unnamed_entries_keep_their_own_calendar_ids_and_premiums_show_the_insurer(w):
    c = w["client"]
    for ins in ("Acme", "Zed"):
        add(c, {"kind": "policy", "insurer": ins, "policy_type": "term", "premium": 1000, "frequency": "yearly", "due": "2026-11-01"})
    rows = nw.upcoming_dates("u-pro", 60)
    prem = [r for r in rows if r["kind"] == "premium"]
    assert len(prem) == 2 and len({r["id"] for r in prem}) == 2 and all(r["id"] for r in prem)
    assert {r["title"] for r in prem} == {"Acme: premium due", "Zed: premium due"}


def test_ppf_yearly_deposit_is_capped_at_1_50_000():
    assert nw.clean(nw.ItemReq(kind="ppf", balance=1000, yearly=150000))["yearly"] == 150000
    with pytest.raises(nw.EntryError, match="1,50,000"):
        nw.clean(nw.ItemReq(kind="ppf", balance=1000, yearly=500000))


# ---------- snapshots ----------
def _t(net, partial=None):
    return {"net": net, "assets": net, "liabilities": 0, "partial": partial}


def test_a_partial_month_snapshot_keeps_a_complete_one_and_a_complete_one_replaces_the_months_partial(w):
    nw.record("u-t", _t(100), "month", date(2026, 10, 1))
    assert nw.record("u-t", _t(40, ["EPF"]), "month", date(2026, 10, 1)) == nw.history("u-t") and nw.history("u-t")[0]["net"] == 100
    assert nw.record("u-t", _t(40, ["EPF"]), "month", date(2026, 10, 2))[0]["net"] == 100      # the month has a complete one
    nw.delete("u-t")
    nw.record("u-t", _t(40, ["EPF"]), "month", date(2026, 10, 1))
    rows = nw.record("u-t", _t(100), "month", date(2026, 10, 3))
    assert [(h["d"], h["net"]) for h in rows] == [("2026-10-03", 100)]                          # one month snapshot, the complete one


def test_the_visit_catch_up_is_only_stopped_by_a_complete_snapshot_this_month(w):
    c = w["client"]
    db.set_setting("networth:u-pro", json.dumps({"items": [{"id": "a", "kind": "cash", "value": 7000}]}))
    nw.record("u-pro", _t(5, ["EPF"]), "month", date(2026, 10, 1))
    c.get("/money/net-worth", headers=PRO)                                                      # complete now: replaces the partial one
    rows = [h for h in nw.history("u-pro") if h["d"][:7] == "2026-10"]
    assert [(h["why"], h.get("partial"), h["net"]) for h in rows] == [("month", None, 7000)]
    c.get("/money/net-worth", headers=PRO)
    assert [h for h in nw.history("u-pro") if h["d"][:7] == "2026-10"] == rows              # and a complete one is taken once


def test_the_catch_up_on_a_weekend_first_is_taken_once_and_a_delete_stays_deleted(w, monkeypatch):
    c = w["client"]
    fake = types.ModuleType("app.money_mf")
    fake.net_worth_value = lambda uid: {"value": 250000.0, "as_of": "2026-10-30"} if uid == "u-pro" else 0      # the Friday close
    monkeypatch.setitem(sys.modules, "app.money_mf", fake)
    import app
    monkeypatch.setattr(app, "money_mf", fake, raising=False)
    db.set_setting("networth:u-pro", json.dumps({"items": [{"id": "a", "kind": "cash", "value": 7000}]}))
    with time_machine.travel(datetime(2026, 11, 1, 5, 0, tzinfo=timezone.utc)):                  # Sunday 1 November, IST
        assert c.get("/money/net-worth", headers=PRO).json()["as_of"] == "2026-10-30"
        rows = nw.history("u-pro")
        assert [(h["d"], h["why"], h["net"]) for h in rows] == [("2026-10-30", "month", 257000)]
        db.set_setting("networth:u-pro", json.dumps({"items": [{"id": "a", "kind": "cash", "value": 9000}]}))
        c.get("/money/net-worth", headers=PRO)
        assert nw.history("u-pro") == rows                                                      # the second visit took nothing
        assert c.delete("/money/net-worth/history/2026-10-30", headers=PRO).json()["history_count"] == 0
        c.get("/money/net-worth", headers=PRO)
        assert nw.history("u-pro") == []                                                        # and a delete stays deleted
    fake.net_worth_value = lambda uid: {"value": 250000.0, "as_of": "2026-11-02"} if uid == "u-pro" else 0
    with time_machine.travel(datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc)):                  # Monday: November's own
        c.get("/money/net-worth", headers=PRO)
        assert [(h["d"], h["why"]) for h in nw.history("u-pro")] == [("2026-11-02", "month")]


def test_a_sunday_edit_does_not_overwrite_fridays_snapshot(w):
    with time_machine.travel(datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc)):                 # Friday
        nw.record("u-t", _t(100), "change", date(2026, 10, 9))
    with time_machine.travel(datetime(2026, 10, 11, 5, 0, tzinfo=timezone.utc)):                # Sunday, IST
        rows = nw.record("u-t", _t(130), "change", date(2026, 10, 9))                           # priced as of Friday's close
    assert [(h["d"], h["net"]) for h in rows] == [("2026-10-09", 100), ("2026-10-11", 130)]


def test_a_partial_change_snapshot_never_replaces_a_complete_one_of_its_day(w):
    lasting = {**_t(60, ["no price or buy price for 1 stock"]), "partial_lasting": True}
    with time_machine.travel(datetime(2026, 10, 5, 5, 0, tzinfo=timezone.utc)):
        nw.record("u-t", _t(100), "month", date(2026, 10, 5))
        rows = nw.record("u-t", lasting, "change")
        assert [(h["d"], h["net"], h["why"], h.get("partial")) for h in rows] == [("2026-10-05", 100, "month", None)]
        nw.delete("u-t")
        nw.record("u-t", _t(100), "change")
        assert [(h["net"], h.get("partial")) for h in nw.record("u-t", lasting, "change")] == [(100, None)]
    with time_machine.travel(datetime(2026, 10, 6, 5, 0, tzinfo=timezone.utc)):                # the next day: recorded, marked
        rows = nw.record("u-t", lasting, "change")
    assert [(h["d"], h["net"], h.get("partial")) for h in rows] == [
        ("2026-10-05", 100, None), ("2026-10-06", 60, ["no price or buy price for 1 stock"])]


def test_the_ppf_value_today_includes_the_yearly_deposits_since_its_balance():
    item = {"id": "p", "kind": "ppf", "balance": 100000, "yearly": 150000, "as_of": "2025-03-31", "rate": 7.1}
    row = nw._asset(item, date(2026, 10, 5), "", None, None, None)
    want = nw.provident(100000, 7.1, date(2025, 3, 31), date(2026, 10, 5), yearly=150000)["value"]
    assert row["value"] == pytest.approx(want) and row["value"] > nw.provident(100000, 7.1, date(2025, 3, 31), date(2026, 10, 5))["value"] + 150000
    assert "yearly deposit" in row["rule"]
    assert nw._asset({**item, "yearly": 0}, date(2026, 10, 5), "", None, None, None)["value"] < row["value"]


def test_a_user_whose_profile_cannot_be_read_gets_a_partial_total(w, monkeypatch):
    monkeypatch.setattr(main.connect_sync, "profile_for", lambda uid: None)
    db.set_setting("networth:u-pro", json.dumps({"items": [{"id": "a", "kind": "cash", "value": 7000}]}))
    assert main._nw_value_of("u-pro")["totals"]["partial"] == ["My Holdings couldn't be read"]


# ---------- review rev5a ----------
def _fake_mf(monkeypatch, fn):
    fake = types.ModuleType("app.money_mf")
    fake.net_worth_value = fn
    monkeypatch.setitem(sys.modules, "app.money_mf", fake)
    import app
    monkeypatch.setattr(app, "money_mf", fake, raising=False)


def test_a_stock_at_cost_keeps_the_history_going(w):
    """B2: one held stock without a price (a suspended company) counts at cost: the total is whole, said in a note, and
    the change and month snapshots are taken as before (they used to stop for good)."""
    from app import holdings
    c = w["client"]
    holdings.save("u-pro", [{"symbol": "RELIANCE", "exchange": "NSE", "name": "Reliance", "qty": 10.0, "avg": 2400.0},
                            {"symbol": "ZOMBIECO", "exchange": "BSE", "name": "Suspended Co", "qty": 100.0, "avg": 12.0}], "Statement")
    db.set_setting("networth:u-pro", json.dumps({"items": [{"id": "a", "kind": "cash", "value": 7000, "as_of": "2026-09-01"}]}))
    v = c.get("/money/net-worth", headers=PRO).json()
    assert v["totals"]["partial"] is None and v["totals"]["notes"] == ["1 stock counted at cost (no price)"]
    v = add(c, {"kind": "cash", "name": "x", "value": 1000})
    assert v["history"] and (v["history"][-1]["why"], v["history"][-1].get("partial"), v["history"][-1]["net"]) == ("change", None, v["totals"]["net"])
    assert nw.Job(main._nw_value_of).tick(datetime(2026, 11, 1, 11, 30, tzinfo=timezone.utc)) == 1
    assert [(h["d"], h["why"], h.get("partial")) for h in nw.history("u-pro")][-1] == ("2026-11-01", "month", None)


def test_a_holding_with_nothing_to_value_it_by_is_named_and_the_history_goes_on_marked(w, monkeypatch):
    """B2: a statement's holding (no buy price) without a price can't be counted: the total names it and is partial, and
    each change is still recorded, flagged with what it leaves out (the chart marks it)."""
    from app import holdings
    c = w["client"]
    holdings.save("u-pro", [{"symbol": "ZOMBIECO", "exchange": "BSE", "name": "Suspended Co", "qty": 100.0, "avg": None}], "Statement")
    add(c, {"kind": "cash", "value": 7000})
    v = add(c, {"kind": "cash", "value": 1000})
    assert v["totals"]["partial"] == ["no price or buy price for 1 stock"] and v["totals"]["partial_lasting"]
    assert v["history"][-1]["why"] == "change" and v["history"][-1]["partial"] == ["no price or buy price for 1 stock"]
    assert v["history"][-1]["net"] == 8000


def test_a_weekend_edit_is_dated_the_day_it_was_made(w, monkeypatch):
    """B3: an entry added on Saturday, with prices as of Friday's close, is snapshotted on Saturday (dated Friday it became
    the baseline, and the headline read "₹0 since Fri")."""
    _fake_mf(monkeypatch, lambda uid: {"value": 250000.0, "as_of": "2026-10-09T15:30:00+05:30"} if uid == "u-pro" else 0)
    db.set_setting("networth:u-pro", json.dumps({"items": [{"id": "a", "kind": "cash", "value": 7000, "as_of": "2026-09-01"}]}))
    nw.record("u-pro", {"net": 257000, "assets": 257000, "liabilities": 0}, "month", date(2026, 10, 1))
    with time_machine.travel(datetime(2026, 10, 10, 5, 0, tzinfo=timezone.utc)):                # Saturday 10 Oct, 10:30 IST
        v = add(w["client"], {"kind": "cash", "name": "FD matured", "value": 50000})
    assert v["as_of"] == "2026-10-09"                                                            # the prices' day
    assert [(h["d"], h["why"], h["net"]) for h in v["history"]] == [("2026-10-01", "month", 257000), ("2026-10-10", "change", 307000)]


def test_editing_an_imported_entry_keeps_it_updated_by_the_next_import(w):
    """B4: an EPF entry read from a passbook, or an NPS one from a statement, stays marked as read when edited (renamed,
    a monthly amount added), so the next passbook or statement updates it instead of being refused."""
    from app.connect import docs, statements, sync
    c = w["client"]
    prof = sync.profile_for("u-pro")
    docs.confirm(prof, "epf", {"balance": 500000, "as_of": "2025-03-31"})
    statements.save_nps("u-pro", {"tier1": 300000, "tier2": 0}, "2026-08-31", "pro")
    for e in nw.load("u-pro")["items"]:
        form = ({"kind": "epf", "name": "My EPF", "balance": e["balance"], "as_of": e["as_of"], "monthly": 3600} if e["kind"] == "epf"
                else {"kind": "nps", "name": "My NPS", "tier1": e["tier1"], "as_of": e["as_of"]})
        assert c.put(f"/money/net-worth/items/{e['id']}", headers=PRO, json=form).status_code == 200
    assert all(i.get("auto") for i in nw.load("u-pro")["items"])
    assert docs.confirm(prof, "epf", {"balance": 650000, "as_of": "2026-03-31"})["detail"] == "EPF balance saved in Net worth."
    assert statements.save_nps("u-pro", {"tier1": 320000, "tier2": 0}, "2026-09-30", "pro") == ""
    got = {i["kind"]: i for i in nw.load("u-pro")["items"]}
    assert len(nw.load("u-pro")["items"]) == 2 and got["epf"]["balance"] == 650000 and got["nps"]["tier1"] == 320000
    # changed to another kind, it is the user's own entry
    e = got["nps"]
    c.put(f"/money/net-worth/items/{e['id']}", headers=PRO, json={"kind": "cash", "name": "Cash", "value": 5})
    assert not next(i for i in nw.load("u-pro")["items"] if i["id"] == e["id"]).get("auto")


def test_imports_keep_to_the_free_plans_entries(w, monkeypatch):
    """B5: an EPF passbook or NPS statement adds an entry only within the plan's limit, as a typed one would; the import
    says so with the same message. An entry imported before is still updated."""
    from app.connect import docs, statements, sync
    payments_live(monkeypatch)
    c = w["client"]
    for n in range(4):
        add(c, {"kind": "cash", "name": f"c{n}", "value": 100}, FREE)
    prof = sync.profile_for("u-free")
    assert docs.confirm(prof, "epf", {"balance": 500000, "as_of": "2026-03-31"})["detail"] == "EPF balance saved in Net worth."
    typed = c.post("/money/net-worth/items", headers=FREE, json={"kind": "cash", "name": "c6", "value": 100})
    assert typed.status_code == 402
    msg = typed.json()["detail"]["message"]
    got = docs.confirm(prof, "nps", {"tier1": 300000, "as_of": "2026-03-31"})
    assert msg in got["detail"] and "NPS" in got["detail"]
    assert msg in statements.save_nps("u-free", {"tier1": 300000, "tier2": 0}, "2026-09-30", prof["_plan"])
    assert len(nw.load("u-free")["items"]) == 5
    assert docs.confirm(prof, "epf", {"balance": 600000, "as_of": "2026-09-30"})["detail"] == "EPF balance saved in Net worth."
    assert [i["balance"] for i in nw.load("u-free")["items"] if i["kind"] == "epf"] == [600000]


def test_the_monthly_job_skips_a_month_already_taken_or_removed(w):
    """B8: the job, late, doesn't take a second "month" snapshot when a visit already took this month's, and doesn't put
    back one the user removed this month."""
    c = w["client"]
    db.set_setting("networth:u-pro", json.dumps({"items": [{"id": "a", "kind": "cash", "value": 7000, "as_of": "2026-09-01"}]}))
    with time_machine.travel(datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc)):                  # Monday 2 Nov, a visit
        c.get("/money/net-worth", headers=PRO)
    assert [(h["d"], h["why"]) for h in nw.history("u-pro")] == [("2026-11-02", "month")]
    nw.Job(main._nw_value_of).tick(datetime(2026, 11, 3, 11, 30, tzinfo=timezone.utc))
    assert [(h["d"], h["why"]) for h in nw.history("u-pro")] == [("2026-11-02", "month")]
    with time_machine.travel(datetime(2026, 12, 2, 5, 0, tzinfo=timezone.utc)):
        c.get("/money/net-worth", headers=PRO)
        assert c.delete("/money/net-worth/history/2026-12-02", headers=PRO).status_code == 200
    nw.Job(main._nw_value_of).tick(datetime(2026, 12, 2, 11, 30, tzinfo=timezone.utc))
    assert [h["d"] for h in nw.history("u-pro")] == ["2026-11-02"]


def test_an_old_dollar_rate_is_dated_where_it_is_used():
    """Item a: a dollar rate read more than a day ago (kept while the day's read failed) is named with its date."""
    now = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)
    assert nw.rate_day("2026-10-09T03:00:00+00:00", now) == " (the rate of 9 Oct 2026)"
    assert nw.rate_day("2026-10-12T01:00:00+00:00", now) == "" and nw.rate_day(None, now) == ""
    t = nw.build([], {"in": 0, "us": 8800.0, "count": 1, "usd_inr": 88.0, "usd_inr_at": "2026-09-01T03:00:00+00:00"}, None, nw.Prices())
    assert "at ₹88.00 a dollar (the rate of 1 Sep 2026)" in t["assets"][0]["rule"]


def test_the_month_start_snapshot_retries_a_user_whose_read_failed(w, monkeypatch):
    for u in ("u1", "u2"):
        db.set_setting(nw.KEY + u, json.dumps({"items": []}))
    calls = {"u1": 0}

    def value_of(uid):
        if uid == "u1":
            calls["u1"] += 1
            if calls["u1"] == 1:
                raise RuntimeError("price source down")
        return {"totals": {"assets": 100.0, "liabilities": 0.0, "net": 100.0}}
    job = nw.Job(value_of)
    assert job.tick(datetime(2026, 11, 1, 11, 0, tzinfo=timezone.utc)) == 1            # u2 only
    assert job.status["last_error"]
    # the unfinished run is resumed once it has gone quiet
    later = time.time() + 700
    monkeypatch.setattr(time, "time", lambda: later)
    assert job.tick(datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc)) == 1           # u1 now
    assert calls["u1"] == 2 and [h["d"][:7] for h in nw.history("u1")] == ["2026-11"]
    assert job.status["last_error"] is None
