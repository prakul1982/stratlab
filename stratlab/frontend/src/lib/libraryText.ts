import { fmtDate } from "./format";

/* The words a library strategy's card and page share, kept free of React so the unit tests read them directly. */

/** "11 Oct 2021 to 6 Oct 2026": the tested period by its days, never the stored timestamps (R6V-004). */
export const testedRange = (r: { from: string; to: string } | null | undefined) =>
  r ? `${fmtDate(String(r.from).slice(0, 10))} to ${fmtDate(String(r.to).slice(0, 10))}` : null;

/** Where it was tested, unless the strategy's own name already says so ("Supertrend flip · 20 US large caps"): by the
 * words shown, or by the group's own name (`group`, when `where` adds a count to it). */
export const whereShown = (name: string, where: string | null | undefined, group?: string | null) => {
  const n = name.toLowerCase();
  return where && !n.includes(where.toLowerCase()) && !(group && n.includes(group.toLowerCase())) ? where : null;
};

/** A check's result in words: "Passed", "Warning", "Failed", "Didn't pass" (an older entry that kept only how many
 * passed), "Not run". */
export const CHECK_RESULT: Record<string, string> = { pass: "Passed", warn: "Warning", fail: "Failed", not_passed: "Didn't pass", skip: "Not run" };
