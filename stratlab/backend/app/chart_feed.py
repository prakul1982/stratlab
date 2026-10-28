"""Where the chart's candles of every timeframe come from (MW-1).

A source sends 1m, 5m, 15m, 1h and 1D as they are; 3m, 10m, 30m, 2h, 4h, 1W and 1M are built from the nearest smaller size by
bar_agg, on the exchange's own session clock. This file holds the rules around that:

- how much history each read covers, and how a scroll back asks for the page before the first candle (never the years in between);
- the 1-minute reads for each kind of source: the broker's own candles for Indian instruments (read in cached blocks, see
  KiteService.history_range), minutes from the delayed source for the other stock markets, forex and commodities, and the
  crypto exchange's;
- whether the answer is live or delayed, so the chart can say so and never shows a delayed price as live.

Facts only: candles as the market printed them."""
from datetime import datetime, timedelta, timezone

from . import bar_agg
from .chart_data import parse_before

# calendar days of history a first read covers and each older page adds, by timeframe: about 600 to 1,100 candles a read
FIRST_DAYS = {"1m": 3, "3m": 5, "5m": 10, "10m": 15, "15m": 30, "30m": 45, "1h": 120, "2h": 200, "4h": 300,
              "1d": 366, "1w": 1830, "1mo": 3650 * 3}
PAGE_DAYS = {"1m": 5, "3m": 10, "5m": 10, "10m": 20, "15m": 30, "30m": 60, "1h": 120, "2h": 240, "4h": 365,
             "1d": 1100, "1w": 1830, "1mo": 3650 * 3}
# how far back a 1-minute read reaches, by kind of source (calendar days): the broker keeps about two years, the delayed
# source a week, the crypto exchange's reads are many small requests so it stops sooner
MINUTE_REACH = {"kite": 400, "delayed": 7, "crypto": 14}
MINUTE_FIRST = {"kite": 3, "delayed": 3, "crypto": 1}
MINUTE_PAGE = {"kite": 5, "delayed": 7, "crypto": 1}
KITE_MARKETS = ("IN", "MCX", "CDS")


def minute_kind(market: str, kite_ready: bool = True) -> str:
    """Which source reads a market's 1-minute candles: "kite" (the broker, while its login is on), "crypto" or "delayed"."""
    if market == "CRYPTO":
        return "crypto"
    return "kite" if market in KITE_MARKETS and kite_ready else "delayed"


def minute_window(tf: str, kind: str, until: datetime | None, now: datetime | None = None) -> tuple[datetime, datetime, bool]:
    """(start, end, whether older candles exist) for one read of 1-minute or 3-minute candles: a first read covers the
    newest few days, a page before `until` the days just before it. Reads go back from `until`, not from now, so a long
    scroll back is one block at a time."""
    now = now or datetime.now(timezone.utc)
    # the same number of candles a read, whatever the size built from the minutes (3m: three times the days)
    days = min((PAGE_DAYS if until is not None else FIRST_DAYS)[tf],
               (MINUTE_PAGE if until is not None else MINUTE_FIRST)[kind] * bar_agg.MINUTES[tf])
    end = until or now + timedelta(minutes=1)
    start = end - timedelta(days=days)
    floor = now - timedelta(days=MINUTE_REACH[kind])
    return max(start, floor), end, start > floor


def delivery(market: str, kite_ready: bool) -> dict:
    """How current an answer for a market is: {"live": bool, "delayed": bool}. The broker's candles and the crypto
    exchange's are live; the other source's are shown as delayed (it can be 15 minutes behind), and an Indian instrument read
    from it because the broker's login hasn't happened today is delayed too. Never both."""
    live = market == "CRYPTO" or (market in KITE_MARKETS and kite_ready)
    return {"live": live, "delayed": not live}


def drop_partial_first(bars: list[dict], more: bool, market: str | None, tf: str) -> list[dict]:
    """Built candles without the first calendar day (or week, month) when older ones exist: the read began part way through
    it, so its first candle would be short, and the page before could never fill it in (it asks for candles before this
    candle's start)."""
    if not more or not bars or tf in ("1d",):
        return bars
    zone, _ = bar_agg._zone(market)
    if tf in bar_agg.MINUTES:
        first = bar_agg._parse(bars[0]["t"], zone).date()
        return [b for b in bars if bar_agg._parse(b["t"], zone).date() > first]
    return bars[1:]


def build(bars: list[dict], market: str | None, tf: str, until: datetime | None, more: bool) -> list[dict]:
    """`bars` (the smaller timeframe `tf` is built from) as `tf` candles: those that start before `until`, and without a short
    first one when older candles exist."""
    out = bar_agg.aggregate(bars, tf, market)
    if until is not None:
        out = [b for b in out if (parse_before(b.get("t")) or until) < until]
    return drop_partial_first(out, more, market, tf) if tf in bar_agg.BASE else out


def utc_iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat()


def between(bars: list[dict], start: datetime, end: datetime) -> list[dict]:
    """The candles that start at or after `start` and before `end`."""
    out = []
    for b in bars:
        t = parse_before(b.get("t"))
        if t is not None and start <= t < end:
            out.append(b)
    return out
