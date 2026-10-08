"""One close per stock across the pages (R6O-009).

The screener and the trend scans read the day's close from daily candles; the company page, the watchlist and holdings
read the exchange's quote. After the close they can differ by a rupee: the candle keeps the last trade, the quote the
exchange's official close (TCS, 8 Oct 2026: Rs 2,077.00 -0.16% on the screener and scan, Rs 2,076.00 -0.21% everywhere
else, which is NSE's close). So for Indian stocks the rows of a screen or a scan take the NSE quote's price and change
whenever the quote is for the same day as the row, and say so (`price_source`)."""
from __future__ import annotations


def overlay(rows: list[dict], quotes: dict[str, dict], day_key: str, change_key: str | None = None) -> list[dict]:
    """The rows with the quote's price (and change) where the quote is for the row's own day. `day_key` names the row's
    field holding its price's day ("price_at", "as_of", "t"); a row without a same-day quote is left as it is."""
    out = []
    for r in rows:
        q = quotes.get(str(r.get("symbol") or "").upper()) or {}
        day = str(r.get(day_key) or "")[:10]
        if q.get("price") is not None and day and str(q.get("at") or "")[:10] == day:
            r = {**r, "price": q["price"], "price_source": "NSE"}
            if change_key and q.get("change_pct") is not None:
                r[change_key] = q["change_pct"]
        out.append(r)
    return out
