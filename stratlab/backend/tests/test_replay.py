"""Chart replay practice: how practice orders fill (at the close, stops and targets on later candles, gaps, both in one
candle, flips, averaging, the end), charges at the published rates, hidden sessions, the API (start, random, finish into
the journal as practice, the journal's real/practice switch, discard), plan gates and bad input.

Also writes frontend/unit/fixtures/replay.json: the page's own running simulation (src/lib/replay.ts) is checked
against these answers by unit/replay.test.mjs."""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from app import db, journal as J, main, replay as R
from app.config import settings
from app.engine import costs as C
from tests import world

PRO, FREE, BASIC = world.headers("pro-token"), world.headers("free-token"), world.headers("basic-token")
FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "unit" / "fixtures" / "replay.json"


def bar(t, o, h, l, c):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": 1000}


def day_bars(n=12, start=100.0):
    """Daily candles on weekdays from 2 Mar 2026, each rising 1 from the last close."""
    out, d, p = [], date(2026, 3, 2), start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(bar(f"{d.isoformat()}T00:00:00+05:30", p, p + 2, p - 2, p + 1))
            p += 1
        d += timedelta(days=1)
    return out


def sim(bars, orders, first=1, cursor=None, kind="flat", step=1.0, brokerage=0.0, close_at_end=True):
    cursor = len(bars) - 1 if cursor is None else cursor
    return R.simulate(bars, R.check_orders(orders, first, cursor), first, cursor, kind, step, brokerage, close_at_end)


# ---------- fills ----------
def test_an_order_fills_at_the_close_of_the_candle_showing():
    b = day_bars()
    got = sim(b, [{"i": 2, "action": "long", "qty": 10}, {"i": 5, "action": "flat"}])
    t, = got["trades"]
    assert (t["side"], t["qty"], t["entry"], t["exit"], t["why"]) == ("long", 10, b[2]["c"], b[5]["c"], "Flat")
    assert t["gross"] == pytest.approx(30) and t["charges"] == 0 and t["net"] == pytest.approx(30)
    assert [f["i"] for f in got["fills"]] == [2, 5]


def test_a_stop_works_from_the_next_candle_and_fills_at_a_gap_open():
    b = day_bars()
    b[4] = bar(b[4]["t"], 96, 97, 90, 95)                   # gaps down through the stop
    got = sim(b, [{"i": 2, "action": "long", "qty": 5}, {"i": 2, "action": "stop", "price": 99}])
    t, = got["trades"]
    assert t["why"] == "Stop" and t["exit"] == 96 and t["exit_i"] == 4      # the open, below the stop
    b2 = day_bars()
    b2[4] = bar(b2[4]["t"], 104, 105, 98, 103)              # trades through the stop after opening above it
    t2, = sim(b2, [{"i": 2, "action": "long", "qty": 5}, {"i": 2, "action": "stop", "price": 99}])["trades"]
    assert t2["exit"] == 99


def test_a_stop_placed_on_a_candle_isnt_hit_by_that_candle():
    b = day_bars()
    # candle 2's low (100) is below 100.5, but the stop only works from candle 3, whose low is 101
    got = sim(b, [{"i": 2, "action": "long", "qty": 1}, {"i": 2, "action": "stop", "price": 100.5}], close_at_end=False)
    assert not got["trades"] and got["position"]["stop"] == 100.5


def test_target_and_both_in_one_candle_takes_the_stop():
    b = day_bars()
    t, = sim(b, [{"i": 2, "action": "long", "qty": 2}, {"i": 2, "action": "target", "price": 106}])["trades"]
    assert t["why"] == "Target" and t["exit"] == 106 and t["exit_i"] == 4       # candle 4: 104..108
    b[4] = bar(b[4]["t"], 104, 110, 95, 100)
    t, = sim(b, [{"i": 2, "action": "long", "qty": 2}, {"i": 2, "action": "stop", "price": 99}, {"i": 2, "action": "target", "price": 106}])["trades"]
    assert t["why"] == "Stop" and t["exit"] == 99


def test_short_stops_and_targets_mirror():
    b = day_bars()
    t, = sim(b, [{"i": 2, "action": "short", "qty": 3}, {"i": 2, "action": "stop", "price": 106.5}])["trades"]
    assert t["side"] == "short" and t["why"] == "Stop" and t["exit"] == 106.5 and t["gross"] == pytest.approx(-3 * (106.5 - 103))
    b2 = day_bars()
    b2[3] = bar(b2[3]["t"], 103, 104, 97, 98)
    t, = sim(b2, [{"i": 2, "action": "short", "qty": 3}, {"i": 2, "action": "target", "price": 99}])["trades"]
    assert t["why"] == "Target" and t["exit"] == 99 and t["gross"] == pytest.approx(12)


def test_adding_averages_and_a_bigger_order_the_other_way_flips():
    b = day_bars()
    got = sim(b, [{"i": 1, "action": "long", "qty": 10}, {"i": 3, "action": "long", "qty": 10}, {"i": 5, "action": "short", "qty": 30},
                  {"i": 7, "action": "flat"}])
    long_, short = got["trades"]
    assert long_["qty"] == 20 and long_["entry"] == pytest.approx((102 * 10 + 104 * 10) / 20) and long_["exit"] == 106
    assert short["side"] == "short" and short["qty"] == 10 and short["entry"] == 106 and short["exit"] == 108
    assert short["gross"] == pytest.approx(-20)


def test_a_partial_exit_stays_one_trade_until_flat():
    b = day_bars()
    t, = sim(b, [{"i": 1, "action": "long", "qty": 10}, {"i": 3, "action": "short", "qty": 4}, {"i": 6, "action": "flat"}])["trades"]
    assert t["qty"] == 10 and t["exit"] == pytest.approx((104 * 4 + 107 * 6) / 10) and t["fills"] == 3


def test_open_at_the_end_closes_at_the_last_candle_shown():
    b = day_bars()
    t, = sim(b, [{"i": 1, "action": "long", "qty": 1}], cursor=6)["trades"]
    assert t["why"] == "End of replay" and t["exit"] == b[6]["c"]
    got = sim(b, [{"i": 1, "action": "long", "qty": 1}, {"i": 1, "action": "target", "price": 150}], cursor=6, close_at_end=False)
    assert got["position"]["unrealised"] == pytest.approx(b[6]["c"] - b[1]["c"]) and got["position"]["target"] == 150


def test_orders_that_do_nothing_are_listed():
    b = day_bars()
    got = sim(b, [{"i": 1, "action": "stop", "price": 90}, {"i": 2, "action": "long", "qty": 1}, {"i": 2, "action": "stop", "price": 200},
                  {"i": 2, "action": "long", "qty": 0.4}], step=1.0)
    assert [s["why"] for s in got["skipped"]] == ["No position", "On the wrong side of the price", "Under one lot"]


def test_lots_round_down_to_the_step():
    b = day_bars()
    t, = sim(b, [{"i": 1, "action": "long", "qty": 140}, {"i": 2, "action": "flat"}], step=65.0)["trades"]
    assert t["qty"] == 130


def test_charges_at_the_published_rates_intraday_or_delivery():
    b = day_bars()
    t, = sim(b, [{"i": 1, "action": "long", "qty": 100}, {"i": 4, "action": "flat"}], kind="in_eq", brokerage=0)["trades"]
    want = C.total(C.order_costs("in_eq", "buy", 100, 102, 0)) + C.total(C.order_costs("in_eq", "sell", 100, 105, 0))
    assert t["charges"] == pytest.approx(want) and t["net"] == pytest.approx(300 - want)
    intra = [bar(f"2026-03-02T09:{15 + 5 * i:02d}:00+05:30", 100 + i, 102 + i, 99 + i, 101 + i) for i in range(8)]
    t, = sim(intra, [{"i": 1, "action": "long", "qty": 100}, {"i": 4, "action": "flat"}], kind="in_eq", brokerage=20)["trades"]
    want = C.total(C.order_costs("in_eq_mis", "buy", 100, 102, 20)) + C.total(C.order_costs("in_eq_mis", "sell", 100, 105, 20))
    assert t["charges"] == pytest.approx(want)


def test_bad_orders_are_refused():
    for bad in ([{"i": 1, "action": "pump", "qty": 1}], [{"i": 99, "action": "long", "qty": 1}], [{"i": 3, "action": "long", "qty": 1}, {"i": 2, "action": "flat"}],
                [{"i": 1, "action": "long", "qty": -1}], [{"i": 1, "action": "long", "qty": float("nan")}], [{"i": 1, "action": "stop"}],
                [{"i": True, "action": "flat"}], ["x"], "not a list", [{"i": 1, "action": "long", "qty": True}]):
        with pytest.raises(R.ReplayError):
            R.check_orders(bad, 1, 5)
    with pytest.raises(R.ReplayError):
        R.check_orders([{"i": 1, "action": "flat"}] * (R.MAX_ORDERS + 1), 1, 5)


def test_rates_as_straight_lines_match_the_cost_model():
    r = R.rates("in_eq", 20)
    for k in ("in_eq", "in_eq_mis"):
        for side in ("buy", "sell"):
            for q, p in ((10, 1500.0), (1, 99.5), (2500, 3.2)):
                assert r[k]["flat"] + r[k][side] * q * p == pytest.approx(C.total(C.order_costs(k, side, q, p, 20)), rel=1e-9)
    assert R.rates("flat", 20) == {"flat": {"buy": 0.0, "sell": 0.0, "flat": 0.0}}


def test_hidden_dates_are_sequential_weekdays_from_2000():
    b = [bar("2026-03-06T09:15:00+05:30", 1, 1, 1, 1), bar("2026-03-06T09:20:00+05:30", 1, 1, 1, 1), bar("2026-03-09T09:15:00+05:30", 1, 1, 1, 1),
         bar("2026-03-10T09:15:00+05:30", 1, 1, 1, 1)]
    got = R.mask(b)
    assert [x["t"] for x in got] == ["2000-01-03T09:15:00+05:30", "2000-01-03T09:20:00+05:30", "2000-01-04T09:15:00+05:30",
                                     "2000-01-05T09:15:00+05:30"]
    fri = R.mask([bar(f"2026-03-0{d}T00:00:00", 1, 1, 1, 1) for d in range(2, 10) if date(2026, 3, d).weekday() < 5])
    assert fri[4]["t"][:10] == "2000-01-07" and fri[5]["t"][:10] == "2000-01-10"        # Friday, then Monday


def test_the_window_needs_history_on_both_sides():
    b = day_bars(400)
    win, first = R.window(b, "1d", date.fromisoformat(b[250]["t"][:10]))
    assert first == R.CONTEXT["1d"] and win[first]["t"] == b[250]["t"] and len(win) == R.CONTEXT["1d"] + 150
    with pytest.raises(R.ReplayError):
        R.window(b, "1d", date.fromisoformat(b[395]["t"][:10]))           # too few candles to play
    with pytest.raises(R.ReplayError):
        R.window(b, "1d", date.fromisoformat(b[10]["t"][:10]))            # too little before


def test_write_the_page_fixture():
    """Cases for the page's own simulation (frontend/src/lib/replay.ts), with the answers from this file."""
    b = day_bars(14)
    b[4] = bar(b[4]["t"], 96, 97, 90, 95)
    intra = [bar(f"2026-03-02T09:{15 + 5 * i:02d}:00+05:30", 100 + i, 102 + i, 99 + i, 101 + i) for i in range(8)] + \
            [bar(f"2026-03-03T09:{15 + 5 * i:02d}:00+05:30", 110 + i, 112 + i, 109 + i, 111 + i) for i in range(6)]
    cases = []
    specs = [
        ("fills, a gap through a stop", b, [{"i": 1, "action": "long", "qty": 10}, {"i": 1, "action": "stop", "price": 99}], 1, 12, "in_eq", 1.0, 0.0),
        ("target, flip and averaging", day_bars(14), [{"i": 1, "action": "long", "qty": 10}, {"i": 2, "action": "long", "qty": 5},
                                                     {"i": 3, "action": "target", "price": 108}, {"i": 7, "action": "short", "qty": 4},
                                                     {"i": 8, "action": "stop", "price": 115}, {"i": 9, "action": "cancel_stop"},
                                                     {"i": 11, "action": "flat"}], 1, 13, "in_fut", 1.0, 20.0),
        ("intraday shares and one held overnight", intra, [{"i": 1, "action": "long", "qty": 100}, {"i": 4, "action": "flat"},
                                                           {"i": 6, "action": "short", "qty": 50}, {"i": 9, "action": "long", "qty": 50}],
         1, 13, "in_eq", 1.0, 20.0),
        ("lots, skipped orders, open at the end", day_bars(14), [{"i": 1, "action": "stop", "price": 50}, {"i": 2, "action": "long", "qty": 140},
                                                                 {"i": 2, "action": "target", "price": 90}, {"i": 3, "action": "target", "price": 200}],
         1, 10, "in_fut", 65.0, 20.0),
        ("crypto fees", day_bars(14), [{"i": 1, "action": "short", "qty": 0.5}, {"i": 6, "action": "long", "qty": 0.5}], 1, 13, "crypto", 0.0001, 0.0),
    ]
    for name, bars, orders, first, cursor, kind, step, brk in specs:
        o = R.check_orders(orders, first, cursor)
        for end in (True, False):
            got = R.simulate(bars, o, first, cursor, kind, step, brk, close_at_end=end)
            cases.append({"name": name, "bars": bars, "orders": orders, "first": first, "cursor": cursor, "kind": kind, "step": step,
                          "brokerage": brk, "rates": R.rates(kind, brk), "close_at_end": end,
                          "want": {"trades": got["trades"], "position": got["position"], "skipped": [s["why"] for s in got["skipped"]]}})
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps({"cases": cases}, indent=1) + "\n", encoding="utf-8")
    assert len(cases) == 10 and any(c["want"]["position"] for c in cases)


# ---------- the API ----------
@pytest.fixture
def w(monkeypatch):
    built = world.build(monkeypatch)
    J._paired.clear()
    yield built
    J._paired.clear()
    built["close"]()


def payments_live(monkeypatch):
    for k, v in (("RAZORPAY_KEY_ID", "rzp_live_x"), ("RAZORPAY_KEY_SECRET", "s"), ("RAZORPAY_PLAN_BASIC", "b"), ("RAZORPAY_PLAN_PRO", "p")):
        monkeypatch.setattr(settings, k, v)


def reliance() -> str:
    return main.markets.provider("IN").equity("RELIANCE")["id"]


def start(c, headers=PRO, **kw):
    body = {"instrument": reliance(), "tf": "1d", "start": (date.today() - timedelta(days=500)).isoformat(), **kw}
    return c.post("/trade/replay", headers=headers, json=body)


def test_start_play_and_finish_into_the_journal(w):
    c = w["client"]
    r = start(c)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["symbol"] == "RELIANCE" and not s["hidden"] and s["first"] == R.CONTEXT["1d"] and len(s["bars"]) == s["first"] + R.PLAY["1d"]
    assert s["rates"]["in_eq"]["flat"] == 0 and s["brokerage"] == 0          # daily shares: the journal's delivery brokerage
    assert s["rates"]["in_eq"]["buy"] == pytest.approx(C.total(C.order_costs("in_eq", "buy", 1, 1e6, 0)) / 1e6)
    f = s["first"]
    orders = [{"i": f - 1, "action": "long", "qty": 10}, {"i": f + 5, "action": "flat"}, {"i": f + 6, "action": "short", "qty": 5}]
    r = c.post(f"/trade/replay/{s['id']}/finish", headers=PRO, json={"cursor": f + 20, "orders": orders})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["saved"] == 2 and out["summary"]["n"] == 2 and out["reveal"]["symbol"] == "RELIANCE" and out["bars"] is None
    assert [t["why"] for t in out["trades"]] == ["Flat", "End of replay"]
    j = c.get("/trade/journal", headers=PRO).json()
    practice = [t for t in j["trades"] if t["src"] == "practice"]
    assert len(practice) == 2 and j["practice_count"] == 2 and all(t["note"]["tag"] == "Practice" for t in practice)
    assert practice[-1]["entry_t"] == s["bars"][f - 1]["t"][:10]            # the real date, no time for a daily candle
    assert practice[-1]["charges"] == pytest.approx(out["trades"][0]["charges"], abs=0.01)
    assert c.get(f"/trade/replay/{s['id']}", headers=PRO).status_code == 404          # finished: gone
    assert c.get("/trade/replay", headers=PRO).json()["practice"]["n"] == 2
    # the journal's switch: real trades only, practice only, both
    c.post("/trade/journal/trades", headers=PRO, json={"symbol": "INFY", "side": "long", "entry_date": "2026-03-02", "exit_date": "2026-03-03",
                                                       "qty": 1, "entry_price": 10, "exit_price": 11})
    base = {"capital": None, "brokerage_delivery": 0, "brokerage_other": 20}
    assert c.put("/trade/journal/settings", headers=PRO, json={**base, "show": "real"}).json()["count"] == 1
    assert c.get("/trade/journal/brief", headers=PRO).json()["count"] == 1               # practice never counts on the Trade home
    v = c.put("/trade/journal/settings", headers=PRO, json={**base, "show": "practice"}).json()
    assert v["count"] == 2 and v["show"] == "practice" and v["verdict"]["checks"]
    assert c.put("/trade/journal/settings", headers=PRO, json={**base, "capital": 100000}).json()["show"] == "practice"   # kept
    assert c.put("/trade/journal/settings", headers=PRO, json={**base, "show": "everything"}).status_code == 422
    v = c.delete(f"/trade/journal/trades/{practice[0]['id']}", headers=PRO).json()
    assert v["practice_count"] == 1 and len(J.load("u-pro")["practice"]) == 1


def test_a_random_replay_hides_the_symbol_and_dates_until_the_end(w):
    c = w["client"]
    r = c.post("/trade/replay", headers=PRO, json={"random": True, "tf": "1d"})
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["hidden"] and s["symbol"] is None and s["name"] is None and s["label"] == "Hidden symbol and date"
    assert s["bars"][0]["t"].startswith("2000-01-03")
    stored = R.get("u-pro", s["id"])
    assert stored["inst"]["symbol"] in R_POOL() and not stored["bars"][0]["t"].startswith("2000")
    listed = c.get("/trade/replay", headers=PRO).json()["sessions"]
    assert listed[0]["label"] == "Hidden symbol and date" and stored["inst"]["symbol"] not in json.dumps(listed)
    f = s["first"]
    out = c.post(f"/trade/replay/{s['id']}/finish", headers=PRO, json={"cursor": f + 3, "orders": [{"i": f, "action": "long", "qty": 1}]}).json()
    assert out["reveal"]["symbol"] == stored["inst"]["symbol"] and out["bars"][0]["t"] == stored["bars"][0]["t"]
    assert out["reveal"]["from"] == stored["bars"][f]["t"][:10]


def R_POOL():
    from app.replay_routes import R_POOL as pool
    return pool()


def test_intraday_replay_and_discard(w):
    c = w["client"]
    r = start(c, tf="15m", start=(date.today() - timedelta(days=40)).isoformat())
    assert r.status_code == 200, r.text
    s = r.json()
    assert "T" in s["bars"][s["first"]]["t"] and s["first"] == R.CONTEXT["15m"]
    assert c.delete(f"/trade/replay/{s['id']}", headers=PRO).json() == {"deleted": True}
    assert c.delete(f"/trade/replay/{s['id']}", headers=PRO).status_code == 404


def test_at_most_three_open_and_only_your_own(w):
    c = w["client"]
    ids = [start(c).json()["id"] for _ in range(4)]
    open_ = {x["id"] for x in c.get("/trade/replay", headers=PRO).json()["sessions"]}
    assert open_ == set(ids[1:])                                      # the oldest made way
    assert c.get(f"/trade/replay/{ids[-1]}", headers=BASIC).status_code == 404
    assert c.post(f"/trade/replay/{ids[-1]}/finish", headers=BASIC, json={"cursor": 300, "orders": []}).status_code == 404


def test_bad_input_is_a_4xx(w):
    c = w["client"]
    today = date.today()
    assert start(c, tf="2m").status_code == 422
    assert start(c, start=today.isoformat()).status_code == 400
    assert start(c, start=(today + timedelta(days=3)).isoformat()).status_code == 400
    assert start(c, start=(today - timedelta(days=5)).isoformat()).json()["detail"]["code"] == "too_recent"
    assert start(c, tf="5m", start=(today - timedelta(days=400)).isoformat()).json()["detail"]["code"] == "too_early"
    assert start(c, instrument="IN:999999999").status_code == 404
    assert c.post("/trade/replay", headers=PRO, json={"tf": "1d"}).status_code == 400
    assert c.post("/trade/replay", headers=PRO, json={"instrument": reliance(), "tf": "1d"}).status_code == 400   # no start
    s = start(c).json()
    f = s["first"]
    for body in ({"cursor": 100000, "orders": []}, {"cursor": f, "orders": [{"i": f + 1, "action": "long", "qty": 1}]},
                 {"cursor": f, "orders": [{"i": f, "action": "rm -rf", "qty": 1}]}, {"cursor": f, "orders": [{"i": f, "action": "long", "qty": "1e999"}]}):
        r = c.post(f"/trade/replay/{s['id']}/finish", headers=PRO, json=body)
        assert 400 <= r.status_code < 500, (body, r.text)
    assert c.post(f"/trade/replay/{s['id']}/finish", headers=PRO, json={"cursor": "x"}).status_code == 422
    assert c.get("/trade/replay/" + "z" * 200, headers=PRO).status_code == 404
    assert c.get("/trade/replay").status_code == 401


def test_nothing_saved_when_asked_not_to_or_with_no_trades(w):
    c = w["client"]
    s = start(c).json()
    f = s["first"]
    out = c.post(f"/trade/replay/{s['id']}/finish", headers=PRO, json={"cursor": f + 4, "orders": [{"i": f, "action": "long", "qty": 1}], "save": False}).json()
    assert out["saved"] == 0 and out["summary"]["n"] == 1 and db.get_setting("journal:u-pro") is None
    s = start(c).json()
    assert c.post(f"/trade/replay/{s['id']}/finish", headers=PRO, json={"cursor": s["first"] + 2, "orders": []}).json()["saved"] == 0


def test_plan_gates(w, monkeypatch):
    payments_live(monkeypatch)
    c = w["client"]
    r = start(c, headers=FREE)
    assert r.status_code == 402 and "Basic" in r.json()["detail"]["message"]
    assert c.get("/trade/replay", headers=FREE).json()["allowed"] is False
    assert start(c, headers=BASIC).status_code == 200
    main.kite._load_instruments()
    fut = next(r for r in main.kite._inst if r["type"] == "FUT")
    r = start(c, headers=BASIC, instrument=fut["id"])
    assert r.status_code == 402 and "Pro" in r.json()["detail"]["message"]
    s = start(c, headers=PRO).json()
    monkeypatch.setitem(main.PLANS["pro"], "features", main.PLANS["pro"]["features"] - {"chart_replay"})
    assert c.post(f"/trade/replay/{s['id']}/finish", headers=PRO, json={"cursor": s["first"], "orders": []}).status_code == 402
