import { useLayoutEffect, useRef, type RefObject } from "react";

/** The column count for `n` equal tiles when `fit` columns would fit, so the last line never holds one tile alone (3 + 1, 4 + 1, 5 + 1):
 * the fullest even split when there is one (6 tiles in 5 columns become 3 + 3), else the widest count that leaves two or more on the
 * last line (5 in 4 become 3 + 2). `fit` itself when it already leaves none alone. (UI-FIX-1, R9) */
export function fillCols(n: number, fit: number): number {
  if (n < 2 || fit < 2 || n <= fit || n % fit !== 1) return fit;
  const tries: number[] = [];
  for (let c = Math.min(fit, n) - 1; c >= 2; c--) if (n % c !== 1) tries.push(c);
  if (!tries.length) return fit;
  // an even split is only worth taking when it is not much narrower than what fit
  return tries.find((c) => n % c === 0 && c >= fit * 0.6) ?? tries[0];
}

/** A grid of equal tiles (stats, fields, cards) that fills its row count: when the browser's own auto-fit leaves the last tile alone on
 * its line, the grid takes the column count `fillCols` picks. Re-checked when the grid's width or its items change. Put the returned ref
 * on the grid. A grid with a tile two columns wide is left as the page drew it; whole-row items do not count. */
export function useNoOrphan<T extends HTMLElement>(): RefObject<T | null> {
  const ref = useRef<T>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let width = -1;
    const fix = () => {
      el.style.removeProperty("grid-template-columns");
      const tracks = getComputedStyle(el).gridTemplateColumns;
      if (!tracks || tracks === "none") return;
      const fit = tracks.split(" ").filter(Boolean).length;
      const own = Array.from(el.children).filter((c) => getComputedStyle(c).display !== "none");
      const col = (c: Element) => { const s = getComputedStyle(c); return `${s.gridColumnStart}|${s.gridColumnEnd}`; };
      if (own.some((c) => /span/.test(col(c)))) return;                               // a tile two columns wide: leave the grid as drawn
      const kids = own.filter((c) => col(c) !== "1|-1");                              // a whole-row item (the buttons under a form) is no tile
      const c = fillCols(kids.length, fit);
      if (c !== fit) el.style.gridTemplateColumns = `repeat(${c}, minmax(0, 1fr))`;
    };
    const ro = new ResizeObserver(() => { const w = el.clientWidth; if (w !== width) { width = w; fix(); } });
    const mo = new MutationObserver(fix);
    ro.observe(el);
    mo.observe(el, { childList: true });
    fix();
    return () => { ro.disconnect(); mo.disconnect(); };
  }, []);
  return ref;
}
