"""/watch: Market Watch (MW-1). The person's lists (GET/POST/PATCH/DELETE /watch/lists, PUT /watch/lists/{id}/items, PUT /watch/order),
prices for the instruments in view (/watch/quotes, /watch/spark), the live stream of them (/watch/stream) and the fixed board a
visitor who isn't signed in sees (/public/markets/watch).

Lists are private to the person: the profile's id is part of every row, so nothing in a URL can reach someone else's. Limits are
the plan's (plans.py) and are refused with a plain message that names what the next plan keeps. Reads are shared and bounded
(watch_quotes, watch_stream); nothing here runs when nobody has the panel open."""
import asyncio
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import watch_quotes as WQ, watch_store as WS
from .auth import current_profile
from .responses import ok, safe
from .watch_stream import MAX_PER_CONN, StreamHub

router = APIRouter(prefix="/watch", tags=["watch"])
public_router = APIRouter(prefix="/public/markets", tags=["watch"])
WRITES = 60            # list changes per person per minute
READS = 40             # quote reads per person per minute (the panel asks every 5 seconds: 12)
SPARKS = 30
STREAMS = 20           # streams a person may open per minute (a reconnecting page opens one a few seconds apart)

_hub: StreamHub | None = None


def _m():
    """The main module, for the broker, the markets registry and the shared tick feed. Imported late: it imports us."""
    from . import main
    return main


def stream_token(key: str) -> int | None:
    """The broker's instrument token for a chart key ("IN:RELIANCE", "IN:^NSEI", "MCX:GOLDM"), or None when the broker's
    feed doesn't carry it (a US stock, crypto, forex...) or its login is off."""
    m = _m()
    market, _, sym = key.partition(":")
    if not sym or not m.kite.ready():
        return None
    if market == "IN":
        inst = m.research_hub._kite_index(sym) if sym.startswith("^") else (m.kite.equity(sym) or m.kite.by_symbol(sym))
        return int(inst["token"]) if inst and inst.get("token") else None
    if market in ("MCX", "CDS"):
        inst = m.markets.resolve(key)[1]
        return int(inst["token"]) if inst and inst.get("token") else None
    return None


def stream_hub() -> StreamHub:
    global _hub
    ticks = _m().hub
    if _hub is None or _hub.ticks is not ticks:           # the shared feed is the one main holds (a test swaps it)
        _hub = StreamHub(ticks, stream_token)
    return _hub


def _known(item: dict) -> bool | None:
    """Whether StratLab knows an instrument added to a list: False when it surely doesn't, None when it can't tell."""
    m, market, sym = _m(), item["market"], item["symbol"]
    try:
        if market in ("IN", "US"):
            if sym.startswith("^"):
                return sym in WS.INDICES and ((market == "IN") == (sym in ("^NSEI", "^BSESN", "^NSEBANK")))
            from .intel import routes as intel
            fn = getattr(intel, "known_symbol", None)
            return fn(market, sym) if callable(fn) else None
        prov, inst = m.markets.resolve(item["id"])
        if prov is None:
            return False
        if not prov.ready():
            return None
        return inst is not None
    except Exception:
        return None


def _ids(raw: str) -> list[str]:
    return [i.strip() for i in raw.split(",") if i.strip()][:WQ.MAX_IDS]


def _plan(profile) -> str:
    return profile["_plan"]


def _out(profile) -> dict:
    return {"lists": WS.all_lists(profile["id"]), "limits": WS.limits(_plan(profile))}


class NameReq(BaseModel):
    name: str = Field(..., max_length=200)


class ItemsReq(BaseModel):
    items: list[dict] = Field(default_factory=list, max_length=WS.HARD_SYMBOLS)


class OrderReq(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=WS.HARD_LISTS)


def _write(profile) -> None:
    _m().throttle(profile, "watch_write", WRITES, 60, "That's a lot of changes in a minute. Wait a moment and try again.")


@router.get("/lists")
def get_lists(profile=Depends(current_profile)):
    """Every list in order, the first being the Research watchlist, and what the plan allows."""
    return ok(_out(profile))


@router.post("/lists")
def create_list(req: NameReq, profile=Depends(current_profile)):
    _write(profile)
    WS.create(profile["id"], req.name, _plan(profile))
    return ok(_out(profile))


@router.patch("/lists/{list_id}")
def rename_list(list_id: str, req: NameReq, profile=Depends(current_profile)):
    _write(profile)
    WS.rename(profile["id"], list_id[:60], req.name)
    return ok(_out(profile))


@router.delete("/lists/{list_id}")
def delete_list(list_id: str, profile=Depends(current_profile)):
    _write(profile)
    WS.delete(profile["id"], list_id[:60])
    return ok(_out(profile))


@router.put("/lists/{list_id}/items")
def put_items(list_id: str, req: ItemsReq, profile=Depends(current_profile)):
    """Replace a list's items: what is in it and in what order, in one call."""
    _write(profile)
    uid = profile["id"]
    before = {i["id"] for i in WS.default_items(uid)} if list_id == WS.DEFAULT_ID else set()
    WS.set_items(uid, list_id[:60], req.items, _plan(profile), _known)
    if list_id == WS.DEFAULT_ID:                     # a stock added to the first list counts as starring it, for invites
        got = {i["id"] for i in WS.default_items(uid)}
        if any(i.split(":")[0] in WS.RESEARCH and not i.split(":")[1].startswith("^") for i in got - before):
            from . import invite_rewards
            invite_rewards.safe_touch(profile, "watchlist")
    return ok(_out(profile))


@router.put("/order")
def put_order(req: OrderReq, profile=Depends(current_profile)):
    _write(profile)
    WS.reorder(profile["id"], [i[:60] for i in req.ids])
    return ok(_out(profile))


@router.get("/quotes")
def get_quotes(ids: str = Query("", max_length=1500), profile=Depends(current_profile)):
    """The last price and the day's change of up to 24 instruments, as the lists name them ("IN:RELIANCE", "CRYPTO:BTC-USD")."""
    _m().throttle(profile, "watch_quotes", READS, 60, "That's a lot of price reads in a minute. Wait a moment and try again.")
    return ok({"quotes": WQ.quotes(_ids(ids))})


@router.get("/spark")
def get_spark(ids: str = Query("", max_length=1500), profile=Depends(current_profile)):
    """A short line of recent daily closes for each instrument, for the list's rows."""
    _m().throttle(profile, "watch_spark", SPARKS, 60, "That's a lot of reads in a minute. Wait a moment and try again.")
    return ok({"sparks": WQ.sparks(_ids(ids))})


@router.get("/stream")
async def stream(request: Request, ids: str = Query("", max_length=1500), profile=Depends(current_profile)):
    """A server-sent-events stream of live prices for instruments the broker's feed carries (Indian stocks, indices, MCX and
    currency futures), at most two events a second, while the market trades. `hello` says which are streamed and which the page
    should keep reading through /watch/quotes; `tick` carries [{k, p, v, t}] (key, last price, day's volume, time)."""
    m = _m()
    m.throttle(profile, "watch_stream", STREAMS, 60, "That's a lot of live connections in a minute. Wait a moment and try again.")
    keys = _ids(ids)[:MAX_PER_CONN]
    hub, why = stream_hub(), None
    from .intel.company import market_open
    if not m.kite.ready() or m.kite.invalid_reason:
        why = "no_login"
    elif not market_open("IN") and not any(k.startswith(("MCX:", "CDS:")) for k in keys):
        why = "closed"
    conn, live, poll = (None, [], keys)
    if why is None:
        conn, live, poll = await run_in_threadpool(hub.open, profile["id"], keys, asyncio.get_running_loop())
        if conn is None:
            why = "limit"
        elif not live:
            hub.close(conn)
            conn, why = None, "none"
    hello = {"live": live, "poll": poll, **({"reason": why} if why else {})}
    headers = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    if conn is None:
        async def once():
            yield f"event: hello\ndata: {json.dumps(hello, separators=(',', ':'))}\n\nevent: bye\ndata: {json.dumps({'reason': 'poll'})}\n\n"
        return StreamingResponse(once(), media_type="text/event-stream", headers=headers)
    return StreamingResponse(hub.feed(conn, hello, request), media_type="text/event-stream", headers=headers)


@public_router.get("/watch")
def public_watch():
    """The board a visitor sees: a fixed set of indices, bitcoin, forex and commodities with price, day's change and a line of
    closes. The same answer for everyone, read once every few seconds."""
    return JSONResponse(safe({"rows": WQ.public_board()}), headers={"Cache-Control": "public, max-age=10"})
