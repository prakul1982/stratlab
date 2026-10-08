"""One close per Indian stock or ETF across every page (R7O-004, R7O-007).

Daily candles keep a day's last trade. The exchange's official close is a different number: the volume-weighted price
of the session's last half hour, which is what the broker's quote shows after the bell and what the exchange's cash
bhavcopy lists (TCS, 8 Oct 2026: the candle's 2,077.00, the official 2,076.00; ICICIBANK 1,344.90 against 1,349.00;
MOGSEC, a thinly traded G-Sec ETF, 62.50 against 64.87). The company page and the app read the quote; the public
pages, the screens built from them and the ETF table read candles or a last trade. Here every page gets the same
figure: the bhavcopy's close of the day when it is out (stored once a day for every symbol), else the quote's price
when the quote is of that same day, else the candle as it was.

Facts only: a price is replaced only by the exchange's own close of the same day."""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timedelta, timezone

from . import db
from .intel.net import TTLCache

KEY = "closes:IN:"            # closes:IN:<YYYY-MM-DD> = {symbol: close}
KEEP_DAYS = 12                # days of closes kept
PUBLISHED_AT = 18             # India hour after which a day's bhavcopy is asked for
RETRY = 20 * 60               # a day whose file isn't out is asked again after this long
IST = timezone(timedelta(hours=5, minutes=30))
_mem = TTLCache(max_items=40, max_bytes=16 * 1024 * 1024)
_lock = threading.Lock()
_src: dict = {"files": None, "quotes": None}


def setup(files_fn=None, quotes_fn=None, force: bool = False):
    """Where the closes come from: `files_fn()` gives exchange_days.Files (the bhavcopy), `quotes_fn(symbols)` the
    broker's quotes ({symbol: {"price", "at"}}). Either may be None (a server without the broker login). With
    OFFICIAL_CLOSE_FETCH=0 (the tests) nothing is read unless `force`."""
    import os
    if os.environ.get("OFFICIAL_CLOSE_FETCH") == "0" and not force:
        files_fn = quotes_fn = None
    _src["files"], _src["quotes"] = files_fn, quotes_fn


def forget():
    _mem.clear()


def _day(d) -> str:
    return d.isoformat() if isinstance(d, date) else str(d or "")[:10]


def stored(day) -> dict[str, float] | None:
    """A day's official closes as stored; None when that day isn't stored."""
    d = _day(day)
    hit = _mem.get(("day", d))
    if hit is not None:
        return hit or None
    try:
        got = db.json_value(db.get_setting(KEY + d), None)
    except Exception:
        got = None
    rows = {str(k): float(v) for k, v in (got or {}).items() if isinstance(v, (int, float)) and v > 0} if isinstance(got, dict) else {}
    if rows:
        _mem.set(("day", d), rows, 6 * 3600)
    return rows or None


def save(day, rows: dict[str, float]) -> int:
    d = _day(day)
    rows = {str(k).upper(): round(float(v), 2) for k, v in (rows or {}).items() if isinstance(v, (int, float)) and v > 0}
    if not rows:
        return 0
    db.set_setting(KEY + d, json.dumps(rows, separators=(",", ":")))
    _mem.set(("day", d), rows, 6 * 3600)
    _prune(d)
    return len(rows)


def _prune(newest: str):
    try:
        cut = (date.fromisoformat(newest) - timedelta(days=KEEP_DAYS)).isoformat()
        for k, _ in db.all_settings_with_prefix(KEY):
            if k[len(KEY):] < cut:
                db.delete_setting(k)
    except Exception as e:                       # old days left over do no harm
        print("official closes: prune:", str(e)[:120])


def closes(day, now: datetime | None = None) -> dict[str, float] | None:
    """A day's official closes: stored, else read from the exchange's cash bhavcopy once it is published (in the
    evening, India time) and stored. None while it isn't out or can't be read (asked again after RETRY)."""
    d = _day(day)
    got = stored(d)
    if got:
        return got
    files_fn = _src.get("files")
    if not files_fn or not d:
        return None
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    if d > now.date().isoformat() or (d == now.date().isoformat() and now.hour < PUBLISHED_AT):
        return None
    if _mem.get(("asked", d)) is not None:
        return None
    with _lock:
        got = stored(d)
        if got:
            return got
        _mem.set(("asked", d), 1, RETRY)
        try:
            from . import exchange_days
            rows = exchange_days.cash_closes(files_fn(), date.fromisoformat(d)) or {}
        except Exception as e:
            print("official closes:", d, str(e)[:120])
            return None
        n = save(d, {s: r.get("close") for s, r in rows.items() if isinstance(r, dict)})
    return stored(d) if n else None


def settled(day, now: datetime | None = None) -> bool:
    """Whether a day's official closes are in, or will no longer be waited for (the next morning, India time): until
    then the price job keeps looking at the day's pages."""
    d = _day(day)
    if closes(d, now):
        return True
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    try:
        return now >= datetime.combine(date.fromisoformat(d) + timedelta(days=1), datetime.min.time(), IST) + timedelta(hours=9)
    except ValueError:
        return True


def quote_close(symbol: str, day) -> float | None:
    """The broker's quote for a stock when it is of `day` (after the bell its price is the official close)."""
    fn = _src.get("quotes")
    if not fn:
        return None
    try:
        q = (fn([symbol]) or {}).get(symbol.upper()) or {}
    except Exception:
        return None
    if q.get("price") and str(q.get("at") or "")[:10] == _day(day):
        return float(q["price"])
    return None


def official(symbol: str, day, use_quote: bool = True, now: datetime | None = None) -> float | None:
    """The exchange's close of one stock on one day: the bhavcopy's, else (with `use_quote`) a same-day quote's."""
    sym = str(symbol or "").upper()
    got = closes(day, now)
    if got and got.get(sym):
        return got[sym]
    return quote_close(sym, day) if use_quote else None


def overlay_bars(bars: list[dict], symbol: str, use_quote: bool = True, now: datetime | None = None) -> list[dict]:
    """Daily candles with the last one's close set to the exchange's official close of that day (when known), so a
    public page, a screen and the company page show one close. Its high and low widen to take it in, never narrow."""
    if not bars:
        return bars
    last = bars[-1]
    day = str(last.get("t") or "")[:10]
    c = official(symbol, day, use_quote, now) if day else None
    if c is None or c == last.get("c"):
        return bars
    fixed = {**last, "c": c, "h": max(c, last.get("h") or c), "l": min(c, last.get("l") or c), "official": True}
    return bars[:-1] + [fixed]
