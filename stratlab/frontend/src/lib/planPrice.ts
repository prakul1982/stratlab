/* A plan's price in words, from the /pricing table: pure (no network), so the unit tests and currency.ts share it. */
import type { CurrencyRow, Pricing } from "./currency";

export function money(row: CurrencyRow | undefined, v: number, code: string): string {
  if (!row) return `₹${v.toLocaleString("en-IN")}`;
  const n = v.toLocaleString(code === "INR" ? "en-IN" : "en-US", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: v % 1 ? 2 : 0 });
  return `${row.symbol}${n}`;
}

/** "Basic is ₹699 a month or ₹6,999 a year.", in `code`'s amounts as the Plans page shows them ("about" for a converted
 * one); the year only while yearly plans are offered. Null for a currency the table doesn't have. */
export function planPriceLine(plan: "basic" | "pro", p: Pricing, code: string): string | null {
  const row = p.currencies[code];
  if (!row || !(row[plan] > 0)) return null;
  const about = row.converted ? "about " : "";
  const name = plan === "pro" ? "Pro" : "Basic";
  const year = p.offer?.yearly !== false && row[`${plan}_year`] > 0 ? ` or ${about}${money(row, row[`${plan}_year`], code)} a year` : "";
  return `${name} is ${about}${money(row, row[plan], code)} a month${year}.`;
}

