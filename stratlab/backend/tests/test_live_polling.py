from datetime import datetime, timezone

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
