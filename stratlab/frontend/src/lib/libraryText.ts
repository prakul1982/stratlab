import { fmtDate } from "./format";

/* The words a library strategy's card and page share, kept free of React so the unit tests read them directly. The
 * title and description live with the site's page words (content/seo.ts), so the build writes the same ones into each
 * strategy's own HTML (R8V-008). */
export { libraryDescription, libraryTitle, whereShown } from "../content/seo";

/** "11 Oct 2021 to 6 Oct 2026": the tested period by its days, never the stored timestamps (R6V-004). */
export const testedRange = (r: { from: string; to: string } | null | undefined) =>
  r ? `${fmtDate(String(r.from).slice(0, 10))} to ${fmtDate(String(r.to).slice(0, 10))}` : null;

/** Why a copy's figures can differ from its card: each card is its own test's dates, and a copy is tested again up to the
 * latest prices (DA-038: a re-test gave +46.2% beside the card's +52.7%, tested to a date 11 days earlier, and nothing said why). */
export const LIBRARY_DATES = "Each card's figures are for the dates under it. A copy is tested again up to the latest prices, so its figures can differ.";

/** A check's result in words: "Passed", "Warning", "Failed", "Didn't pass" (an older entry that kept only how many
 * passed), "Not run". */
export const CHECK_RESULT: Record<string, string> = { pass: "Passed", warn: "Warning", fail: "Failed", not_passed: "Didn't pass", skip: "Not run" };

/** The library's return figures are each the total over the whole test period, not a yearly rate. */
export const TOTAL_AFTER_COSTS = "Total after costs";
export const TOTAL_HOLD = "Total buy and hold";
export const TOTAL_NOTE = "total over the test, after costs";
