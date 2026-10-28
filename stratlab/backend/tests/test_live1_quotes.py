"""LIVE-1: pages read their prices again each minute, so the broker's quotes are read once for everyone within a few seconds
(app/quote_share.py) instead of once for each page open, and the gold and coin prices net worth uses are kept a minute."""
import time

from app import main, quote_share
from app.intel.company import Research


class Feed:
    """A broker feed that counts what it is asked for."""
    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows or {}

    def ready(self):
        return True

    def quote(self, symbols, max_wait=None):
        self.calls.append(list(symbols))
        return {s: {"price": self.rows[s], "prev_close": 100.0, "at": "2026-10-28T10:00:00+05:30"} for s in symbols if s in self.rows}


def test_a_symbol_read_a_moment_ago_is_not_asked_for_again():
    f = Feed({"TCS": 3000.0, "INFY": 1500.0})
    a = quote_share.read(f, ["TCS", "INFY"])
    b = quote_share.read(f, ["TCS"])
    c = quote_share.read(f, ["TCS", "INFY"])
    assert a["TCS"]["price"] == 3000.0 and b["TCS"]["price"] == 3000.0 and c == a
    assert f.calls == [["TCS", "INFY"]]                                   # one read of the feed for three pages


def test_only_the_symbols_not_kept_are_asked_for_in_one_call():
    f = Feed({"TCS": 3000.0, "INFY": 1500.0, "SBIN": 800.0})
    quote_share.read(f, ["TCS"])
    got = quote_share.read(f, ["TCS", "INFY", "SBIN"])
    assert set(got) == {"TCS", "INFY", "SBIN"}
    assert f.calls == [["TCS"], ["INFY", "SBIN"]]


def test_a_symbol_the_feed_does_not_answer_is_not_asked_for_again_either_and_stays_out_of_the_answer():
    f = Feed({"TCS": 3000.0})
    assert quote_share.read(f, ["TCS", "NOSUCH"]) .keys() == {"TCS"}
    assert quote_share.read(f, ["NOSUCH"]) == {}
    assert f.calls == [["TCS", "NOSUCH"]]


def test_a_quote_older_than_its_time_is_read_again(monkeypatch):
    f = Feed({"TCS": 3000.0})
    quote_share.read(f, ["TCS"])
    real = time.monotonic
    monkeypatch.setattr(quote_share.time, "monotonic", lambda: real() + quote_share.SHARE_FOR + 1)
    f.rows["TCS"] = 3010.0
    assert quote_share.read(f, ["TCS"])["TCS"]["price"] == 3010.0
    assert len(f.calls) == 2


def test_the_answer_is_a_copy_a_caller_can_change():
    f = Feed({"TCS": 3000.0})
    a = quote_share.read(f, ["TCS"])
    a["TCS"]["price"] = 1.0
    assert quote_share.read(f, ["TCS"])["TCS"]["price"] == 3000.0


def test_a_failed_read_keeps_nothing_and_raises():
    asked = []

    class Down(Feed):
        def quote(self, symbols, max_wait=None):
            asked.append(list(symbols))
            raise RuntimeError("feed down")
    f = Down()
    for _ in range(2):
        try:
            quote_share.read(f, ["TCS"])
            raise AssertionError("should have raised")
        except RuntimeError:
            pass
    assert len(asked) == 2                                                # nothing kept: the next page asks again


def test_two_feeds_never_share():
    a, b = Feed({"TCS": 3000.0}), Feed({"TCS": 1.0})
    assert quote_share.read(a, ["TCS"])["TCS"]["price"] == 3000.0
    assert quote_share.read(b, ["TCS"])["TCS"]["price"] == 1.0


def test_the_store_is_bounded(monkeypatch):
    monkeypatch.setattr(quote_share, "MAX_ITEMS", 50)
    f = Feed({f"S{i}": float(i) for i in range(200)})
    quote_share.read(f, [f"S{i}" for i in range(200)])
    assert len(quote_share._kept) <= 50


def test_the_research_quotes_of_india_share_one_read_of_the_broker_between_pages():
    """Five people with a watchlist or a peers panel open read the same stocks within a minute: the broker is asked once."""
    f = Feed({"RELIANCE": 2500.0, "TCS": 3000.0})
    hub = Research(f)
    for _ in range(5):
        got = hub.quotes("IN", ["RELIANCE", "TCS"])
        assert got["RELIANCE"]["price"] == 2500.0 and got["TCS"]["price"] == 3000.0
    assert f.calls == [["RELIANCE", "TCS"]]


def test_holdings_prices_are_read_through_the_same_share(monkeypatch):
    """My space, Holdings and Money read a person's prices each minute: two people holding the same stock cost the broker one read."""
    f = Feed({"RELIANCE": 2500.0, "TCS": 3000.0})
    monkeypatch.setattr(main, "kite", f)
    monkeypatch.setattr(main, "close_quotes", lambda todo, now=None: {})
    a = main._read_prices([{"symbol": "RELIANCE"}, {"symbol": "TCS"}], [])
    b = main._read_prices([{"symbol": "TCS"}, {"symbol": "RELIANCE"}], [])
    assert a["live"] and b["live"] and a["quotes"]["TCS"]["price"] == 3000.0 == b["quotes"]["TCS"]["price"]
    assert f.calls == [["RELIANCE", "TCS"]]


def test_gold_and_coin_prices_for_net_worth_are_kept_a_minute_not_ten():
    assert main.NW_PRICE_TTL == 60.0
    main._nw_prices.clear()
    reads = []
    main._nw_cached("gold-test", lambda: reads.append(1) or (7000.0, "x"))
    main._nw_cached("gold-test", lambda: reads.append(1) or (7000.0, "x"))
    assert len(reads) == 1
    main._nw_prices["gold-test"] = (time.time() - main.NW_PRICE_TTL - 1, (1.0, "old"))
    main._nw_cached("gold-test", lambda: reads.append(1) or (7000.0, "x"))
    assert len(reads) == 2
    main._nw_prices.clear()
