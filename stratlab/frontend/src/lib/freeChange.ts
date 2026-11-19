/* FREE-TIER: the one-time notice for an account made before the smaller Free plan (the server's plans.free_change_notice): when its
 * Free counts change and exactly what changes, on Account and My space. Pure functions (no React), so the unit tests read the words
 * as they are; the notice is shown until "Got it" is pressed, once for both pages (kept on this device). No email is sent about it. */
import type { FreeChange } from "./types";

/** A count as the notice says it: "no limit" for none. */
export const changeCount = (n: number | null): string => (n == null ? "no limit" : n.toLocaleString("en-IN"));

/** The day the counts change, as people read it: "30 Nov 2026" (India's calendar). */
export function changeDay(iso: string): string {
  const d = new Date(new Date(iso).getTime() + 5.5 * 3600_000);
  return d.toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });
}

/** The notice's heading: "Your Free plan changes on 30 Nov 2026". */
export const changeTitle = (fc: FreeChange): string => `Your Free plan changes on ${changeDay(fc.on)}`;

/** Each change, one line: "Fresh AI reads a day: 60 now, 5 from 30 Nov 2026"; then what moves to Basic. Rows that don't change are left out. */
export function changeLines(fc: FreeChange): string[] {
  const day = changeDay(fc.on);
  return [...fc.rows.filter((r) => r.before !== r.after).map((r) => `${r.label}: ${changeCount(r.before)} now, ${changeCount(r.after)} from ${day}`),
    ...fc.moves.map((m) => `${m}, from ${day}`)];
}

/** The line under the list: what stays. */
export const CHANGE_KEEPS = "Everything you've saved stays, and reads and themes already written still open. Basic keeps the higher limits.";

/** Where "Got it" is kept, so the notice shows once for the change (and again only for a different change date). */
export const changeSeenKey = (fc: FreeChange) => `stratlab:free-change-seen:${fc.on.slice(0, 10)}`;

/** The notice's table (LIVE8B-006: twelve sentences in a box): one row a limit that changes, [limit, now, from the day]. */
export function changeRows(fc: FreeChange): [string, string, string][] {
  return fc.rows.filter((r) => r.before !== r.after).map((r) => [r.label, changeCount(r.before), changeCount(r.after)]);
}

/** The Plans page's line on the Free card for an account in its grace (LIVE8B-008: "Current plan" listed limits this account doesn't
 * have until the change): that it keeps its earlier limits, and from when the card's limits apply. One short line: each count is in
 * Account's table, which the card links to (LIVE9B-009: every limit in one sentence was an 8-line run-on with "aI" for "AI", and made the
 * Free card about 200px taller than Basic's and Pro's). */
export function graceLine(fc: FreeChange): string {
  const moved = fc.rows.filter((r) => r.before !== r.after), n = moved.length;
  // LIVE13B-006: "your earlier limits on 10 counts" read like ten backtests; it is how many of the card's limits are still the earlier ones
  const higher = n > 0 && moved.every((r) => r.before == null || (r.after != null && r.before > r.after)) ? "earlier, higher" : "earlier";
  // LIVE14B-016: "10 of the limits above" stood under a card listing 5; the count is of the account's limits, each in Account's table
  return `Until ${changeDay(fc.on)}, ${n === 1 ? `one of your Free limits stays at your ${higher} level` : `${n} of your Free limits stay at your ${higher} levels`}.`;
}
