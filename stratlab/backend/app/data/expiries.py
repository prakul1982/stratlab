"""Which Indian index options expire weekly and which monthly, and the exchanges' expiry-day rule.

- Weekly expiries: from 20 Nov 2024 (SEBI's circular of 1 Oct 2024 on equity index derivatives) each exchange keeps
  weekly options on one benchmark index only: NSE on NIFTY 50, BSE on SENSEX. Every other index option (BANKNIFTY,
  FINNIFTY, MIDCPNIFTY, NIFTYNXT50 on NSE; BANKEX, SENSEX50 on BSE) and every stock option expires monthly.
- The day: from 1 Sep 2025 NSE's equity derivatives expire on Tuesdays and BSE's on Thursdays (before that, NSE's on
  Thursdays and BSE's on Tuesdays). A monthly expiry is the month's last such day. An expiry that falls on an exchange
  holiday moves to the trading day before.

The broker's contract list is what the app trades; these rules check it (an expiry a monthly-only index can't have is
dropped) and stand in for it where nothing is listed (the demo feed, the calendar). Commodity (MCX) and currency (CDS)
options follow their own exchanges' lists and are left as listed.
"""
from datetime import date, timedelta

from .calendar import is_trading_day

WEEKLY = {("NFO", "NIFTY"), ("BFO", "SENSEX")}
MONTHLY_ONLY_FROM = date(2024, 11, 20)        # the last weekly BANKNIFTY, FINNIFTY and MIDCPNIFTY expiries were before this
DAY_CHANGE = date(2025, 9, 1)                 # NSE moved to Tuesdays, BSE to Thursdays
RULED = ("NFO", "BFO")                        # the equity derivative segments these rules cover


def cycle(exchange: str, name: str) -> str | None:
    """'weekly' or 'monthly' for an NSE or BSE equity option; None for commodity and currency options."""
    if exchange not in RULED:
        return None
    return "weekly" if (exchange, name) in WEEKLY else "monthly"


def weekday(exchange: str, day: date) -> int:
    """The weekday (Monday 0) the exchange's equity options expire on around `day`."""
    if exchange == "BFO":
        return 3 if day >= DAY_CHANGE else 1
    return 1 if day >= DAY_CHANGE else 3


def trading_on_or_before(d: date, market: str = "IN") -> date:
    """`d`, or the trading day before it when the exchange is shut."""
    for _ in range(10):
        try:
            if is_trading_day(market, d):
                return d
        except Exception:
            return d
        d -= timedelta(days=1)
    return d


def monthly_expiry(exchange: str, year: int, month: int) -> date:
    """The month's last expiry weekday, moved to the trading day before on a holiday."""
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    d = last - timedelta(days=(last.weekday() - weekday(exchange, last)) % 7)
    return trading_on_or_before(d)


def fits(exchange: str, name: str, expiry: str | date) -> bool:
    """Whether an expiry can be one of this option's: any day for a weekly index, commodity and currency options or a
    day before monthly-only began; for a monthly-only option, only its month's last expiry (no expiry weekday later in
    the same month, a holiday's day-earlier move included)."""
    d = expiry if isinstance(expiry, date) else date.fromisoformat(str(expiry)[:10])
    if cycle(exchange, name) != "monthly" or d < MONTHLY_ONLY_FROM:
        return True
    return (d + timedelta(days=7)).month != d.month or d == monthly_expiry(exchange, d.year, d.month)


def keep_listed(exchange: str, name: str, expiries: list[str]) -> list[str]:
    """The listed expiries an option really has: a monthly-only index never shows a weekly date."""
    return [e for e in expiries if fits(exchange, name, e)]


def rule_expiries(exchange: str, name: str, start: date, count: int = 4) -> list[date]:
    """The next `count` expiries on or after `start` by the exchange's rule, for when no contract list is at hand."""
    out: list[date] = []
    if cycle(exchange, name) == "monthly":
        y, m = start.year, start.month
        while len(out) < count:
            e = monthly_expiry(exchange, y, m)
            if e >= start:
                out.append(e)
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return out
    d = start
    while len(out) < count:
        if d.weekday() == weekday(exchange, d):
            e = trading_on_or_before(d)
            if e >= start and e not in out:
                out.append(e)
        d += timedelta(days=1)
    return out
