"""Market breadth while the market is open: live counts worked out by hand on the small made-up market, only while the
market is open, paced batched quotes, today's points stored and restarted each day, the page's three states, the daily
numbers left alone, and facts-only wording."""
import json
from datetime import datetime, timezone

import pytest

from app import breadth, breadth_live, db
from tests.fake_db import headers
from tests.test_breadth import ADVICE, IST_OPEN, PROVIDERS, cut, market, mem, paid, runner, w  # noqa: F401  (fixtures)

OPEN = datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc)            # Thursday 1 Oct 2026, 10:30 IST
SAT = datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc)
EVENING = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)        # 18:30 IST, closed


def quotes(up=1005.0, down=95.0, flat=105.0):
    return {"UP": {"price": up, "prev_close": 999.0}, "DOWN": {"price": down, "prev_close": 101.0},
            "FLAT": {"price": flat, "prev_close": 105.0}, "NIFTY 500": {"price": 24000.5, "prev_close": 23900.0}}


def live(mem, q=None, ready=True, calls=None, rebuild=None):
    def quote(syms):
        if calls is not None:
            calls.append(list(syms))
        if isinstance(q, Exception):
            raise q
        return q if q is not None else quotes()
    return breadth_live.Live(quote, lambda: ready, rebuild, sleep=lambda s: None, pause=0)


def with_base(mem):
    runner().run("IN", IST_OPEN)                                    # the daily run stores each stock's finished days
    assert breadth.load_base("IN")["day"] == "2026-09-30"


def test_daily_run_stores_each_stocks_finished_days(mem):
    with_base(mem)
    b = breadth.load_base("IN")["stocks"]
    assert set(b) == {"UP", "DOWN", "FLAT"}
    assert b["UP"][0] == 999.0 and b["UP"][1] >= 200
    assert b["UP"][2] == sum(range(999 - 18, 1000))                 # the last 19 closes
    short = [{"t": "2026-09-29T00:00:00+05:30", "c": 2.0}, {"t": "2026-09-30T00:00:00+05:30", "c": 1.0}]
    assert breadth.base_row(short) == [1.0, 2, None, None, None]
    assert breadth.base_row([]) is None


def test_live_counts_by_hand(mem):
    with_base(mem)
    res = live(mem).round("IN", OPEN)
    assert res["ok"] and res["quoted"] == 3
    v = breadth_live.view("nifty500", OPEN)
    assert v["state"] == "live" and v["as_of"] == "10:30" and v["every_minutes"] == 15
    # UP 1005 vs 999 up, DOWN 95 vs 101 down, FLAT 105 vs 105 unchanged
    assert [v["latest"][k] for k in ("adv", "dec", "unch")] == [1, 1, 1]
    # today's price counts as the latest close: UP above its 20/50/200 averages, DOWN below, FLAT above its 20 and 50
    # (105 against 100.5 and 100.1) and above its 200 (105 against 100.025)
    assert (v["latest"]["a20"], v["latest"]["n20"]) == (2, 3)
    assert (v["latest"]["a50"], v["latest"]["n50"]) == (2, 3)
    assert (v["latest"]["a200"], v["latest"]["n200"]) == (2, 3)
    assert v["latest"]["pct50"] == 66.67 and v["latest"]["idx"] == 24000.5


def test_average_uses_todays_price_as_the_latest_close():
    base = {"S": [100.0, 30, 1900.0, None, None]}                  # last 19 closes sum to 1900 (mean 100)
    assert breadth_live.count(base, {"S": {"price": 110.0, "prev_close": 100.0}}, ["S"])["a20"] == 1
    assert breadth_live.count(base, {"S": {"price": 99.0, "prev_close": 100.0}}, ["S"])["a20"] == 0
    c = breadth_live.count(base, {"S": {"price": 110.0, "prev_close": 100.0}}, ["S"])
    assert c["n50"] == 0 and c["n200"] == 0                         # not enough closes: left out, not counted below


def test_bad_quotes_are_left_out():
    base = {"A": [10.0, 5, None, None, None]}
    c = breadth_live.count(base, {"A": {"price": None}, "B": {"price": 5.0, "prev_close": 0}, "C": {"price": "x"}}, ["A", "B", "C", "Z"])
    assert c["adv"] == c["dec"] == c["unch"] == 0
    # no quoted previous close: the stored last close stands in
    assert breadth_live.count(base, {"A": {"price": 11.0}}, ["A"])["adv"] == 1


def test_only_while_the_market_is_open():
    assert breadth_live.is_open("IN", OPEN)
    assert not breadth_live.is_open("IN", SAT) and not breadth_live.is_open("IN", EVENING)
    assert not breadth_live.is_open("IN", datetime(2026, 10, 1, 3, 30, tzinfo=timezone.utc))     # 09:00 IST
    assert not breadth_live.is_open("IN", datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc))      # 2 Oct: market holiday
    assert not breadth_live.is_open("US", OPEN)
    assert breadth_live.view("nifty500", EVENING) is None and breadth_live.view("us_large", OPEN) is None


def test_job_runs_a_round_every_fifteen_minutes_only_when_open(mem, monkeypatch):
    with_base(mem)
    calls = []
    lv = live(mem, calls=calls)
    job = breadth_live.LiveJob(lv)
    assert job.tick(SAT) == 0 and not calls
    assert job.tick(OPEN) == 1 and len(calls) == 1
    assert job.tick(OPEN) == 0 and len(calls) == 1                  # a quarter of an hour hasn't passed
    t = __import__("time").time()
    monkeypatch.setattr(breadth_live.time, "time", lambda: t + 16 * 60)
    assert job.tick(OPEN.replace(minute=16)) == 1 and len(calls) == 2
    assert len(breadth_live.load("nifty500", "2026-10-01")["points"]) == 2


def test_quotes_are_batched_and_paced(mem, monkeypatch):
    with_base(mem)
    monkeypatch.setattr(breadth_live, "BATCH", 2)
    pauses, calls = [], []
    lv = live(mem, calls=calls)
    lv.sleep, lv.pause = pauses.append, 0.6
    lv.round("IN", OPEN)
    assert [len(c) for c in calls] == [2, 2, 2, 1] and pauses == [0.6] * 3    # 3 stocks and 4 indices, one pause between calls


def test_no_live_prices_says_so_and_keeps_the_last_close(mem):
    with_base(mem)
    res = live(mem, ready=False).round("IN", OPEN)
    assert res["ok"] is False
    v = breadth_live.view("nifty500", OPEN, ready=False)
    assert v["state"] == "unavailable" and v["points"] == [] and "last close" in v["message"]
    assert "available" in v["message"] and not PROVIDERS.search(v["message"])
    assert breadth.view("nifty500")["today"]["adv"]["value"] == 2        # the daily numbers stand
    assert breadth_live.status()["IN"]["error"]


def test_a_failed_round_keeps_todays_earlier_points_then_goes_stale(mem):
    with_base(mem)
    live(mem).round("IN", OPEN)
    res = live(mem, q=RuntimeError("down")).round("IN", OPEN.replace(minute=15))
    assert res["ok"] is False
    assert breadth_live.view("nifty500", OPEN.replace(minute=15))["state"] == "live"
    late = OPEN.replace(hour=7)                                          # 12:30 IST: the 10:30 point is two hours old
    v = breadth_live.view("nifty500", late)
    assert v["state"] == "unavailable" and "stopped updating after 10:30" in v["message"] and v["points"]
    assert live(mem, q={}).round("IN", OPEN)["ok"] is False             # nothing came back: no point added


def test_a_new_day_starts_afresh(mem):
    with_base(mem)
    live(mem).round("IN", OPEN)
    assert len(breadth_live.load("nifty500", "2026-10-01")["points"]) == 1
    assert breadth_live.load("nifty500", "2026-10-05")["points"] == []


def test_missing_finished_days_are_rebuilt_first(mem):
    built = []

    for g in breadth.GROUPS:
        mem[breadth.MEMBERS_KEY + g] = json.dumps(["UP", "DOWN", "FLAT"])
    data = market()

    def rebuild(region, now):
        built.append(region)
        breadth_live.rebuild_base(lambda r, sym, d: cut(data[sym], d), region, now, gap=0)

    res = live(mem, rebuild=rebuild).round("IN", OPEN)
    assert built == ["IN"] and res["ok"]
    assert breadth_live.view("nifty500", OPEN)["latest"]["adv"] == 1


def test_the_daily_close_numbers_are_untouched(mem):
    with_base(mem)
    before = mem[breadth.HIST_KEY + "nifty500"]
    live(mem).round("IN", OPEN)
    assert mem[breadth.HIST_KEY + "nifty500"] == before


def test_wording_is_facts_and_no_provider():
    src = open(breadth_live.__file__).read()
    msgs = " ".join(m for m in src.split('"') if " " in m and len(m) > 25 and "\n" not in m)
    assert not PROVIDERS.search(msgs.replace("data login", "")) and not ADVICE.search(msgs)


def test_page_carries_the_live_card(w, monkeypatch):
    paid(monkeypatch)
    from app import main
    monkeypatch.setattr(breadth_live, "is_open", lambda region, now: region == "IN")
    c, h = w["client"], headers("pro-token")
    v = c.get("/invest/breadth?group=nifty500", headers=h).json()
    assert v["live"]["state"] == "unavailable"                         # nothing stored yet today
    brief = c.get("/invest/breadth?group=nifty500&brief=true", headers=h).json()
    assert brief["live"] is None
    us = c.get("/invest/breadth?group=us_large", headers=h).json()
    assert us["live"] is None
    assert c.get("/admin/breadth", headers=headers("admin-token")).json()["live"] is not None
    assert not PROVIDERS.search(json.dumps(v))
