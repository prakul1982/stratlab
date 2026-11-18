"""Lane fix16 (LIVE12B review of the live site): figures against the exchange's completed sessions."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx

from app.intel.yahoo import Yahoo, _partial

NY = ZoneInfo("America/New_York")


def _ts(y, m, d, h=0, mi=0):
    return int(datetime(y, m, d, h, mi, tzinfo=NY).timestamp())


def _gold(live_at):
    """GC=F's daily answer read at `live_at` (New York time), inside the session of Wed 18 Nov, which opened at 18:00 on Tue 17 Nov:
    the settled 16 and 17 Nov candles, then the live bar stamped at the moment it was read."""
    return {"chart": {"result": [{
        "meta": {"symbol": "GC=F", "currency": "USD", "exchangeTimezoneName": "America/New_York", "instrumentType": "FUTURE",
                 "regularMarketPrice": 3788.6, "regularMarketTime": live_at,
                 "currentTradingPeriod": {"regular": {"start": _ts(2026, 11, 17, 18), "end": _ts(2026, 11, 18, 17), "timezone": "EST"}}},
        "timestamp": [_ts(2026, 11, 16), _ts(2026, 11, 17), live_at],
        "indicators": {"quote": [{"open": [3840.0, 3855.0, 3860.0], "high": [3870.0, 3880.0, 3866.0], "low": [3830.0, 3845.0, 3780.0],
                                  "close": [3853.0, 3864.2, 3788.6], "volume": [10, 12, 3]}]}}], "error": None}}


def test_a_futures_session_that_opened_last_evening_is_its_own_day_not_the_settled_one_before_it():
    """LIVE12B-005: at 23:02 New York time on 17 Nov (04:02 UTC 18 Nov) the live gold price replaced 17 Nov's settled candle, so My space
    showed "$3,788 ▼ −1.68% on 17 Nov", the change from 16 Nov's close. The live bar is 18 Nov's session: 17 Nov keeps its close and the
    day's change is measured from it."""
    live = _ts(2026, 11, 17, 23, 2)
    y = Yahoo(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_gold(live))))
    bars = y.chart("GC=F", "1d", 30, ttl=0, exact=True)["candles"]
    assert [(b["t"][:10], b["c"]) for b in bars] == [("2026-11-16", 3853.0), ("2026-11-17", 3864.2), ("2026-11-18", 3788.6)]
    last, prev = bars[-1]["c"], bars[-2]["c"]
    assert round((last / prev - 1) * 100, 2) == -1.96                  # not −1.67, the move from 16 Nov
    m = y.meta("GC=F")                                                   # the quote's own day's change (watch rows, the mood)
    assert m["prev_close"] == 3864.2 and round(m["change_pct"], 2) == -1.96
    # the answer counts as a session still trading (kept a minute, not half an hour)
    assert _partial({"meta": _gold(live)["chart"]["result"][0]["meta"], "candles": bars}, now=live + 60)


def test_a_session_within_one_day_and_a_coin_keep_their_calendar_day():
    """A stock's session (09:30 to 16:00) and a coin's midnight-to-midnight period date their candles by the calendar day, as before."""
    for kind, start, end in (("EQUITY", _ts(2026, 11, 17, 9, 30), _ts(2026, 11, 17, 16)),
                             ("CRYPTOCURRENCY", _ts(2026, 11, 17), _ts(2026, 11, 18))):
        live = _ts(2026, 11, 17, 15, 0)
        body = _gold(live)
        meta = body["chart"]["result"][0]["meta"]
        meta.update(instrumentType=kind, currentTradingPeriod={"regular": {"start": start, "end": end}})
        bars = Yahoo(transport=httpx.MockTransport(lambda r, b=body: httpx.Response(200, json=b))).chart("X", "1d", 30, ttl=0, exact=True)["candles"]
        assert [b["t"][:10] for b in bars] == ["2026-11-16", "2026-11-17"], kind      # the live bar is 17 Nov's


def test_statements_write_the_rupee_sign_not_in_rs():
    """LIVE12B-017: the statements' "EPS in Rs" row, beside ₹ everywhere else on the page, is "EPS (₹)"; still a per-share figure."""
    from app.company_tables import aligned
    rows = aligned({"cols": ["Mar 2025", "Mar 2026"], "rows": {"Sales +": [10, 12], "EPS in Rs": [1.0, 3.0], "Dividend Payout %": [40, 45]}}, ["Mar 2025", "Mar 2026"])
    assert [(r["label"], r["kind"]) for r in rows] == [("Sales", "money"), ("EPS (₹)", "per_share"), ("Dividend Payout %", "pct")]


def test_a_brief_whose_summary_is_only_the_moves_keeps_a_line_in_the_list():
    """LIVE12B-025: the 13 Nov brief had no line in the Briefs list (its summary was the index moves alone, which the list leaves to the
    title and the table); every other day had one. Such a summary keeps its moves; one with more drops them as before (LIVE11B-015)."""
    from app.newsletter.write import without_moves
    idx = [{"name": "NIFTY 50", "change_pct": 0.38}, {"name": "SENSEX", "change_pct": 0.31}]
    only = "NIFTY 50 +0.38%; SENSEX +0.31% today."
    assert without_moves(only, idx) == only
    assert without_moves(only + " Metals led; 3 stocks entered Stage 2.", idx) == "Metals led; 3 stocks entered Stage 2."
