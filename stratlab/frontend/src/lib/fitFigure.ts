/* A big figure never breaks inside its digits (LIVE1B-019: "₹6,85,30,\n01,63,68\n0" in a 125px tile). A figure that is one word
 * is kept on one line and its type shrinks, down to 62% of its size, until it fits its box (a rupee amount of ₹100 crore or more
 * is written in crore first: lib/format longRupees). */
/** The smallest the type may shrink to, as a share of its natural size. */
export const FIT_MIN = 0.62;

/** Shrink `el`'s type until its text fits its box on one line. Returns true when it had to shrink by more than 15%, which a row
 * of figures reads as "this one does not fit here". Safe to call again (it starts from the natural size each time). */
export function fitFigure(el: HTMLElement): boolean {
  el.style.fontSize = "";
  const box = el.clientWidth;
  if (!box) return false;
  const natural = parseFloat(getComputedStyle(el).fontSize);
  if (!Number.isFinite(natural) || el.scrollWidth <= box + 0.5) return false;
  let size = natural;
  const floor = natural * FIT_MIN;
  for (let guard = 0; el.scrollWidth > box + 0.5 && size > floor && guard < 40; guard++) {
    size = Math.max(floor, size - 1);
    el.style.fontSize = `${size}px`;
  }
  return size < natural * 0.85;
}
