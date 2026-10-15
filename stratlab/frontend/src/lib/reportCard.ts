/** What the report card says when no target could be settled. A period that is over is never "not ended" (R29B-014: FY23 and
 * FY24 targets said so): a target is "not due yet" only while its period runs or its results are still to come; any other
 * is one that no reported number or later statement settles, said as that. */
export function unsettledNote(c: { pending: number; unchecked: number }): string {
  if (c.pending > 0 && c.unchecked === 0) return "None of the targets found can be settled yet: their results are not out yet.";
  if (c.pending > 0) return "None of the targets found could be settled: some have their results still to come, and for the rest no reported number or later statement gives the result.";
  return "None of the targets found could be checked: no reported number or later statement gives their result.";
}

/** An outlook statement with the day it was said, so a statement from an old call isn't read as current (R29B-014). */
export function saidOn(at: string | null | undefined, fmt: (d: string) => string): string {
  return at ? `said ${fmt(at)}` : "date not given";
}
