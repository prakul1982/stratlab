"""/me/drawings: the signed-in user's chart drawings and layout, per region and symbol, kept on the account so they
come back on any device. Validated (kinds, point counts, colours, sizes), size-limited per symbol, and private to
the user: the profile's id is part of every key, so nothing in the URL can reach someone else's."""
from fastapi import APIRouter, Depends

from . import drawings_store as DS
from .auth import current_profile
from .responses import err, ok

router = APIRouter(prefix="/me/drawings", tags=["drawings"])
WRITES = 120          # saves per user per minute (the chart saves a moment after each change)


def _where(region: str, symbol: str) -> tuple[str, str]:
    r, s = DS.region_of(region), DS.symbol_of(symbol)
    if r is None:
        err(400, "bad_region", "That doesn't look like a market code.")
    if s is None:
        err(400, "bad_symbol", "That doesn't look like a symbol.")
    return r, s


def _out(region: str, symbol: str, got: dict) -> dict:
    return ok({"region": region, "symbol": symbol, "drawings": got["drawings"], "layout": got["layout"], "updated_at": got["updated_at"]})


@router.get("/{region}/{symbol}")
def get_drawings(region: str, symbol: str, profile=Depends(current_profile)):
    r, s = _where(region, symbol)
    return _out(r, s, DS.load(profile["id"], r, s))


@router.put("/{region}/{symbol}")
def put_drawings(region: str, symbol: str, req: DS.Payload, profile=Depends(current_profile)):
    r, s = _where(region, symbol)
    from . import main          # imported late: it imports us
    main.throttle(profile, "drawings_save", WRITES, 60, "That's a lot of saves in a minute. Wait a moment and try again.")
    if DS.body_size(req) > DS.MAX_BYTES:
        err(413, "drawings_too_big", f"There are too many drawings on this chart to save (the limit is {DS.MAX_BYTES // 1024} KB). Remove some and try again.")
    return _out(r, s, DS.save(profile["id"], r, s, req))


@router.delete("/{region}/{symbol}")
def delete_symbol(region: str, symbol: str, profile=Depends(current_profile)):
    r, s = _where(region, symbol)
    DS.forget_symbol(profile["id"], r, s)
    return ok({"deleted": True})


@router.delete("")
def delete_all(profile=Depends(current_profile)):
    """Every drawing and layout, on every chart, for this user."""
    return ok({"deleted": True, "symbols": DS.forget(profile["id"])})
