"""LIVE6 market-data fixes: index candles, special sessions, IPO listing day, business-update dating, theme posts, slow reads."""
from types import SimpleNamespace

from app import main  # noqa: F401, I001  (first: the app loads the newsletter job before the modules built on it)
from app.intel import company as C
from tests.test_review_r7t import StubKite, frozen_yahoo


# ---------- LIVE6-004: an index's daily candle after the close ends on the closing level Mood shows ----------
def _sensex_hub(monkeypatch, quote_price=81879.40):
    monkeypatch.setattr(C, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(C, "market_today", lambda region, now=None: "2026-11-11")
    bars = [{"t": "2026-11-10T00:00:00+05:30", "o": 80900.0, "h": 81200.0, "l": 80800.0, "c": 81107.0, "v": 0.0},
            # today's candle stored during the session, at 81,504
            {"t": "2026-11-11T00:00:00+05:30", "o": 81150.0, "h": 81560.0, "l": 81100.0, "c": 81504.0, "v": 0.0}]
    k = StubKite({"BSE:SENSEX": {"price": quote_price, "open": 81150.0, "high": 81900.0, "low": 81100.0,
                                 "at": "2026-11-11T15:30:00+05:30"}}, bars)
    return C.Research(k, finnhub=SimpleNamespace(ready=lambda: False), yahoo=frozen_yahoo()), k


def test_the_sensex_candle_after_the_close_is_the_close(monkeypatch):
    hub, k = _sensex_hub(monkeypatch)
    got = hub.chart("IN", "^BSESN", "1m", "1d")["candles"]
    assert len(got) == 2 and got[-1]["c"] == 81879.40 and got[-1]["h"] == 81879.40 and got[-1]["o"] == 81150.0
    assert round((got[-1]["c"] / got[-2]["c"] - 1) * 100, 2) == 0.95
    # the quote is kept a minute: a second visit doesn't ask the broker again
    k.quotes = {}
    assert hub.chart("IN", "^BSESN", "1m", "1d")["candles"][-1]["c"] == 81879.40


def test_the_pulse_level_mood_shows_is_the_one_the_candle_takes(monkeypatch):
    import time
    hub, k = _sensex_hub(monkeypatch, quote_price=1.0)
    levels, _ = hub._snaps()
    levels.put("IN", [{"name": "SENSEX", "price": 81879.40, "at": "2026-11-11T15:30:00+05:30", "pre_close": False}], time.time())
    assert hub.chart("IN", "^BSESN", "1m", "1d")["candles"][-1]["c"] == 81879.40
    # a pulse reading from before the close is not used: the live quote is
    levels.put("IN", [{"name": "SENSEX", "price": 81504.0, "at": "2026-11-11T14:10:00+05:30", "pre_close": True}], time.time())
    hub.__dict__.pop("_index_levels", None)
    k.quotes["BSE:SENSEX"]["price"] = 81879.40
    assert hub.chart("IN", "^BSESN", "1m", "1d")["candles"][-1]["c"] == 81879.40


def test_a_previous_sessions_quote_never_changes_todays_candles(monkeypatch):
    hub, k = _sensex_hub(monkeypatch)
    k.quotes["BSE:SENSEX"]["at"] = "2026-11-10T15:30:00+05:30"
    assert hub.chart("IN", "^BSESN", "1m", "1d")["candles"][-1]["c"] == 81504.0


def test_a_stock_candle_out_of_hours_is_left_as_read(monkeypatch):
    monkeypatch.setattr(C, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(C, "market_today", lambda region, now=None: "2026-11-11")
    k = StubKite({}, [{"t": "2026-11-11T00:00:00+05:30", "o": 1.0, "h": 2.0, "l": 1.0, "c": 1.5, "v": 1.0}])
    k.quote = lambda syms: (_ for _ in ()).throw(AssertionError("no quote for a stock's candles out of hours"))
    hub = C.Research(k, finnhub=SimpleNamespace(ready=lambda: False), yahoo=frozen_yahoo())
    assert hub.chart("IN", "RELIANCE", "1y", "1d")["candles"][-1]["c"] == 1.5
