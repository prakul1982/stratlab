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
_mem = TTLCache(max_items=2000, max_bytes=16 * 1024 * 1024)
_lock = threading.Lock()
_src: dict = {"files": None, "quotes": None, "all": None}
QUOTES_FOR = 10 * 60          # how long the broker's after-the-close quotes of every stock are reused
QUOTES_EARLY = 60             # ...and in the first minutes after the auction, while a quote may still be catching up


def setup(files_fn=None, quotes_fn=None, force: bool = False, all_quotes_fn=None):
    """Where the closes come from: `files_fn()` gives exchange_days.Files (the bhavcopy), `quotes_fn(symbols)` the
    broker's quotes ({symbol: {"price", "at"}}), `all_quotes_fn()` the same for every NSE stock in one go (read after
    the close, in batches). Any may be None (a server without the broker login). With OFFICIAL_CLOSE_FETCH=0 (the
    tests) nothing is read unless `force`."""
    import os
    if os.environ.get("OFFICIAL_CLOSE_FETCH") == "0" and not force:
        files_fn = quotes_fn = all_quotes_fn = None
    _src["files"], _src["quotes"], _src["all"] = files_fn, quotes_fn, all_quotes_fn


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
    _mem.pop(("none", d))
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


def quote_close(symbol: str, day, now: datetime | None = None) -> float | None:
    """The broker's quote for a stock when it is of `day` (after the bell its price is the official close). Never before
    that day's closing auction has matched: until then the quote is the last continuous trade (R8B-001)."""
    fn = _src.get("quotes")
    if not fn:
        return None
    try:
        if (now or datetime.now(timezone.utc)) < out_at(day):
            return None
    except ValueError:
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
    return quote_close(sym, day, now) if use_quote else None


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


# ---------- the daily candles every reader gets (R8B-001) ----------
# The broker's daily candle of an Indian stock keeps the session's last continuous trade until its own end-of-day run,
# which for a stock with derivatives is the 15:15 price, before the closing auction (TCS, 9 Oct 2026: the candle's
# 2,171.50 at 16:46 IST against the official close of 2,156.00; the My Stocks email of 16:19 IST said "TCS 2,171.50
# ▲ 4.60%" from it). Every daily candle read from the broker (the charts, the scans and screens, the briefs and My
# Stocks, the alerts that read candles, backtests and paper trading) goes through history_close, which sets a day's
# close to the exchange's: the bhavcopy's once it is out, else, once the auction has matched, the broker's quote of that
# day when its last trade is from the auction or after it (no stock with derivatives trades between 15:15 and the
# auction's match, so such a trade is the auction's or the post-close session's, both at the official close).
def base_symbol(symbol: str) -> str:
    """An NSE symbol as the exchange's files name it: without the broker's "-BE"-style series suffix."""
    sym = str(symbol or "").upper()
    head, _, tail = sym.rpartition("-")
    return head if head and tail in ("BE", "BZ", "SM", "ST", "SZ", "GB", "RR", "IV") else sym


def out_at(day, kind: str = "cas") -> datetime:
    """When a day's official close is out for a kind of stock ("cas": a stock with derivatives, once its closing
    auction has matched; "cash": any other stock, its close is the last half hour's average when continuous trading
    ends)."""
    from .data import sessions as S
    d = date.fromisoformat(_day(day))
    return S.at(d, S.close_known(kind, d))


def _traded_from(day, kind: str) -> datetime:
    """A trade at or after this time of the day is at the official close: the auction's or the post-close session's."""
    from .data import sessions as S
    d = date.fromisoformat(_day(day))
    return S.at(d, S.continuous(kind, d)[1])


def _stored_quick(d: str) -> dict[str, float] | None:
    """stored(), with a day that isn't stored remembered as such for two minutes (a chart asks many times a minute)."""
    if _mem.get(("none", d)) is not None:
        return None
    got = stored(d)
    if not got:
        _mem.set(("none", d), 1, 120)
    return got


def _all_quotes(now: datetime) -> dict:
    """Every NSE stock's quote, read in one go after the close and reused for a few minutes."""
    fn = _src.get("all")
    if not fn:
        return {}
    hit = _mem.get(("allq",))
    if hit is not None:
        return hit
    with _lock:
        hit = _mem.get(("allq",))
        if hit is not None:
            return hit
        try:
            got = {base_symbol(k): v for k, v in (fn() or {}).items() if isinstance(v, dict)}
        except Exception as e:
            print("official closes: quotes:", str(e)[:120])
            got = {}
        early = now.astimezone(IST) < out_at(now.astimezone(IST).date()) + timedelta(minutes=5)
        _mem.set(("allq",), got, QUOTES_EARLY if early or not got else QUOTES_FOR)
    return got


def _quote_of(symbol: str, exchange: str, now: datetime) -> dict | None:
    if exchange == "NSE" and _src.get("all"):
        return _all_quotes(now).get(base_symbol(symbol))
    key = ("q1", exchange, str(symbol).upper())
    hit = _mem.get(key)
    if hit is not None:
        return hit or None
    fn = _src.get("quotes")
    if not fn:
        return None
    try:
        got = (fn([symbol]) or {}).get(str(symbol).upper()) or {}
    except Exception:
        got = {}
    _mem.set(key, got, QUOTES_EARLY)
    return got or None


def day_close(symbol: str, day, kind: str = "cas", exchange: str = "NSE", now: datetime | None = None,
              fetch: bool = True) -> float | None:
    """The exchange's close of one stock on one day, for its daily candle: None until it is out (for a stock with
    derivatives, once the auction has matched), then the bhavcopy's (stored, or read once it is published; with
    `fetch` False only stored) or, for the day itself, the quote of that day whose last trade is the auction's or later."""
    d = _day(day)
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    try:
        if now < out_at(d, kind):
            return None
    except ValueError:
        return None
    sym = base_symbol(symbol) if exchange == "NSE" else str(symbol or "").upper()
    got = None
    if exchange == "NSE":                             # the exchange's file names NSE's stocks
        got = _stored_quick(d)
        if not got and fetch and _src.get("files") and (d < now.date().isoformat() or now.hour >= PUBLISHED_AT):
            got = closes(d, now)
    if got and got.get(sym):
        return got[sym]
    if d != now.date().isoformat():
        return None                                   # an older day is set from the exchange's file only
    q = _quote_of(symbol, exchange, now)
    if not q or not q.get("price") or str(q.get("at") or "")[:10] != d:
        return None
    try:
        at = datetime.fromisoformat(str(q["at"]))
    except ValueError:
        return None
    at = at if at.tzinfo else at.replace(tzinfo=IST)
    if at < _traded_from(d, kind):
        return None                                   # its last trade is from before the close: not the official close
    return float(q["price"])


def history_close(bars: list[dict], symbol: str, kind: str = "cas", exchange: str = "NSE",
                  now: datetime | None = None) -> list[dict]:
    """A stock's daily candles with each recent day's close set to the exchange's official close (day_close): the
    bhavcopy's for the days it is stored, and the latest day's as soon as it is out. High and low widen to take the close
    in, never narrow. The candles given are never changed in place (they are the broker's cached copy)."""
    if not bars:
        return bars
    now = (now or datetime.now(timezone.utc)).astimezone(IST)
    cut = (now.date() - timedelta(days=KEEP_DAYS)).isoformat()
    out = None
    for i in range(len(bars) - 1, -1, -1):
        b = bars[i]
        d = str(b.get("t") or "")[:10]
        if not d or d < cut:
            break
        c = day_close(symbol, d, kind, exchange, now, fetch=i == len(bars) - 1)
        if c is None or (c == b.get("c") and b.get("official")):
            continue
        if out is None:
            out = list(bars)
        out[i] = {**b, "c": c, "h": max(c, b.get("h") or c), "l": min(c, b.get("l") or c), "official": True}
    return out if out is not None else bars
