"""StratLab API."""
import json
import logging
import math
import secrets
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from kiteconnect import exceptions as kite_exc
from razorpay.errors import SignatureVerificationError

from . import admin, basket, billing, db, importer
from .ai_providers import health as ai_health, test_all as ai_test_all
from .ai_writer import AIBusy, AIError, _anthropic, _gemini, write_strategy
from .alerts import notify
from .auth import current_profile
from .config import settings
from . import research
from .engine import walkforward
from .data import DataError, Registry
from .intel import routes as research_routes
from .intel.company import Research
from .kite_auto import AutoLogin, AutoLoginError, configured as auto_login_configured, restart_process
from .kite_service import IST, KiteNotReady, KiteService, TickHub
from .live import LimitError, LiveManager, describe, needs_pro
from .models import (AdminPlanReq, AIReq, ImportReq, AlertsReq, BacktestReq, ExperimentReq, LiveStartReq, NotebookReq, SaveStrategyReq,
                     Strategy, SubscribeReq, VerifyReq)
from .plans import PLANS, has_pro_features, plan_info, trial_state

kite = KiteService()
hub = TickHub(kite)
markets = Registry(kite)
manager = LiveManager(kite, hub, markets)
research_hub = Research(kite, yahoo=markets.providers["US"].yahoo)   # one Yahoo client (and cache) for both


def after_login() -> str:
    """Bring market data and live sessions online with the new Kite token."""
    if hub.started:
        if settings.KITE_RESTART_AFTER_LOGIN:
            manager.persist(only_dirty=False)
            restart_process()
            return "Kite login saved. The server is restarting to reconnect the live feed; it's back in about a minute."
        return "Kite login saved. The live feed was already running on yesterday's token: restart the server now."
    manager.resume()
    return "Kite login saved. Market data and live sessions are online."


auto_login = AutoLogin(kite, after_login)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        kite.load_saved_token()
    except Exception as e:
        print("startup: Kite not ready:", e)
    try:
        manager.resume()  # crypto sessions always; India ones once Kite is logged in
    except Exception as e:
        print("startup: could not resume sessions:", e)
    manager.start_loop()
    auto_login.start()
    yield


log = logging.getLogger("stratlab")
app = FastAPI(title="StratLab API", lifespan=lifespan)
research_routes.setup(research_hub, _gemini, _anthropic)
app.include_router(research_routes.router)


@app.middleware("http")
async def unexpected_errors(request: Request, call_next):
    """Turn crashes into a normal JSON error. Registered before CORS, so the browser can still read it."""
    try:
        return await call_next(request)
    except Exception:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": {"code": "server_error",
                            "message": "Something went wrong on our side. Try again in a moment."}})


app.add_middleware(CORSMiddleware, allow_origins=settings.FRONTEND_ORIGINS,
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
    return has_pro_features(profile["_plan"])


def check_id(sid: str) -> str:
    """Saved strategy and session ids are UUIDs; anything else would make Postgres error out."""
    try:
        return str(uuid.UUID(sid))
    except ValueError:
        err(404, "not_found", "Not found.")


def get_instrument(inst_id: str) -> tuple:
    prov, inst = markets.resolve(inst_id)
    if prov is None:
        err(400, "market_unavailable", "That market isn't connected yet.")
    if not prov.ready():
        raise KiteNotReady("Market data for this market is offline right now.")
    if not inst:
        err(404, "instrument_not_found", "That instrument was not found. Search again.")
    return prov, inst


def check_features(profile, strategy: Strategy, inst: dict | None):
    if not is_pro(profile) and needs_pro(strategy, inst):
        upgrade("Advanced indicators (MACD, Bollinger Bands, VWAP, Supertrend, ADX, Stochastic, Donchian and more) and F&O are on the Pro plan.")


@app.exception_handler(KiteNotReady)
def _kite_not_ready(request, exc):
    return JSONResponse(status_code=503, content={"detail": {"code": "data_offline", "message": str(exc)}})


@app.exception_handler(research.ResearchError)
def _research_error(request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code, "message": exc.message}})


@app.exception_handler(DataError)
def _data_error(request, exc):
    return JSONResponse(status_code=502, content={"detail": {"code": "data_error", "message": str(exc)}})


@app.exception_handler(kite_exc.KiteException)
def _kite_error(request, exc):
    return JSONResponse(status_code=502, content={"detail": {"code": "data_error",
                        "message": f"Market data request failed: {exc}"}})


# ---------- account ----------
@app.get("/health")
def health():
    ai = ai_health()
    return {"ok": True, "data_online": kite.ready(), "feed_connected": hub.connected,
            "ai_configured": any(p["in_use"] for p in ai), "ai": ai}


@app.get("/plans")
def plans():
    return PLANS


@app.get("/me")
def me(profile=Depends(current_profile)):
    plan = profile["_plan"]
    info = plan_info(plan)
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
        "billing_enabled": billing.enabled(),
        "is_admin": admin.is_admin(profile),
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


# ---------- markets and instruments ----------
@app.get("/markets")
def list_markets():
    return markets.markets()


@app.get("/instruments/defaults")
def instrument_defaults(profile=Depends(current_profile)):
    return markets.defaults()


@app.get("/instruments/search")
def instrument_search(q: str = Query(..., min_length=2, max_length=40), market: str | None = Query(None, max_length=10),
                      profile=Depends(current_profile)):
    return markets.search(q, market.upper() if market else None, allow_fno=is_pro(profile))


@app.get("/instruments/{inst_id}")
def instrument_info(inst_id: str, profile=Depends(current_profile)):
    return get_instrument(inst_id)[1]


@app.get("/instruments/{inst_id}/ltp")
def instrument_ltp(inst_id: str, profile=Depends(current_profile)):
    prov, inst = get_instrument(inst_id)
    return {"id": inst["id"], "ltp": prov.ltp(inst)}


# ---------- strategies ----------
@app.get("/strategies")
def strategies(profile=Depends(current_profile)):
    return db.list_strategies(profile["id"])


@app.post("/strategies")
def create_strategy(req: SaveStrategyReq, profile=Depends(current_profile)):
    return db.save_strategy(profile["id"], req.strategy.name, req.strategy.model_dump(), req.instrument_token)


@app.put("/strategies/{sid}")
def update_strategy(sid: str, req: SaveStrategyReq, profile=Depends(current_profile)):
    sid = check_id(sid)
    row = db.save_strategy(profile["id"], req.strategy.name, req.strategy.model_dump(), req.instrument_token, sid)
    if not row:
        err(404, "not_found", "Strategy not found.")
    return row


@app.delete("/strategies/{sid}")
def remove_strategy(sid: str, profile=Depends(current_profile)):
    sid = check_id(sid)
    db.delete_strategy(profile["id"], sid)
    return {"deleted": True}


@app.post("/export/strategy")
def export_strategy(req: SaveStrategyReq, profile=Depends(current_profile)):
    if not is_pro(profile):
        upgrade("Strategy export is on the Pro plan.")
    iid = req.instrument or (f"IN:{req.instrument_token}" if req.instrument_token else None)
    inst = markets.resolve(iid)[1] if iid else None
    payload = {"format": "stratlab-strategy-v1", "exported_at": datetime.now(IST).isoformat(),
               "instrument": inst, "summary": describe(req.strategy), "strategy": req.strategy.model_dump()}
    name = "".join(ch if ch.isalnum() else "-" for ch in req.strategy.name).strip("-") or "strategy"
    return Response(json.dumps(payload, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}.json"'})


def ai_allowance(profile) -> tuple[int, int | None]:
    """AI builds used this month and the plan's limit; errors out when either cap is reached."""
    limit = PLANS[profile["_plan"]]["ai_builds_per_month"]
    used = db.count_usage(profile["id"], "ai", month_start_iso())
    if limit is not None and used >= limit:
        err(429, "ai_limit", f"You've used all {limit} AI builds this month.")
    since = (datetime.now(IST) - timedelta(days=1)).isoformat()
    if db.count_usage(profile["id"], "ai", since) >= 200:
        err(429, "ai_daily_limit", "You've used the AI builder 200 times today. Try again tomorrow.")
    return used, limit


@app.post("/import/strategy")
def import_strategy(req: ImportReq, profile=Depends(current_profile)):
    """Turn an existing strategy (StratLab export, Pine Script, Python, MQL, AFL or plain words) into rules."""
    fmt = importer.detect(req.text, req.filename)
    base = {"source": fmt, "source_name": importer.FORMATS[fmt]}
    if fmt in ("stratlab", "json"):
        try:
            return {**base, **importer.from_json(req.text), "used_ai": False}
        except ValueError as e:
            if fmt == "stratlab":
                err(400, "bad_import", str(e))
            fmt = "text"   # some other JSON: let the AI make sense of it
    used, limit = ai_allowance(profile)
    try:
        out = write_strategy(importer.ai_prompt(fmt, req.text), pro=is_pro(profile))
        db.add_usage(profile["id"], "ai")
        used_ai, usage = True, {"ai_used": used + 1, "ai_limit": limit}
        if not out["entry"] and fmt == "pine":
            out, used_ai = importer.pine(req.text), False
    except AIError as e:
        if fmt != "pine":
            err(503 if isinstance(e, AIBusy) else 422, "ai_busy" if isinstance(e, AIBusy) else "ai_failed",
                "The AI translator couldn't run just now, so this couldn't be imported. Try again in a minute. "
                "(TradingView Pine Script can be read without the AI.)")
        out, used_ai, usage = importer.pine(req.text), False, None
    if not out["entry"]:
        err(422, "nothing_imported", "No entry rules could be found in that. "
            "Check it's a strategy (with buy or short conditions), or describe the idea in words instead.")
    return {**base, **out, "used_ai": used_ai, "usage": usage}


@app.post("/ai/strategy")
def ai_strategy(req: AIReq, profile=Depends(current_profile)):
    used, limit = ai_allowance(profile)
    try:
        out = write_strategy(req.text, pro=is_pro(profile))
    except AIBusy as e:
        err(503, "ai_busy", str(e))
    except AIError as e:
        err(422, "ai_failed", str(e))
    db.add_usage(profile["id"], "ai")
    out["usage"] = {"ai_used": used + 1, "ai_limit": limit}
    return out


_ai_tests: dict[str, float] = {}


@app.post("/ai/test")
def ai_test(profile=Depends(current_profile)):
    """Try every configured AI provider once and report exactly what happened (for the connection check)."""
    last = _ai_tests.get(profile["id"], 0.0)
    if datetime.now().timestamp() - last < 20:
        err(429, "ai_test_wait", "Wait a few seconds before testing again.")
    _ai_tests[profile["id"]] = datetime.now().timestamp()
    return {"providers": ai_test_all(gemini=_gemini, anthropic=_anthropic)}


# ---------- backtests and notebooks ----------
def use_backtest(profile) -> int | None:
    """Check the monthly backtest limit before running one; returns the limit."""
    limit = PLANS[profile["_plan"]]["backtests_per_month"]
    if limit is not None and backtests_used(profile) >= limit:
        upgrade(f"You've used all {limit} backtests for this month.", "backtest_limit")
    return limit


def run_test(profile, strategy: Strategy, req) -> dict:
    if not strategy.entry:
        err(400, "no_entry_rules", "Add at least one buy rule first.")
    limit = use_backtest(profile)
    data = research.load(markets, strategy, req)
    check_features(profile, strategy, data["inst"])
    out = research.run(strategy, data)
    db.add_usage(profile["id"], "backtest")
    used = backtests_used(profile)
    out["usage"] = {"backtests_used": used, "backtests_limit": limit}
    return out


@app.post("/backtest")
def run_backtest(req: BacktestReq, profile=Depends(current_profile)):
    return ok(run_test(profile, req.strategy, req))


def notebook_from_row(row: dict) -> dict:
    """Notebooks live in the strategies table. Rows saved before notebooks existed hold a bare strategy."""
    body = row.get("body") or {}
    if body.get("kind") != "notebook":
        token = row.get("instrument_token")
        body = {"kind": "notebook", "question": row.get("name") or "", "notes": "", "strategy": body,
                "instrument": {"id": f"IN:{token}"} if token else None, "experiments": [],
                "summary": research.summary([])}
    return {"id": row["id"], "name": row.get("name"), "updated_at": row.get("updated_at"), **body}


def get_notebook(profile, nid: str) -> dict:
    row = db.get_strategy(profile["id"], check_id(nid))
    if not row:
        err(404, "not_found", "Notebook not found.")
    return notebook_from_row(row)


def save_notebook(profile, nb: dict) -> dict:
    body = {k: nb.get(k) for k in ("kind", "question", "notes", "strategy", "instrument", "experiments", "summary", "pinned")}
    body["kind"] = "notebook"
    body["tf"] = (nb.get("strategy") or {}).get("tf")
    inst = nb.get("instrument") or {}
    token = inst.get("token") if inst.get("market") == "IN" else None
    row = db.save_strategy(profile["id"], nb.get("name") or "Untitled notebook", body, token, nb.get("id"))
    if not row:
        err(404, "not_found", "Notebook not found.")
    return notebook_from_row(row)


def instrument_summary(inst_id: str | None) -> dict | None:
    if not inst_id:
        return None
    if inst_id.startswith("CSV:"):
        name = inst_id[4:].strip()[:60] or "Uploaded data"
        return {"id": "CSV:upload", "symbol": name, "name": name, "market": "CSV", "currency": "", "tz": "UTC"}
    try:
        return get_instrument(inst_id)[1]
    except (HTTPException, KiteNotReady, DataError):
        # market data is briefly offline: keep the id, details fill in on the next save
        return {"id": inst_id}


@app.get("/notebooks")
def list_notebooks(profile=Depends(current_profile)):
    out = []
    for r in db.list_notebook_rows(profile["id"]):
        if r.get("kind") != "notebook":  # an older saved strategy
            r.update({"question": r.get("name"), "summary": research.summary([]),
                      "instrument": {"id": f"IN:{r['instrument_token']}"} if r.get("instrument_token") else None})
        out.append({**{k: r.get(k) for k in ("id", "name", "question", "instrument", "summary", "updated_at", "tf")},
                    "pinned": r.get("pinned") in (True, "true")})
    out.sort(key=lambda n: not n["pinned"])      # pinned first, most recent first within each group
    return out


@app.post("/notebooks")
def create_notebook(req: NotebookReq, profile=Depends(current_profile)):
    strategy = req.strategy or Strategy(name=req.name or "Untitled notebook")
    nb = {"name": req.name or strategy.name, "question": req.question or "", "notes": req.notes or "",
          "strategy": strategy.model_dump(), "instrument": instrument_summary(req.instrument),
          "experiments": [], "summary": research.summary([])}
    return save_notebook(profile, nb)


@app.get("/notebooks/{nid}")
def read_notebook(nid: str, profile=Depends(current_profile)):
    return ok(get_notebook(profile, nid))


@app.put("/notebooks/{nid}")
def update_notebook(nid: str, req: NotebookReq, profile=Depends(current_profile)):
    nb = get_notebook(profile, nid)
    if req.name is not None:
        nb["name"] = req.name or "Untitled notebook"
    if req.question is not None:
        nb["question"] = req.question
    if req.notes is not None:
        nb["notes"] = req.notes
    if req.strategy is not None:
        nb["strategy"] = req.strategy.model_dump()
    if req.instrument is not None:
        nb["instrument"] = instrument_summary(req.instrument or None)
    if req.pinned is not None:
        nb["pinned"] = req.pinned
    return ok(save_notebook(profile, nb))


@app.post("/notebooks/{nid}/duplicate")
def duplicate_notebook(nid: str, profile=Depends(current_profile)):
    """A fresh copy of the notebook's question, rules, market and notes, without its experiments."""
    nb = get_notebook(profile, nid)
    copy = {"name": f"{nb.get('name') or 'Notebook'} (copy)"[:80], "question": nb.get("question") or "",
            "notes": nb.get("notes") or "", "strategy": nb.get("strategy"), "instrument": nb.get("instrument"),
            "experiments": [], "summary": research.summary([])}
    return ok(save_notebook(profile, copy))


@app.delete("/notebooks/{nid}")
def delete_notebook(nid: str, profile=Depends(current_profile)):
    db.delete_strategy(profile["id"], check_id(nid))
    return {"deleted": True}


@app.post("/notebooks/{nid}/experiments")
def run_experiment(nid: str, req: ExperimentReq, profile=Depends(current_profile)):
    """Test the notebook's current rules and keep the result as its next experiment."""
    nb = get_notebook(profile, nid)
    strategy = Strategy(**(nb.get("strategy") or {}))
    if not req.bars and not req.instrument:
        req.instrument = (nb.get("instrument") or {}).get("id")
    out = run_test(profile, strategy, req)
    experiments = list(nb.get("experiments") or [])
    version = (experiments[-1]["v"] + 1) if experiments else 1
    rec = research.record(out, strategy, req.label, version, db.now_iso())
    experiments = (experiments + [rec])[-50:]
    nb["experiments"], nb["summary"] = experiments, research.summary(experiments)
    save_notebook(profile, nb)
    return ok({"experiment": rec, "usage": out["usage"], "summary": nb["summary"]})


@app.post("/notebooks/{nid}/experiments/{version}/basket")
def run_basket(nid: str, version: int, profile=Depends(current_profile)):
    """Run one experiment's exact rules and period on ~10 similar instruments in the same market."""
    nb = get_notebook(profile, nid)
    exps = list(nb.get("experiments") or [])
    exp = next((e for e in exps if e["v"] == version), None)
    if exp is None:
        err(404, "not_found", "Experiment not found.")
    strategy = Strategy(**exp["strategy"])
    inst = exp.get("instrument") or {}
    limit = use_backtest(profile)          # the whole check counts as one experiment
    check_features(profile, strategy, inst)
    try:
        out = basket.run(markets, strategy, inst.get("market", "IN"), inst.get("id"), exp.get("days") or 365)
    except research.ResearchError as e:
        err(e.status, e.code, e.message)
    db.add_usage(profile["id"], "backtest")
    exp["basket"] = out
    nb["experiments"] = [exp if e["v"] == version else e for e in exps]
    save_notebook(profile, nb)
    return ok({"basket": out, "usage": {"backtests_used": backtests_used(profile), "backtests_limit": limit}})


@app.post("/notebooks/{nid}/experiments/{version}/walkforward")
def run_walkforward(nid: str, version: int, profile=Depends(current_profile)):
    """Re-tune the indicator lengths on a rolling window of the past and trade them on the next,
    unseen stretch, over the experiment's own period. Counts as one experiment."""
    nb = get_notebook(profile, nid)
    exps = list(nb.get("experiments") or [])
    exp = next((e for e in exps if e["v"] == version), None)
    if exp is None:
        err(404, "not_found", "Experiment not found.")
    inst = exp.get("instrument") or {}
    if not inst.get("id") or inst.get("market") == "CSV":
        err(400, "no_walkforward", "Walk-forward needs market data StratLab can fetch again, so it isn't available for uploaded CSVs.")
    strategy = Strategy(**exp["strategy"])
    limit = use_backtest(profile)
    check_features(profile, strategy, inst)
    data = research.load(markets, strategy, basket._Req(inst["id"], exp.get("days") or 365))
    out = walkforward.run(data["bars"], strategy, data["start"], data["lot"], data["kind"])
    db.add_usage(profile["id"], "backtest")
    exp["walkforward"] = out
    nb["experiments"] = [exp if e["v"] == version else e for e in exps]
    save_notebook(profile, nb)
    return ok({"walkforward": out, "usage": {"backtests_used": backtests_used(profile), "backtests_limit": limit}})


@app.delete("/notebooks/{nid}/experiments/{version}")
def delete_experiment(nid: str, version: int, profile=Depends(current_profile)):
    nb = get_notebook(profile, nid)
    nb["experiments"] = [e for e in nb.get("experiments") or [] if e["v"] != version]
    nb["summary"] = research.summary(nb["experiments"])
    save_notebook(profile, nb)
    return {"deleted": True}


# ---------- live paper trading ----------
@app.post("/live/sessions")
def start_live(req: LiveStartReq, profile=Depends(current_profile)):
    s = req.strategy
    if not s.entry:
        err(400, "no_entry_rules", "Add at least one entry rule before going live.")
    _, inst = get_instrument(req.instrument)
    check_features(profile, s, inst)
    start_trial = False
    if profile["_plan"] == "free":
        t = trial_state(profile)
        if t["started"] and not t["active"]:
            upgrade("Your 24-hour live trial has ended. Upgrade to Basic or Pro to keep paper trading.", "trial_ended")
        start_trial = not t["started"]
        if start_trial:
            db.update_profile(profile["id"], live_trial_started_at=db.now_iso())
    try:
        sess = manager.start(profile, profile["_plan"], s, inst)
    except Exception as e:
        if start_trial:  # the session never ran, so don't use up the free trial
            db.update_profile(profile["id"], live_trial_started_at=None)
        if isinstance(e, LimitError):
            upgrade(str(e), "live_limit")
        if isinstance(e, ValueError):
            err(400, "cannot_start", str(e))
        raise
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
    sid = check_id(sid)
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
    snap["orders"] = orders_from(snap.get("events") or [])
    return ok(snap)


def orders_from(events: list[dict]) -> list[dict]:
    """The session's orders, newest first, in the shape the app shows."""
    return [{"side": e["side"], "qty": e["qty"], "price": e["px"], "reason": e.get("why"), "pnl": e.get("pnl"),
             "ts": e["t"]} for e in reversed(events[-200:])]


@app.post("/live/sessions/{sid}/stop")
def stop_live(sid: str, profile=Depends(current_profile)):
    sid = check_id(sid)
    s = manager.sessions.get(sid)
    if s and s.user_id == profile["id"]:
        manager.stop(sid, "Stopped by you.")
    elif db.get_session_row(profile["id"], sid):
        db.update_session(sid, status="stopped", stopped_at=db.now_iso(), stop_reason="Stopped by you.")
    else:
        err(404, "not_found", "Session not found.")
    return {"stopped": True}


@app.delete("/live/sessions/{sid}")
def delete_live(sid: str, profile=Depends(current_profile)):
    """Delete a stopped session and its orders. A running one has to be stopped first."""
    sid = check_id(sid)
    s = manager.sessions.get(sid)
    row = db.get_session_row(profile["id"], sid)
    if not row:
        err(404, "not_found", "Session not found.")
    if (s and s.user_id == profile["id"]) or row["status"] == "running":
        err(409, "still_running", "Stop this session before deleting it.")
    db.delete_session(profile["id"], sid)
    return {"deleted": True}


@app.delete("/live/sessions")
def clear_stopped_live(profile=Depends(current_profile)):
    """Delete every stopped session. Running ones are left alone."""
    return {"deleted": db.delete_stopped_sessions(profile["id"])}


# ---------- billing ----------
@app.post("/billing/subscribe")
def subscribe(req: SubscribeReq, profile=Depends(current_profile)):
    if profile["_plan"] == req.plan:
        err(400, "already_on_plan", f"You're already on {PLANS[req.plan]['name']}.")
    try:
        return billing.create_subscription(profile, req.plan)
    except ValueError as e:
        err(503, "billing_offline", str(e))


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
    except ValueError:  # malformed JSON
        raise HTTPException(400, "bad payload")
    return {"ok": True}


# ---------- admin: daily Kite login ----------
def _admin(key: str):
    if not settings.ADMIN_KEY or not secrets.compare_digest(key.encode(), settings.ADMIN_KEY.encode()):
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
    return HTMLResponse(f"<p>{after_login()}</p>")


@app.post("/admin/kite/auto-login")
def kite_auto_login(key: str = ""):
    """Run the automatic login now, e.g. to test the credentials after setting them."""
    _admin(key)
    try:
        auto_login.run_once()
    except AutoLoginError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"Kite login failed: {e}")
    return auto_login.last


@app.get("/admin/status")
def admin_status(key: str = ""):
    _admin(key)
    return server_status()


def server_status() -> dict:
    return {"kite_ready": kite.ready(), "kite_token_day": kite.token_day, "feed_started": hub.started,
            "feed_connected": hub.connected, "live_sessions": len(manager.sessions),
            "subscribed_tokens": len(hub.listeners), "auto_login": auto_login.last,
            "auto_login_configured": auto_login_configured(),
            "billing_enabled": billing.enabled(), "ai": ai_health(),
            "research": {"finnhub": bool(settings.FINNHUB_API_KEY)}}


# ---------- admin page (signed in with an ADMIN_EMAILS account) ----------
@app.get("/admin/overview")
def admin_overview(_=Depends(admin.admin_profile)):
    return {"server": server_status(), "stats": admin.stats(month_start_iso())}


@app.get("/admin/users")
def admin_users(q: str = "", _=Depends(admin.admin_profile)):
    return admin.users(q, month_start_iso())


@app.post("/admin/users/{user_id}/plan")
def admin_set_plan(user_id: str, req: AdminPlanReq, who=Depends(admin.admin_profile)):
    row = admin.set_plan(user_id, req.plan, req.days)
    log.info("admin %s set %s to %s (%s days)", who.get("email"), row.get("email"), req.plan, req.days)
    return {"ok": True}


@app.get("/admin/sessions")
def admin_sessions(_=Depends(admin.admin_profile)):
    emails = {}
    out = []
    for s in list(manager.sessions.values()):
        if s.user_id not in emails:
            emails[s.user_id] = db.get_profile(s.user_id).get("email")
        account = s.snapshot().get("account") or {}
        out.append({"id": s.id, "name": s.name, "email": emails[s.user_id], "symbol": s.inst.get("symbol"),
                    "market": s.market, "started_at": s.started_at, "capital": account.get("capital"),
                    "equity": account.get("equity"), "trades": account.get("trades")})
    return out


@app.post("/admin/sessions/{sid}/stop")
def admin_stop_session(sid: str, _=Depends(admin.admin_profile)):
    if sid not in manager.sessions:
        err(404, "not_found", "That session isn't running.")
    manager.stop(sid, "Stopped by the site owner.")
    return {"ok": True}


@app.post("/admin/ai/test")
def admin_ai_test(_=Depends(admin.admin_profile)):
    return {"providers": ai_test_all(gemini=_gemini, anthropic=_anthropic)}


@app.post("/admin/kite/login-url")
def admin_kite_login_url(_=Depends(admin.admin_profile)):
    return {"url": kite.login_url()}


@app.post("/admin/kite/auto-login-now")
def admin_kite_auto_login(_=Depends(admin.admin_profile)):
    try:
        auto_login.run_once()
    except AutoLoginError as e:
        err(400, "auto_login_failed", str(e))
    except Exception as e:
        err(502, "auto_login_failed", f"Kite login failed: {e}")
    return auto_login.last
