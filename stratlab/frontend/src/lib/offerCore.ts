/* The part of lib/offer.ts the landing page needs (its pricing section): what is on sale today, the pricing heading, the plan buttons,
 * the yearly label and the small print. Its own file so the landing page doesn't download the app's lock, checkout and View-as words
 * (price102 / Release 103: review-r5's 450 KB budget); lib/offer.ts re-exports all of it, so the app and the tests read one module. */
import type { Offer } from "./types";
import { IST } from "./format";

export type PlanId = "free" | "basic" | "pro";

export type OfferMode = Offer["mode"] | "unknown";

/** The mode, or "unknown" while (or if) the offer couldn't be read: then nothing is promised either way. */
export function offerMode(o: Offer | null | undefined): OfferMode {
  return o && (o.mode === "early" || o.mode === "promo" || o.mode === "paid") ? o.mode : "unknown";
}

/** The stored end instant in India time, as the emails say it: "Thu 22 Oct at 5:20 pm IST". */
export function endsAt(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString("en-GB", { timeZone: IST, weekday: "short", day: "numeric", month: "short" }).replace(",", "").replace(/\bSept\b/, "Sep");
  const time = d.toLocaleTimeString("en-GB", { timeZone: IST, hour: "numeric", minute: "2-digit", hour12: true }).replace(/\s?([ap]m)/i, (_, m) => ` ${m.toLowerCase()}`);
  return `${day} at ${time} IST`;
}

/** The same instant in the visitor's own time zone, when that isn't India's: "Thu 22 Oct, 12:50 pm your time" (R68-009: a US
 * or UK visitor had to convert IST themselves). Null in India, or when the browser's zone can't be read. */
export function endsLocal(iso: string, tz?: string): string | null {
  try {
    const zone = tz ?? Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (!zone || zone === IST || zone === "Asia/Calcutta") return null;
    const d = new Date(iso);
    const day = d.toLocaleDateString("en-GB", { timeZone: zone, weekday: "short", day: "numeric", month: "short" }).replace(",", "").replace(/\bSept\b/, "Sep");
    const time = d.toLocaleTimeString("en-GB", { timeZone: zone, hour: "numeric", minute: "2-digit", hour12: true }).replace(/\s?([ap]m)/i, (_, m) => ` ${m.toLowerCase()}`);
    return `${day}, ${time} your time`;
  } catch {
    return null;
  }
}

/** Can a plan be bought right now? Only when payments are set up. */
export const canBuy = (o: Offer | null | undefined) => !!o?.payments;

/** Where people ask for early access while no plan can be bought (config.js CONTACT_EMAIL in the app). */
export const EARLY_ACCESS_EMAIL = "support@stratlab.studio";

/** The heading and the line under it for the pricing section (landing) and the Plans page. Each plan gets exactly
 * what its card lists, payments on or not; only the launch offer opens everything (the owner's decision, 7 Oct). */
export function pricingIntro(o: Offer | null | undefined, _pro: Record<string, unknown>, where: "landing" | "app", email = EARLY_ACCESS_EMAIL, tz?: string): { title: string; lede: string } {
  const mode = offerMode(o);
  if (mode === "promo") {
    const day = endsAt(o!.promo_until!), local = endsLocal(o!.promo_until!, tz);
    return {
      title: where === "landing" ? `Every Pro feature, free until ${day}.` : "Plans",
      // the Plans page shows the countdown box with the end, so its line doesn't state the offer a second time
      lede: (where === "landing" ? `Launch offer: every Pro feature is free for everyone until ${day}${local ? ` (${local})` : ""}. After that, each plan gets what its card lists.`
        : "When the launch offer ends, each plan gets what its card lists.")
        // whether a plan's button sells something now, said outright (R68-009: "Continue with Google to get Pro" during a free offer),
        // and when what is bought starts: the subscription begins at payment, offer or not (R73-005)
        + (o!.payments ? " Basic and Pro are on sale now too. A paid month or year starts on the day you pay, not when the offer ends."
          : ` Paid plans aren't on sale yet; ask us at ${email} for early access.`),
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
      : "Paid plans: cancel any time; the plan stays active until the paid period ends.",
  };
  // the offer couldn't be read (the server didn't answer): the same cards, with what is on them and no promise about what is on sale
  return { title: "Plans", lede: "Every market and every space is on the Free plan. Paid plans raise the limits and add the deeper tools. Today's offer couldn't be loaded, so reload the page to see what is on sale." };
}

/** What a plan card's button does on the landing page: sign in (every button says it goes to Google), or nothing to sell yet (a note). */
export function landingAction(o: Offer | null | undefined, plan: PlanId): { label: string; buy: boolean } | { note: string } {
  if (plan === "free") return { label: "Continue with Google", buy: false };
  // conv101 (P7, funnel: "…to see plans" read as if the plans were hidden): the plan the button is for, while the offer is still being read too
  if (offerMode(o) === "unknown") return { label: `Continue with Google to get ${plan === "pro" ? "Pro" : "Basic"}`, buy: true };
  if (!canBuy(o)) return { note: "Opens soon" };
  return { label: `Continue with Google to get ${plan === "pro" ? "Pro" : "Basic"}`, buy: true };
}

/** The yearly choice's label. Basic's year is exactly ten months; Pro's is ₹9 over (19,999 against 1,999 × 10), so the
 * label says "about" and each yearly card states its own exact saving (`yearlySaving`). */
export const YEARLY_LABEL = "Yearly · about 2 months free";

/** On a phone the choice is "Yearly" alone (owner, 20 Nov: the full label wrapped to two lines, or ran past its half): each yearly card states
 *  its own saving under its price (`yearlySaving`), so nothing is lost. */
export const YEARLY_SHORT = "Yearly";

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
  /** the rupee price of a year, when a year is charged in rupees though shown in another currency */
  chargedYear?: { basic: string; pro: string } | null;
  /** invoices carry GST (the seller's GSTIN is set); without it no GST is promised, only that none is added (R7M-001, R73-001). Taken as true when not given. */
  gst?: boolean;
}): string[] {
  const out: string[] = [];
  const inr = x.currency === "INR";
  const buy = canBuy(o);
  const gst = x.gst ?? true;
  if (inr) {
    if (gst) out.push(buy ? "Rupee prices include 18% GST, and every payment gets a GST invoice." : "Rupee prices include 18% GST.");
    // without a GSTIN the invoice charges none, so the price is the whole amount: said, so a buyer needn't wonder (R73-001)
    else if (buy) out.push("The price shown is all you pay: no GST is added. Every payment gets an invoice in Account.");
  } else if (buy && x.inRupees && x.charged) {
    out.push(`Paid in rupees for now: a card is charged ${x.charged.basic} (Basic) or ${x.charged.pro} (Pro) a month${gst ? " including GST" : " (no GST is added)"}, and your bank converts it, so the amount in ${x.currency} can differ.`);
  }
  if (buy && o?.yearly && x.year) {
    const rupeesYear = x.inRupeesYear && !inr;
    out.push(`Paying yearly: Basic ${x.year.basic}, Pro ${x.year.pro}${!rupeesYear ? "" : x.chargedYear
      ? `, charged in rupees: ${x.chargedYear.basic} (Basic) or ${x.chargedYear.pro} (Pro) a year` : ", charged in rupees"}.`);
  }
  if (buy) out.push("Paid plans renew each month or year until you cancel, which you can do any time from Account.");
  return out;
}
