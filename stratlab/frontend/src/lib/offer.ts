/* What anyone can buy and use today, in words. One source: the server's plans.offer_state(), which reaches the landing
 * page through /pricing and the app through /me. The landing page's Pricing, the Plans page, the launch-offer banners and
 * the plan buttons all word it here, so they can't say different things (early access on one page, "Start with Pro" on
 * another). Pure functions, no network: unit/offer.test.mjs checks them. */
import type { Offer } from "./types";
import { canBuy, EARLY_ACCESS_EMAIL, endsAt, offerMode, type PlanId } from "./offerCore";
// what the landing page needs is in offerCore.ts (its own chunk-light file); everything is still read from here
export * from "./offerCore";


/** The same instant for a phone's one-line banner, without the weekday: "22 Oct, 5:20 pm IST". */
export function endsAtShort(iso: string): string {
  return endsAt(iso).replace(/^\w{3} /, "").replace(" at ", ", ");
}

/** The launch offer's end, while it runs. */
export function promoUntil(o: Offer | null | undefined, now = Date.now()): string | null {
  const until = o?.mode === "promo" ? o.promo_until : null;
  return until && new Date(until).getTime() > now ? until : null;
}

/** What a lock or a limit offers next: "See plans" once a plan can be bought; while none can, "Tell me when plans open", and
 * once that is pressed, a note that they are on the list. While the offer can't be read, nothing is promised: "See plans". */
export function plansCall(o: Offer | null | undefined, joined: boolean): { kind: "see" | "join" | "joined"; label: string } {
  if (canBuy(o) || offerMode(o) === "unknown") return { kind: "see", label: "See plans" };
  return joined ? { kind: "joined", label: "You're on the list" } : { kind: "join", label: "Tell me when plans open" };
}

const RANK: Record<PlanId, number> = { free: 0, basic: 1, pro: 2 };

/** What to do about a locked feature, in one honest line: see the plans while they can be bought, else ask for early
 * access (the server words its 402 answers the same way: plans.upgrade_note). */
export function unlockHint(o: Offer | null | undefined, email = EARLY_ACCESS_EMAIL, price?: string | null, button = true): string {
  if (!canBuy(o)) return `Paid plans open soon; ask us at ${email} for early access.`;
  // the price, while a plan can be bought: "Basic is ₹699 a month or ₹6,999 a year." (R92-001: no lock said it). The way to it
  // is the lock's own button (See plans), so the words don't say it again (DP2-022: "…or see plans for more. See the plans to
  // upgrade."); a lock with no button (a tag's tooltip) says it in words.
  return [price ?? "", button ? "" : "See the plans to upgrade."].filter(Boolean).join(" ");
}

/** LIVE14A-016 (LIVE13A-017): a plan's price after words that end on what that plan gives ("…Basic gives 5 a month."): "It is ₹699 a month…",
 * not "Basic is ₹699 a month…", the plan named twice in a row. Any other price line as it is. */
export function priceAfterWords(words: string, price: string | null | undefined): string | null {
  if (!price) return price ?? null;
  const plan = /\b(Basic|Pro) (?:gives [^.]+|has no limit on [^.]+)\.\s*$/.exec(words)?.[1];
  return plan && price.startsWith(`${plan} is `) ? `It is ${price.slice(plan.length + 4)}` : price;
}

/** A paid feature's tag in the app. Locked: "Basic" or "Pro" with a lock. Usable without paying for that plan (the
 * launch offer, free Basic time from invites, a plan the owner granted): "Basic · open now", with why. */
export function featureTag(plan: PlanId, o: Offer | null | undefined, x: { paid?: PlanId | null; canUse?: boolean; part?: boolean; what?: string }): { label: string; why: string; locked: boolean } {
  const name = plan === "pro" ? "Pro" : "Basic";
  // a page that is free in the main and has a paid part (history, every scheme…) is not locked: its card says which part (`what`:
  // "Pro for advance tax", not "Pro for part", LIVE1B-022)
  if (!x.canUse && x.part) return { label: `${name} for ${x.what ?? "part"}`, why: `Part of this page is on the ${name} plan; the rest is free. ${unlockHint(o, undefined, null, false)}`, locked: false };
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
