/* What the public library's list says about itself: pure (a type import only), so the unit tests load it alone; the card pieces in
 * components/LibraryBits.tsx re-export it. */
import type { LibEntry } from "../components/LibraryBits";
import { num } from "./format";

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
