"""25 Oct 2026 deep audit of search, navigation, My space and the briefs (DI-001 .. DI-033), the server's side: the company
directory says how well each company matched, first steps follow what the person came for, My space's layout is kept on
the account, and the briefs give each figure its period, a holiday week its true close and the rotation its benchmark."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import db, first_steps, main, newsletter_prefs  # noqa: F401  (main loads the app's modules in their order)
from app.newsletter import content, job, write
from tests import world as W
from tests.fake_db import headers

PRO = headers("pro-token")


@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    main.suggester.clear()
    first_steps._marked.clear()
    yield world
    main.suggester.clear()
    world["close"]()


# ---------- DI-001, DI-002: the company directory for the search box ----------
def test_the_directory_says_how_well_each_company_matched(w):
    c = w["client"]
    rows = c.get("/suggest/companies?q=RELIANCE&ranked=true", headers=PRO).json()["rows"]
    assert rows[0]["symbol"] == "RELIANCE" and rows[0]["market"] == "IN" and rows[0]["match"] == 0
    assert all(isinstance(r["match"], int) and not any(k.startswith("_") for k in r) for r in rows)
    # a typo still finds it, as a looser match
    typo = c.get("/suggest/companies?q=relaince&ranked=true&market=IN", headers=PRO).json()["rows"]
    assert typo and typo[0]["symbol"] == "RELIANCE" and typo[0]["match"] > 3
    # without the flag the answer is as before (the company boxes read it)
    assert "match" not in c.get("/suggest/companies?q=RELIANCE", headers=PRO).json()["rows"][0]


# ---------- DI-008: first steps for what the person came for ----------
def test_first_steps_follow_the_focus(w):
    c = w["client"]
    db.update_profile("u-basic", created_at=datetime.now(timezone.utc).isoformat())
    h = headers("basic-token")
    ids = lambda: [s["id"] for s in c.get("/me/first-steps", headers=h).json()["steps"]]  # noqa: E731
    assert ids() == ["backtest", "watchlist", "deepdive", "paper", "alerts"]                     # no answer yet: the lab's five
    assert c.put("/me/prefs", headers=h, json={"focus": "money"}).status_code == 200
    assert ids() == ["holdings", "networth", "tax", "alerts"]
    c.put("/me/prefs", headers=h, json={"focus": "both"})
    assert ids() == ["backtest", "watchlist", "deepdive", "holdings", "alerts"]
    c.put("/me/prefs", headers=h, json={"focus": "invest"})
    assert ids() == ["watchlist", "deepdive", "holdings", "alerts"]
    steps = {s["id"]: s for s in c.get("/me/first-steps", headers=h).json()["steps"]}
    assert steps["alerts"]["to"] == "/settings#notifications" and steps["holdings"]["to"] == "/holdings"
    assert not steps["holdings"]["done"]
    db.set_setting("holdings:u-basic", json.dumps({"items": [{"symbol": "TCS", "qty": 1, "avg": 100}]}))
    steps = {s["id"]: s for s in c.get("/me/first-steps", headers=h).json()["steps"]}
    assert steps["holdings"]["done"] and not steps["watchlist"]["done"]           # ticked from the user's own data


# ---------- DI-006: My space's layout on the account ----------
def test_my_space_layout_is_kept_on_the_account(w):
    c = w["client"]
    h = headers("free-token")
    assert "mine" not in c.get("/me", headers=h).json()["prefs"]                                # none saved: nothing to read
    lay = {"order": ["networth", "markets", "pnl", "paper", "coming", "watch"], "hidden": ["paper"]}
    r = c.put("/me/prefs", headers=h, json={"mine": lay})
    assert r.status_code == 200 and r.json()["prefs"]["mine"] == lay
    assert c.get("/me", headers=h).json()["prefs"]["mine"] == lay                               # another device reads the same
    c.put("/me/prefs", headers=h, json={"level": "new"})
    assert c.get("/me", headers=h).json()["prefs"]["mine"] == lay                               # other choices leave it alone
    assert c.put("/me/prefs", headers=h, json={"mine": {"order": ["x" * 40]}}).status_code == 422
    assert c.put("/me/prefs", headers=h, json={"mine": {"order": ["a"] * 30}}).status_code == 422


# ---------- DI-024: a weekly brief has no one-day figure ----------
def test_a_weekly_scan_carries_no_one_day_change(monkeypatch):
    rows = [{"symbol": "TECHM", "name": "Tech Mahindra", "price": 1790.0, "chg": -2.14, "stage": 2, "st_up": True, "st_days": 1, "stage_days": 3}]
    monkeypatch.setattr(content.scan, "run", lambda *a, **k: {"rows": rows})
    weekly, daily = content.stage2_names("IN", True), content.stage2_names("IN", False)
    assert "change_pct" not in weekly["st_s2"][0]
    assert daily["st_s2"][0]["change_pct"] == -2.14


# ---------- DI-026: a holiday week's close, and the date day first ----------
def test_a_week_with_a_friday_holiday_ends_on_thursday():
    assert write._week_end("2026-10-03", "IN") == "2026-10-01"            # Fri 2 Oct, Gandhi Jayanti
    assert write._week_end("2026-10-24", "IN") == "2026-10-23"
    assert write._week_end("2026-10-24") == "2026-10-23"                  # no market: the weekend alone, as before
    assert write.close_day({"kind": "market", "region": "IN", "day": "2026-10-03", "weekly": True}) == "2026-10-01"
    assert write.close_day({"kind": "market", "region": "IN", "day": "2026-10-09", "weekly": False}) == "2026-10-09"
    assert write.close_day({"kind": "my_stocks", "day": "2026-10-09"}) is None
    f = {"kind": "market", "region": "IN", "day": "2026-10-03", "weekly": True, "indices": [{"name": "NIFTY 50", "price": 22421.95, "change_pct": -3.11}]}
    assert write.subject(f).startswith("Market Brief India, week to 1 Oct")
    assert write.close_stamp({"kind": "market", "region": "IN", "day": "2026-10-03", "weekly": True}) == "the 15:30 IST close of 1 Oct 2026"


def test_the_ai_writes_dates_day_first():
    assert write.day_first("The S&P 500 fell over the week ending Oct 24.") == "The S&P 500 fell over the week ending 24 Oct."
    assert write.day_first("On October 23, 2026 the index rose 0.4%.") == "On 23 Oct 2026 the index rose 0.4%."
    assert write.day_first("Declines 2 to 1; NIFTY 50 at 22,500.") == "Declines 2 to 1; NIFTY 50 at 22,500."


# ---------- DI-027, DI-028: the rotation's benchmark, the week's holiday, the indices' names ----------
def test_rotation_lines_name_their_benchmark_and_a_holiday_week_says_so():
    f = {"kind": "market", "region": "IN", "weekly": True, "day": "2026-10-24",
         "rotation": [{"sector": "Nifty Bank", "from": "weakening", "to": "leading"}],
         "holidays": content.holidays_in_week("IN", date(2026, 10, 24))}
    secs = {s["title"]: s for s in write.market_sections(f)}
    assert secs["Sector rotation"]["items"][0]["text"].endswith("on the rotation chart (weekly, against the NIFTY 500)")
    assert f["holidays"] and f["holidays"][0]["day"] == "2026-10-20"
    assert secs["No session"]["items"][0]["text"].startswith("The India market was closed on Tue 20 Oct")
    assert secs["No session"]["items"][0]["text"].endswith("so the week had 4 sessions.")
    assert content.holidays_in_week("IN", date(2026, 10, 17)) == []
    us = write.market_sections({**f, "region": "US", "holidays": []})
    assert us[0]["items"][0]["text"].endswith("(weekly, against the S&P 500)")
    assert not any(s["title"] == "No session" for s in write.market_sections({**f, "weekly": False}))
    text = write.house_numbers("The Nasdaq fell 0.71%.", [{"name": "NASDAQ", "price": 25955.34, "change_pct": -0.71}])
    assert text == "The NASDAQ fell 0.71%."


def test_a_stored_brief_is_read_by_todays_rules(w):
    c = w["client"]
    # a weekly brief stored before: its title ran to the Saturday, its summary lost the moves, its rotation had no benchmark
    issue = {"id": "market.IN.2026-10-24.w", "kind": "market", "region": "IN", "day": "2026-10-24", "weekly": True,
             "subject": "Market Brief India, week to 24 Oct: NIFTY 50 −2.36%", "title": "NIFTY 50 down 2.36%", "ai": True,
             "summary": "8 sectors moved to another quadrant on the rotation chart.",
             "ai_summary": "Over the week ending Oct 23, the NIFTY 50 fell.",
             "indices": [{"name": "NIFTY 50", "price": 24100.5, "change_pct": -2.36}],
             "sections": [{"title": "Sector rotation", "items": [{"text": "Nifty Bank moved from Weakening to Leading on the rotation chart (weekly)", "url": None, "lines": []}]},
                          {"title": "Headlines", "items": [{"text": "Sensex falls as markets slide", "url": None, "lines": []}]}],
             "at": "2026-10-24T09:00+05:30"}
    iid = job.issue_id("market", "IN", "2026-10-24", True)
    issue["id"] = iid
    job.save(issue)
    got = job.load(iid)
    assert got["subject"].startswith("Market Brief India, week to 23 Oct")
    assert got["summary"].startswith("NIFTY 50 −2.36% over the week.")
    assert got["ai_summary"] == "Over the week ending 23 Oct, the NIFTY 50 fell."
    rot = next(s for s in got["sections"] if s["title"] == "Sector rotation")
    assert rot["items"][0]["text"].endswith("(weekly, against the NIFTY 500)")
    titles = [s["title"] for s in got["sections"]]
    assert titles.index("No session") < titles.index("Headlines")
    # what is stored is left as it was; the page reads it by today's rules
    assert json.loads(db.get_setting(job._key(*job.parse_id(iid))))["subject"].startswith("Market Brief India, week to 24 Oct")
    view = c.get(f"/news/{iid}", headers=PRO).json()
    assert view["close_day"] == "2026-10-23" and view["subject"].startswith("Market Brief India, week to 23 Oct")
    listed = c.get("/news?kind=market&region=IN", headers=PRO).json()["issues"]
    assert next(i for i in listed if i["id"] == iid)["subject"].startswith("Market Brief India, week to 23 Oct")
