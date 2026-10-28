"""FIX-1C: the live-site review LIVE-1C (Admin, emails, plan views, the owner's real data), the server's side. Each test names the
finding it keeps fixed."""
from datetime import datetime, timezone

import pytest

from app import main  # noqa: F401  (first: it loads the modules in the order they need)
from app import admin_jobs, alerts, ipo as I, market_events as M
from app.config import settings
from app.intel.net import SourceError
from tests.test_ipo import NOW, w  # noqa: F401  (the IPO tests' fake world and its clock)


# ---------- LIVE1C-001: a failed read once left a time where the next run looked for a dict ----------
def test_001_the_index_reader_is_not_stuck_on_a_time_a_failed_read_left_in_tried():
    class Web:
        def text(self, url):
            return ""
    from datetime import date
    # the state a failed run kept: "tried" a time, as a string ("'str' object has no attribute 'items'" on every run after)
    got = M.refresh_index(Web(), {"tried": "2026-10-27T07:20", "error": "x", "changes": []}, date(2026, 10, 28))
    assert got["changes"] == [] and got["tried"] == {}


def test_001_a_program_error_reaches_the_owner_as_words_and_the_log_keeps_the_text():
    plain = admin_jobs.plain_error("Index provider: 'str' object has no attribute 'items'")
    assert plain == "Index provider: the reader hit an unexpected page layout (the log has the details)."
    assert admin_jobs.plain_error("KeyError: 819") == "The reader hit an unexpected page layout (the log has the details)."
    assert admin_jobs.plain_error("Couldn't reach www.rbi.org.in. (ConnectError)") == "Couldn't reach www.rbi.org.in."
    row = admin_jobs._row("events", "Market events", "7:20 AM IST", "2026-10-28T01:00:00Z", "x", ["Index provider: 'str' object has no attribute 'items'"], parts=5)
    assert "'str' object" not in row["error"] and "unexpected page layout" in row["error"]
    assert "'str' object" in row["log"][0]                                   # the log keeps it


def test_001_refresh_says_a_reader_bug_in_words(monkeypatch):
    import json
    store = {}
    monkeypatch.setattr(M.db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(M.db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(M, "READERS", (("index", lambda web, old, today: (_ for _ in ()).throw(AttributeError("'str' object has no attribute 'items'"))),))
    out = M.refresh(web=object())
    assert out["problems"] == ["Index provider: The reader hit an unexpected page layout."]
    kept = json.loads(store[M.KEY])["index"]
    assert kept["error"] == "The reader hit an unexpected page layout." and kept["failed_at"] and "tried" not in kept


# ---------- LIVE1C-002: one company's filing page the SEC answered with a 500 is a Check, not a red feed ----------
def test_002_one_sec_filing_page_failing_leaves_the_ipo_feed_a_check(w, monkeypatch):  # noqa: F811
    seen = []

    def docs_for(name, today):
        seen.append(name)
        raise SourceError("The SEC", "The SEC is having trouble (500).", busy=True)
    monkeypatch.setattr(w["edgar"], "docs_for", docs_for)
    job = I.Job(sleep=lambda s: None)
    job.read("US", NOW)
    assert seen, "the fake world looks up at least one company's filings"
    assert job.status["last_error"] is None
    assert "company filing page" in job.status["check"] and "read again at the next run" in job.status["check"]
    row = admin_jobs._row("ipo", "IPOs", "x", NOW.isoformat(), job.status["last_error"], job.status["problems"], check=job.status["check"])
    assert row["state"] == "warn" and "SEC" in row["error"]


# ---------- LIVE1C-006: the emails sent today, from what the plan has left ----------
def test_006_a_free_plan_with_294_left_has_sent_6_when_the_days_report_is_not_read(monkeypatch):
    from types import SimpleNamespace as NS
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-test")

    def get(url, headers=None, timeout=None, params=None):
        if url.endswith("/account"):
            return NS(json=lambda: {"plan": [{"type": "free", "credits": 294, "creditsType": "sendLimit"}]}, raise_for_status=lambda: None)
        return NS(json=lambda: {}, raise_for_status=lambda: None)             # the day's report without a count
    monkeypatch.setattr(alerts.httpx, "get", get)
    q = alerts.brevo_quota(fresh=True)
    assert q["left_today"] == 294 and q["sent_today"] == 6
    alerts._brevo_quota.update(at=0.0, value=None)


# ---------- LIVE1C-014: the next run is a time ----------
def test_014_next_run_is_the_next_clock_time_the_schedule_names():
    now = datetime(2026, 10, 28, 20, 25, tzinfo=timezone.utc)                 # 01:55 IST on Thu 29 Oct
    sentence = ("Calendar: India 7:15 AM and 6:30 PM IST, US 6:00 AM New York time. Results-day notes 8:00 AM IST and 7:30 AM New York time. "
                "New filings looked for every hour from 10:00 AM IST and 7:00 AM New York time until midnight")
    assert admin_jobs.next_run_label(sentence, now) == "Thu 29 Oct, 7:15 AM IST"
    assert admin_jobs.next_run_label("7:20 AM and 6:40 PM IST", now) == "Thu 29 Oct, 7:20 AM IST"
    assert admin_jobs.next_run_label("Every quarter hour (09:15 to 15:30 IST) while the Indian market is open", now) is None
    assert admin_jobs.next_run_label("Off", now) is None
    # a New York time is told in India's
    assert admin_jobs.next_run_label("US 8:30 AM New York time", now) == "Thu 29 Oct, 6:00 PM IST"
    ipo_line = "India 7:40 AM and 8:10 PM IST; bids every 15 minutes from 9:55 AM to 5:30 PM IST while an issue is open; alerts 8:00 AM (India) IST"
    assert admin_jobs.next_run_label(ipo_line, now) == "Thu 29 Oct, 7:40 AM IST"


# ---------- LIVE1C-019: a P/E far off the profit is left out; a new listing's value counts the shares in issue now ----------
def test_019_an_indian_pe_far_from_market_cap_over_profit_is_not_shown():
    from app import stock_pages as sp
    f = {"region": "IN", "market_cap": 1000.0, "profit_ttm": 20.0, "pe": 50.0, "price": 10.0}          # cap / profit = 50
    assert sp.shown_pe(f) == 50.0 and not sp.pe_off_profit(f)
    assert sp.shown_pe({**f, "pe": 100.0}) == 100.0                          # 2 times apart: a minority holders' share can explain it
    assert sp.shown_pe({**f, "pe": 19.9}) is None and sp.pe_off_profit({**f, "pe": 19.9})       # 8.67 against 19.9 is the review's Quint Digital
    assert sp.shown_pe({**f, "pe": 627.0, "market_cap": 960.0, "profit_ttm": 20.0}) is None       # 48.0 against 627
    assert sp.shown_pe({**f, "region": "US", "pe": 19.9}) == 19.9                  # US pages have their own check (cap_problem)
    assert sp.shown_pe({**f, "profit_ttm": None, "pe": 19.9}) == 19.9              # no profit to compare with


def test_019_the_deep_view_and_the_audit_say_the_pe_was_left_out_not_that_it_is_wrong():
    from app import audit, stock_pages as sp
    from tests.test_deepdive import company
    p = company()                                                          # trailing profit 26
    snap = sp.india_snap_checked({"market_cap_cr": 520.0, "price": 100.0, "pe": 5.0}, p)           # 520 / 26 = 20
    assert snap["pe"] is None and snap["pe_off_profit"] == 5.0 and snap["market_cap_cr"] == 520.0
    issues = audit.check_numbers(p, {"notes": []}, snap)
    left = [i for i in issues if i["area"] == "Valuation"]
    assert left and left[0]["level"] == "fact" and left[0]["detail"].startswith("P/E left out: the source's 5.00 is far from 20.0")


def test_019_a_share_that_listed_after_its_balance_sheet_counts_the_shares_in_issue_now():
    from app import main as m
    p = {"ratios": {"Market Cap": "7,719"}, "balance": {"cols": ["Mar 2025", "Mar 2026"]}}
    snap = {"market_cap_cr": 7410.0, "price": 100.0}                       # the balance sheet's older share count: 4% low
    assert m.pre_issue_cap(snap, p, "2026-09-10")["market_cap_cr"] == 7719.0
    assert m.pre_issue_cap(snap, p, None) is snap                         # an older share keeps the balance sheet's count
    assert m.pre_issue_cap(snap, {**p, "balance": {"cols": ["Sep 2026"]}}, "2026-09-10") is snap       # a balance sheet after the listing has the issue in it


# ---------- the Admin routes (007, 008, 011, 014): a world with an owner ----------
@pytest.fixture
def world(monkeypatch):
    from tests import world as W
    main.forget_overview()
    wd = W.build(monkeypatch)
    yield wd
    main.forget_overview()
    wd["close"]()


def test_007_each_subscription_says_whose_it_is_and_what_it_charges(world, monkeypatch):
    from types import SimpleNamespace as NS
    from app import billing, db
    from tests.fake_db import headers
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_abc")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    db.sb().table("profiles").insert({"id": "u-t1", "email": "owner+sl-free@example.com", "plan": "free"}).execute()
    from app import admin
    monkeypatch.setattr(admin, "admin_emails", lambda: {"owner@example.com"})
    subs = [{"id": "sub_1", "status": "created", "plan_id": "p", "notes": {"user_id": "u-t1", "plan": "basic", "period": "month", "currency": "INR"},
             "created_at": 1790000000, "paid_count": 0},
            {"id": "sub_2", "status": "active", "plan_id": "p", "notes": {"user_id": "u-pro", "plan": "pro", "period": "year", "currency": "INR"},
             "created_at": 1790000000, "paid_count": 1}]
    fake = NS(subscription=NS(all=lambda q: {"items": subs}), refund=NS(all=lambda q: {"items": []}), payment=NS(all=lambda q: {"items": []}))
    monkeypatch.setattr(billing, "client", lambda: fake)
    a = world["client"].get("/admin/billing/activity", headers=headers("admin-token")).json()
    by = {s["id"]: s for s in a["subscriptions"]}
    assert by["sub_1"]["user"] == "Test account" and by["sub_1"]["amount"] and by["sub_1"]["currency"] == "INR" and by["sub_1"]["period"] == "month"
    assert by["sub_2"]["user"] == "pro@example.com" and by["sub_2"]["period"] == "year" and "user_id" not in by["sub_2"]


def test_008_live_keys_with_no_webhook_received_are_a_check_not_ok(world, monkeypatch):
    from app import billing, db
    import json
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_abc")
    assert billing.hook_status() == {"mode": "live", "last_at": None}
    db.set_setting(billing.LAST_WEBHOOK, json.dumps({"at": "2026-10-28T10:00:00+00:00", "event": "subscription.charged"}))
    assert billing.hook_status()["last_at"] == "2026-10-28T10:00:00+00:00"


def test_011_the_paper_sessions_list_leaves_out_the_test_accounts_unless_asked(world, monkeypatch):
    from app import admin, db
    from tests.fake_db import headers
    main.manager.sessions.clear()
    db.sb().table("profiles").insert({"id": "u-t1", "email": "owner+sl-free@example.com", "plan": "free"}).execute()
    monkeypatch.setattr(admin, "admin_emails", lambda: {"owner@example.com"})
    mk = lambda uid, name: db.create_session({"user_id": uid, "name": name, "status": "running", "instrument": {"symbol": "TCS", "market": "IN"}, "strategy": {"risk": {"capital": 1}}})  # noqa: E731
    mk("u-pro", "real one")
    mk("u-t1", "R test EMA cross")
    c, h = world["client"], headers("admin-token")
    assert [r["name"] for r in c.get("/admin/sessions", headers=h).json()] == ["real one"]
    assert sorted(r["name"] for r in c.get("/admin/sessions?test=1", headers=h).json()) == ["R test EMA cross", "real one"]


def test_014_every_job_row_carries_its_next_run_where_it_has_clock_times(world):
    from tests.fake_db import headers
    jobs = world["client"].get("/admin/jobs", headers=headers("admin-token")).json()["jobs"]
    assert all("next" in j for j in jobs)
    events = next(j for j in jobs if j["id"] == "events")
    assert events["next"] and events["next"].endswith("IST") and len(events["next"]) < 40


# ---------- LIVE1C-021: the feature check says what a price is ----------
def test_021_a_running_session_has_a_price_so_far_and_a_currency_pair_its_pips(monkeypatch):
    from datetime import date
    from app import platform_check as pc
    assert pc._px(1.10846) == "1.1085" and pc._px(4079.1) == "4,079.10" and pc._px(96.2) == "96.20"
    assert "currency futures contract" in pc.FUTURES["CDS"] and pc.FUTURES["CMDTY"] == "futures contract"

    class Prov:
        def ready(self):
            return True

        def defaults(self):
            return [{"symbol": "EURUSD", "token": "x"}]

        def history(self, inst, tf, n):
            return [{"t": f"2026-10-{d}T00:00:00+00:00", "o": 1.1, "h": 1.12, "l": 1.09, "c": 1.1084, "v": 1} for d in (26, 27, 28)]

    class Reg:
        def provider(self, m):
            return Prov()
    from datetime import datetime, timezone
    r = pc.check_market(Reg(), "FX", now=datetime(2026, 10, 28, 20, 30, tzinfo=timezone.utc))
    assert r["state"] == "pass" and "price so far" in r["detail"] and "1.1084" in r["detail"] and "close" not in r["detail"]


# ---------- LIVE1C-030, LIVE1C-031: the brief's headlines and its dates ----------
INDICES_28_OCT = [{"name": "NIFTY 50", "price": 22698.85, "change_pct": -0.22}, {"name": "SENSEX", "price": 73246.03, "change_pct": -0.48},
                  {"name": "NIFTY BANK", "price": 54267.40, "change_pct": 0.54}]


@pytest.mark.parametrize("title", [
    "Sensex recovers over 700 pts; Nifty above 24,700; what's keeping markets on edge?",       # the review's: 24,700 over a 22,699 close
    "Market fall explained: Sensex dives 995 points intraday, Nifty at 22,500",                # a fall of 995 points over a day of 350, and "intraday"
    "Nifty 50 rebounds as Sensex gains 400 pts",                                                 # Sensex closed lower
])
def test_030_a_headline_that_the_close_contradicts_is_not_carried(title):
    from app.newsletter import content as C
    assert not C.headline_ok("IN", title, indices=INDICES_28_OCT), title


def test_030_a_headline_that_agrees_with_the_close_stays():
    from app.newsletter import content as C
    for title in ("Sensex falls 356 points, Nifty 50 slips 65 points as banks hold up", "Nifty ends near 22,700 as banks gain; Sensex lower",
                  "Stock market today: Nifty at 22,650 after a choppy session"):
        assert C.headline_ok("IN", title, indices=INDICES_28_OCT), title


def test_031_s_and_p_global_is_a_ratings_company_not_the_us_market():
    from app.newsletter import content as C
    assert not C.headline_ok("US", "Moody's and S&P Global hold France's credit rating as markets wait")
    assert C.headline_ok("US", "S&P 500 ends the week higher as Treasury yields ease")


def test_031_a_weekly_brief_names_the_last_close_not_the_saturday():
    from app.newsletter import write
    issue = {"weekly": True, "day": "2026-10-24", "region": "US"}            # a Saturday: the week ran to Friday 23 Oct
    assert write.close_date_words("Stocks fell over the week ending 24 Oct, led by tech.", issue) == "Stocks fell over the week ending 23 Oct, led by tech."
    assert write.close_date_words("Over the week ending 24 Oct.", {**issue, "weekly": False}) == "Over the week ending 24 Oct."


# ---------- the sample emails (032 to 038) ----------
def test_032_the_stage_line_says_what_it_means_first_and_a_sample_has_no_real_as_of_time():
    from app import email_previews as P
    from app.newsletter import write
    lines = [x["text"] for x in write.stock_lines({"symbol": "ABC", "region": "IN", "price": 100.0, "change_pct": 1.0, "stage": 2, "stage_before": 1, "stage_changed": True}, "2026-10-01")]
    assert "The price is above a rising 150-day average: now Stage 2 (advancing), was Stage 1 (basing)" in lines
    assert not any(") (" in x for x in lines)
    _, html, text = P._my_stocks()
    assert "Prices and numbers as of" not in text and "Prices and numbers as of" not in html


def test_033_the_events_sample_names_a_tuesday_for_the_nifty_expiry():
    import re
    from app import email_previews as P
    _, _, text = P._events()
    assert "NIFTY weekly expiry" in text
    head = re.search(r"MARKET EVENTS (.+)", text).group(1)
    assert "TUE" in head                                                 # a Tuesday (and "tomorrow" or "in N days" as the day really is)


def test_034_the_paper_report_is_a_card_per_session_with_signed_amounts_in_colour():
    import re
    from app import email_previews as P
    subject, html, text = P._daily_report()
    flat = re.sub(r"[ \t]+", " ", text)
    assert "Trades closed today 2 (1 won)" in flat and "Since the start +₹12,400 (+2.5%)" in flat
    assert "NIFTY SUPERTREND" in flat and "BANKNIFTY BREAKOUT" in flat            # each session its own card, with its name over its rows
    assert "Daily report" in flat.splitlines()[0]
    assert 'class="c-up"' in html and 'class="c-down"' in html            # +₹1,840 green, −₹620 red


def test_035_the_admin_weekly_sample_has_round_made_up_figures():
    from app import email_previews as P
    _, _, text = P._weekly_admin()
    assert "100 in all" in text.replace("\n", " ") or "100" in text
    assert "10 in all" not in text and "42 experiments" not in text


def test_036_the_invite_email_is_short_cards_not_a_wall_of_text():
    from datetime import datetime, timezone
    from app import lifecycle
    _, html, text = lifecycle.build("invite_reward", {"id": "u", "email": "x@example.com"}, lifecycle.sample("invite_reward", datetime.now(timezone.utc)))
    assert "HOW IT WORKS" in text and "BASIC INCLUDES" in text and "Backtests" in text
    assert "How it works: a friend who joins" not in text
    longest = max(len(line.split()) for line in text.splitlines())
    assert longest < 40, longest


def test_037_the_launch_offer_ends_at_midnight_india_time_in_the_samples_and_when_started(monkeypatch):
    from datetime import datetime, timezone
    from app import lifecycle, plans
    now = datetime(2026, 10, 28, 20, 26, tzinfo=timezone.utc)                 # 01:56 IST
    for kind in ("promo_before", "promo_end"):
        end = lifecycle.sample(kind, now)["end"].astimezone(plans.IST)
        assert (end.hour, end.minute) == (0, 0), kind
    store = {}
    from app import db
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    until = plans.set_promo(2)
    ist = until.astimezone(plans.IST)
    assert (ist.hour, ist.minute, ist.second) == (0, 0, 0) and 2 <= (until - datetime.now(timezone.utc)).total_seconds() / 86400 < 3.01
    plans._promo.update(read_at=0.0, until=None)


def test_038_the_broker_login_alert_is_previewable_and_names_no_vendor():
    import re
    from app import email_previews as P
    assert "broker_login" in P.registry()
    d = P.describe("broker_login", True)
    assert "login needs you" in d["subject"] and not re.search(r"zerodha|kite", d["html"] + d["text"], re.I)
