"""/chart: the price chart's own API. Candles for any instrument the markets registry knows (notebooks, backtests,
paper trading, the chart workspace), of every timeframe from 1 minute to a month, with older pages for scrolling back, and the
signed-in user's drawings per symbol."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from . import bar_agg, chart_data as CD, chart_feed as CF
from .auth import current_profile
from .responses import err, ok

router = APIRouter(prefix="/chart", tags=["chart"])
CANDLE_READS = 60          # candle reads per user per minute


def _m():
    """The main module, for the markets registry and its instrument lookup. Imported late: it imports us."""
    from . import main
    return main


@router.get("/candles/{inst_id}")
def candles(inst_id: str, tf: str = "1d", range: str = Query("1y", max_length=5), before: str | None = Query(None, max_length=40),
            profile=Depends(current_profile)):
    """One instrument's candles: `tf` is 1m, 3m, 5m, 10m, 15m, 30m, 1h, 2h, 4h, 1d, 1w or 1mo, the first read covering
    `range`, or with `before` the page of candles older than that time. `more` says whether still older candles exist;
    `live` and `delayed` say how current the newest one is. Sizes a source doesn't send are built from smaller ones on the
    exchange's own session clock (bar_agg)."""
    if tf not in CD.TFS:
        err(400, "bad_tf", "Pick a candle size from 1 minute to 1 month.")
    if len(inst_id) > 60:
        err(404, "instrument_not_found", "That instrument was not found. Search again.")
    m = _m()
    # each read can reach the market data source: about one a second per user is plenty for scrolling back
    m.throttle(profile, "chart_candles", CANDLE_READS, 60, "That's a lot of chart reads in a minute. Wait a moment and try again.")
    prov, inst = m.get_instrument(inst_id)
    if m.needs_fno(inst) and not m.fno(profile):          # the same line as search and backtests: F&O is Pro
        m.upgrade("Charts of Indian futures and options are on the Pro plan.")
    until = CD.parse_before(before)
    market = inst.get("market")
    base = bar_agg.base_of(tf)
    live = CF.delivery(market or "", True)           # a provider that is ready: the broker is on, or it isn't the broker's market
    if base == "1m":
        kind = CF.minute_kind(market or "", True)
        start, end, more = CF.minute_window(tf, kind, until)
        kite = getattr(prov, "kite", None)
        if kind == "kite" and kite is not None:
            raw = kite.history_range(int(inst["token"]), "1m", start, end)
        elif hasattr(prov, "minute_history"):
            raw = prov.minute_history(inst, start, end)
        else:
            err(400, "bad_tf", "This market doesn't have candles of that size.")
        bars = CF.build(raw, market, tf, until, more)
        return ok({"currency": inst.get("currency"), "tf": tf, "more": more, **live, "candles": _rows(bars)})
    max_days = (getattr(prov, "max_days", None) or {}).get(base)
    if max_days is None:
        err(400, "bad_tf", "This market doesn't have candles of that size.")
    days, more = CD.window(base, range.lower(), until, max_days)
    bars = CD.older(prov.history(inst, base, days), until)
    from .options.data import frozen_series
    # daily candles that are one standing price with no volume for a week: no live quote, and the chart says so (R13-002)
    stale = tf == "1d" and not until and market in ("CDS", "MCX") and frozen_series(bars)
    bars = CF.build(bars, market, tf, None, more) if base != tf else bars
    return ok({"currency": inst.get("currency"), "tf": tf, "more": more, **live, **({"no_live": True} if stale else {}),
               "candles": _rows(bars)})


def _rows(bars: list[dict]) -> list[dict]:
    return [{k: b.get(k) for k in ("t", "o", "h", "l", "c", "v")} for b in bars]


class DrawingsReq(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=40)
    items: list = Field(default_factory=list, max_length=CD.MAX_DRAWINGS)


def _symbol(symbol: str) -> str:
    if not CD.SYMBOL.match(symbol or ""):
        err(400, "bad_symbol", "That doesn't look like a symbol.")
    return symbol.upper()


@router.get("/drawings")
def get_drawings(symbol: str = Query(..., max_length=40), profile=Depends(current_profile)):
    sym = _symbol(symbol)
    return ok({"symbol": sym, "items": CD.drawings(profile["id"], sym)})


@router.put("/drawings")
def put_drawings(req: DrawingsReq, profile=Depends(current_profile)):
    sym = _symbol(req.symbol)
    return ok({"symbol": sym, "items": CD.save(profile["id"], sym, req.items)})


@router.delete("/drawings")
def delete_drawings(profile=Depends(current_profile)):
    """Every drawing on every chart, for this user."""
    CD.forget(profile["id"])
    return ok({"deleted": True})
