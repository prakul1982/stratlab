/* What each plan includes, for visitors who aren't signed in (the landing page) and until /me arrives (Plans).
 * The server's plans.py is the source of truth: tests/test_plan_copy.py fails when these numbers drift from it, and
 * the same amounts must be set on the Razorpay plans. */

export type PlanId = "free" | "basic" | "pro";
export const PLAN_IDS: PlanId[] = ["free", "basic", "pro"];
export const PLAN_NAME: Record<PlanId, string> = { free: "Free", basic: "Basic", pro: "Pro" };

/** Rupee prices including GST: [a month, a year]. */
export const PRICE: Record<PlanId, [number, number]> = { free: [0, 0], basic: [699, 6999], pro: [1999, 19999] };

export type Limits = { backtests_per_month: number | null; ai_builds_per_month: number | null; live_limit: number; group_size: number;
  deepdives_per_month: number | null; decks_per_month: number | null; stock_alerts: number; screens: number; holdings: number;
  networth_items: number | null; mf_schemes: number | null; journal_trades: number | null;
  /** Market Watch (MW-1): lists, symbols in one list, charts whose drawings are kept, indicators on one chart. null: no limit. */
  watchlists: number | null; watchlist_symbols: number | null; chart_saves: number | null; chart_indicators: number | null;
  /** Fresh AI reads a day (plans.ai_reads_per_day): a company's read already written today and the market mood never count. */
  ai_reads_per_day: number | null; features: string[] };

export const LIMITS: Record<PlanId, Limits> = {
  free: { backtests_per_month: 10, ai_builds_per_month: 10, live_limit: 1, group_size: 10, deepdives_per_month: 2, decks_per_month: 1,
    stock_alerts: 5, screens: 2, holdings: 30, networth_items: 5, mf_schemes: 5, journal_trades: 50,
    watchlists: 1, watchlist_symbols: 20, chart_saves: 3, chart_indicators: 3, ai_reads_per_day: 60, features: [] },
  basic: { backtests_per_month: 100, ai_builds_per_month: 100, live_limit: 2, group_size: 25, deepdives_per_month: 15, decks_per_month: 5,
    stock_alerts: 25, screens: 10, holdings: 100, networth_items: null, mf_schemes: null, journal_trades: null,
    watchlists: 10, watchlist_symbols: 100, chart_saves: null, chart_indicators: 10, ai_reads_per_day: 60,
    features: ["indicators", "group_live", "options", "alerts", "daily_report", "newsletter", "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "money_reminders", "breadth", "positioning", "journal", "mf_costs", "etf_gaps", "fo_alerts", "cas_history", "vix_filter",
      "chart_replay",
      "event_reminders",
      "biz_updates", "holders",
      "stock_futures", "mtf",
      "mf_behaviour", "sip_luck", "rates_slab", "loan_check",
      "ipo_summary", "ipo_alerts"] },
  pro: { backtests_per_month: null, ai_builds_per_month: null, live_limit: 10, group_size: 50, deepdives_per_month: null, decks_per_month: null,
    stock_alerts: 100, screens: 25, holdings: 300, networth_items: null, mf_schemes: null, journal_trades: null,
    watchlists: null, watchlist_symbols: null, chart_saves: null, chart_indicators: null, ai_reads_per_day: null,
    features: ["indicators", "fno", "group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report", "export", "newsletter",
      "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "tax_tools", "money_reminders", "breadth", "positioning", "journal", "itr_export", "us_tax", "mf_costs", "etf_gaps", "fo_alerts", "options_whatif", "cas_history",
      "vix_filter", "strike_rules",
      "chart_replay", "signal_webhooks",
      "event_reminders",
      "biz_updates", "holders",
      "assistant",
      "stock_futures", "mtf",
      "mf_behaviour", "sip_luck", "rates_slab", "loan_check",
      "ipo_summary", "ipo_alerts"] },
};

// Free has every market and the core tools, not every tool: Replay, Forward test, the scans and the full journal are paid (DP1-021)
export const WHO: Record<PlanId, string> = { free: "Every market and the core tools, free", basic: "For investors and part-time traders", pro: "For active traders and heavy research" };

const L = LIMITS;
// six to eight short lines a card, each a topic with its items (DK-003: the old cards were run-on paragraphs); built from the
// limits above so a card never says a different number. tests/test_plan_copy.py checks that each paid feature is named on
// the card of the plan that adds it. The detail of every limit and feature is in the Plans page's "Side by side" tables.
/** The daily safety cap on Pro's unlimited AI builds (the server's AI_BUILDS_PER_DAY). */
export const AI_BUILDS_PER_DAY = 200;

/** The comparison table's cell for a limit that has none: Pro's AI builds still have a daily safety cap. */
export const unlimitedLabel = (p: PlanId, k: keyof Limits) => (p === "pro" && k === "ai_builds_per_month" ? `Unlimited (up to ${AI_BUILDS_PER_DAY} a day)` : "Unlimited");

export const FEATURES: Record<PlanId, string[]> = {
  free: [`${L.free.backtests_per_month} backtests a month, each with a full verdict, and ${L.free.ai_builds_per_month} AI strategy builds`,
    `Paper trading trial: ${L.free.live_limit} strategy on 1 stock for 5 market days from your first start, then Basic or Pro`,
    "Options builder with Greeks and breakevens after charges",
    `Today's derivatives positioning and F&O contract changes, and a journal of your last ${L.free.journal_trades} trades`,
    // a deep dive on Free has the report card and checklist too (DP1-021); a company's PDF and PowerPoint are one deck (DP1-026)
    `${L.free.deepdives_per_month} company deep dives a month, each with the report card and checklist, and ${L.free.decks_per_month} company slide deck (its PDF and PowerPoint count as one)`,
    "Price charts, screens, sector rotation, today's market breadth, ETF prices against NAV and red flags on every company",
    `${L.free.stock_alerts} stock alerts and ${L.free.screens} saved screens; import up to ${L.free.holdings} holdings, ${L.free.mf_schemes} mutual funds and ${L.free.networth_items} net worth entries; Market Watch with ${L.free.watchlists} list of ${L.free.watchlist_symbols} symbols and drawings kept on ${L.free.chart_saves} charts`,
    // the same words as the table's row (DP2-010: "a weekly My Stocks email" here, "Weekly Market Brief and My Stocks" there)
    "Tax report, money calendar, the Market Brief on News, the weekly Market Brief and My Stocks emails, every market we cover and your own CSV"],
  basic: ["Everything in Free, plus:",
    // "No ads" opens the first line: a ninth line would break the card's six to eight (DK-003)
    `No ads, ${L.basic.backtests_per_month} backtests and ${L.basic.ai_builds_per_month} AI builds a month, with all 20+ indicators: MACD, Supertrend, VWAP and more`,
    `Paper trade ${L.basic.live_limit} strategies at a time, whole groups on intraday candles and options at set times, with trade notifications and a daily report`,
    "Trading tools: full trade journal, positioning history, stock futures history, closing auction history, chart replay practice, an India VIX entry filter, SIP dip rules",
    "Alerts: F&O change alerts, ETF gap alerts, IPO alerts and market event reminders and money reminders; the daily Market Brief and My Stocks by email",
    `${L.basic.deepdives_per_month} company deep dives and ${L.basic.decks_per_month} company slide decks a month, business updates in numbers, named-holder search and IPO offer document summaries`,
    "Scans and watchlist: the Stage 2 scan and every other trend scan, watchlist red flags (and each holding's filings and results date), Watchlist at a glance, market breadth charts, margin funding history",
    "Money: every mutual fund and net worth entry, fund capital gains, fund costs in rupees, fund behaviour, dividends with TDS, deposit rates after your own tax, a floating-rate loan check",
    `${L.basic.stock_alerts} stock alerts, ${L.basic.screens} saved screens, ${L.basic.holdings} holdings, ${L.basic.watchlists} Market Watch lists of ${L.basic.watchlist_symbols}, drawings kept on every chart`],
  pro: ["Everything in Basic, plus:", `Unlimited backtests, deep dives and decks; up to ${AI_BUILDS_PER_DAY} AI builds a day`,
    `Paper trade ${L.pro.live_limit} strategies at a time; group tests of up to ${L.pro.group_size}, with faster entries and a spread limit`,
    "Indian F&O contracts (futures and options on stocks and indices) in notebooks, each backtested on its own past prices; the stocks themselves are on every plan",
    "Options paper trading on your own rules' signals, strikes picked by delta or premium, and what-if sliders with a roll preview",
    "Export a notebook's rules and trades, forward-test alert webhooks in paper trading, and StratLab in your AI assistant",
    "Advance tax amounts and the long-term exemption lot by lot",
    "US stocks in Indian tax sale by sale, and ITR-ready schedules with a PDF pack for your CA",
    `${L.pro.stock_alerts} stock alerts, ${L.pro.screens} saved screens, ${L.pro.holdings} holdings, unlimited Market Watch lists and indicators`],
};

/** Ads (ADS-1), one row of the comparison table: Free accounts and signed-out pages may show Google ads, only after the visitor allows
 * them (lib/ads.ts); Basic and Pro never do. The cards say it once, on the plan that adds it (Basic; Pro includes Basic). */
export const ADS: Record<PlanId, string> = { free: "After you allow them", basic: "None", pro: "None" };

export const NUMBERS: [keyof Limits, string][] = [["backtests_per_month", "Backtests a month, each with a verdict"], ["ai_builds_per_month", "AI strategy builds a month"],
  ["live_limit", "Paper trading sessions at a time"], ["group_size", "Instruments in a group test"], ["deepdives_per_month", "Company deep dives a month"],
  ["decks_per_month", "Company slide decks a month (a company's PDF and PowerPoint are one deck)"], ["stock_alerts", "Stock alerts on at a time"], ["screens", "Saved screens"], ["holdings", "Holdings kept"],
  ["mf_schemes", "Mutual fund schemes kept"], ["networth_items", "Net worth entries"], ["journal_trades", "Trades the journal keeps"],
  ["watchlists", "Market Watch lists (the first is your Research watchlist)"], ["watchlist_symbols", "Symbols in one Market Watch list"],
  ["chart_saves", "Charts that keep your drawings and indicators"], ["chart_indicators", "Indicators on one chart"],
  ["ai_reads_per_day", "Fresh AI reads a day (a company's read already written today, and the market mood, never count)"]];
export const FLAGS: [string, string][] = [["indicators", "All 20+ indicators in strategy rules"], ["group_live", "Paper trade a whole group (on 5-minute, 15-minute or 1-hour candles)"], ["options", "Options paper trading at set times"],
  ["alerts", "Trade notifications"], ["daily_report", "Daily report after the close"], ["newsletter", "Daily Market Brief and My Stocks by email"],
  ["scans", "Stage 2 + Supertrend scan, with a daily alert"],
  // what the filings feature unlocks on My Holdings too, so Plans and that page's lock agree (DP2-009)
  ["filings", "Red flags across your watchlist and holdings: each holding's red flags, recent filings and results date on My Holdings, with an evening alert"],
  ["investor_home", "Watchlist at a glance"], ["fno", "Indian F&O in notebooks and backtests"], ["options_signal", "Options entered on your own rules' signals"],
  ["fast_entries", "Faster group entries and a spread limit"], ["export", "Export a notebook's rules and trades"],
  // each says the Free limit it lifts, so the page's lock does too (DP2-012: the Mutual funds lock didn't name the 5 funds)
  ["networth", `Every net worth entry (Free keeps ${LIMITS.free.networth_items}) and the monthly history`],
  ["mf_gains", `Every mutual fund scheme (Free keeps ${LIMITS.free.mf_schemes}) and capital gains by year`],
  // Tax tools' table by company (My Holdings lists each holding's dividends on every plan, DP2-010)
  ["dividends", "Dividends by company on Tax tools, with the TDS expected and US tax withheld"], ["tax_tools", "Advance tax amounts and long-term exemption facts per lot"],
  ["money_reminders", "Money calendar reminders by email or phone"],
  ["mf_costs", "Fund costs: each fund's TER parts in rupees, both plans side by side, and changes since you bought"],
  ["breadth", "Market breadth history, charts and sector table"],
  ["positioning", "Derivatives positioning history and IV percentiles"],
  ["journal", "Trade journal: every trade, the honesty checks, breakdowns and paper vs real"],
  ["itr_export", "ITR-ready schedules and a PDF pack for your CA"], ["us_tax", "US stocks in Indian tax sale by sale: each sale's gain in rupees, the foreign tax credit and Schedule FA"],
  ["etf_gaps", "Alerts on an ETF's price against its NAV"],

["fo_alerts", "Alerts when an F&O exit, lot size or expiry change touches your watchlist or paper sessions"],
  ["options_whatif", "Options what-if: move the underlying, shift IV and pass days, and preview rolling a leg"],
  ["cas_history", "Closing auction history: 60 days of auction closes against the reference price, and index closes"],
  ["vix_filter", "Options sessions that enter only inside an India VIX band"],
  ["strike_rules", "Option strikes picked by model delta, a delta range, premium or a share of the ATM straddle"],
  ["chart_replay", "Chart replay practice on past candles, logged to the journal"],
  ["signal_webhooks", "Forward-test TradingView or Chartink alerts in paper trading with a secret webhook"],
  ["event_reminders", "Reminders of market events: RBI policy, data releases, the Fed, index changes and expiries"],
  ["biz_updates", "Monthly and quarterly business updates read into numbers, the sector view and an alert on new ones"],
  ["holders", "Named holders above 1%: search a holder across companies and follow their changes"],
  ["assistant", "StratLab in your AI assistant: your data and paper orders in Claude or ChatGPT"],
  ["stock_futures", "Stock futures: each F&O stock's OI, buildup, rollover, basis and MWPL history, with MWPL alerts"],
  ["mtf", "Margin funding: each stock's and the market's MTF history, with alerts on a funded level"],
  ["mf_behaviour", "Fund behaviour: your return against each fund's in rupees, your SIP record and redemptions after a fall"],
  ["sip_luck", "SIP test: dip rules, and the same SIP from every start month"],
  ["rates_slab", "Fixed-income rates after tax at the rate from your own tax estimate"],
  ["loan_check", "Floating-rate loans: is your rate following its benchmark, and what each change did"],
  ["ipo_summary", "IPO offer document summaries: what the company does, its figures, what the money is for, the main risk factors and the promoters"],
  ["ipo_alerts", "IPO alerts: when an issue opens, closes, is allotted or lists"]];
export const EVERYONE = ["Every market, and your own CSV",
  "Price charts: candles, Heikin-Ashi or bars, indicators, drawings kept on your account, and compare",
  "Market Watch on every page: lists across every market we cover, live prices, and charts from 1 minute to 1 month with drawings",
  "Options builder: charges to open and close, breakevens and the most it can make or lose after them", "Screens (unlimited runs), sector rotation and the results calendar", "Red flags on every company page",
  "Corporate actions, deals and surveillance lists", "Today's market breadth numbers", "Derivatives positioning today: participant OI, FII/DII flows, PCR and the option chain facts",
  "F&O contract changes: stocks entering and leaving F&O, lot sizes and expiry days",
  "Closing auction, live: each F&O stock's reference and indicative price, the indices and the expiry settlement",
  "Market events calendar: RBI policy, data releases, the Fed, index changes, expiries and holidays",
  "Option Greeks for every strike and your position, and the payoff today beside the one at expiry (model estimates)",
  "A trade journal with the basic stats", "My Holdings, the tax report and the year's total tax estimate", "Money calendar and its calendar feed",
  // what Free sees on these pages, in the words the pages use (DP2-010: Holdings' dividends, US tax's year totals, the ITR preview)
  "Each holding's dividends on My Holdings; the year's dividend total, and each year's US share gains in rupees, on Tax tools and US stocks tax",
  "Advance tax due dates and the exemption used", "A preview of the ITR-ready export: each schedule's totals and line counts",
  "Weekly Market Brief and My Stocks emails", "Public company pages, share cards and invite links", "ETF prices against their NAV, with 30 days of history",
  "Named holders above 1% and the business-update filings on every company page",
  "Stock futures today: OI buildup, rollover, basis and MWPL use for every F&O stock", "Stock lending fees that traded for your holdings",
  "Margin-funded positions per stock today, and your own MTF cost worked out",
  "IPOs in India and the US: dates, price bands, lot sizes, the bids by category while an issue is open, the offer documents' key facts, and listings against the issue price"];

/** The cheapest plan that includes a feature flag ("free" when neither paid list names it). */
export function planOf(feature: string): PlanId {
  return LIMITS.basic.features.includes(feature) ? "basic" : LIMITS.pro.features.includes(feature) ? "pro" : "free";
}

/** The comparison table's "What each plan adds" in three parts with their own subheadings, so 40-odd rows read as trading,
 * research and money (DI-032, DP1-022). A feature not named here goes under Research. */
export const FLAG_GROUPS: { id: "trade" | "research" | "money"; title: string }[] = [
  { id: "trade", title: "Trading" }, { id: "research", title: "Research and alerts" }, { id: "money", title: "Money and tax" }];
export const FLAG_GROUP: Record<string, "trade" | "research" | "money"> = {
  indicators: "trade", group_live: "trade", options: "trade", alerts: "trade", daily_report: "trade", fno: "trade", options_signal: "trade",
  fast_entries: "trade", export: "trade", positioning: "trade", journal: "trade", fo_alerts: "trade", options_whatif: "trade", cas_history: "trade",
  vix_filter: "trade", strike_rules: "trade", chart_replay: "trade", signal_webhooks: "trade", event_reminders: "trade", stock_futures: "trade",
  mtf: "trade", assistant: "trade",
  networth: "money", mf_gains: "money", dividends: "money", tax_tools: "money", money_reminders: "money", mf_costs: "money", itr_export: "money",
  us_tax: "money", mf_behaviour: "money", sip_luck: "money", rates_slab: "money", loan_check: "money",
};
