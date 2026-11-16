/* The words for a person's limits (lib/usage.ts reads them; no imports, so the unit tests read this file on its own). */

export type UsageRow = { key: string; label: string; used: number | null; limit: number | null; left: number | null; resets: "day" | "month" | null };
export type Usage = { plan: string; rows: UsageRow[]; refresh_off?: boolean;
  /** LIVE9A-003: a Free account still on the counts it had before the smaller Free plan: until when, and Free's own counts after */
  grace?: { until: string; reads_after: number; decks_after: number } | null };

/** Refreshes left today: the fresh AI reads left, the one daily count Plans and Account state (LIVE7B-002: a separate "30 left today"
 * on Pro, whose Plans row says Unlimited), or null when there's no limit (or it isn't known yet). */
export function refreshesLeft(u: Usage | null): number | null {
  const r = u?.rows.find((x) => x.key === "research_ai");
  return r ? r.left : null;
}

const graceDay = (iso: string): string => {
  const d = new Date(new Date(iso).getTime() + 5.5 * 3600_000);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
};

/** The note beside Refresh: "4 left today", and on a Free account still on its earlier counts, until when and what Free has after
 * (LIVE9A-003: "60 left today" on Free beside a Plans page saying Free has 5 read as a broken limit). */
export function leftWord(left: number, u: Usage | null): string {
  const base = left === 0 ? "None left today" : `${left} left today`;
  return u?.grace ? `${base} (${u.grace.reads_after} a day from ${graceDay(u.grace.until)})` : base;
}

/** LIVE9A-003: the decks note beside a theme's or a company's download buttons: "Decks this month: 1 of 5", and on a Free account still on its
 * earlier counts, "(the sample deck only from 27 Nov)"; null with no monthly limit (Pro) or none on the plan (the locked button says it). */
export function decksWord(used: number | null | undefined, limit: number | null | undefined, u: Usage | null): string | null {
  if (limit == null || limit === 0) return null;
  const base = `Decks this month: ${used ?? 0} of ${limit}`;
  return u?.grace && u.grace.decks_after === 0 ? `${base} (the sample deck only from ${graceDay(u.grace.until)})` : base;
}

/** FREE-TIER: the plan has no Refresh at all (Free: the server's refresh_off): the button says where it is, never "back at midnight". */
export function refreshNotOnPlan(u: Usage | null): boolean {
  return u?.refresh_off === true;
}
export const REFRESH_ON_BASIC = "Refreshing a stored read is on Basic and Pro";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** When a limit starts again, in words: "Midnight India time", "1 Dec", or "When you remove one" for a kept count. */
export function resetsWord(r: Pick<UsageRow, "resets">, now: Date = new Date()): string {
  if (r.resets === "day") return "Midnight India time";
  if (r.resets === "month") {
    const ist = new Date(now.getTime() + 5.5 * 3600 * 1000);
    return `1 ${MONTHS[(ist.getUTCMonth() + 1) % 12]}`;
  }
  return "When you remove one";
}

/** "3 of 10", "3 (no limit)", or "–" when the count isn't kept. */
export function usedWord(r: Pick<UsageRow, "used" | "limit">): string {
  if (r.used == null) return "–";
  return r.limit == null ? `${r.used} (no limit)` : `${r.used} of ${r.limit}`;
}

/** A stored size in plain units: "820 B", "14.2 KB", "3.1 MB". */
export function bytesText(n: number | null | undefined): string {
  if (n == null) return "–";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** Seconds of work in plain units: "40 s", "12 min", "3.5 h". */
export function hoursText(seconds: number): string {
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}
