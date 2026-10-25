"""The US market calendar a US exchange publishes for every listed company: one call a day for the companies reporting
results that day (with the session, before the open or after the close, they announced), and one for the dividends
going ex that day (with the amount, record and pay dates and the day the company declared it).

The results calendar and the corporate actions calendar read it for the whole market (DE-025, DE-028): the earnings
feed it complemented came back empty in the middle of the reporting season, and a price history only holds ex-dates
that have already happened. The source's name is never shown to users."""
import re
from datetime import date, datetime

import httpx

from .net import BROWSER_UA, Source, SourceError

WHEN = {"time-pre-market": "bmo", "time-after-hours": "amc"}        # results.WHEN's codes; "time-not-supplied" is none


def _day(s) -> date | None:
    """10/30/2026 (or 9/03/2026) as a date."""
    try:
        return datetime.strptime(str(s or "").strip(), "%m/%d/%Y").date()
    except ValueError:
        return None


def _symbol(s) -> str | None:
    """A US ticker as the app writes it (BRK.B as BRK-B is the SEC's; the calendar writes BRK/B or BRK.B)."""
    sym = re.sub(r"[/.]", "-", str(s or "").strip().upper())
    return sym if re.fullmatch(r"[A-Z0-9][A-Z0-9\-]{0,11}", sym) else None


def _amount(v) -> float | None:
    try:
        f = float(str(v).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def earnings_rows(raw: dict, day: date) -> list[dict]:
    """The companies reporting on `day`: [{symbol, name, date, hour, period}], in the shape the results calendar reads
    (hour "bmo"/"amc" or None; period "Sep/2026", the fiscal quarter's end)."""
    rows = (((raw or {}).get("data") or {}).get("rows")) or []
    out = []
    for r in rows if isinstance(rows, list) else []:
        sym = _symbol((r or {}).get("symbol"))
        if not sym:
            continue
        out.append({"symbol": sym, "name": str(r.get("name") or "").strip() or None, "date": day.isoformat(),
                    "hour": WHEN.get(str(r.get("time") or "")), "period": str(r.get("fiscalQuarterEnding") or "").strip() or None})
    return out


def dividend_rows(raw: dict) -> list[dict]:
    """The dividends going ex on the day asked for: [{symbol, name, ex_date, record_date, pay_date, declared, amount}]."""
    rows = ((((raw or {}).get("data") or {}).get("calendar") or {}).get("rows")) or []
    out = []
    for r in rows if isinstance(rows, list) else []:
        sym, ex, amt = _symbol((r or {}).get("symbol")), _day((r or {}).get("dividend_Ex_Date")), _amount((r or {}).get("dividend_Rate"))
        if not sym or not ex or not amt:
            continue
        rec, pay, said = (_day(r.get(k)) for k in ("record_Date", "payment_Date", "announcement_Date"))
        out.append({"symbol": sym, "name": str(r.get("companyName") or "").strip() or None, "ex_date": ex.isoformat(),
                    "record_date": rec.isoformat() if rec else None, "pay_date": pay.isoformat() if pay else None,
                    "declared": said.isoformat() if said else None, "amount": round(amt, 4)})
    return out


class USCalendar(Source):
    name = "The US market calendar"
    STALE_FOR = 0                 # a day's list changes as companies announce: an old copy is never passed off as today's

    def __init__(self, transport: httpx.BaseTransport | None = None):
        super().__init__("https://api.nasdaq.com/api/calendar", per_minute=30, burst=6, transport=transport,
                         headers={"User-Agent": BROWSER_UA, "Accept": "application/json, text/plain, */*",
                                  "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"})

    def _day_list(self, path: str, day: date, ttl: float):
        got = self.fetch(path, {"date": day.isoformat()}, ttl=ttl)
        if not isinstance(got, dict) or "data" not in got:
            raise SourceError(self.name, f"{self.name} sent something that isn't its calendar.", busy=True)
        return got

    def earnings(self, day: date, ttl: float = 3 * 3600) -> list[dict]:
        return earnings_rows(self._day_list("/earnings", day, ttl), day)

    def dividends(self, day: date, ttl: float = 6 * 3600) -> list[dict]:
        return dividend_rows(self._day_list("/dividends", day, ttl))
