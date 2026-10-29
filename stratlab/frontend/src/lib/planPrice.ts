/* A plan's price in words, from the /pricing table: pure (no network), so the unit tests and currency.ts share it. */
import type { CurrencyRow, Pricing } from "./currency";
import { inrWithUsd, usdRate } from "./usdAbout";

export function money(row: CurrencyRow | undefined, v: number, code: string): string {
  if (!row) return `₹${v.toLocaleString("en-IN")}`;
  const n = v.toLocaleString(code === "INR" ? "en-IN" : "en-US", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: v % 1 ? 2 : 0 });
  return `${row.symbol}${n}`;
}

/** "Basic is ₹699 a month (about $8) or ₹6,999 a year (about $80).": rupees first, the currency every card is charged in, with the
 * dollar figure beside each amount at the app's USD/INR rate (item 34, owner 29 Oct; before, a browser that said en-US read "$8 a
 * month" alone, LIVE1B-067/078); the year only while yearly plans are offered. Null when the table has no rupee price. */
export function planPriceLine(plan: "basic" | "pro", p: Pricing): string | null {
  const inr = p.currencies.INR;
  if (!inr || !(inr[plan] > 0)) return null;
  const name = plan === "pro" ? "Pro" : "Basic";
  const rate = usdRate(p);
  const yearly = p.offer?.yearly !== false && inr[`${plan}_year`] > 0;
  return `${name} is ${inrWithUsd(inr[plan], rate, "month")}${yearly ? ` or ${inrWithUsd(inr[`${plan}_year`], rate, "year")}` : ""}.`;
}
