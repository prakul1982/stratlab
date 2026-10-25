"""The US market calendar a US exchange publishes for every listed company: one call a day for the companies reporting
results that day (with the session, before the open or after the close, they announced), and one for the dividends
going ex that day (with the amount, record and pay dates and the day the company declared it), and one for a month's
IPOs (the offerings expected to price, priced, filed and withdrawn), which the IPO section reads (ipo.py).

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


def _shares(v) -> int | None:
    try:
        n = int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _price_range(v) -> tuple[float | None, float | None]:
    """"14.00-16.00" or "$16.00" or "18.00" as (low, high)."""
    nums = [_amount(x) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", str(v or ""))]
    nums = [n for n in nums if n]
    return (nums[0], nums[-1]) if nums else (None, None)


def ipo_rows(raw: dict) -> list[dict]:
    """A month of the IPO calendar as one row per offering: [{id, stage, symbol, name, exchange, low, high, shares, amount,
    expected, priced, filed, withdrawn}]. stage: "upcoming" (expected to price), "priced" (priced; trading from the next
    session), "filed" (filed with the SEC, no date) or "withdrawn". `id` is the calendar's own deal number."""
    data = ((raw or {}).get("data")) or {}
    out = []

    def rows(block):
        got = ((block or {}).get("upcomingTable") if isinstance(block, dict) and "upcomingTable" in block else block) or {}
        r = got.get("rows") if isinstance(got, dict) else None
        return r if isinstance(r, list) else []

    for stage, block in (("upcoming", data.get("upcoming")), ("priced", data.get("priced")), ("filed", data.get("filed")),
                         ("withdrawn", data.get("withdrawn"))):
        for r in rows(block):
            if not isinstance(r, dict) or not r.get("companyName"):
                continue
            low, high = _price_range(r.get("proposedSharePrice"))
            out.append({"id": str(r.get("dealID") or ""), "stage": stage, "symbol": _symbol(r.get("proposedTickerSymbol")),
                        "name": str(r["companyName"]).strip(), "exchange": str(r.get("proposedExchange") or "").strip() or None,
                        "low": low, "high": high, "shares": _shares(r.get("sharesOffered")),
                        "amount": _amount(r.get("dollarValueOfSharesOffered")),
                        "expected": (d.isoformat() if (d := _day(r.get("expectedPriceDate"))) else None),
                        "priced": (d.isoformat() if (d := _day(r.get("pricedDate"))) else None),
                        "filed": (d.isoformat() if (d := _day(r.get("filedDate"))) else None),
                        "withdrawn": (d.isoformat() if (d := _day(r.get("withdrawDate"))) else None)})
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

    def ipos(self, month: date, ttl: float = 3 * 3600) -> list[dict]:
        """The IPO calendar for the month `month` falls in (expected, priced, filed and withdrawn offerings)."""
        got = self.fetch("https://api.nasdaq.com/api/ipo/calendar", {"date": month.strftime("%Y-%m")}, ttl=ttl)
        if not isinstance(got, dict) or "data" not in got:
            raise SourceError(self.name, f"{self.name} sent something that isn't its calendar.", busy=True)
        return ipo_rows(got)
