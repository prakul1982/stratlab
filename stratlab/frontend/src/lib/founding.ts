/* price102 (owner, 28 Nov: "all ok to do", GTM P1 and P3): the founding-member yearly prices and the student price. The server decides
 * whether the founding offer runs (backend offers.founding_public: payments on, both founding plans set, before 31 Dec 2026 23:59 IST and
 * before the 100th paying customer) and sends it, with its words (the line above the cards, a card's note, a lock's yearly price; facts
 * only), as /pricing's and /me's `offer.founding`. The words come from the server so the landing page carries no more than this file
 * within its 450 KB (review-r5). */
import type { Founding } from "./types";

/** The offer while it runs: the server's answer, and not past its end on this page's clock (a page left open past the deadline). */
export function foundingOf(o: { founding?: Founding | null } | null | undefined, now = Date.now()): Founding | null {
  const f = o?.founding;
  return f && f.open && f.prices && f.was && f.note && new Date(f.until).getTime() > now ? f : null;
}

/** The yearly choice's label while the offer runs: a founding year is more than "about 2 months free" (lib/offer YEARLY_LABEL). */
export const FOUNDING_YEARLY = "Yearly · founding-member prices";
