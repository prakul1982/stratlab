import { useEffect, useState } from "react";
import { publicGet } from "./http";
import type { Offer } from "./types";

export type CurrencyRow = { symbol: string; name: string; basic: number; pro: number; basic_year: number; pro_year: number;
  charged_in: string; yearly_charged_in: string;
  /** the amount is the rupee charge (GST included) at today's rate, rounded: shown with "≈" while the card is charged in
   * rupees (R7O-008: "SAR 22" for a ₹699 charge that is about SAR 27) */
  converted?: boolean;
  /** a currency's own fixed price still charged in rupees: the rupee charge in this currency at today's rate, per field
   * ("basic", "pro", "basic_year", "pro_year"), so Plans says what the card is actually charged (R8O-006) */
  charge_about?: Partial<Record<"basic" | "pro" | "basic_year" | "pro_year", number>> };
export type Pricing = { currencies: Record<string, CurrencyRow>; countries: Record<string, string>; offer?: Offer;
  /** whether invoices carry GST (the seller's GSTIN is set in Admin → Money); the pages say "incl. GST" only then (R7M-001) */
  invoice?: { gst: boolean } };

const KEY = "stratlab.currency";

/** The visitor's country: India by its time zone (most Indian browsers say en-US), else the browser's region. */
function country(): string | null {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    if (tz === "Asia/Kolkata" || tz === "Asia/Calcutta") return "IN";
    for (const l of navigator.languages ?? [navigator.language]) {
      const m = /-([A-Z]{2})$/i.exec(l);
      if (m) return m[1].toUpperCase();
    }
  } catch { /* no Intl: fall through */ }
  return null;
}

/** Prices in every currency, and the one this visitor sees: their own choice, else their country's, else dollars
 * (rupees in India). */
export function usePricing() {
  const [p, setP] = useState<Pricing | null>(null);
  const [code, setCode] = useState<string>(() => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } });
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  useEffect(() => {
    let live = true;
    publicGet<Pricing>("/pricing").then((r) => { if (live) { setP(r); setStatus("ready"); } }).catch(() => { if (live) { setP(null); setStatus("failed"); } });
    return () => { live = false; };
  }, []);
  const auto = p ? p.countries[country() ?? ""] ?? (country() ? "USD" : "INR") : "INR";
  const chosen = p && code && p.currencies[code] ? code : auto;
  const pick = (c: string) => { setCode(c); try { localStorage.setItem(KEY, c); } catch { /* private window */ } };
  return { pricing: p, currency: chosen, pick, status };
}

export { approx } from "./approx";

/** An approximate converted amount with its cents: "€6.40" (whole yen). */
export function aboutMoney(row: CurrencyRow, v: number, code: string): string {
  return `${row.symbol}${code === "JPY" ? Math.round(v).toLocaleString("en-US") : v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** The note under a plan's price when the card is charged in rupees: "Charged as ₹699 incl. GST (about €6.40 today) / month". */
export function chargedLine(charged: string, gst: boolean, period: string, about: string | null): string {
  return `Charged as ${charged}${gst ? " incl. GST" : ""}${about ? ` (about ${about} today)` : ""} / ${period}`;
}

/** The page's note while a currency is charged in rupees, with the actual amounts when its price is a fixed one
 * (R8O-006: "can differ slightly" under €8 for a ₹699 charge of about €6.40). */
export function rupeesNote(code: string, about: { basic: string; pro: string } | null): string {
  if (about) return `Paid in rupees for now: your card is charged the rupee price under each plan, about ${about.basic} for Basic and ${about.pro} for Pro at today's rate, not the ${code} prices shown. Your bank converts it at its own rate and may add a fee.`;
  return `Paid in rupees for now: your card is charged the rupee price shown under each plan, and your bank converts it at its own rate and may add a fee, so the amount in ${code} can differ from the one shown.`;
}

export function money(row: CurrencyRow | undefined, v: number, code: string): string {
  if (!row) return `₹${v.toLocaleString("en-IN")}`;
  const n = v.toLocaleString(code === "INR" ? "en-IN" : "en-US", { maximumFractionDigits: v % 1 ? 2 : 0 });
  return `${row.symbol}${n}`;
}
