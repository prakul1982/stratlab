/* The page's own words, as the build wrote them into its HTML (index.html's start-up block, scripts/seoPages.mjs), kept
 * for the app to draw again while the page's code is on its way. A visitor who opens /library, /pricing or /faq cold sees
 * those words first; the app used to replace them with an "Opening StratLab" splash for a second or two and only then
 * draw the page (R10V-006). Drawing the same words until the page is ready makes the start one continuous page. Pure
 * functions over strings and an element: no React, so unit/review-r10v.test.mjs reads them directly. */

let held = "";

/** The start-up block as the page shows it, ready to draw again: the "wait a moment, then fade in" class dropped (a new
 * element would start that fade over, and the words are already on screen). "" when there is no block, or it is the load
 * error. */
export function startupHtml(root: Pick<Element, "querySelector"> | null): string {
  const block = root?.querySelector("[data-boot]") as (Element & { closest?: (s: string) => Element | null }) | null;
  if (!block || /\bboot-now\b/.test(block.getAttribute("class") ?? "")) return "";
  const outer = (block.closest?.("main") ?? block).outerHTML;
  return outer.replace(/\bboot-wait\b\s*/g, "").replace(/class="boot\s+"/g, 'class="boot"');
}

/** Remember the words the page shows now (call before the app draws over them). */
export function holdStartup(root: Pick<Element, "querySelector"> | null): void {
  held = startupHtml(root);
}

/** The remembered words, "" if none. */
export const heldStartup = (): string => held;
