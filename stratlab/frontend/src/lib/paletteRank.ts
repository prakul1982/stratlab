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

/** Whether to offer "Get strategy ideas" for what's typed: not for a lone word nothing matched ("zzzzqq"), and not for the
 * name of a page (`page`: "settings", "invoice", "dark mode" each got "Get strategy ideas for …", DI-003). */
export const offerIdeas = (q: string, found: { features: number; companies: number; helps: number; intent: boolean; page?: boolean }): boolean => {
  if (found.page) return false;
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

/** Whether a help article is the answer to put first for a question: only when it clearly matches (most of the words). Otherwise a
 * question-like line puts the AI's "Do it" first (R31-001). Returns what Enter should do first. */
export const firstForQuestion = (asksInWords: boolean, clearHelps: number): "help" | "ai" | null =>
  !asksInWords ? null : clearHelps > 0 ? "help" : "ai";

/** A stock or ETF with a company page, as opposed to an index, a coin or a contract. */
export const isCompany = (i: { market?: string; type?: string | null; fno?: boolean | null }): boolean =>
  (i.market === "IN" || i.market === "US") && !i.fno && (i.type === "EQ" || i.type === "ETF");

/** One company the box found: its page's address, and how well it matched (name_search's groups, 0 best; 9 not said). */
export interface CompanyHit { key: string; symbol: string; name?: string | null; exchange?: string | null; market: "IN" | "US"; match: number; to: string }
type InstLike = { symbol: string; name?: string | null; exchange?: string | null; market?: string; type?: string | null; fno?: boolean | null; match?: number };
type SuggestLike = { symbol: string; id?: string; name?: string | null; exchange?: string | null; market?: string; match?: number };

/** The companies for what's typed, from both lists: the live instrument search and the company directory that "Look up a
 * company" uses. The directory works when the India feed is off (a weekend) and allows for a typo, so "TCS" and "relaince"
 * still find their company (DI-001, DI-003). One row per company, best match first (the directory's order on a tie, so
 * India comes before the US listing of the same name). */
export function companyHits(insts: InstLike[], suggested: SuggestLike[], limit = 5): CompanyHit[] {
  const out = new Map<string, CompanyHit>();
  const page = (market: string, code: string) => `/research/${market}/${encodeURIComponent(code)}`;
  for (const s of suggested) {
    if (s.market !== "IN" && s.market !== "US") continue;
    const key = `${s.market}:${s.symbol.toUpperCase()}`;
    // a company listed only on BSE opens by its code (the directory's id); every other by its symbol
    if (!out.has(key)) out.set(key, { key, symbol: s.symbol, name: s.name, exchange: s.exchange, market: s.market, match: s.match ?? 9, to: page(s.market, s.id || s.symbol) });
  }
  for (const i of insts) {
    if (!isCompany(i)) continue;
    const market = i.market as "IN" | "US";
    const key = `${market}:${i.symbol.toUpperCase()}`;
    const had = out.get(key);
    if (had) had.match = Math.min(had.match, i.match ?? 9);
    else out.set(key, { key, symbol: i.symbol, name: i.name, exchange: i.exchange, market, match: i.match ?? 9, to: page(market, i.symbol) });
  }
  return [...out.values()].sort((a, b) => a.match - b.match).slice(0, limit);
}

/** Whether the box puts its companies before "Do it" (DI-002: "infosys" and "AAPL" led with the AI's "Do it", so Enter ran the
 * AI instead of opening the company): whenever it found one and nothing else was put first, for a name of a word or two,
 * or a company it is sure of. */
export const companyFirst = (o: { companies: CompanyHit[]; words: number; firstGroup: string | undefined; intent: boolean }): boolean =>
  !o.intent && o.firstGroup === "Do" && o.companies.length > 0 && (o.words <= 2 || o.companies[0].match <= 3);
