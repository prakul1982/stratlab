"""/me/drawings: the signed-in user's chart drawings and layout, per region and symbol, kept on the account so they
come back on any device. Validated (kinds, point counts, colours, sizes), size-limited per symbol, and private to
the user: the profile's id is part of every key, so nothing in the URL can reach someone else's."""
from fastapi import APIRouter, Depends

from . import drawings_store as DS
from .auth import current_profile
from .plans import PLANS, bigger_plan
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


def _says(plan: str, key: str, what: str) -> str:
    """What the plan keeps and what the next one up does, plainly (the same words the Plans page uses)."""
    nxt = bigger_plan(plan, key)
    more = f" {nxt} {'has no limit' if PLANS[nxt.lower()][key] is None else 'keeps ' + str(PLANS[nxt.lower()][key])}." if nxt else ""
    return f"The {PLANS[plan]['name']} plan keeps {PLANS[plan][key]} {what}.{more}"


def _check_plan(profile, region: str, symbol: str, req: DS.Payload) -> None:
    """MW-1: drawings and indicators are kept on a limited number of charts, with a limited number of indicators on each. A
    chart already saved stays editable, so a plan that went down never loses one; only a new chart past the limit, or more
    indicators than the plan allows on one, is refused."""
    plan = profile["_plan"]
    charts, inds = PLANS[plan]["chart_saves"], PLANS[plan]["chart_indicators"]
    studies = (req.layout.studies or []) if req.layout else []
    if inds is not None and len(studies) > inds:
        err(402, "plan_limit", _says(plan, "chart_indicators", "indicators on a chart"))
    if charts is not None and (req.drawings or studies):
        idx = DS._index(profile["id"])
        if not DS.holds_work(idx, f"{region}:{symbol}") and DS.kept_charts(idx) >= charts:
            err(402, "plan_limit", _says(plan, "chart_saves", "charts with saved drawings and indicators"))


@router.get("/summary")
def summary(region: str | None = None, symbol: str | None = None, profile=Depends(current_profile)):
    """How many charts keep drawings or indicators, against the plan: for the chart to say so before the limit is met. With a `region` and
    `symbol`, also whether that chart is one of them."""
    plan = profile["_plan"]
    idx = DS._index(profile["id"])
    r, s = DS.region_of(region or ""), DS.symbol_of(symbol or "")
    return ok({"charts": DS.kept_charts(idx), "limit": PLANS[plan]["chart_saves"], "indicators": PLANS[plan]["chart_indicators"],
               "saved": bool(r and s and DS.holds_work(idx, f"{r}:{s}")),
               "next": {"charts": bigger_plan(plan, "chart_saves"), "indicators": bigger_plan(plan, "chart_indicators")}})


@router.get("/{region}/{symbol}")
def get_drawings(region: str, symbol: str, profile=Depends(current_profile)):
    r, s = _where(region, symbol)
    return _out(r, s, DS.load(profile["id"], r, s))


@router.put("/{region}/{symbol}")
def put_drawings(region: str, symbol: str, req: DS.Payload, profile=Depends(current_profile)):
    r, s = _where(region, symbol)
    from . import main          # imported late: it imports us
    main.throttle(profile, "drawings_save", WRITES, 60, "That's a lot of saves in a minute. Wait a moment and try again.")
    _check_plan(profile, r, s, req)
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
