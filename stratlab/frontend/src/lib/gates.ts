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
  "/invest/business-updates": { feature: "biz_updates", whole: false },
  "/invest/holders": { feature: "holders", whole: false },
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

/** Paid features that live inside other pages, not a page of their own (where to find them, for the test's sake). */
export const ELSEWHERE: Record<string, string> = {
  indicators: "the rules editor", fno: "Indian F&O instruments", group_live: "paper trading a group", options_signal: "the options builder",
  fast_entries: "group paper trading", alerts: "Settings", daily_report: "Settings", export: "a notebook's More menu",
  newsletter: "Settings", dividends: "Holdings", mf_costs: "Mutual funds", mf_behaviour: "Mutual funds", options_whatif: "the options builder",
  vix_filter: "the options builder", strike_rules: "the options builder", loan_check: "Net worth",
  assistant: "Connect an AI assistant (its own plan note)",
};

export const featureName = (feature: string) => FLAGS.find(([f]) => f === feature)?.[1] ?? feature;

/** The gate for a page address, or null. */
export function gateFor(path: string): Gate | null {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  return PAGE_GATES[p] ?? (p.startsWith("/trade/signals/") ? PAGE_GATES["/trade/signals"] : null);
}

/** The plan a gate needs ("basic" or "pro"). */
export const gatePlan = (g: Gate): PlanId => planOf(g.feature);
