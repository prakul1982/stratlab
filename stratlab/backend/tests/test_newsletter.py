"""The newsletters: facts from the fake world, the advice-word filter and template fallback, the email, the
once-a-day schedule, privacy of My Stocks issues, the API and plan gates."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app.ai_providers import AIBusy
import time_machine

from app import alerts, db, main, newsletter_prefs
from app.config import settings
from app.newsletter import content, job, write
from tests import world as W
from tests.fake_db import headers

THU = date(2026, 10, 1)                                        # a trading day in India and the US
AFTER_IN_CLOSE = datetime(2026, 10, 1, 11, 0, tzinfo=timezone.utc)   # 16:30 IST, 07:00 New York
SATURDAY = datetime(2026, 10, 3, 3, 0, tzinfo=timezone.utc)          # 08:30 IST


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    content._cache.clear()
    write._cache.clear()
    yield world
    world["close"]()


@pytest.fixture
def paid(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_x")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_BASIC", "plan_b")
    monkeypatch.setattr(settings, "RAZORPAY_PLAN_PRO", "plan_p")


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None: sent.append((to, subject, text, html)))
    return sent


def market(region="IN", weekly=False, day=THU):
    return {"kind": "market", "region": region, "day": day.isoformat(), "weekly": weekly, "since": "2026-09-30",
            "indices": [{"name": "NIFTY 50", "price": 24812.3, "change_pct": 0.42}],
            "rotation": [{"sector": "Nifty IT", "from": "improving", "to": "leading"}],
            "scan": {"group": "NIFTY 50 stocks", "st_s2": [{"symbol": "TCS", "price": 4100.0, "change_pct": 1.2}],
                     "stage2": [{"symbol": "INFY", "price": 1900.0, "change_pct": 0.4}]},
            "headlines": [{"headline": "Nifty ends higher as banks gain", "url": "https://example.com/a"},
                          {"headline": "Brokerage says buy this stock now", "url": "https://example.com/b"}]}


def reader(uid, email, plan="pro", confirmed=True, **choices):
    db.get_profile(uid, email)
    db.update_profile(uid, plan=plan, plan_status="active", alert_email=email)
    newsletter_prefs.set(uid, **choices)
    if confirmed:                                   # they clicked the link in the confirmation email
        db.set_setting(alerts.CONFIRMED + uid, email)


# ---------- facts ----------
def test_market_facts_from_the_world(w, monkeypatch):
    # the brief's day is India's date, not UTC's: the day the world's market headline (a couple of hours old) falls on. The
    # clock is pinned to a Wednesday after the close: the world's index levels are of the last session, which an issue
    # dated an earlier or later day no longer takes as its own (review 3m)
    with time_machine.travel(datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc), tick=False):
        day = (datetime.now(timezone.utc) - timedelta(hours=2)).astimezone(content.ZoneInfo("Asia/Kolkata")).date()
        f = content.market_facts("IN", day)
    assert f["kind"] == "market" and f["region"] == "IN"
    assert f["indices"] and all("change_pct" in i for i in f["indices"])
    assert f["headlines"] and len(f["headlines"]) <= content.HEADLINES and all(h["headline"] for h in f["headlines"])
    def down(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(main.research_hub, "headlines", down)      # a source that's down only drops its section
    content._cache.clear()
    assert "headlines" not in content.market_facts("IN", date.today())


def test_stock_facts_cover_watchlist_notebooks_and_cache_per_symbol(w, monkeypatch):
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}, {"symbol": "AAPL", "region": "US"}]}))
    monkeypatch.setattr(db, "list_notebook_rows", lambda uid: [{"instrument": {"symbol": "TCS", "market": "IN", "type": "EQ"}},
                                                               {"instrument": {"symbol": "NIFTY 50", "market": "IN", "type": "INDEX"}},
                                                               {"instrument": {"symbol": "BTC/USD", "market": "CRYPTO"}}])
    # R29B-012: only the watchlist and holdings, not notebook or paper instruments
    assert content.my_stocks("u-pro") == [("IN", "RELIANCE"), ("US", "AAPL")]
    f = content.stock_facts("u-pro", date.today())
    assert f["kind"] == "my_stocks" and set(f["unchanged"]) | {r["symbol"] for r in f["stocks"]} <= {"RELIANCE", "AAPL", "TCS"}
    calls = []
    real = main.filings_feed.announcements
    monkeypatch.setattr(main.filings_feed, "announcements", lambda *a, **k: calls.append(a) or real(*a, **k), raising=False)
    content._cache.clear()
    for _ in range(3):                                  # three readers holding the same stock: one lookup
        content.stock_row("IN", "RELIANCE", date.today(), False, "2026-01-01")
    assert len(calls) == 1


def test_a_stock_row_reports_new_red_filings_as_a_change(w):
    since = lambda days: (date.today() - timedelta(days=days)).isoformat()      # noqa: E731  (the QIP was 13 days ago)
    r = content.stock_row("IN", "RELIANCE", date.today(), False, since(30))
    assert r and r["changed"] and r["filings"][0]["label"] == "QIP (fund raise)" and r["filings"][0]["severity"] == "red"
    later = content.stock_row("IN", "RELIANCE", date.today(), False, since(3))
    assert later["filings"] == []


# ---------- writing ----------
def test_banned_words_and_unknown_tickers_drop_the_ai_text(monkeypatch):
    f = market()
    assert write.grounded("NIFTY 50 rose 0.42%. TCS newly matched the ST S2 rule.", f)
    for bad in ("Investors should buy TCS.", "TCS has a target price of 5000.", "Analysts recommend INFY.", "Expect a rally.",
                "Our top picks this week.", "HDFCBANK rose 2%.", "This multibagger looks hot."):
        assert not write.grounded(bad, f), bad
    monkeypatch.setattr(write, "complete", lambda *a, **k: json.dumps({"summary": "NIFTY 50 rose. You should buy TCS now."}))
    s = write.summary(f)
    assert not s["ai"] and s["text"] == write.template(f)
    write._cache.clear()
    monkeypatch.setattr(write, "complete", lambda *a, **k: json.dumps({"summary": "NIFTY 50 closed 0.42% higher; Nifty IT moved to Leading."}))
    assert write.summary(f) == {"text": "NIFTY 50 closed 0.42% higher; Nifty IT moved to Leading.", "ai": True}


def test_ai_failure_falls_back_to_the_template_and_is_asked_once_per_day(w):
    f = market()
    w["ai"].mode = "fail"
    assert write.summary(f) == {"text": write.template(f), "ai": False}
    assert w["ai"].calls == 1
    write.summary(f)
    assert w["ai"].calls == 1                           # shared by every reader: built once
    assert "NIFTY 50 +0.42%" in write.template(f) and "1 stock from the NIFTY 50 stocks newly matched" in write.template(f)


def test_my_stocks_never_calls_the_ai(w):
    f = {"kind": "my_stocks", "uid": "u-pro", "day": THU.isoformat(), "weekly": False, "since": "2026-09-30", "stocks": [], "paper": []}
    write.summary(f)
    assert w["ai"].calls == 0


def test_render_gives_html_and_text_with_the_footer():
    f = market()
    issue = {"id": "market.IN.2026-10-01", "subject": write.subject(f), "summary": "NIFTY 50 rose <a little>.", "sections": write.sections(f)}
    html, text = write.render(issue)
    assert html.startswith("<!doctype html>") and "&lt;a little&gt;" in html and "<img" not in html and "<link" not in html
    for out in (html, text):
        assert write.FOOTER in out and "{unsubscribe_url}" in out and "/news?tab=IN&issue=market.IN.2026-10-01" in out.replace("&amp;", "&")
        assert "TCS matches the Stage 2 rule" in out and "/research/IN/TCS" in out
        assert "Brokerage says buy" not in out             # a headline giving advice is left out
    assert issue["subject"].startswith("Market Brief India, Thu 1 Oct")


# ---------- the schedule ----------
def test_market_brief_goes_once_a_day_and_never_again_after_a_restart(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-pro", "pro@example.com", market_in="daily")
    reader("u-basic", "basic@example.com", plan="basic", market_in="weekly")
    reader("u-free", "free@example.com", plan="free", market_in="off")
    j = job.Job()
    assert j.tick(datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)) == 0          # 14:30 IST: before the close
    assert j.tick(AFTER_IN_CLOSE) == 1
    assert [(to, subj.split(",")[0]) for to, subj, *_ in outbox] == [("pro@example.com", "Market Brief India")]
    to, subj, text, html = outbox[0]
    assert "{unsubscribe_url}" not in text + html and "/unsubscribe?t=" in text and "/unsubscribe?t=" in html
    assert j.tick(AFTER_IN_CLOSE) == 0 and job.Job().tick(AFTER_IN_CLOSE) == 0     # same day, and after a restart
    assert len(outbox) == 1
    stored = job.load("market.IN.2026-10-01")
    assert stored["kind"] == "market" and stored["subject"] == subj and db.get_setting("news:market:IN:2026-10-01")
    assert job.ids("market", "IN") == ["market.IN.2026-10-01"]
    j.tick(SATURDAY)                                                                # the weekly digest: the weekly reader
    assert [to for to, *_ in outbox[1:]] == ["basic@example.com"]


def test_no_email_on_a_holiday(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-pro", "pro@example.com", market_in="daily")
    assert job.Job().tick(datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc)) == 0  # Gandhi Jayanti
    assert outbox == []


def test_my_stocks_sends_nothing_when_nothing_changed(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda *a, **k: {"kind": "market"})      # no market sources today
    reader("u-pro", "pro@example.com", my_stocks="daily")
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}]}))
    monkeypatch.setattr(content, "stock_row", lambda region, sym, day, weekly, since: {
        "symbol": sym, "region": region, "price": 100.0, "change_pct": 0.3, "stage": 2, "stage_before": 2, "stage_changed": False,
        "st_s2": False, "filings": [], "headlines": [], "changed": False})
    assert job.Job().tick(AFTER_IN_CLOSE) == 0
    assert outbox == [] and job.ids("my_stocks", "u-pro") == []


def test_my_stocks_issue_when_something_changed(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda *a, **k: {"kind": "market"})
    reader("u-pro", "pro@example.com", my_stocks="daily")
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}]}))
    qip = {"id": "9", "at": "2026-10-01T18:00", "category": "qip", "label": "QIP (fund raise)", "severity": "red",
           "subject": "Qualified Institutions Placement", "text": "", "url": "https://example.com/q.pdf"}
    monkeypatch.setattr(main.filings_feed, "announcements", lambda sym, days=365: [qip], raising=False)
    j = job.Job()
    j.mark("market-IN", date(2026, 10, 1))              # My stocks follows the India brief (R29B-020)
    assert j.tick(AFTER_IN_CLOSE) == 1
    issue = job.load(job.ids("my_stocks", "u-pro")[0])
    assert issue["uid"] == "u-pro" and "QIP" in issue["text"] and issue["subject"].startswith("My Stocks, Thu 1 Oct")


def test_the_email_carries_one_click_unsubscribe_headers(w, monkeypatch):
    got = []
    monkeypatch.setattr(alerts, "email_ready", lambda: True)
    monkeypatch.setattr(alerts, "send_email", lambda to, subject, text, html=None, headers=None: got.append(headers))
    reader("u-pro", "pro@example.com", market_in="daily")
    assert job.deliver(db.get_profile("u-pro"), job.make_issue(market(), "IN"), "market_in")
    assert "/unsubscribe?t=" in got[0]["List-Unsubscribe"] and got[0]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_plan_gates_in_the_job(w, monkeypatch, outbox, paid):
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    # a quiet week for RELIANCE (whatever the demo world's prices did since the issue's reference day), so My Stocks
    # has nothing to say and only the plan gates decide what goes out
    monkeypatch.setattr(content, "stock_row", lambda region, sym, day, weekly, since: {
        "symbol": sym, "region": region, "price": 100.0, "change_pct": 0.1, "stage": 2, "stage_before": 2, "stage_changed": False,
        "st_s2": False, "filings": [], "headlines": [], "changed": False})
    reader("u-free", "free@example.com", plan="free", market_in="daily", my_stocks="daily")
    db.set_setting("watchlist:u-free", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}]}))
    job.Job().tick(AFTER_IN_CLOSE)
    assert outbox == []                                   # no daily brief and no My Stocks on Free
    job.Job().tick(SATURDAY)
    assert [subj.split(",")[0] for _, subj, *_ in outbox] == ["Market Brief India"]   # the weekly digest instead


def test_my_stocks_weekly_is_free_and_daily_is_basic(w, monkeypatch, outbox, paid):
    """Weekly editions of both newsletters on every plan; daily ones on Basic and up. A Free reader still set to daily
    (their plan changed) gets the weekly edition, like the Market Brief."""
    monkeypatch.setattr(content, "market_facts", lambda *a, **k: {"kind": "market"})
    monkeypatch.setattr(content, "stock_row", lambda region, sym, day, weekly, since: {
        "symbol": sym, "region": region, "price": 100.0, "change_pct": 4.2, "stage": 2, "stage_before": 1, "stage_changed": True,
        "st_s2": False, "filings": [], "headlines": [], "changed": True})
    monkeypatch.setattr(job, "STOCKS_WAIT", timedelta(0))     # these tests are about plans, not the wait for the brief (R29B-020)
    assert job.allowed({"plan": "free"}, "my_stocks", "weekly") and not job.allowed({"plan": "free"}, "my_stocks", "daily")
    assert job.allowed({"plan": "basic", "plan_status": "active"}, "my_stocks", "daily")
    reader("u-free", "free@example.com", plan="free", my_stocks="daily")
    reader("u-basic", "basic@example.com", plan="basic", my_stocks="daily")
    for uid in ("u-free", "u-basic"):
        db.set_setting(f"watchlist:{uid}", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}]}))
    job.Job().tick(AFTER_IN_CLOSE)
    assert [to for to, *_ in outbox] == ["basic@example.com"]                      # daily: Basic only
    job.Job().tick(SATURDAY)
    assert [to for to, *_ in outbox[1:]] == ["free@example.com"]                   # weekly: the Free reader's digest


# ---------- the API ----------
def test_my_stocks_issues_are_private(w):
    c = w["client"]
    c.get("/me", headers=headers("pro-token"))
    job.save({"id": "my_stocks.u-pro.2026-10-01", "kind": "my_stocks", "uid": "u-pro", "region": None, "day": "2026-10-01",
              "weekly": False, "subject": "My Stocks", "summary": "1 of your stocks had something new today.", "sections": [],
              "html": "<p>x {unsubscribe_url}</p>", "text": "x", "at": "2026-10-01T16:20"})
    assert c.get("/news/my_stocks.u-pro.2026-10-01", headers=headers("free-token")).status_code == 404
    assert c.get("/news", params={"kind": "my_stocks"}, headers=headers("free-token")).json() == {"issues": []}
    mine = c.get("/news/my_stocks.u-pro.2026-10-01", headers=headers("pro-token")).json()
    assert set(mine) == {"id", "kind", "region", "day", "weekly", "subject", "summary", "sections", "html", "at"}
    assert "{unsubscribe_url}" not in mine["html"]
    listed = c.get("/news", params={"kind": "my_stocks"}, headers=headers("pro-token")).json()["issues"]
    assert listed == [{"id": "my_stocks.u-pro.2026-10-01", "kind": "my_stocks", "region": None, "day": "2026-10-01", "weekly": False,
                       "subject": "My Stocks", "preview": "1 of your stocks had something new today."}]
    for bad in ("nope", "market.IN.x", "../etc", "my_stocks.u-free.2026-10-01"):
        assert c.get(f"/news/{bad}", headers=headers("pro-token")).status_code == 404
    assert c.get("/news").status_code == 401


def test_market_issues_list_and_read(w, monkeypatch):
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    job.build_market("IN", THU)
    c = w["client"]
    issues = c.get("/news", params={"kind": "market", "region": "IN"}, headers=headers("free-token")).json()["issues"]
    assert [i["id"] for i in issues] == ["market.IN.2026-10-01"] and issues[0]["preview"]
    assert c.get("/news", params={"kind": "market", "region": "US"}, headers=headers("free-token")).json() == {"issues": []}
    assert c.get("/news", params={"kind": "other"}, headers=headers("free-token")).status_code == 400
    full = c.get("/news/market.IN.2026-10-01", headers=headers("free-token")).json()
    assert full["sections"][0]["title"] == "Indices" and write.FOOTER in full["html"]


def test_newsletter_choices(w):
    c = w["client"]
    me = c.get("/me/newsletters", headers=headers("pro-token")).json()
    assert me == {"market_in": "off", "market_us": "off", "my_stocks": "off", "email": "pro@example.com", "confirmed": False,
                  "allowed": {"market_daily": True, "my_stocks": True, "my_stocks_daily": True}}
    out = c.put("/me/newsletters", json={"market_in": "daily", "my_stocks": "weekly"}, headers=headers("pro-token")).json()
    assert (out["market_in"], out["market_us"], out["my_stocks"]) == ("daily", "off", "weekly")
    assert c.put("/me/newsletters", json={"market_in": "hourly"}, headers=headers("pro-token")).status_code == 422
    assert newsletter_prefs.get("u-pro") == {"market_in": "daily", "market_us": "off", "my_stocks": "weekly"}


def test_newsletter_plan_gates(w, paid):
    c = w["client"]
    free = c.get("/me/newsletters", headers=headers("free-token")).json()
    assert free["allowed"] == {"market_daily": False, "my_stocks": True, "my_stocks_daily": False}
    assert c.put("/me/newsletters", json={"market_in": "weekly"}, headers=headers("free-token")).json()["market_in"] == "weekly"
    r = c.put("/me/newsletters", json={"market_us": "daily"}, headers=headers("free-token"))
    assert r.status_code == 402 and "Basic plan" in r.json()["detail"]["message"]
    assert c.put("/me/newsletters", json={"my_stocks": "weekly"}, headers=headers("free-token")).json()["my_stocks"] == "weekly"
    r = c.put("/me/newsletters", json={"my_stocks": "daily"}, headers=headers("free-token"))
    assert r.status_code == 402 and "The daily My Stocks email is on the Basic plan" in r.json()["detail"]["message"]
    assert c.put("/me/newsletters", json={"my_stocks": "off"}, headers=headers("free-token")).status_code == 200
    basic = c.put("/me/newsletters", json={"market_in": "daily"}, headers=headers("basic-token"))
    assert basic.status_code == 200 and basic.json()["allowed"] == {"market_daily": True, "my_stocks": True, "my_stocks_daily": True}
    assert c.put("/me/newsletters", json={"my_stocks": "daily"}, headers=headers("basic-token")).json()["my_stocks"] == "daily"


def test_admin_builds_a_preview(w, monkeypatch):
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    c = w["client"]
    assert c.post("/admin/news/build", params={"kind": "market", "region": "IN"}, headers=headers("pro-token")).status_code == 403
    r = c.post("/admin/news/build", params={"kind": "market", "region": "IN"}, headers=headers("admin-token"))
    assert r.status_code == 200
    issue = r.json()
    assert issue["kind"] == "market" and issue["region"] == "IN" and write.FOOTER in issue["html"] and issue["text"]
    assert job.ids("market", "IN") == []                 # a preview isn't stored, so the real issue uses closing data


# ---------- the day's index change (real NIFTY 50 closes, Oct 2026) ----------
NIFTY = [("2026-09-25", 23140.50), ("2026-10-01", 22421.95), ("2026-10-05", 22555.75), ("2026-10-06", 22776.10), ("2026-10-07", 22603.05)]


def _candles(monkeypatch, closes=NIFTY):
    bars = [{"t": f"{d}T00:00:00+05:30", "o": c, "h": c, "l": c, "c": c, "v": 0} for d, c in closes]
    monkeypatch.setattr(main.research_hub.yahoo, "chart", lambda sym, tf="1d", days=365, ttl=None, exact=False:
                        {"meta": {}, "candles": bars if sym == "^NSEI" else []})


def test_the_brief_measures_the_day_from_the_session_before(w, monkeypatch):
    _candles(monkeypatch)
    moves = {i["name"]: i for i in content.index_moves("IN", date(2026, 10, 7), False)}
    assert moves["NIFTY 50"]["price"] == 22603.05 and moves["NIFTY 50"]["change_pct"] == -0.76     # not the -0.08% since 30 Sep
    assert content.index_moves("IN", date(2026, 10, 5), False)[0]["change_pct"] == 0.6         # from 1 Oct, over the 2 Oct holiday
    assert content.index_moves("IN", date(2026, 10, 3), True)[0]["change_pct"] == -3.11        # the week to Saturday 3 Oct


def test_stored_briefs_get_the_right_index_moves_and_keep_their_order(w, monkeypatch):
    def stored(day, pct):
        f = {**market(day=day), "indices": [{"name": "NIFTY 50", "price": dict(NIFTY)[day.isoformat()], "change_pct": pct, "from_high_pct": -7.1}]}
        job.save(job.make_issue(f, "IN"))
    monkeypatch.setattr(write, "ai_summary", lambda f: "The NIFTY 50 slipped 0.08% today.")
    for day, wrong in ((date(2026, 10, 5), -0.99), (date(2026, 10, 6), 0.26), (date(2026, 10, 7), -0.08)):
        stored(day, wrong)
    _candles(monkeypatch)
    monkeypatch.setattr(job, "date", type("D", (date,), {"today": classmethod(lambda cls: date(2026, 10, 8))}))
    assert job.repair_index_moves("IN") == 3
    assert job.ids("market", "IN") == ["market.IN.2026-10-07", "market.IN.2026-10-06", "market.IN.2026-10-05"]
    fixed = job.load("market.IN.2026-10-07")
    assert fixed["indices"][0]["change_pct"] == -0.76 and fixed["indices"][0]["from_high_pct"] == -7.1
    assert fixed["subject"].endswith("NIFTY 50 −0.76%") and fixed["title"] == "NIFTY 50 down 0.76%"
    assert not fixed["ai"] and "0.08" not in fixed["summary"] and "−0.76%" in fixed["summary"]
    assert [s["title"] for s in fixed["sections"]][:2] == ["Indices", "Sector rotation"] and "−0.76%" in fixed["html"]
    assert "0.08" not in fixed["html"] + fixed["text"]
    assert job.repair_index_moves("IN") == 0                                                  # already right: nothing to do


def test_briefs_stored_before_the_indices_field_are_rebuilt_too(w, monkeypatch):
    # an issue as stored before 6 Oct 2026: the indices only as text in the Indices section, an AI summary
    old = {"id": "market.IN.2026-10-05", "kind": "market", "region": "IN", "day": "2026-10-05", "weekly": False,
           "subject": "Market Brief India, Mon 05 Oct: NIFTY 50 -0.99%", "summary": "The NIFTY 50 slipped 0.99%.", "ai": True,
           "sections": [{"title": "Indices", "items": [{"text": "NIFTY 50: 22,555.75, -0.99% on the day", "url": None, "lines": []}]},
                        {"title": "Headlines", "items": [{"text": "Markets end higher", "url": None, "lines": []}]}],
           "at": "2026-10-05T16:15+05:30"}
    old["html"], old["text"] = write.render(old)
    job.save(old)
    _candles(monkeypatch)
    monkeypatch.setattr(job, "date", type("D", (date,), {"today": classmethod(lambda cls: date(2026, 10, 8))}))
    assert job.repair_index_moves("IN") == 1
    fixed = job.load("market.IN.2026-10-05")
    assert fixed["indices"] == [{"name": "NIFTY 50", "price": 22555.75, "change_pct": 0.6}]   # from 1 Oct, over the 2 Oct holiday
    assert fixed["subject"].endswith("NIFTY 50 +0.60%") and not fixed["ai"] and "0.99" not in fixed["html"] + fixed["text"]
    assert [s["title"] for s in fixed["sections"]] == ["Indices", "Headlines"]


def test_the_weekly_brief_is_tried_again_for_a_region_whose_sources_were_down(w, monkeypatch, outbox):
    up = {"on": False}
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day) if up["on"] else {"kind": "market"})
    reader("u-basic", "basic@example.com", plan="basic", market_in="weekly")
    j = job.Job()
    j.tick(SATURDAY)                                                                # every source down at 08:30 IST
    assert outbox == []
    up["on"] = True
    j.tick(SATURDAY + timedelta(minutes=10))
    assert [to for to, *_ in outbox] == ["basic@example.com"]
    j.tick(SATURDAY + timedelta(minutes=20))
    assert len(outbox) == 1


# ---------- a deploy killing a run ----------
def test_a_my_stocks_run_killed_mid_way_resumes_with_the_readers_left(w, monkeypatch):
    import time
    from types import SimpleNamespace
    from app import run_marks
    clock = [time.time()]
    monkeypatch.setattr(run_marks, "time", SimpleNamespace(time=lambda: clock[0]))
    monkeypatch.setattr(job, "STOCKS_WAIT", timedelta(0))
    monkeypatch.setattr(content, "market_facts", lambda *a, **k: {"kind": "market"})
    qip = {"id": "9", "at": "2026-10-01T18:00", "category": "qip", "label": "QIP (fund raise)", "severity": "red",
           "subject": "Qualified Institutions Placement", "text": "", "url": "https://example.com/q.pdf"}
    monkeypatch.setattr(main.filings_feed, "announcements", lambda sym, days=365: [qip], raising=False)
    for u in ("u1", "u2", "u3"):
        reader(u, f"{u}@example.com", my_stocks="daily")
        db.set_setting(f"watchlist:{u}", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}]}))
    got, kill = [], [True]
    monkeypatch.setattr(alerts, "email_ready", lambda: True)

    def send_email(to, subject, text, html=None, headers=None):
        if len(got) == 1 and kill[0]:
            kill[0] = False
            raise KeyboardInterrupt                      # the deploy's SIGTERM, in the second reader's send
        got.append(to)
    monkeypatch.setattr(alerts, "send_email", send_email)
    with pytest.raises(KeyboardInterrupt):
        job.Job().tick(AFTER_IN_CLOSE)
    assert len(got) == 1
    assert job.Job().tick(AFTER_IN_CLOSE) == 0 and len(got) == 1          # the dead run still looks alive: left alone
    clock[0] += run_marks.STALE + 1
    assert job.Job().tick(AFTER_IN_CLOSE) == 2                            # the one cut off (not recorded until sent) and the one never reached
    assert len(got) == 3 and len(set(got)) == 3                           # none twice among those that were recorded
    clock[0] += run_marks.STALE + 1
    assert job.Job().tick(AFTER_IN_CLOSE) == 0 and len(got) == 3          # done: skipped


def test_the_market_issue_is_not_resent_while_its_send_is_still_going(w, monkeypatch, outbox):
    import time
    reader("u-pro", "pro@example.com", market_in="daily")
    issue = job.save(job.make_issue(market(), "IN"))
    led = {"sent": [], "skipped": {}, "done": False}
    j = job.Job()
    j.last["market-IN"] = "2026-10-01"                                    # the marker the first container wrote
    for beat, want in ((time.time() - 30, 0), (time.time() - 2 * job.run_marks.STALE, 1)):
        db.set_setting(job.SENT + issue["id"], json.dumps({**led, "beat": beat}))
        j._open.clear()
        assert j.catch_up(AFTER_IN_CLOSE, []) == want                    # a live heartbeat: the other container is on it
    assert job.ledger(issue["id"])["done"] and len(outbox) == 1


def test_a_weekly_briefs_close_is_the_last_trading_day_not_its_saturday():
    sat = {"kind": "market", "region": "IN", "day": "2026-10-17", "weekly": True}
    assert write.close_stamp(sat) == "the 15:30 IST close of 16 Oct 2026"
    assert write.close_stamp({**sat, "region": "US"}) == "the 16:00 ET close of 16 Oct 2026"
    assert write.close_stamp({**sat, "weekly": False, "day": "2026-10-16"}) == "the 15:30 IST close of 16 Oct 2026"


def test_a_change_that_rounds_to_zero_carries_no_sign():
    from app import email_kit as kit
    assert kit.pct(0.004) == "0.00%" and kit.pct(-0.004) == "0.00%" and kit.pct(-0.04, 1) == "0.0%"
    assert kit.pct(0.6) == "+0.60%" and kit.pct(-1.25) == "−1.25%"
    assert kit.money(-0.4, "USD", 0, True) == "$0" and kit.money(-35, "USD", 0, True) == "−$35"


def test_my_stocks_run_records_a_reader_only_after_the_email_went(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda *a, **k: {"kind": "market"})
    reader("u-pro", "pro@example.com", my_stocks="daily")
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}]}))
    qip = {"id": "9", "at": "2026-10-01T18:00", "category": "qip", "label": "QIP (fund raise)", "severity": "red",
           "subject": "Qualified Institutions Placement", "text": "", "url": "https://example.com/q.pdf"}
    monkeypatch.setattr(main.filings_feed, "announcements", lambda sym, days=365: [qip], raising=False)

    class Run:
        sent = []
        seen = lambda self, uid: False  # noqa: E731
        beat = lambda self: None  # noqa: E731
        record = lambda self, uid: self.sent.append(uid)  # noqa: E731
    run = Run()
    monkeypatch.setattr(job, "deliver_why", lambda *a, **k: "error")
    assert job.Job().run_stocks(date(2026, 10, 1), False, run) == 0 and run.sent == ["u-pro"]    # handled: its teaser went
    run.sent.clear()
    monkeypatch.setattr(job, "deliver_why", lambda *a, **k: "sent")
    assert job.Job().run_stocks(date(2026, 10, 1), False, run) == 1 and run.sent == ["u-pro"]


def test_my_stocks_resume_doesnt_send_the_teaser_again_to_a_reader_not_emailed(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda *a, **k: {"kind": "market"})
    reader("u-pro", "pro@example.com", my_stocks="daily")
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}]}))
    qip = {"id": "9", "at": "2026-10-01T18:00", "category": "qip", "label": "QIP (fund raise)", "severity": "red",
           "subject": "Qualified Institutions Placement", "text": "", "url": "https://example.com/q.pdf"}
    monkeypatch.setattr(main.filings_feed, "announcements", lambda sym, days=365: [qip], raising=False)
    done, asked = set(), []

    class Run:
        seen = lambda self, uid: uid in done  # noqa: E731
        beat = lambda self: None  # noqa: E731
        record = lambda self, uid: done.add(uid)  # noqa: E731
    monkeypatch.setattr(job, "deliver_why", lambda *a, **k: asked.append(1) or "unconfirmed")
    job.Job().run_stocks(date(2026, 10, 1), False, Run())
    job.Job().run_stocks(date(2026, 10, 1), False, Run())              # the resumed run
    assert asked == [1]


def test_my_stocks_issues_off_the_index_are_deleted_with_their_ledger(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    monkeypatch.setattr(db, "delete_setting", lambda k: store.pop(k, None))
    d0 = date(2026, 1, 1)
    first = job.issue_id("my_stocks", "u1", d0.isoformat(), False)
    for i in range(120):
        iid = job.issue_id("my_stocks", "u1", (d0 + timedelta(days=i)).isoformat(), False)
        job.save({"id": iid, "html": "x", "text": "y"})
        store[job.SENT + iid] = json.dumps({"done": True})            # the ledger of who it was sent to
    rows = [k for k in store if k.startswith("news:my_stocks:u1:")]
    assert len(rows) == job.INDEX_CAP                                  # 60 remain, not 120
    assert len(json.loads(store["news-index:my_stocks:u1"])) == job.INDEX_CAP
    assert job.load(first) is None and job.SENT + first not in store
    newest = job.issue_id("my_stocks", "u1", (d0 + timedelta(days=119)).isoformat(), False)
    assert job.load(newest) and job.SENT + newest in store
    assert [i["id"] for i in job.recent("my_stocks", "u1", 5)][0] == newest
    # re-saving an issue already on the index drops nothing; another reader's and the Market Briefs' are untouched
    job.save({"id": job.issue_id("my_stocks", "u2", "2026-01-01", False), "html": "x", "text": "y"})
    job.save({"id": newest, "html": "again", "text": "y"})
    assert len([k for k in store if k.startswith("news:my_stocks:u1:")]) == job.INDEX_CAP
    assert any(k.startswith("news:my_stocks:u2:") for k in store)
    for i in range(70):
        job.save({"id": job.issue_id("market", "IN", (d0 + timedelta(days=i)).isoformat(), False), "html": "x", "text": "y"})
    assert len([k for k in store if k.startswith("news:market:IN:")]) == 70     # briefs are not pruned here


# ---------- review 3m: what the emails say about the day, week and level they measure from ----------
def _bars(last_day: str, n=40, last_close=140.0, skip=(), tz="-04:00"):
    """n weekday candles ending on `last_day` (days in `skip` had no session), the last one closing at `last_close`."""
    end, days, d = date.fromisoformat(last_day), [], date.fromisoformat(last_day)
    while len(days) < n:
        if d.weekday() < 5 and d.isoformat() not in skip:
            days.append(d)
        d -= timedelta(days=1)
    days.reverse()
    return [{"t": f"{d.isoformat()}T00:00:00{tz}", "o": 100.0, "h": 101.0, "l": 99.0, "c": last_close if d == end else 100.0, "v": 1000.0}
            for d in days]


def _row(monkeypatch, region, sym, day, weekly, bars):
    content._cache.clear()
    monkeypatch.setattr(content, "_symbol_data", lambda r, s, d: {"bars": bars, "filings": [], "news": []})
    monkeypatch.setattr(content.official_close, "with_reference", lambda b, s, ref: b)
    monkeypatch.setattr(content.deals, "recent_for", lambda *a: [])
    monkeypatch.setattr(content, "surveillance_lines", lambda *a: None)
    return content.stock_row(region, sym, day, weekly, "2026-01-01")


def _since_labels(row, issue_since):
    """What the email says a stock changed since: the section row's label and the price line."""
    f = {"stocks": [row], "since": issue_since}
    item = write.stock_sections(f)[0]["items"][0]
    return item["since"], write.stock_lines(row, issue_since)[0]["text"]


def test_a_us_stocks_since_day_is_the_session_its_change_is_measured_from(monkeypatch):
    """The Wed 14 Oct India-dated issue is measured from the day before (Tue 13 Oct), but a US stock's last bar is the 13 Oct
    session, so its change is from Mon 12 Oct: the email said Tue 13 Oct."""
    row = _row(monkeypatch, "US", "AAPL", date(2026, 10, 14), False, _bars("2026-10-13"))
    assert row["since_day"] == "2026-10-12" and row["change_pct"] == 40.0
    issue_since = content.reference_day("US", date(2026, 10, 14), False).isoformat()
    assert issue_since == "2026-10-13"
    label, line = _since_labels(row, issue_since)
    assert label == "since Mon 12 Oct" and line.endswith("since Mon 12 Oct")


def test_a_weekly_stocks_since_day_is_the_last_session_on_or_before_the_week_back(monkeypatch):
    """A week back from Fri 9 Oct is the 2 Oct holiday: the change is from the Thu 1 Oct close, not "Fri 2 Oct"."""
    row = _row(monkeypatch, "IN", "TCS", date(2026, 10, 9), True, _bars("2026-10-09", skip=("2026-10-02",), tz="+05:30"))
    issue_since = content.reference_day("IN", date(2026, 10, 9), True).isoformat()
    assert issue_since == "2026-10-02" and row["since_day"] == "2026-10-01"
    label, line = _since_labels(row, issue_since)
    assert label == "since Thu 1 Oct" and line.endswith("since Thu 1 Oct")


def test_a_row_without_a_since_day_keeps_the_issues():
    row = {"symbol": "TCS", "region": "IN", "price": 100.0, "change_pct": 1.0, "stage": 2, "stage_before": 2, "stage_changed": False}
    assert _since_labels(row, "2026-10-13")[0] == "since Tue 13 Oct"


def test_a_live_index_quote_is_used_only_if_it_is_todays_and_fresh(monkeypatch):
    from types import SimpleNamespace
    day = date(2026, 10, 14)
    quote = {"name": "NIFTY 50", "price": 25000.0, "change_pct": 0.5, "from_high_pct": -1.0}
    monkeypatch.setattr(content, "index_close", lambda sym, d, since=None: None)       # the day's candle isn't out yet

    def moves(**fields):
        monkeypatch.setattr(content, "_main", lambda: SimpleNamespace(research_hub=SimpleNamespace(indices=lambda region: [{**quote, **fields}])))
        return [m["name"] for m in content.index_moves("IN", day, False)]
    assert moves(day="2026-10-14", stale=False) == ["NIFTY 50"]
    assert moves(day="2026-10-13", stale=False) == []                  # the previous session's level, not today's
    assert moves(day="2026-10-14", stale=True) == []
    assert moves() == []                                                # no day on it: not known to be today's


def test_the_52_week_line_says_below_only_for_an_index_below_its_high():
    def sub(from_high):
        return write._tiles([{"name": "NIFTY 50", "price": 25000.0, "change_pct": 0.5, "from_high_pct": from_high}], False)[0].sub
    assert sub(-1.8) == "1.8% below its 52-week high"
    assert sub(1.8) is None and sub(0.0) is None and sub(None) is None  # a positive figure used to read "1.8% below"


def test_a_confirm_link_for_a_deleted_account_makes_no_new_profile(w):
    """acct4: the link reads the profile without creating one (db.get_profile would make a fresh row)."""
    from app import mail_tokens
    c = w["client"]
    t = mail_tokens.make("u-deleted", "confirm", "gone@example.com")
    assert c.get("/email/confirm", params={"t": t}).status_code == 400
    assert c.post("/email/confirm", params={"t": t}).status_code == 400
    assert not db.sb().table("profiles").select("id").eq("id", "u-deleted").execute().data
    assert db.get_setting(alerts.CONFIRMED + "u-deleted") is None


# ---------- R23-002: an India brief built but not mailed, and Admin saying nothing of it ----------
AFTER_US_CLOSE = datetime(2026, 10, 1, 20, 55, tzinfo=timezone.utc)   # 16:55 New York, the closes settled


def test_r23_002_a_failure_starting_the_send_leaves_the_day_open_and_the_brief_goes_at_the_next_check(w, monkeypatch, outbox):
    """The day used to be marked as run before the issue's ledger was written: a database error (or a deploy) in between
    left the India issue built and marked with no ledger, which reads as "sent before ledgers existed", so it was never
    mailed and Admin had no India line at all."""
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-pro", "pro@example.com", market_in="daily")
    real, failed = db.set_setting, []

    def flaky(key, value):
        if key.startswith(job.SENT) and not failed:
            failed.append(key)
            raise RuntimeError("Server disconnected")
        return real(key, value)
    monkeypatch.setattr(db, "set_setting", flaky)
    j = job.Job("newsletters")
    assert j.tick(AFTER_IN_CLOSE) == 0 and outbox == [] and failed
    assert job.load("market.IN.2026-10-01")                                   # built and stored, as on 14 Oct
    assert "couldn't start the send" in j.status["regions"]["IN"]["error"]    # and said in Admin
    assert j.tick(AFTER_IN_CLOSE + timedelta(minutes=5)) == 1
    assert [to for to, *_ in outbox] == ["pro@example.com"]
    assert j.tick(AFTER_IN_CLOSE + timedelta(minutes=10)) == 0 and len(outbox) == 1


def test_r23_002_admin_keeps_indias_run_after_a_restart_before_the_us_run(w, monkeypatch, outbox):
    from app import admin_jobs
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-pro", "pro@example.com", market_in="daily", market_us="daily")
    assert job.Job("newsletters").tick(AFTER_IN_CLOSE) == 1
    restarted = job.Job("newsletters")                                        # a deploy between the two sends
    assert restarted.tick(AFTER_US_CLOSE) == 1
    regions = restarted.status["regions"]
    assert (regions["IN"]["day"], regions["IN"]["sent"], regions["US"]["sent"]) == ("2026-10-01", 1, 1)
    monkeypatch.setattr(main, "newsletter_job", restarted)
    log = next(r for r in admin_jobs.rows() if r["id"] == "newsletters")["log"]
    india = [x for x in log if x.startswith("India, 2026-10-01: sent to 1 of 1 reader; skipped 0")]
    us = [x for x in log if x.startswith("US, 2026-10-01: sent to 1 of 1 reader; skipped 0")]
    assert india and us and "(run " in india[0] and india[0].endswith(" UTC)"), log      # each market's own last run


def test_r23_002_a_daily_reader_whose_plan_has_weekly_only_is_said_as_such(w, monkeypatch, outbox, paid):
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-free", "free@example.com", plan="free", market_in="daily")
    j = job.Job("newsletters")
    j.tick(AFTER_IN_CLOSE)
    rep = j.status["regions"]["IN"]
    assert outbox == [] and rep["other_edition"] == 0
    assert rep["skipped"] == {"chose daily, but their plan has the weekly edition only": 1}


def test_r23_002_admin_says_when_a_due_brief_has_no_run(monkeypatch):
    from app import admin_jobs
    at = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)                   # 17:30 IST on a trading day
    assert job.due_today("IN", at) == "2026-10-14" and job.due_today("US", at) is None
    monkeypatch.setattr(job, "due_today", lambda region, now=None: "2026-10-14" if region == "IN" else None)
    st = {"last_run": "2026-10-13T20:55:00+00:00", "sent": 1, "last_error": None, "regions": {
        "US": {"issue": "market.US.2026-10-13", "day": "2026-10-13", "readers": 1, "sent": 1, "other_edition": 0, "skipped": {},
               "at": "2026-10-13T20:55:00+00:00"}}}
    monkeypatch.setattr(main.newsletter_job, "status", st)
    log = next(r for r in admin_jobs.rows() if r["id"] == "newsletters")["log"]
    assert "India, 2026-10-14: no run recorded yet (due at 16:15 IST)" in log, log


# ---------- R23-004: a sent brief's links keep working after a headline rule shrinks its list ----------
def test_r23_004_a_sent_briefs_link_numbers_survive_a_later_headline_filter(w, monkeypatch, outbox):
    heads = [{"headline": f"Wall Street story {i}", "url": f"https://www.reuters.com/markets/us/{'a' * 200}/{i}"} for i in range(3)]   # long: the short address stands in
    facts = lambda region, day, weekly=False: {**market(region, weekly, day), "headlines": heads}   # noqa: E731
    monkeypatch.setattr(content, "market_facts", facts)
    reader("u-pro", "pro@example.com", market_us="daily")
    assert job.Job().tick(AFTER_US_CLOSE) == 1
    iid = "market.US.2026-10-01"
    assert f"/news-link/{iid}/2" in outbox[0][2]
    issue = job.load(iid)                                                     # a later rule drops the first story, in place
    for s in issue["sections"]:
        if s["title"] == "Headlines":
            s["items"] = s["items"][1:]
    db.set_setting(f"news:market:US:2026-10-01", json.dumps(issue))
    c = w["client"]
    r = c.get(f"/news-link/{iid}/2", follow_redirects=False)
    assert r.headers["cache-control"] == "public, max-age=60"
    assert r.status_code == 302 and r.headers["location"] == heads[2]["url"]  # the story the email named, not a 404
    gone = c.get(f"/news-link/{iid}/9", follow_redirects=False)
    assert gone.status_code == 302 and gone.headers["location"].endswith(f"/news?tab=US&issue={iid}")
    html = c.get(f"/news/{iid}", headers=headers("pro-token")).json()["html"]
    assert f"/news-link/{iid}/2" in html and f"/news-link/{iid}/0" not in html   # the page numbers its links as the email did


# ---------- R23-006: My Stocks prices carry their currency ----------
def test_r23_006_my_stocks_prices_have_their_currency_sign():
    f = {"kind": "my_stocks", "uid": "u", "day": "2026-10-15", "weekly": False, "since": "2026-10-14",
         "stocks": [{"symbol": "TATAMOTORS", "region": "IN", "price": 925.4, "change_pct": 3.4},
                    {"symbol": "AAPL", "region": "US", "price": 341.27, "change_pct": -0.5}]}
    html, text = write.render({"id": "my_stocks.u.2026-10-15", "kind": "my_stocks", "subject": "My Stocks", "summary": "x",
                               "sections": write.sections(f)})
    assert "TATAMOTORS  ₹925.40 ▲ 3.40%" in text and "AAPL  $341.27 ▼ 0.50%" in text
    assert "₹925.40" in html and "$341.27" in html


# ---------- R23-007: the AI's paragraph prints the index numbers as the tiles do ----------
def test_r23_007_the_india_summary_numbers_match_the_tiles():
    indices = [{"name": "NIFTY 50", "price": 22622.7, "change_pct": -0.44}, {"name": "SENSEX", "price": 72781.89, "change_pct": -0.34},
               {"name": "NIFTY BANK", "price": 55316.0, "change_pct": -0.3}]
    ai = ("India's major indices fell on October 14, with the NIFTY 50 at 22,622.7 (-0.44%), the SENSEX at 72,781.89 (-0.34%) "
          "and NIFTY BANK at 55,316.0 (-0.30%). Nifty slipped below 22,650.")
    issue = {"id": "market.IN.2026-10-14", "kind": "market", "region": "IN", "day": "2026-10-14", "weekly": False,
             "subject": "s", "summary": "NIFTY 50 −0.44% today.", "ai_summary": ai, "indices": indices, "sections": []}
    html, text = write.render(issue)
    assert "NIFTY 50 at 22,622.70 (−0.44%)" in text and "SENSEX at 72,781.89 (−0.34%)" in text
    assert "NIFTY BANK at 55,316.00 (−0.30%)" in text and "below 22,650." in text and "October 14" in text
    assert "22,622.7 " not in text and "(-0" not in text
    assert "22,622.70 ▼ 0.44%" in text                                        # the tile it now agrees with


def test_a_failed_ai_summary_is_retried_after_a_few_minutes_not_a_day(monkeypatch):
    import time as real
    from types import SimpleNamespace
    from app.intel import net
    f = market()
    replies = [AIBusy("busy"), json.dumps({"summary": "NIFTY 50 closed 0.42% higher; Nifty IT moved to Leading."})]

    def fake(*a, **k):
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    write._cache.clear()
    monkeypatch.setattr(write, "complete", fake)
    assert write.summary(f)["ai"] is False and len(replies) == 1
    assert write.summary(f)["ai"] is False and len(replies) == 1            # within the minutes: not asked again
    monkeypatch.setattr(net, "time", SimpleNamespace(time=lambda: real.time() + 11 * 60))
    assert write.summary(f)["ai"] is True                                  # after them the AI is asked again
    write._cache.clear()


# ---------- 15 Oct: the India brief's start timed out on the database and went 19 minutes late, with no word ----------
def test_a_timeout_starting_the_send_is_tried_again_within_minutes(w, monkeypatch, outbox):
    import httpx
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-pro", "pro@example.com", market_in="daily")
    real, failed = job.open_ledger, []

    def slow_once(iid):
        if not failed:
            failed.append(iid)
            raise httpx.ReadTimeout("The read operation timed out")
        return real(iid)
    monkeypatch.setattr(job, "open_ledger", slow_once)
    j = job.Job("newsletters")
    pauses = []
    j.sleep = pauses.append
    assert j.tick(AFTER_IN_CLOSE) == 1 and failed                 # sent in the same check, after one pause
    assert pauses == [job.START_RETRY_PAUSES[0]] and pauses[0] <= 120
    assert [to for to, *_ in outbox] == ["pro@example.com"]


def test_the_tries_to_start_are_bounded_and_the_next_check_still_tries(w, monkeypatch, outbox):
    import httpx
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-pro", "pro@example.com", market_in="daily")
    real, tries = job.open_ledger, []

    def down(iid):
        tries.append(iid)
        raise httpx.PoolTimeout("timed out")
    monkeypatch.setattr(job, "open_ledger", down)
    j = job.Job("newsletters")
    pauses = []
    j.sleep = pauses.append
    assert j.tick(AFTER_IN_CLOSE) == 0 and outbox == []
    assert len(tries) == len(job.START_RETRY_PAUSES) + 1 and pauses == list(job.START_RETRY_PAUSES)
    assert "couldn't start the send" in j.status["regions"]["IN"]["error"]
    monkeypatch.setattr(job, "open_ledger", real)                 # the database is back
    assert j.tick(AFTER_IN_CLOSE + timedelta(minutes=5)) == 1


def test_an_error_that_wont_pass_is_not_retried_in_the_check(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    monkeypatch.setattr(job, "open_ledger", lambda iid: (_ for _ in ()).throw(ValueError("bad issue")))
    j = job.Job("newsletters")
    j.sleep = lambda s: pytest.fail("no pause for an error a retry can't fix")
    assert j.tick(AFTER_IN_CLOSE) == 0


def test_the_admins_are_told_when_the_brief_is_30_minutes_late(w, monkeypatch, outbox):
    told = []
    monkeypatch.setattr(alerts, "tell_admins", lambda subject, text, label="Admin alert": told.append((subject, text)) or 1)
    j = job.Job("newsletters")
    j.status["last_error"] = "IN: The read operation timed out"
    slot = datetime(2026, 10, 1, 10, 45, tzinfo=timezone.utc)         # 16:15 IST
    assert j.check_late(slot + timedelta(minutes=29)) == [] and told == []
    assert j.check_late(slot + timedelta(minutes=31)) == ["IN"]
    subject, text = told[0]
    assert subject == "India Market Brief is late (2026-10-01)"
    assert "4:15 PM" in text and "31 minutes" in text and "timed out" in text
    assert j.check_late(slot + timedelta(minutes=36)) == [] and len(told) == 1       # once a day
    assert job.Job("newsletters").check_late(slot + timedelta(minutes=41)) == []     # and not again after a restart
    assert len(told) == 1


def test_no_late_alert_once_the_brief_went(w, monkeypatch, outbox):
    told = []
    monkeypatch.setattr(alerts, "tell_admins", lambda subject, text, label="Admin alert": told.append(subject) or 1)
    monkeypatch.setattr(content, "market_facts", lambda region, day, weekly=False: market(region, weekly, day))
    reader("u-pro", "pro@example.com", market_in="daily")
    assert job.Job("newsletters").tick(AFTER_IN_CLOSE) == 1
    late = datetime(2026, 10, 1, 11, 30, tzinfo=timezone.utc)
    assert job.Job("newsletters").check_late(late) == [] and told == []                # a restarted job reads the mark
    assert job.Job("newsletters").check_late(datetime(2026, 10, 2, 11, 30, tzinfo=timezone.utc)) == []   # holiday


# ---------- R29B-020: My stocks follows the India brief ----------
def test_my_stocks_waits_for_the_india_brief_then_goes_without_it(w, monkeypatch, outbox):
    monkeypatch.setattr(content, "market_facts", lambda *a, **k: {"kind": "market"})
    reader("u-pro", "pro@example.com", my_stocks="daily")
    db.set_setting("watchlist:u-pro", json.dumps({"items": [{"symbol": "RELIANCE", "region": "IN"}]}))
    qip = {"id": "9", "at": "2026-10-01T18:00", "category": "qip", "label": "QIP (fund raise)", "severity": "red",
           "subject": "Qualified Institutions Placement", "text": "", "url": "https://example.com/q.pdf"}
    monkeypatch.setattr(main.filings_feed, "announcements", lambda sym, days=365: [qip], raising=False)
    j = job.Job()
    assert j.tick(AFTER_IN_CLOSE) == 0                                          # 16:30 IST, no brief yet: held
    assert j.tick(AFTER_IN_CLOSE + timedelta(minutes=50)) == 1                  # 17:20: the hour's wait is over
    j2 = job.Job()
    j2.mark("market-IN", date(2026, 10, 1))
    assert j2.brief_started("market-IN", date(2026, 10, 1), AFTER_IN_CLOSE)


# ---------- R29B-012: only the watchlist and holdings ----------
def test_my_stocks_uses_only_watchlist_and_holdings(w, monkeypatch):
    db.set_setting("watchlist:u-x", json.dumps({"items": [{"symbol": "TCS", "region": "IN"}, {"symbol": "NVDA", "region": "US"}]}))
    monkeypatch.setattr(db, "list_notebook_rows", lambda uid: [{"instrument": {"symbol": "RELIANCE", "market": "IN", "type": "EQ"}}])
    assert content.my_stocks("u-x") == [("IN", "TCS"), ("US", "NVDA")]


# ---------- R29B-002: the item carries its market's currency ----------
def test_my_stocks_items_carry_region_and_currency():
    f = {"stocks": [{"symbol": "NVDA", "region": "US", "price": 221.3, "change_pct": 1.0, "since_day": "2026-10-14"},
                    {"symbol": "TCS", "region": "IN", "price": 3000.0, "change_pct": None}], "since": "2026-10-14"}
    items = write.stock_sections(f)[0]["items"]
    assert [(i["region"], i["currency"]) for i in items] == [("US", "USD"), ("IN", "INR")]


# ---------- R29B-007: One-Click only with a tokenised link ----------
def test_one_click_header_only_goes_with_a_tokenised_unsubscribe_link(monkeypatch):
    from app import alerts as A
    sent = []
    monkeypatch.setattr(A.settings, "BREVO_API_KEY", "k", raising=False)
    monkeypatch.setattr(A, "_send_brevo", lambda to, subject, body, html=None, headers=None: sent.append(headers))
    post = {"List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    A.send_email("a@example.com", "s", "b", headers={"List-Unsubscribe": "<https://x.example/settings#newsletters>", **post})
    assert "List-Unsubscribe-Post" not in sent[-1] and "settings#newsletters" in sent[-1]["List-Unsubscribe"]
    A.send_email("a@example.com", "s", "b", headers=A.list_unsubscribe_headers("u1", A.ALERT_EMAILS))
    assert sent[-1]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click" and "/unsubscribe?t=" in sent[-1]["List-Unsubscribe"]
    A.send_email("a@example.com", "s", "b", headers=post)             # none of its own: Manage emails, no One-Click
    assert "List-Unsubscribe-Post" not in sent[-1]
