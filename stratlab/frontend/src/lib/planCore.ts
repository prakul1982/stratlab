/* The plans as the plan cards show them: names, prices, limits (with each plan's feature ids) and the cards' five lines (KEY).
 * The landing page downloads only this file; the comparison table's rows (FLAGS, NUMBERS, EVERYONE, ...) are in plans.ts, which
 * re-exports everything here, so the landing page's JavaScript stays under its budget however many plan rows are added (Release 43).
 * The server's plans.py is the source of truth: tests/test_plan_copy.py fails when these numbers drift from it, and
 * the same amounts must be set on the Razorpay plans. */

export type PlanId = "free" | "basic" | "pro";
export const PLAN_IDS: PlanId[] = ["free", "basic", "pro"];
export const PLAN_NAME: Record<PlanId, string> = { free: "Free", basic: "Basic", pro: "Pro" };

/** Rupee prices including GST: [a month, a year]. */
export const PRICE: Record<PlanId, [number, number]> = { free: [0, 0], basic: [699, 6999], pro: [1999, 19999] };

export type Limits = { backtests_per_month: number | null; ai_builds_per_month: number | null; live_limit: number; group_size: number;
  deepdives_per_month: number | null; decks_per_month: number | null; stock_alerts: number; screens: number; holdings: number;
  /** FREE-TIER: NEW themes mapped a month (every theme already in the library opens on every plan). null: no limit. */
  themes_per_month: number | null;
  networth_items: number | null; mf_schemes: number | null; journal_trades: number | null;
  /** Market Watch (MW-1): lists, symbols in one list, charts whose drawings are kept, indicators on one chart. null: no limit. */
  watchlists: number | null; watchlist_symbols: number | null; chart_saves: number | null; chart_indicators: number | null;
  /** Fresh AI reads a day (plans.ai_reads_per_day): a company's read already written today and the market mood never count. */
  ai_reads_per_day: number | null; features: string[] };

export const LIMITS: Record<PlanId, Limits> = {
  free: { backtests_per_month: 5, ai_builds_per_month: 5, live_limit: 1, group_size: 5, deepdives_per_month: 1, decks_per_month: 0,
    stock_alerts: 3, screens: 1, holdings: 30, networth_items: 5, mf_schemes: 5, journal_trades: 50, themes_per_month: 1,
    watchlists: 1, watchlist_symbols: 20, chart_saves: 3, chart_indicators: 3, ai_reads_per_day: 5, features: [] },
  basic: { backtests_per_month: 100, ai_builds_per_month: 100, live_limit: 2, group_size: 25, deepdives_per_month: 15, decks_per_month: 5,
    stock_alerts: 25, screens: 10, holdings: 100, networth_items: null, mf_schemes: null, journal_trades: null, themes_per_month: 10,
    watchlists: 10, watchlist_symbols: 100, chart_saves: null, chart_indicators: 10, ai_reads_per_day: 60,
    features: ["indicators", "group_live", "options", "alerts", "daily_report", "newsletter", "scans", "filings", "investor_home", "networth", "mf_gains", "dividends", "money_reminders", "breadth", "positioning", "journal", "mf_costs", "etf_gaps", "fo_alerts", "cas_history", "vix_filter",
      "chart_replay",
      "event_reminders",
      "biz_updates", "holders",
      "stock_futures", "mtf",
      "mf_behaviour", "sip_luck", "rates_slab", "loan_check",
      "ipo_summary", "ipo_alerts", "movers",
      "earnings_calls", "group_figures",
      "doc_search",
      "tables",
      "watchlist_import", "tax_export"] },
  pro: { backtests_per_month: null, ai_builds_per_month: null, live_limit: 10, group_size: 50, deepdives_per_month: null, decks_per_month: null,
    stock_alerts: 100, screens: 25, holdings: 300, networth_items: null, mf_schemes: null, journal_trades: null, themes_per_month: null,
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
      "ipo_summary", "ipo_alerts", "movers",
      "earnings_calls", "group_figures",
      "doc_search", "doc_search_all",
      "tables",
      "watchlist_import", "tax_export"] },
};

// Free has every market and the core tools, not every tool: Replay, Forward test, the scans and the full journal are paid (DP1-021)
export const WHO: Record<PlanId, string> = { free: "Every market and the core tools, free", basic: "For investors and part-time traders", pro: "For active traders and heavy research" };

const L = LIMITS;
/** The daily safety cap on Pro's unlimited AI builds (the server's AI_BUILDS_PER_DAY). */
export const AI_BUILDS_PER_DAY = 200;

/** R11 (owner, 5 Nov: the Plans page was "bad UI"); LIVE4-020: every plan card, on the Plans page and the landing page alike, shows five short lines, the plan's main points, and the full
 * comparison is the table under the cards (PlanCompare): the cards are level, short, and say no number the table doesn't. Built from LIMITS. */
export const KEY: Record<PlanId, string[]> = {
  free: ["Every market, price charts, screens and the options builder",
    `${L.free.backtests_per_month} backtests and ${L.free.ai_builds_per_month} AI strategy builds a month`,
    `Paper trading trial: ${L.free.live_limit} strategy for 5 market days`,
    `${L.free.deepdives_per_month} company deep dive a month, ${L.free.ai_reads_per_day} fresh AI reads a day`,
    `${L.free.stock_alerts} stock alerts, ${L.free.screens} saved screen, ${L.free.holdings} holdings`],
  basic: ["Everything in Free, with no ads",
    `${L.basic.backtests_per_month} backtests and ${L.basic.ai_builds_per_month} AI builds a month, all 20+ indicators`,
    `Paper trade ${L.basic.live_limit} strategies at a time, with options and whole groups`,
    "Full trade journal, alerts and the daily Market Brief by email",
    `${L.basic.deepdives_per_month} deep dives and ${L.basic.decks_per_month} slide decks a month`],
  pro: ["Everything in Basic",
    `Unlimited backtests, deep dives and decks; up to ${AI_BUILDS_PER_DAY} AI builds a day`,
    `Paper trade ${L.pro.live_limit} strategies at a time, groups of up to ${L.pro.group_size}`,
    "Indian F&O in notebooks, and options on your own rules' signals",
    // LIVE7B-026: Basic has Tax tools' dividends; what Pro adds there is the advance tax and the long-term exemption
    "Advance tax, long-term exemption, ITR export, StratLab in your AI app"],
};
