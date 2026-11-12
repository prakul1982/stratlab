// Every plan's features in full, each a topic with its items (DK-003), built from the limits in plans.ts so no list says a different
// number. The cards show plans.ts KEY's five lines; these are the landing page's "Every feature, plan by plan" fold, loaded when it is
// opened (LIVE4-020), and backend/tests/test_plan_copy.py checks that each paid feature is named on the list of the plan that adds it.
import { AI_BUILDS_PER_DAY, LIMITS, type PlanId } from "./planCore";

const L = LIMITS;

/** Public share links a month (bet 3): a dated teaser of a deep dive or a theme at /r/<token>. The server's plans.py
 * share_links_per_month; backend/tests/test_plan_copy.py fails when these drift from it. null: no limit. Kept here, not in plans.ts
 * LIMITS, because plans.ts is in the landing page's first load (its JavaScript budget); the comparison table reads it from here. */
export const SHARE_LINKS: Record<PlanId, number | null> = { free: 1, basic: 30, pro: null };

export const FEATURES: Record<PlanId, string[]> = {
  free: [`${L.free.backtests_per_month} backtests a month, each with a full verdict, and ${L.free.ai_builds_per_month} AI strategy builds`,
    `Paper trading trial: ${L.free.live_limit} strategy on 1 stock for 5 market days from your first start, then Basic or Pro`,
    "Options builder with Greeks and breakevens after charges; on every company page, red flags and its latest 3 customer and supplier links",
    `Today's derivatives positioning, F&O contract changes, the top 5 market movers and the first 3 results of a filings search, and a journal of your last ${L.free.journal_trades} trades`,
    // a deep dive on Free has the report card and checklist too (DP1-021); FREE-TIER: no decks of its own, the sample deck instead; reads already written never count
    `${L.free.deepdives_per_month} company deep dive a month with the report card and checklist, ${L.free.ai_reads_per_day} fresh AI reads a day, and the sample deck to download; ${SHARE_LINKS.free} share link`,
    `Price charts, screens, every theme already mapped (and ${L.free.themes_per_month} new theme a month), the heatmap, sector rotation, today's market breadth and ETF prices against NAV`,
    `${L.free.stock_alerts} stock alerts and ${L.free.screens} saved screen; import up to ${L.free.holdings} holdings, ${L.free.mf_schemes} mutual funds and ${L.free.networth_items} net worth entries; Market Watch with ${L.free.watchlists} list of ${L.free.watchlist_symbols} symbols and drawings kept on ${L.free.chart_saves} charts`,
    // the same words as the table's row (DP2-010: "a weekly My Stocks email" here, "Weekly Market Brief and My Stocks" there)
    "Tax report on screen, money calendar, the Market Brief on News, the weekly Market Brief and My Stocks emails, every market we cover and your own CSV"],
  basic: ["Everything in Free, plus:",
    // "No ads" opens the first line, with the plan's amounts: a ninth line would break the card's six to eight short lines (DK-003)
    `No ads, ${L.basic.backtests_per_month} backtests and ${L.basic.ai_builds_per_month} AI builds a month; ${L.basic.stock_alerts} stock alerts, ${L.basic.screens} saved screens, ${L.basic.holdings} holdings, ${L.basic.watchlists} Market Watch lists of ${L.basic.watchlist_symbols} (watchlist import from a file), drawings kept on every chart`,
    `Paper trade ${L.basic.live_limit} strategies at a time, whole groups on intraday candles and options at set times, with trade notifications and a daily report`,
    "Trading tools: all 20+ indicators, full trade journal, positioning history, stock futures history, closing auction history, chart replay practice, an India VIX entry filter, SIP dip rules, the market movers in full",
    "Alerts: F&O change alerts, ETF gap alerts, IPO alerts and market event reminders and money reminders; the daily Market Brief and My Stocks by email; the earnings-call calendar in full",
    // f4: a theme's workbook counts as its deck of the month; the full change log ("What changed") is Basic (Free sees the latest refresh's summary)
    `${L.basic.deepdives_per_month} company deep dives, ${L.basic.decks_per_month} slide decks and ${L.basic.themes_per_month} new themes a month (a theme's workbook in Excel counts as its deck), ${SHARE_LINKS.basic} public share links, theme change logs and business group figures`,
    "Company pages: every peer and ten years of statements and shareholding, customers and suppliers named in filings, business updates in numbers, named-holder search, IPO offer document summaries and search inside filings and call transcripts",
    "Scans and watchlist: the Stage 2 scan and every other trend scan, watchlist red flags (and each holding's filings and results date), Watchlist at a glance, market breadth charts, margin funding history",
    "Money: tax report downloads, every mutual fund and net worth entry, fund capital gains, fund costs in rupees, fund behaviour, dividends with TDS, deposit rates after your own tax, a floating-rate loan check"],
  pro: ["Everything in Basic, plus:", `Unlimited backtests, deep dives and decks, with unlimited share links; up to ${AI_BUILDS_PER_DAY} AI builds a day; filings search over every year of a company's filings, with the results as a CSV`,
    `Paper trade ${L.pro.live_limit} strategies at a time; group tests of up to ${L.pro.group_size}, with faster entries and a spread limit`,
    "Indian F&O contracts (futures and options on stocks and indices) in notebooks, each backtested on its own past prices; the stocks themselves are on every plan",
    "Options paper trading on your own rules' signals, strikes picked by delta or premium, and what-if sliders with a roll preview",
    "Export a notebook's rules and trades, a company's statements to Excel, forward-test alert webhooks in paper trading, and StratLab in your AI assistant; links across a theme's companies, with CSV",
    "Advance tax amounts and the long-term exemption lot by lot",
    "US stocks in Indian tax sale by sale, and ITR-ready schedules with a PDF pack for your CA",
    `${L.pro.stock_alerts} stock alerts, ${L.pro.screens} saved screens, ${L.pro.holdings} holdings, unlimited Market Watch lists and indicators`],
};

// what every plan has (the comparison table's "On every plan" fold); here, not in plans.ts, so the landing page doesn't load it
export const EVERYONE = ["Every market, and your own CSV",
  "Price charts: candles, Heikin-Ashi or bars, indicators, drawings kept on your account, and compare",
  "Market Watch on every page: lists across every market we cover, live prices, and charts from 1 minute to 1 month with drawings",
  "Options builder: charges to open and close, breakevens and the most it can make or lose after them", "Screens (unlimited runs), sector rotation and the results calendar",
  "Every theme already mapped", "Red flags on every company page",
  "Corporate actions, deals and surveillance lists", "Today's market breadth numbers", "Derivatives positioning today: participant OI, FII/DII flows, PCR and the option chain facts",
  "F&O contract changes: stocks entering and leaving F&O, lot sizes and expiry days",
  "Closing auction, live: each F&O stock's reference and indicative price, the indices and the expiry settlement",
  "Market events calendar: RBI policy, data releases, the Fed, index changes, expiries and holidays",
  "Option Greeks for every strike and your position, and the payoff today beside the one at expiry (model estimates)",
  "A trade journal with the basic stats", "My Holdings, the tax report on screen and the year's total tax estimate", "Money calendar and its calendar feed",
  // what Free sees on these pages, in the words the pages use (DP2-010: Holdings' dividends, US tax's year totals, the ITR preview)
  "Each holding's dividends on My Holdings; the year's dividend total, and each year's US share gains in rupees, on Tax tools and US stocks tax",
  "Advance tax due dates and the exemption used", "A preview of the ITR-ready export: each schedule's totals and line counts",
  "Weekly Market Brief and My Stocks emails", "Public company pages, share cards and invite links", "ETF prices against their NAV, with 30 days of history",
  "Named holders above 1% and the business-update filings on every company page",
  "Stock futures today: OI buildup, rollover, basis and MWPL use for every F&O stock", "Stock lending fees that traded for your holdings",
  "Margin-funded positions per stock today, and your own MTF cost worked out",
  "IPOs in India and the US: dates, price bands, lot sizes, the bids by category while an issue is open, the offer documents' key facts, and listings against the issue price",
  "This week's earnings calls and analyst meets, each with its notice and webcast or dial-in link",
  "Business group pages: each group's listed companies, their market value and the day's change"];

/** Paid features added after plans.ts's lists were held for the landing page's JavaScript budget (f4): [flag, its row in the comparison
 * table, the cheapest plan that has it]; every plan above has it too. plans.py says the same, and backend/tests/test_plan_copy.py reads
 * these with plans.ts's LIMITS and FLAGS. */
export const MORE_FLAGS: [string, string, PlanId][] = [
  ["theme_changes", "A theme's full change log: companies added, removed and moved between layers, layers renamed, split or merged, figures restated (Free: the latest refresh's summary)", "basic"],
  ["theme_workbook", "A theme as an Excel workbook: every table of its page and deck, with sources and method (counts as the theme's deck of the month), and its companies as a CSV", "basic"],
];

const RANK: Record<PlanId, number> = { free: 0, basic: 1, pro: 2 };
/** Whether a plan has one of MORE_FLAGS. */
export const hasMore = (plan: PlanId, flag: string) => MORE_FLAGS.some(([f, , p]) => f === flag && RANK[plan] >= RANK[p]);
