"""/trade/signals and /hooks/signal: forward-testing outside signals in paper trading (the Trade space, Pro).

The page's API (signed in): the user's secret webhook URL (made, replaced or turned off; the token is shown once),
their signal sessions (a paper session per instrument, moved only by signals), each session's log of signals and its
trades, and the verdict's luck checks once a session has 30 closed trades.

The webhook (no sign-in; the secret URL is the key): POST /hooks/signal/<token> with a small JSON signal
(signals.py). It is refused without touching anything when the token is malformed, wrong or turned off (404), when an
address keeps trying wrong tokens or a URL sends too many signals (429), when the body is too big (413) or isn't a
valid signal (400), when the user's plan no longer includes it (403), and when the session isn't one of the URL
owner's running signal sessions (404 or 409). Nothing in a signal is ever run, fetched or sent anywhere; it only ever
moves the owner's own paper position."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db, guard
from . import journal as J
from . import signals as SG
from .auth import current_profile
from .plans import FEATURE_PLAN, PLANS, access_plan, allows
from .signal_session import KIND, SignalSession, defaults, stopped_snapshot

router = APIRouter(prefix="/trade/signals", tags=["signals"])
hook_router = APIRouter(tags=["signals"])
VERDICT_AFTER = 30
FORMAT = {"session": "<session id>", "action": "buy", "qty": 1, "symbol": "<optional>", "id": "<optional alert id>",
          "price": "<optional: the alert's price, for comparison>", "time": "<optional: {{timenow}}>", "note": "<optional>"}


def _m():
    """The main module, for the shared helpers and the paper manager. Imported late: it imports us."""
    from . import main
    return main


class SessionReq(BaseModel):
    name: str = Field("", max_length=60)
    instrument: str = Field(..., min_length=1, max_length=60)
    capital: float | None = Field(None, ge=1000, le=1e10)
    allow_short: bool | None = None
    leverage: float | None = Field(None, ge=1, le=10)
    slippage: float | None = Field(None, ge=0, le=2)
    brokerage: float | None = Field(None, ge=0, le=1000)
    product: str | None = Field(None, pattern=r"^(intraday|delivery)$")


class TestReq(BaseModel):
    action: str = Field(..., pattern=r"^(buy|sell|exit)$")
    qty: float | None = Field(None, gt=0, le=SG.MAX_QTY)


def _plan_name() -> str:
    return PLANS[FEATURE_PLAN["signal_webhooks"]]["name"]


def _rows(uid: str) -> list[dict]:
    """The user's signal sessions, newest first, with whether each is running here now."""
    M = _m()
    running = {s.id for s in M.manager.user_running(uid) if getattr(s, "kind", "") == KIND}
    out = []
    for r in db.user_sessions(uid, 50):
        if not (r.get("instrument") or {}).get("signal"):
            continue
        status = r["status"]
        if status == "running" and r["id"] not in running:
            status = "paused"
        out.append({"id": r["id"], "name": r["name"], "symbol": (r.get("instrument") or {}).get("symbol"), "status": status,
                    "started_at": r["started_at"], "stopped_at": r.get("stopped_at")})
    return out


@router.get("")
def overview(profile=Depends(current_profile)):
    uid = profile["id"]
    return _m().ok({"allowed": allows(profile["_plan"], "signal_webhooks"), "plan": _plan_name(), "hook": SG.current(uid),
                    "sessions": _rows(uid), "misses": list(reversed(SG.misses(uid)))[:50], "format": FORMAT,
                    "limits": {"per_minute": SG.PER_MINUTE, "per_day": SG.PER_DAY, "bytes": SG.MAX_BODY, "late_s": SG.LATE_SECONDS,
                               "stale_s": SG.STALE_SECONDS},
                    "verdict_after": VERDICT_AFTER})


@router.post("/hook")
def new_hook(profile=Depends(current_profile)):
    """A new secret URL (the old one stops at once). The token is in this answer only; it can't be shown again."""
    M = _m()
    M.need(profile, "signal_webhooks", "Forward-testing outside signals")
    M.throttle(profile, "signal_hook", 10, 3600, "That's a lot of new URLs in an hour. Try again a little later.")
    token = SG.issue(profile["id"])
    return M.ok({"path": f"/hooks/signal/{token}", "hook": SG.current(profile["id"])})


@router.delete("/hook")
def off_hook(profile=Depends(current_profile)):
    """Turn the URL off: every signal sent to it is refused from now on."""
    return {"deleted": SG.revoke(profile["id"])}


@router.post("/sessions")
def start(req: SessionReq, profile=Depends(current_profile)):
    """A paper session on one instrument, moved only by signals sent to the user's URL."""
    M = _m()
    M.need(profile, "signal_webhooks", "Forward-testing outside signals")
    _, inst = M.get_instrument(req.instrument)
    if inst.get("type") in ("CE", "PE"):
        M.err(400, "no_options", "Signal sessions trade a stock, index, future, coin or pair. Options structures run as options sessions.")
    if M.needs_fno(inst) and not M.fno(profile):
        M.upgrade("Indian F&O is on the Pro plan.")
    base = defaults(inst)
    got = {k: v for k, v in req.model_dump().items() if k in base and v is not None}
    settings = {**base, **got}
    if settings["allow_short"] and inst.get("market", "IN") == "IN" and inst.get("type") == "EQ" and settings["product"] == "delivery":
        M.err(400, "no_delivery_short", "Shares held for delivery can't be sold short. Use intraday, or turn shorts off.")
    name = req.name.strip() or f"Signals on {inst.get('symbol')}"
    plan = SimpleNamespace(name=name[:60], model_dump=lambda: {"kind": KIND, **settings, "risk": {"capital": settings["capital"]}})
    sess = M.start_session(profile, plan, {**inst, "signal": True})
    return M.ok(sess.snapshot())


def _row(profile, sid: str) -> dict:
    M = _m()
    row = db.get_session_row(profile["id"], M.check_id(sid))
    if not row or (row.get("strategy") or {}).get("kind") != KIND:
        M.err(404, "not_found", "Signal session not found.")
    return row


def _verdict(row: dict, n_trades: int, capital: float) -> dict:
    if n_trades < VERDICT_AFTER:
        return {"ready": False, "trades": n_trades, "need": VERDICT_AFTER}
    ts = J.paper_trades(row)
    return {"ready": True, "trades": n_trades, "need": VERDICT_AFTER, **J.verdict(ts, capital)}


@router.get("/sessions/{sid}")
def session(sid: str, profile=Depends(current_profile)):
    """One signal session: its account, the signal log (arrival times, fills and refusals), trades and the checks."""
    M = _m()
    row = _row(profile, sid)
    live = M.manager.sessions.get(row["id"])
    if isinstance(live, SignalSession) and live.user_id == profile["id"]:
        snap = live.snapshot()
        with live.lock:
            row = {**row, "state": live.state()}
    else:
        snap = stopped_snapshot(row)
        if snap["status"] == "running":
            snap["status"] = "paused"
    snap["orders"] = M.orders_from(snap.get("events") or [])
    snap["verdict"] = _verdict(row, snap["account"]["trades"], snap["account"]["capital"])
    snap["format"] = {**FORMAT, "session": row["id"], "symbol": (row.get("instrument") or {}).get("symbol")}
    return M.ok(snap)


@router.post("/sessions/{sid}/test")
def test_signal(sid: str, req: TestReq, profile=Depends(current_profile)):
    """Send a signal from the page, through the same checks as one from an alert (marked as a test in the log)."""
    M = _m()
    M.need(profile, "signal_webhooks", "Forward-testing outside signals")
    M.throttle(profile, "signal_test", SG.PER_MINUTE, 60, "That's a lot of test signals in a minute. Wait a moment.")
    row = _row(profile, sid)
    body = {"session": row["id"], "action": req.action, "note": "Test from the StratLab page"}
    if req.action != "exit":
        body["qty"] = req.qty if req.qty is not None else 1
    try:
        sig = SG.parse(json.dumps(body).encode())
    except SG.SignalError as e:
        M.err(400, e.code, e.message)
    status, out = deliver(profile["id"], sig)
    if status >= 400 and status != 409:
        M.err(status, out["code"], out["message"])
    return M.ok(out)


def deliver(uid: str, sig: dict) -> tuple[int, dict]:
    """Hand a checked signal to the owner's own running session. (HTTP status, answer)."""
    M = _m()
    now = datetime.now(timezone.utc)
    s = M.manager.sessions.get(sig["session"])
    if not isinstance(s, SignalSession) or s.user_id != uid:
        row = db.get_session_row(uid, sig["session"])
        mine = row is not None and (row.get("strategy") or {}).get("kind") == KIND
        if mine and row.get("status") == "running":
            why, status, code = "The session is paused until market data is back. Nothing was filled.", 409, "paused"
        elif mine:
            why, status, code = "That session has stopped. Start a new one to keep forward-testing.", 409, "stopped"
        else:            # another user's session, an options session, or no session at all: all look the same
            why, status, code = "No signal session with that id on this account.", 404, "no_session"
        SG.log_miss(uid, {"at": now.isoformat(timespec="seconds"), "session": sig["session"], "action": sig["action"],
                          "status": "rejected", "reason": why, "note": sig.get("note")})
        return status, {"status": "rejected", "code": code, "message": why}
    entry = s.on_signal(sig, now)
    try:
        with s.lock:
            st = s.state()
        db.update_session(s.id, state=st)
        s.dirty = False
    except Exception as e:                   # the manager saves it again within half a minute
        print("signal session save failed:", s.id, str(e)[:120])
    try:
        SG.touch(uid)
    except Exception:
        pass
    out = {"status": entry["status"], "reason": entry.get("reason"), "price": entry.get("px"), "session": s.id}
    return (409 if entry["status"] == "rejected" else 200), out


def _answer(status: int, code: str, message: str, extra: dict | None = None) -> JSONResponse:
    if status < 400:
        return JSONResponse(status_code=status, content=extra or {})
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}},
                        headers={"retry-after": "60"} if status == 429 else None)


async def _body(request: Request) -> bytes | None:
    """The request body, or None once it passes SG.MAX_BODY (read no further than that)."""
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) > SG.MAX_BODY:
                return None
        except ValueError:
            return None
    got = bytearray()
    async for chunk in request.stream():
        got += chunk
        if len(got) > SG.MAX_BODY:
            return None
    return bytes(got)


@hook_router.post("/hooks/signal/{token}")
async def hook(token: str, request: Request):
    addr = guard.address(request.scope)
    if not SG.limits.misses_left(addr):
        return _answer(429, "slow_down", "Too many requests with a wrong URL. Wait a minute.")
    if not SG.TOKEN.match(token or ""):
        SG.limits.miss(addr)
        return _answer(404, "not_found", "Not found.")
    over = SG.limits.signal(SG.digest(token))
    if over:
        return _answer(429, "slow_down", over + " Wait a minute.")
    body = await _body(request)
    if body is None:
        return _answer(413, "too_large", f"A signal is at most {SG.MAX_BODY} bytes.")
    return await run_in_threadpool(_hook, token, body, addr)


def _hook(token: str, body: bytes, addr: str) -> JSONResponse:
    uid = SG.owner(token)
    if uid is None:
        SG.limits.miss(addr)
        return _answer(404, "not_found", "Not found.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        profile = db.get_profile(uid)
    except Exception:
        return _answer(503, "busy", "Try again in a moment.")
    if not allows(access_plan(profile), "signal_webhooks"):
        SG.log_miss(uid, {"at": now, "status": "rejected", "reason": f"Forward-testing signals is on the {_plan_name()} plan."})
        return _answer(403, "plan", f"Forward-testing signals is on the {_plan_name()} plan.")
    try:
        sig = SG.parse(body)
    except SG.SignalError as e:
        SG.log_miss(uid, {"at": now, "status": "rejected", "reason": e.message})
        return _answer(e.status, e.code, e.message)
    status, out = deliver(uid, sig)
    if status >= 400:
        return _answer(status, out["code"] if "code" in out else out["status"], out.get("message") or out.get("reason") or "Refused.")
    return _answer(200, "", "", out)
