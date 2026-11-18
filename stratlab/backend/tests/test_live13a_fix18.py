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
