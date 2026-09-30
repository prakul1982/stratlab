"""Sector rotation: where each sector (or stock) sits against a benchmark, and where it's heading.

For each member: RS = 100 × price / benchmark. The x-axis (relative strength) is how far RS is above or below its
own recent average, in standard deviations around 100; the y-axis (momentum) is the same measure applied to the
week-on-week change of that ratio. Above 100 on both = Leading, strong but slowing = Weakening, weak on both =
Lagging, weak but picking up = Improving. Members usually rotate clockwise through the four.

StratLab's own calculation, in the spirit of relative rotation charts; not the trademarked RRG indicator."""
import numpy as np
import pandas as pd

from . import universes
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
    "NIFTY HOUSING": "Housing",
}


def _label(market: str, symbol: str, inst: dict | None) -> str:
    if market == "US" and symbol in US_NAMES:
        return US_NAMES[symbol]
    if symbol in IN_NAMES:
        return "Nifty " + IN_NAMES[symbol]
    return (inst or {}).get("name") or symbol


def resolve_sectors(registry, market: str) -> tuple[list[tuple[str, str]], list[str]]:
    """(instrument id, symbol) for each sector index the data source has, and the ones it doesn't."""
    ids, missing = [], []
    if market == "IN":
        kite = registry.provider("IN").kite
        for sym in SECTORS["IN"]["members"]:
            hit = kite.by_symbol(sym)
            (ids.append((hit["id"], sym)) if hit and hit.get("type") == "INDEX" else missing.append(sym))
    else:
        for sym in SECTORS[market]["members"]:
            ids.append((f"{market}:{sym}", sym))
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


def compute(registry, market: str, members: list[tuple[str, str]], interval: str, tail: int, load) -> dict:
    """Rotation paths for members [(id, symbol)] against the market's benchmark. `load(id, days)` gives daily bars."""
    days = 700 if interval == "weekly" else 220
    bid, bsym = benchmark_id(registry, market)
    bench = closes(load(bid, days), interval)
    prov = registry.provider(market)

    def one(item):
        iid, sym = item
        try:
            pts = path(closes(load(iid, days), interval), bench, tail)
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
                     "moved": None if len(pts) < 2 else quadrant(first["x"], first["y"])})
    order = {"leading": 0, "improving": 1, "weakening": 2, "lagging": 3}
    rows.sort(key=lambda r: (order[r["quadrant"]], -r["x"]))
    return {"benchmark": bsym, "interval": interval, "tail": tail, "rows": rows, "skipped": skipped,
            "as_of": max((r["points"][-1]["t"] for r in rows), default=None)}


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
    """Sectors (set "sectors"), or any group of stocks (members), against the market's benchmark."""
    tail = max(1, min(MAX_TAIL, int(tail)))
    if set_id == "sectors":
        items, missing = resolve_sectors(registry, market)
    else:
        ids, missing = universes.resolve(registry, market, (members or [])[:universes.MAX_MEMBERS])
        items = [(i, i.split(":", 1)[1]) for i in ids]
    out = compute(registry, market, items, interval, tail, load_daily(registry))
    if set_id != "sectors":            # stocks: show the trading symbol, not the index-style label
        for r in out["rows"]:
            inst = registry.provider(market).instrument(r["id"].split(":", 1)[1]) if registry.provider(market) else None
            r["name"] = (inst or {}).get("symbol") or r["symbol"]
            r["core"] = True
    out["skipped"] = list(missing) + out["skipped"]
    return out
