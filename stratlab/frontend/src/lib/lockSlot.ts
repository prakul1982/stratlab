/* Where a page's plan-lock note goes: straight under the page's title (RC7-003). Every page's title is a PageHeader, which draws an
 * empty slot after itself and registers it here; PageLock (rendered once, above every page) puts its note into whichever slot the
 * page on screen has. A page with no PageHeader has no slot, and the note stays where it was, at the top. */
import { useSyncExternalStore } from "react";

let node: HTMLElement | null = null;
const listeners = new Set<() => void>();
const tell = () => listeners.forEach((f) => f());

/** The ref of a slot: set when it is drawn, cleared (only if it is still the registered one) when it goes. */
export function lockSlotRef(el: HTMLElement | null, was?: HTMLElement | null): void {
  if (el) node = el;
  else if (was && node === was) node = null;
  else if (!was) node = null;
  tell();
}

export function useLockSlot(): HTMLElement | null {
  return useSyncExternalStore(
    (f) => { listeners.add(f); return () => { listeners.delete(f); }; },
    () => node,
    () => null,
  );
}
