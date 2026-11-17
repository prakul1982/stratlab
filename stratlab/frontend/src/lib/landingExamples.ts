/* The landing page's real verdicts (NAV3, CX-1 and LIVE9A-019: the three samples were all rupee currency pairs that finished behind buy
 * and hold, under an eyebrow repeating their title). Picked from StratLab's own public library by rule, never by name: one whose checks
 * all passed and one that failed, from different markets, Indian stocks first, then US stocks, then crypto, then the rest. Pure data,
 * no React: unit/nav3.test.mjs checks it. */

export type ExampleEntry = {
  id: string; name: string; market: string; ran?: boolean;
  instrument: { symbol: string } | null; group: { name: string } | null;
  verdict: { verdict: string; passed: number; total: number };
};

/** The markets a newcomer recognises first. */
const MARKET_ORDER = ["IN", "US", "CRYPTO"];
const rank = (m: string) => { const i = MARKET_ORDER.indexOf(m.toUpperCase()); return i < 0 ? MARKET_ORDER.length : i; };

/** Every check passed (and there were checks). */
export const passedAll = (e: ExampleEntry) => e.verdict.total > 0 && e.verdict.passed === e.verdict.total;
/** At least one check failed, or the verdict itself says luck or no edge. */
export const failed = (e: ExampleEntry) => e.verdict.passed < e.verdict.total || e.verdict.verdict === "luck" || e.verdict.verdict === "no_edge";

/** Up to `n` entries: a passing one first (when there is one), then a failing one, then the rest, each from a market not shown yet while
 * there is one, the recognised markets first. */
export function pickExamples<T extends ExampleEntry>(entries: T[], n = 3): T[] {
  const ran = entries.filter((e) => e.ran !== false);
  const out: T[] = [];
  const take = (pool: T[]) => {
    const fresh = pool.filter((e) => !out.includes(e));
    const unseen = fresh.filter((e) => !out.some((o) => o.market === e.market));
    const pick = [...(unseen.length ? unseen : fresh)].sort((a, b) => rank(a.market) - rank(b.market))[0];
    if (pick) out.push(pick);
  };
  take(ran.filter(passedAll));
  take(ran.filter(failed));
  while (out.length < n && out.length < ran.length) take(ran);
  return out.slice(0, n);
}

/** The card's small line above the title: the group or the symbol, unless the title already says it (LIVE9A-019: "4 RUPEE CURRENCY
 * PAIRS" over "… · 4 rupee currency pairs"). */
export function exampleEyebrow(e: ExampleEntry, title: string): string | null {
  const said = e.group ? e.group.name : e.instrument?.symbol ?? e.market;
  return title.toLowerCase().includes(said.toLowerCase()) ? null : said;
}
