import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { usePopover } from "./kit/Dialog";

/** Where an (i) box is drawn: inside the floating layer the button is in (a dialog, the Market Watch panel, a full-screen chart), so it
 * is over that layer and under whatever is over it; else on the body, over the page and under every floating layer. */
function layerOf(el: HTMLElement | null): HTMLElement {
  for (let p = el?.parentElement; p && p !== document.body; p = p.parentElement) if (getComputedStyle(p).position === "fixed") return p;
  return document.body;
}

/** The box of an (i) (ui.tsx Info): drawn in a portal, fixed to its button, so a table's scroll box or a card's edge never cuts it
 * (owner, 5 Nov: the box in a table was cut off at the card's edge). It opens under the button, or above when there is no room below,
 * stays inside the screen's sides, and follows the button on scroll and resize. A click inside it doesn't reach what holds the button. */
export default function InfoPop({ id, btn, close, children }: { id: string; btn: RefObject<HTMLButtonElement | null>; close: (open: boolean) => void; children: ReactNode }) {
  const pop = useRef<HTMLSpanElement>(null);
  // Escape or a click outside closes it (Escape puts the focus back on the button); focus stays on the button while it is open
  usePopover(true, close, btn, pop, { focusInto: false });
  const [host] = useState(() => layerOf(btn.current));
  const [at, setAt] = useState<{ left: number; top: number; up: boolean } | null>(null);
  useLayoutEffect(() => {
    const place = () => {
      const b = btn.current?.getBoundingClientRect(), p = pop.current;
      if (!b || !p) return;
      const vw = document.documentElement.clientWidth, vh = window.innerHeight, gap = 8, edge = 12;
      const w = p.offsetWidth, h = p.offsetHeight;
      // the circle is drawn inside a larger tap box: the box starts a little left of the circle's middle
      const left = Math.max(edge, Math.min(b.left + b.width / 2 - 22, vw - w - edge));
      const below = b.bottom + gap;
      const up = h > vh - below - edge && b.top - gap - h >= edge;
      setAt({ left, top: up ? b.top - gap - h : below, up });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => { window.removeEventListener("scroll", place, true); window.removeEventListener("resize", place); };
  }, [btn, pop]);
  return createPortal(
    <span ref={pop} id={id} role="note" className={`info-pop${at?.up ? " up" : ""}`} onClick={(e) => e.stopPropagation()}
      style={at ? { left: at.left, top: at.top } : { left: 0, top: 0, visibility: "hidden" }}>{children}</span>,
    host);
}
