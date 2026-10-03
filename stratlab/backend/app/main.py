"""StratLab API."""
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from html import escape as html_escape
import math
import re
import secrets
import threading
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from kiteconnect import exceptions as kite_exc
from razorpay import errors as rz_errors
from razorpay.errors import SignatureVerificationError

from . import admin, audit, invoices, pricing, basket, platform_check, billing, checklist, db, deck, deepdive, fixtures, importer, industry, investor, report_card, universes
from .ai_providers import health as ai_health, test_all as ai_test_all
from . import ai_writer
from .ai_writer import AIBusy, AIError, _anthropic, _gemini, ask_json, write_strategy
from . import alerts
from .auth import current_profile
from .config import settings
from .branding import public_text
from .errors import report
from .guard import Guard, HeavyGate
from . import research
from .engine import walkforward
from .data import DataError, Registry
from .data import calendar as trading_calendar
from .intel import routes as research_routes
from .intel.company import Research
from .intel import filings, sec
from .intel.sec import SEC
from .intel.net import SourceError
from .docs import Docs
from .intel.screener import summary as screener_summary
from .kite_auto import AutoLogin, AutoLoginError, configured as auto_login_configured, restart_process
from .kite_service import IST, KiteNotReady, KiteService, TickHub
from .live import LimitError, LiveManager, describe, needs_pro
from .options import importer as opt_importer
from .options.data import FREEZE, OptionsData
from .options.engine import fill_price
from .options.session import stopped_snapshot as options_stopped
from .options.recorder import Recorder, parse_targets
from . import ask, daily_report, ideas, library, public, push, risk, rotation, scan
from .models import (ShareReq, GroupLiveReq, OptionImportReq, OptionStartReq)
from .models import (AdminPlanReq, AIReq, AuditReq, MarketAuditReq, PricesReq, SellerReq, BillingDetailsReq, HolidaysReq, ModerateReq, PromoReq, ReportReq, ScanAlertReq, ScanReq, IdeasReq, LibraryReq, PrefsReq, PushReq, ImportReq, AlertsReq, ExperimentReq, LiveStartReq, NotebookReq, SaveStrategyReq,
                     Strategy, SubscribeReq, VerifyReq)
from .plans import FEATURE_PLAN, PLANS, allows, promo_active, promo_until, set_promo, group_size, has_pro_features, plan_info, public_plans, trial_state

kite = KiteService()
hub = TickHub(kite)
markets = Registry(kite)
options_data = OptionsData(kite)
manager = LiveManager(kite, hub, markets, options_data)
recorder = Recorder(options_data, db.add_option_snapshot, parse_targets(settings.OPTION_SNAPSHOTS), settings.OPTION_SNAPSHOT_MINUTES,
                    prune=db.delete_option_snapshots_before, keep_days=settings.OPTION_SNAPSHOT_KEEP_DAYS)
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
    threading.Thread(target=warm_caches, daemon=True).start()
    return "Kite login saved. Market data and live sessions are online."


def warm_caches():
    """Fill the caches the busiest pages share (instrument lists, the NIFTY 50 and US scans, sector rotation, the
    option contracts), so the first people after a restart or the morning login don't all wait on them at once.
    Each step is independent; one failing (a source down, the broker not logged in yet) skips only itself."""
    steps = [("instruments", lambda: kite.ready() and kite.search("RELIANCE", False, 1)),
             ("option contracts", lambda: options_data.ready() and options_data.underlyings()),
             ("market list", lambda: markets.markets()),
             ("scan IN", lambda: markets.provider("IN").ready() and scan.run(markets, "IN", [{"symbol": x} for x in universes.PRESETS["IN"][0]["symbols"]])),
             ("rotation IN", lambda: markets.provider("IN").ready() and rotation.run(markets, "IN", "sectors", None, "weekly", 5)),
             ("scan US", lambda: scan.run(markets, "US", [{"symbol": x} for x in universes.PRESETS["US"][0]["symbols"]])),
             ("rotation US", lambda: rotation.run(markets, "US", "sectors", None, "weekly", 5))]
    for name, fn in steps:
        try:
            fn()
        except Exception as e:
            print(f"warm-up: {name} skipped:", str(e)[:120])


auto_login = AutoLogin(kite, after_login)


def _scan_alert_ok(profile: dict) -> bool:
    from .plans import access_plan
    return allows(access_plan(profile), "scans") and bool(alerts.jobs_for(profile, "", ""))


scan_alerts_job = scan.Alerts(markets, notify=lambda p, subject, text, url: alerts.notify(p, subject, text, url=url),
                              can_alert=_scan_alert_ok)


def _filing_alert_ok(profile: dict) -> bool:
    from .plans import access_plan
    return allows(access_plan(profile), "filings") and bool(alerts.jobs_for(profile, "", ""))


filings_feed = filings.NSEFilings()
filing_alerts_job = filings.Alerts(filings_feed, notify=lambda p, subject, text, url: alerts.notify(p, subject, text, url=url),
                                   can_alert=_filing_alert_ok)
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
    scan_alerts_job.start()
    filing_alerts_job.start()
    threading.Thread(target=trading_calendar.warm, daemon=True).start()   # ~2 s, kept off the first request
    threading.Thread(target=warm_caches, daemon=True).start()
    threading.Thread(target=holiday_job, daemon=True, name="holidays").start()
    threading.Thread(target=rates_job, daemon=True, name="fx-rates").start()
    threading.Thread(target=market_audit.loop, daemon=True, name="market-audit").start()
    threading.Thread(target=market_audit_us.loop, daemon=True, name="market-audit-us").start()
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
        if _source_failed(e, tb):
            return JSONResponse(status_code=503, content={"detail": {"code": "data_unavailable",
                                "message": "A market data source failed while answering this. Try again in a minute "
                                           f"(ref {ref})."}})
        if _database_failed(e, tb):
            return JSONResponse(status_code=503, content={"detail": {"code": "database_unavailable",
                                "message": "StratLab's database isn't answering right now. Nothing you saved is lost; "
                                           f"try again in a minute (ref {ref})."}})
        return JSONResponse(status_code=500, content={"detail": {"code": "server_error",
                            "message": f"Something went wrong on our side ({request.method} {request.url.path}, ref {ref}). "
                                       "Try again in a moment; the admin page lists what failed."}})


SOURCE_FILES = ("/app/kite_service.py", "/app/data/", "/app/intel/net.py", "/app/intel/yahoo.py", "/app/intel/screener.py",
                "/app/intel/finnhub.py", "/app/intel/filings.py", "/app/intel/news.py", "/app/options/data.py", "/app/docs.py")


def _source_failed(e: Exception, tb) -> bool:
    """The crash came from inside a call to a market data source (its library or our client for it), not from
    StratLab's own logic: the user gets "try again", the admin page still lists it."""
    deepest = [f for f in tb if "site-packages" not in f.filename]
    return bool(deepest) and any(x in deepest[-1].filename for x in SOURCE_FILES)


def _database_failed(e: Exception, tb) -> bool:
    """The crash was the database (or the network to it) failing during a database call, not StratLab's code."""
    import httpx
    try:
        from postgrest.exceptions import APIError
    except ImportError:
        APIError = ()
    network = isinstance(e, (httpx.TransportError, ConnectionError, TimeoutError)) or (APIError and isinstance(e, APIError))
    return bool(network) and any(f.filename.endswith(("/app/db.py", "/app/admin.py")) or "/postgrest/" in f.filename for f in tb)


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


app.add_middleware(HeavyGate)   # inside the guard: heavy work takes turns, ordinary pages don't wait behind it
app.add_middleware(Guard)   # size cap, rate limit, security headers; inside CORS so its replies stay readable
app.add_middleware(CORSMiddleware, allow_origins=settings.FRONTEND_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


# ---------- helpers ----------
def err(status: int, code: str, message: str):
    raise HTTPException(status, {"code": code, "message": public_text(message)})


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
    return JSONResponse(status_code=503, content={"detail": {"code": "data_offline", "message": public_text(str(exc))}})


@app.exception_handler(research.ResearchError)
def _research_error(request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code, "message": public_text(exc.message)}})


@app.exception_handler(DataError)
def _data_error(request, exc):
    return JSONResponse(status_code=502, content={"detail": {"code": "data_error", "message": public_text(str(exc))}})


@app.exception_handler(kite_exc.KiteException)
def _kite_error(request, exc):
    print("market data request failed:", exc)
    return JSONResponse(status_code=502, content={"detail": {"code": "data_error",
                        "message": "The market data request failed. Try again in a moment."}})


# ---------- account ----------
@app.get("/health")
def health():
    """Public: only whether things are up. Provider details are on the admin page."""
    return {"ok": True, "data_online": kite.ready(), "feed_connected": hub.connected,
            "ai_configured": any(p["in_use"] for p in ai_health())}


@app.get("/plans")
def plans():
    return PLANS


@app.get("/pricing")
def prices():
    """Prices in every currency StratLab shows, which currency each is charged in, and country → currency."""
    return pricing.public()


def fx_rate(code: str) -> float:
    """Rupees per unit of a currency, from the market data source (e.g. EURINR=X)."""
    price = research_hub.yahoo.meta(f"{code}INR=X").get("price")
    if not price:
        raise ValueError("no rate")
    return float(price)


def rates_job():
    """Once a day: exchange rates, so prices in other currencies follow the rupee price."""
    time.sleep(120)
    while True:
        try:
            pricing.refresh_rates(fx_rate)
        except Exception as e:
            print("exchange rate refresh failed:", e)
        time.sleep(24 * 3600)


def prices_view() -> dict:
    try:
        fx = json.loads(db.get_setting(pricing.RATES) or "{}")
    except Exception:
        fx = {}
    return {"currencies": pricing.table(), "rates_at": fx.get("at"), "rate_errors": fx.get("errors") or []}


@app.get("/admin/prices")
def admin_prices(_=Depends(admin.admin_profile)):
    """Every currency's prices (automatic from the rupee price unless fixed), rates and Razorpay plan IDs."""
    return prices_view()


@app.post("/admin/prices/rates")
def admin_prices_rates(_=Depends(admin.admin_profile)):
    """Read today's exchange rates now instead of waiting for the daily run."""
    pricing.refresh_rates(fx_rate)
    return prices_view()


@app.put("/admin/prices")
def admin_set_prices(req: PricesReq, _=Depends(admin.admin_profile)):
    try:
        pricing.save(req.currencies)
    except ValueError as e:
        err(400, "bad_price", str(e))
    return prices_view()


@app.get("/me")
def me(profile=Depends(current_profile)):
    plan = profile["_plan"]
    info = plan_info(plan)
    return ok({
        "id": profile["id"], "email": profile.get("email"),
        "plan": plan, "plan_info": info, "paid_plan": profile.get("_paid_plan", plan),
        "promo": {"until": until.isoformat()} if (until := promo_until()) and promo_active() else None,
        "billing": {"subscribed_plan": profile.get("plan"), "status": profile.get("plan_status"),
                    "renews_or_ends": profile.get("current_period_end"),
                    "cancel_at_period_end": bool(profile.get("cancel_at_period_end"))},
        "usage": {"backtests_used": backtests_used(profile), "backtests_limit": info["backtests_per_month"],
                  "ai_used": db.count_usage(profile["id"], "ai", month_start_iso()), "ai_limit": info["ai_builds_per_month"]},
        "trial": trial_state(profile) if plan == "free" else None,
        "live_running": len(manager.user_running(profile["id"])), "live_limit": info["live_limit"],
        "alerts": {"channels": alerts.ready_channels(), "enabled": bool(profile.get("alerts_enabled")), "telegram_chat_id": profile.get("telegram_chat_id"),
                   "email": profile.get("alert_email"), "daily_report": daily_report.wants_report(db, profile["id"])},
        "prefs": {k: prefs_of(profile["id"]).get(k) for k in ("level", "focus")},
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
    """Experience level and what the user came for (investing, trading or both): they only change defaults (what's
    expanded, what's suggested first, the menu order), never what's allowed."""
    prefs = {**prefs_of(profile["id"]), **{k: v for k, v in (("level", req.level), ("focus", req.focus)) if v}}
    db.set_setting(daily_report.PREFS + profile["id"], json.dumps(prefs))
    return {"prefs": {k: prefs.get(k) for k in ("level", "focus")}}


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
    if req.group is not None and not req.instrument:
        nb["group"] = group_body(req.group)     # e.g. "Backtest ST S2 on this group" from a scan
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
        nb["group"] = group_body(req.group)
    return ok(save_notebook(profile, nb))


def group_body(g) -> dict:
    return {"id": g.id, "name": g.name, "market": g.market.upper(), "maxOpen": min(g.maxOpen, len(g.members)),
            "members": [m.model_dump(exclude_none=True) for m in g.members]}


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
    experiments = research.slim((experiments + [rec])[-50:])
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


# ---------- Stage 2 + Supertrend scans (Pro) ----------
def scan_members(profile, region: str, set_id: str) -> tuple[str, list[dict]]:
    if set_id == "watchlist":
        return "Your watchlist", scan.watchlist_members(profile["id"], region)
    preset = next((p for p in universes.presets(region) if p["id"] == set_id), None)
    if not preset:
        err(404, "not_found", "That group isn't available.")
    return preset["name"], [{"symbol": s} for s in preset["symbols"]]


@app.get("/research/scan/sets")
def scan_sets(region: str = "IN", profile=Depends(current_profile)):
    region = "US" if region.upper() == "US" else "IN"
    return {"sets": [{"id": "watchlist", "name": "Your watchlist", "count": len(scan.watchlist_members(profile["id"], region))}]
            + [{"id": p["id"], "name": p["name"], "count": p["count"]} for p in universes.presets(region)],
            "alerts": scan.alert_on(profile["id"]), "template": scan.ST_S2, "fresh_days": scan.FRESH,
            "rotation_sets": [{"id": k, "name": v["name"]} for k, v in rotation.index_sets(region).items()]}


@app.post("/research/scan")
def run_scan(req: ScanReq, profile=Depends(current_profile)):
    """Stage and Supertrend for every stock in a group, fresh ST S2 signals first. Facts, never advice."""
    need(profile, "scans", "Stage 2 + Supertrend scans")
    name, members = scan_members(profile, req.region, req.set)
    if not members:
        err(400, "empty", "Your watchlist has no stocks in this market yet. Star a few companies in Research first.")
    prov = markets.provider(req.region)
    if prov is None or not prov.ready():
        raise KiteNotReady("Market data for this market is offline right now.")
    out = scan.run(markets, req.region, members)
    out["problems"] = [public_text(x) for x in out["problems"]]          # data-source errors can name the source
    return ok({"name": name, "market": req.region, **out})


@app.get("/research/rotation")
def sector_rotation(region: str = "IN", set: str = "sectors", interval: str = "weekly", tail: int = 5,
                    profile=Depends(current_profile)):
    """Where each sector (or stock in a group) sits against the benchmark: relative strength and its momentum."""
    need(profile, "scans", "Sector rotation")
    region = "US" if region.upper() == "US" else "IN"
    interval = "daily" if interval == "daily" else "weekly"
    prov = markets.provider(region)
    if prov is None or not prov.ready():
        raise KiteNotReady("Market data for this market is offline right now.")
    set = set[:60]
    index_sets = rotation.index_sets(region)
    if set in index_sets:
        members, name = None, index_sets[set]["name"]
    elif set.startswith("sector:"):
        members, name = None, f"{rotation._label(region, set.split(':', 1)[1], None)} stocks"
    else:
        name, members = scan_members(profile, region, set)
        if len(members) < 2:
            err(400, "empty", "Pick a group with at least two stocks, or star more companies for your watchlist.")
    try:
        out = rotation.run(markets, region, set, members, interval, tail)
    except LookupError as e:
        err(404 if set.startswith("sector:") else 503, "no_benchmark", str(e))
    out["skipped"] = [public_text(x) for x in out["skipped"]]
    return ok({"name": name, "market": region, **out})


@app.put("/research/scan/alerts")
def scan_alerts(req: ScanAlertReq, profile=Depends(current_profile)):
    if req.on:
        need(profile, "scans", "ST S2 watchlist alerts")
    scan.set_alert(profile["id"], req.on)
    return {"alerts": req.on}


# ---------- exchange filings and red flags (Pro, India) ----------
def filing_call(fn):
    try:
        return fn()
    except SourceError as e:
        err(503 if e.busy else 502, "filings_unavailable", str(e))


@app.get("/research/filings")
def filings_watchlist(profile=Depends(current_profile)):
    """Red flags in the last 3 months for each India watchlist stock."""
    need(profile, "filings", "Filings and red flags")
    syms = filings.watchlist_symbols(profile["id"])
    out = filings.overview(filings_feed, syms) if syms else {"rows": [], "problems": [], "days": filings.WINDOW_DAYS}
    out["problems"] = [public_text(x) for x in out["problems"]]
    return ok({**out, "alerts": bool(filings.alert_state(profile["id"]).get("on")), "send_at": filings.SEND_AT})


@app.get("/research/filings/{symbol}")
def filings_company(symbol: str, profile=Depends(current_profile)):
    """One NSE company's filings for the last year, with red flags and the 3-month summary."""
    need(profile, "filings", "Filings and red flags")
    sym = research_routes.symbol_of(symbol)
    return ok(filing_call(lambda: filings.report(filings_feed, sym)))


@app.put("/research/filings/alerts")
def filings_alerts(req: ScanAlertReq, profile=Depends(current_profile)):
    if req.on:
        need(profile, "filings", "Filing alerts")
    filings.set_alert(profile["id"], req.on)
    return {"alerts": req.on}


# ---------- company deep dive: business, capex and growth (Pro, India) ----------
deep_docs = Docs()


def with_industry(sym: str, p: dict) -> dict:
    """The company page's industry classification, or the exchange's own when the page has none."""
    if p.get("industry_path") or not hasattr(filings_feed, "industry"):
        return p
    try:
        return {**p, "industry_path": filings_feed.industry(sym)}
    except Exception:            # a missing classification only means the general rules
        return p


sec_feed = SEC()
REGIONS = ("IN", "US")


def deep_region(region: str) -> str:
    r = (region or "IN").upper()
    if r not in REGIONS:
        err(400, "bad_region", "The deep dive covers Indian (IN) and US companies.")
    return r


def deep_base_us(sym: str) -> dict:
    """A US company from its SEC filings: numbers, industry and filings, with ratios from today's share price."""
    p = dict(research_routes.source_call(lambda: sec_feed.company(sym)))
    try:
        m = research_hub.yahoo.meta(sym)
    except Exception:                     # no price: the numbers still stand, the ratios that need a price don't
        m = {}
    p["ratios"] = sec.ratios(p, m.get("price"), m.get("high52"), m.get("low52"))
    try:
        wiki = research_hub.wiki.company(p.get("name") or sym) or {}
        p["about"] = wiki.get("extract") or ""
    except Exception:
        p["about"] = ""
    return {"p": p, "docs": p.get("documents") or [], "doc_note": None, "filings": None, "trend": price_trend(sym, "US")}


def deep_base(sym: str, region: str = "IN") -> dict:
    """Numbers and the list of readable documents for one company (no AI)."""
    if region == "US":
        return deep_base_us(sym)
    p = with_industry(sym, research_routes.source_call(lambda: research_hub.screener.company(sym)))
    try:
        items = filings_feed.announcements(sym, deepdive.DOC_DAYS)
        doc_note, fsum = None, filings.summarise(items)
    except SourceError as e:
        items, doc_note, fsum = [], public_text(str(e)), None
    return {"p": p, "docs": deepdive.documents(items)[:20], "doc_note": doc_note, "filings": fsum, "trend": price_trend(sym)}


def price_trend(sym: str, market: str = "IN") -> dict | None:
    """Stage and Supertrend on daily candles, or None when prices aren't available."""
    try:
        ids, _ = universes.resolve(markets, market, [{"symbol": sym}])
        return scan.analyse(scan._bars(markets, ids[0])) if ids else None
    except Exception:
        return None


def deep_view(sym: str, base: dict) -> dict:
    p = base["p"]
    us = p.get("region") == "US"
    key = f"US:{sym}" if us else sym          # stored AI reads: Indian symbols keep their old keys
    reads, card = deepdive.stored(key), report_card.stored(key)
    nums = deepdive.numbers(p)
    card_view = report_card.view(card, nums)
    snap = screener_summary(p)
    return {"symbol": sym, "region": "US" if us else "IN", "currency": "USD" if us else "INR", "source_url": p.get("url"),
            "name": p.get("name") or sym, "about": (p.get("about") or "")[:1200], "numbers": nums,
            "snapshot": {k: snap.get(k) for k in ("market_cap_cr", "price", "pe", "pb", "roce", "roe", "debt_equity", "div_yield")},
            "industry_measures": industry.measures(p, sym),
            "valuation": industry.valuation(p, snap, industry.classify(p, nums, sym)["group"], industry.measures(p, sym)["key"]),
            "documents": base["docs"], "doc_note": base["doc_note"], "reads": reads, "reads_stale": not deepdive.fresh(reads),
            "calls": sum(d["kind"] == "transcript" for d in base["docs"]),
            "card": card_view, "card_stale": not report_card.fresh(card), "trend": base["trend"], "filings": base["filings"],
            "checklist": checklist.evaluate(p, nums, base["filings"], base["trend"], card_view, None if us else sym),
            "ai": True, "report_card": not us}


def company_hosts(p: dict) -> tuple[str, ...]:
    """The company's own website, where exchange filings often point for the full transcript or presentation."""
    from .docs import site_domain
    d = site_domain(p.get("website"))
    return (d,) if d else ()


def deep_ai_allowed(profile) -> None:
    since = (datetime.now(IST) - timedelta(days=1)).isoformat()
    if db.count_usage(profile["id"], "research_ai", since) >= settings.RESEARCH_AI_PER_DAY:
        err(429, "research_ai_limit", f"You've used {settings.RESEARCH_AI_PER_DAY} fresh AI reads today. Stored reads still work; try again tomorrow.")


def deep_symbol(symbol: str, region: str) -> str:
    return research_routes.symbol_of(symbol) if region == "IN" else re.sub(r"[^A-Z0-9.\-]", "", symbol.upper())[:12]


def no_us_ai(region: str):
    if region == "US":
        err(400, "us_no_calls", "US companies don't file earnings-call transcripts with the SEC, so the management report card "
                                "isn't available for them yet.")


@app.get("/research/deep/{symbol}")
def deep_dive(symbol: str, region: str = "IN", profile=Depends(current_profile)):
    """Growth, margins, capex and cash flow from the reported numbers, plus any stored read of the company's documents.
    India from the company pages and NSE filings; the US from the SEC's filings."""
    need(profile, "deepdive", "The company deep dive")
    region = deep_region(region)
    sym = deep_symbol(symbol, region)
    return ok(deep_view(sym, deep_base(sym, region)))


@app.post("/research/deep/{symbol}/read")
def deep_dive_read(symbol: str, refresh: bool = False, region: str = "IN", profile=Depends(current_profile)):
    """Read the company's own documents with AI: business model, capex and growth plans. India: the latest investor
    presentation and call transcripts. US: the latest 10-K and earnings releases."""
    need(profile, "deepdive", "The company deep dive")
    region = deep_region(region)
    sym = deep_symbol(symbol, region)
    key = f"US:{sym}" if region == "US" else sym
    base = deep_base(sym, region)
    have = deepdive.stored(key)
    if deepdive.fresh(have) and not refresh:
        return ok(deep_view(sym, base))
    if not base["docs"] and not base["p"].get("about"):
        err(404, "no_documents", "No annual report or earnings release was found for this company in the last two years." if region == "US"
            else "No investor presentation or call transcript was found for this company in the last two years.")
    deep_ai_allowed(profile)
    p = base["p"]
    try:
        if region == "US":
            reads = deepdive.read_us(sym, p.get("name") or sym, p.get("about") or "", base["docs"], sec_feed, (_gemini, _anthropic),
                                     industry.measures(p, sym))
        else:
            reads = deepdive.read(sym, p.get("name") or sym, p.get("about") or "", base["docs"], deep_docs, (_gemini, _anthropic),
                                  industry.measures(p, sym), company_hosts(p))
    except AIBusy as e:
        err(503, "ai_busy", str(e))
    except AIError as e:
        err(422, "ai_failed", str(e))
    reads["problems"] = [public_text(x) for x in reads["problems"]]
    deepdive.store(key, reads)
    db.add_usage(profile["id"], "research_ai")
    return ok(deep_view(sym, base))


_investor_pool = ThreadPoolExecutor(max_workers=4)


@app.get("/research/investor")
def investor_home(profile=Depends(current_profile)):
    """Every India watchlist company: trend, sector rotation, red flags, checklist and report card on one page."""
    need(profile, "deepdive", "The investor home")
    syms = filings.watchlist_symbols(profile["id"])[:investor.MAX]
    if not syms:
        return ok({"rows": [], "as_of": None})
    try:
        rot = rotation.run(markets, "IN", "sectors", None, "weekly", 4)
        quad = {r["symbol"]: {"symbol": r["symbol"], "name": r["name"], "quadrant": r["quadrant"]} for r in rot["rows"]}
    except Exception:
        quad = {}

    def one(sym):
        problem = None
        try:
            p = with_industry(sym, research_hub.screener.company(sym))
        except Exception as e:
            p, problem = None, public_text(str(e))[:120]
        try:
            fsum = filings.summarise(filings_feed.announcements(sym))
        except Exception:
            fsum = None
        trend = price_trend(sym)
        nums = deepdive.numbers(p) if p else None
        card = report_card.view(report_card.stored(sym), nums) if nums else None
        checks = checklist.evaluate(p, nums, fsum, trend, card, sym) if p else None
        sec = investor.sector_of("IN", sym)
        sector = quad.get(sec) or ({"symbol": sec, "name": rotation._label("IN", sec, None), "quadrant": None} if sec else None)
        return investor.row(sym, (p or {}).get("name"), trend, sector, fsum, checks, card, deepdive.stored(sym) is not None, problem)

    rows = list(_investor_pool.map(one, syms))
    return ok({"rows": rows, "as_of": datetime.now(IST).isoformat(timespec="minutes")})


@app.get("/research/deep/{symbol}/deck")
def deep_dive_deck(symbol: str, region: str = "IN", profile=Depends(current_profile)):
    """The deep dive as a PowerPoint deck: numbers, business, plans, report card and checklist, with sources."""
    need(profile, "deepdive", "The company deck")
    region = deep_region(region)
    sym = deep_symbol(symbol, region)
    data = deck.build(deep_view(sym, deep_base(sym, region)))
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{sym}-deep-dive.pptx"'})


@app.post("/research/deep/{symbol}/card")
def deep_dive_card(symbol: str, refresh: bool = False, region: str = "IN", profile=Depends(current_profile)):
    """The management report card: targets given on past earnings calls, checked against the reported numbers."""
    need(profile, "deepdive", "The company deep dive")
    no_us_ai(deep_region(region))
    sym = research_routes.symbol_of(symbol)
    base = deep_base(sym)
    if report_card.fresh(report_card.stored(sym)) and not refresh:
        return ok(deep_view(sym, base))
    if not any(d["kind"] == "transcript" for d in base["docs"]):
        err(404, "no_calls", "No earnings-call transcript was found for this company in the last two years.")
    deep_ai_allowed(profile)
    p = base["p"]
    try:
        card = report_card.read(sym, p.get("name") or sym, base["docs"], deep_docs, (_gemini, _anthropic), company_hosts(p))
    except report_card.NoCalls as e:          # nothing read, nothing charged
        detail = "; ".join(public_text(x) for x in e.problems[:3])
        err(422, "no_readable_calls", "None of the earnings-call transcripts could be read. " + (detail or "")[:400])
    except AIBusy as e:
        err(503, "ai_busy", str(e))
    except AIError as e:
        err(422, "ai_failed", str(e))
    card["problems"] = [public_text(x) for x in card["problems"]]
    report_card.store(sym, card)
    db.add_usage(profile["id"], "research_ai")
    return ok(deep_view(sym, base))


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
        if not isinstance(e, HTTPException):     # the price feed failed while loading the warm-up candles
            report(e, where="start paper session")
            err(503, "prices_unavailable", "Couldn't load the price history this strategy needs to start. Nothing was "
                                           "started; try again in a minute.")
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
        err(503, "data_offline", "Option quotes come from the live feed, which is offline until today's data login completes. "
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
    if profile.get("_paid_plan", profile["_plan"]) == req.plan:
        err(400, "already_on_plan", f"You're already on {PLANS[req.plan]['name']}.")
    try:
        return billing.create_subscription(profile, req.plan, req.period, req.currency)
    except ValueError as e:
        err(503, "billing_offline", str(e))
    except rz_errors.BadRequestError as e:
        # wrong keys ("Authentication failed") or a plan ID the account doesn't have. Not the user's sign-in,
        # so never 401 here: that would sign them out of StratLab.
        print("razorpay subscribe refused:", e)
        why = f" Razorpay said: {str(e)[:200]}" if admin.is_admin(profile) else ""   # only the site owner sees the reason
        err(502, "billing_setup", "Payments aren't set up correctly on the server yet. Try again later." + why)
    except (rz_errors.ServerError, rz_errors.GatewayError) as e:
        print("razorpay subscribe failed:", e)
        err(502, "billing_unavailable", "The payment service didn't answer. Try again in a minute.")


@app.post("/billing/verify")
def verify(req: VerifyReq, profile=Depends(current_profile)):
    try:
        billing.verify_checkout(profile, req.razorpay_payment_id, req.razorpay_subscription_id, req.razorpay_signature)
    except SignatureVerificationError:
        err(400, "payment_not_verified", "Payment could not be verified. If money was taken, it will be refunded by Razorpay or activated shortly.")
    except (rz_errors.BadRequestError, rz_errors.ServerError, rz_errors.GatewayError) as e:
        # the signature was fine but the subscription couldn't be read back; the webhook activates it anyway
        print("razorpay verify fetch failed:", e)
        err(502, "payment_pending", "Payment received. Your plan will switch on within a few minutes; refresh this page shortly.")
    return {"activated": True}


@app.get("/billing/invoices")
def my_invoices(profile=Depends(current_profile)):
    """Your invoices, newest first, and the billing details printed on future ones."""
    return {"invoices": [{k: i[k] for k in ("number", "date", "total", "currency", "supply")} for i in invoices.of_user(profile["id"])],
            "billing": invoices.billing_of(profile["id"]), "states": invoices.STATES}


@app.put("/billing/details")
def my_billing_details(req: BillingDetailsReq, profile=Depends(current_profile)):
    """Name, address, state and (for a business) GSTIN for your future invoices."""
    try:
        return {"billing": invoices.save_billing(profile["id"], req.model_dump())}
    except ValueError as e:
        err(400, "bad_billing", str(e))


@app.get("/billing/invoices/{year}/{n}")
def invoice_page(year: str, n: str, profile=Depends(current_profile)):
    """One invoice as a printable page: its owner or the site owner only."""
    inv = next((i for i in invoices.of_user(profile["id"]) if i["number"].endswith(f"/{year}/{n}")), None)
    if inv is None and admin.is_admin(profile):
        inv = next((i for i in invoices.of_year(year) if i["number"].endswith(f"/{year}/{n}")), None)
    if inv is None:
        err(404, "not_found", "No such invoice.")
    return Response(invoices.html(inv), media_type="text/html; charset=utf-8")


@app.get("/admin/invoices")
def admin_invoices(year: str = "", _=Depends(admin.admin_profile)):
    """Seller details and every invoice of a financial year (this one by default), for the accounts."""
    fy = year or invoices.fy(datetime.now(timezone.utc))
    rows = invoices.of_year(fy)
    return {"seller": invoices.seller(), "states": invoices.STATES, "year": fy,
            "invoices": [{k: i[k] for k in ("number", "date", "total", "currency", "supply")} | {"email": i["buyer"].get("email"),
                         "tax": round(sum(t["amount"] for t in i["taxes"]), 2)} for i in rows]}


@app.put("/admin/invoices/seller")
def admin_invoice_seller(req: SellerReq, _=Depends(admin.admin_profile)):
    try:
        return {"seller": invoices.save_seller(req.model_dump())}
    except ValueError as e:
        err(400, "bad_seller", str(e))


@app.post("/billing/cancel")
def cancel(profile=Depends(current_profile)):
    try:
        billing.cancel(profile)
    except ValueError as e:
        err(400, "no_subscription", str(e))
    return {"cancel_at_period_end": True}


@app.get("/billing/webhook")
def webhook_info():
    """Opening the webhook URL in a browser: say it's up, instead of a bare 405."""
    return {"ok": True, "note": "This is the payment webhook. It only accepts POST requests signed by Razorpay, "
                                "so opening it in a browser does nothing. Use Razorpay's webhook test to check it."}


@app.post("/billing/webhook")
async def webhook(request: Request):
    body = await request.body()
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        print("razorpay webhook refused: RAZORPAY_WEBHOOK_SECRET isn't set on the server")
        err(503, "webhook_not_set", "Webhook secret isn't set on the server: add RAZORPAY_WEBHOOK_SECRET and redeploy.")
    try:
        billing.handle_webhook(body, request.headers.get("X-Razorpay-Signature", ""))
    except SignatureVerificationError:
        print("razorpay webhook refused: signature doesn't match RAZORPAY_WEBHOOK_SECRET")
        err(400, "bad_signature", "Signature doesn't match: RAZORPAY_WEBHOOK_SECRET on the server must be exactly the "
                                  "secret typed in Razorpay's webhook settings (same mode: Test or Live).")
    except ValueError:  # malformed JSON
        err(400, "bad_payload", "The webhook body isn't valid JSON.")
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
            "research": {"finnhub": bool(settings.FINNHUB_API_KEY)},
            "promo_until": (promo_until().isoformat() if promo_active() else None), "option_recorder": recorder.status, "recent_errors": list(reversed(RECENT_ERRORS)),
            "calendar": calendar_status()}


def calendar_status() -> dict:
    """How far ahead India's exchange holidays are known: the installed calendar, the exchange's own list (fetched
    daily) and anything the admin pasted."""
    until = trading_calendar.known_until("IN")
    added = sorted(trading_calendar.extra_holidays("IN"))
    auto = trading_calendar.auto_status("IN")
    # the exchange's list covers its whole year: holidays known to the end of the latest year it lists
    latest_year = max([int(d[:4]) for d in auto.get("days") or []] + [0])
    ends = [until.isoformat() if until else "", f"{latest_year}-12-31" if latest_year else ""]
    last = max(ends) or None
    days_left = (date.fromisoformat(last) - datetime.now(IST).date()).days if last else None
    return {"known_until": until.isoformat() if until else None, "added": added, "covered_until": last, "days_left": days_left,
            "auto": {"at": auto.get("at"), "tried_at": auto.get("tried_at"), "error": public_text(auto.get("error")),
                     "count": len(auto.get("days") or [])}}


def holiday_job():
    """Once a day: the exchange's holiday list, so next year's holidays arrive by themselves when it publishes them."""
    time.sleep(90)                          # after startup traffic
    while True:
        try:
            trading_calendar.refresh_from_exchange(filings_feed.holidays, "IN")
            trading_calendar.refresh_from_exchange(lambda: filings_feed.holidays("CD"), "CDS")
        except Exception as e:
            print("holiday refresh failed:", e)
        time.sleep(24 * 3600)


@app.post("/admin/holidays/refresh")
def admin_holidays_refresh(_=Depends(admin.admin_profile)):
    """Fetch the exchange's holiday list now instead of waiting for the daily run."""
    trading_calendar.refresh_from_exchange(filings_feed.holidays, "IN")
    trading_calendar.refresh_from_exchange(lambda: filings_feed.holidays("CD"), "CDS")
    return calendar_status()


@app.post("/admin/holidays")
def admin_holidays(req: HolidaysReq, _=Depends(admin.admin_profile)):
    """Save the exchange's official holiday list (pasted from its circular), for days the built-in calendar lacks."""
    found = parse_holidays(req.text)
    if not found:
        err(400, "no_dates", "No dates found. Paste the exchange's list, with dates like 26-Jan-2027 or 2027-01-26.")
    trading_calendar.set_extra_holidays("IN", found)
    return calendar_status()


MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def parse_holidays(text: str) -> list[str]:
    """Dates in a pasted holiday list: 2027-01-26, 26-Jan-2027, 26 January 2027 or 26/01/2027."""
    import re as _re
    out = set()
    for y, m, d in _re.findall(r"\b(20\d\d)-(\d\d)-(\d\d)\b", text):
        out.add((int(y), int(m), int(d)))
    for d, mon, y in _re.findall(r"\b(\d{1,2})[-\s/]([A-Za-z]{3,9})[-\s/,]*(20\d\d)\b", text):
        if mon[:3].lower() in MONTHS:
            out.add((int(y), MONTHS[mon[:3].lower()], int(d)))
    for d, m, y in _re.findall(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b", text):
        out.add((int(y), int(m), int(d)))
    valid = []
    for y, m, d in out:
        try:
            valid.append(date(y, m, d).isoformat())
        except ValueError:
            continue
    return sorted(valid)


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


@app.post("/admin/billing/check")
def admin_billing_check(_=Depends(admin.admin_profile)):
    """Whether Razorpay accepts the keys and knows each plan, straight from Razorpay."""
    return billing.check_setup()


@app.post("/admin/fixture/prices")
def admin_fixture_prices(_=Depends(admin.admin_profile)):
    """About two years of real daily prices (indices, sectors, the ready-made groups) as one gzipped JSON file, for
    the test suite. Prices only: no user data and no credentials. Takes a minute or two (the data sources' rate limits)."""
    snap = fixtures.build(markets)
    count = sum(len(v) for v in snap["markets"].values())
    if not count:
        err(503, "data_offline", "No market data came back: " + "; ".join(snap["problems"][:3]))
    return Response(content=fixtures.pack(snap), media_type="application/gzip",
                    headers={"Content-Disposition": 'attachment; filename="real_prices.json.gz"', "X-Instruments": str(count),
                             "X-Problems": str(len(snap["problems"])), "Access-Control-Expose-Headers": "X-Instruments, X-Problems"})


@app.post("/admin/filings/check")
def admin_filings_check(symbol: str = "RELIANCE", _=Depends(admin.admin_profile)):
    """Whether the exchange's filings feed answers from this server, with the latest few filings for one stock."""
    sym = research_routes.symbol_of(symbol)
    filings_feed.cache.clear()
    try:
        items = filings_feed.announcements(sym)
    except SourceError as e:
        return {"ok": False, "symbol": sym, "error": str(e)}
    doc = None
    found = deepdive.documents(filings_feed.announcements(sym, deepdive.DOC_DAYS))
    if found:
        probs: list[str] = []
        got = deepdive.readable(deep_docs, found, 1, probs)
        if got:
            d, text = got[0]
            doc = {"ok": True, "title": d["title"], "kind": d["kind"], "chars": len(text), "start": text[:160]}
        else:
            doc = {"ok": False, "title": found[0]["title"], "kind": found[0]["kind"], "error": public_text("; ".join(probs) or "nothing readable")}
    return {"ok": True, "symbol": sym, "count": len(items), "latest": [{k: i[k] for k in ("at", "label", "subject")} for i in items[:3]],
            "alerts": filing_alerts_job.status, "document": doc, "documents_found": len(found)}


audit_runner = audit.Runner()


def live_price(sym: str) -> float | None:
    """The live exchange price from the broker's feed; the exchange's own website when the feed is offline (it
    turns cloud servers away, so that is a last resort)."""
    if kite.ready():
        return (kite.quote([sym]).get(sym) or {}).get("price")
    return filings_feed.last_price(sym)


def audit_one(sym: str, docs: bool, exchange=None, region: str = "IN") -> dict:
    us = region == "US"
    read = (lambda cands, probs, p: deepdive.readable(deep_docs, cands, 1, probs, company_hosts(p))) if docs and not us else None
    row = audit.audit_company(sym, lambda s: deep_base(s, region), deep_view, None if us else exchange, read)
    for i in row["issues"]:
        i["detail"] = public_text(i["detail"])
    return row


_market_breaker: list = [None, 0.0]


def _market_check(sym: str) -> dict:
    """One company for the whole-market audit; the exchange-price breaker is renewed every six hours, so a refusal
    in the morning doesn't leave the rest of the day unchecked."""
    if time.time() - _market_breaker[1] > 6 * 3600:
        _market_breaker[:] = [audit.Breaker(live_price), time.time()]
    return audit_one(research_routes.symbol_of(sym), False, _market_breaker[0])


market_audit = audit.MarketAudit(lambda: filings_feed.all_equities(), _market_check,
                                 busy_fn=lambda: bool(audit_runner.state.get("running")))


def _sec_companies() -> list[dict]:
    """Every company with a ticker that files with the SEC, from the SEC's own list."""
    return [{"symbol": t, "name": v["name"], "listed": None} for t, v in sec_feed.tickers().items()]


market_audit_us = audit.MarketAudit(lambda: _sec_companies(), lambda s: audit_one(s, False, None, "US"),
                                    busy_fn=lambda: bool(audit_runner.state.get("running")), key="audit:market-us")


def market_for(region: str):
    return market_audit_us if region == "US" else market_audit


@app.get("/admin/audit/market")
def admin_market_audit(region: str = "IN", _=Depends(admin.admin_profile)):
    """The whole-market audit: every NSE-listed company (or every company filing with the SEC), checked in the
    background while switched on."""
    return market_for(deep_region(region)).status()


@app.post("/admin/audit/market")
def admin_market_audit_set(req: MarketAuditReq, _=Depends(admin.admin_profile)):
    """Switch the whole-market audit on or off, re-read the exchange's list now, or check everything again."""
    m = market_for(req.region)
    if req.on is not None:
        m.set_enabled(req.on)
    if req.restart:
        m.restart()
    if req.read_list:
        threading.Thread(target=m.refresh_list, kwargs={"force": True}, daemon=True).start()
    return m.status()


@app.get("/admin/audit")
def admin_audit_status(region: str = "IN", _=Depends(admin.admin_profile)):
    """The running or last data audit, and the sets it can run on."""
    return {**audit_runner.status(), "sets": audit.sets(deep_region(region))}


@app.post("/admin/audit")
def admin_audit_start(req: AuditReq, _=Depends(admin.admin_profile)):
    """Run every company in a set through the deep dive's numbers, prices, checks and documents, comparing each
    against its source. Runs in the background (about 3 to 10 seconds a company, so a NIFTY 500 run takes about an
    hour); no AI is used."""
    try:
        syms = audit.symbols_for(req.set, req.symbols, getattr(filings_feed, "index_members", None), req.region)
    except ValueError:
        err(400, "bad_set", "Pick one of the listed sets.")
    except SourceError as e:
        err(503, "index_unavailable", f"The exchange's index list couldn't be read ({e}). Try again in a minute, "
                                      "or paste the symbols instead.")
    syms = [deep_symbol(s, req.region) for s in syms]
    label = (f"{len(syms)} chosen {'US ' if req.region == 'US' else ''}companies" if req.symbols
             else next((s["name"] for s in audit.sets(req.region) if s["id"] == req.set), req.set))
    try:
        exchange = audit.Breaker(live_price)
        return {**audit_runner.start(syms, label, lambda s: audit_one(s, req.docs, exchange, req.region), req.docs, req.region),
                "sets": audit.sets(req.region)}
    except RuntimeError as e:
        err(409, "audit_running", str(e))


@app.post("/admin/platform/check")
def admin_platform_check(_=Depends(admin.admin_profile)):
    """Every feature once on live data: prices and their freshness per market, a backtest per market, the scans,
    sector rotation, the option chain, filings, company pages, news, the database and the holiday calendar."""
    pc, today = platform_check, datetime.now(IST).date()
    checks = [(f"Prices: {m}", "Prices", (lambda m=m: pc.check_market(markets, m, today))) for m in markets.providers]
    checks += [(f"Backtest: {m}", "Backtests", (lambda m=m: pc.check_backtest(markets, m))) for m in markets.providers]
    checks += [("Scan: NIFTY 50", "Scans", lambda: pc.check_scan(markets, "IN", "nifty50")),
               ("Scan: US large caps", "Scans", lambda: pc.check_scan(markets, "US", "us_mega")),
               ("Sector rotation: IN", "Rotation", lambda: pc.check_rotation(markets, "IN")),
               ("Sector rotation: US", "Rotation", lambda: pc.check_rotation(markets, "US")),
               ("Option chain: NIFTY", "Options", lambda: pc.check_options(options_data, today)),
               ("Exchange filings", "Filings", lambda: pc.check_filings(filings_feed)),
               ("Company page: RELIANCE", "Research", lambda: pc.check_company(research_hub, "IN", "RELIANCE")),
               ("Company page: AAPL", "Research", lambda: pc.check_company(research_hub, "US", "AAPL")),
               ("News", "Research", lambda: pc.check_news(research_hub)),
               ("Database", "Server", lambda: pc.check_database(db)),
               ("Holiday calendar", "Server", lambda: pc.check_calendar(today))]
    out = pc.run_all(checks)
    for r in out["checks"]:
        r["detail"] = public_text(r["detail"])
    return out


@app.delete("/admin/audit")
def admin_audit_stop(_=Depends(admin.admin_profile)):
    """Stop a running audit after the current company; the rows so far are kept."""
    audit_runner.cancel()
    return audit_runner.status()


@app.post("/admin/promo")
def admin_start_promo(req: PromoReq, who=Depends(admin.admin_profile)):
    """Everyone gets Pro, starting now, for this many days (the launch offer). Starting again resets the end."""
    until = set_promo(req.days)
    log.info("admin %s started the free offer until %s", who.get("email"), until)
    return {"until": until.isoformat() if until else None}


@app.delete("/admin/promo")
def admin_end_promo(who=Depends(admin.admin_profile)):
    set_promo(None)
    log.info("admin %s ended the free offer", who.get("email"))
    return {"until": None}


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
