import { fmtDate } from "./format";

/** A results day as "Thu 19 Nov" (the results pages' and the Invest home's). In a file of its own, not the results page, so the Invest, Trade
 * and Money homes read it without downloading the Research pages (LIVE13B-004: the homes' one file pulled the whole Research page in for it). */
export function resultDay(iso: string) {
  return fmtDate(iso.slice(0, 10), { weekday: true, year: false });
}
