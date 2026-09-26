"""Which days each exchange trades: weekends and exchange holidays, from the exchange_calendars package.

India uses the BSE calendar (NSE closes on the same days). Crypto trades every day and forex every
weekday, so neither has holidays here. Exchanges publish holidays about a year ahead; beyond what the
installed calendar knows (or if it can't load), a day counts as a trading day when it's a weekday."""
from datetime import date, timedelta
from functools import lru_cache

# MCX follows the NSE/BSE holiday list (on some of those days it reopens for the evening session only,
# which is treated as closed); global commodity futures follow US exchange holidays.
CODES = {"IN": "XBOM", "MCX": "XBOM", "US": "XNYS", "CMDTY": "XNYS", "UK": "XLON", "EU": "XETR", "JP": "XTKS"}


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


def is_trading_day(market: str, day: date) -> bool:
    if market == "CRYPTO":
        return True
    if market == "CMDTY" and day.weekday() == 6:
        return False                          # Sunday evening's open counts toward Monday
    if day.weekday() >= 5:
        return False
    cal = _calendar(CODES[market]) if market in CODES else None
    if cal is None:
        return True
    try:
        if not (cal.first_session.date() <= day <= cal.last_session.date()):
            return True
        return bool(cal.is_session(day.isoformat()))
    except Exception:
        return True


def is_holiday(market: str, day: date) -> bool:
    """A weekday the exchange is closed."""
    return day.weekday() < 5 and not is_trading_day(market, day)


def holidays(market: str, start: date, days: int = 60) -> list[str]:
    """Weekday closures from `start` over the next `days` days, as ISO dates in the exchange's own calendar."""
    if market not in CODES:
        return []
    return [d.isoformat() for d in (start + timedelta(n) for n in range(days)) if is_holiday(market, d)]
