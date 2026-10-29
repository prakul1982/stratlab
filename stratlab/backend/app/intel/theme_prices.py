"""A theme's price picture from its companies' daily closes (THEME-1): returns over one, three and twelve months and three years, how
many of the companies are above their 200-day average or near a 52-week extreme, and an equal-weighted line for the theme set
against the market's own index (its relative strength over time).

Each company's candles are reduced at once to a few numbers and 160 weekly closes (`reduce_bars`), so a theme never keeps a company's
whole history; the reduced figures are what the caller keeps for the rest of the session. Facts and arithmetic only."""
from datetime import date, datetime, timedelta
from statistics import median

PERIODS = (("1M", 30), ("3M", 91), ("1Y", 365), ("3Y", 1095))
WEEKS = 160                                   # weekly closes kept for a company: three years and a bit
WEEK_RETURNS = {"1M": 4, "3M": 13, "1Y": 52, "3Y": 156}
NEAR_HIGH, NEAR_LOW = 0.05, 0.10             # within 5% below the 52-week closing high, within 10% above the closing low


def _day(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _pairs(bars: list[dict]) -> list[tuple[date, float]]:
    out = {}
    for b in bars or []:
        d, c = _day(b.get("t")), b.get("c")
        if d and isinstance(c, (int, float)) and c > 0:
            out[d] = float(c)
    return sorted(out.items())


def change(pairs: list[tuple[date, float]], days: int) -> float | None:
    """The price change in percent from the last close on or before (last day - days) to the last close; None when the candles
    don't reach back that far."""
    if len(pairs) < 2:
        return None
    last_d, last_c = pairs[-1]
    target = last_d - timedelta(days=days)
    if pairs[0][0] > target:
        return None
    base = None
    for d, c in pairs:
        if d <= target:
            base = c
        else:
            break
    return round((last_c / base - 1) * 100, 1) if base else None


def reduce_bars(bars: list[dict]) -> dict | None:
    """One company's candles as a few numbers: {"last", "date", "ret": {1M, 3M, 1Y, 3Y}, "above200", "above50", "near_high", "near_low",
    "weeks": [Friday ordinals], "closes": [weekly closes]}; None without two closes."""
    pairs = _pairs(bars)
    if len(pairs) < 2:
        return None
    closes = [c for _, c in pairs]
    last_d, last = pairs[-1]
    year = [c for d, c in pairs if d > last_d - timedelta(days=365)]
    hi, lo = max(year), min(year)
    weekly: dict[int, float] = {}
    for d, c in pairs:
        friday = d + timedelta(days=(4 - d.weekday()) % 7 if d.weekday() <= 4 else -(d.weekday() - 4))
        weekly[friday.toordinal()] = c
    keys = sorted(weekly)[-WEEKS:]
    return {"last": last, "date": last_d.isoformat(), "ret": {k: change(pairs, n) for k, n in PERIODS},
            "above200": (last > sum(closes[-200:]) / 200) if len(closes) >= 200 else None,
            "above50": (last > sum(closes[-50:]) / 50) if len(closes) >= 50 else None,
            "near_high": last >= hi * (1 - NEAR_HIGH) if len(year) >= 60 else None,
            "near_low": last <= lo * (1 + NEAR_LOW) if len(year) >= 60 else None,
            "weeks": keys, "closes": [round(weekly[k], 4) for k in keys]}


def equal_weight(series: list[dict]) -> tuple[list[int], list[float]]:
    """An equal-weighted line for several companies: each week the average of the weekly changes of the companies that have both
    that week's close and the one before, compounded from 100. Returns the weeks (Friday ordinals) and the line."""
    all_weeks = sorted({w for s in series for w in s["weeks"]})
    by = [dict(zip(s["weeks"], s["closes"])) for s in series]
    weeks, line = [], []
    prev_week = None
    for w in all_weeks:
        if prev_week is None:
            weeks.append(w)
            line.append(100.0)
            prev_week = w
            continue
        moves = [m[w] / m[prev_week] - 1 for m in by if w in m and prev_week in m]
        if len(moves) >= max(2, len(series) // 2):
            weeks.append(w)
            line.append(line[-1] * (1 + sum(moves) / len(moves)))
            prev_week = w
    return weeks, line


def _from_weeks(line: list[float], weeks: list[int], n: int) -> float | None:
    if len(line) <= n or n <= 0:
        return None
    return round((line[-1] / line[-1 - n] - 1) * 100, 1)


def compute(members: list[tuple[str, str]], reduced: dict[str, dict | None], bench: dict | None, bench_name: str, pending: int = 0) -> dict:
    """The price section. `members`: [(symbol, name)]; `reduced`: symbol -> reduce_bars(...) or None; `bench`: the market index's reduced
    candles. Returns the table by company, the theme's medians, breadth, and the weekly theme/index/relative-strength lines."""
    have = {s: r for s, r in reduced.items() if r}
    rows = [{"symbol": s, "name": n, "ret": have[s]["ret"], "date": have[s]["date"], "above200": have[s]["above200"],
             "near_high": have[s]["near_high"], "near_low": have[s]["near_low"]} for s, n in members if s in have]

    def share(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return {"n": len(vals), "count": sum(1 for v in vals if v), "share": round(sum(1 for v in vals if v) / len(vals) * 100) if vals else None}
    medians = {}
    for k, _ in PERIODS:
        xs = [r["ret"][k] for r in rows if r["ret"].get(k) is not None]
        medians[k] = {"median": round(median(xs), 1), "n": len(xs)} if xs else None
    series = [have[s] for s, _ in members if s in have]
    out = {"companies": rows, "median": medians, "above200": share("above200"), "near_high": share("near_high"), "near_low": share("near_low"),
           "pending": pending, "benchmark": bench_name, "line": None, "returns": None, "as_of": max((r["date"] for r in rows), default=None)}
    if len(series) >= 2:
        weeks, line = equal_weight(series)
        if len(line) >= 5:
            b = dict(zip(bench["weeks"], bench["closes"])) if bench else {}
            use = [(w, v) for w, v in zip(weeks, line) if w in b]
            if len(use) >= 5:
                w0 = use[0][0]
                bw = [b[w] / b[w0] * 100 for w, _ in use]
                tl = [v / use[0][1] * 100 for _, v in use]
                rs = [round(t / x * 100, 2) for t, x in zip(tl, bw)]
                out["line"] = {"weeks": [date.fromordinal(w).isoformat() for w, _ in use], "theme": [round(v, 2) for v in tl],
                               "bench": [round(v, 2) for v in bw], "rs": rs}
                out["returns"] = {k: {"theme": _from_weeks(tl, [], n), "bench": _from_weeks(bw, [], n)} for k, n in WEEK_RETURNS.items()}
    return out
