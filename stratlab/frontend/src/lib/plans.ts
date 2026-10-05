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
  networth_items: number | null; mf_schemes: number | null; journal_trades: number | null; features: string[] };

export const LIMITS: Record<PlanId, Limits> = {
  free: { backtests_per_month: 10, ai_builds_per_month: 10, live_limit: 1, group_size: 10, deepdives_per_month: 2, decks_per_month: 1,
    stock_alerts: 5, screens: 2, holdings: 30, networth_items: 5, mf_schemes: 5, journal_trades: 50, features: [] },
  basic: { backtests_per_month: 100, ai_builds_per_month: 100, live_limit: 2, group_size: 25, deepdives_per_month: 15, decks_per_month: 5,
    stock_alerts: 25, screens: 10, holdings: 100, networth_items: null, mf_schemes: null, journal_trades: null,
    features: ["indicators", "group_live", "options", "alerts", "daily_report", "newsletter", "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "money_reminders", "breadth", "positioning", "journal", "mf_costs", "etf_gaps", "fo_alerts", "chart_replay"] },
  pro: { backtests_per_month: null, ai_builds_per_month: null, live_limit: 10, group_size: 50, deepdives_per_month: null, decks_per_month: null,
    stock_alerts: 100, screens: 25, holdings: 300, networth_items: null, mf_schemes: null, journal_trades: null,
    features: ["indicators", "fno", "group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report", "export", "newsletter",
      "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "tax_tools", "money_reminders", "breadth", "positioning", "journal", "itr_export", "us_tax", "mf_costs", "etf_gaps", "fo_alerts", "options_whatif",
      "chart_replay", "signal_webhooks"] },
};

export const WHO: Record<PlanId, string> = { free: "Try every tool", basic: "For investors and part-time traders", pro: "For active traders and heavy research" };

const L = LIMITS;
// at most 9 lines a card, Trade then Invest then Money, built from the limits above so a card never says a different
// number; tests/test_plan_copy.py checks that each paid feature is named on the card of the plan that adds it. The
// full grid is on Plans.
export const FEATURES: Record<PlanId, string[]> = {
  free: [`${L.free.backtests_per_month} backtests a month, each with a full verdict, and ${L.free.ai_builds_per_month} AI strategy builds`,
    "Paper trading free for 5 market days, and the options builder with Greeks and breakevens after charges",
    `Today's derivatives positioning, F&O contract changes, and a journal of your last ${L.free.journal_trades} trades`,
    `${L.free.deepdives_per_month} company deep dives and ${L.free.decks_per_month} slide deck a month`,
    "Price charts, screens, sector rotation, today's market breadth, ETF prices against NAV and red flags on every company",
    `${L.free.stock_alerts} stock alerts and ${L.free.screens} saved screens`,
    `Import up to ${L.free.holdings} holdings, ${L.free.mf_schemes} mutual funds and ${L.free.networth_items} net worth entries`,
    "The tax report, money calendar and a weekly My Stocks email", "Every market we cover, and your own CSV"],
  basic: ["Everything in Free, plus:", `${L.basic.backtests_per_month} backtests and ${L.basic.ai_builds_per_month} AI builds a month`,
    "All 20+ indicators in your rules: MACD, Supertrend, Bollinger Bands, VWAP and more",
    `Paper trade ${L.basic.live_limit} strategies at a time, whole groups and options at set times, with trade notifications and a daily report`,
    "The full trade journal, chart replay practice, positioning history with IV percentiles, and F&O change alerts",
    `${L.basic.deepdives_per_month} company deep dives (report card and checklist) and ${L.basic.decks_per_month} decks a month`,
    "Stage 2 scan, watchlist red flags, Watchlist at a glance and market breadth charts, with alerts",
    "Every mutual fund and net worth entry, fund capital gains and fund costs in rupees, dividends with TDS, and money reminders",
    `${L.basic.stock_alerts} stock alerts and ETF gap alerts, ${L.basic.screens} saved screens, ${L.basic.holdings} holdings, and the daily Market Brief and My Stocks`],
  pro: ["Everything in Basic, plus:", "Unlimited backtests, AI builds, deep dives and decks", `Paper trade ${L.pro.live_limit} strategies at a time`,
    "Indian F&O, options entered on your own rules' signals, and options what-if sliders with a roll preview", `Group tests of up to ${L.pro.group_size}, with faster entries and a spread limit`,
    "Export rules and trades, and forward-test alert webhooks in paper trading", "Advance tax amounts, and the long-term exemption lot by lot",
    "US stocks in Indian tax, and ITR-ready schedules with a PDF pack for your CA",
    `${L.pro.stock_alerts} stock alerts, ${L.pro.screens} saved screens, ${L.pro.holdings} holdings`],
};

export const NUMBERS: [keyof Limits, string][] = [["backtests_per_month", "Backtests a month, each with a verdict"], ["ai_builds_per_month", "AI strategy builds a month"],
  ["live_limit", "Paper trading sessions at a time"], ["group_size", "Instruments in a group test"], ["deepdives_per_month", "Company deep dives a month"],
  ["decks_per_month", "Company slide decks a month"], ["stock_alerts", "Stock alerts on at a time"], ["screens", "Saved screens"], ["holdings", "Holdings kept"],
  ["mf_schemes", "Mutual fund schemes kept"], ["networth_items", "Net worth entries"], ["journal_trades", "Trades the journal keeps"]];
export const FLAGS: [string, string][] = [["indicators", "All 20+ indicators in strategy rules"], ["group_live", "Paper trade a whole group"], ["options", "Options paper trading at set times"],
  ["alerts", "Trade notifications"], ["daily_report", "Daily report after the close"], ["newsletter", "Daily Market Brief and My Stocks"],
  ["scans", "Stage 2 + Supertrend scan, with a daily alert"], ["filings", "Red flags for the whole watchlist, with an evening alert"],
  ["investor_home", "Watchlist at a glance"], ["fno", "Indian F&O"], ["options_signal", "Options entered on your own rules' signals"],
  ["fast_entries", "Faster group entries and a spread limit"], ["export", "Export rules and trades"],
  ["networth", "Net worth: unlimited entries and the monthly history"],
  ["mf_gains", "Mutual funds: every scheme, and capital gains by year"],
  ["dividends", "Dividends by company, with TDS and US tax withheld"], ["tax_tools", "Advance tax amounts and long-term exemption facts per lot"],
  ["money_reminders", "Money calendar reminders by email or phone"],
  ["mf_costs", "Fund costs: each fund's TER parts in rupees, both plans side by side, and changes since you bought"],
  ["breadth", "Market breadth history, charts and sector table"],
  ["positioning", "Derivatives positioning history and IV percentiles"],
  ["journal", "Trade journal: every trade, the honesty checks, breakdowns and paper vs real"],
  ["itr_export", "ITR-ready schedules and a PDF pack for your CA"], ["us_tax", "US stocks in Indian tax: gains in rupees, foreign tax credit and Schedule FA"],
  ["etf_gaps", "Alerts on an ETF's price against its NAV"],

["fo_alerts", "Alerts when an F&O exit, lot size or expiry change touches your watchlist or paper sessions"],
  ["options_whatif", "Options what-if: move the underlying, shift IV and pass days, and preview rolling a leg"],
  ["chart_replay", "Chart replay practice on past candles, logged to the journal"],
  ["signal_webhooks", "Forward-test TradingView or Chartink alerts in paper trading with a secret webhook"]];
export const EVERYONE = ["Every market, and your own CSV",
  "Price charts: candles, Heikin-Ashi or bars, indicators, drawings kept on your account, and compare",
  "Options builder: charges to open and close, breakevens and the most it can make or lose after them", "Screens (unlimited runs), sector rotation and the results calendar", "Red flags on every company page",
  "Corporate actions, deals and surveillance lists", "Today's market breadth numbers", "Derivatives positioning today: participant OI, FII/DII flows, PCR and the option chain facts",
  "F&O contract changes: stocks entering and leaving F&O, lot sizes and expiry days",
  "Option Greeks for every strike and your position, and the payoff today beside the one at expiry (model estimates)",
  "A trade journal with the basic stats", "My Holdings, the tax report and the year's total tax estimate", "Money calendar and its calendar feed",
  "Dividend and US share totals for each year, advance tax due dates and the exemption used", "A preview of the ITR-ready export",
  "Weekly Market Brief and My Stocks", "Public company pages, share cards and invite links", "ETF prices against their NAV, with 30 days of history"];
