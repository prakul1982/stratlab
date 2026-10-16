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

/** The one line every list or comparison of runs shows for such a run in place of its figures (R38-001). */
export function legacyNote(e: Parameters<typeof emptiedDay>[0]): string {
  const day = emptiedDay(e);
  return `Figures not shown: saved by an older version, it says the account emptied${day ? ` on ${day}` : ""} and then lists trades after that day, so its figures contradict each other. A re-run states them.`;
}

/** Runs split into those that can be charted and compared and those whose figures are not shown. */
export function splitLegacy<T extends Parameters<typeof emptiedDay>[0]>(runs: T[]): { shown: T[]; legacy: T[] } {
  return { shown: runs.filter((e) => !isLegacyEmptied(e)), legacy: runs.filter((e) => isLegacyEmptied(e)) };
}
