"""Lane site76: the LIVE14A / LIVE14B site findings (live review after Release 75, Wed 18 Nov 2026)."""
import time
from datetime import datetime, timezone

import httpx

from app.intel import yahoo as Y
from app.intel.company import index_level


def _answer(price: float, last: float, start: float, end: float) -> dict:
    return {"chart": {"result": [{
        "meta": {"symbol": "^IXIC", "currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": "INDEX",
                 "regularMarketPrice": price, "regularMarketTime": int(last),
                 "currentTradingPeriod": {"regular": {"start": int(start), "end": int(end)}}},
        "timestamp": [int(start)],
        "indicators": {"quote": [{"open": [price], "high": [price], "low": [price], "close": [price], "volume": [1]}]}}], "error": None}}


def test_live14a_001_a_copy_the_edge_kept_mid_session_is_asked_again_at_another_address_and_the_newer_stands():
    """LIVE14A-001: at 14:49 ET on 18 Nov the source's query2 host answered ^IXIC's 1-minute address with 24,322.707 at 15:52:50 UTC
    (10:52 ET), the level Mood showed for 3.7 h, while the other addresses had the live 24,411. The stale answer is detected by its
    own session (trading now, last trade 4 h old) and asked again at the other host with a window rounded to the minute."""
    now = time.time()
    start, end = now - 5 * 3600, now + 2 * 3600
    seen = []

    def reply(r: httpx.Request):
        seen.append(str(r.url))
        if r.url.host == "query2.finance.yahoo.com":
            return httpx.Response(200, json=_answer(24411.17, now - 20, start, end))
        return httpx.Response(200, json=_answer(24322.71, now - 4 * 3600, start, end))
    y = Y.Yahoo(transport=httpx.MockTransport(reply))
    m = y.meta("^IXIC")
    assert m["price"] == 24411.17
    assert len(seen) == 2 and "query2" in seen[1]
    # the fresh address's window ends on a minute, not on the hour the kept copy's does
    p2 = int(httpx.URL(seen[1]).params["period2"])
    assert p2 % 60 == 0 and p2 - now <= 60


def test_live14a_001_a_live_answer_is_not_asked_twice_and_a_thin_stock_is_not_asked_again_for_ten_minutes():
    now = time.time()
    start, end = now - 3600, now + 3600
    calls = []
    y = Y.Yahoo(transport=httpx.MockTransport(lambda r: (calls.append(r.url.host), httpx.Response(200, json=_answer(10.0, now - 30, start, end)))[1]))
    y.meta("^GSPC")
    assert calls == ["query1.finance.yahoo.com"]
    # a thin stock whose last trade really is old: one re-ask, then none for EDGE_MISS_FOR
    calls.clear()
    y2 = Y.Yahoo(transport=httpx.MockTransport(lambda r: (calls.append(r.url.host), httpx.Response(200, json=_answer(3.0, now - 7200, start, end)))[1]))
    y2.meta("THIN")
    y2.cache.clear()
    y2.meta("THIN")
    assert calls.count("query2.finance.yahoo.com") == 1


def test_live14a_001_stale_edge_rule():
    t0 = 1_795_000_000.0
    meta = {"currentTradingPeriod": {"regular": {"start": t0, "end": t0 + 6.5 * 3600}}, "regularMarketTime": t0 + 3600}
    assert not Y.stale_edge(meta, t0 + 3600 + 300)            # five minutes old: fine
    assert Y.stale_edge(meta, t0 + 3600 + 3 * 3600)           # three hours old in the session: a kept copy
    assert Y.stale_edge(meta, t0 + 7 * 3600)                   # after the close, a last trade from mid-session
    assert not Y.stale_edge({**meta, "regularMarketTime": t0 + 6.5 * 3600 - 1}, t0 + 7 * 3600)   # the close's own last trade
    assert not Y.stale_edge(meta, t0 - 60)                     # before the session
    assert not Y.stale_edge({"regularMarketTime": t0}, t0 + 99999)   # no period: can't be said
    assert not Y.stale_edge({**meta, "instrumentType": "CRYPTOCURRENCY"}, t0 + 5 * 3600)


def test_live14a_001_a_level_read_long_ago_in_the_session_is_delayed_not_live():
    """The index row at 14:35 ET read at 10:52 ET: `delayed`, never `live` (the page then says "as of 10:52 ET", not "today")."""
    now = datetime(2026, 11, 18, 19, 35, tzinfo=timezone.utc)           # 14:35 ET, Wed 18 Nov: NYSE open
    q = {"price": 24322.71, "prev_close": 24327.0, "at": "2026-11-18T15:52:50+00:00", "high52": 25000.0}
    lv = index_level("NASDAQ", q, "US", now)
    assert lv["delayed"] is True and lv["live"] is False and lv["stale"] is False and lv["day"] == "2026-11-18"
    fresh = index_level("NASDAQ", {**q, "at": "2026-11-18T19:33:00+00:00"}, "US", now)
    assert fresh["live"] is True and fresh["delayed"] is False
    # after the close the level is the close's, never delayed
    shut = index_level("NASDAQ", {**q, "at": "2026-11-18T21:00:00+00:00"}, "US", datetime(2026, 11, 18, 23, 0, tzinfo=timezone.utc))
    assert shut["delayed"] is False and shut["live"] is False


def test_live14a_001_the_mood_headline_rests_only_on_levels_read_in_the_last_minutes():
    from pathlib import Path
    src = Path(__file__).resolve().parents[1].joinpath("app/intel/mood.py").read_text()
    assert 'fresh = [i for i in levels if not i.get("delayed")]' in src
    assert 'headline_of(fresh, sectors, cmp' in src
