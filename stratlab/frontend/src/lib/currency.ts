import { useEffect, useState } from "react";
import { api } from "./api";
import type { Offer } from "./types";

export type CurrencyRow = { symbol: string; name: string; basic: number; pro: number; basic_year: number; pro_year: number;
  charged_in: string; yearly_charged_in: string; approx?: boolean; approx_year?: boolean };
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
  useEffect(() => { api<Pricing>("/pricing").then(setP).catch(() => setP(null)); }, []);
  const auto = p ? p.countries[country() ?? ""] ?? (country() ? "USD" : "INR") : "INR";
  const chosen = p && code && p.currencies[code] ? code : auto;
  const pick = (c: string) => { setCode(c); try { localStorage.setItem(KEY, c); } catch { /* private window */ } };
  return { pricing: p, currency: chosen, pick };
}

export function money(row: CurrencyRow | undefined, v: number, code: string): string {
  if (!row) return `₹${v.toLocaleString("en-IN")}`;
  const n = v.toLocaleString(code === "INR" ? "en-IN" : "en-US", { maximumFractionDigits: v % 1 ? 2 : 0 });
  return `${row.symbol}${n}`;
}
