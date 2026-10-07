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

const RANK: Record<PlanId, number> = { free: 0, basic: 1, pro: 2 };

/** A paid feature's tag in the app ("Basic", "Pro"). When the person can use it today without paying for that plan
 * (early access, the launch offer, free Basic time), the tag says it's open now and why, so the app and Pricing agree:
 * Pricing lists it under Basic, and the app shows it's a Basic feature that is open for now. */
export function featureTag(plan: PlanId, o: Offer | null | undefined, x: { paid?: PlanId | null; canUse?: boolean }): { label: string; why: string } {
  const name = plan === "pro" ? "Pro" : "Basic";
  const openNow = !!x.canUse && RANK[x.paid ?? "free"] < RANK[plan];
  if (!openNow) return { label: name, why: `On the ${name} plan` };
  const mode = offerMode(o);
  const why = mode === "promo" ? `A ${name} feature, open to everyone during the launch offer`
    : mode === "early" ? `A ${name} feature, open to everyone until paid plans go on sale`
      : `A ${name} feature, open to you for now`;
  return { label: `${name} · open now`, why };
}

const count = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
/** The Free limits a person still meets in early access, in words ("10 backtests a month"), from `free_now`. */
export function stillLimited(o: Offer | null | undefined, pro: Record<string, unknown>): string[] {
  if (!o) return [];
  const f = o.free_now ?? {};
  const out: string[] = [];
  const limited = (k: string) => typeof f[k] === "number" && f[k] !== pro[k];
  if (limited("backtests_per_month")) out.push(`${count(f.backtests_per_month!, "backtest")} a month`);
  if (limited("ai_builds_per_month")) out.push(`${count(f.ai_builds_per_month!, "AI strategy build")} a month`);
  if (limited("deepdives_per_month")) out.push(`${count(f.deepdives_per_month!, "company deep dive")} a month`);
  if (limited("decks_per_month")) out.push(`${count(f.decks_per_month!, "slide deck")} a month`);
  if (limited("live_limit")) out.push(o.free_trial_days ? `paper trading for ${count(o.free_trial_days, "market day")}` : `${count(f.live_limit!, "paper trading session")} at a time`);
  if (limited("stock_alerts")) out.push(count(f.stock_alerts!, "stock alert"));
  if (limited("screens")) out.push(count(f.screens!, "saved screen"));
  if (limited("holdings")) out.push(count(f.holdings!, "holding"));
  return out;
}

/** "a, b and c". */
export function listing(items: string[]): string {
  return items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** The heading and the line under it for the pricing section (landing) and the Plans page. */
export function pricingIntro(o: Offer | null | undefined, pro: Record<string, unknown>, where: "landing" | "app"): { title: string; lede: string } {
  const mode = offerMode(o);
  const limits = stillLimited(o, pro);
  const open = limits.length ? `every feature is open to everyone on the Free plan, with ${listing(limits)}` : "every feature is open to everyone on the Free plan";
  if (mode === "promo") {
    const day = fmtDate(o!.promo_until!, { year: false });
    return {
      title: where === "landing" ? `Every Pro feature, free until ${day}.` : "Plans",
      lede: `Launch offer: every Pro feature is free for everyone until ${day}. After that, each plan's limits apply.`
        + (o!.payments ? "" : " Paid plans aren't on sale yet; the prices below are what they will cost."),
    };
  }
  if (mode === "early") return {
    title: where === "landing" ? "Free during early access." : "Plans",
    lede: `Paid plans aren't on sale yet. Until they are, ${open}. The prices below are what the plans will cost.`,
  };
  if (mode === "paid") return {
    title: where === "landing" ? "Free to start. Pay when you need more." : "Plans",
    lede: where === "landing"
      ? "Every market and every space is on the Free plan. Paid plans raise the limits and add the scans, alerts, live tools, history and the deeper tax tools. Cancel any time."
      : "Cancel any time; your plan stays active until the paid period ends.",
  };
  return { title: where === "landing" ? "Free to start." : "Plans", lede: "Every market and every space is on the Free plan. Paid plans raise the limits and add the deeper tools." };
}

/** What a plan card's button does on the landing page: sign in, or nothing to sell yet (a note, not a button). */
export function landingAction(o: Offer | null | undefined, plan: PlanId): { label: string; buy: boolean } | { note: string } {
  if (plan === "free") return { label: offerMode(o) === "promo" ? "Start free, with every Pro feature" : "Start free", buy: false };
  if (!canBuy(o)) return { note: offerMode(o) === "unknown" ? "Choose a plan after you sign in" : "Not on sale yet" };
  return { label: `Start with ${plan === "pro" ? "Pro" : "Basic"}`, buy: true };
}

/** The small print under the plans, for the currency shown. `prices` are already written in that currency
 * ("₹6,999" or "about $80"); `charged` is the rupee price a card is charged when the currency isn't charged itself. */
export function finePrint(o: Offer | null | undefined, x: {
  currency: string; approx: boolean; approxYear: boolean; year?: { basic: string; pro: string } | null; charged?: { basic: string; pro: string } | null;
}): string[] {
  const out: string[] = [];
  const inr = x.currency === "INR";
  const buy = canBuy(o);
  if (inr) out.push(buy ? "Rupee prices include 18% GST, and every payment gets a GST invoice." : "Rupee prices include 18% GST.");
  else if (x.approx && x.charged) {
    out.push(buy
      ? `Paid in rupees for now: a card is charged ${x.charged.basic} (Basic) or ${x.charged.pro} (Pro) a month including GST, and your bank converts it, so the amount in ${x.currency} can differ slightly.`
      : `Prices in ${x.currency} are the rupee prices (${x.charged.basic} and ${x.charged.pro} a month including GST) at today's exchange rate.`);
  }
  if (buy && o?.yearly && x.year) out.push(`Paying yearly: Basic ${x.year.basic}, Pro ${x.year.pro}${x.approxYear && !inr ? ", charged in rupees" : ""}.`);
  if (buy) out.push("Paid plans renew each month or year until you cancel, which you can do any time from Account.");
  return out;
}
