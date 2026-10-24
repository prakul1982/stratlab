/* When Indian price data comes back, in words: the one place the top banner, the market picker and the questions about an
 * idea take it from (`me.data_note.back_at`, the next automatic data login), so none of them tells a different story (DA-004). */

export type DataNote = { closed: "weekend" | "holiday" | null; back_at: string | null };

/** "Sun 25 Oct, 08:00 IST", and the reader's own clock beside it when that is another zone ("… (Sun 25 Oct, 02:30 your time)").
 * Null when the next login isn't known. The day and time in India come first: that is where the login happens (R46-011, R48-003). */
export function reconnectAt(note: DataNote | null | undefined, localTz?: string): string | null {
  const at = note?.back_at ? new Date(note.back_at) : null;
  if (!at || Number.isNaN(at.getTime())) return null;
  const fmt = (tz?: string) => `${at.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: tz }).replace(",", "")}, ${at.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz })}`;
  const local = localTz ?? (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return ""; } })();
  const inIndia = local === "Asia/Kolkata" || local === "Asia/Calcutta";
  return `${fmt("Asia/Kolkata")} IST${inIndia ? "" : ` (${fmt(local || undefined)} your time)`}`;
}

/** The markets whose prices come through the Indian data login. */
export const INDIA_FEED = new Set(["IN", "MCX", "CDS"]);

/** Why an Indian market can't be searched right now, and when it can: the time is the banner's own. */
export function offlineLine(marketName: string, note: DataNote | null | undefined, localTz?: string): string {
  const back = reconnectAt(note, localTz);
  return `Market data for ${marketName} is offline right now. ${back ? `It reconnects on ${back}.` : "It reconnects with the next daily data login."}`;
}
