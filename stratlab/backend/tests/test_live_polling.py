from datetime import datetime, timezone
from types import SimpleNamespace

from app import live
from app.data import Registry
from app.data.coinbase import CoinbaseProvider
from app.kite_service import KiteService, TickHub
from tests.test_notebooks import EMA, wavy_coinbase


def make_manager():
    kite = KiteService()
    reg = Registry(kite, CoinbaseProvider(transport=wavy_coinbase()))
    return live.LiveManager(kite, TickHub(kite), reg), reg


def test_crypto_session_polls_closed_candles(monkeypatch):
    mgr, reg = make_manager()
    inst = reg.resolve("CRYPTO:BTC-USD")[1]
    row = {"id": "s1", "user_id": "u", "name": "BTC trend", "strategy": {**EMA, "tf": "5m"}, "instrument": inst,
           "started_at": datetime.now(timezone.utc).isoformat()}
    s = live.LiveSession(mgr, row)
    assert s.polled and s.engine.qty_step == 1e-8 and s.engine.kind == "crypto"
    # every bar it starts from has closed
    assert all(live._closed(b, "5m") for b in s.bars)

    # a new closed candle shows up on the next poll
    newer = {"t": "2999-01-01T00:00:00+00:00", "o": 1, "h": 1, "l": 1, "c": 1, "v": 0}
    monkeypatch.setattr(s.prov, "closed_candles", lambda inst, tf, since: [newer])
    n = len(s.bars)
    s.on_timer(datetime.now(timezone.utc))
    assert len(s.bars) == n + 1 and s.bars[-1] is newer
    assert s.last_price == 30000 and s.poll_ok
    snap = s.snapshot()
    assert snap["feed_connected"] is True and snap["forming"] is None
    # no second poll within the interval
    s.on_timer(datetime.now(timezone.utc))
    assert len(s.bars) == n + 1


def test_india_sessions_wait_for_kite_login(monkeypatch):
    mgr, _ = make_manager()
    attached = []
    monkeypatch.setattr(live.db, "running_sessions", lambda: [
        {"id": "a", "instrument": {"market": "IN", "token": 1}},
        {"id": "b", "instrument": {"market": "CRYPTO"}},
    ])
    monkeypatch.setattr(mgr, "_attach", lambda row: attached.append(row["id"]))
    mgr.resume()
    assert attached == ["b"]   # India waits: Kite isn't logged in


# ---------- restarts: the state is saved with each order, and candles closed while down are caught up on ----------
STOP1 = {"name": "Always in", "tf": "5m", "side": "long", "entryJoin": "all",
         "entry": [{"l": {"t": "price"}, "op": "gt", "r": {"t": "num", "v": 1}}], "exit": [],
         "risk": {"capital": 10000, "riskPct": 1, "maxAlloc": 100, "sl": 1, "sizing": "capital", "perTrade": 5000,
                  "leverage": 1, "brokerage": 0, "slippage": 0}}


def bar5(i, c=100.0, lo=None):
    t = datetime(2026, 10, 12, 9, 30, tzinfo=timezone.utc).timestamp() + i * 300
    return {"t": datetime.fromtimestamp(t, timezone.utc).isoformat(), "o": c, "h": c, "l": lo or c, "c": c, "v": 1}


class Now:
    """Runs a background thread at once, so its writes can be checked."""
    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


def run_threads_now(monkeypatch):
    import threading
    monkeypatch.setattr(live, "threading", SimpleNamespace(Thread=Now, Lock=threading.Lock))


def offline_world(monkeypatch, mgr, history):
    calls = []
    prov = mgr.markets.provider("CRYPTO")
    monkeypatch.setattr(prov, "history", lambda inst, tf, days, ttl=None: list(history))
    run_threads_now(monkeypatch)
    monkeypatch.setattr(live.db, "get_profile", lambda uid: {"id": uid, "alerts_enabled": True})
    monkeypatch.setattr(live, "alerts_on", lambda p: True)
    monkeypatch.setattr(live, "notify", lambda p, subj, body, **k: calls.append(("alert", subj, body)))
    monkeypatch.setattr(live.db, "add_order", lambda o: calls.append(("order", o["side"], o["reason"])))
    monkeypatch.setattr(live.db, "update_session", lambda sid, **k: calls.append(("save", k.get("state"))))
    return calls


def test_an_order_saves_the_session_before_it_is_logged_or_alerted(monkeypatch):
    mgr, reg = make_manager()
    calls = offline_world(monkeypatch, mgr, [bar5(i) for i in range(40)])
    row = {"id": "s1", "user_id": "u", "name": "Always in", "strategy": STOP1, "instrument": reg.resolve("CRYPTO:BTC-USD")[1],
           "started_at": "2026-10-12T09:00:00+00:00"}
    s = mgr._attach(row)
    s._on_candle(bar5(40))
    assert [c[0] for c in calls] == ["save", "alert"]          # saved at once, not up to 30 seconds later (a coin's
    # fractional quantity isn't in the whole-number orders table)
    assert calls[0][1]["qty"] > 0 and calls[0][1]["last_bar_t"] == bar5(40)["t"]


def test_a_restart_runs_the_candles_that_closed_while_the_server_was_down(monkeypatch):
    mgr, reg = make_manager()
    hist = [bar5(i) for i in range(40)]
    offline_world(monkeypatch, mgr, hist)
    row = {"id": "s1", "user_id": "u", "name": "Always in", "strategy": STOP1, "instrument": reg.resolve("CRYPTO:BTC-USD")[1],
           "started_at": "2026-10-12T09:00:00+00:00"}
    s = live.LiveSession(mgr, row)
    assert not s.engine.events                        # a new session runs no history
    s._on_candle(bar5(40))
    assert s.engine.qty > 0 and s.engine.sl == 99.0
    saved = s.state()
    # down for three candles: the second one's low crosses the stop; the history now reaches past the saved candle
    calls = offline_world(monkeypatch, mgr, hist + [bar5(40), bar5(41), bar5(42, lo=98.0), bar5(43)])
    mgr.sessions["s1"] = s2 = live.LiveSession(mgr, {**row, "state": saved})
    e = s2.engine
    stop = next(t for t in e.trades if t["why"] == "Stop loss")
    assert stop["exit_t"] == bar5(42)["t"] and stop["exit"] == 99.0
    # the 10:00 candle saved before the restart isn't run again: one entry before it, one after the stop
    assert [ev["t"] for ev in e.events if ev["side"] == "buy"] == [bar5(40)["t"], bar5(43)["t"]]
    assert s2.bars[-1]["t"] == bar5(43)["t"] and s2.state()["last_bar_t"] == bar5(43)["t"]
    alerts = [c for c in calls if c[0] == "alert"]               # one alert for the caught-up orders, not one each
    assert len(alerts) == 1 and "2 paper trades while offline" in alerts[0][1]
    assert "SELL" in alerts[0][2] and "Stop loss" in alerts[0][2] and "Entry rule" in alerts[0][2]
    # restarting again from the caught-up state runs nothing more
    calls.clear()
    s3 = live.LiveSession(mgr, {**row, "state": s2.state()})
    assert len(s3.engine.events) == len(e.events) and not [c for c in calls if c[0] == "alert"]


def test_a_poll_without_a_price_leaves_the_last_one_ageing(monkeypatch):
    mgr, reg = make_manager()
    offline_world(monkeypatch, mgr, [bar5(i) for i in range(40)])
    row = {"id": "s1", "user_id": "u", "name": "Always in", "strategy": STOP1, "instrument": reg.resolve("CRYPTO:BTC-USD")[1],
           "started_at": "2026-10-12T09:00:00+00:00"}
    s = live.LiveSession(mgr, row)
    monkeypatch.setattr(s.prov, "closed_candles", lambda inst, tf, since: [])
    monkeypatch.setattr(s.prov, "ltp", lambda inst: None)
    s.on_timer(datetime.now(timezone.utc))
    assert s.poll_ok and s.last_tick_at is None                   # no price came, so none is fresh
    monkeypatch.setattr(s.prov, "ltp", lambda inst: 101.0)
    s.next_poll = 0
    s.on_timer(datetime.now(timezone.utc))
    assert s.last_price == 101.0 and s.last_tick_at


def test_a_tick_is_as_fresh_as_its_own_time():
    from app.kite_service import IST
    now = datetime.now(IST)
    old = now.replace(microsecond=0) - live.timedelta(days=1)
    assert live.tick_time(old) == old.isoformat()                 # yesterday's close sent on subscribe stays yesterday's
    assert datetime.fromisoformat(live.tick_time(now + live.timedelta(seconds=5))) <= datetime.now(IST)   # never ahead
