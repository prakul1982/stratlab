/* How the investor checklist reads: a figure against a stated threshold, as a fact. The server keeps the states
 * pass / watch / fail; none of those words is shown (round 39: StratLab doesn't pass or fail companies). No imports, so
 * the unit tests load it alone. */

export type CheckState = "pass" | "watch" | "fail" | "na";

/** [badge text, badge tone] for a check's state. */
export const CHECK_BADGE: Record<CheckState, [string, string]> = {
  pass: ["Meets threshold", "pass"], watch: ["Between thresholds", "warn"], fail: ["Outside threshold", "fail"], na: ["No data", "skip"],
};

/** "11 meet the stated threshold · 3 between the two thresholds · 0 outside the stated threshold · 2 without data" */
export function checkCountsLine(c: { pass: number; watch: number; fail: number; na?: number }): string {
  return `${c.pass} meet the stated threshold · ${c.watch} between the two thresholds · ${c.fail} outside the stated threshold${c.na ? ` · ${c.na} without data` : ""}`;
}
