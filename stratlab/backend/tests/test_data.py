import time

import httpx
import pytest

from app.data import Registry, split_id
from app.data.coinbase import CoinbaseProvider, DataError

PRODUCTS = [
    {"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "base_increment": "0.00000001", "status": "online", "trading_disabled": False},
    {"id": "BTC-EUR", "base_currency": "BTC", "quote_currency": "EUR", "base_increment": "0.00000001", "status": "online", "trading_disabled": False},
    {"id": "ETH-USD", "base_currency": "ETH", "quote_currency": "USD", "base_increment": "0.00000001", "status": "online", "trading_disabled": False},
    {"id": "SOL-USD", "base_currency": "SOL", "quote_currency": "USD", "base_increment": "0.001", "status": "online", "trading_disabled": False},
    {"id": "OLD-USD", "base_currency": "OLD", "quote_currency": "USD", "base_increment": "1", "status": "delisted", "trading_disabled": True},
    {"id": "ETH-BTC", "base_currency": "ETH", "quote_currency": "BTC", "base_increment": "0.00000001", "status": "online", "trading_disabled": False},
]


def fake_coinbase(calls=None):
    def handler(req: httpx.Request):
        if calls is not None:
            calls.append(req)
        path = req.url.path
        if path == "/products":
            return httpx.Response(200, json=PRODUCTS)
        if path.endswith("/ticker"):
            return httpx.Response(200, json={"price": "64123.45"})
        if path.endswith("/candles"):
            g = int(req.url.params["granularity"])
            from datetime import datetime
            s = datetime.fromisoformat(req.url.params["start"]).timestamp()
            e = datetime.fromisoformat(req.url.params["end"]).timestamp()
            t = int(s // g * g)
            out = []
            while t <= e:
                out.append([t, 99.0, 101.0, 100.0, 100.5, 12.0])
                t += g
            return httpx.Response(200, json=list(reversed(out))[:300])
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_products_filtered_and_named():
    p = CoinbaseProvider(transport=fake_coinbase())
    btc = p.instrument("BTC-USD")
    assert btc["id"] == "CRYPTO:BTC-USD" and btc["symbol"] == "BTC/USD"
    assert btc["name"] == "Bitcoin / US Dollar" and btc["currency"] == "USD" and btc["step"] == 1e-8
    assert p.instrument("btc/usd") == btc
    assert p.instrument("OLD-USD") is None     # delisted
    assert p.instrument("ETH-BTC") is None     # quote not supported
    assert [d["token"] for d in p.defaults()] == ["BTC-USD", "ETH-USD", "SOL-USD"]


def test_search_prefers_exact_base_and_usd():
    p = CoinbaseProvider(transport=fake_coinbase())
    res = p.search("btc")
    assert [r["token"] for r in res[:2]] == ["BTC-USD", "BTC-EUR"]
    assert p.search("ether")[0]["token"] == "ETH-USD"


def test_history_pages_through_300_candle_chunks():
    calls = []
    p = CoinbaseProvider(transport=fake_coinbase(calls))
    bars = p.history(p.instrument("BTC-USD"), "1h", 30)   # 720 hourly candles -> 3 requests
    candle_calls = [c for c in calls if c.url.path.endswith("/candles")]
    assert len(candle_calls) == 3
    ts = [b["t"] for b in bars]
    assert ts == sorted(ts) and len(ts) == len(set(ts)) and 715 <= len(bars) <= 725
    assert bars[0]["t"].endswith("+00:00")
    again = p.history(p.instrument("BTC-USD"), "1h", 30)    # cached
    assert again is bars


def test_ltp_and_closed_candles():
    p = CoinbaseProvider(transport=fake_coinbase())
    inst = p.instrument("BTC-USD")
    assert p.ltp(inst) == 64123.45
    closed = p.closed_candles(inst, "5m", None)
    from datetime import datetime
    assert closed and all(datetime.fromisoformat(b["t"]).timestamp() + 300 <= time.time() for b in closed)
    last = closed[-1]["t"]
    assert p.closed_candles(inst, "5m", last) == []


def test_errors_are_clean():
    p = CoinbaseProvider(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(DataError):
        p.defaults()


def test_ids_and_registry_markets():
    assert split_id("256265") == ("IN", "256265")
    assert split_id("CRYPTO:BTC-USD") == ("CRYPTO", "BTC-USD")
    from app.kite_service import KiteService
    from app.intel.yahoo import Yahoo
    from tests.fake_yahoo import fake_yahoo
    reg = Registry(KiteService(), CoinbaseProvider(transport=fake_coinbase()), yahoo=Yahoo(transport=fake_yahoo()))
    status = {m["id"]: m["status"] for m in reg.markets()}
    assert status["IN"] == "offline" and status["CRYPTO"] == "live" and status["CSV"] == "live" and status["US"] == "live"
    prov, inst = reg.resolve("CRYPTO:ETH-USD")
    assert inst["symbol"] == "ETH/USD"
    hits = reg.search("eth", None, True)   # India is offline and no stock matches, so only crypto answers
    assert hits and all(r["market"] == "CRYPTO" for r in hits)
