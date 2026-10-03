"""The facts each newsletter reports, built from what the research pages already compute: index moves, sector
rotation, the Stage 2 and ST S2 scans, exchange filings and headlines.

Facts only, never a view. Every source is optional: one that fails or is offline just drops its section. Data a
stock needs is fetched once per day and shared, so a hundred readers holding the same stock cost one lookup."""
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .. import daily_report, db, holdings, rotation, scan, universes
from ..data.calendar import is_trading_day
from ..intel.company import INDICES
from ..intel.net import TTLCache

REGIONS = ("IN", "US")
MAX_STOCKS = 25
HEADLINES = 6
MOVE = {False: 3.0, True: 5.0}       # a price move this big (%, daily or weekly) counts as news on its own
EQUITY = {None, "", "EQ", "ETF"}
CLOSE = {"IN": ("Asia/Kolkata", time(15, 30)), "US": ("America/New_York", time(16, 0))}
_cache = TTLCache(max_items=5000)


def _main():
    """The running app's data sources (imported late: main imports this package)."""
    from .. import main
    return main


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def closed(region: str, day: date) -> bool:
    """Whether `day`'s session is over in that market. Part of every cache key, so facts gathered during the day (an
    admin preview) are never reused for the issue after the close."""
    tz, at = CLOSE[region]
    local = datetime.now(ZoneInfo(tz))
    return local.date() > day or (local.date() == day and local.time() >= at)


def previous_trading_day(region: str, day: date) -> date:
    d = day - timedelta(days=1)
    for _ in range(10):
        if is_trading_day(region, d):
            return d
        d -= timedelta(days=1)
    return d


def reference_day(region: str, day: date, weekly: bool) -> date:
    """What a change is measured from: the previous trading day, or a week back for the weekly issue."""
    return day - timedelta(days=7) if weekly else previous_trading_day(region, day)


def _pct(now: float | None, then: float | None) -> float | None:
    return round((now / then - 1) * 100, 2) if now and then else None


# ---------- the Market Brief ----------
def index_moves(region: str, day: date, weekly: bool) -> list[dict]:
    """The main indices: level and change on the day, or over the week."""
    hub = _main().research_hub
    if not weekly:
        return [{"name": r["name"], "price": round(r["price"], 2), "change_pct": None if r.get("change_pct") is None else round(r["change_pct"], 2),
                 "from_high_pct": None if r.get("from_high_pct") is None else round(r["from_high_pct"], 1)}
                for r in hub.indices(region)]
    out, since = [], reference_day(region, day, True).isoformat()
    for name, sym in INDICES.get(region, []):
        candles = _safe(lambda: hub.yahoo.chart(sym, "1d", 21)["candles"], [])
        before = [c for c in candles if c["t"][:10] <= since]
        if candles and before:
            out.append({"name": name, "price": round(candles[-1]["c"], 2), "change_pct": _pct(candles[-1]["c"], before[-1]["c"])})
    return out


def rotation_shifts(region: str, weekly: bool) -> list[dict]:
    """Sectors that moved to another quadrant of the rotation chart since the last candle (a day, or a week)."""
    out = rotation.run(_main().markets, region, "sectors", None, "weekly" if weekly else "daily", 2)
    return [{"sector": r["name"], "from": r["moved"], "to": r["quadrant"]}
            for r in out["rows"] if r.get("core") and r.get("moved") and r["moved"] != r["quadrant"]]


def stage2_names(region: str, weekly: bool) -> dict:
    """Stocks in the region's broad group that newly match the ST S2 rule, and ones that newly entered Stage 2."""
    group = universes.PRESETS[region][0]
    res = scan.run(_main().markets, region, [{"symbol": s} for s in group["symbols"]])
    window = 5 if weekly else 1

    def row(r):
        return {"symbol": r["symbol"], "name": r.get("name"), "price": round(r["price"], 2),
                "change_pct": None if r.get("chg") is None else round(r["chg"], 2)}
    st_s2 = [row(r) for r in res["rows"] if r["signal"] == "fresh" and r["st_days"] <= window]
    named = {r["symbol"] for r in st_s2}
    stage2 = [row(r) for r in res["rows"] if r["stage"] == 2 and (r.get("stage_days") or 99) <= window and r["symbol"] not in named]
    return {"group": group["name"], "st_s2": st_s2[:12], "stage2": stage2[:12]}


def market_headlines(region: str) -> list[dict]:
    return [{"headline": h["headline"], "url": h.get("url"), "at": h.get("at")}
            for h in _main().research_hub.headlines(region) if h.get("headline")][:HEADLINES]


def market_facts(region: str, day: date, weekly: bool = False) -> dict:
    """Everything the Market Brief reports for one region on one day (or the week to that day). Built once and shared."""
    key = ("market", region, day.isoformat(), weekly, closed(region, day))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    facts = {"kind": "market", "region": region, "day": day.isoformat(), "weekly": weekly,
             "since": reference_day(region, day, weekly).isoformat()}
    for name, fn in (("indices", lambda: index_moves(region, day, weekly)), ("rotation", lambda: rotation_shifts(region, weekly)),
                     ("scan", lambda: stage2_names(region, weekly)), ("headlines", lambda: market_headlines(region))):
        got = _safe(fn)
        if got and (name != "scan" or got["st_s2"] or got["stage2"]):
            facts[name] = got
    if any(k in facts for k in ("indices", "rotation", "scan", "headlines")):
        _cache.set(key, facts, 6 * 3600)
    return facts


# ---------- My Stocks ----------
def _add(out: list, seen: set, region, symbol):
    region, symbol = str(region or "").upper(), str(symbol or "").strip().upper()
    if region in REGIONS and symbol and (region, symbol) not in seen and len(out) < MAX_STOCKS:
        seen.add((region, symbol))
        out.append((region, symbol))


def _instrument(out: list, seen: set, inst):
    if isinstance(inst, dict) and inst.get("type") in EQUITY:
        _add(out, seen, inst.get("market"), inst.get("symbol"))


def my_stocks(uid: str) -> list[tuple[str, str]]:
    """(region, symbol) for the user's watchlist, holdings, notebook instruments and running paper sessions, up to 25."""
    out, seen = [], set()
    try:
        items = json.loads(db.get_setting(f"watchlist:{uid}") or "{}").get("items") or []
    except (ValueError, TypeError, AttributeError):
        items = []
    for i in items:
        if isinstance(i, dict):
            _add(out, seen, i.get("region"), i.get("symbol"))
    for sym in _safe(lambda: holdings.symbols(uid), []) or []:     # holdings count like watchlist names (Indian stocks)
        _add(out, seen, "IN", sym)
    for nb in _safe(lambda: db.list_notebook_rows(uid), []) or []:
        _instrument(out, seen, nb.get("instrument"))
    for s in _safe(lambda: _main().manager.user_running(uid), []) or []:
        _instrument(out, seen, getattr(s, "inst", None))
        for m in getattr(s, "members", None) or []:
            _instrument(out, seen, getattr(m, "inst", None))
    return out


def _symbol_data(region: str, sym: str, day: date) -> dict:
    """One stock's daily candles, filings (India) and recent headlines: fetched once a day for every reader."""
    key = ("stock", region, sym, day.isoformat(), closed(region, day))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    m = _main()

    def bars():
        ids, _ = universes.resolve(m.markets, region, [{"symbol": sym}])
        return scan._bars(m.markets, ids[0]) if ids else None
    data = {"bars": _safe(bars),
            "filings": _safe(lambda: m.filings_feed.announcements(sym, 30)) if region == "IN" else None,
            "news": _safe(lambda: m.research_hub.news.search(f"{sym} share price" if region == "IN" else f"{sym} stock", region, limit=6), [])}
    _cache.set(key, data, 12 * 3600)
    return data


def stock_row(region: str, sym: str, day: date, weekly: bool, since: str) -> dict | None:
    """What changed for one stock since `since` (an ISO date): price, stage, a fresh ST S2 signal, red or amber
    filings and a couple of headlines. None when there's no price data."""
    data = _symbol_data(region, sym, day)
    bars = data["bars"]
    if not bars:
        return None
    ref = reference_day(region, day, weekly).isoformat()
    now = scan.analyse(bars)
    before_bars = [b for b in bars if str(b["t"])[:10] <= ref]
    before = scan.analyse(before_bars) if before_bars else None
    if not now:
        return None
    change = _pct(now["price"], before_bars[-1]["c"] if before_bars else None)
    flags = [{"label": i["label"], "severity": i["severity"], "subject": i["subject"], "at": i["at"], "url": i.get("url")}
             for i in data["filings"] or [] if i["severity"] in ("red", "amber") and i["at"] > since][:4]
    news = [{"headline": n["headline"], "url": n.get("url"), "at": n.get("at")} for n in data["news"] or []
            if n.get("headline") and (not n.get("at") or str(n["at"])[:10] >= since[:10])][:2]
    stage_before = before["stage"] if before else None
    signal = now["signal"] == "fresh" and now["st_days"] <= (5 if weekly else 1)
    stage_moved = now["stage"] is not None and stage_before is not None and now["stage"] != stage_before
    changed = bool(stage_moved or signal or flags or (change is not None and abs(change) >= MOVE[weekly]))
    return {"symbol": sym, "region": region, "price": round(now["price"], 2), "change_pct": change, "stage": now["stage"],
            "stage_before": stage_before, "stage_changed": stage_moved, "st_s2": signal, "filings": flags, "headlines": news,
            "changed": changed}


def paper_lines(uid: str, day: date) -> list[dict]:
    """The user's running paper sessions: today's closed trades and the result since each started."""
    out = []
    for s in _safe(lambda: _main().manager.user_running(uid), []) or []:
        r = _safe(lambda: daily_report.summarise(s, day.isoformat()))
        if not r:
            continue
        total = r["equity"] - r["capital"]
        out.append({"name": r["name"], "currency": r["currency"], "closed": r["closed"], "pnl": round(r["pnl"], 2),
                    "total": round(total, 2), "total_pct": round(total / r["capital"] * 100, 2) if r["capital"] else None})
    return out


def stock_facts(uid: str, day: date, weekly: bool = False, since: str | None = None) -> dict:
    """Everything My Stocks reports for one user. `since` is when their last issue went out (ISO); filings are
    counted from then, or from the reference day if that is later. `changed` is False when there is nothing to send."""
    floor = reference_day("IN", day, weekly).isoformat()
    since = max(since or floor, floor)
    rows = [r for r in (_safe(lambda: stock_row(region, sym, day, weekly, since)) for region, sym in my_stocks(uid)) if r]
    moved = [r for r in rows if r["changed"]]
    return {"kind": "my_stocks", "uid": uid, "day": day.isoformat(), "weekly": weekly, "since": since,
            "stocks": moved, "unchanged": [r["symbol"] for r in rows if not r["changed"]],
            "paper": paper_lines(uid, day), "changed": bool(moved)}
