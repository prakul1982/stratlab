"""26 Oct 2026 re-score, the rest of it (RC2B-008, -010, -026, -028, -031): a business update's period, the weekly brief's
words about a scanned stock, the named-holder counts, the figures' wording and closing your own account."""
import json
from datetime import date

import pytest

from app import biz_updates as B
from app import db, holdings, main, money_networth, shareholders as S, user_data  # noqa: F401  (main first: loads the app's modules in order)
from app.newsletter import job, write
from tests import world as W
from tests.fake_db import headers

FREE, PRO, ADMIN = headers("free-token"), headers("pro-token"), headers("admin-token")


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    world["fake"] = db.sb()
    yield world
    S.forget()
    world["close"]()


def read(at: str, period: str, figures: list[dict], span: str = "month", **kw) -> dict:
    return {"at": at, "title": kw.get("title", "update"), "url": f"https://nsearchives.nseindia.com/corporate/{at}.pdf", "read_at": at,
            "period": period, "span": span, "problem": None, "reader": B.READER,
            "figures": [{"segment": None, "unit": "units", "basis": "month", "prior": None, "headline": False, "quote": "q", "page": 1,
                         "own": True, **f} for f in figures]}


# ---------- RC2B-008: a month can't have a figure before it ends ----------
def test_a_period_is_a_month_that_was_over_on_the_filing_day():
    assert B.settled("2026-10", "2026-10-01T12:00", "month") == "2026-09"          # Tata Motors PV, filed 1 Oct: "Oct 2026"
    assert B.settled("2026-09", "2026-10-01T12:00", "month") == "2026-09"
    assert B.settled("2026-10", "2026-10-31T18:00", "month") == "2026-10"          # filed on the month's last day
    assert B.settled("2026-10", "2026-10-01T12:00", "quarter") == "2026-09"        # a quarter is named by its last month
    assert B.settled("2026-11", "2026-12-02T12:00", "quarter") == "2026-09"
    assert B.settled("2026-12", "2027-01-02T12:00", "quarter") == "2026-12"
    assert B.settled(None, "2026-10-01") is None and B.settled("2026-10", "not a date") == "2026-10"


def test_the_period_the_reader_keeps_is_a_finished_one():
    page = "Tata Motors Passenger Vehicles Q2 FY27 business update\nTotal sales 2,01,723 units"
    reply = {"period": "2026-10", "span": "quarter", "figures": [
        {"metric": "Total sales", "value": 201723, "unit": "units", "basis": "quarter", "headline": True, "quote": "Total sales 2,01,723 units", "page": 1}]}
    period, span, figs = B.clean_figures(reply, [page], "2026-10-01T12:00")
    assert (period, span) == ("2026-09", "quarter") and figs[0]["value"] == 201723


def test_a_stored_october_is_shown_as_september_with_no_empty_october_row():
    # a read kept before this rule: period "2026-10" for a filing of 1 Oct (the API said period: "2026-10")
    reads = {"a": read("2026-10-01T12:00", "2026-10", [{"metric": "Total sales", "value": 201723, "prior": 150000, "headline": True}], span="quarter"),
             "b": read("2026-07-01T12:00", "2026-06", [{"metric": "Total sales", "value": 150000, "headline": True}], span="quarter")}
    ms = B.series(reads)
    assert ms[0]["latest"]["period"] == "2026-09" and ms[0]["points"][-1]["period"] == "2026-09"
    assert all(p["period"] <= "2026-09" for p in ms[0]["points"])
    assert "in Q2 FY27" in B.words(B.headline(ms))
    row = B._headline_row("TMPV", "Tata Motors Passenger Vehicles", reads)
    assert row["period"] == "2026-09"


def test_a_filing_list_shows_the_settled_period(w):
    db.set_setting(B.KEY + "TMPV", json.dumps({"reads": {"f1": {**read("2026-10-01T12:00", "2026-10", [{"metric": "Total sales", "value": 5}], span="quarter"),
                                                                   "title": "Business update Q2 FY27"}}}))
    B.forget()
    got = B.view("TMPV", [], True)
    assert got["filings"][0]["period"] == "2026-09"


# ---------- RC2B-028: the filing's own words for a measure ----------
def test_a_figure_is_named_and_unit_written_like_the_rest():
    f = B.tidy_figure({"metric": "Total Sales (units, month)", "unit": "Units", "segment": None})
    assert (f["metric"], f["unit"]) == ("Total sales", "units")
    assert B.tidy_figure({"metric": "Total Vehicles", "unit": "units"})["metric"] == "Total vehicles"
    assert B.tidy_figure({"metric": "Total Sales (Total Domestic + Export)", "unit": "units"})["metric"] == "Total Sales (Total Domestic + Export)"
    assert B.tidy_figure({"metric": "Production: Grand Total (PV+LCV)", "unit": "₹ Crore"})["unit"] == "₹ crore"
    assert B.tidy_figure({"metric": "Installed capacity", "unit": "MW"})["unit"] == "MW"            # an abbreviation stays
    assert B.tidy_figure({"metric": "Energy sold", "unit": "GWh"})["unit"] == "GWh"
    assert B.tidy_figure({"metric": "CASA ratio", "unit": "%"})["unit"] == "%"
    ms = B.series({"a": read("2026-10-01T12:00", "2026-09", [{"metric": "Total Sales (units, month)", "unit": "Units", "value": 24049, "headline": True}]),
                   "b": read("2026-09-01T12:00", "2026-08", [{"metric": "Total sales", "unit": "units", "value": 20000, "headline": True}])})
    assert len(ms) == 1 and ms[0]["metric"] == "Total sales" and ms[0]["unit"] == "units" and ms[0]["prev"]["value"] == 20000   # one measure, not two
    assert B.fmt_value(24049, ms[0]["unit"]) == "24,049 units"


# ---------- RC2B-010: no price move beside a stock a scan named ----------
def test_no_scan_sentence_carries_a_price_move():
    text = ("The market moved on the week. In the scan of NIFTY 50 stocks, Tech Mahindra Limited dropped 2.14%. "
            "Two stocks newly matched the Stage 2 rule. 3 sectors moved to another quadrant.")
    got = write.no_scan_moves(text, ["TECHM", "Tech Mahindra Limited"])
    assert "2.14" not in got and "Tech Mahindra" not in got
    assert "Two stocks newly matched the Stage 2 rule." in got and "3 sectors moved" in got
    # a stock's name beside a percent, with no scan word, goes too; a sentence without a percent stays
    assert write.no_scan_moves("TECHM fell 2.14% on Thursday. TECHM is in the list.", ["TECHM"]) == "TECHM is in the list."
    assert write.no_scan_moves("Infosys rose 3%.", ["TECHM"]) == "Infosys rose 3%."
    assert write.no_scan_moves("", ["X"]) == ""
    f = {"scan": {"st_s2": [{"symbol": "TECHM", "name": "Tech Mahindra Limited"}], "stage2": [{"symbol": "ABB", "name": None}]}}
    assert write.scan_names(f) == ["TECHM", "Tech Mahindra Limited", "ABB"]


def test_a_stored_weekly_brief_is_read_without_the_scanned_stocks_move(w):
    c = w["client"]
    iid = job.issue_id("market", "IN", "2026-10-24", True)
    issue = {"id": iid, "kind": "market", "region": "IN", "day": "2026-10-24", "weekly": True, "subject": "Market Brief India, week to 23 Oct: NIFTY 50 −2.36%",
             "title": "NIFTY 50 down 2.36%", "ai": True, "summary": "NIFTY 50 −2.36% over the week.",
             "ai_summary": "Banks led. In the scan of NIFTY 50 stocks, Tech Mahindra Limited dropped 2.14%. Eight sectors moved quadrant.",
             "indices": [{"name": "NIFTY 50", "price": 24100.5, "change_pct": -2.36}],
             "sections": [{"title": "Newly matched Stage 2 + Supertrend in the last 5 days (NIFTY 50 stocks)",
                           "items": [{"text": "TECHM matches the Stage 2 rule with the price above its Supertrend (ST S2)", "url": None, "lines": []}]}],
             "at": "2026-10-24T09:00+05:30"}
    job.save(issue)
    got = job.load(iid)
    assert "2.14" not in got["ai_summary"] and "Eight sectors moved quadrant." in got["ai_summary"]
    shown = c.get(f"/news/{iid}", headers=PRO).json()
    assert "2.14" not in shown.get("ai_summary", "") and "2.14" not in shown["html"]
    assert "2.14" in json.loads(db.get_setting(job._key(*job.parse_id(iid))))["ai_summary"]        # what is stored is left as it was


# ---------- RC2B-026: the landing's count is the result's ----------
def holder(name: str, pct: float = 2.0) -> dict:
    return {"name": name, "kind": "Insurance", "group": "public", "shares": int(pct * 1000), "pct": pct}


def quarter(q: str) -> dict:
    return {"quarter": q, "rec": q, "url": "https://nsearchives.nseindia.com/a.xml", "filed": q + "T10:00", "name": "Co"}


def test_a_holder_is_counted_in_the_companies_the_result_lists(w):
    LIC = "LIFE INSURANCE CORPORATION OF INDIA"
    # AAA and BBB: named in the latest quarter; CCC: only in the quarter before (dropped); DDD: only three quarters ago
    for sym, qs in (("AAA", {"2026-03-31": [], "2026-06-30": [LIC], "2026-09-30": [LIC]}), ("BBB", {"2026-06-30": [], "2026-09-30": [LIC]}),
                    ("CCC", {"2026-06-30": [LIC], "2026-09-30": []}), ("DDD", {"2026-03-31": [LIC], "2026-06-30": [], "2026-09-30": []})):
        for q, names in qs.items():
            S.store(sym, quarter(q), {"name": sym + " Ltd", "isin": "", "holders": [holder(n) for n in names] or [holder("SOME OTHER FUND", 3.0)]})
    S.forget()
    found = S.search("life insurance corporation")
    assert found and found[0]["companies"] == 3                       # AAA, BBB, CCC: not DDD, whose line is two quarters back
    result = S.holdings([n["key"] for n in found[0]["names"]])
    assert len(result["rows"]) == found[0]["companies"] == 3
    assert result["count"] + result["dropped"] == 3
    assert [p["companies"] for p in S.popular() if "LIFE INSURANCE" in p["label"].upper()] == [3]        # the landing's count


# ---------- RC2B-031: closing your own account ----------
def seed(uid: str):
    holdings.save(uid, [{"symbol": "TCS", "qty": 3, "avg": 3000.0}], "Manual")
    money_networth.save(uid, [{"id": "n1", "name": "Savings", "kind": "cash", "value": 1000}])
    db.set_setting(f"billing:{uid}", json.dumps({"name": "A Person", "address": "1 Road", "gstin": ""}))
    db.set_setting(f"invoices:{uid}", json.dumps(["INV-9"]))
    db.set_setting("invoice:INV-9", json.dumps({"number": "INV-9", "user_id": uid, "total": 699}))
    iid = job.issue_id("my_stocks", uid, "2026-10-23", False)
    db.set_setting(job._key(*job.parse_id(iid)), json.dumps({"id": iid}))
    db.set_setting(job._index_key("my_stocks", uid), json.dumps([iid]))
    db.set_setting(job.SENT + iid, json.dumps({"sent": ["x"]}))
    db.set_setting(f"lifecycle:{uid}", json.dumps({"welcome": "2026-10-01"}))
    return iid


def close(c, who, email, **kw):
    return c.post("/me/delete-account", headers=who, json={"confirm": email}, **kw)


def test_closing_the_account_deletes_the_data_and_the_sign_in_and_keeps_the_invoices(w):
    c = w["client"]
    mine, theirs = seed("u-free"), seed("u-basic")
    r = close(c, FREE, "free@example.com")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["closed"] and body["failed"] == [] and "invoices" in body["kept"].lower()
    assert "u-free" in w["fake"].auth.admin.deleted                                        # the sign-in service's record
    assert db.find_profile("u-free") is None
    assert holdings.load("u-free")["items"] == [] and db.get_setting(money_networth.KEY + "u-free") is None
    assert db.get_setting("billing:u-free") is None and db.get_setting("lifecycle:u-free") is None
    assert db.get_setting(job._index_key("my_stocks", "u-free")) is None and db.get_setting(job.SENT + mine) is None
    assert json.loads(db.get_setting("invoices:u-free")) == ["INV-9"] and db.get_setting("invoice:INV-9")      # kept, as tax law asks
    # nobody else's rows were touched
    assert db.find_profile("u-basic") and holdings.load("u-basic")["items"]
    assert db.get_setting("billing:u-basic") and db.get_setting(job.SENT + theirs) and "u-basic" not in w["fake"].auth.admin.deleted
    # the same token is refused from now on, and no profile is made for it again
    assert c.get("/me", headers=FREE).status_code == 401
    assert db.find_profile("u-free") is None


def test_closing_needs_the_email_typed_and_is_refused_for_the_owner_and_a_billed_plan(w):
    c = w["client"]
    seed("u-free")
    assert close(c, FREE, "nope@example.com").status_code == 400
    assert close(c, FREE, "").status_code in (400, 422)
    assert db.find_profile("u-free") and w["fake"].auth.admin.deleted == []
    assert c.post("/me/delete-account", headers={}, json={"confirm": "x"}).status_code == 401
    r = close(c, ADMIN, "owner@example.com")
    assert r.status_code == 403 and "owner_account" in json.dumps(r.json())
    assert db.find_profile("u-admin")
    # a plan still being billed: cancel it first
    db.update_profile("u-pro", razorpay_subscription_id="sub_1", plan="pro", plan_status="active", cancel_at_period_end=False)
    r = close(c, PRO, "pro@example.com")
    assert r.status_code == 409 and "Cancel it first" in json.dumps(r.json())
    assert db.find_profile("u-pro") and "u-pro" not in w["fake"].auth.admin.deleted
    # cancelled at the period's end (nothing more will be charged), or a plan that has ended: closing goes ahead
    db.update_profile("u-pro", cancel_at_period_end=True)
    assert close(c, PRO, "pro@example.com").json()["closed"] is True


def test_a_failed_step_leaves_the_account_open_and_the_sign_in_alone(w, monkeypatch):
    c = w["client"]
    seed("u-free")
    def down(uid):
        raise RuntimeError("store down")
    with monkeypatch.context() as m:
        m.setattr(user_data, "CLOSE_STEPS", [("billing_details", "Billing details", down)])
        r = close(c, FREE, "free@example.com").json()
    assert r["ok"] is False and r["closed"] is False and [f["key"] for f in r["failed"]] == ["billing_details"]
    assert db.find_profile("u-free") and w["fake"].auth.admin.deleted == []
    # the sign-in service refusing: the data is gone, the account is open, and trying again finishes it
    w["fake"].auth.admin.fail = RuntimeError("auth down")
    r = close(c, FREE, "free@example.com").json()
    assert r["closed"] is False and r["failed"][0]["key"] == "signin" and db.find_profile("u-free")
    w["fake"].auth.admin.fail = None
    assert close(c, FREE, "free@example.com").json()["closed"] is True


def test_a_late_payment_event_for_a_closed_account_makes_no_profile(w, monkeypatch):
    from app import billing
    monkeypatch.setattr(billing, "_confirmed", lambda sub: sub)
    event = {"event": "subscription.charged", "payload": {"subscription": {"entity": {"id": "sub_gone", "status": "active", "notes": {"user_id": "u-gone"}}}}}
    billing._act(event)
    assert db.find_profile("u-gone") is None
