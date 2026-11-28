/* price102 (owner, 28 Nov: "all ok to do", GTM P1 and P3): the founding-member yearly prices and the student price, in words. The server
 * decides whether the founding offer runs (backend offers.founding_public: payments on, both founding plans set, before 31 Dec 2026 23:59
 * IST and before the 100th paying customer) and sends it as /pricing's and /me's `offer.founding`; these words only say it, facts only.
 * Pure and small (no imports beyond types), so the landing page carries it within its 450 KB. */
import type { Founding } from "./types";

type Plan = "basic" | "pro";

/** The offer while it runs: the server's answer, and not past its end on this page's clock (a page left open past the deadline). */
export function foundingOf(o: { founding?: Founding | null } | null | undefined, now = Date.now()): Founding | null {
  const f = o?.founding;
  return f && f.open && f.prices && f.was && new Date(f.until).getTime() > now ? f : null;
}

const rupee = (v: number) => `₹${v.toLocaleString("en-IN")}`;

/** The end in India time, with its year: "31 Dec 2026, 11:59 pm IST". */
export function foundingDeadline(f: Founding): string {
  const d = new Date(f.until);
  const day = d.toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" }).replace(/\bSept\b/, "Sep");
  const time = d.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour: "numeric", minute: "2-digit", hour12: true }).replace(/\s?([ap]m)/i, (_, m) => ` ${m.toLowerCase()}`);
  return `${day}, ${time} IST`;
}

/** The line above the plan cards while the offer runs. */
export function foundingLine(f: Founding): string {
  return `Founding-member prices for the first ${f.seats} members, until ${foundingDeadline(f)}: Basic ${rupee(f.prices.basic)} a year (was ${rupee(f.was.basic)}), `
    + `Pro ${rupee(f.prices.pro)} a year (was ${rupee(f.was.pro)}). The price stays the same for as long as you renew. Monthly prices don't change.`;
}

/** A yearly card's note under its founding price. */
export function foundingCardNote(f: Founding, plan: Plan): string {
  return `Founding-member price for the first ${f.seats} members, until ${foundingDeadline(f)}. Renews at ${rupee(f.prices[plan])} a year for as long as you keep it.`;
}

/** A lock's price words while the offer runs: "₹4,999 a year (founding-member price until 31 Dec 2026, 11:59 pm IST; was ₹6,999)". */
export function foundingYear(f: Founding, plan: Plan): string {
  return `${rupee(f.prices[plan])} a year (founding-member price until ${foundingDeadline(f)}, for the first ${f.seats} members; was ${rupee(f.was[plan])})`;
}

/** The student price's line on Plans (the server's STUDENT_PRICE; approved by hand). */
export const STUDENT_PRICE = 2499;
export function studentLine(price = STUDENT_PRICE): string {
  return `Student? Basic is ${rupee(price)} a year for students, approved by hand: send your college email or a note about your student ID.`;
}
