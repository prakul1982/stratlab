// Every plan's features in full, each a topic with its items (DK-003), built from the limits in plans.ts so no list says a different
// number. The cards show plans.ts KEY's five lines; these are the landing page's "Every feature, plan by plan" fold, loaded when it is
// opened (LIVE4-020), and backend/tests/test_plan_copy.py checks that each paid feature is named on the list of the plan that adds it.
import { AI_BUILDS_PER_DAY, LIMITS, type PlanId } from "./plans";

const L = LIMITS;

export const FEATURES: Record<PlanId, string[]> = {
  free: [`${L.free.backtests_per_month} backtests a month, each with a full verdict, and ${L.free.ai_builds_per_month} AI strategy builds`,
    `Paper trading trial: ${L.free.live_limit} strategy on 1 stock for 5 market days from your first start, then Basic or Pro`,
    "Options builder with Greeks and breakevens after charges",
    `Today's derivatives positioning and F&O contract changes, and a journal of your last ${L.free.journal_trades} trades`,
    // a deep dive on Free has the report card and checklist too (DP1-021); a company's PDF and PowerPoint are one deck (DP1-026); a theme's deck counts the same (EXPORT)
    `${L.free.deepdives_per_month} company deep dives a month, each with the report card and checklist, and ${L.free.decks_per_month} slide deck of a company or a theme (its PDF and PowerPoint count as one)`,
    "Price charts, screens, themes, the heatmap, sector rotation, today's market breadth, ETF prices against NAV and red flags on every company, with its latest 3 customer and supplier links",
    `${L.free.stock_alerts} stock alerts and ${L.free.screens} saved screens; import up to ${L.free.holdings} holdings, ${L.free.mf_schemes} mutual funds and ${L.free.networth_items} net worth entries; Market Watch with ${L.free.watchlists} list of ${L.free.watchlist_symbols} symbols and drawings kept on ${L.free.chart_saves} charts`,
    // the same words as the table's row (DP2-010: "a weekly My Stocks email" here, "Weekly Market Brief and My Stocks" there)
    "Tax report, money calendar, the Market Brief on News, the weekly Market Brief and My Stocks emails, every market we cover and your own CSV"],
  basic: ["Everything in Free, plus:",
    // "No ads" opens the first line: a ninth line would break the card's six to eight (DK-003)
    `No ads, ${L.basic.backtests_per_month} backtests and ${L.basic.ai_builds_per_month} AI builds a month, with all 20+ indicators: MACD, Supertrend, VWAP and more`,
    `Paper trade ${L.basic.live_limit} strategies at a time, whole groups on intraday candles and options at set times, with trade notifications and a daily report`,
    "Trading tools: full trade journal, positioning history, stock futures history, closing auction history, chart replay practice, an India VIX entry filter, SIP dip rules",
    "Alerts: F&O change alerts, ETF gap alerts, IPO alerts and market event reminders and money reminders; the daily Market Brief and My Stocks by email",
    `${L.basic.deepdives_per_month} company deep dives and ${L.basic.decks_per_month} slide decks of companies or themes a month, business updates in numbers, named-holder search, customers and suppliers named in filings and IPO offer document summaries`,
    "Scans and watchlist: the Stage 2 scan and every other trend scan, watchlist red flags (and each holding's filings and results date), Watchlist at a glance, market breadth charts, margin funding history",
    "Money: every mutual fund and net worth entry, fund capital gains, fund costs in rupees, fund behaviour, dividends with TDS, deposit rates after your own tax, a floating-rate loan check",
    `${L.basic.stock_alerts} stock alerts, ${L.basic.screens} saved screens, ${L.basic.holdings} holdings, ${L.basic.watchlists} Market Watch lists of ${L.basic.watchlist_symbols}, drawings kept on every chart`],
  pro: ["Everything in Basic, plus:", `Unlimited backtests, deep dives and decks; up to ${AI_BUILDS_PER_DAY} AI builds a day`,
    `Paper trade ${L.pro.live_limit} strategies at a time; group tests of up to ${L.pro.group_size}, with faster entries and a spread limit`,
    "Indian F&O contracts (futures and options on stocks and indices) in notebooks, each backtested on its own past prices; the stocks themselves are on every plan",
    "Options paper trading on your own rules' signals, strikes picked by delta or premium, and what-if sliders with a roll preview",
    "Export a notebook's rules and trades, forward-test alert webhooks in paper trading, and StratLab in your AI assistant; links across a theme's companies, with CSV",
    "Advance tax amounts and the long-term exemption lot by lot",
    "US stocks in Indian tax sale by sale, and ITR-ready schedules with a PDF pack for your CA",
    `${L.pro.stock_alerts} stock alerts, ${L.pro.screens} saved screens, ${L.pro.holdings} holdings, unlimited Market Watch lists and indicators`],
};
