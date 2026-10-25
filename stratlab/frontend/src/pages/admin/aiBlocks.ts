import { fmtDateTime, IST } from "../../lib/format";

/** "Blocked by owner@example.com at 9 Oct 2026, 14:05 IST", or what is known of it (a block made before this was recorded has neither). */
export function blockedLine(by?: string | null, at?: number | null): string {
  const when = at ? fmtDateTime(at * 1000, { tz: IST, zone: true }) : null;
  if (!by && !when) return "Blocked (who and when weren't recorded)";
  return `Blocked${by ? ` by ${by}` : ""}${when ? ` at ${when}` : ""}`;
}

/** A provider's badge from its last real result, the same reading Overview's summary counts (DJ-031: "OK, Working" on one
 * the summary counted as failing; "Measured" on one never tried, whose provider listed no models). `state` is the
 * server's light; `result` its last result (older servers send none). */
export function providerWord(p: { state: "ok" | "warn" | "fail" | "off" | "idle"; result?: string | null; ranked_at: number | null; discovered: number | null }):
  ["ok" | "warn" | "bad" | null, string] {
  if (p.state === "off") return [null, "No key"];
  if (p.result === "failed") return ["bad", "Failing"];
  if (p.result === "quota") return ["warn", "Out of credit"];
  if (p.result === "paused") return ["warn", "Paused"];
  if (p.result === "untested" || (p.state === "idle" && !p.result)) {
    return [null, p.ranked_at && p.discovered === 0 ? "Not tried · key may be wrong" : p.ranked_at && !p.result ? "Measured" : "Not tried yet"];
  }
  if (p.result === "working") return p.state === "ok" ? ["ok", "Working"] : ["warn", "Check"];
  return p.state === "ok" ? ["ok", "OK"] : p.state === "warn" ? ["warn", "Check"] : p.state === "fail" ? ["bad", "Problem"] : [null, "Not tested"];
}
