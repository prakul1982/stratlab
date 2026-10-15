"""Coinbase's coin list survives a failed refresh, and a daily series is cached for its UTC day only."""
from datetime import datetime, timedelta, timezone

import httpx
import time_machine

from app.data.coinbase import RELOAD_AFTER_ERROR, CoinbaseProvider

START = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
PRODUCTS = [{"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "status": "online", "base_increment": "0.00000001"}]


def transport(state):
    def handler(r: httpx.Request):
        state["hits"].append(r.url.path)
        if r.url.path == "/products":
            return httpx.Response(state["products"][0], json=state["products"][1]) if state["products"] else httpx.Response(500)
        if r.url.path.endswith("/candles"):
            return httpx.Response(200, json=[[int(datetime.now(timezone.utc).timestamp()) // 86400 * 86400, 1, 2, 1.5, 1.8, 10]])
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_a_failed_refresh_keeps_the_coin_list_and_backs_off():
    state = {"hits": [], "products": (200, PRODUCTS)}
    with time_machine.travel(START, tick=False) as clock:
        p = CoinbaseProvider(transport=transport(state))
        assert p.instrument("BTC-USD")["symbol"] == "BTC/USD"
        state["products"] = None                                   # Coinbase is down
        clock.shift(timedelta(hours=7))                            # the list is stale: a refresh is tried...
        assert p.instrument("BTC-USD")["symbol"] == "BTC/USD"      # ...fails, and the old list serves
        n = state["hits"].count("/products")
        assert p.search("btc") and p.defaults()
        assert state["hits"].count("/products") == n                # backing off: not asked again on every call
        clock.shift(timedelta(seconds=RELOAD_AFTER_ERROR + 1))
        assert p.instrument("BTC-USD")
        assert state["hits"].count("/products") == n + 1            # asked again after the back-off
        state["products"] = (200, PRODUCTS + [{"id": "ETH-USD", "base_currency": "ETH", "quote_currency": "USD", "status": "online"}])
        clock.shift(timedelta(seconds=RELOAD_AFTER_ERROR + 1))
        assert p.instrument("ETH-USD")                              # a good answer replaces the list


def test_with_no_list_at_all_the_error_still_surfaces():
    import pytest
    from app.data.coinbase import DataError
    state = {"hits": [], "products": None}
    with time_machine.travel(START, tick=False):
        with pytest.raises(DataError):
            CoinbaseProvider(transport=transport(state)).instrument("BTC-USD")


def test_a_daily_series_is_cached_for_its_utc_day_only():
    state = {"hits": [], "products": (200, PRODUCTS)}
    with time_machine.travel(START, tick=False) as clock:
        p = CoinbaseProvider(transport=transport(state))
        inst = p.instrument("BTC-USD")
        p.history(inst, "1d", 5)
        n = state["hits"].count("/products/BTC-USD/candles")
        p.history(inst, "1d", 5)
        assert state["hits"].count("/products/BTC-USD/candles") == n          # same UTC day: cached
        clock.move_to(datetime(2026, 10, 12, 23, 59, 30, tzinfo=timezone.utc))
        p.history(inst, "1d", 5)                                              # cached again, a minute before midnight
        clock.move_to(datetime(2026, 10, 13, 0, 0, 30, tzinfo=timezone.utc))
        before = state["hits"].count("/products/BTC-USD/candles")
        p.history(inst, "1d", 5)
        assert state["hits"].count("/products/BTC-USD/candles") > before      # a new UTC day: read again
