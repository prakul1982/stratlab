"""The newsletters: facts from the fake world, the advice-word filter and template fallback, the email, the
once-a-day schedule, privacy of My Stocks issues, the API and plan gates."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

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
    f = content.market_facts("IN", datetime.now(content.ZoneInfo("Asia/Kolkata")).date())   # the brief's day is India's date, not UTC's
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
    assert content.my_stocks("u-pro") == [("IN", "RELIANCE"), ("US", "AAPL"), ("IN", "TCS")]
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
    assert job.Job().tick(AFTER_IN_CLOSE) == 1
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
