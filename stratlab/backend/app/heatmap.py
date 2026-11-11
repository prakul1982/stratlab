"""The stock heatmap: every company of a group as a tile, with its price change over six periods, its market value and its volume.

Nothing here reads a price source. The daily breadth run already reads every stock's daily candles after each market's close; as it
goes it reduces each stock's candles to one short row (`heat_row`: the last close, the change over a day, a week, a month, three months,
the year so far and a year, the last day's volume and its 20-day average) and stores every row of the market in one place
(heatmap:rows:<region>), with each group's index over the same periods. A page asks for a group and gets its rows joined to the
companies' names, sectors and market values from the screens' index, which is kept in memory; the answer is shared by everyone for
two minutes. So the page is one stored read, however many stocks it shows, and nothing runs between the daily runs.

Facts only: a change is a change, a tile's size is the company's market value. Nothing here ranks or rates a stock."""
import json
import math
import time
from bisect import bisect_right
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from . import db
from .auth import current_profile
from .intel.net import TTLCache
from .responses import err, ok

KEY = "heatmap:rows:"                 # heatmap:rows:<region> = {"day", "at", "stocks": {symbol: row}, "index": {group: [six changes]}}
PERIODS = ("1d", "1w", "1m", "3m", "ytd", "1y")
PERIOD_DAYS = {"1w": 7, "1m": 30, "3m": 91, "1y": 365}      # calendar days back; a day and the year so far are worked out on their own
AVG_VOL = 20                          # sessions in the average the last day's volume is set against
STALE_DAYS = 7                        # a stock whose last candle is this much older than the run's day is suspended: left out
MAX_TILES = 600                       # tiles one answer carries: the largest by market value when a group has more
MAX_SYMBOLS = 300                     # companies a list of symbols (a theme) can ask for
UNIVERSES = {"IN": ("nifty50", "nifty500", "midcap150", "smallcap250", "nse_all"), "US": ("sp500", "us_large")}
DEFAULT = {"IN": "nifty500", "US": "sp500"}
CAP_UNIT = {"IN": "₹ crore", "US": "$ million"}

_views = TTLCache(max_items=60, max_bytes=16 * 1024 * 1024)
VIEW_FOR = 120                        # seconds one group's answer is shared by everyone (the rows change once a day)


def _num(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _series(bars: list[dict], through: str | None) -> tuple[list[str], list[float], list[float]]:
    """Daily candles as three lists, oldest first: the days, their closes and their volumes, one entry a day, up to `through`."""
    by: dict[str, tuple[float, float]] = {}
    for b in bars or []:
        try:
            d, c = str(b["t"])[:10], float(b["c"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(c) or c <= 0 or (through and d > through):
            continue
        v = _num(b.get("v"))
        by[d] = (c, v if v and v > 0 else 0.0)
    days = sorted(by)
    return days, [by[d][0] for d in days], [by[d][1] for d in days]


def changes(days: list[str], closes: list[float]) -> list[float | None]:
    """The change in percent to the last close over each of PERIODS: from the close before it (1d), from the last close on or before
    the day 7, 30, 91 or 365 calendar days earlier, and from the last close of the year before (ytd). None where the closes don't
    reach back that far."""
    if len(days) < 2:
        return [None] * len(PERIODS)
    last_day, last = date.fromisoformat(days[-1]), closes[-1]

    def since(target: str) -> float | None:
        i = bisect_right(days, target) - 1
        return round((last / closes[i] - 1) * 100, 2) if i >= 0 and closes[i] > 0 else None

    out: list[float | None] = []
    for p in PERIODS:
        if p == "1d":
            out.append(round((last / closes[-2] - 1) * 100, 2))
        elif p == "ytd":
            out.append(since(f"{last_day.year - 1}-12-31"))
        else:
            out.append(since((last_day - timedelta(days=PERIOD_DAYS[p])).isoformat()))
    return out


def heat_row(bars: list[dict], through: str | None = None) -> list | None:
    """One stock's candles as [last close, the six changes of PERIODS, the last day's volume, the average volume of the 20 sessions
    before it]. None without two closes, or when the last candle is more than STALE_DAYS older than `through` (a suspended stock)."""
    days, closes, vols = _series(bars, through)
    if len(days) < 2:
        return None
    if through and (date.fromisoformat(through) - date.fromisoformat(days[-1])).days > STALE_DAYS:
        return None
    before = [v for v in vols[-1 - AVG_VOL:-1]]
    avg = round(sum(before) / len(before), 1) if len(before) == AVG_VOL and sum(before) > 0 else None
    return [round(closes[-1], 4), *changes(days, closes), round(vols[-1], 1), avg]


def index_row(closes_by_day: dict[str, float] | None) -> list[float | None] | None:
    """An index's six changes from {day: close}; None without two days."""
    pairs = sorted((d, c) for d, c in (closes_by_day or {}).items() if _num(c) and c > 0)
    if len(pairs) < 2:
        return None
    return changes([d for d, _ in pairs], [float(c) for _, c in pairs])


# ---------- the stored rows ----------
def save(region: str, day: str, stocks: dict[str, list], index: dict[str, list] | None = None) -> None:
    doc = {"day": day, "at": int(time.time()), "stocks": stocks, "index": {g: r for g, r in (index or {}).items() if r}}
    db.set_setting(KEY + region, json.dumps(doc, separators=(",", ":")))
    _views.clear()


def load(region: str) -> dict:
    """The market's stored rows. {"day": None, "stocks": {}} before the first daily run has stored them."""
    try:
        raw = db.json_value(db.get_setting(KEY + region), {})
    except Exception:                    # storage down: nothing to show, asked again next time
        raw = {}
    stocks = raw.get("stocks") if isinstance(raw.get("stocks"), dict) else {}
    return {"day": raw.get("day"), "stocks": {s: r for s, r in stocks.items() if isinstance(r, list) and len(r) == len(PERIODS) + 3},
            "index": raw.get("index") if isinstance(raw.get("index"), dict) else {}}


def clear() -> None:
    _views.clear()


# ---------- what the page shows ----------
def universes(region: str) -> list[dict]:
    from . import breadth
    return [{"id": g, "name": breadth.GROUPS[g]["name"]} for g in UNIVERSES[region]]


def _facts(region: str) -> tuple[dict[str, dict], dict[str, str]]:
    """({symbol: the screens' row}, {symbol: sector}) for a market; either is empty when its store can't be read."""
    from . import breadth, screens
    try:
        rows = {r["symbol"]: r for r in screens.load_index(region).get("rows") or []}
    except Exception:
        rows = {}
    try:
        sectors = breadth.sector_map(region)
    except Exception:
        sectors = {}
    return rows, sectors


def tile(symbol: str, row: list, f: dict | None, sector: str | None) -> dict:
    """One company's tile: s symbol, n name, sec sector, ind industry, cap market value (the market's unit), px last close, r the six
    changes, vx the last day's volume as a multiple of its 20-day average, tv the value traded that day (price times volume)."""
    f = f or {}
    close, vol, avg = _num(row[0]), _num(row[-2]), _num(row[-1])
    sec = str(sector or f.get("sector") or "")[:60] or None
    return {"s": symbol, "n": str(f.get("name") or symbol)[:80], "sec": sec, "ind": str(f.get("industry") or "")[:80] or sec,
            "cap": _num(f.get("market_cap")), "px": close, "r": [_num(x) for x in row[1:1 + len(PERIODS)]],
            "vx": round(vol / avg, 2) if vol is not None and avg else None,
            "tv": round(close * vol) if close and vol else None}


def view(region: str, universe: str | None = None, min_cap: float | None = None, symbols: list[str] | None = None) -> dict:
    """A group's tiles (or, with `symbols`, those companies'), the largest by market value first, at most MAX_TILES of them, with the
    group's index over the same periods. `pending` is true until the daily run has stored the market's rows once."""
    from . import breadth
    group = universe if universe in UNIVERSES[region] else DEFAULT[region]
    doc = load(region)
    stocks = doc.get("stocks") or {}
    g = breadth.GROUPS[group]
    out = {"market": region, "universe": None if symbols is not None else group, "universe_name": None if symbols is not None else g["name"],
           "universes": universes(region), "periods": list(PERIODS), "as_of": doc.get("day"), "cap_unit": CAP_UNIT[region],
           "index": {"name": g["index_name"], "r": (doc.get("index") or {}).get(group)}, "pending": not stocks,
           "min_cap": min_cap, "tiles": [], "members": 0, "with_prices": 0, "matching": 0, "shown": 0}
    if not stocks:
        return out
    if symbols is not None:
        want = list(dict.fromkeys(s for s in symbols if s))[:MAX_SYMBOLS]
    else:
        want = breadth.members(group)
    rows, sectors = _facts(region)
    tiles = [tile(s, stocks[s], rows.get(s), sectors.get(s)) for s in want if s in stocks]
    out["members"], out["with_prices"] = len(want), len(tiles)
    if min_cap:
        tiles = [t for t in tiles if t["cap"] is not None and t["cap"] >= min_cap]
    tiles.sort(key=lambda t: (-(t["cap"] or 0), t["s"]))
    out["matching"] = len(tiles)
    out["tiles"] = tiles[:MAX_TILES]
    out["shown"] = len(out["tiles"])
    return out


# ---------- the route ----------
router = APIRouter(tags=["heatmap"])
MAX_CAP = 1e9                         # a smallest market value beyond this is a typo


@router.get("/invest/heatmap")
def heatmap(market: str = "IN", universe: str | None = None, min_cap: float | None = None, symbols: str | None = None,
            profile=Depends(current_profile)):
    """The heatmap's tiles for a group of a market (India or the US), or for a list of symbols (a theme's companies). Every plan."""
    region = (market or "").upper()
    if region not in UNIVERSES:
        err(400, "bad_market", "Pick India or the US.")
    if universe is not None and universe not in UNIVERSES[region]:
        err(404, "not_found", "Pick a group of stocks from the list.")
    if min_cap is not None and not (math.isfinite(min_cap) and 0 <= min_cap <= MAX_CAP):
        err(400, "bad_min_cap", "The smallest market value isn't a number the page offers.")
    if symbols is not None:
        want = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if not want or len(want) > MAX_SYMBOLS or any(len(s) > 20 for s in want):
            err(400, "bad_symbols", f"Give 1 to {MAX_SYMBOLS} symbols.")
        return ok(view(region, None, min_cap or None, want))
    key = (region, universe or DEFAULT[region], min_cap or None)
    hit = _views.get(key)
    if hit is None:
        hit = view(region, universe, min_cap or None)
        _views.set(key, hit, VIEW_FOR)
    return ok(hit)
