"""Sector rotation: where each sector (or stock) sits against a benchmark, and where it's heading.

For each member: RS = 100 × price / benchmark. The x-axis (relative strength) is how far RS is above or below its
own recent average, in standard deviations around 100; the y-axis (momentum) is the same measure applied to the
week-on-week change of that ratio. Above 100 on both = Leading, strong but slowing = Weakening, weak on both =
Lagging, weak but picking up = Improving. Members usually rotate clockwise through the four.

StratLab's own calculation, in the spirit of relative rotation charts; not the trademarked RRG indicator."""
import numpy as np
import pandas as pd

from . import sector_members, universes
from .intel.net import TTLCache
from .scan import _pool

WINDOW = 14          # candles in the normalising window, both axes
SMOOTH = 3           # EMA of the RS line before normalising, to cut day-to-day jitter
MAX_TAIL = 12

SECTORS = {
    "IN": {"benchmark": "NIFTY 500", "name": "NSE sector indices", "members": [
        "NIFTY BANK", "NIFTY IT", "NIFTY AUTO", "NIFTY FMCG", "NIFTY PHARMA", "NIFTY METAL", "NIFTY REALTY",
        "NIFTY ENERGY", "NIFTY INFRA", "NIFTY MEDIA", "NIFTY PSU BANK", "NIFTY PVT BANK", "NIFTY FIN SERVICE",
        "NIFTY CONSUMPTION", "NIFTY COMMODITIES", "NIFTY CPSE", "NIFTY PSE", "NIFTY MNC", "NIFTY SERV SECTOR",
        "NIFTY HEALTHCARE", "NIFTY CONSR DURBL", "NIFTY OIL AND GAS", "NIFTY MIDCAP 150", "NIFTY SMLCAP 250",
        "NIFTY IND DIGITAL", "NIFTY IND DEFENCE", "NIFTY INDIA MFG", "NIFTY CHEMICALS", "NIFTY EV", "NIFTY IND TOURISM",
        "NIFTY CAPITAL MKT", "NIFTY HOUSING"]},
    "US": {"benchmark": "SPY", "name": "S&P 500 sectors", "members": [
        "XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]},
}
# more index sets to compare against the same benchmark (the chart's set picker lists them after "sectors")
INDEX_SETS = {
    "IN": {"size": {"name": "NSE size and style indices", "members": [
        "NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 100", "NIFTY MIDCAP 150", "NIFTY SMLCAP 100", "NIFTY SMLCAP 250",
        "NIFTY MICROCAP250", "NIFTY200 MOMENTM30", "NIFTY100 QUALTY30", "NIFTY100 LOWVOL30", "NIFTY ALPHA 50",
        "NIFTY DIV OPPS 50", "NIFTY GROWSECT 15", "NIFTY MID LIQ 15"]}},
    "US": {"industries": {"name": "US industries", "members": [
        "SMH", "IGV", "XBI", "KRE", "KBE", "ITA", "XOP", "GDX", "ITB", "XHB", "XRT", "JETS", "TAN", "IYT", "CIBR", "PAVE"]}},
}
US_NAMES = {"XLK": "Technology", "XLF": "Financials", "XLV": "Health care", "XLE": "Energy", "XLI": "Industrials",
            "XLY": "Consumer discretionary", "XLP": "Consumer staples", "XLU": "Utilities", "XLB": "Materials",
            "XLRE": "Real estate", "XLC": "Communication"}
BENCHMARK_FALLBACK = {"IN": ["NIFTY 500", "NIFTY 50"], "US": ["SPY"]}
# the sectors shown before the user picks: the broad, non-overlapping ones (the rest stay one click away)
CORE_IN = {"NIFTY BANK", "NIFTY IT", "NIFTY AUTO", "NIFTY FMCG", "NIFTY PHARMA", "NIFTY METAL", "NIFTY REALTY",
           "NIFTY ENERGY", "NIFTY MEDIA", "NIFTY PSU BANK", "NIFTY FIN SERVICE", "NIFTY INFRA"}

_cache = TTLCache(max_items=200)


def quadrant(x: float, y: float) -> str:
    if x >= 100:
        return "leading" if y >= 100 else "weakening"
    return "improving" if y >= 100 else "lagging"


def _z(s: pd.Series, n: int) -> pd.Series:
    sd = s.rolling(n).std()
    return 100 + (s - s.rolling(n).mean()) / sd.where(sd > 0)


def closes(bars: list[dict], interval: str) -> pd.Series:
    """Closing prices by date; weekly takes each week's last close, dated by that day (the current week so far counts)."""
    s = pd.Series([float(b["c"]) for b in bars], index=pd.to_datetime([str(b["t"])[:10] for b in bars]))
    s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    return s.groupby(s.index.to_period("W-FRI")).tail(1) if interval == "weekly" else s


def path(member: pd.Series, bench: pd.Series, tail: int) -> list[dict]:
    """The last `tail` points of (relative strength, momentum), oldest first."""
    df = pd.concat([member, bench], axis=1, join="inner").dropna()
    if len(df) < 2 * WINDOW + SMOOTH + 2:
        return []
    rs = (100 * df.iloc[:, 0] / df.iloc[:, 1]).ewm(span=SMOOTH, adjust=False).mean()
    ratio = _z(rs, WINDOW)
    mom = _z(100 * ratio / ratio.shift(1), WINDOW)
    pts = pd.concat([ratio, mom], axis=1).dropna().tail(tail)
    return [{"t": t.date().isoformat(), "x": round(float(x), 3), "y": round(float(y), 3)} for t, (x, y) in pts.iterrows()]


def heading(pts: list[dict]) -> float | None:
    """Direction of the last step, in degrees (0 = right, 90 = up)."""
    if len(pts) < 2:
        return None
    dx, dy = pts[-1]["x"] - pts[-2]["x"], pts[-1]["y"] - pts[-2]["y"]
    return None if dx == 0 and dy == 0 else round(float(np.degrees(np.arctan2(dy, dx))), 1)


IN_NAMES = {
    "NIFTY BANK": "Bank", "NIFTY IT": "IT", "NIFTY AUTO": "Auto", "NIFTY FMCG": "FMCG", "NIFTY PHARMA": "Pharma",
    "NIFTY METAL": "Metal", "NIFTY REALTY": "Realty", "NIFTY ENERGY": "Energy", "NIFTY INFRA": "Infrastructure",
    "NIFTY MEDIA": "Media", "NIFTY PSU BANK": "PSU Bank", "NIFTY PVT BANK": "Private Bank", "NIFTY FIN SERVICE": "Financial Services",
    "NIFTY CONSUMPTION": "Consumption", "NIFTY COMMODITIES": "Commodities", "NIFTY CPSE": "CPSE", "NIFTY PSE": "PSE",
    "NIFTY MNC": "MNC", "NIFTY SERV SECTOR": "Services", "NIFTY HEALTHCARE": "Healthcare", "NIFTY CONSR DURBL": "Consumer Durables",
    "NIFTY OIL AND GAS": "Oil & Gas", "NIFTY MIDCAP 150": "Midcap 150", "NIFTY SMLCAP 250": "Smallcap 250",
    "NIFTY IND DIGITAL": "Digital", "NIFTY IND DEFENCE": "Defence", "NIFTY INDIA MFG": "Manufacturing",
    "NIFTY CHEMICALS": "Chemicals", "NIFTY EV": "EV", "NIFTY IND TOURISM": "Tourism", "NIFTY CAPITAL MKT": "Capital Markets",
    "NIFTY HOUSING": "Housing", "NIFTY 50": "50", "NIFTY NEXT 50": "Next 50", "NIFTY MIDCAP 100": "Midcap 100",
    "NIFTY SMLCAP 100": "Smallcap 100", "NIFTY MICROCAP250": "Microcap 250", "NIFTY200 MOMENTM30": "200 Momentum 30",
    "NIFTY100 QUALTY30": "100 Quality 30", "NIFTY100 LOWVOL30": "100 Low Volatility 30", "NIFTY ALPHA 50": "Alpha 50",
    "NIFTY DIV OPPS 50": "Dividend Opportunities 50", "NIFTY GROWSECT 15": "Growth Sectors 15", "NIFTY MID LIQ 15": "Midcap Liquid 15",
}


def _label(market: str, symbol: str, inst: dict | None) -> str:
    if market == "US" and symbol in US_NAMES:
        return US_NAMES[symbol]
    if market == "US" and symbol in sector_members.US_NAMES:
        return sector_members.US_NAMES[symbol]
    if symbol in IN_NAMES:
        return "Nifty " + IN_NAMES[symbol]
    return (inst or {}).get("name") or symbol


def index_sets(market: str) -> dict:
    """Every list of indices (or sector funds) the chart can compare, by set id."""
    return {"sectors": SECTORS[market], **INDEX_SETS.get(market, {})}


def resolve_index(registry, market: str, sym: str) -> str | None:
    if market == "IN":
        hit = registry.provider("IN").kite.by_symbol(sym)
        return hit["id"] if hit and hit.get("type") == "INDEX" else None
    return f"{market}:{sym}"


def resolve_sectors(registry, market: str, set_id: str = "sectors") -> tuple[list[tuple[str, str]], list[str]]:
    """(instrument id, symbol) for each index in a set the data source has, and the ones it doesn't."""
    ids, missing = [], []
    for sym in index_sets(market)[set_id]["members"]:
        iid = resolve_index(registry, market, sym)
        (ids.append((iid, sym)) if iid else missing.append(sym))
    return ids, missing


def benchmark_id(registry, market: str) -> tuple[str, str]:
    for sym in BENCHMARK_FALLBACK[market]:
        if market == "IN":
            hit = registry.provider("IN").kite.by_symbol(sym)
            if hit:
                return hit["id"], sym
        else:
            return f"{market}:{sym}", sym
    raise LookupError("No benchmark available for this market.")


def completed_sessions(market: str, load, now=None):
    """`load` without the candle of a session still trading: a chart that says "closes up to 9 Oct" must not carry the
    9 Oct candle while that session is open (R10O-010: the US page said so at 14:55 UTC, with the day's close not yet in)."""
    from .intel.company import market_open, market_today

    def wrapped(iid: str, days: int) -> list[dict]:
        bars = load(iid, days)
        if market_open(market, now):
            today = market_today(market, now)
            return [b for b in bars if str(b["t"])[:10] < today]
        return bars
    return wrapped


def compute(registry, market: str, members: list[tuple[str, str]], interval: str, tail: int, load,
            bench: tuple[str, str] | None = None) -> dict:
    """Rotation paths for members [(id, symbol)] against the market's benchmark (or `bench`, (id, symbol)).
    `load(id, days)` gives daily bars; a session still trading is left out, so the last candle is a finished one."""
    days = 700 if interval == "weekly" else 220
    load = completed_sessions(market, load)
    bid, bsym = bench or benchmark_id(registry, market)
    try:
        bench_s = closes(load(bid, days), interval)
    except LookupError:
        raise
    except Exception as e:      # without the benchmark there's no chart: say so instead of failing
        raise LookupError(f"The benchmark's prices couldn't be loaded right now ({str(e)[:80] or e.__class__.__name__}). "
                          "Try again in a minute.") from None
    prov = registry.provider(market)

    def one(item):
        iid, sym = item
        try:
            pts = path(closes(load(iid, days), interval), bench_s, tail)
            return item, pts, None
        except Exception as e:     # one member's data problem mustn't sink the chart
            return item, [], str(e)[:80] or e.__class__.__name__

    rows, skipped = [], []
    for (iid, sym), pts, problem in _pool.map(one, members):
        if not pts:
            skipped.append(sym if not problem else f"{sym}: {problem}")
            continue
        try:
            inst = prov.instrument(iid.split(":", 1)[1]) if prov else None
        except Exception:
            inst = None
        x, y = pts[-1]["x"], pts[-1]["y"]
        first = pts[0]
        rows.append({"id": iid, "symbol": sym, "name": _label(market, sym, inst), "points": pts, "x": x, "y": y,
                     "quadrant": quadrant(x, y), "heading": heading(pts), "core": market != "IN" or sym in CORE_IN,
                     "stocks": len(sector_members.members(market, sym)),
                     "moved": None if len(pts) < 2 else quadrant(first["x"], first["y"])})
    order = {"leading": 0, "improving": 1, "weakening": 2, "lagging": 3}
    rows.sort(key=lambda r: (order[r["quadrant"]], -r["x"]))
    return {"benchmark": _label(market, bsym, None) if bench else bsym, "interval": interval, "tail": tail, "rows": rows, "skipped": skipped,
            "as_of": max((r["points"][-1]["t"] for r in rows), default=None)}


PAGE_INTERVAL = "weekly"              # the rotation page's chart, which the briefs describe


def shifts(registry, market: str, day: str | None, weekly: bool, load=None) -> list[dict]:
    """The core sectors whose quadrant on the rotation page's chart (weekly candles, the page's own computation)
    changed: since the session before `day` (a daily brief) or since the week before (a weekly brief). Each is
    {"sector", "symbol", "from", "to"}. Prices after `day` are left out, so a brief says what its day showed. (An 8 Oct
    brief said "Nifty IT moving from weakening to leading" from daily candles while the page, on weekly ones, showed
    Weakening.)"""
    load = load or load_daily(registry)
    items, _ = resolve_sectors(registry, market, "sectors")
    bid, _bsym = benchmark_id(registry, market)
    cut = (lambda bars: [b for b in bars if not day or str(b["t"])[:10] <= day])
    bench = cut(load(bid, 700))
    if len(bench) < 2:
        return []
    last = str(bench[-1]["t"])[:10]
    before = [b for b in bench if str(b["t"])[:10] < last]
    b_now, b_prev = closes(bench, PAGE_INTERVAL), closes(before, PAGE_INTERVAL)
    out = []
    for iid, sym in items:
        if market == "IN" and sym not in CORE_IN:
            continue
        try:
            bars = cut(load(iid, 700))
            if weekly:                  # the week before: the chart's previous weekly point
                pts = path(closes(bars, PAGE_INTERVAL), b_now, 2)
                was, now = (pts[0], pts[-1]) if len(pts) == 2 else (None, None)
            else:                       # the session before: the same chart drawn with the prices up to that session
                now = (path(closes(bars, PAGE_INTERVAL), b_now, 1) or [None])[-1]
                was = (path(closes([b for b in bars if str(b["t"])[:10] < last], PAGE_INTERVAL), b_prev, 1) or [None])[-1]
        except Exception:               # one sector's prices missing leaves it out
            continue
        if not now or not was:
            continue
        q_was, q_now = quadrant(was["x"], was["y"]), quadrant(now["x"], now["y"])
        if q_was != q_now:
            out.append({"sector": _label(market, sym, None), "symbol": sym, "from": q_was, "to": q_now})
    return out


def load_daily(registry):
    def load(iid: str, days: int) -> list[dict]:
        key = (iid, days)
        hit = _cache.get(key)
        if hit is not None:
            return hit
        prov, inst = registry.resolve(iid)
        if not prov or not inst:
            raise LookupError("not found")
        bars = prov.history(inst, "1d", days)
        _cache.set(key, bars, 1800)
        return bars
    return load


def run(registry, market: str, set_id: str, members: list[dict] | None, interval: str, tail: int) -> dict:
    """A set of indices (set ids from `index_sets`), one sector's stocks against that sector ("sector:<index>"),
    or any group of stocks (members), against the market's benchmark."""
    tail = max(1, min(MAX_TAIL, int(tail)))
    sets, bench, parent = index_sets(market), None, None
    if set_id in sets:
        items, missing = resolve_sectors(registry, market, set_id)
        missing = []                    # an index this data source doesn't carry isn't worth reporting
    else:
        if set_id.startswith("sector:"):
            sym = set_id.split(":", 1)[1]
            members = [{"symbol": x} for x in sector_members.members(market, sym)]
            iid = resolve_index(registry, market, sym)
            if not members or not iid:
                raise LookupError("That sector's stocks aren't available.")
            bench, parent = (iid, sym), {"symbol": sym, "name": _label(market, sym, None)}
        ids, missing = universes.resolve(registry, market, (members or [])[:universes.MAX_MEMBERS])
        items = [(i, i.split(":", 1)[1]) for i in ids]
    out = compute(registry, market, items, interval, tail, load_daily(registry), bench)
    if set_id not in sets:              # stocks: show the trading symbol, not the index-style label
        for r in out["rows"]:
            inst = registry.provider(market).instrument(r["id"].split(":", 1)[1]) if registry.provider(market) else None
            r["name"] = (inst or {}).get("symbol") or r["symbol"]
            r["core"], r["stocks"] = True, 0
    out["skipped"] = list(missing) + out["skipped"]
    out["parent"] = parent
    return out
