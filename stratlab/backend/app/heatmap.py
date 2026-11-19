"""The stock heatmap: every company of a group as a tile, with its price change over six periods, its market value and its volume.

Nothing here reads a price source. The daily breadth run already reads every stock's daily candles after each market's close; as it
goes it reduces each stock's candles to one short row (`heat_row`: the last close, the change over a day, a week, a month, three months,
the year so far and a year, the last day's volume and its 20-day average) and stores every row of the market in one place
(heatmap:rows:<region>), with each group's index over the same periods. A page asks for a group and gets its rows joined to the
companies' names, sectors and market values from the screens' index, which is kept in memory; the answer is shared by everyone for
two minutes. So the page is one stored read, however many stocks it shows, and nothing runs between the daily runs.

A theme's companies can sit outside every stored group (LIVE6-005: 11 of Cybersecurity's 16, Cloudflare and Zscaler among them, had no
row and were left out). Those are read on demand, the largest first, at most ON_DEMAND a request within ON_DEMAND_SECS, each row kept
for everyone until the next run's day; one still without closes is drawn at its stored last price with no change (grey), so the
largest companies are never silently dropped.

While a market trades, the live breadth round (breadth_live, India) keeps its prices here too (save_live); until the evening run stores
the day's closes, the map and the movers are drawn from them and say of when: the session's latest round, or the day's last trades after
the bell (LIVE13A-012/-029: at 16:05 IST the map still showed the day before's closes beside Mood's day's close).

Facts only: a change is a change, a tile's size is the company's market value. Nothing here ranks or rates a stock."""
import json
import math
import time
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date, timedelta

from fastapi import APIRouter, Depends

from . import db
from .auth import current_profile
from .intel.net import TTLCache
from .responses import err, ok

KEY = "heatmap:rows:"                 # heatmap:rows:<region> = {"day", "at", "stocks": {symbol: row}, "index": {group: [six changes]}}
# LIVE13A-012/-029: the live breadth round's prices, kept for the map and the movers while the day's closes aren't stored yet
LIVE_KEY = "heatmap:live:"            # heatmap:live:<region> = {"day", "time", "close", "at", "q": {symbol: [price, prev close, volume, high, low]}, "idx": {index: [price, prev close]}}
LIVE_FRESH = 40 * 60                  # a session's prices older than this aren't shown as the day's (the breadth card's STALE_AFTER)
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
ON_DEMAND = 24                        # theme companies without a stored row read in one request (the largest first)
ON_DEMAND_SECS = 8.0                  # how long one request waits for those reads; the rest are read on the next ask
ON_DEMAND_DAYS = 400                  # calendar days of candles a row needs (a year back and the year before's last close)
ON_DEMAND_WORKERS = 6
ROW_FOR = 6 * 3600                    # seconds a row read on demand is kept (the stored rows change once a day)
MISS_FOR = 30 * 60                    # seconds a company with no closes (not listed, suspended) is not asked again
_read = TTLCache(max_items=5000, max_bytes=4 * 1024 * 1024)     # (region, day, symbol) -> row, or [] for none
_history = None                       # (region, symbol, days) -> daily candles; set by main (setup), None in a bare import


def setup(history) -> None:
    """The daily-candle reader on-demand rows use (main: the breadth run's own reader, with a short wait for the broker's turn)."""
    global _history
    _history = history


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
            # LIVE9A-010: four places, so a stock down 0.004% is a faller here as in the breadth count (2 places made it "unchanged": the
            # US map said 313 up, 182 down, 4 unchanged beside Mood's 313 / 183 / 3 for the same day)
            out.append(round((last / closes[-2] - 1) * 100, 4))
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
    _read.clear()


# ---------- LIVE13A-012/-029: the day's prices before its closes are stored ----------
def save_live(region: str, day: str, hhmm: str, close: bool, quotes: dict[str, dict], indexes: list[str]) -> int:
    """Keep a live breadth round's prices for the map and the movers: [price, previous close, volume, high, low] of each stock that has
    traded on `day`, and each group index's [price, previous close]. `close`: the round after the bell (the day's last trades). The map
    and the lists draw from these until the evening run stores the day's closes (at 16:05 IST they still showed the day before's).
    Returns how many stocks were kept."""
    from .breadth_live import _traded_before
    q: dict[str, list] = {}
    for s, v in (quotes or {}).items():
        v = v or {}
        px, prev = _num(v.get("price")), _num(v.get("prev_close"))
        if s in indexes or not px or px <= 0 or not prev or prev <= 0 or _traded_before(v.get("at"), day):
            continue
        vol, hi, lo = _num(v.get("volume")), _num(v.get("high")), _num(v.get("low"))
        q[s] = [round(px, 4), round(prev, 4), vol, hi, lo]
    idx = {i: [round(_num((quotes.get(i) or {}).get("price")), 4), round(_num((quotes.get(i) or {}).get("prev_close")), 4)]
           for i in indexes if _num((quotes.get(i) or {}).get("price")) and _num((quotes.get(i) or {}).get("prev_close"))}
    if not q:
        return 0
    db.set_setting(LIVE_KEY + region, json.dumps({"day": day, "time": hhmm, "close": bool(close), "at": int(time.time()), "q": q, "idx": idx},
                                                 separators=(",", ":")))
    _views.clear()
    from . import movers
    movers.clear()
    return len(q)


def live_for(region: str, day: str | None, now: float | None = None) -> dict | None:
    """The kept live prices when they are of a later day than the stored closes `day` and still the day's: the round after the bell
    (until the evening run stores that day), or a session round under LIVE_FRESH old. None otherwise (the page then shows the closes)."""
    try:
        snap = db.json_value(db.get_setting(LIVE_KEY + region), {})
    except Exception:
        return None
    if not isinstance(snap, dict) or not isinstance(snap.get("q"), dict) or not snap["q"] or not snap.get("day"):
        return None
    if day and str(snap["day"]) <= str(day):
        return None
    if not snap.get("close") and (now if now is not None else time.time()) - (_num(snap.get("at")) or 0) > LIVE_FRESH:
        return None
    return snap


def live_row(row: list, q: list) -> list:
    """A stored row brought to a live price: the close becomes the price, the day's change runs from the quote's previous close, every
    longer period's change runs to the price from the same starting close as before (the year so far exactly), and the volume is the
    day's so far against the same 20-session average."""
    px, prev = float(q[0]), float(q[1])
    old = _num(row[0])
    longer = [round(((1 + r / 100) * px / old - 1) * 100, 2) if r is not None and old else None for r in (_num(x) for x in row[2:1 + len(PERIODS)])]
    return [px, round((px / prev - 1) * 100, 4), *longer, q[2], row[-1]]


def live_index(r: list | None, q: list | None) -> list | None:
    """A group index's six changes brought to its live level, as live_row does for a stock."""
    if not q or not r:
        return r
    px, prev = float(q[0]), float(q[1])
    out = [round((px / prev - 1) * 100, 4)]
    # the level the stored changes ran to is not kept, so each longer change is moved by the day's change (from the same close)
    out += [round(((1 + x / 100) * (px / prev) - 1) * 100, 2) if x is not None else None for x in (_num(v) for v in r[1:])]
    return out


def live_rows(region: str, doc: dict) -> tuple[dict[str, list], dict | None, dict]:
    """(stocks, live, index): the stored rows, or with live prices of a later day each stock with a price brought to it (one without a
    trade that day keeps its stored close and longer changes, with no day's change and no volume), `live` saying of when ({day, time, close}) and the indexes'
    brought along."""
    stocks, index = doc.get("stocks") or {}, doc.get("index") or {}
    snap = live_for(region, doc.get("day")) if stocks else None
    if not snap:
        return stocks, None, index
    q = snap["q"]
    out = {s: (live_row(r, q[s]) if s in q else [r[0], None, *r[2:1 + len(PERIODS)], None, r[-1]]) for s, r in stocks.items()}
    from . import breadth
    idx = {}
    for g, r in index.items():
        name = (breadth.GROUPS.get(g) or {}).get("index")
        idx[g] = live_index(r, (snap.get("idx") or {}).get(name))
    return out, {"day": snap["day"], "time": snap.get("time"), "close": bool(snap.get("close")), "quoted": q}, idx


def behind(region: str, day: str | None, now=None) -> bool:
    """True when the market's latest session has closed but its closes aren't stored yet (the page says they are being added)."""
    if not day:
        return False
    try:
        from . import stock_pages
        return stock_pages.last_session(region, now)[0].isoformat() > str(day)
    except Exception:
        return False


def read_missing(region: str, symbols: list[str], through: str | None) -> dict[str, list]:
    """Rows for companies the daily run didn't store, from their daily candles: kept rows at once, then at most ON_DEMAND new reads (in
    the order given: the largest first) within ON_DEMAND_SECS. A read that failed or ran out of time isn't kept, so it is tried again."""
    got: dict[str, list] = {}
    todo: list[str] = []
    for s in symbols:
        hit = _read.get((region, through, s))
        if hit is None:
            todo.append(s)
        elif hit:
            got[s] = hit
    todo = todo[:ON_DEMAND]
    if not todo or _history is None:
        return got

    def one(sym: str) -> list | None:
        try:
            return heat_row(_history(region, sym, ON_DEMAND_DAYS), through) or []
        except LookupError:                      # not listed: nothing to read
            return []
        except Exception:                        # the source busy or down: asked again next time
            return None

    pool = ThreadPoolExecutor(max_workers=min(ON_DEMAND_WORKERS, len(todo)), thread_name_prefix="heatmap")
    try:
        futures = {pool.submit(one, s): s for s in todo}
        done, _ = wait(futures, timeout=ON_DEMAND_SECS)
        for f in done:
            sym, row = futures[f], f.result()
            if row is None:
                continue
            _read.set((region, through, sym), row, ROW_FOR if row else MISS_FOR)
            if row:
                got[sym] = row
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return got


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


def tile(symbol: str, row: list, f: dict | None, sector: str | None, region: str | None = None) -> dict:
    """One company's tile: s symbol, n name, sec sector, ind industry, cap market value (the market's unit), px last close, r the six
    changes, vx the last day's volume as a multiple of its 20-day average, tv the value traded that day (price times volume)."""
    f = f or {}
    close, vol, avg = _num(row[0]), _num(row[-2]), _num(row[-1])
    sec = str(sector or f.get("sector") or "")[:60] or None
    name = str(f.get("name") or symbol)
    if region:
        # LIVE10A-038: one name style in every list ("MICROSOFT CORP", "TYSON FOODS, INC." beside "Apple Inc."), as Results and Mood have it
        from .results import display_name
        name = display_name(region, name) or name
    return {"s": symbol, "n": name[:80], "sec": sec, "ind": str(f.get("industry") or "")[:80] or sec,
            "cap": _num(f.get("market_cap")), "px": close, "r": [_num(x) for x in row[1:1 + len(PERIODS)]],
            "vx": round(vol / avg, 2) if vol is not None and avg else None,
            "tv": round(close * vol) if close and vol else None}


def view(region: str, universe: str | None = None, min_cap: float | None = None, symbols: list[str] | None = None) -> dict:
    """A group's tiles (or, with `symbols`, those companies'), the largest by market value first, at most MAX_TILES of them, with the
    group's index over the same periods. `pending` is true until the daily run has stored the market's rows once. With `symbols`, a
    company without a stored row is read on demand (read_missing), else drawn at its stored last price with no change (`price_only`
    counts those); `members - with_prices - price_only` have neither and are left out."""
    from . import breadth
    group = universe if universe in UNIVERSES[region] else DEFAULT[region]
    doc = load(region)
    stocks, live, index = live_rows(region, doc)
    g = breadth.GROUPS[group]
    out = {"market": region, "universe": None if symbols is not None else group, "universe_name": None if symbols is not None else g["name"],
           "universes": universes(region), "periods": list(PERIODS), "as_of": doc.get("day"), "cap_unit": CAP_UNIT[region],
           "index": {"name": g["index_name"], "r": index.get(group)}, "pending": not stocks,
           "live": {k: v for k, v in live.items() if k != "quoted"} if live else None, "behind": not live and behind(region, doc.get("day")),
           "min_cap": min_cap, "tiles": [], "members": 0, "with_prices": 0, "price_only": 0, "matching": 0, "shown": 0}
    if not stocks:
        return out
    if symbols is not None:
        want = list(dict.fromkeys(s for s in symbols if s))[:MAX_SYMBOLS]
    else:
        # LIVE9A-023: an exchange's placeholder symbol (NSE's DUMMY...) in a group's list is not a company ("1 of the 501 companies has no closes")
        want = [s for s in breadth.members(group) if not str(s).upper().startswith("DUMMY")]
    rows, sectors = _facts(region)
    tiles = [tile(s, stocks[s], rows.get(s), sectors.get(s), region) for s in want if s in stocks]
    if symbols is not None:
        missing = sorted((s for s in want if s not in stocks), key=lambda s: -(_num((rows.get(s) or {}).get("market_cap")) or 0))
        extra = read_missing(region, missing, doc.get("day")) if missing else {}
        if live:                                     # a company read on demand is brought to the same live prices
            extra = {s: (live_row(r, live["quoted"][s]) if s in live["quoted"] else r) for s, r in extra.items()}
        tiles += [tile(s, extra[s], rows.get(s), sectors.get(s), region) for s in missing if s in extra]
        out["with_prices"] = len(tiles)
        blank = [None] * len(PERIODS)
        last = [(s, _num((rows.get(s) or {}).get("price"))) for s in missing if s not in extra]
        tiles += [tile(s, [px, *blank, None, None], rows.get(s), sectors.get(s), region) for s, px in last if px and px > 0]
        out["price_only"] = len(tiles) - out["with_prices"]
    else:
        out["with_prices"] = len(tiles)
    out["members"] = len(want)
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
