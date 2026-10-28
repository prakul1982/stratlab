import { dateOnly, fmtDate, IST } from "./format";
import type { Me } from "./types";

/* Account's words for how someone signed in and how their plan runs. No React here, so the unit tests read it as it is. */

const METHODS: Record<string, string> = { google: "Google", email: "Email link", github: "GitHub", apple: "Apple", azure: "Microsoft", phone: "Phone" };

/** "Google", "Email link"…: from the session, else from what the server's sign-in check saw. null when neither knows,
 * so the page leaves the line out instead of showing a dash. */
export function signedInWith(session: string | null | undefined, server: string | null | undefined): string | null {
  const m = (session || server || "").trim();
  if (!m) return null;
  return METHODS[m.toLowerCase()] ?? m.charAt(0).toUpperCase() + m.slice(1);
}

/** How the paid plan runs, as Account shows it:
 * - "given": the site owner gave it by hand; it has an end date or none, and there is nothing to renew or cancel;
 * - "cancelled": a subscription that ends at the period's end;
 * - "renews": a subscription that renews;
 * - "viewing": the owner's "View as": the plan is only a preview, so nothing is billed, changed or cancelled;
 * - "free": no paid plan. */
export type PlanRun = "given" | "cancelled" | "renews" | "viewing" | "free";

export function planRun(me: Pick<Me, "plan" | "paid_plan" | "billing" | "view_as">): PlanRun {
  const paid = me.paid_plan ?? me.plan;
  if (paid === "free") return "free";
  if (me.view_as) return "viewing";
  if (me.billing.given_by_owner) return "given";
  return me.billing.cancel_at_period_end ? "cancelled" : "renews";
}

const PLAN_LABEL: Record<string, string> = { free: "Free", basic: "Basic", pro: "Pro" };

/** The plan they have (from `paid_plan`), not the launch offer's Pro that `plan` and `plan_info` show for everyone then. */
export function planLabel(me: Pick<Me, "plan" | "paid_plan" | "plan_info"> & Partial<Pick<Me, "promo" | "free_basic_until">>): string {
  // Basic earned through invites is the plan they have, though nothing is paid (paid_plan is "free" then)
  if (me.free_basic_until && !me.promo) return PLAN_LABEL.basic ?? "Basic";
  return PLAN_LABEL[me.paid_plan ?? me.plan] ?? me.plan_info.name;
}

/** The typed confirmation before data is deleted: the text matches, ignoring case and spaces around it. Never matches an
 * empty word. */
export function confirmMatches(typed: string, word: string): boolean {
  const want = word.trim().toLowerCase();
  return !!want && typed.trim().toLowerCase() === want;
}

/** A monthly count against its limit: "3 of 10"; "0 (unlimited)"; or, when the plan has a limit that early access or
 * the launch offer lifts for now, "0 (unlimited during early access; Free has 2 a month)", so Account and the Plans
 * page never disagree. */
export function monthlyUse(used: number, limit: number | null | undefined, planLimit?: number | null, lifted?: string | null, plan?: string): string {
  if (limit != null) return countOf(used, limit);
  if (planLimit != null && lifted) return `${used} (unlimited during ${lifted}; ${plan ?? "your plan"} has ${planLimit} a month)`;
  return `${used} (unlimited)`;
}

/** "2 of 2 (limit reached)" once the count is at the limit. A count past it (the owner's own use, viewed as a smaller plan)
 * never reads "8 of 2" (R17-004, R22-001), and still gives the real count: "2 of 2 (limit reached; 8 used)" (R48-013).
 * The one form Account and the deep dive both use. */
export function countOf(used: number, limit: number): string {
  if (used > limit) return `${limit} of ${limit} (limit reached; ${used} used)`;
  return used === limit ? `${limit} of ${limit} (limit reached)` : `${used} of ${limit}`;
}

/** The deep dive's line under its buttons: "Companies opened this month: 2 of 2 (limit reached). Decks: 1 of 1 (limit
 * reached). Opening a company again this month doesn't count." (R22-002). A deck is a company's: its PDF and its PowerPoint
 * count as one, so the line says so (DP1-026). */
export function deepDiveLimitLine(deepdiveUsed: number, deepdiveLimit: number, deckUsed: number, deckLimit: number | null | undefined): string {
  return `Companies opened this month: ${countOf(deepdiveUsed, deepdiveLimit)}.${deckLimit != null ? ` Decks: ${countOf(deckUsed, deckLimit)}; a company's PDF and PowerPoint are one deck.` : ""} Opening a company again this month doesn't count.`;
}

/** AI builds this month: "5 of 100", or on a plan with no monthly limit "5 (unlimited; up to 200 a day)", the daily safety cap
 * the Plans card names (R9P-005); for an admin the cap isn't enforced, and the line says so. */
export function aiBuildsUse(used: number, limit: number | null | undefined, perDay?: number | null, admin?: boolean): string {
  if (limit != null || perDay == null) return monthlyUse(used, limit);
  return `${used} (unlimited; up to ${perDay.toLocaleString("en-IN")} a day${admin ? ", not enforced for you" : ""})`;
}

/** The plan's row in "Plan and usage", or null for Free. */
export function planRow(me: Pick<Me, "plan" | "paid_plan" | "billing" | "view_as">): [string, string] | null {
  const run = planRun(me), end = me.billing.renews_or_ends;
  if (run === "free" || run === "viewing") return null;
  if (run === "given") return ["Given by StratLab", end ? `Until ${dateOnly(end)}` : "No end date"];
  if (!end) return null;
  return [run === "cancelled" ? "Ends on" : "Renews on", dateOnly(end)];
}

/** Free after its 5-market-day trial: the server stops a Free person's paper sessions within a minute, and a new one
 * is refused. Only the owner's "View as Free" can still show one running, because the server keeps the real plan's
 * sessions; the pages say that instead of "running" beside "trial ended" (R33-003). */
export function viewedFreeKeepsSessions(me: Pick<Me, "plan" | "view_as" | "trial" | "live_running">): boolean {
  return me.view_as === "free" && !!me.trial?.started && !me.trial.active && me.live_running > 0;
}

/** Account's "Paper sessions running" value. */
export function sessionsRunning(me: Pick<Me, "plan" | "view_as" | "trial" | "live_running" | "live_limit">): string {
  const n = `${me.live_running} of ${me.live_limit}`;
  return viewedFreeKeepsSessions(me) ? `${n} (kept running: you're viewing as Free; a real Free plan stops them when the trial ends)` : n;
}

/** One kept-count limit as /me/limits gives it (DP2-031: Account showed the monthly counts only). */
export type KeptLimit = { key: string; used: number | null; limit: number | null; next: string | null };
const KEPT_LABEL: Record<string, string> = { stock_alerts: "Stock alerts on", screens: "Saved screens", holdings: "Holdings kept",
  mf_schemes: "Mutual fund schemes kept", networth_items: "Net worth entries", journal_trades: "Trades the journal counts" };

/** Account's row for a kept-count limit: "3 of 5", "12 (no limit)", and the journal's "The last 50" / "Every trade". */
export function keptRow(r: KeptLimit): [string, string] | null {
  const label = KEPT_LABEL[r.key];
  if (!label) return null;
  if (r.key === "journal_trades") return [label, r.limit == null ? "Every trade" : `The last ${r.limit}`];
  if (r.used == null) return [label, r.limit == null ? "No limit" : `Up to ${r.limit}`];
  return [label, r.limit == null ? `${r.used} (no limit)` : countOf(r.used, r.limit)];
}

/** Account's paper trading row on Free, with the trial: "0 of 1 · trial: 5 market days from your first start", "… · trial: 3
 * market days left, until 30 Oct", "… · trial ended on 30 Oct" (DP2-031: no trial and no days left were said). */
export function trialUse(me: Pick<Me, "plan" | "view_as" | "trial" | "live_running" | "live_limit">): string {
  const base = sessionsRunning(me), t = me.trial;
  if (!t) return base;
  const days = t.days ?? 5;
  if (!t.started) return `${base} · trial: ${days} market days from your first start`;
  // the trial ends at midnight India time after its last day: the day named is that last day, in India's calendar
  const end = t.ends_at ? fmtDate(new Date(new Date(t.ends_at).getTime() - 1000), { tz: IST, year: false }) : null;
  if (!t.active) return `${base} · trial ended${end ? ` on ${end}` : ""}`;
  const left = t.days_left;
  return `${base} · trial: ${left != null ? `${left} market day${left === 1 ? "" : "s"} left` : "running"}${end ? `, until ${end}` : ""}`;
}

/** Which rows of the two-column usage list take a whole line: the long ones, and any row that would otherwise stand alone beside an empty cell. */
export function usageSpans(long: boolean[]): boolean[] {
  const out = [...long];
  let col = 0;
  out.forEach((w, i) => {
    if (w) { if (col === 1) out[i - 1] = true; col = 0; } else col = (col + 1) % 2;
  });
  if (col === 1) out[out.length - 1] = true;
  return out;
}
