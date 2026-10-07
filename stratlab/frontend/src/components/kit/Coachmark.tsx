import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { firstFocus } from "../../lib/focusTrap";
import { useDialogFocus } from "./Dialog";

/** The first element on screen that matches one of the selectors (tried in order), or null. */
function findAnchor(selectors: string[]): HTMLElement | null {
  for (const sel of selectors) {
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(sel))) {
      const r = el.getBoundingClientRect();
      const onScreen = r.right > 0 && r.left < window.innerWidth;     // a phone's closed menu drawer sits off to the left
      if (r.width > 0 && r.height > 0 && onScreen && getComputedStyle(el).visibility !== "hidden") return el;
    }
  }
  return null;
}

const GAP = 12;        // between the thing and the note
const EDGE = 16;       // the page's side gutter

/** A short note pointing at one thing on the page, with the rest dimmed: one step of a tour. `anchor` lists CSS
 * selectors to try in order (the desktop place first, then the phone's); with none on screen the note sits in the
 * middle. A dialog: focus starts on its main button, Tab stays inside, Esc closes. `children` is the note's text and
 * buttons. */
export function Coachmark({ anchor, label, onClose, children }: { anchor: string[]; label: string; onClose: () => void; children: ReactNode }) {
  const note = useRef<HTMLDivElement>(null);
  const ring = useRef<HTMLDivElement>(null);
  const [placed, setPlaced] = useState(false);
  const close = useRef(onClose);
  close.current = onClose;
  const key = anchor.join("|");

  // place the ring on the thing and the note under it (or above, when there's no room below), inside the screen
  useLayoutEffect(() => {
    const place = () => {
      const box = note.current, hole = ring.current;
      if (!box || !hole) return;
      const el = findAnchor(anchor);
      const vw = window.innerWidth, vh = window.innerHeight;
      const w = Math.min(box.offsetWidth || 360, vw - 2 * EDGE), h = box.offsetHeight || 200;
      if (!el) {
        hole.dataset.off = "1";
        box.style.setProperty("--cm-x", `${Math.round((vw - w) / 2)}px`);
        box.style.setProperty("--cm-y", `${Math.round(Math.max(EDGE, (vh - h) / 2))}px`);
        box.dataset.side = "none";
        setPlaced(true);
        return;
      }
      const r = el.getBoundingClientRect();
      delete hole.dataset.off;
      for (const [k, v] of [["--cm-hx", r.left - 4], ["--cm-hy", r.top - 4], ["--cm-hw", r.width + 8], ["--cm-hh", r.height + 8]] as const) hole.style.setProperty(k, `${Math.round(v)}px`);
      const below = r.bottom + GAP + h <= vh - EDGE || r.top - GAP - h < EDGE;
      const right = r.left + w > vw - EDGE && r.width < vw / 2 && r.left > vw / 2;    // a thing on the right: hang the note leftwards
      const x = Math.min(Math.max(EDGE, right ? r.right - w : r.left), vw - EDGE - w);
      const y = below ? Math.min(r.bottom + GAP, vh - EDGE - h) : Math.max(EDGE, r.top - GAP - h);
      box.style.setProperty("--cm-x", `${Math.round(x)}px`);
      box.style.setProperty("--cm-y", `${Math.round(Math.max(EDGE, y))}px`);
      box.dataset.side = below ? "below" : "above";
      setPlaced(true);
    };
    findAnchor(anchor)?.scrollIntoView({ block: "nearest" });
    place();
    const again = () => window.requestAnimationFrame(place);
    window.addEventListener("resize", again);
    window.addEventListener("scroll", again, true);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(again) : null;
    if (ro && note.current) ro.observe(note.current);
    return () => { window.removeEventListener("resize", again); window.removeEventListener("scroll", again, true); ro?.disconnect(); };
  }, [key]);   // eslint-disable-line react-hooks/exhaustive-deps

  // focus the step's main button each step, once the note is placed (until then it is hidden, and a hidden control
  // takes no focus); Tab is kept inside and Esc closes below
  useEffect(() => { if (placed && note.current) firstFocus(note.current)?.focus(); }, [key, placed]);
  // the kit's one dialog behaviour: Tab kept inside, Esc closes, focus back to what opened the tour
  useDialogFocus(note, true, { onEscape: () => close.current() });

  return (
    <div className="k-coach" data-placed={placed ? "1" : undefined}>
      <div className="k-coach-ring" ref={ring} aria-hidden="true" />
      <div className="k-coach-note" ref={note} role="dialog" aria-modal="true" aria-label={label} tabIndex={-1}>{children}</div>
    </div>
  );
}
