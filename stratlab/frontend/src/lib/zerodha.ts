/* What the connected Zerodha account last returned, said plainly (R7M-009): a connected account that returned nothing is a
 * state of its own, not an empty page, and the card's line names a time zone and drops "tap to refresh tomorrow". */
import { IST, quoteAt } from "./format";

export type ZerodhaRead = { live?: boolean; count: number | null; read_at: string | null };

/** "Zerodha is connected; it returned 0 holdings at 06:11 IST." (or "at 7 Oct, 15:29 IST" for an earlier day); null when
 * Zerodha isn't connected, hasn't been read, or returned some holdings. */
export function zerodhaEmpty(z: ZerodhaRead | null | undefined, now: Date = new Date()): string | null {
  if (!z || z.count !== 0 || !z.read_at) return null;
  const at = quoteAt(z.read_at, IST, now);
  return at ? `Zerodha is connected; it returned 0 holdings at ${at}.` : null;
}

/** The Zerodha card's status line. `label` is the server's "today 09:12" / "yesterday 23:00" in India time. */
export function zerodhaLine(k: { live: boolean; refreshed_label: string | null; count: number | null }): string {
  const read = k.refreshed_label ? `last read ${k.refreshed_label} IST` : "not read yet";
  const holdings = k.count != null ? ` · ${k.count} holding${k.count === 1 ? "" : "s"}` : "";
  return k.live
    ? `Connected · ${read}${holdings}`
    : `Today's login has ended · ${read} · log in again to read your holdings`;
}
