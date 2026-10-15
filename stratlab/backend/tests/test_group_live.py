"""Paper trading a group: one engine per member, shared slots, a group-wide loss cap, and restarts."""
from datetime import datetime, timezone

import pytest
import time_machine

from app import db, group_live
from tests.test_live_polling import make_manager

STRAT = {"name": "Momentum", "tf": "5m", "side": "long", "entryJoin": "all",
         "entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}], "exit": [],
         "session": {"dailyLossPct": 1},
         "risk": {"capital": 1000000, "riskPct": 1, "maxAlloc": 100, "sl": 50, "sizing": "capital", "perTrade": 100000, "leverage": 1}}


@pytest.fixture(autouse=True)
def pinned_clock():
    """The candles below are dated 12 Oct 2026 from 09:30 UTC; the clock is pinned to that afternoon so they have closed
    whatever the real date and time are."""
    with time_machine.travel(datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc), tick=False):
        yield


def row(state=None):
    return {"id": "g1", "user_id": "u", "name": "Coins", "strategy": STRAT, "started_at": datetime.now(timezone.utc).isoformat(),
            "state": state, "instrument": {"id": "GROUP:custom", "type": "GROUP", "market": "CRYPTO", "maxOpen": 2,
                                           "members": ["CRYPTO:BTC-USD", "CRYPTO:ETH-USD", "CRYPTO:SOL-USD"],
                                           "names": {}}}


def candle(t, c):
    return {"t": t, "o": c, "h": c, "l": c, "c": c, "v": 1}


def test_slots_are_shared_and_the_loss_cap_closes_everything(monkeypatch):
    mgr, _ = make_manager()
    orders = []
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: orders.append(ev))
    s = group_live.GroupLiveSession(mgr, row())
    assert len(s.members) == 3 and s.polled
    a, b, c = s.members
    for m, px in ((a, 100.0), (b, 100.0), (c, 100.0)):
        s._on_candle(m, candle("2999-01-01T10:00:00+00:00", px))
    assert sum(m.engine.qty > 0 for m in s.members) == 2          # max 2 at once
    assert {o["sym"] for o in orders} <= {a.sym, b.sym, c.sym} and all(o["side"] == "buy" for o in orders)
    # a 10% drop on one position is a 10,000 loss: over the 1% (10,000) group cap once costs are counted
    held = [m for m in s.members if m.engine.qty > 0]
    s._on_candle(held[0], candle("2999-01-01T10:05:00+00:00", 90.0))
    assert s.halted and all(m.engine.qty == 0 for m in s.members)
    assert any(o.get("why") == "Daily loss cap" for o in orders)
    s._on_candle(c, candle("2999-01-01T10:10:00+00:00", 100.0))
    assert c.engine.qty == 0                                        # nothing new today
    s._on_candle(c, candle("2999-01-02T10:00:00+00:00", 100.0))
    assert c.engine.qty > 0 and not s.halted                         # a new day


def test_restart_restores_positions(monkeypatch):
    mgr, _ = make_manager()
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    s = group_live.GroupLiveSession(mgr, row())
    s._on_candle(s.members[0], candle("2999-01-01T10:00:00+00:00", 100.0))
    s2 = group_live.GroupLiveSession(mgr, row(s.state()))
    assert s2.members[0].engine.qty == s.members[0].engine.qty > 0
    snap = s2.snapshot()
    assert snap["kind"] == "group" and snap["account"]["open"] == 1 and snap["members"][0]["position"]


def test_manager_attaches_groups_and_polls_a_few_at_a_time(monkeypatch):
    mgr, _ = make_manager()
    s = mgr._attach(row())
    assert mgr.sessions["g1"] is s
    calls = []
    monkeypatch.setattr(s.prov, "closed_candles", lambda inst, tf, since: calls.append(inst["id"]) or [])
    s.on_timer(datetime.now(timezone.utc))
    assert len(calls) == group_live.POLLS_PER_PASS
    monkeypatch.setattr(db, "update_session", lambda *a, **k: None)
    mgr.stop("g1", "test")
    assert "g1" not in mgr.sessions


def fast_row(fast, strat=STRAT):
    r = row()
    r["strategy"] = strat
    r["instrument"] = {**r["instrument"], "fast": fast}
    return r


def test_min_price_and_spread_filters_skip_entries_only_when_the_rules_hold(monkeypatch):
    mgr, _ = make_manager()
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    s = group_live.GroupLiveSession(mgr, fast_row({"minPrice": 150}))
    a = s.members[0]
    s._on_candle(a, candle("2999-01-01T10:00:00+00:00", 100.0))
    assert a.engine.qty == 0 and a.skips["price"] == 1
    s = group_live.GroupLiveSession(mgr, fast_row({"maxSpreadPct": 0.1}))
    a, b, c = s.members
    s._on_candle(a, candle("2999-01-01T10:00:00+00:00", 100.0))            # no order book yet: skipped
    assert a.engine.qty == 0 and a.skips["spread"] == 1
    a.bid, a.ask, a.quote_at = 99.5, 100.5, group_live.time.time()          # 1% wide
    s._on_candle(a, candle("2999-01-01T10:05:00+00:00", 100.0))
    assert a.engine.qty == 0 and a.skips["spread"] == 2
    a.bid, a.ask = 99.98, 100.02                                           # 0.04%: fine
    s._on_candle(a, candle("2999-01-01T10:10:00+00:00", 100.0))
    assert a.engine.qty > 0
    never = {**STRAT, "entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 1e9}}]}
    s = group_live.GroupLiveSession(mgr, fast_row({"maxSpreadPct": 0.1}, never))
    s._on_candle(s.members[0], candle("2999-01-01T10:00:00+00:00", 100.0))
    assert s.members[0].skips["spread"] == 0                               # no signal, nothing counted
    assert s.snapshot()["account"]["skipped"] == {"spread": 0, "price": 0}


def test_fast_entries_use_the_forming_candle(monkeypatch):
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    mgr, _ = make_manager()
    orders = []
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: orders.append(ev))
    s = group_live.GroupLiveSession(mgr, fast_row({"ticks": True}))
    a = s.members[0]
    tick = lambda px, m, sec=0: a.on_tick({"last_price": px, "exchange_timestamp": datetime(2999, 1, 1, 10, m, sec, tzinfo=ist),
                                          "depth": {"buy": [{"price": px - 0.01}], "sell": [{"price": px + 0.01}]}})
    tick(100.0, 1)
    assert a.engine.qty > 0 and orders[-1]["why"] == "Entry rule (live price)" and orders[-1]["px"] >= 100.0
    assert a.bid == 99.99 and a.ask == 100.01
    n = len(orders)
    tick(101.0, 2)
    tick(102.0, 6)                                                          # the 10:00 candle closes: held, no second entry
    assert len(orders) == n and a.engine.qty > 0 and a.bars[-1]["c"] == 101.0
    s2 = group_live.GroupLiveSession(mgr, fast_row({"ticks": False}))
    b = s2.members[0]
    b.on_tick({"last_price": 100.0, "exchange_timestamp": datetime(2999, 1, 1, 10, 1, tzinfo=ist)})
    assert b.engine.qty == 0                                                 # off: waits for the candle to close


EARLY = {**STRAT, "entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 99}},
                            {"l": {"t": "price"}, "op": "lt", "r": {"t": "num", "v": 101}}],
         "session": {"dailyLossPct": 0},
         "risk": {"capital": 1000000, "riskPct": 1, "maxAlloc": 100, "sl": 1, "tgt": 1, "stopType": "points", "sizing": "capital",
                  "perTrade": 100000, "leverage": 1}}


def early_ticks(monkeypatch, prices):
    """Ticks of one member with fast entries on, one per (minute, second, price); returns the member and the orders."""
    mgr, _ = make_manager()
    orders = []
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: orders.append(ev))
    s = group_live.GroupLiveSession(mgr, fast_row({"ticks": True}, EARLY))
    a = s.members[0]
    for m, sec, px in prices:
        tick_at(a, m, sec, px)
    return a, orders


def tick_at(a, minute, sec, px):
    from zoneinfo import ZoneInfo
    a.next_eval = 0                                       # fast entries are throttled to one check per 15 s
    a.on_tick({"last_price": px, "exchange_timestamp": datetime(2999, 1, 1, 10, minute, sec, tzinfo=ZoneInfo("Asia/Kolkata"))})


def test_an_early_entry_is_not_stopped_out_by_the_part_of_its_candle_before_the_fill(monkeypatch):
    # the 10:00 candle opens at 98 and rises to 100: entered at 100.05 with the stop at 99.05, the candle's low of 98
    # is from before the entry
    a, orders = early_ticks(monkeypatch, [(0, 1, 98.0), (0, 20, 100.0), (1, 0, 100.0), (5, 1, 100.2)])
    assert a.engine.qty > 0 and a.bars[-1]["l"] == 98.0       # the 10:00 candle has closed
    assert a.engine.sl == pytest.approx(99.05, abs=0.01) and a.engine.trades == []
    assert [o["side"] for o in orders] == ["buy"]
    # the next candle is judged as usual
    tick_at(a, 6, 0, 99.0)
    tick_at(a, 10, 1, 99.0)
    assert a.engine.qty == 0 and a.engine.trades[-1]["why"] == "Stop loss"


def test_an_early_entry_does_not_hit_a_target_the_candle_reached_before_the_fill(monkeypatch):
    a, orders = early_ticks(monkeypatch, [(0, 1, 105.0), (0, 20, 100.0), (1, 0, 100.0), (5, 1, 100.2)])
    assert a.bars[-1]["h"] == 105.0 and a.engine.qty > 0 and a.engine.trades == []
    assert a.engine.tg == pytest.approx(101.05, abs=0.01) and a.engine.best == pytest.approx(a.engine.entry)
    assert [o["side"] for o in orders] == ["buy"]


def test_the_early_entry_flag_is_kept_over_a_restart_and_cleared_by_the_candle(monkeypatch):
    from app.engine.core import Engine
    a, _ = early_ticks(monkeypatch, [(0, 1, 98.0), (0, 20, 100.0)])
    assert a.engine.early_t == a.builder.cur["start"].isoformat()
    assert Engine(a.s.each, state=a.engine.dump()).early_t == a.engine.early_t
    tick_at(a, 5, 1, 100.0)
    assert a.engine.early_t is None


def test_a_restart_runs_missed_candles_across_the_group_in_time_order(monkeypatch):
    from tests.test_live_polling import bar5, run_threads_now
    mgr, reg = make_manager()
    hist = {iid: [bar5(i) for i in range(40)] for iid in row()["instrument"]["members"]}
    prov = mgr.markets.provider("CRYPTO")
    monkeypatch.setattr(prov, "history", lambda inst, tf, days, ttl=None: list(hist[inst["id"]]))
    run_threads_now(monkeypatch)
    alerts = []
    monkeypatch.setattr(db, "get_profile", lambda uid: {"id": uid})
    monkeypatch.setattr("app.live.alerts_on", lambda p: True)
    monkeypatch.setattr("app.live.notify", lambda p, subj, body, **k: alerts.append((subj, body)))
    monkeypatch.setattr(db, "update_session", lambda *a, **k: None)
    s = group_live.GroupLiveSession(mgr, row())
    a, b, c = s.members
    s._on_candle(a, bar5(40))                                     # BTC opens at 10:00 (the only member stepped)
    assert a.engine.qty > 0
    alerts.clear()
    saved = s.state()
    # down from 10:00: ETH and SOL's 10:00 candles and everyone's 10:05 one closed meanwhile; BTC falls 10% at 10:05
    hist["CRYPTO:BTC-USD"] += [bar5(40), bar5(41, 90.0)]
    for iid in ("CRYPTO:ETH-USD", "CRYPTO:SOL-USD"):
        hist[iid] += [bar5(40), bar5(41)]
    s2 = group_live.GroupLiveSession(mgr, row(saved))
    a, b, c = s2.members
    assert len(a.engine.events) == 2                              # BTC's 10:00 candle isn't run again
    assert [ev["t"] for ev in b.engine.events if ev["side"] == "buy"] == [bar5(40)["t"]]   # the second slot
    assert not c.engine.events                                    # no third slot at 10:00, the cap had hit at 10:05
    assert s2.halted and all(m.engine.qty == 0 for m in s2.members)
    assert {t["why"] for m in (a, b) for t in m.engine.trades} == {"Daily loss cap"}
    assert all(m.bars[-1]["t"] == bar5(41)["t"] for m in s2.members) and a.last_price == 90.0
    assert len(alerts) == 1 and "3 paper trades while offline" in alerts[0][0]


def test_a_split_and_a_dividend_on_two_members_and_a_restart(monkeypatch):
    from app import corp_actions
    from tests.test_live_polling import DIV, SPLIT, corp_events, sbar, stock_world
    beta_div = {**DIV, "id": "BETA|dividend|2026-01-06|dividend", "symbol": "BETA"}
    mgr, srow = stock_world(monkeypatch, [sbar(5, i, 1000.0) for i in range(40)], [SPLIT, beta_div])
    prov = mgr.markets.provider("US")
    monkeypatch.setattr(mgr.markets, "resolve", lambda iid: (prov, {**srow["instrument"], "id": iid, "symbol": iid.split(":")[1]}))
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    grow = {**row(), "instrument": {"id": "GROUP:custom", "type": "GROUP", "market": "US", "maxOpen": 2,
                                    "members": ["US:ACME", "US:BETA"], "names": {}},
            "strategy": {**STRAT, "risk": {**STRAT["risk"], "sl": 1, "slippage": 0, "brokerage": 0}}}
    s = group_live.GroupLiveSession(mgr, grow)
    a, b = s.members
    for m in (a, b):
        s._on_candle(m, sbar(5, 40, 1000.0))
    qa, qb, real = a.engine.qty, b.engine.qty, s.realised()
    assert qa > 0 and qb > 0 and a.engine.sl == 990.0
    s._on_candle(a, sbar(6, 0, 500.0, lo=496.0))
    s._on_candle(b, sbar(6, 0, 995.0))
    assert (a.engine.qty, a.engine.entry, a.engine.sl) == (2 * qa, 500.0, 495.0) and not a.engine.trades
    assert b.engine.qty == qb and s.corp_cash == 5.0 * qb and s.realised() == real + 5.0 * qb
    assert corp_events(a.engine)[0]["why"].startswith(f"Split 1:2 applied: {qa:,} shares at $1,000 are now {2 * qa:,} at $500")
    assert any(e.get("kind") == "corp" for e in s.snapshot()["events"])
    # restarted: neither is applied again, and the dividend stays in the pot
    s2 = group_live.GroupLiveSession(mgr, {**grow, "state": s.state()})
    a2, b2 = s2.members
    s2._on_candle(a2, sbar(6, 1, 500.0))
    s2._on_candle(b2, sbar(6, 1, 995.0))
    assert a2.engine.qty == 2 * qa and a2.engine.entry == 500.0 and len(corp_events(a2.engine)) == 1
    assert b2.engine.qty == qb and s2.corp_cash == 5.0 * qb and len(corp_events(b2.engine)) == 1
    assert group_live.stopped_snapshot({**grow, "status": "stopped", "state": s2.state()})["account"]["realised"] == s2.realised()
    assert corp_actions.paper_region(a2.inst) == "US"


def test_members_are_sized_from_the_shared_pot(monkeypatch):
    # a second position only gets the cash the first leaves free, as in the group backtest
    mgr, _ = make_manager()
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    big = {**STRAT, "session": {}, "risk": {**STRAT["risk"], "perTrade": 600000}}
    s = group_live.GroupLiveSession(mgr, fast_row({}, big))
    a, b, _ = s.members
    s._on_candle(a, candle("2999-01-01T10:00:00+00:00", 100.0))
    s._on_candle(b, candle("2999-01-01T10:00:00+00:00", 100.0))
    assert a.engine.qty * 100 > 590000
    assert 0 < b.engine.qty * 100 <= 1000000 - a.engine.qty * 100 - a.engine.entry_cost
    value, free = s.funds()
    assert abs(value - s.equity()) < 1e-6 and free >= 0


def test_the_engines_open_fill_gate_takes_the_backtests_argument(monkeypatch):
    # the engine asks its gate free_slot(at_open=True) when a pending entry fills at a candle's open (group backtests)
    mgr, _ = make_manager()
    s = group_live.GroupLiveSession(mgr, row())
    assert s.free_slot(at_open=True) is True and s.members[0].engine.gate(at_open=True) is True


def test_a_member_whose_history_fails_at_a_restart_keeps_its_saved_position(monkeypatch):
    from tests.test_live_polling import bar5
    mgr, _ = make_manager()
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    hist = {iid: [bar5(i) for i in range(40)] for iid in row()["instrument"]["members"]}
    down = {"CRYPTO:BTC-USD"}

    def history(inst, tf, days, ttl=None):
        if inst["id"] in down:
            raise RuntimeError("no data")
        return list(hist[inst["id"]])
    prov = mgr.markets.provider("CRYPTO")
    monkeypatch.setattr(prov, "history", history)
    monkeypatch.setattr(prov, "closed_candles", lambda inst, tf, since: [])
    monkeypatch.setattr(prov, "ltp", lambda inst: None)
    down.clear()
    s = group_live.GroupLiveSession(mgr, row())
    s._on_candle(s.members[0], bar5(40))                          # BTC opens
    saved = s.state()
    btc = saved["members"]["CRYPTO:BTC-USD"]
    assert btc["qty"] > 0
    down.add("CRYPTO:BTC-USD")
    s2 = group_live.GroupLiveSession(mgr, row(saved))
    assert [m.inst["id"] for m in s2.members] == ["CRYPTO:ETH-USD", "CRYPTO:SOL-USD"]
    assert s2.state()["members"]["CRYPTO:BTC-USD"] == btc        # written back unchanged
    assert round(s2.equity(), 2) == round(s.equity(), 2)
    s2._on_candle(s2.members[0], bar5(40))
    assert s2.members[0].engine.qty == 0 and not s2.free_slot()  # nothing opens while BTC's position can't be counted
    snap = s2.snapshot()
    assert snap["account"]["open"] == 1 and "BTC" in snap["notice"] and "no new positions open" in snap["notice"]
    assert any(r["id"] == "CRYPTO:BTC-USD" and r["position"] for r in snap["members"])
    s2.on_timer(datetime.now(timezone.utc))
    assert s2.waiting                                             # still down: tried again later
    down.clear()
    s2.next_retry = 0
    s2.on_timer(datetime.now(timezone.utc))
    assert not s2.waiting and s2.members[-1].inst["id"] == "CRYPTO:BTC-USD" and s2.members[-1].engine.qty == btc["qty"]
    assert s2.free_slot() and s2.snapshot()["notice"] is None


def test_a_candles_new_orders_go_out_before_the_loss_caps_closes(monkeypatch):
    mgr, _ = make_manager()
    orders = []
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: orders.append((ev["sym"], ev["side"], ev["why"])))
    s = group_live.GroupLiveSession(mgr, row())
    a, b, _ = s.members
    s._on_candle(a, candle("2999-01-01T10:00:00+00:00", 100.0))
    a.last_price = 90.0                                             # a's open loss is past the cap
    orders.clear()
    s._on_candle(b, candle("2999-01-01T10:05:00+00:00", 100.0))   # b enters on this candle, then the cap closes both
    assert [o[1] for o in orders if o[0] == b.sym] == ["buy", "sell"]
    assert orders[0][:2] == (b.sym, "buy") and {o[2] for o in orders[1:]} == {"Daily loss cap"}


CAP = {**STRAT, "session": {"dailyLossPct": 2.5},
       "risk": {**STRAT["risk"], "perTrade": 1000000, "sl": 50, "slippage": 0, "brokerage": 0}}


def cap_session(monkeypatch, state=None):
    mgr, _ = make_manager()
    orders = []
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: orders.append(ev))
    return mgr, orders, group_live.GroupLiveSession(mgr, {**row(state), "strategy": CAP})


def test_a_loss_carried_overnight_is_not_the_days_loss(monkeypatch):
    """1.8% lost on day 1 and 0.9% more on day 2 is 0.9% today: under the 2.5% cap, though 2.7% from the entry."""
    mgr, orders, s = cap_session(monkeypatch)
    a = s.members[0]
    s._on_candle(a, candle("2999-01-01T10:00:00+00:00", 100.0))
    e = a.engine
    assert e.qty > 0 and e.entry == 100.0
    s._on_candle(a, candle("2999-01-01T10:05:00+00:00", 98.2))                # -1.8% of the pot
    assert not s.halted and e.qty > 0 and -0.8 < s.today() / s.loss_cap < -0.7        # 1.8% of the pot, the entry charges in
    s._on_candle(a, candle("2999-01-02T10:00:00+00:00", 98.2))                # next day, flat
    assert e.day_mark == 98.2 and s.today() == 0
    s._on_candle(a, candle("2999-01-02T10:05:00+00:00", 97.3))                # a further -0.9%
    assert not s.halted and e.qty > 0 and not any(o.get("why") == "Daily loss cap" for o in orders)
    assert -0.4 < s.today() / s.loss_cap < -0.3 and s.snapshot()["account"]["today"] == s.today()
    assert s.realised() + s.open_pnl() < -0.025 * 1000000                       # from the entry it would have tripped it


def test_a_loss_within_the_day_trips_the_cap(monkeypatch):
    mgr, orders, s = cap_session(monkeypatch)
    a = s.members[0]
    s._on_candle(a, candle("2999-01-01T10:00:00+00:00", 100.0))
    s._on_candle(a, candle("2999-01-01T10:05:00+00:00", 97.4))                # -2.6% in the day
    assert s.halted and a.engine.qty == 0 and any(o.get("why") == "Daily loss cap" for o in orders)
    # the same 2.6% carried over midnight: the day's part of it is 0.8%, so a position closed then doesn't trip it
    mgr, orders, s = cap_session(monkeypatch)
    a = s.members[0]
    s._on_candle(a, candle("2999-01-01T10:00:00+00:00", 100.0))
    s._on_candle(a, candle("2999-01-01T10:05:00+00:00", 98.2))
    s._on_candle(a, candle("2999-01-02T10:00:00+00:00", 98.2))
    s._on_candle(a, candle("2999-01-02T10:05:00+00:00", 97.4))                # -0.8% today
    assert not s.halted and a.engine.qty > 0
    s._on_candle(a, candle("2999-01-02T10:10:00+00:00", 95.5))                # -2.7% today
    assert s.halted and a.engine.qty == 0
    assert a.engine.trades[-1]["pnl"] < -0.04 * 1000000 and s.today() <= -s.loss_cap


def test_the_days_loss_survives_a_restart_in_the_middle_of_the_day(monkeypatch):
    mgr, orders, s = cap_session(monkeypatch)
    a = s.members[0]
    for t, px in (("2999-01-01T10:00:00+00:00", 100.0), ("2999-01-01T10:05:00+00:00", 98.2),
                  ("2999-01-02T10:00:00+00:00", 98.2), ("2999-01-02T10:05:00+00:00", 97.3)):
        s._on_candle(a, candle(t, px))
    s.corp_cash, today = 12.0, s.today()
    st = s.state()
    assert st["day_start_corp"] == 0.0 and st["members"][a.inst["id"]]["day_mark"] == 98.2
    mgr, orders, s2 = cap_session(monkeypatch, st)
    a2 = s2.members[0]
    assert (s2.day, a2.engine.day, a2.engine.day_mark, s2.day_start_corp) == ("2999-01-02", "2999-01-02", 98.2, 0.0)
    a2.last_price = 97.3                                                       # the next tick or poll
    assert s2.today() == pytest.approx(today + 12.0) and a2.engine.qty == a.engine.qty
    # -2.0% from the saved mark (-3.8% from the entry): under the cap, as before the restart
    s2._on_candle(a2, candle("2999-01-02T10:10:00+00:00", 96.2))
    assert not s2.halted and a2.engine.qty > 0
    # a stop mid-day keeps the same measure for a member waiting on its history
    waiting = {a2.inst["id"]: {**a2.engine.dump(), "last_price": 96.2, "symbol": a2.sym}}
    assert group_live._saved_today(waiting[a2.inst["id"]], "2999-01-02") == pytest.approx(a2.engine.day_open_pnl(96.2))
    assert group_live._saved_today(waiting[a2.inst["id"]], "2999-01-03") == 0.0
    s2._on_candle(a2, candle("2999-01-02T10:15:00+00:00", 95.4))              # -2.9% from the mark
    assert s2.halted and a2.engine.qty == 0


def test_a_split_moves_the_days_mark_with_the_entry(monkeypatch):
    from tests.test_live_polling import SPLIT, sbar, stock_world
    mgr, srow = stock_world(monkeypatch, [sbar(5, i, 1000.0) for i in range(40)], [SPLIT])
    prov = mgr.markets.provider("US")
    monkeypatch.setattr(mgr.markets, "resolve", lambda iid: (prov, {**srow["instrument"], "id": iid, "symbol": iid.split(":")[1]}))
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    grow = {**row(), "instrument": {"id": "GROUP:custom", "type": "GROUP", "market": "US", "maxOpen": 2,
                                    "members": ["US:ACME", "US:BETA"], "names": {}},
            "strategy": {**STRAT, "session": {"dailyLossPct": 2.5}, "risk": {**STRAT["risk"], "sl": 1, "slippage": 0, "brokerage": 0}}}
    s = group_live.GroupLiveSession(mgr, grow)
    a = s.members[0]
    s._on_candle(a, sbar(5, 40, 1000.0))
    qty, a.engine.day_mark = a.engine.qty, 1000.0           # carried in, marked at the 1,000 it closed at
    a.corp.apply(a.engine, [SPLIT], "2026-01-06")           # 1:2, applied while the day's mark is held
    assert (a.engine.qty, a.engine.entry, a.engine.day_mark) == (2 * qty, 500.0, 500.0) and a.engine.day_open_pnl(500.0) == 0
    s._on_candle(a, sbar(6, 0, 500.0, lo=496.0))            # the day's first candle: nothing counted as a loss
    assert a.engine.day_mark == 500.0 and s.today() == 0 and not s.halted


@pytest.mark.parametrize("side", ["long", "short"])
def test_the_days_dividend_paid_from_the_timer_counts_in_the_days_pnl(monkeypatch, side):
    """The timer pays the day's dividend after midnight, before the day's first candle. That candle started the day with
    the pot's corporate cash, the dividend already in it, as the day's starting point: on the ex-date the price drop
    counted (-1,995 on 997.5 units at 2 a unit) and the dividend that makes up for it didn't. A short's is the mirror."""
    mgr, _ = make_manager()
    monkeypatch.setattr(mgr, "on_order", lambda s, ev: None)
    s = group_live.GroupLiveSession(mgr, {**row(), "strategy": {**STRAT, "side": side}})
    a = s.members[0]
    s._on_candle(a, candle("2999-01-01T10:00:00+00:00", 100.0))
    s._on_candle(a, candle("2999-01-01T23:55:00+00:00", 100.0))
    q, d = a.engine.qty, a.engine.dir
    assert q > 0 and d == (1 if side == "long" else -1)
    D, seen = 2.0, set()

    def new_day(day):                      # as PaperActions.new_day: the day's actions once, the first time it is seen
        if day in seen:
            return None
        seen.add(day)
        return [{"id": "div"}] if day == "2999-01-02" else None
    monkeypatch.setattr(a.corp, "new_day", new_day)
    monkeypatch.setattr(a.corp, "bars", lambda bars, acts: None)
    monkeypatch.setattr(a.corp, "apply", lambda e, acts, day, todo=False: (e.dir * e.qty * D, 1.0))
    a.corp_day("2999-01-02", timer=True)                          # what on_timer does after midnight
    assert s.corp_cash == pytest.approx(d * q * D) and s.day == "2999-01-02"
    s._on_candle(a, candle("2999-01-02T09:00:00+00:00", 100.0 - D))        # opens ex-dividend, D lower
    assert s.today() == pytest.approx(0.0, abs=0.01)
    st = s.state()
    assert st["day"] == "2999-01-02" and st["day_start_corp"] == pytest.approx(0.0)


def test_a_transient_history_failure_resuming_a_group_is_retried_not_stopped(monkeypatch):
    """A 503 loading the members' history made every member fail to load; that read as 'fewer than two instruments have
    enough history', a ValueError, and the group was stopped for good at the first try."""
    from app import leader, live
    from app.data.coinbase import DataError
    mgr, _ = make_manager()
    monkeypatch.setattr(leader, "leading", lambda: True)
    writes = []
    monkeypatch.setattr(live.db, "update_session", lambda sid, **f: writes.append((sid, f)))
    prov = mgr.markets.provider("CRYPTO")
    good = prov.history

    def boom(*a, **k):
        raise DataError("503")
    monkeypatch.setattr(prov, "history", boom)
    for _ in range(live.RESUME_TRIES - 1):
        mgr.resume([row()])
    assert writes == [] and "g1" not in mgr.sessions                  # still running: the next reconcile tries again
    monkeypatch.setattr(prov, "history", good)
    mgr.resume([row()])
    assert writes == [] and "g1" in mgr.sessions
    # too little history, with nothing failing, still stops it at once
    mgr2, _ = make_manager()
    monkeypatch.setattr(mgr2.markets.provider("CRYPTO"), "history", lambda *a, **k: [])
    mgr2.resume([row()])
    assert len(writes) == 1 and "Fewer than two" in writes[0][1]["stop_reason"]
    # and ten failures in a row stop it, with no data source's name in the reason
    mgr3, _ = make_manager()
    monkeypatch.setattr(mgr3.markets.provider("CRYPTO"), "history", boom)
    for _ in range(live.RESUME_TRIES):
        mgr3.resume([row()])
    assert len(writes) == 2 and "10 tries" in writes[1][1]["stop_reason"] and "503" not in writes[1][1]["stop_reason"]
