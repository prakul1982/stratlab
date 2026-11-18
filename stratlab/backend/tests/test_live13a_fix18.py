"""LIVE13A (fix18): the heatmap and the movers from the live breadth round's prices while the day's closes aren't stored yet (in the
session, and after the bell until the evening run), said as such; a session's prices gone stale, or a closed session with no prices,
said as "being added"; the public movers page stays on the stored closes."""
import json
from datetime import datetime, timedelta, timezone

import pytest
import time_machine

from app import breadth, breadth_live, heatmap, movers
from tests.test_breadth import IST_OPEN, mem, runner  # noqa: F401  (mem is a fixture)
from tests.test_breadth_live import OPEN, live

AFTER_BELL = datetime(2026, 10, 1, 10, 15, tzinfo=timezone.utc)      # 15:45 IST: the close round's time


@pytest.fixture(autouse=True)
def fresh():
    heatmap.clear()
    movers.clear()
    yield
    heatmap.clear()
    movers.clear()


def quotes(**over):
    q = {"UP": {"price": 1010.0, "prev_close": 999.0, "volume": 4000.0, "high": 1012.0, "low": 998.0, "at": "2026-10-01T10:29:00+05:30"},
         "DOWN": {"price": 95.0, "prev_close": 101.0, "volume": 9000.0, "high": 101.0, "low": 94.0, "at": "2026-10-01T10:29:00+05:30"},
         # FLAT hasn't traded today: its last trade is yesterday's
         "FLAT": {"price": 105.0, "prev_close": 105.0, "volume": 0, "high": 105.0, "low": 105.0, "at": "2026-09-30T15:29:00+05:30"},
         "NIFTY 500": {"price": 24120.0, "prev_close": 24000.0}}
    q.update(over)
    return q


def stored(mem):
    runner().run("IN", IST_OPEN)                    # the daily run: closes of 30 Sep, the marks and the base
    assert heatmap.load("IN")["day"] == "2026-09-30"


def test_in_the_session_the_map_and_the_lists_follow_the_live_round(mem):
    stored(mem)
    with time_machine.travel(OPEN, tick=False):
        assert live(mem, quotes()).round("IN", OPEN)["ok"]
        v = heatmap.view("IN")
    assert v["live"] == {"day": "2026-10-01", "time": "10:30", "close": False} and v["as_of"] == "2026-09-30" and v["behind"] is False
    t = {x["s"]: x for x in v["tiles"]}
    assert t["UP"]["px"] == 1010.0 and t["UP"]["r"][0] == round((1010 / 999 - 1) * 100, 4)
    assert t["DOWN"]["r"][0] == round((95 / 101 - 1) * 100, 4)
    # a longer period runs to the price from the same starting close: UP's year so far moves by 1010/999
    old = {s: r for s, r in heatmap.load("IN")["stocks"].items()}
    assert t["UP"]["r"][4] == round(((1 + old["UP"][5] / 100) * 1010 / 999 - 1) * 100, 2)
    # FLAT has no trade today: no day's change (grey), its stored close and longer changes stay
    assert t["FLAT"]["r"][0] is None and t["FLAT"]["px"] == 105.0 and t["FLAT"]["r"][1:] == old["FLAT"][2:7]
    assert v["index"]["r"][0] == 0.5                                     # NIFTY 500 24,120 against 24,000
    with time_machine.travel(OPEN, tick=False):
        m = movers.view("IN")
    assert m["live"]["time"] == "10:30"
    L = {k: [r["s"] for r in x["rows"]] for k, x in m["lists"].items()}
    assert L["gainers"] == ["UP"] and L["losers"] == ["DOWN"]
    assert "FLAT" not in sum(L.values(), [])                             # no trade today: on none of today's lists
    assert L["highs"] == ["UP"] and L["lows"] == ["DOWN"]                # today's high above its 52-week high; the low below
    assert [r["tv"] for r in m["lists"]["traded"]["rows"]] == [round(1010.0 * 4000), round(95.0 * 9000)]     # the day so far


def test_after_the_bell_the_days_last_trades_stand_until_the_evening_run(mem):
    stored(mem)
    with time_machine.travel(AFTER_BELL, tick=False):
        assert live(mem, quotes()).round("IN", AFTER_BELL)["ok"]
    later = AFTER_BELL + timedelta(hours=2)                              # 17:45 IST: long after the round, still no evening run
    with time_machine.travel(later, tick=False):
        v = heatmap.view("IN")
        m = movers.view("IN")
    assert v["live"] == {"day": "2026-10-01", "time": "15:30", "close": True} and m["live"]["close"] is True
    # the evening run stores 1 Oct: the stored closes again
    runner(data=__import__("tests.test_breadth", fromlist=["market"]).market(end="2026-10-01")).run("IN", later + timedelta(hours=1))
    heatmap.clear()
    movers.clear()
    with time_machine.travel(later + timedelta(hours=1), tick=False):
        v = heatmap.view("IN")
    assert v["as_of"] == "2026-10-01" and v["live"] is None and v["behind"] is False


def test_a_stale_session_round_is_not_shown_as_the_days_and_a_closed_session_without_prices_says_it_is_being_added(mem):
    stored(mem)
    with time_machine.travel(OPEN, tick=False):
        assert live(mem, quotes()).round("IN", OPEN)["ok"]
    with time_machine.travel(OPEN + timedelta(minutes=41), tick=False):
        v = heatmap.view("IN")
    assert v["live"] is None and v["behind"] is False                    # 11:11 IST: still 1 Oct's session, its close not yet in
    heatmap.clear()
    with time_machine.travel(AFTER_BELL, tick=False):
        v = heatmap.view("IN")
        m = movers.view("IN")
    assert v["live"] is None and v["behind"] is True and m["behind"] is True     # 1 Oct has closed; its closes aren't stored yet


def test_the_public_movers_page_and_the_first_days_rows_keep_the_stored_closes(mem):
    stored(mem)
    with time_machine.travel(OPEN, tick=False):
        live(mem, quotes()).round("IN", OPEN)
        m = movers.view("IN", with_live=False)
    assert m["live"] is None and m["behind"] is False
    # a round of the same day as the stored closes (the evening run already in) changes nothing
    doc = json.loads(mem[heatmap.LIVE_KEY + "IN"])
    assert doc["day"] == "2026-10-01" and set(doc["q"]) == {"UP", "DOWN"} and doc["idx"] == {"NIFTY 500": [24120.0, 24000.0]}
    assert heatmap.live_for("IN", "2026-10-01") is None


def test_a_live_price_problem_never_costs_the_breadth_round(mem, monkeypatch):
    stored(mem)
    monkeypatch.setattr(heatmap, "save_live", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no")))
    assert live(mem, quotes()).round("IN", OPEN)["ok"]
    assert breadth_live.load("nifty500", "2026-10-01")["points"]


# ---------- LIVE13A-007: one row per company in "Companies in today's headlines" ----------
def test_companies_in_the_headlines_are_one_row_each():
    from app.intel import grounding
    head = "TCS and Titan lead the losers"
    hot = [{"name": "Tata Consultancy Services", "ticker": "TCS", "why": head}, {"name": "Titan Company", "ticker": "TITAN", "why": head},
           {"name": "Tata Consultancy Services (IT sector)", "ticker": "TCS", "why": head},
           {"name": "Titan Company (consumer durables)", "ticker": "", "why": head}, {"name": "Infosys (IT)", "ticker": "INFY", "why": head}]
    out = grounding.one_row_per_company(hot)
    assert [(h["name"], h["ticker"]) for h in out] == [("Tata Consultancy Services", "TCS"), ("Titan Company", "TITAN"), ("Infosys", "INFY")]


# ---------- LIVE13A-015: Mood's live unchanged row doesn't say "closing" ----------
def test_moods_live_unchanged_row_says_the_latest_count():
    from app.intel import mood
    today = {"day": "2026-11-17", "adv": {"value": 261, "prev": 250}, "dec": {"value": 238, "prev": 249}, "unch": {"value": 1, "prev": 1},
             "stocks": {"value": 500}, "pct20": {"value": 74.8}, "pct50": {"value": 57.4}, "pct200": {"value": 50.0}}
    live = {"adv": 122, "dec": 376, "unch": 2, "pct20": 67.2, "pct50": 51.2, "pct200": 48.2, "at": "14:00"}
    rows = {r["key"]: r["means"] for r in mood.breadth_block(today, live, "NIFTY 500", "2026-11-18")["rows"]}
    assert rows["unch"] == "Stocks at the previous close at the latest count."
    shut = mood.breadth_block(today, None, "NIFTY 500", "2026-11-17")
    assert {r["key"]: r["means"] for r in shut["rows"]}["unch"] == "Stocks closing at the previous close."


# ---------- LIVE13A-028: the headlines' read never goes back to an older stamp within a session ----------
def test_the_sessions_newer_headline_read_is_shown_when_the_moves_return_to_an_older_reads_band(monkeypatch):
    from app import main  # noqa: F401  (loads the app first)
    from app.intel import routes as research_routes
    from tests.test_review_fix12 import _open_market
    store = {}
    _open_market(monkeypatch, store)
    reads = {}

    def call(profile, kind, key, ttl, refresh, build, **k):
        if key not in reads:
            reads[key] = {"tone": f"read for {key[3]}", "hot": [], "flows": [], "themes": [], "generated_at": 100.0 + len(reads)}
            store[repr(("pulse", key))] = reads[key]                     # kept under its key, as the AI store does
        return reads[key]
    monkeypatch.setattr(research_routes, "ai_call", call)
    monkeypatch.setattr(research_routes, "pulse_behind", lambda key, write: write() and True)       # written at once, for the test
    band = {"b": ("band A",)}
    monkeypatch.setattr(research_routes, "mood_key", lambda indices, is_open: band["b"])
    first = json.loads(research_routes.pulse_ai("US", "", False, {"id": "pro"}).body)              # 14:12: band A's read
    band["b"] = ("band B",)
    research_routes.pulse_ai("US", "", False, {"id": "basic"})                                     # 14:34: band B's read written
    newer = json.loads(research_routes.pulse_ai("US", "", False, {"id": "basic"}).body)
    band["b"] = ("band A",)                                                                         # 14:50: back to band A
    again = json.loads(research_routes.pulse_ai("US", "", False, {"id": "pro"}).body)
    assert first["generated_at"] < newer["generated_at"] == again["generated_at"] and again["tone"] == newer["tone"]


# ---------- LIVE13A-030: the day's two last counts are labelled apart ----------
def test_after_the_close_the_count_at_the_closing_prices_is_said_apart_from_the_1530_round():
    from app.intel import mood
    today = {"day": "2026-11-17", "adv": {"value": 261, "prev": 250}, "dec": {"value": 238, "prev": 249}, "unch": {"value": 1, "prev": 1},
             "stocks": {"value": 500}, "pct20": {"value": 74.8}, "pct50": {"value": 57.4}, "pct200": {"value": 50.0}}
    before = mood.breadth_block(today, {"adv": 125, "dec": 374, "unch": 1, "pct50": 50.0, "at": "15:30", "close": False}, "NIFTY 500", "2026-11-18")
    after = mood.breadth_block(today, {"adv": 123, "dec": 376, "unch": 1, "pct50": 50.0, "at": "15:30", "close": True}, "NIFTY 500", "2026-11-18")
    line = lambda b: next(x for x in mood.lines_of({"breadth": b, "is_open": False, "region": "IN"}) if "rose and" in x)      # noqa: E731
    assert "125 of 500 NIFTY 500 stocks rose and 374 fell on" in line(before) and "(the 15:30 IST count, before the closing prices)" in line(before)
    assert "123 of 500 NIFTY 500 stocks rose and 376 fell on" in line(after) and "(the count at the closing prices)" in line(after)
    assert before["at_close"] is False and after["at_close"] is True


# ---------- LIVE13A-016: a Briefs list line adds a fact to its title ----------
def test_a_briefs_line_that_was_only_the_index_moves_says_the_briefs_next_fact():
    from app.newsletter.write import other_fact, without_moves
    idx = [{"name": "NIFTY 50", "change_pct": -0.61}, {"name": "SENSEX", "change_pct": -0.39}, {"name": "NIFTY BANK", "change_pct": -0.79}]
    only = "NIFTY 50 −0.61%; SENSEX −0.39%; NIFTY BANK −0.79% today."
    rot = [{"title": "Indices", "items": [{"text": "NIFTY 50: 25,387.40"}]}, {"title": "Sector rotation", "items": [{"text": "a"}, {"text": "b"}]}]
    assert without_moves(only, idx, rot) == "2 sectors moved to another quadrant on the rotation chart."
    scan = [{"title": "Newly matched Stage 2 + Supertrend today (NIFTY 500)", "items": [{"text": "x"}]}]
    assert without_moves(only, idx, scan) == "1 stock from the NIFTY 500 newly matched the Stage 2 + Supertrend rule."
    heads = [{"title": "Headlines", "items": [{"text": "Sensex slips as IT stocks fall"}]}]
    assert without_moves(only, idx, heads) == "In the headlines: Sensex slips as IT stocks fall."
    assert without_moves(only, idx, []) == only and other_fact(None) is None           # nothing else in it: the moves stay (LIVE12B-025)


# ---------- LIVE13A-027: a call held this morning is under Held, not Coming up ----------
def test_todays_calls_already_held_move_from_coming_up_to_held(monkeypatch):
    from datetime import date as D
    from app import concalls as C, db
    from tests.test_f5_concalls import seed
    store = {}
    monkeypatch.setattr(db, "get_setting", lambda k: store.get(k))
    monkeypatch.setattr(db, "set_setting", lambda k, v: store.__setitem__(k, v))
    seed(store, D(2026, 11, 18))
    doc = json.loads(store[C.KEY])
    doc["events"] += [{"id": "SBIN|2026-11-18|meet", "symbol": "SBIN", "name": "State Bank", "date": "2026-11-18", "type": "meet", "time": "09:00", "tz": "IST",
                       "filed": "2026-11-16T18:00", "links": []},
                      {"id": "AZAD|2026-11-18|call", "symbol": "AZAD", "name": "Azad", "date": "2026-11-18", "type": "call", "time": "06:30", "tz": None,
                       "filed": "2026-11-16T18:00", "links": []},
                      {"id": "LATE|2026-11-18|call", "symbol": "LATE", "name": "Late Co", "date": "2026-11-18", "type": "call", "time": "16:00", "tz": "IST",
                       "filed": "2026-11-16T18:00", "links": []}]
    store[C.KEY] = json.dumps(doc)
    C.forget()
    now = datetime(2026, 11, 18, 9, 17, tzinfo=timezone.utc)                # 14:47 IST
    up = [r["symbol"] for r in C.view("IN", today=D(2026, 11, 18), now=now)["rows"]]
    assert "SBIN" not in up and "AZAD" not in up and "LATE" in up
    held = [r["symbol"] for r in C.view("IN", when="past", today=D(2026, 11, 18), now=now)["rows"]]
    assert held[:2] == ["SBIN", "AZAD"] or set(held[:2]) == {"SBIN", "AZAD"}


# ---------- LIVE13A-022: every US IPO row says its exchange ----------
def test_a_us_ipo_row_without_an_exchange_takes_the_one_its_sec_filing_list_names():
    from app import ipo
    class Sec:
        asked = []

        def filings(self, cik, ttl=0):
            self.asked.append(cik)
            return {"cik": cik, "exchanges": {"1001": ["Nasdaq"], "1002": ["NYSE"]}.get(cik, []), "filings": {}}
    rows = [{"id": "us-sec-1001", "market": "US", "name": "Aspen Co", "exchange": None},
            {"id": "us-x", "market": "US", "name": "Bio Co", "cik": "1002", "exchange": None},
            {"id": "us-y", "market": "US", "name": "Wide Co", "exchange": "NASDAQ Global"},
            {"id": "in-z", "market": "IN", "name": "Indian Co", "exchange": None}]
    sec, problems = Sec(), []
    assert ipo.fill_exchanges(rows, sec, problems) == 2
    assert [r["exchange"] for r in rows] == ["NASDAQ", "NYSE", "NASDAQ Global", None] and sec.asked == ["1001", "1002"] and not problems
