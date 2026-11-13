/* AS1: AdSense allows no ad on auto-generated pages or pages with little to no original content. An ad slot shows Google's ad only
 * on a page whose main content holds at least MIN_ORIGINAL_WORDS words of its own text: the same rule as the pages the server draws
 * (backend/app/ads.py, docs/ADMIN.md). Words in <main> count; navigation, header and footer, forms, tables, charts, buttons, link
 * text, the ad itself and anything marked data-shared (wording the same on every page of its kind) don't, and a word has a letter
 * in it, so a number or a date is not one. Loaded with the ad slot's own code only, never with the landing page. */
import type { AdMode, AdSlotName } from "./ads";

export const MIN_ORIGINAL_WORDS = 300;
/** What is left out of the count. */
export const NOT_COUNTED = "script,style,noscript,template,nav,header,footer,form,table,svg,button,select,a,aside,.ad,[data-shared],[hidden],[aria-hidden='true']";
const WORD = /\S*\p{L}\S*/gu;

/** The words in a piece of text (a token with a letter in it). */
export const wordsIn = (text: string | null | undefined): number => (text ?? "").match(WORD)?.length ?? 0;

/** The words of a page's own text in its main content (a copy is counted, so the page itself is never changed). */
export function originalWords(main: Element | null | undefined): number {
  if (!main) return 0;
  const copy = main.cloneNode(true) as Element;
  if (copy.matches(NOT_COUNTED)) return 0;
  copy.querySelectorAll(NOT_COUNTED).forEach((el) => el.remove());
  const walk = copy.ownerDocument.createTreeWalker(copy, 4 /* NodeFilter.SHOW_TEXT */);
  let n = 0;
  while (walk.nextNode()) n += wordsIn(walk.currentNode.nodeValue);
  return n;
}

/** What a slot shows once the page's own words are counted: Google's ad only with enough of them; otherwise what the slot shows
 * with ads off (a StratLab card under an AI answer, nothing on a public page). */
export const withContent = (mode: AdMode, slot: AdSlotName, words: number): AdMode =>
  mode === "ad" && words < MIN_ORIGINAL_WORDS ? (slot === "ai" ? "house" : "none") : mode;
