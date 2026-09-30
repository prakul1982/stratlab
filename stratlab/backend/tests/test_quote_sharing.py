"""Option quotes are shared across sessions and paced to Kite's one-request-a-second limit."""
import time

from app.options import data as D


class FakeKite:
    def __init__(self):
        self.calls, self.kite = [], self

    def _require(self): pass
    def _throttle(self): pass
    def ready(self): return True

    def quote(self, keys):
        self.calls.append((time.time(), list(keys)))
        return {k: {"last_price": 100.0, "depth": {"buy": [{"price": 99.5}], "sell": [{"price": 100.5}]}} for k in keys}


def test_one_request_carries_every_sessions_contracts(monkeypatch):
    monkeypatch.setattr(D, "QUOTE_GAP", 0.0)
    monkeypatch.setattr(D, "REFRESH", 0.0)
    k = FakeKite()
    od = D.OptionsData(k)
    a = od.quotes(["NFO:A1", "NFO:A2"])                     # session A
    assert a["NFO:A1"]["bid"] == 99.5 and k.calls[-1][1] == ["NFO:A1", "NFO:A2"]
    od.quotes(["NFO:B1"])                                   # session B's request refreshes A's contracts too
    assert k.calls[-1][1] == ["NFO:B1", "NFO:A1", "NFO:A2"]
    n = len(k.calls)
    assert set(od.quotes(["NFO:A1", "NFO:A2"])) == {"NFO:A1", "NFO:A2"} and len(k.calls) == n   # A: from the cache


def test_requests_are_paced(monkeypatch):
    monkeypatch.setattr(D, "QUOTE_GAP", 0.2)
    k = FakeKite()
    od = D.OptionsData(k)
    for i in range(3):
        od.quotes([f"NFO:X{i}"], max_age=0)
    gaps = [b[0] - a[0] for a, b in zip(k.calls, k.calls[1:])]
    assert len(k.calls) == 3 and all(g >= 0.19 for g in gaps)


def test_big_requests_are_split(monkeypatch):
    monkeypatch.setattr(D, "QUOTE_GAP", 0.0)
    k = FakeKite()
    out = D.OptionsData(k).quotes([f"NFO:K{i}" for i in range(1000)])
    assert len(out) == 1000 and [len(c[1]) for c in k.calls] == [450, 450, 100]


def test_old_experiments_keep_only_their_last_trades():
    from app import research
    exps = [{"v": i, "trades": [{"n": j} for j in range(100)]} for i in range(15)]
    out = research.slim(exps)
    assert [len(e["trades"]) for e in out] == [30] * 5 + [100] * 10
    assert out[0]["trades_trimmed"] == 70 and out[0]["trades"][-1] == {"n": 99} and "trades_trimmed" not in out[-1]
    assert research.slim(out)[0]["trades_trimmed"] == 70            # trimming again changes nothing


def test_recorder_prunes_old_snapshots_once_a_day():
    from datetime import datetime, timezone
    from app.options.recorder import Recorder

    class Data:
        def ready(self): return False                                # outside hours: nothing recorded
    cut = []
    r = Recorder(Data(), lambda row: None, [("NFO", "NIFTY")], prune=cut.append, keep_days=120)
    now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    r.run_once(now)
    r.run_once(now)
    assert len(cut) == 1 and cut[0].startswith("2026-06-02")
