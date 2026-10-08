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
