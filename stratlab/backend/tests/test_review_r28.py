"""Round 28, India after the close: the market read's size claims and stale headlines, the brief's rotation links and index
levels, the paper report's minus, the closing auction's stamp, the India VIX close and open, the final live breadth, and the
Stage in My Stocks. Fixed clocks only."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest

from app import main  # noqa: F401, I001  (first: the app loads its modules in a fixed order)
from app import breadth_live, closing_auction as CA, daily_report, db, vix as V
from app.intel import ai as A, grounding as G
from app.newsletter import content, write
from tests.test_breadth import mem  # noqa: F401  (fixture)
from tests.test_breadth_live import EVENING, OPEN, live, with_base
from tests import world as W

IST = timezone(timedelta(hours=5, minutes=30))
INDICES = [{"name": "NIFTY 50", "price": 25800.0, "change_pct": 1.66, "low52": 21000.0, "high52": 26300.0},
           {"name": "SENSEX", "price": 84500.0, "change_pct": 2.11, "low52": 70000.0, "high52": 86000.0}]


# ---------- R28-004 ----------
def test_double_digit_gains_are_rejected_when_every_move_is_under_ten_percent():
    bad = "Both major indices posted double-digit percentage gains."
    assert not G.magnitude_ok(bad, INDICES)
    assert G.magnitude_ok("NIFTY 50 gained 1.66%.", INDICES)
    assert G.magnitude_ok(bad, [{"name": "X", "change_pct": 11.2}])


def test_pulse_drops_the_double_digit_sentence_and_keeps_the_rest():
    heads = [{"headline": "Infosys shares in focus", "at": "2026-10-15T09:00:00+05:30"}]
    read = {"tone": "NIFTY 50 gained 1.66%. Both major indices posted double-digit percentage gains.", "hot": [], "flows": [],
            "themes": [{"theme": "Rally", "detail": "Both major indices posted double-digit percentage gains.", "example": ""}]}
    out = G.ground_pulse(read, INDICES, heads)
    assert out["tone"] == "NIFTY 50 gained 1.66%."
    assert out["themes"] == []


def test_headlines_older_than_the_session_day_are_left_out_of_the_read(monkeypatch):
    monkeypatch.setattr(A, "ist_date", lambda: date(2026, 10, 15))
    seen = {}
    monkeypatch.setattr(A, "_ask", lambda system, facts, ai, n: seen.update(facts=facts) or {"tone": "NIFTY 50 gained 1.66%."})
    heads = [{"headline": "Old Infosys line", "at": "2026-10-14T16:00:00+05:30"},
             {"headline": "Fresh line", "at": "2026-10-15T10:00:00+05:30"}, {"headline": "Undated line"}]
    A.pulse("IN", "", INDICES, heads, None, closed=True)
    assert seen["facts"]["headlines"] == ["[2026-10-15] Fresh line", "[] Undated line"]


# ---------- R28-006, R28-009 ----------
def test_rotation_links_carry_the_briefs_region(monkeypatch):
    for region in ("IN", "US"):
        secs = write.market_sections({"region": region, "weekly": False, "indices": [],
                                      "rotation": [{"sector": "IT", "from": "lagging", "to": "improving"}]})
        assert secs[0]["items"][0]["url"].endswith(f"/research/rotation?region={region}")


def test_a_stored_brief_with_the_bare_rotation_link_is_given_its_region():
    bare = f"{write.origin()}/research/rotation"
    issue = {"region": "IN", "sections": [{"title": "Sector rotation", "items": [{"text": "x", "url": bare}]}]}
    assert write.regional_links(issue)["sections"][0]["items"][0]["url"] == bare + "?region=IN"


def test_index_levels_in_the_web_prose_have_two_decimals():
    idx = [{"name": "NIFTY BANK", "price": 55810.5, "change_pct": 0.5}]
    assert "55,810.50" in write.house_numbers("NIFTY BANK closed at 55,810.5.", idx)
    view = main.news_view({"id": "market:IN:2026-10-15", "kind": "market", "region": "IN", "day": "2026-10-15", "subject": "s",
                           "summary": "x", "ai_summary": "NIFTY BANK closed at 55,810.5.", "indices": idx, "sections": [], "html": ""})
    assert "55,810.50" in view["ai_summary"]


# ---------- R28-008 ----------
def test_paper_report_percent_uses_the_true_minus():
    row = {"name": "S", "currency": "INR", "closed": 0, "wins": 0, "pnl": 0, "open": 0, "unrealised": 0, "equity": 4725503,
           "capital": 5000000}
    text = daily_report.text("India", "2026-10-15", [row])
    assert "−₹2,74,497 (−5.5%)" in text and "-5.5" not in text
    up = daily_report.text("India", "2026-10-15", [{**row, "equity": 5100000}])
    assert "(+2.0%)" in up


# ---------- R28-010 ----------
@pytest.fixture
def w(monkeypatch):
    world = W.build(monkeypatch)
    yield world
    world["close"]()
    CA.forget()


def test_closing_auction_stamp_is_the_read_that_holds_the_final_prices(w, monkeypatch):
    stock = dict(zip(CA.FIELDS, [100.0, 95.0, 105.0, 101.0, 10, 102.0, 50, 0, 0, 0, 0, 0, 0, 0, 0]))
    row = {"read": "2026-10-15T15:36:10+05:30", "day": "2026-10-15", "as_of": "2026-10-15T15:28:00+05:30", "status": "ok",
           "message": None, "eligible": ["ABC"], "stocks": {"ABC": stock}, "indices": {}, "start": {}}
    monkeypatch.setattr(CA, "load_live", lambda: row)
    v = CA.view({"id": "u", "_plan": "pro"}, datetime(2026, 10, 15, 15, 40, tzinfo=IST))
    assert v["phase"] == "closed" and v["stocks"][0]["final_out"]
    assert v["as_of"] == "2026-10-15T15:36:10+05:30"
    during = CA.view({"id": "u", "_plan": "pro"}, datetime(2026, 10, 15, 15, 29, tzinfo=IST))
    assert during["as_of"] == "2026-10-15T15:28:00+05:30"


def test_the_final_prices_stamp_holds_when_the_read_is_stored_in_utc(w, monkeypatch):
    """R35: the server stores its read time in UTC; compared as text with the exchange's IST stamp it looked earlier, so
    the final prices kept 'as of 15:28'."""
    stock = dict(zip(CA.FIELDS, [100.0, 95.0, 105.0, 101.0, 10, 102.0, 50, 0, 0, 0, 0, 0, 0, 0, 0]))
    row = {"read": "2026-10-15T10:06:10+00:00", "day": "2026-10-15", "as_of": "2026-10-15T15:28:00+05:30", "status": "ok",
           "message": None, "eligible": ["ABC"], "stocks": {"ABC": stock}, "indices": {}, "start": {}}
    monkeypatch.setattr(CA, "load_live", lambda: row)
    v = CA.view({"id": "u", "_plan": "pro"}, datetime(2026, 10, 15, 15, 40, tzinfo=IST))
    assert v["stocks"][0]["final_out"] and v["as_of"] == "2026-10-15T10:06:10+00:00"


# ---------- R28-011 ----------
LIST = {"timestamp": "15-Oct-2026 15:30:00",
        "data": [{"index": "INDIA VIX", "last": 14.2, "previousClose": 14.63, "open": 14.63, "high": 14.9, "low": 13.9}]}


def test_an_open_equal_to_yesterdays_close_is_not_an_open():
    q = V.parse_quote(LIST)
    assert q["open"] is None and q["value"] == 14.2
    real = V.parse_quote({**LIST, "data": [{**LIST["data"][0], "open": 14.5}]})
    assert real["open"] == 14.5


def test_the_last_quote_after_the_close_stands_in_for_the_missing_close(w, monkeypatch):
    monkeypatch.setattr(V, "quote_now", lambda feed=None: V.parse_quote(LIST))
    row = V.last_quote_row(date(2026, 10, 15))
    assert row == {"2026-10-15": [None, 14.9, 13.9, 14.2]}
    early = V.parse_quote({**LIST, "timestamp": "15-Oct-2026 15:10:00"})
    monkeypatch.setattr(V, "quote_now", lambda feed=None: early)
    assert V.last_quote_row(date(2026, 10, 15)) is None


def test_the_job_stores_the_last_quote_when_the_history_has_no_row(w, monkeypatch):
    from app.data import calendar
    monkeypatch.setattr(calendar, "is_trading_day", lambda region, d: d.weekday() < 5)
    monkeypatch.setattr(V, "daily", lambda *a, **k: [("2026-10-14", [14, 15, 13, 14.63])])
    monkeypatch.setattr(V, "fetch", lambda *a, **k: {})
    monkeypatch.setattr(V, "quote_now", lambda feed=None: V.parse_quote(LIST))
    stored = {}
    monkeypatch.setattr(V, "store", lambda rows: stored.update(rows) or len(rows))
    job = V.Job(lambda: None, sleep=lambda s: None)
    job.tick(datetime(2026, 10, 15, 16, 20, tzinfo=IST).astimezone(timezone.utc))      # Thursday
    assert stored == {"2026-10-15": [None, 14.9, 13.9, 14.2]}
    assert job.status["last_error"] is None


# ---------- R28-012 ----------
AFTER = datetime(2026, 10, 1, 10, 50, tzinfo=timezone.utc)          # 16:20 IST, closed


def test_final_live_breadth_stays_until_the_evening_figures_land(mem):
    with_base(mem)
    live(mem).round("IN", OPEN)
    v = breadth_live.view("nifty500", AFTER)
    assert v["state"] == "final" and v["as_of"] == "10:30" and v["latest"]["adv"] == 1 and not v["late"]
    assert breadth_live.settled(v, "2026-10-01") is None and breadth_live.settled(v, "2026-09-30") is v      # the evening's count is in
    assert breadth_live.view("nifty500", datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)) is None      # the next morning


# ---------- R28-014 ----------
def test_my_stocks_states_a_stage_only_where_the_page_shows_one(monkeypatch):
    class Store:
        def __init__(self, facts):
            self.facts = facts

        def peek(self, region, sym):
            return self.facts
    for facts, shown in (({"stage": 4}, True), ({"stage": None}, False), (None, True)):
        monkeypatch.setattr(main, "stock_page_store", Store(facts))
        assert content.page_shows_stage("IN", "RELIANCE") is shown
