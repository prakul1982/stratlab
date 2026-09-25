"""Options entered and exited on a notebook's rules, run on the underlying's candles."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.models import OptionStrategy, Strategy
from app.options.engine import OptionsEngine
from app.options.signal import SignalFeed
from tests.test_options import at, contracts, quotes

IST = ZoneInfo("Asia/Kolkata")
EMA7 = {"name": "7 EMA", "tf": "5m", "side": "both", "entryJoin": "all",
        "entry": [{"l": {"t": "price"}, "op": "xa", "r": {"t": "ema", "p": 7}}],
        "exit": [{"l": {"t": "price"}, "op": "xb", "r": {"t": "ema", "p": 7}}],
        "shortEntry": [{"l": {"t": "price"}, "op": "xb", "r": {"t": "ema", "p": 7}}],
        "shortExit": [{"l": {"t": "price"}, "op": "xa", "r": {"t": "ema", "p": 7}}],
        "risk": {"capital": 10000, "sl": 0}}


def buy_call(short="mirror", stop=3000):
    return OptionStrategy(name="EMA calls", underlying="NIFTY", legs=[{"side": "buy", "opt": "CE", "offset": 0}],
                          timing={"entry": "09:20", "lastEntry": "15:00", "squareoff": "15:15", "maxEntries": 10, "cooldown": 0},
                          risk={"stopType": "amount", "stop": stop}, costs={"brokerage": 20, "slippageTicks": 0, "freeze": 0},
                          signal={"rules": EMA7, "name": "7 EMA", "short": short})


LONG = {"dir": "long", "key": "2026-09-24T10:00:00+05:30"}


def test_enters_on_the_signal_and_exits_with_it():
    e, c = OptionsEngine(buy_call()), contracts()
    assert e.step(at("10:01"), 25000, c, quotes(25000), True, None) == [] and "rules" in e.note
    out = e.step(at("10:02"), 25000, c, quotes(25000), True, LONG)
    assert [(o["side"], o["sym"]) for o in out] == [("buy", "NIFTY25000CE")] and e.pos["dir"] == "long"
    assert e.step(at("10:10"), 25020, c, quotes(25020), True, LONG) == []          # still long: hold
    out = e.step(at("10:30"), 25040, c, quotes(25040), True, None)                  # the rules exited
    assert out[0]["side"] == "sell" and e.trades[-1]["why"] == "The rules exited" and e.trades[-1]["pnl"] > 0


def test_short_signal_buys_the_mirrored_put_and_a_flip_closes_first():
    e, c = OptionsEngine(buy_call()), contracts()
    short = {"dir": "short", "key": "2026-09-24T10:30:00+05:30"}
    out = e.step(at("10:31"), 25000, c, quotes(25000), True, short)
    assert [(o["side"], o["sym"]) for o in out] == [("buy", "NIFTY25000PE")]
    flip = {"dir": "long", "key": "2026-09-24T11:00:00+05:30"}
    out = e.step(at("11:01"), 25000, c, quotes(25000), True, flip)
    assert e.trades[-1]["why"] == "The rules turned long" and e.pos is None
    out = e.step(at("11:01"), 25000, c, quotes(25000), True, flip)
    assert out[0]["sym"] == "NIFTY25000CE"


def test_long_only_ignores_short_signals():
    e, c = OptionsEngine(buy_call(short="none")), contracts()
    assert e.step(at("10:31"), 25000, c, quotes(25000), True, {"dir": "short", "key": "k"}) == [] and "long signals" in e.note


def test_a_stopped_trade_is_not_re_entered_on_the_same_signal():
    e, c = OptionsEngine(buy_call(stop=500)), contracts()
    e.step(at("10:02"), 25000, c, quotes(25000), True, LONG)
    e.step(at("10:05"), 24800, c, quotes(24800), True, LONG)                         # the call loses: stop
    assert e.trades[-1]["why"] == "Stop loss"
    assert e.step(at("10:06"), 24800, c, quotes(24800), True, LONG) == [] and "Already traded" in e.note
    nxt = {"dir": "long", "key": "2026-09-24T11:00:00+05:30"}
    assert e.step(at("11:01"), 24800, c, quotes(24800), True, nxt)                  # a new signal enters


def test_rules_need_intraday_candles():
    with pytest.raises(Exception, match="5-minute"):
        buy_call().model_copy(update={}).model_validate({**buy_call().model_dump(), "signal": {"rules": {**EMA7, "tf": "1d"}}})


class FakeKite:
    """Kite history for NIFTY 50: a fall, then a rise that crosses back above the 7 EMA."""
    def __init__(self):
        start = datetime(2026, 9, 23, 9, 15, tzinfo=IST)
        self.bars = []
        px = 25000.0
        for i in range(120):
            px += -5 if i < 100 else 25
            t = start + timedelta(minutes=5 * (i % 75)) + timedelta(days=i // 75)
            self.bars.append({"t": t.isoformat(), "o": px, "h": px + 2, "l": px - 2, "c": px, "v": 0})
        self.shown = 110
        self.kite = SimpleNamespace(ltp=lambda keys: {k: {"instrument_token": 256265} for k in keys})

    def _require(self):
        pass

    def _throttle(self):
        pass

    def history(self, token, tf, days):
        assert token == 256265 and tf == "5m"
        return self.bars[:self.shown]


def test_feed_runs_the_rules_on_new_candles_only(monkeypatch):
    import app.live as live
    monkeypatch.setattr(live, "drop_forming", lambda bars, tf: bars)
    k = FakeKite()
    k.shown = 100
    f = SignalFeed(k, Strategy(**EMA7), "NSE:NIFTY 50")
    assert f.token == 256265 and len(f.bars) == 100 and f.want() is None       # warm-up alone doesn't trade
    k.shown = 104
    f.poll(datetime.now(IST))
    assert f.want() and f.want()["dir"] == "long" and f.want()["key"] == k.bars[100]["t"]
    saved = f.dump()
    g = SignalFeed(k, Strategy(**EMA7), "NSE:NIFTY 50", saved)                    # after a restart
    assert g.want() == f.want() and g.token == 256265
    assert f.view()["position"] == "long" and f.view()["tf"] == "5m"
