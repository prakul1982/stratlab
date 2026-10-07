import { dateOnly } from "../../lib/format";
import type { Plan } from "./AdminContext";

/* Admin → Users: the words for a user's plan, and the typed confirmation before their data is deleted. No React here,
 * so the unit tests read it as it is. */

export interface UserRow {
  id: string; email: string | null; created_at: string | null; plan: Plan; plan_set: string; plan_status: string | null;
  plan_until: string | null; paying: boolean; experiments: number; ai_builds: number; referrals?: number; free_months?: number;
}

export const PLAN_NAME: Record<Plan, string> = { free: "Free", basic: "Basic", pro: "Pro" };

/** How a paid plan came and how long it runs: "Razorpay", "Razorpay · renews 5 Nov 2026", "Given · until 6 Nov 2026",
 * "Given · no end date". Empty for Free. */
export function planNote(u: Pick<UserRow, "plan" | "plan_until" | "paying">): string {
  if (u.plan === "free") return "";
  if (u.paying) return u.plan_until ? `Razorpay · renews ${dateOnly(u.plan_until)}` : "Razorpay";
  return u.plan_until ? `Given · until ${dateOnly(u.plan_until)}` : "Given · no end date";
}

/** What has to be typed before a user's data is deleted: their email (their id when there is none). */
export const confirmWord = (u: Pick<UserRow, "id" | "email">): string => u.email ?? u.id;

export { confirmMatches } from "../../lib/account";

export type PlanFilter = "all" | Plan;
export const PLAN_FILTERS: { value: PlanFilter; label: string }[] = [
  { value: "all", label: "All" }, { value: "free", label: "Free" }, { value: "basic", label: "Basic" }, { value: "pro", label: "Pro" },
];

/** The address that lists users: the email search and the plan. */
export function usersPath(q: string, plan: PlanFilter): string {
  return `/admin/users?q=${encodeURIComponent(q)}${plan === "all" ? "" : `&plan=${plan}`}`;
}
