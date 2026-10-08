/* What anyone can buy and use today, in words. One source: the server's plans.offer_state(), which reaches the landing
 * page through /pricing and the app through /me. The landing page's Pricing, the Plans page, the launch-offer banners and
 * the plan buttons all word it here, so they can't say different things (early access on one page, "Start with Pro" on
 * another). Pure functions, no network: unit/offer.test.mjs checks them. */
import type { Offer } from "./types";
import { fmtDate } from "./format";

export type PlanId = "free" | "basic" | "pro";
export type OfferMode = Offer["mode"] | "unknown";

/** The mode, or "unknown" while (or if) the offer couldn't be read: then nothing is promised either way. */
export function offerMode(o: Offer | null | undefined): OfferMode {
  return o && (o.mode === "early" || o.mode === "promo" || o.mode === "paid") ? o.mode : "unknown";
}

/** The launch offer's end, while it runs. */
export function promoUntil(o: Offer | null | undefined, now = Date.now()): string | null {
  const until = o?.mode === "promo" ? o.promo_until : null;
  return until && new Date(until).getTime() > now ? until : null;
}

/** Can a plan be bought right now? Only when payments are set up. */
export const canBuy = (o: Offer | null | undefined) => !!o?.payments;


/** What a lock or a limit offers next: "See plans" once a plan can be bought; while none can, "Tell me when plans open", and
 * once that is pressed, a note that they are on the list. While the offer can't be read, nothing is promised: "See plans". */
export function plansCall(o: Offer | null | undefined, joined: boolean): { kind: "see" | "join" | "joined"; label: string } {
  if (canBuy(o) || offerMode(o) === "unknown") return { kind: "see", label: "See plans" };
  return joined ? { kind: "joined", label: "You're on the list" } : { kind: "join", label: "Tell me when plans open" };
}

const RANK: Record<PlanId, number> = { free: 0, basic: 1, pro: 2 };

/** Where people ask for early access while no plan can be bought (config.js CONTACT_EMAIL in the app). */
export const EARLY_ACCESS_EMAIL = "support@stratlab.studio";

/** What to do about a locked feature, in one honest line: see the plans while they can be bought, else ask for early
 * access (the server words its 402 answers the same way: plans.upgrade_note). */
export function unlockHint(o: Offer | null | undefined, email = EARLY_ACCESS_EMAIL): string {
  return canBuy(o) ? "See the plans to upgrade." : `Paid plans open soon; ask us at ${email} for early access.`;
}

/** A paid feature's tag in the app. Locked: "Basic" or "Pro" with a lock. Usable without paying for that plan (the
 * launch offer, free Basic time from invites, a plan the owner granted): "Basic · open now", with why. */
export function featureTag(plan: PlanId, o: Offer | null | undefined, x: { paid?: PlanId | null; canUse?: boolean; part?: boolean }): { label: string; why: string; locked: boolean } {
  const name = plan === "pro" ? "Pro" : "Basic";
  // a page that is free in the main and has a paid part (history, every scheme…) is not locked: its card says which part
  if (!x.canUse && x.part) return { label: `${name} for part`, why: `Part of this page is on the ${name} plan; the rest is free. ${unlockHint(o)}`, locked: false };
  if (!x.canUse) return { label: `🔒 ${name}`, why: `A ${name} feature. ${unlockHint(o)}`, locked: true };
  const openNow = RANK[x.paid ?? "free"] < RANK[plan];
  if (!openNow) return { label: name, why: `On the ${name} plan`, locked: false };
  const why = offerMode(o) === "promo" ? `A ${name} feature, open to everyone during the launch offer` : `A ${name} feature, open to you for now`;
  return { label: `${name} · open now`, why, locked: false };
}

/** "a, b and c". */
export function listing(items: string[]): string {
  return items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** The heading and the line under it for the pricing section (landing) and the Plans page. Each plan gets exactly
 * what its card lists, payments on or not; only the launch offer opens everything (the owner's decision, 7 Oct). */
export function pricingIntro(o: Offer | null | undefined, _pro: Record<string, unknown>, where: "landing" | "app", email = EARLY_ACCESS_EMAIL): { title: string; lede: string } {
  const mode = offerMode(o);
  if (mode === "promo") {
    const day = fmtDate(o!.promo_until!, { year: false });
    return {
      title: where === "landing" ? `Every Pro feature, free until ${day}.` : "Plans",
      lede: `Launch offer: every Pro feature is free for everyone until ${day}. After that, each plan gets what its card lists.`
        + (o!.payments ? "" : ` Paid plans aren't on sale yet; ask us at ${email} for early access.`),
    };
  }
  if (mode === "early") return {
    title: where === "landing" ? "Free to start. Paid plans open soon." : "Plans",
    lede: `The Free plan is open to everyone. Basic and Pro aren't on sale yet; each will include what its card lists. Ask us at ${email} for early access.`,
  };
  if (mode === "paid") return {
    title: where === "landing" ? "Free to start. Pay when you need more." : "Plans",
    lede: where === "landing"
      ? "Every market and every space is on the Free plan. Paid plans raise the limits and add the scans, alerts, live tools, history and the deeper tax tools. Cancel any time."
      : "Cancel any time; your plan stays active until the paid period ends.",
  };
  // the offer couldn't be read (the server didn't answer): the same cards, with what is on them and no promise about what is on sale
  return { title: "Plans", lede: "Every market and every space is on the Free plan. Paid plans raise the limits and add the deeper tools. Today's offer couldn't be loaded, so reload the page to see what is on sale." };
}

/** What a plan card's button does on the landing page: sign in (every button says it goes to Google), or nothing to sell yet (a note). */
export function landingAction(o: Offer | null | undefined, plan: PlanId): { label: string; buy: boolean } | { note: string } {
  if (plan === "free") return { label: "Continue with Google", buy: false };
  if (offerMode(o) === "unknown") return { label: "Continue with Google to see plans", buy: true };
  if (!canBuy(o)) return { note: "Opens soon" };
  return { label: `Continue with Google to get ${plan === "pro" ? "Pro" : "Basic"}`, buy: true };
}

/** The yearly choice's label. Basic's year is exactly ten months; Pro's is ₹9 over (19,999 against 1,999 × 10), so the
 * label says "about" and each yearly card states its own exact saving (`yearlySaving`). */
export const YEARLY_LABEL = "Yearly · about 2 months free";

/** What paying for a year saves against twelve monthly payments, as an amount in the price's own units (null when a
 * year isn't cheaper). */
export function yearlySaving(month: number, year: number): number | null {
  const save = Math.round((month * 12 - year) * 100) / 100;
  return save > 0 ? save : null;
}

/** The small print under the plans, for the currency shown. `year` is written in that currency ("₹6,999", "$80");
 * `charged` is the rupee price a card is charged while the currency isn't charged itself (`inRupees`). */
export function finePrint(o: Offer | null | undefined, x: {
  currency: string; inRupees: boolean; inRupeesYear: boolean; year?: { basic: string; pro: string } | null; charged?: { basic: string; pro: string } | null;
}): string[] {
  const out: string[] = [];
  const inr = x.currency === "INR";
  const buy = canBuy(o);
  if (inr) out.push(buy ? "Rupee prices include 18% GST, and every payment gets a GST invoice." : "Rupee prices include 18% GST.");
  else if (buy && x.inRupees && x.charged) {
    out.push(`Paid in rupees for now: a card is charged ${x.charged.basic} (Basic) or ${x.charged.pro} (Pro) a month including GST, and your bank converts it, so the amount in ${x.currency} can differ.`);
  }
  if (buy && o?.yearly && x.year) out.push(`Paying yearly: Basic ${x.year.basic}, Pro ${x.year.pro}${x.inRupeesYear && !inr ? ", charged in rupees" : ""}.`);
  if (buy) out.push("Paid plans renew each month or year until you cancel, which you can do any time from Account.");
  return out;
}
