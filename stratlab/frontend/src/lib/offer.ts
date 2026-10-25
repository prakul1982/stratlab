/* What anyone can buy and use today, in words. One source: the server's plans.offer_state(), which reaches the landing
 * page through /pricing and the app through /me. The landing page's Pricing, the Plans page, the launch-offer banners and
 * the plan buttons all word it here, so they can't say different things (early access on one page, "Start with Pro" on
 * another). Pure functions, no network: unit/offer.test.mjs checks them. */
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

/** The same instant for a phone's one-line banner, without the weekday: "22 Oct, 5:20 pm IST". */
export function endsAtShort(iso: string): string {
  return endsAt(iso).replace(/^\w{3} /, "").replace(" at ", ", ");
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
export function unlockHint(o: Offer | null | undefined, email = EARLY_ACCESS_EMAIL, price?: string | null, button = true): string {
  if (!canBuy(o)) return `Paid plans open soon; ask us at ${email} for early access.`;
  // the price, while a plan can be bought: "Basic is ₹699 a month or ₹6,999 a year." (R92-001: no lock said it). The way to it
  // is the lock's own button (See plans), so the words don't say it again (DP2-022: "…or see plans for more. See the plans to
  // upgrade."); a lock with no button (a tag's tooltip) says it in words.
  return [price ?? "", button ? "" : "See the plans to upgrade."].filter(Boolean).join(" ");
}

/** A paid feature's tag in the app. Locked: "Basic" or "Pro" with a lock. Usable without paying for that plan (the
 * launch offer, free Basic time from invites, a plan the owner granted): "Basic · open now", with why. */
export function featureTag(plan: PlanId, o: Offer | null | undefined, x: { paid?: PlanId | null; canUse?: boolean; part?: boolean }): { label: string; why: string; locked: boolean } {
  const name = plan === "pro" ? "Pro" : "Basic";
  // a page that is free in the main and has a paid part (history, every scheme…) is not locked: its card says which part
  if (!x.canUse && x.part) return { label: `${name} for part`, why: `Part of this page is on the ${name} plan; the rest is free. ${unlockHint(o, undefined, null, false)}`, locked: false };
  // the lock is the line icon the tag draws beside the word (`locked`), not an emoji in it (DP2-022, DP1-018)
  if (!x.canUse) return { label: name, why: `A ${name} feature. ${unlockHint(o, undefined, null, false)}`, locked: true };
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

/** What a card is charged in rupees, in words: "₹699 incl. 18% GST" while invoices carry GST, "₹699" while the seller has no
 * GSTIN set (R7M-001: the page promised GST that the invoice would not have). */
export function rupeeCharge(amount: number, gst: boolean): string {
  return `₹${amount.toLocaleString("en-IN")}${gst ? " incl. 18% GST" : ""}`;
}

/** The confirm step's words for what a rupee charge is in the currency the visitor sees: " (about $7.23 today)", from the same
 * `charge_about` figure as the plan cards' "Charged as" line (or the card's own "≈ SAR 27" when the price is converted), so the
 * last screen before payment never drops the conversion (R9P-006). Empty when the charge is not in rupees or nothing is known. */
export function chargeAboutNote(inRupeesElsewhere: boolean, shown: string, about: string | null): string {
  if (!inRupeesElsewhere) return "";
  if (about) return ` (about ${about} today)`;
  const m = /^≈\s*(.+)$/.exec(shown);
  return m ? ` (about ${m[1]} today)` : "";
}

/** The line under the plan's name in Razorpay's payment window (its `description`; `notes` are not shown to the payer): the plan, the
 * period and that it renews, short enough to show whole in the window's one line ("Basic, monthly · renews every month", R11P-005; the
 * earlier "Basic plan, ₹699 / month. Renews every month until you cancel." was cut off there, and the window shows the amount itself).
 * Razorpay's own Esc handling inside its frame is not ours to change. */
export function checkoutDescription(plan: string, period: string): string {
  return `${plan}, ${period === "year" ? "yearly" : "monthly"} · renews every ${period}`;
}

/** What the confirm step says about the payment window that opens next: it names the plan and the period (R6V-009, and
 * the line "shows the amount only" was stale once it did). */
export function paymentWindowLine(plan: string, period: string, currency?: string): string {
  return `The payment window that opens next is headed "StratLab · ${plan}, ${period === "year" ? "yearly" : "monthly"}" and shows the amount in ${currency && currency !== "INR" ? currency : "rupees"}.`;
}

/** The confirm step's fact about a switch: billing cancels the old subscription as soon as the new one is active (also for
 * monthly to yearly on the same plan), and the unused time is not refunded. */
export function switchEndsNote(current: string): string {
  return `Your current ${current} plan ends as soon as the new one is active. The unused time on it is not refunded.`;
}

/** Why the Plans page's buy buttons are off while the owner views the app as a plan (R7M-010: they opened a checkout the
 * server then refused). */
export function viewingPlansNote(plan: string): string {
  return `You're viewing as ${plan}. Plan changes and payments are off while View as is on; turn it off to change your billing.`;
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
