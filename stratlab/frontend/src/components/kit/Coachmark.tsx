import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { firstFocus } from "../../lib/focusTrap";
import { useDialogFocus } from "./Dialog";

/** Shown on screen: has a size, is inside the window sideways (a phone's closed menu drawer sits off to the left), not hidden. */
function shown(el: HTMLElement): boolean {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && r.right > 0 && r.left < window.innerWidth && getComputedStyle(el).visibility !== "hidden";
}

/** The first element on screen that matches one of the selectors (tried in order), or null. */
export function findAnchor(selectors: string[]): HTMLElement | null {
  for (const sel of selectors) {
    let list: HTMLElement[] = [];
    try { list = Array.from(document.querySelectorAll<HTMLElement>(sel)); } catch { continue; }
    const el = list.find(shown);
    if (el) return el;
  }
  return null;
}

const GAP = 12;        // between the thing and the note
const EDGE = 16;       // the page's side gutter
/** How long a step waits for its control to appear on a page still loading, and when its fallback (`or`) may be used instead. */
const WAIT = 5000, FALLBACK_AFTER = 1800;
/** A thing taller than TALL of the window is ringed over its top CAP. */
const TALL = 0.55, CAP = 0.36;

/** A short note pointing at one thing on the page, with the rest dimmed: one step of a tour. `anchor` lists CSS selectors any of
 * which may match (the laptop's place, then the phone's); `or` is a fallback used only once none of them has shown up for a
 * moment (a page still loading its list). It waits for the thing (a page just opened), brings it into view, and with nothing
 * to point at the note sits in the middle. A dialog: focus starts on its main button, Tab stays inside, Esc closes; `announce`
 * is read out by a screen reader each step. `children` is the note's text and buttons. */
export function Coachmark({ anchor, or, label, labelledBy, describedBy, announce, onClose, onKey, children }: {
  anchor: string[]; or?: string; label: string; labelledBy?: string; describedBy?: string; announce?: string;
  onClose: () => void; onKey?: (e: ReactKeyboardEvent<HTMLDivElement>) => void; children: ReactNode;
}) {
  const note = useRef<HTMLDivElement>(null);
  const ring = useRef<HTMLDivElement>(null);
  const [placed, setPlaced] = useState(false);
  const close = useRef(onClose);
  close.current = onClose;
  const key = `${anchor.join("|")}#${or ?? ""}`;

  // find the thing (waiting for it on a page still loading), bring it into view, place the ring on it and the note beside it
  useLayoutEffect(() => {
    setPlaced(false);
    let el: HTMLElement | null = null;
    let poll: number | undefined;
    let found = false, foundAt = 0;            // until the thing is found (or the wait is over), nothing is placed: no note in the middle first
    const born = Date.now();
    const place = () => {
      const box = note.current, hole = ring.current;
      if (!box || !hole || !found) return;
      const vw = window.innerWidth, vh = window.innerHeight;
      const w = Math.min(box.offsetWidth || 360, vw - 2 * EDGE), h = box.offsetHeight || 200;
      // the page drew its list again (data came in): the same thing, found afresh
      if (el && (!el.isConnected || !shown(el))) el = findAnchor(anchor) ?? (or ? findAnchor([or]) : null);
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
      // the first time it lands it is put there, not glided in from the middle of the window
      if (!hole.dataset.landed) { hole.style.transition = "none"; requestAnimationFrame(() => requestAnimationFrame(() => { hole.style.transition = ""; })); hole.dataset.landed = "1"; }
      // a thing taller than the window is ringed where it shows
      // a thing taller than about half the window (a whole table, the heatmap) is ringed at its top, so the note has room under it
      const top = Math.max(r.top, 0), bottom = Math.min(r.bottom, vh, r.height > vh * TALL ? top + vh * CAP : Infinity);
      for (const [k, v] of [["--cm-hx", r.left - 4], ["--cm-hy", top - 4], ["--cm-hw", r.width + 8], ["--cm-hh", bottom - top + 8]] as const) hole.style.setProperty(k, `${Math.round(v)}px`);
      // a thing in the left-hand menu: the note goes beside it, not under it, so it never covers the menu items it is
      // talking about (R5O-029)
      if (el.closest(".sidebar") && r.right + GAP + w <= vw - EDGE) {
        box.style.setProperty("--cm-x", `${Math.round(r.right + GAP)}px`);
        box.style.setProperty("--cm-y", `${Math.round(Math.min(Math.max(EDGE, r.top), vh - EDGE - h))}px`);
        box.dataset.side = "right";
        setPlaced(true);
        return;
      }
      const roomBelow = vh - EDGE - (bottom + GAP), roomAbove = top - GAP - EDGE;
      const below = roomBelow >= h || (roomAbove < h && roomBelow >= roomAbove);
      const right = r.left + w > vw - EDGE && r.width < vw / 2 && r.left > vw / 2;    // a thing on the right: hang the note leftwards
      const x = Math.min(Math.max(EDGE, right ? r.right - w : r.left), vw - EDGE - w);
      const y = below ? Math.min(bottom + GAP, vh - EDGE - h) : Math.max(EDGE, top - GAP - h);
      box.style.setProperty("--cm-x", `${Math.round(x)}px`);
      box.style.setProperty("--cm-y", `${Math.round(Math.max(EDGE, y))}px`);
      box.dataset.side = below ? "below" : "above";
      setPlaced(true);
    };
    // no room for the note above or below the thing (a phone, a tall note): the page scrolls so the thing sits under the top bar
    // with the note below it, rather than the note covering it
    const roomForNote = (t: HTMLElement) => {
      const box = note.current;
      if (!box || t.closest(".sidebar, .topbar") || getComputedStyle(t).position === "fixed") return;
      const h = box.offsetHeight, vh = window.innerHeight, r = t.getBoundingClientRect();
      const height = r.height > vh * TALL ? vh * CAP : r.height;
      if (r.top >= 0 && (r.top + height + GAP + h <= vh - EDGE || r.top - GAP - h >= EDGE)) return;
      const bar = Math.max(0, document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 0);
      const want = Math.max(bar + GAP, vh - EDGE - h - GAP - height);
      if (Math.abs(r.top - want) > 2) window.scrollBy({ top: r.top - want, behavior: "instant" as ScrollBehavior });
    };
    const look = () => {
      const waited = Date.now() - born;
      el = findAnchor(anchor) ?? (or && waited >= FALLBACK_AFTER ? findAnchor([or]) : null);
      if (!el && waited < WAIT && (anchor.length > 0 || !!or)) return false;     // nothing to point at (a list of tours): the middle, now
      found = true;
      foundAt = Date.now();
      if (el) {
        // into view: the middle of the window when it was outside it (a card far down a page), else left where it is; no glide,
        // so the ring is placed where the thing ends up
        const r = el.getBoundingClientRect();
        if (r.top < 0 || r.bottom > window.innerHeight) el.scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? "start" : "center", behavior: "instant" as ScrollBehavior });
        roomForNote(el);
      }
      place();
      return true;
    };
    if (!look()) poll = window.setInterval(() => { if (look()) window.clearInterval(poll); }, 100);
    // while the page settles just after the step shows, its growing content may push the thing under the note: make room again
    const again = () => window.requestAnimationFrame(() => { if (el && found && Date.now() - foundAt < 2500) roomForNote(el); place(); });
    window.addEventListener("resize", again);
    window.addEventListener("scroll", again, true);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(again) : null;
    if (ro && note.current) ro.observe(note.current);
    // the page still filling in moves the thing (a row of badges loads above a company's buttons): the ring follows
    const main = document.querySelector("main");
    if (ro && main) ro.observe(main);
    return () => { window.clearInterval(poll); window.removeEventListener("resize", again); window.removeEventListener("scroll", again, true); ro?.disconnect(); };
  }, [key]);   // eslint-disable-line react-hooks/exhaustive-deps

  // focus the step's main button each step, once the note is placed (until then it is hidden, and a hidden control
  // takes no focus); Tab is kept inside and Esc closes below
  useEffect(() => { if (placed && note.current) firstFocus(note.current)?.focus(); }, [key, placed]);
  // the kit's one dialog behaviour: Tab kept inside, Esc closes, focus back to what opened the tour
  useDialogFocus(note, true, { onEscape: () => close.current(), coach: true });

  return (
    <div className="k-coach" data-placed={placed ? "1" : undefined}>
      <div className="k-coach-ring" ref={ring} aria-hidden="true" />
      <div className="k-coach-note" ref={note} role="dialog" aria-modal="true" aria-label={labelledBy ? undefined : label}
        aria-labelledby={labelledBy} aria-describedby={describedBy} tabIndex={-1} onKeyDown={onKey}>{children}</div>
      {/* read out once the step shows (the note is hidden while its page loads, and a hidden region says nothing) */}
      <p className="sr-only" aria-live="polite" aria-atomic="true">{placed ? announce : ""}</p>
    </div>
  );
}
