"""Plan rules. Change limits and prices here only."""
from datetime import datetime, timedelta, timezone

PLANS = {
    "free": {
        "name": "Free", "price": 0, "price_year": 0,
        # FREE-TIER (owner, Nov: Free is a teaser; the public pages are what attracts people): the counts below are Free's from
        # FREE_TIER_CHANGE_AT; accounts made before it keep FREE_BEFORE's for FREE_GRACE_DAYS (free_grace_until)
        "backtests_per_month": 5,
        "ai_builds_per_month": 5,
        "live_limit": 1,              # only during the trial
        "live_trial_days": 5,         # Indian trading days (no weekends or holidays), counted from the first start
        "group_size": 5,              # instruments in one group test
        "holdings": 30,               # stocks in My Holdings
        "stock_alerts": 3,            # active price and indicator alerts on stocks
        "screens": 1,                 # saved stock screens (running a screen has no limit on any plan)
        "deepdives_per_month": 1,     # companies opened in the deep dive (each counted once a month)
        "decks_per_month": 0,         # slide decks of a company or a theme (PowerPoint or PDF); Free gets the sample deck (sample_deck)
        "themes_per_month": 1,        # NEW themes mapped a month (a theme already in the library opens on every plan)
        "ai_reads_per_day": 5,        # fresh AI reads a day, refreshes included (ai_reads_per_day)
        "search_ai_per_day": 10,      # the search box's AI answers a day
        "share_links_per_month": 1,   # public share links (/r/<token>) to a deep dive or a theme made this month (share.py)
        "networth_items": 5,          # typed-in entries in Net worth (assets, loans and policies)
        "mf_schemes": 5,              # mutual fund schemes kept (Money: mutual funds)
        "journal_trades": 50,         # closed trades the trade journal keeps and counts (Trade: journal)
        "watchlists": 1,              # Market Watch lists (the Research watchlist is the first): None is no limit
        "watchlist_symbols": 20,      # symbols in one Market Watch list
        "chart_saves": 3,             # charts whose drawings and indicators are kept on the account
        "chart_indicators": 3,        # indicators on one chart
        "features": set(),
    },
    "basic": {
        # rupee prices include GST (invoices.py backs the 18% out)
        "name": "Basic", "price": 699, "price_year": 6999,
        "backtests_per_month": 100,
        "ai_builds_per_month": 100,
        "live_limit": 2,
        "live_trial_days": None,
        "group_size": 25,
        "holdings": 100,
        "stock_alerts": 25,
        "screens": 10,
        "deepdives_per_month": 15,
        "decks_per_month": 5,
        "share_links_per_month": 30,
        "themes_per_month": 10,
        "ai_reads_per_day": 60,       # settings.RESEARCH_AI_PER_DAY, when set, is Basic's (ai_reads_per_day)
        "search_ai_per_day": 40,
        "networth_items": None,
        "mf_schemes": None,       # unlimited
        "journal_trades": None,
        "watchlists": 10,
        "watchlist_symbols": 100,
        "chart_saves": None,
        "chart_indicators": 10,
        "features": {"indicators", "group_live", "options", "alerts", "daily_report", "newsletter", "scans", "filings",
                     "investor_home", "networth", "mf_gains", "dividends", "money_reminders", "breadth", "positioning", "journal",
                     "mf_costs", "etf_gaps", "fo_alerts", "cas_history", "vix_filter",
                     "chart_replay",
                     "event_reminders",
                     "biz_updates", "holders",
                     "stock_futures", "mtf",
                     "mf_behaviour", "sip_luck", "rates_slab", "loan_check",
                     "ipo_summary", "ipo_alerts", "movers",
                     "earnings_calls", "group_figures",
                     "doc_search",
                     "tables",
                     "tax_export",
                     "watchlist_import"},
    },
    "pro": {
        "name": "Pro", "price": 1999, "price_year": 19999,
        "backtests_per_month": None,  # unlimited
        "ai_builds_per_month": None,  # unlimited (a daily safety cap of 200 builds still applies, said on Plans)
        "live_limit": 10,
        "live_trial_days": None,
        "group_size": 50,
        "holdings": 300,
        "stock_alerts": 100,
        "screens": 25,
        "deepdives_per_month": None,  # unlimited (and no daily cap on fresh AI reads: ai_reads_per_day)
        "decks_per_month": None,
        "share_links_per_month": None,  # unlimited
        "themes_per_month": None,
        "ai_reads_per_day": None,
        "search_ai_per_day": 40,
        "networth_items": None,
        "mf_schemes": None,
        "journal_trades": None,
        "watchlists": None,
        "watchlist_symbols": None,
        "chart_saves": None,
        "chart_indicators": None,
        "features": {"indicators", "fno", "group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report",
                     "export", "newsletter", "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "tax_tools", "money_reminders",
                     "breadth", "positioning", "journal", "itr_export", "us_tax", "mf_costs", "etf_gaps", "fo_alerts", "options_whatif", "cas_history",
                     "vix_filter", "strike_rules",
                     "chart_replay", "signal_webhooks",
                     "event_reminders",
                     "biz_updates", "holders",
                     "assistant",
                     "stock_futures", "mtf",
                     "mf_behaviour", "sip_luck", "rates_slab", "loan_check",
                     "ipo_summary", "ipo_alerts", "movers",
                     "earnings_calls", "group_figures",
                     "doc_search", "doc_search_all",
                     "tables",
                     "tax_export",
                     "watchlist_import"},
    },
}
# indicators: every indicator beyond price, SMA, EMA and RSI; fno: Indian futures and options;
# newsletter: the daily editions of both newsletters (the weekly ones are for everyone);
# scans: the Stage 2 + Supertrend scan and its alert; filings: red flags for the whole watchlist and the evening alert
# (red flags on a single company page are for everyone); networth: unlimited Net worth entries and its history chart; mf_gains: mutual fund capital gains per financial year;
# dividends: each company's dividends, TDS and US withholding (the year totals are for everyone); tax_tools: advance tax
# amounts and the lot-by-lot long-term exemption facts (the due dates and the exemption used are for everyone); money_reminders: the money calendar's
# reminders (the calendar and its feed are for everyone); breadth: market breadth history, charts and sector table (today's
# numbers are for everyone); positioning: derivatives positioning history and the IV percentile and rank (today's
# participant numbers, cash flows and option-chain facts are for everyone); journal: the trade journal's honesty checks, breakdowns,
# R-multiples and paper-vs-real comparison, and every trade kept (the trade list and basic stats are for everyone); itr_export: the ITR-ready schedules and the pack for your CA
# (the preview of what they hold is for everyone); us_tax: US shares' gains in rupees sale by sale, the foreign tax
# credit and Schedule FA (each year's totals and every lot's long or short term are for everyone); mf_costs: each fund's TER
# parts, rupees a year per fund, the other plan beside it, TER changes since purchase and category changes (each fund's
# TER and the year's total in rupees are for everyone); etf_gaps: alerts on
# an ETF's price against its NAV (the gaps, their 30-day history and the badges are for everyone); fo_alerts: an alert
# when an F&O contract change (an exit, a lot size, an expiry day) touches your watchlist or paper sessions (the dated
# list and its badges are for everyone); options_whatif: the options what-if sliders (spot, IV and days forward, moving
# the payoff, Greeks and P&L) and the roll preview (the model's Greeks for each strike in the chain and each leg, the net
# Greeks and the payoff today beside the one at expiry are for everyone); cas_history: the closing auction desk's 60-day
# history (today's auction, live, is for everyone); vix_filter: the India VIX entry filter on options sessions (the India VIX
# panel, its history and percentile are for everyone; India VIX in notebook rules comes with the other indicators);
# strike_rules: options legs whose strike is picked by model delta, a delta range, premium or a share of the ATM straddle
# (the builder's preview of what a rule picks is for everyone); chart_replay: chart replay practice, logged to the trade journal; signal_webhooks: a secret webhook URL that moves paper sessions from outside alerts (TradingView, Chartink), with the signal log and the verdict's checks on the forward test; event_reminders: reminders of market events (RBI, data releases, the Fed, index changes, expiries) by phone, Telegram or email (the events calendar, its index badges and adding the events to your Money calendar are for everyone); biz_updates: monthly and quarterly business updates read into numbers on company pages, the sector view and the "new business update" alert (the list of update filings is for everyone); holders: searching named holders above 1% across companies and following one (each company's named holders are for everyone); assistant: StratLab in your AI assistant (the MCP server, mcp_server.py): read-only tools and paper orders in your own paper sessions, with keys made on Account; stock_futures: each F&O stock's stored history (OI, buildup, rollover, basis, MWPL use) and the alert on MWPL use crossing 80% (today's table is for everyone); mtf: a stock's and the market's margin-funding history and the alert on a funded level (today's numbers and the MTF cost calculator are for everyone); mf_behaviour: fund behaviour, i.e. the gap to each fund's own return in rupees, the SIP record, redemptions after a fall and holding periods (your XIRR beside the fund's NAV return is for everyone); sip_luck: the SIP test's dip rules and the spread of results over every start month (a plain SIP test with charges and the lump sum is for everyone); rates_slab: fixed-income rates after tax at the marginal rate from your own tax estimate (after tax at a slab you pick is for everyone); loan_check: each floating-rate loan against its benchmark, the gap to your statement's rate and what each change did (the benchmark, spread and reset fields and the reset dates in the calendar are for everyone); ipo_summary: the summary of an IPO's offer document (what the company does, its figures, what the money is for, the main risk factors and the promoters, each statement checked against a quote from the document); ipo_alerts: an alert when an IPO opens, closes, is allotted or lists (the IPO lists, each issue's page and facts, its bids by category and its trading since listing are for everyone); movers: the market movers in full, i.e. every row of each list (gainers, losers, most traded,
# volume spikes, 52-week highs and lows), the index and smallest-market-value filters and the CSV (the top 5 of each list for the
# default index, and the public page's same top 5, are for everyone); earnings_calls: the earnings-call calendar in full, i.e. every week ahead, the calls already held, the transcript, recording and presentation links filed after a call, the filters (your stocks, type, a company) and the calls of your stocks in the money calendar's feed (this week's calls, each with its notice and webcast or dial-in link, are for everyone); group_figures: business group figures, i.e. each member's 1-month and 1-year change, its promoter holding, the members' heatmap and the group's own longer changes (the groups, their members, market values and the day's change are for everyone); watchlist_import: importing a watchlist from a CSV or Excel file, picking its column (pasting symbols is for everyone, up to the plan's watchlist limits)
FEATURES = ("indicators", "fno", "group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report", "export",
            "newsletter", "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "tax_tools", "money_reminders",
            "breadth", "positioning", "journal", "itr_export", "us_tax", "mf_costs", "etf_gaps", "fo_alerts", "options_whatif",
            "cas_history", "vix_filter", "strike_rules",
            "chart_replay", "signal_webhooks",
            "event_reminders",
            "biz_updates", "holders",
            "assistant",
            "stock_futures", "mtf",
            "mf_behaviour", "sip_luck", "rates_slab", "loan_check",
            "ipo_summary", "ipo_alerts", "movers",
            "earnings_calls", "group_figures",
            "doc_search", "doc_search_all",
            "tables",
            "tax_export",
            "watchlist_import")
# doc_search: search inside filings and call transcripts with every hit and every filter (sector, a stored theme's companies, kind
# of document, dates), over the last year (Free: the first DOC_SEARCH["free"]["hits"] hits of a search, filtered by company only;
# visitors: nothing, it needs sign-in); doc_search_all: every year stored (a company's documents across all its years, from its
# company page) and the hits as a CSV (doc_search.py)
DOC_SEARCH = {"free": {"hits": 3, "days": 365}, "basic": {"hits": None, "days": 365}, "pro": {"hits": None, "days": None}}
# tables: on a company page and its deep dive, every peer (up to ten) and sorting them, every year of the statements (up to
# twelve) with the balance sheet, cash flow, ratios, the last twelve quarters and both standalone and consolidated, and twelve quarters of
# shareholding with its chart (the three nearest peers, the latest three years of profit and loss and the latest quarter's shareholding
# are for everyone); a company's statements as Excel or CSV and its peers as CSV are Pro's export (company_tables.py)
# tax_export: the tax report's CSV and PDF downloads (the report on screen is for everyone)
# the smallest plan with each feature, for upgrade messages
FEATURE_PLAN = {f: next(p for p in ("free", "basic", "pro") if f in PLANS[p]["features"] or p == "pro") for f in FEATURES}

BASIC_REFS = {"price", "sma", "ema", "rsi", "num"}      # every other indicator (MACD, Bollinger, VWAP…) is Basic and up

GRACE = timedelta(days=1)


def payments_live() -> bool:
    """People can actually buy a plan: the Razorpay keys and both monthly plan IDs are set. It only changes the
    words (an upgrade message says how to get early access instead of "upgrade"), never what a plan includes."""
    from . import billing
    return billing.enabled()


def allows(plan: str, feature: str) -> bool:
    """Each plan gets exactly what the Pricing page lists, whether or not payments are set up (the owner's decision,
    7 Oct). `plan` is the access plan (access_plan): Pro for everyone during the launch offer and for the site owner, a
    plan the owner granted by hand, free Basic time from invites."""
    return feature in PLANS[plan]["features"]


EARLY_ACCESS_EMAIL = "support@stratlab.studio"


def upgrade_note(message: str) -> str:
    """An upgrade message as it should read today. While no plan can be bought, it says so and how to get early access,
    instead of sending people to a checkout that doesn't exist."""
    if payments_live():
        return message
    from .config import settings
    email = (getattr(settings, "REPLY_TO_EMAIL", "") or EARLY_ACCESS_EMAIL).strip()
    return f"{message.rstrip()} Paid plans open soon; ask us at {email} for early access."


def has_indicators(plan: str) -> bool:
    """Every indicator beyond price, SMA, EMA and RSI (Basic and up)."""
    return allows(plan, "indicators")


def has_fno(plan: str) -> bool:
    """Indian futures and options (Pro)."""
    return allows(plan, "fno")


def bigger_plan(plan: str, key: str) -> str | None:
    """The name of the next plan up with a higher count limit `key` (None counts as unlimited), for upgrade messages;
    None when no plan goes higher."""
    have, order = PLANS[plan][key], ("free", "basic", "pro")
    for p in order[order.index(plan) + 1:]:
        cap = PLANS[p][key]
        if have is not None and (cap is None or cap > have):
            return PLANS[p]["name"]
    return None


# ---------- FREE-TIER: the smaller Free plan, and the accounts that keep the old one for a while ----------
# Free's counts before FREE_TIER_CHANGE_AT (config): an account made before then keeps these for FREE_GRACE_DAYS after it, and sees a
# one-time notice on Account and My space saying what changes and when (free_change_notice). New accounts get PLANS["free"] at once.
FREE_BEFORE = {"backtests_per_month": 10, "ai_builds_per_month": 10, "group_size": 10, "stock_alerts": 5, "screens": 2,
               "deepdives_per_month": 2, "decks_per_month": 1, "themes_per_month": None, "ai_reads_per_day": 60,
               "search_ai_per_day": 40}
FREE_BEFORE_FEATURES = {"tax_export"}           # what Free had before that it loses with the change
FREE_GRACE_DAYS = 14
# what the notice lists, in order: (the key, its words)
FREE_CHANGE_WORDS = (("ai_reads_per_day", "Fresh AI reads a day"),
                     ("search_ai_per_day", "AI answers in the search box a day"), ("themes_per_month", "New themes mapped a month"),
                     ("backtests_per_month", "Backtests a month"), ("ai_builds_per_month", "AI strategy builds a month"),
                     ("deepdives_per_month", "Company deep dives a month"), ("decks_per_month", "Slide decks a month"),
                     ("stock_alerts", "Stock alerts on at a time"), ("screens", "Saved screens"), ("group_size", "Instruments in a group test"))


def free_change_at() -> datetime:
    """When the smaller Free plan started (config.FREE_TIER_CHANGE_AT, set at the deploy that brought it)."""
    from .config import settings
    t = _dt(settings.FREE_TIER_CHANGE_AT)
    return t if t.tzinfo else t.replace(tzinfo=IST)


def free_grace_until(profile: dict | None, now: datetime | None = None) -> datetime | None:
    """When an account made before the change stops having Free's old counts, or None (made after it, the grace is over, or a
    "View as" plan, which shows the plan as it is). Only the counts of the Free plan: a paid plan is never touched."""
    if not profile or view_as_of(profile.get("_view_as")):
        return None
    made = profile.get("created_at")
    if not made:
        return None
    try:
        made = _dt(made)
    except (TypeError, ValueError):
        return None
    made = made if made.tzinfo else made.replace(tzinfo=timezone.utc)
    at = free_change_at()
    end = at + timedelta(days=FREE_GRACE_DAYS)
    return end if made < at and (now or datetime.now(timezone.utc)) < end else None


def _limit(who, key: str):
    """A plan's count `key`: `who` is a plan ("free") or a profile, whose plan (plan_of) is read and, on Free, an account in its grace
    keeps FREE_BEFORE's count."""
    if isinstance(who, dict):
        plan = plan_of(who)
        if plan == "free" and key in FREE_BEFORE and free_grace_until(who):
            return FREE_BEFORE[key]
        return PLANS[plan][key]
    return PLANS[who][key]


def limit_of(who, key: str):
    """The count `key` for a plan or a profile (see _limit): the one place a request reads a changed Free count."""
    return _limit(who, key)


def allows_for(profile: dict, feature: str) -> bool:
    """allows() for a person: on Free in the grace, what Free had before the change (FREE_BEFORE_FEATURES) still works."""
    plan = plan_of(profile)
    return allows(plan, feature) or (plan == "free" and feature in FREE_BEFORE_FEATURES and free_grace_until(profile) is not None)


def group_size(plan) -> int:
    return _limit(plan, "group_size")


def holdings_limit(plan: str) -> int:
    """How many stocks My Holdings keeps. Importing is for everyone; paid plans keep more."""
    return PLANS[plan]["holdings"]


def stock_alerts(plan) -> int:
    """How many stock alerts can be on at once (a plan, or a profile: _limit)."""
    return _limit(plan, "stock_alerts")


def screens(plan) -> int:
    """How many stock screens can be saved (a plan, or a profile: _limit). Running a screen has no limit."""
    return _limit(plan, "screens")


def deepdives(plan) -> int | None:
    """How many companies a month the deep dive opens (None: unlimited). Each company counts once a month."""
    return _limit(plan, "deepdives_per_month")


def decks(plan) -> int | None:
    """How many slide decks (a company's or a theme's) a month (None: unlimited; 0 on Free, which has the sample deck)."""
    return _limit(plan, "decks_per_month")


def themes(plan) -> int | None:
    """How many NEW themes a month a person's search may have mapped (None: unlimited). A theme already in the library never counts."""
    return _limit(plan, "themes_per_month")


def share_links(plan: str) -> int | None:
    """How many public share links (a deep dive's or a theme's dated snapshot) a month (None: unlimited)."""
    return PLANS[plan]["share_links_per_month"]


def networth_items(plan: str) -> int | None:
    """How many typed-in entries Net worth keeps (None: unlimited)."""
    return PLANS[plan]["networth_items"]


def mf_limit(plan: str) -> int | None:
    """How many mutual fund schemes are kept (None: no limit)."""
    return PLANS[plan]["mf_schemes"]


def journal_limit(plan: str) -> int | None:
    """How many closed trades the trade journal keeps and counts (None: no limit)."""
    return PLANS[plan]["journal_trades"]


def ai_reads_per_day(plan) -> int | None:
    """Fresh AI reads a day on a plan (Plans says it): none on Pro, RESEARCH_AI_PER_DAY on Basic, Free's own (5) on Free; a profile on
    Free in the grace keeps the old 60. Reads already written for a company or a market, and the market mood, never count
    (intel/routes.ai_call); a Free reader's company read is the Basic/Pro one when it is written (intel/routes.company_ai)."""
    from .config import settings
    plan_name = plan_of(plan) if isinstance(plan, dict) else plan
    if plan_name == "basic":
        return settings.RESEARCH_AI_PER_DAY
    return _limit(plan, "ai_reads_per_day")


def search_ai_per_day(plan) -> int | None:
    """The search box's AI answers (ideas, ask) a day: Free 10, Basic and Pro 40 (a plan, or a profile: _limit)."""
    return _limit(plan, "search_ai_per_day")


def free_change_notice(profile: dict | None, now: datetime | None = None) -> dict | None:
    """The one-time notice on Account and My space for an account in the grace: when its Free counts change and exactly what changes
    (old and new for each), and the downloads that move to Basic. None for everyone else. No email is sent about it."""
    end = free_grace_until(profile, now)
    if end is None or plan_of(profile) != "free":
        return None
    return {"on": end.isoformat(),
            "rows": [{"key": k, "label": label, "before": FREE_BEFORE[k], "after": PLANS["free"][k]} for k, label in FREE_CHANGE_WORDS],
            "moves": [REFRESH_MOVES, "The tax report's CSV and PDF downloads move to Basic (the report on screen stays free)"]}


# A Refresh of a stored read is one fresh AI read (LIVE7B-002), held to the plan's daily count; Free has none (refreshes_allowed)
REFRESH_MOVES = "Refreshing a stored read (each Refresh is one fresh AI read) moves to Basic"
REFRESH_PLANS = ("basic", "pro")


def refreshes_allowed(plan: str, profile: dict | None = None) -> bool:
    """FREE-TIER: whether a plan may Refresh a stored shared read (an AI read, a theme's read): Basic and Pro, each Refresh one fresh AI
    read held to the plan's daily count; not Free (0 a day), except a Free account in the grace, which keeps it (held to its old 60)."""
    if plan in REFRESH_PLANS:
        return True
    return plan == "free" and profile is not None and free_grace_until(profile) is not None


def plan_info(plan: str, profile: dict | None = None) -> dict:
    """What a plan includes, for /me; with the `profile`, the counts as that account has them (a Free account in the grace: FREE_BEFORE)."""
    who = profile if profile is not None and plan_of(profile) == plan else plan
    info = {k: v for k, v in PLANS[plan].items() if k != "features"}
    out = {**info, "group_size": group_size(who), "holdings": holdings_limit(plan), "stock_alerts": stock_alerts(who),
           "screens": screens(who), "deepdives_per_month": deepdives(who), "decks_per_month": decks(who), "themes_per_month": themes(who),
           "networth_items": networth_items(plan), "mf_schemes": mf_limit(plan), "journal_trades": journal_limit(plan), "indicators": has_indicators(plan), "fno": has_fno(plan),
           "ai_reads_per_day": ai_reads_per_day(who), "search_ai_per_day": search_ai_per_day(who),
           "features": {f: allows(plan, f) or (isinstance(who, dict) and allows_for(who, f)) for f in FEATURES}}
    for k in ("backtests_per_month", "ai_builds_per_month"):
        out[k] = _limit(who, k)
    return out


def public_plans() -> dict:
    """What each plan includes, for the Plans page (independent of early access)."""
    return {k: {**{x: v for x, v in p.items() if x != "features"}, "ai_reads_per_day": ai_reads_per_day(k), "refresh": refreshes_allowed(k),
                "features": sorted(p["features"])}
            for k, p in PLANS.items()}


def _dt(v) -> datetime:
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def effective_plan(profile: dict, now: datetime | None = None) -> str:
    """A paid plan only counts while the subscription is active and not past its period end (at `now`, else now)."""
    plan = profile.get("plan") or "free"
    if plan not in PLANS or plan == "free":
        return "free"
    if profile.get("plan_status") != "active":
        return "free"
    end = profile.get("current_period_end")
    if end and _dt(end) + GRACE < (now or datetime.now(timezone.utc)):
        return "free"
    return plan


IST = timezone(timedelta(hours=5, minutes=30))

# ---------- launch offer: everyone gets Pro until a date the admin sets ----------
PROMO_KEY = "promo:free_until"
PROMO_TTL = 30.0
_promo: dict = {"read_at": 0.0, "until": None}


def promo_until() -> datetime | None:
    """When the free-for-everyone offer ends, or None when there isn't one. Read from the database every 30 s."""
    import time
    from . import db
    if time.monotonic() - _promo["read_at"] > PROMO_TTL:
        try:
            raw = db.get_setting(PROMO_KEY)
            _promo["until"] = _dt(raw) if raw else None
        except Exception:
            pass   # keep the last known value if the database blips
        _promo["read_at"] = time.monotonic()
    return _promo["until"]


def promo_active(now: datetime | None = None) -> bool:
    until = promo_until()
    return bool(until and (now or datetime.now(timezone.utc)) < until)


def set_promo(days: int | None) -> datetime | None:
    """Start the offer now for `days` days, or end it (None)."""
    from . import db
    if days:
        # ends at the end of an Indian day (midnight IST) on or after the `days`, not at the minute it was started: an offer begun at 1:56 am
        # "ended at 1:56 am", which confused (LIVE1C-037); it lasts at least the days asked
        t = (datetime.now(timezone.utc) + timedelta(days=days)).astimezone(IST)
        if (t.hour, t.minute, t.second, t.microsecond) != (0, 0, 0, 0):
            t = (t + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        until = t.astimezone(timezone.utc)
        db.set_setting(PROMO_KEY, until.isoformat())
    else:
        until = None
        db.delete_setting(PROMO_KEY)
    _promo.update(read_at=0.0, until=until)
    return until


# ---------- free Basic time: earned by inviting friends (invite_rewards.py) ----------
FREE_KEY = "freebasic:"          # freebasic:<uid>: {"until": when free Basic ends, "banked": days kept for later}
FREE_TTL = 30.0
_free: dict = {"read_at": -1e9, "rows": {}}


def _free_rows() -> dict:
    """{uid: free Basic record} for everyone who has one. Read from the database every 30 s (only people who earned
    time are stored, so it's a short list)."""
    import json
    import time
    from . import db
    if time.monotonic() - _free["read_at"] > FREE_TTL:
        try:
            rows = {}
            for k, v in db.all_settings_with_prefix(FREE_KEY):
                try:
                    val = json.loads(v)
                except (ValueError, TypeError):
                    continue
                if isinstance(val, dict):
                    rows[k[len(FREE_KEY):]] = val
            _free["rows"] = rows
        except Exception:
            pass   # keep the last known rows if the database blips
        _free["read_at"] = time.monotonic()
    return _free["rows"]


def forget_free_basic():
    """Drop the copy so the next check reads the database (after a change, and between tests)."""
    _free.update(read_at=-1e9, rows={})


def free_basic(uid: str | None) -> dict:
    """{"until": datetime or None, "banked": days} for one user."""
    row = _free_rows().get(uid or "") or {}
    try:
        until = _dt(row["until"]) if row.get("until") else None
        if until and not until.tzinfo:
            until = until.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        until = None
    banked = row.get("banked")
    return {"until": until, "banked": banked if isinstance(banked, int) and 0 < banked < 100000 else 0}


def _save_free(uid: str, until: datetime | None, banked: int):
    import json
    from . import db
    db.set_setting(FREE_KEY + uid, json.dumps({"until": until.isoformat() if until else None, "banked": banked}))
    forget_free_basic()


def add_free_basic(profile: dict, days: int, now: datetime | None = None) -> dict:
    """Give `days` of free Basic. On Free it starts now, stacked after any free time still left; someone paying for
    Basic or Pro banks it instead, and it starts the first time they're seen on Free."""
    now = now or datetime.now(timezone.utc)
    uid = profile["id"]
    have = free_basic(uid)
    until, banked = have["until"], have["banked"]
    if effective_plan(profile, now) == "free":
        until = max(until or now, now) + timedelta(days=days)
    else:
        banked += days
    _save_free(uid, until, banked)
    return {"until": until, "banked": banked}


def take_free_basic(uid: str, days: int, now: datetime | None = None) -> dict:
    """Take back `days` of free Basic given earlier (an invite reward whose payment was refunded): from the days kept
    for later first, then from the end of the free time running, never into the past."""
    now = now or datetime.now(timezone.utc)
    have = free_basic(uid)
    until, banked = have["until"], have["banked"]
    take = min(banked, days)
    banked, left = banked - take, days - take
    if left and until:
        until = max(until - timedelta(days=left), now)
    _save_free(uid, until, banked)
    return {"until": until, "banked": banked}


def free_basic_until(profile: dict, now: datetime | None = None) -> datetime | None:
    """When the user's free Basic ends, or None when they have none running. Banked days start here, the first time
    the user is on Free (their paid plan ended)."""
    now = now or datetime.now(timezone.utc)
    uid = profile.get("id")
    if not uid:
        return None
    have = free_basic(uid)
    until = have["until"]
    if have["banked"] and effective_plan(profile, now) == "free":
        until = max(until or now, now) + timedelta(days=have["banked"])
        try:
            _save_free(uid, until, 0)
        except Exception as e:      # still free Basic now; the bank is spent on the next check instead
            print("free basic: couldn't start banked days:", str(e)[:160])
    return until if until and now < until else None


def view_as_of(value) -> str | None:
    """The plan named by the "View as" header ("free", "basic" or "pro"), or None for anything else (off, empty, junk)."""
    v = str(value or "").strip().lower()
    return v if v in PLANS else None


def access_plan(profile: dict) -> str:
    """What the user can use right now: Pro for everyone during the launch offer, else what they pay for, or Basic
    while they have free Basic time (from inviting friends) and pay for less.

    The site owner (an id recorded at a Google-proved admin sign-in, admin.recorded_owner) gets Pro.
    The site owner's "View as" (auth.current_profile sets `_view_as` for a verified admin only) wins over all of it,
    the launch offer and free Basic time included, so every lock and limit shows as that plan has it. It changes this
    answer only: effective_plan, the stored plan and billing never read it."""
    seen = view_as_of(profile.get("_view_as"))
    if seen:
        return seen
    if promo_active():
        return "pro"
    from .admin import recorded_owner
    if recorded_owner(profile):     # the site owner, in background jobs too (auth.current_profile does it in a request)
        return "pro"
    plan = effective_plan(profile)
    if plan == "free":
        try:
            if free_basic_until(profile):
                return "basic"
        except Exception as e:      # free time is a bonus: a fault here never takes away anything else
            print("free basic check failed:", str(e)[:160])
    return plan


LIMIT_KEYS = ("backtests_per_month", "ai_builds_per_month", "live_limit", "group_size", "deepdives_per_month", "decks_per_month",
              "themes_per_month", "stock_alerts", "screens", "holdings", "networth_items", "mf_schemes", "journal_trades",
              "ai_reads_per_day", "search_ai_per_day")


def offer_state(now: datetime | None = None, promo: bool = True) -> dict:
    """What anyone can buy and use today, in one answer: the landing page, Plans and the in-app banners all read this
    (through /pricing before sign-in and /me after), so they can't say different things.

    mode: "promo" while the launch offer gives everyone Pro; else "early" while payments aren't set up (nobody can buy
    a plan, so every feature is open and only some Free limits apply); else "paid".
    free_now: the Free plan's limits as they apply today (in early access most are lifted to Pro's).
    promo=False leaves the launch offer out, as the site owner sees it while viewing as a plan."""
    from . import billing
    payments = billing.enabled()
    until = promo_until() if promo and promo_active(now) else None
    info = plan_info("free")
    return {
        "mode": "promo" if until else "paid" if payments else "early",
        "payments": payments,
        "yearly": billing.yearly_enabled(),
        "promo_until": until.isoformat() if until else None,
        "free_now": {k: info[k] for k in LIMIT_KEYS},
        "free_trial_days": PLANS["free"]["live_trial_days"],
    }


def plan_of(profile: dict) -> str:
    """The plan to check a feature against: the one sign-in resolved for this request (`_plan`, which also knows the
    site owner), else worked out from the stored profile (background jobs read profiles from the database).
    Re-working it out in a request ignored the owner, and a test or caller that set `_plan` alone."""
    p = profile.get("_plan")
    return p if p in PLANS else access_plan(profile)


TRIAL_DAY_CLOSE = (15, 30)      # NSE's close, India time


def trial_end(started: datetime, days: int) -> datetime:
    """Midnight (India time) after the `days`-th Indian trading day, counting the start day if it is one and the
    start came before the 15:30 close. Weekends and exchange holidays don't count: started on a Saturday, or on a
    weekday after the close, it runs to the end of the fifth trading day after (owner, 28 Oct: an evening start
    shouldn't spend a day of the trial)."""
    from .data.calendar import is_trading_day
    at = started.astimezone(IST)
    d = at.date()
    if (at.hour, at.minute) >= TRIAL_DAY_CLOSE:
        d += timedelta(days=1)             # after the close: the trial's first day is the next trading day
    left = days
    while True:
        if is_trading_day("IN", d):
            left -= 1
            if left == 0:
                break
        d += timedelta(days=1)
    return datetime(d.year, d.month, d.day, tzinfo=IST) + timedelta(days=1)


def trial_days_left(ends: datetime, now: datetime | None = None) -> int:
    """The Indian trading days of the trial still to come, today's included while it runs (Account says it, DP2-031)."""
    from .data.calendar import is_trading_day
    now = now or datetime.now(timezone.utc)
    if now >= ends:
        return 0
    d, last = now.astimezone(IST).date(), (ends.astimezone(IST) - timedelta(days=1)).date()
    n = 0
    while d <= last:
        n += is_trading_day("IN", d)
        d += timedelta(days=1)
    return n


def trial_state(profile: dict) -> dict:
    days = PLANS["free"]["live_trial_days"]
    started = profile.get("live_trial_started_at")
    if not started:
        return {"started": False, "active": False, "ends_at": None, "available": True, "days": days, "days_left": days}
    ends = trial_end(_dt(started), days)
    active = datetime.now(timezone.utc) < ends
    return {"started": True, "active": active, "ends_at": ends.isoformat(), "available": active, "days": days,
            "days_left": trial_days_left(ends)}


# ---------- the one lock wording (DP2-022, DP1-018) ----------
# Every lock and limit says the same three things in the same order: what is locked or used up and on which plan, when a
# monthly count starts again, and what the next plan gives. The price and the way to get it ("Basic is ₹699 a month or
# ₹6,999 a year." and See plans, or early access while nothing is on sale) are added after it: by upgrade_note on the
# server while no plan can be bought, by the page in the visitor's own currency while one can (the 402 names the plan).
def resets_on(now: datetime | None = None) -> str:
    """The day a monthly count starts again, in India time: "1 Nov"."""
    d = (now or datetime.now(timezone.utc)).astimezone(IST)
    first = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return f"{first.day} {first.strftime('%b')}"


def resets_note(now: datetime | None = None) -> str:
    """A monthly limit's last sentence, with its leading space: ' The count starts again on 1 Nov.'"""
    return f" The count starts again on {resets_on(now)}."


def limit_message(plan: str, key: str, used_words: str, what: str, monthly: bool = False, after: str = "") -> str:
    """A count limit in the one wording: "<used_words>.[ The count starts again on 1 Nov.] Basic gives 25." (or "Pro has no
    limit on <what>."); `after` goes between the reset and the next plan (what still works, what to do)."""
    nxt = bigger_plan(plan, key)
    more = ""
    if nxt:
        cap = PLANS[nxt.lower()][key]
        more = f" {nxt} has no limit on {what}." if cap is None else f" {nxt} gives {cap}{' a month' if monthly else ''}."
    return f"{used_words.rstrip('.')}." + (resets_note() if monthly else "") + (f" {after.strip()}" if after.strip() else "") + more


def not_on_plan(plan: str, key: str, what: str, monthly: bool = True, after: str = "") -> str:
    """A limit of 0 (Free's decks) in the one wording: "Slide decks are on Basic: 5 a month." (or "...on Pro, with no limit."), never
    "You've made 0 decks this month"; `after` follows it (what still works)."""
    nxt = bigger_plan(plan, key) or "Pro"
    cap = PLANS[nxt.lower()][key]
    head = f"{what} are on {nxt}, with no limit." if cap is None else f"{what} are on {nxt}: {cap}{' a month' if monthly else ''}."
    return head + (f" {after.strip()}" if after.strip() else "")


def named_plan(message: str) -> str | None:
    """The plan a 402's words send the reader to ("basic" or "pro"), so the page can add its price."""
    import re
    m = re.search(r"\b(Basic|Pro)\b", message or "")
    return m.group(1).lower() if m else None
