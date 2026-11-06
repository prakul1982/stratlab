"""LIVE5-001: after the close the results page priced its rows 24 a call through one read per stock of a source allowed 90 a
minute; past that budget the reads came back as "no price" and 28 rows (and every row "Show 50 more" added) kept the day
before's close for good. Now a stock refused for the budget is said to be pending (the page asks again), each stock's quote
read after the close is kept for every page, and the broker's after-close quotes of today's session read no candles."""
from datetime import datetime, timezone

from app.intel import company
from app.intel.company import Research
from app.intel.net import SourceError, rate_wait


class Yahoo:
    """A delayed source with a budget: the first `budget` reads answer, the rest are refused as busy."""
    def __init__(self, budget=100):
        self.budget, self.asked, self.waits = budget, [], []

    def meta(self, sym):
        self.asked.append(sym)
        self.waits.append(rate_wait())
        if len(self.asked) > self.budget:
            raise SourceError("Yahoo Finance", "busy (our rate limit)", busy=True)
        return {"price": 100.0 + len(self.asked), "prev_close": 100.0, "change_pct": 1.0, "at": "2026-11-06T10:00:00+00:00"}


class NoFinnhub:
    def ready(self):
        return False


def hub(y):
    return Research(None, finnhub=NoFinnhub(), yahoo=y)


def test_stocks_past_the_sources_budget_are_pending_not_priceless(monkeypatch):
    monkeypatch.setattr(company, "market_open", lambda region, now=None: True)
    y = Yahoo(budget=3)
    got, pending = hub(y).quotes_pending("IN", ["A", "B", "C", "D", "E"])
    assert sum(1 for v in got.values() if v) == 3
    assert sorted(pending) == sorted(s for s, v in got.items() if v is None)
    assert len(pending) == 2


def test_a_quote_read_after_the_close_is_kept_for_the_next_page(monkeypatch):
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    y = Yahoo()
    h = hub(y)
    a, _ = h.quotes_pending("IN", ["ABB", "OIL"])
    b, pending = h.quotes_pending("IN", ["ABB", "OIL"])
    assert a == b and not pending
    assert len(y.asked) == 2                     # one read of each stock for two pages


def test_while_the_market_trades_nothing_is_kept_past_the_sources_own_minute(monkeypatch):
    monkeypatch.setattr(company, "market_open", lambda region, now=None: True)
    y = Yahoo()
    h = hub(y)
    h.quotes_pending("IN", ["ABB"])
    h.quotes_pending("IN", ["ABB"])
    assert len(y.asked) == 2


def test_the_reads_on_the_pool_wait_only_the_requests_short_wait(monkeypatch):
    from app.intel.net import with_rate_wait
    monkeypatch.setattr(company, "market_open", lambda region, now=None: True)
    y = Yahoo()
    with_rate_wait(1.0, lambda: hub(y).quotes_pending("IN", ["ABB", "OIL"]))()
    assert y.waits == [1.0, 1.0]


def test_quotes_keeps_its_old_shape(monkeypatch):
    monkeypatch.setattr(company, "market_open", lambda region, now=None: True)
    got = hub(Yahoo()).quotes("IN", ["ABB"])
    assert got["ABB"]["price"] == 101.0


def test_the_brokers_after_close_quote_of_today_reads_no_candles(monkeypatch):
    """After the close each stock's quote went through _last_session, which read 15 daily candles from the broker first: 24
    history reads a call. A quote whose last trade is today's needs none."""
    monkeypatch.setattr(company, "market_open", lambda region, now=None: False)
    monkeypatch.setattr(company, "market_today", lambda region, now=None: "2026-11-06")

    class Kite:
        history_reads = 0

        def ready(self):
            return True

        def quote(self, symbols, max_wait=None):
            return {s: {"price": 6774.0, "prev_close": 6628.0, "change_pct": 2.2, "at": "2026-11-06T15:29:59+05:30"} for s in symbols}

        def equity(self, s):
            return {"token": 1}

        def history(self, *a, **k):
            Kite.history_reads += 1
            return []
    got = Research(Kite()).quotes("IN", ["ABB", "OIL"])
    assert got["ABB"]["price"] == 6774.0
    assert Kite.history_reads == 0


def test_the_route_says_which_stocks_are_pending(monkeypatch):
    from fastapi.testclient import TestClient
    from app import main
    from app.intel import routes
    from tests import world

    class Hub:
        def quotes_pending(self, region, syms):
            return {"ABB": {"price": 6774.0, "at": datetime(2026, 11, 6, 10, tzinfo=timezone.utc).isoformat()}, "OIL": None}, ["OIL"]
    w = world.build(monkeypatch)
    monkeypatch.setattr(routes, "hub", Hub())
    c: TestClient = w["client"]
    r = c.get("/research/quotes?region=IN&symbols=ABB,OIL&pending=1", headers=world.headers("pro-token"))
    assert r.status_code == 200
    body = r.json()["data"] if "data" in r.json() else r.json()
    assert body["quotes"]["ABB"]["price"] == 6774.0 and body["pending"] == ["OIL"]
    plain = c.get("/research/quotes?region=IN&symbols=ABB,OIL", headers=world.headers("pro-token")).json()
    plain = plain.get("data", plain)
    assert plain["ABB"]["price"] == 6774.0 and "pending" not in plain
