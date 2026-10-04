"""The plain facts next to a company's AI read: growth, the price trend, debt and cash, margins and returns.

Every line is a number worked out from the reported results or the daily prices, never from AI, and none of it is
a score, grade or "strong/weak" label: the reader sees the numbers and decides what they mean."""
from datetime import date, timedelta

import pandas as pd

from ..deepdive import _cagr, _series, _years, numbers
from ..engine.indicators import stage
from .net import num
from .screener import summary

STAGE = {1: "Stage 1 (basing)", 2: "Stage 2 (advancing)", 3: "Stage 3 (topping)", 4: "Stage 4 (declining)"}


def _pct(v, signed: bool = False) -> str:
    return f"{v:+.1f}%" if signed else f"{v:.1f}%"


def _item(label: str, text: str | None) -> dict | None:
    return {"label": label, "text": text} if text else None


def _row(rid: str, label: str, *items) -> dict | None:
    items = [i for i in items if i]
    return {"id": rid, "label": label, "items": items} if items else None


def _metric(c: dict, group: str, label: str) -> float | None:
    """One number from the company page's metric groups (what the page itself shows)."""
    for g in c.get("metrics") or []:
        if g.get("title") == group:
            for i in g.get("items") or []:
                if i.get("label") == label:
                    return num(i.get("value"))
    return None


def _first(*vals):
    return next((v for v in vals if v is not None), None)


def _a_year(v) -> str | None:
    return f"{_pct(v)} a year" if v is not None else None


# ---------- growth ----------
def growth(c: dict, nums: dict | None) -> dict | None:
    """Sales and profit growth, compounded over three and five reported years."""
    g = (nums or {}).get("growth") or {}
    trend = c.get("trend") or {}
    profit = [num(p.get("v")) for p in trend.get("profit") or []]
    sales3 = _first(g.get("sales_cagr_3y"), _metric(c, "Sales growth", "3Y CAGR"), _metric(c, "Growth", "Revenue 3Y"))
    sales5 = _first(g.get("sales_cagr_5y"), _metric(c, "Sales growth", "5Y CAGR"), _metric(c, "Growth", "Revenue 5Y"))
    profit3 = _first(g.get("profit_cagr_3y"), _metric(c, "Profit growth", "3Y CAGR"), _cagr(profit, 3))
    profit5 = _first(g.get("profit_cagr_5y"), _metric(c, "Profit growth", "5Y CAGR"), _cagr(profit, 5))
    return _row("growth", "Growth",
                _item("Sales, 3 years", _a_year(sales3)), _item("Sales, 5 years", _a_year(sales5)),
                _item("Net profit, 3 years", _a_year(profit3)), _item("Net profit, 5 years", _a_year(profit5)))


# ---------- the price ----------
def _year_ago(bars: list[dict]) -> float | None:
    """The close about a year before the last one; None when the candles don't reach back that far."""
    try:
        last = date.fromisoformat(str(bars[-1]["t"])[:10])
    except (KeyError, ValueError):
        return None
    cut = (last - timedelta(days=365)).isoformat()
    older = [b for b in bars if str(b.get("t"))[:10] <= (last - timedelta(days=358)).isoformat()]
    if not older:
        return None
    on_or_before = [b for b in older if str(b.get("t"))[:10] <= cut] or older[:1]
    return num(on_or_before[-1].get("c"))


def price_trend(bars: list[dict]) -> dict | None:
    """Where the price sits against its 50- and 200-day averages, its change over a year, and its Stage."""
    closes = [x for x in (num(b.get("c")) for b in bars or []) if x is not None and x > 0]
    if len(closes) < 50:
        return None
    last = closes[-1]

    def vs(n):
        if len(closes) < n:
            return None
        avg = sum(closes[-n:]) / n
        d = (last / avg - 1) * 100
        return f"{_pct(abs(d))} {'above' if d >= 0 else 'below'}"
    ago = _year_ago(bars)
    s = stage(pd.Series(closes), 150, 20).iloc[-1]
    stage_now = None if pd.isna(s) else int(s)
    return _row("price", "Price trend",
                _item("Price vs 50-day average", vs(50)), _item("Price vs 200-day average", vs(200)),
                _item("1-year price change", _pct((last / ago - 1) * 100, True) if ago else None),
                _item("Stage (150-day average)", STAGE.get(stage_now)))


# ---------- debt and cash ----------
def _interest_cover(pl: dict | None) -> str | None:
    """Profit before interest and tax over interest, for the last full year."""
    cols = _years(pl)
    full = [i for i, col in enumerate(cols) if str(col).upper() != "TTM"]
    if not full:
        return None
    i = full[-1]
    interest, pbt = _series(pl, "Interest"), _series(pl, "Profit before tax")
    it = num(interest[i]) if i < len(interest) else None
    pb = num(pbt[i]) if i < len(pbt) else None
    if it is None or pb is None:
        return None
    if it <= 0:
        return "no interest cost"
    return f"{(pb + it) / it:.1f}x"


def _cash_vs_profit(nums: dict | None) -> str | None:
    """Cash from operations as a share of net profit, added up over the last five reported years."""
    rows = [y for y in ((nums or {}).get("years") or [])[-5:] if y.get("cfo") is not None and y.get("profit") is not None]
    if len(rows) < 2:
        return None
    cfo, profit = sum(y["cfo"] for y in rows), sum(y["profit"] for y in rows)
    if profit <= 0:
        return None
    return f"{cfo / profit * 100:.0f}% of net profit over {len(rows)} years"


def debt_and_cash(c: dict, reported: dict | None, nums: dict | None, s: dict) -> dict | None:
    """Debt to equity, interest cover and cash from operations against profit. Lenders carry debt as their
    business, so for banks these lines don't apply."""
    if (nums or {}).get("bank"):
        return None
    de = _first(s.get("debt_equity"), _metric(c, "Returns and quality", "Debt / equity"),
                _metric(c, "Financial health", "LT debt / equity"))
    cover = _interest_cover((reported or {}).get("pl"))
    if cover is None:
        ic = _metric(c, "Financial health", "Interest coverage")
        cover = f"{ic:.1f}x" if ic is not None else None
    return _row("debt", "Debt and cash",
                _item("Debt to equity", f"{de:.2f}" if de is not None else None),
                _item("Interest cover", cover), _item("Cash from operations", _cash_vs_profit(nums)))


# ---------- margins and returns ----------
def margins_and_returns(c: dict, nums: dict | None, s: dict) -> dict | None:
    """The operating margin year by year over five years, and the returns on capital and equity."""
    years = [y for y in ((nums or {}).get("years") or [])[-5:] if y.get("opm") is not None]
    trend = None
    if not (nums or {}).get("bank") and len(years) >= 2:
        trend = " → ".join(_pct(y["opm"]).replace(".0%", "%") for y in years) + f" ({years[0]['year']} to {years[-1]['year']})"
    elif (opm := _metric(c, "Profitability", "Operating margin")) is not None:
        trend = f"{_pct(opm)} (last twelve months)"
    roce = _first(s.get("roce"), _metric(c, "Returns and quality", "ROCE"))
    roe = _first(s.get("roe"), _metric(c, "Returns and quality", "ROE"), _metric(c, "Profitability", "ROE"))
    return _row("margins", "Margins and returns",
                _item("Operating margin, 5 years" if len(years) >= 2 else "Operating margin", trend),
                _item("ROCE", _pct(roce) if roce is not None else None), _item("ROE", _pct(roe) if roe is not None else None))


def build(c: dict, reported: dict | None, bars: list[dict] | None) -> list[dict]:
    """The four rows, from the company page `c`, its reported tables (when there are any) and its daily candles.
    A row with nothing to show is left out."""
    try:
        nums = numbers(reported) if reported and reported.get("pl") else None
    except Exception:            # an odd table: the page's own numbers still stand
        nums = None
    s = summary(reported) if reported else (c.get("summary") or {})
    rows = []
    for make in (lambda: growth(c, nums), lambda: price_trend(bars or []),
                 lambda: debt_and_cash(c, reported, nums, s), lambda: margins_and_returns(c, nums, s)):
        try:
            r = make()
        except Exception as e:   # one row's bad input never hides the others
            print("key facts:", str(e)[:120])
            r = None
        if r:
            rows.append(r)
    return rows
