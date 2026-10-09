/* Admin → Data and jobs → India holidays: how the saved holidays are counted. No React here, so the unit tests read it as it is. */

/** "20 saved, all from the exchange." or "20 saved: 18 from the exchange, 2 added by you." `saved` is every holiday kept, `byHand` only the
 * dates the owner pasted that the exchange's list lacks (R11P-006: the page said "20 added by you" for 20 holidays that all came from the
 * exchange). Without `byHand` (an older server) only the total is said. Empty when nothing is saved. */
export function holidaysSaved(saved: number, byHand?: number | null): string {
  if (!(saved > 0)) return "";
  if (byHand == null) return `${saved} saved.`;
  const hand = Math.min(Math.max(byHand, 0), saved);
  if (hand === 0) return `${saved} saved, all from the exchange.`;
  if (hand === saved) return `${saved} saved, all added by you.`;
  return `${saved} saved: ${saved - hand} from the exchange, ${hand} added by you.`;
}
