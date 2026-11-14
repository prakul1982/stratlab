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
 * have until the change): what it has now, and from when the card's limits apply. */
export function graceLine(fc: FreeChange): string {
  const rows = fc.rows.filter((r) => r.before !== r.after);
  return `Yours until ${changeDay(fc.on)}: ${rows.map((r) => `${r.label.charAt(0).toLowerCase()}${r.label.slice(1)} ${changeCount(r.before)}`).join(", ")}. The limits above apply from then.`;
}
