// The Plans page cards' five lines (R11), apart from lib/plans.ts: the landing page loads plans.ts, and these lines are only drawn on
// /plans (R5V-020: the landing page's JavaScript stays under 450 KB).
import { AI_BUILDS_PER_DAY, LIMITS, type PlanId } from "./plans";

const L = LIMITS;

/** R11 (owner, 5 Nov: the Plans page was "bad UI"): each card on the Plans page shows five short lines, the plan's main points, and the full
 * comparison is the table under the cards (PlanCompare): the cards are level, short, and say no number the table doesn't. Built from LIMITS. */
export const KEY: Record<PlanId, string[]> = {
  free: ["Every market, price charts, screens and the options builder",
    `${L.free.backtests_per_month} backtests and ${L.free.ai_builds_per_month} AI strategy builds a month`,
    `Paper trading trial: ${L.free.live_limit} strategy for 5 market days`,
    `${L.free.deepdives_per_month} company deep dives and ${L.free.decks_per_month} slide deck a month`,
    `${L.free.stock_alerts} stock alerts, ${L.free.screens} saved screens, ${L.free.holdings} holdings`],
  basic: ["Everything in Free, with no ads",
    `${L.basic.backtests_per_month} backtests and ${L.basic.ai_builds_per_month} AI builds a month, all 20+ indicators`,
    `Paper trade ${L.basic.live_limit} strategies at a time, with options and whole groups`,
    "Full trade journal, alerts and the daily Market Brief by email",
    `${L.basic.deepdives_per_month} deep dives and ${L.basic.decks_per_month} slide decks a month`],
  pro: ["Everything in Basic",
    `Unlimited backtests, deep dives and decks; up to ${AI_BUILDS_PER_DAY} AI builds a day`,
    `Paper trade ${L.pro.live_limit} strategies at a time, groups of up to ${L.pro.group_size}`,
    "Indian F&O in notebooks, and options on your own rules' signals",
    "Tax tools, ITR-ready export and StratLab in your AI assistant"],
};
