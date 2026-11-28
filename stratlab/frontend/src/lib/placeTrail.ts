import type { Located } from "./nav";

/** ui100: a page's place as words, a name said once: "Invest › Calendar", never "Invest › Calendar › Calendar" (the Calendar's group and its
 *  own page share the name; Help and search said "Calendar › Calendar"). Its own file, not nav.ts: nav rides in the landing page's download,
 *  whose budget (R5V-020, 450 KB) had no room. */
export const placeTrail = (parts: string[]): string => parts.filter((x, i) => i === 0 || x !== parts[i - 1]).join(" › ");

/** A page's name where it is now, as nav's placeName, with each part said once: "Calendar", not "Calendar › Calendar". */
export function placeLabel(l: Located, was = false): string {
  const own = l.group.pages.length === 1 ? l.page.label : placeTrail([l.group.label, l.page.label]);
  return was && l.page.was ? `${own} (${l.page.was})` : own;
}
