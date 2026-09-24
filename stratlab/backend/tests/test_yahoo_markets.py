from datetime import datetime

import pytest

from app.data.yahoo_markets import YahooProvider, fits
from app.engine import costs as C
from app.intel.yahoo import Yahoo
from tests.fake_yahoo import fake_yahoo


@pytest.fixture
def yahoo():
    return Yahoo(transport=fake_yahoo())


def test_search_keeps_each_market_to_its_own_listings(yahoo):
    assert [r["id"] for r in YahooProvider("US", yahoo).search("aapl")] == ["US:AAPL"]   # not the Mexican listing
    assert [r["id"] for r in YahooProvider("UK", yahoo).search("voda")] == ["UK:VOD.L"]
    assert YahooProvider("EU", yahoo).search("sap")[0]["currency"] == "EUR"
    assert YahooProvider("JP", yahoo).search("toyota")[0]["token"] == "7203.T"
    fx = YahooProvider("FX", yahoo).search("eurusd")[0]
    assert fx["symbol"] == "EUR/USD" and fx["currency"] == "USD" and fx["type"] == "FX"
    assert not fits("US", {"symbol": "RELIANCE.NS", "quoteType": "EQUITY", "exchange": "NSI"})


def test_history_is_in_pounds_for_london(yahoo):
    uk = YahooProvider("UK", yahoo)
    inst = uk.instrument("VOD.L")
    bars = uk.history(inst, "1d", 60)
    raw = yahoo.chart("VOD.L", "1d", 60)["candles"]      # Yahoo quotes London in pence
    assert bars[-1]["c"] == pytest.approx(raw[-1]["c"] / 100)
    assert uk.ltp(inst) == pytest.approx(yahoo.chart("VOD.L", "1d", 7)["meta"]["regularMarketPrice"] / 100)
    us = YahooProvider("US", yahoo)
    assert us.history(us.instrument("AAPL"), "1d", 60)[-1]["c"] > 100


def test_daily_bars_are_dated_in_exchange_time(yahoo):
    us = YahooProvider("US", yahoo)
    bars = us.history(us.instrument("SPY"), "1d", 30)
    t = datetime.fromisoformat(bars[-1]["t"])
    assert t.hour == 0 and str(t.tzinfo) != "UTC"
    assert len({b["t"] for b in bars}) == len(bars)


def test_intraday_history_is_capped_to_what_yahoo_has(yahoo):
    us = YahooProvider("US", yahoo)
    bars = us.history(us.instrument("AAPL"), "15m", 400)
    first = datetime.fromisoformat(bars[0]["t"]).timestamp()
    assert (datetime.now().timestamp() - first) / 86400 <= 60


def test_closed_candles_only_returns_finished_bars(yahoo):
    us = YahooProvider("US", yahoo)
    inst = us.instrument("AAPL")
    bars = us.history(inst, "1h", 5)
    new = us.closed_candles(inst, "1h", bars[-10]["t"])
    assert new and all(b["t"] > bars[-10]["t"] for b in new)
    assert all(datetime.fromisoformat(b["t"]).timestamp() + 3600 <= datetime.now().timestamp() for b in new)


def test_unknown_symbol_is_none(yahoo):
    assert YahooProvider("US", yahoo).instrument("NOPE") is None


def test_uk_stamp_duty_and_fx_spread():
    assert C.kind_of({"market": "UK", "type": "EQ"}) == "uk"
    assert C.kind_of({"market": "UK", "type": "ETF"}) == "uk_etf"
    buy = C.order_costs("uk", "buy", 100, 10.0, 0)
    assert buy["stamp"] == pytest.approx(5.0)
    assert "stamp" not in C.order_costs("uk", "sell", 100, 10.0, 0)
    assert "stamp" not in C.order_costs("uk_etf", "buy", 100, 10.0, 0)
    assert C.order_costs("fx", "buy", 10000, 1.1, 0)["spread"] == pytest.approx(1.1)
