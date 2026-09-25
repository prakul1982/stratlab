"""Paper trading a group: one engine per member, shared slots, a group-wide loss cap, and restarts."""
from datetime import datetime, timezone

from app import db, group_live
from tests.test_live_polling import make_manager

STRAT = {"name": "Momentum", "tf": "5m", "side": "long", "entryJoin": "all",
         "entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 0}}], "exit": [],
         "session": {"dailyLossPct": 1},
         "risk": {"capital": 1000000, "riskPct": 1, "maxAlloc": 100, "sl": 50, "sizing": "capital", "perTrade": 100000, "leverage": 1}}


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
