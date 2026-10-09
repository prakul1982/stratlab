"""StratLab API."""
import base64
import binascii
from concurrent.futures import ThreadPoolExecutor, wait as wait_all
import json
import math
import logging
from html import escape as html_escape
import re
import secrets
import sys
import threading
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from kiteconnect import exceptions as kite_exc
from pydantic import ValidationError
from razorpay import errors as rz_errors
from razorpay.errors import SignatureVerificationError

from . import holdings, holdings_file, instrument_kinds, money_calendar, tax_export, tax_lots, tax_total
from . import money_mf
from . import money_mf_nav
from . import money_mf_ter
from . import money_mf_behaviour
from . import sip_test
from . import fixed_income
from . import loan_check
from . import money_advance_tax, money_routes
from . import journal_routes
from . import user_data
from .connect import routes as connect_routes, sync as connect_sync, jobs as connect_jobs, kite_user as connect_kite, redact as connect_redact
from . import chart_routes
from . import drawings_routes
from . import market_store, storage
from . import official_close
from . import money_itr, money_us_routes
from . import rules, rules_watch
from . import suggest
from . import admin, audit, compute, invoices, pricing, basket, platform_check, billing, checklist, db, deck, deepdive, fixtures, importer, industry, investor, report_card, universes
from .ai_providers import health as ai_health
from . import ai_admin, ai_providers
from . import ai_writer
from .ai_writer import AIBusy, AIError, _anthropic, _gemini, ask_json, write_strategy
from . import alerts
from .auth import current_profile
from .config import api_docs_enabled, settings
from .branding import public_text
from .errors import report
from .responses import err, ok
from .guard import Guard, HeavyGate
from . import research
from .engine import walkforward
from .data import DataError, Registry
from .data import calendar as trading_calendar
from .intel import routes as research_routes
from .intel.company import Research, at_live_price
from .intel.net import TTLCache
from .intel import filings, sec
from .intel.sec import SEC
from .intel.net import SourceError
from .docs import Docs
from .intel.screener import summary as screener_summary
from .kite_auto import AutoLogin, AutoLoginError, configured as auto_login_configured, restart_process
from .kite_service import bse_only_rows, IST, KiteNotReady, KiteService, TickHub
from .live import LimitError, LiveManager, describe, needs_fno, needs_indicators
from .options import charges as opt_charges, greeks as opt_greeks, importer as opt_importer, strikes as opt_strikes
from .options.data import OptionsData, freeze as freeze_limit
from .options.engine import fill_price
from .options.session import stopped_snapshot as options_stopped
from .options.recorder import Recorder, parse_targets
from . import breadth, breadth_live, redflags, redflags_routes, scan_presets
from . import plan_interest
from . import email_kit
from . import mail_pages
from . import ask, company_cards, daily_report, deals, first_steps, ideas, invite_rewards, library, lifecycle, mail_tokens, newsletter_prefs, public, push, referrals, risk, rotation, scan, screens, stock_alerts, stock_pages, weekly
from .newsletter import job as news
from . import results as results_calendar
from . import corp_actions
from . import surveillance
from . import etf_nav
from . import vix
from . import biz_updates, library_seed, shareholders
from . import positioning
from . import fo_changes_routes
from . import closing_auction
from . import replay_routes, signals_routes
from . import market_events_routes
from . import mcp_server
from . import mtf, slb, stock_desks, stock_futures     # the per-stock market desks: futures, lending, margin funding
from .models import (ReferralReq, ShareReq, GroupLiveReq, OptionStartReq, OptGreeksReq, OptRollReq, HoldingsImportReq, HoldingsReq)
from .models import BreadthAlertReq, DeleteMyDataReq
from .models import CorpActionReq, TaxFmvReq, TaxImportReq, TaxInputsReq
from .models import (AdminPlanReq, AIReq, EmailPrefsReq, FirstStepsReq, NewsletterReq, OnboardingReq, AuditReq, MarketAuditReq, PricesReq, SellerReq, BillingDetailsReq, HolidaysReq, ModerateReq, PromoReq, ReportReq, ScanAlertReq, ScanReq, ScreenRunReq, ScreenSaveReq, StockAlertReq, IdeasReq, LibraryReq, PlanInterestReq, PrefsReq, PushReq, ImportReq, AlertsReq, ExperimentReq, LiveStartReq, NotebookReq, SaveStrategyReq,
                     Strategy, SubscribeReq, VerifyReq, ViewAsReq)
from .plans import holdings_limit
from . import money_networth
from .plans import networth_items
from .plans import FEATURE_PLAN, PLANS, allows, offer_state, promo_active, promo_until, set_promo, group_size, has_fno, has_indicators, plan_info, public_plans, trial_state
from .plans import stock_alerts as stock_alert_limit
from .plans import access_plan, ai_reads_per_day, bigger_plan, free_basic_until, screens as screens_limit
from .plans import decks as decks_limit, deepdives as deepdives_limit, payments_live  # noqa: F401  (tests set main.payments_live)

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
    steps = [("company list", lambda: isin_list()),         # full names and ISINs, for search by name
             ("instruments", lambda: kite.ready() and kite.search("RELIANCE", False, 1)),
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
    from .plans import plan_of
    return allows(plan_of(profile), "scans") and bool(alerts.jobs_for(profile, "", ""))


def alert_quotes(region: str, syms: list[str]) -> dict:
    """Quotes for a batch of stocks: one broker call for India when the feed is up, else the research quotes."""
    if region == "IN" and kite.ready():
        try:
            return kite.quote(syms)
        except Exception:
            pass
    return research_hub.quotes(region, syms)


def alert_bars(region: str, sym: str) -> list[dict]:
    """Daily candles (shared with the scans' cache) for the alerts on moving averages, RSI, Stage and 52-week levels."""
    ids, _ = universes.resolve(markets, region, [{"symbol": sym}])
    return scan._bars(markets, ids[0]) if ids else []


def _alert_limit(profile: dict) -> int:
    from .plans import plan_of
    return stock_alert_limit(plan_of(profile))


ALERT_FEATURE = {"etfgap": "etf_gaps", "bizupdate": "biz_updates", "mwpl": "stock_futures", "mtf": "mtf"}     # kinds of alert on a paid plan


def _alert_kind_ok(profile: dict, kind: str) -> bool:
    """Alerts on an ETF's price against its NAV, on business updates, on MWPL use and on margin funding are Basic and up;
    after a downgrade they wait."""
    from .plans import plan_of
    return kind not in ALERT_FEATURE or allows(plan_of(profile), ALERT_FEATURE[kind])


stock_checker = stock_alerts.Checker(lambda r, s: alert_quotes(r, s), lambda r, s: alert_bars(r, s), _alert_limit,
                                     gaps=lambda s, p: etf_nav.gap_now(s, p), kind_ok=_alert_kind_ok)
scan_alerts_job = scan.Alerts(markets, notify=lambda p, subject, text, url: alerts.notify(p, subject, text, url=url),
                              can_alert=_scan_alert_ok, checks=[lambda now: stock_checker.tick(now)])


def _filing_alert_ok(profile: dict) -> bool:
    from .plans import plan_of
    return allows(plan_of(profile), "filings") and bool(alerts.jobs_for(profile, "", ""))


filings_feed = filings.IndiaFilings(filings.NSEFilings(), filings.BSEFilings(), lambda s: bse_code(s), lambda s: bse_twin(s))
filing_alerts_job = filings.Alerts(filings_feed, notify=lambda p, subject, text, url: alerts.notify(p, subject, text, url=url),
                                   can_alert=_filing_alert_ok)
kite.on_invalid = lambda msg: auto_login._alert("StratLab: " + msg)
newsletter_job = news.Job("newsletters")      # its status is kept for Admin → Data and jobs
# the results calendar reads the feeds at call time, so the tests' fakes (and sec_feed, made further down) are used
deals_job = deals.Job(lambda: filings_feed, lambda rows, now: stock_alerts.fire_events(rows, now, _alert_limit))
results_job = results_calendar.Job(lambda: {"in": filings_feed, "us": research_hub.finnhub, "sec": sec_feed})
# corporate actions: the exchange's list for India, the price history's dividends and splits for the US
money_calendar_job = money_calendar.Job()
corp_job = corp_actions.Job(lambda: {"in": filings_feed, "us": research_hub.yahoo})
# red-flag filings of every company (India: the exchange's list; US: the SEC's 8-K items) and US 13D/13G holders, read each evening
redflags_runner = redflags.Runner(lambda: {"in": filings_feed, "sec": sec_feed})
redflags_job = redflags.Job(redflags_runner)
# the exchange's surveillance lists, twice a trading day; stocks entering or leaving one fire the stock alerts
surv_job = surveillance.Job(lambda: filings_feed, lambda changes, now: stock_alerts.fire_events(
    [{**c, "kind": "surveillance"} for c in changes], now, _alert_limit))
lifecycle_job = lifecycle.Job()
advance_tax_job = money_advance_tax.Job()       # advance tax reminders, for those who turned them on
invite_job = invite_rewards.Job()
# derivatives positioning: the exchange's evening files, read through the exchange client (tests swap filings_feed)
positioning_runner = positioning.Runner(lambda: filings_feed)
positioning_job = positioning.Job(positioning_runner)
etf_nav.setup(lambda: filings_feed)              # ETF prices against their NAV: the exchange's ETF list


def _exchange_files():
    from . import exchange_days            # imported here: it loads the newsletter job, which main loads first
    return exchange_days.files_of(lambda: filings_feed, pace=0)


# one official close per Indian symbol across the public pages, the screens and ETF vs NAV (R7O-004, R7O-007)
official_close.setup(_exchange_files, lambda syms: kite.quote(syms) if kite.ready() else {},
                     all_quotes_fn=lambda: kite.day_quotes() if kite.ready() else {})
# ...and in every daily candle read from the broker: charts, scans, briefs, My Stocks, alerts, backtests (R8B-001)
kite.day_close = official_close.history_close
etf_job = etf_nav.Job(lambda: filings_feed)
closing_auction.setup(lambda: filings_feed)      # the closing auction desk: the exchange's CAS data
closing_auction_job = closing_auction.Job(lambda: filings_feed)
vix.setup(lambda: filings_feed)                  # India VIX: the exchange's index list, its chart and history
vix.use_options(lambda: options_data)
vix_job = vix.Job(lambda: filings_feed)
rules_watch_job = rules_watch.Job(lambda: filings_feed, lambda subject, text: tell_admins(subject, text))   # official rate sources, daily
# monthly and quarterly business updates read into numbers, and named holders above 1% (the exchange's filings)
biz_updates.setup(lambda: filings_feed, lambda: deep_docs, lambda: (_gemini, _anthropic))
biz_job = biz_updates.Job(lambda rows, now: stock_alerts.fire_events(rows, now, _alert_limit, kind_ok=_alert_kind_ok),
                          biz_updates.alert_symbols)
shareholders.setup(lambda: filings_feed)
holders_job = shareholders.Job(lambda: filings_feed, notify=lambda p, subject, text, url: alerts.notify(p, subject, text, url=url),
                               can_alert=lambda p: allows(access_plan(p), "holders") and bool(alerts.jobs_for(p, "", "")))


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
    deals_job.start()
    threading.Thread(target=trading_calendar.warm, daemon=True).start()   # ~2 s, kept off the first request
    threading.Thread(target=money_mf_nav.keep_fresh, daemon=True, name="mf-nav").start()   # the mutual fund NAV file, read ahead of the pages (R9P-008)
    threading.Thread(target=warm_caches, daemon=True).start()
    threading.Thread(target=holiday_job, daemon=True, name="holidays").start()
    threading.Thread(target=rates_job, daemon=True, name="fx-rates").start()
    threading.Thread(target=platform_job, daemon=True, name="platform-check").start()
    threading.Thread(target=weekly_job, daemon=True, name="weekly-summary").start()
    connect_job.start()                  # daily Interactive Brokers read; the statement inbox's 40-day reminder
    newsletter_job.start()
    results_job.start()
    corp_job.start()
    redflags_job.start()
    money_calendar_job.start()
    surv_job.start()
    lifecycle_job.start()
    advance_tax_job.start()
    invite_job.start()
    rules_watch_job.start()
    positioning_job.start()
    stock_desks.job.start()                     # stock futures, lending fees and margin funding: the evening files
    fo_changes_routes.job.start()               # F&O contract changes, twice a trading day
    market_events_routes.job.start()            # market events calendar, twice a day, and its reminders
    networth_job.start()
    threading.Thread(target=market_audit.loop, daemon=True, name="market-audit").start()
    threading.Thread(target=market_audit_us.loop, daemon=True, name="market-audit-us").start()
    threading.Thread(target=stock_list_job, daemon=True, name="stock-list").start()
    threading.Thread(target=screen_indexer.loop, daemon=True, name="screens-index").start()
    threading.Thread(target=stock_price_refresh_job, daemon=True, name="stock-prices").start()   # pages follow each close
    screen_job.start()
    breadth_job.start()
    threading.Thread(target=library_seed_once, daemon=True, name="library-seed-once").start()
    breadth_live_job.start()          # breadth every ~15 minutes while the Indian market is open
    etf_job.start()
    closing_auction_job.start()       # the closing auction, every 30 s from 15:14 to 15:40 on trading days
    vix_job.start()
    biz_job.start()
    holders_job.start()
    ai_providers.job.start()          # measures the AI models every 6 hours
    yield


log = logging.getLogger("stratlab")
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=settings.SENTRY_DSN, environment=settings.SENTRY_ENV, traces_sample_rate=0, send_default_pii=False)
    except Exception as e:
        print("Sentry not started:", e)
_docs = api_docs_enabled()
app = FastAPI(title="StratLab API", lifespan=lifespan, docs_url="/docs" if _docs else None, redoc_url="/redoc" if _docs else None,
              openapi_url="/openapi.json" if _docs else None)
research_routes.setup(research_hub, _gemini, _anthropic)
research_routes.corp_sources = corp_job.sources          # a US company page's dividend yield from its listed payments
app.include_router(research_routes.router)
app.include_router(money_mf.router)          # /money/mutual-funds
app.include_router(money_mf_ter.router)      # /money/mutual-funds/costs
app.include_router(money_mf_ter.admin_router)  # /admin/ter
app.include_router(money_mf_behaviour.router)  # /money/mutual-funds/behaviour
app.include_router(sip_test.router)            # /invest/sip-test
app.include_router(fixed_income.router)        # /money/rates
app.include_router(loan_check.router)          # /money/loans/check
app.include_router(money_routes.router)
app.include_router(money_calendar.router)
app.include_router(journal_routes.router)     # /trade/journal
app.include_router(connect_routes.router)     # /connect: statement inbox, Zerodha login, IBKR, EPF/NPS/AIS uploads
app.include_router(connect_routes.hook_router)  # /inbound/email/<provider>: the mail service's webhook (no sign-in, signed)
app.include_router(fo_changes_routes.router)  # /trade/fo-changes
app.include_router(replay_routes.router)      # /trade/replay: chart replay practice
app.include_router(signals_routes.router)     # /trade/signals: forward-testing outside signals
app.include_router(signals_routes.hook_router)  # /hooks/signal/<token>: the signal webhook (no sign-in)
app.include_router(market_events_routes.router)  # /trade/events
from . import email_previews as _email_previews  # noqa: E402
app.include_router(_email_previews.router)       # /admin/email-previews
from . import admin_jobs as _admin_jobs  # noqa: E402
app.include_router(_admin_jobs.router)           # /admin/jobs: every background job, for Admin -> Data and jobs
app.include_router(chart_routes.router)       # /chart: candles and drawings for the price chart
app.include_router(drawings_routes.router)    # /me/drawings/{region}/{symbol}: drawings and layout saved per user
app.include_router(money_us_routes.router)     # /money/us-tax
app.include_router(money_itr.router)           # /money/itr
app.include_router(etf_nav.router)             # /invest/etf-gaps
app.include_router(closing_auction.router)     # /trade/closing-auction
app.include_router(vix.router)                 # /trade/vix
app.include_router(biz_updates.router)         # /research/business-updates, /invest/business-updates
app.include_router(shareholders.router)        # /research/holders, /invest/holders
app.include_router(redflags_routes.router)     # /research/redflags, /research/holders-us
app.include_router(stock_futures.router)       # /trade/stock-futures
app.include_router(slb.router)                 # /invest/stock-lending
app.include_router(mtf.router)                 # /invest/margin-funding
app.include_router(stock_desks.admin_router)   # /admin/stock-desks
app.include_router(ai_admin.router)            # /admin/ai: the AI panel
app.include_router(mcp_server.router)          # /mcp and /me/assistant: StratLab in your AI assistant


RECENT_ERRORS: list[dict] = []   # the last crashes, shown on the admin page
# when this server started, in India time like each error's "at": errors kept from before it are told apart (R7O-006)
SERVER_STARTED_AT = datetime.now(IST).isoformat()


@app.middleware("http")
async def unexpected_errors(request: Request, call_next):
    """Turn crashes into a normal JSON error. Registered before CORS, so the browser can still read it."""
    try:
        return await call_next(request)
    except Exception as e:
        print(connect_redact.mask(traceback.format_exc()), file=sys.stderr)       # a library's error can carry a URL with a key in it
        ref = secrets.token_hex(3).upper()
        tb = traceback.extract_tb(e.__traceback__)
        own = [f for f in tb if "site-packages" not in f.filename and f.name != "unexpected_errors"] or tb   # the deepest frame of our own code
        where = f"{own[-1].filename.rsplit('/', 1)[-1]}:{own[-1].lineno} in {own[-1].name}" if own else ""
        RECENT_ERRORS.append({"ref": ref, "at": datetime.now(IST).isoformat(), "method": request.method,
                              "path": request.url.path, "error": connect_redact.mask(f"{type(e).__name__}: {str(e)[:300]}"), "where": where})
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


app.add_middleware(db.SettingsMemo)   # innermost: each request reads a setting from the database once
app.add_middleware(HeavyGate)   # inside the guard: heavy work takes turns, ordinary pages don't wait behind it
app.add_middleware(Guard)   # size cap, rate limit, security headers; inside CORS so its replies stay readable
app.add_middleware(CORSMiddleware, allow_origins=settings.FRONTEND_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"], max_age=7200)   # a browser asks before each call only every 2 h, not 10 min
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=6)   # outermost: JSON and pages go compressed (a chart is 5x smaller)


# ---------- helpers ----------
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


def month_start_iso() -> str:
    return datetime.now(IST).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def backtests_used(profile) -> int:
    return db.count_usage(profile["id"], "backtest", month_start_iso())


def all_indicators(profile) -> bool:
    """Every indicator, not just price, SMA, EMA and RSI (Basic and up)."""
    return has_indicators(profile["_plan"])


def fno(profile) -> bool:
    """Indian futures and options (Pro)."""
    return has_fno(profile["_plan"])


def lift(plan: str, key: str, what: str) -> str:
    """The end of an upgrade message: which plan lifts a count limit, and to what (" Basic gives 100 a month.")."""
    nxt = bigger_plan(plan, key)
    if not nxt:
        return ""
    cap = PLANS[nxt.lower()][key]
    return f" {nxt} has no limit on {what}." if cap is None else f" {nxt} gives {cap}."


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
    if not fno(profile) and needs_fno(inst):
        upgrade("Indian F&O is on the Pro plan.")
    if not all_indicators(profile) and needs_indicators(strategy):
        upgrade("This strategy uses indicators beyond price, SMA, EMA and RSI (MACD, Bollinger Bands, VWAP, Supertrend, ADX, "
                "Stochastic, Donchian and more). Basic unlocks all of them.")


@app.exception_handler(KiteNotReady)
def _kite_not_ready(request, exc):
    return JSONResponse(status_code=503, content={"detail": {"code": "data_offline", "message": public_text(str(exc))}})


@app.exception_handler(research.ResearchError)
def _research_error(request, exc):
    return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code, "message": public_text(exc.message)}})


@app.exception_handler(DataError)
def _data_error(request, exc):
    return JSONResponse(status_code=502, content={"detail": {"code": "data_error", "message": public_text(str(exc))}})


def _finite_json(v):
    """A value safe to send as JSON: NaN and ±Infinity (which Python's JSON reader accepts in a request body) become
    text, so echoing a bad input back in a 422 can't crash the reply."""
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    if isinstance(v, dict):
        return {k: _finite_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_finite_json(x) for x in v]
    return v


@app.exception_handler(RequestValidationError)
def _invalid_request(request, exc):
    """FastAPI's own 422, with any NaN or Infinity in the echoed input made safe to send."""
    return JSONResponse(status_code=422, content={"detail": _finite_json(jsonable_encoder(exc.errors()))})


@app.exception_handler(kite_exc.KiteException)
def _kite_error(request, exc):
    print("market data request failed:", exc)
    return JSONResponse(status_code=502, content={"detail": {"code": "data_error",
                        "message": "The market data request failed. Try again in a moment."}})


# ---------- account ----------
@app.get("/health")
def health():
    """Public: only whether things are up. Provider details are on the admin page.
    `data_online`: the Indian market data login is valid, so Indian prices (quotes, charts, company pages) are read live.
    `feed`: the streaming tick connection that only live paper-trading sessions on Indian instruments use. It opens with
    the first such session and stays shut while there is none ("idle"), which says nothing about prices elsewhere;
    "disconnected" means it was opened and has dropped. `feed_connected` is kept for monitors that read it."""
    return {"ok": True, "data_online": kite.ready(), "feed_connected": hub.connected,
            "feed": "connected" if hub.connected else "disconnected" if hub.started else "idle",
            "ai_configured": any(p["in_use"] for p in ai_health())}


@app.get("/plans")
def plans():
    return PLANS


@app.get("/pricing")
def prices():
    """Prices in every currency StratLab shows, which currency each is charged in, country → currency, and the offer
    in force today (payments on or not, the launch offer), so the public pages say what the app does."""
    # `invoice.gst`: invoices carry GST (a GSTIN is set in Admin → Money), so the pages only promise a GST invoice then (R7M-001)
    return {**pricing.public(), "offer": offer_state(), "invoice": {"gst": invoices.gst_registered()}}


def fx_rate(code: str) -> float:
    """Rupees per unit of a currency, from the market data source (e.g. EURINR=X). A currency the source has no rupee
    pair for (SAR, NOK, QAR: "Couldn't read" in Admin, R7O-008) goes through the dollar: rupees per dollar over its
    units per dollar ("SAR=X"); for a currency pegged to the dollar, the peg when that read fails too."""
    return pricing.cross_rate(code, lambda pair: research_hub.yahoo.meta(pair).get("price"))


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
    try:
        lifecycle.seen(profile)       # remembers the visit; welcomes a brand-new account
    except Exception as e:
        print("lifecycle visit failed:", str(e)[:160])
    plan = profile["_plan"]
    # the site owner's "View as": every plan field below reads as that plan (no launch offer, no stored plan); the real
    # plan and billing are untouched in the database, and billing changes are refused while it is on
    seen = profile.get("_view_as") if profile.get("_view_as") in PLANS else None
    paid = seen or (profile.get("_paid_plan", plan) if profile.get("_paid_plan", plan) in PLANS else "free")
    info = plan_info(plan)
    reads_today = _usage_pool.submit(research_routes.ai_reads_today, profile)
    used = month_usage(profile["id"], ("backtest", "ai", "deepdive", "deck"))
    reads_cap = research_routes.ai_cap(profile)
    return ok({
        "id": profile["id"], "email": profile.get("email"),
        "plan": plan, "plan_info": info, "paid_plan": seen or profile.get("_paid_plan", plan),
        "view_as": seen,
        "promo": {"until": until.isoformat()} if not seen and (until := promo_until()) and promo_active() else None,
        "free_basic_until": fb.isoformat() if not seen and profile.get("_paid_plan") == "free" and (fb := free_basic_until(profile)) else None,
        "billing": ({"subscribed_plan": None if seen == "free" else seen, "status": None if seen == "free" else "active",
                     "renews_or_ends": None, "cancel_at_period_end": False, "given_by_owner": seen != "free"} if seen else
                    {"subscribed_plan": profile.get("plan"), "status": profile.get("plan_status"),
                     "renews_or_ends": profile.get("current_period_end"),
                     "cancel_at_period_end": bool(profile.get("cancel_at_period_end")),
                     # a paid plan the site owner gave by hand (Admin → Change plan): nothing renews and nothing to cancel
                     "given_by_owner": profile.get("_paid_plan", plan) != "free" and not profile.get("razorpay_subscription_id")}),
        "signed_in_with": profile.get("_signed_in_with"),
        "usage": {"backtests_used": used["backtest"], "backtests_limit": info["backtests_per_month"],
                  "ai_used": used["ai"], "ai_limit": info["ai_builds_per_month"],
                  "deepdive_used": used["deepdive"], "deepdive_limit": info["deepdives_per_month"],
                  "deck_used": used["deck"], "deck_limit": info["decks_per_month"],
                  # the plan's own limits (what the Plans page lists), and why they're lifted now when they are
                  "deepdive_plan_limit": PLANS[paid]["deepdives_per_month"], "deck_plan_limit": PLANS[paid]["decks_per_month"],
                  # fresh AI reads today against the person's daily cap (None: no cap), said on Account (R8O-002)
                  "ai_reads_today": reads_today.result(), "ai_reads_limit": reads_cap,
                  "ai_reads_cap_for": "admin" if admin.is_admin(profile) else None,
                  # the viewed plan's own cap, so an admin's "View as Free or Basic" can say "35 of 60 (not enforced for you)" (R9P-005)
                  "ai_reads_plan_limit": ai_reads_per_day(paid),
                  # the daily safety cap on unlimited AI builds (Pro's), said beside the month's count like the Plans card
                  "ai_builds_per_day": AI_BUILDS_PER_DAY if info["ai_builds_per_month"] is None else None,
                  "lifted_by": "the launch offer" if promo_active() and not seen else None},
        "trial": trial_state(profile) if plan == "free" else None,
        "live_running": len(manager.user_running(profile["id"])), "live_limit": info["live_limit"],
        "alerts": {"channels": alerts.ready_channels(), "enabled": bool(profile.get("alerts_enabled")), "telegram_chat_id": profile.get("telegram_chat_id"),
                   "email": profile.get("alert_email"), "email_off": not alerts.alert_emails_on(profile["id"]), "daily_report": daily_report.wants_report(db, profile["id"])},
        "prefs": {k: prefs_of(profile["id"]).get(k) for k in PREF_KEYS},
        "data_online": kite.ready(),
        "data_note": data_note(),
        "billing_enabled": billing.enabled(), "yearly_enabled": billing.yearly_enabled(), "plans": public_plans(),
        "offer": offer_state(promo=not seen),
        "onboarding": onboarding_of(profile["id"]),
        "established": established_of(profile["id"]),
        "is_admin": admin.is_admin(profile),
    })


_usage_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="usage-counts")


def month_usage(uid: str, kinds: tuple[str, ...]) -> dict[str, int]:
    """This month's count of each kind of use, the counts asked for at the same time: every page opens with /me, and
    one database round trip after another made it the slowest call of the first load."""
    since = month_start_iso()
    jobs = {k: _usage_pool.submit(db.count_usage, uid, k, since) for k in kinds}
    return {k: f.result() for k, f in jobs.items()}


def data_note() -> dict | None:
    """While Indian data is offline: whether India is closed today anyway, and when data comes back by itself."""
    if kite.ready():
        return None
    now = datetime.now(IST)
    today = now.date()
    closed = "weekend" if today.weekday() >= 5 else "holiday" if trading_calendar.is_holiday("IN", today) else None
    back = auto_login.next_login(now)
    return {"closed": closed, "back_at": back.isoformat() if back else None}


PREF_KEYS = ("level", "focus", "space")


def prefs_of(uid: str) -> dict:
    try:
        p = json.loads(db.get_setting(daily_report.PREFS + uid) or "{}")
        return p if isinstance(p, dict) else {}
    except Exception:
        return {}


@app.get("/me/export")
def export_my_data(profile=Depends(current_profile)):
    """Your own copy of everything StratLab keeps for you, as one JSON file (no tokens or passwords)."""
    throttle(profile, "export-my-data", 10, 3600, "Too many downloads. Try again in an hour.")
    body = json.dumps(user_data.export(profile), ensure_ascii=False, indent=1, default=str)
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="stratlab-my-data.json"', "Cache-Control": "no-store"})


@app.post("/me/delete-data")
def delete_my_data(req: DeleteMyDataReq, profile=Depends(current_profile)):
    """Erase your own app data (the same steps as Admin's "Delete this user's data"), once the account's email is typed
    in to confirm. The sign-in account and the plan and payment records stay: closing the sign-in account is done by
    the site owner on request, and payment records are kept as the law asks."""
    email = (profile.get("email") or "").strip().lower()
    if not email or req.confirm.strip().lower() != email:
        err(400, "confirm_mismatch", "Type your account's email exactly to confirm.")
    throttle(profile, "delete-my-data", 5, 3600, "Too many tries. Try again in an hour.")
    out = user_data.erase(profile["id"])
    log.info("user %s erased their own app data: %d areas done, %d failed", profile["id"], len(out["done"]), len(out["failed"]))
    return {"ok": not out["failed"], **out}


@app.put("/me/prefs")
def set_prefs(req: PrefsReq, profile=Depends(current_profile)):
    """Experience level, what the user came for (trading, investing, their money or all of it) and the space last picked
    in the menu: they only change defaults (what's expanded, what's suggested first, which menu shows), never what's
    allowed."""
    given = {k: getattr(req, k) for k in PREF_KEYS}
    prefs = {**prefs_of(profile["id"]), **{k: v for k, v in given.items() if v}}
    db.set_setting(daily_report.PREFS + profile["id"], json.dumps(prefs))
    return {"prefs": {k: prefs.get(k) for k in PREF_KEYS}}


@app.get("/me/plan-interest")
def my_plan_interest(profile=Depends(current_profile)):
    """Whether this person asked to be told when paid plans open."""
    return plan_interest.get(profile["id"])


@app.put("/me/plan-interest")
def ask_plan_interest(req: PlanInterestReq, profile=Depends(current_profile)):
    """"Tell me when plans open": put the person on the list (asking twice changes nothing)."""
    return plan_interest.add(profile["id"], req.source)


@app.delete("/me/plan-interest")
def drop_plan_interest(profile=Depends(current_profile)):
    return plan_interest.remove(profile["id"])


def onboarding_of(uid: str) -> dict:
    """Where this account is in the first-run guide, kept on the account (not the browser), so it shows once per person
    rather than once per device: `welcome` when the "What brings you here?" question was answered or closed, `tour`
    "done" or "skipped" once the short tour was finished or closed."""
    o = prefs_of(uid).get("onboarding")
    o = o if isinstance(o, dict) else {}
    return {"welcome": o.get("welcome") if isinstance(o.get("welcome"), str) else None,
            "tour": o.get("tour") if o.get("tour") in ("done", "skipped") else None}


def established_of(uid: str) -> bool:
    """The account already has holdings, notebooks, a paper session or a watchlist, so the "What brings you here?" question
    is not asked of it. Only looked up while the question is still pending (it costs a few reads); otherwise false."""
    prefs = prefs_of(uid)
    o = prefs.get("onboarding")
    if isinstance(o, dict) and o.get("welcome"):
        return False
    if prefs.get("level") and prefs.get("focus"):
        return False
    return first_steps.has_activity(uid)


@app.put("/me/onboarding")
def set_onboarding(req: OnboardingReq, profile=Depends(current_profile)):
    """Remember that the welcome question or the tour was seen. Only moves forward: a tour that was done stays done."""
    prefs = prefs_of(profile["id"])
    cur = prefs.get("onboarding") if isinstance(prefs.get("onboarding"), dict) else {}
    nxt = dict(cur)
    if req.welcome and not cur.get("welcome"):
        nxt["welcome"] = db.now_iso()
    if req.tour and cur.get("tour") != "done":
        nxt["tour"] = req.tour
    if nxt != cur:
        db.set_setting(daily_report.PREFS + profile["id"], json.dumps({**prefs, "onboarding": nxt}))
    return {"onboarding": onboarding_of(profile["id"])}


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
    if req.alert_email and not alerts.alert_emails_on(profile["id"]):
        alerts.set_alert_emails(profile["id"], True)       # saving an address again turns alert emails back on after an unsubscribe
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


# ---------- newsletter email: confirming the address, unsubscribing from a link ----------
def mail_page(title: str, text: str, status: int = 200) -> HTMLResponse:
    """A small page for links opened from an email, in the site's look (R7M-004)."""
    return HTMLResponse(status_code=status, content=mail_pages.notice(title, text))


def _unsubscribe(t: str, act: bool = True) -> str | None:
    """The newsletter a link names (turned off when `act`); None for a bad link."""
    got = mail_tokens.read(t, "unsubscribe")
    if not got or got[1] not in alerts.NEWSLETTER_NAMES:
        return None
    uid, what = got
    if act and what in ("tips", "all"):
        lifecycle.set_tips(uid, False)
    if act and what in ("screens", "all"):
        screens.mute(uid)
    if act and what in ("advance_tax", "all"):
        money_advance_tax.set_remind(uid, False)
    if act and what == alerts.ALERT_EMAILS:
        alerts.set_alert_emails(uid, False)
    if act and what not in ("tips", "screens", "advance_tax", alerts.ALERT_EMAILS):
        newsletter_prefs.set(uid, {k: "off" for k in newsletter_prefs.KEYS} if what == "all" else {what: "off"})
    return alerts.NEWSLETTER_NAMES[what]


WHERE_EMAILS = "in Settings → Notifications"       # where a reader changes their emails (the real path, R7M-004)


@app.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe_page(t: str = ""):
    """Asks before unsubscribing: mail scanners open every link in an email, and shouldn't unsubscribe anyone."""
    if t == email_kit.PREVIEW_TOKEN:          # the link in Admin → Email previews: what it does for a reader, nothing changed
        return mail_page("Unsubscribe (preview)", "In a real email this link opens a page with one Unsubscribe button: no "
                         "sign-in, and that one email type is turned off. This is a preview, so nothing was changed.")
    name = _unsubscribe(t, act=False)
    if not name:
        return mail_page("This link doesn't work", f"It may be incomplete. You can turn emails off any time {WHERE_EMAILS}.", 400)
    return HTMLResponse(content=mail_pages.ask(f"Unsubscribe from {name}?", f"/unsubscribe?t={t}&page=1", "Unsubscribe"))


@app.post("/unsubscribe")
def unsubscribe_one_click(t: str = "", page: int = 0):
    """Mail apps' own unsubscribe button (RFC 8058 one-click), and the button on the page above."""
    name = _unsubscribe(t)
    if page:
        return (mail_page("Unsubscribed", f"You're unsubscribed from {name}. Change this any time {WHERE_EMAILS}.") if name
                else mail_page("This link doesn't work", f"It may be incomplete. You can turn emails off any time {WHERE_EMAILS}.", 400))
    if not name:
        return Response("This unsubscribe link isn't valid.", status_code=400, media_type="text/plain")
    return Response("Unsubscribed.", media_type="text/plain")


@app.post("/me/email/confirm")
def send_email_confirmation(profile=Depends(current_profile)):
    """Email a link that confirms the address newsletters would go to."""
    to = alerts.newsletter_email(profile)
    if not to:
        err(400, "no_email", "Add an email address in Account first.")
    if alerts.email_confirmed(profile):
        return {"confirmed": True, "sent_to": None}
    if not alerts.email_ready():
        err(503, "email_off", "Email isn't set up on the server yet.")
    throttle(profile, "email_confirm", 5, 3600, "You've asked for 5 confirmation emails this hour. Try again later.")
    link = alerts.confirm_url(profile["id"], to)
    from . import email_previews as previews
    try:
        _, html, text = previews.confirm_email(to, link)
        alerts.send_email(to, "Confirm your StratLab email", text, html=html)
    except Exception as e:
        err(502, "email_failed", f"The email couldn't be sent: {public_text(str(e))[:200]}")
    return {"confirmed": False, "sent_to": to}


def _confirm_link_bad() -> HTMLResponse:
    return mail_page("This link doesn't work", f"It may have expired (links work for 3 days). Ask for a new one {WHERE_EMAILS}.", 400)


@app.get("/email/confirm", response_class=HTMLResponse)
def confirm_email_page(t: str = ""):
    """Asks before confirming: mail scanners open every link, and shouldn't sign anyone up for newsletters."""
    got = mail_tokens.read(t, "confirm")
    if not got or not got[1]:
        return _confirm_link_bad()
    return HTMLResponse(content=mail_pages.ask(f"Send StratLab newsletters to {got[1]}?", f"/email/confirm?t={t}", "Confirm my email",
                                               "If you didn't ask for this, close this page.", manage=False))


@app.post("/email/confirm", response_class=HTMLResponse)
def confirm_email(t: str = ""):
    got = mail_tokens.read(t, "confirm")
    if not got or not got[1]:
        return _confirm_link_bad()
    uid, address = got
    db.set_setting(alerts.CONFIRMED + uid, address.strip().lower())
    return mail_page("Email confirmed", f"Newsletters you choose {WHERE_EMAILS} will go to {address}.")


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
    return markets.search(q, market.upper() if market else None, allow_fno=fno(profile))


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
        err(429, "ai_limit", f"You've used all {limit} AI builds this month." + lift(profile["_plan"], "ai_builds_per_month", "AI builds"))
    since = (datetime.now(IST) - timedelta(days=1)).isoformat()
    # a safety cap on Pro's unlimited builds, said on Plans; the site's admins have none (R8O-002)
    if not admin.is_admin(profile) and db.count_usage(profile["id"], "ai", since) >= AI_BUILDS_PER_DAY:
        err(429, "ai_daily_limit", f"You've used the AI builder {AI_BUILDS_PER_DAY} times today. Try again tomorrow.")
    return used, limit


AI_BUILDS_PER_DAY = 200


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
        out = write_strategy(importer.ai_prompt(fmt, req.text), pro=all_indicators(profile))
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
        out = write_strategy(req.text, pro=all_indicators(profile))
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


money_mf.setup(throttle)


# ---------- backtests and notebooks ----------
def use_backtest(profile) -> int | None:
    """Check the monthly backtest limit before running one; returns the limit."""
    limit = PLANS[profile["_plan"]]["backtests_per_month"]
    if limit is not None and backtests_used(profile) >= limit:
        upgrade(f"You've used all {limit} backtests for this month." + lift(profile["_plan"], "backtests_per_month", "backtests"),
                "backtest_limit")
    return limit


def run_test(profile, strategy: Strategy, req) -> dict:
    if not strategy.entry:
        err(400, "no_entry_rules", "Add at least one buy rule first.")
    limit = use_backtest(profile)
    data = research.load(markets, strategy, req)
    check_features(profile, strategy, data["inst"])
    out = compute.run(strategy, data)                   # in a worker process: other pages stay quick meanwhile
    db.add_usage(profile["id"], "backtest")
    invite_rewards.safe_touch(profile, "backtest")
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
    invite_rewards.safe_touch(profile, "backtest")
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
    body = {k: nb.get(k) for k in ("kind", "question", "notes", "strategy", "instrument", "experiments", "summary", "pinned", "group", "gaps")}
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


def unique_name(profile, name: str) -> str:
    """A new notebook's name, numbered when another notebook already has it ("Ride the trend 2"), so two notebooks
    from the same template can be told apart in the sidebar."""
    name = (name or "Untitled notebook").strip()[:80]
    try:
        taken = {str(r.get("name") or "").strip().lower() for r in db.list_notebook_rows(profile["id"])}
    except Exception:
        return name
    if name.lower() not in taken:
        return name
    n = 2
    while f"{name} {n}".lower() in taken:
        n += 1
    return f"{name[:76]} {n}"


@app.post("/notebooks")
def create_notebook(req: NotebookReq, profile=Depends(current_profile)):
    strategy = req.strategy or Strategy(name=req.name or "Untitled notebook")
    nb = {"name": unique_name(profile, req.name or strategy.name), "question": req.question or "", "notes": req.notes or "",
          "strategy": strategy.model_dump(), "instrument": instrument_summary(req.instrument),
          "experiments": [], "summary": research.summary([])}
    if req.group is not None and not req.instrument:
        nb["group"] = group_body(req.group)     # e.g. "Backtest ST S2 on this group" from a scan
    if req.gaps is not None:
        nb["gaps"] = req.gaps.model_dump()      # the questions still open, there when the person comes back
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
    if req.gaps is not None:
        nb["gaps"] = req.gaps.model_dump()
    if req.clearGaps:
        nb.pop("gaps", None)
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
    if not row:
        err(404, "not_found", "Notebook not found.")
    for e in notebook_from_row(row).get("experiments") or []:
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
    defaulted = None
    if not req.bars and not group and not req.instrument and not (nb.get("instrument") or {}).get("id"):
        # nothing picked yet: test on the default instrument (the first one the market picker offers) and say so
        first = next(iter(markets.defaults()), None)
        if first is None:
            err(400, "no_instrument", "Pick an instrument or upload candles first.")
        nb["instrument"] = instrument_summary(first["id"])
        defaulted = first.get("symbol") or first["id"]
    same = research.unchanged(experiments, strategy, None if group else (nb.get("instrument") or {}).get("id"),
                              req.days, db.now_iso()) if not req.bars and not req.instrument else None
    if same is not None:
        err(409, "unchanged", f"Nothing has changed since v{same}: the same rules, market and period, already run "
            f"today. Its result stands, and no experiment was used. Change something to run a new one.")
    if group and not req.bars:
        rec, usage = run_group_test(profile, strategy, group, req, version)
        out = {"usage": usage}
    else:
        if not req.bars and not req.instrument:
            req.instrument = (nb.get("instrument") or {}).get("id")
        out = run_test(profile, strategy, req)
        rec = research.record(out, strategy, req.label, version, db.now_iso())
    if not req.label.strip():
        rec["label"] = research.describe_change(experiments[-1] if experiments else None, rec)
    experiments = research.slim((experiments + [rec])[-50:])
    nb["experiments"], nb["summary"] = experiments, research.summary(experiments)
    save_notebook(profile, nb)
    return ok({"experiment": rec, "usage": out["usage"], "summary": nb["summary"], "defaulted": defaulted,
               "instrument": nb.get("instrument") if defaulted else None})


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


# ---------- Stage 2 + Supertrend scans (Basic and up) ----------
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
    big = []
    for b in universes.BIG[region]:        # the groups worked out once a day: their size is what the last run checked
        doc = scan_presets.load(b["id"])
        big.append({"id": b["id"], "name": b["name"], "count": (doc or {}).get("checked", 0), "stored": True, "as_of": (doc or {}).get("as_of")})
    return {"sets": [{"id": "watchlist", "name": "Your watchlist", "count": len(scan.watchlist_members(profile["id"], region))}]
            + [{"id": p["id"], "name": p["name"], "count": p["count"]} for p in universes.presets(region)] + big,
            "alerts": scan.alert_on(profile["id"]), "template": scan.ST_S2, "fresh_days": scan.FRESH,
            "scans": scan_presets.listing(),
            "rotation_sets": [{"id": k, "name": v["name"]} for k, v in rotation.index_sets(region).items()]}


def _scan_names(region: str, symbols: list[str]) -> dict[str, dict]:
    """{symbol: {"name", "currency"}} for the rows of a stored scan: the S&P 500's list for the US, the instrument list for India."""
    out = {}
    if region == "US":
        names = universes.sp500_names()
        return {s: {"name": names.get(s), "currency": "USD"} for s in symbols}
    for s in symbols:
        inst = None
        try:
            inst = kite.equity(s)
        except Exception:
            pass
        out[s] = {"name": (inst or {}).get("name"), "currency": "INR"}
    return out


def _stored_scan(profile, region: str, group: str, preset: str, name: str) -> dict:
    """A preset's matches in a big group, from the daily run's stored answer: one read, no price requests."""
    got = scan_presets.stored_view(group, preset)
    if got is None or not got["checked"]:
        err(404, "not_stored", f"{name} hasn't been checked yet: it is read once a day after the market closes. Try a smaller group for now.")
    rows = with_nse_close(region, got["rows"][:SCAN_ROWS], "as_of", "chg")
    names = _scan_names(region, [r["symbol"] for r in rows])
    return {"rows": [{**r, **names.get(r["symbol"], {})} for r in rows], "matches": len(got["rows"]), "checked": got["checked"], "as_of": got["as_of"],
            "updated_at": got["at"], "missing": [], "problems": [], "stored": True}


SCAN_ROWS = 300       # the most rows one scan answer carries (the count of all matches is given beside them)
_nse_quotes = TTLCache(max_items=200)


def nse_quotes(symbols: list[str]) -> dict[str, dict]:
    """The exchange's quotes for Indian stocks (the company page's price), for up to 500 at once, kept a minute; none
    when the data login isn't ready or the call fails (the rows then keep their candle's close)."""
    syms = sorted({str(x).upper() for x in symbols if x})[:500]
    if not syms or not kite.ready():
        return {}
    key = tuple(syms)
    hit = _nse_quotes.get(key)
    if hit is not None:
        return hit
    try:
        got = kite.quote(syms) or {}
    except Exception as e:
        print("nse quotes:", str(e)[:120])
        got = {}
    _nse_quotes.set(key, got, 60)
    return got


def with_nse_close(region: str, rows: list[dict], day_key: str, change_key: str | None = None) -> list[dict]:
    """Indian rows with the company page's close (R6O-009); other markets as they are."""
    if region != "IN" or not rows:
        return rows
    from . import page_close
    return page_close.overlay(rows, nse_quotes([r.get("symbol") for r in rows]), day_key, change_key)


@app.post("/research/scan")
def run_scan(req: ScanReq, profile=Depends(current_profile)):
    """A trend scan over a group: the Stage 2 + Supertrend scan (fresh signals first), or one of the preset rule sets
    (52-week high breakout, golden cross, ...), each stock's match stated as a fact with its date. Never advice."""
    need(profile, "scans", "Trend scans")
    if req.scan != "st_s2" and req.scan not in scan_presets.BY_ID:
        err(404, "not_found", "That scan isn't available.")
    big = next((b for b in universes.BIG[req.region] if b["id"] == req.set), None)
    if big:
        preset = scan_presets.BY_ID[req.scan]
        out = _stored_scan(profile, req.region, big["id"], req.scan, big["name"])
        return ok({"kind": "preset", "scan": req.scan, "scan_name": preset["name"], "name": big["name"], "market": req.region, **out})
    name, members = scan_members(profile, req.region, req.set)
    if not members:
        err(400, "empty", "Your watchlist has no stocks in this market yet. Star a few companies in Research first.")
    prov = markets.provider(req.region)
    if prov is None or not prov.ready():
        raise KiteNotReady("Market data for this market is offline right now.")
    key = ("scan", req.scan, req.region, tuple(_member_key(m) for m in members))
    out = _results.get(key)
    if out is None:                       # the same group gives everyone the same answer until prices move
        if req.scan == "st_s2":
            out = {"kind": "st_s2", **scan.run(markets, req.region, members)}
        else:
            got = scan.run_preset(markets, req.region, members, req.scan)
            out = {"kind": "preset", "scan": req.scan, "scan_name": scan_presets.BY_ID[req.scan]["name"], "matches": len(got["rows"]),
                   "stored": False, **got}
        _results.set(key, out, 300)
    out = dict(out)
    out["rows"] = with_nse_close(req.region, out.get("rows") or [], "t" if out.get("kind") == "st_s2" else "as_of", "chg")
    out["problems"] = [public_text(x) for x in out["problems"]]          # data-source errors can name the source
    return ok({"name": name, "market": req.region, **out})


_results = TTLCache(max_items=300)        # scan and rotation answers, shared: weekly and daily charts move slowly


def _member_key(m) -> str:
    return json.dumps(m, sort_keys=True, default=str) if isinstance(m, dict) else str(m)


@app.get("/research/rotation")
def sector_rotation(region: str = "IN", set: str = "sectors", interval: str = "weekly", tail: int = 5,
                    profile=Depends(current_profile)):
    """Where each sector (or stock in a group) sits against the benchmark: relative strength and its momentum."""
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
    key = ("rotation", region, set, tuple(_member_key(m) for m in members or []), interval, tail)
    out = _results.get(key)
    if out is None:
        try:
            out = rotation.run(markets, region, set, members, interval, tail)
        except LookupError as e:
            err(404 if set.startswith("sector:") else 503, "no_benchmark", str(e))
        _results.set(key, out, 600)
    out = dict(out)
    out["skipped"] = [public_text(x) for x in out["skipped"]]
    return ok({"name": name, "market": region, **out})


@app.put("/research/scan/alerts")
def scan_alerts(req: ScanAlertReq, profile=Depends(current_profile)):
    if req.on:
        need(profile, "scans", "ST S2 watchlist alerts")
    scan.set_alert(profile["id"], req.on)
    return {"alerts": req.on}


# ---------- stock alerts people set (price, day move, moving average, RSI, Stage, 52-week high or low) ----------
ALERT_ID = re.compile(r"^[0-9a-f]{6,24}$")


def alert_view(a: dict) -> dict:
    return {**{k: v for k, v in a.items() if k not in ("state", "rev")}, "text": stock_alerts.describe(a)}


def alerts_page(profile) -> dict:
    mine = stock_alerts.items(profile["id"])
    active = sorted((a for a in mine if a.get("status") == "active"), key=lambda a: a.get("created_at") or "", reverse=True)
    done = sorted((a for a in mine if a.get("status") != "active"), key=lambda a: a.get("triggered_at") or "", reverse=True)
    to = alerts.newsletter_email(profile)
    return {"active": [alert_view(a) for a in active], "triggered": [alert_view(a) for a in done],
            "limit": stock_alert_limit(profile["_plan"]), "count": len(active), "channels": stock_alerts.channels(profile),
            "email": to, "email_confirmed": bool(to) and alerts.email_confirmed(profile)}


def alert_seed(region: str, sym: str) -> dict | None:
    """The stock's quote now, to check it exists and to start a price alert on the right side of its level. A source
    that can't be reached doesn't block saving; a stock with no price does."""
    try:
        q = alert_quotes(region, [sym]) or {}
    except Exception:
        return None
    hit = q.get(sym)
    if not hit or not isinstance(hit.get("price"), (int, float)):
        err(400, "no_price", f"There's no price for {sym} in {'India' if region == 'IN' else 'the US'}. Check the ticker.")
    return hit


def alert_note(a: dict, q: dict | None) -> str | None:
    """Say so when the price is already past the level, since the alert waits for the next crossing."""
    p = (q or {}).get("price")
    if a["kind"] == "surveillance":
        now = [f["label"] for f in surveillance.flags_for(a["symbol"])]
        return (f"{a['symbol']} is on {', '.join(now)} now. " if now else f"{a['symbol']} isn't on an exchange surveillance list now. ") + \
            "The alert fires when it enters, leaves or changes stage on one."
    if a["kind"] == "mwpl":
        r = stock_futures.row_for(a["symbol"])
        return ((f"{a['symbol']}'s MWPL use was {r['m']:.1f}% on {r['as_of']}. " if r and r.get("m") is not None else "")
                + "The alert fires when it crosses 80%, either way, in the evening's file.")
    if a["kind"] == "mtf":
        r = mtf.for_symbol(a["symbol"])
        return ((f"{a['symbol']}'s margin-funded shares were {r['pct_shares']:.2f}% of shares issued on {r['as_of']}. "
                 if r.get("pct_shares") is not None else "") + "The alert fires when the daily disclosure crosses your level.")
    if a["kind"] != "price" or not isinstance(p, (int, float)) or (a.get("state") or {}).get("side") != a["op"]:
        return None
    m = stock_alerts.money
    return (f"{a['symbol']} is already {a['op']} {m(a['value'], a['region'])} (now {m(p, a['region'])}), so the alert "
            f"fires the next time it crosses {a['op']} it.")


def save_alert(profile, req: StockAlertReq, aid: str | None = None) -> dict:
    limit = stock_alert_limit(profile["_plan"])
    try:
        body = stock_alerts.clean(req.model_dump())
    except stock_alerts.AlertError as e:
        err(400, "bad_alert", str(e))
    if body["kind"] == "mwpl":                      # MWPL use crossing 80%: Basic and up, on a stock with futures
        need(profile, "stock_futures", "MWPL alerts")
        if stock_futures.DESK.store.days() and stock_futures.row_for(body["symbol"]) is None:
            err(400, "no_futures", f"{body['symbol']} has no stock futures in the newest F&O file.")
    if body["kind"] == "mtf":                       # margin-funded shares crossing a level: Basic and up
        need(profile, "mtf", "Margin funding alerts")
    if body["kind"] == "etfgap":                    # an ETF's price against its NAV: Basic and up, on a listed ETF
        need(profile, "etf_gaps", "ETF gap alerts")
        if not etf_nav.known(body["symbol"]):
            err(400, "not_etf", f"{body['symbol']} isn't on the exchange's ETF list.")
    if body["kind"] == "bizupdate":                 # a new monthly or quarterly business update: Basic and up
        need(profile, "biz_updates", "Business update alerts")
    q = alert_seed(body["region"], body["symbol"])
    try:
        a = (stock_alerts.update(profile["id"], aid, body, limit, q) if aid else stock_alerts.create(profile["id"], body, limit, q))
    except stock_alerts.LimitReached as e:
        nxt = next((PLANS[p]["name"] for p in ("basic", "pro") if PLANS[p]["stock_alerts"] > e.limit), None)
        upgrade(f"Your plan has {e.limit} active alert{'s' if e.limit != 1 else ''}. Delete one"
                + (f", or move to {nxt} for more." if nxt else " to add another."), "alert_limit")
    if a is None:
        err(404, "not_found", "That alert is gone. Reload the page.")
    return {"alert": alert_view(a), "note": alert_note(a, q), **alerts_page(profile)}


@app.get("/alerts")
def list_stock_alerts(profile=Depends(current_profile)):
    return ok(alerts_page(profile))


@app.post("/alerts")
def create_stock_alert(req: StockAlertReq, profile=Depends(current_profile)):
    throttle(profile, "stock_alert", 60, 3600, "That's a lot of alerts in an hour. Try again later.")
    return ok(save_alert(profile, req))


@app.put("/alerts/{aid}")
def edit_stock_alert(aid: str, req: StockAlertReq, profile=Depends(current_profile)):
    if not ALERT_ID.match(aid):
        err(404, "not_found", "That alert is gone. Reload the page.")
    throttle(profile, "stock_alert", 60, 3600, "That's a lot of alert changes in an hour. Try again later.")
    return ok(save_alert(profile, req, aid))


@app.delete("/alerts/{aid}")
def delete_stock_alert(aid: str, profile=Depends(current_profile)):
    if not ALERT_ID.match(aid) or not stock_alerts.delete(profile["id"], aid):
        err(404, "not_found", "That alert is gone. Reload the page.")
    return ok(alerts_page(profile))


@app.delete("/alerts")
def clear_triggered_alerts(profile=Depends(current_profile)):
    """Clear the list of alerts that already fired."""
    stock_alerts.delete(profile["id"], triggered=True)
    return ok(alerts_page(profile))


# ---------- exchange filings and red flags (Pro, India) ----------
def filing_call(fn):
    try:
        return fn()
    except SourceError as e:
        err(503 if e.busy else 502, "filings_unavailable", str(e))


@app.get("/research/filings")
def filings_watchlist(profile=Depends(current_profile)):
    """Red flags in the last 3 months for each Indian stock the person holds or watches."""
    need(profile, "filings", "Watchlist red flags")
    syms = filings.followed_symbols(profile["id"])
    out = filings.overview(filings_feed, syms) if syms else {"rows": [], "problems": [], "days": filings.WINDOW_DAYS}
    out["problems"] = [public_text(x) for x in out["problems"]]
    return ok({**out, "alerts": bool(filings.alert_state(profile["id"]).get("on")), "send_at": filings.SEND_AT})


@app.get("/research/filings/{symbol}")
def filings_company(symbol: str, profile=Depends(current_profile)):
    """One Indian company's filings for the last year (NSE, or BSE for a company listed only there), with red flags
    and the 3-month summary. For everyone: the watchlist view and its alert are the paid part."""
    sym = research_routes.symbol_of(symbol)
    return ok(filing_call(lambda: filings.report(filings_feed, sym)))


@app.get("/research/deals/{symbol}")
def deals_company(symbol: str, profile=Depends(current_profile)):
    """One Indian company's deals and insider trades over the last year, from exchange disclosures: promoters' and
    insiders' trades and pledges, substantial acquisitions, bulk and block deals. Facts as filed."""
    sym = research_routes.symbol_of(symbol)
    try:
        out = deals.report(filings_feed, sym)
    except SourceError as e:
        inst = _quiet(kite.equity, sym) if kite.ready() else None
        if not inst or inst.get("exchange") == "NSE":
            err(503 if e.busy else 502, "filings_unavailable", str(e))
        # listed only on BSE: the exchange's deal lists have nothing for it, which is an empty answer, not a fault
        out = {"symbol": sym, "days": deals.DEALS_DAYS, "items": [], "count": 0, "problems": [], "flow": None,
               "flow_days": deals.FLOW_DAYS, "source": deals.SOURCE}
    return ok({**out, "flow_text": deals.flow_text(out["flow"]) if out["flow"] else None})


@app.get("/research/surveillance")
def surveillance_lists(profile=Depends(current_profile)):
    """Every Indian stock on an exchange surveillance list now (ASM, GSM, ESM, trade-to-trade, F&O ban, a recent
    price-band change), the words for each flag, and the date of each list. One answer for every badge in the app."""
    return ok(surveillance.view())


@app.post("/admin/surveillance/refresh")
def admin_surveillance_refresh(_=Depends(admin.admin_profile)):
    """Read the surveillance lists now (no alerts are sent from here) and say what each list answered."""
    out = surveillance.refresh(filings_feed)
    surv_job.record(surveillance.ist_now(), out["problems"], len(surveillance.PARTS), changes=len(out["changes"]))
    return {"changes": len(out["changes"]), "problems": [public_text(p) for p in out["problems"]],
            "lists": surveillance.view()["lists"], "job": surv_job.status}


@app.put("/research/filings/alerts")
def filings_alerts(req: ScanAlertReq, profile=Depends(current_profile)):
    if req.on:
        need(profile, "filings", "Filing alerts")
    filings.set_alert(profile["id"], req.on)
    return {"alerts": req.on}


# ---------- results calendar (India and US) ----------
_results_built: set[str] = set()


def results_ready(region: str):
    """Build a region's calendar now when none is stored yet (the first visit after it ships), once per process."""
    if results_calendar.load(region)["at"] or region in _results_built:
        return
    _results_built.add(region)
    try:
        results_job.refresh(region)
    except Exception as e:
        print("results calendar build:", str(e)[:160])


@app.get("/research/results")
def results_page(region: str = "IN", scope: str = "mine", q: str = "", profile=Depends(current_profile)):
    """Results dates this week and next: the user's stocks (watchlist, notebooks, paper sessions) or every company."""
    r = research_routes.region_of(region)
    results_ready(r)
    return research_routes.ok(results_calendar.view(r, profile["id"], "all" if scope == "all" else "mine", q[:30]))


@app.get("/research/results/{region}/{symbol}")
def results_company(region: str, symbol: str, profile=Depends(current_profile)):
    """One company's next results date and its latest one (with the filing, once it's out)."""
    return research_routes.ok(results_calendar.lookup(research_routes.region_of(region), research_routes.symbol_of(symbol)))


@app.put("/research/results/alerts")
def results_alerts(req: ScanAlertReq, profile=Depends(current_profile)):
    results_calendar.set_alerts(profile["id"], req.on)
    return {"alerts": req.on}


@app.post("/admin/results/refresh")
def admin_results_refresh(_=Depends(admin.admin_profile)):
    """Refresh both regions' results calendars now, and say what each feed answered."""
    who = results_calendar.trackers()
    return {region: results_job.refresh(region, who) for region in results_calendar.REGIONS} | {"job": results_job.status}


# ---------- corporate actions (India and US) ----------
_corp_tried: dict[str, float] = {}


def corp_ready(region: str):
    """Build a region's corporate-actions calendar now when none is stored yet: tried again a minute after a feed
    that was busy, so one bad moment doesn't leave the page empty until the next scheduled refresh."""
    if corp_actions.load(region)["at"] or time.time() - _corp_tried.get(region, 0) < 60:
        return
    _corp_tried[region] = time.time()
    try:
        corp_job.refresh(region)
    except Exception as e:
        print("corporate actions build:", str(e)[:160])


@app.get("/research/corp-actions")
def corp_actions_page(region: str = "IN", scope: str = "mine", q: str = "", kind: str = "", profile=Depends(current_profile)):
    """Dividends, bonus issues, splits, buybacks and rights issues by ex-date: the user's stocks or every company."""
    r = research_routes.region_of(region)
    corp_ready(r)
    return research_routes.ok(corp_actions.view(r, profile["id"], "all" if scope == "all" else "mine", q[:30], kind[:20]))


@app.get("/research/corp-actions/{region}/{symbol}/unadjusted")
def corp_actions_unadjusted(region: str, symbol: str, start: str, end: str, profile=Depends(current_profile)):
    """The company's actions in a test window that its prices aren't adjusted for (a demerger), for the backtest page's
    note (R6O-010). Facts as the exchange lists them."""
    r, s = research_routes.region_of(region), research_routes.symbol_of(symbol)
    if not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", start or "") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end or "")):
        err(400, "bad_dates", "Give the start and end as YYYY-MM-DD.")
    return research_routes.ok({"rows": corp_actions.unadjusted(r, s, start, end, corp_job.sources())})


@app.get("/research/corp-actions/{region}/{symbol}")
def corp_actions_company(region: str, symbol: str, profile=Depends(current_profile)):
    """One company's corporate actions: those ahead and the last three years'."""
    r, s = research_routes.region_of(region), research_routes.symbol_of(symbol)
    return research_routes.ok(corp_actions.company(r, s, corp_job.sources()))


@app.put("/research/corp-actions/alerts")
def corp_actions_alerts(req: ScanAlertReq, profile=Depends(current_profile)):
    corp_actions.set_alerts(profile["id"], req.on)
    return {"alerts": req.on}


@app.post("/admin/corp-actions/refresh")
def admin_corp_actions_refresh(universe: bool = False, _=Depends(admin.admin_profile)):
    """Refresh both regions' corporate-actions calendars now, and say what each feed answered. With `universe`, also
    start the read of the whole US universe in the background (it takes several minutes)."""
    who = results_calendar.trackers()
    out = {region: corp_job.refresh(region, who) for region in corp_actions.REGIONS} | {"job": corp_job.status}
    if universe and not corp_job.universe_running:
        corp_job.start_universe(who)
        out["universe_started"] = True
    return out


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


def us_price_ratios(p: dict, sym: str) -> dict:
    """Today's quote for a US ticker (share classes and preferred series written the quote screens' way, BRK-B,
    BAC-PL) and the company's ratios from it, set on `p`; the quote is returned ({} without one). A preferred share,
    warrant or unit trades at its own price, not a slice of the company's value, so its price makes no market value,
    P/E or yield; the company's own figures stand."""
    try:
        m = research_hub.yahoo.meta(sec.price_symbol(sym))
    except Exception:                     # no price: the numbers still stand, the ratios that need a price don't
        m = {}
    if sec.non_common(sym):
        p["ratios"] = sec.ratios(p, None)
        p["share_note"] = (f"{sym.upper()} is a preferred share, warrant or unit of the company, not its common stock: "
                           "the figures are the company's, and its price isn't used for market value or P/E.")
    else:
        p["ratios"] = sec.ratios(p, m.get("price"), m.get("high52"), m.get("low52"))
    return m


def deep_base_us(sym: str, years: int = 2) -> dict:
    """A US company from its SEC filings: numbers, industry and filings, with ratios from today's share price."""
    p = sec.with_fx(dict(research_routes.source_call(lambda: sec_feed.company(sym))), usd_per)
    m = us_price_ratios(p, sym)
    try:
        wiki = research_hub.wiki.company(p.get("name") or sym) or {}
        p["about"] = wiki.get("extract") or ""
    except Exception:
        p["about"] = ""
    try:                                  # insiders' own buying and selling (Form 4), for the checklist
        fh = research_hub.finnhub
        p["insider"] = (fh.insider(sym).get("data") or []) if fh and fh.ready() else None
    except Exception:
        p["insider"] = None
    cut = (datetime.now(IST).date() - timedelta(days=366 * years)).isoformat()
    docs = [d for d in p.get("documents") or [] if d["at"][:10] >= cut]
    trend, why = price_status(sym, "US")
    return {"p": p, "docs": docs, "doc_note": None, "filings": None, "trend": trend, "trend_why": why,
            "quote": {k: m.get(k) for k in ("price", "prev_close", "high", "low")} if m.get("price") else None}


def usd_per(cur: str) -> float | None:
    """Today's US dollars to one unit of a currency, from the market data source's quote of the pair (or the
    other way round, turned over)."""
    try:
        return research_hub.yahoo.meta(f"{cur}USD=X").get("price")
    except SourceError:
        back = research_hub.yahoo.meta(f"USD{cur}=X").get("price")
        return 1 / back if back else None


def deep_years(years: int) -> int:
    lo, hi = report_card.YEARS
    return max(lo, min(hi, int(years or 2)))


BSE_WAIT = "Documents are not available from BSE right now (it is turning requests away). Try again later."


_deep_pool = ThreadPoolExecutor(max_workers=12, thread_name_prefix="deep-dive")   # the deep dive's sources, read side by side


def deep_base(sym: str, region: str = "IN", years: int = 2, trades: bool = True) -> dict:
    """Numbers and the list of readable documents for one company (no AI), documents from the last `years` years.
    `trades`: also read its insider-trading disclosures, for the checklist (the market audit leaves them out)."""
    if region == "US":
        return deep_base_us(sym, years)
    code = bse_code(sym)                                  # listed only on BSE: its numbers are under the BSE code
    # the filings, insider trades and prices don't wait for the numbers: they are read alongside them (R5O-025: the
    # sources were read one after another)
    ahead = {"items": _deep_pool.submit(filings_feed.announcements, sym, max(deepdive.DOC_DAYS, 366 * years)),
             "trend": _deep_pool.submit(price_status, sym)}
    if trades:
        ahead["insider"] = _deep_pool.submit(lambda: _quiet(lambda: filings_feed.insider_trades(sym)))
    p = with_industry(sym, research_routes.source_call(lambda: research_hub.screener.company(code or sym)))
    try:
        p = research_hub.screener.with_cash(p)           # cash on hand, for enterprise value
    except Exception:
        pass
    n = deepdive.numbers(p)
    if not n["bank"] and len(n["years"]) >= 3 and all(y["capex"] is None for y in n["years"][-3:]):
        try:     # no estimate from the balance sheet (fixed assets sold or written down): what it spent buying them
            p = research_hub.screener.with_capex(p)
        except Exception:
            pass
    try:
        items = ahead["items"].result()
        doc_note, fsum = None, filings.summarise(items)
    except SourceError as e:
        # a company listed only on BSE, and BSE turning this server away: its documents wait, they aren't missing
        note = BSE_WAIT if code and getattr(e, "busy", False) else str(e)
        items, doc_note, fsum = [], public_text(note), None
    insider = ahead["insider"].result() if trades else None
    trend, why = ahead["trend"].result()
    cut = (datetime.now(IST) - timedelta(days=366 * years)).strftime("%Y-%m-%dT%H:%M")
    told = None if doc_note else deepdive.meetings(items, cut)
    # four of each kind a year: a deck and a transcript a quarter, so a run of decks can't push the transcripts out
    return {"p": p, "docs": deepdive.documents(items, 4 * max(2, years)), "doc_note": doc_note, "filings": fsum, "trend": trend,
            "trend_why": why, "trades": insider, "told": told}


def price_status(sym: str, market: str = "IN") -> tuple[dict | None, str | None]:
    """(Stage and Supertrend on daily candles, or None; and when None, why): "untraded" (not on the exchange's
    trading list, or no trades in the window: suspended), "new" (under 30 days of prices), "sparse" (an older share that trades on fewer than 30 days), "stale" (no trade for a
    month) or "error" (the price source didn't answer: try again later)."""
    if market == "US":                    # share classes and preferred series are written with a dash for prices: BRK-B, BAC-PL
        sym = sec.price_symbol(sym)
    try:
        ids, _ = universes.resolve(markets, market, [{"symbol": sym}])
    except Exception:
        return None, "error"
    if not ids:
        if market == "US":                # not found, or the price source didn't answer: only the first is a fact
            try:
                research_hub.yahoo.chart(sym, "1d", 30)
            except SourceError as e:
                return None, "error" if e.busy else "untraded"
            except Exception:
                return None, "error"
        return None, "untraded"
    try:
        bars = scan._bars(markets, ids[0])
    except LookupError:
        return None, "untraded"
    except Exception:
        return None, "error"
    if not bars:
        return None, "untraded"
    try:
        last = datetime.fromisoformat(str(bars[-1].get("t"))[:10]).date()
        if (datetime.now(IST).date() - last).days > 31:
            return None, "stale"
    except (TypeError, ValueError):
        pass
    try:
        got = scan.analyse(bars)
    except Exception:
        return None, "error"
    if got:
        return got, None
    if len(bars) >= 30:
        return None, None
    # under 30 candles: a new listing, or an old share that trades on a handful of days a year (the broker's candles
    # skip days without a trade), told apart by how long ago its first candle is: 30 trading days is about six weeks
    try:
        first = datetime.fromisoformat(str(bars[0].get("t"))[:10]).date()
        return None, "new" if (datetime.now(IST).date() - first).days <= 60 else "sparse"
    except (TypeError, ValueError):
        return None, "new"


def price_trend(sym: str, market: str = "IN") -> dict | None:
    """Stage and Supertrend on daily candles, or None when prices aren't available."""
    return price_status(sym, market)[0]


def candle_day(t) -> str | None:
    """A daily candle's time as its day ("2026-10-08"): the candle is stamped at midnight, so the page said "Last
    close as of 8 Oct 2026, 00:00 IST" (R5O-025). A time within the day stays as it is."""
    s = str(t or "")
    if not s:
        return None
    return s[:10] if len(s) <= 10 or s[11:19] in ("00:00:00", "") else s


def deep_view(sym: str, base: dict) -> dict:
    p = base["p"]
    us = p.get("region") == "US"
    key = f"US:{sym}" if us else sym          # stored AI reads: Indian symbols keep their old keys
    reads, card = deepdive.stored(key), report_card.stored(key)
    nums = deepdive.numbers(p)
    card_view = report_card.view(card, nums)
    snap = screener_summary(p)
    if not us:      # at the last close, as on the company page (the source's own ratios are at its once-a-day price)
        snap = at_live_price(snap, (base.get("trend") or {}).get("price"))
    return {"symbol": sym, "region": "US" if us else "IN", "currency": "USD" if us else "INR", "source_url": p.get("url"),
            "reporting_currency": p.get("currency") or ("USD" if us else "INR"),
            "name": p.get("name") or sym, "about": (p.get("about") or "")[:1200], "numbers": nums,
            "snapshot": {k: snap.get(k) for k in ("market_cap_cr", "price", "pe", "pb", "roce", "roe", "debt_equity", "div_yield")},
            "industry_measures": industry.measures(p, sym),
            "valuation": industry.valuation(p, snap, industry.classify(p, nums, sym)["group"], industry.measures(p, sym)["key"]),
            "documents": base["docs"], "doc_note": base["doc_note"], "reads": reads, "reads_stale": not deepdive.fresh(reads),
            "card": card_view, "card_stale": not deepdive.fresh(card), "trend": base["trend"], "filings": base["filings"],
            "checklist": checklist.evaluate(p, nums, base["filings"], base["trend"], card_view, None if us else sym, base.get("trades")),
            "ai": True, "report_card": True, "as_of": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "numbers_at": p.get("fetched_at"), "price_at": candle_day((base["trend"] or {}).get("t")),
            "calls": sum(d["kind"] == ("earnings_release" if us else "transcript") for d in base["docs"])}


def company_hosts(p: dict) -> tuple[str, ...]:
    """The company's own website, where exchange filings often point for the full transcript or presentation."""
    from .docs import site_domain
    d = site_domain(p.get("website"))
    return (d,) if d else ()


def deep_ai_allowed(profile) -> None:
    """The deep dive's AI reads count against the same daily cap as the research pages' (none for admins and Pro)."""
    limit = research_routes.ai_cap(profile)
    if limit is not None and research_routes.ai_reads_today(profile) >= limit:
        err(429, research_routes.LIMIT_CODE, research_routes.limit_words(limit))


DEEP_KINDS = {"deepdive": ("deepdives_per_month", deepdives_limit), "deck": ("decks_per_month", decks_limit)}


def deep_used(profile, kind: str) -> int:
    """Companies opened in the deep dive (kind "deepdive") or decks made ("deck") this month."""
    return db.count_usage(profile["id"], kind, month_start_iso())


def use_deep(profile, kind: str, sym: str, region: str) -> None:
    """Count a company against the plan's monthly deep dives or decks. Only the first time in a month counts: opening
    the same company again (or its deck in the other format) is free. Stops with an upgrade message at the limit."""
    key, limit_of = DEEP_KINDS[kind]
    mark, since = f"{kind}:{region}:{sym}", month_start_iso()
    if db.count_usage(profile["id"], mark, since):
        return
    limit = limit_of(profile["_plan"])
    if limit is not None and deep_used(profile, kind) >= limit:
        more = lift(profile["_plan"], key, "deep dives" if kind == "deepdive" else "decks")
        if kind == "deepdive":
            upgrade(f"You've opened {limit} compan{'y' if limit == 1 else 'ies'} in the deep dive this month. Companies "
                    f"you've already opened this month still open.{more}", "deepdive_limit")
        upgrade(f"You've made {limit} company deck{'' if limit == 1 else 's'} this month.{more}", "deck_limit")
    db.add_usage(profile["id"], kind)
    db.add_usage(profile["id"], mark)


def deep_symbol(symbol: str, region: str) -> str:
    if region != "IN":
        return re.sub(r"[^A-Z0-9.\-]", "", symbol.upper())[:12]
    s = research_routes.symbol_of(symbol)
    # a BSE code and the company's BSE symbol are the same page (and share its stored reads)
    return bse_symbol(s) if s.isdigit() and len(s) == 6 else s


@app.get("/research/deep/{symbol}")
def deep_dive(symbol: str, region: str = "IN", profile=Depends(current_profile)):
    """Growth, margins, capex and cash flow from the reported numbers, plus any stored read of the company's documents.
    India from the company pages and NSE filings; the US from the SEC's filings."""
    region = deep_region(region)
    sym = deep_symbol(symbol, region)
    base = deep_base(sym, region)          # an unknown company stops here, before it's counted
    use_deep(profile, "deepdive", sym, region)
    out = ok(deep_view(sym, base))
    try:
        first_steps.mark(profile["id"], "deepdive")
    except Exception as e:
        print("first steps:", str(e)[:120])
    invite_rewards.safe_touch(profile, "deepdive")
    return out


@app.post("/research/deep/{symbol}/read")
def deep_dive_read(symbol: str, refresh: bool = False, region: str = "IN", years: int = 2, profile=Depends(current_profile)):
    """Read the company's own documents with AI: business model, capex and growth plans. India: the latest investor
    presentation and call transcripts. US: the latest 10-K and earnings releases."""
    region = deep_region(region)
    sym = deep_symbol(symbol, region)
    key = f"US:{sym}" if region == "US" else sym
    years = deep_years(years)
    base = deep_base(sym, region, years)
    use_deep(profile, "deepdive", sym, region)
    have = deepdive.stored(key)
    if deepdive.fresh(have) and not refresh:
        return ok(deep_view(sym, base))
    if not base["docs"] and not base["p"].get("about"):
        err(404, "no_documents", f"No annual report or earnings release was found for this company in the last {years} years." if region == "US"
            else f"No investor presentation or call transcript was found for this company in the last {years} years.")
    deep_ai_allowed(profile)
    p = base["p"]
    try:
        if region == "US":
            reads = deepdive.read_us(sym, p.get("name") or sym, p.get("about") or "", base["docs"], sec_feed, (_gemini, _anthropic),
                                     industry.measures(p, sym), years=years)
        else:
            reads = deepdive.read(sym, p.get("name") or sym, p.get("about") or "", base["docs"], deep_docs, (_gemini, _anthropic),
                                  industry.measures(p, sym), company_hosts(p), years=years)
    except AIBusy as e:
        err(503, "ai_busy", str(e))
    except AIError as e:
        err(422, "ai_failed", str(e))
    reads["problems"] = [public_text(x) for x in reads["problems"]]
    reads["years"] = years
    deepdive.store(key, reads)
    db.add_usage(profile["id"], "research_ai")
    return ok(deep_view(sym, base))


_investor_pool = ThreadPoolExecutor(max_workers=4)


@app.get("/research/investor")
def investor_home(region: str = "IN", profile=Depends(current_profile)):
    """Every watchlist company in one market (India or US): trend, sector rotation, red flags (India), checklist and
    report card on one page."""
    need(profile, "investor_home", "Watchlist at a glance")
    region = "US" if region.upper() == "US" else "IN"
    us = region == "US"
    syms = filings.watchlist_symbols(profile["id"], region)[:investor.MAX]
    if not syms:
        return ok({"rows": [], "as_of": None, "region": region})
    try:
        rot = rotation.run(markets, region, "sectors", None, "weekly", 4)
        quad = {r["symbol"]: {"symbol": r["symbol"], "name": r["name"], "quadrant": r["quadrant"]} for r in rot["rows"]}
    except Exception:
        quad = {}
    # one price source with the List tab: the same quotes call, each with the time of its last trade
    quotes = _quiet(research_hub.quotes, region, syms) or {}

    def one(sym):
        problem, key = None, f"US:{sym}" if us else sym
        try:
            p = deep_base_us(sym)["p"] if us else with_industry(sym, research_hub.screener.company(bse_code(sym) or sym))
        except Exception as e:
            p, problem = None, public_text(str(e))[:120]
        fsum = None
        if not us:                        # exchange filings are Indian; US companies have no red-flag feed here
            try:
                fsum = filings.summarise(filings_feed.announcements(sym))
            except Exception:
                fsum = None
        trend = price_trend(sym, region)
        nums = deepdive.numbers(p) if p else None
        card = report_card.view(report_card.stored(key), nums) if nums else None
        trades = None if us else _quiet(lambda: filings_feed.insider_trades(sym))
        checks = checklist.evaluate(p, nums, fsum, trend, card, None if us else sym, trades) if p else None
        sec = investor.sector_of(region, sym)
        sector = quad.get(sec) or ({"symbol": sec, "name": rotation._label(region, sec, None), "quadrant": None} if sec else None)
        return investor.row(sym, (p or {}).get("name"), trend, sector, fsum, checks, card, deepdive.stored(key) is not None, problem,
                            quotes.get(sym))

    rows = list(_investor_pool.map(one, syms))
    return ok({"rows": rows, "region": region, "as_of": datetime.now(IST).isoformat(timespec="minutes")})


# ---------- My Holdings: the user's own stocks, from their broker's export (everyone; paid plans keep more) ----------
ISIN_KEY = "isin:nse"            # the exchange's ISINs, saved once a day: {"day", "map": {isin: [symbol, name]}}
_isin: dict = {"day": None, "map": {}, "tried": 0.0}
HOLDINGS_FACTS = 40              # stocks checked for trend and filings, largest first
SECTOR_WAIT = 12.0               # seconds a save waits for the exchange's sector names; the rest use the sector index
_holdings_pool = ThreadPoolExecutor(max_workers=6)


def isin_list() -> dict[str, list]:
    """ISIN -> [NSE symbol, company name] from the exchange's list of companies: fetched once a day, with the last
    good list kept for when the exchange turns us away."""
    day = datetime.now(IST).date().isoformat()
    if _isin["day"] == day:
        return _isin["map"]
    if not _isin["map"]:
        try:
            saved = json.loads(db.get_setting(ISIN_KEY) or "{}")
            _isin["map"] = saved.get("map") or {}
            _isin["day"] = saved.get("day") if saved.get("day") == day else None
        except (ValueError, TypeError, AttributeError):
            pass
    if _isin["day"] != day and time.time() - _isin["tried"] > 3600:
        _isin["tried"] = time.time()
        try:
            got = {c["isin"]: [c["symbol"], c["name"]] for c in filings_feed.all_equities() if c.get("isin")}
            if len(got) >= 100:
                _isin.update(day=day, map=got)
                db.set_setting(ISIN_KEY, json.dumps({"day": day, "map": got}))
        except Exception as e:                  # the saved list, or none: symbols and names still match
            print("ISIN list unavailable:", e)
    return _isin["map"]


def _quiet(fn, *a):
    try:
        return fn(*a)
    except Exception:
        return None


def holdings_matcher() -> holdings.Matcher:
    isins = isin_list()
    listed = {v[0]: v[1] for v in isins.values() if isinstance(v, list) and len(v) == 2}
    return holdings.Matcher(lambda s: _quiet(kite.equity, s), lambda n: _quiet(kite.equity_by_name, n),
                            lambda c: (isins.get(c) or [None])[0], listed, kite.ready())


def _india_suggestions() -> list[dict]:
    return suggest.india_rows(kite.equities(), _isin["map"]) if kite.ready() else []


def _india_listed() -> dict[str, dict]:
    """The stored list of Indian companies, named from the exchange's list where the stored one has no name."""
    names = {v[0]: v[1] for v in isin_list().values() if isinstance(v, list) and len(v) == 2}
    return {s: {**v, "name": v.get("name") or names.get(s)} for s, v in stock_pages.companies("IN").items()}


suggester = suggest.Suggester({"IN": _india_suggestions, "US": lambda: suggest.us_rows(_sec_companies())},
                              {"IN": _india_listed, "US": lambda: stock_pages.companies("US")})


# search by name everywhere: the broker's list with the exchange's full names and ISINs (as far as they're read; the
# morning warm-up reads them), and the company boxes' own lists for the research search's US side
KiteService.names_fn = staticmethod(lambda: _isin["map"])
Research.local_search = staticmethod(lambda q, region: suggester.search_ranked(q, region, 10))


@app.get("/suggest/companies")
def suggest_companies(q: str = Query("", max_length=40), market: str | None = Query(None, max_length=4),
                      profile=Depends(current_profile)):
    """Up to 8 listed companies for what's typed (India, the US or both): the exact symbol first, then symbols
    starting with it, then names. Each has the identifier to save (`id`: NSE symbol, BSE code or US ticker)."""
    m = (market or "").upper()
    return ok({"rows": suggester.search(q[:40], m if m in suggest.MARKETS else None)})


def _us_find(sym: str) -> dict | None:
    """A US company's common shares by ticker: from the list of companies, else any ticker the US prices know."""
    hit = suggester.find(sym, "US")
    if hit:
        return hit
    if not suggest.us_common(sym, set()):
        return None
    q = _quiet(research_hub.quotes, "US", [sym]) or {}
    return {"symbol": sym, "name": sym} if (q.get(sym) or {}).get("price") else None


def with_sectors(items: list[dict], known: dict[str, str] | None = None) -> list[dict]:
    """Each holding with its broad sector: the exchange's own, or its sector index's when the exchange is slow. A US
    stock's is its sector fund's, when it's in one."""
    known = known or {}

    def path(i):
        return [] if i["exchange"] != "NSE" else filings_feed.industry(i["symbol"])
    todo = {i["symbol"]: _holdings_pool.submit(path, i) for i in holdings.indian(items) if not known.get(i["symbol"])}
    if todo:
        wait_all(list(todo.values()), timeout=SECTOR_WAIT)
    out = []
    for i in items:
        if holdings.market_of(i) == "US":
            out.append({**i, "sector": holdings.us_sector(investor.sector_of("US", i["symbol"]))})
            continue
        f = todo.get(i["symbol"])
        got = f.result() if f is not None and f.done() and not f.exception() else None
        out.append({**i, "sector": known.get(i["symbol"]) or holdings.sector_label(investor.sector_of("IN", i["symbol"]), got)})
    return out


connect_routes.setup(throttle)
connect_sync.setup(holdings_matcher, _us_find, with_sectors)
connect_redact.install()
connect_job = connect_jobs.Job()


def usd_inr() -> float | None:
    """Rupees a dollar: the day's stored rate, else read now; None when neither is there."""
    got = pricing.rates().get("USD")
    if not got:
        got = _quiet(fx_rate, "USD")
    return float(got) if got else None


_PRICED: dict[tuple, tuple[float, dict]] = {}       # (user, symbols) -> (when read, the prices read)
_PRICED_LOCK = threading.Lock()
PRICED_FOR = 20.0                                   # seconds one reading of a person's prices is shared by every page


def _prices_at(quotes: list[dict]) -> str:
    """When some prices are from: the latest trade among the quotes (the exchange's own stamp), else the moment they were read."""
    now = datetime.now(timezone.utc)
    return (holdings.latest_trade(quotes, now) or now).isoformat(timespec="minutes")


def _read_prices(ind: list[dict], us: list[str]) -> dict:
    """The prices behind a holdings view, read once: the quotes, the US quotes, the dollar rate, and the time of the
    latest trade among them (the exchange's own stamp, never the moment of asking)."""
    quotes, live = {}, bool(ind) and kite.ready()
    if live:
        try:
            quotes = kite.quote([i["symbol"] for i in ind])
        except Exception:
            live = False
    us_quotes = {}
    for n in range(0, len(us), 24):          # the US prices are read 24 at a time
        us_quotes.update({k: v for k, v in (_quiet(research_hub.quotes, "US", us[n:n + 24]) or {}).items() if v})
    rate = usd_inr() if us else None
    return {"quotes": quotes, "live": live, "us_quotes": us_quotes, "rate": rate,
            "prices_at": _prices_at([q for q in [*quotes.values(), *us_quotes.values()] if q]) if live or us_quotes else None}


def holdings_view(profile) -> dict:
    """The person's holdings at today's prices. The prices are read once and shared for a few seconds, so My space, Money,
    Holdings and the net worth add up to the same rupees when opened one after another."""
    h = holdings.load(profile["id"])
    ind = holdings.indian(h["items"])
    us = [i["symbol"] for i in h["items"] if holdings.market_of(i) == "US"]
    key = (profile["id"], tuple(i["symbol"] for i in ind), tuple(us), bool(ind) and kite.ready())
    with _PRICED_LOCK:
        hit = _PRICED.get(key)
    if hit and time.monotonic() - hit[0] < PRICED_FOR:
        got = hit[1]
    else:
        got = _read_prices(ind, us)
        with _PRICED_LOCK:
            if len(_PRICED) > 500:
                for k in [k for k, (t, _) in _PRICED.items() if time.monotonic() - t >= PRICED_FOR]:
                    _PRICED.pop(k, None)
            _PRICED[key] = (time.monotonic(), got)
    live, us_quotes = got["live"], got["us_quotes"]
    return {**holdings.view(h["items"], got["quotes"], us_quotes, got["rate"]), "source": h["source"], "updated_at": h["updated_at"],
            "prices": live or (not ind and bool(us_quotes)), "prices_at": got["prices_at"],
            "us_prices": bool(us_quotes) if us else None,
            "limit": holdings_limit(profile["_plan"]), "facts_max": HOLDINGS_FACTS}


def zerodha_read(profile) -> dict | None:
    """What the connected Zerodha account last returned, so an empty Holdings page can say it was asked and had nothing
    (R7M-009); None when Zerodha isn't connected."""
    try:
        k = connect_kite.status(profile["id"], profile)
    except Exception:
        return None
    if not k.get("connected"):
        return None
    return {"live": bool(k.get("live")), "count": k.get("count"), "read_at": k.get("refreshed_at")}


@app.get("/holdings")
def my_holdings(profile=Depends(current_profile)):
    """The user's holdings at today's prices: value, gain or loss, the day's change and the mix by sector."""
    return ok({**holdings_view(profile), "zerodha": zerodha_read(profile)})


@app.get("/holdings/facts")
def holdings_facts(profile=Depends(current_profile)):
    """For each held stock (the largest 40): its stage and Supertrend and, on plans with filings, red flags in the
    last 3 months, the latest filings and a scheduled results meeting. The same facts the other pages show."""
    items = sorted(holdings.indian(holdings.load(profile["id"])["items"]), key=lambda i: -(i["qty"] * (i.get("avg") or 1)))
    can = allows(profile["_plan"], "filings")
    today = datetime.now(IST).date()

    def one(i):
        sym = i["symbol"]
        found = _quiet(filings_feed.announcements, sym) if can else None
        return sym, holdings.facts(price_trend(sym), found, today, filings.upcoming_results)
    rows = dict(_investor_pool.map(one, items[:HOLDINGS_FACTS]))
    return ok({"rows": rows, "filings": can, "filings_plan": PLANS[FEATURE_PLAN["filings"]]["name"],
               "checked": min(len(items), HOLDINGS_FACTS), "count": len(items)})


@app.post("/holdings/import")
def holdings_import(req: HoldingsImportReq, profile=Depends(current_profile)):
    """Read a holdings export from the user's broker (or any CSV with symbol and quantity), match each line to a
    listed company and save the holdings. Lines that don't match are listed, never guessed."""
    throttle(profile, "holdings_import", 30, 3600, "That's a lot of uploads in an hour. Try again a little later.")
    raw = re.sub(r"^data:[^,]{0,200},", "", req.data.strip())
    if len(raw) > holdings_file.MAX_BYTES * 4 // 3 + 8:
        err(413, "file_too_big", f"That file is larger than {holdings_file.MAX_BYTES // (1024 * 1024)} MB. "
                                 "A holdings export is much smaller; check it's the right file.")
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        err(400, "bad_upload", "The file didn't arrive whole. Pick it again.")
    try:
        parsed = holdings_file.parse(data, req.filename)
    except holdings_file.FileError as e:
        err(400, "bad_file", str(e))
    found, missed = holdings.match_all(parsed["rows"], holdings_matcher())
    missed = sorted(parsed["problems"] + missed, key=lambda m: m.get("line") or 0)
    before = holdings.load(profile["id"])
    if req.mode == "add":
        found = holdings.merge(before["items"] + found)
    limit = holdings_limit(profile["_plan"])
    over, found = [i["symbol"] for i in found[limit:]], found[:limit]
    if found:                             # nothing matched: the saved holdings stay as they were
        known = {i["symbol"]: i.get("sector") for i in holdings.indian(before["items"])}
        holdings.save(profile["id"], with_sectors(found, known), parsed["broker"])
        invite_rewards.safe_touch(profile, "holdings")
    return ok({"broker": parsed["broker"], "imported": len(found), "saved": bool(found), "unmatched": missed[:200],
               "unmatched_count": len(missed), "over_limit": over, "limit": limit, "holdings": holdings_view(profile)})


@app.put("/holdings")
def holdings_edit(req: HoldingsReq, profile=Depends(current_profile)):
    """Save the holdings as edited by hand: add a stock, change a quantity or average price, remove one. Symbols
    that match no listed company are sent back and left out."""
    throttle(profile, "holdings_edit", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    limit = holdings_limit(profile["_plan"])
    if len(req.items) > limit:
        upgrade(f"Your plan keeps up to {limit} stocks in My Holdings." + lift(profile["_plan"], "holdings", "holdings"), "holdings_limit")
    before = holdings.load(profile["id"])
    saved = {(holdings.market_of(i), i["symbol"]): i for i in before["items"]}
    kept, rows, us_rows = [], [], []
    for n, i in enumerate(req.items, 1):
        old = saved.get((i.market, i.symbol.strip().upper()))
        if old:                           # already matched: kept as it is, even while market data is offline
            kept.append({**old, "qty": i.qty, "avg": i.avg or None})
        else:
            (us_rows if i.market == "US" else rows).append({"line": n, "symbol": i.symbol, "qty": i.qty, "avg": i.avg or None, "text": i.symbol})
    found, missed = holdings.match_all(rows, holdings_matcher()) if rows else ([], [])
    if us_rows:
        us_found, us_missed = holdings.match_us(us_rows, _us_find)
        found, missed = found + us_found, missed + us_missed
    found = holdings.merge(kept + found)
    if found:
        known = {i["symbol"]: i.get("sector") for i in holdings.indian(before["items"])}
        holdings.save(profile["id"], with_sectors(found, known), before["source"] or "Manual")
    elif not missed:
        holdings.delete(profile["id"])    # every row removed
    return ok({"unmatched": missed, "holdings": holdings_view(profile)})


HOLDINGS_CA_NOW = 8                # held stocks without a stored history fetched while the page waits; the rest after
_corp_fetching: set[str] = set()


def _corp_histories(uid: str, symbols: list[str], today) -> int:
    """Fetch the histories of held stocks that have none (a few now) or an old one (in the background). Returns
    how many are still being fetched."""
    missing = [s for s in symbols if not corp_actions.hist_load("IN", s)["at"]]
    sources = corp_job.sources()
    now = missing[:HOLDINGS_CA_NOW]
    if now:
        wait_all([_holdings_pool.submit(corp_actions.history, "IN", s, sources, today) for s in now], timeout=12)
    rest = [s for s in symbols if s not in now]
    if rest and uid not in _corp_fetching:
        _corp_fetching.add(uid)

        def later():
            try:
                corp_actions.refresh_histories("IN", sources, set(rest), today)
            finally:
                _corp_fetching.discard(uid)
        threading.Thread(target=later, daemon=True, name="holdings-corp-actions").start()
    return len(missing) - len(now)


def holdings_corp_view(profile, fetch: bool = True) -> dict:
    h = holdings.load(profile["id"])
    today = datetime.now(IST).date()
    ind = holdings.indian(h["items"])           # the exchange's corporate actions are for Indian stocks
    syms = [i["symbol"] for i in ind]
    corp_actions.prefetch("IN", syms)
    checking = _corp_histories(profile["id"], syms, today) if fetch and syms else 0
    cal = corp_actions.load("IN")["rows"]
    acts = {s: corp_actions.actions_for("IN", s, None, today, fetch=False, cal=cal) for s in syms}
    return {**corp_actions.holdings_view(ind, acts, today, h["updated_at"]), "checking": checking}


@app.get("/holdings/corp-actions")
def holdings_corp_actions(profile=Depends(current_profile)):
    """Dividends ahead and of the last twelve months for the user's holdings, and bonuses or splits since the
    holdings were saved, offered as a one-click adjustment (never made without the user)."""
    return ok(holdings_corp_view(profile))


@app.post("/holdings/corp-actions")
def holdings_corp_action(req: CorpActionReq, profile=Depends(current_profile)):
    """Apply a bonus or split to one holding's quantity and average price, set it aside, or undo the last one."""
    throttle(profile, "holdings_edit", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    h = holdings.load(profile["id"])
    sym = req.symbol.strip().upper()
    item = next((i for i in holdings.indian(h["items"]) if i["symbol"] == sym), None)
    if not item:
        err(404, "not_held", f"{sym} isn't in your holdings.")
    today = datetime.now(IST).date()
    saved = (h["updated_at"] or today.isoformat())[:10]
    if req.action == "undo":
        if not item.get("adjusted"):
            err(409, "nothing_to_undo", f"{sym} has no adjustment to undo.")
        new = corp_actions.undo(item)
    else:
        acts = corp_actions.actions_for("IN", sym, None, today, fetch=False)
        wait = corp_actions.pending(item, acts, str(item.get("since") or saved)[:10], today)
        a = next((a for a in wait if a["id"] == req.id), None)
        if not a or (req.action == "apply" and a is not wait[0]):
            err(409, "nothing_to_apply", f"There's no bonus or split waiting to be applied to {sym}. Reload the page.")
        new = corp_actions.apply(item, a) if req.action == "apply" else corp_actions.dismiss(item, a)
    items = [{**(new if i is item else i), "since": (new if i is item else i).get("since") or saved} for i in h["items"]]
    holdings.save(profile["id"], items, h["source"] or "Manual", stamped=True)
    return ok({"holdings": holdings_view(profile), "actions": holdings_corp_view(profile, fetch=False)})


@app.delete("/holdings")
def holdings_delete(profile=Depends(current_profile)):
    """Delete my holdings: every saved position, at once."""
    holdings.delete(profile["id"])
    return {"deleted": True}


# ---------- Money: net worth (stocks from My Holdings, everything else typed in; Free keeps 5 entries) ----------
_nw_prices: dict = {}                  # {"gold": (time read, (rupees a gram, as of))}, {"BTC": (time read, dollars)}
NW_PRICE_TTL = 600.0


def _nw_cached(key: str, read):
    hit = _nw_prices.get(key)
    if hit and time.time() - hit[0] < NW_PRICE_TTL:
        return hit[1]
    got = _quiet(read)
    _nw_prices[key] = (time.time(), got)
    return got


def _nw_gold():
    """Rupees a gram of 24 carat gold: the front-month gold future on the commodity exchange (quoted per 10 g)."""
    def read():
        prov = markets.provider("MCX")
        inst = prov.instrument("GOLD") if prov and prov.ready() else None
        p = prov.ltp(inst) if inst else None
        return (p / 10, datetime.now(timezone.utc).isoformat(timespec="minutes")) if p and p > 0 else None
    return _nw_cached("gold", read)


def _nw_crypto(coin: str):
    def read():
        prov = markets.provider("CRYPTO")
        inst = prov.instrument(f"{coin}-USD") if prov else None
        p = prov.ltp(inst) if inst else None
        return p if p and p > 0 else None
    return _nw_cached("crypto:" + coin, read)


def _nw_stocks(profile) -> dict:
    """My Holdings in rupees: Indian and US stocks apart (a position without a price counts at cost, as on Holdings)."""
    h = holdings_view(profile)
    worth = (lambda r: r["value"] if r["value"] is not None else r["invested"] or 0)
    rate = h.get("usd_inr")
    return {"in": sum(worth(r) for r in h["rows"] if r.get("market") != "US"),
            "us": sum(worth(r) for r in h["rows"] if r.get("market") == "US") * rate if rate else 0,
            "as_of": h.get("prices_at") or h.get("updated_at"), "count": len(h["rows"]), "usd_inr": rate}


app.include_router(money_networth.make_router(
    current_profile, _nw_stocks, money_networth.Prices(_nw_gold, _nw_crypto, usd_inr),
    networth_items, lambda plan: allows(plan, "networth"), throttle))


def _nw_value_of(uid: str) -> dict | None:
    p = db.get_profile(uid)
    return money_networth.build(money_networth.load(uid)["items"], _quiet(_nw_stocks, p) if p else None,
                                money_networth.mf_value(uid), money_networth.Prices(_nw_gold, _nw_crypto, usd_inr))


networth_job = money_networth.Job(_nw_value_of)


# ---------- Tax report: capital gains from the user's own tradebooks (everyone) ----------
FMV_LOOKUPS = 20                 # 31 Jan 2018 prices looked up in one request; the rest on the next visit


def upload_bytes(data: str, what: str, limit: int = holdings_file.MAX_BYTES) -> bytes:
    """An uploaded file, from base64 or a data: URL, within the size cap."""
    raw = re.sub(r"^data:[^,]{0,200},", "", data.strip())
    if len(raw) > limit * 4 // 3 + 8:
        err(413, "file_too_big", f"That file is larger than {limit // (1024 * 1024)} MB. {what}")
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        err(400, "bad_upload", "The file didn't arrive whole. Pick it again.")


def tax_match(trades: list[dict]) -> tuple[list[dict], list[str]]:
    """Each trade with its listed company's symbol (`sym`) when one matches; the ones that don't keep what the file
    called them, so their gains still count, without prices or corporate actions."""
    matcher, seen, missed = holdings_matcher(), {}, []
    for t in trades:
        k = (t.get("isin") or "", t.get("symbol") or "", t.get("name") or "")
        if k not in seen:
            hit, _ = matcher.match({"isin": k[0], "symbol": k[1], "name": k[2]})
            seen[k] = hit["symbol"] if hit else None
            if not hit:
                missed.append(t.get("text") or " · ".join(x for x in k if x))
        if seen[k]:
            t["sym"] = seen[k]
    return trades, missed


def fmv_2018(symbol: str) -> float | None:
    """The highest price on 31 Jan 2018 (or the last trading day before it), in today's share units, from the stored
    price history: kept once found. None when it isn't known."""
    got = db.json_value(db.get_setting(f"{tax_lots.FMV_KEY}{symbol}"), {})
    if isinstance(got, dict) and isinstance(got.get("v"), (int, float)) and got["v"] > 0:
        return float(got["v"])
    if not kite.ready():
        return None
    try:
        inst = kite.equity(symbol)
        if not inst:
            return None
        kite._throttle()
        rows = kite.kite.historical_data(inst["token"], datetime(2018, 1, 22), datetime(2018, 1, 31, 23, 59), "day")
        rows = [r for r in rows if str(r["date"])[:10] <= tax_lots.GF_DATE]
        if not rows:
            return None
        v = float(rows[-1]["high"])
    except Exception as e:
        print("31 Jan 2018 price:", symbol, str(e)[:120])
        return None
    db.set_setting(f"{tax_lots.FMV_KEY}{symbol}", json.dumps({"v": v, "at": datetime.now(timezone.utc).isoformat(timespec="minutes")}))
    return v


def tax_inputs(profile) -> dict:
    """What the tax report is worked out from: the saved trades, each company's bonuses and splits, 31 Jan 2018
    prices, today's prices and the holdings."""
    uid = profile["id"]
    data = tax_lots.load(uid)
    # a price the user typed in wins over the one in a broker's file
    trades = [{**t, "fmv": None} if t.get("fmv") and tax_lots.lot_key(t) in data["fmv"] else t for t in data["trades"]]
    today = datetime.now(IST).date()
    syms = sorted({t["sym"] for t in trades if t.get("sym")})
    acts: dict[str, list[dict]] = {}
    # bonuses and splits only change lots from tradebooks (a tax P&L line already shows them), and the 31 Jan 2018
    # price of shares held then: a tax P&L of recent years needs no company's history
    need = sorted({t["sym"] for t in trades if t.get("sym") and (t.get("src") != "pnl" or t["d"] <= tax_lots.GF_DATE)})
    if need:
        corp_actions.prefetch("IN", need)
        _corp_histories(uid, need, today)
        cal = corp_actions.load("IN")["rows"]
        acts = {s: [a for a in corp_actions.actions_for("IN", s, None, today, fetch=False, cal=cal) if corp_actions.adjusts(a)] for s in need}
    fmv, fmv_src = {}, {}
    pre = sorted({tax_lots.lot_key(t) for t in trades if t["side"] == "B" and t["d"] <= tax_lots.GF_DATE})
    looked = 0
    in_file = {k for k in pre if all(t.get("fmv") for t in trades if tax_lots.lot_key(t) == k and t["side"] == "B" and t["d"] <= tax_lots.GF_DATE)}
    for k in pre:
        if k in data["fmv"]:
            fmv[k], fmv_src[k] = data["fmv"][k], "yours"
            continue
        if k in in_file:
            fmv_src[k] = "your file"
            continue
        if k not in syms or looked >= FMV_LOOKUPS:
            continue
        looked += 1
        v = fmv_2018(k)
        if v:
            after = 1.0                  # the stored prices are in today's shares: back to the shares of 2018
            for a in acts.get(k, []):
                if a["ex_date"] > tax_lots.GF_DATE:
                    after *= a["factor"]
            fmv[k], fmv_src[k] = round(v * after, 4), "looked up"
    quotes, live = {}, bool(syms) and kite.ready()
    if live:
        try:
            quotes = kite.quote(syms[:500])
        except Exception:
            live = False
    return {"data": data, "trades": trades, "acts": acts, "fmv": fmv, "fmv_src": fmv_src, "pre": pre, "quotes": quotes,
            "live": live, "items": holdings.indian(holdings.load(uid)["items"]), "today": today.isoformat(), "business": data["business"],
            "income": tax_total.load_inputs(uid)}


def tax_mf(profile) -> dict:
    """The user's mutual fund sales for the tax report (Basic and up), from the Money space."""
    if not allows(profile["_plan"], "mf_gains"):
        return {"rows": [], "names": {}, "years": {}, "allowed": False}
    return {**money_mf.for_tax(profile["id"]), "allowed": True}


def tax_view(profile) -> dict:
    i = tax_inputs(profile)
    mf = tax_mf(profile)
    usr = money_us_routes.for_tax(profile)
    rep = tax_lots.report(i["trades"], i["acts"], i["fmv"], i["quotes"], i["items"], i["today"], i["business"], i["income"],
                          extra=mf["rows"] + usr["rows"], dividends=money_routes.dividends_for_tax(profile), more_years=set(usr["years"]))
    rep["names"].update(mf["names"])
    rep["names"].update(usr["names"])
    for y in rep["years"]:
        y["mutual_funds"] = mf["years"].get(y["fy"])
        y["us"] = {**usr["years"][y["fy"]], "allowed": usr["allowed"], "plan": usr.get("plan")} if y["fy"] in usr["years"] else None
    return {**rep, "us_trades": usr["count"], "mf": {"allowed": mf["allowed"], "count": len(mf["rows"]),
                          "plan": PLANS[FEATURE_PLAN["mf_gains"]]["name"]}, "files": i["data"]["files"], "updated_at": i["data"]["updated_at"], "trades": len(i["trades"]),
            "business_lines": int(sum(b["trades"] for b in i["business"])),
            "prices": i["live"], "prices_at": _prices_at([q for q in i["quotes"].values() if q]) if i["live"] else None,
            "fmv": {k: {"value": i["fmv"].get(k), "source": i["fmv_src"].get(k)} for k in i["pre"]},
            "max_trades": tax_lots.MAX_TRADES}


@app.get("/tax")
def tax_report(profile=Depends(current_profile)):
    """The tax report: realised capital gains per financial year with the estimated tax, the exemption used, the
    set-off, intraday kept apart, and open lots below cost at today's prices. An estimate, not tax advice."""
    return ok(tax_view(profile))


TAX_TOO_BIG = "Split the tradebook by year and upload each one."


@app.post("/tax/import", openapi_extra={"requestBody": {"content": {
    "application/json": {"schema": TaxImportReq.model_json_schema()},
    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
async def tax_import(request: Request, filename: str = Query("", max_length=200), mode: Literal["replace", "add"] = Query("add"),
                     profile=Depends(current_profile)):
    """Read a tradebook, a tax P&L file or the ZIP of them from the user's broker (or a plain CSV of trades) and save
    its trades with the ones already uploaded, duplicates dropped. Lines that can't be read are listed with the reason.

    The file comes as the request body itself (10 MB at most, 20 MB for an F&O, commodity or currency file; the file
    name and mode in the query), which the page sends, or as base64 in JSON ({filename, data, mode}), the older way."""
    body = await request.body()             # the guard has already held the body to its size
    if request.headers.get("content-type", "").split(";")[0].strip().lower() == "application/json":
        try:
            req = TaxImportReq.model_validate_json(body)
        except ValidationError as e:
            raise RequestValidationError(e.errors(include_url=False, include_context=False)) from None
        filename, mode = req.filename, req.mode
        data = upload_bytes(req.data, TAX_TOO_BIG, tax_cap(filename))
    else:
        cap = tax_cap(filename)
        if len(body) > cap:
            err(413, "file_too_big", f"That file is larger than {cap // (1024 * 1024)} MB. {TAX_TOO_BIG}")
        data = body
    return await run_in_threadpool(tax_import_file, profile, data, filename, mode)


def tax_cap(filename: str) -> int:
    """The biggest file the tax import takes: an F&O, commodity or currency file (by its name) runs larger."""
    return holdings_file.FNO_MAX_BYTES if holdings_file.business_kind(filename) and not re.search(r"(?i)\.zip$", filename or "") else holdings_file.TAX_MAX_BYTES


def tax_import_file(profile, data: bytes, filename: str, mode: str) -> dict:
    throttle(profile, "tax_import", 40, 3600, "That's a lot of uploads in an hour. Try again a little later.")
    try:
        parsed = holdings_file.parse_trades(data, filename)
    except holdings_file.FileError as e:
        err(400, "bad_file", str(e))
    trades, missed = tax_match(parsed["trades"])
    div_added = money_routes.import_from_tax_file(profile, data, filename)     # a tax P&L's dividend sheet, if it has one
    before = tax_lots.load(profile["id"])
    old = [] if mode == "replace" else before["trades"]
    merged, added, dup = tax_lots.merge(old, trades)
    over = max(0, len(merged) - tax_lots.MAX_TRADES)
    files = [] if mode == "replace" else before["files"]
    business, b_added, b_replaced, b_same = tax_lots.merge_business([] if mode == "replace" else before["business"],
                                                                   parsed.get("business") or [])
    lines = sum(f["lines"] for f in parsed.get("files", []) if f["section"] in holdings_file.SEGMENT_NAMES.values()) or \
        sum(b["trades"] for b in parsed.get("business") or [])
    if added or b_added or b_replaced:
        files = files + [{"name": (filename or "file")[:80], "broker": parsed["broker"], "kind": parsed["kind"], "trades": added,
                          "fno_lines": lines if (b_added or b_replaced) else 0, "at": datetime.now(timezone.utc).isoformat(timespec="minutes")}]
        tax_lots.save(profile["id"], merged, files, before["fmv"], business)
    elif mode == "replace":
        tax_lots.save(profile["id"], merged, files, before["fmv"], business)
    return ok({"broker": parsed["broker"], "kind": parsed["kind"], "read": len(trades), "added": added, "duplicates": dup,
               "business": {"lines": lines, "added": b_added, "replaced": b_replaced, "same": b_same,
                            "years": sorted({b["fy"] for b in parsed.get("business") or []})},
               "over_limit": over, "problems": parsed["problems"][:200], "problem_count": len(parsed["problems"]),
               "not_listed": missed[:50], "skipped": parsed.get("skipped", []), "check": parsed.get("check", []),
               "files": parsed.get("files", []), "dividends_added": div_added, "report": tax_view(profile)})


@app.put("/tax/fmv")
def tax_fmv(req: TaxFmvReq, profile=Depends(current_profile)):
    """Set (or clear) the 31 Jan 2018 price a share used to grandfather one company's lots bought before 1 Feb 2018."""
    throttle(profile, "tax_edit", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    data = tax_lots.load(profile["id"])
    key = req.symbol.strip().upper()
    if not any(tax_lots.lot_key(t) == key and t["d"] <= tax_lots.GF_DATE for t in data["trades"]):
        err(404, "no_lots", f"Your files have no {key} shares bought before 1 Feb 2018.")
    fmv = {k: v for k, v in data["fmv"].items() if k != key}
    if req.fmv:
        fmv[key] = round(float(req.fmv), 4)
    tax_lots.save(profile["id"], data["trades"], data["files"], fmv, data["business"])
    return ok(tax_view(profile))


@app.put("/tax/inputs")
def tax_income(req: TaxInputsReq, profile=Depends(current_profile)):
    """Save what the total tax estimate needs for one financial year: the regime, other income (and how much of it
    is salary), deductions under the old regime, the age band and residency. Kept with the user's tax data and
    deleted with it."""
    throttle(profile, "tax_edit", 120, 3600, "That's a lot of changes in an hour. Try again a little later.")
    tax_total.save_inputs(profile["id"], req.fy, req.model_dump(exclude={"fy"}))
    return ok(tax_view(profile))


@app.delete("/tax")
def tax_delete(profile=Depends(current_profile)):
    """Delete my tax data: every uploaded trade and file, the income entered for the estimate, and the dividends and
    advance tax figures of the tax tools, at once."""
    tax_lots.delete(profile["id"])
    tax_total.delete_inputs(profile["id"])
    money_routes.delete_all(profile["id"])
    return {"deleted": True}


@app.get("/tax/export")
def tax_export_file(fy: int = Query(..., ge=2000, le=2100), format: str = Query("csv", pattern="^(csv|pdf)$"),
                    profile=Depends(current_profile)):
    """One financial year's report as a CSV (every realised line) or a PDF summary."""
    throttle(profile, "tax_export", 60, 3600, "That's a lot of downloads in an hour. Try again a little later.")
    i = tax_inputs(profile)
    c = tax_lots.compute(i["trades"], i["acts"], i["fmv"], i["today"])
    mf = tax_mf(profile)
    usr = money_us_routes.for_tax(profile)
    c["realised"] += mf["rows"] + usr["rows"]
    c["names"].update(mf["names"])
    c["names"].update(usr["names"])
    equity, units = tax_lots.split_units(c)
    y = tax_lots.with_total(tax_lots.year(fy, equity, c["intraday"], limit=None), i["business"], i["income"].get(fy),
                            money_routes.dividends_for_tax(profile).get(fy, 0.0), instrument_kinds.other_year(fy, units, c["names"]))
    name = f"stratlab-tax-{y['label'].replace(' ', '-')}"
    if format == "pdf":
        below = tax_lots.below_cost(c["open"], i["quotes"], i["today"]) if fy == tax_lots.fy_of(i["today"]) else None
        return Response(tax_export.to_pdf(y, c["names"], below), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return Response(tax_export.to_csv(y, y["rows"], c["names"]), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@app.get("/research/deep/{symbol}/deck")
def deep_dive_deck(symbol: str, region: str = "IN", format: str = "pptx", profile=Depends(current_profile)):
    """The deep dive as a deck, PowerPoint or PDF (the same slides): numbers, business, plans, report card and
    checklist, with sources."""
    region = deep_region(region)
    sym = deep_symbol(symbol, region)
    base = deep_base(sym, region)
    use_deep(profile, "deepdive", sym, region)
    use_deep(profile, "deck", sym, region)
    view = deep_view(sym, base)
    if format == "pdf":
        return Response(deck.build_pdf(view), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{sym}-deep-dive.pdf"'})
    return Response(deck.build(view), media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    headers={"Content-Disposition": f'attachment; filename="{sym}-deep-dive.pptx"'})


@app.post("/research/deep/{symbol}/card")
def deep_dive_card(symbol: str, refresh: bool = False, region: str = "IN", years: int = 2, profile=Depends(current_profile)):
    """The management report card: targets management gave (India: on earnings calls; US: in earnings releases),
    checked against the reported numbers."""
    region = deep_region(region)
    us = region == "US"
    sym = deep_symbol(symbol, region)
    key = f"US:{sym}" if us else sym
    years = deep_years(years)
    base = deep_base(sym, region, years)
    use_deep(profile, "deepdive", sym, region)
    if deepdive.fresh(report_card.stored(key)) and not refresh:
        return ok(deep_view(sym, base))
    kind = "earnings_release" if us else "transcript"
    if not any(d["kind"] == kind for d in base["docs"]):
        err(404, "no_calls", f"No earnings release was found for this company in the last {years} years." if us
            else f"No earnings-call transcript was found for this company in the last {years} years.")
    deep_ai_allowed(profile)
    p = base["p"]
    try:
        if us:
            card = report_card.read_us(sym, p.get("name") or sym, base["docs"], sec_feed, (_gemini, _anthropic), deepdive._fye(p), years)
        else:
            card = report_card.read(sym, p.get("name") or sym, base["docs"], deep_docs, (_gemini, _anthropic), company_hosts(p), years)
    except report_card.NoCalls as e:          # nothing read, nothing charged
        detail = "; ".join(public_text(x) for x in e.problems[:3])
        err(422, "no_readable_calls", ("None of the earnings releases could be read. " if us
                                       else "None of the earnings-call transcripts could be read. ") + (detail or "")[:400])
    except AIBusy as e:
        err(503, "ai_busy", str(e))
    except AIError as e:
        err(422, "ai_failed", str(e))
    card["problems"] = [public_text(x) for x in card["problems"]]
    report_card.store(key, card)
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
def browse_library(market: str = "", verdict: str = "", q: str = "", sort: str = "best", official: bool = False, profile=Depends(current_profile)):
    shown = [e for e in library.all_entries() if library.visible(e, profile["id"]) and (e.get("official") or not official)]
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


PUBLIC_LIBRARY_HEADERS = {"Cache-Control": "public, max-age=300"}


@app.get("/public/library")
def public_library(market: str = "", verdict: str = "", q: str = "", sort: str = "best", limit: int = 100):
    """StratLab's own library strategies, readable without an account: the rules that were tested and the verdict each
    earned, as the app's own backtest gave it. Only entries StratLab published itself and that are not hidden; a user's
    published strategy is never listed here (signed-in people see those in /library)."""
    rows = library.search(library.public_entries(), market.upper()[:10], verdict[:12], q[:80], sort)
    cap = max(1, min(limit, 200))
    return JSONResponse({"entries": [library.public_view(e) for e in rows[:cap]], "total": len(rows), "reasons": library.REASONS},
                        headers=PUBLIC_LIBRARY_HEADERS)


@app.get("/public/library/{eid}")
def public_library_entry(eid: str):
    e = next((x for x in library.public_entries() if x.get("id") == eid), None)
    if not e:
        err(404, "not_found", "That strategy isn't in StratLab's public library.")
    return JSONResponse(library.public_view(e), headers=PUBLIC_LIBRARY_HEADERS)


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


# ---------- company fact cards: an image and a public link that previews as it ----------
def company_card(market: str, symbol: str) -> dict:
    hit = company_cards.find(market, symbol)
    if not hit:
        err(404, "not_found", "There's no public page for that company to share.")
    region, sym, co = hit
    try:
        f = stock_page_store.get(region, sym, co)
    except stock_pages.Busy:
        err(503, "busy", "The company's facts are being prepared. Try again in a few minutes.")
    if not f:
        err(404, "no_facts", "There aren't enough facts on this company to make a card yet.")
    return company_cards.card(f, region, sym)


@app.get("/cards/company/{market}/{symbol}")
def company_card_data(market: str, symbol: str, profile=Depends(current_profile)):
    """What a company's share card shows, for the browser to draw: facts from its public page, never AI."""
    return company_card(market, symbol)


@app.post("/cards/company/{market}/{symbol}")
def share_company_card(market: str, symbol: str, req: ShareReq, profile=Depends(current_profile)):
    """Make (or refresh) the user's public link to a company card, with the image the browser drew."""
    throttle(profile, "card_share", 30, 3600, "That's a lot of shared cards in an hour. Try again later.")
    c = company_card(market, symbol)
    token = company_cards.publish(profile["id"], c, req.image, referrals.code_for(profile["id"]))
    return {"token": token, "url": company_cards.url(token), "card": c}


@app.get("/c/{card}.png")
def company_card_image(card: str):
    png = company_cards.image(card)
    if not png:
        err(404, "not_found", "No image for this link.")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/c/{card}")
def company_card_page(card: str):
    c = company_cards.load(card)
    if not c:
        return RedirectResponse(settings.PUBLIC_SITE_URL + "/")
    return HTMLResponse(company_cards.preview_html(card, c, company_cards.image(card) is not None))


# ---------- public company pages, for search engines ----------
def stock_page_facts(region: str, co: dict) -> dict | None:
    """One company's public page from the deep dive's cheap sources: reported numbers, the filings list and daily
    prices. Never AI. None when the sources have no page for it; a source that is down or busy raises."""
    sym = co["sym"]
    checks: dict = {}
    try:
        if region == "US":
            p = sec.with_fx(dict(sec_feed.company(sym)), usd_per)
            quote = us_price_ratios(p, sym)
            kind = stock_pages.FUND_TYPES.get(str(quote.get("type") or "").upper())
            if kind:                      # an ETN filed under its bank's name, a fund: not a company (R6V-001)
                checks["not_company"] = kind
            items = [{"at": d["at"], "title": d["title"]} for d in p.get("documents") or []]
            exchange, red = "Listed in the US", None
        else:
            p = with_industry(sym, research_hub.screener.company(co["bse"] or sym))
            try:
                found = filings_feed.announcements(sym)
                items = [{"at": i["at"], "title": f"{i['label']}: {i['subject']}" if i.get("subject") else i["label"]} for i in found]
                red = filings.summarise(found)["red"]
            except Exception:
                items, red = [], None
            exchange = "BSE" if co["bse"] else "NSE"
    except SourceError as e:
        if e.busy:
            raise
        return None                       # no company page at the source
    trend = prices = None
    try:
        # closed sessions only, read after the close settled: the page's price is the last close, with its date, never
        # a session still trading or a cached read from before the close (R6V-002)
        bars = stock_pages.closed_bars(stock_page_bars(region, co), region)
        if bars:
            trend, prices = scan.analyse(bars), stock_pages.price_facts(bars)
    except Exception:                     # no prices: the page goes without the price facts
        pass
    close = (prices or {}).get("price")
    if region == "US" and close and not sec.non_common(sym):
        # the ratios at the same close the page shows (the quote read above is the live price), and the dividend yield
        # from the dividends the price history lists for the year to that close: none in the year is a real 0%, a
        # history that couldn't be read is n/a (the filings' dividend line is missing for many foreign filers)
        p["ratios"] = sec.ratios(p, close, prices.get("high52"), prices.get("low52"))
        # the app's own dividends list first (its Corporate actions card), so both pages have one yield (R7O-004)
        dy = page_dividend_yield("US", sym, close, prices.get("price_at"))
        if dy is None:
            try:
                divs = research_hub.yahoo.events(sec.price_symbol(sym), 400)["dividends"]
                dy = stock_pages.dividend_yield(divs, close, prices.get("price_at"))
            except Exception:
                dy = None
        if dy is None:
            p["ratios"].pop("Dividend Yield", None)
        else:
            p["ratios"]["Dividend Yield"] = dy
    if region == "US":
        checks.update(us_cap_checks(p, sym))
        if close and not sec.non_common(sym):
            # one P/E definition, the app's: the close over earnings per share for the last four reported quarters,
            # else the latest year's, said so (R7V-002, R7V-003); the earnings per share itself, for the app's page
            pe, basis = sec.pe_and_basis(p, close)
            if basis:
                checks.update(pe_basis=basis["basis"], pe_end=basis["end"])
                if checks.get("foreign"):
                    # the profit that P/E is on, in dollars: a foreign filer's market value is checked against it (R8V-001)
                    checks["profit_usd"] = sec.basis_profit(p, basis["basis"])
            if pe and pe > 0:
                checks["eps"] = round(close / pe, 4)
    nums = deepdive.numbers(p)
    snap = screener_summary(p)
    if region == "IN":
        if not close:
            # no daily candles: the exchange's own close of the market's last session, dated (R7V-004), before the
            # fundamentals source's undated price
            prices = official_page_close(co) or prices
            close = (prices or {}).get("price")
        # the fundamentals source prices its ratios once a day: re-priced at the last close shown on the same page (as the
        # company page does), so the screens' market value and P/E agree with the price beside them
        snap = at_live_price(snap, close)
        # the dividend yield as the company page in the app works it out: every dividend with an ex-date in the year to
        # the close, specials included, over the close (R7O-004, R7V-002: TCS 3.08% here against 5.35% in the app);
        # n/a when the dividends couldn't be read, never the last reported year's (another definition)
        dy = page_dividend_yield("IN", sym, close, (prices or {}).get("price_at"), co)
        snap = {**snap, "div_yield": dy}
    return stock_pages.facts(region, sym, p, nums, snap, trend, prices, items, exchange, red, checks)


def official_page_close(co: dict) -> dict | None:
    """An Indian company's official close of the market's last settled session, as page prices ({"price", "price_at",
    "price_basis", "price_official"}); None when the exchange's closing prices for that day aren't stored."""
    day = stock_pages.last_close("IN")[0].isoformat()
    try:
        c = official_close.official(co["bse"] or co["sym"], day, use_quote=False)
    except Exception:
        return None
    return {"price": c, "price_at": day, "price_basis": "close", "price_official": True} if c else None


def page_dividend_yield(region: str, sym: str, close, as_of: str | None, co: dict | None = None, fetch: bool = True) -> float | None:
    """A public page's dividend yield from the same dividends list the app's company page uses (its Corporate actions
    card): every dividend with an ex-date in the year to the close, specials included. None when that list has none to
    go on. India (`co` given): the company's own list is read again when it is more than a day old (R7V-002: TCS's
    page fell back to another yield when no list was stored), a list that was read is a real 0% when it holds no
    dividend in the year, and without any list the price history's dividends count. `fetch` False: the stored list
    only, no read of any source (a stored page's yield worked out again as it is served, R8O-001)."""
    if not close or not as_of:
        return None
    if region == "IN" and co is not None:
        try:
            rows = corp_actions.actions_for("IN", sym, corp_job.sources() if fetch else None, fetch=fetch)
            known = bool(corp_actions.hist_load("IN", sym)["at"])
        except Exception:
            rows, known = [], False
        divs = [{"date": str(d.get("ex_date") or ""), "amount": d.get("amount")} for d in rows or []
                if d.get("kind") == "dividend" and d.get("amount")]
        if divs or known:
            return stock_pages.dividend_yield(divs, close, as_of)
        if not fetch:
            return None
        try:
            listed = research_hub.yahoo.events(f"{co['bse']}.BO" if co.get("bse") else f"{sym}.NS", 400)["dividends"]
        except Exception:
            return None
        return stock_pages.dividend_yield(listed, close, as_of)
    try:
        rows = research_routes.stored_dividends(region, sym)
    except Exception:
        return None
    divs = [{"date": str(d.get("ex_date") or ""), "amount": d.get("amount")} for d in rows or []
            if d.get("kind") == "dividend" and d.get("amount")]
    if not divs:
        return None
    return stock_pages.dividend_yield(divs, close, as_of)


def us_cap_checks(p: dict, sym: str) -> dict:
    """What a US page's market value is checked against (stock_pages.cap_problem): the latest twelve months' (or year's)
    revenue in dollars, 0 for a company that reports none; whether its US shares are depositary shares whose ratio to
    ordinary shares couldn't be read; and whether its accounts show dividends paid (a price history with none then
    gives n/a, not 0%)."""
    out: dict = {}
    rate = sec.usd_rate(p)
    if rate:
        sales = sec._latest(p.get("pl"), "Sales")
        out["sales_usd"] = round(float(sales or 0) * rate, 2)
    if not sec.non_common(sym) and (p.get("ads_unread") or not p.get("ads_ratio") and "depositary" in str(p.get("share_note") or "")):
        out["cap_unverified"] = True        # depositary shares of an unknown ratio, or a report that couldn't be read now
    if sec._latest(p.get("cashflow"), "Dividends paid"):
        out["divs_paid"] = True
    if p.get("foreign") is not None:
        out["foreign"] = bool(p["foreign"])
    if p.get("annual_unread"):
        out["annual_unread"] = p["annual_unread"]       # built again within the hour (stock_pages.fresh, R8V-003)
    return out


def stock_page_bars(region: str, co: dict) -> list[dict]:
    """A company's daily candles for its public page, read after its market's latest close settled: a copy cached
    from before then (a session still trading, a last trade before the official close) is read again."""
    ids, _ = universes.resolve(markets, region, [{"symbol": co["bse"] or co["sym"]}])
    if not ids:
        return []
    prov, inst = markets.resolve(ids[0])
    if not prov or not inst:
        return []
    _, at = stock_pages.last_close(region)
    age = time.time() - (at.timestamp() + stock_pages.settle(region))     # how old a copy may be and still be after it
    try:
        bars = prov.history(inst, "1d", scan.DAYS, ttl=max(60.0, age))
    except TypeError:                     # a source without its own cache control: the scan's copy
        bars = scan._bars(markets, ids[0])
    if region == "IN" and bars:
        # the day's close as the exchange states it, not the candle's last trade: the same figure as the company page
        # and the screens (R7O-004: TCS 2,077.00 here against 2,076.00 in the app)
        bars = official_close.overlay_bars(list(bars), co["sym"] if not co.get("bse") else co["bse"])
    return bars


_class_pages: dict = {"names": None, "by_cik": {}}


def us_share_class_page(symbol: str) -> str | None:
    """The page of a US company's other class of common stock (GOOG → GOOGL, BRK.A → BRK-B), from the SEC's list of
    tickers: the company's ticker that has a page. None for a ticker the SEC doesn't list, a preferred share or the like."""
    s = sec.price_symbol(symbol)
    if not s or sec.non_common(s):
        return None
    names = sec_feed.cache.get("tickers")               # the list the daily company list read; never a read of its own
    if not names:
        return None
    if _class_pages["names"] is not names:              # the list is read once a day: the map is built once per list
        cos = stock_pages.companies("US")
        by_cik: dict = {}
        for t, v in names.items():
            if t in cos and not sec.non_common(t):
                by_cik.setdefault(v["cik"], t)
        _class_pages.update(names=names, by_cik=by_cik)
    hit = names.get(s) or names.get(s.replace("-", "."))
    return _class_pages["by_cik"].get(hit["cik"]) if hit else None


stock_pages.share_class_page = us_share_class_page
def stock_page_older_facts(region: str, symbol: str, f: dict | None) -> dict | None:
    """A stored page built before the facts a page shows now, served as it is while no rebuild is allowed (a burst of
    crawlers past the build ration, a source down): an Indian page's dividend yield is worked out again from the
    company's stored dividends list (the app's), so it never shows another definition's yield (R8O-001: TCS 3.08%,
    the last reported year's, against 5.35% on the page's own definition). A US page's likewise, from the company's
    stored dividends list, and n/a when there is none: a page from before PR 172 kept the filings' dividends paid over
    the market value, another definition (R8V-011: P&G 2.93% against 2.85% by ex-date). Its P/E is labelled with the
    year it is on and is n/a past 15 months (stock_pages.pe_period), and a foreign filer's value is checked against its
    profit (stock_pages.cap_problem), as the page is drawn. Anything else waits for the rebuild."""
    if not f or (f.get("v") or 1) >= stock_pages.FACTS_VERSION:
        return f
    if region == "IN":
        try:
            dy = page_dividend_yield("IN", symbol, f.get("price"), f.get("price_at"), {"sym": symbol, "bse": None}, fetch=False)
        except Exception:
            dy = None
        return {**f, "div_yield": dy} if dy is not None else f
    if region == "US" and (f.get("v") or 1) < 4 and not sec.non_common(symbol):
        try:
            rows = corp_actions.actions_for("US", symbol, None, fetch=False)
            known = bool(corp_actions.hist_load("US", symbol)["at"])
        except Exception:
            rows, known = [], False
        divs = [{"date": str(d.get("ex_date") or ""), "amount": d.get("amount")} for d in rows or []
                if d.get("kind") == "dividend" and d.get("amount")]
        dy = stock_pages.dividend_yield(divs, f.get("price"), f.get("price_at")) if divs or known else None
        return {**f, "div_yield": dy}
    return f


stock_page_store = stock_pages.Pages(stock_page_facts, settings.STOCK_PAGE_BUILDS_PER_MINUTE, older=stock_page_older_facts)
research_routes.public_facts = lambda r, s: stock_page_store.peek(r, s)     # the app's US P/E on the public page's EPS (R7O-004)
SEO_HEADERS = {"Cache-Control": stock_pages.CACHE_CONTROL}


def stock_list_job():
    """Once a day: the lists of listed companies (India, NSE and BSE-only; the US), for the sitemaps and pages."""
    time.sleep(240)                         # after startup traffic
    while True:
        for region, fn in (("IN", india_listing), ("US", _sec_companies)):
            try:
                stock_pages.save_list(region, [{"symbol": r["symbol"], "name": r.get("name")} for r in fn()])
            except Exception as e:
                print(f"stock list {region} failed:", str(e)[:160])
        time.sleep(24 * 3600)


@app.get("/stocks", response_class=HTMLResponse)
@app.get("/stocks/", response_class=HTMLResponse, include_in_schema=False)
def stock_index(q: str = "", m: str = ""):
    """Every company page's way in: search by name or symbol (`m`: in or us), and each market's largest companies."""
    r = stock_pages.REGIONS.get((m or "").lower())
    return HTMLResponse(stock_pages.index_page(r if q else None, q), headers=SEO_HEADERS)


@app.get("/stocks/{region}", response_class=HTMLResponse)
@app.get("/stocks/{region}/", response_class=HTMLResponse, include_in_schema=False)
def stock_region_index(region: str, q: str = ""):
    r = stock_pages.REGIONS.get(region.lower())
    if not r:
        return HTMLResponse(stock_pages.not_found(None, region), status_code=404)
    if region != region.lower():
        return RedirectResponse(f"/stocks/{region.lower()}", status_code=301)
    return HTMLResponse(stock_pages.index_page(r, q), headers=SEO_HEADERS)


@app.get("/stocks/{region}/{symbol}/", include_in_schema=False)
def stock_page_slash(region: str, symbol: str):
    """An address with a trailing slash: one address per company, without it (a relative redirect, so it stays on the
    site's own host)."""
    r = stock_pages.REGIONS.get(region.lower())
    hit = stock_pages.find(r, symbol) if r else None
    if not hit:
        return HTMLResponse(stock_pages.not_found(r, symbol), status_code=404)
    return RedirectResponse(stock_pages.path(r, hit[0]), status_code=301)


@app.get("/stocks/{region}/{symbol}", response_class=HTMLResponse)
def stock_page(region: str, symbol: str, ref: str | None = None):
    """A listed company's public page: facts only, built from stored or cheap data, never AI. Opened from a shared
    card, `ref` is the sharer's invite code, and the page's links into the app carry it."""
    r = stock_pages.REGIONS.get(region.lower())
    hit = stock_pages.find(r, symbol) if r else None
    if not hit:
        return HTMLResponse(stock_pages.not_found(r, symbol), status_code=404)
    sym, co = hit
    ref = ref if ref and referrals.CODE.match(ref) else None
    if region != region.lower() or symbol != sym:          # one address per company
        return RedirectResponse(stock_pages.path(r, sym) + (f"?ref={ref}" if ref else ""), status_code=301)
    try:
        page = stock_page_store.html(r, sym, co)
    except stock_pages.Busy:
        # a page a visitor can read, which loads itself again, never raw JSON (R7O-009); still 503 with Retry-After for
        # crawlers, and never cached
        return HTMLResponse(stock_pages.busy_page(r, sym, co.get("name")), status_code=503,
                            headers={"Retry-After": "600", "Cache-Control": "no-store"})
    if (stock_page_store.mem.get(f"stocks:page:{r}:{sym}") or {}).get("not_company"):
        return HTMLResponse(page, status_code=404)             # a fund or a note: no company page (R6V-001)
    if r == "IN":                           # the surveillance lists change daily, so they're added as the page is sent
        page = stock_pages.with_surveillance(page, surveillance.flags_for(sym))
    return HTMLResponse(stock_pages.with_ref(page, ref) if ref else page, headers=SEO_HEADERS)


@app.get("/public/company/{region}/{symbol}")
def public_company(region: str, symbol: str):
    """A company's name and its public page, for the "Sign in to see …" screen a signed-out visitor gets on a company's
    address in the app. Only what the public page itself shows; 404 when the company has no public page."""
    r = stock_pages.REGIONS.get(region.lower())
    hit = stock_pages.find(r, symbol) if r and len(symbol) <= 20 else None
    if not hit:
        err(404, "not_found", "No public page for that company.")
    sym, co = hit
    return {"region": r, "symbol": sym, "name": co.get("name") or sym, "page": stock_pages.path(r, sym)}


@app.get("/public/business")
def public_business():
    """Who runs the site, for the Contact, Terms and Refund pages: the seller's legal name, address and email as set in
    Admin → Invoices (they already print on every invoice). Blank fields stay blank; the pages fall back to config.js."""
    s = invoices.seller()
    return {k: (s.get(k) or "").strip() for k in ("legal_name", "address", "email")}


@app.get("/robots.txt")
def robots_txt():
    return Response(stock_pages.robots(), media_type="text/plain", headers=SEO_HEADERS)


@app.get("/sitemap.xml")
def sitemap_index():
    return Response(stock_pages.sitemap_index(), media_type="application/xml", headers=SEO_HEADERS)


@app.get("/sitemaps/{name}.xml")
def sitemap_file(name: str):
    xml = stock_pages.sitemap(name)
    if xml is None:
        err(404, "not_found", "No such sitemap.")
    return Response(xml, media_type="application/xml", headers=SEO_HEADERS)


# ---------- stock screens: companies filtered by plain facts, from the stored company pages ----------
def screen_warm(region: str, sym: str, co: dict):
    """Build (or refresh) one stored company page for the screens' index, within the pages' per-minute ration."""
    stock_page_store.get(region, sym, co)


screen_indexer = screens.Indexer(lambda r, s, c: screen_warm(r, s, c))
stock_page_store.on_built = screens.note_page       # a page built is in the screens and the largest list at once (R8O-005)

# after each close, how many stored pages' prices are re-read per run, and the pause between reads (seconds): India's
# broker allows a few reads a second, the US prices fewer a minute, and people's own pages and backtests come first
PRICE_REFRESH = {"IN": (300, 1.0), "US": (150, 2.0)}
PRICE_REFRESH_EVERY = 15 * 60
PRICE_REFRESH_BACKLOG = 60                 # seconds between passes while a pass leaves pages behind
price_refresh_status: dict = {"last_run": None, "IN": None, "US": None}


def stock_price_refresh_once(sleep=time.sleep) -> dict:
    """One pass of the price job: every market's stored pages that are a close behind, largest first (R6V-002)."""
    def bars_of(region: str, symbol: str) -> list[dict]:
        co = stock_pages.companies(region).get(symbol)
        return stock_page_bars(region, co) if co else []
    for region, (limit, gap) in PRICE_REFRESH.items():
        # India: a page read at the close before the exchange's official close was out takes it once it is (R7O-004)
        extra = {"official": lambda s, d: official_close.official(s, d, use_quote=False),
                 "official_ready": official_close.settled} if region == "IN" else {}
        try:
            price_refresh_status[region] = stock_page_store.refresh_prices(region, bars_of, scan.analyse, limit=limit, gap=gap, sleep=sleep, **extra)
        except Exception as e:                        # a source or storage down: the next pass tries again
            price_refresh_status[region] = {"error": str(e)[:160]}
    price_refresh_status["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return price_refresh_status


def refresh_backlog(status: dict) -> bool:
    """Whether a pass left pages it had no room for (pages whose new close wasn't out yet wait for the usual pass)."""
    return any(isinstance(s, dict) and s.get("left") for s in (status.get(r) for r in PRICE_REFRESH))


def stock_price_refresh_job():
    """Every quarter of an hour: re-read the prices of stored company pages that are a close behind; a minute apart
    while a pass leaves pages behind, so the long tail reaches the close the same evening, not a session or two later
    (R7V-005: one pass of 150 US pages every quarter of an hour couldn't cover thousands of stored pages overnight)."""
    time.sleep(420)                           # after startup traffic, the company lists and the first screens index
    while True:
        status: dict = {}
        try:
            status = stock_price_refresh_once()
        except Exception as e:
            print("stock price refresh failed:", str(e)[:160])
        time.sleep(PRICE_REFRESH_BACKLOG if refresh_backlog(status) else PRICE_REFRESH_EVERY)
screen_job = screens.Job(lambda uid: db.get_profile(uid), lambda p: screens_limit(access_plan(p)))


def screens_page(profile) -> dict:
    mine = sorted(screens.items(profile["id"]), key=lambda s: s.get("created_at") or "")
    to = alerts.newsletter_email(profile)
    return {"items": [screens.view(s) for s in mine], "limit": screens_limit(profile["_plan"]), "count": len(mine),
            "email": to, "email_confirmed": bool(to) and alerts.email_confirmed(profile)}


@app.get("/research/screens/meta")
def screens_meta(region: str = "IN", profile=Depends(current_profile)):
    """The filters a screen offers in a market, with each one's plain-English help, and how fresh the numbers are."""
    got = screens.meta(region)
    return ok({**got, "pending": stock_pages.day_due(got.get("region") or region, got.get("as_of"))})


@app.post("/research/screens/run")
def screens_run(req: ScreenRunReq, profile=Depends(current_profile)):
    """The companies that meet the filters, from the stored index (never a data source or AI per request)."""
    try:
        got = screens.run(req.region, req.filters or {}, req.sort, req.desc, req.limit, req.offset)
        got["rows"] = with_nse_close(got["region"], got["rows"], "price_at")      # the company page's close (R6O-009)
        # the evening of a session whose closes aren't in the list yet: "Latest 8 Oct · 9 Oct due about 18:30 IST" (R8B-008)
        got["pending"] = stock_pages.day_due(got["region"], got.get("as_of_newest") or got.get("as_of"))
        return ok(got)
    except screens.ScreenError as e:
        err(400, "bad_screen", str(e))


@app.get("/research/screens/saved")
def screens_saved(profile=Depends(current_profile)):
    return ok(screens_page(profile))


def save_screen(profile, req: ScreenSaveReq, sid: str | None = None) -> dict:
    limit = screens_limit(profile["_plan"])
    try:
        s = screens.save(profile["id"], req.model_dump(), limit, sid)
    except screens.ScreenError as e:
        err(400, "bad_screen", str(e))
    except screens.LimitReached as e:
        nxt = next((PLANS[p]["name"] for p in ("basic", "pro") if PLANS[p]["screens"] > e.limit), None)
        upgrade(f"Your plan keeps {e.limit} saved screen{'s' if e.limit != 1 else ''}. Delete one"
                + (f", or move to {nxt} for more." if nxt else " to save another."), "screen_limit")
    if s is None:
        err(404, "not_found", "That screen is gone. Reload the page.")
    return {"screen": screens.view(s), **screens_page(profile)}


@app.post("/research/screens/saved")
def create_screen(req: ScreenSaveReq, profile=Depends(current_profile)):
    throttle(profile, "screen_save", 60, 3600, "That's a lot of saved screens in an hour. Try again later.")
    return ok(save_screen(profile, req))


@app.put("/research/screens/saved/{sid}")
def edit_screen(sid: str, req: ScreenSaveReq, profile=Depends(current_profile)):
    if not screens.valid_id(sid):
        err(404, "not_found", "That screen is gone. Reload the page.")
    throttle(profile, "screen_save", 60, 3600, "That's a lot of screen changes in an hour. Try again later.")
    return ok(save_screen(profile, req, sid))


@app.delete("/research/screens/saved/{sid}")
def delete_screen(sid: str, profile=Depends(current_profile)):
    if not screens.valid_id(sid) or not screens.delete(profile["id"], sid):
        err(404, "not_found", "That screen is gone. Reload the page.")
    return ok(screens_page(profile))


# ---------- market breadth: how many stocks take part in the market's moves ----------
def breadth_load(region: str, symbol: str, days: int) -> list[dict]:
    """A stock's daily candles for the breadth run, kept out of the price cache (a whole market would empty it)."""
    if region == "IN":
        inst = kite.equity(symbol)
        if not inst:
            raise LookupError("not listed")
        return kite.history(inst["token"], "1d", days, store=False)
    return markets.provider(region).history({"token": symbol}, "1d", days)


def breadth_index(region: str, symbol: str, days: int) -> list[dict]:
    if region == "IN":
        hit = kite.by_symbol(symbol)
        if not hit:
            raise LookupError("index not found")
        return kite.history(hit["token"], "1d", days, store=False)
    return markets.provider(region).history({"token": symbol}, "1d", days)


def breadth_alerts(region: str, groups: list[str], now):
    breadth.check_alerts(groups, now, lambda uid: db.get_profile(uid), lambda p: allows(access_plan(p), "breadth"))


breadth_runner = breadth.Runner(lambda r, s, d: breadth_load(r, s, d), lambda r, s, d: breadth_index(r, s, d),
                                lambda name: filings_feed.index_members(name), lambda: filings_feed.all_equities(),
                                after=lambda r, g, now: breadth_alerts(r, g, now))
breadth_job = breadth.Job(breadth_runner, lambda r: kite.ready() if r == "IN" else True)
breadth_live_runner = breadth_live.Live(
    lambda syms: kite.quote(syms), kite.ready,
    lambda region, now: breadth_live.rebuild_base(lambda r, s, d: breadth_load(r, s, d), region, now))
breadth_live_job = breadth_live.LiveJob(breadth_live_runner)


@app.get("/invest/breadth")
def market_breadth(group: str = breadth.DEFAULT, range: str = "1y", brief: bool = False, profile=Depends(current_profile)):
    """A group of stocks' breadth: today's numbers on every plan; the history, charts and sector table on Basic and up."""
    if group not in breadth.GROUPS:
        err(404, "not_found", "Pick a group of stocks from the list.")
    if range not in breadth.RANGES:
        err(400, "bad_range", "Pick a time range from the list.")
    out = breadth.view(group, range, full=allows(profile["_plan"], "breadth"), brief=brief)
    out["plan_needed"] = PLANS[FEATURE_PLAN["breadth"]]["name"]
    live = breadth_live.view(group, ready=kite.ready())
    if brief and live:
        # the Invest home's card: the newest live point only (R7T-010: the card showed the 8 Oct close after the open
        # while the breadth page was live)
        live = {**live, "points": live["points"][-1:]}
    out["live"] = live
    # after the close, before the evening's count: the page and the card say the newest day and when the next is due (R8B-008)
    region = out["group"].get("region") or "IN"
    # a group with no live view (the US) says so while its session trades too, and when its count comes (R9R-007)
    out["pending"] = stock_pages.day_due(region, (out.get("today") or {}).get("day") or out.get("as_of"),
                                         due=breadth.due_label(region), during=region not in breadth_live.LIVE_REGIONS)
    return ok(out)


def breadth_alerts_view(profile) -> dict:
    return {"items": breadth.alerts_of(profile["id"]), "limit": breadth.MAX_ALERTS, "channels": stock_alerts.channels(profile)}


@app.get("/invest/breadth/alerts")
def breadth_alert_list(profile=Depends(current_profile)):
    """The user's alerts on a group's share of stocks above the 50-day average, and where they would be sent."""
    return ok(breadth_alerts_view(profile))


@app.post("/invest/breadth/alerts")
def breadth_alert_add(req: BreadthAlertReq, profile=Depends(current_profile)):
    need(profile, "breadth", "Market breadth alerts")
    throttle(profile, "breadth_alert", 30, 3600, "That's a lot of alert changes in an hour. Try again later.")
    try:
        breadth.add_alert(profile["id"], req.group, req.level)
    except breadth.AlertError as e:
        err(400, "bad_alert", str(e))
    return ok(breadth_alerts_view(profile))


@app.delete("/invest/breadth/alerts/{aid}")
def breadth_alert_delete(aid: str, profile=Depends(current_profile)):
    if not breadth.delete_alert(profile["id"], aid[:24]):
        err(404, "not_found", "That alert is gone. Reload the page.")
    return ok(breadth_alerts_view(profile))


@app.post("/admin/breadth/run")
def admin_breadth_run(region: str = "IN", full: bool = False, _=Depends(admin.admin_profile)):
    """Work out a market's breadth now, in the background (the whole two years with `full`)."""
    if region not in breadth.REGIONS:
        err(400, "bad_region", "India (IN) or the US.")
    if breadth_runner.running:
        err(409, "busy", "A breadth run is already going.")

    def work():
        breadth._set_status(region, started_at=breadth._now(), last_error=None)
        try:
            r = breadth_runner.run(region, full=full or None)
            if isinstance(r, dict) and r.get("ok") is False:
                breadth._set_status(region, last_error=str(r.get("error") or "")[:200], failed_at=breadth._now())
        except Exception as e:
            print("breadth run failed:", region, str(e)[:160])
            breadth._set_status(region, last_error=str(e)[:200], failed_at=breadth._now())
    threading.Thread(target=work, daemon=True, name="breadth-now").start()
    return {"started": True, "region": region, "status": breadth.status()}


@app.post("/admin/redflags/run")
def admin_redflags_run(region: str = "IN", _=Depends(admin.admin_profile)):
    """Read a region's red-flag filings now, in the background (India: the exchange's announcements; US: 8-K items and 13D/13G)."""
    if region not in redflags.REGIONS:
        err(400, "bad_region", "India (IN) or the US.")
    if redflags_runner.running:
        err(409, "busy", "A red-flag read is already going.")

    def work():
        try:
            redflags_runner.run(region)
        except Exception as e:
            print("red-flag read failed:", region, str(e)[:160])
            redflags._set_state(region, last_error=str(e)[:200], failed_at=redflags._now())
    threading.Thread(target=work, daemon=True, name="redflags-now").start()
    return {"started": True, "region": region, "state": redflags.state(region)}


@app.get("/admin/business-updates/reliability")
def admin_biz_reliability(_=Depends(admin.admin_profile)):
    """Which sectors and companies read into checked figures, from the filings read so far."""
    return biz_updates.reliability()


@app.get("/admin/breadth")
def admin_breadth(_=Depends(admin.admin_profile)):
    """Each market's last breadth run, and whether one is going now."""
    return {"status": breadth.status(), "job": breadth_job.status, "running": breadth_runner.running,
            "live": breadth_live.status(), "live_job": breadth_live_job.status}


@app.get("/admin/storage")
def admin_storage(_=Depends(admin.admin_profile)):
    """How full the main database is (and the second one, when it's set up), its biggest tables and settings."""
    return storage.report()


@app.post("/admin/storage/move")
def admin_storage_move(_=Depends(admin.admin_profile)):
    """Move the market-wide data to the second database, in the background."""
    if market_store.store() is None:
        err(400, "no_market_db", "Add a Postgres on Railway and set MARKET_DATABASE_URL on the backend first.")
    if not storage.start_move():
        err(409, "busy", "A move is already running.")
    return {"started": True}


@app.delete("/notebooks/{nid}/experiments/{version}")
def delete_experiment(nid: str, version: int, profile=Depends(current_profile)):
    nb = get_notebook(profile, nid)
    if not any(e["v"] == version for e in nb.get("experiments") or []):
        err(404, "not_found", "Experiment not found.")
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
            upgrade(str(e) + lift(profile["_plan"], "live_limit", "paper sessions"), "live_limit")
        if isinstance(e, ValueError):
            err(400, "cannot_start", str(e))
        if not isinstance(e, HTTPException):     # the price feed failed while loading the warm-up candles
            report(e, where="start paper session")
            err(503, "prices_unavailable", "Couldn't load the price history this strategy needs to start. Nothing was "
                                           "started; try again in a minute.")
        raise
    invite_rewards.safe_touch(profile, "paper")
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
             "ts": e["t"]} for e in reversed(events[-200:]) if "side" in e]     # an options skip line isn't an order


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
    if exchange not in ("NFO", "BFO", "MCX", "CDS") or not re.fullmatch(r"[A-Z0-9&-]{1,30}", underlying) or \
            not re.fullmatch(r"current|next|month|\d{4}-\d{2}-\d{2}", expiry):
        err(400, "bad_request", "Pick an exchange, an underlying and an expiry.")
    # each strike's IV and Greeks are model estimates, on every plan
    return opt_greeks.add_to_chain(options_data.chain(exchange, underlying, expiry), positioning.ist_now())


# ---------- derivatives positioning (Trade) ----------
def _pos_name(name: str) -> str:
    if name not in positioning.NAMES:
        err(400, "bad_request", "Pick NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY or SENSEX.")
    return name


@app.get("/trade/positioning")
def trade_positioning(brief: bool = False, pcr: bool = True, profile=Depends(current_profile)):
    """The newest participant-wise open interest and volume, FII/DII cash flows and each index's PCR (left out with
    pcr=false, for the page that asks for them on their own). Today's numbers are on every plan; the history and the
    IV percentile and rank are on Basic and up."""
    out = positioning.summary(options_data, allows(profile["_plan"], "positioning"), brief=brief, with_pcr=pcr)
    out["plan_needed"] = PLANS[FEATURE_PLAN["positioning"]]["name"]
    return ok(out)


@app.get("/trade/positioning/pcr")
def trade_positioning_pcr(profile=Depends(current_profile)):
    """Each index's nearest-expiry put-call ratio now: the live chain, else the newest recording."""
    return ok({"pcr": positioning.pcr_table(options_data)})


@app.get("/trade/positioning/chain")
def trade_positioning_chain(name: str = "NIFTY", expiry: str = "current", profile=Depends(current_profile)):
    """One index's option chain as facts: open interest and its change by strike, PCR, max pain, ATM IV."""
    _pos_name(name)
    if not re.fullmatch(r"current|next|\d{4}-\d{2}-\d{2}", expiry):
        err(400, "bad_request", "Pick an expiry.")
    out = positioning.chain_view(options_data, name, expiry, full=allows(profile["_plan"], "positioning"))
    out["plan_needed"] = PLANS[FEATURE_PLAN["positioning"]]["name"]
    return ok(out)


@app.get("/trade/positioning/history")
def trade_positioning_history(kind: str = "participants", name: str = "NIFTY", range: str = "6m", profile=Depends(current_profile)):
    """The stored history behind the charts: participants' positions, cash flows, or an index's PCR, max pain and IV."""
    need(profile, "positioning", "Positioning history")
    if kind not in ("participants", "cash", "chain") or range not in positioning.RANGES:
        err(400, "bad_request", "Pick what to chart and a time range.")
    return ok(positioning.history_view(kind, _pos_name(name), range))


@app.post("/admin/positioning/run")
def admin_positioning_run(backfill: bool = False, _=Depends(admin.admin_profile)):
    """Read the newest trading day's files now (or walk the archives back a step), in the background."""
    if positioning_runner.running:
        err(409, "busy", "A positioning run is already going.")
    day = positioning.expected_day(positioning.ist_now())

    def work():
        try:
            if backfill:
                positioning_runner.backfill(positioning.ist_now().date())
            elif day:
                positioning_job.status["last_result"] = positioning_runner.run_day(day)
        except Exception as e:
            print("positioning run failed:", str(e)[:160])
    threading.Thread(target=work, daemon=True, name="positioning-now").start()
    return {"started": True, "day": day.isoformat() if day else None, "state": positioning.state()}


@app.get("/admin/positioning")
def admin_positioning(_=Depends(admin.admin_profile)):
    """The positioning job's last run, the archive walk and each part's state."""
    return {"state": positioning.state(), "job": positioning_job.status, "running": positioning_runner.running}


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
    # a strike rule (delta, premium, a share of the straddle) picks on the quotes of the strikes near the money now
    rq = options_data.quotes(opt_strikes.keys_for(c, atm, s.legs)) if opt_strikes.uses_rules(s.legs) else {}
    rm = opt_strikes.model_for(c, atm, spot, rq, positioning.ist_now()) if opt_strikes.needs_model(s.legs) else None
    for lg in s.legs:
        why = None
        if lg.pick == "offset":
            k = c.strike_for(atm, lg.opt, lg.offset, s.offsetUnit)
        else:
            k, why = opt_strikes.pick(c, atm, lg, rq, rm)
        legs.append({"side": lg.side, "opt": lg.opt, "lots": lg.lots, "strike": k, "key": c.key(lg.opt, k) if k is not None else None,
                     "rule": opt_strikes.describe(lg, s.offsetUnit), "pick": why})
    q = options_data.quotes([l["key"] for l in legs if l["key"]])
    for l in legs:
        l["quote"] = q.get(l["key"]) if l["key"] else None
        l["fill"] = fill_price(l["quote"], l["side"], s.costs.slippageTicks)
        l["sym"] = l["key"].split(":", 1)[1] if l["key"] else None
    freeze = s.costs.freeze or freeze_limit(s.underlying)
    units = s.sizing.lots
    margin_one = margin_all = None
    if all(l["key"] for l in legs):
        basket = [{"key": l["key"], "side": l["side"], "qty": l["lots"] * c.lot} for l in legs]
        margin_one = options_data.margin(basket)
        if s.sizing.mode == "margin" and margin_one:
            units = max(0, int(s.sizing.capital * s.sizing.safety // margin_one))
        if margin_one and units:
            margin_all = options_data.margin([{**b, "qty": b["qty"] * units} for b in basket])
    priced = [{"side": l["side"], "opt": l["opt"], "strike": l["strike"], "fill": l["fill"], "qty": l["lots"] * units * c.lot}
              for l in legs if l["strike"] is not None and l["fill"] is not None]
    charges = (opt_charges.summary(priced, opt_charges.kind_for(s.exchange), s.costs.brokerage, freeze)
               if units and priced and len(priced) == len(legs) else None)
    return {"spot": spot, "atm": atm, "step": c.step(spot), "expiry": c.expiry, "lot": c.lot, "freeze": freeze,
            "units": units, "margin_one": margin_one, "margin": margin_all, "legs": legs, "charges": charges,
            "strikes": c.strikes, "expiries": options_data.expiries(s.exchange, s.underlying)[:6],
            "spot_ts": (options_data.quotes([sk]).get(sk) or {}).get("ts"),
            **_preview_greeks(c, spot, legs, units)}


def _preview_greeks(c, spot: float, legs: list[dict], units: int) -> dict:
    """The model's view of a priced structure, for every plan: the shared inputs, each leg's IV and Greeks, and the
    net Greeks of the whole position (empty when the expiry has passed)."""
    m = opt_greeks.live_model(options_data, c, spot, positioning.ist_now())
    if not m:
        return {"model": None, "greeks": None}
    have = [l for l in legs if l["strike"] is not None]
    pos = opt_greeks.position([{**l, "qty": l["lots"] * max(units, 1) * c.lot} for l in have], m)
    per = iter(pos["legs"])
    pos["legs"] = [next(per) if l["strike"] is not None else None for l in legs]
    return {"model": opt_greeks.public_model(m), "greeks": pos}


def _held(req: OptGreeksReq, expiry: str | None = None):
    """The contracts, spot and model for a request's underlying and expiry, or a clear error."""
    options_ready()
    c = options_data.contracts(req.exchange, req.underlying, expiry or req.expiry)
    if not c:
        err(404, "no_contracts", f"No {req.underlying} options are listed on {req.exchange} for that expiry.")
    sk = options_data.spot_key(req.exchange, req.underlying, c.expiry)
    spot = (options_data.quotes([sk]).get(sk) or {}).get("ltp") if sk else None
    if not spot:
        err(503, "no_spot", f"Couldn't get the {req.underlying} price just now.")
    m = opt_greeks.live_model(options_data, c, spot, positioning.ist_now())
    if not m:
        err(409, "expired", "That expiry has passed, so there's nothing left to model.")
    return c, spot, m


def _other(side: str) -> str:
    return "buy" if side == "sell" else "sell"


@app.post("/options/greeks")
def options_greeks(req: OptGreeksReq, profile=Depends(current_profile)):
    """A position's model IV and Greeks on today's quotes, leg by leg and net, with what closing every leg now would
    cost in charges (the session page). Model estimates, on every plan."""
    c, spot, m = _held(req)
    legs = [l.model_dump() for l in req.legs]
    keys = [c.key(l["opt"], l["strike"]) for l in legs]
    q = options_data.quotes([k for k in keys if k])
    for l, k in zip(legs, keys):
        l["quote"] = q.get(k) if k else None
    pos = opt_greeks.position(legs, m)
    closes = [{"side": _other(l["side"]), "qty": l["qty"], "fill": fill_price(l["quote"], _other(l["side"]), 0)} for l in legs]
    kind = opt_charges.kind_for(req.exchange)
    cost = (opt_charges.orders_cost(closes, kind, req.brokerage, req.freeze or freeze_limit(req.underlying))
            if all(x["fill"] is not None for x in closes) else None)
    return {"model": opt_greeks.public_model(m), "spot": spot, **pos,
            "close_charges": {"total": round(cost["total"], 2), "orders": cost["orders"], "items": opt_charges.labelled(cost["items"], kind)} if cost else None}


@app.post("/options/roll")
def options_roll(req: OptRollReq, profile=Depends(current_profile)):
    """Close one leg and open another strike or expiry in its place, priced on today's bid and ask: the premium that
    changes hands, the charges of the two orders, and the position's net Greeks before and after (model estimates).
    Pro."""
    need(profile, "options_whatif", "The roll preview")
    if req.leg >= len(req.legs):
        err(400, "bad_request", "Pick one of the position's legs.")
    c, spot, m = _held(req)
    c2, m2 = c, m
    if req.to_expiry and req.to_expiry != c.expiry:
        c2, _, m2 = _held(req, req.to_expiry)
    if req.strike not in c2.strikes:
        err(400, "bad_strike", "That strike isn't listed for that expiry.")
    legs = [l.model_dump() for l in req.legs]
    old = legs[req.leg]
    keys = [c.key(l["opt"], l["strike"]) for l in legs]
    new_key = c2.key(old["opt"], req.strike)
    q = options_data.quotes([k for k in keys + [new_key] if k])
    for l, k in zip(legs, keys):
        l["quote"] = q.get(k) if k else None
    close_side = _other(old["side"])
    close_px = fill_price(old["quote"], close_side, 0)
    open_px = fill_price(q.get(new_key), old["side"], 0)
    if close_px is None or open_px is None:
        err(409, "no_quote", "One of the two contracts has no price right now, so the roll can't be priced.")
    new = {**old, "strike": req.strike, "fill": open_px, "quote": q.get(new_key)}
    before = opt_greeks.position(legs, m)
    new_g = opt_greeks.position([new], m2)
    after_legs = [(l, g) for i, (l, g) in enumerate(zip(legs, before["legs"])) if i != req.leg] + [(new, new_g["legs"][0])]
    sign = 1 if old["side"] == "sell" else -1           # a sold leg pays to close and takes in the new premium
    premium = sign * (open_px - close_px) * old["qty"]
    kind = opt_charges.kind_for(req.exchange)
    cost = opt_charges.orders_cost([{"side": close_side, "qty": old["qty"], "fill": close_px},
                                    {"side": old["side"], "qty": old["qty"], "fill": open_px}],
                                   kind, req.brokerage, req.freeze or freeze_limit(req.underlying))
    return {
        "leg": req.leg, "spot": spot,
        "close": {"opt": old["opt"], "strike": old["strike"], "expiry": c.expiry, "side": close_side, "px": close_px,
                  "sym": keys[req.leg].split(":", 1)[1] if keys[req.leg] else None},
        "open": {"opt": old["opt"], "strike": req.strike, "expiry": c2.expiry, "side": old["side"], "px": open_px,
                 "sym": new_key.split(":", 1)[1] if new_key else None, **new_g["legs"][0]},
        "premium": round(premium, 2),
        "charges": {"total": round(cost["total"], 2), "orders": cost["orders"], "items": opt_charges.labelled(cost["items"], kind)},
        "net": round(premium - cost["total"], 2),
        "before": opt_greeks.net(legs, before["legs"]), "after": opt_greeks.net(*map(list, zip(*after_legs))),
        "complete": before["complete"] and new_g["complete"],
        "model": opt_greeks.public_model(m), "model_to": opt_greeks.public_model(m2),
    }


@app.post("/options/sessions")
def start_options(req: OptionStartReq, profile=Depends(current_profile)):
    need(profile, "options", "Options paper trading")
    s = req.strategy
    if s.signal:
        need(profile, "options_signal", "Options entered on a notebook's signal")
    if opt_strikes.uses_rules(s.legs):
        need(profile, "strike_rules", "Picking strikes by delta or premium")
    if s.vix:
        need(profile, "vix_filter", "The India VIX entry filter")
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


# ---------- billing ----------
def not_viewing(profile) -> None:
    """Billing is the real account's. While the owner views the app as a plan, it is closed (the Plans page would be
    showing a plan they don't have), so a click there can never start a subscription."""
    if profile.get("_view_as"):
        err(409, "view_as_on", "You're viewing as another plan. Turn off View as to change your billing.")


@app.post("/billing/subscribe")
def subscribe(req: SubscribeReq, profile=Depends(current_profile)):
    not_viewing(profile)
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
    not_viewing(profile)
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
    return Response(invoices.html(inv), media_type="text/html; charset=utf-8", headers={"Content-Security-Policy": invoices.CSP})


@app.get("/admin/invoices")
def admin_invoices(year: str = "", _=Depends(admin.admin_profile)):
    """Seller details and every invoice of a financial year (this one by default), for the accounts."""
    fy = year or invoices.fy(datetime.now(timezone.utc))
    rows = invoices.of_year(fy)
    return {"seller": invoices.seller(), "seller_status": invoices.readiness(), "states": invoices.STATES, "year": fy,
            "invoices": [{k: i[k] for k in ("number", "date", "total", "currency", "supply")} | {"email": i["buyer"].get("email"),
                         "tax": round(sum(t["amount"] for t in i["taxes"]), 2)} for i in rows]}


@app.put("/admin/invoices/seller")
def admin_invoice_seller(req: SellerReq, _=Depends(admin.admin_profile)):
    try:
        return {"seller": invoices.save_seller(req.model_dump()), "seller_status": invoices.readiness()}
    except ValueError as e:
        err(400, "bad_seller", str(e))


@app.post("/billing/cancel")
def cancel(profile=Depends(current_profile)):
    not_viewing(profile)
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
        # database reads and writes: off the event loop, so every other request keeps being answered meanwhile (R9R-010)
        await run_in_threadpool(billing.handle_webhook, body, request.headers.get("X-Razorpay-Signature", ""),
                                request.headers.get("X-Razorpay-Event-Id", ""))
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
    if state.startswith(connect_kite.STATE_PREFIX):        # a user connecting their own Zerodha (the Kite app has one redirect address)
        return connect_routes._kite_done(request_token, status, state)
    if status != "success" or not request_token:
        return HTMLResponse("<p>Kite login was cancelled or failed.</p>", status_code=400)
    try:
        kite.complete_login(request_token, state)
    except PermissionError as e:
        return HTMLResponse(f"<p>{html_escape(str(e))}</p>", status_code=403)
    return HTMLResponse(f"<p>{html_escape(after_login())}</p><p><a href=\"{html_escape(settings.PUBLIC_SITE_URL)}/admin\">Back to the admin page</a></p>")


def session_counts(sessions: list) -> dict:
    """The running paper sessions Admin's live price feed light counts: the ones that need the broker's streaming feed
    (India's cash and futures; other markets are polled), and India's options sessions, which read the broker's quotes
    every few seconds instead of the feed and are running all the same (R7T-012: "Idle: no India paper sessions running"
    beside a running NIFTY options session)."""
    return {"india_sessions": sum(1 for x in sessions if not getattr(x, "polled", False)),
            "options_sessions": sum(1 for x in sessions if getattr(x, "kind", None) == "options")}


def running_now(sessions: dict, stopped: set | None = None) -> list:
    """The paper sessions running now, each once ({id: session} as the manager keeps them): one whose stored row says it
    stopped (stopped elsewhere, its row changed while it stayed in memory) isn't counted (R8O-011)."""
    by_id = {}
    for key, s in sessions.items():
        sid = getattr(s, "id", None) or key
        if sid not in (stopped or ()):
            by_id[sid] = s
    return list(by_id.values())


def server_status() -> dict:
    current = dict(manager.sessions)
    try:
        stopped = db.stopped_among([getattr(s, "id", None) or k for k, s in current.items()])
    except Exception:
        stopped = None
    live = running_now(current, stopped)
    return {"kite_ready": kite.ready(), "kite_token_day": kite.token_day, "kite_invalid": kite.invalid_reason, "feed_started": hub.started,
            "feed_connected": hub.connected, "live_sessions": len(live),
            # the sessions that need the broker's live feed (India); other markets are polled and never use it
            **session_counts(live),
            # whose they are: Admin counts every user's sessions, and says so when they are more than one person's (R8O-011)
            "options_users": len({getattr(s, "user_id", None) for s in live if getattr(s, "kind", None) == "options"}),
            "subscribed_tokens": len(hub.listeners), "auto_login": auto_login.last,
            "auto_login_configured": auto_login_configured(),
            "billing_enabled": billing.enabled(), "ai": ai_health(),
            "research": {"finnhub": bool(settings.FINNHUB_API_KEY)},
            "promo_until": (promo_until().isoformat() if promo_active() else None), "option_recorder": recorder.status, "recent_errors": list(reversed(RECENT_ERRORS)), "server_started_at": SERVER_STARTED_AT,
            "calendar": calendar_status(), "invoice_seller": invoices.readiness(),
            "admin_alerts": {"email_ready": alerts.email_ready(), "via": alerts.email_service(), "to": sorted(admin.admin_emails())}}


def calendar_status() -> dict:
    """How far ahead exchange holidays are known. India in detail (the installed calendar, the exchange's own list,
    fetched daily, and anything the admin pasted), and a row for every market."""
    until = trading_calendar.known_until("IN")
    added = sorted(trading_calendar.extra_holidays("IN"))
    auto = trading_calendar.auto_status("IN")
    today = datetime.now(IST).date()
    covered = trading_calendar.covered_until("IN")
    last = covered.isoformat() if covered else None
    days_left = (covered - today).days if covered else None
    return {"known_until": until.isoformat() if until else None, "added": added, "covered_until": last, "days_left": days_left,
            "auto": {"at": auto.get("at"), "tried_at": auto.get("tried_at"), "error": public_text(auto.get("error")),
                     "count": len(auto.get("days") or [])},
            "markets": trading_calendar.all_coverage(today)}


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


@app.post("/admin/etf-gaps/refresh")
def admin_etf_gaps_refresh(_=Depends(admin.admin_profile)):
    """Read the exchange's ETF list now (the job reads it every few minutes in market hours) and say how many ETFs it gave."""
    try:
        parsed = etf_nav.refresh(filings_feed)
    except Exception as e:
        etf_job.status["last_error"] = str(e)[:200]
        err(502, "etf_list_unavailable", f"The exchange's ETF list couldn't be read: {public_text(str(e)[:160])}")
    etf_job.status.update(read=datetime.now(timezone.utc).isoformat(timespec="minutes"), last_error=None)
    return {"etfs": len(parsed["rows"]), "as_of": parsed["as_of"], "job": etf_job.status}


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
    return {"server": server_status(), "stats": {**admin.stats(month_start_iso()), "plan_interest": plan_interest.count()}}


@app.get("/admin/users")
def admin_users(q: str = "", plan: str = "", _=Depends(admin.admin_profile)):
    """The newest 200 users, or those whose email contains `q`, on `plan` (free, basic or pro) when given."""
    if plan and plan not in PLANS:
        err(400, "bad_plan", "Pick Free, Basic or Pro.")
    return admin.users(q, month_start_iso(), plan=plan or None)


@app.get("/admin/invite-rewards")
def admin_invite_rewards(_=Depends(admin.admin_profile)):
    """Invite rewards: those waiting for review (a link with more than 5 sign-ups in a day), and the newest given."""
    return {**invite_rewards.admin_view(), "job": invite_job.status}


@app.post("/admin/invite-rewards/{user_id}/{decision}")
def admin_review_invite_reward(user_id: str, decision: str, who=Depends(admin.admin_profile)):
    """Approve or reject a reward waiting for review. Approved, it's given once the friend is active."""
    if decision not in ("approve", "reject") or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
        err(404, "not_found", "That reward isn't waiting for review.")
    status = invite_rewards.review(user_id, decision == "approve")
    if status is None:
        err(404, "not_found", "That reward isn't waiting for review.")
    log.info("admin %s: invite reward for %s, %s -> %s", who.get("email"), user_id, decision, status)
    return {"status": status, **invite_rewards.admin_view()}


@app.post("/admin/users/{user_id}/plan")
def admin_set_plan(user_id: str, req: AdminPlanReq, who=Depends(admin.admin_profile)):
    row = admin.set_plan(user_id, req.plan, req.days)
    log.info("admin %s set %s to %s (%s days)", who.get("email"), row.get("email"), req.plan, req.days)
    return {"ok": True}


@app.post("/admin/users/{user_id}/delete-data")
def admin_delete_user_data(user_id: str, who=Depends(admin.admin_profile)):
    """Erase one user's app data (drawings, Connect records, holdings, net worth, notebooks, alerts, preferences and the
    like). The sign-in account and the billing record stay."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", user_id):
        err(404, "no_user", "No user with that ID.")
    rows = db.sb().table("profiles").select("id,email").eq("id", user_id).execute().data
    if not rows:
        err(404, "no_user", "No user with that ID.")
    out = user_data.erase(user_id)
    log.info("admin %s erased the app data of %s: %d areas done, %d failed", who.get("email"), rows[0].get("email"),
             len(out["done"]), len(out["failed"]))
    return {"ok": not out["failed"], "email": rows[0].get("email"), **out}


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
                    "equity": account.get("equity"), "trades": account.get("trades"),
                    # the account's currency, so its money is grouped as that currency writes it (Rs47,53,636, $10,000)
                    "currency": s.inst.get("currency") or ("INR" if getattr(s, "market", s.inst.get("market")) == "IN" else "USD")})
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


def live_price(sym: str):
    """The live exchange quote from the broker's feed: last price, previous close, the day's range and the time of
    the last trade, for audit.check_prices; the exchange's own last price when the feed is offline (its website turns
    cloud servers away, so that is a last resort). Works for NSE symbols and BSE-only codes alike."""
    if kite.ready():
        q = kite.quote([sym]).get(sym) or {}
        return {k: q.get(k) for k in ("price", "prev_close", "low", "high", "at")}
    return filings_feed.last_price(sym)


def audit_one(sym: str, docs: bool, exchange=None, region: str = "IN") -> dict:
    us = region == "US"
    read = (lambda cands, probs, p: deepdive.readable(deep_docs, cands, 1, probs, company_hosts(p))) if docs and not us else None
    row = audit.audit_company(sym, lambda s: deep_base(s, region, trades=False), deep_view, None if us else exchange, read)
    for i in row["issues"]:
        i["detail"] = public_text(i["detail"])
    return row


_market_breaker: list = [None, 0.0]


def _nse_check(sym: str) -> dict:
    """One company for the whole-market audit; the exchange-price breaker is renewed every six hours, so a refusal
    in the morning doesn't leave the rest of the day unchecked."""
    if time.time() - _market_breaker[1] > 6 * 3600:
        _market_breaker[:] = [audit.Breaker(live_price), time.time()]
    return audit_one(research_routes.symbol_of(sym), False, _market_breaker[0])


BSE_ONLY = "audit:bse-only"                # the last good list of BSE-only companies: {code: {ts, token, name}}


def bse_only(nse: list[dict]) -> list[dict]:
    """Companies listed on BSE but not on NSE: the broker's BSE equity list less every NSE symbol and company name.
    Kept as the last good list, so a broker outage never looks like thousands of delistings. The first time, none
    of them counts as a new listing."""
    try:
        saved = json.loads(db.get_setting(BSE_ONLY) or "{}")
    except (ValueError, TypeError):
        saved = {}
    if not kite.ready():
        got = saved
    else:
        listed = [{"symbol": r["symbol"], "name": r.get("name") or r["symbol"], "exchange": "NSE", "type": "EQ"} for r in nse]
        got = {str(x["exchange_token"]): {"ts": x["tradingsymbol"], "token": int(x["instrument_token"]), "name": x.get("name") or x["tradingsymbol"]}
               for x in bse_only_rows(kite.instruments_of("BSE"), listed)}   # on NSE too: already in the audit
        if len(got) < 100 and saved:                   # a broken answer: keep the last good list
            got = saved
        elif got:
            db.set_setting(BSE_ONLY, json.dumps(got))
    _bse_map.clear()
    _bse_map.update(got)
    first = not saved                         # the first list: these are the market, not new listings
    return [{"symbol": f"BSE:{c}", "name": v["name"], "listed": None, "old": first} for c, v in got.items()]


_bse_map: dict[str, dict] = {}


def india_listing() -> list[dict]:
    nse = filings_feed.all_equities()
    try:
        return nse + bse_only(nse)
    except Exception as e:                    # the NSE list alone, rather than nothing
        print("BSE-only list unavailable:", e)
        return nse


def _load_bse_map():
    if not _bse_map:
        try:
            _bse_map.update(json.loads(db.get_setting(BSE_ONLY) or "{}"))
        except (ValueError, TypeError):
            pass


def bse_code(sym: str) -> str | None:
    """The BSE scrip code when `sym` is a company listed only on BSE (its six-digit code, or its BSE symbol);
    None for an NSE company."""
    s = (sym or "").strip().upper()
    if s.isdigit() and len(s) == 6:
        return s
    if kite.ready():
        try:
            hit = kite.equity(s)
        except Exception:
            hit = None
        if hit:
            return hit.get("bse_code") if hit["exchange"] == "BSE" else None
    _load_bse_map()                           # the broker offline: the saved BSE-only list
    return next((c for c, v in _bse_map.items() if str(v.get("ts") or "").upper() == s), None)


def bse_twin(sym: str) -> str | None:
    """The BSE scrip code of an NSE company's other listing (same symbol, else the same company name); None when the
    broker is offline or the company isn't on BSE."""
    if not kite.ready():
        return None
    s = (sym or "").strip().upper()
    try:
        hit = kite.by_symbol(s, "BSE")
        if not hit:
            nse = kite.equity(s)
            hit = nse and kite.equity_by_name(nse.get("name") or "")
        return hit.get("bse_code") if hit and hit.get("exchange") == "BSE" and hit.get("type") == "EQ" else None
    except Exception:
        return None


def bse_symbol(code: str) -> str:
    """A BSE-only company's trading symbol, for its page address; the code itself when unknown."""
    if kite.ready():
        try:
            hit = kite.equity(code)
            if hit and hit["exchange"] == "BSE":
                return hit["symbol"]
        except Exception:
            pass
    _load_bse_map()
    return str((_bse_map.get(code) or {}).get("ts") or code)


def _market_check(sym: str) -> dict:
    if sym.startswith("BSE:"):
        code = sym.split(":", 1)[1]
        _load_bse_map()
        ts = (_bse_map.get(code) or {}).get("ts")
        price = live_price if ts and kite.ready() else None          # BSE's own quote, by the scrip code
        row = audit.audit_company(code, deep_base, deep_view, price, None)
        for i in row["issues"]:
            i["detail"] = public_text(i["detail"])
        name = row.get("name") if row.get("name") not in (None, "", code) else None   # the check stopped before the name
        return {**row, "symbol": sym, "name": name or (_bse_map.get(code) or {}).get("name") or sym}
    return _nse_check(sym)


# daily prices and the exchange's quote come from the broker's feed: while it is offline (the day's login not done
# yet) the audit waits rather than marking every company it reaches "not checked yet"
market_audit = audit.MarketAudit(india_listing, _market_check, busy_fn=lambda: bool(audit_runner.state.get("running")),
                                 ready_fn=lambda: kite.ready())


def _sec_companies() -> list[dict]:
    """Every operating company that files with the SEC, once each: its main ticker, not its preferred shares,
    warrants, rights or units (the SEC lists those too, under the same company: ACON's warrant is ACONW, its preferred
    ACON-PA). A company whose only tickers are preferred shares and the like (AHL-PD, once its common stock left the
    exchange) is left out too: there's no common stock to check. Funds, ETFs, commodity trusts and blank-check
    companies (SPACs) are left out, as BSE's debt and ETF codes are in India: they have no business to check."""
    names = sec_feed.tickers()
    by_cik: dict[int, list[str]] = {}
    for t, v in names.items():
        if not sec.non_common(t):
            by_cik.setdefault(v["cik"], []).append(t)
    out = []
    for tickers in by_cik.values():
        if sec.not_operating(names[tickers[0]]["name"]):
            continue
        out.append(min(tickers, key=lambda t: (sec.derived_ticker(t, tickers), tickers.index(t))))
    return [{"symbol": t, "name": names[t]["name"], "listed": None} for t in out]


market_audit_us = audit.MarketAudit(lambda: _sec_companies(), lambda s: audit_one(s, False, None, "US"),
                                    busy_fn=lambda: bool(audit_runner.state.get("running")), key="audit:market-us")


def market_for(region: str):
    return market_audit_us if region == "US" else market_audit


@app.get("/admin/audit/market")
def admin_market_audit(region: str = "IN", _=Depends(admin.admin_profile)):
    """The whole-market audit: new listings in India, NSE and BSE-only (or new SEC filers), checked in the background
    while switched on."""
    return market_status(deep_region(region))


def bse_waiting(rows: list[dict]) -> int:
    """Companies listed only on BSE whose documents are waiting because BSE turned the request away."""
    return sum(1 for r in rows if str(r.get("symbol") or "").startswith("BSE:")
               and any(i.get("level") == "pending" and i.get("area") == "Documents" for i in r.get("issues") or []))


def market_status(region: str) -> dict:
    """The whole-market audit's state, and for India whether BSE is turning this server away and how many companies
    listed only there are waiting for their documents."""
    out = market_for(region).status()
    if region == "IN":
        bse = getattr(filings_feed, "bse", None)
        live = bse.state() if hasattr(bse, "state") else {}
        out["bse"] = {**live, "waiting": bse_waiting(out.get("rows") or [])}
    return out


@app.post("/admin/audit/market")
def admin_market_audit_set(req: MarketAuditReq, _=Depends(admin.admin_profile)):
    """Start or pause the whole-market audit, reset it and check every company again from nothing, re-read the
    exchange's list now, re-check the companies not checked yet or one company, or switch the monthly check."""
    m = market_for(req.region)
    if req.on is not None:
        m.set_enabled(req.on)
    if req.monthly is not None:
        m.set_monthly(req.monthly)
    if req.reset:                     # every result cleared; the list read again so it starts from today's market
        m.reset()
        threading.Thread(target=m.refresh_list, kwargs={"force": True}, daemon=True).start()
    elif req.full:
        m.start_full()
    if req.retry:                     # only the companies a source turned away last time (the exchange refusing filings)
        m.start_full(pending=True)
    if req.read_list and not req.reset:
        threading.Thread(target=m.refresh_list, kwargs={"force": True}, daemon=True).start()
    if req.recheck:
        try:
            m.recheck(req.recheck.strip())
        except KeyError:
            err(404, "not_listed", "That company isn't on the market's list.")
    return market_status(req.region)


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
    return run_platform_check(retry_after=0)


@app.get("/admin/rules")
def admin_rules(_=Depends(admin.admin_profile)):
    """Every hard-coded rate and rule with its source, when each area was last reviewed, and what the daily watch of
    the official sources last read (with any change waiting to be looked at)."""
    today = datetime.now(IST).date()
    watch = rules_watch.state()
    return {"rules": rules.registry(), "areas": rules.review_status(today), "stale_days": rules.STALE_DAYS,
            "watch": watch, "check": rules.check(today, watch=watch), "job": rules_watch_job.status}


@app.post("/admin/rules/watch/run")
def admin_rules_watch_run(_=Depends(admin.admin_profile)):
    """Read the official sources now (changes are emailed as on the daily run)."""
    rules_watch_job.run_now()
    return admin_rules()


@app.post("/admin/rules/watch/{source_id}/seen")
def admin_rules_watch_seen(source_id: str, _=Depends(admin.admin_profile)):
    """Mark a source's change as looked at; the same value won't alert again."""
    if not rules_watch.mark_seen(source_id[:40]):
        err(404, "not_found", "Nothing waiting for that source.")
    return admin_rules()


@app.get("/admin/platform/last")
def admin_platform_last(_=Depends(admin.admin_profile)):
    """The latest check, automatic or by hand, and the last two weeks' tallies."""
    try:
        last = json.loads(db.get_setting(PLATFORM_LAST) or "null")
        hist = json.loads(db.get_setting(PLATFORM_HISTORY) or "[]")
    except (ValueError, TypeError):
        last, hist = None, []
    return {"last": with_live_fund_costs(last), "history": hist}


def with_live_fund_costs(last: dict | None) -> dict | None:
    """The kept check with its "Fund costs (TER)" line read again from the job's last result, so the Admin System page
    and Data and jobs quote the same read (R9R-004: 2,178 schemes against 2,182, an hour apart). Nothing is started."""
    if not isinstance(last, dict) or not isinstance(last.get("checks"), list):
        return last
    try:
        fresh = money_mf_ter.check(start_read=False)
    except Exception as e:
        print("fund costs line not refreshed:", type(e).__name__)
        return last
    fresh["detail"] = public_text(fresh["detail"])
    checks = [{**fresh, "seconds": c.get("seconds")} if c.get("name") == fresh["name"] else c for c in last["checks"]]
    counts = {k: sum(1 for r in checks if r.get("state") == k) for k in ("pass", "warn", "fail")}
    return {**last, "checks": checks, "counts": counts}


PLATFORM_LAST, PLATFORM_HISTORY = "platform:last", "platform:history"
PLATFORM_AT = (16, 50)                   # IST, every day: after India's close, before the evening reports


def platform_checks() -> list:
    pc, today = platform_check, datetime.now(IST).date()
    checks = [(f"Prices: {m}", "Prices", (lambda m=m: pc.check_market(markets, m))) for m in markets.providers]
    checks += [(f"Backtest: {m}", "Backtests", (lambda m=m: pc.check_backtest(markets, m))) for m in markets.providers]
    checks += [("Scan: NIFTY 50", "Scans", lambda: pc.check_scan(markets, "IN", "nifty50")),
               ("Scan: US large caps", "Scans", lambda: pc.check_scan(markets, "US", "us_mega")),
               ("Sector rotation: IN", "Rotation", lambda: pc.check_rotation(markets, "IN")),
               ("Sector rotation: US", "Rotation", lambda: pc.check_rotation(markets, "US")),
               ("Option chain: NIFTY", "Options", lambda: pc.check_options(options_data, today)),
               ("Exchange filings", "Filings", lambda: pc.check_filings(filings_feed)),
               ("BSE filings", "Filings", lambda: pc.check_bse_filings(filings_feed.bse)),
               ("Insider trades", "Filings", lambda: pc.check_insider_trades(filings_feed)),
               ("Surveillance lists", "Filings", lambda: pc.check_surveillance(filings_feed)),
               ("Company page: RELIANCE", "Research", lambda: pc.check_company(research_hub, "IN", "RELIANCE")),
               ("Company page: AAPL", "Research", lambda: pc.check_company(research_hub, "US", "AAPL")),
               ("News", "Research", lambda: pc.check_news(research_hub)),
               ("Database", "Server", lambda: pc.check_database(db)),
               ("Database space", "Server", storage.check),
               ("Holiday calendar", "Server", lambda: pc.check_calendar(today)),
               ("Rates and rules last reviewed", "Rules", lambda: pc.check_rules(today, rules_watch.state())),
               ("Fund costs (TER)", "Money", lambda: pc.check_fund_costs(money_mf_ter))]
    return checks


def run_platform_check(retry_after: float = 120, auto: bool = False) -> dict:
    """Run every check; anything that failed is tried once more after `retry_after` seconds (a source that was
    briefly busy shouldn't page anyone), and only what still fails counts. The result is kept for the Admin page."""
    checks = platform_checks()
    out = platform_check.run_all(checks)
    failed = {r["name"] for r in out["checks"] if r["state"] == "fail"}
    if failed and retry_after:
        time.sleep(retry_after)
        again = {r["name"]: r for r in platform_check.run_all([c for c in checks if c[0] in failed])["checks"]}
        out["checks"] = [{**again[r["name"]], "retried": True} if r["name"] in again else r for r in out["checks"]]
        out["counts"] = {k: sum(1 for r in out["checks"] if r["state"] == k) for k in ("pass", "warn", "fail")}
    for r in out["checks"]:
        r["detail"] = public_text(r["detail"])
    out["auto"] = auto
    try:
        db.set_setting(PLATFORM_LAST, json.dumps(out))
        hist = json.loads(db.get_setting(PLATFORM_HISTORY) or "[]")[-13:]
        hist.append({"at": out["at"], "auto": auto, **out["counts"],
                     "failed": [r["name"] for r in out["checks"] if r["state"] == "fail"]})
        db.set_setting(PLATFORM_HISTORY, json.dumps(hist))
    except Exception as e:
        print("couldn't keep the platform check:", e)
    return out


def tell_admins(subject: str, text: str) -> int:
    return alerts.tell_admins(subject, text)


def platform_job():
    """Every day at PLATFORM_AT (IST): check every feature, retry failures, and tell the admins only if something
    is still broken. Nothing to do when all is well."""
    while True:
        now = datetime.now(IST)
        at = now.replace(hour=PLATFORM_AT[0], minute=PLATFORM_AT[1], second=0, microsecond=0)
        if at <= now:
            at += timedelta(days=1)
        time.sleep((at - now).total_seconds())
        try:
            daily_platform_check()
        except Exception as e:
            print("platform check job failed:", e)


def daily_platform_check(retry_after: float = 120) -> dict:
    out = run_platform_check(retry_after=retry_after, auto=True)
    bad = [r for r in out["checks"] if r["state"] == "fail"]
    if bad:
        lines = "\n".join(f"- {r['name']}: {r['detail'][:160]}" for r in bad[:10])
        tell_admins(f"StratLab: {len(bad)} check{'s' if len(bad) > 1 else ''} failing",
                    f"Today's automatic check found {len(bad)} feature{'s' if len(bad) > 1 else ''} still failing "
                    f"after a retry:\n{lines}\nDetails on the Admin page.")
    return out


def error_counts() -> dict:
    """The server errors listed, told apart as Admin → System tells them: those since this server started and those kept
    from before it (the list survives a restart), the same split as the page's own (R9P-004)."""
    start = datetime.fromisoformat(SERVER_STARTED_AT)

    def since(at) -> bool:
        try:
            return datetime.fromisoformat(str(at).replace("Z", "+00:00")) >= start
        except ValueError:
            return False
    n = sum(1 for e in RECENT_ERRORS if since(e.get("at")))
    return {"errors_since_restart": n, "errors_before_restart": len(RECENT_ERRORS) - n}


def weekly_facts(now: datetime) -> dict:
    """What the Monday summary reports, gathered from the last seven days."""
    since = now - timedelta(days=7)

    def after(at) -> bool:
        try:
            return datetime.fromisoformat(str(at).replace("Z", "+00:00")) >= since
        except ValueError:
            return False
    try:
        hist = json.loads(db.get_setting(PLATFORM_HISTORY) or "[]")
    except (ValueError, TypeError):
        hist = []
    audits = {}
    for market, m in (("India", market_audit), ("US", market_audit_us)):
        rows = m.checked_since(since.astimezone(timezone.utc).isoformat())
        issues = []
        for r in rows:
            levels = [i.get("level") for i in r.get("issues") or []]
            if "mismatch" in levels or "error" in levels:
                issues.append({"symbol": r.get("symbol"), "mismatches": levels.count("mismatch"), "errors": levels.count("error")})
        audits[market] = {"enabled": bool(m.state.get("enabled")), "checked": len(rows), "issues": issues}
    origin = (settings.FRONTEND_ORIGINS or [""])[0].rstrip("/")
    return {"stats": admin.week_stats(since), "checks": [h for h in hist if after(h.get("at"))], "audits": audits,
            "errors": sum(1 for e in RECENT_ERRORS if after(e.get("at"))), **error_counts(),
            "admin_url": f"{origin}/admin" if origin else None}


def weekly_summary(now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(IST)
    return weekly.summary(now, weekly_facts(now))


def send_weekly_summary(now: datetime) -> bool:
    """Send this week's summary if it's due and hasn't gone yet; the week is remembered so a restart never resends."""
    if not weekly.due(now) or db.get_setting(weekly.WEEK_KEY) == weekly.week_of(now):
        return False
    db.set_setting(weekly.WEEK_KEY, weekly.week_of(now))
    tell_admins(*weekly_summary(now))
    return True


def weekly_job():
    """Every Monday at 9:00 IST: the owner's summary of the week. Wakes at least hourly, so a restart catches up."""
    while True:
        try:
            send_weekly_summary(datetime.now(IST))
        except Exception as e:
            print("weekly summary failed:", e)
        now = datetime.now(IST)
        time.sleep(min(3600, max(1, (weekly.next_send(now) - now).total_seconds())))


@app.delete("/admin/audit")
def admin_audit_stop(_=Depends(admin.admin_profile)):
    """Stop a running audit after the current company; the rows so far are kept."""
    audit_runner.cancel()
    return audit_runner.status()


@app.put("/admin/view-as")
def admin_view_as(req: ViewAsReq, who=Depends(admin.admin_profile)):
    """Check a "View as" choice before the page keeps it: free, basic, pro, or off (null). Nothing is stored on the
    server: the page sends the choice with each request (the X-View-As header), and auth.current_profile honours it for
    the site owner only. Anyone else gets a 403 here, and the header does nothing for them."""
    return {"view_as": req.plan}


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


@app.post("/admin/connect/run")
def admin_connect_run(part: str = "all", _=Depends(admin.admin_profile)):
    """Run the connect-once work now: the daily IBKR read for users who are due, and/or the quiet-inbox reminders."""
    if part not in ("all", "ibkr", "reminders"):
        err(400, "bad_part", "Pick ibkr, reminders or all.")
    if not connect_job.run_now(part):
        err(409, "busy", "The connect-once job is running already.")
    return {"started": True, "part": part}


_seeding = threading.Lock()


@app.post("/admin/library/seed")
def admin_library_seed(only: str = "", _=Depends(admin.admin_profile)):
    """Run StratLab's own strategies through the backtest and verdict and publish them to the library (again: the same
    entries are updated in place). In the background; GET /admin/library/seed says how it went."""
    if not _seeding.acquire(blocking=False):
        err(409, "busy", "The StratLab strategies are being run already.")
    slugs = [s for s in only.split(",") if s in library_seed.STRATEGIES] or None

    def work():
        try:
            _seed_result.update(started=db.now_iso(), result=None, error=None)
            _seed_result["result"] = library_seed.seed(markets, only=slugs)
        except Exception as e:
            _seed_result["error"] = str(e)[:200]
        finally:
            _seed_result["finished"] = db.now_iso()
            _seeding.release()
    threading.Thread(target=work, daemon=True, name="library-seed").start()
    return {"started": True, "strategies": slugs or list(library_seed.STRATEGIES)}


_seed_result: dict = {}


@app.get("/admin/library/seed")
def admin_library_seed_status(_=Depends(admin.admin_profile)):
    return {"running": _seeding.locked(), **_seed_result, "official": len(library_seed.seeded())}


SEED_FIRST_WAIT, SEED_RECHECK, SEED_TRIES = 1500, 1800, 48     # seconds; and how many times (a day) market data is waited for


def library_seed_once(sleep=time.sleep):
    """A while after starting: StratLab's own strategies are published once, when the library has none yet and market
    data is up. Market data comes up with the day's broker login, which a night-time deploy starts before, so a start
    that finds it down checks again every half hour for a day instead of giving up until the next deploy. A library
    that has them is never touched again (a deploy costs one cheap check), and a seed is only ever run once a start.
    (After that the admin button refreshes them.)"""
    sleep(SEED_FIRST_WAIT)
    for _ in range(SEED_TRIES):
        try:
            if library_seed.seeded():
                return
            if kite.ready() and _seeding.acquire(blocking=False):
                try:
                    _seed_result.update(started=db.now_iso(), result=library_seed.seed(markets), error=None)
                finally:
                    _seed_result["finished"] = db.now_iso()
                    _seeding.release()
                return
        except Exception as e:
            print("library seed:", str(e)[:160])
            return
        sleep(SEED_RECHECK)


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


@app.post("/admin/alerts/test")
def admin_alert_test(profile=Depends(admin.admin_profile)):
    """One email to the admin's own address, straight away, so the email settings can be checked."""
    throttle(profile, "admin_mail_test", 5, 3600, "You've sent 5 test emails this hour. Try again later.")
    to = alerts.email_for(profile)
    if not alerts.email_ready():
        err(400, "email_not_set", "Email isn't set up on the server yet: add BREVO_API_KEY or RESEND_API_KEY in Railway.")
    try:
        from . import email_previews as previews
        _, html, text = previews.test_email()
        alerts.send_email(to, "StratLab test email", text, html=html)
    except Exception as e:
        why = public_text(str(e))[:200]
        if "unreachable" in why.lower() or "timed out" in why.lower():
            why += ". The host blocks outgoing mail ports: add BREVO_API_KEY or RESEND_API_KEY in Railway to send over HTTPS instead"
        err(502, "email_failed", f"The email couldn't be sent: {why}")
    return {"sent_to": to}


@app.post("/admin/review-link")
def admin_review_link(profile=Depends(admin.admin_profile)):
    """A one-time sign-in link for the owner's own account, emailed to the owner's own address, for the automated
    reviewer that tries the live site as the owner (Google sign-in can't be driven by a script). It expires in an hour
    and works once; only an admin can ask for one, and only for themselves."""
    throttle(profile, "admin_review_link", 5, 3600, "You've asked for 5 reviewer links this hour. Try again later.")
    if not alerts.email_ready():
        err(400, "email_not_set", "Email isn't set up on the server yet: add BREVO_API_KEY or RESEND_API_KEY in Railway.")
    to = profile["email"]
    try:
        res = db.sb().auth.admin.generate_link({"type": "magiclink", "email": to,
                                                "options": {"redirect_to": settings.PUBLIC_SITE_URL.rstrip("/") + "/"}})
        link = res.properties.action_link
    except Exception as e:
        err(502, "link_failed", f"The sign-in service couldn't make a link: {public_text(str(e))[:200]}")
    text = ("A one-time sign-in link for your StratLab account, for the automated reviewer. It works once and expires "
            f"in an hour. If you didn't ask for it, ignore this email.\n\n{link}\n")
    html = (f"<p>A one-time sign-in link for your StratLab account, for the automated reviewer. It works once and expires "
            f"in an hour. If you didn't ask for it, ignore this email.</p><p><a href=\"{link}\">Sign in to StratLab</a></p>")
    try:
        alerts.send_email(to, "StratLab reviewer sign-in link", text, html=html)
    except Exception as e:
        err(502, "email_failed", f"The email couldn't be sent: {public_text(str(e))[:200]}")
    return {"sent_to": to}


def lifecycle_kind(kind: str) -> str:
    if kind not in lifecycle.EMAILS:
        err(404, "not_found", "There's no such email.")
    return kind


@app.get("/admin/lifecycle")
def admin_lifecycle(_=Depends(admin.admin_profile)):
    """The lifecycle emails, for Admin → Services, and how the hourly sweep last went."""
    return {"emails": [{"kind": k, "name": n, "transactional": t} for k, (n, t) in lifecycle.EMAILS.items()],
            "job": lifecycle_job.status, "email_ready": alerts.email_ready()}


@app.post("/admin/lifecycle/{kind}/preview")
def admin_lifecycle_preview(kind: str, profile=Depends(admin.admin_profile)):
    """One lifecycle email with made-up details, as the user would see it. Nothing is sent."""
    return lifecycle.preview(lifecycle_kind(kind), profile)


@app.post("/admin/lifecycle/{kind}/test")
def admin_lifecycle_test(kind: str, profile=Depends(admin.admin_profile)):
    """One lifecycle email with made-up details to the admin's own address, now. Not recorded as sent."""
    kind = lifecycle_kind(kind)
    throttle(profile, "admin_mail_test", 5, 3600, "You've sent 5 test emails this hour. Try again later.")
    if not alerts.email_ready():
        err(400, "email_not_set", "Email isn't set up on the server yet: add BREVO_API_KEY or RESEND_API_KEY in Railway.")
    to = alerts.email_for(profile)
    if not to:
        err(400, "no_email", "Your admin account has no email address to send to.")
    try:
        subject = lifecycle.send_test(kind, profile, to)
    except Exception as e:
        err(502, "email_failed", f"The email couldn't be sent: {public_text(str(e))[:200]}")
    return {"sent_to": to, "subject": subject}


@app.post("/admin/weekly/test")
def admin_weekly_test(profile=Depends(admin.admin_profile)):
    """This week's summary, built and sent to the admins now. Monday's automatic one still goes out."""
    throttle(profile, "admin_weekly_test", 5, 3600, "You've sent 5 summaries this hour. Try again later.")
    subject, text = weekly_summary()
    return {"subject": subject, "text": text, "reached": tell_admins(subject, text)}


# ---------- newsletters: the Market Brief and My Stocks ----------
NEWS_FIELDS = ("id", "kind", "region", "day", "weekly", "subject", "summary", "ai_summary", "sections", "html", "at")


def news_view(issue: dict) -> dict:
    out = {k: issue.get(k) for k in NEWS_FIELDS if k != "ai_summary" or issue.get(k)}
    # the email as it is sent: written from the stored issue the page shows (R7T-009)
    out["html"] = (news.email_of(issue)[0] if issue.get("subject") else out["html"] or "").replace(news.write.UNSUBSCRIBE, news.write.kit.site(news.write.kit.MANAGE_NEWSLETTERS))
    return out


@app.get("/news")
def news_list(kind: str = "market", region: str = "IN", limit: int = 20, profile=Depends(current_profile)):
    """Recent issues: a region's Market Brief, or the caller's own My Stocks."""
    if kind not in news.KINDS:
        err(400, "bad_kind", "Pick the market brief or my stocks.")
    scope = ("US" if region.upper() == "US" else "IN") if kind == "market" else profile["id"]
    return {"issues": [{**{k: i.get(k) for k in ("id", "kind", "region", "day", "weekly", "subject")},
                        "preview": (i.get("summary") or "")[:200]} for i in news.recent(kind, scope, max(1, min(60, limit)))]}


@app.get("/news/{iid}")
def news_issue(iid: str, profile=Depends(current_profile)):
    """One issue in full. Market issues are for everyone; a My Stocks issue only for its reader."""
    parts = news.parse_id(iid)
    issue = news.load(iid) if parts and (parts[0] == "market" or parts[1] == profile["id"]) else None
    if not issue:
        err(404, "not_found", "That issue wasn't found.")
    return news_view(issue)


def newsletters_view(profile: dict) -> dict:
    to = news.address(profile)
    return {**newsletter_prefs.get(profile["id"]), "email": to, "confirmed": bool(to) and news.confirmed(profile),
            "allowed": {"market_daily": allows(profile["_plan"], "newsletter"), "my_stocks": True,
                        "my_stocks_daily": allows(profile["_plan"], "newsletter")}}


@app.get("/me/newsletters")
def my_newsletters(profile=Depends(current_profile)):
    return newsletters_view(profile)


@app.put("/me/newsletters")
def set_newsletters(req: NewsletterReq, profile=Depends(current_profile)):
    """Choose daily, weekly or off for each newsletter. Weekly editions are for everyone; daily ones are Basic and up."""
    if "daily" in (req.market_in, req.market_us):
        need(profile, "newsletter", "The daily Market Brief")
    if req.my_stocks == "daily":
        need(profile, "newsletter", "The daily My Stocks email")
    newsletter_prefs.set(profile["id"], **req.model_dump(exclude_none=True))
    return newsletters_view(profile)


@app.get("/me/emails")
def my_emails(profile=Depends(current_profile)):
    """Whether tips and reminders emails are on. Receipts always go."""
    return {"tips": lifecycle.tips_on(profile["id"]), "email": lifecycle.address(profile)}


@app.put("/me/emails")
def set_my_emails(req: EmailPrefsReq, profile=Depends(current_profile)):
    return {**lifecycle.set_tips(profile["id"], req.tips), "email": lifecycle.address(profile)}


@app.get("/me/first-steps")
def my_first_steps(profile=Depends(current_profile)):
    """The checklist on Home for a new account, each step ticked from the user's own data."""
    return first_steps.view(profile)


@app.put("/me/first-steps")
def set_first_steps(req: FirstStepsReq, profile=Depends(current_profile)):
    first_steps.dismiss(profile["id"], req.dismissed)
    return first_steps.view(profile)


# ---------- invite links ----------
@app.get("/me/referrals")
def my_referrals(profile=Depends(current_profile)):
    """The user's personal invite link, how many friends joined through it and the free months it earned."""
    code = referrals.code_for(profile["id"])
    try:
        mine = invite_rewards.mine(profile)
    except Exception as e:         # the link still shows without the counts
        print("invite rewards:", str(e)[:160])
        mine = {"joined": len(referrals.joined(profile["id"])), "months": 0, "free_basic_until": None, "banked_days": 0}
    return {"code": code, "link": referrals.link(code), **mine}


@app.post("/me/referral")
def record_referral(req: ReferralReq, profile=Depends(current_profile)):
    """A new account says which invite link it arrived by (the app sends it once, right after the first sign-in).
    Counted once, for a new account only, and never for the user's own link; the free-month reward waits for the
    newcomer to become active. A few tries an hour, so nobody can run through codes looking for real ones."""
    throttle(profile, "referral", 10, 3600, "Too many invite codes tried. Try again later.")
    return {"recorded": referrals.record(profile, req.code) == "recorded"}


@app.post("/admin/news/build")
def admin_news_build(kind: str = "market", region: str = "IN", weekly: bool = False, profile=Depends(admin.admin_profile)):
    """Today's issue built now, for a preview: a region's Market Brief, or the admin's own My Stocks. Not stored or
    sent, so the issue after the close is still built from the closing data."""
    if kind not in news.KINDS:
        err(400, "bad_kind", "Pick the market brief or my stocks.")
    region = "US" if region.upper() == "US" else "IN"
    day = datetime.now(ZoneInfo(news.SEND_AT[region][0])).date()
    issue = (news.build_market(region, day, weekly, store=False) if kind == "market"
             else news.build_stocks(profile["id"], day, weekly, store=False))
    if not issue:
        err(404, "empty", "Nothing to put in this issue right now: the sources are down, or nothing changed for your stocks.")
    return {**news_view(issue), "text": issue["text"]}


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
