"""A theme's price picture from its companies' daily closes (THEME-1): returns over one, three and twelve months and three years, how
many of the companies are above their 200-day average or near a 52-week extreme, and an equal-weighted line for the theme set
against the market's own index (its relative strength over time).

Each company's candles are reduced at once to a few numbers and 160 weekly closes (`reduce_bars`), so a theme never keeps a company's
whole history; the reduced figures are what the caller keeps for the rest of the session. Facts and arithmetic only."""
from datetime import date, datetime, timedelta
from statistics import median

# LIVE6-002: every period is a calendar one, counted back from the last close: one month is the close on or before the same day a month back
# (the live SPY "1 month" was worked out over two weeks of a weekly line with gaps, and "3 months" over four)
PERIODS = (("1M", 1), ("3M", 3), ("1Y", 12), ("3Y", 36))
WEEKS = 160                                   # weekly closes kept for a company: three years and a bit
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


def months_back(d: date, months: int) -> date:
    """The same day `months` calendar months before `d` (the month's last day when it is shorter: 31 May -> 30 Apr)."""
    import calendar
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def change(pairs: list[tuple[date, float]], months: int) -> float | None:
    """The price change in percent from the last close on or before the same day `months` calendar months before the last close, to the
    last close; None when the closes don't reach back that far. `pairs`: (date, close), oldest first (a weekly line's dated points too)."""
    if len(pairs) < 2:
        return None
    last_d, last_c = pairs[-1]
    target = months_back(last_d, months)
    if pairs[0][0] > target:
        return None
    base = None
    for d, c in pairs:
        if d <= target:
            base = c
        else:
            break
    return round((last_c / base - 1) * 100, 1) if base else None


def week_of(d: date) -> int:
    """The week a close is in, as the ordinal of that week's Friday (a weekend close joins the Friday before)."""
    return (d + timedelta(days=(4 - d.weekday()) % 7 if d.weekday() <= 4 else -(d.weekday() - 4))).toordinal()


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
        weekly[week_of(d)] = c
    keys = sorted(weekly)[-WEEKS:]
    return {"last": last, "date": last_d.isoformat(), "ret": {k: change(pairs, n) for k, n in PERIODS},
            "above200": (last > sum(closes[-200:]) / 200) if len(closes) >= 200 else None,
            "above50": (last > sum(closes[-50:]) / 50) if len(closes) >= 50 else None,
            "near_high": last >= hi * (1 - NEAR_HIGH) if len(year) >= 60 else None,
            "near_low": last <= lo * (1 + NEAR_LOW) if len(year) >= 60 else None,
            "weeks": keys, "closes": [sig(weekly[k]) for k in keys]}


def sig(c: float) -> float:
    """A close kept to six significant figures (LIVE7A-002: rounded to four decimals, a share under $0.00005 became 0 and the theme's line
    divided by it, a 500 from the price route; and a penny share's 0.0012 -> 0.0013 read as an 8% week)."""
    return float(f"{c:.6g}")


def from_daily_row(row: list | None, day: str | None) -> dict | None:
    """A company's price figures from its stored daily row (the heatmap's: [last close, 1d, 1w, 1m, 3m, ytd, 1y, volume, average volume],
    each change from the last close on or before 30, 91 and 365 calendar days back), for a company whose own candles aren't read yet
    (LIVE7A-002: 78 of 98 companies "not read yet" for a minute and more, the largest among them). No weekly line, no 3-year change and no
    200-day average: those wait for its candles."""
    if not isinstance(row, list) or len(row) < 7 or not day:
        return None
    last = row[0]
    if not isinstance(last, (int, float)) or last <= 0:
        return None
    one = lambda v: round(float(v), 1) if isinstance(v, (int, float)) and not isinstance(v, bool) else None      # noqa: E731
    return {"last": float(last), "date": str(day)[:10], "ret": {"1M": one(row[3]), "3M": one(row[4]), "1Y": one(row[6]), "3Y": None},
            "above200": None, "above50": None, "near_high": None, "near_low": None, "weeks": [], "closes": [], "daily": True}


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
        moves = [m[w] / m[prev_week] - 1 for m in by if w in m and prev_week in m and m[prev_week] > 0]
        if len(moves) >= max(2, len(series) // 2):
            weeks.append(w)
            line.append(line[-1] * (1 + sum(moves) / len(moves)))
            prev_week = w
    return weeks, line


def week_label(week: int, end: date) -> str:
    """A week's date as a chart says it: its Friday, or the last close when the week isn't over (LIVE6-002: the live line ended on
    "13 Nov", a Friday after its last close)."""
    return min(date.fromordinal(week), end).isoformat()


LINE_COVER = 0.8                              # the weekly line is drawn once this share of the priced companies have their own candles read


def compute(members: list[tuple[str, str]], reduced: dict[str, dict | None], bench: dict | None, bench_name: str, pending: int = 0) -> dict:
    """The price section. `members`: [(symbol, name)]; `reduced`: symbol -> reduce_bars(...) (or from_daily_row(...)) or None; `bench`: the
    market index's reduced candles (or its changes only, {"ret", "date"}). Returns the table by company, the theme's medians and averages,
    breadth, and the weekly theme/index/relative-strength lines.
    LIVE7A-002: the theme's and its index's change over each period are worked out from the companies' own changes (the average company:
    equal amounts in each at the period's start) and the index's daily closes, so they never wait on a weekly line (the live India pages
    printed "–" in both columns on every row); the line itself is drawn only once LINE_COVER of the priced companies have their candles."""
    have = {s: r for s, r in reduced.items() if r}
    rows = [{"symbol": s, "name": n, "ret": have[s]["ret"], "date": have[s]["date"], "above200": have[s]["above200"],
             "near_high": have[s]["near_high"], "near_low": have[s]["near_low"]} for s, n in members if s in have]

    def share(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return {"n": len(vals), "count": sum(1 for v in vals if v), "share": round(sum(1 for v in vals if v) / len(vals) * 100) if vals else None}
    medians, means = {}, {}
    for k, _ in PERIODS:
        xs = [r["ret"][k] for r in rows if r["ret"].get(k) is not None]
        medians[k] = {"median": round(median(xs), 1), "n": len(xs)} if xs else None
        means[k] = round(sum(xs) / len(xs), 1) if xs else None
    series = [have[s] for s, _ in members if s in have and have[s].get("weeks")]
    as_of = max((r["date"] for r in rows), default=None)
    bret = (bench or {}).get("ret") or {}
    returns = {k: {"theme": means[k], "bench": bret.get(k)} for k, _ in PERIODS} if rows else None
    out = {"companies": rows, "median": medians, "above200": share("above200"), "near_high": share("near_high"), "near_low": share("near_low"),
           "pending": pending, "missing": sum(1 for s, _ in members if s not in have), "benchmark": bench_name, "line": None, "returns": returns,
           "returns_to": max(as_of or "", str((bench or {}).get("date") or "")[:10]) or None if rows else None, "as_of": as_of}
    if len(series) >= 2 and len(series) >= LINE_COVER * len(rows) and (bench or {}).get("weeks"):
        weeks, line = equal_weight(series)
        if len(line) >= 5:
            b = dict(zip(bench["weeks"], bench["closes"])) if bench else {}
            use = [(w, v) for w, v in zip(weeks, line) if w in b]
            if len(use) >= 5:
                w0 = use[0][0]
                bw = [b[w] / b[w0] * 100 for w, _ in use]
                tl = [v / use[0][1] * 100 for _, v in use]
                rs = [round(t / x * 100, 2) for t, x in zip(tl, bw)]
                end = max(_day(out["as_of"]) or date.min, _day((bench or {}).get("date")) or date.min)
                days = [week_label(w, end) for w, _ in use]
                out["line"] = {"weeks": days, "theme": [round(v, 2) for v in tl], "bench": [round(v, 2) for v in bw], "rs": rs}
    return out
