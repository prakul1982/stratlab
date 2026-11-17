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

/** The one line under the plans on what the dollar figures are: "Prices in ₹ are charged in rupees. The dollar figures beside them
 * are rounded, at ₹95.21 to the dollar (today's rate); a card from abroad is converted by its bank, which may add a fee." With US
 * prices of its own (`us`), they are named, so "about $21" beside ₹1,999 doesn't read as the $20 a US visitor sees (LIVE10B-001);
 * and only the rupee prices are said to be charged in rupees, since dollar prices may be charged in dollars. */
export function usdNote(rate: number, fallback = false, us?: { basic: number; pro: number } | null): string {
  const r = `₹${rate.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
  const usd = (v: number) => `$${v.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
  const own = us ? `: StratLab's US prices are Basic ${usd(us.basic)} and Pro ${usd(us.pro)} a month (Prices in: $ USD)` : "";
  return `Prices in ₹ are charged in rupees. The dollar figures beside them are rounded, at ${fallback ? `about ${r}` : r} to the dollar${fallback ? "" : " (today's rate)"}${own}; a card from abroad is converted by its bank, which may add a fee.`;
}
