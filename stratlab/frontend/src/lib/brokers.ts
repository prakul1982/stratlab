/* The broker logins on Settings -> Connected accounts (Zerodha, Upstox, Angel One, Dhan), said the same way for each: its status,
 * its line (last read, holdings, when the broker ends the login) and the list of names a page can offer. Facts only. */
import { IST, quoteAt } from "./format";

export type BrokerStatus = {
  key: string; name: string; configured?: boolean; available: boolean; connected: boolean; live: boolean; expired?: boolean;
  refreshed_label: string | null; count: number | null; detail: string | null; ends_at?: string | null;
};

/** The badge: what the broker's row says first. */
export function brokerBadge(b: Pick<BrokerStatus, "configured" | "available" | "connected" | "live">): { tone: "ok" | "warn" | "plain"; text: string } {
  if (b.configured === false) return { tone: "plain", text: "Not set up yet" };
  if (!b.available) return { tone: "plain", text: "Not open yet" };
  if (!b.connected) return { tone: "plain", text: "Not connected" };
  return b.live ? { tone: "ok", text: "Connected" } : { tone: "warn", text: "Log in again" };
}

/** "Connected · last read today 09:12 IST · 4 holdings · this login ends at 03:30 IST" (as Zerodha's line, zerodha.ts), or that the login has ended; "" when not connected.
 * `refreshed_label` is the server's "today 09:12" in India time; `ends_at` is when the broker ends the live login by itself. */
export function brokerLine(b: BrokerStatus, now: Date = new Date()): string {
  if (!b.connected || !b.available) return "";
  const read = b.refreshed_label ? `last read ${b.refreshed_label} IST` : "not read yet";
  const holdings = b.count != null ? ` · ${b.count} holding${b.count === 1 ? "" : "s"}` : "";
  const ends = b.ends_at ? quoteAt(b.ends_at, IST, now) : "";
  return b.live
    ? `Connected · ${read}${holdings}${ends ? ` · this login ends ${ends.includes(",") ? "on " : "at "}${ends}` : ""}`
    : `This login has ended · ${read} · log in again to read your holdings`;
}

/** "Zerodha", "Zerodha or Upstox", "Zerodha, Upstox or Dhan". */
export function orList(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}`;
}
