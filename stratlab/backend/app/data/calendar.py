"""Which days each exchange trades: weekends and exchange holidays, from the exchange_calendars package.

India uses the BSE calendar (NSE closes on the same days). Crypto trades every day and forex every
weekday, so neither has holidays here. Exchanges publish holidays about a year ahead; beyond what the
installed calendar knows (or if it can't load), a day counts as a trading day when it's a weekday."""
import re
from datetime import date, timedelta
from functools import lru_cache

# MCX follows the NSE/BSE holiday list (on some of those days it reopens for the evening session only,
# which is treated as closed); global commodity futures follow US exchange holidays.
CODES = {"IN": "XBOM", "MCX": "XBOM", "CDS": "XBOM", "US": "XNYS", "CMDTY": "XNYS", "UK": "XLON", "EU": "XETR", "JP": "XTKS"}


@lru_cache(maxsize=None)
def _calendar(code: str):
    try:
        import exchange_calendars as xc
        return xc.get_calendar(code)
    except Exception as e:           # a calendar that won't load must never take the app down
        print("exchange calendar unavailable:", code, str(e)[:200])
        return None


def warm():
    for code in CODES.values():
        _calendar(code)


# India's fixed-date exchange holidays, used for years the installed calendar doesn't cover yet (the moving ones,
# like Diwali and Holi, come from the list the admin pastes in from the exchange each December)
FIXED_IN = [(1, 26), (5, 1), (8, 15), (10, 2), (12, 25)]
SETTING = "holidays:"             # app_settings: holidays:IN = ["2027-03-22", ...], pasted by the admin
AUTO = "holidays-auto:"           # app_settings: holidays-auto:IN = {"days": [...], "at": ISO}, fetched from the exchange
_extra: dict[str, tuple[float, set]] = {}


def extra_holidays(market: str) -> set:
    """Holidays the admin added (the exchange's published list), cached for ten minutes."""
    import json
    import time
    if market == "CDS":               # the currency segment: the equity list plus its own extra closures
        return extra_holidays("IN") | _stored("CDS")
    key = "IN" if market == "MCX" else market
    hit = _extra.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    days: set = set()
    try:
        from .. import db
        raw = db.get_setting(SETTING + key)
        days = {str(d)[:10] for d in json.loads(raw)} if raw else set()
        auto = json.loads(db.get_setting(AUTO + key) or "{}")
        days |= {str(d)[:10] for d in auto.get("days") or []}
    except Exception:                 # no database (tests, an outage): the built-in calendar alone
        days = hit[1] if hit else set()
    _extra[key] = (time.time(), days)
    return days


def _stored(key: str) -> set:
    import json
    import time
    hit = _extra.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        from .. import db
        days = {str(d)[:10] for d in json.loads(db.get_setting(AUTO + key) or "{}").get("days") or []}
    except Exception:
        days = hit[1] if hit else set()
    _extra[key] = (time.time(), days)
    return days


def auto_status(market: str = "IN") -> dict:
    import json
    try:
        from .. import db
        return json.loads(db.get_setting(AUTO + market) or "{}")
    except Exception:
        return {}


def refresh_from_exchange(fetch, market: str = "IN") -> dict:
    """Fetch the exchange's holiday list and keep it (added to what was fetched before, so past years stay).
    `fetch()` returns ISO dates. A failure is recorded and the last good list kept."""
    import json
    from datetime import datetime, timezone
    from .. import db
    prev = auto_status(market)
    now = datetime.now(timezone.utc).isoformat()
    try:
        got = [d for d in fetch() if _iso(d)]
    except Exception as e:
        state = {**prev, "error": str(e)[:200], "tried_at": now}
        db.set_setting(AUTO + market, json.dumps(state))
        return state
    days = sorted(set(prev.get("days") or []) | set(got))
    state = {"days": days, "at": now, "tried_at": now, "error": None, "latest": max(got)}
    db.set_setting(AUTO + market, json.dumps(state))
    _extra.pop(market, None)
    _holiday_cache.clear()
    return state


def set_extra_holidays(market: str, days: list[str]) -> list[str]:
    import json
    from .. import db
    clean = sorted({d for d in (str(x).strip()[:10] for x in days) if _iso(d)})
    db.set_setting(SETTING + market, json.dumps(clean))
    _extra.pop(market, None)
    _holiday_cache.clear()
    return clean


def _iso(d: str) -> bool:
    try:
        date.fromisoformat(d)
        return True
    except ValueError:
        return False


def known_until(market: str) -> date | None:
    """The last day the installed calendar has the exchange's holidays for."""
    cal = _calendar(CODES[market]) if market in CODES else None
    try:
        return cal.last_session.date() if cal is not None else None
    except Exception:
        return None


def is_trading_day(market: str, day: date) -> bool:
    if market == "CRYPTO":
        return True
    if market == "CMDTY" and day.weekday() == 6:
        return False                          # Sunday evening's open counts toward Monday
    if day.weekday() >= 5:
        return False
    if market in ("IN", "MCX", "CDS") and day.isoformat() in extra_holidays(market):
        return False
    cal = _calendar(CODES[market]) if market in CODES else None
    if cal is None:
        return not (market in ("IN", "MCX", "CDS") and (day.month, day.day) in FIXED_IN)
    try:
        if not (cal.first_session.date() <= day <= cal.last_session.date()):
            # past the published calendar: weekdays count, bar India's fixed national holidays
            return not (market in ("IN", "MCX", "CDS") and (day.month, day.day) in FIXED_IN)
        return bool(cal.is_session(day.isoformat()))
    except Exception:
        return True


# Markets that don't trade at weekends, whose candles come from a feed that can still carry a weekend row (a stray
# Sunday print, a placeholder). Crypto trades every day. India's own exchange feed is taken as it comes: a special
# weekend session (Diwali's Muhurat trading) is a real one.
WEEKDAY_FEEDS = ("US", "UK", "EU", "JP", "FX", "CMDTY")
SUNDAY_EVENING = ("FX", "CMDTY")       # their week opens on Sunday evening: those intraday candles are real


def trading_bars(market: str | None, bars: list[dict], tf: str) -> list[dict]:
    """Only the candles of days the market trades: no weekend candles for a weekday market. Daily candles dated on a
    Saturday or Sunday are dropped; intraday candles on a Saturday too, and on a Sunday except where the week opens on
    Sunday evening (forex, global futures). Candle times are in the exchange's own zone, so the date is the local one."""
    if market not in WEEKDAY_FEEDS or not bars:
        return bars

    def keep(b: dict) -> bool:
        try:
            wd = date.fromisoformat(str(b["t"])[:10]).weekday()
        except ValueError:
            return True
        if wd == 5:
            return False
        return wd != 6 or (tf != "1d" and market in SUNDAY_EVENING)
    out = [b for b in bars if keep(b)]
    return out if len(out) != len(bars) else bars


def is_holiday(market: str, day: date) -> bool:
    """A weekday the exchange is closed."""
    return day.weekday() < 5 and not is_trading_day(market, day)


_holiday_cache: dict = {}


def holidays(market: str, start: date, days: int = 60) -> list[str]:
    """Weekday closures from `start` over the next `days` days, as ISO dates in the exchange's own calendar. Asked on
    every page (the sidebar's market hours), so kept for ten minutes; a refreshed holiday list shows within that."""
    if market not in CODES:
        return []
    import time
    key = (market, start.isoformat(), days)
    hit = _holiday_cache.get(key)
    if hit and time.monotonic() - hit[0] < 600:
        return list(hit[1])
    out = [d.isoformat() for d in (start + timedelta(n) for n in range(days)) if is_holiday(market, d)]
    if len(_holiday_cache) > 500:
        _holiday_cache.clear()
    _holiday_cache[key] = (time.monotonic(), out)
    return list(out)


# Admin → Exchange holidays: every market, where its holidays come from and how far ahead they're known
LISTED = ("IN", "MCX", "CDS")                 # the exchange's own list, read daily (MCX keeps the NSE/BSE days)
NAMES = {"IN": "India (NSE/BSE)", "MCX": "MCX", "CDS": "Currency F&O", "US": "US", "UK": "UK", "EU": "Europe",
         "JP": "Japan", "CMDTY": "Commodities", "CRYPTO": "Crypto", "FX": "Forex"}
FIXED_IN_NAMES = {(1, 26): "Republic Day", (5, 1): "Maharashtra Day", (8, 15): "Independence Day",
                  (10, 2): "Gandhi Jayanti", (12, 25): "Christmas"}
ENOUGH_DAYS = 60                              # fewer days of known holidays than this is worth a look


def covered_until(market: str) -> date | None:
    """The last day this market's holidays are known: what the installed calendar covers, or for India's segments
    the exchange's list too (it covers its whole year, so to 31 Dec of the latest year it lists) and any pasted day."""
    until = known_until(market)
    ends = [until] if until else []
    if market in LISTED:
        ends += [date.fromisoformat(d) for d in extra_holidays(market)]
        years = [int(str(d)[:4]) for k in (("IN", "CDS") if market == "CDS" else ("IN",))
                 for d in auto_status(k).get("days") or [] if _iso(str(d)[:10])]
        if years:
            ends.append(date(max(years), 12, 31))
    return max(ends) if ends else None


def holiday_name(market: str, day: date) -> str | None:
    """The holiday's name when the calendar has one (built-in rules do; the exchange's list gives dates only)."""
    if market in LISTED and (day.month, day.day) in FIXED_IN_NAMES:
        return FIXED_IN_NAMES[(day.month, day.day)]
    cal = _calendar(CODES[market]) if market in CODES else None
    try:
        import pandas as pd
        names = cal.regular_holidays.holidays(pd.Timestamp(day), pd.Timestamp(day), return_name=True)
        return re.sub(r"\s*\([^)]*\)$", "", str(names.iloc[0])) if len(names) else None   # "(2022 onwards)"
    except Exception:
        return None


def coverage(market: str, today: date) -> dict:
    """One row of the admin's holiday table: source, how far ahead holidays are known, the next one and a status."""
    row = {"market": market, "name": NAMES.get(market, market), "known_until": None, "days_left": None,
           "next": None, "next_name": None, "state": "none", "hint": None}
    if market not in CODES:
        return {**row, "source": "No exchange holidays (24/7 / weekdays)"}
    row["source"] = "Exchange's own list, read daily" if market in LISTED else "Built-in calendar rules"
    until = covered_until(market)
    if until is None:
        return {**row, "state": "warn", "hint": "No holiday calendar loaded: update the exchange_calendars package."}
    left = (until - today).days
    ahead = holidays(market, today, max(0, min(left + 1, 400)))
    nxt = date.fromisoformat(ahead[0]) if ahead else None
    ok = left >= ENOUGH_DAYS
    hint = None if ok else ("Read the exchange's list now, or paste it below." if market in LISTED
                            else "Update the exchange_calendars package.")
    return {**row, "known_until": until.isoformat(), "days_left": left, "next": nxt.isoformat() if nxt else None,
            "next_name": holiday_name(market, nxt) if nxt else None, "state": "ok" if ok else "warn", "hint": hint}


def all_coverage(today: date) -> list[dict]:
    return [coverage(m, today) for m in NAMES]
