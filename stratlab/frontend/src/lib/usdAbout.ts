/* Item 34 (owner, 29 Oct): every price reads rupees first, the currency Razorpay charges, with the dollar figure beside it:
 * "₹699 a month (about $8)". The dollar figure is worked out from the USD/INR rate the app already reads each day (/pricing's
 * `usd_inr`, cached on the server), rounded to whole dollars and always "about"; with no rate read, a safe fixed one. No browser
 * locale or saved choice ever shows dollars alone. Pure, so the unit tests load it alone. */

/** Rupees per dollar when /pricing has no rate (an old server, a feed down for days): the figure is still only "about". */
export const USD_INR_FALLBACK = 88;

/** The rate the "about $" figures use: /pricing's, else the fixed one. */
export function usdRate(p: { usd_inr?: { rate?: number } | null } | null | undefined): number {
  const r = p?.usd_inr?.rate;
  return typeof r === "number" && r > 20 && r < 500 ? r : USD_INR_FALLBACK;
}

/** "about $8" for a rupee amount (whole dollars, never under $1 for a paid amount). */
export function aboutUsd(inr: number, rate: number): string {
  const usd = Math.max(1, Math.round(inr / rate));
  return `about $${usd.toLocaleString("en-US")}`;
}

/** "₹6,999" in Indian grouping. */
export const rupees = (inr: number) => `₹${inr.toLocaleString("en-IN")}`;

/** "₹699 a month (about $8)"; `per` left out gives "₹699 (about $8)". Free is "₹0", with no dollar figure. */
export function inrWithUsd(inr: number, rate: number, per?: "month" | "year"): string {
  const own = `${rupees(inr)}${per ? ` a ${per}` : ""}`;
  return inr > 0 ? `${own} (${aboutUsd(inr, rate)})` : own;
}

/** The one line under the plans on what the dollar figures are: "Every price is charged in rupees. The dollar figures beside them
 * are rounded, at ₹95.21 to the dollar (today's rate); a card from abroad is converted by its bank, which may add a fee." */
export function usdNote(rate: number, fallback = false): string {
  const r = `₹${rate.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  return `Every price is charged in rupees. The dollar figures beside them are rounded, at ${fallback ? `about ${r}` : r} to the dollar${fallback ? "" : " (today's rate)"}; a card from abroad is converted by its bank, which may add a fee.`;
}
