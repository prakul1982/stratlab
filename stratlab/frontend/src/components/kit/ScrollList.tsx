import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { watchSize } from "../../lib/resize";
import { FLOOR_ROWS, moreBelow, PHONE_Q, ROWS, rowsFor, scrollCut } from "../../lib/scrollRows";

/* SCROLL (owner, 21 Nov: "it doesn't show all the stocks; add a scroll, don't extend it, and do it everywhere"): every item of a list is in
 * it, and past a few rows the list scrolls inside its card instead of making the card taller. The one way to do it, for lists (ScrollList)
 * and the kit's tables (DataTable, useScrollRows). CSS: .k-scroll-box / .k-scroll in styles.css. */

/** The rows of a scrolling box: a list's items, or a table's body rows. */
const listRows = (el: HTMLElement): HTMLElement[] => {
  const only = el.children.length === 1 ? (el.firstElementChild as HTMLElement) : null;
  return Array.from((only && only.children.length > 0 ? only : el).children) as HTMLElement[];
};

/** How tall a box's content is, from its top to its last child's bottom and its padding: its height before a row stretched it. */
function natural(el: Element): number {
  const r = el.getBoundingClientRect(), st = getComputedStyle(el);
  const bottom = Math.max(r.top, ...Array.from(el.children).map((c) => c.getBoundingClientRect().bottom));
  return bottom - r.top + (parseFloat(st.paddingBottom) || 0) + (parseFloat(st.borderBottomWidth) || 0);
}

/** The cards beside this one (a grid's or a flex row's items, tops level) whose content fits them, and how tall the tallest of them is:
 * a long list gives way to it, so the two end level with no blank box under the shorter. null: no such card. */
function peerHeight(card: Element): number | null {
  let item: Element = card;
  while (item.parentElement && item.parentElement.childElementCount === 1 && item.parentElement !== document.body) item = item.parentElement;
  const row = item.parentElement;
  if (!row) return null;
  const s = getComputedStyle(row);
  if (!(s.display.includes("grid") || (s.display.includes("flex") && !s.flexDirection.startsWith("column")))) return null;
  const top = item.getBoundingClientRect().top;
  const peers = Array.from(row.children).filter((c) => c !== item && c.getBoundingClientRect().height > 0 && Math.abs(c.getBoundingClientRect().top - top) < 4
    && !c.querySelector(".k-scroll[data-over], .k-tbl-wrap[data-over]"));
  return peers.length ? Math.max(...peers.map((p) => natural(p.matches(".k-card") ? p : p.querySelector(".k-card") ?? p))) : null;
}

/** Sizes `scroller` to whole rows: past `rows` it scrolls (on a phone, PHONE_ROWS at least), with the fade under it while more is below.
 * With `box` (ScrollList), the box fills what its card gives it beside a taller neighbour, still in whole rows, and a list taller than a
 * neighbour whose content fits gives way to it (down to FLOOR_ROWS rows), so cards side by side end level. Returns whether it scrolls now. `off`: leave the box as it is (a phone's table drawn as cards). */
export function useScrollRows(scroller: RefObject<HTMLElement | null>, { rows = ROWS, box, items = listRows, off = false }:
  { rows?: number; box?: RefObject<HTMLElement | null>; items?: (el: HTMLElement) => HTMLElement[]; off?: boolean } = {}): boolean {
  const [over, setOver] = useState(false);
  useLayoutEffect(() => {
    const el = scroller.current, wrap = box?.current ?? null;
    const clear = () => { el?.removeAttribute("data-over"); el?.removeAttribute("data-more"); wrap?.removeAttribute("data-over"); if (el) el.style.maxHeight = ""; wrap?.style.removeProperty("--k-scroll-in"); };
    if (!el || off) { clear(); setOver(false); return; }
    const phone = typeof window.matchMedia === "function" ? window.matchMedia(PHONE_Q) : null;
    const more = () => el.toggleAttribute("data-more", el.hasAttribute("data-over") && moreBelow(el.scrollTop, el.clientHeight, el.scrollHeight));
    const run = () => {
      const top = el.getBoundingClientRect().top + el.clientTop - el.scrollTop;
      const bottoms = items(el).map((r) => r.getBoundingClientRect().bottom - top);
      const n = rowsFor(rows, !!phone?.matches);
      let cut = scrollCut(bottoms, n);
      const card = wrap?.closest(".k-card");
      if (wrap && card && bottoms.length > FLOOR_ROWS) {
        // beside a card whose content fits and is shorter, the list gives way (down to FLOOR_ROWS rows) and fills the height that card sets
        const peer = peerHeight(card), full = Math.ceil(bottoms[bottoms.length - 1]);
        const mine = natural(card) - wrap.getBoundingClientRect().height + (cut.over ? cut.cap : full);
        const give = peer !== null && mine > peer + 2;
        if (give || cut.over) {
          const at = give ? scrollCut(bottoms, Math.min(n, FLOOR_ROWS)) : cut;
          wrap.style.setProperty("--k-scroll-in", `${give ? at.floor : at.cap}px`);
          wrap.setAttribute("data-over", "");
          cut = scrollCut(bottoms, give ? Math.min(n, FLOOR_ROWS) : n, wrap.clientHeight);
        }
      } else if (cut.over && wrap) {
        wrap.style.setProperty("--k-scroll-in", `${cut.cap}px`);
        wrap.setAttribute("data-over", "");
        cut = scrollCut(bottoms, n, wrap.clientHeight);
      }
      if (!cut.over) clear();
      else { el.setAttribute("data-over", ""); el.style.maxHeight = `${cut.fit}px`; }
      more();
      setOver(cut.over);
    };
    run();
    const content = el.firstElementChild;
    const row = wrap?.closest(".k-card")?.parentElement ?? null;
    const stops = [watchSize(el, run), ...(content ? [watchSize(content, run)] : []), ...(wrap ? [watchSize(wrap, run)] : []), ...(row ? [watchSize(row, run)] : [])];
    el.addEventListener("scroll", more, { passive: true });
    phone?.addEventListener?.("change", run);
    return () => { stops.forEach((s) => s()); el.removeEventListener("scroll", more); phone?.removeEventListener?.("change", run); };
  }, [scroller, box, items, rows, off]);
  return over;
}

/** A list that shows every item and, past `rows` rows (8 on a phone), scrolls inside its card: whole rows at rest, a fade while more is
 * below, a thin scrollbar, reachable by keyboard (named by `label`), the page not dragged along at its ends. Put the list itself inside
 * (a <ul> whose <li> are the rows, or the rows directly). */
export function ScrollList({ label, rows = ROWS, children, className, testId }: { label: string; rows?: number; children: ReactNode; className?: string; testId?: string }) {
  const box = useRef<HTMLDivElement>(null), sc = useRef<HTMLDivElement>(null);
  const over = useScrollRows(sc, { rows, box });
  return (
    <div ref={box} className={`k-scroll-box${className ? ` ${className}` : ""}`}>
      <div ref={sc} className="k-scroll" data-testid={testId} role={over ? "region" : undefined} aria-label={over ? label : undefined} tabIndex={over ? 0 : undefined}>{children}</div>
    </div>
  );
}
