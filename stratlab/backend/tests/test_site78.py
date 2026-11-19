"""Lane site78: the LIVE15A / LIVE15B site findings (live review after Release 77, Thu 19 Nov 2026)."""
import json
import time
from datetime import date, datetime, timezone

import httpx

from app import main  # noqa: F401, I001  (first: the app loads its jobs before the modules built on them)
from app.intel import yahoo as Y

# 18 Nov 2026 (New York on EST): the session 09:30-16:00 ET = 14:30-21:00 UTC, the kept copy's last trade 10:52 ET, the brief built 16:50 ET
OPEN = datetime(2026, 11, 18, 14, 30, tzinfo=timezone.utc).timestamp()
CLOSE = datetime(2026, 11, 18, 21, 0, tzinfo=timezone.utc).timestamp()
KEPT = datetime(2026, 11, 18, 15, 52, 49, tzinfo=timezone.utc).timestamp()
BUILT = datetime(2026, 11, 18, 21, 50, tzinfo=timezone.utc).timestamp()
PREV_DAY = datetime(2026, 11, 17, 14, 30, tzinfo=timezone.utc).timestamp()


def _answer(symbol: str, prev: float, price: float, last: float) -> dict:
    return {"chart": {"result": [{
        "meta": {"symbol": symbol, "currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": "INDEX",
                 "regularMarketPrice": price, "regularMarketTime": int(last),
                 "currentTradingPeriod": {"regular": {"start": int(OPEN), "end": int(CLOSE)}}},
        "timestamp": [int(PREV_DAY), int(OPEN)],
        "indicators": {"quote": [{"open": [prev, price], "high": [prev, price], "low": [prev, price], "close": [prev, price],
                                  "volume": [1, 1]}]}}], "error": None}}


def _yahoo(fresh_price: float | None, fresh_last: float):
    seen = []

    def reply(r: httpx.Request):
        seen.append(r.url.host)
        if r.url.host == "query2.finance.yahoo.com":
            if fresh_price is None:
                return httpx.Response(200, json=_answer("^GSPC", 7340.53, 7303.98, KEPT))
            return httpx.Response(200, json=_answer("^GSPC", 7340.53, fresh_price, fresh_last))
        return httpx.Response(200, json=_answer("^GSPC", 7340.53, 7303.98, KEPT))
    return Y.Yahoo(transport=httpx.MockTransport(reply)), seen


# ---------- LIVE15A-001: the US brief is written from the day's closes, never a level an edge copy kept ----------
def test_live15a_001_a_closing_read_that_is_a_kept_mid_session_copy_is_asked_again_and_the_close_stands():
    y, seen = _yahoo(7323.63, CLOSE + 2)
    got = y.closing_chart("^GSPC", 21, now=BUILT)
    assert got["candles"][-1]["c"] == 7323.63
    assert seen == ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]


def test_live15a_001_no_close_is_given_when_every_address_sends_the_kept_copy():
    y, _ = _yahoo(None, KEPT)
    assert y.closing_chart("^GSPC", 21, now=BUILT) is None


def test_live15a_001_the_briefs_index_close_refuses_a_level_older_than_the_close(monkeypatch):
    from app.newsletter import content
    y, _ = _yahoo(None, KEPT)
    monkeypatch.setattr(main.research_hub, "yahoo", y)
    monkeypatch.setattr(time, "time", lambda: BUILT)
    assert content.index_close("^GSPC", date(2026, 11, 18), prev="2026-11-17") is None
    y2, _ = _yahoo(7323.63, CLOSE + 2)
    monkeypatch.setattr(main.research_hub, "yahoo", y2)
    got = content.index_close("^GSPC", date(2026, 11, 18), prev="2026-11-17")
    assert got == {"price": 7323.63, "change_pct": round((7323.63 / 7340.53 - 1) * 100, 2)} and got["change_pct"] == -0.23


def test_live15a_001_a_level_from_before_the_close_is_not_taken_as_the_days_close(monkeypatch):
    from app.newsletter import content
    monkeypatch.setattr(content, "index_close", lambda *a, **k: None)
    live = [{"name": "S&P 500", "price": 7303.98, "change_pct": -0.5, "day": "2026-11-18", "stale": False, "pre_close": True}]
    monkeypatch.setattr(main.research_hub, "indices", lambda region: live)
    assert content.index_moves("US", date(2026, 11, 18), False) == []
    live[0]["pre_close"] = False
    assert content.index_moves("US", date(2026, 11, 18), False)[0]["price"] == 7303.98


def test_live15a_001_a_daily_brief_with_no_index_close_waits_for_the_next_check(monkeypatch):
    from app.newsletter import content, job
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(content, "market_facts", lambda r, d, w: {"kind": "market", "region": r, "day": d.isoformat(), "weekly": w,
                                                                    "headlines": [{"headline": "x"}]})
    ny = ZoneInfo("America/New_York")
    assert job.build_market("US", date(2026, 11, 18), store=False, now=datetime(2026, 11, 18, 16, 55, tzinfo=ny)) is None
    monkeypatch.setattr(job, "make_issue", lambda facts, scope: {"id": "x", **facts})
    assert job.build_market("US", date(2026, 11, 18), store=False, now=datetime(2026, 11, 18, 18, 55, tzinfo=ny))["id"] == "x"


def test_live15a_001_the_stored_brief_and_its_post_are_set_to_the_days_closes(monkeypatch):
    from app import blog, db
    from app.newsletter import content, job
    closes = {"^GSPC": (7323.63, -0.23), "^IXIC": (24429.88, 0.42), "^DJI": (50198.17, -1.11)}
    monkeypatch.setattr(content, "INDICES", {"US": [("S&P 500", "^GSPC"), ("NASDAQ", "^IXIC"), ("DOW JONES", "^DJI")]})
    monkeypatch.setattr(content, "index_close", lambda sym, day, since=None, prev=None:
                        {"price": closes[sym][0], "change_pct": closes[sym][1]})
    monkeypatch.setattr(content, "reference_day", lambda r, d, w: date(2026, 11, 17))
    issue = {"id": "market.US.2026-11-18", "kind": "market", "region": "US", "day": "2026-11-18", "weekly": False,
             "at": "2026-11-19T03:20+05:30", "subject": "US market brief, 18 Nov 2026: S&P 500 −0.50%", "summary": "S&P 500 −0.50%.",
             "ai": True, "ai_summary": "The S&P 500 fell 0.50% to 7,303.98.",
             "indices": [{"name": "S&P 500", "price": 7303.98, "change_pct": -0.5}, {"name": "NASDAQ", "price": 24322.71, "change_pct": -0.02},
                         {"name": "DOW JONES", "price": 50089.71, "change_pct": -1.32}],
             "sections": [{"title": "Indices", "items": [{"text": "S&P 500: 7,303.98, −0.50% on the day"}]}]}
    today = date.today().isoformat()
    issue["day"] = today
    iid = f"market.US.{today}"
    issue["id"] = iid
    store = {"news-index:market:US": json.dumps([iid]), f"news:market:US:{today}": json.dumps(issue)}
    monkeypatch.setattr(db, "get_setting", store.get)
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    posts = []
    monkeypatch.setattr(blog, "rewrite_brief", lambda i: posts.append(i) or True)
    assert job.repair_closes("US") == [iid]
    kept = json.loads(store[f"news:market:US:{today}"])
    assert [i["price"] for i in kept["indices"]] == [7323.63, 24429.88, 50198.17]
    assert [i["change_pct"] for i in kept["indices"]] == [-0.23, 0.42, -1.11]
    assert "−0.23%" in kept["subject"] and "7,303.98" not in kept["text"] and "ai_summary" not in kept
    assert posts and posts[0]["indices"][0]["price"] == 7323.63
    assert job.repair_closes("US") == []                     # a stored brief at the closes is left as it is


def test_live15a_001_a_corrected_issue_rewrites_its_existing_post_in_place(monkeypatch):
    from app import blog
    issue = {"id": "market.US.2026-11-18", "kind": "market", "region": "US", "day": "2026-11-18", "weekly": False,
             "indices": [{"name": "S&P 500", "price": 7323.63, "change_pct": -0.23}], "sections": []}
    monkeypatch.setattr(blog, "_open_day", lambda r, d: True)
    monkeypatch.setattr(blog, "get", lambda slug: {"slug": slug, "body": {"gen": blog.BRIEF_GEN}})
    wrote = []
    monkeypatch.setattr(blog, "_rewrite", lambda post: wrote.append(post))
    assert blog.rewrite_brief(issue)
    assert wrote[0]["slug"] == "us-market-brief-2026-11-18" and "−0.23%" in wrote[0]["title"]


# ---------- LIVE15A-002: the Mood card is read again on a clock while the market trades ----------
def test_live15a_002_the_mood_card_is_read_again_every_quarter_hour_while_the_market_trades_and_no_more(monkeypatch):
    from app import mood_job
    from app.data import calendar as tc
    from zoneinfo import ZoneInfo
    monkeypatch.setattr(tc, "is_trading_day", lambda m, d: d.weekday() < 5)
    asked = []
    j = mood_job.Job(read=lambda r: {}, mood=lambda r, d=None: None, session=lambda r: asked.append(r) or "2026-11-19")
    ist = ZoneInfo("Asia/Kolkata")
    at = lambda h, m: datetime(2026, 11, 19, h, m, tzinfo=ist)          # noqa: E731
    assert j.tick_session(at(9, 20)) == {}                               # before the open read's time
    assert j.tick_session(at(9, 35)) == {"IN": "2026-11-19"}
    assert j.tick_session(at(9, 40)) == {}                               # five minutes later: not yet
    assert j.tick_session(at(9, 50)) == {"IN": "2026-11-19"}             # a quarter hour after the last
    assert j.tick_session(at(15, 35)) == {}                              # the market has shut
    assert asked == ["IN", "IN"]
    # bounded: at most SESSION_MAX reads a day
    j2 = mood_job.Job(read=lambda r: {}, mood=lambda r, d=None: None, session=lambda r: "x")
    from datetime import timedelta
    n = sum("IN" in j2.tick_session(at(9, 30) + timedelta(minutes=15 * k)) for k in range(30))
    assert n == 24 <= mood_job.SESSION_MAX                               # 09:30 to 15:15 IST, every 15 minutes


def test_live15a_002_the_clock_job_reads_the_card_in_session():
    from app import mood_job
    assert mood_job.job.session is mood_job._mood_open


# ---------- LIVE15A-003 / LIVE15B-001: a sample deck stays available across a release ----------
def test_live15a_003_the_last_deck_that_passed_stays_the_sample_until_a_deck_of_todays_versions_passes():
    """Fails before: Release 77 changed the deck's versions, every kept PDF stopped being current and /info said available:false (the
    Plans table and the Free list still promised a sample) until someone made a deck again."""
    from app import sample_deck as S
    ok = {"items": [{"id": "a", "ok": True}]}
    bad = {"items": [{"id": "a", "ok": False}]}
    old_good = {"id": "old", "label": "India IT services (PDF, 2026-11-18)", "region": "IN", "meta": {"versions": [1], "gate": ok}}
    assert S.pick([old_good], [2])["id"] == "old"                                     # after the release: the last good one
    new_bad = {"id": "nb", "label": "Cement (PDF, 2026-11-19)", "region": "IN", "meta": {"versions": [2], "gate": bad}}
    assert S.pick([new_bad, old_good], [2])["id"] == "old"                            # a new deck that failed its gate doesn't replace it
    new_good = {"id": "ng", "label": "Consumer durables (PDF, 2026-11-19)", "region": "IN", "meta": {"versions": [2], "gate": ok}}
    assert S.pick([new_good, new_bad, old_good], [2])["id"] == "ng"                   # one of today's versions passed: it is the sample
    assert S.pick([new_bad], [2])["id"] == "nb"                                       # nothing ever passed: as fix20 had it
    assert S.pick([{**old_good, "meta": {"versions": [1]}}], [2]) is None             # an older release's deck with no gate: never


def test_live15a_003_the_link_to_the_last_good_deck_downloads_it(monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from app import computed
    rows = [{"id": "old", "label": "India IT services (PDF, 2026-11-18)", "region": "IN",
             "meta": {"versions": ["an earlier release"], "gate": {"items": [{"id": "a", "ok": True}]}}}]
    monkeypatch.setattr(computed, "entries", lambda kind, q="", region="", limit=500: rows if kind == "deck:theme" else [])
    monkeypatch.setattr(computed, "get_hk", lambda kind, hk: {"value": base64.b64encode(b"%PDF-old").decode()} if hk == "old" else None)
    c = TestClient(main.app)
    info = c.get("/pricing/sample-deck/info").json()
    assert info == {"available": True, "theme": "India IT services", "region": "IN", "id": "old"}
    assert c.get("/pricing/sample-deck", params={"id": "old"}).content == b"%PDF-old"


# ---------- LIVE15A-010: Results never shows growth of a quarter older than the last two ----------
def test_live15a_010_growth_of_a_quarter_older_than_the_last_two_says_not_reported(monkeypatch):
    from app import results as R
    assert R.too_old("Dec 2020 vs Dec 2019", "2026-11-19") and R.too_old("Jun 2014 vs Jun 2013", "2026-11-19")
    assert not R.too_old("Sep 2026 vs Sep 2025", "2026-11-19")                # the quarter being reported
    assert not R.too_old("Jul 2026 vs Jul 2025", "2026-11-19")                # the one before it ("previous quarter")
    assert R.too_old("Mar 2026 vs Mar 2025", "2026-11-19")                    # three quarters back
    assert not R.too_old(None, "2026-11-19") and not R.too_old("soon", "2026-11-19")
    rows = [R.row("US", "PDD", date(2026, 11, 19), "Quarterly results"), R.row("US", "WMT", date(2026, 11, 19), "Quarterly results")]
    monkeypatch.setattr(R, "load", lambda region: {"rows": rows, "v": R.CAL_VERSION, "at": "2026-11-19T04:00:00+00:00"})
    snaps = {"PDD": {"market_cap": 1e11, "q_sales": 146.0, "q_profit": 10.0, "q_of": "Dec 2020 vs Dec 2019"},
             "WMT": {"market_cap": 7e11, "q_sales": 4.8, "q_profit": 1.2, "q_of": "Jul 2026 vs Jul 2025"}}
    monkeypatch.setattr(R, "_snap", lambda region: snaps)
    monkeypatch.setattr(R, "index_sets", lambda region: {})
    monkeypatch.setattr(R, "load_moves", lambda region: {})
    monkeypatch.setattr(R, "my_stocks", lambda uid, region: [])
    monkeypatch.setattr(R, "alerts_on", lambda uid: False)
    v = R.view("US", "u-pro", "all", today=date(2026, 11, 19))
    got = {r["symbol"]: r["q"] for wk in v["weeks"] for r in wk["rows"]}
    assert got["PDD"] == {"sales": None, "profit": None, "of": "Dec 2020 vs Dec 2019", "unreported": True}
    assert got["WMT"]["sales"] == 4.8 and not got["WMT"].get("unreported")
