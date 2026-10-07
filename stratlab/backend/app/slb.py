"""The stock lending (SLB) desk: what lending fees shares actually traded at on the exchange's Securities Lending and
Borrowing segment, for the stocks you hold or watch.

The exchange's daily SLB bhavcopy lists every series that traded that day: the series (named for the month it ends),
its expiry, the lending fee per share (open, high, low, close), the shares lent and the fee paid in all, and the
number of trades. StratLab keeps each day's traded lines (the stock desks' job, exchange_days.py) with the share's
closing price that day, and works out:
- the average fee per share a day's trades paid (fee paid / shares), and that fee as a percent of the share price,
  annualised over the calendar days the series had left;
- for the last 30 and 90 days: the days with any trade, the shares lent and the range of annualised fees.
The exchange's eligibility list says whether a stock can be lent on the segment at all.

Facts with dates. Past traded fees aren't what lending would fetch: demand and fees vary, most stocks see little or no
lending, and StratLab doesn't arrange lending (that goes through an approved intermediary, usually your broker)."""
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from . import exchange_days as X
from .auth import current_profile
from .intel.net import num
from .responses import err, ok

PREFIX = "slb:"
SLB_BHAV = X.ARCHIVE + "/archives/slbs/bhavcopy/SLBM_BC_{dmy}.DAT"
ELIGIBLE = X.ARCHIVE + "/archives/slbs/seclist/SLB_ELG_SEC_{dmy}.csv"
ELIGIBLE_KEY = PREFIX + "eligible"        # {"as_of", "symbols": [...]}
KEEP = 130                                # trading days kept: about six months
WINDOWS = (30, 90)
MAX_SYMBOLS = 120                         # stocks one request can ask about
SYMBOL = re.compile(r"^[A-Z0-9&\-]{1,20}$")
SOURCE = "the exchange's daily SLB bhavcopy and its list of securities eligible for lending"
NOTE = ("Past traded lending fees with their dates, from the exchange's SLB segment. Actual demand and fees vary, many "
        "stocks see no lending on most days, and StratLab doesn't arrange lending: that goes through an approved "
        "intermediary, usually your broker.")
FACTS = [
    ("How it works", "You lend shares you hold for a fixed series (up to about a year) and get a fee per share; the "
                     "borrower returns the same number of shares when the series ends."),
    ("Dividends and corporate actions", "While the shares are lent, the borrower pays you the value of dividends and "
                                        "other corporate-action benefits through the clearing corporation. You can't "
                                        "vote the shares while they're lent."),
    ("Recall", "A lender can ask for the shares back early (a recall) by borrowing back in the market, at that day's "
               "fee, which may differ from the fee earned."),
    ("Tax", "The lending fee is taxed as other income at your slab rate. Lending isn't a sale: the holding period and "
            "the cost of the shares don't change."),
    ("Session", "The SLB segment trades from 9:00 to 17:00 on trading days (from 7 Sep 2026)."),
]


# ---------- reading the files ----------
def _day(v: str) -> str | None:
    from datetime import datetime
    try:
        return datetime.strptime(str(v or "").strip(), "%d-%b-%Y").date().isoformat()
    except ValueError:
        return None


def bhav_rows(text: str) -> tuple[str | None, dict[str, list[list]]]:
    """The SLB bhavcopy: (its trade day, {symbol: [[series, expiry, open, high, low, close, shares, fee paid, trades],
    ...]}). Each line reads: name, symbol, series, expiry, a flag, the previous close, open, high, low and close fee
    per share, a blank, shares, value, the series' high and low, the trade date and the number of trades."""
    out: dict[str, list[list]] = {}
    day = None
    seen = 0
    for line in str(text or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 17:
            continue
        sym, series, exp = parts[1].upper(), parts[2].upper(), _day(parts[3])
        qty, value, trades = num(parts[11]), num(parts[12]), num(parts[16])
        if not SYMBOL.match(sym) or not exp or not qty or qty <= 0:
            continue
        seen += 1
        day = day or _day(parts[15])
        out.setdefault(sym, []).append([series, exp, num(parts[6]), num(parts[7]), num(parts[8]), num(parts[9]),
                                        int(qty), round(value or 0.0, 2), int(trades or 0)])
    if text and text.strip() and not seen and "<html" in text[:300].lower():
        raise ValueError("not the SLB bhavcopy")
    return day, out


def eligible_rows(text: str) -> set[str]:
    """The symbols eligible for lending (normal eligibility "E" in any series)."""
    out = set()
    for r in X.rows_of(text):
        r = {k.lower(): v for k, v in r.items()}
        if (r.get("normal eligibility") or "").upper() == "E" and SYMBOL.match((r.get("symbol") or "").upper()):
            out.add(r["symbol"].upper())
    return out


# ---------- the arithmetic ----------
def avg_fee(line: list) -> float | None:
    """The average fee per share a day's trades in one series paid: fee paid / shares lent."""
    qty, value = line[6], line[7]
    return round(value / qty, 4) if qty and value else None


def annualised(fee: float | None, price: float | None, day: str, expiry: str) -> float | None:
    """A fee per share as a percent of the share price, over the calendar days the series had left, scaled to a year."""
    if not fee or not price or price <= 0:
        return None
    days = (date.fromisoformat(expiry) - date.fromisoformat(day)).days
    if days <= 0:
        return None
    return round(100 * fee / price * 365 / days, 2)


def point(row: dict) -> list | None:
    """A stock's day: [the share's close, [[series, expiry, average fee, annualised %, shares, trades], ...]]."""
    return [row.get("p"), [[ln[0], ln[1], avg_fee(ln), ln_ann, ln[6], ln[8]] for ln, ln_ann in zip(row["l"], row.get("a") or [])]]


def summary(series: list[list], today: str, days: int) -> dict:
    """The last `days` calendar days of a stock's traded lines: days with any trade, shares lent, fee paid, the range
    and share-weighted average of the annualised fee, and the newest trade."""
    since = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    hit = [p for p in series if p[0] > since and p[2]]
    lines = [(p[0], ln) for p in hit for ln in p[2]]
    anns = [(ln[3], ln[4]) for _, ln in lines if ln[3] is not None]
    qty = sum(ln[4] or 0 for _, ln in lines)
    newest = max(lines, key=lambda x: (x[0], x[1][4] or 0)) if lines else None
    return {"days": days, "traded_days": len({d for d, _ in lines}), "shares": qty, "lines": len(lines),
            "fee_paid": round(sum((ln[2] or 0) * (ln[4] or 0) for _, ln in lines), 2),
            "ann_low": min((a for a, _ in anns), default=None), "ann_high": max((a for a, _ in anns), default=None),
            "ann_avg": round(sum(a * q for a, q in anns) / sum(q for _, q in anns), 2) if anns and sum(q for _, q in anns) else None,
            "last": {"day": newest[0], "series": newest[1][0], "expiry": newest[1][1], "fee": newest[1][2], "ann": newest[1][3]} if newest else None}


# ---------- the desk ----------
class Desk(X.Desk):
    name = "slb"
    what = "SLB bhavcopy"
    ready_at = "19:00"
    backfill_days = 95
    store = X.DayStore(PREFIX, KEEP, point, shards=8)

    def read(self, files: X.Files, day: date):
        text = files.text(SLB_BHAV.format(dmy=X.dmy(day)), want=".dat")
        if text is None:
            return None
        got_day, lines = bhav_rows(text)
        if got_day and got_day != day.isoformat():
            return None
        cash = X.cash_closes(files, day) or {}
        rows = {}
        for sym, ls in lines.items():
            price = (cash.get(sym) or {}).get("close")
            rows[sym] = {"p": price, "l": ls, "a": [annualised(avg_fee(ln), price, day.isoformat(), ln[1]) for ln in ls]}
        self._eligible(files, day)
        return rows, {"stocks": len(rows), "lines": sum(len(v) for v in lines.values())}

    def _eligible(self, files: X.Files, day: date):
        """The eligibility list, read with the newest day only (it changes rarely)."""
        cur = X._load(ELIGIBLE_KEY, {})
        if str(cur.get("as_of") or "") >= day.isoformat():
            return
        try:
            text = files.text(ELIGIBLE.format(dmy=X.dmy(day)))
        except Exception:
            return
        syms = eligible_rows(text) if text else set()
        if len(syms) >= 20:                     # the real list has over a thousand; a stub is a broken answer
            X._save(ELIGIBLE_KEY, {"as_of": day.isoformat(), "symbols": sorted(syms)})


DESK = Desk()


def eligible() -> dict:
    return X._load(ELIGIBLE_KEY, {})


# ---------- views ----------
def for_symbol(symbol: str, with_days: bool = True) -> dict:
    """One stock's lending facts: eligibility, the 30- and 90-day summaries and, with `with_days`, each traded line."""
    sym = symbol.upper()
    days = DESK.store.days()
    today = days[-1] if days else None
    elig = eligible()
    ser = DESK.store.series(sym)
    out = {"symbol": sym, "eligible": (sym in set(elig.get("symbols") or [])) if elig.get("symbols") else None,
           "eligible_as_of": elig.get("as_of"), "as_of": today}
    if not today:
        return {**out, "summaries": [], "trades": []}
    out["summaries"] = [summary(ser, today, n) for n in WINDOWS]
    if with_days:
        since = (date.fromisoformat(today) - timedelta(days=max(WINDOWS))).isoformat()
        out["trades"] = [{"day": p[0], "price": p[1], "series": ln[0], "expiry": ln[1], "fee": ln[2], "ann": ln[3],
                          "shares": ln[4], "trades": ln[5]}
                         for p in reversed(ser) if p[0] > since for ln in (p[2] or [])]
    return out


def table(symbols: list[str]) -> dict:
    return {"rows": [for_symbol(s, with_days=False) for s in symbols], "status": X.status(DESK), "note": NOTE,
            "source": SOURCE, "facts": [{"title": t, "text": x} for t, x in FACTS], "windows": list(WINDOWS),
            "coverage": {"days": len(DESK.store.days()), "first": (DESK.store.days() or [None])[0]}}


# ---------- the routes ----------
router = APIRouter(prefix="/invest/stock-lending", tags=["invest"])


@router.get("")
def stock_lending(profile=Depends(current_profile)):
    """Lending fees that traded for the stocks you hold and watch, over the last 30 and 90 days."""
    held, watch = X.mine(profile["id"])
    syms = list(dict.fromkeys(held + watch))[:MAX_SYMBOLS]
    out = table(syms)
    for r in out["rows"]:
        r["held"], r["watched"] = r["symbol"] in held, r["symbol"] in watch
    return ok(out)


@router.get("/{symbol}")
def stock_lending_one(symbol: str, profile=Depends(current_profile)):
    """One stock's traded lending fees, day by day for 90 days."""
    sym = str(symbol or "").upper()
    if not SYMBOL.match(sym):
        err(400, "bad_symbol", "That doesn't look like a stock symbol.")
    return ok({**for_symbol(sym), "status": X.status(DESK), "note": NOTE})
