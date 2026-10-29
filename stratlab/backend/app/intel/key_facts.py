"""The plain facts next to a company's AI read: growth, the price trend, debt and cash, margins and returns.

Every line is a number worked out from the reported results or the daily prices, never from AI, and none of it is
a score, grade or "strong/weak" label: the reader sees the numbers and decides what they mean."""
from datetime import date, timedelta

import pandas as pd

from ..deepdive import _series, _years, numbers
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


def _metric_dp(c: dict, group: str, label: str) -> int | None:
    """The decimals the page shows a Key numbers figure with ("dp" 0: the source gives it in whole percent)."""
    for g in c.get("metrics") or []:
        if g.get("title") == group:
            for i in g.get("items") or []:
                if i.get("label") == label:
                    return i.get("dp")
    return None


def _first(*vals):
    return next((v for v in vals if v is not None), None)


def _a_year(v, nm: dict | None = None, unit: str = "") -> str | None:
    """A yearly growth rate; "n/m" with its base when it starts from a tiny one (DD-018: TONBO's "+268.4% a year" from ₹1 cr)."""
    if nm:
        base = nm.get("from")
        if not isinstance(base, (int, float)):
            return "n/m"
        cur, _, word = unit.partition(" ")
        return f"n/m (from a base of {cur}{base:,.0f} {word} in {nm.get('year')})".replace("  ", " ")
    return f"{_pct(v)} a year" if v is not None else None


# ---------- growth ----------
def growth(c: dict, nums: dict | None) -> dict | None:
    """Sales and profit growth, compounded over three and five reported years."""
    g = (nums or {}).get("growth") or {}
    nm = (nums or {}).get("growth_nm") or {}
    u = (nums or {}).get("unit") or ""
    a = lambda v, k: _a_year(v, nm.get(k), u)          # noqa: E731
    sales3 = _first(g.get("sales_cagr_3y"), _metric(c, "Sales growth", "3Y CAGR"), _metric(c, "Growth", "Revenue 3Y"))
    sales5 = _first(g.get("sales_cagr_5y"), _metric(c, "Sales growth", "5Y CAGR"), _metric(c, "Growth", "Revenue 5Y"))
    # never compounded again from the page's profit trend: it leaves blank years out, so three of its points can span
    # five years (R10C-005, the R10V-001 gap); the deep dive's sums keep each blank year as a gap
    profit3 = _first(g.get("profit_cagr_3y"), _metric(c, "Profit growth", "3Y CAGR"))
    profit5 = _first(g.get("profit_cagr_5y"), _metric(c, "Profit growth", "5Y CAGR"))
    return _row("growth", "Growth",
                _item("Sales, 3 years", a(sales3, "sales_cagr_3y")), _item("Sales, 5 years", a(sales5, "sales_cagr_5y")),
                _item("Net profit, 3 years", a(profit3, "profit_cagr_3y")), _item("Net profit, 5 years", a(profit5, "profit_cagr_5y")))


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


def stage_now(closes: list[float]) -> int | None:
    """The Stage on the latest close, from the 150-day average and its 20-day slope: the one computation the company page
    and the watchlist's At a glance both use (DD-071)."""
    if len(closes) < 50:
        return None
    s = stage(pd.Series(closes), 150, 20).iloc[-1]
    return None if pd.isna(s) else int(s)


def closes_of(bars: list[dict] | None) -> list[float]:
    return [x for x in (num(b.get("c")) for b in bars or []) if x is not None and x > 0]


def price_trend(bars: list[dict], page_1y: float | None = None, page_1y_dp: int | None = None) -> dict | None:
    """Where the price sits against its 50- and 200-day averages, its change over a year, and its Stage. The year's
    change is the page's own Key numbers figure when it has one, so the page shows one 1-year return (R6O-008:
    Eni's "1Y return +59.7%" beside "1-year price change +56.8%")."""
    closes = closes_of(bars)
    if len(closes) < 50:
        return None
    last = closes[-1]

    def vs(n):
        if len(closes) < n:
            return None
        avg = sum(closes[-n:]) / n
        d = (last / avg - 1) * 100
        if abs(d) < 0.05:                 # would read "0.0% below": it is at the average (round 39)
            return "level with it"         # beside its own label ("Price vs 200-day average"), not said twice (R45A-015)
        return f"{_pct(abs(d))} {'above' if d >= 0 else 'below'}"
    ago = _year_ago(bars)
    # the year's change to the page's own decimals: a whole-percent figure stays whole, never "-17.0%" beside "-17%" (DD-017)
    year = (f"{page_1y:+.{page_1y_dp}f}%" if page_1y_dp is not None else _pct(page_1y, True)) if page_1y is not None \
        else _pct((last / ago - 1) * 100, True) if ago else None
    return _row("price", "Price trend",
                _item("Price vs 50-day average", vs(50)), _item("Price vs 200-day average", vs(200)),
                _item("1-year price change", year),
                _item("Stage (150-day average)", STAGE.get(stage_now(closes))))


# ---------- debt and cash ----------
def interest_cover_value(pl: dict | None) -> float | None:
    """Profit before interest and tax over interest, for the last full year, as a number; None without both lines, 0.0 for no interest cost."""
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
        return 0.0
    return (pb + it) / it


def _interest_cover(pl: dict | None) -> str | None:
    """The same, as the page writes it: "4.3x", or "no interest cost"."""
    v = interest_cover_value(pl)
    if v is None:
        return None
    return "no interest cost" if v == 0.0 else f"{v:.1f}x"


def _cash_vs_profit(nums: dict | None) -> str | None:
    """Cash from operations as a share of net profit, added up over the last five reported years."""
    rows = [y for y in ((nums or {}).get("years") or [])[-5:] if y.get("cfo") is not None and y.get("profit") is not None]
    if len(rows) < 2:
        return None
    cfo, profit = sum(y["cfo"] for y in rows), sum(y["profit"] for y in rows)
    if profit <= 0:
        return None
    ratio = cfo / profit
    # against a profit that small (cash ten times it or more, or negative), a percentage says nothing: left out
    if ratio >= 10 or ratio <= -10:
        return None
    return f"{ratio * 100:.0f}% of net profit over {len(rows)} years"


def debt_and_cash(c: dict, reported: dict | None, nums: dict | None, s: dict) -> dict | None:
    """Debt to equity, interest cover and cash from operations against profit. Lenders carry debt as their
    business, so for banks these lines don't apply."""
    if (nums or {}).get("bank"):
        return None
    # one definition per figure, and the line says which (R29B-013: 1.34 total here, 0.66 long-term on the page)
    total = _first(s.get("debt_equity"), _metric(c, "Returns and quality", "Total debt / equity"), _metric(c, "Returns and quality", "Debt / equity"))
    de, what = (total, "Total debt / equity") if total is not None else (_metric(c, "Financial health", "Long-term debt / equity"), "Long-term debt / equity")
    if de is None:
        de = _metric(c, "Financial health", "LT debt / equity")
    cover = _interest_cover((reported or {}).get("pl"))
    if cover is None:
        ic = _metric(c, "Financial health", "Interest coverage")
        cover = f"{ic:.1f}x" if ic is not None else None
    return _row("debt", "Debt and cash",
                _item(what, f"{de:.2f}" if de is not None else None),
                _item("Interest cover", cover), _item("Cash from operations", _cash_vs_profit(nums)))


# ---------- margins and returns ----------
def margins_and_returns(c: dict, nums: dict | None, s: dict) -> dict | None:
    """The EBITDA margin year by year over five years (the reported numbers' operating profit is before depreciation),
    else the last twelve months' operating margin (after depreciation) the US company data gives; and the returns on
    capital and equity."""
    years = [y for y in ((nums or {}).get("years") or [])[-5:] if y.get("opm") is not None]
    trend, label = None, "Operating margin"
    if not (nums or {}).get("bank") and len(years) >= 2:
        trend = " → ".join(_pct(y["opm"]).replace(".0%", "%") for y in years) + f" ({years[0]['year']} to {years[-1]['year']})"
        label = f"EBITDA margin, {len(years)} years"          # as many years as it gives (DD-018: "5 years" over four)
    elif (opm := _metric(c, "Profitability", "Operating margin")) is not None:
        trend = f"{_pct(opm)} (last twelve months)"
    roce = _first(s.get("roce"), _metric(c, "Returns and quality", "ROCE"))
    roe = _first(s.get("roe"), _metric(c, "Returns and quality", "ROE"), _metric(c, "Profitability", "ROE"))
    return _row("margins", "Margins and returns",
                _item(label, trend),
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
    page_1y = _first(_metric(c, "Per share and returns", "1Y return"), _metric(c, "Stock price CAGR", "1Y"))
    dp = _metric_dp(c, "Per share and returns", "1Y return") if _metric(c, "Per share and returns", "1Y return") is not None else _metric_dp(c, "Stock price CAGR", "1Y")
    for make in (lambda: growth(c, nums), lambda: price_trend(bars or [], page_1y, dp),
                 lambda: debt_and_cash(c, reported, nums, s), lambda: margins_and_returns(c, nums, s)):
        try:
            r = make()
        except Exception as e:   # one row's bad input never hides the others
            print("key facts:", str(e)[:120])
            r = None
        if r:
            rows.append(r)
    return rows
