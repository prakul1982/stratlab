/* SCROLL (owner, 21 Nov: "add a scroll, don't extend it, and do it everywhere"): how tall a list's scrolling box is, in whole rows.
 * The arithmetic only (kit/ScrollList.tsx measures the rows and applies it), so the unit tests pin it without a browser. */

/** A card's list shows this many rows, then scrolls inside the card. */
export const ROWS = 6;
/** On a phone (<= 640 px) a list is taller, so it isn't cramped. */
export const PHONE_ROWS = 8;
/** A long list beside a card whose content fits gives way to it, down to this many rows (so the pair ends level with no hole). */
export const FLOOR_ROWS = 3;
/** A table inside a card scrolls, its header row kept in view, past this many rows. */
export const TABLE_ROWS = 15;
export const PHONE_Q = "(max-width: 640px)";

export interface Cut {
  /** more rows than the box shows: the list scrolls */
  over: boolean;
  /** the box's own height: the bottom of row `rows` */
  cap: number;
  /** the least it gives way to: the bottom of row FLOOR_ROWS */
  floor: number;
  /** the height used now: the most whole rows that fit `avail` (never less than `floor`), or `cap` */
  fit: number;
}

/** `bottoms`: each row's bottom edge, measured from the top of the list's content, in order. A height is always a row's bottom, so
 * a row is never cut through the middle at rest. */
export function scrollCut(bottoms: number[], rows: number, avail?: number): Cut {
  const n = Math.max(1, Math.floor(rows));
  if (bottoms.length <= n) return { over: false, cap: 0, floor: 0, fit: 0 };
  const at = (i: number) => Math.ceil(bottoms[i]);
  const cap = at(n - 1), floor = at(Math.min(FLOOR_ROWS, n) - 1);
  if (avail == null || !(avail > 0)) return { over: true, cap, floor, fit: cap };
  let fit = floor;
  for (let i = 0; i < bottoms.length; i++) { if (at(i) <= avail + 1) fit = Math.max(fit, at(i)); else break; }
  return { over: true, cap, floor, fit };
}

/** The fade under a list is there while more is below, and gone at the end. */
export function moreBelow(scrollTop: number, clientHeight: number, scrollHeight: number): boolean {
  return scrollHeight - clientHeight - scrollTop > 2;
}

/** The rows for this screen: a phone's list is taller (never shorter than asked). */
export function rowsFor(rows: number, phone: boolean): number {
  return phone ? Math.max(rows, PHONE_ROWS) : rows;
}
