/* How a card charged in rupees is priced for a visitor whose currency is another (DK-001). Pure, with only a type import, so the unit
 * tests load it alone; lib/currency.ts re-exports it. */
import type { CurrencyRow } from "./currency";

/** An approximate converted amount, rounded to a whole unit: "€6" (the owner, 25 Oct: round every number off; it's
 * "about" anyway, and the bank's own rate differs by more than the cents). */
export function aboutMoney(row: CurrencyRow, v: number, code: string): string {
  return `${row.symbol}${Math.round(v).toLocaleString(code === "INR" ? "en-IN" : "en-US")}`;
}

type Field = "basic" | "pro" | "basic_year" | "pro_year";

/** Whether a card is really charged in rupees though the visitor's currency is another (DK-001): then the rupee price is the
 * main price and the local amount only an "about" beside it. When the currency has its own Razorpay plan (`chargedIn` is
 * the visitor's own currency) the fixed local price stays the main price. One rule for every currency. */
export const chargedInRupees = (row: CurrencyRow | undefined, code: string, chargedIn: string | undefined): boolean => !!row && code !== "INR" && chargedIn === "INR";

/** What the rupee charge is in the visitor's currency, said beside the rupee price: "about $7 at today's rate" (whole units).
 * From the row's `charge_about` (a fixed price charged in rupees), else the row's own amount when it is the converted rupee
 * charge; null when neither is known. */
export function aboutLine(row: CurrencyRow, code: string, field: Field): string | null {
  const v = row.charge_about?.[field] ?? (row.converted ? row[field] : undefined);
  return v != null ? `about ${aboutMoney(row, v, code)} at today's rate` : null;
}
