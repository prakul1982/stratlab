"""Candles of any timeframe from smaller ones, cut by the exchange's own session (MW-1).

The chart offers 1m, 3m, 5m, 10m, 15m, 30m, 1h, 2h, 4h, 1D, 1W and 1M. A source sends only some of them (1m, 5m, 15m, 1h and
1D); the rest are built here from the nearest smaller size that divides them. An intraday candle starts on the session's own
clock, not on midnight: India's 2-hour candles start 09:15, 11:15, 13:15 and 15:15 (IST), a US one's start 09:30, 11:30, 13:30
and 15:30 (ET), so a candle never mixes the close of one session with the open of the next. Weekly candles run Monday to
Friday of the exchange's own week and monthly ones are the exchange's calendar month.

Pure functions on lists of {"t": ISO time, "o", "h", "l", "c", "v"}; no network, so a test can check every figure by hand.
Facts only: the first open, the highest high, the lowest low, the last close and the total volume of the candles in each."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# the timeframes the chart offers, in order, with their length in minutes (1D and up are by calendar)
MINUTES = {"1m": 1, "3m": 3, "5m": 5, "10m": 10, "15m": 15, "30m": 30, "1h": 60, "2h": 120, "4h": 240}
TFS = (*MINUTES, "1d", "1w", "1mo")
# what a source sends as it is; every other timeframe is built from one of these
NATIVE = ("1m", "5m", "15m", "1h", "1d")
# the smaller candles each derived timeframe is built from
BASE = {"3m": "1m", "10m": "5m", "30m": "15m", "2h": "1h", "4h": "1h", "1w": "1d", "1mo": "1d"}

# market -> (time zone, minutes after midnight when its trading day starts). A 24-hour market starts its day when the
# exchange's day turns over: crypto and forex at 00:00 UTC, global futures at 18:00 New York time (the evening before).
SESSIONS = {
    "IN": ("Asia/Kolkata", 9 * 60 + 15), "MCX": ("Asia/Kolkata", 9 * 60), "CDS": ("Asia/Kolkata", 9 * 60),
    "US": ("America/New_York", 9 * 60 + 30), "UK": ("Europe/London", 8 * 60), "EU": ("Europe/Berlin", 9 * 60),
    "JP": ("Asia/Tokyo", 9 * 60), "CRYPTO": ("UTC", 0), "FX": ("UTC", 0), "CMDTY": ("America/New_York", 18 * 60),
}


def base_of(tf: str) -> str:
    """The timeframe a source is asked for to build `tf` (itself when the source sends it)."""
    return BASE.get(tf, tf)


def _zone(market: str | None) -> tuple[ZoneInfo, int]:
    tz, start = SESSIONS.get(market or "", ("UTC", 0))
    return ZoneInfo(tz), start


def _parse(t: str, zone: ZoneInfo) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.replace(tzinfo=zone) if d.tzinfo is None else d.astimezone(zone)


def _bucket_start(d: datetime, tf: str, day_start: int) -> datetime:
    """The start, on the exchange's wall clock, of the `tf` candle holding the moment `d` (already in the exchange's zone)."""
    if tf in MINUTES:
        n = MINUTES[tf]
        minutes = d.hour * 60 + d.minute
        since = (minutes - day_start) % 1440               # minutes into the exchange's trading day
        return d.replace(second=0, microsecond=0) - timedelta(minutes=since % n)
    day = d.replace(hour=0, minute=0, second=0, microsecond=0)
    if tf == "1w":
        return day - timedelta(days=d.weekday())
    if tf == "1mo":
        return day.replace(day=1)
    return day


def aggregate(bars: list[dict], tf: str, market: str | None = None) -> list[dict]:
    """`bars` (a smaller timeframe, oldest first) as `tf` candles on `market`'s own session clock. Daily-and-up candles are
    stamped with their first day's time, as the source stamped it; intraday ones with their start. A timeframe the
    source sends is returned as it is."""
    if tf not in BASE or not bars:
        return bars
    zone, day_start = _zone(market)
    out: list[dict] = []
    key = None
    for b in bars:
        d = _parse(b.get("t"), zone)
        if d is None:
            continue
        k = _bucket_start(d, tf, day_start)
        if key is not None and k == key and out:
            last = out[-1]
            last["h"] = max(last["h"], b["h"])
            last["l"] = min(last["l"], b["l"])
            last["c"] = b["c"]
            last["v"] = (last.get("v") or 0) + (b.get("v") or 0)
        else:
            key = k
            t = k.isoformat() if tf in MINUTES else b["t"]
            out.append({"t": t, "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b.get("v") or 0})
    return out


def candle_seconds(tf: str) -> int | None:
    """How long an intraday candle lasts, in seconds (None for a day, week or month, whose end is the session's)."""
    return MINUTES[tf] * 60 if tf in MINUTES else None
