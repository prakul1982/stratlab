import { useEffect, useState } from "react";
import { publicGet } from "./http";
import type { Offer } from "./types";
import { usdRate } from "./usdAbout";

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
  invoice?: { gst: boolean };
  /** rupees per dollar for the "about $" beside every rupee price (item 34): the daily read, or the server's fixed rate (`fallback`) */
  usd_inr?: { rate: number; fallback?: boolean } };

/** The currency picker's old choice on this device: no longer read (item 34: every price is in rupees, with the dollar beside it),
 * and cleared so a stale "USD" can't come back. */
const KEY = "stratlab.currency";
try { localStorage.removeItem(KEY); } catch { /* storage off */ }

/** Prices, from /pricing: always shown in rupees, the currency every card is charged in, with "about $" beside each (item 34,
 * owner 29 Oct: no browser locale or saved choice shows dollars alone, LIVE1B-067/078). `rate` is the USD/INR rate the dollar
 * figures use (lib/usdAbout.ts). */
export function usePricing() {
  const [p, setP] = useState<Pricing | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "failed">("loading");
  useEffect(() => {
    let live = true;
    // asked again twice before "couldn't be loaded" (R65-002: one failed read during a deploy left the landing page saying
    // today's offer couldn't be loaded)
    let timer = 0;
    const read = (left: number) => publicGet<Pricing>("/pricing").then((r) => { if (live) { setP(r); setStatus("ready"); } })
      .catch(() => { if (!live) return; if (left > 0) timer = window.setTimeout(() => read(left - 1), left === 2 ? 1500 : 4000); else { setP(null); setStatus("failed"); } });
    void read(2);
    return () => { live = false; window.clearTimeout(timer); };
  }, []);
  return { pricing: p, currency: "INR" as const, status, rate: usdRate(p) };
}

let shared: Promise<Pricing> | null = null;

/** A paid plan's price in the visitor's currency, for a lock's note: "Basic is ₹699 a month or ₹6,999 a year." (the
 * amounts the Plans page shows, from one shared read of /pricing). Null until read, or when it can't be. */
export function usePlanPrice(plan: "basic" | "pro" | null | undefined): string | null {
  const [p, setP] = useState<Pricing | null>(null);
  useEffect(() => {
    if (!plan) return;
    let live = true;
    shared ??= publicGet<Pricing>("/pricing").catch((e) => { shared = null; throw e; });
    shared.then((r) => { if (live) setP(r); }).catch(() => {});
    return () => { live = false; };
  }, [plan]);
  if (!plan || !p) return null;
  return planPriceLine(plan, p);
}

/** The same line outside a component (a 402's toast, DP2-022): from the one shared read of /pricing, null when it can't be read. */
export function planPriceFor(plan: "basic" | "pro"): Promise<string | null> {
  shared ??= publicGet<Pricing>("/pricing").catch((e) => { shared = null; throw e; });
  return shared.then((r) => planPriceLine(plan, r)).catch(() => null);
}

export { money, planPriceLine } from "./planPrice";
export { aboutLine, aboutMoney, chargedInRupees } from "./rupeeCharge";
export { aboutUsd, inrWithUsd, rupees, usdNote, usdRate, USD_INR_FALLBACK } from "./usdAbout";
import { planPriceLine } from "./planPrice";

/** The page's note while a currency is charged in rupees, with the actual amounts when its price is a fixed one
 * (R8O-006: "can differ slightly" under €8 for a ₹699 charge of about €6.40). */
export function rupeesNote(code: string, about: { basic: string; pro: string } | null): string {
  if (about) return `Paid in rupees for now: your card is charged the rupee price shown for each plan, about ${about.basic} for Basic and ${about.pro} for Pro at today's rate. Your bank converts it at its own rate and may add a fee.`;
  return `Paid in rupees for now: your card is charged the rupee price shown for each plan, and your bank converts it at its own rate and may add a fee, so the amount in ${code} can differ from the one beside it.`;
}

