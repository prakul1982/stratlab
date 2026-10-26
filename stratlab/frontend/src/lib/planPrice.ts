/* A plan's price in words, from the /pricing table: pure (no network), so the unit tests and currency.ts share it. */
import type { CurrencyRow, Pricing } from "./currency";
import { aboutLine, chargedInRupees } from "./rupeeCharge";

export function money(row: CurrencyRow | undefined, v: number, code: string): string {
  if (!row) return `₹${v.toLocaleString("en-IN")}`;
  const n = v.toLocaleString(code === "INR" ? "en-IN" : "en-US", { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: v % 1 ? 2 : 0 });
  return `${row.symbol}${n}`;
}

/** "Basic is ₹699 a month or ₹6,999 a year.", in `code`'s amounts as the Plans page shows them; the year only while yearly plans are
 * offered. A plan charged in rupees to a visitor whose currency is another (DK-001) is named by its rupee price, the local amount only
 * "about ... at today's rate" after it: "Basic is ₹699 a month or ₹6,999 a year, paid in rupees (about ¥1,155 or ¥11,550 at today's
 * rate)." (RC2A-010: a lock said "¥1,150 a month", a rounded conversion, for a plan charged ₹699). Null for a currency the table doesn't have. */
export function planPriceLine(plan: "basic" | "pro", p: Pricing, code: string): string | null {
  const row = p.currencies[code];
  if (!row || !(row[plan] > 0)) return null;
  const name = plan === "pro" ? "Pro" : "Basic";
  const inr = p.currencies.INR;
  const yearly = p.offer?.yearly !== false && row[`${plan}_year`] > 0;
  const fields = [plan, ...(yearly ? [`${plan}_year` as const] : [])] as ("basic" | "pro" | "basic_year" | "pro_year")[];
  const inRupees = (f: (typeof fields)[number]) => chargedInRupees(row, code, f.endsWith("_year") ? row.yearly_charged_in : row.charged_in) && !!inr && inr[f] > 0;
  if (fields.every(inRupees)) {
    const cost = fields.map((f, i) => `${money(inr, inr[f], "INR")} a ${i ? "year" : "month"}`).join(" or ");
    const about = fields.map((f) => { const l = aboutLine(row, code, f); return l ? l.replace(/^about /, "").replace(/ at today's rate$/, "") : null; });
    return `${name} is ${cost}, paid in rupees${about.every(Boolean) ? ` (about ${about.join(" or ")} at today's rate)` : ""}.`;
  }
  const about = row.converted ? "about " : "";
  const year = yearly ? ` or ${about}${money(row, row[`${plan}_year`], code)} a year` : "";
  return `${name} is ${about}${money(row, row[plan], code)} a month${year}.`;
}
