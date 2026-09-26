"""StratLab API."""
import json
import logging
from html import escape as html_escape
import math
import re
import secrets
import threading
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from kiteconnect import exceptions as kite_exc
from razorpay.errors import SignatureVerificationError

from . import admin, basket, billing, db, importer, universes
from .ai_providers import health as ai_health, test_all as ai_test_all
from . import ai_writer
from .ai_writer import AIBusy, AIError, _anthropic, _gemini, ask_json, write_strategy
from . import alerts
from .auth import current_profile
from .config import settings
from .errors import report
from .guard import Guard
from . import research
from .engine import walkforward
from .data import DataError, Registry
from .data import calendar as trading_calendar
from .intel import routes as research_routes
from .intel.company import Research
from .kite_auto import AutoLogin, AutoLoginError, configured as auto_login_configured, restart_process
from .kite_service import IST, KiteNotReady, KiteService, TickHub
from .live import LimitError, LiveManager, describe, needs_pro
from .options import importer as opt_importer
from .options.data import FREEZE, OptionsData
from .options.engine import fill_price
from .options.session import stopped_snapshot as options_stopped
from .options.recorder import Recorder, parse_targets
from . import ask, daily_report, ideas, library, public, push, risk
from .models import (ShareReq, GroupLiveReq, OptionImportReq, OptionStartReq)
from .models import (AdminPlanReq, AIReq, ModerateReq, ReportReq, IdeasReq, LibraryReq, PrefsReq, PushReq, ImportReq, AlertsReq, ExperimentReq, LiveStartReq, NotebookReq, SaveStrategyReq,
                     Strategy, SubscribeReq, VerifyReq)
from .plans import FEATURE_PLAN, PLANS, allows, group_size, has_pro_features, plan_info, public_plans, trial_state

kite = KiteService()
hub = TickHub(kite)
markets = Registry(kite)
options_data = OptionsData(kite)
manager = LiveManager(kite, hub, markets, options_data)
recorder = Recorder(options_data, db.add_option_snapshot, parse_targets(settings.OPTION_SNAPSHOTS), settings.OPTION_SNAPSHOT_MINUTES)
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
kite.on_invalid = lambda msg: auto_login._alert("StratLab: " + msg)


@asynccontextmanager
async def lifespan(app: FastAPI):
    auto_login.load_last()
    _load_errors()
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
    recorder.start()
    threading.Thread(target=trading_calendar.warm, daemon=True).start()   # ~2 s, kept off the first request
    yield


log = logging.getLogger("stratlab")
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.SENTRY_ENV, traces_sample_rate=0, send_default_pii=False)
    except Exception as e:
        print("Sentry not started:", e)
app = FastAPI(title="StratLab API", lifespan=lifespan)
research_routes.setup(research_hub, _gemini, _anthropic)
app.include_router(research_routes.router)


RECENT_ERRORS: list[dict] = []   # the last crashes, shown on the admin page


@app.middleware("http")
async def unexpected_errors(request: Request, call_next):
    """Turn crashes into a normal JSON error. Registered before CORS, so the browser can still read it."""
    try:
        return await call_next(request)
    except Exception as e:
        traceback.print_exc()
        ref = secrets.token_hex(3).upper()
        tb = traceback.extract_tb(e.__traceback__)
        own = [f for f in tb if "site-packages" not in f.filename and f.name != "unexpected_errors"] or tb   # the deepest frame of our own code
        where = f"{own[-1].filename.rsplit('/', 1)[-1]}:{own[-1].lineno} in {own[-1].name}" if own else ""
        RECENT_ERRORS.append({"ref": ref, "at": datetime.now(IST).isoformat(), "method": request.method,
                              "path": request.url.path, "error": f"{type(e).__name__}: {str(e)[:300]}", "where": where})
        del RECENT_ERRORS[:-25]
        _save_errors()
        report(e, ref=ref, path=f"{request.method} {request.url.path}")
        return JSONResponse(status_code=500, content={"detail": {"code": "server_error",
                            "message": f"Something went wrong on our side ({request.method} {request.url.path}, ref {ref}). "
                                       "Try again in a moment; the admin page lists what failed."}})


def _save_errors():
    """Keep the error list in the database too, so a restart doesn't wipe it."""
    snapshot = json.dumps(RECENT_ERRORS[-25:])

    def work():
        try:
            db.set_setting("recent_errors", snapshot)
        except Exception as x:
            print("could not save errors:", x)
    threading.Thread(target=work, daemon=True).start()


def _load_errors():
    try:
        saved = json.loads(db.get_setting("recent_errors") or "[]")
        if isinstance(saved, list):
            RECENT_ERRORS[:0] = [e for e in saved if isinstance(e, dict)][-25:]
    except Exception as x:
        print("could not load errors:", x)


app.add_middleware(Guard)   # size cap, rate limit, security headers; inside CORS so its replies stay readable
app.add_middleware(CORSMiddleware, allow_origins=settings.FRONTEND_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


# ---------- helpers ----------
def err(status: int, code: str, message: str):
    raise HTTPException(status, {"code": code, "message": message})


def upgrade(message: str, code: str = "upgrade_required"):
    err(402, code, message)


def need(profile, feature: str, what: str):
    """Stop with an upgrade message when the plan doesn't include a feature."""
    if not allows(profile["_plan"], feature):
        upgrade(f"{what} {'is' if not what.endswith('s') else 'are'} on the {PLANS[FEATURE_PLAN[feature]]['name']} plan.")


def check_group_size(profile, n: int):
    cap = group_size(profile["_plan"])
    if n > cap:
        bigger = next((PLANS[p]["name"] for p in ("basic", "pro") if PLANS[p]["group_size"] >= n), None)
        upgrade(f"Your plan tests groups of up to {cap} instruments; this one has {n}."
                + (f" {bigger} goes up to {PLANS['pro' if bigger == 'Pro' else 'basic']['group_size']}." if bigger else ""))


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
    """Public: only whether things are up. Provider details are on the admin page."""
    return {"ok": True, "data_online": kite.ready(), "feed_connected": hub.connected,
            "ai_configured": any(p["in_use"] for p in ai_health())}


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
        "alerts": {"channels": alerts.ready_channels(), "enabled": bool(profile.get("alerts_enabled")), "telegram_chat_id": profile.get("telegram_chat_id"),
                   "email": profile.get("alert_email"), "daily_report": daily_report.wants_report(db, profile["id"])},
        "prefs": {"level": prefs_of(profile["id"]).get("level")},
        "data_online": kite.ready(),
        "data_note": data_note(),
        "billing_enabled": billing.enabled(), "yearly_enabled": billing.yearly_enabled(), "plans": public_plans(),
        "is_admin": admin.is_admin(profile),
    })


def data_note() -> dict | None:
    """While Indian data is offline: whether India is closed today anyway, and when data comes back by itself."""
    if kite.ready():
        return None
    now = datetime.now(IST)
    today = now.date()
    closed = "weekend" if today.weekday() >= 5 else "holiday" if trading_calendar.is_holiday("IN", today) else None
    back = auto_login.next_login(now)
    return {"closed": closed, "back_at": back.isoformat() if back else None}


def prefs_of(uid: str) -> dict:
    try:
        p = json.loads(db.get_setting(daily_report.PREFS + uid) or "{}")
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


@app.put("/me/prefs")
def set_prefs(req: PrefsReq, profile=Depends(current_profile)):
    """Experience level: only changes defaults (what's expanded, which tools are suggested), never what's allowed."""
    prefs = {**prefs_of(profile["id"]), "level": req.level}
    db.set_setting(daily_report.PREFS + profile["id"], json.dumps(prefs))
    return {"prefs": {"level": req.level}}


@app.get("/push/key")
def push_key(profile=Depends(current_profile)):
    return {"enabled": push.enabled(), "key": push.public_key(), "devices": len(push.devices(profile["id"]))}


@app.post("/push/subscribe")
def push_subscribe(req: PushReq, profile=Depends(current_profile)):
    """Remember this device for notifications (trade alerts and the daily report, as the plan allows)."""
    if not push.enabled():
        err(503, "push_off", "Phone notifications aren't set up on the server yet.")
    if not push.valid_endpoint(req.subscription.endpoint):
        err(400, "bad_push_endpoint", "This browser's notification service isn't supported. Try Chrome, Safari, Firefox or Edge.")
    push.add(profile["id"], req.subscription.model_dump())
    return {"devices": len(push.devices(profile["id"]))}


@app.post("/push/test")
def push_test(profile=Depends(current_profile)):
    if not push.enabled():
        err(503, "push_off", "Phone notifications aren't set up on the server yet.")
    throttle(profile, "push_test", 5, 3600, "You've sent 5 test notifications this hour. Try again later.")
    sent = push.send(profile["id"], "StratLab", "Notifications work. Paper-trade alerts and the daily report will arrive like this.", url="/account", tag="test")
    return {"sent": sent}


@app.post("/push/unsubscribe")
def push_unsubscribe(req: PushReq, profile=Depends(current_profile)):
    push.remove(profile["id"], req.subscription.endpoint)
    return {"devices": len(push.devices(profile["id"]))}


@app.put("/me/alerts")
def set_alerts(req: AlertsReq, profile=Depends(current_profile)):
    need(profile, "daily_report", "Alerts and the daily report")
    if req.alerts_enabled:
        need(profile, "alerts", "Trade alerts")
    db.update_profile(profile["id"], alerts_enabled=req.alerts_enabled,
                      telegram_chat_id=(req.telegram_chat_id or None), alert_email=(req.alert_email or None))
    if req.daily_report is not None:
        prefs = json.loads(db.get_setting(daily_report.PREFS + profile["id"]) or "{}")
        db.set_setting(daily_report.PREFS + profile["id"], json.dumps({**prefs, "daily_report": req.daily_report}))
    return {"saved": True}


@app.post("/me/alerts/test")
def test_alert(profile=Depends(current_profile)):
    need(profile, "daily_report", "Alerts and the daily report")
    throttle(profile, "alert_test", 5, 3600, "You've sent 5 test alerts this hour. Try again later.")
    sent, failed = alerts.test(profile)
    if not sent and not failed:
        err(400, "no_channels", "Turn on phone notifications on this device, or add a Telegram chat ID"
            + (" or an email" if alerts.email_ready() else "") + ", first.")
    if not sent:
        err(502, "alert_failed", "The test couldn't be sent: " + "; ".join(f"{k}: {v}" for k, v in failed.items()))
    return {"sent": sent, "failed": failed}


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


@app.post("/export/strategy")
def export_strategy(req: SaveStrategyReq, profile=Depends(current_profile)):
    need(profile, "export", "Strategy export")
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


@app.post("/search/ideas")
def search_ideas(req: IdeasReq, profile=Depends(current_profile)):
    """Testable strategy ideas for anything typed into search. Shared cache; built-in ideas if the AI is down."""
    q = req.q.strip()
    try:
        out = research_routes.ai_call(profile, "ideas", ideas.key(q), 7 * 86400, False, lambda: ideas.build(ask_json, q))
        return {"ideas": out["ideas"], "fallback": False}
    except HTTPException as e:
        if e.status_code in (422, 503):
            return {"ideas": ideas.fallback(q), "fallback": True}
        raise


@app.post("/ask")
def ask_route(req: IdeasReq, profile=Depends(current_profile)):
    """One line from the search box, turned into one action the app then carries out."""
    q = req.q.strip()
    if ask.looks_like_code(q):
        return {"action": "import", "text": q, "title": "Import this strategy", "fallback": False}
    try:
        out = research_routes.ai_call(profile, "ask", ask.key(q), 7 * 86400, False, lambda: ask.build(ask_json, q))
        return {**out, "fallback": False}
    except HTTPException as e:
        if e.status_code in (422, 429, 503):
            return {**ask.guess(q), "fallback": True}
        raise


@app.post("/import/strategy")
def import_strategy(req: ImportReq, profile=Depends(current_profile)):
    """Turn an existing strategy (StratLab export, Pine Script, Python, MQL, AFL or plain words) into rules."""
    fmt = importer.detect(req.text, req.filename)
    base = {"source": fmt, "source_name": importer.FORMATS[fmt]}
    if opt_importer.from_json(req.text) or opt_importer.is_options(req.text, fmt):
        return {**base, **import_options(req.text, profile)}
    if fmt in ("stratlab", "json"):
        try:
            return {**base, **importer.from_json(req.text), "used_ai": False}
        except ValueError as e:
            if fmt == "stratlab":
                err(400, "bad_import", str(e))
            # a config from another system: the AI reads it as a strategy spec
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


_recent: dict[tuple[str, str], list[float]] = {}
_recent_lock = threading.Lock()


def throttle(profile, what: str, times: int, per_seconds: float, message: str):
    """Allow an action a few times per window per user: test sends and other things that reach outside services."""
    now = datetime.now().timestamp()
    key = (profile["id"], what)
    with _recent_lock:
        hits = [t for t in _recent.get(key, []) if now - t < per_seconds]
        if len(hits) >= times:
            err(429, "slow_down", message)
        _recent[key] = hits + [now]
        if len(_recent) > 20000:
            _recent.clear()


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


def run_group_test(profile, strategy: Strategy, group: dict, req, version: int) -> tuple[dict, dict]:
    """A portfolio experiment over the notebook's group of instruments."""
    if not strategy.entry and not strategy.shortEntry:
        err(400, "no_entry_rules", "Add at least one entry rule first.")
    market = group.get("market") or "IN"
    prov = markets.provider(market)
    if prov is None or not prov.ready():
        err(503, "data_offline", "Market data for this market is offline right now. Try again soon.")
    check_group_size(profile, len(group.get("members") or []))
    limit = use_backtest(profile)
    ids, missing = universes.resolve(markets, market, group.get("members") or [])
    datasets, problems = universes.load_all(markets, strategy, ids, req.days)
    problems = [f"{m}: not listed any more" for m in missing] + problems
    if len(datasets) < 2:
        err(400, "group_empty", "Fewer than two of this group's instruments had data for this period. "
            + (" ".join(problems[:3]) if problems else ""))
    for d in datasets:
        check_features(profile, strategy, d["inst"])
    max_days = min(d["max_days"] for d in datasets)
    result = research.run_group(datasets, strategy, group, min(req.days, max_days), max_days)
    db.add_usage(profile["id"], "backtest")
    rec = research.record_group(result, strategy, req.label, version, db.now_iso(), group, datasets, problems)
    return rec, {"backtests_used": backtests_used(profile), "backtests_limit": limit}


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
    body = {k: nb.get(k) for k in ("kind", "question", "notes", "strategy", "instrument", "experiments", "summary", "pinned", "group")}
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
        row = {**{k: r.get(k) for k in ("id", "name", "question", "instrument", "summary", "updated_at", "tf")},
               "pinned": r.get("pinned") in (True, "true")}
        g = r.get("group")
        if isinstance(g, dict) and g.get("members"):
            row["instrument"] = {"id": f"GROUP:{g.get('id')}", "symbol": f"{g.get('name')} ({len(g['members'])})", "market": g.get("market"), "type": "GROUP"}
        out.append(row)
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
    if req.instrument is not None or req.clearGroup:
        nb.pop("group", None)                 # picking one instrument replaces a group
    if req.group is not None:
        g = req.group
        nb["group"] = {"id": g.id, "name": g.name, "market": g.market.upper(), "maxOpen": min(g.maxOpen, len(g.members)),
                       "members": [m.model_dump(exclude_none=True) for m in g.members]}
    return ok(save_notebook(profile, nb))


@app.get("/groups")
def list_groups(market: str = "IN", profile=Depends(current_profile)):
    """Ready-made groups of instruments for a market."""
    return universes.presets(market.upper())


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
    row = db.get_strategy(profile["id"], check_id(nid))
    for e in (notebook_from_row(row).get("experiments") or []) if row else []:
        if e.get("public"):
            public.unpublish(e["public"])   # its public links go with it
    db.delete_strategy(profile["id"], check_id(nid))
    return {"deleted": True}


@app.post("/notebooks/{nid}/experiments")
def run_experiment(nid: str, req: ExperimentReq, profile=Depends(current_profile)):
    """Test the notebook's current rules and keep the result as its next experiment."""
    nb = get_notebook(profile, nid)
    strategy = Strategy(**(nb.get("strategy") or {}))
    experiments = list(nb.get("experiments") or [])
    version = (experiments[-1]["v"] + 1) if experiments else 1
    group = nb.get("group")
    if group and not req.bars:
        rec, usage = run_group_test(profile, strategy, group, req, version)
        out = {"usage": usage}
    else:
        if not req.bars and not req.instrument:
            req.instrument = (nb.get("instrument") or {}).get("id")
        out = run_test(profile, strategy, req)
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
    if (exp.get("instrument") or {}).get("type") == "GROUP":
        err(400, "group_experiment", "This check runs on one instrument. Open the notebook on a single stock to use it.")
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
    if (exp.get("instrument") or {}).get("type") == "GROUP":
        err(400, "group_experiment", "This check runs on one instrument. Open the notebook on a single stock to use it.")
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


@app.post("/notebooks/{nid}/experiments/{version}/share")
def share_experiment(nid: str, version: int, req: ShareReq, profile=Depends(current_profile)):
    """Turn on (or refresh) a public link to this verdict."""
    nb = get_notebook(profile, nid)
    exps = list(nb.get("experiments") or [])
    exp = next((e for e in exps if e["v"] == version), None)
    if exp is None:
        err(404, "not_found", "Experiment not found.")
    token = public.publish(nb, exp, req.image)
    exp["public"] = token
    nb["experiments"] = [exp if e["v"] == version else e for e in exps]
    save_notebook(profile, nb)
    return {"token": token, "url": public.url(token)}


# ---------- the public strategy library ----------
@app.post("/notebooks/{nid}/experiments/{version}/library")
def publish_to_library(nid: str, version: int, req: LibraryReq, profile=Depends(current_profile)):
    """Publish this experiment's rules with its verdict. Publishing again updates the same entry."""
    nb = get_notebook(profile, nid)
    exps = list(nb.get("experiments") or [])
    exp = next((e for e in exps if e["v"] == version), None)
    if exp is None:
        err(404, "not_found", "Experiment not found.")
    if (exp.get("instrument") or {}).get("market") == "CSV":
        err(400, "library_upload", "Strategies tested on uploaded data can't go in the library: nobody else has that data to re-test on.")
    old = library.load(exp.get("library") or "")
    e = library.entry(nb, exp, profile["id"], req.author, req.description,
                      entry_id=old["id"] if old and old.get("owner") == profile["id"] else None)
    if old and old.get("owner") == profile["id"]:
        e["copies"], e["published_at"] = old.get("copies", 0), old.get("published_at", e["published_at"])
        e = library.carry_moderation(old, e)
    library.save(e)
    exp["library"] = e["id"]
    nb["experiments"] = [exp if x["v"] == version else x for x in exps]
    save_notebook(profile, nb)
    return library.public(e, profile["id"])


@app.get("/library")
def browse_library(market: str = "", verdict: str = "", q: str = "", sort: str = "best", profile=Depends(current_profile)):
    shown = [e for e in library.all_entries() if library.visible(e, profile["id"])]
    rows = library.search(shown, market.upper()[:10], verdict[:12], q[:80], sort)
    return {"entries": [library.public(e, profile["id"]) for e in rows[:200]], "total": len(rows),
            "reasons": library.REASONS}


def visible_entry(eid: str, profile) -> dict:
    e = library.load(eid)
    if not e or not (library.visible(e, profile["id"]) or admin.is_admin(profile)):
        err(404, "not_found", "That strategy isn't in the library any more.")
    return e


@app.get("/library/{eid}")
def library_entry(eid: str, profile=Depends(current_profile)):
    return library.public(visible_entry(eid, profile), profile["id"])


@app.post("/library/{eid}/report")
def report_library_entry(eid: str, req: ReportReq, profile=Depends(current_profile)):
    """Flag an entry for the site owner. Several reports hide it until it's reviewed."""
    e = visible_entry(eid, profile)
    if e.get("owner") == profile["id"]:
        err(400, "own_entry", "This is your own strategy. Take it down instead if it shouldn't be here.")
    throttle(profile, "library_report", 20, 86400, "You've sent a lot of reports today. Thanks; try again tomorrow.")
    e = library.report(e, profile["id"], req.reason)
    library.save(e)
    return {"reported": True, "hidden": bool(e.get("hidden"))}


@app.post("/library/{eid}/copy")
def copy_from_library(eid: str, profile=Depends(current_profile)):
    """Put the rules in a new notebook of your own, ready to re-test."""
    e = visible_entry(eid, profile)
    if not e.get("strategy"):
        err(404, "not_found", "That strategy isn't in the library any more.")
    inst = (e.get("instrument") or {}).get("id")
    nb = {"name": e["name"][:80], "question": e.get("question") or e.get("description") or "",
          "notes": f"Copied from the strategy library: \"{e['name']}\" by {e.get('author')}. Its verdict there: {(e.get('verdict') or {}).get('headline', '')}",
          "strategy": {**e["strategy"], "name": e["name"][:80]}, "instrument": instrument_summary(inst) if inst else None,
          "experiments": [], "summary": research.summary([])}
    if e.get("group"):
        nb["group"] = e["group"]
    out = save_notebook(profile, nb)
    if e.get("owner") != profile["id"]:
        e["copies"] = (e.get("copies") or 0) + 1
        library.save(e)
    return out


@app.delete("/library/{eid}")
def unpublish_from_library(eid: str, profile=Depends(current_profile)):
    e = library.load(eid)
    if not e:
        return {"deleted": True}
    if e.get("owner") != profile["id"] and not admin.is_admin(profile):
        err(403, "not_yours", "Only the author can take this strategy down.")
    library.remove(eid)
    return {"deleted": True}


@app.delete("/notebooks/{nid}/experiments/{version}/share")
def unshare_experiment(nid: str, version: int, profile=Depends(current_profile)):
    nb = get_notebook(profile, nid)
    exps = list(nb.get("experiments") or [])
    exp = next((e for e in exps if e["v"] == version), None)
    if exp is None:
        err(404, "not_found", "Experiment not found.")
    public.unpublish(exp.pop("public", None))
    nb["experiments"] = [exp if e["v"] == version else e for e in exps]
    save_notebook(profile, nb)
    return {"shared": False}


@app.get("/public/v/{token}")
def public_verdict(token: str):
    snap = public.load(token)
    if not snap:
        err(404, "not_found", "This link was turned off or never existed.")
    return snap


@app.get("/v/{token}.png")
def public_verdict_image(token: str):
    png = public.image(token)
    if not png:
        err(404, "not_found", "No image for this link.")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/v/{token}")
def public_verdict_page(token: str):
    snap = public.load(token)
    if not snap:
        return RedirectResponse(settings.PUBLIC_SITE_URL + "/")
    return HTMLResponse(public.preview_html(token, snap, public.image(token) is not None))


@app.delete("/notebooks/{nid}/experiments/{version}")
def delete_experiment(nid: str, version: int, profile=Depends(current_profile)):
    nb = get_notebook(profile, nid)
    for e in nb.get("experiments") or []:
        if e["v"] == version and e.get("public"):
            public.unpublish(e["public"])
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
    return ok(start_session(profile, s, inst).snapshot())


def start_session(profile, s, inst):
    """Start paper trading, using up the free plan's one-off live trial on the first start."""
    start_trial = False
    if profile["_plan"] == "free":
        t = trial_state(profile)
        if t["started"] and not t["active"]:
            upgrade("Your free 5-market-day paper trading trial has ended. Upgrade to Basic or Pro to keep paper trading.", "trial_ended")
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
    return sess


@app.post("/live/groups")
def start_live_group(req: GroupLiveReq, profile=Depends(current_profile)):
    """Paper trade a strategy on a whole group of instruments with one pot of capital."""
    s, g = req.strategy, req.group
    if not s.entry and not s.shortEntry:
        err(400, "no_entry_rules", "Add at least one entry rule before going live.")
    if s.tf == "1d":
        err(400, "group_daily", "Paper trading a group needs intraday candles (5-minute, 15-minute or 1-hour). "
            "Daily groups can be tested with experiments.")
    prov = markets.provider(g.market)
    if prov is None or not prov.ready():
        err(503, "data_offline", "Market data for this market is offline right now. Try again soon.")
    ids, missing = universes.resolve(markets, g.market, [m.model_dump() for m in g.members])
    insts = [markets.resolve(i)[1] for i in ids]
    insts = [i for i in insts if i]
    need(profile, "group_live", "Paper trading a group")
    if req.fast.ticks or req.fast.maxSpreadPct:
        need(profile, "fast_entries", "Faster entries and the spread limit")
    check_group_size(profile, len(insts))
    if len(insts) < 2:
        err(400, "group_empty", "Fewer than two of this group's instruments could be found.")
    for i in insts:
        check_features(profile, s, i)
    cur = insts[0].get("currency") or ("INR" if g.market == "IN" else "")
    inst = {"id": f"GROUP:{g.id}", "type": "GROUP", "symbol": f"{g.name} ({len(insts)})", "market": g.market,
            "currency": cur, "tz": insts[0].get("tz"), "maxOpen": min(g.maxOpen, len(insts)),
            "members": [i["id"] for i in insts], "names": {i["id"]: i.get("symbol") for i in insts}, "missing": missing,
            "fast": req.fast.model_dump() if g.market == "IN" else {**req.fast.model_dump(), "ticks": False, "maxSpreadPct": 0}}
    return ok(start_session(profile, s, inst).snapshot())


@app.get("/live/overview")
def live_overview(profile=Depends(current_profile)):
    """Every running paper session together: open value, today, total P&L, worst day, deepest fall."""
    snaps = []
    for s in manager.user_running(profile["id"]):
        try:
            snaps.append(s.snapshot())
        except Exception as e:
            print("overview: snapshot failed:", s.id, e)
    return risk.summary(snaps, datetime.now(IST).date().isoformat())


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
        if (row.get("instrument") or {}).get("type") == "GROUP":
            from .group_live import stopped_snapshot as group_stopped
            snap = group_stopped(row)
            snap["orders"] = orders_from(snap["events"])
            return ok(snap)
        if (row.get("instrument") or {}).get("type") == "OPTIONS":
            snap = options_stopped(row)
            snap["orders"] = orders_from(snap["events"])
            return ok(snap)
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


# ---------- options (live paper trading only) ----------
def options_ready():
    if not options_data.ready():
        err(503, "data_offline", "Option quotes come from the broker's live feed, which is offline until today's Kite login. "
            "Try again after the market data comes back.")


@app.get("/options/underlyings")
def options_underlyings(profile=Depends(current_profile)):
    options_ready()
    return options_data.underlyings()


@app.get("/options/chain")
def options_chain(exchange: str = "NFO", underlying: str = "NIFTY", expiry: str = "current", profile=Depends(current_profile)):
    options_ready()
    if exchange not in ("NFO", "BFO", "MCX") or not re.fullmatch(r"[A-Z0-9&-]{1,30}", underlying) or \
            not re.fullmatch(r"current|next|month|\d{4}-\d{2}-\d{2}", expiry):
        err(400, "bad_request", "Pick an exchange, an underlying and an expiry.")
    return options_data.chain(exchange, underlying, expiry)


@app.post("/options/preview")
def options_preview(req: OptionStartReq, profile=Depends(current_profile)):
    """The structure at today's at-the-money strike, priced on live bid and ask, with margin and costs."""
    options_ready()
    s = req.strategy
    c = options_data.contracts(s.exchange, s.underlying, s.expiry)
    if not c:
        err(404, "no_contracts", f"No {s.underlying} options are listed on {s.exchange} for that expiry.")
    sk = options_data.spot_key(s.exchange, s.underlying, c.expiry)
    spot = (options_data.quotes([sk]).get(sk) or {}).get("ltp") if sk else None
    if not spot:
        err(503, "no_spot", f"Couldn't get the {s.underlying} price just now.")
    atm = c.atm(spot)
    legs = []
    for lg in s.legs:
        k = c.strike_for(atm, lg.opt, lg.offset, s.offsetUnit)
        legs.append({"side": lg.side, "opt": lg.opt, "lots": lg.lots, "strike": k, "key": c.key(lg.opt, k) if k is not None else None})
    q = options_data.quotes([l["key"] for l in legs if l["key"]])
    for l in legs:
        l["quote"] = q.get(l["key"]) if l["key"] else None
        l["fill"] = fill_price(l["quote"], l["side"], s.costs.slippageTicks)
        l["sym"] = l["key"].split(":", 1)[1] if l["key"] else None
    freeze = s.costs.freeze or FREEZE.get(s.underlying, 0)
    units = s.sizing.lots
    margin_one = margin_all = None
    if all(l["key"] for l in legs):
        basket = [{"key": l["key"], "side": l["side"], "qty": l["lots"] * c.lot} for l in legs]
        margin_one = options_data.margin(basket)
        if s.sizing.mode == "margin" and margin_one:
            units = max(0, int(s.sizing.capital * s.sizing.safety // margin_one))
        if margin_one and units:
            margin_all = options_data.margin([{**b, "qty": b["qty"] * units} for b in basket])
    return {"spot": spot, "atm": atm, "step": c.step(spot), "expiry": c.expiry, "lot": c.lot, "freeze": freeze,
            "units": units, "margin_one": margin_one, "margin": margin_all, "legs": legs,
            "strikes": c.strikes, "spot_ts": (options_data.quotes([sk]).get(sk) or {}).get("ts")}


@app.post("/options/sessions")
def start_options(req: OptionStartReq, profile=Depends(current_profile)):
    need(profile, "options", "Options paper trading")
    s = req.strategy
    if s.signal:
        need(profile, "options_signal", "Options entered on a notebook's signal")
    options_ready()
    if not options_data.contracts(s.exchange, s.underlying, s.expiry):
        err(404, "no_contracts", f"No {s.underlying} options are listed on {s.exchange} for that expiry.")
    inst = {"id": f"OPT:{s.exchange}:{s.underlying}", "type": "OPTIONS", "market": "IN", "currency": "INR",
            "tz": "Asia/Kolkata", "symbol": f"{s.underlying} options", "exchange": s.exchange, "underlying": s.underlying}
    return ok(start_session(profile, s, inst).snapshot())


def import_options(text: str, profile) -> dict:
    exact = opt_importer.from_json(text)
    if exact:
        return {"kind": "options", "strategy": exact.model_dump(), "notes": [], "used_ai": False}
    used, limit = ai_allowance(profile)
    try:
        data = ai_writer.ask_json(opt_importer.SYSTEM, text[:30000])
        strategy, notes = opt_importer.parse_ai(data if isinstance(data, dict) else {})
    except AIError as e:
        err(503 if isinstance(e, AIBusy) else 422, "ai_busy" if isinstance(e, AIBusy) else "ai_failed",
            "The AI translator couldn't run just now, so this options strategy couldn't be imported. Try again in a minute.")
    except ValueError as e:
        err(422, "nothing_imported", str(e))
    db.add_usage(profile["id"], "ai")
    return {"kind": "options", "strategy": strategy.model_dump(), "notes": notes, "used_ai": True,
            "usage": {"ai_used": used + 1, "ai_limit": limit}}


@app.post("/options/import")
def options_import(req: OptionImportReq, profile=Depends(current_profile)):
    fmt = importer.detect(req.text, "")
    return {"source": fmt, "source_name": importer.FORMATS[fmt], **import_options(req.text, profile)}


# ---------- billing ----------
@app.post("/billing/subscribe")
def subscribe(req: SubscribeReq, profile=Depends(current_profile)):
    if profile["_plan"] == req.plan:
        err(400, "already_on_plan", f"You're already on {PLANS[req.plan]['name']}.")
    try:
        return billing.create_subscription(profile, req.plan, req.period)
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
# Kite sends the admin back here after logging in. It's protected by the one-time state from login_url(),
# which only an admin can start (the Admin page's "Log in to Kite" button).
@app.get("/admin/kite/callback", response_class=HTMLResponse)
def kite_callback(request_token: str = "", status: str = "", state: str = ""):
    if status != "success" or not request_token:
        return HTMLResponse("<p>Kite login was cancelled or failed.</p>", status_code=400)
    try:
        kite.complete_login(request_token, state)
    except PermissionError as e:
        return HTMLResponse(f"<p>{html_escape(str(e))}</p>", status_code=403)
    return HTMLResponse(f"<p>{html_escape(after_login())}</p><p><a href=\"{html_escape(settings.PUBLIC_SITE_URL)}/admin\">Back to the admin page</a></p>")


def server_status() -> dict:
    return {"kite_ready": kite.ready(), "kite_token_day": kite.token_day, "kite_invalid": kite.invalid_reason, "feed_started": hub.started,
            "feed_connected": hub.connected, "live_sessions": len(manager.sessions),
            "subscribed_tokens": len(hub.listeners), "auto_login": auto_login.last,
            "auto_login_configured": auto_login_configured(),
            "billing_enabled": billing.enabled(), "ai": ai_health(),
            "research": {"finnhub": bool(settings.FINNHUB_API_KEY)}, "option_recorder": recorder.status, "recent_errors": list(reversed(RECENT_ERRORS))}


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
        try:
            if s.user_id not in emails:
                emails[s.user_id] = (db.get_profile(s.user_id) or {}).get("email")
            account = s.snapshot().get("account") or {}
        except Exception as e:   # one broken session mustn't hide the rest
            print("admin sessions:", s.id, e)
            account = {}
        out.append({"id": s.id, "name": s.name, "email": emails.get(s.user_id), "symbol": s.inst.get("symbol"),
                    "market": getattr(s, "market", s.inst.get("market")), "kind": getattr(s, "kind", "rules"),
                    "started_at": s.started_at, "capital": account.get("capital"),
                    "equity": account.get("equity"), "trades": account.get("trades")})
    return out


@app.post("/admin/sessions/{sid}/stop")
def admin_stop_session(sid: str, _=Depends(admin.admin_profile)):
    if sid not in manager.sessions:
        err(404, "not_found", "That session isn't running.")
    manager.stop(sid, "Stopped by the site owner.")
    return {"ok": True}


@app.get("/admin/library")
def admin_library(_=Depends(admin.admin_profile)):
    """Library entries that were reported or hidden, most reported first."""
    emails: dict[str, str | None] = {}
    out = []
    for e in library.all_entries():
        reports = e.get("reports") or {}
        if not reports and not e.get("hidden"):
            continue
        owner = e.get("owner")
        if owner and owner not in emails:
            try:
                emails[owner] = (db.get_profile(owner) or {}).get("email")
            except Exception:
                emails[owner] = None
        reasons: dict[str, int] = {}
        for r in reports.values():
            reasons[r.get("reason", "other")] = reasons.get(r.get("reason", "other"), 0) + 1
        out.append({"id": e["id"], "name": e.get("name"), "author": e.get("author"), "email": emails.get(owner),
                    "description": e.get("description"), "reports": len(reports), "reasons": reasons,
                    "hidden": bool(e.get("hidden")), "hidden_by": e.get("hidden_by"), "published_at": e.get("published_at")})
    out.sort(key=lambda x: (-x["reports"], x["published_at"] or ""))
    return {"entries": out, "reasons": library.REASONS}


@app.post("/admin/library/{eid}")
def admin_moderate_library(eid: str, req: ModerateReq, _=Depends(admin.admin_profile)):
    e = library.load(eid)
    if not e:
        err(404, "not_found", "That strategy isn't in the library any more.")
    if req.action == "delete":
        library.remove(eid)
    else:
        library.save(library.moderate(e, req.action))
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
