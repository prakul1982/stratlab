import { marketState } from "./marketHours";
import type { Market } from "./types";

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

/** When the Indian market next opens, as "Mon 26 Oct, 09:15 IST": the market's own hours and holidays (marketState), so a
 * weekend says when trading resumes, not when the data login runs (DD-006, DC-002: "reconnects Sun 25 Oct 08:00" read as
 * if the market opened on Sunday). Null when the market isn't known yet or is open. */
export function nextOpenAt(m: Market | null | undefined, now = new Date()): string | null {
  if (!m?.hours?.open) return null;
  const s = marketState({ ...m, status: "live" }, now);
  if (s.open || !s.change) return null;
  const tz = "Asia/Kolkata";
  const day = s.change.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: tz }).replace(",", "");
  return `${day}, ${s.change.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: tz })} IST`;
}

/** The top banner's one line while Indian data is offline on a day the market is shut anyway: short, and about the market,
 * not the data feed (DD-006, DP2-036: two wrapped lines on every page, with "your own data work as usual"). */
export function closedLine(closed: "weekend" | "holiday", nextOpen: string | null): { full: string; short: string } {
  const why = closed === "weekend" ? "closed for the weekend" : "closed today for an exchange holiday";
  return {
    full: `Indian markets are ${why}${nextOpen ? ` and open again ${nextOpen}` : ""}. Indian prices are the last close.`,
    short: nextOpen ? `Indian markets open ${nextOpen}` : `Indian markets ${closed === "weekend" ? "closed for the weekend" : "closed today"}`,
  };
}
