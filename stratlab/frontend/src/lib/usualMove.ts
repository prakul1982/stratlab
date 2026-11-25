/* site89b: the Results page's "Usual move", said with what it stands on (its own file: resultsRows.ts stays free of imports, as the unit tests
 * read it). */
import { resultDay } from "./resultDay";

/** site89b: a usual move's basis in words, for its hover: the average size of the moves over which earlier results days, measured how. */
export function usualTitle(m: { n: number; dates: string[]; basis?: string }): string {
  const days = m.dates.length ? ` (${m.dates.map((d) => resultDay(d)).join(", ")})` : "";
  return `Average size of the move over ${m.n} earlier results day${m.n === 1 ? "" : "s"}${days}: ${m.basis ?? "close before the results day to the close of the session after it"}`;
}
