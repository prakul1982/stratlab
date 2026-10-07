/* Keeping the keyboard inside a pop-up: Tab from the last control goes to the first, Shift+Tab from the first to the
 * last, and focus that somehow left (a click behind a transparent part) comes back. The low-level parts of the kit's one
 * dialog behaviour (components/kit/Dialog: useDialogFocus, Dialog, usePopover), which every modal uses. */

const TABBABLE = "a[href], area[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), textarea:not([disabled]), iframe, summary, [tabindex], [contenteditable=true]";

/** The controls Tab stops on inside `box`, in order (a roving group's other options, tabIndex -1, are left out, and so is
 * anything hidden, invisible or inside a shut <details>). */
export function tabbables(box: HTMLElement): HTMLElement[] {
  return Array.from(box.querySelectorAll<HTMLElement>(TABBABLE)).filter((el) => {
    if (el.tabIndex < 0 || el.closest("[hidden], [inert]")) return false;
    if (el.tagName === "SUMMARY" && el.parentElement?.tagName !== "DETAILS") return false;
    const d = el.closest("details");
    if (d && !d.open && !el.closest("summary")) return false;
    const r = el.getBoundingClientRect();
    return (r.width > 0 || r.height > 0) && getComputedStyle(el).visibility !== "hidden";
  });
}

/** Handle Tab on a keydown inside (or anywhere while) the pop-up is open. Returns true when it moved focus. */
export function trapTab(e: KeyboardEvent, box: HTMLElement | null): boolean {
  if (e.key !== "Tab" || !box) return false;
  const list = tabbables(box);
  if (!list.length) { e.preventDefault(); box.focus(); return true; }
  const first = list[0], last = list[list.length - 1];
  const at = document.activeElement as HTMLElement | null;
  if (!at || !box.contains(at)) { e.preventDefault(); (e.shiftKey ? last : first).focus(); return true; }
  if (e.shiftKey && at === first) { e.preventDefault(); last.focus(); return true; }
  if (!e.shiftKey && at === last) { e.preventDefault(); first.focus(); return true; }
  return false;
}

/** The control to focus when the pop-up opens: one marked data-autofocus, else the first field, else the first control
 * that isn't the corner close button. A roving group (Seg) offers only its chosen option, so focus lands on what's selected. */
export function firstFocus(box: HTMLElement): HTMLElement | null {
  const marked = box.querySelector<HTMLElement>("[data-autofocus]");
  if (marked) return marked;
  const list = tabbables(box);
  return list.find((el) => /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) ?? list.find((el) => !el.hasAttribute("data-close")) ?? list[0] ?? null;
}
