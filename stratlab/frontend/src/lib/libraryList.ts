/* What the public library's list says about itself: pure (its imports are the page words and the formats, and a type), so the unit
 * tests load it alone; the card pieces in components/LibraryBits.tsx re-export it. */
import type { LibEntry } from "../components/LibraryBits";
import { num, TF_NAME } from "./format";
import { groupLabel, plainTerms } from "./plainTerms";

/** A library card's one result line: the return against buy and hold in points, nothing else ("108.5 points behind buy and hold").
 * The card used to say it four times (a pill, a sentence, the checks line again, and a note); the figures stay in its stats row
 * and the full sentence on the strategy's page (DK-014). Null when there is no comparison. */
export function holdResult(e: LibEntry): string | null {
  const h = e.vs_hold;
  if (!h) return null;
  const gap = Math.abs(h.gap);
  return gap < 0.05 ? "About the same as buy and hold" : `${num(gap, 1)} points ${h.gap < 0 ? "behind" : "ahead of"} buy and hold`;
}

/** How the whole list reads in one line, from the data: how many finished behind buy and hold, and how many failed a check. */
export function libraryTally(rows: LibEntry[]): { total: number; behind: number; failed: number; line: string } {
  const behind = rows.filter((e) => e.vs_hold && e.vs_hold.gap <= -0.05).length;
  const failed = rows.filter((e) => (e.verdict.checks ?? []).some((c) => c.status === "fail")).length;
  return { total: rows.length, behind, failed, line: `${behind} of ${rows.length} finished behind buy and hold · ${failed} failed a check` };
}

/** The options of a filter that have something behind them: the empty choice, the chosen one, and every option some entry matches
 * (DK-015: "Mixed check results" and "Too few trades" were offered with no strategy under them). */
export function liveOptions(options: [string, string][], rows: LibEntry[], pick: (e: LibEntry) => string, chosen: string): [string, string][] {
  const has = new Set(rows.map(pick));
  return options.filter(([value]) => !value || value === chosen || has.has(value));
}

/** The markets StratLab's own samples can be about, in the order the library lists them, by their names. */
export const MARKET_NAMES: Record<string, string> = {
  IN: "India", US: "United States", UK: "United Kingdom", EU: "Europe", JP: "Japan", CRYPTO: "Crypto", FX: "Forex",
  MCX: "Indian commodities", CDS: "Indian currency futures", CMDTY: "Global commodities",
};
export const marketName = (id: string) => MARKET_NAMES[id] ?? id;

/** The market filter's choices (MO-5b): "All markets" and each market that has a strategy, with how many, in the library's
 * order; the one picked stays so it can be undone. `counts` is the server's (every strategy the list could show, whatever
 * the search or verdict filter); without it, the rows in hand are counted. */
export function marketChoices(counts: Record<string, number> | undefined, rows: { market: string }[], chosen: string): { value: string; label: string }[] {
  const have: Record<string, number> = counts ?? {};
  if (!counts) for (const r of rows) have[r.market] = (have[r.market] ?? 0) + 1;
  const order = [...Object.keys(MARKET_NAMES), ...Object.keys(have).filter((m) => !(m in MARKET_NAMES)).sort()];
  return [{ value: "", label: "All markets" },
    ...order.filter((m) => have[m] > 0 || m === chosen).map((m) => ({ value: m, label: have[m] ? `${marketName(m)} · ${have[m]}` : marketName(m) }))];
}

/** A card's title: the strategy's own name. StratLab's entries are named "Golden cross · NIFTY 50 stocks" so a copy's notebook
 * says where it was tested; the card says that on its meta line, once (MO-5a). */
export function strategyName(e: Pick<LibEntry, "name" | "group" | "instrument" | "official">): string {
  const name = plainTerms(e.name);
  for (const w of [e.group?.name, e.instrument?.symbol, e.instrument?.name]) {
    const tail = w ? ` · ${plainTerms(w)}` : "";
    if (tail && name.endsWith(tail) && name.length > tail.length) return name.slice(0, -tail.length);
  }
  return e.official ? name.split(" · ")[0].trim() || name : name;
}

/** Where, in what and how a strategy was tested, as one line under the card's top: "Japan · 12 large Japanese companies · Daily candles". */
export function libMeta(e: Pick<LibEntry, "market" | "group" | "instrument" | "tf" | "side">): string {
  const where = e.group ? groupLabel(e.group.name, e.group.members?.length) : e.instrument?.symbol ?? "";
  const side = e.side === "both" ? "long and short" : e.side === "short" ? "short" : "";
  return [marketName(e.market), where, `${TF_NAME[e.tf] ?? e.tf} candles`, side].filter(Boolean).join(" · ");
}
