import { dateOnly } from "./format";
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
 * - "free": no paid plan. */
export type PlanRun = "given" | "cancelled" | "renews" | "free";

export function planRun(me: Pick<Me, "plan" | "paid_plan" | "billing">): PlanRun {
  const paid = me.paid_plan ?? me.plan;
  if (paid === "free") return "free";
  if (me.billing.given_by_owner) return "given";
  return me.billing.cancel_at_period_end ? "cancelled" : "renews";
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
  if (limit != null) return `${used} of ${limit}`;
  if (planLimit != null && lifted) return `${used} (unlimited during ${lifted}; ${plan ?? "your plan"} has ${planLimit} a month)`;
  return `${used} (unlimited)`;
}

/** The plan's row in "Plan and usage", or null for Free. */
export function planRow(me: Pick<Me, "plan" | "paid_plan" | "billing">): [string, string] | null {
  const run = planRun(me), end = me.billing.renews_or_ends;
  if (run === "free") return null;
  if (run === "given") return ["Given by the owner", end ? `Until ${dateOnly(end)}` : "No end date"];
  if (!end) return null;
  return [run === "cancelled" ? "Ends on" : "Renews on", dateOnly(end)];
}
