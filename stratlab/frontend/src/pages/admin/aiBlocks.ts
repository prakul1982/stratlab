import { fmtDateTime, IST } from "../../lib/format";

/** "Blocked by owner@example.com at 9 Oct 2026, 14:05 IST", or what is known of it (a block made before this was recorded has neither). */
export function blockedLine(by?: string | null, at?: number | null): string {
  const when = at ? fmtDateTime(at * 1000, { tz: IST, zone: true }) : null;
  if (!by && !when) return "Blocked (who and when weren't recorded)";
  return `Blocked${by ? ` by ${by}` : ""}${when ? ` at ${when}` : ""}`;
}
