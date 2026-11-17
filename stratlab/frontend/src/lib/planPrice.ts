/* A plan's price in words, from the /pricing table: pure (no network), so the unit tests and currency.ts share it. */
import type { CurrencyRow, Pricing } from "./currency";
import { chargedInUsd, dollarText, rupeeText, usdRowOf, type PriceCur } from "./priceCurrency";
import { inrWithUsd, usdRate } from "./usdAbout";

export function money(row: CurrencyRow | undefined, v: number, code: string): string {
  if (!row) return `₹${v.toLocaleString("en-IN")}`;
  const n = v.toLocaleString(code === "INR" ? "en-IN" : "en-US", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: v % 1 ? 2 : 0 });
  return `${row.symbol}${n}`;
}

/** "Basic is ₹699 a month (about $8) or ₹6,999 a year (about $80).", or with US dollars shown "Basic is $8 a month or $80 a year,
 * charged as ₹699 or ₹6,999 in rupees.": rupees first, the currency every card is charged in, with the
 * dollar figure beside each amount at the app's USD/INR rate (item 34, owner 29 Oct; before, a browser that said en-US read "$8 a
 * month" alone, LIVE1B-067/078); the year only while yearly plans are offered. Null when the table has no rupee price. */
export function planPriceLine(plan: "basic" | "pro", p: Pricing, cur: PriceCur = "INR", usdCheckout = false): string | null {
  const inr = p.currencies.INR;
  if (!inr || !(inr[plan] > 0)) return null;
  const name = plan === "pro" ? "Pro" : "Basic";
  const rate = usdRate(p);
  const yearly = p.offer?.yearly !== false && inr[`${plan}_year`] > 0;
  // in US dollars when that is the currency shown (owner, 16 Nov), with the rupee amounts charged said after them while checkout is in rupees
  const usd = cur === "USD" ? usdRowOf(p) : null;
  if (usd) {
    const shown = `${name} is ${dollarText(usd[plan])} a month${yearly ? ` or ${dollarText(usd[`${plan}_year`])} a year` : ""}`;
    const rupeesToo = !chargedInUsd(usd, "month", usdCheckout) || (yearly && !chargedInUsd(usd, "year", usdCheckout));
    return rupeesToo ? `${shown}, charged as ${rupeeText(inr[plan])}${yearly ? ` or ${rupeeText(inr[`${plan}_year`])}` : ""} in rupees.` : `${shown}.`;
  }
  return `${name} is ${inrWithUsd(inr[plan], rate, "month")}${yearly ? ` or ${inrWithUsd(inr[`${plan}_year`], rate, "year")}` : ""}.`;
}
