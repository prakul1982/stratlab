import { useEffect, useState } from "react";
import { publicGet } from "./http";
import type { Offer } from "./types";

export type CurrencyRow = { symbol: string; name: string; basic: number; pro: number; basic_year: number; pro_year: number;
  charged_in: string; yearly_charged_in: string;
  /** the amount is the rupee charge (GST included) at today's rate, rounded: shown with "≈" while the card is charged in
   * rupees (R7O-008: "SAR 22" for a ₹699 charge that is about SAR 27) */
  converted?: boolean };
export type Pricing = { currencies: Record<string, CurrencyRow>; countries: Record<string, string>; offer?: Offer };

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

export function money(row: CurrencyRow | undefined, v: number, code: string): string {
  if (!row) return `₹${v.toLocaleString("en-IN")}`;
  const n = v.toLocaleString(code === "INR" ? "en-IN" : "en-US", { maximumFractionDigits: v % 1 ? 2 : 0 });
  return `${row.symbol}${n}`;
}
