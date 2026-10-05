"""India's equity trading sessions, in one dated table: when continuous trading ends for each kind of instrument,
when the closing auction runs, when the derivatives segment closes and when the price that settles expiring
contracts is fixed. The next timetable SEBI or the exchanges set is one more row in TIMES.

What the rows say (checked against the sources on 5 Oct 2026):
- From 3 Aug 2026 (SEBI circular HO/47/11/11(3)2025-MRD-POD2/I/2765/2026 of 16 Jan 2026; NSE/CMTR/74466 and
  NSE/FAOP/74467 of 29 May 2026; go-live confirmed by NSE/CMTR/75479 of 30 Jul 2026):
  - stocks on which derivatives trade on any exchange ("CAS stocks"): continuous trading 09:15-15:15, then a closing
    auction 15:15-15:35 (15:15-15:20 reference price and transition, no orders; 15:20-15:30 order entry, closing at
    random between 15:28 and 15:30; 15:30-15:35 matching). The auction's equilibrium price is the official close; if
    none is found, the reference price (VWAP of 15:00-15:15) is. Stop-loss and iceberg orders, and limit orders
    outside the auction's +/-3% band, are cancelled when continuous trading ends. Post-close session 15:50-16:00 at
    the closing price.
  - every other stock and ETF: continuous trading to 15:30, close = VWAP of the last 30 minutes, as before.
  - the derivatives segment (index and stock futures and options) trades to 15:40.
  - expiry settlement: stock derivatives at the volume-weighted average of the exchanges' auction closes (NSE
    Clearing NCL/CMPT/73370, 19 Mar 2026); index derivatives at the index close, which is computed from its
    constituents' closes (auction prices for CAS stocks). The price is fixed when auction order entry ends (15:30 at
    the latest); before 3 Aug 2026 it was the VWAP of 15:00-15:30. Either way 15:30.
- Indices are not auctioned. During the auction the exchange publishes the index on its constituents' last
  continuous prices and an indicative close on their indicative auction prices.
- No auction on a day trading halts early on an index circuit breaker (closes then revert to the last-30-minute
  VWAP); this table does not model halts.
- SEBI's consultation paper of 12 Sep 2026 (comments to 3 Oct 2026) proposes other timings and settlement prices.
  Proposals only: nothing here changes until a circular sets a date.
"""
from datetime import date, datetime, time, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class Timetable(NamedTuple):
    since: str                         # first trading day these times apply (India time)
    open: str                          # continuous trading starts, cash and derivatives
    cas_end: str                       # continuous trading ends for CAS stocks (stocks with derivatives)
    cash_end: str                      # continuous trading ends for every other stock and ETF
    auction: tuple[str, str] | None    # the closing auction for CAS stocks: starts, matching done (official close out)
    fo_end: str                        # the derivatives segment closes
    settle_at: str                     # the price that settles expiring contracts is fixed by this time
    source: str


# one row per timetable, oldest first
TIMES = [
    Timetable("2000-01-01", "09:15", "15:30", "15:30", None, "15:30", "15:30", "Exchange market hours before the closing auction"),
    Timetable("2026-08-03", "09:15", "15:15", "15:30", ("15:15", "15:35"), "15:40", "15:30",
              "SEBI HO/47/11/11(3)2025-MRD-POD2/I/2765/2026 (16 Jan 2026); NSE/CMTR/74466, NSE/FAOP/74467 (29 May 2026)"),
]
CAS_FROM = TIMES[-1].since if TIMES[-1].auction else None
SOURCES = {
    "sebi": "https://www.sebi.gov.in/legal/circulars/jan-2026/introduction-of-closing-auction-session-cas-in-the-equity-cash-segment-and-certain-modifications-in-the-pre-open-auction-session_99122.html",
    "nse_cash": "https://nsearchives.nseindia.com/content/circulars/CMTR74466.zip",
    "nse_fo": "https://nsearchives.nseindia.com/content/circulars/FAOP74467.zip",
    "settlement": "https://nsearchives.nseindia.com/content/circulars/CMPT73370.zip",
    "consultation": "https://www.sebi.gov.in/reports-and-statistics/reports/sep-2026/consultation-paper-on-review-of-certain-aspects-of-the-closing-auction-session-market-timings-and-settlement-methodologies-for-derivative-contracts-_104464.html",
}
KINDS = ("cas", "cash", "index", "fo")


def _t(hhmm: str) -> time:
    h, m = hhmm.split(":")
    return time(int(h), int(m))


def _day(d) -> date:
    if isinstance(d, datetime):
        return d.astimezone(IST).date() if d.tzinfo else d.date()
    return d if isinstance(d, date) else date.fromisoformat(str(d)[:10])


def timetable(day) -> Timetable:
    """The timetable in force on a day."""
    iso = _day(day).isoformat()
    return [r for r in TIMES if r.since <= iso][-1]


def kind_of(inst: dict | None, derivative_names=()) -> str:
    """"fo" for a futures or options contract, "index" for an index, "cas" for a stock with derivatives on it (its
    close is set by the auction) and "cash" for anything else. `derivative_names` holds the underlyings the
    derivatives segment lists (the stock's symbol, as the instrument list names them)."""
    inst = inst or {}
    if inst.get("fno") or inst.get("exchange") in ("NFO", "BFO"):
        return "fo"
    if inst.get("type") == "INDEX":
        return "index"
    sym = str(inst.get("symbol") or "").upper()
    if inst.get("exchange") in ("NSE", "BSE") and sym and sym in derivative_names:
        return "cas"
    return "cash"


def continuous(kind: str, day) -> tuple[time, time]:
    """(start, end) of continuous trading for a kind of instrument on a day. Index values move until the cash
    market's end."""
    tt = timetable(day)
    end = tt.fo_end if kind == "fo" else tt.cas_end if kind == "cas" else tt.cash_end
    return _t(tt.open), _t(end)


def auction(kind: str, day) -> tuple[time, time] | None:
    """The closing auction (start, matching done) when this kind of instrument closes through one that day."""
    tt = timetable(day)
    return (_t(tt.auction[0]), _t(tt.auction[1])) if kind == "cas" and tt.auction else None


def close_known(kind: str, day) -> time:
    """When the day's official close is out: after the auction's matching for CAS stocks and for indices (their close
    is computed from the constituents' auction prices), at the end of continuous trading otherwise."""
    tt = timetable(day)
    if tt.auction and kind in ("cas", "index"):
        return _t(tt.auction[1])
    return continuous(kind, day)[1]


def settle_at(day) -> time:
    """When the price that settles contracts expiring that day is fixed."""
    return _t(timetable(day).settle_at)


def at(day, t: time) -> datetime:
    """That time of the day, in India."""
    return datetime.combine(_day(day), t, IST)


def fo_close(day) -> time:
    return _t(timetable(day).fo_end)


def describe(day) -> dict:
    """The day's timetable, for pages and the rules register."""
    tt = timetable(day)
    return {"since": tt.since, "open": tt.open, "cas_stocks_continuous_end": tt.cas_end, "other_continuous_end": tt.cash_end,
            "auction": list(tt.auction) if tt.auction else None, "derivatives_close": tt.fo_end,
            "settlement_fixed_by": tt.settle_at, "source": tt.source}


def minutes_after(t: time, minutes: int) -> time:
    return (datetime.combine(date(2000, 1, 3), t) + timedelta(minutes=minutes)).time()
