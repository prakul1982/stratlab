/* What each plan includes, for visitors who aren't signed in (the landing page) and until /me arrives (Plans).
 * The server's plans.py is the source of truth: tests/test_plan_copy.py fails when these numbers drift from it, and
 * the same amounts must be set on the Razorpay plans. */

export type PlanId = "free" | "basic" | "pro";
export const PLAN_IDS: PlanId[] = ["free", "basic", "pro"];
export const PLAN_NAME: Record<PlanId, string> = { free: "Free", basic: "Basic", pro: "Pro" };

/** Rupee prices including GST: [a month, a year]. */
export const PRICE: Record<PlanId, [number, number]> = { free: [0, 0], basic: [699, 6999], pro: [1999, 19999] };

export type Limits = { backtests_per_month: number | null; ai_builds_per_month: number | null; live_limit: number; group_size: number;
  deepdives_per_month: number | null; decks_per_month: number | null; stock_alerts: number; screens: number; holdings: number; features: string[] };

export const LIMITS: Record<PlanId, Limits> = {
  free: { backtests_per_month: 10, ai_builds_per_month: 10, live_limit: 1, group_size: 10, deepdives_per_month: 2, decks_per_month: 1,
    stock_alerts: 5, screens: 2, holdings: 30, features: [] },
  basic: { backtests_per_month: 100, ai_builds_per_month: 100, live_limit: 2, group_size: 25, deepdives_per_month: 15, decks_per_month: 5,
    stock_alerts: 25, screens: 10, holdings: 100,
    features: ["indicators", "group_live", "options", "alerts", "daily_report", "newsletter", "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "money_reminders", "positioning"] },
  pro: { backtests_per_month: null, ai_builds_per_month: null, live_limit: 10, group_size: 50, deepdives_per_month: null, decks_per_month: null,
    stock_alerts: 100, screens: 25, holdings: 300,
    features: ["indicators", "fno", "group_live", "options", "options_signal", "fast_entries", "alerts", "daily_report", "export", "newsletter",
      "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "tax_tools", "money_reminders", "positioning"] },
};

export const WHO: Record<PlanId, string> = { free: "Try every tool", basic: "For investors and part-time traders", pro: "For active traders and heavy research" };

const L = LIMITS;
// about 8 lines a card, built from the limits above so a card never says a different number; the full grid is on Plans
export const FEATURES: Record<PlanId, string[]> = {
  free: [`${L.free.backtests_per_month} backtests a month, each with a full verdict`, `${L.free.ai_builds_per_month} AI strategy builds a month`,
    "Paper trading free for 5 market days", `${L.free.deepdives_per_month} company deep dives and ${L.free.decks_per_month} slide deck a month`,
    "Screens, sector rotation, results calendar and red flags on every company",
    `${L.free.stock_alerts} stock alerts and ${L.free.screens} saved screens`,
    `Import up to ${L.free.holdings} holdings, a tax report, and a weekly My Stocks email`, "Every market we cover, and your own CSV"],
  basic: ["Everything in Free, plus:", `${L.basic.backtests_per_month} backtests and ${L.basic.ai_builds_per_month} AI builds a month`,
    "All 20+ indicators: MACD, Supertrend, Bollinger Bands, VWAP and more",
    `Paper trade ${L.basic.live_limit} strategies at a time, whole groups and options at set times`, "Trade notifications and a daily report after each close",
    `${L.basic.deepdives_per_month} company deep dives (report card and checklist) and ${L.basic.decks_per_month} decks a month`,
    "Stage 2 scan, watchlist red flags and Watchlist at a glance, with alerts",
    `${L.basic.stock_alerts} stock alerts, ${L.basic.screens} saved screens, ${L.basic.holdings} holdings`, "Daily Market Brief and My Stocks"],
  pro: ["Everything in Basic, plus:", "Unlimited backtests, AI builds, deep dives and decks", `Paper trade ${L.pro.live_limit} strategies at a time`,
    "Indian F&O and options entered on your own rules' signals", `Group tests of up to ${L.pro.group_size}, with faster entries and a spread limit`,
    "Export rules and trades", `${L.pro.stock_alerts} stock alerts, ${L.pro.screens} saved screens, ${L.pro.holdings} holdings`],
};

export const NUMBERS: [keyof Limits, string][] = [["backtests_per_month", "Backtests a month, each with a verdict"], ["ai_builds_per_month", "AI strategy builds a month"],
  ["live_limit", "Paper trading sessions at a time"], ["group_size", "Instruments in a group test"], ["deepdives_per_month", "Company deep dives a month"],
  ["decks_per_month", "Company slide decks a month"], ["stock_alerts", "Stock alerts on at a time"], ["screens", "Saved screens"], ["holdings", "Holdings kept"]];
export const FLAGS: [string, string][] = [["indicators", "All 20+ indicators"], ["group_live", "Paper trade a whole group"], ["options", "Options paper trading at set times"],
  ["alerts", "Trade notifications"], ["daily_report", "Daily report after the close"], ["newsletter", "Daily Market Brief and My Stocks"],
  ["scans", "Stage 2 + Supertrend scan, with a daily alert"], ["filings", "Red flags for the whole watchlist, with an evening alert"],
  ["investor_home", "Watchlist at a glance"], ["fno", "Indian F&O"], ["options_signal", "Options entered on your own rules' signals"],
  ["fast_entries", "Faster group entries and a spread limit"], ["export", "Export rules and trades"],
  ["networth", "Net worth: unlimited entries and the monthly history"],
  ["mf_gains", "Mutual funds: every scheme, and capital gains by year"],
  ["dividends", "Dividends by company, with TDS and US tax withheld"], ["tax_tools", "Advance tax amounts and long-term exemption facts per lot"],
  ["money_reminders", "Money calendar reminders by email or phone"],
  ["positioning", "Derivatives positioning history and IV percentiles"]];
export const EVERYONE = ["Every market, and your own CSV", "Screens (unlimited runs), sector rotation and the results calendar", "Red flags on every company page",
  "Corporate actions, deals and surveillance lists", "Derivatives positioning today: participant OI, FII/DII flows and PCR", "My Holdings and the tax report", "Money calendar and its calendar feed",
  "Weekly Market Brief and My Stocks",
  "Public company pages, share cards and invite links"];
