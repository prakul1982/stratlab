"""The latest completed session of a market, read one way everywhere.

A stock's or index's "last close", the session it belongs to and "the change on the day" outside market hours come from
two numbers: the close of the latest completed session and the close of the session before it. They were worked out in
several places from several copies of the daily candles and the live quote, so a copy that ended one session early (the
broker's history can answer from an older copy for a while after midnight India time, R11C-012) gave a page the new
session's price with the old session's change: "Last close 2,465.00 +45.1 (+1.96%) on 15 Oct" beside "Prices as of 16 Oct",
the change and the percent not even of the same pair, and the Brief and the watchlist disagreeing (R41A).

This module is the one place that decides it:
- `latest_day`: the market's latest completed session (its close settled), the calendar's, holidays and weekends skipped;
- `behind`: whether some daily candles end before it, so they are never served as current;
- `with_quote_close`: the candles with the quote's close appended when the quote is of that session and the candles lack it;
- `move`: the close, its date and the change against the session before it, the change and the percent of the same pair.
"""
from __future__ import annotations

from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo


def _day(v) -> str:
    return str(v or "")[:10]


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _tz(region: str) -> ZoneInfo:
    from .data.markets import BY_ID
    return ZoneInfo((BY_ID.get(region) or {}).get("tz") or "UTC")


def latest_day(region: str, now: datetime | None = None) -> str:
    """The ISO date of the market's latest completed session: the latest trading day whose close has settled."""
    from . import stock_pages
    return stock_pages.last_close(region, now)[0].isoformat()


def behind(bars: list[dict] | None, region: str, now: datetime | None = None) -> bool:
    """Whether daily (or intraday) candles end on a day before the market's latest completed session: a copy that lacks
    the session the market has closed is stale, whatever its age, and is read again rather than served as current."""
    if not bars:
        return False
    try:
        return _day(bars[-1].get("t")) < latest_day(region, now)
    except Exception:                          # no calendar for the market: nothing to say against the candles
        return False


def quote_day(at, region: str) -> str | None:
    """The trading day, in the market's own zone, a quote's time falls on; None without a readable time."""
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00")) if at else None
    except ValueError:
        return None
    if t is None:
        return None
    tz = _tz(region)
    return (t if t.tzinfo else t.replace(tzinfo=tz)).astimezone(tz).date().isoformat()


def quote_candle(q: dict | None, region: str, now: datetime | None = None) -> dict | None:
    """The daily candle a quote of a completed session makes ({"t", "o", "h", "l", "c", "v"}, dated at the session's
    midnight in the market's zone as the broker dates its own), or None when the quote is not of the latest completed
    session or has no price. The close is the quote's last price: after the close it is the session's close."""
    if not q:
        return None
    px = _num(q.get("price"))
    day = quote_day(q.get("at"), region)
    if px is None or px <= 0 or not day:
        return None
    try:
        if day != latest_day(region, now):
            return None
        from .data.calendar import is_trading_day
        if not is_trading_day(region, date.fromisoformat(day)):
            return None
    except Exception:
        return None
    o = _num(q.get("open")) or px
    hi = max(x for x in (_num(q.get("high")), o, px) if x)
    lo = min(x for x in (_num(q.get("low")), o, px) if x)
    t = datetime.combine(date.fromisoformat(day), dtime(0, 0), _tz(region)).isoformat()
    return {"t": t, "o": o, "h": hi, "l": lo, "c": px, "v": _num(q.get("volume")) or 0.0}


def with_quote_close(bars: list[dict], q: dict | None, region: str, now: datetime | None = None) -> list[dict]:
    """The candles, with the quote's candle after them when the quote is of the latest completed session and they end
    before it. Candles given are never changed; candles that already hold the session are returned as they are."""
    c = quote_candle(q, region, now)
    if c is None or (bars and _day(bars[-1].get("t")) >= _day(c["t"])):
        return bars
    return [*(bars or []), c]


def on_or_before(region: str, day: date) -> date:
    """The latest trading day of the market on or before a date (the date itself when it trades): what a page dated
    "today" on a weekend or a holiday names instead, so every page says the same last session (R41A: "Prices as of
    17 Oct 2026" on a Saturday beside "16 Oct" everywhere else). The date itself when the market has no calendar."""
    from datetime import timedelta
    from .data.calendar import is_trading_day
    d = day
    try:
        for _ in range(15):
            if is_trading_day(region, d):
                return d
            d -= timedelta(days=1)
    except Exception:
        pass
    return day


def move(bars: list[dict] | None, q: dict | None, region: str = "IN", now: datetime | None = None) -> dict | None:
    """The latest completed session against the one before it, from one series: the daily candles up to that session, with
    the quote's close appended when the quote is of that session and the candles end before it. {"day", "close",
    "prev_day", "prev_close", "change", "change_pct"}: the change and the percent are of the same two closes. None
    without two sessions (a new listing)."""
    from .intel.company import change_2dp
    try:
        through = latest_day(region, now)
    except Exception:
        return None
    rows = [(d, c) for d, c in ((_day(b.get("t")), _num(b.get("c"))) for b in bars or []) if d and d <= through and c is not None]
    rows = [(_day(b["t"]), b["c"]) for b in with_quote_close([{"t": d, "c": c} for d, c in rows], q, region, now)]
    if len(rows) < 2 or not rows[-2][1]:
        return None
    (day, last), (prev_day, prev) = rows[-1], rows[-2]
    return {"day": day, "close": last, "prev_day": prev_day, "prev_close": prev,
            "change": round(last - prev, 2), "change_pct": change_2dp(last, prev)}
