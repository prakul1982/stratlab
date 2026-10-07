import { dateOnly } from "./format";

/* The invite page's words: what a friend gets, what you get on your plan, and this year's count, in plain words.
 * No React here, so the unit tests read it as it is. */

export type Invites = {
  code: string; link: string; joined: number; months?: number; free_basic_until?: string | null; banked_days?: number;
  use_months?: number; use_cap?: number; paid_months?: number; paid_cap?: number; extras?: number; extra_cap?: number;
  extra_pct?: number; extra_days?: number; waiting_to_subscribe?: number;
};
type Plan = "free" | "basic" | "pro";

const PLAN: Record<Plan, string> = { free: "Free", basic: "Basic", pro: "Pro" };
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** What a friend gets: the same for everyone. */
export const FRIEND_GETS = "A friend who joins with your link and uses StratLab on 3 different days in their first 2 weeks gets a month of Basic free.";

/** What you get, on the plan you have now (`paid`: the plan you have without the launch offer). Someone on Free gets
 * Basic straight away; someone on Basic or Pro has the time kept for when their plan stops, as the server does it. */
export function youGet(v: Pick<Invites, "use_cap" | "paid_cap" | "extra_days">, paid: Plan): string {
  const use = v.use_cap ?? 2, pay = v.paid_cap ?? 2, extra = v.extra_days ?? 8;
  const rule = `for each of your first ${use} friends who do this in a year, and for each of your first ${pay} friends who subscribe. `
    + `After that, each friend who subscribes adds ${extra} days.`;
  return paid === "free"
    ? `You get a month of Basic free ${rule}`
    : `You earn a month of free Basic ${rule} You're on ${PLAN[paid]}, so it's kept for you and starts only if your ${PLAN[paid]} plan stops.`;
}

/** This year's count and the time you have, as label and value rows. */
export function inviteRows(v: Invites, paid: Plan): [string, string][] {
  const rows: [string, string][] = [
    ["Friends who joined", String(v.joined)],
    ["Free months earned", String(v.months ?? 0)],
    ["This year: friends who used StratLab", `${v.use_months ?? 0} of ${v.use_cap ?? 2} months`],
    ["This year: friends who subscribed", `${v.paid_months ?? 0} of ${v.paid_cap ?? 2} months`],
  ];
  if ((v.extras ?? 0) > 0 || (v.paid_months ?? 0) >= (v.paid_cap ?? 2)) rows.push(["This year: extra time", plural((v.extras ?? 0) * (v.extra_days ?? 8), "day")]);
  if ((v.waiting_to_subscribe ?? 0) > 0) rows.push(["Waiting to subscribe", plural(v.waiting_to_subscribe ?? 0, "friend")]);
  if (paid !== "free") rows.push(["Kept for when your plan stops", (v.banked_days ?? 0) > 0 ? plural(v.banked_days ?? 0, "day") + " of Basic" : "Nothing yet"]);
  else if (v.free_basic_until) rows.push(["Free Basic", `Until ${dateOnly(v.free_basic_until)}`]);
  return rows;
}
