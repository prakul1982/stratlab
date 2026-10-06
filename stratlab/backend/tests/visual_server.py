"""The app on the fake world, for the browser tests in stratlab/frontend/e2e: every source faked, plus a company with
loss years (TCS stands in for one, as only listed symbols open) so the charts' handling of losses can be checked.

    python -m tests.visual_server            # serves on 127.0.0.1:8765
"""
import base64
import copy
import os
import sys
from pathlib import Path

import pytest
import uvicorn

sys.path.insert(0, ".")
_web = os.environ.get("E2E_WEB_PORT", "5599")
os.environ.setdefault("FRONTEND_ORIGIN", f"http://127.0.0.1:{_web},http://localhost:{_web}")   # the browser tests' page
from app import main  # noqa: E402
from tests import world  # noqa: E402

PORT = int(os.environ.get("E2E_API_PORT", "8765"))     # another port lets two test runs share a machine
LOSS = "TCS"


def loss_company(p: dict) -> dict:
    """RELIANCE's page with SML-like numbers: losses for three years, then profits."""
    p = copy.deepcopy(p)
    pl = p["pl"]
    n = len(pl["cols"])
    shape = [-21.3, -133.4, -100.2, 20.05, 108.6, 122.4, 160.3]
    pl["rows"]["Net Profit"] = ([None] * max(0, n - len(shape)) + shape)[-n:]
    p["name"] = "Loss Company Ltd"
    return p


def build():
    mp = pytest.MonkeyPatch()
    w = world.build(mp)
    from app import guard
    for limit in ("PER_MINUTE_USER", "PER_MINUTE_ANON", "PER_MINUTE_ADDRESS"):   # the sweep opens hundreds of pages a minute as one user
        mp.setattr(guard, limit, 100_000)
    scr = main.research_hub.screener
    real = scr.company
    mp.setattr(scr, "company", lambda sym: loss_company(real("RELIANCE")) if sym.upper() == LOSS else real(sym))
    from datetime import datetime, timezone
    from app import db
    # brand-new accounts, for the first-steps checklist on Home (u-load-201 and 204: the new-user walkthrough's own)
    for uid in ("u-free", "u-basic", "u-load-201", "u-load-204"):
        db.update_profile(uid, created_at=datetime.now(timezone.utc).isoformat())
    # the owner's holdings, imported from a Zerodha Console file, for the My Holdings page
    sample = Path(__file__).parent / "fixtures" / "holdings" / "zerodha_console_holdings.xlsx"
    w["client"].post("/holdings/import", headers=world.headers("admin-token"),
                     json={"filename": sample.name, "data": base64.b64encode(sample.read_bytes()).decode()})
    # ...and their trades from two brokers, for the tax report
    for name in ("zerodha_console_tradebook.csv", "zerodha_tax_pnl.xlsx"):
        trades = Path(__file__).parent / "fixtures" / "tradebooks" / name
        w["client"].post("/tax/import", headers=world.headers("admin-token"),
                         json={"filename": name, "data": base64.b64encode(trades.read_bytes()).decode()})
    invite_rewards()
    main.corp_job.refresh("IN")             # the corporate-actions calendar, as the morning job would have built it
    from app import surveillance
    surveillance.refresh(main.filings_feed)  # the exchange's surveillance lists, as the morning run would have read them
    from app import fo_changes
    fo_changes.refresh(main.filings_feed)    # the F&O contract file and circulars, likewise
    from tests import fake_market_events
    fake_market_events.seed()                # the market events calendar's sources, as the morning read would have kept them
    screen_index()
    breadth(mp)
    positioning_history()
    stock_desks_history(mp)
    # the public NAV files, from the test fixtures, for the mutual funds page
    from app import money_mf_nav
    navs = Path(__file__).parent / "fixtures" / "mf"
    mp.setattr(money_mf_nav, "fetch_text", lambda url: (navs / ("NAVAll.txt" if url == money_mf_nav.DAILY_URL else "nav_2018-01-31.txt")).read_text())
    mp.setattr(money_mf_nav, "MIN_SCHEMES", 1)
    # the public TER disclosure (made-up schemes), the same table for every month, for the fund costs
    from app import money_mf_ter
    mp.setattr(money_mf_ter, "fetch_month", lambda m, y: (navs / "ter_disclosure.html").read_text())
    for k, v in (("MIN_ROWS", 1), ("PAUSE", 0), ("BACKGROUND", False), ("BACKFILL", 3)):
        mp.setattr(money_mf_ter, k, v)
    # a made-up NAV history for the flexi cap fund, for the fund behaviour card's redemption after a fall
    from app import money_mf_behaviour
    from tests import fake_mf_history
    mp.setattr(money_mf_behaviour, "fetch_json", fake_mf_history.fetch)
    mp.setattr(money_mf_behaviour, "BACKGROUND", False)
    mp.setattr(money_mf_behaviour, "PAUSE", 0)
    # the Reserve Bank's Current Rates panel, from a trimmed real copy, for Money → Rates
    from app import rbi_rates
    rbi_page = (Path(__file__).parent / "fixtures" / "rates" / "rbi_home_rates.html").read_text()
    mp.setattr(rbi_rates, "fetch_text", lambda url=rbi_rates.URL: rbi_page)
    etf_gaps(mp)
    closing_auction(mp)
    vix_history(mp)
    holders_and_updates(mp)
    live_breadth(mp)
    library_seeds()
    all_company_filings(mp)
    # made-up rupees-a-dollar histories (SBI TT buying and RBI reference), for US stocks tax and the ITR export
    from tests import fx_rates
    fx_rates.seed()
    # keep that index: the background job would rebuild it from stored pages a few minutes in, mid-run
    mp.setattr(main.screen_indexer, "loop", lambda: None)
    return w


def all_company_filings(mp):
    """The evening reads as they would have left things: the red-flag filings of every company (a made-up exchange list for
    India, made-up 8-K items and 13D/13G filings for the S&P 500, read from the fake SEC) and the whole US universe's
    dividends and splits (from the fake price history). The jobs stay off, so the stored rows stay as they are."""
    from app import corp_actions
    main.redflags_runner.pause = 0
    main.redflags_runner.sleep = lambda s: None
    for region in ("IN", "US"):
        main.redflags_runner.run(region)
    mp.setattr(corp_actions, "UNIVERSE_PACE", 0)
    main.corp_job.start_universe({}, wait=True)
    mp.setattr(main.redflags_job, "start", lambda: None)
    mp.setattr(main.corp_job, "start", lambda: None)


def holders_and_updates(mp):
    """Named holders from the real (trimmed) shareholding samples, with Safari's list also shown on RELIANCE's page;
    business updates: a made-up year for RELIANCE, and Maruti's and TVS Motor's real September filings read as the job
    would have (the model's replies in fake_biz)."""
    from app import biz_updates as B
    from app.docs import Docs
    from tests import fake_biz, fake_shp
    fake_shp.seed(also={"RELIANCE": "SAFARI"})
    fake_biz.seed(("RELIANCE",))
    mp.setattr(B, "complete", fake_biz.ai)
    docs = Docs(transport=fake_biz.docs_transport(), check_host=lambda h: True, ocr=lambda d: "")
    for sym in ("MARUTI", "TVSMOTOR"):
        item = next(u for u in B.updates(fake_biz.announcements(sym)) if u["url"].endswith(fake_biz.FILES[sym]))
        B.save(sym, item["id"], B.read_one(sym, item, docs, None, []))
    mp.setattr(main.biz_job, "start", lambda: None)
    mp.setattr(main.holders_job, "start", lambda: None)
    # more sectors: a made-up year for two cement makers; the browser tests' Basic users' holdings and watchlist for My stocks
    fake_biz.seed(("ULTRACEMCO", "AMBUJACEM"))
    import json
    from app import db, holdings
    for uid in ("u-load-289", "u-load-292"):
        holdings.save(uid, [{"symbol": "MARUTI", "qty": 10, "avg": 11000.0}, {"symbol": "TCS", "qty": 5, "avg": 3500.0}], "manual")
        db.set_setting(f"watchlist:{uid}", json.dumps({"items": [{"symbol": "TVSMOTOR", "region": "IN"}, {"symbol": "ULTRACEMCO", "region": "IN"},
                                                                  {"symbol": "MARUTI", "region": "IN"}, {"symbol": "AAPL", "region": "US"}]}))


def live_breadth(mp):
    """The market is open for the whole run, with today's points stored for two groups (a third has none, so the page shows
    what it says when live prices aren't there). The job stays off, so the stored points stay as they are."""
    import json
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from app import breadth_live as BL, db
    mp.setattr(BL, "is_open", lambda region, now: region == "IN")
    mp.setattr(BL, "STALE_AFTER", 10**9)
    mp.setattr(main.breadth_live_job, "start", lambda: None)
    day = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    times = ["09:30", "09:45", "10:00", "10:15", "10:30", "10:45"]
    for g, scale in (("nifty500", 5), ("nifty50", 1)):
        pts = []
        for i, t in enumerate(times):
            adv, dec = (230 + 14 * i) * scale, (170 - 9 * i) * scale
            pts.append([t, adv, dec, 12 * scale, 210 * scale + 6 * i, 400 * scale, 190 * scale + 5 * i, 400 * scale, 160 * scale + 2 * i, 380 * scale,
                        24000.5 + 22 * i if g == "nifty500" else 25100.0 + 15 * i])
        db.set_setting(BL.LIVE_KEY + g, json.dumps({"day": day, "fields": list(BL.FIELDS), "points": pts}))


def library_seeds():
    """StratLab's own strategies in the library, run on small stand-ins for the standard groups (the fake market's prices)."""
    from app import library_seed, universes
    keep, days = universes.PRESETS, dict(library_seed.DAYS)
    try:
        universes.PRESETS = {m: [{**p, "symbols": p["symbols"][:5]} for p in ps] for m, ps in keep.items()}
        library_seed.DAYS.update({"1d": 600, "15m": 30})
        library_seed.seed(main.markets, gap=0)
    finally:
        universes.PRESETS = keep
        library_seed.DAYS.update(days)


def invite_rewards():
    """The owner invited friends: one became active (a free month each), and a link with too many sign-ups in a day
    left two rewards waiting for review in Admin (one for the desktop run to reject, one for the phone run to
    approve). This year so far: two friends' use earned the owner a month each (3 and 4), a third became active after
    that and waits to subscribe (5), and a fourth subscribed (6): "Use: 2 of 2 · Subscribed: 1 of 2 · Extra: 0 weeks".
    Dated from today, so the rolling year always holds them."""
    import json
    from datetime import datetime, timedelta, timezone
    from app import db, plans
    now = datetime.now(timezone.utc)
    at, on = (now - timedelta(days=3)).isoformat(timespec="seconds"), (now - timedelta(days=1)).isoformat(timespec="seconds")
    joined = [{"id": f"u-load-{i}", "at": at} for i in range(1, 7)]
    db.set_setting("ref:joined:u-admin", json.dumps(joined))
    given = {"by": "u-admin", "at": at, "status": "given", "signups_that_day": 3,
             "referrer_months": 1, "newcomer_months": 1, "given_at": on, "kind": "use", "referrer_at": on}
    db.set_setting("reward:u-load-3", json.dumps(given))
    db.set_setting("reward:u-load-4", json.dumps(given))
    db.set_setting("reward:u-load-5", json.dumps({**given, "referrer_months": 0, "kind": None, "referrer_at": None,
                                                  "referrer_pending": True}))
    db.set_setting("reward:u-load-6", json.dumps({**given, "status": "waiting", "newcomer_months": 0, "given_at": None,
                                                  "kind": "payment", "paid_at": on, "payment_id": "pay_fixture6"}))
    for i in (1, 2):
        db.set_setting(f"reward:u-load-{i}", json.dumps({**given, "status": "review", "signups_that_day": 6, "kind": None,
                                                        "referrer_months": 0, "newcomer_months": 0, "given_at": None,
                                                        "referrer_at": None}))
    plans.add_free_basic(db.get_profile("u-load-3"), 30)


def breadth(mp):
    """Market breadth for both markets, as the evening runs would have stored it: the NSE indices' lists are the fake
    market's sector stocks, read without the sources' pacing (that only slows the start)."""
    from app import sector_members
    from app.intel.net import RateLimit
    stocks = sorted({s for syms in sector_members.IN.values() for s in syms})
    mp.setattr(main.filings_feed, "index_members", lambda name: stocks[:50] if name == "NIFTY 50" else stocks)
    with pytest.MonkeyPatch.context() as quick:
        quick.setattr(main.kite, "_throttle", lambda: None)
        quick.setattr(main.markets.provider("US").yahoo, "limit", RateLimit(10**7, 10**6))
        quick.setattr(main.breadth_runner, "gap", 0)
        for region in ("IN", "US"):
            main.breadth_runner.run(region)
    mp.setattr(main.breadth_job, "start", lambda: None)      # the stored counts stay as they are for the whole run
def closing_auction(mp):
    """Today's closing auction, as read just after it ended, and 8 stored days for the history."""
    from datetime import date
    from app import closing_auction as CA
    from tests import fake_cas
    CA.refresh(main.filings_feed)
    fake_cas.seed(date.today())
    mp.setattr(main.closing_auction_job, "start", lambda: None)


def etf_gaps(mp):
    """ETF prices against their NAV: the exchange's ETF list as the job would have read it (from the fake exchange),
    the made-up ETFs' NAVs added to the NAV file, and 30 trading days of stored closes."""
    from datetime import date
    from app import etf_nav
    from tests import fake_etf
    data = fake_etf.navs(date(2026, 10, 3))
    mp.setattr(etf_nav, "navs", lambda: data)
    etf_nav.refresh(main.filings_feed)
    fake_etf.seed_history(date.today())
    mp.setattr(main.etf_job, "start", lambda: None)          # the stored list stays as it is for the whole run


def vix_history(mp):
    """India VIX's last year of daily closes, as the job would have stored them (made up, from the fake exchange)."""
    from datetime import date, timedelta
    from app import vix
    vix.fetch(date.today() - timedelta(days=400), date.today(), main.filings_feed, sleep=lambda s: None, pace=0)
    mp.setattr(main.vix_job, "start", lambda: None)


def positioning_history():
    """Derivatives positioning as the evening job would have left it: the exchange's files for about three months (read
    from the fake exchange), and thirty days of recorded NIFTY and BANKNIFTY chains summarised by day."""
    from datetime import date
    from app import db, positioning
    from tests import fake_positioning as fp
    today = date.today()
    days = fp.weekdays_before(today, 30)
    fp.record_days(db.add_option_snapshot, "NIFTY", days)
    fp.record_days(db.add_option_snapshot, "BANKNIFTY", days, spot=55000.0, gap=100)
    day = positioning.expected_day(positioning.ist_now())
    if day:
        main.positioning_runner.run_day(day)
    main.positioning_runner.backfill(today, step=120, days=100)


def stock_desks_history(mp):
    """The stock desks (futures, lending, margin funding) as the evening job and its archive walk would have left them:
    about two months of the fake exchange's files. The job itself stays off, so the stored days stay as they are."""
    from app import exchange_days, stock_desks
    for d in stock_desks.DESKS:
        stock_desks.runner.catch_up(d)
        stock_desks.runner.backfill(d, exchange_days.ist_now().date(), step=30)
    mp.setattr(stock_desks.job, "start", lambda: None)


def screen_index():
    """The stock screens' index, as the background job would gather it from stored company pages (written straight to
    the index, so the public company pages still build from the fake sources)."""
    import json
    import random
    from datetime import date, timedelta
    from app import db, screens
    rng = random.Random(5)
    sectors = ["Energy", "Information Technology", "Financials", "Consumer Staples", "Materials"]
    names = {"IN": ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "ONGC", "ITC", "HINDUNILVR", "TATASTEEL", "JSWSTEEL",
                    "WIPRO", "HCLTECH", "NTPC", "COALINDIA", "SBIN", "AXISBANK", "NESTLEIND", "DABUR", "VEDL", "SAIL"],
             "US": ["AAPL", "MSFT", "XOM", "JPM", "KO", "NUE"]}
    for region, syms in names.items():
        rows = []
        for i, sym in enumerate(syms):
            price = round(rng.uniform(50, 3000), 2)
            f = {"region": region, "symbol": sym, "name": f"{sym.title()} {'Ltd' if region == 'IN' else 'Inc.'}",
                 "industry": [sectors[i % len(sectors)]], "price": price, "high52": round(price * rng.uniform(1, 1.6), 2),
                 "low52": round(price * 0.7, 2), "price_at": "2026-10-01", "market_cap": round(rng.uniform(200, 900000)),
                 "pe": None if i % 7 == 3 else round(rng.uniform(6, 60), 1), "roe": round(rng.uniform(-5, 35), 1),
                 "roce": round(rng.uniform(0, 40), 1), "div_yield": round(rng.uniform(0, 4), 2), "net_margin": round(rng.uniform(-5, 30), 1),
                 "opm": round(rng.uniform(5, 40), 1), "debt_equity": round(rng.uniform(0, 2), 2), "bank": False,
                 "growth": {"sales_cagr_3y": round(rng.uniform(-10, 30), 1)}, "stage": 1 + i % 4,
                 "red_flags": (i % 5 == 0) * 2 if region == "IN" else None, "filings": [], "built_at": "2026-10-01T12:00:00+00:00"}
            r = screens.row(region, sym, f)
            if region == "IN":          # a promoter or insider bought on the open market: 10 days ago for every fourth
                r["insider_buy_at"] = (date.today() - timedelta(days=10 if i % 4 == 1 else 200)).isoformat() if i % 2 else None
            rows.append(r)
        rows.sort(key=lambda r: r["name"].lower())
        db.set_setting(screens.INDEX_KEY + region, json.dumps({"region": region, "at": "2026-10-01T18:00:00+00:00", "rows": rows}))


if __name__ == "__main__":
    build()
    uvicorn.run(main.app, host="127.0.0.1", port=PORT, log_level="warning")
