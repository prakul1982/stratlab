/* How the instrument search lists what it found (components/InstrumentSearch). Pure, so a unit test reads it. */
import type { Instrument } from "./types";

/** The suggestions in groups, the stock or index first, then its futures, then its options, and no more than OPTION_ROWS options until asked: one
 * query ("RELIANCE") was fifty rows, forty of them strikes (LIVE1A-004). */
export const OPTION_ROWS = 6;
const GROUPS = ["Stocks, indices and funds", "Futures", "Options"] as const;
export const groupOf = (r: Pick<Instrument, "type">) => (r.type === "FUT" ? 1 : r.type === "CE" || r.type === "PE" ? 2 : 0);
export function arrange(found: Instrument[], all: boolean): { rows: Instrument[]; hidden: number; heads: Map<string, string> } {
  const sorted = found.map((r, i) => ({ r, i })).sort((a, b) => groupOf(a.r) - groupOf(b.r) || a.i - b.i).map((x) => x.r);
  const opts = sorted.filter((r) => groupOf(r) === 2);
  const rows = all ? sorted : sorted.filter((r) => groupOf(r) !== 2 || opts.indexOf(r) < OPTION_ROWS);
  const used = new Set(rows.map(groupOf));
  const heads = new Map<string, string>();
  if (used.size > 1) for (const g of [0, 1, 2]) { const first = rows.find((r) => groupOf(r) === g); if (first) heads.set(first.id, GROUPS[g]); }
  return { rows, hidden: sorted.length - rows.length, heads };
}

