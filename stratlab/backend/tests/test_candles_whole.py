"""Every candle StratLab reads has its high and low hold its open and close, whatever its source (5 Nov: EUR/USD and gold from
the global source; 6 Nov: MCX gold-mini from the broker, which failed the feature check and emailed the owner)."""
from app.candles import whole, whole_all, whole_candles
from app.data.coinbase import CoinbaseProvider
from app.data.cds import CDSProvider
from app.data.mcx import MCXProvider
from app.kite_service import KiteService
from app.platform_check import candle_sane

GOLDM = {"t": "2026-11-05", "o": 144847.0, "h": 144800.0, "l": 143900.0, "c": 144500.0, "v": 10}


def test_a_broken_candle_is_widened_and_a_whole_one_is_left_alone():
    fixed = whole(GOLDM)
    assert candle_sane(fixed) and fixed["h"] == 144847.0 and fixed["l"] == 143900.0 and fixed["o"] == 144847.0
    ok = {"t": "x", "o": 10.0, "h": 12.0, "l": 9.0, "c": 11.0, "v": 1}
    assert whole(ok) is ok
    assert whole({"t": "x"}) == {"t": "x"}                                    # not a candle: as it is
    assert whole_all(None) is None and whole_all([GOLDM])[0]["h"] == 144847.0
    fine = [ok, dict(ok)]
    assert whole_all(fine) is fine                                             # nothing to fix: the same list, nothing copied


def test_every_history_read_passes_its_candles_through_the_rule():
    for method in (KiteService.history, KiteService.history_range, MCXProvider.history, CDSProvider.history, CoinbaseProvider.history):
        assert getattr(method, "__wrapped__", None) is not None, method.__qualname__

    class Fake:
        @whole_candles
        def history(self):
            return [dict(GOLDM)]
    assert all(candle_sane(b) for b in Fake().history())
