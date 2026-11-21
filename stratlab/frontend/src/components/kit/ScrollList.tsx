import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { watchSize } from "../../lib/resize";
import { FLOOR_ROWS, moreBelow, nearEnd, scrollCut, screenRoom } from "../../lib/scrollRows";

/* SCROLL BY SCREEN (owner, Release 87: "it works on screen size, how much of the block a person can see on screen. Then you give a scroll,
 * so they don't have to scroll the whole page and can scroll the specific block"): every item of a list or table is in it; a block is never
 * taller than the screen, and only content taller than that scrolls inside the block (header row sticky, whole rows at rest, a fade while
 * more is below, overscroll contained, reachable by keyboard), never for fewer than three hidden rows. The one way to do it, for lists
 * (ScrollList) and the kit's tables (DataTable, useScrollRows). Owner's reference: Movers' table. CSS: .k-scroll-box / .k-scroll in styles.css. */

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

/** A peer's own height: a card's content, or a column of stacked cards (the last one may stretch to end level, so it is its content). */
function peerNatural(p: Element): number {
  if (p.matches(".k-card")) return natural(p);
  const cards = Array.from(p.children).filter((c) => c.getBoundingClientRect().height > 0);
  if (cards.length > 1) {
    const last = cards[cards.length - 1];
    return last.getBoundingClientRect().top - p.getBoundingClientRect().top + peerNatural(last);
  }
  return natural(p.querySelector(".k-card") ?? p);
}

/** The cards beside this one (a grid's or a flex row's items, tops level) whose content fits them, and how tall the tallest of them is:
 * a long list gives way to it, so the two end level with no blank box under the shorter. null: no such card. */
export function peerHeight(card: Element): number | null {
  let item: Element = card;
  while (item.parentElement && item.parentElement.childElementCount === 1 && item.parentElement !== document.body) item = item.parentElement;
  // a card at the top of a column of cards: the column is the item beside the other card
  const col = item.parentElement;
  if (col && col !== document.body) {
    const cs = getComputedStyle(col);
    if (cs.display.includes("flex") && cs.flexDirection.startsWith("column") && col.parentElement) {
      const rs = getComputedStyle(col.parentElement);
      if (rs.display.includes("grid") || (rs.display.includes("flex") && !rs.flexDirection.startsWith("column"))) return null;   // a card inside a stack: the stack is measured whole
    }
  }
  const row = item.parentElement;
  if (!row) return null;
  const s = getComputedStyle(row);
  if (!(s.display.includes("grid") || (s.display.includes("flex") && !s.flexDirection.startsWith("column")))) return null;
  const top = item.getBoundingClientRect().top, left = item.getBoundingClientRect().left;
  const peers = Array.from(row.children).filter((c) => c !== item && c.getBoundingClientRect().height > 0 && Math.abs(c.getBoundingClientRect().top - top) < 4
    && Math.abs(c.getBoundingClientRect().left - left) > 4 && !c.querySelector(".k-scroll[data-over], .k-tbl-wrap[data-over]"));
  return peers.length ? Math.max(...peers.map(peerNatural)) : null;
}

/** How far down the sticky app header reaches (the phone's top bar), so a block's room starts under it. */
function stickyTop(): number {
  const bar = document.querySelector(".topbar");
  if (!bar) return 0;
  const st = getComputedStyle(bar);
  if (st.display === "none" || !(st.position === "sticky" || st.position === "fixed")) return 0;
  return Math.max(0, bar.getBoundingClientRect().height);
}

/** Sizes `scroller` to the reader's screen: past what fits (the viewport less the sticky header, the block's head and its foot) it scrolls
 * in whole rows, with the fade under it while more is below. Beside a shorter card whose content fits, a long list gives way to it, so the
 * pair ends level. Never for fewer than three hidden rows: then every row shows. `box`: the element whose top and bottom count as the list's
 * (ScrollList's wrapper). `onEnd`: called when the reader nears the end of the rows drawn (a list whose server sends more). Returns whether
 * it scrolls now. `off`: leave the box as it is. */
export function useScrollRows(scroller: RefObject<HTMLElement | null>, { box, items = listRows, off = false, onEnd }:
  { rows?: number; box?: RefObject<HTMLElement | null>; items?: (el: HTMLElement) => HTMLElement[]; off?: boolean; onEnd?: () => void } = {}): boolean {
  const [over, setOver] = useState(false);
  const end = useRef(onEnd);
  end.current = onEnd;
  useLayoutEffect(() => {
    const el = scroller.current, wrap = box?.current ?? null;
    const clear = () => { el?.removeAttribute("data-over"); el?.removeAttribute("data-more"); if (el) el.style.maxHeight = ""; };
    if (!el || off) { clear(); setOver(false); return; }
    const near = () => {
      if (!end.current) return;
      const r = el.getBoundingClientRect();
      const inBox = el.hasAttribute("data-over") ? nearEnd(el.scrollTop, el.clientHeight, el.scrollHeight) : r.bottom - window.innerHeight <= 400;
      if (inBox && r.height > 0) end.current();
    };
    const more = () => { el.toggleAttribute("data-more", el.hasAttribute("data-over") && moreBelow(el.scrollTop, el.clientHeight, el.scrollHeight)); near(); };
    const run = () => {
      const list = wrap ?? el;
      const top = el.getBoundingClientRect().top + el.clientTop - el.scrollTop;
      const bottoms = items(el).map((r) => r.getBoundingClientRect().bottom - top);
      const card = list.closest(".k-card");
      const lr = list.getBoundingClientRect();
      let head = 0, below = 0;
      if (card) {
        const cr = card.getBoundingClientRect();
        head = lr.top - cr.top;
        below = natural(card) - (lr.bottom - cr.top);
      }
      let avail = screenRoom(window.innerHeight, stickyTop(), head, below);
      const peer = card ? peerHeight(card) : null;
      // beside a shorter card, give way to it, but to no fewer than FLOOR_ROWS rows while the screen has room for them
      if (peer !== null && bottoms.length) avail = Math.min(avail, Math.max(Math.floor(peer - head - below), Math.ceil(bottoms[Math.min(FLOOR_ROWS, bottoms.length) - 1])));
      const cut = scrollCut(bottoms, avail);
      if (!cut.over) clear();
      // the box's own edges (its borders, a sideways scrollbar) are added, so the rows' area ends exactly on the last whole row
      else { el.setAttribute("data-over", ""); el.style.maxHeight = `${cut.fit + Math.max(0, el.offsetHeight - el.clientHeight)}px`; }
      more();
      setOver(cut.over);
    };
    run();
    const content = el.firstElementChild;
    const row = (wrap ?? el).closest(".k-card")?.parentElement ?? null;
    const stops = [watchSize(el, run), ...(content ? [watchSize(content, run)] : []), ...(row ? [watchSize(row, run)] : []), ...(row?.parentElement ? [watchSize(row.parentElement, run)] : [])];
    el.addEventListener("scroll", more, { passive: true });
    window.addEventListener("resize", run);
    window.addEventListener("scroll", near, { passive: true });
    return () => { stops.forEach((s) => s()); el.removeEventListener("scroll", more); window.removeEventListener("resize", run); window.removeEventListener("scroll", near); };
  }, [scroller, box, items, off]);
  return over;
}

/** A list that shows every item and, when it is taller than the screen gives it, scrolls inside its card: whole rows at rest, a fade while
 * more is below, a thin scrollbar, reachable by keyboard (named by `label`), the page not dragged along at its ends. Put the list itself
 * inside (a <ul> whose <li> are the rows, or the rows directly). */
export function ScrollList({ label, children, className, testId, onEnd }: { label: string; /** no longer used: the screen sets the height */ rows?: number; children: ReactNode; className?: string; testId?: string; onEnd?: () => void }) {
  const box = useRef<HTMLDivElement>(null), sc = useRef<HTMLDivElement>(null);
  const over = useScrollRows(sc, { box, onEnd });
  return (
    <div ref={box} className={`k-scroll-box${className ? ` ${className}` : ""}`}>
      <div ref={sc} className="k-scroll" data-testid={testId} role={over ? "region" : undefined} aria-label={over ? label : undefined} tabIndex={over ? 0 : undefined}>{children}</div>
    </div>
  );
}
