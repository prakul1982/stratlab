"""25 Oct 2026 deep audit of Admin (DJ-001 .. DJ-039), the server's side: test accounts are left out of every count,
Users lists when people were last active, the accounts with no profile and the given plans ending, storage is measured
on the real databases against their real limits, audit rows carry their check date and old price mismatches are checked
again, statuses agree with each other, Brevo's sends are read against its daily limit, and Money reads Razorpay."""
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from app import admin, admin_jobs, alerts, audit, billing, db, email_previews, main, platform_check, pricing, storage  # noqa: F401
from app.config import settings
from tests import world as W
from tests.fake_db import headers

A = headers("admin-token")


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    main.forget_overview()
    yield world
    main.forget_overview()
    world["close"]()


def _now(**kw) -> str:
    return (datetime.now(timezone.utc) + timedelta(**kw)).isoformat()


# ---------- DJ-001: test accounts left out of every count, with a switch ----------
def test_test_accounts_are_left_out_of_every_count_and_the_users_list(w, monkeypatch):
    c = w["client"]
    monkeypatch.setattr(admin, "sign_ins", lambda fresh=False: ({}, None))
    before = c.get("/admin/overview?fresh=1", headers=A).json()["stats"]
    # two reviewer accounts made today: one "+sl-" alias of the admin's address, one only recorded by /admin/test-account
    db.sb().table("profiles").insert({"id": "u-t1", "email": "owner+sl-free@example.com", "plan": "free", "created_at": _now()}).execute()
    db.sb().table("profiles").insert({"id": "u-t2", "email": "reviewer@example.com", "plan": "pro", "plan_status": "active",
                                      "created_at": _now()}).execute()
    db.set_setting(admin.TEST_ACCOUNTS, json.dumps({"u-t2": {"email": "reviewer@example.com", "label": "pro-1", "plan": "pro"}}))
    db.sb().table("usage_events").insert({"user_id": "u-t1", "kind": "backtest", "created_at": _now()}).execute()
    st = c.get("/admin/overview?fresh=1", headers=A).json()["stats"]
    assert st["test_accounts"] == 2
    for k in ("users", "signups_today", "new_7d", "experiments_month"):
        assert st[k] == before[k], k
    assert st["plans"] == before["plans"] and st["given"] == before["given"]
    shown = c.get("/admin/overview?fresh=1&test=1", headers=A).json()["stats"]          # "Show test accounts"
    assert shown["users"] == before["users"] + 2 and shown["signups_today"] == before["signups_today"] + 2
    assert shown["plans"]["pro"] == before["plans"]["pro"] + 1 and shown["experiments_month"] == before["experiments_month"] + 1
    listed = {u["id"]: u for u in c.get("/admin/users", headers=A).json()}
    assert "u-t1" not in listed and "u-t2" not in listed
    with_tests = {u["id"]: u for u in c.get("/admin/users?test=1", headers=A).json()}
    assert with_tests["u-t1"]["test"] and with_tests["u-t2"]["test"]
    owners = {u["id"]: u for u in c.get("/admin/users?q=owner&test=1", headers=A).json()}
    assert owners["u-t1"]["test"] and not owners["u-admin"]["test"]
    # the weekly summary counts as Overview does
    assert admin.week_stats(datetime.now(timezone.utc) - timedelta(days=7))["users"] == before["users"]


def test_a_test_address_is_an_alias_of_an_admins_own(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "owner@example.com, me+work@x.com")
    assert admin.is_test_email("owner+sl-basic-1@example.com") and admin.is_test_email("ME+sl-pro@x.com")
    assert not admin.is_test_email("owner@example.com") and not admin.is_test_email("someone+sl-free@example.com")
    assert not admin.is_test_email("owner+work@example.com") and not admin.is_test_email(None)


# ---------- DJ-009, DJ-010, DJ-011: last active, sign-ins with no profile, given plans ending ----------
def test_users_say_when_each_was_last_active(w, monkeypatch):
    seen = {"u-pro": {"email": "pro@example.com", "created_at": _now(days=-30), "last_sign_in_at": _now(days=-3)},
            "u-basic": {"email": "basic@example.com", "created_at": _now(days=-30), "last_sign_in_at": _now(days=-9)}}
    monkeypatch.setattr(admin, "sign_ins", lambda fresh=False: (seen, None))
    db.sb().table("usage_events").insert({"user_id": "u-basic", "kind": "ai", "created_at": _now(hours=-2)}).execute()
    rows = {u["id"]: u for q in ("pro@", "basic@", "free@") for u in w["client"].get(f"/admin/users?q={q}", headers=A).json()}
    assert rows["u-pro"]["last_active"] == seen["u-pro"]["last_sign_in_at"] == rows["u-pro"]["last_sign_in"]
    assert rows["u-basic"]["last_active"] > seen["u-basic"]["last_sign_in_at"]        # the AI build is later than the sign-in
    assert rows["u-free"]["last_active"] is None and not rows["u-free"]["sign_ins_unread"]
    assert admin.active_users(7) >= 2


def test_sign_ins_without_a_profile_and_given_plans_ending_are_listed(w, monkeypatch):
    seen = {"u-pro": {"email": "pro@example.com", "created_at": _now(days=-30), "last_sign_in_at": _now(days=-1)},
            "u-ghost": {"email": "ghost@example.com", "created_at": _now(days=-38), "last_sign_in_at": None}}
    monkeypatch.setattr(admin, "sign_ins", lambda fresh=False: (seen, None))
    db.update_profile("u-basic", current_period_end=_now(days=2))           # given by hand (no subscription), ends in 2 days
    db.update_profile("u-pro", current_period_end=_now(hours=-3))           # ended 3 hours ago, still on it for the grace day
    v = w["client"].get("/admin/accounts", headers=A).json()
    assert [o["id"] for o in v["orphans"]] == ["u-ghost"]
    ending = {e["id"]: e for e in v["ending"]}
    assert not ending["u-basic"]["ended"] and ending["u-pro"]["ended"] and ending["u-pro"]["plan_now"] == "pro"
    assert w["client"].get("/admin/accounts", headers=headers("pro-token")).status_code == 403


def test_the_sign_in_list_is_read_a_page_at_a_time(monkeypatch):
    pages = [[NS(id=f"u{i}", email=f"u{i}@x.com", created_at=None, last_sign_in_at=None) for i in range(1000)],
             [NS(id="last", email="last@x.com", created_at=datetime(2026, 9, 17, tzinfo=timezone.utc), last_sign_in_at=None)]]
    asked = []
    api = NS(list_users=lambda page, per_page: asked.append(page) or pages[page - 1])
    fake = NS(auth=NS(admin=api))
    monkeypatch.setattr(db, "sb", lambda: fake)
    got, error = admin.sign_ins(fresh=True)
    assert error is None and len(got) == 1001 and asked == [1, 2] and got["last"]["created_at"].startswith("2026-09-17")
    monkeypatch.setattr(db, "sb", lambda: NS(auth=NS(admin=NS(list_users=lambda **k: (_ for _ in ()).throw(RuntimeError("down"))))))
    got, error = admin.sign_ins(fresh=True)
    assert got == {} and "didn't answer" in error


# ---------- DJ-020: storage on the real databases against their real limits ----------
class _Store:
    def usage(self):
        return {"total": 382 * 1024 * 1024, "tables": []}


def test_storage_measures_railway_and_supabase_each_against_its_own_limit(monkeypatch):
    MB = 1024 * 1024
    supa = NS(rpc=lambda name: NS(execute=lambda: NS(data={"total": 70 * MB, "tables": [
        {"name": "public.app_settings", "bytes": 57 * MB}, {"name": "auth.users", "bytes": 1 * MB}]})))
    monkeypatch.setattr(db, "on_railway", lambda: True)
    monkeypatch.setattr(db, "usage", lambda: {"total": int(7.5 * MB), "tables": [], "settings": []})     # the app schema only
    monkeypatch.setattr(db, "supabase", lambda: supa)
    monkeypatch.setattr(db, "get_setting", lambda k: None)
    monkeypatch.setattr(storage.market_store, "store", lambda: _Store())
    monkeypatch.setattr(settings, "RAILWAY_VOLUME_MB", 0)
    monkeypatch.setattr(settings, "RAILWAY_PROJECT_ID", "proj-1")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://abcdref.supabase.co")
    r = storage.report()
    rail, sb = r["databases"]
    assert rail["name"] == "Railway Postgres" and rail["used"] == 382 * MB and rail["limit"] is None
    assert rail["link"] == "https://railway.com/project/proj-1" and "Railway" in rail["note"]        # a link, not a guess
    assert sb["used"] == 70 * MB and sb["limit"] == 500 * MB and sb["share"] == 0.14
    assert sb["reclaimable"] == 57 * MB and sb["reclaimable_tables"] == ["public.app_settings"]
    assert sb["link"] == "https://supabase.com/dashboard/project/abcdref/settings/usage"
    assert r["share"] is None                                   # the 7.5 MB app schema is never set against Supabase's limit
    c = storage.check()                                         # System's line: the same figures
    assert c["state"] == "pass"
    assert "Railway Postgres: 382 MB used" in c["detail"] and "Supabase: 70 MB of 500 MB used (14%), 57 MB of it copies" in c["detail"]
    monkeypatch.setattr(settings, "RAILWAY_VOLUME_MB", 5000)    # the owner set the volume's size
    rail = storage.report()["databases"][0]
    assert rail["limit"] == 5000 * MB and rail["share"] == round(382 / 5000, 3)
    assert storage._mb(int(7.5 * MB)) == "7.5 MB" and storage._mb(382 * MB) == "382 MB"     # the panel's own rounding


# ---------- DJ-026, DJ-027: audit rows dated, old price mismatches checked again, a P/E under 1 ----------
def test_a_day_old_price_mismatch_is_checked_again_and_drops_off_once_it_agrees(monkeypatch):
    listing = [{"symbol": s, "name": s, "listed": "2020-01-01"} for s in ("TBZ", "OKCO")]
    wrong = {"TBZ": True}

    def check(sym):
        issues = [{"level": "mismatch", "area": "Prices", "detail": "Last close 595.00 vs 577.00 on the company page"}] if wrong.get(sym) else []
        return {"symbol": sym, "name": sym, "seconds": 0.1, "issues": issues}
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    a = audit.MarketAudit(lambda: listing, check, pause=0)
    a.set_enabled(True)
    a.refresh_list(force=True)
    a.start_full(everything=True)
    while a.step():
        pass
    assert a.rows["TBZ"]["at"] and a.queue() == []
    old = (datetime.now(timezone.utc) - timedelta(hours=audit.STALE_MISMATCH_HOURS + 1)).isoformat()
    a.rows["TBZ"]["at"] = a.rows["OKCO"]["at"] = old
    assert a.stale_mismatches() == ["TBZ"] and a.queue() == ["TBZ"]          # only the mismatch, not the clean one
    wrong["TBZ"] = False                                                     # the prices have caught up
    assert a.step() == "TBZ" and a.rows["TBZ"]["issues"] == [] and a.queue() == []
    assert not [r for r in a.status()["rows"] if r["symbol"] == "TBZ"]


def test_audit_mismatch_rows_say_when_they_were_checked(w, monkeypatch):
    rows = [{"symbol": "TBZ", "name": "TBZ", "at": "2026-10-05T04:00:00+00:00",
             "issues": [{"level": "mismatch", "area": "Prices", "detail": "x"}]},
            {"symbol": "ABC", "name": "ABC", "at": "2026-10-09T04:00:00+00:00",
             "issues": [{"level": "mismatch", "area": "Prices", "detail": "y"}]}]
    monkeypatch.setattr(main.market_audit, "status", lambda: {"rows": rows})
    counts, checked = main.audit_summary()
    assert counts["IN"] == 2 and checked["IN"] == {"oldest": rows[0]["at"], "newest": rows[1]["at"]}
    sv = w["client"].get("/admin/overview", headers=A).json()["server"]
    assert sv["audit_checked"]["IN"]["oldest"] == rows[0]["at"] and "data_note" in sv


def test_a_pe_under_one_is_suspect_and_old_equal_pe_rows_are_not_mismatches():
    assert audit.pe_text(0.08) == "0.08" and audit.pe_text(24.31) == "24.3"
    p = {"name": "Coromandel Agro", "pl": {"cols": ["Mar 2026", "TTM"], "rows": {"Sales": [10, 10], "Net Profit": [2, 2]}}}
    got = [i for i in audit.check_numbers(p, {"years": [], "quarters": []}, {"pe": 0.08, "market_cap_cr": 0.3}) if i["area"] == "Valuation"]
    assert [i["level"] for i in got] == ["gap"] and "P/E 0.08 on the company page is under 1" in got[0]["detail"]
    old = {"level": "mismatch", "area": "Valuation", "detail": "P/E 0.1 on the company page, 0.1 from market cap ÷ trailing profit"}
    again = audit.restate(old)
    assert again["level"] == "gap" and "under 1" in again["detail"]
    assert audit.restate({**old, "detail": "P/E 24.0 on the company page, 24.2 from market cap ÷ trailing profit"}) is None
    big = {**old, "detail": "P/E 10.0 on the company page, 20.0 from market cap ÷ trailing profit"}
    assert audit.restate(big) == big                                        # a real difference stays


# ---------- DJ-021, DJ-022: what an unread source leaves out; the jobs' whole clocks ----------
def test_a_partial_market_events_run_says_what_is_missing_and_whose_fault():
    words = admin_jobs.missing_words("Index provider: www.niftyindices.com answered 404.", {"Index provider": "Index rebalance dates may be missing"}, "6:40 PM IST")
    assert words == (" Index rebalance dates may be missing. Its site isn't answering properly, so the fault looks like the site's, "
                     "not StratLab's: nothing to do; it is tried again at 6:40 PM IST.")
    assert "reader needs a look" in admin_jobs.missing_words("Index provider: no table found", {"Index provider": "x"}, None)
    assert admin_jobs.missing_words("Somebody: down", {}, None) == ""
    at = datetime(2026, 10, 24, 21, 3, tzinfo=timezone.utc)                  # 02:33 IST Sunday
    assert admin_jobs.next_slot((("am", "Asia/Kolkata", "07:20"), ("pm", "Asia/Kolkata", "18:40")), at) == "7:20 AM IST"
    assert admin_jobs.next_slot((("pm", "Asia/Kolkata", "18:40"),), datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc)) == "6:40 PM IST tomorrow"


def test_the_results_and_corporate_actions_schedules_say_every_run(w):
    jobs = {j["id"]: j for j in w["client"].get("/admin/jobs", headers=A).json()["jobs"]}
    assert "every hour from 10:00 AM IST and 7:00 AM New York time" in jobs["results"]["schedule"]
    assert "Results-day notes 8:00 AM IST" in jobs["results"]["schedule"]
    assert "Evening-before notes 5:30 PM IST and 5:00 PM New York time" in jobs["corp"]["schedule"]
    assert "6:30 AM New York time" in jobs["corp"]["schedule"]                # the price histories


# ---------- DJ-031, DJ-036: AI statuses that agree; provider errors never cut mid-word ----------
def test_a_provider_error_is_cut_at_a_word():
    from app.ai_clients import clip
    text = "Rate limit reached for output tokens per minute (OTPM): Limit 8000, Used 7990, Requested 400. Please try again later and improve"
    got = clip(text, 60)
    assert got.endswith("…") and len(got) <= 60 and text.startswith(got[:-1]) and not text[len(got) - 1].isalnum()   # never mid-word
    assert clip("short", 60) == "short"


def test_a_provider_whose_last_result_failed_is_never_shown_as_working(monkeypatch):
    from app import ai_providers
    real = ai_providers._provider_view
    monkeypatch.setattr(ai_providers, "last_result", lambda *a, **k: "failed")
    monkeypatch.setattr(ai_providers, "configured", lambda name: True)
    v = real("groq", datetime.now(timezone.utc).timestamp())
    assert v["result"] == "failed" and v["state"] != "ok" and not v["answering"]
    assert "Working" not in v["state_text"]


# ---------- DJ-033: old data isn't passed as OK ----------
def test_a_feed_whose_newest_item_is_months_old_is_a_check():
    today = date(2026, 10, 25)
    old = platform_check._fresh("Insider trades", "12 Reliance insider-trading disclosures", date(2026, 2, 13), today)
    assert old["state"] == "warn" and "254 days old" in old["detail"]
    ok = platform_check._fresh("Exchange filings", "163 Reliance filings", date(2026, 10, 23), today)
    assert ok["state"] == "pass" and ok["detail"] == "163 Reliance filings; newest 23 Oct."
    assert platform_check._newest([{"at": "2026-10-01"}, {"at": "2026-10-20T10:00:00"}, {"at": "bad"}], "at") == date(2026, 10, 20)


# ---------- DJ-034: Brevo's sends today against its daily limit ----------
def test_brevo_says_how_many_were_sent_today_and_what_is_left(monkeypatch):
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")
    asked = []

    def get(url, headers=None, timeout=None, params=None):
        asked.append((url, params))
        body = ({"plan": [{"type": "free", "credits": 288, "creditsType": "sendLimit"}]} if url.endswith("/account")
                else {"requests": 12, "delivered": 12})
        return NS(json=lambda: body, raise_for_status=lambda: None)
    monkeypatch.setattr(alerts.httpx, "get", get)
    q = alerts.brevo_quota(fresh=True)
    assert q["sent_today"] == 12 and q["left_today"] == 288 and q["plan"] == "free" and q["error"] is None
    assert asked[1][1]["startDate"] == asked[1][1]["endDate"]                # today only
    monkeypatch.setattr(alerts.httpx, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert "Brevo didn't say" in alerts.brevo_quota(fresh=True)["error"]
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    assert alerts.brevo_quota(fresh=True) is None                            # another service: nothing read


# ---------- DJ-015: price labels say Fixed ----------
def test_every_price_outside_india_reads_as_fixed(monkeypatch):
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    pricing.forget()
    try:
        t = pricing.table()
        assert {r["price_set"] for c, r in t.items() if c != "INR"} == {"default"}
        pricing.save({"USD": {"basic": 9}})
        assert pricing.table()["USD"]["price_set"] == "owner" and pricing.table()["EUR"]["price_set"] == "default"
        assert "price_set" not in pricing.public()["currencies"]["USD"]               # Admin's word only
        assert pricing.FIXED_ON == "2026-10-24"
    finally:
        pricing.forget()


# ---------- DJ-016, DJ-017: Money reads Razorpay ----------
def test_money_reads_subscriptions_refunds_and_failed_payments_from_razorpay(w, monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_abc")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    fake = NS(subscription=NS(all=lambda q: {"items": [{"id": "sub_1", "status": "active", "plan_id": "plan_x", "notes": {"plan": "pro"},
                                                         "created_at": 1790000000, "current_end": 1792000000, "paid_count": 1}]}),
              refund=NS(all=lambda q: {"items": [{"id": "rfnd_1", "payment_id": "pay_1", "amount": 69900, "currency": "INR",
                                                   "status": "processed", "created_at": 1790500000}]}),
              payment=NS(all=lambda q: {"items": [{"id": "pay_2", "status": "failed", "amount": 199900, "currency": "INR",
                                                    "created_at": 1790600000, "error_description": "Card declined"},
                                                   {"id": "pay_3", "status": "captured", "amount": 69900, "currency": "INR"}]}))
    monkeypatch.setattr(billing, "client", lambda: fake)
    db.set_setting(billing.LAST_WEBHOOK, json.dumps({"at": "2026-10-24T20:00:00+00:00", "event": "subscription.charged"}))
    a = w["client"].get("/admin/billing/activity", headers=A).json()
    assert a["mode"] == "test" and a["last_webhook"]["event"] == "subscription.charged"
    assert a["subscriptions"][0]["plan"] == "pro" and a["refunds"][0]["amount"] == 699.0
    assert [f["id"] for f in a["failed"]] == ["pay_2"] and a["failed"][0]["why"] == "Card declined"
    assert isinstance(a["revenue_by_month"], list) and a["errors"] == {}
    monkeypatch.setattr(billing, "client", lambda: NS(subscription=NS(all=lambda q: 1 / 0), refund=fake.refund, payment=fake.payment))
    assert "subscriptions" in w["client"].get("/admin/billing/activity", headers=A).json()["errors"]
    assert w["client"].get("/admin/billing/activity", headers=headers("pro-token")).status_code == 403


# ---------- DJ-038, DJ-039: email previews ----------
def test_made_up_previews_are_marked_and_dated_as_they_would_go(w, monkeypatch):
    assert email_previews.describe("events")["sample"] is True
    monkeypatch.setattr(email_previews, "_stored_market", lambda region, weekly: {"weekly": True, "day": "2026-10-24", "kind": "market",
                                                                                     "region": "IN", "subject": "Market Brief India, week to 24 Oct: NIFTY 50 −2.36%",
                                                                                     "html": "<p>week to 24 Oct</p>", "text": "week to 24 Oct"})
    subject, html, text = email_previews._market("IN", True)
    assert subject == "Market Brief India, week to 23 Oct: NIFTY 50 −2.36%" and "week to 23 Oct" in text
    assert email_previews.describe("market_weekly")["sample"] is False                 # a real stored issue
    _, html, _ = email_previews._weekly_admin()
    monday = email_previews._today() + timedelta(days=(7 - email_previews._today().weekday()) % 7)
    assert f"Mon {monday.day} {monday:%b}" in html
