/* How the Ctrl K box ranks what it finds (R5O-024). */

/** Whether a feature's title holds every word typed as a whole word: "sip" names "Test a SIP", "tax" names "Tax report". */
export function namesFeature(title: string, q: string): boolean {
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const have = title.toLowerCase().split(/[^a-z0-9&]+/).filter(Boolean);
  return words.length > 0 && words.every((w) => have.includes(w));
}

/** A search for a contract (a future or an option), not a plain stock: "tcs fut", "nifty 22000 ce", "tcs26octfut". */
export const asksContract = (q: string): boolean =>
  /fut\b|\bfutures?\b|\boptions?\b|\b(ce|pe)\b|\d{2}(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|\bexpiry\b/i.test(q);

/** Whether to offer "Get strategy ideas" for what's typed: not for a lone word nothing matched ("zzzzqq"). */
export const offerIdeas = (q: string, found: { features: number; companies: number; helps: number; intent: boolean }): boolean => {
  const words = q.trim().split(/\s+/).filter(Boolean);
  if (words.length >= 2 || /\?/.test(q)) return true;
  return found.features + found.companies + found.helps > 0 || found.intent;
};

/** The company a name means among the instrument search's rows (any market): a stock or ETF with a company page whose
 * symbol is what was typed, else the first such row (the search ranks them). Indices, coins and contracts are skipped. */
export function pickCompany<T extends { symbol: string; market?: string; type?: string | null; fno?: boolean | null }>(rows: T[], name: string): T | null {
  const up = name.trim().toUpperCase().replace(/\s+/g, " ");
  const companies = rows.filter((r) => (r.market === "IN" || r.market === "US") && !r.fno && (r.type === "EQ" || r.type === "ETF"));
  return companies.find((r) => r.symbol.toUpperCase() === up) ?? companies[0] ?? null;
}

/** The compare page's address for two companies found in any market: on the first one's market (else the second's, else
 * `fallback`), with each company that is listed in that market; one in the other market is left for the reader to pick. */
export function compareTo(a: { symbol: string; market: string } | null, b: { symbol: string; market: string } | null, fallback: string): string {
  const mk = a?.market ?? b?.market ?? (fallback === "US" ? "US" : "IN");
  const p = new URLSearchParams({ region: mk });
  if (a && a.market === mk) p.set("a", a.symbol);
  if (b && b.market === mk) p.set("b", b.symbol);
  return `/research/compare?${p}`;
}
