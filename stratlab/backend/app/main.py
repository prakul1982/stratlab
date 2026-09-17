"""StratLab API."""
import json
import math
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from kiteconnect import exceptions as kite_exc
from razorpay.errors import SignatureVerificationError

from . import billing, db
from .ai_writer import AIBusy, AIError, _model_cache, write_strategy
from .alerts import notify
from .auth import current_profile
from .config import settings
from .engine.core import backtest
from .kite_service import IST, KiteNotReady, KiteService, TickHub, INTERVALS
from .live import LimitError, LiveManager, describe, needs_pro
from .models import (AIReq, AlertsReq, BacktestReq, LiveStartReq, SaveStrategyReq, Strategy,
                     SubscribeReq, VerifyReq)
from .plans import PLANS, trial_state

kite = KiteService()
hub = TickHub(kite)
manager = LiveManager(kite, hub)

MAX_DAYS = {"1d": 3650, "1h": 730, "15m": 365, "5m": 120}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        kite.load_saved_token()
        if kite.ready():
            manager.resume()
    except Exception as e:
        print("startup: Kite not ready:", e)
    manager.start_loop()
    yield


app = FastAPI(title="StratLab API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.FRONTEND_ORIGIN],
                   allow_methods=["*"], allow_headers=["*"])


# ---------- helpers ----------
def err(status: int, code: str, message: str):
    raise HTTPException(status, {"code": code, "message": message})


def upgrade(message: str, code: str = "upgrade_required"):
    err(402, code, message)


def safe(obj):
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [safe(v) for v in obj]
    return obj


def ok(data) -> JSONResponse:
    return JSONResponse(content=safe(data))


def month_start_iso() -> str:
    return datetime.now(IST).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def backtests_used(profile) -> int:
    return db.count_usage(profile["id"], "backtest", month_start_iso())


def is_pro(profile) -> bool:
    return PLANS[profile["_plan"]]["pro_features"]


def get_instrument(token: int) -> dict:
    inst = kite.instrument(token)
    if not inst:
        err(404, "instrument_not_found", "That instrument was not found. Search again.")
    return inst


def check_features(profile, strategy: Strategy, inst: dict | None):
    if not is_pro(profile) and needs_pro(strategy, inst):
        upgrade("Advanced indicators (MACD, Bollinger Bands, VWAP, Supertrend) and F&O are on the Pro plan.")


@app.exception_handler(KiteNotReady)
def _kite_not_ready(request, exc):
    return JSONResponse(status_code=503, content={"detail": {"code": "data_offline", "message": str(exc)}})


@app.exception_handler(kite_exc.KiteException)
def _kite_error(request, exc):
    return JSONResponse(status_code=502, content={"detail": {"code": "data_error",
                        "message": f"Market data request failed: {exc}"}})


# ---------- account ----------
@app.get("/health")
def health():
    ai_key = settings.ANTHROPIC_API_KEY if settings.AI_PROVIDER == "anthropic" else settings.GEMINI_API_KEY
    return {"ok": True, "data_online": kite.ready(), "feed_connected": hub.connected,
            "ai_provider": settings.AI_PROVIDER, "ai_configured": bool(ai_key),
            "ai_model": settings.ANTHROPIC_MODEL if settings.AI_PROVIDER == "anthropic" else (_model_cache["name"] or settings.GEMINI_MODEL)}


@app.get("/plans")
def plans():
    return PLANS


@app.get("/me")
def me(profile=Depends(current_profile)):
    plan = profile["_plan"]
    info = PLANS[plan]
    return ok({
        "id": profile["id"], "email": profile.get("email"),
        "plan": plan, "plan_info": info,
        "billing": {"subscribed_plan": profile.get("plan"), "status": profile.get("plan_status"),
                    "renews_or_ends": profile.get("current_period_end"),
                    "cancel_at_period_end": bool(profile.get("cancel_at_period_end"))},
        "usage": {"backtests_used": backtests_used(profile), "backtests_limit": info["backtests_per_month"],
                  "ai_used": db.count_usage(profile["id"], "ai", month_start_iso()), "ai_limit": info["ai_builds_per_month"]},
        "trial": trial_state(profile) if plan == "free" else None,
        "live_running": len(manager.user_running(profile["id"])), "live_limit": info["live_limit"],
        "alerts": {"enabled": bool(profile.get("alerts_enabled")), "telegram_chat_id": profile.get("telegram_chat_id"),
                   "email": profile.get("alert_email")},
        "data_online": kite.ready(),
    })


@app.put("/me/alerts")
def set_alerts(req: AlertsReq, profile=Depends(current_profile)):
    if not is_pro(profile):
        upgrade("Telegram and email alerts are on the Pro plan.")
    db.update_profile(profile["id"], alerts_enabled=req.alerts_enabled,
                      telegram_chat_id=(req.telegram_chat_id or None), alert_email=(req.alert_email or None))
    return {"saved": True}


@app.post("/me/alerts/test")
def test_alert(profile=Depends(current_profile)):
    if not is_pro(profile):
        upgrade("Telegram and email alerts are on the Pro plan.")
    try:
        sent = notify(profile, "StratLab test alert", "StratLab test alert: your alerts are working.", background=False)
    except Exception as e:
        err(502, "alert_failed", f"Alert could not be sent: {e}")
    if not sent:
        err(400, "no_channels", "Add a Telegram chat ID or an email first, then save.")
    return {"sent": sent}


# ---------- instruments ----------
@app.get("/instruments/defaults")
def instrument_defaults(profile=Depends(current_profile)):
    return kite.defaults()


@app.get("/instruments/search")
def instrument_search(q: str = Query(..., min_length=2, max_length=40), profile=Depends(current_profile)):
    return kite.search(q, allow_fno=is_pro(profile))


@app.get("/instruments/{token}/ltp")
def instrument_ltp(token: int, profile=Depends(current_profile)):
    return {"token": token, "ltp": kite.ltp(token)}


# ---------- strategies ----------
@app.get("/strategies")
def strategies(profile=Depends(current_profile)):
    return db.list_strategies(profile["id"])


@app.post("/strategies")
def create_strategy(req: SaveStrategyReq, profile=Depends(current_profile)):
    return db.save_strategy(profile["id"], req.strategy.name, req.strategy.model_dump(), req.instrument_token)


@app.put("/strategies/{sid}")
def update_strategy(sid: str, req: SaveStrategyReq, profile=Depends(current_profile)):
    row = db.save_strategy(profile["id"], req.strategy.name, req.strategy.model_dump(), req.instrument_token, sid)
    if not row:
        err(404, "not_found", "Strategy not found.")
    return row


@app.delete("/strategies/{sid}")
def remove_strategy(sid: str, profile=Depends(current_profile)):
    db.delete_strategy(profile["id"], sid)
    return {"deleted": True}


@app.post("/export/strategy")
def export_strategy(req: SaveStrategyReq, profile=Depends(current_profile)):
    if not is_pro(profile):
        upgrade("Strategy export is on the Pro plan.")
    inst = kite.instrument(req.instrument_token) if req.instrument_token else None
    payload = {"format": "stratlab-strategy-v1", "exported_at": datetime.now(IST).isoformat(),
               "instrument": inst, "summary": describe(req.strategy), "strategy": req.strategy.model_dump()}
    name = "".join(ch if ch.isalnum() else "-" for ch in req.strategy.name).strip("-") or "strategy"
    return Response(json.dumps(payload, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}.json"'})


@app.post("/ai/strategy")
def ai_strategy(req: AIReq, profile=Depends(current_profile)):
    limit = PLANS[profile["_plan"]]["ai_builds_per_month"]
    used = db.count_usage(profile["id"], "ai", month_start_iso())
    if limit is not None and used >= limit:
        err(429, "ai_limit", f"You've used all {limit} AI builds this month.")
    since = (datetime.now(IST) - timedelta(days=1)).isoformat()
    if db.count_usage(profile["id"], "ai", since) >= 200:
        err(429, "ai_daily_limit", "You've used the AI builder 200 times today. Try again tomorrow.")
    try:
        out = write_strategy(req.text, pro=is_pro(profile))
    except AIBusy as e:
        err(503, "ai_busy", str(e))
    except AIError as e:
        err(422, "ai_failed", str(e))
    db.add_usage(profile["id"], "ai")
    out["usage"] = {"ai_used": used + 1, "ai_limit": limit}
    return out


# ---------- backtest ----------
@app.post("/backtest")
def run_backtest(req: BacktestReq, profile=Depends(current_profile)):
    s = req.strategy
    if not s.entry:
        err(400, "no_entry_rules", "Add at least one entry rule before backtesting.")
    inst = get_instrument(req.instrument_token)
    check_features(profile, s, inst)
    limit = PLANS[profile["_plan"]]["backtests_per_month"]
    used = backtests_used(profile)
    if limit is not None and used >= limit:
        upgrade(f"You've used all {limit} backtests for this month.", "backtest_limit")
    days = min(req.days, MAX_DAYS[s.tf])
    bars = kite.history(inst["token"], s.tf, days + KiteService.warmup_days(s.tf))
    cutoff = (datetime.now(IST) - timedelta(days=days)).isoformat()
    start = next((i for i, b in enumerate(bars) if b["t"] >= cutoff), len(bars))
    if len(bars) - start < 10:
        err(400, "not_enough_data", "Not enough price history for this period. Pick a longer period or another instrument.")
    lot = inst["lot"] if inst["fno"] else 1
    out = backtest(bars, s, start, lot)
    db.add_usage(profile["id"], "backtest")
    out.update({"instrument": inst, "lot": lot, "days": days,
                "warmup_short": start < 200,
                "usage": {"backtests_used": used + 1, "backtests_limit": limit}})
    return ok(out)


# ---------- live paper trading ----------
@app.post("/live/sessions")
def start_live(req: LiveStartReq, profile=Depends(current_profile)):
    s = req.strategy
    if not s.entry:
        err(400, "no_entry_rules", "Add at least one entry rule before going live.")
    inst = get_instrument(req.instrument_token)
    check_features(profile, s, inst)
    if not kite.ready():
        raise KiteNotReady("Market data is offline. The admin needs to complete today's Kite login.")
    if profile["_plan"] == "free":
        t = trial_state(profile)
        if t["started"] and not t["active"]:
            upgrade("Your 24-hour live trial has ended. Upgrade to Basic or Pro to keep paper trading.", "trial_ended")
        if not t["started"]:
            db.update_profile(profile["id"], live_trial_started_at=db.now_iso())
    try:
        sess = manager.start(profile, profile["_plan"], s, inst)
    except LimitError as e:
        upgrade(str(e), "live_limit")
    except ValueError as e:
        err(400, "cannot_start", str(e))
    return ok(sess.snapshot())


@app.get("/live/sessions")
def list_live(profile=Depends(current_profile)):
    running = {s.id for s in manager.user_running(profile["id"])}
    rows = db.user_sessions(profile["id"])
    for r in rows:
        if r["status"] == "running" and r["id"] not in running:
            r["status"] = "paused"   # server restarted and the session could not reattach yet
    return rows


@app.get("/live/sessions/{sid}")
def get_live(sid: str, profile=Depends(current_profile)):
    s = manager.sessions.get(sid)
    if s and s.user_id == profile["id"]:
        snap = s.snapshot()
    else:
        row = db.get_session_row(profile["id"], sid)
        if not row:
            err(404, "not_found", "Session not found.")
        st = row.get("state") or {}
        realised = sum(t["pnl"] for t in st.get("trades", []))
        cap = row["strategy"]["risk"]["capital"]
        snap = {"id": sid, "name": row["name"], "status": row["status"], "stop_reason": row.get("stop_reason"),
                "instrument": row["instrument"], "strategy": row["strategy"], "started_at": row["started_at"],
                "stopped_at": row.get("stopped_at"), "bars": [], "overlays": {}, "oscillators": {},
                "events": st.get("events", []), "equity_curve": st.get("equity_curve", []),
                "account": {"capital": cap, "equity": st.get("cash", cap), "cash": st.get("cash", cap), "qty": 0,
                            "unrealised": 0, "realised": realised, "trades": len(st.get("trades", [])),
                            "wins": sum(1 for t in st.get("trades", []) if t["pnl"] > 0)}}
    snap["orders"] = db.session_orders(sid)
    return ok(snap)


@app.post("/live/sessions/{sid}/stop")
def stop_live(sid: str, profile=Depends(current_profile)):
    s = manager.sessions.get(sid)
    if s and s.user_id == profile["id"]:
        manager.stop(sid, "Stopped by you.")
    elif db.get_session_row(profile["id"], sid):
        db.update_session(sid, status="stopped", stopped_at=db.now_iso(), stop_reason="Stopped by you.")
    else:
        err(404, "not_found", "Session not found.")
    return {"stopped": True}


# ---------- billing ----------
@app.post("/billing/subscribe")
def subscribe(req: SubscribeReq, profile=Depends(current_profile)):
    if profile["_plan"] == req.plan:
        err(400, "already_on_plan", f"You're already on {PLANS[req.plan]['name']}.")
    return billing.create_subscription(profile, req.plan)


@app.post("/billing/verify")
def verify(req: VerifyReq, profile=Depends(current_profile)):
    try:
        billing.verify_checkout(profile, req.razorpay_payment_id, req.razorpay_subscription_id, req.razorpay_signature)
    except SignatureVerificationError:
        err(400, "payment_not_verified", "Payment could not be verified. If money was taken, it will be refunded by Razorpay or activated shortly.")
    return {"activated": True}


@app.post("/billing/cancel")
def cancel(profile=Depends(current_profile)):
    try:
        billing.cancel(profile)
    except ValueError as e:
        err(400, "no_subscription", str(e))
    return {"cancel_at_period_end": True}


@app.post("/billing/webhook")
async def webhook(request: Request):
    body = await request.body()
    try:
        billing.handle_webhook(body, request.headers.get("X-Razorpay-Signature", ""))
    except SignatureVerificationError:
        raise HTTPException(400, "bad signature")
    return {"ok": True}


# ---------- admin: daily Kite login ----------
def _admin(key: str):
    if not settings.ADMIN_KEY or key != settings.ADMIN_KEY:
        raise HTTPException(403, "Forbidden")


@app.get("/admin/kite/login")
def kite_login(key: str = ""):
    _admin(key)
    return RedirectResponse(kite.login_url())


@app.get("/admin/kite/callback", response_class=HTMLResponse)
def kite_callback(request_token: str = "", status: str = "", state: str = ""):
    if status != "success" or not request_token:
        return HTMLResponse("<p>Kite login was cancelled or failed.</p>", status_code=400)
    try:
        kite.complete_login(request_token, state)
    except PermissionError as e:
        return HTMLResponse(f"<p>{e}</p>", status_code=403)
    if hub.started:
        msg = "Kite login saved. The live feed was already running on yesterday's token: restart the server now."
    else:
        manager.resume()
        msg = "Kite login saved. Market data and live sessions are online."
    return HTMLResponse(f"<p>{msg}</p>")


@app.get("/admin/status")
def admin_status(key: str = ""):
    _admin(key)
    return {"kite_ready": kite.ready(), "feed_started": hub.started, "feed_connected": hub.connected,
            "live_sessions": len(manager.sessions), "subscribed_tokens": len(hub.listeners)}
