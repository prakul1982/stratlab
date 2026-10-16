/** A run saved before an account stopped at zero (R13S-001): it says "Account emptied" on one day and then lists trades
 * opened after it, with figures that contradict each other (R29B-009: "871 trades + 10 still open", stop exits at ₹0). Only a
 * re-run can state them truthfully, so the page says so and hides the figures. */
export function emptiedDay(e: { stats?: { emptied_on?: string | null } | null; trades?: { entry_t: string; exit_t: string | null; why?: string }[] | null }): string | null {
  if (e.stats?.emptied_on) return e.stats.emptied_on.slice(0, 10);
  const t = (e.trades ?? []).find((x) => /^account emptied/i.test(x.why ?? ""));
  return t?.exit_t ? t.exit_t.slice(0, 10) : null;
}

export function isLegacyEmptied(e: Parameters<typeof emptiedDay>[0]): boolean {
  const day = emptiedDay(e);
  if (!day) return false;
  return (e.trades ?? []).some((t) => t.entry_t.slice(0, 10) > day);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** "2022-05-09" as "9 May 2022"; anything else as it came. */
function plainDay(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m && MONTHS[Number(m[2]) - 1] ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : iso;
}

/** What every list, comparison or run page says for such a run in place of its figures, in plain words (R38-001, round 39). */
export function legacyNote(e: Parameters<typeof emptiedDay>[0]): string {
  const day = emptiedDay(e);
  return `This run was saved by an older version, and its numbers don't add up (it shows trades after the money ran out${day ? ` on ${plainDay(day)}` : ""}), so they're hidden. Run the notebook again for current figures.`;
}

/** Runs split into those that can be charted and compared and those whose figures are not shown. */
export function splitLegacy<T extends Parameters<typeof emptiedDay>[0]>(runs: T[]): { shown: T[]; legacy: T[] } {
  return { shown: runs.filter((e) => !isLegacyEmptied(e)), legacy: runs.filter((e) => isLegacyEmptied(e)) };
}

/** Why the compare page has nothing to compare, counting the runs whose figures are hidden apart from those that can be
 * compared ("2 experiments" in the list is one run to compare and one hidden, not "one so far"). */
export function compareGap(shown: number, hidden: number): string {
  const lead = `Comparing needs two runs of this notebook${hidden ? " whose figures are shown" : ""}. `;
  const why = hidden === 1 ? "1 is hidden because its figures don't add up" : `${hidden} are hidden because their figures don't add up`;
  if (shown === 1) return lead + (hidden ? `One run can be compared; ${hidden === 1 ? "1 more is" : `${hidden} more are`} hidden because ${hidden === 1 ? "its" : "their"} figures don't add up. Change one thing and run it again.` : "It has one so far: change one thing and run it again.");
  return lead + (hidden ? `No run can be compared yet; ${why}. Run the notebook again for current figures.` : "It has none yet.");
}
