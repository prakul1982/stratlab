import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { Close } from "../Icons";
import { firstFocus, tabbables, trapTab } from "../../lib/focusTrap";

/* One behaviour for everything that floats over the page.
 *
 *  - A dialog (Dialog, or useDialogFocus on your own box: the command palette, the phone menu) is modal: focus moves
 *    into it, Tab and Shift+Tab go round inside it, Esc closes it, and when it closes focus goes back to whatever opened
 *    it (or, when that is gone, to `fallback`, else the page's heading). Dialogs stack: only the top one listens.
 *  - A popover (usePopover: a menu, an (i), a rule word's editor) is not modal: focus moves into it, Esc or a click
 *    outside closes it, and focus goes back to its button when it closes with focus inside it or lost.
 */

export { tabbables };

/** Where focus lands when the thing that opened a dialog has gone (a removed row's Edit button): the page's heading. */
function pageHeading(): HTMLElement | null {
  const h = document.querySelector<HTMLElement>("main h1") ?? document.querySelector<HTMLElement>("main");
  if (h && !h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1");
  return h;
}

/** Focus `el` without scrolling the page when it's already on screen; else bring it into view. */
function focusEl(el: HTMLElement | null | undefined) {
  if (!el || !el.isConnected) return false;
  el.focus({ preventScroll: true });
  if (document.activeElement !== el) return false;
  const r = el.getBoundingClientRect();
  if (r.bottom < 0 || r.top > window.innerHeight) el.scrollIntoView({ block: "center" });
  return true;
}

// the last element focused outside every dialog: what a dialog opened from a menu item that is now gone goes back to
let lastOutside: HTMLElement | null = null;
const stack: object[] = [];
if (typeof document !== "undefined") {
  document.addEventListener("focusin", (e) => {
    const t = e.target as HTMLElement;
    if (t && t !== document.body && !t.closest("[aria-modal=true]")) lastOutside = t;
  }, true);
}

export interface DialogFocusOptions {
  /** Esc, unless something inside (a suggestion list, an (i)) handled it first. */
  onEscape?: () => void;
  /** What gets focus first: an element, else the first `[data-autofocus]`, field, then button (not the close ×). */
  initial?: () => HTMLElement | null | undefined;
  /** Where focus goes on close when the opener has gone. */
  fallback?: () => HTMLElement | null | undefined;
}

/** Makes `ref` a modal while `active`: focus in, Tab kept inside, Esc closes, focus back to the opener on close. */
export function useDialogFocus(ref: RefObject<HTMLElement | null>, active: boolean, opts: DialogFocusOptions = {}) {
  const o = useRef(opts);
  o.current = opts;
  useEffect(() => {
    if (!active) return;
    const box = ref.current;
    if (!box) return;
    const me = {};
    stack.push(me);
    const ae = document.activeElement as HTMLElement | null;
    const opener = ae && ae !== document.body && !box.contains(ae) ? ae : lastOutside;
    const first = () => {
      const pick = o.current.initial?.() ?? firstFocus(box);
      if (pick) pick.focus();
      else { if (!box.hasAttribute("tabindex")) box.setAttribute("tabindex", "-1"); box.focus(); }
    };
    first();
    const top = () => stack[stack.length - 1] === me;
    const key = (e: KeyboardEvent) => {
      if (!top()) return;
      if (e.key === "Escape") {
        if (e.defaultPrevented || !o.current.onEscape) return;
        e.preventDefault();
        o.current.onEscape();
      } else trapTab(e, box);
    };
    // focus that lands outside (a click on the page behind, a script) comes back in
    const into = (e: FocusEvent) => {
      if (!top() || box.contains(e.target as Node)) return;
      const t = e.target as HTMLElement;
      if (t.closest?.("[aria-modal=true]")) return;
      first();
    };
    document.addEventListener("keydown", key);
    document.addEventListener("focusin", into);
    return () => {
      document.removeEventListener("keydown", key);
      document.removeEventListener("focusin", into);
      const i = stack.indexOf(me);
      if (i >= 0) stack.splice(i, 1);
      // back to the opener once this dialog has gone; if it went too (a removed row), to the fallback or the heading
      const back = () => {
        const now = document.activeElement;
        if (now && now !== document.body && now.isConnected && !box.contains(now)) return;   // something else took focus on purpose
        if (!focusEl(opener)) if (!focusEl(o.current.fallback?.())) focusEl(pageHeading());
      };
      queueMicrotask(back);
    };
  }, [active, ref]);
}

/** A modal dialog: a title row with a close button, the content, a dimmed page behind it. Esc, the × and a click on the
 * dimmed page close it; focus stays inside while it's open and goes back to what opened it. */
export function Dialog({ title, onClose, children, wide, fallback, label }: {
  title: string; onClose: () => void; children: ReactNode; wide?: boolean;
  /** Where focus goes when the button that opened this is gone after it closes (a removed row's neighbour). */
  fallback?: () => HTMLElement | null | undefined;
  /** The dialog's name for screen readers, when it isn't the title. */
  label?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  useDialogFocus(box, true, { onEscape: onClose, fallback });
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={label ?? title} ref={box}>
        <div className="modal-head">
          <h2 className="h2">{title}</h2>
          <button type="button" className="icon-btn" data-close aria-label="Close" onClick={onClose}><Close /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** A popover's focus: into `panel` when it opens (its first `[role=menuitem]`, field or button, else the panel), Esc
 * and a click outside close it, and focus goes back to `trigger` when it closes with focus inside it or lost. */
export function usePopover(open: boolean, setOpen: (v: boolean) => void, trigger: RefObject<HTMLElement | null>, panel: RefObject<HTMLElement | null>,
  { focusInto = true, outside }: { focusInto?: boolean; outside?: RefObject<HTMLElement | null> } = {}) {
  const close = useRef(setOpen);
  close.current = setOpen;
  const was = useRef(false);
  useEffect(() => {
    if (open) {
      was.current = true;
      const p = panel.current;
      if (focusInto && p) {
        const el = p.querySelector<HTMLElement>("[role=menuitem]") ?? tabbables(p)[0];
        if (el) el.focus();
        else { if (!p.hasAttribute("tabindex")) p.setAttribute("tabindex", "-1"); p.focus(); }
      }
      const key = (e: KeyboardEvent) => {
        if (e.key !== "Escape" || e.defaultPrevented) return;
        e.preventDefault();          // handled: a dialog behind this stays open
        close.current(false);
        trigger.current?.focus();
      };
      const down = (e: PointerEvent) => {
        const t = e.target as Node;
        const wrap = outside?.current;
        if (wrap ? !wrap.contains(t) : !panel.current?.contains(t) && !trigger.current?.contains(t)) close.current(false);
      };
      document.addEventListener("keydown", key, true);
      document.addEventListener("pointerdown", down);
      return () => { document.removeEventListener("keydown", key, true); document.removeEventListener("pointerdown", down); };
    }
    if (was.current) {
      was.current = false;
      // closed: focus was inside the panel (now gone) or nowhere, so it goes back to the button
      const now = document.activeElement;
      if (!now || now === document.body || !now.isConnected) trigger.current?.focus();
    }
  }, [open, focusInto, panel, trigger, outside]);
}
