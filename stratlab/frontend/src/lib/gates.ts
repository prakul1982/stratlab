/* Which page holds which paid feature, so a locked page says so at the top and the menu shows a lock. The server
 * enforces every one of these (plans.allows); this only words it. `whole`: the page is the paid feature (Trend scan);
 * otherwise part of the page is for everyone and the paid part is named (Market breadth: today's numbers for
 * everyone, the history on Basic). unit/gates.test.mjs checks every paid feature in plans.ts has a page here or an
 * entry in ELSEWHERE. */
import { FLAGS, planOf, type PlanId } from "./plans";

export type Gate = { feature: string; whole: boolean };

export const PAGE_GATES: Record<string, Gate> = {
  "/trade/signals": { feature: "signal_webhooks", whole: true },
  "/trade/replay": { feature: "chart_replay", whole: true },
  "/research/scan": { feature: "scans", whole: true },
  "/research/investor": { feature: "investor_home", whole: true },
  "/research/filings": { feature: "filings", whole: true },
  "/invest/breadth": { feature: "breadth", whole: false },
  "/trade/positioning": { feature: "positioning", whole: false },
  "/trade/positioning/stocks": { feature: "stock_futures", whole: false },
  "/trade/journal": { feature: "journal", whole: false },
  "/trade/closing-auction": { feature: "cas_history", whole: false },
  "/trade/fo-changes": { feature: "fo_alerts", whole: false },
  "/trade/events": { feature: "event_reminders", whole: false },
  "/invest/etf-gaps": { feature: "etf_gaps", whole: false },
  "/invest/margin-funding": { feature: "mtf", whole: false },
  "/invest/ipos": { feature: "ipo_alerts", whole: false },
  // on Free these pages hold nothing else (each company's own updates and holders are on its company page), so the menu
  // marks them locked like the scan (DP1-019: no badge, then a page blank under its banner)
  "/invest/business-updates": { feature: "biz_updates", whole: true },
  "/invest/holders": { feature: "holders", whole: true },
  "/money/net-worth": { feature: "networth", whole: false },
  "/money/mutual-funds": { feature: "mf_gains", whole: false },
  "/money/tax-tools": { feature: "tax_tools", whole: false },
  "/money/us-tax": { feature: "us_tax", whole: false },
  "/money/itr": { feature: "itr_export", whole: false },
  "/money/sip-test": { feature: "sip_luck", whole: false },
  "/money/rates": { feature: "rates_slab", whole: false },
  "/money/calendar": { feature: "money_reminders", whole: false },
  "/options": { feature: "options", whole: false },
};

/** The paid part of a page that is free in the main, in a few words for its card's tag: "Pro for advance tax" (LIVE1B-022: "Pro for
 * part" did not say which part). */
export const PART_WORDS: Record<string, string> = {
  tax_tools: "advance tax", us_tax: "rupee workings", itr_export: "the downloads", networth: "history", mf_gains: "gains by year", journal: "the checks",
};

/** An IPO's own page holds the summary of its offer document (Basic); the rest of the page is for everyone. */
export const IPO_PAGE_GATE: Gate = { feature: "ipo_summary", whole: false };

/** Paid features that live inside other pages, not a page of their own (where to find them, for the test's sake). */
export const ELSEWHERE: Record<string, string> = {
  indicators: "the rules editor", fno: "Indian F&O instruments", group_live: "paper trading a group", options_signal: "the options builder",
  fast_entries: "group paper trading", alerts: "Settings", daily_report: "Settings", export: "a notebook's More menu",
  newsletter: "Settings", dividends: "Tax tools (by company)", mf_costs: "Mutual funds", mf_behaviour: "Mutual funds", options_whatif: "the options builder",
  vix_filter: "the options builder", strike_rules: "the options builder", loan_check: "Net worth",
  assistant: "Connect an AI assistant (its own plan note)", ipo_summary: "an IPO's own page (its gate is below)",
};

export const featureName = (feature: string) => FLAGS.find(([f]) => f === feature)?.[1] ?? feature;

/** The gate for a page address, or null. */
export function gateFor(path: string): Gate | null {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  if (p.startsWith("/invest/ipos/")) return IPO_PAGE_GATE;
  return PAGE_GATES[p] ?? (p.startsWith("/trade/signals/") ? PAGE_GATES["/trade/signals"] : null);
}

/** The plan a gate needs ("basic" or "pro"). */
export const gatePlan = (g: Gate): PlanId => planOf(g.feature);
