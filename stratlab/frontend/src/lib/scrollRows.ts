/* SCROLL BY SCREEN (owner, Release 87: "it works on screen size, how much of the block a person can see on screen. Then you give a scroll,
 * so they don't have to scroll the whole page and can scroll the specific block"): a list or table block is never taller than the reader's
 * screen (the viewport less the sticky app header and the block's own head). Content that fits is drawn whole, with no scroll; only content
 * taller than the screen scrolls inside its block, and never for fewer than MIN_HIDDEN rows hidden (then it grows). The arithmetic only
 * (kit/ScrollList.tsx measures the rows and applies it), so the unit tests pin it without a browser. */

/** A block scrolls only when that hides at least this many rows; fewer and every row shows (owner: "why is there a scroll here for 2 things more"). */
export const MIN_HIDDEN = 3;
/** A long list beside a shorter card gives way to it, but never to fewer whole rows than this (the screen's room allowing). */
export const FLOOR_ROWS = 3;
/** A block's head (its title, a chart above the rows) counts against the screen's room up to this share of the screen (a quarter), so a tall head
 * still leaves the rows a useful box. */
export const HEAD_SHARE = 0.25;
/** What sits under the rows inside their card (a note, or the next tables of a card that holds several) counts up to this share. */
export const FOOT_SHARE = 0.1;
/** Room kept under a block so its bottom edge (and the card's padding) is on screen too. */
export const SCREEN_GAP = 12;
export const PHONE_Q = "(max-width: 640px)";

export interface Cut {
  /** hides MIN_HIDDEN rows or more in `avail`: the block scrolls */
  over: boolean;
  /** the block's height when it scrolls: the bottom edge of the last whole row that fits `avail`, never more than `avail` */
  fit: number;
  /** rows drawn in full at rest */
  shown: number;
}

/** `bottoms`: each row's bottom edge, measured from the top of the block's scrolling box (a table's header row included), in order.
 * `avail`: the height the block may take. A height is always a row's bottom, so a row is never cut through the middle at rest. */
export function scrollCut(bottoms: number[], avail: number): Cut {
  const none: Cut = { over: false, fit: 0, shown: bottoms.length };
  if (!bottoms.length || !(avail > 0)) return none;
  const at = (i: number) => Math.ceil(bottoms[i]);
  if (at(bottoms.length - 1) <= avail + 1) return none;
  let shown = 0;
  for (let i = 0; i < bottoms.length; i++) { if (at(i) <= avail + 1) shown = i + 1; else break; }
  if (bottoms.length - Math.max(1, shown) < MIN_HIDDEN) return none;
  // a block is never taller than its room: one row taller than the screen (a phone's card) is cut at the room, the rest scroll under it
  if (!shown) return { over: true, fit: Math.floor(avail), shown: 1 };
  return { over: true, fit: at(shown - 1), shown };
}

/** The room a block's rows have on this screen: the viewport less the sticky header above, the block's head (capped at HEAD_SHARE of the
 * screen) and what sits under the rows inside the block. */
export function screenRoom(viewport: number, stickyTop: number, head: number, below: number): number {
  return Math.max(0, Math.floor(viewport - stickyTop - Math.min(Math.max(0, head), HEAD_SHARE * viewport) - Math.min(Math.max(0, below), FOOT_SHARE * viewport) - SCREEN_GAP));
}

/** The fade under a list is there while more is below, and gone at the end. */
export function moreBelow(scrollTop: number, clientHeight: number, scrollHeight: number): boolean {
  return scrollHeight - clientHeight - scrollTop > 2;
}

/** AUTO-LOAD: a long list asks the server for its next rows when the reader is this close (px) to the end of what is drawn. */
export const LOAD_AHEAD = 400;
export function nearEnd(scrollTop: number, clientHeight: number, scrollHeight: number, ahead = LOAD_AHEAD): boolean {
  return scrollHeight - clientHeight - scrollTop <= ahead;
}
