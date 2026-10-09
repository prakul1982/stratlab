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

/** The lead of a verdict's headline, for a tab title: "117.1 points behind buy and hold after costs" from "117.1 points
 * behind buy and hold after costs; passed all 3 checks run." Without a headline, the verdict's label. */
const lead = (factHeadline?: string | null, label?: string | null) =>
  ((factHeadline ?? "").split(";")[0].trim() || (label ?? "").trim()).replace(/\.\s*$/, "");

/** A library strategy's tab title, the result first, as the page's headline leads with it (R7V-006: the title said
 * "Passed all 3 checks run" over a page that leads with "117.1 points behind buy and hold"). */
export const libraryTitle = (name: string, factHeadline?: string | null, label?: string | null) => {
  const l = lead(factHeadline, label);
  return l ? `${l}: ${name} · StratLab` : `${name} · StratLab`;
};

/** A library strategy's description for search results and link previews: the headline first, then the strategy, with
 * where it was tested only when its name doesn't already say it (R7V-006: "… 20 US large caps on 20 US large caps"). */
export const libraryDescription = (e: { name: string; where?: string | null; group?: string | null; factHeadline?: string | null;
  headline?: string | null; reason?: string | null }) => {
  const on = whereShown(e.name, e.where, e.group);
  return `${e.factHeadline ?? e.headline ?? ""} ${e.name}${on ? ` on ${on}` : ""}. ${e.reason ?? ""} The rules, results after costs and the four checks, as StratLab tested them on past prices.`
    .replace(/\.\s*\./g, ".").replace(/\s+/g, " ").trim();
};
