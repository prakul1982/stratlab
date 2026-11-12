/* What each plan includes, for visitors who aren't signed in (the landing page) and until /me arrives (Plans).
 * The server's plans.py is the source of truth: tests/test_plan_copy.py fails when these numbers drift from it, and
 * the same amounts must be set on the Razorpay plans. */

// The cards' part (names, prices, LIMITS, WHO, KEY) is in planCore.ts, the only plan file the landing page downloads; this file adds
// the comparison table's rows and is loaded by the app, the Plans page and the landing page's comparison fold.
export * from "./planCore";
import { AI_BUILDS_PER_DAY, LIMITS, type Limits, type PlanId } from "./planCore";

/** The comparison table's cell for a limit that has none: Pro's AI builds still have a daily safety cap. */
export const unlimitedLabel = (p: PlanId, k: keyof Limits) => (p === "pro" && k === "ai_builds_per_month" ? `Unlimited (up to ${AI_BUILDS_PER_DAY} a day)` : "Unlimited");

// LIVE4-020: every plan's features in full are in planFeatures.ts (FEATURES), loaded only when someone opens "Every feature, plan by
// plan" on the landing page, so its JavaScript stays under 450 KB (R5V-020)


/** Ads (ADS-1), one row of the comparison table: Free accounts and signed-out pages may show Google ads, only after the visitor allows
 * them (lib/ads.ts); Basic and Pro never do. The cards say it once, on the plan that adds it (Basic; Pro includes Basic). */
export const ADS: Record<PlanId, string> = { free: "After you allow them", basic: "None", pro: "None" };

export const NUMBERS: [keyof Limits, string][] = [["backtests_per_month", "Backtests a month, each with a verdict"], ["ai_builds_per_month", "AI strategy builds a month"],
  ["live_limit", "Paper trading sessions at a time"], ["group_size", "Instruments in a group test"], ["deepdives_per_month", "Company deep dives a month"],
  ["decks_per_month", "Slide decks a month, of a company or a theme (its PDF and PowerPoint are one deck)"], ["themes_per_month", "New themes mapped a month"], ["stock_alerts", "Stock alerts on at a time"], ["screens", "Saved screens"], ["holdings", "Holdings kept"],
  ["mf_schemes", "Mutual fund schemes kept"], ["networth_items", "Net worth entries"], ["journal_trades", "Trades the journal keeps"],
  ["watchlists", "Market Watch lists (the first is your Research watchlist)"], ["watchlist_symbols", "Symbols in one Market Watch list"],
  ["chart_saves", "Charts that keep your drawings and indicators"], ["chart_indicators", "Indicators on one chart"],
  ["ai_reads_per_day", "Fresh AI reads a day, refreshes included (Free has no refreshes; reads already written, and the market mood, never count)"]];
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
  ["positioning", "Positioning and FII/DII flow history, IV percentiles"],
  ["journal", "Trade journal: every trade, the honesty checks, breakdowns and paper vs real"],
  ["tax_export", "Tax report downloads: CSV and PDF"], ["itr_export", "ITR-ready schedules and a PDF pack for your CA"], ["us_tax", "US stocks in Indian tax sale by sale: each sale's gain in rupees, the foreign tax credit and Schedule FA"],
  ["etf_gaps", "Alerts on an ETF's price against its NAV"],

["fo_alerts", "Alerts when an F&O exit, lot size or expiry change touches your watchlist or paper sessions"],
  ["options_whatif", "Options what-if: move the underlying, shift IV and pass days, and preview rolling a leg"],
  ["cas_history", "Closing auction history: up to 60 days of auction closes against the reference price, and index closes"],
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
  ["ipo_alerts", "IPO alerts: when an issue opens, closes, is allotted or lists"],
  ["movers", "Market movers in full: every row, any index, a smallest market value and CSV"],
  ["earnings_calls", "Earnings-call calendar in full: every week ahead, calls already held with their transcript, recording and presentation links, filters and your stocks' calls in the calendar feed"],
  ["group_figures", "Business group figures: each member's 1-month and 1-year change, promoter holding and the members' heatmap"],
  // the filings search (doc_search.py): Free sees the first 3 results of a search, filtered by company only (plans.DOC_SEARCH)
  ["doc_search", "Search filings: all results"], ["doc_search_all", "Search filings: all years, CSV"],
  ["tables", "All company tables"],
  ["watchlist_import", "Watchlist import from a CSV or Excel file"]];
// EVERYONE (what every plan has, the comparison table's last fold) is in planFeatures.ts: only the lazy table reads it, so the landing
// page's JavaScript doesn't carry it (FREE-TIER kept that page's budget)

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
  us_tax: "money", tax_export: "money", mf_behaviour: "money", sip_luck: "money", rates_slab: "money", loan_check: "money",
};
