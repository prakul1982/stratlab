"""Money calendar: the tax dates the law sets, holdings' results and corporate actions, other Money pages' dates
through optional hooks, the user's own events and their repeats, the private ICS feed (its format, amounts left
out unless asked, revoking and the rate limit), reminders and their plan gate, and deleting it all."""
import sys
import types
from datetime import date, datetime, timedelta, timezone

import pytest

from app import corp_actions, db, holdings, money_calendar as M, results
from app.config import settings
from tests import world

PRO, FREE = world.headers("pro-token"), world.headers("free-token")


@pytest.fixture
def w(monkeypatch):
    M._hits.clear()
    built = world.build(monkeypatch)
    yield built
    built["close"]()
    M._hits.clear()


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


def days_of(evs, kind=None):
    return [e["date"] for e in evs if kind is None or e["kind"] == kind]


# ---------- tax dates ----------
def test_tax_dates_for_a_year_under_the_new_due_dates():
    evs = M.tax_dates(2025)                                          # FY 2025-26
    assert days_of(evs, "advance_tax") == ["2025-06-15", "2025-09-15", "2025-12-15", "2026-03-15"]
    assert [e["title"] for e in evs if e["kind"] == "advance_tax"][1] == "Advance tax, second instalment (45%)"
    assert days_of(evs, "tax_saving") == ["2026-03-31"] and "old regime" in evs[4]["title"]
    assert days_of(evs, "itr") == ["2026-07-31", "2026-08-31", "2026-10-31"]       # ITR-1/2, business without audit, audit
    assert days_of(evs, "itr_late") == ["2026-12-31"] and days_of(evs, "itr_revise") == ["2027-03-31"]


def test_tax_dates_before_the_finance_act_2026_changes():
    evs = M.tax_dates(2024)
    assert days_of(evs, "itr") == ["2025-07-31", "2025-10-31"]
    assert days_of(evs, "itr_late") == ["2025-12-31"] and "revised" in next(e for e in evs if e["kind"] == "itr_late")["title"]
    assert days_of(evs, "itr_revise") == []


def test_tax_dates_in_a_window_cover_every_year_it_touches():
    got = M.tax_between(date(2026, 6, 1), date(2027, 4, 30))
    assert "2026-06-15" in days_of(got) and "2027-03-15" in days_of(got)
    assert "2026-07-31" in days_of(got, "itr") and "2027-03-31" in days_of(got, "itr_revise")      # last year's return
    assert all("2026-06-01" <= d <= "2027-04-30" for d in days_of(got))


# ---------- the user's own events ----------
def test_repeats_fall_on_real_days():
    monthly = {"id": "a", "title": "EMI", "date": "2026-01-31", "repeat": "monthly"}
    assert [d.isoformat() for d in M.occurrences(monthly, date(2026, 2, 1), date(2026, 5, 31))] == \
        ["2026-02-28", "2026-03-31", "2026-04-30", "2026-05-31"]
    yearly = {"id": "b", "title": "Policy", "date": "2024-02-29", "repeat": "yearly"}
    assert [d.isoformat() for d in M.occurrences(yearly, date(2024, 1, 1), date(2028, 12, 31))] == \
        ["2024-02-29", "2025-02-28", "2026-02-28", "2027-02-28", "2028-02-29"]
    once = {"id": "c", "title": "FD", "date": "2026-11-05", "repeat": "none"}
    assert M.occurrences(once, date(2026, 11, 6), date(2026, 12, 1)) == []
    assert M.occurrences({**monthly, "date": "2027-01-01"}, date(2026, 1, 1), date(2026, 12, 31)) == []      # starts later


def test_add_edit_delete_own_events(w):
    c = w["client"]
    r = c.post("/money/calendar/events", headers=PRO, json={"date": "2026-11-05", "title": "FD matures", "note": "Bank FD",
                                                            "amount": 250000, "repeat": "none"})
    assert r.status_code == 200, r.text
    own = r.json()["own"]
    assert [e["title"] for e in own] == ["FD matures"]
    eid = own[0]["id"]
    got = c.get("/money/calendar?start=2026-11-01&end=2026-11-30&cats=custom", headers=PRO).json()
    assert [(e["date"], e["title"], e["amount"]) for e in got["events"]] == [("2026-11-05", "FD matures", 250000)]
    r = c.put(f"/money/calendar/events/{eid}", headers=PRO, json={"date": "2026-11-10", "title": "  FD   matures ", "repeat": "yearly"})
    assert r.status_code == 200 and r.json()["own"][0]["title"] == "FD matures" and r.json()["own"][0]["repeat"] == "yearly"
    assert c.get("/money/calendar", headers=FREE).json()["own"] == []                       # each user's own
    assert c.put(f"/money/calendar/events/{eid}", headers=FREE, json={"date": "2026-11-10", "title": "x"}).status_code == 404
    assert c.delete(f"/money/calendar/events/{eid}", headers=PRO).json() == {"deleted": True}
    assert c.get("/money/calendar", headers=PRO).json()["own"] == []
    assert c.post("/money/calendar/events", headers=PRO, json={"date": "2026-02-30", "title": "x"}).status_code == 400
    assert c.post("/money/calendar/events", headers=PRO, json={"date": "2026-02-03", "title": ""}).status_code == 422
    assert c.get("/money/calendar?start=2026-01-01&end=2028-01-01", headers=PRO).status_code == 400            # too long
    assert c.get("/money/calendar?start=2026-02-01&end=2026-01-01", headers=PRO).status_code == 400
    assert c.get("/money/calendar").status_code == 401


# ---------- holdings, watchlist and other Money pages ----------
def seed(today: date):
    holdings.save("u-pro", [{"symbol": "ITC", "exchange": "NSE", "name": "ITC", "qty": 100, "avg": 400},
                            {"symbol": "SGBMAY29I-GB", "exchange": "NSE", "name": "SGB", "qty": 10, "avg": 4800, "kind": "sgb"}], "CSV")
    db.set_setting("watchlist:u-pro", '{"items": [{"region": "IN", "symbol": "TCS"}]}')
    ex = today + timedelta(days=10)
    div = corp_actions.row("IN", "ITC", corp_actions.parse_purpose("Annual General Meeting/Final Dividend - Rs 7.50 Per Share")[0],
                           ex, record=ex + timedelta(days=1), purpose="Annual General Meeting/Final Dividend - Rs 7.50 Per Share")
    split = corp_actions.row("IN", "TCS", corp_actions.parse_purpose("Bonus 1:1")[0], today + timedelta(days=20))
    other = corp_actions.row("IN", "INFY", corp_actions.parse_purpose("Bonus 1:1")[0], today + timedelta(days=20))
    corp_actions.save("IN", [div, split, other])
    results.save("IN", [results.row("IN", "ITC", today + timedelta(days=5), "Financial results"),
                        results.row("IN", "WIPRO", today + timedelta(days=5), "Financial results")])
    return ex


def test_holdings_and_watchlist_dates(w):
    today = M._today()
    ex = seed(today)
    got = w["client"].get(f"/money/calendar?start={today}&end={today + timedelta(days=60)}&cats=holdings", headers=PRO).json()
    titles = {e["title"]: e for e in got["events"]}
    assert "ITC: results" in titles and not any("WIPRO" in t or "INFY" in t for t in titles)   # only what's held or watched
    exd = titles["ITC: ex-date, Final dividend ₹7.50 a share"]
    assert exd["date"] == ex.isoformat() and exd["amount"] == 750                             # 100 shares × ₹7.50
    assert "ITC: record date, Final dividend ₹7.50 a share" in titles and "ITC: AGM record date" in titles
    assert titles["TCS: ex-date, 1:1 bonus"]["amount"] is None and "watchlist" in titles["TCS: ex-date, 1:1 bonus"]["detail"]
    wide = w["client"].get("/money/calendar?start=2029-04-01&end=2029-06-30&cats=holdings", headers=PRO).json()
    assert [e["title"] for e in wide["events"]] == ["SGBMAY29I-GB: gold bond matures this month"]


def test_other_money_pages_through_hooks(w, monkeypatch):
    today = M._today()
    assert M._hook("money_nothing_here", "upcoming_dates", "u") == []                          # a page that isn't there
    fake = types.ModuleType("app.money_networth")
    fake.upcoming_dates = lambda uid, days: [
        {"date": (today + timedelta(days=3)).isoformat(), "title": "PPF matures", "amount": 512000.0, "kind": "maturity"},
        {"date": "not a date", "title": "bad"}, {"date": today.isoformat()}, "junk",
        {"date": (today + timedelta(days=4)).isoformat(), "title": "Premium", "amount": float("nan")}]
    broken = types.ModuleType("app.money_mf")
    broken.upcoming_dates = lambda uid, days: 1 / 0                                           # a page that fails
    tax = types.ModuleType("app.money_advance_tax")
    jun = date(today.year + (1 if today.month > 6 else 0), 6, 15)
    tax.upcoming_dates = lambda uid, days: [{"date": jun.isoformat(), "title": "Advance tax: ₹12,000 due", "amount": 12000, "kind": "advance_due"}]
    for name, mod in (("app.money_networth", fake), ("app.money_mf", broken), ("app.money_advance_tax", tax)):
        monkeypatch.setitem(sys.modules, name, mod)
    got = M.events("u-pro", today, today + timedelta(days=400))
    money = [(e["title"], e["amount"]) for e in got if e["cat"] == "money"]
    assert money == [("PPF matures", 512000.0), ("Premium", None)]
    on_jun = [e["title"] for e in got if e["date"] == jun.isoformat()]
    assert on_jun == ["Advance tax: ₹12,000 due"]                                             # the page's amount replaces the plain date


# ---------- the feed ----------
def test_ics_format_escaping_folding_and_amounts():
    evs = [M._ev(date(2026, 11, 5), "FD, matures; bank\\x", "custom", "custom", "Line one\nline two " + "long " * 40, amount=250000, ref="a"),
           M._ev(date(2026, 6, 15), "Advance tax, first instalment (15%)", "tax", "advance_tax")]
    ics = M.to_ics(evs, amounts=False, now=datetime(2026, 10, 4, tzinfo=timezone.utc))
    assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "\n" not in ics.replace("\r\n", "")
    lines = ics.split("\r\n")
    assert all(len(x.encode()) <= 75 for x in lines)
    unfolded = ics.replace("\r\n ", "")
    assert "SUMMARY:FD\\, matures\\; bank\\\\x" in unfolded and "DESCRIPTION:Line one\\nline two" in unfolded
    assert "DTSTART;VALUE=DATE:20261105" in unfolded and "DTEND;VALUE=DATE:20261106" in unfolded
    assert unfolded.count("BEGIN:VEVENT") == 2 and "DTSTAMP:20261004T000000Z" in unfolded
    assert "250" not in unfolded                                                              # no amounts unless asked
    assert "Amount: ₹2\\,50\\,000" in M.to_ics(evs, amounts=True).replace("\r\n ", "")
    again = M.to_ics(evs, amounts=False, now=datetime(2026, 10, 5, tzinfo=timezone.utc))
    uid = [x for x in lines if x.startswith("UID:")]
    assert uid == [x for x in again.split("\r\n") if x.startswith("UID:")]                    # stable, so apps update in place


def test_feed_link_amounts_and_revoke(w):
    c = w["client"]
    today = M._today()
    seed(today)
    c.post("/money/calendar/events", headers=PRO, json={"date": (today + timedelta(days=2)).isoformat(), "title": "Rent", "amount": 45000})
    assert c.get("/money/calendar", headers=PRO).json()["feed"] is None
    made = c.post("/money/calendar/feed", headers=PRO, json={"amounts": False}).json()
    path = made["path"]
    assert path.startswith("/money/calendar/feed/") and len(path.split("/")[-1]) > 40 and not made["amounts"]
    r = c.get(path)                                                                          # no sign-in: the token is the key
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    body = r.text.replace("\r\n ", "")
    assert "SUMMARY:Rent" in body and "SUMMARY:Advance tax" in body and "ITC: ex-date" in body
    assert "45,000" not in body and "Amount:" not in body
    assert c.put("/money/calendar/feed", headers=PRO, json={"amounts": True}).json()["path"] == path
    assert "Amount: ₹45\\,000" in c.get(path).text.replace("\r\n ", "")
    new = c.post("/money/calendar/feed", headers=PRO, json={"amounts": False}).json()["path"]      # a new link: the old one stops
    assert new != path and c.get(path).status_code == 404 and c.get(new).status_code == 200
    assert c.delete("/money/calendar/feed", headers=PRO).json() == {"deleted": True}
    assert c.get(new).status_code == 404 and c.get("/money/calendar", headers=PRO).json()["feed"] is None
    assert c.get("/money/calendar/feed/" + "a" * 43 + ".ics").status_code == 404                # a made-up token
    assert c.get("/money/calendar/feed/short.ics").status_code == 404
    assert c.put("/money/calendar/feed", headers=PRO, json={"amounts": True}).status_code == 404


def test_feed_is_rate_limited_per_link(w, monkeypatch):
    c = w["client"]
    monkeypatch.setattr(M, "FEED_RATE", (3, 3600))
    path = c.post("/money/calendar/feed", headers=PRO, json={}).json()["path"]
    assert [c.get(path).status_code for _ in range(4)] == [200, 200, 200, 429]


# ---------- reminders ----------
def test_reminders_are_basic_and_up(w, paid):
    c = w["client"]
    r = c.put("/money/calendar/reminders", headers=FREE, json={"on": True, "days": 3, "channel": "email", "cats": ["tax"]})
    assert r.status_code == 402 and "Basic" in r.json()["detail"]["message"]
    assert c.get("/money/calendar", headers=FREE).json()["reminders_allowed"] is False
    assert c.put("/money/calendar/reminders", headers=FREE, json={"on": False}).status_code == 200      # turning off is fine
    basic = c.put("/money/calendar/reminders", headers=world.headers("basic-token"),
                  json={"on": True, "days": 7, "channel": "push", "cats": ["tax", "holdings", "nope"]})
    assert basic.status_code == 200 and basic.json()["reminders"] == {"on": True, "days": 7, "channel": "push", "cats": ["tax", "holdings"]}
    assert c.put("/money/calendar/reminders", headers=PRO, json={"on": True, "days": 5}).status_code == 400


def test_reminders_go_out_once_a_day_for_the_chosen_categories(w, paid):
    sent = []
    send = lambda profile, channel, subject, text: sent.append((profile["id"], channel, subject, text)) or [channel]  # noqa: E731
    today = date(2026, 6, 12)                                                     # 3 days before the June instalment
    for uid, cats in (("u-basic", ["tax"]), ("u-free", ["tax"]), ("u-pro", ["custom"])):
        data = M.load(uid)
        data["reminders"] = M.clean_reminders({"on": True, "days": 3, "channel": "email", "cats": cats})
        M.save(uid, data)
    assert M.send_reminders(today, send) == 1                                     # free isn't on a plan with reminders; pro has no event that day
    uid, channel, subject, text = sent[0]
    assert (uid, channel) == ("u-basic", "email") and "Advance tax, first instalment" in text and "in 3 days" in text
    job = M.Job(send)
    at = datetime(2026, 6, 12, 3, 20, tzinfo=timezone.utc)                        # 08:50 India time
    assert job.tick(at - timedelta(hours=1)) == 0                                  # before 08:40
    assert job.tick(at) == 1 and job.tick(at + timedelta(minutes=5)) == 0          # once a day
    assert M.Job(send).tick(at + timedelta(minutes=10)) == 0                       # not again after a restart


def test_reminder_channels_are_only_the_ones_picked(monkeypatch):
    from app import alerts
    calls = []
    monkeypatch.setattr(alerts, "jobs_for", lambda p, s, t, url: [("push", lambda: calls.append("push")), ("telegram", lambda: calls.append("tg")),
                                                                  ("email", lambda: calls.append("email"))])
    assert M._send({"id": "u"}, "push", "s", "t") == ["push"] and calls == ["push"]
    assert M._send({"id": "u"}, "both", "s", "t") == ["push", "email"]


# ---------- privacy ----------
def test_delete_everything(w):
    c = w["client"]
    c.post("/money/calendar/events", headers=PRO, json={"date": "2026-11-05", "title": "FD"})
    path = c.post("/money/calendar/feed", headers=PRO, json={}).json()["path"]
    assert c.delete("/money/calendar", headers=PRO).json() == {"deleted": True}
    assert db.get_setting("moneycal:u-pro") is None and c.get(path).status_code == 404
    assert not [k for k, _ in db.all_settings_with_prefix(M.FEED_KEY)]
