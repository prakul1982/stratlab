/* The one wording of a plan's count limit on the pages (DP2-022, DP1-018), the same as the server's (plans.limit_message):
 * what is used up and on which plan, when a monthly count starts again, then what the next plan gives. The plan note
 * (PlanNote) adds the price and the button after it. Pure, no React: the unit tests read it as it is. */
import { LIMITS, PLAN_IDS, PLAN_NAME, type Limits, type PlanId } from "./plans";

type CountKey = Exclude<keyof Limits, "features">;

/** The next plan up with a higher limit `key` (null counts as none), and that limit; null when no plan goes higher. */
export function nextPlan(plan: PlanId, key: CountKey): { id: "basic" | "pro"; name: string; cap: number | null } | null {
  const have = LIMITS[plan][key] as number | null;
  if (have == null) return null;
  for (const p of PLAN_IDS.slice(PLAN_IDS.indexOf(plan) + 1)) {
    const cap = LIMITS[p][key] as number | null;
    if (cap == null || cap > have) return { id: p as "basic" | "pro", name: PLAN_NAME[p], cap };
  }
  return null;
}

/** The day a monthly count starts again, in India's month as the server counts it: "1 Nov". */
export function resetDay(now = Date.now()): string {
  const ist = new Date(now + 5.5 * 3600_000);
  return new Date(Date.UTC(ist.getUTCFullYear(), ist.getUTCMonth() + 1, 1)).toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });
}

/** "<used>.[ The count starts again on 1 Nov.] Basic gives 25." (or "Pro has no limit on <what>."), and the plan it names, for
 * the note's price. `used` is the first sentence, without its full stop. */
export function limitLine(plan: PlanId, key: CountKey, used: string, what: string, monthly = false, now = Date.now()): { text: string; next: "basic" | "pro" | null } {
  const n = nextPlan(plan, key);
  const more = !n ? "" : n.cap == null ? ` ${n.name} has no limit on ${what}.` : ` ${n.name} gives ${n.cap}${monthly ? " a month" : ""}.`;
  return { text: `${used.replace(/\.$/, "")}.${monthly ? ` The count starts again on ${resetDay(now)}.` : ""}${more}`, next: n?.id ?? null };
}

/** The plan a person's limits are read from: the one their account runs on now (Pro during the launch offer). */
export const planIdOf = (p: string | null | undefined): PlanId => (p === "basic" || p === "pro" ? p : "free");

/** The page lock's sentence after its heading, in the one wording (DP2-012: "…: on the Pro plan. You're on Free; the rest of the
 * page is yours."): what the plan adds, and that everything else on the page is on the person's own plan. */
export function lockWords(what: string, plan: string, yours: string, whole: boolean): string {
  return whole ? `${what}. You're on ${yours}.` : `${plan} adds ${lowerFirst(what)}. Everything else here is on your ${yours} plan.`;
}

/** "Market breadth history" → "market breadth history"; a word in capitals stays as it is ("ITR-ready", "SIP test"). */
export const lowerFirst = (s: string) => (/^[A-Z][a-z]/.test(s) && !/^[A-Z][a-z]* [A-Z]{2,}/.test(s) ? s[0].toLowerCase() + s.slice(1) : s);
