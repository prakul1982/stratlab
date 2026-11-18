/* Which currency the plan prices are shown in (owner, 16 Nov: US dollars for US visitors, rupees stay as they are). The visitor's own
 * choice on the "Prices in" switch is kept on this device; with none, the site's region decides (lib/homeMarket: a clock in the
 * Americas is the US), and the page says that is why, so the currency is never a silent guess. The dollar amounts are the /pricing
 * table's USD row (backend pricing.py, changed in Admin → Prices): one config. A dollar price is charged in dollars only when the
 * site's config says dollar checkout is on (USD_CHECKOUT) and the server has the USD Razorpay plans; otherwise the card says the
 * rupee amount it is charged, and checkout asks for the rupee plan. Pure (no imports), so the unit tests load it alone. */

export type PriceCur = "INR" | "USD";
export type Period = "month" | "year";
/** The /pricing USD row's part this file reads. */
export type UsdRow = { basic: number; pro: number; basic_year: number; pro_year: number; charged_in?: string; yearly_charged_in?: string };

/** The visitor's choice, kept on this device (the old picker's "stratlab.currency" stays cleared: lib/currency.ts). */
export const PRICE_CUR_KEY = "stratlab.price-currency";

export function savedPriceCur(store: Pick<Storage, "getItem"> | null | undefined): PriceCur | null {
  try { const v = store?.getItem(PRICE_CUR_KEY); return v === "INR" || v === "USD" ? v : null; } catch { return null; }
}

export function savePriceCur(store: Pick<Storage, "setItem"> | null | undefined, cur: PriceCur): void {
  try { store?.setItem(PRICE_CUR_KEY, cur); } catch { /* storage off: the choice lasts this visit */ }
}

/** The currency shown: the visitor's choice, else dollars for the US region and rupees everywhere else. `auto`: no choice made, so
 * the page says why it shows dollars. */
export function pickPriceCur(saved: PriceCur | null, region: "IN" | "US"): { cur: PriceCur; auto: boolean } {
  return saved ? { cur: saved, auto: false } : { cur: region === "US" ? "USD" : "INR", auto: true };
}

/** The USD row when it has a usable amount for every plan and period, else null (the page then shows rupees only). */
export function usdRowOf(p: { currencies?: Record<string, Partial<UsdRow> | undefined> } | null | undefined): UsdRow | null {
  const r = p?.currencies?.USD;
  if (!r) return null;
  const ok = (v: unknown) => typeof v === "number" && v > 0 && v < 100000;
  return ok(r.basic) && ok(r.pro) && ok(r.basic_year) && ok(r.pro_year) ? (r as UsdRow) : null;
}

/** Whether a dollar price is really charged in dollars for this period: dollar checkout switched on in the config, and the server
 * reports the USD Razorpay plans for the period (`charged_in` / `yearly_charged_in`). */
export function chargedInUsd(usd: UsdRow | null, period: Period, checkoutOn: boolean): boolean {
  return !!usd && checkoutOn && (period === "year" ? usd.yearly_charged_in : usd.charged_in) === "USD";
}

/** The currency the subscribe call asks for: dollars only when they are really charged, else the rupee plan, as before. */
export function checkoutCur(cur: PriceCur, usd: UsdRow | null, period: Period, checkoutOn: boolean): PriceCur {
  return cur === "USD" && chargedInUsd(usd, period, checkoutOn) ? "USD" : "INR";
}

export const rupeeText = (inr: number) => `₹${inr.toLocaleString("en-IN")}`;
/** "US price $8": a plan's own dollar price, beside its rupee price. */
export const usPriceText = (usd: number) => `US price ${dollarText(usd)}`;
export const dollarText = (usd: number) => `$${usd.toLocaleString("en-US", { minimumFractionDigits: usd % 1 ? 2 : 0, maximumFractionDigits: 2 })}`;

/** What a paid plan's card says. `shown`: the main price. `about`: the line beside it ("about $8" beside rupees; "Charged as ₹699
 * in rupees" beside a dollar price that checkout still charges in rupees; null when the dollar price is the charge). `charged`: the
 * amount the card is charged, in the currency it is charged in, for the confirm step and its button. */
export type CardPrice = { shown: string; about: string | null; charged: string; chargedCur: PriceCur; usdShown: boolean };

export function cardPrice(o: { plan: "basic" | "pro"; period: Period; cur: PriceCur; inr: number; usd: UsdRow | null; checkoutOn: boolean;
  /** "about $8" for a rupee amount (lib/usdAbout aboutUsd at today's rate) */ aboutUsd: (inr: number) => string }): CardPrice {
  const { plan, period, cur, inr, usd, checkoutOn } = o;
  const amount = usd ? (period === "year" ? usd[`${plan}_year`] : usd[plan]) : 0;
  // LIVE11B-001 (LIVE10B-001): beside a rupee price, StratLab's own US price when it has one ("US price $8"), not the rupees converted
  // ("about $7"), which read as a second, different dollar price
  if (cur !== "USD" || !usd) return { shown: rupeeText(inr), about: inr > 0 ? (usd ? usPriceText(amount) : o.aboutUsd(inr)) : null, charged: rupeeText(inr), chargedCur: "INR", usdShown: false };
  if (chargedInUsd(usd, period, checkoutOn)) return { shown: dollarText(amount), about: null, charged: dollarText(amount), chargedCur: "USD", usdShown: true };
  return { shown: dollarText(amount), about: `Charged as ${rupeeText(inr)} in rupees`, charged: rupeeText(inr), chargedCur: "INR", usdShown: true };
}

/** Free's price in the currency shown. */
export const freePrice = (cur: PriceCur, usd: UsdRow | null) => (cur === "USD" && usd ? "$0" : "₹0");

/** The line under the switch while dollars were picked by the region, not by the visitor (never a silent guess). */
export const AUTO_USD_LINE = "In US dollars because this device's clock is set to an American time zone. Switch to ₹ any time.";

/** The small print's line on what the dollar prices are, while dollars are shown. */
export function usdPricesNote(usd: UsdRow, period: Period, checkoutOn: boolean): string {
  return chargedInUsd(usd, period, checkoutOn)
    ? "Dollar prices are StratLab's US prices and are charged in US dollars. A card from abroad may get a fee from its bank."
    : "Dollar prices are StratLab's US prices, shown for information: payment is in rupees for now, so your card is charged the rupee amount under each price, and your bank converts it at its own rate and may add a fee.";
}
