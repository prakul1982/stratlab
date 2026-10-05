"""/chart: the price chart's own API. Candles for any instrument the markets registry knows (notebooks, backtests,
paper trading), with older pages for scrolling back, and the signed-in user's drawings per symbol."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from . import chart_data as CD
from .auth import current_profile
from .responses import err, ok

router = APIRouter(prefix="/chart", tags=["chart"])


def _m():
    """The main module, for the markets registry and its instrument lookup. Imported late: it imports us."""
    from . import main
    return main


@router.get("/candles/{inst_id}")
def candles(inst_id: str, tf: str = "1d", range: str = Query("1y", max_length=5), before: str | None = Query(None, max_length=40),
            profile=Depends(current_profile)):
    """One instrument's candles: `tf` 5m, 15m, 1h or 1d, the first read covering `range`, or with `before` the page
    of candles older than that time. `more` says whether still older candles exist."""
    if tf not in CD.TFS:
        err(400, "bad_tf", "Pick 5m, 15m, 1h or 1d candles.")
    if len(inst_id) > 60:
        err(404, "instrument_not_found", "That instrument was not found. Search again.")
    m = _m()
    prov, inst = m.get_instrument(inst_id)
    if m.needs_fno(inst) and not m.fno(profile):          # the same line as search and backtests: F&O is Pro
        m.upgrade("Charts of Indian futures and options are on the Pro plan.")
    until = CD.parse_before(before)
    max_days = (getattr(prov, "max_days", None) or {}).get(tf)
    if max_days is None:
        err(400, "bad_tf", "This market doesn't have candles of that size.")
    days, more = CD.window(tf, range.lower(), until, max_days)
    bars = CD.older(prov.history(inst, tf, days), until)
    return ok({"currency": inst.get("currency"), "tf": tf, "more": more,
               "candles": [{k: b.get(k) for k in ("t", "o", "h", "l", "c", "v")} for b in bars]})


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
